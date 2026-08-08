"""E11.24 target-6 successor — guards for the EB reader repoint + the two view flips.

THE CHANGE THIS PINS. On the clean 2026-08-07 tick band (14-23 UTC) the intraday lineup tick's
remaining COMPUTE_WH waits sat 3/3 on the ``eb_starter_posteriors`` and ``eb_batter_posteriors_raw``
MERGEs. #662 correctly refused to flip them, because ``update_player_posteriors_op`` read both
from Snowflake even under ``--s3``, so a flip would have changed the rows a live daily op consumes.
This change removes that blocker (the reads move to the S3 lakehouse) and then flips both models'
Snowflake branches to metadata-only views.

⚠️ CROSS-PR NOTE: #662 ships ``test_e11_24_pregame_features_are_views.py``, whose
``NOT_FLIPPABLE`` clause asserts these two models are NOT views. That guard is doing its job — it
exists to stop a *sweep-in*, and its own docstring names this change as the sanctioned way out
("Repoint that reader to S3 first, then flip it as its own change"). When both land, the EB pair
moves from that file's ``NOT_FLIPPABLE`` dict into its ``EXT_COPY_VIEW_MODELS`` dict. See the
session handoff for the exact edit.

RED-PROOF DISCIPLINE (NF-D17): every clause below is exercised by a fixture that satisfies every
OTHER clause, so deleting the clause it names is the ONLY thing that can turn it red. The
behavioural tests are deliberately not source inspection — a test that reads a value back under
the key the code wrote cannot catch a wrong key (NF-C0e), so the routing guards prove the read
NEVER TOUCHES SNOWFLAKE by handing the loader a connection that raises on use.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

EB_MODELS = {
    "eb_starter_posteriors": "dbt/models/eb_posteriors/eb_starter_posteriors.sql",
    "eb_batter_posteriors_raw": "dbt/models/eb_posteriors/eb_batter_posteriors_raw.sql",
}


# ── helpers ────────────────────────────────────────────────────────────────────────────────

def _strip_sql_comments(sql: str) -> str:
    """Drop ``--`` comment text so prose can never satisfy a source assertion (INC-38).

    These model headers explain the flip at length and name every retired construct
    (``incremental``, ``merge``, ``is_incremental``), so an un-stripped search would match the
    explanation and pass on source that had been reverted.
    """
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def _snowflake_branch(model: str) -> str:
    """ONLY the ``{% else %}`` (Snowflake) branch of a dual-branch model, comments stripped.

    Load-bearing: the DuckDB branch declares its own ``config()`` and must STAY incremental (it
    is where the real assembly runs), so an assertion over the whole file would read the wrong
    branch in both directions.
    """
    src = (REPO / EB_MODELS[model]).read_text()
    assert "{% else %}" in src, f"{model}: no {{% else %}} branch — the dual-branch shape changed."
    return _strip_sql_comments(src.split("{% else %}")[-1])


def _duckdb_branch(model: str) -> str:
    src = (REPO / EB_MODELS[model]).read_text()
    return _strip_sql_comments(src.split("{% else %}")[0])


class _ExplodingConnection:
    """A Snowflake connection that fails the moment anything tries to USE it.

    This is what makes the routing guards real rather than a restatement of the source: if the
    ``--s3`` path ever falls back to Snowflake for an EB read, the test raises here instead of
    quietly returning a plausible answer.
    """

    def __init__(self) -> None:
        self.used = False

    def cursor(self):  # pragma: no cover - the assertion is that this never runs
        self.used = True
        raise AssertionError(
            "the --s3 path issued a SNOWFLAKE read for an EB table — that is exactly the "
            "dependency this change exists to remove, and it blocks the view flip."
        )

    def close(self) -> None:
        pass


@pytest.fixture
def eb_duck():
    """An in-memory DuckDB carrying the three EB tables under their bare lakehouse names.

    Hermetic by design (fast-gate rule: no network, no S3). The rows encode the two cases the
    rewrite has to get right:
      • player 111 has TWO seasons, so the ``season =`` filter has to bite;
      • player 222's season-first row is decided by a same-date game_pk tie-break, which is the
        case a LEXICOGRAPHIC ordering over the parquet's VARCHAR game_pk would get wrong once
        game_pks grow past 6 digits.
    """
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect()
    con.execute("""
        create table eb_batter_posteriors_raw (
            game_pk varchar, batting_slot integer, batter_id varchar, season bigint,
            game_date date, eb_woba double, eb_woba_uncertainty double)
    """)
    con.execute("""
        insert into eb_batter_posteriors_raw values
            -- player 111: prior season must be excluded by the season filter
            ('900001', 1, '111', 2025, date '2025-04-01', 0.111, 0.011),
            ('900002', 1, '111', 2026, date '2026-04-02', 0.222, 0.022),
            -- player 222: same-date doubleheader. 999999 < 1000000 numerically, but
            -- '1000000' < '999999' lexicographically -> the two orderings disagree.
            ('1000000', 2, '222', 2026, date '2026-04-03', 0.444, 0.044),
            ('999999',  2, '222', 2026, date '2026-04-03', 0.333, 0.033),
            -- a null metric must be filtered out, not seeded as the season-first row
            ('900000', 3, '333', 2026, date '2026-04-01', NULL,  0.099),
            ('900003', 3, '333', 2026, date '2026-04-04', 0.555, 0.055)
    """)
    con.execute("""
        create table eb_starter_posteriors (
            game_pk varchar, pitcher_id varchar, season bigint, game_date date,
            eb_xwoba_against double, eb_xwoba_uncertainty double)
    """)
    con.execute("""
        insert into eb_starter_posteriors values
            ('900010', 'SP1', 2026, date '2026-04-02', 0.300, 0.030),
            ('900011', 'SP1', 2026, date '2026-04-09', 0.310, 0.031),
            ('900012', 'SP2', 2026, date '2026-04-03', 0.320, 0.032)
    """)
    con.execute("""
        create table eb_bullpen_posteriors (
            game_pk varchar, pitcher_id varchar, season bigint, game_date date,
            eb_xwoba_against double, eb_xwoba_uncertainty double)
    """)
    con.execute("""
        insert into eb_bullpen_posteriors values
            ('900010', 'RP1', 2026, date '2026-04-02', 0.290, 0.029),
            -- RP2 relieves in the SAME game SP2 starts: the union must resolve to 'starter'
            ('900012', 'SP2', 2026, date '2026-04-03', 0.280, 0.028)
    """)
    return con


@pytest.fixture
def upp():
    from betting_ml.scripts.sequential_bayes import update_player_posteriors as module
    return module


# ── 1. the reader repoint: the EB reads must not touch Snowflake under --s3 ────────────────

def test_the_cold_start_prior_read_never_touches_snowflake_under_s3(upp, eb_duck) -> None:
    """1. ``_load_eb_priors`` reads all three EB tables off DuckDB when ``duck`` is supplied.

    This is THE precondition for the view flip: it is the read whose consumption spans the whole
    accumulated history (season-first appearance per player), so it is the one a
    merge-accumulated-superset vs current-rebuild divergence actually moves.
    """
    conn = _ExplodingConnection()
    priors = upp._load_eb_priors(conn, 2026, duck=eb_duck)

    assert conn.used is False
    assert priors["batter"]["111"] == (0.222, 0.022), "the season filter did not bite"
    assert priors["batter"]["333"] == (0.555, 0.055), "a NULL metric row was seeded as season-first"
    assert priors["starter"]["SP1"] == (0.300, 0.030), "season-first is not the earliest game_date"
    assert priors["bullpen"]["RP1"] == (0.290, 0.029), "the bullpen side did not route to DuckDB"


def test_the_season_first_tie_break_is_numeric_not_lexicographic(upp, eb_duck) -> None:
    """2. A same-date tie resolves on game_pk as a NUMBER, matching Snowflake.

    game_pk is NUMBER on Snowflake and VARCHAR in the parquet. Every game_pk is 6 characters
    today (measured 2026-08-08: min=max=6 in all three tables, and the two orderings pick the
    same season-first row for 0 players), so this is HARDENING against a 7-digit gamePk rather
    than a fix for a live defect — which is exactly why it needs a fixture that straddles the
    boundary, since live data cannot make it fail.
    """
    priors = upp._load_eb_priors(_ExplodingConnection(), 2026, duck=eb_duck)
    assert priors["batter"]["222"] == (0.333, 0.033), (
        "the tie-break picked game_pk '1000000' over '999999' — that is a LEXICOGRAPHIC sort of "
        "the parquet's VARCHAR game_pk, which disagrees with Snowflake's NUMBER ordering."
    )


def test_the_pitcher_role_read_never_touches_snowflake_under_s3(upp, eb_duck) -> None:
    """3. BOTH halves of the role map come from DuckDB — never one side per backend.

    ``_load_pitcher_roles`` UNIONS the starter and bullpen reads into ONE dict. Repointing only
    the starter side would build that map from two vintages (current rebuild + accumulated
    superset), so a pitcher's role could depend on which side happened to carry a ghost. The
    bullpen assertion below is what makes this clause independent of clause 1.
    """
    conn = _ExplodingConnection()
    roles = upp._load_pitcher_roles(conn, date(2026, 4, 2), duck=eb_duck)

    assert conn.used is False
    assert roles[("SP1", 900010)] == "starter"
    assert roles[("RP1", 900010)] == "bullpen", "the bullpen role read fell back to Snowflake"


def test_a_pitcher_in_both_role_tables_resolves_to_starter(upp, eb_duck) -> None:
    """4. Starter precedence survives the repoint (``setdefault``, not overwrite)."""
    roles = upp._load_pitcher_roles(_ExplodingConnection(), date(2026, 4, 3), duck=eb_duck)
    assert roles[("SP2", 900012)] == "starter", (
        "a pitcher present in BOTH EB role tables for one game was classified bullpen — the "
        "starter-wins precedence was lost in the rewrite."
    )


def test_the_role_date_predicate_is_not_silently_empty(upp, eb_duck) -> None:
    """5. E9.52: an un-cast ``=`` across a type boundary matches 0 rows with NO error.

    The failure mode is not an exception — it is a role map that is simply empty, which makes
    every pitcher observation unclassifiable and silently drops them from the chain. Assert a
    known-populated date is non-empty AND that the emitted literal is explicitly cast.
    """
    assert upp._load_pitcher_roles(_ExplodingConnection(), date(2026, 4, 2), duck=eb_duck)
    assert upp._eb_date_literal(date(2026, 4, 2)) == "CAST('2026-04-02' AS DATE)"


# ── 2. the rewrite/registration sets cannot drift apart ────────────────────────────────────

def test_no_snowflake_fqn_survives_the_rewrite(upp) -> None:
    """6. Every ``baseball_data.betting.<eb table>`` is rewritten to the bare view name.

    A surviving FQN does not raise on DuckDB in an obvious way — it resolves as a
    catalog.schema.table lookup that fails late, or worse matches nothing — so pin it directly.
    """
    for sql in (upp._BATTER_PRIOR_SQL, upp._STARTER_PRIOR_SQL, upp._BULLPEN_PRIOR_SQL,
                upp._STARTER_ROLE_SQL, upp._BULLPEN_ROLE_SQL):
        assert "baseball_data.betting." in sql, "the Snowflake query body lost its FQN"
        assert "baseball_data." not in upp._eb_duck_sql(sql), (
            "a Snowflake FQN survived _eb_duck_sql — the rewrite set has drifted from the "
            "queries it is supposed to cover."
        )


def test_every_eb_table_the_queries_read_is_registered(upp) -> None:
    """7. The registration set is EXACTLY the set the query bodies name.

    A table in the SQL but not in ``_EB_S3_TABLES`` is an unregistered view (a late DuckDB
    failure); one registered but unread is dead weight that hides a later removal. Deriving both
    the rewrite and the registration from one list is what makes this checkable.
    """
    named = {t for t in upp._EB_S3_TABLES
             for sql in (upp._BATTER_PRIOR_SQL, upp._STARTER_PRIOR_SQL, upp._BULLPEN_PRIOR_SQL,
                         upp._STARTER_ROLE_SQL, upp._BULLPEN_ROLE_SQL)
             if f"baseball_data.betting.{t}" in sql}
    assert named == set(upp._EB_S3_TABLES), (
        f"registration set {sorted(upp._EB_S3_TABLES)} does not match the tables the EB queries "
        f"actually read ({sorted(named)})."
    )


def test_maybe_duck_registers_the_eb_tables(upp, monkeypatch) -> None:
    """8. ``--s3`` registers the EB views, not just the PA substrate.

    Without this the loaders route to DuckDB and then fail on an unknown view — i.e. the repoint
    would be wired but never invoked, the NF-C0e "wired ≠ invoked" class.
    """
    registered: list[list[str]] = []
    monkeypatch.setattr(upp, "_get_duckdb", lambda: object())
    monkeypatch.setattr(upp, "_register_s3_views", lambda duck: None)
    monkeypatch.setattr(upp, "register_lakehouse_views",
                        lambda duck, tables: registered.append(list(tables)))

    assert upp._maybe_duck(False) is None, "--s3 off must stay Snowflake-only"
    assert registered == [], "the EB views were registered without --s3"

    upp._maybe_duck(True)
    assert registered == [upp._EB_S3_TABLES]


# ── 3. the runner ordering: duck must exist BEFORE the priors load ────────────────────────

@pytest.mark.parametrize("runner", ["run_single_date", "run_backfill", "run_catchup"])
def test_the_duck_connection_is_built_before_the_priors_are_loaded(upp, monkeypatch, runner) -> None:
    """9. All three runners create the DuckDB connection BEFORE ``_load_priors_and_prep``.

    Pre-E11.24 the ``_maybe_duck`` call sat AFTER the prior load — correct then (only the PA
    substrate was on S3), silently wrong now: the priors would load with ``duck=None`` and fall
    straight back to Snowflake. Nothing would raise; the EB dependency would simply still be
    there, and the view flip shipped on top of it would change what a live op reads. This is the
    ordering bug that has no symptom, so it needs a test rather than a comment.
    """
    sentinel = object()
    seen: list[object] = []

    monkeypatch.setattr(upp, "_maybe_duck", lambda use_s3: sentinel if use_s3 else None)
    monkeypatch.setattr(upp, "_load_priors_and_prep",
                        lambda *a, duck=None, **k: (seen.append(duck), {})[1])
    monkeypatch.setattr(upp, "update_for_date", lambda *a, **k: {
        "players_updated": 0, "obs_processed": 0, "skipped": 0, "closed": 0, "inserted": 0})

    if runner == "run_single_date":
        upp.run_single_date(date(2026, 4, 2), 0.385, 400, dry_run=True, use_s3=True)
    elif runner == "run_backfill":
        from betting_ml.scripts.sequential_bayes import catchup as _catchup
        monkeypatch.setattr(upp, "get_snowflake_connection", _ExplodingConnection)
        monkeypatch.setattr(upp, "_load_game_dates_for_season", lambda *a, **k: [date(2026, 4, 2)])
        # the E9.53 backfill guards are unrelated to this ordering clause — stub them so the
        # test can only fail on the thing it names (NF-D17: one clause, one fixture).
        monkeypatch.setattr(_catchup, "require_source_before_reset", lambda *a, **k: None)
        monkeypatch.setattr(_catchup, "guard_or_reset_backfill", lambda **k: None)
        upp.run_backfill(2026, 0.385, 400, dry_run=True, use_s3=True)
    else:
        from betting_ml.scripts.sequential_bayes import catchup as _catchup
        monkeypatch.setattr(_catchup, "run_catchup", lambda **k: None)
        upp.run_catchup(10, 0.385, 400, dry_run=True, use_s3=True)

    assert seen == [sentinel], (
        f"{runner}: _load_priors_and_prep received duck={seen} — it must be called AFTER "
        "_maybe_duck, or the EB priors silently read from Snowflake under --s3."
    )


# ── 4. the view flip ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("model", sorted(EB_MODELS))
def test_the_snowflake_branch_is_a_view(model: str) -> None:
    """10. Both EB models' Snowflake branches are metadata-only views.

    ``create or replace view`` never resumes COMPUTE_WH; the MERGE these replace did, on every
    intraday lineup tick.
    """
    assert "materialized='view'" in _snowflake_branch(model)


@pytest.mark.parametrize("model", sorted(EB_MODELS))
def test_the_snowflake_branch_keeps_no_incremental_machinery(model: str) -> None:
    """11. The retired incremental constructs are GONE from the Snowflake branch.

    A leftover ``is_incremental()`` window on a view is not merely dead — it would filter the
    view's rows to a 7-day slice, silently truncating every reader. Checked over
    comment-stripped source: this model's header names all three constructs while explaining
    why they were removed (INC-38 — prose must not satisfy the guard).
    """
    branch = _snowflake_branch(model)
    for construct in ("materialized='incremental'", "is_incremental", "incremental_strategy"):
        assert construct not in branch, f"{model}: '{construct}' survives in the Snowflake branch"


@pytest.mark.parametrize("model", sorted(EB_MODELS))
def test_the_duckdb_branch_stays_incremental(model: str) -> None:
    """12. The DuckDB branch must NOT inherit the Snowflake-side flip.

    That branch is the real assembly behind the S3 parquet the Snowflake view reads. Flipping it
    too would leave nothing building the parquet — the view would serve a frozen file.
    """
    assert "materialized='incremental'" in _duckdb_branch(model)


@pytest.mark.parametrize("model", sorted(EB_MODELS))
def test_the_snowflake_branch_still_reads_its_own_ext_table(model: str) -> None:
    """13. The view's body is unchanged: a pure copy of the model's own external table.

    This is what makes the flip's row set well-defined — the view returns exactly what the CTAS
    read, so the only difference is the accumulated ghosts the MERGE never deleted.
    """
    assert f"baseball_data.lakehouse_ext.{model}" in _snowflake_branch(model)


def test_the_tick_selectors_still_rebuild_both_models() -> None:
    """14. Both models stay in the intraday + daily dbt selectors.

    They are now free to rebuild (metadata-only DDL), so there is no cost reason to drop them —
    and dropping one silently stops refreshing the Snowflake view. Read as comment-stripped
    source text: importing ``pipeline`` in the fast gate crashes at collection (E11.23), and a
    model named only in a comment must not satisfy the assertion.
    """
    for rel in ("pipeline/ops/sensor_ops.py", "pipeline/ops/daily_ingestion_ops.py"):
        src = "\n".join(line.split("#", 1)[0] for line in (REPO / rel).read_text().splitlines())
        for model in EB_MODELS:
            assert f'"{model}"' in src, f"{rel} no longer selects {model}"
