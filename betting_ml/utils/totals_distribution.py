"""totals_distribution.py — Edge Program Story E2.3 (Convolution → predictive distributions).

WHY THIS EXISTS
---------------
E2.1 gives a per-SIDE Negative-Binomial marginal over runs scored (home, away). E2.2 then
fit the dependence between the two and found it is **negligible** — residual Gaussian-copula
ρ = −0.0035, home/away runs are essentially INDEPENDENT (see
quant_sports_intel_models/.../ablation_results/e2_2_copula_decision.md). So E2.3 convolves the
two marginals **independently** (ρ=0) into honest predictive distributions for the **total**
(sum), the **run-diff** (difference — a distributional H2H input), and each **team total**
(the marginals themselves). No copula coupling — forcing one would be coupling the data does
not support.

THE LOAD-BEARING FIX (the actual point of E2.3): DISPERSION CALIBRATION
----------------------------------------------------------------------
E2.2 also pinned the real defect behind the Story-29.1 totals variance deficiency: it is NOT
the dependence, it is the **marginal dispersion**. E2.1 fits the NegBin dispersion `r` on
TRAIN-fit means (the LightGBM mean is mildly optimistic in-sample → train residuals are too
tight → `r` biased HIGH ≈ 8.5 → the convolved total is ~24% too narrow). The dispersion
diagnostic showed an `r` fit on HELD-OUT residuals (≈ 3.71) reproduces var(total) and that the
held-out `r` is STABLE across folds (CV 0.054) — E2.1's apparent "r drifts 33→8" is an
estimation artifact of fitting `r` on optimistic train means, NOT temporal non-stationarity.

So E2.3's first task is to calibrate a **single stable per-side `r ≈ 3.71` on held-out
residuals**, leakage-safe (an expanding window of strictly-prior seasons' OOS residuals — the
deployed estimate for season T sees only seasons < T). This module is the convolution +
calibration machinery; the orchestration (re-deriving the E2.1 OOS marginals, the PIT/calib
gate, the served artifact) lives in scripts/totals_generative/fit_totals_distribution.py.

Pure NumPy/SciPy — no Snowflake, no model — so it is fully unit-tested. Reuses the E2.2
`sample_gaussian_copula_negbin` sampler with ρ=0 (independent convolution is its ρ=0 case).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import gammaln

from betting_ml.utils.copula import sample_gaussian_copula_negbin

# Mirror the E2.1 / copula per-side floor so all three layers agree on mu > 0.
_MIN_MU = 0.30
# Default quantile grid P05…P95 (every 5th pct) — stored per game, not raw samples (§6 cost).
DEFAULT_QUANTILES: tuple[float, ...] = tuple(round(q, 2) for q in np.arange(0.05, 0.96, 0.05))
# Calibration gate bands (the E2.3 AC: PIT-flat / calib_80 ≥ 0.80 for the total).
CALIB_80_GATE = 0.80
_PIT_MEAN_TOL = 0.02            # |mean(PIT) − 0.5|
_PIT_DECILE_TOL = 0.025         # max |decile-frequency − 0.10| (a practical flatness band; KS
                                # is over-sensitive at n≈20k — a 0.3% miscalibration tanks its p)


# ---------------------------------------------------------------------------
# Dispersion (NegBin r) on held-out residuals — the E2.3 calibration lever
# ---------------------------------------------------------------------------

def _negbin_nll(y: np.ndarray, mu: np.ndarray, r: float) -> float:
    """Mean NegBin(mu, r) NLL. Matches train_perside_negbin.negbin_nll (var = mu + mu²/r)."""
    mu = np.clip(mu, _MIN_MU, None)
    p = r / (r + mu)
    ll = (
        gammaln(y + r) - gammaln(r) - gammaln(y + 1.0)
        + r * np.log(p) + y * np.log(1.0 - p + 1e-12)
    )
    return float(-np.mean(ll))


def fit_negbin_dispersion(y: np.ndarray, mu: np.ndarray) -> float:
    """MLE of the NegBin dispersion `r` given observations `y` and predicted means `mu`.

    Identical objective to train_perside_negbin.fit_negbin_r — re-implemented here so this
    utility stays Snowflake/model-free (the trainer module pulls in the data loader). When `y`
    and `mu` are HELD-OUT (eval-fold) residuals this recovers the OOS-calibrated dispersion that
    fixes the totals variance deficiency; on TRAIN-fit residuals it reproduces E2.1's biased r.
    """
    mu = np.clip(np.asarray(mu, dtype=float), _MIN_MU, None)
    y = np.asarray(y, dtype=float)
    res = minimize_scalar(
        lambda log_r: _negbin_nll(y, mu, float(np.exp(log_r))),
        bounds=(np.log(0.1), np.log(500.0)), method="bounded",
    )
    return float(np.exp(res.x))


def calibrate_dispersion_expanding(
    seasons: np.ndarray, mu: np.ndarray, y: np.ndarray,
) -> dict[int, float]:
    """Leakage-safe per-season dispersion: for each season T, fit `r` on the **strictly prior**
    seasons' held-out residuals (an expanding walk-forward window — the deployed estimate for
    season T sees only seasons < T). Returns {season: r_used}; the earliest season has no prior
    OOS residuals → omitted from the map (the caller treats it as the un-gated seed).

    `seasons`, `mu`, `y` are flat per-(game, side) arrays of the OOS marginals (home & away
    stacked). E2.2 found the held-out `r` is stable across folds, so this expanding estimate is
    ≈ 3.71 throughout — confirming a single global served `r` is safe (we do NOT condition on
    period; the apparent train-fit drift is an estimation artifact).
    """
    seasons = np.asarray(seasons)
    order = sorted(set(int(s) for s in seasons))
    out: dict[int, float] = {}
    for t in order:
        prior = seasons < t
        if prior.sum() < 50:                 # too few strictly-prior residuals to trust an MLE
            continue
        out[t] = round(fit_negbin_dispersion(y[prior], mu[prior]), 4)
    return out


# ---------------------------------------------------------------------------
# Independent convolution → total / run-diff / team-total samples
# ---------------------------------------------------------------------------

def draw_independent_samples(
    mu_home: np.ndarray,
    mu_away: np.ndarray,
    r_home: np.ndarray | float,
    rng: np.random.Generator,
    *,
    r_away: np.ndarray | float | None = None,
    n_draws: int = 10_000,
) -> tuple[np.ndarray, np.ndarray]:
    """Draw `n_draws` INDEPENDENT (home, away) run counts per game (E2.2 ρ≈0 → ρ=0 here).

    Thin wrapper over the E2.2 `sample_gaussian_copula_negbin` with ρ=0 — the independent
    convolution is exactly its ρ=0 special case, so we reuse the vectorised, tested sampler
    rather than fork it. `r_home` is the calibrated home-side dispersion; `r_away` defaults to
    `r_home` (shared, the E2.2 convention) but may be set independently — the home/away PIT
    diagnostic showed the home side wants a slightly larger `r`, and the run-diff calibration
    is sensitive to the asymmetry the sum is blind to. Returns two (n_games, n_draws) arrays.
    Vectorised; cap `n_draws` at ~10k/game per the §6 cost guard.
    """
    if r_away is None:
        r_away = r_home
    return sample_gaussian_copula_negbin(
        mu_home, r_home, mu_away, r_away, 0.0, rng, n_draws=n_draws,
    )


def derive_distributions(y_home: np.ndarray, y_away: np.ndarray) -> dict[str, np.ndarray]:
    """Map joint (home, away) draws → the four served predictive distributions.

    total    = home + away      (full-game total runs)
    run_diff = home − away       (home margin; a distributional H2H input — >0 ⇔ home wins)
    home_total / away_total = the marginals themselves (team totals).
    Each value is an (n_games, n_draws) sample array.
    """
    return {
        "total": y_home + y_away,
        "run_diff": y_home - y_away,
        "home_total": y_home,
        "away_total": y_away,
    }


# ---------------------------------------------------------------------------
# Quantile grid + p_over (the stored served contract — params + grid, NOT samples)
# ---------------------------------------------------------------------------

def quantile_grid(
    samples: np.ndarray, quantiles: tuple[float, ...] = DEFAULT_QUANTILES,
) -> np.ndarray:
    """Per-game quantiles of a sample array → (n_games, n_quantiles). The stored grid (§6:
    persist params + this grid, never the raw samples). `samples` is (n_games, n_draws)."""
    return np.quantile(samples, np.asarray(quantiles), axis=1).T


def prob_over(samples: np.ndarray, lines: np.ndarray | list[float]) -> dict[float, np.ndarray]:
    """P(total > line) per game for each betting line → {line: (n_games,) array}.

    Over a totals line wins strictly above it; for a half-line (8.5) that is unambiguous, for an
    integer line (9) the equal-mass is the push (returned via `prob_push`). Use on the `total`
    (over/under), the team totals, or `run_diff` (a 0-line gives P(home wins) the distributional
    way). `samples` is (n_games, n_draws)."""
    return {float(ln): (samples > ln).mean(axis=1) for ln in lines}


def prob_push(samples: np.ndarray, lines: np.ndarray | list[float]) -> dict[float, np.ndarray]:
    """P(total == line) per game (non-zero only at integer lines) → {line: (n_games,) array}."""
    return {float(ln): (samples == ln).mean(axis=1) for ln in lines}


# ---------------------------------------------------------------------------
# Calibration diagnostics — the E2.3 gate (PIT-flat / calib_80 ≥ 0.80)
# ---------------------------------------------------------------------------

def interval_coverage(
    y_obs: np.ndarray, samples: np.ndarray, lo: float = 0.10, hi: float = 0.90,
) -> float:
    """Fraction of realised values inside the per-game [Q_lo, Q_hi] predictive interval.

    calib_80 := coverage at (0.10, 0.90). The E2.3 AC for the total is calib_80 ≥ 0.80; a
    well-calibrated 80% interval covers ≈ 80% of outcomes. `samples` is (n_games, n_draws),
    `y_obs` is (n_games,)."""
    q_lo = np.quantile(samples, lo, axis=1)
    q_hi = np.quantile(samples, hi, axis=1)
    return float(np.mean((y_obs >= q_lo) & (y_obs <= q_hi)))


def randomized_pit(
    y_obs: np.ndarray, samples: np.ndarray, rng: np.random.Generator,
) -> np.ndarray:
    """Randomised PIT of each realised count under its empirical predictive sample CDF.

    For a DISCRETE predictive a plain F(y) lands on CDF step-tops (not uniform), so we spread the
    mass: u = F(y⁻) + V·(F(y) − F(y⁻)), V ~ U(0,1), with F(y⁻)=P(sample<y), F(y)=P(sample≤y)
    from the draws (the same distributional transform E2.2 uses, here against the sampled
    predictive). Under correct calibration u ~ Uniform(0,1); `pit_flatness` tests that.
    """
    y_obs = np.asarray(y_obs, dtype=float)[:, None]
    f_lo = (samples < y_obs).mean(axis=1)
    f_hi = (samples <= y_obs).mean(axis=1)
    v = rng.random(size=f_lo.shape)
    return f_lo + v * (f_hi - f_lo)


def pit_flatness(u: np.ndarray) -> dict[str, Any]:
    """Flatness summary of a PIT sample: decile occupancy + a pass/fail flag.

    `is_flat` requires |mean − 0.5| ≤ tol AND every decile within tol of 0.10. (A practical band:
    a KS test against Uniform is over-sensitive at n≈20k — a 0.3% miscalibration tanks its
    p-value — so we gate on decile deviations, the calibration error that actually matters.)
    """
    u = np.asarray(u, dtype=float)
    counts, _ = np.histogram(u, bins=10, range=(0.0, 1.0))
    freqs = counts / counts.sum()
    max_dev = float(np.max(np.abs(freqs - 0.10)))
    mean_dev = float(abs(u.mean() - 0.5))
    return {
        "mean": round(float(u.mean()), 4),
        "std": round(float(u.std()), 4),
        "decile_freqs": [round(float(f), 4) for f in freqs],
        "max_decile_dev": round(max_dev, 4),
        "mean_dev_from_half": round(mean_dev, 4),
        "is_flat": bool(mean_dev <= _PIT_MEAN_TOL and max_dev <= _PIT_DECILE_TOL),
    }


# ---------------------------------------------------------------------------
# Served / calibration params (consumed by E2.5 backfill + E2.7 UX)
# ---------------------------------------------------------------------------

@dataclass
class TotalsDistributionParams:
    """The fitted E2.3 calibration layer + served-contract spec.

    `dispersion_r` is the pooled stable per-side held-out-calibrated NegBin `r` (≈ 3.71) used to
    widen the E2.1 marginals to honest dispersion before convolution. `dispersion_r_home` /
    `dispersion_r_away` are the per-SIDE calibrated dispersions actually served (the home side
    wants a slightly larger `r`); they default to `dispersion_r` (shared) when unset. `rho` is
    pinned at 0.0 (E2.2: home/away independent). `quantile_levels` is the stored P05…P95 grid;
    `n_draws` the capped per-game draw count. JSON-roundtrippable (no model state — the μ come
    from the E2.1 artifact at score time)."""
    dispersion_r: float
    dispersion_r_home: float | None = None
    dispersion_r_away: float | None = None
    rho: float = 0.0
    n_draws: int = 10_000
    quantile_levels: tuple[float, ...] = DEFAULT_QUANTILES
    r_calibration: str = "expanding-window held-out residuals (leakage-safe)"
    notes: str = ""
    version: str = "totals_distribution_v1"

    @property
    def r_home(self) -> float:
        """Served home-side dispersion (per-side if calibrated, else the pooled `dispersion_r`)."""
        return self.dispersion_r if self.dispersion_r_home is None else self.dispersion_r_home

    @property
    def r_away(self) -> float:
        """Served away-side dispersion (per-side if calibrated, else the pooled `dispersion_r`)."""
        return self.dispersion_r if self.dispersion_r_away is None else self.dispersion_r_away

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "dispersion_r": self.dispersion_r,
            "dispersion_r_home": self.dispersion_r_home,
            "dispersion_r_away": self.dispersion_r_away,
            "rho": self.rho,
            "n_draws": self.n_draws,
            "quantile_levels": list(self.quantile_levels),
            "r_calibration": self.r_calibration,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TotalsDistributionParams":
        return cls(
            dispersion_r=float(d["dispersion_r"]),
            dispersion_r_home=None if d.get("dispersion_r_home") is None else float(d["dispersion_r_home"]),
            dispersion_r_away=None if d.get("dispersion_r_away") is None else float(d["dispersion_r_away"]),
            rho=float(d.get("rho", 0.0)),
            n_draws=int(d.get("n_draws", 10_000)),
            quantile_levels=tuple(d.get("quantile_levels", DEFAULT_QUANTILES)),
            r_calibration=d.get("r_calibration", ""),
            notes=d.get("notes", ""),
            version=d.get("version", "totals_distribution_v1"),
        )
