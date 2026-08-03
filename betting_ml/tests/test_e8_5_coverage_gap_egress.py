"""Fast-gate tests for E8.5's coverage-gap egress — the app-side write and the board-build-side read.

Neither side ever touches real S3: `boto3.client` is monkeypatched with a small in-memory fake, the
same convention `test_e8_2_league_router.py` uses for `dynamo`. What has to hold:

  1. THE WRITE NEVER RAISES. It is advisory, not serving-critical — a league save/update/pick must
     never fail because S3 is unreachable.
  2. IT WRITES ONE OBJECT PER (user, league), OVERWRITING WHOLESALE — never merges, so a gap that
     self-healed on the app side (see `test_e8_2_roster_upload.py::TestTheGapSelfHeals`) is written
     as GONE, not appended-and-forgotten.
  3. THE BOARD-BUILD READER TOLERATES A MALFORMED / LEGACY OBJECT without losing every other
     league's report (the E9.49 "one bad row must not blank the whole endpoint" rule, applied here
     to a board-build report instead of an API response).
  4. NOTHING IS EVER MERGED ACROSS USERS.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from app.backend.services import coverage_gap_egress
from betting_ml.scripts.prospect_board import coverage_gap_report


class FakeS3:
    """A tiny in-memory stand-in for the one bucket both sides read/write."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    # ── writer side (app/backend) ──
    def put_object(self, Bucket, Key, Body, ContentType=None):  # noqa: N803 — boto3's own casing
        self.objects[Key] = Body.encode("utf-8") if isinstance(Body, str) else Body

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.objects.pop(Key, None)

    # ── reader side (board build) ──
    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket, Prefix):  # noqa: N803
        contents = [{"Key": k} for k in self.objects if k.startswith(Prefix)]
        yield {"Contents": contents}

    def get_object(self, Bucket, Key):  # noqa: N803
        class _Body:
            def __init__(self, data):
                self._data = data

            def read(self):
                return self._data

        return {"Body": _Body(self.objects[Key])}


@pytest.fixture
def fake_s3(monkeypatch):
    fake = FakeS3()
    monkeypatch.setattr(coverage_gap_egress.boto3, "client", lambda *a, **k: fake)
    monkeypatch.setattr(coverage_gap_report.boto3, "client", lambda *a, **k: fake)
    monkeypatch.setattr(coverage_gap_egress.os, "getenv",
                        lambda k, d=None: "test-artifacts-bucket" if k == "ARTIFACTS_BUCKET" else d)
    monkeypatch.setattr(coverage_gap_report.os, "getenv",
                        lambda k, d=None: "test-artifacts-bucket" if k == "ARTIFACTS_BUCKET" else d)
    return fake


LEAGUE_META = {"name": "Dynasty", "league_scope": "AL", "season": 2026, "updated_at": "2026-08-03T00:00:00Z"}
GAPS = [{"key": "k1", "name": "Vance Honeycutt", "team": "T1", "slot": "OF", "status": "minors",
         "org": "BAL", "positions": "OF", "source": "confirmed"}]


class TestTheWrite:
    def test_writes_one_object_keyed_on_user_and_league(self, fake_s3):
        assert coverage_gap_egress.write("u1", "lg1", LEAGUE_META, GAPS) is True
        keys = list(fake_s3.objects)
        assert len(keys) == 1
        assert "user=u1" in keys[0] and "league=lg1" in keys[0]

    def test_the_body_carries_league_context_and_the_gaps(self, fake_s3):
        coverage_gap_egress.write("u1", "lg1", LEAGUE_META, GAPS)
        body = json.loads(next(iter(fake_s3.objects.values())))
        assert body["user_id"] == "u1"
        assert body["league_id"] == "lg1"
        assert body["league_name"] == "Dynasty"
        assert body["coverage_gaps"] == GAPS

    def test_overwrites_wholesale_rather_than_merging(self, fake_s3):
        """The self-heal contract: an empty second write must leave NOTHING behind."""
        coverage_gap_egress.write("u1", "lg1", LEAGUE_META, GAPS)
        coverage_gap_egress.write("u1", "lg1", LEAGUE_META, [])
        body = json.loads(next(iter(fake_s3.objects.values())))
        assert body["coverage_gaps"] == []

    def test_two_leagues_get_two_objects(self, fake_s3):
        coverage_gap_egress.write("u1", "lg1", LEAGUE_META, GAPS)
        coverage_gap_egress.write("u1", "lg2", LEAGUE_META, [])
        assert len(fake_s3.objects) == 2

    def test_delete_removes_the_object(self, fake_s3):
        coverage_gap_egress.write("u1", "lg1", LEAGUE_META, GAPS)
        coverage_gap_egress.delete("u1", "lg1")
        assert fake_s3.objects == {}

    def test_a_delete_of_a_never_written_league_does_not_raise(self, fake_s3):
        coverage_gap_egress.delete("u1", "never-existed")  # must not raise

    def test_a_broken_s3_client_never_raises(self, monkeypatch):
        """Advisory write — a league save must never fail because S3 is unreachable."""
        class Boom:
            def client(self, *a, **k):
                raise RuntimeError("no network")
        monkeypatch.setattr(coverage_gap_egress, "boto3", Boom())
        assert coverage_gap_egress.write("u1", "lg1", LEAGUE_META, GAPS) is False
        coverage_gap_egress.delete("u1", "lg1")  # must also not raise


BOARD = pd.DataFrame({"player_name": ["Samuel Basallo", "Chase DeLauter"]})


class TestTheBoardBuildReader:
    def test_round_trips_through_the_real_write(self, fake_s3):
        coverage_gap_egress.write("u1", "lg1", LEAGUE_META, GAPS)
        report = coverage_gap_report.build_report(BOARD)
        assert len(report) == 1
        assert report.iloc[0]["name"] == "Vance Honeycutt"
        assert report.iloc[0]["user_id"] == "u1"

    def test_still_missing_is_recomputed_against_this_boards_names_not_trusted_from_the_blob(
        self, fake_s3
    ):
        """The board-build-side self-heal: a name now ON the board reads still_missing=False even
        though the egressed object never learned that (it is only re-written on the NEXT league
        touch)."""
        already_added = [{**GAPS[0], "name": "Samuel Basallo"}]
        coverage_gap_egress.write("u1", "lg1", LEAGUE_META, already_added)
        report = coverage_gap_report.build_report(BOARD)
        assert report.iloc[0]["still_missing"] == False  # noqa: E712

    def test_no_objects_at_all_is_an_empty_report_not_an_error(self, fake_s3):
        report = coverage_gap_report.build_report(BOARD)
        assert report.empty

    def test_nothing_is_ever_merged_across_users(self, fake_s3):
        coverage_gap_egress.write("u1", "lg1", LEAGUE_META, GAPS)
        coverage_gap_egress.write("u2", "lg1", LEAGUE_META, [{**GAPS[0], "name": "D Lesko"}])
        report = coverage_gap_report.build_report(BOARD)
        assert set(report["user_id"]) == {"u1", "u2"}
        assert dict(zip(report["user_id"], report["name"])) == {"u1": "Vance Honeycutt",
                                                                 "u2": "D Lesko"}

    def test_a_malformed_object_is_skipped_not_fatal(self, fake_s3):
        """A legacy/hand-edited blob (or a future field-shape change) must not sink every other
        league's report — the E9.49 'one bad row must not blank the endpoint' rule."""
        coverage_gap_egress.write("u1", "good-league", LEAGUE_META, GAPS)
        fake_s3.objects[
            "baseball/milb/derived/prospect_board_coverage_gaps/user=u2/league=broken.json"
        ] = b"not json at all {{{"
        report = coverage_gap_report.build_report(BOARD)
        assert len(report) == 1
        assert report.iloc[0]["name"] == "Vance Honeycutt"

    def test_a_gap_missing_optional_fields_still_reports(self, fake_s3):
        """A legacy egress object written before a field existed (e.g. no `positions`) must still
        surface — missing optional context, not a dropped row."""
        sparse = [{"key": "k", "name": "Bare Minimum", "source": "suggested"}]
        coverage_gap_egress.write("u1", "lg1", LEAGUE_META, sparse)
        report = coverage_gap_report.build_report(BOARD)
        assert report.iloc[0]["name"] == "Bare Minimum"
        assert report.iloc[0]["org"] is None

    def test_a_coverage_gaps_field_that_is_not_a_list_is_skipped(self, fake_s3):
        fake_s3.objects[
            "baseball/milb/derived/prospect_board_coverage_gaps/user=u1/league=weird.json"
        ] = json.dumps({"user_id": "u1", "league_id": "weird", "coverage_gaps": "not-a-list"}).encode()
        report = coverage_gap_report.build_report(BOARD)
        assert report.empty

    def test_still_missing_rows_sort_first(self, fake_s3):
        coverage_gap_egress.write("u1", "lg1", LEAGUE_META, [
            {**GAPS[0], "name": "Samuel Basallo", "source": "confirmed"},   # on the board already
            {**GAPS[0], "name": "D Lesko", "source": "suggested"},          # still missing
        ])
        report = coverage_gap_report.build_report(BOARD)
        assert report.iloc[0]["name"] == "D Lesko"
        assert report.iloc[0]["still_missing"] == True  # noqa: E712
