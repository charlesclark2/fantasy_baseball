"""Unit tests for the A1.10 feature_coverage_score helper in
scripts/predict_today.py (`scripts` is on pythonpath per pyproject)."""

import pandas as pd

from predict_today import _FEATURE_COVERAGE_BLOCKS, _feature_coverage_score


def _full_row() -> dict:
    """A row with every feature block populated."""
    row = {}
    for cols in _FEATURE_COVERAGE_BLOCKS.values():
        for c in cols:
            row[c] = 0.3
    return row


class TestFeatureCoverageScore:
    def test_all_blocks_present_is_one(self):
        df = pd.DataFrame([_full_row()])
        assert _feature_coverage_score(df, 0) == 1.0

    def test_no_blocks_present_is_zero(self):
        df = pd.DataFrame([{"unrelated_col": 1.0}])
        assert _feature_coverage_score(df, 0) == 0.0

    def test_partial_coverage_is_block_fraction(self):
        # Only the lineup block (2 cols) + odds block (1 col) populated -> 2/6.
        df = pd.DataFrame([{
            "home_avg_eb_woba": 0.3, "away_avg_eb_woba": 0.3,
            "over_prob_consensus": 0.5,
        }])
        assert _feature_coverage_score(df, 0) == round(2 / len(_FEATURE_COVERAGE_BLOCKS), 3)

    def test_block_with_one_null_side_is_not_covered(self):
        # A two-sided block needs BOTH sides non-null to count.
        row = _full_row()
        row["away_avg_eb_woba"] = None  # break the lineup block
        df = pd.DataFrame([row])
        expected = round((len(_FEATURE_COVERAGE_BLOCKS) - 1) / len(_FEATURE_COVERAGE_BLOCKS), 3)
        assert _feature_coverage_score(df, 0) == expected
