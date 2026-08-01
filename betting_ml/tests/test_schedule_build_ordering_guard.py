"""INC-37 guard — the schedule must be captured BEFORE the lakehouse build flattens it, and no
schedule capture may be month-scoped short.

WHAT HAPPENED (2026-08-01, P1 serving-degrade; the third occurrence — 06-01 and 07-01 were
identical and went unnoticed because nothing paged until E11.30 wired send_alert):

    `ingest_statsapi_schedule` sat at s6 in daily_ingestion_job — AFTER the entire lk1..lk10 S3
    lakehouse chain. So every daily feature build flattened whatever schedule the last INTRADAY
    capture had left in S3, never one taken in the same run. On 363 days a year that is harmless:
    yesterday's capture already covers today. On the 1st of a month it is fatal, because
    `run_schedule` iterates WHOLE months — the final July capture (2026-07-31T23:30Z) carried
    2026-07-01..2026-07-31 and ZERO games for 2026-08-01.

    Result: the 12:00-UTC build produced a game universe that stopped at 07-31 — no 08-01 rows in
    mart_game_spine, the W1-W6 marts, the odds bridge, or the whole W8a feature layer. The served
    feature store had 15 rows for 08-01 with 5 of its 6 coverage blocks at 0% (mean coverage
    0.178 vs the 0.70 gate), so predict_today fell to intraday_fallback on all 15 games, the
    outputs went flat, and the Bovada target-book price was blank on the whole slate.

TWO INDEPENDENT CURES, BOTH PINNED HERE — either one alone would have prevented it, and they fail
in different ways, which is the point of keeping both:
  (1) ORDERING — capture the schedule before the flatten reads it (the INC-25 rule applied to the
      schedule: a consumer reading an S3 mirror must be rebuilt DOWNSTREAM of the refresh that
      feeds it, in the SAME run). Protects against a stale capture generally, not just at a month
      boundary.
  (2) LOOKAHEAD — `--lookahead-days N` makes the last N captures of every month ALSO fetch the
      next month, so the month-boundary hole cannot open even for a consumer that reads a capture
      from a previous run (the intraday chain, a re-execute-from-step, a hand-run build).

These are SOURCE-INSPECTION tests, not import tests: `pipeline/__init__.py` reads the dbt
manifest, which is absent in the fast gate, so importing `pipeline` here would crash at
COLLECTION rather than skip (E11.23).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
JOB = REPO_ROOT / "pipeline" / "jobs" / "daily_ingestion_job.py"
DAILY_OPS = REPO_ROOT / "pipeline" / "ops" / "daily_ingestion_ops.py"
INTRADAY_OPS = REPO_ROOT / "pipeline" / "ops" / "intraday_ops.py"
INGEST = REPO_ROOT / "scripts" / "ingest_statsapi.py"
LAKEHOUSE = REPO_ROOT / "scripts" / "run_w1_lakehouse.py"


def _call_line(source: str, callee: str) -> int:
    """1-indexed line of the first CALL to `callee` in the job body (not its import)."""
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith(("#", "from ", "import ")):
            continue
        if re.search(rf"=\s*{re.escape(callee)}\s*\(", stripped):
            return i
    raise AssertionError(f"no call to {callee}() found")


# ── (1) ORDERING ──────────────────────────────────────────────────────────────────────────────

class TestScheduleIsCapturedBeforeTheLakehouseFlatten:

    def test_ingest_precedes_the_lakehouse_chain_in_the_daily_job(self):
        src = JOB.read_text()
        ingest_at = _call_line(src, "ingest_statsapi_schedule")
        export_at = _call_line(src, "lakehouse_schedule_export_op")
        assert ingest_at < export_at, (
            "INC-37: ingest_statsapi_schedule must run BEFORE lakehouse_schedule_export_op / the "
            f"W3pre flatten (found ingest at line {ingest_at}, lakehouse chain start at line "
            f"{export_at}). With the capture downstream, the daily feature build flattens a "
            "schedule from a PREVIOUS run — which on the 1st of a month contains zero games for "
            "today, so the entire slate builds with no pregame features."
        )

    def test_the_lakehouse_chain_actually_depends_on_the_ingest(self):
        """Ordering by line number is not enough — Dagster runs on the dependency graph, so the
        first lakehouse op must take the ingest's handle as its `start`."""
        src = JOB.read_text()
        m = re.search(r"(\w+)\s*=\s*ingest_statsapi_schedule\(", src)
        assert m, "ingest_statsapi_schedule() result is not bound to a name"
        handle = m.group(1)
        assert re.search(rf"lakehouse_schedule_export_op\(start={handle}\)", src), (
            f"INC-37: lakehouse_schedule_export_op must be wired `start={handle}` so the "
            "dependency graph — not just the source order — puts the schedule capture first."
        )

    def test_the_guard_fires_on_the_pre_fix_ordering(self):
        """The invariant must be able to FAIL. Replays the exact pre-fix shape."""
        pre_fix = (
            "    s5b = ingest_statcast_to_s3_op(start=s5)\n"
            "    lk1 = lakehouse_schedule_export_op(start=s5b)\n"
            "    lk5 = lakehouse_w3pre_flatten_op(start=lk4)\n"
            "    s5f = check_feature_block_coverage_op(start=s5e)\n"
            "    s6 = ingest_statsapi_schedule(start=s5f)\n"
        )
        assert _call_line(pre_fix, "ingest_statsapi_schedule") > _call_line(
            pre_fix, "lakehouse_schedule_export_op"
        ), "the pre-fix source must violate the ordering invariant, or this guard proves nothing"


# ── (2) LOOKAHEAD ─────────────────────────────────────────────────────────────────────────────

class TestNoScheduleCaptureIsMonthScopedShort:

    @pytest.mark.parametrize(
        "path,label",
        [
            (DAILY_OPS, "daily_ingestion_ops.ingest_statsapi_schedule"),
            (INTRADAY_OPS, "intraday_ops.intraday_schedule_capture"),
        ],
    )
    def test_every_recurring_capture_passes_a_nonzero_lookahead(self, path, label):
        src = path.read_text()
        # Find the ingest_statsapi.py invocation and assert --lookahead-days rides along with a
        # positive value. A zero/absent lookahead reopens the month-boundary hole.
        blocks = re.findall(
            r"_run_script\(\s*context,\s*\"ingest_statsapi\.py\",(.*?)\)\n", src, re.DOTALL
        )
        sched = [b for b in blocks if '"schedule"' in b]
        assert sched, f"{label}: no ingest_statsapi.py schedule invocation found"
        for block in sched:
            m = re.search(r'"--lookahead-days",\s*"(\d+)"', block)
            assert m, (
                f"INC-37: {label} must pass --lookahead-days so the last captures of a month also "
                "fetch the NEXT month. Without it the final capture of a month holds zero games "
                "for the 1st and the next day's whole slate builds with no pregame features."
            )
            assert int(m.group(1)) > 0, f"{label}: --lookahead-days must be > 0, got {m.group(1)}"

    def test_apply_lookahead_crosses_the_month_boundary(self):
        """The pure function the fix rests on. Loaded by path so the fast gate never imports
        the script's Snowflake/boto3 module-level surface."""
        apply_lookahead = _load_apply_lookahead()
        # The exact INC-37 case: the last capture of July must reach into August.
        assert apply_lookahead(date(2026, 7, 31), 3) == date(2026, 8, 3)
        # ...and a mid-month capture must NOT be widened into the next month (no extra fetch).
        assert apply_lookahead(date(2026, 7, 15), 3) == date(2026, 7, 18)
        # Year boundary.
        assert apply_lookahead(date(2026, 12, 31), 3) == date(2027, 1, 3)
        # A zero/negative lookahead is a no-op — it must never SHORTEN the range.
        assert apply_lookahead(date(2026, 7, 31), 0) == date(2026, 7, 31)
        assert apply_lookahead(date(2026, 7, 31), -5) == date(2026, 7, 31)

    def test_lookahead_is_wired_into_the_month_range_resolution(self):
        """apply_lookahead must actually be applied where schedule_end is resolved — a pure
        function nothing calls is not a fix."""
        src = INGEST.read_text()
        assert "apply_lookahead(schedule_end" in src, (
            "INC-37: ingest_statsapi.py must apply the lookahead to schedule_end before "
            "run_schedule() iterates months"
        )


def _load_apply_lookahead():
    """Import ingest_statsapi.apply_lookahead by path with heavy/IO imports absent.

    The module imports snowflake at top level; if that is unavailable in the fast-gate
    environment, fall back to executing just the function's source (it depends only on
    datetime.timedelta), so this invariant is checked either way rather than silently skipped.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("_inc37_ingest_statsapi", INGEST)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module.apply_lookahead
    except Exception:  # noqa: BLE001 — see docstring
        src = INGEST.read_text()
        m = re.search(r"\ndef apply_lookahead\(.*?\n(?=\n\S|\ndef )", src, re.DOTALL)
        assert m, "apply_lookahead() not found in ingest_statsapi.py"
        ns: dict = {}
        exec("from datetime import date, timedelta\n" + m.group(0), ns)  # noqa: S102
        return ns["apply_lookahead"]


# ── (3) THE DETECTOR MUST PAGE, NOT JUST LOG (E11.30 rule) ────────────────────────────────────

class TestSpineStalenessActuallyPages:

    def test_the_build_emits_the_discriminating_metric(self):
        src = LAKEHOUSE.read_text()
        assert "[METRIC] spine_covers_today=" in src, (
            "INC-37: _alert_stale_game_spine must emit a machine-readable "
            "`[METRIC] spine_covers_today=` line — a stderr banner alone is a detection with no "
            "notification (the E11.30 finding)."
        )

    def test_the_op_pages_on_it(self):
        src = DAILY_OPS.read_text()
        assert "_alert_on_stale_spine(context, spine_out)" in src, (
            "INC-37: lakehouse_spine_odds_bridge_op must evaluate the spine-staleness metric"
        )
        helper = src.split("def _alert_on_stale_spine")[1].split("\n@op")[0]
        assert "send_alert(" in helper, (
            "INC-37: the spine-staleness helper must genuinely PAGE via send_alert — an "
            "ALERT-tier detector enforced only by a docstring is not enforced at all (E11.30)."
        )

    def test_classifier_pages_on_stale_and_is_silent_on_healthy(self):
        from betting_ml.monitoring.spine_horizon import (
            classify,
            parse_spine_covers_today,
        )

        assert classify(parse_spine_covers_today("[METRIC] spine_covers_today=1"))[0] is None
        assert classify(parse_spine_covers_today("[METRIC] spine_covers_today=0"))[0] == "CRITICAL"

    def test_an_unevaluable_or_absent_check_is_not_scored_as_healthy(self):
        """NF1.7 (a): an anchor that fails to evaluate must not make its assertion vacuously
        true. Both the explicit UNKNOWN sentinel and a missing line must be reported, not passed."""
        from betting_ml.monitoring.spine_horizon import (
            classify,
            parse_spine_covers_today,
        )

        assert classify(parse_spine_covers_today("[METRIC] spine_covers_today=-1"))[0] == "WARN"
        assert classify(parse_spine_covers_today("some build output\nno metric here"))[0] == "WARN"

    def test_build_marts_does_not_destroy_a_non_utf8_error(self):
        """INC-37: a DuckDB error whose message isn't valid UTF-8 surfaced as a bare
        UnicodeDecodeError with no model name and no DuckDB text — the real diagnostic was gone."""
        src = LAKEHOUSE.read_text()
        body = src.split("def _build_marts")[1].split("\ndef ")[0]
        assert "except UnicodeDecodeError" in body, (
            "INC-37: _build_marts must catch UnicodeDecodeError around the COPY and re-raise "
            "with the message salvaged + the model named"
        )
        assert 'errors="replace"' in body, (
            "INC-37: the salvaged message must be re-decoded with errors='replace' — otherwise "
            "the original DuckDB text is still lost"
        )

    def test_the_last_metric_line_wins(self):
        """One op runs several build stages; the state after the FINAL spine build is what counts."""
        from betting_ml.monitoring.spine_horizon import (
            classify,
            parse_spine_covers_today,
        )

        out = "[METRIC] spine_covers_today=0\nrebuilding...\n[METRIC] spine_covers_today=1\n"
        assert parse_spine_covers_today(out) == 1
        assert classify(parse_spine_covers_today(out))[0] is None


# ── (4) A TIER GUARD THAT ASSESSED NOTHING MUST NOT READ AS A PASS ────────────────────────────

class TestVacuousTierGuardPassIsSurfaced:
    """INC-37, 2026-08-01: a mis-run left 4 of 15 games served. Both tier guards skip a tier under
    MIN_GAMES_FOR_CHECK=5, so BOTH printed `problem_count=0` / `alert_count=0` while 11 games sat
    unserved. `tiers_assessed=0` was the only tell and no op read it."""

    CHECKS = [
        (REPO_ROOT / "scripts" / "check_intraday_fallback.py", "intraday_fallback"),
        (REPO_ROOT / "scripts" / "check_served_prediction_integrity.py", "served_integrity"),
    ]

    @pytest.mark.parametrize("path,prefix", CHECKS)
    def test_script_emits_the_unassessed_row_count(self, path, prefix):
        src = path.read_text()
        assert f"[METRIC] {prefix}_unassessed_rows=" in src, (
            f"INC-37: {path.name} must report how many served rows it did NOT assess — without "
            f"it a '0 problems' result is indistinguishable from 'nothing was checked'"
        )
        assert "unassessed_rows += stat.n" in src, (
            f"INC-37: {path.name} must ACCUMULATE the skipped tiers' rows, not just emit a zero"
        )

    def test_both_ops_page_when_nothing_was_assessed(self):
        src = DAILY_OPS.read_text()
        # Count CALL sites only — the `def` line matches the same text.
        calls = [ln for ln in src.splitlines()
                 if "_alert_if_nothing_assessed(context," in ln and not ln.lstrip().startswith("def ")]
        assert len(calls) == 2, (
            "INC-37: BOTH check_served_prediction_integrity_op and check_intraday_fallback_op "
            f"must evaluate the not-assessed condition (found {len(calls)} call site(s))"
        )
        helper = src.split("def _alert_if_nothing_assessed")[1].split("\ndef ")[0]
        assert "send_alert(" in helper, "INC-37: the not-assessed helper must genuinely page"
        assert 'severity="WARN"' in helper, (
            "INC-37: 'could not verify' is not 'found a problem' — it must page WARN, not CRITICAL"
        )

    def test_it_stays_silent_unless_nothing_was_assessed(self):
        """Narrowness is the point — this must not become alert fatigue on a small-but-checked
        slate, and a zero-prediction day must never reach it."""
        src = DAILY_OPS.read_text()
        helper = src.split("def _alert_if_nothing_assessed")[1].split("\ndef ")[0]
        assert "if assessed is None or assessed > 0 or unassessed_rows <= 0:" in helper, (
            "INC-37: the guard must fire ONLY when assessed==0 AND rows exist — any tier actually "
            "assessed, or a slate with no rows, must stay silent"
        )
