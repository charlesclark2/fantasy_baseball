"""NF-W0a — the capture jobs are REGISTERED, SCHEDULED, and actually PAGE.

Two layers, deliberately:

  • SOURCE-INSPECTION (always runs, fast gate). ⚠️ Fast-gate tests must NOT import `pipeline` —
    `pipeline/__init__.py` reads the dbt manifest at import, which is gitignored and therefore
    ABSENT in a fresh worktree, so an importing test dies at COLLECTION rather than skipping
    cleanly (the E11.23 rule / the NF-D18 worktree landmine).
  • IN-PROCESS EXECUTION (skipped without the manifest). This is the "wired ≠ invoked" check
    NF-C0e names: a job can be registered in every list and still never actually call the leg or
    fire its page. One test executes the REAL op through a real Dagster job and asserts the page
    goes out — with only the leg itself stubbed.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[2]
_JOBS_INIT = _REPO / "pipeline/jobs/__init__.py"
_SCHED_INIT = _REPO / "pipeline/schedules/__init__.py"
_SCHED_SRC = _REPO / "pipeline/schedules/sports_nfl_pit_capture_schedules.py"
_JOB_SRC = _REPO / "pipeline/jobs/sports_nfl_pit_capture_job.py"

JOBS = ("sports_nfl_pit_weather_job", "sports_nfl_pit_metadata_job", "sports_nfl_pit_market_job")
SCHEDULES = (
    "sports_nfl_pit_weather_schedule",
    "sports_nfl_pit_metadata_schedule",
    "sports_nfl_pit_market_schedule",
)

_MANIFEST = _REPO / "dbt/target/manifest.json"
needs_manifest = pytest.mark.skipif(
    not _MANIFEST.exists(),
    reason="dbt/target/manifest.json absent (gitignored; missing in a fresh worktree) — "
           "`pipeline` cannot be imported here. Run this from the main checkout.",
)


def _uncommented(path: Path) -> str:
    """Source with comment lines stripped.

    A registration guard that matches anywhere in the file would be satisfied by the EXPLANATORY
    COMMENT sitting above the import — the INC-38 "prose cannot satisfy the guard" defect. Both
    `__init__.py` files carry exactly such a comment naming these very symbols.
    """
    return "\n".join(
        line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")
    )


class TestTheJobsAndSchedulesAreRegistered:
    @pytest.mark.parametrize("name", JOBS)
    def test_job_is_in_all_jobs(self, name):
        src = _uncommented(_JOBS_INIT)
        assert re.search(rf"^\s+{name},\s*$", src, re.M), f"{name} is imported but not in `all_jobs`"

    @pytest.mark.parametrize("name", SCHEDULES)
    def test_schedule_is_in_all_schedules(self, name):
        src = _uncommented(_SCHED_INIT)
        assert re.search(rf"^\s+{name},\s*$", src, re.M), (
            f"{name} is imported but not in `all_schedules` — an unregistered schedule NEVER "
            f"fires, silently (the E11.23 outage class)"
        )

    def test_the_comment_stripping_actually_removed_something(self):
        """Guard the guard: if `_uncommented` were a no-op the tests above would pass on prose."""
        assert len(_uncommented(_SCHED_INIT)) < len(_SCHED_INIT.read_text())


class TestTheDefaultStatusSplitIsDeliberate:
    """The free/irreplaceable legs must self-start; the PAID leg must not."""

    @pytest.mark.parametrize("name", ["weather", "metadata"])
    def test_the_free_capture_legs_ship_RUNNING(self, name):
        block = _SCHED_SRC.read_text().split(f"def sports_nfl_pit_{name}_schedule")[0]
        decorator = block.rsplit("@schedule(", 1)[-1]
        assert "DefaultScheduleStatus.RUNNING" in decorator, (
            f"the {name} schedule ships STOPPED — a free capture whose misses are PERMANENT must "
            f"self-start; a STOPPED schedule silently never runs (E11.23)"
        )

    def test_the_PAID_market_leg_ships_STOPPED(self):
        block = _SCHED_SRC.read_text().split("def sports_nfl_pit_market_schedule")[0]
        decorator = block.rsplit("@schedule(", 1)[-1]
        assert "DefaultScheduleStatus.STOPPED" in decorator, (
            "the market schedule ships RUNNING — it spends PAID Odds-API credits and must be an "
            "explicit operator decision"
        )


class TestEveryOpActuallyPages:
    """E11.30: an 'ALERT-tier' op that only reaches `context.log.warning` notifies nobody. This
    repo shipped four of those and the blind spot survived for days."""

    def test_the_job_module_calls_send_alert(self):
        assert "send_alert(" in _JOB_SRC.read_text()

    def test_the_page_is_keyed_per_leg(self):
        """A shared dedup key would let one noisy leg suppress another's page for an hour
        (the INC-39 dedup-slot lesson)."""
        assert 'dedup_key=f"nfl_pit_capture:{leg}"' in _JOB_SRC.read_text()


@needs_manifest
class TestTheOpIsInvokedNotMerelyWired:
    """⭐ NF-C0e: a field is APPLIED when something CALLS it, not when its name appears in a list."""

    def test_the_weather_job_runs_the_leg_and_pages_on_escalation(self):
        from pipeline.jobs.sports_nfl_pit_capture_job import sports_nfl_pit_weather_job

        sent = []
        with patch(
            "quant_sports_intel_models.football.nfl.pit.run_capture.run_legs",
            return_value={"weather": {"captured": 0, "eligible": 3, "escalate": True}},
        ) as run_legs, patch(
            "pipeline.utils.alerting.send_alert",
            side_effect=lambda *a, **k: sent.append((a[0], k.get("severity"), k.get("dedup_key"))) or True,
        ):
            result = sports_nfl_pit_weather_job.execute_in_process()

        assert result.success, "the capture job must never fail the run (WARN tier)"
        assert run_legs.called, "the job is wired but never CALLS the capture leg"
        assert sent and sent[0][1] == "CRITICAL", f"no CRITICAL page fired on escalation: {sent}"
        assert sent[0][2] == "nfl_pit_capture:weather"

    def test_a_raising_leg_does_not_fail_the_job_but_still_pages(self):
        from pipeline.jobs.sports_nfl_pit_capture_job import sports_nfl_pit_market_job

        sent = []
        with patch(
            "quant_sports_intel_models.football.nfl.pit.run_capture.run_legs",
            side_effect=RuntimeError("odds api down"),
        ), patch(
            "pipeline.utils.alerting.send_alert", side_effect=lambda *a, **k: sent.append(a[0]) or True
        ):
            result = sports_nfl_pit_market_job.execute_in_process()

        assert result.success, "a capture failure is not a serving outage — it must not fail the job"
        assert sent, "a raising leg paged nobody"

    def test_a_clean_run_does_NOT_page(self):
        """The other half: a monitor that pages on a healthy run gets muted, and then the real
        page goes unread (the over-paging failure this repo names explicitly)."""
        from pipeline.jobs.sports_nfl_pit_capture_job import sports_nfl_pit_weather_job

        sent = []
        with patch(
            "quant_sports_intel_models.football.nfl.pit.run_capture.run_legs",
            return_value={"weather": {"captured": 12, "eligible": 12, "escalate": False}},
        ), patch(
            "pipeline.utils.alerting.send_alert", side_effect=lambda *a, **k: sent.append(a[0]) or True
        ):
            sports_nfl_pit_weather_job.execute_in_process()
        assert sent == [], f"a healthy capture paged: {sent}"
