"""E9.28 — unit tests for bulk permanent-cache invalidation.

Tests cover pg.invalidate_permanent_picks and s3_cache.invalidate_permanent_picks
without hitting real infrastructure. Both functions must:
  - Return 0 (not raise) when the backing store is unavailable.
  - Return the count of items deleted when the store is available.
  - Target only picks/game/* keys — not the full permanent prefix.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# pg.invalidate_permanent_picks
# ---------------------------------------------------------------------------

class TestPgInvalidatePermanentPicks:
    def test_returns_zero_when_no_pool(self):
        """Gracefully returns 0 when DATABASE_URL is unset (pool is None)."""
        import app.backend.services.pg as pg_mod
        with patch.object(pg_mod, "_get_pool", return_value=None):
            result = pg_mod.invalidate_permanent_picks()
        assert result == 0

    def test_deletes_permanent_picks_rows(self):
        """Issues DELETE with is_permanent=TRUE and picks/game/% and returns rowcount."""
        import app.backend.services.pg as pg_mod

        mock_cur = MagicMock()
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.rowcount = 7

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn

        with patch.object(pg_mod, "_get_pool", return_value=mock_pool):
            result = pg_mod.invalidate_permanent_picks()

        assert result == 7
        executed_sql = mock_cur.execute.call_args[0][0]
        assert "is_permanent = TRUE" in executed_sql
        assert "picks/game/%" in executed_sql
        mock_conn.commit.assert_called_once()

    def test_returns_zero_and_rolls_back_on_db_error(self):
        """Returns 0 (not raises) and rolls back if the DELETE throws."""
        import app.backend.services.pg as pg_mod

        mock_cur = MagicMock()
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.execute.side_effect = Exception("connection reset")

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn

        with patch.object(pg_mod, "_get_pool", return_value=mock_pool):
            result = pg_mod.invalidate_permanent_picks()

        assert result == 0
        mock_conn.rollback.assert_called_once()


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
