"""E9.26 — calibration primitives + serving-cache pair extraction (pure, no network)."""

from __future__ import annotations

import numpy as np

from betting_ml.utils.calibration_metrics import ece, metric_block, reliability_table
from scripts.compute_calibration_artifact_e9_26 import build_artifact, extract_calibration_pairs


# ── metric primitives ────────────────────────────────────────────────────────

def test_ece_zero_for_perfectly_calibrated():
    # bin at 0.1 realizes 10% ones, bin at 0.9 realizes 90% ones → ECE 0
    p = np.array([0.1] * 100 + [0.9] * 100)
    y = np.array([0] * 90 + [1] * 10 + [0] * 10 + [1] * 90)
    assert ece(p, y) < 0.01


def test_ece_high_for_overconfident():
    p = np.array([0.95] * 100)         # says 95%
    y = np.array([0] * 50 + [1] * 50)  # actually 50%
    assert ece(p, y) > 0.4


def test_metric_block_and_reliability_shapes():
    p = np.array([0.2, 0.4, 0.6, 0.8])
    y = np.array([0, 0, 1, 1])
    block = metric_block(p, y)
    assert block["n"] == 4 and block["ece"] is not None and block["brier"] is not None
    rows = reliability_table(p, y)
    assert all({"bin_lo", "bin_hi", "n", "avg_pred", "avg_actual"} <= r.keys() for r in rows)


def test_metric_block_empty_is_safe():
    block = metric_block([], [])
    assert block["n"] == 0 and block["ece"] is None


# ── serving-cache extraction ──────────────────────────────────────────────────

def _detail(status="Final", hs=5, as_=3, picks=None):
    return {"game_score": {"status": status, "home_score": hs, "away_score": as_},
            "picks": picks or []}


def test_extract_h2h_outcome_and_prob():
    d = _detail(hs=5, as_=3, picks=[{"market_type": "h2h", "model_prob": 0.62,
                                     "bovada_devig_prob": 0.58}])
    pairs = extract_calibration_pairs(d)
    assert pairs["h2h"][0] == {"model_prob": 0.62, "market_prob": 0.58, "outcome": 1}


def test_extract_totals_uses_line_and_drops_push():
    over = _detail(hs=5, as_=4, picks=[{"market_type": "totals", "model_prob": 0.55,
                                        "bovada_devig_prob": 0.5, "market_total_line": 8.5}])
    assert extract_calibration_pairs(over)["totals"][0]["outcome"] == 1  # total 9 > 8.5
    push = _detail(hs=4, as_=4, picks=[{"market_type": "totals", "model_prob": 0.55,
                                        "bovada_devig_prob": 0.5, "market_total_line": 8.0}])
    assert "totals" not in extract_calibration_pairs(push)  # push dropped (no label)


def test_extract_skips_non_final_and_missing():
    assert extract_calibration_pairs(_detail(status="Live", picks=[{"market_type": "h2h",
                                                                    "model_prob": 0.6}])) == {}
    assert extract_calibration_pairs(_detail(hs=None, picks=[{"market_type": "h2h",
                                                              "model_prob": 0.6}])) == {}
    # missing model_prob → not paired
    assert extract_calibration_pairs(_detail(picks=[{"market_type": "h2h",
                                                     "bovada_devig_prob": 0.5}])) == {}


def test_build_artifact_notes_totals_uncalibrated():
    d = _detail(hs=6, as_=2, picks=[
        {"market_type": "h2h", "model_prob": 0.6, "bovada_devig_prob": 0.55},
        {"market_type": "totals", "model_prob": 0.52, "bovada_devig_prob": 0.5,
         "market_total_line": 7.5},
    ])
    pairs = extract_calibration_pairs(d)
    art = build_artifact(pairs, {"start": "a", "end": "b", "n_final_games": 1})
    assert art["story"] == "E9.26"
    assert "raw distributional" in art["notes"]["totals"]
    assert art["markets"]["h2h"]["model"]["n"] == 1
