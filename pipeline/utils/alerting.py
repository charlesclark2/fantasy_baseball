"""INC-16-P6 — shared ops-alerting notifier (SNS-backed, email delivery).

ONE channel for the whole AWS box: a single SNS topic (`ALERT_SNS_TOPIC_ARN`)
with an operator-confirmed email subscription. Everything that needs to page —
the Dagster `run_failure_alert_sensor`, the revived freshness sensors, the host
healthcheck, `deploy.sh` rollback — publishes here, so there is ONE inbox and
ONE subscription to confirm. CloudWatch alarms (EC2 status / mem / disk / CPU)
target the *same* topic directly (they can only target SNS), so SNS is the
natural unifying backbone rather than calling SES per-message.

Why this exists (the INC-16 cutover gap): the legacy alert sensors raised an
exception to fire **Dagster+ Cloud's built-in email-on-failure** — a feature that
went away when P4 turned Dagster+ OFF and moved orchestration to the self-hosted
box. Those raises now vanish into sensor-tick logs nobody reads. This notifier
restores an email path under Dagster OSS.

Contract: `send_alert()` is **non-raising** — alerting must NEVER crash the caller
(a serving op, a sensor tick). On any misconfig/SNS error it logs and returns
False. It also rate-limits per `dedup_key` so a flapping condition can't spam the
inbox within the daemon's lifetime.
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

# Per-process rate-limit: dedup_key -> last-sent epoch seconds. The Dagster daemon
# is long-lived, so this survives across sensor ticks within one daemon run.
_LAST_SENT: dict[str, float] = {}
_DEFAULT_DEDUP_TTL_S = 3600  # at most one email per distinct key per hour

_SUBJECT_PREFIX = "[Credence PROD]"
_SNS_SUBJECT_MAX = 100  # SNS hard limit


def _region() -> str:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"


def _topic_arn() -> str:
    return os.environ.get("ALERT_SNS_TOPIC_ARN", "").strip()


def _clamp_subject(subject: str) -> str:
    s = f"{_SUBJECT_PREFIX} {subject}".strip()
    # SNS subjects must be ASCII, <=100 chars, no newlines.
    s = s.replace("\n", " ").replace("\r", " ")
    s = s.encode("ascii", "ignore").decode("ascii")
    return s[:_SNS_SUBJECT_MAX]


def send_alert(
    subject: str,
    message: str,
    *,
    severity: str = "ERROR",
    dedup_key: str | None = None,
    dedup_ttl_s: int = _DEFAULT_DEDUP_TTL_S,
) -> bool:
    """Publish an ops alert to the shared SNS topic. Never raises.

    Args:
        subject: short line (job/check name + what's wrong); prefixed + clamped to 100c.
        message: full body (run id, error, first action).
        severity: "CRITICAL" | "ERROR" | "WARN" — surfaced in the subject.
        dedup_key: rate-limit key; repeats within `dedup_ttl_s` are dropped.
                   Defaults to the (severity, subject) pair.
        dedup_ttl_s: rate-limit window in seconds.

    Returns:
        True if published, False if suppressed (rate-limited) or on any error.
    """
    key = dedup_key or f"{severity}:{subject}"
    now = time.time()
    last = _LAST_SENT.get(key)
    if last is not None and (now - last) < dedup_ttl_s:
        logger.info("send_alert: suppressed (rate-limited) key=%s", key)
        return False

    arn = _topic_arn()
    if not arn:
        # Soft-fail: never crash a serving op because alerting is unconfigured.
        logger.warning(
            "send_alert: ALERT_SNS_TOPIC_ARN unset — alert NOT sent. subject=%r", subject
        )
        return False

    full_subject = _clamp_subject(f"{severity}: {subject}")
    body = f"severity: {severity}\n\n{message}\n"
    try:
        import boto3

        boto3.client("sns", region_name=_region()).publish(
            TopicArn=arn, Subject=full_subject, Message=body
        )
        _LAST_SENT[key] = now
        logger.info("send_alert: published key=%s subject=%r", key, full_subject)
        return True
    except Exception as exc:  # noqa: BLE001 — alerting must never raise
        logger.error("send_alert: SNS publish failed (%s): %s", type(exc).__name__, exc)
        return False
