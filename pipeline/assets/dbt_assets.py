import json
from pathlib import Path

from dagster import AssetExecutionContext
from dagster_dbt import DbtCliResource, dbt_assets

_DBT_MANIFEST_PATH = Path(__file__).parents[2] / "dbt" / "target" / "manifest.json"


def _manifest_dict() -> dict:
    """Load the dbt manifest and strip operation nodes from all graph sections.

    dbt-fusion (dbtf) adds 'operation.*' nodes to the manifest for on-run-start/
    on-run-end hooks (E11.3). dagster-dbt's @dbt_assets decorator (backed by
    dbt-core's NodeSelector) iterates every graph node and calls
    node.config.enabled — but operation nodes have config=None and crash.
    Strip them from nodes, parent_map, and child_map before passing the manifest
    to the decorator; the on-run-start hook still fires at dbt-fusion run time.
    """
    manifest = json.loads(_DBT_MANIFEST_PATH.read_text())

    def _is_op(key: str) -> bool:
        return key.startswith("operation.")

    manifest["nodes"] = {k: v for k, v in manifest.get("nodes", {}).items() if not _is_op(k)}
    manifest["parent_map"] = {k: v for k, v in manifest.get("parent_map", {}).items() if not _is_op(k)}
    manifest["child_map"] = {k: v for k, v in manifest.get("child_map", {}).items() if not _is_op(k)}
    return manifest


@dbt_assets(manifest=_manifest_dict())
def baseball_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build", "--target", "baseball_betting_and_fantasy"], context=context).stream()
