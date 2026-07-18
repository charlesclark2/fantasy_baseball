from pipeline.jobs.snowflake_check import snowflake_check_job
from pipeline.jobs.daily_ingestion_job import daily_ingestion_job
from pipeline.jobs.intraday_jobs import (
    intraday_public_betting_job,
    intraday_schedule_job,
    intraday_weather_job,
    odds_clv_rebuild_job,
    odds_current_rebuild_job,
)
from pipeline.jobs.sensor_jobs import lineup_monitor_job, statcast_catchup_job
from pipeline.jobs.weekly_player_profiles_job import weekly_player_profiles_job
# E11.1-W11-E: historical_matches_catchup_job DECOMMISSIONED (Parlay platform retired) — job removed.
from pipeline.jobs.clv_monitoring_job import clv_monitoring_job
from pipeline.jobs.weekly_ml_job import weekly_meta_model_job, weekly_ml_job
from pipeline.jobs.magnitude_monitor_job import magnitude_monitor_job
from pipeline.jobs.w1_parity_job import w1_parity_job
from pipeline.jobs.sports_dbt_job import sports_nfl_dbt_build_job

all_jobs = [
    snowflake_check_job,
    daily_ingestion_job,
    odds_current_rebuild_job,
    odds_clv_rebuild_job,
    intraday_weather_job,
    intraday_schedule_job,
    intraday_public_betting_job,
    lineup_monitor_job,
    statcast_catchup_job,
    weekly_player_profiles_job,
    clv_monitoring_job,
    weekly_ml_job,
    weekly_meta_model_job,
    magnitude_monitor_job,
    w1_parity_job,
    sports_nfl_dbt_build_job,
]
