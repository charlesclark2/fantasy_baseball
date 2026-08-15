"""E11.24 — ``feature_pregame_team_features`` must stay a VIEW on the Snowflake target.

WHAT THIS PROTECTS
------------------
On the Snowflake target this model is nothing but
``select * from baseball_data.lakehouse_ext.feature_pregame_team_features`` — a COPY of an
external table, with the real assembly living in its DuckDB branch. As ``materialized='table'`` it
ran a ``create or replace transient table … as select *`` on every daily build
(``dbt_umpire_feature_rebuild``), and every one of those statements can RESUME ``COMPUTE_WH``.
``create or replace view`` is metadata-only and provably never does — measured across the 9-day
window in ``docs/e11_24_other_attribution.md`` Table 5: 30 distinct view objects, 837 executions,
0 waits, ``metadata_only == execs``. It was the top *unaddressed* rebuild waker on that board
(~2 waits/day).

WHY THIS IS A SEPARATE FILE FROM ``test_e11_24_pregame_features_are_views.py``
-----------------------------------------------------------------------------
That file's ``EXT_COPY_VIEW_MODELS`` registry carries two clauses this model does not satisfy, and
folding it in would have coupled unrelated stories (the E9.60 lesson: adding a new story's
requirement to an older story's clause makes that clause fail for reasons unrelated to what it
defends). Concretely:

* its clause 3 requires the model's **DuckDB branch** to be ``materialized='incremental'``. This
  model's DuckDB branch is a ``view`` (the W8a layer; ``run_w1_lakehouse._build_w8a`` COPYs its
  output to parquet rather than materialising it in DuckDB). Clause 4 below is that clause's
  analogue, rewritten for a view-materialised build branch.
* its clause 5 pins membership of ``sensor_ops.lineup_dbt_feature_rebuild`` (the INTRADAY tick
  selector). This model is **not** in that selector at all — it is rebuilt by the DAILY
  ``daily_ingestion_ops.dbt_umpire_feature_rebuild``. Clause 5 below points at the real owner.

⚠️ WHAT THIS IS *NOT*
---------------------
It is not a credit win and must not be recorded as one. Wake is a QUEUE (#679): flipping one
statement PROMOTES the next warehouse-occupying statement in the same chain into the waker role.
The bill only moves when the warehouse actually SUSPENDS. The remaining flip in this chain is the
``feature_pregame_lineup_state`` SCD-2 port, deliberately NOT bundled here (one-flip-per-soak).

GUARD HYGIENE (the INC-38 / INC-39 / NF-D17 canon)
--------------------------------------------------
* Every branch assertion is made against ONE extracted branch, so a change to the other branch can
  neither satisfy nor break it.
* ``_strip_sql_comments`` drops ``--`` text first, so the (long) prose above the ``config()`` call
  is unmatchable — prose cannot satisfy an assertion (INC-38).
* Clause 2 asserts BOTH directions, so it fails on a REVERT and not merely on a deletion.
* Each test isolates ONE clause, so deleting that clause from the source is what turns it red
  (NF-D17: a fixture that trips several clauses at once proves none of them).
* Fast-gate safe: reads ``pipeline/ops/daily_ingestion_ops.py`` as TEXT and never imports
  ``pipeline``, whose ``__init__`` reads the gitignored dbt manifest (the E11.23 rule).

RED-PROVEN: every assertion below was confirmed to FAIL against deliberately-broken source before
being trusted (see the session record in ``docs/e11_24_team_features_view_flip.md``).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

MODEL = "feature_pregame_team_features"
MODEL_PATH = REPO / "dbt/models/feature/feature_pregame_team_features.sql"
CONSUMER_PATH = REPO / "dbt/models/feature/feature_pregame_game_features_raw.sql"
DAILY_OPS = REPO / "pipeline/ops/daily_ingestion_ops.py"

# Verbs that would make this relation a WRITE target. INC-27's sibling rule: "no reader blocks it"
# is not "no writer does" — a MERGE INTO / INSERT INTO a VIEW fails outright.
#
# Each pattern requires the model name to be the verb's DIRECT target, with nothing between them
# but an identifier path. A looser "verb … within N chars … model name" form false-positives on
# ordinary prose ("update the docs for feature_pregame_team_features") — and prose in a PYTHON
# docstring is not a ``--`` comment, so _strip_sql_comments cannot remove it. An over-eager guard
# that fires on its own documentation gets weakened or deleted, which is how a real writer later
# slips through.
_IDENT = r'[\w."`\[\]]*'
_WRITE_PATTERNS = [
    rf"merge\s+into\s+{_IDENT}{MODEL}\b",
    rf"insert\s+into\s+{_IDENT}{MODEL}\b",
    rf"update\s+{_IDENT}{MODEL}\b",
    rf"delete\s+from\s+{_IDENT}{MODEL}\b",
    rf"create\s+or\s+replace\s+(?:transient\s+)?table\s+{_IDENT}{MODEL}\b",
]


def _strip_sql_comments(sql: str) -> str:
    """Drop ``--`` comment text so prose can never satisfy a source assertion (INC-38)."""
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def _snowflake_branch(path: Path, model: str) -> str:
    """Return ONLY the ``{% else %}`` (Snowflake) branch of a dual-branch model, comments stripped.

    Load-bearing: the DuckDB branch declares its own ``config()``, so an assertion made over the
    whole file would be reading the wrong branch in both directions.
    """
    src = path.read_text()
    assert src.count("{% else %}") == 1, (
        f"{model}: expected exactly one top-level {{% else %}} (the Snowflake branch). Nested "
        "branching means _snowflake_branch is no longer extracting what it claims — fix the "
        "extractor rather than loosening the assertions."
    )
    branch = src.split("{% else %}", 1)[1].rsplit("{% endif %}", 1)[0]
    return _strip_sql_comments(branch)


def _duckdb_branch(path: Path) -> str:
    """Return ONLY the build (pre-``{% else %}``) branch, comments stripped."""
    return _strip_sql_comments(path.read_text().split("{% else %}", 1)[0])


def test_the_model_file_is_where_this_guard_thinks_it_is() -> None:
    """0. ANTI-VACUITY. Every clause below reads one of three files by path. If a file were moved
    or renamed, ``read_text()`` would raise rather than silently pass — but the *extractors* would
    also mis-read a file that had lost its branch structure, so pin the preconditions once, here,
    instead of letting each clause discover them separately.
    """
    for path in (MODEL_PATH, CONSUMER_PATH, DAILY_OPS):
        assert path.exists(), f"{path} is missing — this guard now asserts nothing about it."

    src = MODEL_PATH.read_text()
    assert "{% if target.name == 'duckdb' %}" in src and "{% else %}" in src, (
        f"{MODEL} is no longer a dual-branch model, so the branch extractors below are reading "
        "something other than what they claim. Re-derive the guard rather than loosening it."
    )


def test_snowflake_branch_is_a_view_not_a_table() -> None:
    """1. The Snowflake branch must materialize as a VIEW — asserted BOTH ways.

    As a ``table`` it is a full ``create or replace transient table … as select *`` on every daily
    build, and a write can resume COMPUTE_WH where a view DDL provably cannot. Asserting the
    ABSENCE of the two write materializations as well as the PRESENCE of ``view`` is what makes
    this fail on a revert rather than only on a deletion.
    """
    branch = _snowflake_branch(MODEL_PATH, MODEL)
    assert "materialized='view'" in branch, (
        f"{MODEL}: the Snowflake branch must be materialized='view' (E11.24). As a table it "
        "re-writes the whole relation on every daily build, and that write can resume COMPUTE_WH."
    )
    assert "materialized='table'" not in branch, (
        f"{MODEL}: the Snowflake branch has reverted to materialized='table'. That reinstates the "
        "per-build `create or replace transient table` — ~2 provisioning waits/day, the top "
        "unaddressed rebuild waker on the docs/e11_24_other_attribution.md board."
    )
    assert "materialized='incremental'" not in branch, (
        f"{MODEL}: the Snowflake branch is now materialized='incremental'. This model has never "
        "been an incremental on Snowflake; an incremental would also make it accumulate ghost "
        "rows and re-open the #675 history-spanning-reader gate this flip is safe precisely "
        "because it avoids."
    )


def test_snowflake_branch_is_still_a_pure_ext_table_copy() -> None:
    """2. The safety PRECONDITION: the branch is still nothing but a select off the ext table.

    The flip is safe because it is content-neutral — the table's own source was this same external
    table, so a view returns the same rows (fresher, if anything: a view cannot lag a refresh the
    way a copy taken before one does). If real compute — a join, an aggregate, a window — ever
    lands here, a view stops being free: it re-evaluates that compute on EVERY read, including the
    offline training loaders that scan all history. This test forces that conversation rather than
    letting the materialization be inherited.
    """
    branch = _snowflake_branch(MODEL_PATH, MODEL)
    body = re.sub(r"\{\{.*?\}\}", "", branch, flags=re.DOTALL)  # drop the config() call
    body = " ".join(body.split()).lower()
    expected = f"select * from baseball_data.lakehouse_ext.{MODEL}"
    assert body == expected, (
        f"{MODEL}: the Snowflake branch is no longer a pure external-table copy.\n"
        f"  expected: {expected!r}\n"
        f"  found:    {body!r}\n"
        "A view is only free while this branch does no compute — re-derive the materialization "
        "before changing this body."
    )


def test_the_duckdb_branch_still_does_the_real_build() -> None:
    """3. The DuckDB branch must STAY the real assembly — the flip is Snowflake-side only.

    The S3 parquet this view reads is produced by the DuckDB branch (``run_w1_lakehouse --w8a``).
    This is the analogue of the sibling file's clause 3, rewritten because that clause asserts
    ``materialized='incremental'`` and THIS branch is legitimately a ``view``: what makes it "the
    real build" here is that it assembles from the source marts, not that it materialises.

    Two directions, because either failure is fatal in a different way:
      * it must still reference the source marts (otherwise there is no assembly left), and
      * it must NOT read ``lakehouse_ext`` (the branch that PRODUCES the parquet reading the
        external table over that same parquet would be circular, and would leave the Snowflake
        view pointing at nothing to scan).
    """
    branch = _duckdb_branch(MODEL_PATH)
    for mart in ("mart_game_spine", "mart_team_rolling_offense", "mart_bullpen_effectiveness"):
        assert mart in branch, (
            f"{MODEL}: the DuckDB branch no longer reads {mart}. That branch is the real build "
            "behind the S3 parquet the Snowflake view reads — it must not inherit the "
            "Snowflake-side flip or be reduced to a passthrough."
        )
    assert "lakehouse_ext" not in branch, (
        f"{MODEL}: the DuckDB branch now reads lakehouse_ext. That is circular — this branch "
        "PRODUCES the parquet the external table is defined over."
    )


def test_no_view_on_view_chain_from_the_snowflake_consumer() -> None:
    """4. ⭐ The bound that justified flipping this model rather than deferring it.

    ``docs/e11_24_other_attribution.md`` item 2 named ``feature_pregame_game_features_raw`` as this
    model's Snowflake consumer and warned that chaining a second view compounds read amplification.
    The manifest does not support that premise: that model's two ``ref()`` calls to this one both
    sit in its DuckDB branch, and its SNOWFLAKE branch reads its OWN external table. So no view
    chains onto this view, and the amplification bound holds.

    If someone later repoints that Snowflake branch at ``ref(MODEL)``, the bound silently stops
    holding and BOTH materializations need re-deriving together. This clause is what makes that
    change impossible to take silently.
    """
    consumer_sf = _snowflake_branch(CONSUMER_PATH, "feature_pregame_game_features_raw")
    assert MODEL not in consumer_sf, (
        "feature_pregame_game_features_raw's SNOWFLAKE branch now references "
        f"{MODEL}, creating a view-on-view chain. The read-amplification bound recorded in "
        f"{MODEL}'s header assumed no such chain exists — re-measure both models' read cost "
        "before leaving this in place."
    )


def test_the_daily_rebuild_selector_still_builds_the_model() -> None:
    """5. The model stays in ``dbt_umpire_feature_rebuild``'s dbt selector.

    Post-flip the rebuild is metadata-only, so there is no cost reason to drop it — and dropping it
    stops the Snowflake view being (re)created at all. Pointed at the DAILY op, which is this
    model's real owner; it is deliberately NOT in the intraday tick selector, so asserting against
    ``sensor_ops`` here would pin a membership that has never existed.

    Read as source text with comment lines removed: importing ``pipeline`` in the fast gate crashes
    at collection (E11.23), and a model named only in a comment must not satisfy the assertion —
    which matters here, because that op's body genuinely does name this model in a comment.
    """
    src = DAILY_OPS.read_text()
    start = src.index("def dbt_umpire_feature_rebuild")
    end = src.index("\ndef ", start + 1)
    body = "\n".join(
        line for line in src[start:end].splitlines() if not line.strip().startswith("#")
    )
    assert f'"{MODEL}"' in body, (
        f"dbt_umpire_feature_rebuild no longer selects {MODEL}. Post-flip the rebuild is "
        "metadata-only, so there is no cost reason to drop it — and dropping it stops the "
        "Snowflake view being created on the daily path."
    )


def test_nothing_in_the_repo_writes_to_the_relation() -> None:
    """6. ⭐ INC-27's sibling: a MERGE INTO / INSERT INTO a VIEW fails outright.

    The flip's reader analysis (grep every consumer, not the DAG) is only half the check — the
    other half is that no consumer WRITES. This re-runs that scan mechanically so a future writer
    cannot be added without turning this red, which is strictly better than a one-off grep recorded
    in a PR description.
    """
    offenders: list[str] = []
    for path in sorted(REPO.glob("**/*.py")) + sorted(REPO.glob("**/*.sql")):
        parts = path.parts
        if "node_modules" in parts or "target" in parts or ".git" in parts:
            continue
        if path == MODEL_PATH:
            continue
        try:
            text = _strip_sql_comments(path.read_text(errors="replace"))
        except OSError:
            continue
        if MODEL not in text:
            continue
        for pattern in _WRITE_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                offenders.append(f"{path.relative_to(REPO)}: {match.group(0)[:90]!r}")

    assert not offenders, (
        f"{MODEL} is now a VIEW on Snowflake, but these look like WRITES against it — a MERGE "
        "INTO / INSERT INTO / UPDATE of a view fails outright (the INC-27 sibling rule):\n  "
        + "\n  ".join(offenders)
    )
