"""NF-INFRA1 follow-up (2026-08-15) — a live-box smoke of `check_monitors_healthy_op`'s page path.

INC-39: E11.30 requires a live-box smoke for every ALERT-tier monitor (CI mocks all IO, so only a
real box run proves the SNS page fires). This proves it for the two schedules this story just added
to `CRITICAL_SCHEDULES` (`sports_nfl_board_publish_schedule`, `sports_nfl_sleeper_injuries_schedule`)
WITHOUT actually stopping either — a real stop would freeze the board / dark Sleeper for however
long the smoke takes, which is exactly the failure this story exists to page on, not to rehearse.

Mechanism: builds a SYNTHETIC fake Dagster instance whose `all_instigator_state(STOPPED)` reports
exactly one instigator name — the schedule under test — as STOPPED. Feeds that into the REAL
`stopped_critical_instigators` detector from `betting_ml.monitoring.monitor_health` (the same
function `check_monitors_healthy_op` calls), so this proves the production detection logic actually
flags the name, not a hand-copied message string. The resulting page goes out via
`send_alert(..., smoke=True)` (INC-39) — labelled `[SMOKE TEST]`, on the `smoke:` dedup namespace —
so it cannot occupy the real `monitor_health` alert's dedup slot or be mistaken for a genuine page.

Usage (on the box):
    docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \\
      python scripts/smoke_test_monitor_health_alert.py --schedule sports_nfl_board_publish_schedule
    docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \\
      python scripts/smoke_test_monitor_health_alert.py --schedule sports_nfl_sleeper_injuries_schedule

Exits 0 only if the detector flagged the synthetic STOPPED state AND `send_alert` reports the smoke
was published (never rate-limited — each run uses a fresh dedup key so repeat smokes never no-op).
"""
from __future__ import annotations

import argparse
import sys
import time
from types import SimpleNamespace

from betting_ml.monitoring.monitor_health import CRITICAL_SCHEDULES, stopped_critical_instigators


class _SyntheticStoppedInstance:
    """Stands in for a real DagsterInstance: reports exactly ONE instigator — the schedule under
    test — as STOPPED. Never touches the real Dagster instance or the real schedule."""

    def __init__(self, schedule_name: str):
        self._schedule_name = schedule_name

    def all_instigator_state(self, instigator_statuses=None):  # noqa: ARG002
        return [SimpleNamespace(instigator_name=self._schedule_name)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--schedule", required=True, choices=sorted(CRITICAL_SCHEDULES),
        help="the CRITICAL_SCHEDULES entry to simulate as STOPPED (a real schedule name, but its "
             "actual on/off state on the box is never read or changed)",
    )
    args = ap.parse_args()

    problems = stopped_critical_instigators(_SyntheticStoppedInstance(args.schedule))
    if not any(args.schedule in p for p in problems):
        print(f"FAIL: stopped_critical_instigators did not flag the synthetic STOPPED "
              f"{args.schedule!r} — the detector itself is broken, not just the page path.")
        return 1
    print(f"OK: detector flagged the synthetic STOPPED state — {problems}")

    from pipeline.utils.alerting import send_alert

    msg = (
        "[SMOKE — synthetic STOPPED state; the real schedule was NOT touched] "
        "SILENTLY-NOT-RUNNING ALERT (E11.23): serving-critical monitors are OFF or intraday "
        "refreshes are gated off — they FAIL SILENT (the odds-froze-3-days class). "
        + "; ".join(problems)
        + ". Fix: START the STOPPED sensor/schedule in Dagit (toggle on) and/or set the missing "
        "flag(s) in the box env_file + redeploy. Intended-state table: "
        "services/dagster/aws/BOX_OPERATIONS.md §10."
    )
    # A fresh dedup key per run — smoke or not, this must never rate-limit itself into a false OK.
    dedup_key = f"nf_infra1_followup_smoke:{args.schedule}:{int(time.time())}"
    ok = send_alert(
        "Monitor silently not running", msg, severity="CRITICAL",
        dedup_key=dedup_key, smoke=True,
    )
    print(f"send_alert(smoke=True) returned: {ok}")
    if not ok:
        print("FAIL: send_alert reported the smoke was NOT published (misconfig or SNS error) — "
              "check ALERT_SNS_TOPIC_ARN / the box's SNS permissions.")
        return 1
    print(f"PASS: confirm a '[SMOKE TEST] ... Monitor silently not running' email arrived, "
          f"then re-run with --schedule <the other one> to cover both.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
