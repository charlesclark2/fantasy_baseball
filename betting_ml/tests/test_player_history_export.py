"""NF3.3 — the fantasy football player-page History panel (past-season actual + past ADP + injury
log), fed by a new export step that PATCHES the shared `projections.json` payload.

Pure/offline: tiny synthetic frames + monkeypatched DuckDB-free reads, no S3/network. Covers:
  * `injury_log_source.injury_records` / `games_missed_records` — the display-record shape.
  * `export_player_history_json.build_past_seasons` — routes to `build_player_track_record` (never a
    parallel re-derivation of the ADP-vs-actual join) and attaches `gamesPlayed`.
  * `export_player_history_json.merge_history` / `diff_verify` — the shared-export-file discipline:
    merging adds ONLY `history`, and the verifier must catch any other drift.
  * `export_player_history_json._maybe_publish` — the NF-D12 dry-run/--publish guard, single-key
    upload variant.
  * `_load_live_projections` — the dev/test override escape hatch, and the "no bucket, no local
    staged file" hard failure.
"""
from __future__ import annotations

import json
import logging

import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import injury_log_source as IL
from quant_sports_intel_models.football.nfl.fantasy import export_player_history_json as ex


# ── injury_log_source ────────────────────────────────────────────────────────────────────────────
def test_injury_records_groups_by_player_and_is_json_null_safe():
    df = pd.DataFrame([
        {"player_id": "P1", "season": 2024, "week": 3, "report_status": "Questionable",
         "report_primary_injury": "Ankle", "practice_status": "Limited Participation in Practice",
         "date_modified": "2024-09-18"},
        {"player_id": "P1", "season": 2024, "week": 4, "report_status": None,
         "report_primary_injury": None, "practice_status": "Full Participation in Practice",
         "date_modified": "2024-09-25"},
        {"player_id": "P2", "season": 2024, "week": 3, "report_status": "Out",
         "report_primary_injury": "Hamstring", "practice_status": "Did Not Participate In Practice",
         "date_modified": "2024-09-19"},
    ])
    out = IL.injury_records(df)
    assert set(out) == {"P1", "P2"}
    assert len(out["P1"]) == 2
    assert out["P1"][0] == {
        "season": 2024, "week": 3, "reportStatus": "Questionable", "reportPrimaryInjury": "Ankle",
        "practiceStatus": "Limited Participation in Practice", "dateModified": "2024-09-18",
    }
    assert out["P1"][1]["reportStatus"] is None
    assert out["P1"][1]["reportPrimaryInjury"] is None


def test_injury_records_empty_frame_returns_empty_map():
    assert IL.injury_records(pd.DataFrame(columns=IL.INJURY_REPORT_COLS)) == {}


def test_games_missed_records_shape_and_sorted_by_season():
    df = pd.DataFrame([
        {"player_id": "P1", "season": 2025, "games_on_roster": 17, "games_missed": 1},
        {"player_id": "P1", "season": 2023, "games_on_roster": 16, "games_missed": 4},
    ])
    out = IL.games_missed_records(df)
    assert out["P1"] == [
        {"season": 2023, "gamesOnRoster": 16, "gamesMissed": 4},
        {"season": 2025, "gamesOnRoster": 17, "gamesMissed": 1},
    ]


def test_games_missed_records_empty_frame_returns_empty_map():
    assert IL.games_missed_records(pd.DataFrame(columns=IL.GAMES_MISSED_COLS)) == {}


# ── export_player_history_json.build_past_seasons — routes to build_player_track_record ───────────
def test_build_past_seasons_routes_through_build_player_track_record_never_rederives(monkeypatch):
    """The core reuse guard: this must call `build_player_track_record` (the SAME function NF3.2's
    public track record uses) rather than re-joining projection/ADP/realized itself."""
    calls = []

    def fake_build_player_track_record(con, season, schema):
        calls.append(season)
        return pd.DataFrame([{
            "player_id": "P1", "player_name": "A", "position": "RB",
            "our_points": 200.0, "our_rank": 1, "adp": 5.2, "adp_rank": 2,
            "actual_points": 190.0, "actual_rank": 1, "is_fade": True, "fade_result": "hit",
            "adp_source": "ffc",
        }])

    def fake_load_realized_season(con, season, schema, include_zero_game=False):
        return pd.DataFrame([{"player_id": "P1", "g": 15, "real_fp_ppr": 190.0}])

    monkeypatch.setattr(ex, "build_player_track_record", fake_build_player_track_record)
    monkeypatch.setattr(ex, "load_realized_season", fake_load_realized_season)

    out = ex.build_past_seasons(None, [2023, 2024], "sch")
    assert calls == [2023, 2024]
    assert len(out["P1"]) == 2
    rec = out["P1"][0]
    assert rec == {
        "season": 2023, "ourRank": 1, "adp": 5.2, "adpRank": 2, "adpSource": "ffc",
        "actualPoints": 190.0, "actualRank": 1, "gamesPlayed": 15, "isFade": True, "fadeResult": "hit",
    }


def test_build_past_seasons_skips_a_season_with_no_built_board(monkeypatch, caplog):
    def fake_build_player_track_record(con, season, schema):
        if season == 2019:
            raise FileNotFoundError("no nf1_5_season_projections_2019.parquet")
        return pd.DataFrame([{
            "player_id": "P1", "player_name": "A", "position": "RB",
            "our_points": 100.0, "our_rank": 1, "adp": 5.0, "adp_rank": 1,
            "actual_points": 90.0, "actual_rank": 1, "is_fade": False, "fade_result": None,
            "adp_source": "ffc",
        }])

    def fake_load_realized_season(con, season, schema, include_zero_game=False):
        return pd.DataFrame([{"player_id": "P1", "g": 10, "real_fp_ppr": 90.0}])

    monkeypatch.setattr(ex, "build_player_track_record", fake_build_player_track_record)
    monkeypatch.setattr(ex, "load_realized_season", fake_load_realized_season)

    with caplog.at_level(logging.WARNING, logger=ex.log.name):
        out = ex.build_past_seasons(None, [2019, 2020], "sch")
    assert [r["season"] for r in out["P1"]] == [2020]
    assert "no NF1.5 refined board" in " ".join(r.message for r in caplog.records)


def test_build_history_map_omits_players_with_nothing(monkeypatch):
    monkeypatch.setattr(ex, "build_past_seasons", lambda con, seasons, schema: {"P1": [{"season": 2024}]})
    monkeypatch.setattr(IL, "load_injury_reports", lambda con, seasons: pd.DataFrame(columns=IL.INJURY_REPORT_COLS))
    monkeypatch.setattr(IL, "load_games_missed", lambda con, seasons, schema: pd.DataFrame(columns=IL.GAMES_MISSED_COLS))

    out = ex.build_history_map(None, [2024], "sch")
    assert set(out) == {"P1"}
    assert out["P1"] == {"pastSeasons": [{"season": 2024}], "injuries": [], "gamesMissedBySeason": []}


# ── merge_history / diff_verify — the shared-export-file discipline ────────────────────────────────
def _base_payload():
    return {
        "season": 2026, "generated_at": "2026-08-01T00:00:00Z", "model_version": "nf1_5_v1",
        "players": [
            {"id": "P1", "name": "A", "pos": "RB", "fpPpr": 200.0},
            {"id": "P2", "name": "B", "pos": "WR", "fpPpr": 150.0},
        ],
    }


def test_merge_history_adds_history_and_nothing_else():
    payload = _base_payload()
    merged = ex.merge_history(payload, {"P1": {"pastSeasons": [{"season": 2024}], "injuries": [], "gamesMissedBySeason": []}})
    assert merged["players"][0]["history"] == {"pastSeasons": [{"season": 2024}], "injuries": [], "gamesMissedBySeason": []}
    assert merged["players"][1]["history"] is None
    # the original payload is untouched (deep copy, not mutate-in-place)
    assert "history" not in payload["players"][0]


def test_diff_verify_passes_on_a_history_only_merge():
    payload = _base_payload()
    merged = ex.merge_history(payload, {"P1": {"pastSeasons": [], "injuries": [], "gamesMissedBySeason": []}})
    ex.diff_verify(payload, merged)  # must not raise


def test_diff_verify_catches_a_changed_top_level_field():
    payload = _base_payload()
    merged = ex.merge_history(payload, {})
    merged["model_version"] = "SOMETHING_ELSE"
    with pytest.raises(ValueError, match="top-level fields changed"):
        ex.diff_verify(payload, merged)


def test_diff_verify_catches_a_changed_player_field_outside_history():
    payload = _base_payload()
    merged = ex.merge_history(payload, {})
    merged["players"][0]["fpPpr"] = 999.0
    with pytest.raises(ValueError, match="changed underneath this patch outside 'history'"):
        ex.diff_verify(payload, merged)


def test_diff_verify_catches_a_dropped_player():
    payload = _base_payload()
    merged = ex.merge_history(payload, {})
    del merged["players"][1]
    with pytest.raises(ValueError, match="player count changed"):
        ex.diff_verify(payload, merged)


def test_diff_verify_catches_reordered_players():
    payload = _base_payload()
    merged = ex.merge_history(payload, {})
    merged["players"] = list(reversed(merged["players"]))
    with pytest.raises(ValueError, match="changed underneath this patch outside 'history'"):
        ex.diff_verify(payload, merged)


# ── _load_live_projections ───────────────────────────────────────────────────────────────────────
def test_load_live_projections_override_reads_the_named_file(tmp_path):
    p = tmp_path / "projections.json"
    p.write_text(json.dumps({"season": 2026, "players": []}))
    payload, desc = ex._load_live_projections(2026, None, p)
    assert payload == {"season": 2026, "players": []}
    assert str(p) in desc


def test_load_live_projections_no_bucket_no_local_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "_BOARD_STAGING_OUT", tmp_path / "nowhere")
    with pytest.raises(SystemExit):
        ex._load_live_projections(2026, None, None)


# ── _maybe_publish — NF-D12 guard, single-key variant ───────────────────────────────────────────────
@pytest.fixture
def patched_file(tmp_path):
    p = tmp_path / "projections.json"
    p.write_text(json.dumps({"season": 2026, "players": []}))
    return p


def _spy_put_object(monkeypatch):
    calls = []

    class _FakeS3:
        def put_object(self, **kwargs):
            calls.append(kwargs)

    import boto3

    monkeypatch.setattr(boto3, "client", lambda *a, **k: _FakeS3())
    return calls


def test_default_dry_run_never_uploads_even_with_a_resolved_bucket(patched_file, monkeypatch):
    calls = _spy_put_object(monkeypatch)
    ex._maybe_publish(patched_file, "credence-prod-s3-api-cache", 2026, publish=False)
    assert calls == []


def test_publish_flag_uploads_only_the_single_projections_key(patched_file, monkeypatch):
    calls = _spy_put_object(monkeypatch)
    ex._maybe_publish(patched_file, "credence-prod-s3-api-cache", 2026, publish=True)
    assert len(calls) == 1
    assert calls[0]["Bucket"] == "credence-prod-s3-api-cache"
    assert calls[0]["Key"] == "fantasy/nfl/2026/projections.json"


def test_no_bucket_with_publish_raises(patched_file, monkeypatch):
    calls = _spy_put_object(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        ex._maybe_publish(patched_file, None, 2026, publish=True)
    assert calls == []
    assert "--publish" in str(exc.value) and "NO BUCKET" in str(exc.value)


def test_no_bucket_no_publish_warns_local_only(patched_file, monkeypatch, caplog):
    _spy_put_object(monkeypatch)
    with caplog.at_level(logging.WARNING, logger=ex.log.name):
        ex._maybe_publish(patched_file, None, 2026, publish=False)
    assert "staged locally only" in " ".join(r.message for r in caplog.records)


# ── _parse_seasons ───────────────────────────────────────────────────────────────────────────────
def test_parse_seasons_range():
    assert ex._parse_seasons("2019-2021") == [2019, 2020, 2021]


def test_parse_seasons_single_year():
    assert ex._parse_seasons("2024") == [2024]
