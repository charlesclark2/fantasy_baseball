"""E11.23 AC guard — EVERY sensor that reads a lakehouse first-pitch ``game_date`` timestamp must
route it through ``betting_ml.utils.lakehouse_monitor.to_utc_datetime``.

The INC-23 landmine: the lakehouse stores every ``TIMESTAMP*`` column as ISO **VARCHAR**, so a DuckDB
``MIN/MAX(game_date)`` returns a *str*; calling ``.astimezone()`` / ``.tzinfo`` on it crashes the sensor
tick, which fail-opens to a SkipReason forever (served odds froze 3 days with no alert, 2026-07-03).
Only SOME sensors were routed through the shared coercion helper; this test makes "all of them" a
mechanical invariant so the next sensor that reads a first-pitch ``game_date`` can't reintroduce the
inline-coercion crash. Sensors that read a freshness heartbeat via a SQL ``::timestamp`` cast
(``MAX(ingestion_ts::timestamp)``) are structurally immune and are NOT required to import the helper.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_SENSORS_DIR = Path(__file__).resolve().parents[2] / "pipeline" / "sensors"
# A SELECT of the first-pitch instant off the lakehouse (the value that comes back as ISO VARCHAR).
_FIRST_PITCH_READ = re.compile(r"(MIN|MAX)\(game_date\)", re.IGNORECASE)
# The forbidden inline coercions the helper replaces (crash on a str).
_INLINE_COERCION = re.compile(r"game_date.*\.(astimezone|tzinfo)", re.IGNORECASE)


def _sensor_files() -> list[Path]:
    return sorted(p for p in _SENSORS_DIR.glob("*.py") if p.name != "__init__.py")


@pytest.mark.parametrize("path", _sensor_files(), ids=lambda p: p.name)
def test_first_pitch_reads_route_through_to_utc_datetime(path: Path):
    src = path.read_text()
    if not _FIRST_PITCH_READ.search(src):
        pytest.skip(f"{path.name} does not read MIN/MAX(game_date)")
    assert "to_utc_datetime" in src, (
        f"{path.name} reads a lakehouse first-pitch game_date but does NOT route it through "
        f"to_utc_datetime — an ISO-VARCHAR read will crash the tick (INC-23). Coerce via "
        f"betting_ml.utils.lakehouse_monitor.to_utc_datetime."
    )


def test_at_least_the_known_first_pitch_sensors_are_covered():
    """Sanity: the five sensors known to read a first-pitch game_date are actually being checked
    (guards against the regex silently matching nothing if the SQL is reworded)."""
    covered = {p.name for p in _sensor_files() if _FIRST_PITCH_READ.search(p.read_text())}
    expected = {
        "lineup_monitor_sensor.py",
        "statcast_freshness_sensor.py",
        "conviction_pick_alert_sensor.py",
        "pregame_alert_sensor.py",
        "odds_current_rebuild_sensor.py",
    }
    assert expected <= covered, f"first-pitch sensors not detected: {expected - covered}"
