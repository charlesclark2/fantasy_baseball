"""spine_horizon.py — INC-37 spine-staleness page classifier.

WHY THIS EXISTS (INC-37, 2026-08-01 — a P1 that had already recurred on 06-01 and 07-01):
    `mart_game_spine` is the scheduled-game universe the --w8a/--w8b feature build reads. When a
    build produces a spine whose games do not reach the current day, the pregame feature store
    loses today's slate and predict_today silently degrades to the intraday assembly — the entire
    morning tier serves on an amputated feature vector.

    `run_w1_lakehouse.py::_alert_stale_game_spine` has DETECTED exactly that since 2026-07-02 and
    it fired correctly on every one of those three mornings. It only ever wrote a stderr WARNING
    inside a Dagster step log, so nobody was notified — precisely the E11.30 finding that
    "ALERT-tier" had quietly come to mean "detected, nobody paged". The script now also emits a
    `[METRIC] spine_covers_today=<1|0|-1>` line on stdout; this module turns that line into a
    paging decision, and `lakehouse_spine_odds_bridge_op` calls send_alert on it.

    Lives in betting_ml/ (not pipeline/) so the fast gate can import it: `pipeline/__init__.py`
    reads the dbt manifest, which is absent in CI, so a fast-gate test that imports `pipeline`
    crashes at COLLECTION rather than skipping (E11.23).

THREE-VALUED ON PURPOSE. `1` = the spine reaches today. `0` = it does not (page). `-1` = the
check could not run (the DuckDB read raised) — that is NOT a pass. A guard whose evaluation
failed must never be scored as healthy (the NF1.7 (a) lesson: an anchor that fails to fit makes
its assertion vacuously true). An ABSENT metric line is treated the same way as `-1`: a build
that never emitted it is an unverified build, not a verified-healthy one — but it is reported at
WARN, not CRITICAL, because the likeliest cause is a gated-off/skipped stage rather than a real
outage, and paging CRITICAL on a deliberate skip is the alert-fatigue failure mode.
"""

from __future__ import annotations

METRIC_PREFIX = "[METRIC] spine_covers_today="

COVERS_TODAY = 1
STALE = 0
UNKNOWN = -1


def parse_spine_covers_today(stdout: str) -> int | None:
    """Return the LAST `spine_covers_today` value in `stdout`, or None if never emitted.

    LAST, not first: one op invocation may run several build stages, and the value that matters
    is the state after the final spine build in that op.
    """
    value: int | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith(METRIC_PREFIX):
            continue
        try:
            value = int(line[len(METRIC_PREFIX):].strip())
        except ValueError:
            continue
    return value


def classify(value: int | None) -> tuple[str | None, str]:
    """PURE. Map a parsed metric value to (severity, message). severity None = do not page.

    severity is CRITICAL only for a CONFIRMED stale spine — the condition that costs a whole
    slate its feature blocks. An unevaluable / absent check is WARN: worth seeing, not worth
    waking someone for, and never silently treated as healthy.
    """
    if value == COVERS_TODAY:
        return None, "mart_game_spine reaches the current date."
    if value == STALE:
        return "CRITICAL", (
            "mart_game_spine's scheduled universe does NOT reach today. The --w8a/--w8b feature "
            "build reads this spine, so feature_pregame_game_features will LACK the current "
            "slate and predict_today will serve the whole tier from the intraday fallback on an "
            "amputated feature vector (INC-37). Most likely cause: the schedule the W3pre flatten "
            "read predates today's games — on the 1st of a month that is the INC-37 "
            "month-boundary hole (the last capture of a month contains no games for the 1st). "
            "Remediate: re-run ingest_statsapi.py schedule --lookahead-days 3, then rebuild "
            "--w5-only --w5-group-a-only -> --w8a -> --w5b -> --w8b and re-score the slate."
        )
    if value == UNKNOWN:
        return "WARN", (
            "The spine-staleness check could not be evaluated (the mart_game_spine read raised). "
            "The spine's freshness is UNVERIFIED for this run — treat it as unknown, not healthy "
            "(INC-37). Check the step log for the underlying DuckDB/S3 error."
        )
    return "WARN", (
        "The spine build emitted no spine_covers_today metric — the spine's freshness is "
        "UNVERIFIED for this run (INC-37). Expected when the stage was gated off/skipped; "
        "otherwise the build did not reach the staleness check."
    )
