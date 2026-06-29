"""E9.39 — unit tests for the Admin dashboard sweep.

Covers the three pieces touched by E9.39 without hitting real infrastructure:
  1. Dagster repoint — admin._dagster_headers honours the EC2 endpoint/auth precedence
     (mirrors scripts/ops/dagster_runs.py) and no longer hard-requires the Cloud token.
  2. Snowflake credit calc — both the admin and finances queries apply the DAILY
     10%-cloud-services billing rule (GREATEST(0, cloud − 0.10·compute), grouped per day).
  3. Monthly P&L — AWS Cost Explorer SERVICE costs are classified into line items and
     get_finances splits SES out from the AWS infra total; Railway/Dagster are gone.
"""
from __future__ import annotations

from unittest.mock import patch

import app.backend.routers.admin as admin
import app.backend.routers.finances as fin


# ---------------------------------------------------------------------------
# 1. Dagster repoint → EC2 dagit
# ---------------------------------------------------------------------------

class TestDagsterRepoint:
    def test_default_endpoint_is_ec2_dagit(self):
        # Default (no env) points at the self-hosted EC2 dagit, not Dagster+ Cloud.
        assert "dagster.credencesports.com" in admin._DAGSTER_ENDPOINT
        assert "dagster.plus" not in admin._DAGSTER_ENDPOINT

    def test_basic_auth_header_when_caddy_creds_set(self):
        with patch.dict(
            "os.environ",
            {"DAGIT_BASIC_AUTH_USER": "ops", "DAGIT_BASIC_AUTH_PASSWORD": "secret"},
            clear=False,
        ):
            h = admin._dagster_headers()
        # Basic auth, base64("ops:secret"), and never the plaintext password.
        assert h["Authorization"].startswith("Basic ")
        assert "secret" not in h["Authorization"]
        assert h["Content-Type"] == "application/json"

    def test_cloud_token_only_used_for_dagster_plus_url(self):
        # EC2 URL + a stray Cloud token → token is ignored (basic-auth path or none).
        with patch.dict("os.environ", {"DAGSTER_CLOUD_API_TOKEN": "tok"}, clear=False):
            with patch.object(admin, "_DAGSTER_ENDPOINT", "https://dagster.credencesports.com/graphql"):
                h = admin._dagster_headers()
            assert "Dagster-Cloud-Api-Token" not in h
            with patch.object(admin, "_DAGSTER_ENDPOINT", "https://x.dagster.plus/prod/graphql"):
                h2 = admin._dagster_headers()
            assert h2["Dagster-Cloud-Api-Token"] == "tok"

    def test_pipeline_runs_no_longer_requires_cloud_token(self):
        # With no Cloud token but a reachable endpoint (mocked), it must not 503.
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("DAGSTER_CLOUD_API_TOKEN", None)
            with patch.object(admin, "_dagster_runs_for_job", return_value=[]):
                result = admin.pipeline_runs(_="admin")
        assert result == []


# ---------------------------------------------------------------------------
# 2. Snowflake credit calc — daily 10% cloud-services rule
# ---------------------------------------------------------------------------

class TestSnowflakeBillingRule:
    def _assert_daily_rule_sql(self, captured_sql: str) -> None:
        s = " ".join(captured_sql.split())  # collapse whitespace
        assert "GREATEST(0, cloud_c - 0.10 * compute_c)" in s  # only bill cloud-svc excess
        assert "GROUP BY USAGE_DATE" in s  # adjustment applied per-day, not period total

    def test_admin_snowflake_credits_query_applies_daily_rule(self):
        captured = {}

        def fake_execute(sql):
            captured["sql"] = sql
            return [{"MONTH": "2026-06-01", "COMPUTE_CREDITS": 177.18,
                     "CLOUD_SERVICE_CREDITS": 24.52, "BILLED_CREDITS": 184.28}]

        with patch.object(admin, "execute_query", side_effect=fake_execute):
            rows = admin.snowflake_credits(_="admin")
        self._assert_daily_rule_sql(captured["sql"])
        assert rows[0].billed_credits == 184.28
        # Billed is below the naive raw sum (compute + cloud = 201.70) — the fix.
        assert rows[0].billed_credits < rows[0].compute_credits + rows[0].cloud_service_credits

    def test_finances_snowflake_query_applies_daily_rule_and_prices(self):
        captured = {}
        fin._sf_cost_cache = None  # bypass per-instance cache

        def fake_execute(sql):
            captured["sql"] = sql
            return [{"MONTH": "2026-06-01", "BILLED_CREDITS": 184.28}]

        with patch.object(fin, "execute_query", side_effect=fake_execute):
            costs = fin._snowflake_costs_by_month()
        self._assert_daily_rule_sql(captured["sql"])
        # Priced at $2/credit.
        assert costs["2026-06"] == round(184.28 * 2.0, 2)
        fin._sf_cost_cache = None


# ---------------------------------------------------------------------------
# 3. AWS Cost Explorer line items + SES split
# ---------------------------------------------------------------------------

class TestAwsClassifier:
    def test_known_services_map_to_line_items(self):
        assert fin._classify_aws_service("Amazon Elastic Compute Cloud - Compute") == "EC2"
        assert fin._classify_aws_service("EC2 - Other") == "EC2"
        assert fin._classify_aws_service("Amazon Simple Storage Service") == "S3"
        assert fin._classify_aws_service("AWS Lambda") == "Lambda"
        assert fin._classify_aws_service("Amazon API Gateway") == "API Gateway"
        assert fin._classify_aws_service("Amazon DynamoDB") == "DynamoDB"
        assert fin._classify_aws_service("Amazon Simple Email Service") == "SES"

    def test_unknown_service_falls_into_other(self):
        assert fin._classify_aws_service("Amazon CloudFront") == "Other AWS"
        assert fin._classify_aws_service("AWS Secrets Manager") == "Other AWS"


class TestGetFinances:
    def test_aws_infra_total_excludes_ses_and_breakdown_accumulates(self):
        month = fin._FINANCES_START.strftime("%Y-%m")
        aws = {month: {"EC2": 10.0, "S3": 2.0, "SES": 1.5, "Other AWS": 0.5}}

        with patch.object(fin, "_snowflake_costs_by_month", return_value={month: 20.0}), \
             patch.object(fin, "_aws_costs_by_month", return_value=aws), \
             patch.object(fin, "_owner_user_id", return_value=None), \
             patch.object(fin, "_betting_pl_by_month", return_value={}):
            resp = fin.get_finances(_="admin")

        row = next(m for m in resp.months if m.month == month)
        # AWS infra total = EC2+S3+Other (ex-SES); SES is its own line.
        assert row.aws_cost == 12.5
        assert row.ses_cost == 1.5
        # total = fixed + snowflake + aws_infra + ses
        assert row.total_cost == round(fin._FIXED_TOTAL + 20.0 + 12.5 + 1.5, 2)
        # No Railway/Dagster fields on the model anymore.
        assert not hasattr(row, "railway_cost")
        assert not hasattr(row, "dagster_cost")
        # Breakdown surfaces every line item including SES.
        assert resp.aws_breakdown["EC2"] == 10.0
        assert resp.aws_breakdown["SES"] == 1.5

    def test_costs_unavailable_marked_none_with_note(self):
        with patch.object(fin, "_snowflake_costs_by_month", return_value={}), \
             patch.object(fin, "_aws_costs_by_month", return_value={}), \
             patch.object(fin, "_owner_user_id", return_value=None), \
             patch.object(fin, "_betting_pl_by_month", return_value={}):
            resp = fin.get_finances(_="admin")
        assert all(m.aws_cost is None and m.ses_cost is None for m in resp.months)
        assert any("Cost Explorer" in n or "ce:GetCostAndUsage" in n for n in resp.notes)
