from dagster import Definitions

from pipeline.resources import snowflake_resource, dbt_resource
from pipeline.assets import all_assets
from pipeline.schedules import all_schedules
from pipeline.sensors import all_sensors
from pipeline.jobs import all_jobs

defs = Definitions(
    assets=all_assets,
    resources={
        "snowflake": snowflake_resource,
        "dbt": dbt_resource,
    },
    schedules=all_schedules,
    sensors=all_sensors,
    jobs=all_jobs,
)
