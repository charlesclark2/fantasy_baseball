"""venues.py — where a game is ACTUALLY played, and whether weather can reach the field.

Two live findings from this story's own probe of the nflverse `schedules` release (2026-08-05),
both of which silently corrupt a naive weather capture:

⭐ FINDING 1 — `roof` IS A POST-HOC FIELD AT RETRACTABLE VENUES, exactly like `temp`/`wind`.
   All 43 blank-`roof` rows in the whole release are season 2026 (unplayed), and they are
   precisely the five retractable-roof venues (State Farm/ARI · AT&T/DAL · NRG-Reliant/HOU ·
   Mercedes-Benz/ATL · Lucas Oil/IND) plus two neutral sites. Those venues NEVER carry the value
   `dome`; historically they carry `closed` (227 games) or `open` (32) — a value that only exists
   AFTER the game-day roof decision. So:
     • for a FUTURE game the roof state is genuinely UNKNOWN at projection time ⇒ we must CAPTURE
       (it might be open), and
     • the historical `closed`/`open` value is NOT point-in-time safe — using it in a Tuesday
       build is a leak, and gating training on it while gating serving on a blank produces
       train/serve skew.
   This extends NF-W0's defect #1 (`schedules.temp`/`wind` are realized, not forecast) to a
   column NF-W0 did not flag. `roof_known` carries the distinction into the store.

⭐ FINDING 2 — THE HOME TEAM'S STADIUM IS THE WRONG PLACE FOR A NEUTRAL-SITE GAME.
   2026 schedules 8 international games. `2026_11_MIN_SF` is listed with home_team `SF` but is
   played at Estadio Banorte in MEXICO CITY; `2026_01_SF_LA` is home_team `LA` at the MELBOURNE
   CRICKET GROUND. Fetching at the home team's coordinates would silently return Santa Clara /
   Inglewood weather — plausible numbers, wrong hemisphere, no error anywhere. nflverse's
   `stadium_id` is no help: Melbourne carries `LAX01`, i.e. the team's code, not the venue's.
   ⇒ a `location != 'Home'` game resolves through `NEUTRAL_SITE_VENUES` by stadium NAME, and an
   UNRECOGNISED neutral venue is REFUSED (loud), never fetched at the home team's coordinates.
   Silently capturing the wrong city is strictly worse than capturing nothing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

#: Team code → (home stadium latitude, longitude). MUST stay byte-identical to the coordinates in
#: `quant_sports_intel_models/sports_dbt/models/nfl/staging/stg_nfl_team_geo.sql` — one logical
#: fact with two owners is this repo's recurring bug shape (INC-30 crontab, INC-36 concurrency),
#: so `test_nfl_pit_capture.py` PARSES that SQL and fails on any drift rather than trusting prose.
TEAM_HOME_GEO: dict[str, tuple[float, float]] = {
    "ARI": (33.5276, -112.2626), "ATL": (33.7554, -84.4008),  "BAL": (39.2780, -76.6227),
    "BUF": (42.7738, -78.7870),  "CAR": (35.2258, -80.8528),  "CHI": (41.8623, -87.6167),
    "CIN": (39.0955, -84.5161),  "CLE": (41.5061, -81.6995),  "DAL": (32.7473, -97.0945),
    "DEN": (39.7439, -105.0201), "DET": (42.3400, -83.0456),  "GB":  (44.5013, -88.0622),
    "HOU": (29.6847, -95.4107),  "IND": (39.7601, -86.1639),  "JAX": (30.3239, -81.6373),
    "KC":  (39.0489, -94.4839),  "LV":  (36.0909, -115.1833), "LAC": (33.9535, -118.3392),
    "LAR": (33.9535, -118.3392), "MIA": (25.9580, -80.2389),  "MIN": (44.9736, -93.2575),
    "NE":  (42.0909, -71.2643),  "NO":  (29.9511, -90.0812),  "NYG": (40.8135, -74.0745),
    "NYJ": (40.8135, -74.0745),  "PHI": (39.9008, -75.1675),  "PIT": (40.4468, -80.0158),
    "SF":  (37.4033, -121.9694), "SEA": (47.5952, -122.3316), "TB":  (27.9759, -82.5033),
    "TEN": (36.1665, -86.7713),  "WAS": (38.9077, -76.8645),
}

#: nflverse `schedules` uses `LA` for the Rams in some rows and `LAR` in others; both resolve to
#: SoFi. Kept as an explicit alias map so an unknown code REFUSES rather than silently defaulting.
TEAM_CODE_ALIASES: dict[str, str] = {"LA": "LAR", "SD": "LAC", "OAK": "LV", "STL": "LAR", "WSH": "WAS"}

#: Neutral-site / international venues, keyed on the `stadium` NAME nflverse publishes. Covers
#: every 2026 international game plus the venues used 2022-2025 (a returning venue must not have
#: to be discovered again at kickoff). An unrecognised neutral venue is REFUSED — see module doc.
NEUTRAL_SITE_VENUES: dict[str, tuple[float, float]] = {
    # 2026 international slate (verified against the release 2026-08-05)
    "Melbourne Cricket Ground":   (-37.8200, 144.9834),
    "Maracana Stadium":           (-22.9121, -43.2302),
    "Tottenham Hotspur Stadium":  (51.6043, -0.0665),
    "Wembley Stadium":            (51.5560, -0.2795),
    "Stade de France":            (48.9245, 2.3601),
    "Bernabeu":                   (40.4531, -3.6883),
    "FC Bayern Munich Stadium":   (48.2188, 11.6247),
    "Estadio Banorte":            (19.3029, -99.1505),
    # recent-history venues that recur
    "Estadio Azteca":             (19.3029, -99.1505),
    "Allianz Arena":              (48.2188, 11.6247),
    "Deutsche Bank Park":         (50.0686, 8.6455),
    "Neo Quimica Arena":          (-23.5453, -46.4742),
    "Arena Corinthians":          (-23.5453, -46.4742),
    "Twickenham Stadium":         (51.4560, -0.3416),
    "Santiago Bernabeu":          (40.4531, -3.6883),
}

#: `roof` values meaning a FIXED indoor venue — weather cannot reach the field, ever.
FIXED_DOME_ROOFS = frozenset({"dome"})

#: `roof` values a RETRACTABLE venue takes, i.e. a value that is only knowable AFTER the game.
#: Present in history, never present for an unplayed game — see FINDING 1.
RETRACTABLE_ROOFS = frozenset({"closed", "open", "retractable"})


class VenueResolutionError(ValueError):
    """A game's playing location could not be resolved — capture is REFUSED for it."""


@dataclass(frozen=True)
class VenueDecision:
    """Where to fetch, and whether weather is worth fetching there."""

    latitude: float
    longitude: float
    venue_name: str
    is_neutral_site: bool
    roof_raw: str
    roof_known: bool
    is_fixed_dome: bool

    @property
    def capture(self) -> bool:
        """Capture unless the venue is a FIXED dome.

        Deliberately FAIL-OPEN on the capture decision and fail-closed on the USE decision. A
        retractable venue whose roof is unknown might be open, and an extra free Open-Meteo call
        costs nothing; NOT capturing costs the week permanently. Downstream gating reads
        `roof_known` / `is_fixed_dome` and can decide, because the fields are stored.
        """
        return not self.is_fixed_dome


def normalise_team(code: str | None) -> str | None:
    if not code:
        return None
    c = str(code).strip().upper()
    return TEAM_CODE_ALIASES.get(c, c)


def resolve_venue(game: dict) -> VenueDecision:
    """Resolve one scheduled game to (lat, lon) + the roof facts. Raises on an unresolvable venue.

    `game` carries the nflverse `schedules` fields: `home_team`, `location`, `roof`, `stadium`.
    """
    roof_raw = str(game.get("roof") or "").strip().lower()
    roof_known = bool(roof_raw)
    is_fixed_dome = roof_raw in FIXED_DOME_ROOFS
    stadium = str(game.get("stadium") or "").strip()
    location = str(game.get("location") or "").strip().lower()

    if location and location != "home":
        if not stadium:
            raise VenueResolutionError(
                f"game {game.get('game_id')!r} is location={game.get('location')!r} (neutral) with "
                f"no stadium name — REFUSED (the home team's coordinates are the wrong city)"
            )
        coords = NEUTRAL_SITE_VENUES.get(stadium)
        if coords is None:
            raise VenueResolutionError(
                f"game {game.get('game_id')!r} is at UNKNOWN neutral venue {stadium!r} — REFUSED. "
                f"Add it to NEUTRAL_SITE_VENUES; falling back to the home team's stadium would "
                f"silently capture the wrong city's weather (see venues.py FINDING 2)."
            )
        return VenueDecision(coords[0], coords[1], stadium, True, roof_raw, roof_known, is_fixed_dome)

    team = normalise_team(game.get("home_team"))
    coords = TEAM_HOME_GEO.get(team) if team else None
    if coords is None:
        raise VenueResolutionError(
            f"game {game.get('game_id')!r}: unknown home team code {game.get('home_team')!r} — "
            f"REFUSED (no coordinates; add it to TEAM_HOME_GEO/TEAM_CODE_ALIASES)"
        )
    return VenueDecision(
        coords[0], coords[1], stadium or f"{team} home", False, roof_raw, roof_known, is_fixed_dome
    )
