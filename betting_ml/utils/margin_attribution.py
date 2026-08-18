"""margin_attribution.py — MH1: the ONE owner of the learner-vs-contract margin decomposition.

WHY THIS MODULE EXISTS
----------------------
A §0.5 bake-off whose arms are `(contract variant × learner class)` reports ONE headline number:
`margin = incumbent_arm − leader_arm`. That is the right PROMOTION question ("is any configuration
better?") and no gate here changes. But it is the WRONG number to attribute to a FEATURE study,
because a leader that also swapped the learner class carries both effects in one figure.

E7.9 measured it: 54–77% of every leader's margin was the `ngboost_normal → glm_elasticnet` swap,
not the columns the story was about. `model_bakeoff.py` has the same arm shape and the same
leader-vs-incumbent margin, so the same mis-attribution was available to every report it wrote.
MH1 ports the decomposition here so there is exactly ONE implementation, and wires it into every
report — including the reports where it CANNOT act, which must say so rather than stay silent
(NF1.7 (a): an anchor that cannot fire is not a passed check).

THE DECOMPOSITION
-----------------
Fix the learner and vary only the contract; fix the contract and vary only the learner::

    reference := incumbent-contract arm under the LEADER's learner
    learner_swap = incumbent_arm − reference     (what changing the LEARNER bought)
    contract     = reference     − leader_arm    (what changing the CONTRACT/features bought)
    learner_swap + contract == total             (exactly, by construction)

⭐ **TWO READINGS THE RAW SHARE CANNOT GIVE YOU, AND BOTH ARE LOUDER THAN "over half".**

1. **A SIGN FLIP.** `learner_share > 1` (or `< 0`) means the CONTRACT component has the OPPOSITE
   sign to the reported margin — i.e. holding the learner fixed, the "winning" contract is WORSE.
   A report that says "the re-pruned contract won" while the learner-fixed reading says it lost is
   not merely over-crediting; it is reporting the wrong direction. That is a distinct verdict about
   the ATTRIBUTION, and it is flagged separately from the `share ≥ 0.5` case.

2. **A SUB-NOISE DENOMINATOR.** `learner_share` is a RATIO, and a ratio whose denominator sits
   inside the metric's own noise floor is noise amplification, not a proportion — the same class of
   error as reading a percentage off a near-zero base. So the share is computed (the legacy key is
   preserved verbatim) but `share_is_meaningful` records whether the denominator clears the noise
   floor, and the renderer REFUSES to headline a percentage that does not. Measured on the record:
   two of E7.9's own three margins (0.0053 and 0.0127 crps against a 0.02 floor) are sub-noise, so
   its quoted "54%/77%" are shares of a denominator the gate itself calls noise.

NOTHING HERE IS A GATE. Every function is pure, IO-free and fast-gate safe; the outputs are
PRESENTATIONAL. A decomposition that would move a verdict is a bug, not a feature.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

__all__ = [
    "ARM_SEPARATOR",
    "INCUMBENT_VARIANT",
    "margin_decomposition",
    "render_margin_attribution_md",
    "variant_effect_by_learner",
]

# The repo-wide arm-name convention this module reads: "<contract variant>::<learner class>",
# with the incumbent contract spelled `incumbent`. A vertical whose arms are named differently
# passes its own `separator` / `incumbent_variant` rather than re-implementing the split.
ARM_SEPARATOR = "::"
INCUMBENT_VARIANT = "incumbent"


def _scores_of(rows, metric: str) -> dict[str, float]:
    """Accept either E7.9's `list[dict]` arm table or a plain `{arm: score}` mapping.

    A vertical that already has scores in hand should not have to fabricate a table to call this.
    """
    if isinstance(rows, Mapping):
        return {str(k): float(v) for k, v in rows.items()}
    key = f"{metric}_mean"
    return {r["arm"]: float(r[key]) for r in rows}


def margin_decomposition(
    table_rows,
    incumbent_arm: str,
    leader_arm: str,
    metric: str,
    *,
    noise_floor: float | None = None,
    separator: str = ARM_SEPARATOR,
    incumbent_variant: str = INCUMBENT_VARIANT,
    lower_is_better: bool = True,
) -> dict:
    """Split the reported margin into its LEARNER-swap part and its CONTRACT part.

    `table_rows` is E7.9's arm table (`[{"arm": ..., f"{metric}_mean": ...}, ...]`) or a
    `{arm: score}` mapping. Arms are `"<variant>{separator}<learner>"`.

    ⚠️ **SIGN CONVENTION.** With `lower_is_better` (crps/brier/nll — every current caller) the
    margin is `incumbent − leader`, so POSITIVE means the leader is BETTER. `lower_is_better=False`
    flips it, so a higher-is-better vertical can adopt this without a silent sign inversion — the
    failure mode a "just reuse it" adoption would otherwise ship.

    Returns a dict that ALWAYS carries `available`, and when unavailable ALWAYS carries a `reason`
    — a bare `False` is indistinguishable from a check that never ran (NF1.7 (a)). Never raises:
    a report must degrade, not crash, because this is presentation and not a gate.
    """
    scores = _scores_of(table_rows, metric)
    leader_learner = leader_arm.partition(separator)[2]
    same_learner_ref = f"{incumbent_variant}{separator}{leader_learner}"
    inc, lead, ref = (scores.get(incumbent_arm), scores.get(leader_arm),
                      scores.get(same_learner_ref))

    if inc is None or lead is None:
        missing = [n for n, v in ((incumbent_arm, inc), (leader_arm, lead)) if v is None]
        return {"available": False,
                "reason": f"arm(s) absent from the scored table: {', '.join(missing)}"}

    sign = 1.0 if lower_is_better else -1.0
    total = sign * (inc - lead)
    if ref is None:
        return {
            "available": False,
            "reason": (f"no same-learner reference arm `{same_learner_ref}` — the leader's learner "
                       f"was never scored on the incumbent contract, so the margin CANNOT be split"),
            "total": round(total, 6),
            "same_learner_reference_arm": same_learner_ref,
        }

    learner = sign * (inc - ref)
    contract = sign * (ref - lead)
    share = (learner / total) if total else None
    floor = None if noise_floor is None else abs(float(noise_floor))
    meaningful = None if floor is None else bool(abs(total) > floor)
    out = {
        "available": True,
        "total": round(total, 6),
        "learner_swap": round(learner, 6),
        "contract": round(contract, 6),
        "learner_share": (round(share, 4) if share is not None else None),
        "same_learner_reference_arm": same_learner_ref,
        # ── MH1 additions (the legacy keys above are byte-preserved) ──
        "noise_floor": floor,
        "share_is_meaningful": meaningful,
        # opposite signs ⇒ the learner-fixed contract effect points the OTHER WAY to the headline.
        "sign_flip": bool(total != 0 and contract != 0 and (contract > 0) != (total > 0)),
        "learner_dominates": bool(share is not None and share >= 0.5),
        "components_within_noise": (
            None if floor is None
            else {"total": abs(total) <= floor, "learner_swap": abs(learner) <= floor,
                  "contract": abs(contract) <= floor}
        ),
    }
    return out


def variant_effect_by_learner(
    table_rows,
    metric: str,
    variants: Sequence[str],
    *,
    separator: str = ARM_SEPARATOR,
    incumbent_variant: str = INCUMBENT_VARIANT,
    lower_is_better: bool = True,
) -> list[dict]:
    """Per-learner effect of each contract variant vs the incumbent contract (+ = variant better).

    Holding the learner FIXED is the only way to read a FEATURE effect out of a
    `(contract × learner)` grid; the headline margin structurally cannot do it. Ordered by the
    learner's incumbent-contract score (best first).

    `variants` is passed EXPLICITLY rather than discovered from the arm names: a table that happens
    to be missing an arm would otherwise silently drop a whole column, and a column that vanishes
    when its data is thin is the report-shape equivalent of a guard that cannot fail.
    """
    if isinstance(table_rows, Mapping):
        scores = {str(k): float(v) for k, v in table_rows.items()}
        learners = sorted({a.partition(separator)[2] for a in scores})
    else:
        key = f"{metric}_mean"
        scores = {r["arm"]: float(r[key]) for r in table_rows}
        learners = sorted({r["learner"] for r in table_rows
                           if r.get("learner") and r["learner"] != "-"})
    sign = 1.0 if lower_is_better else -1.0
    out = []
    for lrn in learners:
        base = scores.get(f"{incumbent_variant}{separator}{lrn}")
        if base is None:
            continue
        row = {"learner": lrn, "incumbent": round(base, 4)}
        for v in variants:
            x = scores.get(f"{v}{separator}{lrn}")
            row[v] = round(sign * (base - x), 4) if x is not None else None
        out.append(row)
    return sorted(out, key=lambda r: r["incumbent"])


def render_margin_attribution_md(
    decomp: Mapping,
    *,
    metric: str,
    leader_arm: str,
    incumbent_arm: str,
    heading: str = "## ⚠️ Margin attribution — learner swap vs contract",
    separator: str = ARM_SEPARATOR,
) -> list[str]:
    """The shared markdown block. ONE renderer so every vertical's report says the same thing.

    Emitted on EVERY report — including the ones where the decomposition cannot act, which print
    the NAMED reason. A report that is silent about attribution is indistinguishable from one where
    attribution was checked and found clean.
    """
    a: list[str] = [heading, ""]
    if not decomp.get("available"):
        a += [f"_Not available — {decomp.get('reason', 'reason not recorded')}._", ""]
        if decomp.get("total") is not None:
            a += [f"Reported margin (undecomposed): `{decomp['total']:+.4f}` {metric}.", ""]
        return a

    total, learner, contract = decomp["total"], decomp["learner_swap"], decomp["contract"]
    share, meaningful = decomp.get("learner_share"), decomp.get("share_is_meaningful")
    show_share = share is not None and meaningful is not False
    leader_learner = leader_arm.partition(separator)[2] or leader_arm

    a += [
        f"The gate compares `{leader_arm}` against `{incumbent_arm}`, where an arm is "
        f"(contract variant × learner class). That is the right PROMOTION question and the gate is "
        f"unchanged — but it CONFLATES the feature effect with a learner-class swap. Split against "
        f"`{decomp['same_learner_reference_arm']}` (the incumbent contract under the LEADER's "
        f"learner), + = better:",
        "",
        f"| component | Δ {metric} | share of margin |",
        "|---|---:|---:|",
        f"| **learner swap** (→ `{leader_learner}`) | {learner:+.4f} | "
        + (f"{share:.0%} |" if show_share else "— |"),
        f"| **contract** (the features this study is about) | {contract:+.4f} | "
        + (f"{1 - share:.0%} |" if show_share else "— |"),
        f"| **total reported margin** | {total:+.4f} | " + ("100% |" if show_share else "— |"),
        "",
    ]

    if decomp.get("sign_flip"):
        a += [f"🚩🚩 **SIGN FLIP — holding the learner fixed, the contract is WORSE, not better** "
              f"(`{contract:+.4f}`). The reported `{total:+.4f}` is a learner-class effect that "
              f"more than covers a contract effect pointing the other way. Do NOT read this "
              f"margin as evidence for the features.", ""]
    elif show_share and share >= 0.5:
        a += [f"🚩 **{share:.0%} of this margin is the LEARNER SWAP, not the features.** What the "
              f"contract bought is `{contract:+.4f}`, not `{total:+.4f}`.", ""]

    if meaningful is False:
        a += [f"⚠️ **The share is not a reliable proportion here:** the total margin "
              f"(`{abs(total):.4f}`) is inside this metric's noise floor "
              f"(`{decomp['noise_floor']}`), so the ratio divides by a quantity the gate itself "
              f"treats as noise. Read the ABSOLUTE components, not the percentages.", ""]
    return a
