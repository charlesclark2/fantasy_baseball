"""NF-WK-RC1 — the REALIZED weekly stat line, mapped onto the ONE scorer's own stat keys.

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
═══════════════════════════════════════════════════════════════════════════════════════════════════

`projection_fields.STAT_FIELD` maps the scorer's stat keys onto the fields the PROJECTION payload
serves them under. This module is its REALIZED twin: the same keys, mapped onto the columns a
completed week actually carries, so it can go through `league_scoring.score_row` with NOTHING ELSE
CHANGED.

⭐ TWO SOURCES, ONE MAP (since NF-WK-ACC1 part 3). Most terms come from `nflverse.stats_player_week`
(`REALIZED_STAT_SOURCE`); the three 40+ yard touchdown bonuses come from `pbp`
(`REALIZED_PBP_SOURCE`), because they are a play-level fact no column of the weekly line carries at
any grain. `REALIZED_SOURCE_ALL` is the union and is what the scorer reads. The split exists ONLY so
each lake read asks its own table for columns that table has — a single merged column list would make
the weekly SELECT ask for a column that does not exist there and fail the read.

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
   touchdown count, which settles it. ⭐ A SECOND AUTHORITY AGREES: Sleeper carries BOTH spellings
   as separate keys (`rec_40p` the play count beside `rec_td_40p` the touchdown count), so the
   platform we reproduce distinguishes exactly the two quantities the wrong-key would conflate.
   ⇒ the three terms are absent from THIS table's map on purpose, and since NF-WK-ACC1 part 3 they
   are supplied from `pbp` instead, through `REALIZED_PBP_SOURCE` below. The trap stays recorded
   here because the tempting column is still sitting on this table.

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

⚠️⚠️ `fumbles_lost` READS `fumbles_lost_total` — AND THIS ENTRY EXISTS TO RECORD THAT IT USED TO READ
THE THREE PER-PHASE COLUMNS UNDER A REFUSAL THAT HAS NOW BEEN OVERTURNED (PM ruling ① on
NF-WK-ACC1's residuals, 2026-09-18, option A). The refusal is rewritten rather than deleted, because
a reader who finds the total mapped here deserves to know it was once deliberately not.

WHAT THE OLD REFUSAL CLAIMED. `fumbles_lost_total` additionally counts PUNT AND KICKOFF RETURN
fumbles, which the three phase columns do not; the narrow reading was said to be backed by two
independent authorities, and the comment ended "⛔ Do not 'tidy' this back to the total: it is
shorter, it reads more natural, and it is wrong."

WHICH HALF DIED, AND WHY. The nflverse-PPR-parity half is dead, by measurement rather than by
argument: THERE IS NO LIVE PARITY GUARD. `REALIZED_PPR_COLUMN` is nflverse's own
`fantasy_points_ppr`, CARRIED THROUGH VERBATIM and never recomputed (see its own comment below and
`weekly_recap.realized_board`, which copies it), so no number this system serves depends on which
column `fumbles_lost` reads. The 1,116-of-1,118 figure the old comment cited was a one-off
in-session probe, not a clause any suite runs. A refusal resting on a guard that does not exist is
the vacuous-check class wearing a comment's clothes.

WHICH HALF IS SUPERSEDED, AND BY WHAT. The projected/realized symmetry half is REAL — the projected
twin is `proj_fumbles_lost = touches x 0.006` (`season_projection.py`), an OFFENSIVE-touch heuristic
that cannot mean a return fumble. It is superseded by NF-WK-ACC1 part 1's option D, which
established that a realized-only term with no projection twin is a legitimate shape (`fum` reads
`fumbles_total` and has no projection column at all). And on the recap surface this scorer's
registered job is to EXPLAIN THE LEAGUE'S NUMBER: Sleeper charges `fum_lost` on the total, so
reading the per-phase columns was not caution — it was a measured disagreement with the very
authority we are itemising.

THE MEASURED COST THAT FORCED THE AMENDMENT. Over 2025 REG the two readings differ on 36 rows
(total 249 vs per-phase 213), 28 of them at startable offensive positions (WR 22, RB 4, QB 2); 2
rows in 2026 week 1 (Jimmy Horn Jr. and Chimere Dike, both return men, both carrying
`fumbles_lost_total = 1` with all three phase columns at 0 — the rows the old comment quoted as
evidence FOR the narrow reading are the rows that prove the league charges for them). On the
operator's own league it was 1 of 48 team-weeks: DJ Moore, 2025 week 1, ours 8.40 against the
league's 7.40, because the league pays `fum` −1 AND `fumbles_lost` −1 and we were charging only the
first.

⛔ WHAT IS STILL TRUE, so the pendulum does not swing back on the next reading: the two columns
genuinely mean different things, and a consumer pairing this term against the PROJECTED twin is
still pairing two different quantities. That is a real constraint on any future projected/realized
comparison of THIS term — it is simply not a reason to misreport a league's own scoring.
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
    # ⭐ `fumbles_lost_total`, NOT the three per-phase columns — CHANGED by PM ruling ① (2026-09-18,
    # option A) after the per-phase reading was measured as a 36-row disagreement with the platform
    # whose scoring we are itemising. The full reasoning, including which half of the old refusal
    # died and which is superseded, is in the header; ⛔ do not re-narrow this without reading it.
    "fumbles_lost": ("fumbles_lost_total",),
    # ⭐ ANY fumble, lost or recovered by your own team — a DIFFERENT term from `fumbles_lost`
    # above, and the league pays both (Sleeper: `fum` −1 and `fum_lost` −1, so a lost fumble costs
    # a manager twice). `fum` is Sleeper's own key, carried through unmapped by the importer
    # because no canonical term existed for it; naming it here is what turns it from a rule we
    # merely KEPT into one we APPLY (NF-WK-ACC1 part 1, PM ruling 2026-09-18 option D — the
    # reasoning is on `projection_fields.STAT_FIELD`'s entry, beside the paid-set consequence).
    # ⚠️ `fumbles_total`, NOT the three per-phase columns: this term counts every fumble, which is
    # exactly what the per-phase sum deliberately excludes (return fumbles). Measured on 2025
    # weeks 1-4: team totals 14/48 -> 27/48, diverging player seats 61 -> 24.
    "fum": ("fumbles_total",),
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
    # ⭐ REWORDED BY NF-WK-ACC1 PART 3, and the change of MEANING matters. These three are now
    # SUPPLIED, from the week's plays (`REALIZED_PBP_SOURCE`) — so this reason is no longer "we have
    # no source for this" but "the source exists and this week's plays have not landed yet", which
    # points at a completely different fix. The previous wording named the wrong-key that made the
    # weekly line unusable for them; that trap is a standing hazard and now lives in the module
    # header, where it cannot be mistaken for the reason a live week came up short.
    "pass_td_40p": (
        "40+ yard touchdown bonuses come from the week's individual plays, and this week's plays "
        "have not been published yet, so the bonus is not in this number."
    ),
    "rush_td_40p": (
        "40+ yard touchdown bonuses come from the week's individual plays, and this week's plays "
        "have not been published yet, so the bonus is not in this number."
    ),
    "rec_td_40p": (
        "40+ yard touchdown bonuses come from the week's individual plays, and this week's plays "
        "have not been published yet, so the bonus is not in this number."
    ),
    "def_blocked_kick": (
        "this line carries blocked kicks only from the KICKING team's side (a kicker's own kick "
        "being blocked), never the blocking defence's, so there is nothing here that means what "
        "this term means."
    ),
}

#: ── THE PLAY-DERIVED HALF (NF-WK-ACC1 part 3) ───────────────────────────────────────────────────
#:
#: scorer stat key → the column a flattened row serves it under when the week's PLAYS were read.
#: These three are 40+ yard TOUCHDOWN counts: a play-level fact no column of `stats_player_week`
#: carries at any grain, so they arrive from `pbp` through
#: `quant_sports_intel_models...realized_player_pbp.player_long_td_counts`, whose header is the
#: freeze record (the rule, its two verifications, and the lateral case that would otherwise credit
#: the wrong player).
#:
#: ⛔ DECLARED HERE RATHER THAN IMPORTED, for the reason `realized_dst.REALIZED_PBP_DST_FIELD` is:
#: this module runs INSIDE THE API LAMBDA, which bundles neither pandas nor
#: `quant_sports_intel_models`. The two sides are pinned to each other by a guard in the test suite
#: (which can import both), so the duplication cannot drift silently.
#:
#: ⚠️ THE `pbp_` PREFIX IS DELIBERATE. A reader of a flattened row can see at a glance that the term
#: came from PLAYS rather than from the weekly stat line — they have different freshness and
#: different failure modes — and it cannot collide if the vendor ever adds a `pass_td_40p` column to
#: `stats_player_week` (which carries the differently-meaning `passing_40` today).
REALIZED_PBP_SOURCE: dict[str, tuple[str, ...]] = {
    "pass_td_40p": ("pbp_pass_td_40p",),
    "rush_td_40p": ("pbp_rush_td_40p",),
    "rec_td_40p": ("pbp_rec_td_40p",),
}

#: The whole realized map: the weekly line PLUS the play-derived terms. ⭐ THIS is what the scorer
#: reads and what `unsupported_stat_keys` measures against — the split below it exists only so the
#: LAKE READ asks each table for the columns it actually has.
REALIZED_SOURCE_ALL: dict[str, tuple[str, ...]] = {**REALIZED_STAT_SOURCE, **REALIZED_PBP_SOURCE}

#: The derived columns a row carries when the plays were read. A week whose plays are not published
#: yet carries NONE of them, and the three terms then resolve CAPTURED — which is the honest state,
#: and is why the absence reasons below are worded for that case rather than deleted.
REALIZED_PBP_COLUMNS: tuple[str, ...] = tuple(sorted(
    {c for cols in REALIZED_PBP_SOURCE.values() for c in cols}
))

#: Columns the artifact CARRIES but the scorer does not read — kept deliberately, with the reason.
#:
#: ⭐ THE THREE PER-PHASE LOST-FUMBLE COLUMNS. `fumbles_lost` reads `fumbles_lost_total` since PM
#: ruling ① (see the header), so these three are no longer a scoring source. They stay in the read
#: for two reasons, and the SECOND one is load-bearing:
#:
#:   1. They are the EVIDENCE for the distinction the ruling turned on. `fumbles_lost_total` minus
#:      their sum is exactly "fumbles lost outside the three offensive phases" — the quantity that
#:      separates DJ Moore's week-1 lateral from an ordinary strip. Dropping them would leave the
#:      artifact unable to explain its own number.
#:   2. ⛔ WITHOUT THEM THE MAP CHANGE WOULD NEVER REACH A READER. A column leaving the artifact makes
#:      `realized_week.publish_decision` classify every already-published week as a vendor `restate`
#:      rather than a `widen_columns`, so the served week keeps its old rows forever — the same
#:      no-op-by-construction trap `widen_columns` exists to prevent, arriving from the narrowing
#:      side. Keeping them makes the new artifact a strict SUPERSET of the old one, which is the
#:      shape that machinery is built for.
#:
#: ⚠️ DECLARED, NOT INCIDENTAL. A column nothing reads is cruft that rots; a column something
#: deliberately keeps needs a name and a reason, or the next reader prunes it and re-breaks the
#: publish path.
REALIZED_DIAGNOSTIC_COLUMNS: tuple[str, ...] = (
    "sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost",
)

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
    return tuple(sorted(k for k in keys if k not in REALIZED_SOURCE_ALL))


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
    unmapped = sorted(k for k in REALIZED_SOURCE_ALL if k not in keys)
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
        for key, cols in REALIZED_SOURCE_ALL.items()
    }


#: Resolved at IMPORT, mirroring `nfl_weekly.WEEKLY_COMPONENT_FIELD`: a map that has drifted from
#: the scorer must fail on the way in, not on the day a league with that weight is scored.
REALIZED_STAT_FIELD: dict[str, str] = resolve_realized_fields()

#: Every `stats_player_week` column a realized read must SELECT to satisfy the map. Derived, so
#: adding a term to `REALIZED_STAT_SOURCE` widens the read automatically — a term whose column the
#: query forgot to select would resolve CAPTURED and score zero, silently (NF-C0e).
#:
#: ⛔ DELIBERATELY THE WEEKLY-LINE HALF ONLY, not `REALIZED_SOURCE_ALL`. This set is what a caller
#: SELECTs FROM `stats_player_week`, and that table has no column for the play-derived terms — asking
#: it for `pbp_pass_td_40p` would fail the read outright. The play-derived columns are
#: `REALIZED_PBP_COLUMNS`, and they arrive from a second, independent read.
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
    for key, cols in REALIZED_SOURCE_ALL.items():
        field = REALIZED_STAT_FIELD[key]
        if len(cols) == 1:
            if cols[0] in row:
                out[field] = row[cols[0]]
            continue
        present = [row[c] for c in cols if c in row and row[c] is not None]
        if present:
            out[field] = sum(float(v) for v in present)
    return out
