from pathlib import Path

from dagster import AssetExecutionContext
from dagster_dbt import DbtCliResource, dbt_assets

DBT_MANIFEST_PATH = Path(__file__).parents[2] / "dbt" / "target" / "manifest.json"


@dbt_assets(manifest=DBT_MANIFEST_PATH)
def baseball_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build", "--target", "baseball_betting_and_fantasy"], context=context).stream()
