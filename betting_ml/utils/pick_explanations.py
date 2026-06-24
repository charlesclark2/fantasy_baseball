"""Story 30.15 — per-pick feature attribution (explainable picks).

At SERVE TIME, compute per-game LOCAL feature contributions for each target's
prediction, reduce to the top-N signed drivers with human-readable labels, and
return a small JSON-serialisable payload the frontend can render as "why this
pick." This is PER-PICK, PER-GAME local attribution — distinct from:
  - influence_report.py  → GLOBAL permutation importance (what drives the model
                           overall), and
  - A2.5 _build_imputation_summary → which features were IMPUTED (a data
                           COMPLETENESS signal, not a contribution).

Method — exact SHAP for every target (no approximation):
  - home_win — dispatched by model class (home_win_is_linear):
      • XGBoost (v5): shap.TreeExplainer on the underlying XGBClassifier is
        native + exact.
      • glm_elasticnet (E1.9 de-leaked v6): exact linear SHAP, coef_j·z_j on the
        StandardScaler-standardized inputs (E[z]=0 by construction), base=intercept.
    Both are in margin (log-odds) space; the Platt calibrator is monotonic, so
    sign + ranking are preserved through calibration — i.e. a positive
    contribution pushes the calibrated P(home win) up.
  - run_diff / total_runs (NGBoost): NGBoost models the loc (mean) parameter as
    an ADDITIVE ensemble of sklearn DecisionTreeRegressors. SHAP is additive over
    an additive model, so summing per-stage TreeSHAP (scaled by the stage's
    learning-rate × scaling, restricted to that stage's column-subsample) yields
    EXACT SHAP for loc. We self-check additivity (Σcontrib ≈ loc − intercept) and
    fail safe to a 'deferred' payload on any mismatch — so this is safe to serve
    even where the NGBoost internals differ from what we validated.

HONESTY GUARD (Story 30.15 + [[feedback_no_auto_betting]] + the FAQ no-win-rate
rule): these attributions explain the MODEL's reasoning, NOT a betting edge. With
best_alpha=0 the posterior ≈ the market, so the payload is framed as "what our
model weighs," never "where the edge comes from." No win-rate / profit framing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.model_evaluation.analyze_feature_importance import _infer_feature_group

# Framing string stored alongside every payload so any consumer (API/frontend)
# inherits the honesty stance even if read in isolation.
MODEL_REASONING_DISCLAIMER = (
    "Shows which inputs most moved our model's prediction for this game — it "
    "explains the model's reasoning. The EV signal (edge) shown elsewhere reflects "
    "model probability vs. market probability; it is not a guarantee of profit."
)

# What each target's contribution pushes ON (units the frontend can phrase around).
_TARGET_OUTCOME = {
    "home_win": {"unit": "log_odds", "toward": "home win probability"},
    "total_runs": {"unit": "runs", "toward": "projected total runs"},
    "run_diff": {"unit": "runs", "toward": "home run differential"},
}

# Curated plain-English labels. Keyed by the home_/away_-STRIPPED stem (so one
# entry covers both sides; the side prefix is prepended by humanize_feature).
# This is a CURATED OVERLAY — humanize_feature() falls back to a generated label
# for anything not listed, so coverage of every possible top-N feature is total.
_STEM_LABELS: dict[str, str] = {
    # Bullpen / relief. NOTE: wOBA/xwOBA here are ALLOWED by the pitching staff, so
    # HIGHER = WORSE. Labels are phrased neutrally ("…wOBA allowed") so that pairing
    # with a raw-feature SHAP `direction` never reads backwards (a label saying
    # "quality" would imply higher=better and invert the meaning).
    "bullpen_eb_xwoba": "bullpen expected wOBA allowed",
    "bullpen_eb_woba": "bullpen wOBA allowed",
    "bullpen_eb_uncertainty": "bullpen estimate uncertainty",
    "bp_eb_xwoba": "bullpen expected wOBA allowed",
    "bp_eb_uncertainty": "bullpen estimate uncertainty",
    "bp_eb_coverage": "bullpen sample coverage",
    "team_sequential_bullpen_xwoba": "bullpen expected wOBA allowed (sequential)",
    "team_sequential_bullpen_woba": "bullpen wOBA allowed (sequential)",
    "bullpen_mu": "bullpen run-prevention",
    "bullpen_fip": "bullpen FIP",
    "bullpen_era": "bullpen ERA",
    "closer_available": "closer availability",
    "closer_used_prev_1d": "closer used yesterday",
    "reliever_availability_index": "bullpen availability",
    # Starting pitcher. Same allowed-not-quality convention as bullpen above.
    "starter_eb_xwoba": "starting pitcher expected wOBA allowed",
    "starter_eb_woba": "starting pitcher wOBA allowed",
    "starter_fip": "starting pitcher FIP",
    "starter_era": "starting pitcher ERA",
    "starter_xfip": "starting pitcher xFIP",
    "starter_k_pct": "starting pitcher strikeout rate",
    "starter_bb_pct": "starting pitcher walk rate",
    "starter_ip": "starting pitcher expected innings",
    "starter_days_rest": "starting pitcher rest",
    # Team offense / batting
    "off_woba": "team offense (wOBA)",
    "off_xwoba": "team offense (expected wOBA)",
    "off_wrc_plus": "team offense (wRC+)",
    "avg_woba": "lineup offense (wOBA)",
    "avg_xwoba": "lineup offense (expected wOBA)",
    "lineup_avg_woba_vs_cluster": "lineup vs. pitcher-type matchup",
    "lineup_avg_xwoba_vs_cluster": "lineup vs. pitcher-type matchup (expected)",
    # Ratings / records
    "elo": "team strength (ELO)",
    "elo_rating": "team strength (ELO)",
    "pythagorean_win_exp": "expected win pct (run-based)",
    "pythagorean_win_exp_diff": "expected win-pct edge (run-based)",
    "win_rate": "season win pct",
    "win_pct": "season win pct",
    # Park / weather / umpire
    "park_factor": "ballpark run environment",
    "park_run_factor": "ballpark run environment",
    "temp_f": "game-time temperature",
    "wind_speed": "wind speed",
    "wind_out": "wind blowing out",
    "ump_runs_zscore": "umpire run tendency",
    "ump_k_zscore": "umpire strikeout tendency",
    "elevation": "ballpark elevation",
}

# Higher-level family → friendly family name for grouping in the UI.
_FAMILY_LABELS = {
    "bullpen": "Bullpen",
    "team_offense": "Team offense",
    "rolling_batting": "Lineup offense",
    "platoon_splits": "Platoon matchup",
    "elo": "Team rating",
    "pythagorean": "Run-based rating",
    "season_record": "Season record",
    "park_weather_ump": "Park / weather / umpire",
    "lineup_archetype": "Lineup archetype",
    "market": "Market",
    "schedule": "Schedule / rest",
    "oaa": "Defense (OAA)",
    "injury": "Injuries",
}

_SIDE_PREFIX = {"home_": "Home ", "away_": "Away "}


def humanize_feature(name: str) -> tuple[str, str, str]:
    """(label, family_key, family_label) for a raw feature column.

    Guarantees a non-empty label for ANY input (curated overlay → generated
    fallback), so every feature that can land in a top-N list is covered.
    """
    side = ""
    stem = name
    for pfx, friendly in _SIDE_PREFIX.items():
        if name.startswith(pfx):
            side = friendly
            stem = name[len(pfx):]
            break

    base = _STEM_LABELS.get(stem)
    if base is None:
        # Generated fallback: drop trailing _diff/_zscore noise, prettify.
        pretty = stem
        for suf in ("_zscore", "_z", "_pct", "_diff"):
            if pretty.endswith(suf):
                pretty = pretty[: -len(suf)]
                break
        base = pretty.replace("_", " ").strip()
    label = f"{side}{base}".strip()

    fam_key = _infer_feature_group(name)
    # Substring rescue: _infer_feature_group only matches on PREFIX, so a mid-name
    # family signal (e.g. team_sequential_BULLPEN_xwoba) falls through to "other".
    # Catch the common families by substring before giving up.
    if fam_key == "other":
        low = name.lower()
        for needle, fk in (("bullpen", "bullpen"), ("_bp_", "bullpen"),
                           ("reliever", "bullpen"), ("closer", "bullpen"),
                           ("starter", "starter_x"), ("_sp_", "starter_x")):
            if needle in low:
                fam_key = fk
                break
    if fam_key.startswith("starter_"):
        fam_label = "Starting pitcher"  # _infer_feature_group emits starter_<sub> keys
    else:
        fam_label = _FAMILY_LABELS.get(fam_key, fam_key.replace("_", " ").title())
    return label, fam_key, fam_label


def _drivers_for_game(
    feat_cols: list[str], contribs: np.ndarray, target: str, top_n: int
) -> list[dict]:
    """Top-N positive + top-N negative signed contributions for one game."""
    toward = _TARGET_OUTCOME.get(target, {}).get("toward", "the prediction")
    order = np.argsort(contribs)  # ascending
    neg_idx = [i for i in order[:top_n] if contribs[i] < 0]
    pos_idx = [i for i in order[::-1][:top_n] if contribs[i] > 0]
    out: list[dict] = []
    for idx in list(pos_idx) + list(neg_idx):
        c = float(contribs[idx])
        label, fam_key, fam_label = humanize_feature(feat_cols[idx])
        out.append({
            "feature": feat_cols[idx],
            "label": label,
            "family": fam_label,
            "family_key": fam_key,
            "contribution": round(c, 5),
            "direction": "increases" if c > 0 else "decreases",
            "toward": toward,
        })
    # strongest-first regardless of sign
    out.sort(key=lambda d: abs(d["contribution"]), reverse=True)
    return out


def home_win_shap(clf, X: np.ndarray, feat_cols: list[str]) -> tuple[np.ndarray, float]:
    """Exact TreeSHAP for the home_win XGBClassifier (margin / log-odds space).

    `clf` is a PlattCalibratedXGBClassifier (has `.xgb_classifier`) or a raw
    XGBClassifier. Returns (per-game contributions [n, n_feat], base_value).
    """
    import shap

    booster_owner = getattr(clf, "xgb_classifier", clf)
    explainer = shap.TreeExplainer(booster_owner)
    sv = explainer.shap_values(X)
    sv = np.asarray(sv)
    if sv.ndim == 3:  # some shap versions return (n, n_feat, n_class)
        sv = sv[..., -1]
    base = explainer.expected_value
    base = float(np.ravel(base)[-1]) if np.ndim(base) else float(base)
    return sv, base


def _extract_linear_pipeline(clf):
    """Return (scaler_or_None, linear_estimator) for a glm_elasticnet home_win model.

    Accepts the PlattCalibratedLinearClassifier wrapper (.linear_pipeline /
    .pipeline), a bare sklearn Pipeline(StandardScaler, LogisticRegression), or a
    bare LogisticRegression. Returns None if no linear estimator is found.
    """
    target = getattr(clf, "linear_pipeline", None) or getattr(clf, "pipeline", None) or clf
    steps = getattr(target, "steps", None)
    if steps:  # an sklearn Pipeline → find the scaler + the estimator with coef_
        scaler = next((e for _, e in steps if hasattr(e, "scale_") and hasattr(e, "mean_")), None)
        linear = next((e for _, e in steps if hasattr(e, "coef_")), None)
        return (scaler, linear) if linear is not None else None
    if hasattr(target, "coef_"):  # a bare linear estimator (no scaler)
        return (None, target)
    return None


def home_win_is_linear(clf) -> bool:
    """True iff the home_win model is the glm_elasticnet (linear) v6 champion.

    XGBoost (v5) carries `.xgb_classifier`; the linear v6 exposes a pipeline with
    a `.coef_` estimator. Used to dispatch TreeSHAP vs exact linear SHAP.
    """
    if hasattr(clf, "xgb_classifier"):
        return False
    return _extract_linear_pipeline(clf) is not None


def home_win_linear_shap(clf, X: np.ndarray, feat_cols: list[str]) -> tuple[np.ndarray, float] | None:
    """Exact local SHAP for the glm_elasticnet home_win champion (margin/log-odds).

    For a standardized linear model logit(p) = intercept + Σ_j coef_j · z_j (where
    z = StandardScaler(X)), SHAP_j(x) = coef_j · (z_j − E[z_j]). The scaler centers
    the training set, so E[z_j] = 0 and SHAP_j = coef_j · z_j EXACTLY, with
    base_value = intercept. The Platt calibrator and the served TemperatureCalibrator
    are both monotonic, so a positive contribution pushes the calibrated P(home win)
    up — same guarantee the XGBoost TreeSHAP path documents.

    Self-checks additivity (Σcontrib + base ≈ decision_function) and returns None on
    any mismatch → caller emits a 'deferred' payload (fail safe, never blocks scoring).
    """
    pair = _extract_linear_pipeline(clf)
    if pair is None:
        return None
    scaler, linear = pair
    try:
        Xv = np.asarray(X, dtype=float)
        z = scaler.transform(Xv) if scaler is not None else Xv
        coef = np.asarray(linear.coef_, dtype=float).reshape(-1)
        if coef.shape[0] != z.shape[1]:
            return None
        contribs = z * coef[None, :]
        base = float(np.asarray(linear.intercept_, dtype=float).reshape(-1)[0])
        # additivity self-check: contributions + base must reconstruct the logit
        logit = z @ coef + base
        if not np.allclose(contribs.sum(axis=1) + base, logit, atol=1e-6):
            return None
        return contribs, base
    except Exception:
        return None


def ngboost_loc_shap(
    model, X: np.ndarray, feat_cols: list[str], loc_param_idx: int = 0
) -> tuple[np.ndarray, float] | None:
    """Exact additive TreeSHAP for an NGBoost regressor's loc parameter.

    NGBoost predicts loc additively: init_params[loc] − lr·Σ_k scaling_k ·
    tree_k(X[:, col_idxs_k]). SHAP is additive over additive models, so summing
    per-stage TreeSHAP (same lr·scaling factor, scattered back to the stage's
    sub-sampled columns) is EXACT SHAP for loc, with intercept = init_params[loc].

    Self-checks additivity (Σcontrib ≈ loc − intercept) and returns None on any
    failure → caller emits a 'deferred' payload (fail safe, never blocks scoring).
    """
    try:
        import shap

        n, p = X.shape
        contribs = np.zeros((n, p), dtype=float)
        for k in range(model.n_estimators):
            cols = model.col_idxs[k]
            learner = model.base_models[k][loc_param_idx]
            factor = -model.learning_rate * float(model.scalings[k])
            sv = np.asarray(shap.TreeExplainer(learner).shap_values(X[:, cols]))
            if sv.ndim == 1:
                sv = sv.reshape(n, -1)
            contribs[:, cols] += factor * sv

        intercept = float(model.init_params[loc_param_idx])
        loc = np.asarray(model.pred_dist(X).params["loc"], dtype=float)
        # additivity self-check: contributions must reconstruct loc − intercept
        if not np.allclose(contribs.sum(axis=1), loc - intercept, atol=1e-4):
            return None
        return contribs, intercept
    except Exception:
        return None


def _empty_target(target: str, method: str, note: str) -> dict:
    return {"method": method, "drivers": [], "note": note,
            "toward": _TARGET_OUTCOME.get(target, {}).get("toward", "")}


def build_pick_explanations(
    *,
    served_tier: str,
    top_n: int = 5,
    clf_hw=None, X_clf=None, hw_feat_cols=None,
    ngb_total=None, X_tot=None, tot_feat_cols=None,
    ngb_diff=None, X_diff=None, diff_feat_cols=None,
    # Story 22.4 — per-game sigma gate fields (lists parallel to model rows, or None)
    sigma_tiers: list[str] | None = None,
    abstain_reasons: list[str] | None = None,
    totals_ci_widths: list[float | None] | None = None,
    h2h_ci_widths: list[float | None] | None = None,
) -> list[dict]:
    """Per-game explanation payloads (one dict per game row, all targets).

    Returns list length == n_games; each item:
      {"served_tier", "disclaimer", "basis": "model_reasoning",
       "targets": {"home_win": {...}, "total_runs": {...}, "run_diff": {...}}}
    Any target whose model/inputs are absent is simply omitted from "targets".
    """
    n = None
    for X in (X_clf, X_tot, X_diff):
        if X is not None:
            n = len(X)
            break
    if n is None:
        return []

    # Compute each target's per-game contribution matrix once for the whole slate.
    per_target: dict[str, dict] = {}

    if clf_hw is not None and X_clf is not None and hw_feat_cols is not None:
        try:
            # Dispatch by model class: glm_elasticnet v6 (E1.9 de-leaked) → exact
            # linear SHAP; XGBoost v5 → TreeSHAP. TreeExplainer would throw on a
            # linear model, so the dispatch (not a try/except) is what keeps the
            # v6 home_win explanations populated rather than 'deferred'.
            if home_win_is_linear(clf_hw):
                res = home_win_linear_shap(clf_hw, np.asarray(X_clf), hw_feat_cols)
                if res is None:
                    per_target["home_win"] = {"err": "linear_shap_deferred"}
                else:
                    sv, base = res
                    per_target["home_win"] = {"sv": sv, "base": base, "cols": hw_feat_cols,
                                              "method": "linear_shap_exact"}
            else:
                sv, base = home_win_shap(clf_hw, np.asarray(X_clf), hw_feat_cols)
                per_target["home_win"] = {"sv": sv, "base": base, "cols": hw_feat_cols,
                                          "method": "treeshap_exact"}
        except Exception as exc:  # never block scoring on an explainability failure
            per_target["home_win"] = {"err": f"shap_failed: {exc}"}

    for tname, model, X, cols in (
        ("total_runs", ngb_total, X_tot, tot_feat_cols),
        ("run_diff", ngb_diff, X_diff, diff_feat_cols),
    ):
        if model is None or X is None or cols is None:
            continue
        res = ngboost_loc_shap(model, np.asarray(X), cols)
        if res is None:
            per_target[tname] = {"err": "ngboost_shap_deferred"}
        else:
            sv, base = res
            per_target[tname] = {"sv": sv, "base": base, "cols": cols,
                                 "method": "treeshap_exact_loc"}

    payloads: list[dict] = []
    for i in range(n):
        targets: dict[str, dict] = {}
        for tname, info in per_target.items():
            if "err" in info:
                targets[tname] = _empty_target(tname, "deferred", info["err"])
                continue
            sv_i = np.asarray(info["sv"][i], dtype=float)
            targets[tname] = {
                "method": info["method"],
                "units": _TARGET_OUTCOME.get(tname, {}).get("unit", ""),
                "base_value": round(float(info["base"]), 5),
                "prediction": round(float(info["base"] + sv_i.sum()), 5),
                "toward": _TARGET_OUTCOME.get(tname, {}).get("toward", ""),
                "drivers": _drivers_for_game(info["cols"], sv_i, tname, top_n),
            }
        # Story 22.4 — σ confidence tier + abstain reason in payload
        sigma_payload: dict = {}
        if sigma_tiers is not None and i < len(sigma_tiers):
            sigma_payload["sigma_tier"] = sigma_tiers[i]
        if abstain_reasons is not None and i < len(abstain_reasons):
            sigma_payload["abstain_reason"] = abstain_reasons[i] or ""
        if totals_ci_widths is not None and i < len(totals_ci_widths):
            v = totals_ci_widths[i]
            if v is not None:
                sigma_payload["totals_ci_width"] = round(float(v), 4)
        if h2h_ci_widths is not None and i < len(h2h_ci_widths):
            v = h2h_ci_widths[i]
            if v is not None:
                sigma_payload["h2h_ci_width"] = round(float(v), 4)

        payloads.append({
            "served_tier": served_tier,
            "basis": "model_reasoning",
            "disclaimer": MODEL_REASONING_DISCLAIMER,
            "targets": targets,
            **sigma_payload,
        })
    return payloads
