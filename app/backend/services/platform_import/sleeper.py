"""sleeper.py — the Sleeper league-import adapter (NF-C0).

Sleeper publishes a genuinely PUBLIC, read-only, unauthenticated HTTP API
(https://docs.sleeper.com/). That makes it the cleanest possible fit for this story's hard red line:
there is no credential to hold, no OAuth to broker, and nothing a user has to paste but their own
username or league id. It is the reason Sleeper is the first adapter shipped rather than the
biggest-reach one.

🔎 PROBED LIVE 2026-08-01, not read off documentation (the E7.2 / NF-D8 discipline):
  * `GET /v1/state/nfl` → 200, `season=2026`, `season_start_date=2026-08-06` (draft season is live).
  * `GET /v1/user/<name>` → 200 with a `user_id`; an unknown user returns `null` with a 200.
  * `GET /v1/league/<id>` → the real payload this module is written against: `scoring_settings`
    (a flat weight map), `roster_positions` (ONE ENTRY PER SEAT), `settings` (num_teams,
    league_average_match, best_ball, playoff_week_start, taxi_slots, reserve_slots, type).
  * `GET /v1/league/<id>/rosters` · `/users` · `/drafts` · `GET /v1/draft/<id>/picks` → all live.
  * Documented limit: stay under 1000 calls/minute or risk an IP block. One import is ~5 calls, so
    the ceiling is irrelevant per-user — but it is a SHARED ceiling across all our users on one
    Lambda egress IP, which is why nothing here loops or polls.

⚠️ THE TWO PLACES A NAIVE IMPORT LOSES THE LEAGUE'S ACTUAL RULES, both handled below:
  1. `bonus_rec_te` / `bonus_rec_rb` / `bonus_rec_wr` are PER-POSITION reception premiums. Folding
     them into the flat `rec` weight would pay every position the TE premium; they belong in
     `position_bonuses` (which is exactly what that engine field exists for).
  2. `reserve_slots` (IR) and `taxi_slots` are REAL roster spots that do NOT appear in
     `roster_positions` — verified on a live league whose 27 `roster_positions` entries omitted its
     3 IR and 5 taxi spots. Importing only `roster_positions` silently shrinks the roster.
"""

from __future__ import annotations

import re

from app.backend.services.platform_import import canonical as C
from app.backend.services.platform_import.http import PlatformHTTPError, get_json

BASE_URL = "https://api.sleeper.app/v1"
PLATFORM = "sleeper"

# 🔒 SSRF / path-injection guard. These values come straight from a user-supplied form field and are
# interpolated into a URL, so they are validated against the platform's real id shapes BEFORE any
# request is built — never sanitized after the fact. Sleeper ids are decimal snowflakes; usernames
# are the limited set Sleeper itself allows.
_ID_RE = re.compile(r"^[0-9]{1,24}$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_SEASON_RE = re.compile(r"^(19|20)[0-9]{2}$")


class SleeperInputError(ValueError):
    """A malformed username/league id — the user's mistake, not the platform's (→ 422, not 502)."""


# ── scoring vocabulary ────────────────────────────────────────────────────────────────────────────
# Sleeper key → canonical key(s). A tuple with TWO entries means Sleeper's bucket is COARSER than
# ours and the same weight restates it EXACTLY across both of our finer buckets (see
# `apply_scoring_map`). Everything NOT listed here rides through under its Sleeper key and is
# reported CAPTURED — deliberately, so a rule we cannot project is preserved and disclosed rather
# than dropped.
SCORING_KEY_MAP: dict[str, tuple[str, ...]] = {
    # passing
    "pass_yd": ("pass_yds",),
    "pass_td": ("pass_td",),
    "pass_int": ("pass_int",),
    "pass_cmp": ("pass_cmp",),
    "pass_att": ("pass_att",),
    # rushing
    "rush_yd": ("rush_yds",),
    "rush_td": ("rush_td",),
    "rush_att": ("rush_att",),
    # receiving
    "rec": ("rec",),
    "rec_yd": ("rec_yds",),
    "rec_td": ("rec_td",),
    # misc offence
    "fum_lost": ("fumbles_lost",),
    "fum_rec_td": ("fumble_rec_td",),
    # ⚠️ `st_td` is Sleeper's PLAYER-credited return TD; the DEF unit's version is `def_st_td`
    # below. Mapping both to the same canonical key would double-count a single return TD.
    "st_td": ("st_player_td",),
    # kicking — Sleeper's 50+ bucket covers our 50-59 AND 60+, so both take the same weight
    "fgm_0_19": ("fg_made_0_19",),
    "fgm_20_29": ("fg_made_20_29",),
    "fgm_30_39": ("fg_made_30_39",),
    "fgm_40_49": ("fg_made_40_49",),
    # ⚠️ Sleeper supports BOTH a coarse 50+ bucket AND the finer 50-59 / 60+ pair, and real leagues
    # use either — a live league was found paying 5 for 50-59 and 6 for 60+, and the first cut,
    # which mapped only `fgm_50p`, silently dropped both of those rules to "captured" even though
    # the catalog has an exact column for each. The coarse key fans out across both of our buckets;
    # the fine keys map one-to-one. `_translate_scoring` drops the coarse key when a fine one is
    # present, so a league that somehow sets both is not resolved by dict ordering.
    "fgm_50p": ("fg_made_50_59", "fg_made_60p"),
    "fgm_50_59": ("fg_made_50_59",),
    "fgm_60p": ("fg_made_60p",),
    "fgmiss": ("fg_missed",),
    "xpm": ("pat_made",),
    "xpmiss": ("pat_missed",),
    # team defence
    "sack": ("def_sacks",),
    "int": ("def_int",),
    "fum_rec": ("def_fumble_rec",),
    "ff": ("def_forced_fumble",),
    "safe": ("def_safety",),
    "blk_kick": ("def_blocked_kick",),
    "def_td": ("def_td",),
    "def_st_td": ("st_td",),
    # team defence — points allowed. Sleeper's 7-tier table restates EXACTLY on our nine buckets,
    # which were chosen as the common refinement of the ESPN and Yahoo schemes.
    "pts_allow_0": ("dst_pa_g_0",),
    "pts_allow_1_6": ("dst_pa_g_1_6",),
    "pts_allow_7_13": ("dst_pa_g_7_13",),
    "pts_allow_14_20": ("dst_pa_g_14_17", "dst_pa_g_18_20"),
    "pts_allow_21_27": ("dst_pa_g_21_27",),
    "pts_allow_28_34": ("dst_pa_g_28_34",),
    "pts_allow_35p": ("dst_pa_g_35_45", "dst_pa_g_46p"),
}

# Per-position reception premiums → `position_bonuses` (see the module docstring, point 1).
BONUS_KEY_MAP: dict[str, tuple[str, str]] = {
    "bonus_rec_te": ("TE", "rec"),
    "bonus_rec_rb": ("RB", "rec"),
    "bonus_rec_wr": ("WR", "rec"),
}

# Sleeper splits the 2-point conversion into three per-phase keys; our catalog has ONE `two_pt`.
# Handled outside `apply_scoring_map` because collapsing three keys onto one is only lossless when
# they AGREE — and when they disagree we must say so rather than let last-write-wins pick silently.
_TWO_PT_KEYS = ("pass_2pt", "rush_2pt", "rec_2pt")

# Sleeper slot token → (canonical slot name, eligibility, is_bench).
ROSTER_SLOT_MAP: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "QB": ("QB", ("QB",), False),
    "RB": ("RB", ("RB",), False),
    "WR": ("WR", ("WR",), False),
    "TE": ("TE", ("TE",), False),
    "K": ("K", ("K",), False),
    "DEF": ("DST", ("DST",), False),
    "FLEX": ("FLEX", C.FLEX_ELIG, False),
    "SUPER_FLEX": ("SUPERFLEX", C.SUPERFLEX_ELIG, False),
    "REC_FLEX": ("REC_FLEX", C.WR_TE_ELIG, False),
    "WRRB_FLEX": ("WR/RB FLEX", C.RB_WR_ELIG, False),
    "IDP_FLEX": ("IDP FLEX", C.IDP_ELIG, False),
    "DL": ("DL", ("DL",), False),
    "LB": ("LB", ("LB",), False),
    "DB": ("DB", ("DB",), False),
    "BN": ("BN", (), True),
    "IR": ("IR", (), True),
    "TAXI": ("TAXI", (), True),
}

# `settings.type` — Sleeper's league-format code.
_LEAGUE_TYPE = {0: "redraft", 1: "keeper", 2: "dynasty"}


def _url(path: str) -> str:
    return f"{BASE_URL}{path}"


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


# ── public lookups ────────────────────────────────────────────────────────────────────────────────


def resolve_user(username_or_id: str) -> dict:
    """Resolve a Sleeper username (or numeric user id) to `{user_id, display_name}`.

    Sleeper answers an unknown user with a 200 and a `null` body, so a miss is detected on the
    PAYLOAD, not the status code — treating it as a transport error would tell the user "Sleeper is
    down" when they simply mistyped their name.
    """
    value = (username_or_id or "").strip()
    if not (_USERNAME_RE.match(value) or _ID_RE.match(value)):
        raise SleeperInputError("That does not look like a Sleeper username.")
    payload = _as_dict(get_json(_url(f"/user/{value}")))
    user_id = str(payload.get("user_id") or "")
    if not user_id:
        raise SleeperInputError(
            f"Sleeper has no user called {value!r}. Check the spelling, or paste your league ID "
            "instead — it is the long number in your league's URL."
        )
    return {
        "user_id": user_id,
        "display_name": str(payload.get("display_name") or value),
    }


def resolve_target(value: str, season: str, sport: str = "nfl") -> dict:
    """Accept whatever identifier the user actually has, and work out what it is.

    ⭐ WHY THIS EXISTS. The first field asked for a "Sleeper username", but the identifier a user
    has to hand is almost always the **league ID** — it sits right in the league's URL
    (`sleeper.app/leagues/<id>`), whereas a username has to be recalled and a user ID is never
    surfaced in Sleeper's UI at all. Making the user supply the one identifier they DON'T have is a
    self-inflicted dead end, so this accepts a username, a league ID, or a user ID.

    Returns either:
      * `{"kind": "league", "league": {...}, "leagues": [{...}]}` — the value was a league; a caller
        that understands `kind` goes straight to preview.
      * `{"kind": "user", "user": {...}, "leagues": [...]}` — the value was a user; pick a league.

    🚨 `leagues` IS ALWAYS PRESENT, in both branches, and that is load-bearing rather than tidy.
    The API Lambda and the Next.js frontend deploy INDEPENDENTLY (the Lambda has no CI/CD — it ships
    only via `infrastructure/lambda/deploy.sh`), so there is always a window where one side is newer
    than the other. The first cut of this function returned `{"kind": "league", "league": ...}` with
    no `leagues` key; an older frontend read `res.leagues`, got `undefined`, and rendered NOTHING on
    a 200 — a silent empty with no error anywhere, which is this repo's most-repeated failure shape.
    ⇒ **a change to a deployed endpoint's response must be ADDITIVE**: add `kind`, never remove the
    key the previous client reads.

    ⚠️ A bare number is AMBIGUOUS — Sleeper league ids and user ids are both snowflakes and are
    indistinguishable by shape. **League is tried first** because that is overwhelmingly where a
    user gets a number from (the league URL). Falling back to the user lookup costs one extra
    request only in the rare case, and the error when BOTH miss names both possibilities rather
    than blaming the one we happened to try.
    """
    value = (value or "").strip()
    if not value:
        raise SleeperInputError("Enter your Sleeper username or a league ID.")

    if _ID_RE.match(value) and len(value) >= 6:
        league = _as_dict(get_json(_url(f"/league/{value}")))
        if league.get("league_id"):
            summary = {
                "league_id": str(league.get("league_id")),
                "name": str(league.get("name") or "Sleeper league"),
                "season": str(league.get("season") or ""),
                "total_rosters": int(league.get("total_rosters") or 0),
                "status": str(league.get("status") or ""),
                "sport": str(league.get("sport") or "nfl"),
            }
            # `leagues` is duplicated here ON PURPOSE — see the docstring. A client that predates
            # `kind` reads this key and renders a one-item picker instead of a blank screen.
            return {"kind": "league", "league": summary, "leagues": [summary]}
        user = _as_dict(get_json(_url(f"/user/{value}")))
        if user.get("user_id"):
            resolved = {"user_id": str(user["user_id"]), "display_name": str(user.get("display_name") or value)}
            return {"kind": "user", "user": resolved, "leagues": list_leagues(resolved["user_id"], season, sport)}
        raise SleeperInputError(
            f"{value} is not a Sleeper league ID or user ID. If you meant your username, enter that "
            "instead; if you meant a league, the ID is the long number in your league's URL."
        )

    user = resolve_user(value)
    return {"kind": "user", "user": user, "leagues": list_leagues(user["user_id"], season, sport)}


def list_leagues(user_id: str, season: str, sport: str = "nfl") -> list[dict]:
    """Every league this Sleeper user is in for a season — the league PICKER's data.

    Returned deliberately thin (id/name/size/status/shape): it is a list to choose from, and pulling
    each league's full settings here would multiply the request count by the user's league count for
    data the picker never shows.
    """
    if not _ID_RE.match(user_id or ""):
        raise SleeperInputError("Invalid Sleeper user id.")
    if not _SEASON_RE.match(str(season)):
        raise SleeperInputError("Invalid season.")
    if sport != "nfl":
        raise SleeperInputError("Only NFL leagues can be imported today.")
    leagues = _as_list(get_json(_url(f"/user/{user_id}/leagues/{sport}/{season}")))
    out = []
    for raw in leagues:
        league = _as_dict(raw)
        league_id = str(league.get("league_id") or "")
        if not league_id:
            continue
        out.append(
            {
                "league_id": league_id,
                "name": str(league.get("name") or "Sleeper league"),
                "season": str(league.get("season") or season),
                "total_rosters": int(league.get("total_rosters") or 0),
                "status": str(league.get("status") or ""),
                "sport": str(league.get("sport") or sport),
            }
        )
    return out


# ── the import itself ─────────────────────────────────────────────────────────────────────────────


def _translate_scoring(raw: dict) -> tuple[C.ScoringTranslation, list[str]]:
    """Sleeper's flat weight map → canonical `per_stat` + `position_bonuses`, plus any warnings."""
    warnings: list[str] = []

    two_pt_values = {k: float(raw[k]) for k in _TWO_PT_KEYS if _is_number(raw.get(k))}

    # A league expressing the FINE 50-59 / 60+ buckets has stated its 50+ rule at a resolution the
    # coarse key cannot, so the coarse key is redundant — drop it rather than let alphabetical
    # ordering decide which of two contradictory statements lands.
    drop = set(_TWO_PT_KEYS)
    if any(_is_number(raw.get(k)) for k in ("fgm_50_59", "fgm_60p")):
        drop.add("fgm_50p")

    translated = C.apply_scoring_map(
        {k: v for k, v in raw.items() if k not in drop},
        SCORING_KEY_MAP,
        bonus_map=BONUS_KEY_MAP,
    )

    if two_pt_values:
        values = sorted(set(two_pt_values.values()))
        # A single agreed value is an EXACT restatement. When they disagree the largest-magnitude
        # value is kept (deterministic, and never understates the rule) — but the collapse is
        # DISCLOSED rather than resolved silently, because our projection carries one 2-point
        # conversion column and dict order must not be what decides a user's scoring.
        chosen = values[0] if len(values) == 1 else max(values, key=abs)
        translated.per_stat["two_pt"] = chosen
        if len(values) > 1:
            detail = ", ".join(f"{k}={v:g}" for k, v in sorted(two_pt_values.items()))
            warnings.append(
                "Your league pays different amounts for passing, rushing and receiving 2-point "
                f"conversions ({detail}). Our projection has a single 2-point conversion term, so "
                f"the board uses {chosen:g}."
            )

    return translated, warnings


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _translate_roster(league: dict) -> tuple[list[dict], list[str]]:
    """`roster_positions` (+ the IR/taxi spots it omits) → counted `RosterSlot` dicts."""
    warnings: list[str] = []
    sequence: list[tuple[str, tuple[str, ...], bool]] = []
    unknown: set[str] = set()

    for token in _as_list(league.get("roster_positions")):
        token = str(token)
        mapped = ROSTER_SLOT_MAP.get(token)
        if mapped is None:
            unknown.add(token)
            # An unrecognised slot is kept as a BENCH slot under its own name: bench slots create no
            # starter demand, so an unknown token can never inflate replacement level and quietly
            # distort the board. Dropping it would understate the roster instead.
            sequence.append((token, (), True))
            continue
        sequence.append(mapped)

    settings = _as_dict(league.get("settings"))
    # IR + taxi are real roster spots that `roster_positions` omits (verified live).
    for count_key, slot_name in (("reserve_slots", "IR"), ("taxi_slots", "TAXI")):
        count = settings.get(count_key)
        if _is_number(count) and int(count) > 0:
            already = sum(1 for name, _, _ in sequence if name == slot_name)
            for _ in range(max(0, int(count) - already)):
                sequence.append((slot_name, (), True))

    if unknown:
        warnings.append(
            "These roster slots are not ones we rank, so they were saved as bench spots and do not "
            f"affect the board: {', '.join(sorted(unknown))}."
        )
    return C.collapse_slots(sequence), warnings


def _captured_rules(league: dict) -> dict[str, object]:
    """League rules we record for fidelity and DELIBERATELY do not apply to the board.

    Every entry here changes standings, schedule or roster mechanics — none of them changes what a
    player is projected to score, so applying them would be wrong and dropping them would make the
    saved league an inaccurate record of the real one. `LeagueConfig.captured_rules` is the field
    built for exactly this, and nothing in the scorer reads it.
    """
    settings = _as_dict(league.get("settings"))
    out: dict[str, object] = {}
    if settings.get("league_average_match"):
        out["median_scoring"] = True
    if settings.get("best_ball"):
        out["best_ball"] = True
    if _is_number(settings.get("playoff_week_start")):
        out["playoff_weeks"] = int(settings["playoff_week_start"])
    league_type = settings.get("type")
    if _is_number(league_type) and int(league_type) in _LEAGUE_TYPE:
        out["league_type"] = _LEAGUE_TYPE[int(league_type)]
    if _is_number(settings.get("max_keepers")) and int(settings["max_keepers"]) > 0:
        out["max_keepers"] = int(settings["max_keepers"])
    return out


def _player_from_pick_metadata(player_id: str, meta: dict, *, starter: bool = False) -> C.ImportedPlayer:
    name = " ".join(
        part for part in (str(meta.get("first_name") or ""), str(meta.get("last_name") or "")) if part
    ).strip()
    return C.ImportedPlayer(
        player_key=str(player_id),
        name=name or str(player_id),
        position=str(meta.get("position") or "") or None,
        team=str(meta.get("team") or "") or None,
        starter=starter,
    )


def _fetch_teams(league_id: str) -> tuple[tuple[C.ImportedTeam, ...], list[str]]:
    """Rosters + their owners.

    ⚠️ Sleeper's roster payload carries PLAYER IDS ONLY (`["11599","5846",…]`) — no names. Resolving
    them needs the `/players/nfl` dump, which Sleeper documents as ~5 MB and asks callers to fetch at
    most once per day; pulling it inside a request would blow the Lambda's memory and the platform's
    own guidance at once. So roster entries carry the id and an empty name, and the caller is told
    so explicitly — an honest gap beats a fabricated name. The DRAFT payload, by contrast, embeds
    full player metadata per pick, which is why draft state comes back fully named.
    """
    rosters = _as_list(get_json(_url(f"/league/{league_id}/rosters")))
    users = {
        str(_as_dict(u).get("user_id")): _as_dict(u)
        for u in _as_list(get_json(_url(f"/league/{league_id}/users")))
    }

    teams: list[C.ImportedTeam] = []
    for raw in rosters:
        roster = _as_dict(raw)
        owner_id = str(roster.get("owner_id") or "")
        user = users.get(owner_id, {})
        starters = {str(p) for p in _as_list(roster.get("starters")) if p and str(p) != "0"}
        players = tuple(
            C.ImportedPlayer(player_key=str(pid), name="", starter=str(pid) in starters)
            for pid in _as_list(roster.get("players"))
            if pid and str(pid) != "0"
        )
        display = str(user.get("display_name") or "")
        team_name = str(_as_dict(user.get("metadata")).get("team_name") or "") or display or "Team"
        teams.append(
            C.ImportedTeam(
                team_key=str(roster.get("roster_id") or ""),
                name=team_name,
                owner=display or None,
                players=players,
            )
        )
    note = (
        [
            "Sleeper's roster endpoint returns player IDs without names. Resolving them needs "
            "Sleeper's ~5 MB player file, which they ask callers to download at most once a day, so "
            "roster spots are shown by ID. Draft picks below DO carry full names."
        ]
        if any(t.players for t in teams)
        else []
    )
    return tuple(teams), note


def fetch_draft_state(league_id: str) -> C.DraftState:
    """The league's most recent draft + its picks — fetched LIVE, never persisted (see DraftState)."""
    if not _ID_RE.match(league_id or ""):
        raise SleeperInputError("Invalid Sleeper league id.")
    drafts = _as_list(get_json(_url(f"/league/{league_id}/drafts")))
    if not drafts:
        return C.DraftState(supported=True, note="This league has no draft yet.")

    # `/drafts` returns newest-first in practice; sort defensively on start_time so a re-ordered
    # response can never make us show last season's draft as the live one.
    draft = _as_dict(
        sorted(
            (_as_dict(d) for d in drafts),
            key=lambda d: int(d.get("start_time") or 0),
            reverse=True,
        )[0]
    )
    draft_id = str(draft.get("draft_id") or "")
    settings = _as_dict(draft.get("settings"))

    picks: list[C.DraftPick] = []
    if draft_id:
        for raw in _as_list(get_json(_url(f"/draft/{draft_id}/picks"))):
            pick = _as_dict(raw)
            player_id = str(pick.get("player_id") or "")
            picks.append(
                C.DraftPick(
                    pick_no=int(pick.get("pick_no") or 0),
                    round=int(pick.get("round") or 0),
                    team_key=str(pick.get("roster_id") or "") or None,
                    player=(
                        _player_from_pick_metadata(player_id, _as_dict(pick.get("metadata")))
                        if player_id
                        else None
                    ),
                )
            )
    picks.sort(key=lambda p: p.pick_no)

    start_time = draft.get("start_time")
    return C.DraftState(
        status=str(draft.get("status") or "") or None,
        type=str(draft.get("type") or "") or None,
        rounds=int(settings["rounds"]) if _is_number(settings.get("rounds")) else None,
        # Sleeper stamps epoch MILLISECONDS; passing it through raw would render as year 57000.
        start_time=_epoch_ms_to_iso(start_time),
        picks=tuple(picks),
    )


def _epoch_ms_to_iso(value: object) -> str | None:
    if not _is_number(value) or int(value) <= 0:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(int(value) / 1000.0, tz=timezone.utc).isoformat()


def import_league(league_id: str, *, include_draft: bool = True) -> C.ImportedLeague:
    """Pull one Sleeper league into the shared `LeagueConfig` + its live roster/draft state."""
    if not _ID_RE.match((league_id or "").strip()):
        raise SleeperInputError("That does not look like a Sleeper league ID.")
    league_id = league_id.strip()

    league = _as_dict(get_json(_url(f"/league/{league_id}")))
    if not league:
        raise PlatformHTTPError("Sleeper has no league with that ID.", status=404)
    if str(league.get("sport") or "nfl") != "nfl":
        raise SleeperInputError("Only NFL leagues can be imported today.")

    scoring, warnings = _translate_scoring(_as_dict(league.get("scoring_settings")))
    roster, roster_warnings = _translate_roster(league)
    warnings.extend(roster_warnings)

    settings = _as_dict(league.get("settings"))
    n_teams = int(league.get("total_rosters") or settings.get("num_teams") or 0)

    config = C.build_config(
        name=str(league.get("name") or "Sleeper league"),
        n_teams=n_teams,
        per_stat=scoring.per_stat,
        roster=roster,
        position_bonuses=scoring.position_bonuses,
        captured_rules=_captured_rules(league),
        description=f"Imported from Sleeper ({league.get('season') or ''}).".replace(" )", ")"),
    )
    if not C.config_is_rankable(config):
        raise SleeperInputError(
            "This league has no starting lineup slots we can rank against, so a draft board cannot "
            "be built from it. You can still enter it by hand under League settings."
        )

    teams, team_notes = _fetch_teams(league_id)
    warnings.extend(team_notes)

    return C.ImportedLeague(
        platform=PLATFORM,
        source_league_id=league_id,
        season=str(league.get("season") or "") or None,
        config=config,
        teams=teams,
        draft=fetch_draft_state(league_id) if include_draft else None,
        warnings=tuple(warnings),
        unmapped_scoring_keys=tuple(sorted(scoring.unmapped)),
    )


__all__ = [
    "BONUS_KEY_MAP",
    "PLATFORM",
    "ROSTER_SLOT_MAP",
    "SCORING_KEY_MAP",
    "SleeperInputError",
    "fetch_draft_state",
    "import_league",
    "list_leagues",
    "resolve_target",
    "resolve_user",
]
