"""
h2h_bradley_terry_nuts.py — Epic 28, Story 28.5

Hierarchical Bayesian Bradley-Terry (paired-comparison) H2H model. Reopens the
H2H *architecture* after Story 28.4 showed feature augmentation on the XGBoost
classifier could not clear the sharp 2026 market (credible-2026 model Brier 0.223
vs market 0.187).

WHY A PAIRED-COMPARISON LIKELIHOOD
----------------------------------
The totals models hit a structural Jensen floor: a log-link NegBin on per-side
run *counts*, aggregated to a game total, systematically over-predicts because
E[exp(βz)] > exp(βE[z]). H2H has no count aggregation — the outcome is a single
Bernoulli with a logit link:

    P(home win) = σ(s_home − s_away + hfa_home)

so there is NO Jensen floor. The ceiling here is signal quality + calibration,
which a hierarchical paired-comparison model with partially-pooled team strength
and team-specific home-field advantage can address directly.

MODEL (non-centered reparameterization on every hierarchical term — required to
hit the divergence/ESS gates):

    sigma_team      ~ HalfNormal(0.5)
    z_team          = z_team_raw · sigma_team,      z_team_raw ~ Normal(0,1)[team]
    league_hfa      ~ Normal(0.10, 0.10)            (≈ logit home edge; e.g. 0.10 → ~52.5%)
    sigma_hfa       ~ HalfNormal(0.10)
    hfa_team        = league_hfa + hfa_raw·sigma_hfa, hfa_raw ~ Normal(0,1)[team]
    beta_off/bull/start/rd_sigma ~ Normal(0, 0.5)

    s_home = z_team[home] + β_off·off^h + β_bull·bull^h + β_start·start^h
    s_away = z_team[away] + β_off·off^a + β_bull·bull^a + β_start·start^a
    logit  = (s_home − s_away) + hfa_team[home] + β_rd_sigma·run_diff_sigma_z
    home_win ~ Bernoulli(σ(logit))

The partially-pooled Normal prior on z_team IS the continuous analogue of the
Beta-Binomial prior-strength shrinkage the icebox calls for (Task 3): teams with
little signal are shrunk toward the league mean (0); sigma_team is the learned
pooling strength. hfa_team realises the hierarchical-HFA icebox item.

SUB-MODEL COVARIATES (offense_v2, bullpen_v2, starter_v1, run_diff μ/σ), all
leakage-free walk-forward OOS signals (the same parquets the totals NUTS model
and the leakage-free H2H matrix consume):
  - offense (pred_runs_mu_v2)        → per side, on team strength
  - bullpen (bullpen_mu_v2)          → per side (own staff), on team strength
  - starter (starter_suppression_mu_v1) → per side (own staff), on team strength
  - run_diff μ → STRUCTURALLY ABSORBED. Under the logit link the offense term
        β_off·(off^h − off^a) already *is* the run-diff-mean signal (run_diff_mu =
        home_off − away_off is an affine function of off^h − off^a, sharing one
        scaler). Adding run_diff_mu as a separate regressor would be perfectly
        collinear and destroy ESS / induce divergences — exactly the convergence
        gate this story must pass. It is therefore folded into β_off, not duplicated.
  - run_diff σ → run_diff_sigma_z, a genuine *conviction* covariate (predicted
        total-run scale, sqrt(off^h + off^a)); NOT collinear with the means.

TRAIN 2022–2025 (2021 excluded — run_env walk-forward floor, same as the totals
NUTS model). SCORE 2026 OOS. Evaluate L1/L2/L3 + Layer 4 vs the XGBoost champion
(oos_predictions_h2h_v2.parquet) and the credible 2026 Parlay market on the SAME
games. PROMOTE ONLY if it beats BOTH the champion AND closes toward the market.

Usage (HAND-OFF — Snowflake load + NUTS; expect several minutes to ~1-2 hr):
  uv run python betting_ml/models/bayesian/h2h_bradley_terry_nuts.py

Outputs:
  betting_ml/models/bayesian/h2h_bt_trace.nc
  betting_ml/models/bayesian/h2h_bt_summary.json
  betting_ml/models/layer3/oos_predictions_h2h_bt_28_5.parquet
  quant_sports_intel_models/baseball/ablation_results/h2h_bradley_terry_28_5.md
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_PROJECT_ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_BAYESIAN_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "bayesian"
_LAYER3_DIR   = _PROJECT_ROOT / "betting_ml" / "models" / "layer3"
_ABLATION_DIR = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results"

_TRACE_PATH    = _BAYESIAN_DIR / "h2h_bt_trace.nc"
_SUMMARY_PATH  = _BAYESIAN_DIR / "h2h_bt_summary.json"
_OOS_PRED_PATH = _LAYER3_DIR / "oos_predictions_h2h_bt_28_5.parquet"
_REPORT_PATH   = _ABLATION_DIR / "h2h_bradley_terry_28_5.md"
_CHAMPION_PARQUET = _LAYER3_DIR / "oos_predictions_h2h_v2.parquet"
_ISOTONIC_PATH    = _LAYER3_DIR / "isotonic_h2h.pkl"

# Reuse the leakage-free data-prep from the totals NUTS / ADVI pipeline verbatim.
from betting_ml.models.bayesian.run_scoring_advi import (  # noqa: E402
    _load_oos_signals,
    _load_game_results,
    _expand_to_sides,
    _build_training_frame,
)

_TRAIN_SEASONS = [2022, 2023, 2024, 2025]  # 2021 excluded: run_env walk-forward floor
_OOS_SEASON = 2026

# NUTS settings — Bernoulli likelihood over ~7k games is light; these are ample.
_N_DRAWS  = 2000
_N_TUNE   = 1500
_N_CHAINS = 4
_TARGET_ACCEPT = 0.95
_SEED = 42

# Convergence gates (Acceptance criterion 1).
_RHAT_MAX = 1.01
_ESS_MIN  = 400
_DIVERGENCES_MAX = 5

# A credible sharp h2h market lands ≈0.18-0.22 Brier; ≥0.235 is a degraded/near-flat
# baseline (the 2024-25 historical Odds-API Bovada h2h snapshots). Only the credible
# 2026 Parlay surface counts toward the verdict (reference_bovada_h2h_line_quality).
_SANE_MARKET_BRIER_MAX = 0.235
_MARKET_TARGET_BRIER = 0.182  # the sharp-band target the model must close toward


# ---------------------------------------------------------------------------
# Data prep: per-side leakage-free signals → game-level Bradley-Terry frame
# ---------------------------------------------------------------------------

def _prepare_game_frame() -> tuple[pd.DataFrame, list[str], dict]:
    """Build the game-level BT frame with z-scored covariates.

    Returns (game_df, teams, scaler_stats). game_df has one row per game with:
      game_pk, season, game_date, home_team, away_team, home_win,
      home_off_z, away_off_z, home_bull_z, away_bull_z,
      home_start_z, away_start_z, run_diff_sigma_z,
      home_team_idx, away_team_idx.

    All scalers are fit on TRAINING (2022-2025) rows only and pool both sides of
    each signal so β is shared symmetrically across home/away.
    """
    log.info("[data] Loading leakage-free OOS signals + game results...")
    signals = _load_oos_signals()
    games   = _load_game_results(_TRAIN_SEASONS + [_OOS_SEASON])
    sides   = _expand_to_sides(games)
    frame   = _build_training_frame(signals, sides)
    # frame is per-(game_pk, side) with: pred_runs_mu (own offense), opp_bullpen_mu,
    # opp_starter_mu (the OPPONENT's staff facing this side), runs_scored,
    # batting_team, home_team, season, game_date, side.

    home = frame[frame["side"] == "home"].set_index("game_pk")
    away = frame[frame["side"] == "away"].set_index("game_pk")
    common = home.index.intersection(away.index)
    home, away = home.loc[common], away.loc[common]
    log.info("[data] %d games with both sides present", len(common))

    g = pd.DataFrame(index=common)
    g["season"]    = home["season"]
    g["game_date"] = home["game_date"]
    g["home_team"] = home["batting_team"]
    g["away_team"] = away["batting_team"]
    g["home_win"]  = (home["runs_scored"] > away["runs_scored"]).astype(int)

    # ── Map per-side signals to team-strength covariates ──────────────────────
    # Own offense:
    g["home_off"] = home["pred_runs_mu"]
    g["away_off"] = away["pred_runs_mu"]
    # Own pitching staff = the OPPONENT-row's "opp_*" (the staff the opposing
    # batters face). home's bullpen/starter = the staff the AWAY batters face =
    # away-row's opp_bullpen_mu / opp_starter_mu, and vice-versa.
    g["home_bull"]  = away["opp_bullpen_mu"]
    g["home_start"] = away["opp_starter_mu"]
    g["away_bull"]  = home["opp_bullpen_mu"]
    g["away_start"] = home["opp_starter_mu"]
    # run_diff conviction (σ): predicted total-run scale (NOT collinear with means).
    g["run_diff_sigma"] = np.sqrt(g["home_off"].clip(lower=0) + g["away_off"].clip(lower=0))

    g = g.dropna(subset=["home_off", "away_off", "home_bull", "away_bull",
                         "home_start", "away_start", "run_diff_sigma"]).reset_index()
    g = g.rename(columns={"index": "game_pk"})
    g["game_pk"] = g["game_pk"].astype(int)

    train_mask = g["season"].isin(_TRAIN_SEASONS)

    # ── Pooled z-scoring (fit on 2022-2025, both sides) ───────────────────────
    def _pool_scaler(col_pair: tuple[str, str]) -> tuple[float, float]:
        vals = pd.concat([g.loc[train_mask, col_pair[0]], g.loc[train_mask, col_pair[1]]])
        return float(vals.mean()), float(vals.std(ddof=0))

    off_mean, off_std     = _pool_scaler(("home_off", "away_off"))
    bull_mean, bull_std   = _pool_scaler(("home_bull", "away_bull"))
    start_mean, start_std = _pool_scaler(("home_start", "away_start"))
    rds_mean = float(g.loc[train_mask, "run_diff_sigma"].mean())
    rds_std  = float(g.loc[train_mask, "run_diff_sigma"].std(ddof=0))

    def _z(col, m, s):
        return (g[col] - m) / (s if s > 1e-9 else 1.0)

    g["home_off_z"]  = _z("home_off", off_mean, off_std)
    g["away_off_z"]  = _z("away_off", off_mean, off_std)
    g["home_bull_z"] = _z("home_bull", bull_mean, bull_std)
    g["away_bull_z"] = _z("away_bull", bull_mean, bull_std)
    g["home_start_z"]= _z("home_start", start_mean, start_std)
    g["away_start_z"]= _z("away_start", start_mean, start_std)
    g["run_diff_sigma_z"] = _z("run_diff_sigma", rds_mean, rds_std)

    # ── Team index from TRAINING teams (OOS uses same mapping) ─────────────────
    teams = sorted(set(g.loc[train_mask, "home_team"].dropna()) |
                   set(g.loc[train_mask, "away_team"].dropna()))
    team_to_idx = {t: i for i, t in enumerate(teams)}
    g["home_team_idx"] = g["home_team"].map(team_to_idx)
    g["away_team_idx"] = g["away_team"].map(team_to_idx)
    before = len(g)
    g = g.dropna(subset=["home_team_idx", "away_team_idx"]).reset_index(drop=True)
    if before - len(g):
        log.warning("[data] dropped %d games with an unseen team", before - len(g))
    g["home_team_idx"] = g["home_team_idx"].astype(int)
    g["away_team_idx"] = g["away_team_idx"].astype(int)

    scaler_stats = {
        "offense":  {"mean": off_mean, "std": off_std},
        "bullpen":  {"mean": bull_mean, "std": bull_std},
        "starter":  {"mean": start_mean, "std": start_std},
        "run_diff_sigma": {"mean": rds_mean, "std": rds_std},
    }
    log.info("[data] scaler z-score check (train): off mean=%.3f std=%.3f | "
             "bull mean=%.3f std=%.3f | start mean=%.3f std=%.3f",
             float(g.loc[g["season"].isin(_TRAIN_SEASONS), "home_off_z"].mean()),
             float(g.loc[g["season"].isin(_TRAIN_SEASONS), "home_off_z"].std()),
             float(g.loc[g["season"].isin(_TRAIN_SEASONS), "home_bull_z"].mean()),
             float(g.loc[g["season"].isin(_TRAIN_SEASONS), "home_bull_z"].std()),
             float(g.loc[g["season"].isin(_TRAIN_SEASONS), "home_start_z"].mean()),
             float(g.loc[g["season"].isin(_TRAIN_SEASONS), "home_start_z"].std()))
    log.info("[data] games: %d train (2022-25) + %d OOS (2026); %d teams",
             int(g["season"].isin(_TRAIN_SEASONS).sum()),
             int((g["season"] == _OOS_SEASON).sum()), len(teams))
    return g, teams, scaler_stats


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def build_bt_model(train_df: pd.DataFrame, teams: list[str]):
    """Hierarchical Bradley-Terry, non-centered on every hierarchical term."""
    import pymc as pm

    coords = {"team": teams}
    h_idx = train_df["home_team_idx"].values
    a_idx = train_df["away_team_idx"].values

    home_off_z   = train_df["home_off_z"].values
    away_off_z   = train_df["away_off_z"].values
    home_bull_z  = train_df["home_bull_z"].values
    away_bull_z  = train_df["away_bull_z"].values
    home_start_z = train_df["home_start_z"].values
    away_start_z = train_df["away_start_z"].values
    rd_sigma_z   = train_df["run_diff_sigma_z"].values
    y = train_df["home_win"].values.astype(int)

    with pm.Model(coords=coords) as model:
        # ── Hierarchical team strength (non-centered) ─────────────────────────
        sigma_team = pm.HalfNormal("sigma_team", sigma=0.5)
        z_team_raw = pm.Normal("z_team_raw", mu=0.0, sigma=1.0, dims="team")
        z_team = pm.Deterministic("z_team", z_team_raw * sigma_team, dims="team")

        # ── Hierarchical team-specific HFA (non-centered) ─────────────────────
        league_hfa = pm.Normal("league_hfa", mu=0.10, sigma=0.10)
        sigma_hfa  = pm.HalfNormal("sigma_hfa", sigma=0.10)
        hfa_raw    = pm.Normal("hfa_raw", mu=0.0, sigma=1.0, dims="team")
        hfa_team   = pm.Deterministic("hfa_team", league_hfa + hfa_raw * sigma_hfa, dims="team")

        # ── Shared signal coefficients (partial pooling of effects) ───────────
        beta_off      = pm.Normal("beta_off",      mu=0.0, sigma=0.5)
        beta_bull     = pm.Normal("beta_bull",     mu=0.0, sigma=0.5)
        beta_start    = pm.Normal("beta_start",    mu=0.0, sigma=0.5)
        beta_rd_sigma = pm.Normal("beta_rd_sigma", mu=0.0, sigma=0.5)

        s_home = (z_team[h_idx]
                  + beta_off * home_off_z
                  + beta_bull * home_bull_z
                  + beta_start * home_start_z)
        s_away = (z_team[a_idx]
                  + beta_off * away_off_z
                  + beta_bull * away_bull_z
                  + beta_start * away_start_z)

        logit_p = (s_home - s_away) + hfa_team[h_idx] + beta_rd_sigma * rd_sigma_z
        pm.Bernoulli("home_win", logit_p=logit_p, observed=y)

    return model


def run_nuts(model):
    import pymc as pm
    log.info("[nuts] sampling %d chains × %d draws (+%d tune), target_accept=%.2f",
             _N_CHAINS, _N_DRAWS, _N_TUNE, _TARGET_ACCEPT)
    with model:
        trace = pm.sample(
            draws=_N_DRAWS, tune=_N_TUNE, chains=_N_CHAINS,
            target_accept=_TARGET_ACCEPT, random_seed=_SEED,
            progressbar=True, return_inferencedata=True,
        )
    return trace


def check_diagnostics(trace) -> dict:
    import arviz as az
    divergences = int(trace.sample_stats["diverging"].values.sum())
    summary = az.summary(trace, var_names=[
        "sigma_team", "league_hfa", "sigma_hfa",
        "beta_off", "beta_bull", "beta_start", "beta_rd_sigma",
    ])
    log.info("\n[diag] key scalars:\n%s", summary.to_string())

    full = az.summary(trace)  # all params incl. per-team
    rhat = float(np.nanmax(full["r_hat"].values)) if "r_hat" in full else float("nan")
    ess  = float(np.nanmin(full["ess_bulk"].values)) if "ess_bulk" in full else float("nan")

    rhat_ok = rhat < _RHAT_MAX
    ess_ok  = ess > _ESS_MIN
    div_ok  = divergences <= _DIVERGENCES_MAX
    log.info("[diag] max R-hat=%.4f (<%.2f %s) | min ESS_bulk=%.0f (>%d %s) | "
             "divergences=%d (<=%d %s)",
             rhat, _RHAT_MAX, "OK" if rhat_ok else "FAIL",
             ess, _ESS_MIN, "OK" if ess_ok else "FAIL",
             divergences, _DIVERGENCES_MAX, "OK" if div_ok else "FAIL")
    return {
        "max_rhat": rhat, "min_ess_bulk": ess, "divergences": divergences,
        "rhat_ok": rhat_ok, "ess_ok": ess_ok, "div_ok": div_ok,
        "converged": rhat_ok and ess_ok and div_ok,
        "betas": {k: float(summary.loc[k, "mean"]) for k in
                  ["beta_off", "beta_bull", "beta_start", "beta_rd_sigma"]},
    }


# ---------------------------------------------------------------------------
# Posterior scoring
# ---------------------------------------------------------------------------

def score_games(trace, df: pd.DataFrame) -> np.ndarray:
    """Posterior-mean P(home win) for each row of df (vectorized over draws)."""
    post = trace.posterior
    n_samples = post.sizes["chain"] * post.sizes["draw"]
    n_teams = post.sizes["team"]

    z_team   = post["z_team"].values.reshape(n_samples, n_teams)
    hfa_team = post["hfa_team"].values.reshape(n_samples, n_teams)
    b_off    = post["beta_off"].values.reshape(n_samples)
    b_bull   = post["beta_bull"].values.reshape(n_samples)
    b_start  = post["beta_start"].values.reshape(n_samples)
    b_rds    = post["beta_rd_sigma"].values.reshape(n_samples)

    h = df["home_team_idx"].values
    a = df["away_team_idx"].values

    def col(name):
        return df[name].values[None, :]  # (1, n_games)

    s_home = (z_team[:, h]
              + b_off[:, None] * col("home_off_z")
              + b_bull[:, None] * col("home_bull_z")
              + b_start[:, None] * col("home_start_z"))
    s_away = (z_team[:, a]
              + b_off[:, None] * col("away_off_z")
              + b_bull[:, None] * col("away_bull_z")
              + b_start[:, None] * col("away_start_z"))
    logit = (s_home - s_away) + hfa_team[:, h] + b_rds[:, None] * col("run_diff_sigma_z")
    p = 1.0 / (1.0 + np.exp(-logit))      # (n_samples, n_games)
    return p.mean(axis=0)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def _brier(p, y):
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def _logloss(p, y):
    p = np.clip(np.asarray(p, float), 1e-12, 1 - 1e-12)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _ece(p, y, n_bins=10):
    p = np.asarray(p, float); y = np.asarray(y, float)
    bins = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(p, bins) - 1, 0, n_bins - 1)
    e = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.any():
            e += (m.mean()) * abs(p[m].mean() - y[m].mean())
    return float(e)


def evaluate(g_oos: pd.DataFrame, p_bt: np.ndarray, env: str) -> dict:
    """Three-layer + Layer-4 eval of the BT model on credible 2026, vs the
    XGBoost champion and the market on the SAME market-covered games."""
    from betting_ml.scripts.load_layer3_features import load_devig_home_prob_bovada
    from betting_ml.scripts.evaluation.bayesian_model_eval import (
        sweep_thresholds, layer4_verdict, evaluate_selective_strategy, MIN_BETS_RELIABLE,
    )

    df = g_oos.copy()
    df["p_bt"] = p_bt
    y = df["home_win"].to_numpy(float)

    # Market (de-vigged Bovada/Parlay P(home win)).
    mkt = load_devig_home_prob_bovada(df["game_pk"].tolist(), env=env)
    mkt_by_pk = {int(pk): float(v) for pk, v in
                 zip(mkt["game_pk"], mkt["bovada_devig_home_prob"]) if pd.notna(v)}

    # Champion OOS preds (2026 rows of the leakage-free H2H surface).
    champ = pd.read_parquet(_CHAMPION_PARQUET)
    champ = champ[champ["season"] == _OOS_SEASON]
    champ_by_pk = {int(pk): float(v) for pk, v in
                   zip(champ["game_pk"], champ["model_p_home_win"]) if pd.notna(v)}

    df["mkt"]   = df["game_pk"].map(mkt_by_pk)
    df["champ"] = df["game_pk"].map(champ_by_pk)

    # Credible head-to-head set: covered by BOTH market and champion (identical games).
    cov = df["mkt"].notna() & df["champ"].notna()
    d = df[cov].reset_index(drop=True)
    n_cov = len(d)
    log.info("[eval] 2026 OOS games: %d total | %d market-covered | %d ∩ champion",
             len(df), int(df["mkt"].notna().sum()), n_cov)

    yc = d["home_win"].to_numpy(float)
    p_bt_c   = d["p_bt"].to_numpy(float)
    p_mkt_c  = d["mkt"].to_numpy(float)
    p_chmp_c = d["champ"].to_numpy(float)

    market_brier = _brier(p_mkt_c, yc)
    market_credible = market_brier <= _SANE_MARKET_BRIER_MAX

    # Optional isotonic recalibration (production H2H calibrator; fit on champion
    # probs, so reported as a reference only).
    iso_brier = float("nan"); iso_ece = float("nan")
    try:
        import joblib
        iso = joblib.load(_ISOTONIC_PATH)
        p_bt_iso = iso.predict(p_bt_c)
        iso_brier = _brier(p_bt_iso, yc); iso_ece = _ece(p_bt_iso, yc)
    except Exception as e:  # noqa: BLE001
        log.warning("[eval] isotonic recal skipped: %s", e)

    base_rate = float(g_oos[g_oos["season"] == _OOS_SEASON]["home_win"].mean())

    rec = {
        "n_covered": n_cov,
        "base_rate_2026": base_rate,
        "market_brier": market_brier,
        "market_credible": bool(market_credible),
        "market_target": _MARKET_TARGET_BRIER,
        # Layer 1
        "bt_nll": _logloss(p_bt_c, yc),
        "champ_nll": _logloss(p_chmp_c, yc),
        "market_nll": _logloss(p_mkt_c, yc),
        "prior_nll": _logloss(np.full(n_cov, base_rate), yc),
        # Layer 2
        "bt_ece": _ece(p_bt_c, yc),
        "champ_ece": _ece(p_chmp_c, yc),
        "bt_calib_in_large": float(p_bt_c.mean() - yc.mean()),
        "champ_calib_in_large": float(p_chmp_c.mean() - yc.mean()),
        "bt_iso_brier": iso_brier,
        "bt_iso_ece": iso_ece,
        # Layer 3
        "bt_brier": _brier(p_bt_c, yc),
        "champ_brier": _brier(p_chmp_c, yc),
        "prior_naive_brier": _brier(np.full(n_cov, base_rate), yc),
    }

    # Layer 4 selective strategy for the BT model.
    games4 = pd.DataFrame({
        "market": "h2h", "model_p_home": p_bt_c,
        "market_p_home": p_mkt_c, "home_win": yc,
    })
    sweep = sweep_thresholds(games4)
    rec["layer4"] = {
        "verdict": layer4_verdict(sweep),
        "default": evaluate_selective_strategy(games4),
        "min_bets_reliable": MIN_BETS_RELIABLE,
    }

    # ── PROMOTION decision ────────────────────────────────────────────────────
    beats_champion = rec["bt_brier"] < rec["champ_brier"]
    closes_to_market = (rec["bt_brier"] < rec["champ_brier"]) and (
        rec["bt_brier"] <= max(rec["champ_brier"], market_brier) and
        (rec["champ_brier"] - rec["bt_brier"]) > 0
    )
    beats_market = rec["bt_brier"] <= market_brier
    rec["beats_champion"] = bool(beats_champion)
    rec["closes_toward_market"] = bool((rec["champ_brier"] - rec["bt_brier"]) > 0)
    rec["beats_market"] = bool(beats_market)
    # Promote ONLY if it beats the champion AND closes toward the market, on a
    # credible 2026 surface.
    rec["promote"] = bool(market_credible and beats_champion and rec["closes_toward_market"])
    return rec


def _write_report(rec: dict, diag: dict, scaler_stats: dict, n_train: int) -> Path:
    _ABLATION_DIR.mkdir(parents=True, exist_ok=True)

    def b(x): return "✅" if x else "❌"

    conv = diag["converged"]
    gap_champ = rec["champ_brier"] - rec["bt_brier"]
    gap_mkt   = rec["bt_brier"] - rec["market_brier"]
    v = rec["layer4"]["verdict"]

    lines = [
        "# Story 28.5 — Hierarchical Bayesian Bradley-Terry H2H Model",
        "",
        "_Reopens the H2H **architecture** after 28.4: a paired-comparison logit "
        "likelihood (no count aggregation → no Jensen floor) with partially-pooled "
        "team strength, team-specific HFA, and sub-model-signal covariates. "
        f"Trained 2022–2025 ({n_train} games), scored leakage-free on 2026 OOS._",
        "",
        "## Acceptance Criterion 1 — Convergence (gate FIRST)",
        "",
        "| diagnostic | value | gate | pass |",
        "|---|---:|---|:---:|",
        f"| max R-hat | {diag['max_rhat']:.4f} | < {_RHAT_MAX} | {b(diag['rhat_ok'])} |",
        f"| min ESS_bulk | {diag['min_ess_bulk']:.0f} | > {_ESS_MIN} | {b(diag['ess_ok'])} |",
        f"| divergences | {diag['divergences']} | ≤ {_DIVERGENCES_MAX} | {b(diag['div_ok'])} |",
        "",
        f"**Converged: {b(conv)}** "
        + ("" if conv else "— convergence gate FAILED; head-to-head metrics below are not trustworthy until this passes."),
        "",
        "Signal coefficients (posterior mean): "
        + ", ".join(f"`{k}`={val:+.3f}" for k, val in diag["betas"].items()) + ".",
        "",
        "## Acceptance Criterion 2 — Head-to-head vs XGBoost champion (credible 2026)",
        "",
        f"- Market quality gate: 2026 Bovada/Parlay Brier = **{rec['market_brier']:.4f}** "
        f"({'credible ✅' if rec['market_credible'] else f'⚠️ DEGRADED (>{_SANE_MARKET_BRIER_MAX}) — verdict INCONCLUSIVE'}); "
        f"sharp-band target ≈ {_MARKET_TARGET_BRIER:.3f}.",
        f"- Identical market-covered ∩ champion games: **n = {rec['n_covered']}**. "
        f"2026 home-win base-rate = {rec['base_rate_2026']:.3f}.",
        "",
        "| layer | metric | Bradley-Terry | XGBoost champion | market |",
        "|---|---|---:|---:|---:|",
        f"| L1 | NLL (log-loss) | {rec['bt_nll']:.4f} | {rec['champ_nll']:.4f} | {rec['market_nll']:.4f} |",
        f"| L2 | ECE | {rec['bt_ece']:.4f} | {rec['champ_ece']:.4f} | — |",
        f"| L2 | calib-in-large | {rec['bt_calib_in_large']:+.4f} | {rec['champ_calib_in_large']:+.4f} | — |",
        f"| L3 | Brier | **{rec['bt_brier']:.4f}** | {rec['champ_brier']:.4f} | {rec['market_brier']:.4f} |",
        "",
        f"- Prior baselines: Bernoulli base-rate NLL {rec['prior_nll']:.4f}, "
        f"prior-naive Brier {rec['prior_naive_brier']:.4f}.",
        f"- Isotonic-recalibrated BT (reference; production calibrator fit on champion probs): "
        f"Brier {rec['bt_iso_brier']:.4f}, ECE {rec['bt_iso_ece']:.4f}.",
        "",
        "### Gates",
        "",
        "| gate | result |",
        "|---|:---:|",
        f"| L1 NLL < Bernoulli prior | {b(rec['bt_nll'] < rec['prior_nll'])} |",
        f"| Beats champion Brier (Δ = {gap_champ:+.4f}) | {b(rec['beats_champion'])} |",
        f"| Closes toward market | {b(rec['closes_toward_market'])} |",
        f"| Beats market Brier (gap to mkt = {gap_mkt:+.4f}) | {b(rec['beats_market'])} |",
        f"| L4 roi_devig>0 & n≥{rec['layer4']['min_bets_reliable']} | {b(v.get('passed', False))} |",
        "",
        f"## Verdict — PROMOTE: {b(rec['promote'])}",
        "",
    ]

    if not diag["converged"]:
        lines += ["**Not promotable — convergence gate failed.** Re-check the "
                  "non-centered reparameterization / priors before reading the head-to-head.", ""]
    elif not rec["market_credible"]:
        lines += ["**Inconclusive** — the 2026 market baseline is degraded (>{:.3f}); "
                  "a 'win' here is an artifact, not skill. Re-gate on a credible Parlay surface."
                  .format(_SANE_MARKET_BRIER_MAX), ""]
    elif rec["promote"]:
        lines += [f"**PROMOTE** — converged, beats the XGBoost champion on Brier "
                  f"({rec['bt_brier']:.4f} < {rec['champ_brier']:.4f}) and closes toward the "
                  f"sharp 2026 market ({rec['market_brier']:.4f}). Verify Layer 4 ROI before wiring "
                  f"into production scoring.", ""]
    else:
        reason = ("does not beat the champion" if not rec["beats_champion"]
                  else "does not close toward the market")
        lines += [f"**DO NOT PROMOTE** — the architecture change converged but {reason} on the "
                  f"credible 2026 surface (BT Brier {rec['bt_brier']:.4f} vs champion "
                  f"{rec['champ_brier']:.4f} vs market {rec['market_brier']:.4f}). Consistent with "
                  f"the standing Epic 11/28 finding: no H2H edge against the sharp Parlay market.", ""]

    _REPORT_PATH.write_text("\n".join(lines) + "\n")
    return _REPORT_PATH


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Story 28.5 — Bradley-Terry H2H NUTS")
    ap.add_argument("--env", default="prod")
    args = ap.parse_args()

    log.info("=" * 64)
    log.info("Story 28.5 — Hierarchical Bayesian Bradley-Terry H2H (NUTS)")
    log.info("=" * 64)

    g, teams, scaler_stats = _prepare_game_frame()
    train_df = g[g["season"].isin(_TRAIN_SEASONS)].reset_index(drop=True)
    oos_df   = g[g["season"] == _OOS_SEASON].reset_index(drop=True)
    if len(oos_df) == 0:
        log.error("No 2026 OOS games — aborting.")
        sys.exit(1)

    log.info("[model] building Bradley-Terry model (%d train games, %d teams)...",
             len(train_df), len(teams))
    model = build_bt_model(train_df, teams)
    trace = run_nuts(model)

    log.info("[save] writing trace → %s", _TRACE_PATH)
    trace.to_netcdf(str(_TRACE_PATH), engine="h5netcdf")

    diag = check_diagnostics(trace)

    log.info("[score] posterior-mean P(home) for %d 2026 OOS games...", len(oos_df))
    p_oos = score_games(trace, oos_df)
    oos_out = oos_df[["game_pk", "season", "game_date", "home_team", "away_team", "home_win"]].copy()
    oos_out["model_p_home_bt"] = p_oos
    _OOS_PRED_PATH.parent.mkdir(parents=True, exist_ok=True)
    oos_out.to_parquet(_OOS_PRED_PATH, index=False)
    log.info("[save] OOS predictions → %s", _OOS_PRED_PATH)

    log.info("[eval] three-layer + Layer-4 vs champion and market...")
    rec = evaluate(oos_df, p_oos, args.env)

    summary = {
        "model": "h2h_hierarchical_bradley_terry",
        "story": "28.5",
        "nuts": {"draws": _N_DRAWS, "tune": _N_TUNE, "chains": _N_CHAINS,
                 "target_accept": _TARGET_ACCEPT},
        "n_train_games": len(train_df), "n_oos_games": len(oos_df), "n_teams": len(teams),
        "scaler_stats": scaler_stats,
        "diagnostics": diag,
        "evaluation": {k: v for k, v in rec.items() if k != "layer4"},
        "layer4_verdict": rec["layer4"]["verdict"],
    }
    with open(_SUMMARY_PATH, "w") as f:
        json.dump(summary, f, indent=2, default=float)
    log.info("[save] summary → %s", _SUMMARY_PATH)

    report = _write_report(rec, diag, scaler_stats, len(train_df))
    log.info("[save] report → %s", report)

    log.info("\n" + "=" * 64)
    log.info("28.5 SUMMARY")
    log.info("  Converged:       %s (R-hat=%.4f ESS=%.0f div=%d)",
             diag["converged"], diag["max_rhat"], diag["min_ess_bulk"], diag["divergences"])
    log.info("  BT Brier:        %.4f", rec["bt_brier"])
    log.info("  Champion Brier:  %.4f", rec["champ_brier"])
    log.info("  Market Brier:    %.4f (%s)", rec["market_brier"],
             "credible" if rec["market_credible"] else "DEGRADED")
    log.info("  Beats champion:  %s | Closes to market: %s",
             rec["beats_champion"], rec["closes_toward_market"])
    log.info("  PROMOTE:         %s", rec["promote"])
    log.info("=" * 64)


if __name__ == "__main__":
    main()
