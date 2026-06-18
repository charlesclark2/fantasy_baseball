"""Tests for Epic E1.4 — PBO (CSCV) + Deflated Sharpe + the dashboard gates."""

from __future__ import annotations

import numpy as np
import pytest

from betting_ml.utils.overfitting import (
    DSR_CONFIDENCE, PBO_SHADOW_TO_LIVE, PBO_SHIP_TO_SHADOW, deflated_sharpe,
    pbo_cscv, render_overfitting_dashboard,
)


class TestPBO:
    def test_pure_noise_pbo_near_half(self):
        rng = np.random.default_rng(0)
        perf = rng.standard_normal((200, 20))   # configs differ only by noise
        r = pbo_cscv(perf, n_splits=10, max_combos=200)
        assert 0.30 < r.pbo < 0.70

    def test_real_edge_low_pbo(self):
        rng = np.random.default_rng(1)
        perf = rng.standard_normal((200, 20)) * 0.5
        perf[:, 0] += 0.8                        # config 0 persistently best
        r = pbo_cscv(perf, n_splits=10, max_combos=200)
        assert r.pbo < PBO_SHADOW_TO_LIVE
        assert r.ships_to_shadow and r.clears_live_pbo

    def test_higher_is_better_flag(self):
        rng = np.random.default_rng(2)
        loss = rng.standard_normal((120, 8)) * 0.5
        loss[:, 3] -= 0.7                        # config 3 has the LOWEST loss (best)
        r = pbo_cscv(loss, higher_is_better=False, n_splits=8, max_combos=100)
        assert r.pbo < 0.5

    def test_combos_capped(self):
        rng = np.random.default_rng(3)
        perf = rng.standard_normal((300, 5))
        r = pbo_cscv(perf, n_splits=20, max_combos=50)
        assert r.n_combos <= 50

    def test_requires_two_configs(self):
        with pytest.raises(ValueError):
            pbo_cscv(np.zeros((100, 1)))


class TestDeflatedSharpe:
    def test_more_trials_deflate_harder(self):
        rng = np.random.default_rng(0)
        ret = rng.normal(0.05, 0.1, 500)
        few = deflated_sharpe(ret, n_trials=5)
        many = deflated_sharpe(ret, n_trials=5000)
        assert many.sr0 > few.sr0
        assert many.dsr <= few.dsr

    def test_no_edge_fails_live(self):
        rng = np.random.default_rng(1)
        ret = rng.normal(0.0, 0.1, 500)
        d = deflated_sharpe(ret, n_trials=100)
        assert d.dsr < DSR_CONFIDENCE
        assert not d.passes_live

    def test_strong_edge_passes_live(self):
        rng = np.random.default_rng(2)
        ret = rng.normal(0.06, 0.1, 600)
        d = deflated_sharpe(ret, n_trials=5)
        assert d.passes_live

    def test_trial_sharpes_set_variance(self):
        rng = np.random.default_rng(3)
        ret = rng.normal(0.03, 0.1, 400)
        trials = list(rng.normal(0.0, 0.2, 50))
        d = deflated_sharpe(ret, n_trials=50, trial_sharpes=trials)
        assert d.var_trials_sr > 0
        assert 0.0 <= d.dsr <= 1.0

    def test_too_few_obs_raises(self):
        with pytest.raises(ValueError):
            deflated_sharpe([0.1, 0.2], n_trials=10)


class TestDashboard:
    def test_verdicts(self):
        rng = np.random.default_rng(0)
        good = pbo_cscv(np.concatenate([rng.standard_normal((100, 6)) * 0.4 +
                                        np.r_[1.0, np.zeros(5)], ], axis=0), n_splits=8, max_combos=50)
        ret = rng.normal(0.06, 0.1, 600)
        dsr = deflated_sharpe(ret, n_trials=4)
        md = render_overfitting_dashboard([
            {"strategy": "live-ready", "stage": "proposed", "pbo": good, "dsr": dsr, "live_clv": True},
            {"strategy": "no-pbo", "stage": "proposed"},
        ])
        assert "LIVE-eligible" in md
        assert "NO PBO ON RECORD" in md
        assert str(PBO_SHIP_TO_SHADOW) in md

    def test_shadow_only_when_no_dsr(self):
        rng = np.random.default_rng(5)
        perf = rng.standard_normal((120, 10)) * 0.4
        perf[:, 0] += 0.9
        good = pbo_cscv(perf, n_splits=8, max_combos=80)
        md = render_overfitting_dashboard([
            {"strategy": "pbo-only", "stage": "proposed", "pbo": good},
        ])
        assert "SHADOW-eligible" in md
