"""NF-TR2b — guards for the whole-board CROSS-POSITION placement read (the NF-D16 class).

Every clause here is written to be INDEPENDENTLY RED-PROVABLE: `nf_tr2b_placement_red_proof.py`
deletes/inverts one behaviour at a time and asserts the matching clause goes red. Two disciplines
this repo has been burned by are enforced deliberately:

  ▸ a gate is only meaningful if it can FAIL — so every gate clause is TWO-SIDED (a fixture that
    passes AND a fixture that must trip it), never "the served board happens to be fine";
  ▸ an UNEVALUABLE gate is never scored healthy (NF1.7 (a)).
"""
from __future__ import annotations

import ast
import pathlib

import pandas as pd
import pytest

from quant_sports_intel_models.fantasy_engine.vor import build_board
from quant_sports_intel_models.football.nfl.fantasy import nf_tr2b_placement as PL
from quant_sports_intel_models.football.nfl.fantasy import veteran_level_policy as VLP
from quant_sports_intel_models.football.nfl.fantasy.league_presets import NFL_PROFILE, get_preset

_MODULE = pathlib.Path(PL.__file__)
K = {"QB": 0.93, "RB": 1.25, "WR": 1.10, "TE": 1.11}


def _board(rows) -> pd.DataFrame:
    """rows: (id, pos, pts, rookie) -> a served-board-shaped frame."""
    return pd.DataFrame([{"id": i, "pos": p, "pts": v, "rookie": r,
                          "name": i, "adp": None} for i, p, v, r in rows])


def _built(frame: pd.DataFrame, preset="half_ppr", n_teams=12) -> dict:
    return PL.paired_boards(frame, K, get_preset(preset, n_teams=n_teams), NFL_PROFILE)


# ── the incumbent reconstruction ────────────────────────────────────────────────────────────────
def test_reconstruction_divides_only_veterans_at_recalibrated_positions():
    """Exact by linearity — and LEG-SCOPED. A rookie or a K/DST row must come back untouched."""
    b = _board([("v_rb", "RB", 125.0, False), ("r_rb", "RB", 125.0, True),
                ("v_k", "K", 100.0, False), ("v_qb", "QB", 186.0, False)])
    got = PL.reconstruct_incumbent_points(b, K)
    assert got.iloc[0] == pytest.approx(125.0 / 1.25), "veteran RB must be divided by k_RB"
    assert got.iloc[1] == pytest.approx(125.0), "ROOKIE must be untouched (NF-D21 holds that leg)"
    assert got.iloc[2] == pytest.approx(100.0), "K is outside RECALIBRATED_POSITIONS"
    assert got.iloc[3] == pytest.approx(186.0 / 0.93), "veteran QB must be divided by k_QB"


def test_reconstruction_is_the_exact_inverse_so_a_round_trip_returns_the_original():
    b = _board([("a", "RB", 200.0, False), ("b", "WR", 150.0, False), ("c", "TE", 90.0, True)])
    inc = PL.reconstruct_incumbent_points(b, K)
    back = inc * b["pos"].map(lambda p: K[p]).where(~b["rookie"].astype(bool), 1.0)
    pd.testing.assert_series_equal(back, pd.to_numeric(b["pts"]), check_names=False)


# ── G1: within-position order, PER LEG ──────────────────────────────────────────────────────────
def test_g1_passes_when_each_leg_keeps_its_own_order_and_reports_the_cross_leg_break():
    """The real claim. A positive constant is monotone, so each LEG holds; the rookie/veteran
    boundary is allowed to move and is REPORTED rather than silently passed or failed."""
    frame = _board([("v1", "RB", 300.0, False), ("v2", "RB", 200.0, False),
                    ("r1", "RB", 260.0, True), ("w1", "WR", 180.0, False)])
    p = _built(frame)
    g = PL.within_position_order_preserved(p["board_inc"], p["board_rec"])
    assert g["pass"] is True, "each leg must keep its own order"
    assert g["positions"]["RB"]["veterans"]["order_identical"] is True
    assert g["positions"]["RB"]["rookies"]["order_identical"] is True
    # the RB leg boundary DOES move here (rookie 260 sits between veterans 200*1.25 and 300*1.25)
    assert "RB" in g["cross_leg_reordered_positions"], (
        "the cross-leg reordering must be REPORTED, not hidden")


def test_g1_goes_red_on_a_non_monotone_transform():
    """TWO-SIDED. If the correction were NOT order-preserving, the veterans leg must fail."""
    frame = _board([("v1", "RB", 300.0, False), ("v2", "RB", 200.0, False)])
    cfg = get_preset("half_ppr", n_teams=12)
    base = pd.DataFrame({"position": frame["pos"], "id": frame["id"],
                         "name": frame["id"], "rookie": frame["rookie"], "adp": None})
    inc = base.copy(); inc["league_points"] = [300.0, 200.0]
    bad = base.copy(); bad["league_points"] = [200.0, 300.0]      # an order-INVERTING map
    g = PL.within_position_order_preserved(
        build_board(inc, cfg, NFL_PROFILE, points_col="league_points"),
        build_board(bad, cfg, NFL_PROFILE, points_col="league_points"))
    assert g["pass"] is False, "a non-monotone map MUST trip G1 — else the gate cannot fail"


# ── G2: the inherited rookie placement cap ──────────────────────────────────────────────────────
def test_g2_delegates_the_cap_and_transcribes_no_threshold_of_its_own():
    """The cap belongs to NF-D18/D20. This module must CALL it, never carry a copy of the number —
    a transcribed threshold drifts out of sync with its owner in silence.

    Docstrings and comments are stripped before scanning: prose explaining a threshold must not be
    able to satisfy OR trip a source guard (the INC-38 lesson, applied in both directions)."""
    tree = ast.parse(_MODULE.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body = node.body[1:] or [ast.Pass()]
    code = ast.unparse(tree)
    assert "rookie_placement_breach" in code, "G2 must delegate to the cap's owner"
    fn = next(n for n in ast.walk(ast.parse(code))
              if isinstance(n, ast.FunctionDef) and n.name == "rookie_placement")
    literals = [n.value for n in ast.walk(fn)
                if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
                and not isinstance(n.value, bool)]
    assert not literals, f"rookie_placement must transcribe no numeric threshold; found {literals}"


def test_g2_is_two_sided_a_rookie_placed_too_high_trips_it_and_moving_it_down_clears_it():
    """The DIRECTION is the whole argument: the cap refuses a rookie placing TOO HIGH, so TR2b —
    which moves rookies DOWN — moves strictly away from breach. Proven, not asserted."""
    high = pd.DataFrame([{"id": "r", "position": "RB", "rookie": True, "overall_rank": 1}])
    low = pd.DataFrame([{"id": "r", "position": "RB", "rookie": True, "overall_rank": 400}])
    assert PL.rookie_placement(high)["pass"] is False, "a rookie at overall 1 MUST breach the cap"
    assert PL.rookie_placement(low)["pass"] is True, "moving that rookie DOWN must clear it"


def test_g2_is_unevaluable_rather_than_healthy_on_a_board_with_no_rookies():
    """NF1.7 (a) — a check that could not run is never scored as a pass by the classifier."""
    none_rk = pd.DataFrame([{"id": "v", "position": "RB", "rookie": False, "overall_rank": 1}])
    got = PL.rookie_placement(none_rk)
    assert got["verdict"].get("breach") is None
    assert PL.classify_placement({"g": {"pass": None}})["verdict"] == "REVIEW_REQUIRED"


# ── G3 / G4 ─────────────────────────────────────────────────────────────────────────────────────
def test_g3_trips_when_a_recalibrated_position_is_wiped_out_of_the_top_n():
    survives = pd.DataFrame([{"id": f"p{i}", "position": p, "overall_rank": i + 1}
                             for i, p in enumerate(["QB", "RB", "WR", "TE"])])
    assert PL.position_survival(survives, K, top_n=4)["pass"] is True
    wiped = pd.DataFrame([{"id": f"p{i}", "position": p, "overall_rank": i + 1}
                          for i, p in enumerate(["RB", "RB", "WR", "TE"])])
    got = PL.position_survival(wiped, K, top_n=4)
    assert got["pass"] is False and "QB" in got["wiped_out"]


def test_g4_catches_an_inverted_band_and_a_point_outside_its_own_band():
    ok = pd.DataFrame([{"fpPpr": 100.0, "fpP10": 50.0, "fpP90": 150.0}])
    assert PL.band_integrity(ok)["pass"] is True
    inverted = pd.DataFrame([{"fpPpr": 100.0, "fpP10": 150.0, "fpP90": 50.0}])
    assert PL.band_integrity(inverted)["pass"] is False
    through_p90 = pd.DataFrame([{"fpPpr": 200.0, "fpP10": 50.0, "fpP90": 150.0}])
    got = PL.band_integrity(through_p90)
    assert got["pass"] is False and got["point_above_p90"] == 1, (
        "a point pushed THROUGH its own p90 is the predictable TR2b serving symptom — it must trip")


# ── the runner's contracts ──────────────────────────────────────────────────────────────────────
def test_the_runner_writes_only_inside_the_repo_and_only_its_own_paths():
    """A fixed-output-path write that escapes the checkout clobbers whatever is at the other end,
    and a run must never write a DECIDED story's artifacts (the NCAAF-P2.1 S1-serve lesson)."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_tr2b_placement_read as R
    root = R._PROJECT_ROOT
    assert (root / "pyproject.toml").exists() and (root / "CLAUDE.md").exists(), (
        f"_PROJECT_ROOT {root} is not the repo root — outputs would land outside the checkout")
    for out in (R._OUT_JSON, R._OUT_MD):
        assert root in out.parents, f"{out} escapes the repo root"
        assert out.name.startswith("nf_tr2b_placement_read."), (
            f"{out.name} is not this story's own artifact")


def test_k_is_read_from_the_served_artifact_and_a_missing_stamp_raises(tmp_path):
    """The read must undo the k that is ACTUALLY ON THE WIRE. A stamp-less payload is a FINDING —
    defaulting past it would let the read silently agree with itself."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_tr2b_placement_read as R
    import json
    (tmp_path / "projections.json").write_text(json.dumps({"season": 2026, "players": []}))
    with pytest.raises(RuntimeError, match="no veteran_level_policy params"):
        R.run(tmp_path)


def test_the_policy_positions_and_the_read_agree_on_what_is_recalibrated():
    """If the served policy ever recalibrates a new position, the reconstruction must follow it
    automatically rather than carrying its own list."""
    src = _MODULE.read_text()
    assert "VLP.RECALIBRATED_POSITIONS" in src, "the read must source positions from the policy"
    assert set(VLP.RECALIBRATED_POSITIONS) == {"QB", "RB", "WR", "TE"}
