"""Guards for NF-B3 — the joint level+band selection under the corrected C3 (13 folds).

Four families, each red-provable (a guard that cannot FAIL is worse than none — INC-38/INC-39):
  1. THE C3 EQUALITY-BOUNDARY FIX (the NF-C3-REREAD harness finding, canonical in B3): an arm whose
     coverage EQUALS the incumbent's — λ=0 above all — must be ADMISSIBLE under
     `equality_exact=True` + an UNROUNDED incumbent, must still be REFUSED one row below the
     boundary, and the LEGACY default must stay byte-stable (the recorded NF-RECAL1 / NF-C3-REREAD
     reproductions depend on the artifact).
     ⭐ Each clause has its own ISOLATING fixture (NF-D17: a fixture that trips a different clause
     proves nothing about the one it names).
  2. STRUCTURAL C2 INACTIVITY: a rookie-less board YEAR-GATED into `structural_c2_inactive` is
     vacuously admissible + flagged inactive (NF-D20 (g⁗)); the SAME board outside the set keeps the
     refusal (unevaluable is never a pass, NF1.7 (a)); and `load_boards_b3` RAISES on a rookie-less
     board for any substrate-era year (≥ 2016).
  3. THE B3 PRE-REGISTRATION PINS: 13 folds, the 11-arm declared field, the exact-C3 flag, the
     knn_norm k300 band, and the inherited deflation gates — so a drift in any of them fails a test
     rather than silently changing what "NF-B3" means.
  4. WIRING (AST, not grep — prose cannot satisfy it, INC-38): every `score_arm` /
     `build_fold_evidence` / `anchor_constraint_state` call in the runner carries `cov_exact=True`,
     every `fold_fits` call carries `cov_rounding=None`, and the must-lose magnitude anchors
     (`over_scale`, `wide_band`) are in the scored anchor set.
"""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import level_recalibration as LR
from quant_sports_intel_models.football.nfl.fantasy import run_nf_b3_joint as B3
from quant_sports_intel_models.football.nfl.fantasy import run_nf_recal1_level as R1

_RUNNER = Path(B3.__file__)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1 · The C3 equality-boundary fix
# ══════════════════════════════════════════════════════════════════════════════════════════════
# The isolating fixture: ONE position, n = 7, the incumbent band covers 5 rows → the incumbent's own
# coverage is 5/7 = 0.714285714…, which 6-dp rounding lifts to 0.714286 → ceil(0.714286·7) = 6 > 5.
# Only the boundary clause can decide this fixture: C1/C2 are not part of `coverage_floor_check`,
# every row is finite, and the single position keeps the per-position loop trivial.
def _boundary_fixture():
    n = 7
    y = np.arange(n, dtype=float) * 10.0 + 5.0          # 5, 15, …, 65
    lo = np.zeros(n)
    hi = np.full(n, 100.0)
    lo[5], hi[5] = 90.0, 99.0                            # rows 5, 6 fall OUTSIDE the band
    lo[6], hi[6] = 90.0, 99.0
    pos = np.array(["RB"] * n, dtype=object)
    return y, lo, hi, pos


def test_unrounded_incumbent_is_available_and_the_default_still_rounds():
    y, lo, hi, pos = _boundary_fixture()
    exact = LR.per_position_coverage(y, lo, hi, pos, rounding=None)["RB"]
    legacy = LR.per_position_coverage(y, lo, hi, pos)["RB"]
    assert exact == pytest.approx(5.0 / 7.0, abs=0), "rounding=None must return the exact coverage"
    assert legacy == round(5.0 / 7.0, 6) and legacy > 5.0 / 7.0, \
        "the 6-dp default must round UP here — that asymmetry is the artifact the fix removes"


def test_lambda_zero_is_admissible_at_the_equality_boundary_under_the_exact_clause():
    """The headline guard: coverage EQUAL to the incumbent's (λ=0 IS the incumbent) passes."""
    y, lo, hi, pos = _boundary_fixture()
    inc = LR.per_position_coverage(y, lo, hi, pos, rounding=None)
    out = LR.coverage_floor_check(y, lo, hi, pos, incumbent_coverage=inc, equality_exact=True)
    assert out["ok"], f"λ=0 must be admissible at the equality boundary: {out['breaches']}"
    assert out["per_position"]["RB"]["rows_of_slack"] == 0, \
        "the boundary case must sit EXACTLY on the requirement, not above it"


def test_the_legacy_clause_fails_the_same_fixture_by_one_row():
    """The red-proof of the fix: remove `equality_exact` and the identical fixture is refused —
    i.e. this test FAILS if someone deletes the eps from the exact branch, and the next one FAILS
    if someone silently changes the legacy default the recorded reproductions depend on."""
    y, lo, hi, pos = _boundary_fixture()
    inc_rounded = LR.per_position_coverage(y, lo, hi, pos)          # the legacy 6-dp incumbent
    out = LR.coverage_floor_check(y, lo, hi, pos, incumbent_coverage=inc_rounded)
    assert not out["ok"] and out["per_position"]["RB"]["rows_of_slack"] == -1, \
        "the legacy round-then-ceil artifact must reproduce (recorded runs depend on it)"


def _float_overshoot_fixture():
    """The SECOND artifact channel, isolated: at n = 25 with 7 covered rows the UNROUNDED incumbent
    is the double nearest 7/25, and `(7/25)·25` lands a float-epsilon ABOVE 7 → `ceil` demands 8
    even with rounding removed. ONLY the −1e-9 eps decides this fixture (the n=7 fixture above is
    decided by the un-rounding alone — two channels, two isolating fixtures, NF-D17)."""
    n = 25
    y = np.arange(n, dtype=float) * 10.0 + 5.0
    lo = np.zeros(n)
    hi = np.full(n, 300.0)
    for i in range(7, n):                                # rows 7..24 fall OUTSIDE: 7 covered
        lo[i], hi[i] = 290.0, 299.0
    pos = np.array(["RB"] * n, dtype=object)
    return y, lo, hi, pos


def test_the_eps_alone_decides_the_float_overshoot_channel():
    """Red-proof target for the eps itself: delete the 1e-9 and this fixture is refused at the
    equality boundary even with the UNROUNDED incumbent, because `bind·n` overshoots the integer
    in floating point."""
    y, lo, hi, pos = _float_overshoot_fixture()
    inc = LR.per_position_coverage(y, lo, hi, pos, rounding=None)
    assert float(inc["RB"]) * 25 > 7.0, "the fixture must overshoot in floats or it isolates nothing"
    out = LR.coverage_floor_check(y, lo, hi, pos, incumbent_coverage=inc, equality_exact=True)
    assert out["ok"] and out["per_position"]["RB"]["rows_of_slack"] == 0, \
        f"λ=0 must be admissible at the float-overshoot boundary: {out['breaches']}"


def test_the_exact_clause_still_refuses_one_row_below_the_boundary():
    """The fix must not loosen PAST the boundary: coverage one row BELOW the incumbent's refuses."""
    y, lo, hi, pos = _boundary_fixture()
    inc = LR.per_position_coverage(y, lo, hi, pos, rounding=None)
    lo2 = lo.copy(); hi2 = hi.copy()
    lo2[4], hi2[4] = 90.0, 99.0                          # a third row falls out: 4/7 < 5/7
    out = LR.coverage_floor_check(y, lo2, hi2, pos, incumbent_coverage=inc, equality_exact=True)
    assert not out["ok"] and out["per_position"]["RB"]["rows_of_slack"] == -1, \
        "one covered row below the incumbent must still breach — the boundary is exact, not loose"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2 · Structural C2 inactivity
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _mini_fold_and_board(year: int):
    n = 30
    rng = np.random.default_rng(7)
    point = np.linspace(50, 250, n)
    te = pd.DataFrame({
        "point": point,
        "served_p10": point * 0.2,                        # wide band: C3 passes at every λ here
        "served_p90": point * 3.0,
        "position": ["RB"] * n,
        "proj_games": np.full(n, 15.0),
        "real_fp_ppr": point * (1.0 + rng.normal(0, 0.05, n)),
        "target_season": year, "player_id": [f"p{i}" for i in range(n)],
    })
    fold = {"year": year, "train": te, "test": te, "test_universe": te}
    fits = {year: {("global_const", LR.PRIMARY_SPACE): {"k": 1.1},
                   "_inc_coverage": LR.per_position_coverage(
                       te["real_fp_ppr"], te["served_p10"], te["served_p90"], te["position"],
                       rounding=None)}}
    board = pd.DataFrame({"player_name": [f"v{i}" for i in range(n)], "position": ["RB"] * n,
                          "proj_fp_ppr": point, "proj_games": np.full(n, 15.0),
                          "is_rookie": [False] * n})
    return fold, fits, board


def test_structural_c2_inactive_year_is_vacuously_admissible_and_flagged():
    fold, fits, board = _mini_fold_and_board(2015)
    ev = R1.build_fold_evidence([fold], fits, {2015: board}, forms=("global_const",),
                                cov_exact=True, structural_c2_inactive=(2015,))
    per = ev["global_const"][2015]
    assert per["c2_inactive_structural"] is True
    assert all(v["c2_placement_ok"] for v in per["per_lambda"].values())
    assert all(v["c2_inactive_structural"] for v in per["per_lambda"].values()), \
        "every λ on a structural fold must be FLAGGED inactive so it can never be read as a pass"
    assert per["constraint_can_act"] is False, "the activity count must read the fold INACTIVE"
    assert len(per["admissible"]) > 0, "C1/C3 pass here, so admissibility must be driven by them"


def test_the_same_rookieless_board_outside_the_structural_set_refuses_every_lambda():
    """The red-proof: without the year gate the vacuous branch must NOT engage — an unevaluable
    C2 stays a refusal (NF1.7 (a)), so a silent widening of the structural set cannot hide."""
    fold, fits, board = _mini_fold_and_board(2015)
    ev = R1.build_fold_evidence([fold], fits, {2015: board}, forms=("global_const",),
                                cov_exact=True, structural_c2_inactive=())
    per = ev["global_const"][2015]
    assert not any(v["c2_placement_ok"] for v in per["per_lambda"].values())
    assert per["admissible"] == ()


def test_load_boards_b3_raises_on_a_rookieless_substrate_era_board(tmp_path, monkeypatch):
    monkeypatch.setattr(R1, "_ART", tmp_path)
    _, _, board = _mini_fold_and_board(2019)
    board.assign(base_season=2018).to_parquet(tmp_path / "nfl_fantasy_season_projections_2019.parquet")
    with pytest.raises(SystemExit, match="BROKEN rebuild"):
        B3.load_boards_b3((2019,))


def test_load_boards_b3_allows_and_returns_the_pre_substrate_rookieless_years(tmp_path, monkeypatch):
    monkeypatch.setattr(R1, "_ART", tmp_path)
    _, _, board = _mini_fold_and_board(2015)
    board.assign(base_season=2014).to_parquet(tmp_path / "nfl_fantasy_season_projections_2015.parquet")
    boards, structural = B3.load_boards_b3((2015,))
    assert structural == [2015] and 2015 in boards


def test_load_boards_b3_stops_on_a_missing_board_with_the_operator_precursor():
    with pytest.raises(SystemExit, match="backtest-from 2013"):
        B3.load_boards_b3((1999,))


def test_load_boards_b3_raises_on_a_non_walk_forward_board(tmp_path, monkeypatch):
    monkeypatch.setattr(R1, "_ART", tmp_path)
    _, _, board = _mini_fold_and_board(2015)
    board.assign(base_season=2015).to_parquet(tmp_path / "nfl_fantasy_season_projections_2015.parquet")
    with pytest.raises(SystemExit, match="not walk-forward"):
        B3.load_boards_b3((2015,))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3 · The B3 pre-registration pins
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_b3_registration_pins():
    reg = B3.B3_REGISTRATION
    assert reg["fold_seasons"] == tuple(range(2013, 2026)) and len(reg["fold_seasons"]) == 13
    assert reg["c3_equality_exact"] is True
    assert reg["rookie_substrate_start"] == 2016
    assert reg["band"]["form"] == "knn_norm" and reg["band"]["k"] == 300
    assert "served_p10" in reg["band"]["forbidden_source"]
    assert reg["train_panel_start"] == 2007


def test_the_declared_field_is_eleven_arms_and_the_gates_are_inherited():
    assert len(LR.candidate_configs()) == 11
    assert LR.DSR_MIN == 0.95 and LR.PBO_MAX == 0.2 and LR.ALPHA == 0.10
    assert LR.COVERAGE_FLOOR == 0.80


def test_the_recorded_legacy_default_did_not_drift():
    """`coverage_floor_check`'s DEFAULT must remain the legacy clause — the recorded NF-RECAL1 and
    NF-C3-REREAD artifacts (whose reproduction gates re-run this code) depend on it."""
    import inspect
    sig = inspect.signature(LR.coverage_floor_check)
    assert sig.parameters["equality_exact"].default is False
    assert inspect.signature(LR.per_position_coverage).parameters["rounding"].default == 6


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4 · Wiring — AST, so a comment or docstring cannot satisfy it (INC-38)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            got = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if got == name:
                out.append(node)
    return out


def _kw(call: ast.Call, key: str):
    for k in call.keywords:
        if k.arg == key:
            return k.value
    return None


def test_every_scoring_call_in_the_runner_uses_the_exact_c3_boundary():
    tree = ast.parse(_RUNNER.read_text())
    for fn in ("score_arm", "build_fold_evidence", "anchor_constraint_state"):
        calls = _calls(tree, fn)
        assert calls, f"the runner no longer calls {fn} — the wiring guard is stale, fix it"
        for c in calls:
            v = _kw(c, "cov_exact")
            assert isinstance(v, ast.Constant) and v.value is True, \
                f"a {fn} call in the runner lacks cov_exact=True — its C3 would silently use the " \
                "legacy boundary"


def test_fold_fits_uses_the_unrounded_incumbent():
    tree = ast.parse(_RUNNER.read_text())
    calls = _calls(tree, "fold_fits")
    assert calls, "the runner no longer calls fold_fits — the wiring guard is stale, fix it"
    for c in calls:
        v = _kw(c, "cov_rounding")
        assert isinstance(v, ast.Constant) and v.value is None, \
            "fold_fits must be called with cov_rounding=None — the exact boundary needs the " \
            "UNROUNDED incumbent or the fix is only half-applied"


def test_the_must_lose_magnitude_anchors_stay_in_the_scored_set():
    """C3 cannot police magnitude from above on the corrected band (NF-C3-REREAD) — the metric
    must, so over_scale and wide_band must be SCORED every run, not merely mentioned."""
    src = _RUNNER.read_text()
    tree = ast.parse(src)
    tuples = [n for n in ast.walk(tree) if isinstance(n, ast.Tuple)]
    flat = {e.value for t in tuples for e in t.elts if isinstance(e, ast.Constant)}
    assert {"over_scale", "wide_band", "zero_project", "pos_median",
            "oracle_perplayer"} <= flat, \
        "an anchor fell out of the runner's scored anchor tags"


def test_structural_years_are_threaded_into_both_evidence_and_anchor_constraints():
    tree = ast.parse(_RUNNER.read_text())
    for fn in ("build_fold_evidence", "anchor_constraint_state"):
        for c in _calls(tree, fn):
            assert _kw(c, "structural_c2_inactive") is not None, \
                f"a {fn} call drops structural_c2_inactive — pre-2016 folds would refuse " \
                "everything on C2 and the gate would manufacture its own null (NF1.7 (a))"
