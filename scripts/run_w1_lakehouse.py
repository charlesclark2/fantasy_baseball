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
  python3 scripts/run_w1_lakehouse.py             # default: W1 + W2  (writes to S3)
  python3 scripts/run_w1_lakehouse.py --dry-run   # row-count only, no S3 writes
  python3 scripts/run_w1_lakehouse.py --w1-only   # only the W1 pitch marts (skip W2)
  python3 scripts/run_w1_lakehouse.py --skip-w1   # only W2 (reuse existing W1 parquet)
  python3 scripts/run_w1_lakehouse.py --w3pre     # W1 + W2 + the W3pre odds/staging tier (opt-in)
  python3 scripts/run_w1_lakehouse.py --w3pre-only # only the W3pre odds/staging flatten tier

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

import re
import sys
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


def find_model(model_name: str) -> Path:
    for subdir in ("staging", "mart", "marts"):
        p = MODELS_DIR / subdir / f"{model_name}.sql"
        if p.exists():
            return p
    raise FileNotFoundError(
        f"Model file not found: {model_name}.sql  "
        f"(searched {MODELS_DIR}/staging|mart|marts/)"
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


def run(
    dry_run: bool = False,
    skip_w1: bool = False,
    w1_only: bool = False,
    w3pre: bool = False,
    w3pre_only: bool = False,
) -> None:
    import duckdb

    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs")
    conn.execute("""
        CREATE OR REPLACE SECRET baseball_s3 (
          TYPE S3,
          PROVIDER credential_chain,
          REGION 'us-east-2'
        )
    """)

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

    # ── W3pre: odds/staging flatten tier (E11.1-W3pre) — OPT-IN ──────────────
    # NOT built by default: the daily run_w1_lakehouse_op calls this with no args, and
    # the W3pre stg models need the lakehouse_raw/ tier populated (export + flipped
    # writers) first. Enable with --w3pre once the raw export is wired and cutover is
    # validated, so an empty raw tier can't fail the HALT-tier daily op.
    if w3pre:
        _build_w3pre(conn, dry_run)

    conn.close()
    print(f"\nW1+W2{'+W3pre' if w3pre else ''} lakehouse run complete.")


if __name__ == "__main__":
    run(
        dry_run="--dry-run" in sys.argv,
        skip_w1="--skip-w1" in sys.argv,
        w1_only="--w1-only" in sys.argv,
        w3pre="--w3pre" in sys.argv,
        w3pre_only="--w3pre-only" in sys.argv,
    )
