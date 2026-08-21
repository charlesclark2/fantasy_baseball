"""coverage_power_floor.py — the POWER-DERIVED coverage floor for a shipped interval band (NF-D22).

⚠️ WHAT THIS REPLACES, AND WHY THE THING IT REPLACES IS A DEFECT IN THE GATE
════════════════════════════════════════════════════════════════════════════════════════════════
A per-group coverage floor set at the NOMINAL level and read as a POINT ESTIMATE — "this group's
realized coverage must be ≥ 0.80" — is a hypothesis test whose false-reject rate is **≈ 0.5 at every
sample size the program has**, because the realized coverage of a *perfectly calibrated* band is a
Binomial mean that lands below its own expectation about half the time. NF1.8 measured this and said
so plainly:

    "at n ≈ 81 a hard point-estimate floor at nominal rejects a PERFECTLY-calibrated arm ~50% of the
     time — and that false-reject rate barely moves with n; sample size buys the ability to detect a
     SMALLER true shortfall, not a lower false-reject rate."

Measured here across the whole range this program uses (exact Binomial, nominal 0.80):

    n        30     81    148    400   1000   3000   6000
    P(reject | truly nominal)   0.393  0.456  0.500  0.470  0.481  0.489  0.492

⇒ A gate built on that floor is a **coin flip on a correct band, forever, at any n**. That is not a
conservative gate; it is an *uninformative* one, and an uninformative gate that blocks things is
strictly worse than no gate, because its refusals read as evidence.

THE REPLACEMENT — a floor derived from **n and a pre-registered false-reject TARGET, and nothing
else**. The floor is the exact one-sided Binomial acceptance bound: the largest required covered-row
count `k` such that a band whose TRUE coverage is nominal clears it with probability ≥ 1 − target.
Equivalently (and this is the form the story states): accept a band whose exact one-sided lower
confidence bound on coverage, at confidence 1 − target, reaches nominal.

    floor(n) = k(n) / n      where   k(n) = max{ k : P(Binom(n, nominal) < k) ≤ target }

⭐ EVERY INPUT IS A **DESIGN QUANTITY KNOWN BEFORE ANY RESULT EXISTS**: the group's row count, the
nominal coverage the band was built for, and the target false-reject rate. No observed coverage, no
board, no fold and no artifact can reach these functions — `power_floor` does not take a coverage
argument, and a guard asserts that its signature never gains one. That is the property that makes
this a floor rather than a number reverse-engineered from something that failed.

════════════════════════════════════════════════════════════════════════════════════════════════
⛔ WHAT THIS FILE MAY NOT BECOME (E2.1-r; NF1.8 §1) — READ BEFORE EDITING
════════════════════════════════════════════════════════════════════════════════════════════════
  · `FALSE_REJECT_TARGET` IS NOT A TUNING KNOB. A floor that moves until something clears it is not
    a floor. The target is not new and was not chosen here: it is the SAME one-sided 5% level NF1.8
    pre-registered for its Tier-2 fallback (`_TIER2_Z = 1.6449 = Φ⁻¹(0.95)`), written down long
    before anything measured against it — see `TARGET_PROVENANCE` and the guard that pins the
    equality mechanically rather than trusting this sentence.
  · ⛔ NEVER TIGHTEN A FLOOR ABOVE NOMINAL. NF1.8: "every notch above nominal moves the eligible set
    toward `max_width` and away from an honest interval." `power_floor` clamps at nominal and a
    guard proves the clamp binds; a "safety margin" above nominal is the same error facing the
    other way.
  · ⛔ THIS IS A **GATE** FLOOR, NOT A **SELECTION** FLOOR — and the distinction is load-bearing,
    not a scoping convenience:
      – Inside a §0.5 BAKE-OFF the floor is an ELIGIBILITY CONSTRAINT over a FIELD of candidate
        arms, and the METRIC does the selecting. NF1.8's whole discipline rests on that shape ("a
        constraint a degenerate satisfies is fine, because the metric then eliminates it"). Loosening
        eligibility there would admit arms into searches that are already RECORDED, i.e. re-decide
        past selections post hoc.
      – In the STANDING RE-VALIDATION and the promotion GATE there is ONE shipped band, no field and
        no metric. The floor IS the entire decision. That is exactly and only where a ~50%
        false-reject rate is fatal.
    ⇒ `run_rookie_perposition_ablation.position_floors` (the selection floor) is deliberately
    UNTOUCHED by NF-D22 and its guards remain green, unedited.
  · A floor breach under THIS rule is still a RE-SELECTION TRIGGER, never a reason to move the
    floor again. Under the calibrated rule a breach now MEANS something — that is the point.

════════════════════════════════════════════════════════════════════════════════════════════════
⭐ APPLIED UNIFORMLY TO EVERY CONSTRAINED GROUP — BECAUSE A BOUNDARY IS A DEGREE OF FREEDOM
════════════════════════════════════════════════════════════════════════════════════════════════
The brief asks for the power-derived floor "applied uniformly to all THIN groups". This module
applies it to **every** constrained group instead, and the two are the same set:

  · The floor SELF-ATTENUATES. `nominal − floor(n)` shrinks as √(1/n) — 13.3pp at n = 30, 1.2pp at
    n = 3000, 0.85pp at n = 6000 — so on a fat group it converges to the nominal floor on its own.
    Nothing has to decide when to stop applying it.
    ⚠️ ATTENUATION IS AN ENVELOPE, NOT POINTWISE MONOTONICITY, and the difference is worth stating
    because "the floor rises with n" is the natural (wrong) way to assert it: the requirement is an
    INTEGER count, so discreteness makes the floor locally jagged (n = 31 → 0.6774 but n = 37 →
    0.6757). What is stable is `(nominal − floor)·√n`, which sits in a narrow band (~0.63–0.76 at
    nominal 0.80) across three orders of magnitude. The guard asserts the envelope; asserting
    monotonicity would have been a claim the arithmetic does not support.
  · Under the pre-registered target, EVERY group size this program has is thin by the only
    knob-free criterion available (the calibrated floor sits more than one covered row below the
    nominal one: 4 rows at n = 30, 9 at n = 148, 51 at n = 6000). `is_thin` reports it; it does not
    gate, because it never discriminates.
  · ⭐ AND THAT IS THE POINT: a "thin-group list" would be a boundary someone drew, and the one
    thing NF-D22 must not be accusable of is drawing a boundary around the group that failed. There
    is no list here, no threshold, and no position name anywhere in this file.

════════════════════════════════════════════════════════════════════════════════════════════════
🚧 THE SUBSTANTIVE BACKSTOP IS THE POOLED FLOOR, AND IT IS NOT AN ACCIDENT
════════════════════════════════════════════════════════════════════════════════════════════════
The obvious objection to a self-attenuating per-group floor is that a thin group's floor is genuinely
low (0.743 at n = 148), so a band could in principle sit near it everywhere. It cannot: the POOLED
check runs the identical rule over the pooled row count, which is several times larger, so its floor
is materially tighter (0.7733 at n = 600 vs 0.7432 at n = 148). A band sitting at each thin group's
own floor fails the pooled one. The two-tier structure is the backstop, `pooled_backstop_check`
measures it rather than asserting it, and a guard proves the pooled floor is the stricter of the two.

════════════════════════════════════════════════════════════════════════════════════════════════
📐 WHAT IS REPORTED BESIDE THE VERDICT (both sides, always)
════════════════════════════════════════════════════════════════════════════════════════════════
A floor that only ever reports "met/breached" hides whether it can see anything. Every read here
carries:
  · `false_reject_rate` — P(a truly-nominal band fails), which the contract bounds by the target;
  · `detectable_shortfall` — the largest true coverage this n rejects with ≥ 80% probability, i.e.
    the floor's RESOLUTION. A gate that cannot resolve a defect has not cleared it, it has failed to
    look (NF1.7 (a)); reporting the resolution is what stops a pass being read as a certificate;
  · `slack_rows` — the margin in COVERED ROWS, never in coverage decimals (NF1.8's convention: a
    coverage decimal a fraction below nominal reads like a calibration change, while "two covered
    rows out of a hundred and fifty" reads like what it actually is);
  · `family_false_reject_rate` — the MULTIPLICITY reading over all floors in the family. It is
    REPORTED AND NOT ACTED ON, deliberately: a Bonferroni split would make every individual floor
    LOOSER, which is precisely the move a reader should distrust from this story. The per-group
    pre-registered target binds; the family figure is the honest caveat beside it (NF1.8's
    report-both-conventions rule).

No IO, no pandas, no football. Pure arithmetic on (n, nominal, target), so the fast gate can exercise
every branch (CLAUDE.md: a gate that fetches its own inputs is a gate validated nowhere).
"""
from __future__ import annotations

from typing import Iterable, Mapping

import numpy as np
from scipy.stats import binom, norm

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered constants
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: The false-reject TARGET: the probability that a band whose TRUE coverage is exactly nominal is
#: rejected by its own floor. The contract this module honours is `P(reject | truly nominal) ≤ this`
#: at EVERY n, exactly (not asymptotically).
#:
#: ⭐ IT IS NOT A NEW NUMBER. It is NF1.8's own pre-registered Tier-2 level — that fallback floor is
#: `nominal − 1.6449·SE(n)`, i.e. "not significantly below nominal, ONE-SIDED AT 95%", so its target
#: is 1 − Φ(1.6449) = 0.05. NF-D22 changes that level's SCOPE (from a hardcoded two-position tuple to
#: every constrained group) and its FORM (exact Binomial rather than a normal approximation that does
#: not actually honour the stated rate at small n). It does not change the level, and
#: `test_the_target_is_nf1_8s_own_pre_registered_level` pins that mechanically so this paragraph
#: cannot drift away from the code.
FALSE_REJECT_TARGET: float = 0.05

TARGET_PROVENANCE = (
    "NF1.8's pre-registered Tier-2 fallback level: `_TIER2_Z = 1.6448536269514722 = Φ⁻¹(0.95)`, "
    "i.e. a ONE-SIDED 95% test ⇒ a 0.05 false-reject target. Recorded in "
    "`run_rookie_perposition_ablation` before any of the results this floor is now read against "
    "existed. NF-D22 widens its SCOPE and makes it EXACT; it does not move the level."
)

#: The probability at which a floor is said to DETECT a true shortfall. Used only to REPORT the
#: floor's resolution (`detectable_shortfall`); it never enters a verdict, so it is a reporting
#: convention rather than a second gate knob. 0.80 is the conventional power level.
DETECTION_POWER: float = 0.80

#: The rule's identity, stamped into every report so a stored verdict can never be mistaken for one
#: produced under the previous (hard point-estimate) rule.
FLOOR_RULE = "nf_d22_exact_binomial_power_floor_v1"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The floor itself — a function of (n, nominal, target) and NOTHING else
# ══════════════════════════════════════════════════════════════════════════════════════════════
def required_covered_rows(n: int, *, nominal: float, target: float = FALSE_REJECT_TARGET) -> int:
    """The floor expressed where it is honest: in COVERED ROWS.

    `k = max{ k : P(Binom(n, nominal) < k) ≤ target }` — the largest requirement whose false-reject
    rate against a truly-nominal band still honours the target. Solved EXACTLY (a search around the
    Binomial quantile, then walked to the boundary) rather than through a normal approximation: at
    n = 30 the approximation's realized rate misses its own stated level, and a floor that does not
    honour the rate it advertises is the defect this module exists to remove.

    ⚠️ NO COVERAGE ARGUMENT, EVER. This is the design quantity; what a band actually covered belongs
    on the other side of the comparison.
    """
    n = int(n)
    if n <= 0:
        raise ValueError(f"a floor needs rows to stand on; got n={n}")
    if not 0.0 < nominal < 1.0:
        raise ValueError(f"nominal must lie strictly in (0, 1); got {nominal}")
    if not 0.0 < target < 0.5:
        raise ValueError(
            f"a false-reject target outside (0, 0.5) is not a target; got {target}. ⛔ It is not a "
            "tuning knob — see this module's prohibitions.")
    k = int(binom.ppf(target, n, nominal))
    # walk DOWN while the requirement rejects a truly-nominal band too often …
    while k > 0 and float(binom.cdf(k - 1, n, nominal)) > target:
        k -= 1
    # … then UP to the largest requirement that still honours the target (discreteness means the
    # quantile can land strictly inside the acceptance region).
    while float(binom.cdf(k, n, nominal)) <= target:
        k += 1
    return int(k)


def power_floor(n: int, *, nominal: float, target: float = FALSE_REJECT_TARGET) -> float:
    """The power-derived coverage floor for a group of `n` held-out rows.

    ⛔ CLAMPED AT NOMINAL AND NEVER ABOVE IT. The clamp is mathematically slack for any sane target
    (the acceptance bound always sits below the nominal count) but it is written, and guarded,
    because "tighten the floor a little for safety" is a real and recurring temptation and NF1.8
    forbids it explicitly: every notch above nominal moves the eligible set toward `max_width`.
    """
    return float(min(nominal, required_covered_rows(n, nominal=nominal, target=target) / int(n)))


def normal_approx_floor(n: int, *, nominal: float,
                        target: float = FALSE_REJECT_TARGET) -> float:
    """`nominal − z·SE(n)` — NF1.8's Tier-2 form, kept for CONTINUITY OF THE RECORD only.

    Reported beside the exact floor so a reader can see NF-D22 did not move the level, only the
    approximation. ⛔ It is not what gates: at small n it does not honour its own advertised rate,
    which `approximation_error` measures rather than assumes."""
    se = float(np.sqrt(nominal * (1.0 - nominal) / int(n)))
    return float(min(nominal, nominal - float(norm.ppf(1.0 - target)) * se))


def false_reject_rate(n: int, *, nominal: float, floor: float) -> float:
    """P(a band whose TRUE coverage is exactly `nominal` fails `floor`) — EXACT, not asymptotic.

    This is the number that indicts the incumbent rule (≈0.5 at every n) and the number the new
    rule's contract bounds by the target. It is computed the same way for both, so the comparison is
    a measurement rather than a claim."""
    need = int(np.ceil(float(floor) * int(n) - 1e-9))
    return float(binom.cdf(need - 1, int(n), nominal))


def pass_probability(n: int, *, true_coverage: float, floor: float) -> float:
    """P(a band whose TRUE coverage is `true_coverage` CLEARS `floor`) — the two-sided half.

    A floor is only worth having if a genuinely-short band still fails it. This is the function that
    lets that be measured instead of hoped for."""
    need = int(np.ceil(float(floor) * int(n) - 1e-9))
    return float(1.0 - binom.cdf(need - 1, int(n), float(true_coverage)))


def detectable_shortfall(n: int, *, nominal: float, target: float = FALSE_REJECT_TARGET,
                         power: float = DETECTION_POWER) -> float | None:
    """The floor's RESOLUTION: the largest true coverage this floor rejects with probability ≥ `power`.

    ⭐ REPORTED WITH EVERY VERDICT, because a floor that cannot resolve a defect has not cleared the
    band — it has failed to look, and scoring that green is how a gate becomes decoration (NF1.7 (a)).
    Returns `None` when no coverage in (0, nominal] is detectable at this n, which is itself the
    finding: at that size the floor can only ever say "not shown to be broken".
    """
    floor = power_floor(n, nominal=nominal, target=target)
    grid = np.arange(round(float(nominal), 4), 0.0, -0.0005)
    for p in grid:
        if 1.0 - pass_probability(n, true_coverage=float(p), floor=floor) >= power:
            return round(float(p), 4)
    return None


def is_thin(n: int, *, nominal: float, target: float = FALSE_REJECT_TARGET) -> bool:
    """Does the calibrated floor sit more than ONE COVERED ROW below the nominal one?

    The only knob-free reading of "structurally thin" available: it compares two quantities this
    module already owns and introduces no threshold of its own. ⚠️ **It is a DIAGNOSTIC and gates
    NOTHING** — under the pre-registered target it is `True` at every group size this program has
    (4 rows at n = 30 through 51 at n = 6000), which is exactly why the floor is applied uniformly
    and why a "thin-group list" would have been a boundary someone chose rather than measured."""
    return (int(np.ceil(nominal * int(n) - 1e-9))
            - required_covered_rows(int(n), nominal=nominal, target=target)) >= 1


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Reading a group, and reading a family of groups
# ══════════════════════════════════════════════════════════════════════════════════════════════
def group_floor(n: int, *, nominal: float, target: float = FALSE_REJECT_TARGET,
                coverage: float | None = None) -> dict:
    """One group's floor, its properties, and — only if supplied — its verdict.

    ⚠️ `coverage` is OPTIONAL AND LAST, and it does not touch the floor. Calling this with no
    coverage yields the complete DESIGN table: every floor in the family can be published before a
    single band is scored, which is the strongest available demonstration that no result produced
    them."""
    n = int(n)
    hard_k = int(np.ceil(nominal * n - 1e-9))
    k = required_covered_rows(n, nominal=nominal, target=target)
    floor = power_floor(n, nominal=nominal, target=target)
    out = {
        "n": n,
        "nominal": round(float(nominal), 4),
        "floor": round(floor, 4),
        "floor_rule": FLOOR_RULE,
        "target_false_reject_rate": float(target),
        "covered_rows_required": k,
        "covered_rows_required_at_nominal_floor": hard_k,
        # the relaxation in ROWS — NF1.8's convention, and the number that says how much the
        # calibration correction is actually worth to this group
        "relaxation_rows": hard_k - k,
        "relaxation_pp": round(100.0 * (float(nominal) - floor), 3),
        "normal_approx_floor": round(normal_approx_floor(n, nominal=nominal, target=target), 4),
        "false_reject_rate": round(false_reject_rate(n, nominal=nominal, floor=floor), 4),
        "false_reject_rate_at_nominal_floor": round(
            false_reject_rate(n, nominal=nominal, floor=float(nominal)), 4),
        "detectable_shortfall": detectable_shortfall(n, nominal=nominal, target=target),
        "is_thin": bool(is_thin(n, nominal=nominal, target=target)),
    }
    # ⭐ THE APPROXIMATION ERROR, MEASURED — this is the evidence for using the exact form rather
    #    than NF1.8's normal one. It is how far the Tier-2 approximation's REALIZED false-reject
    #    rate sits from the rate it advertises; a positive value means it rejects a truly-nominal
    #    band more often than it says it does. Measured, so "the exact form is better" is a number
    #    in the report rather than an assertion in this docstring.
    out["approximation_error"] = round(
        false_reject_rate(n, nominal=nominal, floor=out["normal_approx_floor"]) - target, 4)
    if coverage is None:
        return out
    covered = int(round(float(coverage) * n))
    out.update({
        "coverage": round(float(coverage), 4),
        "covered_rows": covered,
        "slack_rows": covered - k,
        "slack_rows_at_nominal_floor": covered - hard_k,
        "met": bool(covered >= k),
    })
    return out


def family_false_reject_rate(ns: Iterable[int], *, nominal: float,
                             target: float = FALSE_REJECT_TARGET) -> dict:
    """The MULTIPLICITY reading over a family of floors — REPORTED, NOT ACTED ON.

    Every floor in a family must hold for the check to pass, so the rate at which the WHOLE check
    falsely fires compounds. Both readings are given because they are both true and they say
    different things.

    ⛔ NF-D22 DELIBERATELY DOES NOT CORRECT FOR MULTIPLICITY, and the reason is the story's own
    integrity: a Bonferroni split lowers `target` per group, which makes every individual floor
    LOOSER — i.e. the one adjustment a reader should most distrust from a story whose downstream
    consequence is a previously-refused publish clearing. The per-group pre-registered level binds;
    this figure is the caveat that travels beside it (NF1.8: report both conventions, let the
    pre-registered one bind).
    """
    ns = [int(x) for x in ns]
    per_group = [false_reject_rate(n, nominal=nominal,
                                   floor=power_floor(n, nominal=nominal, target=target))
                 for n in ns]
    incumbent = [false_reject_rate(n, nominal=nominal, floor=float(nominal)) for n in ns]
    fam = 1.0 - float(np.prod([1.0 - r for r in per_group])) if per_group else 0.0
    fam_inc = 1.0 - float(np.prod([1.0 - r for r in incumbent])) if incumbent else 0.0
    return {
        "n_floors": len(ns),
        "per_group_target": float(target),
        "family_false_reject_rate": round(fam, 4),
        "family_false_reject_rate_at_nominal_floor": round(fam_inc, 4),
        "note": (
            "Independence across groups is ASSUMED here and is optimistic — rows in different "
            "positions share draft classes/seasons, so the true family rate is somewhat lower than "
            "the product. Reported as the conservative reading. ⛔ NOT corrected for: a Bonferroni "
            "split would LOOSEN every individual floor, which is the adjustment this story must "
            "least be able to make."),
    }


def floor_table(n_by_group: Mapping[str, int | None], *, nominal: float,
                target: float = FALSE_REJECT_TARGET,
                min_n: int | None = None,
                coverage_by_group: Mapping[str, float | None] | None = None) -> dict:
    """The whole family's floors in one read.

    `min_n` carries the CALLER's pre-registered minimum group size unchanged — a group below it is
    reported UNCONSTRAINED exactly as before. NF-D22 does not touch that threshold: it is a separate
    pre-registered design quantity owned by each population's own story, and quietly moving it here
    would be a floor change wearing a different hat.
    """
    cov = dict(coverage_by_group or {})
    floors: dict[str, dict] = {}
    unconstrained: list[str] = []
    # ⚠️ "no coverage was supplied at all" (the DESIGN table) and "coverage was supplied and could
    #    not be read" are different facts and must not collapse into one. The second is a check with
    #    no subject and is NEVER a pass (NF1.7 (a)); the first is the whole point of being able to
    #    publish the floors before anything is scored.
    blind: list[str] = []
    for g, n in n_by_group.items():
        n_i = int(n or 0)
        if n_i <= 0 or (min_n is not None and n_i < int(min_n)):
            unconstrained.append(str(g))
            continue
        if g in cov and cov[g] is None:
            blind.append(str(g))
        floors[str(g)] = group_floor(n_i, nominal=nominal, target=target,
                                     coverage=cov.get(g))
    misses = [f"{g} {b['coverage']}<{b['floor']:.4f} ({b['covered_rows']}/{b['n']} covered, "
              f"{b['covered_rows_required']} required)"
              for g, b in sorted(floors.items())
              if "coverage" in b and not b["met"]]
    return {
        "floor_rule": FLOOR_RULE,
        "target_false_reject_rate": float(target),
        "target_provenance": TARGET_PROVENANCE,
        "nominal": round(float(nominal), 4),
        "min_n": (int(min_n) if min_n is not None else None),
        "floors": {g: b["floor"] for g, b in floors.items()},
        "detail": floors,
        "unconstrained": sorted(unconstrained),
        "misses": misses,
        "coverage_unavailable": sorted(blind),
        "family": family_false_reject_rate([b["n"] for b in floors.values()], nominal=nominal,
                                           target=target),
    }


def pooled_backstop_check(pooled_n: int, group_ns: Iterable[int], *, nominal: float,
                          target: float = FALSE_REJECT_TARGET) -> dict:
    """MEASURE (never assert) that the POOLED floor is the stricter of the two tiers.

    The objection to a self-attenuating per-group floor is that a band could sit near every thin
    group's own low floor. The pooled check refutes it — but only if the pooled floor really is
    tighter, which depends on the pooled row count and is therefore a fact to measure per run rather
    than a property to claim in a docstring (`verdict` says `BACKSTOP_HOLDS` / `BACKSTOP_ABSENT`).
    """
    group_ns = [int(x) for x in group_ns if int(x or 0) > 0]
    pooled = power_floor(int(pooled_n), nominal=nominal, target=target)
    per = {int(n): power_floor(int(n), nominal=nominal, target=target) for n in group_ns}
    loosest = max(per.values()) if per else None
    tightest = min(per.values()) if per else None
    return {
        "pooled_n": int(pooled_n),
        "pooled_floor": round(pooled, 4),
        "loosest_group_floor": (round(loosest, 4) if loosest is not None else None),
        "tightest_group_floor": (round(tightest, 4) if tightest is not None else None),
        "verdict": ("BACKSTOP_HOLDS" if tightest is not None and pooled > tightest
                    else "BACKSTOP_ABSENT"),
        "note": ("The pooled floor runs the IDENTICAL rule over a larger n, so it sits closer to "
                 "nominal than any single group's floor. A band resting at each group's own floor "
                 "therefore fails the pooled check — that two-tier structure, not a hand-set "
                 "minimum, is the substantive backstop."),
    }
