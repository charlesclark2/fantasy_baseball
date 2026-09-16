"""NF-WK-RC1 — the REALIZED weekly stat line, mapped onto the ONE scorer's own stat keys.

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
═══════════════════════════════════════════════════════════════════════════════════════════════════

`projection_fields.STAT_FIELD` maps the scorer's stat keys onto the fields the PROJECTION payload
serves them under. This module is its REALIZED twin: the same keys, mapped onto the columns
`nflverse.stats_player_week` actually carries, so a completed week can go through
`league_scoring.score_row` with NOTHING ELSE CHANGED.

⛔ IT IS NOT A FOURTH SCORER. Nothing here multiplies a weight by a stat. `score_row` already takes
`stat_field` as a PARAMETER — that is the seam NF-WK-MT1 used for the projected line, and this is
the same seam used again. `resolve_scoring` likewise takes `fields=`, so the per-league coverage
report comes out of the existing machinery rather than out of a second implementation of it.

───────────────────────────────────────────────────────────────────────────────────────────────────
⭐⭐ THE KEY SET IS THE SCORER'S, NEVER THIS FILE'S — AND THAT IS ENFORCED, NOT INTENDED
───────────────────────────────────────────────────────────────────────────────────────────────────

`resolve_realized_fields` RAISES on any key this module names that `STAT_FIELD` does not know,
exactly as `nfl_weekly.resolve_component_fields` does for the projected component head. A
hand-typed realized map is a DENYLIST in disguise: it would drift the moment someone teaches the
scorer a new term, and the drift would present as a league's weight scoring zero behind an
"applied" label — the NF-C0e wrong-key class, whose whole harm is that an unrecognized key passes
through silently.

The converse direction — a scorer key this module has no realized source for — is NOT an error. It
is the honest ABSENCE that makes `resolve_scoring` classify that league's term CAPTURED, which is
the difference between "your fumble scoring contributed nothing" and "your fumble scoring is not in
this number". Only the second is true, and only the second is what we say.

───────────────────────────────────────────────────────────────────────────────────────────────────
🕳️ THE THREE WRONG-KEY TRAPS THIS TABLE SETS, ALL MEASURED RATHER THAN REASONED
───────────────────────────────────────────────────────────────────────────────────────────────────

1. ⭐ `passing_40` / `rushing_40` / `receiving_40` ARE NOT 40+ YARD TOUCHDOWN COUNTS. They are
   40+ yard PLAY counts, and they are the nearest-looking column to the scorer's `pass_td_40p` /
   `rush_td_40p` / `rec_td_40p`. Measured on 2025 REG: `passing_40` EXCEEDS `passing_tds` on 36
   player-weeks and `receiving_40` exceeds `receiving_tds` on 108 — impossible for a subset of the
   touchdown count, which settles it. The authoritative derivation for those three terms is
   `run_nf_c0e_captured_terms._PLAYER_TERM_SQL`, and it reads `pbp` (`pass_touchdown = 1 AND
   yards_gained >= 40`), NOT this table. So they are ABSENT here, on purpose.

2. `fg_blocked` / `pat_blocked` / `pt_blocked` are the KICKING side's own blocked kicks, not the
   defence's `def_blocked_kick`. This table's defensive block carries no blocked-kick column at
   all, so that term is absent rather than mapped onto a column that counts the opposite team's
   event.

3. The `dst_*` family is TEAM-grained (points and yards allowed). `stats_player_week` is
   player-grained and carries neither. They are absent here; supplying them needs a team-level
   source, which is a deliberate second read rather than a column on this row.

───────────────────────────────────────────────────────────────────────────────────────────────────
THE SUMMED TERMS ARE EXACT, AND THEIR DIRECTION MATTERS
───────────────────────────────────────────────────────────────────────────────────────────────────

Three keys are a SUM of realized columns rather than one of them. Each is exact — a total, not an
apportionment — which is the opposite of the projected side's `FG_DERIVED_BUCKETS`, where a league's
six fine buckets are folded DOWN onto three coarse projected ones by attempt share and the fold can
be inexact. Realized data runs the other way: it is FINER than the scorer's keys, so folding it up
loses nothing.

  two_pt           = passing_2pt_conversions + rushing_2pt_conversions + receiving_2pt_conversions
  fg_made_0_39     = fg_made_0_19 + fg_made_20_29 + fg_made_30_39
  fg_made_50_plus  = fg_made_50_59 + fg_made_60_

⚠️⚠️ `fumbles_lost` READS THE THREE PER-PHASE COLUMNS, NOT `fumbles_lost_total`, AND THAT WAS
SETTLED BY MEASUREMENT AFTER THE ARMCHAIR GOT IT BACKWARDS. `fumbles_lost_total` additionally counts
PUNT AND KICKOFF RETURN fumbles; the three phase columns do not. The parity clause is what found it:
with the total mapped, 1,116 of 1,118 real 2026 week-1 rows agreed with nflverse's own PPR to 1e-9
and exactly two disagreed by exactly 2.0 — Jimmy Horn Jr. and Chimere Dike, both return men, both
carrying `fumbles_lost_total = 1` with all three phase columns at 0. Over 2025 REG the gap is 36
rows (249 vs 213).

Two independent authorities agree on the narrow reading, which is why it is the mapping:
  • the PROJECTED twin is `proj_fumbles_lost = touches x 0.006` (`season_projection.py`) — an
    OFFENSIVE-touch heuristic that cannot mean a return fumble. A realized column that counts
    return fumbles would be measuring a different quantity from the projection it is paired
    against, which is precisely what boundary (i) exists to prevent.
  • nflverse's own `fantasy_points_ppr` uses the same three columns.

⛔ Do not "tidy" this back to the total: it is shorter, it reads more natural, and it is wrong.
"""

from __future__ import annotations

from app.backend.services.projection_fields import STAT_FIELD

#: The lake table this module reads, named once so a consumer never re-types it.
REALIZED_SOURCE_TABLE = "stats_player_week"

#: The identity/grain columns every realized read needs beside the stat columns.
REALIZED_KEY_COLUMNS: tuple[str, ...] = (
    "player_id", "player_display_name", "position", "team", "opponent_team",
    "season", "week", "season_type", "game_id",
)

#: The realized PPR total the source computes itself — the points-head figure boundary (i) pairs a
#: projected PPR against. Carried through verbatim; never recomputed, because a second computation
#: of a number the source already publishes is a drift surface for no gain.
REALIZED_PPR_COLUMN = "fantasy_points_ppr"

#: scorer stat key → the `stats_player_week` column(s) that supply it. A tuple of length > 1 is
#: summed (see the header: realized data is finer than the scorer's keys, so folding up is exact).
#:
#: ⚠️ EVERY ENTRY WAS READ OFF A LIVE `DESCRIBE` of the table (145 columns, 2026-09-15), never
#: pattern-matched from the scorer's key spelling. The champion calls a pass attempt `attempts` and
#: a rush attempt `carries`; a name-similarity join would mis-map both.
REALIZED_STAT_SOURCE: dict[str, tuple[str, ...]] = {
    # ── passing ──
    "pass_att": ("attempts",),
    "pass_cmp": ("completions",),
    "pass_yds": ("passing_yards",),
    "pass_td": ("passing_tds",),
    "pass_int": ("passing_interceptions",),
    # ── rushing ──
    "rush_att": ("carries",),
    "rush_yds": ("rushing_yards",),
    "rush_td": ("rushing_tds",),
    # ── receiving ──
    "targets": ("targets",),
    "rec": ("receptions",),
    "rec_yds": ("receiving_yards",),
    "rec_td": ("receiving_tds",),
    # ── misc offence ──
    # ⚠️ NOT `fumbles_lost_total` — that counts return fumbles too. See the header; the parity
    # clause caught this, and the projected twin is an offensive-touch heuristic.
    "fumbles_lost": ("sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost"),
    "two_pt": ("passing_2pt_conversions", "rushing_2pt_conversions", "receiving_2pt_conversions"),
    # ── kicking ──
    "fg_att": ("fg_att",),
    "fg_made": ("fg_made",),
    "fg_made_0_39": ("fg_made_0_19", "fg_made_20_29", "fg_made_30_39"),
    "fg_made_40_49": ("fg_made_40_49",),
    "fg_made_50_plus": ("fg_made_50_59", "fg_made_60_"),
    "fg_missed": ("fg_missed",),
    "pat_att": ("pat_att",),
    "pat_made": ("pat_made",),
    # ── individual defensive (NOT the team D/ST aggregate — see the header) ──
    "def_sacks": ("def_sacks",),
    "def_int": ("def_interceptions",),
    "def_fumble_rec": ("fumble_recovery_opp",),
    "def_td": ("def_tds",),
    "def_safety": ("def_safeties",),
    "def_forced_fumble": ("def_fumbles_forced",),
    "st_td": ("special_teams_tds",),
}

#: Scorer keys this table CANNOT supply, each with the sentence explaining why. Declared rather than
#: merely omitted: an inventory that lists only what works cannot be audited, and a reader needs to
#: tell "we did not get to this" from "this table does not carry it".
#:
#: ⭐ THE SET IS DERIVED (see `unsupported_stat_keys`) — this dict only supplies the REASONS. A
#: hand-maintained absence list would rot silently the moment a key moved.
REALIZED_ABSENCE_REASON: dict[str, str] = {
    "pass_td_40p": (
        "40+ yard touchdown bonuses are a play-level fact. This table's `passing_40` counts 40+ "
        "yard PLAYS, not 40+ yard touchdowns (measured: it exceeds the touchdown count), so the "
        "term is left unscored rather than scored off a column that means something else."
    ),
    "rush_td_40p": (
        "40+ yard touchdown bonuses are a play-level fact; `rushing_40` counts 40+ yard plays, "
        "not 40+ yard touchdowns."
    ),
    "rec_td_40p": (
        "40+ yard touchdown bonuses are a play-level fact; `receiving_40` counts 40+ yard plays, "
        "not 40+ yard touchdowns."
    ),
    "def_blocked_kick": (
        "this line carries blocked kicks only from the KICKING team's side (a kicker's own kick "
        "being blocked), never the blocking defence's, so there is nothing here that means what "
        "this term means."
    ),
}

#: Every `dst_*` key shares one reason, so it is stated once rather than copied thirty times.
_DST_REASON = (
    "team defence scoring is a TEAM total (points and yards allowed). This line is one row per "
    "PLAYER, so it carries neither."
)


def unsupported_stat_keys(stat_field: dict[str, str] | None = None) -> tuple[str, ...]:
    """Every scorer key this realized line has no source for — DERIVED, never declared.

    🔴 NF-K1, the same direction `weekly_league_board.served_positions` takes: a declared list
    restates what the author INTENDED and keeps saying it after the mapping moves underneath.
    Deriving it from the two dicts means it can only ever describe the map in hand.
    """
    keys = STAT_FIELD if stat_field is None else stat_field
    return tuple(sorted(k for k in keys if k not in REALIZED_STAT_SOURCE))


#: A league term the SCORER ITSELF has no key for — a different fact from "the realized line does
#: not carry it", and the two must not share a sentence.
_NO_SCORER_KEY_REASON = (
    "our scorer does not carry this term on either side — it is absent from the projection's stat "
    "map too, so no projected or realized number is behind it."
)


def absence_reason(stat_key: str, stat_field: dict[str, str] | None = None) -> str:
    """The sentence explaining why `stat_key` is not scored — and WHICH of the two causes it is.

    ⭐ THE TWO CAUSES ARE DIFFERENT FACTS AND POINT AT DIFFERENT FIXES:
      • the SCORER has no key for the term (`pat_missed`, `fumble_rec_td`, `st_player_td` — the
        NF-C0e terms that failed their held-out gate). Nothing about the realized line is the
        reason, and some of these columns DO exist upstream (`pat_missed` is a real column on this
        very table); the blocker is `STAT_FIELD` and its two mirrors.
      • the REALIZED LINE has no source for a term the scorer does know.

    ⚠️ The first cut of this function answered the second sentence for both, which told a reader
    that `pat_missed` is missing from a table that carries a `pat_missed` column — a confident
    wrong explanation, which NF1.7(a) / NF-C6b rank as worse than an honest "we cannot attribute
    this". Distinguishing them is the whole job of an absence reason.
    """
    keys = STAT_FIELD if stat_field is None else stat_field
    if stat_key not in keys:
        return _NO_SCORER_KEY_REASON
    if stat_key in REALIZED_ABSENCE_REASON:
        return REALIZED_ABSENCE_REASON[stat_key]
    if stat_key.startswith("dst_"):
        return _DST_REASON
    return "this week's realized stat line does not carry a column for this term."


def resolve_realized_fields(stat_field: dict[str, str] | None = None) -> dict[str, str]:
    """scorer stat key → the field name a FLATTENED realized row serves it under.

    RAISES on a key this module names that the scorer does not know — the `resolve_component_fields`
    contract, in the same words and for the same reason: a realized term with no scorer key behind
    it is a map that has drifted from the thing it claims to mirror, and the drift is invisible at
    runtime because an unrecognized key scores zero without error.

    A pure function, so the refusal is directly testable rather than only reachable by reloading a
    module (a guard nobody can drive is not a guard — the NF1.7(a) family).
    """
    keys = STAT_FIELD if stat_field is None else stat_field
    unmapped = sorted(k for k in REALIZED_STAT_SOURCE if k not in keys)
    if unmapped:
        raise ValueError(
            f"the realized map names stat key(s) {unmapped} that are absent from "
            "projection_fields.STAT_FIELD. The scorer's key set is the authority — a realized "
            "term with no scorer key behind it would be multiplied by no weight and score zero "
            "with no error (the NF-C0e wrong-key class). Add the key to STAT_FIELD (and its two "
            "mirrors) or drop it here."
        )
    # The flattened row serves a single-column term under THAT COLUMN'S OWN NAME, and a summed term
    # under the scorer key prefixed — so a reader of a flattened row can always tell a carried
    # column from a computed one without consulting this file.
    return {
        key: cols[0] if len(cols) == 1 else f"sum_{key}"
        for key, cols in REALIZED_STAT_SOURCE.items()
    }


#: Resolved at IMPORT, mirroring `nfl_weekly.WEEKLY_COMPONENT_FIELD`: a map that has drifted from
#: the scorer must fail on the way in, not on the day a league with that weight is scored.
REALIZED_STAT_FIELD: dict[str, str] = resolve_realized_fields()

#: Every lake column a realized read must SELECT to satisfy the map. Derived, so adding a term to
#: `REALIZED_STAT_SOURCE` widens the read automatically — a term whose column the query forgot to
#: select would resolve CAPTURED and score zero, silently (NF-C0e).
REALIZED_STAT_COLUMNS: tuple[str, ...] = tuple(sorted(
    {c for cols in REALIZED_STAT_SOURCE.values() for c in cols}
))


def flatten_realized_row(row: dict) -> dict:
    """One `stats_player_week` row → a row `league_scoring.score_row` can read under
    `REALIZED_STAT_FIELD`.

    ⚠️ A SUM OVER COLUMNS THAT ARE ALL ABSENT STAYS ABSENT. If it defaulted to `0.0` the term would
    look PRESENT to `league_scoring.available_fields`, and a league's weight on it would resolve
    APPLIED while contributing nothing — the exact all-zeroes-that-look-covered failure
    `weekly_league_board` refuses at the payload level. A term nothing backs must be missing, so
    that `resolve_scoring` can call it CAPTURED.
    """
    out: dict = {}
    for key, cols in REALIZED_STAT_SOURCE.items():
        field = REALIZED_STAT_FIELD[key]
        if len(cols) == 1:
            if cols[0] in row:
                out[field] = row[cols[0]]
            continue
        present = [row[c] for c in cols if c in row and row[c] is not None]
        if present:
            out[field] = sum(float(v) for v in present)
    return out
