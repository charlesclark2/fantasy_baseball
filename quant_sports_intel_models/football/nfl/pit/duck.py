"""duck.py — the ONE DuckDB connection factory for the PIT capture legs, with a BOX-AWARE
`memory_limit`.

⛔ NEVER call `duckdb.connect()` directly in this package. A bare connection inherits DuckDB's
DEFAULT limit of ~80% of physical RAM — **~12.8 GB on the box's 16 GB r6g.large** — which is a
promise the box cannot keep, because it is co-resident with the Dagster daemon, Postgres, the
dbt-runner and byparr.

This is INC-22 #4, verbatim: a memory_limit above what the box can actually spare told DuckDB it
never needed to spill, so it blew past physical memory and **the kernel OOM-killed the EC2 host,
taking Dagster with it**. The consequence is not "the NFL capture fails" — it is "MLB serving
loses its scheduler", which is an outage of a different order than anything this package is worth.

The formula mirrors `scripts/run_w1_lakehouse.py::_safe_memory_limit_gb` (60% of RAM, floored at
2 GB, capped at 11 GB, with a conservative 6 GB fallback when RAM is undetectable — e.g. macOS
dev). It is duplicated rather than imported because `run_w1_lakehouse` is a heavyweight
serving-path script and importing it from a capture leg would drag its whole import graph onto
the hourly cron. `threads=2` matches the box's 2 vCPU so a capture cannot starve the daemon of
CPU either (the INC-32 class).
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

#: 60% of physical RAM, floored/capped. Kept in step with `run_w1_lakehouse._safe_memory_limit_gb`.
_RAM_FRACTION = 0.6
_FLOOR_GB = 2
_CAP_GB = 11
_UNKNOWN_RAM_FALLBACK_GB = 6

#: The box is an r6g.large = 2 vCPU. DuckDB otherwise grabs every core.
_THREADS = 2


def _physical_ram_gb() -> float | None:
    """Physical RAM in GB, or None when undetectable. Pure stdlib (the box image has no psutil)."""
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 ** 3)
    except (ValueError, OSError, AttributeError):
        return None


def safe_memory_limit_gb() -> int:
    ram = _physical_ram_gb()
    if ram is None:
        return _UNKNOWN_RAM_FALLBACK_GB
    return max(_FLOOR_GB, min(_CAP_GB, int(ram * _RAM_FRACTION)))


def connect(*, httpfs: bool = True):
    """A DuckDB connection that cannot OOM-kill the box. Use this everywhere in `pit/`.

    `httpfs` is loaded by default because every capture leg reads nflverse release parquet over
    HTTPS. Spillable operators spill under the cap instead of growing without bound.
    """
    import duckdb

    con = duckdb.connect()
    limit = safe_memory_limit_gb()
    con.execute(f"SET memory_limit='{limit}GB'")
    con.execute(f"SET threads={_THREADS}")
    if httpfs:
        con.execute("INSTALL httpfs; LOAD httpfs")
    log.debug("duckdb: memory_limit=%sGB threads=%s", limit, _THREADS)
    return con
