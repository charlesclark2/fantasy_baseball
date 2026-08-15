"""NF-INFRA1 follow-up (2026-08-15) — the board-publish/Sleeper heartbeat guard (fast-gate safe).

WHY: NF-INFRA1 turned `sports_nfl_board_publish_schedule` ON in Dagit and confirmed
`sports_nfl_sleeper_injuries_schedule` ON, but both shipped `default_status=STOPPED` and neither
was in `check_monitors_healthy_op`'s required-RUNNING set (`CRITICAL_SCHEDULES`). Their ON state
lived ONLY in the Dagster Postgres, so a volume reset / box re-host would silently revert them to
STOPPED — the board freezes (or Sleeper goes dark again) — with nothing paging. This is the same
"silently never runs" class E11.23 already cures for the primary sensors/schedules; this guard
keeps CRITICAL_SCHEDULES and the BOX_OPERATIONS.md §10 table in sync for these two, mechanically
(the E11.23 convention: "extend both together").

Imports ``betting_ml.monitoring.monitor_health`` — NOT ``pipeline`` — on purpose: importing the
pipeline package triggers the dbt-manifest read, absent in the fast gate (E11.23). The
default_status=RUNNING self-start AC is cross-checked against the ACTUAL registered schedule
objects in ``test_monitor_health_wiring.py`` (manifest-guarded; `sports_nfl_board_publish_schedule`
/ `sports_nfl_sleeper_injuries_schedule` fall under its existing `test_critical_instigators_self_start`
sweep once they're in `CRITICAL_SCHEDULES` — no new test needed there).
"""
from __future__ import annotations

from pathlib import Path

from betting_ml.monitoring.monitor_health import CRITICAL_SCHEDULES

_REPO = Path(__file__).resolve().parents[2]
_BOX_OPS = _REPO / "services" / "dagster" / "aws" / "BOX_OPERATIONS.md"

_REQUIRED_RUNNING = {
    "sports_nfl_board_publish_schedule",
    "sports_nfl_sleeper_injuries_schedule",
}
# ⛔ Deliberately excluded until the NCAAF-on-box card turns them on (they ship STOPPED on
# purpose) — adding them to CRITICAL_SCHEDULES now would false-page every heartbeat evaluation.
_DELIBERATELY_EXCLUDED = {
    "sports_ncaaf_dbt_schedule",
    "sports_ncaaf_roll_forward_schedule",
}


def test_board_publish_and_sleeper_are_in_the_required_running_set():
    """The exact defect this story fixes: nothing paged on a silent revert to STOPPED because
    neither schedule was in the heartbeat's required-RUNNING set."""
    assert _REQUIRED_RUNNING <= CRITICAL_SCHEDULES, (
        f"missing from CRITICAL_SCHEDULES: {_REQUIRED_RUNNING - CRITICAL_SCHEDULES}"
    )


def test_ncaaf_schedules_are_not_yet_in_the_required_running_set():
    """NCAAF is intentionally STOPPED until the NCAAF-on-box card flips it — adding it here now
    would false-page every evaluation while it's deliberately off."""
    assert _DELIBERATELY_EXCLUDED.isdisjoint(CRITICAL_SCHEDULES), (
        f"NCAAF schedules leaked into CRITICAL_SCHEDULES before their story turned them on: "
        f"{_DELIBERATELY_EXCLUDED & CRITICAL_SCHEDULES}"
    )


def _row_for(text: str, name: str) -> str:
    """The single §10 table row whose FIRST cell names `name` — anchored on line start so a
    cross-reference to the same schedule INSIDE another row's prose can't satisfy the match."""
    for line in text.splitlines():
        if line.startswith(f"| `{name}`") or line.startswith(f"| `{name}` /"):
            return line
    raise AssertionError(f"no BOX_OPERATIONS.md §10 table row starts with `{name}`")


def test_box_operations_doc_marks_both_schedules_running_and_heartbeat_checked():
    """§10 is the source-of-truth table E11.23 requires be kept in sync with CRITICAL_SCHEDULES —
    a code-only change here is a documentation lie the next operator reads as ground truth."""
    text = _BOX_OPS.read_text()
    for name in sorted(_REQUIRED_RUNNING):
        row = _row_for(text, name)
        assert "RUNNING" in row, f"{name}'s §10 row does not say RUNNING: {row[:120]}..."
        assert "heartbeat-checked" in row or "CRITICAL_SCHEDULES" in row, (
            f"{name}'s §10 row does not claim heartbeat coverage — the doc and "
            f"CRITICAL_SCHEDULES have drifted apart: {row[:120]}..."
        )


def test_box_operations_doc_still_marks_ncaaf_schedules_not_heartbeat_checked():
    """The NCAAF rows must keep saying NOT heartbeat-checked while they're deliberately excluded —
    catches the doc drifting ahead of (or behind) the code either direction."""
    text = _BOX_OPS.read_text()
    for name in sorted(_DELIBERATELY_EXCLUDED):
        row = _row_for(text, name)
        assert "NOT heartbeat-checked" in row, (
            f"{name}'s §10 row no longer says NOT heartbeat-checked — if it's now heartbeat-"
            f"checked, add it to CRITICAL_SCHEDULES in the SAME change: {row[:120]}..."
        )
