"""E13.6b — served totals P(over) calibration: pure extraction + fit logic (no network)."""

from __future__ import annotations

import numpy as np

from betting_ml.scripts.fit_totals_calibrator_e13_6b import (
    _split_index,
    extract_totals_pair,
    fit_candidates,
    fit_temperature,
)


# ── serving-cache totals extraction ──────────────────────────────────────────
def _detail(status="Final", hs=5, as_=4, totals=None, extra_picks=None):
    picks = list(extra_picks or [])
    if totals is not None:
        picks.append({"market_type": "totals", **totals})
    return {"game_score": {"status": status, "home_score": hs, "away_score": as_}, "picks": picks}


def test_extract_totals_over_and_date_retained():
    row = extract_totals_pair(_detail(hs=5, as_=4, totals={
        "model_prob": 0.55, "bovada_devig_prob": 0.5, "market_total_line": 8.5,
        "game_date": "2026-05-01", "game_pk": 123}))
    assert row == {"game_pk": 123, "game_date": "2026-05-01",
                   "model_prob": 0.55, "market_prob": 0.5, "outcome": 1}  # total 9 > 8.5


def test_extract_totals_under_outcome_zero():
    row = extract_totals_pair(_detail(hs=2, as_=3, totals={
        "model_prob": 0.6, "market_total_line": 8.5, "game_date": "2026-05-01"}))
    assert row["outcome"] == 0  # total 5 < 8.5


def test_extract_drops_push_and_nonfinal_and_missing():
    push = extract_totals_pair(_detail(hs=4, as_=4, totals={
        "model_prob": 0.55, "market_total_line": 8.0, "game_date": "2026-05-01"}))
    assert push is None  # total 8 == line → no binary label
    assert extract_totals_pair(_detail(status="Live", totals={
        "model_prob": 0.5, "market_total_line": 8.5, "game_date": "d"})) is None
    assert extract_totals_pair(_detail(hs=None, totals={
        "model_prob": 0.5, "market_total_line": 8.5, "game_date": "d"})) is None
    assert extract_totals_pair(_detail(totals={  # missing model_prob
        "market_total_line": 8.5, "game_date": "d"})) is None
    assert extract_totals_pair(_detail(totals=None)) is None  # no totals pick


def test_extract_market_prob_optional():
    row = extract_totals_pair(_detail(hs=6, as_=5, totals={
        "model_prob": 0.7, "market_total_line": 9.5, "game_date": "d"}))  # no bovada_devig_prob
    assert row["market_prob"] is None and row["outcome"] == 1  # total 11 > 9.5


# ── date-aligned chronological split ─────────────────────────────────────────
def test_split_index_keeps_cut_date_whole_in_train_and_no_straddle():
    # 10 games across 4 dates; eval_frac 0.25 → target ~7 → cut date fully in train.
    dates = ["2026-05-01"] * 3 + ["2026-05-02"] * 3 + ["2026-05-03"] * 2 + ["2026-05-04"] * 2
    train_end, eval_start, train_cut, eval_start_date = _split_index(dates, eval_frac=0.25, embargo_days=0)
    # no date may appear in both train and eval
    train_dates, eval_dates = set(dates[:train_end]), set(dates[eval_start:])
    assert train_dates.isdisjoint(eval_dates)
    assert train_cut in train_dates and eval_start_date in eval_dates


def test_split_index_embargo_drops_boundary_slate():
    dates = ["2026-05-01"] * 3 + ["2026-05-02"] * 3 + ["2026-05-03"] * 2 + ["2026-05-04"] * 2
    _, eval_start, train_cut, eval_start_date = _split_index(dates, eval_frac=0.25, embargo_days=1)
    # the slate the day AFTER train_cut is embargoed out of eval
    from datetime import date, timedelta
    embargoed = (date.fromisoformat(train_cut) + timedelta(days=1)).isoformat()
    assert eval_start_date > embargoed or eval_start_date == "<none>"


# ── calibrator fit ───────────────────────────────────────────────────────────
def test_fit_temperature_shrinks_overconfident():
    rng = np.random.default_rng(0)
    # overconfident: prob spread wide but outcome ~ base rate → T should be > 1 (shrink)
    p = rng.uniform(0.1, 0.9, 400)
    y = (rng.uniform(size=400) < 0.5).astype(float)  # no signal → any confidence is overconfidence
    assert fit_temperature(p, y) > 1.0


def test_fit_candidates_selects_by_ece_and_returns_calibrator():
    rng = np.random.default_rng(1)
    n = 600
    # chronologically ordered synthetic overconfident served probs
    p = rng.uniform(0.15, 0.85, n)
    y = (rng.uniform(size=n) < 0.5 + 0.15 * (p - 0.5)).astype(float)  # mild real signal
    dates = [f"2026-05-{1 + i // 30:02d}" for i in range(n)]
    out = fit_candidates(p, y, dates, eval_frac=0.25, embargo_days=1)
    assert out["ece_pick"] in {"identity", "platt", "isotonic", "temperature"}
    assert out["eval_n"] >= 20 and out["train_n"] > out["eval_n"]
    # candidate must be a usable calibrator (predict/predict_proba)
    cand = out["candidate"]
    pred = (cand.predict(np.array([0.3, 0.6])) if hasattr(cand, "predict")
            else cand.predict_proba(np.array([[0.3], [0.6]]))[:, 1])
    assert pred.shape == (2,)
