"""NF-W7k — the Monte-Carlo variance decomposition of a §0.5 per-fold delta, and the DSR CEILING.

NF-W7j left QB refused on `dsr_ok` alone and named exactly ONE remaining lever: a lower-variance
DESIGN. NF-W7f had already closed the other two — more folds (`n` enters DSR only through
`√(n−1)`, so it scales a positive gap and cannot create one) and a coherent narrower field (`V`
falls 8.8× and DSR still reaches only 0.174). What is left is Monte-Carlo error: every bank is a
quantile summary of 4,000 draws, so each per-fold CRPS — and therefore each per-fold delta — is a
NOISY estimate of the quantity the gate means to read.

⭐ THE INSTRUMENT'S POINT is that "would more draws clear the gate?" has an EXACT answer that costs
a fraction of the expensive re-run: re-score the SAME folds at several draw SEEDS, split the
per-fold delta's variance into a Monte-Carlo part (across-seed, WITHIN a fold) and a heterogeneity
part (across folds), and evaluate the gate at the LIMIT where the Monte-Carlo part is zero. That
limit is a CEILING: no draw count can do better. A ceiling below the bar closes the lever outright,
which is a decision more data can never overturn — `CONSTRAINT_REFUSED`'s shape (NF-D18), not
`POWER_LIMITED`'s.

⚠️ THE TRAP THIS MODULE IS BUILT AROUND — the winner is a MEMBER OF ITS OWN TRIAL FIELD. DSR
deflates against `SR0 = std(trial_sharpes) · z(N)`, and the winner's Sharpe is one of those trial
Sharpes. So shrinking Monte-Carlo error raises the winner's Sharpe AND `SR0` together, and whether
the gap closes is arithmetic, not intuition. That is precisely why the pre-registration makes the
CEILING bind over the "is the MC share large?" proxy (prereg §3.1): a large MC share is fully
compatible with a ceiling that never clears.

⛔ EVERY DSR IN THIS MODULE IS COMPUTED BY THE HARNESS'S OWN `nf1_1_model.deflated_sharpe`, BY
IDENTITY. A re-implementation would let the projection and the gate drift apart, which is the
NF-C0e "the check validates its own copy of the logic" class — the same defect a RED proof caught
in `mixture_leg_draws`, and the reason that function is one function.
"""

from __future__ import annotations

import math

import numpy as np

from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14

STORY = "NF-W7k"
PREDECESSOR = "NF-W7j"

#: NF-W7f's assembly seed — the BASE. Every other seed is `BASE_SEED + k * SEED_STRIDE`.
BASE_SEED = 20260818
#: ⭐ Stream spacing. The assembly draws from `seed + row_block_start` (block starts are multiples
#: of 256) and the availability Bernoulli from `seed + 1_000_000 + row_block_start`. A stride far
#: above BOTH offsets makes it impossible for two "different" seeds to share a stream — which would
#: report ZERO Monte-Carlo error and drive a FALSE STOP, the dangerous direction here.
SEED_STRIDE = 7_000_003
N_SEEDS = 5
SEEDS: tuple[int, ...] = tuple(BASE_SEED + k * SEED_STRIDE for k in range(N_SEEDS))

#: (primary, scaling-control) draw counts — the control exists to MEASURE the 1/D law the whole
#: projection rests on rather than assume it (prereg §3 G2).
DRAWS_PRIMARY = 4000
DRAWS_CONTROL = 1000
DRAW_LEVELS: tuple[int, ...] = (DRAWS_PRIMARY, DRAWS_CONTROL)

#: the registered admissible band for `σ²_MC(1000) / σ²_MC(4000)` — nominal 4.0
#:
#: ⭐ WHY [2, 8], MEASURED RATHER THAN ASSERTED. Each `σ²_MC` pools `n_folds × (n_seeds − 1)` df,
#: so the observed ratio is `true_ratio × F(df, df)` and the band's meaning depends entirely on
#: the DESIGN. At this story's design — 8 folds × 5 seeds = **32 df** — a true 1/D law lands in
#: this band **94.6%** of the time (90% of observations fall in [2.22, 7.22]), so the band is a
#: real test that a correct law passes and a flat one (ratio ≈ 1) fails.
#:
#: ⚠️ AND THE COROLLARY THAT MATTERS FOR ANY SMALLER PROBE: at 2 folds × 2 seeds = **2 df**, a
#: true ratio of 4 produces observations spanning **[0.21, 76.0]** and lands in band only **33%**
#: of the time. A cheap pre-flight at that size is therefore UNINFORMATIVE about G2 — it cannot
#: distinguish a broken law from a correct one, and reading its scatter as evidence against the
#: extrapolation would be the "measurement whose resolution is below the effect" error (MH2's
#: underpowered ≠ absent, one statistic over). Judge G2 only at the registered design.
SCALING_BAND: tuple[float, float] = (2.0, 8.0)
#: the registered Phase-B draw ladder and its cap (prereg §3)
DRAW_LADDER: tuple[int, ...] = (16_000, 64_000, 256_000)

_REPRO_TOL = 1e-9


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The decomposition
# ══════════════════════════════════════════════════════════════════════════════════════════════
def decompose(delta_by_fold: dict[str, list[float]]) -> dict:
    """Split a per-fold delta's variance into Monte-Carlo and heterogeneity components.

    `delta_by_fold[fold] = [δ at seed 1, δ at seed 2, ...]` — the SAME fold re-scored at several
    draw seeds with everything else held byte-identical, so the only thing that moved is the RNG.

    - `mc_var` pools the WITHIN-fold across-seed variance over folds. It is the sampling variance
      of a **one-seed** delta estimate — the error NF-W7f's published numbers actually carry.
    - `between_var` is the across-fold variance of the per-fold seed MEAN. It carries heterogeneity
      PLUS a residual `mc_var / S` (the seed mean is itself an average of S noisy draws).
    - `het_var = between_var − mc_var / S` is therefore the honest heterogeneity estimate.

    ⚠️ `het_var` is returned SIGNED. A negative estimate is a real reading — it says the observed
    fold-to-fold spread is no larger than draw noise alone would produce — and clamping it silently
    to zero would manufacture a ceiling of `+∞` and a fake `FUND`. The caller sees the sign.
    """
    folds = sorted(delta_by_fold)
    if len(folds) < 2:
        raise ValueError(f"the decomposition needs ≥2 folds, got {len(folds)} — a single fold has "
                         f"no across-fold spread to compare the Monte-Carlo error against")
    counts = {len(delta_by_fold[f]) for f in folds}
    if counts != {min(counts)} or min(counts) < 2:
        raise ValueError(f"every fold must carry the SAME number of seeds and at least 2; got "
                         f"{ {f: len(delta_by_fold[f]) for f in folds} } — an unbalanced pool "
                         f"would weight folds by how often they happened to be scored")
    n_seeds = min(counts)

    per_fold_var = {f: float(np.var(np.asarray(delta_by_fold[f], dtype=float), ddof=1))
                    for f in folds}
    mc_var = float(np.mean([per_fold_var[f] for f in folds]))
    seed_mean = {f: float(np.mean(delta_by_fold[f])) for f in folds}
    means = np.asarray([seed_mean[f] for f in folds], dtype=float)
    between_var = float(np.var(means, ddof=1))
    het_var = between_var - mc_var / n_seeds
    single_seed_var = het_var + mc_var
    return {
        "folds": folds,
        "n_seeds": n_seeds,
        "per_fold_across_seed_var": per_fold_var,
        "per_fold_across_seed_sd": {f: math.sqrt(v) for f, v in per_fold_var.items()},
        "seed_mean_by_fold": seed_mean,
        "mc_var": mc_var,
        "mc_sd": math.sqrt(mc_var),
        "between_var": between_var,
        "between_sd": math.sqrt(between_var),
        "het_var": het_var,                       # ⚠️ SIGNED — never clamped here
        "het_sd": math.sqrt(het_var) if het_var > 0.0 else None,
        "het_var_is_negative": bool(het_var < 0.0),
        "single_seed_var": single_seed_var,
        "mc_share_of_single_seed_var": (mc_var / single_seed_var) if single_seed_var > 0 else None,
        "mean_delta": float(np.mean(means)),
    }


def projected_sd(mc_var: float, het_var: float, k: float) -> float:
    """A one-seed delta's sd at draw multiplier `k` (relative to the draw count `mc_var` was
    measured at). `k = inf` is the CEILING: all Monte-Carlo error removed.

    Monte-Carlo variance falls as 1/draws — an assumption the pre-registration REFUSES to take on
    faith and measures instead (`scaling_check`, prereg §3 G2)."""
    if k <= 0:
        raise ValueError(f"draw multiplier must be positive, got {k}")
    v = max(het_var, 0.0) + (0.0 if math.isinf(k) else mc_var / k)
    return math.sqrt(max(v, 0.0))


def scaling_check(mc_var_control: float, draws_control: int,
                  mc_var_primary: float, draws_primary: int,
                  band: tuple[float, float] = SCALING_BAND) -> dict:
    """MEASURE the 1/D law rather than assume it. The whole projection — and therefore the whole
    decision — rests on Monte-Carlo variance falling as 1/draws, so it is checked against a second
    draw count at a registered band. Outside the band the story issues NO decision (prereg §3 G2):
    a wrong extrapolation could close the lever on a distribution that never obeyed it."""
    expected = draws_primary / draws_control
    if mc_var_primary <= 0.0:
        return {"evaluable": False, "holds": False,
                "reason": f"the primary-draw Monte-Carlo variance is {mc_var_primary} — a ratio "
                          f"against it is undefined, so the 1/D law is UNEVALUATED and can never "
                          f"be scored as holding (NF1.7 (a))"}
    ratio = mc_var_control / mc_var_primary
    return {"evaluable": True, "ratio": ratio, "expected": expected, "band": list(band),
            "holds": bool(band[0] <= ratio <= band[1]),
            "mc_var_control": mc_var_control, "mc_var_primary": mc_var_primary,
            "draws_control": draws_control, "draws_primary": draws_primary}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The projection into the gate's own arithmetic
# ══════════════════════════════════════════════════════════════════════════════════════════════
def rescale_to_sd(series: np.ndarray, target_sd: float) -> np.ndarray:
    """Rescale a delta series' centred deviations to `target_sd`, holding the MEAN fixed.

    ⭐ This preserves every STANDARDIZED shape moment — skew and kurtosis, both of which
    `deflated_sharpe` reads through its `denom` term — so the projected series differs from the
    observed one in exactly one respect: its dispersion. Anything else would be projecting a
    different object than the one being deflated."""
    d = np.asarray(series, dtype=float)
    mu = float(d.mean())
    sd = float(d.std(ddof=1))
    if sd <= 1e-15:
        return d.copy()
    return mu + (d - mu) * (target_sd / sd)


def sr0_of(trial_sharpes) -> float:
    """The deflation benchmark `SR0`, in the SAME closed form `deflated_sharpe` uses internally.

    ⚠️ Exposed only so the record can PRINT the bar beside the Sharpe; every DSR VERDICT in this
    module still goes through `deflated_sharpe` by identity. Kept beside the projection because the
    load-bearing subtlety lives here: the winner is one of the trials this dispersion is taken
    over, so removing Monte-Carlo error moves the Sharpe and the bar TOGETHER."""
    from scipy.stats import norm

    s = np.asarray(trial_sharpes, dtype=float)
    s = s[np.isfinite(s)]
    if len(s) < 2 or s.std(ddof=1) <= 0:
        return 0.0
    em = 0.5772156649015329
    n = len(s)
    return float(s.std(ddof=1) * ((1 - em) * norm.ppf(1 - 1 / n)
                                  + em * norm.ppf(1 - 1 / (n * np.e))))


def project_gate(base_deltas: dict[str, np.ndarray], target_sd: dict[str, float],
                 winner: str) -> dict:
    """Re-run the gate's DSR arithmetic with every arm's delta series rescaled to `target_sd`.

    `base_deltas[arm]` is that arm's OBSERVED per-fold `(best_foil − arm)` series — NF-W7f's own
    object. Passing `target_sd` equal to the observed sds is the registered NO-OP identity: it must
    return NF-W7f's recorded DSR exactly (prereg §3.2)."""
    if winner not in base_deltas:
        raise KeyError(f"the winner `{winner}` is not among the scored arms {sorted(base_deltas)} "
                       f"— a projection whose winner is absent would deflate a different arm")
    if set(target_sd) != set(base_deltas):
        raise ValueError(f"target sds cover {sorted(target_sd)} but the arms are "
                         f"{sorted(base_deltas)} — every arm in the field must be projected, or "
                         f"`SR0` would mix projected and unprojected trials")
    # ⚠️ A DEGENERATE TARGET SD IS UNBOUNDED, NOT ZERO — and conflating the two was a real defect a
    # glue proof over the live path caught. When `het_var` comes out ≤ 0 the ceiling's target sd is
    # 0, and a zero-dispersion series with a positive mean has an INFINITE Sharpe. Reading it
    # through the usual `sd > 1e-12 else 0.0` guard silently reported Sharpe **0.0** — i.e. the
    # single most favourable case for the lever was rendered as the least favourable one, which
    # would have driven a FALSE STOP on exactly the folds where the lever is most alive. It is now
    # named, and the caller decides what an unbounded ceiling means (it cannot REFUSE).
    degenerate = sorted(a for a in target_sd if target_sd[a] <= 1e-15)
    proj = {a: rescale_to_sd(np.asarray(d, dtype=float), target_sd[a])
            for a, d in base_deltas.items()}
    srs = []
    for a in sorted(proj):
        d = proj[a]
        sd = float(np.nanstd(d, ddof=1))
        srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    w = proj[winner]
    w_sd = float(np.nanstd(w, ddof=1))
    if winner in degenerate:
        return {
            "dsr": None, "winner_sharpe": None, "sr0": sr0_of(srs), "unbounded": True,
            "degenerate_arms": degenerate,
            "reason": f"the projected dispersion of `{winner}` is zero, so its Sharpe is unbounded "
                      f"— the ceiling is NOT bounded away from the bar and cannot refuse the "
                      f"lever. ⛔ Reporting this as Sharpe 0 would invert the most favourable case "
                      f"into the least favourable one.",
            "trial_sharpes": {a: (float(np.nanmean(proj[a]))
                                  / float(np.nanstd(proj[a], ddof=1))
                                  if float(np.nanstd(proj[a], ddof=1)) > 1e-12 else 0.0)
                              for a in sorted(proj)},
            "target_sd": dict(target_sd), "p_one_sided": M14.onesided_paired_pvalue(w)}
    return {
        "dsr": M14.deflated_sharpe(w, np.asarray(srs)),
        "winner_sharpe": (float(np.nanmean(w)) / w_sd) if w_sd > 1e-12 else 0.0,
        "sr0": sr0_of(srs), "unbounded": False, "degenerate_arms": degenerate,
        "trial_sharpes": {a: (float(np.nanmean(proj[a]))
                              / float(np.nanstd(proj[a], ddof=1))
                              if float(np.nanstd(proj[a], ddof=1)) > 1e-12 else 0.0)
                          for a in sorted(proj)},
        "target_sd": dict(target_sd),
        "p_one_sided": M14.onesided_paired_pvalue(w),
    }


def sd_ladder(decomps: dict[str, dict], k: float) -> dict[str, float]:
    """Every arm's projected one-seed sd at draw multiplier `k` (`inf` = the CEILING)."""
    return {a: projected_sd(d["mc_var"], d["het_var"], k) for a, d in decomps.items()}


def ceiling_report(base_deltas: dict[str, np.ndarray], decomps: dict[str, dict], winner: str,
                   ladder: tuple[int, ...] = DRAW_LADDER,
                   draws_primary: int = DRAWS_PRIMARY) -> dict:
    """The gate evaluated at k = 1 (the no-op identity), at each registered ladder rung, and at the
    CEILING k → ∞. Monotonicity of the winner's Sharpe in `k` is ASSERTED, not reported: removing
    noise can only raise `|SR|`, so a violation is a coding defect (prereg §3.3)."""
    observed_sd = {a: float(np.asarray(d, dtype=float).std(ddof=1)) for a, d in base_deltas.items()}

    # ⚠️ THE IDENTITY ROW IS NOT A POINT ON THE PROJECTION CURVE, and conflating the two was a real
    # defect the end-to-end guard caught. `observed_sd` is the BASE-SEED series' own sd; the curve
    # is built from the POOLED decomposition (`√(σ²_het + σ²_MC/k)`), estimated over all seeds. The
    # two are estimates of the same quantity but are not equal, so a monotonicity check that
    # included the identity row compared incomparable scales and RAISED on perfectly sound input.
    # The identity is reported (prereg §3.2 pins it against NF-W7f's recorded DSR); the curve is
    # what §3.3's monotonicity is a property OF.
    identity = {"label": "observed (no-op identity)", "draws": draws_primary, "k": None,
                "kind": "identity", **project_gate(base_deltas, observed_sd, winner)}
    curve: list[dict] = [
        {"label": f"{draws_primary:,} (reconstructed)", "draws": draws_primary, "k": 1.0,
         "kind": "reconstruction",
         **project_gate(base_deltas, sd_ladder(decomps, 1.0), winner)}]
    for d2 in ladder:
        k = d2 / draws_primary
        curve.append({"label": f"{d2:,} draws", "draws": d2, "k": k, "kind": "ladder",
                      **project_gate(base_deltas, sd_ladder(decomps, k), winner)})
    ceil = {"label": "ceiling (∞ draws)", "draws": None, "k": math.inf, "kind": "ceiling",
            **project_gate(base_deltas, sd_ladder(decomps, math.inf), winner)}
    curve.append(ceil)

    # an UNBOUNDED rung sits at +∞ by construction, so it can never violate monotonicity; it is
    # excluded from the comparison rather than being read as a 0 that would look like a collapse
    sharpes = [r["winner_sharpe"] for r in curve if r.get("winner_sharpe") is not None]
    if any(b < a - 1e-9 for a, b in zip(sharpes, sharpes[1:])):
        raise ValueError(f"the winner's projected Sharpe is not monotone in the draw count "
                         f"({sharpes}) — removing Monte-Carlo error can only raise |SR|, so this "
                         f"is a coding defect in the projection, not a finding (prereg §3.3)")
    # how well the pooled decomposition reconstructs the base-seed series it is projecting FROM —
    # a large gap would say the two estimates of the one-seed sd disagree, which is worth seeing
    recon = {a: {"observed_sd": observed_sd[a], "reconstructed_sd": projected_sd(
        decomps[a]["mc_var"], decomps[a]["het_var"], 1.0)} for a in sorted(base_deltas)}
    return {"rungs": [identity, *curve], "identity": identity, "ceiling": ceil,
            "observed_sd": observed_sd, "reconstruction": recon}


def bootstrap_ceiling_dsr(delta_by_fold_by_arm: dict[str, dict[str, list[float]]], winner: str,
                          n_boot: int = 2000, seed: int = BASE_SEED) -> dict:
    """A percentile CI95 on the CEILING DSR by resampling FOLDS with replacement.

    ⭐ Folds are the resampling unit, not seeds — the ceiling's uncertainty is dominated by having
    only 8 seasons to estimate the heterogeneity from, and a seed-level bootstrap would describe
    the Monte-Carlo error this statistic exists to REMOVE. Every arm is resampled on the SAME fold
    indices, so the field stays paired exactly as the gate reads it.

    ⚠️ The UPPER end is what the decision reads (prereg §3 G3): the honest question is whether the
    lever could clear the bar, so the gate is refused only when even the optimistic end fails."""
    arms = sorted(delta_by_fold_by_arm)
    folds = sorted(delta_by_fold_by_arm[winner])
    rng = np.random.default_rng(seed)
    vals: list[float] = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(folds), size=len(folds))
        picked = [folds[i] for i in idx]
        if len({f for f in picked}) < 2:
            continue                       # a resample collapsed onto one fold carries no spread
        try:
            dec = {a: decompose({f"{j}:{f}": delta_by_fold_by_arm[a][f]
                                 for j, f in enumerate(picked)}) for a in arms}
            base = {a: np.asarray([dec[a]["seed_mean_by_fold"][f"{j}:{f}"]
                                   for j, f in enumerate(picked)], dtype=float) for a in arms}
            g = project_gate(base, sd_ladder(dec, math.inf), winner)
        except (ValueError, KeyError):
            continue
        # ⛔ an unbounded resample must NOT be dropped: dropping exactly the resamples most
        # favourable to the lever would bias the CI's UPPER end — the end the decision reads —
        # downward, and the bias would grow with how alive the lever is. DSR is a probability, so
        # an unbounded Sharpe takes it to its supremum.
        if g.get("unbounded"):
            vals.append(1.0)
        elif g["dsr"] is not None:
            vals.append(float(g["dsr"]))
    if len(vals) < 100:
        return {"evaluable": False, "n_effective": len(vals),
                "reason": "fewer than 100 usable bootstrap resamples produced a DSR — the CI is "
                          "UNEVALUATED and must not be scored as passing or failing (NF1.7 (a))"}
    a = np.asarray(vals, dtype=float)
    return {"evaluable": True, "n_effective": len(a), "n_boot": n_boot,
            "lo": float(np.percentile(a, 2.5)), "median": float(np.percentile(a, 50)),
            "hi": float(np.percentile(a, 97.5))}


def required_mc_share_for_ceiling(base_deltas: dict[str, np.ndarray], winner: str,
                                  dsr_min: float, n_grid: int = 200,
                                  n_refine: int = 30) -> dict:
    """⭐ HOW MUCH Monte-Carlo error would the measurement have to FIND for the ceiling to clear?

    A SENSITIVITY, not the decision — it is arithmetic on NF-W7f's already-published series and
    measures nothing new. Its value is that it converts a vague "is the MC share large?" into a
    crisp number the run either exceeds or does not, fixed BEFORE the run reports anything.

    ⚠️ THE STATED ASSUMPTION: one COMMON absolute Monte-Carlo sd across the four arms. That is the
    right first-order shape — under common random numbers every arm's paired delta is a difference
    of two CRPS means over the same base normals, so the draw noise they carry is of similar
    absolute size — but it is an ASSUMPTION, and the real run measures each arm's `σ²_MC`
    separately. Read this as an orientation, never as a substitute.

    ⭐ Note what the sweep exposes: raising the common MC component lifts the WINNER's Sharpe and
    `SR0` TOGETHER, because the winner is one of the four trials whose dispersion sets the bar. So
    the ceiling is NOT monotonically easier as the assumed MC share grows, and a threshold may not
    exist at all."""
    sds = {a: float(np.asarray(d, dtype=float).std(ddof=1)) for a, d in base_deltas.items()}
    m_max = 0.999 * min(sds.values())          # keep every arm's heterogeneity strictly positive

    def at(m: float) -> dict | None:
        target = {a: math.sqrt(max(sds[a] ** 2 - m ** 2, 0.0)) for a in sds}
        if min(target.values()) <= 0.0:
            return None
        g = project_gate(base_deltas, target, winner)
        return {"mc_sd": m, "mc_share_of_winner_var": (m ** 2) / (sds[winner] ** 2),
                "dsr": g["dsr"], "winner_sharpe": g["winner_sharpe"], "sr0": g["sr0"]}

    rows = [r for r in (at(m_max * i / n_grid) for i in range(1, n_grid + 1)) if r is not None]
    cleared = [i for i, r in enumerate(rows) if r["dsr"] is not None and r["dsr"] >= dsr_min]
    required: dict | None = None
    if cleared:
        # ⭐ BISECT between the last non-clearing grid point and the first clearing one rather than
        # refining the whole grid: the answer wanted is a THRESHOLD, so spending the budget at the
        # crossing gives far more precision per `project_gate` call than a uniformly finer sweep.
        lo = rows[cleared[0] - 1]["mc_sd"] if cleared[0] > 0 else 0.0
        hi = rows[cleared[0]]["mc_sd"]
        for _ in range(n_refine):
            mid = 0.5 * (lo + hi)
            r = at(mid)
            if r is not None and r["dsr"] is not None and r["dsr"] >= dsr_min:
                hi, required = mid, r
            else:
                lo = mid
        required = required or rows[cleared[0]]
    return {
        "assumption": "one COMMON absolute Monte-Carlo sd across the declared arms",
        "winner_observed_sd": sds[winner],
        "threshold_exists": bool(cleared),
        "required_mc_share_of_winner_var": (required["mc_share_of_winner_var"]
                                            if required else None),
        "required_mc_sd": (required["mc_sd"] if required else None),
        "max_dsr_over_sweep": max((r["dsr"] for r in rows if r["dsr"] is not None), default=None),
        "grid_points": len(rows), "refine_steps": n_refine,
        "curve": [rows[j] for j in range(0, len(rows), max(1, len(rows) // 12))],
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered decision
# ══════════════════════════════════════════════════════════════════════════════════════════════
def smallest_clearing_rung(rungs: list[dict], dsr_min: float,
                           ladder: tuple[int, ...] = DRAW_LADDER) -> int:
    """The smallest LADDER rung projected to clear the bar, else the registered cap.

    ⛔ `kind == "ladder"` is load-bearing: the identity and reconstruction rows carry the CURRENT
    draw count, so reading them as rungs could "fund" a re-run at exactly the count that already
    failed — a no-op dressed as a remedy. One helper, two callers, so the two funding paths cannot
    drift apart."""
    return int(next((r["draws"] for r in rungs
                     if r.get("kind") == "ladder" and r["dsr"] is not None
                     and r["dsr"] >= dsr_min), ladder[-1]))


def decide(scaling: dict, ceiling_dsr: float | None, ceiling_ci: dict, rungs: list[dict],
           dsr_min: float, ladder: tuple[int, ...] = DRAW_LADDER,
           ceiling_unbounded: bool = False) -> dict:
    """The prereg §3 rule, in order. G2 is a VALIDITY clause — it does not fail toward a verdict,
    it withholds one; only G3 decides."""
    if not scaling.get("evaluable") or not scaling.get("holds"):
        return {
            "verdict": "UNDEFINED_SCALING", "fund_phase_b": False, "d2": None,
            "reason": f"Monte-Carlo variance did not scale as 1/draws between "
                      f"{scaling.get('draws_control')} and {scaling.get('draws_primary')} draws "
                      f"(ratio {scaling.get('ratio')}, registered band {scaling.get('band')}), so "
                      f"the extrapolation the ceiling rests on is not valid here. ⛔ NO decision is "
                      f"issued and nothing is funded — a ceiling computed off a law the data does "
                      f"not obey would close the lever on arithmetic rather than on evidence.",
            "publishes_retest_trigger": False,
        }
    if not ceiling_ci.get("evaluable"):
        return {"verdict": "UNDEFINED_CEILING_CI", "fund_phase_b": False, "d2": None,
                "reason": ceiling_ci.get("reason", "the ceiling CI could not be evaluated"),
                "publishes_retest_trigger": False}
    hi = float(ceiling_ci["hi"])
    if ceiling_unbounded:
        d2 = smallest_clearing_rung(rungs, dsr_min, ladder)
        return {
            "verdict": "FUND_HIGH_DRAW_RUN", "fund_phase_b": True, "d2": int(d2),
            "reason": f"the heterogeneity estimate is not distinguishable from zero, so the "
                      f"CEILING is UNBOUNDED — no finite bar refuses it, and the lever cannot be "
                      f"closed on this evidence. Phase B is funded at {int(d2):,} draws. ⛔ This "
                      f"funds a MEASUREMENT, not a certification.",
            "publishes_retest_trigger": False,
        }
    if hi < dsr_min:
        return {
            "verdict": "MC_LEVER_EXHAUSTED", "fund_phase_b": False, "d2": None,
            "reason": f"the CEILING deflated Sharpe — the gate with ALL Monte-Carlo error removed, "
                      f"which no draw count can beat — is {ceiling_dsr} with CI95 upper end {hi:.4f}, "
                      f"below the bar {dsr_min}. ⇒ NO draw count clears `dsr_ok`: the DRAW-COUNT "
                      f"lever is EXHAUSTED, and ⛔ no draw / fold / season re-test trigger is "
                      f"published (NF-D18). ⚠️ SCOPE — this closes the DRAW lever, NOT every "
                      f"conceivable lower-variance design. The residual variance is what remains "
                      f"once draw noise is removed, and this design CANNOT split it further: "
                      f"across-fold varies the test ROWS and the SEASON together, so it mixes true "
                      f"season-to-season heterogeneity with finite-test-row sampling error. A "
                      f"row-count or sharper-metric lever is UNTESTED here, not refuted.",
            "publishes_retest_trigger": False,
        }
    d2 = smallest_clearing_rung(rungs, dsr_min, ladder)
    return {
        "verdict": "FUND_HIGH_DRAW_RUN", "fund_phase_b": True, "d2": int(d2),
        "reason": f"the ceiling DSR {ceiling_dsr} (CI95 upper {hi:.4f}) reaches the bar {dsr_min}, "
                  f"so a lower-variance design CAN in principle clear `dsr_ok`. Phase B is funded "
                  f"at the smallest registered ladder rung projected to clear it: {int(d2):,} "
                  f"draws. ⛔ This funds a MEASUREMENT, not a certification — every other clause "
                  f"must still hold at the new draw count.",
        "publishes_retest_trigger": False,
    }
