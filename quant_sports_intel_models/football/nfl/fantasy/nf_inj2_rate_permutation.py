"""nf_inj2_rate_permutation.py — NF-INJ2: permute the per-game RATE, not the season POINT.

⭐ READ `ablation_results/nf_inj1_preregistration.md` FIRST. It is THIS story's pre-registration,
committed during NF-INJ1 before any arm was scored and funded by the PM on 2026-08-21. ⛔ Editing it
after a result is not a pre-registration (E2.1-r); anything the decisive run overturns is left in
place under a `SUPERSEDED` marker, verbatim (NF-W7f).

────────────────────────────────────────────────────────────────────────────────────────────────
THE DEFECT THIS EXISTS TO REMOVE
────────────────────────────────────────────────────────────────────────────────────────────────
MVP-1's season point is `per-game rate × expected games`, so it EMBEDS availability:

    season[s] = shrunk_per_game_rate[s] * proj_games          # coherent BY CONSTRUCTION

NF1.5's ordering step then hands each veteran a DIFFERENT player's season point from the position's
own multiset and rescales his twelve counting stats to reach it — while `proj_games` stays exactly
where MVP-1 left it (`nf1_model._RAW_SCALE_COLS` enumerates the stats and omits the games). Permuting
a composite quantity redistributes EVERY factor inside it, so the availability discount moves between
players (NF-INJ1 §6). Measured on the live board:

  · ρ(proj_games, point ratio) = **−0.213** (p = 1.4e-08, n = 697) — a systematic transfer of point
    level from high-availability players to low-availability ones;
  · on the 23-row injury-capped cohort, **+36.4% of the availability discount handed back**
    (median point ratio 1.292; 18 of 23 scaled UP — Higgins ×2.32, Guerendo ×1.81, Pierce ×1.67,
    Kittle ×1.29), i.e. **the founding injury priority running backwards**;
  · 10 served rows are PHYSICALLY IMPOSSIBLE at their own `g` (Easton Stick: 153.4 pass attempts
    over 1.86 games = 82.7/game against an all-time realized maximum of 45.44).

────────────────────────────────────────────────────────────────────────────────────────────────
THE REFORMULATION
────────────────────────────────────────────────────────────────────────────────────────────────
Permute the per-game RATE multiset and re-multiply by each player's OWN games:

    incumbent      target_i = point_j                    (j = the learned-rank-matched player)
    rate_permute   target_i = (point_j / games_j) * games_i

`games_i` never leaves row `i`, so availability stops being a permutable quantity and the served
pair (line, games) stays a real player's per-game rate at a real player's own availability.

⚠️ "COHERENT BY CONSTRUCTION" IS A CLAIM ABOUT THE *TRANSFER*, NOT A PROOF OF ZERO VIOLATIONS, AND
THIS MODULE DOES NOT ASSERT THE LATTER. The rescale factor becomes `r_j / r_i` — a ratio of two
per-game POINT rates, both O(1) within a position — instead of `p_j / p_i`, which silently carries the
games ratio `g_i / g_j` (up to ~20× on a roster holding a 17-game starter beside a 1-game QB3). That
bounds the transfer; it does not mathematically forbid a breach on a row whose stat-per-point mix is
itself extreme. NF-D16 (g‴) is explicit that "zero harm BY CONSTRUCTION" is the kind of sentence that
turns out to be false — so the violation count is MEASURED for every arm, on every fold, and reported.
Per the pre-registration it is a PRECONDITION, ⛔ never a discriminator between arms.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT THIS MODULE IS
────────────────────────────────────────────────────────────────────────────────────────────────
The pure target-assignment kernel for all six pre-registered arms plus the matched foil, and the
serving POLICY flag. It imports nothing from the projection stack except the envelope constants, so
it can be unit-tested without a DuckDB, and `nf1_model.apply_learned_ordering` delegates to it —
ONE implementation, so the arm the bake-off scored and the arm the board would serve cannot drift
(the NF-C0e "a study that re-derives the shipped logic measures something else" lesson).
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import projection_coherence as PC

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered field (nf_inj1_preregistration.md §2) — DECLARED FORWARD
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: the primary arm.
PRIMARY_ARM = "rate_permute"

#: the thing to beat.
INCUMBENT_ARM = "incumbent"

#: pre-registered DEGENERATES — they MUST lose. Declared here, before any score, so the DSR-CONV
#: convention (degenerate ∈ n_trials, ∉ V) is a property of the registration and not of the result
#: (⛔ declaring an arm degenerate after seeing it lose is laundering — CLAUDE.md DSR-CONV).
DEGENERATE_ARMS: tuple[str, ...] = ("mvp1_null", "random_order")

#: the six declared arms. `declared_field_size = 6` is what `cv_power.classify_null` is told.
ARMS: tuple[str, ...] = (
    "incumbent",          # today's season-POINT multiset permutation
    "rate_permute",       # PRIMARY — permute the per-game RATE multiset, × the row's own games
    "stratified",         # permute the POINT multiset within availability (games-tercile) strata
    "feasibility_clamp",  # incumbent, with the rescale bounded by the physical envelope
    "mvp1_null",          # DEGENERATE — no re-order at all
    "random_order",       # DEGENERATE — a seeded within-position random permutation
)
DECLARED_FIELD_SIZE = len(ARMS)

#: the NF-D15 (g′) matched foil: identical machinery, the per-player availability channel REMOVED.
#: If `rate_permute` beats the incumbent and this does not, the lift is the per-player availability
#: channel — the stated mechanism. If both win equally, the mechanism claim is REFUTED and the win
#: is a level effect.
MATCHED_FOIL = "rate_permute_games_frozen"

#: every arm the harness scores (the declared field + the matched foil).
ALL_ARMS: tuple[str, ...] = ARMS + (MATCHED_FOIL,)

#: seeds are fixed in the registration so `random_order` is reproducible to the last digit.
RANDOM_ORDER_SEED = 20260821

#: `stratified`'s availability strata — TERCILES of `proj_games` within each position. Three is the
#: registered choice: it is the coarsest split that still separates "barely plays" from "starter",
#: and a finer grid would shrink each stratum toward a no-op (a permutation inside a stratum of one
#: is the identity), which would make the arm converge on `mvp1_null` for reasons of arithmetic
#: rather than of evidence.
STRATIFIED_N_STRATA = 3

#: a hard floor on the games divisor. It exists so a degenerate row can never produce an infinite
#: rate — NOT as a tuning knob. It is MEASURED to be inert: the minimum `proj_games` is 0.795 on the
#: 2026 board (794 rows) and 0.8145 across the 11,885-row 2007–2025 veteran panel, i.e. ~3× the floor,
#: and `games_floor_binding()` reports the count so "inert" stays a measurement rather than a
#: comment — counting `games_floored_mask()`, the same predicate the kernel applies (PLAT-CVP2 d4).
GAMES_FLOOR = 0.25


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The physical-feasibility bound (the `feasibility_clamp` arm)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def max_feasible_scale(line: pd.DataFrame, positions, games, *,
                       envelope: Mapping[str, Mapping[str, float]] | None = None) -> np.ndarray:
    """The largest whole-line rescale that keeps EVERY counting stat inside `REALIZED_MAX_PER_GAME`.

    For stat `x` the served per-game rate after a rescale `s` is `x_i · s / g_i`, so the binding
    bound is `s ≤ min_x (env[pos][x] · g_i / x_i)`. A row with no positive stat, an unknown position,
    or a non-finite games value is UNBOUNDED (`+inf`) rather than refused — the envelope is a MAX
    over twenty seasons of realized football, so a row it cannot speak to must not be silently
    clamped by it (NF1.7 (a): an unevaluable check is not a finding in either direction)."""
    env = PC.REALIZED_MAX_PER_GAME if envelope is None else envelope
    pos = np.array([str(p or "").upper() for p in pd.Series(positions).reset_index(drop=True)],
                   dtype=object)
    g = pd.to_numeric(pd.Series(games).reset_index(drop=True), errors="coerce").to_numpy(dtype=float)
    out = np.full(len(pos), np.inf, dtype=float)
    for field, col in PC.PARQUET_FIELD.items():
        if col not in line.columns:
            continue
        x = pd.to_numeric(line[col], errors="coerce").to_numpy(dtype=float)
        cap = np.array([float(env.get(p, {}).get(field, np.inf)) for p in pos], dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            bound = np.where((x > 1e-9) & np.isfinite(g) & (g > 0.0) & np.isfinite(cap),
                             cap * g / np.where(x > 1e-9, x, 1.0), np.inf)
        out = np.minimum(out, np.where(np.isfinite(bound), bound, np.inf))
    return out


def games_floored_mask(games) -> np.ndarray:
    """⭐ **THE ONE PREDICATE — "which rows does the `GAMES_FLOOR` actually MOVE?"** — read by the
    kernel that applies the floor AND by every census that reports it.

    **PLAT-CVP2 defect 4 (NF-INJ2c §6.3).** These were two predicates. `games_floor_binding()`
    counted `isfinite(g) & (g < FLOOR)`; the kernel substituted on `~(isfinite(g) & (g > FLOOR))`.
    They agree on a healthy column and diverge on a NON-FINITE row — which the kernel floors and the
    census could not see. Nothing was mis-scored (measured inert on every fold of every arm), but a
    census that cannot see one of the two ways its own mechanism acts cannot support the claim it is
    printed to support: "the floor is inert" would have been read off the narrower of two counts
    (NF1.7 (a)). A defect corrected at the point of reading is a defect in the instrument (MH2.7), so
    there is now one predicate with one owner.

    ⭐ THE DEFINITION IS BY **VALUE**, NOT BY BRANCH, and that choice is NF-INJ2c's, kept: a row at
    exactly `g == FLOOR` takes the kernel's substitution branch but is substituted with `FLOOR`, so
    its divisor does not move and it cannot make the assignment and the check disagree. Counting it
    would answer a question about control flow instead of the hypothesis's question — did the
    divisor change? Hence `~isfinite(g) | (g < FLOOR)`, which is exactly `gsafe != g`.

    The kernel's output is UNCHANGED to the last bit: `np.where(mask, FLOOR, g)` and the previous
    `np.where(isfinite(g) & (g > FLOOR), g, FLOOR)` agree on every input, the boundary row included
    (both yield `FLOOR`, which is what it already held)."""
    g = pd.to_numeric(pd.Series(games), errors="coerce").to_numpy(dtype=float)
    return ~np.isfinite(g) | (g < GAMES_FLOOR)


def games_floor_binding(games) -> int:
    """How many rows the `GAMES_FLOOR` guard actually moved. Reported so "the floor is inert" is a
    measurement on this population, not a claim inherited from the docstring.

    ⭐ Counts `games_floored_mask()` — the SAME predicate the kernel applies (PLAT-CVP2 defect 4).
    It previously required `isfinite(g)` and so could not see a non-finite row the kernel floors."""
    return int(np.sum(games_floored_mask(games)))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The kernel — ONE function, every arm
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _order(score: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """The incumbent's own tie-break, reproduced EXACTLY: unscored rows sink, `kind="stable"` so a
    tie keeps frame order. Shared by every arm, so no arm can win on a different tie-break."""
    s = score[idx]
    s = np.where(np.isfinite(s), s, -np.inf)
    return idx[np.argsort(-s, kind="stable")]


def assign_targets(*, base, games, score, positions, eligible, arm: str,
                   learn_positions: Sequence[str], line: pd.DataFrame | None = None,
                   seed: int = RANDOM_ORDER_SEED,
                   rescale_lo: float = 0.30, rescale_hi: float = 3.5) -> np.ndarray:
    """The target season point each row is re-levelled to, under `arm`.

    `base` is the row's OWN MVP-1 scored season point (the multiset being permuted); `games` its
    `proj_games`; `score` the learned ordering score; `eligible` the NF1.5b mask restricting the
    permutation to rows the learner can speak to (an ineligible row keeps its MVP-1 point EXACTLY,
    under every arm — including the degenerates, so the arms differ in the permutation rule and in
    nothing else).

    Returns an array the caller hands to `nf1_model.apply_learned_level`. Pure and total: an
    unrecognised `arm` RAISES rather than silently falling through to the incumbent, because a typo
    that quietly scores the incumbent under another arm's name is the failure mode that would make
    this entire bake-off vacuous."""
    if arm not in ALL_ARMS:
        raise ValueError(f"unknown arm {arm!r} — the declared field is {ALL_ARMS}")
    b = np.asarray(base, dtype=float)
    g = pd.to_numeric(pd.Series(games).reset_index(drop=True), errors="coerce").to_numpy(dtype=float)
    s = np.asarray(score, dtype=float)
    pos = np.array([str(p or "").upper() for p in pd.Series(positions).reset_index(drop=True)],
                   dtype=object)
    elig = np.asarray(eligible, dtype=bool)
    target = b.copy()

    if arm == "mvp1_null":                       # DEGENERATE — no re-order at all
        return target

    if arm == "feasibility_clamp":
        if line is None:
            raise ValueError("feasibility_clamp needs the counting line to bound the rescale")

    rng = np.random.default_rng(seed)
    # ⭐ PLAT-CVP2 defect 4 — ONE predicate, shared with `games_floor_binding`. Byte-identical to
    # the previous `np.where(isfinite(g) & (g > GAMES_FLOOR), g, GAMES_FLOOR)` on every input.
    gsafe = np.where(games_floored_mask(g), GAMES_FLOOR, g)

    for p in learn_positions:
        idx = np.where((pos == p) & elig)[0]
        if len(idx) < 2:
            continue

        if arm == "random_order":                # DEGENERATE — a seeded random permutation
            target[rng.permutation(idx)] = np.sort(b[idx])[::-1]
            continue

        if arm == "stratified":
            # permute the POINT multiset only WITHIN availability strata, so a level is exchanged
            # only between players of comparable expected games. Terciles are taken on THIS
            # position's eligible rows; `pd.qcut` with `duplicates="drop"` degrades to fewer strata
            # on a degenerate games distribution rather than raising.
            try:
                strata = pd.qcut(g[idx], STRATIFIED_N_STRATA, labels=False, duplicates="drop")
            except (ValueError, IndexError):
                strata = np.zeros(len(idx), dtype=int)
            strata = np.asarray(pd.Series(strata).fillna(-1), dtype=int)
            for k in np.unique(strata):
                sub = idx[strata == k]
                if len(sub) < 2:
                    continue
                target[_order(s, sub)] = np.sort(b[sub])[::-1]
            continue

        order = _order(s, idx)

        if arm in ("rate_permute", MATCHED_FOIL):
            # ⭐ THE STORY. Permute the per-game RATE multiset, then re-multiply by the row's OWN
            # expected games — so `games_i` never leaves row `i` and availability is not permutable.
            # `order` holds this position's eligible rows, best learned score first — the SAME
            # line the incumbent uses. The only change is WHICH multiset is handed out along it.
            rate_desc = np.sort(b[idx] / gsafe[idx])[::-1]
            if arm == "rate_permute":
                multiplier = gsafe[order]          # ⭐ the row's OWN games — never permuted
            else:
                # THE MATCHED FOIL (NF-D15 g′): identical machinery, the per-player availability
                # channel REMOVED — every row re-multiplied by the POSITION's MEAN games. It keeps
                # the rate permutation and the level scale, and differs from the primary in exactly
                # one thing: whether `games` is the player's own.
                multiplier = np.full(len(order), float(np.nanmean(gsafe[idx])))
            target[order] = rate_desc * multiplier
            continue

        # `incumbent` and `feasibility_clamp` share the season-POINT permutation; the clamp differs
        # only in the BOUND applied downstream, which is returned separately by `feasible_hi`.
        target[order] = np.sort(b[idx])[::-1]

    return target


def feasible_hi(*, arm: str, line: pd.DataFrame | None, positions, games,
                rescale_hi: float = 3.5) -> np.ndarray | float:
    """The per-row upper rescale bound for `arm`.

    Only `feasibility_clamp` narrows it: `min(hi, max_feasible_scale)`, so the assigned level is
    reached where it is physically reachable and truncated exactly where it is not. Every other arm
    keeps the shipped scalar clamp — an arm must not get a quietly different clamp."""
    if arm != "feasibility_clamp":
        return rescale_hi
    if line is None:
        raise ValueError("feasibility_clamp needs the counting line to bound the rescale")
    return np.minimum(float(rescale_hi), max_feasible_scale(line, positions, games))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# SERVING POLICY — deploy-held until the PM records a disposition (NF-D21's shape)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: which arm the SHIPPED board serves. `nf1_model.apply_learned_ordering` defaults to this.
#: ⛔ NOT a free-form switch: `assert_coherent()` runs at import and refuses a state that would serve
#: an arm the gates did not clear, so a bare flag flip cannot ship a result the record does not
#: support (NF-D22's governance shape).
SERVED_ARM = "incumbent"

#: the §0.5 outcome. One of "UNRUN" | "CLEARED" | "CONSTRAINT_REFUSED" | "NULL", read by
#: `assert_coherent`.
#:
#: ⭐ IT IS PINNED TO THE COMMITTED REPORT, not maintained by hand. The first cut said it was
#: "written here by hand when the decisive run lands" — and it then shipped as `"UNRUN"` after the
#: decisive run had landed and been refused, i.e. the policy module claimed the study had never run.
#: Harmless that day (a non-incumbent `SERVED_ARM` is what makes `assert_coherent` read it, and the
#: board serves the incumbent), but it is exactly the documented-≠-actual class this repo keeps
#: paying for, and a hand-maintained flag with no consumer is the NF-C0e defect in miniature.
#: `test_the_recorded_gate_status_matches_the_committed_report` now fails if this and
#: `ablation_results/nf_inj2_rate_permutation.json`'s verdict disagree, so a re-run that changes the
#: verdict must change this in the SAME commit.
GATE_STATUS = "CONSTRAINT_REFUSED"

#: whether a PM has recorded a disposition to serve `PRIMARY_ARM`. Kept SEPARATE from `GATE_STATUS`
#: because clearing the gates and deciding to ship are different facts, and NF-D21/NF-D22 were both
#: burned by a record in which they had been collapsed into one flag.
PM_DISPOSITION_RECORDED = False


def assert_coherent() -> None:
    """Refuse a policy state the record does not support. Runs at IMPORT — a bare flag flip that
    would serve an uncleared arm fails the process that flipped it, rather than shipping."""
    if SERVED_ARM not in ALL_ARMS:
        raise RuntimeError(f"SERVED_ARM {SERVED_ARM!r} is not a declared arm")
    if SERVED_ARM in DEGENERATE_ARMS:
        raise RuntimeError(
            f"SERVED_ARM {SERVED_ARM!r} is a pre-registered DEGENERATE — it exists to LOSE")
    if SERVED_ARM != INCUMBENT_ARM:
        if GATE_STATUS != "CLEARED":
            raise RuntimeError(
                f"SERVED_ARM {SERVED_ARM!r} but GATE_STATUS={GATE_STATUS!r} — an arm may only be "
                "served once its §0.5 gates CLEARED (nf_inj1_preregistration.md §3/§4)")
        if not PM_DISPOSITION_RECORDED:
            raise RuntimeError(
                f"SERVED_ARM {SERVED_ARM!r} but no PM disposition is recorded — clearing the gates "
                "and deciding to ship are different facts")


assert_coherent()
