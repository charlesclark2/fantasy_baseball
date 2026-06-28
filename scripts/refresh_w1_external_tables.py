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


def main():
    conn = get_snowflake_conn()
    cur = conn.cursor()
    failed = []
    # W1+W2 are REQUIRED (HALT) — they exist and feed the morning build. W3pre tables are
    # BEST-EFFORT until cutover: they don't exist until generate_w3pre_external_tables.py
    # is run, so a "does not exist" here is an expected skip (WARN-tier), NOT a HALT — else
    # this op would fail the daily job for the entire pre-cutover rollout window. (E11.1-W3pre)
    required = set(W1_TABLES) | set(W2_TABLES) | set(W3_TABLES)
    for table in W1_TABLES + W2_TABLES + W3_TABLES + W3PRE_TABLES + W4_TABLES:
        fqn = f"{_SCHEMA}.{table}"
        try:
            cur.execute(f"ALTER EXTERNAL TABLE {fqn} REFRESH")
            print(f"  refreshed {fqn}")
        except Exception as e:
            if table in required:
                print(f"  FAILED {fqn}: {e}", file=sys.stderr)
                failed.append(table)
            else:
                print(f"  WARNING skip {fqn} (W3pre/W4, not yet created): {e}", file=sys.stderr)
    cur.close()
    conn.close()
    if failed:
        raise RuntimeError(
            f"External table refresh FAILED for: {failed}  "
            "Downstream feature build will see stale S3 data."
        )
    print("W1+W2+W3 external table refresh complete (W3pre + W4 best-effort).")


if __name__ == "__main__":
    main()
