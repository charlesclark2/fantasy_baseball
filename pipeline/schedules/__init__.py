from pipeline.schedules.daily_ingestion_schedule import daily_ingestion_schedule
from pipeline.schedules.intraday_schedules import all_intraday_schedules
# E11.1-W11-E: parlay_api DECOMMISSIONED (Parlay platform retired). historical_matches_weekly_schedule
# — the last live parlay ingestion — is removed with its asset/schedule/job files.
from pipeline.schedules.weekly_player_profiles_schedule import weekly_player_profiles_schedule
from pipeline.schedules.weekly_clv_monitoring_schedule import weekly_clv_monitoring_schedule
from pipeline.schedules.weekly_ml_schedules import weekly_meta_model_schedule, weekly_ml_schedule
from pipeline.schedules.magnitude_monitor_schedule import magnitude_monitor_schedule
from pipeline.schedules.settlement_schedule import settlement_schedule
# NCAAF-P1.1: game-day-gated NCAAF/NFL mart rebuilds. ⛔ Both ship default_status=STOPPED
# (operator-gated — no live football until Aug/Sep 2026). Enable in Dagit before kickoff.
from pipeline.schedules.sports_dbt_schedules import (
    sports_ncaaf_dbt_schedule,
    sports_nfl_dbt_schedule,
)
# NCAAF-P0.7: the annual PRE-SEASON roll-forward refresh. ⛔ default_status=STOPPED (operator-gated,
# needs CFBD_API_KEY on the box) — ENABLE in Dagit before the Aug-29 opener (the launch-critical
# action; intended state in BOX_OPERATIONS.md §10).
# NF-D1: the annual NFL season roll-forward refresh (rosters/schedule/depth_charts/injuries/
# rookie class). ⛔ default_status=STOPPED (operator-gated — the mart-rebuild step shares the
# sports_nfl_dbt_build_job box-readiness prereq; the ingest step itself needs no API key).
# NF-D5: the daily (through camp) Sleeper forward-availability refresh, continuing NF-D2 slice 5.
# ⛔ default_status=STOPPED (operator-gated — same box-readiness prereq as NF-D1's roll-forward;
# the Sleeper fetch itself needs no API key). WARN-tier throughout — advisory, non-serving.
from pipeline.schedules.sports_rollforward_schedules import (
    sports_ncaaf_roll_forward_schedule,
    sports_nfl_roll_forward_schedule,
    sports_nfl_sleeper_injuries_schedule,
)
# NCAAF-P0.6b: the recurring IN-SEASON closing-line catch-up (weekly, Aug-Jan). ⛔ default_status=
# STOPPED (operator-gated, needs ODDS_API_KEY + CFBD_API_KEY) — ENABLE alongside the roll-forward
# schedule before the Aug-29 opener (intended state in BOX_OPERATIONS.md §10).
from pipeline.schedules.sports_odds_capture_schedules import sports_ncaaf_odds_capture_schedule
# E7.1 — daily MiLB incremental ingest. default_status=RUNNING (self-start; continuous capture of
# the live 2026 season). Isolated single-op job; WARN-tier; free Stats API; Snowflake-free.
# NF-W0a: NFL point-in-time forward capture. weather + metadata ship RUNNING (FREE, and a missed
# checkpoint is PERMANENT data loss — a STOPPED schedule here would be found out in January);
# ⛔ the MARKET schedule ships STOPPED (PAID Odds-API credits) and MUST be enabled before the
# 2026-09-09 opener or no Tue/Fri market feature is ever backtestable.
from pipeline.schedules.sports_nfl_pit_capture_schedules import (
    sports_nfl_pit_market_schedule,
    sports_nfl_pit_metadata_schedule,
    sports_nfl_pit_weather_schedule,
)
from pipeline.schedules.milb_ingest_schedule import milb_ingest_schedule

# E11.1-W1d: w1_parity_schedule was a one-shot gate (fired 2026-06-25) for the
# parallel-validation window. Parity confirmed GREEN — schedule decommissioned.

all_schedules = [
    daily_ingestion_schedule,
    weekly_player_profiles_schedule,
    weekly_clv_monitoring_schedule,
    weekly_ml_schedule,
    weekly_meta_model_schedule,
    magnitude_monitor_schedule,
    settlement_schedule,
    sports_ncaaf_dbt_schedule,
    sports_nfl_dbt_schedule,
    sports_ncaaf_roll_forward_schedule,
    sports_nfl_roll_forward_schedule,
    sports_nfl_sleeper_injuries_schedule,
    sports_ncaaf_odds_capture_schedule,
    sports_nfl_pit_weather_schedule,
    sports_nfl_pit_metadata_schedule,
    sports_nfl_pit_market_schedule,
    milb_ingest_schedule,
] + all_intraday_schedules
