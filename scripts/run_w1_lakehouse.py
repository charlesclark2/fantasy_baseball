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
  python3 scripts/run_w1_lakehouse.py            # full run  (writes to S3)
  python3 scripts/run_w1_lakehouse.py --dry-run  # row-count only, no S3 writes
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

MART_MODELS = [
    "mart_pitch_characteristics",
    "mart_pitch_play_event",
    "mart_pitch_game_context",
    "mart_pitch_fielding",
    "mart_pitch_hitter_profile",
    "mart_pitch_pitcher_profile",
    "mart_pitch_hit_characteristics",
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

    if model_name == "stg_batter_pitches":
        # Layout A: pull the duckdb branch out of the if/else
        m = re.search(
            r'\{%-?\s*if\s+target\.name\s*==\s*[\'"]duckdb[\'"]\s*-?%\}'
            r'(.*?)'
            r'\{%-?\s*else\s*-?%\}',
            text, re.DOTALL,
        )
        if not m:
            raise ValueError("Could not find duckdb branch in stg_batter_pitches.sql")
        sql = m.group(1)

        # Strip {{ config(...) }}
        sql = re.sub(r'\{\{[^}]*config[^}]*\}\}', '', sql)

        # Resolve {{ lakehouse_loc("stg_batter_pitches") }} → S3 path
        sql = re.sub(
            r'\{\{\s*lakehouse_loc\([\'"]stg_batter_pitches[\'"]\)\s*\}\}',
            f"{LAKEHOUSE}/stg_batter_pitches/",
            sql,
        )

    else:
        # Layout B: mart_pitch_* models have {{ config() }} at the top level
        # (NOT inside a {% if target.name %} conditional — strip it directly).
        sql = text

        # Strip {{ config(...) }} — multi-line block at the top of each model
        sql = re.sub(r'\{\{\s*config\(.*?\)\s*\}\}', '', sql, flags=re.DOTALL)

        # Strip any remaining {% if target.name == 'duckdb' %} … {% endif %} blocks
        sql = re.sub(
            r'\{%-?\s*if\s+target\.name\s*==\s*[\'"]duckdb[\'"]\s*-?%\}'
            r'.*?'
            r'\{%-?\s*endif\s*-?%\}',
            '', sql, flags=re.DOTALL,
        )

        # Resolve {{ ref('model') }} → model
        sql = re.sub(r"\{\{\s*ref\(['\"](\w+)['\"]\)\s*\}\}", r'\1', sql)

        # Resolve {{ source('schema', 'table') }} → table
        sql = re.sub(
            r"\{\{\s*source\(['\"][^'\"]+['\"],\s*['\"](\w+)['\"]\)\s*\}\}", r'\1', sql
        )

        # Strip {% if is_incremental() %} … {% endif %} blocks (removes {{ this }})
        sql = re.sub(
            r'\{%-?\s*if\s+is_incremental\(\)\s*-?%\}.*?\{%-?\s*endif\s*-?%\}',
            '', sql, flags=re.DOTALL,
        )

    # Guard: any surviving Jinja will cause a DuckDB parser error
    if re.search(r'\{[{%]', sql):
        sample = re.findall(r'\{[{%][^}]*?[%}]\}', sql)[:3]
        raise ValueError(f"Unresolved Jinja in {model_name}.sql: {sample}")

    return sql.strip()


def run(dry_run: bool = False) -> None:
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

    # Register stg_batter_pitches as a view so mart refs resolve.
    stg_sql = extract_duckdb_sql("stg_batter_pitches")
    conn.execute(f"CREATE OR REPLACE VIEW stg_batter_pitches AS {stg_sql}")
    n = conn.execute("SELECT count(*) FROM stg_batter_pitches").fetchone()[0]
    print(f"stg_batter_pitches: {n:,} pitches loaded from S3")

    # mart_pitch_hitter_profile and mart_pitch_pitcher_profile left-join ref_players
    # for display names.  ref_players lives in Snowflake (baseball_data.savant.ref_players)
    # and is not yet on S3.  Create an empty stub so the left join compiles; player name
    # columns (batter_name, pitcher_name, etc.) will be NULL until ref_players is exported.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ref_players (
            mlb_bam_id       INTEGER,
            first_name       VARCHAR,
            last_name        VARCHAR,
            player_name      VARCHAR,
            mlb_played_first INTEGER,
            mlb_played_last  INTEGER
        )
    """)
    print("ref_players: empty stub (player name cols will be NULL)")

    for model in MART_MODELS:
        loc = f"{LAKEHOUSE}/{model}/data.parquet"
        mart_sql = extract_duckdb_sql(model)
        if dry_run:
            n = conn.execute(f"SELECT count(*) FROM ({mart_sql}) t").fetchone()[0]
            print(f"  {model}: {n:,} rows  (dry-run — no S3 write)")
        else:
            conn.execute(f"COPY ({mart_sql}) TO '{loc}' (FORMAT PARQUET)")
            print(f"  {model}: written → {loc}")

    conn.close()
    print("\nW1 lakehouse run complete.")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
