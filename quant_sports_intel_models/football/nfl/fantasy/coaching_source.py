"""coaching_source.py — NF-D10 OFFENSIVE-COORDINATOR / HEAD-COACH change source (the one genuine
feature GAP NF1.5 surfaced; feeds H-SYSTEM and the future weekly model).

THE GAP (quoting NF1.2's own H-SYSTEM registration, `nf1_2_model.py`):

    H-SYSTEM `system` — scheme/volume context of the FORWARD team: the projection team's
                        base-season pass rate + pace … **(Forward OC changes are unobservable in
                        our data; the destination team's realized base-season rate is the proxy.)**

That parenthesis IS the gap. A team's base-season pass rate is the OLD coordinator's rate; when a
team hires a new OC the rate a projection should lean on is the NEW one's. This module makes the
OC/HC change observable, so H-SYSTEM can be tested with the real regime variable instead of a
proxy that is definitionally blind to the shock it is trying to price.

── SOURCES (LIVE-PROBED 2026-07-31, not coded to docs — see `run_coaching_ingest.py --probe`) ────

  HEAD COACH → **nflverse `schedules/games.parquet`** (`home_coach` / `away_coach`), the SAME
    release this repo already reads for schedules. PER-GAME grain, 100% non-null 1999→2026 (the
    2026 rows already carry the announced staffs), so an HC stint carries an EXACT effective date
    — a mid-season firing is dated to the first game the successor coached, not guessed.

  OFFENSIVE COORDINATOR → **Wikipedia team-season articles** via the Wikimedia REST API
    (`api.wikimedia.org/core/v1/wikipedia/en/page/<title>`), content CC BY-SA 4.0. This is the
    story's explicitly-sanctioned last resort, taken only after probing the structured options:
      • nflverse has NO coaching release — the 25 release tags were enumerated live; `contracts`,
        `depth_charts`, `officials`, … exist, a coaches table does not.
      • Pro-Football-Reference's coaching pages sit behind a Cloudflare JS challenge (a plain
        `robots.txt` fetch returns the "Just a moment…" interstitial) — the SAME disposition
        NF-D8 reached for Spotrac/OverTheCap, so no scraper was built against it.
      • `spatto12/NFLCoaches` (PFR-derived, MIT) is HEAD-COACH ONLY and stops at 2023.
    Wikipedia's `robots.txt` allows `/wiki/<Article>` for `User-agent: *` (only `Special:` pages,
    `/w/` and `/api/` are disallowed); we read through the dedicated `api.wikimedia.org` host,
    which is Wikimedia's own designated programmatic endpoint, with an identifying UA per their
    UA policy, ONE fetch per (team, season) cached to disk forever. `robots.txt` was fetched and
    honoured, not assumed.

  A historical season's article INLINES its frozen staff list (`==Staff==` → `|Offensive Coaches=`
  → `*Offensive coordinator – [[Name]]`); the CURRENT season instead TRANSCLUDES the live
  `Template:<Franchise> staff`, so the current board year is read from the template. That split is
  load-bearing: reading the live template for a PAST season would stamp today's staff on history.

── 🚨 LEAKAGE-SAFE AS-OF (the correctness crux) ───────────────────────────────────────────────

Every stint carries an `effective_date`, and a projection for season Y may only see stints with
`effective_date <= asof_date(Y)` where `asof_date(Y) = March 15 of Y` (`_ASOF_MONTH/_ASOF_DAY`) —
after the new league year opens (~Mar 11) and after essentially the whole January–February
coaching carousel, but months before Week 1. Consequences, both intended:

  * an OFFSEASON hire for season Y IS in the Y feature (a season-opening stint is stamped with
    that anchor, which is genuinely when the hire was public);
  * a MID-SEASON firing INSIDE season Y is dated inside Y, so it is `> asof(Y)` and CANNOT reach
    Y's pre-season feature — it becomes visible only from Y+1 onward (where it is history).

`known_stints(stints, season)` is the single chokepoint that enforces this, and
`test_coaching_source.py` asserts a mid-season-Y change is invisible to Y and visible to Y+1.

── THE PRE-REGISTERED FEATURE SET (the H-SYSTEM hypothesis — ⛔ no open search) ─────────────────

Exactly the story's registration, plus the one column that makes the family a real H-SYSTEM test
rather than a bag of flags:

  `new_oc`                    — the OC changed vs whoever finished last season (0/1).
  `oc_tenure_years`           — consecutive prior seasons this OC has held the job (0 = new).
  `new_hc`                    — the head coach changed (0/1).
  `coach_continuity`          — the "scheme-family continuity" candidate: 1.0 both retained,
                                0.5 one changed, 0.0 both changed.
  `oc_prior_pass_rate_delta`  — the SCHEME-SHOCK MAGNITUDE, and the column that actually closes
                                NF1.2's parenthesis: (the new OC's LAST team's realized pass rate)
                                − (this team's base-season pass rate). 0.0 for a retained OC by
                                construction; NaN for a first-time/internally-promoted OC with no
                                prior NFL coordinator season. Built in `nf1_2_model.attach_coach`
                                (it needs the team-rate frame the runner already loads once).

`best_alpha = 0` — projection FEATURES, not an edge claim. Whether they EARN a place is decided
by NF1.5's deflated market+blind re-bake-off, not asserted here (a new data source is not
automatically a feature).

Every helper below is PURE (frames/strings in, frames out, NO IO) so the whole construct — the
wikitext parse, the stint assembly, the as-of rule, the tenure walk — is fast-gate tested offline;
the network fetches live in `fetch_*` and the lake read in `_read_lake`.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("nfl.fantasy.coaching")

_ART = Path(__file__).resolve().parent / "artifacts"
_DEFAULT_CACHE = _ART / "coaching_cache"

# ── Sources ────────────────────────────────────────────────────────────────────────────────────
SCHEDULES_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet"
WIKI_API = "https://api.wikimedia.org/core/v1/wikipedia/en/page/{}"
# Wikimedia's UA policy asks for an identifying agent with contact info on programmatic access.
WIKI_UA = "credence-sports-research/1.0 (ctcb57@gmail.com) NF-D10-coaching-ingest"
WIKI_LICENSE = "CC BY-SA 4.0 (Wikipedia)"
_FETCH_SLEEP_S = 0.25  # courtesy rate-limit; every page is cached forever after the first fetch

# The landed Delta tables (the serving deliverables).
LAKE_SPORT = "nfl"
LAKE_TIER = "fantasy"
LAKE_SOURCE_STINTS = "coaching/coach_stints"
LAKE_SOURCE_FEATURES = "coaching/team_coach_features"

# The AS-OF anchor: what a season-Y pre-season projection is allowed to know (see the docstring).
_ASOF_MONTH, _ASOF_DAY = 3, 15

ROLE_HC = "HC"
ROLE_OC = "OC"

# The observed coverage floor of the Wikipedia team-season staff sections + the nflverse coach
# columns; the story's ~2006 target. `run_coaching_ingest.py --probe` re-measures it live.
DEFAULT_FROM_SEASON, DEFAULT_TO_SEASON = 2006, 2026

# Legacy team codes → the current franchise code (the crosswalk landmine; nflverse schedules key
# the Rams 'LA'/'STL' and the Raiders 'OAK', our marts use 'LAR'/'LV').
_TEAM_NORM = {"LA": "LAR", "STL": "LAR", "SD": "LAC", "OAK": "LV"}

# Season-aware Wikipedia franchise names (2006–2026). A relocation/rename changes the ARTICLE
# TITLE, so a single name per team would 404 half the history.
_FRANCHISE_ERAS: dict[str, tuple[tuple[int, str], ...]] = {
    "ARI": ((0, "Arizona Cardinals"),), "ATL": ((0, "Atlanta Falcons"),),
    "BAL": ((0, "Baltimore Ravens"),), "BUF": ((0, "Buffalo Bills"),),
    "CAR": ((0, "Carolina Panthers"),), "CHI": ((0, "Chicago Bears"),),
    "CIN": ((0, "Cincinnati Bengals"),), "CLE": ((0, "Cleveland Browns"),),
    "DAL": ((0, "Dallas Cowboys"),), "DEN": ((0, "Denver Broncos"),),
    "DET": ((0, "Detroit Lions"),), "GB": ((0, "Green Bay Packers"),),
    "HOU": ((0, "Houston Texans"),), "IND": ((0, "Indianapolis Colts"),),
    "JAX": ((0, "Jacksonville Jaguars"),), "KC": ((0, "Kansas City Chiefs"),),
    "LV": ((0, "Oakland Raiders"), (2020, "Las Vegas Raiders")),
    "LAC": ((0, "San Diego Chargers"), (2017, "Los Angeles Chargers")),
    "LAR": ((0, "St. Louis Rams"), (2016, "Los Angeles Rams")),
    "MIA": ((0, "Miami Dolphins"),), "MIN": ((0, "Minnesota Vikings"),),
    "NE": ((0, "New England Patriots"),), "NO": ((0, "New Orleans Saints"),),
    "NYG": ((0, "New York Giants"),), "NYJ": ((0, "New York Jets"),),
    "PHI": ((0, "Philadelphia Eagles"),), "PIT": ((0, "Pittsburgh Steelers"),),
    "SF": ((0, "San Francisco 49ers"),), "SEA": ((0, "Seattle Seahawks"),),
    "TB": ((0, "Tampa Bay Buccaneers"),), "TEN": ((0, "Tennessee Titans"),),
    "WAS": ((0, "Washington Redskins"), (2020, "Washington Football Team"),
            (2022, "Washington Commanders")),
}

TEAMS: tuple[str, ...] = tuple(sorted(_FRANCHISE_ERAS))

_STINT_COLS = ["season", "team", "role", "coach_name", "effective_date", "is_season_opener",
               "annotation", "source"]

FEATURE_COLS = ["season", "team", "hc_name", "oc_name", "prev_hc_name", "prev_oc_name",
                "new_hc", "new_oc", "hc_tenure_years", "oc_tenure_years", "coach_continuity",
                "oc_prev_team", "oc_prev_season", "oc_source"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Pure helpers — naming / the as-of rule (no IO, fast-gate tested)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def norm_team(team) -> str | float:
    """Legacy/alternate team code → the current franchise code (NaN-safe). PURE."""
    if team is None or (isinstance(team, float) and np.isnan(team)):
        return np.nan
    t = str(team).strip().upper()
    return _TEAM_NORM.get(t, t)


def franchise_name(team: str, season: int) -> str | None:
    """The franchise's Wikipedia name in `season` (e.g. ('LAR', 2012) → 'St. Louis Rams'). A code
    outside the 32-team map → None. PURE."""
    eras = _FRANCHISE_ERAS.get(str(team).strip().upper())
    if not eras:
        return None
    name = None
    for start, n in eras:
        if int(season) >= start:
            name = n
    return name


def season_article_title(team: str, season: int) -> str | None:
    """The team-season article title, e.g. '2015 Dallas Cowboys season'. PURE."""
    name = franchise_name(team, season)
    return f"{int(season)} {name} season" if name else None


def staff_template_title(team: str, season: int) -> str | None:
    """The LIVE staff template, e.g. 'Template:Chicago Bears staff' — the current season's article
    transcludes this instead of inlining a frozen staff list, so the current board year reads
    here. ⚠️ Valid ONLY for the current season: it always reflects TODAY's staff. PURE."""
    name = franchise_name(team, season)
    return f"Template:{name} staff" if name else None


def asof_date(season: int) -> date:
    """What a season-`season` PRE-SEASON projection is allowed to know: March 15 of that season —
    after the new league year opens and after the January–February coaching carousel, months
    before Week 1. The single leakage boundary; see the module docstring. PURE."""
    return date(int(season), _ASOF_MONTH, _ASOF_DAY)


def known_stints(stints: pd.DataFrame, season: int) -> pd.DataFrame:
    """🚨 THE LEAKAGE CHOKEPOINT — the stints a season-`season` pre-season projection may use:
    `effective_date <= asof_date(season)`. An offseason hire for `season` qualifies (its stint is
    anchored at exactly that date); a mid-season change INSIDE `season` is dated inside the season
    and is therefore excluded, becoming visible only from `season + 1`. A stint with no parseable
    effective date is EXCLUDED (unknown-date ⇒ not known — fail closed, never leak). PURE."""
    if stints is None or stints.empty:
        return pd.DataFrame(columns=_STINT_COLS)
    d = stints.copy()
    eff = pd.to_datetime(d["effective_date"], errors="coerce")
    cutoff = pd.Timestamp(asof_date(season))
    return d[eff.notna() & (eff <= cutoff)].copy()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Pure helpers — the Wikipedia staff parse
# ══════════════════════════════════════════════════════════════════════════════════════════════
# A staff line: '*Offensive coordinator – [[Scott Linehan]]'. The LABEL is everything before the
# dash and is matched loosely on purpose — real articles carry COMBINED titles
# ('*Assistant head coach/offensive coordinator – [[Marty Mornhinweg]]', '*Offensive coordinator/
# quarterbacks – …'), and requiring the label to START with the role dropped ~8% of team-seasons.
# The separator is the en/em dash (or a SPACED hyphen) — a bare '-' would split 'Co-offensive'.
_ROLE_PATTERNS = {
    ROLE_OC: re.compile(
        r"^\*+\s*'{0,3}\s*(?P<label>[^\n–—]*?offensive\s+coordinator[^\n–—]*?)'{0,3}"
        r"\s*(?:[–—]|\s-\s)\s*(?P<rest>.+?)\s*$", re.I | re.M),
    ROLE_HC: re.compile(
        r"^\*+\s*'{0,3}\s*(?P<label>[^\n–—]*?head\s+coach[^\n–—]*?)'{0,3}"
        r"\s*(?:[–—]|\s-\s)\s*(?P<rest>.+?)\s*$", re.I | re.M),
}

# Labels that CONTAIN the role token but are a DIFFERENT job — an assistant/associate coordinator,
# a quality-control or position-group coach. 'Assistant HEAD COACH/offensive coordinator' is the
# real OC and must survive, so the rejection anchors on the role token itself, not on 'assistant'.
_ROLE_REJECT = {
    ROLE_OC: re.compile(r"(assistant|associate|assist\.)\s+offensive\s+coordinator"
                        r"|quality\s+control|offensive\s+coordinator\s+intern", re.I),
    ROLE_HC: re.compile(r"assistant\s+head\s+coach\s*$|associate\s+head\s+coach\s*$", re.I),
}

# '[[Ben Johnson (American football coach)|Ben Johnson]]' → 'Ben Johnson'; '[[Dan Campbell]]' →
# 'Dan Campbell'.
_WIKILINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]|]+)\]\]")
_PAREN = re.compile(r"\(([^)]*)\)")
_REF = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.I | re.S)


def clean_coach_name(raw: str) -> str:
    """A wikitext staff value → a bare coach name: resolve the wikilink (piped display text wins),
    drop refs/comments/parentheticals/formatting. '' when nothing is left. PURE."""
    if not raw:
        return ""
    s = _REF.sub("", str(raw))
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = _WIKILINK.sub(r"\1", s)
    s = _PAREN.sub("", s)
    s = s.replace("'''", "").replace("''", "").replace("&nbsp;", " ")
    s = re.sub(r"\{\{[^}]*\}\}", "", s)
    s = s.split("<")[0]
    return re.sub(r"\s+", " ", s).strip(" ,;*–—-")


# Section headings that hold a team-season's staff list. The parse is RESTRICTED to this section:
# a season article's prose ('… was hired as offensive coordinator …') also lives in `*` bullets
# under Offseason/Coaching-changes, and matching those made a PROSE sentence outrank the real
# coordinator on 2 of 32 teams in a probed season. A staff TEMPLATE page carries no `==` heading
# at all, so a page with no headings is parsed whole.
_STAFF_HEADING = re.compile(
    r"^==\s*(?:staff|coaching\s+staff|personnel|staff\s+and\s+roster|coaches)\s*==\s*$",
    re.I | re.M)
_ANY_HEADING = re.compile(r"^==[^=].*?==\s*$", re.M)


_NOINCLUDE = re.compile(r"<noinclude>.*?</noinclude>", re.I | re.S)


def staff_section(wikitext: str) -> str:
    """The `==Staff==` section of a team-season article (up to the next top-level heading), the
    whole text when the page carries no headings at all (a staff TEMPLATE), or '' when the article
    has headings but no staff section (a genuine coverage gap).

    `<noinclude>` blocks are stripped FIRST: a staff template's transcluded body has no headings,
    but its `<noinclude>` documentation does — leaving them in made every template look like an
    article with no staff section and silently zeroed the CURRENT board year. PURE."""
    if not wikitext:
        return ""
    wikitext = _NOINCLUDE.sub("", wikitext)
    m = _STAFF_HEADING.search(wikitext)
    if m is None:
        return "" if _ANY_HEADING.search(wikitext) else wikitext
    rest = wikitext[m.end():]
    nxt = _ANY_HEADING.search(rest)
    return rest[: nxt.start()] if nxt else rest


def _is_opening_holder(label: str, annotation: str, ordinal: int) -> bool:
    """Does this parsed staff line describe the season's WEEK-1 holder?

    A season that changed coordinators mid-year lists BOTH, usually annotated ('(Weeks 1–8)',
    '(interim)', '(fired October 21)'). The opener is the FIRST listed line that is not marked
    interim and whose week annotation, if any, starts at week 1. Anything else is a mid-season
    replacement — which the as-of rule then keeps out of that season's feature. PURE."""
    tag = f"{label or ''} {annotation or ''}".lower()
    if "interim" in tag:
        return False
    # 'through week 8' / 'weeks 1–8' / 'fired Nov 26' all describe the man who STARTED the season.
    if re.search(r"\b(through|until|thru)\s+week|\bweeks?\s*1\s*[-–—]|\bfired\b|\bresigned\b", tag):
        return True
    m = re.search(r"weeks?\s*(\d+)", tag)
    if m:
        return int(m.group(1)) <= 1
    if re.search(r"\b(replaced|promoted|hired|took over|from week)\b", tag):
        return False
    return ordinal == 0


def parse_staff_roles(wikitext: str, role: str) -> list[dict]:
    """Every `role` line in a team-season article / staff template, in document order.

    Read ONLY from `staff_section` (see its docstring — prose bullets otherwise outrank the real
    coordinator). Returns dicts of {coach_name, label, annotation, is_season_opener, ordinal}.
    Lines whose label names a DIFFERENT job that merely contains the role token (an assistant/
    associate coordinator, a quality-control coach) are rejected by `_ROLE_REJECT`. An empty list
    means the article carries no staff list for that role — a coverage gap, never fabricated.

    ⚠️ A mid-season INTERIM is often listed FIRST (his combined title, e.g. 'Assistant head coach/
    interim offensive coordinator', sorts above the plain 'Offensive coordinator' line), which
    would leave a season with NO opener. So when nothing is flagged, the first NON-interim line is
    promoted — a season that genuinely has a holder must not lose him to list order. PURE."""
    pat, reject = _ROLE_PATTERNS[role], _ROLE_REJECT[role]
    section = staff_section(wikitext)
    out: list[dict] = []
    for m in pat.finditer(section):
        label = (m.group("label") or "").strip()
        if reject.search(label):
            continue
        rest = _WIKILINK.sub(r"\1", m.group("rest"))  # drop '(American football)' disambiguators
        name = clean_coach_name(m.group("rest"))
        if not name:
            continue
        annotation = "; ".join(a.strip() for a in _PAREN.findall(rest) if a.strip())
        out.append({
            "coach_name": name,
            "label": label,
            "annotation": annotation,
            "is_season_opener": _is_opening_holder(label, annotation, len(out)),
            "ordinal": len(out),
        })
    if out and not any(r["is_season_opener"] for r in out):
        for r in out:
            if "interim" not in f"{r['label']} {r['annotation']}".lower():
                r["is_season_opener"] = True
                break
    return out


def oc_stints_from_wikitext(wikitext: str, team: str, season: int,
                            source: str = "wikipedia_season_article") -> pd.DataFrame:
    """One team-season's OC stint rows from its staff wikitext.

    The season-OPENING holder is stamped with `asof_date(season)` (he was hired in the offseason —
    that IS when he became known). Any FURTHER listed coordinator is a mid-season replacement: he
    gets a WITHIN-SEASON effective date derived from his week annotation when present, else the
    season's November 1 midpoint — either way strictly AFTER `asof_date(season)`, so the as-of rule
    keeps him out of `season`'s pre-season feature while still recording him for `season + 1`. PURE."""
    rows = []
    for r in parse_staff_roles(wikitext, ROLE_OC):
        if r["is_season_opener"]:
            eff = asof_date(season)
        else:
            m = re.search(r"weeks?\s*(\d+)", (r["annotation"] or "").lower())
            week = int(m.group(1)) if m else 9
            # week 1 ≈ the Thursday after Labor Day; a week is 7 days. An approximation is fine —
            # the only thing that must be exact is "inside the season, after the as-of anchor".
            eff = pd.Timestamp(date(int(season), 9, 8)) + pd.Timedelta(days=7 * max(week - 1, 1))
            eff = eff.date()
        rows.append({
            "season": int(season), "team": norm_team(team), "role": ROLE_OC,
            "coach_name": r["coach_name"], "effective_date": str(eff),
            "is_season_opener": bool(r["is_season_opener"]),
            "annotation": r["annotation"], "source": source,
        })
    return pd.DataFrame(rows, columns=_STINT_COLS)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Pure helpers — head-coach stints from the per-game schedule
# ══════════════════════════════════════════════════════════════════════════════════════════════
def head_coach_stints(games: pd.DataFrame) -> pd.DataFrame:
    """HC stints from nflverse `games.parquet` (regular season): for each (season, team) the
    coaches in game order, one stint per contiguous run.

    The season's FIRST coach is the opener → stamped `asof_date(season)` (his hire was public in
    the offseason). A successor is stamped the ACTUAL `gameday` of his first game — an exact
    mid-season effective date, and one strictly after the as-of anchor, so a mid-season firing is
    structurally invisible to that season's pre-season feature. PURE."""
    if games is None or games.empty:
        return pd.DataFrame(columns=_STINT_COLS)
    g = games.copy()
    if "game_type" in g.columns:
        g = g[g["game_type"].astype(str).str.upper() == "REG"]
    long = pd.concat([
        g.rename(columns={"home_team": "team", "home_coach": "coach_name"})[
            ["season", "week", "gameday", "team", "coach_name"]],
        g.rename(columns={"away_team": "team", "away_coach": "coach_name"})[
            ["season", "week", "gameday", "team", "coach_name"]],
    ], ignore_index=True)
    long["team"] = long["team"].map(norm_team)
    long = long.dropna(subset=["team", "coach_name"])
    long["coach_name"] = long["coach_name"].astype(str).str.strip()
    long = long[long["coach_name"] != ""]
    if long.empty:
        return pd.DataFrame(columns=_STINT_COLS)
    long["week"] = pd.to_numeric(long["week"], errors="coerce")
    long = long.sort_values(["season", "team", "week", "gameday"])

    rows = []
    for (season, team), d in long.groupby(["season", "team"], sort=True):
        prev = None
        first = True
        for r in d.itertuples(index=False):
            if r.coach_name == prev:
                continue
            prev = r.coach_name
            eff = str(asof_date(int(season))) if first else str(r.gameday)[:10]
            rows.append({
                "season": int(season), "team": team, "role": ROLE_HC,
                "coach_name": r.coach_name, "effective_date": eff,
                "is_season_opener": bool(first),
                "annotation": "" if first else f"from week {int(r.week)}"
                if pd.notna(r.week) else "",
                "source": "nflverse_schedules",
            })
            first = False
    return pd.DataFrame(rows, columns=_STINT_COLS)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Pure helpers — the leakage-safe per-season feature build
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _opener(known: pd.DataFrame, team: str, role: str, season: int) -> str | None:
    """`season`'s WEEK-1 holder of `role` for `team` (from the already-as-of-filtered frame)."""
    d = known[(known["team"] == team) & (known["role"] == role)
              & (known["season"] == int(season)) & (known["is_season_opener"])]
    return str(d.iloc[0]["coach_name"]) if len(d) else None


def _last_holder(known: pd.DataFrame, team: str, role: str, season: int) -> str | None:
    """Who FINISHED `season` in `role` for `team` — the chronologically last stint of that
    season (a mid-season replacement supersedes the opener)."""
    d = known[(known["team"] == team) & (known["role"] == role)
              & (known["season"] == int(season))]
    if d.empty:
        return None
    d = d.sort_values("effective_date")
    return str(d.iloc[-1]["coach_name"])


def _tenure_years(known: pd.DataFrame, team: str, role: str, season: int, holder: str | None,
                  max_lookback: int = 25) -> float:
    """Consecutive PRIOR seasons `holder` finished as `team`'s `role` (0 = new this season). NaN
    when the holder is unknown."""
    if not holder:
        return np.nan
    n = 0
    for back in range(1, max_lookback + 1):
        if _last_holder(known, team, role, int(season) - back) != holder:
            break
        n += 1
    return float(n)


def _oc_previous_job(known: pd.DataFrame, team: str, season: int,
                     holder: str | None) -> tuple[str | float, float]:
    """The new OC's most recent PRIOR coordinator job at a DIFFERENT team → (team, season).

    This is what makes `oc_prior_pass_rate_delta` computable: the scheme he is bringing is the one
    his last offense actually ran. (NaN, NaN) for a retained OC, a first-time coordinator, or an
    internal promotion — an honest unknown, never a fabricated 0."""
    if not holder:
        return np.nan, np.nan
    d = known[(known["role"] == ROLE_OC) & (known["coach_name"] == holder)
              & (known["season"] < int(season)) & (known["team"] != team)]
    if d.empty:
        return np.nan, np.nan
    d = d.sort_values(["season", "effective_date"])
    last = d.iloc[-1]
    return str(last["team"]), float(last["season"])


def build_team_coach_features(stints: pd.DataFrame, season: int) -> pd.DataFrame:
    """⭐ The leakage-safe per-(team) coaching-regime features for projecting `season`.

    Reads ONLY `known_stints(stints, season)` — so a mid-season change inside `season` cannot
    influence its own season's row (see the module docstring). Compares `season`'s WEEK-1 holder
    against whoever FINISHED `season - 1` (both fully known before Week 1), which is the change a
    player's usage actually experiences. PURE."""
    known = known_stints(stints, season)
    if known.empty:
        return pd.DataFrame(columns=FEATURE_COLS)
    teams = sorted(known.loc[known["season"] == int(season), "team"].dropna().unique())
    if not teams:
        teams = sorted(known["team"].dropna().unique())

    src_by_team = (known[(known["role"] == ROLE_OC) & (known["season"] == int(season))]
                   .drop_duplicates("team").set_index("team")["source"].to_dict())

    rows = []
    for team in teams:
        hc = _opener(known, team, ROLE_HC, season)
        oc = _opener(known, team, ROLE_OC, season)
        prev_hc = _last_holder(known, team, ROLE_HC, int(season) - 1)
        prev_oc = _last_holder(known, team, ROLE_OC, int(season) - 1)
        new_hc = float(hc != prev_hc) if (hc and prev_hc) else np.nan
        new_oc = float(oc != prev_oc) if (oc and prev_oc) else np.nan
        prev_team, prev_season = ((np.nan, np.nan) if not new_oc
                                  else _oc_previous_job(known, team, season, oc))
        cont = np.nan
        if np.isfinite(new_hc) and np.isfinite(new_oc):
            cont = float(1.0 - 0.5 * (new_hc + new_oc))
        rows.append({
            "season": int(season), "team": team,
            "hc_name": hc, "oc_name": oc, "prev_hc_name": prev_hc, "prev_oc_name": prev_oc,
            "new_hc": new_hc, "new_oc": new_oc,
            "hc_tenure_years": _tenure_years(known, team, ROLE_HC, season, hc),
            "oc_tenure_years": _tenure_years(known, team, ROLE_OC, season, oc),
            "coach_continuity": cont,
            "oc_prev_team": prev_team, "oc_prev_season": prev_season,
            "oc_source": src_by_team.get(team),
        })
    return pd.DataFrame(rows, columns=FEATURE_COLS).sort_values("team").reset_index(drop=True)


_FEATURE_STR_COLS = ("team", "hc_name", "oc_name", "prev_hc_name", "prev_oc_name",
                     "oc_prev_team", "oc_source")
_FEATURE_NUM_COLS = ("new_hc", "new_oc", "hc_tenure_years", "oc_tenure_years",
                     "coach_continuity", "oc_prev_season")


def pin_feature_dtypes(features: pd.DataFrame) -> pd.DataFrame:
    """Pin every feature column to a stable dtype before it is landed.

    🧨 The landmine (hit on the first real Delta write, and the same shape as the repo's
    NULLABLE-INT→DOUBLE mirror poisoning): a season in which NO team has a resolvable previous OC
    job makes `oc_prev_team` an ALL-NaN pandas column → float64 → the Delta table is CREATED with
    that column as Float64, and the next season's partition — which does carry team codes — dies
    with `Cannot cast string 'CLE' to value of Float64 type`. Pinning at the WRITER heals every
    partition in one place rather than depending on which season happens to be written first.
    PURE."""
    out = features.copy()
    for c in _FEATURE_STR_COLS:
        if c in out.columns:
            out[c] = out[c].astype("string")
    for c in _FEATURE_NUM_COLS:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").astype("float64")
    if "season" in out.columns:
        out["season"] = pd.to_numeric(out["season"], errors="coerce").astype("int64")
    return out


def pin_stint_dtypes(stints: pd.DataFrame) -> pd.DataFrame:
    """The same dtype pin for the effective-dated stint table (`annotation` is empty for every
    season-opening row, so a season with no mid-season change would otherwise land as float).
    PURE."""
    out = stints.copy()
    for c in ("team", "role", "coach_name", "effective_date", "annotation", "source"):
        if c in out.columns:
            out[c] = out[c].astype("string")
    if "is_season_opener" in out.columns:
        out["is_season_opener"] = out["is_season_opener"].fillna(False).astype(bool)
    if "season" in out.columns:
        out["season"] = pd.to_numeric(out["season"], errors="coerce").astype("int64")
    return out


def coverage_report(stints: pd.DataFrame, features: pd.DataFrame, season: int) -> dict:
    """Honest per-season coverage: how many of the 32 teams carry an OC (the Wikipedia parse's
    real hit rate), an HC, and a computable `new_oc` — plus the observed change rate, the
    face-validity read (a plausible league-wide OC turnover is roughly a quarter to a third of
    teams per year)."""
    n_teams = int(len(features))
    oc = features["oc_name"].notna().sum() if n_teams else 0
    hc = features["hc_name"].notna().sum() if n_teams else 0
    new_oc = pd.to_numeric(features.get("new_oc"), errors="coerce") if n_teams else pd.Series(dtype=float)
    return {
        "season": int(season),
        "n_teams": n_teams,
        "oc_coverage": round(float(oc) / n_teams, 3) if n_teams else 0.0,
        "hc_coverage": round(float(hc) / n_teams, 3) if n_teams else 0.0,
        "new_oc_computable": int(new_oc.notna().sum()) if n_teams else 0,
        "new_oc_rate": round(float(new_oc.mean()), 3) if n_teams and new_oc.notna().any() else None,
        "new_hc_rate": (round(float(pd.to_numeric(features["new_hc"], errors="coerce").mean()), 3)
                        if n_teams and features["new_hc"].notna().any() else None),
        "n_stints_known": int(len(known_stints(stints, season))),
        "teams_missing_oc": sorted(features.loc[features["oc_name"].isna(), "team"].tolist())
        if n_teams else [],
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Network fetches (cached — assemble-once; a primed cache makes every rebuild offline)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def fetch_schedule_games(cache_dir: str | Path | None = None, refresh: bool = False,
                         timeout: int = 60) -> pd.DataFrame:
    """nflverse `schedules/games.parquet` (1999→the scheduled season), cached to disk. Carries
    `home_coach`/`away_coach` — the HC source — and the gamedays that date every stint."""
    cache_dir = Path(cache_dir or _DEFAULT_CACHE)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / "games.parquet"
    if not cache.exists() or refresh:
        req = urllib.request.Request(SCHEDULES_URL, headers={"User-Agent": WIKI_UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed https host
            cache.write_bytes(resp.read())
        log.info("nflverse schedules cache written: %s", cache)
    return pd.read_parquet(cache)


def _wiki_cache_path(cache_dir: Path, title: str) -> Path:
    safe = title.replace(" ", "_").replace("/", "_").replace(":", "__")
    return cache_dir / "wiki" / f"{safe}.txt"


def fetch_wikitext(title: str, cache_dir: str | Path | None = None, refresh: bool = False,
                   timeout: int = 60) -> str:
    """One Wikipedia page's wikitext via the Wikimedia REST API, cached forever on disk (an empty
    cached file records a page that does not exist / did not fetch, so a rebuild never re-hammers
    the API). Returns '' when unavailable — a coverage gap, never an exception that aborts a
    21-season build."""
    cache_dir = Path(cache_dir or _DEFAULT_CACHE)
    path = _wiki_cache_path(cache_dir, title)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not refresh:
        return path.read_text()
    url = WIKI_API.format(urllib.parse.quote(title.replace(" ", "_"), safe=""))
    req = urllib.request.Request(url, headers={"User-Agent": WIKI_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed https host
            src = json.loads(resp.read()).get("source", "")
    except Exception as exc:  # noqa: BLE001 — a missing page is a coverage gap, not a failure
        log.info("wikitext unavailable for %r (%s)", title, str(exc)[:100])
        src = ""
    path.write_text(src)
    time.sleep(_FETCH_SLEEP_S)
    return src


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Assembly
# ══════════════════════════════════════════════════════════════════════════════════════════════
def build_oc_stints(seasons: list[int], *, cache_dir: str | Path | None = None,
                    refresh: bool = False, current_season: int | None = None) -> pd.DataFrame:
    """OC stints for every (team, season) in `seasons`, read from Wikipedia (cached).

    `current_season` (default: the max requested) reads the LIVE `Template:<Franchise> staff`
    instead of the season article, because a not-yet-played season transcludes that template
    rather than inlining a frozen staff list. ⚠️ The template is only valid for the CURRENT
    season — using it for history would stamp today's staff onto past years, so it is applied to
    exactly one season and its rows are tagged `wikipedia_staff_template`."""
    cur = int(current_season) if current_season is not None else (max(seasons) if seasons else None)
    frames = []
    for season in sorted(int(s) for s in seasons):
        for team in TEAMS:
            title = season_article_title(team, season)
            if not title:
                continue
            src = fetch_wikitext(title, cache_dir=cache_dir, refresh=refresh)
            part = oc_stints_from_wikitext(src, team, season)
            tag = "wikipedia_season_article"
            if part.empty and season == cur:
                tmpl = staff_template_title(team, season)
                if tmpl:
                    src = fetch_wikitext(tmpl, cache_dir=cache_dir, refresh=refresh)
                    part = oc_stints_from_wikitext(src, team, season,
                                                   source="wikipedia_staff_template")
                    tag = "wikipedia_staff_template"
            if not part.empty:
                frames.append(part)
            elif tag:  # nothing parsed — a coverage gap, logged not fabricated
                log.debug("no OC parsed for %s %s", season, team)
    return (pd.concat(frames, ignore_index=True) if frames
            else pd.DataFrame(columns=_STINT_COLS))


def build_coach_stints(seasons: list[int], *, cache_dir: str | Path | None = None,
                       refresh: bool = False, games: pd.DataFrame | None = None,
                       current_season: int | None = None) -> pd.DataFrame:
    """The full stint table (HC from nflverse schedules + OC from Wikipedia) for `seasons`.

    HC history is pulled for EVERY season the schedule covers (not just the requested window) —
    tenure and 'who finished last season' both need the season before the window's floor."""
    g = games if games is not None else fetch_schedule_games(cache_dir=cache_dir, refresh=refresh)
    hc = head_coach_stints(g)
    oc = build_oc_stints(seasons, cache_dir=cache_dir, refresh=refresh,
                         current_season=current_season)
    out = pd.concat([hc, oc], ignore_index=True) if len(oc) else hc
    return out.sort_values(["season", "team", "role", "effective_date"]).reset_index(drop=True)


def build_coach_features(season: int, *, stints: pd.DataFrame | None = None,
                         cache_dir: str | Path | None = None,
                         refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(features, stints) for one projection `season`. When `stints` isn't supplied it is built
    for the seasons the as-of rule can reach (the target season back through the tenure window)."""
    if stints is None:
        lo = int(season) - 12
        stints = build_coach_stints(list(range(lo, int(season) + 1)), cache_dir=cache_dir,
                                    refresh=refresh, current_season=int(season))
    return build_team_coach_features(stints, season), stints


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Serving contract (lake read-through — mirrors contract_source / defense_source / xfp_source)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _read_lake(season: int, source: str) -> pd.DataFrame | None:
    """Read a landed coaching Delta table for `season` from S3, or None when absent/offline."""
    from quant_sports_intel_models.football.nfl.ingest import s3io

    uri = s3io.table_uri(LAKE_SPORT, source, tier=LAKE_TIER)
    con = s3io.duckdb_lake_connection()  # INC-45 — the secret channel `delta_scan` actually reads
    try:
        df = con.sql(f"select * from delta_scan('{uri}') where season = {int(season)}").df()
        return df if not df.empty else None
    except Exception as exc:  # noqa: BLE001 — table absent / offline ⇒ caller computes
        log.info("coaching lake read unavailable (%s/%s: %s) — will compute", source, season,
                 str(exc)[:120])
        return None
    finally:
        con.close()


def load_coach_features(season: int, *, from_lake: bool = True,
                        cache_dir: str | Path | None = None, refresh: bool = False,
                        stints: pd.DataFrame | None = None) -> pd.DataFrame:
    """⭐ THE DELIVERABLE — the leakage-safe per-team coaching-regime features for projecting
    `season` (the same load-and-join contract as `contract_source.load_contract_features` /
    `defense_source.load_forward_defense`).

    Reads the landed Delta `nfl/fantasy/coaching/team_coach_features` for `season` when present,
    else computes from the (cached) sources. `best_alpha = 0` — a projection FEATURE; its lift is
    proven in NF1.5's deflated re-bake-off, not asserted here."""
    if from_lake:
        df = _read_lake(season, LAKE_SOURCE_FEATURES)
        if df is not None:
            return df
    feats, _ = build_coach_features(season, stints=stints, cache_dir=cache_dir, refresh=refresh)
    return feats


def load_coach_stints(season: int, *, from_lake: bool = True,
                      cache_dir: str | Path | None = None, refresh: bool = False) -> pd.DataFrame:
    """The raw stint rows for `season` (effective-dated OC/HC changes) — the audit table behind
    the features, for a leakage review or the weekly model."""
    if from_lake:
        df = _read_lake(season, LAKE_SOURCE_STINTS)
        if df is not None:
            return df
    _, stints = build_coach_features(season, cache_dir=cache_dir, refresh=refresh)
    return stints[stints["season"] == int(season)].reset_index(drop=True)
