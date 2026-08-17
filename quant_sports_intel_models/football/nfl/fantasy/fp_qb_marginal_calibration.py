"""fp_qb_marginal_calibration.py — NF-W7f: the QB MARGINAL-layer zero-mass recalibration on the
NF-W6d 52-cell substrate (pure).

THE STORY IN ONE PARAGRAPH. NF-W7e CONFIRMED, by measurement rather than inference, that QB's PIT
ceiling is set by the MARGINAL layer: the installed Bernoulli atom is Σ-invariant to the last digit
(0.267125 under Σ_all and under Σ_played, max fold gap 0.0), the per-stat marginals ADMIT at most
`mean_i min_j P̂_j(0)` = **0.2687** of atom against a realized all-zero rate of **0.5162**, and the
marginal-admissible clamp binds on **91.7%** of QB rows. Three stories (NF-W7c/W7d/W7e) exercised
every joint-layer knob — split on/off × Σ_all/Σ_played, plus the comonotone ceiling — and the best
PIT any real arm posts at QB is 0.064 against a 0.05 bar. NF-W7e §12.5 names the ONLY remaining
route: *"the cells that bind it are identifiable from the served map (the leg with the least zero
mass on each row). This is the ONLY route to a calibrated assembled QB distribution."* This story
takes it. ⛔ It opens NO joint-layer knob: Σ is the incumbent's `FA.position_sigma` on all train
rows, the mixture machinery and π̂ estimator are NF-W7d's by identity, and the ONLY thing that
varies across the declared family is **the per-leg zero-mass TARGET of the QB marginals**.

WHY A MARGINAL CAN UNDER-PRICE ITS OWN ZERO. The all-zero event has a COMMON CAUSE — a player who
did not take a snap has every leg at zero — but the 52 substrate cells are fitted INDEPENDENTLY and
none of them knows about the others. A cell whose form places little mass at exactly zero therefore
caps `min_j P̂_j(0)` for the whole row, and the assembled atom with it. The suspected binding cell is
identifiable from the COMMITTED records before this run scores anything: the NF-W6c serving record
puts `QB|passing_yards` at `p_zero_mean` **0.3295**, the lowest QB leg by a wide margin and a leg
the gate league PRICES, against ≥0.53 for every other QB leg (`QB|attempts` 0.556, `QB|carries`
0.534, `QB|passing_interceptions` 0.798, everything else ≥0.92). ⛔ That is a HYPOTHESIS read off a
89-row serving proof, not a finding — so the runner MEASURES the per-leg zero mass, the realized
per-leg zero rate and the row-wise argmin (which leg actually binds each row) as a first-class
diagnostic, and the record reports what bound the cap rather than what was expected to.

THE TRANSFORM. `resplice_zero_mass(banks, targets)` re-weights each leg's ATOM and preserves its
CONDITIONAL-ON-POSITIVE law exactly: the new quantile function is 0 below the target and, above it,
the original evaluated at the matched conditional level. It is a pure marginal reweighting — no
learner, no refit, no new feature. It is **RAISE-ONLY** (a target below a leg's own atom is a no-op:
lowering would require inventing positive mass the source never expressed, and because the cap is a
row-wise MIN only raising can lift it — so the cap can never move backwards), and it carries three
MEASURED identities rather than an assertion:
  · `zero_mass_hits_target`  — the recalibrated bank, RE-READ through the public atom reader, carries
                               exactly the atom the raise-only rule asked for;
  · `positive_law_drift`     — the conditional-on-positive law moved by no more than the resolution
                               a raised atom necessarily costs (a counting Kolmogorov distance
                               against a derived bound, so a RESHAPE is refused);
  · `matched_foil_identity`  — re-splicing to a bank's OWN atom is BYTE-IDENTICAL through
                               `FA.draw_legs`.
⭐ That last one is what makes NF-W7e's own arm the EXACT matched foil: `mixall_learned − zm_*` is the
marginal recalibration with the joint construction, the π̂ fit and the draw stream all held fixed.
⛔ All three were RED before they were green — the first cut of this module zeroed a leg's
sub-threshold knots (which changed an integer leg's interpolation ramp and flipped draws 1→0),
allowed a target off the bank's grid (which misaligned the conditional levels), allowed a target to
LOWER an atom (which the identity caught as a 0.43 gap), and measured the conditional law by
INVERTING a staircase (which reported a 0.835 tie artifact). Every one was found by an identity
going red, and every fix was to the CONSTRUCTION, never to the tolerance (E2.1-r).

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 CHALLENGER: promotes nothing,
publishes nothing, retrains nothing, serves nothing. Every emitted string is a calibrated RANGE —
never an edge / ROI / win-rate claim.

Pure module — no lake IO, no S3, no boto3. Runner: `run_nf_w7f_qb_marginal.py`.
"""
from __future__ import annotations

import numpy as np

from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA
from quant_sports_intel_models.football.nfl.fantasy import fp_availability_mixture as MX
from quant_sports_intel_models.football.nfl.fantasy import fp_availability_split_allrows as SA

# ── Pre-registration constants (the runner READS these — NF-D16) ────────────────────────────────
STORY = "NF-W7f"
PREDECESSOR = SA.STORY                           # NF-W7e — whose arm is this story's matched foil
TARGET = FA.TARGET                               # `league_fantasy_points`
SELECTION_METRIC = FA.SELECTION_METRIC           # `crps_q199` — ranks; PIT gates (SA/MX, inherited)
GATE_STATISTIC = SA.GATE_STATISTIC               # `randomized_pit_max_decile_dev`

#: ⭐ SCOPE: **QB ONLY**. The card gates QB and names an RB certificate as a SEPARATE prerequisite
#: for the four-position optimizer input (NF-W8). NF-W7e already certified WR; RB and TE returned
#: `GENUINE_ABSENCE` against NF-W7d's own arm there. ⛔ RB/WR/TE are NOT scored here and NOT
#: reported — a position this story does not run cannot be read as evidence in either direction
#: (NF1.7 (a)), and a report-only result may never be re-classified into shippability (E2.1-r).
#: The BH family therefore carries ONE member; that is the declared scope, not a multiplicity dodge,
#: and it is stated on the verdict so a reader prices it.
GATE_POSITIONS: tuple[str, ...] = ("QB",)
POSITIONS: tuple[str, ...] = ("QB",)
CAP_POSITION = "QB"

LEGS, N_LEGS, EVAL_LEVELS, N_LEVELS = FA.LEGS, FA.N_LEGS, FA.EVAL_LEVELS, FA.N_LEVELS
INTEGER_LEGS = FA.INTEGER_LEGS
MIN_ESTIMATION_ROWS = FA.MIN_ESTIMATION_ROWS
ASSEMBLY_DRAWS = FA.ASSEMBLY_DRAWS
ROW_BLOCK = FA.ROW_BLOCK

#: ⭐ THE DRAW SEED IS INHERITED, THREE TIMES OVER. NF-W7d inherited NF-W7c's seed; NF-W7e inherited
#: both that and NF-W7d's availability-stream offset. This story inherits the whole chain, so
#: `single_copula` reproduces NF-W7c AND `mixall_learned` reproduces NF-W7e — per fold, to 1e-9 —
#: and every arm, foil and anchor of a fold transforms the SAME base normals (common random
#: numbers), so an arm-vs-foil difference is the marginal recalibration and nothing else. Nothing
#: can be shopped by keeping it: no recalibrated arm has ever been scored under this seed.
_SEED = SA._SEED
AVAIL_STREAM_OFFSET = SA.AVAIL_STREAM_OFFSET

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The zero-mass reweighting — the ONE transform this story introduces
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: The highest zero mass a target may name. The bank's grid tops out at `EVAL_LEVELS[-1]`; a target
#: at or above it would leave the leg with no positive knot at all — a degenerate point mass, not a
#: recalibration. Clipped rather than raised, and the clipping SHARE is reported per fold.
MAX_ZERO_TARGET = float(EVAL_LEVELS[-1])         # 0.995
#: The bank grid's own step in probability — derived from `EVAL_LEVELS`, never typed.
GRID_STEP = float(EVAL_LEVELS[1] - EVAL_LEVELS[0])

#: Tolerances. ⛔ None is a knob. The first two are EXACT identities of the construction (float
#: noise only — `snap_to_grid` puts the target ON the bank's grid, which makes the atom re-read
#: exactly and the no-op byte-identical). The third is a RATIO against a DERIVED resolution bound,
#: not a bar on a raw number: raising an atom to `t` leaves `(1 − t)·199` knots for the positive
#: part, so a conditional CDF can shift by up to one grid step at each end no matter how correct
#: the transform is — `positive_law_drift` reports the raw drift, the bound and the ratio, and the
#: ratio is what binds. ⛔ The first cut of that clause used a flat VALUE tolerance, went RED at
#: every magnitude, and the honest fix was the MEASUREMENT, never the bar (E2.1-r).
ZERO_MASS_TOLERANCE = 1e-12
NO_OP_TOLERANCE = 0.0
MAX_POSITIVE_LAW_DRIFT_RATIO = 1.0
#: The fewest positive knots a cell must retain for its conditional law to be COMPARABLE. Derived,
#: not tuned: a conditional CDF represented on `k` knots cannot be compared with one on 199 to
#: better than `1/k` of probability, so below 10 knots the comparison is UNEVALUABLE (0.1) rather
#: than informative — and an unevaluable check is never a pass (NF1.7 (a)).
MIN_CONDITIONAL_KNOTS = 10

# ── The availability decomposition's buckets (REPORTED, never gated) ────────────────────────────
#: ⭐ FIXED, ABSOLUTE π̂ edges — ⛔ deliberately NOT per-fold quantiles. Quantile edges are computed
#: from each fold's own π̂ distribution, so "bucket k" describes a DIFFERENT population on every
#: fold and an 8-fold pool of them measures the fold-to-fold movement of the edges as much as the
#: effect (the NF1.8 "a per-group figure must pool over ROWS, not average per-class means" lesson,
#: one axis over — and the first cut of this table used quartiles, which is why it is called out).
#: With fixed edges a bucket is the same population on every fold, so the pool is exact.
PI_BUCKET_EDGES: tuple[float, ...] = tuple(round(0.1 * k, 2) for k in range(11))
#: A bucket thinner than this cannot carry a sign, so its pooled delta is reported as `None` and it
#: can never supply a crossover — an unevaluable cell is never a reading (NF1.7 (a)).
MIN_BUCKET_ROWS = 30

#: ⭐ The per-leg threshold below which a DRAW realizes as zero — derived from `FA.INTEGER_LEGS`,
#: the same source `MX.leg_zero_mass` derives its own from, because `FA.draw_legs` ROUNDS integer
#: legs (so a bank value below 0.5 draws as a zero and IS removable mass) and FLOORS every leg at 0
#: (so a negative yardage knot draws as a zero too). ⛔ Not a second copy of a rule: a guard
#: constructs a bank at a known level and asserts this threshold and `MX.leg_zero_mass` agree, so a
#: change to the rounding convention in `FA` goes RED here rather than silently mis-reading an atom.
ZERO_THRESHOLD: np.ndarray = np.array(
    [0.5 if leg in INTEGER_LEGS else 0.0 for leg in LEGS], dtype=float)

#: The measured zero mass of a leg's bank — MX's reader, BY IDENTITY (the quantity `pi_floor` and
#: therefore the atom cap are built from; a second implementation is the NF-C0e wrong-key class).
leg_zero_mass = MX.leg_zero_mass
pi_floor = MX.pi_floor
atom_cap = SA.atom_cap
total_zero_mass = SA.total_zero_mass


def snap_to_grid(t: np.ndarray) -> np.ndarray:
    """A zero-mass target rounded DOWN onto the bank's own 199-level grid.

    ⭐ LOAD-BEARING, and found by the positive-law identity going RED. A bank can only place an atom
    at a level it carries, so a target off the grid is installed at the nearest level BELOW it —
    which leaves the recalibrated bank's conditional-on-positive levels misaligned from the
    original's by up to one grid step, and near a steep part of a quantile function one step of
    probability is a large change in value (measured: a relative deviation of 1.04 at the first
    conditional percentile of an event leg, where the conditional law lives on ~4 knots). SNAPPING
    the target first makes the reparameterization map level-for-level, so the conditional law is
    preserved EXACTLY rather than to the grid's resolution.

    Rounding DOWN, not to nearest, so the installed atom never EXCEEDS what the arm asked for —
    every approximation in this module is taken in the direction that under-states the effect."""
    a = np.asarray(t, dtype=float)
    idx = np.searchsorted(EVAL_LEVELS, a, side="right") - 1
    return np.where(idx >= 0, EVAL_LEVELS[np.clip(idx, 0, N_LEVELS - 1)], 0.0)


def realized_zero(raw: np.ndarray) -> np.ndarray:
    """(n, 13) bool — did each leg REALIZE as zero, on the same threshold the draw path uses?

    `FA.draw_legs` rounds integer legs and floors every leg at 0, so a realized rushing_yards of
    −3 and a realized 0 are the SAME assembled outcome. Reading the realized zero any other way
    would compare a marginal's atom against a differently-defined event."""
    r = np.asarray(raw, dtype=float)
    if r.ndim != 2 or r.shape[1] != N_LEGS:
        raise ValueError(f"realized matrix is {r.shape}, expected (n, {N_LEGS})")
    return r <= ZERO_THRESHOLD[None, :]


def resplice_zero_mass(banks: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """(n, 13, 199) banks + (n, 13) target zero masses → banks whose ATOM is the target and whose
    CONDITIONAL-ON-POSITIVE law is the original's, unchanged.

    The construction, in one line: for a new level `v`, the conditional-positive level is
    `(v − t)/(1 − t)`, and the ORIGINAL level carrying that same conditional level is
    `u = p̂ + (1 − p̂)·(v − t)/(1 − t)`, where `p̂ = leg_zero_mass(bank)` is the bank's own atom read
    the way the draw path reads it. So `Q*(v) = 0` for `v ≤ t` and `Q*(v) = Q(u(v))` above — a
    monotone reparameterization of the positive part, with the atom re-weighted and NOTHING ELSE
    touched. No learner, no refit, no feature: this is a calibration of one number per (row, leg).

    ⭐ AT `t == p̂` THIS IS A NO-OP, BYTE-FOR-BYTE. `u(v) = v` identically so the mapped knots come
    back unchanged, and the knots at or below `p̂` are LEFT AT THEIR ORIGINAL VALUES — which is the
    load-bearing detail, found by the identity below going RED. Overwriting them with 0.0 looks
    harmless (the draw path rounds an integer leg and floors every leg, so a knot at 0.41 already
    draws as 0) but it is NOT: `sample_from_bank` INTERPOLATES, so flattening the last
    sub-threshold knot changes the ramp into the first positive knot and a draw just above the atom
    flips 1 → 0. Measured on synthetic banks: a max draw gap of 1.0 on 7 of 13 legs. So only the
    NEWLY ADDED atom — the levels in `(p̂, t]` — is written, and it is written at the source's own
    last sub-threshold value floored at 0, which keeps the bank monotone and still draws as zero.
    That identity is what makes NF-W7e's own arm the EXACT matched foil rather than a
    differently-implemented one, and it is MEASURED per fold (`matched_foil_identity`), never
    assumed — the NF-W7d RED-proof lesson (a diagnostic that validates its own copy of the logic
    validates nothing).

    ⚠️ Two edges, both taken in the direction that UNDER-states the story's effect:
      · `p̂ = 0` (no knot at or below the threshold — the signature of a continuous leg with no
        atom, which is the defect under repair): `u` runs from 0, and `np.interp` clamps below the
        grid's first level, so the very bottom of the positive part is flattened to `Q(0.005)`.
      · `t < p̂` (a target LOWERING the atom — reachable only by the row-blind arm): `u` can exceed
        the grid's last level and the top knot flattens. The share of (row, leg) cells in each edge
        is REPORTED per fold rather than silently absorbed."""
    b = np.asarray(banks, dtype=float)
    if b.ndim != 3 or b.shape[1] != N_LEGS or b.shape[2] != N_LEVELS:
        raise ValueError(f"banks are {b.shape}, expected (n, {N_LEGS}, {N_LEVELS})")
    t = np.asarray(targets, dtype=float)
    if t.shape != b.shape[:2]:
        raise ValueError(f"targets are {t.shape}, expected {b.shape[:2]} — one zero mass per "
                         f"(row, leg)")
    if not np.all(np.isfinite(t)):
        raise ValueError("a zero-mass target is non-finite — a probability that is not a "
                         "probability is a coding defect, not an arm")
    p_hat = leg_zero_mass(b)
    # ⭐ RAISE-ONLY, and it must actually BE monotone (NF1.7 (d) (4): "a widen-only knob must
    # actually be monotone — clamp so it can only widen"). LOWERING an atom would require inventing
    # positive mass the source model never expressed, which is a RESHAPE, not a recalibration; and
    # because the cap is a row-wise MIN over legs, only RAISING can lift it. So a target below the
    # source's own atom is a no-op on that leg, the share is REPORTED (`resplice_edges`), and the
    # cap can never move backwards. ⛔ Declared, not incidental: the first cut let a target lower an
    # atom, the sub-threshold values it preserves then pinned the re-read atom at `p̂` anyway, and
    # `zero_mass_hits_target` went RED with a 0.43 gap — the clause catching the transform's own
    # undeclared direction.
    t = np.maximum(snap_to_grid(np.clip(t, 0.0, MAX_ZERO_TARGET)), p_hat)
    lv = EVAL_LEVELS[None, None, :]
    frac = np.clip((lv - t[:, :, None]) / np.clip(1.0 - t, 1e-12, None)[:, :, None], 0.0, 1.0)
    u = p_hat[:, :, None] + (1.0 - p_hat)[:, :, None] * frac
    # ⭐ EXACTNESS OF THE NO-OP: where no new atom is added the level map is the identity, and it is
    # written as the identity rather than computed through the affine map — `p̂ + (1−p̂)·(v−p̂)/(1−p̂)`
    # equals `v` in exact arithmetic but drifts ~1e-13 in floats, which at yardage scale survives
    # into the draw and cost the byte-identical matched-foil claim (measured: a non-zero draw gap on
    # the continuous legs). The matched-foil argument rests on this being EXACT, so it is exact.
    u = np.where(t[:, :, None] > p_hat[:, :, None], u, lv)
    mapped = np.empty_like(b)
    for i in range(b.shape[0]):
        for j in range(N_LEGS):
            mapped[i, j] = np.interp(u[i, j], EVAL_LEVELS, b[i, j])
    # the value the NEWLY added atom is written at: the source's own last sub-threshold knot,
    # floored at 0 (0.0 outright when the source carries no atom). Sub-threshold by construction,
    # so it still DRAWS as zero, and ≥ every knot it sits above, so the bank stays monotone.
    idx = (b <= ZERO_THRESHOLD[None, :, None]).sum(axis=2) - 1
    block = np.clip(np.take_along_axis(b, np.clip(idx, 0, N_LEVELS - 1)[:, :, None],
                                       axis=2)[:, :, 0], 0.0, None)
    block = np.where(idx >= 0, block, 0.0)[:, :, None]
    below_source = lv <= p_hat[:, :, None]
    new_atom = (~below_source) & (lv <= t[:, :, None])
    return np.where(below_source, b, np.where(new_atom, block, mapped))


def resplice_edges(banks: np.ndarray, targets: np.ndarray) -> dict:
    """The share of (row, leg) cells in each of `resplice_zero_mass`'s two flattening edges, and
    the share whose target was CLIPPED at `MAX_ZERO_TARGET` — reported, never absorbed."""
    b, t = np.asarray(banks, dtype=float), np.asarray(targets, dtype=float)
    p_hat = leg_zero_mass(b)
    n = float(p_hat.size) or 1.0
    return {
        "share_no_atom_in_source": round(float((p_hat <= 0.0).sum()) / n, 4),
        # a target BELOW the source's own atom: the RAISE-ONLY rule makes it a no-op on that leg
        "share_target_below_source_ignored": round(float((snap_to_grid(
            np.clip(t, 0.0, MAX_ZERO_TARGET)) < p_hat - 1e-12).sum()) / n, 4),
        "share_target_clipped": round(float((t > MAX_ZERO_TARGET).sum()) / n, 4),
        "mean_target": round(float(np.clip(t, 0.0, MAX_ZERO_TARGET).mean()), 4),
        "mean_source_zero_mass": round(float(p_hat.mean()), 4),
    }


# ── The three MEASURED identities of the transform (§5 clauses; none restates the code) ──────────
def zero_mass_hits_target(banks: np.ndarray, targets: np.ndarray,
                          recal: np.ndarray) -> dict:
    """Re-read the RECALIBRATED bank through the PUBLIC reader and compare against the grid level
    the target names. Not a restatement of the transform: it goes back through `leg_zero_mass` —
    the very function `pi_floor` and the atom cap are built from — so a splice that installs a
    different atom than it claims (a wrong `p̂`, an off-by-one on the grid, an inverted direction)
    goes RED here rather than shipping a cap that the mixture then silently clamps against."""
    # the atom the RAISE-ONLY rule actually asks for, derived from the arm's target and the SOURCE
    # bank (never from the transform's internals — the check re-reads the RESULT below)
    want = np.maximum(
        snap_to_grid(np.clip(np.asarray(targets, dtype=float), 0.0, MAX_ZERO_TARGET)),
        leg_zero_mass(np.asarray(banks, dtype=float)))
    got = leg_zero_mass(np.asarray(recal, dtype=float))
    gap = float(np.max(np.abs(got - want))) if got.size else 0.0
    return {"max_abs_gap": round(gap, 12), "holds": bool(gap <= ZERO_MASS_TOLERANCE),
            "mean_installed": round(float(got.mean()), 4) if got.size else None,
            "mean_requested": round(float(want.mean()), 4) if want.size else None}


def conditional_quantiles(bank: np.ndarray, levels: np.ndarray) -> np.ndarray:
    """(n, 13, len(levels)) each leg's CONDITIONAL-ON-POSITIVE quantile function, read through the
    bank's OWN measured atom: `Q_cond(c) = Q(p + (1 − p)·c)` with `p = leg_zero_mass(bank)`.

    Deliberately reads the bank through the PUBLIC atom reader and `np.interp` — the same two steps
    the draw path uses — so a comparison built on it never consults the transform's internals (the
    NF-C0e "a test that reads a value back under the key the code writes" class)."""
    x = np.asarray(bank, dtype=float)
    c = np.asarray(levels, dtype=float)
    p = leg_zero_mass(x)
    lv = p[:, :, None] + (1.0 - p)[:, :, None] * c[None, None, :]
    out = np.empty(lv.shape, dtype=float)
    for i in range(x.shape[0]):
        for j in range(N_LEGS):
            out[i, j] = np.interp(lv[i, j], EVAL_LEVELS, x[i, j])
    return out


def positive_law_drift(banks: np.ndarray, recal: np.ndarray) -> dict:
    """How far the CONDITIONAL-ON-POSITIVE law moved, in **PROBABILITY** units, against the
    RESOLUTION BOUND that raising an atom necessarily costs.

    ⭐ WHY PROBABILITY UNITS AND WHY A DERIVED BOUND RATHER THAN A FLAT BAR — the first cut of this
    clause measured a VALUE deviation against a flat 2%-of-inter-decile-range bar and went RED at
    every target magnitude, including a target one grid step above the source. That was not a bug in
    the transform: the bank is a FIXED 199-level grid, so installing an atom of `t` leaves only
    `(1 − t)·199` knots for the positive part. The conditional law is preserved as a DISTRIBUTION and
    represented more COARSELY — and on an event leg whose positive part is ~4 knots, one step of
    probability is a large step in value. A flat value tolerance therefore measures the grid, not the
    transform, and "tighten it until it passes" would be the E2.1-r inversion.
    So: the deviation is the sup distance between the two conditional CDFs (`max_c |c − F_o(Q_n(c))|`,
    a Kolmogorov distance, the same units `MX.mixture_marginal_drift` reports), and the tolerance is
    the resolution the NEW atom leaves — `2 × 0.005 / (1 − t)`, one grid step at each end. Both the
    raw drift and the bound are reported, so a reader can re-derive under another rule (NF-D14).

    ⛔ IT STAYS FALSIFIABLE, which is the whole point: a splice that RESHAPED a marginal instead of
    re-weighting its atom — a refit wearing a recalibration's badge, the one thing §1 forbids —
    moves the conditional CDF by far more than the grid spacing, and is REFUSED. A guard that could
    not fail would be the vacuous-guard class (NF1.7 (a) / INC-38)."""
    b, r = np.asarray(banks, dtype=float), np.asarray(recal, dtype=float)
    c = EVAL_LEVELS
    qo, qn = conditional_quantiles(b, c), conditional_quantiles(r, c)
    # ⭐ A COUNTING Kolmogorov distance, because the legs are DISCRETE. Both conditional quantile
    # functions are sampled at the same 199 conditional levels, so each is an equally-weighted
    # 199-point representation of its own conditional law and `#{q ≤ x}/199` is its CDF — exactly,
    # with no interpolation and no inversion. ⛔ The first cut INVERTED one quantile function through
    # the other (`np.interp(qn, qo, c)`), which is ill-posed on a staircase: a count leg's
    # conditional law is flat over long runs (0, 1, 2, 3 touchdowns), the inverse lands anywhere on
    # the flat, and the clause reported a 0.835 "drift" that was entirely tie artifact. Counting is
    # tie-immune.
    nlv = float(len(c))
    drift = np.zeros(b.shape[:2], dtype=float)
    for i in range(b.shape[0]):
        for j in range(N_LEGS):
            a, z = np.sort(qo[i, j]), np.sort(qn[i, j])
            xs = np.concatenate((a, z))
            fo = np.searchsorted(a, xs, side="right") / nlv
            fn = np.searchsorted(z, xs, side="right") / nlv
            drift[i, j] = float(np.max(np.abs(fo - fn)))
    p_new = leg_zero_mass(r)
    bound = 2.0 * GRID_STEP / np.clip(1.0 - p_new, GRID_STEP, None)
    # ⛔ DEGENERATE cells are UNEVALUABLE, never a pass (NF1.7 (a)). A leg whose atom is ~0.995 has
    # ONE positive knot: its conditional law is a point mass, inverting a constant function returns
    # the first level for every input, and the "drift" is then an artifact (measured 0.99 on
    # synthetic banks) that would buy the clause slack it has not earned. So the comparison runs on
    # cells whose conditional law both banks resolve — ≥ MIN_CONDITIONAL_KNOTS knots and non-flat —
    # and the EXCLUDED share is reported rather than silently absorbed.
    n_pos = np.minimum((1.0 - p_new), (1.0 - leg_zero_mass(b))) * N_LEVELS
    ok = (n_pos >= MIN_CONDITIONAL_KNOTS) & ((qo[:, :, -1] - qo[:, :, 0]) > 0.0)
    ratio = np.where(ok, drift / np.clip(bound, 1e-12, None), 0.0)
    worst = float(ratio.max()) if ratio.size and ok.any() else 0.0
    return {"max_probability_drift": round(float(drift[ok].max()) if ok.any() else 0.0, 6),
            "mean_probability_drift": round(float(drift[ok].mean()) if ok.any() else 0.0, 6),
            "max_resolution_bound": round(float(bound[ok].max()) if ok.any() else 0.0, 6),
            "max_drift_over_bound": round(worst, 6),
            "evaluable_cell_share": round(float(ok.mean()) if ok.size else 0.0, 4),
            "min_conditional_knots": MIN_CONDITIONAL_KNOTS,
            "tolerance_ratio": MAX_POSITIVE_LAW_DRIFT_RATIO,
            # an ALL-degenerate comparison did not run — it must not read as a pass
            "evaluated": bool(ok.any()),
            "holds": bool(ok.any() and worst <= MAX_POSITIVE_LAW_DRIFT_RATIO)}


def matched_foil_identity(banks: np.ndarray, *, draws: int = 64, seed: int = 0) -> dict:
    """⭐ The identity that makes NF-W7e's arm the EXACT matched foil: re-splicing a bank to its OWN
    measured zero mass must leave `FA.draw_legs` byte-identical.

    Measured on the DRAW path, not on the knots, because the draw path is what the assembly scores
    — and because the knots at or below the threshold legitimately differ (a negative yardage knot
    becomes 0), while the draws cannot, since `draw_legs` already floors at 0. A harness in which
    this fails is one where `zm_* − mixall_learned` is measuring the transform's own arithmetic
    rather than the recalibration."""
    b = np.asarray(banks, dtype=float)
    same = resplice_zero_mass(b, leg_zero_mass(b))
    rng = np.random.default_rng(seed)
    u = rng.random((b.shape[0], draws, N_LEGS))
    gap = float(np.max(np.abs(FA.draw_legs(b, u) - FA.draw_legs(same, u)))) if b.size else 0.0
    return {"max_abs_draw_gap": round(gap, 12), "holds": bool(gap <= NO_OP_TOLERANCE),
            "n_rows": int(b.shape[0]), "draws": int(draws)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The zero-mass TARGETS — the one quantity the declared family varies
# ══════════════════════════════════════════════════════════════════════════════════════════════
def conditional_zero_rate(raw: np.ndarray) -> np.ndarray:
    """(13,) the TRAIN realized `P(leg = 0 | the player was active)`, per leg.

    Estimated on ACTIVE rows only (`MX.activity_indicator`), because the two-part reconstruction
    needs the played-but-recorded-nothing rate separately from the inactivity rate — a QB who plays
    still throws no interception most weeks, and that zero is NOT an availability zero.

    ⛔ Refuses below the estimation floor rather than defaulting: a conditional rate estimated on a
    handful of rows would be a made-up number wearing an estimate's badge (NF1.7 (a))."""
    z = realized_zero(raw)
    act = np.asarray(activity_indicator(np.asarray(raw, dtype=float)), dtype=bool)
    if int(act.sum()) < MIN_ESTIMATION_ROWS:
        raise ValueError(f"{int(act.sum())} active rows is below the estimation floor "
                         f"({MIN_ESTIMATION_ROWS}) — the conditional zero rate is REFUSED, not "
                         f"defaulted")
    return z[act].mean(axis=0)


def marginal_zero_rate(raw: np.ndarray) -> np.ndarray:
    """(13,) the TRAIN realized `P(leg = 0)`, per leg — over ALL rows, active or not. The row-blind
    arm's target, and the yardstick the per-leg diagnostic compares each bank's own atom against."""
    r = np.asarray(raw, dtype=float)
    if len(r) < MIN_ESTIMATION_ROWS:
        raise ValueError(f"{len(r)} rows is below the estimation floor ({MIN_ESTIMATION_ROWS}) — "
                         f"the marginal zero rate is REFUSED, not defaulted")
    return realized_zero(r).mean(axis=0)


def zero_targets(arm: str, *, banks: np.ndarray, pi_hat: np.ndarray, cond_rate: np.ndarray,
                 marg_rate: np.ndarray) -> np.ndarray:
    """(n, 13) the arm's per-(row, leg) zero-mass target — the ONLY thing the family varies.

    Every arm is a function of the SAME inputs (the served banks, NF-W7d's learned π̂, and the two
    TRAIN realized rates), so the family is coherent by construction and no arm can quietly reach
    for information another cannot see. `q̂ = 1 − π̂` is the estimated INACTIVITY probability."""
    b = np.asarray(banks, dtype=float)
    q = 1.0 - np.clip(np.asarray(pi_hat, dtype=float), 0.0, 1.0)
    if q.shape != (b.shape[0],):
        raise ValueError(f"pi is {q.shape}, expected ({b.shape[0]},) — one availability "
                         f"probability per row")
    cond = np.asarray(cond_rate, dtype=float)
    marg = np.asarray(marg_rate, dtype=float)
    if cond.shape != (N_LEGS,) or marg.shape != (N_LEGS,):
        raise ValueError(f"the train zero rates are {cond.shape}/{marg.shape}, expected "
                         f"({N_LEGS},) each — one rate per leg")
    if arm == "zm_conditional":
        # zero if inactive, OR active-and-still-nothing: q + (1 − q)·p̂₊
        return q[:, None] + (1.0 - q)[:, None] * cond[None, :]
    if arm == "zm_floor":
        # the minimal intervention: lift ONLY the legs that under-price inactivity
        return np.maximum(leg_zero_mass(b), q[:, None])
    if arm == "zm_climatology":
        # row-BLIND: the leg's train realized rate, identical on every row
        return np.broadcast_to(marg[None, :], b.shape[:2]).copy()
    if arm == "zm_over":
        qo = np.clip(OVER_SCALE * q, 0.0, 1.0)
        return qo[:, None] + (1.0 - qo)[:, None] * cond[None, :]
    raise KeyError(f"unknown zero-mass arm `{arm}` — not in the pre-registered family {REAL_ARMS}")


def binding_leg_share(banks: np.ndarray) -> dict[str, float]:
    """Which leg ATTAINS the row-wise `min_j P̂_j(0)` — i.e. which cell caps the atom, per row.

    ⭐ The diagnostic that makes this story's premise auditable instead of assumed. NF-W7e named the
    binding cell as identifiable "from the served map (the leg with the least zero mass on each
    row)"; the NF-W6c serving record puts `QB|passing_yards` lowest at 0.3295 on an 89-row proof.
    This MEASURES it on every fold, so the record reports which cell actually bound the cap."""
    z = leg_zero_mass(np.asarray(banks, dtype=float))
    if z.size == 0:
        return {}
    arg = np.asarray(z).argmin(axis=1)
    n = float(len(arg))
    return {leg: round(float((arg == i).sum()) / n, 4) for i, leg in enumerate(LEGS)
            if int((arg == i).sum()) > 0}


def leg_zero_mass_table(banks: np.ndarray, raw: np.ndarray) -> dict[str, dict]:
    """Per leg: the mean zero mass the served bank carries vs the realized zero rate on the same
    rows, and the gap. The premise of the whole story in one table — a leg whose `predicted` sits
    well below its `realized` is a cell that under-prices its own atom."""
    z = leg_zero_mass(np.asarray(banks, dtype=float))
    r = realized_zero(raw)
    return {leg: {"predicted_zero_mass": round(float(z[:, i].mean()), 4),
                  "realized_zero_rate": round(float(r[:, i].mean()), 4),
                  "gap_realized_minus_predicted": round(float(r[:, i].mean() - z[:, i].mean()), 4)}
            for i, leg in enumerate(LEGS)}


def bucket_by_availability(delta_per_row: np.ndarray, pi_hat: np.ndarray) -> dict:
    """Bucket a per-ROW quantity onto `PI_BUCKET_EDGES`, returning SUMS and COUNTS — never means.

    Sums-and-counts is the whole point: a fold contributes its raw numerator and denominator, so
    pooling across folds is `Σsums / Σcounts` = the exact row-pooled mean. A fold that returned
    per-bucket MEANS could only be pooled as a mean-of-means, which silently re-weights a thin fold
    equal to a fat one (NF1.8)."""
    d = np.asarray(delta_per_row, dtype=float).ravel()
    p = np.asarray(pi_hat, dtype=float).ravel()
    if d.shape != p.shape:
        raise ValueError(f"delta_per_row {d.shape} and pi_hat {p.shape} must be the same length")
    nb = len(PI_BUCKET_EDGES) - 1
    idx = np.clip(np.digitize(p, np.asarray(PI_BUCKET_EDGES[1:-1], dtype=float)), 0, nb - 1)
    sums = np.bincount(idx, weights=d, minlength=nb)[:nb]
    counts = np.bincount(idx, minlength=nb)[:nb]
    return {"sums": [round(float(v), 6) for v in sums],
            "counts": [int(v) for v in counts]}


def pool_availability_buckets(per_fold: list[dict]) -> dict:
    """Pool per-fold availability buckets over ROWS and locate the SIGN CROSSOVER.

    ⭐ The successor's whole premise in one table: NF-W7f's smoke measured that the per-leg effect of
    raising a leg's atom HELPS where the player probably did not play and HURTS where he probably
    did — because the component model already prices availability internally, so an
    availability-derived target prices it twice. That claim is only worth carrying forward if it is
    MEASURED across folds with a located crossover, not asserted off one fold (the NF-W7d matched-
    foil lesson: a mechanism claim needs a paired reading, and a mechanism's LOCATION needs a
    measured one). REPORTED only — nothing gates on it."""
    nb = len(PI_BUCKET_EDGES) - 1
    if not per_fold:
        return {"state": "UNDEFINED", "reason": "no folds supplied", "edges": PI_BUCKET_EDGES,
                "counts": [0] * nb, "mean_delta": [None] * nb, "crossovers": [],
                "n_evaluable_buckets": 0, "min_bucket_rows": MIN_BUCKET_ROWS}
    sums, counts = np.zeros(nb), np.zeros(nb)
    for f in per_fold:
        s, c = np.asarray(f["sums"], dtype=float), np.asarray(f["counts"], dtype=float)
        if s.shape != (nb,) or c.shape != (nb,):
            raise ValueError(f"a fold supplied {s.shape}/{c.shape} buckets, expected ({nb},) — a "
                             f"pool over inconsistent bucketings is not a measurement")
        sums, counts = sums + s, counts + c
    means = [round(float(sums[k] / counts[k]), 5) if counts[k] >= MIN_BUCKET_ROWS else None
             for k in range(nb)]
    centers = [round(0.5 * (PI_BUCKET_EDGES[k] + PI_BUCKET_EDGES[k + 1]), 3) for k in range(nb)]
    ev = [(k, m) for k, m in enumerate(means) if m is not None]
    # ⚠️ a bucket sitting EXACTLY at zero carries no sign, so it is dropped from the SIGN walk (it is
    # still reported in `mean_delta`). Dropping it rather than treating it as a wall is what makes a
    # crossover that lands exactly on a bucket centre locatable: its neighbours become adjacent in
    # the walk and the interpolation returns that centre. Skipping the PAIR instead reported
    # `MIXED_NO_ADJACENT_CROSSING` for a textbook single crossing — caught by its own guard.
    ev_signed = [(k, m) for k, m in ev if m != 0.0]
    crossings = []
    for (k0, m0), (k1, m1) in zip(ev_signed, ev_signed[1:]):
        if (m0 > 0.0) == (m1 > 0.0):
            continue
        w = abs(m0) / max(abs(m0) + abs(m1), 1e-12)
        crossings.append({
            "between_buckets": [PI_BUCKET_EDGES[k0], PI_BUCKET_EDGES[k1 + 1]],
            "pi_hat": round(centers[k0] + w * (centers[k1] - centers[k0]), 4),
            "direction": ("helps_below_hurts_above" if m0 > 0.0 else "hurts_below_helps_above"),
            "delta_below": m0, "delta_above": m1})
    if len(ev_signed) < 2:
        state, reason = "UNDEFINED", (
            f"only {len(ev_signed)} bucket(s) reached {MIN_BUCKET_ROWS} rows AND carried a sign, so "
            f"no sign change could be located — UNEVALUABLE, never read as 'no crossover' "
            f"(NF1.7 (a))")
    elif not crossings:
        allpos = all(m > 0.0 for _, m in ev_signed)
        state = "ALL_POSITIVE" if allpos else ("ALL_NEGATIVE"
                                              if all(m < 0.0 for _, m in ev_signed)
                                              else "MIXED_NO_ADJACENT_CROSSING")
        reason = (f"the pooled per-row delta has the same sign in every evaluable bucket "
                  f"({state}) — the effect does NOT flip with availability on this population")
    elif len(crossings) == 1:
        state, reason = "CROSSES", (
            f"the pooled per-row delta changes sign once, at π̂ ≈ {crossings[0]['pi_hat']} "
            f"({crossings[0]['direction']})")
    else:
        state, reason = "NON_MONOTONE", (
            f"{len(crossings)} sign changes — the effect is not a single crossover in availability, "
            f"so a successor conditioning on a single π̂ threshold would be mis-specified")
    return {"state": state, "reason": reason, "edges": list(PI_BUCKET_EDGES),
            "counts": [int(c) for c in counts], "mean_delta": means, "bucket_centers": centers,
            "crossovers": crossings, "n_evaluable_buckets": len(ev),
            "min_bucket_rows": MIN_BUCKET_ROWS,
            "pooled_mean_delta": (round(float(sums.sum() / counts.sum()), 5)
                                  if counts.sum() > 0 else None)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The declared field (⛔ never trimmed or grown after a score — MH2 (a) / MH2.2)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: A COHERENT family: four arms that differ ONLY in the per-leg zero-mass TARGET they name, over an
#: IDENTICAL joint construction (NF-W7e's `mixall_learned`: the learned π̂ + the incumbent's all-rows
#: Σ), identical marginals-before-recalibration, identical mixture machinery and identical draw
#: stream. ⛔ Nothing about the copula, the Σ population or the availability estimator is re-opened
#: here — NF-W7e closed the joint line and this story does not re-litigate it.
#:
#:   zm_conditional ⭐ PRIMARY — the two-part reconstruction. A leg is zero if the player did not
#:                   play (probability `q̂ = 1 − π̂`, NF-W7d's learned estimator, imported) OR if he
#:                   played and still recorded nothing (the TRAIN realized rate, per leg):
#:                   `t = q̂ + (1 − q̂)·p̂₊`. It is the structurally correct marginal for a population
#:                   with an availability atom, and it is what makes the atom COMMON across legs so
#:                   the mixture can install it once instead of the clamp forbidding it.
#:   zm_floor       — the MINIMAL intervention: `t = max(P̂(0), q̂)`. It touches only the legs that
#:                   under-price inactivity and leaves every already-sufficient leg untouched, so it
#:                   isolates "is the cap the whole story?" from "are the marginals wrong?".
#:   zm_climatology — row-BLIND: `t = ` the leg's TRAIN realized zero rate, the same number for
#:                   every row. Registered SHIPPABLE per NF-D20 (a blind rule that wins is a
#:                   finding about the signal, not an anchor to be disqualified after the fact).
#:   zm_over        — the MAGNITUDE probe: the primary's target with the inactivity inflated,
#:                   `q̂′ = min(1, 1.5·q̂)`. ⭐ A REAL, SHIPPABLE arm, NOT an anchor (NF-D20 /
#:                   NF-W7b): an anchor registered to lose that then BEATS the field produces a null
#:                   while the answer sits in an ineligible cell. It is EXPECTED to lose — the
#:                   primary's predicted installed atom (≈0.514) already lands on the realized rate
#:                   (0.5162) — and if it wins, the magnitude hypothesis is REFUTED and the record
#:                   says so rather than re-labelling it.
REAL_ARMS: tuple[str, ...] = ("zm_conditional", "zm_floor", "zm_climatology", "zm_over")
PRIMARY_ARM = "zm_conditional"
#: The inflation factor of the magnitude probe. ⛔ Not tuned — 1.5 is the smallest multiple that
#: pushes the primary's predicted atom (≈0.514) clearly PAST the realized all-zero rate (≈0.516) on
#: a majority of rows, which is what makes it a test of "is more atom better?" rather than a second
#: copy of the primary.
OVER_SCALE = 1.5

#: ⭐ THE TWO CONTEST FOILS — `beats_foil` binds against these and ONLY these:
#:   mixall_learned — NF-W7e's registered QB arm, reproduced to 1e-9, and ⭐ THE MATCHED FOIL:
#:                    identical joint construction, identical π̂ fit, identical draw stream, the
#:                    marginals NOT recalibrated. `mixall_learned − zm_*` is the marginal
#:                    recalibration channel with nothing else moving (the no-op identity is what
#:                    earns that claim). It is also the CRPS-best QB construction on record —
#:                    NF-W7e beat both its foils 8/8 at QB, DSR 0.9999, refused on the PIT bar
#:                    alone — so the arm must beat the best thing that EXISTS, not merely the thing
#:                    that shipped.
#:   single_copula  — THE INCUMBENT (NF-W7c's `joint_rank`), reproduced to 1e-9. The construction
#:                    every predecessor scored against; keeping it binding makes this story's margin
#:                    comparable to NF-W7c/W7d/W7e's on the same folds and the same seed.
CONTEST_FOILS: tuple[str, ...] = ("mixall_learned", "single_copula")
MATCHED_FOIL = "mixall_learned"
INCUMBENT_FOIL = "single_copula"

#: The reproduction targets — what each foil IS in the predecessors' committed records.
INCUMBENT_RECORD_RELPATH = SA.INCUMBENT_RECORD_RELPATH        # NF-W7c
INCUMBENT_RECORD_ARM = SA.INCUMBENT_RECORD_ARM                # `joint_rank`
PREDECESSOR_RECORD_RELPATH = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                              "nf_w7e_split_allrows.json")
PREDECESSOR_RECORD_ARMS: dict[str, str] = {"mixall_learned": "mixall_learned"}

#: REFERENCE FOILS — SCORED and REPORTED; they do NOT bind `beats_foil`, and they are excluded from
#: the PBO/DSR trial field (MH2.1 (a) — a diagnostic anchor that joins the trial field sets the
#: gate's own bar). `zm_cond_copula` completes the 2×2 {recalibrated, served} × {split, no split}:
#: the PRIMARY arm's marginals under the INCUMBENT's copula, i.e. the recalibration with the
#: availability split OFF, which answers a question the gated cell cannot — does raising the
#: marginal atom pay when nothing makes that atom COMMON across legs? `assembled_indep` carries the
#: three inherited dependence clauses; `foil_direct_points` is the ARCHITECTURE question (NF-W7c
#: §11.4), never this story's gate.
REFERENCE_FOILS: tuple[str, ...] = ("zm_cond_copula", "assembled_indep", "foil_direct_points")
FOILS: tuple[str, ...] = (*CONTEST_FOILS, *REFERENCE_FOILS)
#: PBO runs over the search the selection actually ran (NF1.8): the 4 arms + the 2 contest foils.
ELIGIBLE: tuple[str, ...] = (*REAL_ARMS, *CONTEST_FOILS)

DEGENERATES: tuple[str, ...] = SA.DEGENERATES
FOILS_WITH_ORACLE: tuple[str, ...] = SA.FOILS_WITH_ORACLE
#: `zm_permuted` — the PRIMARY arm's per-row inactivity `q̂` SHUFFLED across players within a global
#: week, used consistently in BOTH the marginal target and the mixture. It preserves the population
#: LEVEL of the atom and destroys only its per-ROW assignment, so it separates "the recalibration
#: found the right rows" from "the recalibration raised the average". ⛔ Without it a row-blind level
#: shift would be indistinguishable from a per-player signal (NF-D15 (g′)).
ANCHORS: tuple[str, ...] = (
    *DEGENERATES, "permuted_direct", "zm_permuted",
    *(f"oracle__{a}" for a in REAL_ARMS), *(f"matched_n__{a}" for a in REAL_ARMS),
    *(f"oracle__{f}" for f in FOILS_WITH_ORACLE),
)
ALL_LABELS: tuple[str, ...] = (*REAL_ARMS, *FOILS, *ANCHORS)
#: labels whose coverage / PIT are stored per fold — every degenerate's PIT is printed every run,
#: which is what PROVES the bar was never promoted into a selection criterion (NF1.8 / NF-D18).
WATCHED: tuple[str, ...] = (*REAL_ARMS, *FOILS, *DEGENERATES, "zm_permuted")

# ── Gate constants — ⛔ every one INHERITED by reference (E2.1-r / NF1.8 / NF-D18) ───────────────
COVERAGE_FLOOR, COVERAGE_BLOCK_SE = SA.COVERAGE_FLOOR, SA.COVERAGE_BLOCK_SE
PBO_MAX, DSR_MIN, FDR_Q = SA.PBO_MAX, SA.DSR_MIN, SA.FDR_Q
PIT_MAX_DECILE_DEV = SA.PIT_MAX_DECILE_DEV
MIN_MIXTURE_ATOM = SA.MIN_MIXTURE_ATOM
MAX_MARGINAL_DRIFT = SA.MAX_MARGINAL_DRIFT
INCUMBENT_TOLERANCE = SA.INCUMBENT_TOLERANCE
SELECTION_IS_CRPS_NOT_PIT = SA.SELECTION_IS_CRPS_NOT_PIT
oracle_floor_state = SA.oracle_floor_state
ORACLE_RESPECTED, ORACLE_VIOLATED, ORACLE_INACTIVE = (
    SA.ORACLE_RESPECTED, SA.ORACLE_VIOLATED, SA.ORACLE_INACTIVE)
#: the mixture + Σ primitives, BY IDENTITY — one code path (NF-W7d's RED-proof lesson)
assemble_mixture_bank = SA.assemble_mixture_bank
mixture_marginal_drift = SA.mixture_marginal_drift
clamp_pi = SA.clamp_pi
pi_for_arm = SA.pi_for_arm
activity_indicator = SA.activity_indicator
atom_rate = SA.atom_rate
sigma_all = SA.sigma_all                         # ⭐ the incumbent's Σ estimator, verbatim
pit_detail, pooled_pit = SA.pit_detail, SA.pooled_pit
pit_null_reference, pit_null_pvalue = SA.pit_null_reference, SA.pit_null_pvalue
incumbent_reproduction = SA.incumbent_reproduction
#: ⛔ The joint construction is FIXED at NF-W7e's registered arm for EVERY real arm — the family
#: varies the marginal target and nothing else. Named as a constant so a future reader can see the
#: held-fixed factor without reading the runner (and so a guard can pin it).
JOINT_CONSTRUCTION = "mixall_learned"
PI_ESTIMATOR = SA.PI_ESTIMATOR_OF[SA.PRIMARY_ARM]     # NF-W7d's `mix_learned`, imported

#: ⭐ THE MECHANISM-ACTIVITY FLOOR for THIS story (NF1.9 "a mechanism that cannot act is a finding"
#: / NF1.7 (a)). The recalibration acts through ONE channel: it raises the atom cap
#: `mean_i min_j P̂_j(0)` so the mixture's clamp stops binding. If the cap does not move, every arm
#: is its own matched foil and the contest passes on nothing.
#:
#: DERIVED FROM DESIGN QUANTITIES KNOWN BEFORE THIS RUN, not tuned to a runtime or a result: the
#: pre-registered bar is a max-decile deviation of 0.05, and NF-W7e RECORDED the winner's QB first
#: decile at 0.162 — so at least `0.162 − 0.150 = 0.012` of probability mass must move out of the
#: bottom decile for ANY arm to clear the bar. A cap lift below that is structurally incapable of
#: clearing PIT, so an arm that lifts the cap by less has not turned the knob.
MIN_CAP_LIFT = 0.012
#: NF-W7e's RECORDED QB figures — the baseline this story's cap lift is measured AGAINST. ⛔ Read
#: from the committed predecessor record at run time (`predecessor_cap_baseline`), never trusted
#: from these constants: they are here so the pre-registration is legible, and a guard asserts the
#: record still carries them.
PREDECESSOR_CAP_MEAN = 0.2687
PREDECESSOR_REALIZED_ATOM = 0.5162
PREDECESSOR_CLAMP_BINDING_SHARE = 0.917
PREDECESSOR_BEST_QB_PIT = 0.064

#: ⭐ The per-leg calibration clause. Recalibrating a marginal CHANGES a NF-W6d certified cell, so
#: the story must show it did not buy the assembled atom by wrecking the parts. The check is
#: two-sided BY DESIGN: if the diagnosis (the QB legs under-price their own zero) is right, the
#: recalibrated legs' own CRPS IMPROVES; if it is wrong, this is where it shows.
#: ⛔ Pooled over the PRICED legs and expressed as a fraction of the served banks' own CRPS, so one
#: minor channel's rounding cannot refuse the story and a real degradation cannot hide inside a
#: yardage leg three orders of magnitude larger than a touchdown leg.
MAX_PER_LEG_CRPS_DEGRADATION = 0.0

STATISTICAL_CHECKS: tuple[str, ...] = SA.STATISTICAL_CHECKS
ANCHOR_CHECKS: tuple[str, ...] = (
    "degenerates_lose", "permutation_behaves", "oracle_floors_respected",
    "mixture_is_active", "mixture_preserves_marginals", "incumbent_reproduces",
    "predecessor_reproduces", "zero_mass_hits_target", "positive_law_preserved",
    "matched_foil_identity", "cap_was_lifted", "per_leg_calibration_not_degraded",
    "independence_under_disperses", "dependence_moves_coverage", "beats_indep_on_coverage",
)

REFUSAL_MECHANISM = (
    ". The mechanism: recalibrating the QB legs' zero mass raises the marginal-admissible atom cap "
    "and un-clamps the availability split, moving the assembled predictive in the modelled "
    "direction — but the residual is no longer the atom the marginals forbid. What remains is "
    "either the SHAPE of the conditional-on-playing law (a Gaussian copula still has zero tail "
    "dependence among the played rows) or the availability probability's own resolution, and "
    "neither is a zero-mass question.")
REFUSAL_REMEDY = (
    "NONE — a constraint refusal is not rescuable by data (NF-D18): more folds shrink the SE and "
    "make the refusal MORE certain. The remedy is a DIFFERENT MECHANISM under a FRESH registration "
    "— read `marginal_cap` below for WHICH residual the run measured — or a PM decision; ⛔ never "
    "a post-hoc bar change (E2.1-r).")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE MARGINAL-CAP VERDICT — the story's headline rule, fixed BEFORE any score
# ══════════════════════════════════════════════════════════════════════════════════════════════
CAP_CLEARS = "QB_CLEARS_AT_THE_MARGINAL_LAYER"
CAP_RESIDUAL = "QB_STILL_BLOCKED_WITH_THE_CAP_LIFTED"
CAP_INACTIVE = "CAP_NOT_LIFTED"
CAP_UNDEFINED = "UNDEFINED"
CAP_STATES: tuple[str, ...] = (CAP_CLEARS, CAP_RESIDUAL, CAP_INACTIVE, CAP_UNDEFINED)


def marginal_cap_verdict(*, pit_by_arm: dict[str, float], cap_mean: float,
                         predecessor_cap_mean: float, realized_atom: float,
                         installed_atom: float, clamp_binding_share: float,
                         binding_legs: dict[str, float], pit_matched_foil: float | None,
                         bar: float = PIT_MAX_DECILE_DEV,
                         min_lift: float = MIN_CAP_LIFT) -> dict:
    """⭐ Is QB's PIT ceiling still set by the marginal layer once the cap is LIFTED?

    NF-W7e CONFIRMED the cap binds (`QB_BLOCKED_AT_THE_MARGINAL_LAYER`) by measuring that the
    installed atom is Σ-invariant and that the marginals admit 0.2687 against a realized 0.5162.
    That confirmation names a mechanism; it does NOT promise the mechanism is the whole residual.
    This rule reads the four outcomes and refuses to let the run be read as either verdict when the
    knob did not turn:

    CLEARS   (`QB_CLEARS_AT_THE_MARGINAL_LAYER`) — the cap moved by at least `min_lift` AND some
        real arm's QB PIT clears the bar. The marginal layer WAS the binding constraint;
        NF-W7e's confirmation is vindicated and a calibrated assembled QB distribution exists.
    RESIDUAL (`QB_STILL_BLOCKED_WITH_THE_CAP_LIFTED`) — the cap moved and no arm clears. The atom
        cap was REAL but not the whole ceiling; the remainder is a SHAPE or resolution question and
        the record must name which, because "the marginal layer" is no longer an available answer.
        ⛔ This is a CONSTRAINT_REFUSED shape, not a power shortfall: no fold count moves a fixed
        bar (NF-D18).
    INACTIVE (`CAP_NOT_LIFTED`) — the cap did NOT move. Every arm is then its own matched foil and
        the contest passed on nothing: the thesis is UNTESTED, not refuted (NF1.7 (a) / NF-D20's
        "count the folds the mechanism could act on"). A harness reading, never a finding about QB.
    UNDEFINED — the position was not scored. Never read as any of the above.

    Beside the state it reports the magnitudes a reader needs to CHECK the rule rather than
    re-decide it: the cap before and after, the atom actually installed against the realized rate,
    how far the clamp still binds, and WHICH LEGS bound the row-wise minimum."""
    lifted = bool(np.isfinite(cap_mean) and np.isfinite(predecessor_cap_mean)
                  and (cap_mean - predecessor_cap_mean) >= min_lift)
    if not pit_by_arm or not np.isfinite(cap_mean):
        state = CAP_UNDEFINED
    elif not lifted:
        state = CAP_INACTIVE
    else:
        state = CAP_CLEARS if min(pit_by_arm.values()) <= bar else CAP_RESIDUAL
    best_arm = min(pit_by_arm, key=pit_by_arm.get) if pit_by_arm else None
    return {
        "state": state,
        "cap_was_lifted": lifted,
        "atom_cap_mean": round(float(cap_mean), 4),
        "atom_cap_mean_predecessor": round(float(predecessor_cap_mean), 4),
        "cap_lift": (round(float(cap_mean - predecessor_cap_mean), 4)
                     if np.isfinite(cap_mean) and np.isfinite(predecessor_cap_mean) else None),
        "min_cap_lift_required": min_lift,
        "installed_atom": round(float(installed_atom), 4),
        "realized_all_zero_rate": round(float(realized_atom), 4),
        "atom_shortfall_installed_vs_realized": round(float(realized_atom - installed_atom), 4),
        "clamp_binding_share": round(float(clamp_binding_share), 4),
        "clamp_binding_share_predecessor": PREDECESSOR_CLAMP_BINDING_SHARE,
        "binding_leg_share": {k: round(float(v), 4) for k, v in binding_legs.items()},
        "pit_by_arm": {k: round(float(v), 4) for k, v in pit_by_arm.items()},
        "best_pit_arm": best_arm,
        "best_pit": None if best_arm is None else round(float(pit_by_arm[best_arm]), 4),
        "bar": bar,
        "pit_matched_foil": (None if pit_matched_foil is None
                             else round(float(pit_matched_foil), 4)),
        "pit_moved_by_recalibration": (
            None if pit_matched_foil is None or best_arm is None
            else round(float(pit_by_arm[PRIMARY_ARM] - pit_matched_foil), 4)),
        "reading": {
            CAP_CLEARS: ("the marginal-admissible atom cap was lifted and a real arm clears the "
                         "PIT bar — the MARGINAL layer was QB's binding constraint, NF-W7e's "
                         "confirmation is vindicated, and a calibrated assembled QB distribution "
                         "exists (deploy-held, NF-G0 challenger)"),
            CAP_RESIDUAL: ("the cap was lifted and no arm clears the bar — the atom cap was real "
                           "but not the whole ceiling; the residual is a SHAPE or resolution "
                           "question, not a zero-mass one, and no fold count moves a fixed bar "
                           "(NF-D18)"),
            CAP_INACTIVE: ("the recalibration did not move the atom cap — every arm is its own "
                           "matched foil and the contest passed on nothing; the thesis is "
                           "UNTESTED, not refuted (NF1.7 (a))"),
            CAP_UNDEFINED: ("the confirmation could not run — never read as a verdict "
                            "(NF1.7 (a))"),
        }[state],
    }


PROMOTE_BLOCKERS: tuple[str, ...] = (
    "NF-W7f is DEPLOY-HELD: the QB marginal recalibration is an NF-G0 challenger and is served by "
    "nothing until governance promotes it",
    "⛔ QB ONLY. This record certifies NOTHING about RB/WR/TE — they were not scored. NF-W8's "
    "four-position optimizer input additionally requires an RB certificate, which is a separate "
    "story; and NF-W7c §4 / NF-W7e's scope rule still binds: a per-position-certified distribution "
    "may not feed a CROSS-POSITION ranking until every compared position is on the same generator "
    "and the same level recalibration",
    "the recalibration CHANGES NF-W6d certified cells' marginals — a consumer reading the 52-cell "
    "substrate directly is reading the SERVED cells, not these; nothing here re-serves W6d",
    "NF-W7c's promote blockers are INHERITED in full: an assembled row whose `source` is not "
    "`bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league "
    "prices, and a league pricing a SKILL_UNMODELED_KEYS term has a real coverage gap",
    "a ship here does NOT re-open NF-W4's Layer B: availability enters as a component of the "
    "predictive's draw law and of its marginals' atom, never as a feature injected into a "
    "point/quantile learner",
    "the recalibration is certified on the NF-W7c fold axis under the declared gate league — a "
    "league or a position outside that certification is not covered by this record",
)
