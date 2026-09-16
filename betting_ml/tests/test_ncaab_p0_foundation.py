"""NCAAB-P0 guards — the invariants this vertical's foundation rests on.

Every clause here is RED-proven by `betting_ml/tests/ncaab_p0_red_proof.py`, which deliberately
breaks the source and asserts the guard goes red. A guard that cannot fail is worse than no
guard (NF1.7(a) / INC-38 / INC-39), and several of these were written specifically because the
naive version of them passes on broken source.

FAST-GATE SAFE: no `pipeline` import (E11.23), no network at import or at test time.
"""

from __future__ import annotations

import ast
import json
import pathlib
from datetime import date, datetime, timezone

import pytest

from betting_ml.monitoring import ncaab_freshness as nf
from betting_ml.monitoring import sports_delta_freshness as sdf
from quant_sports_intel_models.basketball.ncaab.ingest import budget, sources as S
from quant_sports_intel_models.basketball.ncaab.ingest import source_audit as sa
from quant_sports_intel_models.basketball.ncaab.ingest import odds_capture as oc

REPO = pathlib.Path(__file__).resolve().parents[2]
NCAAB = REPO / "quant_sports_intel_models" / "basketball" / "ncaab"
PROBE_JSON = NCAAB / "ablation_results" / "ncaab_p0_credit_probe.json"


# ── 1. the fan-out ceiling REFUSES; it does not truncate ────────────────────────────────
class TestFanOutCeilingRefusesRatherThanTruncating:
    def test_a_board_sized_fan_out_raises(self):
        with pytest.raises(budget.FanOutRefused):
            budget.guard_fan_out(budget.PEAK_BOARD_EVENTS)

    def test_a_small_repair_is_allowed_and_priced(self):
        # The ceiling must not be so tight that a legitimate targeted repair is impossible —
        # a guard nobody can satisfy gets deleted, which is the same outcome as no guard.
        cost = budget.guard_fan_out(budget.DEFAULT_FAN_OUT_CEILING)
        assert cost == budget.DEFAULT_FAN_OUT_CEILING * budget.HISTORICAL_PER_EVENT_GAME_LINES

    def test_the_refusal_names_the_cheaper_alternative(self):
        # A refusal that does not say what to do instead gets worked around by raising the
        # ceiling, which defeats it. The message must carry the bulk-call escape hatch.
        with pytest.raises(budget.FanOutRefused) as exc:
            budget.guard_fan_out(50)
        msg = str(exc.value)
        assert "bulk" in msg.lower()
        assert str(budget.HISTORICAL_GAME_LINE_SNAPSHOT) in msg

    def test_it_never_silently_returns_a_truncated_count(self):
        # ⭐ THE CLAUSE THAT MATTERS. A "helpful" implementation that capped n_events at the
        # ceiling and returned would satisfy every test above except this one: it would not
        # raise, and it would report a plausible cost for a partial board.
        for n in (9, 50, budget.PEAK_BOARD_EVENTS, 1000):
            with pytest.raises(budget.FanOutRefused):
                budget.guard_fan_out(n)


# ── 2. the measured constants cannot drift from the witness that established them ───────
class TestBudgetConstantsMatchTheMeasuredWitness:
    """A price sheet is exactly what this vertical must not run on. These constants are only
    trustworthy while they still equal what the probe actually measured, so the artifact is
    the source of truth and the constants are checked against it."""

    @pytest.fixture(scope="class")
    def probe(self):
        assert PROBE_JSON.exists(), f"the credit-probe witness is missing: {PROBE_JSON}"
        return json.loads(PROBE_JSON.read_text())

    def test_the_witness_reconciled_two_independent_instruments(self, probe):
        # If the per-call headers and the free-read bracket disagreed, every constant derived
        # from them is suspect and the vertical should not be budgeting off it at all.
        assert probe["reconciliation"]["state"] == "AGREE", probe["reconciliation"]

    def test_historical_three_market_snapshot_is_thirty(self, probe):
        costs = {c["x_requests_last"] for c in probe["calls"]
                 if c["label"].startswith("historical/depth/") and c["rows"]}
        assert costs == {budget.HISTORICAL_GAME_LINE_SNAPSHOT}, costs

    def test_per_event_fan_out_unit_price_is_measured_not_assumed(self, probe):
        # The 105x argument rests on this number; if it ever changes the ceiling's rationale
        # changes with it.
        assert budget.HISTORICAL_PER_EVENT_GAME_LINES == budget.HISTORICAL_GAME_LINE_SNAPSHOT

    def test_an_empty_board_was_measured_free(self, probe):
        empties = [c for c in probe["calls"]
                   if c["paid"] and c["rows"] == 0 and c["error"] is None]
        assert empties, "the witness recorded no empty paid call — the free-empty claim is unbacked"
        assert all(c["x_requests_last"] == 0 for c in empties)

    def test_the_archive_floor_is_the_one_the_vendor_named(self, probe):
        nexts = {c["next_timestamp"] for c in probe["calls"]
                 if c["label"].startswith("historical/depth/") and c["rows"] == 0}
        assert budget.ARCHIVE_FIRST_SNAPSHOT_GAME_LINES in nexts, nexts


# ── 3. the three-state landing classifier ───────────────────────────────────────────────
class TestLandingStatesAreThreeNotTwo:
    def test_an_in_season_empty_escalates(self):
        msg = S.check_landing(S.SOURCES["schedules"], 0, when=date(2027, 2, 1))
        assert msg and "ZERO ROWS" in msg

    def test_an_off_season_empty_is_quiet(self):
        assert S.check_landing(S.SOURCES["schedules"], 0, when=date(2026, 9, 14)) is None

    def test_a_healthy_landing_is_quiet(self):
        assert S.check_landing(S.SOURCES["schedules"], 6318, when=date(2027, 2, 1)) is None

    def test_absence_is_quiet_pre_season_and_loud_in_season(self):
        # Two-sided on purpose: a classifier that is quiet in BOTH states would pass a
        # one-sided test while being exactly as useless as no classifier at all.
        box = S.SOURCES["team_box"]
        assert S.classify_absence(box, 2027, when=date(2026, 9, 14)) is None
        assert S.classify_absence(box, 2027, when=date(2027, 2, 1)) is not None


# ── 4. the season label's July cut ──────────────────────────────────────────────────────
class TestSeasonLabelling:
    """hoopR labels a season by the year it ENDS. Getting this backwards loads last season's
    file, which EXISTS — so nothing errors and the wrong data lands silently."""

    @pytest.mark.parametrize("d,expected", [
        (date(2026, 6, 30), 2026),   # last day of the old label
        (date(2026, 7, 1), 2027),    # the cut
        (date(2026, 11, 3), 2027),   # first tip
        (date(2027, 4, 5), 2027),    # title game
    ])
    def test_season_for(self, d, expected):
        assert S.season_for(d) == expected


# ── 5. NCAAB does not fork the shared lake layer ────────────────────────────────────────
class TestNcaabDoesNotForkTheSharedLakeLayer:
    def test_the_package_ships_no_local_copy_of_the_shared_modules(self):
        # The two existing copies have already diverged by 216 lines; a third would be a third
        # owner of one logical thing, seeded from whichever copy the author happened to open.
        forbidden = {"s3io.py", "query_lake.py", "backfill.py"}
        present = {p.name for p in (NCAAB / "ingest").glob("*.py")}
        assert not (forbidden & present), f"NCAAB grew its own copy of {forbidden & present}"

    def test_every_lake_import_goes_through_the_single_seam(self):
        # `lake.py` is allowed to name the shared owner; nothing else in the package may, so
        # relocating the shared layer later stays a one-file change in this vertical.
        offenders = []
        for py in (NCAAB / "ingest").rglob("*.py"):
            if py.name == "lake.py":
                continue
            tree = ast.parse(py.read_text())
            for node in ast.walk(tree):
                mod = getattr(node, "module", None) or ""
                names = [a.name for a in getattr(node, "names", [])] if isinstance(
                    node, (ast.Import, ast.ImportFrom)) else []
                if "football" in mod or any("football" in n for n in names):
                    offenders.append(f"{py.name}:{node.lineno}")
        assert not offenders, f"lake layer imported outside lake.py: {offenders}"


# ── 6. a contract is armed WITH its writer, and only with its writer ────────────────────
class TestFreshnessContractsTrackTheirWriters:
    """The rule is ARM WITH THE WRITER — never before (a contract for a table nothing writes is
    a permanent false page, the reason INC-41 rejected a table from its own registry) and never
    after (an unregistered contract is a silent freeze). So this class is TWO-SIDED by design:
    the ingest pair is armed because its writer is confirmed running; the odds pair is NOT,
    because enabling it is the operator's spend decision and it is still off."""

    def test_the_ingest_contracts_are_armed_now_that_their_writer_runs(self):
        # Proven by the schedule's first AUTONOMOUS fire (2026-09-15 14:00Z SUCCESS) — every
        # earlier run was invoked by hand, which says nothing about whether the SCHEDULE ticks.
        live = {c.name for c in sdf.REGISTRY}
        assert set(nf.ARMED_IN_REGISTRY) <= live, (
            f"{set(nf.ARMED_IN_REGISTRY) - live} claim to be armed but are not in REGISTRY")

    def test_the_unarmed_contracts_are_NOT_live_while_their_writer_is_off(self):
        # ⭐ The other half. sports_ncaab_odds_capture_schedule ships STOPPED, so arming its
        # contracts would page CRITICAL every day on a table nobody writes.
        live = {c.name for c in sdf.REGISTRY}
        still_waiting = set(nf.proposed_but_unenabled())
        assert not (live & still_waiting), (
            f"NCAAB contracts {live & still_waiting} are armed, but their writer is not enabled. "
            f"Register them in the SAME change that toggles the schedule ON.")

    def test_the_two_sets_are_disjoint_and_neither_is_empty(self):
        # ⭐ Anti-vacuity, covering BOTH clauses above: each passes trivially over an empty set,
        # which is exactly how this guard would rot into testing nothing.
        armed, waiting = set(nf.ARMED_IN_REGISTRY), set(nf.proposed_but_unenabled())
        assert armed and waiting, f"armed={armed} waiting={waiting}"
        assert not (armed & waiting), "a contract cannot be both armed and awaiting its writer"
        assert len(armed | waiting) >= 4, "the NCAAB contract set has shrunk unexpectedly"

    def test_every_ncaab_contract_carries_active_season_semantics(self):
        # A wall-clock SLA on a seasonal writer pages all summer on a correctly-idle table.
        ncaab = list(nf.DECLARED) + [c for c in sdf.REGISTRY if c.sport == "ncaab"]
        assert len(ncaab) >= 4
        for c in ncaab:
            assert c.active_months, f"{c.name} has no active_months"
            assert c.sport == "ncaab"

    def test_the_box_score_contract_cannot_page_before_the_season_tips(self):
        """🔴 MEASURED BEFORE ARMING. `active_months` restarts the clock at 00:00 Nov 1, but the
        season tips ~Nov 3 and hoopR publishes team_box_YYYY only once games are PLAYED — so a
        bare 36h SLA breaches Nov 3 00:00Z, ~12h BEFORE the first tip, and pages CRITICAL through
        opening week on a healthy pipeline."""
        box = next(c for c in sdf.REGISTRY if c.name == "ncaab_team_box")
        assert box.season_warmup_hours >= 96.0, (
            "the warmup no longer covers window-open -> first tip -> first box file; arming this "
            "contract will page every opening week")
        last = datetime(2026, 9, 14, 18, tzinfo=timezone.utc)   # the pre-season backfill
        reading = sdf.DeltaReading(name=box.name, last_commit=last, rows=100, version=1)
        for day in (1, 3, 5):
            v = sdf.classify(box, reading, now=datetime(2026, 11, day, tzinfo=timezone.utc))
            assert v["severity"] is None, f"Nov {day} pages: {v}"

    def test_BUT_a_feed_that_never_arrives_still_pages(self):
        """⭐ The half that keeps the warmup a GRACE rather than an exemption. A blanket
        in-season pass would silence this forever (the NF1.7(a) vacuous-anchor class)."""
        box = next(c for c in sdf.REGISTRY if c.name == "ncaab_team_box")
        last = datetime(2026, 9, 14, 18, tzinfo=timezone.utc)
        reading = sdf.DeltaReading(name=box.name, last_commit=last, rows=100, version=1)
        v = sdf.classify(box, reading, now=datetime(2026, 11, 20, tzinfo=timezone.utc))
        assert v["verdict"] == "STALE" and v["severity"] == "CRITICAL", v

    def test_the_armed_names_and_the_registry_cannot_drift(self):
        """ARMED_IN_REGISTRY is plain strings (an object import would re-create the cycle), so
        it needs a cross-check or the two modules can disagree silently."""
        live = {c.name for c in sdf.REGISTRY if c.sport == "ncaab"}
        assert live == set(nf.ARMED_IN_REGISTRY), f"registry={live} names={nf.ARMED_IN_REGISTRY}"

    def test_the_freshness_modules_import_in_any_order(self):
        """The armed contracts live in sports_delta_freshness because ncaab_freshness imports
        SportsDeltaContract FROM it. The season window therefore has its own owner module; a
        regression here is an ImportError at collection, so pin it explicitly."""
        import importlib, subprocess, sys
        for first in ("ncaab_freshness", "sports_delta_freshness", "ncaab_season"):
            r = subprocess.run(
                [sys.executable, "-c",
                 f"import betting_ml.monitoring.{first}; "
                 "import betting_ml.monitoring.sports_delta_freshness as s; "
                 "assert any(c.sport=='ncaab' for c in s.REGISTRY)"],
                capture_output=True, text=True, cwd=str(REPO))
            assert r.returncode == 0, f"importing {first} first fails:\n{r.stderr[-600:]}"

    def test_the_season_window_contains_every_in_season_day(self):
        # CONTAINMENT, not equality: the month-granular monitor window must be WIDER than the
        # day-granular ingest window, never narrower, or it blinds the monitor during live play.
        ok, missing = nf.season_month_containment_holds()
        assert ok, f"months live in the ingest layer but absent from SEASON_MONTHS: {missing}"


# ── 6b. the robots parser honours GROUPED User-agent lines, in BOTH directions ──────────
class TestRobotsGroupingIsParsedCorrectly:
    """The terms verdict decided this vertical's architecture (build on the licensed
    redistribution, not on scraping), so the parser that produced it has to be right in both
    directions — and its first cut was wrong in one of them."""

    def test_a_grouped_block_closed_by_one_disallow_blocks_every_agent_in_it(self):
        # ncaa.com lists 20+ AI agents as consecutive User-agent lines closed by a single
        # `Disallow: /`. A per-line parse reads those agents as having NO rules and reports the
        # site as permitted — the exact inversion.
        txt = (
            "User-agent: AI2Bot\n"
            "User-agent: anthropic-ai\n"
            "User-agent: ClaudeBot\n"
            "Disallow: /\n"
        )
        v = sa._robots_verdict(txt, ("anthropic-ai", "ClaudeBot"))
        assert set(v["blanket_disallowed"]) == {"anthropic-ai", "ClaudeBot"}

    def test_a_later_groups_disallow_does_not_leak_onto_an_earlier_allowed_agent(self):
        # ⭐ THE CLAUSE THE FIRST CUT FAILED. Without resetting the group when a User-agent line
        # follows a rule line, the trailing bot's `Disallow: /` was attributed to our agent and
        # the verdict inverted to a FALSE "DISALLOWED". It did not change the real ESPN/NCAA
        # readings (both genuinely disallow us), which is exactly why it could have shipped.
        txt = (
            "User-agent: BadBot\n"
            "Disallow: /\n"
            "\n"
            "User-agent: anthropic-ai\n"
            "Allow: /\n"
            "\n"
            "User-agent: OtherBot\n"
            "Disallow: /\n"
        )
        v = sa._robots_verdict(txt, ("anthropic-ai",))
        assert v["blanket_disallowed"] == [], v

    def test_an_unnamed_agent_reports_that_the_wildcard_governs(self):
        # "not named" and "named and permitted" are different findings and must not collapse.
        txt = "User-agent: *\nDisallow: /admin/\n"
        v = sa._robots_verdict(txt, ("anthropic-ai",))
        assert "not named" in v["verdict"]


# ── 6c. the odds capture MERGES; it does not overwrite, and it cannot collapse history ──
class TestOddsCaptureMergeCannotDestroyHistory:
    """Odds accumulate all season while the lake's ordinary write is a season-grained
    replaceWhere OVERWRITE. Everything here guards the gap between those two facts — and the
    first cut of that merge really did collapse a season into one row."""

    def test_the_merge_key_refuses_a_row_with_no_capture_timestamp(self):
        # ⭐ THE DEFECT A REAL RUN CAUGHT. The raw_json write path produced read-back rows with
        # none of these columns, so every EXISTING row keyed to (None, None, None) and the
        # merge collapsed them into one — silently, on the second capture. Keying a shape it
        # does not understand to a default is the failure; raising is the fix.
        with pytest.raises(RuntimeError, match="capture_timestamp"):
            oc._merge_key({"market_tier": "game_lines", "event_id": "abc"})

    def test_distinct_captures_of_the_same_event_are_distinct_rows(self):
        a = {"capture_timestamp": "2027-01-15T18:00:00+00:00", "market_tier": "game_lines",
             "event_id": "evt1"}
        b = dict(a, capture_timestamp="2027-01-15T18:30:00+00:00")
        assert oc._merge_key(a) != oc._merge_key(b), (
            "two snapshots of one event at different times must survive as two rows, or the "
            "line-movement history the capture exists to build is lost")

    def test_re_merging_the_same_tick_is_idempotent(self):
        rows = [{"capture_timestamp": "2027-01-15T18:00:00+00:00", "market_tier": "game_lines",
                 "event_id": f"evt{i}"} for i in range(5)]
        merged = {oc._merge_key(r): r for r in rows}
        for r in rows:                      # a retry / a manual run beside the cron
            merged[oc._merge_key(r)] = r
        assert len(merged) == 5

    def test_the_write_path_is_typed_not_raw_json(self):
        # The merge must read back the SAME SHAPE it writes. `write_records` wraps everything
        # into a raw_json VARCHAR, which is precisely what broke the key.
        src = pathlib.Path(
            REPO / "quant_sports_intel_models/basketball/ncaab/ingest/odds_capture.py"
        ).read_text()
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        assert "write_dataframe(" in code
        assert "write_records(" not in code, (
            "odds_capture must not use the raw_json write path — see ODDS_COLUMNS")

    def test_an_unreadable_existing_partition_refuses_rather_than_merging_into_nothing(self):
        # If an unreadable table returned [], the merge would write only the new capture and
        # the replaceWhere would delete a season of history — the same catastrophe by the
        # error path instead of the happy one.
        src = pathlib.Path(
            REPO / "quant_sports_intel_models/basketball/ncaab/ingest/odds_capture.py"
        ).read_text()
        assert "REFUSING the merge" in src

    def test_futures_capture_is_once_a_day_not_once_a_tick(self):
        # 48 futures calls a day for a board that moves slowly is 48x the price for no extra
        # information; and the decision is a pure function of the tick, so no second cron.
        fires = [oc.should_capture_futures(datetime(2027, 1, 15, h, m, tzinfo=timezone.utc))
                 for h in range(24) for m in (0, 30)]
        assert sum(fires) == 1, f"expected exactly one futures tick a day, got {sum(fires)}"


# ── 6b. a current-season-only upstream must not page daily ──────────────────────────────
class TestTheCrosswalkAbsenceIsNotAnEscalation:
    """NCAAB-P0 runtime gate. MEASURED 2026-09-14: hoopR publishes the team crosswalk for
    exactly ONE season at a time — only `2026` existed; 2024, 2025 AND 2027 were all 404.

    So for that source a 404 carries no information about health, and escalating on it was
    harmful in two measured ways: a historical backfill escalated on 4 of 5 seasons and exited
    1 on a completely healthy run, and from the season's first tip the DAILY job would have
    raised every day until hoopR rolled the file forward — paging CRITICAL through
    `run_failure_alert_sensor` on a benign upstream lag, for weeks, right when the season starts.
    """

    def test_the_crosswalk_is_declared_current_season_only(self):
        assert S.SOURCES["team_crosswalk"].current_season_only is True

    @pytest.mark.parametrize("season,when,label", [
        (2027, date(2026, 11, 3), "at first tip — the daily-page case"),
        (2027, date(2027, 2, 1), "mid-season"),
        (2022, date(2026, 9, 14), "a historical backfill"),
    ])
    def test_a_404_never_escalates_for_it(self, season, when, label):
        assert S.classify_absence(S.SOURCES["team_crosswalk"], season, when=when) is None, label

    @pytest.mark.parametrize("name", ["schedules", "team_box"])
    def test_BUT_an_ordinary_source_still_escalates_in_season(self, name):
        """⭐ THE LOAD-BEARING HALF. A one-sided test would pass just as happily on a
        `classify_absence` that had been blanket-disabled, which is the NF1.7(a) vacuous-anchor
        class — the exemption must be scoped to the sources that earned it."""
        msg = S.classify_absence(S.SOURCES[name], 2027, when=date(2026, 11, 3))
        assert msg is not None and "ABSENT" in msg

    def test_only_the_crosswalk_carries_the_exemption(self):
        """Pin the registry: a future source must not pick this up by copy-paste."""
        exempt = {n for n, spec in S.SOURCES.items() if spec.current_season_only}
        assert exempt == {"team_crosswalk"}, f"unexpected exemption(s): {exempt}"

    def test_the_crosswalk_has_NO_freshness_contract_and_that_is_deliberate(self):
        """The obvious follow-on ("move the watching to a freshness SLA") is wrong, and INC-45
        already paid for it: an SLA on a deliberately-static artifact pages on a healthy file.
        Between hoopR's rolls NOTHING writes this table, legitimately, for weeks. The reasoning
        is recorded in ncaab_freshness.py so the gap is not read as an oversight."""
        assert "ncaab_team_crosswalk" not in {c.name for c in nf.DECLARED}
        src = (REPO / "betting_ml/monitoring/ncaab_freshness.py").read_text()
        assert "HAS NO CONTRACT HERE, AND THAT IS A DECISION" in src


# ── 6c. both NCAAB jobs are BOUNDED and cannot stack ────────────────────────────────────
class TestTheNcaabJobsAreBoundedAndSerialised:
    """🔴 BOTH TIMEOUT CONSTANTS WERE DECLARED AND NEVER APPLIED. `NCAAB_INGEST_TIMEOUT_SECONDS`
    and `NCAAB_ODDS_TIMEOUT_SECONDS` each appeared EXACTLY ONCE in the whole repo — at their own
    definition — so both ops ran unbounded on a Dagster worker (the INC-32 class: an un-timed-out
    wait wedges the worker, and the sensor daemon behind it). The capture job additionally had no
    `concurrency_group`, and `services/dagster/dagster.yaml` caps concurrency per group value, so
    a job without one opts out of the cap entirely — at 32 fires a day on a 2-vCPU box that is
    the stacking shape E11.26 found in `intraday_schedule_job`.

    ⚠️ ASSERTED VIA AST, NOT A TEXT SCAN, and that is load-bearing here: the explanatory comments
    above each decorator NAME both tag keys, so a substring guard would pass with the tags
    deleted (the INC-38 prose-cannot-satisfy rule).
    """

    JOBS = {
        "pipeline/jobs/sports_ncaab_ingest_job.py": ("sports_ncaab_ingest_job",
                                                     "NCAAB_INGEST_TIMEOUT_SECONDS"),
        "pipeline/jobs/sports_ncaab_odds_capture_job.py": ("sports_ncaab_odds_capture_job",
                                                           "NCAAB_ODDS_TIMEOUT_SECONDS"),
    }

    @staticmethod
    def _job_tags(path: str, func_name: str) -> dict:
        """The `tags=` mapping on the @job decorator of `func_name`, as {key: source-text}."""
        tree = ast.parse((REPO / path).read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name != func_name:
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                for kw in dec.keywords:
                    if kw.arg == "tags" and isinstance(kw.value, ast.Dict):
                        return {k.value: ast.unparse(v)
                                for k, v in zip(kw.value.keys, kw.value.values)
                                if isinstance(k, ast.Constant)}
        return {}

    @pytest.mark.parametrize("path", list(JOBS))
    def test_the_job_applies_its_declared_timeout(self, path):
        func, const = self.JOBS[path]
        tags = self._job_tags(path, func)
        assert tags, f"{func} has no tags= on its @job decorator"
        assert "dagster/max_runtime" in tags, (
            f"{func} runs UNBOUNDED on a Dagster worker. A run tag bounds every wait at once — "
            f"subprocess, HTTP, retry backoff and in-process work — without enumerating them.")
        assert const in tags["dagster/max_runtime"], (
            f"{func}'s max_runtime does not use {const}; a second literal is a second owner of "
            f"the budget, and the constant would go back to being declared-and-never-applied.")

    @pytest.mark.parametrize("path", list(JOBS))
    def test_the_job_declares_a_concurrency_group(self, path):
        func, _ = self.JOBS[path]
        tags = self._job_tags(path, func)
        assert "concurrency_group" in tags, (
            f"{func} has no concurrency_group, so dagster.yaml's per-group cap does not apply "
            f"and its ticks can STACK on a 2-vCPU box (E11.26 / INC-32).")

    def test_the_two_jobs_do_not_share_a_group(self):
        """A shared value would make the daily ingest and the 30-minute capture queue behind
        each other for no reason — and a stuck one would mute the other."""
        groups = {self._job_tags(p, f)["concurrency_group"] for p, (f, _) in self.JOBS.items()}
        assert len(groups) == len(self.JOBS), f"jobs share a concurrency_group: {groups}"


# ── 7. the paid feeds cannot run by accident ────────────────────────────────────────────
#
# 🔴 THE FIRST VERSION OF THIS CLASS COULD NOT FAIL, and it let a real defect ship. It asserted
# `all(not SOURCES[n].on_demand for n in DEFAULT_SOURCES)` while DEFAULT_SOURCES was DEFINED as
# "every source that is not on_demand" — the definition restated back to itself, true by
# construction (the NF-C0e "read the value back under the key the code wrote" class). Meanwhile
# the two LIVE odds feeds are paid but NOT on_demand, so they sat in the default set and
# `sports_ncaab_ingest_job` — RUNNING, daily, calling run_ingest with no source names — was about
# to bill credits on a schedule nobody enabled AND season-OVERWRITE the capture's accumulating
# tables.
#
# So these clauses deliberately do NOT key on the flag the definition uses:
#   • an explicit NAME list, which no flag change can satisfy;
#   • the REFUSAL's behaviour, exercised rather than inspected;
#   • the two writers' table sets being disjoint, by name.
class TestPaidFeedsAreOptIn:
    #: Written out, not derived. A derived expectation would move with the bug.
    FREE_SOURCE_NAMES = {"schedules", "team_box", "team_crosswalk"}
    PAID_SOURCE_NAMES = {"odds_futures", "odds_game_lines", "odds_historical"}

    def test_the_registry_is_fully_partitioned_into_free_and_paid(self):
        # Anti-vacuity FIRST: if a rename empties either side, every clause below says nothing.
        assert self.FREE_SOURCE_NAMES | self.PAID_SOURCE_NAMES == set(S.SOURCES), (
            "the free/paid name lists no longer partition the registry — a source was added or "
            f"renamed. registry={sorted(S.SOURCES)}")

    def test_a_default_run_executes_exactly_the_free_sources(self):
        # The load-bearing clause. Keyed on NAMES, so flipping `paid`/`on_demand` cannot satisfy it.
        assert set(S.DEFAULT_SOURCES) == self.FREE_SOURCE_NAMES, (
            "a plain run_ingest() would execute something other than the free hoopR feeds. "
            "sports_ncaab_ingest_job ships RUNNING and calls run_ingest with no source names, so "
            f"anything here bills or writes on a schedule nobody enabled. default={S.DEFAULT_SOURCES}")

    def test_no_paid_source_can_reach_a_default_run(self):
        assert not (set(S.DEFAULT_SOURCES) & self.PAID_SOURCE_NAMES)

    def test_the_historical_feed_is_on_demand(self):
        assert S.SOURCES["odds_historical"].on_demand is True

    @pytest.mark.parametrize("name", ["odds_futures", "odds_game_lines"])
    def test_run_ingest_REFUSES_a_capture_owned_table_even_when_named(self, name):
        """Behavioural, not definitional: the default set is only half the protection.

        `--sources odds_game_lines` would otherwise take the run_ingest write path, which is a
        season `replaceWhere` OVERWRITE onto a table the capture ACCUMULATES into — replacing a
        whole season of snapshots with one board, silently."""
        from quant_sports_intel_models.basketball.ncaab.ingest.handler import run_ingest

        with pytest.raises(S.IngestRefusal) as exc:
            run_ingest(seasons=[2027], source_names=[name])
        assert "run_capture" in str(exc.value), "the refusal must name the correct writer"

    def test_the_two_writers_own_disjoint_tables(self):
        """One writer per table. An overlap does not conflict — it silently overwrites."""
        assert not (set(S.DEFAULT_SOURCES) & set(S.CAPTURE_OWNED_SOURCES))
        assert S.CAPTURE_OWNED_SOURCES == {"odds_futures", "odds_game_lines"}

    def test_the_ingest_op_does_not_narrow_the_set_itself(self):
        """The protection must live in the REGISTRY, not in one caller.

        If the op passed its own hand-written source list, the registry could stay wrong and every
        other caller (the CLI, a future job, a backfill) would inherit the defect."""
        src = (REPO / "pipeline/jobs/sports_ncaab_ingest_job.py").read_text()
        assert "run_ingest(seasons=[season])" in src, (
            "the ingest op now names its own sources — move the constraint into DEFAULT_SOURCES "
            "so every caller inherits it, rather than fixing this one call site")
