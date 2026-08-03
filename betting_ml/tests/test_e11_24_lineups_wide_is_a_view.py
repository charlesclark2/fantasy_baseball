"""E11.24 guard — the three intraday-tick staging models must not be TABLEs on Snowflake.

WHY (measured 2026-08-03, `scripts/report_e11_24_wake_census.py`, 10-day window):

    `stg_statsapi_lineups_wide` was `materialized='table'` on the Snowflake target, so every
    rebuild compiled to

        create or replace transient table baseball_data.betting.stg_statsapi_lineups_wide as (...)

    = real warehouse compute. It is re-run on EVERY lineup-monitor tick
    (sensor_ops.lineup_dbt_staging_rebuild) AND every intraday schedule-capture tick
    (intraday_ops.intraday_lineup_rebuild), which made it the single top waiting statement in the
    account: **49 provisioning waits / 10 days**, split across the 14-23 tick band AND the 00-03
    overnight band — waking a ZERO-GAME warehouse all night.

    Its two siblings were already views, and in the same census their CREATE_VIEW statements
    recorded **zero** waits: `create or replace view` is metadata-only and never resumes the
    warehouse. Flipping the wide model to a view removes the waker for every caller at once
    without touching the serving lineup job graph.

WHAT THIS PINS: the Snowflake (`{% else %}`) branch of each model must NOT be a table
materialization. A future edit that flips one back to `table` silently reinstates a ~49-wait /
10-day COMPUTE_WH waker — invisible to CI, invisible to every serving test, and visible only on
the next Snowflake bill. That is exactly the class E11.24 exists to close.

⚠️ Deliberately asserts on the SNOWFLAKE branch only. The duckdb branch carries its own
`materialized='view'` config, so a naive whole-file "is there a table config" check would pass on
a broken file whenever the duckdb branch happened to look right — the file has TWO config blocks
and only one of them is the waker.

SOURCE-INSPECTION, not an import: `pipeline/__init__.py` reads the dbt manifest, absent in the
fast gate, so importing `pipeline` here would crash at COLLECTION rather than skip (E11.23).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGING = REPO_ROOT / "dbt" / "models" / "staging"

# The three models the intraday tick rebuilds (sensor_ops.lineup_dbt_staging_rebuild /
# intraday_ops.intraday_lineup_rebuild). All three must be view-materialized on Snowflake.
TICK_MODELS = [
    "stg_statsapi_lineups",
    "stg_statsapi_lineups_wide",
    "stg_statsapi_probable_pitchers",
]


def _snowflake_branch(model: str) -> str:
    """The `{% else %}` (Snowflake) half of a duckdb/Snowflake dual-branch staging model."""
    src = (STAGING / f"{model}.sql").read_text()
    marker = "{% else %}"
    idx = src.find(marker)
    assert idx != -1, f"{model}.sql has no `{marker}` branch — is it still dual-branch?"
    return src[idx:]


def _strip_jinja_comments(sql: str) -> str:
    """Drop {# ... #} blocks so the fix's own explanatory comment cannot satisfy a guard
    (the INC-38 prose-satisfiable-guard lesson)."""
    return re.sub(r"\{#.*?#\}", "", sql, flags=re.DOTALL)


@pytest.mark.parametrize("model", TICK_MODELS)
def test_snowflake_branch_is_not_a_table(model: str):
    branch = _strip_jinja_comments(_snowflake_branch(model))
    assert not re.search(r"materialized\s*=\s*['\"]table['\"]", branch), (
        f"{model}.sql declares materialized='table' on its Snowflake branch. That compiles to a "
        f"CREATE TABLE AS SELECT which RESUMES COMPUTE_WH on every intraday tick — the E11.24 "
        f"waker (49 provisioning waits / 10 days, incl. the zero-game 00-03 overnight band). "
        f"Use materialized='view': a CREATE OR REPLACE VIEW is metadata-only and measured zero "
        f"waits on the sibling models."
    )


@pytest.mark.parametrize("model", TICK_MODELS)
def test_snowflake_branch_declares_a_view(model: str):
    """Positive half — absence of `table` is not the same as presence of `view`.

    Without this, deleting the config block entirely would pass the negative test above while
    falling back to whatever dbt_project.yml defaults the staging path to (which may be a table).
    """
    branch = _strip_jinja_comments(_snowflake_branch(model))
    assert re.search(r"materialized\s*=\s*['\"]view['\"]", branch), (
        f"{model}.sql does not explicitly declare materialized='view' on its Snowflake branch. "
        f"Relying on the dbt_project.yml default leaves the materialization free to become a "
        f"table again without touching this file."
    )
