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
        # ── NF1.6: KICKER raw components (distance-bucketed, so a league's own 3/4/5 — or any
        #    other per-distance schedule — is expressed exactly rather than approximated) ───────
        "fg_att": "proj_fg_att",
        "fg_made": "proj_fg_made",
        "fg_made_0_39": "proj_fg_made_0_39",
        "fg_made_40_49": "proj_fg_made_40_49",
        "fg_made_50_plus": "proj_fg_made_50_plus",
        "fg_missed": "proj_fg_missed",
        "pat_att": "proj_pat_att",
        "pat_made": "proj_pat_made",
        # ── NF1.6: TEAM DEFENSE (DST) raw components ──────────────────────────────────────────
        "def_sacks": "proj_def_sacks",
        "def_int": "proj_def_int",
        "def_fumble_rec": "proj_def_fumble_rec",
        "def_td": "proj_def_td",
        "st_td": "proj_st_td",
        "def_safety": "proj_def_safety",
        "def_blocked_kick": "proj_def_blocked_kick",
        "dst_points_allowed": "proj_dst_points_allowed",
        # ⭐ The POINTS-ALLOWED TIER terms. Each column is the EXPECTED NUMBER OF GAMES landing in
        #    that points-allowed bucket, so a per-game tier table scores a season as
        #    `Σ_bucket tier_points × expected_games` — LINEAR in these columns, which is what lets
        #    the sport-agnostic scorer express any tier scheme EXACTLY with no engine change (and
        #    is why NF-C0b's tier work needs no new plumbing, only its own `per_stat` weights).
        #    The nine edges are the common refinement of the ESPN and Yahoo schemes, so both are
        #    exact unions of them. See `kdst_projection.PA_BUCKET_LABELS`.
        "dst_pa_g_0": "proj_dst_pa_g_0",
        "dst_pa_g_1_6": "proj_dst_pa_g_1_6",
        "dst_pa_g_7_13": "proj_dst_pa_g_7_13",
        "dst_pa_g_14_17": "proj_dst_pa_g_14_17",
        "dst_pa_g_18_20": "proj_dst_pa_g_18_20",
        "dst_pa_g_21_27": "proj_dst_pa_g_21_27",
        "dst_pa_g_28_34": "proj_dst_pa_g_28_34",
        "dst_pa_g_35_45": "proj_dst_pa_g_35_45",
        "dst_pa_g_46p": "proj_dst_pa_g_46p",
    },
    positions=("QB", "RB", "WR", "TE", "K", "DST"),
    position_column="position",
    base_points_column="proj_fp_ppr",   # the MVP-1 convenience total the interval was built on
    base_sd_column="fp_ppr_sd",
    # NF1.7: carry the projection's OWN bounds so an ASYMMETRIC band survives the rescore. The rookie
    # band is heavily right-skewed (a late pick's p10 is ~0 and his p90 is a real season), and
    # rebuilding it from a single sd would silently re-centre it — the CV path stays as the fallback.
    base_p10_column="fp_ppr_p10",
    base_p90_column="fp_ppr_p90",
    # NF1.6: the K/DST projection duplicates its convenience total + bounds into the SAME four
    # columns, so a `concat` of the offensive and K/DST projections scores under this one profile.
    # ⚠️ K/DST bands are MORE skewed than any offensive position (both targets floor at 0 and a cut
    # kicker realises exactly 0), so the per-side p10/p90 path above is what keeps the rescore
    # coherent for them — a single-`sd` reconstruction would re-symmetrise a band whose p10 IS 0.
    position_aliases={
        "FB": "RB",          # fullbacks are RB / flex-eligible, not an un-scarce island
        # NF1.6: platform feeds spell the two new positions several ways — fold them all onto the
        # canonical codes so an imported league config never creates a phantom position with no
        # projections behind it.
        "DEF": "DST", "D/ST": "DST", "DEFENSE": "DST", "D": "DST",
        "PK": "K", "KICKER": "K",
    },
)

# Standard NFL scoring shared by every preset (only the per-reception weight + roster differ). 4-pt
# passing TD is the modal default; a league can override to 6 via `custom_config`.
_BASE_SCORING = {
    "pass_yds": 0.04, "pass_td": 4.0, "pass_int": -2.0,
    "rush_yds": 0.1, "rush_td": 6.0,
    "rec_yds": 0.1, "rec_td": 6.0,
    "fumbles_lost": -2.0, "two_pt": 2.0,
}

# ── NF1.6: default KICKER + DST scoring, shared by every preset ────────────────────────────────
# The modal defaults (ESPN/Yahoo agree on distance-bucketed FG 3/4/5 and PAT 1). A league overrides
# any of these through `custom_config(scoring=ScoringRules(...))` exactly like the offensive terms —
# nothing here is special-cased in the engine.
_K_SCORING = {
    "fg_made_0_39": 3.0, "fg_made_40_49": 4.0, "fg_made_50_plus": 5.0, "pat_made": 1.0,
}
# The ESPN-default DST takeaway terms.
_DST_SCORING = {
    "def_sacks": 1.0, "def_int": 2.0, "def_fumble_rec": 2.0, "def_td": 6.0, "st_td": 6.0,
    "def_safety": 2.0, "def_blocked_kick": 2.0,
}
# ⭐ The ESPN-default POINTS-ALLOWED TIER table, expressed as per-bucket weights on the
# expected-games columns. Because those columns are `games × P(bucket)`, this linear form is the
# tier table EXACTLY — not an approximation of it. Yahoo's scheme differs only in these weights
# (its 14-20 tier = our 14_17 + 18_20, its 21-27 = our 21_27, its 35+ = our 35_45 + 46p), which is
# why the nine buckets were chosen as the common refinement of the two.
_DST_PA_TIER_SCORING = {
    "dst_pa_g_0": 5.0, "dst_pa_g_1_6": 4.0, "dst_pa_g_7_13": 3.0, "dst_pa_g_14_17": 1.0,
    "dst_pa_g_18_20": 0.0, "dst_pa_g_21_27": 0.0, "dst_pa_g_28_34": -1.0,
    "dst_pa_g_35_45": -3.0, "dst_pa_g_46p": -5.0,
}
_KDST_SCORING = {**_K_SCORING, **_DST_SCORING, **_DST_PA_TIER_SCORING}

# Flex eligibility conventions (a league can redefine per slot).
_FLEX_ELIG = ("RB", "WR", "TE")
_SUPERFLEX_ELIG = ("QB", "RB", "WR", "TE")

# Standard redraft starting lineup (dedicated + one FLEX) + bench. ⭐ NF1.6: the K and DST slots are
# now BACKED BY A PROJECTION (`run_kdst_projection`) — before it they were declared for completeness
# but contributed no ranked players, so the slots rendered "not projected". They rank on a
# deliberately BASE model with wide honest intervals; read them as streaming tiers, not fine ranks.
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
    per_stat = dict(_BASE_SCORING, **_KDST_SCORING, rec=rec_pts)
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
