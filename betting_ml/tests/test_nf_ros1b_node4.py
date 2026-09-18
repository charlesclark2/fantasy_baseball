"""NF-ROS1b node 4 — the certified ROS artifact, born contracted (registration §9, amendment 1).

Fast gate: the contract, the real `build()` over synthetic inputs (the real `assemble`, no lake, no
S3), the write-gate, the served-bytes check, the executing entrypoint smoke with IO stubbed at the
boundary, the freshness policy, and source-level pins on the Dagster wiring (never an import of
`pipeline` — E11.23).
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.backend.models import nfl_ros as C
from app.backend.services.projection_fields import PAID_PLAYER_FIELDS, STAT_FIELD
from betting_ml.monitoring import nfl_ros_freshness as RF
from quant_sports_intel_models.football.nfl.fantasy import ros_interval as RI
from quant_sports_intel_models.football.nfl.fantasy import ros_value as V
from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1 as N
from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1_publish as P

REPO = Path(__file__).resolve().parents[2]
JOB = REPO / "pipeline/jobs/sports_nfl_weekly_serving_job.py"
SLEEPER = REPO / "pipeline/jobs/sports_nfl_sleeper_injuries_job.py"
NOW = datetime(2026, 9, 17, 16, 0, tzinfo=timezone.utc)


def _code(path: Path) -> str:
    """Source with comment lines and docstring-only lines stripped (prose cannot satisfy a pin)."""
    out = []
    for ln in path.read_text().splitlines():
        s = ln.strip()
        if s.startswith("#"):
            continue
        out.append(ln)
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# the contract
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_four_absences_are_declared_and_distinct():
    assert C.ROS_ABSENCES == ("not_certified", "position_not_evaluated", "no_preseason_prior",
                              "join_unresolved")
    args = set(C.RosAbsence.__args__)
    assert args == set(C.ROS_ABSENCES)


def test_no_field_invites_a_cross_position_comparison():
    names = C.contract_field_names()
    assert len(names) > 40, "the scan read almost nothing — it is not reading the contract"
    bad = [n for n in names if any(t in n.lower() for t in C.FORBIDDEN_FIELD_TOKENS)]
    assert bad == []
    assert "not a cross-position ranking input" in C.COMPARISON_NOTE


def test_the_stat_line_is_derived_from_stat_field_and_is_paid():
    fields = set(C.NflRosPlayer.model_fields)
    assert set(STAT_FIELD.values()) <= fields
    assert set(STAT_FIELD.values()) <= fields & PAID_PLAYER_FIELDS
    # The rest of the paid set is the alternative scorings; pinned by its own clause below.


def test_the_paid_set_is_the_stat_line_plus_the_alternative_scorings():
    """⭐ THE PM'S 2026-09-18 ACK, PINNED. The paid-set diff shown to the PM carried a pricing
    question: the six ROS Std/Half values came out FREE because `PAID_SCORING_FIELDS` was a hand
    list naming `fpStd`/`fpHalf` only, while the season board's Std/Half were paid — a user would
    have paid for a format on one tab and got it free on the next. Ruling: Std/Half join the paid
    set, the PPR triple stays free WITH its band.

    Asserted as the RULE's consequence, both ways: nothing PPR is paid, nothing Std/Half is free.
    """
    fields = set(C.NflRosPlayer.model_fields)
    per_scoring = {f for f in fields if f.startswith("ros")}
    assert per_scoring == {"rosPtsStd", "rosP10Std", "rosP90Std",
                           "rosPtsHalf", "rosP10Half", "rosP90Half",
                           "rosPtsPpr", "rosP10Ppr", "rosP90Ppr"}

    paid_scorings = {f for f in per_scoring if f.endswith("Std") or f.endswith("Half")}
    free_scorings = per_scoring - paid_scorings
    assert paid_scorings <= PAID_PLAYER_FIELDS, "an alternative scoring would ship free"
    assert not free_scorings & PAID_PLAYER_FIELDS, "the free PPR wedge would be withheld"

    # The rest of the paid diff is the stat line, exactly as the PM was shown.
    assert (fields & PAID_PLAYER_FIELDS) - paid_scorings == set(STAT_FIELD.values())


def test_the_upper_edge_is_served_as_a_tail_not_a_ceiling():
    """§13 finding ⑪ rides the artifact, not only the record (PM ack, 2026-09-18) — a display
    consumer reading the P90 gets the reason it can exceed any pace on record in the same blob."""
    note = C.NflRosManifest.model_fields["upper_tail_note"].default
    assert note == C.UPPER_TAIL_NOTE
    assert "not clamped" in note.lower()
    assert "tail" in note.lower() and "ceiling" in note.lower()


def test_missing_declared_fields_sees_an_absent_default():
    blob = {"season": 2026, "throughWeek": 1, "generated_at": "x", "manifest_key": "m"}
    assert C.missing_declared_fields(blob, C.NflRosCurrent) == ["players_key"]


def test_keys():
    assert C.ros_manifest_key(2026, 3) == "ros/2026/3/manifest.json"
    assert C.ros_players_key(2026, 3) == "ros/2026/3/players.json"
    assert C.ros_current_key(2026) == "ros/2026/current.json"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# the build, over synthetic inputs, through the real assemble
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _served():
    def p(pid, name, pos, team, g, rookie=False, pick=None, **stats):
        return {"id": pid, "name": name, "pos": pos, "team": team, "g": g, "rookie": rookie,
                "draftPick": pick, **stats}
    return {"generated_at": "2026-09-15T00:00:00Z", "model_version": "board_v",
            "players": [
                p("00-0000001", "Alpha Back", "RB", "LAR", 16.0, rushYds=1100.0, rushTd=8.0,
                  rec=40.0, recYds=300.0, rushAtt=240.0, tgt=50.0, twoPt=0.6, fum=1.5),
                p("SYN0000001", "Rookie Runner", "RB", "KC", 14.0, True, 5, rushYds=700.0,
                  rushTd=5.0, rec=20.0, recYds=150.0, rushAtt=160.0, tgt=25.0),
                p("SYN0000002", "Vocab Guy", "RB", "NE", 10.0, True, 60, rushYds=200.0,
                  rushAtt=50.0),
                p("00-0000002", "Quarter Back", "QB", "KC", 17.0, passYds=4000.0, passTd=30.0,
                  passAtt=550.0, passCmp=360.0),
                p("DST-KC", "KC D/ST", "DST", "KC", 17.0),
                p("00-0000004", "Kick Er", "K", "BUF", 17.0, fg039=20.0, patMade=40.0),
            ]}


def _real_and_sched():
    weeks = range(1, 19)
    sched = pd.DataFrame(
        [dict(season=2026, week=w, game_type="REG", home_team="LA", away_team="KC")
         for w in weeks if w != 9]
        + [dict(season=2026, week=w, game_type="REG", home_team="NE", away_team="BUF")
           for w in weeks if w != 10])
    rows = []

    def r(pid, name, pos, team, game, **st):
        rows.append(dict(player_id=pid, player_display_name=name, position=pos, team=team,
                         season=2026, week=1, season_type="REG", game_id=game, **st))
    r("00-0000001", "Alpha Back", "RB", "LA", "g1a", carries=18.0, rushing_yards=95.0,
      rushing_tds=1.0, receptions=3.0, receiving_yards=21.0)
    r("00-0000009", "Rookie Runner", "RB", "KC", "g1a", carries=10.0, rushing_yards=44.0,
      receptions=1.0, receiving_yards=5.0)
    r("00-0000010", "Vocab Guy", "WR", "NE", "g1b", receptions=2.0, receiving_yards=12.0)
    r("00-0000002", "Quarter Back", "QB", "KC", "g1a", passing_yards=250.0, passing_tds=2.0)
    r("00-0000004", "Kick Er", "K", "BUF", "g1b", fg_made_20_29=1.0, pat_made=2.0)
    r("00-0000099", "Waiver Guy", "WR", "BUF", "g1b", receptions=4.0, receiving_yards=60.0)
    real = pd.DataFrame(rows)
    for c in N.R.REALIZED_STAT_COLUMNS:
        if c not in real.columns:
            real[c] = 0.0
    real[list(N.R.REALIZED_STAT_COLUMNS)] = real[list(N.R.REALIZED_STAT_COLUMNS)].fillna(0.0)
    real["fantasy_points_ppr"] = 0.0
    return real, sched


def _authority(pick_gsis=None):
    picks = pd.DataFrame({"season": [2026, 2026], "pick": [5, 60],
                          "gsis_id": [pick_gsis or "00-0000009", "00-0000010"],
                          "pfr_player_name": ["Rookie Runner", "Vocab Guy"],
                          "position": ["RB", "RB"]})
    rosters = pd.DataFrame({"season": [2026], "week": [1], "full_name": ["x"],
                            "position": ["RB"], "gsis_id": ["00-0000077"]})
    return lambda: (picks, rosters)


def _params(served, real, sched):
    """Serving params shaped exactly like `fit_serving_params` output, with simple fixed tables."""
    boards = P.served_board_frame(served, 2026)
    _, diag = N.assemble((2026,), stats_version=None, schedules_version=None, d=Path("."),
                         boards_override=boards, real_override=real, sched_override=sched)
    stat_keys = [k for k in diag["scoring_terms"]["_stat_keys"] if k != "two_pt"]
    _, diag2 = N.assemble((2026,), stats_version=None, schedules_version=None, d=Path("."),
                          boards_override=boards, real_override=real, sched_override=sched,
                          allowed_keys=stat_keys)
    ratio = list(np.linspace(0.2, 2.5, len(RI.FINE_LEVELS)))
    table = {"edges": {"RB": [10.0, 50.0]}, "cell": {}, "kb": {}, "pos": {"RB": ratio}}
    pi = {"single_class": True, "base": 0.08, "dropped": 0, "mu": [0.0] * 10, "sd": [1.0] * 10,
          "keep": [True] * 10}
    return {
        "certified_positions": ["RB"], "certified_weeks": [1, 12],
        "m": {P_: {"m_r": 4, "m_a": 3} for P_ in V.POSITIONS},
        "pi": {p: {P_: pi for P_ in V.POSITIONS} for p in V.PRESETS},
        "ratio_tables": {p: table for p in V.PRESETS},
        "scoring_terms": {p: diag2["scoring_terms"][p]["applied"] for p in V.PRESETS},
        "stat_keys": stat_keys,
        "certification": [{"pos": P_, "certified": P_ == "RB", "failed_clauses": [],
                           "mean_lift": 1.0, "folds_won": 6, "pit_max_decile_dev": 0.01,
                           "coverage80": 0.85, "coverage_floor": 0.78, "reported_state": None}
                          for P_ in V.POSITIONS],
        "decisive_commit": "abc12345",
    }


@pytest.fixture
def built():
    served = _served()
    real, sched = _real_and_sched()
    params = _params(served, real, sched)
    b = P.build(params, "sha", served, real, sched, season=2026, stats_version=29,
                schedules_version=36, authority=_authority(), now=NOW)
    return b, served, params


def test_the_build_serves_certified_rows_and_states_every_absence(built):
    b, served, _ = built
    rows = {r["id"]: r for r in b["payload"]["players"]}
    assert set(rows) == {r["id"] for r in served["players"]}
    assert rows["00-0000001"]["certified"] and rows["00-0000001"]["absence"] is None
    assert rows["SYN0000001"]["certified"] and rows["SYN0000001"]["gamesPlayed"] == 1
    assert rows["SYN0000002"]["absence"] == "join_unresolved" and not rows["SYN0000002"]["certified"]
    assert rows["00-0000002"]["absence"] == "not_certified" and rows["00-0000002"]["rosPtsPpr"] is None
    assert rows["00-0000004"]["absence"] == "not_certified"
    assert rows["DST-KC"]["absence"] == "position_not_evaluated"
    for r in rows.values():
        assert r["waiverValue"] is None and r["waiverAbsence"] == C.WAIVER_ABSENCE
    m = b["manifest"]
    assert m["join_unresolved_names"] == ["Vocab Guy"]
    counts = {c["reason"]: c["n"] for c in m["absence_counts"]}
    assert counts["no_preseason_prior"] == m["no_preseason_prior_players"] >= 1
    assert m["certified_positions"] == ["RB"] and m["certified_for_this_week"] is True
    assert m["throughWeek"] == 1


def test_a_certified_row_carries_a_coherent_band_and_stat_line(built):
    b, _, _ = built
    r = next(x for x in b["payload"]["players"] if x["id"] == "00-0000001")
    for suf in ("Std", "Half", "Ppr"):
        assert r[f"rosP10{suf}"] <= r[f"rosPts{suf}"] <= r[f"rosP90{suf}"]
    assert r["rushYds"] > 0 and r["twoPt"] is None      # the unevaluated term is never served
    assert 0 < r["rateWeight"] < 1 and r["availWeight"] == pytest.approx(1 / 4)


def test_an_unevaluated_board_term_is_stripped_before_scoring():
    """The live finding: the served board carries `twoPt`, which history never did. The point must
    not apply it — so its value is identical with and without the field on the board."""
    served = _served()
    real, sched = _real_and_sched()
    params = _params(served, real, sched)
    a = P.build(params, "sha", served, real, sched, season=2026, stats_version=29,
                schedules_version=36, authority=_authority(), now=NOW)
    for r in served["players"]:
        r.pop("twoPt", None)
    b = P.build(params, "sha", served, real, sched, season=2026, stats_version=29,
                schedules_version=36, authority=_authority(), now=NOW)
    pa = next(x for x in a["payload"]["players"] if x["id"] == "00-0000001")
    pb = next(x for x in b["payload"]["players"] if x["id"] == "00-0000001")
    assert pa["rosPtsStd"] == pb["rosPtsStd"]


def test_an_incoherent_stat_line_refuses(monkeypatch):
    """The gate that caught the live `twoPt` defect: a stat line that does not score to the served
    value must stop the build, never ship."""
    served = _served()
    real, sched = _real_and_sched()
    params = _params(served, real, sched)
    orig = P.stat_line
    monkeypatch.setattr(P, "stat_line",
                        lambda *a, **k: {f: 1.01 * v for f, v in orig(*a, **k).items()})
    with pytest.raises(P.RosPublishError, match="coherence"):
        P.build(params, "sha", served, real, sched, season=2026, stats_version=29,
                schedules_version=36, authority=_authority(), now=NOW)


def test_a_wrong_identity_join_stops_the_build():
    served = _served()
    real, sched = _real_and_sched()
    params = _params(served, real, sched)
    with pytest.raises(P.RosPublishError, match="WRONG"):
        P.build(params, "sha", served, real, sched, season=2026, stats_version=29,
                schedules_version=36, authority=_authority(pick_gsis="00-0000055"), now=NOW)


def test_a_week_outside_the_certified_range_serves_no_numbers():
    served = _served()
    real, sched = _real_and_sched()
    params = _params(served, real, sched)
    params["certified_weeks"] = [2, 12]
    b = P.build(params, "sha", served, real, sched, season=2026, stats_version=29,
                schedules_version=36, authority=_authority(), now=NOW)
    assert b["manifest"]["certified_for_this_week"] is False
    assert not any(r["certified"] for r in b["payload"]["players"])


def test_a_term_set_drift_refuses():
    served = _served()
    real, sched = _real_and_sched()
    params = _params(served, real, sched)
    params["scoring_terms"]["full_ppr"] = params["scoring_terms"]["full_ppr"] + ["def_td"]
    with pytest.raises(P.RosPublishError, match="term set"):
        P.build(params, "sha", served, real, sched, season=2026, stats_version=29,
                schedules_version=36, authority=_authority(), now=NOW)


def test_no_final_week_builds_nothing():
    served = _served()
    real, sched = _real_and_sched()
    params = _params(served, real, sched)
    partial = real[real["game_id"] == "g1a"]          # one of week 1's two games
    assert P.final_through_week(partial, sched) == 0
    assert P.build(params, "sha", served, partial, sched, season=2026, stats_version=29,
                   schedules_version=36, authority=_authority(), now=NOW) is None


def test_final_week_needs_every_game_and_contiguity():
    _, sched = _real_and_sched()
    wk = lambda w, g: dict(season_type="REG", week=w, game_id=g)
    real = pd.DataFrame([wk(1, "a"), wk(1, "b"), wk(3, "c"), wk(3, "d")])
    assert P.final_through_week(real, sched) == 1


# ── the write-gate, served bytes, entrypoint ──────────────────────────────────────────────────────
def test_the_write_gate_refuses_a_short_blob(built):
    b, _, _ = built
    del b["manifest"]["framing"]
    with pytest.raises(P.RosPublishError, match="framing"):
        P.stage(b, Path("/nonexistent-never-written"))


def test_the_write_gate_refuses_a_players_hash_mismatch(built):
    b, _, _ = built
    b["manifest"]["players_sha256"] = "0" * 64
    with pytest.raises(P.RosPublishError, match="players_sha256"):
        P.publish(b, None, do_publish=False)


class _FakeS3:
    def __init__(self, corrupt=False):
        self.store, self.corrupt = {}, corrupt

    def put_object(self, Bucket, Key, Body, ContentType):
        self.store[Key] = Body + (b" " if self.corrupt else b"")

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.store[Key])}


def test_publish_reads_back_and_compares_the_served_bytes(built):
    b, _, _ = built
    served = P.publish(b, "bucket", do_publish=True, s3=_FakeS3())
    assert len(served) == 3
    with pytest.raises(P.RosPublishError, match="served bytes differ"):
        P.publish(b, "bucket", do_publish=True, s3=_FakeS3(corrupt=True))


def test_publish_without_a_bucket_fails(built):
    b, _, _ = built
    with pytest.raises(P.RosPublishError, match="bucket"):
        P.publish(b, None, do_publish=True, s3=_FakeS3())


def test_the_written_blob_is_the_validated_dump(built):
    b, _, _ = built
    assert json.loads(b["players_bytes"]) == b["payload"]
    assert hashlib.sha256(b["players_bytes"]).hexdigest() == b["manifest"]["players_sha256"]
    assert C.missing_declared_fields(b["payload"], C.NflRosPayload) == []


def test_the_entrypoint_executes_end_to_end(tmp_path, monkeypatch):
    """§8 'executing entrypoint smoke': `main()` with IO stubbed at the boundary only."""
    served = _served()
    real, sched = _real_and_sched()
    params = _params(served, real, sched)
    fake = _FakeS3()
    monkeypatch.setattr(P, "load_params", lambda s: (params, "sha"))
    monkeypatch.setattr(P, "load_served_board", lambda s, b: served)
    monkeypatch.setattr(P, "lake_reads", lambda s: (real, sched, 29, 36))
    monkeypatch.setattr(P, "authority_reads", lambda s: _authority()())
    import boto3
    monkeypatch.setattr(boto3, "client", lambda *a, **k: fake)
    assert P.main(["--out", str(tmp_path), "--publish", "--s3-bucket", "b"]) == 0
    assert set(fake.store) == {"fantasy/nfl/" + k for k in
                               (C.ros_manifest_key(2026, 1), C.ros_players_key(2026, 1),
                                C.ros_current_key(2026))}
    assert (tmp_path / C.ros_manifest_key(2026, 1)).exists()


def test_the_entrypoint_skips_cleanly_with_no_final_week(tmp_path, monkeypatch):
    served = _served()
    real, sched = _real_and_sched()
    params = _params(served, real, sched)
    monkeypatch.setattr(P, "load_params", lambda s: (params, "sha"))
    monkeypatch.setattr(P, "load_served_board", lambda s, b: served)
    monkeypatch.setattr(P, "lake_reads", lambda s: (real[real["game_id"] == "g1a"], sched, 29, 36))
    assert P.main(["--out", str(tmp_path)]) == P.EXIT_NO_FINAL_WEEK
    assert not any(tmp_path.rglob("*.json"))


def test_the_committed_params_certify_what_the_decisive_record_certified():
    params, _ = P.load_params(P.SERVING_SEASON)
    record = json.loads(P.DECISIVE_RECORD.read_text())
    _, certified = P.certification_table(record)
    assert params["certified_positions"] == certified == ["RB"]
    assert params["decisive_commit"] == record["meta"]["commit"]
    assert params["frame_rows"] == record["meta"]["rows"]
    assert params["certified_weeks"] == [1, 12]
    assert "two_pt" not in params["stat_keys"]


def test_the_committed_ratio_tables_round_trip():
    params, _ = P.load_params(P.SERVING_SEASON)
    t = P.table_from_json(params["ratio_tables"]["full_ppr"])
    assert all(len(q) == len(RI.FINE_LEVELS) for q in t["pos"].values())
    assert P._table_to_json(t) == params["ratio_tables"]["full_ppr"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# the freshness policy
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _reading(week=1, hours_ago=2.0):
    return RF.RosReading(season=2026, through_week=week, generated_at=NOW - timedelta(hours=hours_ago))


@pytest.mark.parametrize("kw,want", [
    (dict(reading=_reading(), enabled=True, expected_through_week=0), "INACTIVE"),
    (dict(reading=RF.RosReading(season=2026), enabled=False, expected_through_week=1),
     "ARMED_NOT_FIRING"),
    (dict(reading=RF.RosReading(season=2026), enabled=True, expected_through_week=1),
     "NOTHING_PUBLISHED"),
    (dict(reading=_reading(hours_ago=40), enabled=True, expected_through_week=1), "STALE"),
    (dict(reading=_reading(week=1), enabled=True, expected_through_week=2), "BEHIND"),
    (dict(reading=_reading(week=2), enabled=True, expected_through_week=2), "OK"),
    (dict(reading=RF.RosReading(season=2026, error="x"), enabled=True, expected_through_week=2),
     "UNKNOWN"),
])
def test_freshness_verdicts(kw, want):
    v = RF.classify(**kw, lake_commit=NOW - timedelta(hours=5), now=NOW)
    assert v["verdict"] == want
    assert RF.is_problem(v) == (want not in ("INACTIVE", "OK"))


def test_a_just_final_week_is_not_behind_yet():
    v = RF.classify(_reading(week=1), enabled=True, expected_through_week=2,
                    lake_commit=NOW - timedelta(minutes=20), now=NOW)
    assert v["verdict"] == "OK"


def test_the_deploy_held_state_is_warn_not_critical_and_names_the_action():
    v = RF.classify(RF.RosReading(season=2026), enabled=False, expected_through_week=1,
                    lake_commit=None, now=NOW)
    assert v["severity"] == "WARN" and RF.PUBLISH_ENABLED_FLAG in v["detail"]


def test_an_unreadable_lake_is_never_healthy():
    v = RF.classify(_reading(), enabled=True, expected_through_week=None, lake_commit=None,
                    now=NOW, lake_error="boom")
    assert v["verdict"] == "UNKNOWN" and v["severity"] == "WARN"


def test_the_flag_reads_only_exactly_one():
    assert RF.publish_enabled({RF.PUBLISH_ENABLED_FLAG: "1"})
    for val in ("", "0", "true", " ", "yes"):
        assert not RF.publish_enabled({RF.PUBLISH_ENABLED_FLAG: val})
    assert not RF.publish_enabled({})


# ══════════════════════════════════════════════════════════════════════════════════════════════
# the Dagster wiring (source-level — the fast gate never imports `pipeline`)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_publish_is_an_independent_branch_off_the_ingest():
    src = _code(JOB)
    body = src[src.index("def sports_nfl_weekly_serving_job("):]
    assert "nfl_ros_value_publish_op(start=landed)" in body


def test_the_publish_op_checks_the_flag_before_doing_anything():
    src = _code(JOB)
    op = src[src.index("def nfl_ros_value_publish_op("):src.index("def sports_nfl_weekly_serving_job(")]
    flag_at = op.index("if not RF.publish_enabled():")
    assert flag_at < op.index("run_bounded(")
    assert re.search(r"if not RF\.publish_enabled\(\):\s+context\.log\.warning\([\s\S]*?\n\s+return\n", op)


def test_the_publish_subprocess_is_bounded_and_the_exit_code_is_pinned():
    src = _code(JOB)
    op = src[src.index("def nfl_ros_value_publish_op("):src.index("def sports_nfl_weekly_serving_job(")]
    assert "timeout=NFL_ROS_PUBLISH_TIMEOUT_SECONDS" in op
    m = re.search(r"^EXIT_ROS_NO_FINAL_WEEK = (\d+)$", src, re.M)
    assert m and int(m.group(1)) == P.EXIT_NO_FINAL_WEEK


def test_the_publish_op_pages_and_raises_on_failure_and_verifies_what_it_served():
    src = _code(JOB)
    op = src[src.index("def nfl_ros_value_publish_op("):src.index("def sports_nfl_weekly_serving_job(")]
    assert 'dedup_key="nfl_ros_publish:failed"' in op
    assert 'raise Exception(f"NFL ROS publish failed' in op
    assert "players_sha256" in op and 'raise Exception("NFL ROS verification failed' in op


def test_the_freshness_op_runs_outside_its_subject():
    job_body = _code(JOB)
    serving = job_body[job_body.index("def sports_nfl_weekly_serving_job("):
                       job_body.index("def nfl_ros_freshness_op(")]
    assert "nfl_ros_freshness_op(" not in serving
    sleeper = _code(SLEEPER)
    body = sleeper[sleeper.index("def sports_nfl_sleeper_injuries_job("):]
    assert "nfl_ros_freshness_op()" in body


def test_the_flag_is_not_a_deploy_requirement():
    req = (REPO / "services/dagster/aws/env.required").read_text()
    assert RF.PUBLISH_ENABLED_FLAG not in req


def test_the_hosting_schedule_self_starts_and_is_heartbeat_checked():
    from betting_ml.monitoring.monitor_health import CRITICAL_SCHEDULES

    assert "sports_nfl_weekly_serving_schedule" in CRITICAL_SCHEDULES
    src = _code(REPO / "pipeline/schedules/sports_rollforward_schedules.py")
    block = src[src.index("NFL_WEEKLY_SERVING_CRON ="):src.index("def sports_nfl_weekly_serving_schedule(")]
    assert "default_status=DefaultScheduleStatus.RUNNING" in block
