"""E11.24 TARGET 6 — the ext-table-COPY models must stay VIEWs on the Snowflake target.

WHAT THIS PROTECTS
------------------
Four models in the intraday tick selector are, on the Snowflake target, nothing but
``select * from baseball_data.lakehouse_ext.<model>`` — a COPY of an external table:

    stg_statsapi_umpire_game_log
    feature_pregame_umpire_features
    feature_pregame_starter_features
    feature_pregame_lineup_features

While they were ``materialized='table'`` every intraday lineup tick re-ran a full CTAS over
each of them (``lineup_dbt_feature_rebuild``, ~9 fires/slate, plus the daily
``dbt_umpire_feature_rebuild``). A CTAS RESUMES ``COMPUTE_WH``; ``create or replace view`` is
metadata-only and never does. The umpire pair alone was 111 of 662 provisioning waits over
8 days — the largest single band in the E11.24 census.

The flip is content-neutral BY CONSTRUCTION: the CTAS's own source was this same external
table, so a view returns byte-identical rows at read time. That property is what makes the
change safe, so it is PINNED here (test 2): if someone later puts real compute in the
Snowflake branch, a view stops being free and this guard must be revisited deliberately.

⛔ It also supersedes and removes the E11.24-6a conditional-skip gate
(``E11_24_UMPIRE_REBUILD_GATE`` + ``betting_ml/monitoring/umpire_rebuild_gate.py``): skipping a
metadata-only DDL saves nothing, and the gate was independently verified INERT on the
2026-08-04 armed slate (0 skips of 3 real opportunities — its S3 marker object had never
existed, so every tick took the fail-OPEN path). Tests 4-6 stop it being reintroduced.

GUARD HYGIENE (the INC-38 / INC-39 / NF-D17 canon)
--------------------------------------------------
* ⭐ THE VACUITY TRAP THIS FILE EXISTS TO DODGE: three of the four models ALREADY declare
  ``materialized='view'`` in their **DuckDB** branch. A naive ``"materialized='view'" in src``
  would therefore pass on completely unchanged, pre-flip source — a guard that cannot fail.
  So every assertion here is made against the ``{% else %}`` (Snowflake) branch ONLY, extracted
  by ``_snowflake_branch``, and test 1 asserts BOTH directions (view present AND table absent).
* Comments cannot satisfy any assertion: ``_strip_sql_comments`` removes ``--`` lines first, so
  the prose above each ``config()`` call is not matchable (INC-38's prose-cannot-satisfy rule).
* Fast-gate safe: this file INSPECTS ``pipeline/ops/sensor_ops.py`` as text and never imports
  ``pipeline`` (whose ``__init__`` reads the gitignored dbt manifest — the E11.23 rule).

RED-PROVEN: each assertion was confirmed to FAIL against deliberately-broken source before
being trusted (see the session record in docs/e11_24_literal_zero_snowflake.md).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# The four ext-table-COPY models, mapped to their model file.
EXT_COPY_VIEW_MODELS = {
    "stg_statsapi_umpire_game_log": "dbt/models/staging/statsapi/stg_statsapi_umpire_game_log.sql",
    "feature_pregame_umpire_features": "dbt/models/feature/feature_pregame_umpire_features.sql",
    "feature_pregame_starter_features": "dbt/models/feature/feature_pregame_starter_features.sql",
    "feature_pregame_lineup_features": "dbt/models/feature/feature_pregame_lineup_features.sql",
}

SENSOR_OPS = REPO / "pipeline/ops/sensor_ops.py"


def _strip_sql_comments(sql: str) -> str:
    """Drop ``--`` comment text so prose can never satisfy a source assertion (INC-38)."""
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def _snowflake_branch(model: str) -> str:
    """Return ONLY the ``{% else %}`` (Snowflake) branch of a dual-branch model, comments stripped.

    Load-bearing: the DuckDB branch of three of these models already says
    ``materialized='view'``, so an assertion made over the WHOLE file would pass on
    unchanged pre-flip source and prove nothing.
    """
    src = (REPO / EXT_COPY_VIEW_MODELS[model]).read_text()
    assert src.count("{% else %}") == 1, (
        f"{model}: expected exactly one top-level {{% else %}} (the Snowflake branch). "
        "Nested branching means _snowflake_branch is no longer extracting what it claims — "
        "fix the extractor rather than loosening the assertions."
    )
    branch = src.split("{% else %}", 1)[1].rsplit("{% endif %}", 1)[0]
    return _strip_sql_comments(branch)


@pytest.mark.parametrize("model", sorted(EXT_COPY_VIEW_MODELS))
def test_snowflake_branch_is_a_view_not_a_table(model: str) -> None:
    """1. The Snowflake branch must materialize as a VIEW — asserted both ways.

    A CTAS here resumes COMPUTE_WH on every intraday tick; ``create or replace view`` does not.
    Asserting the ABSENCE of ``materialized='table'`` as well as the presence of
    ``materialized='view'`` is what makes this fail on a revert, not merely on a deletion.
    """
    branch = _snowflake_branch(model)
    assert "materialized='view'" in branch, (
        f"{model}: the Snowflake branch must be materialized='view' (E11.24 target 6). "
        "As a table it is re-CTAS'd on every intraday lineup tick and each CTAS resumes "
        "COMPUTE_WH."
    )
    assert "materialized='table'" not in branch, (
        f"{model}: the Snowflake branch has reverted to materialized='table'. That reinstates "
        "the per-tick CTAS that was the largest single band in the E11.24 wake census."
    )


@pytest.mark.parametrize("model", sorted(EXT_COPY_VIEW_MODELS))
def test_snowflake_branch_is_still_a_pure_ext_table_copy(model: str) -> None:
    """2. The safety PRECONDITION: the branch is still nothing but a select off the ext table.

    The flip is safe because it is content-neutral by construction — the CTAS read this same
    external table, so a view returns identical rows. If real compute (a join, an aggregate, a
    window) ever lands in this branch, a view stops being free: it would re-evaluate that
    compute on EVERY read. Then the materialization must be reconsidered deliberately, not
    inherited. This test is what forces that conversation.
    """
    branch = _snowflake_branch(model)
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


def test_the_tick_selector_rebuilds_all_four_unconditionally() -> None:
    """3. All four models stay in lineup_dbt_feature_rebuild's dbt selector.

    They are now free to rebuild (metadata-only DDL), and dropping one would silently stop
    refreshing it — the serving-freshness half of the trade. Read as source text: importing
    ``pipeline`` in the fast gate crashes at collection (E11.23).
    """
    src = SENSOR_OPS.read_text()
    start = src.index("def lineup_dbt_feature_rebuild")
    end = src.index("\ndef ", start + 1)
    body = "\n".join(
        line for line in src[start:end].splitlines() if not line.strip().startswith("#")
    )
    for model in EXT_COPY_VIEW_MODELS:
        assert f'"{model}"' in body, (
            f"lineup_dbt_feature_rebuild no longer selects {model}. Post-E11.24-target-6 the "
            "rebuild is metadata-only, so there is no cost reason to drop it — and dropping it "
            "stops the Snowflake view being refreshed on the intraday path."
        )


def test_the_6a_umpire_gate_is_gone_and_not_reintroduced() -> None:
    """4. No conditional gating of the umpire models may come back.

    6a was verified INERT (0 skips of 3 opportunities on the 2026-08-04 armed slate) and is now
    pointless: a conditional skip of a free metadata-only DDL saves nothing while costing a
    flag, an S3 marker, four config owners and a soak.
    """
    assert not (REPO / "betting_ml/monitoring/umpire_rebuild_gate.py").exists(), (
        "betting_ml/monitoring/umpire_rebuild_gate.py is back. The E11.24-6a gate is superseded "
        "by the table→view flip — skipping a metadata-only DDL saves nothing."
    )
    src = SENSOR_OPS.read_text()
    code = "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("#")
    )
    for token in ("umpire_gate_on", "umpire_rebuild_decision", "write_rebuild_marker"):
        assert token not in code, (
            f"pipeline/ops/sensor_ops.py calls {token}() again — the 6a gate has been "
            "reintroduced. See the docstring on lineup_dbt_feature_rebuild."
        )


def test_the_gate_flag_is_deregistered_from_env_required() -> None:
    """5. E11_24_UMPIRE_REBUILD_GATE is no longer a deploy-validated required key.

    ``deploy.sh`` env-parity die()s when a key listed in env.required is missing or empty in the
    box .env, so a flag that no code reads must not stay listed — that is this repo's
    documented-but-never-set class facing the other way. Only NON-comment lines count: the
    removal note in that file mentions the name, and a comment must not satisfy the guard.
    """
    keys = [
        line.strip()
        for line in (REPO / "services/dagster/aws/env.required").read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert "E11_24_UMPIRE_REBUILD_GATE" not in keys, (
        "E11_24_UMPIRE_REBUILD_GATE is still a required env key, but no code reads it — "
        "deploy.sh would die() on a box .env that has correctly dropped it."
    )


def test_no_module_still_imports_the_deleted_gate() -> None:
    """6. Nothing anywhere still imports the deleted module (a stale import is an ImportError
    at op run time, which CI's mocked-IO suite would not necessarily surface)."""
    offenders = []
    for path in REPO.rglob("*.py"):
        if "node_modules" in path.parts or ".git" in path.parts:
            continue
        text = path.read_text(errors="ignore")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "umpire_rebuild_gate" in stripped and (
                stripped.startswith("import ") or stripped.startswith("from ") or "import" in stripped
            ):
                offenders.append(f"{path.relative_to(REPO)}: {stripped}")
    assert not offenders, "stale imports of the deleted 6a gate module:\n" + "\n".join(offenders)
