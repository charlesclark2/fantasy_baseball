"""E9.9 / A0.6 — publish a "qualified plays today" alert to SNS.

`predict_today` calls :func:`notify_qualified_plays_safe` after the bet-permission
gate. When the model posts `qualified_bet > 0` for TODAY's slate, it publishes one
SNS message that the `push-notification-sender` Lambda fans out to opted-in users
(push / email / SMS).

WARN-tier (failure-semantics contract): a publish failure must NEVER crash
predict_today — it is peripheral to the serving-critical prediction write. So the
public entry point catches everything and returns a bool instead of raising.

Idempotent: predict_today runs multiple times a day (morning pre-lineup +
post-lineup re-score) and E11.22 runs it heavily for audits. A DynamoDB
conditional put keyed by the game date claims the day's single send, so the alert
fires at most once per slate no matter how many times scoring runs.
"""

from __future__ import annotations

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

from betting_ml.utils.game_day import current_game_date_iso

logger = logging.getLogger(__name__)


def build_qualified_plays_message(target_date: str, rows: list[dict]) -> dict:
    """Neutral, model-relative payload — the honest copy is rendered by the Lambda."""
    plays: list[dict] = []
    for r in rows:
        if not r.get("qualified_bet"):
            continue
        home = r.get("home_team_abbrev") or r.get("home_team") or "?"
        away = r.get("away_team_abbrev") or r.get("away_team") or "?"
        plays.append(
            {
                "matchup": f"{away} @ {home}",
                "pick": r.get("pick"),
                "game_pk": r.get("game_pk"),
            }
        )
    return {"date": target_date, "n_qualified": len(plays), "plays": plays}


def _claim_send_once(cache_table: str, target_date: str, region: str) -> bool:
    """Claim the day's single alert via a conditional put. True = we claimed it."""
    table = boto3.resource("dynamodb", region_name=region).Table(cache_table)
    try:
        table.put_item(
            Item={"pk": "ops", "sk": f"alert_sent#{target_date}", "value": target_date},
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def notify_qualified_plays_safe(target_date: str, rows: list[dict], *, now=None) -> bool:
    """Publish the qualified-plays alert for TODAY. Never raises.

    Returns True iff a message was actually published. Skips silently (returns False)
    for: unset topic, a non-today (backfill) date, zero qualified plays, or an already
    -claimed day. `now` is injectable purely for freeze-time tests.
    """
    try:
        topic = os.environ.get("QUALIFIED_BETS_SNS_TOPIC_ARN", "").strip()
        if not topic:
            # ALERT-loud-but-continue: a missing env var must not be a silent skip.
            logger.warning(
                "QUALIFIED_BETS_SNS_TOPIC_ARN unset — skipping qualified-play alert for %s",
                target_date,
            )
            return False

        # Only alert for the real current game day — never a backfill / historical re-score.
        if target_date != current_game_date_iso(now):
            return False

        msg = build_qualified_plays_message(target_date, rows)
        if msg["n_qualified"] <= 0:
            return False

        # INC-31: resolve region via AWS_REGION only (default us-east-1) — do NOT fall through to
        # AWS_DEFAULT_REGION. The box sets AWS_DEFAULT_REGION=us-east-2 for DuckDB/S3 lakehouse reads;
        # consulting it here misdirects BOTH the idempotency-cache PutItem and the SNS publish to
        # us-east-2, but the serving-cache table AND the SNS topic both live in us-east-1 → AccessDenied
        # → alerts silently never fire. Mirrors serving_cache.py's region resolution (same table).
        region = os.environ.get("AWS_REGION", "us-east-1")
        cache_table = os.environ.get("SERVING_CACHE_TABLE", "credence-prod-serving-cache")
        if not _claim_send_once(cache_table, target_date, region):
            logger.info("qualified-play alert already sent for %s — skipping", target_date)
            return False

        boto3.client("sns", region_name=region).publish(
            TopicArn=topic,
            Subject=f"Credence: {msg['n_qualified']} qualified play(s) today"[:100],
            Message=json.dumps(msg),
        )
        logger.info(
            "published qualified-play alert for %s (%d play(s))", target_date, msg["n_qualified"]
        )
        return True
    except Exception:  # noqa: BLE001 — WARN tier: a publish failure must not crash predict_today
        logger.warning("qualified-play SNS publish failed (non-fatal)", exc_info=True)
        return False
