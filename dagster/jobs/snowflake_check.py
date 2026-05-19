from dagster import op, job
from dagster_snowflake import SnowflakeResource


@op
def snowflake_connectivity_check(context, snowflake: SnowflakeResource):
    with snowflake.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE()"
        )
        row = cursor.fetchone()
    context.log.info(
        f"Snowflake OK — user={row[0]}, role={row[1]}, "
        f"warehouse={row[2]}, database={row[3]}"
    )


@job
def snowflake_check_job():
    snowflake_connectivity_check()
