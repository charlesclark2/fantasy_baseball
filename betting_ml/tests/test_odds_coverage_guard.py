"""Tests for scripts/check_odds_coverage.py — the durable odds-coverage DQ guard.

Guards the 2026-07-02 "bridge freeze" incident: mart_game_odds_bridge stalls with 0
has_odds rows for the current slate while mart_game_spine + mart_odds_outcomes stay
fresh, so predictions run market-blind with no error. The classifier must fire FREEZE
on that exact signature and NEVER on a books-haven't-posted-yet slate.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _PROJECT_ROOT / "scripts" / "check_odds_coverage.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_odds_coverage", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


coc = _load_module()


class TestClassify:
    def test_off_day(self):
        # No scheduled games → nothing to attach; benign.
        assert coc._classify(spine_games=0, odds_events=0, bridge_with_odds=0) == "OFF_DAY"

    def test_no_odds_yet_is_not_a_freeze(self):
        # Games exist but books have not posted → benign timing, NOT a freeze.
        assert coc._classify(spine_games=9, odds_events=0, bridge_with_odds=0) == "NO_ODDS_YET"

    def test_freeze_signature(self):
        # The incident: games AND odds exist but ZERO attached in the bridge.
        assert coc._classify(spine_games=9, odds_events=9, bridge_with_odds=0) == "FREEZE"

    def test_partial(self):
        # Below the 50% floor → partial coverage warning.
        assert coc._classify(spine_games=10, odds_events=10, bridge_with_odds=3) == "PARTIAL"

    def test_ok(self):
        assert coc._classify(spine_games=10, odds_events=10, bridge_with_odds=10) == "OK"

    def test_ok_at_floor(self):
        # Exactly at the floor counts as OK (>= min_coverage).
        assert coc._classify(spine_games=10, odds_events=10, bridge_with_odds=5) == "OK"


def _run_main(rows, argv, capsys):
    """Run check_odds_coverage.main() with a mocked Snowflake cursor returning `rows`
    (list of (d, spine_games, odds_events, bridge_games, bridge_with_odds) tuples).
    Returns (return_code, stdout_text)."""
    cur = mock.MagicMock()
    cur.description = [("d",), ("spine_games",), ("odds_events",),
                       ("bridge_games",), ("bridge_with_odds",)]
    cur.fetchall.return_value = rows
    conn = mock.MagicMock()
    conn.cursor.return_value = cur
    with mock.patch.object(coc, "get_snowflake_connection", return_value=conn), \
         mock.patch.object(sys, "argv", ["check_odds_coverage.py", *argv]):
        rc = coc.main()
    return rc, capsys.readouterr().out


class TestMain:
    _FREEZE_ROWS = [
        ("2026-07-02", 9, 9, 0, 0),    # current slate — FREEZE
        ("2026-07-03", 13, 0, 0, 0),   # forward — NO_ODDS_YET
    ]

    def test_freeze_non_strict_alerts_but_exits_zero(self, capsys, caplog):
        # Default (ALERT-continue): never blocks serving.
        with caplog.at_level("WARNING"):
            rc, out = _run_main(self._FREEZE_ROWS, ["--env", "prod", "--date", "2026-07-02"], capsys)
        assert rc == 0
        assert "odds_coverage_score=0.0000" in out
        assert "ALERT" in caplog.text and "FREEZE" in caplog.text

    def test_freeze_strict_halts(self, capsys, caplog):
        # --strict promotes a current-slate FREEZE to a HALT (non-zero exit).
        with caplog.at_level("ERROR"):
            rc, out = _run_main(
                self._FREEZE_ROWS, ["--env", "prod", "--date", "2026-07-02", "--strict"], capsys
            )
        assert rc == 1
        assert "HALT" in caplog.text

    def test_healthy_slate_passes(self, capsys):
        rows = [("2026-07-02", 9, 9, 9, 9), ("2026-07-03", 13, 0, 0, 0)]
        rc, out = _run_main(rows, ["--env", "prod", "--date", "2026-07-02", "--strict"], capsys)
        assert rc == 0
        assert "odds_coverage_score=1.0000" in out

    def test_no_odds_yet_current_slate_is_not_a_halt(self, capsys):
        # Books have not posted for today yet → benign even under --strict.
        rows = [("2026-07-02", 9, 0, 0, 0)]
        rc, out = _run_main(rows, ["--env", "prod", "--date", "2026-07-02", "--strict"], capsys)
        assert rc == 0

    def test_off_day_scores_full(self, capsys):
        # No games today → score 1.0 (nothing to attach), never a failure.
        rows = [("2026-07-03", 13, 0, 0, 0)]
        rc, out = _run_main(rows, ["--env", "prod", "--date", "2026-07-02", "--strict"], capsys)
        assert rc == 0
        assert "odds_coverage_score=1.0000" in out
