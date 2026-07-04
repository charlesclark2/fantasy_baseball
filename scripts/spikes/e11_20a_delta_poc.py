#!/usr/bin/env python3
"""
E11.20a SPIKE — Delta Lake + Polars POC on ONE stable table (mart_pitch_characteristics analogue).

Runs entirely on LOCAL FS with a synthetic dataset whose schema/scale mirror the real
W1 pitch mart. NO prod S3 touch, NO serving change. Measures Delta-on-path + Polars vs the
current Parquet baseline, and exercises the 4 Delta wins that justify the migration.

Baseline pattern replicated from scripts/run_w1_lakehouse.py:
  - DuckDB `COPY (...) TO '<model>/data.parquet' (FORMAT PARQUET)`  (single object per mart)
  - full rebuild every run (the ~40-min driver)
  - Snowflake ext table over the parquet; TIMESTAMP stored as ISO VARCHAR (W8a cure)
"""
import json
import os
import shutil
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import polars as pl
import pyarrow as pa
from deltalake import DeltaTable, write_deltalake

ROOT = Path(__file__).resolve().parent / "poc_work"
if ROOT.exists():
    shutil.rmtree(ROOT)
ROOT.mkdir(parents=True)

PARQUET_DIR = ROOT / "parquet_baseline" / "mart_pitch_characteristics"
DELTA_DIR = ROOT / "delta" / "mart_pitch_characteristics"
N_ROWS = 1_500_000
YEARS = [2023, 2024, 2025, 2026]
RESULTS = {}


def timed(label):
    class _T:
        def __enter__(self):
            self.t = time.perf_counter(); return self
        def __exit__(self, *a):
            dt = time.perf_counter() - self.t
            RESULTS[label] = round(dt, 3)
            print(f"  ⏱  {label}: {dt:.3f}s")
    return _T()


def dir_size_mb(p: Path) -> float:
    return round(sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1e6, 2)


# ── 0. Generate a synthetic pitch mart (schema + type mix mirrors mart_pitch_characteristics)
def make_frame(n, seed=0):
    rng = np.random.default_rng(seed)
    years = rng.choice(YEARS, size=n)
    # game_date as real dates within each year
    doy = rng.integers(90, 270, size=n)
    game_date = pd.to_datetime([f"{y}-01-01" for y in years]) + pd.to_timedelta(doy, unit="D")
    df = pd.DataFrame({
        "pitch_id": np.arange(n, dtype=np.int64),                 # PK
        "game_pk": rng.integers(700000, 800000, size=n),
        "game_year": years.astype(np.int32),
        "game_date": game_date.date,                              # DATE (INT32 in parquet — SF-safe)
        "pitcher_id": rng.integers(400000, 700000, size=n),
        "batter_id": rng.integers(400000, 700000, size=n),
        "pitch_type": rng.choice(["FF", "SL", "CH", "CU", "SI", "FC"], size=n),
        "release_speed": np.round(rng.normal(92, 5, n), 1),       # DOUBLE
        "release_spin_rate": rng.integers(1500, 3000, size=n).astype(np.float64),
        "pfx_x": np.round(rng.normal(0, 6, n), 3),
        "pfx_z": np.round(rng.normal(6, 4, n), 3),
        "plate_x": np.round(rng.normal(0, 1, n), 3),
        "plate_z": np.round(rng.normal(2.5, 1, n), 3),
        "csw": rng.integers(0, 2, size=n).astype(np.int32),
        # TIMESTAMP col — the W8a landmine surface. Stored micros; downstream SF-ext misreads binary.
        "ingested_at": pd.Timestamp("2026-07-02 12:00:00") + pd.to_timedelta(rng.integers(0, 3600, n), unit="s"),
    })
    return df


print("[0] generating synthetic pitch mart …")
with timed("gen_pandas"):
    pdf = make_frame(N_ROWS)
print(f"    rows={len(pdf):,}  cols={len(pdf.columns)}  mem={pdf.memory_usage(deep=True).sum()/1e6:.0f}MB")

con = duckdb.connect()
con.register("pdf", pdf)

# ── 1. BASELINE: current pattern — DuckDB COPY to a single Parquet object (per-year, mirrors W1)
print("\n[1] BASELINE — DuckDB COPY → Parquet (current run_w1_lakehouse pattern)")
PARQUET_DIR.mkdir(parents=True)
with timed("parquet_write_full"):
    # W1 marts write a single data.parquet; larger marts partition. Do per-year to mirror scale.
    con.execute(f"COPY (SELECT * FROM pdf) TO '{PARQUET_DIR}' "
                f"(FORMAT PARQUET, PARTITION_BY (game_year), OVERWRITE_OR_IGNORE)")
RESULTS["parquet_storage_mb"] = dir_size_mb(PARQUET_DIR)
print(f"    storage={RESULTS['parquet_storage_mb']}MB")

with timed("parquet_read_duckdb_count"):
    n = con.execute(f"SELECT count(*) FROM read_parquet('{PARQUET_DIR}/**/*.parquet')").fetchone()[0]
with timed("parquet_read_duckdb_agg"):
    con.execute(f"SELECT pitch_type, avg(release_speed) FROM "
                f"read_parquet('{PARQUET_DIR}/**/*.parquet') GROUP BY 1").fetchall()

# Simulate the current "incremental" reality: a full rebuild every run (no partition MERGE).
with timed("parquet_incremental_is_FULL_rebuild"):
    con.execute(f"COPY (SELECT * FROM pdf) TO '{PARQUET_DIR}' "
                f"(FORMAT PARQUET, PARTITION_BY (game_year), OVERWRITE_OR_IGNORE)")

# ── 2. DELTA on-path — write via delta-rs (delta_log on the path, catalog-optional)
print("\n[2] DELTA on-path — write via deltalake (delta-rs), partitioned by game_year")
arrow_tbl = con.execute("SELECT * FROM pdf").arrow()
with timed("delta_write_full"):
    write_deltalake(str(DELTA_DIR), arrow_tbl, partition_by=["game_year"], mode="overwrite")
RESULTS["delta_storage_mb"] = dir_size_mb(DELTA_DIR)
dt = DeltaTable(str(DELTA_DIR))
print(f"    storage={RESULTS['delta_storage_mb']}MB  version={dt.version()}  files={len(dt.file_uris())}")

# ── 3. READ Delta three ways: DuckDB delta_scan, Polars read_delta, Arrow→Polars→DuckDB
print("\n[3] READ paths over Delta")
con.execute("INSTALL delta; LOAD delta")
with timed("delta_read_duckdb_count"):
    n2 = con.execute(f"SELECT count(*) FROM delta_scan('{DELTA_DIR}')").fetchone()[0]
with timed("delta_read_duckdb_agg"):
    con.execute(f"SELECT pitch_type, avg(release_speed) FROM delta_scan('{DELTA_DIR}') GROUP BY 1").fetchall()

with timed("delta_read_polars_scan_agg"):
    pl_res = (pl.scan_delta(str(DELTA_DIR))
              .group_by("pitch_type").agg(pl.col("release_speed").mean())
              .collect())

# Arrow-native Delta → Polars → DuckDB (zero-copy handoff)
with timed("delta_polars_to_duckdb"):
    pldf = pl.read_delta(str(DELTA_DIR))
    arrow_from_pl = pldf.to_arrow()
    con.register("pl_arrow", arrow_from_pl)
    con.execute("SELECT count(*) FROM pl_arrow").fetchone()

print(f"    duckdb count={n2:,}  polars agg rows={pl_res.height}  arrow handoff OK")

# ── 4a. WIN: SCHEMA EVOLUTION (the INC-19 structural cure) — add a column, no HALT
print("\n[4a] WIN — schema evolution (add column; the INC-19 cure)")
new_batch = pdf.head(50_000).copy()
new_batch["pitch_id"] = np.arange(N_ROWS, N_ROWS + 50_000)
new_batch["stuff_plus"] = np.round(np.random.default_rng(1).normal(100, 10, 50_000), 2)  # NEW col
try:
    with timed("delta_schema_evolution_add_col"):
        write_deltalake(str(DELTA_DIR), con.execute("SELECT * FROM new_batch").arrow(),
                        mode="append", schema_mode="merge", partition_by=["game_year"])
    dt = DeltaTable(str(DELTA_DIR))
    cols = dt.schema().to_arrow().names
    has_new = "stuff_plus" in cols
    # Old rows read back NULL for the new col — no rewrite, no ALTER, no type HALT
    null_old = con.execute(f"SELECT count(*) FROM delta_scan('{DELTA_DIR}') WHERE stuff_plus IS NULL").fetchone()[0]
    RESULTS["schema_evolution"] = f"OK — col added at v{dt.version()}, {null_old:,} old rows NULL, no rewrite"
    print(f"    ✅ stuff_plus present={has_new}; old rows NULL={null_old:,}; version={dt.version()}")
except Exception as e:
    RESULTS["schema_evolution"] = f"FAILED: {e}"
    print(f"    ❌ {e}")

# ── 4b. WIN: MERGE-into-partition (incremental update, NO full rebuild — the 40-min driver)
print("\n[4b] WIN — MERGE upsert into one partition (vs full rebuild)")
# Restate today's slate (2026) — the realistic daily incremental: upsert ~1 day of pitches.
upsert = make_frame(40_000, seed=99)
upsert["game_year"] = np.int32(2026)
upsert["pitch_id"] = np.arange(5_000_000, 5_040_000)  # some new, force a few updates too
upsert.loc[:2000, "pitch_id"] = np.arange(2001)        # overlap existing → true UPSERT
upsert["stuff_plus"] = np.round(np.random.default_rng(3).normal(100, 10, len(upsert)), 2)
upsert_arrow = con.execute("SELECT * FROM upsert").arrow()
try:
    with timed("delta_MERGE_upsert_partition"):
        (DeltaTable(str(DELTA_DIR))
         .merge(source=upsert_arrow, predicate="t.pitch_id = s.pitch_id",
                source_alias="s", target_alias="t")
         .when_matched_update_all()
         .when_not_matched_insert_all()
         .execute())
    dt = DeltaTable(str(DELTA_DIR))
    RESULTS["merge_upsert"] = f"OK — v{dt.version()}, {len(dt.file_uris())} files"
    print(f"    ✅ MERGE done; version={dt.version()}; files={len(dt.file_uris())}")
    # HONEST framing: at 1.5M rows local, full rebuild is sub-second, so wall-clock does NOT favor
    # MERGE. The win is ALGORITHMIC, not constant-factor: MERGE writes O(rows in the touched
    # partition) and reads only that partition's files; the current full rebuild reads + rewrites
    # O(ALL history) every run (the ~40-min run_w1_lakehouse driver, dominated by re-reading the
    # full stg_batter_pitches substrate). The gap widens with history size — a 4-year POC can't show it.
    m = dt.metadata()
    RESULTS["merge_vs_fullrebuild_wallclock_x"] = round(
        RESULTS["parquet_incremental_is_FULL_rebuild"] / max(RESULTS["delta_MERGE_upsert_partition"], 1e-6), 2)
    RESULTS["merge_scaling_note"] = ("wall-clock parity at POC scale (rebuild is trivially cheap here); "
                                     "MERGE is O(touched-partition), rebuild is O(all-history) → MERGE wins "
                                     "as history grows. Real driver = re-reading full stg substrate each run.")
    print(f"    ⚡ MERGE {RESULTS['delta_MERGE_upsert_partition']}s vs rebuild "
          f"{RESULTS['parquet_incremental_is_FULL_rebuild']}s (parity at POC scale); "
          f"win is O(partition) vs O(all-history) — see note")
except Exception as e:
    RESULTS["merge_upsert"] = f"FAILED: {e}"
    print(f"    ❌ {e}")

# ── 4d. WIN: TIME-TRAVEL as-of (leakage-audit / point-in-time asset)
#   NOTE: run BEFORE vacuum — vacuum physically removes the files older versions point to.
print("\n[4d] WIN — time-travel as-of version (point-in-time / leakage audit)")
try:
    dt = DeltaTable(str(DELTA_DIR))
    latest = dt.version()
    hist = dt.history()
    # read as-of v0 (initial overwrite, before schema-evolution / merge)
    dt0 = DeltaTable(str(DELTA_DIR), version=0)
    v0_cols = dt0.schema().to_arrow().names
    v0_rows = dt0.to_pyarrow_dataset().count_rows()
    latest_rows = DeltaTable(str(DELTA_DIR)).to_pyarrow_dataset().count_rows()
    RESULTS["time_travel"] = (f"OK — v0 has {v0_rows:,} rows / {len(v0_cols)} cols (no stuff_plus); "
                              f"latest v{latest} has {latest_rows:,} rows; {len(hist)} commits in log")
    print(f"    ✅ v0={v0_rows:,} rows, {len(v0_cols)} cols; latest v{latest}={latest_rows:,} rows; "
          f"'stuff_plus' in v0 cols = {'stuff_plus' in v0_cols}")
except Exception as e:
    RESULTS["time_travel"] = f"FAILED: {e}"
    print(f"    ❌ {e}")

# ── 4c. WIN: RETENTION / COMPACTION / VACUUM (the INC-20 cure) — LAST, it destroys time-travel
print("\n[4c] WIN — OPTIMIZE compaction + VACUUM (the INC-20 retention cure)")
dt = DeltaTable(str(DELTA_DIR))
files_before = len(dt.file_uris())
try:
    with timed("delta_optimize_compact"):
        dt.optimize.compact()
    dt = DeltaTable(str(DELTA_DIR))
    files_after_compact = len(dt.file_uris())
    # VACUUM retention_hours=0 forces the safety override — proves the mechanism, but it also
    # deletes every file that pre-compaction versions referenced → time-travel to v0..v2 now breaks.
    # Production MUST keep the default 7-day (168h) retention so recent time-travel survives.
    with timed("delta_vacuum"):
        removed = dt.vacuum(retention_hours=0, enforce_retention_duration=False, dry_run=False)
    # prove the tension: v0 time-travel is now broken because its parquet was vacuumed
    tt_after = "still works"
    try:
        DeltaTable(str(DELTA_DIR), version=0).to_pyarrow_dataset().count_rows()
    except Exception as _tt:
        tt_after = "BROKEN (files vacuumed) — expected; keep 168h retention in prod"
    RESULTS["retention_compaction"] = (f"OK — files {files_before}→{files_after_compact} after compact; "
                                       f"vacuum removed {len(removed)} stale files; time-travel-to-v0 {tt_after}")
    print(f"    ✅ files {files_before}→{files_after_compact}; vacuum removed {len(removed)}; "
          f"time-travel→v0 after aggressive vacuum: {tt_after}")
except Exception as e:
    RESULTS["retention_compaction"] = f"FAILED: {e}"
    print(f"    ❌ {e}")

# ── 5. MODEL-I/O BOUNDARY: Polars → pandas at model.predict() (sklearn expects pandas)
print("\n[5] MODEL-I/O boundary — Polars → pandas handoff")
with timed("polars_to_pandas_convert"):
    feat_pl = pl.read_delta(str(DELTA_DIR)).select(
        ["release_speed", "release_spin_rate", "pfx_x", "pfx_z", "plate_x", "plate_z"]).head(200_000)
    feat_pd = feat_pl.to_pandas()  # <-- the boundary. use_pyarrow_extension_array=False → numpy-backed
print(f"    polars {feat_pl.shape} → pandas {feat_pd.shape}; dtypes ok for sklearn: "
      f"{all(str(t).startswith(('float','int')) for t in feat_pd.dtypes)}")

# ── 6. DuckDB native Delta WRITE probe (prompt asks whether COPY FORMAT delta exists in 1.5.x)
print("\n[6] DuckDB native Delta-WRITE probe")
try:
    con.execute(f"COPY (SELECT * FROM pdf LIMIT 10) TO '{ROOT/'ddb_delta_probe'}' (FORMAT delta)")
    RESULTS["duckdb_delta_write"] = "SUPPORTED"
except Exception as e:
    RESULTS["duckdb_delta_write"] = f"NOT SUPPORTED in duckdb {duckdb.__version__}: {str(e)[:120]}"
print(f"    {RESULTS['duckdb_delta_write']}")

# ── summary
RESULTS["storage_delta_vs_parquet_pct"] = round(100 * RESULTS["delta_storage_mb"] / RESULTS["parquet_storage_mb"], 1)
RESULTS["_versions"] = {"duckdb": duckdb.__version__, "polars": pl.__version__,
                        "deltalake": __import__("deltalake").__version__, "pyarrow": pa.__version__}
print("\n=== RESULTS ===")
print(json.dumps(RESULTS, indent=2, default=str))
(Path(ROOT).parent / "poc_results.json").write_text(json.dumps(RESULTS, indent=2, default=str))
print(f"\nwrote {Path(ROOT).parent / 'poc_results.json'}")
