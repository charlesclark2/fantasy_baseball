"""yahoo.py — the Yahoo Fantasy Sports league-import adapter (NF-C0).

Yahoo is the one MAJOR platform with an OFFICIAL, ToS-blessed, OAuth2-gated read API — which is why
it ships beside Sleeper rather than falling to the manual floor: the user grants a read-only,
revocable permission on Yahoo's own consent screen and we never touch their password.

🔎 PROBED LIVE 2026-08-01 (the endpoints and their shapes were verified, not assumed):
  * Base URL `https://fantasysports.yahooapis.com/fantasy/v2` — confirmed live, 401 unauthenticated.
  * `/league/{league_key}/settings` · `/league/{league_key}/teams` · `/league/{league_key}/draftresults`
    · `/users;use_login=1/games;game_keys=nfl/leagues` — all present in the current documentation at
    `sports.yahoo.com/developer/docs/` (the old `developer.yahoo.com/fantasysports/guide/` now
    308-redirects there).
  * `game_key` for the 2025 NFL season is `461`; the literal `nfl` always resolves to the CURRENT
    season, which is what a league picker should use.

⚠️ WHAT IS AND IS NOT VERIFIED. The endpoint list, the auth flow and the stat-id table are probe- or
doc-verified. The RESPONSE PARSING below could not be exercised against a live payload, because
every Fantasy resource requires an approved developer app and Yahoo now gates that behind an
application REVIEW (see `docs/nf_c0_yahoo_oauth_setup.md`). Two consequences shaped this module:
  1. Parsing is done by SEARCHING the response tree for the keys we need, never by indexing fixed
     positions (`league[1]["settings"][0]`). Yahoo's JSON is a notorious mix of arrays and
     numeric-keyed objects whose ordering varies by resource, so positional parsing is exactly the
     code that breaks on the first real payload. A tree walk is invariant to that.
  2. Scoring is mapped by STAT ID, not by display name. Yahoo ships two stats called almost the
     same thing — id 6 "Interceptions" (thrown by a QB) and id 33 "Interception" (made by a
     defense) — and a name-matching importer silently pays a quarterback for defensive picks. Ids
     are stable across seasons and unambiguous; the live `stat_categories` names are used only to
     LABEL the terms we could not map.

🚩 ATTRIBUTION. Yahoo's API terms require "Fantasy data provided by Yahoo Fantasy" to be displayed
with a link back to Yahoo Fantasy wherever this data is shown. `ATTRIBUTION` below is the string the
UI renders; it is part of the integration's compliance, not decoration.
"""

from __future__ import annotations

import re
from typing import Iterator

from app.backend.services.platform_import import canonical as C
from app.backend.services.platform_import.http import PlatformHTTPError, get_json
from app.backend.services.platform_import.yahoo_oauth import YahooNotEntitled

BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"
PLATFORM = "yahoo"

ATTRIBUTION = "Fantasy data provided by Yahoo Fantasy"
ATTRIBUTION_URL = "https://football.fantasysports.yahoo.com/"

# Yahoo's `oauth_problem` for "valid token, but this app may not read Fantasy data" (MEASURED
# 2026-08-19: every `/fantasy/v2/*` resource returned it while `openid/v1/userinfo` returned 200 for
# the same token). It arrives as a bare 401, so the body is the only discriminator.
_NOT_ENTITLED = "additional_authorization_required"

# `{game_key}.l.{league_id}` — e.g. `461.l.1000`. Validated before any URL is built (SSRF guard).
_LEAGUE_KEY_RE = re.compile(r"^[0-9]{1,6}\.l\.[0-9]{1,12}$")

# How many player keys to resolve per `players;player_keys=` call, and the call ceiling. A deep
# dynasty draft can run to hundreds of picks; without a cap, naming every one would fan a single
# import into dozens of upstream calls. The cap is DISCLOSED in a warning when it binds rather than
# silently returning a partial draft.
_PLAYER_BATCH = 25
_MAX_PLAYER_BATCHES = 12


class YahooInputError(ValueError):
    """A malformed league key — the user's mistake, not the platform's (→ 422, not 502)."""


# ── scoring: Yahoo stat_id → canonical key(s) ─────────────────────────────────────────────────────
# A two-entry tuple means Yahoo's bucket is COARSER than ours and the same weight restates it
# exactly across both of our finer buckets — our nine points-allowed buckets were chosen as the
# common refinement of the ESPN and Yahoo tables precisely so this is lossless.
STAT_ID_MAP: dict[str, tuple[str, ...]] = {
    # passing
    "4": ("pass_yds",),
    "5": ("pass_td",),
    "6": ("pass_int",),  # ⚠️ thrown by the passer — NOT the defensive interception (id 33)
    "1": ("pass_att",),
    "2": ("pass_cmp",),
    # rushing
    "8": ("rush_att",),
    "9": ("rush_yds",),
    "10": ("rush_td",),
    # receiving
    "11": ("rec",),
    "12": ("rec_yds",),
    "13": ("rec_td",),
    "78": ("targets",),
    # misc offence
    "15": ("st_player_td",),  # "Return Touchdowns" — credited to the returning PLAYER
    "16": ("two_pt",),
    "18": ("fumbles_lost",),
    "57": ("fumble_rec_td",),  # "Offensive Fumble Return TD"
    # kicking
    "19": ("fg_made_0_19",),
    "20": ("fg_made_20_29",),
    "21": ("fg_made_30_39",),
    "22": ("fg_made_40_49",),
    "23": ("fg_made_50_59", "fg_made_60p"),  # Yahoo's "50+" covers both of our buckets
    "29": ("pat_made",),
    "30": ("pat_missed",),
    "24": ("fg_missed",),
    # team defence
    "32": ("def_sacks",),
    "33": ("def_int",),  # ⚠️ made BY a defense — NOT the passer's interception (id 6)
    "34": ("def_fumble_rec",),
    "35": ("def_td",),
    "36": ("def_safety",),
    "37": ("def_blocked_kick",),
    "49": ("st_td",),  # "Kickoff and Punt Return Touchdowns" — credited to the DEF/ST unit
    # team defence — points allowed
    "50": ("dst_pa_g_0",),
    "51": ("dst_pa_g_1_6",),
    "52": ("dst_pa_g_7_13",),
    "53": ("dst_pa_g_14_17", "dst_pa_g_18_20"),
    "54": ("dst_pa_g_21_27",),
    "55": ("dst_pa_g_28_34",),
    "56": ("dst_pa_g_35_45", "dst_pa_g_46p"),
}

# Yahoo roster-position token → (canonical slot name, eligibility, is_bench).
ROSTER_SLOT_MAP: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "QB": ("QB", ("QB",), False),
    "RB": ("RB", ("RB",), False),
    "WR": ("WR", ("WR",), False),
    "TE": ("TE", ("TE",), False),
    "K": ("K", ("K",), False),
    "DEF": ("DST", ("DST",), False),
    "W/R": ("W/R FLEX", C.RB_WR_ELIG, False),
    "W/T": ("W/T FLEX", C.WR_TE_ELIG, False),
    "W/R/T": ("FLEX", C.FLEX_ELIG, False),
    "R/W/T": ("FLEX", C.FLEX_ELIG, False),
    "Q/W/R/T": ("SUPERFLEX", C.SUPERFLEX_ELIG, False),
    "D": ("IDP", C.IDP_ELIG, False),
    "DL": ("DL", ("DL",), False),
    "LB": ("LB", ("LB",), False),
    "DB": ("DB", ("DB",), False),
    "BN": ("BN", (), True),
    "IR": ("IR", (), True),
    "IR+": ("IR", (), True),
    "IL": ("IR", (), True),
}


# ── Yahoo JSON traversal ──────────────────────────────────────────────────────────────────────────
# Yahoo mixes three container idioms in one document: plain objects, arrays of single-key objects,
# and "collections" keyed by stringified integers alongside a sibling `count`. Everything below
# walks the tree instead of indexing it, so a reshuffle upstream degrades to a missing field rather
# than an IndexError on an unrelated key.


def _walk(node: object) -> Iterator[dict]:
    """Yield every dict in the tree, depth-first."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _find_first(node: object, key: str) -> object:
    for d in _walk(node):
        if key in d:
            return d[key]
    return None


def _find_all(node: object, key: str) -> list:
    return [d[key] for d in _walk(node) if key in d]


def _collection(node: object) -> list:
    """Flatten a Yahoo numeric-keyed collection (`{"0": {...}, "1": {...}, "count": 2}`) to a list.

    Plain lists pass through unchanged so callers do not have to know which idiom a given resource
    used — that choice varies by endpoint and has changed between Yahoo API revisions.
    """
    if isinstance(node, list):
        return list(node)
    if isinstance(node, dict):
        out = []
        for key in sorted((k for k in node if str(k).isdigit()), key=lambda k: int(k)):
            out.append(node[key])
        return out
    return []


def _merge_fragments(node: object) -> dict:
    """Yahoo splits one entity across an array of partial objects — merge them into one dict.

    A team arrives as `[[{"team_key":…},{"name":…},…], {"roster":…}]`: a list whose first element is
    itself a list of single-key fragments. Merging is what lets the rest of this module treat a
    team as a normal dict.
    """
    merged: dict = {}

    def _absorb(value: object) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                merged.setdefault(k, v)
        elif isinstance(value, list):
            for item in value:
                _absorb(item)

    _absorb(node)
    return merged


def _num(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


# ── authenticated fetch ───────────────────────────────────────────────────────────────────────────


def _get(path: str, access_token: str) -> object:
    """GET a Fantasy resource as JSON on behalf of the user.

    `format=json` is REQUIRED — the API answers XML by default, and a caller that forgets it gets a
    parse failure that reads like an outage.
    """
    joiner = "&" if "?" in path else "?"
    url = f"{BASE_URL}{path}{joiner}format=json"
    try:
        return get_json(url, headers={"Authorization": f"Bearer {access_token}"})
    except PlatformHTTPError as e:
        # ⭐ A 401 here has TWO causes that Yahoo spells identically in the status line and
        # distinguishes only in the body. `additional_authorization_required` means the APP lacks
        # Fantasy data access — telling that user to reconnect loops them through the consent
        # screen on a fault only the operator can clear. See `YahooNotEntitled`.
        if e.status == 401 and _NOT_ENTITLED in (e.body or ""):
            raise YahooNotEntitled(
                "Yahoo import is not available yet — our application does not have access to "
                "Yahoo's fantasy data. Reconnecting will not help; this is ours to fix."
            ) from e
        raise


def list_leagues(access_token: str, game_key: str = "nfl") -> list[dict]:
    """The logged-in user's leagues for a game — the league PICKER's data.

    `game_key='nfl'` resolves to the CURRENT season by Yahoo's own convention, so the picker follows
    the season rollover without a code change.
    """
    if not re.match(r"^[A-Za-z0-9]{1,8}$", game_key):
        raise YahooInputError("Invalid game key.")
    payload = _get(f"/users;use_login=1/games;game_keys={game_key}/leagues", access_token)

    out: list[dict] = []
    for leagues_node in _find_all(payload, "leagues"):
        for entry in _collection(leagues_node):
            league = _merge_fragments(_find_first(entry, "league") or entry)
            league_key = str(league.get("league_key") or "")
            if not league_key:
                continue
            out.append(
                {
                    "league_id": league_key,
                    "name": str(league.get("name") or "Yahoo league"),
                    "season": str(league.get("season") or ""),
                    "total_rosters": int(_num(league.get("num_teams"))),
                    "status": "in_season" if str(league.get("is_finished") or "0") != "1" else "complete",
                    "sport": "nfl",
                }
            )
    # A user in the same league across seasons can surface duplicates; key on the league key.
    unique: dict[str, dict] = {}
    for league in out:
        unique.setdefault(league["league_id"], league)
    return list(unique.values())


def _stat_names(access_token: str, game_key: str) -> dict[str, str]:
    """`stat_id -> human name` for the league's game, used to LABEL terms we could not map.

    Best-effort by design: if this call fails the import still succeeds, the unmapped terms just
    read as raw ids. A cosmetic lookup must never be able to fail an import.
    """
    try:
        payload = _get(f"/game/{game_key}/stat_categories", access_token)
    except (PlatformHTTPError, ValueError):
        return {}
    names: dict[str, str] = {}
    for stat_node in _find_all(payload, "stat"):
        stat = _merge_fragments(stat_node)
        stat_id = str(stat.get("stat_id") or "")
        name = str(stat.get("name") or stat.get("display_name") or "")
        if stat_id and name:
            names[stat_id] = name
    return names


def _translate_scoring(settings: dict, stat_names: dict[str, str]) -> tuple[C.ScoringTranslation, list[str]]:
    """`stat_modifiers` → canonical `per_stat`, with unmapped ids carried through under a readable
    key so they land in the coverage report as CAPTURED rather than disappearing."""
    modifiers = _find_first(settings.get("stat_modifiers"), "stats")
    raw: dict[str, object] = {}
    for entry in _collection(modifiers) or _collection(settings.get("stat_modifiers")):
        stat = _merge_fragments(_find_first(entry, "stat") or entry)
        stat_id = str(stat.get("stat_id") or "")
        if stat_id:
            raw[stat_id] = _num(stat.get("value"))

    translated = C.ScoringTranslation()
    for stat_id, value in sorted(raw.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        weight = float(value)  # type: ignore[arg-type]
        targets = STAT_ID_MAP.get(stat_id)
        if targets:
            for canonical in targets:
                translated.per_stat[canonical] = weight
            continue
        # Unmapped: keep the rule under a self-describing key. `yahoo_<id>_<slug>` stays stable
        # across imports (the id leads) while still being readable to the user.
        label = stat_names.get(stat_id, "")
        slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") if label else ""
        key = f"yahoo_{stat_id}" + (f"_{slug}" if slug else "")
        translated.per_stat[key] = weight
        if abs(weight) > 1e-12:
            translated.unmapped.append(key)

    return translated, []


def _translate_roster(settings: dict) -> tuple[list[dict], list[str]]:
    """`roster_positions` → counted `RosterSlot` dicts.

    Yahoo already gives a COUNT per position (unlike Sleeper's one-entry-per-seat listing), so the
    seat sequence is reconstructed before collapsing — keeping one code path for both platforms.
    """
    warnings: list[str] = []
    unknown: set[str] = set()
    sequence: list[tuple[str, tuple[str, ...], bool]] = []

    positions = settings.get("roster_positions")
    for entry in _collection(positions) or _collection(_find_first(positions, "roster_positions")):
        slot = _merge_fragments(_find_first(entry, "roster_position") or entry)
        token = str(slot.get("position") or "").strip()
        if not token:
            continue
        count = int(_num(slot.get("count"), 0))
        if count <= 0:
            continue
        mapped = ROSTER_SLOT_MAP.get(token)
        if mapped is None:
            unknown.add(token)
            # Unknown → BENCH: a bench slot creates no starter demand, so an unrecognised token can
            # never inflate replacement level and distort the board (dropping it would understate
            # the roster instead).
            mapped = (token, (), True)
        for _ in range(count):
            sequence.append(mapped)

    if unknown:
        warnings.append(
            "These roster slots are not ones we rank, so they were saved as bench spots and do not "
            f"affect the board: {', '.join(sorted(unknown))}."
        )
    return C.collapse_slots(sequence), warnings


def _captured_rules(settings: dict, league: dict) -> dict[str, object]:
    out: dict[str, object] = {}
    if str(settings.get("uses_playoff") or "") == "1" and settings.get("playoff_start_week"):
        out["playoff_weeks"] = int(_num(settings.get("playoff_start_week")))
    if str(settings.get("uses_fractional_points") or "") == "1":
        out["fractional_scoring"] = True
    if str(settings.get("is_auction_draft") or "") == "1":
        out["auction_draft"] = True
    scoring_type = str(league.get("scoring_type") or "")
    if scoring_type and scoring_type != "head":
        out["scoring_type"] = scoring_type
    return out


def _fetch_teams(league_key: str, access_token: str) -> tuple[C.ImportedTeam, ...]:
    """Every team plus its roster, in ONE call.

    `/league/{key}/teams/roster` uses the documented "any team sub-resource is valid under the teams
    collection" rule, which turns what would be 1 + N requests into 1 — the difference between an
    import that fits comfortably inside an API Gateway request window and one that does not.
    """
    payload = _get(f"/league/{league_key}/teams/roster", access_token)
    teams: list[C.ImportedTeam] = []
    for teams_node in _find_all(payload, "teams"):
        for entry in _collection(teams_node):
            team = _merge_fragments(_find_first(entry, "team") or entry)
            team_key = str(team.get("team_key") or "")
            if not team_key:
                continue
            managers = _find_all(entry, "manager")
            owner = None
            is_owner = False
            for raw_manager in managers:
                manager = _merge_fragments(raw_manager)
                owner = owner or str(manager.get("nickname") or "") or None
                if str(manager.get("is_current_login") or "0") == "1":
                    is_owner = True

            players: list[C.ImportedPlayer] = []
            for player_node in _find_all(entry, "player"):
                player = _merge_fragments(player_node)
                player_key = str(player.get("player_key") or "")
                if not player_key:
                    continue
                selected = _merge_fragments(player.get("selected_position"))
                position = str(selected.get("position") or "")
                players.append(
                    C.ImportedPlayer(
                        player_key=player_key,
                        name=str(_merge_fragments(player.get("name")).get("full") or player_key),
                        position=str(player.get("display_position") or "") or None,
                        team=str(player.get("editorial_team_abbr") or "") or None,
                        starter=bool(position) and position not in ("BN", "IR", "IR+", "IL"),
                    )
                )
            teams.append(
                C.ImportedTeam(
                    team_key=team_key,
                    name=str(team.get("name") or "Team"),
                    owner=owner,
                    is_owner=is_owner,
                    players=tuple(players),
                )
            )
    return tuple(teams)


def _resolve_player_names(
    league_key: str, access_token: str, player_keys: list[str]
) -> tuple[dict[str, C.ImportedPlayer], bool]:
    """Batch-resolve draft player keys to names. Returns `(by_key, truncated)`."""
    resolved: dict[str, C.ImportedPlayer] = {}
    batches = [
        player_keys[i : i + _PLAYER_BATCH] for i in range(0, len(player_keys), _PLAYER_BATCH)
    ]
    truncated = len(batches) > _MAX_PLAYER_BATCHES
    for batch in batches[:_MAX_PLAYER_BATCHES]:
        try:
            payload = _get(f"/league/{league_key}/players;player_keys={','.join(batch)}", access_token)
        except PlatformHTTPError:
            # Names are an enrichment; a failed batch leaves those picks keyed by id rather than
            # failing the whole draft read.
            continue
        for player_node in _find_all(payload, "player"):
            player = _merge_fragments(player_node)
            player_key = str(player.get("player_key") or "")
            if not player_key:
                continue
            resolved[player_key] = C.ImportedPlayer(
                player_key=player_key,
                name=str(_merge_fragments(player.get("name")).get("full") or player_key),
                position=str(player.get("display_position") or "") or None,
                team=str(player.get("editorial_team_abbr") or "") or None,
            )
    return resolved, truncated


def fetch_draft_state(league_key: str, access_token: str) -> C.DraftState:
    """The league's draft results — fetched LIVE, never persisted (see `DraftState`)."""
    if not _LEAGUE_KEY_RE.match(league_key or ""):
        raise YahooInputError("Invalid Yahoo league key.")
    payload = _get(f"/league/{league_key}/draftresults", access_token)

    raw_picks: list[dict] = []
    for results_node in _find_all(payload, "draft_results"):
        for entry in _collection(results_node):
            result = _merge_fragments(_find_first(entry, "draft_result") or entry)
            if result.get("pick") is not None or result.get("player_key"):
                raw_picks.append(result)
    if not raw_picks:
        return C.DraftState(note="This league has not drafted yet.")

    player_keys = [str(p.get("player_key")) for p in raw_picks if p.get("player_key")]
    names, truncated = _resolve_player_names(league_key, access_token, player_keys)

    picks = [
        C.DraftPick(
            pick_no=int(_num(pick.get("pick"))),
            round=int(_num(pick.get("round"))),
            team_key=str(pick.get("team_key") or "") or None,
            player=names.get(
                str(pick.get("player_key") or ""),
                C.ImportedPlayer(
                    player_key=str(pick.get("player_key") or ""),
                    name=str(pick.get("player_key") or ""),
                )
                if pick.get("player_key")
                else None,
            ),
        )
        for pick in raw_picks
    ]
    picks.sort(key=lambda p: p.pick_no)
    return C.DraftState(
        status="complete" if picks else None,
        rounds=max((p.round for p in picks), default=None),
        picks=tuple(picks),
        note=(
            f"Showing the first {_PLAYER_BATCH * _MAX_PLAYER_BATCHES} drafted players by name; the "
            "rest are listed by Yahoo player ID."
            if truncated
            else ""
        ),
    )


def import_league(league_key: str, access_token: str, *, include_draft: bool = True) -> C.ImportedLeague:
    """Pull one Yahoo league into the shared `LeagueConfig` + its live roster/draft state."""
    league_key = (league_key or "").strip()
    if not _LEAGUE_KEY_RE.match(league_key):
        raise YahooInputError(
            "That does not look like a Yahoo league key (it should look like 461.l.1000)."
        )

    payload = _get(f"/league/{league_key}/settings", access_token)
    league = _merge_fragments(_find_first(payload, "league"))
    settings = _merge_fragments(_find_first(payload, "settings"))
    if not settings:
        raise PlatformHTTPError("Yahoo returned no settings for that league.", status=404)

    game_key = league_key.split(".", 1)[0]
    scoring, warnings = _translate_scoring(settings, _stat_names(access_token, game_key))
    roster, roster_warnings = _translate_roster(settings)
    warnings.extend(roster_warnings)

    n_teams = int(_num(league.get("num_teams")))
    config = C.build_config(
        name=str(league.get("name") or "Yahoo league"),
        n_teams=n_teams,
        per_stat=scoring.per_stat,
        roster=roster,
        position_bonuses=scoring.position_bonuses,
        captured_rules=_captured_rules(settings, league),
        description=f"Imported from Yahoo ({league.get('season') or ''}).".replace(" )", ")"),
    )
    if not C.config_is_rankable(config):
        raise YahooInputError(
            "This league has no starting lineup slots we can rank against, so a draft board cannot "
            "be built from it. You can still enter it by hand under League settings."
        )

    return C.ImportedLeague(
        platform=PLATFORM,
        source_league_id=league_key,
        season=str(league.get("season") or "") or None,
        config=config,
        teams=_fetch_teams(league_key, access_token),
        draft=fetch_draft_state(league_key, access_token) if include_draft else None,
        warnings=tuple(warnings),
        unmapped_scoring_keys=tuple(sorted(scoring.unmapped)),
    )


__all__ = [
    "ATTRIBUTION",
    "ATTRIBUTION_URL",
    "PLATFORM",
    "ROSTER_SLOT_MAP",
    "STAT_ID_MAP",
    "YahooInputError",
    "fetch_draft_state",
    "import_league",
    "list_leagues",
]
