"""draft.py — sport-agnostic LIVE draft optimizer over a VOR board (NF-C2 / MVP-3).

Given a scored+ranked league board (the `vor.build_board` / `mart_nfl_fantasy_league_board` output),
plus the CURRENT draft state (who's been taken, who's on MY roster, my slot, the league's roster
requirements), recommend the value-maximizing pick(s). Three signals, all transparent:

  1. VOR              — value-over-replacement already encodes CROSS-position scarcity (the board's job).
  2. POSITIONAL NEED  — does adding this player fill one of MY still-open STARTER slots (dedicated OR
                        flex/superflex)? A player who plugs a hole is worth more to *me* than his raw VOR.
  3. VONA / TIER CLIFF— value-over-next-available at his position: how much value I lose at that position
                        if I pass now and wait. A big drop-off (the "tier cliff") is the grab-now signal.

The recommendation score is additive SEASON POINTS (never a multiplier — the base can be negative):

    score = seat_value + need_bonus - bye_pen
    need_bonus = NEED_W[level] * positional_dropoff    (level: open-dedicated > open-flex > none)

and NF-C7 adds ONE user control, which orders rather than scores: a per-position DEPTH TARGET moves
a short position up WITHIN the bench cohort, below every open starter slot (see the note there).

so the rationale writes itself ("VOR 122 + fills your open RB2, +38 drop-off to the next RB = 160").

⭐ `seat_value` IS THE SEAT THE PLAYER WOULD ACTUALLY OCCUPY, and there are three of them:

    open DEDICATED slot   his VOR                    — you must start a TE, so measure him vs TEs
    open FLEX seat        points over the SEAT's own replacement (NF-C2.1)
    BENCH (no open slot)  his INSURANCE value (NF-C7) — P(you need him) x his upgrade over the
                          next man up, over the weeks a starter is out or on bye

The third is NF-C7 and it replaced a flat "keep 15% of his VOR" discount. VOR is a STARTER-SCARCITY
currency and a bench seat is not a starter slot: measured over 120 paired drafts (NF-C-LDA-6), the
flat discount put 47% backup QB and 53% backup TE on the bench with ZERO RBs and ZERO WRs, while the
insurance rule captures 83% of a peeking oracle's headroom (+77.3 season points, 118/120 drafts).

Everything is pure (board rows in, recommendations out) and sport-neutral: positions, eligibility and
roster shape come only from the `LeagueConfig` — the identical algorithm powers the live TS client
(`frontend/lib/draft-optimizer.ts`); keep the two in lock-step. K/DST (or any position with no ranked
players) simply never surface as a candidate — handled by construction, never a crash.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from quant_sports_intel_models.fantasy_engine.league_config import LeagueConfig, draftable_slot_count

# Need weights (in VONA-points): a candidate that fills an OPEN DEDICATED starter slot gets the full
# positional drop-off as a bonus; one that only fills a FLEX/superflex spot gets a fraction; a position
# whose starter demand I've already met gets none (VOR alone ranks the pure-depth pick).
NEED_W_DEDICATED = 1.0
NEED_W_FLEX = 0.4
# ⭐⭐ NF-C7 — WHERE THE BENCH COHORT SITS, WHICH IS A DIFFERENT QUESTION FROM WHO IS IN IT.
#
# `SURPLUS_BASE + SURPLUS_OVER` (capped at `SURPLUS_CAP`) damped a bench candidate to 15% of his VOR.
# NF-C7 replaces it as a VALUATION — `bench_insurance_value` is a far better answer to "which bench
# player?" — but KEEPS it as the ORDERING term that places the bench cohort against the need-fillers,
# and that distinction is load-bearing:
#
#   * a NEED-FILLER's score is VOR — points over the FREELY-AVAILABLE alternative at his position,
#     i.e. over the player you would take instead if you waited;
#   * an INSURANCE value is points added to YOUR lineup, measured against the man you already hold.
#
# Different baselines, so putting insurance straight into the sort compares two different questions.
# MEASURED on the 41 committed parity states: doing that made bench depth outrank EVERY open-starter
# filler in 8 of the 23 states that have both — including a bench RB (55.6) beating an EMPTY QB1
# (12.9). Under the retired rule that happened in 1 of 8, by 0.3 points. An empty starter slot scores
# ZERO every week, so recommending depth over it is the failure the reserve constraint exists to
# stop, arriving several rounds before the constraint can act.
#
# ⭐ It is also the ONLY shape NF-C-LDA-6 measured: every arm there first asked the shipped engine
# what it would take and re-ranked only if that was a bench pick — "the arms never differ on WHETHER
# to take a bench player, only on WHICH". The +77.3 is a measurement OF THAT SHAPE.
#
# ⛔ NOT a valuation and NEVER displayed. It orders; `score` values. One constant (0.85, the product
# the three retired ones always evaluated to) so nobody re-tunes three knobs that only moved together.
# ⚠️ LOCK-STEP: `BENCH_ORDER_DAMPING` / `benchOrderValue` in `frontend/lib/draft-optimizer.ts`.
BENCH_ORDER_DAMPING = 0.85

#: ⭐⭐ NF-C7 — HOW FAR DOWN THE BOARD INSURANCE IS ALLOWED TO REACH, and it is the single most
#: consequential number in this file. MEASURED, not chosen.
#:
#: NF-C-LDA-6 scored its arms by asking the engine for its top 40 and re-ranking the BENCH candidates
#: among THOSE. That shortlist was never presented as part of the rule — but it is, and removing it
#: destroys the result. Re-measured over the same 120 paired drafts with the identical valuation
#: function:
#:
#:     re-rank the legacy top-40's bench candidates    +45.2 season points, ±8.0, 102/120
#:     re-rank EVERY bench candidate on the board       +3.0 season points, ±12.2,  61/120
#:
#: The second is a NULL — its interval spans zero. Same formula, same anchors, same seeds; the only
#: difference is how far down the board the re-rank may reach.
#:
#: ⭐ WHY, and it generalises: an insurance value is points added to MY lineup, so it is happy to
#: crown a player the whole league has passed on 300 times, if his position happens to be thin on my
#: roster. VOR is what says he is not worth a pick. So insurance is a good TIE-BREAKER among
#: candidates the value board already rates, and a bad PRIMARY over the entire pool — which is
#: exactly the shape the shortlist enforces.
#:
#: ⚠️ NOT a tuned knob: 40 is the number the study measured, carried over verbatim. Moving it is a
#: re-measurement, not a preference. ⚠️ LOCK-STEP: `BENCH_RERANK_SHORTLIST` in the TS.
BENCH_RERANK_SHORTLIST = 40


def bench_order_value(vor: float) -> float:
    """Where a bench candidate SITS relative to a need-filler — the retired rule, in VOR units, so
    the comparison is like-for-like. See `BENCH_ORDER_DAMPING`."""
    return vor - (BENCH_ORDER_DAMPING * vor if vor > 0 else 0.0)


# ── NF-C7: THE BENCH SEAT IS AN INSURANCE POLICY, NOT A DISCOUNTED STARTER ────────────────────────
#
# VOR is a STARTER-SCARCITY currency: points over the LEAGUE's last startable player at the position.
# That is the right unit for a starter slot and the wrong one for a bench seat, exactly as it is the
# wrong one for a FLEX seat (see `seat_value_of` — the same move, one seat over).
#
# Measured on the real 2026 board, ~pick 115: QB +3.0 | TE +23.7 | RB -37.2 | WR -27.0, with 2 QBs
# and 3 TEs still above replacement and ZERO RBs or WRs. 35 WRs and 25 RBs clear replacement and a
# 12-team room consumes all of them by round 8 because every team starts two or three; only 12 TEs
# and 12 QBs clear it and each team needs exactly one. ⇒ positive VOR survives ONLY at the two
# positions where a bench player is LEAST useful to you. So "best value on the board (VOR)" was
# STRUCTURALLY GUARANTEED to return a backup TE or QB in the back half of every draft — quantified
# over 120 drafts, the shipped rule's bench came back 47% backup QB / 53% backup TE with ZERO RBs
# and ZERO WRs, a tight-end share closer to a NIHILIST's (98%) than to the oracle's (23%).
#
# A bench seat collects points only in the weeks you actually have to start him. So:
#
#     bench value = P(I need him) x (his per-game rate - the man he displaces)  x  weeks
#
# ⚠️ `SEASON_WEEKS` is the fantasy regular season the study scored (18 weeks, one bye each). It is
# the unit the expected-start count is expressed in, NOT a claim about any particular league's
# playoff schedule.
SEASON_WEEKS = 18
#: Games in an NFL regular season — the denominator the board's `games` projection is stated against
#: (a player projected for `g` of these misses `17 - g`). Distinct from `SEASON_WEEKS`, which counts
#: FANTASY weeks including the bye; conflating them is a silent one-week error in `absence_prob`.
SEASON_GAMES = 17.0
# ⭐⭐ NF-C7 — A DEPTH TARGET IS AN ORDERING TIER, NOT A SCORE BONUS, AND THAT IS A MEASUREMENT.
#
# The insurance rule above de-emphasises a backup QB/TE further than the rule it replaced, which is
# correct on average and wrong for a user who deliberately wants one. `depth_targets` lets them ask:
# a target COUNT per position.
#
# The obvious spelling is a bonus through the existing need machinery, `NEED_W_DEPTH * urgency` with
# `NEED_W_DEPTH` under `NEED_W_FLEX`. It was built that way first and it DOES NOT WORK, for a reason
# worth keeping: `urgency` is a VOR gap and a bench candidate's `score` is his INSURANCE value, so
# the bonus is in the wrong unit for the number it is added to. Measured mid-draft on the real 2026
# board with `{QB: 2, TE: 2}` set: the QB dropoff is a couple of points, so the bonus came to well
# under one point against bench running backs scoring 50+, and NOT ONE candidate at a short position
# reached a six-slot panel. A control the user cannot feel is not a control.
#
# Raising the weight is not the fix either — it would have to be ~50x `NEED_W_FLEX` to bridge the
# gap, at which point it is a number reverse-engineered from the answer, and it would corrupt
# `score`, which the panel prints (E2.1-r).
#
# So the target ORDERS instead of scoring, exactly as `deferred` does for K/DST and for exactly the
# same stated reason. Inside the BENCH cohort — and only there — a position short of its target
# sorts above one that is not. That is literally "below a real open starter slot, above generic
# depth": the cohort's placement against the need-fillers is untouched.
#
# ⭐⭐ IT CANNOT REACH `must_fill` OR `deferred`. It reorders WITHIN the level-0 cohort and touches
# nothing else — `need_level` is unchanged, so `must_fill = must_fill_now and level > 0` cannot see
# it, and the K/DST deferral is a HIGHER sort key, so a kicker target cannot surface a kicker in
# round 6. The reserve constraint OUTRANKS every depth target by construction, not by tuning: a
# preference can never walk a user into an illegal roster. Pinned by
# `betting_ml/tests/test_nf_c7_pick_recommendation.py`.
# Bye-week stacking penalty (fraction of VOR per player I ALREADY hold at the same position on the same
# bye week) — a modest tiebreak so I don't end up with, say, 3 WR starters all idle the same week. Only
# applies when bye weeks are known (populated once the season schedule is ingested).
BYE_PEN_FRAC = 0.08
BYE_CLUSTER_CAP = 3


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# Roster requirements — the league's STARTER shape, distilled from a LeagueConfig
# ─────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RosterRequirements:
    """The per-team STARTER demand: dedicated single-position slots + multi-eligibility flex slots.
    Bench slots carry no starter demand (they don't drive need). Built once per league config."""

    dedicated: dict[str, int]                       # position -> dedicated starter count per team
    flex: tuple[tuple[frozenset[str], int], ...]    # (eligible-set, count) per flex/superflex slot
    bench: int = 0

    @classmethod
    def from_config(cls, config: LeagueConfig) -> "RosterRequirements":
        dedicated: dict[str, int] = {}
        flex: list[tuple[frozenset[str], int]] = []
        bench = 0
        for s in config.roster:
            if s.bench:
                bench += s.count
                continue
            if len(s.eligible) == 1:
                dedicated[s.eligible[0]] = dedicated.get(s.eligible[0], 0) + s.count
            elif len(s.eligible) > 1:
                flex.append((frozenset(s.eligible), s.count))
        return cls(dedicated=dedicated, flex=tuple(flex), bench=bench)

    def positions(self) -> set[str]:
        out = set(self.dedicated)
        for elig, _ in self.flex:
            out |= set(elig)
        return out


@dataclass
class OpenSlots:
    """What starter demand REMAINS for my roster after assigning the players I already hold."""

    dedicated: dict[str, int]                        # position -> still-open dedicated spots
    flex: list[frozenset[str]]                       # one entry per still-open flex/superflex spot
    #: NF-C7 — position -> how many of MY players are currently SEATED in a starter slot at it. The
    #: same greedy assignment that produced the two fields above, counted rather than discarded.
    #:
    #: ⭐ WHY IT IS NOT `starter_seats_for` (the roster's CAPACITY at the position). A bench
    #: candidate can only ever start in place of somebody this roster ACTUALLY seats at his
    #: position. TE capacity in a 1TE+1FLEX league is 2, but if an RB is sitting in the flex then
    #: TE occupies ONE seat, and a second TE covers only that one man's absence. Using capacity made
    #: a level-0 candidate who out-rated the single seated TE read as "walks into a seat" and score
    #: his ENTIRE projected season: measured on the real 2026 board, George Kittle came back at 248
    #: points as bench cover. Deriving it here rather than re-running the assignment keeps ONE
    #: implementation of it (E9.61).
    seated: dict[str, int] = field(default_factory=dict)

    def need_level(self, position: str) -> int:
        """2 = fills an open DEDICATED slot; 1 = fills only an open FLEX; 0 = no open starter slot."""
        if self.dedicated.get(position, 0) > 0:
            return 2
        if any(position in elig for elig in self.flex):
            return 1
        return 0


def _normalize(profile_normalize: Callable[[str | None], str | None] | None, pos: str | None) -> str | None:
    if profile_normalize is None:
        return pos
    return profile_normalize(pos)


def open_starter_slots(
    my_positions: Sequence[str],
    req: RosterRequirements,
    *,
    normalize: Callable[[str | None], str | None] | None = None,
) -> OpenSlots:
    """Greedily assign the positions I've already drafted to my starter slots (dedicated first, then
    the most-restrictive flex), and return what's still open. Most-restrictive-first mirrors `vor.py`'s
    league-wide flex allocation so 'need' is defined consistently with how replacement was computed."""
    open_ded = dict(req.dedicated)
    counts: dict[str, int] = {}
    for p in my_positions:
        p = _normalize(normalize, p)
        if p is None:
            continue
        counts[p] = counts.get(p, 0) + 1

    # fill dedicated slots first
    seated: dict[str, int] = {}
    for pos in list(open_ded.keys()):
        take = min(open_ded[pos], counts.get(pos, 0))
        open_ded[pos] -= take
        counts[pos] = counts.get(pos, 0) - take
        if take:
            seated[pos] = seated.get(pos, 0) + take

    # expand flex slots to individual spots, most-restrictive (smallest eligibility) first
    flex_spots: list[frozenset[str]] = []
    for elig, n in req.flex:
        flex_spots.extend([elig] * n)
    flex_spots.sort(key=len)

    open_flex: list[frozenset[str]] = []
    for elig in flex_spots:
        # fill this flex spot with any leftover eligible player, preferring the scarcest surplus
        filler = None
        # ⭐ TOTAL ORDER, AND THE SECOND KEY IS LOAD-BEARING (NF-C7). "Prefer the scarcest surplus"
        # leaves TIES — a roster holding 3 RBs and 3 WRs with 2+2 dedicated seats has one of each
        # spare, and either may take the flex. `elig` is a FROZENSET, whose iteration order is
        # HASH-RANDOMIZED per process in Python, so the winner of that tie was not even stable
        # RUN-TO-RUN here, and it differed from the TS engine's (insertion-ordered `Set`).
        #
        # It was invisible until NF-C7 because nothing downstream could see WHICH position took the
        # seat — only how many flex spots were left, which is the same either way. `seated` can see
        # it, and it feeds every bench candidate's insurance value, so the two engines disagreed on
        # the recommended pick. Breaking the tie on the position NAME makes it deterministic and
        # identical in both. ⚠️ LOCK-STEP: the same two-key sort in `draft-optimizer.ts`.
        for pos in sorted(elig, key=lambda p: (counts.get(p, 0), p)):
            if counts.get(pos, 0) > 0:
                filler = pos
                break
        if filler is not None:
            counts[filler] -= 1
            seated[filler] = seated.get(filler, 0) + 1
        else:
            open_flex.append(elig)
    return OpenSlots(dedicated={p: n for p, n in open_ded.items() if n > 0}, flex=open_flex,
                     seated=seated)


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# NF-C7 — the BENCH seat: what a depth pick is actually worth
# ─────────────────────────────────────────────────────────────────────────────────────────────────
#
# ⚠️ LOCK-STEP: `perWeekPoints` / `absenceProb` / `starterSeatsFor` / `expectedStarts` /
# `displacedRate` / `benchInsuranceValue` in `frontend/lib/draft-optimizer.ts`, pinned byte-for-byte
# by `betting_ml/tests/test_nf_c_lda_1_optimizer_parity.py`.
def per_week_points(row: dict) -> float:
    """Points per WEEK OF THE SEASON — his projected total spread over the games in one, NOT over
    the games he is projected to play.

    ⭐⭐ `pts / games` IS THE WRONG QUANTITY AND IT SHIPPED ONCE. It is points per game PLAYED, so it
    divides by a number that is TINY for exactly the players a bench comparison is about. Found by
    drafting: the board projects Easton Stick for 1.9 games and 76.6 points, which is a "rate" of
    40.3 a game — nearly DOUBLE any real starting quarterback. The insurance rule read that as "he
    out-rates the QB you hold", concluded he would walk into your starting seat, and recommended him
    in round 10 at "worth 35 as cover" against a published VOR of MINUS 189. Bailey Zappe (0.8
    games) was the same defect one step further along.
    #
    ⭐ `pts / SEASON_GAMES` has no small denominator at all — the divisor is a CONSTANT — and it is
    the quantity a seat actually collects: what he adds to a lineup in an average week of the
    season, availability included. The identity survives too (`SEASON_GAMES x per_week = pts`), so a
    candidate can never be worth more than his own projection.
    #
    ⚠️ BECAUSE AVAILABILITY IS ALREADY IN THE NUMERATOR, `expected_starts` must NOT multiply by it
    again — see the note there. Carrying it once, in the stable place, is the whole point.
    #
    ⚠️ `absence_prob` still divides by games and that is correct: it is asked only about the players
    ALREADY ON THE ROSTER, whose `games` is a real full-season projection.
    """
    return _fnum(row.get("league_points")) / SEASON_GAMES


def absence_prob(row: dict) -> float:
    """P(he misses any given non-bye week), read from the board's own expected-games projection.

    ⚠️ Read, NOT invented. `games` is the projection's own `g`; a player projected for 15.2 of 17 is
    absent 10.6% of weeks. Nothing here models injury CORRELATION or in-season news.

    ⭐ A row with NO `games` is treated as fully AVAILABLE, not as certainly absent. `(SEASON_GAMES - 0)
    / SEASON_GAMES` is 1.0 — "out every week" — which would make every backup behind him maximally
    valuable, so the arithmetic default is the DANGEROUS one. Assuming availability is the
    conservative reading: it adds no bench value we cannot evidence."""
    g = _fnum(row.get("games"))
    if g <= 0:
        return 0.0
    return max(0.0, min(1.0, (SEASON_GAMES - g) / SEASON_GAMES))


def starter_seats_for(req: "RosterRequirements", position: str) -> int:
    """How many STARTER seats this position could ever occupy on one roster — its dedicated slots
    plus every flex/superflex slot it is eligible for. A property of the roster SHAPE.

    ⛔ NOT the seat count the bench-insurance value uses — see `OpenSlots.seated`, which is how many
    of those seats this roster's players ACTUALLY occupy right now. Capacity over-counts whenever
    another position is sitting in a shared flex seat, and over-counting there makes a bench
    candidate read as "walks into a seat" and price at his entire projected season. Kept because it
    is the right answer to a different question (what a position could ever be worth to this
    roster), and named apart so the two cannot be confused."""
    return req.dedicated.get(position, 0) + sum(n for elig, n in req.flex if position in elig)


def expected_starts(candidate: dict, ahead: Sequence[dict], seats: int,
                    weeks: int = SEASON_WEEKS) -> float:
    """Weeks I would ACTUALLY get points out of him — the whole point of a bench seat.

`ahead` is every player I already hold at his position who out-scores him per week. If I hold
    fewer of those than the position SEATS, he takes a seat outright and every non-bye week counts.
    Otherwise he reaches one only when at least `len(ahead) - seats + 1` of them are out — a
    POISSON-BINOMIAL over their per-week absence probabilities, with a bye a certain absence. Exact
    by DP; the counts are tiny (a roster holds a handful per position).

    ⚠️ HIS OWN BYE IS SKIPPED, and that is the only self-adjustment here. His own ABSENCE is already
    inside `per_week_points` (see that function), so multiplying by `1 - absence_prob(him)` as well
    would charge him for it TWICE. Skipping the bye is not double-counting: a bye is a certainty
    about a NAMED week, which a season average cannot express, and it is what prices a backup who
    shares his starter's bye — the one week he can never cover.

    ⚠️ Absences are treated as INDEPENDENT across players and weeks. That understates the value of
    depth (a real injury is a contiguous BLOCK, which is exactly what a bench player covers), i.e.
    it is conservative in the direction of the incumbent rule — NF-C-LDA-6 measured both models and
    the ranking held under each.
    """
    need = None if len(ahead) < seats else len(ahead) - seats + 1
    cand_bye = candidate.get("bye")
    starts = 0.0
    for week in range(1, weeks + 1):
        if cand_bye == week:
            continue
        if need is None:
            starts += 1.0
            continue
        out_probs = [1.0 if r.get("bye") == week else absence_prob(r) for r in ahead]
        dist = [1.0]
        for prob in out_probs:
            nxt = [0.0] * (len(dist) + 1)
            for k, v in enumerate(dist):
                nxt[k] += v * (1.0 - prob)
                nxt[k + 1] += v * prob
            dist = nxt
        starts += sum(dist[need:])
    return starts


def displaced_rate(my_rates_desc: Sequence[float], seats: int, candidate_rate: float) -> float:
    """Whose snaps he actually takes — the comparator the upgrade is measured against.

    Two cases, and the distinction is the ⭐ NF-C7 CORRECTION to the rule NF-C-LDA-6 scored:

      * he out-rates enough of my seat-holders to WALK INTO A SEAT — he pushes out the WEAKEST
        current seat-holder, so that is who he displaces;
      * otherwise he only plays when somebody ahead is out — he displaces whoever would have covered
        that seat instead, i.e. my best player at the position who is NOT already in a seat, or
        NOBODY (rate 0) if I have no cover at all.

    ⚠️ THE STUDY'S RULE ALWAYS TOOK THE SECOND BRANCH, which is wrong in the first: with three RB
    seats, three RBs held and a better RB falling to me, the bench is EMPTY, so the comparator was
    0 and his insurance value came out as his ENTIRE projected season (~4x the true upgrade). That
    branch is reachable in a normal draft, so it is corrected here and the correction is MEASURED as
    its own arm (`insurance_seat`) in `bench_valuation_study.py` rather than assumed — an unmeasured
    "obvious" fix is exactly what that study's own two harness defects were.
    """
    if seats > 0 and len(my_rates_desc) >= seats:
        n_ahead = sum(1 for r in my_rates_desc if r > candidate_rate)
        if n_ahead < seats:
            return float(my_rates_desc[seats - 1])
    bench = list(my_rates_desc[seats:])
    return float(bench[0]) if bench else 0.0


def bench_insurance_value(candidate: dict, my_rows_at_position: Sequence[dict], seats: int,
                          weeks: int = SEASON_WEEKS) -> float:
    """What a BENCH seat is worth: P(I need him) x his upgrade over the man he displaces.

    ⭐ FLOORED AT ZERO ON THE UPGRADE, NOT ON THE PRODUCT: a candidate who is worse than the cover I
    already have is worth nothing extra, and a NEGATIVE insurance value would be a claim that
    holding him makes my lineup worse, which is false — I would simply never start him.
    """
    rate = per_week_points(candidate)
    rates_desc = sorted((per_week_points(r) for r in my_rows_at_position), reverse=True)
    ahead = sorted((r for r in my_rows_at_position if per_week_points(r) > rate),
                   key=per_week_points, reverse=True)
    upgrade = max(0.0, rate - displaced_rate(rates_desc, seats, rate))
    if upgrade <= 0.0:
        return 0.0
    return expected_starts(candidate, ahead, seats, weeks) * upgrade


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# Tiers — group a position's players by unusually-large VOR/points gaps (the "tier cliff")
# ─────────────────────────────────────────────────────────────────────────────────────────────────
#: NF-D19 tier SIZING, ported from `frontend/lib/draft-optimizer.ts` (the shipping engine). A raw
#: gap threshold can cliff off a "tier" of exactly ONE player, which reads as broken rather than as a
#: signal; a flat minimum only fixes that half, leaving the mirror problem — a long flat stretch that
#: no gap ever splits collapsing most of a position into one undifferentiated tier. Both bounds are
#: enforced and both SCALE WITH THE POOL (`n`), so a ~20-deep TE pool and an ~84-row overall board do
#: not share an absolute floor. 4%/15% target roughly 7-25 tiers regardless of n.
MIN_TIER_FRAC = 0.04
MAX_TIER_FRAC = 0.15


def _js_round(x: float) -> int:
    """JavaScript `Math.round` — half away from zero, NOT Python's half-to-EVEN.

    ⚠️ LOAD-BEARING FOR PARITY, and the exact class of detail that makes a "faithful port" silently
    unfaithful: `round(12.5)` is 13 in JS and 12 in Python, so a pool whose 4% lands on a half
    would tier differently in the two engines while every other line agreed. `min_size`/`max_size`
    are the only rounded quantities here, and both are non-negative.
    """
    return int(math.floor(x + 0.5))


def _js_round1(x: float) -> float:
    """JavaScript `Math.round(x * 10) / 10` — the shipping engine's output rounding, reproduced.

    ⚠️ NOT `round(x, 1)`. Python rounds half-to-EVEN and JS rounds half-AWAY-FROM-ZERO, so the two
    disagree in the first decimal on every exact half — measured on a real 2026 full_ppr/12 board,
    that put `score` 0.05 apart on 10 of 41 sampled draft states while every other quantity agreed
    to 1e-14. And the ORDER is sorted on this rounded value in the TS engine, so a Python engine
    that rounded differently could order two near-tied candidates differently.

    ⚠️ THE SORT-ON-A-ROUNDED-VALUE IS THE SHIPPING ENGINE'S BEHAVIOUR AND IS MATCHED DELIBERATELY,
    not endorsed: it can collapse two candidates 0.04 apart into a tie broken by list position (the
    hazard `league_scoring.build_board`'s `_vor_raw` note records). Changing it would make this
    engine disagree with the web app, which is the one thing lock-step exists to prevent — so it is
    a decision for the ranker, taken in BOTH engines at once, never a quiet fix on one side.
    """
    return _js_round(x * 10) / 10


def assign_tiers(points_desc: Sequence[float], *, k: float = 1.0, min_gap: float = 1e-9) -> list[int]:
    """Tier numbers (1 = best) for a DESCENDING points list.

    A new tier starts at an 'unusually large' consecutive drop (gap > mean + k*std), then the raw
    groups are bounded: undersized ones merge into their neighbour, oversized ones split at their
    OWN largest internal gap — so the split points still come from the data, just against a
    per-group relative threshold rather than the whole-pool one. A split that would leave either
    side under `min_size` is skipped (the minimum is the harder constraint; an oversized but
    otherwise unsplittable tail is left alone rather than manufacturing a below-floor sliver).

    ⚠️ LOCK-STEP: `assignTiers` in `frontend/lib/draft-optimizer.ts`. Pinned byte-for-byte by
    `betting_ml/tests/test_nf_c_lda_1_optimizer_parity.py` against output generated by that engine.
    """
    n = len(points_desc)
    if n == 0:
        return []
    if n == 1:
        return [1]
    min_size = max(2, _js_round(n * MIN_TIER_FRAC))
    max_size = max(min_size + 1, _js_round(n * MAX_TIER_FRAC))

    gaps = [max(0.0, float(points_desc[i]) - float(points_desc[i + 1])) for i in range(n - 1)]
    mean = sum(gaps) / len(gaps)
    var = sum((g - mean) ** 2 for g in gaps) / len(gaps)
    std = math.sqrt(var)
    thr = mean + k * std

    # Raw gap-based groups — each a contiguous run of indices into `points_desc`.
    groups: list[list[int]] = [[0]]
    for i, g in enumerate(gaps):
        if g > thr and g > min_gap:
            groups.append([i + 1])
        else:
            groups[-1].append(i + 1)

    # Pass 1 — fold any undersized group into its neighbour.
    merged: list[list[int]] = []
    for g in groups:
        if merged and len(merged[-1]) < min_size:
            merged[-1].extend(g)
        else:
            merged.append(g)
    if len(merged) > 1 and len(merged[-1]) < min_size:
        last = merged.pop()
        merged[-1].extend(last)

    # Pass 2 — split any oversized group at its largest internal gap(s), recursively.
    def split_oversized(g: list[int]) -> list[list[int]]:
        if len(g) <= max_size:
            return [g]
        best_pos, best_gap = -1, -math.inf
        for pos in range(min_size, len(g) - min_size + 1):
            gap_val = gaps[g[pos - 1]]      # the gap between g[pos-1] and g[pos] — a contiguous run
            if gap_val > best_gap:
                best_gap, best_pos = gap_val, pos
        if best_pos == -1:                  # cannot split without leaving a sliver under min_size
            return [g]
        return split_oversized(g[:best_pos]) + split_oversized(g[best_pos:])

    final: list[list[int]] = []
    for g in merged:
        final.extend(split_oversized(g))

    tiers = [1] * n
    for t, g in enumerate(final, start=1):
        for idx in g:
            tiers[idx] = t
    return tiers


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# The recommendation
# ─────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class Recommendation:
    player_id: str
    player_name: str
    position: str
    team_id: str | None
    vor: float
    league_points: float
    positional_rank: int
    overall_rank: int
    score: float                     # seat value + need bonus — the recommendation sort key
    #: ⚠️ `score`/`need_bonus`/`positional_dropoff`/`seat_value` are rounded through `_js_round1`,
    #: NOT `round(x, 1)` — see that helper. The board pass-throughs (`vor`, `league_points`,
    #: `vor_p10/p90`) are left exactly as the board supplied them, which is what the TS engine does.
    need_level: int                  # 2 dedicated / 1 flex / 0 none
    need_bonus: float
    positional_dropoff: float        # VONA: my-value lost at this position if I pass now
    #: The base the score is built on: plain VOR, except for a FLEX-ONLY candidate, where it is
    #: points over the FLEX SEAT's replacement. Exposed so the exact pre-flex-seat ordering stays
    #: reconstructible from a `Recommendation` alone. ⚠️ LOCK-STEP: `seatValue` in the TS.
    seat_value: float
    #: ⭐ NF-C7 — THE SORT KEY, which is `score` for every candidate that fills an open starter slot
    #: and something else for a BENCH candidate. See `BENCH_ORDER_DAMPING`: a bench candidate's
    #: `score` is his insurance value, on a different baseline from a need-filler's VOR, so the two
    #: must not be compared directly. Exposed rather than kept private so the ordering stays
    #: reconstructible from a `Recommendation` alone — the panel is not sorted by the number it
    #: prints, and a reader has to be able to see why. ⚠️ LOCK-STEP: `orderValue` in the TS.
    order_value: float
    #: NF-C7 — how many more of this position the user asked for than they hold. 0 for every
    #: candidate whenever no target is set, so the whole feature is inert until asked for, and 0 for
    #: anything filling an open starter slot (the lineup already asks for those).
    #: ⚠️ LOCK-STEP: `depthShort` in the TS.
    depth_short: int
    #: NF-C7 — the weeks I would actually have to start him, given who I already hold at his
    #: position and their byes/absence. `SEASON_WEEKS` when he walks into a seat on merit; 0 for a
    #: candidate who fills an open starter slot (he starts by definition, so the question is moot).
    #: Shown to the user, because it is the whole reason a bench pick is worth anything.
    #: ⚠️ LOCK-STEP: `expectedStarts` in the TS.
    expected_starts: float
    tier: int
    is_last_in_tier: bool
    is_rookie: bool
    bye: int | None
    bye_conflict: int
    vor_p10: float | None
    vor_p90: float | None
    #: The reserve constraint binds and this player fills an open starter slot — every remaining pick
    #: is spoken for, so passing on all of these strands a mandatory slot empty. False when there is
    #: slack. ⚠️ LOCK-STEP: mirrored as `mustFill` in `frontend/lib/draft-optimizer.ts`.
    must_fill: bool
    #: A LOW-PREDICTABILITY position (K/DST — the exporter's own `low_pred`), held back until the
    #: roster actually requires it. See the note on the sort. ⚠️ LOCK-STEP: `deferred` in the TS.
    deferred: bool
    rationale: str


def _fnum(v, default=0.0) -> float:
    try:
        if v is None:
            return default
        f = float(v)
        return default if math.isnan(f) else f
    except (TypeError, ValueError):
        return default


def recommend(
    board: Iterable[dict],
    *,
    config: LeagueConfig,
    drafted_ids: Iterable[str] = (),
    my_player_ids: Iterable[str] = (),
    normalize: Callable[[str | None], str | None] | None = None,
    depth_targets: dict[str, int] | None = None,
    top_n: int = 8,
    tier_k: float = 1.0,
    bench_value: Callable[[dict, str], float] | None = None,
) -> list[Recommendation]:
    """Rank the still-AVAILABLE board players for MY next pick.

    `board`         — the (config, size)-filtered board rows (dicts with player_id, position, vor,
                      league_points, positional_rank, overall_rank, team_id, is_rookie, vor_p10/p90).
    `drafted_ids`   — every player already taken (by anyone), MINE INCLUDED.
    `my_player_ids` — the subset on my roster (drives positional need).
    `normalize`     — optional position normalizer (e.g. NFL FB→RB); defaults to identity.
    `depth_targets` — NF-C7, OPTIONAL: `{position: how many of him I want in total}`. A position I
                      hold fewer of than its target sorts above one that is not, INSIDE the bench
                      cohort only — below every open starter slot, above generic depth. It is a
                      PREFERENCE, so it lives here rather
                      than on the `LeagueConfig`: a league's identity does not include how many
                      backup quarterbacks its drafter likes. Absent/empty ⇒ the feature is inert.
    `bench_value`   — ⚠️ RESEARCH SEAM, `None` in every shipped caller. Overrides how a LEVEL-0
                      (bench) candidate is valued, as `(row, position) -> seat value`. It exists so
                      `bench_valuation_study.py` can score a competing bench comparator through
                      THIS ENGINE rather than through a re-ranked copy of it: that study's own worst
                      harness defect was a re-implementation of this sort, which mixed units and
                      pushed a peeking ORACLE below the incumbent — a harness bug that reads exactly
                      like a metric inversion. A seam is cheaper than a second engine.
                      ⛔ NOT a user-facing knob and NOT mirrored in the TS engine: the parity guard
                      pins the DEFAULT path, which is the only one anything ships.

    Returns up to `top_n` recommendations sorted by `score` (VOR + roster-need bonus), each with a
    plain-language rationale. Positions with no ranked players (K/DST) never appear — by construction.
    """
    drafted = set(drafted_ids)
    mine = set(my_player_ids)
    req = RosterRequirements.from_config(config)

    # my current positions → still-open starter slots; my (position, bye) counts → bye-stack penalty
    my_positions: list[str] = []
    #: NF-C7 — my roster grouped by position, which is what the bench-seat insurance value is
    #: measured against (`my_positions` alone cannot say how good the players I hold are).
    my_rows_by_pos: dict[str, list[dict]] = {}
    my_byes: dict[tuple[str, int], int] = {}
    by_id: dict[str, dict] = {}
    available: list[dict] = []
    for row in board:
        pid = str(row.get("player_id"))
        by_id[pid] = row
        if pid in drafted:
            if pid in mine:
                p = _normalize(normalize, row.get("position")) or ""
                my_positions.append(p)
                if p:
                    my_rows_by_pos.setdefault(p, []).append(row)
                b = row.get("bye")
                if p and b is not None:
                    my_byes[(p, int(b))] = my_byes.get((p, int(b)), 0) + 1
            continue
        available.append(row)
    open_slots = open_starter_slots(my_positions, req, normalize=normalize)

    # ── THE RESERVE CONSTRAINT: a mandatory starter slot may never be left unfilled ───────────────
    #
    # An empty starter slot scores ZERO, so once my remaining picks are all needed to fill my open
    # starter slots, bench depth is not a trade-off any more — it is strictly dominated, and every
    # remaining pick MUST fill a slot. Without it the optimizer walks a user into an illegal roster:
    # measured on the live 2026 full_ppr/12 board, with every above-replacement RB gone and both RB
    # slots open, the best available RB ranked #86 of 834 and a damped BACKUP QB (vor
    # 25.2, kept 15% by the then-current surplus penalty) out-scored it; the draft ended 7/9 starters filled.
    #
    # ⭐ EXACT, NOT A HEURISTIC — binds iff taking a non-filler PROVABLY strands a slot, so it cannot
    # distort normal drafting: inert with slack, total without. Deliberately NO safety margin — "grab
    # a filler a round early" is a preference; "do not end the draft with an empty starter slot" is a
    # correctness property, and only that is enforced here.
    #
    # Everything is DERIVED (roster size from the config, picks made from `my_player_ids`), so the
    # signature is unchanged and no caller has to be taught to pass draft state.
    # ⚠️ It RANKS, never FILTERS — if no filler exists at all the caller still gets its best options.
    # ⚠️ LOCK-STEP: mirrored in `frontend/lib/draft-optimizer.ts` (the shipping engine).
    # ⛔ DRAFTABLE slots, not every slot: an IR/taxi spot is roster depth NO PICK CAN REACH, so
    # counting it inflates `picks_remaining` and fires this constraint that many picks LATE
    # (see `RESERVE_SLOT_NAMES` — on a real ESPN league with 2 IR spots it first bound with the
    # roster already full, i.e. never in time, and the draft ended with D/ST and K unfilled).
    total_slots = draftable_slot_count(config.roster)
    picks_remaining = total_slots - len(list(my_player_ids or []))
    open_starter_count = sum(open_slots.dedicated.values()) + len(open_slots.flex)
    must_fill_now = open_starter_count > 0 and picks_remaining <= open_starter_count

    # per-position available lists (points-descending) → tiers + next-available lookup
    pos_players: dict[str, list[dict]] = {}
    for row in available:
        pos = _normalize(normalize, row.get("position"))
        if pos is None:
            continue
        pos_players.setdefault(pos, []).append(row)
    pos_tier: dict[str, dict[str, int]] = {}
    pos_next_vor: dict[str, dict[str, float]] = {}
    #: player_id of the BEST AVAILABLE player at each position — the only one that earns the scarcity
    #: bonus (see the note at `need_bonus` below). Keyed off the same pts-descending order as tiers.
    pos_best: dict[str, str] = {}
    for pos, rows in pos_players.items():
        rows.sort(key=lambda r: _fnum(r.get("league_points")), reverse=True)
        tiers = assign_tiers([_fnum(r.get("league_points")) for r in rows], k=tier_k)
        pos_tier[pos] = {}
        pos_next_vor[pos] = {}
        if rows:
            pos_best[pos] = str(rows[0].get("player_id"))
        for i, r in enumerate(rows):
            pid = str(r.get("player_id"))
            pos_tier[pos][pid] = tiers[i]
            nxt = _fnum(rows[i + 1].get("vor")) if i + 1 < len(rows) else _fnum(r.get("replacement_points")) - _fnum(r.get("league_points"))
            # positional drop-off (VONA) = my value now minus the best value still available AFTER me
            pos_next_vor[pos][pid] = nxt

    # ⭐⭐ THE FLEX SEAT IS SCORED ON POINTS, NOT ON A POSITION'S OWN REPLACEMENT ─────────────────
    #
    # VOR is points-over-replacement-AT-HIS-OWN-POSITION, which is exactly right for a DEDICATED
    # slot — you must start a TE, so a TE's worth is measured against other TEs. It is the wrong
    # unit for a FLEX seat, because the seat does not care which position walks into it: it
    # collects POINTS.
    #
    # Measured on the served 2026 full_ppr/12 board, replacement is RB 150.1 / WR 148.3 / TE 130.4.
    # That gap is STRUCTURAL, not noise: the twelve flex seats in a 12-team league go to whichever
    # position has the best next man, TE13 never wins one, so TE replacement stays at TE12 while
    # RB/WR replacement is pushed ~19 points deeper. Plain VOR therefore hands every TE a ~19.7-point
    # head start in a flex comparison he does not deliver in the lineup — the operator's report of
    # "TEs pushed into FLEX in the middle rounds" (2026-08-17).
    #
    # ⛔ NOT a change to VOR and NOT a TE penalty: `seat_value` returns plain VOR for level 0 and
    # level 2, so this can only ever act on the one question it is about. The published board, the
    # rankings, every dedicated slot and every bench pick are untouched.
    #
    # ⚠️ LOCK-STEP: `flexSeatRepl`/`seatValue`/`flexPoolDropoff` in
    # `frontend/lib/draft-optimizer.ts` — the shipping engine, where this was measured
    # (`frontend/scripts/measure-flex-urgency.mjs`: 181 of 3,000 decision points flip, the displaced
    # pick a TE at a FLEX seat in 181 of 181, rounds 3-7 and nowhere else).
    repl_of: dict[str, float] = {}
    # ⚠️ `by_id.values()`, NOT the `board` argument: `board` is an Iterable and was already consumed
    # by the pass above, and its insertion order into `by_id` is the board order the TS engine reads
    # `replOf` in — so "the first row of each position wins" means the same thing in both.
    for row in by_id.values():
        p = _normalize(normalize, row.get("position"))
        if p is not None and p not in repl_of and row.get("replacement_points") is not None:
            repl_of[p] = _fnum(row.get("replacement_points"))
    #: The replacement level of the best FLEX seat this position can still fill — absent when it has
    #: no open flex seat, which is every level-0 and level-2 candidate. `min` over the open seats
    #: because the player picks his best one; `max` within a seat because any eligible
    #: replacement-level player can displace him.
    flex_seat_repl: dict[str, float] = {}
    for pos in pos_players:
        if open_slots.need_level(pos) != 1:
            continue
        best = math.inf
        for slot in open_slots.flex:
            if pos not in slot:
                continue
            seat = -math.inf
            for e in slot:
                if e in repl_of:
                    seat = max(seat, repl_of[e])
            if math.isfinite(seat):
                best = min(best, seat)
        if math.isfinite(best):
            flex_seat_repl[pos] = best

    # ⭐⭐ NF-C7 — THE BENCH SEAT, the third of the three seats `seat_value_of` prices.
    #
    # A level-0 candidate fills no open starter slot, so he is bench depth, and a bench seat does
    # not collect a season of points: it collects the weeks a starter is out or on bye. Pricing him
    # in VOR — points over the LEAGUE's last STARTABLE player — measures him against a seat he is
    # not in. Exactly the flex-seat argument (above), one seat further along.
    #
    # `insurance_of` is memoised per candidate because `expected_starts` runs an 18-week
    # Poisson-binomial and the value is read twice (score + rationale).
    seats_for: dict[str, int] = {}
    insurance_cache: dict[str, tuple[float, float]] = {}

    def bench_seats(pos: str) -> int:
        """Seats this position OCCUPIES in my lineup right now — the seats a bench pick at it could
        ever be needed for. Zero means the position starts nobody for me, so no depth at it can
        ever score: `bench_insurance_value` then returns 0, correctly."""
        if pos not in seats_for:
            seats_for[pos] = int(open_slots.seated.get(pos, 0))
        return seats_for[pos]

    def insurance_of(row: dict, pos: str) -> tuple[float, float]:
        """`(value, expected_starts)` — ONE computation feeding both the score and the sentence
        shown beside it. Two call sites re-deriving the start count would be two rule sets (E9.61),
        and the sentence would eventually quote a number the score did not use."""
        pid_ = str(row.get("player_id"))
        if pid_ not in insurance_cache:
            mine_at_pos = my_rows_by_pos.get(pos, ())
            seats = bench_seats(pos)
            rate = per_week_points(row)
            ahead = sorted((r for r in mine_at_pos if per_week_points(r) > rate),
                           key=per_week_points, reverse=True)
            starts = expected_starts(row, ahead, seats)
            insurance_cache[pid_] = (
                bench_insurance_value(row, mine_at_pos, seats), starts,
            )
        return insurance_cache[pid_]

    def seat_value_of(row: dict) -> float:
        """What this player is worth in the seat he would actually occupy.

        Three seats, three baselines: an open DEDICATED slot is plain VOR (you must start a TE, so
        measure him against TEs); an open FLEX seat re-bases onto the SEAT's own replacement
        (NF-C2.1); a BENCH seat is his insurance value (NF-C7).
        """
        p = _normalize(normalize, row.get("position"))
        if p is None:
            return _fnum(row.get("vor"))
        if p in flex_seat_repl:
            return _fnum(row.get("league_points")) - flex_seat_repl[p]
        if open_slots.need_level(p) == 0:
            return bench_value(row, p) if bench_value is not None else insurance_of(row, p)[0]
        return _fnum(row.get("vor"))

    # ⭐ VONA over the pool that can fill the OPEN SLOT. For a DEDICATED starter that is the next
    # player at the same position (`pos_next_vor`); for a FLEX seat it is the next flex-eligible
    # player at ANY position the seat accepts — using the within-position gap there is a units error
    # with a systematic direction (TE is the thinnest position, so its cliffs are structurally the
    # steepest).
    #
    # ⚠️ MEASURED INERT ON ITS OWN in the TS engine (reverting just this half moved the #1
    # recommendation on 0 of 3,000 decision points — the flex bonus is capped by `NEED_W_FLEX` and
    # the gaps it competes against are far wider). It is kept because it is the correct denominator,
    # NOT because it fixed anything, and saying so is the point: a plausible mechanism that measured
    # inert is a finding, and banking it as the fix would have left the real one (the re-basing
    # above) in place.
    flex_pool_dropoff: dict[str, float] = {}
    for pos, rows_p in pos_players.items():
        if open_slots.need_level(pos) != 1 or not rows_p:
            continue
        pool: set[str] = set()
        for slot in open_slots.flex:
            if pos in slot:
                pool.update(slot)
        nxt_best = seat_value_of(rows_p[1]) if len(rows_p) > 1 else -math.inf
        for other in pool:
            if other == pos:
                continue
            others = pos_players.get(other)
            if others:
                nxt_best = max(nxt_best, seat_value_of(others[0]))
        if nxt_best == -math.inf:
            # Nothing else can fill the seat — fall back to the dedicated measure, whose own
            # last-player fallback is `replacement - points`.
            nxt_best = pos_next_vor[pos].get(str(rows_p[0].get("player_id")), 0.0)
        flex_pool_dropoff[pos] = max(0.0, seat_value_of(rows_p[0]) - nxt_best)

    recs: list[Recommendation] = []
    for row in available:
        pid = str(row.get("player_id"))
        pos = _normalize(normalize, row.get("position"))
        if pos is None:
            continue
        if row.get("vor") is None:                 # unprojected (K/DST) — never a recommendation
            continue
        vor = _fnum(row.get("vor"))
        next_vor = pos_next_vor[pos].get(pid, 0.0)
        dropoff = max(0.0, vor - next_vor)
        level = open_slots.need_level(pos)
        need_w = NEED_W_DEDICATED if level == 2 else (NEED_W_FLEX if level == 1 else 0.0)
        # ⭐ THE SCARCITY BONUS BELONGS TO THE POSITION, SO ONLY ITS BEST AVAILABLE PLAYER EARNS IT.
        # Awarding each player his OWN `dropoff` inverts a position: `dropoff` is a pure GAP that says
        # nothing about what the candidate is worth, so whoever sits on the near side of a cliff
        # collects the whole cliff, however bad he is.
        #
        # Measured on the live 2026 full_ppr/12 board (2026-08-12): the kicker pool cliffs 29.1 VOR
        # between projected starters and deep backups, so K31 (vor -10.8) scored 18.3 and beat the
        # BEST kicker (vor +8.1, score 9.6) — landing K31 at #66 overall, a round-6 pick.
        #
        # ⚠️ It survived because MVP-3 shipped K/DST as null-VOR placeholders (skipped above); NF1.6
        # gave them real projections and made a ~30-row sub-replacement tail live for the first time.
        #
        # ⛔ The obvious patch (`need_w * dropoff if vor > 0 else 0`) is wrong twice: it MOVES the
        # inversion rather than removing it (the row above the cliff still wins when the cliff sits
        # one place higher), and it BREAKS need-filling — late in a draft everything left at a needed
        # position is below replacement and the roster must still be filled
        # (`test_mock_snake_draft_replay`: "team 8 never drafted a TE").
        #
        # VONA answers "should I address this position NOW?", never "which player at it?" — that is
        # always VOR. So urgency is computed once per position, at the player you would actually
        # draft. Ordering inside a position is then VOR-monotone BY CONSTRUCTION, while the best
        # available at a needed position keeps the full bonus even below replacement.
        # ⚠️ LOCK-STEP: mirrored in `frontend/lib/draft-optimizer.ts` (the shipping engine).
        #
        # ⭐ `urgency` is the gap over the pool that can fill the OPEN SLOT (see `flex_pool_dropoff`):
        # within-position for a dedicated starter, across the flex pool for a flex seat. `dropoff`
        # stays the within-position number because the tier-cliff line is a genuine statement about
        # the POSITION and is true regardless of which seat is open.
        urgency = flex_pool_dropoff.get(pos, dropoff) if level == 1 else dropoff
        need_bonus = need_w * urgency if pos_best.get(pos) == pid else 0.0
        # ⭐ NF-C7 — THE USER'S DEPTH TARGET. `depth_short` is how many more of this position the
        # user asked for than they hold. It carries NO weight and NO bonus: it is read by the bench
        # re-rank below as an ORDERING TIER (see the note at the top of this module, which records
        # why a weighted bonus was built first and measured inert).
        #
        # ⛔ LEVEL 0 ONLY. A position with an OPEN starter slot is already being asked for by the
        # lineup, and letting a preference speak there would re-weight the very needs it must rank
        # below.
        depth_short = 0
        if level == 0 and depth_targets:
            depth_short = max(0, int(depth_targets.get(pos, 0)) - len(my_rows_by_pos.get(pos, ())))
        # bye-week stacking: penalize by how many I already start/hold at this position on the same bye
        bye = row.get("bye")
        bye_conflict = my_byes.get((pos, int(bye)), 0) if bye is not None else 0
        bye_pen = BYE_PEN_FRAC * min(bye_conflict, BYE_CLUSTER_CAP) * vor if (bye_conflict and vor > 0) else 0.0
        # ⭐ `seat_value`, not `vor` — see the seat blocks above. Identical to `vor` for a candidate
        # filling an open DEDICATED slot; re-based for a flex-only one; his insurance value for a
        # BENCH pick. (`bye_pen` scales a held-position stack, so it stays on `vor`: it is a
        # statement about the ROSTER, not about the open seat.)
        base = seat_value_of(row)
        score = base + need_bonus - bye_pen
        # True only while the reserve constraint binds AND this player fills an open starter slot.
        must_fill = must_fill_now and level > 0
        # ⭐ K/DST are held back until the roster requires them. Read from the exporter's own
        # `low_pred` rather than a position list — the flag exists so a consumer never has to know
        # which positions are soft, and a hardcoded ("K","DST") would silently miss a future one.
        deferred = bool(row.get("low_pred"))

        tier = pos_tier[pos].get(pid, 1)
        rows_pos = pos_players[pos]
        last_in_tier = (
            rows_pos.index(row) == len(rows_pos) - 1
            or pos_tier[pos].get(str(rows_pos[rows_pos.index(row) + 1].get("player_id"))) != tier
        )
        recs.append(Recommendation(
            player_id=pid,
            player_name=str(row.get("player_name") or ""),
            position=pos,
            team_id=(row.get("team_id") if row.get("team_id") is not None else None),
            vor=vor,
            league_points=_fnum(row.get("league_points")),
            positional_rank=int(_fnum(row.get("positional_rank"))),
            overall_rank=int(_fnum(row.get("overall_rank"))),
            score=_js_round1(score),
            need_level=level,
            need_bonus=_js_round1(need_bonus),
            positional_dropoff=_js_round1(dropoff),
            seat_value=_js_round1(base),
            # For a candidate that fills an open starter slot this IS `score`. For a BENCH candidate
            # it is the retired damping in VOR units — the same bonuses and penalties applied to a
            # comparable base — and the re-rank below PERMUTES those values across the cohort into
            # insurance order.
            order_value=_js_round1(
                bench_order_value(vor) - bye_pen if level == 0 else score
            ),
            depth_short=depth_short,
            expected_starts=(_js_round1(insurance_of(row, pos)[1]) if level == 0 else 0.0),
            tier=tier,
            is_last_in_tier=bool(last_in_tier),
            is_rookie=bool(row.get("is_rookie")),
            bye=(int(bye) if bye is not None else None),
            bye_conflict=int(bye_conflict),
            vor_p10=(_fnum(row.get("vor_p10")) if row.get("vor_p10") is not None else None),
            vor_p90=(_fnum(row.get("vor_p90")) if row.get("vor_p90") is not None else None),
            must_fill=must_fill,
            deferred=deferred,
            rationale=_rationale(pos, level, need_bonus, dropoff, urgency, base - vor, vor,
                                 last_in_tier, tier, bye, bye_conflict, must_fill,
                                 picks_remaining, open_starter_count, base, depth_short,
                                 depth_targets.get(pos, 0) if depth_targets else 0),
        ))

    # ── the ordering, in three keys ───────────────────────────────────────────────────────────────
    #
    # 1. `must_fill` — a required filler outranks everything (the reserve constraint).
    # 2. `deferred`  — a LOW-PREDICTABILITY position (K/DST) sits below every real candidate.
    # 3. `score`.
    #
    # ⭐ WHY (2) EXISTS. Recommending a D/ST in an early round destroys trust in every other
    # recommendation on the page, and it was happening: on the live 2026 full_ppr/12 board ROUND 6's
    # six-slot panel came back FIVE-SIXTHS K/DST with DEN D/ST ranked #1.
    #
    # Not a scoring bug — VOR read as comparable across positions where it is not. The whole
    # above-replacement VOR range is 8.1 at K and 10.4 at D/ST against a MEDIAN 80% interval of 118.7
    # and 87.3 on a single player (signal-to-noise 0.07 / 0.12, vs 0.55-0.61 at RB/WR/TE), so DST1
    # over DST12 is not a distinction this projection can support — which is what the exporter says
    # by stamping `low_pred`.
    #
    # ⛔ NOT a score penalty: a fudge big enough to sink K/DST would be reverse-engineered from the
    # answer and would corrupt `score`, which the UI shows. Deferral changes only the ORDER.
    #
    # ⚠️ The two rules COMPOSE, and that is what makes absolute deferral safe: whenever K/DST are the
    # only thing a roster can still accept, the bench is full ⇒ picks_remaining == open_starter_count
    # ⇒ the reserve constraint is NECESSARILY binding ⇒ `must_fill` lifts them back to the top.
    # Structural, not luck. Never early, always by the end.
    # ⚠️ LOCK-STEP: mirrored in `frontend/lib/draft-optimizer.ts` (the shipping engine).
    # ── NF-C7: the bench cohort keeps its retired PLACEMENT, and insurance decides WHO fills it ──
    #
    # The level-0 rows collectively occupy exactly the slots the retired damping gave them — so
    # WHETHER to take a bench player is unchanged, which is what NF-C-LDA-6 held fixed — while WHICH
    # bench player gets each of those slots is decided by insurance. Within the cohort the ordering
    # is therefore monotone in `score` too, so only the boundary between fillers and bench can read
    # out of order, and the rationale on each row says which it is.
    #
    # ⚠️ SPLIT BY `deferred`. K/DST sit below every real candidate on their own sort key, so mixing
    # their order values into the skill-position cohort would hand a skill-position bench pick a
    # K/DST slot and vice versa — placements that mean nothing, since the two never compete.
    # ⚠️ TOTAL ORDER ON BOTH SIDES (`player_id` breaks a tie): a stable sort would inherit board
    # order, which is the same in both engines today but is not a property either of them states.
    # ⚠️ LOCK-STEP: mirrored in `frontend/lib/draft-optimizer.ts`.
    for deferred_group in (False, True):
        # ⭐ THE SHORTLIST (see `BENCH_RERANK_SHORTLIST`): only the bench candidates the RETIRED
        # ordering already rates may be re-ranked. Everything below keeps its legacy place, so
        # insurance can pick among plausible depth and can never reach 300 picks down the board for
        # a player whose only virtue is that my roster is thin at his position.
        #
        # ⭐⭐ …PLUS THE BEST CANDIDATE AT EACH POSITION THE USER IS SHORT OF. The shortlist is a
        # bound on how far INSURANCE may reach; it must not be a bound on what the USER may ask
        # for. Found by driving a mock draft: with a TE target set and no tight end inside the top
        # 40, the target could not act at all and the control was invisible to whoever set it.
        #
        # ⚠️ PROVABLY INERT WITHOUT A TARGET, which is what keeps the measurement valid: no arm in
        # `bench_valuation_study.py` sets `depth_targets`, so `depth_short` is 0 for every
        # candidate there and this union is empty. +45.2 was measured on exactly this set.
        same_tier = [r for r in recs if r.deferred is deferred_group]
        ranked_by_order = sorted(same_tier, key=lambda r: (-r.order_value, r.player_id))
        eligible_ids = {r.player_id for r in ranked_by_order[:BENCH_RERANK_SHORTLIST]}
        best_short: dict[str, Recommendation] = {}
        for r in ranked_by_order:
            if r.need_level == 0 and r.depth_short > 0 and r.position not in best_short:
                best_short[r.position] = r
        eligible_ids |= {r.player_id for r in best_short.values()}
        cohort = [r for r in same_tier if r.need_level == 0 and r.player_id in eligible_ids]
        if len(cohort) < 2:
            continue
        slots = sorted((r.order_value for r in cohort), reverse=True)
        # ⭐ THE DEPTH TIER LIVES HERE, and only here: the cohort's SLOTS are fixed (that is the
        # placement rule) and the target decides only WHO gets which of them. So a target can
        # reorder the bench and can never move the bench as a whole.
        # ⭐ THE THIRD KEY IS NOT COSMETIC. A tie on `score` is COMMON — every bench candidate a
        # roster has no use for is worth exactly 0 — and falling through to the player id there is
        # arbitrary. Found by drafting: with the whole bench tied at 0 the best placement slot went
        # to whoever won an ALPHABETICAL tie, and round 10 recommended Philip Rivers (VOR -246)
        # over bench receivers the retired rule ranked 200 points higher. Breaking the tie on the
        # candidate's OWN placement value means insurance decides, and WHERE INSURANCE IS
        # INDIFFERENT THE RETIRED ORDERING STANDS — the correct fallback, not a new rule.
        ranked = sorted(cohort,
                        key=lambda r: (r.depth_short <= 0, -r.score, -r.order_value, r.player_id))
        for rec, slot_value in zip(ranked, slots):
            rec.order_value = slot_value

    # ⚠️ TOTAL ORDER. `order_value` TIES inside the bench cohort (many bench candidates share a
    # rounded value), and a stable sort would then fall back to BOARD order — silently undoing the
    # re-rank above, which is the whole NF-C7 change. The extra keys re-state the re-rank's own
    # ordering, so a tie resolves the same way the cohort was ranked.
    # ⚠️ LOCK-STEP: the same comparator chain in `frontend/lib/draft-optimizer.ts`.
    recs.sort(key=lambda r: (not r.must_fill, r.deferred, -r.order_value,
                             r.depth_short <= 0, -r.score, r.player_id))

    return recs[:top_n]


def _rationale(pos, level, need_bonus, dropoff, urgency, seat_adj, vor, last_in_tier, tier,
               bye=None, bye_conflict=0, must_fill=False, picks_remaining=0,
               open_starter_count=0, seat_value=0.0, depth_short=0, depth_target=0) -> str:
    """The plain-language sentence shown beside a recommendation.

    ⚠️ LOCK-STEP, AND THE WORDING IS PART OF IT: `rationale()` in
    `frontend/lib/draft-optimizer.ts`. The overlay renders whatever this returns beside the same
    `score` the web app shows, so a capitalisation or separator difference is a user-visible
    disagreement between two surfaces that claim to be one tool.

    `urgency` is the gap the bonus was ACTUALLY computed from (equal to `dropoff` for a dedicated
    starter, the flex-POOL gap for a flex seat), passed separately so the sentence can never quote a
    number the score did not use. `seat_adj` is `seat_value - vor`.
    """
    parts: list[str] = []
    # Leads the sentence when it applies: this is no longer a value judgement the user can weigh, so
    # saying WHY the tool stopped offering better-scoring bench players is the honest thing to show.
    if must_fill:
        picks = f"{picks_remaining} pick{'' if picks_remaining == 1 else 's'} left"
        slots = f"{open_starter_count} starter slot{'' if open_starter_count == 1 else 's'} still open"
        parts.append(f"\u26a0 Must fill a starter \u2014 {picks}, {slots}")
    if level == 2:
        parts.append(f"Fills your open {pos} starter")
    elif level == 1:
        parts.append(f"Fills an open FLEX ({pos}-eligible)")
    # The re-basing, whenever it is big enough to matter to the score on screen. SHORT on purpose:
    # it names the two numbers, and the WHY belongs in the surface's tooltip rather than repeated on
    # every row.
    if level == 1 and seat_adj < -0.5:
        parts.append(f"Scored for the FLEX seat: {_js_round(vor + seat_adj)}, "
                     f"not his {_js_round(vor)} VOR")
    # ⭐ NF-C7 — a BENCH pick names what it is worth AND why, because the number is no longer his
    # VOR and a reader would otherwise have no way to tell. The wording states the seat it prices.
    if level == 0:
        parts.append(f"Bench depth \u2014 worth {_js_round(seat_value)} as cover, "
                     f"not his {_js_round(vor)} VOR")
    if depth_short > 0:
        parts.append(f"You asked for {depth_target} {pos}"
                     f"{'' if depth_target == 1 else 's'} \u2014 {depth_short} short")
    if last_in_tier and dropoff > 0:
        parts.append(f"Last of Tier {tier} \u2014 {_js_round(dropoff)} VOR cliff to the next {pos}")
    # ⚠️ QUOTES `urgency`, NOT `dropoff` — for a FLEX seat the bonus is the gap over the flex POOL,
    # and naming the (larger) within-position gap beside it would explain the score with a number the
    # score did not use. The wording names the pool too, so the two cases are not confusable.
    elif urgency > 0 and need_bonus > 0:
        parts.append(f"+{_js_round(urgency)} VOR over the next FLEX-eligible player" if level == 1
                     else f"+{_js_round(urgency)} VOR over the next {pos}")
    if bye_conflict and bye is not None:
        parts.append(f"\u26a0 {bye_conflict} other {pos} on bye {bye}")
    if not parts:
        parts.append("Best value on the board (VOR)")
    return " \u00b7 ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# Snake-draft helpers — "how long until my next pick?" (informs whether a tier survives the wait)
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def overall_pick_for(team_slot: int, n_teams: int, draft_round: int) -> int:
    """1-indexed overall pick number for `team_slot` (1..n_teams) in `draft_round` (1-indexed), snake."""
    if draft_round % 2 == 1:                              # odd round: 1..n_teams
        return (draft_round - 1) * n_teams + team_slot
    return (draft_round - 1) * n_teams + (n_teams - team_slot + 1)  # even round: reversed


def my_upcoming_picks(team_slot: int, n_teams: int, rounds: int) -> list[int]:
    return [overall_pick_for(team_slot, n_teams, r) for r in range(1, rounds + 1)]


def picks_until_next(team_slot: int, n_teams: int, current_overall_pick: int, rounds: int = 30) -> int:
    """How many OTHER picks happen before my next turn (0 = I'm on the clock now)."""
    for p in my_upcoming_picks(team_slot, n_teams, rounds):
        if p >= current_overall_pick:
            return p - current_overall_pick
    return 0
