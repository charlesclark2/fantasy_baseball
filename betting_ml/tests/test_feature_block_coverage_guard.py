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
        # Coverage-gapped block (baseline < WELL_COVERED) — a drop can't be asserted.
        assert fbc._classify(base_cov=0.70, recent_cov=0.10) == "SKIPPED"

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


def _run_main(present_cols, base_n, recent_n, block_counts, argv, capsys):
    """Run main() with a mocked cursor. `block_counts` maps block-name -> (base_notnull,
    recent_notnull). `present_cols` = the columns information_schema reports present.
    Returns (return_code, stdout_text)."""
    blocks = {b: c for b, c in fbc._BLOCKS.items()
              if c.lower() in {p.lower() for p in present_cols}}
    description = [("base_n",), ("recent_n",)]
    rowvals = [base_n, recent_n]
    for b in blocks:
        description += [(f"base_{b}",), (f"recent_{b}",)]
        bc, rc = block_counts.get(b, (base_n, recent_n))
        rowvals += [bc, rc]

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
        # A block whose baseline is < 85% must be SKIPPED even if recent is far lower,
        # and must NOT HALT under --strict.
        counts = self._healthy_counts(100, 20)
        counts["odds_metadata"] = (60, 2)   # base 0.60 (gapped) → recent 0.10
        with caplog.at_level("ERROR"):
            rc, out = _run_main(_ALL_COLS, 100, 20, counts,
                                ["--env", "prod", "--date", "2026-07-03", "--strict"], capsys)
        assert rc == 0   # gapped baseline is never asserted

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

    def test_insufficient_games_is_benign(self, capsys, caplog):
        # Empty windows (feature store not fresh) → benign ALERT, never a HALT.
        counts = self._healthy_counts(0, 0)
        with caplog.at_level("WARNING"):
            rc, out = _run_main(_ALL_COLS, 0, 0, counts,
                                ["--env", "prod", "--date", "2026-07-03", "--strict"], capsys)
        assert rc == 0
        assert "insufficient played games" in caplog.text
