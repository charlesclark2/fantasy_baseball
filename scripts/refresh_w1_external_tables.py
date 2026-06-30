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

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)
from dotenv import load_dotenv

load_dotenv()

_SCHEMA = "baseball_data.lakehouse_ext"

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
    "stg_fangraphs__pitcher_arsenal",
    "stg_fangraphs__zips_hitting",
    "stg_fangraphs__hitting_leaderboard",
    "fct_fangraphs_pitcher_arsenal_wide",
    "fct_fangraphs_hitting_analytics",
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


def _load_private_key():
    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    if not key_path:
        return None
    with open(key_path, "rb") as fh:
        raw = fh.read()
    passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    key = load_pem_private_key(
        raw, password=passphrase.encode() if passphrase else None, backend=default_backend()
    )
    return key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())


def get_snowflake_conn():
    import snowflake.connector
    kwargs = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        role=os.environ.get("SNOWFLAKE_ROLE"),
        database="baseball_data",
        schema="lakehouse_ext",
    )
    pk = _load_private_key()
    if pk:
        kwargs["private_key"] = pk
    else:
        kwargs["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    return snowflake.connector.connect(**kwargs)


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
    ap.add_argument("--w8b", action="store_true",
                    help="E11.1-W8b: refresh only the 9 serving-aggregator + complex-upstream "
                         "external tables (after run_w1_lakehouse.py --w8b). Best-effort — these "
                         "don't exist until the W8b build is enabled, so a missing table is an "
                         "expected skip.")
    args = ap.parse_args()

    # E11.1-W8a: the W8a build op refreshes its own external tables right after the build
    # (mirror-tier — best-effort, never required). Kept off the default daily refresh list until
    # the W8a cutover (the dbt else branches that read them aren't merged until then).
    if args.w8a:
        print("Refreshing W8a upstream feature-layer + EB-posterior external tables (--w8a):")
        _refresh(W8A_TABLES, required=set())
        print("W8a external-table refresh complete (best-effort).")
        return

    # E11.1-W8b: the serving-aggregator build op refreshes its own external tables right after the
    # build (mirror-tier — best-effort, never required). Kept off the default daily refresh list until
    # the W8b cutover (the dbt else branches that read them aren't merged until then).
    if args.w8b:
        print("Refreshing W8b serving-aggregator + complex-upstream external tables (--w8b):")
        _refresh(W8B_TABLES, required=set())
        print("W8b external-table refresh complete (best-effort).")
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
    required = set(W1_TABLES) | set(W2_TABLES) | set(W3_TABLES)
    _refresh(
        W1_TABLES + W2_TABLES + W3_TABLES + W3PRE_TABLES
        + W4_TABLES + W5_TABLES + ARCHETYPE_TABLES + W6_TABLES + W7_TABLES,
        required=required,
    )
    print("W1+W2+W3 external table refresh complete (W3pre + W4 + W5 + W5b + W6 + W7 best-effort).")


if __name__ == "__main__":
    main()
