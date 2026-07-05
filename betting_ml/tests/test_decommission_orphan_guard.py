"""
test_decommission_orphan_guard.py  (INC-27 — un-orphan a dropped table; fast gate)
==================================================================================
W11-E DROPPED baseball_data.betting.stg_batter_pitches on a dbt-DAG conclusion ("only consumer =
mart_pa_outcome_substrate, duckdb-only") — but ~6 hybrid Python scripts embed the table as a RAW
SQL STRING the DAG could not see (write_serving_store's intraday path + the team/bullpen posterior
state-writers, which read stg_batter_pitches AND write their posteriors back to Snowflake). They
HALTed / degraded at runtime (`002003 (42S02): STG_BATTER_PITCHES does not exist`). CI never caught
it — CI mocks all IO, and the dbt DAG can't see a raw SQL string in a .py state-writer.

The durable fix (operator choice) recreates the table as lakehouse_ext.stg_batter_pitches (external
table over the S3 parquet the daily ingest already writes) + a betting.stg_batter_pitches view over
it — the same pattern as every other decommissioned lakehouse table — with the ext table's daily
REFRESH wired into refresh_w1_external_tables.py's REQUIRED set so the view never serves stale data.

This guard MECHANIZES the prevention landmine (CLAUDE.md "DROPPING A TABLE IN A DECOMMISSION — the
dbt DAG is NOT the full consumer list"): a registry of decommissioned lakehouse tables that still
have raw-SQL (non-DAG-visible) consumers, EACH of which MUST have its lakehouse_ext view refreshed
DAILY. If a future decommission drops such a table and forgets the view backstop, add it to the
registry — this test stays RED until the daily refresh is wired, so the orphaned-consumer class
cannot silently ship. Pure source-scan (no pipeline/snowflake import), so it runs in the fast gate.
"""
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

# ── Registry ──────────────────────────────────────────────────────────────────────────────────
# SF tables DROPPED in a decommission that STILL have raw-SQL (non-DAG-visible) consumers, served
# durably via a lakehouse_ext external-table view. Map bare table name -> its Snowflake schema.
# ➕ WHEN YOU DECOMMISSION A TABLE WITH RAW-SQL CONSUMERS, ADD IT HERE — but FIRST run
#    `grep -rIn "<schema>\.<table>"` over the WHOLE repo (.py/.sql string literals), not just
#    `dbt ls`/the manifest, to find every consumer the DAG can't see (INC-27).
DECOMMISSIONED_WITH_RAW_CONSUMERS = {
    "stg_batter_pitches": "betting",
}

REFRESH_SCRIPT = REPO / "scripts" / "refresh_w1_external_tables.py"
GEN_SCRIPT = REPO / "scripts" / "ddl" / "generate_stg_batter_pitches_external_table.py"

# Serving/pipeline surface where a raw-SQL consumer of a dropped table would silently HALT/500.
_SCAN_ROOTS = ["scripts", "pipeline", "app/backend", "betting_ml/scripts", "betting_ml/utils"]


@pytest.mark.parametrize("table,schema", sorted(DECOMMISSIONED_WITH_RAW_CONSUMERS.items()))
def test_decommissioned_table_has_daily_refresh_backstop(table, schema):
    """A dropped table with raw-SQL consumers MUST have its lakehouse_ext view refreshed daily,
    else those consumers read a stale/absent table (the INC-27 outage class)."""
    src = REFRESH_SCRIPT.read_text()
    assert table in src, (
        f"{schema}.{table} was decommissioned (registered in this guard) but is NOT refreshed by "
        f"refresh_w1_external_tables.py — its {schema}.{table} view will go stale/absent and orphan "
        f"its raw-SQL consumers. Wire the lakehouse_ext.{table} refresh into the DAILY required set."
    )


def test_stg_batter_pitches_refresh_is_required_tier():
    """stg_batter_pitches backs the intraday box score + the posterior writers (serving-critical),
    so its refresh must be REQUIRED (HALT) tier, not best-effort."""
    src = REFRESH_SCRIPT.read_text()
    assert 'STG_BATTER_PITCHES_TABLE = ["stg_batter_pitches"]' in src, (
        "STG_BATTER_PITCHES_TABLE constant missing/renamed in refresh_w1_external_tables.py."
    )
    assert "set(STG_BATTER_PITCHES_TABLE)" in src, (
        "stg_batter_pitches must be in the REQUIRED daily-refresh set (serving-critical), not "
        "best-effort — a missing/failed refresh should HALT, not silently serve a stale view."
    )
    assert "STG_BATTER_PITCHES_TABLE +" in src, (
        "stg_batter_pitches must be included in the tables passed to the daily _refresh() call."
    )


def test_generator_script_present():
    """The external-table generator must survive so the operator can rebuild the view after any
    lakehouse_ext stage/schema rebuild (INC-16-class re-host)."""
    assert GEN_SCRIPT.exists(), (
        f"{GEN_SCRIPT.relative_to(REPO)} is missing — without it the betting.stg_batter_pitches "
        f"view cannot be regenerated after a stage rebuild."
    )


def test_registered_tables_are_actually_referenced_somewhere():
    """Sanity: a table in the registry should actually be referenced as raw SQL somewhere in the
    serving/pipeline surface (otherwise the registry entry is stale and should be removed)."""
    for table, schema in DECOMMISSIONED_WITH_RAW_CONSUMERS.items():
        fqn = f"{schema}.{table}"
        hits = []
        for root in _SCAN_ROOTS:
            base = REPO / root
            if not base.exists():
                continue
            for path in list(base.rglob("*.py")) + list(base.rglob("*.sql")):
                try:
                    if fqn in path.read_text(errors="ignore"):
                        hits.append(path)
                        break
                except OSError:
                    continue
            if hits:
                break
        assert hits, (
            f"Registry lists {fqn} as having raw-SQL consumers, but no reference was found in "
            f"{_SCAN_ROOTS}. If the consumers were migrated to DuckDB, remove the stale registry "
            f"entry; the view backstop is no longer needed."
        )
