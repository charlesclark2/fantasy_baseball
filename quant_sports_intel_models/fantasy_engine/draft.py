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
def assign_tiers(points_desc: Sequence[float], *, k: float = 1.0, min_gap: float = 1e-9) -> list[int]:
    """Tier numbers (1 = best) for a DESCENDING points list. A new tier starts at an 'unusually large'
    consecutive drop: gap > mean(gaps) + k*std(gaps). Transparent, sample-robust, no magic thresholds."""
    n = len(points_desc)
    if n == 0:
        return []
    if n == 1:
        return [1]
    gaps = [max(0.0, float(points_desc[i]) - float(points_desc[i + 1])) for i in range(n - 1)]
    mean = sum(gaps) / len(gaps)
    var = sum((g - mean) ** 2 for g in gaps) / len(gaps)
    std = math.sqrt(var)
    thr = mean + k * std
    tiers = [1]
    t = 1
    for g in gaps:
        if g > thr and g > min_gap:
            t += 1
        tiers.append(t)
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
    score: float                     # VOR + need bonus — the recommendation sort key
    need_level: int                  # 2 dedicated / 1 flex / 0 none
    need_bonus: float
    positional_dropoff: float        # VONA: my-value lost at this position if I pass now
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
        need_bonus = need_w * dropoff if pos_best.get(pos) == pid else 0.0
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
        score = vor + need_bonus - surplus_pen - bye_pen
        # True only while the reserve constraint binds AND this player fills an open starter slot.
        must_fill = must_fill_now and level > 0

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
            vor=round(vor, 1),
            league_points=round(_fnum(row.get("league_points")), 1),
            positional_rank=int(_fnum(row.get("positional_rank"))),
            overall_rank=int(_fnum(row.get("overall_rank"))),
            score=round(score, 1),
            need_level=level,
            need_bonus=round(need_bonus, 1),
            positional_dropoff=round(dropoff, 1),
            tier=tier,
            is_last_in_tier=bool(last_in_tier),
            is_rookie=bool(row.get("is_rookie")),
            bye=(int(bye) if bye is not None else None),
            bye_conflict=int(bye_conflict),
            vor_p10=(round(_fnum(row.get("vor_p10")), 1) if row.get("vor_p10") is not None else None),
            vor_p90=(round(_fnum(row.get("vor_p90")), 1) if row.get("vor_p90") is not None else None),
            must_fill=must_fill,
            rationale=_rationale(pos, level, need_bonus, dropoff, last_in_tier, tier, surplus_pen,
                                 bye, bye_conflict, must_fill, picks_remaining, open_starter_count),
        ))

    # A required filler outranks every non-filler; within each group, score decides. `must_fill` is
    # False for ALL candidates unless the reserve constraint binds ⇒ with slack this is the old sort.
    recs.sort(key=lambda r: (r.must_fill, r.score), reverse=True)
    return recs[:top_n]


def _rationale(pos, level, need_bonus, dropoff, last_in_tier, tier, surplus_pen, bye=None, bye_conflict=0,
               must_fill=False, picks_remaining=0, open_starter_count=0) -> str:
    parts: list[str] = []
    # Leads the sentence when it applies: this is no longer a value judgement the user can weigh, so
    # saying WHY the tool stopped offering better-scoring bench players is the honest thing to show.
    if must_fill:
        picks = f"{picks_remaining} pick{'' if picks_remaining == 1 else 's'} left"
        slots = f"{open_starter_count} starter slot{'' if open_starter_count == 1 else 's'} still open"
        parts.append(f"MUST fill a starter — {picks}, {slots}")
    if level == 2:
        parts.append(f"fills your open {pos} starter")
    elif level == 1:
        parts.append(f"fills an open FLEX ({pos}-eligible)")
    if last_in_tier and dropoff > 0:
        parts.append(f"last of Tier {tier} — {dropoff:.0f} VOR cliff to the next {pos}")
    elif dropoff > 0 and need_bonus > 0:
        parts.append(f"+{dropoff:.0f} VOR over the next {pos}")
    if surplus_pen > 0:
        parts.append(f"depth pick — {pos} starters already set")
    if bye_conflict and bye is not None:
        parts.append(f"⚠ {bye_conflict} other {pos} on bye {bye}")
    if not parts:
        parts.append("best value on the board (VOR)")
    return "; ".join(parts)


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
