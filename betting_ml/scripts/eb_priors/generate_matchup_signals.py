"""
generate_matchup_signals.py — Epic 8, Story 8.3 / 8.5

Loads the matchup_v1 champion artifact (Ridge raw, alpha=0.2873) and archetype
posterior soft assignments, scores every regular-season game-side in 2021+, and
writes 7 signals per game-side to mart_sub_model_signals via the SCD-2 writer.

Grain: (game_pk, side) — two rows per game.
  side='home': home lineup batters facing away probable starter
  side='away': away lineup batters facing home probable starter

Signals per game-side:
    matchup_advantage_mu          — soft-mixture xwOBA interaction residual (vs. EB additive pred)
    matchup_advantage_sigma       — predictive uncertainty from the soft archetype mixture
    matchup_volatility_signal     — Shannon entropy of joint P(batter_arch)×P(pitcher_arch)
    matchup_soft_vs_hard_delta    — diagnostic: soft mu − MAP-cell mu
    matchup_k_pressure_signal     — soft-weighted expected K% across cells
    matchup_power_signal          — soft-weighted expected hard-hit% across cells
    matchup_cell_posterior_source — 2.0=sequential_current_season, 1.0=historical_eb, 0.0=marginals_only

Story 8.5 integration:
    When matchup_cell_sequential_posteriors has is_current=True rows for the current
    season, those posterior_mu / posterior_sigma values replace the Ridge model's
    static cell predictions for the soft mixture. The cell_posterior_source signal
    records which path was taken.

signal_available = True when:
  - Probable starter posterior exists with pa_count >= _MIN_PITCHER_PA
  - >= _MIN_LINEUP_SLOTS batter posteriors exist (pa_count >= 1) in the lineup

Usage:
    # Backfill 2021-2026
    uv run python betting_ml/scripts/eb_priors/generate_matchup_signals.py --backfill

    # Single date (daily scoring)
    uv run python betting_ml/scripts/eb_priors/generate_matchup_signals.py --date 2026-06-02

    # Dry-run (compute without writing to Snowflake)
    uv run python betting_ml/scripts/eb_priors/generate_matchup_signals.py --backfill --dry-run
    uv run python betting_ml/scripts/eb_priors/generate_matchup_signals.py --date 2024-05-01 --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.artifact_store import load_artifact
from betting_ml.scripts.scd2_writer import scd2_upsert, _SCHEMA_PROD, _SCHEMA_DEV

# ── Artifact / model constants ─────────────────────────────────────────────────

_ARTIFACT_S3_URI = "s3://baseball-betting-ml-artifacts/sub_models/matchup_v1.pkl"
_ARTIFACT_LOCAL  = _PROJECT_ROOT / "betting_ml" / "models" / "matchup_v1" / "matchup_v1.pkl"
_EB_PRIORS_PATH  = _PROJECT_ROOT / "betting_ml" / "models" / "eb_priors" / "matchup_cell_priors.json"

_SUB_MODEL_NAME    = "matchup_v1"
_SUB_MODEL_VERSION = "v1"
_TRAINING_START    = "2021-01-01"

# Archetype category ordering — must match train_matchup_v1.py exactly
_BATTER_CATS  = ["contact_spray", "groundball_speed", "high_whiff", "patient_obp", "power_pull"]
_PITCHER_CATS = ["changeup_deceptive", "contact_sinker_ball", "multi_pitch_mix",
                 "power_swing_and_miss", "soft_command"]
_N_B = len(_BATTER_CATS)
_N_P = len(_PITCHER_CATS)

_UNIFORM_BATTER  = np.ones(_N_B) / _N_B
_UNIFORM_PITCHER = np.ones(_N_P) / _N_P

# Season normalization bounds — from train_matchup_v1.py
_SEASON_MIN = 2021
_SEASON_MAX = 2025

# signal_available gates
_MIN_PITCHER_PA  = 10  # pa_count required in pitcher posterior
_MIN_LINEUP_SLOTS = 6  # lineup slots that need at least 1 PA in posterior

# Sparse PA fallbacks used when a cell has no data in the prior season
_FALLBACK_K_PCT       = 0.224
_FALLBACK_BB_PCT      = 0.082
_FALLBACK_HARD_HIT_PCT = 0.375

# cell_posterior_source numeric encoding (emitted as signal_value)
_SOURCE_MARGINALS_ONLY  = 0.0   # no posterior data; uniform priors
_SOURCE_HISTORICAL_EB   = 1.0   # Ridge model static cell means (no sequential update yet)
_SOURCE_SEQUENTIAL      = 2.0   # sequential current-season posteriors from Story 8.5

# ── E11.1-W7a lakehouse: read-on-DuckDB ───────────────────────────────────────
# `--s3` repoints the matchup-signal SOURCE reads (the cell-feature substrate, the games
# spine, and the archetype posteriors) at S3 parquet via DuckDB so the operator can stop
# running the Snowflake builds of batter_clusters/pitcher_clusters/mart_player_archetype_posteriors.
# The WRITES stay on Snowflake: the matchup_cell_sequential_posteriors read (_load_seq_cell_posteriors)
# and the SCD-2 write to mart_sub_model_signals are UNCHANGED — so in --s3 mode the script holds
# BOTH a DuckDB connection (S3 reads) and a Snowflake connection (seq-posteriors read + final write).
_S3_BUCKET = "baseball-betting-ml-artifacts"
_LAKEHOUSE = f"s3://{_S3_BUCKET}/baseball/lakehouse"

# Source tables this script reads (all repointed to S3 in --s3 mode). union_by_name=true with the
# **/*.parquet glob matches both partitioned layouts and single-file data.parquet layouts.
# E11.1-W7a: ONLY the source tables that actually exist in the S3 lakehouse get a DuckDB view.
# `stg_statsapi_probable_pitchers` + `stg_statsapi_lineups_wide` are NOT migrated (Snowflake-only
# staging — verified via `aws s3 ls .../lakehouse/`; only `stg_statsapi_lineups`, the long flatten,
# is in S3). They're read ONLY by _GAMES_SQL → which stays on Snowflake in --s3 mode (see run()).
# This does NOT keep any dual-write builder alive: the credit-drop tables (batter_clusters,
# pitcher_clusters, mart_player_archetype_posteriors) are all here and read off S3 below.
_S3_SOURCE_TABLES = [
    "mart_pitch_play_event",
    "stg_batter_pitches",
    "mart_batter_archetype_vs_pitcher_cluster",
    "batter_clusters",
    "pitcher_clusters",
    "mart_player_archetype_posteriors",
]


def _get_duckdb():
    import duckdb
    duck = duckdb.connect()
    duck.execute("INSTALL httpfs; LOAD httpfs")
    duck.execute(
        "CREATE OR REPLACE SECRET baseball_s3 "
        "(TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')"
    )
    for _p in ("SET http_timeout=600000", "SET http_retries=8",
               "SET preserve_insertion_order=false"):
        try:
            duck.execute(_p)
        except Exception:
            pass
    return duck


def _register_s3_views(duck) -> None:
    """Register every source table this script reads as a DuckDB view under its bare Snowflake
    name, so _duck_sql_for's table-name rewrite resolves."""
    for name in _S3_SOURCE_TABLES:
        glob = f"{_LAKEHOUSE}/{name}/**/*.parquet"
        duck.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_parquet('{glob}', union_by_name=true)"
        )


def _duck_sql_for(sql: str) -> str:
    """Rewrite a Snowflake matchup-source query to its DuckDB equivalent: point the
    fully-qualified tables at the registered bare-name views, translate Snowflake-only SQL
    (YEAR(), CURRENT_DATE()), and cast the VARCHAR parquet game_date to DATE wherever it
    crosses an engine type boundary (date comparisons in _GAMES_SQL)."""
    import re
    s = sql
    s = s.replace("baseball_data.betting.mart_pitch_play_event", "mart_pitch_play_event")
    s = s.replace("baseball_data.betting.stg_batter_pitches", "stg_batter_pitches")
    s = s.replace("baseball_data.betting.mart_batter_archetype_vs_pitcher_cluster",
                  "mart_batter_archetype_vs_pitcher_cluster")
    s = s.replace("baseball_data.statsapi.batter_clusters", "batter_clusters")
    s = s.replace("baseball_data.statsapi.pitcher_clusters", "pitcher_clusters")
    s = s.replace("baseball_data.betting.mart_game_results", "mart_game_results")
    s = s.replace("baseball_data.betting.stg_statsapi_probable_pitchers",
                  "stg_statsapi_probable_pitchers")
    s = s.replace("baseball_data.betting.stg_statsapi_lineups_wide", "stg_statsapi_lineups_wide")
    s = s.replace("baseball_data.betting.mart_player_archetype_posteriors",
                  "mart_player_archetype_posteriors")
    s = s.replace("CURRENT_DATE()", "current_date")
    # YEAR(game_date) → year(game_date::date): parquet game_date is VARCHAR.
    s = re.sub(r"YEAR\(\s*game_date\s*\)", "year(game_date::date)", s)
    # _GAMES_SQL date-range filter compares g.game_date (VARCHAR in parquet) to literal dates.
    s = re.sub(r"g\.game_date\s*>=", "g.game_date::date >=", s)
    s = re.sub(r"g\.game_date\s*<=", "g.game_date::date <=", s)
    return s


def _fetch_duck(duck, sql: str) -> list[dict]:
    cur = duck.execute(sql)
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


_SEQ_POSTERIORS_TABLE = "baseball_data.betting.matchup_cell_sequential_posteriors"

_SEQ_POSTERIORS_SQL = """
SELECT
    batter_archetype,
    pitcher_archetype,
    posterior_mu,
    posterior_sigma,
    n_pa_cumulative
FROM {table}
WHERE is_current = TRUE
  AND season = %(season)s
"""


def _load_seq_cell_posteriors(conn, season: int) -> dict[tuple[str, str], dict]:
    """
    Return {(batter_arch, pitcher_arch): {posterior_mu, posterior_sigma, n_pa_cumulative}}
    for the current season. Empty dict if the table doesn't exist or has no rows.
    """
    try:
        cur = conn.cursor()
        cur.execute(
            _SEQ_POSTERIORS_SQL.format(table=_SEQ_POSTERIORS_TABLE),
            {"season": season},
        )
        cols = [d[0].lower() for d in cur.description]
        rows = {
            (r[0], r[1]): dict(zip(cols, r))
            for r in cur.fetchall()
        }
        cur.close()
        return rows
    except Exception:
        # Table doesn't exist yet (before 8.5 runs for the first time)
        return {}


# ── Schema resolution ──────────────────────────────────────────────────────────

def _resolve_tables(env: str) -> tuple[str, str]:
    schema = _SCHEMA_PROD if env == "prod" else _SCHEMA_DEV
    return f"{schema}.mart_sub_model_signals", f"{schema}.tmp_scd2_incoming"


# ── Core mixture computation (law of total variance) ─────────────────────────

def compute_matchup_signal_soft(
    batter_probs: np.ndarray,   # shape (9, K_b) — one row per lineup slot
    pitcher_probs: np.ndarray,  # shape (K_p,)
    cell_means: np.ndarray,     # shape (K_b, K_p) — predicted interaction residual
    cell_sigmas: np.ndarray,    # shape (K_b, K_p) — per-cell predictive uncertainty
) -> tuple[float, float]:
    """
    Returns (matchup_advantage_mu, matchup_advantage_sigma) as a mixture
    over all archetype combinations weighted by joint probability.
    sigma uses the law of total variance:
      Var[X] = E[Var[X|cell]] + Var[E[X|cell]]
    A batter with high archetype uncertainty produces higher sigma
    even if the cell means are identical.
    """
    avg_batter_probs = batter_probs.mean(axis=0)                   # (K_b,)
    joint_probs      = np.outer(avg_batter_probs, pitcher_probs)   # (K_b, K_p)
    mu               = float((joint_probs * cell_means).sum())
    expected_cell_var      = float((joint_probs * cell_sigmas ** 2).sum())
    variance_of_cell_means = float((joint_probs * (cell_means - mu) ** 2).sum())
    sigma = float(np.sqrt(max(expected_cell_var + variance_of_cell_means, 1e-10)))
    return mu, sigma


def _joint_entropy(batter_probs: np.ndarray, pitcher_probs: np.ndarray) -> float:
    """Shannon entropy of joint P(batter_arch) × P(pitcher_arch) distribution."""
    avg_b = batter_probs.mean(axis=0)           # (K_b,)
    joint = np.outer(avg_b, pitcher_probs).ravel()
    joint = joint[joint > 0]
    return float(-np.sum(joint * np.log(joint)))


# ── Artifact loading ───────────────────────────────────────────────────────────

def _load_artifacts() -> tuple[dict, dict]:
    artifact_path = _ARTIFACT_S3_URI if (os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("ARTIFACTS_FROM_S3")) else _ARTIFACT_LOCAL
    if isinstance(artifact_path, Path) and not artifact_path.exists():
        print(f"ERROR: {artifact_path} not found. Run train_matchup_v1.py first.")
        sys.exit(1)
    artifact = load_artifact(artifact_path)
    print(
        f"  matchup_v1: model_type={artifact['model_type']}, "
        f"sigma={artifact['sigma']:.5f}, CV NLL={artifact['cv_nll']:.4f}"
    )

    if not _EB_PRIORS_PATH.exists():
        print(f"ERROR: {_EB_PRIORS_PATH} not found. Run fit_matchup_cell_priors.py first.")
        sys.exit(1)
    eb = json.loads(_EB_PRIORS_PATH.read_text())
    return artifact, eb


# ── Cell feature matrix ────────────────────────────────────────────────────────

_CELL_HARD_SQL = """
SELECT
    bc.cluster_label  AS batter_cluster_label,
    pc.cluster_label  AS pitcher_cluster_label,
    COUNT(*)          AS hard_n_pa,
    ROUND(AVG(ppe.xwoba), 6)
                                                                        AS hard_xwoba_mean,
    ROUND(AVG(CASE WHEN ppe.is_strikeout THEN 1.0 ELSE 0.0 END), 6)    AS k_pct,
    ROUND(AVG(CASE WHEN ppe.is_walk     THEN 1.0 ELSE 0.0 END), 6)    AS bb_pct,
    ROUND(
        SUM(CASE WHEN sbp.exit_velocity_mph >= 95 THEN 1.0 ELSE 0.0 END)
        / NULLIF(SUM(CASE WHEN ppe.is_in_play THEN 1.0 ELSE 0.0 END), 0),
    6)                                                                  AS hard_hit_pct
FROM baseball_data.betting.mart_pitch_play_event ppe
JOIN baseball_data.statsapi.batter_clusters bc
    ON  bc.batter_id = ppe.batter_id
    AND bc.season    = ppe.game_year - 1
JOIN baseball_data.statsapi.pitcher_clusters pc
    ON  pc.pitcher_id = ppe.pitcher_id
    AND pc.season     = ppe.game_year - 1
LEFT JOIN baseball_data.betting.stg_batter_pitches sbp
    ON  sbp.game_pk       = ppe.game_pk
    AND sbp.at_bat_number = ppe.at_bat_number
    AND sbp.pitch_number  = ppe.pitch_number
WHERE ppe.plate_appearance_event IS NOT NULL
  AND ppe.game_year = %(season)s
GROUP BY 1, 2
"""

_CELL_SOFT_SQL = """
SELECT
    batter_cluster_label,
    pitcher_cluster_label,
    pa_weight  AS soft_pa_weight,
    raw_xwoba  AS soft_xwoba_mean,
    raw_woba   AS soft_woba_mean
FROM (
    SELECT
        batter_cluster_label,
        pitcher_cluster_label,
        game_date,
        pa_weight,
        raw_xwoba,
        raw_woba,
        ROW_NUMBER() OVER (
            PARTITION BY batter_cluster_label, pitcher_cluster_label
            ORDER BY game_date DESC
        ) AS rn
    FROM baseball_data.betting.mart_batter_archetype_vs_pitcher_cluster
    WHERE YEAR(game_date) = %(season)s
      AND raw_xwoba IS NOT NULL
) t
WHERE rn = 1
"""


def _build_cell_df(conn, prior_season: int, eb: dict, duck=None) -> pd.DataFrame:
    """
    Build a 25-row cell feature DataFrame for `prior_season` (= game_year - 1).
    Features mirror the training data produced by build_matchup_training_data.py.

    E11.1-W7a: when `duck` is provided (--s3), the hard/soft cell SQL reads from S3 parquet
    via DuckDB (named %(season)s param substituted as a literal int — DuckDB execute here
    uses string substitution, not paramstyle). `conn` (Snowflake) is unused in that mode.
    """
    if duck is not None:
        hard_sql = _duck_sql_for(_CELL_HARD_SQL).replace("%(season)s", str(int(prior_season)))
        hard_list = _fetch_duck(duck, hard_sql)
        hard_rows = {(r["batter_cluster_label"], r["pitcher_cluster_label"]): r for r in hard_list}

        soft_sql = _duck_sql_for(_CELL_SOFT_SQL).replace("%(season)s", str(int(prior_season)))
        soft_list = _fetch_duck(duck, soft_sql)
        soft_rows = {(r["batter_cluster_label"], r["pitcher_cluster_label"]): r for r in soft_list}
    else:
        cur = conn.cursor()

        cur.execute(_CELL_HARD_SQL, {"season": prior_season})
        cols = [d[0].lower() for d in cur.description]
        hard_rows = {(r[0], r[1]): dict(zip(cols, r)) for r in cur.fetchall()}

        cur.execute(_CELL_SOFT_SQL, {"season": prior_season})
        cols = [d[0].lower() for d in cur.description]
        soft_rows = {(r[0], r[1]): dict(zip(cols, r)) for r in cur.fetchall()}

        cur.close()

    grand_mean    = eb["global"]["grand_mean_xwoba"]
    batt_effects  = eb["batter_effects"]
    pitch_effects = eb["pitcher_effects"]
    cell_eb       = eb["cells"]

    # Clip season_norm — extrapolates to 1.25 for 2026, which is fine for Ridge
    season_norm = (prior_season - _SEASON_MIN) / max(_SEASON_MAX - _SEASON_MIN, 1)

    records = []
    for b in _BATTER_CATS:
        for p in _PITCHER_CATS:
            h      = hard_rows.get((b, p), {})
            s      = soft_rows.get((b, p), {})
            eb_c   = cell_eb.get(f"{b}__{p}", {})
            n_pa   = int(h.get("hard_n_pa", 0))
            b_eff  = batt_effects.get(b, 0.0)
            p_eff  = pitch_effects.get(p, 0.0)

            records.append({
                "batter_cluster_label":   b,
                "pitcher_cluster_label":  p,
                "hard_n_pa":              n_pa,
                "hard_xwoba_mean":        float(h.get("hard_xwoba_mean") or grand_mean),
                "k_pct":                  float(h.get("k_pct") or _FALLBACK_K_PCT),
                "bb_pct":                 float(h.get("bb_pct") or _FALLBACK_BB_PCT),
                "hard_hit_pct":           float(h.get("hard_hit_pct") or _FALLBACK_HARD_HIT_PCT),
                "soft_pa_weight":         float(s.get("soft_pa_weight") or 0),
                "soft_xwoba_mean":        float(s.get("soft_xwoba_mean") or grand_mean),
                "soft_woba_mean":         float(s.get("soft_woba_mean") or grand_mean),
                "eb_grand_mean":          grand_mean,
                "eb_batter_effect":       round(b_eff, 6),
                "eb_pitcher_effect":      round(p_eff, 6),
                "eb_additive_pred":       round(grand_mean + b_eff + p_eff, 6),
                "eb_shrunk_interaction":  eb_c.get("shrunk_interaction", 0.0),
                "eb_mu_cell":             eb_c.get("mu_cell", grand_mean + b_eff + p_eff),
                "eb_cell_shrinkage_factor": eb_c.get("cell_shrinkage_factor", 0.0),
                "eb_cell_n_pa":           float(eb_c.get("cell_n_pa") or 0),
                "cell_sparsity_flag":     float(n_pa < 200),
                "season_norm":            season_norm,
            })

    return pd.DataFrame(records)


def _score_cells(
    artifact: dict,
    cell_df: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Apply the Ridge model to the 25-cell feature matrix.
    Returns:
        cell_means   (K_b, K_p) — predicted xwOBA interaction residual per cell
        cell_sigmas  (K_b, K_p) — constant model sigma (from artifact)
        k_pct_mat    (K_b, K_p) — raw k_pct from cell stats
        hard_hit_mat (K_b, K_p) — raw hard_hit_pct from cell stats
    """
    # Replicate feature engineering from train_matchup_v1._add_base_features / _make_X
    df = cell_df.copy()
    df["log_hard_n_pa"]      = np.log1p(df["hard_n_pa"])
    df["log_soft_pa_weight"] = np.log1p(df["soft_pa_weight"].fillna(0))
    df["log_eb_cell_n_pa"]   = np.log1p(df["eb_cell_n_pa"].fillna(0))
    df["cell_sparsity_flag"] = df["cell_sparsity_flag"].astype(float)

    df["batter_cluster_label"]  = pd.Categorical(df["batter_cluster_label"],  categories=_BATTER_CATS)
    df["pitcher_cluster_label"] = pd.Categorical(df["pitcher_cluster_label"], categories=_PITCHER_CATS)

    _RAW_BASE = [
        "log_hard_n_pa",
        "k_pct", "bb_pct", "hard_hit_pct",
        "log_soft_pa_weight",
        "soft_xwoba_mean", "soft_woba_mean",
        "cell_sparsity_flag",
        "season_norm",
    ]
    b_dummies = pd.get_dummies(df["batter_cluster_label"],  prefix="batter",  drop_first=True, dtype=float)
    p_dummies = pd.get_dummies(df["pitcher_cluster_label"], prefix="pitcher", drop_first=True, dtype=float)
    X_df = pd.concat([df[_RAW_BASE], b_dummies, p_dummies], axis=1)

    # Align to artifact's feature_cols (adds any missing dummy columns as zeros)
    for col in artifact["feature_cols"]:
        if col not in X_df.columns:
            X_df[col] = 0.0
    X = X_df[artifact["feature_cols"]].values

    mu_flat = artifact["model"].predict(X)  # (25,)

    cell_means   = np.zeros((_N_B, _N_P))
    cell_sigmas  = np.full((_N_B, _N_P), artifact["sigma"])
    k_pct_mat    = np.zeros((_N_B, _N_P))
    hard_hit_mat = np.zeros((_N_B, _N_P))

    for i, row in cell_df.iterrows():
        bi = _BATTER_CATS.index(row["batter_cluster_label"])
        pi = _PITCHER_CATS.index(row["pitcher_cluster_label"])
        cell_means[bi, pi]   = float(mu_flat[i])
        k_pct_mat[bi, pi]    = float(row["k_pct"])
        hard_hit_mat[bi, pi] = float(row["hard_hit_pct"])

    return cell_means, cell_sigmas, k_pct_mat, hard_hit_mat


# ── Game data query ────────────────────────────────────────────────────────────

_GAMES_SQL = """
SELECT
    g.game_pk,
    g.game_date,
    g.game_year,
    g.home_team,
    g.away_team,
    hp.probable_pitcher_id AS home_pitcher_id,
    ap.probable_pitcher_id AS away_pitcher_id,
    lh.slot_1_player_id AS home_slot_1,
    lh.slot_2_player_id AS home_slot_2,
    lh.slot_3_player_id AS home_slot_3,
    lh.slot_4_player_id AS home_slot_4,
    lh.slot_5_player_id AS home_slot_5,
    lh.slot_6_player_id AS home_slot_6,
    lh.slot_7_player_id AS home_slot_7,
    lh.slot_8_player_id AS home_slot_8,
    lh.slot_9_player_id AS home_slot_9,
    la.slot_1_player_id AS away_slot_1,
    la.slot_2_player_id AS away_slot_2,
    la.slot_3_player_id AS away_slot_3,
    la.slot_4_player_id AS away_slot_4,
    la.slot_5_player_id AS away_slot_5,
    la.slot_6_player_id AS away_slot_6,
    la.slot_7_player_id AS away_slot_7,
    la.slot_8_player_id AS away_slot_8,
    la.slot_9_player_id AS away_slot_9
FROM baseball_data.betting.mart_game_results g
LEFT JOIN baseball_data.betting.stg_statsapi_probable_pitchers hp
    ON  hp.game_pk = g.game_pk AND hp.side = 'home'
LEFT JOIN baseball_data.betting.stg_statsapi_probable_pitchers ap
    ON  ap.game_pk = g.game_pk AND ap.side = 'away'
LEFT JOIN baseball_data.betting.stg_statsapi_lineups_wide lh
    ON  lh.game_pk = g.game_pk AND lh.home_away = 'home'
LEFT JOIN baseball_data.betting.stg_statsapi_lineups_wide la
    ON  la.game_pk = g.game_pk AND la.home_away = 'away'
WHERE g.game_date >= '{start_date}'
  AND g.game_date <= '{end_date}'
  AND g.game_type  = 'R'
ORDER BY g.game_date, g.game_pk
"""


def _load_games(conn, start_date: str, end_date: str, duck=None) -> list[dict]:
    # E11.1-W7a: --s3 reads the games spine from S3 parquet via DuckDB. _GAMES_SQL already
    # interpolates the dates literally (.format); _duck_sql_for adds the g.game_date::date casts.
    if duck is not None:
        sql = _duck_sql_for(_GAMES_SQL.format(start_date=start_date, end_date=end_date))
        return _fetch_duck(duck, sql)
    cur = conn.cursor()
    cur.execute(_GAMES_SQL.format(start_date=start_date, end_date=end_date))
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


# ── Archetype posteriors ───────────────────────────────────────────────────────

_POSTERIORS_SQL = """
SELECT
    player_id,
    player_type,
    season,
    as_of_date,
    map_cluster,
    cluster_probs,
    pa_count
FROM baseball_data.betting.mart_player_archetype_posteriors
WHERE season = %(season)s
ORDER BY player_id, player_type, as_of_date
"""


def _load_posteriors(conn, season: int, duck=None) -> dict[tuple[int, str], list[dict]]:
    """Return {(player_id, player_type): [rows sorted asc by as_of_date]}.

    E11.1-W7a: --s3 reads mart_player_archetype_posteriors from S3 parquet via DuckDB.
    """
    if duck is not None:
        sql = _duck_sql_for(_POSTERIORS_SQL).replace("%(season)s", str(int(season)))
        rows = _fetch_duck(duck, sql)
    else:
        cur = conn.cursor()
        cur.execute(_POSTERIORS_SQL, {"season": season})
        cols = [d[0].lower() for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close()

    index: dict[tuple[int, str], list[dict]] = {}
    for r in rows:
        key = (int(r["player_id"]), r["player_type"])
        index.setdefault(key, []).append(r)
    return index


def _posterior_as_of(
    posteriors: dict,
    player_id: int | None,
    player_type: str,
    game_date: date,
    uniform: np.ndarray,
    cats: list[str],
) -> tuple[np.ndarray, str | None, int]:
    """
    Return (prob_array, map_cluster, pa_count) for the most recent posterior
    with as_of_date < game_date.  Falls back to uniform if none found.
    """
    if player_id is None:
        return uniform.copy(), None, 0

    key   = (int(player_id), player_type)
    rows  = posteriors.get(key, [])
    best  = None
    for r in rows:
        aod = r["as_of_date"]
        if isinstance(aod, str):
            aod = date.fromisoformat(aod)
        elif isinstance(aod, datetime):  # S3 parquet may hand back TIMESTAMP → datetime; narrow to date
            aod = aod.date()
        if aod < game_date:
            best = r
        else:
            break  # rows sorted asc — once we pass game_date we're done

    if best is None:
        return uniform.copy(), None, 0

    cp = best["cluster_probs"]
    if isinstance(cp, str):
        cp = json.loads(cp)
    if cp is None:
        return uniform.copy(), best.get("map_cluster"), int(best.get("pa_count") or 0)

    probs = np.array([float(cp.get(k, 0.0)) for k in cats])
    s = probs.sum()
    probs = probs / s if s > 0 else uniform.copy()
    return probs, best.get("map_cluster"), int(best.get("pa_count") or 0)


# ── Signal computation ─────────────────────────────────────────────────────────

def _input_hash(game_pk: int, side: str, game_date: date) -> str:
    return hashlib.md5(f"{game_pk}|{side}|{game_date}".encode()).hexdigest()[:16]


def _signals_for_side(
    game: dict,
    side: str,
    posteriors: dict,
    cell_means: np.ndarray,
    cell_sigmas: np.ndarray,
    k_pct_mat: np.ndarray,
    hard_hit_mat: np.ndarray,
    seq_cell_posteriors: dict | None = None,
) -> list[dict]:
    """
    Compute all 7 signals for one game-side.

    side='home': home lineup faces away probable starter
    side='away': away lineup faces home probable starter

    seq_cell_posteriors: {(b_arch, p_arch): {posterior_mu, posterior_sigma, n_pa_cumulative}}
        from matchup_cell_sequential_posteriors (Story 8.5). When provided, sequential
        posterior_mu / posterior_sigma replace the static Ridge cell predictions.
    """
    game_pk   = int(game["game_pk"])
    game_date = game["game_date"]
    if isinstance(game_date, str):
        game_date = date.fromisoformat(game_date)

    if side == "home":
        lineup_slots  = [f"home_slot_{i}" for i in range(1, 10)]
        opp_pitcher_id = game.get("away_pitcher_id")
    else:
        lineup_slots  = [f"away_slot_{i}" for i in range(1, 10)]
        opp_pitcher_id = game.get("home_pitcher_id")

    # Batter soft posteriors — shape (9, K_b)
    batter_probs_list: list[np.ndarray] = []
    batter_pa_counts: list[int] = []
    for slot in lineup_slots:
        pid = game.get(slot)
        probs, _, pa = _posterior_as_of(
            posteriors, pid, "batter", game_date, _UNIFORM_BATTER, _BATTER_CATS
        )
        batter_probs_list.append(probs)
        batter_pa_counts.append(pa)
    batter_probs = np.stack(batter_probs_list, axis=0)   # (9, K_b)

    # Pitcher soft posterior — shape (K_p,)
    pitcher_probs, pitcher_map, pitcher_pa = _posterior_as_of(
        posteriors, opp_pitcher_id, "pitcher", game_date, _UNIFORM_PITCHER, _PITCHER_CATS
    )

    # signal_available gate
    slots_with_data = sum(1 for pa in batter_pa_counts if pa >= 1)
    sig_avail = pitcher_pa >= _MIN_PITCHER_PA and slots_with_data >= _MIN_LINEUP_SLOTS

    # Story 8.5: overlay sequential posteriors onto cell_means / cell_sigmas when available
    if seq_cell_posteriors:
        active_cell_means  = cell_means.copy()
        active_cell_sigmas = cell_sigmas.copy()
        for bi, b in enumerate(_BATTER_CATS):
            for pi, p in enumerate(_PITCHER_CATS):
                row = seq_cell_posteriors.get((b, p))
                if row is not None:
                    active_cell_means[bi, pi]  = float(row["posterior_mu"])
                    active_cell_sigmas[bi, pi] = float(row["posterior_sigma"])
        cell_posterior_source = _SOURCE_SEQUENTIAL
    else:
        active_cell_means  = cell_means
        active_cell_sigmas = cell_sigmas
        cell_posterior_source = _SOURCE_HISTORICAL_EB

    # Primary signals — soft mixture
    mu, sigma = compute_matchup_signal_soft(batter_probs, pitcher_probs, active_cell_means, active_cell_sigmas)
    entropy   = _joint_entropy(batter_probs, pitcher_probs)

    # Hard MAP signal (dominant batter archetype vs. MAP pitcher archetype)
    avg_b      = batter_probs.mean(axis=0)
    hard_b_idx = int(np.argmax(avg_b))
    hard_p_idx = (
        _PITCHER_CATS.index(pitcher_map)
        if pitcher_map in _PITCHER_CATS
        else int(np.argmax(pitcher_probs))
    )
    mu_hard            = float(active_cell_means[hard_b_idx, hard_p_idx])
    soft_vs_hard_delta = mu - mu_hard

    # Secondary signals — soft-weighted cell stat means
    joint        = np.outer(avg_b, pitcher_probs)   # (K_b, K_p)
    k_pressure   = float((joint * k_pct_mat).sum())
    power_signal = float((joint * hard_hit_mat).sum())

    feat_hash = _input_hash(game_pk, side, game_date)
    pi_width  = 2 * 1.2816 * sigma   # 80% Normal PI width

    base = {
        "game_pk":            game_pk,
        "side":               side,
        "sub_model_name":     _SUB_MODEL_NAME,
        "sub_model_version":  _SUB_MODEL_VERSION,
        "signal_available":   sig_avail,
        "input_feature_hash": feat_hash,
    }

    return [
        {**base, "signal_name": "matchup_advantage_mu",           "signal_value": mu,                   "uncertainty": pi_width},
        {**base, "signal_name": "matchup_advantage_sigma",        "signal_value": sigma,                "uncertainty": None},
        {**base, "signal_name": "matchup_volatility_signal",      "signal_value": entropy,              "uncertainty": None},
        {**base, "signal_name": "matchup_soft_vs_hard_delta",     "signal_value": soft_vs_hard_delta,   "uncertainty": None},
        {**base, "signal_name": "matchup_k_pressure_signal",      "signal_value": k_pressure,           "uncertainty": None},
        {**base, "signal_name": "matchup_power_signal",           "signal_value": power_signal,         "uncertainty": None},
        {**base, "signal_name": "matchup_cell_posterior_source",  "signal_value": cell_posterior_source, "uncertainty": None},
    ]


# ── Main orchestration ─────────────────────────────────────────────────────────

def run(start_date: str, end_date: str, env: str, dry_run: bool, use_s3: bool = False) -> None:
    target_table, temp_table = _resolve_tables(env)

    # E11.1-W7a: in --s3 mode the SOURCE reads come from S3 via this DuckDB connection;
    # the seq-posteriors read + SCD-2 write below STILL use Snowflake.
    duck = None
    if use_s3:
        print("\n[--s3] Reading matchup sources from S3 lakehouse via DuckDB...")
        duck = _get_duckdb()
        _register_s3_views(duck)

    print("\nLoading artifacts...")
    artifact, eb = _load_artifacts()

    print(f"\nLoading games {start_date} → {end_date}...")
    # E11.1-W7a: _GAMES_SQL joins stg_statsapi_probable_pitchers + stg_statsapi_lineups_wide,
    # which are NOT in the S3 lakehouse (Snowflake-only staging) → load the games spine from
    # Snowflake even in --s3 mode. mart_game_results in this query is a lakehouse_ext view
    # (S3-backed), so it's a view scan, not a native CTAS, and keeps no dual-write builder alive
    # (the credit-drop cluster/posterior tables are read from S3 in the per-season loop below).
    conn = get_snowflake_connection()
    try:
        games = _load_games(conn, start_date, end_date)
    finally:
        conn.close()

    if not games:
        print("No games found in the given range. Exiting.")
        return
    print(f"  {len(games):,} games")

    # Process season by season — cell features and posteriors queried once per season
    seasons = sorted({int(g["game_year"]) for g in games})
    games_by_season: dict[int, list[dict]] = {s: [] for s in seasons}
    for g in games:
        games_by_season[int(g["game_year"])].append(g)

    all_rows: list[dict] = []

    for season in seasons:
        prior_season  = season - 1
        season_games  = games_by_season[season]
        print(f"\n  Season {season} ({len(season_games):,} games; cell features from prior_season={prior_season})...")

        if use_s3:
            # E11.1-W7a: cell features + archetype posteriors from S3/DuckDB; seq-posteriors
            # (matchup_cell_sequential_posteriors) STILL from Snowflake (write-side table).
            print(f"    Building 25-cell feature matrix (prior_season={prior_season})...")
            cell_df = _build_cell_df(None, prior_season, eb, duck=duck)
            n_cells_with_data = (cell_df["hard_n_pa"] > 0).sum()
            print(f"    {n_cells_with_data}/25 cells have hard MAP data for {prior_season}")

            print(f"    Loading archetype posteriors (season={season})...")
            posteriors = _load_posteriors(None, season, duck=duck)
            n_players  = len(posteriors)
            print(f"    {n_players:,} players with posterior records")

            print(f"    Loading sequential cell posteriors for season {season} (Snowflake)...")
            conn = get_snowflake_connection()
            try:
                seq_cell_posteriors = _load_seq_cell_posteriors(conn, season)
            finally:
                conn.close()
        else:
            conn = get_snowflake_connection()
            try:
                print(f"    Building 25-cell feature matrix (prior_season={prior_season})...")
                cell_df = _build_cell_df(conn, prior_season, eb)
                n_cells_with_data = (cell_df["hard_n_pa"] > 0).sum()
                print(f"    {n_cells_with_data}/25 cells have hard MAP data for {prior_season}")

                print(f"    Loading archetype posteriors (season={season})...")
                posteriors = _load_posteriors(conn, season)
                n_players  = len(posteriors)
                print(f"    {n_players:,} players with posterior records")

                print(f"    Loading sequential cell posteriors for season {season}...")
                seq_cell_posteriors = _load_seq_cell_posteriors(conn, season)
            finally:
                conn.close()

        if seq_cell_posteriors:
            print(f"    {len(seq_cell_posteriors)} sequential posteriors found — using Story 8.5 path")
        else:
            print(f"    No sequential posteriors for {season} — using Ridge model (historical_eb)")

        print(f"    Scoring cells with Ridge model...")
        cell_means, cell_sigmas, k_pct_mat, hard_hit_mat = _score_cells(artifact, cell_df)

        n_available = 0
        for game in season_games:
            for side in ("home", "away"):
                rows = _signals_for_side(
                    game, side, posteriors,
                    cell_means, cell_sigmas, k_pct_mat, hard_hit_mat,
                    seq_cell_posteriors=seq_cell_posteriors or None,
                )
                all_rows.extend(rows)
                if rows and rows[0]["signal_available"]:
                    n_available += 1

        n_sides = len(season_games) * 2
        pct = 100.0 * n_available / n_sides if n_sides > 0 else 0.0
        print(f"    {n_sides:,} game-sides → {n_available:,} signal_available=True ({pct:.1f}%)")

    n_total  = len(all_rows)
    n_signals = 7   # 6 core matchup signals + matchup_cell_posterior_source
    n_sides  = n_total // n_signals
    print(f"\n  Total rows: {n_total:,}  ({n_sides:,} game-sides × {n_signals} signals)")

    if duck is not None:
        duck.close()

    if dry_run:
        print("\n[DRY RUN] Sample — first game, home side (7 rows):")
        for r in all_rows[:7]:
            sv = r['signal_value']
            print(f"  {r['signal_name']:<35s}  {sv:+.6f}  avail={r['signal_available']}")
        print("[DRY RUN] Skipping Snowflake write.")
        return

    # E11.1-W7a: the SCD-2 write to mart_sub_model_signals ALWAYS goes to Snowflake.
    print(f"\nWriting to {target_table}...")
    conn = get_snowflake_connection()
    try:
        result = scd2_upsert(
            conn, all_rows,
            target_table=target_table,
            temp_table=temp_table,
            computed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    finally:
        conn.close()

    print(f"  skipped={result['skipped']:,}  closed={result['closed']:,}  inserted={result['inserted']:,}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate matchup_v1 signals (Epic 8, Story 8.3)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--backfill", action="store_true",
                       help=f"Process {_TRAINING_START} through today")
    group.add_argument("--date", metavar="YYYY-MM-DD",
                       help="Process a single date")
    parser.add_argument("--env", choices=["prod", "dev"], default="prod",
                        help="Target Snowflake environment (default: prod)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute signals but do not write to Snowflake")
    parser.add_argument("--s3", action="store_true",
                        help="E11.1-W7a: read matchup SOURCE tables (cell features, games "
                             "spine, archetype posteriors) from S3 parquet via DuckDB. The "
                             "seq-posteriors read + SCD-2 write stay on Snowflake.")
    args = parser.parse_args()

    if args.backfill:
        start_date = _TRAINING_START
        end_date   = date.today().isoformat()
    else:
        start_date = end_date = args.date

    print(f"generate_matchup_signals  {start_date} → {end_date}  env={args.env}  s3={args.s3}")
    run(start_date, end_date, env=args.env, dry_run=args.dry_run, use_s3=args.s3)


if __name__ == "__main__":
    main()
