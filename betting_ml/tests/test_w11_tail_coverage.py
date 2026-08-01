"""Tests for scripts/check_w11_tail_coverage.py — the current-slate guard for the three blocks
the six-block feature-store coverage gate cannot see (INC-37, 2026-08-01).

The whole value of this check is a THREE-WAY discrimination, and each leg has a real incident
behind it:

  - **BUILD_GAP fires** when the raw feed HAS the slate but the built feature table does not.
    That is the INC-37 fingerprint verbatim: `feature_pregame_weather_features` and
    `feature_pregame_public_betting_features` held 0 of 15 slate games because the W11 tail was
    built on a July-only game universe, while `check_feature_block_coverage` read a healthy 0.878
    (it excludes the anchor date, so it is a store-HISTORY guard, never a TODAY guard).
  - **FEED_PENDING stays SILENT** when neither the feed nor the table has the slate. The HP-umpire
    assignment posts in the afternoon, so a monitor that paged on an empty morning umpire block
    would page every single day and get muted — the same "don't cry wolf" requirement E11.27 and
    the injury feed-freshness carve-out are built on.
  - **PARTIAL fires** when the table is behind a feed that already has more.

ALERT tier (E11.7): `main()` must never exit non-zero without `--strict`, so a blank transparency
panel can never withhold a slate's predictions.

Fast-gate-safe: pure classifier + a mocked-IO main(); imports no `pipeline` module and does no IO.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _PROJECT_ROOT / "scripts" / "check_w11_tail_coverage.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_w11_tail_coverage", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


w11 = _load_module()


def _cov(block="weather", slate=15, raw=15, feature=15):
    return w11.BlockCoverage(block=block, slate_games=slate, raw_games=raw, feature_games=feature)


class TestVerdicts:
    def test_build_gap_is_the_inc37_fingerprint(self):
        """Raw has the slate, the built table has none — the exact 0/15 INC-37 shape."""
        c = _cov(block="weather", slate=15, raw=15, feature=0)
        assert c.verdict == "BUILD_GAP"
        assert c.is_problem

    def test_feed_pending_is_silent_not_a_defect(self):
        """An empty morning umpire block with no assignment posted yet must NOT page — that is
        the daily steady state, and paging on it is how a monitor gets muted."""
        c = _cov(block="umpire", slate=15, raw=0, feature=0)
        assert c.verdict == "FEED_PENDING"
        assert not c.is_problem

    def test_partial_when_the_table_lags_the_feed(self):
        c = _cov(block="umpire", slate=15, raw=10, feature=5)
        assert c.verdict == "PARTIAL"
        assert c.is_problem

    def test_ok_when_the_table_has_caught_up(self):
        assert _cov(raw=14, feature=14).verdict == "OK"
        # A table AHEAD of the current feed (carried from an earlier capture) is fine, not PARTIAL.
        assert _cov(raw=0, feature=15).verdict == "OK"

    def test_no_slate_is_not_a_problem(self):
        """An off-day (or a date before any games) must not read as a defect."""
        c = _cov(slate=0, raw=0, feature=0)
        assert c.verdict == "NO_SLATE"
        assert not c.is_problem

    def test_full_coverage_and_zero_coverage_are_opposite_verdicts(self):
        """Two-sided: the same block, same slate, only the built-table count differs."""
        assert _cov(raw=15, feature=15).verdict == "OK"
        assert _cov(raw=15, feature=0).verdict == "BUILD_GAP"


class TestBlocksRegistry:
    def test_covers_exactly_the_three_gate_blind_blocks(self):
        """These three and only these three — the six blocks in
        `_FEATURE_STORE_COVERAGE_BLOCKS` are already gated and must not be duplicated here."""
        assert {b[0] for b in w11.BLOCKS} == {"umpire", "weather", "public_betting"}

    def test_each_block_names_a_feature_table_and_its_raw_mirror(self):
        for block, feature_table, raw_table, raw_key in w11.BLOCKS:
            assert feature_table.startswith("feature_pregame_")
            assert raw_table and raw_key in ("game_pk", "game_date")


class TestMainIsAlertTier:
    def test_main_exits_zero_on_a_problem_without_strict(self):
        problem = [_cov(block="weather", slate=15, raw=15, feature=0)]
        with mock.patch.object(w11, "_fetch", return_value=problem), \
             mock.patch.object(sys, "argv", ["check_w11_tail_coverage.py", "--date", "2026-08-01"]):
            assert w11.main() == 0

    def test_strict_escalates_the_same_problem_to_exit_1(self):
        problem = [_cov(block="weather", slate=15, raw=15, feature=0)]
        with mock.patch.object(w11, "_fetch", return_value=problem), \
             mock.patch.object(sys, "argv",
                               ["check_w11_tail_coverage.py", "--date", "2026-08-01", "--strict"]):
            assert w11.main() == 1

    def test_clean_slate_exits_zero_in_both_modes(self):
        clean = [_cov(block=b, slate=15, raw=15, feature=15) for b, *_ in w11.BLOCKS]
        for argv in (["check_w11_tail_coverage.py", "--date", "2026-08-01"],
                     ["check_w11_tail_coverage.py", "--date", "2026-08-01", "--strict"]):
            with mock.patch.object(w11, "_fetch", return_value=clean), \
                 mock.patch.object(sys, "argv", argv):
                assert w11.main() == 0

    def test_a_read_failure_never_takes_a_slate_down(self):
        """An unevaluable check is loud, never silent — and never fatal outside --strict."""
        with mock.patch.object(w11, "_fetch", side_effect=RuntimeError("s3 unreachable")), \
             mock.patch.object(sys, "argv", ["check_w11_tail_coverage.py", "--date", "2026-08-01"]):
            assert w11.main() == 0
