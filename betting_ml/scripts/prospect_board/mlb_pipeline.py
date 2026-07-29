"""mlb_pipeline.py — MLB Edge-E7.11: parse MLB Pipeline prospect rankings (pure, no IO).

MLB Pipeline is the free SECOND scouting source (`research_milb_projection_2026-07-29.md` Thread 2):
a Top 100 plus all 30 organizational Top 30s, ~900 ranked players, published by MLB.com at no cost
and behind no paywall. This module turns one fetched ranking page into typed rows; the network and
S3 layers live in `scripts/ingest_mlb_pipeline_to_s3.py` so every rule below is fast-gate testable.

⭐ THE REASON THIS SOURCE IS WORTH INGESTING AT ALL: **it publishes the MLBAM id directly.**
Each ranked entry references `Person:<id>`, and that `<id>` IS the MLBAM `person.id` — the same
spine `dim_player_xref` is keyed on (E7.4). So Pipeline joins to our board with **zero name
matching**, which is exactly the leg E7.4 refused to build (a name-equality match against the MiLB
logs produced a FALSE POSITIVE; no match beats a wrong match). A second scouting opinion that
arrives pre-keyed to our spine is a rare thing — that is what makes a consensus feasible here.

🚦 ACCESS DISCIPLINE (the story's hard constraint — probe-first, robots honored, no credentials)
------------------------------------------------------------------------------------------------
Verified live 2026-07-29:
  • `https://www.mlb.com/robots.txt` disallows `/api/`, `/mlb/`, `/web/`, `/search`, … — it does
    **NOT** disallow `/prospects/`. The ranking pages are `https://www.mlb.com/prospects/<season>/
    <list>/`, an ALLOWED path, fetched as an ordinary page read.
  • `https://data-graph.mlb.com/robots.txt` is `User-agent: * / Disallow: /`. That host is the
    GraphQL API the page's client-side code calls, and it is therefore **OFF LIMITS** — we never
    call it. ⚠️ This is the whole reason this module parses HTML instead of calling a clean JSON
    API: the clean API is robots-blocked and the page is not. Do NOT "simplify" this into a
    data-graph request.
  • Prospects Live (the story's candidate free third source) publishes
    `User-agent: ClaudeBot / Disallow: /` plus a `Content-Signal: ai-train=no` reservation, and its
    ranking routes 404 for an anonymous reader (the lists live in Ghost posts, partly Patreon).
    ⇒ **NOT ingested.** It is routed through the MANUAL second-opinion path like the paywalled
    sources, where a human may hand-key it. Same for Baseball America / Keith Law / ESPN / BP.

🧬 WHERE THE DATA ACTUALLY IS (non-obvious — preserve it)
--------------------------------------------------------
The page ships a server-rendered Apollo cache in its HTML. Two pieces matter:

    getPlayerRankingsFromSelection({"limit":100,"slug":"sel-pr-2026-top100"})
        → [ {rank: 1, playerEntity: {player: {__ref: "Person:815908"}, position, eta, …}}, … ]
    "Person:815908": { id, useName, useLastName, birthDate, currentAge, activeRoster: {__ref:
                       "Team:5015"}, primaryPosition, … }
    "Team:5015":     { id, name, parentOrgId, parentOrgName }

so rank → MLBAM id → name/bio/org resolves entirely inside one document. The whole blob is
HTML-entity-escaped inside an attribute, so it must be unescaped before it will parse as JSON.

⚠️ The rank list is embedded but the SELECTION KEY is not stable across page types (`limit` is 100
for the Top 100 and 30 for an org list), so it is matched by regex on the slug, never by a
hardcoded key string.

🕰️ HISTORICAL SEASONS ARE AVAILABLE — AND CARRY TWO LEAKAGE TRAPS (verified live 2026-07-29)
--------------------------------------------------------------------------------------------
`/prospects/<year>/<list>/` serves archived rankings back to **2010**; 2008 and earlier return an
empty selection. ⚠️ **LIST DEPTH CHANGED OVER TIME AND A STUDY MUST NORMALIZE FOR IT** — the overall
list was Top **50** in 2010–2011 and Top 100 from 2012; the ORG lists were Top **10** in 2011, Top
**20** in 2012–2014, and Top 30 only from 2015 (`OVERALL_LIST_DEPTH_BY_ERA` /
`ORG_LIST_DEPTH_BY_ERA`). So "absent from the 2013 org list" means *outside that club's top 20*, a
materially weaker statement than the same absence in 2023. The RANKS are genuinely
point-in-time — the 2015 list opens Buxton / Bryant / Correa, the 2019 list Guerrero / Tatís, the
2023 list Henderson / Carroll, all matching what MLB Pipeline actually published those years. That
makes ~17 seasons of MLBAM-keyed rankings available for an accuracy study.

**But the page's `Person` and `Team` entities are LIVE records, not archived ones**, and its bio
list includes reports written AFTER the season. Both were measured, not assumed:

  1. **Current-state contamination.** On the 2015 page Byron Buxton returns `currentAge` 32 (he was
     21) and Kris Bryant returns COL (he was a Cub). Every such field is therefore suffixed
     **`_current`** — `org_current`, `age_current`, `affiliate_team_current` — so using one as an
     as-of feature is visible at the call site. `org` (unsuffixed) is populated ONLY from the URL
     of an org list, which genuinely is as-of that season.
  2. **Future bios.** The 2015 page carries 2016/2017/2018 scouting reports for 65 of its 100
     players. `_select_bio` therefore takes the report titled `season`, else the newest **not
     after** it — never a later one — and stamps `bio_season` so a consumer can verify.

🎓 TOOL GRADES ARE PROSE, NOT FIELDS. `gradesHitting` / `gradesPitching` come back NULL on every
row (verified on the live 2026 Top 100). The 20-80 grades are published inside the scouting-report
HTML as `Scouting grades: Hit: 50 | Power: 55 | ... | Overall: 55`. They are parsed best-effort and
namespaced `pipeline_grade_*` — a prose parse is a weaker contract than a field, so a miss is a
None, never a zero (a 0 grade reads as *scouted and terrible*, the E8.0 Prospect-Savant landmine).
"""
from __future__ import annotations

import html as _html
import json
import re
from typing import Any

__all__ = [
    "MAX_BIO_YEAR",
    "MIN_BIO_YEAR",
    "ORG_LIST_DEPTH_BY_ERA",
    "ORG_NAME_TO_ABBREV",
    "ORG_SLUG_TO_ABBREV",
    "PIPELINE_SOURCE",
    "PipelineParseError",
    "OVERALL_LIST_DEPTH_BY_ERA",
    "TOP100_LIST",
    "extract_scouting_grades",
    "list_slug",
    "parse_rankings_page",
    "robots_disallows",
    "selection_slug",
]

PIPELINE_SOURCE = "mlb_pipeline"
TOP100_LIST = "top100"

# A `contentTitle` outside this range is not a season, whatever `.isdigit()` says (see `_select_bio`).
MIN_BIO_YEAR = 1980
MAX_BIO_YEAR = 2100

# 📏 HOW DEEP EACH LIST IS PUBLISHED, BY ERA — measured over the full 2010–2026 backfill.
#
# 🚨 A STUDY CANNOT COMPARE RANKS ACROSS THESE ERAS WITHOUT NORMALIZING. MLB Pipeline's org lists
# were **Top 10 in 2011, Top 20 in 2012–2014, and Top 30 only from 2015** — so "absent from the
# 2013 org list" means *outside that club's top 20*, which is a materially weaker statement than
# the same absence in 2023, and an org rank of 15 is mid-pack in one era and near-elite in another.
# The overall list has the same problem at the other end (Top 50 in 2010–2011).
#
# The authoritative depth is always the OBSERVED `max(rank)` per (season, list_name) in the table —
# this map is the documented summary, not a substitute for reading it.
OVERALL_LIST_DEPTH_BY_ERA: dict[str, int] = {"2010-2011": 50, "2012+": 100}
ORG_LIST_DEPTH_BY_ERA: dict[str, int] = {"2011": 10, "2012-2014": 20, "2015+": 30}

# The 30 org list slugs, exactly as they appear in the URL path, → THE BOARD's org abbreviation
# (`board_assembly.ORG_TO_LEAGUE` keys, FanGraphs convention: SFG/WSN/CHW/KCR/SDP/TBR, ATH for the
# relocated Athletics). Hardcoded rather than derived: the ingest probes all 30 URLs on every run
# and FAILS LOUD on a miss, so a renamed club slug surfaces as an error instead of a silently
# absent organization (the "coverage silently dropped" class this repo keeps getting bitten by).
ORG_SLUG_TO_ABBREV: dict[str, str] = {
    "orioles": "BAL", "redsox": "BOS", "yankees": "NYY", "rays": "TBR", "bluejays": "TOR",
    "whitesox": "CHW", "guardians": "CLE", "tigers": "DET", "royals": "KCR", "twins": "MIN",
    "athletics": "ATH", "astros": "HOU", "angels": "LAA", "mariners": "SEA", "rangers": "TEX",
    "braves": "ATL", "marlins": "MIA", "mets": "NYM", "phillies": "PHI", "nationals": "WSN",
    "cubs": "CHC", "reds": "CIN", "brewers": "MIL", "pirates": "PIT", "cardinals": "STL",
    "dbacks": "ARI", "rockies": "COL", "dodgers": "LAD", "padres": "SDP", "giants": "SFG",
}

# `Team.parentOrgName` (MLBAM's full club name) → the same abbreviation. Used for the Top 100,
# where a player's organization is only knowable from his affiliate's parent club.
ORG_NAME_TO_ABBREV: dict[str, str] = {
    "Baltimore Orioles": "BAL", "Boston Red Sox": "BOS", "New York Yankees": "NYY",
    "Tampa Bay Rays": "TBR", "Toronto Blue Jays": "TOR", "Chicago White Sox": "CHW",
    "Cleveland Guardians": "CLE", "Detroit Tigers": "DET", "Kansas City Royals": "KCR",
    "Minnesota Twins": "MIN", "Athletics": "ATH", "Oakland Athletics": "ATH",
    "Houston Astros": "HOU", "Los Angeles Angels": "LAA", "Seattle Mariners": "SEA",
    "Texas Rangers": "TEX", "Atlanta Braves": "ATL", "Miami Marlins": "MIA", "New York Mets": "NYM",
    "Philadelphia Phillies": "PHI", "Washington Nationals": "WSN", "Chicago Cubs": "CHC",
    "Cincinnati Reds": "CIN", "Milwaukee Brewers": "MIL", "Pittsburgh Pirates": "PIT",
    "St. Louis Cardinals": "STL", "Arizona Diamondbacks": "ARI", "Colorado Rockies": "COL",
    "Los Angeles Dodgers": "LAD", "San Diego Padres": "SDP", "San Francisco Giants": "SFG",
}


class PipelineParseError(RuntimeError):
    """The ranking payload could not be located or did not look like a ranking.

    HARD stop rather than an empty list: MLB.com is a JS-heavy marketing site, and "the page
    rendered but the embedded cache moved" is indistinguishable from "this org has no prospects"
    unless the parser refuses to return an empty success. A silently-empty source would enter the
    consensus as *unranked everywhere*, which is a data claim we never made.
    """


# ── URL / selection keys ─────────────────────────────────────────────────────────────────────

def list_slug(season: int, list_name: str) -> str:
    """The URL path for a ranking list, e.g. `/prospects/2026/top100/`."""
    return f"/prospects/{int(season)}/{list_name}/"


def selection_slug(season: int, list_name: str) -> str:
    """The Apollo selection key MLB uses for that list, e.g. `sel-pr-2026-top100`."""
    return f"sel-pr-{int(season)}-{list_name}"


# ── robots.txt ───────────────────────────────────────────────────────────────────────────────

def robots_disallows(robots_txt: str, path: str, agent: str = "*") -> bool:
    """Would `agent` be disallowed from `path` by this robots.txt?

    A deliberately small, strict prefix matcher over the `User-agent: <agent>` group (plus a
    trailing-`*` wildcard, which mlb.com does not currently use). It exists so the access rule is
    MECHANICAL: the ingest re-reads robots on every run and refuses to fetch if `/prospects/`ever
    becomes disallowed, rather than relying on a note in a docstring that a future session skims.
    An empty `Disallow:` means "allow everything" per the standard and is ignored.
    """
    active = False
    disallows: list[str] = []
    for raw in robots_txt.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            active = value == agent or value == "*"
        elif field == "disallow" and active and value:
            disallows.append(value)
    for rule in disallows:
        if rule.endswith("*"):
            if path.startswith(rule[:-1]):
                return True
        elif path.startswith(rule):
            return True
    return False


# ── Scouting grades (best-effort, from prose) ────────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")
_GRADES_RE = re.compile(r"scouting grades?\s*:?\s*(.{0,220})", re.IGNORECASE | re.DOTALL)
_GRADE_PAIR_RE = re.compile(r"([A-Za-z][A-Za-z /\.]{1,18}?)\s*:\s*(\d{2})(?!\d)")

# The grade labels MLB Pipeline publishes → our column suffix. Hitters get five tools + Overall;
# pitchers get their pitch mix + Control. Anything unrecognised is dropped rather than guessed —
# a mislabelled grade is worse than an absent one for E7.12's tool-grade→component prior.
_GRADE_LABELS: dict[str, str] = {
    "hit": "hit", "power": "power", "run": "run", "arm": "arm", "field": "field",
    "fastball": "fastball", "curveball": "curveball", "slider": "slider", "changeup": "changeup",
    "cutter": "cutter", "splitter": "splitter", "sinker": "sinker", "sweeper": "sweeper",
    "control": "control", "command": "control", "overall": "overall",
}


def extract_scouting_grades(bio_html: str | None) -> dict[str, float]:
    """`"Scouting grades: Hit: 50 | Power: 55 | ... | Overall: 55"` → `{'hit': 50.0, ...}`.

    Best-effort by construction: the grades live in free text, not a field (see the module
    docstring). No grades found ⇒ an EMPTY dict, so a downstream consumer sees "not published"
    rather than a row of zeros.
    """
    if not bio_html:
        return {}
    text = _TAG_RE.sub(" ", str(bio_html))
    match = _GRADES_RE.search(text)
    if not match:
        return {}
    out: dict[str, float] = {}
    for label, value in _GRADE_PAIR_RE.findall(match.group(1)):
        key = _GRADE_LABELS.get(label.strip().lower())
        if key is None:
            continue
        grade = float(value)
        # The 20-80 scouting scale. A number outside it is a parse artifact (a year, a jersey
        # number, a stat), not a grade — dropped rather than carried into a prior.
        if 20.0 <= grade <= 80.0:
            out.setdefault(key, grade)
    return out


# ── The page parser ──────────────────────────────────────────────────────────────────────────

def _selection_pattern(slug: str) -> str:
    """The regex for one selection key. The `limit` differs per list type (100 vs 30) and the inner
    quotes may or may not be backslash-escaped depending on where in the document the cache landed,
    so both are matched loosely and only the SLUG is pinned."""
    return (r'getPlayerRankingsFromSelection\(\{\\?"limit\\?":(\d+),\\?"slug\\?":\\?"'
            + re.escape(slug) + r'\\?"\}\)"\s*:\s*')


def _extract_json_array(text: str, start: int) -> str:
    """Bracket-match the JSON array beginning at `start` (the payload is one line of ~700 KB, so a
    regex for the whole array is not viable and a naive `]` search truncates it mid-player)."""
    depth = 0
    for pos in range(start, len(text)):
        char = text[pos]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[start:pos + 1]
    raise PipelineParseError(
        "the ranking array is unterminated — the page was truncated mid-download. Re-fetch; do "
        "NOT write a partial list (a short list reads downstream as 'these players were cut')."
    )


def _entity_blob(text: str, key: str) -> dict[str, Any] | None:
    """Pull one `"<Type>:<id>":{…}` entity out of the flat Apollo cache by bracket-matching."""
    marker = f'"{key}":' + "{"
    idx = text.find(marker)
    if idx < 0:
        return None
    start = idx + len(marker) - 1
    depth = 0
    for pos in range(start, len(text)):
        char = text[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:pos + 1])
                except ValueError:
                    return None
    return None


def _select_bio(bios: Any, season: int) -> tuple[str | None, int | None]:
    """The scouting report to grade off, and which year it is. Returns `(text, bio_season)`.

    🚨 **NEVER A BIO FROM AFTER `season`.** A historical ranking page serves the player's WHOLE bio
    history, including reports written years LATER: the 2015 Top 100 page carries 2016/2017/2018
    writeups (measured — 65 of its 100 players have a 2016 bio). Grading a 2015 snapshot off a 2018
    report would feed three years of hindsight into a point-in-time row, which is precisely the
    leakage an accuracy study exists to avoid. So the rule is: the bio titled `season` if it exists
    (measured 100/100 on the 2015, 2019 and 2023 Top 100s), else the newest one **not after** it.

    Non-year titles (`"international"`, `"draft"`) carry no date and cannot be ordered against a
    season, so they are used only when nothing dated qualifies — and `bio_season` comes back None,
    which is how a consumer knows the grade is undated rather than era-matched.
    """
    if not isinstance(bios, list) or not bios:
        return None, None
    dated: list[tuple[int, Any]] = []
    undated: list[Any] = []
    for bio in bios:
        title = str((bio or {}).get("contentTitle") or "").strip()
        # ⚠️ `.isdigit()` alone is not "is a year". The real feed contains a `contentTitle` of
        # "201" (one row in the 2016 backfill) — digits, parses to the year 201, sorts below every
        # real season and so quietly wins the "newest bio not after the season" fallback whenever
        # nothing else qualifies, then reports `bio_season = 201` into a study. A title outside a
        # plausible range is UNDATED, which is the honest answer: we cannot place it in time.
        year = int(title) if title.isdigit() else None
        if year is not None and MIN_BIO_YEAR <= year <= MAX_BIO_YEAR:
            dated.append((year, bio))
        else:
            undated.append(bio)
    eligible = [(year, bio) for year, bio in dated if year <= int(season)]
    if eligible:
        year, bio = max(eligible, key=lambda pair: pair[0])
        return (bio or {}).get("contentText"), year
    if undated:
        return (undated[0] or {}).get("contentText"), None
    return None, None


def parse_rankings_page(page_html: str, *, season: int, list_name: str) -> list[dict[str, Any]]:
    """One fetched ranking page → typed rows (one per ranked player).

    Every row carries `mlbam_id` (the spine), `rank`, and the display attributes. The org comes
    from the URL for an org list (authoritative — that IS the list) and from the player's affiliate
    parent club for the Top 100.
    """
    text = _html.unescape(page_html)
    slug = selection_slug(season, list_name)
    match = re.search(_selection_pattern(slug), text)
    if not match:
        raise PipelineParseError(
            f"no ranking payload for selection '{slug}' in the fetched page. Either the season/list "
            f"does not exist yet, or MLB moved the embedded cache. Re-run with --probe and inspect; "
            f"do NOT fall back to https://data-graph.mlb.com/graphql — that host is robots-blocked."
        )
    entries = json.loads(_extract_json_array(text, match.end()))
    if not entries:
        raise PipelineParseError(f"selection '{slug}' resolved to an EMPTY ranking.")

    org_from_slug = ORG_SLUG_TO_ABBREV.get(list_name)
    rows: list[dict[str, Any]] = []
    for entry in entries:
        player_entity = entry.get("playerEntity") or {}
        ref = ((player_entity.get("player") or {}).get("__ref") or "")
        mlbam_id = ref.split(":", 1)[1] if ref.startswith("Person:") else None
        person = _entity_blob(text, ref) if ref else None
        person = person or {}

        team_ref = ((person.get("activeRoster") or {}).get("__ref") or "")
        team = _entity_blob(text, team_ref) if team_ref else None
        # A minor-league affiliate carries `parentOrgName`; a player who has reached the majors is
        # rostered on the MLB club itself, whose `parentOrgName` is NULL — his club IS the org.
        # Without this fallback the three Top-100 players already at MLB came back org-less.
        parent_org_name = (team or {}).get("parentOrgName") or (team or {}).get("name")
        org_current = ORG_NAME_TO_ABBREV.get(str(parent_org_name)) if parent_org_name else None

        name_parts = [person.get("useName"), person.get("useLastName")]
        player_name = " ".join(p for p in name_parts if p) or None

        bio, bio_season = _select_bio(player_entity.get("prospectBio"), season)
        grades = extract_scouting_grades(bio)

        rows.append({
            "source": PIPELINE_SOURCE,
            "list_name": list_name,
            "list_type": "top100" if list_name == TOP100_LIST else "org",
            "rank": int(entry["rank"]) if entry.get("rank") is not None else None,
            "mlbam_id": str(mlbam_id) if mlbam_id else None,
            "player_name": player_name,
            # ── POINT-IN-TIME: these belong to the ranking itself ────────────────────────────
            # `org` comes from the URL for an org list — the 2015 Orioles list IS the Orioles'
            # 2015 top 30, so that org is as-of the season. A Top-100 entry has no org of its own,
            # which is why it is NULL here rather than borrowed from `org_current` (see below).
            "org": org_from_slug,
            "position": (player_entity.get("position")
                         or ((person.get("primaryPosition") or {}).get("abbreviation"))),
            "eta": _int_or_none(player_entity.get("eta")),
            "birth_date": person.get("birthDate"),
            "bats": person.get("batSideCode"),
            "throws": person.get("pitchHandCode"),
            "draft_year": _int_or_none(person.get("draftYear")),
            "bio_season": bio_season,
            # ── CURRENT STATE — ⚠️ AS OF THE FETCH, NOT AS OF `season` ───────────────────────
            # `Person`/`Team` entities are LIVE records, so a historical page returns TODAY's
            # roster and age. Measured on the 2015 Top 100: Byron Buxton comes back age 32 (he was
            # 21) and Kris Bryant comes back COL (he was a Cub). Using either as an as-of feature
            # would be straightforward leakage — hence the `_current` suffix, which makes the
            # mistake visible at the call site instead of six months later in a study's residuals.
            "org_current": org_current,
            "age_current": _float_or_none(person.get("currentAge")),
            "affiliate_team_current": (team or {}).get("name"),
            "parent_org_name_current": parent_org_name,
            **{f"pipeline_grade_{k}": v for k, v in grades.items()},
        })
    return rows


def _int_or_none(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
