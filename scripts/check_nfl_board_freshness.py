#!/usr/bin/env python
"""NF-INFRA2 — is the PUBLISHED NFL draft board still advancing?

The operator's acceptance check for "did the scheduled publish actually fire, with no human in the
loop?", and the manual form of the daily paging op (`nfl_board_freshness_op`).

⭐ IT READS `manifest.generated_at` OUT OF THE PUBLISHED OBJECT, NEVER AN S3 `LastModified`
(INC-41). The exporter re-uploads all ~15 board files every publish, so an mtime advances whenever
the UPLOADER ran — including a run that re-uploaded a stale staging directory. `generated_at` is
stamped at BUILD time, so it advances only if a board was genuinely rebuilt, and it is the same
field the job's own `_verify_published` and the served UI stamp read.

⛔ THE PROOF OF LIFE IS AN ADVANCED `generated_at`, NOT A GREEN RUN IN DAGIT — and for this
artifact there may be no run at all: the failure mode this catches is the publish job NOT RUNNING
(a schedule reverted to STOPPED, a code location that failed to load, a stalled daemon), which
produces no failed run to notice. Note the timestamp this prints before a fire, and check it
INCREASED after.

Usage (LAPTOP or the EC2 BOX — read-only; needs S3 read on the api-cache bucket, us-east-1):
    uv run python scripts/check_nfl_board_freshness.py
    uv run python scripts/check_nfl_board_freshness.py --strict
    uv run python scripts/check_nfl_board_freshness.py --local-path <staged>/manifest.json

Exit codes: 0 = OK (or a non-strict run); 1 (with `--strict`) = STALE or UNKNOWN. An UNKNOWN
(unreadable) board is a FAILURE under `--strict`, never a pass — a check that could not run is not
a check that succeeded (NF1.7(a)).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.monitoring import nfl_board_freshness as NBF  # noqa: E402


def _default_season() -> int:
    from quant_sports_intel_models.football.nfl.ingest.sources import current_season

    return current_season()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-INFRA2 — published NFL board freshness SLA")
    ap.add_argument("--season", type=int, default=None,
                    help="board season (default: the clock-derived current_season())")
    ap.add_argument("--bucket", default=None,
                    help=f"override the api-cache bucket (default {NBF.DEFAULT_CACHE_BUCKET})")
    ap.add_argument("--local-path", default=None,
                    help="read a LOCAL manifest.json instead of S3 (e.g. a staged export)")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when the board is not OK (the acceptance-gate mode)")
    args = ap.parse_args(argv)

    season = args.season if args.season is not None else _default_season()
    now = datetime.now(timezone.utc)
    print(f"[METRIC] nfl_board_freshness_checked_at={now.isoformat()}")
    print(f"[METRIC] nfl_board_freshness_season={season}")

    reading = NBF.read_published_manifest(season, bucket=args.bucket,
                                          local_path=args.local_path)
    verdict = NBF.classify(reading, now=now)
    print(f"[METRIC] nfl_published_board_freshness={verdict['verdict']} "
          f"lag_hours={verdict['lag_hours']} sla_hours={verdict['sla_hours']}")
    print(f"[METRIC] nfl_published_board_generated_at="
          f"{reading.generated_at.isoformat() if reading.generated_at else 'UNREADABLE'}")
    print(f"[METRIC] nfl_published_board_coherence_present="
          f"{int(reading.coherence_present)}")
    marker = "OK " if not NBF.is_problem(verdict) else f"{verdict['severity']:<8}"
    print(f"  {marker} cadence={verdict['cadence']}")
    print(f"  {marker} {verdict['detail']}")

    problem = NBF.is_problem(verdict)
    print(f"[METRIC] nfl_board_freshness_problem_count={int(problem)}")
    if problem and args.strict:
        print("STRICT: the published NFL board is not OK — see above.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
