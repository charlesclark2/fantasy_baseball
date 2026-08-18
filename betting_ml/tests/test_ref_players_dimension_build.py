"""
test_ref_players_dimension_build.py   (E5.10 follow-up — the merge SQL itself; fast gate)
=========================================================================================
Runs the REAL ``build_ref_players_dimension.build_sql`` against REAL parquet on a REAL DuckDB
connection. Only the location is swapped (local files instead of S3) — the SQL, the layering and
the coalescing are the shipped ones.

⭐ WHY THIS FILE EXISTS — a production BinderException that a green suite could not have caught.

    ``build_sql`` branches on whether the live profiles parquet carries first_name/last_name:

        live_first = "first_name" if "first_name" in live_cols else "cast(null as varchar)"

    The first cut emitted ``l.first_name`` for the present-branch. That is wrong — the fragment is
    interpolated into the INNER ``live`` subquery, whose only table is ``player_profiles_raw``,
    while ``l`` is the OUTER join alias. But the ABSENT-branch fragment (``cast(null as varchar)``)
    carries no alias at all, so it bound perfectly; and at the time the code was written the live
    parquet did not yet have the columns, so every local smoke, the box smoke and the first
    production run all took the absent branch. The aliased branch executed for the first time in
    production, immediately after the profiles backfill landed the columns, and raised
    ``Binder Error: Referenced table "l" not found``.

    That is the NF-C0e "wired ≠ invoked" class inside a single conditional: a branch that exists,
    is reachable, and is never executed is untested no matter how green the suite is. The cure is
    not "add a test", it is **run both arms**, which is what the parametrisation below does.

Fast-gate-safe: no ``pipeline`` import, no S3, no network — DuckDB over tmp_path parquet.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _PROJECT_ROOT / "scripts" / "build_ref_players_dimension.py"


def _load():
    spec = importlib.util.spec_from_file_location("_ref_players_builder", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


B = _load()


def _fixture_conn(tmp_path: Path, *, live_has_parts: bool):
    """Build the three source parquets and register them under the module's own table names.

    The population is deliberately shaped like the real one:
      * 700001 — in BOTH sources (a normal modern player)
      * 700002 — LIVE ONLY, plays in the current season (a 2026 debutant: the E5.10 victim)
      * 700003 — ARCHIVE ONLY, no recent appearances (a pre-2020 retiree the live feed lacks)
    """
    import duckdb

    tmp_path.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    parts_cols = (
        ", 'Aaron' AS first_name, 'Judge' AS last_name"
        if live_has_parts else ""
    )
    parts_cols2 = (
        ", 'Travis' AS first_name, 'Bazzana' AS last_name"
        if live_has_parts else ""
    )
    live = tmp_path / "live.parquet"
    con.execute(f"""
        COPY (
            SELECT 700001 AS player_id, 'Aaron Judge' AS full_name,
                   '2026-08-16 10:00:00' AS last_fetched_at{parts_cols}
            UNION ALL
            SELECT 700002, 'Travis Bazzana', '2026-08-16 10:00:00'{parts_cols2}
        ) TO '{live}' (FORMAT PARQUET)
    """)

    archive = tmp_path / "archive.parquet"
    con.execute(f"""
        COPY (
            SELECT 700001 AS mlb_bam_id, 'Aaron' AS first_name, 'Judge' AS last_name,
                   'Judge, Aaron' AS player_name, 2016.0 AS mlb_played_first,
                   2025.0 AS mlb_played_last
            UNION ALL
            SELECT 700003, 'Old', 'Timer', 'Timer, Old', 2005.0, 2011.0
        ) TO '{archive}' (FORMAT PARQUET)
    """)

    # game_year stored as VARCHAR, as the lakehouse stores things (INC-23) — so the ::integer
    # casts in the real SQL are genuinely exercised rather than bypassed by a convenient type.
    games = tmp_path / "games.parquet"
    con.execute(f"""
        COPY (
            SELECT 700001 AS batter_id, 700002 AS pitcher_id, '2026' AS game_year
            UNION ALL
            SELECT 700001, 700002, '2025'
        ) TO '{games}' (FORMAT PARQUET)
    """)

    con.execute(f"CREATE VIEW {B.LIVE_PREFIX} AS SELECT * FROM read_parquet('{live}')")
    con.execute(f"CREATE VIEW {B.ARCHIVE_PREFIX} AS SELECT * FROM read_parquet('{archive}')")
    con.execute(f"CREATE VIEW {B.GAME_PREFIX} AS SELECT * FROM read_parquet('{games}')")
    return con


@pytest.mark.parametrize("live_has_parts", [False, True], ids=["live_lacks_parts", "live_has_parts"])
def test_the_merge_sql_binds_and_layers_correctly_on_both_branches(tmp_path, live_has_parts):
    """THE REGRESSION. `live_has_parts=True` is the arm that raised in production.

    Parametrised rather than written once, because the whole defect was that only one arm had ever
    been executed — a single-arm test would reproduce the blind spot exactly.
    """
    con = _fixture_conn(tmp_path, live_has_parts=live_has_parts)
    live_cols = B._columns_of(con, B.LIVE_PREFIX)
    assert ({"first_name", "last_name"} <= live_cols) is live_has_parts, (
        "the fixture does not actually realise the branch under test — the parametrisation would "
        "be running the same arm twice"
    )

    # Must not raise: this is the BinderException the box hit.
    rows = {r[0]: r for r in con.execute(B.build_sql(live_cols, current_season=2026)).fetchall()}
    cols = [d[0] for d in con.execute(
        B.build_sql(live_cols, current_season=2026) + " LIMIT 0").description]

    # Contract preserved, in order, plus the additive build stamp.
    assert cols[:len(B.CONTRACT_COLUMNS)] == list(B.CONTRACT_COLUMNS)
    assert cols[-1] == "built_at"

    # Union of both sources — neither layer may drop players.
    assert set(rows) == {700001, 700002, 700003}

    idx = {c: i for i, c in enumerate(cols)}

    # The 2026 debutant is LIVE-ONLY and must carry the current season, derived from appearances.
    # This is the E5.10 symptom: before the fix this player did not exist in the dimension at all.
    assert rows[700002][idx["mlb_played_last"]] == 2026
    assert rows[700002][idx["player_name"]] is not None

    # The pre-2020 retiree is ARCHIVE-ONLY and must survive with its archived career span.
    assert rows[700003][idx["player_name"]] == "Timer, Old"
    assert rows[700003][idx["mlb_played_last"]] == 2011

    # Appearances OVERRIDE the archive's stale span: the archive says 2025, the games say 2026.
    assert rows[700001][idx["mlb_played_last"]] == 2026
    assert rows[700001][idx["mlb_played_first"]] == 2025


def test_live_name_parts_are_used_when_present_and_never_split_when_absent(tmp_path):
    """The live-only debutant is the only row that can distinguish the two branches.

    With parts, it renders the canonical "Last, First". Without them it falls back to the live
    full_name — ⛔ never a split of that full name, which would be wrong for every multi-word
    surname (NF-C0e / E9.61).
    """
    with_parts = _fixture_conn(tmp_path / "a", live_has_parts=True)
    without = _fixture_conn(tmp_path / "b", live_has_parts=False)

    def row(con):
        cols = B._columns_of(con, B.LIVE_PREFIX)
        out = con.execute(B.build_sql(cols, current_season=2026)).fetchall()
        return next(r for r in out if r[0] == 700002)

    r_with, r_without = row(with_parts), row(without)

    # (mlb_bam_id, first_name, last_name, player_name, ...)
    assert (r_with[1], r_with[2]) == ("Travis", "Bazzana")
    assert r_with[3] == "Bazzana, Travis", "known parts must render the canonical 'Last, First'"

    assert (r_without[1], r_without[2]) == (None, None), (
        "with no stated parts the dimension must leave them NULL — inferring them by splitting "
        "full_name is the name-mangling defect this design exists to avoid"
    )
    assert r_without[3] == "Travis Bazzana", (
        "the display name must still fall back to the live full_name, so the player is NAMED "
        "rather than absent (strictly better than the pre-fix state)"
    )


def test_the_absent_branch_emits_no_table_alias(tmp_path):
    """A targeted pin on the exact production failure.

    The bug was an out-of-scope `l.` qualifier reaching the inner subquery. Assert neither branch
    emits a qualified name-part reference, so the regression cannot return in either arm.
    """
    for cols in ({"player_id", "full_name"}, {"player_id", "full_name", "first_name", "last_name"}):
        sql = B.build_sql(cols, current_season=2026)
        head = sql[:sql.index("archive as")]        # the `live` CTE only
        assert "l.first_name" not in head and "l.last_name" not in head, (
            "the live CTE qualified a name part with the OUTER join alias `l`, which is not in "
            'scope there — this is the exact production BinderException ("Referenced table \\"l\\" '
            'not found")'
        )
