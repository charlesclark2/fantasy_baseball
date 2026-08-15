#!/usr/bin/env python
"""NF-INFRA1 — read the SPORTS lake's Delta transaction logs and report each table's freshness.

The `check_data_freshness.py` analogue for the sports (NCAAF/NFL) S3 Delta lake, and the operator's
acceptance check for "did the Sleeper feed actually come back to life?".

⭐ IT READS THE COMMIT TIMESTAMP INSIDE `_delta_log`, NEVER AN S3 `LastModified` (INC-41): an mtime
is refreshed by any server-side rewrite (compaction, a re-copy) that changes no data, and
`aws s3 ls` prints SHELL-LOCAL time — both would have read GREEN straight through the 19-day
NF-FRESH1 outage this exists to catch.

⛔ THE PROOF OF LIFE IS A NEW COMMIT VERSION, NOT A GREEN JOB RUN. That is the whole NF-FRESH1
lesson: `sports_nfl_sleeper_injuries_job` reported SUCCESS 19 times over one 19-day-old commit.
Note the `version=` this prints before a run, and check it INCREASED after.

Usage (LAPTOP or the EC2 BOX — read-only, Snowflake-free, needs S3 read on the sports lake):
    SPORTS_LAKE_REGION=us-east-2 uv run python scripts/check_sports_delta_freshness.py
    SPORTS_LAKE_REGION=us-east-2 uv run python scripts/check_sports_delta_freshness.py --strict

Exit codes: 0 = every contract OK (or a non-strict run); 1 (with `--strict`) = at least one
contract is STALE/EMPTY/UNKNOWN. An UNKNOWN (unreadable) contract is a FAILURE under `--strict`,
never a pass — a check that could not run is not a check that succeeded (NF1.7(a)).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.monitoring import sports_delta_freshness as SDF  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-INFRA1 — sports Delta-lake freshness SLAs")
    ap.add_argument("--contract", action="append", default=None,
                    help="check only these contract names (repeatable); default: all")
    ap.add_argument("--bucket", default=None, help="override the sports lake bucket")
    ap.add_argument("--lake-root", default=None, help="read a LOCAL-FS Delta tree instead of S3")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when any contract is not OK (the acceptance-gate mode)")
    args = ap.parse_args(argv)

    contracts = SDF.REGISTRY
    if args.contract:
        contracts = tuple(SDF.by_name(n) for n in args.contract)

    now = datetime.now(timezone.utc)
    print(f"[METRIC] sports_delta_freshness_checked_at={now.isoformat()}")

    problems = []
    for contract in contracts:
        reading = SDF.read_contract(contract, bucket=args.bucket, local_root=args.lake_root)
        verdict = SDF.classify(contract, reading, now=now)
        # One machine-readable line per contract, mirroring the repo's `[METRIC]` convention so a
        # caller can key on it without parsing prose.
        print(f"[METRIC] {contract.name}_freshness={verdict['verdict']} "
              f"lag_hours={verdict['lag_hours']} version={reading.version} rows={reading.rows}")
        marker = "OK " if not SDF.is_problem(verdict) else f"{verdict['severity']:<8}"
        print(f"  {marker} {contract.name}: {verdict['detail']}")
        if SDF.is_problem(verdict):
            problems.append(verdict)

    print(f"[METRIC] sports_delta_freshness_problem_count={len(problems)}")
    if problems and args.strict:
        print("STRICT: at least one sports Delta contract is not OK — see above.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
