"""NF-WK-RC1 (PM ruling D2) — the REALIZED team D/ST line, built from the lake.

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

from app.backend.services.projection_fields import STAT_FIELD
from app.backend.services.realized_stat_fields import REALIZED_STAT_FIELD

#: The scorer keys this module supplies, beyond the player-grain defensive counters that
#: `realized_stat_fields` already maps at team level by summation.
DST_POINTS_KEY = "dst_points_allowed"
DST_YARDS_KEY = "dst_yards_allowed"

#: How a non-offensive touchdown is priced when removing it from points allowed. 6 for the score
#: plus an ASSUMED made extra point — see the header; disclosed on the wire, never silent.
NON_OFFENSIVE_TD_POINTS = 7

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


def net_yards_allowed(passing: float | None, rushing: float | None, sack_yards: float | None) -> float | None:
    """The opponent's NET offensive yards. `sack_yards_lost` is stored NEGATIVE — see the header."""
    if passing is None and rushing is None:
        return None
    return float(passing or 0.0) + float(rushing or 0.0) + float(sack_yards or 0.0)


#: The `dst_*` scorer keys this module supplies, each served under its OWN name on the row. Merged
#: with `REALIZED_STAT_FIELD` by `dst_stat_field()` so a caller never hand-assembles the two.
REALIZED_DST_FIELD: dict[str, str] = {
    k: k for k in [DST_POINTS_KEY, DST_YARDS_KEY, *PA_BUCKETS, *YA_BUCKETS]
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
) -> dict:
    """One team-week's D/ST line, keyed so `league_scoring.score_row` can read it directly.

    `team_defensive_stats` are the team's own summed counters (sacks, interceptions, fumble
    recoveries, defensive/special-teams touchdowns, safeties, forced fumbles) already keyed by the
    scorer's stat keys — they are the SAME keys `realized_stat_fields` maps at player grain, summed
    to the team, so there is one vocabulary rather than two.
    """
    pa = points_allowed(opponent_score, opponent_non_offensive_tds)
    ya = net_yards_allowed(opponent_passing_yards, opponent_rushing_yards, opponent_sack_yards_lost)
    # ⭐ TRANSLATE SCORER KEYS → THE FIELD NAMES THE MAP POINTS AT. The caller names counters in the
    # scorer's own vocabulary (`def_fumble_rec`), which is the natural thing to write; `score_row`
    # reads them under `REALIZED_STAT_FIELD`'s field name (`fumble_recovery_opp`). Doing the
    # translation here is what stops the two spellings drifting at a call site — see the note on
    # `dst_stat_field`, which is where that mistake actually happened.
    row: dict = {}
    for key, value in (team_defensive_stats or {}).items():
        if key not in REALIZED_STAT_FIELD:
            raise DstBucketError(
                f"{key!r} is not a stat key the realized map knows, so nothing would ever read it. "
                "A counter under an unrecognised key scores zero with no error (the NF-C0e class)."
            )
        row[REALIZED_STAT_FIELD[key]] = value
    if pa is not None:
        row[DST_POINTS_KEY] = pa
        row.update(_bucket_indicators(pa, PA_BUCKETS))
    if ya is not None:
        row[DST_YARDS_KEY] = ya
        row.update(_bucket_indicators(ya, YA_BUCKETS))
    return row
