"""
training_cache.py — Parquet-based caching layer for Snowflake training queries.

Pattern:
    from betting_ml.utils.training_cache import get_cached_df

    df = get_cached_df(
        cache_key="run_env_training",
        pull_fn=load_training_data,
        max_age_hours=24,
        refresh=args.refresh_cache,
    )

On first call (or when cache is stale / refresh=True):
  - Calls pull_fn() to fetch from Snowflake
  - Saves result to betting_ml/data/cache/{cache_key}.parquet
  - Writes a sidecar {cache_key}.meta.json with timestamp and row count

On subsequent calls within max_age_hours:
  - Reads from Parquet — zero Snowflake credits consumed
  - Prints cache hit message with age

DuckDB shortcut (for exploratory SQL on cached data):
    from betting_ml.utils.training_cache import duckdb_on_cache

    con = duckdb_on_cache("run_env_training")
    con.execute("SELECT game_date, AVG(total_runs) FROM df GROUP BY 1 ORDER BY 1")

Requires duckdb to be installed; falls back to pandas if not available.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

_CACHE_DIR = Path(__file__).resolve().parents[2] / "betting_ml" / "data" / "cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(cache_key: str) -> Path:
    return _CACHE_DIR / f"{cache_key}.parquet"


def _meta_path(cache_key: str) -> Path:
    return _CACHE_DIR / f"{cache_key}.meta.json"


def _cache_age_hours(cache_key: str) -> float | None:
    """Return age of cache in hours, or None if no cache exists."""
    meta = _meta_path(cache_key)
    if not meta.exists():
        return None
    data = json.loads(meta.read_text())
    saved_at = datetime.fromisoformat(data["saved_at"])
    return (datetime.now(timezone.utc) - saved_at).total_seconds() / 3600


def _save_cache(df: pd.DataFrame, cache_key: str) -> None:
    df.to_parquet(_cache_path(cache_key), index=False, engine="pyarrow")
    meta = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "rows": len(df),
        "columns": list(df.columns),
    }
    _meta_path(cache_key).write_text(json.dumps(meta, indent=2))


def get_cached_df(
    cache_key: str,
    pull_fn: Callable[[], pd.DataFrame],
    max_age_hours: float = 24.0,
    refresh: bool = False,
) -> pd.DataFrame:
    """Return a DataFrame, reading from Parquet cache when fresh.

    Args:
        cache_key: Identifier for the cache file (e.g. "run_env_training").
        pull_fn: Zero-argument callable that fetches data from Snowflake.
        max_age_hours: Cache is considered stale after this many hours.
        refresh: If True, bypass cache and re-pull from Snowflake.
    """
    age = _cache_age_hours(cache_key)
    cache_file = _cache_path(cache_key)

    if not refresh and age is not None and age < max_age_hours and cache_file.exists():
        print(
            f"[cache] HIT {cache_key} "
            f"({age:.1f}h old, {pd.read_parquet(cache_file).shape[0]:,} rows) "
            f"— skipping Snowflake"
        )
        return pd.read_parquet(cache_file, engine="pyarrow")

    reason = "refresh requested" if refresh else ("no cache" if age is None else f"stale ({age:.1f}h)")
    print(f"[cache] MISS {cache_key} ({reason}) — pulling from Snowflake...")
    df = pull_fn()
    _save_cache(df, cache_key)
    print(f"[cache] Saved {len(df):,} rows → {cache_file}")
    return df


def duckdb_on_cache(cache_key: str):
    """Return a DuckDB connection with the cached Parquet registered as 'df'.

    Usage:
        con = duckdb_on_cache("run_env_training")
        result = con.execute("SELECT COUNT(*) FROM df").fetchdf()

    Raises ImportError if duckdb is not installed.
    """
    try:
        import duckdb
    except ImportError:
        print(
            "duckdb is not installed. Run: uv add duckdb",
            file=sys.stderr,
        )
        raise

    cache_file = _cache_path(cache_key)
    if not cache_file.exists():
        raise FileNotFoundError(
            f"No cache found for '{cache_key}'. "
            f"Call get_cached_df() first to populate the cache."
        )

    con = duckdb.connect()
    con.execute(f"CREATE VIEW df AS SELECT * FROM read_parquet('{cache_file}')")
    return con


def list_caches() -> None:
    """Print all cached datasets with their age and row counts."""
    metas = sorted(_CACHE_DIR.glob("*.meta.json"))
    if not metas:
        print("No caches found.")
        return

    print(f"{'Cache key':<35} {'Age':>8} {'Rows':>10}  Path")
    print("-" * 80)
    for meta_file in metas:
        key = meta_file.stem.replace(".meta", "")
        data = json.loads(meta_file.read_text())
        saved_at = datetime.fromisoformat(data["saved_at"])
        age_h = (datetime.now(timezone.utc) - saved_at).total_seconds() / 3600
        age_str = f"{age_h:.1f}h" if age_h < 48 else f"{age_h / 24:.1f}d"
        print(f"{key:<35} {age_str:>8} {data['rows']:>10,}  {_cache_path(key)}")


if __name__ == "__main__":
    list_caches()
