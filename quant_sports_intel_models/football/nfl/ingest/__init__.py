"""NFL lakehouse ingest package (NFL-N0.2).

Registry-driven ingest → S3 Delta lake → dbt-duckdb staging, instantiating the SHARED
`sport_data_platform.md` pattern for NFL (the 2nd sport after NCAAF-P0.2). `s3io` / `handler` /
`backfill` / `query_lake` are sport-agnostic boilerplate copied from NCAAF (§2 "copy or symlink
across sports"); only `sources.py` (the nflverse + Odds API registry) is NFL-specific.

NFL diverges from NCAAF in ONE structural way: nflverse data is TYPED release Parquet (read via
DuckDB, landed via `s3io.write_dataframe` as typed Delta), not JSON — so the whole 145-col
player stack / 372-col PBP lands with columns preserved, and the staging is plain renames, not
`json_extract`. The Odds API feeds stay JSON (`write_records` / raw_json), like NCAAF.
"""
