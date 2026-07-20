"""E11.20 — the PURE Delta-lakehouse registry: which lakehouse tables are Delta-backed,
where they live on S3, and what the rollout mode is.

⚠️ TWO BYTE-IDENTICAL HOMES — keep them in sync (guard-tested):
  • betting_ml/utils/delta_lakehouse.py — imported by the in-process Dagster sensors
    (lakehouse_monitor) + the builder (run_w1_lakehouse), which may only import
    pipeline/ or the betting_ml wheel (feedback_dagster_import_only_packaged_code).
  • scripts/utils/delta_lakehouse.py — imported by scripts/utils/lakehouse_read.py +
    scripts/utils/delta_lake.py, because the LEAN capture images COPY scripts/utils/
    wholesale and must never contain a betting_ml import node
    (test_lean_capture_images_selfcontained — INC-29 class).
betting_ml/tests/test_delta_lakehouse_guard.py FAILS if the two files differ.

This module is the single source of truth for the Delta rollout state. It is deliberately
PURE stdlib — importing it pulls in no duckdb / deltalake / boto3 / pandas — so it is
fast-gate-test safe and lean-image safe.

Rollout mode (per migrated family) is an env var with THREE values, mirroring the
LAKEHOUSE_RAW_WRITE_MODE / W*_LAKEHOUSE_S3 cutover convention:

  off      (default) — Delta not written, not read. Merging this code is a no-op.
  mirror   — Delta IS written alongside the authoritative parquet (validation window;
             parity via scripts/parity_check_delta_w1.py), reads stay on parquet.
  cutover  — Delta is the SOLE writer + reader for the family. The old
             lakehouse/<table>/data.parquet keys are FROZEN the moment this flips
             (INC-31 writer-uniqueness: one writer per key — the retired parquet
             writer is skipped, never left racing the Delta write).

⚠️ An UNKNOWN mode value raises ValueError LOUDLY (never a silent default): a typo'd
cutover flag silently reading as "off" is exactly the "silently never runs" outage class.
"""
from __future__ import annotations

import os

BUCKET = "s3://baseball-betting-ml-artifacts"
# Delta tables live under their OWN prefix — NEVER inside lakehouse/<table>/ next to the
# legacy data.parquet. The lakehouse_ext external tables glob <table>/**/*.parquet, so
# co-locating Delta part-files there would double-count rows through the ext table
# (the glob-dup landmine) and violate INC-31 writer-uniqueness-per-key.
LAKEHOUSE_DELTA = f"{BUCKET}/baseball/lakehouse_delta"

# ── Phase 1 (E11.20-P1): the W1 pitch-mart family ──────────────────────────────────────
# Chosen per the spike's rollout guidance (hot/high-churn first, not a big-bang): the 7
# W1 pitch marts are the highest-volume tables in the daily rebuild, are pure row-local
# pitch-level projections of stg_batter_pitches (zero window functions — verified
# 2026-07-10 — so a season-partition rebuild is value-identical), and have NO
# request-time reader outside the shared read helpers.
DELTA_W1_TABLES = frozenset({
    "mart_pitch_characteristics",
    "mart_pitch_play_event",
    "mart_pitch_game_context",
    "mart_pitch_fielding",
    "mart_pitch_hitter_profile",
    "mart_pitch_pitcher_profile",
    "mart_pitch_hit_characteristics",
})

# Every phase-1 table is partitioned by season — the MERGE/overwrite predicate must pin
# this column so the daily write stays O(current season), never O(history) (spike gotcha
# #8: a non-partition-aware predicate scans the whole table and forfeits the win).
DELTA_PARTITION_COL = "game_year"

# Spike gotcha #3 (INC-20 cure with teeth): vacuum below 168h physically deletes the
# files older versions point to → time-travel/point-in-time BREAKS. 168h is the FLOOR,
# enforced by scripts/utils/delta_lake.compact_and_vacuum + a fast-gate guard test.
DELTA_MIN_RETENTION_HOURS = 168

DELTA_W1_MODE_ENV = "LAKEHOUSE_DELTA_W1"
_VALID_MODES = ("off", "mirror", "cutover")


def delta_w1_mode() -> str:
    """The W1-family rollout mode: 'off' | 'mirror' | 'cutover' (default 'off')."""
    mode = os.environ.get(DELTA_W1_MODE_ENV, "off").strip().lower() or "off"
    if mode not in _VALID_MODES:
        raise ValueError(
            f"{DELTA_W1_MODE_ENV}={mode!r} is not one of {_VALID_MODES} — refusing to "
            f"guess (a typo'd cutover flag silently reading as 'off' is the "
            f"'silently never runs' outage class)."
        )
    return mode


def delta_write_enabled(table: str) -> bool:
    """True when the daily build should WRITE `table` to Delta (mirror or cutover)."""
    return table in DELTA_W1_TABLES and delta_w1_mode() in ("mirror", "cutover")


def delta_read_enabled(table: str) -> bool:
    """True when readers should resolve `table` via delta_scan instead of the legacy
    lakehouse/<table>/**/*.parquet glob (cutover only — in mirror mode parquet stays
    authoritative so the parallel window is value-identical to production)."""
    return table in DELTA_W1_TABLES and delta_w1_mode() == "cutover"


def delta_table_uri(table: str) -> str:
    """The S3 URI of a Delta table (the directory holding _delta_log/)."""
    return f"{LAKEHOUSE_DELTA}/{table}"


def delta_scan_view_sql(table: str) -> str:
    """The CREATE-VIEW body for a Delta-backed table (DuckDB `delta` extension —
    READ-ONLY, the spike's roadmap correction: DuckDB cannot WRITE Delta)."""
    return f"SELECT * FROM delta_scan('{delta_table_uri(table)}')"


# ── Reader-side routing (E11.20 phase 1.5, 2026-07-20 — the post-drop outage cure) ──────
# Every DuckDB consumer that registers a lakehouse table as a bare-name view MUST route
# through lakehouse_view_sql(). Phase 1.5 DELETED the legacy/compat parquet under
# lakehouse/<w1 table>/ (the SF ext tables that needed it are dropped), so a hardcoded
# `read_parquet('<lakehouse>/<table>/**/*.parquet')` on a W1 mart now raises
# "IO Error: No files found that match the pattern" — which is exactly how the daily job
# broke on 2026-07-20 (generate_matchup_signals_op died → predict_today never ran → a
# whole slate served nothing). Under cutover the W1 marts live ONLY in Delta.
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"


def lakehouse_view_sql(table: str) -> str:
    """The CREATE-VIEW body for ANY lakehouse table, routed by storage backend: Delta
    (delta_scan) for a cut-over W1 mart, the parquet glob for everything else. Callers
    must load the DuckDB `delta` extension first — use ensure_delta_extension(conn)."""
    if delta_read_enabled(table):
        return delta_scan_view_sql(table)
    return f"SELECT * FROM read_parquet('{LAKEHOUSE}/{table}/**/*.parquet', union_by_name=true)"


def ensure_delta_extension(conn) -> None:
    """Load the read-only DuckDB `delta` extension when any cut-over table may be read.
    Best-effort by design: on a build with no delta extension available this leaves the
    connection usable for pure-parquet reads instead of hard-failing at connect time."""
    if delta_w1_mode() != "cutover":
        return
    try:
        conn.execute("INSTALL delta; LOAD delta")
    except Exception:  # noqa: BLE001 — surfaced later by the delta_scan itself
        pass


def register_lakehouse_views(conn, tables) -> None:
    """Register each table as a bare-name DuckDB view over its correct backend."""
    ensure_delta_extension(conn)
    for name in tables:
        conn.execute(f"CREATE OR REPLACE VIEW {name} AS {lakehouse_view_sql(name)}")
