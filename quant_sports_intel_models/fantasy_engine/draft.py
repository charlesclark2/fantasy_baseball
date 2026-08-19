"""draft.py — sport-agnostic LIVE draft optimizer over a VOR board (NF-C2 / MVP-3).

Given a scored+ranked league board (the `vor.build_board` / `mart_nfl_fantasy_league_board` output),
plus the CURRENT draft state (who's been taken, who's on MY roster, my slot, the league's roster
requirements), recommend the value-maximizing pick(s). Three signals, all transparent:

  1. VOR              — value-over-replacement already encodes CROSS-position scarcity (the board's job).
  2. POSITIONAL NEED  — does adding this player fill one of MY still-open STARTER slots (dedicated OR
                        flex/superflex)? A player who plugs a hole is worth more to *me* than his raw VOR.
  3. VONA / TIER CLIFF— value-over-next-available at his position: how much value I lose at that position
                        if I pass now and wait. A big drop-off (the "tier cliff") is the grab-now signal.

The recommendation score stays in VOR POINTS (additive, never a multiplier — VOR can be negative):

    score = vor + need_bonus                          (need_bonus = 0 when the slot is already full)
    need_bonus = NEED_W[level] * positional_dropoff   (level: open-dedicated > open-flex > none)

so the rationale writes itself ("VOR 122 + fills your open RB2, +38 drop-off to the next RB = 160").

Everything is pure (board rows in, recommendations out) and sport-neutral: positions, eligibility and
roster shape come only from the `LeagueConfig` — the identical algorithm powers the live TS client
(`frontend/lib/draft-optimizer.ts`); keep the two in lock-step. K/DST (or any position with no ranked
players) simply never surface as a candidate — handled by construction, never a crash.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from quant_sports_intel_models.fantasy_engine.league_config import LeagueConfig

# Need weights (in VONA-points): a candidate that fills an OPEN DEDICATED starter slot gets the full
# positional drop-off as a bonus; one that only fills a FLEX/superflex spot gets a fraction; a position
# whose starter demand I've already met gets none (VOR alone ranks the pure-depth pick).
NEED_W_DEDICATED = 1.0
NEED_W_FLEX = 0.4
# Surplus (bench-depth) penalty as a fraction of VOR, applied when a pick fills NO open starter slot:
#   base           — any bench pick is discounted vs a need-filler,
#   + over-capacity — extra when I already hold as many as I could ever START at the position (dedicated
#                     + flex-eligible slots) → a 2nd QB in a 1-QB league is punished hard, so it stops
#                     out-ranking RB/WR depth once my starters are set.
SURPLUS_BASE = 0.5
SURPLUS_OVER = 0.35
SURPLUS_CAP = 0.9
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
    for pos in list(open_ded.keys()):
        take = min(open_ded[pos], counts.get(pos, 0))
        open_ded[pos] -= take
        counts[pos] = counts.get(pos, 0) - take

    # expand flex slots to individual spots, most-restrictive (smallest eligibility) first
    flex_spots: list[frozenset[str]] = []
    for elig, n in req.flex:
        flex_spots.extend([elig] * n)
    flex_spots.sort(key=len)

    open_flex: list[frozenset[str]] = []
    for elig in flex_spots:
        # fill this flex spot with any leftover eligible player, preferring the scarcest surplus
        filler = None
        for pos in sorted(elig, key=lambda p: counts.get(p, 0)):
            if counts.get(pos, 0) > 0:
                filler = pos
                break
        if filler is not None:
            counts[filler] -= 1
        else:
            open_flex.append(elig)
    return OpenSlots(dedicated={p: n for p, n in open_ded.items() if n > 0}, flex=open_flex)


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
    top_n: int = 8,
    tier_k: float = 1.0,
) -> list[Recommendation]:
    """Rank the still-AVAILABLE board players for MY next pick.

    `board`         — the (config, size)-filtered board rows (dicts with player_id, position, vor,
                      league_points, positional_rank, overall_rank, team_id, is_rookie, vor_p10/p90).
    `drafted_ids`   — every player already taken (by anyone), MINE INCLUDED.
    `my_player_ids` — the subset on my roster (drives positional need).
    `normalize`     — optional position normalizer (e.g. NFL FB→RB); defaults to identity.

    Returns up to `top_n` recommendations sorted by `score` (VOR + roster-need bonus), each with a
    plain-language rationale. Positions with no ranked players (K/DST) never appear — by construction.
    """
    drafted = set(drafted_ids)
    mine = set(my_player_ids)
    req = RosterRequirements.from_config(config)

    # my current positions → still-open starter slots; my (position, bye) counts → bye-stack penalty
    my_positions: list[str] = []
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
    # slots open, the best available RB ranked #86 of 834 and a surplus-penalized BACKUP QB (vor
    # 25.2, kept 10% by SURPLUS_CAP) out-scored it; the draft ended 7/9 starters filled.
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
    total_slots = sum(s.count for s in config.roster)
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
    my_counts: dict[str, int] = {}
    for p in my_positions:
        my_counts[p] = my_counts.get(p, 0) + 1
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

    def seat_value_of(row: dict) -> float:
        """What this player is worth in the seat he would actually occupy — plain VOR everywhere
        except a flex-only candidate, where the baseline moves onto the seat."""
        p = _normalize(normalize, row.get("position"))
        if p is not None and p in flex_seat_repl:
            return _fnum(row.get("league_points")) - flex_seat_repl[p]
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
        # surplus damping: this pick fills NO open starter slot (level 0) → it's bench depth. Discount it
        # vs a need-filler, and punish it HARDER once I already hold everything I could ever start at the
        # position (so a 2nd QB / 2nd TE stops out-ranking RB/WR depth once my starters are set).
        held = my_counts.get(pos, 0)
        capacity = req.dedicated.get(pos, 0) + sum(n for elig, n in req.flex if pos in elig)
        surplus_pen = 0.0
        if level == 0 and vor > 0:
            frac = SURPLUS_BASE + (SURPLUS_OVER if held >= capacity else 0.0)
            surplus_pen = min(SURPLUS_CAP, frac) * vor
        # bye-week stacking: penalize by how many I already start/hold at this position on the same bye
        bye = row.get("bye")
        bye_conflict = my_byes.get((pos, int(bye)), 0) if bye is not None else 0
        bye_pen = BYE_PEN_FRAC * min(bye_conflict, BYE_CLUSTER_CAP) * vor if (bye_conflict and vor > 0) else 0.0
        # ⭐ `seat_value`, not `vor` — see the flex-seat block above. Identical to `vor` for every
        # candidate except a flex-only one. (`surplus_pen` is level-0-only and `bye_pen` scales a
        # held-position stack, so both stay on `vor`: they are statements about the ROSTER, not
        # about the open seat.)
        base = seat_value_of(row)
        score = base + need_bonus - surplus_pen - bye_pen
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
                                 last_in_tier, tier, surplus_pen, bye, bye_conflict, must_fill,
                                 picks_remaining, open_starter_count),
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
    recs.sort(key=lambda r: (r.must_fill, not r.deferred, r.score), reverse=True)
    return recs[:top_n]


def _rationale(pos, level, need_bonus, dropoff, urgency, seat_adj, vor, last_in_tier, tier,
               surplus_pen, bye=None, bye_conflict=0, must_fill=False, picks_remaining=0,
               open_starter_count=0) -> str:
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
    if last_in_tier and dropoff > 0:
        parts.append(f"Last of Tier {tier} \u2014 {_js_round(dropoff)} VOR cliff to the next {pos}")
    # ⚠️ QUOTES `urgency`, NOT `dropoff` — for a FLEX seat the bonus is the gap over the flex POOL,
    # and naming the (larger) within-position gap beside it would explain the score with a number the
    # score did not use. The wording names the pool too, so the two cases are not confusable.
    elif urgency > 0 and need_bonus > 0:
        parts.append(f"+{_js_round(urgency)} VOR over the next FLEX-eligible player" if level == 1
                     else f"+{_js_round(urgency)} VOR over the next {pos}")
    if surplus_pen > 0:
        parts.append(f"Depth pick \u2014 {pos} starters already set")
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
