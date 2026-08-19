"""fp_cross_position.py — NF-W8-0: the cross-position comparability layer for the weekly
optimizer input, plus the registered-forward QB consumption decision (pure).

THE STORY IN ONE PARAGRAPH. The four positions' weekly fantasy-point distributions come from
DIFFERENT generators — TE from NF-W7c's single-copula assembly, WR from NF-W7e's availability
mixture over the all-rows Σ, RB from the direct-points quantile learner NF-W7i measured at its
ceiling, QB from NF-W7f's zero-mass-recalibrated assembly consumed under the Option-B
registration below. A cross-position VOR ranking is invalid until those generators sit on the
SAME scale: a systematic LEVEL gap between generators moves a position up or down the merged
board by which CODE produced its number, not by skill (NF-W7c §4). This module carries (a) the
QB consumption registration, (b) the pinned consumed-generator map, (c) the level-gap
measurement and the declared recalibration field, (d) the generator-swap verification, and
(e) the verdict rule — all fixed BEFORE any score (the narrative pre-registration is committed
at `ablation_results/nf_w8_0_preregistration.md`).

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 CHALLENGER: this story produces the
INPUT to the eventual weekly optimizer; it promotes nothing, publishes nothing, retrains nothing.

Pure module — no lake IO, no S3, no boto3. Runner: `run_nf_w8_0_cross_position.py`.
"""
from __future__ import annotations

import numpy as np
from scipy import stats as sps

from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA
from quant_sports_intel_models.football.nfl.fantasy import fp_availability_mixture as MX

# ── Pre-registration constants (the runner READS these — NF-D16) ────────────────────────────────
STORY = "NF-W8-0"
TARGET = FA.TARGET                               # `league_fantasy_points`
POSITIONS: tuple[str, ...] = FA.POSITIONS
EVAL_LEVELS, N_LEVELS = FA.EVAL_LEVELS, FA.N_LEVELS
PREREGISTRATION_RELPATH = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                           "nf_w8_0_preregistration.md")

# ══════════════════════════════════════════════════════════════════════════════════════════════
# §1 — THE QB CONSUMPTION DECISION (Option B), registered FORWARD (prereg §1)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: ⭐⭐ PM decision 2026-08-19, registered before any NF-W8-0 scoring: NF-W8 consumes the
#: RECALIBRATED QB (NF-W7f `zm_floor`). ⛔ NOT a re-certification — the ship bar stands exactly
#: as NF-W7j/W7k left it; this is a CONSUMER decision for a projection product.
QB_CONSUMPTION = "OPTION_B_RECALIBRATED"
QB_CONSUMPTION_RATIONALE = (
    "dsr_ok is a SHIPPING gate, not a CONSUMPTION bar for a projection consumer: the fantasy "
    "vertical gates consumption on calibration + the product metric, not betting-posture "
    "deflation. NF-W7f's `zm_floor` is the only QB construction on record clearing the PIT bar "
    "(0.0281, 8/8 folds vs the incumbent's 0/8) AND the best-scoring (+0.0184 CRPS vs the matched "
    "foil, p=0.0121, PBO 0.0; +0.0189 vs direct-points); its dsr_ok refusal deflated a search "
    "whose flip mass was 100% on the winner, and every remedy is measured closed (NF-W7j "
    "DSR_UNREACHABLE — field size is no lever; NF-W7k MC_LEVER_EXHAUSTED — a 325x draw-noise "
    "shortfall). Every alternative consumption is strictly worse on BOTH axes.")
QB_CONSUMPTION_CAVEAT = (
    "WEAKER FOOTING, carried by every consumer of QB rows: QB is the only position not through "
    "the full certification gate WR (DSR 0.9852) and TE (0.9822) cleared and RB was registered "
    "against. The un-certified residual is deflation-adjusted ARM SELECTION within the zm family "
    "— not calibration (a per-fold measurement) and not the sign of the improvement. QB rows are "
    "'calibrated + best-on-record, consumed under Option B; not certification-equivalent'.")
SECOND_READER = {
    "requested": True,
    "scope": ("the §1 QB consumption registration — whether NF-W8 may consume a "
              "calibrated-but-dsr-uncertified distribution under a registered-forward Option B "
              "(inherits NF-W7j's open governance flag)"),
    "status": "OPEN — unsigned until a governance second reader signs the prereg §1",
}

# ══════════════════════════════════════════════════════════════════════════════════════════════
# §2 — the consumed-generator map (PINS — nothing here is selected in this story)
# ══════════════════════════════════════════════════════════════════════════════════════════════
CONSUMED_GENERATOR_OF: dict[str, str] = {
    "QB": "qb_zm_floor",        # NF-W7f `zm_floor`, by identity (Option B, §1)
    "RB": "rb_direct",          # direct-points (NF-W7i: near-ceiling, take as-is)
    "WR": "wr_mixall",          # NF-W7e `mixall_learned`, by identity
    "TE": "te_single_copula",   # NF-W7c `joint_rank` (= single_copula), by identity
}
#: the swap ALTERNATIVES for the §6 verification — never consumed, never certified here
SWAP_GENERATOR_OF: dict[str, str] = {
    "QB": "direct_points", "RB": "single_copula", "WR": "direct_points", "TE": "direct_points",
}
#: reproduction pins: consumed generator → (record relpath, record story, record arm). A failed
#: or absent reproduction REFUSES the position — never a pass (NF1.7 (a)).
_AR = "quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
GENERATOR_RECORD_PINS: dict[str, tuple[str, str, str]] = {
    "QB": (_AR + "nf_w7f_qb_marginal.json", "NF-W7f", "zm_floor"),
    "RB": (_AR + "nf_w7e_split_allrows.json", "NF-W7e", "foil_direct_points"),
    "WR": (_AR + "nf_w7e_split_allrows.json", "NF-W7e", "mixall_learned"),
    "TE": (_AR + "nf_w7c_fp_assembly.json", "NF-W7c", "joint_rank"),
}
REPRODUCTION_TOLERANCE = MX.INCUMBENT_TOLERANCE                     # 1e-9, inherited

# ══════════════════════════════════════════════════════════════════════════════════════════════
# §4 — the declared recalibration field (⛔ never trimmed or grown after a score — MH2/MH2.2)
# ══════════════════════════════════════════════════════════════════════════════════════════════
INCUMBENT = "identity"
REAL_ARMS: tuple[str, ...] = ("level_add", "level_affine")
ANCHOR_ARMS: tuple[str, ...] = ("zero_point", "position_mean_point",
                                "level_add_permuted", "level_add_oracle")
ALL_POINT_LABELS: tuple[str, ...] = (INCUMBENT, *REAL_ARMS, *ANCHOR_ARMS)
ELIGIBLE: tuple[str, ...] = (INCUMBENT, *REAL_ARMS)   # the PBO field; trials = the 2 real arms
DECLARED_FIELD_SIZE = len(REAL_ARMS)                  # passed to classify_null (MH2.7)

#: prior-OOF floor per (position, generator) cell below which recal keeps identity, FLAGGED
MIN_PRIOR_ROWS = 50
#: the deterministic cyclic shift for `level_add_permuted` (fixed in advance — no RNG to shop)
PERMUTATION_CYCLE: dict[str, str] = {"QB": "RB", "RB": "WR", "WR": "TE", "TE": "QB"}
#: gates — inherited where a house constant exists (E2.1-r)
BH_Q = 0.10                                            # family A: the 6 pairwise bias contrasts
ALPHA = 0.05                                           # paired one-sided clauses
PBO_MAX, DSR_MIN = MX.PBO_MAX, MX.DSR_MIN
#: ⭐ the NF1.8 tied-field discipline, PRE-REGISTERED (prereg §5.2 (g)): the two real arms are
#: near-clones BY CONSTRUCTION whenever the true artifact is additive (slope ≈ 1 makes the
#: affine ≈ the add), so a raw PBO over this field reads high purely from the top tie.
#: `pbo_ok := PBO < PBO_MAX OR os_gap_pct ≤ OS_GAP_TIE_PCT` — Bailey's degradation asks "did
#: picking it COST anything?"; ≤1% is a tie, not overfitting. Both figures + flips reported.
OS_GAP_TIE_PCT = 1.0
#: §6 activity rule: a position is ACTIVE for the swap clause iff |pooled pre-layer level shift|
#: exceeds this multiple of its paired SE (NF-D20: an inactive position is UNINFORMATIVE)
ACTIVITY_SE_MULT = 2.0
#: arm tie rule: level_add vs level_affine within this many SE of the range statistic → simpler
TIE_SE_MULT = 1.0
#: MDE multiplier: z_{0.975} + z_{0.80} (two-sided alpha=0.05 at 80% power)
MDE_MULT = float(sps.norm.ppf(0.975) + sps.norm.ppf(0.80))

#: ⛔ affine admissibility: any fitted slope ≤ this at any (position, evaluable fold) makes the
#: whole arm INELIGIBLE (NF-D16 / NF-TR2b: a non-positive slope inverts a board)
AFFINE_MIN_SLOPE = 0.0

# the verdict states (prereg §5), fixed before any score
V_COMPARABLE = "COMPARABLE_AS_IS"
V_REMOVED = "LEVEL_ARTIFACT_REMOVED"
V_UNREPAIRED = "LEVEL_GAP_DETECTED_UNREPAIRED"
V_UNDEFINED = "UNDEFINED"
VERDICT_STATES: tuple[str, ...] = (V_COMPARABLE, V_REMOVED, V_UNREPAIRED, V_UNDEFINED)

SWAP_INACTIVE_EVERYWHERE = "INACTIVE_EVERYWHERE"

#: the arm-admissibility clauses (prereg §5.2 (a)–(g)); (h) BH within family B is trivial
ARM_CLAUSES: tuple[str, ...] = (
    "reduces_gap", "beats_permuted", "no_rmse_harm", "degenerates_lose", "banks_untouched",
    "swap_clause", "pbo_ok", "dsr_ok",
)
#: the partition the null classification reads (NF-W7f's mixed-failure rule): a refusal resting
#: on any ANCHOR clause is CONSTRAINT_REFUSED (no data trigger — NF-D18); one resting only on
#: STATISTICAL clauses goes to `classify_null` (recorded verbatim). `no_rmse_harm` is a
#: do-no-harm CONSTRAINT in kind (more data makes a real harm refusal MORE certain), like
#: NF-W7f's per-leg clause.
STATISTICAL_CLAUSES: tuple[str, ...] = ("reduces_gap", "pbo_ok", "dsr_ok")
ANCHOR_CLAUSES: tuple[str, ...] = ("beats_permuted", "no_rmse_harm", "degenerates_lose",
                                   "banks_untouched", "swap_clause")

INPUT_SCHEMA: tuple[str, ...] = (
    "season", "week", "gw", "gsis_id", "position", "generator", "point_raw", "point_recal",
    "recal_arm", "point_vs_bank_offset", "p10", "p50", "p90", "replacement_points", "vor",
    "overall_rank", "positional_rank", "level_gap_disclosure", "qb_option_b",
    "calibration_warning",
)

PROMOTE_BLOCKERS: tuple[str, ...] = (
    "NF-W8-0 is DEPLOY-HELD: the cross-position input is an NF-G0 challenger consumed by nothing "
    "until governance promotes it",
    "every QB row carries the §1 Option-B caveat: calibrated + best-on-record, consumed under a "
    "registered-forward PM decision — NOT certification-equivalent to WR/TE/RB, and the ship bar "
    "was never relaxed (E2.1-r)",
    "NF-W7c's promote blockers are INHERITED in full: an assembled row whose source is not "
    "`bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league "
    "prices (`calibration_warning`), and a league pricing a SKILL_UNMODELED_KEYS term has a real "
    "coverage gap",
    "K/DST are OUT OF SCOPE — the input is declared 4-position; the NF-W7 K/DST weekly models "
    "join in a successor's registration, never by silent extension",
    "the layer corrects LEVEL (and uniform affine scale) only; a rank-dependent generator "
    "artifact is a successor's fresh registration",
)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The ranking point + level-gap statistics (prereg §3)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def bank_point(bank: np.ndarray) -> np.ndarray:
    """(n,) THE ranking point: the mean of the 199-level quantile grid. Uniform levels
    (0.005…0.995) make this the midpoint-rule E[Y] with the outer 0.5% tails truncated — the
    truncation is PART of the measured generator artifact, because this is exactly the point the
    optimizer input carries (prereg §3)."""
    b = np.asarray(bank, dtype=float)
    if b.ndim != 2 or b.shape[1] != N_LEVELS:
        raise ValueError(f"bank is {b.shape}, expected (n, {N_LEVELS})")
    return b.mean(axis=1)


def bias_detail(point: np.ndarray, y: np.ndarray) -> dict:
    """One (fold, position) cell's OOF level reading: mean(point − y), with the sums that let the
    pooled figure be Σerr/Σn over folds (NF1.8: pool over rows, never a mean of fold means)."""
    p, yv = np.asarray(point, float), np.asarray(y, float)
    if p.shape != yv.shape:
        raise ValueError(f"point {p.shape} vs y {yv.shape}")
    if not (np.isfinite(p).all() and np.isfinite(yv).all()):
        raise ValueError("non-finite point or realized value — refused, never nan-meaned (NF-W3)")
    err = p - yv
    return {"n": int(len(err)), "sum_err": float(err.sum()),
            "bias": float(err.mean()), "sd_err": float(err.std(ddof=1)) if len(err) > 1 else None}


def pooled_bias(cells: list[dict]) -> dict:
    """Σerr/Σn over fold cells + the mean-of-fold-means convention beside it (both reported)."""
    n = sum(c["n"] for c in cells)
    if n == 0:
        return {"n": 0, "bias_pooled": None, "bias_fold_mean": None}
    return {"n": n, "bias_pooled": float(sum(c["sum_err"] for c in cells) / n),
            "bias_fold_mean": float(np.mean([c["bias"] for c in cells]))}


def bh_reject(pvals: dict[str, float], q: float = BH_Q) -> dict:
    """Benjamini–Hochberg over a named family. Returns {name: bool}; a None p never rejects
    (fails closed)."""
    named = {k: v for k, v in pvals.items() if v is not None and np.isfinite(v)}
    m = len(named)
    out = {k: False for k in pvals}
    if m == 0:
        return out
    order = sorted(named, key=named.get)
    k_max = 0
    for i, name in enumerate(order, start=1):
        if named[name] <= q * i / m:
            k_max = i
    for name in order[:k_max]:
        out[name] = True
    return out


def paired_onesided_p(deltas: np.ndarray) -> float | None:
    """One-sided paired t: P(mean ≤ 0 | data) small when the deltas are reliably positive.
    None (fails closed) below 2 usable folds or at zero spread with zero mean."""
    d = np.asarray(deltas, float)
    d = d[np.isfinite(d)]
    if len(d) < 2:
        return None
    sd = float(d.std(ddof=1))
    if sd <= 1e-15:
        return 0.0 if float(d.mean()) > 0 else 1.0
    t = float(d.mean()) / (sd / np.sqrt(len(d)))
    return float(1.0 - sps.t.cdf(t, df=len(d) - 1))


def pairwise_gap_tests(bias_by_pos: dict[str, list[float]], *, q: float = BH_Q) -> dict:
    """Family A (prereg §3): the 6 pairwise position contrasts of per-fold biases, paired by
    fold, two-sided t, BH-FDR at q. Also the per-pair MDE at 80% power in PPR (MH2.6: a null is
    'no artifact larger than X', never 'no artifact')."""
    pos = [p for p in POSITIONS if p in bias_by_pos]
    pairs: dict[str, dict] = {}
    pvals: dict[str, float | None] = {}
    for i, a in enumerate(pos):
        for b in pos[i + 1:]:
            da, db = np.asarray(bias_by_pos[a], float), np.asarray(bias_by_pos[b], float)
            if len(da) != len(db):
                raise ValueError(f"{a}|{b}: unpaired fold vectors ({len(da)} vs {len(db)}) — the "
                                 f"pairwise family is fold-PAIRED by construction")
            d = da - db
            d = d[np.isfinite(d)]
            name = f"{a}|{b}"
            if len(d) < 2:
                pairs[name] = {"n_folds": int(len(d)), "gap": None, "p_two_sided": None,
                               "se": None, "mde_ppr": None}
                pvals[name] = None
                continue
            se = float(d.std(ddof=1) / np.sqrt(len(d)))
            if se <= 1e-15:
                p2 = 0.0 if abs(float(d.mean())) > 0 else 1.0
            else:
                t = float(d.mean()) / se
                p2 = float(2.0 * (1.0 - sps.t.cdf(abs(t), df=len(d) - 1)))
            pairs[name] = {"n_folds": int(len(d)), "gap": round(float(d.mean()), 4),
                           "se": round(se, 4), "p_two_sided": round(p2, 6),
                           "mde_ppr": round(MDE_MULT * se, 4)}
            pvals[name] = p2
    rejected = bh_reject(pvals, q)
    for name in pairs:
        pairs[name]["bh_rejected"] = bool(rejected[name])
    evaluable = [n for n, p in pvals.items() if p is not None]
    return {
        "pairs": pairs, "bh_q": q, "n_pairs_evaluable": len(evaluable),
        # a family that could not evaluate is UNDEFINED, never a clean 'no gap' (NF1.7 (a))
        "gap_detected": (None if not evaluable else bool(any(rejected[n] for n in evaluable))),
        "max_mde_ppr": (max(pairs[n]["mde_ppr"] for n in evaluable) if evaluable else None),
    }


def calibration_slope(point: np.ndarray, y: np.ndarray) -> dict:
    """The scale read (prereg §3, reported): OLS slope of y on point. Slope 1 = scale-correct;
    a slope ≠ 1 distorts VOR spread multiplicatively."""
    p, yv = np.asarray(point, float), np.asarray(y, float)
    var = float(p.var(ddof=0))
    if len(p) < 3 or var <= 1e-12:
        return {"slope": None, "intercept": None, "n": int(len(p))}
    b = float(np.cov(p, yv, ddof=0)[0, 1] / var)
    a = float(yv.mean() - b * p.mean())
    return {"slope": round(b, 4), "intercept": round(a, 4), "n": int(len(p))}


def rmse(point: np.ndarray, y: np.ndarray) -> float:
    """The point metric (prereg §4): squared error selects the MEAN — the quantity under repair.
    ⛔ NOT MAE (the all-rows weekly target is zero-heavy; NF-D11's conditional-median inversion —
    the `zero_point` degenerate is scored against exactly this risk every run)."""
    p, yv = np.asarray(point, float), np.asarray(y, float)
    return float(np.sqrt(np.mean((p - yv) ** 2)))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The recalibration estimators (prereg §4) — prior-fold OOF rows only, per (position, generator)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def fit_level_add(prior_point: np.ndarray, prior_y: np.ndarray) -> dict:
    """δ = −mean(prior OOF error). Below MIN_PRIOR_ROWS: identity, FLAGGED (never silent)."""
    p, yv = np.asarray(prior_point, float), np.asarray(prior_y, float)
    if len(p) < MIN_PRIOR_ROWS:
        return {"delta": 0.0, "fitted": False, "n_prior": int(len(p)),
                "note": f"{len(p)} prior OOF rows < floor {MIN_PRIOR_ROWS} — identity, flagged"}
    return {"delta": float((yv - p).mean()), "fitted": True, "n_prior": int(len(p))}


def fit_level_affine(prior_point: np.ndarray, prior_y: np.ndarray) -> dict:
    """OLS y = a + b·point on prior OOF rows. A slope ≤ AFFINE_MIN_SLOPE is reported and makes
    the WHOLE arm ineligible at the verdict layer (NF-D16 — a non-positive slope inverts a
    board; a b > 0 affine is order-preserving within position)."""
    p, yv = np.asarray(prior_point, float), np.asarray(prior_y, float)
    if len(p) < MIN_PRIOR_ROWS:
        return {"a": 0.0, "b": 1.0, "fitted": False, "n_prior": int(len(p)),
                "note": f"{len(p)} prior OOF rows < floor {MIN_PRIOR_ROWS} — identity, flagged"}
    var = float(p.var(ddof=0))
    if var <= 1e-12:
        return {"a": 0.0, "b": 1.0, "fitted": False, "n_prior": int(len(p)),
                "note": "degenerate prior points (zero variance) — identity, flagged"}
    b = float(np.cov(p, yv, ddof=0)[0, 1] / var)
    a = float(yv.mean() - b * p.mean())
    return {"a": a, "b": b, "fitted": True, "n_prior": int(len(p))}


def apply_level_add(point: np.ndarray, params: dict) -> np.ndarray:
    return np.asarray(point, float) + float(params["delta"])


def apply_level_affine(point: np.ndarray, params: dict) -> np.ndarray:
    return float(params["a"]) + float(params["b"]) * np.asarray(point, float)


def permuted_params(params_by_pos: dict[str, dict]) -> dict[str, dict]:
    """`level_add_permuted` (prereg §4): the fitted δs cyclically shifted across positions —
    the population of corrections preserved, their per-position ASSIGNMENT destroyed."""
    return {pos: params_by_pos[PERMUTATION_CYCLE[pos]] for pos in params_by_pos
            if PERMUTATION_CYCLE.get(pos) in params_by_pos}


def fold_range(bias_by_pos_fold: dict[str, float]) -> float:
    """The per-fold cross-position bias RANGE (max − min over the 4 positions) — the gap
    statistic family B's paired deltas are computed on."""
    vals = [v for v in bias_by_pos_fold.values() if v is not None and np.isfinite(v)]
    if len(vals) < 2:
        raise ValueError("fold range needs ≥2 evaluable positions — refused, not defaulted")
    return float(max(vals) - min(vals))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §6 — the generator-swap verification
# ══════════════════════════════════════════════════════════════════════════════════════════════
def swap_activity(shifts_by_fold: np.ndarray, *, se_mult: float = ACTIVITY_SE_MULT) -> dict:
    """Is this position ACTIVE for the swap clause? |pooled pre-layer level shift| must exceed
    se_mult × its paired SE — on an INACTIVE position the two generators already agree on level
    and the clause has nothing to act on (NF-D20: uninformative, never a pass)."""
    s = np.asarray(shifts_by_fold, float)
    s = s[np.isfinite(s)]
    if len(s) < 2:
        return {"active": None, "note": "fewer than 2 evaluable folds — activity UNDEFINED"}
    se = float(s.std(ddof=1) / np.sqrt(len(s)))
    pooled = float(s.mean())
    return {"active": bool(abs(pooled) > se_mult * se), "pooled_shift": round(pooled, 4),
            "se": round(se, 4), "threshold": round(se_mult * se, 4), "n_folds": int(len(s))}


def swap_clause(before_by_pos: dict[str, np.ndarray],
                after_by_pos: dict[str, np.ndarray]) -> dict:
    """`swap_level_component_collapses` (prereg §6): on every ACTIVE position the layer must
    reduce |level shift| (paired per fold, one-sided p < ALPHA). Inactive positions are reported
    INACTIVE; if none is active the clause is INACTIVE_EVERYWHERE (corroborates comparability,
    cannot certify a repair)."""
    detail: dict[str, dict] = {}
    active_pass: list[bool] = []
    for pos, before in before_by_pos.items():
        act = swap_activity(np.asarray(before, float))
        entry = {"activity": act}
        if act["active"]:
            b = np.abs(np.asarray(before, float))
            a = np.abs(np.asarray(after_by_pos[pos], float))
            if b.shape != a.shape:
                raise ValueError(f"{pos}: unpaired before/after swap shifts")
            reduction = b - a
            p = paired_onesided_p(reduction)
            entry.update({"mean_abs_before": round(float(b.mean()), 4),
                          "mean_abs_after": round(float(a.mean()), 4),
                          "p_one_sided": p,
                          "passes": bool(p is not None and p < ALPHA)})
            active_pass.append(entry["passes"])
        detail[pos] = entry
    n_active = len(active_pass)
    return {
        "detail": detail, "n_active_positions": n_active,
        "state": (SWAP_INACTIVE_EVERYWHERE if n_active == 0
                  else "PASS" if all(active_pass) else "FAIL"),
        "passes": (None if n_active == 0 else bool(all(active_pass))),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §5 — the verdict rule, fixed in advance
# ══════════════════════════════════════════════════════════════════════════════════════════════
def select_arm(range_by_arm: dict[str, dict]) -> str | None:
    """Between the admissible real arms: the smaller pooled cross-position bias range; a tie
    (within TIE_SE_MULT × the paired SE of their per-fold range difference) goes to the SIMPLER
    arm (`level_add`). Registered before any score (prereg §5.2)."""
    cands = {a: d for a, d in range_by_arm.items() if a in REAL_ARMS and d.get("eligible", True)}
    if not cands:
        return None
    if len(cands) == 1:
        return next(iter(cands))
    ra = np.asarray(cands["level_add"]["range_by_fold"], float)
    rf = np.asarray(cands["level_affine"]["range_by_fold"], float)
    d = rf - ra                                     # positive ⇒ affine's range is LARGER
    se = float(d.std(ddof=1) / np.sqrt(len(d))) if len(d) > 1 else 0.0
    if abs(float(d.mean())) <= TIE_SE_MULT * se:
        return "level_add"                          # the pre-registered tie rule: simpler wins
    return "level_add" if float(d.mean()) > 0 else "level_affine"


def comparability_verdict(*, harness_ok: bool, gap_detected: bool | None,
                          max_mde_ppr: float | None, winner: str | None,
                          winner_clauses: dict[str, bool | None] | None,
                          swap_state: str | None) -> dict:
    """The four-state rule (prereg §5). `winner_clauses` maps ARM_CLAUSES → bool (a None clause
    is UNEVALUABLE and refuses — never a pass, NF1.7 (a)); `swap_clause` may be None when the
    swap check is INACTIVE_EVERYWHERE, in which case it neither passes nor refuses the arm (the
    clause had nothing to act on) — every other None refuses."""
    if not harness_ok or gap_detected is None:
        state, reason = V_UNDEFINED, ("a reproduction pin failed, a position was skipped, or "
                                      "family A could not evaluate — the harness did not run; "
                                      "never read as any verdict (NF1.7 (a))")
    elif gap_detected is False:
        state = V_COMPARABLE
        reason = (f"no pairwise generator level gap survives BH(q={BH_Q}) over the 6 position "
                  f"contrasts; the four generators sit on a common scale at the stated MDE "
                  f"(max pairwise MDE {max_mde_ppr} PPR at 80% power). `identity` ships; this is "
                  f"'no artifact larger than the MDE', never 'no artifact' (MH2.6).")
    else:
        missing = [] if winner_clauses else list(ARM_CLAUSES)
        failing = []
        if winner_clauses:
            for c in ARM_CLAUSES:
                v = winner_clauses.get(c)
                if c == "swap_clause" and v is None:
                    continue                        # INACTIVE_EVERYWHERE: nothing to act on
                if v is None:
                    missing.append(c)
                elif not v:
                    failing.append(c)
        if winner is not None and not failing and not missing:
            state = V_REMOVED
            reason = (f"the level gap is real and `{winner}` removes it under every admissibility "
                      f"clause (prereg §5.2 (a)–(g)); the input ships with `{winner}` applied to "
                      f"the ranking point only — banks untouched, certified PIT preserved by "
                      f"identity")
        else:
            state = V_UNREPAIRED
            reason = (f"the level gap is real and no registered arm is admissible "
                      f"(winner={winner}, failing={failing}, unevaluable={missing}) — the hybrid "
                      f"is NOT cross-rankable as-is; the input ships as `identity` with the "
                      f"per-position gap DISCLOSED (`level_gap_disclosure`) and flagged "
                      f"not-cross-rankable")
    return {"state": state, "reason": reason, "gap_detected": gap_detected,
            "max_mde_ppr": max_mde_ppr, "winner": winner, "swap_state": swap_state,
            "qb_consumption": QB_CONSUMPTION, "second_reader": SECOND_READER}
