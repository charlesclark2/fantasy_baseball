"""NF-C-LDA-1 — `/fantasy/nfl/draft-assistant` through the REAL ASGI app.

Two properties that only exist end-to-end and that no unit test of `draft_assistant.py` can reach:

  1. 🔒 THE PAID GATE IS SERVER-SIDE. The extension decides nothing about entitlement; an
     unentitled caller must get a 403 from the API no matter what its UI does (E9.45 — a
     client-side gate on a paid feature is not a gate).
  2. ⭐ THE RESPONSE NAMES THE PICK IT REASONED ABOUT. That is the story's break-detection
     contract, and it has to survive Pydantic serialization — the E9.41 class, where a served field
     was silently STRIPPED because the response model never declared it and the store had been
     right all along.

Raw ASGI rather than `TestClient`, for the two reasons the E9.56/freemium suites document: no
`httpx` here, and `TestClient` cannot set the `aws.event` scope key Mangum uses to carry the API
Gateway authorizer context — which is the one thing separating a real subscriber from a forged
token.

⛔ ANCHORED IN ITS OWN CLAUSE (E9.60).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).parent / "fixtures"
_SOURCE = json.loads((_FIXTURES / "nf_c_lda_1_optimizer_parity_input.json").read_text())

#: A small but REAL slice of the published board — the endpoint scores it through the shipped
#: `league_scoring.build_board`, so the rows must carry what the scorer reads.
_PROJECTIONS = json.loads(
    (Path(__file__).parent.parent.parent
     / "quant_sports_intel_models/football/nfl/fantasy/artifacts/player_history_json/2026"
     / "projections.json").read_text()
)

#: The real ESPN capture's own settings block — the path a mock draft takes, where there is no
#: saved league to name.
_ESPN = json.loads((_FIXTURES / "espn_league_642070_2025_drafted.json").read_text())
_SETTINGS = {
    "name": "Test League",
    "size": 12,
    "rosterSettings": _ESPN["settings"]["rosterSettings"],
    "scoringSettings": _ESPN["settings"].get("scoringSettings") or {"scoringItems": []},
}


def _pool(n: int = 60) -> list[dict]:
    out = []
    for team in _ESPN["teams"]:
        for entry in (team.get("roster") or {}).get("entries") or []:
            player = (entry.get("playerPoolEntry") or {}).get("player") or entry.get("player")
            if player:
                out.append({k: player.get(k) for k in
                            ("id", "fullName", "proTeamId", "defaultPositionId", "eligibleSlots")})
    return out[:n]


def _body(**over) -> dict:
    pool = _pool()
    body = {
        "season": 2026,
        "espn_settings": _SETTINGS,
        "pool": pool,
        "picks": [{"team": "3", "player": str(p["id"])} for p in pool[:6]],
        "my_team": "14",
        "on_the_clock_team": "14",
        "overall_pick": 7,
        "top_n": 5,
    }
    body.update(over)
    return body


@pytest.fixture()
def app_env(monkeypatch):
    from app.backend.routers import fantasy
    from app.backend.services import cost_guardrails, jwt_verify

    # The per-IP limiter is process-global and stateful across FILES; a depleted bucket surfaces as
    # payload-shape failures rather than as throttling (the freemium suite's measured lesson).
    cost_guardrails.get_limiter().reset()

    def fake_load(rel_key: str, sport: str = "nfl"):
        return _PROJECTIONS if rel_key.endswith("projections.json") else None

    monkeypatch.setattr(fantasy, "_load_json", fake_load)
    fantasy._full_projections_memo.clear()
    monkeypatch.setattr(jwt_verify, "_fetch_jwks", lambda: None)
    jwt_verify.reset_jwks_cache()
    return True


def _post(path: str, payload: dict, *, aws_event: dict | None = None):
    import anyio

    from app.backend.main import app

    raw = json.dumps(payload).encode()
    out: dict = {}
    parts: list[bytes] = []

    async def run():
        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.1"},
            "http_version": "1.1", "method": "POST", "scheme": "https",
            "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
            "headers": [(b"host", b"testserver"), (b"content-type", b"application/json"),
                        (b"content-length", str(len(raw)).encode())],
            "client": ("test", 1), "server": ("testserver", 443),
        }
        if aws_event is not None:
            scope["aws.event"] = aws_event

        async def receive():
            return {"type": "http.request", "body": raw, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                out["status"] = message["status"]
            elif message["type"] == "http.response.body":
                parts.append(message.get("body", b""))

        await app(scope, receive, send)

    anyio.run(run)
    return out["status"], b"".join(parts)


def _entitled(groups: str = "[subscriber]"):
    return {"requestContext": {"authorizer": {"jwt": {"claims": {
        "sub": "sub-1", "cognito:groups": groups}}}}}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The gate
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_an_anonymous_caller_is_refused(app_env):
    status, _ = _post("/fantasy/nfl/draft-assistant", _body())
    assert status in (401, 403), f"an anonymous draft request returned {status}"


def test_a_signed_in_free_account_is_refused(app_env):
    """⭐ THE ONE THAT MATTERS. Anonymous is refused by almost anything; a FREE account with a real
    Cognito session is the caller a client-side gate lets through."""
    status, body = _post("/fantasy/nfl/draft-assistant", _body(), aws_event=_entitled("[]"))
    assert status == 403, f"a free account got {status}: {body[:300]!r}"


def test_a_subscriber_is_served(app_env):
    status, body = _post("/fantasy/nfl/draft-assistant", _body(), aws_event=_entitled())
    assert status == 200, f"a subscriber got {status}: {body[:400]!r}"
    data = json.loads(body)
    assert data["recommendations"], "a subscriber got an empty recommendation list"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The response contract
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_response_names_the_pick_it_reasoned_about(app_env):
    """⭐ BREAK DETECTION'S SERVER HALF. Without this echo the overlay cannot show which pick the
    advice is for, and a frozen read is indistinguishable from a quiet draft."""
    status, body = _post("/fantasy/nfl/draft-assistant", _body(), aws_event=_entitled())
    assert status == 200
    state = json.loads(body)["state"]
    assert state["overall_pick"] == 7, "the pick number was not echoed back"
    assert state["on_the_clock_team"] == "14"
    assert state["on_the_clock_is_me"] is True
    assert state["picks_seen"] == 6
    assert state["my_team_known"] is True


def test_an_unknown_team_is_reported_rather_than_rendered_as_an_empty_roster(app_env):
    """`my_team_known` is the difference between "you have not picked yet" and "we could not tell
    which team is yours" — two states that look identical on screen (NF1.7(a))."""
    status, body = _post("/fantasy/nfl/draft-assistant", _body(my_team=None),
                         aws_event=_entitled())
    assert status == 200
    data = json.loads(body)
    assert data["state"]["my_team_known"] is False
    assert data["state"]["on_the_clock_is_me"] is False
    assert data["my_roster"] == [], "a roster appeared for a team we cannot identify"
    assert data["recommendations"], "the board should still rank even without a team"


def test_the_resolution_report_travels_with_the_answer(app_env):
    """A player we could not resolve is not recommendable, and the three causes stay apart
    (NF-K1)."""
    status, body = _post("/fantasy/nfl/draft-assistant", _body(), aws_event=_entitled())
    assert status == 200
    report = json.loads(body)["resolution"]
    assert report["considered"] > 0, "the report claims nothing was even considered"
    assert report["resolved"] > 0
    assert report["tier1"] == "not_attempted"
    assert isinstance(report["unresolved_by_cause"], dict)


def test_the_recommendations_carry_their_reason(app_env):
    """The SAME sentence the web app shows — it comes from the same engine function, pinned by
    `test_nf_c_lda_1_optimizer_parity.py`."""
    status, body = _post("/fantasy/nfl/draft-assistant", _body(), aws_event=_entitled())
    assert status == 200
    for rec in json.loads(body)["recommendations"]:
        assert rec["why"], f"{rec['name']} was recommended with no reason"
        assert rec["player_id"] and rec["pos"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Input handling
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_naming_both_league_sources_is_refused(app_env):
    status, _ = _post("/fantasy/nfl/draft-assistant",
                      _body(league_id="abc"), aws_event=_entitled())
    assert status == 422, "a request naming BOTH a saved league and inline settings was accepted"


def test_naming_neither_league_source_is_refused(app_env):
    status, _ = _post("/fantasy/nfl/draft-assistant",
                      _body(espn_settings=None), aws_event=_entitled())
    assert status == 422


def test_an_unknown_field_is_refused_rather_than_ignored(app_env):
    """⛔ `extra="forbid"`. An accepted-but-ignored field is how a silently-dropped save happens
    (E8.6), and here it is also the property that makes "we only ever receive these fields"
    checkable rather than merely intended."""
    body = _body()
    body["espn_s2"] = "AEBmarPuDdT1x9K7"
    status, _ = _post("/fantasy/nfl/draft-assistant", body, aws_event=_entitled())
    assert status == 422, "the endpoint accepted a field the contract does not declare"


def test_an_oversized_pool_is_refused(app_env):
    body = _body()
    body["pool"] = body["pool"] * 200
    status, _ = _post("/fantasy/nfl/draft-assistant", body, aws_event=_entitled())
    assert status == 422, "an unbounded pool reached the join"
