#!/usr/bin/env python3
"""
build_ref_players_dimension.py
==============================
Rebuild the ``stg_ref_players`` player-name dimension from a LIVE source, replacing a
one-shot manual mirror of a Snowflake table that has itself been frozen since 2025-10-13.

WHY THIS EXISTS (E5.10 → this story; INC-27 / NF-INFRA1 class)
-------------------------------------------------------------
``stg_ref_players`` was written by ``scripts/export_ref_players_to_s3.py``, a job whose own
docstring said "Run ONCE … re-run when ref_players changes". It was referenced by NO pipeline
op, schedule or workflow, so nothing ever re-ran it. E5.10 found the parquet 53 days stale and
holding ZERO players with ``mlb_played_last = 2026``; a writer that named batters from it
silently skipped 34.

⭐ THE MEASUREMENT THAT CHANGED THE FIX, and the reason "just schedule the export" is WRONG:
   the SNOWFLAKE SOURCE IS ITSELF DEAD. ``baseball_data.savant.ref_players`` reports
   ``last_altered = 2025-10-13`` (~308 days, not 53) and ``max(mlb_played_last) = 2025``, and a
   whole-repo grep finds NO writer to it — no ingest, no dbt model, no op. The S3 parquet was a
   FAITHFUL MIRROR OF A DEAD TABLE. Scheduling the existing export would therefore have refreshed
   the object's mtime while the CONTENT stayed 2025, and — worse — an INC-41 freshness SLA laid on
   top of that would have read GREEN forever on dead data. That is the exact shape INC-41 warns
   about ("a re-copied object carries a fresh mtime even when the DATA is unchanged"), arrived at
   from the writer side instead of the reader side. A scheduled writer is only a fix when it has
   something live to write.

THE SOURCES, AND WHY BOTH LAYERS ARE NEEDED (measured 2026-08-17, whole Statcast history)
------------------------------------------------------------------------------------------
Distinct players appearing in ``stg_batter_pitches`` as a batter or a pitcher, split by debut era,
counting how many each candidate source MISSES:

    debut era      players    frozen ref_players misses    live player_profiles misses
    2020+            1,751                          208                              4
    pre-2020         2,475                            0                            471

The two sources are COMPLEMENTARY, which is the whole design:
  * the frozen export is a COMPLETE HISTORICAL ARCHIVE (0 misses pre-2020) that stopped advancing;
  * ``player_profiles_raw`` is LIVE (weekly ``ingest_player_profiles.py update`` +
    ``reexport_player_profiles_op``'s daily S3 mirror leaf, E11.24 Bundle) but only covers 2020+
    by construction — its backfill was seeded from ``mart_pitch_play_event WHERE game_year >= 2020``.

So this builder LAYERS them: live takes precedence, the archive fills the pre-2020 tail. On the
2026 slate specifically, 204 of the 208 players the archive misses (98.1%) are in live profiles.

⭐ WHY REBUILD THE ARTIFACT RATHER THAN REPOINT THE ~11 CONSUMERS
   Most consumers do not read the dbt model — they read the S3 PREFIX directly as a raw string
   (``.../lakehouse/stg_ref_players/**/*.parquet``) from a clustering script, a prop-substrate
   builder or a zone-overlay writer. Fixing the dimension AT ITS PREFIX therefore repairs every
   one of them with ZERO consumer edits and ONE column contract, instead of 11 independent name
   resolutions each free to drift (the E9.61 "two renderers of one field are two rule sets"
   lesson). The consumer set is pinned in
   ``betting_ml/tests/test_stg_ref_players_consumers.py``.

COLUMN CONTRACT — DELIBERATELY UNCHANGED
----------------------------------------
Emits exactly the six columns ``stg_ref_players`` has always emitted, so no consumer, no dbt
model and no mart column list moves:

    mlb_bam_id, first_name, last_name, player_name, mlb_played_first, mlb_played_last

plus ONE additive column, ``built_at`` — the INC-41 content timestamp, read from INSIDE the
parquet (never an S3 ``LastModified``; ``aws s3 ls`` prints shell-LOCAL time and an atomic
server-side copy refreshes the mtime on unchanged data).

⛔ NAMES ARE NEVER SPLIT FROM A FULL NAME.
   ``player_profiles_raw`` carries ``full_name`` ("First Last"). Deriving ``last_name`` by
   splitting it is wrong for "Vladimir Guerrero Jr." and every multi-word surname — the exact
   name-mangling class that has already cost this repo two investigations (NF-C0e's wrong key
   map, E9.61's "MacK Hollins"/"Ceedee Lamb"). Name PARTS therefore come only from a source that
   states them: ``player_profiles_raw.first_name/last_name`` once
   ``ingest_player_profiles.py`` captures them from the StatsAPI ``/people`` payload (which has
   always returned ``firstName``/``lastName`` — the ingest simply discarded them), else the
   archive's own parts, else NULL. A player with a known ``full_name`` but no parts gets a
   correct ``player_name`` and NULL parts, which is strictly better than being absent entirely.

   Because that ingest column is rolling out behind this change, the builder DETECTS which name
   columns the live parquet actually has and adapts. It never assumes.

``mlb_played_first`` / ``mlb_played_last`` are derived LIVE from the game data (min/max
``game_year`` over ``batter_id ∪ pitcher_id``), which is precisely what they mean, falling back
to the archive for players with no Statcast appearance. This is what makes
``mlb_played_last = 2026`` true again — the E5.10 symptom.

Usage
-----
    uv run python scripts/build_ref_players_dimension.py
    uv run python scripts/build_ref_players_dimension.py --dry-run
    uv run python scripts/build_ref_players_dimension.py --min-current-season-players 300
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

# Snowflake-FREE by construction: DuckDB over S3 only. Importing this module must not pull in
# snowflake.connector (this runs as a fan-out leaf in a box job that already carries enough).
from scripts.utils import lakehouse_read as lk  # noqa: E402

# ── Locations ────────────────────────────────────────────────────────────────────────────────
# The OUTPUT prefix is the one every consumer already reads — that is the point.
OUTPUT_PREFIX = "stg_ref_players"
OUTPUT_KEY = "baseball/lakehouse/stg_ref_players/part-0.parquet"

# The frozen historical layer, moved OFF the live prefix so that the archive can never again be
# mistaken for a live table. `export_ref_players_to_s3.py` writes here and nothing else does.
ARCHIVE_PREFIX = "stg_ref_players_archive"

LIVE_PREFIX = "player_profiles_raw"
GAME_PREFIX = "stg_batter_pitches"

S3_BUCKET = "baseball-betting-ml-artifacts"

# The six-column contract, in order. Pinned by the consumer guard.
CONTRACT_COLUMNS = (
    "mlb_bam_id",
    "first_name",
    "last_name",
    "player_name",
    "mlb_played_first",
    "mlb_played_last",
)


#: Every lakehouse table this builder reads. Registered as DuckDB views through the SHARED
#: registry (`lakehouse_read.register_views`) rather than a hardcoded `**/*.parquet` glob.
#: ⚠️ THIS IS LOAD-BEARING, NOT STYLE. `stg_batter_pitches` is Delta-backed under
#: `LAKEHOUSE_DELTA_W1=cutover`, where the legacy compat parquet is FROZEN and was ultimately
#: DELETED — E11.20 phase-1.5 took a ZERO-PREDICTION SLATE (P0) precisely because several readers
#: had been pointed at that legacy PATH instead of the registry. `register_views` routes a
#: Delta-backed table via `delta_scan` and everything else via the glob, so a future layout move
#: reaches this builder for free. `test_lakehouse_reader_delta_routing.py` fails any new
#: hardcoded W1 glob.
SOURCE_TABLES = (LIVE_PREFIX, ARCHIVE_PREFIX, GAME_PREFIX)


def _columns_of(conn, table: str) -> set[str]:
    """Column names present in a registered lakehouse view, lowercased. Empty set if unreadable.

    Used to ADAPT rather than assume: `player_profiles_raw` gains first_name/last_name only once
    the ingest change has shipped AND its mirror has re-exported, and this builder must be
    correct on both sides of that rollout.
    """
    try:
        rows = conn.execute(f"describe select * from {table}").fetchall()
    except Exception as exc:  # pragma: no cover — exercised on the box, not in CI
        print(f"  [warn] cannot describe {table}: {exc}")
        return set()
    return {str(r[0]).lower() for r in rows}


def build_sql(live_cols: set[str], *, current_season: int) -> str:
    """The merge query.

    Layering, per column:
      identity   live ∪ archive (full outer on the player id)
      name parts live parts → archive parts → NULL      (⛔ never split a full name)
      player_name  "Last, First" when parts are known → live full_name → archive player_name
      played_first/last  derived from the game data → archive
    """
    # Only reference live name-part columns that actually exist in the parquet today.
    # ⚠️ BARE column names, NOT `l.`-qualified: these are interpolated into the INNER `live`
    # subquery, whose only table is {LIVE_PREFIX} — the `l` alias belongs to the OUTER join and is
    # not in scope here. The first cut wrote `l.first_name` and bound fine for weeks, because the
    # `cast(null as varchar)` fallback carries no alias and the pre-backfill smoke only ever
    # exercised THAT branch. The aliased branch first ran in production, where it raised
    # `Binder Error: Referenced table "l" not found`. A conditional whose other arm is never
    # invoked is untested however green the suite looks (NF-C0e "wired ≠ invoked"), which is why
    # test_ref_players_dimension_build.py now runs BOTH arms through real DuckDB.
    live_first = "first_name" if "first_name" in live_cols else "cast(null as varchar)"
    live_last = "last_name" if "last_name" in live_cols else "cast(null as varchar)"

    return f"""
    with live as (
        -- Latest profile row per player (the raw table is append-only; the dbt staging model
        -- dedupes the same way).
        select * from (
            select
                cast(player_id as bigint)              as mlb_bam_id,
                full_name,
                {live_first}                           as first_name,
                {live_last}                            as last_name,
                row_number() over (
                    partition by player_id
                    order by try_cast(last_fetched_at as timestamp) desc nulls last
                ) as rn
            from {LIVE_PREFIX}
            where player_id is not null
        ) where rn = 1
    ),

    archive as (
        select
            cast(mlb_bam_id as bigint)                 as mlb_bam_id,
            any_value(first_name)                      as first_name,
            any_value(last_name)                       as last_name,
            any_value(player_name)                     as player_name,
            max(try_cast(mlb_played_first as double))  as mlb_played_first,
            max(try_cast(mlb_played_last  as double))  as mlb_played_last
        from {ARCHIVE_PREFIX}
        where mlb_bam_id is not null
        group by 1
    ),

    -- mlb_played_first/last mean "first/last MLB season the player appeared", so derive them
    -- from the appearances themselves. This is the column E5.10 found frozen at 2025.
    appearances as (
        select id as mlb_bam_id, min(game_year) as played_first, max(game_year) as played_last
        from (
            select cast(batter_id  as bigint) id, cast(game_year as integer) game_year
            from {GAME_PREFIX}
            where batter_id is not null
            union all
            select cast(pitcher_id as bigint), cast(game_year as integer)
            from {GAME_PREFIX}
            where pitcher_id is not null
        )
        group by 1
    ),

    ids as (
        select mlb_bam_id from live
        union
        select mlb_bam_id from archive
    )

    select
        i.mlb_bam_id,
        coalesce(l.first_name, a.first_name)                       as first_name,
        coalesce(l.last_name,  a.last_name)                        as last_name,
        -- Prefer the canonical "Last, First" the archive has always emitted; fall back to the
        -- live display name when parts are unknown (documented in schema.yml — the downstream
        -- name normaliser in betting_ml/utils/prop_edge.py already handles BOTH formats).
        coalesce(
            case
                when coalesce(l.first_name, a.first_name) is not null
                 and coalesce(l.last_name,  a.last_name)  is not null
                then coalesce(l.last_name, a.last_name) || ', ' || coalesce(l.first_name, a.first_name)
            end,
            a.player_name,
            l.full_name
        )                                                          as player_name,
        coalesce(cast(ap.played_first as double), a.mlb_played_first) as mlb_played_first,
        coalesce(cast(ap.played_last  as double), a.mlb_played_last)  as mlb_played_last,
        cast('{datetime.now(timezone.utc).isoformat(timespec='seconds')}' as varchar) as built_at
    from ids i
    left join live        l  on l.mlb_bam_id  = i.mlb_bam_id
    left join archive     a  on a.mlb_bam_id  = i.mlb_bam_id
    left join appearances ap on ap.mlb_bam_id = i.mlb_bam_id
    """


def current_season(now: datetime | None = None) -> int:
    """The season the dimension is expected to cover.

    Uses the US baseball day (game_day.current_game_date), never a UTC date — the box runs UTC and
    a UTC "today" rolls to tomorrow during US evening games (INC-22).
    """
    if now is not None:
        return now.year
    try:
        from betting_ml.utils.game_day import current_game_date

        return current_game_date().year
    except Exception:  # pragma: no cover — helper is always importable in-repo
        return datetime.now(timezone.utc).year


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Rebuild the stg_ref_players dimension from live sources (E5.10 follow-up)"
    )
    ap.add_argument("--dry-run", action="store_true", help="Build and report; no S3 write")
    ap.add_argument(
        "--min-current-season-players",
        type=int,
        default=200,
        help=(
            "Coverage floor: refuse to publish a dimension carrying fewer than this many players "
            "whose mlb_played_last is the current season. Guards the exact defect this story "
            "fixes — a dimension that BUILDS but carries no current-season players."
        ),
    )
    args = ap.parse_args()

    season = current_season()
    print(f"stg_ref_players dimension rebuild — live profiles over frozen archive (season {season})")

    conn = lk.duck_connect()
    # Route every source through the shared registry (Delta-aware) — see SOURCE_TABLES.
    lk.register_views(conn, SOURCE_TABLES)

    live_cols = _columns_of(conn, LIVE_PREFIX)
    if not live_cols:
        print("[ERROR] live player_profiles_raw is unreadable — refusing to rebuild the dimension.")
        print("        Publishing from the archive alone would silently reinstate the frozen table.")
        return 1
    has_parts = {"first_name", "last_name"} <= live_cols
    print(
        f"  live name parts available: {has_parts}"
        + ("" if has_parts else "  (falling back to archive parts; ⛔ full_name is NOT split)")
    )

    if not _columns_of(conn, ARCHIVE_PREFIX):
        print(f"[ERROR] frozen archive prefix '{ARCHIVE_PREFIX}' is unreadable.")
        print("        Run: uv run python scripts/export_ref_players_to_s3.py   (one-time seed)")
        return 1

    df = conn.execute(build_sql(live_cols, current_season=season)).df()
    print(f"  merged dimension: {len(df):,} players")

    n_current = int((df["mlb_played_last"] == season).sum())
    n_named = int(df["player_name"].notna().sum())
    n_parts = int((df["first_name"].notna() & df["last_name"].notna()).sum())
    print(f"  players with mlb_played_last = {season}: {n_current:,}")
    print(f"  players with a display name: {n_named:,}  |  with first+last parts: {n_parts:,}")
    print(f"[METRIC] ref_players_rows={len(df)}")
    print(f"[METRIC] ref_players_current_season={season}")
    print(f"[METRIC] ref_players_current_season_players={n_current}")

    # ── Publish guard (NF-K1): count the rows that CARRY THE VALUE, never just the rows. ──
    # A row-count check is satisfied by an archive-only rebuild, which is exactly the broken
    # artifact this story exists to prevent republishing.
    if n_current < args.min_current_season_players:
        print(
            f"[ERROR] REFUSING TO PUBLISH: only {n_current} players carry "
            f"mlb_played_last={season}, below the floor of {args.min_current_season_players}. "
            "That is the E5.10 signature (a dimension that builds but knows no current players). "
            "Check that player_profiles_raw and stg_batter_pitches are both current."
        )
        return 1

    if args.dry_run:
        print("  dry-run — no S3 write")
        return 0

    import pyarrow as pa
    import pyarrow.parquet as pq

    tmp = Path("/tmp/stg_ref_players_dimension.parquet")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), str(tmp))

    # INC-16 / AKID: pass explicit keys ONLY when both are present, else let boto3 resolve the
    # EC2 instance role. Passing aws_access_key_id=None DISABLES the default chain.
    from scripts.utils.lakehouse_raw_writer import make_s3_client

    s3 = make_s3_client()
    print(f"  uploading → s3://{S3_BUCKET}/{OUTPUT_KEY}")
    s3.upload_file(str(tmp), S3_BUCKET, OUTPUT_KEY)
    tmp.unlink(missing_ok=True)

    print(f"\nDimension rebuild complete — {len(df):,} players, {n_current:,} current-season.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
