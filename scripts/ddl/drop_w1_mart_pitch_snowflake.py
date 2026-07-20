#!/usr/bin/env python3
"""
scripts/ddl/drop_w1_mart_pitch_snowflake.py  (E11.20 phase 1.5 — §6 step c)

DROP the Snowflake side of the W1 pitch-mart family: the 7 betting.mart_pitch_* thin
views + the 7 lakehouse_ext.mart_pitch_* external tables. Safe because (verified before
this script existed — docs/e11_20_delta_rollout.md §6):
  - zero-reader check PASSED 2026-07-18 (access_history: real reads ended 07-13),
  - every raw-SQL straggler is repointed to the lakehouse (§6 a0; guard:
    betting_ml/tests/test_phase15_straggler_repoint.py),
  - the SF-side dbt models are disabled (enabled=(target.name=='duckdb')) so the daily
    dbt run no longer re-creates the views,
  - the compat-mirror write is retired (W1_SF_COMPAT_MIRROR default 0).

Default = print the DDL only. --apply executes it via the shared resolver
(betting_ml.utils.data_loader.get_snowflake_connection — the blessed inline-key parser;
the Snowflake MCP role cannot run DDL). Views drop before ext tables (dependency order).
Run WHERE the key lives: the LAPTOP, or the box via
  docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \\
      python scripts/ddl/drop_w1_mart_pitch_snowflake.py --apply

Rollback: scripts/ddl/w1_external_tables.sql re-creates everything; then set
W1_SF_COMPAT_MIRROR=1 (next daily re-freshens the compat mirror) and re-add W1_TABLES
to the daily refresh in scripts/refresh_w1_external_tables.py.
"""
from __future__ import annotations

import argparse
import sys

MARTS = [
    "mart_pitch_characteristics",
    "mart_pitch_play_event",
    "mart_pitch_game_context",
    "mart_pitch_fielding",
    "mart_pitch_hitter_profile",
    "mart_pitch_pitcher_profile",
    "mart_pitch_hit_characteristics",
]

DDL = (
    [f"drop view if exists baseball_data.betting.{m}" for m in MARTS]
    + [f"drop external table if exists baseball_data.lakehouse_ext.{m}" for m in MARTS]
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="execute the DDL (default: print only)")
    args = ap.parse_args()

    if not args.apply:
        print("-- DRY RUN (pass --apply to execute):")
        for stmt in DDL:
            print(f"{stmt};")
        return 0

    from betting_ml.utils.data_loader import get_snowflake_connection
    conn = get_snowflake_connection()
    cur = conn.cursor()
    failures = 0
    for stmt in DDL:
        try:
            cur.execute(stmt)
            print(f"✔ {stmt}")
        except Exception as exc:  # noqa: BLE001 — report every statement, then fail loud
            failures += 1
            print(f"✘ {stmt}\n    {exc}", file=sys.stderr)
    conn.close()
    if failures:
        print(f"\n{failures} statement(s) FAILED — SF state is now partial; re-run after "
              f"fixing (statements are idempotent `if exists`).", file=sys.stderr)
        return 1
    print(f"\nAll {len(DDL)} drops applied. The W1 mart_pitch_* family is SF-free "
          f"(AC-C clock starts now).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
