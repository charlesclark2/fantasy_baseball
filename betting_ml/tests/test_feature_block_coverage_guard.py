"""Tests for scripts/check_feature_block_coverage.py — the served-feature-block coverage guard.

Guards the F2 / F2-recurrence incident (umpire z-scores collapsed to ~0% in served
feature_pregame_game_features on 2026-07-02 AND again 2026-07-03) while every other block +
the row count stayed intact. The classifier must fire DEGRADED on a normally-full block that
recently collapsed, SKIP a legitimately coverage-gapped block, and never false-fire on a
healthy block.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _PROJECT_ROOT / "scripts" / "check_feature_block_coverage.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_feature_block_coverage", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fbc = _load_module()


class TestClassify:
    def test_no_data(self):
        assert fbc._classify(None, 0.5) == "NO_DATA"
        assert fbc._classify(0.9, None) == "NO_DATA"

    def test_skipped_low_baseline(self):
        # Coverage-gapped block (baseline < WELL_COVERED) with no healthy history — a drop
        # can't be asserted → SKIPPED (hist_cov defaults to None / low).
        assert fbc._classify(base_cov=0.70, recent_cov=0.10) == "SKIPPED"
        assert fbc._classify(base_cov=0.70, recent_cov=0.10, hist_cov=0.72) == "SKIPPED"

    def test_degraded_is_the_umpire_signature(self):
        # base ~1.0 → recent ~0.08 (the observed regression) → collapsed.
        assert fbc._classify(base_cov=1.0, recent_cov=0.077) == "DEGRADED"

    def test_degraded_just_below_relative_floor(self):
        # recent just below 0.70 * base.
        assert fbc._classify(base_cov=1.0, recent_cov=0.69) == "DEGRADED"

    def test_ok_at_relative_floor(self):
        # Exactly at 0.70 * base is not a collapse.
        assert fbc._classify(base_cov=1.0, recent_cov=0.70) == "OK"

    def test_ok_healthy(self):
        assert fbc._classify(base_cov=0.98, recent_cov=0.98) == "OK"

    # ── INC-31: persistently-/born-dead block collapsed vs a healthy HISTORICAL baseline ──
    def test_collapsed_vs_history_rescued_from_skip(self):
        # Dead across the WHOLE trailing window (base_cov=0, recent_cov=0) so the trailing
        # check would SKIP — but it was ~99% historically → RESCUED to DEGRADED (the umpire
        # ext-table-break signature after played-slate values also went null).
        assert fbc._classify(base_cov=0.0, recent_cov=0.0, hist_cov=0.99) == "DEGRADED"

    def test_collapsed_vs_history_partial_trailing(self):
        # Trailing baseline weak (0.40) AND recent near-dead (0.05), healthy history → DEGRADED.
        assert fbc._classify(base_cov=0.40, recent_cov=0.05, hist_cov=0.97) == "DEGRADED"

    def test_no_false_fire_when_history_also_gapped(self):
        # A genuinely era-gapped block (never well covered, incl. history) stays SKIPPED.
        assert fbc._classify(base_cov=0.0, recent_cov=0.0, hist_cov=0.0) == "SKIPPED"
        assert fbc._classify(base_cov=0.60, recent_cov=0.10, hist_cov=0.55) == "SKIPPED"

    def test_no_false_fire_when_history_missing(self):
        # Early-season: no historical games (hist_cov=None) → cannot rescue → SKIPPED.
        assert fbc._classify(base_cov=0.0, recent_cov=0.0, hist_cov=None) == "SKIPPED"

    def test_recovered_block_not_flagged_vs_history(self):
        # Historically healthy AND recently healthy (base weak only by coincidence) — recent
        # is NOT below 70% of history → not a collapse.
        assert fbc._classify(base_cov=0.80, recent_cov=0.95, hist_cov=0.98) == "SKIPPED"


def _run_main(present_cols, base_n, recent_n, block_counts, argv, capsys, hist_n=None):
    """Run main() with a mocked cursor. `block_counts` maps block-name -> (base_notnull,
    recent_notnull) OR (hist_notnull, base_notnull, recent_notnull). `present_cols` = the
    columns information_schema reports present. `hist_n` defaults to base_n (a populated
    historical window). Returns (return_code, stdout_text)."""
    if hist_n is None:
        hist_n = base_n
    blocks = {b: c for b, c in fbc._BLOCKS.items()
              if c.lower() in {p.lower() for p in present_cols}}
    # Column order MUST match the SELECT in main(): hist_n, base_n, recent_n, then per block
    # hist_{b}, base_{b}, recent_{b}.
    description = [("hist_n",), ("base_n",), ("recent_n",)]
    rowvals = [hist_n, base_n, recent_n]
    for b in blocks:
        description += [(f"hist_{b}",), (f"base_{b}",), (f"recent_{b}",)]
        vals = block_counts.get(b, (base_n, recent_n))
        if len(vals) == 2:               # (base, recent) → healthy history
            bc, rc = vals
            hc = hist_n
        else:                            # (hist, base, recent)
            hc, bc, rc = vals
        rowvals += [hc, bc, rc]

    cur = mock.MagicMock()
    cur.fetchall.return_value = [(c,) for c in present_cols]   # _present_columns
    cur.description = description
    cur.fetchone.return_value = tuple(rowvals)                 # coverage query
    conn = mock.MagicMock()
    conn.cursor.return_value = cur
    with mock.patch.object(fbc, "get_snowflake_connection", return_value=conn), \
         mock.patch.object(sys, "argv", ["check_feature_block_coverage.py", *argv]):
        rc = fbc.main()
    return rc, capsys.readouterr().out


_ALL_COLS = list(fbc._BLOCKS.values())


class TestMain:
    def _healthy_counts(self, base_n, recent_n):
        return {b: (base_n, recent_n) for b in fbc._BLOCKS}   # every block ~100%

    def test_umpire_collapse_non_strict_alerts_but_exits_zero(self, capsys, caplog):
        counts = self._healthy_counts(100, 20)
        counts["umpire"] = (100, 2)   # base 1.0 → recent 0.10 → DEGRADED
        with caplog.at_level("WARNING"):
            rc, out = _run_main(_ALL_COLS, 100, 20, counts,
                                ["--env", "prod", "--date", "2026-07-03"], capsys)
        assert rc == 0
        assert "feature_block_min_cov_ratio=" in out
        assert "ALERT" in caplog.text and "umpire" in caplog.text

    def test_umpire_collapse_strict_halts(self, capsys, caplog):
        counts = self._healthy_counts(100, 20)
        counts["umpire"] = (100, 2)
        with caplog.at_level("ERROR"):
            rc, out = _run_main(_ALL_COLS, 100, 20, counts,
                                ["--env", "prod", "--date", "2026-07-03", "--strict"], capsys)
        assert rc == 1
        assert "HALT" in caplog.text

    def test_all_healthy_passes(self, capsys):
        counts = self._healthy_counts(100, 20)
        rc, out = _run_main(_ALL_COLS, 100, 20, counts,
                            ["--env", "prod", "--date", "2026-07-03", "--strict"], capsys)
        assert rc == 0
        assert "feature_block_min_cov_ratio=1.0000" in out

    def test_coverage_gapped_block_is_skipped_not_degraded(self, capsys, caplog):
        # A block that is coverage-gapped ACROSS ALL windows (history included, e.g. odds
        # market_bookmaker_count ~0.6-0.7 by tier) must be SKIPPED even if recent is far lower,
        # and must NOT HALT under --strict. (hist 0.55 < WELL_COVERED → no rescue.)
        counts = self._healthy_counts(100, 20)
        counts["odds_metadata"] = (55, 60, 2)   # hist 0.55, base 0.60 (gapped) → recent 0.10
        with caplog.at_level("ERROR"):
            rc, out = _run_main(_ALL_COLS, 100, 20, counts,
                                ["--env", "prod", "--date", "2026-07-03", "--strict"], capsys)
        assert rc == 0   # gapped baseline + gapped history is never asserted

    def test_absent_column_is_skipped_gracefully(self, capsys, caplog):
        # If the umpire column is absent from the store, it is skipped with a warning,
        # not a crash — and the run still passes on the remaining healthy blocks.
        present = [c for c in _ALL_COLS if c != "ump_accuracy_zscore"]
        counts = self._healthy_counts(100, 20)
        with caplog.at_level("WARNING"):
            rc, out = _run_main(present, 100, 20, counts,
                                ["--env", "prod", "--date", "2026-07-03", "--strict"], capsys)
        assert rc == 0
        assert "umpire" in caplog.text and "absent" in caplog.text

    def test_persistently_dead_block_alarms_vs_history(self, capsys, caplog):
        # INC-31 blind spot: umpire dead across the WHOLE trailing window (base 0, recent 0)
        # would be SKIPPED by the trailing-baseline check alone — but it was 99% historically,
        # so it must now ALARM (DEGRADED) and HALT under --strict.
        counts = self._healthy_counts(100, 20)
        counts["umpire"] = (99, 0, 0)   # (hist 0.99, base 0.0, recent 0.0)
        with caplog.at_level("ERROR"):
            rc, out = _run_main(_ALL_COLS, 100, 20, counts,
                                ["--env", "prod", "--date", "2026-07-09", "--strict"], capsys,
                                hist_n=100)
        assert rc == 1
        assert "HALT" in caplog.text
        assert "umpire" in caplog.text and "history" in caplog.text.lower()

    def test_born_dead_without_history_stays_skipped(self, capsys, caplog):
        # A block dead everywhere (incl. history) is genuinely coverage-gapped → SKIPPED, no HALT.
        counts = self._healthy_counts(100, 20)
        counts["umpire"] = (0, 0, 0)
        with caplog.at_level("ERROR"):
            rc, out = _run_main(_ALL_COLS, 100, 20, counts,
                                ["--env", "prod", "--date", "2026-07-09", "--strict"], capsys,
                                hist_n=100)
        assert rc == 0

    def test_insufficient_games_is_benign(self, capsys, caplog):
        # Empty windows (feature store not fresh) → benign ALERT, never a HALT.
        counts = self._healthy_counts(0, 0)
        with caplog.at_level("WARNING"):
            rc, out = _run_main(_ALL_COLS, 0, 0, counts,
                                ["--env", "prod", "--date", "2026-07-03", "--strict"], capsys)
        assert rc == 0
        assert "insufficient played games" in caplog.text
