from pipeline.jobs.snowflake_check import snowflake_check_job
from pipeline.jobs.daily_ingestion_job import daily_ingestion_job

all_jobs = [snowflake_check_job, daily_ingestion_job]
