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
from pipeline.jobs.settlement_jobs import settle_user_bets_job
from pipeline.jobs.weekly_player_profiles_job import weekly_player_profiles_job
# E11.1-W11-E: historical_matches_catchup_job DECOMMISSIONED (Parlay platform retired) — job removed.
from pipeline.jobs.clv_monitoring_job import clv_monitoring_job
from pipeline.jobs.weekly_ml_job import weekly_meta_model_job, weekly_ml_job
from pipeline.jobs.magnitude_monitor_job import magnitude_monitor_job
from pipeline.jobs.w1_parity_job import w1_parity_job
from pipeline.jobs.sports_dbt_job import (
    sports_ncaaf_dbt_build_job,
    sports_nfl_dbt_build_job,
)
# NCAAF-P0.7: the annual pre-season season roll-forward (schedule + covariates → mart rebuild).
from pipeline.jobs.sports_ncaaf_rollforward_job import sports_ncaaf_roll_forward_job
# NF-D1: the annual NFL season roll-forward (rosters/schedule/depth_charts/injuries/rookie class
# → mart rebuild) — the NFL analog of NCAAF-P0.7.
from pipeline.jobs.sports_nfl_board_publish_job import sports_nfl_board_publish_job
from pipeline.jobs.sports_nfl_weekly_serving_job import (
    sports_nfl_weekly_freshness_job,
    sports_nfl_weekly_serving_job,
    sports_nfl_weekly_freshness_job,
)
from pipeline.jobs.sports_nfl_rollforward_job import sports_nfl_roll_forward_job
# NF-D5: daily (through camp) Sleeper forward-availability capture — continues NF-D2 slice 5.
from pipeline.jobs.sports_nfl_sleeper_injuries_job import sports_nfl_sleeper_injuries_job
# NCAAF-P0.6b: the recurring IN-SEASON closing-line catch-up (bridges the P0.6 one-time backfill).
from pipeline.jobs.sports_ncaaf_odds_capture_job import sports_ncaaf_odds_capture_job
from pipeline.jobs.sports_ncaaf_odds_live_job import sports_ncaaf_odds_live_job
# NCAAF-PS: the weekly PRE-KICKOFF prediction snapshot (per-game predictives + the P1.5 futures
# board → the lake). TIME-CRITICAL in the same sense as the NF-W0a capture jobs — a prediction not
# written before kickoff can never be written, and a backtest is not a substitute.
from pipeline.jobs.sports_ncaaf_prediction_snapshot_job import (
    sports_ncaaf_prediction_snapshot_job,
)
from pipeline.jobs.sports_ncaaf_serving_write_job import (
    sports_ncaaf_serving_write_job,
)
# NF-W0a: the NFL point-in-time FORWARD CAPTURE jobs (weather ladder / injuries+schema / market).
# TIME-CRITICAL — a checkpoint not captured cannot be backfilled (the Open-Meteo archive returns
# observations, and the odds history holds only closing lines).
from pipeline.jobs.sports_nfl_pit_capture_job import (
    sports_nfl_pit_market_job,
    sports_nfl_pit_metadata_job,
    sports_nfl_pit_weather_job,
)
from pipeline.jobs.milb_ingest_job import milb_ingest_job  # E7.1 — isolated daily MiLB ingest
# INC-41 — off-cycle serving-artifact freshness SLA check (SF-free; pages, never HALTs)
from pipeline.jobs.artifact_freshness_job import artifact_freshness_job

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
    settle_user_bets_job,
    weekly_player_profiles_job,
    clv_monitoring_job,
    weekly_ml_job,
    weekly_meta_model_job,
    magnitude_monitor_job,
    w1_parity_job,
    sports_nfl_dbt_build_job,
    sports_ncaaf_dbt_build_job,
    sports_ncaaf_roll_forward_job,
    sports_nfl_board_publish_job,
    sports_nfl_weekly_serving_job,
    sports_nfl_roll_forward_job,
    sports_nfl_sleeper_injuries_job,
    sports_ncaaf_odds_capture_job,
    sports_ncaaf_odds_live_job,
    sports_ncaaf_prediction_snapshot_job,
    sports_ncaaf_serving_write_job,
    sports_nfl_pit_weather_job,
    sports_nfl_pit_metadata_job,
    sports_nfl_pit_market_job,
    milb_ingest_job,
    artifact_freshness_job,
]
