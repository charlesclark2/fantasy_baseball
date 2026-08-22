"""nf_inj3_injury_games.py — NF-INJ3: a fitted, designation-onset-aware injury-games model.

⭐ READ `ablation_results/nf_inj3_preregistration.md` FIRST. It is this story's pre-registration,
committed before any arm was scored. ⛔ Editing it after a result is not a pre-registration
(E2.1-r).

────────────────────────────────────────────────────────────────────────────────────────────────
THE DEFECT
────────────────────────────────────────────────────────────────────────────────────────────────
`season_projection._INJURY_STATUS_GAMES_CAP = {"RES": 4.0, "PUP": 4.0, "NFI": 4.0, "SUS": 7.0}` at
`_INJURY_OVERRIDE_BLEND = 0.7`. Four hardcoded constants that set the expected games of every
flagged player on the board — and `proj_games` is both the quantity that makes an injured player
project down (MVP-1's point is `rate × games`) and a directly served field. They are unfitted, they
do not match their own docstring's stated empirics (RES → 3.7, PUP → 2.4, SUS → 6.9), and they are
timing-blind: a March PUP and a late-August PUP both collapse to 4.0.

────────────────────────────────────────────────────────────────────────────────────────────────
⚠️ WHAT "TIMING" CAN AND CANNOT MEAN HERE — MEASURED BEFORE THE FIELD WAS DECLARED
────────────────────────────────────────────────────────────────────────────────────────────────
There is **no designation DATE in this stack**, forward or historical: the weekly roster feed has
no preseason weeks (a week-1 `RES` row is a STATE, not an EVENT), the Sleeper ingest OVERWRITES its
Delta partition on every capture so exactly ONE snapshot exists, the nflverse injury report has no
`PRE` rows and no 2026 rows, and there is no transactions feed. So the hypothesis is tested through
a declared proxy for designation ONSET (`TIMING_FEATURES` below) and the result is scoped to that
proxy — it is NOT evidence about a designation date and must never be reported as such.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT THIS MODULE IS
────────────────────────────────────────────────────────────────────────────────────────────────
The pure kernel: the pre-registered field, the incumbent's own map (imported from
`season_projection`, never restated — a study that re-derives the shipped logic measures something
else, NF-C0e), the in-fold arm fits, the shared Beta-Binomial predictive, and the exact discrete
CRPS reducer. No lake IO, so it unit-tests without a DuckDB. The runner is
`run_nf_inj3_injury_games.py`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, gammaln, logit

from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered field (nf_inj3_preregistration.md §4) — DECLARED FORWARD
# ══════════════════════════════════════════════════════════════════════════════════════════════
PRIMARY_ARM = "timing_aware"
INCUMBENT_ARM = "incumbent"

#: the matched foil (NF-D10 / NF-D15): `timing_aware` with the timing covariates stripped and
#: NOTHING else changed. Non-shippable; the paired delta IS the timing attribution.
MATCHED_FOIL = "timing_aware_minus_timing"

#: pre-registered DEGENERATES — they MUST lose. Named here, before any score, so the DSR-CONV
#: convention (degenerate ∈ n_trials, ∉ V) is a property of the registration and not of the result.
DEGENERATE_ARMS: tuple[str, ...] = ("all_zero", "no_cap")

ARMS: tuple[str, ...] = (
    "incumbent",        # the shipped hardcoded caps at blend 0.7
    "fitted_status",    # the SAME form, per-status level + blend fitted in-fold
    "timing_aware",     # PRIMARY — + the declared onset covariates
    "hurdle_transfer",  # the certified W2/W2b/W2d form: P(plays) × E[games | plays]
    "sus_regime",       # SUS as its own regime; injuries on the fitted_status form
    "all_zero",         # DEGENERATE
    "no_cap",           # DEGENERATE
)
DECLARED_FIELD_SIZE = len(ARMS)

#: anchors — scored, never shippable. A missing anchor RAISES (NF1.7 (a)).
ANCHORS: tuple[str, ...] = ("permuted_timing", "pooled_mean")

#: ⭐ the ONLY two columns the matched foil strips. Declared here so the foil cannot silently
#: become "the primary minus whatever happened to help".
TIMING_FEATURES: tuple[str, ...] = ("onset_carryover", "weeks_since_last_game")
#: the non-timing covariates BOTH the primary and its matched foil carry.
BASE_FEATURES: tuple[str, ...] = ("prior_games", "log1p_prior_fp", "is_qb")

#: eval folds — expanding window, fit on 2016…Y−1. Burn-in 2016–2018.
FOLDS: tuple[int, ...] = (2019, 2020, 2021, 2022, 2023, 2024, 2025)
#: the era restriction, derived from a snapshot-FIDELITY design quantity (preregistration §3).
ERA_MIN_SEASON = 2016

#: a fit cell thinner than this falls back to the pooled level rather than fitting noise — and the
#: fallback is RECORDED, never silent (NF1.7 (a)).
MIN_CELL_N = 20
#: a whole in-fold history thinner than this RAISES: a device that cannot fit must fail loudly.
MIN_FIT_N = 60

_RIDGE = 1.0          # L2 on the GLM slopes (not the intercept) — fixed a-priori, never tuned
_PHI_BOUNDS = (0.05, 200.0)


def season_game_count(season: int) -> int:
    """Regular-season games available to a player in `season` (17 from 2021)."""
    return 17 if int(season) >= 2021 else 16


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The incumbent — the SHIPPED map, imported not restated
# ══════════════════════════════════════════════════════════════════════════════════════════════
def incumbent_games(status: pd.Series, eg: np.ndarray,
                    blend: float = SP._INJURY_OVERRIDE_BLEND) -> np.ndarray:
    """The shipped `injury_availability_games` map, evaluated through `season_projection` itself.

    ⭐ It delegates to the production function rather than re-implementing `(1-b)·eg + b·min(eg,cap)`
    so the arm the bake-off scores and the arm the board serves cannot drift (NF-C0e)."""
    df = pd.DataFrame({"proj_games": np.asarray(eg, dtype=float),
                       "proj_status": pd.Series(status).astype("string").to_numpy()})
    return SP.injury_availability_games(df, blend=blend)


def recover_pre_cap_games(served_games: np.ndarray, status: pd.Series,
                          blend: float = SP._INJURY_OVERRIDE_BLEND) -> np.ndarray:
    """Invert the incumbent map to recover the model's PRE-cap expected games `eg`.

    The map is a bijection: `g = (1-b)·eg + b·min(eg, cap)` gives `g = eg` when `eg ≤ cap` and
    `g = (1-b)·eg + b·cap > cap` when `eg > cap`, so `g > cap ⟺ eg > cap` and the branch is
    recoverable from `g` alone. ⚠️ Valid ONLY on rows where no LATER cap ran — the preregistration
    excludes returners (`seasons_missed ≥ 1`) for exactly this reason."""
    g = np.asarray(served_games, dtype=float)
    cap = pd.Series(status).map(SP._INJURY_STATUS_GAMES_CAP).to_numpy(dtype=float)
    flagged = np.isfinite(cap)
    eg = g.copy()
    hi = flagged & (g > cap + 1e-12)
    eg[hi] = (g[hi] - blend * cap[hi]) / (1.0 - blend)
    return eg


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The shared predictive family — a MATCHED nuisance (preregistration §4)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _betabinom_logpmf(k: np.ndarray, n: int, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (gammaln(n + 1) - gammaln(k + 1) - gammaln(n - k + 1)
            + gammaln(k + a) + gammaln(n - k + b) - gammaln(n + a + b)
            + gammaln(a + b) - gammaln(a) - gammaln(b))


def betabinom_pmf(mu: np.ndarray, n: int, phi: float) -> np.ndarray:
    """`Beta-Binomial(n, mu/n, phi)` pmf over {0..n}, one row per element of `mu`."""
    p = np.clip(np.asarray(mu, dtype=float) / n, 1e-4, 1 - 1e-4)
    a, b = (p * phi)[:, None], ((1 - p) * phi)[:, None]
    k = np.arange(n + 1)[None, :]
    return np.exp(_betabinom_logpmf(k, n, a, b))


def fit_shared_phi(y: np.ndarray, mu: np.ndarray, n: int) -> float:
    """The ONE dispersion parameter, fitted in-fold **under the INCUMBENT's mean** and then held
    byte-identical for every arm.

    ⭐ Deliberately calibrated to the arm being CHALLENGED: a φ tuned to the incumbent's (worse)
    mean is inflated to cover that misfit, which under CRPS helps the incumbent. So the nuisance is
    generous to the thing to beat, and a null therefore means something."""
    y = np.asarray(y, dtype=float)
    mu = np.clip(np.asarray(mu, dtype=float), 1e-3, n - 1e-3)

    def nll(t):
        phi = float(np.exp(t[0]))
        p = np.clip(mu / n, 1e-4, 1 - 1e-4)
        return -float(_betabinom_logpmf(y, n, p * phi, (1 - p) * phi).sum())

    r = minimize(nll, x0=np.array([0.0]), method="L-BFGS-B",
                 bounds=[(np.log(_PHI_BOUNDS[0]), np.log(_PHI_BOUNDS[1]))])
    return float(np.clip(np.exp(r.x[0]), *_PHI_BOUNDS))


def crps_discrete(pmf: np.ndarray, y: np.ndarray) -> np.ndarray:
    """EXACT discrete CRPS `Σ_k (F(k) − 1{y ≤ k})²` on the integer support {0..n}.

    ⛔ Not a quantile grid: a coarse grid silently TIES arms whose means differ by less than its
    step, on exactly the zero-heavy discrete target this study has (NF-W4)."""
    f = np.cumsum(np.asarray(pmf, dtype=float), axis=1)
    k = np.arange(pmf.shape[1])[None, :]
    return ((f - (np.asarray(y, dtype=float)[:, None] <= k).astype(float)) ** 2).sum(axis=1)


def score_arm(mu: np.ndarray, y: np.ndarray, n: int, phi: float) -> dict:
    """One arm's fold score. CRPS selects; MAE is disclosed and NEVER used (it is *measurably*
    inverted on this cohort — the all-zero nihilist wins it)."""
    mu = np.clip(np.asarray(mu, dtype=float), 0.0, float(n))
    c = crps_discrete(betabinom_pmf(mu, n, phi), y)
    return {"crps": float(np.mean(c)), "mae": float(np.mean(np.abs(y - mu))),
            "mean_mu": float(np.mean(mu)), "n": int(len(y))}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The arms
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _design(df: pd.DataFrame, features: tuple[str, ...]) -> np.ndarray:
    """Status dummies + the requested covariates + an intercept. Status is ALWAYS carried."""
    cols = [np.ones(len(df))]
    for s in ("PUP", "NFI", "SUS"):          # RES is the reference level
        cols.append((df["proj_status"].astype(str) == s).to_numpy(dtype=float))
    for f in features:
        cols.append(pd.to_numeric(df[f], errors="coerce").fillna(0.0).to_numpy(dtype=float))
    return np.column_stack(cols)


def fit_glm_mean(train: pd.DataFrame, features: tuple[str, ...], n: int) -> np.ndarray:
    """A logit-link Beta-Binomial GLM for the MEAN games, ridge-penalised on the slopes only.

    Few parameters and an L2 fixed a-priori (never tuned) — the fit has to be stable at ~150–380
    in-fold rows, and an open hyper-parameter search here would be exactly the subset search §0.5
    forbids."""
    x = _design(train, features)
    y = pd.to_numeric(train["realized_games"], errors="coerce").to_numpy(dtype=float)
    phi0 = 1.0

    def nll(beta):
        p = np.clip(expit(x @ beta), 1e-4, 1 - 1e-4)
        ll = _betabinom_logpmf(y, n, p * phi0, (1 - p) * phi0).sum()
        return -float(ll) + _RIDGE * float(np.dot(beta[1:], beta[1:]))

    b0 = np.zeros(x.shape[1])
    b0[0] = logit(np.clip(y.mean() / n, 1e-3, 1 - 1e-3))
    return minimize(nll, x0=b0, method="L-BFGS-B").x


def predict_glm_mean(beta: np.ndarray, eval_df: pd.DataFrame,
                     features: tuple[str, ...], n: int) -> np.ndarray:
    return float(n) * expit(_design(eval_df, features) @ beta)


def fit_status_levels(train: pd.DataFrame) -> tuple[dict, dict]:
    """Per-status mean realized games, fitted in-fold. A cell thinner than `MIN_CELL_N` falls back
    to the pooled level and the fallback is RECORDED (`used_fallback`), never silent."""
    pooled = float(pd.to_numeric(train["realized_games"], errors="coerce").mean())
    levels, prov = {}, {}
    for s in ("RES", "PUP", "NFI", "SUS"):
        cell = train[train["proj_status"].astype(str) == s]
        if len(cell) >= MIN_CELL_N:
            levels[s] = float(pd.to_numeric(cell["realized_games"], errors="coerce").mean())
            prov[s] = {"n": int(len(cell)), "used_fallback": False}
        else:
            levels[s] = pooled
            prov[s] = {"n": int(len(cell)), "used_fallback": True,
                       "why": f"cell n < MIN_CELL_N={MIN_CELL_N}; pooled level used"}
    return levels, prov


def fit_blend(train: pd.DataFrame, levels: dict, n: int) -> float:
    """The blend weight fitted in-fold on a fixed 0..1 grid (11 points, declared, not searched)."""
    eg = pd.to_numeric(train["eg"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(train["realized_games"], errors="coerce").to_numpy(dtype=float)
    cap = train["proj_status"].astype(str).map(levels).to_numpy(dtype=float)
    grid = np.linspace(0.0, 1.0, 11)
    phi = 1.0
    best, best_b = np.inf, SP._INJURY_OVERRIDE_BLEND
    for b in grid:
        mu = np.clip((1 - b) * eg + b * np.minimum(eg, cap), 0.0, float(n))
        s = float(np.mean(crps_discrete(betabinom_pmf(mu, n, phi), y)))
        if s < best:
            best, best_b = s, float(b)
    return best_b


def fit_hurdle(train: pd.DataFrame, n: int) -> dict:
    """The NF-W2/W2b/W2d transfer: an explicit availability HURDLE.

    ⭐ WHAT ACTUALLY TRANSFERS. The certified weekly family cannot transfer its FEATURES — its
    source (`stg_nfl_injuries`) has no preseason rows and no 2026 rows, so it can never feed a
    preseason board. What transfers is its measured FINDING: the lift lives in the zero /
    availability leg (`inj_zero_leg` sat within 0.0004–0.0043 CRPS of the both-legs arm at every
    position and won outright at TE). So this arm splits the mechanism the same way —
    `P(plays ≥ 1 game)` fitted separately from `E[games | plays ≥ 1]` — instead of one conditional
    mean, and lets the data say whether the split pays on a SEASON target."""
    y = pd.to_numeric(train["realized_games"], errors="coerce").to_numpy(dtype=float)
    feats = TIMING_FEATURES + BASE_FEATURES
    x = _design(train, feats)
    plays = (y > 0).astype(float)

    def nll_p(beta):
        p = np.clip(expit(x @ beta), 1e-6, 1 - 1e-6)
        return -float((plays * np.log(p) + (1 - plays) * np.log(1 - p)).sum()) \
            + _RIDGE * float(np.dot(beta[1:], beta[1:]))

    b_play = minimize(nll_p, x0=np.zeros(x.shape[1]), method="L-BFGS-B").x
    pos = train[y > 0]
    if len(pos) >= MIN_CELL_N:
        b_cond = fit_glm_mean(pos, feats, n)
    else:
        b_cond = None
    cond_pooled = float(y[y > 0].mean()) if (y > 0).any() else 0.0
    return {"b_play": b_play, "b_cond": b_cond, "cond_pooled": cond_pooled, "features": feats}


def predict_hurdle(fit: dict, eval_df: pd.DataFrame, n: int) -> np.ndarray:
    x = _design(eval_df, fit["features"])
    p = expit(x @ fit["b_play"])
    cond = (predict_glm_mean(fit["b_cond"], eval_df, fit["features"], n)
            if fit["b_cond"] is not None else np.full(len(eval_df), fit["cond_pooled"]))
    return p * np.clip(cond, 1e-6, float(n))


def arm_mu(arm: str, train: pd.DataFrame, ev: pd.DataFrame, n: int) -> tuple[np.ndarray, dict]:
    """The mean expected games each declared arm emits on the eval fold, fitted IN-FOLD on `train`.

    Returns `(mu, provenance)`. Every fit that fell back is recorded in the provenance."""
    if len(train) < MIN_FIT_N:
        raise ValueError(
            f"NF-INJ3: in-fold history is {len(train)} rows (< MIN_FIT_N={MIN_FIT_N}) — a device "
            f"that cannot fit must fail LOUDLY, never silently no-op (NF1.7 (a))")
    eg = pd.to_numeric(ev["eg"], errors="coerce").to_numpy(dtype=float)

    if arm == "incumbent":
        return incumbent_games(ev["proj_status"], eg), {"blend": SP._INJURY_OVERRIDE_BLEND,
                                                        "levels": dict(SP._INJURY_STATUS_GAMES_CAP)}
    if arm == "all_zero":
        return np.zeros(len(ev)), {"degenerate": True}
    if arm == "no_cap":
        return np.clip(eg, 0.0, float(n)), {"degenerate": True,
                                            "what": "the uncapped stale durability estimate"}
    if arm == "fitted_status":
        levels, prov = fit_status_levels(train)
        b = fit_blend(train, levels, n)
        cap = ev["proj_status"].astype(str).map(levels).to_numpy(dtype=float)
        return np.clip((1 - b) * eg + b * np.minimum(eg, cap), 0.0, float(n)), \
            {"levels": levels, "blend": b, "cells": prov}
    if arm == "timing_aware":
        f = TIMING_FEATURES + BASE_FEATURES
        return predict_glm_mean(fit_glm_mean(train, f, n), ev, f, n), {"features": list(f)}
    if arm == MATCHED_FOIL:
        f = BASE_FEATURES
        return predict_glm_mean(fit_glm_mean(train, f, n), ev, f, n), \
            {"features": list(f), "stripped": list(TIMING_FEATURES), "matched_foil": True}
    if arm == "hurdle_transfer":
        fit = fit_hurdle(train, n)
        return predict_hurdle(fit, ev, n), {"cond_leg_fitted": fit["b_cond"] is not None}
    if arm == "sus_regime":
        levels, prov = fit_status_levels(train)
        b = fit_blend(train, levels, n)
        cap = ev["proj_status"].astype(str).map(levels).to_numpy(dtype=float)
        mu = np.clip((1 - b) * eg + b * np.minimum(eg, cap), 0.0, float(n))
        sus_tr = train[train["proj_status"].astype(str) == "SUS"]
        used_fallback = len(sus_tr) < MIN_CELL_N
        sus_level = (float(pd.to_numeric(sus_tr["realized_games"], errors="coerce").mean())
                     if not used_fallback else levels["SUS"])
        is_sus = (ev["proj_status"].astype(str) == "SUS").to_numpy()
        mu = np.where(is_sus, sus_level, mu)               # a known-length administrative absence
        return np.clip(mu, 0.0, float(n)), {"sus_level": sus_level, "sus_n": int(len(sus_tr)),
                                            "used_fallback": bool(used_fallback)}
    raise ValueError(f"NF-INJ3: unknown arm {arm!r}")


def permute_timing(ev: pd.DataFrame, seed: int) -> pd.DataFrame:
    """The `permuted_timing` anchor — shuffle the TIMING columns within (status × season), which
    destroys player linkage while preserving each cell's marginal distribution exactly."""
    out = ev.copy()
    rng = np.random.default_rng(seed)
    for _, idx in out.groupby([out["proj_status"].astype(str), out["target_season"]]).groups.items():
        ix = np.asarray(list(idx))
        if len(ix) < 2:
            continue
        perm = rng.permutation(len(ix))
        for c in TIMING_FEATURES:
            out.loc[ix, c] = out.loc[ix[perm], c].to_numpy()
    return out
