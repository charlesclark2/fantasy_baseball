"""The nullable-int→DOUBLE mirror-poisoning guard (2026-07-15, the INC-17-class
avg_eb_woba outage — lineup block NULL on every served slate since 2026-07-03).

MECHANISM: a `SELECT *`→pandas→parquet mirror turns any Snowflake NUMBER(38,0) column
containing NULLs into float64 → parquet DOUBLE (SLOT_6..9_PLAYER_ID had pre-lineup
NULLs; slots 1–5 stayed BIGINT). feature_pregame_lineup_features UNIONs all 9 slot ids,
so ONE double column coerced the whole `batter_id` to DOUBLE → `::varchar` rendered
'664983.0' → the string join to eb_batter_posteriors_raw matched 0 rows → avg_eb_woba
NULL for EVERY game (historical too). Parity/CI-blind: types only exist at a real
export. This is the numeric sibling of the W11 `dtype=str`→VARCHAR-mirror landmine.

CURE (writer-side, one place heals every consumer): export_w8b_precursors_to_s3 pins
every FIXED scale-0 result column to pandas nullable Int64 pre-write and REFUSES to
write a pinned column as a non-int parquet type. These tests keep both halves wired and
pin the library behavior the cure relies on.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa

REPO = Path(__file__).resolve().parents[2]
EXPORTER = (REPO / "scripts" / "export_w8b_precursors_to_s3.py").read_text()


def test_exporter_pins_fixed_scale0_columns_to_int64():
    assert 'astype("Int64")' in EXPORTER, (
        "export_w8b_precursors_to_s3 no longer pins FIXED scale-0 columns to nullable "
        "Int64 — a NUMBER(38,0) column with NULLs (SLOT_6..9_PLAYER_ID) will write as "
        "parquet DOUBLE and re-null avg_eb_woba on every served slate (2026-07-15)."
    )
    assert "d[1] == 0 and (d[5] or 0) == 0" in EXPORTER, (
        "the Int64 pin must select columns from the CURSOR DESCRIPTION "
        "(type_code 0 = FIXED, scale 0) — not a hand-kept column list."
    )


def test_exporter_refuses_to_write_a_pinned_column_as_double():
    assert "is_integer" in EXPORTER and "refusing to clobber the mirror" in EXPORTER, (
        "the write-time int contract is gone — a silent DOUBLE write re-poisons every "
        "VARCHAR-cast join downstream; the export must RAISE instead."
    )


def test_nullable_int64_roundtrips_as_parquet_int():
    """The library behavior the cure rests on: object column of ints+None → Int64 →
    arrow int64 (nulls preserved). If a pandas/pyarrow bump breaks this, the box would
    re-poison the mirror on its next export — fail HERE first."""
    df = pd.DataFrame({"SLOT_9_PLAYER_ID": [664983, None, 123456]})
    assert str(df["SLOT_9_PLAYER_ID"].dtype) == "float64"  # the poisoning default
    df["SLOT_9_PLAYER_ID"] = df["SLOT_9_PLAYER_ID"].astype("Int64")
    tbl = pa.Table.from_pandas(df, preserve_index=False)
    f = tbl.schema.field("SLOT_9_PLAYER_ID")
    assert pa.types.is_integer(f.type), f"Int64 pin wrote {f.type}, not int"
    vals = tbl.column("SLOT_9_PLAYER_ID").to_pylist()
    assert vals == [664983, None, 123456], "values/nulls must survive the pin exactly"
