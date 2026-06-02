from dagster import define_asset_job

clv_monitoring_job = define_asset_job(
    name="clv_monitoring_job",
    selection=["clv_monitoring"],
    description="Weekly CLV descriptive monitoring — queries feature mart, appends to log, logs to MLflow.",
)
