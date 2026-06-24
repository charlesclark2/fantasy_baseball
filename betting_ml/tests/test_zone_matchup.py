"""E13.10 zone-matchup PURE-logic tests — grid binning, EB shrinkage, overlap math, per-game
aggregation, and the cold-start fallback. No S3 / no duckdb (the lakehouse reads are exercised
by the operator's full run); these pin the math the viz + lift-feature both depend on."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from betting_ml.scripts.zone_matchup import grid, overlap, profiles, shrink, viz


# ── grid ──────────────────────────────────────────────────────────────────────
def test_bin_clamps_to_edges():
    g = grid.GridSpec()
    assert g.bin_x(-999) == 0 and g.bin_x(999) == g.nx - 1
    assert g.bin_z(-999) == 0 and g.bin_z(999) == g.nz - 1
    # center of grid lands in a middle cell
    assert g.bin_x(0.0) == g.nx // 2
    assert g.bin_z(0.5) == g.nz // 2


def test_python_and_sql_binning_agree():
    """The closed-form SQL expression MUST reproduce bin_x/bin_z exactly (the leak-free guarantee
    that viz cells and feature cells are the same cells)."""
    g = grid.GridSpec()
    for v in np.linspace(-2.0, 2.0, 41):
        # replicate the SQL: greatest(0, least(N-1, floor((v-min)/step)))
        ix_sql = max(0, min(g.nx - 1, math.floor((v - g.x_min) / g.x_step)))
        assert ix_sql == g.bin_x(v), v
    for v in np.linspace(-1.0, 2.0, 31):
        iz_sql = max(0, min(g.nz - 1, math.floor((v - g.z_min) / g.z_step)))
        assert iz_sql == g.bin_z(v), v


def test_group_of_and_sql_case_agree():
    assert grid.group_of("FF") == "FB" and grid.group_of("SI") == "FB"
    assert grid.group_of("SL") == "BR" and grid.group_of("KC") == "BR"
    assert grid.group_of("CH") == "OS" and grid.group_of("FS") == "OS"
    assert grid.group_of(None) is None and grid.group_of("XX") is None
    # the SQL CASE lists must cover exactly the same codes
    case = grid.sql_group_case("pt")
    for code in ("FF", "SI", "FC", "SL", "CU", "ST", "CH", "FS"):
        assert f"'{code}'" in case


# ── shrink ──────────────────────────────────────────────────────────────────────
def test_eb_mean_collapses_to_prior_at_n0_and_to_raw_at_large_n():
    raw = np.array([0.5, 0.5, np.nan])
    n = np.array([0.0, 1e6, 0.0])
    prior = np.array([0.1, 0.1, 0.1])
    out = shrink.eb_mean(raw, n, prior, k=120.0)
    assert out[0] == 0.1                       # n=0 → prior
    assert abs(out[1] - 0.5) < 1e-3            # huge n → raw
    assert out[2] == 0.1                       # NaN raw, n=0 → prior


def test_eb_rate_is_between_prior_and_raw():
    out = shrink.eb_rate(np.array([10.0]), np.array([20.0]), np.array([0.25]), k=150.0)
    # raw=0.5, prior=0.25, heavy k → closer to prior
    assert 0.25 < out[0] < 0.5
    # tot=0 → prior
    assert shrink.eb_rate(np.array([0.0]), np.array([0.0]), np.array([0.25]), k=150.0)[0] == 0.25


# ── overlap ──────────────────────────────────────────────────────────────────────
def _toy_profiles():
    # one batter (id 1, RHB) crushes fastballs (value 1.0) but weak vs breaking (-0.5);
    bval = pd.DataFrame([
        dict(batter_id=1, b_hand="R", vs_p_hand="R", pgroup="FB", ix=2, iz=2, value=1.0),
        dict(batter_id=1, b_hand="R", vs_p_hand="R", pgroup="BR", ix=2, iz=2, value=-0.5),
    ])
    return bval if False else bval  # noqa


def test_compute_overlap_is_freq_weighted_value():
    bval = pd.DataFrame([
        dict(batter_id=1, b_hand="R", vs_p_hand="R", pgroup="FB", ix=2, iz=2, value=1.0),
        dict(batter_id=1, b_hand="R", vs_p_hand="R", pgroup="BR", ix=2, iz=2, value=-0.5),
    ])
    # pitcher 9 (RHP) throws 70% FB / 30% BR into that cell vs RHB
    pfreq = pd.DataFrame([
        dict(pitcher_id=9, p_hand="R", vs_b_hand="R", pgroup="FB", ix=2, iz=2, freq=0.7),
        dict(pitcher_id=9, p_hand="R", vs_b_hand="R", pgroup="BR", ix=2, iz=2, freq=0.3),
    ])
    pairs = pd.DataFrame([dict(batter_id=1, b_hand="R", pitcher_id=9, p_hand="R")])
    out = overlap.compute_overlap(bval, pfreq, pairs)
    assert abs(out.loc[0, "overlap"] - (0.7 * 1.0 + 0.3 * -0.5)) < 1e-9
    assert out.loc[0, "overlap_cells"] == 2


def test_compute_overlap_respects_handedness_split():
    # batter value only defined vs RHP; facing a LHP → no cells join → overlap NaN
    bval = pd.DataFrame([dict(batter_id=1, b_hand="R", vs_p_hand="R", pgroup="FB",
                             ix=2, iz=2, value=1.0)])
    pfreq = pd.DataFrame([dict(pitcher_id=9, p_hand="L", vs_b_hand="R", pgroup="FB",
                              ix=2, iz=2, freq=1.0)])
    pairs = pd.DataFrame([dict(batter_id=1, b_hand="R", pitcher_id=9, p_hand="L")])
    out = overlap.compute_overlap(bval, pfreq, pairs)
    assert out.loc[0, "overlap_cells"] == 0
    assert pd.isna(out.loc[0, "overlap"])


def test_game_side_overlap_pivots_to_home_away():
    bval = pd.DataFrame([
        dict(batter_id=1, b_hand="R", vs_p_hand="L", pgroup="FB", ix=2, iz=2, value=0.4),
        dict(batter_id=2, b_hand="L", vs_p_hand="R", pgroup="FB", ix=2, iz=2, value=0.8),
    ])
    pfreq = pd.DataFrame([
        dict(pitcher_id=50, p_hand="L", vs_b_hand="R", pgroup="FB", ix=2, iz=2, freq=1.0),
        dict(pitcher_id=60, p_hand="R", vs_b_hand="L", pgroup="FB", ix=2, iz=2, freq=1.0),
    ])
    # game 100: home lineup = batter 1; away lineup = batter 2; home starter=60 (R), away starter=50 (L)
    lineups = pd.DataFrame([
        dict(game_pk=100, side="home", batter_id=1, b_hand="R"),
        dict(game_pk=100, side="away", batter_id=2, b_hand="L"),
    ])
    starters = pd.DataFrame([
        dict(game_pk=100, side="home", pitcher_id=60, p_hand="R"),
        dict(game_pk=100, side="away", pitcher_id=50, p_hand="L"),
    ])
    out = overlap.game_side_overlap(lineups, starters, bval, pfreq)
    row = out[out["game_pk"] == 100].iloc[0]
    # home offense (b1, R) faces away starter 50 (L) → uses bval vs_p_hand=L = 0.4
    assert abs(row["home_zone_overlap"] - 0.4) < 1e-9
    # away offense (b2, L) faces home starter 60 (R) → uses bval vs_p_hand=R = 0.8
    assert abs(row["away_zone_overlap"] - 0.8) < 1e-9
    assert row["home_zone_overlap_n"] == 1 and row["away_zone_overlap_n"] == 1


# ── profiles (cold-start) ──────────────────────────────────────────────────────
def _toy_league_raw():
    rows = []
    for ph in ("L", "R"):
        for bh in ("L", "R"):
            for pg in ("FB", "BR", "OS"):
                rows.append(dict(p_hand=ph, b_hand=bh, pgroup=pg, ix=2, iz=2,
                                 n_pitches=1000, lg_rv=-0.01, n_swings=400, n_whiffs=80,
                                 lg_xwoba_con=0.34))
    return pd.DataFrame(rows)


def test_batter_cold_start_flag_and_shrink_to_prior():
    league = _toy_league_raw()
    # rookie: only 10 pitches total → cold start; value should sit near the league prior (-0.01)
    rookie = pd.DataFrame([dict(batter_id=7, b_hand="R", vs_p_hand="R", pgroup="FB", ix=2, iz=2,
                               n_pitches=10, raw_rv=2.0, n_swings=5, n_whiffs=0, n_bip=3,
                               raw_xwoba_con=0.9)])
    out = profiles.build_batter_value(rookie, league, min_pitches=200)
    assert bool(out.loc[0, "is_cold_start"]) is True
    assert abs(out.loc[0, "value"] - (-0.01)) < 0.2   # heavily shrunk toward prior despite raw=2.0


def test_pitcher_freq_sums_to_one_and_cold_start_uses_league():
    league = _toy_league_raw()
    warm = pd.DataFrame([
        dict(pitcher_id=11, p_hand="R", vs_b_hand="R", pgroup="FB", ix=2, iz=2, n_pitches=700),
        dict(pitcher_id=11, p_hand="R", vs_b_hand="R", pgroup="BR", ix=2, iz=2, n_pitches=300),
    ])
    out = profiles.build_pitcher_freq(warm, league, min_pitches=200)
    s = out[(out.pitcher_id == 11) & (out.vs_b_hand == "R")]["freq"].sum()
    assert abs(s - 1.0) < 1e-9
    assert not out["is_cold_start"].any()

    cold = pd.DataFrame([
        dict(pitcher_id=22, p_hand="L", vs_b_hand="R", pgroup="FB", ix=2, iz=2, n_pitches=5),
    ])
    out2 = profiles.build_pitcher_freq(cold, league, min_pitches=200)
    assert out2["is_cold_start"].all()
    # league usage fallback present for all 3 groups in that league cell
    assert set(out2["pgroup"]) == {"FB", "BR", "OS"}


# ── harness bridge (the opt-in lakehouse → lift-harness join) ──────────────────
def test_merge_feature_parquet_joins_on_game_pk(tmp_path):
    from betting_ml.scripts.incremental_lift_eval import merge_feature_parquet

    df = pd.DataFrame({"game_pk": [1, 2, 3], "game_year": [2026, 2026, 2026],
                       "home_existing": [0.1, 0.2, 0.3]})
    feat = pd.DataFrame({"game_pk": [1, 2], "home_zone_overlap": [0.5, 0.6],
                         "away_zone_overlap": [-0.1, -0.2]})
    p = tmp_path / "f.parquet"
    feat.to_parquet(p, index=False)

    out = merge_feature_parquet(df, str(p))
    assert {"home_zone_overlap", "away_zone_overlap"} <= set(out.columns)
    assert out.loc[out.game_pk == 1, "home_zone_overlap"].iloc[0] == 0.5
    assert pd.isna(out.loc[out.game_pk == 3, "home_zone_overlap"].iloc[0])  # unmatched → NaN
    # no path ⇒ untouched (default Snowflake-only behaviour preserved)
    assert merge_feature_parquet(df, None) is df


def test_merge_feature_parquet_does_not_overwrite_existing(tmp_path):
    from betting_ml.scripts.incremental_lift_eval import merge_feature_parquet

    df = pd.DataFrame({"game_pk": [1], "home_zone_overlap": [9.9]})
    feat = pd.DataFrame({"game_pk": [1], "home_zone_overlap": [0.5]})
    p = tmp_path / "f.parquet"
    feat.to_parquet(p, index=False)
    out = merge_feature_parquet(df, str(p))
    assert out.loc[0, "home_zone_overlap"] == 9.9   # existing column not clobbered


# ── overlay JSON contract (Track A product) ────────────────────────────────────
def test_build_overlay_json_contract():
    g = grid.GridSpec()
    bval = profiles.build_batter_value(
        pd.DataFrame([dict(batter_id=1, b_hand="L", vs_p_hand="R", pgroup="FB", ix=2, iz=2,
                           n_pitches=500, raw_rv=0.05, n_swings=200, n_whiffs=40, n_bip=120,
                           raw_xwoba_con=0.45)]),
        _toy_league_raw(), grid=g, min_pitches=200)
    pfreq = profiles.build_pitcher_freq(
        pd.DataFrame([dict(pitcher_id=9, p_hand="R", vs_b_hand="L", pgroup="FB", ix=2, iz=2,
                           n_pitches=600, loc_x=0.1, loc_znorm=0.55)]),
        _toy_league_raw(), min_pitches=200)
    ov = viz.build_overlay(bval, pfreq, batter_id=1, b_hand="L", pitcher_id=9, p_hand="R",
                           grid=g, as_of_date="2026-06-20", batter_name="B", pitcher_name="P",
                           sz_top=3.4, sz_bot=1.6)
    assert ov["schema_version"] == "2.0"
    assert ov["pitch_groups"] == ["fastball", "breaking", "offspeed", "all"]
    assert ov["strike_zone"] == {"sz_top": 3.4, "sz_bot": 1.6}
    # 25 cells × 4 groups
    assert len(ov["cells"]) == g.n_cells * 4
    c = ov["cells"][0]
    assert {"pitch_group", "ix", "iz", "x_ft", "z_norm", "z_ft", "batter_run_value",
            "pitcher_usage_freq", "pitcher_loc"} <= set(c)
    assert set(c["pitcher_loc"]) == {"x_ft", "z_ft"}
    # the pitcher's measured location is carried (not just the cell center)
    fb = [x for x in ov["cells"] if x["pitch_group"] == "fastball" and x["ix"] == 2 and x["iz"] == 2][0]
    assert abs(fb["pitcher_loc"]["x_ft"] - 0.1) < 1e-6
    assert ov["overlap_scalar"] is not None
