"""E11.24 target-6 SUCCESSOR — the pregame-feature ext-table COPIES must stay VIEWs on Snowflake.

WHAT THIS PROTECTS
------------------
On the Snowflake target these two models are nothing but
``select * from baseball_data.lakehouse_ext.<model>`` — a COPY of an external table, with all of
the real assembly living in their DuckDB branch:

    feature_pregame_game_features_raw
    feature_pregame_game_features

While they were ``materialized='incremental'`` (``delete+insert``) each intraday lineup tick ran a
temp CTAS + DELETE + INSERT over each of them, and every one of those statements can RESUME
``COMPUTE_WH``; ``create or replace view`` is metadata-only and never does. They are the tail of
the same tick selector target 6 flipped (``lineup_dbt_feature_rebuild``), so this is that flip's
established shape one materialization over.

The flip is content-neutral, and that was MEASURED rather than argued (2026-08-08, MONITOR_WH):
26,969 = 26,969 rows with zero game_dates differing in count, 756/756 and 790/790 columns with
zero ``data_type`` mismatches, and value agreement on every game inside the 7-day incremental
window. Test 2 pins the PRECONDITION that makes it so — if real compute ever lands in the
Snowflake branch, a view stops being free and the materialization must be re-derived deliberately.

⚠️ WHAT THIS IS *NOT*
---------------------
It is not a wake reduction, and it must not be recorded as one. On 2026-08-07 — the one clean
fully-post-target-6 day — these two models took **zero** provisioning waits in the 14-23 UTC tick
band. All of that band's tick wake sat on three writers this change deliberately does NOT touch:

    merge into ...eb_starter_posteriors        3 waits
    merge into ...eb_batter_posteriors_raw     3 waits
    UPDATE ...feature_pregame_lineup_state     3 waits

⚠️ **SCOPE UPDATE (2026-08-09, #675 landed in the same window).** When this file shipped, none of
the three was flippable and a fourth test (``NOT_FLIPPABLE`` + its ``@parametrize`` consumer) held
that line by failing if the EB pair was swept in. **That test has been DELETED, on purpose** — it
existed to force the EB pair through its own analysis, and #675 is that analysis: it repoints
``update_player_posteriors``'s history-spanning read to S3 and then flips both EB models to views.
Keeping the clause would assert the exact opposite of what now ships, and *emptying* the dict
would be worse — ``@parametrize`` over an empty mapping collects ZERO cases and passes on nothing
(the NF1.7 (a) vacuous-guard class). ``test_e11_24_eb_reader_repoint.py`` (20 assertions) is its
successor and covers strictly more.

``feature_pregame_lineup_state`` remains NOT flippable, and for a different reason than the EB
pair: it is not a lakehouse passthrough at all — Snowflake is the MASTER (written by
``scripts/backfill_lineup_state_scd2.py``'s SCD-2 UPDATE) and S3 is the downstream mirror, so
there is no table→view flip available to it. It has no guard here because it has no dual-branch
dbt model to assert against; porting that write off Snowflake is the next target.

GUARD HYGIENE (the INC-38 / INC-39 / NF-D17 canon)
--------------------------------------------------
* Every assertion is made against the ``{% else %}`` (Snowflake) branch only, extracted by
  ``_snowflake_branch``. Asserting over the whole file would let a change to the DuckDB branch —
  which must stay ``incremental``, because that is where the real build happens — satisfy or
  break a guard about Snowflake.
* Comments cannot satisfy any assertion: ``_strip_sql_comments`` drops ``--`` text first, so the
  prose above each ``config()`` call is unmatchable (INC-38's prose-cannot-satisfy rule).
* Test 1 asserts BOTH directions (view present AND incremental absent) so it fails on a revert,
  not merely on a deletion.
* Each test isolates ONE clause, so disabling that clause in the source is what makes it go red
  (NF-D17: a fixture that trips several clauses at once proves none of them).
* Fast-gate safe: this file INSPECTS ``pipeline/ops/sensor_ops.py`` as text and never imports
  ``pipeline`` (whose ``__init__`` reads the gitignored dbt manifest — the E11.23 rule).

RED-PROVEN: every assertion was confirmed to FAIL against deliberately-broken source before being
trusted (see the session record in docs/e11_24_literal_zero_snowflake.md).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# The ext-table-COPY models this story flips, mapped to their model file.
EXT_COPY_VIEW_MODELS = {
    "feature_pregame_game_features_raw":
        "dbt/models/feature/feature_pregame_game_features_raw.sql",
    "feature_pregame_game_features":
        "dbt/models/feature/feature_pregame_game_features.sql",
}

SENSOR_OPS = REPO / "pipeline/ops/sensor_ops.py"


def test_the_model_registry_is_not_empty() -> None:
    """0. ANTI-VACUITY. Three ``@parametrize`` tests and one loop below iterate
    ``EXT_COPY_VIEW_MODELS``; emptying it collects ZERO cases and every one of them passes on
    nothing (NF1.7 (a) / the #690 "a guard that iterates matches must assert non-vacuity" rule).

    This clause is here because the failure mode is not hypothetical: #675 removed a sibling
    ``@parametrize`` whose source dict it had made obsolete, and the *tempting* edit — emptying the
    dict rather than deleting the dict AND its consumer — would have left a green suite guarding
    nothing. Deleting the consumer is the correct move; this assertion is what makes the *other*
    move impossible to take silently.
    """
    assert EXT_COPY_VIEW_MODELS, (
        "EXT_COPY_VIEW_MODELS is empty, so every parametrized guard in this file now collects zero "
        "cases and asserts nothing. If a model genuinely left this story's scope, DELETE its tests "
        "with it rather than emptying the registry they iterate."
    )


def _strip_sql_comments(sql: str) -> str:
    """Drop ``--`` comment text so prose can never satisfy a source assertion (INC-38)."""
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def _snowflake_branch(path: str, model: str) -> str:
    """Return ONLY the ``{% else %}`` (Snowflake) branch of a dual-branch model, comments stripped.

    Load-bearing: the DuckDB branch of these models declares its own ``config()`` and must STAY
    ``incremental`` (it is where the real assembly runs), so an assertion made over the whole file
    would be reading the wrong branch in both directions.
    """
    src = (REPO / path).read_text()
    assert src.count("{% else %}") == 1, (
        f"{model}: expected exactly one top-level {{% else %}} (the Snowflake branch). Nested "
        "branching means _snowflake_branch is no longer extracting what it claims — fix the "
        "extractor rather than loosening the assertions."
    )
    branch = src.split("{% else %}", 1)[1].rsplit("{% endif %}", 1)[0]
    return _strip_sql_comments(branch)


@pytest.mark.parametrize("model", sorted(EXT_COPY_VIEW_MODELS))
def test_snowflake_branch_is_a_view_not_an_incremental(model: str) -> None:
    """1. The Snowflake branch must materialize as a VIEW — asserted both ways.

    As an incremental it is a temp CTAS + DELETE + INSERT on every intraday lineup tick, each of
    which can resume COMPUTE_WH. Asserting the ABSENCE of ``materialized='incremental'`` as well
    as the presence of ``materialized='view'`` is what makes this fail on a revert rather than
    only on a deletion.
    """
    branch = _snowflake_branch(EXT_COPY_VIEW_MODELS[model], model)
    assert "materialized='view'" in branch, (
        f"{model}: the Snowflake branch must be materialized='view' (E11.24 target-6 successor). "
        "As an incremental it re-writes rows on every intraday lineup tick, and a write can "
        "resume COMPUTE_WH where a view DDL cannot."
    )
    assert "materialized='incremental'" not in branch, (
        f"{model}: the Snowflake branch has reverted to materialized='incremental'. That "
        "reinstates the per-tick temp CTAS + DELETE + INSERT, and it re-opens the history drift "
        "the view flip closed (77 of 26,969 game_pks differed from the parquet on 2026-08-08)."
    )


@pytest.mark.parametrize("model", sorted(EXT_COPY_VIEW_MODELS))
def test_snowflake_branch_is_still_a_pure_ext_table_copy(model: str) -> None:
    """2. The safety PRECONDITION: the branch is still nothing but a select off the ext table.

    The flip is safe because it is content-neutral — the incremental's own source was this same
    external table, so a view returns the same rows (fresher, if anything: it cannot lag a
    refresh the way a copy taken before one does). If real compute — a join, an aggregate, a
    window — ever lands here, a view stops being free: it re-evaluates that compute on EVERY
    read, including the offline training loaders that scan all history. This test is what forces
    that conversation instead of letting the materialization be inherited.

    It also pins the removal of the ``is_incremental()`` window: a view makes that filter inert,
    and leaving dead Jinja in the branch is how a future reader concludes the model still has an
    incremental scope it no longer has.
    """
    branch = _snowflake_branch(EXT_COPY_VIEW_MODELS[model], model)
    body = re.sub(r"\{\{.*?\}\}", "", branch, flags=re.DOTALL)  # drop the config() call
    body = " ".join(body.split()).lower()
    expected = f"select * from baseball_data.lakehouse_ext.{model}"
    assert body == expected, (
        f"{model}: the Snowflake branch is no longer a pure external-table copy.\n"
        f"  expected: {expected!r}\n"
        f"  found:    {body!r}\n"
        "A view is only free while this branch does no compute — re-derive the materialization "
        "before changing this body."
    )


@pytest.mark.parametrize("model", sorted(EXT_COPY_VIEW_MODELS))
def test_the_duckdb_branch_still_does_the_real_build(model: str) -> None:
    """3. The DuckDB branch must STAY incremental — the flip is Snowflake-side only.

    The S3 parquet these views read is produced by the DuckDB branch (run_w1_lakehouse --w8b).
    Flipping THAT to a view would leave the external table pointing at nothing to scan and take
    the served feature store down, so the two branches must not be changed together by reflex.
    """
    src = (REPO / EXT_COPY_VIEW_MODELS[model]).read_text()
    duckdb_branch = _strip_sql_comments(src.split("{% else %}", 1)[0])
    assert "materialized='incremental'" in duckdb_branch, (
        f"{model}: the DuckDB branch is no longer materialized='incremental'. That branch is the "
        "real build behind the S3 parquet the Snowflake view reads — it must not inherit the "
        "Snowflake-side flip."
    )


def test_the_tick_selector_still_rebuilds_both_models() -> None:
    """5. Both models stay in lineup_dbt_feature_rebuild's dbt selector.

    They are now free to rebuild (metadata-only DDL), so there is no cost reason to drop them —
    and dropping one silently stops refreshing the Snowflake view on the intraday path. Read as
    source text, and with comment lines removed: importing ``pipeline`` in the fast gate crashes
    at collection (E11.23), and a model named only in a comment must not satisfy the assertion.
    """
    src = SENSOR_OPS.read_text()
    start = src.index("def lineup_dbt_feature_rebuild")
    end = src.index("\ndef ", start + 1)
    body = "\n".join(
        line for line in src[start:end].splitlines() if not line.strip().startswith("#")
    )
    for model in EXT_COPY_VIEW_MODELS:
        assert f'"{model}"' in body, (
            f"lineup_dbt_feature_rebuild no longer selects {model}. Post-flip the rebuild is "
            "metadata-only, so there is no cost reason to drop it — and dropping it stops the "
            "Snowflake view being refreshed on the intraday path."
        )
