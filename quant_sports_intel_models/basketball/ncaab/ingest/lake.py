"""lake.py — NCAAB's ONE seam onto the shared sport lake layer.

Every NCAAB module that writes or reads the lake imports from HERE, never from a football
package directly. That keeps the awkward import path (`football.nfl.ingest.s3io`, chosen
because the cross-cutting monitors already treat it as canonical — see this package's
`__init__` docstring) in a single file, so relocating the shared layer to a neutral package
later is a one-file change in this vertical instead of a grep-and-pray across it.

⛔ Do NOT add a `s3io.py` to this package. If the shared layer needs a behaviour NCAAB
wants, change it in the shared owner (and run the NFL + NCAAF scaffold suites, which pin
its output — the MH2.7 "changing a shared instrument requires grepping cross-vertical
guards" rule), or wrap it here. A local copy is a fourth owner.
"""
from __future__ import annotations

# The de-facto canonical, INC-45-cured, sport-agnostic lake layer. `sport` is a parameter
# on every public function; the module holds no NFL constants.
from quant_sports_intel_models.football.nfl.ingest import s3io

#: The lake's sport prefix. Everything NCAAB writes lands under `s3://<bucket>/ncaab/…`.
SPORT = "ncaab"

# Re-exported so NCAAB callers never name the football path themselves.
DEFAULT_BUCKET = s3io.DEFAULT_BUCKET
DEFAULT_REGION = s3io.DEFAULT_REGION
PARTITION_COL = s3io.PARTITION_COL

storage_options = s3io.storage_options
records_to_arrow = s3io.records_to_arrow
write_season_partition = s3io.write_season_partition
existing_seasons = s3io.existing_seasons
configure_duckdb_lake_auth = s3io.configure_duckdb_lake_auth
duckdb_lake_connection = s3io.duckdb_lake_connection


def table_uri(source: str, *, bucket: str | None = None, tier: str = "raw") -> str:
    """The Delta table directory for one NCAAB `source`, with the sport pinned."""
    return s3io.table_uri(SPORT, source, bucket=bucket or DEFAULT_BUCKET, tier=tier)


def local_table_uri(root: str, source: str, *, tier: str = "raw") -> str:
    """A local-FS Delta path for the offline smoke (delta-rs writes local identically)."""
    return s3io.local_table_uri(root, SPORT, source, tier=tier)


def write_records(records, *, source: str, season: int, week: int | None = None,
                  bucket: str | None = None, local_root: str | None = None,
                  tier: str = "raw") -> int:
    """Land raw JSON records for one NCAAB (source, season) as a Delta season partition."""
    return s3io.write_records(
        records, sport=SPORT, source=source, season=season, week=week,
        bucket=bucket or DEFAULT_BUCKET, local_root=local_root, tier=tier,
    )


def write_dataframe(df, *, source: str, season: int, bucket: str | None = None,
                    local_root: str | None = None, tier: str = "raw") -> int:
    """Land a TYPED pandas DataFrame (an hoopR/ESPN slice) as a Delta season partition."""
    return s3io.write_dataframe(
        df, sport=SPORT, source=source, season=season,
        bucket=bucket or DEFAULT_BUCKET, local_root=local_root, tier=tier,
    )
