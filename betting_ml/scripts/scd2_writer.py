"""
SCD-2 writer for mart_sub_model_signals.

Provides scd2_upsert() — called by sub-model inference scripts (Epics 3–8)
to write signal rows into the long-format SCD-2 store. Handles three cases:

  - New natural key   → INSERT as current row
  - Unchanged payload → skip (idempotent; same record_hash)
  - Changed payload   → close prior row (valid_to, is_current=FALSE),
                        INSERT new current row

The natural key for mart_sub_model_signals is:
    (game_pk, side, signal_name, sub_model_version)

record_hash is computed over payload columns:
    (signal_value, uncertainty, signal_available)

See quant_sports_intel_models/baseball/scd2_convention.md for the
full convention, AS-OF query pattern, and out-of-order arrival policy.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import snowflake.connector

_DEFAULT_TABLE = "baseball_data.betting.mart_sub_model_signals"

_NATURAL_KEY_COLS = ("game_pk", "side", "signal_name", "sub_model_version")
_PAYLOAD_COLS = ("signal_value", "uncertainty", "signal_available")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scd2_upsert(
    conn: snowflake.connector.SnowflakeConnection,
    rows: list[dict[str, Any]],
    *,
    target_table: str = _DEFAULT_TABLE,
    computed_at: datetime | None = None,
) -> dict[str, int]:
    """
    Upsert a batch of signal rows into mart_sub_model_signals.

    Parameters
    ----------
    conn          : Open Snowflake connection (caller owns lifecycle).
    rows          : Each dict must contain:
                      game_pk, side, signal_name, sub_model_name,
                      sub_model_version, signal_value, uncertainty,
                      signal_available, input_feature_hash
    target_table  : Fully-qualified Snowflake table name.
    computed_at   : Timestamp to stamp on all rows; defaults to utcnow.

    Returns
    -------
    {"skipped": int, "closed": int, "inserted": int}
        skipped  — rows whose payload was unchanged (same record_hash)
        closed   — prior current rows that were closed out
        inserted — new current rows written
    """
    if not rows:
        return {"skipped": 0, "closed": 0, "inserted": 0}

    now = computed_at or datetime.now(timezone.utc).replace(tzinfo=None)

    annotated = [_annotate(r) for r in rows]

    cur = conn.cursor()
    try:
        _create_temp_table(cur)
        _load_temp_table(cur, annotated)
        closed = _close_changed_rows(cur, target_table, now)
        inserted = _insert_new_rows(cur, target_table, now)
        cur.execute("DROP TABLE IF EXISTS tmp_scd2_incoming")
    finally:
        cur.close()

    skipped = len(rows) - closed - inserted
    return {"skipped": max(skipped, 0), "closed": closed, "inserted": inserted}


def compute_record_hash(row: dict[str, Any]) -> str:
    """Return the MD5 record_hash for a signal row (public for testing)."""
    return _record_hash(row)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _record_hash(row: dict[str, Any]) -> str:
    parts = "|".join(
        "" if row.get(c) is None else str(row[c]) for c in _PAYLOAD_COLS
    )
    return hashlib.md5(parts.encode()).hexdigest()


def _annotate(row: dict[str, Any]) -> dict[str, Any]:
    r = dict(row)
    r["record_hash"] = _record_hash(row)
    return r


def _create_temp_table(cur: Any) -> None:
    cur.execute("""
        CREATE OR REPLACE TEMPORARY TABLE tmp_scd2_incoming (
            game_pk             NUMBER        NOT NULL,
            side                VARCHAR(10)   NOT NULL,
            signal_name         VARCHAR(100)  NOT NULL,
            sub_model_name      VARCHAR(100)  NOT NULL,
            sub_model_version   VARCHAR(20)   NOT NULL,
            signal_value        FLOAT,
            uncertainty         FLOAT,
            signal_available    BOOLEAN       NOT NULL,
            input_feature_hash  VARCHAR(32),
            record_hash         VARCHAR(32)   NOT NULL
        )
    """)


def _load_temp_table(cur: Any, rows: list[dict[str, Any]]) -> None:
    cur.executemany(
        """
        INSERT INTO tmp_scd2_incoming VALUES (
            %(game_pk)s, %(side)s, %(signal_name)s, %(sub_model_name)s,
            %(sub_model_version)s, %(signal_value)s, %(uncertainty)s,
            %(signal_available)s, %(input_feature_hash)s, %(record_hash)s
        )
        """,
        rows,
    )


def _close_changed_rows(cur: Any, target_table: str, now: datetime) -> int:
    cur.execute(
        f"""
        UPDATE {target_table} t
        SET
            valid_to   = %(now)s::TIMESTAMP_NTZ,
            is_current = FALSE
        FROM tmp_scd2_incoming s
        WHERE t.game_pk           = s.game_pk
          AND t.side              = s.side
          AND t.signal_name       = s.signal_name
          AND t.sub_model_version = s.sub_model_version
          AND t.is_current        = TRUE
          AND t.record_hash      != s.record_hash
        """,
        {"now": now},
    )
    return cur.rowcount


def _insert_new_rows(cur: Any, target_table: str, now: datetime) -> int:
    cur.execute(
        f"""
        INSERT INTO {target_table} (
            game_pk, side, signal_name, sub_model_name, sub_model_version,
            signal_value, uncertainty, signal_available,
            input_feature_hash, computed_at,
            valid_from, valid_to, is_current, record_hash
        )
        SELECT
            s.game_pk, s.side, s.signal_name, s.sub_model_name, s.sub_model_version,
            s.signal_value, s.uncertainty, s.signal_available,
            s.input_feature_hash, %(now)s::TIMESTAMP_NTZ,
            %(now)s::TIMESTAMP_NTZ, NULL, TRUE, s.record_hash
        FROM tmp_scd2_incoming s
        LEFT JOIN {target_table} t
            ON  t.game_pk           = s.game_pk
            AND t.side              = s.side
            AND t.signal_name       = s.signal_name
            AND t.sub_model_version = s.sub_model_version
            AND t.is_current        = TRUE
        WHERE t.game_pk IS NULL
        """,
        {"now": now},
    )
    return cur.rowcount
