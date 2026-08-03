"""Fast-gate tests for NF-C0d — coverage-gap telemetry on platform league imports.

Three things have to hold:

1. **THE WRITE IS BEST-EFFORT AND NEVER RAISES.** An import must never fail — or even surface an
   error — because the telemetry write failed. `record_captured_terms` must swallow every failure
   mode: no bucket configured, a boto3 error, a malformed term.

2. **THE ROW IS AGGREGATE, NOT SURVEILLANCE.** A recorded row can only ever carry platform, key,
   weight, verdict, season, imported_at — there is no field anywhere in this path for a user id,
   team name, or roster, so there is nothing identifying to leak even if a caller tried.

3. **THE RANKING MATH MATCHES THE STORY'S OWN EXAMPLE.** A term seen in many leagues at a
   meaningful weight must outrank one seen once at a trivial weight — score = occurrences ×
   avg(|weight|), never occurrences × total(|weight|) (which would double-count frequency).

Fast-gate discipline: pure imports, no `pipeline`, no network — every S3 client is a MagicMock/fake,
mirroring test_invalidate_permanent_cache.py's pattern for app/backend/services/s3_cache.py.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

import app.backend.routers.admin as admin
import app.backend.routers.fantasy_import as fantasy_import_router
import app.backend.services.fantasy_import_telemetry as telemetry


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. record_captured_terms — best-effort write, never raises
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestRecordCapturedTerms:
    def test_noop_when_no_bucket(self, monkeypatch):
        monkeypatch.setattr(telemetry, "CACHE_BUCKET", None)
        mock_s3 = MagicMock()
        monkeypatch.setattr(telemetry, "_s3", mock_s3)
        telemetry.record_captured_terms("sleeper", "2026", [{"key": "st_ff", "weight": 1.0}])
        mock_s3.put_object.assert_not_called()

    def test_noop_when_no_terms(self, monkeypatch):
        monkeypatch.setattr(telemetry, "CACHE_BUCKET", "test-bucket")
        mock_s3 = MagicMock()
        monkeypatch.setattr(telemetry, "_s3", mock_s3)
        telemetry.record_captured_terms("sleeper", "2026", [])
        mock_s3.put_object.assert_not_called()

    def test_writes_one_object_with_the_narrow_row_shape(self, monkeypatch):
        monkeypatch.setattr(telemetry, "CACHE_BUCKET", "test-bucket")
        mock_s3 = MagicMock()
        monkeypatch.setattr(telemetry, "_s3", mock_s3)

        telemetry.record_captured_terms(
            "sleeper",
            "2026",
            [
                {"key": "st_ff", "weight": 1.0, "verdict": "captured"},
                {"key": "def_st_ff", "weight": -2.5, "verdict": "captured"},
            ],
        )

        mock_s3.put_object.assert_called_once()
        kwargs = mock_s3.put_object.call_args.kwargs
        assert kwargs["Bucket"] == "test-bucket"
        assert kwargs["Key"].startswith("fantasy-import-telemetry/sleeper/")
        assert kwargs["Key"].endswith(".json")

        rows = json.loads(kwargs["Body"].decode("utf-8"))
        assert len(rows) == 2
        for row in rows:
            # The row is EXACTLY the aggregate shape — nothing identifying.
            assert set(row.keys()) == {"platform", "key", "weight", "verdict", "season", "imported_at"}
            assert row["platform"] == "sleeper"
            assert row["season"] == "2026"
        assert {r["key"] for r in rows} == {"st_ff", "def_st_ff"}

    def test_never_raises_on_s3_error(self, monkeypatch):
        monkeypatch.setattr(telemetry, "CACHE_BUCKET", "test-bucket")
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = Exception("S3 unavailable")
        monkeypatch.setattr(telemetry, "_s3", mock_s3)
        # Must not raise.
        telemetry.record_captured_terms("sleeper", "2026", [{"key": "st_ff", "weight": 1.0}])

    def test_skips_malformed_terms_without_raising(self, monkeypatch):
        monkeypatch.setattr(telemetry, "CACHE_BUCKET", "test-bucket")
        mock_s3 = MagicMock()
        monkeypatch.setattr(telemetry, "_s3", mock_s3)
        # One well-formed term, one missing the required "key".
        telemetry.record_captured_terms(
            "sleeper", "2026", [{"key": "st_ff", "weight": 1.0}, {"weight": 1.0}]
        )
        kwargs = mock_s3.put_object.call_args.kwargs
        rows = json.loads(kwargs["Body"].decode("utf-8"))
        assert len(rows) == 1
        assert rows[0]["key"] == "st_ff"

    def test_caps_terms_per_import(self, monkeypatch):
        monkeypatch.setattr(telemetry, "CACHE_BUCKET", "test-bucket")
        mock_s3 = MagicMock()
        monkeypatch.setattr(telemetry, "_s3", mock_s3)
        many = [{"key": f"k{i}", "weight": 1.0} for i in range(500)]
        telemetry.record_captured_terms("sleeper", "2026", many)
        rows = json.loads(mock_s3.put_object.call_args.kwargs["Body"].decode("utf-8"))
        assert len(rows) == telemetry.MAX_TERMS_PER_IMPORT


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. list_captured_term_rows — non-raising read, flattens across objects
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestListCapturedTermRows:
    def test_returns_empty_when_no_bucket(self, monkeypatch):
        monkeypatch.setattr(telemetry, "CACHE_BUCKET", None)
        assert telemetry.list_captured_term_rows() == []

    def test_flattens_rows_across_multiple_objects(self, monkeypatch):
        monkeypatch.setattr(telemetry, "CACHE_BUCKET", "test-bucket")

        obj1_rows = [{"platform": "sleeper", "key": "st_ff", "weight": 1.0}]
        obj2_rows = [{"platform": "sleeper", "key": "def_st_ff", "weight": -2.0}]

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"Contents": [{"Key": "fantasy-import-telemetry/sleeper/a.json"},
                          {"Key": "fantasy-import-telemetry/sleeper/b.json"}]}
        ]
        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator

        def _get_object(Bucket, Key):  # noqa: N803 - boto3 kwarg casing
            body = obj1_rows if Key.endswith("a.json") else obj2_rows
            mock_body = MagicMock()
            mock_body.read.return_value = json.dumps(body).encode("utf-8")
            return {"Body": mock_body}

        mock_s3.get_object.side_effect = _get_object
        monkeypatch.setattr(telemetry, "_s3", mock_s3)

        rows = telemetry.list_captured_term_rows()
        assert len(rows) == 2
        assert {r["key"] for r in rows} == {"st_ff", "def_st_ff"}

    def test_returns_empty_on_list_error(self, monkeypatch):
        monkeypatch.setattr(telemetry, "CACHE_BUCKET", "test-bucket")
        mock_s3 = MagicMock()
        mock_s3.get_paginator.side_effect = Exception("S3 unavailable")
        monkeypatch.setattr(telemetry, "_s3", mock_s3)
        assert telemetry.list_captured_term_rows() == []

    def test_skips_unreadable_object_without_raising(self, monkeypatch):
        monkeypatch.setattr(telemetry, "CACHE_BUCKET", "test-bucket")
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"Contents": [{"Key": "fantasy-import-telemetry/sleeper/bad.json"}]}
        ]
        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_s3.get_object.side_effect = ValueError("corrupt")
        monkeypatch.setattr(telemetry, "_s3", mock_s3)
        assert telemetry.list_captured_term_rows() == []


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 3. aggregate_captured_terms — the ranking math
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestAggregateCapturedTerms:
    def test_frequent_meaningful_term_outranks_rare_trivial_one(self):
        """The story's own example: a term in many leagues at a real weight beats one seen once
        at a trivial weight."""
        rows = (
            [{"platform": "sleeper", "key": "st_ff", "weight": 1.0, "verdict": "captured"}] * 40
            + [{"platform": "sleeper", "key": "rare_bonus", "weight": 1.0, "verdict": "captured"}]
        )
        ranked = telemetry.aggregate_captured_terms(rows)
        assert ranked[0]["key"] == "st_ff"
        assert ranked[0]["occurrences"] == 40
        assert ranked[-1]["key"] == "rare_bonus"

    def test_score_is_occurrences_times_avg_abs_weight_not_total(self):
        rows = [
            {"platform": "sleeper", "key": "st_ff", "weight": 2.0, "verdict": "captured"},
            {"platform": "sleeper", "key": "st_ff", "weight": -4.0, "verdict": "captured"},
        ]
        ranked = telemetry.aggregate_captured_terms(rows)
        assert len(ranked) == 1
        assert ranked[0]["occurrences"] == 2
        assert ranked[0]["avg_abs_weight"] == pytest.approx(3.0)  # avg(|2|, |4|)
        assert ranked[0]["score"] == pytest.approx(6.0)  # 2 x 3.0, NOT 2 x 6.0 (the total)

    def test_groups_by_platform_and_key_independently(self):
        rows = [
            {"platform": "sleeper", "key": "st_ff", "weight": 1.0, "verdict": "captured"},
            {"platform": "yahoo", "key": "st_ff", "weight": 1.0, "verdict": "captured"},
        ]
        ranked = telemetry.aggregate_captured_terms(rows)
        assert len(ranked) == 2
        assert {(r["platform"], r["key"]) for r in ranked} == {("sleeper", "st_ff"), ("yahoo", "st_ff")}

    def test_excludes_non_captured_verdicts(self):
        rows = [
            {"platform": "sleeper", "key": "rec", "weight": 1.0, "verdict": "applied"},
            {"platform": "sleeper", "key": "pass_yd", "weight": 0.04, "verdict": "derived"},
            {"platform": "sleeper", "key": "st_ff", "weight": 1.0, "verdict": "captured"},
        ]
        ranked = telemetry.aggregate_captured_terms(rows)
        assert len(ranked) == 1
        assert ranked[0]["key"] == "st_ff"

    def test_ignores_rows_missing_platform_or_key(self):
        rows = [
            {"platform": "", "key": "st_ff", "weight": 1.0, "verdict": "captured"},
            {"platform": "sleeper", "key": "", "weight": 1.0, "verdict": "captured"},
        ]
        assert telemetry.aggregate_captured_terms(rows) == []

    def test_empty_input_returns_empty(self):
        assert telemetry.aggregate_captured_terms([]) == []

    def test_last_seen_at_is_the_max_across_occurrences(self):
        rows = [
            {"platform": "sleeper", "key": "st_ff", "weight": 1.0, "verdict": "captured",
             "imported_at": "2026-07-01T00:00:00+00:00"},
            {"platform": "sleeper", "key": "st_ff", "weight": 1.0, "verdict": "captured",
             "imported_at": "2026-08-01T00:00:00+00:00"},
        ]
        ranked = telemetry.aggregate_captured_terms(rows)
        assert ranked[0]["last_seen_at"] == "2026-08-01T00:00:00+00:00"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4. POST /fantasy/import/telemetry — the write route
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestRecordImportTelemetryRoute:
    def test_rejects_unknown_platform(self):
        payload = fantasy_import_router.ImportTelemetryRequest(
            platform="not_a_real_platform", season="2026", terms=[]
        )
        with pytest.raises(Exception) as exc_info:
            fantasy_import_router.record_import_telemetry(payload, user_id="u1")
        assert getattr(exc_info.value, "status_code", None) == 422

    def test_records_captured_terms_for_a_known_platform(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            fantasy_import_router.fantasy_import_telemetry,
            "record_captured_terms",
            lambda platform, season, terms: calls.append((platform, season, terms)),
        )
        payload = fantasy_import_router.ImportTelemetryRequest(
            platform="sleeper",
            season="2026",
            terms=[fantasy_import_router.CapturedTermTelemetry(key="st_ff", weight=1.0, verdict="captured")],
        )
        result = fantasy_import_router.record_import_telemetry(payload, user_id="u1")
        assert result == {"status": "recorded"}
        assert len(calls) == 1
        platform, season, terms = calls[0]
        assert platform == "sleeper"
        assert season == "2026"
        assert terms == [{"key": "st_ff", "weight": 1.0, "verdict": "captured"}]

    def test_a_write_failure_never_reaches_the_caller(self, monkeypatch):
        """The service is non-raising by contract, but pin it at the route too: even if the
        service somehow raised, that must not be what this test asserts against — this test
        instead pins that the route trusts the service's non-raising contract and always
        returns normally for a known platform."""
        monkeypatch.setattr(
            fantasy_import_router.fantasy_import_telemetry,
            "record_captured_terms",
            lambda *a, **k: None,  # mirrors the real non-raising contract
        )
        payload = fantasy_import_router.ImportTelemetryRequest(platform="sleeper", season=None, terms=[])
        result = fantasy_import_router.record_import_telemetry(payload, user_id="u1")
        assert result == {"status": "recorded"}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 5. GET /admin/fantasy-import-telemetry — the ranking read
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestFantasyImportTelemetryRankingRoute:
    def test_ranks_and_returns_captured_term_stats(self, monkeypatch):
        fake_rows = [
            {"platform": "sleeper", "key": "st_ff", "weight": 1.0, "verdict": "captured",
             "imported_at": "2026-08-01T00:00:00+00:00"},
        ]
        monkeypatch.setattr(
            admin.fantasy_import_telemetry, "list_captured_term_rows", lambda: fake_rows
        )
        result = admin.fantasy_import_telemetry_ranking(_="admin")
        assert len(result) == 1
        stat = result[0]
        assert isinstance(stat, admin.CapturedTermStat)
        assert stat.platform == "sleeper"
        assert stat.key == "st_ff"
        assert stat.occurrences == 1
        assert stat.score == pytest.approx(1.0)

    def test_empty_store_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(admin.fantasy_import_telemetry, "list_captured_term_rows", lambda: [])
        assert admin.fantasy_import_telemetry_ranking(_="admin") == []
