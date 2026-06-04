"""
evaluate_production_bayesian.py — three-layer Bayesian evaluation of the PRODUCTION
models (home_win, run_differential, total_runs) on the 2026 OOS fold, champion vs.
the sequential-enriched challenger (Step 2 of the sequential-feature retrain).

This generalizes the totals-only `evaluate_totals_bayesian.py` to all three production
targets and to an arbitrary challenger artifact (the `*_tuned` outputs of the retrain
searches), so the same head-to-head framework that gated Epic 10/11 now decides the
sequential retrain. Per the spec the three targets are reported and gated INDEPENDENTLY
(a home_win win promotes home_win regardless of the others).

Framework (per target):
  Layer 1 — NLL vs a prior-predictive baseline (must beat to be informative):
      totals/run_diff: discretized-PMF NLL vs a prior fit on the 2021–25 training
      marginal (NegBin for totals, discretized-Normal for run_diff);
      home_win: log-loss vs the Bernoulli base-rate (training home-win rate).
  Layer 2 — calibration:
      totals/run_diff: calib_80 (central-80% interval coverage), gate [0.75, 0.85];
      home_win (Bernoulli — interval coverage N/A): ECE + calibration-in-the-large.
  Layer 3 — deployable blended Brier (alpha log-odds blend toward the Bovada market):
      vs prior-naive (training over-rate for totals / home-win rate for h2h) AND market.
      home_win adds the market-quality gate (Bovada Brier <= 0.235 => credible).
      run_diff has no direct market => L1/L2 only.

Champion surface: each champion is inference-scored on the 2026 fold (trained 2021–25,
2026 held out => genuine OOS). The challenger is scored the same way on its own feature
set (which includes the 10 Epic-16 sequential columns).

Snowflake-heavy (load_features + market loaders) => hand-off run.
Output: ablation_results/production_bayesian_<target>.md  (+ console summary)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

import joblib  # noqa: E402

from betting_ml.utils.data_loader import load_features  # noqa: E402
from betting_ml.utils.preprocessing import build_imputation_pipeline  # noqa: E402
from betting_ml.utils.feature_selection import load_retained_features  # noqa: E402
from betting_ml.scripts.train_elasticnet_prod import _MARKET_COLS_TO_EXCLUDE  # noqa: E402
from betting_ml.models.total_runs_trainer import p_over_line  # noqa: E402
from betting_ml.scripts.train_totals import _negbin_logpmf, _fit_negbin_r  # noqa: E402
from betting_ml.scripts.calibrate_totals_v1 import brier_score  # noqa: E402
from betting_ml.scripts.train_h2h import logloss as _logloss, ece as _ece  # noqa: E402
from betting_ml.utils.probability_layer import compute_posterior  # noqa: E402
from betting_ml.scripts.load_layer3_features import (  # noqa: E402
    load_total_line_bovada, load_devig_home_prob_bovada,
)
from betting_ml.scripts.evaluation.bayesian_model_eval import (  # noqa: E402
    sweep_thresholds, layer4_verdict, evaluate_selective_strategy,
    sweep_table_markdown, MIN_BETS_RELIABLE,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_MODELS = _PROJECT_ROOT / "betting_ml" / "models"
_S3_BUCKET = "s3://baseball-betting-ml-artifacts"
_BEST_ALPHA = _MODELS / "best_alpha.json"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results"
_OOS_YEAR = 2026
_TRAIN_MAX_YEAR = 2025
_SANE_MARKET_BRIER_MAX = 0.235  # h2h credible-market gate (Epic 11)
_CALIB_LO, _CALIB_HI = 0.75, 0.85

# Champion artifact + feature-column file per target.
#
# NOTE: the deployed S3 *_eb_enriched champions are NOT used here. Provenance
# recovery established that the deployed binaries drifted from every record
# (binary needs ≥374 features; registry/json/md@7.M and MLflow all document 369 =
# 367 base + 2 imputation indicators), and NGBoost stores no feature names — so
# their exact contract is unrecoverable. The faithful, reproducible form of the
# documented champion is a no-sequential ("nonseq") retrain of the same
# architecture on the 367 documented base features (retained − sequential −
# market), produced by the search scripts' --exclude-sequential flag. This both
# matches the documented champion spec AND is the clean ablation baseline (only
# difference vs. the challenger = the 10 Epic-16 sequential cols). Each nonseq
# model writes a feature-contract sidecar, so the matrix is reconstructed exactly.
_CHAMPION = {
    "total_runs":        ("total_runs/ngboost_nonseq_2026.pkl",       "total_runs/feature_columns_ngboost_nonseq_2026.json"),
    "run_differential":  ("run_differential/ngboost_nonseq_2026.pkl", "run_differential/feature_columns_ngboost_nonseq_2026.json"),
    "home_win":          ("home_win/xgb_classifier_nonseq_2026.pkl",  "home_win/feature_columns_xgb_classifier_nonseq_2026.json"),
}
# Challenger artifact + feature-column file per target (the sequential-enriched
# retrain-search outputs). The sidecar is read when present; otherwise the feature
# list is reconstructed via load_retained_features minus market cols (377),
# matching the search's own feature_cols construction.
_CHALLENGER = {
    "total_runs":       ("total_runs/ngboost_tuned_2026.pkl",        "total_runs/feature_columns_ngboost_tuned_2026.json"),
    "run_differential": ("run_differential/ngboost_tuned_2026.pkl",  "run_differential/feature_columns_ngboost_tuned_2026.json"),
    "home_win":         ("home_win/xgb_classifier_tuned_2026.pkl",   "home_win/feature_columns_xgb_classifier_tuned_2026.json"),
}
_NGB_TARGETS = {"total_runs", "run_differential"}


# ---------------------------------------------------------------------------
# Matrix + imputation (fit on 2021–25, applied to the 2026 eval rows — no leakage)
# ---------------------------------------------------------------------------

def _load_matrix():
    df = load_features(min_games_played=15)
    df["game_pk"] = df["game_pk"].astype(int)
    return df


def _reconstructed_feature_cols(df_cols) -> list[str]:
    """Challenger feature set — identical construction to the retrain search scripts."""
    return [f for f in load_retained_features()
            if f in df_cols and f not in _MARKET_COLS_TO_EXCLUDE]


def _feature_cols(df_cols, cols_file: str | None) -> list[str]:
    """Resolve a model's pre-imputation feature list.

    Prefer the model's own feature-contract sidecar (written by the search at
    persist time → exact, drift-proof); fall back to the retained-minus-market
    reconstruction only when the sidecar is absent.
    """
    if cols_file is not None and (_MODELS / cols_file).exists():
        payload = json.loads((_MODELS / cols_file).read_text())
        cols = payload["feature_cols"] if isinstance(payload, dict) else payload
        return [c for c in cols if c in df_cols]
    return _reconstructed_feature_cols(df_cols)


def _load_model(artifact: str):
    """Local artifact (all comparators here — nonseq champions and seq challengers —
    are search-script outputs persisted locally). S3 fallback retained for safety."""
    path = _MODELS / artifact
    if path.exists():
        return joblib.load(path)
    from betting_ml.utils.artifact_store import load_artifact
    uri = f"{_S3_BUCKET}/{artifact}"
    log.info("Local artifact missing — loading from %s", uri)
    return load_artifact(uri)


def _transform(df, feature_cols) -> pd.DataFrame:
    """Replicate the search scripts' exact training preprocessing (mirrors
    compare_model_versions._build_challenger_transform): impute the model's own
    feature_cols, then select numeric. _AddIndicators appends the 2 structural
    indicators last, so the output is feature_cols + 2 in pipeline order — the
    exact column structure the model was trained on via .values (NGBoost) /
    feature_names_in_ (XGBoost). No reindex to any external/stale json."""
    available = [c for c in feature_cols if c in df.columns]
    pipe = build_imputation_pipeline()
    transformed = pipe.fit_transform(df[available])
    return transformed.select_dtypes(include=[np.number])


def _score_ngb(artifact: str, feature_cols, df) -> pd.DataFrame:
    eval_mask = (df["game_year"] == _OOS_YEAR).to_numpy()
    Xt = _transform(df, feature_cols)
    model = _load_model(artifact)
    pred = model.pred_dist(Xt.loc[eval_mask].values)
    return pd.DataFrame({
        "game_pk": df.loc[eval_mask, "game_pk"].to_numpy(),
        "mu": np.asarray(pred.params["loc"], dtype=float),
        "sigma": np.asarray(pred.params["scale"], dtype=float),
    })


def _score_xgb(artifact: str, feature_cols, df) -> pd.DataFrame:
    eval_mask = (df["game_year"] == _OOS_YEAR).to_numpy()
    Xt = _transform(df, feature_cols)
    model = _load_model(artifact)
    Xe = Xt.loc[eval_mask]
    # PlattCalibratedXGBClassifier stores feature_names_in_ → align by name.
    names = [str(f) for f in model.xgb_classifier.feature_names_in_]
    Xe = Xe.reindex(columns=names, fill_value=0.0)
    proba = model.predict_proba(Xe)
    p = np.asarray(proba)[:, 1] if np.ndim(proba) == 2 else np.asarray(proba, dtype=float)
    return pd.DataFrame({"game_pk": df.loc[eval_mask, "game_pk"].to_numpy(), "p_home": p.astype(float)})


# ---------------------------------------------------------------------------
# Distribution metrics
# ---------------------------------------------------------------------------

def _normal_discrete_nll(y, mu, sigma) -> float:
    sigma = np.clip(sigma, 1e-6, None)
    pmf = norm.cdf((y + 0.5 - mu) / sigma) - norm.cdf((y - 0.5 - mu) / sigma)
    return float(-np.mean(np.log(np.clip(pmf, 1e-12, None))))


def _normal_calib_80(y, mu, sigma) -> float:
    sigma = np.clip(sigma, 1e-6, None)
    return float(np.mean(np.abs(y - mu) <= 1.2815515 * sigma))


def _american_to_prob(a: float) -> float:
    a = float(a)
    return 100.0 / (a + 100.0) if a > 0 else (-a) / ((-a) + 100.0)


def _devig_over(over_price, under_price) -> float:
    io, iu = _american_to_prob(over_price), _american_to_prob(under_price)
    return io / (io + iu)


def _blend(p, mkt, alpha) -> np.ndarray:
    return np.array([compute_posterior(float(a), float(b), alpha) for a, b in zip(p, mkt)])


# ---------------------------------------------------------------------------
# Per-target evaluation
# ---------------------------------------------------------------------------

def _layer4_block(games: pd.DataFrame) -> dict:
    """Layer 4 — selective-strategy sweep + verdict + default-threshold detail for
    one model's scored OOS games (totals or h2h canonical frame)."""
    sweep = sweep_thresholds(games)
    verdict = layer4_verdict(sweep)
    default = evaluate_selective_strategy(games)
    return {"sweep": sweep, "verdict": verdict, "default": default}


def _eval_ngb_target(target: str, df, with_challenger: bool) -> dict:
    """totals / run_differential: L1 NLL vs prior-predictive, L2 calib_80, (totals) L3."""
    actual_col = "total_runs" if target == "total_runs" else "run_differential"
    y_all = df[actual_col].astype(float)
    train_mask = df["game_year"] <= _TRAIN_MAX_YEAR
    y_train = y_all[train_mask].to_numpy()

    # Prior predictive on the training marginal.
    if target == "total_runs":
        mu_p = float(np.mean(y_train))
        r_p = _fit_negbin_r(y_train, np.full(len(y_train), mu_p))
        prior_nll_fn = lambda y: -float(np.mean(_negbin_logpmf(y, mu_p, r_p)))
        prior_desc = f"NegBin(mu={mu_p:.3f}, r={r_p:.3f})"
    else:
        mu0, sig0 = float(np.mean(y_train)), float(np.std(y_train, ddof=1))
        prior_nll_fn = lambda y: _normal_discrete_nll(y, np.full(len(y), mu0), np.full(len(y), sig0))
        prior_desc = f"discretized-Normal(mu={mu0:.3f}, sigma={sig0:.3f})"

    champ_art, champ_cols_file = _CHAMPION[target]
    models = {"champion": (champ_art, _feature_cols(df.columns, champ_cols_file))}
    if with_challenger:
        chall_art, chall_cols_file = _CHALLENGER[target]
        models["challenger"] = (chall_art, _feature_cols(df.columns, chall_cols_file))

    # Score all model variants; align them on the shared 2026 game_pk set (the
    # intersection of all variants' scored games and the settled-outcome rows).
    scored = {k: _score_ngb(a, c, df) for k, (a, c) in models.items()}
    base = df[df["game_year"] == _OOS_YEAR][["game_pk", actual_col]].dropna(subset=[actual_col]).copy()
    pk_set = set(base["game_pk"])
    for s in scored.values():
        pk_set &= set(s["game_pk"])
    base = base[base["game_pk"].isin(pk_set)].reset_index(drop=True)
    y = base[actual_col].to_numpy(float)
    prior_nll = prior_nll_fn(y)

    # Totals market (de-vigged Bovada over prob) for L3.
    market = None
    if target == "total_runs":
        lines = load_total_line_bovada(list(pk_set))
        lines = lines.dropna(subset=["total_line_bovada", "over_price", "under_price"])
        lines["devig_over"] = lines.apply(
            lambda r: _devig_over(r["over_price"], r["under_price"]), axis=1)
        lines["over_hit"] = np.nan  # filled after merge with actuals
        market = lines[["game_pk", "total_line_bovada", "devig_over"]]
        alpha = float(json.loads(_BEST_ALPHA.read_text()).get("totals_alpha", 0.70))
        train_over = _train_over_rate(df, train_mask)

    out = {"target": target, "n": len(base), "prior_nll": prior_nll, "prior_desc": prior_desc,
           "models": {}}
    for k, s in scored.items():
        m = s[s["game_pk"].isin(pk_set)].set_index("game_pk").loc[base["game_pk"]]
        mu, sigma = m["mu"].to_numpy(float), m["sigma"].to_numpy(float)
        rec = {"nll": _normal_discrete_nll(y, mu, sigma),
               "calib_80": _normal_calib_80(y, mu, sigma),
               "mean_pred": float(mu.mean())}
        if target == "total_runs" and market is not None:
            mk = base.merge(market, on="game_pk", how="left")
            line = mk["total_line_bovada"].to_numpy(float)
            devig = mk["devig_over"].to_numpy(float)
            over_hit = (y > line).astype(float)
            valid = ~np.isnan(devig) & ~np.isnan(line)
            p_over = np.asarray(p_over_line("Normal", {"loc": mu, "scale": sigma}, line), dtype=float)
            blended = _blend(p_over[valid], devig[valid], alpha)
            rec.update({
                "blended_brier": brier_score(blended, over_hit[valid]),
                "market_brier": brier_score(devig[valid], over_hit[valid]),
                "prior_naive_brier": brier_score(np.full(valid.sum(), train_over), over_hit[valid]),
                "mean_p_over_blended": float(blended.mean()),
                "actual_over_rate": float(over_hit[valid].mean()),
                "pct_pred_over_line": float((mu[valid] > line[valid]).mean() * 100),
                "n_market": int(valid.sum()), "alpha": alpha, "train_over_rate": train_over,
            })
            # Layer 4 — selective strategy on this model's 2026 OOS predictions.
            games4 = pd.DataFrame({
                "market": "totals", "model_mu": mu, "total_line": line,
                "actual_total": y, "model_p_over": p_over, "market_p_over": devig,
            })
            rec["layer4"] = _layer4_block(games4)
        out["models"][k] = rec
    return out


def _train_over_rate(df, train_mask) -> float:
    tr = df.loc[train_mask, ["game_pk", "total_runs"]].dropna()
    lines = load_total_line_bovada(tr["game_pk"].tolist())
    j = tr.merge(lines[["game_pk", "total_line_bovada"]], on="game_pk", how="inner").dropna()
    return float((j["total_runs"] > j["total_line_bovada"]).mean()) if len(j) else 0.456


def _eval_home_win(df, with_challenger: bool) -> dict:
    y_all = df["home_win"].astype(float)
    train_mask = df["game_year"] <= _TRAIN_MAX_YEAR
    base_rate = float(y_all[train_mask].mean())  # Bernoulli prior-predictive

    champ_art, champ_cols_file = _CHAMPION["home_win"]
    models = {"champion": (champ_art, _feature_cols(df.columns, champ_cols_file))}
    if with_challenger:
        chall_art, chall_cols_file = _CHALLENGER["home_win"]
        models["challenger"] = (chall_art, _feature_cols(df.columns, chall_cols_file))

    scored = {k: _score_xgb(a, c, df) for k, (a, c) in models.items()}
    base = df[df["game_year"] == _OOS_YEAR][["game_pk", "home_win"]].dropna(subset=["home_win"]).copy()
    pk_set = set(base["game_pk"])
    for s in scored.values():
        pk_set &= set(s["game_pk"])
    base = base[base["game_pk"].isin(pk_set)].reset_index(drop=True)
    y = base["home_win"].to_numpy(float)

    # Market: de-vigged Bovada home win prob + credible-market gate.
    mkt = load_devig_home_prob_bovada(list(pk_set))
    mkt_by_pk = {int(pk): float(v) for pk, v in
                 zip(mkt["game_pk"], mkt["bovada_devig_home_prob"]) if pd.notna(v)}
    cov = base["game_pk"].map(lambda pk: int(pk) in mkt_by_pk).to_numpy()
    mkt_p = base["game_pk"].map(lambda pk: mkt_by_pk.get(int(pk), np.nan)).to_numpy(float)
    market_brier = brier_score(mkt_p[cov], y[cov]) if cov.any() else float("nan")

    alpha = float(json.loads(_BEST_ALPHA.read_text()).get("best_alpha", 0.0))
    prior_nll = _logloss(np.full(len(y), base_rate), y)
    prior_naive_brier = brier_score(np.full(int(cov.sum()), base_rate), y[cov]) if cov.any() else float("nan")

    out = {"target": "home_win", "n": len(base), "n_market": int(cov.sum()),
           "base_rate": base_rate, "prior_nll": prior_nll, "alpha": alpha,
           "market_brier": market_brier, "prior_naive_brier": prior_naive_brier,
           "market_credible": (market_brier <= _SANE_MARKET_BRIER_MAX), "models": {}}
    for k, s in scored.items():
        p = s[s["game_pk"].isin(pk_set)].set_index("game_pk").loc[base["game_pk"], "p_home"].to_numpy(float)
        blended = _blend(p[cov], mkt_p[cov], alpha) if cov.any() else np.array([])
        rec = {
            "nll": _logloss(p, y),
            "ece": _ece(p, y),
            "calib_in_large": float(p.mean() - y.mean()),
            "brier_model": brier_score(p[cov], y[cov]) if cov.any() else float("nan"),
            "blended_brier": brier_score(blended, y[cov]) if cov.any() else float("nan"),
            "mean_p": float(p.mean()),
        }
        if cov.any():
            # Layer 4 — selective strategy on the model's RAW P(home) vs the de-vigged
            # Bovada line (covered games only). Must use the raw model probability, NOT
            # the alpha-blended posterior: at production h2h alpha=0 the blend equals the
            # market, so a blended Layer 4 is vacuous (model==market → 0 bets). Layer 4
            # asks whether the model's own signal has selective edge — that is the
            # pre-blend probability (consistent with the H2H OOS surface in Epic 26.4 and
            # the live attribution logging in 26.5, which both use the raw model prob).
            games4 = pd.DataFrame({
                "market": "h2h", "model_p_home": p[cov],
                "market_p_home": mkt_p[cov], "home_win": y[cov],
            })
            rec["layer4"] = _layer4_block(games4)
        out["models"][k] = rec
    return out


# ---------------------------------------------------------------------------
# Decision gates (per the spec)
# ---------------------------------------------------------------------------

def _b(x):
    return "✅" if x else "❌"


def _gates_ngb(R: dict) -> dict:
    M = R["models"]
    g = {}
    for k, m in M.items():
        gk = {"L1 NLL < prior": m["nll"] < R["prior_nll"],
              "L2 calib_80 in [0.75,0.85]": _CALIB_LO <= m["calib_80"] <= _CALIB_HI}
        if "blended_brier" in m:
            gk["L3 Brier(blended) < prior-naive"] = m["blended_brier"] < m["prior_naive_brier"]
            gk["L3 Brier(blended) < market"] = m["blended_brier"] < m["market_brier"]
        if "layer4" in m:
            gm = m["layer4"]["verdict"]["gate_metric"]
            gk[f"L4 selective {gm}>0 & n>={MIN_BETS_RELIABLE}"] = m["layer4"]["verdict"]["passed"]
        g[k] = gk
    if "challenger" in M:
        ch, cp = M["challenger"], M["champion"]
        g["head_to_head"] = {"challenger NLL < champion": ch["nll"] < cp["nll"]}
        if "blended_brier" in ch:
            g["head_to_head"]["challenger Brier(blended) < champion"] = ch["blended_brier"] < cp["blended_brier"]
    return g


def _gates_home(R: dict) -> dict:
    M = R["models"]
    g = {}
    for k, m in M.items():
        gk = {"L1 NLL < prior (base-rate)": m["nll"] < R["prior_nll"],
              "L2 ECE <= 0.05": m["ece"] <= 0.05,
              "L3 Brier(blended) < prior-naive": m["blended_brier"] < R["prior_naive_brier"],
              "L3 Brier(blended) < market": m["blended_brier"] < R["market_brier"]}
        if "layer4" in m:
            gm = m["layer4"]["verdict"]["gate_metric"]
            gk[f"L4 selective {gm}>0 & n>={MIN_BETS_RELIABLE}"] = m["layer4"]["verdict"]["passed"]
        g[k] = gk
    g["market_quality"] = {f"Bovada market Brier <= {_SANE_MARKET_BRIER_MAX}": R["market_credible"]}
    if "challenger" in M:
        ch, cp = M["challenger"], M["champion"]
        g["head_to_head"] = {"challenger NLL < champion": ch["nll"] < cp["nll"],
                             "challenger Brier(blended) < champion": ch["blended_brier"] < cp["blended_brier"]}
    return g


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _json_default(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def _layer4_lines(target: str, M: dict) -> list[str]:
    keys = [k for k in ("champion", "challenger") if k in M and "layer4" in M[k]]
    if not keys:
        return []
    out = ["", "## Layer 4 — Selective Strategy", "",
           "_Edge on the bet-triggered subset only (not all games). Layer 4 does NOT replace "
           "L1–L3: a model failing L1/L3 but passing L4 is **selective-edge-only** — informative "
           "for manual selection, not automated deployment. Passing all four => deployable at the "
           f"optimal threshold. ⚠️ rows have n_bets < {MIN_BETS_RELIABLE} (statistically unreliable)._", "",
           "_**Gate metric:** totals → **roi_110** (totals settle at -110 both sides). H2H → "
           "**roi_devig** (each bet priced at de-vigged fair odds) — flat -110 misprices "
           "moneyline favorites/underdogs. roi_devig is vig-free (optimistic upper bound)._", ""]
    for k in keys:
        l4 = M[k]["layer4"]; v = l4["verdict"]; d = l4["default"]; gate = v["gate_metric"]
        out += [f"### {k}", ""] + sweep_table_markdown(l4["sweep"]) + [""]
        if v["passed"]:
            thr = (f"totals {v['optimal_totals_threshold']:.2f}" if target == "total_runs"
                   else f"h2h {v['optimal_h2h_threshold']:.2f}")
            out += [f"- **Verdict: ✅ PASS** (gate={gate}) — optimal {thr}: n_bets {v['n_bets']}, "
                    f"win_rate {v['win_rate']:.3f}, {gate} {v['roi']:+.4f}.", ""]
        else:
            out += [f"- **Verdict: ❌ FAIL** (gate={gate}) — no threshold with {gate}>0 "
                    f"AND n_bets≥{MIN_BETS_RELIABLE}.", ""]
        if target == "total_runs" and "totals" in d:
            tb, nb = d["totals"], d["no_bet"]
            out += [f"- @default 1.0 run — over: n={tb['over']['n_bets']} roi {tb['over']['roi_110']:+.4f} · "
                    f"under: n={tb['under']['n_bets']} roi {tb['under']['roi_110']:+.4f}.",
                    f"- No-bet (n={nb['n']}): uncertainty-zone |μ−line|<0.5 frac "
                    f"{nb.get('totals_uncertainty_zone_frac', float('nan')):.3f} "
                    f"(rest = view-below-threshold) · model Brier {nb.get('totals_model_brier', float('nan')):.4f} "
                    f"vs market {nb.get('totals_market_brier', float('nan')):.4f}.", ""]
        elif target == "home_win" and "h2h" in d:
            hb, nb = d["h2h"], d["no_bet"]
            out += [f"- @default 0.12 — direction_flip: n={hb['direction_flip']['n_bets']} roi "
                    f"{hb['direction_flip']['roi_110']:+.4f} · magnitude: n={hb['magnitude']['n_bets']} roi "
                    f"{hb['magnitude']['roi_110']:+.4f}.",
                    f"- No-bet (n={nb['n']}): model Brier {nb.get('h2h_model_brier', float('nan')):.4f} "
                    f"vs market {nb.get('h2h_market_brier', float('nan')):.4f}.", ""]
    return out


def _write_report(R: dict, gates: dict) -> Path:
    t = R["target"]
    path = _REPORT_DIR / f"production_bayesian_{t}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    M = R["models"]
    keys = [k for k in ("champion", "challenger") if k in M]
    lines = [f"# {t} — Production Bayesian Three-Layer Evaluation (sequential retrain)", "",
             f"- **OOS set:** {R['n']} games (2026 fold; trained 2021–25 → genuine OOS).",
             "- **Champion = faithful 369-feature no-sequential reproduction** (the documented "
             "production-champion spec). The deployed S3 `*_eb_enriched` binaries drifted from "
             "every record (needed ≥374 features vs. documented 369) and are unrecoverable; this "
             "nonseq retrain reproduces the documented contract AND is the clean ablation baseline.",
             f"- **Challenger present:** {'yes (sequential-enriched)' if 'challenger' in M else 'NO (champion baseline only)'}.", ""]
    if t in _NGB_TARGETS:
        lines += [f"- **Layer 1 prior-predictive:** {R['prior_desc']} → NLL **{R['prior_nll']:.4f}** (must beat).", ""]
        hdr = "| Metric | " + " | ".join(keys) + " |"
        sep = "|---|" + "---:|" * len(keys)
        rows = [hdr, sep,
                "| L1 NLL (PMF) | " + " | ".join(f"{M[k]['nll']:.4f}" for k in keys) + " |",
                "| L2 calib_80 | " + " | ".join(f"{M[k]['calib_80']:.3f}" for k in keys) + " |",
                "| mean pred | " + " | ".join(f"{M[k]['mean_pred']:.3f}" for k in keys) + " |"]
        if t == "total_runs":
            rows += ["| L3 Brier(blended) | " + " | ".join(f"{M[k]['blended_brier']:.4f}" for k in keys) + " |",
                     "| L3 mean P(over) | " + " | ".join(f"{M[k]['mean_p_over_blended']:.3f}" for k in keys) + " |",
                     "| pct pred>line | " + " | ".join(f"{M[k]['pct_pred_over_line']:.1f}%" for k in keys) + " |"]
            cm = M[keys[0]]
            lines += [f"- **L3 baselines:** prior-naive Brier **{cm['prior_naive_brier']:.4f}** (over-rate "
                      f"{cm['train_over_rate']:.3f}) · market Brier **{cm['market_brier']:.4f}** · "
                      f"actual over-rate {cm['actual_over_rate']:.3f} · alpha {cm['alpha']:.2f} · "
                      f"n_market {cm['n_market']}.", ""]
        lines += rows
    else:  # home_win
        lines += [f"- **Layer 1 prior-predictive:** Bernoulli base-rate {R['base_rate']:.3f} → log-loss "
                  f"**{R['prior_nll']:.4f}** (must beat).",
                  f"- **L3 baselines:** prior-naive Brier **{R['prior_naive_brier']:.4f}** · market Brier "
                  f"**{R['market_brier']:.4f}** ({'credible' if R['market_credible'] else '⚠️ DEGRADED'}; "
                  f"gate ≤{_SANE_MARKET_BRIER_MAX}) · alpha {R['alpha']:.2f} · n_market {R['n_market']}.",
                  "- _Note: calib_80 (interval coverage) is undefined for a Bernoulli model; Layer 2 uses ECE "
                  "and calibration-in-the-large instead._", ""]
        hdr = "| Metric | " + " | ".join(keys) + " |"
        sep = "|---|" + "---:|" * len(keys)
        lines += [hdr, sep,
                  "| L1 log-loss | " + " | ".join(f"{M[k]['nll']:.4f}" for k in keys) + " |",
                  "| L2 ECE | " + " | ".join(f"{M[k]['ece']:.4f}" for k in keys) + " |",
                  "| calib-in-large | " + " | ".join(f"{M[k]['calib_in_large']:+.4f}" for k in keys) + " |",
                  "| L3 Brier(blended) | " + " | ".join(f"{M[k]['blended_brier']:.4f}" for k in keys) + " |",
                  "| Brier(model raw) | " + " | ".join(f"{M[k]['brier_model']:.4f}" for k in keys) + " |"]
    lines += _layer4_lines(t, M)
    lines += ["", "## Gates"]
    for grp, gd in gates.items():
        lines += [f"### {grp}", "| Gate | Result |", "|---|:--:|",
                  *[f"| {kk} | {_b(vv)} |" for kk, vv in gd.items()], ""]
    path.write_text("\n".join(lines) + "\n")

    # JSON companion (machine-readable; includes the layer4_selective_strategy block).
    jpath = _REPORT_DIR / f"production_bayesian_{t}.json"
    payload = {"target": t, "report": R, "gates": gates,
               "layer4_selective_strategy": {k: R["models"][k].get("layer4")
                                             for k in M if "layer4" in R["models"][k]}}
    jpath.write_text(json.dumps(payload, indent=2, default=_json_default))
    return path


def run(target: str, env: str = "prod", champion_only: bool = False) -> dict:
    df = _load_matrix()
    chall_art = _CHALLENGER[target][0]
    with_challenger = (not champion_only) and (_MODELS / chall_art).exists()
    if not champion_only and not with_challenger:
        log.warning("Challenger artifact %s not found — running champion baseline only.",
                    chall_art)
    if target in _NGB_TARGETS:
        R = _eval_ngb_target(target, df, with_challenger)
        gates = _gates_ngb(R)
    else:
        R = _eval_home_win(df, with_challenger)
        gates = _gates_home(R)
    path = _write_report(R, gates)
    log.info("[%s] n=%d  %s", target, R["n"],
             "  ".join(f"{k}:NLL={m['nll']:.4f}" for k, m in R["models"].items()))
    log.info("Wrote %s", path)
    return {"R": R, "gates": gates, "report": str(path)}


def main() -> None:
    p = argparse.ArgumentParser(description="Three-layer Bayesian eval of production models (sequential retrain)")
    p.add_argument("--target", choices=["total_runs", "run_differential", "home_win", "all"], default="all")
    p.add_argument("--env", choices=["prod", "dev"], default="prod")
    p.add_argument("--champion-only", action="store_true",
                   help="Baseline the current champions without a challenger (establishes the bar).")
    args = p.parse_args()
    targets = ["total_runs", "run_differential", "home_win"] if args.target == "all" else [args.target]
    for t in targets:
        run(t, env=args.env, champion_only=args.champion_only)


if __name__ == "__main__":
    main()
