"""NF-WK-RC1 ① — the realized artifact has a RECURRING WRITER, and it can refuse.

⛔ THE DEFECT THIS GUARDS IS AN ABSENCE. Phase A published 2026 week 1 by hand and nothing was
scheduled to publish week 2 — "an operator runs a CLI every Tuesday" is the silent-freeze class with
a human as the cron (NF-FRESH1's 19 green runs, one layer earlier: there was no run at all). Every
clause below is about a property no single file shows: an EDGE on the compiled graph, a monitor
hosted outside its own subject, a decision table, and a window sized from a measurement.

⚠️ THE JOB MODULE IS LOADED BY PATH (E11.23) — importing `pipeline.jobs...` executes
`pipeline/__init__.py`, which reads the gitignored dbt manifest and dies at COLLECTION on CI. A skip
would be worse than a failure here: these are exactly the clauses that must run in the environment
that gates the merge.
"""

from __future__ import annotations

import contextlib
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

from app.backend.services import realized_dst, weekly_recap
from betting_ml.monitoring import nfl_realized_freshness as RF
from quant_sports_intel_models.football.nfl.fantasy import realized_week as RW

_REPO = Path(__file__).resolve().parents[2]
_JOB_PATH = _REPO / "pipeline/jobs/sports_nfl_weekly_serving_job.py"
_INJURIES_PATH = _REPO / "pipeline/jobs/sports_nfl_sleeper_injuries_job.py"
_RUNNER_PATH = _REPO / "quant_sports_intel_models/football/nfl/fantasy/run_realized_week.py"


_MISSING = object()

#: The `pipeline.*` names the injuries job imports AT TOP LEVEL. Pre-seeding these is what lets it
#: be loaded without executing `pipeline/__init__.py` — see `_pipeline_stubbed`.
_PIPELINE_NAMES = (
    "pipeline",
    "pipeline.jobs",
    "pipeline.jobs.sports_dbt_job",
    "pipeline.jobs.sports_nfl_weekly_serving_job",
)


@contextlib.contextmanager
def _pipeline_stubbed():
    """Make `pipeline.*` importable WITHOUT running `pipeline/__init__.py`, then restore exactly.

    ⛔⛔ E11.23, AND THIS FILE WALKED INTO IT ON CI AFTER PASSING LOCALLY — which is the whole
    lesson. `pipeline/__init__.py` reads the GITIGNORED `dbt/target/manifest.json` at import, and
    this worktree carries a SYMLINK to the main checkout's copy, so the two clauses that load the
    injuries job (which imports `pipeline.jobs.*` at top level, unlike the weekly job module) passed
    here and died at COLLECTION on a CI runner. A developer machine cannot see this rule.

    ⭐ THE CURE IS NOT A SKIP. A skipped clause is a vacuous anchor in the one environment that
    gates the merge — CI would never run the "a monitor is not hosted inside its own subject"
    property these tests exist for. Instead the package NAMES are pre-seeded in `sys.modules` and
    the two submodules actually needed are loaded BY PATH under their real names, so Python's
    import machinery finds everything already present and executes no package `__init__`.

    ⚠️ RESTORED EXACTLY on exit, including keys that were ABSENT before (the `_MISSING` sentinel).
    pytest imports every test module during collection and xdist shares a worker across files, so a
    leaked `sys.modules` entry is the "passes in isolation, fails in the full run" flake this repo
    already paid for once (`_serving_store_loader`).
    """
    saved = {name: sys.modules.get(name, _MISSING) for name in _PIPELINE_NAMES}
    try:
        for pkg in ("pipeline", "pipeline.jobs"):
            mod = ModuleType(pkg)
            mod.__path__ = [str(_REPO / pkg.replace(".", "/"))]
            sys.modules[pkg] = mod
        for mod_name, rel in (
            ("pipeline.jobs.sports_dbt_job", "pipeline/jobs/sports_dbt_job.py"),
            ("pipeline.jobs.sports_nfl_weekly_serving_job",
             "pipeline/jobs/sports_nfl_weekly_serving_job.py"),
        ):
            sys.modules[mod_name] = _load(_REPO / rel, mod_name)
        yield
    finally:
        for name, prior in saved.items():
            if prior is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"could not load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _by_path(path: Path, name: str):
    """Load a job module by path. The injuries job additionally needs `pipeline.*` pre-seeded."""
    if path == _INJURIES_PATH:
        with _pipeline_stubbed():
            return _load(path, name)
    return _load(path, name)


def test_the_weekly_job_module_still_needs_no_pipeline_package_at_import():
    """⭐ THE PRECONDITION THAT MAKES THE LOADER ABOVE SOUND, asserted rather than assumed.

    Loading the weekly job by path is only safe while that module imports nothing from `pipeline` at
    top level. If it ever does, this clause fails HERE with a readable reason instead of the whole
    file dying at collection on CI with a FileNotFoundError about a dbt manifest.
    """
    src = _JOB_PATH.read_text()
    offenders = [
        ln.strip() for ln in src.splitlines()
        if ln.startswith(("from pipeline", "import pipeline"))
    ]
    assert not offenders, (
        f"{_JOB_PATH.name} now imports the pipeline package at top level: {offenders}. That "
        "executes `pipeline/__init__.py`, which reads the gitignored dbt manifest — see "
        "`_pipeline_stubbed`."
    )


def _edges(job):
    out = []
    for node, deps in job.graph.dependencies.items():
        for dep in deps.values():
            out.append((node.alias or node.name, dep.node))
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1 — THE CADENCE EXISTS, AND IT IS SEQUENCED BEHIND ITS OWN FEED
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_realized_publish_runs_downstream_of_the_stats_ingest_it_reads():
    """⭐ THE INC-25 RULE AS A GRAPH PROPERTY. The artifact is built from `stats_player_week`, which
    `nfl_weekly_stats_ingest_op` writes — on separate schedules the publish could read a lake the
    ingest had not touched, which is the whole shape of NF-INC-0916 one table over."""
    job = _by_path(_JOB_PATH, "_rc1_job").sports_nfl_weekly_serving_job
    edges = _edges(job)
    assert edges, "the job graph has no dependencies at all — this clause would pass on nothing"
    names = {d for d, _ in edges} | {u for _, u in edges}
    assert "nfl_realized_week_publish_op" in names, (
        "the realized-week publish is not in the weekly serving job at all. Nothing else publishes "
        "it, so the recap surface renders whatever week an operator last ran by hand."
    )
    upstream = {d: {u for dd, u in edges if dd == d} for d, _ in edges}
    assert "nfl_weekly_stats_ingest_op" in upstream.get("nfl_realized_week_publish_op", set()), (
        "the realized publish is NOT downstream of the training-feed ingest — it would read the "
        "lake as it was BEFORE this run refreshed it (INC-25)."
    )


def test_the_realized_publish_is_not_downstream_of_the_projection_build():
    """⛔ TWO UNRELATED FAILURES MUST NOT SHARE A FATE. `nfl_weekly_serving_op` RAISES on a refusal,
    often correctly. If the realized publish hung off it, a refused PROJECTION would withhold the
    REALIZED facts — a different product, on a different input, for no reason."""
    job = _by_path(_JOB_PATH, "_rc1_job2").sports_nfl_weekly_serving_job
    edges = _edges(job)
    upstream: dict[str, set[str]] = {}
    for d, u in edges:
        upstream.setdefault(d, set()).add(u)

    def reaches(node: str, target: str, seen=None) -> bool:
        seen = seen or set()
        for u in upstream.get(node, ()):
            if u == target or (u not in seen and reaches(u, target, seen | {u})):
                return True
        return False

    assert not reaches("nfl_realized_week_publish_op", "nfl_weekly_serving_op"), (
        "the realized publish is downstream of the projection build — a refused build would now "
        "also withhold the realized week."
    )
    assert not reaches("nfl_weekly_serving_op", "nfl_realized_week_publish_op"), (
        "the projection build is downstream of the realized publish — a lake hiccup in the "
        "realized read would now sink a perfectly good projection."
    )


def test_the_realized_publish_subprocess_is_bounded():
    """INC-32 — a finite timeout, and `run_bounded` so the whole process group dies on expiry."""
    src = _JOB_PATH.read_text()
    start = src.index("def nfl_realized_week_publish_op(")
    end = src.index("def _parse_result_line(")
    assert start < end, "the op no longer precedes its result parser — re-anchor this slice"
    body = src[start:end]
    assert "run_bounded(" in body, "the realized publish does not use the bounded-subprocess helper"
    assert "timeout=NFL_REALIZED_PUBLISH_TIMEOUT_SECONDS" in body, (
        "the realized publish subprocess has no finite timeout"
    )


def test_the_cadence_inherits_a_heartbeat_rather_than_adding_an_instigator():
    """⭐ NO NEW SCHEDULE. The publish rides `sports_nfl_weekly_serving_schedule`, which already
    ships `default_status=RUNNING` and is in the required-RUNNING heartbeat set — so a Dagster-DB
    reset that silently reverts it PAGES instead of freezing the artifact (NF-INFRA1/E11.23)."""
    from betting_ml.monitoring.monitor_health import CRITICAL_SCHEDULES

    assert "sports_nfl_weekly_serving_schedule" in CRITICAL_SCHEDULES, (
        "the schedule hosting the realized cadence is not in the heartbeat's required-RUNNING set, "
        "so a silent revert to STOPPED would freeze the artifact with nothing paging."
    )
    sched_src = (_REPO / "pipeline/schedules/sports_rollforward_schedules.py").read_text()
    assert "default_status=DefaultScheduleStatus.RUNNING" in sched_src, (
        "the hosting schedule no longer self-starts"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2 — THE MONITOR IS NOT HOSTED INSIDE ITS OWN SUBJECT
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_realized_freshness_backstop_runs_on_a_different_job_than_its_subject():
    """⛔ A monitor inside the job it judges cannot see that job STOP. The event it exists for is
    `sports_nfl_weekly_serving_job` never running — no run, no failure, no page, and the last run
    in Dagit a genuine green one."""
    subject = _by_path(_JOB_PATH, "_rc1_job3").sports_nfl_weekly_serving_job
    host = _by_path(_INJURIES_PATH, "_rc1_inj").sports_nfl_sleeper_injuries_job
    subject_ops = {n.name for n in subject.graph.node_defs}
    host_ops = {n.name for n in host.graph.node_defs}
    assert "nfl_realized_freshness_op" in host_ops, (
        "the realized freshness backstop is not invoked anywhere — a named escalation path that "
        "does not run is worse than an absent one (the NF-C6-PH2 finding, verbatim)."
    )
    assert "nfl_realized_freshness_op" not in subject_ops, (
        "the backstop is hosted inside the very job it judges, so it can only ever agree with a run "
        "that happened."
    )


def test_the_backstop_is_an_independent_leaf_on_its_host():
    """A Sleeper outage must not blind the realized monitor — no `ins`, nothing upstream."""
    host = _by_path(_INJURIES_PATH, "_rc1_inj2").sports_nfl_sleeper_injuries_job
    for node, deps in host.graph.dependencies.items():
        if (node.alias or node.name) == "nfl_realized_freshness_op":
            assert not deps, "the backstop has upstream dependencies; it must be an independent leaf"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3 — WHICH WEEKS A FIRE PUBLISHES (the FINAL gate, and self-healing)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_a_partial_week_is_never_planned_by_the_cadence():
    """⛔ THE PM GATE (2026-09-16): a scheduled fire publishes a FINAL week or nothing. A pre-MNF
    Monday fire would otherwise ship 15/16 games, and that week's Monday-night players would render
    as absences indistinguishable from 'did not play'."""
    states = {1: "final", 2: "partial", 3: "not_started"}
    plan = RW.plan_auto(states, published_weeks=set())
    assert [p["week"] for p in plan] == [1], (
        f"the cadence planned {[p['week'] for p in plan]} — a partial or not-started week is in it"
    )


def test_the_cadence_heals_a_gap_it_previously_missed():
    """Self-healing: a week the cadence never landed (a run that was down) is picked up later."""
    states = {w: "final" for w in range(1, 9)}
    plan = RW.plan_auto(states, published_weeks={1, 2, 4, 5, 6, 7, 8})
    assert {p["week"] for p in plan if p["reason"] == "missing"} == {3}


def test_the_cadence_rewatches_only_the_recent_restatement_window():
    """⚠️ A DELIBERATE SCOPE LIMIT, asserted so it stays deliberate. Re-building all 18 weeks daily
    would spend a season's lake reads watching a window that closed months ago; a restatement older
    than the window is not detected by the cadence, and the single-week CLI covers it on demand."""
    states = {w: "final" for w in range(1, 11)}
    plan = RW.plan_auto(states, published_weeks=set(range(1, 11)))
    watched = {p["week"] for p in plan}
    assert watched == {8, 9, 10}, f"the restatement window watched {watched}"
    assert all(p["reason"] == "restatement_window" for p in plan)


def test_the_completeness_map_delegates_to_the_one_count_rule():
    """⭐ ONE OWNER OF 'FINAL'. A second comparison here could drift from the single-week path, and
    the two answering differently is precisely how a half-played week renders as final."""
    states = RW.week_completeness_map({1: 16, 2: 15, 3: 0}, {1: 16, 2: 16, 3: 16})
    assert states == {1: "final", 2: "partial", 3: "not_started"}
    assert states[1] == RW.completeness(16, 16)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4 — WHAT A SECOND PUBLISH OF THE SAME WEEK MEANS
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _man(state="final", sha="abc"):
    return {"season": 2026, "week": 3, "completeness": state, "content_sha256": sha}


def test_nothing_published_is_a_create():
    d = RW.publish_decision(_man(), None)
    assert d["action"] == "create" and d["servingWrite"] and not d["event"]


def test_identical_content_writes_nothing_and_raises_no_event():
    """A routine re-run must not manufacture events — an event stream that fires on nothing is
    ignored within a week (the muted-monitor pattern)."""
    d = RW.publish_decision(_man(), _man())
    assert d["action"] == "unchanged"
    assert not d["servingWrite"] and not d["event"]


def test_a_partial_week_is_upgraded_by_a_final_one():
    d = RW.publish_decision(_man("final", "new"), _man("partial", "old"))
    assert d["action"] == "upgrade" and d["servingWrite"]


def test_a_final_week_is_never_replaced_by_a_partial_one():
    """A mid-week hand-run must not clobber a complete week with an incomplete one."""
    d = RW.publish_decision(_man("partial", "new"), _man("final", "old"))
    assert d["action"] == "refuse_downgrade"
    assert not d["servingWrite"], "a downgrade reached the served keys"
    assert d["event"], "a refused publish must be surfaced, not silently swallowed"


def test_a_restatement_keeps_the_published_week_serving():
    """⭐ THE RULING ALREADY MADE, one artifact over (`weekly_recap_store`): the stored record keeps
    serving and the restatement is a NAMED EVENT — never a number that changes underneath a reader
    with no explanation."""
    d = RW.publish_decision(_man("final", "new"), _man("final", "old"))
    assert d["action"] == "restate"
    assert not d["servingWrite"], "a restatement overwrote the served week"
    assert d["event"]


def test_an_uncomparable_published_week_is_not_reported_as_unchanged():
    """⛔ NF1.7(a): a week published before the hash existed cannot be compared, and answering 'we
    could not tell' with 'unchanged' is a vacuous pass. It gets its own visible action."""
    prior = {"season": 2026, "week": 3, "completeness": "final"}  # no content_sha256
    d = RW.publish_decision(_man("final", "new"), prior)
    assert d["action"] == "backfill_hash"
    assert d["action"] != "unchanged"


def test_only_declared_actions_reach_the_served_keys():
    """The write set is DERIVED, so a new action cannot become a serving write by omission."""
    assert RW._SERVING_WRITE_ACTIONS == {"create", "upgrade", "backfill_hash"}
    for action in ("unchanged", "restate", "refuse_downgrade"):
        assert action not in RW._SERVING_WRITE_ACTIONS


def test_the_content_hash_ignores_row_order_but_not_row_content():
    """DuckDB promises no ordering, so an ordering difference must not read as a restatement — and
    a real change must not be hidden by the canonicalisation."""
    a = [{"game_id": "g2", "player_id": "p1", "yards": 10},
         {"game_id": "g1", "player_id": "p2", "yards": 20}]
    assert RW.content_hash(a) == RW.content_hash(list(reversed(a)))
    b = [dict(a[0], yards=11), a[1]]
    assert RW.content_hash(a) != RW.content_hash(b), "a real stat change did not move the hash"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5 — THE FRESHNESS BACKSTOP'S VERDICTS
# ══════════════════════════════════════════════════════════════════════════════════════════════

_NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def _reading(**kw):
    base = dict(season=2026, published_weeks=set(), lake_final_weeks=set(), slate_end_by_week={})
    base.update(kw)
    return RF.RealizedReading(**base)


def test_no_final_week_is_inactive_and_never_pages():
    """⏳ ACTIVE-SEASON SEMANTICS. Out of season the artifact correctly does not advance, and an SLA
    that paged on that would be muted within a fortnight (INC-45)."""
    v = RF.classify(_reading(), now=_NOW)
    assert v["verdict"] == "INACTIVE"
    assert not RF.is_problem(v)
    assert v["verdict"] != "OK", "'nothing to check' must not be reported as 'checked and healthy'"


def test_every_final_week_published_is_ok():
    v = RF.classify(_reading(lake_final_weeks={1, 2}, published_weeks={1, 2}), now=_NOW)
    assert v["verdict"] == "OK" and not RF.is_problem(v)


def test_a_just_completed_week_inside_the_window_does_not_page():
    """The vendor's own lag plus one cadence. Paging here would be paging about someone else's
    schedule, every single week."""
    v = RF.classify(_reading(lake_final_weeks={1}, published_weeks=set(),
                             slate_end_by_week={1: _NOW - timedelta(hours=5)}), now=_NOW)
    assert v["verdict"] == "AWAITING_PUBLISH" and not RF.is_problem(v)


def test_an_overdue_newest_week_pages_critical():
    v = RF.classify(_reading(lake_final_weeks={1, 2}, published_weeks={1},
                             slate_end_by_week={2: _NOW - timedelta(hours=RF.GRACE_HOURS + 2)}),
                    now=_NOW)
    assert v["verdict"] == "STALE" and v["severity"] == "CRITICAL"


def test_nothing_published_at_all_pages_critical():
    """The shape 2026 week 1 was lost in."""
    v = RF.classify(_reading(lake_final_weeks={1}, published_weeks=set(),
                             slate_end_by_week={1: _NOW - timedelta(hours=RF.GRACE_HOURS + 2)}),
                    now=_NOW)
    assert v["verdict"] == "NOTHING_PUBLISHED" and v["severity"] == "CRITICAL"


def test_an_older_gap_alone_is_lower_severity_than_a_stale_newest_week():
    """A filled newest week with a hole behind it is a self-healing failure, not a stale surface."""
    old = _NOW - timedelta(hours=RF.GRACE_HOURS + 2)
    v = RF.classify(_reading(lake_final_weeks={1, 2}, published_weeks={2},
                             slate_end_by_week={1: old, 2: old}), now=_NOW)
    assert v["verdict"] == "STALE" and v["severity"] == "ERROR"


def test_an_unevaluable_reading_is_warn_and_never_healthy():
    v = RF.classify(_reading(error="ClientError: denied"), now=_NOW)
    assert v["verdict"] == "UNEVALUABLE" and v["severity"] == "WARN"
    assert RF.is_problem(v), "an unevaluable check must not be silent"


def test_an_unresolvable_slate_end_delays_a_page_rather_than_inventing_one():
    """A monitor that guesses in the paging direction on absent evidence buries real findings."""
    v = RF.classify(_reading(lake_final_weeks={1}, published_weeks=set()), now=_NOW)
    assert v["verdict"] == "AWAITING_PUBLISH" and not RF.is_problem(v)


def test_the_grace_window_exceeds_the_measured_vendor_lag():
    """⛔ TIGHTENING THIS BELOW THE VENDOR'S OWN PUBLICATION LAG makes the monitor page every week
    about a feed that is behaving normally — measured at node 1 as ~23 h after the Monday close."""
    assert RF.GRACE_HOURS > RF.VENDOR_LAG_HOURS + RF.CADENCE_HOURS, (
        "the grace window no longer covers the vendor lag plus one full cadence"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6 — THE PUBLISHED-WEEK SCAN, AND THE MNF TAG (PM ④ / card yOhLHprC)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_a_parked_revision_does_not_read_as_a_published_week():
    """⛔ Otherwise a RESTATED week looks published and a genuine gap hides behind its own revision."""
    runner = _by_path(_RUNNER_PATH, "_rc1_runner")

    class _S3:
        def get_paginator(self, _):
            class P:
                def paginate(self, **kw):
                    return [{"Contents": [
                        {"Key": "fantasy/nfl/realized/2026/1/manifest.json"},
                        {"Key": "fantasy/nfl/realized/2026/2/manifest.revision-20260916T0100.json"},
                        {"Key": "fantasy/nfl/realized/2026/1/players.json"},
                    ]}]
            return P()

    assert runner._published_weeks(_S3(), "b", 2026) == {1}


_DST_PENDING_SCORED = {
    "teams": [{
        "teamKey": "1", "teamName": "T",
        "seats": [
            {"slot": "DEF", "seat": 0, "position": "DST", "team": "MIN",
             "name": "MIN", "points": 6.0, "platformPts": 6.0},
            {"slot": "DEF", "seat": 1, "position": "DST", "team": "SEA",
             "name": "SEA", "points": 8.0, "platformPts": 8.0},
        ],
    }]
}


def test_a_defence_whose_game_result_has_not_published_is_tagged_not_dropped():
    """⚠️ PM ④ / card yOhLHprC. `schedules` refreshes Monday 06:15 PT, BEFORE Monday Night Football,
    so the two MNF defences lack their points-allowed term every week for a reason that has nothing
    to do with the fXIYuvMN residual. They are TAGGED and split out — never removed, which would
    make 'could not compute' and 'agreed' the same number."""
    out = weekly_recap.compare_to_platform(
        _DST_PENDING_SCORED,
        dst_constructed={"MIN": 1.0, "SEA": 6.0},   # both diverge
        dst_result_pending={"MIN"},                 # …but MIN's is the known cadence artifact
    )
    dst = out["dstSeats"]
    assert dst["diverging"] == 2, "the raw count must stay visible"
    assert dst["divergingScheduleResultPending"] == 1
    assert dst["divergingUnexplained"] == 1, "the residual signal still counts the real one"
    assert {r["name"] for r in dst["scheduleResultPendingRows"]} == {"MIN"}
    assert len(dst["rows"]) == 2, "a tagged row was dropped from the record"
    assert [r["scheduleResultPending"] for r in dst["rows"]] == [True, False]


def test_the_tag_is_reported_as_unsupplied_rather_than_assumed_absent():
    """A caller that does not supply the pending set must not have its rows read as 'all clean' —
    `resultPendingSupplied` says which, so a silent omission is visible in the record."""
    out = weekly_recap.compare_to_platform(
        _DST_PENDING_SCORED, dst_constructed={"MIN": 1.0, "SEA": 6.0})
    assert out["dstSeats"]["resultPendingSupplied"] is False
    assert out["dstSeats"]["divergingScheduleResultPending"] == 0


def test_the_pending_predicate_has_one_owner_at_the_construction_site():
    """The tag and the cause must share a definition: points allowed is unavailable exactly when the
    opponent's score is, which is what `schedules` withholds until it refreshes."""
    assert realized_dst.result_pending(None) is True
    assert realized_dst.result_pending(24) is False
    assert realized_dst.points_allowed(None, 0) is None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7 — THE SERVED CONTRACT AND THE CLIENT THAT READS IT CANNOT DRIFT (Phase B)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# ⛔ WHY THIS IS WORTH A GUARD RATHER THAN CARE. A wrong field name in a TypeScript interface does
# not fail a build and does not throw: `undefined` renders as an empty cell, so the page reports a
# blank as data. MT1 lost two operator round-trips to probes that invented field names, and the
# same mistake one layer over is worse because a reader sees it as a fact about their league rather
# than as an error.
#
# ⭐ AND IT READS BOTH SIDES FROM THEIR OWN SOURCE. The Pydantic model is the server's declaration
# and the TS interface is the client's; a test that restated either would be a copy of the thing it
# is checking (the NF-C0e "a test that reads a value back under the key the code wrote" class).

_RECAP_TS = _REPO / "frontend/lib/fantasy.ts"


def _ts_interface_fields(name: str) -> set[str]:
    """The field names a TS interface declares, read out of the file rather than restated here."""
    src = _RECAP_TS.read_text()
    start = src.index(f"export interface {name} {{")
    body = src[start:src.index("\n}", start)]
    fields: set[str] = set()
    for line in body.splitlines()[1:]:
        stripped = line.strip()
        # Skip comments and block-comment continuations; a field line is `name?: type` / `name: type`.
        if not stripped or stripped.startswith(("//", "/*", "*")):
            continue
        head = stripped.split(":", 1)[0].strip()
        if head and head.replace("?", "").isidentifier():
            fields.add(head.rstrip("?"))
    return fields


def _model_fields(model_name: str) -> set[str]:
    from app.backend.models import nfl_recap

    return set(getattr(nfl_recap, model_name).model_fields)


def test_the_client_types_match_the_served_recap_contract_exactly():
    """Every field the server sends is declared by the client, and vice versa."""
    for model, interface in (
        ("RecapSeat", "RecapSeat"),
        ("RecapTeam", "RecapTeam"),
        ("WeeklyRecap", "WeeklyRecapPayload"),
        ("PowerRankingRow", "PowerRankingRow"),
        ("PowerRankings", "PowerRankingsPayload"),
    ):
        served = _model_fields(model)
        declared = _ts_interface_fields(interface)
        assert served, f"{model} declares no fields — this clause would pass on nothing"
        assert declared, f"{interface} parsed to no fields — the reader is broken, not the contract"
        assert served == declared, (
            f"{model} (server) and {interface} (client) disagree.\n"
            f"  only on the server: {sorted(served - declared)}\n"
            f"  only on the client: {sorted(declared - served)}\n"
            "A field the client does not declare renders as an empty cell, which the page reports "
            "as data rather than as an error."
        )


def test_the_two_totals_keep_different_names_on_the_wire():
    """⛔ PM ruling (i): the league's published total and our itemisation must never be presented as
    two estimates of one number. A single `total` field is the first step to exactly that, so the
    absence of one is asserted rather than left to a reviewer to notice."""
    served = _model_fields("RecapTeam")
    assert {"standingsTotal", "itemisedTotal"} <= served
    assert "total" not in served, (
        "RecapTeam grew a bare `total`. One name for two different facts is how the standings "
        "record and our explanation of it get treated as interchangeable."
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8 — THE BOX EXECUTES `app/backend` CODE, AND THE BOX DEPLOY IS NOT TRIGGERED BY IT
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# ⚠️ A TRIPWIRE, NOT A FIX — and the distinction is the point, because the fix is a decision this
# story does not get to take alone.
#
# `orchestration_cd.yml` deliberately EXCLUDES `app/backend/**`, and
# `test_orchestration_cd_paths.py::test_the_lambda_and_frontend_are_not_wired_to_the_box_deploy`
# pins that exclusion with a good reason: the API ships via `infrastructure/lambda/deploy.sh`, and
# wiring it to the box deploy would read as though merging deployed the API — the NF-C0 skew
# misconception, which has cost this repo real outages.
#
# ⛔ BUT THAT CLAUSE'S PREMISE — "a change the box does not run" — IS NO LONGER TRUE, and NF-WK-RC1
# is what made it untrue. Measured: before this story the box reached TWO `app/backend` modules
# (`models/nfl_weekly.py`, `services/projection_fields.py`, via `run_weekly_serving`); RC1's
# `realized_week.py` widened that to SIX by importing the scorer and the recap adapter.
#
# ⭐ THE LIVE EXPOSURE IS NARROWER THAN IT FIRST LOOKS, and saying so is what keeps this from being
# alarmism. A ONE-SCORER change necessarily also touches `quant_sports_intel_models/fantasy_engine/`,
# which IS a trigger path, so the box rebuilds anyway. What is genuinely unprotected is a change
# touching ONLY `app/backend/{services,models}` — and there is a concrete one: `EXPLANATION_COLUMNS`
# derives from `EXPLAINABLE_CAPTURED_TERMS` in `weekly_recap.py`, and `realized_week.required_columns`
# reads it to decide which lake columns the published artifact carries. A box on a stale image would
# publish an artifact missing a column, silently — which `realized_week`'s own header records as
# "how the split shipped as a no-op once".
#
# ⇒ SO THIS CLAUSE PINS THE CLOSURE RATHER THAN THE FILTER. Widening it fails here, loudly, and
# forces the decision to be taken deliberately instead of discovered later. The filter change itself
# is in `closeout.followUps` for the PM, because it means amending another story's ratified clause.

_BOX_ENTRYPOINTS = (
    "quant_sports_intel_models/football/nfl/fantasy/run_realized_week.py",
    "quant_sports_intel_models/football/nfl/fantasy/realized_week.py",
    "pipeline/jobs/sports_nfl_weekly_serving_job.py",
)

#: MEASURED 2026-09-16, not asserted from reading. Every `app/backend` module the box can reach from
#: the entrypoints above.
_BOX_REACHED_APP_BACKEND = {
    "app/backend/models/nfl_recap.py",
    "app/backend/models/nfl_weekly.py",
    "app/backend/services/league_scoring.py",
    "app/backend/services/projection_fields.py",
    # ⚠️ WIDENED 2026-09-17 by NF-WK-ACC1 (PM rider ⑥ — the divergence recorder's box-side inputs,
    # `realized_week.build_dst_inputs`, need `dst_row`). Taken deliberately: the part-2-mutable
    # construction (`team_week_inputs`) was placed in `realized_week.py`, a box-trigger path, so only
    # stable primitives sit in this module. The ⑪ filter decision stays routed to the hygiene bundle.
    "app/backend/services/realized_dst.py",
    "app/backend/services/realized_stat_fields.py",
    "app/backend/services/weekly_recap.py",
}


def _app_backend_closure(seeds) -> set[str]:
    """Every `app/backend` module reachable from `seeds`, by transitive import (NF-K1's method)."""
    import ast

    seen: set[str] = set()
    stack = list(seeds)
    reached: set[str] = set()
    while stack:
        rel = stack.pop()
        if rel in seen:
            continue
        seen.add(rel)
        path = _REPO / rel
        if not path.exists():
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            mods: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                mods.append(node.module)
                mods += [f"{node.module}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Import):
                mods += [a.name for a in node.names]
            for mod in mods:
                cand = mod.replace(".", "/") + ".py"
                if not (_REPO / cand).exists():
                    continue
                if mod.startswith("app.backend"):
                    reached.add(cand)
                    stack.append(cand)
                elif mod.split(".")[0] in ("quant_sports_intel_models", "betting_ml"):
                    stack.append(cand)
    return reached


def test_the_box_reached_app_backend_surface_has_not_widened():
    """⛔ A NEW `app/backend` IMPORT ON A BOX PATH IS A DEPLOY DECISION, not a refactor."""
    reached = _app_backend_closure(_BOX_ENTRYPOINTS)
    assert reached, "the closure is empty — this clause would pass on nothing"
    assert reached == _BOX_REACHED_APP_BACKEND, (
        "the set of `app/backend` modules the BOX executes has changed:\n"
        f"  newly reached: {sorted(reached - _BOX_REACHED_APP_BACKEND)}\n"
        f"  no longer reached: {sorted(_BOX_REACHED_APP_BACKEND - reached)}\n"
        "`orchestration_cd.yml` does NOT trigger a box rebuild on `app/backend/**` (deliberately — "
        "the API ships via deploy.sh). So every module in this set can go STALE on the box while "
        "CI is green. Widening it is a decision; take it deliberately and update the PM finding."
    )


def test_the_box_deploy_still_excludes_the_api_so_this_tripwire_is_not_moot():
    """Two-sided: if the exclusion is ever lifted, this whole clause stops being a hazard and should
    be retired rather than left as decoration (NF1.7(a) — a guard whose premise has gone away)."""
    wf = (_REPO / ".github/workflows/orchestration_cd.yml").read_text()
    triggers = [ln.strip().strip('- "') for ln in wf.splitlines() if ln.strip().startswith('- "')]
    assert not any(t.startswith("app/backend") or t == "app/**" for t in triggers), (
        "`app/backend` now triggers the box deploy, so the staleness hazard above is closed — "
        "retire this section instead of leaving a guard whose premise no longer holds."
    )
