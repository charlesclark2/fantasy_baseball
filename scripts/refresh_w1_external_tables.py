#!/usr/bin/env python3
"""
scripts/refresh_w1_external_tables.py
E11.1-W1d: Refresh Snowflake external table metadata after S3 writes.

External tables with AUTO_REFRESH=FALSE cache their file listing at creation
time.  This script runs ALTER EXTERNAL TABLE ... REFRESH for all 7 mart_pitch_*
external tables so Snowflake sees the files just written by run_w1_lakehouse.py.

Tier: HALT (serving-critical — the daily feature build reads from these tables).
Run: uv run python scripts/refresh_w1_external_tables.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

_SCHEMA = "baseball_data.lakehouse_ext"

# INC-27 (2026-07-04): stg_batter_pitches was DROPPED from Snowflake by W11-E, but ~6 hybrid
# Python consumers (write_serving_store intraday, the team/bullpen posterior writers) still read
# baseball_data.betting.stg_batter_pitches as a RAW SQL STRING on a Snowflake connection. It is
# recreated as lakehouse_ext.stg_batter_pitches (external table over the S3 parquet the daily
# ingest already writes) + a betting.stg_batter_pitches view over it — the same durable pattern as
# every other decommissioned table. REQUIRED/HALT tier: the ext table is refreshed FIRST in the
# daily job (right after ingest_statcast_to_s3 writes the parquet) so the view never serves stale
# box scores / posteriors. Created by scripts/ddl/generate_stg_batter_pitches_external_table.py.
STG_BATTER_PITCHES_TABLE = ["stg_batter_pitches"]

# ⚰️ E11.20 PHASE 1.5 (2026-07-20): RETIRED from the daily refresh — the SF
# lakehouse_ext.mart_pitch_* ext tables + betting.mart_pitch_* views are DROPPED
# (scripts/ddl/drop_w1_mart_pitch_snowflake.py). The list is kept ONLY for the
# rollback path (docs/e11_20_delta_rollout.md §6): recreate via
# scripts/ddl/w1_external_tables.sql, set W1_SF_COMPAT_MIRROR=1, re-add below.
W1_TABLES = [
    "mart_pitch_characteristics",
    "mart_pitch_play_event",
    "mart_pitch_game_context",
    "mart_pitch_fielding",
    "mart_pitch_hitter_profile",
    "mart_pitch_pitcher_profile",
    "mart_pitch_hit_characteristics",
]

# E11.1-W2: the pitch-derived batch marts written by run_w1_lakehouse.py after
# the W1 marts. Refreshed in the same op so the morning feature build sees the
# latest parquet. (Each entry must have an external table created by
# scripts/ddl/generate_w2_external_tables.py before it can be refreshed.)
W2_TABLES = [
    "mart_pitcher_batted_ball_profile",
    "mart_batter_bat_tracking_profile",
    "mart_batter_rolling_stats",
    "mart_pitcher_rolling_stats",
    "mart_starting_pitcher_game_log",
    "mart_pitcher_batter_history",
    "mart_starter_csw_rolling",
    "mart_starter_pitch_mix_rolling",
]

# E11.1-W3: the remaining pitch-derived batch marts written by run_w1_lakehouse.py
# after the W2 marts (created by scripts/ddl/generate_w3_external_tables.py before
# they can be refreshed). REQUIRED/HALT like W2 — these feed feature_pregame_* (the
# morning feature build) and write_serving_store, so a stale read would degrade
# serving. The cutover order (create the external tables BEFORE the PR merges) means
# this refresh code never ships ahead of the tables existing.
W3_TABLES = [
    "mart_pitcher_pitch_archetype",
    "mart_batter_vs_pitch_archetype",
    "mart_batter_vs_handedness_splits",
    "mart_pitcher_vs_handedness_splits",
    "mart_starter_tto_splits",
    "mart_team_base_state_splits",
    "mart_team_vs_pitcher_hand",
    "mart_bullpen_handedness_splits",
    "mart_bullpen_leverage",
    "mart_bullpen_workload",
    "mart_reliever_top3_availability",
]

# E11.1-W3pre: the odds/staging flatten tier (created by
# scripts/ddl/generate_w3pre_external_tables.py before it can be refreshed). Refreshed
# in the same op so the daily build / serving marts see the latest flattened parquet.
W3PRE_TABLES = [
    "stg_oddsapi_odds",
    "stg_oddsapi_events",
    "stg_derivative_odds",
    "stg_statsapi_games",
]

# E11.1-W4: the FanGraphs / posteriors-cluster / raw-savant marts (6) + their FanGraphs
# precursor subtree (4 staging + 2 fct + 1 statsapi staging), created by
# scripts/ddl/generate_w4_external_tables.py. BEST-EFFORT (WARN if missing) during the
# opt-in rollout — like W3pre, these external tables don't exist until the generator is
# run, so a "does not exist" here is an expected skip, NOT a HALT (else this op would fail
# the daily job for the whole pre-cutover window). PROMOTE to `required` once W4 is
# default-on in run_w1_lakehouse (the marts feed the morning feature build at batch time;
# the W4 read-path audit confirmed NONE are read at request time).
W4_TABLES = [
    "stg_fangraphs__stuff_plus",
    "stg_fangraphs__zips_pitching",        # E11.1-W11-FG
    "stg_fangraphs__pitcher_arsenal",
    "stg_fangraphs__zips_hitting",
    "stg_fangraphs__hitting_leaderboard",
    "fct_fangraphs_pitcher_arsenal_wide",
    "fct_fangraphs_hitting_analytics",
    "fct_fangraphs_pitching_analytics",    # E11.1-W11-FG

    "stg_statsapi_player_profiles",
    "mart_pitcher_arsenal_summary",
    "mart_pitcher_profile_summary",
    "mart_batter_profile_summary",
    "mart_park_factors_granular",
    "mart_batter_woba_vs_cluster",
    "mart_catcher_framing",
]

# E11.1-W5: the mart_game_results/mart_game_spine team/game chain (Group A, 10) + the 4
# W4-deferred marts and the stg_batter_sprint_speed precursor (Group B, 5), created by
# scripts/ddl/generate_w5_external_tables.py. BEST-EFFORT (WARN if missing) during the
# opt-in rollout — like W3pre/W4, these external tables don't exist until the generator
# is run, so a "does not exist" here is an expected skip, NOT a HALT (else this op would
# fail the daily job for the whole pre-cutover window). PROMOTE to `required` once W5 is
# default-on in run_w1_lakehouse (the chain feeds the morning feature build at batch time;
# the W4 read-path audit found NO request-time read of any W5 mart — only the game-detail
# Snowflake FALLBACK reads mart_team_pythagorean_rolling, behind the DynamoDB cache).
# NOTE: the seeds (ref_teams/ref_team_aliases) stay dbt seeds — they have no external table.
W5_TABLES = [
    "dim_team_name_lookup",
    "mart_game_results",
    "mart_game_spine",
    "mart_head_to_head_team_history",
    "mart_home_away_splits",
    "mart_park_run_factors",
    "mart_team_pythagorean_rolling",
    "mart_team_rolling_offense",
    "mart_team_rolling_pitching",
    "mart_team_season_record",
    "stg_batter_sprint_speed",
    "mart_eb_park_factors",
    "mart_bullpen_effectiveness",
    "mart_team_fielding_oaa",
    "mart_team_defense_quality_rolling",
]

# E11.1-W5b: the archetype mart (its own tolerance-class mini-wave), created by
# scripts/ddl/generate_w5b_external_tables.py. BEST-EFFORT (WARN if missing) like W3pre/W4/W5
# during the opt-in rollout. The mart reads the mart_player_archetype_posteriors parquet
# (builder output, no external table) — only the mart itself becomes a lakehouse_ext view.
ARCHETYPE_TABLES = ["mart_batter_archetype_vs_pitcher_cluster"]

# E11.1-W6: the 2 Group-C staging flattens + 13 odds/CLV + odds-serving marts, created by
# scripts/ddl/generate_w6_external_tables.py. BEST-EFFORT (WARN if missing) during the opt-in
# rollout, like W3pre/W4/W5. Refreshed in full by the DAILY op (the _history bucket of
# mart_odds_outcomes is rewritten daily). NOTE: mart_odds_outcomes is date-bucketed
# (_history/_current) — one REFRESH re-lists both buckets.
W6_TABLES = [
    "stg_statsapi_venues",
    "stg_statsapi_lineups",
    "mart_odds_outcomes",
    "mart_odds_events",
    "mart_game_odds_bridge",
    "mart_odds_consensus",
    "mart_odds_line_movement",
    "mart_closing_line_value",
    "mart_clv_labeled_games",
    "mart_clv_label_count",
    "mart_prediction_clv",
    "mart_derivative_closes",
    "mart_bookmaker_disagreement",
    "mart_team_schedule_context",
    "mart_player_game_starts",
]

# E11.1-W6 INTRADAY: the odds-serving hot set refreshed on the odds_current_rebuild cadence
# (--w6-odds), AFTER run_w1_lakehouse.py --w6-odds-current rewrites mart_odds_outcomes'
# _current bucket. SERVING-CRITICAL: stale here = stale served prices (INC-16). Only these
# two — the CLV/line-movement marts are post-hoc (once/day, --w6-clv).
W6_ODDS_INTRADAY_TABLES = ["mart_odds_outcomes", "mart_game_odds_bridge"]
# Refreshed once/day after odds_clv_dbt_rebuild (closing line locks at first pitch).

# E11.1-W7a: the builder-output cluster external tables, created by
# scripts/ddl/generate_w7_external_tables.py over the cluster_batters/cluster_pitchers --s3
# parquet. The feature layer now reads clusters from here (source 'lakehouse_clusters')
# instead of native statsapi.{batter,pitcher}_clusters. BEST-EFFORT (WARN if missing) like
# W4/W5/W5b/W6 during the opt-in rollout. Clusters are rebuilt SEASONALLY (pre-season +
# optional mid-season), so this REFRESH is a cheap no-op on most days, but it's included in
# the daily refresh so a same-day cluster_*.py --s3 run is picked up without a manual step.
W7_TABLES = ["batter_clusters", "pitcher_clusters"]
W6_CLV_TABLES = ["mart_closing_line_value", "mart_prediction_clv", "mart_odds_line_movement"]

# E11.1-W7b: the prediction/serving mini-wave external tables (created by
# scripts/ddl/generate_w7b_external_tables.py over the run_w1_lakehouse.py --w7b parquet): the
# mart_player_profile_identity injury chain + the serving-mart backlog. BEST-EFFORT (WARN if
# missing) like W4/W5/W5b/W6/W7 during the opt-in rollout — these don't exist until the generator
# runs, so a "does not exist" is an expected skip, NOT a HALT. PROMOTE to required once W7b is
# default-on. (player_transactions is read via read_parquet, not a Snowflake source → no external table.)
W7B_TABLES = [
    "stg_statsapi_transactions",
    "stg_statsapi_player_injury_status",
    "feature_pregame_injury_status",
    "mart_player_profile_identity",
    "stg_statsapi_probable_pitchers",
    "stg_statsapi_lineups_wide",
]

# INC-31 (2026-07-10): the two W7b SERVING marts whose S3 parquet is now rebuilt on the INTRADAY
# cadence (run_w1_lakehouse.py --w7b-only inside _schedule_lakehouse_intraday) so a slate's lineups
# are seen the SAME DAY they post — not only at the next morning build. Their lakehouse_ext tables
# must be REFRESHed on that same cadence, or the SF view lineup_monitor.py reads (betting.
# stg_statsapi_lineups_wide → lakehouse_ext → this parquet) stays stale and the lineup monitor is
# blind to today's confirmed lineups (post_lineup predict never fires) + the pick-detail lineup card
# is empty for the live slate. Added to the DEFAULT refresh (best-effort — WARN if the ext table
# does not exist yet). Kept as a distinct constant (not the whole W7B_TABLES) to avoid re-refreshing
# stg_statsapi_transactions, which is already in the W11TX required set.
W7B_SERVING_TABLES = ["stg_statsapi_lineups_wide", "stg_statsapi_probable_pitchers"]

# E11.1-W9: the 5 sub-model SIGNAL STORES mirrored to S3 by scripts/export_w9_signals_to_s3.py
# (external tables created by scripts/ddl/generate_w9_external_tables.py). BEST-EFFORT (WARN if
# missing) like W4/W5/W6/W7/W7b during the opt-in rollout — they don't exist until the export
# mirror runs (W9_LAKEHOUSE_S3=1), so a "does not exist" is an expected skip, NOT a HALT.
# Refreshed via the dedicated --w9 path (the W9 mirror op calls it right after the export), so
# they stay OUT of the default daily refresh list until W9 cutover (no native reader yet).
W9_TABLES = [
    "mart_sub_model_signals",
    "offense_v1_signals",
    "offense_v2_signals",
    "starter_suppression_signals",
    "starter_ip_signals",
]

# E11.1-W8a: the upstream feature layer + EB posteriors external tables (created by
# scripts/ddl/generate_w8a_external_tables.py over the run_w1_lakehouse.py --w8a parquet).
# BEST-EFFORT (WARN if missing) like W4/W5/W6/W7/W7b/W9 during the opt-in rollout. Refreshed via
# the dedicated --w8a path (the W8a mirror op calls it right after the build). The 5 EB models'
# Snowflake side is INCREMENTAL — a stale external-table refresh just delays the MERGE pickup.
W8A_TABLES = [
    "stg_statsapi_starter_snapshots",
    "feature_pregame_starter_status",
    "feature_pregame_park_status",
    "feature_pregame_park_features",
    "feature_pregame_team_features",
    "feature_pregame_expected_lineup",
    "feature_pregame_odds_features",
    "feature_pregame_sub_model_signals",
    "int_bullpen_ali_by_season",
    "eb_bullpen_posteriors",
    "eb_bullpen_team_posteriors",
    "eb_starter_posteriors",
    "eb_batter_posteriors_raw",
]

# E11.1-W8b: the serving aggregator + complex upstream + matchup external tables (created by
# scripts/ddl/generate_w8b_external_tables.py over the run_w1_lakehouse.py --w8b parquet). BEST-EFFORT
# (WARN if missing) like W4-W9 during the opt-in rollout. Refreshed via the dedicated --w8b path (the
# W8b build op calls it right after the build). feature_pregame_game_features_raw + _game_features are
# INCREMENTAL on Snowflake — a stale external-table refresh just delays the MERGE pickup.
# NOTE: feature_pregame_injury_status is NOT here — it reuses its W7b external table (W7B_TABLES).
W8B_TABLES = [
    "feature_pregame_starter_features",
    "feature_pregame_lineup_features",
    "feature_pregame_bullpen_state_features",
    "feature_batter_archetype_matchups",
    "feature_pitcher_batter_h2h_matchups",
    "feature_pitcher_cluster_matchups",
    "feature_pregame_game_features_raw",
    "feature_league_contact_baseline",
    "feature_pregame_game_features",
]

# E11.1-W11 Tier-B: the umpire stg + feature external tables (created by
# scripts/ddl/generate_w11b_external_tables.py over the run_w1_lakehouse.py --w11b parquet).
# BEST-EFFORT (WARN if missing) like W4-W9 during the opt-in rollout. Refreshed via the dedicated
# --w11b path (the W11b mirror op calls it right after the build). All 4 are TABLE on the Snowflake
# side (no incrementals) → no DROP+rebuild at cutover.
W11B_TABLES = [
    "stg_statsapi_umpire_game_log",
    "stg_statsapi_umpire_snapshots",
    "feature_pregame_umpire_features",
    "feature_pregame_umpire_status",
]

# E11.1-W11 Tier-C: the weather stg + feature external tables (created by
# scripts/ddl/generate_w11c_external_tables.py over the run_w1_lakehouse.py --w11c parquet).
# BEST-EFFORT (WARN if missing) like W4-W9 during the opt-in rollout. Refreshed via the dedicated
# --w11c path (the W11c mirror op calls it right after the build). All 4 are TABLE/VIEW on the
# Snowflake side (no incrementals) → no DROP+rebuild at cutover.
W11C_TABLES = [
    "stg_weather_raw",
    "stg_weather_raw_snapshots",
    "feature_pregame_weather_status",
    "feature_pregame_weather_features",
]

# E11.1-W11 Tier-D: the public-betting stg + feature external tables (created by
# scripts/ddl/generate_w11d_external_tables.py over the run_w1_lakehouse.py --w11d parquet).
# BEST-EFFORT (WARN if missing) like W4-W9/W11b-c during the opt-in rollout. Refreshed via the
# dedicated --w11d path (the W11d mirror op calls it right after the build). All 4 are TABLE/VIEW on
# the Snowflake side (no incrementals) → no DROP+rebuild at cutover.
W11D_TABLES = [
    "stg_actionnetwork_public_betting",
    "stg_actionnetwork_public_betting_snapshots",
    "feature_pregame_public_betting_status",
    "feature_pregame_public_betting_features",
]

# E11.22: player_transactions read-cutover — the external table over the run_w1_lakehouse.py --w11tx
# parquet (generate_w11tx_external_table.py). TABLE on the Snowflake side (no incremental). Refreshed
# via --w11tx AND (since the SF raw was DROPPED 2026-07-09) in the DAILY REQUIRED set below — the
# model's serving read now depends on it, so a missing refresh is HALT, not best-effort.
W11TX_TABLES = ["stg_statsapi_transactions"]


def get_snowflake_conn():
    # INC-22: on the EC2 box Snowflake auth is the INLINE key (SNOWFLAKE_PRIVATE_KEY,
    # raw/base64), NOT a key FILE — and there is NO SNOWFLAKE_PASSWORD. This script's
    # own file-only resolver therefore KeyError'd on the box (SNOWFLAKE_PRIVATE_KEY_PATH
    # unset → fell through to os.environ["SNOWFLAKE_PASSWORD"]). Delegate to the shared
    # PATH-if-exists→inline→password resolver in data_loader (the same one the coverage
    # guard + serving writers use). ALTER EXTERNAL TABLE statements are fully-qualified,
    # so the connection's default schema is immaterial.
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema="lakehouse_ext")


def _refresh(tables, required: set) -> None:
    conn = get_snowflake_conn()
    cur = conn.cursor()
    failed = []
    for table in tables:
        fqn = f"{_SCHEMA}.{table}"
        try:
            cur.execute(f"ALTER EXTERNAL TABLE {fqn} REFRESH")
            print(f"  refreshed {fqn}")
        except Exception as e:
            if table in required:
                print(f"  FAILED {fqn}: {e}", file=sys.stderr)
                failed.append(table)
            else:
                print(f"  WARNING skip {fqn} (not yet created / best-effort): {e}", file=sys.stderr)
    cur.close()
    conn.close()
    if failed:
        raise RuntimeError(
            f"External table refresh FAILED for: {failed}  "
            "Downstream feature build / served prices will see stale S3 data."
        )


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Refresh lakehouse_ext external tables after S3 writes")
    ap.add_argument("--w6-odds", action="store_true",
                    help="INTRADAY: refresh only mart_odds_outcomes + mart_game_odds_bridge "
                         "(serving-critical — after run_w1_lakehouse.py --w6-odds-current).")
    ap.add_argument("--w6-clv", action="store_true",
                    help="Once/day: refresh the CLV/line-movement marts (after odds_clv rebuild).")
    ap.add_argument("--w9", action="store_true",
                    help="E11.1-W9: refresh only the 5 sub-model signal-store external tables "
                         "(after export_w9_signals_to_s3.py). Best-effort — these don't exist "
                         "until the W9 mirror is enabled, so a missing table is an expected skip.")
    ap.add_argument("--w8a", action="store_true",
                    help="E11.1-W8a: refresh only the 13 upstream feature-layer + EB-posterior "
                         "external tables (after run_w1_lakehouse.py --w8a). Best-effort — these "
                         "don't exist until the W8a build is enabled, so a missing table is an "
                         "expected skip.")
    ap.add_argument("--sub-model-signals", action="store_true",
                    help="INC-25: refresh ONLY the feature_pregame_sub_model_signals external table "
                         "(after run_w1_lakehouse.py --sub-model-signals-only re-writes its parquet "
                         "from the fresh W9 stores). Best-effort — missing table is an expected skip.")
    ap.add_argument("--w8b", action="store_true",
                    help="E11.1-W8b: refresh only the 9 serving-aggregator + complex-upstream "
                         "external tables (after run_w1_lakehouse.py --w8b). Best-effort — these "
                         "don't exist until the W8b build is enabled, so a missing table is an "
                         "expected skip.")
    ap.add_argument("--w11b", action="store_true",
                    help="E11.1-W11 Tier-B: refresh only the 4 umpire stg + feature external "
                         "tables (after run_w1_lakehouse.py --w11b). Best-effort — these don't "
                         "exist until the W11b build is enabled, so a missing table is an "
                         "expected skip.")
    ap.add_argument("--w11c", action="store_true",
                    help="E11.1-W11 Tier-C: refresh only the 4 weather stg + feature external "
                         "tables (after run_w1_lakehouse.py --w11c). Best-effort — these don't "
                         "exist until the W11c build is enabled, so a missing table is an "
                         "expected skip.")
    ap.add_argument("--w11d", action="store_true",
                    help="E11.1-W11 Tier-D: refresh only the 4 public-betting stg + feature external "
                         "tables (after run_w1_lakehouse.py --w11d). Best-effort — these don't "
                         "exist until the W11d build is enabled, so a missing table is an "
                         "expected skip.")
    ap.add_argument("--w11tx", action="store_true",
                    help="E11.22: refresh only the stg_statsapi_transactions external table (after "
                         "run_w1_lakehouse.py --w11tx). Best-effort until the SF raw is dropped.")
    args = ap.parse_args()

    # E11.1-W8a: the W8a build op refreshes its own external tables right after the build
    # (mirror-tier — best-effort, never required). Kept off the default daily refresh list until
    # the W8a cutover (the dbt else branches that read them aren't merged until then).
    if args.w8a:
        print("Refreshing W8a upstream feature-layer + EB-posterior external tables (--w8a):")
        _refresh(W8A_TABLES, required=set())
        print("W8a external-table refresh complete (best-effort).")
        return

    # INC-25: the narrow post-generator consumer refresh (after --sub-model-signals-only re-writes
    # the parquet). Refreshes only feature_pregame_sub_model_signals so the serving read reflects
    # the current slate before signal_freshness_check + the SF materialize.
    if args.sub_model_signals:
        print("Refreshing feature_pregame_sub_model_signals external table (--sub-model-signals):")
        _refresh(["feature_pregame_sub_model_signals"], required=set())
        print("feature_pregame_sub_model_signals external-table refresh complete (best-effort).")
        return

    # E11.1-W8b: the serving-aggregator build op refreshes its own external tables right after the
    # build (mirror-tier — best-effort, never required). Kept off the default daily refresh list until
    # the W8b cutover (the dbt else branches that read them aren't merged until then).
    if args.w8b:
        print("Refreshing W8b serving-aggregator + complex-upstream external tables (--w8b):")
        _refresh(W8B_TABLES, required=set())
        print("W8b external-table refresh complete (best-effort).")
        return

    # E11.1-W11 Tier-B: the umpire mirror op refreshes its own external tables right after the
    # build (mirror-tier — best-effort, never required). Kept off the default daily refresh list
    # until cutover (the dbt else branches that read them aren't merged/flipped until then).
    if args.w11b:
        print("Refreshing W11b umpire stg + feature external tables (--w11b):")
        _refresh(W11B_TABLES, required=set())
        print("W11b umpire external-table refresh complete (best-effort).")
        return

    # E11.1-W11 Tier-C: the weather mirror op refreshes its own external tables right after the
    # build (mirror-tier — best-effort, never required). Kept off the default daily refresh list
    # until cutover (the dbt else branches that read them aren't merged/flipped until then).
    if args.w11c:
        print("Refreshing W11c weather stg + feature external tables (--w11c):")
        _refresh(W11C_TABLES, required=set())
        print("W11c weather external-table refresh complete (best-effort).")
        return

    # E11.1-W11 Tier-D: the public-betting mirror op refreshes its own external tables right after the
    # build (mirror-tier — best-effort, never required). Kept off the default daily refresh list
    # until cutover (the dbt else branches that read them aren't merged/flipped until then).
    if args.w11d:
        print("Refreshing W11d public-betting stg + feature external tables (--w11d):")
        _refresh(W11D_TABLES, required=set())
        print("W11d public-betting external-table refresh complete (best-effort).")
        return

    # E11.22: refresh only the player_transactions stg external table (after run_w1_lakehouse.py
    # --w11tx). Best-effort until the SF raw is dropped, at which point the serving read depends on
    # it → move W11TX_TABLES into the DAILY REQUIRED set below.
    if args.w11tx:
        print("Refreshing W11tx transactions stg external table (--w11tx):")
        _refresh(W11TX_TABLES, required=set())
        print("W11tx transactions external-table refresh complete (best-effort).")
        return

    # E11.1-W9: the signal-store mirror op refreshes its own external tables right after writing
    # the parquet (mirror-tier — best-effort, never required). Kept off the default daily refresh
    # list because no native reader depends on them until W8/W9 cutover.
    if args.w9:
        print("Refreshing W9 sub-model signal-store external tables (--w9):")
        _refresh(W9_TABLES, required=set())
        print("W9 signal-store external-table refresh complete (best-effort).")
        return

    # E11.1-W6 INTRADAY: the odds hot set is SERVING-CRITICAL (HALT) — a missing/failed REFRESH
    # here means served prices go stale (INC-16). By the time this op fires, cutover has happened
    # (the intraday wiring only runs post-cutover), so these tables MUST exist → required.
    if args.w6_odds:
        print("Refreshing W6 INTRADAY odds-serving external tables (--w6-odds):")
        _refresh(W6_ODDS_INTRADAY_TABLES, required=set(W6_ODDS_INTRADAY_TABLES))
        print("W6 intraday odds external-table refresh complete.")
        return

    if args.w6_clv:
        print("Refreshing W6 CLV/line-movement external tables (--w6-clv):")
        _refresh(W6_CLV_TABLES, required=set(W6_CLV_TABLES))
        print("W6 CLV external-table refresh complete.")
        return

    # DAILY full refresh. W1+W2+W3 are REQUIRED (HALT) — they feed the morning build. W3pre/W4/
    # W5/W5b/W6 are BEST-EFFORT until their cutover (they don't exist until the generator runs,
    # so a "does not exist" is an expected skip, NOT a HALT that would fail the whole daily job).
    # INC-27: stg_batter_pitches is REQUIRED (serving-critical — its betting.* view backs the
    # intraday box score + the posterior writers). Refreshed FIRST so the view is fresh before
    # any downstream read. Grouped with W1 (the pitch substrate) since it shares its cadence.
    # E11.22: player_transactions SF raw DROPPED 2026-07-09 → stg_statsapi_transactions serving read
    # now depends on the S3 ext table, so W11TX_TABLES is REQUIRED (HALT) in the daily refresh (per the
    # comment at W11TX_TABLES). The --w11tx nightly path still runs the BUILD (dedup parquet) + a
    # best-effort refresh; this REQUIRED refresh is the durable freshness guarantee decoupled from the flag.
    # E11.20 PHASE 1.5 (2026-07-20): the W1 pitch marts are OUT of the daily refresh
    # entirely — the lakehouse_ext.mart_pitch_* external tables + betting.mart_pitch_*
    # views are DROPPED (zero readers; stragglers repointed in §6 a0; the SF-compat
    # season mirror write is retired behind W1_SF_COMPAT_MIRROR in run_w1_lakehouse).
    # Refreshing a dropped ext table would HALT the daily. Rollback: re-run the DDL in
    # scripts/ddl/w1_external_tables.sql, set W1_SF_COMPAT_MIRROR=1, re-add W1_TABLES
    # here (docs/e11_20_delta_rollout.md §6).
    required = (set(STG_BATTER_PITCHES_TABLE) | set(W2_TABLES)
                | set(W3_TABLES) | set(W11TX_TABLES))
    _refresh(
        STG_BATTER_PITCHES_TABLE + W2_TABLES + W3_TABLES + W3PRE_TABLES
        + W4_TABLES + W5_TABLES + ARCHETYPE_TABLES + W6_TABLES + W7_TABLES + W7B_SERVING_TABLES
        + W11TX_TABLES,
        required=required,
    )
    print("stg_batter_pitches + W2+W3 + W11tx external table refresh complete "
          "(W3pre + W4 + W5 + W5b + W6 + W7 + W7b-serving best-effort; "
          "W1 mart_pitch_* RETIRED — phase 1.5).")


if __name__ == "__main__":
    main()
