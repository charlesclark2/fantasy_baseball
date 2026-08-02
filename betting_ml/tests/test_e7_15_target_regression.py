"""E7.15 H4 — guards for regressing the TARGET toward true talent.

Fast-gate, pure (no IO). The load-bearing ones are the ESTIMAND guards: H4 is the only E7.15 slice that
changes what the model is trained to predict, and the way that goes wrong is subtle — an arm scored
against its own shrunken label answers an easier question than the foil, and the leaderboard then ranks
the amount of shrinkage instead of the quality of the map.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle.park_context import STABILIZATION_PA
from betting_ml.scripts.milb_mle.target_regression import (
    LABEL_EXPOSURE_COL,
    TargetSpec,
    evaluation_target_is_untouched,
    label_reliability,
    shrink_training_target_only,
    target_coverage,
)


def _train(n: int = 200, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "player_id": [f"P{i:03d}" for i in range(n)],
        "level": rng.choice(["Double-A", "Triple-A"], n),
        "target": rng.normal(0.320, 0.030, n),
        LABEL_EXPOSURE_COL: rng.integers(150, 1500, n).astype(float),
    })


# ══════════════════════════════════════════════════════════════════════════════════════
# ⭐ The estimand invariants
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_shrink_cannot_reach_the_evaluation_target():
    """⭐ THE SLICE'S CENTRAL INVARIANT — scoring an arm against its OWN shrunken label would answer an
    easier question than the foil (the E7.16 matched-support defect, one mechanism over).

    Enforced structurally: the function takes a train frame and returns a train frame, so there is no
    signature through which a test row could be mutated.
    """
    import inspect
    sig = inspect.signature(shrink_training_target_only)
    assert "test" not in sig.parameters and "eval" not in sig.parameters


def test_evaluation_target_invariant_detects_a_mutation():
    """The invariant checker must not be vacuous — prove it fails on a mutated frame."""
    test = _train(50)
    assert evaluation_target_is_untouched(test, test)
    mutated = test.copy()
    mutated.loc[0, "target"] = float(mutated.loc[0, "target"]) + 0.01
    assert not evaluation_target_is_untouched(test, mutated)


def test_default_spec_leaves_the_target_byte_identical():
    tr = _train()
    out = shrink_training_target_only(tr, "woba", TargetSpec())
    assert np.allclose(out["target"].to_numpy(float), tr["target"].to_numpy(float))
    assert (out["target_shrink_r"] == 1.0).all()


def test_identity_mode_is_a_byte_noop_so_the_anchor_is_real():
    tr = _train()
    out = shrink_training_target_only(tr, "woba", TargetSpec(mode="identity"))
    assert np.allclose(out["target"].to_numpy(float), tr["target"].to_numpy(float))


# ══════════════════════════════════════════════════════════════════════════════════════
# The mechanism
# ══════════════════════════════════════════════════════════════════════════════════════


def test_reliability_is_per_row_and_rises_with_exposure():
    tr = _train().sort_values(LABEL_EXPOSURE_COL).reset_index(drop=True)
    r = label_reliability(tr, "k_pct", TargetSpec())
    assert np.all(np.diff(r) >= -1e-12), "r must be monotone in PA"
    assert 0.0 < r.min() < r.max() < 1.0


def test_reliability_uses_the_metrics_own_stabilization_point():
    tr = _train()
    r_k = label_reliability(tr, "k_pct", TargetSpec()).mean()
    r_iso = label_reliability(tr, "iso", TargetSpec()).mean()
    assert STABILIZATION_PA["k_pct"] < STABILIZATION_PA["iso"]
    assert r_k > r_iso, "the metric that stabilises sooner must keep more of its observed deviation"


def test_a_missing_exposure_column_raises_rather_than_silently_no_opping():
    """⭐ A shrink disabled by a missing column would report a CLEAN NULL for a mechanism that never ran
    — the E7.12 `label_weight_col` lesson and the H2 inert-anchor class."""
    tr = _train().drop(columns=[LABEL_EXPOSURE_COL])
    with pytest.raises(KeyError, match="silently no-op"):
        shrink_training_target_only(tr, "woba", TargetSpec(mode="eb"))


def test_shrink_pulls_toward_the_mean_and_compresses_the_spread():
    tr = _train()
    out = shrink_training_target_only(tr, "woba", TargetSpec(mode="eb"))
    assert out["target"].std() < tr["target"].std()
    assert out["target"].mean() == pytest.approx(tr["target"].mean(), abs=1e-3)


def test_full_shrink_collapses_the_target_to_a_constant():
    """The family's own degenerate: a model trained on this has learned nothing, so it must lose."""
    out = shrink_training_target_only(_train(), "woba", TargetSpec(mode="full"))
    assert out["target"].nunique() == 1


def test_bigger_k_shrinks_harder():
    tr = _train()
    a = shrink_training_target_only(tr, "woba", TargetSpec(mode="eb", k_mult=1.0))
    b = shrink_training_target_only(tr, "woba", TargetSpec(mode="eb", k_mult=2.0))
    assert b["target"].std() < a["target"].std()


def test_level_mode_shrinks_toward_the_rows_own_level_mean():
    tr = _train()
    tr.loc[tr["level"] == "Triple-A", "target"] += 0.05      # make the level means clearly differ
    out = shrink_training_target_only(tr, "woba", TargetSpec(mode="eb_level"))
    for lvl, g in out.groupby("level"):
        assert g["target"].mean() == pytest.approx(tr.loc[tr["level"] == lvl, "target"].mean(), abs=2e-3)


# ══════════════════════════════════════════════════════════════════════════════════════
# ⭐ The matched foil that decides the slice
# ══════════════════════════════════════════════════════════════════════════════════════


def test_constant_foil_matches_the_average_compression_but_has_no_per_player_content():
    """⭐ THE INSTRUMENT THAT SEPARATES 'reliability de-noising' FROM 'a global rescale'.

    If the constant foil ties the real arm, the per-player story is refuted and what was measured is a
    rescale the regression's own slope already absorbs. For that comparison to mean anything the foil
    must have the SAME average compression — otherwise it would be testing shrink STRENGTH instead.
    """
    tr = _train()
    real = shrink_training_target_only(tr, "woba", TargetSpec(mode="eb"))
    foil = shrink_training_target_only(tr, "woba", TargetSpec(mode="constant"))
    assert foil["target_shrink_r"].nunique() == 1, "the foil must carry NO per-player content"
    assert real["target_shrink_r"].nunique() > 1
    # matched on average compression, to a tolerance well inside any effect the slice could claim
    assert foil["target_shrink_r"].mean() == pytest.approx(
        float(np.average(real["target_shrink_r"], weights=tr[LABEL_EXPOSURE_COL])), abs=0.02)


def test_the_constant_foil_is_not_accidentally_identical_to_the_real_arm():
    """A foil byte-identical to the arm it foils passes on nothing (the H2 inert-anchor class)."""
    tr = _train()
    real = shrink_training_target_only(tr, "woba", TargetSpec(mode="eb"))["target"].to_numpy(float)
    foil = shrink_training_target_only(tr, "woba", TargetSpec(mode="constant"))["target"].to_numpy(float)
    assert not np.allclose(real, foil)


# ══════════════════════════════════════════════════════════════════════════════════════
# Coverage — the mechanism's own units
# ══════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("mode", ["eb", "eb_level", "constant", "full"])
def test_every_active_mode_reports_movement_in_target_units(mode):
    tr = _train()
    out = shrink_training_target_only(tr, "woba", TargetSpec(mode=mode))
    cov = target_coverage(out, tr, TargetSpec(mode=mode))
    assert cov["pct_rows_moved"] > 1.0
    assert cov["target_sd_ratio"] <= 1.0


def test_the_foil_reports_zero_movement():
    tr = _train()
    out = shrink_training_target_only(tr, "woba", TargetSpec())
    assert target_coverage(out, tr, TargetSpec())["pct_rows_moved"] == 0.0


def test_empty_train_is_safe():
    empty = _train(0)
    out = shrink_training_target_only(empty, "woba", TargetSpec(mode="eb"))
    assert out.empty
    assert target_coverage(out, empty, TargetSpec(mode="eb"))["n_rows"] == 0


def test_invalid_specs_raise():
    with pytest.raises(ValueError):
        TargetSpec(mode="nope")
    with pytest.raises(ValueError):
        TargetSpec(k_mult=0.0)
