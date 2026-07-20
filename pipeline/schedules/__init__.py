from pipeline.schedules.daily_ingestion_schedule import daily_ingestion_schedule
from pipeline.schedules.intraday_schedules import all_intraday_schedules
# E11.1-W11-E: parlay_api DECOMMISSIONED (Parlay platform retired). historical_matches_weekly_schedule
# — the last live parlay ingestion — is removed with its asset/schedule/job files.
from pipeline.schedules.weekly_player_profiles_schedule import weekly_player_profiles_schedule
from pipeline.schedules.weekly_clv_monitoring_schedule import weekly_clv_monitoring_schedule
from pipeline.schedules.weekly_ml_schedules import weekly_meta_model_schedule, weekly_ml_schedule
from pipeline.schedules.magnitude_monitor_schedule import magnitude_monitor_schedule
# NCAAF-P1.1: game-day-gated NCAAF/NFL mart rebuilds. ⛔ Both ship default_status=STOPPED
# (operator-gated — no live football until Aug/Sep 2026). Enable in Dagit before kickoff.
from pipeline.schedules.sports_dbt_schedules import (
    sports_ncaaf_dbt_schedule,
    sports_nfl_dbt_schedule,
)

# E11.1-W1d: w1_parity_schedule was a one-shot gate (fired 2026-06-25) for the
# parallel-validation window. Parity confirmed GREEN — schedule decommissioned.

all_schedules = [
    daily_ingestion_schedule,
    weekly_player_profiles_schedule,
    weekly_clv_monitoring_schedule,
    weekly_ml_schedule,
    weekly_meta_model_schedule,
    magnitude_monitor_schedule,
    sports_ncaaf_dbt_schedule,
    sports_nfl_dbt_schedule,
] + all_intraday_schedules
