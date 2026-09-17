"""NF-WK-ACC1 — guards for the divergence recorder's wiring (PM rider ⑥) and the D/ST inputs.

RC1's closeout ⑥ measured that `compare_to_platform` and `dst_row` had NO production caller: the
recorder was built, proven and guarded, and the system never ran it. Every clause here is about the
recorder actually RUNNING, record-only, and each is RED-proven in `nf_wk_acc1_red_proof.py`.
"""
from __future__ import annotations

import ast
import importlib.util
import io
import json
import re
from pathlib import Path

import pytest

from app.backend.services import realized_dst, weekly_recap, weekly_recap_divergence
from quant_sports_intel_models.football.nfl.fantasy import realized_week as RW

_REPO = Path(__file__).resolve().parents[2]
_ROUTER = _REPO / "app/backend/routers/fantasy.py"
_RECORDER = _REPO / "app/backend/services/weekly_recap_divergence.py"
_JOB_PATH = _REPO / "pipeline/jobs/sports_nfl_weekly_serving_job.py"


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────────

def _fetched():
    """One matchup: a player seat (who fumbled) and a DST seat, with the league's own figures."""
    return {
        "season": 2025, "week": 1, "platform": "sleeper", "leagueId": "P1",
        "startingSlots": ["RB", "DEF"],
        "teams": [{
            "teamKey": "1", "teamName": "A", "matchupId": 1, "platformTotal": 13.0,
            "lineup": [
                {"slot": "RB", "seat": 0, "playerKey": "9", "empty": False, "name": "Real Player",
                 "position": "RB", "team": "ATL", "platformPts": 9.0},
                {"slot": "DEF", "seat": 1, "playerKey": "PHI", "empty": False, "name": "PHI D/ST",
                 "position": "DST", "team": "PHI", "platformPts": 4.0},
            ],
        }],
    }


#: 100 rushing yards at 0.1 = 10.0 by us; the league's -1 `fum` (captured by us) makes it 9.0.
_REALIZED = [{"player_display_name": "Real Player", "position": "RB", "team": "ATL",
              "rushing_yards": 100, "fumbles_total": 1}]
_CFG = {"scoring": {"per_stat": {"rush_yds": 0.1, "fum": -1.0, "def_sacks": 1.0,
                                 "dst_pa_g_14_17": 1.0, "dst_pa_g_18_20": 1.0}}}


def _games():
    return [{"game_id": "g1", "home_team": "PHI", "away_team": "DAL",
             "home_score": 24, "away_score": 20}]


def _stats(**phi):
    base = {c: 0 for c in realized_dst.DST_TEAM_COLUMNS}
    return {"PHI": {**base, **phi}, "DAL": dict(base)}


# ── the construction's box half ──────────────────────────────────────────────────────────────────

def test_the_box_half_builds_one_line_per_defence_keyed_by_the_scorers_team_vocabulary():
    out = RW.team_week_inputs(_stats(def_sacks=3), _games())
    assert set(out) == {"PHI", "DAL"}
    assert out["PHI"]["line"]["dst_points_allowed"] == 20.0
    assert out["PHI"]["line"]["def_sacks"] == 3
    assert out["PHI"]["opponent"] == "DAL" and out["PHI"]["resultPending"] is False


def test_a_missing_opponent_score_is_tagged_pending_not_dropped():
    """PM card yOhLHprC — the Monday-night result lands late. Tagged, never silently omitted."""
    games = [{**_games()[0], "away_score": None}]
    out = RW.team_week_inputs(_stats(), games)
    assert out["PHI"]["resultPending"] is True
    assert "dst_points_allowed" not in out["PHI"]["line"]
    assert out["DAL"]["resultPending"] is False


def test_a_defence_with_no_stats_row_is_omitted_not_zero_filled():
    """An omitted defence reports `notConstructed`; a zero-filled one would read as agreement."""
    out = RW.team_week_inputs({"PHI": _stats()["PHI"]}, _games())
    assert out == {}


def test_the_lakes_LA_meets_the_platforms_LAR():
    games = [{"game_id": "g", "home_team": "LA", "away_team": "DAL",
              "home_score": 10, "away_score": 3}]
    stats = {"LA": _stats()["PHI"], "DAL": _stats()["DAL"]}
    out = RW.team_week_inputs(stats, games)
    from app.backend.services import league_scoring
    assert league_scoring.normalize_team("LAR") in out


# ── the recorder ─────────────────────────────────────────────────────────────────────────────────

def _scored_and_seats():
    seats: dict = {}
    scored = weekly_recap.score_week(fetched=_fetched(), realized_rows=_REALIZED, cfg=_CFG,
                                     realized_by_seat=seats)
    return scored, seats


def test_score_week_fills_the_seat_explanations_and_never_serves_them():
    scored, seats = _scored_and_seats()
    assert seats == {("1", 0): {"fumbles_total": 1}}
    served = json.dumps(scored["teams"], default=str)
    assert "explain" not in served and "fumbles_total" not in served


def test_the_explained_split_is_actually_fed_on_the_wired_path():
    """⛔ THE RC1 NO-OP, ONE LEVEL UP. With the seat explanations wired, the fumble delta is
    EXPLAINED; if the out-parameter stopped being filled, `unexplained` would equal `diverging`."""
    scored, seats = _scored_and_seats()
    rec = weekly_recap_divergence.build_record(scored=scored, scoring=_CFG["scoring"],
                                               dst_inputs=None, realized_by_seat=seats)
    ps = rec["comparison"]["playerSeats"]
    assert ps["diverging"] == 1
    assert ps["unexplained"] == 0, ps


def test_missing_dst_inputs_are_recorded_as_not_supplied_never_as_agreement():
    scored, seats = _scored_and_seats()
    rec = weekly_recap_divergence.build_record(scored=scored, scoring=_CFG["scoring"],
                                               dst_inputs=None, realized_by_seat=seats)
    dst = rec["comparison"]["dstSeats"]
    assert dst["constructionSupplied"] is False and dst["compared"] == 0


def test_published_dst_inputs_are_scored_under_the_leagues_own_settings():
    scored, seats = _scored_and_seats()
    inputs = {"teams": RW.team_week_inputs(_stats(def_sacks=3), _games())}
    rec = weekly_recap_divergence.build_record(scored=scored, scoring=_CFG["scoring"],
                                               dst_inputs=inputs, realized_by_seat=seats)
    dst = rec["comparison"]["dstSeats"]
    assert dst["constructionSupplied"] is True and dst["compared"] == 1
    # PA 20 → the 18-20 tier (1) + 3 sacks (3) = 4.0 = the league's figure.
    assert dst["diverging"] == 0, dst["rows"]


def test_the_recorder_never_pages():
    tree = ast.parse(_RECORDER.read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "send_alert" not in names, "the divergence recorder must record data, never a page"


class _FakeS3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.puts = 0

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            err = Exception("missing")
            err.response = {"Error": {"Code": "NoSuchKey"}}
            raise err
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.puts += 1
        self.objects[Key] = Body.encode() if isinstance(Body, str) else Body


def test_the_record_is_written_once_and_rewritten_only_when_it_changes():
    s3 = _FakeS3()
    scored, seats = _scored_and_seats()
    kw = dict(scored=scored, scoring=_CFG["scoring"], realized_by_seat=seats,
              league_id="L1", s3=s3, bucket="b")
    assert weekly_recap_divergence.record(dst_inputs=None, **kw)["status"] == "created"
    assert weekly_recap_divergence.record(dst_inputs=None, **kw)["status"] == "unchanged"
    assert s3.puts == 1
    inputs = {"teams": RW.team_week_inputs(_stats(def_sacks=3), _games()), "generated_at": "t"}
    assert weekly_recap_divergence.record(dst_inputs=inputs, **kw)["status"] == "updated"
    assert s3.puts == 2


def test_a_read_error_that_is_not_a_miss_raises():
    class Broken(_FakeS3):
        def get_object(self, Bucket, Key):
            err = Exception("denied")
            err.response = {"Error": {"Code": "AccessDenied"}}
            raise err
    scored, seats = _scored_and_seats()
    with pytest.raises(Exception, match="denied"):
        weekly_recap_divergence.record(scored=scored, scoring={}, dst_inputs=None,
                                       realized_by_seat=seats, league_id="L", s3=Broken(),
                                       bucket="b")


# ── the production caller ────────────────────────────────────────────────────────────────────────

def _strip(src: str) -> str:
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))


def test_the_recap_route_turns_the_recorder_on():
    """⭐ WIRED, NOT MERELY IMPORTED (NF-C0e). Matched as a CALL with the flag, on comment-stripped
    source, so the explanatory comment beside it cannot satisfy the clause (INC-38)."""
    src = _strip(_ROUTER.read_text())
    start = src.index("def nfl_weekly_recap(")
    body = src[start:src.index("\n@router", start + 1)]
    assert re.search(r"_recap_week\([^)]*record_divergence=True", body), (
        "the single-week recap route no longer asks for the divergence record — the recorder has "
        "no production caller again (RC1 closeout ⑥)")


def test_recap_week_invokes_the_recorder_and_survives_its_failure(monkeypatch):
    """By substitution: the real `_recap_week`, the real scorer, a recorder that RAISES."""
    from app.backend.routers import fantasy

    blobs = {
        "realized/2025/1/players.json": {"players": _REALIZED},
        "realized/2025/1/manifest.json": {"completeness": "final"},
        "realized/2025/1/dst_inputs.json": {"teams": {}},
    }
    monkeypatch.setattr(fantasy.weekly_recap_store, "load", lambda *a: _fetched())
    monkeypatch.setattr(fantasy, "_load_json", lambda key, *a, **k: blobs.get(key))
    calls = []

    def boom(**kw):
        calls.append(kw)
        raise RuntimeError("s3 is down")

    monkeypatch.setattr(fantasy.weekly_recap_divergence, "record", boom)
    record = {"source_platform": "sleeper", "source_league_id": "P1", "league_id": "L1", **_CFG}
    out = fantasy._recap_week(record, 2025, 1, record_divergence=True)
    assert out["teams"][0]["standingsTotal"] == 13.0, "a recorder failure must not touch the recap"
    assert len(calls) == 1
    assert calls[0]["realized_by_seat"] == {("1", 0): {"fumbles_total": 1}}
    assert calls[0]["dst_inputs"] == {"teams": {}} and calls[0]["league_id"] == "L1"

    calls.clear()
    fantasy._recap_week(record, 2025, 1)
    assert calls == [], "power rankings (the default) must not multiply the recorder's round-trips"


# ── the box-side publish ─────────────────────────────────────────────────────────────────────────

def _built():
    return {"season": 2026, "week": 1, "teams": RW.team_week_inputs(_stats(), _games()),
            "resultPendingTeams": []}


def test_dst_inputs_publish_is_content_addressed_and_dry_runs_write_nothing():
    s3 = _FakeS3()
    assert RW.publish_dst_inputs(_built(), s3=s3, bucket="b", dry=True)["action"] == "create"
    assert s3.puts == 0
    assert RW.publish_dst_inputs(_built(), s3=s3, bucket="b")["action"] == "create"
    assert RW.publish_dst_inputs(_built(), s3=s3, bucket="b")["action"] == "unchanged"
    changed = _built()
    changed["teams"]["PHI"]["resultPending"] = True
    assert RW.publish_dst_inputs(changed, s3=s3, bucket="b")["action"] == "update"
    assert s3.puts == 2
    key = "fantasy/nfl/realized/2026/1/dst_inputs.json"
    assert key in s3.objects, "the recap route reads this exact key"


def _runner():
    spec = importlib.util.spec_from_file_location(
        "_acc1_runner", _REPO / "quant_sports_intel_models/football/nfl/fantasy/run_realized_week.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_dst_inputs_failure_is_kept_out_of_the_critical_error_list(monkeypatch):
    runner = _runner()

    def explode(*a, **k):
        raise RuntimeError("lake hiccup")

    monkeypatch.setattr(RW, "build_dst_inputs", explode)

    class Args:
        season, s3_bucket = 2026, "b"

    results, errors = runner._dst_inputs(Args, _FakeS3(), False, [1, 2], None, None)
    assert results == [] and [e["week"] for e in errors] == [1, 2]


def _load_job():
    spec = importlib.util.spec_from_file_location("_acc1_job", _JOB_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_op_pages_dst_input_failures_at_warn_and_does_not_fail_the_run(monkeypatch):
    """Executed, not grepped: the real op, the subprocess replaced by a canned RESULT line."""
    import subprocess

    from dagster import build_op_context

    from betting_ml.utils import bounded_subprocess

    job = _load_job()
    summary = {"planned": [], "results": [], "events": [], "errors": [], "final_weeks": [1],
               "season_to_date": {}, "dst_inputs": [],
               "dst_inputs_errors": [{"week": 1, "error": "RuntimeError: lake hiccup"}]}
    monkeypatch.setattr(bounded_subprocess, "run_bounded", lambda cmd, **k: subprocess.CompletedProcess(
        cmd, 0, stdout="RESULT " + json.dumps(summary), stderr=""))
    pages = []
    monkeypatch.setattr(job, "_page", lambda ctx, title, body, **kw: pages.append(kw))
    job.nfl_realized_week_publish_op(build_op_context())
    assert [p["severity"] for p in pages] == ["WARN"]
    assert pages[0]["dedup_key"] == "nfl_realized_publish:dst_inputs"
