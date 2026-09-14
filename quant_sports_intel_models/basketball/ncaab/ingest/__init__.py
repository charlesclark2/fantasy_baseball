"""NCAAB lakehouse ingest package (NCAAB-P0).

Instantiates the SHARED `sport_data_platform.md` pattern for college basketball. Only
`sources.py` (the per-sport table registry) and `credit_probe.py` (the per-sport odds
budget measurement) are NCAAB-specific.

⛔ THIS PACKAGE DELIBERATELY SHIPS NO `s3io.py` / `handler.py` / `query_lake.py` COPY.
`sport_data_platform.md` §2 sanctioned "copy or symlink across sports" and the NCAAF
package's own docstring asked for the modules to be "lift[ed] to a shared package when
NFL/NCAAB instantiate". NFL copied instead, and the two copies have since DIVERGED — 216
differing lines in `s3io.py` alone, where the NFL copy carries the INC-45 DuckDB-secret
cure and two typed-write hardenings the NCAAF copy never received. A third copy here would
be a third owner of one logical thing (the INC-30 / INC-36 / INC-38 class the NCAAB-P0
spec names in its first paragraph), and it would be seeded from whichever copy the author
happened to open.

So NCAAB IMPORTS the lake layer rather than copying it, and it imports the NFL copy
specifically because that is already the DE-FACTO canonical one: the cross-cutting
monitors (`betting_ml/monitoring/sports_delta_freshness.py`,
`scripts/check_artifact_freshness.py`) import `football.nfl.ingest.s3io` to read the lake
for EVERY sport, and `betting_ml/tests/test_inc45_lake_read_channel.py` pins it as the
INC-45 owner. `football.nfl.ingest.s3io` is sport-agnostic in fact as well as in name —
`sport` is a parameter on every public function and the module holds no NFL constants.

The module PATH is a naming wart (basketball importing from football), not a coupling
defect. Relocating the shared layer to a neutral package and migrating NCAAF + NFL onto it
is a cross-vertical change touching two in-season verticals, so it is recorded as a P0
follow-up for the PM rather than performed here. `lake.py` is the one seam that has to
change when it happens.
"""
