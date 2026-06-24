"""E13.11 — exact linear SHAP for the glm_elasticnet (v6 de-leaked) home_win champion.

The v6 home_win champion is a Pipeline(StandardScaler, LogisticRegression) wrapped in
PlattCalibratedLinearClassifier, NOT an XGBoost model. shap.TreeExplainer (the v5 path)
throws on a linear model, which would silently degrade every home_win pick explanation to
'deferred'. These tests lock the dispatch + the exactness of the linear attribution so the
production explanations stay populated and leak-aware after the champion swap.
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from betting_ml.utils.calibrated_classifier import (
    PlattCalibratedLinearClassifier,
    PlattCalibratedXGBClassifier,
)
from betting_ml.utils.pick_explanations import (
    build_pick_explanations,
    home_win_is_linear,
    home_win_linear_shap,
)

FEAT_COLS = ["elo_diff", "home_bp_eb_xwoba", "pythagorean_win_exp_diff", "home_avg_xwoba_30d"]


def _fit_v6_home_win(seed: int = 0) -> tuple[PlattCalibratedLinearClassifier, np.ndarray]:
    """Mirror the bake-off glm_elasticnet recipe + the Platt wrapper used at serve time."""
    rng = np.random.default_rng(seed)
    n, p = 400, len(FEAT_COLS)
    X = rng.normal(size=(n, p))
    # a real (linear) signal so coefficients are non-degenerate
    logits = 1.3 * X[:, 0] - 0.9 * X[:, 1] + 0.6 * X[:, 2]
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-logits))).astype(int)

    pipeline = make_pipeline(
        StandardScaler(),
        LogisticRegression(penalty="elasticnet", l1_ratio=0.5, C=0.5,
                           solver="saga", max_iter=3000, random_state=seed),
    )
    pipeline.fit(X, y)
    raw = pipeline.predict_proba(X)[:, 1]
    platt = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    platt.fit(raw.reshape(-1, 1), y)
    return PlattCalibratedLinearClassifier(pipeline, platt), X


def test_dispatch_detects_linear_vs_tree():
    clf, _ = _fit_v6_home_win()
    assert home_win_is_linear(clf) is True

    # a stand-in for the v5 XGBoost wrapper (has .xgb_classifier) must NOT be linear
    class _FakeXGB:
        n_features_in_ = len(FEAT_COLS)

        def predict_proba(self, X):  # pragma: no cover - not exercised here
            return np.zeros((len(X), 2))

    fake_wrapper = PlattCalibratedXGBClassifier.__new__(PlattCalibratedXGBClassifier)
    fake_wrapper.xgb_classifier = _FakeXGB()
    fake_wrapper.calibrator = None
    assert home_win_is_linear(fake_wrapper) is False


def test_linear_shap_is_exact_and_reconstructs_logit():
    clf, X = _fit_v6_home_win()
    res = home_win_linear_shap(clf, X, FEAT_COLS)
    assert res is not None, "linear SHAP must not defer on a well-formed glm pipeline"
    contribs, base = res
    assert contribs.shape == X.shape

    # Σ contributions + base == the model's decision_function (the logit) for every row.
    pipe = clf.linear_pipeline
    scaler = pipe.named_steps["standardscaler"]
    logreg = pipe.named_steps["logisticregression"]
    expected_logit = logreg.decision_function(scaler.transform(X))
    np.testing.assert_allclose(contribs.sum(axis=1) + base, expected_logit, atol=1e-6)


def test_build_pick_explanations_populates_linear_home_win():
    clf, X = _fit_v6_home_win()
    payloads = build_pick_explanations(
        served_tier="post_lineup", top_n=3,
        clf_hw=clf, X_clf=X[:5].astype(np.float32), hw_feat_cols=FEAT_COLS,
    )
    assert len(payloads) == 5
    hw = payloads[0]["targets"]["home_win"]
    # the whole point of E13.11: home_win explanations are populated (not 'deferred')
    assert hw["method"] == "linear_shap_exact"
    assert hw["drivers"], "home_win drivers must be non-empty for the linear champion"
    # the leak feature is allowed to appear but must not be the ONLY signal — elo / pythagorean
    # (the real E1.7 signal) should be representable; assert drivers reference contract features.
    assert all(d["feature"] in FEAT_COLS for d in hw["drivers"])


def test_n_features_in_matches_pipeline():
    clf, _ = _fit_v6_home_win()
    assert clf.n_features_in_ == len(FEAT_COLS)
