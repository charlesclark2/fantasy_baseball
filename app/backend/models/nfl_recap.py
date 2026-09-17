"""NF-WK-RC1 — the served contract for a weekly league recap and its power rankings.

⛔ ADDITIVE. Nothing here changes `nfl_weekly`'s contract; the weekly projection lens (NF-WK-MT1,
PHASE_B_HELD) and the public weekly page (NF-WK-FE1) are untouched.

⭐ THE FIELD NAMES CARRY THE PM RULING (i), 2026-09-16. `standingsTotal` is the LEAGUE'S OWN
published figure and is the standings fact; `itemisedTotal` is OUR sum of the seats we could
itemise. They are deliberately NOT one field with a source flag, because a single `total` is exactly
what a consumer would swap between and then present as two estimates of one number — which the
ruling forbids: "one is the league's record, the other is our itemization of what we can itemize."
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: How complete a week is. ⭐ DERIVED FROM A COUNT, NEVER A CLOCK (node 1): a week is FINAL only when
#: the realized line carries as many distinct games as the schedule says the week has. A
#: "Tuesday morning" rule calls a 15/16 week final the moment one game is postponed, silently.
RecapCompleteness = Literal["final", "partial", "not_started"]

COMPLETENESS_NOTE: dict[str, str] = {
    "final": "Every game in this week is complete.",
    "partial": (
        "This week is still in progress — some games have not finished, so these numbers will "
        "still change."
    ),
    "not_started": "This week has not been played yet.",
}


# ── the served key scheme ────────────────────────────────────────────────────────────────────────
#
# ⭐ IT LIVES HERE, NOT BESIDE THE BUILDER, AND THAT IS LOAD-BEARING. The builder
# (`quant_sports_intel_models...realized_week`) reads the lake and therefore pulls pandas; the API
# Lambda bundles NEITHER pandas NOR `quant_sports_intel_models` (see `league_scoring`'s header — the
# zip already sits near its size cap). A router importing the builder just for two key strings would
# fail at IMPORT on the deployed Lambda, which is the PERF cold-start import-path class in its most
# literal form. The builder imports these FROM here; the direction is one-way on purpose.

def realized_players_key(season: int, week: int) -> str:
    """Relative key (under `fantasy/nfl/`) of one week's realized player lines."""
    return f"realized/{int(season)}/{int(week)}/players.json"


def realized_manifest_key(season: int, week: int) -> str:
    """Relative key (under `fantasy/nfl/`) of one week's realized manifest."""
    return f"realized/{int(season)}/{int(week)}/manifest.json"


def realized_dst_inputs_key(season: int, week: int) -> str:
    """Relative key (under `fantasy/nfl/`) of one week's team-grain D/ST inputs (NF-WK-ACC1 ⑥).

    ⭐ A SIBLING FILE, NOT A COLUMN ON THE PLAYERS ARTIFACT. Adding columns there would move every
    served week's `content_sha256` and turn the next fire into a restatement event for every week.
    The divergence recorder reads this; nothing user-facing does.
    """
    return f"realized/{int(season)}/{int(week)}/dst_inputs.json"


#: The cumulative season-to-date artifact (PM ruling, NF-WVR1 ⑯ = option b, 2026-09-17). ⭐ The
#: directory is the literal word `season`, NOT a number, and that is load-bearing: both week-listers
#: (`run_realized_week._published_weeks` and the freshness op) count a served week only when the
#: parent directory is all digits, so this key can never be read as a published week.
REALIZED_SEASON_DIR = "season"


def realized_season_players_key(season: int) -> str:
    """Relative key (under `fantasy/nfl/`) of the season-to-date realized rows, one per player-game."""
    return f"realized/{int(season)}/{REALIZED_SEASON_DIR}/players.json"


def realized_season_manifest_key(season: int) -> str:
    """Relative key (under `fantasy/nfl/`) of the season-to-date realized manifest."""
    return f"realized/{int(season)}/{REALIZED_SEASON_DIR}/manifest.json"


class RecapSeat(BaseModel):
    """One lineup slot as it was ACTUALLY started, with what it scored and where that came from."""

    slot: str = Field(description="the lineup seat, e.g. QB / FLEX / DEF")
    seat: int = Field(description="0-based index into the league's starting-slot order")
    name: str = ""
    position: str = ""
    team: str = ""
    points: float | None = Field(default=None, description="null when the seat has an absence")
    #: ⭐ PER-SEAT PROVENANCE, rendered plainly and never as a footnote (PM disposition D2 = (C)).
    source: Literal["our_scorer", "league_published"] | None = None
    sourceNote: str | None = None
    pprPts: float | None = Field(
        default=None,
        description="the source's own PPR total — the points-head figure, carried never recomputed",
    )
    absence: dict | None = Field(
        default=None, description="{reason, detail} when this seat scored nothing"
    )


class RecapTeam(BaseModel):
    teamKey: str
    teamName: str
    matchupId: int | None = None
    seats: list[RecapSeat] = Field(default_factory=list)
    #: THE LEAGUE'S OWN RECORD — what the standings are. Null when the platform published none, in
    #: which case there is NO standing for this team rather than an approximate one.
    standingsTotal: float | None = None
    standingsSource: str | None = None
    #: OURS — the sum of the seats we could itemise. Never a substitute for `standingsTotal`.
    itemisedTotal: float = 0.0
    itemisationGap: float | None = None


class RecapMatchup(BaseModel):
    matchupId: int | None = None
    teams: list[dict] = Field(default_factory=list)
    winnerTeamKey: str | None = None
    tied: bool | None = None
    unpaired: bool | None = None
    resultUnavailable: bool | None = None


class WeeklyRecap(BaseModel):
    season: int
    week: int
    leagueId: str
    leagueName: str | None = None
    platform: str
    completeness: RecapCompleteness
    completenessNote: str
    #: When the lineups were captured. A recap is built from a POINT-IN-TIME record, so this is the
    #: instant the league's week was read — not when this response was assembled.
    capturedAt: str | None = None
    startingSlots: list[str] = Field(default_factory=list)
    teams: list[RecapTeam] = Field(default_factory=list)
    matchups: list[RecapMatchup] = Field(default_factory=list)
    coverage: dict = Field(default_factory=dict)
    #: ⛔ RENDERED ADJACENT TO THE TOTAL (MT1 ruling ③) and SPECIFIC — it names the league's own
    #: captured terms. Null when the league captures nothing, so no empty caveat is drawn.
    itemisationGapNote: str | None = None
    standingsNote: str


class PowerRankingRow(BaseModel):
    """One team's standing. Every number here is the LEAGUE'S OWN, and the rank's arithmetic is
    stated rather than implied — the spec's "no opaque composite score"."""

    rank: int
    teamKey: str
    teamName: str
    wins: int = 0
    losses: int = 0
    ties: int = 0
    pointsFor: float = 0.0
    pointsAgainst: float = 0.0
    weeksCounted: int = 0


class PowerRankings(BaseModel):
    season: int
    leagueId: str
    leagueName: str | None = None
    platform: str
    throughWeek: int
    weeksIncluded: list[int] = Field(default_factory=list)
    rows: list[PowerRankingRow] = Field(default_factory=list)
    #: ⭐ THE RANK'S ARITHMETIC, SERVED. A reader must be able to reproduce the order by hand.
    rankingBasis: str
    standingsNote: str
