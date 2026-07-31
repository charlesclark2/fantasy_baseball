"""2026-07-31 — pin LOAD-THEN-DELETE ordering in the three sequential-posterior backfills.

THE INCIDENT THIS PINS. E9.53 added `guard_or_reset_backfill` so a `--backfill` could not silently
double-apply onto a populated season. It DELETEs when `--reset` is passed, and all three writers
called it BEFORE reading their game-date source. The first live use deleted **52,300 rows** from
`player_sequential_posteriors` and then RAISED, because the backfill's PA substrate
(`mart_pitch_play_event`) had been dropped from Snowflake by E11.20 phase-1.5 and the command
omitted `--s3`.

⭐ A guard that makes a repair safe against one failure mode and unsafe against another has just
MOVED the failure — here to a strictly worse place, since a silently inflated store degrades
calibration while an empty one breaks the consumers' join outright.

Source inspection only: the fast gate may not import `pipeline`, and importing these writers pulls
in snowflake/duckdb. The invariant is textual and structural — exactly what a regression would
break — so reading the file is the right instrument.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from betting_ml.scripts.sequential_bayes.catchup import require_source_before_reset

_SEQ = Path(__file__).resolve().parents[2] / "betting_ml" / "scripts" / "sequential_bayes"

WRITERS = {
    "update_player_posteriors.py": "player-seq-backfill",
    "update_team_posteriors.py": "team-seq-backfill",
    "update_matchup_cell_posteriors.py": "matchup-cell-backfill",
}


def _run_backfill_src(name: str) -> str:
    src = (_SEQ / name).read_text()
    start = src.index("def run_backfill")
    # to the next top-level def, or EOF
    nxt = src.find("\ndef ", start + 1)
    return src[start:] if nxt == -1 else src[start:nxt]


@pytest.mark.parametrize("name", sorted(WRITERS))
def test_every_writer_validates_the_source_before_the_destructive_guard(name):
    src = _run_backfill_src(name)
    assert "require_source_before_reset" in src, (
        f"{name}: run_backfill must call require_source_before_reset — without it a source outage "
        f"plus --reset empties the store"
    )
    assert src.index("require_source_before_reset") < src.index("guard_or_reset_backfill("), (
        f"{name}: the source check must precede the DELETE, not follow it"
    )


@pytest.mark.parametrize("name", sorted(WRITERS))
def test_the_game_date_load_precedes_the_destructive_guard(name):
    """The real invariant: nothing that can RAISE on a missing source may run after the DELETE."""
    src = _run_backfill_src(name)
    load_markers = [m for m in ("_load_game_dates_for_season", "_SEASON_DATES_SQL") if m in src]
    assert load_markers, f"{name}: could not find the game-date load in run_backfill"
    first_load = min(src.index(m) for m in load_markers)
    assert first_load < src.index("guard_or_reset_backfill("), (
        f"{name}: the game-date source is read AFTER the guard that DELETEs — that is the exact "
        f"ordering that emptied player_sequential_posteriors on 2026-07-31"
    )


def test_an_empty_source_refuses_rather_than_deleting():
    with pytest.raises(SystemExit) as e:
        require_source_before_reset([], season=2026, label="player-seq-backfill")
    msg = str(e.value)
    # the message must name the actual cause, or the next operator repeats the failed command
    assert "--s3" in msg and "LAKEHOUSE_DELTA_W1" in msg


def test_a_non_empty_source_proceeds():
    assert require_source_before_reset(["2026-04-01"], season=2026, label="x") is None
