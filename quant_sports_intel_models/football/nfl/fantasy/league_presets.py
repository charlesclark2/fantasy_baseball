"""league_presets.py — the NFL instantiation of the sport-agnostic fantasy engine (NF-C1-lite).

Provides the NFL `SportProfile` (which MVP-1 raw columns map to which canonical scoring stats) and the
shipped format PRESETS (standard / half-PPR / full-PPR / superflex) + a custom-override helper. The
scoring/VOR LOGIC lives in `quant_sports_intel_models.fantasy_engine`; this file is only the NFL policy
+ column mapping, so MLB's `F-C1` reuses the same engine with its own profile + presets.

The raw-column names come straight from the MVP-1 output contract (`mart_nfl_fantasy_season_projection`
/ `season_projection.RAW_STAT_COLS`): season TOTALS `proj_pass_yds`, `proj_rush_td`, `proj_rec`, … We
RESCORE from that raw line — never the `proj_fp_*` convenience columns.
"""
from __future__ import annotations

from quant_sports_intel_models.fantasy_engine.league_config import (
    LeagueConfig,
    RosterSlot,
    ScoringRules,
    SportProfile,
)

# ── NFL sport profile: canonical stat_key → MVP-1 raw projection column ───────────────────────────
NFL_PROFILE = SportProfile(
    sport="nfl",
    stat_columns={
        "pass_att": "proj_pass_att",
        "pass_cmp": "proj_pass_cmp",
        "pass_yds": "proj_pass_yds",
        "pass_td": "proj_pass_td",
        "pass_int": "proj_pass_int",
        "rush_att": "proj_rush_att",
        "rush_yds": "proj_rush_yds",
        "rush_td": "proj_rush_td",
        "targets": "proj_targets",
        "rec": "proj_rec",
        "rec_yds": "proj_rec_yds",
        "rec_td": "proj_rec_td",
        "fumbles_lost": "proj_fumbles_lost",
        "two_pt": "proj_two_pt",
    },
    positions=("QB", "RB", "WR", "TE"),
    position_column="position",
    base_points_column="proj_fp_ppr",   # the MVP-1 convenience total the interval was built on
    base_sd_column="fp_ppr_sd",
    position_aliases={"FB": "RB"},       # fullbacks are RB / flex-eligible, not an un-scarce island
)

# Standard NFL scoring shared by every preset (only the per-reception weight + roster differ). 4-pt
# passing TD is the modal default; a league can override to 6 via `custom_config`.
_BASE_SCORING = {
    "pass_yds": 0.04, "pass_td": 4.0, "pass_int": -2.0,
    "rush_yds": 0.1, "rush_td": 6.0,
    "rec_yds": 0.1, "rec_td": 6.0,
    "fumbles_lost": -2.0, "two_pt": 2.0,
}

# Flex eligibility conventions (a league can redefine per slot).
_FLEX_ELIG = ("RB", "WR", "TE")
_SUPERFLEX_ELIG = ("QB", "RB", "WR", "TE")

# Standard redraft starting lineup (dedicated + one FLEX) + bench. K/DST are declared for completeness
# but the MVP-1 projection carries no K/DST line, so they contribute no ranked players (kept honest).
_STD_ROSTER = (
    RosterSlot("QB", 1, ("QB",)),
    RosterSlot("RB", 2, ("RB",)),
    RosterSlot("WR", 2, ("WR",)),
    RosterSlot("TE", 1, ("TE",)),
    RosterSlot("FLEX", 1, _FLEX_ELIG),
    RosterSlot("K", 1, ("K",)),
    RosterSlot("DST", 1, ("DST",)),
    RosterSlot("BN", 6, ("QB", "RB", "WR", "TE"), bench=True),
)
# The modern "3-WR" starting lineup (1QB/2RB/3WR/1TE/1FLEX) — a very common redraft shape that
# starts an extra WR (raising WR starter demand → deeper WR replacement level → more WRs are startable).
_STD_ROSTER_3WR = (
    RosterSlot("QB", 1, ("QB",)),
    RosterSlot("RB", 2, ("RB",)),
    RosterSlot("WR", 3, ("WR",)),
    RosterSlot("TE", 1, ("TE",)),
    RosterSlot("FLEX", 1, _FLEX_ELIG),
    RosterSlot("K", 1, ("K",)),
    RosterSlot("DST", 1, ("DST",)),
    RosterSlot("BN", 6, ("QB", "RB", "WR", "TE"), bench=True),
)
# Superflex adds an OP/SUPERFLEX slot (QB-eligible) — the format that makes QBs scarce.
_SUPERFLEX_ROSTER = (
    RosterSlot("QB", 1, ("QB",)),
    RosterSlot("RB", 2, ("RB",)),
    RosterSlot("WR", 2, ("WR",)),
    RosterSlot("TE", 1, ("TE",)),
    RosterSlot("FLEX", 1, _FLEX_ELIG),
    RosterSlot("SUPERFLEX", 1, _SUPERFLEX_ELIG),
    RosterSlot("K", 1, ("K",)),
    RosterSlot("DST", 1, ("DST",)),
    RosterSlot("BN", 6, ("QB", "RB", "WR", "TE"), bench=True),
)


def _scoring(rec_pts: float, te_premium: float = 0.0) -> ScoringRules:
    per_stat = dict(_BASE_SCORING, rec=rec_pts)
    bonuses = {"TE": {"rec": te_premium}} if te_premium else {}
    return ScoringRules(per_stat=per_stat, position_bonuses=bonuses)


def standard(n_teams: int = 12) -> LeagueConfig:
    return LeagueConfig(
        name="standard", sport="nfl", n_teams=n_teams, ppr="standard",
        scoring=_scoring(0.0), roster=_STD_ROSTER,
        description="Standard (non-PPR), 12-team, 1QB/2RB/2WR/1TE/1FLEX.",
    ).validate()


def half_ppr(n_teams: int = 12) -> LeagueConfig:
    return LeagueConfig(
        name="half_ppr", sport="nfl", n_teams=n_teams, ppr="half",
        scoring=_scoring(0.5), roster=_STD_ROSTER,
        description="Half-PPR (0.5/reception), 12-team, 1QB/2RB/2WR/1TE/1FLEX.",
    ).validate()


def full_ppr(n_teams: int = 12) -> LeagueConfig:
    return LeagueConfig(
        name="full_ppr", sport="nfl", n_teams=n_teams, ppr="ppr",
        scoring=_scoring(1.0), roster=_STD_ROSTER,
        description="Full-PPR (1.0/reception), 12-team, 1QB/2RB/2WR/1TE/1FLEX.",
    ).validate()


def superflex(n_teams: int = 12) -> LeagueConfig:
    return LeagueConfig(
        name="superflex", sport="nfl", n_teams=n_teams, ppr="ppr", superflex=True,
        scoring=_scoring(1.0), roster=_SUPERFLEX_ROSTER,
        description="Superflex full-PPR, 12-team, adds a QB-eligible SUPERFLEX slot.",
    ).validate()


def standard_3wr(n_teams: int = 12) -> LeagueConfig:
    return LeagueConfig(
        name="standard_3wr", sport="nfl", n_teams=n_teams, ppr="standard",
        scoring=_scoring(0.0), roster=_STD_ROSTER_3WR,
        description="Standard (non-PPR), 12-team, 1QB/2RB/3WR/1TE/1FLEX (3-WR roster).",
    ).validate()


def half_ppr_3wr(n_teams: int = 12) -> LeagueConfig:
    return LeagueConfig(
        name="half_ppr_3wr", sport="nfl", n_teams=n_teams, ppr="half",
        scoring=_scoring(0.5), roster=_STD_ROSTER_3WR,
        description="Half-PPR (0.5/reception), 12-team, 1QB/2RB/3WR/1TE/1FLEX (3-WR roster).",
    ).validate()


def full_ppr_3wr(n_teams: int = 12) -> LeagueConfig:
    return LeagueConfig(
        name="full_ppr_3wr", sport="nfl", n_teams=n_teams, ppr="ppr",
        scoring=_scoring(1.0), roster=_STD_ROSTER_3WR,
        description="Full-PPR (1.0/reception), 12-team, 1QB/2RB/3WR/1TE/1FLEX (3-WR roster).",
    ).validate()


def te_premium(n_teams: int = 12, premium: float = 0.5) -> LeagueConfig:
    """Full-PPR with an extra +premium per TE reception (the TE-premium format)."""
    return LeagueConfig(
        name="te_premium", sport="nfl", n_teams=n_teams, ppr="ppr",
        scoring=_scoring(1.0, te_premium=premium), roster=_STD_ROSTER,
        description=f"Full-PPR + {premium}/reception TE premium, 12-team.",
    ).validate()


# The shipped presets. The 4 gate presets (2-WR roster) + the common 3-WR roster across PPR variants
# + TE-premium (a demonstrator of position bonuses). All share the sport-agnostic engine.
PRESETS = {
    "standard": standard,
    "half_ppr": half_ppr,
    "full_ppr": full_ppr,
    "superflex": superflex,
    "standard_3wr": standard_3wr,
    "half_ppr_3wr": half_ppr_3wr,
    "full_ppr_3wr": full_ppr_3wr,
    "te_premium": te_premium,
}


def get_preset(name: str, n_teams: int = 12) -> LeagueConfig:
    if name not in PRESETS:
        raise KeyError(f"unknown preset {name!r}; choose from {sorted(PRESETS)}")
    return PRESETS[name](n_teams)


def custom_config(base: str = "full_ppr", *, n_teams: int = 12, **overrides) -> LeagueConfig:
    """A preset with field overrides — the 'custom format' path. `overrides` are `LeagueConfig` fields
    (e.g. `scoring=ScoringRules(...)`, `roster=(...)`, `n_teams=10`). Example: a 6-pt passing-TD, 10-team
    full-PPR = `custom_config("full_ppr", n_teams=10, scoring=ScoringRules({**base_scoring, "pass_td":6, "rec":1.0}))`.
    """
    cfg = get_preset(base, n_teams)
    if overrides:
        cfg = cfg.with_overrides(**overrides)
    return cfg
