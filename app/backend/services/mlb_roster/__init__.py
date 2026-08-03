"""E8.2 — a user's fantasy-baseball league rosters, and what they make UNAVAILABLE on the board.

Two pure modules, no IO, no pandas (the API Lambda has neither):

  * `roster_upload` — the UPLOAD parser. Reads the CBS "roster grid" export (one row per fantasy
    TEAM, players CONCATENATED inside a position cell with no delimiter) and a generic
    one-row-per-player CSV, so the feature works for a platform we have never seen.
  * `board_match`  — roster entry → prospect-board row, league-scoped, with an explicit
    UNRESOLVED tier rather than a silent drop.

⚖️ WHY AN UPLOAD AND NOT AN API. E8.2a probed CBS for a compliant read and found none: the
documented API is dead, the league pages are login-walled, robots.txt is a blanket disallow, and
there is no OAuth program. Path B was OMITTED rather than deferred, and no code here reaches CBS.
"""

from app.backend.services.mlb_roster.board_match import (
    MatchedEntry,
    RosterMatch,
    match_roster,
)
from app.backend.services.mlb_roster.roster_upload import (
    ParsedRoster,
    RosterEntry,
    RosterUploadError,
    parse_roster_upload,
    split_grid_cell,
)

__all__ = [
    "MatchedEntry",
    "ParsedRoster",
    "RosterEntry",
    "RosterMatch",
    "RosterUploadError",
    "match_roster",
    "parse_roster_upload",
    "split_grid_cell",
]
