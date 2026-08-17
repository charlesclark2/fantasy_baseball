"""fp_availability_mixture.py — NF-W7d: the QB AVAILABILITY MIXTURE for the assembled
fantasy-point distribution (pure).

THE STORY IN ONE PARAGRAPH. NF-W7c certified the arbitrary-league assembly at TE and was refused
at QB by ONE clause — randomized-PIT decile flatness (0.0888 against a 0.05 bar). Its §11.1
post-run finding measured why, and the measurement is unusually specific: QB is **53.9% all-zero
rows**, and its fitted correlation is mostly *"did he play"* rather than *"how did he play"* —
ρ̄ over all rows 0.239 against ρ̄ on played rows only 0.127, a ratio of **1.88×** where RB/WR/TE sit
at 1.14–1.32×. ⭐ **That RATIO orders the PIT failure across the four positions; the SIZE of the
zero atom does not** (RB carries the larger joint-zero excess and passes comfortably). One Gaussian
copula is being asked to carry a binary AVAILABILITY factor and a within-game co-movement at once
and fits a compromise between them — and a Gaussian copula has **zero tail dependence by
construction**, so at ρ̂ ≈ 0.24 it cannot reproduce a 53.9% joint-zero atom at all.

THE MECHANISM UNDER TEST. Separate the two things the single copula conflates:

    F_total(t)  =  (1 − π) · 1{t ≥ 0}  +  π · F_played(t)

a Bernoulli availability draw times a CONDITIONAL-ON-PLAYING joint draw, with Σ estimated on
PLAYED ROWS ONLY. Availability stops being a shape the copula has to imitate and becomes an
explicit component.

⭐⭐ THE PROPERTY THAT MAKES THIS COMPARABLE TO THE INCUMBENT AT ALL — THE MIXTURE IS
MARGINAL-PRESERVING BY CONSTRUCTION. A naive mixture would draw the availability event and then
draw each leg from its UNCONDITIONAL W6d bank, which double-counts the zero atom (once from the
Bernoulli, once from the bank) and would under-state every stat. The whole NF-W7 line rests on
"the marginals are frozen; only the JOINT law moves", so that is not admissible here either.

Not playing implies EVERY leg is zero, so the unconditional law of leg i decomposes exactly:

    F_i(t) = (1 − π) + π · F_i(t | played)      for t ≥ 0
  ⇒ Q_i(u | played) = Q_i( (1 − π) + π·u )

i.e. the conditional bank is the unconditional bank read at a SHIFTED uniform. So the mixture is
implemented as a **shift of the copula uniforms**, `u ↦ (1−π) + π·u`, and the leg marginals are
untouched by algebra rather than by hope — the identity is exact whenever `1 − π ≤ P(X_i = 0)` for
every leg, which is true of the true availability rate and is CLAMPED and COUNTED when the
ESTIMATE violates it (`clamp_pi`). `mixture_marginal_drift` then MEASURES the residual, and
`assemble_mixture_bank` at π ≡ 1 is BYTE-IDENTICAL to `fp_assembly.assemble_fp_bank`, which is
what makes "the availability term off" a real matched foil rather than a differently-coded one.

⚠️ THIS MUST BEAT NF-W4's NULL ×4, AND THE DISTINCTION IS REGISTERED, NOT ASSERTED. NF-W4 tested
an availability mixture and returned four nulls — but they are nulls about a DIFFERENT claim, and
NF-W4's own record says which:
  · NF-W4 **Layer A** modelled the roster PLAYED label and **SHIPPED** it (`lgbm_binary`, +0.0220
    CRPS over the injury-aware climatology, 8/8 folds, DSR 0.995). Availability is MODELABLE — that
    is a settled, certified result this story CONSUMES rather than re-litigates.
  · NF-W4 **Layer B** injected the projected availability as a **FEATURE** into the point/quantile
    champion and returned GENUINE_ABSENCE ×3 + POWER_LIMITED. That is the null: *a learner already
    given lagged usage cannot be told anything new by an availability COLUMN.*
  · NF-W7d consumes availability as a **STRUCTURAL COMPONENT OF THE PREDICTIVE'S DRAW LAW**, and
    is gated on a statistic NF-W4 never scored — the ASSEMBLED TOTAL's joint-zero atom and its
    randomized-PIT flatness. A feature cannot put an atom in a distribution; a mixture is the only
    thing that can. ⛔ A null here would be a null about the MIXTURE, and would NOT re-decide
    NF-W4; a ship here does NOT re-open NF-W4's Layer B.

⭐ AND THE ATOM IS DEFINED AS THE MEASURED MECHANISM, NOT AS THE ROSTER FLAG. §11.1's diagnosis is
stated in ALL-ZERO ROWS (53.9%), so `plays` here is the ACTIVITY indicator — "this player-week
produced a non-zero modeled stat line" — not NF-W4's roster `played` label. Three reasons, declared
before any score: it is the event the §11.1 mechanism actually names; it is the event that makes
the marginal decomposition EXACT (all-zero ⟹ every leg zero, so `1 − π ≤ P(X_i = 0)` holds by
construction at the population level); and it needs no new source, no new feature family and no new
provenance gate — it is read off the same realized stat lines the assembly is scored against. A QB
who dressed, took two snaps and threw an incompletion is "not active" here, and that is the
intended reading: he contributes to the atom the gate is failing on.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 CHALLENGER: promotes nothing,
publishes nothing, retrains nothing. Every emitted string is a calibrated RANGE — never an edge /
ROI / win-rate claim.

Pure module — no lake IO, no S3, no boto3. Runner: `run_nf_w7d_qb_availability.py`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import availability_mixture as AV
from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA
from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import joint_draw as JD
from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KW

# ── Pre-registration constants (the runner READS these — NF-D16) ────────────────────────────────
STORY = "NF-W7d"
TARGET = FA.TARGET                               # `league_fantasy_points`, the NF-W7c target
SELECTION_METRIC = FA.SELECTION_METRIC           # `crps_q199` — ⛔ selection is CRPS, see below
GATE_STATISTIC = "randomized_pit_max_decile_dev"

#: ⭐ ONE GATED POSITION. QB is the position NF-W7c refused and the only one whose PIT fails; the
#: other three are scored REPORT-ONLY (diagnostic — does the mixture HARM a position that already
#: passed?). A report-only position is never promotable from this record: a win there is a
#: hypothesis for a successor to register, never a ship (E2.1-r — a result may not be re-classified
#: into shippability after it is seen).
GATE_POSITION = "QB"
REPORT_POSITIONS: tuple[str, ...] = tuple(p for p in FA.POSITIONS if p != GATE_POSITION)
POSITIONS: tuple[str, ...] = FA.POSITIONS

LEGS = FA.LEGS
N_LEGS = FA.N_LEGS
EVAL_LEVELS = FA.EVAL_LEVELS
N_LEVELS = FA.N_LEVELS
INTEGER_LEGS = FA.INTEGER_LEGS
MIN_ESTIMATION_ROWS = FA.MIN_ESTIMATION_ROWS
ASSEMBLY_DRAWS = FA.ASSEMBLY_DRAWS
ROW_BLOCK = FA.ROW_BLOCK

#: ⭐⭐ THE DRAW SEED IS **DELIBERATELY INHERITED** FROM NF-W7c, AND THAT IS THE OPPOSITE OF SEED
#: SHOPPING. Every fresh registration in this vertical re-seeds; this one must not, because the
#: contest foil `single_copula` IS NF-W7c's pre-registered primary construction and the harness
#: proves it by REPRODUCING NF-W7c's recorded per-fold scores EXACTLY (`incumbent_reproduces`).
#: A fresh seed would move the common-random-number blocks, make that reproduction approximate,
#: and force a tolerance knob — a knob chosen after seeing the gap. Nothing can be shopped by
#: keeping it: the three mixture arms are NEW constructions that did not exist under this seed, so
#: there is no prior score for them to have been selected against.
_SEED = FA._SEED
#: The availability Bernoulli draws from an INDEPENDENT stream at this offset, so the first 13
#: base-normal columns stay byte-identical to NF-W7c's and `single_copula` reproduces exactly.
#: Availability is drawn INDEPENDENTLY of the conditional copula on purpose — that independence IS
#: the separation the story tests.
AVAIL_STREAM_OFFSET = 1_000_000

# ── The declared field (⛔ never trimmed or grown after a score — MH2 (a) / MH2.2) ───────────────
#: A COHERENT family (MH2 (a) / NF-W6b-C): three arms that differ ONLY in how π is estimated, over
#: identical mixture machinery and an identical played-only Σ. Bundling unrelated mechanisms
#: over-taxes DSR through the cross-trial dispersion channel; these three sit close by design.
#:
#: mix_learned ⭐ PRIMARY — π̂ from an in-fold binary learner on the champion feature set (the
#:               NF-W4 certified availability learner SPEC, imported not re-typed).
#: mix_clim    — π̂ from the player's own EB-shrunk lagged availability (the honest climatology).
#: mix_const   — π̂ = the position's TRAIN activity rate: per-row BLIND, zero information.
#:               ⭐ REGISTERED SHIPPABLE, on purpose. NF-D20's lesson is that a blind arm registered
#:               NON-shippable produces a null resting on a REGISTRATION CHOICE rather than on the
#:               evidence. If the per-row signal is inert and the STRUCTURE alone is what pays, this
#:               arm wins, ships, and the record says exactly that.
REAL_ARMS: tuple[str, ...] = ("mix_learned", "mix_clim", "mix_const")
PRIMARY_ARM = "mix_learned"

#: ⭐ THE TWO CONTEST FOILS — `beats_foil` binds against these and ONLY these, declared here with
#: the reason (⛔ not chosen after seeing a score):
#:   single_copula — NF-W7c's pre-registered PRIMARY (`joint_rank`), i.e. THE INCUMBENT: one
#:                   Gaussian copula, Σ on ALL train rows. Reproduced byte-for-byte.
#:   mix_off       — ⭐ THE MATCHED FOIL: the mixture's own Σ (played rows only) in a single copula
#:                   with the availability term OFF. So `mixture − mix_off` isolates the SPLIT
#:                   itself, holding the conditional Σ fixed, and `mix_off − single_copula`
#:                   isolates the Σ-estimation population. A two-step attribution, not a bundle
#:                   (NF-D10 / NF-D15 (g′): a win must be attributable to its claimed channel).
CONTEST_FOILS: tuple[str, ...] = ("single_copula", "mix_off")

#: ⭐ REFERENCE FOILS — SCORED and REPORTED, but they do NOT bind `beats_foil`, and the reason is
#: pre-registered. NF-W7c §11.4 is explicit that `classify_null` names the FOIL, not the
#: hypothesis: its QB `GENUINE_ABSENCE` answered "does assembling from per-stat parts beat
#: modelling the total directly?" — a question about ARCHITECTURE that §11.3 cards as its own
#: successor hypothesis, and NOT the question this story asks. Gating NF-W7d on
#: `foil_direct_points` would re-run that architecture verdict under a mixture badge and tell us
#: nothing about availability. Both references are still SCORED, `beats_direct_points` is REPORTED
#: on every position, and `assembled_indep` carries the three dependence clauses.
#: ⛔ They are excluded from the PBO/DSR trial field for the MH2.1 (a) reason: a diagnostic that is
#: far from the contest inflates the cross-trial dispersion `V` and over-taxes a real finding.
REFERENCE_FOILS: tuple[str, ...] = ("assembled_indep", "foil_direct_points")
FOILS: tuple[str, ...] = (*CONTEST_FOILS, *REFERENCE_FOILS)
#: The set the selection actually SEARCHED (NF1.8 — a deflation statistic over a field containing
#: its own diagnostics measures the diagnostics).
ELIGIBLE: tuple[str, ...] = (*REAL_ARMS, *CONTEST_FOILS)

#: Degenerates — ALL SCORED, ALL registered to LOSE the SELECTION metric (NF1.8 / NF-D14).
#: ⭐ `assembled_comonotone` is load-bearing twice over here. It is the over-correlated ceiling that
#: must lose CRPS — and NF-W7c measured that it has the **BEST PIT in the entire QB field**
#: (0.0563), because perfect dependence is a crude availability factor: every leg goes to zero
#: together. Scoring it is therefore the PROOF that the PIT bar is a CONSTRAINT and never a
#: selection criterion (see `SELECTION_IS_CRPS_NOT_PIT`).
DEGENERATES: tuple[str, ...] = ("nihilist_zero", "zero_width", "max_width",
                                "assembled_comonotone")

#: `assembled_indep` and `mix_off` deliberately carry NO oracle: neither estimates anything a peek
#: could improve beyond what its own arm's oracle already covers, and an anchor that cannot differ
#: from what it anchors is décor (NF1.7 (a)). `foil_direct_points` is a real learner and carries one
#: — it is the ACTIVITY POSITIVE CONTROL that proves the oracle detector can see a peek that acts.
FOILS_WITH_ORACLE: tuple[str, ...] = ("foil_direct_points",)
ANCHORS: tuple[str, ...] = (
    *DEGENERATES, "permuted_direct", "pi_permuted",
    *(f"oracle__{a}" for a in REAL_ARMS), *(f"matched_n__{a}" for a in REAL_ARMS),
    *(f"oracle__{f}" for f in FOILS_WITH_ORACLE),
)
#: Every label an arm/foil/anchor may take — the partition is guard-tested.
ALL_LABELS: tuple[str, ...] = (*REAL_ARMS, *FOILS, *ANCHORS)

# ── Gate constants — ⛔ every one INHERITED; none may be softened here (NF-D18 / E2.1-r / NF1.8) ──
COVERAGE_FLOOR = FA.COVERAGE_FLOOR
COVERAGE_BLOCK_SE = FA.COVERAGE_BLOCK_SE
PBO_MAX, DSR_MIN, FDR_Q = FA.PBO_MAX, FA.DSR_MIN, FA.FDR_Q
#: ⭐ THE BAR THIS STORY EXISTS TO CLEAR — NF-W7c's, verbatim. Re-setting a bar a predecessor
#: failed, in the story written to clear it, is the E2.1-r inversion in its most literal form.
PIT_MAX_DECILE_DEV = FA.PIT_MAX_DECILE_DEV
ORACLE_VIOLATION_ALPHA = FA.ORACLE_VIOLATION_ALPHA
ORACLE_INVERSION_MATERIAL_FRACTION = FA.ORACLE_INVERSION_MATERIAL_FRACTION
oracle_floor_state = FA.oracle_floor_state       # the three-state evaluator, imported not re-typed
ORACLE_RESPECTED, ORACLE_VIOLATED, ORACLE_INACTIVE = (
    FA.ORACLE_RESPECTED, FA.ORACLE_VIOLATED, FA.ORACLE_INACTIVE)

#: ⭐⭐ WHY PIT GATES BUT DOES NOT SELECT — the single most important design decision in this story,
#: fixed BEFORE any score and derivable from NF-W7c's COMMITTED record rather than from anything
#: this run will produce.
#:
#: The card names PIT flatness as the primary metric, and it IS the statistic the story is gated on
#: — but it may not be the statistic that RANKS the arms, because NF-W7c already measured that the
#: over-correlated degenerate `assembled_comonotone` posts the BEST PIT in the QB field (0.0563 vs
#: the winner's 0.0888) while posting the WORST CRPS (2.6954 vs 2.5859). **A criterion a degenerate
#: WINS is fatal** (NF1.8); a CONSTRAINT a degenerate satisfies is fine, because the metric then
#: eliminates it. So: arms are RANKED on `crps_q199` among the real arms, and the SELECTED arm must
#: then clear the PIT bar — PIT is a hard gate clause, never a ranking key. The degenerates are
#: scored on PIT every run and the table is printed, which is what PROVES the bar was not quietly
#: promoted into a selection criterion (NF-D18's discipline, applied to PIT rather than to
#: coverage). ⛔ Reading this as "the story moved its own primary metric" inverts it: the gate
#: statistic is unchanged and the bar is unchanged; only the RANKING key is named, and it is named
#: to keep a degenerate from winning it.
SELECTION_IS_CRPS_NOT_PIT = (
    "arms are RANKED on crps_q199; PIT flatness is a hard GATE clause on the selected arm and "
    "never a ranking key, because NF-W7c measured the over-correlated degenerate posting the best "
    "PIT in the QB field while posting the worst CRPS — a criterion a degenerate wins is fatal "
    "(NF1.8). The bar (0.05) and the statistic are NF-W7c's, unchanged.")

#: The PIT reference distribution's Monte-Carlo size — a REPORTED calibrated null (MH2.6: a
#: bootstrap describes a statistic's spread; only a calibrated null answers "would a perfectly
#: calibrated model produce a window this rough?"). ⛔ It does NOT move the bar; it makes the bar
#: readable, and it states the MDE so a pass cannot be mistaken for evidence the window could not
#: have carried.
PIT_NULL_DRAWS = 4000

#: ⭐ THE MECHANISM-ACTIVITY FLOOR (NF1.9 "a mechanism that cannot act is a finding" / NF-D20).
#: The marginal clamp below can, in principle, push π̂ back to ~1 on every row — in which case the
#: mixture IS `mix_off` and the whole contest is a comparison of an arm with itself, passing on
#: nothing. So the mean per-row atom the mixture actually installs is MEASURED and must exceed this
#: floor, or the arm is declared INACTIVE rather than scored. Derived from a design quantity, not
#: tuned: one percent of the assembled mass is below any effect this gate could act on, and NF-W7c
#: measured the QB atom it is meant to model at 53.9%.
MIN_MIXTURE_ATOM = 0.01
#: Rows / draws the marginal-drift diagnostic pools over (a structural check, not an estimate).
DRIFT_ROWS, DRIFT_DRAWS = 96, 1000
#: The marginal-preservation tolerance, in **PROBABILITY** units — the sup distance between the
#: mixture's realized leg distribution and the availability-off construction's.
#:
#: ⚠️ IT MUST BE A PROBABILITY, NOT A VALUE. A first cut measured the drift in units of each leg's
#: own inter-decile range and read 10.0 on an EXACT construction — because a mostly-zero integer
#: leg (a QB's receptions, anyone's two-point conversions) has an inter-decile range of 0 or 1, so
#: a single unit of discretization divides by nothing and reports a catastrophe. The claim being
#: tested is "no probability mass moved", so the metric is a Kolmogorov distance and the units are
#: the claim's own.
#:
#: ⛔ DERIVED FROM A DESIGN QUANTITY, NOT TUNED TO A MEASUREMENT: the diagnostic pools
#: `DRIFT_ROWS × DRIFT_DRAWS` = 96,000 draws per leg, so the Monte-Carlo standard error of a
#: pooled ECDF is ≤ 1/(2√N) ≈ 0.0016 and three of them is ≈ 0.005. Rounded UP to 0.01 — twice the
#: MC floor, and still an order of magnitude below the ~26% zero-mass a double-counted atom would
#: move, which is the defect this clause exists to catch.
MAX_MARGINAL_DRIFT = 0.01

STATISTICAL_CHECKS: tuple[str, ...] = (
    "beats_foil", "fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok", "coverage_floor_ok",
    "pit_flat_ok",
)
ANCHOR_CHECKS: tuple[str, ...] = (
    "degenerates_lose", "permutation_behaves", "oracle_floors_respected",
    "mixture_is_active", "mixture_preserves_marginals", "incumbent_reproduces",
    "independence_under_disperses", "dependence_moves_coverage", "beats_indep_on_coverage",
)

REFUSAL_MECHANISM = (
    ". The mechanism: the availability MIXTURE moves the assembled QB predictive in the modelled "
    "direction but does not carry it across the pre-registered bar — separating the Bernoulli "
    "availability factor from the conditional-on-playing joint law prices the atom this population "
    "carries, and what remains is either the CONDITIONAL dependence shape (a Gaussian copula still "
    "has zero tail dependence among the played rows) or the availability probability's own "
    "resolution.")
REFUSAL_REMEDY = (
    "NONE — a constraint refusal is not rescuable by data (NF-D18): more folds shrink the SE and "
    "make the refusal MORE certain. The remedy is a DIFFERENT MECHANISM under a FRESH registration "
    "(the NF-MARGIN2→3 / NF-W6b-C successor pattern — a tail-dependent or atom-aware conditional "
    "copula, or a sharper availability probability), or a PM decision; ⛔ never a post-hoc bar "
    "change (E2.1-r / NF1.8).")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The atom: what "plays" MEANS here
# ══════════════════════════════════════════════════════════════════════════════════════════════
def activity_indicator(raw: np.ndarray) -> np.ndarray:
    """1 where the player-week produced a NON-ZERO modeled stat line, 0 where every leg is zero.

    ⭐ This is the event NF-W7c §11.1 measured (QB 53.9% all-zero rows), and it is deliberately NOT
    NF-W4's roster `played` label: it is the event that GENERATES the assembled total's atom, and
    the event under which the conditional-marginal decomposition is EXACT (all legs zero ⟹ every
    leg's zero mass is at least the atom, so the uniform shift can never remove positive mass).
    """
    m = np.asarray(raw, dtype=float)
    if m.ndim != 2 or m.shape[1] != N_LEGS:
        raise ValueError(f"raw outcome matrix is {m.shape}, expected (n, {N_LEGS}) in LEGS order")
    return (np.abs(np.nan_to_num(m, nan=0.0)) > 0).any(axis=1).astype(float)


def atom_rate(raw: np.ndarray) -> float:
    """The all-zero share — the quantity §11.1's QB row reports as 53.9%."""
    return float(1.0 - activity_indicator(raw).mean())


# ══════════════════════════════════════════════════════════════════════════════════════════════
# π̂ — the availability probability (three estimators, one signature)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: The NF-W4 certified availability learner SPEC and EB constants, IMPORTED — a re-typed copy is a
#: copy that drifts (the NF-C0e wrong-key class), and re-deriving a certified family is exactly
#: what NF-W4's own contract forbids.
_lgbm_clf = AV._lgbm_clf
EB_KAPPA_AVAIL = AV.EB_KAPPA_AVAIL
N_L4_EVIDENCE = AV.N_L4_EVIDENCE
#: The one lagged availability column the CHAMPION feature set already carries. It is the roster
#: played share, not this story's activity indicator — a deliberate, DISCLOSED mismatch: it makes
#: the climatology arm a weaker (honest) baseline rather than a stronger one, and the learned arm
#: is free to use it alongside everything else.
CLIM_FEATURE = "prior_week_box__played_share_l4"


def pi_const(train: pd.DataFrame, test: pd.DataFrame, features: list[str], *,
             train_raw: np.ndarray, y_train: np.ndarray | None = None) -> np.ndarray:
    """π̂ = the TRAIN activity rate, broadcast. Per-row BLIND — registered SHIPPABLE (NF-D20)."""
    y = activity_indicator(train_raw) if y_train is None else np.asarray(y_train, dtype=float)
    return np.full(len(test), float(np.clip(y.mean(), 1e-6, 1 - 1e-6)))


def pi_clim(train: pd.DataFrame, test: pd.DataFrame, features: list[str], *,
            train_raw: np.ndarray, y_train: np.ndarray | None = None) -> np.ndarray:
    """π̂ = the player's own lagged availability, EB-shrunk toward the TRAIN activity rate.

    NULL-BEARING: a missing window (a first appearance) is honestly the base rate, ⛔ never 0
    (NF-W0b — an unmeasured history is unknown, not absent)."""
    y = activity_indicator(train_raw) if y_train is None else np.asarray(y_train, dtype=float)
    base = float(np.clip(y.mean(), 1e-6, 1 - 1e-6))
    l4 = pd.to_numeric(test[CLIM_FEATURE], errors="coerce").to_numpy(dtype=float)
    blended = ((EB_KAPPA_AVAIL * base + N_L4_EVIDENCE * np.nan_to_num(l4, nan=base))
               / (EB_KAPPA_AVAIL + N_L4_EVIDENCE))
    return np.clip(np.where(np.isfinite(l4), blended, base), 1e-6, 1 - 1e-6)


def pi_learned(train: pd.DataFrame, test: pd.DataFrame, features: list[str], *,
               train_raw: np.ndarray, y_train: np.ndarray | None = None) -> np.ndarray:
    """π̂ from the NF-W4 certified binary learner spec, on the champion feature set.

    ⛔ Nothing new is consumed: the features are `weekly_projection.FEATURES` (already PIT-gated
    and provenance-checked by the reused matrix builder) and the label is derived from the SAME
    realized stat lines the assembly is scored against."""
    y = activity_indicator(train_raw) if y_train is None else np.asarray(y_train, dtype=float)
    m = _lgbm_clf()
    m.fit(GE._X(train, features), (y == 1.0).astype(int))
    return np.clip(m.predict_proba(GE._X(test, features))[:, 1], 1e-6, 1 - 1e-6)


PI_FITTERS = {"mix_learned": pi_learned, "mix_clim": pi_clim, "mix_const": pi_const}


def pi_for_arm(arm: str, train: pd.DataFrame, test: pd.DataFrame, features: list[str], *,
               train_raw: np.ndarray, y_train: np.ndarray | None = None) -> np.ndarray:
    """The arm's π̂ from ITS pre-registered estimator — the caller supplies the estimation context
    (train for a real arm, test for an oracle, the matched slice for the capacity control), so no
    arm can quietly change estimator."""
    if arm not in PI_FITTERS:
        raise KeyError(f"unknown mixture arm `{arm}` — not in the pre-registered family "
                       f"{REAL_ARMS}")
    return PI_FITTERS[arm](train, test, features, train_raw=train_raw, y_train=y_train)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Σ on PLAYED rows only — the conditional half of the separation
# ══════════════════════════════════════════════════════════════════════════════════════════════
def sigma_played(raw: np.ndarray, *, one_factor: bool = False,
                 min_rows: int = MIN_ESTIMATION_ROWS) -> tuple[np.ndarray, dict]:
    """The story's conditional Σ̂: NF-W7c's raw-rank estimator restricted to ACTIVE rows.

    ⭐ This is half the hypothesis. §11.1 measured QB's all-row ρ̄ at 0.239 against 0.127 on played
    rows — the single copula fits a compromise between an availability factor and a within-game
    structure, and estimating on played rows only is what makes the second one estimable at all.

    REFUSES below the row floor by delegating to `FA.position_sigma` — an unevaluable estimate must
    never masquerade as independence (NF1.7 (a))."""
    m = np.asarray(raw, dtype=float)
    active = activity_indicator(m) == 1.0
    if int(active.sum()) < min_rows:
        raise ValueError(
            f"dependence estimation refused: {int(active.sum())} ACTIVE rows < {min_rows} — the "
            f"conditional-on-playing correlation is unevaluable on this slice and must not be "
            f"silently replaced by the unconditional one")
    sig, note = FA.position_sigma(m[active], min_rows=min_rows)
    if one_factor:
        sig, lam = JD.one_factor_corr(sig)
        note = {**note, "structure": "one_factor",
                "loadings": {LEGS[i]: round(float(v), 4) for i, v in enumerate(lam)}}
    return sig, {**note, "population": "active_rows_only", "n_active": int(active.sum()),
                 "n_all": int(len(m)), "atom_rate": round(atom_rate(m), 4)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The marginal-preservation clamp (the exactness condition, enforced and COUNTED)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def leg_zero_mass(banks: np.ndarray) -> np.ndarray:
    """(n, 13) the probability mass each row's own W6d bank places on a leg drawing exactly 0.

    ⚠️ TWO ALIGNMENTS, both of which a naive reading gets wrong and both of which show up as
    marginal drift:
      · the POST-ROUNDING threshold — `FA.draw_legs` rounds integer legs, so a bank value below
        0.5 draws as a zero and IS removable mass; and
      · the SAMPLER'S OWN GRID — draws come from `np.interp` over `EVAL_LEVELS`, so the mass at or
        below the threshold is read as the LEVEL of the last bank knot that clears it, not as a
        fraction of knots. Reading it as a fraction over-states the removable mass by up to one
        level and lets the uniform shift eat genuine positive mass.
    Both errors here are taken in the CONSERVATIVE direction (a smaller removable mass raises the
    floor, so the mixture is clamped toward the incumbent rather than toward a distorted marginal)."""
    b = np.asarray(banks, dtype=float)
    if b.ndim != 3 or b.shape[1] != N_LEGS or b.shape[2] != N_LEVELS:
        raise ValueError(f"banks are {b.shape}, expected (n, {N_LEGS}, {N_LEVELS})")
    thr = np.array([0.5 if leg in INTEGER_LEGS else 0.0 for leg in LEGS], dtype=float)
    # the bank is sorted, so the count of knots at/below the threshold locates the last such knot
    idx = (b <= thr[None, :, None]).sum(axis=2) - 1
    return np.where(idx >= 0, EVAL_LEVELS[np.clip(idx, 0, N_LEVELS - 1)], 0.0)


def pi_floor(banks: np.ndarray) -> np.ndarray:
    """(n,) the SMALLEST availability probability the row's own marginals admit.

    The uniform shift `u ↦ (1−π) + π·u` removes the bottom `1−π` of every leg's bank. It is
    marginal-preserving exactly while that removed mass is all ZERO mass, i.e. while
    `1 − π ≤ min_i P̂_i(0)`. At the population level the true availability rate satisfies this by
    construction (not-active ⟹ every leg zero); an ESTIMATE need not, so the binding case is
    clamped and counted rather than silently distorting a marginal."""
    return 1.0 - leg_zero_mass(banks).min(axis=1)


def clamp_pi(pi: np.ndarray, banks: np.ndarray) -> tuple[np.ndarray, dict]:
    """π̂ raised to the marginal-admissible floor, with the binding RECORDED.

    ⛔ Fails LOUD, never silently: the returned note carries the binding rate and the mean/max
    upward move, because a clamp that binds on every row would make the mixture identical to its
    own matched foil — a mechanism that cannot act, which is a finding and not a pass (NF1.9 /
    NF-D20). The gate reads it through `mixture_is_active`."""
    p = np.asarray(pi, dtype=float)
    floor = pi_floor(banks)
    if p.shape != floor.shape:
        raise ValueError(f"pi is {p.shape} but the bank tensor implies {floor.shape} rows")
    used = np.clip(np.maximum(p, floor), 0.0, 1.0)
    binds = used > p + 1e-12
    return used, {
        "n_rows": int(len(p)),
        "clamp_binding_share": round(float(binds.mean()), 4),
        "mean_pi_hat": round(float(p.mean()), 4),
        "mean_pi_used": round(float(used.mean()), 4),
        "mean_upward_move": round(float(np.mean(used - p)), 4),
        "max_upward_move": round(float(np.max(used - p)) if len(p) else 0.0, 4),
        "mean_installed_atom": round(float(np.mean(1.0 - used)), 4),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The mixture assembly — Bernoulli(π) × the conditional joint draw
# ══════════════════════════════════════════════════════════════════════════════════════════════
def mixture_leg_draws(banks_block: np.ndarray, base_z: np.ndarray, *, pi: np.ndarray,
                      corr: np.ndarray, seed: int = _SEED, block_start: int = 0) -> np.ndarray:
    """(b, draws, 13) leg draws under the mixture — ⭐ **THE ONE CODE PATH**, shared by the
    assembly that is SCORED and by the marginal-preservation diagnostic that VALIDATES it.

    ⚠️ IT IS ONE FUNCTION BECAUSE A RED PROOF CAUGHT IT BEING TWO. The first cut implemented the
    conditional uniform shift separately in `assemble_mixture_bank` and in
    `mixture_marginal_drift`; deleting the shift from the assembly — i.e. shipping the exact
    double-counted-atom defect the clause exists to catch — left the whole suite GREEN, because the
    diagnostic was validating its own copy of the logic rather than the path being scored. That is
    the NF-C0e "a test that reads a value back under the key the code writes" / INC-39
    "one test must exercise the REAL leg" class, and the cure is structural, not another test."""
    u = JD.gaussian_copula_uniforms(base_z, corr)
    # the CONDITIONAL-on-playing marginal, read as a shifted uniform (see the module docstring)
    u = (1.0 - pi)[:, None, None] + pi[:, None, None] * u
    x = FA.draw_legs(banks_block, u)
    arng = np.random.default_rng(seed + AVAIL_STREAM_OFFSET + block_start)
    alive = arng.random(base_z.shape[:2]) < pi[:, None]
    return np.where(alive[:, :, None], x, 0.0)


def assemble_mixture_bank(banks: np.ndarray, weights: np.ndarray, *, pi: np.ndarray,
                          corr: np.ndarray, draws: int = ASSEMBLY_DRAWS, seed: int = _SEED,
                          row_block: int = ROW_BLOCK) -> np.ndarray:
    """One assembled (n, 199) league-fantasy-point bank under the availability mixture.

    ⭐ AT π ≡ 1 THIS IS BYTE-IDENTICAL TO `FA.assemble_fp_bank(mode="copula", corr=corr)`. That is
    not a coincidence to be checked once and forgotten — it is what makes `mix_off` a MATCHED foil
    (same code path, availability term off) rather than a differently-implemented one, and it is
    guard-tested. The base normals depend only on (block index, draws, seed) exactly as NF-W7c's
    do, so common random numbers are shared across every arm, foil and anchor of a fold.

    The Bernoulli draws from a SEPARATE generator at `AVAIL_STREAM_OFFSET`, which (a) leaves the
    13 copula columns untouched so `single_copula` reproduces NF-W7c exactly, and (b) makes the
    availability event INDEPENDENT of the conditional joint — the separation under test."""
    b = np.asarray(banks, dtype=float)
    if b.ndim != 3 or b.shape[1] != N_LEGS or b.shape[2] != N_LEVELS:
        raise ValueError(f"banks are {b.shape}, expected (n, {N_LEGS}, {N_LEVELS})")
    w = np.asarray(weights, dtype=float)
    if w.shape != (N_LEGS,):
        raise ValueError(f"weights are {w.shape}, expected ({N_LEGS},)")
    p = np.asarray(pi, dtype=float)
    if p.shape != (b.shape[0],):
        raise ValueError(f"pi is {p.shape}, expected ({b.shape[0]},) — one availability "
                         f"probability per assembled row")
    if not np.all(np.isfinite(p)) or float(p.min()) < 0.0 or float(p.max()) > 1.0:
        raise ValueError("pi carries non-finite or out-of-[0,1] values — an availability "
                         "probability that is not a probability is a coding defect, not an arm")
    n = b.shape[0]
    out = np.empty((n, N_LEVELS), dtype=float)
    for start in range(0, n, row_block):
        stop = min(start + row_block, n)
        rng = np.random.default_rng(seed + start)
        base_z = rng.standard_normal((stop - start, draws, N_LEGS))
        legs = mixture_leg_draws(b[start:stop], base_z, pi=p[start:stop], corr=corr, seed=seed,
                                 block_start=start)
        out[start:stop] = np.quantile(legs @ w, EVAL_LEVELS, axis=1).T
    return out


def mixture_marginal_drift(banks: np.ndarray, *, pi: np.ndarray, corr: np.ndarray,
                           draws: int = DRIFT_DRAWS, seed: int = _SEED,
                           n_rows: int = DRIFT_ROWS) -> dict:
    """⭐ MEASURED PROOF that the mixture moved the JOINT law and nothing else.

    Each leg's realized draw distribution under the mixture is compared against the SAME
    construction with the availability term off (π ≡ 1, common random numbers) as a **Kolmogorov
    distance — a sup difference of two CDFs, in PROBABILITY units**. The algebra says this is zero;
    the number says whether the code agrees, and it is the clause that would catch a
    double-counted zero atom, the defect a naive availability mixture ships silently and which
    would surface here as ~`mean(1−π)` of displaced mass.

    ⚠️ THE UNITS ARE THE CLAIM'S OWN, AND A FIRST CUT GOT THEM WRONG. Measuring the drift in units
    of each leg's inter-decile RANGE read 10.0 on a construction that is exact by algebra — because
    a mostly-zero integer leg (a QB's receptions, anyone's two-point conversions) has an
    inter-decile range of 0 or 1, so one unit of discretization divides by nothing and reports a
    catastrophe. The claim under test is "no probability mass moved"; the metric must be a
    probability.

    Pooled over rows AND draws per leg: both sides pool the SAME rows in the same proportion, so a
    per-row marginal violation cannot cancel in the pool, while the pooled ECDF's Monte-Carlo noise
    falls to ~1/(2√96,000). Per-row ECDFs at this draw count would be noise-dominated by the
    availability Bernoulli alone and could not resolve the tolerance."""
    b = np.asarray(banks, dtype=float)[:n_rows]
    p = np.asarray(pi, dtype=float)[:n_rows]
    if not len(b):
        raise ValueError("marginal-drift diagnostic received no rows — a check that did not run "
                         "is not a pass (NF1.7 (a))")
    rng = np.random.default_rng(seed)
    base_z = rng.standard_normal((len(b), draws, N_LEGS))
    # ⭐ BOTH SIDES ARE THE REAL SCORED PATHS, and that asymmetry is deliberate: the mixture side
    # is `mixture_leg_draws` (what the assembly runs) and the reference side is `FA._uniforms` +
    # `FA.draw_legs` (what `mix_off` runs). Routing both through the SAME helper would make a
    # defect in the shift cancel on both sides and the clause pass on nothing.
    mix = mixture_leg_draws(b, base_z, pi=p, corr=corr, seed=seed)
    off = FA.draw_legs(b, FA._uniforms(base_z, "copula", corr))
    per_leg: dict[str, float] = {}
    for i, leg in enumerate(LEGS):
        x_off = off[:, :, i].ravel()
        x_mix = mix[:, :, i].ravel()
        grid = np.unique(np.quantile(x_off, EVAL_LEVELS))
        f_off = (x_off[None, :] <= grid[:, None]).mean(axis=1)
        f_mix = (x_mix[None, :] <= grid[:, None]).mean(axis=1)
        per_leg[leg] = round(float(np.max(np.abs(f_off - f_mix))), 5)
    worst = max(per_leg.values())
    return {"max_probability_drift": worst, "per_leg": per_leg, "n_rows": int(len(b)),
            "draws": int(draws), "tolerance": MAX_MARGINAL_DRIFT,
            "units": "probability — sup |F_mixture − F_availability_off| per leg",
            "preserved": bool(worst <= MAX_MARGINAL_DRIFT)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PIT — the gate statistic, WITH its direction (NF-W7c §11.2's carded instrumentation gap)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def pit_detail(u: np.ndarray) -> dict:
    """`KW.pit_flatness` plus the DECILE VECTOR that NF-W7c could not recover without another run.

    §11.2, verbatim: "the record stores only `max_decile_dev` — not the decile vector, not WHICH
    decile is off … the direction of miscalibration is not recoverable without another run …
    Any successor touching calibration should carry the decile vector." This is that successor, so
    it carries it — as COUNTS, which pool exactly across folds at no storage cost."""
    base = KW.pit_flatness(u)
    v = np.asarray(u, dtype=float)
    v = v[np.isfinite(v)]
    counts, _ = np.histogram(v, bins=10, range=(0, 1))
    freq = (counts / len(v)) if len(v) else np.full(10, np.nan)
    return {**base, "decile_counts": [int(c) for c in counts],
            "decile_freq": [round(float(f), 4) for f in freq],
            "worst_decile": (int(np.argmax(np.abs(freq - 0.1))) if len(v) else None)}


def pooled_pit(decile_counts: list[list[int]]) -> dict:
    """The ROW-POOLED PIT across folds, from the stored counts (NF1.8: pool over ROWS for any
    per-group statistic). ⛔ REPORTED beside — never instead of — the inherited per-fold mean,
    which is NF-W7c's convention and is the one that BINDS; swapping conventions in the story
    written to clear a bar the predecessor failed is the E2.1-r inversion."""
    total = np.sum(np.asarray(decile_counts, dtype=float), axis=0)
    n = float(total.sum())
    if n <= 0:
        return {"max_decile_dev": None, "n": 0, "decile_freq": None}
    freq = total / n
    return {"max_decile_dev": round(float(np.max(np.abs(freq - 0.1))), 4), "n": int(n),
            "decile_freq": [round(float(f), 4) for f in freq],
            "worst_decile": int(np.argmax(np.abs(freq - 0.1)))}


def pit_null_reference(n: int, *, draws: int = PIT_NULL_DRAWS, seed: int = _SEED) -> dict:
    """The max-decile-deviation a PERFECTLY calibrated predictive posts at this sample size.

    MH2.6's discipline: a bar without a calibrated null cannot say whether a value is rough or
    whether the window was simply too small to be smooth. ⛔ This does NOT move the bar — the bar
    is NF-W7c's 0.05 — it makes the bar readable and states what the window could have detected."""
    if n <= 0:
        raise ValueError("the PIT null reference needs a positive sample size — a reference "
                         "computed on nothing is a pass on nothing (NF1.7 (a))")
    rng = np.random.default_rng(seed)
    devs = np.empty(draws, dtype=float)
    for i in range(draws):
        counts, _ = np.histogram(rng.random(n), bins=10, range=(0, 1))
        devs[i] = np.max(np.abs(counts / n - 0.1))
    return {
        "n": int(n), "draws": int(draws),
        "median": round(float(np.median(devs)), 4),
        "p95": round(float(np.quantile(devs, 0.95)), 4),
        "p_exceeds_bar_under_perfect_calibration": round(
            float((devs > PIT_MAX_DECILE_DEV).mean()), 4),
        "bar": PIT_MAX_DECILE_DEV,
    }


def pit_null_pvalue(observed: float, n: int, *, draws: int = PIT_NULL_DRAWS,
                    seed: int = _SEED) -> float:
    """P(a perfectly calibrated predictive at this n is at least this rough)."""
    rng = np.random.default_rng(seed + 7)
    hits = 0
    for _ in range(draws):
        counts, _ = np.histogram(rng.random(n), bins=10, range=(0, 1))
        hits += int(np.max(np.abs(counts / n - 0.1)) >= observed)
    return round((hits + 1) / (draws + 1), 5)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The incumbent-reproduction control
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: NF-W7c's committed record and the arm whose construction `single_copula` reproduces.
INCUMBENT_RECORD_RELPATH = FA.RECORD_RELPATH
INCUMBENT_ARM = "joint_rank"
INCUMBENT_FOIL = "single_copula"
#: ⭐ EXACT, not approximate. Same marginals, same folds, same seed, same construction ⇒ the same
#: float. A tolerance here would be a knob; 1e-9 is float noise in a sum of ~700 CRPS terms.
INCUMBENT_TOLERANCE = 1e-9


def incumbent_reproduction(fold_scores: dict[str, float], record_scores: dict[str, float],
                           *, tolerance: float = INCUMBENT_TOLERANCE) -> dict:
    """Per-fold |`single_copula` − NF-W7c's `joint_rank`| — the harness's own identity proof.

    ⭐ WHY THIS IS THE STRONGEST CONTROL IN THE STORY. Every comparison here is "the mixture
    against the incumbent". If the marginals, folds, draws or scoring had drifted by ANY amount,
    the contest would be measuring the drift and would still look perfectly plausible. Reproducing
    the predecessor's recorded per-fold numbers to float precision makes that failure mode
    impossible to miss — and it can only be checked because the draw seed was deliberately
    inherited rather than refreshed (see `_SEED`)."""
    gaps = {label: abs(fold_scores[label] - record_scores[label])
            for label in sorted(set(fold_scores) & set(record_scores))}
    if not gaps:
        return {"reproduces": False, "n_folds_compared": 0, "max_abs_gap": None,
                "note": ("no fold label matched the NF-W7c record — the comparison did not run, "
                         "which is not a pass (NF1.7 (a))")}
    worst = max(gaps.values())
    return {"reproduces": bool(worst <= tolerance), "n_folds_compared": len(gaps),
            "max_abs_gap": float(worst), "tolerance": tolerance,
            "per_fold_abs_gap": {k: float(v) for k, v in gaps.items()}}


PROMOTE_BLOCKERS: tuple[str, ...] = (
    "NF-W7d is DEPLOY-HELD: the availability-mixture assembly is an NF-G0 challenger and is served "
    "by nothing until governance promotes it",
    "QB is the ONLY gated position — RB/WR/TE are scored REPORT-ONLY and a win there is a "
    "hypothesis for a successor to register, never a ship from this record (E2.1-r)",
    "NF-W7c's promote blockers are INHERITED in full: an assembled row whose `source` is not "
    "`bakeoff_all_priced_legs` carries a NF-W6d calibrated DEFAULT among the legs this league "
    "prices, and a league pricing a SKILL_UNMODELED_KEYS term has a real coverage gap",
    "a ship here does NOT re-open NF-W4's Layer B: this story consumes availability as a component "
    "of the predictive's draw law, never as a feature injected into a point/quantile learner",
    "the mixture is certified on the NF-W7c fold axis under the declared gate league — a league or "
    "a position outside that certification is not covered by this record",
)
