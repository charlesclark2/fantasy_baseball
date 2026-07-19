"""2026-07-19 — postponed-makeup dedup guard (the 823523 rained-out-Saturday bug).

MLB marks a Postponed game abstractGameState='Final', then reuses the SAME gamePk for the
makeup (state 'Preview') — both entries coexist in one schedule snapshot. stg_statsapi_games'
dedup ranked states Final(3) > Preview(1), so the STALE postponed row won: the served game
time showed the rained-out slot (00:08Z instead of 16:35Z) and the Statcast SLA sensor's
"today's first pitch" read a past instant and false-fired a CRITICAL.

The cure (source-inspected here, mirroring the test_timestamp_wrap_guard pattern — the
DuckDB branch only builds on the box):
  1. stg_statsapi_games demotes detailedState='Postponed' to rank 1 (ties Preview; the
     coexisting makeup wins via the postponed-last tiebreak, an older-snapshot Preview
     still loses to a postponed-only game via ingestion_ts).
  2. statcast_freshness_sensor excludes Postponed rows from its MIN(first pitch).
"""
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_STG = (_ROOT / "dbt" / "models" / "staging" / "stg_statsapi_games.sql").read_text()
_SENSOR = (_ROOT / "pipeline" / "sensors" / "statcast_freshness_sensor.py").read_text()


def _dedup_block() -> str:
    start = _STG.index("deduped as (")
    return _STG[start:_STG.index("from deduped", start)]


def test_postponed_demoted_below_live_states():
    """The state-rank CASE must special-case detailedState='Postponed' to rank 1 — if the
    plain abstractGameState ranking returns, Postponed (abstract 'Final') again beats the
    makeup's 'Preview' and the stale row wins."""
    block = _dedup_block()
    assert "detailedState') = 'Postponed' then 1" in block, (
        "stg_statsapi_games dedup no longer demotes Postponed below Live/Final — the "
        "postponed original will out-rank its makeup entry again (823523 class)"
    )


def test_postponed_last_tiebreak_present():
    """Within one snapshot (equal ingestion_ts) the makeup must beat the postponed original
    deterministically — an explicit postponed-last ASC tiebreak, not just the DH flag (a
    makeup rescheduled to a plain non-DH date has doubleHeader='N' on both entries)."""
    block = _dedup_block()
    assert block.count("= 'Postponed' then 1") >= 2, (
        "the postponed-last tiebreak after ingestion_ts is gone — same-snapshot "
        "postponed-vs-makeup ordering is arbitrary again"
    )


def test_statcast_first_pitch_excludes_postponed():
    """The SLA sensor's first-pitch MIN must filter Postponed rows — their game_date is the
    original (past) instant, which makes the deadline instantly breached."""
    assert "detailed_state <> 'Postponed'" in _SENSOR, (
        "statcast_freshness_sensor MIN(game_date) no longer excludes Postponed rows — a "
        "postponed game's stale past first-pitch will false-fire the SLA breach"
    )
