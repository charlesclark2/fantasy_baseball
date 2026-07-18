"""query_lake.py  (NFL-N0.2 — the DuckDB-over-lake parity tool, sport_data_platform.md §7A)
============================================================================================
Query the NFL lake via DuckDB with ZERO connection boilerplate — the parity tool to the
Snowflake MCP (no warehouse to resume, no credits, instant). Every later NFL session explores
the lake through here.

  from quant_sports_intel_models.football.nfl.ingest.query_lake import q, delta
  q("select season, count(*) from delta('schedules') group by 1 order by 1")
  q("select player_display_name, passing_yards from delta('stats_player_week') "
    "where season=2024 order by passing_yards desc limit 5")

`delta(source)` expands to `delta_scan('s3://<bucket>/nfl/raw/<source>')`. The raw tier is
Delta, so reads go through DuckDB's (read-only) `delta` extension. AWS creds resolve via the
credential chain (same instance-role / env the writers use); region is pinned per resource.
"""
from __future__ import annotations

from . import s3io

_con = None


def _connect():
    global _con
    if _con is not None:
        return _con
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs")
    con.execute("INSTALL delta; LOAD delta")
    con.execute(
        f"CREATE OR REPLACE SECRET sports_s3 "
        f"(TYPE S3, PROVIDER credential_chain, REGION '{s3io.DEFAULT_REGION}')"
    )
    _con = con
    return con


def delta(source: str, *, sport: str = "nfl", tier: str = "raw", bucket: str | None = None) -> str:
    """A `delta_scan(...)` expression for a lake source — drop it into a FROM clause."""
    uri = s3io.table_uri(sport, source, bucket=bucket or s3io.DEFAULT_BUCKET, tier=tier)
    return f"delta_scan('{uri}')"


def local(source: str, root: str, *, sport: str = "nfl", tier: str = "raw") -> str:
    """A `delta_scan(...)` for a LOCAL-FS Delta table (the offline smoke output)."""
    return f"delta_scan('{s3io.local_table_uri(root, sport, source, tier=tier)}')"


def q(sql: str):
    """Run SQL against the lake; returns a pandas DataFrame. Use delta('<source>') in FROM."""
    return _connect().sql(sql).df()
