"""Tests for Story E1.6 — cross-era run-environment regime weighting."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.utils import run_env_regime as rer
from betting_ml.utils.run_env_regime import (
    REGIME_WEIGHT_COLUMN, attach_regime_weight, compute_regime_weights, season_regime_profile,
    season_regime_weights,
)

# Real per-season run environment (level, spread) from mart_game_results 2016-2026.
_REAL = pd.DataFrame({
    "avg_total_runs": {2016: 8.955, 2017: 9.293, 2018: 8.897, 2019: 9.661, 2020: 9.292,
                       2021: 9.061, 2022: 8.566, 2023: 9.230, 2024: 8.786, 2025: 8.895, 2026: 8.939},
    "std_total_runs": {2016: 4.486, 2017: 4.526, 2018: 4.532, 2019: 4.760, 2020: 4.553,
                       2021: 4.518, 2022: 4.394, 2023: 4.583, 2024: 4.312, 2025: 4.594, 2026: 4.484},
})


def _synth_games():
    rows = []
    for yr in _REAL.index:
        for _ in range(50):
            rows.append({"game_year": yr, "game_date": f"{yr}-06-15", "total_runs": 9.0})
    return pd.DataFrame(rows)


class TestProfile:
    def test_emits_level_and_spread(self):
        df = pd.DataFrame({"game_year": [2021, 2021, 2022, 2022],
                           "total_runs": [8, 10, 7, 9]})
        prof = season_regime_profile(df)
        assert list(prof.columns) == ["avg_total_runs", "std_total_runs"]
        assert prof.loc[2021, "avg_total_runs"] == 9.0

    def test_contact_axis_added_when_present(self):
        df = pd.DataFrame({"game_year": [2021, 2021], "total_runs": [8, 10],
                           "league_x": [0.32, 0.34]})
        prof = season_regime_profile(df, contact_cols=["league_x"])
        assert "avg_league_x" in prof.columns


class TestWeights:
    def test_regime_not_time_ordered(self):
        w = season_regime_weights(_REAL, target_season=2026, trailing=2)
        # 2016 (on-regime) must out-weight 2023 (trained-on but off-regime) and 2019 (juiced)
        assert w[2016] > w[2023] > w[2019]
        assert w[2016] > 0.7        # on-regime
        assert w[2019] < 0.3        # peak juiced ball, heavily down-weighted

    def test_weights_bounded(self):
        w = season_regime_weights(_REAL, target_season=2026)
        assert (w >= rer.MIN_WEIGHT - 1e-9).all() and (w <= 1.0 + 1e-9).all()
        assert np.isclose(w.max(), 1.0)

    def test_trailing_centroid_is_leakage_safe(self):
        # the centroid for 2026 uses only seasons < 2026
        z = rer._standardize(_REAL)
        cen2 = rer.trailing_centroid(z, 2026, trailing=2)
        manual = z.loc[[2024, 2025]].mean(axis=0).to_numpy()
        assert np.allclose(cen2, manual)

    def test_bandwidth_controls_sharpness(self):
        tight = season_regime_weights(_REAL, 2026, bandwidth=0.5)
        wide = season_regime_weights(_REAL, 2026, bandwidth=3.0)
        # a wider kernel keeps off-regime seasons relatively higher
        assert wide[2019] > tight[2019]

    def test_earliest_season_falls_back(self):
        # target = earliest season has no prior seasons → must not crash, weights valid
        w = season_regime_weights(_REAL, target_season=int(_REAL.index.min()))
        assert (w > 0).all()


class TestPerGameAndAttach:
    def test_compute_regime_weights_per_game(self):
        df = _synth_games()
        prof = season_regime_profile(df.assign(total_runs=df["game_year"].map(_REAL["avg_total_runs"])))
        w = compute_regime_weights(df["game_date"], target_season=2026, profile=_REAL)
        assert len(w) == len(df)
        # a 2019 game must get a smaller weight than a 2016 game
        w2019 = w[df["game_year"].values == 2019][0]
        w2016 = w[df["game_year"].values == 2016][0]
        assert w2016 > w2019

    def test_attach_adds_canonical_column(self):
        df = _synth_games().assign(total_runs=lambda d: d["game_year"].map(_REAL["avg_total_runs"]))
        out = attach_regime_weight(df, target_season=2026)
        assert REGIME_WEIGHT_COLUMN in out.columns
        assert REGIME_WEIGHT_COLUMN not in df.columns          # no mutation
        assert (out[REGIME_WEIGHT_COLUMN] > 0).all()

    def test_canonical_constants_pinned(self):
        # drift guard (mirrors season_normalization parity): pin the contract surface
        assert rer.REGIME_WEIGHT_COLUMN == "regime_weight"
        assert rer.DEFAULT_TRAILING_SEASONS == 2
        assert 0.0 < rer.MIN_WEIGHT < 1.0
