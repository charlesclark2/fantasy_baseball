"""NF-WVR1 fact columns — realized 2026 production-to-date on the FA pool (PM ruling Q4, ⑮, ⑯ = b).

⛔ ANCHORED IN ITS OWN CLAUSES (the E9.60 coupling trap). Each test names the defect it prevents.

⭐ THE LINEAGE CLAUSES START FROM THE STORED WEEK 1, NOT A HAND-WRITTEN FIXTURE.
`fixtures/nf_wk_rc1_realized_2026_wk1_stored.json.gz` is the served week-1 artifact (RC1's anchor),
and the season artifact under test is built from it by RC1's OWN builder — so the backend verifier
twin is checked against what the publisher actually writes, not against this file's idea of it.
"""

from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path

import pytest

from app.backend.services import league_scoring, waiver_facts

_FIXTURE = Path(__file__).parent / "fixtures" / "nf_wk_rc1_realized_2026_wk1_stored.json.gz"

PPR = {"pass_yds": 0.04, "pass_td": 4, "pass_int": -2, "rush_yds": 0.1, "rush_td": 6, "rec": 1,
       "rec_yds": 0.1, "rec_td": 6, "two_pt": 2, "fumbles_lost": -2, "st_td": 6}
CFG = {"n_teams": 12, "scoring": {"per_stat": PPR}, "roster": []}


def _week(week: int) -> tuple[dict, list[dict]]:
    fx = json.loads(gzip.decompress(_FIXTURE.read_bytes()))
    players = [dict(zip(fx["columns"], r)) for r in fx["rows"]]
    for p in players:
        p["week"] = week
        p["game_id"] = p["game_id"].replace("_01_", f"_{week:02d}_")
    man = {**copy.deepcopy(fx["manifest"]), "week": week, "completeness": "final"}
    return man, players


def _season(weeks=(1,), *, gap_after=None) -> tuple[dict, dict]:
    """RC1's own builder over the stored week, re-served as the two JSON objects the API reads."""
    RW = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.realized_week")
    served = {}
    for w in weeks:
        man, players = _week(w)
        served[w] = ({**man, "content_sha256": RW.content_hash(players)}, players)
    if gap_after is not None:
        man, players = _week(gap_after)
        served[gap_after] = ({**man, "completeness": "partial",
                              "content_sha256": RW.content_hash(players)}, players)
    built = RW.build_season(2026, served)
    body = {"encoding": RW.SEASON_ENCODING, "columns": built["columns"], "rows": built["rows"],
            "generated_at": built["manifest"]["generated_at"]}
    # Through JSON, exactly as S3 serves it — the hash must survive the round trip.
    return (json.loads(json.dumps(built["manifest"], default=str)),
            json.loads(json.dumps(body, default=str)))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1 — THE LINEAGE CHECK IS A FAITHFUL TWIN OF THE PUBLISHER'S
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_verifier_accepts_what_the_real_builder_publishes():
    """THE DEFECT: a twin hash definition that drifted from `build_season` would reject EVERY real
    artifact and silently turn the fact columns off for every user."""
    man, body = _season((1, 2))
    assert waiver_facts.verify_season(man, body) == []


@pytest.mark.parametrize("mutate, needle", [
    (lambda m, b: b["rows"][17].__setitem__(b["columns"].index("passing_yards"), 999),
     "content_sha256"),
    (lambda m, b: m["sources"][0].__setitem__("content_sha256", "0" * 64), "source_fingerprint"),
    (lambda m, b: m.__setitem__("weeks", [1, 3]), "weeks"),
    (lambda m, b: m.__setitem__("through_week", 1), "through_week"),
    (lambda m, b: m.__setitem__("n_rows", m["n_rows"] - 1), "n_rows"),
    (lambda m, b: m.__setitem__("encoding", "rows-v0"), "encoding"),
])
def test_a_single_broken_lineage_property_is_refused(mutate, needle):
    """Each lineage property, broken alone, must be refused and NAMED — a verifier that passes a
    tampered cell would attach numbers no published week supports."""
    man, body = _season((1, 2))
    mutate(man, body)
    violations = waiver_facts.verify_season(man, body)
    assert violations, "a broken artifact was accepted"
    assert any(needle in v for v in violations), violations


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2 — WHAT GETS SUMMED
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_league_scored_facts_match_the_sources_own_ppr_under_a_ppr_league():
    """An INDEPENDENT correctness anchor (not our join, not our scorer's own output): under plain
    full-PPR, every non-kicker's season total must equal nflverse's `fantasy_points_ppr` sum."""
    man, body = _season((1, 2))
    facts = waiver_facts.season_facts(man, body, CFG)
    cols = body["columns"]
    ppr: dict[str, float] = {}
    for r in body["rows"]:
        d = dict(zip(cols, r))
        ppr[d["player_id"]] = ppr.get(d["player_id"], 0.0) + (d["fantasy_points_ppr"] or 0.0)
    scored = [a for a in facts["by_id"].values() if a["pos"] != "K"]
    assert len(scored) > 300, "the sum ran over too few players to mean anything"
    bad = [a["name"] for a in scored if abs(a["points"] - ppr[a["player_id"]]) > 1e-6]
    assert bad == []
    assert all(a["games"] == 2 and a["weeks"] == [1, 2] for a in scored)


def test_only_the_covered_run_of_weeks_is_summed():
    """THE DEFECT: summing every row present (or a later excluded week) presents a partial season
    as complete. A partial week 2 is listed in `excluded` by the builder and must add nothing."""
    man, body = _season((1,), gap_after=2)
    assert man["weeks"] == [1] and man["excluded"][0]["week"] == 2
    facts = waiver_facts.season_facts(man, body, CFG)
    assert all(a["weeks"] == [1] for a in facts["by_id"].values())

    # …and a row from an uncovered week that DID reach the rows file is still not summed.
    # ⚠️ The injected row must be one the POSITION filter keeps (a WR who scored), or the position
    # filter — not the week filter — is what drops it and this clause is vacuous (the RED proof
    # caught exactly that: the artifact's first row is a safety).
    cols = body["columns"]
    extra = list(next(r for r in body["rows"] if r[cols.index("position")] == "WR"
                      and (r[cols.index("fantasy_points_ppr")] or 0) > 5))
    extra[cols.index("week")] = 2
    body2 = {**body, "rows": body["rows"] + [extra]}
    facts2 = waiver_facts.season_facts(man, body2, CFG)
    assert facts2["by_id"] == facts["by_id"]


def test_two_identical_weeks_sum_to_twice_one_week():
    """The aggregate is a SUM over covered games — not the latest week, not an average."""
    man, body = _season((1, 2))
    facts = waiver_facts.season_facts(man, body, CFG)
    pid, agg = next((k, v) for k, v in facts["by_id"].items() if v["pos"] == "WR" and v["points"])
    single = waiver_facts.season_facts(*_season((1,)), CFG)["by_id"][pid]["points"]
    assert agg["points"] == pytest.approx(2 * single)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3 — THE FACT CELL: absences are stated, never zeros; no projection is ever read
# ══════════════════════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def facts():
    return waiver_facts.season_facts(*_season((1,)), CFG)


def _named(facts, pos):
    return next(a for a in facts["by_id"].values() if a["pos"] == pos and a["points"] > 5)


def test_a_team_defence_is_a_stated_team_grain_absence_never_a_zero(facts):
    """NF-C6b / NF-K1 + ruling ⑮: "no facts for this defence" must not read as "did nothing"."""
    cell = waiver_facts.fact_for({"id": "DST-DET", "name": "DET D/ST", "pos": "DST", "team": "DET"},
                                 facts)
    assert cell == {"points": None, "games": None, "absence": "team_grain_not_covered"}


def test_a_player_with_no_line_is_a_stated_absence_never_a_zero(facts):
    cell = waiver_facts.fact_for({"id": "NF-ROOKIE-1", "name": "Nobody Atall", "pos": "WR",
                                  "team": "DET"}, facts)
    assert cell["points"] is None and cell["absence"] == "no_realized_line"


def test_the_projection_is_never_substituted_for_a_missing_fact(facts):
    """THE ABSOLUTE RULE: a board row's preseason `fpPpr` must never appear as a realized number."""
    row = {"id": "NF-X", "name": "Nobody Atall", "pos": "QB", "team": "CLE", "fpPpr": 268.3,
           "fpStd": 250.0, "fpHalf": 259.0, "pts": 268.3}
    assert waiver_facts.fact_for(row, facts)["points"] is None
    # ⚠️ AST, not text: the module's own docstring NAMES `fpPpr` while forbidding it, so a text scan
    # is red on correct code (and a comment-only strip would still see the docstring).
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(waiver_facts))
    docstrings = {
        id(n.body[0].value) for n in ast.walk(tree)
        if isinstance(n, (ast.Module, ast.FunctionDef)) and n.body
        and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)
    }
    literals = {n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in docstrings}
    # (`"pts"` is deliberately not listed: it is `score_row`'s OWN output key, read on purpose.
    # The behavioural assertion above covers a row-level `pts`.)
    for field in ("fpPpr", "fpStd", "fpHalf", "fpP10", "fpP90", "fpSd", "g"):
        assert field not in literals, f"waiver_facts reads the projection field {field!r}"


def test_the_id_rung_recovers_a_name_alias(facts):
    """Measured on the live board: `Joshua Palmer` (board) vs `Josh Palmer` (realized), same gsis id.
    The name join alone leaves a scoring player reading as having no line."""
    real = _named(facts, "WR")
    alias = {"id": real["player_id"], "name": real["name"] + " Jr. The Third", "pos": "WR",
             "team": real["team"]}
    assert league_scoring._join_key(alias["name"], "WR", alias["team"]) not in facts["by_key"]
    assert waiver_facts.fact_for(alias, facts)["points"] == pytest.approx(real["points"])


def test_a_synthetic_id_still_joins_by_name(facts):
    """The rookie class carries non-gsis ids; the id rung must not cost them the name join."""
    real = _named(facts, "RB")
    rookie = {"id": "NF-ROOKIE-42", "name": real["name"], "pos": "RB", "team": real["team"]}
    assert waiver_facts.fact_for(rookie, facts)["points"] == pytest.approx(real["points"])


def test_an_id_match_at_a_different_position_is_not_trusted(facts):
    real = _named(facts, "WR")
    wrong = {"id": real["player_id"], "name": "Someone Else", "pos": "QB", "team": real["team"]}
    assert waiver_facts.fact_for(wrong, facts)["absence"] == "no_realized_line"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4 — ORDERING
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_within_a_position_facts_order_high_first_and_the_rest_keep_board_order():
    ps = [
        {"name": "A", "realized": {"points": None}},
        {"name": "B", "realized": {"points": 3.0}},
        {"name": "C", "realized": {"points": None}},
        {"name": "D", "realized": {"points": 9.5}},
        {"name": "E", "realized": {"points": 3.0}},
    ]
    assert [p["name"] for p in waiver_facts.order_group(ps)] == ["D", "B", "E", "A", "C"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5 — THE ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════════════════════

ROSTER = [
    {"name": "QB", "count": 1, "eligible": ["QB"], "bench": False},
    {"name": "WR", "count": 2, "eligible": ["WR"], "bench": False},
    {"name": "DST", "count": 1, "eligible": ["DST"], "bench": False},
    {"name": "BN", "count": 4, "eligible": ["QB", "WR"], "bench": True},
]


def _record():
    return {
        "league_id": "L1", "sport": "nfl", "source_platform": "sleeper", "n_teams": 2,
        "scoring": {"per_stat": PPR}, "roster": ROSTER, "imported_roster": [],
        "league_rosters": [{"team_key": "1", "team_name": "A", "players": []},
                           {"team_key": "2", "team_name": "B", "players": []}],
        "league_rosters_truncated": False, "league_rosters_synced_at": "2026-09-17T00:00:00Z",
    }


def _board_from(facts):
    """Board rows for real realized players — plus a high-projection no-line QB (the Mendoza row)."""
    rows = []
    for pos in ("WR", "QB"):
        picked = [a for a in facts["by_id"].values() if a["pos"] == pos][:6]
        for a in picked:
            rows.append({"id": a["player_id"], "name": a["name"], "pos": pos, "team": a["team"],
                         "fpPpr": 100.0, "fpSd": 10.0, "fpP10": 80.0, "fpP90": 120.0, "g": 17})
    rows.insert(0, {"id": "NF-M", "name": "Nobody Atall", "pos": "QB", "team": "CLE",
                    "fpPpr": 268.3, "fpSd": 30.0, "fpP10": 220.0, "fpP90": 300.0, "g": 17})
    rows.append({"id": "DST-DET", "name": "DET D/ST", "pos": "DST", "team": "DET",
                 "fpPpr": 110.0, "fpSd": 10.0, "fpP10": 90.0, "fpP90": 130.0, "g": 17})
    return rows


@pytest.fixture()
def endpoint(monkeypatch, facts):
    from starlette.requests import Request

    from app.backend.routers import fantasy

    man, body = _season((1,))
    served = {"manifest": man, "body": body}
    monkeypatch.setattr(fantasy, "_realized_season_memo", {})
    monkeypatch.setattr(fantasy.dynamo, "list_fantasy_leagues", lambda uid: [_record()])
    monkeypatch.setattr(fantasy.entitlement, "resolve_entitlement", lambda req: "subscriber")
    monkeypatch.setattr(fantasy.entitlement, "personalized_league_quota", lambda ent: 25)
    monkeypatch.setattr(fantasy, "_full_projections",
                        lambda season: {"players": _board_from(facts)})

    def load(rel):
        if rel.endswith("season/manifest.json"):
            return served["manifest"]
        if rel.endswith("season/players.json"):
            return served["body"]
        return None

    monkeypatch.setattr(fantasy, "_load_json", load)
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": [],
                   "query_string": b""})

    def call():
        return fantasy.nfl_waiver_pool(request=req, league_id="L1", season=2026, refresh=False,
                                       user_id="u1")

    return call, served, fantasy


def _group(out, pos):
    return next(g for g in out["pool"] if g["pos"] == pos)


def test_the_payload_orders_by_realized_facts_and_states_the_basis(endpoint):
    call, _, _ = endpoint
    out = call()
    assert out["ordering"] == "realized_to_date"
    assert "week 1" in out["ordering_note"] and "not a forecast" in out["ordering_note"]
    assert out["realized"]["absence"] is None and out["realized"]["weeks"] == [1]
    qb = _group(out, "QB")
    assert qb["ordering"] == "realized_to_date"
    pts = [p["realized"]["points"] for p in qb["players"]]
    with_facts = [x for x in pts if x is not None]
    assert with_facts == sorted(with_facts, reverse=True) and with_facts
    # The Mendoza row — top of the board by projection — has no line and sorts LAST, never first.
    assert qb["players"][-1]["name"] == "Nobody Atall"
    assert qb["players"][-1]["realized"] == {"points": None, "games": 0,
                                             "absence": "no_realized_line"}


def test_the_defence_group_stays_unranked_with_its_specific_reason(endpoint):
    call, _, _ = endpoint
    dst = _group(call(), "DST")
    assert dst["ordering"] == "unranked"
    assert dst["facts_absence"] == "team_grain_not_covered"
    assert dst["players"][0]["realized"]["absence"] == "team_grain_not_covered"


def test_an_excluded_week_is_carried_as_a_stated_gap(endpoint):
    call, served, _ = endpoint
    served["manifest"], served["body"] = _season((1,), gap_after=2)
    out = call()
    assert out["realized"]["excluded"] == [{"week": 2, "reason": "not_final"}]
    assert out["realized"]["through_week"] == 1


def test_no_artifact_falls_back_to_the_stated_unranked_listing(endpoint):
    call, served, _ = endpoint
    served["manifest"] = None
    out = call()
    assert out["ordering"] == "unranked"
    assert out["realized"]["absence"] == "realized_not_published"
    assert all(g["ordering"] == "unranked" and g["facts_absence"] == "realized_not_published"
               for g in out["pool"])
    assert all(p["realized"] is None for g in out["pool"] for p in g["players"])


def test_a_tampered_artifact_withholds_the_facts_and_is_not_cached(endpoint):
    """A read that fails lineage must withhold every fact — and must not be memoized, or a
    request landing between RC1's two writes would switch the facts off for the whole TTL."""
    call, served, fantasy = endpoint
    good = copy.deepcopy(served["body"])
    served["body"]["rows"][3][served["body"]["columns"].index("receiving_yards")] = 777
    out = call()
    assert out["realized"]["absence"] == "realized_lineage_unverified"
    assert out["ordering"] == "unranked"
    assert fantasy._realized_season_memo == {}
    served["body"] = good
    assert call()["realized"]["absence"] is None


def test_the_payload_key_registry_names_the_new_block():
    from app.backend.routers import fantasy
    assert "realized" in fantasy.WAIVER_PAYLOAD_KEYS


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6 — FRESHNESS: a waiver claim made after the stored snapshot must change the pool
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_a_refreshed_roster_removes_a_player_the_stale_snapshot_still_listed(endpoint, monkeypatch):
    """THE DEFECT the whole refresh exists for: an FA pool from a stale snapshot offers a player who
    was claimed since — "the worst output this feature can produce". The stored rosters are empty
    (every board player available); the platform now reports one of them on a team."""
    call, _, fantasy = endpoint
    stale = call()
    qb = next(g for g in stale["pool"] if g["pos"] == "QB")
    claimed = next(p for p in qb["players"] if p["realized"]["points"] is not None)

    from app.backend.services.platform_import import sleeper

    fresh = [{"team_key": "1", "team_name": "A",
              "players": [{"name": claimed["name"], "position": "QB", "team": claimed["team"]}]},
             {"team_key": "2", "team_name": "B", "players": []}]
    monkeypatch.setattr(sleeper, "refresh_league_rosters",
                        lambda lid: {"rosters": fresh, "synced_at": "2026-09-17T12:00:00+00:00"})
    monkeypatch.setattr(fantasy.dynamo, "put_fantasy_league", lambda *a, **k: None)
    rec = {**_record(), "source_league_id": "999"}
    monkeypatch.setattr(fantasy.dynamo, "list_fantasy_leagues", lambda uid: [rec])

    from starlette.requests import Request
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""})
    out = fantasy.nfl_waiver_pool(request=req, league_id="L1", season=2026, refresh=True, user_id="u1")
    assert out["rosters"]["refreshed"] is True
    names = {p["name"] for g in out["pool"] for p in g["players"]}
    assert claimed["name"] not in names, "a player claimed since the snapshot is still offered"
    assert len(names) == sum(len(g["players"]) for g in stale["pool"]) - 1
