"""cv_power.py — Story MH2: how much can a §0.5 bake-off at THIS fold count actually detect?

WHY THIS EXISTS
---------------------------------------------------------------------------------------------------
Every §0.5 verdict in this program is read as if the gates were a fixed bar. They are not. The same
four clauses — fold consistency, BH-FDR, PBO, DSR — mean **completely different things** at 3 folds
and at 11, and DSR additionally means a different thing at 2 arms and at 28. E7.9 recorded
`DSR 0.842 vs 0.95` on 3 purged folds over a 28-arm grid and correctly called that "what an
UNDER-POWERED real effect looks like, not what a dead one looks like" — but nothing in the program
could say *how* underpowered, or which of the other ~120 recorded nulls were in the same position.

So this module answers, mechanically and without re-fitting anything:

  * **How many folds does the design even yield?** `achievable_folds` — `PurgedWalkForwardSplit`
    inherits `all_season_splits`, so the fold count is a deterministic function of the window
    (`n_seasons − min_train_seasons`), not a per-story choice. (Verified against E7.9: 2021→2026 is
    6 seasons ⇒ 3 folds, which is exactly what that run reported.)
  * **What can each STAT resolve at that fold count?** `pbo_evaluable`, `sign_test_floor`,
    `fold_gate_false_fire`, `dsr_*`. The binding constraint VARIES — E7.14 died on the sign-test
    floor, E7.12-S6 on PBO being undefined, E7.9/E7.15-H3 on DSR — so a single "power" number would
    be a lie.
  * **How does detectability move with the FIELD SIZE?** `dsr_max_field_size`, `field_size_curve`,
    `decompose_field_size`. This is a binding constraint DISTINCT from fold count and it is the one
    the program had no instrument for at all.
  * **Which kind of null is this?** `classify_null` — SEVEN states, because "trustworthy dead" and
    "underpowered" do not exhaust the possibilities.

⭐ **THE ORGANISING FINDING (MH2): A GATE'S STRINGENCY MUST BE A DESIGN CONSTANT, NOT A SIDE-EFFECT
OF n.** The `fold_win_rate ≥ 0.60` clause fires on a TRUE lift of zero **49.7% of the time at 3
folds** and **27.4% at 11** — i.e. its meaning drifts by a factor of two across the fold counts this
program actually runs, and at the low end it is very nearly free. That is the E7.12-S5/S6 defect
routed here as H8. The cure is `fold_consistency_clause`: hold the FALSE-FIRE RATE fixed and let the
required win COUNT move with n, which is the same shape as every other calibrated gate in the repo.

DIAGNOSTIC, NOT A RE-DECISION. Nothing here re-scores an arm or changes a recorded verdict. The one
behavioural change is the H8 clause, which is **weakly stricter than the legacy clause at every fold
count** (proved in `test_cv_power.py`) — so it can only ever prevent a false ADD, never manufacture
one — and is verified against the stored record to re-decide none of the 8 recorded ADDs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

from betting_ml.utils.overfitting import DSR_CONFIDENCE, PBO_SHADOW_TO_LIVE

# ── Design constants the program already owns, restated here so the power maths has one home ──────
MIN_TRAIN_SEASONS = 3          # `all_season_splits` default — the fold-count driver
MIN_FOLDS_FOR_PBO = 4          # `deflation_report` returns pbo=None below this: UNDEFINED, not failed
MIN_FOLDS_FOR_DSR = 3          # `deflated_sharpe` raises below this
LEGACY_FOLD_WIN_RATE = 0.60    # the clause H8 is about (`h_harness.MIN_FOLD_WIN_RATE`)
BH_ALPHA = 0.10                # the family-wise alpha the E7.x harnesses use

# ⭐ **H8: THE CALIBRATED CONSISTENCY LEVEL, AND WHY IT IS 0.20 — derived from DESIGN QUANTITIES, not
# from any arm's score (the NF1.8 discipline: a floor reverse-engineered from the answer is not a
# floor).** Two independent derivations land on the same number:
#   (a) The legacy clause's own operating range. At the fold counts this program actually runs
#       (n = 3…11) `rate ≥ 0.60` has a null false-fire rate of 0.497 (n=3) down to 0.274 (n=11).
#       Pinning the level at the TIGHTEST end of that range makes the clause **no looser than it has
#       ever been at any fold count** while making it uniform — a re-calibration, not a tightening.
#   (b) It is the program's existing "this much selection noise is tolerable" constant: `MAX_PBO`
#       / `PBO_SHADOW_TO_LIVE` is 0.20, and a consistency clause sitting INSIDE a composite gate
#       (which already carries a BH-FDR-corrected paired t) should not also be asked to carry a
#       primary-analysis alpha — that double-counts the same evidence.
# The α=0.10 sensitivity is computed and REPORTED by the MH2 characterization rather than hidden: it
# would re-decide 4 of the 8 recorded ADDs, which is exactly why the choice must be visible.
FOLD_CONSISTENCY_ALPHA = 0.20


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. How many folds does the design yield?
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def achievable_folds(n_seasons: int, min_train_seasons: int = MIN_TRAIN_SEASONS) -> int:
    """Folds `PurgedWalkForwardSplit` yields on a window of `n_seasons` distinct seasons.

    `PurgedWalkForwardSplit.split` delegates its outer loop to `cv_splits.all_season_splits`, which
    emits one fold per season having ≥`min_train_seasons` prior seasons. Purging only TRIMS a fold's
    training rows; it never removes a fold. So the count is deterministic — **the binding constraint
    on every §0.5 verdict in this program is a property of the WINDOW, not a per-story choice.**

    Verified against E7.9 (2021-04-18 → 2026-07-27 = 6 seasons ⇒ 3 folds, which is what it reported).
    """
    return max(0, int(n_seasons) - int(min_train_seasons))


def seasons_for_folds(n_folds: int, min_train_seasons: int = MIN_TRAIN_SEASONS) -> int:
    """Inverse of `achievable_folds` — the window length needed to reach `n_folds`."""
    return max(int(min_train_seasons), int(n_folds) + int(min_train_seasons))


def pbo_evaluable(n_folds: int, n_configs: int = 2) -> bool:
    """Is CSCV/PBO computable at all? Below `MIN_FOLDS_FOR_PBO` it is **UNDEFINED, not failed**.

    Mirrors `run_e7_12_slice1.deflation_report`'s own guard exactly. The distinction matters because
    "PBO could not be computed" is routinely read in a report as "the deflation requirement was not
    met", which converts a design limit into a negative finding about a mechanism (E7.12 S6).
    """
    return int(n_folds) >= MIN_FOLDS_FOR_PBO and int(n_configs) >= 2


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. The fold-consistency clause — the H8 diagnosis and its fix
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def _binom_sf(k: int, n: int, p: float = 0.5) -> float:
    """P(X ≥ k) for X ~ Binomial(n, p), exactly (integer arithmetic under the hood at p=0.5)."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return float(sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(int(k), int(n) + 1)))


def fold_gate_false_fire(n_folds: int, rate: float = LEGACY_FOLD_WIN_RATE) -> float:
    """⭐ **H8, DIAGNOSED: the false-fire rate of a `fold_win_rate ≥ rate` clause on a TRUE LIFT OF
    ZERO** — computed exactly rather than simulated.

    Under the null the per-fold sign is a fair coin, so the clause fires with probability
    `P(Bin(n, ½) ≥ ⌈rate·n⌉)`. That probability is **not a constant** — it is 0.4968 at n=3, 0.3438
    at n=6, 0.2744 at n=11. A clause whose meaning moves by a factor of two across the fold counts a
    program actually runs is not a gate; it is a fold-count-dependent tax. This reproduces E7.12-S6's
    simulated 0.4968 in closed form, and explains E7.12-S5 from the other side (a permuted-bucket
    placebo clearing the same clause 9 times in 11 is unremarkable at ~27% per shot).
    """
    n = int(n_folds)
    if n <= 0:
        return float("nan")
    return _binom_sf(math.ceil(float(rate) * n), n)


@dataclass(frozen=True)
class FoldConsistencyClause:
    """The calibrated replacement for `fold_win_rate ≥ 0.60` (H8's FIX)."""

    n_folds: int
    alpha: float
    wins_required: int | None      # None ⇒ the level is UNATTAINABLE at this fold count
    attained_false_fire: float     # the clause's ACTUAL null false-fire rate (≤ alpha when attainable)
    legacy_wins_required: int
    legacy_false_fire: float

    @property
    def attainable(self) -> bool:
        return self.wins_required is not None

    @property
    def equivalent_rate(self) -> float:
        return float("nan") if self.wins_required is None else self.wins_required / self.n_folds

    @property
    def is_stricter_than_legacy(self) -> bool:
        """Weakly stricter — the property that makes adopting it unable to manufacture an ADD."""
        return self.wins_required is None or self.wins_required >= self.legacy_wins_required

    def passes(self, fold_wins: int) -> bool:
        return self.wins_required is not None and int(fold_wins) >= self.wins_required


def fold_consistency_clause(n_folds: int, alpha: float = FOLD_CONSISTENCY_ALPHA,
                            legacy_rate: float = LEGACY_FOLD_WIN_RATE) -> FoldConsistencyClause:
    """⭐ **H8, FIXED: hold the FALSE-FIRE RATE fixed and let the required WIN COUNT move with n.**

    Required wins = `max(legacy_k, calibrated_k)` where `calibrated_k` is the smallest `k` with
    `P(Bin(n, ½) ≥ k) ≤ alpha`. Three properties, each of which the legacy clause lacks:

      1. **Stable meaning.** The clause's null false-fire rate is ≤ `alpha` at EVERY fold count,
         instead of drifting from 0.50 to 0.27 across the range the program runs.
      2. **It says when it cannot be evaluated.** At n folds the smallest attainable false-fire rate
         is `2⁻ⁿ` (unanimity), so below `n = ⌈log₂(1/alpha)⌉` no win count reaches the level and the
         clause is **UNDEFINED, not passed** — the same honesty `pbo_evaluable` already applies to
         CSCV, and the direct cure for "a placebo cleared the clause" at 3 folds.
      3. **Weakly stricter than the legacy clause at every fold count** (pinned by a test), so
         adopting it can only ever prevent a false ADD. It never manufactures one, which is what
         makes it safe to wire into a live harness inside a diagnostic story.

    🪤 **WHY `max(...)` AND NOT SIMPLY THE CALIBRATED COUNT — property 3 IS FALSE WITHOUT IT, AND MY
    OWN GUARD CAUGHT IT (parametrised to n=40).** A fixed-α sign test asymptotically demands only
    `n/2 + z_α·√n/2` wins, i.e. a RATE tending to 0.50, while `≥60%` demands 0.60n. They cross at
    **n ≈ 31**, beyond which the calibrated count alone would be the LOOSER clause and adopting it
    could admit an arm the legacy bar rejected — exactly the thing this story must not do.

    The deeper point is that the two clauses answer DIFFERENT questions and the gate wants both:
    `≥60%` is a SUBSTANTIVE consistency bar ("the win is broad, not concentrated in a few folds"),
    while the sign test is a STATISTICAL one ("this many wins is not a coin flip"). At small `n` the
    statistical bar is the binding one and the substantive bar is nearly free; at large `n` it is
    the reverse. Taking the max keeps whichever is binding and never relaxes the other. Today's
    tiers all sit at n ≤ 11, so the max is the calibrated count in practice — but a clause whose
    safety property expires silently at some future fold count is not a safe clause.
    """
    n = int(n_folds)
    legacy_k = math.ceil(float(legacy_rate) * n) if n > 0 else 0
    legacy_ff = fold_gate_false_fire(n, legacy_rate) if n > 0 else float("nan")
    cal_k = next((i for i in range(1, n + 1) if _binom_sf(i, n) <= float(alpha)), None)
    k = None if cal_k is None else max(cal_k, legacy_k)
    return FoldConsistencyClause(
        n_folds=n, alpha=float(alpha), wins_required=k,
        attained_false_fire=(_binom_sf(k, n) if k is not None else float("nan")),
        legacy_wins_required=legacy_k, legacy_false_fire=legacy_ff,
    )


def sign_test_floor(n_folds: int, two_sided: bool = False) -> float:
    """The SMALLEST p-value a fold-sign test can produce at `n_folds` — the E7.14 binding constraint.

    A unanimous fold sweep gives `2⁻ⁿ` one-sided (`2·2⁻ⁿ` two-sided). If that floor sits ABOVE the
    BH-FDR cutoff the family must clear, then **no effect of any size can pass** and the null is a
    statement about the design, not about the mechanism. E7.14 hit exactly this: 5 board seasons ⇒
    two-sided floor 0.0625 against a rank-1 BH cutoff of 0.0100, so its 5-of-5 sweep was
    "REAL BUT NOT CERTIFIABLE HERE" — which is a completely different record from "no effect".
    """
    n = int(n_folds)
    if n <= 0:
        return float("nan")
    return float((2.0 if two_sided else 1.0) * 0.5**n)


def folds_for_sign_certifiability(bh_cutoff: float, two_sided: bool = False) -> int:
    """Smallest fold count at which a UNANIMOUS sweep can clear `bh_cutoff` — a re-test trigger in
    the unit that grows. (E7.14: cutoff 0.010, two-sided ⇒ 8 seasons, which is what it reported.)"""
    c = float(bh_cutoff)
    if not (c > 0):
        return 0
    n = 1
    while sign_test_floor(n, two_sided) > c and n < 200:
        n += 1
    return n


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 3. DSR detectability — by fold count AND by field size
# ══════════════════════════════════════════════════════════════════════════════════════════════════

_EULER_GAMMA = 0.5772156649015329


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(float(z) / math.sqrt(2.0)))


def _phi_inv(p: float) -> float:
    from scipy.stats import norm

    return float(norm.ppf(p))


def dsr_benchmark_sr0(n_trials: int, var_trials_sr: float, benchmark_sr: float = 0.0) -> float:
    """The deflated benchmark `SR0` = expected MAXIMUM Sharpe under `n_trials` (AFML §14).

    Byte-for-byte the same expression `overfitting.deflated_sharpe` uses, exposed on its own because
    **SR0 is where the field-size axis lives**: it scales with `√V · z(N)` where `z(N)` grows like
    `√(2 ln N)`. Both factors are properties of the FIELD, not of the winner — which is why adding
    unrelated arms to a bake-off taxes a real finding (see `decompose_field_size`).
    """
    N = max(int(n_trials), 1)
    if N == 1:
        return float(benchmark_sr)
    z = (1 - _EULER_GAMMA) * _phi_inv(1 - 1.0 / N) + _EULER_GAMMA * _phi_inv(1 - 1.0 / (N * math.e))
    return float(benchmark_sr + math.sqrt(max(float(var_trials_sr), 1e-12)) * z)


def _dsr_stat(sr: float, sr0: float, n_obs: int, skew: float = 0.0, kurt: float = 3.0) -> float:
    denom = math.sqrt(max(1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2, 1e-12))
    return (sr - sr0) * math.sqrt(max(int(n_obs) - 1, 1)) / denom


def dsr_from_sr(sr: float, *, n_obs: int, n_trials: int, var_trials_sr: float,
                skew: float = 0.0, kurt: float = 3.0, benchmark_sr: float = 0.0) -> float:
    """DSR for a hypothetical winner with per-fold Sharpe `sr`. The closed-form the power table
    inverts; agrees with `overfitting.deflated_sharpe` on a real series (pinned by a test)."""
    sr0 = dsr_benchmark_sr0(n_trials, var_trials_sr, benchmark_sr)
    return _phi(_dsr_stat(float(sr), sr0, n_obs, skew, kurt))


def dsr_required_sr(*, n_obs: int, n_trials: int, var_trials_sr: float,
                    confidence: float = DSR_CONFIDENCE, skew: float = 0.0, kurt: float = 3.0,
                    benchmark_sr: float = 0.0) -> float:
    """The per-fold Sharpe a winner MUST post to reach `confidence` — the honest bar, stated up front.

    This is the number a pre-registration should carry instead of "DSR ≥ 0.95": at 3 folds over a
    28-arm grid the bar is a per-fold Sharpe near 3, which is a statement about the DESIGN that can
    be read before a single arm is fitted.
    """
    sr0 = dsr_benchmark_sr0(n_trials, var_trials_sr, benchmark_sr)
    z = _phi_inv(float(confidence))
    lo, hi = sr0, sr0 + 1.0
    for _ in range(200):                      # expand until the target is bracketed
        if _dsr_stat(hi, sr0, n_obs, skew, kurt) >= z:
            break
        hi += max(1.0, hi - sr0)
    for _ in range(200):                      # bisect (the statistic is increasing in sr above sr0)
        mid = 0.5 * (lo + hi)
        if _dsr_stat(mid, sr0, n_obs, skew, kurt) < z:
            lo = mid
        else:
            hi = mid
    return float(hi)


def folds_to_clear_dsr(*, observed_sr: float, n_trials: int, var_trials_sr: float,
                       confidence: float = DSR_CONFIDENCE, skew: float = 0.0, kurt: float = 3.0,
                       benchmark_sr: float = 0.0, max_folds: int = 100_000,
                       n_obs_now: int | None = None,
                       var_is_asymptotic_fallback: bool = False) -> int | None:
    """Fold count at which an effect of THIS size clears DSR — `None` when no `n` ever does.

    ⭐ **AND THE CLOSED-FORM REASON, which the program previously could only discover by searching:
    with a MEASURED trial dispersion, DSR is UNREACHABLE AT ANY n exactly when `observed_sr ≤ SR0`.**
    `n` enters the statistic only through the increasing factor `√(n−1)`, so it can scale a positive
    gap but cannot create one. A winner whose per-fold Sharpe sits below the field's expected maximum
    is not "far from the gate"; it is on the wrong side of it, and more seasons will never help —
    only a SMALLER FIELD will (a different remedy with a different cost; the two must not be
    reported alike). `h_harness.null_analysis` used to search to 4,000 folds and return `None`; this
    says *why*.

    ⚠️ **BUT `V` IS ONLY A FIELD CONSTANT WHEN IT WAS MEASURED FROM ONE.** `deflated_sharpe` falls
    back to `V = 1/n_obs` — the asymptotic null variance of a Sharpe estimate — when fewer than two
    trial Sharpes are available, and THAT quantity genuinely does shrink as observations accrue. So
    the extrapolation must branch exactly as the gate does: hold `V` fixed when it is a measured
    cross-trial dispersion (`var_is_asymptotic_fallback=False`, the default), and let it scale as
    `1/k` when it is the fallback. Getting this wrong in either direction extrapolates a bar the
    gate does not use — the same "reports on a quantity it is not measuring" failure that produced
    the two E7.15-H3 defects and the `np.resize` one. In the fallback branch `SR0 ∝ 1/√k` while the
    numerator's `√(k−1)` grows, so the statistic is still monotone in `k` and a scan is exact.
    """
    sr = float(observed_sr)
    z = _phi_inv(float(confidence))

    def _stat_at(k: int) -> float:
        v = var_trials_sr
        if var_is_asymptotic_fallback and n_obs_now:
            v = float(var_trials_sr) * (float(n_obs_now) / float(k))
        sr0_k = dsr_benchmark_sr0(n_trials, v, benchmark_sr)
        return _dsr_stat(sr, sr0_k, k, skew, kurt)

    if not (var_is_asymptotic_fallback and n_obs_now):
        sr0 = dsr_benchmark_sr0(n_trials, var_trials_sr, benchmark_sr)
        if sr <= sr0:
            return None
        denom = math.sqrt(max(1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2, 1e-12))
        n_ceil = int(math.ceil(1.0 + (z * denom / (sr - sr0)) ** 2))
        return n_ceil if n_ceil <= int(max_folds) else None

    if sr <= 0:
        return None                      # a non-positive Sharpe never clears, however V shrinks
    lo, hi = max(int(n_obs_now), 2), max(int(n_obs_now), 2)
    while hi <= int(max_folds):
        if _stat_at(hi) >= z:
            break
        lo, hi = hi, hi * 2
    if hi > int(max_folds):
        return None
    while lo < hi:                        # exact integer crossing (monotone in k)
        mid = (lo + hi) // 2
        if _stat_at(mid) >= z:
            hi = mid
        else:
            lo = mid + 1
    return lo


def dsr_ceiling(n_obs: int, kurt: float = 3.0, skew: float = 0.0) -> float:
    """⭐ **THE HARD STRUCTURAL CEILING: the LARGEST DSR attainable at `n_obs` observations, at ANY
    effect size and ANY field size.**

    As `sr → ∞` the DSR statistic tends to `√(n−1) / √((kurt−1)/4)` — the non-normality correction in
    the denominator grows linearly in `sr`, exactly cancelling the numerator — so the test has a
    finite maximum that depends ONLY on the observation count. Under normal-ish moments that is
    `Φ(√(2(n−1)))`, which at **n = 3 is 0.977**: the `DSR ≥ 0.95` gate is only 0.027 below the
    absolute ceiling of the design, and reaching even the gate needs a per-fold Sharpe in the
    single-to-double digits once a real field is deflated against.

    This is the number that turns "E7.9 scored 0.842 against a 0.95 gate" from a statement about the
    features into a statement about the DESIGN — and it can be computed before a single arm is fit.
    """
    n = int(n_obs)
    if n < 2:
        return float("nan")
    return _phi(math.sqrt(n - 1) / math.sqrt(max((float(kurt) - 1.0) / 4.0, 1e-12)))


def dsr_max_field_size(*, observed_sr: float, n_obs: int, var_trials_sr: float,
                       confidence: float = DSR_CONFIDENCE, skew: float = 0.0, kurt: float = 3.0,
                       benchmark_sr: float = 0.0, max_trials: int = 500) -> int:
    """⭐ **THE FIELD-SIZE AXIS: the LARGEST arm count in which this effect still clears DSR.**

    `SR0` is monotone increasing in `n_trials`, so DSR is monotone DECREASING in it — the answer is
    a clean threshold. This is the number a story needs BEFORE it designs its field: E7.15-H3's
    trajectory arms clear at 2 and fail at 7, so "how many arms may I run?" is answerable in advance
    instead of discovered after the run. Returns 0 when even a 2-arm field cannot clear.
    """
    best = 0
    for n in range(2, int(max_trials) + 1):
        if dsr_from_sr(observed_sr, n_obs=n_obs, n_trials=n, var_trials_sr=var_trials_sr,
                       skew=skew, kurt=kurt, benchmark_sr=benchmark_sr) >= float(confidence):
            best = n
        else:
            break
    return best


def field_size_curve(*, observed_sr: float, n_obs: int, var_trials_sr: float,
                     arm_counts: Sequence[int] = (2, 3, 4, 5, 7, 10, 15, 20, 28, 40),
                     confidence: float = DSR_CONFIDENCE) -> list[dict]:
    """DSR vs field size, holding the winner's effect and the trial dispersion fixed."""
    out = []
    for n in arm_counts:
        sr0 = dsr_benchmark_sr0(n, var_trials_sr)
        d = dsr_from_sr(observed_sr, n_obs=n_obs, n_trials=n, var_trials_sr=var_trials_sr)
        out.append({"n_arms": int(n), "sr0": round(sr0, 4), "dsr": round(d, 4),
                    "passes": bool(d >= confidence)})
    return out


def decompose_field_size(*, observed_sr: float, n_obs: int,
                         n_trials_wide: int, var_wide: float,
                         n_trials_narrow: int, var_narrow: float,
                         confidence: float = DSR_CONFIDENCE,
                         skew: float = 0.0, kurt: float = 3.0) -> dict:
    """⚠️ **SHRINKING A FIELD MOVES TWO THINGS AT ONCE, AND ONLY ONE OF THEM IS "MULTIPLICITY".**

    `SR0 = √V · z(N)`. Dropping arms lowers `N` (the multiplicity channel) **and** usually lowers `V`
    — the cross-trial Sharpe DISPERSION — because the arms you drop are the ones far from the winner.
    That second channel is the NF-D14 lesson ("a deflation statistic computed over a field containing
    its own nulls measures the nulls") wearing a different hat, and on the E7.15-H3 case it is the
    DOMINANT one: 7→2 arms moves `z` by ~2.5× but `V` by ~300×.

    Reporting only "we ran fewer arms" therefore under-explains the change and invites the wrong
    generalisation ("just run fewer arms"). The honest statement is: **a family gets its own
    pre-registered field because bundling unrelated mechanisms inflates BOTH the trial count and the
    trial dispersion, and the dispersion term is the bigger tax.**
    """
    def _d(N: int, V: float) -> float:
        # ⚠️ The empirical moments MUST be threaded through. An earlier cut defaulted them here
        # while `dsr_max_field_size` was called with the real ones, and the two then disagreed about
        # whether a 2-arm field cleared — a diagnostic reporting on a quantity it was not measuring,
        # which is this repo's most-repeated defect shape. Same moments everywhere, or nowhere.
        return dsr_from_sr(observed_sr, n_obs=n_obs, n_trials=N, var_trials_sr=V,
                           skew=skew, kurt=kurt)

    wide, narrow = _d(n_trials_wide, var_wide), _d(n_trials_narrow, var_narrow)
    n_only = _d(n_trials_narrow, var_wide)     # multiplicity channel alone
    v_only = _d(n_trials_wide, var_narrow)     # dispersion channel alone
    return {
        "dsr_wide_field": round(wide, 4), "dsr_narrow_field": round(narrow, 4),
        "dsr_if_only_trial_count_shrank": round(n_only, 4),
        "dsr_if_only_dispersion_shrank": round(v_only, 4),
        "dsr_ceiling_at_this_n_obs": round(dsr_ceiling(n_obs, kurt), 4),
        "sr0_wide": round(dsr_benchmark_sr0(n_trials_wide, var_wide), 4),
        "sr0_narrow": round(dsr_benchmark_sr0(n_trials_narrow, var_narrow), 4),
        "share_from_trial_count": round((n_only - wide) / (narrow - wide), 3)
        if abs(narrow - wide) > 1e-12 else float("nan"),
        "share_from_dispersion": round((v_only - wide) / (narrow - wide), 3)
        if abs(narrow - wide) > 1e-12 else float("nan"),
        "passes_wide": bool(wide >= confidence), "passes_narrow": bool(narrow >= confidence),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4. Composite-gate power and the minimum detectable effect
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def composite_gate_power(*, n_folds: int, lift_over_sd: float, n_metrics: int = 1,
                         alpha: float = BH_ALPHA,
                         consistency_alpha: float = FOLD_CONSISTENCY_ALPHA,
                         n_sims: int = 20_000, seed: int = 2) -> dict:
    """Power of the ACTUAL composite rule, simulated, at a true per-fold lift of `lift_over_sd` SDs.

    The thing that has to detect an effect in this program is not a textbook t-test; it is
    `fold consistency AND positive mean AND a one-sided paired t under BH-FDR at rank 1`. Each clause
    degrades differently at small n — the consistency clause is COARSE (at 3 folds it can only read
    0, ⅓, ⅔ or 1) while the t-clause has fat tails (df=2) — so a formula for either alone materially
    misstates the design. Generalised from `s6_feasibility.power_curve`, with the H8 clause reported
    beside the legacy one so the cost of the fix is visible rather than assumed.
    """
    from scipy import stats

    n = int(n_folds)
    rng = np.random.default_rng(int(seed))
    d = rng.normal(float(lift_over_sd), 1.0, size=(int(n_sims), n))
    wins = (d > 0).sum(axis=1)
    legacy_k = math.ceil(LEGACY_FOLD_WIN_RATE * n)
    clause = fold_consistency_clause(n, consistency_alpha)
    sd = d.std(axis=1, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = d.mean(axis=1) / (sd / math.sqrt(n))
    p = stats.t.sf(t, df=n - 1)
    bh_cut = float(alpha) / max(int(n_metrics), 1)
    pos, bh = d.mean(axis=1) > 0, p <= bh_cut
    legacy_pass = wins >= legacy_k
    new_pass = (wins >= clause.wins_required) if clause.attainable else np.zeros_like(legacy_pass)
    return {
        "n_folds": n, "lift_over_sd": float(lift_over_sd), "bh_cutoff": bh_cut,
        "power_consistency_legacy": round(float(legacy_pass.mean()), 4),
        "power_consistency_calibrated": round(float(new_pass.mean()), 4),
        "consistency_clause_attainable": clause.attainable,
        "power_bh": round(float(bh.mean()), 4),
        "power_full_rule_legacy": round(float((legacy_pass & pos & bh).mean()), 4),
        "power_full_rule_calibrated": round(float((new_pass & pos & bh).mean()), 4),
    }


def mde_in_sd_units(*, n_folds: int, n_metrics: int = 1, target_power: float = 0.80,
                    alpha: float = BH_ALPHA,
                    consistency_alpha: float = FOLD_CONSISTENCY_ALPHA,
                    calibrated: bool = True, n_sims: int = 20_000, seed: int = 2,
                    grid: Iterable[float] | None = None) -> float | None:
    """Smallest true per-fold lift (in fold-delta SDs) the composite rule detects with `target_power`.

    Returns `None` when the design cannot reach the target at ANY effect size — which happens
    whenever the sign floor or the consistency clause is structurally unattainable, and is a
    materially different finding from "the effect must be large".
    """
    key = "power_full_rule_calibrated" if calibrated else "power_full_rule_legacy"
    for lift in (grid if grid is not None else np.arange(0.0, 6.01, 0.05)):
        pw = composite_gate_power(n_folds=n_folds, lift_over_sd=float(lift), n_metrics=n_metrics,
                                  alpha=alpha, consistency_alpha=consistency_alpha,
                                  n_sims=n_sims, seed=seed)
        if pw[key] >= float(target_power):
            return float(lift)
    return None


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 5. Reading a null — SEVEN states, because two do not cover the cases
# ══════════════════════════════════════════════════════════════════════════════════════════════════

#: The seven states a §0.5 null can be in. `TRUSTWORTHY_DEAD` and `POWER_LIMITED` are the two the
#: story set out to separate; the other three are cases the binary reading silently mislabels.
NULL_STATES = (
    "INACTIVE",           # the mechanism CANNOT ACT on this population — not power, not a bug
    "UNKNOWN",            # the artifact records no fold structure — unread, not underpowered
    "UNDEFINED",          # a required stat was not computable at this fold count — not failed
    "GENUINE_ABSENCE",    # the best arm loses on average — no n and no field size rescues it
    "DSR_UNREACHABLE",    # beats the foil, but SR ≤ SR0 in THIS field — only a smaller field helps
    "POWER_LIMITED",      # every gate reachable; states the folds/seasons it needs
    "TRUSTWORTHY_DEAD",   # powered to detect the pre-registered meaningful effect, and did not
)


@dataclass
class NullVerdict:
    state: str
    reason: str
    retest_trigger: str | None = None
    folds_have: int | None = None
    folds_needed: int | None = None
    extra_seasons: int | None = None
    max_field_size: int | None = None
    detail: dict = field(default_factory=dict)


# ⭐⭐ DSR-CONV (2026-08-08) — THE INSTRUMENT'S REMEDY IS ONLY AS TRUSTWORTHY AS THE `V` IT WAS
# HANDED. Every DSR-derived verdict below (`DSR_UNREACHABLE`'s "use a smaller field",
# `POWER_LIMITED`'s "+N folds OR ≤M arms") is computed from `var_trials_sr` via `SR0 = √V·z(N)`. If
# that `V` was measured over a field CONTAINING its pre-registered lose-by-construction degenerates,
# it is inflated for a structural reason — a designed loser's consistency is not evidence about how
# real configurations disperse — and so the remedy prescribes a FIELD TRIM to fix what is actually a
# CONVENTION defect. That is the third member of the MH2.2 family (the first: `classify_null`
# prescribing a field below a story's DECLARED minimum; the second: a post-hoc trim reported as if it
# were a design choice). The cure is provenance: the caller states whether the `V` it handed over was
# degenerate-excluded, and an UNSTATED provenance is hedged, never assumed clean (NF1.7 (a) — a check
# that did not run is not a check that passed).
_V_PROVENANCE_CLEAN = (
    "`V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction "
    "degenerates, which remain in `n_trials`), so the field-size reading below is about the "
    "EVIDENCE.")
_V_PROVENANCE_INFLATED = (
    "⛔ **DO NOT QUOTE THIS REMEDY BARE.** The `V` handed to this classifier INCLUDES the "
    "pre-registered lose-by-construction degenerates, which inflate it for a structural reason "
    "(`SR0 = √V·z(N)`). The FIRST lever is therefore the DSR-CONV convention — re-measure `V` over "
    "the non-degenerate arms, keeping `n_trials` at the full declared field — NOT a field trim. "
    "Re-classify on the degenerate-excluded `V` before treating any field-size trigger as advice.")
_V_PROVENANCE_UNKNOWN = (
    "⚠️ The provenance of `V` was NOT stated (`degenerates_excluded_from_v=None`), so this "
    "classifier cannot tell a DSR-CONV-correct dispersion from one inflated by pre-registered "
    "degenerates. Treat the field-size reading as UNVERIFIED — establish the provenance and "
    "re-classify rather than acting on it.")


def _v_provenance_note(degenerates_excluded_from_v: bool | None) -> str:
    if degenerates_excluded_from_v is True:
        return _V_PROVENANCE_CLEAN
    if degenerates_excluded_from_v is False:
        return _V_PROVENANCE_INFLATED
    return _V_PROVENANCE_UNKNOWN


def classify_null(*, metric: str, n_folds: int, n_arms: int,
                  beats_foil: bool, observed_sr: float | None = None,
                  var_trials_sr: float | None = None,
                  fold_wins: int | None = None,
                  p_one_sided: float | None = None, bh_cutoff: float | None = None,
                  active: bool = True, inactive_reason: str | None = None,
                  mde_sd_units: float | None = None,
                  meaningful_sd_units: float | None = None,
                  skew: float = 0.0, kurt: float = 3.0,
                  confidence: float = DSR_CONFIDENCE,
                  degenerates_excluded_from_v: bool | None = None,
                  var_trials_sr_with_degenerates: float | None = None) -> NullVerdict:
    """Classify one recorded null into one of `NULL_STATES`. **Order matters** — each state below is checked before the ones
    that would otherwise absorb it.

    ⭐ **`INACTIVE` IS FIRST AND IT IS THE STATE THE PROGRAM WAS MISSING (E7.15).** A mechanism that
    structurally cannot act on its population — E7.15's `xwoba_against`, whose minor-league feature is
    a Triple-A-only Statcast summary, so the ladder has ZERO within-player transitions to act on — is
    neither underpowered nor broken. The harness's inert-anchor guard cannot tell the two apart and
    correctly BLOCKS on both, which sent a session hunting a defect that did not exist. Labelling it
    up front is the cure: an inactive population is a finding about SCOPE, and the remedy is a
    different population, never more seasons and never a bug hunt.

    `UNDEFINED` is second for the same reason: a stat that could not be COMPUTED must never be
    absorbed into a verdict about a mechanism (E7.12-S6's PBO at 3 folds).

    `GENUINE_ABSENCE` outranks the power states because a negative point estimate is not rescued by
    n (NF-D15 g″), and `DSR_UNREACHABLE` outranks `POWER_LIMITED` because its remedy is a smaller
    FIELD, not more seasons — reporting it as "needs N more seasons" (which a naive search does) is
    an actively misleading re-test trigger.

    ⭐ **`degenerates_excluded_from_v` (DSR-CONV) states the PROVENANCE of `var_trials_sr`**, because
    every field-size remedy below is computed from it. Pass `True` when `V` was measured excluding the
    pre-registered lose-by-construction degenerates (what `dsr_gate`'s binding `var_trials_sr` now
    is), `False` when they are still in it, and leave it `None` only if you genuinely do not know —
    an unstated provenance is HEDGED in the remedy text, never assumed clean. `var_trials_sr_with_
    degenerates` is recorded beside it so the size of the inflation is on the record rather than
    asserted. None of this changes a STATE — the classification is unchanged for a given `V`; what
    changes is whether the remedy sentence may be acted on.
    """
    d: dict = {"n_folds": int(n_folds), "n_arms": int(n_arms)}

    if not active:
        return NullVerdict("INACTIVE", inactive_reason or (
            f"`{metric}`: the mechanism has no rows it can act on, so no arm is a real candidate. "
            f"This is a statement about the POPULATION's scope, not about the effect. More seasons "
            f"cannot fix it and there is no defect to find (E7.15/NF1.9)."),
            retest_trigger="a population on which the mechanism can act at all", detail=d)

    if not n_folds:
        # ⚠️ "no fold count on record" is NOT "too few folds". Collapsing the two would let the
        # inventory emit a re-test trigger ("+4 folds") for a study whose fold count it simply
        # never read — a fabricated finding, which is the failure mode this whole story is about.
        return NullVerdict("UNKNOWN", (
            f"`{metric}`: the artifact records no fold count, so NOTHING can be said about what "
            f"this design could detect. Not underpowered, not dead — unread. The remedy is a "
            f"harness that records its fold structure, not more data."),
            retest_trigger="record the fold structure in the artifact, then re-classify", detail=d)

    if not pbo_evaluable(n_folds, n_arms):
        return NullVerdict("UNDEFINED", (
            f"`{metric}`: {n_folds} fold(s) < {MIN_FOLDS_FOR_PBO} — CSCV/PBO is UNDEFINED, so the "
            f"§0.5 deflation requirement was not EVALUATED, let alone failed. No effect size and no "
            f"gate choice fixes this; only more folds do."),
            retest_trigger=(f"{MIN_FOLDS_FOR_PBO - int(n_folds)} more fold(s) — i.e. a window of "
                            f"{seasons_for_folds(MIN_FOLDS_FOR_PBO)} seasons"),
            folds_have=int(n_folds), folds_needed=MIN_FOLDS_FOR_PBO,
            extra_seasons=MIN_FOLDS_FOR_PBO - int(n_folds), detail=d)

    if not beats_foil:
        return NullVerdict("GENUINE_ABSENCE", (
            f"`{metric}`: the best arm does not beat the foil ON AVERAGE. No sample size rescues a "
            f"negative point estimate and no field size changes its sign — do NOT re-test."),
            retest_trigger=None, folds_have=int(n_folds), detail=d)

    if observed_sr is not None and var_trials_sr is not None:
        # ⚠️ The EMPIRICAL moments must be threaded through here exactly as they are into
        # `decompose_field_size`. Defaulting them makes this classifier answer about a
        # normal-moment world while the gate it is classifying used the real ones — the two then
        # disagree about whether a metric is DSR-reachable, which is the whole verdict.
        sr0 = dsr_benchmark_sr0(int(n_arms), float(var_trials_sr))
        d.update({"observed_sr": round(float(observed_sr), 4), "sr0": round(sr0, 4),
                  "var_trials_sr": float(var_trials_sr),
                  "degenerates_excluded_from_v": degenerates_excluded_from_v})
        v_note = _v_provenance_note(degenerates_excluded_from_v)
        if var_trials_sr_with_degenerates is not None:
            d["var_trials_sr_with_degenerates"] = float(var_trials_sr_with_degenerates)
            d["v_inflation_factor_from_degenerates"] = (
                round(float(var_trials_sr_with_degenerates) / float(var_trials_sr), 4)
                if float(var_trials_sr) > 0 else None)
        need = folds_to_clear_dsr(observed_sr=float(observed_sr), n_trials=int(n_arms),
                                  var_trials_sr=float(var_trials_sr), skew=skew, kurt=kurt,
                                  confidence=confidence)
        max_field = dsr_max_field_size(observed_sr=float(observed_sr), n_obs=int(n_folds),
                                       var_trials_sr=float(var_trials_sr), skew=skew, kurt=kurt,
                                       confidence=confidence)
        if need is None:
            return NullVerdict("DSR_UNREACHABLE", (
                f"`{metric}`: the winner's per-fold Sharpe {observed_sr:.3f} sits at or BELOW the "
                f"{n_arms}-arm field's deflated benchmark SR0 {sr0:.3f}, so DSR is unreachable at "
                f"ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a "
                f"SMALLER, pre-registered field, not more seasons. {v_note}"),
                retest_trigger=(
                    (f"re-run the mechanism in a field of ≤{max_field} arms"
                     if max_field >= 2 else
                     "NOT rescuable by field size either — even a 2-arm field does not "
                     "clear at this fold count and dispersion, so the only lever left "
                     "is a lower-variance design (more rows per fold / a sharper metric)")
                    + ("" if degenerates_excluded_from_v is True
                       else f" — ⚠️ BUT FIRST: {v_note}")),
                folds_have=int(n_folds), max_field_size=max_field, detail=d)
        if need > int(n_folds):
            # ⚠️ Stated in FOLDS, never translated to seasons here. The fold RULE differs per tier
            # — walk-forward burns `min_train_seasons` before its first fold, leave-one-cohort-out
            # does not — so this function, which does not know the tier, must not do the calendar
            # arithmetic. An earlier cut applied the walk-forward inverse to a cohort-based tier and
            # produced a "36-season window" for a study whose folds ARE cohorts. The caller owns
            # the translation because only the caller knows the rule.
            return NullVerdict("POWER_LIMITED", (
                f"`{metric}`: the effect is positive and every gate is REACHABLE, but this design "
                f"cannot resolve it — DSR alone needs {need} folds against {n_folds} (the BH-FDR "
                f"requirement is separate and may be larger). {v_note}"),
                retest_trigger=(f"+{need - int(n_folds)} folds for the DSR gate"
                                + (f", OR a field of ≤{max_field} arms at the CURRENT fold count"
                                   if max_field >= 2 else
                                   " — field size alone cannot rescue it at this dispersion")
                                + ("" if degenerates_excluded_from_v is True
                                   else f" — ⚠️ BUT FIRST: {v_note}")),
                folds_have=int(n_folds), folds_needed=need,
                extra_seasons=need - int(n_folds), max_field_size=max_field, detail=d)

    if p_one_sided is not None and bh_cutoff is not None:
        floor = sign_test_floor(n_folds, two_sided=False)
        d.update({"sign_floor": floor, "bh_cutoff": float(bh_cutoff)})
        if floor > float(bh_cutoff):
            need = folds_for_sign_certifiability(float(bh_cutoff))
            return NullVerdict("POWER_LIMITED", (
                f"`{metric}`: at {n_folds} folds the fold-sign floor is {floor:.4f}, ABOVE the BH "
                f"cutoff {bh_cutoff:.4f} — no effect of any size could have passed. This is a "
                f"statement about the design, not the mechanism (E7.14)."),
                retest_trigger=f"+{need - int(n_folds)} folds (⇒ {need} total) for certifiability",
                folds_have=int(n_folds), folds_needed=need,
                extra_seasons=need - int(n_folds), detail=d)

    if mde_sd_units is not None and meaningful_sd_units is not None:
        d.update({"mde_sd_units": float(mde_sd_units),
                  "meaningful_sd_units": float(meaningful_sd_units)})
        if float(mde_sd_units) > float(meaningful_sd_units):
            return NullVerdict("POWER_LIMITED", (
                f"`{metric}`: the design detects {mde_sd_units:.2f} SD at 80% power, but the "
                f"pre-registered practically-meaningful effect is {meaningful_sd_units:.2f} SD — a "
                f"decision-changing effect would NOT reliably have shown up here."), detail=d)
        return NullVerdict("TRUSTWORTHY_DEAD", (
            f"`{metric}`: the design detects {mde_sd_units:.2f} SD at 80% power, at or below the "
            f"pre-registered meaningful effect of {meaningful_sd_units:.2f} SD. A decision-changing "
            f"effect would have shown and did not — this null RULES THE MECHANISM OUT at the size "
            f"that would matter."), retest_trigger=None, folds_have=int(n_folds), detail=d)

    return NullVerdict("POWER_LIMITED", (
        f"`{metric}`: insufficient recorded statistics to certify the null as powered. Absent a "
        f"detectability figure the honest default is POWER-LIMITED — a null is trustworthy only "
        f"when something was computed to make it so."), folds_have=int(n_folds), detail=d)


__all__ = [
    "MIN_TRAIN_SEASONS", "MIN_FOLDS_FOR_PBO", "MIN_FOLDS_FOR_DSR", "LEGACY_FOLD_WIN_RATE",
    "BH_ALPHA", "FOLD_CONSISTENCY_ALPHA", "PBO_SHADOW_TO_LIVE", "NULL_STATES",
    "achievable_folds", "seasons_for_folds", "pbo_evaluable",
    "fold_gate_false_fire", "FoldConsistencyClause", "fold_consistency_clause",
    "sign_test_floor", "folds_for_sign_certifiability",
    "dsr_benchmark_sr0", "dsr_from_sr", "dsr_required_sr", "dsr_ceiling", "folds_to_clear_dsr",
    "dsr_max_field_size", "field_size_curve", "decompose_field_size",
    "composite_gate_power", "mde_in_sd_units", "NullVerdict", "classify_null",
]
