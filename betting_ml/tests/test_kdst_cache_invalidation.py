"""NF-C0e follow-up — a cached lake read must INVALIDATE when its query changes.

🚨 THE BUG THIS EXISTS FOR (2026-08-03, reached PROD). `load_team_defense_seasons` cached to
`team_defense_{lo}_{hi}.parquet` — keyed on the season range ALONE. NF-C0e added
`def_fumbles_forced` to `_TEAM_DEF_SQL` and graduated `def_forced_fumble` to APPLIED on held-out
evidence; the on-disk cache predated that edit, so the loader kept returning the OLD column set.
`build_dst_training_panel` then SKIPPED the absent component (its honest fallback),
`fit_dst_component_model` never fitted it, `project_dst` emitted nothing, and the published
projection carried `proj_def_forced_fumble` as **0 of 32 non-null** while every sibling component
was fully populated.

⚠️ WHY A WARNING WOULD NOT HAVE BEEN ENOUGH, and why these tests assert on the KEY. The
absent-component path is deliberately silent because silence is CORRECT there: a component the
history genuinely lacks must be skipped, never zero-filled (a zero-filled component gets fitted and
scored as APPLIED against fabricated data). That correct behaviour is precisely what converts "my
cache is stale" into "this feature isn't available" with no error anywhere. So the fix has to make a
stale cache impossible to READ.

⭐ AND IT IS INVISIBLE IN A FRESH CHECKOUT. A new worktree has no `artifacts/` directory, rebuilds
from the lake, and PASSES — the end-to-end verification that missed this ran in exactly such a
checkout. Same class as the board-export stale-source landmine in CLAUDE.md: an on-disk artifact
precedence bug cannot be reproduced where the artifact is absent. These tests therefore CONSTRUCT
the stale artifact rather than relying on whatever happens to be on disk.
"""
from __future__ import annotations

import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import kdst_source as KS


class _FakeCon:
    """A DuckDB stand-in that returns a frame whose columns follow the SQL it was handed."""

    def __init__(self, df: pd.DataFrame):
        self._df = df
        self.queries: list[str] = []

    def sql(self, q: str):
        self.queries.append(q)
        return self

    def df(self) -> pd.DataFrame:
        return self._df.copy()


def _team_def_frame(*, with_forced_fumble: bool) -> pd.DataFrame:
    df = pd.DataFrame({
        "season": [2024, 2024], "team": ["DEN", "BUF"], "games": [17.0, 17.0],
        "def_sacks": [63.0, 39.0], "def_int": [17.0, 15.0], "def_fumble_rec": [9.0, 11.0],
        "def_td": [4.0, 2.0], "st_td": [0.0, 1.0], "def_safety": [1.0, 0.0],
        "def_blocked_kick": [2.0, 1.0],
    })
    if with_forced_fumble:
        df["def_forced_fumble"] = [14.0, 12.0]
    return df


@pytest.fixture()
def cache_dir(tmp_path):
    return tmp_path / "kdst_team_defense_cache"


def test_a_stale_cache_written_before_a_new_column_is_NOT_served(cache_dir, monkeypatch):
    """The exact prod failure, reconstructed: an old cache must not satisfy a widened query.

    Writes the pre-NF-C0e cache (no `def_forced_fumble`) under the OLD un-fingerprinted name, then
    loads with the CURRENT query. The load must go back to the lake and return the new column."""
    monkeypatch.setattr(KS, "_ensure_s3", lambda con: None)
    cache_dir.mkdir(parents=True)
    legacy = cache_dir / "team_defense_1999_2026.parquet"
    _team_def_frame(with_forced_fumble=False).to_parquet(legacy, index=False)

    con = _FakeCon(_team_def_frame(with_forced_fumble=True))
    out = KS.load_team_defense_seasons(con, 1999, 2026, cache_dir=cache_dir)

    assert con.queries, "a stale-schema cache was served instead of re-reading the lake"
    assert "def_forced_fumble" in out.columns
    assert out["def_forced_fumble"].notna().all()


def test_the_guard_would_actually_catch_the_bug_it_was_written_for(cache_dir, monkeypatch):
    """RED-proof: under the OLD (range-only) cache key the test above cannot fail.

    Re-creates the pre-fix behaviour exactly — read `team_defense_{lo}_{hi}.parquet` if it exists —
    and asserts it silently returns the stale column set. Without this, a regression that reverted
    the fingerprint could leave the suite green if some other clause happened to reject the
    fixture (the NF-D17 vacuous-guard lesson)."""
    cache_dir.mkdir(parents=True)
    legacy = cache_dir / "team_defense_1999_2026.parquet"
    _team_def_frame(with_forced_fumble=False).to_parquet(legacy, index=False)

    def _pre_fix_load(con, lo, hi, *, cache_dir):
        cache = cache_dir / f"team_defense_{lo}_{hi}.parquet"
        if cache.exists():
            return pd.read_parquet(cache)
        return con.sql("...").df()

    con = _FakeCon(_team_def_frame(with_forced_fumble=True))
    stale = _pre_fix_load(con, 1999, 2026, cache_dir=cache_dir)
    assert not con.queries, "the pre-fix reader is supposed to serve the cache"
    assert "def_forced_fumble" not in stale.columns, (
        "this test no longer reproduces the original bug, so the guard above proves nothing"
    )


def test_an_unchanged_query_still_hits_the_cache(cache_dir, monkeypatch):
    """The fingerprint must not defeat caching — a re-run with no edit reads from disk.

    Without this, 'always miss' would pass every other test here while quietly turning a ~instant
    re-run into a full lake scan."""
    monkeypatch.setattr(KS, "_ensure_s3", lambda con: None)
    con = _FakeCon(_team_def_frame(with_forced_fumble=True))
    first = KS.load_team_defense_seasons(con, 1999, 2026, cache_dir=cache_dir)
    n_after_first = len(con.queries)
    second = KS.load_team_defense_seasons(con, 1999, 2026, cache_dir=cache_dir)

    assert n_after_first == 1
    assert len(con.queries) == 1, "an unchanged query re-read the lake instead of the cache"
    pd.testing.assert_frame_equal(first, second)


def test_writing_a_new_fingerprint_prunes_the_superseded_file(cache_dir, monkeypatch):
    """A query edit must not leave one orphaned parquet per historical version on disk."""
    monkeypatch.setattr(KS, "_ensure_s3", lambda con: None)
    cache_dir.mkdir(parents=True)
    (cache_dir / "team_defense_1999_2026.parquet").write_bytes(
        _team_def_frame(with_forced_fumble=False).to_parquet(index=False)
    )
    con = _FakeCon(_team_def_frame(with_forced_fumble=True))
    KS.load_team_defense_seasons(con, 1999, 2026, cache_dir=cache_dir)

    files = sorted(p.name for p in cache_dir.glob("*.parquet"))
    assert len(files) == 1, f"superseded cache files were not pruned: {files}"
    assert "def_forced_fumble" in pd.read_parquet(cache_dir / files[0]).columns


def test_refresh_still_forces_a_rebuild(cache_dir, monkeypatch):
    monkeypatch.setattr(KS, "_ensure_s3", lambda con: None)
    con = _FakeCon(_team_def_frame(with_forced_fumble=True))
    KS.load_team_defense_seasons(con, 1999, 2026, cache_dir=cache_dir)
    KS.load_team_defense_seasons(con, 1999, 2026, cache_dir=cache_dir, refresh=True)
    assert len(con.queries) == 2


def test_the_fingerprint_ignores_whitespace_but_not_columns():
    """Reformatting a query must not invalidate the cache; changing its SELECT list must."""
    base = "select a, b from t"
    assert KS._sql_fingerprint(base) == KS._sql_fingerprint("select   a,\n  b\nfrom t")
    assert KS._sql_fingerprint(base) != KS._sql_fingerprint("select a, b, c from t")


def test_every_cached_reader_routes_through_the_shared_helper():
    """A new cached reader must not hand-roll the read/write pair that caused this bug.

    The registry is the point: the fix is only as good as its coverage, and the original defect was
    a per-reader implementation detail. `load_team_yards` is deliberately NOT here — it does not
    cache, which is exactly why the yards-allowed family shipped correctly while forced fumbles did
    not."""
    import inspect

    src = inspect.getsource(KS)
    for reader in ("load_team_defense_seasons", "load_kicker_seasons"):
        body = src.split(f"def {reader}(")[1].split("\ndef ")[0]
        assert "_read_cached_lake_query" in body, f"{reader} does not use the shared cached read"
        assert "_sql_fingerprint" in body, f"{reader}'s cache key omits the query fingerprint"
        assert "read_parquet" not in body, f"{reader} still hand-rolls its cache read"
