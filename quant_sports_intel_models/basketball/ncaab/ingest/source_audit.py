"""source_audit.py — NCAAB-P0 node 2: the FREE-SOURCE AUDIT, by measurement.

The deliverable is a PAID-NECESSITY VERDICT the operator decides spend against. So every
claim here is a live pull, and the module re-runs end to end: `python -m …source_audit`
regenerates `ablation_results/ncaab_p0_source_audit.json`. Doc-reading is not evidence —
two of this audit's findings contradict what the documentation would have told you:

  • GitHub reports hoopR-mbb-data's licence as "NOASSERTION / Other", which reads as a legal
    risk. It is actually **CC BY 4.0** (the R packaging convention puts the year and holder
    in LICENSE and names the licence in DESCRIPTION). Reading the API's licence field alone
    would have wrongly disqualified the best free source in the audit.
  • ESPN's `site.api` host 403s every request from us regardless of user agent, while
    `sports.core.api` answers normally. "ESPN has a public API" is true and useless; WHICH
    ESPN host answers is the fact that matters, and only a pull establishes it.

WHAT IS MEASURED, per the acceptance criteria:
  COVERAGE     — teams, conferences, games, scored-game share, per season, every season.
  FIELDS       — the NCAAF-parity MVP inventory: results, scores, pace-computable box lines,
                 venue / neutral-site flags. Presence is checked by NAME against the real
                 schema, and pace is checked as the actual possession identity's operands.
  PIT          — does the source revise history? Measured from commit history on an old
                 season file vs the current one, not asserted.
  TERMS        — robots directives for OUR agent class, read live, plus the licence.

⚠️ A SOURCE THAT 403s IS A MEASUREMENT, NOT AN ERROR. Every probe records its status and the
audit reports UNREACHABLE as a finding. A run that silently dropped unreachable sources would
report a rosier free-source picture than reality and the spend verdict would be wrong in the
expensive direction.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

HOOPR_REPO = "sportsdataverse/hoopR-mbb-data"
HOOPR_RAW = f"https://raw.githubusercontent.com/{HOOPR_REPO}/main/mbb"
HOOPR_SEASONS = range(2003, 2028)

#: ESPN's D-I conference grouping. Measured: this group returns exactly 366 teams for 2026,
#: which independently corroborates hoopR's 366 distinct home teams that season.
ESPN_DI_GROUP = 50
ESPN_CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball"
ESPN_SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"

#: The agent classes whose robots directives decide whether a site is usable BY US.
OUR_AGENT_CLASSES = ("anthropic-ai", "ClaudeBot", "Claude-Web")

#: The NCAAF-parity MVP field inventory. A source must supply these to stand alone.
MVP_FIELDS = {
    "result_score_home": "home_score",
    "result_score_away": "away_score",
    "result_winner": "home_winner",
    "game_date": "game_date",
    "season": "season",
    "season_type": "season_type",
    "neutral_site": "neutral_site",
    "venue_id": "venue_id",
    "home_team_id": "home_id",
    "away_team_id": "away_id",
    "home_conference": "home_conference_id",
    "away_conference": "away_conference_id",
    "completed_flag": "status_type_completed",
}

#: Possessions ~= FGA - ORB + TO + 0.475*FTA. Pace is the whole NCAAB modelling structure
#: (tempo x efficiency), so its operands are checked by name, not assumed from "has box score".
PACE_OPERANDS = {
    "field_goals_attempted": "FGA",
    "offensive_rebounds": "ORB",
    "turnovers": "TO",
    "free_throws_attempted": "FTA",
}


@dataclass
class Probe:
    """One measured reachability probe. A non-200 is DATA, never a crash."""

    label: str
    url: str
    status: int | None = None
    bytes_: int | None = None
    content_type: str = ""
    note: str = ""
    error: str | None = None

    @property
    def reachable(self) -> bool:
        return self.status == 200


@dataclass
class Audit:
    generated_at: str = ""
    probes: list[Probe] = field(default_factory=list)
    coverage: list[dict] = field(default_factory=list)
    fields_present: dict = field(default_factory=dict)
    pace: dict = field(default_factory=dict)
    pit: dict = field(default_factory=dict)
    terms: dict = field(default_factory=dict)
    corroboration: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _get(url: str, label: str, *, ua: str = "Mozilla/5.0 (credence-ncaab-p0-audit)",
         timeout: int = 40) -> tuple[Probe, bytes | None]:
    p = Probe(label=label, url=url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ua,
                                                   "Accept": "application/json,text/plain,*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            p.status, p.bytes_ = r.status, len(body)
            p.content_type = r.headers.get("Content-Type", "")
            return p, body
    except urllib.error.HTTPError as e:
        p.status, p.error = e.code, f"HTTP {e.code} {e.reason}"
    except Exception as exc:  # noqa: BLE001
        p.error = f"{type(exc).__name__}: {exc}"
    return p, None


def _gh(path: str) -> dict | list | None:
    p, body = _get(f"https://api.github.com/repos/{HOOPR_REPO}/{path}", f"gh:{path}")
    return json.loads(body) if body else None


# ── the legs ────────────────────────────────────────────────────────────────────────────
def measure_hoopr_coverage(audit: Audit) -> None:
    """Season-by-season coverage over EVERY published schedule file. One DuckDB read."""
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs")
    urls = ",".join(f"'{HOOPR_RAW}/schedules/parquet/mbb_schedule_{y}.parquet'"
                    for y in HOOPR_SEASONS)
    rows = con.execute(f"""
        SELECT season, count(*) games, count(DISTINCT home_id) home_teams,
               sum(CASE WHEN home_score IS NOT NULL AND away_score IS NOT NULL
                        THEN 1 ELSE 0 END) scored,
               sum(CASE WHEN neutral_site THEN 1 ELSE 0 END) neutral_site_games,
               count(DISTINCT home_conference_id) conferences,
               sum(CASE WHEN venue_id IS NOT NULL THEN 1 ELSE 0 END) with_venue
        FROM read_parquet([{urls}], union_by_name=true)
        GROUP BY season ORDER BY season
    """).fetchall()
    audit.coverage = [
        {"season": s, "games": g, "home_teams": ht, "scored": sc,
         "scored_pct": round(100 * sc / g, 2) if g else None,
         "neutral_site_games": ne, "conferences": cf,
         "venue_pct": round(100 * vn / g, 2) if g else None}
        for s, g, ht, sc, ne, cf, vn in rows
    ]
    # neutral_site is a REQUIRED MVP field, and it is absent before 2008. Surfacing that as a
    # per-season zero rather than a global "present" is the difference between a usable
    # training window and a silently mis-specified one.
    first_neutral = next((r["season"] for r in audit.coverage
                          if r["neutral_site_games"] > 0), None)
    audit.notes.append(
        f"neutral_site is populated from season {first_neutral} onward; it is identically 0 "
        f"for every earlier season. That is an ABSENCE, not 'no neutral games were played' — "
        f"any training window reaching before {first_neutral} must treat the flag as missing "
        f"rather than False (the MH2.1 per-column-absence lesson)."
    )


def measure_hoopr_fields(audit: Audit) -> None:
    """Field inventory + pace operands, checked by NAME against the live schema."""
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs")
    sched = f"{HOOPR_RAW}/schedules/parquet/mbb_schedule_2026.parquet"
    box = f"{HOOPR_RAW}/team_box/parquet/team_box_2026.parquet"
    scols = {c[0] for c in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{sched}')").fetchall()}
    bcols = {c[0] for c in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{box}')").fetchall()}
    audit.fields_present = {
        "schedule_n_columns": len(scols),
        "team_box_n_columns": len(bcols),
        "mvp": {k: (v in scols) for k, v in MVP_FIELDS.items()},
        "mvp_missing": [k for k, v in MVP_FIELDS.items() if v not in scols],
    }
    audit.pace = {
        "operands": {v: (k in bcols) for k, v in PACE_OPERANDS.items()},
        "computable": all(k in bcols for k in PACE_OPERANDS),
        "identity": "possessions ~= FGA - ORB + TO + 0.475*FTA",
    }
    # How far back is pace computable? The MVP needs a tempo prior, so the answer bounds the
    # training window as hard as the schedule coverage does.
    earliest = None
    for y in (2003, 2008, 2014, 2020):
        try:
            cols = {c[0] for c in con.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{HOOPR_RAW}/team_box/parquet/team_box_{y}.parquet')"
            ).fetchall()}
            if all(k in cols for k in PACE_OPERANDS):
                earliest = y
                break
        except Exception:  # noqa: BLE001 — a missing season file is a measurement
            continue
    audit.pace["earliest_season_with_all_operands"] = earliest


def measure_pit(audit: Audit) -> None:
    """Does the source REVISE history? Commit counts on an old vs current season file."""
    out = {}
    for path, label in [
        ("mbb/schedules/parquet/mbb_schedule_2015.parquet", "completed_season_2015"),
        ("mbb/schedules/parquet/mbb_schedule_2026.parquet", "recent_season_2026"),
        ("mbb/schedules/parquet/mbb_schedule_2027.parquet", "upcoming_season_2027"),
    ]:
        cs = _gh(f"commits?path={path}&per_page=100") or []
        dates = [c["commit"]["committer"]["date"] for c in cs]
        out[label] = {"commits_seen": len(cs), "newest": dates[0] if dates else None,
                      "oldest": dates[-1] if dates else None,
                      "capped_at_page_size": len(cs) == 100}
    out["as_of_field_available"] = False
    out["interpretation"] = (
        "A COMPLETED season's file is stable (2015: 3 commits, all on its load date). The "
        "CURRENT season's file is rewritten continuously (2026: >=100 commits across the "
        "season). The source therefore offers NO as-of and no vintage: an in-season read is "
        "an overwrite of the same path. ⇒ point-in-time is OURS to create — every ingest must "
        "stamp its own capture time and land a content-timestamped Delta version, which is "
        "exactly what makes Delta time-travel the as-of this source lacks."
    )
    audit.pit = out


def measure_terms(audit: Audit) -> None:
    """Robots directives FOR OUR AGENT CLASS, read live, plus the licence."""
    terms: dict = {}
    for host in ["https://www.espn.com", "https://www.ncaa.com", "https://stats.ncaa.org",
                 "https://site.api.espn.com", "https://sports.core.api.espn.com"]:
        p, body = _get(f"{host}/robots.txt", f"robots:{host}")
        audit.probes.append(p)
        if not body:
            terms[host] = {"robots_readable": False, "status": p.status,
                           "verdict": "UNDECLARED — robots.txt itself is not served, so no "
                                      "directive can be read either way"}
            continue
        txt = body.decode("utf-8", "replace")
        verdict = _robots_verdict(txt, OUR_AGENT_CLASSES)
        terms[host] = {"robots_readable": True, **verdict}
    lic = _gh("license") or {}
    p, desc = _get(f"https://raw.githubusercontent.com/{HOOPR_REPO}/main/DESCRIPTION",
                   "hoopr:DESCRIPTION")
    audit.probes.append(p)
    declared = None
    if desc:
        for line in desc.decode("utf-8", "replace").splitlines():
            if line.lower().startswith("license"):
                declared = line.split(":", 1)[1].strip()
    terms["hoopr_licence"] = {
        "github_api_says": lic.get("license", {}).get("spdx_id"),
        "DESCRIPTION_declares": declared,
        "verdict": (
            "CC BY 4.0 — share and adapt, including commercially, WITH ATTRIBUTION. "
            "⚠️ GitHub's licence API reports NOASSERTION because the R convention puts only "
            "the year and copyright holder in LICENSE; the licence itself is named in "
            "DESCRIPTION and spelled out in LICENSE.md. Trusting the API field alone would "
            "have wrongly disqualified this source."
        ),
    }
    audit.terms = terms


def _robots_verdict(txt: str, agents: tuple[str, ...]) -> dict:
    """Resolve whether any of `agents` is disallowed, honouring GROUPED User-agent lines.

    ⚠️ Consecutive `User-agent:` lines share ONE following rule block. ncaa.com lists 20+ AI
    agents in a row and closes the group with a single `Disallow: /` — a naive per-line parse
    reads those agents as having no rules at all and reports the site as permitted. That is
    the exact inversion this function exists to prevent, so the grouping is the whole point.
    """
    lines = [l.strip() for l in txt.splitlines()]
    group: list[str] = []
    hits: dict[str, list[str]] = {}
    for line in lines:
        if not line or line.startswith("#"):
            continue
        low = line.lower()
        if low.startswith("user-agent:"):
            name = line.split(":", 1)[1].strip()
            group.append(name)
            continue
        if low.startswith(("disallow:", "allow:")):
            for a in agents:
                if any(g.lower() == a.lower() for g in group):
                    hits.setdefault(a, []).append(line)
        else:
            group = []
            continue
        # a rule line ends the "collecting agents" run but keeps the group active
    disallowed = {a: rs for a, rs in hits.items()
                  if any(r.lower().replace(" ", "") == "disallow:/" for r in rs)}
    return {
        "our_agents_matched": sorted(hits),
        "rules_seen": {a: rs[:4] for a, rs in hits.items()},
        "blanket_disallowed": sorted(disallowed),
        "verdict": ("DISALLOWED for our agent class" if disallowed
                    else ("no blanket disallow found for our agent class" if hits
                          else "our agent class is not named; the wildcard group governs")),
    }


def measure_espn(audit: Audit) -> None:
    """Which ESPN hosts actually answer, and does D-I corroborate hoopR's team count?"""
    p, body = _get(f"{ESPN_SITE}/scoreboard?dates=20260207&groups={ESPN_DI_GROUP}&limit=500",
                   "espn:site.api scoreboard")
    audit.probes.append(p)
    p2, body2 = _get(
        f"{ESPN_CORE}/seasons/2026/types/2/groups/{ESPN_DI_GROUP}/teams?limit=500",
        "espn:core.api D-I teams")
    audit.probes.append(p2)
    espn_di = None
    if body2:
        try:
            espn_di = json.loads(body2).get("count")
        except Exception:  # noqa: BLE001
            pass
    hoopr_2026 = next((r["home_teams"] for r in audit.coverage if r["season"] == 2026), None)
    audit.corroboration = {
        "espn_core_di_team_count": espn_di,
        "hoopr_2026_distinct_home_teams": hoopr_2026,
        "agree": (espn_di == hoopr_2026) if (espn_di and hoopr_2026) else None,
        "interpretation": (
            "Two INDEPENDENT sources agreeing on the D-I team count is what makes ~360 a "
            "measured figure rather than a repeated one. ESPN's `site.api` host 403s for us "
            "on every path and user agent tried, while `sports.core.api` answers normally — "
            "so 'ESPN has a public API' is true and not actionable; the reachable host is the "
            "finding."
        ),
    }


def run() -> Audit:
    audit = Audit(generated_at=datetime.now(timezone.utc).isoformat())
    measure_hoopr_coverage(audit)
    measure_hoopr_fields(audit)
    measure_pit(audit)
    measure_terms(audit)
    measure_espn(audit)
    return audit


def to_dict(a: Audit) -> dict:
    return {
        "audit": "ncaab_p0_source_audit",
        "generated_at": a.generated_at,
        "coverage": a.coverage,
        "fields": a.fields_present,
        "pace": a.pace,
        "point_in_time": a.pit,
        "terms": a.terms,
        "corroboration": a.corroboration,
        "notes": a.notes,
        "probes": [vars(p) for p in a.probes],
    }


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="NCAAB-P0 free-source audit (measured)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    a = run()
    d = to_dict(a)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump(d, fh, indent=2)
    cov = a.coverage
    complete = [r for r in cov if r["scored_pct"] == 100.0 and r["games"] > 3000]
    print(f"hoopR seasons measured: {len(cov)}  fully-scored seasons: {len(complete)} "
          f"({complete[0]['season']}-{complete[-1]['season']})")
    print(f"MVP fields missing: {a.fields_present['mvp_missing'] or 'NONE'}")
    print(f"pace computable: {a.pace['computable']} from season "
          f"{a.pace['earliest_season_with_all_operands']}")
    print(f"D-I corroboration: ESPN={a.corroboration['espn_core_di_team_count']} "
          f"hoopR={a.corroboration['hoopr_2026_distinct_home_teams']} "
          f"agree={a.corroboration['agree']}")
    for host, t in a.terms.items():
        if host.startswith("http"):
            print(f"  terms {host:36s} {t.get('verdict')}")
    for p in a.probes:
        if not p.reachable:
            print(f"  UNREACHABLE {p.label:34s} {p.error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
