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
from quant_sports_intel_models.fantasy_engine.settings import (
    CoverageReport,
    DerivedBucket,
    StatTerm,
    resolve_scoring,
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
        # ── NF-C0e: the LONG-TOUCHDOWN bonus terms. Projected as `proj_<x>_td x the in-fold
        #    league 40+ share` — so the claim is "your bonus is applied in proportion to the
        #    touchdowns we project", NOT "we predict who scores long touchdowns". See
        #    `captured_terms.py`. Graduated on a held-out degenerate-baseline test (7/7 seasons,
        #    both losses); `pat_missed`, `fum` (total), `st_player_td` and `fumble_rec_td` were
        #    tested the same way, FAILED, and are deliberately absent so they stay CAPTURED.
        "pass_td_40p": "proj_pass_td_40p",
        "rush_td_40p": "proj_rush_td_40p",
        "rec_td_40p": "proj_rec_td_40p",
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
        # NF-C0e — the column was in `stg_nfl_team_week` all along and simply never loaded. It
        # beats the league-mean degenerate on both losses in 16/16 held-out seasons, a WIDER
        # margin than `def_sacks` (which was already applied).
        "def_forced_fumble": "proj_def_forced_fumble",
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
        # ⭐ NF-C0e — the YARDS-ALLOWED TIER terms, the structural twin of the block above and the
        #    single highest-|weight| family the import machinery was forced to call CAPTURED
        #    (Sleeper prices it +6 to -6, ESPN +5 to -7). Same construction: each column is the
        #    EXPECTED NUMBER OF GAMES landing in that yards-allowed bucket, so a per-game tier
        #    table scores a season as `sum_bucket tier_points x expected_games` — LINEAR in these
        #    columns, hence the league's own table applied EXACTLY rather than approximated, with
        #    no engine change. Unlike the points ladder (where ESPN's 18-21/22-27 split forces one
        #    disclosed boundary), the nine yards rungs are IDENTICAL on Sleeper and ESPN.
        "dst_ya_g_0_99": "proj_dst_ya_g_0_99",
        "dst_ya_g_100_199": "proj_dst_ya_g_100_199",
        "dst_ya_g_200_299": "proj_dst_ya_g_200_299",
        "dst_ya_g_300_349": "proj_dst_ya_g_300_349",
        "dst_ya_g_350_399": "proj_dst_ya_g_350_399",
        "dst_ya_g_400_449": "proj_dst_ya_g_400_449",
        "dst_ya_g_450_499": "proj_dst_ya_g_450_499",
        "dst_ya_g_500_549": "proj_dst_ya_g_500_549",
        "dst_ya_g_550p": "proj_dst_ya_g_550p",
        "dst_yards_allowed": "proj_dst_yards_allowed",
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


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# NF-C0b — the MANUAL league-settings EDITOR's catalog + honest coverage policy
# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The presets above are the four-or-so shapes we ship. A real league is not one of them, and when a
# platform import can't reach it (private league, long-tail platform, a fragile ESPN endpoint) the
# user must be able to type it in. That means the editor has to offer EVERY term a real league scores
# — including terms our season projection does not produce. `fantasy_engine.settings` classifies each
# one mechanically; this section is only the NFL POLICY: what the terms are and how the ones we
# resolve more coarsely fold.

# ── FIELD GOALS: the league's table is finer than the projection's ────────────────────────────────
# Leagues (and the operator's Sleeper screenshots) express FG in SIX distance buckets. NF1.6's kicker
# projection resolves three: 0-39 / 40-49 / 50+. The three sub-40 buckets therefore fold onto
# `fg_made_0_39`, and 50-59 / 60+ fold onto `fg_made_50_plus`.
#
# ⭐ WHY THIS IS USUALLY LOSSLESS: almost every league pays the SAME for a 22-, 28- and 35-yarder, so
# the fine values inside a projected bucket agree and the fold is EXACT — the shares below never
# enter the arithmetic. They matter only for the genuinely-rare league that prices 30-39 above 20-29,
# and in that case `resolve_scoring` reports `exact=False` so the surface can say the term is
# approximated rather than pretending to a resolution the projection does not have.
#
# ⚠️ THE SHARES ARE A STATED ASSUMPTION, NOT A MEASUREMENT. They encode only the uncontroversial
# ordering that a sub-20 attempt is vanishingly rare (a kick from inside the 2), that 30-39 dominates
# the sub-40 bucket, and that 60+ is a small slice of the 50+ bucket. They are deliberately NOT
# presented as fitted quantities, and nothing selects or gates on them.
_FG_SUB40_SHARES = {"fg_made_0_19": 0.02, "fg_made_20_29": 0.30, "fg_made_30_39": 0.68}
_FG_50PLUS_SHARES = {"fg_made_50_59": 0.88, "fg_made_60p": 0.12}

FG_DERIVED_BUCKETS: tuple[DerivedBucket, ...] = tuple(
    [DerivedBucket(k, "fg_made_0_39", s) for k, s in _FG_SUB40_SHARES.items()]
    + [DerivedBucket(k, "fg_made_50_plus", s) for k, s in _FG_50PLUS_SHARES.items()]
)
# 40-49 needs no fold: the league bucket and the projected bucket are the same bucket.

# ── THE EDITOR CATALOG ────────────────────────────────────────────────────────────────────────────
# `default` is the modal league value (what a fresh custom config seeds to). A term absent from
# `NFL_PROFILE.stat_columns` scores nothing and is reported CAPTURED — that is the mechanism, so a
# term is never listed here as applied; `resolve_scoring` decides, against the real columns.
SCORING_CATALOG: tuple[StatTerm, ...] = (
    # passing
    StatTerm("pass_yds", "Passing yards", "passing", 0.04, "Points per passing yard (0.04 = 1 per 25)."),
    StatTerm("pass_td", "Passing TD", "passing", 4.0),
    StatTerm("pass_int", "Interception thrown", "passing", -2.0),
    StatTerm("pass_cmp", "Completion", "passing", 0.0, "Some leagues add a per-completion bonus."),
    StatTerm("pass_att", "Pass attempt", "passing", 0.0),
    # rushing
    StatTerm("rush_yds", "Rushing yards", "rushing", 0.1, "Points per rushing yard (0.1 = 1 per 10)."),
    StatTerm("rush_td", "Rushing TD", "rushing", 6.0),
    StatTerm("rush_att", "Rush attempt", "rushing", 0.0),
    # receiving
    StatTerm("rec", "Reception (PPR)", "receiving", 1.0, "1.0 full PPR, 0.5 half, 0 standard."),
    StatTerm("rec_yds", "Receiving yards", "receiving", 0.1),
    StatTerm("rec_td", "Receiving TD", "receiving", 6.0),
    StatTerm("targets", "Target", "receiving", 0.0),
    # misc offence
    StatTerm("two_pt", "2-point conversion", "misc", 2.0),
    StatTerm("fumbles_lost", "Fumble lost", "misc", -2.0),
    StatTerm("fumble_rec_td", "Fumble recovery TD", "misc", 6.0,
             "Offensive player recovering a fumble in the end zone."),
    StatTerm("st_player_td", "Return TD (player)", "misc", 6.0,
             "A kick/punt return TD credited to a skill player."),
    # NF-C0e — the long-touchdown bonuses. Applied in proportion to PROJECTED touchdowns using the
    # measured league 40+ share; we do not claim to know WHO scores long ones (see captured_terms).
    StatTerm("pass_td_40p", "40+ yard passing TD bonus", "passing", 0.0,
             "Extra points for a touchdown pass of 40+ yards, on top of the passing-TD value."),
    StatTerm("rush_td_40p", "40+ yard rushing TD bonus", "rushing", 0.0,
             "Extra points for a rushing touchdown of 40+ yards, on top of the rushing-TD value."),
    StatTerm("rec_td_40p", "40+ yard receiving TD bonus", "receiving", 0.0,
             "Extra points for a receiving touchdown of 40+ yards, on top of the receiving-TD value."),
    # kicking — the SIX league buckets; three of them fold (see FG_DERIVED_BUCKETS)
    StatTerm("fg_made_0_19", "FG made 0-19", "kicking", 3.0),
    StatTerm("fg_made_20_29", "FG made 20-29", "kicking", 3.0),
    StatTerm("fg_made_30_39", "FG made 30-39", "kicking", 3.0),
    StatTerm("fg_made_40_49", "FG made 40-49", "kicking", 4.0),
    StatTerm("fg_made_50_59", "FG made 50-59", "kicking", 5.0),
    StatTerm("fg_made_60p", "FG made 60+", "kicking", 5.0),
    StatTerm("fg_missed", "FG missed", "kicking", 0.0, "Often -1; leave 0 if your league does not penalise."),
    StatTerm("pat_made", "PAT made", "kicking", 1.0),
    StatTerm("pat_missed", "PAT missed", "kicking", 0.0),
    # team defence
    StatTerm("def_td", "Defensive TD", "defense", 6.0),
    StatTerm("st_td", "Special-teams TD (team)", "defense", 6.0),
    StatTerm("def_sacks", "Sack", "defense", 1.0),
    StatTerm("def_int", "Interception", "defense", 2.0),
    StatTerm("def_fumble_rec", "Fumble recovered", "defense", 2.0),
    StatTerm("def_forced_fumble", "Fumble forced", "defense", 0.0),
    StatTerm("def_safety", "Safety", "defense", 2.0),
    StatTerm("def_blocked_kick", "Blocked kick", "defense", 2.0),
    # team defence — points-allowed tiers. Nine buckets = the common refinement of the ESPN and Yahoo
    # tables, so a 7-tier league table restates EXACTLY (see `merge_group`).
    StatTerm("dst_pa_g_0", "Points allowed 0", "dst_points_allowed", 5.0),
    StatTerm("dst_pa_g_1_6", "Points allowed 1-6", "dst_points_allowed", 4.0),
    StatTerm("dst_pa_g_7_13", "Points allowed 7-13", "dst_points_allowed", 3.0),
    StatTerm("dst_pa_g_14_17", "Points allowed 14-17", "dst_points_allowed", 1.0, merge_group="pa_14_20"),
    StatTerm("dst_pa_g_18_20", "Points allowed 18-20", "dst_points_allowed", 0.0, merge_group="pa_14_20"),
    StatTerm("dst_pa_g_21_27", "Points allowed 21-27", "dst_points_allowed", 0.0),
    StatTerm("dst_pa_g_28_34", "Points allowed 28-34", "dst_points_allowed", -1.0),
    StatTerm("dst_pa_g_35_45", "Points allowed 35-45", "dst_points_allowed", -3.0, merge_group="pa_35p"),
    StatTerm("dst_pa_g_46p", "Points allowed 46+", "dst_points_allowed", -5.0, merge_group="pa_35p"),
    # ── NF-C0e: team defence — YARDS-allowed tiers ────────────────────────────────────────────
    # Defaults are 0: unlike the points ladder, a yards-allowed table is an OPT-IN a minority of
    # leagues set, so seeding non-zero values would invent a rule for every league that lacks one.
    # The nine rungs are exactly Sleeper's self-describing keys and exactly ESPN's 128..136.
    StatTerm("dst_ya_g_0_99", "Yards allowed under 100", "dst_yards_allowed", 0.0),
    StatTerm("dst_ya_g_100_199", "Yards allowed 100-199", "dst_yards_allowed", 0.0),
    StatTerm("dst_ya_g_200_299", "Yards allowed 200-299", "dst_yards_allowed", 0.0),
    StatTerm("dst_ya_g_300_349", "Yards allowed 300-349", "dst_yards_allowed", 0.0),
    StatTerm("dst_ya_g_350_399", "Yards allowed 350-399", "dst_yards_allowed", 0.0),
    StatTerm("dst_ya_g_400_449", "Yards allowed 400-449", "dst_yards_allowed", 0.0),
    StatTerm("dst_ya_g_450_499", "Yards allowed 450-499", "dst_yards_allowed", 0.0),
    StatTerm("dst_ya_g_500_549", "Yards allowed 500-549", "dst_yards_allowed", 0.0),
    StatTerm("dst_ya_g_550p", "Yards allowed 550+", "dst_yards_allowed", 0.0),
)

# Groups the editor renders, in order, with the honest header each one needs.
SCORING_GROUPS: tuple[tuple[str, str], ...] = (
    ("passing", "Passing"),
    ("rushing", "Rushing"),
    ("receiving", "Receiving"),
    ("misc", "Miscellaneous"),
    ("kicking", "Kicking (K)"),
    ("defense", "Team defense (D/ST)"),
    ("dst_points_allowed", "D/ST points allowed"),
    ("dst_yards_allowed", "D/ST yards allowed"),
)

# Rules a league genuinely has that DO NOT move a per-player projection or value-over-replacement.
# Offered in the editor so a config is a faithful record of the league, stored in
# `LeagueConfig.captured_rules`, and never read by the engine. See that field's docstring.
CAPTURED_RULE_CATALOG: tuple[tuple[str, str, str], ...] = (
    (
        "median_scoring",
        "Second matchup vs the league median",
        "A standings/schedule rule: each week you also play the league median. It changes WIN-LOSS "
        "records, not what any player is projected to score, so it does not affect the board.",
    ),
    (
        "fractional_scoring",
        "Fractional (decimal) scoring",
        "Recorded for fidelity. The board is computed in decimals regardless, so this changes nothing "
        "about the ranking.",
    ),
    (
        "playoff_weeks",
        "Playoff weeks",
        "Recorded for fidelity. Season-long projections are full-season totals, so the playoff "
        "schedule does not enter the board.",
    ),
)


# The roster shape the operator's Sleeper screenshots show, and a good starting point for a
# hand-entered league: 1QB/2RB/2WR/1TE/2 W-R-T flex/1K/1DEF + 5 bench + 3 IR.
# ⭐ IR needs no schema change: it is a BENCH slot (`bench=True`), so like BN it contributes NO
# starter demand and therefore cannot move replacement level — which is exactly right, since an IR
# spot never starts. The two are distinguished by NAME only, which is all the fidelity a projection
# board needs. A bench slot is also allowed an EMPTY eligibility list (`validate` only requires
# starters to declare one), so "IR: any position" is representable as-is.
_EDITOR_DEFAULT_ROSTER = (
    RosterSlot("QB", 1, ("QB",)),
    RosterSlot("RB", 2, ("RB",)),
    RosterSlot("WR", 2, ("WR",)),
    RosterSlot("TE", 1, ("TE",)),
    RosterSlot("FLEX", 2, _FLEX_ELIG),
    RosterSlot("K", 1, ("K",)),
    RosterSlot("DST", 1, ("DST",)),
    RosterSlot("BN", 5, ("QB", "RB", "WR", "TE", "K", "DST"), bench=True),
    RosterSlot("IR", 3, (), bench=True),
)


def default_custom_roster() -> tuple[RosterSlot, ...]:
    """The roster a fresh custom league starts from (editable in full by the editor)."""
    return _EDITOR_DEFAULT_ROSTER


def default_custom_scoring() -> dict[str, float]:
    """The catalog's defaults as a `per_stat` map — what a brand-new custom config starts from."""
    return {t.key: float(t.default) for t in SCORING_CATALOG}


def resolve_config(
    config: LeagueConfig, *, available_columns: frozenset[str] | None = None
) -> tuple[LeagueConfig, CoverageReport]:
    """Fold a (possibly hand-entered) config onto what the NFL projection can express + report coverage.

    This is the ONE place a manually-built config and an imported one are treated identically: both
    are just `LeagueConfig`s, both go through this, and the board is scored from the result. Returns
    `(config_ready_to_score, report)` — the report is what the UI renders as applied / derived /
    captured, so the surface never has to guess which of a user's settings actually moved a number.
    """
    resolved, report = resolve_scoring(
        config.scoring,
        NFL_PROFILE,
        derived_buckets=FG_DERIVED_BUCKETS,
        available_columns=available_columns,
        captured_rules=tuple(str(k) for k in config.captured_rules),
    )
    return config.with_overrides(scoring=resolved), report


def custom_config(base: str = "full_ppr", *, n_teams: int = 12, **overrides) -> LeagueConfig:
    """A preset with field overrides — the 'custom format' path. `overrides` are `LeagueConfig` fields
    (e.g. `scoring=ScoringRules(...)`, `roster=(...)`, `n_teams=10`). Example: a 6-pt passing-TD, 10-team
    full-PPR = `custom_config("full_ppr", n_teams=10, scoring=ScoringRules({**base_scoring, "pass_td":6, "rec":1.0}))`.
    """
    cfg = get_preset(base, n_teams)
    if overrides:
        cfg = cfg.with_overrides(**overrides)
    return cfg
