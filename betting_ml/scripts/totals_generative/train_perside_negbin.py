"""train_perside_negbin.py — Edge Program Story E2.1 (Per-side count-distribution model).

Stage 1 of the Per-Side Generative Totals epic (E2): a per-game, per-SIDE Negative-Binomial
distribution over runs scored — the marginal the E2.2 copula will couple and E2.3 will
convolve into an honest total / run-diff / team-total distribution.

WHAT THIS CHANGES vs offense_v2 (the AC asks us to document the deltas)
----------------------------------------------------------------------
offense_v2 (LightGBM + global-r NegBin) already ships a per-side run distribution, but it
only sees the *batting side's own offence* (feature_pregame_lineup_features). E2.1 keeps that
NegBin output standard and builds on it, with three deliberate changes:

  1. FULL MATCHUP INPUTS.  Each side's runs are modelled from that side's offence PLUS the
     *opposing* starter, the *opposing* bullpen (quality + pen-state), the opposing pitching
     staff, park & environment, weather and umpire — the structural drivers of runs scored
     that offense_v2 omits. Assembled by "unpivoting" the wide per-game mart
     feature_pregame_game_features into one row per (game_pk, side): `off_*` = the batting
     side, `opp_*` = the team it faces, plus shared park/weather/umpire context.
  2. E1.1 PURGED CV.  Evaluation uses PurgedWalkForwardSplit (purge + embargo) instead of a
     plain season walk-forward, so the held-out NLL is not inflated by the rolling-feature
     boundary leak the E1 audit quantified.
  3. EXPLICIT POISSON BASELINE + OVERDISPERSION CHECK.  A count-natural Poisson-loss mean is
     scored under BOTH a Poisson likelihood (var = mean) and a NegBin likelihood (MLE
     dispersion r). The AC is: NegBin beats Poisson on held-out per-side-runs NLL, and the
     overdispersion is recovered (var/mean > 1).

MARKET-BLIND (architecture Principle 3, non-negotiable): the feature matrix is built from an
explicit baseball-only allow-list AND verified by `assert_market_blind` (the reusable
CONTRACT-GUARD) immediately before every fit. Zero odds/line/consensus/book columns enter.

GATE / AC
---------
  * NegBin mean held-out NLL  <  Poisson mean held-out NLL  (per-side runs, purged CV)
  * overdispersion recovered:  fitted r finite, implied var/mean > 1
  * CONTRACT-GUARD passes (no market columns in the matrix)

This is a >1-min Snowflake + multi-fold LightGBM job — HAND IT TO THE OPERATOR; do not run on
a request path. Output: artifact (model + r + contract) for E2.2/E2.5 to consume, and a CV
results JSON for the E2.6 gate record. Registration of the served signal is E2.5, not here.

Usage (operator):
    uv run python betting_ml/scripts/totals_generative/train_perside_negbin.py
    uv run python betting_ml/scripts/totals_generative/train_perside_negbin.py --no-save
    uv run python betting_ml/scripts/totals_generative/train_perside_negbin.py --min-year 2021
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import gammaln
from scipy.stats import nbinom

warnings.filterwarnings(
    "ignore", message="X does not have valid feature names", category=UserWarning,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection, _numeric_convert
from betting_ml.utils.cv import PurgedWalkForwardSplit
from betting_ml.utils.market_blind import assert_market_blind, find_market_columns

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EXCLUDE_EVAL_YEAR = 2026   # partial season — excluded from CV folds (offense_v2 convention)
_MIN_MU            = 0.30   # NegBin / Poisson require mu > 0; per-side runs floor
_CALIB_80_GATE     = 0.80
_MODEL_VERSION     = "totals_perside_v1"

# Count-natural LightGBM mean (Poisson loss → strictly-positive mu, the canonical count GBM).
# Fixed sensible params — Optuna (≈hours) is deferred; the AC bar is "beat Poisson", and the
# rich matrix clears it comfortably. Re-tune in E2.6 if the derivative gate needs it.
_LGBM_PARAMS = {
    "objective":         "poisson",
    "num_leaves":        31,
    "learning_rate":     0.03,
    "min_child_samples": 40,
    "subsample":         0.85,
    "subsample_freq":    1,
    "colsample_bytree":  0.85,
    "n_estimators":      400,
    "random_state":      42,
    "verbose":           -1,
}

_OUTPUT_DIR   = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / _MODEL_VERSION
_RESULTS_DIR  = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results"
)
_ARTIFACT_S3_URI = f"s3://baseball-betting-ml-artifacts/sub_models/{_MODEL_VERSION}.pkl"

# ---------------------------------------------------------------------------
# Per-side feature inventory (baseball-only; market columns deliberately absent)
#
# Bases are the column names WITHOUT the home_/away_ prefix. For batting side S facing
# opponent O: `off_<b>` = f"{S}_{b}" for OFF_BASES; `opp_<b>` = f"{O}_{b}" for OPP_PITCH_BASES.
# MATCHUP templates carry the opponent explicitly. SHARED_* are used as-is for both sides.
# ---------------------------------------------------------------------------

OFF_BASES: list[str] = [
    # EB lineup rates
    "avg_eb_woba", "avg_eb_woba_sequential", "avg_eb_k_pct", "avg_eb_bb_pct", "avg_eb_iso",
    "avg_eb_woba_uncertainty", "eb_coverage_pct",
    # lineup rolling rates
    "avg_woba_30d", "avg_xwoba_30d", "avg_k_pct_30d", "avg_bb_pct_30d", "avg_hard_hit_pct_30d",
    "avg_barrel_pct_30d", "avg_whiff_rate_30d", "avg_chase_rate_30d",
    "avg_woba_std", "avg_xwoba_std", "avg_k_pct_std", "avg_bb_pct_std",
    "avg_hard_hit_pct_std", "avg_barrel_pct_std",
    # team rolling offence
    "off_runs_per_game_7d", "off_runs_per_game_14d", "off_runs_per_game_30d", "off_runs_per_game_std",
    "off_woba_7d", "off_woba_14d", "off_woba_30d", "off_woba_std",
    "off_xwoba_7d", "off_xwoba_14d", "off_xwoba_30d", "off_xwoba_std",
    "off_k_pct_7d", "off_k_pct_30d", "off_k_pct_std",
    "off_bb_pct_7d", "off_bb_pct_30d", "off_bb_pct_std",
    "off_hard_hit_pct_7d", "off_hard_hit_pct_30d", "off_hard_hit_pct_std",
    "off_barrel_pct_30d", "off_slugging_30d", "off_woba_7d_minus_30d",
    # platoon
    "avg_woba_vs_lhp", "avg_xwoba_vs_lhp", "avg_k_pct_vs_lhp", "avg_bb_pct_vs_lhp", "avg_hard_hit_pct_vs_lhp",
    "avg_woba_vs_rhp", "avg_xwoba_vs_rhp", "avg_k_pct_vs_rhp", "avg_bb_pct_vs_rhp", "avg_hard_hit_pct_vs_rhp",
    "vs_lhp_woba_30d", "vs_lhp_xwoba_30d", "vs_lhp_k_pct_30d", "vs_lhp_bb_pct_30d",
    "vs_lhp_hard_hit_pct_30d", "vs_lhp_slugging_30d", "vs_lhp_woba_std", "vs_lhp_xwoba_std",
    "vs_rhp_woba_30d", "vs_rhp_xwoba_30d", "vs_rhp_k_pct_30d", "vs_rhp_bb_pct_30d",
    "vs_rhp_hard_hit_pct_30d", "vs_rhp_slugging_30d", "vs_rhp_woba_std", "vs_rhp_xwoba_std",
    # situational hitting
    "woba_with_runners_on_30d", "xwoba_with_runners_on_30d", "woba_with_risp_30d",
    "xwoba_with_risp_30d", "runs_per_baserunner_30d",
    # composition
    "lhb_count", "rhb_count", "has_full_lineup", "injured_player_count",
    "injury_adj_avg_woba_30d", "injury_adj_avg_xwoba_30d",
    "n_power_pull", "n_patient_obp", "n_high_whiff", "n_groundball_speed", "n_contact_spray", "n_no_label",
    # bat tracking
    "lineup_avg_bat_speed", "lineup_bat_speed_std", "lineup_avg_swing_length",
    "lineup_avg_attack_angle", "lineup_bat_speed_vs_starter_velo",
    # archetype / cluster matchup vs the pitcher faced
    "lineup_woba_vs_starter_archetype", "lineup_xwoba_vs_starter_archetype",
    "lineup_k_pct_vs_starter_archetype", "lineup_iso_vs_starter_archetype", "lineup_archetype_pa_coverage",
    "lineup_avg_woba_vs_cluster", "lineup_avg_xwoba_vs_cluster", "lineup_cluster_slot_coverage",
    "lineup_archetype_avg_woba", "lineup_archetype_avg_xwoba", "lineup_archetype_slot_coverage",
    # sequential offence + team strength
    "team_sequential_woba", "team_sequential_win_prob", "pythagorean_win_exp", "win_pct",
]

OPP_PITCH_BASES: list[str] = [
    # opposing starter (the pitcher this lineup faces) — quality / form
    "starter_days_rest",
    "starter_k_pct_7d", "starter_bb_pct_7d", "starter_xwoba_against_7d", "starter_hard_hit_pct_7d",
    "starter_barrel_pct_7d", "starter_whiff_rate_7d", "starter_batter_chase_rate_7d", "starter_avg_fastball_velo_7d",
    "starter_k_pct_14d", "starter_bb_pct_14d", "starter_xwoba_against_14d", "starter_hard_hit_pct_14d",
    "starter_barrel_pct_14d", "starter_whiff_rate_14d", "starter_batter_chase_rate_14d", "starter_avg_fastball_velo_14d",
    "starter_k_pct_30d", "starter_bb_pct_30d", "starter_xwoba_against_30d", "starter_hard_hit_pct_30d",
    "starter_barrel_pct_30d", "starter_whiff_rate_30d", "starter_batter_chase_rate_30d", "starter_avg_fastball_velo_30d",
    "starter_k_pct_std", "starter_bb_pct_std", "starter_xwoba_against_std", "starter_hard_hit_pct_std",
    "starter_barrel_pct_std", "starter_whiff_rate_std", "starter_batter_chase_rate_std", "starter_avg_fastball_velo_std",
    "starter_fastball_velo_trend", "starter_velo_delta_3start",
    "starter_k_pct_7d_minus_std", "starter_xwoba_7d_minus_std",
    "starter_appearances_30d", "starter_appearances_std",
    "starter_k_pct_vs_lhb", "starter_bb_pct_vs_lhb", "starter_xwoba_vs_lhb", "starter_whiff_rate_vs_lhb",
    "starter_k_pct_vs_rhb", "starter_bb_pct_vs_rhb", "starter_xwoba_vs_rhb", "starter_whiff_rate_vs_rhb",
    "starter_avg_ip_last_3", "starter_avg_ip_season",
    "starter_stuff_plus", "starter_fastball_pct", "starter_breaking_pct", "starter_offspeed_pct",
    "starter_fastball_stuff_plus", "starter_slider_stuff_plus", "starter_curveball_stuff_plus",
    "starter_changeup_stuff_plus", "starter_avg_fastball_velo",
    "starter_proj_fip", "starter_proj_xfip", "starter_trailing_fip_30g", "starter_trailing_ra9_30g", "starter_fip_ra9_gap",
    "starter_csw_pct_3start", "starter_csw_pct_season",
    "starter_fastball_pct_drift_5start", "starter_breaking_pct_drift_5start", "starter_offspeed_pct_drift_5start",
    "starter_eb_xwoba_against", "starter_eb_xwoba_against_sequential", "starter_eb_k_pct", "starter_eb_bb_pct",
    "starter_eb_xwoba_uncertainty", "starter_cluster_id",
    # opposing bullpen — quality
    "bp_k_pct_14d", "bp_bb_pct_14d", "bp_xwoba_against_14d", "bp_hard_hit_pct_14d", "bp_whiff_rate_14d", "bp_innings_pitched_14d",
    "bp_k_pct_30d", "bp_bb_pct_30d", "bp_xwoba_against_30d", "bp_hard_hit_pct_30d", "bp_whiff_rate_30d", "bp_innings_pitched_30d",
    "bp_eb_xwoba", "bp_eb_uncertainty", "bp_eb_coverage_pct", "bp_matchup_xwoba",
    # opposing bullpen — pen-state / availability (deepened further in E2.1b)
    "bullpen_pitches_prev_1d", "bullpen_pitches_prev_3d", "bullpen_pitches_prev_7d",
    "pitchers_used_prev_2d", "pitchers_used_prev_3d", "pitchers_used_prev_7d",
    "reliever_appearances_prev_3d", "reliever_appearances_prev_7d",
    "high_leverage_used_prev_2d", "closer_used_prev_1d", "closer_used_prev_2d",
    "bullpen_ip_prev_1d", "bullpen_ip_prev_2d",
    "bp_leverage_sum_1d", "bp_leverage_sum_3d", "bp_high_lev_appearances_3d",
    # opposing pitching staff — rolling
    "pit_runs_allowed_7d", "pit_runs_allowed_14d", "pit_runs_allowed_30d", "pit_runs_allowed_std",
    "pit_woba_against_7d", "pit_woba_against_14d", "pit_woba_against_30d", "pit_woba_against_std",
    "pit_xwoba_against_7d", "pit_xwoba_against_14d", "pit_xwoba_against_30d", "pit_xwoba_against_std",
    "pit_k_pct_7d", "pit_k_pct_30d", "pit_k_pct_std", "pit_bb_pct_7d", "pit_bb_pct_30d", "pit_bb_pct_std",
    "pit_hard_hit_pct_7d", "pit_hard_hit_pct_30d", "pit_hard_hit_pct_std", "pit_barrel_pct_30d", "pit_xwoba_7d_minus_30d",
    "woba_against_with_runners_on_30d", "woba_against_with_risp_30d",
    # opposing catcher (run-suppression) + sequential pitching + team defence
    "catcher_framing_runs", "catcher_defensive_runs",
    "team_sequential_bullpen_xwoba", "team_oaa_prior_season", "team_oaa_blended",
]

# Side-directional matchup features: f"{S}_lineup_vs_{O}_starter_<m>" → off_lineup_vs_opp_starter_<m>
MATCHUP_TEMPLATES: list[tuple[str, str]] = [
    ("off_lineup_vs_opp_starter_xwoba_adj",  "{s}_lineup_vs_{o}_starter_xwoba_adj"),
    ("off_lineup_vs_opp_starter_k_pct_adj",  "{s}_lineup_vs_{o}_starter_k_pct_adj"),
    ("off_lineup_vs_opp_starter_bb_pct_adj", "{s}_lineup_vs_{o}_starter_bb_pct_adj"),
    ("off_lineup_vs_opp_starter_h2h_woba",   "{s}_lineup_vs_{o}_starter_h2h_woba"),
    ("off_lineup_vs_opp_starter_h2h_xwoba",  "{s}_lineup_vs_{o}_starter_h2h_xwoba"),
    ("off_lineup_h2h_pa_coverage",           "{s}_lineup_h2h_pa_coverage"),
]

# Categorical bases (OHE). off_ = the pitcher-archetype faced + own batter cluster mode;
# opp_ = the faced starter's hand / archetype / primary pitch.
OFF_CAT_BASES: list[str] = ["starter_pitch_archetype", "batter_cluster_mode"]
OPP_CAT_BASES: list[str] = ["starter_pitcher_hand", "starter_pitcher_archetype", "starter_primary_pitch_type"]

# Shared game context (used as-is for both sides; no prefix in the wide mart).
SHARED_NUMERIC: list[str] = [
    "elevation_ft", "left_line_ft", "left_ft", "left_center_ft", "center_ft",
    "right_center_ft", "right_line_ft", "runs_per_game_at_park", "park_run_factor_3yr",
    "temp_f", "wind_speed_mph", "wind_direction_deg", "wind_component_mph", "humidity_pct",
    "ump_k_pct_zscore", "ump_bb_pct_zscore", "ump_runs_per_game_zscore",
    "ump_run_impact_zscore", "ump_accuracy_zscore", "ump_games_sample",
    "series_game_number",
]
SHARED_BOOL: list[str] = ["is_day_game", "is_dome", "post_2022_rules", "is_new_venue"]
SHARED_CAT: list[str] = ["roof_type", "turf_type"]

_TARGET = "runs_scored"


# ---------------------------------------------------------------------------
# Data loading + per-side assembly
# ---------------------------------------------------------------------------

def _wide_query(min_year: int) -> str:
    return f"""
    SELECT f.*, r.home_final_score, r.away_final_score
    FROM baseball_data.betting_features.feature_pregame_game_features f
    JOIN baseball_data.betting.mart_game_results r USING (game_pk)
    WHERE f.has_full_data = TRUE
      AND r.game_type = 'R'
      AND r.home_final_score IS NOT NULL
      AND f.game_year >= {int(min_year)}
    """


def load_wide_lakehouse(min_year: int) -> pd.DataFrame:
    """Load the wide per-game mart from the **S3 lakehouse via DuckDB** (E2.1-r).

    Snowflake-FREE (CLAUDE.md §0.5 post-E11.1: a Snowflake pull for training data is a RED
    FLAG — `feature_pregame_game_features` and `mart_game_results` both live as S3 parquet).
    Needs AWS creds only (DuckDB `credential_chain`) + `AWS_DEFAULT_REGION=us-east-2`.
    """
    from scripts.utils.lakehouse_read import (
        duck_connect,
        referenced_tables,
        register_views,
        strip_fqn,
    )

    sql = _wide_query(min_year)
    conn = duck_connect()
    register_views(conn, referenced_tables(sql))
    df = conn.execute(strip_fqn(sql)).fetch_df()
    df.columns = [c.lower() for c in df.columns]
    return _numeric_convert(df)


def load_wide(min_year: int, *, source: str = "lakehouse") -> pd.DataFrame:
    """Load the wide per-game feature mart + both final scores (regular season, full data).

    `source="lakehouse"` (DEFAULT) reads S3 parquet via DuckDB. `source="snowflake"` is the
    legacy path, retained only for a parity spot-check — it is NOT the sanctioned route.
    """
    if source == "lakehouse":
        return load_wide_lakehouse(min_year)
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_wide_query(min_year))
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    return _numeric_convert(df)


def _present(bases: list[str], wide_cols: set[str]) -> list[str]:
    """Keep only bases present as BOTH home_<b> and away_<b> in the wide mart."""
    keep, missing = [], []
    for b in bases:
        if f"home_{b}" in wide_cols and f"away_{b}" in wide_cols:
            keep.append(b)
        else:
            missing.append(b)
    if missing:
        print(f"  [skip] {len(missing)} base(s) absent from mart (both sides): {missing}")
    return keep


def build_perside_frame(wide: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Unpivot the wide per-game mart into one row per (game_pk, side).

    Returns (df, numeric_feature_cols, categorical_feature_cols). `df` is sorted by date and
    reset_index(drop=True) so PurgedWalkForwardSplit's positional indices are valid.
    """
    wide = wide.copy()
    wide.columns = [c.lower() for c in wide.columns]
    cols = set(wide.columns)

    off_bases   = _present(OFF_BASES, cols)
    opp_bases   = _present(OPP_PITCH_BASES, cols)
    off_cats    = _present(OFF_CAT_BASES, cols)
    opp_cats    = _present(OPP_CAT_BASES, cols)
    shared_num  = [c for c in SHARED_NUMERIC if c in cols]
    shared_bool = [c for c in SHARED_BOOL if c in cols]
    shared_cat  = [c for c in SHARED_CAT if c in cols]
    matchups    = [(name, tpl) for name, tpl in MATCHUP_TEMPLATES
                   if tpl.format(s="home", o="away") in cols and tpl.format(s="away", o="home") in cols]

    id_cols = ["game_pk", "game_date", "game_year"]
    frames: list[pd.DataFrame] = []
    for side, opp in (("home", "away"), ("away", "home")):
        # Build the whole side-frame from a single {dest: source-series} map, then one concat —
        # avoids the column-by-column insert that fragments a ~280-col frame (PerformanceWarning).
        src: dict[str, pd.Series] = {
            "game_pk":   wide["game_pk"],
            "game_date": wide["game_date"],
            "game_year": wide["game_year"],
            "side":      pd.Series(side, index=wide.index),
            "is_home":   pd.Series(1.0 if side == "home" else 0.0, index=wide.index),
            _TARGET:     wide[f"{side}_final_score"],
        }
        # offence (batting side) → off_<base>
        for b in off_bases + off_cats:
            src[f"off_{b}"] = wide[f"{side}_{b}"]
        # opposing pitching → opp_<base>
        for b in opp_bases + opp_cats:
            src[f"opp_{b}"] = wide[f"{opp}_{b}"]
        # directional matchups
        for name, tpl in matchups:
            src[name] = wide[tpl.format(s=side, o=opp)]
        # shared context (identical for both sides)
        for c in shared_num + shared_cat:
            src[c] = wide[c]
        for c in shared_bool:
            src[c] = wide[c].astype(float)
        frames.append(pd.DataFrame(src, copy=False))

    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values(["game_date", "game_pk", "side"]).reset_index(drop=True)

    numeric_cols = (
        ["is_home"]
        + [f"off_{b}" for b in off_bases]
        + [f"opp_{b}" for b in opp_bases]
        + [name for name, _ in matchups]
        + shared_num + shared_bool
    )
    cat_cols = (
        [f"off_{b}" for b in off_cats]
        + [f"opp_{b}" for b in opp_cats]
        + shared_cat
    )
    # Coerce numerics (Snowflake Decimals / bool already handled), drop the target out of
    # features. The `.astype("float64")` is load-bearing, not cosmetic: the DuckDB/lakehouse
    # read (E2.1-r) returns integer columns as pandas NULLABLE Int64, and a nullable-int column
    # rejects a float mean in `_prepare_matrix`'s fillna ("Invalid value ... for dtype Int64").
    # Pinning float64 here makes the Snowflake and lakehouse paths dtype-identical.
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    df[_TARGET] = pd.to_numeric(df[_TARGET], errors="coerce").astype("float64")
    df = df[df[_TARGET].notna()].reset_index(drop=True)
    _ = id_cols  # retained for clarity
    return df, numeric_cols, cat_cols


# ---------------------------------------------------------------------------
# Matrix prep (impute + OHE), mirroring the offense_v1/v2 fold pattern
# ---------------------------------------------------------------------------

def _impute_means(train: pd.DataFrame, numeric_cols: list[str]) -> dict[str, float]:
    means: dict[str, float] = {}
    for c in numeric_cols:
        m = train[c].mean()
        means[c] = float(m) if pd.notna(m) else 0.0
    return means


def _prepare_matrix(
    train: pd.DataFrame,
    eval_: pd.DataFrame,
    numeric_cols: list[str],
    cat_cols: list[str],
    impute_means: dict[str, float],
    ohe_columns: list[str] | None,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Impute numerics to train means and OHE every categorical; align eval to train columns.

    If `ohe_columns` is None it is learned from `train` (CV / final-fit); otherwise eval is
    reindexed to the supplied column order (serve-time parity).
    """
    tr = train.copy()
    ev = eval_.copy()
    for c, v in impute_means.items():
        tr[c] = tr[c].fillna(v)
        ev[c] = ev[c].fillna(v)

    tr_dummies, ev_dummies = [], []
    for c in cat_cols:
        td = pd.get_dummies(tr[c].astype("object").fillna("__NA__"), prefix=c, dtype=float)
        ed = pd.get_dummies(ev[c].astype("object").fillna("__NA__"), prefix=c, dtype=float)
        tr_dummies.append(td)
        ev_dummies.append(ed)
    tr_ohe = pd.concat(tr_dummies, axis=1) if tr_dummies else pd.DataFrame(index=tr.index)
    ev_ohe = pd.concat(ev_dummies, axis=1) if ev_dummies else pd.DataFrame(index=ev.index)

    if ohe_columns is None:
        ohe_columns = sorted(tr_ohe.columns.tolist())
    tr_ohe = tr_ohe.reindex(columns=ohe_columns, fill_value=0.0)
    ev_ohe = ev_ohe.reindex(columns=ohe_columns, fill_value=0.0)

    feat_cols = numeric_cols + ohe_columns
    X_tr = np.concatenate([tr[numeric_cols].to_numpy(float), tr_ohe.to_numpy(float)], axis=1)
    X_ev = np.concatenate([ev[numeric_cols].to_numpy(float), ev_ohe.to_numpy(float)], axis=1)
    return X_tr, X_ev, feat_cols


# ---------------------------------------------------------------------------
# Likelihood helpers (Poisson + NegBin)
# ---------------------------------------------------------------------------

def poisson_nll(y: np.ndarray, mu: np.ndarray) -> float:
    """Mean Poisson NLL. Baseline: assumes var = mean (no overdispersion)."""
    mu = np.clip(mu, _MIN_MU, None)
    ll = y * np.log(mu) - mu - gammaln(y + 1.0)
    return float(-np.mean(ll))


def negbin_nll(y: np.ndarray, mu: np.ndarray, r: float) -> float:
    """Mean NegBin(mu, r) NLL. r = dispersion; var = mu + mu^2/r ≥ mu."""
    mu = np.clip(mu, _MIN_MU, None)
    p = r / (r + mu)
    ll = (
        gammaln(y + r) - gammaln(r) - gammaln(y + 1.0)
        + r * np.log(p) + y * np.log(1.0 - p + 1e-12)
    )
    return float(-np.mean(ll))


def fit_negbin_r(y: np.ndarray, mu: np.ndarray) -> float:
    """MLE of the NegBin dispersion r given observations y and predicted means mu."""
    mu = np.clip(mu, _MIN_MU, None)
    res = minimize_scalar(
        lambda log_r: negbin_nll(y, mu, float(np.exp(log_r))),
        bounds=(np.log(0.1), np.log(500)), method="bounded",
    )
    return float(np.exp(res.x))


def calib_80(y: np.ndarray, mu: np.ndarray, r: float) -> float:
    mu = np.clip(mu, _MIN_MU, None)
    p = r / (r + mu)
    lo = nbinom.ppf(0.10, n=r, p=p)
    hi = nbinom.ppf(0.90, n=r, p=p)
    return float(np.mean((y >= lo) & (y <= hi)))


def _fit_lgbm(X: np.ndarray, y: np.ndarray):
    import lightgbm as lgb
    model = lgb.LGBMRegressor(**_LGBM_PARAMS)
    model.fit(X, y)
    return model


# ---------------------------------------------------------------------------
# Purged-CV evaluation: NegBin vs Poisson baseline
# ---------------------------------------------------------------------------

def run_cv(
    df: pd.DataFrame,
    numeric_cols: list[str],
    cat_cols: list[str],
) -> dict:
    """Walk-forward purged CV. Per fold: fit Poisson-loss mean, score Poisson vs NegBin NLL."""
    splitter = PurgedWalkForwardSplit(min_train_seasons=3)
    # purge band is sized from the rolling-window suffixes that survive renaming (_7d/_30d…)
    folds = list(splitter.split(df, feature_cols=numeric_cols))
    stats = {s.eval_year: s for s in splitter.last_stats}

    fold_records: list[dict] = []
    print(f"\n── Purged walk-forward CV ({_MODEL_VERSION}) ─────────────────────────")
    print(f"  {'Eval':>6}  {'N_tr':>7}  {'N_ev':>6}  {'Pois_NLL':>9}  {'NB_NLL':>8}  "
          f"{'Δ(P-NB)':>8}  {'calib80':>8}  {'r':>7}  {'MAE':>6}  {'purged':>7}")

    for train_idx, eval_idx in folds:
        eval_year = int(df.loc[eval_idx, "game_year"].mode().iloc[0])
        if eval_year == _EXCLUDE_EVAL_YEAR:
            continue
        tr, ev = df.loc[train_idx], df.loc[eval_idx]
        means = _impute_means(tr, numeric_cols)
        X_tr, X_ev, _ = _prepare_matrix(tr, ev, numeric_cols, cat_cols, means, None)
        y_tr = tr[_TARGET].to_numpy(float)
        y_ev = ev[_TARGET].to_numpy(float)

        model = _fit_lgbm(X_tr, y_tr)
        mu_tr = np.clip(model.predict(X_tr), _MIN_MU, None)
        mu_ev = np.clip(model.predict(X_ev), _MIN_MU, None)
        r = fit_negbin_r(y_tr, mu_tr)            # dispersion fit on TRAIN only (no eval leak)

        p_nll = poisson_nll(y_ev, mu_ev)
        nb_nll = negbin_nll(y_ev, mu_ev, r)
        c80 = calib_80(y_ev, mu_ev, r)
        mae = float(np.mean(np.abs(mu_ev - y_ev)))
        std_p = float(np.std(mu_ev))
        frac_purged = stats[eval_year].frac_dropped if eval_year in stats else 0.0

        print(f"  {eval_year:>6}  {len(y_tr):>7,}  {len(y_ev):>6,}  {p_nll:>9.4f}  {nb_nll:>8.4f}  "
              f"{p_nll - nb_nll:>+8.4f}  {c80:>8.3f}  {r:>7.3f}  {mae:>6.3f}  {frac_purged:>6.1%}")
        fold_records.append({
            "eval_year": eval_year, "n_train": int(len(y_tr)), "n_eval": int(len(y_ev)),
            "poisson_nll": round(p_nll, 4), "negbin_nll": round(nb_nll, 4),
            "nll_gain": round(p_nll - nb_nll, 4), "calib_80": round(c80, 3),
            "negbin_r": round(r, 3), "mae": round(mae, 4), "std_pred": round(std_p, 4),
            "frac_purged": round(frac_purged, 4),
        })

    mean_p   = float(np.mean([r["poisson_nll"] for r in fold_records]))
    mean_nb  = float(np.mean([r["negbin_nll"] for r in fold_records]))
    mean_c80 = float(np.mean([r["calib_80"] for r in fold_records]))
    mean_r   = float(np.mean([r["negbin_r"] for r in fold_records]))
    n_wins   = sum(r["negbin_nll"] < r["poisson_nll"] for r in fold_records)

    print(f"\n  Mean Poisson NLL: {mean_p:.4f}   Mean NegBin NLL: {mean_nb:.4f}   "
          f"gain: {mean_p - mean_nb:+.4f}")
    print(f"  NegBin beats Poisson on {n_wins}/{len(fold_records)} folds   "
          f"mean calib_80: {mean_c80:.3f}   mean r: {mean_r:.3f}")
    return {
        "folds": fold_records,
        "mean_poisson_nll": round(mean_p, 4),
        "mean_negbin_nll": round(mean_nb, 4),
        "mean_nll_gain": round(mean_p - mean_nb, 4),
        "mean_calib_80": round(mean_c80, 3),
        "mean_negbin_r": round(mean_r, 3),
        "folds_negbin_wins": n_wins,
        "n_folds": len(fold_records),
    }


# ---------------------------------------------------------------------------
# Final fit + artifact
# ---------------------------------------------------------------------------

def fit_final(df: pd.DataFrame, numeric_cols: list[str], cat_cols: list[str]) -> dict:
    train = df[df["game_year"] != _EXCLUDE_EVAL_YEAR].reset_index(drop=True)
    means = _impute_means(train, numeric_cols)
    X, _, feat_cols = _prepare_matrix(train, train, numeric_cols, cat_cols, means, None)
    y = train[_TARGET].to_numpy(float)
    model = _fit_lgbm(X, y)
    mu = np.clip(model.predict(X), _MIN_MU, None)
    r = fit_negbin_r(y, mu)
    ohe_columns = feat_cols[len(numeric_cols):]

    var_mean = 1.0 + float(np.mean(mu)) / r   # implied var/mean at the mean prediction
    print(f"\n── Final fit on complete seasons (n={len(y):,}) ───────────────────────")
    print(f"  fitted NegBin r: {r:.4f}   implied var/mean at μ̄: {var_mean:.3f}   "
          f"in-sample NegBin NLL: {negbin_nll(y, mu, r):.4f}")

    return {
        "model": model,
        "model_type": "lgbm_poisson_negbin",
        "negbin_r": r,
        "numeric_cols": numeric_cols,
        "cat_cols": cat_cols,
        "ohe_columns": ohe_columns,
        "feature_names": feat_cols,
        "impute_means": means,
        "min_mu": _MIN_MU,
        "target_mean": float(y.mean()),
        "target_std": float(y.std()),
        "implied_var_mean": var_mean,
        "lgbm_params": _LGBM_PARAMS,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Story E2.1 — per-side NegBin runs model")
    ap.add_argument("--min-year", type=int, default=2018,
                    help="Earliest season to load (default 2018 → 5 clean Statcast-era eval folds "
                         "2021-2025). Pre-2021 sequential posteriors + pre-2023 bat-tracking are "
                         "NULL and impute to the train mean (a constant, not leakage); narrow to "
                         "--min-year 2021 for the sequential-complete era (fewer folds).")
    ap.add_argument("--no-save", action="store_true", help="Skip artifact/results write.")
    args = ap.parse_args()

    print("=== STORY E2.1 — PER-SIDE COUNT-DISTRIBUTION MODEL (market-blind) ===")
    print("Loading wide per-game mart from Snowflake ...")
    wide = load_wide(args.min_year)
    print(f"  {len(wide):,} games, seasons {int(wide['game_year'].min())}–{int(wide['game_year'].max())}")

    df, numeric_cols, cat_cols = build_perside_frame(wide)
    print(f"  Per-side rows: {len(df):,}  |  {len(numeric_cols)} numeric + {len(cat_cols)} categorical bases")

    # ── CONTRACT-GUARD: no market/odds columns may reach the matrix ──
    all_feature_cols = numeric_cols + cat_cols
    leaks = find_market_columns(all_feature_cols)
    assert_market_blind(all_feature_cols, context=f"{_MODEL_VERSION} feature matrix")
    print(f"  CONTRACT-GUARD: market-blind ✅  (0 market columns among {len(all_feature_cols)} features)")
    assert not leaks

    results = run_cv(df, numeric_cols, cat_cols)

    # ── Gate / AC ──
    beats_poisson = results["mean_negbin_nll"] < results["mean_poisson_nll"]
    overdispersed = results["mean_negbin_r"] < 500.0 and results["mean_nll_gain"] > 0
    print("\n" + "=" * 72)
    print("E2.1 GATE")
    print("=" * 72)
    print(f"  NegBin beats Poisson on per-side-runs NLL : {'✅' if beats_poisson else '❌'} "
          f"({results['mean_negbin_nll']:.4f} < {results['mean_poisson_nll']:.4f}, "
          f"gain {results['mean_nll_gain']:+.4f}, {results['folds_negbin_wins']}/{results['n_folds']} folds)")
    print(f"  Overdispersion recovered (var/mean > 1)   : {'✅' if overdispersed else '❌'} "
          f"(mean r {results['mean_negbin_r']:.3f})")
    print(f"  Market-leakage guard passes               : ✅")
    gate_pass = beats_poisson and overdispersed

    if args.no_save:
        print("\n[--no-save] Skipping artifact + results write.")
        return

    artifact = fit_final(df, numeric_cols, cat_cols)
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    import joblib
    artifact_path = _OUTPUT_DIR / f"{_MODEL_VERSION}.pkl"
    joblib.dump(artifact, artifact_path)
    print(f"\nArtifact → {artifact_path.relative_to(_PROJECT_ROOT)}")

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results_doc = {
        "story": "E2.1",
        "model_version": _MODEL_VERSION,
        "trained_at": date.today().isoformat(),
        "min_year": args.min_year,
        "n_perside_rows": int(len(df)),
        "n_numeric_features": len(numeric_cols),
        "n_categorical_features": len(cat_cols),
        "cv": results,
        "gate": {
            "negbin_beats_poisson": beats_poisson,
            "overdispersion_recovered": overdispersed,
            "market_blind": True,
            "pass": gate_pass,
        },
        "final_negbin_r": round(artifact["negbin_r"], 4),
        "final_implied_var_mean": round(artifact["implied_var_mean"], 4),
    }
    results_path = _RESULTS_DIR / f"e2_1_perside_negbin_cv.json"
    results_path.write_text(json.dumps(results_doc, indent=2))
    print(f"Results → {results_path.relative_to(_PROJECT_ROOT)}")
    print(f"\nE2.1 GATE: {'PASS ✅' if gate_pass else 'FAIL ❌'}")
    print("Next: E2.2 fits the Gaussian copula over this NegBin marginal; E2.5 registers + "
          "leakage-safe-backfills the served signal. Artifact NOT promoted to S3 (gated at E2.6).")


if __name__ == "__main__":
    main()
