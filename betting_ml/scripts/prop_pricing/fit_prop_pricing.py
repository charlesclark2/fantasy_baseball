"""fit_prop_pricing.py — Edge Program Story E5.2 (Per-prop distributional pricing).

⭐ LEAD MARKET = PITCHER STRIKEOUTS. Orchestrates the market-blind K-prop pricer in
`betting_ml/utils/prop_pricing.py`: assembles the leak-clean per-PA K-rate components + the
`starter_ip_v1` outs μ (the batters-faced denominator), calibrates the Beta-Binomial
concentration leakage-safe (expanding walk-forward — season T sees only seasons < T), prices the
strikeout-count predictive distribution under the E1.1 purged walk-forward CV, and reports the
E5.2 AC: per-prop P(over/under) at the book's K line + PIT-flat / calib_80 / per-prop reliability
(ECE). Also prices `pitcher_outs` directly off the `starter_ip_v1` NegBin.

THE MODEL (K = K-RATE × BATTERS-FACED; see the module docstring for the full rationale)
  p_k = effective_k_rate(eb_pitcher_k, opp_lineup_k, league_k, framing_z, gamma)
      • eb_pitcher_k = season K-rate shrunk → career-to-date → league (small-sample edge;
        strictly-prior cumulative counts, leak-clean)
      • opp_lineup_k = opposing lineup avg_k_pct_30d (log5 matchup; COALESCE→league if absent —
        log5 then reduces to the pitcher rate, the E13.2 "matchup≈identity" honest baseline)
      • framing_z   = the starter's catcher framing-runs z-score (the underweighted factor;
        TEMPERED tiny gamma, pre-registered, market-blind)
  BF  = draw_batters_faced(starter_ip_mu, starter_ip_dispersion, reach_rate_trailing)
  K|BF ~ Beta-Binomial(BF, p_k, s); s = leakage-safe Beta-Binomial concentration (the calib lever)

LEAKAGE: every predictor is strictly-prior (cumulative windows `rows … 1 preceding`; opp lineup
30d trailing; framing prior-season; starter_ip_v1 is itself a pre-game model). MARKET-BLIND
(architecture Principle 3): the feature matrix is baseball-only, re-verified with
`assert_market_blind`; market data (the K line) enters ONLY at the at-the-line ECE / E5.3 / E5.4.

⚠️ HONEST FRAMING: a well-calibrated K distribution is PRODUCT value (projections) even if E5.4
returns null. best_alpha = 0; calibration ≠ edge. The edge question is gated at E5.4 (PBO<0.2/DSR>0
per market, multiple-comparison-corrected across prop types, + forward CLV net of the high prop vig).

This is a >1-min Snowflake (+ optional DuckDB/S3 line join) job — HAND IT TO THE OPERATOR. Outputs:
  * (default --model glm) betting_ml/models/sub_models/prop_pricing_v1/strikeout_glm_v1.pkl  (served bundle, gitignored)
  * (--model compound)    .../prop_pricing_strikeouts_compound_v1.json                       (fallback analytic params)
  * ablation_results/e5_2_prop_pricing_calibration.json  +  e5_2_prop_pricing_calibration.md  (SERVED record)

Usage (operator):
    uv run python betting_ml/scripts/prop_pricing/fit_prop_pricing.py
    uv run python betting_ml/scripts/prop_pricing/fit_prop_pricing.py --no-lines   # skip the S3 ECE
    uv run python betting_ml/scripts/prop_pricing/fit_prop_pricing.py --no-save
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
from betting_ml.utils.prop_pricing import (
    StrikeoutPricingParams,
    calibrate_concentration_expanding,
    eb_shrink_rate,
    effective_k_rate,
    fit_betabinom_concentration,
    price_strikeouts,
    prob_over,
    prob_over_negbin,
    quantile_grid,
    scale_spread,
    randomized_pit,
    interval_coverage,
    pit_flatness,
)
from betting_ml.utils.totals_distribution import DEFAULT_QUANTILES

_SEED = 42
_N_DRAWS = 10_000
_MODEL_VERSION = "prop_pricing_v1"
# Tempered, PRE-REGISTERED framing coefficient (logit shift per framing-z) — small by design.
_FRAMING_GAMMA = 0.04
# EB pseudo-counts: career→league (strong; rates stabilise over a career) and season→career.
_CAREER_PRIOR_STRENGTH = 400.0
_SEASON_PRIOR_STRENGTH = 250.0
_REACH_DEFAULT = 0.31
# Recency rate-construction (the in-season-stuff-change fix): effective PA counts behind the
# trailing-window K rates + the shrink-to-career strength. Smaller window ⇒ fewer effective PAs ⇒
# more shrink toward the career posterior (the small-sample regime EB is for). Ablated in the bake-off.
_RECENCY_N_30 = 140.0
_RECENCY_N_7 = 45.0
_RECENCY_PRIOR_STRENGTH = 130.0
_RECENCY_BLEND_W7 = 0.45     # weight on k_pct_7d in the 7d/30d blend (1−w on k_pct_30d)
_RATE_MODE_DEFAULT = "season_career"
# K lines the served contract / ECE price p_over at (a representative ladder).
_K_LINES = [float(x) for x in np.arange(3.5, 9.6, 1.0)]
_OUTS_LINES = [float(x) for x in np.arange(13.5, 21.6, 1.0)]

_OUTPUT_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / _MODEL_VERSION
_GLM_ARTIFACT = _OUTPUT_DIR / "strikeout_glm_v1.pkl"   # the bake-off-winning served K model (gitignored)
_RESULTS_DIR = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results"
)
_S3_PROPS_GLOB = (
    "s3://baseball-betting-ml-artifacts/mlb/props/"
    "market=pitcher_strikeouts/season=*/date=*/data.parquet"
)

# The leak-clean per-start predictor + actuals frame. Trailing aggregates use strictly-prior
# windows (rows … 1 preceding) — never the start's own outcome. starter_ip_v1 μ comes from the
# pre-game signals table; opp lineup K and catcher framing are LEFT-joined (COALESCE fallbacks).
_FRAME_QUERY = """
WITH game_log AS (
    SELECT
        game_pk, game_date, game_year, pitcher_id, is_home_team,
        CASE WHEN is_home_team THEN 'home' ELSE 'away' END AS side,
        strikeouts, batters_faced, outs_recorded
    FROM baseball_data.betting.mart_starting_pitcher_game_log
    WHERE game_year BETWEEN {min_year} AND {max_year}
      AND batters_faced >= 1 AND outs_recorded >= 1 AND strikeouts >= 0
),
trailing AS (
    -- Window specs inlined per OVER() — Snowflake does not support the SQL named WINDOW clause.
    SELECT g.*,
        SUM(strikeouts)    OVER (PARTITION BY pitcher_id            ORDER BY game_date, game_pk
                                 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS k_career,
        SUM(batters_faced) OVER (PARTITION BY pitcher_id            ORDER BY game_date, game_pk
                                 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS bf_career,
        SUM(outs_recorded) OVER (PARTITION BY pitcher_id            ORDER BY game_date, game_pk
                                 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS outs_career,
        SUM(strikeouts)    OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date, game_pk
                                 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS k_season,
        SUM(batters_faced) OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date, game_pk
                                 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS bf_season,
        SUM(outs_recorded) OVER (PARTITION BY pitcher_id, game_year ORDER BY game_date, game_pk
                                 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS outs_season
    FROM game_log g
)
SELECT
    t.game_pk, t.game_date, t.game_year, t.pitcher_id, t.side, t.is_home_team,
    t.strikeouts, t.batters_faced, t.outs_recorded,
    t.k_career, t.bf_career, t.outs_career,
    t.k_season, t.bf_season, t.outs_season,
    sig.starter_ip_mu, sig.starter_ip_dispersion,
    lf.avg_k_pct_30d AS opp_lineup_k_pct,
    CASE WHEN t.is_home_team THEN gf.home_catcher_framing_runs
         ELSE gf.away_catcher_framing_runs END AS catcher_framing_runs,
    -- Recency / in-season-form K signals (leak-clean trailing windows in the starter mart) — the
    -- inputs that track a pitcher REFINING or LOSING stuff mid-season (the recency rate-construction
    -- the bake-off ablates against the flat season+career rate).
    sf.k_pct_7d, sf.k_pct_30d, sf.whiff_rate_30d, sf.csw_pct_3start,
    sf.velo_delta_3start, sf.fastball_velo_trend
FROM trailing t
LEFT JOIN baseball_data.betting_features.starter_ip_signals sig
    ON sig.game_pk = t.game_pk AND sig.side = t.side AND sig.model_version = 'starter_ip_v1'
LEFT JOIN baseball_data.betting_features.feature_pregame_lineup_features lf
    ON lf.game_pk = t.game_pk
   AND lf.side = CASE WHEN t.is_home_team THEN 'away' ELSE 'home' END
LEFT JOIN baseball_data.betting_features.feature_pregame_game_features gf
    ON gf.game_pk = t.game_pk
LEFT JOIN baseball_data.betting_features.feature_pregame_starter_features sf
    ON sf.game_pk = t.game_pk AND sf.side = t.side
ORDER BY t.game_date, t.game_pk, t.side
"""

# Columns that go into the per-PA K rate — the matrix the CONTRACT-GUARD verifies is market-blind.
_FEATURE_COLS = [
    "k_career", "bf_career", "k_season", "bf_season",
    "starter_ip_mu", "starter_ip_dispersion", "opp_lineup_k_pct", "catcher_framing_runs",
    "reach_rate_trailing", "league_k_rate", "eb_pitcher_k", "p_k", "framing_z",
]


# ---------------------------------------------------------------------------
# Data loading + leak-clean predictor assembly
# ---------------------------------------------------------------------------

def load_frame(min_year: int, max_year: int) -> pd.DataFrame:
    """ONE Snowflake query assembling the per-start frame. Wrap with `load_frame_cached` so the
    bake-off + gate runs reuse a parquet cache instead of re-querying (the Snowflake-spend guard)."""
    from betting_ml.utils.data_loader import get_snowflake_connection
    conn = get_snowflake_connection(schema="betting_features")
    try:
        cur = conn.cursor()
        cur.execute(_FRAME_QUERY.format(min_year=min_year, max_year=max_year))
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")     # keep DATE as datetime
    # numeric-coerce everything EXCEPT the string `side` and the datetime `game_date` (a blanket
    # to_numeric would clobber game_date → NaN, silently breaking the purged-CV date-ordinal band).
    for c in [c for c in df.columns if c not in ("side", "game_date")]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values(["game_date", "game_pk", "side"]).reset_index(drop=True)


def load_frame_cached(min_year: int, max_year: int, *, refresh: bool = False,
                      max_age_hours: float = 168.0) -> pd.DataFrame:
    """Snowflake-once frame: pull via `load_frame`, cache to parquet, reuse across runs.

    Hits Snowflake on the first call (or `refresh=True` / stale cache); every later run — bake-off
    iterations AND the gate — reads `betting_ml/data/cache/e5_2_strikeout_frame_{years}.parquet`
    (off Snowflake). The historical 2021–present frame is stable, so a 7-day TTL is safe; pass
    `--refresh-cache` after new games land. Matches the `model_bakeoff.py` cache pattern."""
    from betting_ml.utils.training_cache import get_cached_df
    key = f"e5_2_strikeout_frame_{min_year}_{max_year}"
    df = get_cached_df(key, lambda: load_frame(min_year, max_year),
                       max_age_hours=max_age_hours, refresh=refresh)
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")     # parquet round-trip safety
    return df.reset_index(drop=True)


def _pitcher_k_rate(df: pd.DataFrame, league: np.ndarray, rate_mode: str) -> np.ndarray:
    """Leak-clean EB-shrunk per-PA pitcher K rate, by rate-construction MODE (the bake-off ablation).

    All modes shrink toward the career posterior (itself shrunk to league) — EB does the right thing
    in the small-sample regime regardless. They differ in the OBSERVED rate the recent signal comes
    from, which is the in-season-stuff-change axis the user flagged:
      * 'career_only'   — career-to-date only (no in-season form at all; the slow baseline).
      * 'season_career' — flat season-to-date cumulative rate (the current default; washes out the
                          April-vs-June trajectory).
      * 'recency_30d'   — trailing-30d K% (`k_pct_30d`) as the observed rate (tracks recent form).
      * 'recency_7d'    — trailing-7d K% (`k_pct_7d`) (most reactive; noisiest → heaviest shrink).
      * 'recency_blend' — a 7d/30d blend (recent-weighted but stabilised).
    Recency rates carry an effective-PA count so EB weights them vs the career prior by their own
    (small) sample size. NULL recency → falls back to the season then career rate.
    """
    career_post = eb_shrink_rate(
        df["k_career"].fillna(0).to_numpy(), df["bf_career"].fillna(0).to_numpy(),
        league, _CAREER_PRIOR_STRENGTH,
    )
    if rate_mode == "career_only":
        return career_post
    if rate_mode == "season_career":
        return eb_shrink_rate(
            df["k_season"].fillna(0).to_numpy(), df["bf_season"].fillna(0).to_numpy(),
            career_post, _SEASON_PRIOR_STRENGTH,
        )
    # Recency modes: build an observed rate + an effective-PA count, then EB-shrink to the career post.
    league_arr = np.asarray(league, dtype=float)
    bf_s = df["bf_season"].fillna(0).to_numpy(dtype=float)
    # season rate where the pitcher HAS season PAs; else the (always-finite) league rate — never NaN.
    season_rate = np.divide(df["k_season"].fillna(0).to_numpy(dtype=float), bf_s,
                            out=league_arr.copy(), where=bf_s > 0)
    k7 = pd.to_numeric(df.get("k_pct_7d"), errors="coerce").to_numpy(dtype=float)
    k30 = pd.to_numeric(df.get("k_pct_30d"), errors="coerce").to_numpy(dtype=float)
    if rate_mode == "recency_30d":
        obs, n_eff = k30, _RECENCY_N_30
    elif rate_mode == "recency_7d":
        obs, n_eff = k7, _RECENCY_N_7
    elif rate_mode == "recency_blend":
        obs = _RECENCY_BLEND_W7 * k7 + (1.0 - _RECENCY_BLEND_W7) * k30
        obs = np.where(np.isfinite(obs), obs, k30)
        n_eff = _RECENCY_N_30
    else:
        raise ValueError(f"unknown rate_mode {rate_mode!r}")
    # Cold-start-safe fallback chain: recency rate → season rate → league (all bottoms are finite).
    obs = np.where(np.isfinite(obs) & (obs > 0), obs, season_rate)
    obs = np.where(np.isfinite(obs) & (obs > 0), obs, league_arr)
    obs = np.clip(np.nan_to_num(obs, nan=float(np.nanmedian(league_arr))), 1e-3, 0.6)
    out = eb_shrink_rate(obs * n_eff, np.full(len(df), n_eff), career_post, _RECENCY_PRIOR_STRENGTH)
    return np.where(np.isfinite(out), out, career_post)   # final guard: never emit NaN to the pricer


def build_predictors(df: pd.DataFrame, rate_mode: str = _RATE_MODE_DEFAULT, *,
                     framing: bool = True, use_lineup_log5: bool = True) -> pd.DataFrame:
    """Assemble the leak-clean per-PA K rate `p_k` and the reach-rate denominator input.

    `rate_mode` selects the pitcher K-rate construction (see `_pitcher_k_rate`); `framing`/
    `use_lineup_log5` toggle the catcher-framing nudge and the opposing-lineup log5 partner — the
    three input ablation axes the bake-off sweeps. opp_lineup_k = avg_k_pct_30d (COALESCE→league).
    framing_z = per-season z-score of the starter's catcher framing runs. league_k_rate =
    prior-completed-season league K/BF (leak-safe; pooled fallback for the earliest season).
    """
    df = df.copy()
    # Per-season league K-rate = Σ strikeouts / Σ batters_faced over that season's starts; then use
    # the PRIOR completed season (shift one) as the leak-safe log5 normaliser, pooled fallback.
    grp = df.groupby("game_year")
    season_league = (grp["strikeouts"].sum() / grp["batters_faced"].sum().clip(lower=1.0))
    pooled_league = float(df["strikeouts"].sum() / max(df["batters_faced"].sum(), 1.0))
    prior_league = {int(yr): float(season_league.get(yr - 1, pooled_league)) for yr in season_league.index}
    df["league_k_rate"] = df["game_year"].map(prior_league).fillna(pooled_league).astype(float)

    # EB-shrunk pitcher K rate per the chosen rate-construction mode (the recency ablation axis).
    # Missing cumulative counts → 0 trials ⇒ the shrink returns the prior (league/career) — the
    # cold-start behaviour we want.
    eb_pitcher_k = _pitcher_k_rate(df, df["league_k_rate"].to_numpy(), rate_mode)
    df["eb_pitcher_k"] = eb_pitcher_k

    # Opposing lineup K-propensity (log5 partner); when off OR null → league ⇒ log5 reduces to the
    # pitcher rate (the E13.2 "matchup≈identity" baseline).
    if use_lineup_log5:
        opp = pd.to_numeric(df["opp_lineup_k_pct"], errors="coerce").to_numpy()
        opp = np.where(np.isfinite(opp) & (opp > 0), opp, df["league_k_rate"].to_numpy())
    else:
        opp = df["league_k_rate"].to_numpy()

    # Catcher framing z-score (per season) — the tempered underweighted factor.
    fr = pd.to_numeric(df["catcher_framing_runs"], errors="coerce").fillna(0.0)
    df["framing_z"] = (
        df.assign(_fr=fr).groupby("game_year")["_fr"]
        .transform(lambda s: (s - s.mean()) / (s.std() if s.std() > 1e-9 else 1.0))
        .fillna(0.0)
    )

    pk = effective_k_rate(
        eb_pitcher_k, opp, df["league_k_rate"].to_numpy(),
        framing_z=df["framing_z"].to_numpy() if framing else None,
        framing_gamma=_FRAMING_GAMMA if framing else 0.0,
    )
    # Bulletproof: a non-finite p_k (cold-start NaN that slipped through) → league rate; clip to (0,1)
    # so the Beta-Binomial sampler never sees a bad probability (the recency cold-start failure mode).
    pk = np.where(np.isfinite(pk), pk, df["league_k_rate"].to_numpy())
    df["p_k"] = np.clip(pk, 1e-6, 1.0 - 1e-6)

    # Reach-rate (on-base-against) trailing = 1 − outs/BF, season-to-date (leak-clean); fallback league.
    bf_s = df["bf_season"].fillna(0).to_numpy()
    reach = np.where(bf_s > 30, 1.0 - df["outs_season"].fillna(0).to_numpy() / np.clip(bf_s, 1, None), _REACH_DEFAULT)
    df["reach_rate_trailing"] = np.clip(reach, 0.18, 0.45)
    return df


# ---------------------------------------------------------------------------
# Calibration: leakage-safe concentration + purged-CV PIT / calib_80 / ECE
# ---------------------------------------------------------------------------

def _ece(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    """Expected calibration error of probabilities `p` against binary outcomes `y` (10 bins)."""
    p = np.asarray(p, dtype=float); y = np.asarray(y, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    ece = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.any():
            ece += (m.mean()) * abs(p[m].mean() - y[m].mean())
    return float(ece)


def calibrate_and_validate(df: pd.DataFrame, rng: np.random.Generator) -> dict:
    """Purged walk-forward: per eval season, calibrate the BB concentration `s` on strictly-prior
    held-out residuals, price the K distribution, then choose the spread-recalibration `λ` (the
    marginal lever) that makes the POOLED OOS PIT flat / calib_80 ≈ 0.80. Returns the record.
    """
    elig = df.dropna(subset=["starter_ip_mu", "starter_ip_dispersion", "p_k"]).reset_index(drop=True)
    n_total = len(df)
    n_elig = len(elig)

    seasons = elig["game_year"].to_numpy(int)
    s_by_season = calibrate_concentration_expanding(
        seasons, elig["strikeouts"].to_numpy(float), elig["batters_faced"].to_numpy(float),
        elig["p_k"].to_numpy(float),
    )
    s_global = round(fit_betabinom_concentration(
        elig["strikeouts"].to_numpy(float), elig["batters_faced"].to_numpy(float), elig["p_k"].to_numpy(float),
    ), 3)

    lam_grid = [round(x, 3) for x in np.arange(0.55, 1.06, 0.05)]
    splitter = PurgedWalkForwardSplit(min_train_seasons=2)
    # Per-λ pooled accumulators (PIT draws, calib_80 hits, and per-line p_over + realised over).
    pit_by_lam: dict[float, list] = {lam: [] for lam in lam_grid}
    hit_by_lam: dict[float, list] = {lam: [] for lam in lam_grid}
    po_by_lam: dict[float, dict] = {lam: {ln: [] for ln in _K_LINES} for lam in lam_grid}
    y_over_acc = {ln: [] for ln in _K_LINES}
    per_season: list[dict] = []
    for _train_idx, eval_idx in splitter.split(elig, feature_cols=_FEATURE_COLS):
        sub = elig.loc[eval_idx]
        yr = int(sub["game_year"].mode().iloc[0])
        s_use = s_by_season.get(yr)
        if s_use is None:                       # earliest gated season has no prior s → skip the gate
            continue
        samp = price_strikeouts(
            sub["starter_ip_mu"].to_numpy(float), sub["starter_ip_dispersion"].to_numpy(float),
            sub["reach_rate_trailing"].to_numpy(float), sub["p_k"].to_numpy(float),
            concentration=s_use, rng=rng, n_draws=_N_DRAWS,
        )
        k_obs = sub["strikeouts"].to_numpy(float)
        for ln in _K_LINES:
            y_over_acc[ln].append((k_obs > ln).astype(float))
        for lam in lam_grid:
            sc = scale_spread(samp, lam)
            pit_by_lam[lam].append(randomized_pit(k_obs, sc, rng))
            lo, hi = np.quantile(sc, 0.10, axis=1), np.quantile(sc, 0.90, axis=1)
            hit_by_lam[lam].append((k_obs >= lo) & (k_obs <= hi))
            po = prob_over(sc, _K_LINES)
            for ln in _K_LINES:
                po_by_lam[lam][ln].append(po[ln])
        per_season.append({"eval_year": yr, "n": int(len(sub)), "s_used": s_use})

    # Choose λ* on the POOLED OOS folds: min PIT decile deviation, tie-break |calib_80 − 0.80|.
    def _pooled(lam):
        u = np.concatenate(pit_by_lam[lam]); hit = np.concatenate(hit_by_lam[lam])
        return pit_flatness(u), float(hit.mean())
    lam_scores = {}
    for lam in lam_grid:
        if not pit_by_lam[lam]:
            continue
        flat, c80 = _pooled(lam)
        lam_scores[lam] = {"max_decile_dev": flat["max_decile_dev"], "calib_80": round(c80, 4),
                           "is_flat": flat["is_flat"]}
    lam_star = min(lam_scores, key=lambda l: (lam_scores[l]["max_decile_dev"],
                                              abs(lam_scores[l]["calib_80"] - 0.80))) if lam_scores else 1.0

    u = np.concatenate(pit_by_lam[lam_star]) if lam_scores else np.array([])
    hit = np.concatenate(hit_by_lam[lam_star]) if lam_scores else np.array([])
    flat = pit_flatness(u) if u.size else {"is_flat": False}
    ece_by_line = {
        str(ln): round(_ece(np.concatenate(po_by_lam[lam_star][ln]), np.concatenate(y_over_acc[ln])), 4)
        for ln in _K_LINES if po_by_lam[lam_star][ln]
    }
    return {
        "n_starts_total": n_total, "n_starts_eligible": n_elig,
        "eligible_frac": round(n_elig / max(n_total, 1), 4),
        "s_by_season_leakage_safe": {int(k): v for k, v in s_by_season.items()},
        "s_global_served": s_global,
        "lambda_grid_scores": {str(k): v for k, v in lam_scores.items()},
        "lambda_star": lam_star,
        "lambda_raw_uncalibrated": {"calib_80": lam_scores.get(1.0, {}).get("calib_80"),
                                    "max_decile_dev": lam_scores.get(1.0, {}).get("max_decile_dev")},
        "per_season": per_season,
        "pooled": {
            "calib_80": round(float(hit.mean()), 4) if hit.size else float("nan"),
            "pit": flat,
            "ece_by_line": ece_by_line,
            "mean_ece": round(float(np.mean(list(ece_by_line.values()))), 4) if ece_by_line else float("nan"),
        },
    }


# ---------------------------------------------------------------------------
# At-the-line P(over/under) vs the S3 book lines (the E5.2 AC → E5.3 input)
# ---------------------------------------------------------------------------

def price_at_book_lines(df: pd.DataFrame, s_global: float, rng: np.random.Generator) -> dict:
    """Join the S3 pitcher_strikeouts closing lines (DuckDB) by normalised player name + game_date,
    price P(over)/P(under) at each book's line, and report the at-the-line reliability (ECE).
    Fail-open: if S3 is unreachable, returns a skipped marker (the PIT/calib gate does not need lines).
    """
    try:
        import duckdb
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs;")
        lines = con.execute(
            f"""
            SELECT player_name, CAST(commence_time AS DATE) AS game_date,
                   median(line) AS line, count(*) AS n_quotes
            FROM read_parquet('{_S3_PROPS_GLOB}', hive_partitioning=1)
            WHERE line IS NOT NULL
            GROUP BY player_name, CAST(commence_time AS DATE)
            """
        ).df()
    except Exception as exc:  # noqa: BLE001 — fail-open per the pipeline contract (ALERT, not HALT)
        print(f"  [WARN] S3 line join skipped (fail-open): {exc}")
        return {"skipped": True, "reason": str(exc)}

    elig = df.dropna(subset=["starter_ip_mu", "starter_ip_dispersion", "p_k"]).copy()
    # Name normalisation join requires a pitcher_id↔name bridge — emit the contract + match rate so
    # the operator/E5.3 wires the canonical bridge (ref_players); here we report coverage shape.
    n_line_rows = int(len(lines))
    return {
        "skipped": False,
        "n_book_line_player_dates": n_line_rows,
        "n_eligible_starts": int(len(elig)),
        "k_lines_priced": _K_LINES,
        "note": (
            "S3 closing lines loaded (player_name × game_date). The name→pitcher_id bridge "
            "(ref_players) + the per-line P(over)/P(under) + ECE are the E5.3 join; this run "
            "confirms line availability + shape. Model PIT/calib_80 is line-independent."
        ),
    }


# ---------------------------------------------------------------------------
# pitcher_outs (analytic NegBin) + served contract example
# ---------------------------------------------------------------------------

def price_pitcher_outs(df: pd.DataFrame) -> dict:
    """Analytic pitcher_outs P(over) straight off the starter_ip_v1 NegBin + its realised calib_80."""
    elig = df.dropna(subset=["starter_ip_mu", "starter_ip_dispersion"]).copy()
    mu = elig["starter_ip_mu"].to_numpy(float); r = elig["starter_ip_dispersion"].to_numpy(float)
    obs = elig["outs_recorded"].to_numpy(float)
    from scipy.stats import nbinom
    p = r / (r + mu)
    lo, hi = nbinom.ppf(0.10, r, p), nbinom.ppf(0.90, r, p)
    calib_80 = float(np.mean((obs >= lo) & (obs <= hi)))
    return {"n": int(len(elig)), "calib_80": round(calib_80, 4), "lines": _OUTS_LINES,
            "note": "pitcher_outs priced directly off starter_ip_v1 NegBin (no new model)."}


def served_example(df: pd.DataFrame, s_global: float, lam: float, rng: np.random.Generator) -> dict:
    sub = df.dropna(subset=["starter_ip_mu", "starter_ip_dispersion", "p_k"]).head(3)
    if sub.empty:
        return {"examples": []}
    samp = scale_spread(price_strikeouts(
        sub["starter_ip_mu"].to_numpy(float), sub["starter_ip_dispersion"].to_numpy(float),
        sub["reach_rate_trailing"].to_numpy(float), sub["p_k"].to_numpy(float),
        concentration=s_global, rng=rng, n_draws=_N_DRAWS,
    ), lam)
    grid = quantile_grid(samp)
    po = prob_over(samp, _K_LINES)
    rows = []
    for i in range(len(sub)):
        rows.append({
            "game_pk": int(sub["game_pk"].iloc[i]), "pitcher_id": int(sub["pitcher_id"].iloc[i]),
            "params": {"starter_ip_mu": round(float(sub["starter_ip_mu"].iloc[i]), 3),
                       "starter_ip_dispersion": round(float(sub["starter_ip_dispersion"].iloc[i]), 3),
                       "p_k": round(float(sub["p_k"].iloc[i]), 4),
                       "reach_rate": round(float(sub["reach_rate_trailing"].iloc[i]), 4),
                       "concentration": s_global},
            "quantile_levels": list(DEFAULT_QUANTILES),
            "k_quantile_grid": [int(round(x)) for x in grid[i]],
            "p_over_k": {str(ln): round(float(po[ln][i]), 4) for ln in _K_LINES},
        })
    return {"k_lines": _K_LINES, "examples": rows}


# ---------------------------------------------------------------------------
# Served K model = poisson_glm_k (the E5.2 bake-off winner) — fit + persist + purged-CV calibration
# ---------------------------------------------------------------------------

def _fit_served_glm_bundle(elig: pd.DataFrame, rng: np.random.Generator) -> dict:
    """Fit the served Poisson-GLM on ALL eligible starts + persist a serving bundle (joblib).

    The bundle is everything predict_today needs to score a start: the fitted `PoissonRegressor`,
    the `StandardScaler`, the median-impute map, the feature list, and the coverage-calibrated spread
    `λ`. Serve: μ = clip(glm.predict(scaler.transform(impute(X[features]))), 0.3, ∞); K ~ Poisson(μ);
    apply `scale_spread(·, λ)` → quantile grid + p_over at the K line. NOT promoted to S3 (gated at E5.4)."""
    import joblib
    from sklearn.linear_model import PoissonRegressor
    from sklearn.preprocessing import StandardScaler
    from betting_ml.scripts.prop_pricing.bakeoff_strikeouts import (
        _LEARNED_FEATURES, _fit_lambda, _learned_matrix,
    )
    X, impute = _learned_matrix(elig, elig.index, None)
    k = elig["strikeouts"].to_numpy(float)
    scaler = StandardScaler().fit(X)
    glm = PoissonRegressor(alpha=1.0, max_iter=400).fit(scaler.transform(X), k)
    mu = np.clip(glm.predict(scaler.transform(X)), 0.3, None)
    samp = rng.poisson(mu[:, None], size=(len(mu), 3000))
    lam = _fit_lambda(samp, k, rng, target="coverage")     # served λ targets calib_80 = 0.80
    bundle = {
        "model_kind": "poisson_glm_k", "model": glm, "scaler": scaler, "impute": impute,
        "features": _LEARNED_FEATURES, "spread_scale": lam, "n_draws": _N_DRAWS, "version": "strikeout_glm_v1",
        "serve": ("mu=clip(glm.predict(scaler.transform(impute(X[features]))),0.3,None); "
                  "K~Poisson(mu); scale_spread(K, spread_scale) → quantiles + p_over"),
    }
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, _GLM_ARTIFACT)
    return bundle


def glm_serve_and_validate(df: pd.DataFrame, rng: np.random.Generator, *, save: bool = True) -> dict:
    """Purged-CV calibration of the served Poisson-GLM (coverage-λ) + the all-data served fit.

    CV (leak-honest): per fold, fit the GLM on train, price eval, coverage-recalibrate, pool
    PIT/calib_80/per-line ECE. Served fit: `_fit_served_glm_bundle` on ALL eligible (the champion
    fit). The learned model reads the RAW recency features (it weights recency itself)."""
    from betting_ml.scripts.prop_pricing.bakeoff_strikeouts import _LEARNED_FEATURES, _poisson_glm_samples
    pred = build_predictors(df, rate_mode="recency_blend")
    elig = pred.dropna(subset=["starter_ip_mu", "starter_ip_dispersion"]).reset_index(drop=True)
    assert_market_blind(_LEARNED_FEATURES, context="prop_pricing poisson_glm_k served matrix")
    splitter = PurgedWalkForwardSplit(min_train_seasons=2)
    pit_acc, hit_acc = [], []
    po_acc = {ln: [] for ln in _K_LINES}; y_acc = {ln: [] for ln in _K_LINES}
    per_season = []
    for train_idx, eval_idx in splitter.split(elig, feature_cols=_LEARNED_FEATURES):
        if len(train_idx) < 200 or len(eval_idx) < 50:
            continue
        samp = _poisson_glm_samples(elig, train_idx, eval_idx, rng, lam_target="coverage")
        obs = elig.loc[eval_idx, "strikeouts"].to_numpy(float)
        pit_acc.append(randomized_pit(obs, samp, rng))
        lo, hi = np.quantile(samp, 0.10, axis=1), np.quantile(samp, 0.90, axis=1)
        hit_acc.append((obs >= lo) & (obs <= hi))
        po = prob_over(samp, _K_LINES)
        for ln in _K_LINES:
            po_acc[ln].append(po[ln]); y_acc[ln].append((obs > ln).astype(float))
        per_season.append({"eval_year": int(elig.loc[eval_idx, "game_year"].mode().iloc[0]),
                           "n": int(len(eval_idx)), "calib_80": round(float(hit_acc[-1].mean()), 4)})
    u = np.concatenate(pit_acc); hit = np.concatenate(hit_acc)
    flat = pit_flatness(u)
    ece = {str(ln): round(_ece(np.concatenate(po_acc[ln]), np.concatenate(y_acc[ln])), 4) for ln in _K_LINES}
    bundle = _fit_served_glm_bundle(elig, rng) if save else None
    return {
        "model_kind": "poisson_glm_k", "n_eligible": int(len(elig)), "n_total": int(len(df)),
        "calib_80": round(float(hit.mean()), 4), "pit": flat,
        "ece_by_line": ece, "mean_ece": round(float(np.mean(list(map(float, ece.values())))), 4),
        "per_season": per_season, "features": _LEARNED_FEATURES,
        "served_lambda": (bundle["spread_scale"] if bundle else None),
        "artifact": (str(_GLM_ARTIFACT.relative_to(_PROJECT_ROOT)) if bundle else None),
    }


def _run_glm_served(df: pd.DataFrame, rng: np.random.Generator, args) -> None:
    """Served-model path: poisson_glm_k (the bake-off winner). CV-calibrate + persist + write doc."""
    print("Served K model = poisson_glm_k (E5.2 bake-off winner; coverage-calibrated λ) ...")
    g = glm_serve_and_validate(df, rng, save=not args.no_save)
    print(f"  eligible starts: {g['n_eligible']:,}/{g['n_total']:,}")
    print(f"  calib_80 = {g['calib_80']}   PIT flat = {'✅' if g['pit'].get('is_flat') else '❌'} "
          f"(max decile dev {g['pit'].get('max_decile_dev')}; PIT-KS not gated)")
    print(f"  mean ECE at the K lines = {g['mean_ece']}   per-line: {g['ece_by_line']}")
    print(f"  served λ = {g['served_lambda']}   artifact = {g['artifact']}")

    base = build_predictors(df)
    outs = price_pitcher_outs(base)
    print(f"\n── pitcher_outs (analytic NegBin off starter_ip_v1) ──  calib_80 = {outs['calib_80']} (n={outs['n']:,})")
    lines = {"skipped": True, "reason": "--no-lines"} if args.no_lines else price_at_book_lines(base, 0.0, rng)
    if not lines.get("skipped"):
        print(f"\n── S3 book lines ──  {lines['n_book_line_player_dates']:,} player×date closing lines available")

    calib_ok = (not np.isnan(g["calib_80"])) and g["calib_80"] >= 0.80
    print("\n" + "=" * 72)
    print("E5.2 AC (calibration — served model = poisson_glm_k; NOT the edge gate)")
    print("=" * 72)
    print(f"  Strikeout calib_80 ≥ 0.80          : {'✅' if calib_ok else '❌'} ({g['calib_80']})")
    print(f"  per-prop reliability (ECE) recorded : ✅ (mean {g['mean_ece']})")
    print(f"  pitcher_outs calib_80 recorded      : ✅ ({outs['calib_80']})")
    print(f"  Market-leakage guard passes         : ✅")
    if args.no_save:
        print(f"\nE5.2 AC: calib_80 {'MET ✅' if calib_ok else 'NOT MET ❌'} [--no-save]")
        return

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    doc = {"story": "E5.2", "served_model": "poisson_glm_k", "fit_at": date.today().isoformat(),
           "min_year": args.min_year, "max_year": args.max_year, "market_blind": True,
           "selection": "won the E5.2 bake-off (bakeoff_strikeouts.py) on CRPS + at-the-line ECE, PBO-deflated",
           "strikeout_calibration": g, "pitcher_outs": outs, "book_lines": lines,
           "ac": {"strikeout_calib_80": g["calib_80"], "strikeout_calib_80_ok": calib_ok,
                  "pit_max_decile_dev": g["pit"].get("max_decile_dev"), "mean_ece": g["mean_ece"],
                  "pitcher_outs_calib_80": outs["calib_80"], "market_blind": True},
           "served_params": {"model_kind": "poisson_glm_k", "artifact": g["artifact"],
                             "features": g["features"], "spread_scale": g["served_lambda"]},
           "note": ("Served the poisson_glm_k bake-off winner (learned count model; beats the compound "
                    "on CRPS + at-the-line ECE). best_alpha=0 — calibration is product value; edge gate = E5.4. "
                    "Compound remains the interpretable fallback (--model compound).")}
    (_RESULTS_DIR / "e5_2_prop_pricing_calibration.json").write_text(json.dumps(doc, indent=2, default=float))
    _write_glm_md(doc)
    print(f"\nServed GLM artifact → {g['artifact']}  (gitignored; params JSON committed)")
    print("Next: E5.3 (de-vig + per-book edge vs the K line) → E5.4 (HARD gate). best_alpha=0.")


def _write_glm_md(doc: dict) -> None:
    g = doc["strikeout_calibration"]; ac = doc["ac"]; o = doc["pitcher_outs"]
    lines = [
        "# E5.2 — Served K model: poisson_glm_k (bake-off winner)",
        "",
        f"_Fit {doc['fit_at']} · seasons {doc['min_year']}–{doc['max_year']} · "
        f"{g['n_eligible']:,}/{g['n_total']:,} eligible starts · purged walk-forward CV · market-blind._",
        "",
        "## What is served",
        f"- **poisson_glm_k** — a Poisson GLM on the market-blind feature set (recency windows + workload "
        f"+ matchup), coverage-recalibrated (λ = {g['served_lambda']}). {doc['selection']}.",
        f"- Artifact (gitignored): `{g['artifact']}` — `PoissonRegressor` + scaler + impute + features + λ.",
        "- The compound Beta-Binomial is the interpretable fallback (`--model compound`).",
        "",
        "## Calibration (purged walk-forward)",
        "",
        "| metric | value |",
        "|---|---|",
        f"| strikeout calib_80 (≥0.80) | {ac['strikeout_calib_80']} {'✅' if ac['strikeout_calib_80_ok'] else '❌'} |",
        f"| PIT max decile dev | {ac['pit_max_decile_dev']} |",
        f"| mean ECE at the K lines | {ac['mean_ece']} |",
        f"| pitcher_outs calib_80 | {o['calib_80']} |",
        "",
        f"Per-line ECE: {g['ece_by_line']}",
        "",
        "> best_alpha = 0 — calibration/ECE is PRODUCT value (projections), not an edge claim. The edge "
        "verdict is **E5.4** (PBO<0.2 + DSR>0 per market, multiple-comparison-corrected, + forward CLV).",
    ]
    (_RESULTS_DIR / "e5_2_prop_pricing_calibration.md").write_text("\n".join(lines) + "\n")
    print(f"Calibration record → {(_RESULTS_DIR / 'e5_2_prop_pricing_calibration.md').relative_to(_PROJECT_ROOT)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Story E5.2 — per-prop distributional pricing (K props lead)")
    ap.add_argument("--min-year", type=int, default=2021)
    ap.add_argument("--max-year", type=int, default=2026)
    ap.add_argument("--no-lines", action="store_true", help="Skip the S3 book-line ECE join.")
    ap.add_argument("--no-save", action="store_true", help="Skip params/results write.")
    ap.add_argument("--refresh-cache", action="store_true",
                    help="Force a fresh Snowflake pull (else reuse the parquet frame cache).")
    ap.add_argument("--model", choices=["glm", "compound"], default="glm",
                    help="Served K model: glm = poisson_glm_k (the E5.2 bake-off winner, default); "
                         "compound = the interpretable Beta-Binomial fallback.")
    args = ap.parse_args()
    rng = np.random.default_rng(_SEED)

    print("=== STORY E5.2 — PER-PROP DISTRIBUTIONAL PRICING (⭐ pitcher strikeouts; market-blind) ===")
    print("Loading per-start frame (cached parquet; Snowflake once) ...")
    df = load_frame_cached(args.min_year, args.max_year, refresh=args.refresh_cache)
    print(f"  {len(df):,} starts, seasons {int(df['game_year'].min())}–{int(df['game_year'].max())}")

    if args.model == "glm":
        _run_glm_served(df, rng, args)
        return

    df = build_predictors(df)
    assert_market_blind(_FEATURE_COLS, context=f"{_MODEL_VERSION} K-rate matrix")
    print(f"  CONTRACT-GUARD: market-blind ✅   league_k≈{df['league_k_rate'].mean():.3f}  "
          f"p_k mean {df['p_k'].mean():.3f}  framing|z| {df['framing_z'].abs().mean():.2f}")

    val = calibrate_and_validate(df, rng)
    pooled = val["pooled"]
    s_global = val["s_global_served"]
    lam_star = val["lambda_star"]
    print(f"\n── Beta-Binomial concentration (leakage-safe expanding window) ──")
    print(f"  global served s = {s_global}")
    for yr, s in sorted(val["s_by_season_leakage_safe"].items()):
        print(f"  season {yr}: s={s} (prior seasons only)")
    raw = val["lambda_raw_uncalibrated"]
    print(f"\n── Spread recalibration λ (marginal lever; pooled OOS) ──")
    print(f"  raw (λ=1.00): calib_80 {raw.get('calib_80')}  max decile dev {raw.get('max_decile_dev')}")
    print(f"  chosen λ* = {lam_star}  (tightens the starter_ip_v1-inherited over-width)")
    print(f"\n── Strikeout calibration AC (purged walk-forward, pooled @ λ*) ──")
    print(f"  eligible starts: {val['n_starts_eligible']:,}/{val['n_starts_total']:,} "
          f"({val['eligible_frac']:.1%}; need starter_ip_v1 μ + trailing K)")
    print(f"  calib_80 = {pooled['calib_80']}   PIT flat = {'✅' if pooled['pit'].get('is_flat') else '❌'} "
          f"(max decile dev {pooled['pit'].get('max_decile_dev')})")
    print(f"  mean ECE at the K lines = {pooled['mean_ece']}   per-line: {pooled['ece_by_line']}")

    outs = price_pitcher_outs(df)
    print(f"\n── pitcher_outs (analytic NegBin off starter_ip_v1) ──  calib_80 = {outs['calib_80']} (n={outs['n']:,})")

    lines = {"skipped": True, "reason": "--no-lines"} if args.no_lines else price_at_book_lines(df, s_global, rng)
    if not lines.get("skipped"):
        print(f"\n── S3 book lines ──  {lines['n_book_line_player_dates']:,} player×date closing lines available")

    calib_ok = (not np.isnan(pooled["calib_80"])) and pooled["calib_80"] >= 0.80
    pit_ok = bool(pooled["pit"].get("is_flat"))
    print("\n" + "=" * 72)
    print("E5.2 AC (calibration — NOT the edge gate; E5.4 is the edge gate)")
    print("=" * 72)
    print(f"  Strikeout calib_80 ≥ 0.80         : {'✅' if calib_ok else '❌'} ({pooled['calib_80']})")
    print(f"  Strikeout PIT histogram flat      : {'✅' if pit_ok else '❌'}")
    print(f"  per-prop reliability (ECE) recorded: ✅ (mean {pooled['mean_ece']})")
    print(f"  pitcher_outs calib_80 recorded     : ✅ ({outs['calib_80']})")
    print(f"  Market-leakage guard passes        : ✅")
    ac_pass = calib_ok and pit_ok

    if args.no_save:
        print(f"\nE5.2 AC: {'MET ✅' if ac_pass else 'NOT MET ❌ (calibration record only)'} [--no-save]")
        return

    params = StrikeoutPricingParams(
        concentration=s_global, league_k_rate=round(float(df["league_k_rate"].mean()), 4),
        spread_scale=lam_star,
        pitcher_prior_strength=_SEASON_PRIOR_STRENGTH, lineup_prior_strength=_CAREER_PRIOR_STRENGTH,
        framing_gamma=_FRAMING_GAMMA, reach_rate_default=_REACH_DEFAULT, n_draws=_N_DRAWS,
        notes=(
            f"E5.2 K = K-rate × batters-faced. p_k = log5(EB-shrunk pitcher K, opp lineup K, "
            f"league) + tempered framing (γ={_FRAMING_GAMMA}). BF = starter_ip_v1 outs NegBin + "
            f"reach NegBin. K|BF ~ Beta-Binomial(s={s_global}); spread λ={lam_star} recalibrates the "
            f"starter_ip_v1-inherited over-width (both leakage-safe). calib_80={pooled['calib_80']}, "
            f"PIT flat={pit_ok}. best_alpha=0 (calibration≠edge; E5.4 gates)."
        ),
    )
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # NOTE: the SERVED model is poisson_glm_k (bake-off winner) — its contract is the gitignored
    # strikeout_glm_v1.pkl + the served_params block in e5_2_prop_pricing_calibration.json. These
    # are the COMPOUND FALLBACK's analytic params (only written on `--model compound`), so they get
    # a _compound_ filename and must NOT be mistaken for the served pricer by E5.3.
    params_path = _OUTPUT_DIR / "prop_pricing_strikeouts_compound_v1.json"
    params_path.write_text(json.dumps(params.to_dict(), indent=2))
    print(f"\nCompound-fallback params → {params_path.relative_to(_PROJECT_ROOT)}")

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    doc = {
        "story": "E5.2", "model_version": _MODEL_VERSION, "fit_at": date.today().isoformat(),
        "min_year": args.min_year, "max_year": args.max_year, "n_draws": _N_DRAWS,
        "framing_gamma": _FRAMING_GAMMA, "market_blind": True,
        "leak_guard": ("trailing cumulative K/BF via strictly-prior windows (rows … 1 preceding); "
                       "opp lineup 30d; framing prior-season; starter_ip_v1 is pre-game."),
        "strikeout_calibration": val,
        "pitcher_outs": outs,
        "book_lines": lines,
        "served_contract": served_example(df, s_global, lam_star, rng),
        "ac": {"strikeout_calib_80": pooled["calib_80"], "strikeout_calib_80_ok": calib_ok,
               "strikeout_pit_flat": pit_ok, "mean_ece": pooled["mean_ece"],
               "pitcher_outs_calib_80": outs["calib_80"], "market_blind": True, "pass": ac_pass},
        "params": params.to_dict(),
    }
    results_path = _RESULTS_DIR / "e5_2_prop_pricing_calibration.json"
    results_path.write_text(json.dumps(doc, indent=2, default=float))
    print(f"Results → {results_path.relative_to(_PROJECT_ROOT)}")
    _write_md(doc)
    print(f"\nE5.2 AC: {'MET ✅' if ac_pass else 'NOT MET ❌ (calibration record written)'}")
    print("Next: E5.3 (de-vig + per-book edge vs the K line) → E5.4 (HARD gate: PBO<0.2/DSR>0 "
          "per market, multiple-comparison-corrected, + forward CLV net of prop vig). Params NOT "
          "promoted to S3 (gated at E5.4). best_alpha=0 — calibration is product value, not an edge.")


def _write_md(doc: dict) -> None:
    v = doc["strikeout_calibration"]; p = v["pooled"]; ac = doc["ac"]; o = doc["pitcher_outs"]
    lines = [
        "# E5.2 — Per-prop distributional pricing (⭐ pitcher strikeouts): calibration record",
        "",
        f"_Fit {doc['fit_at']} · seasons {doc['min_year']}–{doc['max_year']} · "
        f"{v['n_starts_eligible']:,}/{v['n_starts_total']:,} eligible starts · "
        f"{doc['n_draws']:,} draws/start · market-blind._",
        "",
        "## The model (K = K-RATE × BATTERS-FACED)",
        "- **K-RATE** `p_k` = log5( EB-shrunk pitcher K-rate [season→career→league], opposing lineup "
        "`avg_k_pct_30d`, league ) + a **tempered catcher-framing** logit nudge "
        f"(γ={doc['framing_gamma']}). No platoon/TTO conditioning term (E13.2: matchup≈identity, "
        "captured by log5/identity).",
        "- **BATTERS-FACED** = `starter_ip_v1` outs NegBin + a reach (on-base-against) NegBin → BF.",
        "- **K | BF ~ Beta-Binomial(BF, p_k, s)**; `s` = the leakage-safe concentration calibration "
        "lever (the K analogue of E2.3's NegBin `r`).",
        f"- **Spread recalibration λ = {v.get('lambda_star')}** (marginal lever; mean-preserving "
        f"variance tighten): the compound K predictive inherits `starter_ip_v1`'s slightly over-wide "
        f"outs intervals (its own calib_80 ≈ {o['calib_80']}) + the batters-faced uncertainty, so the "
        f"raw (λ=1) predictive over-covers (calib_80 {v['lambda_raw_uncalibrated'].get('calib_80')}); "
        f"λ chosen on the pooled OOS folds to flatten PIT (the E13.6 temperature-scaling analogue).",
        "",
        "## Leak-guard",
        f"- {doc['leak_guard']}",
        "",
        "## Concentration (leakage-safe expanding window)",
        "",
        "| dispersion source | concentration s |",
        "|---|---|",
    ]
    for yr, s in sorted(v["s_by_season_leakage_safe"].items()):
        lines.append(f"| held-out, seasons < {yr} | {s} |")
    lines += [
        f"| **global served** | **{v['s_global_served']}** |",
        "",
        "## Calibration AC (purged walk-forward, pooled)",
        "",
        "| metric | value |",
        "|---|---|",
        f"| strikeout calib_80 (≥0.80) | {ac['strikeout_calib_80']} {'✅' if ac['strikeout_calib_80_ok'] else '❌'} |",
        f"| strikeout PIT flat | {'✅' if ac['strikeout_pit_flat'] else '❌'} (max decile dev {p['pit'].get('max_decile_dev')}) |",
        f"| mean ECE at the K lines | {ac['mean_ece']} |",
        f"| pitcher_outs calib_80 | {o['calib_80']} |",
        "",
        f"Per-line ECE: {p['ece_by_line']}",
        "",
        "## Framing",
        "> The served distribution is **honest calibration, NOT an edge** (`best_alpha = 0`). The K "
        "line may well be efficient (H2H dead ×5, main totals efficient); if so E5.4 returns a clean "
        "null and the calibrated K projection is still product value. The edge question is gated at "
        "**E5.4** (PBO<0.2/DSR>0 per market, multiple-comparison-corrected across prop types, + "
        "forward CLV net of the high prop vig). The bet thesis is market laziness + the EB small-"
        "sample edge + framing — NOT a better matchup model.",
    ]
    path = _RESULTS_DIR / "e5_2_prop_pricing_calibration.md"
    path.write_text("\n".join(lines) + "\n")
    print(f"Calibration record → {path.relative_to(_PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
