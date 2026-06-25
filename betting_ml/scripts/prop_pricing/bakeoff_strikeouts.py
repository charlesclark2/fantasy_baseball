"""bakeoff_strikeouts.py — Edge Program E5.2: pitcher-strikeout MODEL-CLASS + FEATURE bake-off.

WHY (the methodology gap this closes)
--------------------------------------
The E5.2 first pass shipped a SINGLE architecture (the structural compound Beta-Binomial). That
is not the program's standard — every other model (E1.9 v6, starter_ip_v1's Candidate A/C, the
per-side NegBin-vs-Poisson gate) first bakes off model CLASSES and ablates feature INPUTS under
the honest gate, then picks on the metric with a PBO guard. Two specific gaps motivated this:

  1. **Only one model class.** We never showed the compound model beats a directly-learned count
     model on calibration / CRPS. Maybe a learned model calibrates tighter (it would not inherit
     starter_ip_v1's slightly-over-wide outs intervals); maybe the compound wins at the tails.
  2. **In-season stuff change ignored.** The compound's K-rate used a FLAT season-to-date + career
     average, which washes out a pitcher REFINING or LOSING stuff mid-season (velo gain, a new
     pitch). Recent in-season form is the whole small-sample point. The fix is a RECENCY-weighted
     rate (k_pct_7d / k_pct_30d / 3-start) — and a learned model given those multi-window features
     LEARNS the recency weighting from prior seasons. (The forward-CV protocol — fit on prior
     seasons, eval the next — STAYS: fitting on the eval season's own outcomes is leakage. Only the
     FEATURE construction needed to become recency-aware.)

WHAT IT DOES
------------
Under E1.1 PurgedWalkForwardSplit, scores every candidate's per-game PREDICTIVE SAMPLES the same
way (apples-to-apples via promotion_gate.PredictiveOutput.from_samples):
  * CRPS (crps_ensemble — the proper, distribution-free accuracy-to-truth score) — PRIMARY
  * coverage@80 + PIT-KS (calibration_report) — is the DISTRIBUTION honest
  * at-the-line ECE (reliability of P(over) at representative K lines)
Then PBO (CSCV, overfitting.pbo_cscv) across the candidate slate — is the winner an overfit pick?

Candidates (all market-blind, CONTRACT-GUARD'd):
  M1 compound_flat      — compound Beta-Binomial, FLAT season+career K-rate (the current baseline)
  M2 compound_recency   — compound Beta-Binomial, RECENCY-weighted K-rate (7d/30d blend)
  M3 lgbm_poisson_k     — direct LightGBM-Poisson on K + NegBin-r-by-decile (learns recency)
  M4 poisson_glm_k      — Poisson GLM floor (the simple learned baseline)
Feature/input ablation (compound family): rate-construction {career_only, season_career,
  recency_30d, recency_7d, recency_blend} × framing{on,off} × lineup-log5{on,off}.

The LightGBM / GLM fits are multi-fold → HAND TO THE OPERATOR. `--smoke` runs the whole harness on
a synthetic frame (no Snowflake) to validate it end-to-end. Output:
  ablation_results/e5_2_strikeout_bakeoff.{json,md}

Usage (operator):
    uv run python betting_ml/scripts/prop_pricing/bakeoff_strikeouts.py
    uv run python betting_ml/scripts/prop_pricing/bakeoff_strikeouts.py --smoke   # harness check
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.cv import PurgedWalkForwardSplit
from betting_ml.utils.market_blind import assert_market_blind
from betting_ml.utils.overfitting import pbo_cscv
from betting_ml.utils.promotion_gate import PredictiveOutput, calibration_report
from betting_ml.utils.prop_pricing import (
    calibrate_concentration_expanding,
    fit_betabinom_concentration,
    price_strikeouts,
    prob_over,
    scale_spread,
)
from betting_ml.utils.totals_distribution import fit_negbin_dispersion
from betting_ml.scripts.prop_pricing.fit_prop_pricing import (
    _K_LINES,
    _ece,
    build_predictors,
)

_SEED = 42
_N_DRAWS = 4_000          # fewer draws than the gate (4k) — the bake-off scores many configs
_LAM_GRID = [round(x, 3) for x in np.arange(0.6, 1.06, 0.05)]
_RESULTS_DIR = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results"
)

# Market-blind feature set for the LEARNED candidates (raw recency + workload + matchup columns —
# the model weights recency itself). NO market/odds columns (CONTRACT-GUARD verifies).
_LEARNED_FEATURES = [
    "eb_pitcher_k", "league_k_rate", "opp_lineup_k_pct", "framing_z", "reach_rate_trailing",
    "starter_ip_mu", "starter_ip_dispersion", "k_career", "bf_career", "k_season", "bf_season",
    "k_pct_7d", "k_pct_30d", "whiff_rate_30d", "csw_pct_3start", "velo_delta_3start",
    "fastball_velo_trend",
]


# ---------------------------------------------------------------------------
# Candidate predictive samplers — each returns (n_eval, n_draws) K-count samples
# ---------------------------------------------------------------------------

_LAM_FIT_MAX_ROWS = 3000     # λ is one robust scalar — cap the train subsample it is fit on


def _fit_lambda(train_samp: np.ndarray, k_train: np.ndarray, rng, *, target: str = "pit") -> float:
    """The spread-recalibration λ for the TRAIN predictive (one robust scalar).

    Applied to EVERY candidate (compound AND learned) so the calibration comparison is FAIR. `target`:
    'pit' minimises the PIT decile deviation (the bake-off default, comparing distribution shape);
    'coverage' minimises |coverage@80 − 0.80| (the SERVED objective — the E5.2 calib_80 AC; over-wide
    predictives are tightened to a true 80% interval)."""
    from betting_ml.utils.prop_pricing import interval_coverage, pit_flatness, randomized_pit
    if len(k_train) > _LAM_FIT_MAX_ROWS:
        sel = rng.choice(len(k_train), _LAM_FIT_MAX_ROWS, replace=False)
        train_samp, k_train = train_samp[sel], k_train[sel]
    best_lam, best_score = 1.0, np.inf
    for lam in _LAM_GRID:
        sc = scale_spread(train_samp, lam)
        score = (abs(interval_coverage(k_train, sc, 0.10, 0.90) - 0.80) if target == "coverage"
                 else pit_flatness(randomized_pit(k_train, sc, rng))["max_decile_dev"])
        if score < best_score:
            best_score, best_lam = score, lam
    return best_lam


def _compound_samples(pred: pd.DataFrame, train_idx, eval_idx, rng) -> np.ndarray:
    """Compound Beta-Binomial: calibrate s + λ on the TRAIN fold (leak-safe), price the EVAL fold."""
    tr, ev = pred.loc[train_idx], pred.loc[eval_idx]
    s = fit_betabinom_concentration(
        tr["strikeouts"].to_numpy(float), tr["batters_faced"].to_numpy(float), tr["p_k"].to_numpy(float))
    tr_s = tr if len(tr) <= _LAM_FIT_MAX_ROWS else tr.sample(_LAM_FIT_MAX_ROWS, random_state=0)
    tr_samp = price_strikeouts(
        tr_s["starter_ip_mu"].to_numpy(float), tr_s["starter_ip_dispersion"].to_numpy(float),
        tr_s["reach_rate_trailing"].to_numpy(float), tr_s["p_k"].to_numpy(float),
        concentration=s, rng=rng, n_draws=1500)
    lam = _fit_lambda(tr_samp, tr_s["strikeouts"].to_numpy(float), rng)
    ev_samp = price_strikeouts(
        ev["starter_ip_mu"].to_numpy(float), ev["starter_ip_dispersion"].to_numpy(float),
        ev["reach_rate_trailing"].to_numpy(float), ev["p_k"].to_numpy(float),
        concentration=s, rng=rng, n_draws=_N_DRAWS)
    return scale_spread(ev_samp, lam)


def _learned_matrix(pred: pd.DataFrame, idx, impute: dict | None) -> tuple[np.ndarray, dict]:
    sub = pred.loc[idx, _LEARNED_FEATURES].apply(pd.to_numeric, errors="coerce")
    if impute is None:
        impute = {c: float(sub[c].median()) for c in _LEARNED_FEATURES}
    return sub.fillna(impute).to_numpy(float), impute


def _lgbm_poisson_samples(pred, train_idx, eval_idx, rng) -> np.ndarray:
    """Direct LightGBM-Poisson mean on K + NegBin r-by-decile (mirrors starter_ip_v1) → samples."""
    import lightgbm as lgb
    Xtr, imp = _learned_matrix(pred, train_idx, None)
    Xev, _ = _learned_matrix(pred, eval_idx, imp)
    ktr = pred.loc[train_idx, "strikeouts"].to_numpy(float)
    model = lgb.LGBMRegressor(objective="poisson", n_estimators=400, learning_rate=0.02,
                              num_leaves=31, min_child_samples=40, subsample=0.7,
                              colsample_bytree=0.7, verbosity=-1)
    model.fit(Xtr, ktr)
    mu_tr = np.clip(model.predict(Xtr), 0.3, None)
    mu_ev = np.clip(model.predict(Xev), 0.3, None)
    # NegBin r per predicted-mean decile, fit on TRAIN residuals (leak-safe).
    edges = np.quantile(mu_tr, np.linspace(0.1, 0.9, 9))
    r_by_bin = {}
    btr = np.clip(np.digitize(mu_tr, edges), 0, 9)
    for b in range(10):
        m = btr == b
        r_by_bin[b] = fit_negbin_dispersion(ktr[m], mu_tr[m]) if m.sum() > 30 else 8.0
    btr2 = np.clip(np.digitize(mu_tr, edges), 0, 9)
    r_tr = np.array([r_by_bin[int(b)] for b in btr2])
    tr_samp = rng.negative_binomial(r_tr[:, None], (r_tr / (r_tr + mu_tr))[:, None], size=(len(mu_tr), 1500))
    lam = _fit_lambda(tr_samp, ktr, rng)         # same fair λ recalibration as the compound
    bev = np.clip(np.digitize(mu_ev, edges), 0, 9)
    r_ev = np.array([r_by_bin[int(b)] for b in bev])
    p_ev = r_ev / (r_ev + mu_ev)
    ev_samp = rng.negative_binomial(r_ev[:, None], p_ev[:, None], size=(len(mu_ev), _N_DRAWS))
    return scale_spread(ev_samp, lam)


def _poisson_glm_samples(pred, train_idx, eval_idx, rng, *, lam_target: str = "pit") -> np.ndarray:
    """Poisson-GLM (sklearn PoissonRegressor) → Poisson samples — the E5.2 SERVED class (won the
    bake-off). `lam_target` picks the spread-recalibration objective ('pit' for the fair bake-off
    comparison; 'coverage' for the served fit / the calib_80 AC)."""
    from sklearn.linear_model import PoissonRegressor
    from sklearn.preprocessing import StandardScaler
    Xtr, imp = _learned_matrix(pred, train_idx, None)
    Xev, _ = _learned_matrix(pred, eval_idx, imp)
    ktr = pred.loc[train_idx, "strikeouts"].to_numpy(float)
    sc = StandardScaler().fit(Xtr)
    glm = PoissonRegressor(alpha=1.0, max_iter=400).fit(sc.transform(Xtr), ktr)
    mu_tr = np.clip(glm.predict(sc.transform(Xtr)), 0.3, None)
    mu_ev = np.clip(glm.predict(sc.transform(Xev)), 0.3, None)
    tr_samp = rng.poisson(mu_tr[:, None], size=(len(mu_tr), 1500))
    lam = _fit_lambda(tr_samp, ktr, rng, target=lam_target)
    ev_samp = rng.poisson(mu_ev[:, None], size=(len(mu_ev), _N_DRAWS))
    return scale_spread(ev_samp, lam)


# ---------------------------------------------------------------------------
# Bake-off driver
# ---------------------------------------------------------------------------

def _score_candidate(name, sampler, pred, splitter, rng) -> dict:
    """Run a candidate through purged-CV: pool eval samples/obs, keep per-fold CRPS for PBO."""
    pooled_samp, pooled_obs, fold_crps = [], [], []
    for train_idx, eval_idx in splitter.split(pred, feature_cols=_LEARNED_FEATURES):
        if len(train_idx) < 200 or len(eval_idx) < 50:
            continue
        try:
            samp = sampler(pred, train_idx, eval_idx, rng)
        except Exception as exc:  # noqa: BLE001 — a candidate that errors is dropped, logged
            print(f"  [WARN] {name} fold failed: {exc}")
            continue
        obs = pred.loc[eval_idx, "strikeouts"].to_numpy(float)
        out = PredictiveOutput.from_samples(samp)
        fold_crps.append(float(np.mean(out.score_to_truth(obs, "crps"))))
        pooled_samp.append(samp); pooled_obs.append(obs)
    if not pooled_samp:
        return {"name": name, "ok": False}
    samp = np.concatenate(pooled_samp, axis=0); obs = np.concatenate(pooled_obs)
    out = PredictiveOutput.from_samples(samp)
    rep = calibration_report(obs, out, level=0.80)
    po = prob_over(samp, _K_LINES)
    ece = {str(ln): round(_ece(po[ln], (obs > ln).astype(float)), 4) for ln in _K_LINES}
    return {
        "name": name, "ok": True, "n": int(len(obs)),
        "crps": round(float(np.mean(out.score_to_truth(obs, "crps"))), 4),
        "coverage_80": round(rep["coverage"], 4), "pit_ks": round(rep["pit_ks"], 4),
        "bias": round(rep["bias"], 4), "mean_ece": round(float(np.mean(list(map(float, ece.values())))), 4),
        "ece_by_line": ece, "fold_crps": [round(x, 4) for x in fold_crps],
    }


# PRE-REGISTERED config grid (fixed; do NOT expand reactively — §0.5). Each row is ONE config the
# PBO deflates over: the model class × its feature inputs. The compound feature-ablation cells
# (rate-construction × framing × lineup-log5) are configs too, NOT a separate un-deflated table.
_COMPOUND_FEAT_CFGS = {
    "rate=career_only":              dict(rate_mode="career_only",   framing=True,  use_lineup_log5=True),
    "rate=season_career":            dict(rate_mode="season_career", framing=True,  use_lineup_log5=True),
    "rate=recency_30d":              dict(rate_mode="recency_30d",   framing=True,  use_lineup_log5=True),
    "rate=recency_7d":               dict(rate_mode="recency_7d",    framing=True,  use_lineup_log5=True),
    "rate=recency_blend":            dict(rate_mode="recency_blend", framing=True,  use_lineup_log5=True),
    "rate=recency_blend|no_framing": dict(rate_mode="recency_blend", framing=False, use_lineup_log5=True),
    "rate=recency_blend|no_lineup":  dict(rate_mode="recency_blend", framing=True,  use_lineup_log5=False),
}


def _paired_delta(ok: dict, a: str, b: str) -> dict | None:
    """Paired-by-FOLD CRPS difference CRPS(a)−CRPS(b) (same purged folds → aligned). The named-
    mechanism stat (§0.5): mean Δ + a ±2·SEM band; `excludes_zero` distinguishes a real effect
    ('adds X, CI excludes 0') from 'orthogonal-but-inert'. Negative Δ ⇒ `a` is better (lower CRPS)."""
    if a not in ok or b not in ok:
        return None
    fa, fb = ok[a]["fold_crps"], ok[b]["fold_crps"]
    L = min(len(fa), len(fb))
    if L < 2:
        return None
    d = np.array(fa[:L]) - np.array(fb[:L])
    sem = float(d.std(ddof=1) / np.sqrt(L))
    return {"mean_delta_crps": round(float(d.mean()), 4), "sem": round(sem, 4), "n_folds": L,
            "ci95": [round(float(d.mean() - 2 * sem), 4), round(float(d.mean() + 2 * sem), 4)],
            "excludes_zero": bool(abs(d.mean()) > 2 * sem)}


def run_grid(df: pd.DataFrame, rng) -> dict:
    """Score the FULL pre-registered grid (model classes × feature configs) under ONE purged CV,
    deflate the selection with a SINGLE PBO over EVERY config, and report named mechanisms.

    §0.5 guards: (1) PBO deflates over the whole grid (models + feature cells), not just the 4
    classes; (2) all in-config nuisance fitting (the compound `s`/`λ`, the learned model fit) is
    TRAIN-fold-only inside the purged CV — config SELECTION is on pooled OOS (what PBO then
    deflates); (3) the grid is pre-registered/fixed — no reactive expansion (use
    incremental_lift_eval.py for any ADD test); (4) report the winning model×config, the full
    table, and the per-contrast mechanism."""
    splitter = PurgedWalkForwardSplit(min_train_seasons=2)
    assert_market_blind(_LEARNED_FEATURES, context="strikeout bake-off learned matrix")
    preds = {k: build_predictors(df, **v) for k, v in _COMPOUND_FEAT_CFGS.items()}
    learned_frame = preds["rate=recency_blend"]   # learned models read the raw recency features

    configs = []
    for fname in _COMPOUND_FEAT_CFGS:
        fr = preds[fname]
        configs.append((f"compound|{fname}", "compound", fname,
                        (lambda frame: (lambda p, tr, ev, r: _compound_samples(frame, tr, ev, r)))(fr), fr))
    configs.append(("lgbm_poisson_k", "lgbm_poisson_k", "recency(raw)", _lgbm_poisson_samples, learned_frame))
    configs.append(("poisson_glm_k", "poisson_glm_k", "recency(raw)", _poisson_glm_samples, learned_frame))

    results = {}
    for name, model, feat, sampler, frame in configs:
        print(f"  scoring {name} ...")
        r = _score_candidate(name, sampler, frame, splitter, rng)
        r["model"], r["feat"] = model, feat
        results[name] = r
        if r.get("ok"):
            print(f"    {name:<34} CRPS {r['crps']}  cov {r['coverage_80']}  pit_ks {r['pit_ks']}  ECE {r['mean_ece']}")

    ok = {k: v for k, v in results.items() if v.get("ok")}
    # (1) PBO deflates over the FULL grid — every model × feature-config is a trial.
    pbo = None
    names = [k for k in ok if ok[k]["fold_crps"]]
    if len(names) >= 2:
        L = min(len(ok[n]["fold_crps"]) for n in names)
        if L >= 2:
            mat = np.array([[-ok[n]["fold_crps"][i] for n in names] for i in range(L)])
            res = pbo_cscv(mat, higher_is_better=True, n_splits=min(8, L))
            pbo = {"pbo": round(float(res.pbo), 4), "n_configs": len(names), "n_folds": L,
                   "deflated_over": "full model×feature grid (not just model classes)"}
    # (4) winner = the (model × feature-config) with min CRPS among well-calibrated.
    calibrated = [k for k in ok if abs(ok[k]["coverage_80"] - 0.80) <= 0.04]
    if calibrated:
        winner = min(calibrated, key=lambda k: (ok[k]["crps"], ok[k]["pit_ks"]))
        winner_basis = "min CRPS among well-calibrated (|cov−0.80|≤0.04), over the full grid"
    elif ok:
        winner = min(ok, key=lambda k: (ok[k]["pit_ks"], abs(ok[k]["coverage_80"] - 0.80)))
        winner_basis = "none well-calibrated → best PIT-KS; calibration bar unmet (the finding)"
    else:
        winner, winner_basis = None, "no config scored"
    # Named mechanisms (paired-by-fold), all signed (WITH input − WITHOUT input) so a NEGATIVE ΔCRPS
    # consistently means "the named input HELPS" (lowers CRPS); positive = hurts; CI-spans-0 = inert.
    mechanisms = {
        "recency_vs_flat": _paired_delta(ok, "compound|rate=recency_blend", "compound|rate=season_career"),
        "framing_effect": _paired_delta(ok, "compound|rate=recency_blend", "compound|rate=recency_blend|no_framing"),
        "lineup_log5_effect": _paired_delta(ok, "compound|rate=recency_blend", "compound|rate=recency_blend|no_lineup"),
    }
    return {"results": results, "winner": winner, "winner_basis": winner_basis,
            "pbo": pbo, "mechanisms": mechanisms}


# ---------------------------------------------------------------------------
# Synthetic frame for --smoke (no Snowflake)
# ---------------------------------------------------------------------------

def _synthetic_frame(n: int, rng) -> pd.DataFrame:
    yrs = rng.choice([2021, 2022, 2023, 2024, 2025], size=n)
    mu_outs = rng.uniform(12, 21, n)
    bf_season = rng.uniform(50, 600, n); k_season = bf_season * rng.uniform(0.16, 0.30, n)
    bf_career = bf_season + rng.uniform(200, 3000, n); k_career = bf_career * rng.uniform(0.16, 0.28, n)
    outs_season = bf_season * rng.uniform(0.62, 0.70, n)
    p_true = np.clip(k_career / bf_career, .12, .34)
    outs = rng.poisson(mu_outs); reaches = rng.negative_binomial(np.clip(outs, 1, None), 1 - 0.31)
    bf_act = np.clip(outs, 1, None) + reaches
    k_act = rng.binomial(bf_act, rng.beta(p_true * 40, (1 - p_true) * 40))
    dates = pd.to_datetime("2021-04-01") + pd.to_timedelta(rng.integers(0, 1500, n), "D")
    return pd.DataFrame(dict(
        game_pk=np.arange(n), game_date=dates, game_year=yrs, pitcher_id=rng.integers(1, 400, n),
        side=rng.choice(["home", "away"], n), is_home_team=rng.choice([True, False], n),
        strikeouts=k_act.astype(float), batters_faced=bf_act.astype(float), outs_recorded=outs.astype(float),
        k_career=k_career, bf_career=bf_career, outs_career=bf_career * 0.66,
        k_season=k_season, bf_season=bf_season, outs_season=outs_season,
        starter_ip_mu=mu_outs, starter_ip_dispersion=rng.uniform(15, 40, n),
        opp_lineup_k_pct=rng.uniform(0.18, 0.28, n), catcher_framing_runs=rng.normal(0, 5, n),
        k_pct_7d=np.clip(p_true + rng.normal(0, 0.04, n), .08, .4),
        k_pct_30d=np.clip(p_true + rng.normal(0, 0.025, n), .08, .4),
        whiff_rate_30d=rng.uniform(.2, .35, n), csw_pct_3start=rng.uniform(.26, .34, n),
        velo_delta_3start=rng.normal(0, .5, n), fastball_velo_trend=rng.normal(0, .4, n),
    )).sort_values(["game_date", "game_pk", "side"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="E5.2 strikeout model-class + feature bake-off")
    ap.add_argument("--min-year", type=int, default=2021)
    ap.add_argument("--max-year", type=int, default=2026)
    ap.add_argument("--smoke", action="store_true", help="Run on a synthetic frame (no Snowflake).")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--refresh-cache", action="store_true",
                    help="Force a fresh Snowflake pull (else reuse the parquet frame cache the gate shares).")
    args = ap.parse_args()
    rng = np.random.default_rng(_SEED)

    print("=== E5.2 STRIKEOUT BAKE-OFF (model class + feature ablation; market-blind) ===")
    if args.smoke:
        print("[--smoke] synthetic frame")
        df = _synthetic_frame(6000, rng)
    else:
        # Same cached parquet frame the gate uses → Snowflake is hit ONCE across both runs.
        from betting_ml.scripts.prop_pricing.fit_prop_pricing import load_frame_cached
        df = load_frame_cached(args.min_year, args.max_year, refresh=args.refresh_cache)
        df = df.dropna(subset=["starter_ip_mu", "starter_ip_dispersion"]).reset_index(drop=True)
    print(f"  {len(df):,} starts")

    print("\n── Full bake-off grid (model class × feature config; ONE PBO over all) ──")
    grid = run_grid(df, rng)
    print(f"\n  WINNER: {grid['winner']}  ({grid.get('winner_basis')})")
    if grid["pbo"]:
        p = grid["pbo"]
        print(f"  PBO over the FULL grid ({p['n_configs']} configs × {p['n_folds']} folds) = {p['pbo']} "
              f"— {'overfit risk LOW (<0.2)' if p['pbo'] < 0.2 else 'overfit risk — interpret with care'}")
    print("\n  Mechanisms (paired-by-fold ΔCRPS; negative ⇒ the named input helps):")
    for k, m in grid["mechanisms"].items():
        if m:
            verdict = "REAL (CI excludes 0)" if m["excludes_zero"] else "inert (CI spans 0)"
            print(f"    {k:<20} ΔCRPS {m['mean_delta_crps']:+.4f} ±{2*m['sem']:.4f}  → {verdict}")

    if args.no_save:
        print("\n[--no-save] done.")
        return
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    doc = {"story": "E5.2-bakeoff", "fit_at": date.today().isoformat(),
           "smoke": args.smoke, "n_starts": int(len(df)), "grid": grid,
           "primary_metric": "CRPS (lower=better; proper, distribution-free)",
           "deflation": "PBO (CSCV) over EVERY model×feature config — the full pre-registered grid",
           "note": ("Forward-CV (fit prior seasons, eval next) is fixed for leak-honesty; recency is "
                    "in the FEATURES; nuisance params fit IN-FOLD; grid pre-registered (no reactive "
                    "expansion). best_alpha=0 — calibration/CRPS is product value; edge gate = E5.4.")}
    (_RESULTS_DIR / "e5_2_strikeout_bakeoff.json").write_text(json.dumps(doc, indent=2, default=float))
    _write_md(doc)
    print(f"\nResults → ablation_results/e5_2_strikeout_bakeoff.json")
    print("Next: promote the winning model×config into fit_prop_pricing (the served pricer), then "
          "E5.3 de-vig → E5.4 hard gate. The PBO already deflated over the full grid.")


def _write_md(doc: dict) -> None:
    g = doc["grid"]; rows = g["results"]
    lines = [
        "# E5.2 — Pitcher-strikeout model-class × feature bake-off",
        "",
        f"_Fit {doc['fit_at']}{' · SMOKE (synthetic)' if doc['smoke'] else ''} · {doc['n_starts']:,} starts · "
        f"purged walk-forward CV · primary = CRPS (lower better) · market-blind._",
        "",
        "## Why",
        "Closes two methodology gaps in the E5.2 first pass: (1) only one model class was tried; "
        "(2) the K-rate was a FLAT season+career average that ignores in-season stuff change. Forward "
        "CV stays (fit prior seasons / eval next = leak-honest); recency lives in the FEATURES.",
        "",
        "## §0.5 discipline",
        "- **One PBO over the FULL grid** — every model × feature config below is a trial the PBO "
        "deflates over (not just the model classes).",
        "- **In-fold nuisance fitting** — the compound `s`/`λ` and the learned model fits are TRAIN-fold "
        "only; config SELECTION is on pooled OOS (what PBO deflates).",
        "- **Pre-registered grid** — fixed axes, no reactive expansion (use `incremental_lift_eval.py` "
        "for any ADD test).",
        "- **DSR** is the E5.4 leg (deflates a CLV/ROI Sharpe); this bake-off is calibration/CRPS, so "
        "PBO is the selection-overfit guard here.",
        "",
        "## Full grid (model class × feature config)",
        "",
        "| config | model | features | CRPS | coverage@80 | PIT-KS | bias | mean ECE |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, r in rows.items():
        if r.get("ok"):
            lines.append(f"| {name} | {r.get('model')} | {r.get('feat')} | {r['crps']} | "
                         f"{r['coverage_80']} | {r['pit_ks']} | {r['bias']} | {r['mean_ece']} |")
        else:
            lines.append(f"| {name} | {r.get('model','?')} | {r.get('feat','?')} | (failed) | | | | |")
    p = g["pbo"]
    lines += [
        "",
        f"**Winner: `{g['winner']}`** — {g.get('winner_basis')}.",
        (f"**PBO over the full grid = {p['pbo']}** ({p['n_configs']} configs × {p['n_folds']} folds; "
         f"{p['deflated_over']}) — {'overfit risk LOW (<0.2)' if p['pbo'] < 0.2 else 'interpret with care'}."
         if p else "PBO: n/a (need ≥2 configs × ≥2 folds)."),
        "",
        "## Named mechanisms (paired-by-fold ΔCRPS; negative ⇒ the input helps)",
        "",
        "| contrast | mean ΔCRPS | ±2·SEM | verdict |",
        "|---|---|---|---|",
    ]
    for k, m in g["mechanisms"].items():
        if m:
            verdict = "REAL — CI excludes 0" if m["excludes_zero"] else "orthogonal-but-inert — CI spans 0"
            lines.append(f"| {k} | {m['mean_delta_crps']:+.4f} | {2*m['sem']:.4f} | {verdict} |")
        else:
            lines.append(f"| {k} | n/a | | (one side failed/too few folds) |")
    lines += [
        "",
        "## Read",
        "All contrasts signed **(WITH input − WITHOUT input)** → negative ΔCRPS = the input HELPS.",
        "- **recency_vs_flat** < 0 & CI excludes 0 ⇒ in-season recency genuinely helps (the gap the flat "
        "rate washed out); spans 0 ⇒ the flat season rate already carries it.",
        "- **framing_effect / lineup_log5_effect** < 0 & CI excludes 0 ⇒ the input earns its place; "
        "spans 0 ⇒ orthogonal-but-inert (keep documented, not assumed).",
        "- **Winner** = the (model × feature-config) cell, promoted into the served pricer "
        "(`fit_prop_pricing._RATE_MODE_DEFAULT`, or the learned class). Optuna-tune the WINNER only "
        "(the §0.5 exemplar `model_bakeoff → optuna_hpo`).",
        "",
        "> best_alpha = 0 — CRPS/calibration is PRODUCT value (projections), not an edge claim. The edge "
        "verdict is E5.4 (PBO<0.2 **AND DSR>0** per market, multiple-comparison-corrected, + forward CLV).",
    ]
    (_RESULTS_DIR / "e5_2_strikeout_bakeoff.md").write_text("\n".join(lines) + "\n")
    print(f"Bake-off record → ablation_results/e5_2_strikeout_bakeoff.md")


if __name__ == "__main__":
    main()
