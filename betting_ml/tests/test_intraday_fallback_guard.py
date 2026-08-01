"""Tests for scripts/check_intraday_fallback.py — the E11.27 per-slate intraday_fallback
monitor (the silent-degrade blind-spot closer, E11.24 §8 / INC-35).

Guards the "don't cry wolf" three-way discrimination the story requires:
  - fires on a SLATE-WIDE / high-share intraday_fallback slate, or any feature_store=0 tier
    (the phase-2b tz-incident fingerprint, independent of the fallback share — 7/24 fell through
    entirely via 'intraday_assembly' with ZERO 'intraday_fallback' rows)
  - stays SILENT on a clean slate
  - stays SILENT on a CHRONIC single-game-fallback slate (the ~1/slate steady-state since INC-35)

main() must ALERT-but-always-exit-0 — this monitor has no --strict escalation; it is ALERT-tier,
never HALT (CLAUDE.md E11.7 op→tier map).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _PROJECT_ROOT / "scripts" / "check_intraday_fallback.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_intraday_fallback", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


cif = _load_module()


def _clean(tier: str = "post_lineup", n: int = 15) -> "cif.TierFallbackStat":
    """A tier that passes every check: fully served from the feature store."""
    return cif.TierFallbackStat(
        tier=tier, n=n, n_feature_store=n, n_intraday_fallback=0, n_intraday_assembly=0,
    )


def _chronic(tier: str = "morning", n: int = 15) -> "cif.TierFallbackStat":
    """The INC-35 steady-state: one game/slate hasn't posted its lineup/starter yet."""
    return cif.TierFallbackStat(
        tier=tier, n=n, n_feature_store=n - 1, n_intraday_fallback=1, n_intraday_assembly=0,
    )


class TestEvaluateTierThreeWayDiscrimination:
    def test_clean_slate_has_no_problems(self):
        assert cif.evaluate_tier(_clean()) == []

    def test_chronic_single_game_fallback_is_silent(self):
        # 1/15 = 6.7% share, well under both the count (3) and share (30%) floors.
        assert cif.evaluate_tier(_chronic()) == []

    def test_chronic_two_games_on_a_big_slate_is_still_silent(self):
        s = _chronic(n=16)
        s.n_feature_store = 14
        s.n_intraday_fallback = 2  # 12.5% share — still well under 30%
        assert cif.evaluate_tier(s) == []

    def test_slate_wide_high_share_fallback_fires(self):
        s = _clean()
        s.n_feature_store = 6
        s.n_intraday_fallback = 9  # 9/15 = 60% — count and share both cross the floor
        probs = cif.evaluate_tier(s)
        assert any("intraday_fallback" in p and "INC-35" in p for p in probs)

    def test_count_floor_alone_does_not_fire_below_share_floor(self):
        # 3 fallback games on a 20-game slate = 15% share — below FALLBACK_ALERT_SHARE (30%).
        s = cif.TierFallbackStat(tier="morning", n=20, n_feature_store=17,
                                  n_intraday_fallback=3, n_intraday_assembly=0)
        assert cif.evaluate_tier(s) == []

    def test_share_floor_alone_does_not_fire_below_count_floor(self):
        # 2/5 = 40% share but only 2 games — below FALLBACK_ALERT_COUNT (3).
        s = cif.TierFallbackStat(tier="morning", n=5, n_feature_store=3,
                                  n_intraday_fallback=2, n_intraday_assembly=0)
        assert cif.evaluate_tier(s) == []

    def test_too_small_slate_is_not_assessed(self):
        s = _clean(n=3)  # < MIN_GAMES_FOR_CHECK
        s.n_feature_store = 0
        s.n_intraday_fallback = 3  # would be 100% fallback, but n too small → skipped
        assert cif.evaluate_tier(s) == []

    def test_feature_store_zero_fires_even_with_zero_fallback_rows(self):
        # The 7/24 signature: the tier fell through ENTIRELY to 'intraday_assembly' — ZERO
        # 'intraday_fallback' rows, so a fallback-share-only check would have missed this.
        s = cif.TierFallbackStat(tier="morning", n=15, n_feature_store=0,
                                  n_intraday_fallback=0, n_intraday_assembly=15)
        probs = cif.evaluate_tier(s)
        assert any("feature_store=0" in p for p in probs)

    def test_feature_store_zero_fires_with_all_fallback_rows(self):
        # The 7/25 signature: the tier fell through entirely, this time via 'intraday_fallback'.
        s = cif.TierFallbackStat(tier="morning", n=15, n_feature_store=0,
                                  n_intraday_fallback=15, n_intraday_assembly=0)
        probs = cif.evaluate_tier(s)
        assert len(probs) == 1  # feature_store=0 reports ONE problem, not an overlapping second
        assert "feature_store=0" in probs[0]

    def test_high_share_fallback_below_serious_count_floor_alone_is_silent(self):
        # A 6-game light slate, 2 on fallback = 33% share (over the share floor) but only
        # 2 games (under the count floor of 3) — both must clear, so this stays silent.
        s = cif.TierFallbackStat(tier="morning", n=6, n_feature_store=4,
                                  n_intraday_fallback=2, n_intraday_assembly=0)
        assert cif.evaluate_tier(s) == []


def _run_main(stats, argv, capsys, *, served_date="2026-07-25"):
    with mock.patch.object(cif, "_fetch_tier_stats", return_value=stats), \
         mock.patch.object(sys, "argv",
                           ["check_intraday_fallback.py", "--date", served_date, *argv]):
        rc = cif.main()
    return rc, capsys.readouterr().out


class TestMain:
    def test_clean_slate_passes_silently(self, capsys, caplog):
        with caplog.at_level("WARNING"):
            rc, out = _run_main([_clean()], ["--env", "prod"], capsys)
        assert rc == 0
        assert "ALERT" not in caplog.text
        assert "intraday_fallback_alert_count=0" in out

    def test_chronic_slate_passes_silently(self, capsys, caplog):
        with caplog.at_level("WARNING"):
            rc, out = _run_main([_chronic()], ["--env", "prod"], capsys)
        assert rc == 0
        assert "ALERT" not in caplog.text
        assert "intraday_fallback_alert_count=0" in out
        assert "intraday_fallback_chronic_games=1" in out

    def test_serious_slate_alerts_but_exits_zero(self, capsys, caplog):
        s = _clean()
        s.n_feature_store = 5
        s.n_intraday_fallback = 10  # 67% share, 10 games — well past both floors
        with caplog.at_level("WARNING"):
            rc, out = _run_main([s], ["--env", "prod"], capsys)
        assert rc == 0  # ALERT-tier — never HALTs, no --strict escalation exists
        assert "ALERT" in caplog.text and "INC-35" in caplog.text
        assert "intraday_fallback_alert_count=1" in out

    def test_feature_store_zero_slate_alerts_and_is_counted_separately(self, capsys, caplog):
        s = cif.TierFallbackStat(tier="morning", n=15, n_feature_store=0,
                                  n_intraday_fallback=0, n_intraday_assembly=15)
        with caplog.at_level("WARNING"):
            rc, out = _run_main([s], ["--env", "prod"], capsys)
        assert rc == 0
        assert "ALERT" in caplog.text and "feature_store=0" in caplog.text
        assert "intraday_fallback_alert_count=1" in out
        assert "intraday_fallback_zero_feature_store_tiers=1" in out

    def test_empty_slate_is_benign(self, capsys):
        rc, out = _run_main([], ["--env", "prod"], capsys)
        assert rc == 0
        assert "intraday_fallback_alert_count=0" in out

    def test_never_halts_even_on_multiple_serious_tiers(self, capsys, caplog):
        morning = cif.TierFallbackStat(tier="morning", n=15, n_feature_store=0,
                                        n_intraday_fallback=15, n_intraday_assembly=0)
        post_lineup = cif.TierFallbackStat(tier="post_lineup", n=15, n_feature_store=2,
                                            n_intraday_fallback=13, n_intraday_assembly=0)
        with caplog.at_level("WARNING"):
            rc, out = _run_main([morning, post_lineup], ["--env", "prod"], capsys)
        assert rc == 0
        assert "intraday_fallback_alert_count=2" in out
