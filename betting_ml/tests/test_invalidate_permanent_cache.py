"""E9.28 / INC-16-P2 — unit tests for bulk permanent-cache invalidation.

Tests cover serving_cache.invalidate_permanent_picks (DynamoDB; replaced the
Railway PG api_cache in INC-16-P2) and s3_cache.invalidate_permanent_picks
without hitting real infrastructure. Both functions must:
  - Return 0 (not raise) when the backing store is unavailable.
  - Return the count of items deleted when the store is available.
  - Target only picks/game/* keys — not the full permanent prefix.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# serving_cache.invalidate_permanent_picks (DynamoDB)
# ---------------------------------------------------------------------------

def _mock_table():
    tbl = MagicMock()
    batch = MagicMock()

    @contextmanager
    def _bw():
        yield batch

    tbl.batch_writer.side_effect = _bw
    tbl._batch = batch
    return tbl


class TestServingCacheInvalidatePermanentPicks:
    def test_returns_zero_on_error(self):
        """Gracefully returns 0 when DynamoDB is unavailable."""
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        tbl.query.side_effect = Exception("ddb down")
        with patch.object(sc, "_table", return_value=tbl):
            assert sc.invalidate_permanent_picks() == 0

    def test_deletes_permanent_picks_items(self):
        """Queries pk=picks + begins_with game/ with an is_permanent filter and
        batch-deletes each matched item, returning the count."""
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        tbl.query.return_value = {"Items": [
            {"pk": "picks", "sk": "game/1#PERMANENT"},
            {"pk": "picks", "sk": "game/2#PERMANENT"},
            {"pk": "picks", "sk": "game/3#PERMANENT"},
        ]}
        with patch.object(sc, "_table", return_value=tbl):
            result = sc.invalidate_permanent_picks()
        assert result == 3
        assert tbl._batch.delete_item.call_count == 3
        assert "FilterExpression" in tbl.query.call_args.kwargs


# ---------------------------------------------------------------------------
# s3_cache.invalidate_permanent_picks
# ---------------------------------------------------------------------------

class TestS3InvalidatePermanentPicks:
    def test_returns_zero_when_no_bucket(self, monkeypatch):
        """Returns 0 when CACHE_BUCKET env var is absent."""
        import app.backend.services.s3_cache as s3_mod
        monkeypatch.setattr(s3_mod, "CACHE_BUCKET", None)
        result = s3_mod.invalidate_permanent_picks()
        assert result == 0

    def test_deletes_only_permanent_picks_prefix(self, monkeypatch):
        """Paginates api-cache/permanent/picks/game and deletes each object."""
        import app.backend.services.s3_cache as s3_mod

        monkeypatch.setattr(s3_mod, "CACHE_BUCKET", "test-bucket")

        fake_objects = [
            {"Key": "api-cache/permanent/picks/game/123.json"},
            {"Key": "api-cache/permanent/picks/game/456.json"},
        ]
        fake_page = {"Contents": fake_objects}

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [fake_page]

        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator

        monkeypatch.setattr(s3_mod, "_s3", mock_s3)

        result = s3_mod.invalidate_permanent_picks()

        assert result == 2
        # Confirm paginator was called with the targeted prefix only
        paginate_kwargs = mock_paginator.paginate.call_args[1]
        assert paginate_kwargs["Prefix"] == "api-cache/permanent/picks/game"
        assert paginate_kwargs["Bucket"] == "test-bucket"
        # Confirm each object was deleted
        assert mock_s3.delete_object.call_count == 2

    def test_returns_zero_on_s3_error(self, monkeypatch):
        """Returns 0 (not raises) when S3 throws."""
        import app.backend.services.s3_cache as s3_mod

        monkeypatch.setattr(s3_mod, "CACHE_BUCKET", "test-bucket")

        mock_s3 = MagicMock()
        mock_s3.get_paginator.side_effect = Exception("S3 unavailable")
        monkeypatch.setattr(s3_mod, "_s3", mock_s3)

        result = s3_mod.invalidate_permanent_picks()
        assert result == 0

    def test_empty_prefix_returns_zero(self, monkeypatch):
        """Returns 0 (not raises) when the prefix has no objects."""
        import app.backend.services.s3_cache as s3_mod

        monkeypatch.setattr(s3_mod, "CACHE_BUCKET", "test-bucket")

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{}]  # no "Contents" key

        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        monkeypatch.setattr(s3_mod, "_s3", mock_s3)

        result = s3_mod.invalidate_permanent_picks()
        assert result == 0
        mock_s3.delete_object.assert_not_called()
