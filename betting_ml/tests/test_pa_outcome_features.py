"""Unit tests for the E13.2 leak-safe PA-outcome feature builder
(betting_ml/scripts/pa_outcome_v1/features_pa_outcome.py).

The critical property is LEAKAGE: a PA's batter/pitcher prior-rate profile must
reflect ONLY PAs strictly before that PA's game_date — never the current PA's own
outcome, never same-day games, never future games.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_FEATURES_DIR = Path(__file__).resolve().parents[1] / "scripts" / "pa_outcome_v1"
sys.path.insert(0, str(_FEATURES_DIR))
from features_pa_outcome import (  # noqa: E402
    CLASSES,
    DEFAULT_KAPPA,
    STATIC_LEAGUE_PRIOR,
    build_pit_features,
)


def _row(game_pk, ab, date, batter, pitcher, label, b_hand="R", p_hand="R", tto=1):
    return dict(game_pk=game_pk, at_bat_number=ab, game_date=date,
                game_year=int(date[:4]), batter_id=batter, pitcher_id=pitcher,
                pa_outcome_label=label, batter_hand=b_hand, pitcher_hand=p_hand,
                pitcher_times_thru_order_at_entry=tto)


def test_first_pa_has_no_prior_uses_static_marginal():
    df = pd.DataFrame([_row(1, 1, "2015-04-01", 100, 200, "HR")])
    out, _ = build_pit_features(df)
    r = out.iloc[0]
    assert r["bat_prior_n"] == 0.0 and r["pit_prior_n"] == 0.0
    for c in CLASSES:
        assert abs(r[f"bat_eb_{c}"] - STATIC_LEAGUE_PRIOR[c]) < 1e-9, c
        assert abs(r[f"pit_eb_{c}"] - STATIC_LEAGUE_PRIOR[c]) < 1e-9, c


def test_batter_rate_reflects_only_strictly_earlier_dates():
    df = pd.DataFrame([
        _row(1, 1, "2015-04-01", 100, 201, "HR"),
        _row(2, 1, "2015-04-02", 100, 202, "HR"),
        _row(3, 1, "2015-04-03", 100, 203, "K"),   # current — its own K must NOT count
    ])
    out, _ = build_pit_features(df, kappa=DEFAULT_KAPPA)
    r3 = out[out["game_pk"] == 3].iloc[0]
    assert r3["bat_prior_n"] == 2.0          # 2 prior PAs, not 3 (no same-PA leak)
    assert r3["bat_eb_HR"] > STATIC_LEAGUE_PRIOR["HR"]
    assert r3["bat_eb_K"] <= STATIC_LEAGUE_PRIOR["K"] + 1e-9


def test_same_day_games_do_not_leak():
    df = pd.DataFrame([
        _row(1, 1, "2015-04-01", 100, 201, "HR"),
        _row(10, 1, "2015-05-01", 100, 202, "1B"),
        _row(11, 1, "2015-05-01", 100, 203, "1B"),  # same date as game 10
    ])
    out, _ = build_pit_features(df)
    a = out[out["game_pk"] == 10].iloc[0]
    b = out[out["game_pk"] == 11].iloc[0]
    assert a["bat_prior_n"] == 1.0 and b["bat_prior_n"] == 1.0
    for c in CLASSES:
        assert abs(a[f"bat_eb_{c}"] - b[f"bat_eb_{c}"]) < 1e-12


def test_eb_shrinks_thin_cells_toward_prior():
    df = pd.DataFrame([
        _row(1, 1, "2015-04-01", 100, 201, "HR"),
        _row(2, 1, "2015-04-02", 100, 202, "out"),
    ])
    out, _ = build_pit_features(df, kappa=100.0)
    r2 = out[out["game_pk"] == 2].iloc[0]
    assert r2["bat_eb_HR"] < 0.05                       # not the raw 1.0
    assert r2["bat_eb_HR"] > STATIC_LEAGUE_PRIOR["HR"]  # but above marginal


def test_eb_rows_sum_to_one():
    rng = np.random.default_rng(0)
    labels = rng.choice(CLASSES, size=400)
    df = pd.DataFrame([
        _row(i, 1, f"2015-{1 + (i // 28) % 9:02d}-{1 + (i % 28):02d}",
             100 + (i % 7), 200 + (i % 5), labels[i],
             b_hand="LR"[i % 2], p_hand="LR"[(i // 2) % 2], tto=1 + (i % 3))
        for i in range(400)
    ])
    out, cols = build_pit_features(df)  # splits on by default
    for fam in ("bat_eb", "pit_eb", "bat_plat_eb", "pit_plat_eb", "pit_tto_eb"):
        s = out[[f"{fam}_{c}" for c in CLASSES]].sum(axis=1).to_numpy()
        assert np.allclose(s, 1.0, atol=1e-9), fam
    assert len(cols) == 22 + 30  # v1 (22) + v2 splits (30)


# ── v2 matched-split features ────────────────────────────────────────────────

def test_split_matches_current_context_and_is_leak_safe():
    # Batter 100 homers vs LHP twice (earlier), then a PA vs an LHP (current).
    # bat_plat_eb_HR (vs-L matched) must be elevated and must NOT include the
    # current PA's own outcome.
    df = pd.DataFrame([
        _row(1, 1, "2015-04-01", 100, 301, "HR", p_hand="L"),
        _row(2, 1, "2015-04-02", 100, 302, "HR", p_hand="L"),
        _row(3, 1, "2015-04-03", 100, 303, "K",  p_hand="L"),  # current vs LHP
    ])
    out, _ = build_pit_features(df, kappa_split=50.0)
    r3 = out[out["game_pk"] == 3].iloc[0]
    # 2 prior HR vs LHP → matched split HR rate elevated above the batter's overall.
    assert r3["bat_plat_eb_HR"] > r3["bat_eb_HR"]
    # The current K did not leak into the vs-L HR/ K split (prior is 2 PAs only).
    assert r3["bat_plat_eb_K"] <= r3["bat_eb_K"] + 1e-9


def test_split_falls_back_to_overall_when_no_prior_in_context():
    # Batter's only prior is vs LHP; a PA vs RHP has no matching-context prior →
    # bat_plat_eb (vs-R) must equal the batter's overall rate (graceful fallback).
    df = pd.DataFrame([
        _row(1, 1, "2015-04-01", 100, 301, "HR", p_hand="L"),
        _row(2, 1, "2015-04-02", 100, 304, "out", p_hand="R"),  # first PA vs RHP
    ])
    out, _ = build_pit_features(df, kappa_split=50.0)
    r2 = out[out["game_pk"] == 2].iloc[0]
    for c in CLASSES:
        assert abs(r2[f"bat_plat_eb_{c}"] - r2[f"bat_eb_{c}"]) < 1e-9, c
