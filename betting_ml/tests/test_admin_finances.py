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

import os
import urllib.parse
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

    def test_pipeline_runs_uses_queried_job_name(self):
        # OSS dagit returns no `dagster/job_name` tag → fall back to the job we queried.
        def fake_runs(job, limit=8):
            return [{"runId": f"r-{job}", "status": "SUCCESS",
                     "startTime": 1.0, "endTime": 2.0, "tags": [],
                     "_queried_job": job}]
        with patch.object(admin, "_dagster_runs_for_job", side_effect=fake_runs):
            runs = admin.pipeline_runs(_="admin")
        jobs = {r.job_name for r in runs}
        assert "daily_ingestion_job" in jobs
        assert "lineup_monitor_job" in jobs
        assert "—" not in jobs


# ---------------------------------------------------------------------------
# 4. Model freshness — live served version vs stale registry ledger
# ---------------------------------------------------------------------------

class TestLiveServedVersion:
    def test_normalizes_tiers_and_picks_highest(self):
        rows = [{"MODEL_VERSION": "pre_lineup_v6"}, {"MODEL_VERSION": "v6"},
                {"MODEL_VERSION": "v5"}, {"MODEL_VERSION": "pre_lineup_v1"}]
        with patch.object(admin, "execute_query", return_value=rows):
            assert admin._live_served_versions()["default"] == "v6"

    def test_returns_none_on_query_failure(self):
        with patch.object(admin, "execute_query", side_effect=Exception("no table")):
            assert admin._live_served_versions()["default"] is None

    def test_model_freshness_shows_served_version_and_flags_stale_ledger(self):
        registry_rows = [{"TARGET": "home_win", "MODEL_NAME": "xgb_classifier_market_blind",
                          "MODEL_VERSION": "v5", "PROMOTED_DATE": "2026-06-12", "DAYS_SINCE": 17}]
        with patch.object(admin, "execute_query", return_value=registry_rows), \
             patch.object(admin, "_live_served_versions",
                          return_value={"default": "v6", "total_runs": None}):
            out = admin.model_freshness(_="admin")
        row = out[0]
        assert row.version == "v6"            # what's actually serving
        assert row.registry_version == "v5"   # what the ledger records
        assert row.ledger_behind is True
        assert row.status == "watch"          # mismatch surfaced, not silently "healthy"

    def test_model_freshness_no_flag_when_in_sync(self):
        registry_rows = [{"TARGET": "home_win", "MODEL_NAME": "m",
                          "MODEL_VERSION": "v6", "PROMOTED_DATE": "2026-06-20", "DAYS_SINCE": 9}]
        with patch.object(admin, "execute_query", return_value=registry_rows), \
             patch.object(admin, "_live_served_versions",
                          return_value={"default": "v6", "total_runs": None}):
            out = admin.model_freshness(_="admin")
        assert out[0].ledger_behind is False
        assert out[0].status == "healthy"


# ---------------------------------------------------------------------------
# 5. Pipeline status — opt-in fallback_latest (admin) leaves dashboard untouched
# ---------------------------------------------------------------------------

class TestPipelineStatusFallback:
    def test_fallback_queries_latest_only_when_today_missing(self):
        import app.backend.routers.pipeline as pipe
        calls = []

        def fake_execute(sql):
            calls.append(sql)
            if "CURRENT_DATE" in sql:
                return []  # no row for today
            return [{"RUN_DATE": "2026-06-28", "PIPELINE_STATUS": "complete",
                     "N_GAMES_SCORED": 15, "N_QUALIFIED_BETS": 37,
                     "LINEUP_CONFIRMED_COMPLETE_TS": None,
                     "PREDICT_TODAY_COMPLETE_TS": "2026-06-28T13:08:42"}]

        with patch.object(pipe, "execute_query", side_effect=fake_execute):
            status = pipe.get_pipeline_status(fallback_latest=True)
        # Two queries: today (empty) then the latest fallback.
        assert len(calls) == 2 and "ORDER BY run_date DESC" in calls[1]
        assert status.n_games_scored == 15

    def test_dashboard_default_does_not_fall_back(self):
        import app.backend.routers.pipeline as pipe
        calls = []

        def fake_execute(sql):
            calls.append(sql)
            return []  # nothing for today

        with patch.object(pipe, "execute_query", side_effect=fake_execute):
            status = pipe.get_pipeline_status()  # default fallback_latest=False
        # Only the today query runs — no fallback for the public dot.
        assert len(calls) == 1
        assert status.indicator == "red"


# ---------------------------------------------------------------------------
# 2. Snowflake credit calc — daily 10% cloud-services rule
# ---------------------------------------------------------------------------

class TestSnowflakeBillingRule:
    def _assert_daily_rule_sql(self, captured_sql: str) -> None:
        s = " ".join(captured_sql.split())  # collapse whitespace
        assert "GREATEST(0, cloud_c - 0.10 * compute_c)" in s  # only bill cloud-svc excess
        assert "GROUP BY USAGE_DATE" in s  # adjustment applied per-day, not period total

    @staticmethod
    def _assert_runs_on_the_monitoring_warehouse(warehouse):
        """E11.24 — a cost panel must never run on the warehouse it is reporting on.

        Measured 2026-07-29: today these queries wake NOTHING (0 of 636 resumes over 8 days had
        one first-after-resume) because the warehouse is always already awake for pipeline work.
        That is exactly why this guard exists: once the literal-zero cutovers land and the
        warehouse genuinely sleeps, opening the admin cost page BECOMES the resume — the page
        that displays the Snowflake bill would start billing for the privilege.
        """
        from app.backend.services.snowflake import MONITORING_WAREHOUSE

        assert warehouse == MONITORING_WAREHOUSE, (
            f"the cost query ran on {warehouse!r} instead of the monitoring warehouse "
            f"{MONITORING_WAREHOUSE!r} — see docs/e11_24_literal_zero_snowflake.md"
        )

    def test_admin_snowflake_credits_query_applies_daily_rule(self):
        captured = {}

        def fake_execute(sql, warehouse=None):
            captured["sql"] = sql
            captured["warehouse"] = warehouse
            return [{"MONTH": "2026-06-01", "COMPUTE_CREDITS": 177.18,
                     "CLOUD_SERVICE_CREDITS": 24.52, "BILLED_CREDITS": 184.28}]

        with patch.object(admin, "execute_query", side_effect=fake_execute):
            rows = admin.snowflake_credits(_="admin")
        self._assert_daily_rule_sql(captured["sql"])
        self._assert_runs_on_the_monitoring_warehouse(captured["warehouse"])
        assert rows[0].billed_credits == 184.28
        # Billed is below the naive raw sum (compute + cloud = 201.70) — the fix.
        assert rows[0].billed_credits < rows[0].compute_credits + rows[0].cloud_service_credits

    def test_finances_snowflake_query_applies_daily_rule_and_prices(self):
        captured = {}
        fin._sf_cost_cache = None  # bypass per-instance cache

        def fake_execute(sql, warehouse=None):
            captured["sql"] = sql
            captured["warehouse"] = warehouse
            return [{"MONTH": "2026-06-01", "BILLED_CREDITS": 184.28}]

        with patch.object(fin, "execute_query", side_effect=fake_execute):
            costs = fin._snowflake_costs_by_month()
        self._assert_daily_rule_sql(captured["sql"])
        self._assert_runs_on_the_monitoring_warehouse(captured["warehouse"])
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
             patch.object(fin, "_vercel_costs_by_month", return_value={}), \
             patch.object(fin, "_owner_user_id", return_value=None), \
             patch.object(fin, "_betting_pl_by_month", return_value={}):
            resp = fin.get_finances(_="admin")

        row = next(m for m in resp.months if m.month == month)
        # AWS infra total = EC2+S3+Other (ex-SES); SES is its own line.
        assert row.aws_cost == 12.5
        assert row.ses_cost == 1.5
        # total = fixed(this month) + snowflake + aws_infra + ses + vercel
        expected_vercel = fin._vercel_cost_for_month(month, {})
        assert row.total_cost == round(
            fin._fixed_cost_for_month(month) + 20.0 + 12.5 + 1.5 + expected_vercel, 2
        )
        # No Railway/Dagster fields on the model anymore.
        assert not hasattr(row, "railway_cost")
        assert not hasattr(row, "dagster_cost")
        # Breakdown surfaces every line item including SES.
        assert resp.aws_breakdown["EC2"] == 10.0
        assert resp.aws_breakdown["SES"] == 1.5

    def test_costs_unavailable_marked_none_with_note(self):
        with patch.object(fin, "_snowflake_costs_by_month", return_value={}), \
             patch.object(fin, "_aws_costs_by_month", return_value={}), \
             patch.object(fin, "_vercel_costs_by_month", return_value={}), \
             patch.object(fin, "_owner_user_id", return_value=None), \
             patch.object(fin, "_betting_pl_by_month", return_value={}):
            resp = fin.get_finances(_="admin")
        assert all(m.aws_cost is None and m.ses_cost is None for m in resp.months)
        assert any("Cost Explorer" in n or "ce:GetCostAndUsage" in n for n in resp.notes)


# ---------------------------------------------------------------------------
# E9.62 — per-month fixed costs, Vercel as a variable source, additive response
# ---------------------------------------------------------------------------

def _finances_response(**overrides):
    """Call get_finances with every external fetcher stubbed.

    `_vercel_costs_by_month` is ALWAYS stubbed: unstubbed it reads VERCEL_API_TOKEN from the
    ambient environment and would attempt a real billing-API call on a developer laptop that
    happens to have the token exported.
    """
    stubs = {
        "_snowflake_costs_by_month": {},
        "_aws_costs_by_month": {},
        "_vercel_costs_by_month": {},
        "_owner_user_id": None,
        "_betting_pl_by_month": {},
    }
    stubs.update(overrides)
    from contextlib import ExitStack
    with ExitStack() as stack:
        for name, value in stubs.items():
            stack.enter_context(patch.object(fin, name, return_value=value))
        return fin.get_finances(_="admin")


class TestPerMonthFixedCosts:
    """Part A — a fixed cost that applies to SOME months, not every month."""

    def test_july_and_august_carry_the_upgraded_prices(self):
        for month in ("2026-07", "2026-08"):
            items = fin._fixed_breakdown_for_month(month)
            assert items["Claude Code"] == 200.0, month
            assert items["The Odds API"] == 119.0, month

    def test_a_month_outside_the_override_window_gets_the_base_price(self):
        # The whole point of the refactor: the same key must NOT return the same value for
        # every month. A flat dict passes every other assertion here but fails this one.
        for month in ("2026-06", "2026-09", "2027-01"):
            items = fin._fixed_breakdown_for_month(month)
            assert items["Claude Code"] == 100.0, month
            assert items["The Odds API"] == 59.0, month

    def test_july_total_differs_from_september_total(self):
        july, september = fin._fixed_cost_for_month("2026-07"), fin._fixed_cost_for_month("2026-09")
        assert july != september
        # 8 + 119 + 200 + 15  vs  8 + 59 + 100 + 15
        assert (july, september) == (342.0, 182.0)

    def test_an_override_replaces_the_base_rather_than_adding_to_it(self):
        # $119 REPLACING $59 — not $178. Guards the one arithmetic mistake this model invites.
        july = fin._fixed_breakdown_for_month("2026-07")
        assert july["The Odds API"] == 119.0
        assert july["The Odds API"] != 59.0 + 119.0
        assert july["Claude Code"] != 100.0 + 200.0

    def test_unchanged_items_are_identical_in_every_month(self):
        for month in ("2026-05", "2026-07", "2026-08", "2026-12"):
            items = fin._fixed_breakdown_for_month(month)
            assert items["Zoho"] == 8.0, month
            assert items["FanGraphs"] == 15.0, month

    def test_domain_is_gone_from_every_month(self):
        # Double-counted: the $15/yr registration is billed via Route 53 and already lands in
        # the Cost Explorer "Other AWS" line.
        assert "Domain" not in fin._FIXED_LINE_ITEM_SPEC
        for month in ("2026-05", "2026-07", "2026-08", "2026-09"):
            assert "Domain" not in fin._fixed_breakdown_for_month(month), month

    def test_no_fixed_month_still_carries_the_old_flat_total(self):
        # The pre-E9.62 constant was $183.25 (incl. the double-counted $1.25 Domain line).
        # No month may reproduce it — that value can only come from the removed line.
        for month in ("2026-05", "2026-06", "2026-07", "2026-08", "2026-09"):
            assert fin._fixed_cost_for_month(month) != 183.25, month

    def test_the_served_months_vary_their_fixed_cost(self):
        # End-to-end through the endpoint, not just the helper: the per-month value must reach
        # MonthlyFinances.fixed_cost (it was a single module constant before).
        resp = _finances_response()
        by_month = {m.month: m.fixed_cost for m in resp.months}
        assert by_month.get("2026-07") == 342.0
        assert by_month.get("2026-05") == 182.0
        assert by_month["2026-07"] != by_month["2026-05"]


class TestAdditiveResponseShape:
    """NF-C0/E9.41 — the API Lambda ships separately, so nothing may be removed."""

    def test_flat_fixed_breakdown_is_still_populated_for_an_undeployed_client(self):
        # The deployed admin page reads `fixed_breakdown`; emptying it blanks that panel.
        resp = _finances_response()
        assert resp.fixed_breakdown, "fixed_breakdown must stay populated (NF-C0)"
        assert "Claude Code" in resp.fixed_breakdown

    def test_flat_fixed_breakdown_is_the_current_month_slice(self):
        import datetime
        current = datetime.date.today().strftime("%Y-%m")
        resp = _finances_response()
        assert resp.fixed_breakdown == fin._fixed_breakdown_for_month(current)

    def test_per_month_breakdown_covers_every_served_month(self):
        resp = _finances_response()
        assert set(resp.fixed_breakdown_by_month) == {m.month for m in resp.months}
        assert resp.fixed_breakdown_by_month["2026-07"]["Claude Code"] == 200.0

    def test_new_fields_are_declared_on_the_pydantic_models(self):
        # E9.41: a field absent from the response model is silently DROPPED on serialize —
        # the store/writer being right is not enough. Assert on the SERIALIZED payload.
        resp = _finances_response()
        payload = resp.model_dump()
        assert "fixed_breakdown_by_month" in payload
        assert "fixed_breakdown" in payload
        assert "vercel_cost" in payload["months"][0]


class TestVercelCostModel:
    """Part B — seat floor + metered overage."""

    def test_months_before_the_pro_upgrade_are_free(self):
        # Hobby was free; a seat floor before the upgrade would invent a cost we never paid.
        for month in ("2026-05", "2026-06", "2026-07"):
            assert fin._vercel_cost_for_month(month, {}) == 0.0, month

    def test_the_seat_floor_applies_from_the_upgrade_month(self):
        # ⛔ never $0 for a month the seat was paid — including when the API reports nothing.
        for month in ("2026-08", "2026-09", "2027-03"):
            assert fin._vercel_cost_for_month(month, {}) == 20.0, month

    def test_a_zero_reading_from_the_api_does_not_beat_the_floor(self):
        assert fin._vercel_cost_for_month("2026-08", {"2026-08": 0.0}) == 20.0

    def test_metered_spend_above_the_floor_wins(self):
        assert fin._vercel_cost_for_month("2026-09", {"2026-09": 34.75}) == 34.75

    def test_metered_spend_below_the_floor_is_lifted_to_it(self):
        assert fin._vercel_cost_for_month("2026-08", {"2026-08": 12.0}) == 20.0

    def test_vercel_is_in_the_monthly_total(self):
        resp = _finances_response(_vercel_costs_by_month={"2026-08": 41.0})
        aug = next((m for m in resp.months if m.month == "2026-08"), None)
        if aug is None:
            return  # window has not reached Aug 2026 yet
        assert aug.vercel_cost == 41.0
        assert aug.total_cost == round(fin._fixed_cost_for_month("2026-08") + 41.0, 2)


class TestVercelFetcher:
    """The billing-API call itself — parsing, and graceful degrade."""

    @staticmethod
    def _fake_response(body: str):
        class _Resp:
            def read(self_inner):
                return body.encode("utf-8")

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

        return _Resp()

    def setup_method(self):
        fin._vercel_cost_cache = None

    def teardown_method(self):
        fin._vercel_cost_cache = None

    def test_jsonl_charges_are_summed_per_calendar_month(self):
        # FOCUS v1.3: one charge per line, BilledCost in USD, ChargePeriodStart ISO-8601.
        body = "\n".join([
            '{"BilledCost": 20.0, "ChargePeriodStart": "2026-08-01T00:00:00Z", "ServiceName": "Pro seat"}',
            '{"BilledCost": 1.25, "ChargePeriodStart": "2026-08-14T00:00:00Z", "ServiceName": "Edge Requests"}',
            '{"BilledCost": 3.50, "ChargePeriodStart": "2026-09-02T00:00:00Z", "ServiceName": "Bandwidth"}',
            "",  # trailing newline must not blow up the parse
        ])
        with patch.dict("os.environ", {"VERCEL_API_TOKEN": "tok"}, clear=False), \
             patch("urllib.request.urlopen", return_value=self._fake_response(body)):
            costs = fin._vercel_costs_by_month()
        assert costs == {"2026-08": 21.25, "2026-09": 3.5}

    def test_credits_net_out_against_charges(self):
        body = "\n".join([
            '{"BilledCost": 20.0, "ChargePeriodStart": "2026-08-01T00:00:00Z", "ChargeCategory": "Purchase"}',
            '{"BilledCost": -5.0, "ChargePeriodStart": "2026-08-03T00:00:00Z", "ChargeCategory": "Credit"}',
        ])
        with patch.dict("os.environ", {"VERCEL_API_TOKEN": "tok"}, clear=False), \
             patch("urllib.request.urlopen", return_value=self._fake_response(body)):
            assert fin._vercel_costs_by_month() == {"2026-08": 15.0}

    def test_request_is_authorized_and_time_bounded(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["auth"] = req.get_header("Authorization")
            captured["timeout"] = timeout
            return self._fake_response("")

        with patch.dict("os.environ", {"VERCEL_API_TOKEN": "tok", "VERCEL_TEAM_ID": "team_x"}, clear=False), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            fin._vercel_costs_by_month()

        assert captured["auth"] == "Bearer tok"
        assert captured["url"].startswith("https://api.vercel.com/v1/billing/charges?")
        assert "teamId=team_x" in captured["url"]
        assert "from=" in captured["url"] and "to=" in captured["url"]
        # INC-32: an un-timed-out call on a request path burns the whole API Gateway window.
        assert isinstance(captured["timeout"], (int, float)) and captured["timeout"] > 0

    def test_requested_range_never_exceeds_the_api_one_year_cap(self):
        import datetime
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            return self._fake_response("")

        # Simulate the window start receding far into the past.
        with patch.object(fin, "_FINANCES_START", datetime.date(2020, 1, 1)), \
             patch.dict("os.environ", {"VERCEL_API_TOKEN": "tok"}, clear=False), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            fin._vercel_costs_by_month()

        qs = urllib.parse.parse_qs(urllib.parse.urlparse(captured["url"]).query)
        start = datetime.date.fromisoformat(qs["from"][0][:10])
        end = datetime.date.fromisoformat(qs["to"][0][:10])
        assert (end - start).days <= 366, f"{start}..{end} exceeds the billing API's 1-year cap"

    def test_missing_token_degrades_quietly(self):
        env = {k: v for k, v in os.environ.items() if k != "VERCEL_API_TOKEN"}
        with patch.dict("os.environ", env, clear=True):
            assert fin._vercel_costs_by_month() == {}

    def test_api_failure_degrades_quietly(self):
        # A billing-API outage must never take the finances page down with it.
        with patch.dict("os.environ", {"VERCEL_API_TOKEN": "tok"}, clear=False), \
             patch("urllib.request.urlopen", side_effect=Exception("503")):
            assert fin._vercel_costs_by_month() == {}

    def test_malformed_jsonl_degrades_quietly(self):
        with patch.dict("os.environ", {"VERCEL_API_TOKEN": "tok"}, clear=False), \
             patch("urllib.request.urlopen", return_value=self._fake_response("not json")):
            assert fin._vercel_costs_by_month() == {}

    def test_unavailable_vercel_still_serves_the_floor_with_a_note(self):
        # The graceful-degrade contract: the page renders, the seat is still counted, and the
        # missing metered spend is DISCLOSED rather than silently reported as $0.
        resp = _finances_response(_vercel_costs_by_month={})
        assert any("Vercel" in n for n in resp.notes)
        aug = next((m for m in resp.months if m.month >= "2026-08"), None)
        if aug is not None:
            assert aug.vercel_cost == 20.0
