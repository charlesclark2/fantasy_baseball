"""E11.24 target 6 — a pure ext-table passthrough on the Snowflake branch must be a VIEW.

WHY THIS GUARD EXISTS
---------------------
Several dbt models are dual-branch: a real DuckDB compute that writes the S3 parquet, and a
Snowflake branch whose ENTIRE body is ``select * from baseball_data.lakehouse_ext.<model>`` —
i.e. a pure copy of an external table over that same parquet.

Materialized as a ``table`` that copy is a **CTAS**, which requires a running warehouse. The
intraday lineup-monitor tick re-ran it every ~10 minutes through the slate, re-copying
byte-identical rows. Measured over 8 days (``queued_provisioning_time > 0`` on COMPUTE_WH):

    feature_pregame_lineup_features + feature_pregame_starter_features   66 waits
    stg_statsapi_umpire_game_log + feature_pregame_umpire_features      111 waits

Materialized as a ``view`` the same statement is ``create or replace view`` — metadata-only,
executed on Snowflake's cloud-services layer, and it never resumes the warehouse.

WHY THE SWAP IS SAFE FOR THIS SHAPE SPECIFICALLY (and NOT for the siblings)
--------------------------------------------------------------------------
``create or replace table AS select *`` already REPLACES the whole table on every run, so the
table's row population is already exactly "whatever the external table holds right now" — which
is precisely what a view returns. Equivalence is structural, not empirical.

That argument does **not** extend to ``feature_pregame_game_features_raw`` /
``feature_pregame_game_features``, which are ``incremental`` + ``delete+insert`` over a lookback
window: they ACCUMULATE history, so a view could silently change the row population if the S3
parquet is not full-history. Those need a measured row-population parity check before flipping
and are deliberately excluded here. This test therefore only ever asserts on models whose
Snowflake branch is a *pure* passthrough (no ``is_incremental()``, no WHERE clause).

WHAT IS PINNED
--------------
The model list is COMPUTED from the intraday selector in ``pipeline/ops/sensor_ops.py`` (plus
``UMPIRE_MODELS``) rather than hand-listed, so a model added to the tick is covered
automatically — the INC-38 lesson that a per-item fix fails exactly where its registry is
incomplete. A hand-written registry would need editing to stay correct; this one cannot rot.

⚠️ Comment-stripping is load-bearing. The flipped models carry explanatory comments containing
the literal string ``materialized='table'``; a naive regex over raw source would match that prose
and mis-read a correct file. Every check below runs over comment-stripped SQL (the INC-38
"a source-inspection guard is vacuous if prose can satisfy it" rule, facing the other way).

Fast-gate safe: pure source inspection, no ``pipeline`` import (the E11.23 rule), no IO.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DBT_MODELS = REPO / "dbt" / "models"
SENSOR_OPS = REPO / "pipeline" / "ops" / "sensor_ops.py"
UMPIRE_GATE = REPO / "betting_ml" / "monitoring" / "umpire_rebuild_gate.py"


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------

def strip_sql_comments(sql: str) -> str:
    """Drop ``--`` line comments. Without this, prose mentioning ``materialized='table'``
    satisfies (or falsely trips) every check below — the INC-38 vacuous-guard class."""
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def snowflake_branch(sql: str) -> str | None:
    """The Snowflake-executable branch: everything after the LAST ``{% else %}``.

    Returns None for a single-branch model (no dual-branch structure)."""
    if "{% if target.name == 'duckdb' %}" not in sql:
        return None
    marker = "{% else %}"
    if marker not in sql:
        return None
    return sql[sql.rindex(marker) + len(marker):]


PASSTHROUGH_RE = re.compile(
    r"^\s*select\s+\*\s+from\s+baseball_data\.lakehouse_ext\.(\w+)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def is_pure_passthrough(branch: str) -> bool:
    """True when the branch body is *only* ``select * from baseball_data.lakehouse_ext.<x>``.

    A branch carrying ``is_incremental()`` or a WHERE clause is NOT pure — it accumulates or
    filters, so the table→view equivalence argument does not hold and the model is out of scope.
    """
    body = strip_sql_comments(branch)
    # remove the config block and the closing endif so only the SQL body remains
    body = re.sub(r"\{\{\s*config\(.*?\)\s*\}\}", "", body, flags=re.DOTALL)
    body = body.replace("{% endif %}", "")
    if "is_incremental" in body or re.search(r"\bwhere\b", body, re.IGNORECASE):
        return False
    return bool(PASSTHROUGH_RE.fullmatch(body.strip()))


def declared_materialization(branch: str) -> str | None:
    body = strip_sql_comments(branch)
    m = re.search(r"materialized\s*=\s*'(\w+)'", body)
    return m.group(1) if m else None


def find_model(name: str) -> Path | None:
    hits = list(DBT_MODELS.rglob(f"{name}.sql"))
    return hits[0] if len(hits) == 1 else (hits[0] if hits else None)


def intraday_selector_models() -> list[str]:
    """The models ``lineup_dbt_feature_rebuild`` passes to ``dbt run --select``.

    Computed from source so a model added to the intraday tick is covered without editing
    this test."""
    src = SENSOR_OPS.read_text()
    start = src.index("def lineup_dbt_feature_rebuild")
    body = src[start:]
    # the _run_dbt(...) call: from '"run",' up to the closing '--target'
    run_start = body.index('"run",')
    run_end = body.index('"--target"', run_start)
    block = strip_sql_comments(body[run_start:run_end])
    # python comments too
    block = "\n".join(re.sub(r"#.*$", "", line) for line in block.splitlines())
    names = re.findall(r'"([a-z0-9_]+)"', block)
    models = [n for n in names if n not in {"run", "--select"}]

    ump = re.search(r"UMPIRE_MODELS\s*=\s*\(([^)]*)\)", UMPIRE_GATE.read_text())
    assert ump, "UMPIRE_MODELS constant not found — the selector derivation is broken"
    models += re.findall(r'"([a-z0-9_]+)"', ump.group(1))
    return sorted(set(models))


# --------------------------------------------------------------------------------------
# the derivation itself must not silently return nothing (NF1.7 (a): a check that did not
# run is not a pass)
# --------------------------------------------------------------------------------------

def test_the_selector_derivation_is_not_vacuous():
    models = intraday_selector_models()
    assert len(models) >= 6, f"selector derivation returned only {models} — parsing has rotted"
    # the four known passthroughs and the two known incrementals must all be present
    for expected in (
        "feature_pregame_lineup_features",
        "feature_pregame_starter_features",
        "feature_pregame_umpire_features",
        "stg_statsapi_umpire_game_log",
        "feature_pregame_game_features_raw",
        "feature_pregame_game_features",
    ):
        assert expected in models, f"{expected} missing from the derived intraday selector"


def test_at_least_four_intraday_models_are_pure_passthroughs():
    """If this drops to zero the classifier has rotted and every assertion below goes vacuous."""
    pure = [
        m for m in intraday_selector_models()
        if (p := find_model(m)) and (b := snowflake_branch(p.read_text())) and is_pure_passthrough(b)
    ]
    assert len(pure) >= 4, f"expected >=4 pure passthroughs in the intraday selector, got {pure}"


# --------------------------------------------------------------------------------------
# the actual invariant
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("model", intraday_selector_models())
def test_pure_passthrough_in_the_intraday_tick_is_a_view_not_a_table(model):
    """A CTAS of an external table resumes COMPUTE_WH on every ~10-min tick; a view does not.

    Only *pure* passthroughs are asserted — an incremental/filtered branch is skipped because
    the table→view equivalence argument does not hold for it (it accumulates)."""
    path = find_model(model)
    if path is None:
        pytest.skip(f"{model} is not a dbt model file")
    branch = snowflake_branch(path.read_text())
    if branch is None or not is_pure_passthrough(branch):
        pytest.skip(f"{model} is not a pure lakehouse_ext passthrough on the Snowflake branch")

    mat = declared_materialization(branch)
    assert mat == "view", (
        f"{model}'s Snowflake branch is a pure `select * from lakehouse_ext.*` but is "
        f"materialized='{mat}'. A table makes it a CTAS, which resumes COMPUTE_WH on every "
        f"intraday lineup-monitor tick (E11.24 target 6: this class was ~177 provisioning "
        f"waits / 8 days). Use materialized='view' — metadata-only, and provably equivalent "
        f"because a CTAS already replaces the whole table each run."
    )


def test_the_accumulating_incrementals_are_deliberately_out_of_scope():
    """Pins the scope boundary so a later session does not flip them by pattern-matching.

    ``feature_pregame_game_features_raw`` / ``_game_features`` accumulate via delete+insert over
    a lookback window, so a view is NOT provably equivalent — it would silently change the row
    population if the S3 parquet is not full-history. They need a measured parity check first."""
    for model in ("feature_pregame_game_features_raw", "feature_pregame_game_features"):
        path = find_model(model)
        assert path is not None, f"{model} not found"
        branch = snowflake_branch(path.read_text())
        assert branch is not None, f"{model} lost its dual-branch structure"
        assert not is_pure_passthrough(branch), (
            f"{model} now classifies as a PURE passthrough — it previously carried an "
            f"is_incremental() window. If the incremental window was genuinely removed, flip it "
            f"to a view deliberately (with a row-population parity check) rather than letting "
            f"the classifier change meaning underneath this guard."
        )


# --------------------------------------------------------------------------------------
# two-sided controls: the classifier must accept the real shape and REJECT the near-misses.
# Without these, `is_pure_passthrough` returning False for everything would make the
# invariant above pass on nothing.
# --------------------------------------------------------------------------------------

_REAL = """
{{ config(materialized='view') }}

select * from baseball_data.lakehouse_ext.feature_pregame_lineup_features

{% endif %}
"""

_TABLE_FORM = _REAL.replace("'view'", "'table'")

_INCREMENTAL = """
{{ config(materialized='incremental', unique_key='game_pk') }}

select * from baseball_data.lakehouse_ext.feature_pregame_game_features_raw
{% if is_incremental() %}
where game_date::date >= dateadd('day', -7, current_date)
{% endif %}

{% endif %}
"""

_PROSE_ONLY = """
-- materialized='table' → 'view': this comment must not satisfy or trip the classifier.
{{ config(materialized='view') }}

select * from baseball_data.lakehouse_ext.feature_pregame_umpire_features

{% endif %}
"""

_REAL_COMPUTE = """
{{ config(materialized='table') }}

select a.*, b.x from baseball_data.betting.some_mart a join other b on a.k = b.k

{% endif %}
"""


def test_classifier_accepts_a_pure_passthrough():
    assert is_pure_passthrough(_REAL)
    assert declared_materialization(_REAL) == "view"


def test_classifier_flags_the_table_form():
    assert is_pure_passthrough(_TABLE_FORM)
    assert declared_materialization(_TABLE_FORM) == "table"


def test_classifier_rejects_an_accumulating_incremental():
    assert not is_pure_passthrough(_INCREMENTAL)


def test_classifier_rejects_real_compute():
    assert not is_pure_passthrough(_REAL_COMPUTE)


def test_prose_containing_the_word_table_does_not_defeat_the_classifier():
    """The flipped models really do carry `materialized='table'` inside a comment."""
    assert is_pure_passthrough(_PROSE_ONLY)
    assert declared_materialization(_PROSE_ONLY) == "view"
