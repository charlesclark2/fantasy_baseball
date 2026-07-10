#!/usr/bin/env python3
"""
scripts/delta_maintenance.py   (E11.20)

Compact + vacuum every Delta-backed lakehouse table — the REQUIRED companion to the daily
partition-overwrite pattern (spike gotcha #7: each incremental write adds small files;
unmaintained, file count grows and read planning degrades). Vacuum retention is clamped to
the 168h floor inside scripts/utils/delta_lake.compact_and_vacuum (spike gotcha #3: below
that, the files older versions point to are physically deleted and time-travel — the
leakage-audit / point-in-time asset — is destroyed).

Invoked daily by lakehouse_delta_maintenance_op (WARN-but-continue tier — a failure defers
maintenance to the next run, never blocks serving). Safe to run manually any time:

  uv run python scripts/delta_maintenance.py            # all Delta-backed tables
  uv run python scripts/delta_maintenance.py mart_pitch_play_event   # one table

Per-table failures WARN to stderr and continue (one table's maintenance must not starve
the rest); exits 1 if any table failed so the caller's tier decides loudness.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
try:
    from betting_ml.utils.delta_lakehouse import DELTA_W1_TABLES, delta_w1_mode
except ModuleNotFoundError:
    sys.path.insert(0, str(REPO_ROOT))
    from betting_ml.utils.delta_lakehouse import DELTA_W1_TABLES, delta_w1_mode


def main() -> int:
    mode = delta_w1_mode()
    if mode == "off":
        print("WARNING: [delta-maintenance] LAKEHOUSE_DELTA_W1=off — nothing to maintain "
              "(loud no-op).", file=sys.stderr)
        return 0

    from scripts.utils.delta_lake import compact_and_vacuum, table_exists

    requested = [a for a in sys.argv[1:] if not a.startswith("-")]
    tables = requested or sorted(DELTA_W1_TABLES)
    failed: list[str] = []
    for table in tables:
        if not table_exists(table):
            print(f"WARNING: [delta-maintenance] {table}: Delta table absent — has the "
                  f"--delta-full backfill run? Skipping.", file=sys.stderr)
            continue
        try:
            info = compact_and_vacuum(table)
            print(f"  ✔ {table}: v{info['version']}, {info['files_after_compact']} files "
                  f"after compact, {info['vacuumed_files']} vacuumed")
        except Exception as e:  # noqa: BLE001 — one table's failure must not starve the rest
            print(f"WARNING: [delta-maintenance] {table} FAILED: {e}", file=sys.stderr)
            failed.append(table)
    if failed:
        print(f"WARNING: [delta-maintenance] failed tables: {failed}", file=sys.stderr)
        return 1
    print("Delta maintenance complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
