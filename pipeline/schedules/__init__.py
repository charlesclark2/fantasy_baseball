from pipeline.schedules.daily_ingestion_schedule import daily_ingestion_schedule
from pipeline.schedules.intraday_schedules import all_intraday_schedules
from pipeline.schedules.historical_matches_schedule import historical_matches_weekly_schedule
from pipeline.schedules.weekly_player_profiles_schedule import weekly_player_profiles_schedule
from pipeline.schedules.weekly_clv_monitoring_schedule import weekly_clv_monitoring_schedule

all_schedules = [
    daily_ingestion_schedule,
    historical_matches_weekly_schedule,
    weekly_player_profiles_schedule,
    weekly_clv_monitoring_schedule,
] + all_intraday_schedules
