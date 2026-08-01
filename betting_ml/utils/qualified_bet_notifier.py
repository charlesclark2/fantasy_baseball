"""E9.9 / A0.6 -> E9.50 — publish a post-lineup "actionable picks" alert to SNS.

`predict_today` calls :func:`notify_post_lineup_actionable_picks_safe` after the
bet-permission gate, on POST-LINEUP (lineup-confirmed) re-scores only. A qualified
row (`qualified_bet` = a non-abstain Layer-4 H2H or totals decision — props never
appear in this table, so scope is naturally H2H+totals only) with a healthy
`data_source` (excludes the worst-tier `intraday_fallback` carry-forward) is an
actionable, lineup-confirmed pick. When a confirmed-lineup re-score newly
qualifies one or more such picks, this publishes one SNS message that the
`push-notification-sender` Lambda fans out to opted-in users (push / email / SMS).

E9.50 (2026-07-31) retires the old per-SLATE, per-DAY idempotent alert and its
morning trigger: `lineup_monitor` calls predict_today per-game as lineups
confirm, staggered over hours, so post-lineup picks arrive INCREMENTALLY across
many re-score cycles, not in one batch. Dedupe is now per (date, game_pk): a
DynamoDB conditional put claims each game's alert individually, so a pick is
emailed exactly once — the first time its game becomes actionable — and a later
re-score of the SAME game (a pitcher-change re-trigger, a retry) never re-sends
it. The picks that newly qualify within one re-score cycle (lineup_monitor
already batches a tick's newly-ready games into a single predict_today
invocation) are batched into ONE digest, never one email per pick. The morning
(pre-lineup) run no longer calls this at all — a pre-lineup pick is a preview,
not confirmed-actionable, so the first alert a user gets for a slate is now the
post-lineup digest.

WARN-tier (failure-semantics contract): a publish failure must NEVER crash
predict_today — it is peripheral to the serving-critical prediction write. So the
public entry point catches everything and returns a bool instead of raising.
"""

from __future__ import annotations

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

from betting_ml.utils.game_day import current_game_date_iso

logger = logging.getLogger(__name__)

# The worst-tier data_source (team-level carry-forward, no lineup/starter overlay) —
# never present it as a lineup-confirmed actionable pick even if qualified_bet is TRUE.
_DEGRADED_DATA_SOURCE = "intraday_fallback"


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


def _is_actionable(row: dict) -> bool:
    """H2H/totals qualified, lineup-confirmed-quality, and identifiable by game_pk."""
    return bool(
        row.get("qualified_bet")
        and row.get("game_pk") is not None
        and row.get("data_source") != _DEGRADED_DATA_SOURCE
    )


def _claim_game_alert_once(cache_table: str, target_date: str, game_pk, region: str) -> bool:
    """Claim a (date, game_pk) post-lineup alert via a conditional put.

    True = we claimed it (this game has never alerted today). False = already
    sent — a later re-score of the same game (e.g. a pitcher-change re-trigger)
    must not re-notify.
    """
    table = boto3.resource("dynamodb", region_name=region).Table(cache_table)
    try:
        table.put_item(
            Item={
                "pk": "ops",
                "sk": f"post_lineup_alert_sent#{target_date}#{game_pk}",
                "value": target_date,
            },
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def notify_post_lineup_actionable_picks_safe(
    target_date: str, rows: list[dict], *, lineup_confirmed: bool, now=None
) -> bool:
    """Publish a digest of NEWLY-actionable, lineup-confirmed picks. Never raises.

    Returns True iff a message was actually published. Skips silently (returns
    False) for: a pre-lineup (morning) run (`lineup_confirmed=False` — the
    retired path), a non-today (backfill) date, zero actionable rows in this
    cycle, every actionable game already alerted today, or an unset topic.
    """
    try:
        if not lineup_confirmed:
            # E9.50: the morning pre-lineup email is retired. A pre-lineup row is a
            # preview (lineups not yet confirmed) — never actionable — so only a
            # post-lineup (lineup-confirmed) re-score may alert.
            return False

        topic = os.environ.get("QUALIFIED_BETS_SNS_TOPIC_ARN", "").strip()
        if not topic:
            # ALERT-loud-but-continue: a missing env var must not be a silent skip.
            logger.warning(
                "QUALIFIED_BETS_SNS_TOPIC_ARN unset — skipping post-lineup alert for %s",
                target_date,
            )
            return False

        # Only alert for the real current game day — never a backfill / historical re-score.
        if target_date != current_game_date_iso(now):
            return False

        actionable_rows = [r for r in rows if _is_actionable(r)]
        if not actionable_rows:
            return False

        # INC-31: resolve region via AWS_REGION only (default us-east-1) — do NOT fall
        # through to AWS_DEFAULT_REGION. The box sets AWS_DEFAULT_REGION=us-east-2 for
        # DuckDB/S3 lakehouse reads; consulting it here misdirects BOTH the idempotency
        # -cache PutItem and the SNS publish, but the serving-cache table AND the SNS
        # topic both live in us-east-1 -> AccessDenied -> alerts silently never fire.
        region = os.environ.get("AWS_REGION", "us-east-1")
        cache_table = os.environ.get("SERVING_CACHE_TABLE", "credence-prod-serving-cache")

        newly_claimed: list[dict] = []
        for r in actionable_rows:
            try:
                if _claim_game_alert_once(cache_table, target_date, r["game_pk"], region):
                    newly_claimed.append(r)
            except Exception:  # noqa: BLE001 — one game's claim failure must not sink the batch
                logger.warning(
                    "post-lineup alert: claim failed for game_pk=%s (non-fatal)",
                    r.get("game_pk"), exc_info=True,
                )

        if not newly_claimed:
            logger.info(
                "post-lineup alert: all %d actionable game(s) already alerted for %s — skipping",
                len(actionable_rows), target_date,
            )
            return False

        msg = build_qualified_plays_message(target_date, newly_claimed)

        boto3.client("sns", region_name=region).publish(
            TopicArn=topic,
            Subject=f"Credence: {msg['n_qualified']} lineup-confirmed play(s)"[:100],
            Message=json.dumps(msg),
        )
        logger.info(
            "published post-lineup actionable-pick digest for %s (%d new play(s), "
            "%d already alerted this slate)",
            target_date, msg["n_qualified"], len(actionable_rows) - len(newly_claimed),
        )
        return True
    except Exception:  # noqa: BLE001 — WARN tier: a publish failure must not crash predict_today
        logger.warning("post-lineup actionable-pick SNS publish failed (non-fatal)", exc_info=True)
        return False
