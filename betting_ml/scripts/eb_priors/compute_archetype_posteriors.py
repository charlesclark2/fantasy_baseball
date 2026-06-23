"""
compute_archetype_posteriors.py — Posterior soft cluster membership (Epic 7A.2)

For each player × game_date they appeared, computes a posterior probability
distribution over archetype clusters:

    posterior_k ∝ exp(−dist_k²) × Dirichlet_prior_k

where dist_k is the squared Euclidean distance from the player's feature vector
to centroid_k in the StandardScaler-normalized space used by Epic 7 KMeans.

Source data:   baseball_data.betting.stg_batter_pitches (rolling per game_date)
Centroids:     betting_ml/models/batter_archetypes/kmeans_*.pkl  (+ pitcher)
Priors:        betting_ml/models/eb_priors/archetype_priors.json
Output table:  baseball_data.betting.mart_player_archetype_posteriors

  PRIMARY KEY: (player_id, player_type, season, as_of_date)
  as_of_date = last game_date included in the running stats.
  Join guard for predictions: WHERE as_of_date < game_date

Modes:
  today    — stats through yesterday → one row per active cluster player
             (idempotent; upserts on yesterday's date)
  backfill — rolling snapshot per player × game_date in --season;
             reconstructs every point-in-time posterior for the full season

Usage:
    uv run python betting_ml/scripts/eb_priors/compute_archetype_posteriors.py --mode today
    uv run python betting_ml/scripts/eb_priors/compute_archetype_posteriors.py --mode backfill --season 2024
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import joblib
import numpy as np

warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

# ── Constants ──────────────────────────────────────────────────────────────────

_MODELS_DIR   = _PROJECT_ROOT / "betting_ml" / "models"
_PRIORS_PATH  = _MODELS_DIR / "eb_priors" / "archetype_priors.json"
_BATTER_DIR   = _MODELS_DIR / "batter_archetypes"
_PITCHER_DIR  = _MODELS_DIR / "pitcher_archetypes"

# Archetype centroids/scalers live in S3 (the prod source of truth — .pkl files are
# gitignored and not baked into the Dagster image). The fit_*_archetypes.py scripts
# upload here after saving locally; this script prefers S3 and falls back to the local
# dir for dev. Keys mirror the local layout: <prefix>/{kmeans,scaler}_<fit_date>.pkl.
_S3_BUCKET         = "baseball-betting-ml-artifacts"
_BATTER_S3_PREFIX  = "batter_archetypes"
_PITCHER_S3_PREFIX = "pitcher_archetypes"

_TARGET = "baseball_data.betting.mart_player_archetype_posteriors"
_TMP    = "baseball_data.betting.tmp_archetype_posteriors"

_PA_FULL    = 100   # ≥ full_eb
_PA_PARTIAL = 1     # ≥ partial_update (< _PA_FULL)
_BF_FULL    = 100
_BF_PARTIAL = 1

_BATTER_FEATURES = [
    "k_pct", "bb_pct", "iso", "pull_pct", "hard_hit_pct", "gb_pct",
    "height_inches", "weight_lbs", "age_at_season_start",
    "bb_k_ratio", "contact_power",
]
_PITCHER_FEATURES = [
    "fastball_pct", "breaking_pct", "offspeed_pct",
    "fb_avg_velocity", "fb_avg_hmov", "fb_avg_vmov",
    "brk_avg_hmov", "brk_avg_vmov",
    "k_pct", "bb_pct", "whiff_pct", "gb_pct",
    "age_at_season_start",
]

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TARGET} (
    player_id             INTEGER      NOT NULL,
    player_type           VARCHAR(10)  NOT NULL,
    season                INTEGER      NOT NULL,
    as_of_date            DATE         NOT NULL,
    pa_count              INTEGER,
    age_band              VARCHAR(5),
    cluster_probs         VARIANT,
    map_cluster           VARCHAR(50),
    cluster_entropy       FLOAT,
    assignment_confidence FLOAT,
    eb_data_source        VARCHAR(20),
    run_timestamp         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (player_id, player_type, season, as_of_date)
)
"""

# ── SQL ────────────────────────────────────────────────────────────────────────

_BATTER_ROLLING_SQL = """
WITH pa AS (
    SELECT
        batter_id,
        game_date,
        game_year,
        1                                                                     AS d_pa,
        CASE WHEN plate_appearance_event IN (
            'strikeout','strikeout_double_play')                               THEN 1 ELSE 0 END AS d_k,
        CASE WHEN plate_appearance_event IN ('walk','intent_walk')             THEN 1 ELSE 0 END AS d_bb,
        CASE WHEN plate_appearance_event = 'double'  THEN 1
             WHEN plate_appearance_event = 'triple'  THEN 2
             WHEN plate_appearance_event = 'home_run' THEN 3
             ELSE 0 END                                                       AS d_xb,
        CASE WHEN plate_appearance_event NOT IN (
            'walk','intent_walk','hit_by_pitch',
            'sac_fly','sac_fly_double_play',
            'sac_bunt','sac_bunt_double_play','catcher_interf')               THEN 1 ELSE 0 END AS d_ab,
        CASE WHEN batted_ball_type IS NOT NULL                                 THEN 1 ELSE 0 END AS d_bip,
        CASE WHEN batted_ball_type = 'ground_ball'                             THEN 1 ELSE 0 END AS d_gb,
        CASE WHEN batter_hand = 'R' AND hit_location_fielder IN (5,6,7)       THEN 1
             WHEN batter_hand = 'L' AND hit_location_fielder IN (3,4,9)       THEN 1
             ELSE 0 END                                                       AS d_pull,
        CASE WHEN exit_velocity_mph >= 95                                      THEN 1 ELSE 0 END AS d_hard
    FROM baseball_data.betting.stg_batter_pitches
    WHERE game_year  = %(season)s
      AND game_type  = 'R'
      AND plate_appearance_event IS NOT NULL
      {date_filter}
),
daily AS (
    SELECT
        batter_id, game_date, game_year,
        SUM(d_pa)   AS d_pa,
        SUM(d_k)    AS d_k,
        SUM(d_bb)   AS d_bb,
        SUM(d_xb)   AS d_xb,
        SUM(d_ab)   AS d_ab,
        SUM(d_bip)  AS d_bip,
        SUM(d_gb)   AS d_gb,
        SUM(d_pull) AS d_pull,
        SUM(d_hard) AS d_hard
    FROM pa
    GROUP BY batter_id, game_date, game_year
)
SELECT
    batter_id AS player_id,
    game_date AS as_of_date,
    game_year AS season,
    SUM(d_pa)   OVER (PARTITION BY batter_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS pa_count,
    SUM(d_k)    OVER (PARTITION BY batter_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_pa)  OVER (PARTITION BY batter_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS k_pct,
    SUM(d_bb)   OVER (PARTITION BY batter_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_pa)  OVER (PARTITION BY batter_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS bb_pct,
    SUM(d_xb)   OVER (PARTITION BY batter_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_ab)  OVER (PARTITION BY batter_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS iso,
    SUM(d_gb)   OVER (PARTITION BY batter_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_bip) OVER (PARTITION BY batter_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS gb_pct,
    SUM(d_pull) OVER (PARTITION BY batter_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_bip) OVER (PARTITION BY batter_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS pull_pct,
    SUM(d_hard) OVER (PARTITION BY batter_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_pa)  OVER (PARTITION BY batter_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS hard_hit_pct
FROM daily
ORDER BY batter_id, game_date
"""

_PITCHER_ROLLING_SQL = """
WITH pitches AS (
    SELECT
        pitcher_id,
        game_date,
        game_year,
        CASE WHEN pitch_type IN ('FF','SI','FC')                   THEN 'fastball'
             WHEN pitch_type IN ('SL','ST','SV','CU','KC','CS','EP') THEN 'breaking'
             WHEN pitch_type IN ('CH','FS','FO','SC')              THEN 'offspeed'
             ELSE 'other' END                                      AS pitch_cat,
        release_speed_mph,
        pitch_movement_x_ft,
        pitch_movement_z_ft,
        plate_appearance_event,
        CASE WHEN plate_appearance_event IN (
            'strikeout','strikeout_double_play')                    THEN 1 ELSE 0 END AS is_k,
        CASE WHEN plate_appearance_event IN ('walk','intent_walk')  THEN 1 ELSE 0 END AS is_bb,
        CASE WHEN plate_appearance_event IS NOT NULL                THEN 1 ELSE 0 END AS is_bf,
        CASE WHEN batted_ball_type = 'ground_ball'                  THEN 1 ELSE 0 END AS is_gb,
        CASE WHEN batted_ball_type IS NOT NULL                      THEN 1 ELSE 0 END AS is_bip,
        CASE WHEN pitch_description IN (
            'swinging_strike','swinging_strike_blocked','missed_bunt') THEN 1 ELSE 0 END AS is_whiff,
        CASE WHEN pitch_description IN (
            'swinging_strike','swinging_strike_blocked','missed_bunt',
            'foul','foul_tip','foul_bunt','hit_into_play','bunt_foul_tip') THEN 1 ELSE 0 END AS is_swing
    FROM baseball_data.betting.stg_batter_pitches
    WHERE game_year = %(season)s
      AND game_type = 'R'
      {date_filter}
),
daily AS (
    SELECT
        pitcher_id, game_date, game_year,
        COUNT(*)                                                       AS d_pitches,
        SUM(CASE WHEN pitch_cat = 'fastball' THEN 1 ELSE 0 END)       AS d_fb,
        SUM(CASE WHEN pitch_cat = 'breaking' THEN 1 ELSE 0 END)       AS d_brk,
        SUM(CASE WHEN pitch_cat = 'offspeed' THEN 1 ELSE 0 END)       AS d_os,
        SUM(CASE WHEN pitch_cat = 'fastball' AND release_speed_mph IS NOT NULL
                 THEN release_speed_mph ELSE 0 END)                    AS d_fb_vsum,
        SUM(CASE WHEN pitch_cat = 'fastball' AND release_speed_mph IS NOT NULL
                 THEN 1 ELSE 0 END)                                    AS d_fb_vcnt,
        SUM(CASE WHEN pitch_cat = 'fastball' AND pitch_movement_x_ft IS NOT NULL
                 THEN pitch_movement_x_ft ELSE 0 END)                  AS d_fb_hsum,
        SUM(CASE WHEN pitch_cat = 'fastball' AND pitch_movement_x_ft IS NOT NULL
                 THEN 1 ELSE 0 END)                                    AS d_fb_hcnt,
        SUM(CASE WHEN pitch_cat = 'fastball' AND pitch_movement_z_ft IS NOT NULL
                 THEN pitch_movement_z_ft ELSE 0 END)                  AS d_fb_vsum2,
        SUM(CASE WHEN pitch_cat = 'fastball' AND pitch_movement_z_ft IS NOT NULL
                 THEN 1 ELSE 0 END)                                    AS d_fb_vcnt2,
        SUM(CASE WHEN pitch_cat = 'breaking' AND pitch_movement_x_ft IS NOT NULL
                 THEN pitch_movement_x_ft ELSE 0 END)                  AS d_brk_hsum,
        SUM(CASE WHEN pitch_cat = 'breaking' AND pitch_movement_x_ft IS NOT NULL
                 THEN 1 ELSE 0 END)                                    AS d_brk_hcnt,
        SUM(CASE WHEN pitch_cat = 'breaking' AND pitch_movement_z_ft IS NOT NULL
                 THEN pitch_movement_z_ft ELSE 0 END)                  AS d_brk_vsum,
        SUM(CASE WHEN pitch_cat = 'breaking' AND pitch_movement_z_ft IS NOT NULL
                 THEN 1 ELSE 0 END)                                    AS d_brk_vcnt,
        SUM(is_bf)    AS d_bf,
        SUM(is_k)     AS d_k,
        SUM(is_bb)    AS d_bb,
        SUM(is_whiff) AS d_whiff,
        SUM(is_swing) AS d_swing,
        SUM(is_gb)    AS d_gb,
        SUM(is_bip)   AS d_bip
    FROM pitches
    GROUP BY pitcher_id, game_date, game_year
)
SELECT
    pitcher_id AS player_id,
    game_date  AS as_of_date,
    game_year  AS season,
    SUM(d_bf)       OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS bf_count,
    SUM(d_fb)       OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_pitches)  OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS fastball_pct,
    SUM(d_brk)      OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_pitches)  OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS breaking_pct,
    SUM(d_os)       OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_pitches)  OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS offspeed_pct,
    SUM(d_fb_vsum)  OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_fb_vcnt)  OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS fb_avg_velocity,
    SUM(d_fb_hsum)  OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_fb_hcnt)  OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS fb_avg_hmov,
    SUM(d_fb_vsum2) OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_fb_vcnt2) OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS fb_avg_vmov,
    SUM(d_brk_hsum) OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_brk_hcnt) OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS brk_avg_hmov,
    SUM(d_brk_vsum) OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_brk_vcnt) OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS brk_avg_vmov,
    SUM(d_k)        OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_bf)       OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS k_pct,
    SUM(d_bb)       OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_bf)       OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS bb_pct,
    SUM(d_whiff)    OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_swing)    OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS whiff_pct,
    SUM(d_gb)       OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / NULLIF(SUM(d_bip)      OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 0) AS gb_pct
FROM daily
ORDER BY pitcher_id, game_date
"""

_PROFILES_SQL = """
SELECT
    player_id,
    height_inches,
    weight_lbs,
    birth_date
FROM baseball_data.betting.stg_statsapi_player_profiles
"""

_PRIOR_CLUSTERS_SQL = """
SELECT batter_id AS player_id, 'batter' AS player_type, cluster_label
FROM baseball_data.statsapi.batter_clusters
WHERE season = %(season)s
UNION ALL
SELECT pitcher_id AS player_id, 'pitcher' AS player_type, cluster_label
FROM baseball_data.statsapi.pitcher_clusters
WHERE season = %(season)s
"""

# ── Model loading ──────────────────────────────────────────────────────────────

def _latest_s3_key(s3_prefix: str, prefix: str) -> str | None:
    """Return the latest (date-stamped names sort lexicographically) S3 key for
    <s3_prefix>/<prefix>_*.pkl, or None if S3 is unreachable / has no match."""
    try:
        import boto3
        s3 = boto3.client("s3")
        resp = s3.list_objects_v2(Bucket=_S3_BUCKET, Prefix=f"{s3_prefix}/{prefix}_")
        keys = [c["Key"] for c in resp.get("Contents", []) if c["Key"].endswith(".pkl")]
        return sorted(keys)[-1] if keys else None
    except Exception as exc:  # noqa: BLE001 — fall back to local; surface why.
        print(f"  [WARN] S3 lookup for {s3_prefix}/{prefix} failed ({exc}); trying local.")
        return None


def _load_latest_pkl(model_dir: Path, prefix: str, s3_prefix: str):
    """Load the latest centroid/scaler artifact. Prefers S3 (prod source of truth —
    .pkl files are gitignored and absent from the image); falls back to the local dir."""
    key = _latest_s3_key(s3_prefix, prefix)
    if key is not None:
        from betting_ml.utils.artifact_store import load_artifact
        return load_artifact(f"s3://{_S3_BUCKET}/{key}")

    files = sorted(model_dir.glob(f"{prefix}_*.pkl"), reverse=True)
    if not files:
        raise FileNotFoundError(
            f"No {prefix} pkl in s3://{_S3_BUCKET}/{s3_prefix}/ or local {model_dir}"
        )
    return joblib.load(files[0])


def _load_models():
    b_km  = _load_latest_pkl(_BATTER_DIR,  "kmeans", _BATTER_S3_PREFIX)
    b_sc  = _load_latest_pkl(_BATTER_DIR,  "scaler", _BATTER_S3_PREFIX)
    p_km  = _load_latest_pkl(_PITCHER_DIR, "kmeans", _PITCHER_S3_PREFIX)
    p_sc  = _load_latest_pkl(_PITCHER_DIR, "scaler", _PITCHER_S3_PREFIX)
    priors = json.loads(_PRIORS_PATH.read_text())
    return b_km, b_sc, p_km, p_sc, priors


# ── Data loading ───────────────────────────────────────────────────────────────

def _fetch(cur, sql: str, params: dict | None = None) -> list[dict]:
    cur.execute(sql, params or {})
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _load_rolling(conn, player_type: str, season: int, mode: str) -> list[dict]:
    date_filter = "AND game_date < CURRENT_DATE()" if mode == "today" else ""
    sql_tmpl = _BATTER_ROLLING_SQL if player_type == "batter" else _PITCHER_ROLLING_SQL
    sql = sql_tmpl.format(date_filter=date_filter)
    cur = conn.cursor()
    rows = _fetch(cur, sql, {"season": season})
    cur.close()

    if mode == "today":
        # Keep only the latest snapshot per player
        latest: dict[int, dict] = {}
        for r in rows:
            pid = r["player_id"]
            if pid not in latest or r["as_of_date"] > latest[pid]["as_of_date"]:
                latest[pid] = r
        rows = list(latest.values())

    return rows


def _load_profiles(conn) -> dict[int, dict]:
    cur = conn.cursor()
    rows = _fetch(cur, _PROFILES_SQL)
    cur.close()
    return {r["player_id"]: r for r in rows}


def _load_prior_clusters(conn, prior_season: int) -> dict[tuple[int, str], str]:
    cur = conn.cursor()
    rows = _fetch(cur, _PRIOR_CLUSTERS_SQL, {"season": prior_season})
    cur.close()
    return {(r["player_id"], r["player_type"]): r["cluster_label"] for r in rows}


# ── Age / band helpers ─────────────────────────────────────────────────────────

_AGE_BANDS = [("u24", None, 23), ("a24", 24, 27), ("a28", 28, 999)]


def _age_at_season_start(birth_date, season: int) -> float | None:
    if not birth_date:
        return None
    try:
        if isinstance(birth_date, date):
            bd = birth_date
        else:
            from datetime import datetime
            bd = datetime.strptime(str(birth_date)[:10], "%Y-%m-%d").date()
        return (date(season, 4, 1) - bd).days / 365.25
    except (ValueError, TypeError):
        return None


def _age_band(age: float | None) -> str | None:
    if age is None:
        return None
    for label, lo, hi in _AGE_BANDS:
        if (lo is None or age >= lo) and age <= hi:
            return label
    return "a28"


# ── Posterior computation ──────────────────────────────────────────────────────

def _build_feature_vector(
    row: dict,
    features: list[str],
    profile: dict | None,
) -> tuple[np.ndarray, int]:
    """Return (feature_vector, n_missing). Missing values filled with NaN."""
    v: list[float] = []
    for f in features:
        if f == "age_at_season_start":
            birth = profile.get("birth_date") if profile else None
            age = _age_at_season_start(birth, int(row["season"]))
            v.append(float(age) if age is not None else float("nan"))
        elif f == "height_inches":
            h = profile.get("height_inches") if profile else None
            v.append(float(h) if h is not None else float("nan"))
        elif f == "weight_lbs":
            w = profile.get("weight_lbs") if profile else None
            v.append(float(w) if w is not None else float("nan"))
        elif f == "bb_k_ratio":
            bb = row.get("bb_pct")
            k  = row.get("k_pct")
            if bb is not None and k is not None:
                v.append(float(bb) / (float(k) + 0.001))
            else:
                v.append(float("nan"))
        elif f == "contact_power":
            k   = row.get("k_pct")
            iso = row.get("iso")
            if k is not None and iso is not None:
                v.append((1.0 - float(k)) * float(iso))
            else:
                v.append(float("nan"))
        else:
            val = row.get(f)
            v.append(float(val) if val is not None else float("nan"))
    arr = np.array(v, dtype=float)
    n_missing = int(np.isnan(arr).sum())
    return arr, n_missing


def _gaussian_likelihood(
    fv_scaled: np.ndarray,
    centers_scaled: np.ndarray,
    missing_mask: np.ndarray,
) -> np.ndarray:
    """
    Gaussian likelihood per cluster using available feature dimensions only.
    Missing dimensions contribute 0 to squared distance (neutral — matches centroid).
    L_k = exp(-dist_k²)  per spec.
    """
    diffs = centers_scaled - fv_scaled[np.newaxis, :]     # (K, D)
    diffs[:, missing_mask] = 0.0                           # zero out missing dims
    sq_dist = (diffs ** 2).sum(axis=1)                    # (K,)
    return np.exp(-sq_dist)


def _shannon_entropy(probs: np.ndarray) -> float:
    eps = 1e-12
    return float(-np.sum(probs * np.log(probs + eps)))


def _compute_posterior(
    row: dict,
    player_type: str,
    km,
    scaler,
    priors: dict,
    profile: dict | None,
    prior_cluster: str | None,
    features: list[str],
    cluster_labels: list[str],
) -> dict:
    season = int(row["season"])
    pa_col = "pa_count" if player_type == "batter" else "bf_count"
    pa = int(row.get(pa_col) or 0)

    birth = profile.get("birth_date") if profile else None
    age   = _age_at_season_start(birth, season)
    band  = _age_band(age)

    pop_priors = priors[f"{player_type}s"]["base_prior"]
    total_alpha = priors["total_alpha_by_band"]

    # ── Prior probability vector ───────────────────────────────────────────────
    if band and band in pop_priors:
        cell = pop_priors[band]
        alphas = np.array([cell["alpha"][k] for k in cluster_labels])
    else:
        # No birth_date → uniform
        alphas = np.ones(len(cluster_labels))

    if prior_cluster and prior_cluster in cluster_labels and band:
        # Peaked prior: 80% on confirmed cluster, 20% uniform over rest
        ta    = total_alpha[band]
        peak  = 0.8 * ta
        unif  = (0.2 * ta) / max(len(cluster_labels) - 1, 1)
        alphas = np.array([
            peak if k == prior_cluster else unif
            for k in cluster_labels
        ])

    prior_probs = alphas / alphas.sum()

    # ── Feature vector and likelihood ─────────────────────────────────────────
    fv, n_missing = _build_feature_vector(row, features, profile)
    n_features = len(features)

    # Fallback: if > 50% missing, skip likelihood (use prior only)
    missing_fraction = n_missing / n_features if n_features else 1.0
    use_likelihood = pa >= _PA_PARTIAL and missing_fraction <= 0.5

    if use_likelihood:
        fv_filled = fv.copy()
        col_medians = scaler.mean_  # use scaler mean as imputation in original space
        for i, nan_flag in enumerate(np.isnan(fv)):
            if nan_flag:
                fv_filled[i] = col_medians[i]
        fv_scaled = scaler.transform(fv_filled.reshape(1, -1))[0]
        centers   = km.cluster_centers_                    # already in scaled space
        missing_mask = np.isnan(fv)
        # Re-impute in scaled space: set to centroid value per dim for missing
        for i, nan_flag in enumerate(np.isnan(fv)):
            if nan_flag:
                fv_scaled[i] = 0.0                         # centroid mean ≈ 0 in scaled space
        likelihood = _gaussian_likelihood(fv_scaled, centers, missing_mask)
    else:
        likelihood = np.ones(len(cluster_labels))

    # ── Posterior ─────────────────────────────────────────────────────────────
    unnorm    = likelihood * prior_probs
    total     = unnorm.sum()
    posterior = unnorm / total if total > 0 else prior_probs

    # ── Summary statistics ────────────────────────────────────────────────────
    map_idx    = int(np.argmax(posterior))
    map_label  = cluster_labels[map_idx]
    entropy    = _shannon_entropy(posterior)
    confidence = float(posterior[map_idx])

    if pa == 0:
        eb_src = "prior_only"
    elif pa < _PA_FULL:
        eb_src = "partial_update"
    else:
        eb_src = "full_eb"

    cluster_probs = {k: round(float(p), 6) for k, p in zip(cluster_labels, posterior)}

    return {
        "player_id":             int(row["player_id"]),
        "player_type":           player_type,
        "season":                season,
        "as_of_date":            row["as_of_date"],
        "pa_count":              pa,
        "age_band":              band,
        "cluster_probs":         json.dumps(cluster_probs),
        "map_cluster":           map_label,
        "cluster_entropy":       round(entropy, 6),
        "assignment_confidence": round(confidence, 6),
        "eb_data_source":        eb_src,
    }


# ── Snowflake write ────────────────────────────────────────────────────────────

def _ensure_table(cur) -> None:
    cur.execute(_DDL)


def _upsert(conn, rows: list[dict]) -> None:
    if not rows:
        return
    cur = conn.cursor()
    _ensure_table(cur)

    cur.execute(f"""
        CREATE OR REPLACE TEMPORARY TABLE {_TMP} (
            player_id             VARCHAR,
            player_type           VARCHAR,
            season                VARCHAR,
            as_of_date            VARCHAR,
            pa_count              VARCHAR,
            age_band              VARCHAR,
            cluster_probs         VARCHAR,
            map_cluster           VARCHAR,
            cluster_entropy       VARCHAR,
            assignment_confidence VARCHAR,
            eb_data_source        VARCHAR
        )
    """)

    def _s(v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, date):
            return v.isoformat()
        return str(v)

    data = [
        (
            _s(r["player_id"]),
            _s(r["player_type"]),
            _s(r["season"]),
            _s(r["as_of_date"]),
            _s(r["pa_count"]),
            _s(r["age_band"]),
            _s(r["cluster_probs"]),
            _s(r["map_cluster"]),
            _s(r["cluster_entropy"]),
            _s(r["assignment_confidence"]),
            _s(r["eb_data_source"]),
        )
        for r in rows
    ]
    cur.executemany(f"INSERT INTO {_TMP} VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", data)

    cur.execute(f"""
        MERGE INTO {_TARGET} tgt
        USING (
            SELECT
                player_id::INTEGER                  AS player_id,
                player_type::VARCHAR(10)            AS player_type,
                season::INTEGER                     AS season,
                as_of_date::DATE                    AS as_of_date,
                pa_count::INTEGER                   AS pa_count,
                age_band::VARCHAR(5)                AS age_band,
                PARSE_JSON(cluster_probs)           AS cluster_probs,
                map_cluster::VARCHAR(50)            AS map_cluster,
                cluster_entropy::FLOAT              AS cluster_entropy,
                assignment_confidence::FLOAT        AS assignment_confidence,
                eb_data_source::VARCHAR(20)         AS eb_data_source
            FROM {_TMP}
        ) src
        ON  tgt.player_id   = src.player_id
        AND tgt.player_type = src.player_type
        AND tgt.season      = src.season
        AND tgt.as_of_date  = src.as_of_date
        WHEN MATCHED THEN UPDATE SET
            pa_count              = src.pa_count,
            age_band              = src.age_band,
            cluster_probs         = src.cluster_probs,
            map_cluster           = src.map_cluster,
            cluster_entropy       = src.cluster_entropy,
            assignment_confidence = src.assignment_confidence,
            eb_data_source        = src.eb_data_source,
            run_timestamp         = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT (
            player_id, player_type, season, as_of_date,
            pa_count, age_band, cluster_probs, map_cluster,
            cluster_entropy, assignment_confidence, eb_data_source
        ) VALUES (
            src.player_id, src.player_type, src.season, src.as_of_date,
            src.pa_count, src.age_band, src.cluster_probs, src.map_cluster,
            src.cluster_entropy, src.assignment_confidence, src.eb_data_source
        )
    """)
    cur.close()


# ── Main ───────────────────────────────────────────────────────────────────────

def _process_population(
    conn,
    player_type: str,
    season: int,
    mode: str,
    km,
    scaler,
    priors: dict,
    profiles: dict,
    prior_clusters: dict,
) -> list[dict]:
    features      = _BATTER_FEATURES if player_type == "batter" else _PITCHER_FEATURES
    cluster_labels = priors[f"{player_type}s"]["base_prior"]["u24"]["alpha"].keys()
    cluster_labels = list(cluster_labels)

    print(f"  Loading {player_type} rolling stats ({mode}, season={season})...")
    rows = _load_rolling(conn, player_type, season, mode)
    print(f"    {len(rows)} player-date rows loaded")

    output: list[dict] = []
    for row in rows:
        pid     = int(row["player_id"])
        profile = profiles.get(pid)
        prior   = prior_clusters.get((pid, player_type))
        out     = _compute_posterior(
            row, player_type, km, scaler, priors, profile, prior,
            features, cluster_labels,
        )
        output.append(out)

    n_prior   = sum(1 for r in output if r["eb_data_source"] == "prior_only")
    n_partial = sum(1 for r in output if r["eb_data_source"] == "partial_update")
    n_full    = sum(1 for r in output if r["eb_data_source"] == "full_eb")
    print(f"    prior_only={n_prior}  partial={n_partial}  full_eb={n_full}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute archetype posteriors (7A.2)")
    parser.add_argument("--mode",   choices=["today", "backfill"], default="today")
    parser.add_argument("--season", type=int, default=date.today().year,
                        help="Season year (backfill mode)")
    args = parser.parse_args()

    b_km, b_sc, p_km, p_sc, priors = _load_models()

    conn = get_snowflake_connection()
    try:
        print("Loading player profiles...")
        profiles = _load_profiles(conn)
        print(f"  {len(profiles)} profiles loaded")

        prior_season = args.season - 1
        print(f"Loading prior-season cluster assignments (season={prior_season})...")
        prior_clusters = _load_prior_clusters(conn, prior_season)
        print(f"  {len(prior_clusters)} prior-season assignments loaded")

        all_output: list[dict] = []

        print(f"\n── Batters ──────────────────────────────────────────────")
        all_output += _process_population(
            conn, "batter", args.season, args.mode,
            b_km, b_sc, priors, profiles, prior_clusters,
        )

        print(f"\n── Pitchers ─────────────────────────────────────────────")
        all_output += _process_population(
            conn, "pitcher", args.season, args.mode,
            p_km, p_sc, priors, profiles, prior_clusters,
        )

        print(f"\nUpserting {len(all_output)} rows → {_TARGET} ...")
        _upsert(conn, all_output)
        print("Done.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
