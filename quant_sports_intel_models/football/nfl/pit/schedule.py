"""schedule.py — the upcoming-game spine every capture leg keys on (FREE nflverse, SF-free).

Reads the nflverse `schedules` release Parquet directly over HTTPS via DuckDB — the same source
`ingest/sources.py::_season_kickoffs` uses, so the capture legs and the lake agree on kickoff
times by construction rather than by convention.

⚠️ KICKOFF TIME IS ET, AND THE CONVERSION IS THE WHOLE BALLGAME. `gameday` is a date and
`gametime` is `HH:MM` in **America/New_York**, DST-dependent. Every checkpoint on the T-120h…T-1h
ladder is computed from the UTC instant, so a botched conversion silently shifts every capture by
an hour — the LTZ/NTZ family this repo has produced four separate bugs from. `zoneinfo` handles
DST correctly; a missing tzdata FAILS rather than falling back to a fixed offset (a fixed −4h
offset is right in September and wrong in January, which is exactly the kind of "plausible but
wrong" value that hides).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

log = logging.getLogger(__name__)

NFLVERSE_RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"
SCHEDULES_URL = f"{NFLVERSE_RELEASE}/schedules/games.parquet"

#: The columns the capture legs need. Selected explicitly (not `*`) so an upstream column
#: DELETION fails loudly here instead of arriving as a silent 100%-NULL merge backfill — the
#: exact mechanism behind NF-W0's three 2025 silent deaths.
SCHEDULE_COLUMNS = (
    "game_id", "season", "game_type", "week", "gameday", "gametime",
    "home_team", "away_team", "location", "roof", "surface", "stadium", "stadium_id",
)


class ScheduleReadError(RuntimeError):
    """The schedule could not be read — capture is refused rather than run on a stale spine."""


@dataclass(frozen=True)
class ScheduledGame:
    game_id: str
    season: int
    week: int
    game_type: str
    kickoff_utc: datetime
    home_team: str
    away_team: str
    location: str
    roof: str
    stadium: str

    def as_venue_input(self) -> dict:
        return {
            "game_id": self.game_id, "home_team": self.home_team,
            "location": self.location, "roof": self.roof, "stadium": self.stadium,
        }


def _et_zone():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("America/New_York")
    except Exception as exc:  # noqa: BLE001
        raise ScheduleReadError(
            "no tzdata for America/New_York — refusing to guess a fixed UTC offset for NFL "
            "kickoffs (a fixed −4h is right in September and wrong in January). Install tzdata."
        ) from exc


def _duck():
    """The box-aware connection — NEVER a bare `duckdb.connect()` (see pit/duck.py: a
    default memory_limit is ~80% of RAM, which is how INC-22 #4 OOM-killed the host)."""
    from .duck import connect

    return connect()


def read_schedule(season: int, *, con=None, url: str = SCHEDULES_URL) -> list[ScheduledGame]:
    """Every game of `season` that has a set kickoff, as UTC instants.

    A game with a blank `gametime` (not yet scheduled) is skipped — there is no checkpoint ladder
    to compute for it, and it will appear once the league sets the time.
    """
    con = con or _duck()
    cols = ", ".join(SCHEDULE_COLUMNS)
    try:
        rows = con.execute(
            f"SELECT {cols} FROM read_parquet(?) WHERE season = ? "
            "AND gameday IS NOT NULL AND gametime IS NOT NULL AND gametime <> ''",
            [url, int(season)],
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        raise ScheduleReadError(f"could not read nflverse schedules for {season}: {exc}") from exc

    et = _et_zone()
    idx = {c: i for i, c in enumerate(SCHEDULE_COLUMNS)}
    out: list[ScheduledGame] = []
    for r in rows:
        day, tod = str(r[idx["gameday"]])[:10], str(r[idx["gametime"]])
        try:
            kickoff = datetime.strptime(f"{day} {tod}", "%Y-%m-%d %H:%M").replace(tzinfo=et)
        except (ValueError, TypeError):
            continue
        out.append(
            ScheduledGame(
                game_id=str(r[idx["game_id"]]),
                season=int(r[idx["season"]]),
                week=int(r[idx["week"]]) if r[idx["week"]] is not None else -1,
                game_type=str(r[idx["game_type"]] or ""),
                kickoff_utc=kickoff.astimezone(timezone.utc),
                home_team=str(r[idx["home_team"]] or ""),
                away_team=str(r[idx["away_team"]] or ""),
                location=str(r[idx["location"]] or ""),
                roof=str(r[idx["roof"]] or ""),
                stadium=str(r[idx["stadium"]] or ""),
            )
        )
    return sorted(out, key=lambda g: g.kickoff_utc)


#: The week whose kickoff marks "every season-scoped asset should exist by now". Week 1's data is
#: published within a day or two of week 1 ending (Monday night), so week 2's first kickoff — the
#: following Thursday — is comfortably past it while still being early enough to catch a real
#: outage in the season's first fortnight.
DATA_EXPECTED_FROM_WEEK = 2

#: Used only when the schedule cannot be read. Deliberately LATE and deliberately fixed: by
#: October 1 of any normal season every asset exists, so the fallback can only ever DELAY a page,
#: never suppress one — and a schedule read that fails is its own loud problem.
_FALLBACK_EXPECTED_FROM = (10, 1)


def data_expected_from(
    season: int, *, games: list[ScheduledGame] | None = None
) -> datetime:
    """The instant from which a season-scoped nflverse asset SHOULD exist.

    ⏰ WHY THIS EXISTS. `current_season()` is right about which season we are IN and wrong as a
    proxy for which season nflverse has FILES for. It rolls to the new season in March, but
    nflverse publishes each season's assets only as data starts existing — measured 2026-08-05:
    `depth_charts_2026.parquet` was created 2026-08-04 (training camp) while `injuries_2026`,
    `play_by_play_2026`, `snap_counts_2026` and ten others did not exist at all. So for roughly
    six months a year, a season-scoped URL 404s **by design**.

    Before this instant a never-yet-published asset is EXPECTED-ABSENT (recorded, never paged);
    from it onward the same absence is a real defect. Without the bar the quiet branch would be
    unbounded — an asset nflverse never publishes would stay silent all season, which is the
    silent-death class this leg exists to prevent.
    """
    try:
        games = games if games is not None else read_schedule(season)
    except ScheduleReadError as exc:  # noqa: BLE001 — fail toward eventually paging, never silence
        log.warning(
            "[nfl/pit/schedule] could not read the %s schedule for the data-expected bar (%s) — "
            "falling back to %s-%02d-%02d",
            season, exc, season, *_FALLBACK_EXPECTED_FROM,
        )
        games = []
    kickoffs = [g.kickoff_utc for g in games if g.week == DATA_EXPECTED_FROM_WEEK]
    if kickoffs:
        return min(kickoffs)
    month, day = _FALLBACK_EXPECTED_FROM
    return datetime(int(season), month, day, tzinfo=timezone.utc)


def looks_like_missing_asset(error: str) -> bool:
    """True when a read failure is "the release asset does not exist", not "the read broke".

    ⚠️ MATCHED CONSERVATIVELY, AND THE DEFAULT IS TO ESCALATE. A network blip, a DNS failure or an
    auth error must never be laundered into "expected absence" — only an unambiguous not-found is.
    An unmatched error therefore keeps its escalation, which is the safe direction: a false page
    costs attention, a suppressed real break costs a season.
    """
    low = (error or "").lower()
    return "http 404" in low or "404 not found" in low


def current_season(now: datetime | None = None) -> int:
    """The NFL season a given instant belongs to.

    An NFL season spans the calendar boundary (Sep–Feb), so the season is the year of its
    SEPTEMBER. January/February belong to the PRIOR year's season — pinning a literal season is
    the NCAAF-P0.6 landmine this avoids.
    """
    now = now or datetime.now(timezone.utc)
    return now.year if now.month >= 3 else now.year - 1
