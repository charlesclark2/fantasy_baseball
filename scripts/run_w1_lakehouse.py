#!/usr/bin/env python3
"""
scripts/run_w1_lakehouse.py

Execute the E11.1-W1 lakehouse mart models via Python DuckDB.

dbt-fusion 2.0.0-preview.190 cannot forward S3 credentials to its bundled DuckDB
through any supported channel (env vars, profiles.yml settings, persistent secrets,
~/.duckdb/stored_secrets/).  This script bypasses dbt-fusion for the DuckDB target
by parsing the relevant Jinja branches from each model file directly, then running
the rendered SQL via Python DuckDB which has working credential-chain S3 auth.

No dbt compile step is needed — the parser handles the exact Jinja patterns used in
the W1 mart models (target.name conditional, config(), ref(), is_incremental()).

Prerequisites:
  - stg_batter_pitches exported to S3 first:
      python3 scripts/export_statcast_to_s3.py
  - AWS credentials accessible via credential chain (aws configure or env vars)

Usage (run from anywhere in the repo):
  python3 scripts/run_w1_lakehouse.py             # default: W1 + W2 + W3  (writes to S3)
  python3 scripts/run_w1_lakehouse.py --dry-run   # row-count only, no S3 writes
  python3 scripts/run_w1_lakehouse.py --w1-only   # only the W1 pitch marts (skip W2 + W3)
  python3 scripts/run_w1_lakehouse.py --skip-w1   # only W2 + W3 (reuse existing W1 parquet)
  python3 scripts/run_w1_lakehouse.py --w3-only   # only the W3 marts (reuse existing W1+W2 parquet)
  python3 scripts/run_w1_lakehouse.py --w3pre     # W1 + W2 + W3 + the W3pre odds/staging tier (opt-in)
  python3 scripts/run_w1_lakehouse.py --w3pre-only # only the W3pre odds/staging flatten tier
  python3 scripts/run_w1_lakehouse.py --w4         # W1 + W2 + W3 + the W4 FanGraphs/posteriors/savant marts (opt-in)
  python3 scripts/run_w1_lakehouse.py --w4-only    # only the W4 marts + FanGraphs precursors (reuse W1 parquet)

E11.1-W2 (2026-06-26): this script now also builds the W2 pitch-derived batch
marts (W2_MART_MODELS) after the W1 pitch marts, registering the W1 marts as
DuckDB views first so the W2 models' `from mart_pitch_*` resolves. The build
stays in this single op (run_w1_lakehouse_op) — sequenced before dbt_daily_build
so the external tables are fresh for the morning feature build. (The original
"use a Railway cron, not a Dagster op" guidance was to avoid Dagster+ serverless
run-minute billing, which E11.15 eliminated by self-hosting Dagster on Railway —
self-host cost is held RAM, not run-minutes — so extending this op is now both
free and the safest ordering.)
"""

import os
import re
import sys
import tempfile
import time
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "dbt" / "models"

# ── S3 locations (mirrors lakehouse_loc() macro in dbt/macros/lakehouse.sql) ──
BUCKET = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
# E11.1-W3pre: RAW tier (un-flattened source JSON parquet) read by the W3pre staging
# models' duckdb branch. Mirrors lakehouse_raw_loc() / lakehouse_raw_writer.RAW_PREFIX.
LAKEHOUSE_RAW = f"{BUCKET}/baseball/lakehouse_raw"

MART_MODELS = [
    "mart_pitch_characteristics",
    "mart_pitch_play_event",
    "mart_pitch_game_context",
    "mart_pitch_fielding",
    "mart_pitch_hitter_profile",
    "mart_pitch_pitcher_profile",
    "mart_pitch_hit_characteristics",
]

# E11.1-W2: the next batch tier — pitch-derived marts whose ENTIRE upstream
# closure is already in S3 (stg_batter_pitches + the W1 mart_pitch_* above +
# stg_ref_players). Built AFTER the W1 marts each run; the W1 marts are
# registered as DuckDB views (over their freshly-written parquet) first so the
# plain table names in these models' duckdb branches resolve. Ordering within
# the list respects intra-W2 deps (none today — each reads only stg_* or W1).
W2_MART_MODELS = [
    "mart_pitcher_batted_ball_profile",   # ← stg_batter_pitches
    "mart_batter_bat_tracking_profile",   # ← stg_batter_pitches
    "mart_batter_rolling_stats",          # ← stg_batter_pitches
    "mart_pitcher_rolling_stats",         # ← stg_batter_pitches
    "mart_starting_pitcher_game_log",     # ← stg_batter_pitches + mart_pitch_game_context
    "mart_pitcher_batter_history",        # ← mart_pitch_play_event
    "mart_starter_csw_rolling",           # ← mart_pitch_play_event
    "mart_starter_pitch_mix_rolling",     # ← mart_pitch_characteristics
]

# E11.1-W3: the remaining pitch-derived batch marts whose ENTIRE upstream closure is
# already in S3 (stg_batter_pitches + the W1 mart_pitch_* + the W2 mart_starting_pitcher_game_log).
# Built AFTER W2 each run; the W2 marts are registered as DuckDB views first so the
# bullpen marts' `from mart_starting_pitcher_game_log` resolves. ORDER MATTERS:
# mart_pitcher_pitch_archetype must be built + registered as a view BEFORE
# mart_batter_vs_pitch_archetype (which reads it) — each W3 model is registered as a
# view immediately after it is built (see run()), so the intra-W3 dep resolves.
W3_MART_MODELS = [
    "mart_pitcher_pitch_archetype",       # ← stg_batter_pitches   (must precede batter_vs_pitch_archetype)
    "mart_batter_vs_pitch_archetype",     # ← stg_batter_pitches + mart_pitcher_pitch_archetype
    "mart_batter_vs_handedness_splits",   # ← stg_batter_pitches
    "mart_pitcher_vs_handedness_splits",  # ← stg_batter_pitches
    "mart_starter_tto_splits",            # ← stg_batter_pitches
    "mart_team_base_state_splits",        # ← stg_batter_pitches
    "mart_team_vs_pitcher_hand",          # ← stg_batter_pitches
    "mart_bullpen_handedness_splits",     # ← stg_batter_pitches + mart_starting_pitcher_game_log
    "mart_bullpen_leverage",              # ← stg_batter_pitches + mart_pitch_play_event + mart_starting_pitcher_game_log
    "mart_bullpen_workload",              # ← stg_batter_pitches + mart_starting_pitcher_game_log
    "mart_reliever_top3_availability",    # ← stg_batter_pitches + mart_pitch_play_event + mart_starting_pitcher_game_log
]

# E11.1-W4: the FanGraphs + posteriors/cluster + raw-savant non-serving marts (6),
# plus the FanGraphs precursor subtree they read. Unlike W1-W3 these do NOT descend
# from stg_batter_pitches alone — they read RAW precursor parquet (exported by
# scripts/export_w4_raw_to_s3.py) and builder-output parquet (the migrated DuckDB
# builds of fit_granular_park_priors.py + cluster_pitchers.py). OPT-IN (--w4) until
# cutover, like W3pre: the precursor parquet must exist first, so the default daily
# (HALT) op stays W1+W2+W3 until the operator validates W4 and flips it default-on.
#
# Built in DEPENDENCY ORDER; each is registered as a DuckDB view immediately after
# build so the next model's plain-name reads resolve:
#   FanGraphs staging (flatten raw_json parquet) → FanGraphs fct → statsapi staging →
#   the 6 marts (mart_pitcher_arsenal_summary precedes mart_pitcher_profile_summary).
# Raw/builder-output parquet is read DIRECTLY via read_parquet(lakehouse_loc("X")) in
# each duckdb branch (no view registration needed):
#   catcher_framing_raw, fg_stuff_plus_raw, fg_zips_pitching_raw, fg_zips_hitting_raw,
#   fg_hitting_leaderboard_raw, player_profiles_raw, eb_park_factors_granular_raw,
#   pitcher_clusters.
W4_PRECURSOR_MODELS = [
    "stg_fangraphs__stuff_plus",          # ← fg_stuff_plus_raw (parquet)
    "stg_fangraphs__zips_pitching",       # ← fg_zips_pitching_raw (parquet); E11.1-W11-FG
    "stg_fangraphs__pitcher_arsenal",     # ← fg_stuff_plus_raw (parquet)
    "stg_fangraphs__zips_hitting",        # ← fg_zips_hitting_raw (parquet)
    "stg_fangraphs__hitting_leaderboard", # ← fg_hitting_leaderboard_raw (parquet)
    "fct_fangraphs_pitcher_arsenal_wide", # ← stg_fangraphs__pitcher_arsenal + __stuff_plus
    "fct_fangraphs_hitting_analytics",    # ← stg_fangraphs__zips_hitting + __hitting_leaderboard
    "fct_fangraphs_pitching_analytics",   # ← stg_fangraphs__stuff_plus + __zips_pitching; E11.1-W11-FG
    "stg_statsapi_player_profiles",       # ← player_profiles_raw (parquet)
]

W4_MART_MODELS = [
    "mart_pitcher_arsenal_summary",       # ← fct_fangraphs_pitcher_arsenal_wide + mart_pitch_characteristics(W1)
    "mart_pitcher_profile_summary",       # ← mart_pitcher_arsenal_summary(W4) + stg_batter_pitches + stg_statsapi_player_profiles(W4)
    "mart_batter_profile_summary",        # ← fct_fangraphs_hitting_analytics + mart_pitch_play_event(W1) + stg_batter_pitches
    "mart_park_factors_granular",         # ← eb_park_factors_granular_raw (builder-output parquet)
    "mart_batter_woba_vs_cluster",        # ← mart_pitch_play_event(W1) + pitcher_clusters (builder-output parquet)
    "mart_catcher_framing",               # ← catcher_framing_raw (parquet)
]

# Ordered build list for _build_w4 (precursors first, then marts; mart_pitcher_arsenal_summary
# before mart_pitcher_profile_summary, already true in W4_MART_MODELS order).
W4_BUILD_MODELS = W4_PRECURSOR_MODELS + W4_MART_MODELS

# E11.1-W3pre: the staging tier that feeds the odds/CLV BATCH subtree. Each model's
# duckdb branch flattens the RAW JSON parquet under lakehouse_raw/<source>/ (written by
# the migrated writers + scripts/export_odds_raw_to_s3.py) — no W1/W2 dependency, so
# they build independently. Built to lakehouse/<model>/data.parquet like the marts; the
# Snowflake side is a view over the lakehouse_ext external table. (stg_oddsapi_events is
# included though its live feed stalled 2026-06-04 — historical rows still flatten.)
W3PRE_STG_MODELS = [
    "stg_oddsapi_odds",      # ← lakehouse_raw/mlb_odds_raw      (⚠ feeds serving mart_odds_outcomes)
    "stg_oddsapi_events",    # ← lakehouse_raw/mlb_events_raw
    "stg_derivative_odds",   # ← lakehouse_raw/derivative_odds_raw (eval/CLV only)
    "stg_statsapi_games",    # ← lakehouse_raw/monthly_schedule   (⚠ double-duty + serving)
]

# E11.1-W5: the seeds + the mart_game_results / mart_game_spine team/game chain (10
# marts) + the 4 W4-deferred marts. OPT-IN (--w5) until cutover, like W3pre/W4: the
# precursor exports (scripts/export_w5_raw_to_s3.py) + the W3pre stg_statsapi_games
# parquet must exist first, so the default daily (HALT) op stays W1+W2+W3 until the
# operator validates W5 and flips it default-on.
#
# Precursor VIEWS registered (read directly from S3 parquet, NOT built here):
#   • seeds (part-0.parquet): ref_teams, ref_team_aliases
#   • W3pre flatten (data.parquet): stg_statsapi_games   ← mart_game_results/spine read it
#   • W2 mart (data.parquet): mart_starting_pitcher_game_log  ← Group B bullpen mart
# stg_batter_pitches + the W1 mart_pitch_* are already registered by run() before this.
W5_SEED_VIEWS = ["ref_teams", "ref_team_aliases"]
W5_PRECURSOR_VIEWS = ["stg_statsapi_games"]

# Group A — built in DEPENDENCY ORDER (each registered as a DuckDB view immediately
# after build so the next model's plain-name reads resolve). dim_team_name_lookup +
# mart_game_results precede mart_game_spine; the spine precedes the Group B marts that
# read it (team_fielding_oaa, team_defense_quality_rolling).
W5_MART_MODELS = [
    "dim_team_name_lookup",          # ← ref_teams + ref_team_aliases seeds
    "mart_game_results",             # ← stg_batter_pitches + ref_teams + stg_statsapi_games
    "mart_game_spine",               # ← mart_game_results + stg_statsapi_games + dim_team_name_lookup
    "mart_head_to_head_team_history",# ← mart_game_results + ref_teams
    "mart_home_away_splits",         # ← stg_batter_pitches + mart_game_results
    "mart_park_run_factors",         # ← mart_game_results
    "mart_team_pythagorean_rolling", # ← mart_game_results + ref_teams
    "mart_team_rolling_offense",     # ← stg_batter_pitches + mart_game_results
    "mart_team_rolling_pitching",    # ← stg_batter_pitches + mart_game_results
    "mart_team_season_record",       # ← mart_game_results + ref_teams (+ inlined date_spine)
]

# Group B — the 4 W4-deferred marts + the stg_batter_sprint_speed precursor. Each reads
# RAW/builder-output parquet exported by scripts/export_w5_raw_to_s3.py directly via
# read_parquet(lakehouse_loc(...)) in its duckdb branch (eb_park_factors_raw,
# oaa_team_season_raw, eb_bullpen_team_posteriors, sprint_speed_raw) PLUS the Group-A
# mart_game_spine (registered above). stg_batter_sprint_speed is a staging precursor
# (flattens sprint_speed_raw) — built + registered before the defense-quality mart that
# reads it. ⚠ The builders that WRITE those raw tables (fit_park_priors.py, the
# eb_bullpen_team_posteriors dbt model, the OAA + Savant ingests) keep their Snowflake
# writes — this is the one-time/opt-in S3 mirror (W4 dual-write caveat).
W5B_PRECURSOR_MODELS = ["stg_batter_sprint_speed"]   # ← sprint_speed_raw (parquet)
W5B_MART_MODELS = [
    "mart_eb_park_factors",             # ← eb_park_factors_raw (parquet)
    "mart_bullpen_effectiveness",       # ← stg_batter_pitches + mart_starting_pitcher_game_log + eb_bullpen_team_posteriors (parquet)
    "mart_team_fielding_oaa",           # ← mart_game_spine + oaa_team_season_raw (parquet)
    "mart_team_defense_quality_rolling",# ← oaa_team_season_raw (parquet) + stg_batter_sprint_speed + mart_game_spine
]

# E11.1-W5b: the ARCHETYPE builder-mini-wave (its OWN risk class — Bayesian/k-means →
# TOLERANCE parity, NOT row-exact). The single dual-branch mart reads the W1
# mart_pitch_play_event (registered as a view) + the mart_player_archetype_posteriors
# parquet directly via read_parquet(lakehouse_loc(...)) in its duckdb branch. That parquet
# is produced by betting_ml/scripts/eb_priors/compute_archetype_posteriors.py (--seed for the
# one-time Snowflake→S3 baseline, --s3 to rebuild on DuckDB), which itself reads the migrated
# batter_clusters (cluster_batters.py --s3/--seed) + pitcher_clusters (W4). OPT-IN (--archetype)
# until the posteriors parquet exists + cutover is validated.
ARCHETYPE_MODELS = ["mart_batter_archetype_vs_pitcher_cluster"]

# E11.1-W6: the odds/CLV + odds-serving path (the most serving-coupled tier) + the 2
# Group-C marts inherited from W5. OPT-IN (--w6) until cutover, like W3pre/W4/W5: W6 reads
# precursor parquet (scripts/export_w6_raw_to_s3.py: odds_snapshots_historical +
# daily_model_predictions flat exports, venues_raw RAW JSON) plus the already-migrated
# W3pre staging (stg_oddsapi_*, stg_derivative_odds, stg_statsapi_games) + W5 game chain
# (dim_team_name_lookup, mart_game_spine, mart_game_results) registered as views.
#
# Precursor VIEWS registered (read from S3 parquet, NOT built here):
#   • W5 game chain (data.parquet): dim_team_name_lookup, mart_game_spine, mart_game_results
#   • W3pre flatten (data.parquet): stg_oddsapi_odds, stg_oddsapi_events,
#     stg_derivative_odds, stg_statsapi_games
# Raw/builder parquet read DIRECTLY via read_parquet(lakehouse_loc/raw_loc) in each duckdb
# branch (no registration): odds_snapshots_historical, daily_model_predictions (lakehouse/),
# mlb_odds_raw, venues_raw, monthly_schedule (lakehouse_raw/).
W6_PRECURSOR_VIEWS = [
    # W5 game chain
    "dim_team_name_lookup",
    "mart_game_spine",
    "mart_game_results",
    # W3pre odds/staging flatten
    "stg_oddsapi_odds",
    "stg_oddsapi_events",
    "stg_derivative_odds",
    "stg_statsapi_games",
]

# The 2 Group-C staging flattens (W3pre-style): venues_raw / monthly_schedule RAW JSON →
# stg. Built first so the 2 inherited marts (team_schedule_context / player_game_starts)
# resolve their `from stg_statsapi_venues|lineups` reads.
W6_STG_MODELS = [
    "stg_statsapi_venues",     # ← venues_raw RAW JSON (lakehouse_raw)
    "stg_statsapi_lineups",    # ← monthly_schedule RAW JSON (lakehouse_raw; already exported W3pre)
]

# Built in DEPENDENCY ORDER (each registered as a DuckDB view immediately after build so the
# next model's plain-name reads resolve):
#   odds_outcomes → (events) → game_odds_bridge → consensus/line_movement/closing_line_value
#   → clv_labeled_games → clv_label_count, prediction_clv → derivative_closes
#   → bookmaker_disagreement; the 2 Group-C marts read the stg flattens + mart_game_spine.
W6_MART_MODELS = [
    "mart_odds_outcomes",          # ← stg_oddsapi_odds        (incremental→view; serving)
    "mart_odds_events",            # ← stg_oddsapi_events
    "mart_game_odds_bridge",       # ← dim_team_name_lookup + mart_game_spine + stg_statsapi_games + mart_odds_outcomes (serving)
    "mart_odds_consensus",         # ← mart_odds_outcomes
    "mart_odds_line_movement",     # ← odds_snapshots_historical + stg_statsapi_games + mart_odds_outcomes + mart_game_odds_bridge (serving)
    "mart_closing_line_value",     # ← odds_snapshots_historical + stg_statsapi_games + mart_odds_outcomes + mart_game_odds_bridge
    "mart_clv_labeled_games",      # ← daily_model_predictions + mart_closing_line_value + mart_game_results (serving: performance)
    "mart_clv_label_count",        # ← mart_clv_labeled_games  (view)
    "mart_prediction_clv",         # ← daily_model_predictions + mart_closing_line_value
    "mart_derivative_closes",      # ← stg_derivative_odds + mart_game_odds_bridge
    "mart_bookmaker_disagreement", # ← mlb_odds_raw RAW + mart_game_odds_bridge + mart_odds_outcomes
    "mart_team_schedule_context",  # ← mart_game_spine + stg_statsapi_venues   (Group-C)
    "mart_player_game_starts",     # ← mart_game_spine + stg_statsapi_lineups   (Group-C)
]

# E11.1-W6 INTRADAY REFRESH (operator-decided 2026-06-28, option b — TODAY-SCOPED
# PARTITIONED REBUILD): mart_odds_outcomes (~2.26M rows of mostly-immutable history)
# rebuilds INTRADAY on the odds-capture cycle (odds_current_rebuild_sensor), unlike the
# daily-cadence pitch marts. A full re-flatten each cycle is O(history) → degrades every
# season. Instead the parquet is split into TWO date-bounded buckets that the external
# table UNIONs:
#   mart_odds_outcomes/_history/data.parquet  — commence_date <  today (frozen; daily full build)
#   mart_odds_outcomes/_current/data.parquet  — commence_date >= today (intraday rewrite, O(today))
# The buckets are DISJOINT (split on commence_date == today's LA date) so the UNION is the
# full table with no double-count. The columns (incl. commence_date) stay IN the parquet
# (NOT Hive PARTITION_BY, which would strip the partition column from the file and break the
# external-table column inference). Intraday only _current is rewritten (atomic — a failed
# COPY leaves the prior good _current object live, S3 multipart never exposes a half-write);
# _history is touched ONLY by the daily full build.
W6_PARTITIONED = {"mart_odds_outcomes"}

# The intraday --w6-odds-current pass rebuilds only the odds-serving hot set: mart_odds_outcomes
# (_current bucket) + mart_game_odds_bridge (full — ~26k rows, cheap; its event_id map must
# track new events intraday). The CLV/line-movement marts are post-hoc (closing line locks at
# first pitch) → they stay on the once/day odds_clv path (full rebuild), NOT here.
W6_INTRADAY_MARTS = ["mart_game_odds_bridge"]

# Intraday _current is rebuilt from a RECENT raw window (ingestion dt >= today − N days)
# rather than all history: no game's odds are captured more than ~7 days ahead, so reading
# the last 12 ingestion-date partitions yields the COMPLETE snapshot set for every
# commence_date >= today game (not an approximation), at ~12/season-days the cost. The daily
# full build (reads ALL raw) re-establishes completeness each morning.
W6_ODDS_CURRENT_RAW_DAYS = 12


def find_model(model_name: str) -> Path:
    for subdir in ("staging", "mart", "marts"):
        p = MODELS_DIR / subdir / f"{model_name}.sql"
        if p.exists():
            return p
    # E11.1-W4: the FanGraphs precursor models live in NESTED dirs
    # (dbt/models/staging/fangraphs/, dbt/models/marts/fangraphs/) and the
    # statsapi staging in dbt/models/staging/statsapi/ — the flat lookup above
    # misses them. Fall back to a recursive search (first match wins; model
    # names are unique across the project).
    matches = list(MODELS_DIR.rglob(f"{model_name}.sql"))
    if matches:
        return matches[0]
    raise FileNotFoundError(
        f"Model file not found: {model_name}.sql  "
        f"(searched {MODELS_DIR}/**/ recursively)"
    )


def extract_duckdb_sql(model_name: str) -> str:
    """
    Extract the runnable SQL for a model's duckdb branch.

    Two layouts in these models:
      A) stg_batter_pitches — the entire SELECT is inside
         {% if target.name == 'duckdb' %} … {% else %} … {% endif %}
      B) mart_pitch_* — only {{ config() }} is inside the conditional;
         the WITH … SELECT block lives outside it.
    """
    text = find_model(model_name).read_text()

    if model_name.startswith("stg_"):
        # Layout A: the entire SELECT lives inside the duckdb branch (stg_batter_pitches,
        # stg_ref_players). Pull the duckdb branch out of the if/else.
        m = re.search(
            r'\{%-?\s*if\s+target\.name\s*==\s*[\'"]duckdb[\'"]\s*-?%\}'
            r'(.*?)'
            r'\{%-?\s*else\s*-?%\}',
            text, re.DOTALL,
        )
        if not m:
            raise ValueError(f"Could not find duckdb branch in {model_name}.sql")
        sql = m.group(1)

        # Strip {{ config(...) }}
        sql = re.sub(r'\{\{[^}]*config[^}]*\}\}', '', sql)

        # Resolve any {{ lakehouse_loc("X") }} → S3 path (generic over model name)
        sql = re.sub(
            r'\{\{\s*lakehouse_loc\([\'"](\w+)[\'"]\)\s*\}\}',
            rf"{LAKEHOUSE}/\1/",
            sql,
        )

        # E11.1-W3pre: resolve {{ lakehouse_raw_loc("source") }} → RAW S3 path. The W3pre
        # staging models read the un-flattened source JSON parquet from this tier.
        sql = re.sub(
            r'\{\{\s*lakehouse_raw_loc\([\'"](\w+)[\'"]\)\s*\}\}',
            rf"{LAKEHOUSE_RAW}/\1/",
            sql,
        )

    else:
        # Layout B: mart_pitch_* models (E11.1-W1d dual-branch structure).
        # {{ config() }} at top level, then:
        #   {% if target.name == 'duckdb' %} ... transformation SQL ...
        #   {% else %} ... thin Snowflake view ... {% endif %}
        # Extract the duckdb branch; discard the Snowflake branch.

        # Strip {{ config(...) }} first
        stripped = re.sub(r'\{\{\s*config\(.*?\)\s*\}\}', '', text, flags=re.DOTALL)

        # Extract duckdb branch (content between the if and else)
        m = re.search(
            r'\{%-?\s*if\s+target\.name\s*==\s*[\'"]duckdb[\'"]\s*-?%\}'
            r'(.*?)'
            r'\{%-?\s*else\s*-?%\}',
            stripped, re.DOTALL,
        )
        if not m:
            raise ValueError(
                f"No {{% if target.name == 'duckdb' %}} branch found in {model_name}.sql. "
                "mart_pitch_* models must have a dual-branch structure (E11.1-W1d)."
            )
        sql = m.group(1)

        # Safety-net resolvers (the duckdb branch uses plain table names, not Jinja,
        # but these are kept as a guard against accidental {{ ref() }} / {{ source() }}).
        sql = re.sub(r"\{\{\s*ref\(['\"](\w+)['\"]\)\s*\}\}", r'\1', sql)
        sql = re.sub(
            r"\{\{\s*source\(['\"][^'\"]+['\"],\s*['\"](\w+)['\"]\)\s*\}\}", r'\1', sql
        )

        # E11.1-W4: mart/fct duckdb branches read RAW precursor parquet directly via
        # {{ lakehouse_loc("X") }} (catcher_framing_raw, fg_*_raw, player_profiles_raw,
        # the builder-output parquet eb_park_factors_granular_raw / pitcher_clusters).
        # Layout A already resolved these; do the same for Layout B (mart/fct).
        sql = re.sub(
            r'\{\{\s*lakehouse_loc\([\'"](\w+)[\'"]\)\s*\}\}',
            rf"{LAKEHOUSE}/\1/",
            sql,
        )
        sql = re.sub(
            r'\{\{\s*lakehouse_raw_loc\([\'"](\w+)[\'"]\)\s*\}\}',
            rf"{LAKEHOUSE_RAW}/\1/",
            sql,
        )

        # Strip {% if is_incremental() %} … {% endif %} blocks (safety net)
        sql = re.sub(
            r'\{%-?\s*if\s+is_incremental\(\)\s*-?%\}.*?\{%-?\s*endif\s*-?%\}',
            '', sql, flags=re.DOTALL,
        )

    # E11.1-W8a: the EB-posterior models stamp `'{{ invocation_id }}' as run_id` (dbt's run
    # UUID). DuckDB has no invocation_id; resolve it to a stable literal here. run_id is
    # provenance metadata (not parity-checked — like fit_date), so the literal is value-safe.
    sql = re.sub(r"\{\{\s*invocation_id\s*\}\}", "lakehouse_duckdb", sql)

    # Guard: any surviving Jinja will cause a DuckDB parser error
    if re.search(r'\{[{%]', sql):
        sample = re.findall(r'\{[{%][^}]*?[%}]\}', sql)[:3]
        raise ValueError(f"Unresolved Jinja in {model_name}.sql: {sample}")

    return sql.strip()


def _physical_ram_gb() -> float | None:
    """Total physical RAM in GiB, or None if undetectable (non-Linux dev box)."""
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 ** 3)
    except (ValueError, OSError, AttributeError):
        return None


def _safe_memory_limit_gb() -> int:
    """A DuckDB memory_limit that stays BELOW physical RAM so a flatten can never OOM-KILL
    the box.

    INC-22 (2026-06-29): a hardcoded 11GB memory_limit on a 4 GiB t4g.medium told DuckDB it
    had ~3× the box's RAM, so it never spilled — it blew past physical memory and the kernel
    OOM-killed the EC2 host (Dagster + dbt-runner + flaresolverr with it). The cure is to size
    the limit to physical RAM and leave headroom for the co-resident container stack; spillable
    operators still spill to the temp_directory set in run(). 60% of RAM, floored at 2GB, capped
    at 11GB (the monthly_schedule flatten doesn't need more after the collapse-early dedup, and
    the cap bounds very large boxes). When RAM is undetectable (dev/macOS) fall back to a
    conservative 6GB rather than the old over-allocating 11GB.
    """
    ram = _physical_ram_gb()
    if ram is None:
        return 6
    return max(2, min(11, int(ram * 0.6)))


def _string_timestamp_wrap(conn, mart_sql: str) -> str:
    """Store every TIMESTAMP-family output column as an ISO **VARCHAR** in the parquet.

    ⚠️ ROOT CAUSE (the 24h serving outage): Snowflake's parquet external table reads a binary
    parquet TIMESTAMP INT64 at the WRONG SCALE PER ROW — it interprets the micros value as SECONDS,
    so e.g. 2026-06-30 (1.78e15 micros) materializes as year ~56,000,000, and the Python connector
    raises `252005 … year … is out of range` (EOVERFLOW) on fetch. The trap: `min/max(year(col))`
    and `to_varchar(min(col))` are answered from parquet COLUMN STATISTICS (read correctly), so the
    column looks fine until you fetch / CTAS / dbt-materialize a ROW. Re-casting micros↔nanos does
    NOT help — Snowflake misreads any binary parquet timestamp here.

    CURE (the documented write_pandas-timestamp convention — store VARCHAR ISO, cast downstream):
    cast each TIMESTAMP column to ISO VARCHAR before the COPY. The W8a ext-table DDL then declares
    these columns TIMESTAMP_NTZ AS (VALUE:col::TIMESTAMP_NTZ) — a STRING parse, which Snowflake does
    reliably (verified '2022-04-23 15:59:45.ffffff'::timestamp_ntz round-trips). DATE columns are
    read correctly by Snowflake (INT32 days) so they are left alone — only TIMESTAMP* is stringified.
    Keep generate_w8a_external_tables.TS_STRING_COLS in sync with the columns this stringifies.
    DESCRIBE binds-only (no execution) so it's cheap.

    ⚠️ INC-23 (2026-06-30): a DESCRIBE failure must HALT, NEVER fall back to an unwrapped COPY.
    The prior "warn + return mart_sql (COPY proceeds unwrapped)" was the exact dangerous pattern
    this helper exists to prevent — on a model with TIMESTAMP outputs an unwrapped COPY re-emits the
    BINARY parquet timestamp Snowflake misreads per-row (the year-~56M EOVERFLOW / W8a 24h outage),
    and parity never catches it. DESCRIBE binds the SAME plan the COPY would, so if it fails to bind
    we cannot identify (let alone stringify) the TIMESTAMP columns — we refuse to COPY and raise.
    The recurring trigger is a date function / interval arithmetic applied to a column an upstream
    wrap already stringified to ISO VARCHAR (e.g. year(x) where x is now a parquet-VARCHAR) — fix it
    by casting x::date at the use site (see INC-23 / mart_bookmaker_disagreement.game_date).
    """
    try:
        desc = conn.execute(f"DESCRIBE SELECT * FROM (\n{mart_sql}\n) _d").fetchall()
    except Exception as exc:
        # HALT — do NOT return mart_sql for an unwrapped COPY (would risk shipping a binary parquet
        # timestamp Snowflake misreads per-row). run_w1_lakehouse_op is HALT-tier; raising surfaces
        # the failure loudly on the box at build time, BEFORE any COPY, instead of silently re-
        # introducing the outage class.
        raise RuntimeError(
            "timestamp-stringify DESCRIBE failed — REFUSING to COPY unwrapped (an unwrapped COPY "
            "would risk a binary parquet timestamp that Snowflake's external table misreads per-row: "
            "the year-~56M EOVERFLOW / W8a 24h serving outage). Most common cause: a date function or "
            "interval arithmetic applied to a column an upstream wrap stringified to ISO VARCHAR — "
            "cast that column ::date at the use site. Underlying DuckDB binder error: "
            f"{exc}"
        ) from exc
    ts_cols = [r[0] for r in desc if str(r[1]).upper().startswith("TIMESTAMP")]
    if not ts_cols:
        return mart_sql
    repl = ", ".join(f'"{c}"::varchar AS "{c}"' for c in ts_cols)
    return f"SELECT * REPLACE ({repl}) FROM (\n{mart_sql}\n) _d"


def _build_marts(conn, models: list[str], dry_run: bool) -> None:
    """Extract each model's duckdb-branch SQL and COPY it to S3 parquet."""
    for model in models:
        loc = f"{LAKEHOUSE}/{model}/data.parquet"
        mart_sql = extract_duckdb_sql(model)
        # STRING TIMESTAMP PIN: Snowflake's parquet external table misreads BINARY parquet
        # timestamps per-row (micros read as seconds → year ~56M → connector EOVERFLOW). Store
        # every TIMESTAMP column as ISO VARCHAR; the ext-table DDL parses it back (reliable).
        body = _string_timestamp_wrap(conn, mart_sql)
        # NEWLINE-SAFE WRAP: a type-pinned incremental's DuckDB branch ends in the GENERATED
        # `-- TYPE-PIN-END` line comment (gen_type_contract.py). Inlining `({mart_sql})` on one
        # line would put the closing `)` (and the TO/alias clause) ON that comment line → commented
        # out → "syntax error at end of input". Put the body on its own lines so `)` is never eaten.
        # (The _string wrap, when applied, already encloses mart_sql in an outer SELECT, so the
        # trailing comment is interior — but keep the newlines unconditionally for the no-ts path.)
        if dry_run:
            n = conn.execute(f"SELECT count(*) FROM (\n{body}\n) t").fetchone()[0]
            print(f"  {model}: {n:,} rows  (dry-run — no S3 write)", flush=True)
        else:
            # Print BEFORE the COPY (+ flush) so a stalled S3/httpfs read pinpoints the exact
            # mart: a hang shows "▶ building X …" with no matching "✔ X" — instead of the whole
            # build being one silent black box. The elapsed time also surfaces the slow mart.
            print(f"  ▶ building {model} …", flush=True)
            _t0 = time.monotonic()
            conn.execute(f"COPY (\n{body}\n) TO '{loc}' (FORMAT PARQUET)")
            print(f"  ✔ {model}: written → {loc}  ({time.monotonic() - _t0:.1f}s)", flush=True)


def _register_mart_views(conn, models: list[str], dry_run: bool) -> None:
    """Register built marts as DuckDB views so downstream W2 marts (which read
    plain `mart_pitch_*` names in their duckdb branch) resolve.

    Real run: read the just-written S3 parquet (fast). Dry-run: the parquet may be
    absent/stale (dry-run skips the COPY), so recompute the view from the stg views.
    """
    for model in models:
        if dry_run:
            conn.execute(f"CREATE OR REPLACE VIEW {model} AS {extract_duckdb_sql(model)}")
        elif model in W6_PARTITIONED:
            # Partitioned mart (mart_odds_outcomes): glob both date-bucket subdirs
            # (_history + _current) so downstream W6 marts read the full table.
            glob = f"{LAKEHOUSE}/{model}/**/*.parquet"
            conn.execute(
                f"CREATE OR REPLACE VIEW {model} AS "
                f"SELECT * FROM read_parquet('{glob}', union_by_name=true)"
            )
        else:
            loc = f"{LAKEHOUSE}/{model}/data.parquet"
            conn.execute(
                f"CREATE OR REPLACE VIEW {model} AS SELECT * FROM read_parquet('{loc}')"
            )
        print(f"  registered view: {model}")


def _raw_source_for(model: str) -> str:
    """The lakehouse_raw source a W3pre stg model reads (parsed from its read_parquet)."""
    text = find_model(model).read_text()
    m = re.search(r'lakehouse_raw_loc\([\'"](\w+)[\'"]\)', text)
    return m.group(1) if m else model


def _build_w3pre(conn, dry_run: bool) -> None:
    """Build the W3pre staging tier (each model flattens its raw JSON parquet directly;
    no W1/W2 view dependency, so this runs standalone). A source whose raw tier has no
    parquet yet (export not run) is SKIPPED with a warning rather than crashing the build
    — important because this op is HALT-tier on the daily path once wired in."""
    print("\nW3pre staging (odds/CLV-feeding flatten):")
    # E11.1-W3pre: monthly_schedule blobs are large (~1.4 MB each, ~2.4 GB total) and the
    # stg_statsapi_games flatten explodes them in parallel — that parallelism multiplied peak
    # RAM and OOM'd even with spilling. Cap threads so only a couple of big blobs inflate at
    # once (the OOM error's #1 recommended knob). This tier is tiny (3 trivial odds models +
    # the schedule), so the throughput cost is negligible. Raise if the host has ample RAM.
    # INC-22: set a BOX-AWARE memory_limit (_safe_memory_limit_gb — a fraction of physical RAM,
    # leaving headroom for the co-resident Dagster/dbt-runner/flaresolverr stack), NOT a hardcoded
    # value. The earlier 11GB hardcode OOM-KILLED the 4 GiB t4g.medium host (DuckDB never spilled
    # because the limit was 3× physical RAM). threads=2 caps how many big blobs inflate at once;
    # spillable ops spill to temp_directory (set in run()). The collapse-early dedup keeps the
    # working set small enough that the box-aware limit is ample on the resized host.
    for _pragma in ("SET threads=2", f"SET memory_limit='{_safe_memory_limit_gb()}GB'"):
        conn.execute(_pragma)
    for model in W3PRE_STG_MODELS:
        source = _raw_source_for(model)
        glob = f"{LAKEHOUSE_RAW}/{source}/**/*.parquet"
        try:
            has_files = conn.execute(f"SELECT count(*) FROM glob('{glob}')").fetchone()[0]
        except Exception:
            has_files = 0
        if not has_files:
            print(f"  ⚠️  SKIP {model}: no raw parquet at lakehouse_raw/{source}/ "
                  f"(run scripts/export_odds_raw_to_s3.py --source {source} first)")
            continue
        _build_marts(conn, [model], dry_run)


def _build_w3(conn, dry_run: bool) -> None:
    """Build the W3 pitch-derived marts. Each model is registered as a DuckDB view
    immediately after it is built so the intra-W3 dependency resolves (the only one
    today: mart_batter_vs_pitch_archetype reads mart_pitcher_pitch_archetype). The
    bullpen marts read the already-registered W1 (mart_pitch_play_event) and W2
    (mart_starting_pitcher_game_log) views."""
    print("\nW3 marts:")
    for model in W3_MART_MODELS:
        _build_marts(conn, [model], dry_run)
        # Register so a later W3 model that reads this one resolves.
        _register_mart_views(conn, [model], dry_run)


def _build_w4(conn, dry_run: bool) -> None:
    """Build the E11.1-W4 FanGraphs/posteriors/cluster/raw-savant marts + their
    FanGraphs precursor subtree, in dependency order. Each model is registered as a
    DuckDB view immediately after build so the next model's plain-name reads resolve
    (FG staging → FG fct → statsapi staging → marts; mart_pitcher_arsenal_summary
    precedes mart_pitcher_profile_summary). Raw/builder-output parquet is read
    directly via read_parquet(lakehouse_loc(...)) inside each duckdb branch — no
    registration needed. The W1 marts it reads (mart_pitch_characteristics,
    mart_pitch_play_event) and stg_batter_pitches are registered as views by the
    caller before this runs."""
    print("\nW4 marts (FanGraphs / posteriors-cluster / raw-savant):")
    # E11.1-W4: the FanGraphs flatten (stg_fangraphs__hitting_leaderboard extracts ~60
    # json_extract_string columns + a dedup window) and the pitch-derived marts
    # (mart_batter_woba_vs_cluster reads the full mart_pitch_play_event PA substrate with
    # career-cumulative windows) inflate large intermediates and OOM'd at the box's RAM
    # ceiling (14.3 GiB). Same class as the W3pre schedule flatten — cap parallelism so
    # fewer big intermediates inflate at once, and lower memory_limit so DuckDB spills to
    # temp_directory (set in run()) EARLIER, leaving headroom for small unspillable allocs.
    # value-identical output (every output is a parquet COPY re-globbed downstream).
    for _pragma in ("SET threads=2", f"SET memory_limit='{_safe_memory_limit_gb()}GB'"):
        try:
            conn.execute(_pragma)
        except Exception as _e:
            print(f"  (note: {_pragma} not applied: {_e})")
    for model in W4_BUILD_MODELS:
        _build_marts(conn, [model], dry_run)
        # Register so a later W4 model that reads this one resolves (fct reads staging;
        # mart_pitcher_profile_summary reads mart_pitcher_arsenal_summary).
        _register_mart_views(conn, [model], dry_run)


def _register_s3_glob_views(conn, names: list[str]) -> None:
    """Register S3 parquet directly as DuckDB views by globbing the model dir.

    Used for E11.1-W5 precursors that are NOT built in this run: the tiny seeds
    (ref_teams/ref_team_aliases — part-0.parquet), the W3pre stg_statsapi_games flatten
    (data.parquet), and the W2 mart_starting_pitcher_game_log (data.parquet). None of
    these are year-partitioned, so a flat `<name>/*.parquet` glob matches both the
    part-0/data file naming without a recursive walk."""
    for name in names:
        glob = f"{LAKEHOUSE}/{name}/*.parquet"
        conn.execute(
            f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{glob}')"
        )
        print(f"  registered S3 view: {name}")


def _alert_stale_game_spine(conn) -> None:
    """Spine-staleness ALERT at the SOURCE (2026-07-02).

    Post-W8b-cutover mart_game_spine is SERVING-CRITICAL: the --w8a/--w8b feature build reads it as a
    precursor view, and the served pregame feature store (feature_pregame_game_features) is only as
    fresh as the spine's scheduled-game universe. If a build produces a spine whose games do NOT reach
    the current day — a frozen spine (--w5 not run) OR a stale stg_statsapi_games — the feature store
    loses today's slate and predict_today silently degrades to the intraday-assembly fallback (patchy
    post_lineup coverage). WARN loudly (stderr → ALERT tier) HERE, at the build, rather than only at the
    downstream serving symptom. Never raises — pure observability. Reads the just-registered
    mart_game_spine view; game_date is ISO-VARCHAR in the parquet (INC-23 ts-stringify) so try_cast."""
    try:
        row = conn.execute(
            "select max(try_cast(game_date as date)) as mx, "
            "(max(try_cast(game_date as date)) >= current_date) as covers_today "
            "from mart_game_spine"
        ).fetchone()
    except Exception as e:  # noqa: BLE001 — observability only; never fail the build
        print(f"  (spine-staleness check skipped: {e})", file=sys.stderr)
        return
    mx, covers_today = (row[0] if row else None), (row[1] if row else False)
    if not covers_today:
        print(
            f"WARNING: [spine-staleness] mart_game_spine's scheduled universe does not reach today "
            f"(current_date); max game_date = {mx}. The pregame feature store will LACK the current "
            f"slate → predict_today degrades to the intraday-assembly fallback. Ensure --w5-group-a "
            f"runs daily BEFORE --w8a/--w8b and that stg_statsapi_games is fresh.",
            file=sys.stderr,
        )
    else:
        print(f"[spine-staleness] OK: mart_game_spine reaches today (max game_date {mx}).")


def _build_w5(conn, dry_run: bool, group_b: bool = True) -> None:
    """Build the E11.1-W5 seeds + mart_game_results/mart_game_spine team/game chain
    (Group A, 10 marts) and, optionally, the 4 W4-deferred marts (Group B).

    Group A registers the seed + W3pre precursor views first, then builds each mart in
    dependency order, registering it as a DuckDB view immediately so the next model's
    plain-name reads resolve (dim_team_name_lookup + mart_game_results → mart_game_spine
    → the team/game leaves). The W1 mart_pitch_* + stg_batter_pitches it reads are
    registered as views by the caller before this runs.

    Group B reads its raw/builder parquet (eb_park_factors_raw, oaa_team_season_raw,
    eb_bullpen_team_posteriors, sprint_speed_raw) DIRECTLY via read_parquet(lakehouse_loc)
    in each model's duckdb branch — no view registration — plus the Group-A mart_game_spine
    + the W2 mart_starting_pitcher_game_log (registered here). A Group B raw parquet that
    is absent (export not run) makes that mart's build raise; Group B is gated by the
    caller (opt-in) so the daily HALT op never trips on a missing precursor."""
    print("\nW5 precursor views (seeds + W3pre stg_statsapi_games):")
    _register_s3_glob_views(conn, W5_SEED_VIEWS + W5_PRECURSOR_VIEWS)

    print("\nW5 Group A marts (game-results team/game chain):")
    for model in W5_MART_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)

    # Spine now built + registered — ALERT if its scheduled universe doesn't reach today (serving-critical).
    _alert_stale_game_spine(conn)

    if not group_b:
        return

    print("\nW5 Group B marts (W4-deferred) + stg_batter_sprint_speed precursor:")
    # mart_bullpen_effectiveness reads the W2 mart_starting_pitcher_game_log.
    _register_s3_glob_views(conn, ["mart_starting_pitcher_game_log"])
    for model in W5B_PRECURSOR_MODELS + W5B_MART_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)


def _alert_stale_w5b(conn) -> None:
    """W5b staleness ALERT at the SOURCE (2026-07-02). Post-W8b-cutover the --w8b aggregator reads the
    W5b park/defense/bullpen-effectiveness feature VALUES; if --w5b doesn't run daily these marts
    freeze and the served features drift stale (stale VALUES, not missing games — lower severity than
    the spine's missing slate). WARN (stderr → ALERT tier) if the per-game rolling defense mart does
    not reach today. Never raises — pure observability. game_date is ISO-VARCHAR in the parquet
    (INC-23) so try_cast."""
    try:
        row = conn.execute(
            "select max(try_cast(game_date as date)) as mx, "
            "(max(try_cast(game_date as date)) >= current_date) as covers_today "
            "from mart_team_defense_quality_rolling"
        ).fetchone()
    except Exception as e:  # noqa: BLE001 — observability only; never fail the build
        print(f"  (w5b-staleness check skipped: {e})", file=sys.stderr)
        return
    mx, covers_today = (row[0] if row else None), (row[1] if row else False)
    if not covers_today:
        print(
            f"WARNING: [w5b-staleness] mart_team_defense_quality_rolling does not reach today "
            f"(max game_date {mx}); the W5b park/defense/bullpen-effectiveness feature VALUES the "
            f"aggregator reads are stale. Ensure --w5b-only runs daily (between --w8a and --w8b).",
            file=sys.stderr,
        )
    else:
        print(f"[w5b-staleness] OK: mart_team_defense_quality_rolling reaches today (max game_date {mx}).")


def _build_w5b(conn, dry_run: bool) -> None:
    """Build ONLY the W5 Group-B marts (the 4 W4-deferred park/defense/bullpen-effectiveness marts +
    the stg_batter_sprint_speed precursor), reusing the existing Group-A + W2 parquet.

    WHY --w5b-only exists (2026-07-02, sibling of the spine fix): the W8b cutover made these marts
    serving-relevant — the --w8b aggregator reads their feature VALUES — but --w5 isn't in the daily
    build, so they froze at the last manual --w5 run and drift stale (stale VALUES, not missing games).
    W5b reads the W8a EB posteriors (eb_bullpen_team_posteriors parquet) so it must run AFTER --w8a;
    the aggregator reads W5b so it must run BEFORE --w8b → the daily slot is between --w8a and --w8b
    (Group A / --w5-group-a-only still runs before --w8a — it's the game universe). Registers the
    Group-A marts it reads (mart_game_spine etc.) + the W2 mart_starting_pitcher_game_log from their
    existing parquet; the raw inputs (eb_park_factors_raw, oaa_team_season_raw,
    eb_bullpen_team_posteriors, sprint_speed_raw) are read directly via read_parquet in each model."""
    print("\nW5b Group-B marts (reuse existing Group-A/W2 parquet for --w5b-only):")
    # Register the Group-A deps as views (read the existing parquet on a real run; recomputed from the
    # seed + W3pre precursor views in --dry-run, hence registering those first).
    _register_s3_glob_views(conn, W5_SEED_VIEWS + W5_PRECURSOR_VIEWS)
    _register_mart_views(conn, ["dim_team_name_lookup", "mart_game_results", "mart_game_spine"], dry_run)
    _register_s3_glob_views(conn, ["mart_starting_pitcher_game_log"])
    for model in W5B_PRECURSOR_MODELS + W5B_MART_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)
    _alert_stale_w5b(conn)


def _build_archetype(conn, dry_run: bool) -> None:
    """Build the E11.1-W5b archetype mart (mart_batter_archetype_vs_pitcher_cluster). It
    reads the W1 mart_pitch_play_event (registered as a DuckDB view) + the
    mart_player_archetype_posteriors parquet directly via read_parquet(lakehouse_loc(...))
    in its duckdb branch. ⚠️ TOLERANCE risk class — the posteriors are Bayesian; when they
    are rebuilt on DuckDB (compute_archetype_posteriors.py --s3) rather than seeded, this
    mart's adj_woba/adj_xwoba carry ~3rd-decimal float drift (parity_check_w5b uses bands)."""
    print("\nW5b archetype mart (mart_batter_archetype_vs_pitcher_cluster):")
    # mart_pitch_play_event is the only registered-view dependency (the posteriors parquet
    # is read directly). It is registered by the caller for the full path; register here too
    # so --archetype-only works standalone.
    _register_mart_views(conn, ["mart_pitch_play_event"], dry_run)
    for model in ARCHETYPE_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)


def _la_today(conn) -> str:
    """Today's calendar date in America/Los_Angeles (the tz mart_odds_outcomes.commence_date
    is computed in) as an ISO string. The _history/_current split boundary — the daily full
    build and every intraday rebuild within the same LA day agree on it."""
    return conn.execute(
        "SELECT (now() AT TIME ZONE 'America/Los_Angeles')::date::varchar"
    ).fetchone()[0]


def _register_recent_stg_oddsapi_odds(conn, boundary: str) -> None:
    """Register stg_oddsapi_odds as a RECENT-SCOPED flatten for the intraday _current rebuild:
    flatten only the last W6_ODDS_CURRENT_RAW_DAYS ingestion-date partitions of
    lakehouse_raw/mlb_odds_raw (a literal list of dt= globs, so DuckDB never lists the full
    history). That window covers every snapshot of every commence_date >= today game (odds
    are never captured >~7 days ahead), so the resulting _current bucket is COMPLETE."""
    from datetime import date, timedelta
    b = date.fromisoformat(boundary)
    globs = ",".join(
        f"'{LAKEHOUSE_RAW}/mlb_odds_raw/dt={(b - timedelta(days=d)).isoformat()}/**/*.parquet'"
        for d in range(W6_ODDS_CURRENT_RAW_DAYS + 1)
    )
    full_sql = extract_duckdb_sql("stg_oddsapi_odds")
    # Point the model's full-history glob at the recent dt= window (missing dt= dirs are
    # silently skipped by read_parquet's list form).
    recent_sql = full_sql.replace(
        f"'{LAKEHOUSE_RAW}/mlb_odds_raw/**/*.parquet'",
        f"[{globs}]",
    )
    if recent_sql == full_sql:
        raise RuntimeError(
            "stg_oddsapi_odds raw glob not found for recent-scope rewrite — the model's "
            "read_parquet path changed; update _register_recent_stg_oddsapi_odds."
        )
    conn.execute(f"CREATE OR REPLACE VIEW stg_oddsapi_odds AS {recent_sql}")
    print(f"  registered RECENT-scoped stg_oddsapi_odds (dt >= {b - timedelta(days=W6_ODDS_CURRENT_RAW_DAYS)})")


def _build_odds_outcomes(conn, dry_run: bool, boundary: str, intraday: bool) -> None:
    """Build mart_odds_outcomes into its two date-bucket subdirs (E11.1-W6 option b).

    intraday=False (daily full build): rewrite BOTH _history (commence_date < boundary) and
    _current (commence_date >= boundary) from the full stg_oddsapi_odds.
    intraday=True: rewrite ONLY _current from the recent-scoped stg_oddsapi_odds (caller must
    register it first). _history is left untouched. The COPY targets a single object per
    bucket; S3 multipart makes the swap effectively atomic (a failed COPY leaves the prior
    good object live)."""
    model = "mart_odds_outcomes"
    base = f"{LAKEHOUSE}/{model}"
    mart_sql = extract_duckdb_sql(model)
    cur = f"SELECT * FROM ({mart_sql}) t WHERE commence_date >= DATE '{boundary}'"
    hist = f"SELECT * FROM ({mart_sql}) t WHERE commence_date <  DATE '{boundary}'"
    if dry_run:
        n_cur = conn.execute(f"SELECT count(*) FROM ({cur})").fetchone()[0]
        print(f"  {model} _current (>= {boundary}): {n_cur:,} rows  (dry-run)")
        if not intraday:
            n_hist = conn.execute(f"SELECT count(*) FROM ({hist})").fetchone()[0]
            print(f"  {model} _history (<  {boundary}): {n_hist:,} rows  (dry-run)")
        return
    conn.execute(f"COPY ({cur}) TO '{base}/_current/data.parquet' (FORMAT PARQUET)")
    print(f"  {model}: _current (>= {boundary}) written → {base}/_current/data.parquet")
    if not intraday:
        conn.execute(f"COPY ({hist}) TO '{base}/_history/data.parquet' (FORMAT PARQUET)")
        print(f"  {model}: _history (<  {boundary}) written → {base}/_history/data.parquet")


def _build_w6_precursor_views(conn) -> None:
    """Register the shared W6 precursor views (W5 game chain + W3pre odds/staging flatten +
    the two typed flat-export views). Used by both the daily and intraday W6 builds."""
    print("\nW6 precursor views (W5 game chain + W3pre odds/staging flatten):")
    _register_s3_glob_views(conn, W6_PRECURSOR_VIEWS)
    print("\nW6 typed precursor views (odds_snapshots_historical + daily_model_predictions):")
    conn.execute(
        "CREATE OR REPLACE VIEW odds_snapshots_historical AS "
        "SELECT * REPLACE ("
        "  snapshot_ts::timestamptz AS snapshot_ts,"
        "  game_date::date          AS game_date,"
        "  loaded_at::timestamptz   AS loaded_at"
        f") FROM read_parquet('{LAKEHOUSE}/odds_snapshots_historical/*.parquet', union_by_name=true)"
    )
    print("  registered typed view: odds_snapshots_historical")
    conn.execute(
        "CREATE OR REPLACE VIEW daily_model_predictions AS "
        "SELECT * REPLACE ("
        "  score_date::date       AS score_date,"
        "  game_date::date        AS game_date,"
        "  inserted_at::timestamp AS inserted_at,"
        "  game_datetime::timestamp AS game_datetime"
        f") FROM read_parquet('{LAKEHOUSE}/daily_model_predictions/*.parquet', union_by_name=true)"
    )
    print("  registered typed view: daily_model_predictions")


def _build_w6_odds_current(conn, dry_run: bool) -> None:
    """E11.1-W6 INTRADAY pass (--w6-odds-current): rewrite ONLY the odds-serving hot set —
    mart_odds_outcomes _current bucket (today + future games, from a recent raw window) +
    mart_game_odds_bridge (full; cheap). Fired by the odds_current_rebuild path AFTER the
    capture exports today's mlb_odds_raw → S3. _history is untouched (frozen by the daily
    build). The caller (intraday op) then refreshes only these external tables."""
    _build_w6_precursor_views(conn)
    for _pragma in ("SET threads=2", f"SET memory_limit='{_safe_memory_limit_gb()}GB'"):
        try:
            conn.execute(_pragma)
        except Exception as _e:
            print(f"  (note: {_pragma} not applied: {_e})")
    boundary = _la_today(conn)
    print(f"\nW6 intraday rebuild (LA today = {boundary}):")
    # Recent-scoped stg so the _current flatten is O(recent), not O(history).
    _register_recent_stg_oddsapi_odds(conn, boundary)
    _build_odds_outcomes(conn, dry_run, boundary, intraday=True)
    _register_mart_views(conn, ["mart_odds_outcomes"], dry_run)
    # bridge reads the FULL mart_odds_outcomes (both buckets, just re-registered) — small,
    # full rebuild keeps its event_id map fresh for today's games.
    for model in W6_INTRADAY_MARTS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)


def _build_w6(conn, dry_run: bool) -> None:
    """Build the E11.1-W6 odds/CLV + odds-serving marts (13) + the 2 Group-C staging
    flattens (the DAILY full build). Registers the W5 game chain + W3pre odds/staging
    flattens as views first, then builds the 2 stg flattens (venues/lineups RAW JSON), then
    the 13 marts in dependency order — each registered as a DuckDB view immediately after
    build so the next model's plain-name reads resolve. mart_odds_outcomes is built into its
    _history/_current date buckets (see W6_PARTITIONED); every other mart writes a single
    data.parquet. The raw/builder parquet (odds_snapshots_historical, daily_model_predictions,
    mlb_odds_raw, venues_raw, monthly_schedule) is read DIRECTLY via
    read_parquet(lakehouse_loc/raw_loc) in each duckdb branch — no view registration."""
    _build_w6_precursor_views(conn)

    # The stg_statsapi_lineups flatten explodes the same large monthly_schedule month-blobs
    # as the W3pre stg_statsapi_games (the known OOM source); the bookmaker_disagreement
    # historical path re-flattens mlb_odds_raw. Cap parallelism + lower memory_limit so
    # DuckDB spills to temp_directory (set in run()) rather than OOMing. value-identical
    # output (every output is a parquet COPY re-globbed downstream).
    for _pragma in ("SET threads=2", f"SET memory_limit='{_safe_memory_limit_gb()}GB'"):
        try:
            conn.execute(_pragma)
        except Exception as _e:
            print(f"  (note: {_pragma} not applied: {_e})")

    boundary = _la_today(conn)
    print(f"\nW6 daily full build (mart_odds_outcomes _history/_current split at LA today = {boundary}):")

    print("\nW6 Group-C staging flattens (venues / lineups RAW JSON):")
    for model in W6_STG_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)

    print("\nW6 marts (odds/CLV + odds-serving + Group-C):")
    for model in W6_MART_MODELS:
        if model in W6_PARTITIONED:
            # mart_odds_outcomes — write both date buckets (_history + _current), then
            # register the union view so downstream W6 marts read the full table.
            _build_odds_outcomes(conn, dry_run, boundary, intraday=False)
        else:
            _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)


# E11.1-W7b: the prediction/serving-path mini-wave — the mart_player_profile_identity injury
# chain + the serving-mart backlog (stg_statsapi_probable_pitchers / stg_statsapi_lineups_wide).
# OPT-IN (--w7b) until cutover, like W3pre/W4/W5/W6: reads the player_transactions precursor
# parquet (scripts/export_w7b_precursors_to_s3.py) + the W2/W4/W6 marts (registered as views) +
# the monthly_schedule raw tier (already exported). Enable with --w7b once the precursor export
# is wired and parity is validated. Each builds a single data.parquet; the Snowflake side is a
# view over the lakehouse_ext external table (generate_w7b_external_tables.py).
#
# Precursor VIEWS registered (read from S3 parquet, NOT built here):
#   • W2 marts: mart_batter_rolling_stats, mart_starting_pitcher_game_log
#   • W4 staging: stg_statsapi_player_profiles
#   • W6 staging: stg_statsapi_lineups
# Read DIRECTLY via read_parquet(lakehouse_loc/raw_loc) in the duckdb branch (no registration):
#   • player_transactions (lakehouse/), monthly_schedule (lakehouse_raw/).
W7B_PRECURSOR_VIEWS = [
    "mart_batter_rolling_stats",
    "mart_starting_pitcher_game_log",
    "stg_statsapi_player_profiles",
    "stg_statsapi_lineups",
]

# Built in DEPENDENCY ORDER (each registered as a DuckDB view immediately after build so the next
# model's plain-name reads resolve): the injury chain feeds mart_player_profile_identity.
W7B_CHAIN_MODELS = [
    "stg_statsapi_transactions",          # ← player_transactions (parquet, read_parquet lakehouse_loc)
    "stg_statsapi_player_injury_status",  # ← stg_statsapi_transactions
    "feature_pregame_injury_status",      # ← stg_statsapi_player_injury_status (SCD-2)
    "mart_player_profile_identity",       # ← W2/W4/W6 precursors + feature_pregame_injury_status
]

# Independent serving-mart backlog (no intra-W7b dep): probable_pitchers flattens monthly_schedule
# raw directly; lineups_wide pivots the registered W6 stg_statsapi_lineups view.
W7B_BACKLOG_MODELS = [
    "stg_statsapi_probable_pitchers",     # ← monthly_schedule raw (lakehouse_raw)
    "stg_statsapi_lineups_wide",          # ← stg_statsapi_lineups (W6 view)
]

W7B_MODELS = W7B_CHAIN_MODELS + W7B_BACKLOG_MODELS


def _build_w7b(conn, dry_run: bool) -> None:
    """Build the E11.1-W7b prediction/serving mini-wave: the mart_player_profile_identity injury
    chain (dependency-ordered, each registered as a view immediately after build) + the serving-mart
    backlog (probable_pitchers reads monthly_schedule raw directly; lineups_wide reads the registered
    W6 stg_statsapi_lineups). Registers the W2/W4/W6 precursor views first. The player_transactions
    precursor parquet + monthly_schedule raw are read directly via read_parquet(lakehouse_loc/raw_loc)
    in each duckdb branch — no registration. A missing precursor makes a build raise; W7b is gated
    (opt-in) so the daily HALT op never trips on it pre-cutover."""
    print("\nW7b precursor views (W2 rolling marts + W4 profiles + W6 lineups):")
    _register_s3_glob_views(conn, W7B_PRECURSOR_VIEWS)

    # The probable_pitchers flatten explodes the same large monthly_schedule month-blobs as
    # stg_statsapi_games (the known OOM source) → cap parallelism + lower memory_limit so DuckDB
    # spills rather than OOMing. value-identical output (every output is a parquet COPY).
    for _pragma in ("SET threads=2", f"SET memory_limit='{_safe_memory_limit_gb()}GB'"):
        try:
            conn.execute(_pragma)
        except Exception as _e:
            print(f"  (note: {_pragma} not applied: {_e})")

    print("\nW7b injury chain → mart_player_profile_identity:")
    for model in W7B_CHAIN_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)

    print("\nW7b serving-mart backlog (probable_pitchers / lineups_wide):")
    for model in W7B_BACKLOG_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)


# E11.1-W8a: the INDEPENDENT half of the feature tree — feature/status models + the EB
# posteriors that depend ONLY on already-S3 marts/staging/refs/signal-stores (NO dependency
# on the W8b serving aggregator). OPT-IN (--w8a) until cutover, like W3pre/W4/W5/W6/W7b: reads
# precursor parquet that must exist first:
#   • the W8a Python-table mirrors + EB seeds (scripts/export_w8a_precursors_to_s3.py)
#   • the W9 signal stores (scripts/export_w9_signals_to_s3.py)
#   • the prior-wave marts/staging (W1-W7b), registered as DuckDB views from existing S3 parquet
#   • monthly_schedule RAW (lakehouse_raw; read directly by stg_statsapi_starter_snapshots)
# Each W8a model builds a single data.parquet; the Snowflake side is a view/table over the
# lakehouse_ext external table (generate_w8a_external_tables.py).
#
# ⚠️ BUILD-ORDER NOTE (eb_bullpen_team_posteriors → mart_bullpen_effectiveness): the W5b mart
# mart_bullpen_effectiveness reads eb_bullpen_team_posteriors S3 parquet (was the export_w5
# mirror; W8a now BUILDS it). In a FULL rebuild run --w8a BEFORE --w5 so the W5b mart reads the
# fresh EB parquet; in the daily flow the EB posteriors change slowly (1-day-stale is acceptable
# and parity-checkable). The W8a build is otherwise independent of the serving aggregator.
W8A_PRECURSOR_VIEWS = [
    # W1
    "mart_pitch_play_event",
    # W2
    "mart_batter_rolling_stats", "mart_starting_pitcher_game_log",
    # W3
    "mart_batter_vs_handedness_splits", "mart_bullpen_workload", "mart_team_vs_pitcher_hand",
    # W4
    "stg_fangraphs__zips_hitting", "mart_park_factors_granular",
    # W5 game/team chain
    "mart_game_results", "mart_game_spine", "mart_park_run_factors",
    "mart_team_pythagorean_rolling", "mart_team_rolling_offense", "mart_team_rolling_pitching",
    "mart_team_season_record",
    # W5b
    "mart_eb_park_factors", "mart_bullpen_effectiveness", "mart_team_fielding_oaa",
    # W6
    "stg_statsapi_venues", "mart_game_odds_bridge", "mart_odds_consensus",
    "mart_team_schedule_context", "stg_statsapi_lineups",
    # W7b
    "stg_statsapi_probable_pitchers",
    # W9 signal stores (feature_pregame_sub_model_signals reads all 5)
    "mart_sub_model_signals", "offense_v1_signals", "offense_v2_signals",
    "starter_suppression_signals", "starter_ip_signals",
    # W8a Python-table mirrors (scripts/export_w8a_precursors_to_s3.py)
    "mart_player_start_probability", "feature_pregame_market_features", "player_sequential_posteriors",
    # team_elo_history (compute_elo output; Python-written source read by feature_pregame_team_features
    # via a hardcoded source(). Already mirrored by W7b export_features_to_s3.py, AND by the W8a
    # precursor export for --w8a-only self-containment — same low-risk full-table mirror pattern.)
    "team_elo_history",
    # W8a EB-prior seeds (mirrored alongside)
    "ref_eb_starter_priors", "ref_eb_lineup_priors", "ref_eb_bullpen_priors",
]

# Feature/status models, dependency-ordered (each registered as a view after build so intra-W8a
# reads resolve — stg_statsapi_starter_snapshots precedes feature_pregame_starter_status).
W8A_FEATURE_MODELS = [
    "stg_statsapi_starter_snapshots",   # ← monthly_schedule RAW (lakehouse_raw); retains all snapshots
    "feature_pregame_starter_status",   # ← stg_statsapi_starter_snapshots (SCD-2)
    "feature_pregame_park_status",      # ← mart_eb_park_factors + mart_game_results + stg_statsapi_venues (SCD-2)
    "feature_pregame_park_features",    # ← mart_game_spine + park marts + stg_statsapi_venues
    "feature_pregame_team_features",    # ← team marts + bullpen marts + team_elo_history (mirrored precursor)
    "feature_pregame_expected_lineup",  # ← mart_player_start_probability + batter rolling/platoon marts
    "feature_pregame_odds_features",    # ← mart_game_spine/odds_bridge/consensus + feature_pregame_market_features
    "feature_pregame_sub_model_signals",# ← the 5 W9 signal stores
]

# EB posteriors (ALL INCREMENTAL on Snowflake; DuckDB = full COPY). Dependency-ordered:
# int_bullpen_ali → eb_bullpen_posteriors → eb_bullpen_team_posteriors; eb_starter/eb_batter
# are independent leaves (read player_sequential_posteriors mirror + seeds).
W8A_EB_MODELS = [
    "int_bullpen_ali_by_season",        # ← stg_batter_pitches + mart_pitch_play_event + mart_starting_pitcher_game_log
    "eb_bullpen_posteriors",            # ← int_bullpen_ali + mart_starting_pitcher_game_log + ref_eb_bullpen_priors + stg_batter_pitches
    "eb_bullpen_team_posteriors",       # ← eb_bullpen_posteriors + mart_game_spine
    "eb_starter_posteriors",            # ← mart_starting_pitcher_game_log + ref_eb_starter_priors + stg_statsapi_probable_pitchers + player_seq
    "eb_batter_posteriors_raw",         # ← mart_batter_rolling_stats + ref_eb_lineup_priors + stg_fangraphs__zips_hitting + stg_statsapi_lineups + player_seq
]

W8A_MODELS = W8A_FEATURE_MODELS + W8A_EB_MODELS


def _register_w8a_views(conn, names: list[str]) -> None:
    """Register W8a precursor parquet as DuckDB views with the UNIVERSAL
    `<name>/**/*.parquet` glob (union_by_name=true) so single-file marts, the seed
    part-0.parquet, year-partitioned tables, AND W6 date-bucketed marts all resolve
    through one code path (same contract as scripts/utils/lakehouse_read.register_views)."""
    for name in names:
        glob = f"{LAKEHOUSE}/{name}/**/*.parquet"
        conn.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_parquet('{glob}', union_by_name=true)"
        )
        print(f"  registered S3 view: {name}")


def _build_w8a(conn, dry_run: bool) -> None:
    """Build the E11.1-W8a upstream feature layer + EB posteriors. Registers the prior-wave +
    W9 + W8a-mirror precursor views first, then builds the feature/status models and the EB
    posteriors in dependency order (each registered as a view immediately after build). The
    monthly_schedule RAW (stg_statsapi_starter_snapshots) + the seed/mirror parquet are read via
    read_parquet / registered views — a missing precursor makes a build raise; W8a is gated
    (opt-in) so the daily HALT op never trips on it pre-cutover."""
    print("\nW8a precursor views (prior-wave marts/staging + W9 signal stores + W8a mirrors/seeds):")
    _register_w8a_views(conn, W8A_PRECURSOR_VIEWS)

    # stg_statsapi_starter_snapshots RETAINS every (game_pk, side, ingestion_ts) snapshot, so the
    # monthly_schedule month-blob flatten is NOT collapsed early (the OOM source — same as
    # stg_statsapi_games). Cap parallelism + lower memory_limit so DuckDB spills rather than OOMs.
    for _pragma in ("SET threads=2", f"SET memory_limit='{_safe_memory_limit_gb()}GB'"):
        try:
            conn.execute(_pragma)
        except Exception as _e:
            print(f"  (note: {_pragma} not applied: {_e})")

    print("\nW8a feature/status models (dependency-ordered):")
    for model in W8A_FEATURE_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)

    print("\nW8a EB posteriors (dependency-ordered; run BEFORE --w5 in a full rebuild — see note):")
    for model in W8A_EB_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)


# INC-25 (2026-07-01): the 5 W9 signal STORES the consumer feature_pregame_sub_model_signals reads
# (subset of W8A_PRECURSOR_VIEWS; kept as its own name so the narrow rebuild below registers exactly
# these and nothing else).
W9_SIGNAL_STORE_VIEWS = [
    "mart_sub_model_signals", "offense_v1_signals", "offense_v2_signals",
    "starter_suppression_signals", "starter_ip_signals",
]


def _build_sub_model_signals_consumer(conn, dry_run: bool) -> None:
    """INC-25: rebuild ONLY the feature_pregame_sub_model_signals consumer parquet from the freshly
    exported W9 signal-store parquets.

    WHY: the full --w8a build runs at daily-job START — BEFORE the day's signal generators write the
    stores AND before export_w9_signals_to_s3 mirrors them to S3 — so the consumer parquet it
    produces lags the stores by a full slate. After the W8a cutover the Snowflake consumer is
    `select * from lakehouse_ext.feature_pregame_sub_model_signals` = that stale parquet, so
    signal_freshness_check sees the SCD-2 groups (run_env/bullpen/matchup/env/defense) missing on the
    freshest completed slate and HALTs the daily job (INC-25). The daily job runs this narrow rebuild
    AFTER export_w9_signals_to_s3 refreshes the store parquets, so the consumer reflects the current
    slate before the SF materialize + the freshness gate. Reads only the 5 store parquets (glob
    views) — no prior-wave parquet needed, so it is standalone + fast (a single pivot)."""
    print("\nINC-25: rebuilding feature_pregame_sub_model_signals from fresh W9 store parquets:")
    _register_w8a_views(conn, W9_SIGNAL_STORE_VIEWS)
    _build_marts(conn, ["feature_pregame_sub_model_signals"], dry_run)


# E11.1-W8b: the SERVING-CRITICAL half — the complex upstream feature models (starter/lineup/
# bullpen-state), the 3 lineup-matchup models (the INC-17-P2 dual-source-lineup class), THE
# AGGREGATOR feature_pregame_game_features_raw (+ its public wrapper feature_pregame_game_features)
# and feature_league_contact_baseline. OPT-IN (--w8b) until cutover, like the prior waves: reads
# precursor parquet that must exist first:
#   • the W8b precursor mirrors (scripts/export_w8b_precursors_to_s3.py): feature_pregame_lineup_state
#     (SCD-2; the INC-17-P2 source), team_sequential_posteriors (Epic 16.3), stg_actionnetwork_public_betting.
#   • fct_fangraphs_pitching_analytics (ZiPS FIP) is now W4-BUILT natively in DuckDB (E11.1-W11-FG:
#     stg_fangraphs__zips_pitching + fct dual-branched; fg_zips_pitching_raw from S3). It writes the SAME
#     lakehouse/fct_fangraphs_pitching_analytics/data.parquet this build registers below, so it was
#     DROPPED from the export mirror (its uppercase SELECT * cols would have broken the W4 ext table's
#     lowercase VALUE: accessors). ZiPS 'zips' rows are pre-season static → no daily rebuild needed.
#   • the W7b-1 feature mirror (scripts/export_features_to_s3.py) for the W11-deferred tail the
#     aggregator still reads: feature_pregame_umpire_features, feature_pregame_weather_features.
#   • the prior-wave (W1-W8a) marts/staging/feature-layer parquet already in S3 + the W7a clusters +
#     the W7b injury chain — all registered as DuckDB views.
#
# ⚠️ The 2 macro models (feature_league_contact_baseline + feature_pregame_game_features) cannot go
# through extract_duckdb_sql (it is a regex pseudo-renderer that errors on the as_of_contact_baseline()
# / contact_quality_columns() Jinja loops). They are built by dedicated Python builders that PORT the
# macro (reading the canonical 34-column list from dbt/macros/season_normalize_contact.sql — the single
# source of truth) so the DuckDB build can never drift from the Snowflake macro's column list.
W8B_PRECURSOR_VIEWS = [
    # W1-W6 marts read by the feature/matchup models + the aggregator
    "mart_game_spine", "mart_game_results", "mart_team_base_state_splits",
    "mart_pitcher_rolling_stats", "mart_starting_pitcher_game_log",
    "mart_pitcher_vs_handedness_splits", "mart_starter_csw_rolling",
    "mart_starter_pitch_mix_rolling", "mart_starter_tto_splits",
    "mart_catcher_framing", "mart_batter_rolling_stats",
    "mart_batter_vs_handedness_splits", "mart_batter_vs_pitch_archetype",
    "mart_batter_bat_tracking_profile", "mart_pitcher_pitch_archetype",
    "mart_pitcher_batter_history", "mart_batter_woba_vs_cluster",
    "mart_batter_archetype_vs_pitcher_cluster", "mart_bullpen_workload",
    "mart_bullpen_handedness_splits", "mart_bullpen_leverage",
    "mart_reliever_top3_availability", "mart_odds_line_movement",
    "mart_bookmaker_disagreement",
    # W4 fct + stg
    "fct_fangraphs_pitcher_arsenal_wide", "stg_fangraphs__zips_hitting",
    # W3pre / W6 / W7b staging
    "stg_statsapi_games", "stg_statsapi_lineups_wide", "stg_statsapi_probable_pitchers",
    # E1.11 Phase 2 — starter + lineup features read stg_statsapi_transactions (W7b parquet,
    # written by --w7b before --w8b in the daily op) for the recently-acquired / traded-player
    # context (is_recently_acquired, days_on_team, same-team form). Fresh via the daily --w7b run.
    "stg_statsapi_transactions",
    # W7a clusters (lakehouse_clusters source)
    "pitcher_clusters", "batter_clusters",
    # W7b injury chain (already in S3; read by lineup_features)
    "feature_pregame_injury_status",
    # W8a feature layer (already in S3; read by the aggregator)
    "feature_pregame_expected_lineup", "feature_pregame_odds_features",
    "feature_pregame_park_features", "feature_pregame_team_features",
    # W8a EB posteriors (read by starter/lineup features)
    "eb_starter_posteriors", "eb_batter_posteriors_raw",
    # W11-deferred tail the aggregator still reads — mirrored by export_features_to_s3.py (W7b-1)
    "feature_pregame_umpire_features", "feature_pregame_weather_features",
    # W8b NEW precursor mirrors (export_w8b_precursors_to_s3.py)
    "feature_pregame_lineup_state", "team_sequential_posteriors",
    "stg_actionnetwork_public_betting",
    # fct_fangraphs_pitching_analytics is now W4-BUILT (E11.1-W11-FG) — this registers its W4
    # data.parquet as a view; the W4 build must have run so the parquet exists (ZiPS static).
    "fct_fangraphs_pitching_analytics",
]

# Dialect-clean feature/matchup models + the aggregator, DEPENDENCY-ORDERED (each registered as a
# DuckDB view immediately after build so the next model's plain-name reads resolve). The aggregator
# reads the 3 matchup models + lineup/starter features + the W8a layer, so it is built LAST here.
W8B_FEATURE_MODELS = [
    "feature_pregame_starter_features",        # ← marts + eb_starter + clusters + probable + fct_fangraphs_pitching_analytics
    "feature_pregame_lineup_features",         # ← lineup_state + lineups_wide + injury + starter_features + eb_batter + clusters + marts
    "feature_pregame_bullpen_state_features",  # ← lineup_features + bullpen marts + game_spine
    "feature_batter_archetype_matchups",       # ← lineup_state + clusters + archetype mart + probable + game_spine
    "feature_pitcher_batter_h2h_matchups",     # ← lineup_state + pitcher_batter_history + probable + game_spine
    "feature_pitcher_cluster_matchups",        # ← lineup_state + batter_woba_vs_cluster + clusters + probable + game_spine
    "feature_pregame_game_features_raw",       # ← THE AGGREGATOR (all the above + W8a layer + W8b mirrors); TYPE-PIN incremental
]

# 🧨 DuckDB filter_pushdown is_current binder bug (W8b first-build HALT 2026-06-30; DISTINCT from the
# INC-23 year(VARCHAR) incident — operator to assign a number) — precursor parquet that must be
# MATERIALIZED into a DuckDB table (not a glob VIEW) so a downstream `where is_current = true` +
# `qualify` + wide projection doesn't trip DuckDB's filter_pushdown ColumnBindingResolver (it pushes
# the boolean predicate into the parquet scan → mis-binds is_current as UBIGINT → `INTERNAL Error:
# Failed to bind column reference "IS_CURRENT": inequal types (UBIGINT != BOOLEAN)`, even though the
# parquet is_current IS BOOLEAN — verified, no data issue). A physical table has no parquet scan → no
# pushdown-into-scan → no bug. feature_pregame_lineup_state (the INC-17-P2 SCD-2 source read by
# lineup_features + the 3 matchup models with exactly that pattern) is the only one that hits it.
W8B_MATERIALIZE_TABLES = ["feature_pregame_lineup_state"]


def _contact_quality_columns() -> list[str]:
    """The canonical contact-quality column list — PARSED from the dbt macro
    (dbt/macros/season_normalize_contact.sql `contact_quality_columns()` return list) so the
    DuckDB build of feature_league_contact_baseline / feature_pregame_game_features can never drift
    from the Snowflake macro's list (the macro's whole point — a single source of truth)."""
    macro = REPO_ROOT / "dbt" / "macros" / "season_normalize_contact.sql"
    text = macro.read_text()
    m = re.search(r"macro\s+contact_quality_columns\(\).*?return\(\[(.*?)\]\)", text, re.DOTALL)
    if not m:
        raise RuntimeError("could not parse contact_quality_columns() from season_normalize_contact.sql")
    cols = re.findall(r"'([a-z0-9_]+)'", m.group(1))
    if len(cols) < 30:
        raise RuntimeError(f"contact_quality_columns() parse looks wrong ({len(cols)} cols)")
    return cols


def _contact_baseline_sql(upstream: str) -> str:
    """Python PORT of the as_of_contact_baseline() dbt macro (dbt/macros/season_normalize_contact.sql).
    Emits the strictly-prior AS-OF league mean/std per contact column, shrunk toward the prior season
    with pseudo-count K (var contact_baseline_shrinkage_k default 200). Byte-for-byte the macro's SQL —
    every expression mirrors the macro so the DuckDB build matches the Snowflake build (parity)."""
    cc = _contact_quality_columns()
    K = 200  # var('contact_baseline_shrinkage_k', 200)
    wf = "over (partition by game_year order by game_date rows between unbounded preceding and 1 preceding)"
    daily = ",\n        ".join(
        f"count({c}) as n__{c}, sum({c}) as s__{c}, sum({c} * {c}) as ss__{c}" for c in cc)
    asof = ",\n        ".join(
        f"sum(n__{c}) {wf} as cn__{c}, sum(s__{c}) {wf} as cs__{c}, sum(ss__{c}) {wf} as css__{c}" for c in cc)
    season = ",\n        ".join(
        f"avg({c}) as fmu__{c}, coalesce(stddev_samp({c}), 0) as fsd__{c}" for c in cc)
    prior = ",\n        ".join(f"fmu__{c} as pmu__{c}, fsd__{c} as psd__{c}" for c in cc)
    least = ", ".join(f"coalesce(a.cn__{c}, 0)" for c in cc)
    finals = ",\n        ".join(
        f"(coalesce(a.cn__{c}, 0) * (a.cs__{c} / nullif(a.cn__{c}, 0)) "
        f"+ {K} * coalesce(pr.pmu__{c}, sf.fmu__{c})) / (coalesce(a.cn__{c}, 0) + {K}) as {c}__mu,\n"
        f"        (coalesce(a.cn__{c}, 0) * sqrt(greatest("
        f"a.css__{c} / nullif(a.cn__{c}, 0) - power(a.cs__{c} / nullif(a.cn__{c}, 0), 2), 0)) "
        f"+ {K} * coalesce(pr.psd__{c}, sf.fsd__{c})) / (coalesce(a.cn__{c}, 0) + {K}) as {c}__sd"
        for c in cc)
    return (
        f"with daily as (\n"
        f"    select game_year, game_date,\n        {daily}\n"
        f"    from {upstream}\n    group by game_year, game_date\n),\n"
        f"asof_cum as (\n"
        f"    select game_year, game_date,\n        {asof}\n    from daily\n),\n"
        f"season_full as (\n"
        f"    select game_year,\n        {season}\n    from {upstream}\n    group by game_year\n),\n"
        f"prior as (\n"
        f"    select game_year + 1 as game_year,\n        {prior}\n    from season_full\n)\n"
        f"select\n    a.game_year,\n    a.game_date,\n    least({least}) as n_asof_min,\n        {finals}\n"
        f"from asof_cum a\n"
        f"left join prior       pr on pr.game_year = a.game_year\n"
        f"left join season_full sf on sf.game_year = a.game_year\n"
    )


def _game_features_wrapper_sql() -> str:
    """Python PORT of feature_pregame_game_features (the public wrapper): raw.* + a season-normalized
    `<col>_seasonnorm` per contact column (cast ::double — the INC-19 pin). Mirrors the dbt for-loop."""
    cc = _contact_quality_columns()
    sn = ",\n    ".join(
        f"coalesce((raw.{c} - b.{c}__mu) / nullif(b.{c}__sd, 0), 0)::double as {c}_seasonnorm"
        for c in cc)
    return (
        f"select\n    raw.*,\n    {sn}\n"
        f"from feature_pregame_game_features_raw raw\n"
        f"left join feature_league_contact_baseline b\n"
        f"    on  b.game_year = raw.game_year\n    and b.game_date = raw.game_date\n"
    )


def _build_one_sql(conn, name: str, sql: str, dry_run: bool) -> None:
    """Build a model from EXPLICIT SQL (the macro models extract_duckdb_sql can't render) → S3 parquet,
    then register it as a DuckDB view. Applies the same TIMESTAMP→ISO-VARCHAR pin + newline-safe COPY
    as _build_marts (the wrapper carries odds_ingestion_ts via raw.* → must be stringified)."""
    loc = f"{LAKEHOUSE}/{name}/data.parquet"
    body = _string_timestamp_wrap(conn, sql)
    if dry_run:
        n = conn.execute(f"SELECT count(*) FROM (\n{body}\n) t").fetchone()[0]
        print(f"  {name}: {n:,} rows  (dry-run — no S3 write)")
        conn.execute(f"CREATE OR REPLACE VIEW {name} AS {sql}")
    else:
        conn.execute(f"COPY (\n{body}\n) TO '{loc}' (FORMAT PARQUET)")
        print(f"  {name}: written → {loc}")
        conn.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{loc}')")


def _build_w8b(conn, dry_run: bool) -> None:
    """Build the E11.1-W8b serving-aggregator wave. Registers the prior-wave feature layer + marts +
    the W8b/W7b-1 mirrors as DuckDB views first, then builds the dialect-clean feature/matchup models
    and the aggregator in dependency order (each registered as a view immediately after build), then
    builds the 2 macro models (league_contact_baseline → public wrapper) via the Python ports. A
    missing precursor makes a build raise; W8b is gated (opt-in) so the daily HALT op never trips on
    it pre-cutover."""
    print("\nW8b precursor views (prior-wave feature layer + marts + W8b/W7b-1 mirrors):")
    # Register every precursor as a view EXCEPT the INC-23 materialize-tables (CREATE OR REPLACE TABLE
    # can't replace an existing VIEW of the same name, so never register those as views first).
    _register_w8a_views(conn, [v for v in W8B_PRECURSOR_VIEWS if v not in W8B_MATERIALIZE_TABLES])

    # 🧨 DuckDB filter_pushdown is_current binder bug (W8b first-build HALT 2026-06-30; DISTINCT from
    # the INC-23 year-VARCHAR incident): the lineup_features + 3 matchup models read
    # feature_pregame_lineup_state with `where is_current = true` + `qualify row_number() over (…)` +
    # a wide projection. Through a parquet-scan VIEW, DuckDB pushes the is_current predicate into the
    # scan and ColumnBindingResolver mis-binds it → `INTERNAL Error: Failed to bind column reference
    # "IS_CURRENT": inequal types (UBIGINT != BOOLEAN)` (the parquet is_current IS BOOLEAN — no data
    # issue; verified). Data-side cures (projection barrier / ::boolean cast in the view) do NOT
    # survive the full models; disabling filter_pushdown globally would slow/OOM the wide aggregator.
    # CURE: MATERIALIZE these into physical DuckDB tables (no parquet scan → no pushdown-into-scan →
    # no bug). Tiny (~2.4k rows) → negligible. Overrides the views registered just above.
    for _t in W8B_MATERIALIZE_TABLES:
        glob = f"{LAKEHOUSE}/{_t}/**/*.parquet"
        conn.execute(
            f"CREATE OR REPLACE TABLE {_t} AS "
            f"SELECT * FROM read_parquet('{glob}', union_by_name=true)"
        )
        print(f"  materialized table (INC-23 filter_pushdown cure): {_t}")

    # The aggregator + lineup_features are very wide (700+ cols / 9-slot unpivots); cap parallelism +
    # box-aware memory_limit so DuckDB spills to temp_directory rather than OOMing. value-identical
    # output (every output is a parquet COPY re-globbed downstream).
    for _pragma in ("SET threads=2", f"SET memory_limit='{_safe_memory_limit_gb()}GB'"):
        try:
            conn.execute(_pragma)
        except Exception as _e:
            print(f"  (note: {_pragma} not applied: {_e})")

    print("\nW8b feature/matchup models + aggregator (dependency-ordered):")
    for model in W8B_FEATURE_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)

    print("\nW8b macro models (Python-ported from the dbt macros — league baseline, then public wrapper):")
    _build_one_sql(conn, "feature_league_contact_baseline",
                   _contact_baseline_sql("feature_pregame_game_features_raw"), dry_run)
    _build_one_sql(conn, "feature_pregame_game_features", _game_features_wrapper_sql(), dry_run)


# E11.1-W11 Tier-B: the shared UMPIRE feed's stg + feature layer. The 4 umpire writers dual-write
# one raw source (lakehouse_raw/umpire_game_log/); these 4 models read it via read_parquet in their
# duckdb branch (self-contained — the ONLY precursor is the raw parquet, no prior-wave view needed).
# OPT-IN (--w11b) until cutover, like the prior waves. Dependency order: the 2 stg models read the
# raw directly; feature_features reads stg_umpire_game_log, feature_status reads stg_umpire_snapshots.
# feature_pregame_umpire_features is the W8a-deferred straggler the W8b aggregator reads — once its
# native parquet lands at lakehouse/feature_pregame_umpire_features/, the W8b precursor VIEW reads it
# directly (replacing the W7b-1 export_features_to_s3.py mirror at the SAME S3 path → no W8b edit).
W11B_STG_MODELS = ["stg_statsapi_umpire_game_log", "stg_statsapi_umpire_snapshots"]
W11B_FEATURE_MODELS = ["feature_pregame_umpire_features", "feature_pregame_umpire_status"]
W11B_MODELS = W11B_STG_MODELS + W11B_FEATURE_MODELS


def _build_w11b(conn, dry_run: bool) -> None:
    """Build the E11.1-W11 Tier-B umpire stg + feature layer from the umpire_game_log raw mirror.
    Self-contained: each stg model reads lakehouse_raw/umpire_game_log/ directly, so no prior-wave
    precursor view is needed. Builds the 2 stg models, registers each as a view, then builds the 2
    feature models (which read the stg views) and registers them. A missing raw parquet makes a
    build raise; W11b is gated (opt-in) so the daily HALT op never trips on it pre-cutover."""
    # Cap parallelism + box-aware memory_limit (consistent with the other waves; the umpire raw is
    # tiny so this is precautionary, not load-bearing).
    for _pragma in ("SET threads=2", f"SET memory_limit='{_safe_memory_limit_gb()}GB'"):
        try:
            conn.execute(_pragma)
        except Exception as _e:
            print(f"  (note: {_pragma} not applied: {_e})")

    print("\nW11b umpire staging (read lakehouse_raw/umpire_game_log/ directly):")
    for model in W11B_STG_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)

    print("\nW11b umpire feature layer (dependency-ordered; read the stg views just built):")
    for model in W11B_FEATURE_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)


# E11.22: player_transactions read-cutover. player_transactions was the ONE W7b-precursor whose stg
# model's Snowflake (else) branch still read {{ source('statsapi','player_transactions') }} directly
# (not lakehouse_ext), so its SF raw could not be dropped with the A/B/C/D batch. Build
# stg_statsapi_transactions to lakehouse/<model>/data.parquet (self-contained: it reads the
# lakehouse_raw/player_transactions/ mirror directly + dedups by transaction_id), so a lakehouse_ext
# external table over it lets the else branch read S3, exactly like the umpire/fangraphs stg models.
W11TX_MODELS = ["stg_statsapi_transactions"]


def _build_w11tx(conn, dry_run: bool) -> None:
    """Build the E11.22 player_transactions stg model from the player_transactions raw mirror.
    Self-contained (reads lakehouse_raw/player_transactions/ directly), mirroring _build_w11b. A missing
    raw parquet makes the build raise; --w11tx is gated (opt-in) so the daily HALT op never trips on it
    pre-cutover."""
    for _pragma in ("SET threads=2", f"SET memory_limit='{_safe_memory_limit_gb()}GB'"):
        try:
            conn.execute(_pragma)
        except Exception as _e:
            print(f"  (note: {_pragma} not applied: {_e})")

    print("\nW11tx transactions staging (read lakehouse_raw/player_transactions/ directly):")
    for model in W11TX_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)


# E11.1-W11 Tier-D: the ActionNetwork PUBLIC-BETTING stg + feature layer. The writer dual-writes one
# raw source (lakehouse_raw/public_betting_raw/); these 4 models read it. Unlike W11b (umpire), this
# chain is NOT self-contained — stg_actionnetwork_public_betting_snapshots joins the pregame spine
# feature_pregame_game_features (a W8b output) for game_pk resolution, so _build_w11d registers that as
# a precursor VIEW first and MUST run AFTER --w8b (its parquet must exist). Dependency order: the plain
# stg feeds the W8b aggregator (a 1-cycle propagation lag on its contribution is acceptable — public
# betting is a slow-moving, non-serving-critical feature); the snapshots stg + SCD-2 chain feed the
# W8a-deferred straggler feature_pregame_public_betting_features (read by the W8b aggregator tail +
# export_features_to_s3.py mirror at the same S3 key → this native build replaces that mirror).
W11D_STG_MODELS = ["stg_actionnetwork_public_betting", "stg_actionnetwork_public_betting_snapshots"]
W11D_FEATURE_MODELS = ["feature_pregame_public_betting_status", "feature_pregame_public_betting_features"]
W11D_MODELS = W11D_STG_MODELS + W11D_FEATURE_MODELS
# The pregame-spine precursor the snapshots stg joins for game_pk resolution (built by --w8b).
W11D_PRECURSOR_VIEWS = ["feature_pregame_game_features"]


def _build_w11d(conn, dry_run: bool) -> None:
    """Build the E11.1-W11 Tier-D public-betting stg + feature layer from the public_betting_raw mirror.
    NOT self-contained: stg_actionnetwork_public_betting_snapshots joins feature_pregame_game_features
    (registered here as a DuckDB view over its W8b native parquet), so this runs AFTER --w8b. Builds the
    2 stg models (plain → snapshots), registers each as a view, then builds the 2 feature models (SCD-2
    status → current-state features) and registers them. A missing raw parquet or the missing spine
    parquet makes a build raise; W11d is gated (opt-in) so the daily HALT op never trips on it
    pre-cutover."""
    for _pragma in ("SET threads=2", f"SET memory_limit='{_safe_memory_limit_gb()}GB'"):
        try:
            conn.execute(_pragma)
        except Exception as _e:
            print(f"  (note: {_pragma} not applied: {_e})")

    print("\nW11d public-betting precursor (register the pregame spine as a DuckDB view):")
    _register_s3_glob_views(conn, W11D_PRECURSOR_VIEWS)

    print("\nW11d public-betting staging (read lakehouse_raw/public_betting_raw/ + the spine view):")
    for model in W11D_STG_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)

    print("\nW11d public-betting feature layer (SCD-2 status → current-state features):")
    for model in W11D_FEATURE_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)


# E11.1-W11 Tier-C: the shared WEATHER feed's stg + feature layer. Both weather writers
# (ingest_weather / backfill_observed_weather) dual-write one raw source (lakehouse_raw/weather_raw/);
# these 4 models read it via read_parquet in their duckdb branch. The 2 feature models are the
# W8a-deferred stragglers (feature_pregame_weather_features feeds the W8b aggregator + the game-features
# incremental). Dependency: the 2 stg read the raw directly; feature_status reads stg_weather_raw_snapshots;
# feature_features reads feature_status + the raw (observed) + the ref_venues seed. OPT-IN (--w11c).
W11C_STG_MODELS = ["stg_weather_raw", "stg_weather_raw_snapshots"]
W11C_FEATURE_MODELS = ["feature_pregame_weather_status", "feature_pregame_weather_features"]
W11C_MODELS = W11C_STG_MODELS + W11C_FEATURE_MODELS

SEEDS_DIR = REPO_ROOT / "dbt" / "seeds"


def _register_seed_csv(conn, name: str) -> None:
    """Register a dbt seed CSV as a DuckDB view so a duckdb-branch model can join it by bare name.

    ref_venues (venue_id, venue_name, roof_type, park_facing_degrees) is a tiny static seed that is
    NOT exported to the S3 lakehouse (unlike ref_teams/ref_team_aliases); the CSV ships in the repo, so
    read it directly. read_csv_auto infers the (int, varchar, varchar, int) types correctly."""
    csv_path = SEEDS_DIR / f"{name}.csv"
    conn.execute(
        f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_csv_auto('{csv_path}', header=true)"
    )
    print(f"  registered seed view: {name}  ({csv_path})")


def _build_w11c(conn, dry_run: bool) -> None:
    """Build the E11.1-W11 Tier-C weather stg + feature layer from the weather_raw raw mirror.
    Registers the ref_venues seed view first (the snapshots + observed feature paths join it), then
    builds the 2 stg models (read lakehouse_raw/weather_raw/ directly) and registers them, then the 2
    feature models in dependency order (feature_status reads stg_weather_raw_snapshots; feature_features
    reads feature_status + the raw + ref_venues). A missing raw parquet makes a build raise; W11c is
    gated (opt-in) so the daily HALT op never trips on it pre-cutover."""
    for _pragma in ("SET threads=2", f"SET memory_limit='{_safe_memory_limit_gb()}GB'"):
        try:
            conn.execute(_pragma)
        except Exception as _e:
            print(f"  (note: {_pragma} not applied: {_e})")

    print("\nW11c precursor: ref_venues seed view")
    _register_seed_csv(conn, "ref_venues")

    print("\nW11c weather staging (read lakehouse_raw/weather_raw/ directly):")
    for model in W11C_STG_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)

    print("\nW11c weather feature layer (dependency-ordered; read the stg views just built):")
    for model in W11C_FEATURE_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)


def run(
    dry_run: bool = False,
    skip_w1: bool = False,
    w1_only: bool = False,
    w3pre: bool = False,
    w3pre_only: bool = False,
    w3_only: bool = False,
    w4: bool = False,
    w4_only: bool = False,
    w5: bool = False,
    w5_only: bool = False,
    w5_group_a_only: bool = False,
    w5b_only: bool = False,
    archetype: bool = False,
    archetype_only: bool = False,
    w6: bool = False,
    w6_only: bool = False,
    w6_odds_current: bool = False,
    w7b: bool = False,
    w7b_only: bool = False,
    w8a: bool = False,
    w8a_only: bool = False,
    sub_model_signals_only: bool = False,
    w8b: bool = False,
    w8b_only: bool = False,
    w11b: bool = False,
    w11b_only: bool = False,
    w11c: bool = False,
    w11c_only: bool = False,
    w11d: bool = False,
    w11d_only: bool = False,
    w11tx: bool = False,
    w11tx_only: bool = False,
) -> None:
    import duckdb

    conn = duckdb.connect()

    # E11.1-W3pre: enable larger-than-memory operators. The stg_statsapi_games flatten explodes
    # monthly_schedule's ~1,700 month-blobs (one row per snapshot of a month) into a multi-hundred-
    # thousand / million-row intermediate BEFORE the `qualify row_number() over (partition by
    # game_pk ...)` dedup collapses it to ~26k game_pks. An IN-MEMORY DuckDB does NOT spill to disk
    # unless temp_directory is set, so that window OOMs (observed 14.3/14.3 GiB) instead of spilling.
    # Set a spill dir + drop insertion-order preservation: every output here is a parquet COPY that
    # is re-globbed downstream (row order is irrelevant; the parity hash sorts explicitly), so this
    # is purely a memory fix — value-identical output. temp_directory under the system temp is
    # writable on both the operator box and the self-hosted Dagster EC2 host. Harmless for W1/W2.
    _spill_dir = os.path.join(tempfile.gettempdir(), "duckdb_lakehouse_spill")
    os.makedirs(_spill_dir, exist_ok=True)
    conn.execute("SET preserve_insertion_order=false")
    conn.execute(f"SET temp_directory='{_spill_dir}'")
    # E11.1-W6: pin the session timezone to UTC so any implicit naive↔tz cast is
    # deterministic + UTC-consistent. The odds/CLV marts union a TIMESTAMP_NTZ (UTC
    # wall-clock) live arm into a TIMESTAMP_TZ column (mart_closing_line_value.
    # close_snapshot_ts) and compare snapshot_ts (timestamptz) to a TIMESTAMP_NTZ
    # ingestion_ts — UTC pinning keeps those casts reproducible across hosts. Harmless
    # for W1–W5 (their marts use only explicit ::date/::timestamp, no implicit tz casts).
    try:
        conn.execute("SET TimeZone='UTC'")
    except Exception as _e:
        print(f"  (note: SET TimeZone='UTC' not applied: {_e})")

    conn.execute("INSTALL httpfs; LOAD httpfs")
    # E11.1-W6: the odds/CLV marts use timezone conversion (mart_odds_outcomes /
    # mart_odds_events commence_date, mart_closing_line_value / mart_bookmaker_disagreement
    # ET-window guards). Snowflake's convert_timezone(src, tgt, ts) is reimplemented in the
    # duckdb branch with `ts AT TIME ZONE 'UTC' AT TIME ZONE '<tgt>'`, which needs the ICU
    # extension. Load it here (harmless for W1–W5). Autoload usually covers AT TIME ZONE, but
    # load explicitly so a host with autoload disabled still resolves the zone names.
    try:
        conn.execute("INSTALL icu; LOAD icu")
    except Exception as _e:
        print(f"  (note: ICU extension not loaded: {_e}; AT TIME ZONE may rely on autoload)")
    conn.execute("""
        CREATE OR REPLACE SECRET baseball_s3 (
          TYPE S3,
          PROVIDER credential_chain,
          REGION 'us-east-2'
        )
    """)
    # E11.1-W4: harden S3 reads against transient httpfs timeouts. The FanGraphs / raw
    # precursor parquets are read over httpfs and a slow GET was tripping the default 30s
    # per-request window (`Timeout was reached error for HTTP GET ...`). Raise the timeout
    # and add retries with backoff so a transient slow response is retried, not fatal.
    for _pragma in (
        # Hang-budget cap: timeout × retries bounds how long a stalled GET can park. Was
        # 600000ms × 8 = ~80 min of silent parking (the recurring "--w6 ran 50 min, no output"
        # stall). Keep a generous 5-min per-request window for a genuinely slow FanGraphs GET,
        # but 4 retries → ≤~20 min worst case, safely under the op's 2700s wall-clock cap.
        "SET http_timeout = 300000",      # 5 min per request (default 30_000 ms)
        "SET http_retries = 4",           # default 3
        "SET http_retry_wait_ms = 500",
        "SET http_retry_backoff = 4",
    ):
        try:
            conn.execute(_pragma)
        except Exception as _e:  # older httpfs builds may not expose every knob — non-fatal
            print(f"  (note: {_pragma} not applied: {_e})")

    # E11.1-W3pre: --w3pre-only flattens the odds/staging tier from lakehouse_raw/ without
    # touching the pitch marts (lets the operator iterate on W3pre after a raw export).
    if w3pre_only:
        _build_w3pre(conn, dry_run)
        conn.close()
        print("\nW3pre staging run complete (--w3pre-only).")
        return

    # E11.1-W6 INTRADAY: --w6-odds-current rewrites ONLY mart_odds_outcomes' _current bucket
    # (today + future games, recent-scoped flatten) + mart_game_odds_bridge, reusing the
    # existing W3pre/W5 parquet. Standalone (no pitch-mart build) so the odds_current_rebuild
    # path stays light. The caller exports today's mlb_odds_raw → S3 first, then refreshes the
    # mart_odds_outcomes / mart_game_odds_bridge / stg_oddsapi_odds external tables.
    if w6_odds_current:
        print("\nBuilding W6 INTRADAY current-odds pass (--w6-odds-current):")
        _build_w6_odds_current(conn, dry_run)
        conn.close()
        print("\nW6 intraday current-odds run complete (--w6-odds-current).")
        return

    # INC-25: --sub-model-signals-only rebuilds JUST the feature_pregame_sub_model_signals consumer
    # parquet from the freshly-exported W9 store parquets. Placed HERE (before the heavy
    # stg_batter_pitches scan) because the consumer pivot reads only the 5 signal-store parquets — it
    # is standalone + fast. The daily job runs this AFTER export_w9_signals_to_s3 (so the consumer
    # isn't a slate stale — the full --w8a build at job START read yesterday's stores). See
    # _build_sub_model_signals_consumer for the full rationale.
    if sub_model_signals_only:
        _build_sub_model_signals_consumer(conn, dry_run)
        conn.close()
        print("\nfeature_pregame_sub_model_signals consumer rebuild complete (--sub-model-signals-only).")
        return

    # Register stg_batter_pitches as a view so mart refs resolve.
    stg_sql = extract_duckdb_sql("stg_batter_pitches")
    conn.execute(f"CREATE OR REPLACE VIEW stg_batter_pitches AS {stg_sql}")
    n = conn.execute("SELECT count(*) FROM stg_batter_pitches").fetchone()[0]
    print(f"stg_batter_pitches: {n:,} pitches loaded from S3")

    # mart_pitch_hitter_profile and mart_pitch_pitcher_profile left-join the player-name
    # dimension. As of the ref_players S3 export (scripts/export_ref_players_to_s3.py),
    # stg_ref_players reads real names from S3 — register it as a view (same Layout-A
    # extraction as stg_batter_pitches) so the marts' `from stg_ref_players` resolves.
    stg_ref_sql = extract_duckdb_sql("stg_ref_players")
    conn.execute(f"CREATE OR REPLACE VIEW stg_ref_players AS {stg_ref_sql}")
    n_ref = conn.execute("SELECT count(*) FROM stg_ref_players").fetchone()[0]
    print(f"stg_ref_players: {n_ref:,} players loaded from S3")

    # E11.1-W3: --w3-only rebuilds just the W3 marts, reusing the existing W1+W2
    # parquet (registered as views from S3). Lets the operator iterate on W3 / re-run
    # parity without rebuilding the heavy pitch marts.
    if w3_only:
        print("\nRegistering W1 + W2 marts as views (reuse existing parquet for --w3-only):")
        _register_mart_views(conn, MART_MODELS, dry_run)
        _register_mart_views(conn, W2_MART_MODELS, dry_run)
        _build_w3(conn, dry_run)
        conn.close()
        print("\nW3 marts run complete (--w3-only).")
        return

    # E11.1-W4: --w4-only rebuilds just the W4 marts + their FanGraphs precursor
    # subtree, reusing the existing W1 parquet (the only prior-wave marts W4 reads are
    # the W1 mart_pitch_characteristics / mart_pitch_play_event). Lets the operator
    # iterate on W4 / re-run parity after an export or a builder run, without
    # rebuilding the heavy pitch marts.
    if w4_only:
        print("\nRegistering W1 marts as views (reuse existing parquet for --w4-only):")
        _register_mart_views(conn, MART_MODELS, dry_run)
        _build_w4(conn, dry_run)
        conn.close()
        print("\nW4 marts run complete (--w4-only).")
        return

    # E11.1-W5: --w5-only rebuilds just the W5 marts (the game-results team/game chain
    # + the 4 W4-deferred marts), reusing the existing W1/W2/W3pre parquet (registered
    # as views by _build_w5). stg_batter_pitches is already registered above. Lets the
    # operator iterate on W5 / re-run parity after an export, without rebuilding the
    # heavy pitch marts. --w5-group-a-only stops after the 10-mart Group A chain.
    if w5_only:
        print("\nBuilding W5 (reuse existing W1/W2/W3pre parquet for --w5-only):")
        _build_w5(conn, dry_run, group_b=not w5_group_a_only)
        conn.close()
        print("\nW5 marts run complete (--w5-only).")
        return

    # E11.1-W5b: --w5b-only rebuilds JUST the W5 Group-B marts (park/defense/bullpen-effectiveness),
    # reusing the existing Group-A/W2 parquet. The daily job runs this BETWEEN --w8a (whose
    # eb_bullpen_team_posteriors parquet W5b reads) and --w8b (whose aggregator reads W5b). See
    # _build_w5b for the full rationale.
    if w5b_only:
        print("\nBuilding W5b Group-B marts (reuse existing Group-A/W2 parquet for --w5b-only):")
        _build_w5b(conn, dry_run)
        conn.close()
        print("\nW5b Group-B marts run complete (--w5b-only).")
        return

    # E11.1-W5b: --archetype-only rebuilds just the archetype mart, reusing the existing W1
    # mart_pitch_play_event parquet + the mart_player_archetype_posteriors parquet (built by
    # compute_archetype_posteriors.py --s3/--seed). stg_batter_pitches is already registered
    # above (the archetype mart doesn't read it, but run() registers it unconditionally).
    if archetype_only:
        print("\nBuilding W5b archetype mart (reuse existing parquet for --archetype-only):")
        _build_archetype(conn, dry_run)
        conn.close()
        print("\nW5b archetype mart run complete (--archetype-only).")
        return

    # E11.1-W6: --w6-only rebuilds just the W6 odds/CLV + odds-serving marts + the 2
    # Group-C staging flattens, reusing the existing W3pre/W5 parquet (registered as views
    # by _build_w6) + the precursor exports. stg_batter_pitches is already registered above
    # (W6 doesn't read it). Lets the operator iterate on W6 / re-run parity after an export,
    # without rebuilding the heavy pitch marts.
    if w6_only:
        print("\nBuilding W6 (reuse existing W3pre/W5 parquet for --w6-only):")
        _build_w6(conn, dry_run)
        conn.close()
        print("\nW6 marts run complete (--w6-only).")
        return

    # E11.1-W7b: --w7b-only rebuilds just the prediction/serving mini-wave (the
    # mart_player_profile_identity injury chain + the probable_pitchers/lineups_wide serving-mart
    # backlog), reusing the existing W2/W4/W6 parquet (registered as precursor views by _build_w7b)
    # + the player_transactions precursor export + the monthly_schedule raw tier. Lets the operator
    # iterate on W7b / re-run parity after an export, without rebuilding the heavy pitch marts.
    if w7b_only:
        print("\nBuilding W7b (reuse existing W2/W4/W6 parquet for --w7b-only):")
        _build_w7b(conn, dry_run)
        conn.close()
        print("\nW7b mini-wave run complete (--w7b-only).")
        return

    # E11.1-W8a: --w8a-only rebuilds just the upstream feature layer + EB posteriors, reusing the
    # existing prior-wave parquet (registered as precursor views by _build_w8a) + the W9 signal
    # stores + the W8a Python-table/seed mirrors. stg_batter_pitches is already registered above.
    # Lets the operator iterate on W8a / re-run parity after an export, without rebuilding the
    # heavy pitch marts.
    if w8a_only:
        print("\nBuilding W8a (reuse existing prior-wave/W9/mirror parquet for --w8a-only):")
        _build_w8a(conn, dry_run)
        conn.close()
        print("\nW8a upstream feature layer + EB posteriors run complete (--w8a-only).")
        return

    # E11.1-W8b: --w8b-only rebuilds just the serving-aggregator wave (complex upstream feature
    # models + 3 matchup models + the aggregator + its wrapper + the contact baseline), reusing the
    # existing prior-wave/W8a/W7b-1 parquet (registered as precursor views by _build_w8b) + the W8b
    # precursor mirrors (export_w8b_precursors_to_s3.py). stg_batter_pitches is already registered
    # above (W8b doesn't read it directly). Lets the operator iterate on W8b / re-run parity after an
    # export, without rebuilding the heavy pitch marts. ⚠️ W8a must already be in S3 (the aggregator
    # reads the W8a feature layer); run --w8a-only first in a clean rebuild.
    if w8b_only:
        print("\nBuilding W8b (reuse existing prior-wave/W8a/W7b-1/mirror parquet for --w8b-only):")
        _build_w8b(conn, dry_run)
        conn.close()
        print("\nW8b serving-aggregator wave run complete (--w8b-only).")
        return

    # E11.1-W11 Tier-B: --w11b-only rebuilds just the umpire stg + feature layer from the
    # umpire_game_log raw mirror. Self-contained (no prior-wave parquet needed), so it runs
    # standalone — ideal for the box RUNTIME GATE (rebuild umpire only, then per-ROW ext-validate).
    if w11b_only:
        print("\nBuilding W11b umpire stg + feature layer (--w11b-only):")
        _build_w11b(conn, dry_run)
        conn.close()
        print("\nW11b umpire wave run complete (--w11b-only).")
        return
    # E11.22: --w11tx-only rebuilds just the player_transactions stg from its raw mirror. Self-contained
    # (like --w11b-only) → ideal for the box RUNTIME GATE (rebuild transactions only, then per-ROW ext-validate).
    if w11tx_only:
        print("\nBuilding W11tx transactions staging (--w11tx-only):")
        _build_w11tx(conn, dry_run)
        conn.close()
        print("\nW11tx transactions wave run complete (--w11tx-only).")
        return

    # E11.1-W11 Tier-C: --w11c-only rebuilds just the weather stg + feature layer from the weather_raw
    # raw mirror (+ the ref_venues seed CSV). Self-contained (no prior-wave parquet needed), so it runs
    # standalone — ideal for the box RUNTIME GATE (rebuild weather only, then per-ROW ext-validate).
    if w11c_only:
        print("\nBuilding W11c weather stg + feature layer (--w11c-only):")
        _build_w11c(conn, dry_run)
        conn.close()
        print("\nW11c weather wave run complete (--w11c-only).")
        return

    # E11.1-W11 Tier-D: --w11d-only rebuilds just the public-betting stg + feature layer from the
    # public_betting_raw mirror. NOT fully self-contained — it registers feature_pregame_game_features
    # (the pregame spine the snapshots stg joins) as a view over its EXISTING W8b parquet, so a prior
    # --w8b build must have written that parquet to S3. Ideal for the box RUNTIME GATE (rebuild
    # public-betting only, then per-ROW ext-validate) once the spine parquet is present.
    if w11d_only:
        print("\nBuilding W11d public-betting stg + feature layer (--w11d-only):")
        _build_w11d(conn, dry_run)
        conn.close()
        print("\nW11d public-betting wave run complete (--w11d-only).")
        return

    # ── W1: pitch-level marts ────────────────────────────────────────────────
    if not skip_w1:
        print("\nW1 marts:")
        _build_marts(conn, MART_MODELS, dry_run)

    if w1_only:
        conn.close()
        print("\nW1 lakehouse run complete (--w1-only; W2 skipped).")
        return

    # ── W2: pitch-derived batch marts (E11.1-W2) ─────────────────────────────
    # Register the W1 marts as views first so W2 models that read mart_pitch_*
    # resolve. With --skip-w1 the parquet from a prior run is reused (lets the
    # operator iterate on W2 without rebuilding the heavy pitch marts).
    print("\nRegistering W1 marts as views (for W2 dependencies):")
    _register_mart_views(conn, MART_MODELS, dry_run)

    print("\nW2 marts:")
    _build_marts(conn, W2_MART_MODELS, dry_run)

    # ── W3: remaining pitch-derived batch marts (E11.1-W3) ───────────────────
    # Register the W2 marts as views first so the W3 bullpen marts' reads of
    # mart_starting_pitcher_game_log resolve (the W1 marts are already registered
    # above). W3 is NOT opt-in (unlike W3pre): its whole upstream is already in S3,
    # so it builds on the default daily path right after W2.
    print("\nRegistering W2 marts as views (for W3 dependencies):")
    _register_mart_views(conn, W2_MART_MODELS, dry_run)
    _build_w3(conn, dry_run)

    # ── W3pre: odds/staging flatten tier (E11.1-W3pre) — OPT-IN ──────────────
    # NOT built by default: the daily run_w1_lakehouse_op calls this with no args, and
    # the W3pre stg models need the lakehouse_raw/ tier populated (export + flipped
    # writers) first. Enable with --w3pre once the raw export is wired and cutover is
    # validated, so an empty raw tier can't fail the HALT-tier daily op.
    if w3pre:
        _build_w3pre(conn, dry_run)

    # ── W4: FanGraphs / posteriors-cluster / raw-savant marts (E11.1-W4) — OPT-IN ──
    # NOT built by default (like W3pre): W4 reads RAW precursor parquet (export_w4_raw_to_s3.py)
    # and builder-output parquet (migrated fit_granular_park_priors.py + cluster_pitchers.py)
    # that must exist first. Enable with --w4 once the exports + builders are wired and cutover
    # is validated, so an empty precursor tier can't fail the HALT-tier daily op. The W1 marts
    # W4 reads are already registered as views above.
    if w4:
        _build_w4(conn, dry_run)

    # ── W5: seeds + mart_game_results/spine team chain + W4-deferred marts — OPT-IN ──
    # NOT built by default (like W3pre/W4): W5 reads the seed + W4-deferred raw parquet
    # (scripts/export_w5_raw_to_s3.py) that must exist first. Enable with --w5 once the
    # exports are wired and cutover is validated. --w5-group-a-only restricts to the
    # 10-mart Group A chain (skips the 4 W4-deferred Group B marts).
    if w5:
        _build_w5(conn, dry_run, group_b=not w5_group_a_only)

    # ── W5b: the archetype builder-mini-wave (tolerance class) — OPT-IN ──────────
    # NOT built by default: reads the mart_player_archetype_posteriors parquet (produced by
    # compute_archetype_posteriors.py --seed/--s3) that must exist first. Enable with
    # --archetype once the posteriors parquet is written + cutover is validated.
    if archetype:
        _build_archetype(conn, dry_run)

    # ── W6: odds/CLV + odds-serving path + Group-C marts (E11.1-W6) — OPT-IN ──────
    # NOT built by default: reads the precursor exports (odds_snapshots_historical,
    # daily_model_predictions, venues_raw via scripts/export_w6_raw_to_s3.py) + the W5 game
    # chain + W3pre staging that must exist first. Enable with --w6 once the exports are
    # wired and cutover is validated, so an empty precursor tier can't fail the HALT-tier
    # daily op. The W3pre/W5 marts W6 reads are registered as views inside _build_w6.
    if w6:
        _build_w6(conn, dry_run)

    # ── W7b: prediction/serving mini-wave (profile_identity chain + serving backlog) — OPT-IN ──
    # NOT built by default: reads the player_transactions precursor export
    # (scripts/export_w7b_precursors_to_s3.py) + the W2/W4/W6 marts + monthly_schedule raw that
    # must exist first. Enable with --w7b once the export is wired and parity is validated. The
    # daily run_w1_lakehouse_op appends --w7b only when the W7b mirror is on (W7B_LAKEHOUSE_S3=1
    # or W7B_LAKEHOUSE_PARALLEL=1), so an empty precursor tier can't fail the HALT-tier daily op.
    if w7b:
        _build_w7b(conn, dry_run)

    # ── W8a: upstream feature layer + EB posteriors (E11.1-W8a) — OPT-IN ──────────
    # NOT built by default: reads the W8a Python-table/seed mirrors
    # (scripts/export_w8a_precursors_to_s3.py) + the W9 signal stores + the prior-wave
    # marts that must exist first. Enable with --w8a once the exports are wired and parity
    # is validated. ⚠️ In a full rebuild --w8a must run BEFORE --w5 (the W5b mart
    # mart_bullpen_effectiveness reads the eb_bullpen_team_posteriors parquet W8a builds).
    if w8a:
        _build_w8a(conn, dry_run)

    # ── W8b: serving-aggregator wave (complex upstream + matchups + aggregator) — OPT-IN ──
    # NOT built by default: reads the W8b precursor mirrors (scripts/export_w8b_precursors_to_s3.py)
    # + the W8a feature layer + the W7b-1 feature mirror (umpire/weather tail) that must exist first.
    # Enable with --w8b once the exports are wired and parity is validated. ⚠️ --w8a (and --w7b for
    # the injury chain) must run BEFORE --w8b in a full rebuild — the aggregator reads the W8a feature
    # layer + injury_status.
    if w8b:
        _build_w8b(conn, dry_run)

    # ── W11b: umpire stg + feature layer — OPT-IN ──
    # Self-contained (reads only the umpire_game_log raw mirror), so it is independent of the other
    # waves' order. Enable with --w11b once the umpire writers dual-write and the ext tables exist.
    if w11b:
        _build_w11b(conn, dry_run)

    # ── W11tx: player_transactions stg — OPT-IN (E11.22) ──
    # Self-contained (reads only the player_transactions raw mirror). Enable with --w11tx once the
    # ext table exists + the model repoint merges. Standalone use is --w11tx-only.
    if w11tx:
        _build_w11tx(conn, dry_run)

    # ── W11c: weather stg + feature layer — OPT-IN ──
    # Self-contained (reads only the weather_raw raw mirror + the ref_venues seed). Enable with --w11c
    # once the weather writers dual-write + the ext tables exist. Standalone use is --w11c-only.
    if w11c:
        _build_w11c(conn, dry_run)

    # ── W11d: public-betting stg + feature layer — OPT-IN ──
    # Runs AFTER --w8b (the snapshots stg joins feature_pregame_game_features, built by W8b). Enable
    # with --w11d once the writer dual-writes + the ext tables exist. On the full path the spine parquet
    # was just written above; standalone use is --w11d-only (which also registers the spine view).
    if w11d:
        _build_w11d(conn, dry_run)

    conn.close()
    print(
        f"\nW1+W2+W3{'+W3pre' if w3pre else ''}{'+W4' if w4 else ''}"
        f"{'+W5' if w5 else ''}{'+W5b' if archetype else ''}{'+W6' if w6 else ''}"
        f"{'+W7b' if w7b else ''}{'+W8a' if w8a else ''}{'+W8b' if w8b else ''}"
        f"{'+W11b' if w11b else ''}{'+W11c' if w11c else ''}{'+W11d' if w11d else ''} "
        f"lakehouse run complete."
    )


if __name__ == "__main__":
    run(
        dry_run="--dry-run" in sys.argv,
        skip_w1="--skip-w1" in sys.argv,
        w1_only="--w1-only" in sys.argv,
        w3pre="--w3pre" in sys.argv,
        w3pre_only="--w3pre-only" in sys.argv,
        w3_only="--w3-only" in sys.argv,
        w4="--w4" in sys.argv,
        w4_only="--w4-only" in sys.argv,
        w5="--w5" in sys.argv,
        w5_only="--w5-only" in sys.argv,
        w5_group_a_only="--w5-group-a-only" in sys.argv,
        w5b_only="--w5b-only" in sys.argv,
        archetype="--archetype" in sys.argv,
        archetype_only="--archetype-only" in sys.argv,
        w6="--w6" in sys.argv,
        w6_only="--w6-only" in sys.argv,
        w6_odds_current="--w6-odds-current" in sys.argv,
        w7b="--w7b" in sys.argv,
        w7b_only="--w7b-only" in sys.argv,
        w8a="--w8a" in sys.argv,
        w8a_only="--w8a-only" in sys.argv,
        sub_model_signals_only="--sub-model-signals-only" in sys.argv,
        w8b="--w8b" in sys.argv,
        w8b_only="--w8b-only" in sys.argv,
        w11b="--w11b" in sys.argv,
        w11b_only="--w11b-only" in sys.argv,
        w11c="--w11c" in sys.argv,
        w11c_only="--w11c-only" in sys.argv,
        w11d="--w11d" in sys.argv,
        w11d_only="--w11d-only" in sys.argv,
        w11tx="--w11tx" in sys.argv,
        w11tx_only="--w11tx-only" in sys.argv,
    )
