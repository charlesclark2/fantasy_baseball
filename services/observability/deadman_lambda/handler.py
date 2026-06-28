"""INC-16-P6 — daily-output dead-man switch (OFF-box AWS Lambda).

The highest-value alert: it watches the THING USERS SEE (today's serving output),
not a process — so it fires whatever the root cause (dead box, crashed daemon,
failed dbt build, bad deploy, stuck cron). It runs OFF the box (Lambda + an
EventBridge schedule) precisely so a DEAD box can't take the alarm down with it.

How: `write_serving_store` stamps a daily heartbeat into the DynamoDB serving
cache — item (pk="ops", sk="heartbeat#daily") whose JSON `value.date` is today's
serving date. EventBridge invokes this Lambda at the morning cutoff; if the
heartbeat's date isn't today (ET) — or the item is missing — the serving cycle
did NOT complete and we publish a CRITICAL alert to the shared SNS topic.

Why a heartbeat, not a raw "are there picks?" count: 0 picks on a legitimate MLB
off-day looks identical to a dead box. The heartbeat proves the cycle RAN; it also
carries `n_picks`/`errors` so we can warn on a degraded-but-alive run.

Env:
  SERVING_CACHE_TABLE   DynamoDB table (default credence-prod-serving-cache)
  ALERT_SNS_TOPIC_ARN   SNS topic (required to actually send)
  HEARTBEAT_TZ          IANA tz for "today" (default America/New_York)
  WARN_ON_ERRORS        "1" to also alert when heartbeat present but errors>0

IAM (Lambda execution role): dynamodb:GetItem on the table + sns:Publish on the topic.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3

_TABLE = os.environ.get("SERVING_CACHE_TABLE", "credence-prod-serving-cache")
_TOPIC = os.environ.get("ALERT_SNS_TOPIC_ARN", "").strip()
_TZ = os.environ.get("HEARTBEAT_TZ", "America/New_York")
_WARN_ON_ERRORS = os.environ.get("WARN_ON_ERRORS", "1") == "1"
_SUBJECT_PREFIX = "[Credence PROD]"


def _today_local() -> str:
    return datetime.now(ZoneInfo(_TZ)).date().isoformat()


def _publish(severity: str, subject: str, body: str) -> None:
    full_subject = f"{_SUBJECT_PREFIX} {severity}: {subject}"[:100]
    if not _TOPIC:
        print(f"WARN: ALERT_SNS_TOPIC_ARN unset — would have sent: {full_subject}\n{body}")
        return
    boto3.client("sns").publish(TopicArn=_TOPIC, Subject=full_subject, Message=f"severity: {severity}\n\n{body}\n")
    print(f"published: {full_subject}")


def _get_heartbeat() -> dict | None:
    resp = boto3.resource("dynamodb").Table(_TABLE).get_item(Key={"pk": "ops", "sk": "heartbeat#daily"})
    item = resp.get("Item")
    if not item:
        return None
    try:
        return json.loads(item["value"])
    except Exception:
        return {"_unparseable": True}


def lambda_handler(event, context):  # noqa: ANN001 — Lambda signature
    today = _today_local()
    hb = _get_heartbeat()

    # 1) missing or stale heartbeat → the serving cycle did NOT complete today.
    if hb is None or hb.get("date") != today:
        last = (hb or {}).get("date", "NONE")
        subject = "Daily serving output MISSING"
        body = (
            f"The daily serving cycle has NOT produced today's output by the cutoff.\n\n"
            f"  expected serving date (today, {_TZ}): {today}\n"
            f"  last heartbeat date in DynamoDB:       {last}\n"
            f"  table:                                 {_TABLE}\n\n"
            f"This fires regardless of root cause (dead box / crashed daemon / failed dbt "
            f"build / bad deploy / stuck cron). FIRST ACTION: check the box — "
            f"`aws ssm start-session --target i-07594af1679f81c38`, then "
            f"`docker compose ps` and the daily_ingestion_job run in Dagit."
        )
        _publish("CRITICAL", subject, body)
        return {"status": "ALERT", "reason": "missing_or_stale_heartbeat", "today": today, "last": last}

    # 2) heartbeat present for today but the run logged errors → degraded-but-alive.
    errors = hb.get("errors")
    if _WARN_ON_ERRORS and isinstance(errors, int) and errors > 0:
        _publish(
            "WARN",
            "Daily serving ran with errors",
            f"Today's serving cycle completed (date={today}) but logged {errors} error(s); "
            f"n_picks={hb.get('n_picks')}. Some cache blobs may be missing — check the "
            f"write_serving_store_op logs in Dagit.",
        )
        return {"status": "WARN", "errors": errors, "today": today}

    return {"status": "OK", "today": today, "n_picks": hb.get("n_picks")}
