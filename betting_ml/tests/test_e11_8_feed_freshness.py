"""E11.8 — regression guards for feed-freshness monitoring completeness.

Covers three recurrence-prevention checks born from INC-7 / INC-8:

  1. Scheduling gap (INC-8): update_archetype_posteriors_op must be present in
     daily_ingestion_job so archetype posteriors are updated every day, not only
     on the (sometimes-skipped) statcast_catchup_job path.

  2. Statcast SLA breach must RAISE (not yield SkipReason): the sensor tick must
     fail when Statcast is still missing within _DEADLINE_LEAD of first pitch, so
     Dagster's standard email-on-failure alert fires (INC-5 monitor-the-monitors
     lesson: a sensor that silently skips on a real problem is the same blind spot).

  3. schedule_freshness_alert_sensor is registered in all_sensors (the new HARD
     alert for schedule-data staleness on game days).

Import strategy: AST/source-text analysis where possible to avoid Dagster / Snowflake
dependencies at test time.
"""
import ast
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).parents[2]


def _read(rel: str) -> str:
    return (_REPO / rel).read_text()


def _parse(rel: str) -> ast.Module:
    return ast.parse(_read(rel))


# ── 1. Archetype posteriors in daily_ingestion_job ───────────────────────────

class TestArchetypePosteriorsInDailyJob:
    """update_archetype_posteriors_op must be imported AND called in
    daily_ingestion_job.py (INC-8 scheduling gap fix, E11.8).

    The statcast_catchup_job already wires it; the daily job must too so
    archetype posteriors refresh on every run, not only when the catchup
    sensor fires.
    """

    @pytest.fixture(autouse=True)
    def _src(self):
        self._text = _read("pipeline/jobs/daily_ingestion_job.py")

    def test_op_is_imported(self):
        assert "update_archetype_posteriors_op" in self._text, (
            "update_archetype_posteriors_op is not imported in daily_ingestion_job.py — "
            "archetype posteriors only run in the statcast_catchup_job (INC-8 gap). "
            "Import and wire it in the daily job."
        )

    def test_op_is_called(self):
        """The op must be called (not just imported) somewhere in the job body."""
        tree = _parse("pipeline/jobs/daily_ingestion_job.py")
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "update_archetype_posteriors_op"
        ]
        assert calls, (
            "update_archetype_posteriors_op is imported but never called in "
            "daily_ingestion_job.py — wire it into the job graph (INC-8 fix)."
        )

    def test_op_precedes_dbt_umpire_feature_rebuild(self):
        """Archetype posteriors must be wired BEFORE dbt_umpire_feature_rebuild
        (which reads mart_player_archetype_posteriors).  Verify by line ordering."""
        lines = self._text.splitlines()
        archetype_line = None
        umpire_line = None
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if "update_archetype_posteriors_op(" in stripped and "=" in stripped:
                archetype_line = i
            if "dbt_umpire_feature_rebuild(" in stripped and "=" in stripped:
                umpire_line = i
        assert archetype_line is not None, (
            "update_archetype_posteriors_op(...) assignment not found in daily_ingestion_job.py"
        )
        assert umpire_line is not None, (
            "dbt_umpire_feature_rebuild(...) assignment not found in daily_ingestion_job.py"
        )
        assert archetype_line < umpire_line, (
            f"update_archetype_posteriors_op called at line {archetype_line} but "
            f"dbt_umpire_feature_rebuild called at line {umpire_line} — archetype "
            "posteriors must be wired before the feature rebuild reads them."
        )


def _strip_comments(src: str) -> str:
    """Return source with comment-only lines removed (for code-only assertions)."""
    lines = []
    for line in src.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith("#"):
            lines.append(line)
    return "\n".join(lines)


# ── 2. Statcast SLA breach must RAISE ────────────────────────────────────────

class TestStatcastSLABreachRaises:
    """The statcast_freshness_sensor SLA breach path must raise an Exception
    rather than yielding a SkipReason (INC-5 / monitor-the-monitors, E11.8).

    A SkipReason on the SLA breach branch means the sensor tick never fails →
    Dagster never sends an email-on-failure alert → the SLA breach goes unnoticed.
    The fix: raise Exception so the tick fails and the standard alert fires.
    """

    @pytest.fixture(autouse=True)
    def _src(self):
        raw = _read("pipeline/sensors/statcast_freshness_sensor.py")
        # Strip comment lines before asserting on code structure so comment text
        # referencing old "SkipReason" usage does not confuse the checks.
        self._text = _strip_comments(raw)

    def test_sla_breach_raises_not_skip_reason(self):
        """After the SLA breach condition (now_et >= deadline), the code must
        NOT yield SkipReason — it must raise an Exception."""
        src = self._text
        breach_idx = src.find("now_et >= deadline")
        assert breach_idx != -1, (
            "'now_et >= deadline' condition not found in statcast_freshness_sensor.py"
        )
        vicinity = src[breach_idx: breach_idx + 800]
        assert "raise Exception" in vicinity, (
            "SLA breach path in statcast_freshness_sensor.py does not raise Exception. "
            "A SkipReason here means Dagster never pages on the breach (INC-5 lesson). "
            "Change to: raise Exception('...')"
        )
        # Check no 'yield SkipReason' appears in code (non-comment) before the raise
        before_raise = vicinity.split("raise Exception")[0]
        assert "yield SkipReason" not in before_raise, (
            "SLA breach path yields SkipReason before raising — remove the yield and "
            "use raise Exception only (comments mentioning SkipReason are fine)."
        )

    def test_sla_breach_not_yield_skip_reason_after_breach(self):
        """The breach block must not contain a yield SkipReason (in code) before the raise."""
        src = self._text
        breach_idx = src.find("now_et >= deadline")
        assert breach_idx != -1
        vicinity = src[breach_idx: breach_idx + 600]
        raise_idx = vicinity.find("raise Exception")
        skip_idx  = vicinity.find("yield SkipReason")
        # If both present, the raise must come first (or SkipReason must be absent)
        if raise_idx != -1 and skip_idx != -1:
            assert raise_idx < skip_idx, (
                "yield SkipReason appears before raise Exception in the SLA breach block "
                "(code lines only) — a SkipReason before raise would still silence the alert."
            )


# ── 3. schedule_freshness_alert_sensor in all_sensors ────────────────────────

class TestScheduleFreshnessSensorRegistered:
    """schedule_freshness_alert_sensor must be listed in
    pipeline/sensors/__init__.py all_sensors so Dagster loads it (E11.8).

    Without this, the sensor exists in code but Dagster never evaluates it and
    the HARD alert for schedule staleness never fires.
    """

    @pytest.fixture(autouse=True)
    def _src(self):
        self._text = _read("pipeline/sensors/__init__.py")

    def test_sensor_imported(self):
        assert "schedule_freshness_alert_sensor" in self._text, (
            "schedule_freshness_alert_sensor not imported in pipeline/sensors/__init__.py — "
            "add: from pipeline.sensors.schedule_freshness_alert_sensor import schedule_freshness_alert_sensor"
        )

    def test_sensor_in_all_sensors_list(self):
        """The sensor must appear in the all_sensors list (not just imported)."""
        tree = _parse("pipeline/sensors/__init__.py")
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "all_sensors":
                        if isinstance(node.value, ast.List):
                            names = [
                                elt.id for elt in node.value.elts
                                if isinstance(elt, ast.Name)
                            ]
                            assert "schedule_freshness_alert_sensor" in names, (
                                "schedule_freshness_alert_sensor not in all_sensors list "
                                "in pipeline/sensors/__init__.py — add it so Dagster loads it."
                            )
                            return
        pytest.fail("Could not find all_sensors list in pipeline/sensors/__init__.py")


# ── 4. schedule_freshness_alert_sensor contract ───────────────────────────────

class TestScheduleFreshnessSensorContract:
    """The new schedule_freshness_alert_sensor must conform to the E11.7 contract:
    real problems RAISE (not SkipReason), transient errors yield SkipReason."""

    @pytest.fixture(autouse=True)
    def _src(self):
        self._text = _read("pipeline/sensors/schedule_freshness_alert_sensor.py")

    def test_sensor_raises_on_problems(self):
        """The sensor must call raise Exception when staleness is detected."""
        assert "raise Exception" in self._text, (
            "schedule_freshness_alert_sensor does not raise Exception — "
            "it must raise (not yield SkipReason) on real problems so Dagster pages."
        )

    def test_transient_connection_errors_yield_skip_reason(self):
        """Transient Snowflake failures must yield SkipReason, not raise."""
        assert "SkipReason" in self._text, (
            "schedule_freshness_alert_sensor never yields SkipReason — "
            "transient Snowflake errors should skip (not page) per INC-5 contract."
        )

    def test_sensor_deduplicates_per_day(self):
        """One alert per calendar day via cursor (same pattern as pregame_alert_sensor)."""
        assert "context.cursor" in self._text and "context.update_cursor" in self._text, (
            "schedule_freshness_alert_sensor lacks cursor deduplication — "
            "without it, the sensor fires on every 30-min tick after detecting staleness."
        )

    def test_alert_window_defined(self):
        """Sensor must define a time window so it doesn't fire at midnight."""
        assert "_WINDOW_OPEN_UTC" in self._text or "WINDOW_OPEN" in self._text, (
            "schedule_freshness_alert_sensor has no alert window — "
            "define _WINDOW_OPEN_UTC and _WINDOW_CLOSE_UTC to avoid midnight false alarms."
        )
