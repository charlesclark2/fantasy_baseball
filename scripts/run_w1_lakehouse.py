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
#   catcher_framing_raw, fg_stuff_plus_raw, fg_zips_hitting_raw,
#   fg_hitting_leaderboard_raw, player_profiles_raw, eb_park_factors_granular_raw,
#   pitcher_clusters.
W4_PRECURSOR_MODELS = [
    "stg_fangraphs__stuff_plus",          # ← fg_stuff_plus_raw (parquet)
    "stg_fangraphs__pitcher_arsenal",     # ← fg_stuff_plus_raw (parquet)
    "stg_fangraphs__zips_hitting",        # ← fg_zips_hitting_raw (parquet)
    "stg_fangraphs__hitting_leaderboard", # ← fg_hitting_leaderboard_raw (parquet)
    "fct_fangraphs_pitcher_arsenal_wide", # ← stg_fangraphs__pitcher_arsenal + __stuff_plus
    "fct_fangraphs_hitting_analytics",    # ← stg_fangraphs__zips_hitting + __hitting_leaderboard
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

    # Guard: any surviving Jinja will cause a DuckDB parser error
    if re.search(r'\{[{%]', sql):
        sample = re.findall(r'\{[{%][^}]*?[%}]\}', sql)[:3]
        raise ValueError(f"Unresolved Jinja in {model_name}.sql: {sample}")

    return sql.strip()


def _build_marts(conn, models: list[str], dry_run: bool) -> None:
    """Extract each model's duckdb-branch SQL and COPY it to S3 parquet."""
    for model in models:
        loc = f"{LAKEHOUSE}/{model}/data.parquet"
        mart_sql = extract_duckdb_sql(model)
        if dry_run:
            n = conn.execute(f"SELECT count(*) FROM ({mart_sql}) t").fetchone()[0]
            print(f"  {model}: {n:,} rows  (dry-run — no S3 write)")
        else:
            conn.execute(f"COPY ({mart_sql}) TO '{loc}' (FORMAT PARQUET)")
            print(f"  {model}: written → {loc}")


def _register_mart_views(conn, models: list[str], dry_run: bool) -> None:
    """Register built marts as DuckDB views so downstream W2 marts (which read
    plain `mart_pitch_*` names in their duckdb branch) resolve.

    Real run: read the just-written S3 parquet (fast). Dry-run: the parquet may be
    absent/stale (dry-run skips the COPY), so recompute the view from the stg views.
    """
    for model in models:
        if dry_run:
            conn.execute(f"CREATE OR REPLACE VIEW {model} AS {extract_duckdb_sql(model)}")
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
    conn.execute("SET threads=2")
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
    for _pragma in ("SET threads=2", "SET memory_limit='11GB'"):
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

    if not group_b:
        return

    print("\nW5 Group B marts (W4-deferred) + stg_batter_sprint_speed precursor:")
    # mart_bullpen_effectiveness reads the W2 mart_starting_pitcher_game_log.
    _register_s3_glob_views(conn, ["mart_starting_pitcher_game_log"])
    for model in W5B_PRECURSOR_MODELS + W5B_MART_MODELS:
        _build_marts(conn, [model], dry_run)
        _register_mart_views(conn, [model], dry_run)


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
    archetype: bool = False,
    archetype_only: bool = False,
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

    conn.execute("INSTALL httpfs; LOAD httpfs")
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
        "SET http_timeout = 600000",      # 10 min per request (default 30_000 ms)
        "SET http_retries = 8",           # default 3
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

    conn.close()
    print(
        f"\nW1+W2+W3{'+W3pre' if w3pre else ''}{'+W4' if w4 else ''}"
        f"{'+W5' if w5 else ''}{'+W5b' if archetype else ''} lakehouse run complete."
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
        archetype="--archetype" in sys.argv,
        archetype_only="--archetype-only" in sys.argv,
    )
