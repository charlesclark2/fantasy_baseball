"""rookie_point_scaling.py — NF-D15 pure model logic: the AVAILABILITY-SCALED rookie POINT projection.

WHY THIS STORY EXISTS. NF-D14 fitted a rookie AVAILABILITY prior (a predictive distribution over
rookie-season GAMES PLAYED) to widen the rookie-QB *interval*, and recorded a clean null on that
question. On the way past, OUTSIDE its pre-registered scope, it measured what happens if you scale the
rookie POINT projection by that prior's expected-games ratio (§6 of its report):

    position   MAE base   MAE availability-scaled     bias base   bias scaled
    QB           50.15            58.56                 -10.66      +11.36
    RB           46.40            42.86                 -19.69      -15.97
    TE           31.24            30.05                 -16.01      -14.27
    WR           44.01            41.92                 -23.82      -19.98

NF-D14 DECLINED it, correctly and twice over: the change is a POINT change while NF-D14's gate was the
INTERVAL, and it BREAKS QB (+16.8% MAE, bias flipping from −10.7 COLD to +11.4 HOT) because a rookie
QB's expected playing time already varies enormously with draft capital — the slot curve prices that
once and the availability ratio prices it a second time. Selecting it there would have been scope creep
dressed as a finding. This module is the honest home for the RB/TE/WR half, with the RIGHT gate.

────────────────────────────────────────────────────────────────────────────────────────────────────
⛔ QB IS EXCLUDED BY PRE-REGISTRATION, AND THE EXCLUSION IS ENFORCED IN ONE PLACE
────────────────────────────────────────────────────────────────────────────────────────────────────
`apply_position_scale` is the ONLY place a scale reaches a point projection, and it passes any position
outside `SCALED_POSITIONS` through UNCHANGED — so no arm, degenerate or oracle included, can quietly
re-open the QB question by construction rather than by discipline. The double-pricing at QB is a
MEASURED result from NF-D14, not a hypothesis, and this story does not re-litigate it.

────────────────────────────────────────────────────────────────────────────────────────────────────
⭐ THE ONE CONTROL THE WHOLE STORY TURNS ON — THE MATCHED FOIL (CLAUDE.md / NF-D10)
────────────────────────────────────────────────────────────────────────────────────────────────────
NF-D14's own explanation of the RB/TE/WR lift is that "the ratio is not a haircut: it exceeds 1 for
high-capital rookies, so it partially corrects the COLD bias NF1.4 documented." Read carefully, that
sentence does not describe an availability effect at all — it describes a LEVEL correction. A single
per-position constant would deliver the same level correction, with ZERO per-player information and
ZERO ordering risk.

So every availability arm is registered BESIDE the IDENTICAL arm with the per-player content stripped
out — `mean_ratio`, the same base ratio replaced by its own in-fold per-position MEAN. The PAIRED delta
between them is the availability content; the rank on a leaderboard is not (NF-D10: "a leaderboard rank
alone confuses 'my feature is inert' with 'my feature is in a tie'"). If `mean_ratio` matches the
availability arm, the honest verdict is "the lift is a recalibration, and availability earned none of
it" — which is a NULL for this story and a recorded lead for a different one.

────────────────────────────────────────────────────────────────────────────────────────────────────
PRE-REGISTERED SCALE FORMS (≥3 classes + a direct-learned foil + the incumbent, per §0.5)
────────────────────────────────────────────────────────────────────────────────────────────────────
  • `incumbent`      — THE NULL. Scale ≡ 1: the shipped rookie point, untouched. In the field, and it
                       can win.
  • `ratio_pos`      — NF-D14 §6 VERBATIM: `k = E[games] / (the position's in-fold mean games)`. Its
                       λ=1 arm must REPRODUCE NF-D14's §6 numbers, which is this harness's wiring
                       proof (`reproduces_nf_d14_section6`).
  • `ratio_slot`     — `k = E[games] / (the games the SLOT CURVE itself already assumed)`. The point
                       projection is not agnostic about playing time — `project_rookies` carries a
                       `proj_games` read straight off `curve.games_by_pos_slot`. Scaling relative to
                       what the point ALREADY assumes is the first honest answer to the double-pricing
                       that broke QB.
  • `ratio_residual` — `k = E[games | capital + depth] / E[games | capital]`. The second, sharper
                       answer: the slot curve prices DRAFT CAPITAL, so the only availability content
                       it cannot already contain is the increment the DEPTH CHART adds ON TOP of
                       capital. This arm carries exactly that increment and nothing else.
  • `learned_scale`  — THE DIRECT-LEARNED FOIL: a shallow GBM fitted in-fold on the realized
                       multiplicative correction `log1p(realized) − log1p(point)` over the SAME
                       availability features. It differs from the prescribed ratios ONLY in the
                       functional form of the correction, so a win is attributable to the learner.
  • `mean_ratio[·]`  — the MATCHED FOIL for each ratio base (above). Not an availability arm.

Each non-null form × a SHRINK grid λ. The shrink is GEOMETRIC (`k**λ`) so that **λ = 0 reproduces the
incumbent EXACTLY** (asserted in the tests) — the same honesty NF-D14's `blend` grid has: the knob's
zero end IS the null rather than something that merely resembles it.

────────────────────────────────────────────────────────────────────────────────────────────────────
📏 SELECTION METRIC — NF1.4's `tier_mae`, INHERITED RATHER THAN CHOSEN
────────────────────────────────────────────────────────────────────────────────────────────────────
The incumbent rookie point was selected on NF1.4's `tier_mae` — the draftable-tier MAE, on a tier FIXED
by the incumbent's own projection (NF1.1's fixed-anchor rule, so no candidate can buy a friendlier
subset). NF-D15 changes that same product, so it is scored on that same metric. Picking a *different*
metric to grade a change to an already-selected product is metric-shopping, and it is exactly how a
"lift" gets manufactured.

⚠️ NF-D14's headline for this lead is a UNIVERSE MAE (all ~75 drafted rookies a class). That number is
REPORTED here in full — it is the bridge back to NF-D14's §6 and the harness's wiring proof — but it
does not select. The universe read is dominated by late-round rookies nobody drafts; the product is a
draft board.

⚠️ TWO-SIDED ANCHORS, EVERY RUN, NEVER REASONED ABOUT (CLAUDE.md E2.1-r (b)/(c), NF-D11, NF-D14):
  · `oracle_perplayer` — peeking at full resolution (`k = realized/point`). Scores ~0; nothing may beat
                         it. A DIRECTION check for an accidentally-inverted metric.
  · `oracle_posconst`  — peeking at the MATCHED FAMILY of `mean_ratio` (the held-out class's OWN
                         per-position mean correction). The floor that is well-posed against a constant
                         arm; an honest PER-PLAYER arm may legitimately beat it (NF1.7 (b) / NF1.9 (f):
                         a peeking oracle is a floor only at matched family AND matched resolution).
  · `permuted`         — the availability prior fitted on SHUFFLED training games. Same family, same n;
                         only the information moves. Well-posed at ANY n, and therefore the anchor that
                         actually does the work here.
  · `zero_scale`       — DEGENERATE CEILING: k = 0, "project nothing for every rookie."
  · `pos_median`       — DEGENERATE CEILING: NF1.4's MAE-collapse tell (the in-fold position median for
                         everyone). MAE is minimised at the conditional median, so this is the arm that
                         WINS an inverted metric.
⭐ The degenerates are SCORED AND READ every run rather than argued about — NF-D14's own refinement of
the NF-D11 landmine ("'zero-heavy' is not the test; the conditional MEDIAN being at the floor is") is
precisely a reminder that reasoning about whether a metric will invert is not a substitute for scoring
the arm that would win it if it did.

────────────────────────────────────────────────────────────────────────────────────────────────────
🚧 DO-NO-ORDERING-HARM — THE CONSTRAINT THAT MAKES AN MAE WIN MEAN SOMETHING
────────────────────────────────────────────────────────────────────────────────────────────────────
A multiplicative per-player scale REORDERS the board within a position. A point-MAE win that scrambles
the draft order is a loss for a draft-board product, so the winner must also keep each scaled
position's within-position Spearman ρ within `ORDERING_DO_NO_HARM` of the incumbent's — NF1.4's own
constant, inherited verbatim so the bar is not re-negotiated for the story that needs it.

⭐ CHECKED PER POSITION, NEVER AS A POOLED MEAN. NF1.8's lesson one axis over: a pooled ρ can sit flat
while a single position's ordering collapses, and the pooled mean is the exact statistic that hides it.
An UNSCORABLE ρ for a candidate at a position the incumbent scores is a FAILURE, never a skip — an
absent measurement passes on nothing (NF1.7 anchor lesson (a)).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy.nf1_4_rookie import (
    ORDERING_DO_NO_HARM,
    SELECTION_METRIC,
    TIER_K,
)

MODEL_VERSION = "nfl_fantasy_nf_d15_rookie_point_scaling_v1"

# ⛔ The pre-registered scope. QB is EXCLUDED — NF-D14 measured the double-pricing (+16.8% MAE, bias
#    −10.66 → +11.36) and this story does not re-open it. Enforced in `apply_position_scale`.
SCALED_POSITIONS = ("RB", "TE", "WR")
EXCLUDED_POSITIONS = ("QB",)

# The NF-D14 leg-1 winner, REUSED not refitted (the story's step 0). Held here as the expected identity
# so `require_reused_prior` can refuse to run against a different signal than the one this story is
# built on — a silent substitution would make every number in the report about a prior nobody selected.
NF_D14_PRIOR = {"form": "tier_empirical", "tier": "depth", "blocks": ("capital",), "blend": 1.0}
# The CAPITAL-ONLY sibling, same family. It is not a candidate — it exists solely as the DENOMINATOR of
# `ratio_residual`, i.e. "the availability draft capital alone already implies", so that arm can carry
# the depth-chart increment and nothing the slot curve has already priced.
NF_D14_CAPITAL_SIBLING = {"form": "tier_empirical", "tier": "round", "blocks": ("capital",),
                          "blend": 1.0}

# Deflation gates. PBO/FDR inherited from NF1.1/NF1.4 so this search is held to the program's bar; DSR
# is NF-D14's own stricter level, carried forward deliberately — the availability signal this story
# consumes is the one that failed exactly that gate in NF-D14, so relaxing it here would be shopping
# for a bar the signal can clear.
PBO_MAX = 0.2
DSR_MIN = 0.95
FDR_Q = 0.10

# The shrink grid. GEOMETRIC in the scale, so λ = 0 IS the incumbent exactly.
SHRINK_GRID = (0.25, 0.5, 0.75, 1.0)
RATIO_BASES = ("ratio_pos", "ratio_slot", "ratio_residual")

# A scale is clipped into this band before it is applied. Not a tuning knob — a physical bound: the
# availability ratio is an expected-games ratio, and a rookie cannot play negative games or more than
# the season. The UPPER clip is what stops a single tiny in-fold denominator (a thin position × tier
# cell) from emitting a 40× scale that would dominate a whole position's MAE.
SCALE_CLIP = (0.0, 3.0)

# Forms that exist to CHARACTERISE the metric or to bound it — never to ship.
NON_SHIPPABLE = ("zero_scale", "pos_median", "oracle_perplayer", "oracle_posconst", "permuted")
# Families that carry PER-PLAYER availability information. `mean_ratio` deliberately does not: it is
# the matched foil, and a selection that lands on it is a NULL for this story (see the module docstring).
AVAILABILITY_FAMILIES = ("ratio", "learned")

__all__ = [
    "MODEL_VERSION", "SCALED_POSITIONS", "EXCLUDED_POSITIONS", "NF_D14_PRIOR",
    "NF_D14_CAPITAL_SIBLING", "PBO_MAX", "DSR_MIN", "FDR_Q", "SHRINK_GRID", "RATIO_BASES",
    "SCALE_CLIP", "NON_SHIPPABLE", "AVAILABILITY_FAMILIES", "SELECTION_METRIC",
    "ORDERING_DO_NO_HARM", "TIER_K", "SCALED_TIER_K",
    "apply_position_scale", "shrink_scale", "safe_ratio", "position_mean_scale",
    "candidate_configs", "config_key", "require_reused_prior", "require_anchors",
    "ordering_check", "per_position_ship", "point_scaling_verdict",
    "reproduces_nf_d14_section6",
]

# The draftable tier, restricted to the positions this story may touch. QB's tier is IDENTICAL across
# every arm by construction, so carrying it into the selection metric would only dilute the contest
# with a constant. It stays in the REPORTED full read.
SCALED_TIER_K = {p: k for p, k in TIER_K.items() if p in SCALED_POSITIONS}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The scale primitives
# ══════════════════════════════════════════════════════════════════════════════════════════════
def apply_position_scale(point, positions, scale, *,
                         scaled_positions: tuple = SCALED_POSITIONS,
                         clip: tuple = SCALE_CLIP) -> np.ndarray:
    """⛔ THE SINGLE GATE BETWEEN A SCALE AND A POINT PROJECTION — and the ONLY place the QB exclusion
    lives.

    Any position outside `scaled_positions` is returned UNCHANGED, whatever the arm asked for. That
    makes "QB is excluded" a property of the code rather than of every arm remembering to honour it,
    which matters because the anchors (`zero_scale`, the oracles) are exactly the arms most likely to
    be written without the exclusion in mind — and an oracle that silently scaled QB would be scoring a
    different question than every candidate.

    A non-finite scale falls back to 1.0 (the incumbent). A NaN scale must never blank a rookie off the
    board: the honest degradation of "I have no availability read for this player" is "leave his
    projection alone", not "project him at zero"."""
    p = np.asarray(point, dtype=float)
    k = np.asarray(scale, dtype=float).astype(float, copy=True)
    k = np.where(np.isfinite(k), k, 1.0)
    k = np.clip(k, clip[0], clip[1])
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    k = np.where(np.isin(pos, tuple(scaled_positions)), k, 1.0)
    return p * k


def shrink_scale(scale, lam: float) -> np.ndarray:
    """GEOMETRIC shrink of a multiplicative scale toward 1: `k ** λ`.

    ⭐ `λ = 0` reproduces the incumbent EXACTLY (`k**0 == 1`), which is what makes the grid an honest
    shrink toward "no availability information" rather than a knob that quietly changes shape at its
    zero end. Geometric rather than linear because the quantity is multiplicative: halving the strength
    of a 2× scale should give 1.41×, not 1.5× — and unlike the linear form, the geometric one cannot
    turn a scale below 1 into one above it for any λ ≥ 0.

    A scale of exactly 0 stays 0 for every λ > 0 (the `zero_scale` degenerate does not get shrunk into
    respectability), and λ = 0 sends even that to 1, as it must."""
    lam = float(lam)
    k = np.asarray(scale, dtype=float)
    if lam == 0.0:
        return np.ones_like(k)
    return np.power(np.clip(k, 0.0, None), lam)


def safe_ratio(numer, denom, *, min_denom: float = 0.25) -> np.ndarray:
    """`numer / denom` with a FLOOR on the denominator, returning NaN (⇒ the incumbent, via
    `apply_position_scale`) where the denominator is missing or implausibly small.

    ⚠️ The floor is load-bearing rather than defensive. Both denominators in this story are expected
    GAMES read off a thin in-fold cell — a position × depth-tier cell can hold a handful of rookies —
    and one 0.1-game denominator emits a 100× scale that would single-handedly decide a position's
    MAE. A silently-huge scale from a thin cell is a fitting artefact, not an availability signal."""
    n = np.asarray(numer, dtype=float)
    d = np.asarray(denom, dtype=float)
    out = np.full(len(n), np.nan)
    ok = np.isfinite(n) & np.isfinite(d) & (d >= float(min_denom))
    out[ok] = n[ok] / d[ok]
    return out


def position_mean_scale(scale, positions, *, scaled_positions: tuple = SCALED_POSITIONS
                        ) -> np.ndarray:
    """⭐ THE MATCHED FOIL (NF-D10) — the same scale with its PER-PLAYER content removed, replaced by
    its own per-position mean.

    This is the arm that decides whether NF-D15 has found an availability effect or a recalibration.
    It delivers the IDENTICAL average level correction as its partner arm, carries ZERO per-player
    information, and does ZERO ordering harm by construction. The paired delta against its partner is
    the availability content; the leaderboard rank is not (a rank cannot tell "my feature is inert"
    from "my feature is in a tie").

    A position whose scale is entirely non-finite gets 1.0 — the incumbent — rather than NaN, so the
    foil is always scorable and its check can never pass vacuously."""
    k = np.asarray(scale, dtype=float)
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    out = np.ones(len(k))
    for p in scaled_positions:
        sel = pos == p
        if not sel.any():
            continue
        v = k[sel]
        v = v[np.isfinite(v)]
        out[sel] = float(np.mean(v)) if len(v) else 1.0
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered search grid (EVERY config counts toward PBO/DSR — §0.5)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def candidate_configs(*, smoke: bool = False) -> list[dict]:
    """The full pre-registered candidate list, fixed before any result was read.

    Every availability arm is emitted BESIDE its matched `mean_ratio` foil at the SAME λ, because the
    pairing is the story's attribution instrument and a pair that only exists at some λ would let the
    comparison be made at whichever λ flattered it."""
    cfgs: list[dict] = [{"label": "incumbent (NULL)", "family": "incumbent", "base": None,
                         "lam": 0.0, "uses_availability": False, "shippable": True}]
    lams = (1.0,) if smoke else SHRINK_GRID
    bases = RATIO_BASES[:1] if smoke else RATIO_BASES
    for base in tuple(bases) + ("learned",):
        short = base.replace("ratio_", "")
        family = "learned" if base == "learned" else "ratio"
        name = "learned scale" if base == "learned" else f"avail ratio[{short}]"
        for lam in lams:
            cfgs.append({"label": f"{name} · λ {lam:g}", "family": family,
                         "base": base, "lam": lam, "uses_availability": True, "shippable": True})
            cfgs.append({"label": f"MATCHED FOIL mean[{short}] · λ {lam:g}", "family": "mean_ratio",
                         "base": base, "lam": lam, "uses_availability": False, "shippable": True})
    return cfgs


def config_key(cfg: dict) -> str:
    return f"{cfg['family']}[{cfg.get('base') or '-'}]@{float(cfg.get('lam', 0.0)):g}"


def require_reused_prior(cfg: dict, expected: dict = NF_D14_PRIOR) -> None:
    """⭐ THE REUSE IS ASSERTED, NOT ASSUMED (the story's step 0).

    NF-D15 consumes NF-D14's fitted availability signal and does NOT re-select it. The winner is read
    back out of NF-D14's own artifact rather than re-derived, so this guard exists to catch the case
    where that artifact has been regenerated with a DIFFERENT leg-1 winner: every number in this
    report would then be about a prior nobody selected, and nothing else in the harness would notice.
    Loud and early beats subtly wrong."""
    got = {k: (tuple(cfg.get(k)) if k == "blocks" else cfg.get(k)) for k in expected}
    want = {k: (tuple(v) if k == "blocks" else v) for k, v in expected.items()}
    if got != want:
        raise SystemExit(
            f"NF-D15 reuses NF-D14's leg-1 winner {want} but the artifact carries {got}. This story "
            "does NOT refit the availability prior — re-run NF-D14 or fix the artifact before "
            "reading any NF-D15 selection.")


_REQUIRED_ANCHORS = ("oracle_perplayer", "oracle_posconst", "permuted", "zero_scale", "pos_median")


def require_anchors(scored: dict, required: tuple = _REQUIRED_ANCHORS) -> None:
    """⭐ A MISSING ANCHOR IS A HARD FAILURE, NEVER A PASS (NF1.7 anchor lesson (a)).

    An anchor that fails to fit makes its own check VACUOUSLY TRUE — `winner < anchor` on an absent
    anchor compares nothing and reports green. NF1.7 shipped exactly that bug once; every anchored
    story since has carried this guard, and it is a function rather than an inline `if` so it is
    unit-testable without running the bake-off."""
    missing = [k for k in required
               if k not in scored or scored[k].get(SELECTION_METRIC) is None]
    if missing:
        raise SystemExit(
            f"the anchor(s) {missing} did not score — their checks would pass on NOTHING. Fix the "
            "anchor before reading any selection (NF1.7 anchor-set lesson 1).")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The do-no-ordering-harm constraint
# ══════════════════════════════════════════════════════════════════════════════════════════════
def ordering_check(candidate_rho: dict, incumbent_rho: dict, *,
                   positions: tuple = SCALED_POSITIONS,
                   tol: float = ORDERING_DO_NO_HARM) -> dict:
    """Within-position rank correlation, PER POSITION, against the incumbent.

    ⭐ PER POSITION AND NEVER A POOLED MEAN. The pooled ρ over four positions can sit flat while one
    position's ordering collapses — averaging is the exact operation that hides the failure this
    constraint exists to catch (NF1.8's "a per-group constraint cannot be a mean of per-class means",
    one axis over).

    ⚠️ An UNSCORABLE candidate ρ at a position the INCUMBENT scores is a FAILURE, not a skip. That is
    not pedantry: the way a scale arm loses its ρ is by going CONSTANT within a position (every rookie
    scaled onto the same number), which is precisely the collapse the constraint is for — treating it
    as "no measurement, carry on" would let the worst arm pass unexamined.

    `tol` is NF1.4's `ORDERING_DO_NO_HARM`, inherited verbatim. `strict_ok` reports the zero-tolerance
    reading beside it so a reader can see whether the tolerance is doing any work in this story's
    answer rather than having to take it on trust."""
    per: dict[str, dict] = {}
    ok = True
    strict_ok = True
    for p in positions:
        inc = incumbent_rho.get(p)
        cand = candidate_rho.get(p)
        if inc is None:
            per[p] = {"incumbent": None, "candidate": cand, "delta": None, "ok": True,
                      "note": "incumbent unscorable — nothing to protect"}
            continue
        if cand is None:
            per[p] = {"incumbent": round(float(inc), 4), "candidate": None, "delta": None,
                      "ok": False, "note": "candidate rho UNSCORABLE (constant within position?)"}
            ok = strict_ok = False
            continue
        delta = float(cand) - float(inc)
        good = delta >= -float(tol)
        per[p] = {"incumbent": round(float(inc), 4), "candidate": round(float(cand), 4),
                  "delta": round(delta, 4), "ok": bool(good)}
        ok = ok and good
        strict_ok = strict_ok and (delta >= 0.0)
    deltas = [v["delta"] for v in per.values() if v.get("delta") is not None]
    return {"ok": bool(ok), "strict_ok": bool(strict_ok), "per_position": per,
            "worst_delta": round(min(deltas), 4) if deltas else None,
            "tol": float(tol)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The verdict — per position, then overall
# ══════════════════════════════════════════════════════════════════════════════════════════════
def per_position_ship(*, position: str, winner: dict | None, incumbent_metric: float | None,
                      ordering: dict, pbo: float | None, dsr: float | None,
                      fdr_survives: bool, pbo_max: float = PBO_MAX,
                      dsr_min: float = DSR_MIN) -> dict:
    """⭐ THE SHIP DECISION FOR ONE POSITION — and the reason the BH-FDR in this story is CONSUMED
    rather than merely computed.

    E7.12's landmine was a BH-FDR that was calculated, printed, and then never gated the emission — a
    computed-but-unconsumed statistic, the quiet cousin of the silent-empty class. Here `fdr_survives`
    is an argument to the decision, so a position that fails its multiplicity correction cannot receive
    the scaling no matter what its point estimate says.

    A position ships ONLY when its own selected arm (a) uses per-player availability — a `mean_ratio`
    win is a recalibration finding, not this story's claim; (b) beats the incumbent on the
    pre-registered metric; (c) does no ordering harm AT THIS POSITION; (d) clears PBO and DSR on its
    OWN search; and (e) survives BH-FDR across the three scaled positions."""
    uses = bool(winner and winner.get("uses_availability"))
    beats = bool(winner and incumbent_metric is not None
                 and winner.get("metric") is not None
                 and float(winner["metric"]) < float(incumbent_metric))
    checks = {
        "has_eligible_winner": winner is not None,
        "uses_availability": uses,
        "beats_incumbent": beats,
        "ordering_ok": bool(ordering.get("per_position", {}).get(position, {}).get("ok", False)),
        "pbo_ok": pbo is not None and pbo < pbo_max,
        "dsr_ok": dsr is not None and dsr >= dsr_min,
        "fdr_ok": bool(fdr_survives),
    }
    return {"position": position, "ship": all(checks.values()), **checks}


def point_scaling_verdict(*, positions_shipped: tuple, degenerates_lose: bool,
                          permutation_beaten: bool, oracle_respected: bool,
                          qb_untouched: bool) -> dict:
    """The STORY-level decision. It ships if at least one position cleared its own per-position gate
    AND the run's global sanity anchors all held.

    ⚠️ The anchors are STORY-level vetoes on purpose. A degenerate winning the metric, or the truth
    losing to its own permutation, does not mean "this position is unlucky" — it means the measurement
    is not trustworthy anywhere in the run, and no per-position result computed from it may be shipped.

    `qb_untouched` is the pre-registered scope assertion, measured on real emitted projections rather
    than asserted from the code: NF-D14 proved the QB double-pricing, and the one way this story could
    silently undo that finding is by letting a scale reach QB."""
    checks = {
        "any_position_ships": len(positions_shipped) > 0,
        "degenerates_lose": bool(degenerates_lose),
        "permutation_beaten": bool(permutation_beaten),
        "oracle_respected": bool(oracle_respected),
        "qb_untouched": bool(qb_untouched),
    }
    return {"ship": all(checks.values()), "positions_shipped": list(positions_shipped), **checks}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The wiring proof
# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF-D14 §6, transcribed. This is not decoration: NF-D15 rebuilds the same scale in a new harness, and
# the ONE cheap way to prove the rebuild is faithful is that its λ=1 `ratio_pos` arm reproduces the
# numbers NF-D14 published. A rebuild that quietly differs would make every comparison in this report
# a comparison with something else.
NF_D14_SECTION6 = {
    "QB": {"mae_base": 50.15, "mae_scaled": 58.56},
    "RB": {"mae_base": 46.40, "mae_scaled": 42.86},
    "TE": {"mae_base": 31.24, "mae_scaled": 30.05},
    "WR": {"mae_base": 44.01, "mae_scaled": 41.92},
}


def reproduces_nf_d14_section6(measured: dict, *, tol: float = 0.05,
                              positions: tuple = SCALED_POSITIONS) -> dict:
    """Does this harness's `ratio_pos · λ 1` arm reproduce NF-D14's §6 UNIVERSE MAE?

    Checked on the SCALED positions only — NF-D14 §6 scaled QB too (that is what it measured and
    declined), while NF-D15 cannot, by construction. So the QB row is expected to differ and is
    reported rather than checked; pretending otherwise would be a check that fails for the one reason
    the story is proud of.

    `measured` = {position: {"mae_base": …, "mae_scaled": …}}. Returns per-position deltas and a
    verdict; the caller reports it in the run header, where a wiring break is visible before any
    selection is read."""
    out: dict = {"tol": float(tol), "per_position": {}, "ok": True}
    for p in positions:
        want = NF_D14_SECTION6.get(p)
        got = (measured or {}).get(p)
        if not want or not got:
            out["per_position"][p] = {"ok": False, "note": "not measured"}
            out["ok"] = False
            continue
        rec = {}
        good = True
        for k in ("mae_base", "mae_scaled"):
            g, w = got.get(k), want[k]
            d = None if g is None else round(float(g) - float(w), 3)
            rec[k] = {"nf_d14": w, "nf_d15": None if g is None else round(float(g), 2), "delta": d}
            good = good and d is not None and abs(d) <= tol
        rec["ok"] = good
        out["per_position"][p] = rec
        out["ok"] = out["ok"] and good
    return out


def scaled_positions_only(frame: pd.DataFrame, *, positions: tuple = SCALED_POSITIONS
                          ) -> pd.DataFrame:
    """The rows this story is allowed to have an opinion about."""
    return frame[frame["position_group"].astype(str).str.upper().isin(positions)]
