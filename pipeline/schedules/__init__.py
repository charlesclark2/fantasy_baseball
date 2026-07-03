from pipeline.schedules.daily_ingestion_schedule import daily_ingestion_schedule
from pipeline.schedules.intraday_schedules import all_intraday_schedules
# E11.1-W11-E: parlay_api DECOMMISSIONED (Parlay platform retired). historical_matches_weekly_schedule
# — the last live parlay ingestion — is removed with its asset/schedule/job files.
from pipeline.schedules.weekly_player_profiles_schedule import weekly_player_profiles_schedule
from pipeline.schedules.weekly_clv_monitoring_schedule import weekly_clv_monitoring_schedule
from pipeline.schedules.weekly_ml_schedules import weekly_meta_model_schedule, weekly_ml_schedule
from pipeline.schedules.magnitude_monitor_schedule import magnitude_monitor_schedule

# E11.1-W1d: w1_parity_schedule was a one-shot gate (fired 2026-06-25) for the
# parallel-validation window. Parity confirmed GREEN — schedule decommissioned.

all_schedules = [
    daily_ingestion_schedule,
    weekly_player_profiles_schedule,
    weekly_clv_monitoring_schedule,
    weekly_ml_schedule,
    weekly_meta_model_schedule,
    magnitude_monitor_schedule,
] + all_intraday_schedules
