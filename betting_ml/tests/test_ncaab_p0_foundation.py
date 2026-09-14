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
from datetime import date

import pytest

from betting_ml.monitoring import ncaab_freshness as nf
from betting_ml.monitoring import sports_delta_freshness as sdf
from quant_sports_intel_models.basketball.ncaab.ingest import budget, sources as S

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


# ── 6. freshness contracts are declared but NOT armed ───────────────────────────────────
class TestFreshnessContractsAreDeclaredNotArmed:
    def test_no_ncaab_contract_is_live_while_no_writer_exists(self):
        # A contract for a table nothing writes is a permanent false page from the first
        # deploy — the reason INC-41 rejected a table from its own registry.
        live = {c.name for c in sdf.REGISTRY}
        declared = set(nf.proposed_but_unenabled())
        assert not (live & declared), (
            f"NCAAB contracts {live & declared} are armed, but no NCAAB writer is scheduled. "
            f"Register them in the SAME change that enables their schedule.")

    def test_the_declared_contracts_are_not_empty(self):
        # ⭐ Anti-vacuity. The clause above passes trivially if DECLARED is empty, which is
        # exactly how this guard would rot into testing nothing.
        assert len(nf.DECLARED) >= 4

    def test_every_declared_contract_carries_active_season_semantics(self):
        # A wall-clock SLA on a seasonal writer pages all summer on a correctly-idle table.
        for c in nf.DECLARED:
            assert c.active_months, f"{c.name} has no active_months"
            assert c.sport == "ncaab"

    def test_the_season_window_contains_every_in_season_day(self):
        # CONTAINMENT, not equality: the month-granular monitor window must be WIDER than the
        # day-granular ingest window, never narrower, or it blinds the monitor during live play.
        ok, missing = nf.season_month_containment_holds()
        assert ok, f"months live in the ingest layer but absent from SEASON_MONTHS: {missing}"


# ── 7. the paid feeds cannot run by accident ────────────────────────────────────────────
class TestPaidFeedsAreOptIn:
    def test_the_historical_feed_is_on_demand(self):
        assert S.SOURCES["odds_historical"].on_demand is True

    def test_a_default_run_names_no_on_demand_source(self):
        assert all(not S.SOURCES[n].on_demand for n in S.DEFAULT_SOURCES)

    def test_the_default_set_is_not_empty(self):
        # Anti-vacuity again: the clause above is trivially true of an empty default set.
        assert len(S.DEFAULT_SOURCES) >= 4
