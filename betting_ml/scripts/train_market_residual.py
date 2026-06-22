"""train_market_residual.py — Edge Program E13.1: market-anchored residual model.

HYPOTHESIS (pre-registered)
---------------------------
A model that predicts the RESIDUAL on top of the vig-free market line —
    P(home) = market_implied_devig + learned_residual(features)
finds mispriced spots better than predicting outcomes from scratch, and produces
positive forward CLV (the soft book's OWN close moves toward our lean).

KILL CRITERION (pre-registered)
-------------------------------
No positive forward CLV over >=100 games, net of vig + the PBO/DSR discipline →
kill the residual thesis and record it. CLV cannot be backtested into truth, so the
deliverable of THIS offline run is the *leading indicator* (historical CLV proxy +
ROI net of vig + PBO/DSR on the selected config) and a forward-validation plan — NOT
a go-live. Nothing deploys to users without clearing forward CLV first (best_alpha=0
honest framing): this is "spots the market misprices, proven by CLV," never a
"we predict games" claim.

PRIOR ART (read before trusting any positive number here)
---------------------------------------------------------
E4 (the cross-book sharp-anchor thesis) was KILLED 2026-06-18: the CLV signal was
REAL but ~0.5-0.9 prob-pts, FAR below the soft book's ~4% vig → CLV != cashable
profit, every ROI bucket negative. E13.1 is a DIFFERENT mechanism (feature-based
residual, not the raw cross-book gap), but the same trap applies — a positive CLV
proxy is meaningless until it clears vig. This script reports BOTH (CLV proxy AND
ROI net of an explicit hold) so the cashability question is answered head-on.

WHAT IT DOES
------------
For a --tier (post_lineup / pre_lineup), on the clean post-E1.8 home_win contract:
  1. Load the de-leaked training matrix; join mart_closing_line_value to attach the
     vig-free OPENING implied P(home) (`open_vf_home` = the morning bet-point ANCHOR)
     and `clv_home_ml` (= close - open vig-free P(home) = realized CLV truth).
  2. CONTRACT-GUARD: the FEATURE matrix X is market-blind (no odds columns). The market
     line enters ONLY as the additive anchor + as the residual target — it is
     point-in-time pre-game, so it is the anchor, never a leaked feature. (E13.1 is the
     market-AWARE exception to the market-blind rule.)
  3. Residual target z = home_win - open_vf_home. Fit residual regressors (GBM + GLM,
     plus hyperparam variants for an honest multiple-testing surface) under E1.1 PURGED
     CV. model_prob = clip(anchor + z_hat, eps, 1-eps).
  4. Also score the existing market-blind point model (XGB+Platt) and the anchor-only
     market floor as competing configs → answers "additive-to vs replace the point
     model" directly.
  5. Judge on FORWARD-style CLV (sign(lean) . clv_home_ml) by |lean| bucket + ROI net of
     an explicit vig hold (cashability) + PBO<0.2 (CSCV over the config slate) + DSR>0 on
     the EXCESS-over-drift return (drift = unconditional always-bet-home CLV, per the
     corrected E1.4 harness lesson). Accuracy (Brier vs the raw market line) is reported
     as a SECONDARY diagnostic, NOT the gate.

The XGBoost arms over multi-season purged folds make this a multi-minute job → HAND OFF
to the operator. `--smoke` caps rows/estimators/configs for a fast harness check.

Usage:
    uv run python betting_ml/scripts/train_market_residual.py --tier post_lineup
    uv run python betting_ml/scripts/train_market_residual.py --tier pre_lineup
    uv run python betting_ml/scripts/train_market_residual.py --smoke   # harness check
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.model_bakeoff import (
    _CONTRACTS, _assert_market_blind, _contract_cols, load_clean_matrix,
)
from betting_ml.scripts.promotion_gate_eval import (
    XGBPlattSpec, _impute, make_gate_splitter,
)
from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.feature_hygiene import is_identifier_name
from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv
from betting_ml.utils.promotion_gate import (
    NOISE_FLOOR, PredictiveOutput, brier, evaluate_promotion,
)

_REPORT_DIR = PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results"
_JSON_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "edge_residual"

_EPS = 1e-6
# |lean| thresholds (prob-pts) for the CLV-by-conviction sweep. tau=0 = bet every game.
_TAU_GRID = (0.0, 0.01, 0.02, 0.03, 0.05)
# Default total book hold for the ROI estimate (h2h moneyline, ~4.5% two-sided). This is the
# E4 cashability bar: the captured CLV must clear roughly half this per side to profit.
_DEFAULT_HOLD = 0.045


# ── CLV anchor/truth from mart_closing_line_value (one row per game_pk) ───────

_CLV_QUERY = """
SELECT game_pk, open_vf_home, close_vf_home, clv_home_ml, n_books_with_clv
FROM baseball_data.betting.mart_closing_line_value
WHERE open_vf_home IS NOT NULL AND clv_home_ml IS NOT NULL
"""


def _load_clv() -> pd.DataFrame:
    """Per-game vig-free opening anchor (`open_vf_home`) and realized CLV (`clv_home_ml`)."""
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_CLV_QUERY)
        cols = [c[0].lower() for c in cur.description]
        clv = pd.DataFrame(cur.fetchall(), columns=cols)
    finally:
        conn.close()
    for c in ("open_vf_home", "close_vf_home", "clv_home_ml"):
        clv[c] = pd.to_numeric(clv[c], errors="coerce")
    clv["game_pk"] = pd.to_numeric(clv["game_pk"], errors="coerce").astype("Int64")
    clv["n_books_with_clv"] = pd.to_numeric(clv["n_books_with_clv"], errors="coerce").fillna(0).astype(int)
    clv = clv.dropna(subset=["game_pk"])
    clv["game_pk"] = clv["game_pk"].astype("int64")
    return clv.dropna(subset=["open_vf_home", "clv_home_ml"]).reset_index(drop=True)


# ── residual learners (predict z = home_win - anchor) + the competing configs ──

@dataclass
class ResidualSpec:
    """A residual regressor: fit on (X, z=home_win-anchor); P(home)=clip(anchor+z_hat)."""
    name: str
    factory: object  # () -> sklearn-style regressor with fit/predict

    def model_prob(self, Xtr, ztr, Xev, anchor_ev, y_ev=None) -> np.ndarray:
        est = self.factory()
        est.fit(Xtr, ztr)
        z_hat = np.asarray(est.predict(Xev), float)
        return np.clip(anchor_ev + z_hat, _EPS, 1 - _EPS)


@dataclass
class AnchorFloor:
    """Market floor: P(home) = the vig-free opening line itself (z_hat == 0)."""
    name: str = "anchor_only_market"

    def model_prob(self, Xtr, ztr, Xev, anchor_ev, y_ev=None) -> np.ndarray:
        return np.clip(anchor_ev, _EPS, 1 - _EPS)


@dataclass
class PointModelSpec:
    """The EXISTING market-blind point model (XGB+Platt) scoring P(home) from scratch — the
    'replace' comparator. Its lean vs the anchor answers 'does the residual model add CLV
    beyond what the market-blind champion already captures?' (additive-to vs replace)."""
    name: str
    n_est: int
    seed: int

    def model_prob(self, Xtr, ytr, Xev, anchor_ev, y_ev=None) -> np.ndarray:
        spec = XGBPlattSpec({"n_estimators": self.n_est, "max_depth": 4, "learning_rate": 0.05,
                             "subsample": 0.8, "colsample_bytree": 0.8, "tree_method": "hist",
                             "eval_metric": "logloss", "random_state": self.seed, "n_jobs": -1},
                            name=self.name)
        # Platt-calibrate on the eval split with the BINARY eval labels (mirrors the bake-off
        # recipe). The anchor is irrelevant to the market-blind point model.
        out = spec.fit_predict(Xtr, ytr, Xev, y_ev)
        return np.clip(out.prob, _EPS, 1 - _EPS)


def _residual_configs(seed: int, smoke: bool) -> list[ResidualSpec]:
    """GBM + GLM residual learners, with a few hyperparam variants so PBO/DSR see an honest
    multiple-testing surface (a Sharpe/CLV picked from 1 config can't be deflated)."""
    from sklearn.linear_model import ElasticNet
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from xgboost import XGBRegressor

    n_est = 60 if smoke else 400

    def xgb(depth, lr):
        return ResidualSpec(
            f"gbm_d{depth}_lr{lr}",
            lambda: XGBRegressor(n_estimators=n_est, max_depth=depth, learning_rate=lr,
                                 subsample=0.8, colsample_bytree=0.8, tree_method="hist",
                                 random_state=seed, n_jobs=-1))

    def glm(alpha, l1):
        return ResidualSpec(
            f"glm_a{alpha}_l{l1}",
            lambda: make_pipeline(StandardScaler(),
                                  ElasticNet(alpha=alpha, l1_ratio=l1, random_state=seed)))

    if smoke:
        return [xgb(3, 0.05), glm(0.01, 0.5)]
    return [xgb(3, 0.05), xgb(4, 0.05), xgb(5, 0.03),
            glm(0.003, 0.5), glm(0.01, 0.5), glm(0.03, 0.2)]


# ── per-bet CLV proxy + ROI net of vig ───────────────────────────────────────

def _vig_roi(direction: np.ndarray, anchor: np.ndarray, home_win: np.ndarray, hold: float) -> np.ndarray:
    """Per-bet PnL (units, stake 1) of betting at the OPEN line, settling on the OUTCOME, net
    of an explicit two-sided book hold. direction = +1 bet home, -1 bet away. The book offers a
    price worse than fair by ~hold/2 per side: offered_decimal = fair_decimal / (1 + hold/2).

    This is the E4 cashability bar — captured CLV must clear the per-side vig to profit. It is
    an ESTIMATE (mart_closing_line_value stores vig-free probs, not the raw offered American
    price); the TRUE ROI gate is forward live. Reported alongside the vig-free CLV proxy.
    """
    p_side = np.where(direction > 0, anchor, 1.0 - anchor)
    p_side = np.clip(p_side, _EPS, 1 - _EPS)
    offered_dec = (1.0 / p_side) / (1.0 + hold / 2.0)
    won = np.where(direction > 0, home_win == 1, home_win == 0)
    return np.where(won, offered_dec - 1.0, -1.0)


def _clv_table(frame: pd.DataFrame, hold: float) -> list[dict]:
    """For one config's per-game frame, the |lean| sweep: n_bets, %CLV-positive, mean captured
    CLV (vig-free, prob-pts), and ROI net of vig. captured_clv = sign(lean) . clv_home_ml."""
    lean = frame["lean"].values
    clv = frame["clv_home_ml"].values
    anchor = frame["anchor"].values
    y = frame["home_win"].values
    direction = np.sign(lean)
    captured = direction * clv
    roi = _vig_roi(direction, anchor, y, hold)
    rows = []
    for tau in _TAU_GRID:
        m = np.abs(lean) > tau
        n = int(m.sum())
        rows.append({
            "tau": tau, "n_bets": n,
            "pct_clv_positive": float(np.mean(captured[m] > 0)) if n else float("nan"),
            "mean_captured_clv": float(np.mean(captured[m])) if n else float("nan"),
            "roi_net_vig": float(np.mean(roi[m])) if n else float("nan"),
        })
    return rows


def _per_season_clv(frame: pd.DataFrame, tau: float) -> dict:
    """Per-season %CLV-positive and mean captured CLV at a chosen conviction tau (forward-honesty:
    is the signal stable across seasons or a pooled mirage? — E4 found 2025 collapsed to noise)."""
    lean = frame["lean"].values
    captured = np.sign(lean) * frame["clv_home_ml"].values
    m = np.abs(lean) > tau
    sub = frame.loc[m].assign(_cap=captured[m])
    out = {}
    for yr, g in sub.groupby("game_year"):
        out[int(yr)] = {"n": int(len(g)),
                        "pct_clv_pos": float(np.mean(g["_cap"] > 0)),
                        "mean_captured_clv": float(g["_cap"].mean())}
    return out


# ── driver ───────────────────────────────────────────────────────────────────

def run(tier: str, *, seed: int, smoke: bool, refresh_cache: bool, embargo_days: int,
        hold: float, eval_tau: float) -> dict:
    df = load_clean_matrix(refresh_cache=refresh_cache, smoke=smoke)
    df["game_pk"] = pd.to_numeric(df["game_pk"], errors="coerce").astype("int64")
    clv = _load_clv()
    df = df.merge(clv, on="game_pk", how="inner").reset_index(drop=True)
    print(f"Joined CLV: {len(df)} games with vig-free open anchor + realized CLV "
          f"({df['game_year'].min()}-{df['game_year'].max()})")

    cols = _contract_cols("home_win", tier, df)
    _assert_market_blind(cols)  # FEATURES stay market-blind; the anchor is the only market input
    if any(is_identifier_name(c) for c in cols):
        raise SystemExit(f"❌ identifier column(s) in contract: {[c for c in cols if is_identifier_name(c)]}")
    contract_path = _CONTRACTS[tier]["home_win"]
    print(f"tier={tier} | {len(cols)} market-blind features | anchor=open_vf_home (vig-free)")

    resid = _residual_configs(seed, smoke)
    point_name = "point_model_market_blind"
    anchor_name = "anchor_only_market"
    point_spec = PointModelSpec(point_name, n_est=(60 if smoke else 400), seed=seed)
    anchor_spec = AnchorFloor(anchor_name)

    splitter, _ = make_gate_splitter(True, feature_cols=cols, embargo_days=embargo_days)
    folds = list(splitter(df))
    config_names = [s.name for s in resid] + [point_name, anchor_name]
    print(f"{len(config_names)} configs × {len(folds)} purged folds")

    # per-config long frame of eval-game outcomes
    recs: dict[str, list[pd.DataFrame]] = {n: [] for n in config_names}
    for tr, ev in folds:
        y_tr = df.loc[tr, "home_win"].values.astype(float)
        y_ev = df.loc[ev, "home_win"].values.astype(float)
        a_tr = df.loc[tr, "open_vf_home"].values.astype(float)
        a_ev = df.loc[ev, "open_vf_home"].values.astype(float)
        z_tr = y_tr - a_tr
        Xtr, Xev = _impute(df.loc[tr, cols], df.loc[ev, cols])
        meta = df.loc[ev, ["game_pk", "game_year", "game_date", "home_win", "open_vf_home", "clv_home_ml"]].copy()
        meta = meta.rename(columns={"open_vf_home": "anchor"})
        # year-month bucket for PBO/CSCV — season alone gives only ~3 eval buckets (< the 4
        # CSCV needs); month granularity yields ~18 so the slate has a real partition surface.
        meta["ym"] = (meta["game_year"].astype(int).astype(str) + "-"
                      + pd.to_datetime(meta["game_date"]).dt.month.astype(str).str.zfill(2))

        def _stash(name, prob):
            f = meta.copy()
            f["model_prob"] = prob
            f["lean"] = prob - a_ev  # >0 ⇒ we think home is underpriced vs the open line
            recs[name].append(f)

        for s in resid:
            _stash(s.name, s.model_prob(Xtr, z_tr, Xev, a_ev, y_ev))
        _stash(point_name, point_spec.model_prob(Xtr, y_tr, Xev, a_ev, y_ev))
        _stash(anchor_name, anchor_spec.model_prob(Xtr, z_tr, Xev, a_ev, y_ev))

    frames = {n: pd.concat(recs[n], ignore_index=True) for n in config_names}

    # ── accuracy (SECONDARY): Brier vs the raw market line, gated honestly ───────
    anchor_frame = frames[anchor_name]
    anchor_brier = brier(anchor_frame["home_win"].values, anchor_frame["anchor"].values)
    accuracy = {}
    for n in config_names:
        fr = frames[n]
        chal_brier = brier(fr["home_win"].values, fr["model_prob"].values)
        # align to anchor rows (same eval set, same order across configs by construction)
        verdict = evaluate_promotion(
            season=fr["game_year"].values.astype(int),
            champion_score=anchor_brier, challenger_score=chal_brier,
            metric="brier", current_season=int(fr["game_year"].max()))
        accuracy[n] = {"brier_mean": float(np.mean(chal_brier)),
                       "delta_vs_market": float(np.mean(chal_brier) - np.mean(anchor_brier)),
                       "beats_market": verdict.decision == "PROMOTE",
                       "decision": verdict.decision}

    # ── CLV proxy + ROI net of vig (PRIMARY) ────────────────────────────────────
    clv_by_config = {n: _clv_table(frames[n], hold) for n in config_names}
    season_by_config = {n: _per_season_clv(frames[n], eval_tau) for n in config_names}

    # ── select the winning RESIDUAL config: best mean captured CLV at eval_tau ───
    def _captured_at_tau(name, tau):
        fr = frames[name]
        m = np.abs(fr["lean"].values) > tau
        if not m.any():
            return float("nan")
        return float(np.mean(np.sign(fr["lean"].values[m]) * fr["clv_home_ml"].values[m]))

    resid_names = [s.name for s in resid]
    winner = max(resid_names, key=lambda n: (_captured_at_tau(n, eval_tau)
                                             if _captured_at_tau(n, eval_tau) == _captured_at_tau(n, eval_tau)
                                             else -1e9))

    # ── PBO across the config slate (CSCV) on a (month × config) captured-CLV matrix ─
    # higher captured CLV is better. Build per-(year-month) mean captured CLV per config.
    def _bucket_captured(name):
        fr = frames[name].copy()
        m = np.abs(fr["lean"].values) > eval_tau
        fr = fr.loc[m]
        cap = np.sign(fr["lean"].values) * fr["clv_home_ml"].values
        return pd.Series(cap).groupby(fr["ym"].values).mean()  # per year-month bucket
    slate = resid_names + [point_name]  # anchor floor excluded (degenerate: lean≡0)
    season_keys = sorted(set().union(*[set(_bucket_captured(n).index) for n in slate]))
    perf = np.array([[_bucket_captured(n).get(k, np.nan) for n in slate] for k in season_keys])
    keep = ~np.isnan(perf).any(axis=1)
    pbo_val = float("nan")
    if keep.sum() >= 4 and len(slate) >= 2:
        pres = pbo_cscv(perf[keep], higher_is_better=True,
                        n_splits=min(16, keep.sum() - (keep.sum() % 2)))
        pbo_val = float(pres.pbo)

    # ── DSR on the EXCESS-over-drift return of the winner (corrected E1.4 harness) ─
    # drift baseline = unconditional always-bet-home captured CLV (= clv_home_ml itself).
    # excess = winner's captured CLV − always-home CLV, per bet, at eval_tau.
    fw = frames[winner]
    mw = np.abs(fw["lean"].values) > eval_tau
    cap_win = np.sign(fw["lean"].values[mw]) * fw["clv_home_ml"].values[mw]
    drift = fw["clv_home_ml"].values[mw]  # always-bet-home capture (direction ≡ +1)
    excess = cap_win - drift
    # per-config trial Sharpes (excess vs drift) estimate cross-trial SR dispersion V
    trial_srs = []
    for n in slate:
        fr = frames[n]; m = np.abs(fr["lean"].values) > eval_tau
        if m.sum() >= 3:
            ex = np.sign(fr["lean"].values[m]) * fr["clv_home_ml"].values[m] - fr["clv_home_ml"].values[m]
            sd = ex.std(ddof=0)
            trial_srs.append(float(ex.mean() / sd) if sd > 0 else 0.0)
    dsr_res = None
    if len(excess) >= 3:
        dsr_res = deflated_sharpe(excess, n_trials=max(len(slate), 1),
                                  trial_sharpes=trial_srs if len(trial_srs) > 1 else None)

    # ── verdict (honest framing: forward CLV is the real gate; this is the leading read) ─
    win_clv = next(r for r in clv_by_config[winner] if r["tau"] == eval_tau)
    pbo_ok = pbo_val == pbo_val and pbo_val < 0.2
    dsr_ok = bool(dsr_res and dsr_res.dsr > 0.5)  # >0 in the spec sense = better-than-even excess
    clv_pos = win_clv["mean_captured_clv"] > 0 and win_clv["roi_net_vig"] > 0
    if clv_pos and pbo_ok and dsr_ok:
        verdict = "PROMISING → forward-validate"
        rationale = ("positive in-sample CLV proxy AND ROI clears the modeled vig AND PBO<0.2 / "
                     "DSR-excess>even. NOT a go-live — CLV can't be backtested into truth; "
                     "advance to the >=100-game forward-CLV plan below.")
    elif win_clv["mean_captured_clv"] > 0 and not clv_pos:
        verdict = "KILL (CLV ≠ cashable)"
        rationale = ("CLV proxy positive but ROI net of vig <=0 — the captured CLV does NOT clear "
                     "the book hold. Same failure mode as the E4 kill (2026-06-18). Record and stop.")
    else:
        verdict = "KILL (no CLV edge)"
        rationale = ("no positive in-sample CLV proxy on the selected config under purged CV — the "
                     "residual lean does not anticipate the close. Record the kill.")

    result = {
        "story": "E13.1", "tier": tier, "seed": seed, "smoke": smoke,
        "n_games": int(len(df)), "season_range": [int(df["game_year"].min()), int(df["game_year"].max())],
        "n_features": len(cols), "n_folds": len(folds), "contract": contract_path,
        "hold": hold, "eval_tau": eval_tau, "noise_floor_brier": NOISE_FLOOR.get("brier"),
        "anchor_brier_mean": float(np.mean(anchor_brier)),
        "winner": winner,
        "accuracy_secondary": accuracy,
        "clv_proxy_by_config": clv_by_config,
        "per_season_clv": season_by_config,
        "pbo_slate": pbo_val,
        "dsr": (None if dsr_res is None else {
            "dsr": dsr_res.dsr, "observed_sr": dsr_res.observed_sr, "sr0": dsr_res.sr0,
            "n_trials": dsr_res.n_trials, "n_obs": dsr_res.n_obs}),
        "winner_clv_at_eval_tau": win_clv,
        "verdict": verdict, "rationale": rationale,
    }
    _write_report(result)
    return result


def _write_report(result: dict) -> None:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True); _JSON_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"edge_residual_home_win_{result['tier']}" + ("_smoke" if result["smoke"] else "")
    (_JSON_DIR / f"{stem}.json").write_text(json.dumps(result, indent=2, default=float))

    w = result["winner"]; tau = result["eval_tau"]
    wc = result["winner_clv_at_eval_tau"]
    L = [
        f"# Market-Anchored Residual Model — home_win ({result['tier']})  [E13.1]", "",
        ("⚠️ **SMOKE** (capped rows/estimators — harness check, NOT a result)." if result["smoke"] else
         f"{result['n_games']} games {result['season_range'][0]}–{result['season_range'][1]} · "
         f"{result['n_features']} market-blind feats · {result['n_folds']} purged folds · "
         f"anchor = vig-free opening P(home) · ROI hold = {result['hold']:.3f}"),
        "",
        f"## Verdict: **{result['verdict']}**",
        f"_{result['rationale']}_", "",
        f"- **Winning residual config:** `{w}`",
        f"- At |lean| > {tau}: **{wc['n_bets']} bets**, "
        f"{wc['pct_clv_positive']*100:.1f}% CLV-positive, "
        f"mean captured CLV **{wc['mean_captured_clv']*100:+.2f} prob-pts**, "
        f"**ROI net of vig {wc['roi_net_vig']*100:+.2f}%**",
        f"- PBO across slate (CSCV): **{result['pbo_slate']:.3f}**"
        + ("  ✅ <0.2" if result['pbo_slate'] == result['pbo_slate'] and result['pbo_slate'] < 0.2
           else "  ⚠️ ≥0.2 (selection may be overfit)" if result['pbo_slate'] == result['pbo_slate'] else "  (n/a)"),
    ]
    if result["dsr"]:
        d = result["dsr"]
        L.append(f"- DSR on excess-over-drift return: **{d['dsr']:.3f}** "
                 f"(SR={d['observed_sr']:+.3f} vs SR0={d['sr0']:+.3f}, n_trials={d['n_trials']}, n={d['n_obs']})")
    L += ["",
          "## CLV proxy by conviction (winner) — captured = sign(lean)·clv_home_ml",
          "| |lean|> | n_bets | %CLV-pos | mean captured CLV | ROI net vig |",
          "|---|---|---|---|---|"]
    for r in result["clv_proxy_by_config"][w]:
        pc = "—" if r["pct_clv_positive"] != r["pct_clv_positive"] else f"{r['pct_clv_positive']*100:.1f}%"
        mc = "—" if r["mean_captured_clv"] != r["mean_captured_clv"] else f"{r['mean_captured_clv']*100:+.2f}pp"
        ro = "—" if r["roi_net_vig"] != r["roi_net_vig"] else f"{r['roi_net_vig']*100:+.2f}%"
        L.append(f"| {r['tau']} | {r['n_bets']} | {pc} | {mc} | {ro} |")

    L += ["", "## Per-season CLV (winner, at eval τ) — forward-honesty / stability check",
          "| season | n | %CLV-pos | mean captured CLV |", "|---|---|---|---|"]
    for yr, s in sorted(result["per_season_clv"][w].items()):
        L.append(f"| {yr} | {s['n']} | {s['pct_clv_pos']*100:.1f}% | {s['mean_captured_clv']*100:+.2f}pp |")

    L += ["", "## Additive-to vs replace — CLV proxy at eval τ, all configs",
          "| config | %CLV-pos | mean captured CLV | ROI net vig | Brier vs market | beats mkt? |",
          "|---|---|---|---|---|---|"]
    for n, rows in result["clv_proxy_by_config"].items():
        r = next(x for x in rows if x["tau"] == tau)
        acc = result["accuracy_secondary"][n]
        pc = "—" if r["pct_clv_positive"] != r["pct_clv_positive"] else f"{r['pct_clv_positive']*100:.1f}%"
        mc = "—" if r["mean_captured_clv"] != r["mean_captured_clv"] else f"{r['mean_captured_clv']*100:+.2f}pp"
        ro = "—" if r["roi_net_vig"] != r["roi_net_vig"] else f"{r['roi_net_vig']*100:+.2f}%"
        L.append(f"| `{n}` | {pc} | {mc} | {ro} | {acc['delta_vs_market']:+.4f} | "
                 f"{'✅' if acc['beats_market'] else ''} |")

    L += ["",
          "## Forward-validation plan (CLV cannot be backtested into truth)",
          f"- Score the `{w}` residual config live each morning (post-A1.11 serving), log lean + the "
          "OPEN vig-free line per game.",
          "- At close, record `clv_home_ml`; accrue captured CLV + ROI net of vig over a rolling window.",
          "- **Gate (pre-registered):** >=100 forward games with POSITIVE captured CLV *and* ROI clearing "
          "the real book hold → promote to advisory. Else KILL the residual thesis.",
          "- Honest framing (best_alpha=0): advisory is \"spots the market misprices, proven by CLV,\" "
          "never \"we predict games.\" No auto-betting.",
          "",
          "_Offline CLV/ROI here is the LEADING indicator + discipline check, NOT a go-live. E4 (the "
          "cross-book thesis) had a real CLV signal that died at the vig — read the ROI column, not the "
          "CLV column, before believing this._"]
    (_REPORT_DIR / f"{stem}.md").write_text("\n".join(L))
    print(f"\nWrote {_REPORT_DIR / f'{stem}.md'}")
    print(f"→ winner={w} | verdict={result['verdict']} | "
          f"captured_clv={wc['mean_captured_clv']*100:+.2f}pp | roi={wc['roi_net_vig']*100:+.2f}% | "
          f"PBO={result['pbo_slate']:.3f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", choices=list(_CONTRACTS), default="post_lineup")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--embargo-days", type=int, default=3)
    ap.add_argument("--hold", type=float, default=_DEFAULT_HOLD,
                    help="Two-sided book hold for the ROI-net-of-vig estimate (default 0.045).")
    ap.add_argument("--eval-tau", type=float, default=0.02,
                    help="|lean| conviction threshold (prob-pts) the verdict/PBO/DSR are read at.")
    ap.add_argument("--refresh-cache", action="store_true")
    ap.add_argument("--smoke", action="store_true",
                    help="Cap rows/estimators/configs for a fast end-to-end harness check.")
    args = ap.parse_args()
    run(args.tier, seed=args.seed, smoke=args.smoke, refresh_cache=args.refresh_cache,
        embargo_days=args.embargo_days, hold=args.hold, eval_tau=args.eval_tau)


if __name__ == "__main__":
    main()
