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
  * **Which kind of null is this?** `classify_null` — EIGHT states, because "trustworthy dead" and
    "underpowered" do not exhaust the possibilities.
  * **Is "get a lower-variance design" a lever at all?** `lockstep_variance_lever` — computed, not
    prescribed (PLAT-CVP1 defect 3 / NF-W8-0d R2).
  * **Would these gates pass a REAL effect?** `injected_effect_positive_control` — the standing
    recipe, executable (PLAT-CVP1 defect 4 / MLB-HV2-1), and it distinguishes a family that is BLIND
    from one stopped by its DEFLATION half or by a DETERMINISTIC CONSTRAINT (PLAT-CVP2 defects 1-2).
  * **Could this gate set be passed at all?** `validate_sign_certifiability` — a sign floor above its
    own BH cutoff is unpassable by an effect of any size (PLAT-CVP2 defect 3 / E7.14).

⭐⭐ **PLAT-CVP1 (2026-08-25) — FOUR MEASURED DEFECTS FIXED AT THE SOURCE, AND THE INTERIM
HAND-RECORD RULE RETIRES FOR FUTURE CALLERS.** Four studies each found a defect in this instrument,
each did the right local thing (fix at the CALL SITE, preserve the instrument's raw output beside it,
and file the gap), and each said the same thing about where the fix belonged — MH2.7's own lesson (i):
**a defect corrected N times downstream is a defect in the INSTRUMENT.** The four, with what they
measured:

  1. **NCAAF-VAL1** (`ncaaf_val1_clv_week_strat.md` §8a + `.json`) — `GENUINE_ABSENCE` short-circuited
     ahead of every power reading, so **5 of 6 buckets** were mislabelled "do NOT re-test", including
     the one bucket whose interval still ADMITTED the pre-registered meaningful effect. ⇒ when a
     meaningful bar is on record, `classify_null` now consults the INTERVAL first.
  2. **NCAAF-VAL3** (`ncaaf_val3_cold_start_mu.md` §3) — the classifier took **no PBO argument at
     all**, so it could express PBO-UNDEFINED but not PBO-EVALUATED-AND-FAILED, and returned
     `POWER_LIMITED` while the real refusal was the PBO gate. ⇒ a `pbo` input and a
     `DEFLATION_REFUSED` state, with the "more seasons" trigger SUPPRESSED.
  3. **NF-W8-0d R2** (`nf_w8_0d_dsr_frontier.md` §1) — the `DSR_UNREACHABLE` remedy named "a
     lower-variance design" verbatim, a lever the **lockstep invariant** makes deterministically void
     when `SR ≤ SR0`; that one sentence sent NF-W7f, NF-W7j and NF-W8-0c at the same wall. ⇒ the
     lockstep is now COMPUTED (`lockstep_variance_lever`) rather than prescribed around.
  4. **MLB-HV2-1** (`ablation_results/mlb_hv2_1_market_bias.md` §5c) — with a **6pp bias INJECTED**,
     every metric gate fired and a **field-level PBO applied as a per-arm gate** (0.426) vetoed the
     planted effect, because a uniform edge makes the arms near-clones and a high PBO over near-clones
     is a TIE (NF1.8), while the same edge inflates `V` and collapses DSR (MH2.5 / NF-W6b-C). ⇒ the
     application is now distinguished and the misapplication REFUSED, and the standing recipe is a
     CALLABLE (`injected_effect_positive_control`) instead of a paragraph.

⛔ **HISTORY IS UNTOUCHED.** Those four records are the FIXTURES that prove the new behaviour; not one
of them is edited, restated or "upgraded", and no recorded verdict is recomputed. The interim rule
those studies followed — hand-record the corrected state beside the instrument's raw one — retires for
**FUTURE callers only**: a caller that supplies the new inputs gets the corrected state from the
instrument, and a caller that does not is unchanged, by construction (every new input defaults to
`None` and every existing branch is byte-identical without them).

⭐⭐ **PLAT-CVP2 (2026-09-03) — FOUR MORE, AND TWO OF THEM ARE VERDICT INVERSIONS.** The same MH2.7
rule, a second pass. An inversion outranks a merely wrong verdict, because a wrong verdict is argued
with and an inverted one is believed:

  1. **NF-INJ2b D2** (PR #1051) — arms blocked SOLELY by a gate the injection structurally CANNOT
     move were reported `BLIND` ("a null from this family is free"), the opposite of the truth; the
     record had to carry a render-time "⛔ do not read that badge at face value". ⇒ a FORWARD-DECLARED
     `invariant_gates=` set and a `CONSTRAINT_BLOCKED` verdict; `BLIND` keeps its meaning for MOVABLE
     gates only.
  2. **MLB-TV2-2 finding 7** (`mlb_tv2_2_mixture_head.md` §17) — the control partitions gates into
     deflation-class and metric BY NAME, so a caller whose clause names share ZERO overlap with the
     default vocabulary had its deflation gate filed as a METRIC gate and got `BLIND` when the truth
     was `DEFLATION_BLOCKED`. Found by hand. ⇒ a zero-overlap partition reports `UNVERIFIED` and
     names the input that fixes it; `gate_classes=` is the durable half, and the name heuristic
     survives only as a fallback that ANNOUNCES ITSELF.
  3. **MLB-TV2-2 finding 2 / E7.14** (prereg §14.1) — at 5 folds a sign floor of `2⁻⁵ = 0.03125` sat
     ABOVE a 4-arm BH cutoff of 0.0125, so the multiplicity clause was structurally unpassable by an
     effect of ANY size. `sign_test_floor` and `folds_for_sign_certifiability` had said so since MH2
     and nothing had to ask them. ⇒ `validate_sign_certifiability` REFUSES such a gate set at
     registration time, with the arithmetic in the message.
  4. **NF-INJ2c §6.3** — a floor census and the kernel that applies the floor read DIFFERENT
     predicates, so a non-finite row the kernel floors was invisible to the census. ⇒ fixed at its
     own owner, `nf_inj2_rate_permutation.games_floored_mask`: one predicate, both readers.

The retirement note, with all four citations, lives on `injected_effect_positive_control` — the
callable a future study meets. ⛔ Same contract as PLAT-CVP1: those four records are the FIXTURES,
they are not edited, and no recorded verdict is recomputed or upgraded.

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
from typing import Iterable, Mapping, Sequence

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

#: The program's CSCV/PBO gate (`h_harness.MAX_PBO`, and the same 0.20 every §0.5 harness registers).
#: Mirrored here so `classify_null` can be handed a PBO and read it against the bar the callers use;
#: a caller with a different pre-registered bar passes `pbo_gate=` explicitly.
MAX_PBO = 0.20

#: ⭐ PLAT-CVP1 defect 4 — HOW a PBO was APPLIED, which is a different fact from what it measured.
#: CSCV/PBO is a **FIELD-LEVEL** statistic: it answers "did the SELECTION overfit?" over the whole
#: declared field, and it has exactly one value per field. Applying that single number as a PER-ARM
#: pass/fail gate is a category error, and MLB-HV2-1 MEASURED what it costs — see
#: `_PBO_PER_ARM_MISAPPLICATION`.
PBO_APPLICATIONS = ("field", "per_arm")

#: Gate names that deflate the SEARCH rather than scoring one arm's own evidence. The split is the
#: whole point of defect 4: `bh_fdr` and a fold-consistency clause are statistics of the ARM's OWN
#: evidence (they answer "is this arm's margin real?"), while PBO and DSR answer "did picking a
#: winner out of THIS FIELD overfit?" — a question about the search, whose answer moves with the
#: field's composition and correlation structure rather than with the effect. A caller whose harness
#: names these differently passes `deflation_gates=`.
DEFLATION_CLASS_GATES = frozenset({"pbo", "cscv", "dsr", "deflated_sharpe"})

#: Of those, the ones that are ONE NUMBER PER FIELD. A field-level statistic can legitimately refuse
#: a SEARCH; it cannot legitimately refuse an individual ARM, because it does not vary across arms —
#: reading it per-arm converts "the selection was unstable" into "this arm failed", which is not a
#: statement the statistic makes. (`dsr` is deliberately NOT here: DSR is per-arm — each arm has its
#: own Sharpe — even though its BENCHMARK is field-derived.)
_FIELD_LEVEL_STATISTICS = frozenset({"pbo", "cscv"})


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


@dataclass(frozen=True)
class SignCertifiability:
    n_folds: int
    bh_cutoff: float
    sign_floor: float
    certifiable: bool
    folds_needed: int
    headroom: float          #: floor / cutoff — < 1 is certifiable, <= 0.5 leaves real margin
    reason: str


def validate_sign_certifiability(
        *, n_folds: int, bh_cutoff: float | None = None, n_arms: int | None = None,
        alpha: float = BH_ALPHA, two_sided: bool = False,
        strict: bool = True) -> SignCertifiability:
    """⭐ **PLAT-CVP2 DEFECT 3 — REFUSE A GATE SET NO EFFECT OF ANY SIZE COULD PASS, AT REGISTRATION
    TIME.**

    A fold-sign test over `n` folds has a minimum attainable one-sided p of `2⁻ⁿ`. If that floor sits
    ABOVE the BH cutoff the family must clear, the multiplicity clause is **structurally unpassable**
    — a unanimous sweep of a gigantic effect still misses the bar — and the resulting null is a
    statement about the DESIGN, not about the mechanism (E7.14 verbatim).

    `sign_test_floor` and `folds_for_sign_certifiability` have existed since MH2 and **nothing had
    to consult them**, which is the defect: MLB-TV2-2 registered `N_BLOCKS = 5` against a 4-arm BH
    cutoff of 0.0125 — floor `2⁻⁵ = 0.03125`, **2.5× the cutoff** — and its C8 clause was unpassable.
    It was caught by a vacuity control, by hand, after registration (prereg §14.1). This is the same
    self-safe move MH2.7 made for `declared_field_size`: the instrument REFUSES, with the arithmetic
    in the message, rather than letting a caller compute a null it could never have avoided.

    Pass the cutoff you registered, or `n_arms` to derive the rank-1 BH cutoff `alpha / n_arms`.
    `strict=False` returns the report instead of raising — for a caller INSPECTING a design (e.g.
    choosing `n_folds`), never for one about to score with it.
    """
    n = int(n_folds)
    if bh_cutoff is None and n_arms is None:
        raise ValueError(
            "`validate_sign_certifiability` needs the bar it is checking against: pass "
            "`bh_cutoff=` (the cutoff you registered) or `n_arms=` (⇒ rank-1 cutoff alpha/n_arms). "
            "Defaulting one would be the instrument choosing a caller's registration for it.")
    cut = float(alpha) / max(int(n_arms), 1) if bh_cutoff is None else float(bh_cutoff)
    floor = sign_test_floor(n, two_sided=two_sided)
    need = folds_for_sign_certifiability(cut, two_sided=two_sided)
    ok = bool(floor <= cut)
    side = "two-sided" if two_sided else "one-sided"
    arith = (f"at {n} folds the {side} fold-sign floor is 2^-{n}"
             + (" x 2" if two_sided else "") + f" = {floor:.5f}, against a BH cutoff of "
             f"{cut:.5f}" + (f" (alpha {alpha:g} / {int(n_arms)} arms)" if bh_cutoff is None else "")
             + f" — a ratio of {floor / cut:.2f}x")
    if ok:
        why = (f"CERTIFIABLE: {arith}. A unanimous sweep clears the cutoff"
               + ("" if floor <= 0.5 * cut else
                  f" — but with NO MARGIN (the floor is {floor / cut:.2f} of the cutoff, so a "
                  f"borderline p cannot clear); {folds_for_sign_certifiability(0.5 * cut, two_sided)}"
                  f" folds would put it at or below half (MLB-TV2-2's forward-stated rule)."))
    else:
        why = (f"REFUSED: {arith}, so NO EFFECT OF ANY SIZE could pass this multiplicity clause — "
               f"a unanimous {n}-of-{n} sweep still misses the bar. This is a statement about the "
               f"DESIGN, not about the mechanism (E7.14; MLB-TV2-2 prereg §14.1 hit it at exactly "
               f"{n} folds / cutoff {cut:g}). {need} folds is the smallest certifiable design "
               f"(floor {sign_test_floor(need, two_sided):.5f}); "
               f"{folds_for_sign_certifiability(0.5 * cut, two_sided)} puts the floor at or below "
               f"HALF the cutoff, which is the margin rule MLB-TV2-2 stated forward. Fix the "
               f"DESIGN before scoring — a null computed here would be unavoidable, not evidence.")
    rep = SignCertifiability(n_folds=n, bh_cutoff=cut, sign_floor=floor, certifiable=ok,
                             folds_needed=need, headroom=(floor / cut if cut > 0 else float("inf")),
                             reason=why)
    if strict and not ok:
        raise ValueError(why)
    return rep


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
# 4b. ⭐ PLAT-CVP1 defect 3 — THE LOCKSTEP CHECK, COMPUTED RATHER THAN PRESCRIBED AROUND
# ══════════════════════════════════════════════════════════════════════════════════════════════════

#: The dispersion multipliers NF-W8-0d ran its ladder over. A DESIGN quantity — the ladder exists to
#: make the invariance VISIBLE across four orders of magnitude, not to be tuned to a result.
LOCKSTEP_DISPERSION_FACTORS = (1.0, 0.5, 0.25, 0.1, 0.01)


@dataclass(frozen=True)
class LockstepReport:
    """What a SHARED (proportional) variance lever can and cannot do to a DSR gate.

    `closed is True` ⇒ `SR ≤ SR0`, so no shared variance lever of any magnitude clears the gate and
    a sharper design makes DSR strictly WORSE. `closed is False` ⇒ `SR > SR0`, the gap is positive
    and a proportional sharpening scales it up, so the lever IS live. `closed is None` ⇒ not
    evaluable (NF1.7 (a): a check that did not run is never scored as a pass).
    """
    closed: bool | None
    sr: float | None = None
    sr0: float | None = None
    gap: float | None = None
    sign_invariant: bool | None = None
    dsr_falls_as_design_sharpens: bool | None = None
    ladder: tuple[dict, ...] = ()


def lockstep_variance_lever(*, observed_sr: float | None, n_trials: int,
                            var_trials_sr: float | None, n_obs: int,
                            skew: float = 0.0, kurt: float = 3.0,
                            confidence: float = DSR_CONFIDENCE,
                            dispersion_factors: Sequence[float] = LOCKSTEP_DISPERSION_FACTORS,
                            ) -> LockstepReport:
    """⭐⭐ **IS "GET A LOWER-VARIANCE DESIGN" A LEVER HERE? COMPUTE IT — DO NOT PRESCRIBE IT.**

    `deflated_sharpe` reads the winner's Sharpe `SR` **and** the deflation benchmark
    `SR0 = √V · z(N)` — and **the winner is one of the trials whose dispersion `V` measures**
    (NF-W7k). A design change that multiplies EVERY arm's per-fold dispersion by a common `c` scales
    every trial Sharpe by `1/c`, hence `SR0` by `1/c`, hence

        `SR − SR0  ↦  (SR − SR0)/c`  — **its SIGN is invariant.**

    Clearing needs `SR > SR0`. So a purely proportional dispersion lever — more rows per fold, more
    Monte-Carlo draws, a proportionally sharper estimator — **can never flip an `SR ≤ SR0` refusal,
    at any row count, fold count or draw count**, and when the gap is negative a *sharper* design
    makes DSR strictly WORSE. Under common random numbers (the generic case: the arms score the same
    rows with the same draws) a variance reduction IS shared, so this is the ordinary situation.

    ⚠️ **WHY THIS IS COMPUTED AND NOT ASSERTED.** `classify_null`'s `DSR_UNREACHABLE` remedy named
    "a lower-variance design (more rows per fold / a sharper metric)" verbatim, and that one sentence
    sent **three consecutive records** (NF-W7f, NF-W7j, NF-W8-0c) at a wall before NF-W8-0d measured
    the ladder and filed R2. The remedy was not wrong about its own axis — it is a prescription the
    instrument was not checking, which is MH2.7's lesson (i) exactly: a defect corrected N times
    downstream is a defect in the INSTRUMENT.

    What is NOT closed by a closed lockstep, stated so the finding is not over-read: a
    **DIFFERENTIAL**-variance design (one that shrinks the WINNER's dispersion more than the field's)
    is untested, not refuted; so are a bigger effect and a genuine absence.

    Returns a `LockstepReport`. The ladder re-derives `SR`, `SR0`, the gap and DSR at each dispersion
    multiplier, so the invariance is exhibited numerically rather than argued from the algebra.
    """
    if observed_sr is None or var_trials_sr is None or int(n_trials) < 1:
        return LockstepReport(closed=None)
    sr = float(observed_sr)
    sr0 = dsr_benchmark_sr0(int(n_trials), float(var_trials_sr))
    gap = sr - sr0
    ladder: list[dict] = []
    for c in dispersion_factors:
        c = float(c)
        if c <= 0:
            continue
        # every trial Sharpe scales by 1/c ⇒ their VARIANCE scales by 1/c²
        row_sr, row_v = sr / c, float(var_trials_sr) / (c * c)
        row_sr0 = dsr_benchmark_sr0(int(n_trials), row_v)
        ladder.append({
            "dispersion_factor": c,
            "winner_sharpe": row_sr,
            "sr0": row_sr0,
            "sr_minus_sr0": row_sr - row_sr0,
            "dsr": dsr_from_sr(row_sr, n_obs=int(n_obs), n_trials=int(n_trials),
                               var_trials_sr=row_v, skew=skew, kurt=kurt),
        })
    signs = {int(np.sign(r["sr_minus_sr0"])) for r in ladder}
    dsrs = [r["dsr"] for r in ladder]
    return LockstepReport(
        closed=bool(gap <= 0.0),
        sr=sr, sr0=sr0, gap=gap,
        sign_invariant=(len(signs) <= 1),
        # ⭐ the two-sided half: when the gap is NEGATIVE a sharper design must make DSR FALL, and
        # when it is POSITIVE it must RISE. Reporting only the "falls" case would make the check
        # satisfiable by a constant.
        dsr_falls_as_design_sharpens=(all(b <= a for a, b in zip(dsrs, dsrs[1:]))
                                      if len(dsrs) > 1 else None),
        ladder=tuple(ladder),
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4c. ⭐ PLAT-CVP1 defect 4b — THE INJECTED-EFFECT POSITIVE CONTROL, AS A CALLABLE
# ══════════════════════════════════════════════════════════════════════════════════════════════════

#: The verdicts an injected-effect control can return, IN PRECEDENCE ORDER. `VACUOUS` is first in
#: importance: a gate family that certifies arms on a NO-EFFECT payload cannot certify anything on a
#: real one. ⭐ PLAT-CVP2 added two: `UNVERIFIED` (the partition could not be established, so no
#: partition-dependent verdict is admissible — MH2.7's self-safe move) and `CONSTRAINT_BLOCKED` (an
#: arm cleared everything the injection could move and was stopped by a gate it structurally cannot
#: — NF-D18's `CONSTRAINT_REFUSED`, one level up, inside a positive control).
POSITIVE_CONTROL_VERDICTS = ("VACUOUS", "UNVERIFIED", "DETECTED", "CONSTRAINT_BLOCKED",
                             "DEFLATION_BLOCKED", "BLIND")

#: ⭐ PLAT-CVP2 defects 1 + 2 — the THREE classes a registered gate can be in, because two do not
#: cover the cases. `metric` reads the ARM's own evidence and MUST fire on a planted effect;
#: `deflation` deflates the SEARCH and may legitimately block a correlated field (MH2.5 / NF1.8);
#: `invariant` is a gate the injection structurally CANNOT move — a deterministic constraint, whose
#: failure is a fact about the constraint and never about the family's sensitivity. Filing an
#: invariant gate as a metric gate is what made NF-INJ2b read `BLIND` ("a null from this family is
#: free") for a family whose every movable gate fired.
GATE_CLASSES = ("metric", "deflation", "invariant")

#: How the gate partition was established, recorded on every report so a reader never has to guess.
#: `name_heuristic` is the LEGACY fallback and it ANNOUNCES ITSELF (PLAT-CVP2 defect 2): it is the
#: mode in which a zero-overlap partition silently inverted TV2-2's verdict.
GATE_PARTITION_SOURCES = ("gate_classes", "declared_vocabulary", "name_heuristic")
#: unpacked rather than re-typed at each site, so the constant and the strings the report carries
#: CANNOT drift apart — a `*_SOURCES` constant nothing reads is the E11.29 dead-config shape, and
#: two copies of the same vocabulary is the E9.61 two-renderers shape. This is neither.
_SRC_GATE_CLASSES, _SRC_DECLARED_VOCAB, _SRC_NAME_HEURISTIC = GATE_PARTITION_SOURCES


@dataclass(frozen=True)
class PositiveControlReport:
    verdict: str
    effect: float
    survivors: tuple[str, ...] = ()
    metric_survivors: tuple[str, ...] = ()
    deflation_blocked: tuple[str, ...] = ()
    blocking_gates: dict = field(default_factory=dict)
    deflation_gates: tuple[str, ...] = ()
    metric_gates: tuple[str, ...] = ()
    #: gate names present on EVERY arm that are field-level statistics — i.e. one number per FIELD
    #: being read as a per-ARM pass/fail. Defect 4(a), detected rather than asserted.
    field_level_gates_applied_per_arm: tuple[str, ...] = ()
    null_control_checked: bool = False
    null_control_survivors: tuple[str, ...] | None = None
    #: ⭐ PLAT-CVP2 defect 1 — gates DECLARED FORWARD as ones the injection structurally cannot move,
    #: and the arms stopped by those ALONE. An arm here cleared every movable gate, metric AND
    #: deflation; reading it as `BLIND` is the inversion NF-INJ2b had to annotate around by hand.
    invariant_gates: tuple[str, ...] = ()
    constraint_blocked: tuple[str, ...] = ()
    #: ⭐ PLAT-CVP2 defect 2 — HOW the partition was established, and whether it could be
    #: established at all. `partition_verified is False` means no partition-dependent verdict was
    #: admissible; the verdict is then `UNVERIFIED` unless a partition-FREE one applied.
    partition_source: str = "name_heuristic"
    partition_verified: bool = True
    gate_classes_resolved: dict = field(default_factory=dict)
    reason: str = ""


def _partition_gates(
        gate_names: Sequence[str], *,
        gate_classes: Mapping[str, str] | None,
        deflation_gates: Iterable[str],
        invariant_gates: Iterable[str] | None,
        vocabulary_declared: bool) -> tuple[dict[str, str], str, bool]:
    """Resolve every observed gate name to one of `GATE_CLASSES`. Returns `(classes, source, ok)`.

    ⭐ **PLAT-CVP2 DEFECT 2 — THE ZERO-INTERSECTION INVERSION, REFUSED RATHER THAN GUESSED.**
    The legacy partition is BY NAME against `DEFLATION_CLASS_GATES`. That vocabulary is a fact about
    what *this repo's harnesses happen to call things*, not about what a caller's clauses measure —
    so a study whose deflation clause is named `C7_deflation` gets ZERO overlap, its deflation gate
    filed as a METRIC gate, and the verdict INVERTED: `DEFLATION_BLOCKED` ("the metric half fires;
    the deflation half stops it") silently becomes `BLIND` ("a null from this family is free").
    MLB-TV2-2 was told exactly that, and the inversion was found by hand.

    ⛔ The two states a zero-overlap partition cannot tell apart are "this family has no deflation
    gate" and "this family's deflation gate is named something else" — so it must not pick one
    (NF1.7 (a); MH2.7's `declared_field_size` refusal, one instrument over). `ok=False` is returned
    and the caller withholds every partition-DEPENDENT verdict.

    The DURABLE half of the fix is `gate_classes`: an explicit per-gate declaration, which is the
    only input that can affirm "there is no deflation gate here". It must cover EVERY observed gate
    — a partially-declared partition reintroduces exactly the ambiguity being refused."""
    names = [str(g) for g in gate_names]
    if gate_classes is not None:
        declared = {str(k): str(v) for k, v in dict(gate_classes).items()}
        bad = sorted({v for v in declared.values()} - set(GATE_CLASSES))
        if bad:
            raise ValueError(
                f"`gate_classes` assigned unknown class(es) {bad} — every gate must be one of "
                f"{list(GATE_CLASSES)}.")
        missing = sorted(set(names) - set(declared))
        if missing:
            raise ValueError(
                f"`gate_classes` does not classify {missing} — a PARTIALLY declared partition "
                f"reintroduces the ambiguity it exists to remove (PLAT-CVP2 defect 2). Classify "
                f"every gate the study scores, or omit `gate_classes` entirely.")
        return {g: declared[g] for g in names}, _SRC_GATE_CLASSES, True

    defl = frozenset(str(g) for g in deflation_gates)
    inv = frozenset(str(g) for g in (invariant_gates or ()))
    overlap = bool(defl & set(names))
    source = _SRC_DECLARED_VOCAB if vocabulary_declared else _SRC_NAME_HEURISTIC
    classes = {g: ("invariant" if g in inv else "deflation" if g in defl else "metric")
               for g in names}
    # a vocabulary that names NOTHING in this study cannot have partitioned it. `gate_classes` is
    # the only affirmative way to say "no deflation gate exists here".
    return classes, source, overlap


def injected_effect_positive_control(
        *, inject, run_gates, effect: float,
        deflation_gates: Iterable[str] | None = None,
        gate_classes: Mapping[str, str] | None = None,
        invariant_gates: Iterable[str] | None = None,
        check_null_control: bool = True,
        null_effect: float = 0.0) -> PositiveControlReport:
    """⭐⭐ **"WHICH GATES SHOULD PASS A PLANTED EFFECT?" — EXECUTED, NOT NARRATED.**

    Plant an effect of KNOWN size into the study's own population, re-run the study's own registered
    gate family, and report which gates fired and which blocked. MLB-HV2-1 ran exactly this by hand
    and it produced the program's sharpest instrument finding: with a **6-percentage-point** dog bias
    injected, **no arm survived** — the METRIC gates all fired correctly (ROI up to +0.156, p as low
    as 1.4e-8) while **PBO rose to 0.426** (a uniform edge makes the arms simultaneously strong
    NEAR-CLONES, so "which arm is best in-sample" becomes a coin flip — NF1.8's lesson that a high
    PBO over a near-clone field is the signature of a TIE, not of overfitting) and **DSR collapsed**
    (the same uniform edge inflates the cross-trial dispersion `V`, so `SR0` outruns every arm's
    Sharpe — the MH2.5 / NF-W6b-C mechanism). That is a bound on what a SURVIVOR would have meant,
    and it is the difference between a gate family that is BLIND and one whose deflation half is
    hostile to a correlated field. Neither is visible from a leaderboard.

    Arguments
    ---------
    `inject(effect) -> payload` — build the study's population with an effect of that size planted.
      `inject(0.0)` MUST return the no-effect payload (that is the two-sided leg; a caller that
      cannot express it passes `check_null_control=False`, and the report then records that the leg
      did NOT run rather than scoring it as passed — NF1.7 (a)).
    `run_gates(payload) -> {arm_id: {gate_name: bool}}` — the study's OWN registered gates. It must
      be the gate function the study actually scores with; re-implementing it here would restate the
      harness's assumptions instead of testing them (the NF-C0e "a test that reads a value back
      under the key the code wrote" class).
    `gate_classes={gate: "metric"|"deflation"|"invariant"}` — ⭐ the DECLARED partition, and the
      durable half of PLAT-CVP2's defect-2 fix. It must classify EVERY gate the study scores. It is
      the ONLY input that can affirm "this family has no deflation gate"; without it a vocabulary
      that names nothing in the study is reported UNVERIFIED rather than guessed.
    `deflation_gates=` / `invariant_gates=` — the vocabulary form, for a caller that only needs to
      rename one class. `invariant_gates` is DECLARED FORWARD by the registration, which is what
      keeps it from laundering: a gate cannot be reclassified as injection-invariant after seeing
      that it blocked (E2.1-r).

    Verdicts (in precedence order)
    ------------------------------
    `VACUOUS`            an arm survives on the NO-EFFECT payload ⇒ the family certifies noise; no
                         reading of the injected run means anything. PARTITION-FREE.
    `UNVERIFIED`         the gate partition could not be established, so no partition-DEPENDENT
                         verdict is admissible. Declare `gate_classes=`.
    `DETECTED`           at least one arm clears EVERY gate ⇒ the family can certify an effect of
                         this size over this field. PARTITION-FREE.
    `CONSTRAINT_BLOCKED` at least one arm is stopped ONLY by DECLARED injection-invariant gates ⇒ it
                         cleared every gate the injection could move, metric AND deflation. The
                         blockage is a deterministic CONSTRAINT, not insensitivity.
    `DEFLATION_BLOCKED`  no arm clears everything, but at least one clears every movable METRIC gate
                         and is stopped by deflation-class gates ⇒ the family is NOT blind; its
                         deflation half cannot certify an effect of this size over THIS field.
    `BLIND`              not even the movable metric gates fire ⇒ a null from this family is free
                         (it would have returned one for a real, large effect), so it is evidence
                         about nothing.

    ⚠️ `VACUOUS` and `DETECTED` are returned even when the partition is UNVERIFIED, and that is a
    deliberate, MEASURED exemption rather than a hole: both are computed from EMPTY blocking sets
    alone and are provably invariant to every partition (pinned two-sided — see
    `test_the_partition_free_verdicts_are_invariant_to_any_partition`). Withholding "this family
    certifies noise" behind "I could not classify your gates" would suppress the control's single
    most important finding to protect against an inversion that cannot reach it.

    ⛔ **THE ANNOTATE-AROUND RULE RETIRES HERE, FOR FUTURE CALLERS ONLY.** Four incidents were each
    corrected by hand at the point of reading, which is a defect in the INSTRUMENT (MH2.7):
      1. **NF-INJ2b D2** (PR #1051) — `stratified` and `feasibility_clamp` blocked under injection by
         `coherence_restored` ALONE, every metric gate and `dsr` firing; the badge said `BLIND` and
         the report had to carry a render-time "⛔ do not read that badge at face value". Now
         `CONSTRAINT_BLOCKED` with `invariant_gates=("coherence_restored",)`.
      2. **MLB-TV2-2 finding 7** (`ablation_results/mlb_tv2_2_mixture_head.md` §17) — clause names
         with ZERO overlap against the default vocabulary filed `C7_deflation` as a METRIC gate and
         returned `BLIND` for a family whose metric gates fired on every arm. Now `UNVERIFIED`
         unless the partition is declared; TV2-2's own corrected call is byte-identical.
      3. **MLB-TV2-2 finding 2 / E7.14** (prereg §14.1) — a sign floor ABOVE its own BH cutoff makes
         a multiplicity clause structurally unpassable. Now refused at registration time by
         `validate_sign_certifiability`.
      4. **NF-INJ2c §6.3** — a floor census and the kernel that applies the floor read different
         predicates. Fixed at its own owner (`nf_inj2_rate_permutation.games_floored_mask`).
    ⛔ Their RECORDS are the fixtures that prove this behaviour and are NOT edited: every recorded
    verdict stands as the instrument returned it (E2.1-r — a result is annotated, never re-labelled).

    ⛔ This is a DIAGNOSTIC about a gate family. It certifies nothing, re-scores nothing, and it does
    not rescue or damage a study whose null rests on a gate the control leaves untouched — HV2-1's
    null rests on `roi_positive`, which is de-vig-free, PBO-free, DSR-free and field-free, so no
    deflation-gate finding can turn its negative point estimates positive.
    """
    if float(effect) == 0.0:
        raise ValueError(
            "an injected-effect control with a ZERO effect plants nothing — it is the null control, "
            "not the positive one. Pass a real effect size (and use `check_null_control` for the "
            "no-effect leg).")
    vocabulary_declared = deflation_gates is not None or invariant_gates is not None
    defl_vocab = DEFLATION_CLASS_GATES if deflation_gates is None else deflation_gates

    def _score(payload) -> dict[str, dict[str, bool]]:
        got = run_gates(payload)
        if not isinstance(got, dict) or not got:
            raise ValueError(
                "`run_gates` returned no arms — an empty gate table makes every clause below "
                "vacuously true (there are no survivors because there is nothing to survive).")
        out: dict[str, dict[str, bool]] = {}
        for arm, gates in got.items():
            if not isinstance(gates, dict) or not gates:
                raise ValueError(
                    f"`run_gates` returned no gates for arm {arm!r} — an arm with an empty gate "
                    f"dict passes 'every gate' trivially, which is the vacuity this control exists "
                    f"to refuse.")
            out[str(arm)] = {str(g): bool(ok) for g, ok in gates.items()}
        return out

    scored = _score(inject(float(effect)))
    gate_names = sorted({g for gates in scored.values() for g in gates})
    classes, partition_source, partition_ok = _partition_gates(
        gate_names, gate_classes=gate_classes, deflation_gates=defl_vocab,
        invariant_gates=invariant_gates, vocabulary_declared=vocabulary_declared)
    defl = frozenset(g for g, c in classes.items() if c == "deflation")
    inv = frozenset(g for g, c in classes.items() if c == "invariant")
    metric_names = tuple(g for g in gate_names if classes[g] == "metric")
    defl_names = tuple(g for g in gate_names if classes[g] == "deflation")
    inv_names = tuple(g for g in gate_names if classes[g] == "invariant")
    # defect 4(a), MEASURED: a field-level statistic carried as a per-arm pass/fail on every arm.
    per_arm_field_level = tuple(
        g for g in defl_names
        if g in _FIELD_LEVEL_STATISTICS and all(g in gates for gates in scored.values()))

    blocking = {arm: tuple(g for g, ok in gates.items() if not ok) for arm, gates in scored.items()}
    survivors = tuple(a for a, b in blocking.items() if not b)
    # ⭐ PLAT-CVP2 defect 1: an INVARIANT gate is neither a metric detector nor a deflation
    # statistic. "Cleared every metric gate" must mean every gate the injection could have MOVED, or
    # a constraint failure is charged to the family's sensitivity.
    metric_survivors = tuple(a for a, b in blocking.items() if not any(classes[g] == "metric"
                                                                      for g in b))
    constraint_blocked = tuple(a for a in metric_survivors
                               if blocking[a] and set(blocking[a]) <= inv)
    deflation_blocked = tuple(a for a in metric_survivors if any(g in defl for g in blocking[a]))

    null_survivors: tuple[str, ...] | None = None
    if check_null_control:
        null_scored = _score(inject(float(null_effect)))
        null_blocking = {a: [g for g, ok in gs.items() if not ok] for a, gs in null_scored.items()}
        null_survivors = tuple(a for a, b in null_blocking.items() if not b)

    if null_survivors:
        verdict, why = "VACUOUS", (
            f"{len(null_survivors)} arm(s) clear every gate on the NO-EFFECT payload "
            f"({', '.join(null_survivors)}) — the family certifies noise, so nothing the injected "
            f"run shows is evidence about anything.")
    elif survivors:
        verdict, why = "DETECTED", (
            f"{len(survivors)} arm(s) clear every registered gate at an injected effect of "
            f"{effect:g} — the family can certify an effect of this size over this field.")
    elif not partition_ok:
        # ⭐ PLAT-CVP2 defect 2 — the self-safe refusal. Everything below this line reads the
        # partition, and the partition could not be established, so NONE of it is admissible.
        verdict, why = "UNVERIFIED", (
            f"the gate partition could NOT be established: the deflation vocabulary "
            f"({', '.join(sorted(str(g) for g in defl_vocab)) or '—'}) names NOTHING among this "
            f"study's gates ({', '.join(gate_names)}). \"this family has no deflation gate\" and "
            f"\"its deflation gate is called something else\" are indistinguishable from here, and "
            f"they lead to OPPOSITE verdicts — BLIND (\"a null from this family is free\") versus "
            f"DEFLATION_BLOCKED (\"the metric gates all fire; the deflation half stops it\"). "
            f"MLB-TV2-2 was told BLIND on exactly this shape and the truth was DEFLATION_BLOCKED "
            f"(§17). ⇒ DECLARE the partition: pass "
            f"`gate_classes={{gate: \"metric\"|\"deflation\"|\"invariant\"}}` covering every gate "
            f"above. No partition-dependent verdict is returned here (NF1.7 (a): a check that "
            f"cannot discriminate has not passed).")
    elif constraint_blocked:
        _blockers = sorted({g for a in constraint_blocked for g in blocking[a]})
        verdict, why = "CONSTRAINT_BLOCKED", (
            f"no arm clears every gate, but {len(constraint_blocked)} "
            f"({', '.join(constraint_blocked)}) are stopped ONLY by gates DECLARED "
            f"injection-invariant (`{'`, `'.join(_blockers)}`) — they cleared every gate the "
            f"injection could move, METRIC and DEFLATION alike. The blockage is a DETERMINISTIC "
            f"CONSTRAINT, not statistical insensitivity: no injection of any size could clear it, "
            f"so this says nothing about the family's sensitivity in either direction. "
            f"⛔ NOT `BLIND` — that reads \"a null from this family is free\", and NF-INJ2b had to "
            f"annotate exactly this misreading out by hand (PR #1051 D2). NF-D18's "
            f"`CONSTRAINT_REFUSED`, one level up, inside a positive control.")
    elif deflation_blocked:
        verdict, why = "DEFLATION_BLOCKED", (
            f"no arm clears every gate, but {len(deflation_blocked)} clear every METRIC gate and "
            f"are stopped ONLY by deflation-class gates "
            f"({', '.join(sorted({g for a in deflation_blocked for g in blocking[a]}))}). The "
            f"family is NOT blind: its DEFLATION half cannot certify an effect of size {effect:g} "
            f"over THIS field. A uniform effect makes the arms simultaneously strong near-clones, "
            f"which is a TIE (high PBO) and an inflated cross-trial dispersion (collapsed DSR) — "
            f"MLB-HV2-1's measurement, NF1.8 / MH2.5's mechanisms. ⛔ This bounds what a SURVIVOR "
            f"would have meant; it does not by itself refuse any recorded null.")
    else:
        verdict, why = "BLIND", (
            f"not one arm clears even the MOVABLE METRIC gates at an injected effect of {effect:g} "
            f"— this family would return a null for a real, large effect, so a null from it is "
            f"free (NF1.7 (a): a check that cannot fire is not a check that passed)."
            + (f" ⚠️ {len(inv_names)} gate(s) are DECLARED injection-invariant "
               f"(`{'`, `'.join(inv_names)}`) and were excluded from that reading, so BLIND here "
               f"means the MOVABLE half genuinely failed to fire." if inv_names else ""))
    if partition_source == _SRC_NAME_HEURISTIC and partition_ok and verdict != "VACUOUS":
        # ⭐ PLAT-CVP2 defect 2 — the heuristic survives only as a fallback that ANNOUNCES ITSELF.
        why += (f" ⚠️ PARTITION BY NAME HEURISTIC: the deflation half was inferred from the default "
                f"vocabulary {sorted(DEFLATION_CLASS_GATES)} matching "
                f"`{'`, `'.join(defl_names)}`, NOT declared by this caller. That vocabulary is a "
                f"fact about this repo's harness names, not about what your clauses measure — "
                f"declare `gate_classes=` to make the partition part of the registration.")
    if per_arm_field_level:
        why += (f" ⚠️ AND: {', '.join(per_arm_field_level)} is a FIELD-LEVEL statistic carried as a "
                f"per-ARM pass/fail on every arm — see `classify_null(pbo_application=...)`.")

    return PositiveControlReport(
        verdict=verdict, effect=float(effect), survivors=survivors,
        metric_survivors=metric_survivors, deflation_blocked=deflation_blocked,
        blocking_gates={a: tuple(b) for a, b in blocking.items()},
        deflation_gates=defl_names, metric_gates=metric_names,
        field_level_gates_applied_per_arm=per_arm_field_level,
        null_control_checked=bool(check_null_control), null_control_survivors=null_survivors,
        invariant_gates=inv_names, constraint_blocked=constraint_blocked,
        partition_source=partition_source, partition_verified=bool(partition_ok),
        gate_classes_resolved=dict(classes),
        reason=why)


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
    "DEFLATION_REFUSED",  # a pre-registered deflation gate was EVALUATED and FAILED — no n moves it
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
    #: ⭐ MH2.7 — is the `max_field_size` leg ACTIONABLE ADVICE, or is it arithmetic only? `False`
    #: means the arithmetic-implied field sits BELOW the declared family, so acting on it would mean
    #: dropping pre-registered arms because they lost. `None` when no field leg arises at all. A
    #: MACHINE flag deliberately, so a report table can gate on it instead of parsing the prose (the
    #: MH2.2 report had to carry a hand-written callout under the table — that is not enforcement).
    field_remedy_admissible: bool | None = None
    #: ⭐ PLAT-CVP1 defect 4(a) — was the PBO handed over applied the way the statistic is DEFINED?
    #: `True` = field-level (a verdict about the SEARCH, which is what CSCV measures); `False` = it
    #: was used as a per-ARM pass/fail, a misapplication this classifier REFUSES to convert into a
    #: refusal verdict; `None` = no PBO was supplied, or its application was not stated. A MACHINE
    #: flag for the same reason `field_remedy_admissible` is one: a report table gates on it instead
    #: of parsing prose.
    pbo_application_admissible: bool | None = None
    #: ⭐ PLAT-CVP1 defect 3 — the computed shared-variance (lockstep) reading, when the DSR legs
    #: were evaluable. `None` when they were not (never scored as "the lever is open").
    lockstep: "LockstepReport | None" = None


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


# ⭐⭐ MH2.7 (2026-08-14) — **THE INSTRUMENT'S OWN REMEDY MUST OBEY THE RULE THE INSTRUMENT EXISTS TO
# ENFORCE: YOU GET TO PRE-REGISTER A FAMILY, YOU DO NOT GET TO DISCOVER ONE.**
#
# `dsr_max_field_size` answers a purely ARITHMETIC question — "in how large a field would this effect
# still have cleared?" — and that number is a legitimate design quantity worth recording. What was
# NOT legitimate was handing it back as an IMPERATIVE. `classify_null` sees only a trial COUNT, so it
# cannot tell a DECLARED narrow family (legitimate: the family was named in advance on mechanistic
# grounds) from a DISCOVERED one (the post-hoc trim, which is satisfied by deleting whichever arm
# LOST). MH2.2 hit the bad half live: on a 3-arm DECLARED family (`bb_pct`, 11 folds) the trigger read
# "…OR a field of ≤2 arms at the CURRENT fold count" — and that ≤2-arm field IS the retired post-hoc
# field the whole MH2 lineage exists to reject. Its DSR jump (0.849 → 0.998) was bought by the
# cross-trial dispersion `V` collapsing 19,938× when the LOSING arm was dropped, i.e. by exactly the
# selection bias DSR is there to deflate — re-committed inside a badge that reads like a remedy
# (the E2.1-r inversion, one level up: not a metric chosen after the answer, a REMEDY chosen after it).
#
# The cure is provenance, and it is the same shape as the DSR-CONV `V` note above: the CALLER states
# the smallest field that was PRE-REGISTERED, and an UNSTATED provenance is REFUSED, never assumed
# permissive (NF1.7 (a) — a check that did not run is not a check that passed). Note which way the
# default has to fall: the safe default is the field actually SCORED, because that is the only field
# we know was pre-registered. So `classify_null` can no longer emit a below-declared prescription;
# the number survives as arithmetic, flagged `field_remedy_admissible=False`.
#
# ⚠️ **AND THE HONEST LIMIT OF THIS GUARD, STATED RATHER THAN IMPLIED.** DSR-CONV can insist a
# degenerate qualifies BY DESIGN and never by declaration, because "designed loser" has a measurable
# signature (`|Sharpe| ≥ 3`). "Declared" has none: whether a family was pre-registered is a fact about
# a DOCUMENT, not about the data, so no pure function can verify it. A caller who passes
# `declared_field_size=2` for a family it only decided on afterwards still gets the admissible badge.
# What changes is that the claim must now be MADE, EXPLICITLY, and it lands on the record
# (`detail["declared_field_size_source"]`) where a reviewer can check it against the pre-registration
# — instead of the instrument volunteering the post-hoc field unprompted, which is what it did to
# MH2.2. The guard converts a silent default into an auditable assertion; it does not, and cannot,
# adjudicate the pre-registration itself.
_FIELD_ARITHMETIC_ONLY = (
    "⛔ **NOT A REMEDY — ARITHMETIC ONLY.** The effect clears only in a field of ≤{max_field} arm(s), "
    "which is BELOW the declared family of {declared}. Shrinking a field below what was "
    "pre-registered means dropping arms BECAUSE THEY LOST — the very selection bias DSR exists to "
    "deflate, and on MH2.2's `bb_pct` that move bought its whole apparent gain through a 19,938× "
    "collapse in the cross-trial dispersion `V`, not through honest multiplicity. A smaller field is "
    "a legitimate remedy ONLY if that smaller family was itself declared in advance on MECHANISTIC "
    "grounds. ⇒ the ≤{max_field} figure is reported as a DESIGN QUANTITY, never as advice.")
_FIELD_DECLARED_UNSTATED = (
    " ⚠️ And `declared_field_size` was NOT stated, so this classifier cannot tell a DECLARED narrow "
    "family from a DISCOVERED one; it falls back to the {n_arms} arm(s) actually scored — the only "
    "field known to have been pre-registered — and REFUSES to prescribe below it. If a smaller "
    "family genuinely was pre-registered, pass `declared_field_size=` and re-classify.")
_FIELD_ADMISSIBLE = (
    "re-run the mechanism in its PRE-REGISTERED {max_field}-arm-or-smaller family (≥ the declared "
    "floor of {declared}, so no scored arm has to be dropped to reach it)")
_FIELD_NO_RESCUE = (
    "field size is NOT a lever here — even a 2-arm field does not clear at this fold count and "
    "dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper "
    "metric)")

# ⭐⭐ PLAT-CVP1 defect 3 (NF-W8-0d R2) — THE SENTENCE ABOVE IS ONLY HALF-TRUE, AND THE WRONG HALF IS
# THE ONE A READER ACTS ON. "the only lever left is a lower-variance design" is correct whenever the
# gap `SR − SR0` is POSITIVE (a proportional sharpening scales a positive gap UP). It is
# DETERMINISTICALLY VOID when the gap is negative — the winner is one of the trials whose dispersion
# sets `SR0`, so a shared variance reduction scales BOTH by the same factor and the SIGN of the gap
# never moves (NF-W7k; `lockstep_variance_lever`). NF-W8-0d measured it: dispersion ×0.01 takes DSR
# from 0.1654 to 0.0154, i.e. the prescribed lever makes the gate STRICTLY WORSE. That one sentence
# sent NF-W7f, NF-W7j and NF-W8-0c at the same wall. So the instrument now COMPUTES which half it is
# in rather than naming a lever it was not checking.
_FIELD_NO_RESCUE_LOCKSTEP_CLOSED = (
    "field size is NOT a lever here — even a 2-arm field does not clear at this fold count and "
    "dispersion. ⛔ **AND NEITHER IS A LOWER-VARIANCE DESIGN**, computed rather than assumed: the "
    "gap `SR − SR0` is {gap:.4f} ≤ 0, and a design change that shrinks EVERY arm's dispersion by a "
    "common factor scales `SR` and `SR0` together, so the gap's SIGN is invariant — measured across "
    "a ×{lo:g}…×{hi:g} ladder, over which DSR FALLS as the design sharpens. ⛔ Do NOT publish a "
    "rows/folds/draws/sharper-metric trigger: no `n` overturns a deterministic invariant (NF-W7k / "
    "NF-W8-0d). What remains UNTESTED (not refuted): a DIFFERENTIAL-variance design that shrinks the "
    "WINNER's dispersion more than the field's, a bigger effect, or a genuine absence.")

# ⭐ PLAT-CVP1 defect 2 (NCAAF-VAL3) — A DEFLATION GATE THAT WAS EVALUATED AND FAILED.
# `classify_null` took no PBO argument at all, so it could express PBO-UNDEFINED (too few folds, or a
# single contrast) but NOT PBO-EVALUATED-AND-FAILED. VAL3 hit that squarely: its PBO was the binding
# refusal and the instrument returned `POWER_LIMITED` on its honest insufficient-statistics default,
# a state that structurally could not name the gate that bound. The record hand-carried
# `DEFLATION_REFUSED_PBO` beside it and filed the gap.
_DEFLATION_REFUSED = (
    "`{metric}`: the pre-registered **{gate}** deflation gate was EVALUATED and FAILED "
    "({value:.4f} vs the {bar:.4f} bar). This is not a power shortfall and not an absence — the "
    "search's own deflation requirement refused, over the field as registered.")
_DEFLATION_NO_FOLD_TRIGGER = (
    "⛔ **NO fold/season/row re-test trigger is published, deliberately.** No fold count moves a "
    "pre-registered gate POPULATION, so a 'come back with more seasons' trigger would be the "
    "actively-misleading direction (NF-D18 / MH2 (g″)). The admissible remedy is a FORWARD-registered "
    "narrower COHERENT family on mechanistic grounds (or a forward-registered PBO population) — "
    "⛔ never a post-hoc re-cut of a field you have already scored (MH2.2).")

# ⭐⭐ PLAT-CVP1 defect 4(a) (MLB-HV2-1, MEASURED) — A FIELD-LEVEL STATISTIC READ AS A PER-ARM GATE.
# CSCV/PBO has ONE value per field: it answers "did picking a winner out of THIS field overfit?" With
# a 6-percentage-point bias INJECTED into HV2-1's population, every metric gate fired (ROI up to
# +0.156, p as low as 1.4e-8) and PBO ROSE to 0.426 — because a uniform edge makes the arms
# simultaneously strong NEAR-CLONES, so "which arm is best in-sample" becomes a coin flip. That is
# NF1.8's lesson (a high PBO over a near-clone field is the signature of a TIE, not of overfitting),
# and it means a field-level PBO used as a per-arm gate VETOES A REAL, LARGE, UNIFORM EFFECT. So the
# classifier will not convert a per-arm-applied PBO into a refusal verdict; it reports the
# misapplication instead, and the other gates decide.
_PBO_PER_ARM_MISAPPLICATION = (
    "⛔ **PBO REFUSAL NOT ADMITTED — a FIELD-LEVEL statistic was applied PER ARM.** CSCV/PBO has one "
    "value for the whole field and answers whether the SELECTION overfit; it does not vary across "
    "arms, so reading it as a per-arm pass/fail converts 'the search was unstable' into 'this arm "
    "failed', which is not a statement the statistic makes. MLB-HV2-1 MEASURED the cost: with a 6pp "
    "bias INJECTED, every metric gate fired and PBO rose to 0.426 precisely BECAUSE the planted "
    "effect made the arms near-clones (NF1.8: a high PBO over near-clones is a TIE, not overfitting) "
    "— so the per-arm reading vetoed a real, large effect. ⇒ this classifier does NOT return "
    "`DEFLATION_REFUSED` on it; re-read the PBO at FIELD level (a verdict about the search) and "
    "re-classify, and let the per-arm gates decide the arm.")
_PBO_APPLICATION_UNSTATED = (
    " ⚠️ `pbo_application` was NOT stated, so this classifier cannot tell a FIELD-level reading (the "
    "statistic's own meaning) from the per-ARM misapplication MLB-HV2-1 measured. The refusal stands "
    "as recorded but is flagged UNVERIFIED — state `pbo_application='field'` and re-classify rather "
    "than quoting it bare (NF1.7 (a): a check that did not run is not a check that passed).")


def _field_size_remedy(*, max_field: int, n_arms: int,
                       declared_field_size: int | None,
                       lockstep: "LockstepReport | None" = None) -> tuple[bool | None, str]:
    """The `max_field_size` leg of a re-test trigger, made self-safe. Returns `(admissible, text)`.

    `admissible is None` ⇒ field size is no lever at all here (nothing to be admissible ABOUT);
    `False` ⇒ the arithmetic sits below the declared/scored family, so the number is reported but the
    IMPERATIVE is refused; `True` ⇒ a pre-registered family at least this small exists, so the
    prescription can be acted on without re-cutting a scored field.
    """
    if int(max_field) < 2:
        # ⭐ PLAT-CVP1 defect 3 — which half of the variance statement are we in? COMPUTED, because
        # naming "a lower-variance design" when the lockstep is closed is the sentence that sent
        # three consecutive records at a wall (NF-W8-0d R2).
        if lockstep is not None and lockstep.closed:
            lo = min(r["dispersion_factor"] for r in lockstep.ladder) if lockstep.ladder else 1.0
            hi = max(r["dispersion_factor"] for r in lockstep.ladder) if lockstep.ladder else 1.0
            return None, _FIELD_NO_RESCUE_LOCKSTEP_CLOSED.format(
                gap=float(lockstep.gap), lo=lo, hi=hi)
        return None, _FIELD_NO_RESCUE
    declared = int(declared_field_size) if declared_field_size is not None else int(n_arms)
    if int(max_field) >= declared:
        return True, _FIELD_ADMISSIBLE.format(max_field=int(max_field), declared=declared)
    text = _FIELD_ARITHMETIC_ONLY.format(max_field=int(max_field), declared=declared)
    if declared_field_size is None:
        text += _FIELD_DECLARED_UNSTATED.format(n_arms=int(n_arms))
    return False, text


def classify_null(*, metric: str, n_folds: int, n_arms: int,
                  beats_foil: bool, observed_sr: float | None = None,
                  var_trials_sr: float | None = None,
                  fold_wins: int | None = None,
                  p_one_sided: float | None = None, bh_cutoff: float | None = None,
                  active: bool = True, inactive_reason: str | None = None,
                  mde_sd_units: float | None = None,
                  meaningful_sd_units: float | None = None,
                  effect_ci_upper_sd_units: float | None = None,
                  effect_ci_lower_sd_units: float | None = None,
                  pbo: float | None = None, pbo_gate: float = MAX_PBO,
                  pbo_application: str | None = None,
                  skew: float = 0.0, kurt: float = 3.0,
                  confidence: float = DSR_CONFIDENCE,
                  degenerates_excluded_from_v: bool | None = None,
                  var_trials_sr_with_degenerates: float | None = None,
                  declared_field_size: int | None = None) -> NullVerdict:
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

    ⭐⭐ **`declared_field_size` (MH2.7) states the SMALLEST field that was PRE-REGISTERED for this
    mechanism**, and it is what stops the `max_field_size` leg from prescribing the retired post-hoc
    field (see `_field_size_remedy`). Normally it equals `n_arms` — the declared family you scored —
    and should be passed as such; pass something SMALLER only when that smaller family was itself
    named in advance on mechanistic grounds (E7.15-H3's 7 eligible arms bundled two families, of
    which the 3-arm trajectory family was declared). Leaving it `None` is REFUSED, not permitted:
    the classifier falls back to `n_arms` and will not prescribe below it. Like the `V` provenance,
    this changes NO state — only whether the field sentence is an imperative or a design quantity.
    """
    d: dict = {"n_folds": int(n_folds), "n_arms": int(n_arms)}
    #: computed by the DSR block when its inputs are present; `None` means NOT EVALUATED, and is
    #: never read as "the shared-variance lever is open" (NF1.7 (a)).
    lock: LockstepReport | None = None
    #: the DSR fold-shortfall verdict, HELD so the deflation branch can preempt it (defect 2).
    pending: NullVerdict | None = None
    #: defect 4(a) — set once a PBO is supplied; threaded onto every verdict below.
    pbo_admissible: bool | None = None

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

    if int(n_arms) < 2:
        # ⭐ MH2.7 CO-FIX — **A SINGLE PRE-REGISTERED CONTRAST IS NOT A FOLD SHORTAGE.** `pbo_evaluable`
        # is false for TWO structurally different reasons — too few folds, or too few arms — and
        # collapsing them made the fold branch below render a 1-arm design as "8 fold(s) < 4",
        # prescribing "−4 more fold(s)". That trigger tells a reader to BUY SEASONS for a deflation
        # statistic a 1-arm design never needed, and it is exactly the actively-misleading direction
        # this module was written to stop (the DSR_UNREACHABLE "needs N more seasons" lesson, one
        # state over). The fantasy vertical hand-corrected it FOUR times (NF-W2 → NF-D18 → NF-W3 →
        # NF-W4) before it was fixed here; a defect that keeps getting corrected downstream is a
        # defect in the instrument. ⚠️ The STATE is deliberately UNCHANGED (`UNDEFINED` either way) —
        # PBO genuinely is not computable, so no recorded verdict moves; what changes is that the
        # reason names the real cause and the fabricated fold trigger is GONE (`None`, for the same
        # reason `GENUINE_ABSENCE` carries none: quoting one would be a lie).
        also_short = int(n_folds) < MIN_FOLDS_FOR_PBO
        return NullVerdict("UNDEFINED", (
            f"`{metric}`: the design is a SINGLE pre-registered contrast ({n_arms} selectable arm), "
            f"so there is NO SEARCH to overfit — CSCV/PBO is INAPPLICABLE, not unmet, and no fold "
            f"count makes it computable. ⛔ Do NOT read this as a power shortfall and do NOT quote a "
            f"fold trigger for it (NF-W3/NF-W4). The deflation requirement is satisfied by the "
            f"DESIGN; read the remaining gates — the paired contrast, its fold consistency and DSR — "
            f"to classify the null itself."
            + (f" ⚠️ Separately, {n_folds} fold(s) < {MIN_FOLDS_FOR_PBO} is a real shortfall for "
               f"those OTHER gates; it is simply not what makes PBO undefined here." if also_short
               else "")),
            retest_trigger=None, folds_have=int(n_folds), detail=d)

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
        # ⭐⭐ PLAT-CVP1 defect 1 (NCAAF-VAL1) — **CONSULT THE INTERVAL BEFORE CLAIMING ABSENCE.**
        # This branch used to short-circuit unconditionally, ahead of every power reading, on the
        # (correct, as far as it goes) principle that no `n` flips a negative point estimate. What it
        # missed is that at low `n` a TRUE, decision-changing effect ROUTINELY presents as a negative
        # point estimate — VAL1 measured a design where a true +2 pp edge reads as −1 pp — so
        # "do NOT re-test" over-claims. It was worse than over-claiming in one direction: VAL1's
        # `ats/wk1-3` bucket, whose interval STILL ADMITS the pre-registered meaningful effect, got
        # the same do-not-re-test badge as buckets whose interval excludes it. 5 of its 6 buckets
        # were mislabelled and hand-corrected at the call site.
        #
        # The fix is the sharper POST-DATA question, and it was registered forward in VAL1 §8a: when
        # a practically-meaningful bar is on record, read the EFFECT'S INTERVAL against it.
        #   * interval WHOLLY BELOW the bar ⇒ the entire plausible range is below a decision-changing
        #     effect ⇒ this is DECISIVE, and `GENUINE_ABSENCE`'s "do not re-test" is earned.
        #   * interval SPANNING the bar ⇒ the design cannot separate the null from an effect that
        #     would matter ⇒ `POWER_LIMITED`. ⛔ Not absence.
        # ⚠️ The MDE and the interval answer DIFFERENT questions ("what would I have caught?" vs
        # "what is still plausible given what I saw"), and the interval is the sharper one after the
        # data. The MDE is used only as the fallback when no interval is supplied, and the evidence
        # that backed the verdict is recorded either way — an absence certified by neither is not
        # certified (NF1.7 (a)).
        # ⭐ Back-compat is exact and deliberate: a caller with NO pre-registered meaningful effect
        # passes no `meaningful_sd_units` and gets the unchanged verdict, because there is no bar to
        # read an interval against and the point-estimate rule is then the only rule there is.
        if meaningful_sd_units is None:
            return NullVerdict("GENUINE_ABSENCE", (
                f"`{metric}`: the best arm does not beat the foil ON AVERAGE. No sample size rescues "
                f"a negative point estimate and no field size changes its sign — do NOT re-test."),
                retest_trigger=None, folds_have=int(n_folds), detail=d)

        bar = float(meaningful_sd_units)
        d["meaningful_sd_units"] = bar
        if effect_ci_lower_sd_units is not None:
            d["effect_ci_lower_sd_units"] = float(effect_ci_lower_sd_units)
        if mde_sd_units is not None:
            d["mde_sd_units"] = float(mde_sd_units)

        if effect_ci_upper_sd_units is not None:
            ub = float(effect_ci_upper_sd_units)
            d["effect_ci_upper_sd_units"] = ub
            if ub < bar:
                d["absence_evidence"] = "interval"
                return NullVerdict("GENUINE_ABSENCE", (
                    f"`{metric}`: the best arm does not beat the foil ON AVERAGE, **and** the whole "
                    f"plausible range is below what would matter — the effect's upper bound {ub:.4f} "
                    f"lies below the pre-registered meaningful effect {bar:.4f}. That is DECISIVE, "
                    f"not underpowered: no re-test, because the interval already excludes the effect "
                    f"a trigger would be sized on (NF-D18)."),
                    retest_trigger=None, folds_have=int(n_folds), detail=d)
            d["absence_evidence"] = "none — the interval still admits the meaningful effect"
            return NullVerdict("POWER_LIMITED", (
                f"`{metric}`: the point estimate is below the foil, but the effect's upper bound "
                f"{ub:.4f} STILL ADMITS the pre-registered meaningful effect {bar:.4f}. ⛔ Do NOT "
                f"read this as absence — at this `n` a decision-changing effect routinely presents "
                f"as a negative point estimate, so this design cannot separate the two (NCAAF-VAL1)."),
                retest_trigger=(
                    "a design whose interval EXCLUDES the meaningful effect. ⚠️ Stated as a design "
                    "requirement, not in seasons: only the caller knows the fold/row rule that "
                    "converts it (the same reason the DSR trigger is stated in folds)."),
                folds_have=int(n_folds), detail=d)

        # No interval supplied. The MDE is the only power evidence on record, and it is weaker —
        # so it may certify an absence only when the design demonstrably RESOLVES the bar.
        if mde_sd_units is not None and float(mde_sd_units) <= bar:
            d["absence_evidence"] = "mde"
            return NullVerdict("GENUINE_ABSENCE", (
                f"`{metric}`: the best arm does not beat the foil ON AVERAGE, and the design "
                f"resolves {float(mde_sd_units):.2f} SD at 80% power — at or below the "
                f"pre-registered meaningful effect of {bar:.2f} SD. An effect that would matter "
                f"would have shown; it did not. ⚠️ This absence is MDE-backed, which is the weaker "
                f"reading — the sharper post-data question is the effect's own interval, and none "
                f"was supplied (pass `effect_ci_upper_sd_units=`)."),
                retest_trigger=None, folds_have=int(n_folds), detail=d)
        d["absence_evidence"] = "none — no interval supplied and the MDE does not reach the bar"
        return NullVerdict("POWER_LIMITED", (
            f"`{metric}`: the point estimate is below the foil, but nothing on record certifies that "
            f"as ABSENCE — no effect interval was supplied, and "
            + (f"the design resolves only {float(mde_sd_units):.2f} SD at 80% power against a "
               f"pre-registered meaningful effect of {bar:.2f} SD"
               if mde_sd_units is not None else
               f"no detectability figure was recorded against the pre-registered meaningful effect "
               f"of {bar:.2f} SD")
            + f". ⛔ A below-foil point estimate at an `n` this design cannot resolve is not a "
              f"do-not-re-test finding (NCAAF-VAL1)."),
            retest_trigger=("supply the effect's interval (`effect_ci_upper_sd_units=`) and "
                            "re-classify — an absence is certified by an interval that excludes the "
                            "bar, or by a design that resolves it, and neither is on record here"),
            folds_have=int(n_folds), detail=d)

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
        # ⭐ MH2.7 — the field leg is built ONCE here and shared by both DSR-derived states below, so
        # the two can never drift apart on whether shrinking the field is admissible.
        # ⭐ PLAT-CVP1 defect 3 — the shared-variance lever, COMPUTED here (NF-W8-0d R2) so the
        # remedy sentences below can never name a lever the arithmetic has already closed.
        lock = lockstep_variance_lever(
            observed_sr=float(observed_sr), n_trials=int(n_arms),
            var_trials_sr=float(var_trials_sr), n_obs=int(n_folds), skew=skew, kurt=kurt,
            confidence=confidence)
        d.update({"lockstep_closed": lock.closed, "lockstep_gap": lock.gap,
                  "lockstep_sign_invariant": lock.sign_invariant})
        field_ok, field_text = _field_size_remedy(
            max_field=max_field, n_arms=int(n_arms), declared_field_size=declared_field_size,
            lockstep=lock)
        d.update({"declared_field_size": declared_field_size,
                  "declared_field_size_source": ("stated" if declared_field_size is not None
                                                 else "unstated — defaulted to n_arms (refused)"),
                  "field_remedy_admissible": field_ok})
        if need is None:
            return NullVerdict("DSR_UNREACHABLE", (
                f"`{metric}`: the winner's per-fold Sharpe {observed_sr:.3f} sits at or BELOW the "
                f"{n_arms}-arm field's deflated benchmark SR0 {sr0:.3f}, so DSR is unreachable at "
                f"ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a "
                f"SMALLER, PRE-REGISTERED field, not more seasons — and ⛔ only if such a field was "
                f"pre-registered; this is NOT a licence to re-cut a field you have already scored "
                f"(MH2.7). {v_note}"),
                retest_trigger=(
                    field_text
                    + ("" if degenerates_excluded_from_v is True
                       else f" — ⚠️ BUT FIRST: {v_note}")),
                folds_have=int(n_folds), max_field_size=max_field,
                field_remedy_admissible=field_ok, lockstep=lock, detail=d)
        if need > int(n_folds):
            # ⚠️ Stated in FOLDS, never translated to seasons here. The fold RULE differs per tier
            # — walk-forward burns `min_train_seasons` before its first fold, leave-one-cohort-out
            # does not — so this function, which does not know the tier, must not do the calendar
            # arithmetic. An earlier cut applied the walk-forward inverse to a cohort-based tier and
            # produced a "36-season window" for a study whose folds ARE cohorts. The caller owns
            # the translation because only the caller knows the rule.
            # ⭐ PLAT-CVP1 defect 2 — this verdict is HELD, not returned, so the PBO branch below
            # can preempt it. A study whose pre-registered PBO was evaluated and FAILED must not be
            # handed a "+N folds" trigger: no fold count moves a gate POPULATION, and publishing one
            # is exactly the actively-misleading direction (NF-D18). Nothing else about the verdict
            # changes — with no `pbo` supplied the branch below is a no-op and this is returned
            # byte-identically to before.
            pending = NullVerdict("POWER_LIMITED", (
                f"`{metric}`: the effect is positive and every gate is REACHABLE, but this design "
                f"cannot resolve it — DSR alone needs {need} folds against {n_folds} (the BH-FDR "
                f"requirement is separate and may be larger). {v_note}"),
                retest_trigger=(f"+{need - int(n_folds)} folds for the DSR gate"
                                + (f", OR {field_text} at the CURRENT fold count" if field_ok
                                   else f" — {field_text}" if field_ok is None
                                   else f". On field size — {field_text}")
                                + ("" if degenerates_excluded_from_v is True
                                   else f" — ⚠️ BUT FIRST: {v_note}")),
                folds_have=int(n_folds), folds_needed=need,
                extra_seasons=need - int(n_folds), max_field_size=max_field,
                field_remedy_admissible=field_ok, lockstep=lock, detail=d)

    # ⭐⭐ PLAT-CVP1 defect 2 (NCAAF-VAL3) — A DEFLATION GATE THAT WAS EVALUATED AND FAILED.
    # Placed HERE deliberately, and the order is the argument:
    #   * AFTER `beats_foil` — MLB-HV2-1's lesson. When every arm's point estimate is negative the
    #     null rests on the point estimate, not on a deflation gate, and no gate change moves it.
    #   * AFTER `DSR_UNREACHABLE` — that state says no fold count AND no admissible field clears,
    #     which is strictly more specific and less rescuable than "the PBO gate refused".
    #   * BEFORE every `POWER_LIMITED` — including the DSR one held above. This is the whole defect:
    #     VAL3's PBO was the binding refusal and the classifier returned `POWER_LIMITED` on its
    #     insufficient-statistics default, a state that structurally could not name the gate that
    #     bound. Whether a fold trigger would have been published there is not a detail: a
    #     "come back with more seasons" trigger for a PBO refusal is a lie about the remedy.
    if pbo is not None:
        d.update({"pbo": float(pbo), "pbo_gate": float(pbo_gate),
                  "pbo_pass": bool(float(pbo) < float(pbo_gate)),
                  "pbo_application": pbo_application})
        if pbo_application is not None and pbo_application not in PBO_APPLICATIONS:
            raise ValueError(f"pbo_application must be one of {PBO_APPLICATIONS} or None, "
                             f"got {pbo_application!r}")
        if float(pbo) >= float(pbo_gate):
            # defect 4(a): a FIELD-level statistic read as a per-ARM gate is refused, not converted
            # into a refusal verdict. The measurement behind this is HV2-1's injected 6pp bias.
            if pbo_application == "per_arm":
                d["pbo_application_admissible"] = pbo_admissible = False
                d["pbo_refusal_admitted"] = False
                d["pbo_refusal_refused_because"] = _PBO_PER_ARM_MISAPPLICATION
            else:
                d["pbo_application_admissible"] = pbo_admissible = (
                    True if pbo_application == "field" else None)
                d["pbo_refusal_admitted"] = True
                return NullVerdict("DEFLATION_REFUSED", (
                    _DEFLATION_REFUSED.format(metric=metric, gate="CSCV/PBO", value=float(pbo),
                                              bar=float(pbo_gate))
                    + " " + _DEFLATION_NO_FOLD_TRIGGER
                    + ("" if pbo_application == "field" else _PBO_APPLICATION_UNSTATED)),
                    retest_trigger=None, folds_have=int(n_folds),
                    pbo_application_admissible=d["pbo_application_admissible"],
                    lockstep=lock, detail=d)
        else:
            d["pbo_application_admissible"] = pbo_admissible = (
                True if pbo_application == "field" else
                False if pbo_application == "per_arm" else None)

    if pending is not None:
        # the DSR fold shortfall, released now that no deflation gate preempted it
        if pbo_admissible is not None:
            pending.pbo_application_admissible = pbo_admissible
        return pending

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
                extra_seasons=need - int(n_folds),
                pbo_application_admissible=pbo_admissible, lockstep=lock, detail=d)

    if mde_sd_units is not None and meaningful_sd_units is not None:
        d.update({"mde_sd_units": float(mde_sd_units),
                  "meaningful_sd_units": float(meaningful_sd_units)})
        if float(mde_sd_units) > float(meaningful_sd_units):
            return NullVerdict("POWER_LIMITED", (
                f"`{metric}`: the design detects {mde_sd_units:.2f} SD at 80% power, but the "
                f"pre-registered practically-meaningful effect is {meaningful_sd_units:.2f} SD — a "
                f"decision-changing effect would NOT reliably have shown up here."),
                pbo_application_admissible=pbo_admissible, lockstep=lock, detail=d)
        return NullVerdict("TRUSTWORTHY_DEAD", (
            f"`{metric}`: the design detects {mde_sd_units:.2f} SD at 80% power, at or below the "
            f"pre-registered meaningful effect of {meaningful_sd_units:.2f} SD. A decision-changing "
            f"effect would have shown and did not — this null RULES THE MECHANISM OUT at the size "
            f"that would matter."), retest_trigger=None, folds_have=int(n_folds),
            pbo_application_admissible=pbo_admissible, lockstep=lock, detail=d)

    return NullVerdict("POWER_LIMITED", (
        f"`{metric}`: insufficient recorded statistics to certify the null as powered. Absent a "
        f"detectability figure the honest default is POWER-LIMITED — a null is trustworthy only "
        f"when something was computed to make it so."), folds_have=int(n_folds),
        pbo_application_admissible=pbo_admissible, lockstep=lock, detail=d)


__all__ = [
    "MIN_TRAIN_SEASONS", "MIN_FOLDS_FOR_PBO", "MIN_FOLDS_FOR_DSR", "LEGACY_FOLD_WIN_RATE",
    "BH_ALPHA", "FOLD_CONSISTENCY_ALPHA", "PBO_SHADOW_TO_LIVE", "NULL_STATES",
    "MAX_PBO", "PBO_APPLICATIONS", "DEFLATION_CLASS_GATES", "LOCKSTEP_DISPERSION_FACTORS",
    "POSITIVE_CONTROL_VERDICTS", "LockstepReport", "lockstep_variance_lever",
    "PositiveControlReport", "injected_effect_positive_control",
    "achievable_folds", "seasons_for_folds", "pbo_evaluable",
    "fold_gate_false_fire", "FoldConsistencyClause", "fold_consistency_clause",
    "sign_test_floor", "folds_for_sign_certifiability",
    "SignCertifiability", "validate_sign_certifiability",
    "GATE_CLASSES", "GATE_PARTITION_SOURCES",
    "dsr_benchmark_sr0", "dsr_from_sr", "dsr_required_sr", "dsr_ceiling", "folds_to_clear_dsr",
    "dsr_max_field_size", "field_size_curve", "decompose_field_size",
    "composite_gate_power", "mde_in_sd_units", "NullVerdict", "classify_null",
]
