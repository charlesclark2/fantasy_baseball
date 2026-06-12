"""
model_registry_tracker.py — Maintain the Snowflake champion-lineage table on promote.

Story 30.7 (model & prediction provenance). The table
`baseball_data.betting_ml.model_registry` was created + seeded once by
`scripts/ddl/model_tracking_migration.sql` with the right SCD shape
(promoted_date / deprecated_date / is_current) but NOTHING maintained it on
promotion — so after the first promote its lineage went stale. This module is
the missing maintenance step: call `record_promotion(...)` as part of the
promotion runbook (right after the S3 artifact push) and the table stays a
gap-free, queryable history of which model was the production champion in which
window.

Canonicality split (Story 30.7): this Snowflake table is canonical for the
TEMPORAL lineage (windows); `betting_ml/models/model_registry.yaml` stays
canonical for the CURRENT serving artifact that predict_today.py loads.

Usage (programmatic):
    from betting_ml.utils.model_registry_tracker import record_promotion
    record_promotion(
        target="home_win", new_version="v5", model_name="xgb_market_blind",
        artifact_path="s3://baseball-betting-ml-artifacts/home_win/...pkl",
        feature_columns_path="betting_ml/models/home_win/...json",
        features=209, training_rows=10766, training_cutoff="2021+",
        cv_metric_name="brier", cv_metric_value=0.1919,
        promoted_date="2026-06-12",
        notes="Story 30.4 market-blind retrain. Promoted via correctness override ...",
    )

Idempotent: keyed on the table PK (target, model_version). Re-running the same
promotion is a no-op (the new row already exists and is current); it will NOT
double-deprecate or shift any date.
"""

from __future__ import annotations

from dataclasses import dataclass

from betting_ml.utils.data_loader import get_snowflake_connection

_REGISTRY = "baseball_data.betting_ml.model_registry"


@dataclass
class PromotionRecord:
    """Outcome of a record_promotion() call (for logging / assertions)."""
    target: str
    new_version: str
    deprecated_version: str | None  # the version that was current before, now retired
    already_current: bool           # True if new_version was already is_current (no-op)


def record_promotion(
    target: str,
    new_version: str,
    model_name: str,
    artifact_path: str,
    feature_columns_path: str,
    features: int,
    training_rows: int,
    training_cutoff: str,
    cv_metric_name: str,
    cv_metric_value: float,
    promoted_date: str,
    notes: str,
    conn=None,
) -> PromotionRecord:
    """Record a champion promotion in the Snowflake lineage table, transactionally.

    Steps, in ONE transaction:
      1. Find the current (is_current=TRUE) row for `target`, if any.
      2. If `new_version` is already that current row → no-op (idempotent re-run).
      3. Otherwise: close the outgoing champion
         (deprecated_date = promoted_date, is_current = FALSE),
         then INSERT the new champion (is_current = TRUE, deprecated_date = NULL).
         If `new_version` already exists but isn't current (e.g. a rollback/re-promote),
         it is UPDATEd back to current instead of inserted.

    `promoted_date` must be an ISO date string ('YYYY-MM-DD'); the caller supplies
    it explicitly (this codebase forbids argless date construction).

    Returns a PromotionRecord describing what changed.
    """
    owns_conn = conn is None
    if owns_conn:
        conn = get_snowflake_connection()
    try:
        cur = conn.cursor()

        # 1. Current champion for this target (if any).
        cur.execute(
            f"SELECT model_version FROM {_REGISTRY} "
            f"WHERE target = %(target)s AND is_current = TRUE",
            {"target": target},
        )
        current_rows = cur.fetchall()
        current_version = current_rows[0][0] if current_rows else None

        # 2. Idempotent no-op: the new version is already the live champion.
        if current_version == new_version:
            return PromotionRecord(
                target=target, new_version=new_version,
                deprecated_version=None, already_current=True,
            )

        # 3a. Close out the outgoing champion (if different).
        if current_version is not None:
            cur.execute(
                f"UPDATE {_REGISTRY} "
                f"SET deprecated_date = %(promoted_date)s, is_current = FALSE "
                f"WHERE target = %(target)s AND model_version = %(old)s",
                {"promoted_date": promoted_date, "target": target, "old": current_version},
            )

        # 3b. Does the new version already exist (rollback / re-promote)?
        cur.execute(
            f"SELECT 1 FROM {_REGISTRY} "
            f"WHERE target = %(target)s AND model_version = %(v)s",
            {"target": target, "v": new_version},
        )
        exists = bool(cur.fetchall())

        params = {
            "target": target, "model_version": new_version, "model_name": model_name,
            "artifact_path": artifact_path, "feature_columns_path": feature_columns_path,
            "features": int(features), "training_rows": int(training_rows),
            "training_cutoff": training_cutoff, "cv_metric_name": cv_metric_name,
            "cv_metric_value": float(cv_metric_value), "promoted_date": promoted_date,
            "notes": notes,
        }

        if exists:
            # Re-promote an existing version back to current.
            cur.execute(
                f"UPDATE {_REGISTRY} "
                f"SET is_current = TRUE, deprecated_date = NULL, "
                f"    promoted_date = %(promoted_date)s, notes = %(notes)s "
                f"WHERE target = %(target)s AND model_version = %(model_version)s",
                params,
            )
        else:
            cur.execute(
                f"INSERT INTO {_REGISTRY} "
                f"(target, model_version, model_name, artifact_path, feature_columns_path, "
                f" features, training_rows, training_cutoff, cv_metric_name, cv_metric_value, "
                f" promoted_date, deprecated_date, is_current, notes) "
                f"VALUES (%(target)s, %(model_version)s, %(model_name)s, %(artifact_path)s, "
                f" %(feature_columns_path)s, %(features)s, %(training_rows)s, %(training_cutoff)s, "
                f" %(cv_metric_name)s, %(cv_metric_value)s, %(promoted_date)s, NULL, TRUE, %(notes)s)",
                params,
            )

        conn.commit()
        return PromotionRecord(
            target=target, new_version=new_version,
            deprecated_version=current_version, already_current=False,
        )
    finally:
        if owns_conn:
            conn.close()
