"""MLB-INC-0917 — a bounded retry for the HALT-tier lakehouse ops in `daily_ingestion_job`.

WHAT HAPPENED (2026-09-16).

`lakehouse_w3_marts_op` failed at 12:26:21Z with S3 403 `RequestTimeTooSkewed` while binding
`CREATE OR REPLACE VIEW stg_batter_pitches` (`run_w1_lakehouse.py:2741`). The step ran 998 s
against its usual ~250 s (09-13/14/15: 250 / 251 / 249 s), and W2 had bound the very same view
minutes earlier in its normal 272 s. Because every lakehouse op is HALT-tier, that ONE transient
failure skipped the rest of the daily job:

  * `lakehouse_w3pre_flatten_op` — the only writer of stg_oddsapi_odds / stg_derivative_odds since
    MLB-LAKE2, so CLV/line-history accumulation froze until INC-41 paged 30 h later;
  * W6, W7b, spine/odds-bridge, W8a, W8b and the W11 tail;
  * `dbt_daily_build`, the signal generators, `predict_today_morning` and the serving writes —
    the 09-16 morning tier never served (the slate ran on `intraday_assembly` until the lineup
    rebuild landed at 20:41Z).

Nobody re-executed the run. The same build had succeeded four hours earlier inside
`odds_clv_rebuild_job` and every day before, so the failure was transient, and a second attempt in
a fresh process would very likely have recovered the whole slate.

THE MECHANISM IS NOT MEASURED, and this module does not claim it. It is the INC-42 class: INC-42's
two failures landed at 1044.7 s and 1056.1 s, this one at ~998 s — all three past S3's 900 s SigV4
tolerance, which is consistent with INC-42's OPEN hypothesis H ("DuckDB signs once per query, so any
request issued >900 s into one query is rejected"). Three consistent observations are not a
confirmation. What stalled the bind is unknown; the glob is small (366 files, 1.09 GB), so INC-42's
"the glob grew too large" lead does not explain it. A retry is a MITIGATION of the consequence
(one transient takes down a whole slate), not a cure of the stall.

THE POLICY.

  MAX_RETRIES = 1   — one extra attempt. A deterministic failure (a schema break, the INC-23 class)
                      costs one more attempt and then fails exactly as before, still paging
                      CRITICAL through run_failure_alert_sensor (daily_ingestion_job is in its
                      HALT set). More attempts would only lengthen a run that is going to fail.
  DELAY_SECONDS = 60 — the repo's existing precedent (`sensor_ops._CATCHUP_RETRY`). A retry is a
                      fresh subprocess, so it re-signs every request; the delay only gives an S3 /
                      network blip a moment to clear.

Retrying is safe because every retried op is a full, idempotent rebuild that runs daily by design
(Delta partition swap / full parquet rewrite / ext-table REFRESH). A retry is keyed on the op
FAILING — never on matching an error string (the NCAAF-LAKE1 lesson: message text is not a
contract).

THE BOUND (pinned by betting_ml/tests/test_mlb_inc_0917_lakehouse_retry.py). For every retried op
with a wall-clock cap C, its worst case `C * (1 + MAX_RETRIES) + DELAY_SECONDS * MAX_RETRIES` stays
below the global `run_monitoring.max_runtime_seconds` (14 400 s), so a single retried op can never
be swept away by a run-level termination that says nothing about which op died. The mirror-tier
ops carry no per-script cap; a retry can only follow a FAILURE, so it cannot extend a hang — a hang
is still ended by run monitoring, exactly as before this change.

VISIBILITY. A retry that succeeds leaves the run green, which is precisely how INC-42's failures
hid ("only findable by grepping the Postgres event log"). Every retried attempt therefore logs a
WARNING, prints a `[METRIC] lakehouse_op_retry=` line and pages WARN — so the recurrence rate of
this class is COUNTED, which is the evidence INC-42's hypothesis H still needs.

Import-safe (no `pipeline` import at module scope — the E11.23 fast-gate rule).
"""
from __future__ import annotations

from typing import Callable, Optional

MAX_RETRIES = 1
DELAY_SECONDS = 60

# Every `lakehouse_*` op in pipeline/ops/daily_ingestion_ops.py is in exactly one of these two
# registries; the guard test fails if a new lakehouse op is added without being classified.
RETRIED_OPS: tuple[str, ...] = (
    "lakehouse_w1_pitch_marts_op",
    "lakehouse_w2_marts_op",
    "lakehouse_w3_marts_op",
    "lakehouse_w3pre_flatten_op",
    "lakehouse_w6_odds_marts_op",
    "lakehouse_w7b_serving_op",
    "lakehouse_spine_odds_bridge_op",
    "lakehouse_w8a_feature_layer_op",
    "lakehouse_w8b_aggregator_op",
)

NOT_RETRIED_OPS: dict[str, str] = {
    "lakehouse_schedule_export_op": (
        "does no work since E11.20 phase-2b (the bridge is retired; the op only logs) — it cannot "
        "fail, so a policy on it would be decoration"
    ),
    "lakehouse_w11_nightly_op": (
        "ALERT-continue tier — each sub-tier swallows its own failure, so the op never raises and "
        "a retry could never trigger"
    ),
    "lakehouse_delta_maintenance_op": (
        "WARN tier, off the critical path — a failure defers compaction to tomorrow by design"
    ),
}

RETRY_METRIC = "lakehouse_op_retry"


def note_retry_attempt(
    context,
    op_name: str,
    *,
    sender: Optional[Callable[..., object]] = None,
) -> bool:
    """Make a retried attempt LOUD. Returns True when this attempt is a retry.

    Call as the first statement of every op in RETRIED_OPS. On the first attempt
    (`context.retry_number == 0`) it does nothing. On a retry it logs a WARNING carrying a
    `[METRIC]` line and pages WARN. Never raises — a failed page must not fail the rebuild.
    """
    attempt = int(getattr(context, "retry_number", 0) or 0)
    if attempt <= 0:
        return False
    run_id = getattr(context, "run_id", "?")
    context.log.warning(
        f"[MLB-INC-0917] {op_name} is RETRYING (attempt {attempt + 1} of {MAX_RETRIES + 1}) after a "
        f"failed attempt in run {run_id}. The previous attempt's error is in this step's event log.\n"
        f"[METRIC] {RETRY_METRIC}={op_name} attempt={attempt}"
    )
    try:
        if sender is None:
            from pipeline.utils.alerting import send_alert as sender  # call-time: box process only
        sender(
            f"{op_name} retrying after a failed attempt",
            (
                f"{op_name} failed its first attempt in daily_ingestion_job run {run_id} and is being "
                f"retried once (MLB-INC-0917). If this attempt succeeds, the run continues and no "
                f"CRITICAL page follows; if it fails, run_failure_alert_sensor pages CRITICAL.\n\n"
                f"Read the failed attempt's error in the step event log. A 403 RequestTimeTooSkewed "
                f"there is the INC-42 class — record the attempt's duration, which is the evidence "
                f"INC-42's open hypothesis still needs."
            ),
            severity="WARN",
            dedup_key=f"{RETRY_METRIC}:{op_name}",
        )
    except Exception as e:  # noqa: BLE001 — a failed page must not fail the build
        context.log.warning(f"[MLB-INC-0917] retry page failed (non-fatal): {e}")
    return True
