"""NF-W8-0d — the DSR gate-design FRONTIER: is `dsr_ok` reachable by a lower-variance design?

FOUR consecutive QB/RB stories (NF-W7f, NF-W7h, NF-W7j, NF-W8-0c) were refused by **`dsr_ok`
ALONE** while passing every other registered clause, and THREE of them named the same remaining
remedy — "a lower-variance design". NF-W8-0c narrowed it further to **rows per fold** (80.7% of the
fold-scale variance of the corrected quantity is within-fold sampling noise at ~685 rows/fold).
This module measures whether that lever exists, before another modelling story is funded into the
same wall.

⛔ NOTHING HERE RELAXES A LIVE GATE. `DSR_MIN` is INHERITED at 0.95, the declared field stays at 4
(MH2.7), no arm is re-scored and no model ships. Every input is arithmetic on NF-W8-0c's ALREADY
PUBLISHED per-fold scores — the EFFECT is held fixed; only the DESIGN moves.

──────────────────────────────────────────────────────────────────────────────────────────────
⭐ THE PROPOSITION THIS MODULE IS BUILT AROUND — THE LOCKSTEP INVARIANT

`deflated_sharpe` reads two things: the winner's Sharpe `SR = mean(δ_w)/sd(δ_w)`, and the deflation
benchmark `SR0 = std(trial Sharpes) · z(N)` — and **the winner is one of those trials** (NF-W7k).

Suppose a design change multiplies EVERY arm's per-fold delta dispersion by a common factor `c`,
holding the means fixed. Then every trial Sharpe scales by `1/c`, so `std(trial Sharpes)` scales by
`1/c`, so `SR0` scales by `1/c` — and therefore

        SR − SR0   ↦   (SR − SR0)/c        ⇒  ITS SIGN IS INVARIANT.

Clearing `DSR ≥ 0.95` requires the DSR statistic `(SR − SR0)·√(T−1)/√denom ≥ Φ⁻¹(0.95) > 0`, hence
requires `SR > SR0`. **So a purely proportional dispersion lever can never flip an `SR ≤ SR0`
refusal — at any fold count, any row count, any draw count.** Worse: with `SR < SR0` the gap
`SR − SR0` is negative and a sharper design makes it MORE negative, so DSR falls.

This generalises NF-W7k (draws) and MH2's `DSR_UNREACHABLE` (folds) into the statement that covers
the remedy three records actually prescribed: **"a lower-variance design" is not a lever whenever
the variance reduction is shared across the field** — which is the GENERIC case, because the arms
score the same rows with the same draws (common random numbers).

A variance lever can only help to the extent it shrinks the WINNER's dispersion MORE than the
field's. That residual is real but small, and it is exactly what the simulated frontier measures
rather than asserts.

──────────────────────────────────────────────────────────────────────────────────────────────
⚠️ THE STRUCTURAL REASON THE ROWS/FOLD LEVER IS WEAKER THAN THE LEVEL DECOMPOSITION SUGGESTS

NF-W8-0c decomposed the fold-to-fold SD of the LEVEL (the bias) and found it 80.7% sampling noise.
But the gate deflates the PAIRED statistic `δ = |b_I| − |b_a|`, and

        b_I,f − b_a,f = −(1/m) · Σᵢ (pointₐ,ᵢ − point_I,ᵢ)      ← the realized `y` cancels EXACTLY

so the common row-sampling error CANCELS between the arms. For `cond_shift` the per-row point
difference is `shift·πᵢ`, whose row SD is bounded by `|shift|·½ ≤ 0.25` PPR against a per-row error
SD of 6.13 PPR — under 0.2% of the level's sampling variance. The level's noise re-enters `δ` ONLY
through the `|·|` KINK, on the folds where the corrected bias crosses zero. Measuring the lever on
the LEVEL therefore over-states it; this module measures it on the statistic the gate reads.

──────────────────────────────────────────────────────────────────────────────────────────────
⛔ EVERY DSR IS COMPUTED BY `nf1_1_model.deflated_sharpe`, BY IDENTITY — including the split-field
diagnostic, which is expressed as a synthetic trial vector fed to that same function rather than as
a second copy of the arithmetic (NF-W7k / NF-C0e "the check validates its own copy of the logic").

📌 SCOPE. The lockstep invariant is vertical-agnostic; this module is not. It lives beside
`fp_mc_variance.py` in the fantasy vertical deliberately — promoting it into `betting_ml/utils/`
would change a SHARED instrument whose output is pinned by cross-vertical guards, and that is a
FORWARD decision for a successor, never a side effect of an instrument story (MH2.7's lesson ii).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14
from quant_sports_intel_models.football.nfl.fantasy import fp_cross_position as XP

STORY = "NF-W8-0d"
PREDECESSORS: tuple[str, ...] = ("NF-W8-0c", "NF-W7k", "NF-W7j", "NF-W7h", "NF-W7f")

#: ⛔ INHERITED and NEVER relaxed — this story reads the bar, it does not set it (E2.1-r).
DSR_MIN: float = XP.DSR_MIN

#: NF-W8-0c's declared QB body field, in its registered order. The FIRST entry is the winner.
REAL_ARMS: tuple[str, ...] = ("cond_shift", "cond_scale", "avail_relevel", "leg_scale")
INCUMBENT = "identity"
WINNER = "cond_shift"
DECLARED_FIELD_SIZE = len(REAL_ARMS)

#: NF-W8-0c's recorded family-B DSR — the reproduction pin (prereg §3 G0).
RECORDED_DSR = 0.1654
REPRO_TOL = 1e-9

#: QB modelled rows per SEASON, measured from NF-W8-0c's own folds (2 half-season blocks).
#: A design quantity, declared before the sweep (prereg §5).
QB_ROWS_PER_SEASON = 1374.6

#: The lockstep ladder — dispersion multipliers `c` applied to EVERY arm's delta series.
LOCKSTEP_FACTORS: tuple[float, ...] = (1.0, 0.5, 0.25, 0.1, 0.01)

#: The declared, bracketed scaling laws for the NON-sampling fold-scale variance (prereg §4).
LAWS: tuple[str, ...] = ("persistent", "averaging")

#: The feasible + a-fortiori windows (prereg §5). `feasible` gates verdict (a).
WINDOWS: tuple[tuple[str, int, bool, str], ...] = (
    ("2022-2025 (SHIPPED)", 4, True, "the design NF-W8-0c actually ran"),
    ("2019-2025 (widest reachable today)", 7, True,
     "costs train history — 3 seasons of burn-in instead of 6"),
    ("2019-2030 (calendar-bound)", 12, False, "+1 eval season per year; not reachable today"),
    ("20 eval seasons", 20, False, "⛔ UNREACHABLE — an a fortiori bound only"),
)
FOLD_COUNTS: tuple[int, ...] = (3, 4, 5, 6, 8, 10, 12, 14, 16, 20)
#: a fold thinner than this is not a credible test block for this vertical
MIN_ROWS_PER_FOLD = 200
#: modelled weeks per season (`weekly_projection.TEST_BLOCKS` splits each season into H1 = weeks
#: 1–9 and H2 = weeks 10+). Used only to express a grid point's BLOCK LENGTH.
MODELLED_WEEKS_PER_SEASON = 18
#: ⭐ A GRANULARITY FLOOR, declared before the sweep. `weekly_projection.PURGE_WEEKS` is 2, so a
#: block shorter than this makes the purge comparable to the block itself and the expanding-window
#: design stops being credible. A point below it is marked INFEASIBLE with its reason — ⛔ never
#: silently dropped, because a silently-dropped grid point is a coverage claim nobody can audit.
MIN_BLOCK_WEEKS = 4.0
REPS = 2000
BASE_SEED = 20260820


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Reading the published record
# ══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Observed:
    """NF-W8-0c's published per-fold QB level biases — the EFFECT, held fixed."""

    folds: tuple[str, ...]
    bias: dict[str, np.ndarray]          # arm -> per-fold level bias (PPR)
    n_rows: np.ndarray                   # per-fold QB test rows
    sd_err: np.ndarray                   # per-fold per-row error SD (PPR)

    @property
    def shifts(self) -> dict[str, np.ndarray]:
        """`s_a,f = b_a,f − b_I,f` — the paired level shift, which carries ~no test-row noise."""
        return {a: self.bias[a] - self.bias[INCUMBENT] for a in REAL_ARMS}


def load_observed(record: dict) -> Observed:
    """Read the evaluable-fold QB biases out of NF-W8-0c's JSON record.

    ⚠️ Reads the EVALUABLE folds family B actually scored, not all eight — scoring the frontier on
    a fold family B excluded would compare a different population to the recorded DSR."""
    folds = tuple(record["family_b"]["evaluable_folds"])
    if len(folds) < 3:
        raise ValueError(f"the record carries {len(folds)} evaluable folds; DSR needs ≥3 — a "
                         f"frontier anchored on fewer would have no observed DSR to reproduce")
    by_label = {f["label"]: f for f in record["fold_results"]}
    missing = [f for f in folds if f not in by_label]
    if missing:
        raise KeyError(f"evaluable folds {missing} are absent from `fold_results` — the record is "
                       f"internally inconsistent and must not be silently partially read")
    arms = (INCUMBENT, *REAL_ARMS)
    bias = {a: np.asarray([by_label[f]["qb"]["arms"][a]["bias"]["bias"] for f in folds], float)
            for a in arms}
    n_rows = np.asarray([by_label[f]["qb"]["arms"][INCUMBENT]["bias"]["n"] for f in folds], float)
    sd_err = np.asarray([by_label[f]["qb"]["arms"][INCUMBENT]["bias"]["sd_err"] for f in folds],
                        float)
    return Observed(folds=folds, bias=bias, n_rows=n_rows, sd_err=sd_err)


def delta_series(bias: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """`δ_a = |b_I| − |b_a|` for every declared arm — the statistic the registered gate deflates."""
    abs_inc = np.abs(bias[INCUMBENT])
    return {a: abs_inc - np.abs(bias[a]) for a in REAL_ARMS}


def sharpes(deltas: dict[str, np.ndarray]) -> np.ndarray:
    """Each declared arm's per-fold Sharpe, in `REAL_ARMS` order — the DSR trial population."""
    out = []
    for a in REAL_ARMS:
        d = np.asarray(deltas[a], float)
        sd = float(np.nanstd(d, ddof=1))
        out.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    return np.asarray(out, float)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Split-field DSR (`V` from one set, `n_trials` from another) — the DSR-CONV shape
# ══════════════════════════════════════════════════════════════════════════════════════════════
def synth_trials_for_split_field(v_sharpes, n_trials: int) -> np.ndarray:
    """A length-`n_trials` vector whose SAMPLE sd equals `std(v_sharpes, ddof=1)`.

    ⭐ WHY THIS EXISTS RATHER THAN A SECOND DSR IMPLEMENTATION. DSR-CONV's convention is "the
    excluded arm leaves `V` but STAYS in `n_trials`", and `nf1_1_model.deflated_sharpe` derives
    both from one array. Feeding it a synthetic vector with the reduced set's dispersion and the
    full field's LENGTH expresses exactly that split **through the gate's own function**, so the
    diagnostic and the gate can never drift apart (NF-W7k / NF-C0e).

    ⚠️ The vector is not a claim about any arm's Sharpe — it is a carrier for `(V, N)` and nothing
    else. `deflated_sharpe` reads only `std(ddof=1)` and `len` from it, which is asserted by the
    guard's identity pin (equal sets ⇒ byte-identical DSR)."""
    s = np.asarray(v_sharpes, float)
    s = s[np.isfinite(s)]
    n = int(n_trials)
    if len(s) < 2:
        raise ValueError(f"a split-field `V` needs ≥2 retained trial Sharpes, got {len(s)} — with "
                         f"fewer the dispersion is undefined and the benchmark would silently "
                         f"fall back to 0, i.e. NO deflation at all (NF1.7 (a))")
    if n < 2:
        raise ValueError(f"n_trials must be ≥2, got {n}")
    if n < len(s):
        raise ValueError(f"n_trials {n} is below the retained set size {len(s)} — a field cannot "
                         f"be smaller than the arms kept in its own dispersion")
    base = np.arange(n, dtype=float)
    base -= base.mean()
    return base * (float(s.std(ddof=1)) / float(base.std(ddof=1)))


def dsr_split_field(winner_delta, v_sharpes, n_trials: int) -> float | None:
    """DSR with `V` measured over `v_sharpes` and multiplicity charged at `n_trials`."""
    return M14.deflated_sharpe(np.asarray(winner_delta, float),
                               synth_trials_for_split_field(v_sharpes, n_trials))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §2 — the level decomposition (NF-W8-0c's memo, recomputed from the published record)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def level_decomposition(obs: Observed) -> dict:
    """Split the identity's fold-to-fold bias SD into within-fold sampling SE vs the excess.

    The excess is reported SIGNED-SAFE but its provenance is stated: `σ_row²/m` is KNOWN (measured
    per fold), so the excess is a residual, and a residual at or below zero would say the observed
    fold spread is no larger than row sampling alone — a real reading, never clamped away silently
    (NF-W7k's `het_var` discipline)."""
    b = obs.bias[INCUMBENT]
    within_var = obs.sd_err ** 2 / obs.n_rows
    obs_var = float(b.var(ddof=1))
    mean_within = float(within_var.mean())
    excess = obs_var - mean_within
    return {
        "observed_fold_sd": math.sqrt(obs_var),
        "mean_within_fold_se": float(np.sqrt(within_var).mean()),
        "mean_within_fold_var": mean_within,
        "excess_var": excess,
        "excess_sd": math.sqrt(excess) if excess > 0 else None,
        "excess_is_non_positive": bool(excess <= 0.0),
        "sampling_share_of_fold_variance": mean_within / obs_var if obs_var > 0 else None,
        "sigma_row": float(np.sqrt(float((obs.sd_err ** 2).mean()))),
        "mean_rows_per_fold": float(obs.n_rows.mean()),
    }


#: the declared availability levels the paired bound is evaluated over (see `paired_noise_bound`)
PI_BAR_GRID: tuple[float, ...] = (1.0, 0.8, 0.6, 0.4)


def paired_noise_bound(obs: Observed) -> dict:
    """The STRUCTURAL bound on how much test-row sampling error survives into the PAIRED delta.

    `b_I,f − b_a,f` depends only on the two POINT vectors — **the realized `y` cancels exactly** —
    and `cond_shift` adds `S·alive` to every draw, so every row's point difference `dᵢ` lies in
    `[0, S]` (a non-negative shift raises every grid quantile weakly, and by at most `S`). By
    Bhatia–Davis, a variable on `[0, S]` with mean `μ` has `Var ≤ μ(S − μ)`, and the fold's OBSERVED
    level shift IS that mean (`μ = s_f`). So the paired difference's row SD is bounded by
    `√(s_f·(S − s_f))`.

    ⚠️ `S` is the raw shift PARAMETER and is not in the published record; only `s_f = S·π̄` is. An
    earlier draft asserted `SD ≤ |s_f|/2`, which is only exact at `π̄ = 1` and is NOT rigorous
    otherwise. Rather than assume a `π̄`, the bound is EVALUATED over a declared grid — and it stays
    under 1% of the level's sampling variance across the whole of it, which is what makes the
    finding robust instead of contingent."""
    s = np.abs(obs.shifts[WINNER])
    worst_shift = float(s.max())
    sigma_row = float(np.sqrt(float((obs.sd_err ** 2).mean())))
    ladder = []
    for pi_bar in PI_BAR_GRID:
        if not 0.0 < pi_bar <= 1.0:
            raise ValueError(f"π̄ must lie in (0, 1], got {pi_bar}")
        raw_shift = worst_shift / pi_bar
        sd = math.sqrt(max(worst_shift * (raw_shift - worst_shift), 0.0))
        ladder.append({"pi_bar": float(pi_bar), "raw_shift_ppr": raw_shift,
                       "paired_row_sd_bound_ppr": sd,
                       "share_of_level_variance": (sd / sigma_row) ** 2})
    worst = max(ladder, key=lambda r: r["share_of_level_variance"])
    return {
        "worst_fold_shift_ppr": worst_shift,
        "level_row_sd_ppr": sigma_row,
        "pi_bar_ladder": ladder,
        "worst_case_pi_bar": worst["pi_bar"],
        "paired_row_sd_bound_ppr": worst["paired_row_sd_bound_ppr"],
        "paired_share_of_level_variance_bound": worst["share_of_level_variance"],
        "note": ("Bhatia–Davis on a per-row point difference confined to [0, S]; evaluated over a "
                 "DECLARED π̄ grid because S itself is not in the published record"),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §3 — the LOCKSTEP ladder
# ══════════════════════════════════════════════════════════════════════════════════════════════
def scale_dispersion(series: np.ndarray, c: float) -> np.ndarray:
    """Multiply a series' deviations by `c`, holding the mean fixed (NF-W7k's `rescale_to_sd`
    shape: every standardized moment `deflated_sharpe` reads is preserved; only dispersion moves)."""
    d = np.asarray(series, float)
    mu = float(d.mean())
    return mu + (d - mu) * float(c)


def lockstep_ladder(deltas: dict[str, np.ndarray], winner: str = WINNER,
                    factors: tuple[float, ...] = LOCKSTEP_FACTORS) -> list[dict]:
    """The gate re-read with EVERY arm's dispersion multiplied by the same `c`.

    This is the proposition made arithmetic: `SR` and `SR0` move together, so `sign(SR − SR0)` is
    fixed and a proportional variance lever cannot rescue an `SR ≤ SR0` refusal."""
    from quant_sports_intel_models.football.nfl.fantasy.fp_mc_variance import sr0_of

    rows = []
    for c in factors:
        scaled = {a: scale_dispersion(deltas[a], c) for a in REAL_ARMS}
        srs = sharpes(scaled)
        rows.append({
            "dispersion_factor": float(c),
            "winner_sharpe": float(srs[REAL_ARMS.index(winner)]),
            "sr0": float(sr0_of(srs)),
            "sr_minus_sr0": float(srs[REAL_ARMS.index(winner)] - sr0_of(srs)),
            "dsr": M14.deflated_sharpe(scaled[winner], srs),
        })
    return rows


def lockstep_is_live(rows: list[dict]) -> bool:
    """G2 — the ladder must actually MOVE the arithmetic, or it pins nothing (NF1.7 (a))."""
    srs = [r["winner_sharpe"] for r in rows]
    return len(srs) >= 2 and all(abs(b) > abs(a) + 1e-9 for a, b in zip(srs, srs[1:]))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §4 — the design model and the frontier
# ══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class DesignModel:
    """The generative model of a per-fold bias panel — calibrated to the PUBLISHED record."""

    mu_bar: float                 # the identity's pooled level
    sigma_u: float                # between-fold (regime) SD of the true level
    sigma_row: float              # per-row error SD
    rows_per_fold_0: float        # the design σ_u was estimated AT
    shift_matrix: np.ndarray      # (n_folds, n_arms) observed shifts, bootstrapped JOINTLY
    arms: tuple[str, ...] = field(default=REAL_ARMS)


def fit_design_model(obs: Observed) -> DesignModel:
    dec = level_decomposition(obs)
    return DesignModel(
        mu_bar=float(obs.bias[INCUMBENT].mean()),
        sigma_u=float(math.sqrt(max(dec["excess_var"], 0.0))),
        sigma_row=float(dec["sigma_row"]),
        rows_per_fold_0=float(dec["mean_rows_per_fold"]),
        shift_matrix=np.column_stack([obs.shifts[a] for a in REAL_ARMS]),
    )


def _law_factor(model: DesignModel, rows_per_fold: float, law: str) -> float:
    """The multiplier applied to the NON-sampling fold-scale spread at a new fold size.

    `persistent` — regime variation is real and does not average away (1.0).
    `averaging`  — it is white below the fold and falls as `1/m` (`√(m₀/m)`), the reading most
                   FAVOURABLE to the rows/fold lever. Both are run; neither is asserted (prereg §4).
    """
    if law == "persistent":
        return 1.0
    if law == "averaging":
        return math.sqrt(model.rows_per_fold_0 / float(rows_per_fold))
    raise ValueError(f"unknown scaling law `{law}` — the declared laws are {LAWS}; an unrecognised "
                     f"law must RAISE, never silently default to one of them")


def simulate_design(model: DesignModel, rows_per_fold: float, n_folds: int, law: str,
                    *, reps: int = REPS, seed: int = BASE_SEED,
                    v_exclude: tuple[str, ...] = ()) -> dict:
    """Projected DSR at design `(rows_per_fold, n_folds)`, holding the EFFECT fixed.

    `v_exclude` names arms removed from the deflation dispersion `V` while STAYING in `n_trials`
    (the DSR-CONV shape). ⛔ Passing it does NOT change any live gate — it is the diagnostic the
    forward recommendation is stated against, and the registered-gate columns are always computed
    with `v_exclude=()` beside it."""
    if n_folds < 3:
        raise ValueError(f"DSR is UNDEFINED below 3 observations; got {n_folds} folds — an "
                         f"undefined statistic is never a pass (NF1.7 (a))")
    bad = [a for a in v_exclude if a not in REAL_ARMS]
    if bad:
        raise KeyError(f"cannot exclude {bad} from V — not in the declared field {REAL_ARMS}")
    keep = [i for i, a in enumerate(REAL_ARMS) if a not in v_exclude]
    if len(keep) < 2:
        raise ValueError("excluding those arms leaves <2 in V; the dispersion would be undefined "
                         "and the benchmark would collapse to 0 (no deflation at all)")

    rng = np.random.default_rng(seed)
    k = _law_factor(model, rows_per_fold, law)
    sd_u = model.sigma_u * k
    sd_eps = model.sigma_row / math.sqrt(float(rows_per_fold))
    S, s_bar = model.shift_matrix, model.shift_matrix.mean(axis=0)
    n_obs_folds = S.shape[0]
    w = REAL_ARMS.index(WINNER)

    dsr = np.empty(reps)
    sr_w = np.empty(reps)
    sr0 = np.empty(reps)
    for r in range(reps):
        b_inc = rng.normal(model.mu_bar, sd_u, n_folds) + rng.normal(0.0, sd_eps, n_folds)
        # ⭐ bootstrap the shift ROWS jointly across arms: the cross-arm correlation of the shifts
        # is what sets `std(trial Sharpes)`, so drawing arms independently would fabricate `SR0`.
        draw = S[rng.integers(0, n_obs_folds, n_folds)]
        shifts = s_bar + (draw - s_bar) * k
        abs_inc = np.abs(b_inc)
        d = np.column_stack([abs_inc - np.abs(b_inc + shifts[:, j])
                             for j in range(len(REAL_ARMS))])
        sd = d.std(axis=0, ddof=1)
        srs = np.where(sd > 1e-12, d.mean(axis=0) / np.where(sd > 1e-12, sd, 1.0), 0.0)
        v = (M14.deflated_sharpe(d[:, w], srs) if not v_exclude
             else dsr_split_field(d[:, w], srs[keep], len(REAL_ARMS)))
        dsr[r] = v if v is not None else np.nan
        sr_w[r] = srs[w]
        sr0[r] = _sr0_from(srs[keep], len(REAL_ARMS))
    med = float(np.nanmedian(dsr))
    return {
        "rows_per_fold": float(rows_per_fold), "n_folds": int(n_folds), "law": law,
        "v_excluded": list(v_exclude),
        "dsr_median": med, "dsr_p05": float(np.nanpercentile(dsr, 5)),
        "dsr_p95": float(np.nanpercentile(dsr, 95)),
        "p_clears": float(np.nanmean(dsr >= DSR_MIN)),
        "clears_on_median": bool(med >= DSR_MIN),
        "sr_median": float(np.nanmedian(sr_w)), "sr0_median": float(np.nanmedian(sr0)),
        "p_sr_exceeds_sr0": float(np.nanmean(sr_w > sr0)),
        "reps": int(reps),
    }


def _sr0_from(v_sharpes: np.ndarray, n_trials: int) -> float:
    """`SR0` for a possibly-split field, in the SAME closed form the gate uses internally.

    ⚠️ Reporting only — every DSR VERDICT still goes through `deflated_sharpe` (NF-W7k)."""
    from scipy.stats import norm

    s = np.asarray(v_sharpes, float)
    s = s[np.isfinite(s)]
    if len(s) < 2 or s.std(ddof=1) <= 0 or n_trials < 2:
        return 0.0
    em = 0.5772156649015329
    n = int(n_trials)
    return float(s.std(ddof=1) * ((1 - em) * norm.ppf(1 - 1 / n)
                                  + em * norm.ppf(1 - 1 / (n * math.e))))


def window_rows(eval_seasons: int) -> int:
    """Modelled QB rows in an evaluation window of `eval_seasons` seasons (prereg §5)."""
    return int(round(eval_seasons * QB_ROWS_PER_SEASON))


def frontier(model: DesignModel, *, windows=WINDOWS, fold_counts=FOLD_COUNTS, laws=LAWS,
             reps: int = REPS, seed: int = BASE_SEED,
             v_exclude: tuple[str, ...] = ()) -> list[dict]:
    """The (rows/fold × fold-count) grid. On a fixed window the two trade: `m = N / T`."""
    rows: list[dict] = []
    for w_i, (label, seasons, feasible, why) in enumerate(windows):
        n_rows = window_rows(seasons)
        for t_i, t in enumerate(fold_counts):
            m = n_rows / t
            if m < MIN_ROWS_PER_FOLD:
                continue
            block_weeks = MODELLED_WEEKS_PER_SEASON * seasons / t
            granular = block_weeks >= MIN_BLOCK_WEEKS
            note = why if granular else (
                f"{why}; ⛔ ALSO granularity-infeasible — a {block_weeks:.1f}-week block against a "
                f"{2}-week purge")
            for l_i, law in enumerate(laws):
                r = simulate_design(model, m, t, law, reps=reps,
                                    seed=seed + 1000 * w_i + 37 * t_i + l_i,
                                    v_exclude=v_exclude)
                r.update({"window": label, "eval_seasons": seasons, "window_rows": n_rows,
                          "block_weeks": float(block_weeks),
                          "granularity_ok": bool(granular),
                          "feasible": bool(feasible and granular), "feasibility_note": note})
                rows.append(r)
    return rows


def best_point(rows: list[dict], *, feasible_only: bool = True) -> dict | None:
    """The grid point with the highest MEDIAN projected DSR.

    ⭐ The verdict binds on the MEDIAN, never on `P(clear)` (prereg §3): a design that only
    sometimes gets a lucky draw has not cleared — that is the selection bias DSR exists to
    deflate."""
    pool = [r for r in rows if r["feasible"]] if feasible_only else list(rows)
    return max(pool, key=lambda r: r["dsr_median"]) if pool else None


def verdict(rows: list[dict]) -> dict:
    """(a) a FEASIBLE point clears the bar on the median · (b) none does ⇒ the gate is
    mis-specified for this effect at this design, and the remedy is a FORWARD gate-design change
    (⛔ never a post-hoc relaxation — E2.1-r)."""
    feas = best_point(rows, feasible_only=True)
    anyp = best_point(rows, feasible_only=False)
    if feas is None:
        raise ValueError("the frontier contains no FEASIBLE grid point — a verdict computed over "
                         "an empty feasible set would pass on nothing (NF1.7 (a))")
    clears = bool(feas["dsr_median"] >= DSR_MIN)
    return {
        "state": "FEASIBLE_DESIGN_CLEARS" if clears else "NO_FEASIBLE_DESIGN_CLEARS",
        "answer": "a" if clears else "b",
        "best_feasible": feas,
        "best_anywhere": anyp,
        "bar": DSR_MIN,
        "n_grid_points": len(rows),
        "n_feasible_points": sum(1 for r in rows if r["feasible"]),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §5 — WHERE the deflation benchmark's dispersion comes from
# ══════════════════════════════════════════════════════════════════════════════════════════════
def v_attribution(deltas: dict[str, np.ndarray]) -> list[dict]:
    """Each declared arm's share of `Var(trial Sharpes)` — the quantity `SR0` deflates against.

    ⭐ This is the diagnostic that names the mechanism. `SR0 = √V · z(N)`, and `V` is a SAMPLE
    variance over the field's Sharpes, so ONE arm can dominate the bar every other arm must clear.
    Reported for every arm, not just the largest — a share table that only prints the culprit
    cannot show that the rest are unremarkable."""
    srs = sharpes(deltas)
    dev = (srs - srs.mean()) ** 2
    tot = float(dev.sum())
    return [{"arm": a, "sharpe": float(s), "share_of_var_trial_sharpes":
             (float(dv / tot) if tot > 0 else None)}
            for a, s, dv in zip(REAL_ARMS, srs, dev)]


def alternative_statistic_field(bias: dict[str, np.ndarray]) -> list[dict]:
    """The Sharpe field + DSR under alternative SELECTION statistics — a labelled DIAGNOSTIC.

    ⛔ NOT a re-read of NF-W8-0c. Re-scoring a failed gate on a better-looking statistic is the
    E2.1-r inversion in its most literal form. These rows exist so that a FORWARD recommendation
    can say which alternatives were tested and **which of them LOST**, rather than quietly
    proposing the one that happened to look best.

    - `abs_delta` — the registered statistic `|b_I| − |b_a|`.
    - `squared_delta` — `b_I² − b_a²`, the smooth (kink-free) sibling. The `|·|` kink is what
      injects the level's full sampling noise into exactly the folds where the correction
      over-shoots, so removing it is the obvious candidate; it is scored here rather than argued.
    """
    variants = {
        "abs_delta (REGISTERED)": lambda a: np.abs(bias[INCUMBENT]) - np.abs(bias[a]),
        "squared_delta (kink-free)": lambda a: bias[INCUMBENT] ** 2 - bias[a] ** 2,
    }
    out = []
    for name, fn in variants.items():
        d = {a: fn(a) for a in REAL_ARMS}
        srs = sharpes(d)
        out.append({"statistic": name,
                    "sharpes": {a: float(s) for a, s in zip(REAL_ARMS, srs)},
                    "sr0": _sr0_from(srs, len(REAL_ARMS)),
                    "winner_sharpe": float(srs[REAL_ARMS.index(WINNER)]),
                    "dsr": M14.deflated_sharpe(d[WINNER], srs)})
    return out
