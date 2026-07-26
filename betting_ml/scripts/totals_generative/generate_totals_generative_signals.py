"""
generate_totals_generative_signals.py — Edge Program Story E2.5
(Signal registration + leakage-safe backfill for the per-side generative totals model).

Scores every regular-season game-SIDE with the E2.1/E2.1-r per-side count-distribution model
(`totals_perside_v1.pkl` — LightGBM Poisson mean, the E2.1-r bake-off's validated learner) and
writes four distributional signals per (game_pk, side) to
`baseball_data.betting_features.totals_generative_signals` via a VARCHAR temp table + MERGE
(idempotent; safe to re-run). This is the served marginal E2.6 prices the derivative markets from.

WHY A SEPARATE SIGNAL vs offense_v2 (both predict per-side runs)
---------------------------------------------------------------
offense_v2 sees only the batting side's own offence. `totals_perside_v1` models each side's runs
from the FULL matchup — that side's offence PLUS the opposing starter, opposing bullpen + pen-state,
opposing staff, park, weather and umpire — under E1.1 purged CV (train_perside_negbin.py). It is the
marginal the E2.2 copula couples and E2.3 convolves into the honest total / run-diff / team-total
distribution.

⚠️ DISPERSION = THE E2.3 CALIBRATED HELD-OUT PER-SIDE r, NOT the artifact's train-fit r.
---------------------------------------------------------------------------------------
The artifact stores `negbin_r = 7.449` — the E2.1 TRAIN-fit dispersion, which E2.1-r/E2.3 proved is
UNDER-DISPERSED (calib_80 0.778 < 0.80; the ~24% totals variance deficit). E2.3 re-calibrated a stable
leakage-safe expanding-window held-out per-side r (home 4.0645 / away 3.3977; `totals_distribution_v1.json`)
that covers correctly (calib_80 0.838). We serve the LightGBM Poisson MEAN (the validated learner —
unchanged) with the CALIBRATED per-side r. Serving the artifact's train-fit r would re-introduce the
exact bug E2.3 fixed. (E2.1-r verdict = PROMOTE_MINIMAL_FIX: keep the learner, switch the dispersion.)

LEAKAGE-SAFE BACKFILL (the AC — see [[project_layer3_signal_leakage]])
----------------------------------------------------------------------
The champion trained on all COMPLETE seasons (≠ the partial current season). Scoring a training
season with the champion is IN-SAMPLE: any downstream OOS eval (E2.6 CLV/PBO gates) that reads such
a row is contaminated (the signal encodes the fit of the very game it scores). `--backfill
--leakage-safe` produces genuinely OOS historical signals via WALK-FORWARD as-of scoring: each eval
season Y is scored by a model trained ONLY on seasons < Y (reusing the E1.1 PurgedWalkForwardSplit +
the exact per-side fit from train_perside_negbin — the same folds `run_cv` evaluates, now persisted).
Every row records `is_oos` + `train_through_season` so a downstream eval can filter to honest-OOS
rows with one predicate (`where is_oos`). The LIVE daily path scores the current (partial) season with
the champion — OOS by construction (the champion never trained on it).

  season class            scoring model                       is_oos  train_through_season
  ─────────────────────   ─────────────────────────────────   ──────  ────────────────────
  warm-up (< first fold)  champion (no as-of model exists)     False   champion max-train
  walk-forward folds      as-of model (train seasons < Y)      True    Y - 1
  current partial season  champion (never trained on it)       True    champion max-train

MARKET-BLIND: the feature matrix is the market-blind per-side matrix from train_perside_negbin
(CONTRACT-GUARD `assert_market_blind` in the trainer). No odds/line/consensus columns enter. best_alpha=0.

Usage (operator — >1-min Snowflake/DuckDB + multi-fold LightGBM: HAND OFF, never a request path):
    # Leakage-safe historical backfill (walk-forward as-of scoring) — the AC run
    uv run python betting_ml/scripts/totals_generative/generate_totals_generative_signals.py \
        --backfill --leakage-safe --s3

    # Single completed date (daily Dagster scoring; champion → live OOS)
    uv run python betting_ml/scripts/totals_generative/generate_totals_generative_signals.py \
        --date 2026-05-29 --s3

    # Dry-run (compute, print, no Snowflake write)
    uv run python betting_ml/scripts/totals_generative/generate_totals_generative_signals.py \
        --backfill --leakage-safe --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.artifact_store import load_artifact
from betting_ml.utils.data_loader import get_snowflake_connection

# Reuse the trainer's per-side assembly + fit machinery VERBATIM (single source of truth for the
# feature contract, the purged folds, and the LightGBM/NegBin fit). This keeps serve-time features
# byte-identical to train-time and makes the walk-forward backfill the SAME computation run_cv scores.
from betting_ml.scripts.totals_generative.train_perside_negbin import (
    _EXCLUDE_EVAL_YEAR,
    _MIN_MU,
    _fit_lgbm,
    _impute_means,
    _prepare_matrix,
    build_perside_frame,
    fit_negbin_r,
    load_wide,
)
from betting_ml.utils.cv import PurgedWalkForwardSplit

_MODEL_VERSION = "totals_generative_v1"
_SOURCE_ARTIFACT = "totals_perside_v1"
_ARTIFACT_S3_URI = f"s3://baseball-betting-ml-artifacts/sub_models/{_SOURCE_ARTIFACT}.pkl"
_ARTIFACT_LOCAL = (
    _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / _SOURCE_ARTIFACT / f"{_SOURCE_ARTIFACT}.pkl"
)
_DIST_JSON_S3_URI = f"s3://baseball-betting-ml-artifacts/sub_models/{_SOURCE_ARTIFACT}/totals_distribution_v1.json"
_DIST_JSON_LOCAL = (
    _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / _SOURCE_ARTIFACT / "totals_distribution_v1.json"
)

# The champion (fit_final in train_perside_negbin) trains on every season EXCEPT the partial
# _EXCLUDE_EVAL_YEAR (2026), so its last complete training season is _EXCLUDE_EVAL_YEAR - 1. A row is
# OOS for the champion iff its season is strictly after that (i.e. the current/future partial season).
_CHAMPION_TRAIN_THROUGH = _EXCLUDE_EVAL_YEAR - 1

# Training floor for the backfill load (mirrors train_perside_negbin.main default): 2018 → 5 clean
# Statcast-era eval folds 2021-2025. The current partial season is scored by the champion.
_BACKFILL_MIN_YEAR = 2018

_DB = "baseball_data"
_WRITE_SCHEMA = {"prod": "betting_features", "dev": "dev_betting_features"}
_TABLE_NAME = "totals_generative_signals"
_TEMP_TABLE = "tmp_totals_generative_signals_incoming"


# ---------------------------------------------------------------------------
# Calibrated per-side dispersion (E2.3 held-out r) + artifact loading
# ---------------------------------------------------------------------------

def _load_dispersion() -> tuple[float, float]:
    """Return (r_home, r_away) — the E2.3 leakage-safe held-out-calibrated per-side dispersion.

    NOT the artifact's train-fit `negbin_r` (under-dispersed; the bug E2.3 fixed). Falls back to the
    pooled `dispersion_r` then a hard 3.73 default so the generator never dies on a stale JSON."""
    path = _DIST_JSON_S3_URI if _artifacts_from_s3() else str(_DIST_JSON_LOCAL)
    try:
        if str(path).startswith("s3://"):
            import boto3  # lazy — laptop path uses the local file
            bucket, key = str(path)[5:].split("/", 1)
            body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
            doc = json.loads(body)
        else:
            doc = json.loads(Path(path).read_text())
    except Exception as exc:  # noqa: BLE001 — never let a missing JSON kill scoring
        print(f"  [WARN] could not read {path} ({exc}); using pooled r=3.7311 default.")
        return 3.7311, 3.7311
    pooled = float(doc.get("dispersion_r", 3.7311))
    r_home = float(doc.get("dispersion_r_home", pooled))
    r_away = float(doc.get("dispersion_r_away", pooled))
    return r_home, r_away


def _artifacts_from_s3() -> bool:
    return bool(os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("ARTIFACTS_FROM_S3"))


def _load_champion() -> dict:
    path = _ARTIFACT_S3_URI if _artifacts_from_s3() else str(_ARTIFACT_LOCAL)
    print(f"Loading champion artifact from {path} ...")
    return load_artifact(path)


# ---------------------------------------------------------------------------
# Data loading — date-bounded wide per-game mart (reuses train_perside sources)
# ---------------------------------------------------------------------------

def _wide_date_query(start_date: str, end_date: str) -> str:
    """Date-bounded version of train_perside_negbin._wide_query (which is min-year bounded).

    Same sources (feature_pregame_game_features ⋈ mart_game_results), same filters (full data,
    regular season, final present) — the join to finals also supplies the per-side `runs_scored`
    target build_perside_frame needs (we only ever score COMPLETED slates, so finals exist)."""
    return f"""
    SELECT f.*, r.home_final_score, r.away_final_score
    FROM baseball_data.betting_features.feature_pregame_game_features f
    JOIN baseball_data.betting.mart_game_results r USING (game_pk)
    WHERE f.has_full_data = TRUE
      AND r.game_type = 'R'
      AND r.home_final_score IS NOT NULL
      AND f.game_date >= '{start_date}'
      AND f.game_date <= '{end_date}'
    """


def _load_wide_date(start_date: str, end_date: str, use_s3: bool) -> pd.DataFrame:
    sql = _wide_date_query(start_date, end_date)
    if use_s3:
        from scripts.utils.lakehouse_read import (
            duck_connect,
            referenced_tables,
            register_views,
            strip_fqn,
        )
        conn = duck_connect()
        try:
            register_views(conn, referenced_tables(sql))
            df = conn.execute(strip_fqn(sql)).fetch_df()
        finally:
            conn.close()
        df.columns = [c.lower() for c in df.columns]
    else:
        conn = get_snowflake_connection(schema="betting_features")
        try:
            cur = conn.cursor()
            cur.execute(sql)
            cols = [d[0].lower() for d in cur.description]
            rows = cur.fetchall()
        finally:
            conn.close()
        df = pd.DataFrame(rows, columns=cols)
    from betting_ml.utils.data_loader import _numeric_convert
    return _numeric_convert(df)


# ---------------------------------------------------------------------------
# Serve-time matrix prep (impute + OHE aligned to the artifact) + scoring
# ---------------------------------------------------------------------------

def _prepare_score_matrix(df: pd.DataFrame, artifact: dict) -> np.ndarray:
    """Impute numerics to the artifact's train means, OHE the categoricals, and align to the
    artifact's exact `feature_names` order (numeric_cols + ohe_columns) — serve-time parity with
    train_perside_negbin._prepare_matrix / fit_final."""
    numeric_cols = artifact["numeric_cols"]
    cat_cols = artifact["cat_cols"]
    ohe_columns = artifact["ohe_columns"]
    means = artifact["impute_means"]

    # Numeric block: reindex to the artifact's exact column set in one shot (no per-column insert →
    # no DataFrame fragmentation), coerce, then impute each column to its train mean.
    num = df.reindex(columns=numeric_cols).apply(pd.to_numeric, errors="coerce")
    num = num.fillna({c: means.get(c, 0.0) for c in numeric_cols}).astype("float64")

    dummies = []
    for c in cat_cols:
        col = df[c].astype("object").fillna("__NA__") if c in df.columns else pd.Series("__NA__", index=df.index)
        dummies.append(pd.get_dummies(col, prefix=c, dtype=float))
    ohe = pd.concat(dummies, axis=1) if dummies else pd.DataFrame(index=df.index)
    ohe = ohe.reindex(columns=ohe_columns, fill_value=0.0)

    X = np.concatenate([num.to_numpy(float), ohe.to_numpy(float)], axis=1)
    assert X.shape[1] == len(artifact["feature_names"]), (
        f"feature count mismatch: {X.shape[1]} != {len(artifact['feature_names'])}"
    )
    return X


def _dispersion_for_side(side: pd.Series, r_home: float, r_away: float) -> np.ndarray:
    return np.where(side.to_numpy() == "home", r_home, r_away).astype(float)


def compute_signals(
    df: pd.DataFrame,
    mu: np.ndarray,
    r_home: float,
    r_away: float,
    *,
    is_oos: bool | np.ndarray,
    train_through: int | np.ndarray,
) -> pd.DataFrame:
    """Attach the four distributional signals + the two leakage-tracking columns.

    mu is supplied by the caller (champion predict OR a per-fold as-of predict) so the same routine
    serves both the live and the walk-forward paths. r is the E2.3 calibrated held-out per-side r."""
    mu = np.clip(np.asarray(mu, dtype=float), _MIN_MU, None)
    r = _dispersion_for_side(df["side"], r_home, r_away)
    p = r / (r + mu)
    lo = nbinom.ppf(0.10, n=r, p=p).astype(float)
    hi = nbinom.ppf(0.90, n=r, p=p).astype(float)

    out = df.copy()
    out["totals_perside_mu"] = mu
    out["totals_perside_dispersion"] = r
    out["totals_perside_raw"] = mu  # alias (offense_v2 parity: pred_runs_raw)
    out["uncertainty"] = hi - lo
    out["is_oos"] = is_oos if np.ndim(is_oos) else bool(is_oos)
    out["train_through_season"] = train_through if np.ndim(train_through) else int(train_through)
    return out


# ---------------------------------------------------------------------------
# Live / single-date scoring (champion)
# ---------------------------------------------------------------------------

def score_with_champion(df_perside: pd.DataFrame, artifact: dict, r_home: float, r_away: float) -> pd.DataFrame:
    """Score a per-side frame with the champion. is_oos = season strictly after champion's last
    complete training season (the current/future partial season is OOS by construction)."""
    X = _prepare_score_matrix(df_perside, artifact)
    mu = artifact["model"].predict(X)
    is_oos = (df_perside["game_year"].to_numpy(int) > _CHAMPION_TRAIN_THROUGH)
    return compute_signals(
        df_perside, mu, r_home, r_away, is_oos=is_oos, train_through=_CHAMPION_TRAIN_THROUGH
    )


# ---------------------------------------------------------------------------
# Leakage-safe walk-forward backfill (the AC)
# ---------------------------------------------------------------------------

def backfill_leakage_safe(
    wide: pd.DataFrame, artifact: dict, r_home: float, r_away: float
) -> pd.DataFrame:
    """Walk-forward as-of scoring — the leakage-safe backfill.

    For each PurgedWalkForwardSplit fold (eval season Y), fit a fresh per-side LightGBM Poisson mean
    on the purged prior-seasons train split and score season Y OOS (is_oos=True, train_through=Y-1).
    The excluded partial season (_EXCLUDE_EVAL_YEAR) + the warm-up seasons that are never an eval fold
    are scored by the champion and honestly tagged (is_oos = season > champion max-train). Every
    (game_pk, side) is emitted exactly once. This is the SAME computation train_perside_negbin.run_cv
    evaluates — now persisted as signals."""
    df, numeric_cols, cat_cols = build_perside_frame(wide)
    print(f"  Per-side rows: {len(df):,}  |  {len(numeric_cols)} numeric + {len(cat_cols)} categorical bases")

    splitter = PurgedWalkForwardSplit(min_train_seasons=3)
    folds = list(splitter.split(df, feature_cols=numeric_cols))

    scored_frames: list[pd.DataFrame] = []
    fold_eval_years: set[int] = set()

    print("\n── Leakage-safe walk-forward backfill (as-of per-fold fits) ─────────────")
    print(f"  {'EvalYr':>6}  {'N_tr':>7}  {'N_ev':>6}  {'train_through':>13}  {'mu_mean':>8}")
    for train_idx, eval_idx in folds:
        eval_year = int(df.loc[eval_idx, "game_year"].mode().iloc[0])
        if eval_year == _EXCLUDE_EVAL_YEAR:
            continue  # partial season — scored by the champion path below (never in-sample)
        tr, ev = df.loc[train_idx], df.loc[eval_idx]
        means = _impute_means(tr, numeric_cols)
        X_tr, X_ev, _ = _prepare_matrix(tr, ev, numeric_cols, cat_cols, means, None)
        model = _fit_lgbm(X_tr, tr["runs_scored"].to_numpy(float))
        mu_ev = model.predict(X_ev)
        train_through = int(tr["game_year"].max())
        assert train_through < eval_year, "walk-forward invariant violated (train ≥ eval season)"
        scored_frames.append(
            compute_signals(ev, mu_ev, r_home, r_away, is_oos=True, train_through=train_through)
        )
        fold_eval_years.add(eval_year)
        print(f"  {eval_year:>6}  {len(tr):>7,}  {len(ev):>6,}  {train_through:>13}  {float(np.mean(mu_ev)):>8.3f}")

    # Seasons that were never an eval fold (warm-up seasons + the excluded partial season) — score
    # with the champion and tag honestly. is_oos is False for in-sample warm-up seasons (excluded
    # from any OOS eval) and True for the partial current season.
    remainder = df[~df["game_year"].isin(fold_eval_years)].copy()
    if len(remainder):
        X = _prepare_score_matrix(remainder, artifact)
        mu = artifact["model"].predict(X)
        is_oos = remainder["game_year"].to_numpy(int) > _CHAMPION_TRAIN_THROUGH
        scored_frames.append(
            compute_signals(remainder, mu, r_home, r_away, is_oos=is_oos, train_through=_CHAMPION_TRAIN_THROUGH)
        )
        n_oos = int(np.sum(is_oos))
        print(f"  champion-scored remainder: {len(remainder):,} rows "
              f"({sorted(remainder['game_year'].unique())}) — is_oos True on {n_oos:,}")

    out = pd.concat(scored_frames, ignore_index=True)
    n_oos = int(out["is_oos"].sum())
    print(f"\n  Backfill total: {len(out):,} rows  |  is_oos True: {n_oos:,} "
          f"({n_oos / len(out):.1%})  |  eval folds: {sorted(fold_eval_years)}")
    return out


# ---------------------------------------------------------------------------
# Snowflake write (VARCHAR temp table + MERGE) — mirrors offense_v2
# ---------------------------------------------------------------------------

def _ddl(target_table: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {target_table} (
    game_pk                   VARCHAR(20)   NOT NULL,
    side                      VARCHAR(4)    NOT NULL,
    game_date                 DATE          NOT NULL,
    game_year                 INTEGER       NOT NULL,
    totals_perside_mu         FLOAT         NOT NULL,
    totals_perside_dispersion FLOAT         NOT NULL,
    totals_perside_raw        FLOAT         NOT NULL,
    uncertainty               FLOAT         NOT NULL,
    is_oos                    BOOLEAN       NOT NULL,
    train_through_season      INTEGER       NOT NULL,
    model_version             VARCHAR(30)   NOT NULL,
    ingestion_ts              TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (game_pk, side, model_version)
)
"""


def ensure_table(conn, target_table: str) -> None:
    conn.cursor().execute(_ddl(target_table))


def write_signals(conn, df: pd.DataFrame, target_table: str, dry_run: bool = False) -> dict[str, int]:
    rows = [
        (
            str(row["game_pk"]),
            str(row["side"]),
            str(row["game_date"]),
            str(int(row["game_year"])),
            str(round(float(row["totals_perside_mu"]), 6)),
            str(round(float(row["totals_perside_dispersion"]), 6)),
            str(round(float(row["totals_perside_raw"]), 6)),
            str(round(float(row["uncertainty"]), 6)),
            "true" if bool(row["is_oos"]) else "false",
            str(int(row["train_through_season"])),
            _MODEL_VERSION,
        )
        for _, row in df.iterrows()
    ]

    if dry_run:
        print(f"\n[DRY RUN] Would write {len(rows):,} rows to {target_table}.")
        for r in rows[:4]:
            print(f"    {r}")
        return {"inserted": 0, "updated": 0}

    cur = conn.cursor()
    cur.execute(f"""
        CREATE OR REPLACE TEMPORARY TABLE {_TEMP_TABLE} (
            game_pk                   VARCHAR,
            side                      VARCHAR,
            game_date                 VARCHAR,
            game_year                 VARCHAR,
            totals_perside_mu         VARCHAR,
            totals_perside_dispersion VARCHAR,
            totals_perside_raw        VARCHAR,
            uncertainty               VARCHAR,
            is_oos                    VARCHAR,
            train_through_season      VARCHAR,
            model_version             VARCHAR
        )
    """)
    cur.executemany(
        f"INSERT INTO {_TEMP_TABLE} VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        rows,
    )
    print(f"  Staged {len(rows):,} rows in temp table.")

    merge_sql = f"""
        MERGE INTO {target_table} AS tgt
        USING (
            SELECT
                game_pk::VARCHAR(20)                   AS game_pk,
                side::VARCHAR(4)                       AS side,
                game_date::DATE                        AS game_date,
                game_year::INTEGER                     AS game_year,
                totals_perside_mu::FLOAT               AS totals_perside_mu,
                totals_perside_dispersion::FLOAT       AS totals_perside_dispersion,
                totals_perside_raw::FLOAT              AS totals_perside_raw,
                uncertainty::FLOAT                     AS uncertainty,
                is_oos::BOOLEAN                        AS is_oos,
                train_through_season::INTEGER          AS train_through_season,
                model_version::VARCHAR(30)             AS model_version
            FROM {_TEMP_TABLE}
        ) AS src
        ON  tgt.game_pk       = src.game_pk
        AND tgt.side          = src.side
        AND tgt.model_version = src.model_version
        WHEN MATCHED THEN UPDATE SET
            game_date                 = src.game_date,
            game_year                 = src.game_year,
            totals_perside_mu         = src.totals_perside_mu,
            totals_perside_dispersion = src.totals_perside_dispersion,
            totals_perside_raw        = src.totals_perside_raw,
            uncertainty               = src.uncertainty,
            is_oos                    = src.is_oos,
            train_through_season      = src.train_through_season,
            ingestion_ts              = CURRENT_TIMESTAMP
        WHEN NOT MATCHED THEN INSERT
            (game_pk, side, game_date, game_year, totals_perside_mu, totals_perside_dispersion,
             totals_perside_raw, uncertainty, is_oos, train_through_season, model_version)
        VALUES
            (src.game_pk, src.side, src.game_date, src.game_year, src.totals_perside_mu,
             src.totals_perside_dispersion, src.totals_perside_raw, src.uncertainty,
             src.is_oos, src.train_through_season, src.model_version)
    """
    cur.execute(merge_sql)
    row = cur.fetchone()
    inserted = int(row[0]) if row and row[0] is not None else 0
    updated = int(row[1]) if row and len(row) > 1 and row[1] is not None else 0
    return {"inserted": inserted, "updated": updated}


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

def run_sanity_checks(df: pd.DataFrame, r_home: float, r_away: float) -> None:
    mu_p5 = float(np.percentile(df["totals_perside_mu"], 5))
    mu_p95 = float(np.percentile(df["totals_perside_mu"], 95))
    unc_p50 = float(np.percentile(df["uncertainty"], 50))
    print(f"\n  totals_perside_mu — p5={mu_p5:.3f}  p95={mu_p95:.3f}  (expect p5 ≥ 1.5, p95 ≤ 10.0)")
    print(f"  dispersion        — r_home={r_home:.3f}  r_away={r_away:.3f}  (E2.3 held-out calibrated)")
    print(f"  uncertainty       — median={unc_p50:.1f} runs (80% NegBin PI width)")
    if mu_p5 < 1.5:
        print(f"  [WARN] mu p5={mu_p5:.3f} below 1.5 floor — check imputation.")
    if mu_p95 > 10.0:
        print(f"  [WARN] mu p95={mu_p95:.3f} above 10.0 ceiling — check outliers.")
    if "is_oos" in df:
        print(f"  is_oos coverage   — {int(df['is_oos'].sum()):,}/{len(df):,} rows "
              f"({df['is_oos'].mean():.1%}) are honest-OOS.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Generate totals_generative_v1 signals (Story E2.5)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backfill", action="store_true",
                      help="Score the historical span. Pair with --leakage-safe for walk-forward "
                           "as-of scoring (the AC); without it the champion scores everything (fast, "
                           "but training seasons are IN-SAMPLE — only valid for a re-serve, not eval).")
    mode.add_argument("--date", metavar="YYYY-MM-DD", help="Score one completed date (daily scoring).")
    ap.add_argument("--leakage-safe", action="store_true",
                    help="With --backfill: walk-forward as-of scoring so no season is scored in-sample.")
    ap.add_argument("--min-year", type=int, default=_BACKFILL_MIN_YEAR,
                    help=f"Earliest season for --backfill (default {_BACKFILL_MIN_YEAR}).")
    ap.add_argument("--env", choices=["prod", "dev"], default="prod")
    ap.add_argument("--dry-run", action="store_true", help="Compute + print, skip the Snowflake write.")
    ap.add_argument("--s3", action="store_true", help="Read features from the S3 lakehouse (DuckDB).")
    args = ap.parse_args()

    target_table = f"{_DB}.{_WRITE_SCHEMA[args.env]}.{_TABLE_NAME}"
    print(f"[{args.env.upper()}] target={target_table}   model_version={_MODEL_VERSION}")

    artifact = _load_champion()
    print(f"  model_type={artifact['model_type']}  n_features={len(artifact['feature_names'])}  "
          f"artifact_train_fit_r={artifact['negbin_r']:.3f} (NOT served — E2.3 held-out r is)")
    r_home, r_away = _load_dispersion()
    print(f"  served dispersion: r_home={r_home:.4f}  r_away={r_away:.4f}  (E2.3 calibrated held-out)")

    if args.backfill:
        if not args.leakage_safe:
            print("\n⚠️  --backfill without --leakage-safe scores training seasons IN-SAMPLE — the "
                  "resulting rows are NOT valid for OOS eval. Use --leakage-safe for the AC backfill.")
        today = date.today().isoformat()
        print(f"\nLoading wide mart {args.min_year}-01-01 → {today} from "
              f"{'S3 (DuckDB)' if args.s3 else 'Snowflake'} ...")
        wide = _load_wide_date(f"{args.min_year}-01-01", today, args.s3) if not args.leakage_safe \
            else load_wide(args.min_year, source="lakehouse" if args.s3 else "snowflake")
        print(f"  {len(wide):,} games loaded.")
        if not len(wide):
            print("No games found. Exiting.")
            return
        if args.leakage_safe:
            df_out = backfill_leakage_safe(wide, artifact, r_home, r_away)
        else:
            df_perside, _, _ = build_perside_frame(wide)
            df_out = score_with_champion(df_perside, artifact, r_home, r_away)
    else:
        print(f"\nLoading completed slate {args.date} from {'S3 (DuckDB)' if args.s3 else 'Snowflake'} ...")
        wide = _load_wide_date(args.date, args.date, args.s3)
        print(f"  {len(wide):,} games loaded.")
        if not len(wide):
            print("No games found for date. Exiting.")
            return
        df_perside, _, _ = build_perside_frame(wide)
        df_out = score_with_champion(df_perside, artifact, r_home, r_away)

    print(f"\n  Generated {len(df_out):,} signal rows ({df_out['game_pk'].nunique():,} games).")
    run_sanity_checks(df_out, r_home, r_away)

    if args.dry_run:
        write_signals(None, df_out, target_table, dry_run=True)
        print("\n[DRY RUN] Complete. No rows written.")
        return

    conn = get_snowflake_connection(schema=_WRITE_SCHEMA[args.env])
    try:
        ensure_table(conn, target_table)
        result = write_signals(conn, df_out, target_table, dry_run=False)
    finally:
        conn.close()
    print(f"  Done. inserted={result['inserted']:,}  updated={result['updated']:,}")
    print("\nStory E2.5 write complete. Next: export_w9_signals_to_s3.py --table totals_generative_signals, "
          "then dbtf build --select feature_pregame_sub_model_signals.")


if __name__ == "__main__":
    main()
