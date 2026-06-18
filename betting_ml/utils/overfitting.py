"""overfitting.py — Epic E1.4: the program's go-live gate.

Two numbers that turn "are we getting closer to something real?" from a feeling into a
measurement, both from Lopez de Prado's *Advances in Financial Machine Learning*:

  * `pbo_cscv()` — **Probability of Backtest Overfitting** via Combinatorially-Symmetric
    Cross-Validation (AFML §11.4). Given a per-configuration performance matrix (you already
    have many configs — every challenger, every ablation, every CV sub-period), it estimates
    P(the in-sample-best config underperforms the OOS median). High PBO ⇒ your "best" model
    is selection noise.
  * `deflated_sharpe()` — **Deflated Sharpe Ratio** (AFML §14). Deflates an observed Sharpe
    by the number of trials run and the non-normality of returns, then reports the
    probability the true Sharpe beats the benchmark. The honest bar for any BETTING strategy
    (E2 derivatives, E3/E4 selective bets) whose backtest Sharpe was cherry-picked from many.

GATES (encode here; these gate E2–E4 — see implementation_guide.md §3 E1.4):
  - ship-to-shadow : PBO < 0.5
  - shadow-to-live : PBO < 0.2  AND  DSR > 0 at 95% (i.e. P(SR>benchmark) ≥ 0.95)  AND the
    existing live-CLV gate (enforced outside this module).
No E2–E4 strategy goes live without a PBO and a DSR on record (`overfitting_dashboard.md`).

COST (§6): both are embarrassingly parallel over folds/resamples and run as a periodic
EC2/local batch job on the S3-Parquet training matrix — never repeated Snowflake scans.
`pbo_cscv` caps CSCV combinations (`max_combos`) and `deflated_sharpe` is closed-form, so
both bound their own compute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from math import e as _E

import numpy as np

try:
    from scipy.stats import norm as _norm

    def _Phi(z):
        return float(_norm.cdf(z))

    def _Phi_inv(p):
        return float(_norm.ppf(p))
except Exception:  # pragma: no cover
    from math import erf, sqrt

    def _Phi(z):
        return 0.5 * (1.0 + erf(z / sqrt(2.0)))

    def _Phi_inv(p):  # crude bisection fallback
        lo, hi = -10.0, 10.0
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            if _Phi(mid) < p:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)


_EULER_GAMMA = 0.5772156649015329

# ── Gate thresholds (the program's go-live constants) ────────────────────────
PBO_SHIP_TO_SHADOW = 0.5     # PBO must be < this to ship a strategy to SHADOW
PBO_SHADOW_TO_LIVE = 0.2     # PBO must be < this to graduate SHADOW → LIVE
DSR_CONFIDENCE = 0.95        # "DSR > 0 at 95%": P(SR > benchmark) must be ≥ this to go live


@dataclass
class PBOResult:
    pbo: float                       # P(IS-best underperforms OOS median)
    n_combos: int                    # CSCV combinations actually evaluated
    n_configs: int
    n_splits: int
    logits: list[float] = field(default_factory=list)        # per-combo logit λ_c
    oos_relative_ranks: list[float] = field(default_factory=list)  # ω_c ∈ (0,1)
    median_oos_rank_of_is_best: float = float("nan")
    ships_to_shadow: bool = False    # PBO < PBO_SHIP_TO_SHADOW
    clears_live_pbo: bool = False    # PBO < PBO_SHADOW_TO_LIVE

    def __str__(self) -> str:  # pragma: no cover - display helper
        return (f"PBO={self.pbo:.3f} over {self.n_combos} CSCV combos "
                f"({self.n_configs} configs, S={self.n_splits})  "
                f"ship→shadow(<{PBO_SHIP_TO_SHADOW})={self.ships_to_shadow}  "
                f"shadow→live(<{PBO_SHADOW_TO_LIVE})={self.clears_live_pbo}")


def pbo_cscv(
    perf: np.ndarray,
    *,
    higher_is_better: bool = True,
    n_splits: int = 16,
    max_combos: int = 1000,
    seed: int = 42,
) -> PBOResult:
    """Probability of Backtest Overfitting via CSCV (AFML §11.4).

    Parameters
    ----------
    perf : (T, N) array — T performance observations (CV sub-periods / fold-slices / time
        buckets) × N candidate configurations. Entry = that config's performance in that
        slice (e.g. negative MAE, −CRPS, Sharpe, ROI). Make sure higher is better OR set
        `higher_is_better=False` (it is negated internally).
    n_splits : S, the number of disjoint row partitions (must be even; clamped to T). CSCV
        forms every way of choosing S/2 partitions as in-sample and the rest as OOS.
    max_combos : cap on C(S, S/2). When the full set exceeds it, a RANDOM subset of combos
        is evaluated (bounds cost per §6); reported as `n_combos`.

    Method (per combination c): pick S/2 partitions as IS, the complement as OOS. n*(c) =
    argmax of mean IS performance. ω_c = relative rank of n*(c)'s mean OOS performance among
    all configs (1 = best OOS, →0 = worst). λ_c = logit(ω_c). PBO = fraction of combos with
    λ_c ≤ 0, i.e. the IS-best config landed in the WORSE OOS half. PBO → 0.5 means the
    selection carries no OOS information (pure overfit); PBO → 0 means IS skill persists OOS.
    """
    M = np.asarray(perf, float)
    if M.ndim != 2:
        raise ValueError("perf must be a 2-D (T, N) matrix of per-config performances")
    if not higher_is_better:
        M = -M
    T, N = M.shape
    if N < 2:
        raise ValueError("PBO needs ≥2 configurations to compare")
    S = min(int(n_splits), T)
    if S % 2 == 1:
        S -= 1
    if S < 2:
        raise ValueError(f"need ≥2 row partitions for CSCV; got T={T}")

    # Disjoint, contiguous-by-position partitions (rows are time-ordered slices).
    bounds = np.array_split(np.arange(T), S)
    parts = [b for b in bounds if len(b) > 0]
    S = len(parts)
    half = S // 2

    all_combos = list(combinations(range(S), half))
    rng = np.random.default_rng(seed)
    if len(all_combos) > max_combos:
        pick = rng.choice(len(all_combos), size=max_combos, replace=False)
        combos = [all_combos[i] for i in pick]
    else:
        combos = all_combos

    logits: list[float] = []
    omegas: list[float] = []
    ranks_of_best: list[float] = []
    n_below = 0
    for is_parts in combos:
        is_set = set(is_parts)
        is_rows = np.concatenate([parts[i] for i in is_parts])
        oos_rows = np.concatenate([parts[i] for i in range(S) if i not in is_set])
        is_mean = M[is_rows].mean(axis=0)
        oos_mean = M[oos_rows].mean(axis=0)
        n_star = int(np.argmax(is_mean))
        # relative OOS rank of the IS-best config (average rank handles ties)
        order = np.argsort(oos_mean)
        rank = np.empty(N)
        rank[order] = np.arange(1, N + 1)
        # break ties to the mean rank so ω is symmetric
        for v in np.unique(oos_mean):
            m = oos_mean == v
            rank[m] = rank[m].mean()
        omega = rank[n_star] / (N + 1)       # ∈ (0,1); 1≈best OOS
        omega = min(max(omega, 1e-6), 1 - 1e-6)
        ranks_of_best.append(rank[n_star])
        omegas.append(omega)
        lam = np.log(omega / (1 - omega))
        logits.append(float(lam))
        if lam <= 0:
            n_below += 1

    pbo = n_below / len(combos)
    return PBOResult(
        pbo=float(pbo), n_combos=len(combos), n_configs=N, n_splits=S,
        logits=logits, oos_relative_ranks=omegas,
        median_oos_rank_of_is_best=float(np.median(ranks_of_best)),
        ships_to_shadow=bool(pbo < PBO_SHIP_TO_SHADOW),
        clears_live_pbo=bool(pbo < PBO_SHADOW_TO_LIVE),
    )


@dataclass
class DSRResult:
    dsr: float                  # P(true SR > benchmark) after deflation ∈ [0,1]
    observed_sr: float          # per-period Sharpe of the strategy
    sr0: float                  # deflated benchmark (expected max SR under n_trials)
    n_trials: int
    n_obs: int
    skew: float
    kurtosis: float             # NON-excess (normal = 3)
    var_trials_sr: float
    passes_live: bool = False   # dsr ≥ DSR_CONFIDENCE  ("DSR > 0 at 95%")

    def __str__(self) -> str:  # pragma: no cover
        return (f"DSR={self.dsr:.3f}  SR={self.observed_sr:.3f} vs deflated SR0={self.sr0:.3f}  "
                f"(trials={self.n_trials}, n={self.n_obs})  live(≥{DSR_CONFIDENCE})={self.passes_live}")


def _sharpe(returns: np.ndarray, benchmark: float = 0.0) -> float:
    r = np.asarray(returns, float)
    sd = r.std(ddof=1)
    return float((r.mean() - benchmark) / sd) if sd > 0 else 0.0


def deflated_sharpe(
    returns,
    *,
    n_trials: int,
    benchmark_sr: float = 0.0,
    trial_sharpes=None,
    var_trials_sr: float | None = None,
) -> DSRResult:
    """Deflated Sharpe Ratio (AFML §14).

    Parameters
    ----------
    returns : 1-D per-period return series of the CANDIDATE strategy (the one bet series —
        e.g. per-bet de-vig PnL units). Sharpe + skew/kurtosis are computed from it.
    n_trials : number of independent strategy configurations tried to FIND this one (the
        multiple-testing count). The whole point: a Sharpe selected from many trials is
        inflated; DSR deflates by an estimate of the expected MAXIMUM Sharpe under that many
        trials.
    benchmark_sr : the SR to beat (default 0 — "is there any edge at all?").
    trial_sharpes : optional per-trial Sharpe ratios; their variance estimates the cross-
        trial SR dispersion `V` used for the expected-max benchmark. If absent, pass
        `var_trials_sr` directly; if neither is given, `V` falls back to Var(SR)≈1/n_obs
        (the asymptotic null variance of a Sharpe estimate).

    Returns the probability the strategy's TRUE Sharpe exceeds the deflated benchmark `SR0`
    (the expected max under `n_trials`), adjusting the test statistic's variance for skew
    and (non-excess) kurtosis per AFML §14. `passes_live` = DSR ≥ 0.95.
    """
    r = np.asarray(returns, float)
    n_obs = len(r)
    if n_obs < 3:
        raise ValueError("deflated_sharpe needs ≥3 return observations")
    sr = _sharpe(r, benchmark=0.0)
    # moments of the return series (skew γ3, NON-excess kurtosis γ4)
    rc = r - r.mean()
    sd = r.std(ddof=0)
    skew = float((rc ** 3).mean() / sd ** 3) if sd > 0 else 0.0
    kurt = float((rc ** 4).mean() / sd ** 4) if sd > 0 else 3.0

    if trial_sharpes is not None and len(trial_sharpes) > 1:
        V = float(np.var(np.asarray(trial_sharpes, float), ddof=1))
    elif var_trials_sr is not None:
        V = float(var_trials_sr)
    else:
        V = 1.0 / n_obs   # asymptotic null variance of an SR estimate

    V = max(V, 1e-12)
    N = max(int(n_trials), 1)
    # expected maximum of N standard normals (AFML eq. 14): √V · [(1−γ)Φ⁻¹(1−1/N) + γΦ⁻¹(1−1/(Ne))]
    if N == 1:
        sr0 = benchmark_sr
    else:
        z = (1 - _EULER_GAMMA) * _Phi_inv(1 - 1.0 / N) + _EULER_GAMMA * _Phi_inv(1 - 1.0 / (N * _E))
        sr0 = benchmark_sr + np.sqrt(V) * z

    # DSR test statistic (AFML §14): variance of the SR estimator corrected for non-normality
    denom = np.sqrt(max(1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2, 1e-12))
    stat = (sr - sr0) * np.sqrt(max(n_obs - 1, 1)) / denom
    dsr = _Phi(stat)
    return DSRResult(
        dsr=float(dsr), observed_sr=float(sr), sr0=float(sr0), n_trials=N, n_obs=n_obs,
        skew=skew, kurtosis=kurt, var_trials_sr=V,
        passes_live=bool(dsr >= DSR_CONFIDENCE),
    )


# ── Standing report: ablation_results/overfitting_dashboard.md ───────────────

def render_overfitting_dashboard(
    entries: list[dict], *, title: str = "Overfitting Dashboard (Epic E1.4)"
) -> str:
    """Render the standing `overfitting_dashboard.md` from a list of strategy entries.

    Each entry: {'strategy', 'stage' ('proposed'/'shadow'/'live'), optional 'pbo'
    (PBOResult or float), optional 'dsr' (DSRResult or float), optional 'live_clv' (bool),
    optional 'notes'}. The verdict column applies the gates: ship-to-shadow needs PBO<0.5;
    shadow-to-live needs PBO<0.2 AND DSR≥0.95 AND live-CLV.
    """
    lines = [f"# {title}", "",
             "Regenerated whenever a strategy is proposed (E1.4). Gate thresholds: "
             f"**ship→shadow PBO < {PBO_SHIP_TO_SHADOW}**; "
             f"**shadow→live PBO < {PBO_SHADOW_TO_LIVE} AND DSR ≥ {DSR_CONFIDENCE} AND live-CLV.**",
             "",
             "| Strategy | Stage | PBO | DSR | live-CLV | Verdict | Notes |",
             "|---|---|---|---|---|---|---|"]
    for ent in entries:
        pbo_obj = ent.get("pbo")
        pbo = pbo_obj.pbo if isinstance(pbo_obj, PBOResult) else pbo_obj
        dsr_obj = ent.get("dsr")
        dsr = dsr_obj.dsr if isinstance(dsr_obj, DSRResult) else dsr_obj
        live_clv = ent.get("live_clv")
        pbo_s = "—" if pbo is None else f"{pbo:.3f}"
        dsr_s = "—" if dsr is None else f"{dsr:.3f}"
        clv_s = "—" if live_clv is None else ("yes" if live_clv else "no")
        verdict = _dashboard_verdict(pbo, dsr, live_clv)
        lines.append(f"| {ent.get('strategy','?')} | {ent.get('stage','proposed')} | "
                     f"{pbo_s} | {dsr_s} | {clv_s} | {verdict} | {ent.get('notes','')} |")
    lines += ["",
              "_PBO = P(in-sample-best config underperforms the OOS median) via CSCV "
              "(AFML §11.4). DSR = P(true Sharpe > deflated benchmark) accounting for "
              "trial count + non-normality (AFML §14)._"]
    return "\n".join(lines)


def _dashboard_verdict(pbo, dsr, live_clv) -> str:
    if pbo is None:
        return "⛔ NO PBO ON RECORD"
    if pbo >= PBO_SHIP_TO_SHADOW:
        return f"⛔ HOLD (PBO≥{PBO_SHIP_TO_SHADOW})"
    live_ok = (pbo < PBO_SHADOW_TO_LIVE) and (dsr is not None and dsr >= DSR_CONFIDENCE) and bool(live_clv)
    if live_ok:
        return "✅ LIVE-eligible"
    return "🟡 SHADOW-eligible"
