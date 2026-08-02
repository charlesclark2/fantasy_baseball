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
from .canonical import ImportedLeague, ImportedPlayer, ImportedTeam, ScoringTranslation

# The read host. Present ONLY so the UI can build a copy-link for the user to open themselves —
# nothing in this module fetches it. ESPN has moved this host once already
# (`fantasy.espn.com` → `lm-api-reads.fantasy.espn.com`) with no notice.
#
# ESPN takes REPEATED `view=` params, so one link still means one paste for the user. `mSettings`
# carries scoring + roster shape; `mTeam` the team list; `mRoster` the players on them.
READ_VIEWS: tuple[str, ...] = ("mSettings", "mTeam", "mRoster")

READ_URL_TEMPLATE = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
    "/segments/0/leagues/{league_id}?{views}"
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
    # ⚠️ NARROWED TO THE COOKIE-ASSIGNMENT FORM (`SWID=`), deliberately — a bare `\bSWID\b` would
    # be a FALSE-REFUSAL LANDMINE now that we request `mTeam`, whose `members[].id` is a SWID GUID:
    # if ESPN ever labels that field with the literal word, every honest import would be rejected
    # with a message accusing the user of pasting credentials. The asymmetry decides it — narrowing
    # costs nothing, because a pasted cookie header is caught three times over (`espn_s2`, the
    # `Cookie:` header patterns, and this), while over-matching breaks the feature for everyone.
    # A bare SWID GUID is an identifier, not a credential: it cannot authenticate without `espn_s2`.
    ("your ESPN sign-in cookie", re.compile(r"\bSWID\s*=", re.IGNORECASE)),
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
                f"That paste includes {label} — we don't want it and won't accept it. Copy just "
                'the JSON response body (the text starting with "{" that the page displays), not '
                "the request or its headers."
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
# 🔬 HOW THESE WERE ESTABLISHED — VERIFIED, NOT TRUSTED. ESPN publishes no stat-id dictionary, so a
# label from memory or a blog post is a guess, and a wrong guess silently MISPRICES a league (far
# worse than an unmapped id, which merely reports CAPTURED and tells the truth). Every id below was
# confirmed against a real `kona_player_info` projection export using an identity a wrong map fails:
#
#   * the nine points-allowed buckets (89/90/91/92/121/122/123/124/125) SUM TO EXACTLY 17.000000
#     games for a team — they partition the season, which fixes both their identity and their ORDER;
#   * the yards-allowed buckets 129..136 likewise sum to 17.000000 — but ⚠️ SEE THE CORRECTION AT
#     `_YARDS_ALLOWED_KEYS`: that sum is 17 only because ESPN projects no sub-100-yard game, so it
#     establishes the ladder's ORDER and not its EXTENT. A second real league scores 128 as well;
#   * stat 126 == points_allowed/17 and stat 137 == yards_allowed/17 to full precision;
#   * 80 + 77 + 74 == 83 (the sub-40, 40-49 and 50+ field goals partition total FGM);
#   * receiving_yards / stat-53 == stat-60 (yards per reception) ⇒ **53 is receptions**, despite
#     being commonly labelled "receptions_alternate"; ESPN reports no stat 41 at all;
#   * stat-1 + stat-2 == stat-0 (completions + incompletions = attempts).
#
# ⛔ Extend this map ONLY with an id that passes a comparable identity or is confirmed against the
# human-readable ESPN settings page. "It looked right in a table" is how a league gets mispriced.
SCORING_KEY_MAP: dict[str, tuple[str, ...]] = {
    # ── offence ────────────────────────────────────────────────────────────────────────────────
    "3": ("pass_yd",),
    "4": ("pass_td",),
    "20": ("pass_int",),
    "24": ("rush_yd",),
    "25": ("rush_td",),
    "42": ("rec_yd",),
    "43": ("rec_td",),
    "53": ("rec",),                      # receptions — see the yards-per-reception identity above
    "72": ("fum_lost",),
    # ── kicking ────────────────────────────────────────────────────────────────────────────────
    # ESPN's "under 40" is COARSER than our three sub-40 buckets, so it fans out across all three.
    # Writing one weight to each is an EXACT restatement of the league's rule (every sub-40 kick
    # scores the same), the mirror image of the fine→coarse FOLD that `resolve_scoring` flags.
    "80": ("fg_made_0_19", "fg_made_20_29", "fg_made_30_39"),
    "77": ("fg_made_40_49",),
    # ⚠️ 74 is the COARSE 50+ bucket; 198/201 are the FINE 50-59 / 60+ pair — the same coarse/fine
    # duality that cost a silent mapping bug on Sleeper (`fgm_50p` vs `fgm_50_59`/`fgm_60p`). In the
    # projection export 198 is byte-identical to 74 ONLY because ESPN projects no 60-yard makes;
    # that is not evidence they are the same field. `_drop_coarse_when_fine_present` resolves a
    # league that sets both, so dict ordering never decides it.
    "74": ("fg_made_50_59", "fg_made_60p"),
    "198": ("fg_made_50_59",),
    "201": ("fg_made_60p",),
    "85": ("fg_missed",),
    "86": ("pat_made",),
    "88": ("pat_missed",),
    # ── team defence (the "@dst" namespace — see the pointsOverrides note above) ───────────────
    "95@dst": ("def_int",),
    "96@dst": ("def_fumble_rec",),
    "97@dst": ("def_blocked_kick",),
    "98@dst": ("def_safety",),
    "99@dst": ("def_sacks",),
    "106@dst": ("def_forced_fumble",),
    "94@dst": ("def_td",),
    # ── team defence, points allowed ──────────────────────────────────────────────────────────
    # 🚨 ESPN'S TIERS DO **NOT** RESTATE EXACTLY ON OUR NINE BUCKETS, contrary to the comment in
    # `sleeper.py` that calls them "the common refinement of the ESPN and Yahoo schemes". They are
    # the YAHOO refinement: ESPN splits at 18-21 / 22-27 while ours splits at 18-20 / 21-27, so a
    # true common refinement would need **21 as a bucket of its own**. Exactly one point value is
    # therefore misplaced — a game allowing exactly 21 points scores at our 21-27 rate rather than
    # ESPN's 18-21 rate. It is mapped to the nearest exact bucket and DISCLOSED as a warning; see
    # `_PA_BOUNDARY_NOTE`. Silently fanning 121 across both buckets would be worse: it would apply
    # the 18-21 weight to the whole of 22-27.
    "89@dst": ("dst_pa_g_0",),
    "90@dst": ("dst_pa_g_1_6",),
    "91@dst": ("dst_pa_g_7_13",),
    "92@dst": ("dst_pa_g_14_17",),
    "121@dst": ("dst_pa_g_18_20",),
    "122@dst": ("dst_pa_g_21_27",),
    "123@dst": ("dst_pa_g_28_34",),
    "124@dst": ("dst_pa_g_35_45",),
    "125@dst": ("dst_pa_g_46p",),
}

# Several ESPN ids land on ONE canonical key. Collapsing is lossless only when they AGREE, so each
# group is resolved explicitly (and disclosed when it does not) rather than by dict ordering —
# the same discipline `_TWO_PT_KEYS` applies on Sleeper.
_COLLAPSE_GROUPS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    # ESPN prices the 2-point conversion per play type; our catalog has one `two_pt`.
    ("two_pt", ("19", "26", "44"), "two-point conversions"),
    # A player-credited return TD. ⚠️ Kept STRICTLY apart from the D/ST unit's return TD below —
    # mapping both onto one key double-counts a single return (the Sleeper st_td/def_st_td rule).
    ("st_player_td", ("101", "102"), "kick and punt return touchdowns"),
    # The DEF unit's own scores: blocked-kick, interception-return and fumble-return touchdowns.
    ("def_td", ("93@dst", "103@dst", "104@dst"), "defensive touchdowns"),
    ("st_td", ("101@dst", "102@dst"), "special-teams touchdowns by the defence"),
    # A player recovering a fumble for a score; ESPN reports it under two ids.
    ("fumble_rec_td", ("63", "104"), "fumble-recovery touchdowns"),
)

# Every collapse-group member also has to BE in the map, or it collapses to an agreed value and is
# then reported CAPTURED anyway. Deriving those entries from the group table keeps one source of
# truth — listing them twice is exactly how the two drift apart.
for _target, _keys, _ in _COLLAPSE_GROUPS:
    for _key in _keys:
        SCORING_KEY_MAP.setdefault(_key, (_target,))

# Long-touchdown bonuses (15/16 pass, 35/36 rush, 45/46 receiving) are deliberately ABSENT: the
# projection catalog has no 40+/50+ touchdown column, so there is nothing to apply them to. They
# flow through as CAPTURED, which is the honest answer, and NF-C0e is where they would be earned.

# ── CAPTURED-key labels ───────────────────────────────────────────────────────────────────────
#
# A captured rule is only honest if the user can tell WHAT was captured. Sleeper and Yahoo name
# their rules in words; ESPN numbers them, so an unlabelled coverage panel reports "129@dst · 3.00"
# — which discloses nothing. These labels exist purely for display and never affect scoring.
#
# ⚠️ DELIBERATELY NO YARD/DISTANCE THRESHOLDS IN THESE LABELS. The identity evidence above fixes
# the yards-allowed ladder's ORDER (monotone, nine rungs) but NOT its cut points, and a label is a
# claim shown to a user. Naming a boundary I have not verified would be the same "it looked right
# in a table" guess this map's header forbids — one rung over, in the display layer.
_YARDS_ALLOWED_KEYS: tuple[str, ...] = tuple(f"{i}@dst" for i in range(128, 137))

CAPTURED_LABELS: dict[str, str] = {
    # The yards-allowed ladder. Present in league 642070 across nine rungs (+5 down to −7); absent
    # entirely from league 998005 — which is exactly why one payload could not have found it.
    **{key: "Yards allowed tier (D/ST)" for key in _YARDS_ALLOWED_KEYS},
    # Long-touchdown bonuses — no 40+/50+ touchdown column exists to apply them to.
    "15": "Long passing touchdown bonus",
    "16": "Long passing touchdown bonus",
    "35": "Long rushing touchdown bonus",
    "36": "Long rushing touchdown bonus",
    "45": "Long receiving touchdown bonus",
    "46": "Long receiving touchdown bonus",
    # The BASE (non-D/ST) side of two defensive scores. Their `@dst` twins are applied as `def_td`;
    # these carry the value for an INDIVIDUAL defensive player, and we project no IDP positions.
    "93": "Blocked-kick return touchdown by an individual defender",
    "103": "Interception returned for touchdown by an individual defender",
}

_YARDS_ALLOWED_NOTE = (
    "Your league scores your defence on total yards allowed. We don't project yards allowed, so "
    "those tiers are saved with your league but don't affect its D/ST rankings — a defence that "
    "wins by suppressing yardage will be under-rated on your board."
)

_PA_BOUNDARY_NOTE = (
    "ESPN scores a game where your defence allows exactly 21 points in its 18-21 tier; we resolve "
    "points allowed on buckets that split at 20/21, so that one case scores at your 22-27 rate "
    "instead. Every other tier matches your league exactly."
)

# Non-scoring bookkeeping fields that would be noise in the coverage report.
IGNORE_KEYS: frozenset[str] = frozenset()


def _drop_coarse_when_fine_present(flat: dict[str, float]) -> dict[str, float]:
    """ESPN exposes BOTH a coarse 50+ field-goal bucket (74) and the fine 50-59 / 60+ pair
    (198/201). A league that sets a fine key means it; the coarse one would double-write the same
    canonical column, and which won would depend on dict ordering. Prefer the fine keys."""
    if "198" in flat or "201" in flat:
        flat = {k: v for k, v in flat.items() if k != "74"}
    return flat


def _collapse_group(
    flat: dict[str, float], keys: tuple[str, ...], label: str
) -> tuple[dict[str, float], list[str]]:
    """Force one canonical key's ESPN sources to a single value, disclosing any disagreement."""
    present = [k for k in keys if k in flat]
    values = {flat[k] for k in present}
    if len(values) <= 1:
        return flat, []
    # Pick the modal value so the majority rule survives, and say plainly that we flattened it.
    chosen = max(values, key=lambda v: sum(1 for k in present if flat[k] == v))
    flat = dict(flat)
    for k in present:
        flat[k] = chosen
    return flat, [
        f"Your league pays different amounts for {label} "
        f"({', '.join(str(v) for v in sorted(values))}); we apply a single value of {chosen}."
    ]


def translate_scoring(flat: dict[str, float]) -> tuple[ScoringTranslation, list[str]]:
    """Map the flattened ESPN keys onto canonical stats.

    Two lossy edges are handled EXPLICITLY here rather than left to dict ordering, because both
    would otherwise change a user's scoring silently: several ESPN ids collapse onto one canonical
    key (resolved only when they agree), and the points-allowed tiers do not align at 20/21.
    """
    warnings: list[str] = []
    flat = _drop_coarse_when_fine_present(flat)

    for _canonical_key, keys, label in _COLLAPSE_GROUPS:
        flat, notes = _collapse_group(flat, keys, label)
        warnings.extend(notes)

    # Disclose the 18-21 / 22-27 boundary only when the league actually scores those tiers
    # DIFFERENTLY — if both tiers carry the same weight the misplacement is a no-op, and warning
    # about a difference that cannot affect the board would be noise.
    t18, t22 = flat.get("121@dst"), flat.get("122@dst")
    if t18 is not None and t22 is not None and t18 != t22:
        warnings.append(_PA_BOUNDARY_NOTE)

    # Same conditional-disclosure rule for the yards-allowed ladder: say it only when the league
    # actually scores it. A league that leaves those tiers unset loses nothing and should not be
    # handed a caveat about a rule it does not have.
    if any(flat.get(key) for key in _YARDS_ALLOWED_KEYS):
        warnings.append(_YARDS_ALLOWED_NOTE)

    translation = canonical.apply_scoring_map(flat, SCORING_KEY_MAP, ignore=IGNORE_KEYS)
    return translation, warnings


# ---------------------------------------------------------------------------------------------
# Teams and rosters (the `mTeam` + `mRoster` views)
# ---------------------------------------------------------------------------------------------
#
# ⏳ THE PRE-DRAFT CASE IS THE NORMAL CASE, NOT AN EDGE CASE. Most people import BEFORE their draft
# — that is when a draft tool is worth having — and an undrafted ESPN league returns its teams with
# EMPTY rosters. So "no players" must read as an expected state with a next step, never as a failed
# or partial import. Both real fixtures are undrafted (`draftDetail.drafted == false`), so this is
# the path the tests actually exercise.
#
# 🔒 PRIVACY. `mTeam` carries a `members` array whose `id` is the member's SWID GUID. We map it to a
# display name to label the team and then DROP it: a GUID identifies a real ESPN account, and we
# have no use for one. It is not a credential (it cannot authenticate without `espn_s2`), which is
# why the paste is still safe — but "not a credential" is not a reason to keep it.

# A player's own position, derived from `eligibleSlots` against the ALREADY-VERIFIED slot map rather
# than from ESPN's separate `defaultPositionId` table — which is a second numbering I have no
# identity to check. A real position slot admits exactly one position, so the intersection is a
# singleton for an ordinary player; slot 1 (TQB, a whole-team QB slot) is excluded because it is not
# an individual's position.
_POSITION_BY_SLOT: dict[int, str] = {
    slot: eligible[0]
    for slot, (_name, eligible, is_bench) in ROSTER_SLOT_MAP.items()
    if len(eligible) == 1 and not is_bench and slot != 1
}

# ESPN's pro-team ids: 1988-era alphabetical-by-city, with relocations applied and expansion teams
# appended (29 CAR, 30 JAX, 33 BAL, 34 HOU). 0 = free agent.
#
# ⚖️ WHY THIS SHIPS AT A LOWER EVIDENCE BAR THAN `SCORING_KEY_MAP`, deliberately and not by
# oversight: a wrong stat id SILENTLY MISPRICES a league — it changes numbers the user acts on. A
# wrong pro-team abbreviation shows a wrong badge next to a correct player, on a roster we display
# but do not score. The consequences differ by orders of magnitude, so the rigor does too. An id
# that is NOT in this table yields `None` rather than a guess, and `test_pro_team_ids_are_pinned_
# against_a_real_payload` upgrades this to identity-checked the moment a rostered payload exists.
_PRO_TEAM_BY_ID: dict[int, str] = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET",
    9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA", 16: "MIN",
    17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC",
    25: "SF", 26: "SEA", 27: "TB", 28: "WSH", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
}

# Lineup slots that are NOT a started position.
_BENCH_SLOTS = frozenset({20, 21})

_PRE_DRAFT_NOTE = (
    "Your league hasn't drafted yet, so there are no rosters to bring over — we imported your "
    "scoring and roster shape, which is everything the draft tools need. Import again after your "
    "draft and we'll pull the rosters too."
)

_WHOSE_TEAM_NOTE = (
    "ESPN's response doesn't say which of these teams is yours, so we haven't marked one. Your "
    "scoring and roster settings are unaffected."
)


def _player_position(player: dict) -> str | None:
    """A player's real position, from `eligibleSlots` ∩ the verified single-position slots."""
    slots = player.get("eligibleSlots")
    if not isinstance(slots, list):
        return None
    found = sorted(
        {_POSITION_BY_SLOT[s] for s in (_as_int(x, default=-1) for x in slots) if s in _POSITION_BY_SLOT}
    )
    # A multi-eligible player (rare) is reported as the lowest-id primary slot, which is ESPN's own
    # ordering; returning one of several true positions beats returning nothing.
    return found[0] if found else None


def translate_teams(payload: dict) -> tuple[list[ImportedTeam], list[str]]:
    """`teams` (+ `members`) → the shared team/roster shape.

    Absent views are NOT an error: a user with an older single-view link, or a league whose response
    omits `teams`, still gets a complete settings import. Rosters are additive to that.
    """
    raw_teams = payload.get("teams")
    if not isinstance(raw_teams, list) or not raw_teams:
        return [], []

    # member id (a SWID GUID) → display name, used to LABEL a team and then discarded.
    owner_names: dict[str, str] = {}
    for member in payload.get("members") or []:
        if not isinstance(member, dict):
            continue
        member_id = member.get("id")
        display = member.get("displayName") or member.get("firstName")
        if isinstance(member_id, str) and isinstance(display, str) and display.strip():
            owner_names[member_id] = display.strip()

    teams: list[ImportedTeam] = []
    for raw in raw_teams:
        if not isinstance(raw, dict):
            continue
        # ESPN moved the team name from `location` + `nickname` to a single `name`; accept either
        # so an older season's payload still reads.
        name = str(raw.get("name") or "").strip()
        if not name:
            name = " ".join(
                str(raw.get(k) or "").strip() for k in ("location", "nickname")
            ).strip()
        team_key = str(raw.get("id") if raw.get("id") is not None else len(teams))

        owner = None
        for owner_id in raw.get("owners") or []:
            if isinstance(owner_id, str) and owner_id in owner_names:
                owner = owner_names[owner_id]
                break

        players: list[ImportedPlayer] = []
        entries = (raw.get("roster") or {}).get("entries") if isinstance(raw.get("roster"), dict) else None
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            pool = entry.get("playerPoolEntry")
            player = pool.get("player") if isinstance(pool, dict) else None
            if not isinstance(player, dict):
                continue
            full_name = str(player.get("fullName") or "").strip()
            if not full_name:
                continue
            slot = _as_int(entry.get("lineupSlotId"), default=-1)
            players.append(
                ImportedPlayer(
                    player_key=str(player.get("id") if player.get("id") is not None else ""),
                    name=full_name,
                    position=_player_position(player),
                    team=_PRO_TEAM_BY_ID.get(_as_int(player.get("proTeamId"), default=-1)),
                    starter=slot >= 0 and slot not in _BENCH_SLOTS,
                )
            )

        teams.append(
            ImportedTeam(
                team_key=team_key,
                name=name or f"Team {team_key}",
                owner=owner,
                # ESPN's response never identifies the requesting account, and we deliberately do
                # not ask for the credential that would. Nobody is marked rather than guessing.
                is_owner=False,
                players=tuple(players),
            )
        )

    warnings: list[str] = []
    if teams and not any(t.players for t in teams):
        warnings.append(_PRE_DRAFT_NOTE)
    elif teams:
        warnings.append(_WHOSE_TEAM_NOTE)
    return teams, warnings


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

    teams, team_warnings = translate_teams(payload)
    warnings.extend(team_warnings)

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
        teams=tuple(teams),
        warnings=tuple(warnings),
        unmapped_scoring_keys=tuple(translation.unmapped),
        # Labels only for what was ACTUALLY captured, so the panel never explains a rule this
        # league does not have.
        unmapped_labels={
            key: CAPTURED_LABELS[key] for key in translation.unmapped if key in CAPTURED_LABELS
        },
    )


def build_read_url(league_id: str, season: int) -> str:
    """The link the UI shows the user to open THEMSELVES. Nothing here fetches it."""
    league_id = str(league_id).strip()
    if not _LEAGUE_ID_RE.match(league_id):
        raise EspnInputError(
            "That doesn't look like an ESPN league ID. It's the number in your league's URL, after "
            '"leagueId=".'
        )
    views = "&".join(f"view={v}" for v in READ_VIEWS)
    return READ_URL_TEMPLATE.format(season=int(season), league_id=league_id, views=views)


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
