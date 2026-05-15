# SCD-2 Convention

## Overview

New feature marts and sub-model output stores use Type-2 Slowly Changing Dimensions (SCD-2). Each row represents one version of a record's state. When the payload changes, the prior row is closed (`valid_to` stamped, `is_current = FALSE`) and a new current row is inserted. This preserves the full history of every state change, enabling point-in-time (AS-OF) queries and historical replay.

## Column definitions

| Column | Type | Description |
|--------|------|-------------|
| `valid_from` | `TIMESTAMP_NTZ NOT NULL` | When this row's state became active. Set to `computed_at` of the write. |
| `valid_to` | `TIMESTAMP_NTZ NULL` | When this row was superseded. `NULL` when `is_current = TRUE`. |
| `is_current` | `BOOLEAN NOT NULL` | `TRUE` for the latest state of each natural key. Mirrors `(valid_to IS NULL)` for query convenience. |
| `record_hash` | `VARCHAR(32) NOT NULL` | `MD5(CONCAT_WS('\|', COALESCE(payload_col::VARCHAR, '') ...))` over payload columns. Drives change detection. |
| `computed_at` | `TIMESTAMP_NTZ NOT NULL` | When the write script materialized this row. Used as `valid_from` for new rows. |

## Change-detection rule

A new SCD-2 row is written when the incoming `record_hash` differs from the current row's `record_hash`. If the hash is unchanged the row is skipped — writes are idempotent.

## record_hash formula

```
MD5(CONCAT_WS('|', COALESCE(col_a::VARCHAR, ''), COALESCE(col_b::VARCHAR, ''), ...))
```

NULL values map to `''` (empty string) so that a NULL → non-NULL change is always detected. The Python writer (`scd2_writer._record_hash`) and the dbt macro (`scd2_merge`) use the same formula.

## Out-of-order arrival policy

Out-of-order rows are inserted as new current rows if no current row exists, or silently skipped if a current row with a matching or newer `record_hash` already exists. We do not retroactively re-order `valid_from`/`valid_to` chains — history reflects write order, not event order.

## Deletion semantics

Rows are never physically deleted. To mark a signal as unavailable, write a new row with `signal_available = FALSE` and `signal_value = NULL`. The prior row is closed normally.

## Point-in-time (AS-OF) query pattern

```sql
-- "What was the run_env_signal for game X as known at prediction time T?"
SELECT signal_value
FROM baseball_data.betting.mart_sub_model_signals
WHERE game_pk          = :game_pk
  AND signal_name      = 'run_env_signal'
  AND sub_model_version = 'v1'
  AND valid_from       <= :prediction_ts
  AND (valid_to > :prediction_ts OR valid_to IS NULL)
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY game_pk, signal_name, sub_model_version
    ORDER BY valid_from DESC
) = 1;
```

The `QUALIFY` guard handles the edge case where two rows share the same `valid_from` due to concurrent writes.

## Tables using SCD-2

| Table | Natural key | Payload columns | Writer |
|-------|-------------|-----------------|--------|
| `baseball_data.betting.mart_sub_model_signals` | `(game_pk, side, signal_name, sub_model_version)` | `signal_value, uncertainty, signal_available` | `betting_ml/scripts/scd2_writer.py` |
| `feature_pregame_matchup_bat_tracking` (Story 2.9) | TBD | TBD | `dbt/macros/scd2_merge.sql` |

## Implementation

### Python inference scripts (`mart_sub_model_signals`)

```python
from betting_ml.scripts.scd2_writer import scd2_upsert
from betting_ml.utils.data_loader import get_snowflake_connection

conn = get_snowflake_connection()
rows = [
    {
        "game_pk": 748532,
        "side": "home",
        "signal_name": "run_env_signal",
        "sub_model_name": "run_env",
        "sub_model_version": "v1",
        "signal_value": 9.34,
        "uncertainty": 0.42,
        "signal_available": True,
        "input_feature_hash": "abc123...",
    },
    # ... one dict per (game_pk, side, signal_name, sub_model_version)
]
stats = scd2_upsert(conn, rows)
# → {"skipped": N, "closed": N, "inserted": N}
conn.close()
```

### dbt-managed tables (Stories 2.6, 2.9)

```bash
dbtf run-operation scd2_merge --args '{
    "target": "baseball_data.betting.my_mart",
    "source": "baseball_data.betting_features.my_staging",
    "natural_key_cols": ["game_pk", "side"],
    "payload_cols": ["col_a", "col_b"]
}'
```

## Decision: dbt snapshots vs. custom macros

**Decision: custom macros + Python utility.**

dbt snapshots were rejected because:
- They use a single-hash strategy (hash all non-key columns) with no payload/key separation
- They struggle with compound natural keys that span multiple columns
- `mart_sub_model_signals` is written by Python inference scripts at inference time, not dbt — snapshots don't apply at all
- The merge logic is opaque and hard to audit

Custom approach:
- Full control over hash strategy (payload columns only, not key columns)
- `scd2_upsert()` Python function for inference scripts (`betting_ml/scripts/scd2_writer.py`)
- `scd2_merge` dbt macro for dbt-managed marts (`dbt/macros/scd2_merge.sql`)
- Explicit two-step merge (UPDATE close-out → INSERT new) — readable and testable
