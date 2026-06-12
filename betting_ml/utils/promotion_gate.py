"""Canonical model-promotion gate (model-agnostic: frequentist AND Bayesian).

WHY THIS EXISTS
---------------
Promotion was ad-hoc: "challenger beats champion on the latest season" — which
overfits to a partial, regime-specific sample (the current season is the smallest,
noisiest, least-complete fold) and thrashes the deployed champion every spring as the
run environment shifts. This module makes the rule explicit, consistent, and robust.

THE RULESET (operator decision 2026-06-12; see implementation_guide.md
"⭐ MODEL PROMOTION GATE" + docs/model_promotion_runbook.md):

  PROMOTE a challenger over the production champion iff ALL hold on the
  accuracy-to-truth metric (lower = better for every scorer here):

   1. CROSS-SEASON, walk-forward. Judge on the mean over COMPLETED held-out seasons,
      never the current partial season. (We never train on the future; folds are
      season-forward — see cv_splits.all_season_splits.)
   2. EFFECT SIZE beyond the noise floor. The pooled per-game improvement must exceed
      a per-metric noise floor (≈ sampling noise on ~700 games/season), not a bare
      point delta.
   3. STATISTICAL SIGNIFICANCE. A season-stratified PAIRED bootstrap CI of the
      per-game (challenger − champion) score must lie entirely below 0 (challenger
      reliably better), not just on average.
   4. NO COMPLETED-SEASON REGRESSION. The challenger must not get worse than the noise
      floor on ANY completed season. Win-overall-and-lose-2024 = overfitting → HOLD.
   5. CURRENT SEASON = CORROBORATION ONLY. Reported, and a strong regression is flagged,
      but it never DRIVES a PROMOTE (too small / regime-specific). Requires a minimum
      game count before it's even considered informative.
   6. HYSTERESIS (operational, threaded by the caller). Promotion should require the
      gate to pass on >= `min_consecutive_passes` independent evaluations and respect a
      minimum re-eval interval — to stop monthly redeploys chasing early-season regime
      noise. A single call returns one verdict; the caller tracks the streak.

  Beating the MARKET is NOT a promotion condition (the production champion does not beat
  the market either) — closeness-to-truth is the gate; market edge is secondary context.
  See memory project_promote_on_point_accuracy / project_search_baseline_misleading.

FREQUENTIST *AND* BAYESIAN
--------------------------
The gate consumes a per-game SCORE array (lower = better) and does not care how it was
produced. That makes it identical for a point model and a posterior-predictive one:

  - Point/frequentist:  abs_error (→ MAE), brier (classification), or the closed-form
    crps_normal / nll_normal / nll_lognormal of an NGBoost predictive dist.
  - Bayesian / sample-based (PyMC posterior predictive draws, Epic 17): crps_ensemble
    (proper, distribution-free — the unifying accuracy-to-truth score: CRPS of a point
    mass reduces to absolute error, so a point model and a posterior are compared on the
    SAME ruler) or nll_ensemble (Gaussian-approx predictive density).

So a Bayesian challenger is judged by exactly criteria 1–6, scored with crps_ensemble,
against the champion's crps_normal (or its own crps_ensemble) on the shared OOS games.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

try:  # SciPy is a project dep; fall back to a numpy erf if ever absent.
    from scipy.stats import norm as _norm

    def _Phi(z):
        return _norm.cdf(z)

    def _phi(z):
        return _norm.pdf(z)
except Exception:  # pragma: no cover
    def _Phi(z):
        from math import erf, sqrt
        return 0.5 * (1.0 + np.vectorize(erf)(np.asarray(z) / np.sqrt(2.0)))

    def _phi(z):
        return np.exp(-0.5 * np.asarray(z) ** 2) / np.sqrt(2.0 * np.pi)


# ── Per-game scorers — LOWER IS BETTER for every one ─────────────────────────

def abs_error(y, mean) -> np.ndarray:
    """Point accuracy → MAE when averaged. (= CRPS of a point mass.)"""
    return np.abs(np.asarray(mean, float) - np.asarray(y, float))


def squared_error(y, mean) -> np.ndarray:
    return (np.asarray(mean, float) - np.asarray(y, float)) ** 2


def brier(y, p) -> np.ndarray:
    """Per-game Brier for a binary outcome y∈{0,1} and P(y=1)=p."""
    return (np.asarray(p, float) - np.asarray(y, float)) ** 2


def nll_normal(y, loc, scale, eps: float = 1e-9) -> np.ndarray:
    y, loc, scale = (np.asarray(a, float) for a in (y, loc, scale))
    scale = np.maximum(scale, eps)
    return 0.5 * np.log(2 * np.pi * scale ** 2) + 0.5 * ((y - loc) / scale) ** 2


def nll_lognormal(y, loc, scale, eps: float = 1e-9) -> np.ndarray:
    """NLL of a LogNormal whose UNDERLYING normal is N(loc, scale) (NGBoost LogNormal
    parameterization). y must be > 0."""
    y, loc, scale = (np.asarray(a, float) for a in (y, loc, scale))
    scale = np.maximum(scale, eps)
    y = np.maximum(y, eps)
    return (np.log(y) + 0.5 * np.log(2 * np.pi * scale ** 2)
            + 0.5 * ((np.log(y) - loc) / scale) ** 2)


def crps_normal(y, loc, scale, eps: float = 1e-9) -> np.ndarray:
    """Closed-form CRPS of N(loc, scale). Proper; reduces toward |y-loc| as scale→0."""
    y, loc, scale = (np.asarray(a, float) for a in (y, loc, scale))
    scale = np.maximum(scale, eps)
    z = (y - loc) / scale
    return scale * (z * (2 * _Phi(z) - 1) + 2 * _phi(z) - 1.0 / np.sqrt(np.pi))


def crps_ensemble(y, samples) -> np.ndarray:
    """Distribution-free CRPS from predictive SAMPLES (Bayesian posterior predictive,
    bootstrap ensembles, etc.). `samples` is (n_games, n_draws).

        CRPS = E|X - y| - 0.5 E|X - X'|

    This is the unifying accuracy-to-truth score: works for ANY predictive distribution
    and reduces to absolute error for a degenerate (point) predictive.
    """
    y = np.asarray(y, float)
    S = np.asarray(samples, float)
    if S.ndim == 1:
        S = S[:, None]
    m = S.shape[1]
    term1 = np.mean(np.abs(S - y[:, None]), axis=1)
    # E|X - X'| via the sorted-sample identity: (2/m^2) * sum_i (2i - m - 1) x_(i)
    Ss = np.sort(S, axis=1)
    idx = np.arange(1, m + 1)
    coef = (2 * idx - m - 1)
    term2 = (2.0 / (m * m)) * np.sum(coef[None, :] * Ss, axis=1)
    return term1 - 0.5 * term2


def nll_ensemble(y, samples, eps: float = 1e-9) -> np.ndarray:
    """Approximate per-game NLL from predictive samples via a Gaussian fit to each
    game's draws. Use crps_ensemble when you want a distribution-free score; this is the
    log-density analog when NLL is the agreed metric (e.g. matching the Epic 17/totals
    three-layer L1 prior-predictive NLL gate)."""
    S = np.asarray(samples, float)
    if S.ndim == 1:
        S = S[:, None]
    loc = S.mean(axis=1)
    scale = np.maximum(S.std(axis=1, ddof=1) if S.shape[1] > 1 else np.full(S.shape[0], eps), eps)
    return nll_normal(y, loc, scale, eps)


# Noise-floor effect size per metric — the minimum pooled improvement (in metric units)
# that counts as real rather than sampling noise on ~700 games/season. Conservative;
# override per call when you have a measured noise floor for the target.
NOISE_FLOOR = {
    "mae": 0.02,        # runs (run_diff / total_runs)
    "rmse": 0.03,
    "brier": 0.002,     # home_win classification
    "crps": 0.02,       # runs, distributional
    "nll": 0.01,        # nats
}

MIN_CURRENT_SEASON_GAMES = 200   # below this, the current partial season is non-informative
MIN_CONSECUTIVE_PASSES = 2       # hysteresis: gate must pass this many evals before promoting


def bernoulli_nll(y, p, eps: float = 1e-7) -> np.ndarray:
    p = np.clip(np.asarray(p, float), eps, 1 - eps)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


@dataclass
class PredictiveOutput:
    """Uniform per-game predictive output so ANY model maps to comparable scores.

    A model adapter returns one of these; `score_to_truth` turns it into the per-game
    accuracy-to-truth score the gate consumes. This is the contract that lets a
    frequentist point model, an NGBoost predictive, and a Bayesian posterior-predictive
    (PyMC) all be judged on the SAME metric on the SAME games.

    kind ∈ {'point','binary_prob','normal','lognormal','samples'}. `mean` (the predictive
    mean / point estimate) is always populated; the kind-specific fields back the
    distributional metrics (crps/nll).
    """
    kind: str
    mean: np.ndarray
    prob: np.ndarray | None = None       # binary_prob: P(y=1)
    loc: np.ndarray | None = None        # normal/lognormal: underlying-normal mean
    scale: np.ndarray | None = None      # normal/lognormal: underlying-normal sd
    samples: np.ndarray | None = None    # samples: (n_games, n_draws)

    # ── constructors ─────────────────────────────────────────────────────────
    @classmethod
    def point(cls, mean):
        return cls("point", np.asarray(mean, float))

    @classmethod
    def binary(cls, prob):
        p = np.asarray(prob, float)
        return cls("binary_prob", p, prob=p)

    @classmethod
    def normal(cls, loc, scale):
        loc = np.asarray(loc, float)
        return cls("normal", loc, loc=loc, scale=np.asarray(scale, float))

    @classmethod
    def lognormal(cls, loc, scale):
        loc, scale = np.asarray(loc, float), np.asarray(scale, float)
        return cls("lognormal", np.exp(loc + scale ** 2 / 2), loc=loc, scale=scale)

    @classmethod
    def from_samples(cls, samples):
        S = np.asarray(samples, float)
        if S.ndim == 1:
            S = S[:, None]
        return cls("samples", S.mean(axis=1), samples=S)

    # ── scoring ──────────────────────────────────────────────────────────────
    def score_to_truth(self, y, metric: str, *, n_draws: int = 500, seed: int = 0) -> np.ndarray:
        """Per-game score (LOWER = better) under `metric` ∈
        {'mae','mse','brier','crps','nll'}. Raises if the metric is undefined for this
        output kind (e.g. 'nll' on a bare point prediction) so a mis-paired comparison
        fails loudly instead of silently."""
        y = np.asarray(y, float)
        if metric == "mae":
            return abs_error(y, self.mean)
        if metric == "mse":
            return squared_error(y, self.mean)
        if metric == "brier":
            if self.prob is None:
                raise ValueError("brier requires a binary_prob output")
            return brier(y, self.prob)
        if metric == "crps":
            if self.kind == "normal":
                return crps_normal(y, self.loc, self.scale)
            if self.kind == "samples":
                return crps_ensemble(y, self.samples)
            if self.kind == "lognormal":
                rng = np.random.default_rng(seed)
                draws = np.exp(self.loc[:, None] + self.scale[:, None] * rng.standard_normal((len(y), n_draws)))
                return crps_ensemble(y, draws)
            return abs_error(y, self.mean)  # point / binary → CRPS of a point mass = |·|
        if metric == "nll":
            if self.kind == "normal":
                return nll_normal(y, self.loc, self.scale)
            if self.kind == "lognormal":
                return nll_lognormal(y, self.loc, self.scale)
            if self.kind == "samples":
                return nll_ensemble(y, self.samples)
            if self.kind == "binary_prob":
                return bernoulli_nll(y, self.prob)
            raise ValueError("nll undefined for a bare 'point' output (no density)")
        raise ValueError(f"unknown metric {metric!r}")


# ── Calibration diagnostics for distributional predictives ───────────────────
# MAE/CRPS judge the POINT; these judge whether the predicted DISTRIBUTION is honest.
# Required before a distributional model (e.g. an NGBoost LogNormal totals challenger)
# can be the projection source for an over/under product: a miscalibrated spread yields
# wrong tail probabilities even at a perfect mean.

def predictive_pit(y, out: "PredictiveOutput") -> np.ndarray:
    """Probability integral transform F_pred(y) per game. ~Uniform(0,1) iff calibrated.
    U-shaped ⇒ overconfident (intervals too tight); dome ⇒ underconfident; sloped ⇒
    directional bias. Defined for distributional outputs only."""
    y = np.asarray(y, float)
    if out.kind == "normal":
        return _Phi((y - out.loc) / out.scale)
    if out.kind == "lognormal":
        return _Phi((np.log(np.maximum(y, 1e-9)) - out.loc) / out.scale)
    if out.kind == "samples":
        return (out.samples <= y[:, None]).mean(axis=1)
    raise ValueError(f"PIT undefined for kind {out.kind!r} (need normal/lognormal/samples)")


def predictive_interval(out: "PredictiveOutput", level: float = 0.80):
    """Central `level` predictive interval (lo, hi) per game."""
    alpha = (1.0 - level) / 2.0
    if out.kind in ("normal", "lognormal"):
        try:
            from scipy.stats import norm
            z = float(norm.ppf(1.0 - alpha))
        except Exception:  # pragma: no cover
            z = {0.80: 1.2815515594, 0.90: 1.6448536269, 0.95: 1.9599639845}.get(round(level, 2), 1.2815515594)
        if out.kind == "normal":
            return out.loc - z * out.scale, out.loc + z * out.scale
        return np.exp(out.loc - z * out.scale), np.exp(out.loc + z * out.scale)
    if out.kind == "samples":
        return (np.quantile(out.samples, alpha, axis=1),
                np.quantile(out.samples, 1.0 - alpha, axis=1))
    raise ValueError(f"interval undefined for kind {out.kind!r}")


def calibration_report(y, out: "PredictiveOutput", *, level: float = 0.80) -> dict:
    """Honesty of a predictive DISTRIBUTION vs realized `y`. Returns:
      coverage      — empirical fraction of y inside the central `level` PI (target≈level)
      coverage_gap  — coverage − level (negative ⇒ overconfident / intervals too tight)
      pit_ks        — KS distance of the PIT to Uniform(0,1) (lower = better calibrated)
      pit_hist      — 10-bin PIT counts (eyeball the shape)
      nll_mean      — mean predictive NLL (proper; rewards calibration)
      crps_mean     — mean CRPS (proper; distribution-free)
      mean_pred / mean_actual / bias — directional check (bias = pred − actual)
    """
    y = np.asarray(y, float)
    lo, hi = predictive_interval(out, level)
    coverage = float(np.mean((y >= lo) & (y <= hi)))
    pit = predictive_pit(y, out)
    pit_sorted = np.sort(pit)
    ecdf = np.arange(1, len(pit_sorted) + 1) / len(pit_sorted)
    pit_ks = float(np.max(np.abs(ecdf - pit_sorted))) if len(pit_sorted) else float("nan")
    pit_hist = [int(c) for c in np.histogram(pit, bins=10, range=(0.0, 1.0))[0]]
    try:
        nll_mean = float(np.mean(out.score_to_truth(y, "nll")))
    except Exception:
        nll_mean = float("nan")
    crps_mean = float(np.mean(out.score_to_truth(y, "crps")))
    mean_pred = float(np.mean(out.mean))
    mean_actual = float(np.mean(y))
    return {
        "n": int(len(y)), "level": level, "coverage": coverage,
        "coverage_gap": coverage - level, "pit_ks": pit_ks, "pit_hist": pit_hist,
        "nll_mean": nll_mean, "crps_mean": crps_mean,
        "mean_pred": mean_pred, "mean_actual": mean_actual, "bias": mean_pred - mean_actual,
    }


@dataclass
class SeasonDelta:
    season: int
    n: int
    champion: float
    challenger: float
    delta: float          # challenger - champion  (<0 = challenger better)
    complete: bool
    regressed: bool       # delta > tolerance on a COMPLETED season


@dataclass
class PromotionVerdict:
    decision: str                       # "PROMOTE" | "HOLD"
    metric: str
    tolerance: float
    overall_delta: float                # pooled per-game mean (challenger - champion), completed seasons
    boot_ci: tuple[float, float]        # paired bootstrap CI of overall_delta
    effect_size_pass: bool
    significant: bool
    consistency_pass: bool
    current_season: SeasonDelta | None
    per_season: list[SeasonDelta] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    # Hysteresis bookkeeping the caller threads across evals:
    single_eval_pass: bool = False      # would this eval ALONE clear criteria 2-4?
    override_applied: bool = False      # promoted via a recorded correctness override

    def __str__(self) -> str:  # pragma: no cover - display helper
        lines = [f"PROMOTION GATE → {self.decision}   (metric={self.metric}, tol={self.tolerance})"]
        for s in self.per_season:
            tag = "current/partial" if not s.complete else ("REGRESSED" if s.regressed else "ok")
            lines.append(f"  {s.season} (n={s.n:4d}): champ={s.champion:.4f} "
                         f"chal={s.challenger:.4f}  Δ={s.delta:+.4f}  [{tag}]")
        lines.append(f"  pooled Δ (completed)={self.overall_delta:+.4f}  "
                     f"95% CI=[{self.boot_ci[0]:+.4f}, {self.boot_ci[1]:+.4f}]")
        lines.append(f"  effect_size={self.effect_size_pass}  significant={self.significant}  "
                     f"consistency={self.consistency_pass}")
        for r in self.reasons:
            lines.append(f"  • {r}")
        return "\n".join(lines)


def evaluate_promotion(
    season: np.ndarray,
    champion_score: np.ndarray,
    challenger_score: np.ndarray,
    *,
    metric: str,
    completed_seasons: set[int] | None = None,
    current_season: int | None = None,
    tolerance: float | None = None,
    min_current_games: int = MIN_CURRENT_SEASON_GAMES,
    require_significant: bool = True,
    correctness_override: str | None = None,
    n_boot: int = 2000,
    seed: int = 42,
) -> PromotionVerdict:
    """Decide PROMOTE vs HOLD from per-GAME scores (lower = better) of the champion and
    challenger on the SAME games, tagged by season.

    Parameters
    ----------
    season, champion_score, challenger_score : 1-D arrays, aligned per game.
    metric : key into NOISE_FLOOR ('mae'|'rmse'|'brier'|'crps'|'nll') — sets the default
        noise-floor tolerance and labels the verdict.
    completed_seasons : seasons treated as full/held-out for the gate. If None, every
        season except `current_season` is treated as complete.
    current_season : the in-progress partial season (corroboration only). If None,
        inferred as max(season) when it is excluded from completed_seasons.
    tolerance : noise-floor effect size; defaults to NOISE_FLOOR[metric].
    require_significant : require the paired bootstrap CI upper bound < 0.

    Returns a PromotionVerdict. NOTE: this is ONE evaluation; HYSTERESIS (criterion 6)
    is the caller's job — promote only after `MIN_CONSECUTIVE_PASSES` verdicts with
    decision == 'PROMOTE' (or single_eval_pass) and a respected re-eval interval.
    """
    season = np.asarray(season)
    champ = np.asarray(champion_score, float)
    chal = np.asarray(challenger_score, float)
    if not (len(season) == len(champ) == len(chal)):
        raise ValueError("season / champion_score / challenger_score must be equal length")
    tol = float(NOISE_FLOOR.get(metric, 0.0) if tolerance is None else tolerance)

    all_seasons = sorted({int(s) for s in np.unique(season)})
    if current_season is None and completed_seasons is None:
        # Infer: the latest season is the in-progress one.
        current_season = all_seasons[-1] if all_seasons else None
    if completed_seasons is None:
        completed_seasons = {s for s in all_seasons if s != current_season}
    completed_seasons = {int(s) for s in completed_seasons}

    diff = chal - champ  # <0 ⇒ challenger better
    per_season: list[SeasonDelta] = []
    cur: SeasonDelta | None = None
    for s in all_seasons:
        m = season == s
        n = int(m.sum())
        c_mean, h_mean = float(champ[m].mean()), float(chal[m].mean())
        d = h_mean - c_mean
        complete = s in completed_seasons
        regressed = bool(complete and d > tol)
        sd = SeasonDelta(season=s, n=n, champion=c_mean, challenger=h_mean,
                         delta=d, complete=complete, regressed=regressed)
        per_season.append(sd)
        if s == current_season:
            cur = sd

    comp_mask = np.isin(season, list(completed_seasons))
    reasons: list[str] = []
    if comp_mask.sum() == 0:
        return PromotionVerdict(
            decision="HOLD", metric=metric, tolerance=tol, overall_delta=float("nan"),
            boot_ci=(float("nan"), float("nan")), effect_size_pass=False, significant=False,
            consistency_pass=False, current_season=cur, per_season=per_season,
            reasons=["No completed held-out seasons to judge on (need ≥1 full prior season)."],
        )

    d_comp = diff[comp_mask]
    s_comp = season[comp_mask]
    overall_delta = float(d_comp.mean())

    # Season-stratified PAIRED bootstrap of the pooled mean diff (preserves season balance).
    rng = np.random.default_rng(seed)
    seasons_in_comp = sorted({int(s) for s in np.unique(s_comp)})
    idx_by_season = {s: np.where(s_comp == s)[0] for s in seasons_in_comp}
    boots = np.empty(n_boot)
    for b in range(n_boot):
        parts = [d_comp[rng.choice(idx_by_season[s], size=len(idx_by_season[s]), replace=True)]
                 for s in seasons_in_comp]
        boots[b] = np.concatenate(parts).mean()
    lo, hi = float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))

    effect_size_pass = overall_delta <= -tol
    significant = hi < 0.0
    regressed_seasons = [sd.season for sd in per_season if sd.regressed]
    consistency_pass = len(regressed_seasons) == 0

    if effect_size_pass:
        reasons.append(f"Pooled improvement {overall_delta:+.4f} clears the {tol} noise floor.")
    else:
        reasons.append(f"Pooled improvement {overall_delta:+.4f} does NOT clear the {tol} noise floor.")
    if require_significant:
        reasons.append(f"Paired bootstrap 95% CI upper bound {hi:+.4f} "
                       f"{'< 0 (significant)' if significant else '≥ 0 (not significant)'}.")
    if consistency_pass:
        reasons.append("No completed season regresses beyond tolerance (cross-season consistent).")
    else:
        reasons.append(f"Regresses beyond tolerance on completed season(s) {regressed_seasons} "
                       f"→ overfitting risk; HOLD.")
    if cur is not None:
        if cur.n < min_current_games:
            reasons.append(f"Current season {cur.season} (n={cur.n}) below {min_current_games} games "
                           f"— not yet informative; corroboration only.")
        elif cur.delta > tol:
            reasons.append(f"⚠ Current season {cur.season} REGRESSES ({cur.delta:+.4f}) — does not block "
                           f"(corroboration only), but watch for a regime shift before promoting.")
        else:
            reasons.append(f"Current season {cur.season} corroborates ({cur.delta:+.4f}).")

    single_eval_pass = bool(effect_size_pass and consistency_pass
                            and (significant or not require_significant))
    decision = "PROMOTE" if single_eval_pass else "HOLD"
    if decision == "PROMOTE":
        reasons.append(f"Single-eval criteria PASS → PROMOTE candidate. "
                       f"Confirm hysteresis (≥{MIN_CONSECUTIVE_PASSES} consecutive passes) before deploy.")

    # ── Correctness override ─────────────────────────────────────────────────
    # Market-/identifier-leakage is a CORRECTNESS violation (architecture Principle 3),
    # not an accuracy tradeoff — a champion that leaks is NON-COMPLIANT and must be
    # replaced by a compliant challenger regardless of an accuracy *win*. The override
    # WAIVES the effect-size + significance bars BUT NOT the no-regression bar
    # (criterion 4): a hygiene fix must not ship an accuracy regression. Always RECORD
    # the override + the violation in the registry notes + the story doc.
    override_applied = False
    if correctness_override and not single_eval_pass:
        if consistency_pass:
            decision = "PROMOTE"
            override_applied = True
            reasons.append(
                f"⭐ CORRECTNESS OVERRIDE — {correctness_override}. PROMOTE despite no "
                f"significant accuracy gain: the fix is mandatory (compliance, not "
                f"accuracy) and the gate confirms accuracy NON-REGRESSION "
                f"(pooled Δ {overall_delta:+.4f}, no completed-season regression). "
                f"Effect-size/significance bars waived; record the override + violation.")
        else:
            reasons.append(
                f"Correctness override ({correctness_override}) REQUESTED but REFUSED: "
                f"challenger regresses completed season(s) {regressed_seasons} beyond "
                f"tolerance — a hygiene fix must not ship an accuracy regression.")

    return PromotionVerdict(
        decision=decision, metric=metric, tolerance=tol, overall_delta=overall_delta,
        boot_ci=(lo, hi), effect_size_pass=effect_size_pass, significant=significant,
        consistency_pass=consistency_pass, current_season=cur, per_season=per_season,
        reasons=reasons, single_eval_pass=single_eval_pass, override_applied=override_applied,
    )
