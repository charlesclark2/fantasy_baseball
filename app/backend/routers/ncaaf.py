"""ncaaf.py — the PUBLIC college-football API (games/predictions, futures, team pages).

NCAAF is FREE (E9.45 — fantasy is the paid hook), so this router carries no `Depends` at all: no
`require_subscriber`, no `require_fantasy_access`, nothing. It is mounted with no `dependencies=`
in `main.py`, mirroring `fantasy_public.py`'s separate-router pattern rather than a flag inside a
gated router.

⚠️ BEING PUBLIC IN FASTAPI IS NOT SUFFICIENT AND NEVER HAS BEEN. The HTTP API applies a Cognito JWT
authorizer PER ROUTE, configured in the AWS console and living in NO repo IaC — so a route that is
genuinely public in code still answers **401 at the gateway before the Lambda is ever invoked**
(NF3.2). Each route below needs an explicit `--authorization-type NONE` route; the
`create-route` commands are in `infrastructure/aws_resources.md`. ⛔ This story is NOT done at
merge: `deploy.sh` ships the code and the gateway routes are a separate operator step — and that
applies to EVERY route added later, one per path. NCAAF-P3.3's `/ncaaf/teams/{team_id}` is the
fifth and needs its own; a new public route with no gateway route 401s for everyone, with nothing
in this repo to show why.

📚 WHAT LIVES HERE. The game board (manifest / slate / one game), the P1.5 futures board, and —
NCAAF-P3.3 — one FBS team's stats page. The team route is the link-out target of the game cards.

📣 WHAT IT SERVES — AND WHAT IT STRUCTURALLY CANNOT
---------------------------------------------------
Probabilities, distributional interval parameters, the model's line and (when one has been
captured) the market's line beside it. `best_alpha = 0` is stamped on every payload: P1.4's CLV leg
came back a clean null (VAL1: ATS 0.496 = placebo), so no stake rides on any of it. There is no
pick field in the schema — `app/backend/models/ncaaf.py` REFUSES at import to declare one — and no
"best bets" or edge language anywhere on the wire.

🧾 EVERY SERVED FIELD IS DECLARED ON THE RESPONSE MODEL. That is the E9.41 landmine: a field the
store carries but the model does not declare is silently STRIPPED on serialize, with the data
correct in the store the whole time and no error anywhere. Nothing here is returned as a bare dict,
and nothing is serialised with `exclude_none` — a declared field is always on the wire, `null`
included, because absent and null are different facts.

🕐 The default slate is the America/Los_Angeles game-day (INC-22): the Lambda runs UTC, and a UTC
"today" rolls over at 00:00 UTC — Saturday EVENING in the US, which for college football is the
middle of the slate.

⛔ NO ROUTE TAKES A WEEK. CFBD restarts `week` at 1 for the postseason, so a "week" parameter would
name two different sets of games; `game_prediction_snapshot.py`'s `season_order_week` is a verbatim
alias of that raw week (the recorded alias landmine). The manifest hands a client the list of
KICKOFF DAYS to build a selector from instead.

📦 ADDITIVE ONLY (NF-C0). These are brand-new response shapes, so nothing can break today — but the
rule binds from here on: a later story adds keys, never removes or renames one a deployed client
reads, and the API Lambda deploys separately from `frontend/` so there is always a skew window.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Path, Query

from app.backend.models.ncaaf import (
    NcaafFuturesBoard,
    NcaafGamePrediction,
    NcaafManifest,
    NcaafSlate,
    NcaafTeamPage,
)
from app.backend.services import ncaaf_serving
from betting_ml.utils.game_day import current_game_date_iso

logger = logging.getLogger(__name__)

# No `dependencies=[...]` — NCAAF is free (E9.45). See the module docstring.
router = APIRouter(prefix="/ncaaf", tags=["ncaaf"])

_GAME_DAY_PATTERN = r"^\d{4}-\d{2}-\d{2}$"

#: The 404 detail strings. Written so the three ways "nothing here" can happen stay
#: DISTINGUISHABLE to a client (NF-C6b) — a surface that renders them identically is one that
#: re-investigates the same symptom every time it recurs.
_NO_MANIFEST = (
    "No NCAAF serving manifest has been published yet. Nothing has been written to the serving "
    "store for this season."
)
_NO_SLATE = "No NCAAF projections are published for this game-day."
_NO_GAME = "No NCAAF projection is published for this game."
_NO_FUTURES = "No NCAAF futures board is published for this season."
_NO_TEAM = (
    "No NCAAF team page is published for this team. Either the team id is not an FBS team we "
    "model, or the serving store has not been written for this season yet."
)


@router.get("/manifest", response_model=NcaafManifest)
def ncaaf_manifest():
    """Which LA game-days have a published slate, and which one is 'today'.

    This is what a week selector reads — kickoff DAYS, never a CFBD week (see the module
    docstring). It also carries the model provenance and the honest-framing flags, so a client can
    render the disclosure and the artifact vintage without a second call.
    """
    blob = ncaaf_serving.read_manifest()
    if blob is None:
        raise HTTPException(status_code=404, detail=_NO_MANIFEST)
    return NcaafManifest.model_validate(blob)


@router.get("/games", response_model=NcaafSlate)
def ncaaf_slate(
    game_day: str | None = Query(
        default=None, pattern=_GAME_DAY_PATTERN,
        description="America/Los_Angeles kickoff day (YYYY-MM-DD). Defaults to today in LA."),
):
    """Every FBS projection kicking off on one LA game-day."""
    day = game_day or current_game_date_iso()  # INC-22 — LA, never the Lambda's UTC date
    blob = ncaaf_serving.read_slate(day)
    if blob is None:
        raise HTTPException(status_code=404, detail=f"{_NO_SLATE} (game_day={day})")
    return NcaafSlate.model_validate(blob)


@router.get("/games/{game_id}", response_model=NcaafGamePrediction)
def ncaaf_game(game_id: int = Path(..., ge=1, description="the CFBD game id")):
    """One game's full projection — win probability both sides, the margin and total curves, and
    the market line beside the model line where one has been captured."""
    blob = ncaaf_serving.read_game(game_id)
    if blob is None:
        raise HTTPException(status_code=404, detail=f"{_NO_GAME} (game_id={game_id})")
    return NcaafGamePrediction.model_validate(blob)


@router.get("/teams/{team_id}", response_model=NcaafTeamPage)
def ncaaf_team(team_id: int = Path(..., ge=1, description="the CFBD team id")):
    """One FBS team's stats page: the P1.2 strength rating WITH its posterior band, the P1.1
    opponent-adjusted efficiency, the season's schedule and results, and the trench/pace splits.

    ⭐ THE BAND IS SERVED WITH THE RATING, ALWAYS. At week 1 nothing has been played and the
    posterior is the prior — a real number with a wide interval (~7 points of sd on the 2026
    opener). A rating without its band would publish a precision the model does not claim, which on
    this vertical is exactly the line between context and a pick. `best_alpha = 0`: a strength
    rating is context, never a recommendation.

    ⚖️ EACH BLOCK STATES ITS OWN AVAILABILITY. The page assembles from four independently-available
    sources — the P1.2 strength lake and three P1.1 marts — and on a September Saturday a CORRECT
    page has a rating, a schedule, and three structurally empty blocks because no game has been
    played. That must not render identically to "our mart build failed", so every block carries a
    `status` and a machine-readable `reason` (`no_games_played_yet` vs `source_marts_unavailable`
    vs `no_row_for_this_team_and_season`) rather than one shared blank (NF-C6b / NF-K1).

    ⛔ 404 MEANS ABSENT. A team we publish nothing for is a 404, never an empty-but-successful body
    — "we have no page for this team" and "we have a page and some field is null" are different
    facts (the same rule the slate and game routes follow).

    ⚠️ LIKE EVERY ROUTE HERE, BEING PUBLIC IN CODE IS NOT SUFFICIENT: this path needs its own
    API-Gateway route with `--authorization-type NONE`, or the Cognito JWT authorizer answers 401
    before the Lambda is invoked (NF3.2). See `infrastructure/aws_resources.md`.
    """
    blob = ncaaf_serving.read_team(team_id)
    if blob is None:
        raise HTTPException(status_code=404, detail=f"{_NO_TEAM} (team_id={team_id})")
    return NcaafTeamPage.model_validate(blob)


@router.get("/futures", response_model=NcaafFuturesBoard)
def ncaaf_futures():
    """The P1.5 season-simulation board: conference-title, playoff and national-title
    PROBABILITIES per team, with expected wins."""
    blob = ncaaf_serving.read_futures()
    if blob is None:
        raise HTTPException(status_code=404, detail=_NO_FUTURES)
    return NcaafFuturesBoard.model_validate(blob)
