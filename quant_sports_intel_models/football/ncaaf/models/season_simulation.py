"""season_simulation.py — NCAAF-P1.5 (the posterior-predictive SEASON Monte-Carlo).

WHAT THIS IS
------------
The pure engine for NCAAF season-long FUTURES: **National-Championship winner** + **each
Conference-championship winner** probabilities. You cannot derive P(win the conf / natty)
analytically — schedule structure + standings + tiebreakers + the CFP bracket/selection make it a
combinatorial object — so a full-season Monte-Carlo on top of the P1.4 game model IS the right tool
(⭐ unlike a game-level bottom-up sim, which MLB's E13.2 found to be a null; SEASON simulation is the
genuinely-correct MC application: the P1.4 per-matchup predictive distribution is the engine, run the
whole season thousands of times, count championship frequencies).

⭐ THE ONE DISCIPLINE THAT MAKES A FUTURES NUMBER HONEST (the load-bearing bit)
-----------------------------------------------------------------------------
Each team's TRUE season strength is drawn ONCE per simulated season (from its P1.2 posterior) and
REUSED across that team's entire schedule — NOT re-rolled per game. A team that is genuinely a
coin-flip to be good must have that uncertainty CORRELATED across all ~12 of its games (a good draw
wins more of the schedule that sim), which is the real correlation structure that a futures
distribution lives or dies on. Then every game is simulated with the P1.4 game model in
`fixed_strength=True` mode — the IRREDUCIBLE game noise σ₀ ALONE — because the strength uncertainty
is already injected by the once-per-season draw. Adding the k²·strength_var per-game term on top
would DOUBLE-COUNT it (see `ncaaf_game_predictor.sample_matchup`). This module owns that discipline.

THE MEAN MAP (drawn strengths → per-game μ) — faithful to the served ridge/strength_only model
----------------------------------------------------------------------------------------------
P1.4 shipped `ridge / strength_only / strength_posterior`. Its mean is, to within its served σ, the
textbook additive strength decomposition (verified on the real 2014–2025 matrix: residual sd 16.4
vs the served σ_margin 16.1, and 72.3% winner accuracy = P1.2/P1.4):

    μ_margin = HFA·(not neutral) + (strength_margin_home − strength_margin_away)
    μ_total  = 2·league_base + (off_home + off_away) − (def_home + def_away)

⚠️ SIGN CONVENTION (the P1.2 trap): `strength_offense` and `strength_defense` are BOTH
higher-is-better (defense = points PREVENTED), so net strength is their SUM and the TOTAL subtracts
the two defenses. `strength_margin` = off + def; we draw the net once and split the shock into
offense/defense in proportion to their posterior sds so the identity `margin = off + def` holds
exactly per draw (a transparent, documented approximation — the strength model only gives the net
decomposition, not an independent pace axis).

THE STRUCTURE (conference titles + the 2026 12-team CFP) — an EXPLICIT, SWAPPABLE ruleset
----------------------------------------------------------------------------------------
Committee behaviour is fuzzy, so it is approximated by a TRANSPARENT heuristic stated as an explicit
assumption (per the story). Verified against a current source (2026-07-24):

  * **Conference champion**: the conference's two best teams by conference win-pct (ties → the
    engine's `_rank_key`: conf win-pct, then overall win-pct, then that sim's drawn net strength —
    a documented proxy for the real multi-way NCAA tiebreakers, which are infeasible to replay
    exactly across thousands of sims) meet in a simulated neutral CONFERENCE-CHAMPIONSHIP GAME; the
    winner is champion. A conference too small for a title game (or "FBS Independents") has no title.
  * **2026 CFP (12 teams, STRAIGHT SEEDING — the 2025-26 rule change, confirmed for 2026)**: the 5
    highest-ranked CONFERENCE CHAMPIONS auto-qualify (the 4 Power-conference champions + the single
    highest-ranked Group-of-5 champion); the remaining 7 are at-large by committee score. All 12 are
    then STRAIGHT-SEEDED by committee score (NOT the old 2024 "top-4 conference champions get the
    byes" rule); seeds 1–4 get a first-round bye, seeds 5–12 play (5v12, 6v11, 7v10, 8v9), and the
    bracket is simulated as neutral games → the national champion.
  * **Committee score** = drawn net strength − `loss_penalty`·losses (points units; blends quality
    and record transparently). Swappable via `CfpFormat`.

HONEST FRAME: futures carry a HIGH hold (20–40% on a big board) and are brand/public-shaped, so
`best_alpha = 0` applies HARD — a calibrated title-odds board is PRODUCT value regardless of edge;
an edge is only claimed if our de-vigged-vs-market number survives the deflation gate over
teams×markets×seasons (which pre-season, with no historical futures capture, it cannot yet — the
board ships honestly framed either way). This module is PURE (no IO, fully unit-tested); the driver
`run_season_simulation.py` supplies the strengths + schedule + structure from the lake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

# The served P1.4 dispersion object; the sim uses ONLY its irreducible σ₀ (fixed_strength mode).
from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_distribution import (
    NcaafGameDistributionParams,
)

# "FBS Independents" and NULL carry no conference title.
NO_CONFERENCE = frozenset({"FBS Independents", "Independent", "", None})


# ---------------------------------------------------------------------------
# Inputs (the driver assembles these from the lake; the engine never does IO)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TeamPosterior:
    """A team's pre-season (or as-of-week) strength POSTERIOR — the object the sim draws from.

    All in points vs an average FBS team. `*_sd` are the P1.2 posterior sds (parameter uncertainty;
    the once-per-season draw uses them as the season-strength spread — see `strength_sd_scale`).
    """

    team_id: int
    team: str
    conference: str
    strength_margin: float
    strength_margin_sd: float
    strength_offense: float
    strength_offense_sd: float
    strength_defense: float
    strength_defense_sd: float


@dataclass(frozen=True)
class ScheduledGame:
    """One game on the schedule. `neutral`/`is_conference_game` are structural; `played` + `home_win`
    let a MID-SEASON re-run CONDITION on games already completed (fixed, not simulated)."""

    home_id: int
    away_id: int
    neutral: bool = False
    is_conference_game: bool = False
    played: bool = False
    home_win: bool | None = None   # realized result when played (else simulated)


@dataclass
class CfpFormat:
    """The (swappable) championship-structure ruleset. Defaults = the 2026 12-team format."""

    n_playoff_teams: int = 12
    n_byes: int = 4                       # seeds 1–4 (straight seeding, 2025-26 rule)
    n_auto_qualifiers: int = 5            # 4 Power champs + 1 best Group-of-5 champion
    power_conferences: frozenset[str] = frozenset({"SEC", "Big Ten", "ACC", "Big 12"})
    straight_seeding: bool = True         # 2025-26+ ; False = the 2024 "champs seeded 1–4" rule
    loss_penalty: float = 8.0             # committee score = net_strength − loss_penalty·losses
    min_teams_for_conf_title: int = 6     # a conference smaller than this crowns no champion
    run_playoff: bool = True              # False → conference-title board only (format-independent)


@dataclass
class SeasonSimConfig:
    """Knobs for one season's simulation."""

    n_sims: int = 10_000
    # The once-per-season strength draw uses `sd × strength_sd_scale`. P1.2's sd is ~1.5× too tight
    # as a PREDICTIVE sd (documented); the P1.4 strength_posterior form recalibrated it with
    # k_margin≈0.57 for the PER-GAME width. For the SEASON draw, 1.0 uses the raw posterior sd
    # (the honest "draw from the P1.2 posterior" default per the story); the driver can widen it if
    # a held-out calibration says the futures are over-confident. Documented, swappable.
    strength_sd_scale: float = 1.0
    seed: int = 20260724


# ---------------------------------------------------------------------------
# Team indexing
# ---------------------------------------------------------------------------

@dataclass
class TeamIndex:
    """Dense 0..T-1 indexing over the season's teams + the vectors the game model needs."""

    team_ids: np.ndarray            # (T,) int
    names: list[str]
    conferences: list[str]
    margin: np.ndarray              # (T,) posterior mean net strength
    margin_sd: np.ndarray
    offense: np.ndarray
    offense_sd: np.ndarray
    defense: np.ndarray
    defense_sd: np.ndarray
    id_to_idx: dict[int, int]

    @property
    def n_teams(self) -> int:
        return len(self.team_ids)


def build_team_index(posteriors: list[TeamPosterior]) -> TeamIndex:
    ids = np.array([p.team_id for p in posteriors], dtype=np.int64)
    id_to_idx = {int(t): i for i, t in enumerate(ids)}
    if len(id_to_idx) != len(ids):
        raise ValueError("duplicate team_id in posteriors")
    return TeamIndex(
        team_ids=ids,
        names=[p.team for p in posteriors],
        conferences=[p.conference for p in posteriors],
        margin=np.array([p.strength_margin for p in posteriors], dtype=float),
        margin_sd=np.array([p.strength_margin_sd for p in posteriors], dtype=float),
        offense=np.array([p.strength_offense for p in posteriors], dtype=float),
        offense_sd=np.array([p.strength_offense_sd for p in posteriors], dtype=float),
        defense=np.array([p.strength_defense for p in posteriors], dtype=float),
        defense_sd=np.array([p.strength_defense_sd for p in posteriors], dtype=float),
        id_to_idx=id_to_idx,
    )


# ---------------------------------------------------------------------------
# Step 1 — draw each team's season strength ONCE per sim (the honest correlation)
# ---------------------------------------------------------------------------

def draw_season_strengths(
    idx: TeamIndex, n_sims: int, rng: np.random.Generator, *, sd_scale: float = 1.0,
) -> dict[str, np.ndarray]:
    """Draw (net margin, offense, defense) per team per sim — ONE draw reused across the schedule.

    The net margin is drawn from its posterior; the shock is then split into offense/defense in
    proportion to their posterior sds so `margin = offense + defense` holds EXACTLY per draw (the
    strength model gives only the net decomposition, so this is the transparent identity-preserving
    split — documented in the module header). Returns arrays shaped (n_sims, n_teams).
    """
    T = idx.n_teams
    z = rng.standard_normal((n_sims, T))
    margin = idx.margin[None, :] + (idx.margin_sd[None, :] * sd_scale) * z
    shock = margin - idx.margin[None, :]
    denom = idx.offense_sd + idx.defense_sd
    w_off = np.where(denom > 0, idx.offense_sd / np.where(denom > 0, denom, 1.0), 0.5)
    offense = idx.offense[None, :] + w_off[None, :] * shock
    defense = idx.defense[None, :] + (1.0 - w_off)[None, :] * shock
    return {"margin": margin, "offense": offense, "defense": defense}


# ---------------------------------------------------------------------------
# Step 2 — simulate every (remaining) game with the P1.4 game model (σ₀ ONLY)
# ---------------------------------------------------------------------------

def _sigma0(params: NcaafGameDistributionParams) -> tuple[float, float]:
    """The irreducible game σ (margin, total) — the fixed_strength mode. For strength_posterior it
    is (σ0_margin, σ0_total); for a homoscedastic served form it is the single served σ (there is no
    separable strength term to strip, so the whole served σ is the per-game noise)."""
    if params.form == "strength_posterior":
        return float(params.sigma0_margin), float(params.sigma0_total)
    return float(params.sigma_margin), float(params.sigma_total)


def _draw_game_margins(
    strengths: dict[str, np.ndarray], home: np.ndarray, away: np.ndarray, neutral: np.ndarray,
    hfa: float, league_base: float, params: NcaafGameDistributionParams,
    rng: np.random.Generator,
) -> np.ndarray:
    """Simulated home margin for a BATCH of games, per sim. Vectorised over sims × games.

    `home`/`away`/`neutral` are (n_games,) team-index / bool arrays; `strengths[*]` are
    (n_sims, n_teams). Returns (n_sims, n_games) home-minus-away margins. Uses σ₀ only
    (fixed_strength — the season draw already carries the strength uncertainty).
    """
    s0_m, _ = _sigma0(params)
    mu_margin = (strengths["margin"][:, home] - strengths["margin"][:, away]) \
        + np.where(neutral, 0.0, hfa)[None, :]
    z = rng.standard_normal(mu_margin.shape)
    return mu_margin + s0_m * z


# ---------------------------------------------------------------------------
# Step 3 — standings from the simulated schedule
# ---------------------------------------------------------------------------

@dataclass
class Standings:
    wins: np.ndarray          # (n_sims, n_teams) total wins
    losses: np.ndarray        # (n_sims, n_teams)
    conf_wins: np.ndarray     # (n_sims, n_teams) conference wins
    conf_games: np.ndarray    # (n_teams,) conference games scheduled (deterministic)
    games: np.ndarray         # (n_teams,) total games scheduled (deterministic)
    head_to_head: dict[tuple[int, int], np.ndarray]  # (i,j)->(n_sims,) True iff i beat j (i<j)


def simulate_regular_season(
    idx: TeamIndex, schedule: list[ScheduledGame], strengths: dict[str, np.ndarray],
    hfa: float, league_base: float, params: NcaafGameDistributionParams,
    rng: np.random.Generator,
) -> Standings:
    """Simulate every game → per-sim standings. Played games are FIXED to their realized result
    (mid-season conditioning); the rest are drawn. Batches the unplayed games into one vectorised
    margin draw for speed."""
    n_sims = strengths["margin"].shape[0]
    T = idx.n_teams
    wins = np.zeros((n_sims, T), dtype=np.int32)
    losses = np.zeros((n_sims, T), dtype=np.int32)
    conf_wins = np.zeros((n_sims, T), dtype=np.int32)
    conf_games = np.zeros(T, dtype=np.int32)
    games = np.zeros(T, dtype=np.int32)
    h2h: dict[tuple[int, int], np.ndarray] = {}

    unplayed_home, unplayed_away, unplayed_neutral, unplayed_meta = [], [], [], []
    for g in schedule:
        if g.home_id not in idx.id_to_idx or g.away_id not in idx.id_to_idx:
            continue  # a game vs a non-FBS / unrated team — outside the rated universe
        i, j = idx.id_to_idx[g.home_id], idx.id_to_idx[g.away_id]
        games[i] += 1
        games[j] += 1
        if g.is_conference_game:
            conf_games[i] += 1
            conf_games[j] += 1
        if g.played:
            if g.home_win is None:
                raise ValueError("played game missing home_win")
            hw = np.full(n_sims, bool(g.home_win))
            _record_game(wins, losses, conf_wins, h2h, i, j, hw, g.is_conference_game)
        else:
            unplayed_home.append(i)
            unplayed_away.append(j)
            unplayed_neutral.append(g.neutral)
            unplayed_meta.append((i, j, g.is_conference_game))

    if unplayed_home:
        margins = _draw_game_margins(
            strengths, np.array(unplayed_home), np.array(unplayed_away),
            np.array(unplayed_neutral, dtype=bool), hfa, league_base, params, rng,
        )
        home_wins = margins > 0  # (n_sims, n_unplayed); margin==0 → away (negligible, continuous)
        for k, (i, j, is_conf) in enumerate(unplayed_meta):
            _record_game(wins, losses, conf_wins, h2h, i, j, home_wins[:, k], is_conf)

    return Standings(wins=wins, losses=losses, conf_wins=conf_wins, conf_games=conf_games,
                     games=games, head_to_head=h2h)


def _record_game(wins, losses, conf_wins, h2h, i, j, home_win, is_conf) -> None:
    hw = home_win.astype(np.int32)
    aw = 1 - hw
    wins[:, i] += hw
    wins[:, j] += aw
    losses[:, i] += aw
    losses[:, j] += hw
    if is_conf:
        conf_wins[:, i] += hw
        conf_wins[:, j] += aw
    key = (i, j) if i < j else (j, i)
    i_beats_j = home_win if i < j else ~home_win
    prev = h2h.get(key)
    # If a pair meets twice (regular + championship), keep the LATER result as the h2h tiebreak
    # proxy; a season sweep is rare and this stays deterministic.
    h2h[key] = i_beats_j if prev is None else i_beats_j


# ---------------------------------------------------------------------------
# Step 4 — conference championships
# ---------------------------------------------------------------------------

def _rank_key(conf_win_pct, overall_win_pct, drawn_strength) -> np.ndarray:
    """A single sortable score per (sim, team) that encodes the tiebreak order: conference win-pct
    first, then overall win-pct, then drawn net strength. Composed as a lexicographic float so
    `argsort` gives the standings order. The multipliers are wide enough that a lower key never
    overtakes a higher one on the level above (win-pcts ∈ [0,1], strength ∈ ~[-45,45])."""
    return conf_win_pct * 1e6 + overall_win_pct * 1e3 + np.clip(drawn_strength, -400, 400)


@dataclass
class ConferenceResult:
    conference: str
    member_idx: list[int]
    has_title: bool
    champion_idx: np.ndarray | None   # (n_sims,) team-index of the champion, or None if no title
    finalist_idx: np.ndarray | None   # (n_sims, 2) the two title-game participants


def simulate_conference_titles(
    idx: TeamIndex, standings: Standings, strengths: dict[str, np.ndarray],
    fmt: CfpFormat, params: NcaafGameDistributionParams, rng: np.random.Generator,
    league_base: float,
) -> list[ConferenceResult]:
    """Per conference: seed by `_rank_key`, take the top 2, simulate a neutral championship GAME →
    champion. Conferences below `min_teams_for_conf_title` (or Independents) crown no champion."""
    n_sims = standings.wins.shape[0]
    conf_of = np.array(idx.conferences, dtype=object)
    overall_pct = standings.wins / np.maximum(standings.games[None, :], 1)
    conf_pct = standings.conf_wins / np.maximum(standings.conf_games[None, :], 1)

    results: list[ConferenceResult] = []
    for conf in sorted({c for c in idx.conferences if c not in NO_CONFERENCE}):
        members = [k for k in range(idx.n_teams) if conf_of[k] == conf]
        if len(members) < fmt.min_teams_for_conf_title:
            results.append(ConferenceResult(conf, members, False, None, None))
            continue
        members_arr = np.array(members)
        key = _rank_key(conf_pct[:, members_arr], overall_pct[:, members_arr],
                        strengths["margin"][:, members_arr])          # (n_sims, n_members)
        order = np.argsort(-key, axis=1)                               # best first
        top1 = members_arr[order[:, 0]]                                # (n_sims,) — varies per sim
        top2 = members_arr[order[:, 1]]
        # simulate the (neutral) championship game between the two finalists — the two team indices
        # VARY per sim, so use the per-sim-column neutral helper (NOT _draw_game_margins, whose
        # home/away are shared across sims).
        champ_is_top1 = _batch_neutral(
            strengths, top1[:, None], top2[:, None], params, rng)[:, 0] > 0
        champion = np.where(champ_is_top1, top1, top2)
        finalist = np.stack([top1, top2], axis=1)
        results.append(ConferenceResult(conf, members, True, champion, finalist))
    return results


# ---------------------------------------------------------------------------
# Step 5 — the 12-team CFP: select the field, seed, simulate the bracket
# ---------------------------------------------------------------------------

@dataclass
class PlayoffResult:
    in_field: np.ndarray       # (n_sims, n_teams) bool — made the CFP
    champion: np.ndarray       # (n_sims,) team-index of the national champion
    reached_final: np.ndarray  # (n_sims, n_teams) bool
    top_seed: np.ndarray       # (n_sims, n_teams) bool — earned a top-`n_byes` seed


def simulate_playoff(
    idx: TeamIndex, standings: Standings, strengths: dict[str, np.ndarray],
    conf_results: list[ConferenceResult], fmt: CfpFormat,
    params: NcaafGameDistributionParams, rng: np.random.Generator, league_base: float,
) -> PlayoffResult:
    """Select the 12-team field (5 champ AQs + 7 at-large), straight-seed, simulate the bracket.

    Committee score = drawn net strength − loss_penalty·losses. AQs = the 4 Power-conference
    champions + the single highest-scoring Group-of-5 champion. All 12 straight-seeded by committee
    score; seeds 1–`n_byes` bye; the rest play (5v12…8v9) as neutral games → champion.
    """
    n_sims, T = standings.wins.shape
    committee = strengths["margin"] - fmt.loss_penalty * standings.losses  # (n_sims, T)

    # champion index per conference (n_sims,), and whether each conf is a Power conf
    power_champ_cols, g5_champ_cols = [], []
    for cr in conf_results:
        if not cr.has_title or cr.champion_idx is None:
            continue
        (power_champ_cols if cr.conference in fmt.power_conferences else g5_champ_cols).append(
            cr.champion_idx)

    in_field = np.zeros((n_sims, T), dtype=bool)
    rows = np.arange(n_sims)

    # 1) auto-qualifiers: every Power champion (guaranteed, 2026 rule) + the highest-ranked
    #    Group-of-5 champion(s) needed to reach n_auto_qualifiers (2026: 4 P4 + 1 best G5 = 5).
    aq_cols: list[np.ndarray] = list(power_champ_cols)
    n_g5_slots = max(0, fmt.n_auto_qualifiers - len(power_champ_cols))
    if g5_champ_cols and n_g5_slots > 0:
        g5 = np.stack(g5_champ_cols, axis=1)                       # (n_sims, n_g5_confs)
        g5_scores = committee[rows[:, None], g5]
        g5_rank = np.argsort(-g5_scores, axis=1)                   # best G5 champ first
        for r in range(min(n_g5_slots, g5.shape[1])):
            aq_cols.append(g5[rows, g5_rank[:, r]])
    for col in aq_cols:
        in_field[rows, col] = True

    # 2) at-large: fill to n_playoff_teams by committee score among non-AQ teams
    masked = np.where(in_field, -np.inf, committee)                # AQs already in → exclude
    n_at_large = fmt.n_playoff_teams - in_field.sum(axis=1)        # per sim (AQs may be < 5 early)
    # take enough of the top to cover the max needed, then fill per sim
    order = np.argsort(-masked, axis=1)                            # best non-AQ first
    max_needed = int(np.max(n_at_large)) if n_sims else 0
    for r in range(max_needed):
        need = r < n_at_large
        pick = order[:, r]
        in_field[rows[need], pick[need]] = True

    # 3) straight seeding by committee score among the field → seeds 0..11 (0 = best)
    field_score = np.where(in_field, committee, -np.inf)
    seed_order = np.argsort(-field_score, axis=1)[:, : fmt.n_playoff_teams]  # (n_sims, 12) team idx
    top_seed = np.zeros((n_sims, T), dtype=bool)
    top_seed[rows[:, None], seed_order[:, : fmt.n_byes]] = True

    champion, reached_final = _simulate_bracket(
        seed_order, strengths, fmt, params, rng)

    return PlayoffResult(in_field=in_field, champion=champion, reached_final=reached_final,
                         top_seed=top_seed)


def _simulate_bracket(
    seed_order: np.ndarray, strengths: dict[str, np.ndarray], fmt: CfpFormat,
    params: NcaafGameDistributionParams, rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Simulate the standard 12-team seeded bracket (4 byes) → (champion (n_sims,),
    reached_final (n_sims, n_teams)).

    `seed_order` is (n_sims, 12) team indices with column 0 = the #1 seed. Structure (all neutral,
    the higher seed carried as `a`):
      Round 1  : 5v12, 6v11, 7v10, 8v9   (0-based seeds 4v11, 5v10, 6v9, 7v8)
      Quarters : 1 vs W(8v9), 2 vs W(7v10), 3 vs W(6v11), 4 vs W(5v12)
      Semis    : QF(1-side) vs QF(4-side),  QF(2-side) vs QF(3-side)
      Final    : the two semi winners
    """
    n_sims, T = strengths["margin"].shape
    if (fmt.n_playoff_teams, fmt.n_byes) != (12, 4):
        raise NotImplementedError(
            f"only the standard 12-team/4-bye bracket is implemented; got "
            f"{fmt.n_playoff_teams} teams / {fmt.n_byes} byes")
    reached_final = np.zeros((n_sims, T), dtype=bool)
    rows = np.arange(n_sims)

    def play(a_cols: np.ndarray, b_cols: np.ndarray) -> np.ndarray:
        """Winner team-indices for a (n_sims, g) batch of neutral games (a = higher seed)."""
        margins = _batch_neutral(strengths, a_cols, b_cols, params, rng)   # a − b
        return np.where(margins > 0, a_cols, b_cols)

    s = seed_order
    # Round 1: seeds [4,5,6,7] host [11,10,9,8].  r1w[:,0]=5v12 … r1w[:,3]=8v9 winner
    r1w = play(s[:, [4, 5, 6, 7]], s[:, [11, 10, 9, 8]])
    # Quarters: seed0 vs 8v9-winner(r1w[3]); seed1 vs 7v10(r1w[2]); seed2 vs 6v11(r1w[1]); seed3 vs 5v12(r1w[0])
    qf_hi = s[:, [0, 1, 2, 3]]
    qf_lo = r1w[:, [3, 2, 1, 0]]
    qfw = play(qf_hi, qf_lo)                       # qfw[:,0]=seed0-side … qfw[:,3]=seed3-side
    # Semis: (seed0-side vs seed3-side), (seed1-side vs seed2-side)
    sf_hi = qfw[:, [0, 1]]
    sf_lo = qfw[:, [3, 2]]
    sfw = play(sf_hi, sf_lo)                        # (n_sims, 2) the two finalists
    reached_final[rows[:, None], sfw] = True
    champion = play(sfw[:, [0]], sfw[:, [1]])[:, 0]
    return champion, reached_final


def _batch_neutral(
    strengths: dict[str, np.ndarray], home_cols: np.ndarray, away_cols: np.ndarray,
    params: NcaafGameDistributionParams, rng: np.random.Generator,
) -> np.ndarray:
    """Neutral-site margins for a (n_sims, n_games) batch where the team indices VARY per sim AND per
    game (home_cols/away_cols are (n_sims, n_games) team indices). Returns (n_sims, n_games)."""
    s0_m, _ = _sigma0(params)
    rows = np.arange(strengths["margin"].shape[0])[:, None]
    mu = strengths["margin"][rows, home_cols] - strengths["margin"][rows, away_cols]
    z = rng.standard_normal(mu.shape)
    return mu + s0_m * z


# ---------------------------------------------------------------------------
# Step 6 — one full season → per-team frequency board
# ---------------------------------------------------------------------------

@dataclass
class SeasonBoard:
    season: int
    teams: list[dict[str, Any]]         # per-team row: name, conf, p_conf_title, p_playoff, p_natty…
    n_sims: int
    meta: dict[str, Any] = field(default_factory=dict)


def simulate_season(
    posteriors: list[TeamPosterior], schedule: list[ScheduledGame],
    params: NcaafGameDistributionParams, hfa: float, league_base: float,
    fmt: CfpFormat, cfg: SeasonSimConfig, *, season: int = 0,
) -> SeasonBoard:
    """Run the full season Monte-Carlo → a per-team futures board.

    Returns P(win conference title), P(make the playoff), P(earn a top seed / bye), P(reach the
    national final), P(win the national championship) per team, plus expected wins.
    """
    idx = build_team_index(posteriors)
    rng = np.random.default_rng(cfg.seed)
    strengths = draw_season_strengths(idx, cfg.n_sims, rng, sd_scale=cfg.strength_sd_scale)
    standings = simulate_regular_season(idx, schedule, strengths, hfa, league_base, params, rng)
    conf_results = simulate_conference_titles(
        idx, standings, strengths, fmt, params, rng, league_base)

    T = idx.n_teams
    n_sims = cfg.n_sims
    p_conf = np.zeros(T)
    conf_title_available = np.zeros(T, dtype=bool)
    for cr in conf_results:
        if cr.has_title and cr.champion_idx is not None:
            for k in cr.member_idx:
                conf_title_available[k] = True
            counts = np.bincount(cr.champion_idx, minlength=T)
            p_conf += counts / n_sims

    p_playoff = np.zeros(T)
    p_natty = np.zeros(T)
    p_final = np.zeros(T)
    p_top_seed = np.zeros(T)
    if fmt.run_playoff:
        po = simulate_playoff(idx, standings, strengths, conf_results, fmt, params, rng, league_base)
        p_playoff = po.in_field.mean(axis=0)
        p_top_seed = po.top_seed.mean(axis=0)
        p_final = po.reached_final.mean(axis=0)
        p_natty = np.bincount(po.champion, minlength=T) / n_sims

    exp_wins = standings.wins.mean(axis=0)
    exp_losses = standings.losses.mean(axis=0)

    teams = []
    for k in range(T):
        teams.append({
            "team_id": int(idx.team_ids[k]),
            "team": idx.names[k],
            "conference": idx.conferences[k],
            "strength_margin": round(float(idx.margin[k]), 3),
            "strength_margin_sd": round(float(idx.margin_sd[k]), 3),
            "exp_wins": round(float(exp_wins[k]), 2),
            "exp_losses": round(float(exp_losses[k]), 2),
            "conf_title_available": bool(conf_title_available[k]),
            "p_conf_title": round(float(p_conf[k]), 5),
            "p_playoff": round(float(p_playoff[k]), 5),
            "p_top_seed": round(float(p_top_seed[k]), 5),
            "p_reach_final": round(float(p_final[k]), 5),
            "p_natty": round(float(p_natty[k]), 5),
        })
    teams.sort(key=lambda r: (-r["p_natty"], -r["p_playoff"], -r["p_conf_title"]))
    return SeasonBoard(season=season, teams=teams, n_sims=n_sims, meta={
        "n_teams": T, "hfa": hfa, "league_base": league_base, "form": params.form,
        "sigma0_margin": _sigma0(params)[0], "sigma0_total": _sigma0(params)[1],
        "strength_sd_scale": cfg.strength_sd_scale,
        "power_conferences": sorted(fmt.power_conferences),
        "cfp": {"n_playoff_teams": fmt.n_playoff_teams, "n_byes": fmt.n_byes,
                "n_auto_qualifiers": fmt.n_auto_qualifiers, "straight_seeding": fmt.straight_seeding,
                "loss_penalty": fmt.loss_penalty},
    })
