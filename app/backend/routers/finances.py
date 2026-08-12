"""Admin finances endpoint — monthly infrastructure costs + betting P&L.

GET /admin/finances — 6-month rolling window of costs, P&L, and net profitability.

Variable cost sources:
  - Snowflake: ACCOUNT_USAGE.METERING_DAILY_HISTORY (requires IMPORTED PRIVILEGES).
               Cloud-services credits are billed only above 10% of the day's compute
               credits, applied DAILY (see _snowflake_costs_by_month).
  - AWS:       Cost Explorer ce:GetCostAndUsage grouped by SERVICE (requires the
               ce:GetCostAndUsage IAM permission on the Lambda role). Broken into
               line items: EC2, S3, Lambda, API Gateway, DynamoDB, SES, Other AWS.
  - Vercel:    GET /v1/billing/charges (FOCUS v1.3 JSONL) with a $20/mo Pro seat FLOOR
               from the upgrade month (see _vercel_costs_by_month / _vercel_cost_for_month).

Post-INC-16 (Railway cancelled, Dagster self-hosted on EC2) there is no separate
Railway/Dagster cost line — that spend now shows up inside the AWS EC2 line item.

Fixed costs and subscription revenue are hardcoded / placeholders updated in this file.

⚠️ RESPONSE SHAPE (E9.62, NF-C0/E9.41). This backend ships ONLY via
`infrastructure/lambda/deploy.sh` while `frontend/` auto-deploys on merge, so the two halves
are ALWAYS skewed in one direction or the other. Every field added here is therefore ADDITIVE:
`fixed_breakdown` (a flat dict) stays populated with the CURRENT month's view so an older
client keeps rendering, and the per-month truth arrives alongside it in
`fixed_breakdown_by_month`. Never remove or rename a field an already-deployed client reads.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from typing import NamedTuple

import boto3
from boto3.dynamodb.conditions import Attr, Key
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.backend.dependencies import get_admin_user
from app.backend.services.snowflake import MONITORING_WAREHOUSE, execute_query

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
#
# Each line item is a monthly `base` price plus optional per-month `overrides` keyed
# "YYYY-MM". An override REPLACES the base for that month — it is NOT added to it. That
# distinction is the whole point of the model: the Odds API plan was upgraded for Jul+Aug
# 2026, so those months cost $119 INSTEAD OF $59, not $178.
#
# ⛔ There is deliberately NO "Domain" line. The $15/yr registration is billed through AWS
# Route 53, so it already lands in the Cost Explorer "Other AWS" line item below; a fixed
# $1.25/mo entry here would DOUBLE-COUNT it (removed E9.62, operator-confirmed 2026-08-04).
_FIXED_LINE_ITEM_SPEC: dict[str, dict] = {
    "Zoho": {"base": 8.0},
    "The Odds API": {"base": 59.0, "overrides": {"2026-07": 119.0, "2026-08": 119.0}},
    "Claude Code": {"base": 100.0, "overrides": {"2026-07": 200.0, "2026-08": 200.0}},
    "FanGraphs": {"base": 15.0},
}

_SNOWFLAKE_CREDIT_PRICE: float = 2.0  # $/credit

# ── Vercel (variable, with a fixed seat floor) ────────────────────────────────
#
# ⭐ READ `EffectiveCost`, NOT `BilledCost` (E9.62b, measured against the live API 2026-08-12).
# FOCUS defines BilledCost as the amount that hits the INVOICE, so while consumption sits
# inside the plan's included allowance it is identically ZERO — every one of August's 17,304
# charge lines billed 0.00. That makes BilledCost a BINARY "have we crossed?" flag and
# structurally useless for "how close are we?". `EffectiveCost` is the amortized attributed
# cost and is what the Vercel usage dashboard shows. Measured on 2026-08:
#     Pro (the seat)   EffectiveCost 18.0645  = $20 × 28/31, prorated from the Aug-4 upgrade
#     everything else  EffectiveCost  3.8987  = the "$3.90" the usage page displayed
#     total                          21.9632
# So the two fields answer two different questions and we keep BOTH: EffectiveCost is the
# month's cost and the drawdown, BilledCost (ex-seat) is the overage alarm.
_VERCEL_PRO_START = "2026-08"     # first month the Pro seat was billed
_VERCEL_SEAT_FLOOR = 20.0         # $/month, charged regardless of usage
# Service names that are the PLAN/SEAT rather than metered consumption. Anything not listed
# here counts as usage — deliberately the safe direction: an unrecognised plan name inflates
# the visible drawdown rather than silently vanishing from it.
_VERCEL_PLAN_SERVICES = frozenset({"pro", "enterprise", "hobby", "additional team seats"})
_VERCEL_BILLING_URL = "https://api.vercel.com/v1/billing/charges"
# Operator-provisioned Vercel account/team token (see infrastructure/aws_resources.md).
# Absent → the seat floor still applies and a note explains that metered spend is missing.
_VERCEL_TOKEN_ENV = "VERCEL_API_TOKEN"
_VERCEL_TEAM_ID_ENV = "VERCEL_TEAM_ID"   # optional; omit for a personal account
# INC-32: a finite timeout is mandatory. An un-timed-out call on a request path burns the
# whole API Gateway window (29s cap) and returns an undiagnosable 502.
_VERCEL_TIMEOUT = 8.0
# The billing API caps a query at a 1-year range; never ask for more than this.
_VERCEL_MAX_RANGE_DAYS = 364

_vercel_cost_cache: tuple[float, dict[str, float]] | None = None  # (expires_at, data)
_VERCEL_CACHE_TTL = 6 * 3600  # billing data is daily-grained; 6h mirrors the SF cache

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
    fixed_cost: float        # varies by month — see _fixed_cost_for_month
    snowflake_cost: float | None
    aws_cost: float | None   # AWS infra total (EC2+S3+Lambda+API GW+DynamoDB+Other), ex-SES
    ses_cost: float | None
    # E9.62. Not Optional: unlike AWS/Snowflake there is always a defensible number — the
    # seat floor from the Pro-upgrade month, $0 (free Hobby plan) before it — so "we could
    # not reach the API" is carried by notes[], never by a null that reads as "$0 spent".
    vercel_cost: float
    # E9.62b — the floor used to hide its own input: "$20 measured" and "$20 because we had
    # nothing" rendered identically. These make it legible.
    vercel_floored: bool     # True → vercel_cost is the SEAT FLOOR, not a measurement
    vercel_usage: float      # allowance DRAWDOWN this month (EffectiveCost ex-seat)
    vercel_overage: float    # $0.00 until an included allowance is EXCEEDED (BilledCost ex-seat)
    total_cost: float
    betting_pl: float
    subscription_revenue: float
    net: float


class FinancesResponse(BaseModel):
    months: list[MonthlyFinances]
    # ⚠️ KEPT for an un-deployed client (NF-C0): the CURRENT month's per-item view. Fixed
    # costs are per-month as of E9.62, so this is one slice of fixed_breakdown_by_month —
    # populated, never removed, because the deployed admin page reads it.
    fixed_breakdown: dict[str, float]
    # The per-month truth: {"2026-07": {"Claude Code": 200.0, …}, …}. Any field absent from
    # this model is silently dropped on serialize (E9.41), so new fields go HERE, not just
    # in the writer.
    fixed_breakdown_by_month: dict[str, dict[str, float]]
    aws_breakdown: dict[str, float]  # window totals per AWS line item (EC2, S3, …, SES, Other AWS)
    # E9.62b — window totals per Vercel service, ex-seat, by EffectiveCost. This is what
    # answers "what is actually consuming the allowance" (measured 2026-08: Build CPU
    # Minutes $3.75 of a $3.90 drawdown — i.e. builds, not traffic).
    vercel_breakdown: dict[str, float]
    notes: list[str]


# ── Fixed costs, per month ────────────────────────────────────────────────────

def _fixed_breakdown_for_month(month_key: str) -> dict[str, float]:
    """Per-line-item fixed costs for one "YYYY-MM", applying that month's overrides.

    An override REPLACES the base price for the month (not additive) — the Odds API's
    Jul/Aug upgrade is $119 instead of $59, so summing base+override would be wrong.
    """
    return {
        name: float(spec.get("overrides", {}).get(month_key, spec["base"]))
        for name, spec in _FIXED_LINE_ITEM_SPEC.items()
    }


def _fixed_cost_for_month(month_key: str) -> float:
    """Total fixed cost for one "YYYY-MM"."""
    return round(sum(_fixed_breakdown_for_month(month_key).values()), 2)


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
        """, warehouse=MONITORING_WAREHOUSE)  # E11.24 — never resume the measured warehouse
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


class VercelMonth(NamedTuple):
    """One calendar month of Vercel charges, split so each number answers one question."""

    total: float                  # EffectiveCost, all services → the month's cost
    seat: float                   # EffectiveCost of the plan/seat lines (prorated by Vercel)
    usage: float                  # EffectiveCost ex-seat → the allowance DRAWDOWN
    overage: float                # BilledCost ex-seat → $0 until an allowance is EXCEEDED
    services: dict[str, float]    # EffectiveCost per service, ex-seat (what is driving usage)


def _vercel_costs_by_month() -> dict[str, VercelMonth]:
    """Vercel charges per month from the billing API.

    GET /v1/billing/charges returns FOCUS v1.3 records as newline-delimited JSON, one
    charge per line. Each carries `EffectiveCost` (amortized attributed cost — what the
    usage dashboard shows) and `BilledCost` (what reaches the invoice), both USD, plus a
    `ChargePeriodStart` and a `ServiceName`.

    Returns {} when the token is absent or the call fails; the caller then falls back to
    the seat floor and surfaces a note. This never raises — a billing-API outage must not
    take down the whole finances page (mirrors the Snowflake/Cost-Explorer fetchers).
    """
    global _vercel_cost_cache
    now = time.time()
    if _vercel_cost_cache is not None and now < _vercel_cost_cache[0]:
        return _vercel_cost_cache[1]

    token = os.getenv(_VERCEL_TOKEN_ENV)
    if not token:
        logger.warning("Vercel billing skipped — %s not set on the Lambda", _VERCEL_TOKEN_ENV)
        return {}

    try:
        today = datetime.date.today()
        # `to` is exclusive; clamp `from` so the window can never exceed the API's 1-year cap
        # as _FINANCES_START recedes into the past.
        start = max(_FINANCES_START, today - datetime.timedelta(days=_VERCEL_MAX_RANGE_DAYS))
        end = today + datetime.timedelta(days=1)
        params = {"from": f"{start.isoformat()}T00:00:00Z", "to": f"{end.isoformat()}T00:00:00Z"}
        team_id = os.getenv(_VERCEL_TEAM_ID_ENV)
        if team_id:
            params["teamId"] = team_id

        req = urllib.request.Request(  # nosec B310 — literal https URL, params are urlencoded
            f"{_VERCEL_BILLING_URL}?{urllib.parse.urlencode(params)}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/jsonl"},
        )
        with urllib.request.urlopen(req, timeout=_VERCEL_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")

        acc: dict[str, dict] = {}
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            period = str(record.get("ChargePeriodStart") or "")
            if len(period) < 7:
                continue
            key = period[:7]  # "2026-08-01T00:00:00Z" → "2026-08"
            bucket = acc.setdefault(
                key, {"total": 0.0, "seat": 0.0, "usage": 0.0, "overage": 0.0, "services": {}}
            )
            service = str(record.get("ServiceName") or "Unknown")
            effective = float(record.get("EffectiveCost") or 0.0)
            billed = float(record.get("BilledCost") or 0.0)

            bucket["total"] += effective
            if service.strip().lower() in _VERCEL_PLAN_SERVICES:
                bucket["seat"] += effective
            else:
                bucket["usage"] += effective
                bucket["overage"] += billed
                bucket["services"][service] = bucket["services"].get(service, 0.0) + effective

        result = {
            key: VercelMonth(
                total=round(b["total"], 2),
                seat=round(b["seat"], 2),
                usage=round(b["usage"], 2),
                # The API returns float noise around zero (measured 3.9e-10 on a month with
                # no overage at all); rounding to cents is what makes "$0.00" mean "nothing
                # exceeded" instead of a number that merely looks tiny.
                overage=round(b["overage"], 2),
                services={s: round(v, 2) for s, v in b["services"].items() if round(v, 2) > 0},
            )
            for key, b in acc.items()
        }
        _vercel_cost_cache = (now + _VERCEL_CACHE_TTL, result)
        return result
    except Exception:
        logger.warning("Vercel billing query failed — check %s validity/scope", _VERCEL_TOKEN_ENV)
        return {}


def _vercel_cost_for_month(month_key: str, metered: dict[str, VercelMonth]) -> tuple[float, bool]:
    """Monthly Vercel cost, and whether the seat FLOOR had to supply it.

    Returns (cost, floored). The $20 seat is charged whether or not the site gets traffic,
    so a month on Pro can never cost less than that — reporting a missing reading verbatim
    would under-state the bill. Months before the upgrade were on the free Hobby plan.

    ⭐ The floor is now a SAFETY NET, not the usual answer: `EffectiveCost` already contains
    the seat (Vercel prorates it), so a healthy reading lands above $20 on its own and
    `floored` is False. `floored=True` means the reading was short — a partial month, or a
    reading we could not get — and the caller MUST say so rather than pass off a synthetic
    $20 as a measurement (the previous cut showed exactly that, indistinguishable).
    """
    # "YYYY-MM" strings are zero-padded, so lexicographic order IS chronological order.
    month = metered.get(month_key)
    amount = month.total if month is not None else 0.0
    if month_key >= _VERCEL_PRO_START and amount < _VERCEL_SEAT_FLOOR:
        return _VERCEL_SEAT_FLOOR, True
    return round(amount, 2), False


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
    vercel_metered = _vercel_costs_by_month()
    owner_id = _owner_user_id()
    pl_by_month = _betting_pl_by_month(owner_id) if owner_id else {}

    notes: list[str] = []
    if not sf_costs:
        notes.append("Snowflake costs unavailable — role needs IMPORTED PRIVILEGES on SNOWFLAKE database")
    if not aws_costs:
        notes.append("AWS costs unavailable — add ce:GetCostAndUsage to Lambda IAM role")
    if not vercel_metered:
        notes.append(
            f"Vercel metered spend unavailable ({_VERCEL_TOKEN_ENV} missing or the billing API "
            f"call failed) — showing the ${_VERCEL_SEAT_FLOOR:.0f}/mo Pro seat floor from "
            f"{_VERCEL_PRO_START}; any usage above the included credit is not counted"
        )

    today = datetime.date.today()
    current_month = datetime.date(today.year, today.month, 1)
    current_key = current_month.strftime("%Y-%m")
    this_month = vercel_metered.get(current_key)
    if this_month is not None and this_month.overage > 0:
        # BilledCost only leaves zero once an included allowance is EXCEEDED, so any
        # non-zero here is the crossing itself — name the services so it is actionable.
        worst = sorted(this_month.services.items(), key=lambda kv: -kv[1])[:3]
        notes.append(
            f"Vercel usage EXCEEDED the plan allowance this month — ${this_month.overage:.2f} "
            f"billed above it. Largest consumers: "
            + ", ".join(f"{s} ${v:.2f}" for s, v in worst)
        )
    months: list[MonthlyFinances] = []
    aws_breakdown: dict[str, float] = {}  # window totals per line item
    vercel_breakdown: dict[str, float] = {}  # window totals per Vercel service, ex-seat
    fixed_breakdown_by_month: dict[str, dict[str, float]] = {}
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

        vercel, vercel_floored = _vercel_cost_for_month(key, vercel_metered)
        vm = vercel_metered.get(key)
        for svc, amount in (vm.services if vm else {}).items():
            vercel_breakdown[svc] = round(vercel_breakdown.get(svc, 0.0) + amount, 2)
        fixed_breakdown_by_month[key] = _fixed_breakdown_for_month(key)
        fixed = _fixed_cost_for_month(key)

        variable = (sf or 0.0) + (aws or 0.0) + (ses or 0.0) + vercel
        total = round(fixed + variable, 2)
        pl = pl_by_month.get(key, 0.0)
        subs = 0.0  # placeholder — wire when subscription billing is live
        net = round(pl + subs - total, 2)

        months.append(MonthlyFinances(
            month=key,
            month_label=label,
            fixed_cost=fixed,
            snowflake_cost=sf,
            aws_cost=aws,
            ses_cost=ses,
            vercel_cost=vercel,
            vercel_floored=vercel_floored,
            vercel_usage=vm.usage if vm else 0.0,
            vercel_overage=vm.overage if vm else 0.0,
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

    # NF-C0: `fixed_breakdown` is the CURRENT month's slice, kept populated so an admin page
    # deployed before this change still renders a sensible panel instead of blanking.
    return FinancesResponse(
        months=months,
        fixed_breakdown=fixed_breakdown_by_month.get(
            current_key, _fixed_breakdown_for_month(current_key)
        ),
        fixed_breakdown_by_month=fixed_breakdown_by_month,
        aws_breakdown=aws_breakdown,
        vercel_breakdown=vercel_breakdown,
        notes=notes,
    )
