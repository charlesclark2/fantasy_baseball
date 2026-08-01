"""survivorship.py — MLB Edge-E7.12 SLICE 2: the promotion-selection correction for the MiLB→MLB MLE.

Pure numpy/pandas (no S3, no DuckDB, no `pipeline` import) so the fast gate exercises the whole
mechanism directly — the repo rule for model-quality code, since CI mocks all IO.

WHAT THIS IS FOR, STATED CORRECTLY (an earlier draft of the story prompt got this backwards and the
error is worth carrying as a comment, because it changes what the slice should even try to do)
---------------------------------------------------------------------------------------------------
The MLE is fit on GRADUATES and served on PROSPECTS. Only ~7.5% of batters in the substrate ever debut.
It is tempting to say "promotion is decided on the minor-league line, which IS the model's feature, so
the fit is biased" — **that is false**. Selection on an OBSERVED covariate leaves `E[Y|X]` unbiased; it
is the textbook harmless case. Two things actually motivate a correction:

  (a) **THE ESTIMAND (the defensible one).** We fit where the data is dense — good prospects who got
      promoted — and serve where it is sparse. Even with unbiased coefficients, the fit is optimised
      for the wrong population. Re-weighting training toward the served population is a statement
      about WHICH conditional mean we want, not a bias fix.
  (b) **SELECTION ON UNOBSERVABLES.** Scouts promote on tools, makeup, health and organisational need.
      None of that is in the design matrix, and all of it plausibly predicts MLB performance. If the
      selection error correlates with the outcome error, the translation IS biased — the Heckman case.

⚠️ Consequence worth stating plainly: **IPW does not address (b).** Inverse-propensity weighting fixes
selection on OBSERVABLES, under which the conditional mean was already fine. IPW's job here is (a).

🚨 RIGHT-CENSORING IS THE FIRST PROBLEM, NOT A DETAIL
-----------------------------------------------------
Measured on the live substrate 2026-07-31: **37.3% of the "never-MLB" batters (3,385 of 9,068) were
still active in MiLB in 2023 or later, and 1,921 were playing in 2026.** Those players have not FAILED
to be promoted — they have not FINISHED. A naive `debuted ∈ {0,1}` propensity model fit on that
population learns "recent players do not get promoted", which is FOLLOW-UP TIME wearing selection's
clothes, and IPW would then inflate the weights on exactly the most recent cohorts — the opposite of
the intended correction, and invisible in an overall MAE.

So the propensity here is a **DISCRETE-TIME HAZARD**: each player contributes one row per MiLB season
they were still un-promoted, `promoted_this_season ∈ {0,1}`, and a player is CENSORED at their last
observed MiLB season rather than counted as a permanent failure. The cumulative promotion probability
over a fixed horizon then follows from the per-season hazards. `censoring_diagnostic()` is the guard:
a fitted promotion rate that declines monotonically in recency means the model learned the censoring.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# The hazard model's covariates. Deliberately SMALL and all pre-promotion: this is a nuisance model, and
# an over-fit propensity produces extreme weights, which is the failure mode that eats IPW.
HAZARD_FEATURES: tuple[str, ...] = ("minor_rate_z", "age_z", "log_pa", "season_index")

# Propensity floor/ceiling. An IPW weight is 1/p; without a floor a single p≈0.001 graduate carries a
# weight of 1,000 and IS the fit. Trimming is not optional and the trimmed share must be reported.
DEFAULT_PROPENSITY_CLIP: tuple[float, float] = (0.02, 0.98)

# IPW weight clip, applied AFTER normalisation to mean 1. Mirrors `PartialPoolProjector._weights`'s own
# [0.2, 5.0] tail clip so the two do not silently compound into something neither chose.
DEFAULT_WEIGHT_CLIP: tuple[float, float] = (0.2, 5.0)

# Terciles of the propensity distribution — the stratified score. See `propensity_strata`.
N_STRATA = 3

# The FIXED promotion horizon, in MiLB seasons from a player's first season at a level. See
# `fixed_horizon_propensity` for why a fixed window is not a detail but the whole basis of the estimand.
DEFAULT_HORIZON = 4

# Per-cohort binomial z below which observed promotions are "far fewer than the fitted model expects".
# -3 is ~1-in-750 two-sided per cohort; over ~11 cohorts the family-wise false-flag rate is ~1.5%.
CENSORING_Z = -3.0


@dataclass(frozen=True)
class HazardFit:
    """A fitted discrete-time promotion hazard + everything needed to audit it."""

    coef: np.ndarray
    features: tuple[str, ...]
    n_person_seasons: int
    n_events: int
    n_censored_players: int
    base_rate: float
    converged: bool

    def hazard(self, X: np.ndarray) -> np.ndarray:
        return _sigmoid(X @ self.coef)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    out = np.empty_like(z, dtype=float)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


# Which column carries "how good was the minor-league line" for the hazard. The first one PRESENT wins.
# `_hazard_rate` is the synthetic-truth column the unit tests plant; the real ones are the substrate's
# summary rate (batters: wOBA; pitchers: xwOBA-against, where LOWER is better — the hazard only needs to
# ORDER players, so the coefficient simply comes back negative on that side and nothing downstream cares).
RATE_COL_PREFERENCE: tuple[str, ...] = ("_hazard_rate", "minor_woba", "minor_xwoba_against")


def resolve_rate_col(pairs: pd.DataFrame,
                     preference: tuple[str, ...] = RATE_COL_PREFERENCE) -> str | None:
    """First present, non-all-null column from `preference`.

    🪤 Returns None rather than guessing when nothing matches — and `build_person_seasons` then RAISES.
    A hazard silently fit on an all-NaN rate is the worst outcome available: it converges, produces a
    smooth propensity, and every IPW weight downstream is a function of age and PA alone while the
    report says the propensity is quality-driven.
    """
    for c in preference:
        if c in pairs.columns and pd.to_numeric(pairs[c], errors="coerce").notna().any():
            return c
    return None


def build_person_seasons(pairs: pd.DataFrame, *, horizon: int | None = None,
                         rate_col: str | None = None) -> pd.DataFrame:
    """Explode one row per (player, level) into one row per (player, level, MiLB season at risk).

    A player is AT RISK in every season from `first_minor_season` through the season they were promoted
    (`debut_cohort`) or, if never promoted, their `last_minor_season` — at which point they are
    **CENSORED, not failed**. `event = 1` only in the promotion season.

    ⚠️ This is the whole point of the module: without the censoring distinction, the never-promoted
    population is 37% players who simply have not finished yet, and the model learns recency.

    ⚠️ **The covariates are the player's LEVEL-AGGREGATE line, held constant across their at-risk
    seasons** — the substrate is aggregated per (player, level), so a genuinely time-varying hazard is not
    expressible without re-deriving the pairs per season. That is a real limitation and it bounds what
    this propensity can claim: it separates players, not a player's own trajectory. It does NOT threaten
    the censoring correction, which is about the LENGTH of the at-risk window, not its contents.
    """
    need = {"player_id", "level", "first_minor_season", "last_minor_season"}
    missing = need - set(pairs.columns)
    if missing:
        raise KeyError(
            f"pairs is missing {sorted(missing)} — the survivorship slice needs the as-of MiLB window "
            f"on EVERY row including the never-promoted ones. Rebuild with the E7.12-S2 "
            f"`build_graduated_pairs*` (it adds first/last_minor_season); a pre-S2 artifact cannot "
            f"support a leakage-safe or censoring-aware promotion model.")

    rate_col = rate_col or resolve_rate_col(pairs)
    if rate_col is None or rate_col not in pairs.columns:
        raise KeyError(
            f"no usable minor-league rate column (tried {list(RATE_COL_PREFERENCE)}) — pass `rate_col=`. "
            f"Refusing to fit the hazard on age and PA alone while reporting a quality-driven propensity.")

    df = pairs.copy()
    first = pd.to_numeric(df["first_minor_season"], errors="coerce")
    last = pd.to_numeric(df["last_minor_season"], errors="coerce")
    debut = pd.to_numeric(df.get("debut_cohort"), errors="coerce")
    ok = first.notna() & last.notna() & (last >= first)
    df, first, last, debut = df[ok], first[ok], last[ok], debut[ok]

    max_season = int(last.max())
    rows = []
    for i, (_, r) in enumerate(df.iterrows()):
        f, l = int(first.iloc[i]), int(last.iloc[i])
        d = debut.iloc[i]
        promoted = bool(pd.notna(d))
        # at risk through the debut season (inclusive) or through the last observed MiLB season
        end = int(d) if promoted and int(d) >= f else l
        if horizon is not None:
            end = min(end, f + horizon - 1)
        # 🪤 A never-promoted player's last season means one of TWO completely different things, and
        # collapsing them is what makes a promotion model uninterpretable: if he was still playing in the
        # final observed season he is CENSORED (not finished); otherwise he EXITED affiliated ball, which
        # is a real, observed, terminal event — and the one that happens to 85% of them.
        exited = (not promoted) and l < max_season
        for s in range(f, end + 1):
            rows.append({
                "player_id": r["player_id"], "level": r["level"], "season": s,
                "season_index": s - f,
                "event": int(promoted and int(d) == s),
                "exited": int(exited and s == end),
                "censored": int(not promoted and not exited and s == end),
                "minor_rate": r.get(rate_col, np.nan),
                "age": r.get("age", np.nan),
                "minor_pa": r.get("minor_pa", np.nan),
            })
    return pd.DataFrame(rows)


# The reduced feature set for a STABILIZED-IPW numerator model: calendar position only, no player
# covariates. 🪤 A stabilized weight is `p_marginal / p_full`; if the numerator is a CONSTANT (the sample
# mean propensity) then after normalising the weights to mean 1 the constant cancels EXACTLY and the
# "stabilized" arm is byte-identical to the raw one — a second arm that is the same arm, inflating the
# field the deflation is computed over. The numerator has to be a MODEL, not a scalar.
MARGINAL_FEATURES: tuple[str, ...] = ("season_index",)


def _design(ps: pd.DataFrame, mu: dict | None = None,
            features: tuple[str, ...] = HAZARD_FEATURES) -> tuple[np.ndarray, dict]:
    """Standardised design for the hazard, with an intercept. Returns the scaler so PREDICT reuses the
    TRAIN statistics — standardising on the prediction rows would leak the test fold's distribution."""
    rate = pd.to_numeric(ps.get("minor_rate"), errors="coerce")
    age = pd.to_numeric(ps.get("age"), errors="coerce")
    pa = pd.to_numeric(ps.get("minor_pa"), errors="coerce")
    log_pa = np.log1p(pa.fillna(0.0).clip(lower=0.0))
    si = pd.to_numeric(ps.get("season_index"), errors="coerce").fillna(0.0)

    raw = {"minor_rate_z": rate, "age_z": age, "log_pa": log_pa, "season_index": si}
    if mu is None:
        mu = {}
        for k, v in raw.items():
            m = float(v.mean()) if v.notna().any() else 0.0
            s = float(v.std(ddof=0)) if v.notna().sum() > 1 and float(v.std(ddof=0)) > 0 else 1.0
            mu[k] = (m, s)
    cols = [np.ones(len(ps))]
    for k in features:
        m, s = mu[k]
        cols.append(((raw[k] - m) / s).fillna(0.0).to_numpy(float))
    return np.column_stack(cols), mu


def fit_hazard(person_seasons: pd.DataFrame, *, l2: float = 1.0, event_col: str = "event",
               features: tuple[str, ...] = HAZARD_FEATURES,
               max_iter: int = 100, tol: float = 1e-8) -> tuple[HazardFit, dict]:
    """L2-penalised logistic regression on the person-season panel (Newton-Raphson).

    The penalty is not cosmetic: an unpenalised propensity separates on thin cells, drives p→0 for some
    graduates, and 1/p then hands one row the entire fit. A nuisance model wants to be smooth, not sharp.

    `event_col` selects which per-season transition is being modelled — `event` (promotion) or `exited`
    (leaving affiliated ball, the competing risk). Same panel, same covariates, two hazards.
    """
    X, mu = _design(person_seasons, features=features)
    y = pd.to_numeric(person_seasons[event_col], errors="coerce").fillna(0.0).to_numpy(float)
    n, p = X.shape
    beta = np.zeros(p)
    pen = np.full(p, float(l2))
    pen[0] = 0.0                       # never penalise the intercept — that would shift the base rate
    converged = False
    for _ in range(max_iter):
        eta = X @ beta
        mu_i = _sigmoid(eta)
        w = np.clip(mu_i * (1.0 - mu_i), 1e-9, None)
        grad = X.T @ (y - mu_i) - pen * beta
        H = (X * w[:, None]).T @ X + np.diag(pen)
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(H, grad, rcond=None)[0]
        beta = beta + step
        if float(np.max(np.abs(step))) < tol:
            converged = True
            break
    fit = HazardFit(
        coef=beta, features=features, n_person_seasons=int(n), n_events=int(y.sum()),
        n_censored_players=int(pd.to_numeric(person_seasons.get("censored"), errors="coerce")
                               .fillna(0).sum()),
        base_rate=float(y.mean()) if n else 0.0, converged=converged,
    )
    return fit, mu


def cumulative_promotion_probability(fit: HazardFit, person_seasons: pd.DataFrame, mu: dict,
                                     keys: tuple[str, ...] = ("player_id", "level")) -> pd.DataFrame:
    """Per-(player, level) `P(promoted at some point in the observed window)` from the per-season hazards:
    `1 - prod_s (1 - h_s)`. This is the propensity IPW inverts."""
    X, _ = _design(person_seasons, mu, features=fit.features)
    h = np.clip(fit.hazard(X), 1e-9, 1 - 1e-9)
    tmp = person_seasons[list(keys)].copy()
    tmp["_log1mh"] = np.log1p(-h)
    g = tmp.groupby(list(keys), dropna=False)["_log1mh"].sum().reset_index()
    g["propensity"] = 1.0 - np.exp(g["_log1mh"].to_numpy(float))
    return g[list(keys) + ["propensity"]]


def fixed_horizon_propensity(fit: HazardFit, person_seasons: pd.DataFrame, mu: dict,
                             *, horizon: int = DEFAULT_HORIZON, max_season: int | None = None,
                             exit_fit: HazardFit | None = None, exit_mu: dict | None = None,
                             keys: tuple[str, ...] = ("player_id", "level")) -> pd.DataFrame:
    """`P(promoted within `horizon` seasons of entering the level)` — the propensity IPW should invert.

    🚨 **WHY NOT `cumulative_promotion_probability`, WHICH LOOKS LIKE THE SAME THING.** That function
    multiplies over the seasons a player was ACTUALLY at risk, and that window is OUTCOME-DEPENDENT: a
    promoted player's risk window ENDS at his promotion, so it is short, so his expected promotion
    probability is small. Aggregate that over a cohort and expected is systematically depressed exactly
    where promotions happened — which is why the observed/expected ratio on live data sits at ~1.29 for
    mature cohorts instead of ~1.0. A calibration statistic built on it is measuring its own construction.

    A FIXED window is not outcome-dependent: every player gets `season_index = 0..horizon-1` evaluated
    from the model, promoted or not. Expected is then a real counterfactual ("how likely was this player
    to be promoted within four seasons"), the mature cohorts calibrate to ~1.0, and the only thing that
    can make a cohort fall short is that the CALENDAR cut its window off — which is the censoring the
    guard is looking for, and which is also reported structurally as `follow_up_complete`.

    🚨 **`exit_fit` IS NOT OPTIONAL IN PRACTICE — WITHOUT IT THIS OVER-PREDICTS BY ~2.2×.** A survival
    product `1 - Π(1-h)` assumes the player is still there to be promoted in all `horizon` seasons. On
    the live substrate the mean at-risk window is **2.05 seasons**, and **85% of never-promoted players
    LEAVE affiliated ball** rather than sitting around being un-promoted. Attrition is not a nuisance
    here, it is the dominant competing risk, and ignoring it makes every mature cohort look like it
    under-promotes by half (measured o/e ≈ 0.45, z ≈ -24 — a "calibration check" that is really just
    measuring the missing risk). With the exit hazard supplied this becomes a proper two-state walk:

        S_0 = 1;  P(promote at k) = S_k · h_k;  S_{k+1} = S_k · (1 - h_k) · (1 - e_k)

    ⇒ pass `exit_fit`/`exit_mu` from a second `fit_hazard(..., event_col="exited")` on the same panel.

    Returns one row per key with `propensity`, `entry_cohort`, `follow_up_seasons` and
    `follow_up_complete` (the window fits inside the observed calendar).
    """
    ps = person_seasons
    if max_season is None:
        max_season = int(pd.to_numeric(ps["season"], errors="coerce").max())

    # one representative covariate row per player-level (the covariates are level-aggregate, so any row
    # carries them); `entry` is the player's first at-risk season
    base = (ps.sort_values("season").groupby(list(keys), dropna=False, as_index=False)
              .agg(entry_cohort=("season", "min"), minor_rate=("minor_rate", "first"),
                   age=("age", "first"), minor_pa=("minor_pa", "first")))

    # expand each player across the FIXED horizon, regardless of what actually happened to them
    rep = base.loc[base.index.repeat(horizon)].reset_index(drop=True)
    rep["season_index"] = np.tile(np.arange(horizon), len(base))
    X, _ = _design(rep, mu, features=fit.features)
    h = np.clip(fit.hazard(X), 1e-9, 1 - 1e-9).reshape(len(base), horizon)
    if exit_fit is not None:
        Xe, _ = _design(rep, exit_mu if exit_mu is not None else mu,
                        features=exit_fit.features)
        e = np.clip(exit_fit.hazard(Xe), 1e-9, 1 - 1e-9).reshape(len(base), horizon)
    else:
        e = np.zeros_like(h)

    # two-state walk: promote, exit, or survive to the next season
    surv = np.ones(len(base))
    prom = np.zeros(len(base))
    for k in range(horizon):
        prom += surv * h[:, k]
        surv = surv * (1.0 - h[:, k]) * (1.0 - e[:, k])
    base = base.assign(propensity=prom)

    out = base[list(keys) + ["entry_cohort", "propensity"]].copy()
    out["follow_up_seasons"] = (max_season - out["entry_cohort"] + 1).clip(upper=horizon)
    out["follow_up_complete"] = out["follow_up_seasons"] >= horizon
    return out


def ipw_weights(propensity: np.ndarray | pd.Series,
                clip: tuple[float, float] = DEFAULT_PROPENSITY_CLIP,
                weight_clip: tuple[float, float] = DEFAULT_WEIGHT_CLIP) -> tuple[np.ndarray, dict]:
    """`1/p̂`, trimmed then normalised to mean 1, plus the audit a weighted fit is not honest without.

    ⭐ **EFFECTIVE SAMPLE SIZE IS PART OF THE RESULT, NOT A DIAGNOSTIC.** Kish's ESS
    `(Σw)² / Σw²` says how many observations the weighted fit actually behaves like. IPW buys
    population-representativeness by SPENDING sample size, and an arm that quietly drops the effective n
    from 2,171 to 400 has traded bias for variance. Reporting only MAE hides that entirely.
    """
    p = pd.to_numeric(pd.Series(propensity), errors="coerce").to_numpy(float)
    lo, hi = clip
    n = len(p)
    finite = np.isfinite(p)
    trimmed = int(np.sum(finite & ((p < lo) | (p > hi))))
    p = np.where(finite, np.clip(p, lo, hi), np.nan)
    med = float(np.nanmedian(p)) if np.isfinite(p).any() else 1.0
    p = np.nan_to_num(p, nan=med)
    w = 1.0 / p
    mean = float(np.mean(w))
    w = w / mean if mean > 0 else np.ones(n)
    w = np.clip(w, *weight_clip)
    ess = float((w.sum() ** 2) / np.sum(w ** 2)) if n else 0.0
    return w, {
        "n": n,
        "n_propensity_trimmed": trimmed,
        "pct_propensity_trimmed": round(100.0 * trimmed / n, 3) if n else 0.0,
        "ess": round(ess, 1),
        "ess_fraction": round(ess / n, 4) if n else 0.0,
        "weight_min": round(float(w.min()), 4) if n else None,
        "weight_max": round(float(w.max()), 4) if n else None,
    }


def propensity_strata(propensity: pd.Series, n_strata: int = N_STRATA) -> pd.Series:
    """Tercile labels 0..k-1 (0 = LOWEST propensity). Ties are broken by rank so a lumpy propensity
    distribution still yields non-empty strata."""
    p = pd.to_numeric(propensity, errors="coerce")
    r = p.rank(method="first", na_option="keep")
    q = np.ceil(r / max(len(p.dropna()), 1) * n_strata)
    return q.clip(1, n_strata).sub(1).astype("Int64")


def censoring_diagnostic(person_seasons: pd.DataFrame, fit: HazardFit, mu: dict,
                         *, horizon: int = DEFAULT_HORIZON, min_cohort_n: int = 20,
                         z_crit: float = CENSORING_Z, max_season: int | None = None,
                         exit_fit: HazardFit | None = None, exit_mu: dict | None = None) -> dict:
    """🚨 THE GUARD FOR THE FAILURE THIS MODULE EXISTS TO PREVENT — two independent readings.

    ⚠️⚠️ **THIS GUARD'S FIRST VERSION PASSED ITS UNIT TESTS AND THEN STAYED SILENT ON LIVE DATA WHOSE
    NEWEST COHORT PROMOTES AT A QUARTER OF ITS EXPECTED RATE.** Three separate defects, each worth
    carrying because each is a general trap:

      1. **THE POSITIVE ANCHOR WAS DEGENERATE.** The synthetic "censored" world forced recent entrants to
         `promoted=False`, i.e. o/e of exactly 0.000. Real censoring is PARTIAL (live batter cohorts run
         0.80 / 0.64 / 0.26). Proving a guard fires on total truncation says nothing about whether it
         fires on the regime that actually occurs — and it did not.
      2. **THE NEGATIVE ANCHOR WAS NOT NEGATIVE.** The "clean" world capped every window at the same
         calendar horizon, so recent entrants were truncated there too (92% of 2023+ entrants
         never-promoted, mean window 3.3 vs 4.3). Tuning a threshold to stay quiet on a control that is
         itself contaminated is how the threshold ended up too lax to fire on anything real.
      3. **THE STATISTIC IGNORED COHORT SIZE.** A ratio threshold cannot serve a 90-player toy cohort and
         a 1,400-player real cohort at once. The z-score below is the same instrument at both scales.

    ⇒ the general lesson, and it is the E2.1-r oracle rule pointed at a GUARD rather than a metric:
    **verifying a guard on synthetic data verifies its MECHANISM, not its THRESHOLD.** A guard is not
    trustworthy until it has been fired on the real population it will police.

    Two readings, deliberately not collapsed into one number:

      • **STRUCTURAL** (`n_incomplete_followup`, definitional, cannot be fooled by a model error): a
        cohort entering later than `max_season - horizon + 1` simply has not been observed long enough.
      • **EMPIRICAL** (`cohort_z`, catches hazard mis-specification the structural check cannot see):
        observed promotions within the horizon vs the fitted model's expectation, as a Poisson-binomial
        z — `(obs - Σp) / sqrt(Σ p(1-p))`, which is scale-free across cohort sizes.
    """
    """🚨 THE GUARD FOR THE FAILURE THIS MODULE EXISTS TO PREVENT — as an OBSERVED-vs-EXPECTED
    CALIBRATION CHECK BY ENTRY COHORT, which is the only form of it that actually discriminates.

    ⚠️ **A NAIVE VERSION OF THIS GUARD DOES NOT WORK, AND THE REASON IS INSTRUCTIVE.** The first
    implementation asked whether the FITTED PER-SEASON HAZARD declines in recent calendar seasons. It
    failed in BOTH directions on synthetic worlds — silent on a censoring-only world, firing on a clean
    one. The hazard carries no calendar-time covariate, so censoring CANNOT express itself in the
    per-season rate; and any slight drift in covariate composition trips a monotone-decline test. The
    contamination lands somewhere else entirely: **in the CUMULATIVE probability**, because a truncated
    player is simply at risk for fewer seasons.

    So the discriminating question is not "does the rate decline?" but **"do recent entry cohorts get
    promoted LESS OFTEN THAN THEIR OWN WINDOW LENGTH PREDICTS?"** — expected already accounts for a short
    window (it is a product over the seasons the player was actually at risk), so a large observed
    shortfall on top of that is censoring rather than a real cohort difference.

    A True flag means every IPW weight derived from this hazard is suspect regardless of MAE.
    """
    ps = person_seasons.copy()
    if max_season is None:
        max_season = int(pd.to_numeric(ps["season"], errors="coerce").max())
    prop = fixed_horizon_propensity(fit, ps, mu, horizon=horizon, max_season=max_season,
                                    exit_fit=exit_fit, exit_mu=exit_mu)

    # observed = promoted WITHIN the same fixed horizon, so observed and expected answer one question
    ps["_si"] = pd.to_numeric(ps["season_index"], errors="coerce")
    obs = (ps[ps["_si"] < horizon].groupby(["player_id", "level"], dropna=False)["event"]
             .max().rename("promoted").reset_index())
    d = prop.merge(obs, on=["player_id", "level"], how="left")
    d["promoted"] = d["promoted"].fillna(0).astype(int)
    d["_var"] = d["propensity"] * (1.0 - d["propensity"])

    g = (d.groupby("entry_cohort", as_index=False)
           .agg(n=("promoted", "size"), obs_n=("promoted", "sum"),
                exp_n=("propensity", "sum"), var_n=("_var", "sum"),
                follow_up=("follow_up_seasons", "max"),
                complete=("follow_up_complete", "max"))
           .sort_values("entry_cohort"))
    g["observed"] = g["obs_n"] / g["n"]
    g["expected"] = g["exp_n"] / g["n"]
    g["oe"] = np.where(g["exp_n"] > 0, g["obs_n"] / g["exp_n"], np.nan)
    g["z"] = np.where(g["var_n"] > 0, (g["obs_n"] - g["exp_n"]) / np.sqrt(g["var_n"]), np.nan)

    ev = g[g["n"] >= min_cohort_n].copy()
    ev["flagged"] = (ev["z"] < z_crit) & (~ev["complete"].astype(bool))
    flagged = ev[ev["flagged"]]
    n_incomplete = int(ev.loc[~ev["complete"].astype(bool), "n"].sum())
    total_n = int(ev["n"].sum())
    contaminated = bool(len(flagged))
    mature = ev[ev["complete"].astype(bool)]

    cohorts = ", ".join(f"{int(r.entry_cohort)} (o/e {r.oe:.2f}, z {r.z:+.1f})"
                        for r in flagged.itertuples()) or "none"
    return {
        "horizon": horizon,
        "by_entry_cohort": g.to_dict(orient="records"),
        "flagged_cohorts": [int(c) for c in flagged["entry_cohort"]],
        "n_incomplete_followup": n_incomplete,
        "pct_incomplete_followup": round(100.0 * n_incomplete / total_n, 2) if total_n else 0.0,
        "mature_oe_mean": round(float(mature["oe"].mean()), 4) if len(mature) else None,
        "mature_oe_range": ([round(float(mature["oe"].min()), 4), round(float(mature["oe"].max()), 4)]
                            if len(mature) else None),
        "recent_cohorts_are_censoring_contaminated": contaminated,
        "reading": (
            f"⛔ {len(flagged)} entry cohort(s) promote FAR less often than the fitted model expects over "
            f"a {horizon}-season horizon — {cohorts}. Their windows do not fit inside the observed "
            f"calendar, so they are RIGHT-CENSORED ('not promoted YET', not 'not promoted'). "
            f"{n_incomplete:,} of {total_n:,} players ({100.0*n_incomplete/max(total_n,1):.1f}%) sit in "
            f"an incomplete-follow-up cohort. Every propensity over them is depressed for a reason that "
            f"has nothing to do with selection, and IPW would up-weight the OLDEST cohorts. RESTRICT the "
            f"risk set to complete-follow-up cohorts before reading any lift from this run."
            if contaminated else
            f"✅ no entry cohort promotes materially below its {horizon}-season expectation "
            f"(mature o/e {ev['oe'].min():.2f}–{ev['oe'].max():.2f}); no censoring contamination "
            f"detectable at this horizon."),
    }
