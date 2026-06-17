"""Admin finances endpoint — monthly infrastructure costs + betting P&L.

GET /admin/finances — 6-month rolling window of costs, P&L, and net profitability.

Variable cost sources:
  - Snowflake: ACCOUNT_USAGE.METERING_DAILY_HISTORY (requires IMPORTED PRIVILEGES)
  - AWS:       Cost Explorer ce:GetCostAndUsage (requires IAM permission on Lambda role)
  - Railway:   RAILWAY_MONTHLY_ESTIMATE env var (manual — no public billing API)
  - Dagster+:  DAGSTER_MONTHLY_ESTIMATE env var (manual — $0.04/credit, check dashboard)

Fixed costs and subscription revenue are hardcoded / placeholders updated in this file.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import time

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException
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

# S3 key for admin-editable cost estimates (outside api-cache/ prefix, never invalidated)
_FINANCES_CONFIG_S3_KEY = "admin-settings/finances-config.json"
_FINANCES_CONFIG_DEFAULTS: dict[str, float] = {
    "railway_monthly_estimate": 0.0,
    "dagster_monthly_estimate": 50.0,  # sensible default until set explicitly
}


# ── Response models ───────────────────────────────────────────────────────────

class MonthlyFinances(BaseModel):
    month: str               # "2026-06"
    month_label: str         # "Jun 2026"
    fixed_cost: float
    snowflake_cost: float | None
    aws_cost: float | None
    railway_cost: float | None
    dagster_cost: float | None
    total_cost: float
    betting_pl: float
    subscription_revenue: float
    net: float


class FinancesResponse(BaseModel):
    months: list[MonthlyFinances]
    fixed_breakdown: dict[str, float]
    notes: list[str]


class FinancesConfig(BaseModel):
    railway_monthly_estimate: float = 0.0
    dagster_monthly_estimate: float = 50.0


# ── S3 config helpers ─────────────────────────────────────────────────────────

def _load_finances_config() -> FinancesConfig:
    bucket = os.getenv("CACHE_BUCKET")
    if not bucket:
        return FinancesConfig(**_FINANCES_CONFIG_DEFAULTS)
    try:
        s3 = boto3.client("s3", region_name=_REGION)
        resp = s3.get_object(Bucket=bucket, Key=_FINANCES_CONFIG_S3_KEY)
        data = json.loads(resp["Body"].read().decode())
        return FinancesConfig(**{**_FINANCES_CONFIG_DEFAULTS, **data})
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchKey":
            logger.warning("Could not load finances config from S3: %s", exc)
        return FinancesConfig(**_FINANCES_CONFIG_DEFAULTS)
    except Exception as exc:
        logger.warning("Could not load finances config from S3 — using defaults: %s", exc)
        return FinancesConfig(**_FINANCES_CONFIG_DEFAULTS)


def _save_finances_config(config: FinancesConfig) -> None:
    bucket = os.getenv("CACHE_BUCKET")
    if not bucket:
        raise HTTPException(status_code=500, detail="CACHE_BUCKET not configured")
    try:
        s3 = boto3.client("s3", region_name=_REGION)
        s3.put_object(
            Bucket=bucket,
            Key=_FINANCES_CONFIG_S3_KEY,
            Body=json.dumps(config.model_dump()),
            ContentType="application/json",
        )
    except Exception as exc:
        logger.error("Failed to save finances config: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save config") from exc


# ── Data fetchers ─────────────────────────────────────────────────────────────

def _snowflake_costs_by_month() -> dict[str, float]:
    global _sf_cost_cache
    now = time.time()
    if _sf_cost_cache is not None and now < _sf_cost_cache[0]:
        return _sf_cost_cache[1]

    try:
        rows = execute_query("""
            SELECT
                DATE_TRUNC('month', USAGE_DATE)                     AS month,
                SUM(CREDITS_USED_COMPUTE + CREDITS_USED_CLOUD_SERVICES) AS total_credits
            FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_DAILY_HISTORY
            WHERE USAGE_DATE >= DATEADD('month', -6, CURRENT_DATE())
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
        credits = float(row.get("TOTAL_CREDITS") or 0)
        result[key] = round(credits * _SNOWFLAKE_CREDIT_PRICE, 2)

    _sf_cost_cache = (now + _SF_CACHE_TTL, result)
    return result


def _aws_costs_by_month() -> dict[str, float]:
    try:
        today = datetime.date.today()
        year, month = today.year, today.month - 5
        while month <= 0:
            month += 12
            year -= 1
        start = datetime.date(year, month, 1)
        end = today + datetime.timedelta(days=1)  # CE end is exclusive

        ce = boto3.client("ce", region_name="us-east-1")
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
        )
        result: dict[str, float] = {}
        for period in resp.get("ResultsByTime", []):
            key = period["TimePeriod"]["Start"][:7]
            amount = float(period["Total"]["UnblendedCost"]["Amount"])
            result[key] = round(amount, 2)
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

@router.get("/finances-config", response_model=FinancesConfig)
def get_finances_config(_: str = Depends(get_admin_user)) -> FinancesConfig:
    """Read editable cost estimates (Railway, Dagster+)."""
    return _load_finances_config()


@router.patch("/finances-config", response_model=FinancesConfig)
def update_finances_config(body: FinancesConfig, _: str = Depends(get_admin_user)) -> FinancesConfig:
    """Persist updated cost estimates to S3."""
    _save_finances_config(body)
    return body


@router.get("/finances", response_model=FinancesResponse)
def get_finances(_: str = Depends(get_admin_user)) -> FinancesResponse:
    """6-month rolling infrastructure cost + betting P&L profitability view."""
    sf_costs = _snowflake_costs_by_month()
    aws_costs = _aws_costs_by_month()
    owner_id = _owner_user_id()
    pl_by_month = _betting_pl_by_month(owner_id) if owner_id else {}

    cfg = _load_finances_config()
    railway_est = cfg.railway_monthly_estimate
    dagster_est = cfg.dagster_monthly_estimate

    notes: list[str] = []
    if not sf_costs:
        notes.append("Snowflake costs unavailable — role needs IMPORTED PRIVILEGES on SNOWFLAKE database")
    if not aws_costs:
        notes.append("AWS costs unavailable — add ce:GetCostAndUsage to Lambda IAM role")
    if railway_est == 0:
        notes.append("Railway estimate not set — edit estimates above to include Railway costs")
    if dagster_est == 0:
        notes.append("Dagster+ estimate not set — edit estimates above ($0.04/credit)")

    today = datetime.date.today()
    current_month = datetime.date(today.year, today.month, 1)
    months: list[MonthlyFinances] = []
    month_date = _FINANCES_START
    while month_date <= current_month:
        key = month_date.strftime("%Y-%m")
        label = month_date.strftime("%b %Y")

        sf = sf_costs.get(key)
        aws = aws_costs.get(key)
        ry = railway_est if railway_est > 0 else None
        da = dagster_est if dagster_est > 0 else None

        variable = (sf or 0.0) + (aws or 0.0) + (ry or 0.0) + (da or 0.0)
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
            railway_cost=ry,
            dagster_cost=da,
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
        notes=notes,
    )
