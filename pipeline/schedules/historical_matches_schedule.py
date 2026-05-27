from datetime import date, timedelta

from dagster import RunRequest, ScheduleEvaluationContext, define_asset_job, schedule

from pipeline.assets.historical_matches_asset import parlay_historical_matches_catchup

historical_matches_catchup_job = define_asset_job(
    name="historical_matches_catchup_job",
    selection=[parlay_historical_matches_catchup],
)


@schedule(
    cron_schedule="0 10 * * 1",  # 06:00 EDT every Monday
    job=historical_matches_catchup_job,
    execution_timezone="UTC",
)
def historical_matches_weekly_schedule(context: ScheduleEvaluationContext):
    today = date.today()
    return RunRequest(
        run_config={
            "ops": {
                "parlay_historical_matches_catchup": {
                    "config": {
                        "start_date": (today - timedelta(days=14)).isoformat(),
                        "end_date": (today - timedelta(days=1)).isoformat(),
                    }
                }
            }
        }
    )
