"""NF-C3-REREAD — guards for the corrected-band re-read of NF-RECAL1's C3 + NF-D21's floor gate.

WHAT THIS PROTECTS. NF1.9-R proved the veteran panel's `served_p10`/`served_p90` columns carry the
PRE-NF1.9 normal band (~0.50 tier coverage), not the band on the wire (0.845). NF-C3-REREAD re-read
both refusals against the model-path-refit served band: NF-RECAL1's CONSTRAINT_REFUSED does NOT
stand (corrected state POWER_LIMITED at the deflation gate — still nothing ships); NF-D21's DOES
(its gate never read the trapped columns). The things that can silently break:

  1. **The record must agree with its own data.** The verdict flags are re-derived from the JSON's
     own tables — a hand-edited verdict (or a re-run that changes the data without the story) goes
     red here.
  2. **The floor may never move.** Every binding level in the corrected C3 detail must sit AT or
     BELOW the 0.80 floor (`min(floor, coverage_incumbent)` can only lower the bar; E2.1-r / NF1.8).
  3. **The step-0 reproduction is a RAISE, not a log line.** A harness that no longer stops on a
     band mismatch would let a future re-run gate on the wrong band again — the exact trap.
  4. **The round-then-ceil ε-artifact is a measured fact**, pinned functionally: the recorded
     clause fails coverage EQUAL to the incumbent's when 6-dp rounding rounds up; the ε-tolerant
     sensitivity passes it. If either half stops reproducing, the record's harness finding is stale.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import level_recalibration as LR
from quant_sports_intel_models.football.nfl.fantasy import run_nf_c3_reread as RR

_RECORD = (Path(__file__).resolve().parents[2]
           / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
           / "nf_c3_reread.json")


@pytest.fixture(scope="module")
def record() -> dict:
    assert _RECORD.exists(), "the NF-C3-REREAD record is missing"
    return json.loads(_RECORD.read_text())


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1 · the record agrees with its own data
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestRecordInternalConsistency:
    def test_step0_reproduced_the_served_band(self, record):
        s = record["step0_reproduction"]
        assert s["universe_is80"] == pytest.approx(RR._NF19_UNIVERSE_IS80, rel=1e-5)
        assert s["universe_is80_delta_pct"] == pytest.approx(0.0, abs=1e-3)
        assert s["served_tier_coverage_2019_2025"] == pytest.approx(
            RR._NF19R_SERVED_TIER_COV_2019_2025, abs=5e-5)
        assert s["panel_column_tier_coverage_2019_2025"] == pytest.approx(
            RR._NFRECAL1_PANEL_TIER_COV_2019_2025, abs=5e-5)

    def test_nf_recal1_verdict_is_rederivable_from_read1(self, record):
        v = record["verdict"]["nf_recal1"]
        cleared = {r["arm"] for r in record["read1_recorded_arms_corrected_gate"]
                   if r["arm"] != "incumbent (NULL)" and r["holds_out"]
                   and any(float(x) > 0 for x in (r["lam_by_fold"] or {}).values())}
        assert set(v["arms_recorded_lambda_cleared_corrected_c3"]) == cleared
        assert bool(cleared) == (not v["recorded_null_stands"])

    def test_nothing_ships_and_the_reason_is_the_deflation_gate(self, record):
        v = record["verdict"]["nf_recal1"]
        assert v["nothing_ships"] is True
        assert v["read2_ship_gate"]["ship"] is False
        assert v["read2_ship_gate"]["dsr_ok"] is False, \
            "the record's story is that DSR is what refuses the ship — if this flips, the story " \
            "must be re-written, not silently inherited"
        # every constraint clause passes on the corrected read — the refusal is NOT a constraint
        for clause in ("ordering_ok_every_position", "placement_holds_out_every_fold",
                       "coverage_floors_hold"):
            assert v["read2_ship_gate"][clause] is True

    def test_corrected_state_matches_the_classification(self, record):
        v = record["verdict"]["nf_recal1"]
        assert v["recorded_null_stands"] is False
        assert v["corrected_state"] == record["read2_classification"]["state"]

    def test_nf_d21_verdict_is_rederivable_from_its_sweep(self, record):
        d21 = record["nf_d21"]
        lam0 = next(r for r in d21["sweep"]["rows"] if float(r["lambda"]) == 0.0)
        lam05 = next(r for r in d21["sweep"]["rows"] if float(r["lambda"]) == 0.5)
        rb_bind = min(0.80, float(lam0["coverage"]["RB"]))
        rb_ok = float(lam05["coverage"]["RB"]) >= rb_bind - 1e-12
        assert d21["verdict"]["lambda_0_5_ok_under_corrected_structure"] == rb_ok
        assert record["verdict"]["nf_d21"]["recorded_null_stands"] == (not rb_ok)

    def test_scrutiny_anchors_hold_on_the_corrected_band(self, record):
        s = record["metric_scrutiny_served_band"]
        assert s["oracle_is_the_floor"] is True
        assert s["degenerates_lose"] is True
        assert s["over_scale_loses_to_best_real"] is True
        assert s["attribution_signature_read2"]["verdict"] == "level_fix"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2 · the floor never moved
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestFloorNeverMoved:
    def test_every_binding_level_at_or_below_the_floor(self, record):
        binds = []
        for key in ("read1_recorded_arms_corrected_gate", "read2_full_replay"):
            for arm in record[key]:
                for pf in arm["per_fold"].values():
                    for w in (pf.get("coverage_detail") or {}).values():
                        if w.get("binding_level") is not None:
                            binds.append(float(w["binding_level"]))
        assert binds, "no binding levels recorded — the detail table went missing"
        assert max(binds) <= LR.COVERAGE_FLOOR + 1e-9

    def test_d21_binding_level_is_the_bare_floor(self, record):
        for row in record["nf_d21"]["corrected_c3_structure"]:
            for w in row["per_position"].values():
                assert float(w["binding_level"]) <= 0.80 + 1e-9


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3 · the step-0 reproduction RAISES on a wrong band — one ISOLATING fixture per clause (NF-D17:
#     a guard on an AND-composed gate is vacuous unless each fixture satisfies every OTHER clause)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _step0_rows(*, is80: float, tier_cov: float, panel_cov: float) -> pd.DataFrame:
    """A synthetic row frame hitting the three step-0 readings EXACTLY: universe IS80 (constant
    width 100, penalty carried by the tier misses), served tier coverage, panel-column coverage."""
    n, n_tier = 10000, 5000
    tier = np.zeros(n, dtype=bool)
    tier[:n_tier] = True
    n_miss = n_tier - int(round(tier_cov * n_tier))
    width = 100.0
    lo = np.full(n, 10.0)
    hi = lo + width
    y = lo + width / 2.0
    if n_miss:
        d = (is80 - width) * n / (10.0 * n_miss)      # solve mean IS80 == is80 exactly
        y[:n_miss] = hi[:n_miss] + d
    p_lo, p_hi = lo.copy(), hi.copy()
    p_y_out = n_tier - int(round(panel_cov * n_tier))
    p_lo[:p_y_out] = y[:p_y_out] + 1.0                # push the panel band off these outcomes
    p_hi[:p_y_out] = y[:p_y_out] + 2.0
    return pd.DataFrame({
        "year": 2019, "pos": ["WR"] * n, "lo": lo, "hi": hi, "y": y, "point": y,
        "fell_back": False, "panel_lo": p_lo, "panel_hi": p_hi, "tier": tier})


class TestStepZeroIsAGate:
    _OK = dict(is80=RR._NF19_UNIVERSE_IS80, tier_cov=RR._NF19R_SERVED_TIER_COV_2019_2025,
               panel_cov=RR._NFRECAL1_PANEL_TIER_COV_2019_2025)

    def test_the_fixtures_isolate(self):
        """All three clauses satisfied at once — proving each failing fixture below fails for ITS
        clause and no other."""
        proofs = RR.reproduction_proofs(_step0_rows(**self._OK))
        assert proofs["universe_is80_delta_pct"] == pytest.approx(0.0, abs=1e-3)

    def test_raises_on_a_wrong_universe_is80(self):
        with pytest.raises(SystemExit, match="universe IS80"):
            RR.reproduction_proofs(_step0_rows(**{**self._OK, "is80": 200.0}))

    def test_raises_on_a_wrong_served_tier_coverage(self):
        with pytest.raises(SystemExit, match="served tier coverage"):
            RR.reproduction_proofs(_step0_rows(**{**self._OK, "tier_cov": 0.90}))

    def test_raises_on_a_wrong_panel_column_coverage(self):
        with pytest.raises(SystemExit, match="panel-column tier coverage"):
            RR.reproduction_proofs(_step0_rows(**{**self._OK, "panel_cov": 0.90}))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4 · the round-then-ceil ε-artifact, pinned functionally
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestEpsilonBoundaryArtifact:
    """28 of 37 covered → coverage 0.7567567…, which 6-dp rounding lifts to 0.756757, so
    `ceil(round(inc,6)·37) = 29 > 28`: the recorded clause fails an arm whose coverage EQUALS the
    incumbent's own — λ=0 fails against itself — while the ε-tolerant check honours equality."""

    def _population(self):
        n = 37
        y = np.arange(n, dtype=float) + 10.0
        lo = np.where(np.arange(n) < 28, y - 1.0, y + 5.0)   # 28 covered, 9 missed
        hi = lo + 2.0
        pos = np.array(["QB"] * n, dtype=object)
        return y, lo, hi, pos

    def test_recorded_clause_fails_equality_at_the_rounded_boundary(self):
        y, lo, hi, pos = self._population()
        inc = LR.per_position_coverage(y, lo, hi, pos)          # rounded to 6 dp — rounds UP here
        got = LR.coverage_floor_check(y, lo, hi, pos, incumbent_coverage=inc)
        assert got["per_position"]["QB"]["ok"] is False, \
            "the round-then-ceil artifact stopped reproducing — the record's §3 harness finding " \
            "is stale and must be re-measured"

    def test_eps_check_honours_the_equality_boundary(self):
        y, lo, hi, pos = self._population()
        inc = RR._unrounded_cov(y, lo, hi, pos)
        got = RR._cov_check_eps(y, lo, hi, pos, inc)
        assert got["per_position"]["QB"]["ok"] is True
        assert got["per_position"]["QB"]["rows_of_slack"] == 0
