"""NF-INFRA2 — guards for the automated NFL board publish: its freshness SLA and its publish-time
artifact checks.

⭐ WHAT THIS STORY ACTUALLY FOUND, because it changes what these guards are for. The card's premise
was that the board is hand-published by six manual commands. It is NOT: `sports_nfl_board_publish_job`
+ `sports_nfl_board_publish_schedule` have existed since NF-FRESH2 and the schedule self-starts
(`default_status=RUNNING`, NF-INFRA1). MEASURED on 2026-08-23, the live published manifest carried
`generated_at=2026-08-23T14:22:33Z` — 07:22 PT, i.e. the 07:15 PT schedule firing with no human in
the loop. So the automation exists and works; what it lacked was a way to notice it STOPPING, and
publish-time checks on two things a broken artifact leaves undisturbed.

Fast-gate safe: imports `betting_ml.monitoring`, never `pipeline` (E11.23 — importing the pipeline
package triggers the dbt-manifest read, which is absent in the fast gate). The wiring claims are
proved by AST over the job source rather than by importing Dagster; comments are irrelevant to an
AST assertion, so prose cannot satisfy these (INC-38).

Every claim here is falsifiable — `betting_ml/tests/nf_infra2_red_proof.py` re-introduces each
defect and requires the named test to go RED.
"""
from __future__ import annotations

import ast
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from betting_ml.monitoring import nfl_board_freshness as NBF

_REPO = Path(__file__).resolve().parents[2]
_SLEEPER_JOB = _REPO / "pipeline" / "jobs" / "sports_nfl_sleeper_injuries_job.py"
_PUBLISH_JOB = _REPO / "pipeline" / "jobs" / "sports_nfl_board_publish_job.py"
_SCHEDULES = _REPO / "pipeline" / "schedules" / "sports_rollforward_schedules.py"
_FIXTURE = Path(__file__).parent / "fixtures" / "nf_infra2_published_manifest.json"

#: The board publishes at 07:15 PT and the monitor rides the 06:30 PT NFL job, so a board published
#: exactly on schedule is already this old the next time anything looks at it. This number is the
#: reason an SLA may never equal its cadence.
NOMINAL_DAILY_LAG_HOURS = 23.25
SKIPPED_DAILY_LAG_HOURS = 47.25
NOMINAL_WEEKLY_LAG_HOURS = 167.25
SKIPPED_WEEKLY_LAG_HOURS = 335.25
#: The SLA must clear the nominal lag by enough to absorb REAL lateness (a slow build, a deploy
#: window), not merely by the arithmetic difference. An SLA equal to the cadence clears the
#: nominal lag by only 45 minutes, which is not tolerance — it is a coin flip.
MIN_LATENESS_TOLERANCE_HOURS = 2.0

_MID_DRAFT_SEASON = date(2026, 8, 20)      # daily cadence, well clear of both boundaries
_OFF_SEASON = date(2026, 11, 10)           # weekly cadence


def _fn(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {path.name}")


def _reading(*, lag_hours: float, now: datetime) -> NBF.BoardReading:
    return NBF.BoardReading(season=2026, generated_at=now - timedelta(hours=lag_hours),
                            adp_as_of="2026-08-20", coherence_present=True)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The SLA is derived from the cadence — and must not page on a healthy board
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_sla_exceeds_the_lag_a_perfectly_healthy_board_already_carries():
    """The monitor looks 45 minutes BEFORE the publish hour, so a healthy board is already 23.25h
    old when it is judged. An SLA equal to the cadence therefore tolerates only 45 minutes of real
    lateness — a monitor that fires on a slow build is one everybody mutes."""
    assert NBF.sla_hours(_MID_DRAFT_SEASON) >= NOMINAL_DAILY_LAG_HOURS + MIN_LATENESS_TOLERANCE_HOURS, (
        f"daily SLA {NBF.sla_hours(_MID_DRAFT_SEASON)}h leaves under "
        f"{MIN_LATENESS_TOLERANCE_HOURS}h of tolerance over a board published exactly on schedule "
        f"({NOMINAL_DAILY_LAG_HOURS}h old at check time)")
    assert NBF.sla_hours(_OFF_SEASON) >= NOMINAL_WEEKLY_LAG_HOURS + MIN_LATENESS_TOLERANCE_HOURS, (
        f"weekly SLA {NBF.sla_hours(_OFF_SEASON)}h leaves too little tolerance on the weekly cadence")


def test_a_skipped_publish_is_over_the_sla_on_both_cadences():
    """The event this monitor exists for. A bar that a skipped cycle does not cross is decoration."""
    assert NBF.sla_hours(_MID_DRAFT_SEASON) < SKIPPED_DAILY_LAG_HOURS
    assert NBF.sla_hours(_OFF_SEASON) < SKIPPED_WEEKLY_LAG_HOURS


def test_the_draft_season_boundary_uses_the_LOOSER_weekly_sla():
    """The seasonal-boundary hole (E9.48(c) / INC-37) applied to an SLA. On Aug 1 the newest
    publish may legitimately be the previous WEEKLY one, so the daily bar would false-page on
    exactly the day the daily cadence begins."""
    assert NBF.cadence_hours(date(2026, 8, 1)) == NBF.WEEKLY_CADENCE_HOURS
    assert NBF.cadence_hours(date(2026, 8, 2)) == NBF.WEEKLY_CADENCE_HOURS
    assert NBF.cadence_hours(date(2026, 8, 3)) == NBF.DAILY_CADENCE_HOURS, (
        "by the third day of draft season the daily cadence has certainly published — the tighter "
        "bar should be in force")
    assert NBF.cadence_hours(date(2026, 9, 16)) == NBF.WEEKLY_CADENCE_HOURS


def test_the_schedule_and_the_sla_read_the_SAME_cadence_predicate():
    """ONE owner. An SLA pinned separately from the cadence it judges is the "one logical thing,
    many owners" shape (INC-30/INC-36/INC-38) — they drift, and the monitor false-pages every
    off-season Tuesday. Asserted by AST so a re-declared local copy is caught even though the
    module would still import cleanly."""
    src = _SCHEDULES.read_text()
    tree = ast.parse(src)
    local_defs = [n.name for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "is_draft_season"]
    assert not local_defs, (
        "sports_rollforward_schedules re-defines is_draft_season locally — it must IMPORT it from "
        "betting_ml.monitoring.nfl_board_freshness, which the freshness SLA also reads")
    imported = any(
        isinstance(n, ast.ImportFrom)
        and n.module == "betting_ml.monitoring.nfl_board_freshness"
        and any(a.name == "is_draft_season" for a in n.names)
        for n in ast.walk(tree))
    assert imported, "the schedule must import is_draft_season from the monitoring module"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. classify — the stopped-schedule detector
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_frozen_board_is_STALE_and_carries_a_paging_severity():
    now = datetime(2026, 8, 20, 13, 30, tzinfo=timezone.utc)
    verdict = NBF.classify(_reading(lag_hours=SKIPPED_DAILY_LAG_HOURS, now=now), now=now)
    assert verdict["verdict"] == "STALE"
    assert verdict["severity"] in {"WARN", "CRITICAL"}, "a stale board must PAGE, not just log"


def test_a_long_freeze_escalates_to_CRITICAL():
    """Within 2x the SLA is a missed cycle; beyond it the publisher is not running at all —
    mirroring `sports_delta_freshness`, so the two sports monitors read the same way."""
    now = datetime(2026, 8, 20, 13, 30, tzinfo=timezone.utc)
    bar = NBF.sla_hours(now.date())
    assert NBF.classify(_reading(lag_hours=bar * 1.5, now=now), now=now)["severity"] == "WARN"
    assert NBF.classify(_reading(lag_hours=bar * 3, now=now), now=now)["severity"] == "CRITICAL"


def test_an_unreadable_board_is_UNVERIFIED_never_healthy():
    """NF1.7(a) — a check that could not run is not a check that passed."""
    verdict = NBF.classify(NBF.BoardReading(season=2026, error="AccessDenied"))
    assert verdict["verdict"] == "UNKNOWN"
    assert verdict["severity"] == "WARN"
    assert NBF.is_problem(verdict)


def test_the_stale_page_names_the_stopped_schedule_as_the_first_thing_to_check():
    """An alert that does not name its likeliest cause costs the operator the first hour (INC-40's
    other half). The dominant cause here is structurally invisible: no run at all."""
    now = datetime(2026, 8, 20, 13, 30, tzinfo=timezone.utc)
    detail = NBF.classify(_reading(lag_hours=SKIPPED_DAILY_LAG_HOURS, now=now),
                          now=now)["detail"]
    assert "sports_nfl_board_publish_schedule" in detail
    assert "STOPPED" in detail


def test_a_healthy_board_is_OK_and_does_not_page():
    now = datetime(2026, 8, 20, 13, 30, tzinfo=timezone.utc)
    verdict = NBF.classify(_reading(lag_hours=NOMINAL_DAILY_LAG_HOURS, now=now), now=now)
    assert verdict["verdict"] == "OK" and not NBF.is_problem(verdict)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. verify_manifest — the publish-time guards, on the artifact
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _real_manifest() -> dict:
    return json.loads(_FIXTURE.read_text())


def _at(blob: dict, offset_hours: float = 0.0) -> datetime:
    return datetime.fromisoformat(blob["generated_at"]) + timedelta(hours=offset_hours)


def test_the_REAL_published_manifest_passes_clean():
    """Non-vacuity, and the direction that actually matters: these guards must not page on the
    board production is serving right now. The fixture is REAL captured output, not a hand-written
    blob shaped by the guard's own assumptions (NF-C0e). `now` is derived from the fixture's own
    stamp so it can never rot into a failure as the file ages."""
    blob = _real_manifest()
    res = NBF.verify_manifest(blob, started=_at(blob, -0.5), now=_at(blob, 0.1))
    assert res["fatal"] == [], res["fatal"]
    assert res["alerts"] == [], res["alerts"]
    assert set(res["stamps"]) == {s.name for s in NBF.REQUIRED_FEED_STAMPS}
    assert all(v is not None for v in res["stamps"].values())


def test_a_REUSED_stale_export_is_FATAL():
    """Three steps exiting 0 prove each script ran; they do not prove a board advanced."""
    blob = _real_manifest()
    res = NBF.verify_manifest(blob, started=_at(blob, +6), now=_at(blob, +6))
    assert any("predates this run" in p for p in res["fatal"]), res


@pytest.mark.parametrize("stamp", NBF.REQUIRED_FEED_STAMPS, ids=lambda s: s.name)
def test_a_MISSING_feed_stamp_is_FATAL(stamp):
    """A board whose input vintage is UNKNOWN is the original NF-FRESH1 defect wearing a new
    stamp. Parametrized over the registry so a stamp added later cannot skip its guard."""
    blob = _real_manifest()
    cur = blob
    for key in stamp.path[:-1]:
        cur = cur[key]
    cur.pop(stamp.path[-1])
    res = NBF.verify_manifest(blob, started=_at(blob, -0.5), now=_at(blob, 0.1))
    assert any(stamp.name in p for p in res["fatal"]), res


def test_a_MISSING_coherence_block_is_FATAL():
    """The vacuous-guard class, caught on the artifact: if `report_publish_coherence` stops
    running, the NF-INJ1 guard is silently GONE while every step still exits 0. A guard that
    stopped running is indistinguishable from a guard that passed unless its OUTPUT is asserted."""
    blob = _real_manifest()
    blob.pop("coherence")
    res = NBF.verify_manifest(blob, started=_at(blob, -0.5), now=_at(blob, 0.1))
    assert any("coherence" in p for p in res["fatal"]), res


@pytest.mark.parametrize("stamp", NBF.REQUIRED_FEED_STAMPS, ids=lambda s: s.name)
def test_a_STALE_but_present_stamp_ALERTS_and_does_NOT_block_the_publish(stamp):
    """The ratified NF-INJ1 tiering (PM, 2026-08-21): HALTing a publish blocks every other fix
    riding it — the run that would have been blocked was the one that corrected 23 injured
    players. A known-stale feed is an honest, bounded degradation; the served `input_vintage`
    block reports it. ⇒ page, publish anyway."""
    blob = _real_manifest()
    now = _at(blob, stamp.max_lag_hours + 24)
    res = NBF.verify_manifest(blob, started=_at(blob, -0.5), now=now)
    assert any(stamp.name in a for a in res["alerts"]), res
    assert res["fatal"] == [], (
        f"a stale {stamp.name} must NOT be fatal — refusing to publish freezes the whole board "
        "over one late feed")


def test_a_non_OK_injury_coherence_verdict_ALERTS():
    blob = _real_manifest()
    blob["coherence"]["injury_input"] = {"verdict": "STALE", "detail": "injury status 400h old"}
    res = NBF.verify_manifest(blob, started=_at(blob, -0.5), now=_at(blob, 0.1))
    assert any("injury_input" in a for a in res["alerts"]), res
    assert res["fatal"] == []


def test_an_injury_verdict_that_is_ABSENT_is_reported_UNVERIFIED_not_healthy():
    blob = _real_manifest()
    blob["coherence"]["injury_input"] = {}
    res = NBF.verify_manifest(blob, started=_at(blob, -0.5), now=_at(blob, 0.1))
    assert any("UNVERIFIED" in a for a in res["alerts"]), res


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Wiring — where the monitor lives, and what it is NOT downstream of
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_board_sla_op_does_NOT_live_in_the_job_it_watches():
    """The whole point. `_verify_published` only runs when the job runs, and the failure being
    detected is the job NOT RUNNING — a schedule reverted to STOPPED, a code location that failed
    to load, a stalled daemon. A monitor hosted inside its own subject cannot see its subject
    stop."""
    assert "nfl_published_board_freshness_op" not in _PUBLISH_JOB.read_text()
    assert "nfl_published_board_freshness_op" in _SLEEPER_JOB.read_text()


def test_the_board_sla_op_is_INVOKED_by_the_daily_job_not_merely_defined():
    """wired ≠ invoked (NF-C0e). AST over the job function body, so a comment naming the op — or
    the op's own `def` — cannot satisfy this."""
    job_fn = _fn(_SLEEPER_JOB, "sports_nfl_sleeper_injuries_job")
    calls = [n for n in ast.walk(job_fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "nfl_published_board_freshness_op"]
    assert calls, "the daily NFL job never CALLS nfl_published_board_freshness_op"


def test_the_board_sla_op_is_INDEPENDENT_so_a_sleeper_outage_cannot_blind_it():
    """The Sleeper ingest fails loud and RAISES by design (NF-INFRA1). Hanging this monitor off it
    would mean a Sleeper outage blinds the board monitor on exactly the days something is already
    wrong. Two unrelated failures must not share a fate."""
    job_fn = _fn(_SLEEPER_JOB, "sports_nfl_sleeper_injuries_job")
    call = next(n for n in ast.walk(job_fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "nfl_published_board_freshness_op")
    assert not call.args and not call.keywords, (
        "nfl_published_board_freshness_op takes a dependency (e.g. start=...) — it must be an "
        "INDEPENDENT step so an unrelated ingest failure cannot skip it")


def test_the_publish_verification_delegates_to_the_pure_policy():
    """Keeps the guards RED-provable in the fast gate: driving them against a deliberately stale
    or truncated manifest must need no Dagster, no S3 and no box."""
    fn = _fn(_PUBLISH_JOB, "_verify_published")
    assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == "verify_manifest" for n in ast.walk(fn)), (
        "_verify_published must call nfl_board_freshness.verify_manifest")


def test_the_input_refresh_asserts_the_sleeper_feed_it_is_about_to_build_on():
    """AC1 / INC-25. Depth charts and rosters are ordered by a graph edge; the Sleeper capture is a
    different job on a different schedule, ordered only by a 45-minute cron offset — which this
    job's own docstring calls "a courtesy, NOT the ordering guarantee". Assert it landed."""
    fn = _fn(_PUBLISH_JOB, "nfl_board_input_refresh_op")
    src = ast.unparse(fn)
    assert "sports_delta_freshness" in src and "nfl_sleeper_injuries" in src, (
        "the board build does not check that today's Sleeper capture landed before it builds")


def test_the_publish_schedule_still_self_starts():
    """E11.23 — regression guard on the property NF-INFRA1 landed. Read off the NAMED decorator so
    a sibling schedule's identical argument cannot satisfy it (the E11.26 cron-guard lesson)."""
    tree = ast.parse(_SCHEDULES.read_text())
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
              and n.name == "sports_nfl_board_publish_schedule")
    dec = next(d for d in fn.decorator_list if isinstance(d, ast.Call))
    status = next(k for k in dec.keywords if k.arg == "default_status")
    assert ast.unparse(status.value).endswith("RUNNING"), (
        "sports_nfl_board_publish_schedule must self-start — its ON state must not live only in "
        "the Dagster Postgres, which a volume reset silently clears")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The REAL op, not just the pure policy
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _skip_without_manifest():
    """`pipeline/__init__.py` reads the dbt manifest at import (the E11.23 fast-gate rule), so a
    test that imports `pipeline` must SKIP rather than crash at collection when it is absent."""
    if not (_REPO / "dbt" / "target" / "manifest.json").exists():
        pytest.skip("dbt manifest absent — `pipeline` is not importable in the fast gate")


def test_the_REAL_op_pages_on_a_degraded_input_and_still_publishes(tmp_path, monkeypatch):
    """⭐ DRIVE THE REAL LEG, not only the pure policy (INC-39). The pure verdict and the op's
    handling of it are different code, and the ALERT branch is the one whose bug is SILENT: a
    fault there means either a page that never fires, or a raise that freezes the board over a
    late feed — the exact outcome the ratified NF-INJ1 tiering forbids.

    This is not hypothetical caution: writing this suite against the pure function alone left the
    op's success path unexercised, and a `NameError` on it shipped into the working tree until the
    re-anchored NF-FRESH2 guard drove the op and caught it."""
    _skip_without_manifest()
    import importlib

    from dagster import build_op_context

    J = importlib.import_module("pipeline.jobs.sports_nfl_board_publish_job")
    pages: list[tuple] = []
    monkeypatch.setattr(J, "_page", lambda ctx, title, body, **kw: pages.append((title, kw)))
    monkeypatch.setattr(J, "_APP_DIR", tmp_path)
    out = tmp_path / J._STAGING_OUT / "2026"
    out.mkdir(parents=True)

    started = datetime.now(timezone.utc)
    stale = (started - timedelta(hours=500)).isoformat()
    (out / "manifest.json").write_text(json.dumps({
        "generated_at": started.isoformat(),
        "adp_as_of": stale,                       # ← the single degraded input
        "ecr_as_of": started.date().isoformat(),
        "freshness": {"input_vintage": {"depth_chart_as_of": started.isoformat()}},
        "coherence": {"injury_input": {"verdict": "OK", "detail": "fresh"}},
    }))

    # MUST NOT RAISE — a known-stale feed is an honest, bounded degradation; refusing to publish
    # would freeze every other fix riding this cycle (PM, 2026-08-21).
    J._verify_published(build_op_context(), 2026, started)

    assert pages, "a degraded input published silently — nothing paged"
    assert any("adp_as_of" in str(t) or "degraded" in str(t).lower() for t, _ in pages), pages
    keys = {kw.get("dedup_key") for _, kw in pages}
    assert "nfl_board_publish:verify_failed" not in keys, (
        "a degraded input must not occupy the FATAL page's dedup slot (INC-39)")
