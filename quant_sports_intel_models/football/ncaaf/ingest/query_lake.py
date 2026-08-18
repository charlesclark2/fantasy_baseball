"""query_lake.py  (NCAAF-P0.2 — the DuckDB-over-lake parity tool, sport_data_platform.md §7A)
==============================================================================================
The first-class dev-loop affordance: query the sports lake via DuckDB with ZERO connection
boilerplate — the parity tool to the Snowflake MCP (there is no warehouse to resume, no
credits, instant). Every later NCAAF session explores the lake through here.

  from quant_sports_intel_models.football.ncaaf.ingest.query_lake import q, delta
  q("select season, count(*) from delta('games') group by 1 order by 1")
  q("select raw_json->>'homeTeam' t from delta('games') limit 5")

`delta(source)` expands to `delta_scan('s3://<bucket>/ncaaf/raw/<source>')`. The raw tier is
Delta, so reads go through DuckDB's (read-only) `delta` extension. AWS creds resolve via the
credential chain (same instance-role / env the writers use); region is pinned per resource.
"""
from __future__ import annotations

import logging
import os

from . import s3io

log = logging.getLogger(__name__)

_con = None


def _connect():
    global _con
    if _con is not None:
        return _con
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs")
    con.execute("INSTALL delta; LOAD delta")
    try:
        con.execute(
            f"CREATE OR REPLACE SECRET sports_s3 "
            f"(TYPE S3, PROVIDER credential_chain, REGION '{s3io.DEFAULT_REGION}')"
        )
    except Exception as exc:  # noqa: BLE001 — best-effort; see note below
        # `credential_chain` VALIDATES eagerly at CREATE-SECRET time, so an environment with NO
        # AWS credential source anywhere (env / profile / IMDS role — e.g. a CI sandbox that
        # intentionally mocks all external IO) fails HERE, before any query even runs. A query
        # that only reads a LOCAL path (`local()`) never needs this secret, so don't let its
        # absence break local-only usage — a query that DOES need S3 (`delta()`) will still fail
        # naturally, with a clear credentials error, at actual S3 access.
        log.debug("sports_s3 credential-chain secret unavailable (%s) — local-only reads still "
                  "work; an S3 read will fail at actual access, not here.", str(exc)[:160])
    _con = con
    return con


def delta(source: str, *, sport: str = "ncaaf", tier: str = "raw", bucket: str | None = None) -> str:
    """A `delta_scan(...)` expression for a lake source — drop it into a FROM clause."""
    uri = s3io.table_uri(sport, source, bucket=bucket or s3io.DEFAULT_BUCKET, tier=tier)
    return f"delta_scan('{uri}')"


def local(source: str, root: str, *, sport: str = "ncaaf", tier: str = "raw") -> str:
    """A `delta_scan(...)` for a LOCAL-FS Delta table (the offline smoke output)."""
    return f"delta_scan('{s3io.local_table_uri(root, sport, source, tier=tier)}')"


def q(sql: str):
    """Run SQL against the lake; returns a pandas DataFrame. Use delta('<source>') in FROM."""
    return _connect().sql(sql).df()


# ── "absent partition" vs "transient read failure" (the destructive-overwrite guard) ────────
#
# ⭐ ONE implementation, several callers. Every READ-MERGE-WRITE writer in this vertical
# (`odds_recurring_capture`, `game_prediction_snapshot`) preserves what is already in the lake by
# READING it first — so "I could not read it" must NEVER be indistinguishable from "there is
# nothing there yet." The second is a licence to overwrite; the first is a bug that silently
# deletes every prior week. A real CI flake (a read-after-write `delta_scan` hiccup on a partition
# the same run had just written) proved that swallowing any read exception into `None` loses data.
# Two renderers of this rule would be two rule sets (the E9.61 lesson), so it lives here.

#: substrings that mean the Delta table/partition GENUINELY does not exist yet.
MISSING_TABLE_MARKERS: tuple[str, ...] = ("InvalidTableLocationError", "Path does not exist")


def is_missing_table_error(exc: Exception) -> bool:
    """True only when `exc` means the Delta table/partition genuinely doesn't exist yet (a
    source's first-ever write). Anything else — a network hiccup, an extension-load glitch, a
    read-after-write visibility blip — must NOT be mistaken for "nothing's there yet"."""
    msg = str(exc)
    return any(marker in msg for marker in MISSING_TABLE_MARKERS)


def query_or_missing(sql: str, *, retries: int = 2, retry_sleep: float = 0.15):
    """Run a read-only lake SELECT. Returns the DataFrame, or `None` if the table/partition
    genuinely doesn't exist yet. Any OTHER failure is retried a bounded number of times (a
    transient `delta_scan` hiccup usually clears within one retry) and then RAISED — never
    silently swallowed into "nothing there yet."

    A caller that cannot CONFIRM what is already in the lake must fail loud, never guess "empty."
    """
    import time

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return q(sql)
        except Exception as exc:  # noqa: BLE001 — inspected immediately below, never blindly swallowed
            if is_missing_table_error(exc):
                return None
            last_exc = exc
            if attempt < retries:
                try:
                    _connect().execute("LOAD delta")  # defensive re-affirm; cheap, idempotent
                except Exception:  # noqa: BLE001 — best-effort; a persistent problem surfaces below
                    pass
                time.sleep(retry_sleep)
    raise RuntimeError(
        f"lake read failed {retries + 1}x and is NOT a missing-table error — refusing to treat "
        f"this as 'nothing is there yet' (that would risk a destructive merge overwrite): "
        f"{last_exc}"
    ) from last_exc
