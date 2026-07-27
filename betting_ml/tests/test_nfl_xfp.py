"""NF-D7 — Expected Fantasy Points (xFP) + TD regression. Pure/offline unit tests for the opportunity
math (league bucket rates, expected-TD, the TD-regression blend, window weighting) and the
`project_veterans` wiring. No IO (the S3 play-by-play read is exercised by the ablation harness), so
these land in the fast gate."""
import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import season_projection as sp
from quant_sports_intel_models.football.nfl.fantasy import xfp_source as X


# ── league TD-conversion rates ────────────────────────────────────────────────────────────────────
def _opp_pool():
    """A tiny synthetic opportunity pool: goal-line converts far more than midfield, per role."""
    return pd.DataFrame([
        # player A: 10 goal-line carries → 5 rush TDs (rate 0.5); 100 midfield carries → 1 TD (0.01)
        {"player_id": "A", "c_gl": 10, "ctd_gl": 5, "c_rz5": 0, "ctd_rz5": 0, "c_rz10": 0, "ctd_rz10": 0,
         "c_rz20": 0, "ctd_rz20": 0, "c_ff": 100, "ctd_ff": 1,
         "t_gl": 0, "ttd_gl": 0, "t_rz5": 0, "ttd_rz5": 0, "t_rz10": 0, "ttd_rz10": 0,
         "t_rz20": 0, "ttd_rz20": 0, "t_ff": 0, "ttd_ff": 0},
        # player B: 20 end-zone (gl) targets → 8 rec TDs (rate 0.4); 80 midfield targets → 2 (0.025)
        {"player_id": "B", "c_gl": 0, "ctd_gl": 0, "c_rz5": 0, "ctd_rz5": 0, "c_rz10": 0, "ctd_rz10": 0,
         "c_rz20": 0, "ctd_rz20": 0, "c_ff": 0, "ctd_ff": 0,
         "t_gl": 20, "ttd_gl": 8, "t_rz5": 0, "ttd_rz5": 0, "t_rz10": 0, "ttd_rz10": 0,
         "t_rz20": 0, "ttd_rz20": 0, "t_ff": 80, "ttd_ff": 2},
    ])


def test_league_td_rates_are_exact_bucket_conversion():
    rush, rec = X.league_td_rates(_opp_pool())
    assert rush["gl"] == pytest.approx(0.5)      # 5/10
    assert rush["ff"] == pytest.approx(0.01)     # 1/100
    assert rec["gl"] == pytest.approx(0.4)       # 8/20
    assert rec["ff"] == pytest.approx(0.025)     # 2/80
    # a bucket with no opportunity → 0.0 (never NaN)
    assert rush["rz5"] == 0.0 and rec["rz10"] == 0.0


def test_expected_td_is_opportunity_weighted_sum():
    pool = _opp_pool()
    rush, rec = X.league_td_rates(pool)
    out = X.expected_td_from_opportunity(pool, rush, rec)
    a = out[out.player_id == "A"].iloc[0]
    b = out[out.player_id == "B"].iloc[0]
    # A: 10·0.5 + 100·0.01 = 6.0 expected rush TDs (vs 6 actual — well finished)
    assert a["xrush_td"] == pytest.approx(6.0)
    assert a["xrec_td"] == pytest.approx(0.0)
    # B: 20·0.4 + 80·0.025 = 10.0 expected rec TDs (vs 10 actual)
    assert b["xrec_td"] == pytest.approx(10.0)


def test_expected_td_flags_lucky_and_unlucky():
    # a player with elite goal-line volume but bad finishing → xTD >> actual (regress UP)
    pool = pd.DataFrame([{"player_id": "unlucky", "c_gl": 20, "ctd_gl": 2,  # only 2 of 20 GL → unlucky
                          **{c: 0 for c in ("c_rz5 ctd_rz5 c_rz10 ctd_rz10 c_rz20 ctd_rz20 c_ff ctd_ff "
                             "t_gl ttd_gl t_rz5 ttd_rz5 t_rz10 ttd_rz10 t_rz20 ttd_rz20 t_ff ttd_ff").split()}}])
    # league GL rush rate from a separate pool = 0.5
    rush = {"gl": 0.5, "rz5": 0.0, "rz10": 0.0, "rz20": 0.0, "ff": 0.0}
    out = X.expected_td_from_opportunity(pool, rush, {b: 0.0 for b in X._BUCKETS})
    assert out["xrush_td"].iloc[0] == pytest.approx(10.0)   # 20·0.5 expected; only 2 scored ⇒ buy-low


# ── the TD-regression blend (pure) ──────────────────────────────────────────────────────────────
def test_regress_td_rate_blend_bounds():
    actual = np.array([1.0, 0.0, 0.5])
    expected = np.array([0.5, 0.5, 0.5])
    assert np.allclose(X.regress_td_rate(actual, expected, 0.0), actual)      # blend 0 = pure actual
    assert np.allclose(X.regress_td_rate(actual, expected, 1.0), expected)    # blend 1 = pure expected
    mid = X.regress_td_rate(actual, expected, 0.5)
    assert np.allclose(mid, 0.5 * actual + 0.5 * expected)                    # linear blend


def test_regress_td_rate_is_noop_where_expected_is_nan():
    actual = np.array([1.0, 2.0])
    expected = np.array([np.nan, 0.5])
    out = X.regress_td_rate(actual, expected, 0.7)
    assert out[0] == pytest.approx(1.0)                                       # NaN expected ⇒ unchanged
    assert out[1] == pytest.approx(0.3 * 2.0 + 0.7 * 0.5)


def test_window_weight_recency_and_games():
    # a season 1yr older counts 0.6×; an injury-shortened season contributes fewer games
    w = X.window_weight(np.array([0, 1, 2]), np.array([16.0, 16.0, 16.0]))
    assert w[0] == pytest.approx(16.0)
    assert w[1] == pytest.approx(0.6 * 16.0)
    assert w[2] == pytest.approx(0.36 * 16.0)
    # a base-season injury year (fewer games) down-weights
    assert X.window_weight(np.array([0]), np.array([4.0]))[0] == pytest.approx(4.0)


def test_bucket_constants_are_consistent():
    assert X._BUCKETS == ("gl", "rz5", "rz10", "rz20", "ff")
    # the recency window/decay must match the projection's base-season line (aligned per-game footing)
    assert X.RECENCY_DECAY == 0.6 and X.WINDOW_YEARS == 3


# ── project_veterans wiring ───────────────────────────────────────────────────────────────────────
def _rb(pid, rush_td_pg, x_rush_td_pg):
    base = {"player_id": pid, "player_name": pid, "team_id": "AAA", "position": "RB",
            "games_played": 15, "depth_chart_position_rank": 1, "fp_ppr_sd": 6.0,
            "snap_share": 0.8, "target_share": 0.08,
            "xrush_td_pg": x_rush_td_pg, "xrec_td_pg": 0.02}
    for s in sp._VET_PERGAME_STATS:
        base[s + "_pg"] = 0.0
    base.update(rush_att_pg=15, rush_yds_pg=70, rush_td_pg=rush_td_pg, targets_pg=3, rec_pg=2.4, rec_yds_pg=18)
    return base


def test_td_regression_moves_projection_toward_expected():
    # a LUCKY RB (high actual TD rate, lower expected) must regress DOWN; an UNLUCKY one UP.
    base = pd.DataFrame([_rb("LUCKY", rush_td_pg=1.0, x_rush_td_pg=0.4),
                         _rb("UNLUCKY", rush_td_pg=0.2, x_rush_td_pg=0.7)])
    priors = sp.positional_pergame_priors(base)
    on = sp.project_veterans(base, priors, 2026, xfp_td_blend=0.5).set_index("player_name")
    off = sp.project_veterans(base, priors, 2026, xfp_td_blend=0.0).set_index("player_name")
    # lucky player's projected rush TDs drop, unlucky player's rise, vs the un-regressed baseline
    assert on.loc["LUCKY", "proj_rush_td"] < off.loc["LUCKY", "proj_rush_td"]
    assert on.loc["UNLUCKY", "proj_rush_td"] > off.loc["UNLUCKY", "proj_rush_td"]


def test_td_regression_off_is_identity():
    base = pd.DataFrame([_rb("X", rush_td_pg=1.0, x_rush_td_pg=0.4)])
    priors = sp.positional_pergame_priors(base)
    on0 = sp.project_veterans(base, priors, 2026, xfp_td_blend=0.0)
    # blend 0 == the default shipped value (OFF) == dropping the xTD columns entirely
    base_noxtd = base.drop(columns=["xrush_td_pg", "xrec_td_pg"])
    noxtd = sp.project_veterans(base_noxtd, sp.positional_pergame_priors(base_noxtd), 2026)
    assert on0["proj_rush_td"].iloc[0] == pytest.approx(noxtd["proj_rush_td"].iloc[0])


def test_td_regression_noop_when_columns_absent():
    # a base frame with NO xTD columns must project identically regardless of the blend (graceful)
    base = pd.DataFrame([_rb("X", rush_td_pg=0.8, x_rush_td_pg=0.4)]).drop(columns=["xrush_td_pg", "xrec_td_pg"])
    priors = sp.positional_pergame_priors(base)
    a = sp.project_veterans(base, priors, 2026, xfp_td_blend=0.6)
    b = sp.project_veterans(base, priors, 2026, xfp_td_blend=0.0)
    assert a["proj_rush_td"].iloc[0] == pytest.approx(b["proj_rush_td"].iloc[0])


def test_shipped_default_blend_is_off():
    # the SHIPPED default must stay OFF unless the NF-D7 ablation earns it (honest-analytics posture)
    assert sp._XFP_TD_BLEND == 0.0
