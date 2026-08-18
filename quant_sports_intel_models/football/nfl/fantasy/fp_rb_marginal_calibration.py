"""fp_rb_marginal_calibration.py — NF-W7h: the RB MARGINAL-layer zero-mass recalibration on the
NF-W6d 52-cell substrate (pure).

THE STORY IN ONE PARAGRAPH. NF-W7f cleared QB's assembled calibration by recalibrating the QB
legs' zero mass on the 52-cell substrate (PIT 0.0648 → 0.0281, 8/8 folds where the reproduced
incumbent clears 0/8). RB is the other position NF-W8's four-position optimizer input needs, and it
returned `GENUINE_ABSENCE` in both NF-W7c and NF-W7e. This story asks whether the SAME marginal
mechanism moves RB. ⛔ It is NOT a re-run of NF-W7f, and the two reasons are MEASURED off committed
records before this story scores anything (`ablation_results/nf_w7h_preregistration.md` §0):

  1. ⭐ **RB's assembled calibration ALREADY CLEARS.** NF-W7e recorded RB's best construction at a
     PIT max-decile deviation of **0.0242** against the 0.05 bar (QB: 0.0640, failing). So NF-W7f's
     headline rule — "the cap lifted AND some arm's PIT clears" — is satisfied at RB BEFORE the
     story runs, and reusing it would return a CLEARS verdict for a mechanism that did nothing (the
     NF1.7 (a) vacuous-anchor class). RB therefore gets its OWN verdict rule, `rb_marginal_verdict`
     (§7 of the pre-registration), whose states are about the PROPER SCORE while HOLDING the
     calibration RB already has — including `RB_CALIBRATION_DAMAGED`, a state QB's rule structurally
     cannot express and RB structurally needs.
  2. ⭐ **RB's continuous cells OVER-price their zero, and the transform is RAISE-ONLY.** On NF-W6d's
     committed 126-row RB serving proof, `gap = realized P(0) − predicted P(0)` is NEGATIVE for
     every continuous RB cell — `receptions` −0.0923, `receiving_yards` −0.0707, `rushing_yards`
     −0.0647, `carries` −0.0588 — against `QB|passing_yards` at **+0.2211**, the defect NF-W7f
     repaired. `resplice_zero_mass` is RAISE-ONLY by construction, so it CANNOT touch an
     over-pricing cell. The one RB cell that materially under-prices its zero is `rushing_tds`
     (+0.0457), a low-weight touchdown leg. ⛔ That is a HYPOTHESIS off a 126-row single-week proof,
     exactly as NF-W7f treated the analogous 89-row QB reading — the runner MEASURES the per-leg
     zero mass, the row-wise argmin and the cap before/after on EVERY fold at fold scale (~1,073 RB
     test rows/fold, 8.5× the proof), and the record reports what bound the cap rather than what was
     expected to.

WHAT IS HELD FIXED, AND THE ONE THING THAT VARIES. The joint construction is pinned at
**`mix_played`** — NF-W7d's registered primary (learned π̂ + Σ on ACTIVE rows) — because NF-W7e
measured it as RB's CRPS-best construction on record (2.5173 vs `mixall_learned` 2.5212 vs
`single_copula` 2.5290). ⭐ This is NF-W7f's own rule ("the arm must beat the best thing that EXISTS,
not merely the thing that shipped") applied to RB's facts rather than copied from QB's conclusion:
NF-W7f pinned `mixall_learned` because at QB that arm IS the best on record, and at RB it is not.
Σ, π̂, the mixture machinery and the draw stream are inherited BY IDENTITY; the ONLY thing the
declared family varies is the per-leg zero-mass TARGET of the RB marginals.

⭐ THE TRANSFORM IS IMPORTED, NOT RE-IMPLEMENTED. `resplice_zero_mass`, its three measured
identities, the arm targets and the availability bucketing are `fp_qb_marginal_calibration`'s, by
identity. A second implementation of a shared rule is the NF-C0e wrong-key class, and it would also
break the matched-foil argument: `mix_played − zm_*` is only "the marginal recalibration and nothing
else" if the splice is the SAME splice whose no-op identity is measured per fold.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 CHALLENGER: promotes nothing,
publishes nothing, retrains nothing, serves nothing. Every emitted string is a calibrated RANGE —
never an edge / ROI / win-rate claim.

Pure module — no lake IO, no S3, no boto3. Runner: `run_nf_w7h_rb_marginal.py`.
"""
from __future__ import annotations

import numpy as np

from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA
from quant_sports_intel_models.football.nfl.fantasy import fp_availability_split_allrows as SA
from quant_sports_intel_models.football.nfl.fantasy import fp_qb_marginal_calibration as QM

# ── Pre-registration constants (the runner READS these — NF-D16) ────────────────────────────────
STORY = "NF-W7h"
#: NF-W7e is the record this story's cap baseline and matched foil are READ FROM; NF-W7f is the
#: story whose TRANSFORM this one imports. Both are named so a reader can trace either lineage.
PREDECESSOR = SA.STORY                           # NF-W7e — the record carrying RB's cap baseline
TRANSFORM_SOURCE = QM.STORY                      # NF-W7f — whose splice this story imports
TARGET = FA.TARGET                               # `league_fantasy_points`
SELECTION_METRIC = FA.SELECTION_METRIC           # `crps_q199` — ranks; PIT gates
GATE_STATISTIC = SA.GATE_STATISTIC               # `randomized_pit_max_decile_dev`

#: ⭐ SCOPE: **RB ONLY**. NF-W7e certified WR; NF-W7f calibrated QB (deploy-held, CONSTRAINT_REFUSED);
#: TE returned GENUINE_ABSENCE. ⛔ QB/WR/TE are NOT scored here and NOT reported — a position this
#: story does not run cannot be read as evidence in either direction (NF1.7 (a)), and a report-only
#: result may never be re-classified into shippability (E2.1-r). The BH family therefore carries ONE
#: member; that is the declared scope, not a multiplicity dodge, and it is stated on the verdict.
GATE_POSITIONS: tuple[str, ...] = ("RB",)
POSITIONS: tuple[str, ...] = ("RB",)
CAP_POSITION = "RB"

LEGS, N_LEGS, EVAL_LEVELS, N_LEVELS = FA.LEGS, FA.N_LEGS, FA.EVAL_LEVELS, FA.N_LEVELS
INTEGER_LEGS = FA.INTEGER_LEGS
MIN_ESTIMATION_ROWS = FA.MIN_ESTIMATION_ROWS
ASSEMBLY_DRAWS = FA.ASSEMBLY_DRAWS
ROW_BLOCK = FA.ROW_BLOCK

#: ⭐ THE DRAW SEED IS INHERITED, FOUR TIMES OVER (NF-W7c → W7d → W7e → W7f). So `single_copula`
#: reproduces NF-W7c and `mix_played` reproduces NF-W7d — per fold, to 1e-9 — and every arm, foil
#: and anchor of a fold transforms the SAME base normals (common random numbers), so an arm-vs-foil
#: difference is the marginal recalibration and nothing else. Nothing can be shopped by keeping it:
#: no recalibrated RB arm has ever been scored under this seed.
_SEED = QM._SEED
AVAIL_STREAM_OFFSET = QM.AVAIL_STREAM_OFFSET

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The transform — IMPORTED BY IDENTITY from NF-W7f (⛔ never re-implemented)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: ⭐ Every one of these is `fp_qb_marginal_calibration`'s object, not a copy. The matched-foil
#: argument (`mix_played − zm_*` is the recalibration and nothing else) rests on the splice being
#: THE splice whose byte-identical no-op is measured per fold; a second implementation would make
#: the contest measure the re-implementation's arithmetic instead (NF-C0e / NF-W7d's RED-proof
#: lesson: a diagnostic that validates its own copy of the logic validates nothing).
MAX_ZERO_TARGET = QM.MAX_ZERO_TARGET
GRID_STEP = QM.GRID_STEP
ZERO_MASS_TOLERANCE = QM.ZERO_MASS_TOLERANCE
NO_OP_TOLERANCE = QM.NO_OP_TOLERANCE
MAX_POSITIVE_LAW_DRIFT_RATIO = QM.MAX_POSITIVE_LAW_DRIFT_RATIO
MIN_CONDITIONAL_KNOTS = QM.MIN_CONDITIONAL_KNOTS
ZERO_THRESHOLD = QM.ZERO_THRESHOLD

resplice_zero_mass = QM.resplice_zero_mass
resplice_edges = QM.resplice_edges
zero_mass_hits_target = QM.zero_mass_hits_target
positive_law_drift = QM.positive_law_drift
matched_foil_identity = QM.matched_foil_identity
conditional_quantiles = QM.conditional_quantiles
snap_to_grid = QM.snap_to_grid
realized_zero = QM.realized_zero
zero_targets = QM.zero_targets
conditional_zero_rate = QM.conditional_zero_rate
marginal_zero_rate = QM.marginal_zero_rate
binding_leg_share = QM.binding_leg_share
leg_zero_mass_table = QM.leg_zero_mass_table
leg_zero_mass = QM.leg_zero_mass
pi_floor = QM.pi_floor
atom_cap = QM.atom_cap
total_zero_mass = QM.total_zero_mass
OVER_SCALE = QM.OVER_SCALE

# ── The availability decomposition's buckets (REPORTED, never gated) ────────────────────────────
#: ⭐ FIXED, ABSOLUTE π̂ edges — ⛔ deliberately NOT per-fold quantiles, and this story is the reason
#: the rule is load-bearing rather than stylistic. NF-W7f's headline mechanism claim ("the cell
#: already prices availability internally, so an availability-derived target prices it twice, and
#: the sign flips with P(played)") was REFUTED BY ITS OWN DECISIVE RUN precisely because a
#: π̂-QUARTILE bucketing on a bimodal covariate FABRICATED a monotone gradient that did not exist:
#: quartiles read a tidy sign flip (+0.58/−0.30/−1.95/−0.19) while the same data on fixed absolute
#: edges, pooled over 8 folds as Σsums/Σcounts, was NON_MONOTONE with SIX sign changes and the two
#: buckets holding 57% of rows sat at −0.16/−0.03. Imported by identity so the two stories' tables
#: are comparable row for row.
PI_BUCKET_EDGES = QM.PI_BUCKET_EDGES
MIN_BUCKET_ROWS = QM.MIN_BUCKET_ROWS
bucket_by_availability = QM.bucket_by_availability
pool_availability_buckets = QM.pool_availability_buckets

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The declared field (⛔ never trimmed or grown after a score — MH2 (a) / MH2.2)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: The SAME coherent family shape NF-W7f declared: four arms differing ONLY in the per-(row, leg)
#: zero-mass TARGET, over an IDENTICAL joint construction, identical marginals-before-recalibration,
#: identical mixture machinery and identical draw stream. The target FUNCTIONS are imported
#: (`zero_targets`); what this story declares is that these four, and only these four, are its
#: field.
#:
#:   zm_conditional ⭐ PRIMARY — the two-part reconstruction: a leg is zero if the player did not
#:                   play (`q̂ = 1 − π̂`) OR he played and still recorded nothing (the TRAIN realized
#:                   rate on ACTIVE rows): `t = q̂ + (1 − q̂)·p̂₊`.
#:   zm_floor       — the MINIMAL intervention `t = max(P̂(0), q̂)`: touches only the legs that
#:                   under-price inactivity. ⭐ NF-W7f's QB WINNER, so it is the arm most likely to
#:                   transfer — and at RB it is also the arm the §0.2 premise predicts will be
#:                   closest to a no-op, since RB's continuous legs already carry MORE zero mass
#:                   than `q̂` on most rows. Scoring it is how that prediction becomes a measurement.
#:   zm_climatology — row-BLIND: the leg's TRAIN realized zero rate, the same number on every row.
#:                   Registered SHIPPABLE per NF-D20 (a blind rule that wins is a finding about the
#:                   signal, not an anchor to be disqualified after the fact).
#:   zm_over        — the MAGNITUDE probe, `q̂′ = min(1, 1.5·q̂)`. ⭐ A REAL, SHIPPABLE arm, NOT an
#:                   anchor (NF-D20 / NF-W7b): an anchor registered to lose that then BEATS the
#:                   field produces a null while the answer sits in an ineligible cell. It is
#:                   EXPECTED to lose; if it wins, the magnitude hypothesis is REFUTED and the
#:                   record says so rather than re-labelling it.
REAL_ARMS: tuple[str, ...] = ("zm_conditional", "zm_floor", "zm_climatology", "zm_over")
PRIMARY_ARM = "zm_conditional"
#: ⭐ Passed to `cv_power.classify_null(declared_field_size=…)` and sourced to the committed
#: pre-registration, so the MH2.7 `field_remedy_admissible` flag is an AUDITABLE claim rather than
#: a post-hoc field size (MH2.2: you get to PRE-REGISTER a family, you do NOT get to DISCOVER one).
DECLARED_FIELD_SIZE = len(REAL_ARMS)
DECLARED_FIELD_SIZE_SOURCE = (
    "fp_rb_marginal_calibration.REAL_ARMS, committed in "
    "ablation_results/nf_w7h_preregistration.md §3 before any score")

#: ⭐ THE JOINT CONSTRUCTION, HELD FIXED FOR EVERY REAL ARM — and the one substantive difference
#: from NF-W7f's field. NF-W7e measured RB's constructions at `mix_played` 2.5173 < `mixall_learned`
#: 2.5212 < `single_copula` 2.5290, so RB's CRPS-best construction on record is NF-W7d's registered
#: primary, NOT NF-W7e's registered arm. Pinning `mixall_learned` here (a copy of NF-W7f's choice)
#: would hand this story a foil already KNOWN to be beaten and make any win un-attributable to the
#: recalibration.
JOINT_CONSTRUCTION = "mix_played"
#: NF-W7d's learned π̂ estimator — the same estimator NF-W7e's and NF-W7f's primaries use.
PI_ESTIMATOR = SA.PI_ESTIMATOR_OF[SA.PRIMARY_ARM]

#: ⭐ THE TWO CONTEST FOILS — `beats_foil` binds against these and ONLY these:
#:   mix_played    — ⭐ THE MATCHED FOIL: the identical joint construction (learned π̂ + Σ on ACTIVE
#:                   rows) on the SERVED marginals, reproduced to 1e-9 against NF-W7d's
#:                   `mix_learned`. `mix_played − zm_*` is the marginal recalibration channel with
#:                   the copula, the Σ, the π̂ fit and the draw stream all held fixed — a claim the
#:                   byte-identical no-op identity EARNS rather than asserts. It is also RB's
#:                   CRPS-best construction on record, so the arm must beat the best thing that
#:                   EXISTS, not merely the thing that shipped.
#:   single_copula — THE INCUMBENT (NF-W7c's `joint_rank`), reproduced to 1e-9. Keeping it binding
#:                   makes this story's margin comparable to NF-W7c/W7d/W7e/W7f's on the same folds
#:                   and the same seed.
CONTEST_FOILS: tuple[str, ...] = ("mix_played", "single_copula")
MATCHED_FOIL = "mix_played"
INCUMBENT_FOIL = "single_copula"

#: The reproduction targets — what each foil IS in the predecessors' committed records.
INCUMBENT_RECORD_RELPATH = SA.INCUMBENT_RECORD_RELPATH        # NF-W7c
INCUMBENT_RECORD_ARM = SA.INCUMBENT_RECORD_ARM                # `joint_rank`
#: ⭐ `mix_played` is NF-W7d's `mix_learned`, and NF-W7d scored RB (recorded 2.5173) — so the
#: reproduction is checked against the record that ACTUALLY carries an RB row, not against NF-W7e's
#: re-scoring of it. NF-W7e's record is read separately, for the CAP BASELINE only (§4).
PREDECESSOR_RECORD_RELPATH = SA.PREDECESSOR_RECORD_RELPATH     # NF-W7d
#: ⚠️ THE STORY STRING OF THE REPRODUCTION RECORD IS **NF-W7d**, NOT `PREDECESSOR` (= NF-W7e).
#: `_record_scores` REFUSES a record whose `story` does not match, returning None — and a None
#: record makes the reproduction control report "DID NOT RUN" forever, which is a silent
#: never-running control, not a failure anyone would trace (NF1.7 (a)). The two records this story
#: reads are deliberately DIFFERENT: NF-W7e carries RB's CAP BASELINE, NF-W7d carries the
#: `mix_learned` scores `mix_played` must reproduce. Caught by a guard, not by inspection.
REPRODUCTION_RECORD_STORY = SA.PREDECESSOR                      # "NF-W7d"
PREDECESSOR_RECORD_ARMS: dict[str, str] = {"mix_played": "mix_learned"}
#: the record the atom-cap baseline is read from (NF-W7e — the only run that measured RB's cap)
CAP_BASELINE_RECORD_RELPATH = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                               "nf_w7e_split_allrows.json")

#: REFERENCE FOILS — SCORED and REPORTED; they do NOT bind `beats_foil`, and they are EXCLUDED from
#: the PBO/DSR trial field (MH2.1 (a) — a diagnostic anchor that joins the trial field sets the
#: gate's own bar). `zm_cond_copula` completes the 2×2 {recalibrated, served} × {split, no split}:
#: the PRIMARY arm's marginals under the INCUMBENT's copula, i.e. the recalibration with the
#: availability split OFF. `assembled_indep` carries the three inherited dependence clauses;
#: `foil_direct_points` is the ARCHITECTURE question (NF-W7c §11.4), never this story's gate.
#: ⭐ `mix_off` is here by the §12 PRE-SCORE AMENDMENT, and the reason is RB-specific. NF-W7f could
#: report a clean split channel as `single_copula − mixall_learned` because at QB the pinned
#: construction and the incumbent share the SAME Σ population (all rows). At RB the pinned
#: construction is `mix_played`, whose Σ is estimated on ACTIVE rows, so `single_copula − mix_played`
#: differs in TWO things at once (the split AND the Σ population) and labelling it "the split
#: channel" would be a bundled contrast wearing a single channel's name (the NF-W7d bundled-null
#: lesson, facing the attribution direction). `mix_off` — the incumbent's copula construction at
#: Σ_played, split OFF, NF-W7d's own reference cell — isolates the split at a FIXED Σ. ⛔ Reference
#: foils never bind `beats_foil` and never enter the PBO eligible set or the DSR trial field, so
#: this adds a reported COLUMN, not an arm: `ELIGIBLE`, `DECLARED_FIELD_SIZE` and the BH family are
#: all unchanged.
REFERENCE_FOILS: tuple[str, ...] = ("zm_cond_copula", "mix_off", "assembled_indep",
                                    "foil_direct_points")
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
#: ⭐ Σ ON ACTIVE ROWS — NF-W7d's estimator, which is what `mix_played` uses. ⛔ NOT `sigma_all`:
#: the family holds the joint construction fixed at RB's CRPS-best, and that construction's Σ
#: population is the played one (NF-W7e measured `sigma_population_with_split` at −0.0039 for RB,
#: i.e. Σ_played WINS at RB while Σ_all wins at QB/WR).
sigma_played = SA.sigma_played
pit_detail, pooled_pit = SA.pit_detail, SA.pooled_pit
pit_null_reference, pit_null_pvalue = SA.pit_null_reference, SA.pit_null_pvalue
incumbent_reproduction = SA.incumbent_reproduction

# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE MECHANISM-ACTIVITY FLOOR — derived from RECORDED design quantities (§4 of the prereg)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: NF-W7e's RECORDED RB figures. ⛔ Read from the committed record at run time
#: (`cap_baseline` in the runner), never TRUSTED from these constants: they are here so the
#: pre-registration is legible in code, and a guard asserts the record still carries them (the
#: NF1.9-R `served_*`-column lesson — never trust a NAME for a MEASUREMENT).
PREDECESSOR_CAP_MEAN = 0.3018            # what RB's SERVED marginals admit: mean_i min_j P̂_j(0)
PREDECESSOR_REALIZED_ATOM = 0.3359       # RB's realized all-zero rate
PREDECESSOR_INSTALLED_ATOM = 0.2646      # the atom the mixture actually installed
PREDECESSOR_CLAMP_BINDING_SHARE = 0.4184
PREDECESSOR_BEST_RB_PIT = 0.0242         # `mix_played` — ⭐ ALREADY CLEARS the 0.05 bar

#: ⭐ THE FLOOR. DERIVED, not tuned: the recalibration exists to stop the marginals FORBIDDING the
#: atom the population actually exhibits, so it has turned the knob iff the recalibrated cap reaches
#: RB's realized all-zero rate ⇒ `MIN_CAP_LIFT = realized − cap = 0.3359 − 0.3018`.
#:
#: It is the RB analogue of NF-W7f's QB floor (0.012 of probability mass, derived from the 0.05 bar
#: and QB's recorded first decile of 0.162), and it is a TARGET stated in advance rather than a
#: level read off a result — NF-W7f's own decisive run SATISFIES the same rule at QB (cap
#: 0.2687 → 0.5481 = a lift of 0.2794 against a QB shortfall of 0.2475), so the rule is not tuned to
#: make RB pass or fail.
MIN_CAP_LIFT = round(PREDECESSOR_REALIZED_ATOM - PREDECESSOR_CAP_MEAN, 4)     # 0.0341

# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE COMPONENT-DEGRADATION CLAUSE — decided FORWARD (§6 of the pre-registration)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: THE GATING QUESTION, RESOLVED FIRST (prereg §6.1): **the served paid stat line does NOT derive
#: from these cells.** Every consumer of `stat_distribution_serving{,_d}` / `stat_distributions_*`
#: in the repo is a research runner or a test; `export_draft_board_json.py` references none of them;
#: and the served `STAT_FIELD` payload is built from the board's `proj_*` columns, which
#: `season_projection.py` produces — the SEASONAL point path, a different model. ⇒ a per-leg CRPS
#: change here damages NO served surface, so the clause cannot be defended as protecting the paid
#: stat line.
#:
#: ⭐ IT STAYS A HARD GATE ANYWAY, because it has a scientific job: it refuses a story that buys the
#: assembled atom by WRECKING THE PARTS — a refit wearing a recalibration's badge.
#: `positive_law_preserved` guards *reshape vs re-weight* structurally; this clause guards the
#: softer question of whether the parts got worse.
#:
#: WHAT CHANGES IS THE THRESHOLD, AND IT COMES FROM A DESIGN QUANTITY. NF-W7f used 0.0 — ANY
#: degradation refuses — which is the "demonstrable ≠ material" defect (NF-W6) facing the refusal
#: direction: it fires on a rounding artefact. NF-W7c's rule, adopted verbatim: a violation must be
#: DEMONSTRABLE **and** MATERIAL.
#:
#: ⭐ PROOF THIS RESCUES NOTHING: applied to NF-W7f's OWN recorded QB numbers the relaxed rule STILL
#: REFUSES QB — claimed effect 0.0184/2.5829 = 0.712% relative ⇒ a materiality bar of 0.0712%,
#: against an observed per-leg degradation of 0.3866%, which is 5.4× above it. The threshold was
#: fixed before any RB score and does not retroactively flip the one recorded result it could have.
#: Both the raw sums and the two relative figures are reported so a reader can re-derive under
#: another rule (NF-D14).
#: the fraction of the arm's OWN claimed effect at which a degradation becomes material
PER_LEG_MATERIALITY_FRACTION = 0.1
#: DEMONSTRABLE = worse on a MAJORITY of folds, so one fold's noise cannot refuse the story. A
#: bare majority (not the 0.60 selection clause) because this is a REFUSAL threshold, and the
#: conservative direction for a refusal bar is the one that refuses more readily.
PER_LEG_DEGRADED_FOLD_FRACTION = 0.5


def per_leg_degradation_verdict(*, relative_change: float,
                                relative_claimed_effect: float,
                                degraded_folds: int, n_folds: int,
                                materiality_fraction: float = PER_LEG_MATERIALITY_FRACTION,
                                fold_fraction: float = PER_LEG_DEGRADED_FOLD_FRACTION) -> dict:
    """Did the recalibration buy the assembled atom by WRECKING THE PARTS?

    `relative_change` = (Σ recalibrated − Σ served) / Σ served over the PRICED legs — POSITIVE means
    the parts got WORSE. `relative_claimed_effect` = Δcrps(matched foil − arm) / crps(matched foil)
    — the arm's own claimed effect on the same RELATIVE scale, which is what makes the two
    comparable at all (the priced-leg sum lives at yardage scale ~36, the assembled score at ~2.5;
    only a fractional change of each is a common currency, and the raw figures are reported beside
    it so a reader can re-derive under another rule — NF-D14).

    ⛔ REGISTERED EDGE: a non-positive claimed effect makes the materiality bar non-positive, so the
    clause is UNEVALUABLE — and it is reported as such, NEVER as a pass (NF1.7 (a)). That case is
    not a loophole: the arm has already lost `beats_foil`, so the gate is lost regardless."""
    rel = float(relative_change)
    eff = float(relative_claimed_effect)
    n = int(n_folds)
    improved = rel <= 0.0
    demonstrable = bool(n > 0 and float(degraded_folds) / n > fold_fraction)
    bar = materiality_fraction * eff
    if not np.isfinite(rel) or not np.isfinite(eff) or n <= 0:
        return {"holds": False, "evaluated": False,
                "state": "UNEVALUABLE",
                "reason": "the per-leg comparison or the claimed effect is not finite / no folds "
                          "were scored — an unevaluable clause is never a pass (NF1.7 (a))",
                "relative_change": rel, "relative_claimed_effect": eff,
                "materiality_bar": None, "degraded_folds": int(degraded_folds), "n_folds": n}
    if improved:
        return {"holds": True, "evaluated": True, "state": "IMPROVED",
                "reason": f"the priced legs' summed CRPS IMPROVED by {abs(rel):.6f} relative — the "
                          f"recalibration did not buy the atom by wrecking the parts",
                "relative_change": rel, "relative_claimed_effect": eff,
                "materiality_bar": round(bar, 8), "degraded_folds": int(degraded_folds),
                "n_folds": n, "demonstrable": demonstrable, "material": False}
    if eff <= 0.0:
        return {"holds": False, "evaluated": False, "state": "UNEVALUABLE",
                "reason": f"the arm's claimed effect is {eff:.6f} ≤ 0, so the materiality bar "
                          f"({materiality_fraction:g} × the claimed effect) is non-positive and "
                          f"the clause cannot be evaluated — reported UNEVALUABLE, never a pass "
                          f"(NF1.7 (a)). The gate is already lost on `beats_foil`.",
                "relative_change": rel, "relative_claimed_effect": eff,
                "materiality_bar": round(bar, 8), "degraded_folds": int(degraded_folds),
                "n_folds": n, "demonstrable": demonstrable, "material": None}
    material = bool(rel >= bar)
    holds = not (demonstrable and material)
    return {
        "holds": holds, "evaluated": True,
        "state": ("REFUSED" if not holds else
                  "DEGRADED_BUT_IMMATERIAL" if demonstrable else "DEGRADED_BUT_NOT_DEMONSTRABLE"),
        "reason": (
            f"the priced legs' summed CRPS worsened by {rel:.6f} relative on "
            f"{int(degraded_folds)}/{n} folds against a materiality bar of {bar:.6f} "
            f"({materiality_fraction:g} × the arm's own claimed effect {eff:.6f}) — a refusal "
            f"needs the degradation to be DEMONSTRABLE (a majority of folds) AND MATERIAL "
            f"(≥ the bar); here demonstrable={demonstrable}, material={material}"),
        "relative_change": rel, "relative_claimed_effect": eff,
        "materiality_bar": round(bar, 8), "degraded_folds": int(degraded_folds), "n_folds": n,
        "demonstrable": demonstrable, "material": material,
    }


STATISTICAL_CHECKS: tuple[str, ...] = SA.STATISTICAL_CHECKS
ANCHOR_CHECKS: tuple[str, ...] = (
    "degenerates_lose", "permutation_behaves", "oracle_floors_respected",
    "mixture_is_active", "mixture_preserves_marginals", "incumbent_reproduces",
    "predecessor_reproduces", "zero_mass_hits_target", "positive_law_preserved",
    "matched_foil_identity", "cap_was_lifted", "per_leg_calibration_not_degraded",
    "independence_under_disperses", "dependence_moves_coverage", "beats_indep_on_coverage",
)

REFUSAL_MECHANISM = (
    ". The mechanism: RB's assembled calibration ALREADY cleared the PIT bar before this story ran "
    "(NF-W7e recorded 0.0242 against 0.05), so unlike QB there was no calibration defect for the "
    "marginal layer to repair — the registered question was whether removing the "
    "marginal-admissibility constraint improves RB's PROPER SCORE while holding that calibration. "
    "Read `marginal_cap` for whether the cap moved at all, and the per-leg zero-mass table for "
    "which RB cells the RAISE-ONLY splice could and could not reach.")
REFUSAL_REMEDY = (
    "NONE — a constraint refusal is not rescuable by data (NF-D18): more folds shrink the SE and "
    "make the refusal MORE certain. The remedy is a DIFFERENT MECHANISM under a FRESH registration "
    "— read `marginal_cap` below for WHICH residual the run measured — or a PM decision; ⛔ never "
    "a post-hoc bar change (E2.1-r).")

# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE RB VERDICT RULE — five states, fixed BEFORE any score (§7 of the pre-registration)
# ══════════════════════════════════════════════════════════════════════════════════════════════
RB_PAYS = "RB_RECALIBRATION_PAYS"
RB_NO_GAIN = "RB_CAP_LIFTED_NO_SCORE_GAIN"
RB_DAMAGED = "RB_CALIBRATION_DAMAGED"
CAP_INACTIVE = "CAP_NOT_LIFTED"
CAP_UNDEFINED = "UNDEFINED"
RB_STATES: tuple[str, ...] = (RB_PAYS, RB_NO_GAIN, RB_DAMAGED, CAP_INACTIVE, CAP_UNDEFINED)


def _finite(x, nd: int = 4):
    """A rounded float, or None when the quantity was never measured — so a record never prints a
    bare `nan` that a reader must know to distrust (NF1.7 (a), on the reporting side)."""
    v = float(x)
    return round(v, nd) if np.isfinite(v) else None


def rb_marginal_verdict(*, pit_by_arm: dict[str, float], cap_mean: float,
                        predecessor_cap_mean: float, realized_atom: float,
                        installed_atom: float, clamp_binding_share: float,
                        clamp_mean_move: float | None, binding_legs: dict[str, float],
                        pit_matched_foil: float | None, beats_both_foils: bool | None,
                        bar: float = PIT_MAX_DECILE_DEV,
                        min_lift: float = MIN_CAP_LIFT) -> dict:
    """⭐ Does removing RB's marginal-admissibility constraint improve the proper score WITHOUT
    losing the calibration RB already has?

    ⛔ THIS IS NOT NF-W7f's RULE, AND THE DIFFERENCE IS THE POINT. QB's `marginal_cap_verdict`
    returns CLEARS when *the cap lifted AND some real arm's PIT clears the bar*. At RB the second
    conjunct is TRUE BEFORE THE STORY RUNS (NF-W7e recorded `mix_played` at 0.0242 against a 0.05
    bar), so that rule would return a CLEARS verdict for any arm that moved the cap by a hair — a
    verdict satisfied by a mechanism that did nothing (NF1.7 (a) / NF-D20). The RB question is about
    the PROPER SCORE, held to the calibration RB already has, so the states are:

    CAP_NOT_LIFTED — the cap moved by less than the DERIVED floor. Every arm is then close to its
        own matched foil and the contest passed on nothing: the thesis is UNTESTED, not refuted
        (NF1.7 (a) / NF-D20's "count the folds the mechanism could act on"). A harness reading,
        never a finding about RB, and it publishes NO re-test trigger of any kind.
    RB_CALIBRATION_DAMAGED — the cap lifted and the best arm's PIT NO LONGER clears the bar RB
        already cleared. ⭐ The state QB's rule structurally cannot express and RB structurally
        needs: a RAISE-ONLY transform pushing atoms onto cells that already OVER-price their zero
        (the §0.2 premise) would show up exactly here, as calibration LOST rather than gained.
    RB_RECALIBRATION_PAYS — the cap lifted, PIT still clears, and the winner beats BOTH contest
        foils. The marginal layer WAS a live constraint on RB's proper score.
    RB_CAP_LIFTED_NO_SCORE_GAIN — the cap lifted, PIT still clears, and no arm beats both foils.
        The cap was REAL but not RB's binding constraint: NF-W7e's `GENUINE_ABSENCE` stands and
        RB's residual lives elsewhere. ⛔ An absence/constraint shape, not a power shortfall.
    UNDEFINED — the position was not scored. Never read as any of the above.

    ⭐ `clamp_mean_move` is reported beside `clamp_binding_share` because an ACTIVITY SHARE IS NOT A
    MAGNITUDE (NF-W7f measured a binding share BYTE-IDENTICAL before and after — 0.917 → 0.917 —
    while the clamp's mean upward move on π̂ collapsed 112×, so a headline quoting the share alone
    would have said *nothing changed* about a constraint that had stopped mattering)."""
    lifted = bool(np.isfinite(cap_mean) and np.isfinite(predecessor_cap_mean)
                  and (cap_mean - predecessor_cap_mean) >= min_lift)
    best_arm = min(pit_by_arm, key=pit_by_arm.get) if pit_by_arm else None
    if not pit_by_arm or not np.isfinite(cap_mean):
        state = CAP_UNDEFINED
    elif not lifted:
        state = CAP_INACTIVE
    elif pit_by_arm[best_arm] > bar:
        state = RB_DAMAGED
    elif beats_both_foils:
        state = RB_PAYS
    else:
        state = RB_NO_GAIN
    return {
        "state": state,
        "cap_was_lifted": lifted,
        "atom_cap_mean": round(float(cap_mean), 4) if np.isfinite(cap_mean) else None,
        "atom_cap_mean_predecessor": round(float(predecessor_cap_mean), 4)
        if np.isfinite(predecessor_cap_mean) else None,
        "cap_lift": (round(float(cap_mean - predecessor_cap_mean), 4)
                     if np.isfinite(cap_mean) and np.isfinite(predecessor_cap_mean) else None),
        "min_cap_lift_required": min_lift,
        "min_cap_lift_derivation": (
            f"realized all-zero rate {PREDECESSOR_REALIZED_ATOM} − NF-W7e's recorded RB atom cap "
            f"{PREDECESSOR_CAP_MEAN}: the recalibration has turned the knob iff the recalibrated "
            f"cap reaches the atom the population actually exhibits"),
        # ⛔ a NON-FINITE quantity renders as None, never as a bare `nan`: an UNDEFINED run has not
        # MEASURED these, and a record should say "not measured" rather than print a float-shaped
        # token a reader has to know to distrust (NF1.7 (a), on the reporting side).
        "installed_atom": _finite(installed_atom),
        "realized_all_zero_rate": _finite(realized_atom),
        "atom_shortfall_installed_vs_realized": _finite(realized_atom - installed_atom),
        "clamp_binding_share": _finite(clamp_binding_share),
        "clamp_binding_share_predecessor": PREDECESSOR_CLAMP_BINDING_SHARE,
        # ⭐ the MAGNITUDE beside the SHARE (NF-W7f) — a share can be byte-identical while the
        # constraint stops mattering
        "clamp_mean_upward_move": (None if clamp_mean_move is None
                                   else round(float(clamp_mean_move), 5)),
        "binding_leg_share": {k: round(float(v), 4) for k, v in binding_legs.items()},
        "pit_by_arm": {k: round(float(v), 4) for k, v in pit_by_arm.items()},
        "best_pit_arm": best_arm,
        "best_pit": None if best_arm is None else round(float(pit_by_arm[best_arm]), 4),
        "bar": bar,
        "pit_predecessor_already_cleared": PREDECESSOR_BEST_RB_PIT,
        "pit_matched_foil": (None if pit_matched_foil is None
                             else round(float(pit_matched_foil), 4)),
        "pit_moved_by_recalibration": (
            None if pit_matched_foil is None or PRIMARY_ARM not in pit_by_arm
            else round(float(pit_by_arm[PRIMARY_ARM] - pit_matched_foil), 4)),
        "beats_both_foils": (None if beats_both_foils is None else bool(beats_both_foils)),
        "reading": {
            RB_PAYS: ("the cap was lifted, RB's assembled PIT still clears the bar, and the winner "
                      "beats BOTH contest foils — the marginal layer was a live constraint on RB's "
                      "proper score (deploy-held, NF-G0 challenger)"),
            RB_NO_GAIN: ("the cap was lifted and RB's calibration held, but no arm beats both "
                         "contest foils — the marginal-admissibility cap was REAL and was NOT RB's "
                         "binding constraint; NF-W7e's GENUINE_ABSENCE stands and RB's residual "
                         "lives elsewhere. An absence, not a power shortfall (NF-D18)"),
            RB_DAMAGED: ("the cap was lifted and RB's assembled PIT NO LONGER clears the bar it "
                         "already cleared — the raise-only recalibration COST calibration rather "
                         "than buying it, which is what raising atoms on cells that already "
                         "over-price their zero predicts"),
            CAP_INACTIVE: ("the recalibration did not move the atom cap by the derived floor — "
                           "every arm is close to its own matched foil and the contest passed on "
                           "nothing; the thesis is UNTESTED, not refuted (NF1.7 (a) / NF-D20), and "
                           "no re-test trigger is published"),
            CAP_UNDEFINED: ("the confirmation could not run — never read as a verdict "
                            "(NF1.7 (a))"),
        }[state],
    }


PROMOTE_BLOCKERS: tuple[str, ...] = (
    "NF-W7h is DEPLOY-HELD: the RB marginal recalibration is an NF-G0 challenger and is served by "
    "nothing until governance promotes it",
    "⛔ RB ONLY. This record certifies NOTHING about QB/WR/TE — they were not scored (NF1.7 (a))",
    "⛔ A per-position-certified distribution may NOT feed a CROSS-POSITION ranking until every "
    "compared position is on the same generator AND the same level recalibration (NF-W7c §4). "
    "NF-W8's four-position optimizer input IS a ranking, so an RB certificate alone does not "
    "unblock it — QB is calibrated but CONSTRAINT_REFUSED and TE is a GENUINE_ABSENCE",
    "the recalibration CHANGES NF-W6d certified cells' marginals — a consumer reading the 52-cell "
    "substrate directly is reading the SERVED cells, not these; nothing here re-serves W6d",
    "NF-W7c's promote blockers are INHERITED in full, and RB's labelling is materially WEAKER than "
    "QB's: NF-W7e recorded RB as `partial_default` with 7 of 10 priced stats using a NF-W6d "
    "calibrated DEFAULT — a calibrated range, not a conditional projection",
    "a ship here does NOT re-open NF-W4's Layer B: availability enters as a component of the "
    "predictive's draw law and of its marginals' atom, never as a feature injected into a "
    "point/quantile learner",
    "the recalibration is certified on the NF-W7c fold axis under the declared gate league — a "
    "league or a position outside that certification is not covered by this record",
)
