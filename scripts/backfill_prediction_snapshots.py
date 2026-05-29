"""backfill_prediction_snapshots.py
----------------------------------
One-time backfill: for every game_pk in baseball_data.betting_ml.daily_model_predictions,
write a best_effort row to baseball_data.betting.prediction_snapshots.

Design choices:
- Takes the most-recent scoring row per game_pk (by inserted_at).
- predicted_at  = inserted_at from daily_model_predictions (upper bound on when
  the prediction was made; confidence = 'bounded').
- feature_snapshot = feature values from feature_pregame_game_features at game_pk
  using the current champion's feature column list for each target.
  This is deliberate: the backfill is labelled 'best_effort' precisely because
  it reconstructs features from the current mart rather than a point-in-time snapshot.
- Writes one row per game_pk × target (home_win | total_runs | run_diff).
- Idempotent: MERGE on (game_pk, target, reconstruction_type='best_effort') — safe
  to re-run; existing best_effort rows are never overwritten.
- Logs game_pks where features were missing from feature_pregame_game_features.

Usage:
    uv run python scripts/backfill_prediction_snapshots.py
    uv run python scripts/backfill_prediction_snapshots.py --dry-run
    uv run python scripts/backfill_prediction_snapshots.py --limit 200
    uv run python scripts/backfill_prediction_snapshots.py --chunk-size 500
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import decimal

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_REGISTRY_PATH = PROJECT_ROOT / "betting_ml" / "models" / "model_registry.yaml"

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_FETCH_PREDICTIONS_SQL = """
WITH ranked AS (
    SELECT
        game_pk,
        model_version,
        inserted_at,
        calibrated_win_prob,
        pred_total_runs,
        pred_run_diff_loc,
        ROW_NUMBER() OVER (
            PARTITION BY game_pk
            ORDER BY inserted_at DESC
        ) AS rn
    FROM baseball_data.betting_ml.daily_model_predictions
    WHERE game_pk IS NOT NULL
)
SELECT
    game_pk,
    model_version,
    inserted_at,
    calibrated_win_prob,
    pred_total_runs,
    pred_run_diff_loc
FROM ranked
WHERE rn = 1
ORDER BY game_pk
"""

_FETCH_FEATURES_SQL = """
SELECT *
FROM baseball_data.betting_features.feature_pregame_game_features
WHERE game_pk IN ({placeholders})
"""

_ALTER_ADD_CONFIDENCE = """
ALTER TABLE baseball_data.betting.prediction_snapshots
    ADD COLUMN IF NOT EXISTS predicted_at_confidence VARCHAR(10)
"""

_CREATE_SNAPSHOTS_TABLE = """
CREATE TABLE IF NOT EXISTS baseball_data.betting.prediction_snapshots (
    game_pk                     INTEGER         NOT NULL,
    target                      VARCHAR(30)     NOT NULL,
    model_version               VARCHAR(20)     NOT NULL,
    predicted_at                TIMESTAMP_NTZ   NOT NULL,
    predicted_at_confidence     VARCHAR(10),
    prediction                  FLOAT,
    feature_snapshot            VARIANT,
    model_artifact_s3_uri       VARCHAR(500),
    reconstruction_type         VARCHAR(20)     NOT NULL,
    inserted_at                 TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP()
)
"""

_CREATE_TEMP = """
CREATE TEMPORARY TABLE baseball_data.betting.tmp_backfill_snapshots (
    game_pk                     INTEGER,
    target                      VARCHAR(30),
    model_version               VARCHAR(20),
    predicted_at                TIMESTAMP_NTZ,
    predicted_at_confidence     VARCHAR(10),
    prediction                  FLOAT,
    feature_snapshot_str        VARCHAR,
    model_artifact_s3_uri       VARCHAR(500),
    reconstruction_type         VARCHAR(20)
)
"""

_INSERT_TEMP = """
INSERT INTO baseball_data.betting.tmp_backfill_snapshots
    (game_pk, target, model_version, predicted_at, predicted_at_confidence,
     prediction, feature_snapshot_str, model_artifact_s3_uri, reconstruction_type)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_MERGE_BEST_EFFORT = """
MERGE INTO baseball_data.betting.prediction_snapshots t
USING (
    SELECT
        game_pk,
        target,
        model_version,
        predicted_at,
        predicted_at_confidence,
        prediction,
        PARSE_JSON(feature_snapshot_str) AS feature_snapshot,
        model_artifact_s3_uri,
        reconstruction_type
    FROM baseball_data.betting.tmp_backfill_snapshots
) s
ON  t.game_pk = s.game_pk
AND t.target  = s.target
AND t.reconstruction_type = 'best_effort'
WHEN NOT MATCHED THEN INSERT (
    game_pk, target, model_version, predicted_at, predicted_at_confidence,
    prediction, feature_snapshot, model_artifact_s3_uri, reconstruction_type
) VALUES (
    s.game_pk, s.target, s.model_version, s.predicted_at, s.predicted_at_confidence,
    s.prediction, s.feature_snapshot, s.model_artifact_s3_uri, s.reconstruction_type
)
"""

# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

def _load_registry() -> dict:
    with open(_REGISTRY_PATH) as f:
        return yaml.safe_load(f) or {}


def _load_feature_cols(registry: dict, registry_key: str) -> list[str]:
    """Return the current champion's feature column list for a registry key."""
    entry = registry[registry_key]
    rel_path = entry.get("feature_columns_path")
    if not rel_path:
        raise ValueError(f"No feature_columns_path for registry key '{registry_key}'")
    full_path = PROJECT_ROOT / rel_path
    with open(full_path) as f:
        return json.load(f)


def _artifact_uri(registry: dict, registry_key: str, model_version: str) -> str:
    """Return the artifact S3 URI most appropriate for the given model_version."""
    entry = registry[registry_key]
    # Per-version explicit override (e.g. v2_artifact_path on total_runs)
    explicit = entry.get(f"{model_version}_artifact_path")
    if explicit:
        return explicit
    if model_version == "v0":
        return entry.get("rollback_artifact_path") or entry["artifact_path"]
    # v1, v2, prod → current champion (best proxy for best_effort rows)
    return entry["artifact_path"]


# ---------------------------------------------------------------------------
# Target config
# ---------------------------------------------------------------------------

# Maps snapshot target name → (registry_key, prediction column in daily_model_predictions)
_TARGETS: list[tuple[str, str, str]] = [
    ("home_win",   "home_win",          "calibrated_win_prob"),
    ("total_runs", "total_runs",        "pred_total_runs"),
    ("run_diff",   "run_differential",  "pred_run_diff_loc"),
]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

_NUMERIC_TYPES = (int, float, np.floating, np.integer, decimal.Decimal)


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _build_snapshot_dict(feat_row: dict, feat_cols: list[str]) -> dict:
    snap: dict[str, Any] = {}
    for col in feat_cols:
        v = feat_row.get(col)
        snap[col] = _safe_float(v) if isinstance(v, _NUMERIC_TYPES) else v
    return snap


def run_backfill(dry_run: bool, limit: int | None, chunk_size: int) -> None:
    registry = _load_registry()

    # Load feature column lists and artifact URIs per target
    target_meta: list[dict] = []
    for target_name, reg_key, pred_col in _TARGETS:
        feat_cols = _load_feature_cols(registry, reg_key)
        target_meta.append({
            "target": target_name,
            "reg_key": reg_key,
            "pred_col": pred_col,
            "feat_cols": feat_cols,
        })
        log.info("Target %-12s  %d feature columns", target_name, len(feat_cols))

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()

        # Ensure table + column exist
        cur.execute(_CREATE_SNAPSHOTS_TABLE)
        cur.execute(_ALTER_ADD_CONFIDENCE)
        conn.commit()

        # Fetch all predictions (one row per game_pk, most recent scoring)
        log.info("Fetching predictions from daily_model_predictions …")
        cur.execute(_FETCH_PREDICTIONS_SQL)
        cols = [d[0].lower() for d in cur.description]
        all_preds = [dict(zip(cols, row)) for row in cur.fetchall()]
        if limit:
            all_preds = all_preds[:limit]
        log.info("  %d distinct game_pks to backfill", len(all_preds))

        # Index by game_pk for O(1) lookup after feature join
        pred_by_gk: dict[int, dict] = {int(r["game_pk"]): r for r in all_preds}
        all_game_pks = list(pred_by_gk.keys())

        total_written = 0
        missing_pks: list[int] = []

        # Process in chunks to bound memory and temp-table size
        for chunk_start in range(0, len(all_game_pks), chunk_size):
            chunk_pks = all_game_pks[chunk_start: chunk_start + chunk_size]
            pct = (chunk_start + len(chunk_pks)) / len(all_game_pks) * 100

            # Fetch feature rows for this chunk
            placeholders = ", ".join(str(pk) for pk in chunk_pks)
            cur.execute(_FETCH_FEATURES_SQL.format(placeholders=placeholders))
            feat_cols_raw = [d[0].lower() for d in cur.description]
            feat_rows = {
                int(row[feat_cols_raw.index("game_pk")]): dict(zip(feat_cols_raw, row))
                for row in cur.fetchall()
                if "game_pk" in feat_cols_raw
            }

            # Identify missing game_pks in this chunk
            chunk_missing = [pk for pk in chunk_pks if pk not in feat_rows]
            if chunk_missing:
                missing_pks.extend(chunk_missing)
                log.warning(
                    "  chunk %d–%d: %d game_pks have no feature row",
                    chunk_start, chunk_start + len(chunk_pks) - 1, len(chunk_missing),
                )

            # Build rows for every matched game_pk × target
            rows: list[tuple] = []
            for gk in chunk_pks:
                if gk not in feat_rows:
                    continue
                pred_row = pred_by_gk[gk]
                feat_row = feat_rows[gk]
                model_ver = pred_row.get("model_version") or "unknown"
                predicted_at: datetime = pred_row["inserted_at"]

                for tgt in target_meta:
                    pred_val = _safe_float(pred_row.get(tgt["pred_col"]))
                    artifact_uri = _artifact_uri(registry, tgt["reg_key"], model_ver)
                    snap = _build_snapshot_dict(feat_row, tgt["feat_cols"])
                    rows.append((
                        int(gk),
                        tgt["target"],
                        model_ver,
                        predicted_at,
                        "bounded",
                        pred_val,
                        json.dumps(snap),
                        artifact_uri,
                        "best_effort",
                    ))

            if dry_run:
                log.info(
                    "  [dry-run] chunk %d–%d: would insert %d rows (%.0f%%)",
                    chunk_start, chunk_start + len(chunk_pks) - 1, len(rows), pct,
                )
                continue

            if not rows:
                continue

            # Write via temp table → MERGE
            cur.execute(_CREATE_TEMP)
            cur.executemany(_INSERT_TEMP, rows)
            cur.execute(_MERGE_BEST_EFFORT)
            inserted = cur.rowcount or 0
            cur.execute("DROP TABLE IF EXISTS baseball_data.betting.tmp_backfill_snapshots")
            conn.commit()
            total_written += inserted
            log.info(
                "  chunk %d–%d: merged %d rows → prediction_snapshots (%.0f%%)",
                chunk_start, chunk_start + len(chunk_pks) - 1, inserted, pct,
            )

        # Summary
        if dry_run:
            log.info("\n[dry-run] complete — no rows written.")
        else:
            log.info(
                "\nBackfill complete: %d best_effort rows written to "
                "baseball_data.betting.prediction_snapshots",
                total_written,
            )

        if missing_pks:
            log.warning(
                "%d game_pks had no matching row in feature_pregame_game_features:",
                len(missing_pks),
            )
            for pk in missing_pks[:20]:
                log.warning("  missing game_pk: %d", pk)
            if len(missing_pks) > 20:
                log.warning("  … and %d more", len(missing_pks) - 20)
        else:
            log.info("All game_pks matched feature_pregame_game_features.")

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be inserted; write nothing.")
    p.add_argument("--limit", type=int, default=None,
                   help="Process only the first N game_pks (for testing).")
    p.add_argument("--chunk-size", type=int, default=500,
                   help="Number of game_pks per MERGE batch (default 500).")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_backfill(dry_run=args.dry_run, limit=args.limit, chunk_size=args.chunk_size)
