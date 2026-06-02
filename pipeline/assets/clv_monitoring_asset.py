import sys
from pathlib import Path

from dagster import AssetExecutionContext, MetadataValue, Output, asset

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


@asset(
    compute_kind="python",
    group_name="clv_monitoring",
    description=(
        "Weekly CLV descriptive monitoring. Queries feature_pregame_meta_model_features, "
        "appends a dated analysis section to clv_monitoring_log.md, and logs summary "
        "metrics to MLflow under experiment 'clv_monitoring'."
    ),
)
def clv_monitoring(context: AssetExecutionContext) -> Output[dict]:
    from betting_ml.scripts.compute_clv_monitoring import run

    context.log.info("Starting CLV monitoring run")
    metrics = run()

    if not metrics:
        context.log.warning("No data returned — feature mart may be empty.")
        return Output(value={}, metadata={"status": MetadataValue.text("no_data")})

    context.log.info("CLV monitoring complete — %d metrics logged", len(metrics))
    return Output(
        value=metrics,
        metadata={k: MetadataValue.float(float(v))
                  for k, v in metrics.items()
                  if isinstance(v, (int, float))},
    )
