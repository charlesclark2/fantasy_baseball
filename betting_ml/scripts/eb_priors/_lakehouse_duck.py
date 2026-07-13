"""
_lakehouse_duck.py — E11.20 phase 1.5: shared DuckDB/S3 routing for the OFFLINE bullpen
eb_priors scripts (compute_bullpen_posteriors / compute_bullpen_v3 / fit_bullpen_priors).

These scripts' aLI/pen queries join the mart_pitch_play_event win-expectancy substrate —
one of the 7 W1 pitch marts whose Snowflake views DROP in the E11.20 phase-1.5
decommission (docs/e11_20_delta_rollout.md §6 step 6). Their `--s3` mode routes that ONE
query per script through DuckDB over the S3 lakehouse; every other read and all writes
stay on Snowflake (the W7a dual-connection pattern).

Kept separate from generate_matchup_signals' canonical W7a helpers because the bullpen
queries read a DIFFERENT view set (mart_starting_pitcher_game_log, mart_game_spine) —
extending the matchup scripts' _S3_SOURCE_TABLES would couple two unrelated read paths.

INC-23 note for callers: parquet `game_date` is VARCHAR ISO in several lakehouse tables —
every game_date comparison in a routed query must cast `::date` at the use site (`::date`
is a no-op when the column is already DATE, so it is always safe to add).
"""
from __future__ import annotations

_LAKEHOUSE = "s3://baseball-betting-ml-artifacts/baseball/lakehouse"

# Every table the bullpen aLI/pen queries touch. All verified present in the lakehouse:
# stg_batter_pitches (W-series flatten), mart_pitch_play_event (W1 — season-bucket compat
# files post-cutover; the **/*.parquet glob matches both layouts), the game log (W2) and
# the spine (W5 Group A, daily-rebuilt).
BULLPEN_SOURCE_TABLES = [
    "mart_pitch_play_event",
    "stg_batter_pitches",
    "mart_starting_pitcher_game_log",
    "mart_game_spine",
]

# The pitcher-clustering stability analysis reads a different pair (W1 + W2).
CLUSTER_STABILITY_TABLES = [
    "mart_pitch_characteristics",
    "mart_pitcher_arsenal_summary",
]

_QUALIFIED = {
    "baseball_data.betting.mart_pitch_play_event": "mart_pitch_play_event",
    "baseball_data.betting.stg_batter_pitches": "stg_batter_pitches",
    "baseball_data.betting.mart_starting_pitcher_game_log": "mart_starting_pitcher_game_log",
    "baseball_data.betting.mart_game_spine": "mart_game_spine",
    "baseball_data.betting.mart_pitch_characteristics": "mart_pitch_characteristics",
    "baseball_data.betting.mart_pitcher_arsenal_summary": "mart_pitcher_arsenal_summary",
}


def get_duckdb():
    """A DuckDB connection with httpfs + the instance-role/ambient credential chain,
    region pinned to the artifacts bucket (mirrors generate_matchup_signals._get_duckdb),
    PLUS the INC-22 memory discipline: the bullpen aLI queries hash-join the full 7.8M-row
    pitch substrate, so cap memory at 60% of RAM (floor 2 / cap 8 GB) and give spillable
    operators a temp_directory — DuckDB's ~80% default swap-froze a laptop on the E11.20
    Delta backfill and OOM-killed the box on INC-22."""
    import os
    import tempfile

    import duckdb

    duck = duckdb.connect()
    duck.execute("INSTALL httpfs; LOAD httpfs")
    duck.execute(
        "CREATE OR REPLACE SECRET baseball_s3 "
        "(TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')"
    )
    try:
        ram_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 ** 3)
        limit = max(2, min(8, int(ram_gb * 0.6)))
    except (ValueError, OSError, AttributeError):
        limit = 4
    spill = os.path.join(tempfile.gettempdir(), "bullpen_duck_spill")
    for _p in ("SET http_timeout=600000", "SET http_retries=8",
               "SET preserve_insertion_order=false", "SET threads=2",
               f"SET memory_limit='{limit}GB'", f"SET temp_directory='{spill}'"):
        try:
            duck.execute(_p)
        except Exception:  # noqa: BLE001 — older DuckDB without the pragma
            pass
    return duck


def register_views(duck, tables: list[str] | None = None) -> None:
    """Register each source table as a bare-name view over its lakehouse glob."""
    for name in (tables if tables is not None else BULLPEN_SOURCE_TABLES):
        glob = f"{_LAKEHOUSE}/{name}/**/*.parquet"
        duck.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_parquet('{glob}', union_by_name=true)"
        )


def rewrite(sql: str) -> str:
    """Point the fully-qualified Snowflake names at the registered bare-name views, and
    translate the one Snowflake-only date function these queries use: DuckDB has
    `datediff` but NOT `dateadd` — `dateadd('day', -N, expr)` becomes
    `(expr - INTERVAL N DAY)` (verified equivalent). Date-literal interpolation and
    ::date casts stay at the CALLER's use sites — the caller knows which comparisons
    cross the VARCHAR/DATE boundary (INC-23)."""
    import re

    for qualified, bare in _QUALIFIED.items():
        sql = sql.replace(qualified, bare)
    sql = re.sub(
        r"dateadd\(\s*'day'\s*,\s*-(\d+)\s*,\s*([A-Za-z_][\w.]*)\s*\)",
        r"(\2 - INTERVAL \1 DAY)",
        sql,
    )
    return sql


def fetch_dicts(duck, sql: str) -> list[dict]:
    cur = duck.execute(sql)
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
