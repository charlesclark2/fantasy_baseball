from pipeline.sensors.lineup_monitor_sensor import lineup_monitor_sensor
from pipeline.sensors.morning_watchdog_sensor import morning_watchdog_sensor
from pipeline.sensors.pregame_alert_sensor import pregame_alert_sensor
from pipeline.sensors.clv_alert_sensor import clv_alert_sensor
from pipeline.sensors.statcast_freshness_sensor import statcast_freshness_sensor
from pipeline.sensors.model_health_alert_sensor import model_health_alert_sensor
from pipeline.sensors.conviction_pick_alert_sensor import conviction_pick_alert_sensor
from pipeline.sensors.odds_current_rebuild_sensor import odds_current_rebuild_sensor
from pipeline.sensors.odds_freshness_alert_sensor import odds_freshness_alert_sensor
from pipeline.sensors.schedule_freshness_alert_sensor import schedule_freshness_alert_sensor
from pipeline.sensors.run_failure_alert_sensor import run_failure_alert_sensor

all_sensors = [
    run_failure_alert_sensor,  # INC-16-P6: OSS run-failure → SES email (replaces Dagster+ alerting)
    lineup_monitor_sensor,
    morning_watchdog_sensor,
    pregame_alert_sensor,
    clv_alert_sensor,
    statcast_freshness_sensor,
    model_health_alert_sensor,
    conviction_pick_alert_sensor,
    odds_current_rebuild_sensor,
    odds_freshness_alert_sensor,
    schedule_freshness_alert_sensor,  # E11.8: HARD alert for schedule data staleness
]
