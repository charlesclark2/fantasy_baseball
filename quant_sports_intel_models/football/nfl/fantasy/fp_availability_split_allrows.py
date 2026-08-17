"""fp_availability_split_allrows.py — NF-W7e: the availability SPLIT over the ALL-ROWS Σ, and the
ATOM-CAP confirmation (pure).

THE STORY IN ONE PARAGRAPH. NF-W7d's QB null was about a BUNDLE whose two halves point in
OPPOSITE directions. Its matched foil `mix_off` split the registered arm into (a) the availability
SPLIT — Bernoulli(plays) × a conditional-on-playing joint draw, marginal-preserving by algebra —
which paid at ALL FOUR positions (+0.0149 / +0.0161 / +0.0058 / +0.0036 CRPS at QB/RB/WR/TE,
4/4), and (b) the Σ POPULATION — estimating the copula correlation on ACTIVE rows only — which
COST at all four (−0.0180 / −0.0044 / −0.0042 / −0.0015). The bundle netted negative at QB alone,
because QB's Σ penalty is ~4× any other position's. NF-W7d §12.1 was explicit that "the split
over the ALL-ROWS Σ" was NOT in its declared field and may not be asserted from its record: the
split's +0.0149 was measured CONDITIONAL ON Σ_played. So this is a FRESH registration (MH2.2):
keep the half that pays, drop the half that costs, and score it against the SAME reproduced
incumbent under a gate every position may ship through.

THE ARM. `assemble_mixture_bank(banks, weights, pi=π̂, corr=Σ_ALL)` — NF-W7d's mixture machinery
BY IDENTITY (one code path, `MX.mixture_leg_draws`), with Σ estimated by NF-W7c's own
`FA.position_sigma` on ALL train rows — i.e. exactly the incumbent's Σ. Nothing new is estimated:
π̂ comes from the three NF-W7d estimators, Σ from the incumbent. ⭐ THAT MAKES THE INCUMBENT ITS OWN
MATCHED FOIL: at π ≡ 1 the mixture over Σ_all is BYTE-IDENTICAL to `single_copula` (guard-tested),
so `single_copula − mixall` is the split's contribution over the all-rows Σ, with nothing else
moving. The second contest foil is NF-W7d's own registered arm (`mix_played` = Σ_played + the same
learned π): the all-rows arm must beat the bundle it claims to improve on, or the claim "Σ_played
was the costly half" is not earned. Together with `mix_off` (reference) the field completes a 2×2 —
{split on, off} × {Σ_all, Σ_played} — every cell measured on common random numbers.

⭐ THE ATOM-CAP CONFIRMATION (successor 0, folded in because it is nearly free). NF-W7d §12.4
measured that the MARGINALS bound how much atom the mixture may install: the marginal-admissible
floor `π ≥ 1 − min_i P̂_i(0)` clamps π̂ on 91.7% of QB rows, so only 0.267 of atom is installed
against a realized all-zero rate of 0.516. The cap is a function of the per-stat banks and π̂
ALONE — Σ never enters `clamp_pi` — so the all-rows Σ CANNOT move the installed Bernoulli atom.
That is an identity of the construction and it is MEASURED here per fold (`atom_is_sigma_invariant`)
rather than asserted. What Σ CAN move is the assembled total's realized zero mass through the
conditional joint-zero probability (a higher-ρ Σ puts more of the conditional draw at all-legs-zero)
and therefore the PIT — NF-W7d measured `single_copula` 0.0646 vs `mix_off` 0.0731 with the split
OFF, i.e. Σ_all vs Σ_played is worth ~0.009 of PIT. So the QB PIT under this arm is a genuine
TEST, pre-registered as such: if QB clears 0.05 here, QB is NOT blocked at the marginal layer; if
QB fails PIT under this arm — with every joint-layer knob now exercised (split on/off × Σ_all /
Σ_played, plus the comonotone ceiling) — the ceiling is set by the marginal layer and no
joint-layer story clears it. The verdict rule is a CONSTANT below (`atom_cap_verdict`), fixed
before any score.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 CHALLENGER: promotes nothing,
publishes nothing, retrains nothing. Every emitted string is a calibrated RANGE — never an edge /
ROI / win-rate claim.

Pure module — no lake IO, no S3, no boto3. Runner: `run_nf_w7e_split_allrows.py`.
"""
from __future__ import annotations

import numpy as np

from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA
from quant_sports_intel_models.football.nfl.fantasy import fp_availability_mixture as MX

# ── Pre-registration constants (the runner READS these — NF-D16) ────────────────────────────────
STORY = "NF-W7e"
PREDECESSOR = MX.STORY                           # NF-W7d — whose arms this field re-scores
TARGET = FA.TARGET                               # `league_fantasy_points`
SELECTION_METRIC = FA.SELECTION_METRIC           # `crps_q199` — ranks; PIT gates (see MX)
GATE_STATISTIC = MX.GATE_STATISTIC

#: ⭐ EVERY POSITION GATES AND MAY SHIP. NF-W7d scored RB/WR/TE report-only and its record says a
#: report-only win "is a hypothesis for a successor to register FORWARD" — this is that successor.
#: The optimizer needs all four positions, so all four are registered SHIPPABLE here, and the BH
#: family therefore carries FOUR members (the multiplicity is bought, not dodged).
GATE_POSITIONS: tuple[str, ...] = FA.POSITIONS
POSITIONS: tuple[str, ...] = FA.POSITIONS
#: The position whose PIT the atom-cap confirmation reads (NF-W7c refused it; NF-W7d could not
#: clear it). ⛔ Not a gate scope — QB gates like the other three; this names the CONFIRMATION.
ATOM_CAP_POSITION = "QB"

LEGS, N_LEGS, EVAL_LEVELS, N_LEVELS = FA.LEGS, FA.N_LEGS, FA.EVAL_LEVELS, FA.N_LEVELS
MIN_ESTIMATION_ROWS = FA.MIN_ESTIMATION_ROWS
ASSEMBLY_DRAWS = FA.ASSEMBLY_DRAWS
ROW_BLOCK = FA.ROW_BLOCK

#: ⭐ THE DRAW SEED IS INHERITED, TWICE OVER. NF-W7d inherited NF-W7c's seed so `single_copula`
#: reproduces NF-W7c's per-fold scores exactly; this story inherits the same seed AND NF-W7d's
#: availability stream offset, so `single_copula` reproduces NF-W7c AND `mix_off`/`mix_played`
#: reproduce NF-W7d — to 1e-9, per fold. Nothing can be shopped by keeping it: the three all-rows
#: arms did not exist under this seed, so there is no prior score for them to have been selected
#: against. (Same argument as NF-W7d §2; guard-tested by identity.)
_SEED = MX._SEED
AVAIL_STREAM_OFFSET = MX.AVAIL_STREAM_OFFSET

# ── The declared field (⛔ never trimmed or grown after a score — MH2 (a) / MH2.2) ───────────────
#: A COHERENT family: three arms that differ ONLY in how π is estimated, over identical mixture
#: machinery and the identical ALL-ROWS Σ. The three π estimators are NF-W7d's, IMPORTED — the
#: family's shape is the predecessor's; only the Σ population changes.
REAL_ARMS: tuple[str, ...] = ("mixall_learned", "mixall_clim", "mixall_const")
PRIMARY_ARM = "mixall_learned"
#: each all-rows arm → the NF-W7d π estimator it uses (`MX.pi_for_arm` is called with THIS name)
PI_ESTIMATOR_OF: dict[str, str] = {
    "mixall_learned": "mix_learned", "mixall_clim": "mix_clim", "mixall_const": "mix_const",
}

#: ⭐ THE TWO CONTEST FOILS — `beats_foil` binds against these and ONLY these:
#:   single_copula — THE INCUMBENT (NF-W7c's `joint_rank`: one Gaussian copula, Σ on ALL rows) —
#:                   which is ALSO this story's MATCHED foil, because the mixture over Σ_all at
#:                   π ≡ 1 is byte-identical to it. `single_copula − mixall` = the split's
#:                   contribution over the all-rows Σ, and nothing else moves.
#:   mix_played    — NF-W7d's registered PRIMARY (`mix_learned`: Σ on ACTIVE rows + learned π),
#:                   reproduced to 1e-9. The all-rows arm must beat the bundle it claims to
#:                   improve on — `mix_played − mixall` is the Σ-population effect WITH the split
#:                   on, the cell of the 2×2 NF-W7d could not measure.
CONTEST_FOILS: tuple[str, ...] = ("single_copula", "mix_played")
INCUMBENT_FOIL = "single_copula"
PREDECESSOR_FOIL = "mix_played"
#: What each foil IS in the predecessors' records — the reproduction targets.
INCUMBENT_RECORD_RELPATH = MX.INCUMBENT_RECORD_RELPATH       # NF-W7c
INCUMBENT_RECORD_ARM = MX.INCUMBENT_ARM                      # `joint_rank`
PREDECESSOR_RECORD_RELPATH = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                              "nf_w7d_qb_availability.json")
PREDECESSOR_RECORD_ARMS: dict[str, str] = {"mix_played": "mix_learned", "mix_off": "mix_off"}

#: REFERENCE FOILS — SCORED and REPORTED; they do NOT bind `beats_foil` (declared with the reason,
#: NF-W7c §11.4 / NF-W7d §3): `mix_off` completes the 2×2 (Σ_played, split OFF); `assembled_indep`
#: carries the three inherited dependence clauses; `foil_direct_points` answers the ARCHITECTURE
#: question, not this story's. Excluded from the PBO/DSR trial field (MH2.1 (a)).
REFERENCE_FOILS: tuple[str, ...] = ("mix_off", "assembled_indep", "foil_direct_points")
FOILS: tuple[str, ...] = (*CONTEST_FOILS, *REFERENCE_FOILS)
ELIGIBLE: tuple[str, ...] = (*REAL_ARMS, *CONTEST_FOILS)

DEGENERATES: tuple[str, ...] = MX.DEGENERATES
FOILS_WITH_ORACLE: tuple[str, ...] = MX.FOILS_WITH_ORACLE
ANCHORS: tuple[str, ...] = (
    *DEGENERATES, "permuted_direct", "pi_permuted",
    *(f"oracle__{a}" for a in REAL_ARMS), *(f"matched_n__{a}" for a in REAL_ARMS),
    *(f"oracle__{f}" for f in FOILS_WITH_ORACLE),
)
ALL_LABELS: tuple[str, ...] = (*REAL_ARMS, *FOILS, *ANCHORS)
#: labels whose coverage / PIT are stored per fold
WATCHED: tuple[str, ...] = (*REAL_ARMS, *FOILS, "assembled_comonotone", "pi_permuted")

# ── Gate constants — ⛔ every one INHERITED by reference (E2.1-r / NF1.8 / NF-D18) ───────────────
COVERAGE_FLOOR, COVERAGE_BLOCK_SE = MX.COVERAGE_FLOOR, MX.COVERAGE_BLOCK_SE
PBO_MAX, DSR_MIN, FDR_Q = MX.PBO_MAX, MX.DSR_MIN, MX.FDR_Q
PIT_MAX_DECILE_DEV = MX.PIT_MAX_DECILE_DEV
MIN_MIXTURE_ATOM = MX.MIN_MIXTURE_ATOM
MAX_MARGINAL_DRIFT = MX.MAX_MARGINAL_DRIFT
INCUMBENT_TOLERANCE = MX.INCUMBENT_TOLERANCE
SELECTION_IS_CRPS_NOT_PIT = MX.SELECTION_IS_CRPS_NOT_PIT
oracle_floor_state = MX.oracle_floor_state
ORACLE_RESPECTED, ORACLE_VIOLATED, ORACLE_INACTIVE = (
    MX.ORACLE_RESPECTED, MX.ORACLE_VIOLATED, MX.ORACLE_INACTIVE)
#: the mixture primitives, BY IDENTITY — one code path (NF-W7d's RED-proof lesson)
assemble_mixture_bank = MX.assemble_mixture_bank
mixture_marginal_drift = MX.mixture_marginal_drift
clamp_pi = MX.clamp_pi
pi_floor = MX.pi_floor
pi_for_arm = MX.pi_for_arm
activity_indicator = MX.activity_indicator
atom_rate = MX.atom_rate
sigma_played = MX.sigma_played
sigma_all = FA.position_sigma                    # ⭐ THE ALL-ROWS Σ — the incumbent's, verbatim
pit_detail, pooled_pit = MX.pit_detail, MX.pooled_pit
pit_null_reference, pit_null_pvalue = MX.pit_null_reference, MX.pit_null_pvalue
incumbent_reproduction = MX.incumbent_reproduction

#: ⭐ The identity tolerance for `atom_is_sigma_invariant`: the installed atom under Σ_all and
#: under Σ_played is computed from the SAME π̂ and the SAME banks by the SAME clamp, so the two
#: figures are the same float. Float noise in a mean of ~700 rows, not a knob.
ATOM_INVARIANCE_TOLERANCE = 1e-9

STATISTICAL_CHECKS: tuple[str, ...] = MX.STATISTICAL_CHECKS
ANCHOR_CHECKS: tuple[str, ...] = (
    "degenerates_lose", "permutation_behaves", "oracle_floors_respected",
    "mixture_is_active", "mixture_preserves_marginals", "incumbent_reproduces",
    "predecessor_reproduces", "atom_is_sigma_invariant",
    "independence_under_disperses", "dependence_moves_coverage", "beats_indep_on_coverage",
)

REFUSAL_MECHANISM = (
    ". The mechanism: the availability split over the ALL-ROWS Σ moves the assembled predictive "
    "in the modelled direction but does not carry it across the pre-registered bar — the split "
    "prices the atom the row's own marginals ADMIT, and the residual is the atom they do not: "
    "the marginal-admissible floor caps the installed atom below the realized all-zero rate, and "
    "no joint-layer construction can install mass its marginals forbid.")
REFUSAL_REMEDY = (
    "NONE — a constraint refusal is not rescuable by data (NF-D18): more folds shrink the SE and "
    "make the refusal MORE certain. The remedy is a DIFFERENT LAYER under a FRESH registration — "
    "the MARGINAL layer (a NF-W6d cell whose own zero mass is smaller than the realized all-zero "
    "rate; the 52-cell substrate) — or a PM decision; ⛔ never a post-hoc bar change (E2.1-r).")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The atom cap — what the marginals ADMIT, and what the assembled total actually CARRIES
# ══════════════════════════════════════════════════════════════════════════════════════════════
def atom_cap(banks: np.ndarray) -> float:
    """The MAXIMUM Bernoulli atom the rows' own marginals admit, averaged over rows:
    `mean_i (1 − π_floor,i)`. A mixture can install at most this much; §12.4's 0.267 at QB is this
    number with the clamp binding on 92% of rows. Σ never enters it."""
    return float(np.mean(1.0 - pi_floor(banks)))


def total_zero_mass(bank: np.ndarray) -> np.ndarray:
    """(n,) the probability mass an ASSEMBLED (n, 199) fantasy-point bank places on EXACTLY zero
    points — the atom the realized all-zero rows land on.

    Read off the sampler's own grid the way `MX.leg_zero_mass` reads a leg: P(T ≤ 0) is the level
    of the last knot at or below 0, P(T < 0) the level of the last knot strictly below 0 (a
    negatively-weighted leg — an interception, a fumble — can push a row's total below zero, and
    that mass is not the atom). Both reads are conservative (they under-state, never over-state,
    the atom), so a mixture is judged against a floor rather than credited with mass it may not
    carry."""
    b = np.asarray(bank, dtype=float)
    if b.ndim != 2 or b.shape[1] != N_LEVELS:
        raise ValueError(f"assembled bank is {b.shape}, expected (n, {N_LEVELS})")
    le = (b <= 0.0).sum(axis=1) - 1
    lt = (b < 0.0).sum(axis=1) - 1
    p_le = np.where(le >= 0, EVAL_LEVELS[np.clip(le, 0, N_LEVELS - 1)], 0.0)
    p_lt = np.where(lt >= 0, EVAL_LEVELS[np.clip(lt, 0, N_LEVELS - 1)], 0.0)
    return np.clip(p_le - p_lt, 0.0, 1.0)


#: The four atom-cap states, fixed before any score. Read on the ATOM_CAP_POSITION's selection.
CAP_CONFIRMED = "QB_BLOCKED_AT_THE_MARGINAL_LAYER"
CAP_REFUTED = "QB_CLEARS_UNDER_THE_ALL_ROWS_SIGMA"
CAP_UNDEFINED = "UNDEFINED"          # the position was not scored, or the identity did not hold
CAP_STATES: tuple[str, ...] = (CAP_CONFIRMED, CAP_REFUTED, CAP_UNDEFINED)


def atom_cap_verdict(*, pit_by_arm: dict[str, float], atom_all_rows: float,
                     atom_played: float, atom_cap_mean: float, realized_atom: float,
                     total_zero_mass_by_arm: dict[str, float],
                     pit_predecessor: float | None, bar: float = PIT_MAX_DECILE_DEV,
                     tolerance: float = ATOM_INVARIANCE_TOLERANCE) -> dict:
    """⭐ THE ATOM-CAP CONFIRMATION, as a RULE fixed in advance (not a reading taken afterwards).

    Question: is QB's PIT ceiling (~0.059 under every joint-layer construction so far) set by the
    MARGINAL layer? The cap `1 − min_i P̂_i(0)` is a function of the per-stat banks and π̂ alone,
    so the all-rows Σ cannot move the INSTALLED atom (an identity, measured as
    `atom_is_sigma_invariant`); it can move the assembled total's realized zero mass and the PIT
    only through the conditional joint-zero probability. So:

    CONFIRMED (`QB_BLOCKED_AT_THE_MARGINAL_LAYER`) — the identity holds AND no real arm's PIT
        clears the bar. Every joint-layer knob has now been exercised across NF-W7c/W7d/W7e
        (split on/off × Σ_all/Σ_played, plus the comonotone ceiling): the ceiling is the
        marginals', and no joint-layer story clears it. The QB roadmap moves to the substrate.
    REFUTED (`QB_CLEARS_UNDER_THE_ALL_ROWS_SIGMA`) — the identity holds and some real arm's PIT
        clears the bar: the joint layer CAN clear QB; the cap was not the binding constraint.
    UNDEFINED — the identity did not hold (a harness defect: the two arms did not share a π̂ /
        bank), or the position was not scored. Never read as either verdict (NF1.7 (a)).

    Beside the state the rule reports the MAGNITUDES a reader needs to check it: how far the
    all-rows Σ moved the predecessor's PIT (`pit_moved_by_sigma_all`), the cap vs the realized
    atom (`atom_shortfall`), and the total zero mass each arm actually carries."""
    identity = bool(abs(atom_all_rows - atom_played) <= tolerance)
    if not pit_by_arm or not identity:
        state = CAP_UNDEFINED
    else:
        state = CAP_REFUTED if min(pit_by_arm.values()) <= bar else CAP_CONFIRMED
    best_arm = min(pit_by_arm, key=pit_by_arm.get) if pit_by_arm else None
    return {
        "state": state,
        "atom_identity_holds": identity,
        "installed_atom_all_rows_sigma": round(float(atom_all_rows), 6),
        "installed_atom_played_sigma": round(float(atom_played), 6),
        "atom_cap_mean": round(float(atom_cap_mean), 4),
        "realized_all_zero_rate": round(float(realized_atom), 4),
        "atom_shortfall_cap_vs_realized": round(float(realized_atom - atom_cap_mean), 4),
        "pit_by_arm": {k: round(float(v), 4) for k, v in pit_by_arm.items()},
        "best_pit_arm": best_arm,
        "best_pit": None if best_arm is None else round(float(pit_by_arm[best_arm]), 4),
        "bar": bar,
        "pit_predecessor_played_sigma": (None if pit_predecessor is None
                                         else round(float(pit_predecessor), 4)),
        "pit_moved_by_sigma_all": (None if pit_predecessor is None or best_arm is None
                                   else round(float(pit_by_arm[PRIMARY_ARM] - pit_predecessor), 4)),
        "total_zero_mass_by_arm": {k: round(float(v), 4)
                                   for k, v in total_zero_mass_by_arm.items()},
        "reading": {
            CAP_CONFIRMED: ("the installed atom is Σ-invariant (identity holds) and no all-rows "
                            "arm clears the PIT bar — with split on/off × Σ_all/Σ_played all "
                            "measured, the QB ceiling is set by the MARGINAL layer; no joint-layer "
                            "story clears it; the QB roadmap moves to the 52-cell substrate"),
            CAP_REFUTED: ("an all-rows arm clears the PIT bar — the joint layer CAN clear QB and "
                          "the marginal cap was NOT the binding constraint"),
            CAP_UNDEFINED: ("the confirmation could not run — never read as a verdict "
                            "(NF1.7 (a))"),
        }[state],
    }


PROMOTE_BLOCKERS: tuple[str, ...] = (
    "NF-W7e is DEPLOY-HELD: the all-rows-Σ availability-mixture assembly is an NF-G0 challenger "
    "and is served by nothing until governance promotes it",
    "a position ships from this record ONLY through its own registered gate (all four gate; the "
    "BH family carries four members) — a position that failed is a null, and NF-W7d's report-only "
    "wins are NOT carried forward as evidence (E2.1-r)",
    "NF-W7c's promote blockers are INHERITED in full: an assembled row whose `source` is not "
    "`bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league "
    "prices, and a league pricing a SKILL_UNMODELED_KEYS term has a real coverage gap",
    "a ship here does NOT re-open NF-W4's Layer B: availability enters as a component of the "
    "predictive's draw law, never as a feature injected into a point/quantile learner",
    "the mixture is certified on the NF-W7c fold axis under the declared gate league — a league or "
    "a position outside that certification is not covered by this record",
)
