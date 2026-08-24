"""NCAAF-P3.1 — guards for the serving plumbing (contract, writer, router).

WHAT EACH GROUP IS DEFENDING, because a guard whose purpose is not stated is the one that gets
weakened later to make a build green:

  §1 THE CONTRACT      — no pick/edge field can EXIST in the served schema, and the served token
                         list cannot fork from the lake-row one it mirrors.
  §2 ABSENT vs NULL    — a declared field is always on the wire (null included); a missing game is
                         a 404, never an empty-but-successful body.
  §3 THE E9.41 PROOF   — a REAL serialized payload round-trips the actual FastAPI app with every
                         field intact. Driven through the ASGI interface, not by calling the route
                         function: `response_model` filtering happens in the app layer, so a test
                         that calls the function directly is structurally incapable of catching the
                         silent-drop this exists to catch.
  §4 INC-22 / THE WEEK — the serving grain is the America/Los_Angeles kickoff day, and nothing in
                         the serving layer keys on CFBD's restarting week.
  §5 THE WRITER        — both stores, the HALT tier, and "nothing to write" as a no-op.
  §6 PUBLIC + FREE     — no entitlement dependency, and NCAAF is in the degrade floor + the public
                         cache rules (a new public surface that joins neither undoes G100-D1).

Pure/offline (fast gate): no boto3, no lake, no network. Every store is a fake.
"""
from __future__ import annotations

import ast
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from pydantic import BaseModel

from app.backend.models import ncaaf as contract
from app.backend.routers import ncaaf as ncaaf_router
from app.backend.services import cost_guardrails, ncaaf_serving
from quant_sports_intel_models.football.ncaaf.serving import payloads

_REPO = Path(__file__).resolve().parents[2]
_SERVING_SOURCES = (
    _REPO / "app/backend/models/ncaaf.py",
    _REPO / "app/backend/routers/ncaaf.py",
    _REPO / "app/backend/services/ncaaf_serving.py",
    _REPO / "quant_sports_intel_models/football/ncaaf/serving/payloads.py",
    _REPO / "scripts/write_ncaaf_serving_store.py",
    _REPO / "pipeline/jobs/sports_ncaaf_serving_write_job.py",
    _REPO / "pipeline/schedules/sports_ncaaf_serving_write_schedules.py",
)


# ══════════════════════════════════════════════════════════════════════════════════════════
# Fixtures — a snapshot frame shaped exactly like what NCAAF-PS persists
# ══════════════════════════════════════════════════════════════════════════════════════════

def _snapshot_row(game_id: int, commence: str, snapshot_ts: str, *, p_home: float = 0.62):
    row = {
        "season": 2026, "game_id": game_id, "snapshot_ts": snapshot_ts,
        "snapshot_kind": "pre_kickoff", "commence_time": commence, "lead_minutes": 4320.0,
        "start_time_tbd": False, "cfbd_week": 1, "season_type": "regular",
        "home_team_id": 194, "home_team": "Ohio State", "home_conference": "Big Ten",
        "away_team_id": 2050, "away_team": "Ball State", "away_conference": "Mid-American",
        "is_neutral_site": False, "is_conference_game": False,
        "p_home_win": p_home,
        "mu_margin": 40.4, "sigma_margin": 16.2,
        "mu_total": 55.1, "sigma_total": 12.9,
        "margin_interval_width": 41.5, "total_interval_width": 33.0,
        "strength_as_of_week": 1,
        "home_strength_margin": 22.1, "home_strength_margin_sd": 3.2,
        "away_strength_margin": -18.3, "away_strength_margin_sd": 4.1,
        "home_strength_games_in_window": 12.0, "away_strength_games_in_window": 12.0,
        "pace_term_active": False, "n_draws": 20000,
        "model_version": "ncaaf_game_v2", "model_form": "student_t", "model_learner": "ridge",
        "model_contract": "strength_pace", "mean_artifact_version": "v2",
        "framing": "market_blind_projection", "best_alpha": 0.0,
    }
    for i, level in enumerate(payloads.QUANTILE_LEVELS):
        row[payloads._q_col("margin", level)] = 40.4 + (i - 3) * 10.0
        row[payloads._q_col("total", level)] = 55.1 + (i - 3) * 8.0
    return row


@pytest.fixture()
def snapshots() -> pd.DataFrame:
    """Two games on two DIFFERENT LA game-days, one of which has TWO vintages.

    The second vintage is load-bearing for §5's latest-wins test: an append-only table legitimately
    holds several snapshots of the same game, and serving must publish the NEWEST.
    """
    return pd.DataFrame([
        _snapshot_row(401628319, "2026-08-29T16:00:00.000Z", "2026-08-25T16:00:00.000Z", p_home=0.51),
        _snapshot_row(401628319, "2026-08-29T16:00:00.000Z", "2026-08-27T16:00:00.000Z", p_home=0.62),
        # 03:30 UTC on the 30th = 20:30 PT on the 29th — a SATURDAY game. The UTC date says Sunday.
        _snapshot_row(401628320, "2026-08-30T03:30:00.000Z", "2026-08-27T16:00:00.000Z", p_home=0.44),
    ])


@pytest.fixture()
def futures_rows() -> pd.DataFrame:
    return pd.DataFrame([
        {"season": 2026, "team_id": 194, "team": "Ohio State", "conference": "Big Ten",
         "snapshot_ts": "2026-08-27T16:00:00.000Z", "snapshot_kind": "pre_kickoff",
         "strength_margin": 22.1, "strength_margin_sd": 3.2, "exp_wins": 10.4, "exp_losses": 1.6,
         "conf_title_available": True, "p_conf_title": 0.31, "p_playoff": 0.72,
         "p_top_seed": 0.28, "p_reach_final": 0.19, "p_natty": 0.11, "n_sims": 10000,
         "strength_as_of_week": 1, "model_version": "ncaaf_game_v2",
         "model_contract": "strength_pace", "framing": "market_blind_projection", "best_alpha": 0.0},
        {"season": 2026, "team_id": 2050, "team": "Ball State", "conference": "Mid-American",
         "snapshot_ts": "2026-08-27T16:00:00.000Z", "snapshot_kind": "pre_kickoff",
         "strength_margin": -18.3, "strength_margin_sd": 4.1, "exp_wins": 4.1, "exp_losses": 7.9,
         "conf_title_available": True, "p_conf_title": 0.04, "p_playoff": 0.001,
         "p_top_seed": 0.0, "p_reach_final": 0.0, "p_natty": 0.0, "n_sims": 10000,
         "strength_as_of_week": 1, "model_version": "ncaaf_game_v2",
         "model_contract": "strength_pace", "framing": "market_blind_projection", "best_alpha": 0.0},
    ])


def _code_only(src: str) -> str:
    """Source with every COMMENT and every STRING LITERAL removed — executable code only.

    INC-38: a source-inspection guard a COMMENT can satisfy is not a guard. Every module in this
    story documents at length WHY it must not use `season_order_week`, so a naive substring scan
    would be satisfied by the explanation and would stay green with the real usage present.
    Tokenising (rather than regexing `#` out) is what makes it robust: a `#` inside a docstring
    would otherwise corrupt the docstring and defeat a subsequent replace.
    """
    import io
    import tokenize

    kept = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        kept.append(tok.string)
    return " ".join(kept)


def _code_squashed(src: str) -> str:
    """`_code_only` with all whitespace removed — for asserting on a dotted CALL, which tokenising
    otherwise splits into `a . b (`."""
    return re.sub(r"\s+", "", _code_only(src))


def test_the_code_only_scan_actually_removes_prose():
    """Positive control for the scanner every source guard below depends on. Without it, "the token
    is absent" could mean "the scanner returned nothing"."""
    src = '''"""a docstring mentioning season_order_week."""
# a comment mentioning season_order_week
x = 1  # trailing season_order_week
'''
    stripped = _code_only(src)
    assert "season_order_week" not in stripped
    assert "x" in stripped and "=" in stripped, "the scanner ate the code too"


# ══════════════════════════════════════════════════════════════════════════════════════════
# §1 The contract
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_no_pick_or_edge_field_exists_in_the_served_schema():
    """The whole posture, as a schema property: `best_alpha=0` and the CLV null mean a pick column
    would assert what the evidence does not support."""
    contract.assert_no_edge_claim_in_schema()  # raises if any model declares one


def test_the_edge_claim_guard_actually_catches_one():
    """The positive control. A guard that cannot FAIL is worse than no guard (NF1.7 (a))."""
    class Sneaky(BaseModel):
        best_pick: str | None = None

    with pytest.raises(ValueError, match="edge/pick claim"):
        contract.assert_no_edge_claim_in_schema((Sneaky,))


def test_the_contract_model_registry_is_exhaustive():
    """Every `BaseModel` declared in the contract module is in `CONTRACT_MODELS`.

    Without this, a model added to the file but not the tuple escapes the edge-claim walk entirely
    — the guard would pass on nothing (the vacuity class).
    """
    declared = {
        obj for obj in vars(contract).values()
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel
        and obj.__module__ == contract.__name__
    }
    assert declared == set(contract.CONTRACT_MODELS), (
        "CONTRACT_MODELS is out of sync with the module's models: "
        f"missing={sorted(m.__name__ for m in declared - set(contract.CONTRACT_MODELS))}, "
        f"stale={sorted(m.__name__ for m in set(contract.CONTRACT_MODELS) - declared)}")


def test_the_forbidden_token_list_matches_the_persisted_row_contract():
    """The served contract and the lake-row contract enforce the SAME posture at two points.

    Pinned equal rather than imported (importing the snapshot module drags numpy/pyarrow into the
    Lambda's model file). Two renderers of one rule are two rule sets unless something holds them
    together (E9.61).
    """
    from quant_sports_intel_models.football.ncaaf.models import game_prediction_snapshot as gps
    assert contract.FORBIDDEN_PAYLOAD_TOKENS == gps.FORBIDDEN_PAYLOAD_TOKENS
    assert contract.FRAMING == gps.FRAMING


def test_the_quantile_ladder_matches_what_the_snapshot_persists():
    """Serving copies a ladder off the row; if the two disagree, a level silently serves as null."""
    from quant_sports_intel_models.football.ncaaf.models import game_prediction_snapshot as gps
    assert payloads.QUANTILE_LEVELS == gps.PERSISTED_QUANTILES
    assert (payloads.INTERVAL_LO_LEVEL, payloads.INTERVAL_HI_LEVEL) == (gps.INTERVAL_LO, gps.INTERVAL_HI)


def test_best_alpha_is_zero_on_every_blob(snapshots, futures_rows):
    latest = payloads.latest_snapshot_per_key(snapshots, ("game_id",))
    slates = payloads.build_slate_payloads(latest, season=2026)
    board = payloads.build_futures_payload(
        payloads.latest_snapshot_per_key(futures_rows, ("team_id",)), season=2026)
    for blob in (*slates.values(), board):
        contract.assert_best_alpha_is_zero(blob)


def test_the_best_alpha_walk_catches_a_non_zero_stamp():
    """Positive control for the stamp walk — it must find one nested inside a list of games."""
    with pytest.raises(ValueError, match="best_alpha"):
        contract.assert_best_alpha_is_zero({"games": [{"framing": {"best_alpha": 0.02}}]})


#: Claim words the served copy may not ASSERT. ⚠️ Scanned NEGATION-AWARE, and that is load-bearing
#: rather than fussy: this repo has already shipped a substring denylist that fired on its own
#: honest hedge, where the cheapest way to pass the guard was to DELETE the sentence that made the
#: surface honest (NF-DS). "we publish no picks" is the copy we want; "our picks" is not.
_CLAIM_WORDS = ("best bet", "edge", "pick", "lock", "guarantee", "beat the book", "win rate")
_NEGATORS = ("no ", "not ", "never ", "without ", "don't ", "do not ")


def _asserted_claim_words(text: str) -> list[str]:
    """Claim words that appear WITHOUT a negation in the ~24 characters before them."""
    lowered = text.lower()
    found = []
    for word in _CLAIM_WORDS:
        for match in re.finditer(re.escape(word), lowered):
            window = lowered[max(0, match.start() - 24):match.start()]
            if not any(neg in window for neg in _NEGATORS):
                found.append(word)
    return found


def test_the_served_disclosure_asserts_no_claim():
    """The copy half of the posture: no picks, no best-bets, no edge — ASSERTED nowhere."""
    assert _asserted_claim_words(contract.DISCLOSURE) == []
    lowered = contract.DISCLOSURE.lower()
    assert "market-blind" in lowered and "no claim" in lowered


def test_the_copy_scan_is_negation_aware_in_both_directions():
    """Positive control, both ways. A scan that flagged the honest hedge would push a future author
    to delete it; a scan that flagged nothing would pass on an actual claim."""
    assert _asserted_claim_words("we publish no picks and claim no edge") == []
    assert "pick" in _asserted_claim_words("today's best picks")
    assert "edge" in _asserted_claim_words("our edge over the market")


# ══════════════════════════════════════════════════════════════════════════════════════════
# §2 Absent vs null
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_every_declared_field_is_on_the_wire_even_when_null():
    """A DECLARED field is always serialized. `exclude_none` anywhere would make "we have no value"
    indistinguishable from "this field does not exist" — different facts (NF-C6b)."""
    blob = contract.NcaafGamePrediction(game_id=1, season=2026, game_day="2026-08-29").model_dump()
    assert set(blob) == set(contract.declared_field_names(contract.NcaafGamePrediction))
    for nested, model in (("market", contract.NcaafMarketLine),
                          ("margin", contract.NcaafDistribution),
                          ("provenance", contract.NcaafModelProvenance),
                          ("win_probability", contract.NcaafWinProbability)):
        assert set(blob[nested]) == set(contract.declared_field_names(model))
    assert blob["market"]["home_spread"] is None  # present AND null


def test_an_unavailable_market_line_names_its_cause(snapshots):
    """A null market line has several causes and they must not render identically."""
    row = snapshots.iloc[-1].to_dict()
    no_capture = payloads.build_game_payload(row)["market"]
    read_failed = payloads.build_game_payload(row, market_read_failed=True)["market"]
    assert no_capture["status"] == read_failed["status"] == "unavailable"
    assert no_capture["reason"] == payloads.MARKET_REASON_NO_CAPTURE
    assert read_failed["reason"] == payloads.MARKET_REASON_READ_FAILED
    assert no_capture["reason"] != read_failed["reason"], (
        "a captured-nothing-yet null and a failed-read null are different facts")


def test_an_available_market_line_sits_beside_the_model_line_without_a_comparison(snapshots):
    """Transparency, not a verdict: both numbers are served, no difference/advantage field exists."""
    row = snapshots.iloc[-1].to_dict()
    market = {"close_home_spread": -3.5, "close_total": 52.0,
              "close_home_ml_american": -165.0, "close_home_ml_prob": 0.623,
              "close_snapshot_ts": "2026-08-29T15:55:00.000Z"}
    payload = payloads.build_game_payload(row, market_row=market)
    assert payload["market"]["status"] == "available"
    assert payload["market"]["home_spread"] == -3.5
    assert payload["margin"]["mu"] == row["mu_margin"]          # the model line, unchanged
    # Scanned over FIELD NAMES, not the serialized values: the payload legitimately CONTAINS the
    # disclosure sentence ("we make no claim to an advantage over it"), and a value scan would flag
    # exactly the honest copy — the NF-DS negation-blind trap, one layer over.
    names = {p.rsplit(".", 1)[-1].rstrip("]0123456789[") for p in _leaf_paths(payload)}
    for banned in ("edge", "advantage", "beats_market", "discrepancy", "delta", "vs_market"):
        assert not any(banned in n for n in names), (
            f"the served game payload declares a {banned!r} field — the market line is shown "
            "BESIDE the model line, never compared to it (VAL1's CLV null)")


def test_a_nan_becomes_null_never_zero(snapshots):
    """A fabricated 0.0 is a wrong number that looks like a measurement; honest NULLs stay NULL."""
    row = snapshots.iloc[-1].to_dict()
    row["p_home_win"] = float("nan")
    row["mu_total"] = float("nan")
    payload = payloads.build_game_payload(row)
    assert payload["win_probability"]["home"] is None
    assert payload["win_probability"]["away"] is None
    assert payload["total"]["mu"] is None


# ══════════════════════════════════════════════════════════════════════════════════════════
# §3 The E9.41 round-trip proof — through the REAL app
# ══════════════════════════════════════════════════════════════════════════════════════════

def _asgi_get(path: str, query: str = "") -> tuple[int, dict]:
    """Drive the real FastAPI app over ASGI and return (status, parsed body).

    ⭐ NOT a direct call to the route function. `response_model` filtering — the mechanism that
    silently DROPPED `FeaturedYesterday.status` in E9.41 — happens in the app layer, so a test that
    calls the function directly cannot see it. Driven over ASGI rather than with `TestClient`
    because `httpx` is not a test dependency of this repo.
    """
    from app.backend.main import app

    captured: dict = {"body": b""}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
        elif message["type"] == "http.response.body":
            captured["body"] += message.get("body", b"")

    async def run():
        await app({
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
            "path": path, "raw_path": path.encode(), "query_string": query.encode(),
            "headers": [(b"host", b"testserver")], "client": ("127.0.0.1", 5555),
            "server": ("testserver", 80), "scheme": "http", "root_path": "",
        }, receive, send)

    asyncio.run(run())
    return captured["status"], json.loads(captured["body"].decode() or "null")


def _leaf_paths(node, prefix="$"):
    """Every leaf path in a JSON tree — the comparison unit for "no field was dropped"."""
    if isinstance(node, dict):
        out = set()
        for k, v in node.items():
            out |= _leaf_paths(v, f"{prefix}.{k}")
        return out or {prefix}
    if isinstance(node, list):
        out = set()
        for i, v in enumerate(node):
            out |= _leaf_paths(v, f"{prefix}[{i}]")
        return out or {prefix}
    return {prefix}


@pytest.fixture()
def served(monkeypatch, snapshots, futures_rows):
    """The exact blobs the writer would build, installed behind the router's read functions."""
    latest = payloads.latest_snapshot_per_key(snapshots, ("game_id",))
    market = {401628319: {"close_home_spread": -34.5, "close_total": 54.5,
                          "close_home_ml_american": -5000.0, "close_home_ml_prob": 0.98,
                          "close_snapshot_ts": "2026-08-29T15:55:00.000Z"}}
    slates = payloads.build_slate_payloads(latest, season=2026, market_by_game=market)
    board = payloads.build_futures_payload(
        payloads.latest_snapshot_per_key(futures_rows, ("team_id",)), season=2026)
    manifest = payloads.build_manifest_payload(
        slates, season=2026, current_game_day="2026-08-29", futures_available=True)

    games = {g["game_id"]: g for s in slates.values() for g in s["games"]}
    monkeypatch.setattr(ncaaf_serving, "read_manifest", lambda: manifest)
    monkeypatch.setattr(ncaaf_serving, "read_slate", lambda d: slates.get(d))
    monkeypatch.setattr(ncaaf_serving, "read_game", lambda gid: games.get(int(gid)))
    monkeypatch.setattr(ncaaf_serving, "read_futures", lambda: board)
    return {"slates": slates, "board": board, "manifest": manifest, "games": games}


def test_a_real_payload_round_trips_the_router_with_every_field_intact(served):
    """THE E9.41 PROOF, on every route: what the writer built is byte-for-byte what the API returns.

    Compared as full LEAF PATHS, not just top-level keys — the silent drop that motivated this
    happened on a NESTED field, and a top-level key comparison would have passed straight through it.
    """
    cases = [
        ("/ncaaf/manifest", "", served["manifest"]),
        ("/ncaaf/games", "game_day=2026-08-29", served["slates"]["2026-08-29"]),
        ("/ncaaf/games/401628319", "", served["games"][401628319]),
        ("/ncaaf/futures", "", served["board"]),
    ]
    for path, query, expected in cases:
        status, body = _asgi_get(path, query)
        assert status == 200, f"{path} → {status}: {body}"
        missing = _leaf_paths(expected) - _leaf_paths(body)
        extra = _leaf_paths(body) - _leaf_paths(expected)
        assert not missing, f"{path} DROPPED {sorted(missing)} on serialize (the E9.41 class)"
        assert not extra, f"{path} invented {sorted(extra)}"
        assert body == expected, f"{path} changed a value on the way out"


def test_the_round_trip_would_notice_a_dropped_field(served):
    """Positive control for the proof above, and it exercises the REAL mechanism.

    A second FastAPI app serves the SAME blob under a response model with one nested field removed,
    driven through the same ASGI harness. If the harness cannot observe `response_model` stripping,
    the test above passes on nothing — which is exactly the E9.41 shape (the data was right in the
    store the whole time; only the serialize step dropped it).
    """
    from fastapi import FastAPI

    class _TrimmedMarket(contract.NcaafMarketLine):
        pass

    del _TrimmedMarket.model_fields["home_spread"]
    _TrimmedMarket.model_rebuild(force=True)

    class _TrimmedGame(contract.NcaafGamePrediction):
        market: _TrimmedMarket = _TrimmedMarket()

    probe = FastAPI()
    blob = served["games"][401628319]

    @probe.get("/probe", response_model=_TrimmedGame)
    def _probe():
        return blob

    captured: dict = {"body": b""}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
        elif message["type"] == "http.response.body":
            captured["body"] += message.get("body", b"")

    asyncio.run(probe({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
        "path": "/probe", "raw_path": b"/probe", "query_string": b"",
        "headers": [(b"host", b"testserver")], "client": ("127.0.0.1", 5555),
        "server": ("testserver", 80), "scheme": "http", "root_path": "",
    }, receive, send))

    assert captured["status"] == 200
    body = json.loads(captured["body"].decode())
    assert "home_spread" not in body["market"], (
        "the ASGI harness cannot observe a response_model drop — the round-trip proof above is "
        "vacuous")
    assert "home_spread" in blob["market"], "the source blob under test never had the field"


def test_an_unpublished_game_is_a_404_not_an_empty_success(served):
    """ABSENT ≠ NULL. A game we have no projection for must not come back as a 200 with blanks."""
    status, body = _asgi_get("/ncaaf/games/999999999", "")
    assert status == 404
    assert "No NCAAF projection" in body["detail"]

    status, body = _asgi_get("/ncaaf/games", "game_day=2030-01-01")
    assert status == 404
    assert "2030-01-01" in body["detail"], "the 404 must name the day it found nothing for"


def test_the_default_slate_is_the_la_game_day(served, monkeypatch):
    """No `game_day` ⇒ today in LA (INC-22), not the Lambda's UTC date."""
    monkeypatch.setattr(ncaaf_router, "current_game_date_iso", lambda: "2026-08-29")
    status, body = _asgi_get("/ncaaf/games", "")
    assert status == 200 and body["game_day"] == "2026-08-29"


# ══════════════════════════════════════════════════════════════════════════════════════════
# §4 INC-22 + the week landmine
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_a_late_saturday_kickoff_is_filed_under_saturday_not_the_utc_sunday():
    """INC-22, two-sided: the LA answer and the naive-UTC answer DISAGREE on this instant, so the
    test can tell them apart. A fixture where they agree would prove nothing."""
    kickoff = "2026-08-30T03:30:00.000Z"          # 20:30 PT, Saturday the 29th
    assert payloads.game_day_for(kickoff) == "2026-08-29"
    assert str(kickoff)[:10] == "2026-08-30", "the fixture no longer discriminates LA from UTC"


def test_slates_are_split_on_the_la_kickoff_day(snapshots):
    latest = payloads.latest_snapshot_per_key(snapshots, ("game_id",))
    slates = payloads.build_slate_payloads(latest, season=2026)
    assert set(slates) == {"2026-08-29"}, (
        "both games kick off on the LA Saturday; a UTC split would have produced two days")
    assert slates["2026-08-29"]["n_games"] == 2


def test_nothing_in_the_serving_layer_keys_on_season_order_week():
    """The recorded alias landmine: `game_prediction_snapshot.py:696` sets `season_order_week` to a
    verbatim copy of CFBD's postseason-restarting raw week, so nothing this story builds may key on
    it. Scanned over COMMENT-STRIPPED source — every module here explains at length why it does not
    use the column, and a naive substring scan would be satisfied by the explanation (INC-38)."""
    for path in _SERVING_SOURCES:
        stripped = _code_only(path.read_text())
        assert "season_order_week" not in stripped, f"{path.name} references season_order_week"


def test_no_serving_key_is_built_from_a_week():
    """`cfbd_week` may be DISPLAYED; it may never appear in a cache or S3 key."""
    for key in (contract.slate_cache_key("2026-08-29"), contract.game_cache_key(1),
                contract.FUTURES_CACHE_KEY, contract.MANIFEST_CACHE_KEY,
                contract.slate_s3_key("2026-08-29"), contract.game_s3_key(1),
                contract.FUTURES_S3_KEY, contract.MANIFEST_S3_KEY):
        assert "week" not in key.lower(), f"{key!r} keys on a week"


def test_the_manifest_indexes_game_days_not_weeks(snapshots):
    latest = payloads.latest_snapshot_per_key(snapshots, ("game_id",))
    slates = payloads.build_slate_payloads(latest, season=2026)
    manifest = payloads.build_manifest_payload(
        slates, season=2026, current_game_day="2026-08-29", futures_available=False)
    assert [d["game_day"] for d in manifest["game_days"]] == ["2026-08-29"]
    assert manifest["n_games_total"] == 2
    # The ONLY week-bearing name anywhere in the manifest is `strength_as_of_week`, and it is an
    # INPUT VINTAGE under `provenance` (which P1.2 row the prediction read), never an index into
    # the served games. Anything else named for a week would be the alias landmine re-entering.
    week_paths = {p for p in _leaf_paths(manifest) if "week" in p.lower()}
    assert week_paths == {"$.provenance.strength_as_of_week"}, week_paths


def test_ncaaf_keys_are_off_the_mlb_serving_lane():
    """Separate keys, same stores. The DynamoDB partition key IS the namespace, so an MLB read can
    never reach an NCAAF row; S3 uses its own prefix rather than the MLB lane's `api-cache/`."""
    assert contract.NAMESPACE == "ncaaf"
    for key in (contract.slate_cache_key("2026-08-29"), contract.game_cache_key(7),
                contract.FUTURES_CACHE_KEY, contract.MANIFEST_CACHE_KEY):
        assert key.partition("/")[0] == "ncaaf"
    for key in (contract.slate_s3_key("2026-08-29"), contract.game_s3_key(7),
                contract.FUTURES_S3_KEY, contract.MANIFEST_S3_KEY):
        assert key.startswith("ncaaf-cache/")
        assert not key.startswith("api-cache/")


# ══════════════════════════════════════════════════════════════════════════════════════════
# §5 The writer
# ══════════════════════════════════════════════════════════════════════════════════════════

class _FakeTable:
    def __init__(self, fail: bool = False):
        self.items: dict[tuple[str, str], dict] = {}
        self.fail = fail

    def put_item(self, Item):  # noqa: N803 — boto3's casing
        if self.fail:
            raise RuntimeError("dynamo down")
        self.items[(Item["pk"], Item["sk"])] = Item


class _FakeS3:
    def __init__(self, fail: bool = False):
        self.objects: dict[str, str] = {}
        self.fail = fail

    def put_object(self, Bucket, Key, Body, ContentType):  # noqa: N803
        if self.fail:
            raise RuntimeError("s3 down")
        self.objects[Key] = Body


@pytest.fixture()
def writer(monkeypatch, snapshots, futures_rows):
    import scripts.write_ncaaf_serving_store as w
    from quant_sports_intel_models.football.ncaaf.models import game_prediction_snapshot as gps

    def fake_read(season, source, *, local_root=None):
        return snapshots if source == gps.SNAPSHOT_SOURCE else futures_rows

    monkeypatch.setattr(w, "read_snapshots", fake_read)
    monkeypatch.setattr(w, "read_market_lines", lambda season: ({}, False))
    monkeypatch.setenv("CACHE_BUCKET", "credence-prod-s3-api-cache")
    return w


def test_the_writer_reaches_both_stores_and_the_blobs_read_back(writer, monkeypatch):
    table, s3 = _FakeTable(), _FakeS3()
    monkeypatch.setattr(writer, "_dynamo_table", lambda: table)
    monkeypatch.setattr(writer, "_s3_client", lambda: s3)

    manifest = writer.write_serving_store(2026)
    assert manifest["status"] == "ok"
    assert manifest["n_games"] == 2 and manifest["n_game_days"] == 1
    assert manifest["futures_teams"] == 2
    # manifest + 1 slate + 2 games + futures
    assert manifest["n_blobs"] == 5 == manifest["dynamo_writes"] == manifest["s3_writes"]

    # every blob is addressable under the ncaaf namespace / prefix, and decodes
    assert ("ncaaf", "manifest#PERMANENT") in table.items
    assert ("ncaaf", "slate/2026-08-29#PERMANENT") in table.items
    assert ("ncaaf", "game/401628319#PERMANENT") in table.items
    assert ("ncaaf", "futures/board#PERMANENT") in table.items
    assert set(s3.objects) == {
        "ncaaf-cache/manifest.json", "ncaaf-cache/slate/2026-08-29.json",
        "ncaaf-cache/game/401628319.json", "ncaaf-cache/game/401628320.json",
        "ncaaf-cache/futures/board.json"}
    assert json.loads(s3.objects["ncaaf-cache/game/401628319.json"])["win_probability"]["home"] == 0.62


def test_the_writer_serves_the_latest_vintage(writer, monkeypatch):
    """An append-only table holds several snapshots per game; serving publishes the NEWEST."""
    table, s3 = _FakeTable(), _FakeS3()
    monkeypatch.setattr(writer, "_dynamo_table", lambda: table)
    monkeypatch.setattr(writer, "_s3_client", lambda: s3)
    writer.write_serving_store(2026)
    game = json.loads(s3.objects["ncaaf-cache/game/401628319.json"])
    assert game["provenance"]["snapshot_ts"] == "2026-08-27T16:00:00.000Z"
    assert game["win_probability"]["home"] == 0.62, "the older 0.51 vintage was published"


def test_a_dynamodb_outage_still_serves_from_s3(writer, monkeypatch):
    """Degraded, not down — that is what the S3 fallback is for. The run must NOT go red."""
    s3 = _FakeS3()
    monkeypatch.setattr(writer, "_dynamo_table", lambda: _FakeTable(fail=True))
    monkeypatch.setattr(writer, "_s3_client", lambda: s3)
    manifest = writer.write_serving_store(2026)
    assert manifest["dynamo_writes"] == 0 and manifest["s3_writes"] == 5


def test_the_writer_halts_when_neither_store_took_a_blob(writer, monkeypatch):
    """HALT tier. Both stores down means the app has no board, so the run must go red where an
    operator sees it — never a quiet success (the 19-green-runs class, NF-FRESH1)."""
    monkeypatch.setattr(writer, "_dynamo_table", lambda: _FakeTable(fail=True))
    monkeypatch.setattr(writer, "_s3_client", lambda: _FakeS3(fail=True))
    with pytest.raises(RuntimeError, match="reached NEITHER store"):
        writer.write_serving_store(2026)


def test_no_snapshots_is_a_no_op_not_a_write(writer, monkeypatch):
    """Pre-opener: nothing to publish is a genuine no-op, distinguishable from a failure AND from a
    write. An unreadable lake raises upstream in `query_or_missing` — the two must never look
    the same (INC-38)."""
    table, s3 = _FakeTable(), _FakeS3()
    monkeypatch.setattr(writer, "read_snapshots", lambda *a, **k: None)
    monkeypatch.setattr(writer, "_dynamo_table", lambda: table)
    monkeypatch.setattr(writer, "_s3_client", lambda: s3)
    manifest = writer.write_serving_store(2026)
    assert manifest["status"] == "no_snapshots"
    assert not table.items and not s3.objects, "a no-op wrote to the serving store"


def test_an_unwritten_snapshot_table_is_an_empty_read_not_a_crash(monkeypatch):
    """Before the first NCAAF-PS run both snapshot tables are absent from S3, and the pre-opener
    serving write must log a clean no-op rather than going RED.

    🩹 NCAAF-LAKE1 RE-ANCHORED this. P3.1 shipped a LOCAL message match in `read_snapshots` for the
    object-store absence wording; the shared `query_lake` helper now establishes absence by LISTING
    the store, for every caller, so the local branch was removed as a second rule for one question.
    The PROPERTY is unchanged and still pinned — it is now proven through the real shared path.
    """
    import scripts.write_ncaaf_serving_store as w
    from quant_sports_intel_models.football.ncaaf.ingest import query_lake
    from quant_sports_intel_models.football.ncaaf.models import game_prediction_snapshot as gps

    monkeypatch.setattr(query_lake, "_connect", lambda: type("C", (), {"execute": lambda *a: None})())
    monkeypatch.setattr(query_lake, "q", lambda sql: (_ for _ in ()).throw(
        Exception("IO Error: DeltaKernel GenericError (5): No files in log segment")))
    monkeypatch.setattr(query_lake, "_table_has_commits", lambda uri: False)
    assert w.read_snapshots(2026, gps.SNAPSHOT_SOURCE) is None


def test_a_genuine_read_failure_still_raises(monkeypatch):
    """The other side of the same coin — the leniency must be narrow. A transient lake failure must
    NEVER be published over as "nothing to serve" (INC-38: a no-op and a broken read are different
    facts). Re-anchored onto the shared helper alongside its sibling above."""
    import scripts.write_ncaaf_serving_store as w
    from quant_sports_intel_models.football.ncaaf.ingest import query_lake
    from quant_sports_intel_models.football.ncaaf.models import game_prediction_snapshot as gps

    monkeypatch.setattr(query_lake, "_connect", lambda: type("C", (), {"execute": lambda *a: None})())
    monkeypatch.setattr(query_lake, "q", lambda sql: (_ for _ in ()).throw(
        Exception("IO Error: HTTP 503 SlowDown from S3")))
    monkeypatch.setattr(query_lake, "_table_has_commits", lambda uri: True)
    with pytest.raises(RuntimeError, match="refusing to treat this as a missing table"):
        w.read_snapshots(2026, gps.SNAPSHOT_SOURCE)


def test_a_dry_run_writes_nothing(writer, monkeypatch):
    table, s3 = _FakeTable(), _FakeS3()
    monkeypatch.setattr(writer, "_dynamo_table", lambda: table)
    monkeypatch.setattr(writer, "_s3_client", lambda: s3)
    manifest = writer.write_serving_store(2026, dry_run=True)
    assert manifest["status"] == "ok" and manifest["n_blobs"] == 5
    assert not table.items and not s3.objects


def test_a_failed_market_read_never_costs_the_slate(writer, monkeypatch):
    """WARN tier: the market line is enrichment beside the model line, never an input."""
    monkeypatch.setattr(writer, "read_market_lines", lambda season: ({}, True))
    table, s3 = _FakeTable(), _FakeS3()
    monkeypatch.setattr(writer, "_dynamo_table", lambda: table)
    monkeypatch.setattr(writer, "_s3_client", lambda: s3)
    manifest = writer.write_serving_store(2026)
    assert manifest["status"] == "ok" and manifest["n_games"] == 2
    assert manifest["market_read_failed"] is True
    game = json.loads(s3.objects["ncaaf-cache/game/401628319.json"])
    assert game["market"]["reason"] == payloads.MARKET_REASON_READ_FAILED


def test_the_market_read_is_warn_tier_and_reports_the_failure(monkeypatch):
    """The REAL `read_market_lines`, driven into a failure.

    ⭐ The sibling test above monkeypatches this function away, so it proves the writer HANDLES a
    reported failure — it says nothing about whether the function still swallows one. This is the
    other half, and the RED proof is what found it missing: a break to the `except` left that test
    green. Two properties, and both matter: it must NOT raise (WARN tier — the market line is
    transparency beside the model line, never an input), and it must REPORT `read_failed=True` so
    the served `market.reason` can name the cause instead of rendering a bare blank (NF-C6b).
    """
    import scripts.write_ncaaf_serving_store as w

    class _Boom:
        def __getattr__(self, name):
            raise RuntimeError("lake read exploded")

    monkeypatch.setitem(
        __import__("sys").modules,
        "quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game", _Boom())
    lines, failed = w.read_market_lines(2026)
    assert lines == {} and failed is True


def _skip_without_manifest():
    """`pipeline/__init__.py` reads the dbt manifest at IMPORT, and it is gitignored — so it is
    absent in a fresh worktree and in the fast gate (E11.23 / NF-D18). A test that needs the
    compiled Dagster graph skips there rather than dying at import."""
    if not (_REPO / "dbt/target/manifest.json").exists():
        pytest.skip("dbt manifest absent — `pipeline` is not importable here")


def test_the_serving_write_schedule_is_daily_and_in_season():
    """Manifest-FREE (source-read): the cadence the spec asks for — a daily in-season refresh
    beside the weekly board write chained into the snapshot job."""
    src = (_REPO / "pipeline/schedules/sports_ncaaf_serving_write_schedules.py").read_text()
    cron = re.search(r'NCAAF_SERVING_WRITE_CRON = "([^"]+)"', src).group(1)
    minute, hour, dom, month, dow = cron.split()
    assert dom == "*" and dow == "*", f"must fire every day in its months, got {cron!r}"
    months = {int(m) for part in month.split(",")
              for m in (range(int(part.split("-")[0]), int(part.split("-")[1]) + 1)
                        if "-" in part else [int(part)])}
    assert {8, 9, 10, 11, 12, 1} <= months, f"the season window is incomplete: {sorted(months)}"
    assert "America/Los_Angeles" in src, "the schedule must fire on the LA clock (INC-22)"
    assert "DefaultScheduleStatus.STOPPED" in src, (
        "NCAAF schedules ship operator-gated (the E11.23 carve-out this vertical takes)")


def test_the_serving_write_op_is_halt_tier():
    """Manifest-FREE: the op must not wrap the write in a `try`. A swallowed failure here is a
    serving outage that reports success — the class that produced 19 green runs (NF-FRESH1)."""
    src = _code_only((_REPO / "pipeline/jobs/sports_ncaaf_serving_write_job.py").read_text())
    assert "try" not in src.split(), (
        "the serving write is HALT tier: it must raise, not swallow")


def test_the_serving_write_op_runs_after_the_snapshot_ops(writer):
    """INC-25: the serving store is a CONSUMER of the snapshot tables, so the publish must sit
    DOWNSTREAM of the write that feeds it in the SAME run — pinned on the compiled Dagster graph,
    not on source-line order (which is vacuous for an in-process executor)."""
    _skip_without_manifest()
    from pipeline.jobs.sports_ncaaf_prediction_snapshot_job import (
        sports_ncaaf_prediction_snapshot_job as job,
    )
    graph = job.graph
    assert "ncaaf_serving_write_after_snapshot_op" in graph.node_dict
    edges = {
        invocation.name: {dep.node for dep in inputs.values()}
        for invocation, inputs in graph.dependencies.items()
    }
    assert edges["ncaaf_serving_write_after_snapshot_op"] == {"ncaaf_futures_snapshot_op"}, (
        "the serving write must be chained downstream of the snapshot chain (INC-25)")
    assert edges["ncaaf_futures_snapshot_op"] == {"ncaaf_prediction_snapshot_op"}, (
        "the chain the serving write rides on was re-wired; the publish is no longer guaranteed "
        "to run after the per-game snapshot")


# ══════════════════════════════════════════════════════════════════════════════════════════
# §6 Public + free
# ══════════════════════════════════════════════════════════════════════════════════════════

def test_the_ncaaf_router_carries_no_entitlement_dependency():
    """NCAAF is FREE (E9.45). A `Depends` here — or a `dependencies=` on the mount — would gate it."""
    assert ncaaf_router.router.dependencies == []
    for route in ncaaf_router.router.routes:
        assert getattr(route, "dependencies", []) == [], f"{route.path} carries a dependency"

    main_src = _code_squashed((_REPO / "app/backend/main.py").read_text())
    assert "app.include_router(ncaaf.router)" in main_src, (
        "the NCAAF router must be mounted with NO dependencies= argument")


def test_every_ncaaf_route_is_in_the_degrade_floor_and_the_public_cache_rules():
    """A new public surface that joins neither registry silently undoes G100-D1's guardrails."""
    for route in ncaaf_router.router.routes:
        path = route.path.replace("{game_id}", "12345")
        assert cost_guardrails.is_allowed_in_degrade(path), f"{path} is not in the degrade floor"
        assert cost_guardrails.public_cache_control(path), f"{path} has no public cache rule"


def test_the_degrade_allowlist_is_still_a_prefix_match_not_a_substring():
    """Positive control: `/ncaaf` must not accidentally admit an unrelated `/ncaafanything`."""
    assert not cost_guardrails.is_allowed_in_degrade("/ncaafx/secret")
    assert not cost_guardrails.public_cache_control("/ncaafx/secret")


def test_the_read_path_is_dynamodb_then_s3_with_no_snowflake():
    """The read order the whole serving store is built on; Snowflake is not on this path at all."""
    src = _code_squashed((_REPO / "app/backend/services/ncaaf_serving.py").read_text())
    assert "serving_cache.get_cache(" in src, "the DynamoDB read is no longer the first leg"
    assert "_s3_get(" in src, "the S3 fallback leg is gone"
    assert "snowflake" not in src.lower()


def test_the_s3_fallback_runs_when_dynamodb_returns_nothing(monkeypatch):
    """A DynamoDB error decodes to None inside `serving_cache`, so the fallback must fire on None —
    not only on a confirmed miss (the silent-empty class, E9.26b)."""
    from app.backend.services import serving_cache
    monkeypatch.setattr(serving_cache, "get_cache", lambda k, d: None)
    monkeypatch.setattr(ncaaf_serving, "_s3_get", lambda key: {"from": "s3", "key": key})
    assert ncaaf_serving.read_futures() == {"from": "s3", "key": contract.FUTURES_S3_KEY}


def test_dynamodb_wins_when_it_has_the_blob(monkeypatch):
    from app.backend.services import serving_cache
    monkeypatch.setattr(serving_cache, "get_cache", lambda k, d: {"from": "dynamo"})
    monkeypatch.setattr(ncaaf_serving, "_s3_get",
                        lambda key: pytest.fail("S3 was read while DynamoDB had the blob"))
    assert ncaaf_serving.read_manifest() == {"from": "dynamo"}
