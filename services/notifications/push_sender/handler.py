"""push-notification-sender — SNS-triggered fan-out of "qualified plays today" alerts.

E9.9 / A0.6. `predict_today` publishes ONE SNS message when the model posts
`qualified_bet > 0` for today's slate. This Lambda receives it, scans the
DynamoDB subscriptions table for opted-in users, and fans out per-channel:

  • Web Push  (pywebpush + VAPID)  — users who granted browser push permission
  • Email     (SES)               — the always-available fallback
  • SMS       (SNS Publish)       — users who entered a phone number in Settings

Design rules (from the story + failure-semantics contract):
  • Per-recipient try/except — one bad endpoint never blocks the batch.
  • Web Push 404/410 (Gone) → prune the dead `push_subscription` from DynamoDB.
  • HONEST framing — the copy says the model posted N *qualified* plays; it is NOT
    a "+EV / you'll win" claim (best_alpha = 0). No profitability language.

This package is deployed as a self-contained Lambda (it bundles pywebpush/py-vapid),
so it does NOT import `betting_ml` — the copy lives here and is unit-tested here.

Env:
  DYNAMO_PUSH_SUBSCRIPTIONS_TABLE  subscriptions table (default credence-prod-dynamo-push-subscriptions)
  VAPID_PRIVATE_KEY                VAPID private key (PEM or base64url) — Lambda ONLY, never the bundle
  VAPID_SUBJECT                    VAPID `sub` claim, e.g. mailto:support@credencesports.com
  SES_FROM_ADDRESS                 verified SES sender (default alerts@credencesports.com)
  SES_CONFIGURATION_SET            optional SES config set (bounce/complaint tracking)
  APP_URL                          deep-link base (default https://credencesports.com)
  AWS_REGION                       provided by the Lambda runtime
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_TABLE = os.environ.get("DYNAMO_PUSH_SUBSCRIPTIONS_TABLE", "credence-prod-dynamo-push-subscriptions")
_VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
_VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:support@credencesports.com").strip()
_SES_FROM = os.environ.get("SES_FROM_ADDRESS", "alerts@credencesports.com").strip()
_SES_CONFIG_SET = os.environ.get("SES_CONFIGURATION_SET", "").strip()
_APP_URL = os.environ.get("APP_URL", "https://credencesports.com").rstrip("/")

# Honest, model-relative disclaimer. Deliberately free of profitability / bet-rec
# language (cf. the E5.5 honest-framing guard). Enforced by the unit tests here.
_DISCLAIMER = (
    "This reflects the model's qualified selections for today. It is not betting "
    "advice. Past performance does not indicate future results."
)


class PushEndpointGone(Exception):
    """Raised when a Web Push endpoint returns 404/410 (Gone) → prune it."""


# ── Copy (pure, unit-tested) ────────────────────────────────────────────────

def _plural(n: int) -> str:
    return "play" if n == 1 else "plays"


def render_summary_lines(plays: list[dict[str, Any]], limit: int = 6) -> list[str]:
    """One neutral line per qualified play: 'AWAY @ HOME — <pick>'."""
    lines: list[str] = []
    for p in plays[:limit]:
        matchup = p.get("matchup") or f"{p.get('away', '?')} @ {p.get('home', '?')}"
        pick = p.get("pick")
        lines.append(f"{matchup} — {pick}" if pick else matchup)
    if len(plays) > limit:
        lines.append(f"…and {len(plays) - limit} more")
    return lines


def build_push_payload(msg: dict[str, Any]) -> dict[str, Any]:
    n = int(msg.get("n_qualified", 0))
    date = msg.get("date", "")
    return {
        "title": f"Credence — {n} qualified {_plural(n)} for today",
        "body": f"The model posted {n} qualified {_plural(n)} for today's slate ({date}).",
        "url": f"{_APP_URL}/dashboard",
        "tag": f"qualified-plays-{date}",
    }


def build_sms(msg: dict[str, Any]) -> str:
    n = int(msg.get("n_qualified", 0))
    date = msg.get("date", "")
    return (
        f"Credence: the model posted {n} qualified {_plural(n)} for today's slate "
        f"({date}). Review at {_APP_URL}/dashboard . Not betting advice."
    )


def build_email(msg: dict[str, Any]) -> tuple[str, str, str]:
    """Return (subject, html_body, text_body)."""
    n = int(msg.get("n_qualified", 0))
    date = msg.get("date", "")
    plays = msg.get("plays") or []
    lines = render_summary_lines(plays)

    subject = f"Credence — {n} qualified {_plural(n)} for today's slate"

    text = (
        f"The model posted {n} qualified {_plural(n)} for today's slate ({date}).\n\n"
        + "\n".join(lines)
        + f"\n\nReview: {_APP_URL}/dashboard\n\n{_DISCLAIMER}\n"
    )

    list_html = "".join(
        f'<li style="padding:6px 0;border-bottom:1px solid #262626;color:#e5e5e5;'
        f'font-family:monospace;font-size:14px;">{_esc(li)}</li>'
        for li in lines
    )
    html = f"""\
<!doctype html><html><body style="margin:0;background:#0a0a0a;padding:24px 0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
    <table role="presentation" width="480" cellpadding="0" cellspacing="0"
           style="background:#141414;border:1px solid #262626;border-radius:12px;overflow:hidden;">
      <tr><td style="padding:24px 28px 8px;">
        <span style="color:#10b981;font-family:sans-serif;font-weight:700;font-size:18px;">Credence</span>
      </td></tr>
      <tr><td style="padding:0 28px 4px;">
        <h1 style="margin:0;color:#ffffff;font-family:sans-serif;font-size:20px;font-weight:700;">
          {n} qualified {_plural(n)} for today
        </h1>
        <p style="margin:6px 0 0;color:#a3a3a3;font-family:sans-serif;font-size:13px;">
          The model posted {n} qualified {_plural(n)} for today's slate ({_esc(date)}).
        </p>
      </td></tr>
      <tr><td style="padding:16px 28px 8px;">
        <ul style="margin:0;padding:0;list-style:none;">{list_html}</ul>
      </td></tr>
      <tr><td style="padding:16px 28px 24px;">
        <a href="{_APP_URL}/dashboard"
           style="display:inline-block;background:#10b981;color:#0a0a0a;text-decoration:none;
                  font-family:sans-serif;font-weight:700;font-size:14px;padding:10px 20px;border-radius:8px;">
          Review today's slate
        </a>
        <p style="margin:18px 0 0;color:#6b7280;font-family:sans-serif;font-size:11px;line-height:1.5;">
          {_esc(_DISCLAIMER)}
        </p>
      </td></tr>
    </table>
  </td></tr></table>
</body></html>"""
    return subject, html, text


def _esc(s: Any) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ── Senders (thin wrappers; monkeypatched in tests) ─────────────────────────

def _send_web_push(subscription: dict[str, Any], payload: dict[str, Any]) -> None:
    from pywebpush import WebPushException, webpush  # bundled in the Lambda package

    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=_VAPID_PRIVATE_KEY,
            vapid_claims={"sub": _VAPID_SUBJECT},
            timeout=10,
        )
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            raise PushEndpointGone(str(status)) from exc
        raise


def _send_email(ses, to_addr: str, subject: str, html: str, text: str) -> None:
    kwargs: dict[str, Any] = {
        "Source": _SES_FROM,
        "Destination": {"ToAddresses": [to_addr]},
        "Message": {
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {
                "Html": {"Data": html, "Charset": "UTF-8"},
                "Text": {"Data": text, "Charset": "UTF-8"},
            },
        },
    }
    if _SES_CONFIG_SET:
        kwargs["ConfigurationSetName"] = _SES_CONFIG_SET
    ses.send_email(**kwargs)


def _send_sms(sns, phone: str, text: str) -> None:
    sns.publish(
        PhoneNumber=phone,
        Message=text,
        MessageAttributes={
            "AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"},
        },
    )


def _prune_push(table, user_id: str) -> None:
    """Remove a dead push endpoint but keep the row (email/SMS prefs survive)."""
    try:
        table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="REMOVE push_subscription SET push_enabled = :f",
            ExpressionAttributeValues={":f": False},
        )
        logger.info("pruned 410/404 push endpoint for user %s", user_id)
    except Exception:
        logger.exception("failed to prune push endpoint for user %s", user_id)


# ── Fan-out ─────────────────────────────────────────────────────────────────

def _iter_enabled_subs(table):
    """Yield every item with master `enabled` = True (paginated scan)."""
    kwargs = {"FilterExpression": Attr("enabled").eq(True)}
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            yield item
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek


def fan_out(msg: dict[str, Any], table, ses, sns) -> dict[str, int]:
    stats = {"push": 0, "email": 0, "sms": 0, "pruned": 0, "errors": 0, "users": 0}
    push_payload = build_push_payload(msg)
    subject, html, text = build_email(msg)
    sms_text = build_sms(msg)

    for item in _iter_enabled_subs(table):
        stats["users"] += 1
        user_id = item.get("user_id", "?")

        # Web Push
        sub = item.get("push_subscription")
        if item.get("push_enabled") and sub:
            try:
                _send_web_push(sub, push_payload)
                stats["push"] += 1
            except PushEndpointGone:
                _prune_push(table, user_id)
                stats["pruned"] += 1
            except Exception:
                logger.exception("web push failed for user %s", user_id)
                stats["errors"] += 1

        # Email (default-on fallback)
        email = item.get("email")
        if item.get("email_enabled", True) and email:
            try:
                _send_email(ses, email, subject, html, text)
                stats["email"] += 1
            except Exception:
                logger.exception("email failed for user %s", user_id)
                stats["errors"] += 1

        # SMS
        phone = item.get("phone_number")
        if item.get("sms_enabled") and phone:
            try:
                _send_sms(sns, phone, sms_text)
                stats["sms"] += 1
            except Exception:
                logger.exception("sms failed for user %s", user_id)
                stats["errors"] += 1

    return stats


def _parse_sns_message(event: dict[str, Any]) -> dict[str, Any]:
    records = event.get("Records") or []
    if not records:
        # Allow a direct (test) invocation with the message inline.
        return event if "n_qualified" in event else {}
    raw = records[0].get("Sns", {}).get("Message", "{}")
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        logger.warning("could not parse SNS message: %r", raw)
        return {}


def lambda_handler(event, context):  # noqa: ANN001 — Lambda signature
    msg = _parse_sns_message(event)
    if not msg or int(msg.get("n_qualified", 0)) <= 0:
        logger.info("no qualified plays in message; nothing to send: %r", msg)
        return {"sent": {}, "note": "no qualified plays"}

    region = os.environ.get("AWS_REGION", "us-east-1")
    table = boto3.resource("dynamodb", region_name=region).Table(_TABLE)
    ses = boto3.client("ses", region_name=region)
    sns = boto3.client("sns", region_name=region)

    stats = fan_out(msg, table, ses, sns)
    logger.info("fan-out complete: %s", stats)
    return {"sent": stats}
