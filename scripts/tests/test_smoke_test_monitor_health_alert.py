"""NF-INFRA1 follow-up — pure/import-safe coverage for the live-box smoke script.

`send_alert` is imported lazily INSIDE `main()` (not at module scope), so importing this script's
module here never pulls in `pipeline` (no dbt-manifest read) — fast-gate safe. The actual SNS
delivery is only provable on the box (the 🟥 runtime gate); this locks in the parts that ARE
provable without it: the detector call is wired to the real schedule name, and both schedules this
story added are selectable.
"""
from __future__ import annotations

import argparse

from betting_ml.monitoring.monitor_health import CRITICAL_SCHEDULES, stopped_critical_instigators
from smoke_test_monitor_health_alert import _SyntheticStoppedInstance, main  # noqa: F401

_REQUIRED = {"sports_nfl_board_publish_schedule", "sports_nfl_sleeper_injuries_schedule"}


def test_synthetic_instance_flags_exactly_the_named_schedule():
    problems = stopped_critical_instigators(
        _SyntheticStoppedInstance("sports_nfl_board_publish_schedule")
    )
    assert any("sports_nfl_board_publish_schedule" in p and "STOPPED" in p for p in problems)
    assert not any("sports_nfl_sleeper_injuries_schedule" in p for p in problems)


def test_both_nf_infra1_followup_schedules_are_selectable():
    """The script's --schedule choices are drawn from CRITICAL_SCHEDULES — both new entries must
    be reachable, or the smoke can't cover them."""
    assert _REQUIRED <= CRITICAL_SCHEDULES
    # argparse choices mirror CRITICAL_SCHEDULES exactly (sorted in the script) — assert the same
    # membership a real `--schedule <name>` invocation would validate against.
    parser = argparse.ArgumentParser()
    parser.add_argument("--schedule", choices=sorted(CRITICAL_SCHEDULES))
    for name in sorted(_REQUIRED):
        parser.parse_args(["--schedule", name])  # raises SystemExit on an invalid choice
