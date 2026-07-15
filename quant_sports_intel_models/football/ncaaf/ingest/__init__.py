"""NCAAF lakehouse ingest package (NCAAF-P0.2).

Registry-driven ingest → S3 Delta lake → dbt-duckdb staging, instantiating the SHARED
`sport_data_platform.md` pattern. `s3io` / `handler` / `backfill` / `query_lake` /
`cfbd_client` are sport-agnostic boilerplate (lift to a shared package when NFL/NCAAB
instantiate — §2 "copy or symlink across sports"); only `sources.py` is NCAAF-specific.
"""
