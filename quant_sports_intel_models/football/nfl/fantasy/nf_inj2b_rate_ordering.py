"""nf_inj2b_rate_ordering.py — NF-INJ2b: order the multiset the learner was FITTED to order.

⭐ READ `ablation_results/nf_inj2b_preregistration.md` FIRST. It is THIS story's pre-registration,
committed before any arm was scored. ⛔ Editing it after a result is not a pre-registration (E2.1-r);
anything the decisive run overturns is left in place under a `SUPERSEDED` marker, verbatim (NF-W7f).

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT NF-INJ2's REFUSAL NAMED
────────────────────────────────────────────────────────────────────────────────────────────────
`rate_permute` restored coherence on the served board (10 → 0 attributable impossible rows), turned
the injury give-back from +33.96% into −11.99%, and WON the selecting metric — and was refused on the
pre-registered ORDERING constraint at QB (draftable-tier ρ 0.481 → 0.350, BH-significant). Its own
§6b decomposition named the successor: NF1.5's ordering learner is fitted on `real_fp_ppr`, a season
TOTAL, so it was selected to order POINTS. Handing it a per-game RATE multiset asks a question it was
never validated on, and the mismatch is largest exactly where the games spread is widest.

THE MECHANISM, stated so it can be refuted. Under the coherent form the served point is
`rate_{σ(i)} × games_i`, where σ ranks by the learned score. A POINTS-fitted score already prices
availability (through `mvp1_fp`, `expected_games`, `base_games`), so availability is priced TWICE —
once in deciding which rate a row receives, and once in the multiply. A RATE-fitted score is asked
only to rank rates, so availability enters exactly once, at the multiply.

⚠️ AND THE BOUND ON THAT MECHANISM, MEASURED BEFORE ANY SCORING (pre-registration §1b, so it cannot
read as a post-hoc excuse): the fit target reaches `PosRefinedBlend`'s score ONLY through its inner
model, which exists only when `anchor == "learned"`. RB's selected class anchors on `mvp1_fp`, so at
RB the re-fit is **byte-identically INACTIVE** (measured max |Δscore| = 0.000e+00) and an RB result
under the primary is UNINFORMATIVE, never a pass (NF-D20). Where it IS active the re-fitted score is
still ≥0.9918 rank-correlated with the incumbent's, because the market axis (`market_score`, an
ADP/ECR season-TOTAL consensus) is target-invariant. A target swap alone therefore cannot make the
score availability-neutral — which is why the registered field also carries an arm that acts on the
MULTIPLY rather than on the score.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT THIS MODULE IS
────────────────────────────────────────────────────────────────────────────────────────────────
The pure assignment kernel for the declared 2×2, plus the serving POLICY. Two factors:

    F1  the score's FIT TARGET      points | rate            ← supplied by the CALLER as `score`
    F2  the multiset + ASSIGNMENT   point-by-score | rate-by-score | *-within-strata

F1 lives in the score the caller hands in, so arms that differ only in F1 route to the SAME
assignment rule and cannot drift apart. F2 lives here. Everything NF-INJ2 already implements is
DELEGATED to it rather than reimplemented — one kernel per rule, so the arm the bake-off scores and
the arm the board would serve are the same code (NF-C0e).

⚠️ ONE OWNER FOR THE SERVED ARM. Two policy modules each claiming to name the served arm is the
"one logical thing, two execution owners" class this repo keeps paying for (INC-30 / INC-36 /
INC-38). `resolve_served_arm()` is the SINGLE authority, and `assert_coherent()` runs at import and
refuses a state in which both modules name a non-incumbent arm.
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import nf_inj2_rate_permutation as _RP

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered field (nf_inj2b_preregistration.md §2) — DECLARED FORWARD
# ══════════════════════════════════════════════════════════════════════════════════════════════
PRIMARY_ARM = "rate_refit"
INCUMBENT_ARM = "incumbent"

#: pre-registered DEGENERATES — they MUST lose. Declared here, before any score, so the DSR-CONV
#: convention (degenerate ∈ n_trials, ∉ V) is a property of the REGISTRATION and not of the result
#: (⛔ declaring an arm degenerate after seeing it lose is laundering — CLAUDE.md DSR-CONV).
DEGENERATE_ARMS: tuple[str, ...] = ("mvp1_null", "random_order")

#: ⭐ MH2.1 (a) — `incumbent`'s lift series is identically ZERO by construction, and a structural 0.0
#: inflates a small family's cross-trial dispersion `V` exactly as a diagnostic anchor does. It is
#: excluded from `V` and KEPT in `n_trials`. Declared here, before any score (the NF-INJ3 lesson:
#: a pre-registration must name its deflation conventions, not just its arms).
REFERENCE_ARMS: tuple[str, ...] = (INCUMBENT_ARM,)

#: the ten declared arms. `declared_field_size = 10` is what `cv_power.classify_null` is told.
ARMS: tuple[str, ...] = (
    "incumbent",               # F1 points · F2 point-by-score      — the reference / the ordering bar
    "points_rate_permute",     # F1 points · F2 rate-by-score       — NF-INJ2's refused arm, carried
    "rate_refit",              # F1 RATE   · F2 rate-by-score       — PRIMARY
    "points_rate_stratified",  # F1 points · F2 rate-within-strata  — the 2×2's fourth cell
    "rate_refit_stratified",   # F1 RATE   · F2 rate-within-strata  — acts on the MULTIPLY
    "rate_refit_reselect",     # F1 RATE, class chosen IN-FOLD      — the "re-select" half
    "stratified",              # F1 points · F2 point-within-strata — carried by name
    "feasibility_clamp",       # F1 points · F2 point-by-score, envelope-bounded — carried by name
    "mvp1_null",               # DEGENERATE — no re-order at all
    "random_order",            # DEGENERATE — a seeded within-position random permutation
)
DECLARED_FIELD_SIZE = len(ARMS)

#: F1 — WHICH fitted score each arm is ordered by. The runner supplies the array; this table is what
#: makes "these two arms differ ONLY in the fit target" a property of the registration rather than of
#: a call site. `None` = the arm ignores the score entirely (the degenerates).
SCORE_OF: Mapping[str, str | None] = {
    "incumbent": "points",
    "points_rate_permute": "points",
    "rate_refit": "rate",
    "points_rate_stratified": "points",
    "rate_refit_stratified": "rate",
    "rate_refit_reselect": "rate_reselect",
    "stratified": "points",
    "feasibility_clamp": "points",
    "mvp1_null": None,
    "random_order": None,
}

#: F2 — the assignment rule each arm uses. Arms sharing a rule share the CODE PATH exactly, so a
#: matched pair differing only in F1 cannot acquire a second difference by accident.
ASSIGNMENT_OF: Mapping[str, str] = {
    "incumbent": "point_by_score",
    "points_rate_permute": "rate_by_score",
    "rate_refit": "rate_by_score",
    "points_rate_stratified": "rate_within_strata",
    "rate_refit_stratified": "rate_within_strata",
    "rate_refit_reselect": "rate_by_score",
    "stratified": "point_within_strata",
    "feasibility_clamp": "point_by_score_clamped",
    "mvp1_null": "identity",
    "random_order": "random",
}

#: the arm names NF-INJ2's kernel owns, keyed by OUR assignment rule. Delegation, never a re-write.
_DELEGATE_TO_NF_INJ2: Mapping[str, str] = {
    "point_by_score": "incumbent",
    "rate_by_score": "rate_permute",
    "point_within_strata": "stratified",
    "point_by_score_clamped": "feasibility_clamp",
    "identity": "mvp1_null",
    "random": "random_order",
}

#: ⭐ THE MATCHED PAIRS, declared now (NF-D15 g′ / NF-W7e). Each is (arm, foil, what it isolates).
#: A pair whose two members share an `ASSIGNMENT_OF` value differs ONLY in the fit target; a pair
#: sharing a `SCORE_OF` value differs ONLY in the assignment rule. `assert_coherent` PROVES that,
#: rather than trusting this comment.
MATCHED_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("rate_refit", "points_rate_permute", "TARGET — the fit target is the only difference"),
    ("rate_refit_stratified", "points_rate_stratified", "TARGET, inside the stratified assignment"),
    ("rate_refit_stratified", "rate_refit", "ASSIGNMENT — the stratification is the only difference"),
    ("stratified", "incumbent", "ASSIGNMENT in POINT space — the point-space control"),
)

#: every arm the harness scores. There is no separate matched FOIL here: NF-INJ2's foil answered the
#: availability-channel question and is not re-run; this story's foils are DECLARED MEMBERS of the
#: 2×2 (`points_rate_permute`, `points_rate_stratified`), so they pay full multiplicity.
ALL_ARMS: tuple[str, ...] = ARMS

RANDOM_ORDER_SEED = _RP.RANDOM_ORDER_SEED
STRATIFIED_N_STRATA = _RP.STRATIFIED_N_STRATA
GAMES_FLOOR = _RP.GAMES_FLOOR

#: the in-fold re-selection's candidate set — the SAME four-variant family NF1.5's own stage-1
#: searched. ⛔ No expansion: a wider class set would be a new search with its own deflation cost,
#: and the pre-registration puts hyperparameter re-tuning explicitly out of scope.
RESELECT_CANDIDATES: tuple[str, ...] = (
    "pos_learned_adaptive_blend", "pos_learned_blend", "pos_adaptive_blend", "pos_blend_flat",
)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The kernel — the ONE rule this story adds, everything else delegated
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _rate_within_strata(*, base: np.ndarray, gsafe: np.ndarray, score: np.ndarray,
                        pos: np.ndarray, elig: np.ndarray,
                        learn_positions: Sequence[str], target: np.ndarray) -> np.ndarray:
    """Permute the per-game RATE multiset WITHIN availability strata, × the row's own games.

    Coherent by the same construction as `rate_permute` — `games_i` never leaves row `i`, so the
    served pair (line, games) is a real player's per-game rate at a real player's own availability.
    What the stratification adds is a bound on the MULTIPLY: a rate is exchanged only between rows of
    comparable expected games, so the `× games` step can no longer re-rank a tercile against another
    one. That is the channel NF-INJ2's §6b decomposition indicts — the ordering damage tracked the
    games signal's per-position deficit, not the score's.

    Strata are `proj_games` TERCILES within each position, taken on that position's ELIGIBLE rows —
    the identical construction `nf_inj2_rate_permutation`'s `stratified` uses in POINT space, so the
    two are a matched pair differing only in which multiset is permuted (⛔ not in how the strata are
    cut). `duplicates="drop"` degrades to fewer strata on a degenerate games distribution rather than
    raising, and a stratum of one is left EXACTLY at its MVP-1 point (a permutation of one row is the
    identity, and guessing at it would be a level change this arm does not claim)."""
    for p in learn_positions:
        idx = np.where((pos == p) & elig)[0]
        if len(idx) < 2:
            continue
        try:
            strata = pd.qcut(gsafe[idx], STRATIFIED_N_STRATA, labels=False, duplicates="drop")
        except (ValueError, IndexError):
            strata = np.zeros(len(idx), dtype=int)
        strata = np.asarray(pd.Series(strata).fillna(-1), dtype=int)
        for k in np.unique(strata):
            sub = idx[strata == k]
            if len(sub) < 2:
                continue
            rate_desc = np.sort(base[sub] / gsafe[sub])[::-1]
            order = _RP._order(score, sub)          # the incumbent's own tie-break, shared
            target[order] = rate_desc * gsafe[order]
    return target


def assign_targets(*, base, games, score, positions, eligible, arm: str,
                   learn_positions: Sequence[str], line: pd.DataFrame | None = None,
                   seed: int = RANDOM_ORDER_SEED,
                   rescale_lo: float = 0.30, rescale_hi: float = 3.5) -> np.ndarray:
    """The target season point each row is re-levelled to, under `arm`.

    Signature-compatible with `nf_inj2_rate_permutation.assign_targets`, and every rule NF-INJ2
    already owns is DELEGATED to it — so `incumbent` here and `incumbent` there are the same code,
    and an arm cannot win on a quietly different tie-break or clamp.

    ⛔ An unrecognised `arm` RAISES rather than falling through to the incumbent: a typo that
    silently scores the incumbent under another arm's name is the failure mode that would make the
    whole bake-off vacuous."""
    if arm in _RP.ALL_ARMS and arm not in ARMS:
        # an NF-INJ2 arm name (e.g. `rate_permute`, `rate_permute_games_frozen`) — NF-INJ2's runner
        # and any existing caller keep working unchanged.
        return _RP.assign_targets(
            base=base, games=games, score=score, positions=positions, eligible=eligible, arm=arm,
            learn_positions=learn_positions, line=line, seed=seed,
            rescale_lo=rescale_lo, rescale_hi=rescale_hi)
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r} — the declared field is {ARMS}")

    rule = ASSIGNMENT_OF[arm]
    if rule != "rate_within_strata":
        return _RP.assign_targets(
            base=base, games=games, score=score, positions=positions, eligible=eligible,
            arm=_DELEGATE_TO_NF_INJ2[rule], learn_positions=learn_positions, line=line, seed=seed,
            rescale_lo=rescale_lo, rescale_hi=rescale_hi)

    b = np.asarray(base, dtype=float)
    g = pd.to_numeric(pd.Series(games).reset_index(drop=True), errors="coerce").to_numpy(dtype=float)
    s = np.asarray(score, dtype=float)
    pos = np.array([str(p or "").upper() for p in pd.Series(positions).reset_index(drop=True)],
                   dtype=object)
    elig = np.asarray(eligible, dtype=bool)
    gsafe = np.where(np.isfinite(g) & (g > GAMES_FLOOR), g, GAMES_FLOOR)
    return _rate_within_strata(base=b, gsafe=gsafe, score=s, pos=pos, elig=elig,
                               learn_positions=learn_positions, target=b.copy())


def feasible_hi(*, arm: str, line: pd.DataFrame | None, positions, games,
                rescale_hi: float = 3.5) -> np.ndarray | float:
    """The per-row upper rescale bound for `arm` — delegated, so no arm gets a quietly different
    clamp. Only `feasibility_clamp` narrows it."""
    delegate = (arm if arm in _RP.ALL_ARMS and arm not in ARMS
                else _DELEGATE_TO_NF_INJ2.get(ASSIGNMENT_OF.get(arm, ""), "incumbent"))
    return _RP.feasible_hi(arm=delegate, line=line, positions=positions, games=games,
                           rescale_hi=rescale_hi)


def games_floor_binding(games) -> int:
    """How many rows the `GAMES_FLOOR` guard actually moved — a MEASUREMENT on this population, not
    a claim inherited from a docstring."""
    return _RP.games_floor_binding(games)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# SERVING POLICY — ONE owner, deploy-held until the PM records a disposition
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: which arm the SHIPPED board serves, as named by THIS story. `None` = "this story names nothing;
#: defer to NF-INJ2's policy", which is the state a deploy-held §0.5 story ships in.
SERVED_ARM: str | None = None

#: the §0.5 outcome. One of "UNRUN" | "CLEARED" | "CONSTRAINT_REFUSED" | "NULL" | "DEFLATION_REFUSED"
#: | "GENUINE_ABSENCE", read by `assert_coherent`.
#:
#: ⭐ PINNED TO THE COMMITTED REPORT, not maintained by hand — NF-INJ2's own module shipped as
#: "UNRUN" after its decisive run had landed and been refused, i.e. the policy module claimed the
#: study had never run. `test_nf_inj2b_*::test_the_recorded_gate_status_matches_the_committed_report`
#: fails if this and `ablation_results/nf_inj2b_rate_ordering.json`'s verdict disagree, so a re-run
#: that changes the verdict must change this in the SAME commit.
GATE_STATUS = "UNRUN"

#: whether a PM has recorded a disposition to serve a non-incumbent arm. Kept SEPARATE from
#: `GATE_STATUS` because clearing the gates and deciding to ship are different facts — NF-D21 and
#: NF-D22 were both burned by a record in which they had been collapsed into one flag.
PM_DISPOSITION_RECORDED = False


def resolve_served_arm() -> str:
    """⭐ THE SINGLE AUTHORITY for which arm the board serves.

    `nf1_model.apply_learned_ordering` asks this and nothing else, so there is exactly one place
    that decides — the cure for the "one logical thing, two execution owners" class (INC-30 crontab,
    INC-36 deploy, INC-38 month-boundary flags). NF-INJ2b's own `SERVED_ARM` wins when it names one;
    otherwise NF-INJ2's policy stands."""
    return _RP.SERVED_ARM if SERVED_ARM is None else str(SERVED_ARM)


def assert_coherent() -> None:
    """Refuse a policy state the record does not support, and PROVE the registration's own claims.

    Runs at IMPORT, so a bare flag flip that would serve an uncleared arm fails the process that
    flipped it rather than shipping (NF-D22's governance shape)."""
    # ── the declared field is internally consistent ────────────────────────────────────────────
    if set(SCORE_OF) != set(ARMS) or set(ASSIGNMENT_OF) != set(ARMS):
        raise RuntimeError("SCORE_OF / ASSIGNMENT_OF must cover exactly the declared field")
    if DECLARED_FIELD_SIZE != len(set(ARMS)):
        raise RuntimeError("the declared field contains a duplicate arm")
    for rule in set(ASSIGNMENT_OF.values()) - {"rate_within_strata"}:
        if rule not in _DELEGATE_TO_NF_INJ2:
            raise RuntimeError(f"assignment rule {rule!r} has no delegate — it would silently fall "
                               f"through to another arm's kernel")
    # ── ⭐ the MATCHED PAIRS are matched IN FACT, not in a comment (the NF-D17 lesson: a guard on a
    #    conjunction is vacuous unless its fixture isolates the clause). A TARGET pair must share its
    #    assignment rule and differ in its score; an ASSIGNMENT pair the reverse.
    for a, b, why in MATCHED_PAIRS:
        if a not in ARMS or b not in ARMS:
            raise RuntimeError(f"matched pair ({a}, {b}) names an arm outside the declared field")
        same_rule = ASSIGNMENT_OF[a] == ASSIGNMENT_OF[b]
        same_score = SCORE_OF[a] == SCORE_OF[b]
        if same_rule == same_score:
            raise RuntimeError(
                f"matched pair ({a}, {b}) — {why!r} — differs on BOTH factors or on NEITHER "
                f"(assignment {ASSIGNMENT_OF[a]!r} vs {ASSIGNMENT_OF[b]!r}; score {SCORE_OF[a]!r} "
                f"vs {SCORE_OF[b]!r}). A pair that moves two things at once attributes nothing.")
    if set(DEGENERATE_ARMS) & set(REFERENCE_ARMS):
        raise RuntimeError("an arm cannot be both a degenerate and the reference")
    # ── the serving policy ────────────────────────────────────────────────────────────────────
    served = resolve_served_arm()
    if served not in ALL_ARMS and served not in _RP.ALL_ARMS:
        raise RuntimeError(f"served arm {served!r} is not a declared arm of either registration")
    if served in DEGENERATE_ARMS:
        raise RuntimeError(f"served arm {served!r} is a pre-registered DEGENERATE — it exists to LOSE")
    if SERVED_ARM is not None and _RP.SERVED_ARM != _RP.INCUMBENT_ARM:
        raise RuntimeError(
            f"BOTH registrations name a non-incumbent served arm (NF-INJ2b {SERVED_ARM!r}, "
            f"NF-INJ2 {_RP.SERVED_ARM!r}) — one logical thing, two owners (INC-30/36/38)")
    if served != INCUMBENT_ARM and SERVED_ARM is not None:
        if GATE_STATUS != "CLEARED":
            raise RuntimeError(
                f"SERVED_ARM {SERVED_ARM!r} but GATE_STATUS={GATE_STATUS!r} — an arm may only be "
                "served once its §0.5 gates CLEARED (nf_inj2b_preregistration.md §3/§6)")
        if not PM_DISPOSITION_RECORDED:
            raise RuntimeError(
                f"SERVED_ARM {SERVED_ARM!r} but no PM disposition is recorded — clearing the gates "
                "and deciding to ship are different facts")


assert_coherent()
