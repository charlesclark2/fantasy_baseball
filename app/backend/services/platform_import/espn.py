"""ESPN league import via USER-MEDIATED PASTE.

⚠️ READ FIRST: this adapter makes **no network request to ESPN, ever**. There is no client here on
purpose. The user opens the read URL in their OWN signed-in browser, copies the JSON response body,
and pastes it in; we parse what they hand us.

WHY THAT IS NOT THE THING NF-C0 REFUSED (docs/nf_c0_espn_access_probe.md §3(c) vs §3(d)):
`espn_s2` is an HTTP **cookie**. The browser attaches it to the request and it is **never echoed
into the response body**, so a paste of the body is *structurally incapable* of carrying the session
credential — not "unlikely to", incapable. Verified against a real payload: `espn_s2`, `SWID`,
`Cookie`, `Authorization`, `members` and `email` are all absent from `?view=mSettings`. We end up
holding data, not a key: nothing is re-fetchable, we cannot act on the league, and access ends when
the user closes the tab.

⛔ NEVER add a "paste your cookie instead" path for users who find the copy awkward. That is §3(c)
wearing a different hat, and the convenience gap is exactly the pressure that would produce it. If
the paste is too hard, fix the UX.
"""

from __future__ import annotations

import json
import re

from . import canonical
from .canonical import ImportedLeague, ScoringTranslation

# The read host. Present ONLY so the UI can build a copy-link for the user to open themselves —
# nothing in this module fetches it. ESPN has moved this host once already
# (`fantasy.espn.com` → `lm-api-reads.fantasy.espn.com`) with no notice.
READ_URL_TEMPLATE = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
    "/segments/0/leagues/{league_id}?view=mSettings"
)

# SSRF/format guard on the user-supplied id, mirroring `sleeper._ID_RE`. The id only ever reaches a
# URL we render for the USER to click, but an unvalidated id in a rendered link is still an
# injection surface.
_LEAGUE_ID_RE = re.compile(r"^[0-9]{1,24}$")

MAX_PASTE_BYTES = 4_000_000  # under the Lambda synchronous request ceiling (~6 MB), with headroom.


class EspnInputError(ValueError):
    """The pasted text is not usable. Message is shown to the user verbatim."""


class EspnCredentialPasteError(EspnInputError):
    """The paste contains credential material. Distinct type so the route can refuse LOUDLY and so
    the caller can be sure it never logs the offending body."""


# ---------------------------------------------------------------------------------------------
# The runtime credential scrubber — the guard that keeps §3(d) from decaying into §3(c).
# ---------------------------------------------------------------------------------------------

# The RESPONSE BODY cannot contain these. The user, however, can paste the wrong artifact — DevTools'
# "Copy as cURL" embeds the entire `Cookie:` header, and a Network-tab "Copy request headers" carries
# `Authorization`. Those are the realistic accidents, and we refuse them rather than parse around
# them. Matching is case-insensitive because header casing is not normalised in any of those copies.
_CREDENTIAL_SIGNATURES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("your ESPN sign-in cookie", re.compile(r"espn_s2", re.IGNORECASE)),
    ("your ESPN account identifier", re.compile(r"\bSWID\b", re.IGNORECASE)),
    ("a Cookie header", re.compile(r"^\s*-?-?\s*cookie\s*:", re.IGNORECASE | re.MULTILINE)),
    ("a Cookie header", re.compile(r"-H\s+['\"]?cookie\s*:", re.IGNORECASE)),
    ("an Authorization header", re.compile(r"authorization\s*:", re.IGNORECASE)),
    ("a set-cookie header", re.compile(r"set-cookie\s*:", re.IGNORECASE)),
)


def assert_no_credentials(text: str) -> None:
    """Raise if the paste carries credential material.

    ⚠️ The raised message names WHICH signature matched but NEVER echoes the surrounding text —
    an error string is a log line waiting to happen, and the whole point is that this value never
    reaches a log. Callers must not log the input either.
    """
    for label, pattern in _CREDENTIAL_SIGNATURES:
        if pattern.search(text):
            raise EspnCredentialPasteError(
                f"That paste includes {label}, which is part of your ESPN sign-in — we don't want "
                "it and won't accept it. Copy just the JSON response body (the text starting with "
                '"{" that the page displays), not the request or its headers.'
            )


# ---------------------------------------------------------------------------------------------
# Roster slots
# ---------------------------------------------------------------------------------------------

# ESPN lineup-slot id → (our slot name, eligible positions, is_bench).
# ⭐ SUPERFLEX IS SLOT 7 ("OP"/offensive player) AND IS DETECTED BY ELIGIBILITY, NEVER BY NAME —
# the `canonical.detect_superflex` rule. A league that renames its flex does not fool this.
ROSTER_SLOT_MAP: dict[int, tuple[str, tuple[str, ...], bool]] = {
    0: ("QB", ("QB",), False),
    1: ("TQB", ("QB",), False),
    2: ("RB", ("RB",), False),
    3: ("RB/WR", ("RB", "WR"), False),
    4: ("WR", ("WR",), False),
    5: ("WR/TE", ("WR", "TE"), False),
    6: ("TE", ("TE",), False),
    7: ("SUPERFLEX", ("QB", "RB", "WR", "TE"), False),
    8: ("DT", ("DT",), False),
    9: ("DE", ("DE",), False),
    10: ("LB", ("LB",), False),
    11: ("DL", ("DL",), False),
    12: ("CB", ("CB",), False),
    13: ("S", ("S",), False),
    14: ("DB", ("DB",), False),
    15: ("DP", ("DP",), False),
    16: ("DST", ("DST",), False),
    17: ("K", ("K",), False),
    18: ("P", ("P",), False),
    19: ("HC", ("HC",), False),
    20: ("BN", (), True),
    21: ("IR", (), True),
    23: ("FLEX", ("RB", "WR", "TE"), False),
}

DST_SLOT_ID = "16"


def translate_roster(roster_settings: dict) -> tuple[list[dict], list[str]]:
    """`lineupSlotCounts` → counted `RosterSlot` dicts."""
    warnings: list[str] = []
    sequence: list[tuple[str, tuple[str, ...], bool]] = []
    unknown: list[str] = []

    counts = roster_settings.get("lineupSlotCounts")
    if not isinstance(counts, dict):
        raise EspnInputError(
            "That league's settings don't include a lineup, so we can't tell what its starting "
            "roster looks like. Make sure you copied the whole response."
        )

    for raw_slot, raw_count in sorted(counts.items(), key=lambda kv: _as_int(kv[0], default=10**6)):
        count = _as_int(raw_count, default=0)
        if count <= 0:
            continue
        slot_id = _as_int(raw_slot, default=-1)
        mapped = ROSTER_SLOT_MAP.get(slot_id)
        if mapped is None:
            # Unknown slot → BENCH, never a starter. Bench slots create no starter demand, so an
            # unrecognised id cannot inflate replacement level and distort the board; dropping it
            # would understate the roster instead. Same rule as the Sleeper adapter.
            unknown.append(str(raw_slot))
            for _ in range(count):
                sequence.append((f"SLOT_{raw_slot}", (), True))
            continue
        for _ in range(count):
            sequence.append(mapped)

    if unknown:
        warnings.append(
            "These roster slots aren't ones we rank, so they were saved as bench spots and do not "
            f"affect the board: {', '.join(sorted(set(unknown)))}."
        )
    if not sequence:
        raise EspnInputError("That league has no roster slots set, so there is nothing to import.")
    return canonical.collapse_slots(sequence), warnings


# ---------------------------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------------------------

# 🚨 THE POSITION-OVERRIDE TRAP — the single most important thing in this module.
#
# ESPN encodes position-conditional scoring as `pointsOverrides`, keyed by LINEUP SLOT ID. On a real
# 12-team league, 19 of 43 scoring rules carried an override and **16 of those had a base `points`
# of exactly 0.0**, with their real value living only in `pointsOverrides["16"]` (slot 16 = D/ST).
#
# A parser that reads `points` and ignores `pointsOverrides` therefore scores the ENTIRE team-defense
# sheet as ZERO — every points-allowed tier, every yards-allowed tier, sacks, interceptions, safeties.
# And it fails in the worst possible way: those rules would be reported APPLIED with weight 0.0, which
# is indistinguishable from working. That is precisely the silent-zero failure the whole
# APPLIED/DERIVED/CAPTURED apparatus exists to prevent, so it must be handled HERE, at the read.
#
# We therefore flatten each rule into up to two namespaced keys:
#   "<statId>"      — the base value, i.e. what a normal offensive player scores
#   "<statId>@dst"  — the D/ST value, when an override for slot 16 is present
# so the two can map to DIFFERENT canonical stats. That matters even when both are non-zero: statIds
# 101/102 score 6.0 for a player and 0.0 for a D/ST, which is the same player-vs-unit distinction the
# Sleeper adapter draws between `st_td` and `def_st_td`.


def flatten_scoring_items(items: object) -> tuple[dict[str, float], list[str]]:
    """`scoringItems` → a flat `{key: weight}` dict, resolving `pointsOverrides`."""
    if not isinstance(items, list):
        raise EspnInputError(
            "That league's settings don't include any scoring rules. Make sure you copied the whole "
            "response, including the part starting with \"scoringSettings\"."
        )

    flat: dict[str, float] = {}
    notes: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        stat_id = item.get("statId")
        if stat_id is None:
            continue
        key = str(_as_int(stat_id, default=-1))
        base = _as_float(item.get("points"), default=0.0)
        overrides = item.get("pointsOverrides")
        dst_value = None
        if isinstance(overrides, dict) and DST_SLOT_ID in overrides:
            dst_value = _as_float(overrides[DST_SLOT_ID], default=0.0)

        # A rule with NO override applies at its base value everywhere.
        if dst_value is None:
            if base:
                flat[key] = base
            continue

        # With an override present, base and D/ST are genuinely different rules.
        if base:
            flat[key] = base
        if dst_value:
            flat[f"{key}@dst"] = dst_value

        if isinstance(overrides, dict):
            extra = sorted(k for k in overrides if k != DST_SLOT_ID)
            if extra:
                # Per-slot overrides for something other than D/ST are rare and we do not model
                # them. Say so rather than silently applying the base value to that position.
                notes.append(
                    f"Rule {key} scores differently for some positions in a way we don't model "
                    "yet; we used its standard value."
                )
    if not flat:
        raise EspnInputError("That league's scoring rules are all zero, so there is nothing to import.")
    return flat, notes


# ESPN statId → canonical key(s).
#
# ⚠️ DELIBERATELY PARTIAL, AND THAT IS SAFE. ESPN publishes no stat-id dictionary, so this map covers
# only ids confirmed against a real payload whose values are self-identifying (0.04/pt passing yard,
# 6/rushing TD, 1/reception on a league whose own `playerRankType` reads "PPR", …). Every id NOT here
# flows through `apply_scoring_map` under its original key and is reported **CAPTURED** — stored
# faithfully, visibly not applied. Guessing an id would be far worse: a wrong guess silently
# MISPRICES a league, whereas an unmapped id merely tells the truth about what we don't know.
#
# ⛔ Do not extend this map from memory or from a blog post. Extend it only against a real payload
# whose human-readable ESPN settings page confirms the label (the NF-C0 "second real payload" rule).
SCORING_KEY_MAP: dict[str, tuple[str, ...]] = {
    "3": ("pass_yd",),
    "4": ("pass_td",),
    "19": ("two_pt",),        # 2-pt passing conversion
    "20": ("pass_int",),
    "24": ("rush_yd",),
    "25": ("rush_td",),
    "26": ("two_pt",),        # 2-pt rush
    "42": ("rec_yd",),
    "43": ("rec_td",),
    "44": ("two_pt",),        # 2-pt reception
    "53": ("rec",),
    "63": ("fum_rec_td",),
    "72": ("fum_lost",),
    "86": ("xp_made",),
}

# Non-scoring bookkeeping fields that would be noise in the coverage report.
IGNORE_KEYS: frozenset[str] = frozenset()


def translate_scoring(flat: dict[str, float]) -> tuple[ScoringTranslation, list[str]]:
    """Map the flattened ESPN keys onto canonical stats, collapsing the three 2-point rules."""
    warnings: list[str] = []

    # ESPN prices 2-pt conversions separately by play type (19/26/44); our canonical schema has ONE
    # `two_pt`. Collapse only when they agree, and DISCLOSE when they don't rather than silently
    # picking one — the same rule the Sleeper adapter applies to pass_2pt/rush_2pt/rec_2pt.
    two_pt_keys = [k for k in ("19", "26", "44") if k in flat]
    values = {flat[k] for k in two_pt_keys}
    if len(values) > 1:
        chosen = max(values, key=lambda v: sum(1 for k in two_pt_keys if flat[k] == v))
        warnings.append(
            "Your league pays different amounts for passing, rushing and receiving two-point "
            f"conversions ({', '.join(str(flat[k]) for k in two_pt_keys)}); we apply a single value "
            f"of {chosen} to all of them."
        )
        flat = dict(flat)
        for k in two_pt_keys:
            flat[k] = chosen

    translation = canonical.apply_scoring_map(flat, SCORING_KEY_MAP, ignore=IGNORE_KEYS)
    return translation, warnings


# ---------------------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------------------


def parse_settings_payload(pasted: str, *, season: int | None = None) -> ImportedLeague:
    """Parse a pasted `?view=mSettings` response into the shared `LeagueConfig` shape.

    `pasted` is user input and is treated as such: credential-scrubbed first, size-capped, and never
    logged by this module.
    """
    if not isinstance(pasted, str) or not pasted.strip():
        raise EspnInputError("Paste the JSON from your ESPN league settings link to import it.")
    if len(pasted.encode("utf-8", "ignore")) > MAX_PASTE_BYTES:
        raise EspnInputError(
            "That paste is too large to import. Use the link we generated, which asks ESPN only for "
            "your league's settings."
        )

    assert_no_credentials(pasted)  # BEFORE any parsing, so a cURL paste never reaches the parser.

    try:
        payload = json.loads(pasted)
    except ValueError:
        raise EspnInputError(
            "That doesn't look like the JSON from ESPN. Open the link we generated, select all of "
            'the text on that page (it starts with "{"), and paste it here.'
        ) from None
    if not isinstance(payload, dict):
        raise EspnInputError("That JSON isn't an ESPN league response.")

    # ESPN answers an unauthorised read with a 401 body rather than settings. Recognise it and say
    # what to do, instead of failing as "missing settings".
    if "settings" not in payload and payload.get("messages"):
        raise EspnInputError(
            "ESPN answered that link with \"not authorized to view this League\". Open the link "
            "while signed in to the ESPN account that's in the league, then copy what it shows."
        )

    settings = payload.get("settings")
    if not isinstance(settings, dict):
        raise EspnInputError(
            "That JSON doesn't contain league settings. Make sure the link ends with "
            '"?view=mSettings" and that you copied the whole page.'
        )

    warnings: list[str] = []
    roster, roster_warnings = translate_roster(_as_dict(settings.get("rosterSettings")))
    warnings.extend(roster_warnings)

    scoring_settings = _as_dict(settings.get("scoringSettings"))
    flat, flatten_notes = flatten_scoring_items(scoring_settings.get("scoringItems"))
    warnings.extend(flatten_notes)
    translation, scoring_warnings = translate_scoring(flat)
    warnings.extend(scoring_warnings)

    name = str(settings.get("name") or "Imported ESPN league").strip() or "Imported ESPN league"
    n_teams = _as_int(settings.get("size"), default=0) or _as_int(payload.get("teamsJoined"), default=0)
    if n_teams <= 0:
        raise EspnInputError("That league doesn't report how many teams it has, so we can't rank it.")

    # Rules we store for fidelity but deliberately never apply — same contract as the other
    # adapters: recorded so nothing is lost, and reported CAPTURED so nothing is overclaimed.
    captured: dict[str, object] = {}
    for key, source in (
        ("scoring_type", scoring_settings.get("scoringType")),
        ("player_rank_type", scoring_settings.get("playerRankType")),
        ("playoff_team_count", _as_dict(settings.get("scheduleSettings")).get("playoffTeamCount")),
        ("matchup_period_count", _as_dict(settings.get("scheduleSettings")).get("matchupPeriodCount")),
        ("keeper_count", _as_dict(settings.get("draftSettings")).get("keeperCount")),
        ("draft_type", _as_dict(settings.get("draftSettings")).get("type")),
    ):
        if source not in (None, ""):
            captured[key] = source

    config = canonical.build_config(
        name=name,
        n_teams=n_teams,
        per_stat=translation.per_stat,
        roster=roster,
        position_bonuses=translation.position_bonuses,
        captured_rules=captured,
        description=f"Imported from ESPN — {name}",
    )

    league_id = payload.get("id")
    resolved_season = season or _as_int(payload.get("seasonId"), default=0)
    return ImportedLeague(
        platform="espn",
        source_league_id=str(league_id) if league_id is not None else "",
        season=str(resolved_season) if resolved_season else None,
        config=config,
        warnings=tuple(warnings),
        unmapped_scoring_keys=tuple(translation.unmapped),
    )


def build_read_url(league_id: str, season: int) -> str:
    """The link the UI shows the user to open THEMSELVES. Nothing here fetches it."""
    league_id = str(league_id).strip()
    if not _LEAGUE_ID_RE.match(league_id):
        raise EspnInputError(
            "That doesn't look like an ESPN league ID. It's the number in your league's URL, after "
            '"leagueId=".'
        )
    return READ_URL_TEMPLATE.format(season=int(season), league_id=league_id)


# ---------------------------------------------------------------------------------------------


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _as_int(value: object, *, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_float(value: object, *, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
