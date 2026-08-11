"""margin_calibration.py — NF-MARGIN1: per-player interval/tail calibration of the hurdle
champion (pure).

THE STORY IN ONE PARAGRAPH. Three consecutive component studies came back null against the
injury-aware `lgbm_hurdle` champion — NF-W3 (environment), NF-W4 (availability), NF-W5
(correlation) — so the frontier is no longer in adding components; it is in the MARGINALS
themselves. NF-W5's diagnostic that outlives its null is the lead: the assembled champion's
TEAM-TOTAL predictive under-covers — coverage(80) 0.706 vs the 0.80 floor (n=2,174, ~11 binomial
SE) — under EVERY copula INCLUDING the peeking oracles, which proves the roster-grain
miscalibration is a MARGINAL-SHAPE defect in the per-player predictive, not missing correlation.
NF-MARGIN1 diagnoses WHERE the per-player shape is wrong (per position — QB/TE zero-atom behavior
differs from RB/WR) and prices pre-registered recalibration arms against the champion.

THE STRUCTURAL SUSPECT, VISIBLE IN THE CODE. The champion's quantile learners fit 9 knots ending
at 0.05/0.95 (`WP.FIT_LEVELS`); `interp_to_levels` extends them FLAT to the 39-level grid's
0.025/0.975 ends, and the joint sampler (`OA.x_from_uniforms`) clamps there again. So the served
per-player predictive carries NO tail model beyond its own 5%/95% knots — ~10% of reality is
squeezed onto two flat points. A sum of K such truncated marginals is structurally too narrow,
which is exactly the NF-W5 team-total signature. The diagnosis stage MEASURES this (randomized-PIT
tail mass beyond the grid vs the nominal 2.5% per side) rather than assuming it.

EVERY ARM IS A MONOTONE LEVEL MAP over the SAME champion bank. A construction maps each
evaluation level tau to a source level g(tau) on the champion's own quantile function (the NF-W5
inverse-CDF machinery), optionally with a parametric exponential tail beyond the grid ends. The
champion's marginals are therefore PINNED as the substrate; arms differ only in the map — the
identity map reproduces the incumbent bank byte-for-byte (guard-tested, the no-op reproduction
rule).

⚠️ TWO HARD RULES FROM THE VERTICAL, encoded structurally:
  · NF1.7 (d): the widen-only knob (`level_widen`) is monotone BY CONSTRUCTION — its grid starts
    at w=1.0 (can only widen) and |g(tau)-0.5| is nondecreasing in w for every tau. Guard-tested.
  · NF1.8 / E2.1-r: the coverage floor is a CONSTRAINT, never a target. The `max_width`
    degenerate must SATISFY the floor and still LOSE the primary metric (proving the floor is not
    a criterion), and no arm is fit or selected on |coverage − 0.80|; the calibration gate reads
    randomized-PIT flatness (E2.1-r (a)).

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: this module promotes nothing and serves
nothing; a clearing arm's retrain/promote path is blocked on NF-C6 Ph2 + NF-G0.

Pure module — no lake IO. The runner is `run_nf_margin1_interval_calibration.py`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import opportunity_allocation as OA
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────
STORY = "NF-MARGIN1"
#: The selection metric — CRPS via the 2×mean-pinball identity over a 199-level grid
#: (0.005..0.995). ⭐ WHY NOT `crps_q39`: the diagnosed defect lives partly BEYOND the champion's
#: 39-level grid (the flat-tail truncation), and a metric evaluated only on that grid is
#: structurally blind to any arm that models the tails (the instrument must be able to SEE the
#: fix — MH2.1's lesson, on levels instead of stratifiers). The incumbent is scored on the same
#: grid with its as-served flat tails, i.e. exactly the object the NF-W5 sampler draws from.
PRIMARY_METRIC = "crps_q199"
EVAL_LEVELS: np.ndarray = np.round(np.arange(0.005, 0.9951, 0.005), 4)  # 199 levels
#: Q_LEVELS is an exact subset of EVAL_LEVELS (0.025k = 5·0.005k); this index recovers the
#: champion-grid columns from an eval bank (guard-tested).
IDX_Q39: np.ndarray = np.searchsorted(EVAL_LEVELS, WP.Q_LEVELS)
#: Winkler interval score at the 80% central interval (q10/q90 — both exact grid levels).
CO_METRICS: tuple[str, ...] = ("winkler_80", "coverage_80", "coverage_95", "coverage_99")
WINKLER_ALPHA = 0.20
_SEED = 20260812

#: Foils (never shippable; the best foil binds). `incumbent` is the champion as served —
#: the thing every arm must beat. `pit_recal_global` is the position-POOLED recalibration
#: (the NF1.8 pooled-conformal foil: it prices whether per-position conditioning earns anything).
FOILS: tuple[str, ...] = ("incumbent", "pit_recal_global")
#: 4 structurally different recalibration classes (§0.5):
#:   `pit_recal_pos`  — nonparametric monotone level map = empirical quantiles of the calibration
#:                      PITs, per position (distribution-free; within-grid only).
#:   `pit_recal_tail` — the same map + parametric exponential tails beyond the grid ends
#:                      (the ONLY class that can put mass beyond the champion's q025/q975 —
#:                      the truncation channel; its paired delta vs `pit_recal_pos` is the
#:                      pre-registered tail-channel attribution, NF-D10 (g)).
#:   `level_widen`    — g(tau) = 0.5 + (tau−0.5)·w with w ≥ 1: the widen-only knob, clamped
#:                      monotone (NF1.7 (d)); prices the naive "under-dispersed ⇒ widen" fix.
#:   `zscore_affine`  — g(tau) = Φ(μ + σ·Φ⁻¹(tau)) with (μ, σ) the calibration normal-score
#:                      moments: the two-parameter Gaussian recalibration anchored on the
#:                      analytic Var(z)=1 truth (MH2.1 (b)). Two-sided BY DECLARATION — it may
#:                      sharpen; it is not labelled widen-only.
REAL_ARMS: tuple[str, ...] = ("pit_recal_pos", "pit_recal_tail", "level_widen", "zscore_affine")
PARAMETRIZED_FORMS: tuple[str, ...] = (*REAL_ARMS, "pit_recal_global")
#: Diagnostic anchors — excluded from PBO and the DSR trial field (MH2.1 (a)).
#: `zero_width` + `max_width` bracket sharpness two-sidedly (NF1.7 (c)); `permuted_recal` is the
#: permutation anchor (map fit on PITs of within-(position, week) permuted outcomes).
BASE_ANCHORS: tuple[str, ...] = ("zero_width", "max_width", "permuted_recal")

#: The widen-only grid STARTS at 1.0 — the NF1.7 (d) clamp is the grid itself.
WIDEN_GRID: tuple[float, ...] = (1.0, 1.05, 1.10, 1.15, 1.20, 1.30, 1.40, 1.60)
#: `max_width` spread multiplier about the row median (mirrors NF-W1's max_width convention).
MAX_WIDTH_SCALE = 3.0
#: Exponential-tail fit: below this many exceedance rows the beta is 0 (the tail collapses to
#: the clamp) and the cell is COUNTED in `thin_tail_cells` — loud, never silent (NF1.7 (a)).
MIN_TAIL_N = 10
#: Level maps are clipped to this open-interval margin before use.
LEVEL_EPS = 1e-4

#: Calibration split (honest OOS PITs for map fitting): the most recent train global weeks
#: totaling ≥ max(CAL_MIN_ROWS, CAL_TARGET_FRACTION·len(train)) rows become the CAL slice; the
#: champion is refit on the remaining core (with the same PURGE_WEEKS gap) to predict it.
#: ⚠️ WHY: in-sample PITs of a boosted model are optimistically flat — a map fit on them
#: under-corrects. Structural constants, not tuned.
CAL_TARGET_FRACTION = 0.20
CAL_MIN_ROWS = 6000

TEST_BLOCKS = WP.TEST_BLOCKS                    # the NF-W1 fold axis, verbatim
PURGE_WEEKS = WP.PURGE_WEEKS
PBO_MAX, DSR_MIN, FDR_Q = WP.PBO_MAX, WP.DSR_MIN, WP.FDR_Q
COVERAGE_FLOOR, COVERAGE_BLOCK_SE = WP.COVERAGE_FLOOR, WP.COVERAGE_BLOCK_SE
POSITIONS = WP.POSITIONS

#: ⭐ TWO pre-registered multiplicity families, own-family AND pooled computed, the STRICTER
#: binds (MH2 (a)): the per-position ARM tests, and the per-position TAIL-CHANNEL contrasts
#: (`pit_recal_tail` − `pit_recal_pos`, the truncation attribution).
FDR_FAMILIES: dict[str, tuple[str, ...]] = {
    "arm": tuple(f"margin_arm_{p}" for p in POSITIONS),
    "tail_channel": tuple(f"margin_tail_{p}" for p in POSITIONS),
}

oracle_of = GE.oracle_of
matched_n_of = GE.matched_n_of

#: Team-total re-check (report-only, never selects): the NF-W5 independence construction re-run
#: with each arm's marginals — closes the loop on the motivating coverage table. Sample count
#: matches NF-W5 so the incumbent row is an exact reproduction anchor.
TEAM_TOTAL_SAMPLES = OA.N_SAMPLES
MIN_TEAM_K = OA.MIN_TEAM_K


def anchors() -> tuple[str, ...]:
    return (*BASE_ANCHORS,
            *(oracle_of(f) for f in PARAMETRIZED_FORMS),
            *(matched_n_of(a) for a in REAL_ARMS))


def all_labels() -> tuple[str, ...]:
    return (*REAL_ARMS, *FOILS, *anchors())


def eligible_labels() -> list[str]:
    """The set the selection actually searched — real arms + foils (NF1.8: a deflation statistic
    over a field containing its own anchors measures the anchors)."""
    return [*REAL_ARMS, *FOILS]


def form_of(label: str) -> str:
    """Resolve a label to its base form (oracle__X / matched_n__X → X)."""
    for prefix in ("oracle__", "matched_n__"):
        if label.startswith(prefix):
            return label[len(prefix):]
    return label


# Shared verdict / reporting helpers — IMPORTED, never re-typed (NF-W2d discipline).
direction_word = GE.direction_word
verdict_sentence = GE.verdict_sentence
paired_ci95 = GE.paired_ci95
flag_unsafe_field_shrink = GE.flag_unsafe_field_shrink
gate_sensitivity = GE.gate_sensitivity

# The atom-aware PIT + inverse-CDF machinery — IMPORTED from NF-W5, never re-derived.
randomized_pit = OA.randomized_pit
x_from_uniforms = OA.x_from_uniforms
assert_finite_samples = OA.assert_finite_samples
group_seed = OA.group_seed
group_base = OA.group_base


# ── Calibration split ───────────────────────────────────────────────────────────────────────────
def calibration_split(train: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """(core, cal, note): the most recent train gws totaling ≥ the target become CAL; CORE is the
    remainder minus a PURGE_WEEKS gap. RAISES if either side would be empty (NF1.7 (a))."""
    target = max(CAL_MIN_ROWS, int(CAL_TARGET_FRACTION * len(train)))
    gws = np.sort(train["gw"].unique())[::-1]
    take: list[int] = []
    total = 0
    for g in gws:
        take.append(int(g))
        total += int((train["gw"] == g).sum())
        if total >= target:
            break
    cal = train[train["gw"].isin(take)]
    core = train[train["gw"] <= min(take) - 1 - PURGE_WEEKS]
    if not len(core) or not len(cal):
        raise ValueError(
            f"calibration split degenerate: core={len(core)} cal={len(cal)} rows from "
            f"{len(train)} train rows — refusing to fit maps on an empty side (NF1.7 (a))")
    note = {"n_train": int(len(train)), "n_core": int(len(core)), "n_cal": int(len(cal)),
            "cal_gw_min": int(min(take)), "cal_gw_max": int(max(take))}
    return core, cal, note


def permute_within_pos_week(cal: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """Outcomes permuted WITHIN (position, global week) — destroys the row-level predictive link,
    keeps every position-week composition (the permutation substrate)."""
    y = cal["fantasy_points"].to_numpy(dtype=float).copy()
    keys = cal["position"].astype(str) + "|" + cal["gw"].astype(str)
    for _, idx in pd.Series(np.arange(len(cal)), index=keys.to_numpy()).groupby(level=0):
        posn = idx.to_numpy()
        if len(posn) > 1:
            y[posn] = y[rng.permutation(posn)]
    return y


# ── Level-map forms ─────────────────────────────────────────────────────────────────────────────
def fit_recal_levels(u: np.ndarray) -> np.ndarray:
    """The nonparametric map's parameter: the SORTED calibration PIT sample. g(tau) is its
    empirical quantile function (atom-aware because the randomized PIT already is)."""
    u = np.asarray(u, dtype=float)
    u = u[np.isfinite(u)]
    if len(u) < 50:
        raise ValueError(f"recal map fit on {len(u)} PIT rows < 50 — refusing (NF1.7 (a))")
    return np.sort(u)


def fit_zscore_affine(u: np.ndarray) -> dict:
    from scipy.stats import norm
    z = norm.ppf(np.clip(np.asarray(u, dtype=float), 1e-6, 1 - 1e-6))
    z = z[np.isfinite(z)]
    if len(z) < 50:
        raise ValueError(f"zscore_affine fit on {len(z)} rows < 50 — refusing (NF1.7 (a))")
    return {"mu": float(np.mean(z)), "sigma": float(np.std(z, ddof=1))}


def fit_tail_betas(q39_sorted: np.ndarray, y: np.ndarray) -> dict:
    """Exponential exceedance scales beyond the grid ends, fit by mean excess (the exponential
    MLE). A side with < MIN_TAIL_N exceedances gets beta 0 and is COUNTED."""
    q_lo, q_hi = q39_sorted[:, 0], q39_sorted[:, -1]
    yv = np.asarray(y, dtype=float)
    hi_exc = yv[yv > q_hi] - q_hi[yv > q_hi]
    lo_exc = q_lo[yv < q_lo] - yv[yv < q_lo]
    out = {"beta_hi": float(np.mean(hi_exc)) if len(hi_exc) >= MIN_TAIL_N else 0.0,
           "beta_lo": float(np.mean(lo_exc)) if len(lo_exc) >= MIN_TAIL_N else 0.0,
           "n_hi": int(len(hi_exc)), "n_lo": int(len(lo_exc))}
    out["thin_hi"] = bool(len(hi_exc) < MIN_TAIL_N)
    out["thin_lo"] = bool(len(lo_exc) < MIN_TAIL_N)
    return out


def fit_level_widen(q39_sorted: np.ndarray, y: np.ndarray,
                    grid: tuple[float, ...] = WIDEN_GRID) -> float:
    """The widen-only knob, fit in-fold: argmin over the (w ≥ 1) grid of the calibration-slice
    CRPS. The grid STARTS at 1.0, so the knob can only widen — the NF1.7 (d) clamp is the grid
    itself, not a runtime check."""
    best_w, best_c = grid[0], np.inf
    for w in grid:
        q_eval = apply_level_map(q39_sorted, widen_levels(w))
        c = float(np.mean(WP.crps_from_quantiles(q_eval, y, EVAL_LEVELS)))
        if c < best_c:
            best_w, best_c = float(w), c
    return best_w


def recal_levels_g(u_sorted: np.ndarray, levels: np.ndarray = EVAL_LEVELS) -> np.ndarray:
    return np.clip(np.quantile(u_sorted, levels), LEVEL_EPS, 1 - LEVEL_EPS)


def zscore_affine_g(params: dict, levels: np.ndarray = EVAL_LEVELS) -> np.ndarray:
    from scipy.stats import norm
    g = norm.cdf(params["mu"] + params["sigma"] * norm.ppf(levels))
    return np.clip(g, LEVEL_EPS, 1 - LEVEL_EPS)


def widen_levels(w: float, levels: np.ndarray = EVAL_LEVELS) -> np.ndarray:
    return np.clip(0.5 + (levels - 0.5) * float(w), LEVEL_EPS, 1 - LEVEL_EPS)


def apply_level_map(q39_sorted: np.ndarray, g: np.ndarray, tail: dict | None = None) -> np.ndarray:
    """Evaluate the champion quantile bank at source levels `g` (one shared map per position),
    with optional exponential tails beyond the grid ends.

    Within the grid this is exactly `OA.x_from_uniforms` row-wise (guard-tested equal); it is
    vectorized here because the map is shared across rows. Beyond [0.025, 0.975]: without a tail
    the value clamps to the grid end (the as-served behavior); with a tail it extends
    x = q975 + beta_hi·ln(0.025/(1−u)) above (continuous at the joint), mirrored below."""
    q = np.asarray(q39_sorted, dtype=float)
    g = np.asarray(g, dtype=float)
    if not np.all(np.diff(g) >= 0):
        raise ValueError("level map is not monotone — refusing to build a crossing predictive")
    inner = np.clip(g, WP.Q_LEVELS[0], WP.Q_LEVELS[-1])
    hi_idx = np.clip(np.searchsorted(WP.Q_LEVELS, inner, side="right"), 1, len(WP.Q_LEVELS) - 1)
    lo_lv, hi_lv = WP.Q_LEVELS[hi_idx - 1], WP.Q_LEVELS[hi_idx]
    wt = (inner - lo_lv) / np.maximum(hi_lv - lo_lv, 1e-12)
    out = q[:, hi_idx - 1] * (1 - wt)[None, :] + q[:, hi_idx] * wt[None, :]
    if tail is not None:
        above = g > WP.Q_LEVELS[-1]
        below = g < WP.Q_LEVELS[0]
        if above.any() and tail["beta_hi"] > 0:
            ext = tail["beta_hi"] * np.log(WP.Q_LEVELS[0] / (1.0 - g[above]))
            out[:, above] = q[:, -1][:, None] + ext[None, :]
        if below.any() and tail["beta_lo"] > 0:
            ext = tail["beta_lo"] * np.log(WP.Q_LEVELS[0] / g[below])
            out[:, below] = q[:, 0][:, None] - ext[None, :]
    return out


# ── Construction dispatch ───────────────────────────────────────────────────────────────────────
def build_eval_bank(label: str, params, q39_sorted: np.ndarray) -> np.ndarray:
    """The (n, 199) evaluation-grid quantile bank for one construction. The identity map
    reproduces the incumbent bank exactly (the no-op reproduction rule, guard-tested)."""
    form = form_of(label)
    if form == "incumbent":
        return apply_level_map(q39_sorted, EVAL_LEVELS)
    if form == "zero_width":
        med = apply_level_map(q39_sorted, np.array([0.5]))[:, 0]
        return np.repeat(med[:, None], len(EVAL_LEVELS), axis=1)
    if form == "max_width":
        base = apply_level_map(q39_sorted, EVAL_LEVELS)
        med = base[:, np.searchsorted(EVAL_LEVELS, 0.5)][:, None]
        return med + MAX_WIDTH_SCALE * (base - med)
    if form in ("pit_recal_pos", "pit_recal_global", "permuted_recal"):
        return apply_level_map(q39_sorted, recal_levels_g(params))
    if form == "pit_recal_tail":
        return apply_level_map(q39_sorted, recal_levels_g(params["u_sorted"]),
                               tail=params["tail"])
    if form == "level_widen":
        return apply_level_map(q39_sorted, widen_levels(params))
    if form == "zscore_affine":
        return apply_level_map(q39_sorted, zscore_affine_g(params))
    raise ValueError(f"unknown construction label: {label}")


def fit_form(form: str, u: np.ndarray, q39_sorted: np.ndarray, y: np.ndarray):
    """Fit one parametrized form on a (PIT, bank, outcome) calibration sample."""
    if form in ("pit_recal_pos", "pit_recal_global", "permuted_recal"):
        return fit_recal_levels(u)
    if form == "pit_recal_tail":
        return {"u_sorted": fit_recal_levels(u), "tail": fit_tail_betas(q39_sorted, y)}
    if form == "level_widen":
        return fit_level_widen(q39_sorted, y)
    if form == "zscore_affine":
        return fit_zscore_affine(u)
    raise ValueError(f"unknown parametrized form: {form}")


# ── Metrics ─────────────────────────────────────────────────────────────────────────────────────
_I10 = int(np.searchsorted(EVAL_LEVELS, 0.10))
_I90 = int(np.searchsorted(EVAL_LEVELS, 0.90))
_COV_IDX = {"coverage_50": (int(np.searchsorted(EVAL_LEVELS, 0.25)),
                            int(np.searchsorted(EVAL_LEVELS, 0.75))),
            "coverage_80": (_I10, _I90),
            "coverage_95": (int(np.searchsorted(EVAL_LEVELS, 0.025)),
                            int(np.searchsorted(EVAL_LEVELS, 0.975))),
            "coverage_99": (int(np.searchsorted(EVAL_LEVELS, 0.005)),
                            int(np.searchsorted(EVAL_LEVELS, 0.995)))}


def winkler_80(q_eval: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Winkler interval score at the central 80% interval (proper; lower is better)."""
    lo, hi = q_eval[:, _I10], q_eval[:, _I90]
    yv = np.asarray(y, dtype=float)
    return (hi - lo) + (2.0 / WINKLER_ALPHA) * (np.maximum(lo - yv, 0.0)
                                                + np.maximum(yv - hi, 0.0))


def score_bank(q_eval: np.ndarray, y: np.ndarray) -> dict:
    assert_finite_samples(q_eval, "eval bank")
    yv = np.asarray(y, dtype=float)
    out = {"crps_q199": float(np.mean(WP.crps_from_quantiles(q_eval, yv, EVAL_LEVELS))),
           "winkler_80": float(np.mean(winkler_80(q_eval, yv))),
           "n": int(len(yv))}
    for name, (li, hi) in _COV_IDX.items():
        out[name] = float(np.mean((yv >= q_eval[:, li]) & (yv <= q_eval[:, hi])))
    return out


# ── PIT accounting (poolable across folds) ──────────────────────────────────────────────────────
PIT_DECILES = np.linspace(0.0, 1.0, 11)


def pit_stats(u: np.ndarray) -> dict:
    """Poolable randomized-PIT accounting: decile counts, beyond-grid tail counts (nominal 2.5%
    per side), and normal-score sums for Var(z)."""
    from scipy.stats import norm
    u = np.asarray(u, dtype=float)
    z = norm.ppf(np.clip(u, 1e-6, 1 - 1e-6))
    counts = np.histogram(u, bins=PIT_DECILES)[0]
    return {"decile_counts": [int(c) for c in counts], "n": int(len(u)),
            "n_below_grid": int((u < WP.Q_LEVELS[0]).sum()),
            "n_above_grid": int((u > WP.Q_LEVELS[-1]).sum()),
            "sum_z": float(np.sum(z)), "sum_z2": float(np.sum(z * z))}


def pool_pit_stats(parts: list[dict]) -> dict:
    n = sum(p["n"] for p in parts)
    if not n:
        return {"n": 0}
    counts = np.sum([p["decile_counts"] for p in parts], axis=0)
    freq = counts / n
    sum_z = sum(p["sum_z"] for p in parts)
    sum_z2 = sum(p["sum_z2"] for p in parts)
    mean_z = sum_z / n
    var_z = sum_z2 / n - mean_z ** 2
    return {"n": int(n), "decile_freq": [round(float(f), 5) for f in freq],
            "max_decile_dev": round(float(np.max(np.abs(freq - 0.1))), 5),
            "p_below_grid": round(float(sum(p["n_below_grid"] for p in parts) / n), 5),
            "p_above_grid": round(float(sum(p["n_above_grid"] for p in parts) / n), 5),
            "mean_z": round(float(mean_z), 4), "var_z": round(float(var_z), 4)}


# ── Team-total re-check (report-only; the NF-W5 loop closed) ────────────────────────────────────
def team_total_check(groups: list[dict], q_eval: np.ndarray, y_all: np.ndarray,
                     fold_label: str) -> dict:
    """Independence-copula team-total interval accounting for ONE construction's marginals, on
    the SAME common-random-number base as NF-W5 (so the incumbent row is an exact reproduction
    anchor of the motivating measurement). Counts inside/below/above the central 80%."""
    inside = below = above = 0
    from scipy.stats import norm
    for g in groups:
        rows = g["rows"]
        U = norm.cdf(group_base(fold_label, g["team"], g["gw"], len(rows),
                                n_samples=TEAM_TOTAL_SAMPLES)["Z"])
        X = np.empty_like(U)
        for j, r in enumerate(rows):
            X[:, j] = np.interp(U[:, j], EVAL_LEVELS, q_eval[r])
        T = X.sum(axis=1)
        t_star = float(y_all[rows].sum())
        q10, q90 = np.quantile(T, [0.10, 0.90])
        if t_star < q10:
            below += 1
        elif t_star > q90:
            above += 1
        else:
            inside += 1
    n = inside + below + above
    return {"n": n, "inside": inside, "below_q10": below, "above_q90": above}


def pool_team_total(parts: list[dict]) -> dict:
    n = sum(p["n"] for p in parts)
    if not n:
        return {"n": 0}
    below = sum(p["below_q10"] for p in parts)
    above = sum(p["above_q90"] for p in parts)
    se = float(np.sqrt(COVERAGE_FLOOR * (1 - COVERAGE_FLOOR) / n))
    return {"n": int(n), "coverage_80": round(float(sum(p["inside"] for p in parts) / n), 4),
            "share_below_q10": round(float(below / n), 4),
            "share_above_q90": round(float(above / n), 4), "binomial_se": round(se, 4)}


# ── Gate composition + refusal classification ───────────────────────────────────────────────────
MARGIN_STATISTICAL_CHECKS: tuple[str, ...] = (
    "beats_foil", "fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok", "coverage_floor_ok",
)
MARGIN_ANCHOR_CHECKS: tuple[str, ...] = (
    "degenerates_lose", "permutation_behaves", "oracle_floors_respected",
)
#: ⭐ The story's two-sided calibration gate, as SEPARATE named clauses (NF-D20: never bundle):
#: the winner must improve the Winkler-80 interval score AND the randomized-PIT flatness vs the
#: incumbent. Coverage stays a FLOOR in the statistical set — nothing gates on |cov − 0.80|.
MARGIN_CALIBRATION_CHECKS: tuple[str, ...] = (
    "interval_score_improves", "pit_flatness_improves",
)


def compose_gate_margin(sel: dict, fdr_pass: bool) -> dict:
    checks = {
        "beats_foil": bool(sel["beats_foil"]),
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "degenerates_lose": bool(sel["anchors"]["zero_width_loses"]
                                 and sel["anchors"]["max_width_loses"]),
        "permutation_behaves": bool(sel["anchors"]["winner_beats_permuted"]
                                    and sel["anchors"]["permuted_lift_not_significant"]),
        "oracle_floors_respected": bool(sel["anchors"]["oracle_floors_respected_at_matched_n"]),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
        "interval_score_improves": bool(sel["calibration"]["winkler_delta_vs_incumbent"] > 0),
        "pit_flatness_improves": bool(sel["calibration"]["flatness_delta_vs_incumbent"] > 0),
    }
    return {"checks": checks, "ship": all(checks.values())}


def hand_classify_refusal_margin(checks: dict) -> dict | None:
    """The NF-D18/MH2.7 hand check with this story's third clause category: when every
    STATISTICAL gate passes and the null rests only on anchor/calibration clauses, the state is
    CONSTRAINT_REFUSED — more data cannot change a directional anchor refusal, and ⛔ no
    sample-size re-test trigger may be published."""
    stat_fail = [c for c in MARGIN_STATISTICAL_CHECKS if not checks.get(c, True)]
    other_fail = [c for c in (*MARGIN_ANCHOR_CHECKS, *MARGIN_CALIBRATION_CHECKS)
                  if not checks.get(c, True)]
    if stat_fail or not other_fail:
        return None
    return {
        "state": "CONSTRAINT_REFUSED",
        "reason": ("hand-classified (the NF-D18/MH2.7 classify_null gap): every statistical gate "
                   f"passed and the null rests entirely on anchor/calibration clauses "
                   f"{other_fail}. More data cannot change this verdict."),
        "retest_trigger": None,
        "failing_anchor_checks": other_fail,
    }
