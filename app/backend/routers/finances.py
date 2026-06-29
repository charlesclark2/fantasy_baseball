"""Admin finances endpoint — monthly infrastructure costs + betting P&L.

GET /admin/finances — 6-month rolling window of costs, P&L, and net profitability.

Variable cost sources:
  - Snowflake: ACCOUNT_USAGE.METERING_DAILY_HISTORY (requires IMPORTED PRIVILEGES).
               Cloud-services credits are billed only above 10% of the day's compute
               credits, applied DAILY (see _snowflake_costs_by_month).
  - AWS:       Cost Explorer ce:GetCostAndUsage grouped by SERVICE (requires the
               ce:GetCostAndUsage IAM permission on the Lambda role). Broken into
               line items: EC2, S3, Lambda, API Gateway, DynamoDB, SES, Other AWS.

Post-INC-16 (Railway cancelled, Dagster self-hosted on EC2) there is no separate
Railway/Dagster cost line — that spend now shows up inside the AWS EC2 line item.

Fixed costs and subscription revenue are hardcoded / placeholders updated in this file.
"""

from __future__ import annotations

import datetime
import logging
import os
import time

import boto3
from boto3.dynamodb.conditions import Attr, Key
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.backend.dependencies import get_admin_user
from app.backend.services.snowflake import execute_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

_REGION = os.getenv("AWS_REGION", "us-east-1")
_USER_BETS_TABLE = os.getenv("USER_BETS_TABLE", "credence-prod-dynamo-user-bets")
_USERS_TABLE = os.getenv("USERS_TABLE", "credence-prod-dynamo-users")
_OWNER_EMAIL = "ctcb57@gmail.com"
# Set OWNER_USER_ID to the owner's Cognito sub (find in Cognito console or JWT 'sub' claim).
# Without it, finances falls back to a DynamoDB Scan which requires dynamodb:Scan on the
# Lambda role — add that permission or just set this env var.
_OWNER_USER_ID_OVERRIDE = os.getenv("OWNER_USER_ID")

# Finances start month — project launched May 2026
_FINANCES_START = datetime.date(2026, 5, 1)

# ── Fixed monthly costs (USD) — update here when prices change ────────────────

_FIXED_LINE_ITEMS: dict[str, float] = {
    "Domain": round(15 / 12, 2),   # $15/year → $1.25/month
    "Zoho": 8.0,
    "The Odds API": 59.0,
    "Claude Code": 100.0,
    "FanGraphs": 15.0,
}
_FIXED_TOTAL: float = round(sum(_FIXED_LINE_ITEMS.values()), 2)

_SNOWFLAKE_CREDIT_PRICE: float = 2.0  # $/credit

# ACCOUNT_USAGE refreshes every ~3hrs; cache per Lambda instance to avoid charging
# Cloud Services compute on every page load. Resets on cold start (acceptable).
_sf_cost_cache: tuple[float, dict[str, float]] | None = None  # (expires_at, data)
_SF_CACHE_TTL = 6 * 3600  # 6 hours

# AWS Cost Explorer SERVICE-dimension names → P&L line-item labels. Matched by
# case-insensitive substring (CE service names vary: "EC2 - Other" vs "Amazon
# Elastic Compute Cloud - Compute"). Anything unmatched falls into "Other AWS".
# Order matters — first match wins.
_AWS_LINE_ITEMS: list[tuple[str, tuple[str, ...]]] = [
    ("EC2", ("elastic compute cloud", "ec2")),
    ("S3", ("simple storage service",)),
    ("Lambda", ("lambda",)),
    ("API Gateway", ("api gateway",)),
    ("DynamoDB", ("dynamodb",)),
    ("SES", ("simple email service", "ses")),
]
_AWS_OTHER = "Other AWS"
# Line items rolled into the AWS infra total (SES is kept as its own P&L line).
_AWS_INFRA_LABELS = ("EC2", "S3", "Lambda", "API Gateway", "DynamoDB", _AWS_OTHER)


# ── Response models ───────────────────────────────────────────────────────────

class MonthlyFinances(BaseModel):
    month: str               # "2026-06"
    month_label: str         # "Jun 2026"
    fixed_cost: float
    snowflake_cost: float | None
    aws_cost: float | None   # AWS infra total (EC2+S3+Lambda+API GW+DynamoDB+Other), ex-SES
    ses_cost: float | None
    total_cost: float
    betting_pl: float
    subscription_revenue: float
    net: float


class FinancesResponse(BaseModel):
    months: list[MonthlyFinances]
    fixed_breakdown: dict[str, float]
    aws_breakdown: dict[str, float]  # window totals per AWS line item (EC2, S3, …, SES, Other AWS)
    notes: list[str]


# ── Data fetchers ─────────────────────────────────────────────────────────────

def _classify_aws_service(service_name: str) -> str:
    """Map a Cost Explorer SERVICE name to a P&L line-item label."""
    s = service_name.lower()
    for label, needles in _AWS_LINE_ITEMS:
        if any(n in s for n in needles):
            return label
    return _AWS_OTHER


def _snowflake_costs_by_month() -> dict[str, float]:
    """Monthly Snowflake $ cost, applying the daily 10%-cloud-services billing rule.

    Cloud-services credits are billed only above 10% of the day's compute credits,
    so billed credits = SUM_day(compute + MAX(0, cloud_services − 0.10·compute)).
    The 10% rule is applied DAILY (a free day cannot offset a heavy day), then the
    daily billed credits are summed per month and priced at $/credit.
    """
    global _sf_cost_cache
    now = time.time()
    if _sf_cost_cache is not None and now < _sf_cost_cache[0]:
        return _sf_cost_cache[1]

    try:
        rows = execute_query("""
            WITH daily AS (
                SELECT
                    USAGE_DATE,
                    SUM(CREDITS_USED_COMPUTE)        AS compute_c,
                    SUM(CREDITS_USED_CLOUD_SERVICES) AS cloud_c
                FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_DAILY_HISTORY
                WHERE USAGE_DATE >= DATEADD('month', -6, CURRENT_DATE())
                GROUP BY USAGE_DATE
            )
            SELECT
                DATE_TRUNC('month', USAGE_DATE)                          AS month,
                SUM(compute_c + GREATEST(0, cloud_c - 0.10 * compute_c)) AS billed_credits
            FROM daily
            GROUP BY 1
            ORDER BY 1 DESC
        """)
    except Exception:
        logger.warning("Snowflake cost query failed — role may need IMPORTED PRIVILEGES on SNOWFLAKE db")
        return {}
    result: dict[str, float] = {}
    for row in rows:
        dt = row.get("MONTH")
        if dt is None:
            continue
        key = dt.strftime("%Y-%m") if hasattr(dt, "strftime") else str(dt)[:7]
        credits = float(row.get("BILLED_CREDITS") or 0)
        result[key] = round(credits * _SNOWFLAKE_CREDIT_PRICE, 2)

    _sf_cost_cache = (now + _SF_CACHE_TTL, result)
    return result


def _aws_costs_by_month() -> dict[str, dict[str, float]]:
    """AWS $ cost per month, grouped into P&L line items via Cost Explorer SERVICE.

    Returns {month_key: {line_item_label: cost}}. An empty dict signals the CE call
    failed (e.g. missing ce:GetCostAndUsage) so the caller can mark costs unavailable.
    """
    try:
        today = datetime.date.today()
        year, month = today.year, today.month - 5
        while month <= 0:
            month += 12
            year -= 1
        start = datetime.date(year, month, 1)
        end = today + datetime.timedelta(days=1)  # CE end is exclusive

        ce = boto3.client("ce", region_name="us-east-1")
        result: dict[str, dict[str, float]] = {}
        next_token: str | None = None
        while True:
            kwargs: dict = {
                "TimePeriod": {"Start": start.isoformat(), "End": end.isoformat()},
                "Granularity": "MONTHLY",
                "Metrics": ["UnblendedCost"],
                "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
            }
            if next_token:
                kwargs["NextPageToken"] = next_token
            resp = ce.get_cost_and_usage(**kwargs)
            for period in resp.get("ResultsByTime", []):
                key = period["TimePeriod"]["Start"][:7]
                bucket = result.setdefault(key, {})
                for grp in period.get("Groups", []):
                    label = _classify_aws_service(grp["Keys"][0])
                    amount = float(grp["Metrics"]["UnblendedCost"]["Amount"])
                    bucket[label] = round(bucket.get(label, 0.0) + amount, 2)
            next_token = resp.get("NextPageToken")
            if not next_token:
                break
        return result
    except Exception:
        logger.warning("AWS Cost Explorer query failed — add ce:GetCostAndUsage to Lambda IAM role")
        return {}


def _owner_user_id() -> str | None:
    if _OWNER_USER_ID_OVERRIDE:
        return _OWNER_USER_ID_OVERRIDE
    # Fallback: scan users table by email (requires dynamodb:Scan on Lambda role).
    # Prefer setting OWNER_USER_ID env var to avoid this.
    try:
        ddb = boto3.resource("dynamodb", region_name=_REGION)
        table = ddb.Table(_USERS_TABLE)
        resp = table.scan(
            FilterExpression=Attr("email").eq(_OWNER_EMAIL),
            ProjectionExpression="user_id",
        )
        items = resp.get("Items", [])
        if items:
            return str(items[0]["user_id"])
        logger.warning("Owner user ID not found via scan — is %s in the users table?", _OWNER_EMAIL)
        return None
    except Exception as exc:
        logger.warning("Users table scan for owner ID failed (add dynamodb:Scan or set OWNER_USER_ID): %s", exc)
        return None


def _betting_pl_by_month(user_id: str) -> dict[str, float]:
    """Sum settled profit_loss by score_date month for the owner."""
    try:
        ddb = boto3.resource("dynamodb", region_name=_REGION)
        table = ddb.Table(_USER_BETS_TABLE)
        items: list[dict] = []
        kwargs: dict = {"KeyConditionExpression": Key("user_id").eq(user_id)}
        while True:
            resp = table.query(**kwargs)
            items.extend(resp.get("Items", []))
            lek = resp.get("LastEvaluatedKey")
            if not lek:
                break
            kwargs["ExclusiveStartKey"] = lek

        result: dict[str, float] = {}
        for item in items:
            if item.get("outcome") is None:
                continue  # unsettled
            pl = item.get("profit_loss")
            if pl is None:
                continue
            date_str = str(item.get("score_date", ""))
            if len(date_str) < 7:
                continue
            key = date_str[:7]
            result[key] = round(result.get(key, 0.0) + float(pl), 2)
        return result
    except Exception:
        logger.warning("Betting P&L DynamoDB query failed")
        return {}


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/finances", response_model=FinancesResponse)
def get_finances(_: str = Depends(get_admin_user)) -> FinancesResponse:
    """6-month rolling infrastructure cost + betting P&L profitability view."""
    sf_costs = _snowflake_costs_by_month()
    aws_costs = _aws_costs_by_month()
    owner_id = _owner_user_id()
    pl_by_month = _betting_pl_by_month(owner_id) if owner_id else {}

    notes: list[str] = []
    if not sf_costs:
        notes.append("Snowflake costs unavailable — role needs IMPORTED PRIVILEGES on SNOWFLAKE database")
    if not aws_costs:
        notes.append("AWS costs unavailable — add ce:GetCostAndUsage to Lambda IAM role")

    today = datetime.date.today()
    current_month = datetime.date(today.year, today.month, 1)
    months: list[MonthlyFinances] = []
    aws_breakdown: dict[str, float] = {}  # window totals per line item
    month_date = _FINANCES_START
    while month_date <= current_month:
        key = month_date.strftime("%Y-%m")
        label = month_date.strftime("%b %Y")

        sf = sf_costs.get(key)
        aws_bucket = aws_costs.get(key)  # None if CE failed or no spend for this month
        if aws_bucket is not None:
            aws = round(sum(aws_bucket.get(lbl, 0.0) for lbl in _AWS_INFRA_LABELS), 2)
            ses = aws_bucket.get("SES")
            for lbl, amount in aws_bucket.items():
                aws_breakdown[lbl] = round(aws_breakdown.get(lbl, 0.0) + amount, 2)
        else:
            aws = None
            ses = None

        variable = (sf or 0.0) + (aws or 0.0) + (ses or 0.0)
        total = round(_FIXED_TOTAL + variable, 2)
        pl = pl_by_month.get(key, 0.0)
        subs = 0.0  # placeholder — wire when subscription billing is live
        net = round(pl + subs - total, 2)

        months.append(MonthlyFinances(
            month=key,
            month_label=label,
            fixed_cost=_FIXED_TOTAL,
            snowflake_cost=sf,
            aws_cost=aws,
            ses_cost=ses,
            total_cost=total,
            betting_pl=pl,
            subscription_revenue=subs,
            net=net,
        ))

        # Advance to next month
        if month_date.month == 12:
            month_date = datetime.date(month_date.year + 1, 1, 1)
        else:
            month_date = datetime.date(month_date.year, month_date.month + 1, 1)

    return FinancesResponse(
        months=months,
        fixed_breakdown=_FIXED_LINE_ITEMS,
        aws_breakdown=aws_breakdown,
        notes=notes,
    )
