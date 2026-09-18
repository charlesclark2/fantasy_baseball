"""NF-WK-RC1 (PM ruling D2) — the REALIZED team D/ST line, built from the lake.

⛔⛔ NOT WIRED TO THE SERVED D/ST SEAT, AND THAT IS THE PM'S DISPOSITION (2026-09-16), NOT AN
OVERSIGHT. Against Sleeper's own scoring of the same defences this construction reproduced only
35 of 48 team-weeks (disagreeing 1/3/6/3 of 12 across four weeks) — systematic, not a stat
correction. Option (C) was ruled: the SERVED D/ST seat carries the league's OWN published figure,
because on a factual surface that number IS the fact and this construction would substitute an
unvalidated estimate for a known one.

What lives here is therefore a set of VALIDATED COMPONENTS AWAITING THE (B) STORY (PM card
fXIYuvMN) — the points-allowed correction (proven decisively by MIN's 24 -> 17 tier crossing), the
negative `sack_yards_lost` sign, the key-derived tier ranges, and the LA/LAR franchise
normalisation. They are all correct and all worth keeping.

⛔ NOTHING MAY QUIETLY WIRE THIS INTO THE SERVED SEAT LATER WITHOUT THE CROSS-CHECK HARNESS PASSING.
Its remaining job under (C) is to run as a DIVERGENCE RECORDER: it records data, never a page —
"a comparison known to fail on ~27% of team-weeks that paged would be the muted-monitor pattern
arriving on day one."

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHY THIS EXISTS
═══════════════════════════════════════════════════════════════════════════════════════════════════

Node 1 found that 21 of the 25 scoring terms a realized player line CANNOT carry are the `dst_*`
family: team defence scoring is a TEAM total (points and yards allowed) and `stats_player_week` is
one row per PLAYER. The PM ruled the gap closed inside Phase A rather than rendered as an absence:

    "D/ST is a starting slot in most leagues, so a recap with a stated absence in a starting slot
     every week is honest but visibly hollow, and the team feeds are already landed."

Measured on the probed league, that is literally true: its lineup is QB/RB/RB/WR/WR/TE/FLEX/FLEX/DEF
— a DEF seat and no kicker at all, so an absent D/ST would be one ninth of every lineup, every week.

───────────────────────────────────────────────────────────────────────────────────────────────────
⭐⭐ THE TRAP THAT MAKES THIS WORTH MEASURING: "POINTS ALLOWED" IS NOT THE OPPONENT'S SCORE
───────────────────────────────────────────────────────────────────────────────────────────────────

A D/ST is charged with the points the opposing OFFENSE scored. Points the opponent's DEFENCE or
SPECIAL TEAMS put up — a pick-six against your quarterback — are not your defence's fault and every
platform excludes them. The naive `opponent_final_score` is therefore WRONG, and wrong in exactly
the games where it matters: a single defensive touchdown moves a team across a scoring bucket.

MEASURED, not reasoned (2025 week 1, against Sleeper's own D/ST scoring of the same league):

    PHI  allowed DAL 20 pts / 307 yds · 0 sacks · 1 FR · 1 FF
         → pts_allow_14_20 1 + yds_allow_300_349 1 + fum_rec 1 + ff 1  = 4.0  ✅ Sleeper: 4.0
    MIN  CHI's final score was 24 — but CHI scored a DEFENSIVE TOUCHDOWN, so MIN's defence allowed
         24 − 7 = 17, not 24.
         naive (PA 24 → the 21-27 bucket, worth 0) = 5.0   ✗ Sleeper: 6.0
         correct (PA 17 → the 14-20 bucket, worth 1) = 6.0  ✅ Sleeper: 6.0

⚠️ THE 7 IS AN ASSUMPTION AND IS DISCLOSED AS ONE. A non-offensive touchdown is 6 plus whatever
followed it; we subtract 7, i.e. we assume the extra point was kicked and made. Deriving it exactly
needs `pbp` (drive-level scoring), which is not in the ingest set for the current season. The
approximation is right in the large majority of cases and its failure mode is bounded — one point,
which only matters when it straddles a bucket edge — so it is carried on the wire as
`pointsAllowedAssumption` rather than hidden.

───────────────────────────────────────────────────────────────────────────────────────────────────
⚠️ `sack_yards_lost` IS STORED NEGATIVE
───────────────────────────────────────────────────────────────────────────────────────────────────

Measured: CHI's week-1 `sack_yards_lost` is **−12**. So net yardage is `passing + rushing + sack`
(an addition of a negative), and the natural-looking `passing + rushing − sack_yards_lost` moves the
total the WRONG WAY — it inflated CHI's 317 net to 341. The first cut of the probe did exactly that.

───────────────────────────────────────────────────────────────────────────────────────────────────
⭐ THE BUCKET RANGES ARE PARSED FROM THE SCORER'S OWN KEY NAMES
───────────────────────────────────────────────────────────────────────────────────────────────────

The PM's instruction was "the D/ST term map derived from the scorer's key set like everything else,
never hand-typed". A hand-written `{0: (0,0), 1: (1,6), …}` table is the denylist hazard again: it
would drift silently the day a bucket is renamed or a tier is added. So the ranges come out of the
KEYS THEMSELVES (`dst_pa_g_14_17` → 14..17, `dst_pa_g_46p` → 46..∞), and an unparseable bucket key
RAISES rather than being skipped — a tier nobody scores would otherwise cost a league real points
with no error.
"""

from __future__ import annotations

import math
import re

from app.backend.services import league_scoring
from app.backend.services.projection_fields import STAT_FIELD
from app.backend.services.realized_stat_fields import REALIZED_STAT_FIELD

#: The scorer keys this module supplies, beyond the player-grain defensive counters that
#: `realized_stat_fields` already maps at team level by summation.
DST_POINTS_KEY = "dst_points_allowed"
DST_YARDS_KEY = "dst_yards_allowed"

#: How a non-offensive touchdown is priced when removing it from points allowed. 6 for the score
#: plus an ASSUMED made extra point — see the header; disclosed on the wire, never silent.
NON_OFFENSIVE_TD_POINTS = 7

#: What the wire says when the FROZEN play-derived rule produced the figure (NF-WK-ACC1 part 2).
#: There is no assumption left to disclose: the charge is read off the plays rather than estimated,
#: and it reproduced 544 of 544 team-weeks in 2025 against the league's own published figures.
POINTS_ALLOWED_RULE_PBP = (
    "Points allowed excludes touchdowns scored by the opposing DEFENCE (removed at 6 points, the "
    "touchdown itself — the extra point is a separate play your defence is not on the field for) and "
    "safeties the opponent scored (2 points). Their special-teams touchdowns stay charged. Read from "
    "play-by-play, not estimated."
)

POINTS_ALLOWED_ASSUMPTION = (
    "Points allowed excludes touchdowns scored by the opposing defence or special teams, which are "
    "not charged to your defence. Each is removed at 7 points (the score plus an assumed extra "
    "point); the exact conversion is not in this season's ingested data."
)

_BUCKET_RE = re.compile(r"^dst_(pa|ya)_g_(\d+)(?:_(\d+)|(p))?$")


class DstBucketError(ValueError):
    """A `dst_*_g_*` key whose range cannot be read off its name — see the header."""


def _parse_buckets(prefix: str, stat_field: dict[str, str] | None = None) -> dict[str, tuple[float, float]]:
    """`{bucket_key: (lo, hi)}` for one family, DERIVED from the scorer's key names.

    RAISES on a key that matches the family prefix but not the naming grammar: silently skipping it
    would leave a tier that scores nothing, which costs a league real points with no error.
    """
    keys = STAT_FIELD if stat_field is None else stat_field
    out: dict[str, tuple[float, float]] = {}
    for key in keys:
        if not key.startswith(f"dst_{prefix}_g_"):
            continue
        m = _BUCKET_RE.match(key)
        if not m or m.group(1) != prefix:
            raise DstBucketError(
                f"{key!r} looks like a {prefix} tier but its range cannot be read off its name. "
                "The ranges are DERIVED from the key names on purpose (a hand-written table drifts "
                "silently); teach the grammar or rename the key."
            )
        lo = float(m.group(2))
        hi = float(m.group(3)) if m.group(3) else (math.inf if m.group(4) else lo)
        out[key] = (lo, hi)
    return out


#: Resolved at IMPORT, mirroring `nfl_weekly.WEEKLY_COMPONENT_FIELD` / `REALIZED_STAT_FIELD`: a
#: tier the scorer knows about but this module cannot price must fail on the way in.
PA_BUCKETS: dict[str, tuple[float, float]] = _parse_buckets("pa")
YA_BUCKETS: dict[str, tuple[float, float]] = _parse_buckets("ya")


def _bucket_indicators(value: float | None, buckets: dict[str, tuple[float, float]]) -> dict[str, float]:
    """1.0 on the tier `value` falls in, 0.0 on the others — the form a scoring weight multiplies.

    ⛔ An UNKNOWN value yields NO keys at all rather than a row of zeroes. A zero reads to
    `league_scoring.available_fields` as a real number, so a league's tier weights would resolve
    APPLIED and contribute nothing — the all-zeroes-that-look-covered failure. Absent means
    CAPTURED, which is the honest answer when we do not know what a defence allowed.
    """
    if value is None:
        return {}
    out = {}
    for key, (lo, hi) in buckets.items():
        out[key] = 1.0 if lo <= float(value) <= hi else 0.0
    return out


def points_allowed(opponent_score: float | None, opponent_non_offensive_tds: float | None) -> float | None:
    """What the defence is actually charged with. See the header for why this is not the score.

    Never returns a negative: a defence whose opponent scored only non-offensive touchdowns allowed
    zero, and a negative would fall outside every tier and silently score nothing.
    """
    if opponent_score is None:
        return None
    tds = float(opponent_non_offensive_tds or 0.0)
    return max(0.0, float(opponent_score) - NON_OFFENSIVE_TD_POINTS * tds)


def result_pending(opponent_score: float | None) -> bool:
    """Is this defence's game result simply NOT IN `schedules` YET?

    ⚠️ THIS IS A KNOWN, DATED CADENCE DEFECT, NOT A DATA ERROR — PM card yOhLHprC (2026-09-16).
    `schedules` refreshes Monday 06:15 PT, BEFORE Monday Night Football, so for up to seven days the
    MNF game carries no score while `stats_player_week` already holds every player's line. Points
    allowed is read from `schedules`; yards and the team counters are not. So for exactly the two
    MNF defences the construction is missing its largest term and will disagree with the league's
    figure EVERY WEEK, for a reason that has nothing to do with the residual fXIYuvMN is chasing.

    ⛔ SO IT IS TAGGED, NEVER DROPPED. Silently excluding these rows would make "we could not
    compute this one" and "this one agreed" the same number — the vacuity `compare_to_platform`
    already refuses elsewhere. The row is recorded, marked, and reported in its own bucket so the
    residual signal can be read clean without anything being hidden.
    """
    return opponent_score is None


def net_yards_allowed(passing: float | None, rushing: float | None, sack_yards: float | None) -> float | None:
    """The opponent's NET offensive yards. `sack_yards_lost` is stored NEGATIVE — see the header."""
    if passing is None and rushing is None:
        return None
    return float(passing or 0.0) + float(rushing or 0.0) + float(sack_yards or 0.0)


#: Terms a D/ST line can carry that the PLAYER table cannot supply at all — they come from
#: play-by-play (NF-WK-ACC1 part 2, frozen 2026-09-18; the rules live in
#: `quant_sports_intel_models/football/nfl/fantasy/realized_dst_pbp.py`).
#:
#: ⚠️ THEY BELONG HERE RATHER THAN IN `realized_stat_fields.REALIZED_STAT_SOURCE` BECAUSE THAT MAP
#: IS A CONTRACT ABOUT ONE TABLE — scorer key → `stats_player_week` column. A blocked kick has no
#: player column in the seasons we hold; a defence-credited special-teams fumble is not a player
#: stat at all. Naming them there would claim a column that does not exist; naming them here says
#: what is true: the D/ST line serves them under their own name, and something else supplies them.
#: `def_st_ff` / `def_st_fum_rec` are Sleeper's own raw keys (the importer carries them through
#: unmapped, as it does `fum`) — the DEFENCE-credited versions, distinct from the player-credited
#: `st_ff` / `st_fum_rec` a returner earns.
REALIZED_PBP_DST_FIELD: dict[str, str] = {
    k: k for k in ("def_blocked_kick", "def_st_ff", "def_st_fum_rec")
}

#: The `dst_*` scorer keys this module supplies, each served under its OWN name on the row. Merged
#: with `REALIZED_STAT_FIELD` by `dst_stat_field()` so a caller never hand-assembles the two.
REALIZED_DST_FIELD: dict[str, str] = {
    **{k: k for k in [DST_POINTS_KEY, DST_YARDS_KEY, *PA_BUCKETS, *YA_BUCKETS]},
    **REALIZED_PBP_DST_FIELD,
}


def dst_stat_field(stat_field: dict[str, str] | None = None) -> dict[str, str]:
    """The ONE stat-field map a D/ST row is scored under — player-grain terms plus the `dst_*` ones.

    ⚠️ THIS EXISTS BECAUSE ASSEMBLING IT AT THE CALL SITE IS WHERE THE BUG WENT. The first cut had
    the caller merge `REALIZED_STAT_FIELD` with a locally-built dict and pass team counters keyed by
    SCORER KEY (`def_fumble_rec`), while `score_row` looks them up by the map's FIELD NAME
    (`fumble_recovery_opp`) — so every team defensive counter silently scored ZERO and nine of
    twelve defences came out low against Sleeper's own figure. One owner, no call-site assembly.
    """
    base = REALIZED_STAT_FIELD if stat_field is None else stat_field
    return {**base, **REALIZED_DST_FIELD}


def dst_row(
    *,
    opponent_score: float | None,
    opponent_non_offensive_tds: float | None,
    opponent_passing_yards: float | None,
    opponent_rushing_yards: float | None,
    opponent_sack_yards_lost: float | None,
    team_defensive_stats: dict[str, float] | None = None,
    points_allowed_override: float | None = None,
) -> dict:
    """One team-week's D/ST line, keyed so `league_scoring.score_row` can read it directly.

    `team_defensive_stats` are the team's own summed counters (sacks, interceptions, fumble
    recoveries, defensive/special-teams touchdowns, safeties, forced fumbles) already keyed by the
    scorer's stat keys — they are the SAME keys `realized_stat_fields` maps at player grain, summed
    to the team, so there is one vocabulary rather than two.
    """
    # ⭐ `points_allowed_override` IS THE FROZEN PLAY-DERIVED FIGURE (NF-WK-ACC1 part 2). When a
    # caller has play-by-play it computes points allowed under the frozen rule — the opponent's score
    # minus 6 per touchdown their DEFENCE scored minus 2 per safety — which reproduced 544 of 544
    # team-weeks in 2025 against the 457 this module's own 7-point rule reaches. The 7-point rule
    # stays as the fallback for a week with no plays, and `dst_inputs`' `source` says which ran, so a
    # degraded construction is never mistaken for the frozen one.
    pa = (float(points_allowed_override) if points_allowed_override is not None
          else points_allowed(opponent_score, opponent_non_offensive_tds))
    ya = net_yards_allowed(opponent_passing_yards, opponent_rushing_yards, opponent_sack_yards_lost)
    # ⭐ TRANSLATE SCORER KEYS → THE FIELD NAMES THE MAP POINTS AT. The caller names counters in the
    # scorer's own vocabulary (`def_fumble_rec`), which is the natural thing to write; `score_row`
    # reads them under `REALIZED_STAT_FIELD`'s field name (`fumble_recovery_opp`). Doing the
    # translation here is what stops the two spellings drifting at a call site — see the note on
    # `dst_stat_field`, which is where that mistake actually happened.
    row: dict = {}
    # ⚠️ VALIDATED AGAINST THE MAP THE LINE IS ACTUALLY SCORED UNDER (`dst_stat_field()`), not
    # against the player-grain map alone: the play-derived terms above live only in the D/ST half,
    # and validating against the narrower map would refuse exactly the counters part 2 adds.
    scoring_map = dst_stat_field()
    for key, value in (team_defensive_stats or {}).items():
        if key not in scoring_map:
            raise DstBucketError(
                f"{key!r} is not a stat key the realized map knows, so nothing would ever read it. "
                "A counter under an unrecognised key scores zero with no error (the NF-C0e class)."
            )
        row[scoring_map[key]] = value
    if pa is not None:
        row[DST_POINTS_KEY] = pa
        row.update(_bucket_indicators(pa, PA_BUCKETS))
    if ya is not None:
        row[DST_YARDS_KEY] = ya
        row.update(_bucket_indicators(ya, YA_BUCKETS))
    return row


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# NF-WK-ACC1 (PM rider ⑥ on RC1's closeout, 2026-09-17) — THE RECORDER'S PRODUCTION INPUTS
# ═══════════════════════════════════════════════════════════════════════════════════════════════════
#
# ⭐ WHY THE CONSTRUCTION IS SPLIT INTO TWO HALVES. The API Lambda cannot read the NFL lake, so the
# team-grain half (which defence allowed what, and what it did) is built BOX-SIDE once per week and
# published beside the realized player artifact — `realized_week.team_week_inputs`. The league-grain
# half (what that line is WORTH under one league's settings) can only be computed at request time,
# because it depends on the league — `score_dst_lines`, here. The cross-check harness drives exactly
# these two functions, so the recorded stream and the harness can never measure two constructions.
#
# ⚠️ THE BOX HALF LIVES IN `realized_week.py` ON PURPOSE (RC1 closeout ⑪): `orchestration_cd.yml`
# does not rebuild the box on an `app/backend` edit, so construction logic that part 2 will keep
# changing belongs on a path that DOES trigger the box deploy. Only stable primitives stay here.
#
# ⛔ THIS IS STILL NOT THE SERVED SEAT. It feeds `weekly_recap.compare_to_platform` as a recorder —
# data, never a page, never a number a user sees (D2 disposition (C)).

#: The lake columns (`stats_player_week` / `stats_team_week` names) a team-week line is built from.
#: Declared once so the box-side read can SELECT exactly these and a missing one fails loudly.
DST_TEAM_COLUMNS: tuple[str, ...] = (
    "def_sacks", "def_interceptions", "fumble_recovery_opp", "def_tds", "fumble_recovery_tds",
    "def_safeties", "def_fumbles_forced", "special_teams_tds",
    "passing_yards", "rushing_yards", "sack_yards_lost",
)


def score_dst_lines(entries: dict[str, dict], scoring: dict) -> tuple[dict[str, float], set[str]]:
    """REQUEST-SIDE half: the published lines scored under ONE league's settings.

    Returns `(points_by_defence, result_pending_defences)` — exactly the two arguments
    `weekly_recap.compare_to_platform` takes for its D/ST leg.
    """
    field_map = dst_stat_field()
    lines = [e["line"] for e in entries.values() if isinstance(e, dict) and "line" in e]
    resolved, _ = league_scoring.resolve_scoring(
        scoring or {}, stat_field=field_map, fields=league_scoring.available_fields(lines))
    points = {
        team: league_scoring.score_row(e["line"], "DST", resolved, field_map)["pts"]
        for team, e in entries.items() if isinstance(e, dict) and "line" in e
    }
    pending = {team for team, e in entries.items() if isinstance(e, dict) and e.get("resultPending")}
    return points, pending
