"""Edge Program E13.10 — ZONE-MATCHUP.

Build leak-clean batter zone-value profiles and pitcher location/arsenal profiles from the
LAKEHOUSE (S3 + duckdb, NOT Snowflake), then:

  * TRACK A (guaranteed): the marketable batter-hot-zone × pitcher-tendency OVERLAY heatmap —
    viz data (JSON) + a static rendering proof + an app-handoff spec. Ships regardless of edge.
  * TRACK B (gated bonus, honest-null-expected): a single zone-overlap scalar matchup feature,
    tested for INCREMENTAL lift over Stuff+/archetype/platoon via the E13.4 lift harness.

The profiles are built ONCE and serve both tracks (the E13.10 §"build the profiles once" rule).

Pure-logic primitives live in `grid` (binning), `shrink` (empirical-Bayes), and `overlap`
(the scalar) — all unit-tested in betting_ml/tests/test_zone_matchup.py without S3. The duckdb
aggregation lives in `lakehouse`; viz in `viz`; the operator CLI in build_zone_matchup.py.
"""
