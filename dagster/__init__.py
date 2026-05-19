from dagster import Definitions

from dagster.resources import snowflake_resource, dbt_resource
from dagster.assets import all_assets
from dagster.schedules import all_schedules
from dagster.sensors import all_sensors
from dagster.jobs import all_jobs

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
