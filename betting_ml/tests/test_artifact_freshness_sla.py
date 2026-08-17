"""INC-41 — guards for the per-artifact freshness SLA on serving-critical parquet.

WHAT THESE PROVE, and why each layer is here.

    On 2026-08-06 `stg_statsapi_lineups_wide` froze for 6.5 hours while every existing check read
    green, because each of them watches a SOURCE and none asserted the DERIVED artifact had
    advanced. The check that closes it is only worth having if it genuinely fires — so the suite
    is built around a two-sided RED proof over REAL parquet:

      • a deliberately FROZEN fixture  -> the real script pages CRITICAL
      • a FRESH fixture                -> silent
      • an ABSENT artifact             -> WARN, never scored healthy (NF1.7 (a))

    The end-to-end tests run the REAL `main()` against REAL parquet files on a REAL DuckDB
    connection, with only the S3 location swapped. Nothing about the timestamp SQL, the print
    format, the parsers or the classifier is hand-authored — which is the INC-39 lesson (a suite
    that stubs the subprocess away asserts only against a stdout string a test author wrote, and
    stays green if the print format and the regex drift apart) and the NF-C0e lesson (a test that
    reads a value back under the key the code wrote can never catch a wrong key).

Fast-gate-safe: imports `pipeline` ONLY inside tests guarded on the dbt manifest (E11.23).
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

from betting_ml.monitoring.artifact_freshness import (
    ALWAYS,
    MAX_CLOCK_SKEW_MINUTES,
    OK,
    REGISTRY,
    SCHEDULE_CAPTURE_HOURS,
    STALE,
    UNEVALUABLE,
    FreshnessContract,
    active_minutes_between,
    classify,
    evaluate,
    parse_evaluated,
    parse_now,
    parse_verdicts,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _PROJECT_ROOT / "scripts" / "check_artifact_freshness.py"

_MANIFEST = _PROJECT_ROOT / "dbt" / "target" / "manifest.json"
requires_pipeline = pytest.mark.skipif(
    not _MANIFEST.exists(), reason="needs the dbt manifest to import `pipeline` (E11.23)"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("_inc41_freshness_check", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


chk = _load_script()


def _utc(y, m, d, hh=0, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


# ══ 1. The core mechanism: active-minute lag ═══════════════════════════════════════════════
# Everything else rests on this. A raw wall-clock lag would false-page every night, because the
# schedule-capture writer has a DELIBERATE 10.5-hour overnight gap (*/30 14-23 + 0,30 0-3 UTC).

class TestActiveMinuteLagIsOffHoursAware:
    def test_the_overnight_gap_is_not_counted_as_lag(self):
        """Froze at the last overnight fire (03:30) and it is now 05:04 — the live 2026-08-07
        reading. Only 03:30-04:00 is active, so the artifact is 30 min behind, not 94."""
        lag = active_minutes_between(
            _utc(2026, 8, 7, 3, 30), _utc(2026, 8, 7, 5, 4), SCHEDULE_CAPTURE_HOURS
        )
        assert lag == 30
        assert (_utc(2026, 8, 7, 5, 4) - _utc(2026, 8, 7, 3, 30)).total_seconds() / 60 == 94

    def test_the_whole_dead_band_adds_nothing_no_matter_how_long_you_wait(self):
        """13:59 UTC is the last minute before the daytime band reopens: still only 30 min."""
        assert active_minutes_between(
            _utc(2026, 8, 7, 3, 30), _utc(2026, 8, 7, 13, 59), SCHEDULE_CAPTURE_HOURS
        ) == 30

    def test_hour_4_is_excluded_so_the_overnight_lag_cannot_reach_the_sla(self):
        """REGRESSION (found by running the check live, 2026-08-07 05:04Z).

        Including UTC hour 4 to give the 03:30 fire its 30-minute grace instead adds a FULL 60,
        which put every schedule-derived artifact at a lag of EXACTLY 90 against an SLA of 90 —
        passing only because the comparison is strictly `>`. The overnight lag must stay capped
        well below the SLA, or the monitor false-pages every single night.
        """
        assert 4 not in SCHEDULE_CAPTURE_HOURS
        worst_overnight = max(
            active_minutes_between(_utc(2026, 8, 7, 3, 30), _utc(2026, 8, 7, h, m),
                                   SCHEDULE_CAPTURE_HOURS)
            for h in range(4, 14) for m in (0, 30, 59)
        )
        sla = min(c.max_lag_minutes for c in REGISTRY
                  if c.active_hours_utc == SCHEDULE_CAPTURE_HOURS)
        assert worst_overnight == 30
        assert worst_overnight < sla / 2, (
            f"overnight lag {worst_overnight} leaves no headroom under SLA {sla}"
        )

    def test_lag_resumes_when_the_band_reopens(self):
        """A freeze that survives INTO the active band must start accruing again — otherwise the
        off-hours exemption would swallow a real freeze that began overnight."""
        assert active_minutes_between(
            _utc(2026, 8, 7, 3, 30), _utc(2026, 8, 7, 14, 45), SCHEDULE_CAPTURE_HOURS
        ) == 75  # 30 overnight + 45 into the daytime band
        assert active_minutes_between(
            _utc(2026, 8, 7, 3, 30), _utc(2026, 8, 7, 15, 30), SCHEDULE_CAPTURE_HOURS
        ) == 120  # over the 90 SLA: 90 min into the band with no write IS a freeze

    def test_the_inc41_freeze_itself_is_far_past_the_sla(self):
        """The actual incident: froze 20:08Z, still frozen at 02:38Z. Both ends are inside the
        active band, so the full 6.5h counts — this is the case that must page."""
        lag = active_minutes_between(
            _utc(2026, 8, 6, 20, 8), _utc(2026, 8, 7, 2, 38), SCHEDULE_CAPTURE_HOURS
        )
        assert lag == 390
        assert lag > 90

    def test_always_active_is_plain_wall_clock(self):
        assert active_minutes_between(
            _utc(2026, 8, 6, 23, 30), _utc(2026, 8, 7, 5, 0), ALWAYS
        ) == 330

    def test_a_content_timestamp_ahead_of_now_is_never_negative_lag(self):
        assert active_minutes_between(
            _utc(2026, 8, 7, 16, 0), _utc(2026, 8, 7, 15, 0), SCHEDULE_CAPTURE_HOURS
        ) == 0.0


# ══ 2. evaluate(): a reading that cannot be taken is never a pass ══════════════════════════

class TestEvaluateRefusesToScoreTheUnevaluableAsHealthy:
    contract = REGISTRY[0]

    def test_a_missing_timestamp_is_unevaluable_not_ok(self):
        r = evaluate(self.contract, None, _utc(2026, 8, 7, 16, 0))
        assert r.verdict == UNEVALUABLE and r.is_problem

    def test_a_future_timestamp_is_unevaluable_not_ok(self):
        """E9.48-b: an upstream keying typo dated a row far in the future and thereby SILENTLY
        DISABLED a max()-based freshness guard — the lag went hugely negative and the check could
        never trip. A future max() must refuse, not pass."""
        now = _utc(2026, 8, 7, 16, 0)
        r = evaluate(self.contract, now + timedelta(days=900), now)
        assert r.verdict == UNEVALUABLE and r.is_problem

    def test_a_naive_timestamp_is_read_as_utc(self):
        """DuckDB returns naive datetimes for the ISO-VARCHAR lakehouse columns (INC-23)."""
        r = evaluate(self.contract, datetime(2026, 8, 7, 15, 45), _utc(2026, 8, 7, 16, 0))
        assert r.verdict == OK and r.active_lag_minutes == 15

    def test_fresh_is_ok_and_stale_is_stale_across_the_boundary(self):
        now = _utc(2026, 8, 7, 18, 0)
        sla = self.contract.max_lag_minutes
        assert evaluate(self.contract, now - timedelta(minutes=sla), now).verdict == OK
        assert evaluate(self.contract, now - timedelta(minutes=sla + 1), now).verdict == STALE


# ══ 3. END-TO-END over REAL parquet ════════════════════════════════════════════════════════
# The RED proof. Real parquet -> real DuckDB -> the real ts_expr SQL -> the real script main()
# -> its real stdout -> the real parsers -> the real classifier. Only the S3 location is swapped.

def _write_fixture(tmp_path: Path, table: str, ts: str | None, *, column="ingestion_ts") -> None:
    """Write a real parquet for `table`. ts=None writes a row whose timestamp column is NULL."""
    import duckdb

    d = tmp_path / table
    d.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    value = "NULL" if ts is None else f"'{ts}'"
    # Stored as VARCHAR, exactly as the lakehouse stores every TIMESTAMP (the INC-23 cure) — so
    # the try_cast in each contract's ts_expr is genuinely exercised.
    con.execute(
        f"COPY (SELECT 1 AS game_pk, {value}::VARCHAR AS {column}) "
        f"TO '{d / 'data.parquet'}' (FORMAT PARQUET)"
    )
    con.close()


def _run_real_script_against(tmp_path: Path, now: datetime | None = None) -> str:
    """Run the REAL script main() over the fixture directory and return its REAL stdout.

    Only two seams are patched, both purely locational: `duck()` (a plain local DuckDB instead of
    the S3-configured one) and `register_lakehouse_views` (a view over the fixture parquet instead
    of the S3 glob). The timestamp SQL, the verdicts, the printing and the exit code are the
    production code paths.
    """
    import duckdb

    def _fake_register(conn, tables):
        for t in tables:
            path = tmp_path / t / "data.parquet"
            if not path.exists():
                # Exactly how an absent artifact behaves in production: DuckDB raises on a glob
                # that matches nothing, and the script must degrade to UNEVALUABLE, not crash.
                raise duckdb.IOException(
                    f'IO Error: No files found that match the pattern "{path}"')
            conn.execute(
                f"CREATE OR REPLACE VIEW {t} AS SELECT * FROM read_parquet('{path}')")

    buf = io.StringIO()
    ctx = contextlib.ExitStack()
    ctx.enter_context(mock.patch("betting_ml.utils.lakehouse_monitor.duck", duckdb.connect))
    ctx.enter_context(
        mock.patch("betting_ml.utils.delta_lakehouse.register_lakehouse_views", _fake_register))
    ctx.enter_context(mock.patch.object(sys, "argv", ["check_artifact_freshness.py"]))
    ctx.enter_context(contextlib.redirect_stdout(buf))
    with ctx:
        rc = chk.main()
    assert rc == 0, "ALERT tier: the script must never exit non-zero without --strict"
    return buf.getvalue()


def _ts_column_of(contract) -> str:
    """The column a contract's ts_expr reads, DERIVED from the expression itself.

    ⚠️ This used to be `"computed_at" if "computed_at" in ts_expr else "ingestion_ts"` — an
    incomplete branch on what is really an open set. Adding a registry entry with any third column
    silently produced a fixture with the WRONG column name, so the real script could not bind its
    ts_expr and every end-to-end test reported UNEVALUABLE. (Caught exactly that way by the
    `stg_ref_players` entry, whose stamp is `built_at`.) Deriving the name means a future entry
    needs no change here at all — the same reason a two-way test on a three-way field is a bug
    (E9.64b), not a style preference.
    """
    m = re.search(r"try_cast\(\s*([A-Za-z_][A-Za-z0-9_]*)\s+as\b", contract.ts_expr, re.I)
    assert m, (
        f"cannot derive the timestamp column from {contract.name}'s ts_expr "
        f"({contract.ts_expr!r}) — the fixture would be built on a guess"
    )
    return m.group(1)


def test_every_contract_yields_a_fixture_column():
    """Anti-vacuity for the derivation above: if it silently returned nothing for an entry, that
    entry's fixture would be malformed and its end-to-end coverage would evaporate."""
    assert REGISTRY, "the registry is empty — every end-to-end test below is vacuous"
    for c in REGISTRY:
        assert _ts_column_of(c)


def _all_fixtures(tmp_path: Path, ts: str) -> None:
    """Give every registered artifact a fixture at `ts`, using its own timestamp column."""
    for c in REGISTRY:
        _write_fixture(tmp_path, c.ts_table, ts, column=_ts_column_of(c))


class TestEndToEndOverRealParquet:
    def test_a_fresh_artifact_is_silent(self, tmp_path):
        now = datetime.now(timezone.utc)
        _all_fixtures(tmp_path, now.strftime("%Y-%m-%d %H:%M:%S"))
        out = _run_real_script_against(tmp_path)
        assert parse_evaluated(out) is True
        verdicts = parse_verdicts(out)
        assert {v for v, _, _ in verdicts.values()} == {OK}
        severity, _ = classify(out, now)
        assert severity is None, "a fresh artifact must not page"

    def test_a_frozen_artifact_pages_critical(self, tmp_path):
        """THE RED PROOF — the INC-41 scenario. Every artifact frozen 3 days ago: far past every
        SLA in the registry no matter which hours are active."""
        now = datetime.now(timezone.utc)
        _all_fixtures(tmp_path, (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"))
        out = _run_real_script_against(tmp_path)
        verdicts = parse_verdicts(out)
        assert {v for v, _, _ in verdicts.values()} == {STALE}
        severity, msg = classify(out, now)
        assert severity == "CRITICAL"
        assert "stg_statsapi_lineups_wide" in msg

    def test_the_inc41_victim_alone_going_stale_still_pages(self, tmp_path):
        """The realistic shape: ONE build leg dies (INC-41's `--w7b-only`) while everything else
        keeps advancing. A per-artifact SLA must not be drowned out by its healthy neighbours."""
        now = datetime.now(timezone.utc)
        _all_fixtures(tmp_path, now.strftime("%Y-%m-%d %H:%M:%S"))
        _write_fixture(tmp_path, "stg_statsapi_lineups",
                       (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"))
        out = _run_real_script_against(tmp_path)
        verdicts = parse_verdicts(out)
        assert verdicts["stg_statsapi_lineups_wide"][0] == STALE
        assert verdicts["stg_statsapi_games"][0] == OK
        severity, msg = classify(out, now)
        assert severity == "CRITICAL"
        assert "stg_statsapi_lineups_wide" in msg
        assert "PROXY" in msg, "a proxied reading must say so in the page body"

    def test_an_absent_artifact_is_warn_not_healthy(self, tmp_path):
        """NF1.7 (a): a check that could not run is not a pass. The artifact is simply not
        written — the read raises, and the verdict must be UNEVALUABLE, never OK."""
        now = datetime.now(timezone.utc)
        _all_fixtures(tmp_path, now.strftime("%Y-%m-%d %H:%M:%S"))
        (tmp_path / "stg_statsapi_lineups" / "data.parquet").unlink()
        out = _run_real_script_against(tmp_path)
        assert parse_verdicts(out)["stg_statsapi_lineups_wide"][0] == UNEVALUABLE
        severity, msg = classify(out, now)
        assert severity == "WARN"
        assert "UNVERIFIED" in msg

    def test_an_all_null_timestamp_column_is_warn_not_healthy(self, tmp_path):
        """The subtler absence: the artifact EXISTS and reads fine, but its timestamp is NULL —
        so max() returns NULL. Scoring that OK is the vacuous-anchor failure."""
        now = datetime.now(timezone.utc)
        _all_fixtures(tmp_path, now.strftime("%Y-%m-%d %H:%M:%S"))
        _write_fixture(tmp_path, "stg_statsapi_lineups", None)
        out = _run_real_script_against(tmp_path)
        assert parse_verdicts(out)["stg_statsapi_lineups_wide"][0] == UNEVALUABLE
        assert classify(out, now)[0] == "WARN"

    def test_one_unreadable_artifact_does_not_blind_the_others(self, tmp_path):
        """Per-artifact isolation: an absent table must cost only its own verdict."""
        now = datetime.now(timezone.utc)
        _all_fixtures(tmp_path, now.strftime("%Y-%m-%d %H:%M:%S"))
        (tmp_path / "stg_statsapi_lineups" / "data.parquet").unlink()
        verdicts = parse_verdicts(_run_real_script_against(tmp_path))
        assert len(verdicts) == len(REGISTRY), "every artifact must still be reported"
        assert verdicts["stg_statsapi_games"][0] == OK


# ══ 4. INC-39: the readings must be about THIS moment ══════════════════════════════════════

class TestReplayedOutputCannotBeReadAsLive:
    def test_the_script_stamps_now_on_the_success_path(self, tmp_path):
        _all_fixtures(tmp_path, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        assert parse_now(_run_real_script_against(tmp_path)) is not None

    def test_the_script_stamps_now_even_when_the_read_fails(self):
        """Stamped BEFORE the read, so the op's cross-check can never be vacuously satisfied by
        an absent line (NF1.7 (a) — the INC-39 lesson applied to the failure path)."""
        buf = io.StringIO()
        with mock.patch.object(chk, "_fetch", side_effect=RuntimeError("S3 down")), \
                mock.patch.object(sys, "argv", ["check_artifact_freshness.py"]), \
                contextlib.redirect_stdout(buf):
            assert chk.main() == 0
        out = buf.getvalue()
        assert parse_now(out) is not None
        assert parse_evaluated(out) is False

    def test_stale_output_from_an_earlier_run_is_unverified_not_critical(self, tmp_path):
        """Freshness output is the most replay-sensitive thing a monitor can parse: every number
        in a replayed stdout is individually real. It must not be read as this moment's state."""
        _all_fixtures(tmp_path, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        out = _run_real_script_against(tmp_path)
        much_later = parse_now(out) + timedelta(minutes=MAX_CLOCK_SKEW_MINUTES + 5)
        severity, msg = classify(out, much_later)
        assert severity == "WARN"
        assert "UNVERIFIED" in msg

    def test_empty_stdout_is_warn_never_silence(self):
        """The op passes "" when the subprocess dies. Silence there would recreate the exact
        INC-41 failure: a check that did not run reading as a check that passed."""
        severity, msg = classify("", datetime.now(timezone.utc))
        assert severity == "WARN"
        assert all(c.name in msg for c in REGISTRY)


# ══ 5. Registry integrity ══════════════════════════════════════════════════════════════════

class TestTheRegistryIsCoherent:
    def test_the_inc41_victim_is_registered(self):
        assert "stg_statsapi_lineups_wide" in {c.name for c in REGISTRY}

    def test_names_are_unique(self):
        names = [c.name for c in REGISTRY]
        assert len(names) == len(set(names))

    def test_every_contract_is_actionable(self):
        for c in REGISTRY:
            assert c.max_lag_minutes > 0
            assert c.ts_expr.strip() and c.cadence.strip()
            assert c.why.strip() and c.remediate.strip(), f"{c.name} has no remediation"
            if c.active_hours_utc is not None:
                assert all(0 <= h <= 23 for h in c.active_hours_utc)

    def test_the_proxy_is_declared_and_flagged(self):
        """A borrowed timestamp must be visible as borrowed — never silently substituted."""
        wide = next(c for c in REGISTRY if c.name == "stg_statsapi_lineups_wide")
        assert wide.is_proxied
        assert wide.ts_table == "stg_statsapi_lineups"
        assert not next(c for c in REGISTRY if c.name == "stg_statsapi_games").is_proxied

    def test_no_contract_reads_an_s3_mtime(self):
        """S3 LastModified is banned twice over: `aws s3 ls` prints shell-local time, and PR
        #638's atomic server-side copy refreshes the mtime even when the DATA is unchanged — so
        an mtime check would have read GREEN through INC-41 itself."""
        for c in REGISTRY:
            expr = c.ts_expr.lower()
            assert "lastmodified" not in expr and "last_modified" not in expr
            assert "filename" not in expr

    def test_odds_ingestion_ts_is_not_used_as_a_freshness_signal(self):
        """Measured 2026-08-07: `feature_pregame_game_features_raw.odds_ingestion_ts` was 40 HOURS
        stale on a healthy store — it records when the joined odds were captured, not when the
        store was built. Registering it would be a permanent false page."""
        for c in REGISTRY:
            assert "odds_ingestion_ts" not in c.ts_expr


# ══ 6. Op wiring: ALERT tier means it PAGES (E11.30) ═══════════════════════════════════════

@requires_pipeline
class TestTheOpActuallyPages:
    def _run_op(self, stdout: str):
        from pipeline.ops import daily_ingestion_ops as ops

        ctx = mock.MagicMock()
        with mock.patch.object(ops, "_run_script", return_value=stdout), \
                mock.patch("pipeline.utils.alerting.send_alert") as send:
            ops._run_artifact_freshness_check(ctx)
        return send

    def test_a_stale_artifact_pages_critical(self, tmp_path):
        now = datetime.now(timezone.utc)
        _all_fixtures(tmp_path, (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"))
        send = self._run_op(_run_real_script_against(tmp_path))
        assert send.called, "ALERT-tier op that only logs is 'detected, nobody notified' (E11.30)"
        assert send.call_args.kwargs["severity"] == "CRITICAL"

    def test_a_fresh_slate_does_not_page(self, tmp_path):
        _all_fixtures(tmp_path, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        assert not self._run_op(_run_real_script_against(tmp_path)).called

    def test_a_dead_subprocess_pages_warn_rather_than_passing_silently(self):
        from pipeline.ops import daily_ingestion_ops as ops

        ctx = mock.MagicMock()
        with mock.patch.object(ops, "_run_script", side_effect=RuntimeError("timeout")), \
                mock.patch("pipeline.utils.alerting.send_alert") as send:
            ops._run_artifact_freshness_check(ctx)
        assert send.called and send.call_args.kwargs["severity"] == "WARN"

    def test_the_op_never_raises_when_the_subprocess_dies(self):
        """ALERT tier (E11.7): a freshness monitor must never take down the daily job."""
        from pipeline.ops import daily_ingestion_ops as ops

        ctx = mock.MagicMock()
        with mock.patch.object(ops, "_run_script", side_effect=RuntimeError("boom")), \
                mock.patch("pipeline.utils.alerting.send_alert"):
            ops._run_artifact_freshness_check(ctx)  # must not raise


@requires_pipeline
class TestJobWiring:
    def test_the_daily_job_runs_the_check_downstream_of_predict(self):
        """INC-40: a monitor placed UPSTREAM of its own producer manufactures a false stale-alarm
        on the newest artifact. This must fan out from predict, which is downstream of the W7b
        and W8a builds it guards."""
        from pipeline.jobs.daily_ingestion_job import daily_ingestion_job

        deps = daily_ingestion_job.graph.dependencies
        key = next(k for k in deps if k.name == "check_artifact_freshness_op")
        upstream = {d.node for d in deps[key].values()}
        assert any("predict" in u for u in upstream), (
            f"must depend on predict (INC-40 ordering); got {upstream}")

    def test_an_off_cycle_job_exists_so_an_intraday_freeze_is_caught(self):
        """INC-41 froze at 20:08Z, hours after the daily job finished green — the daily fan-out
        alone could not have caught it before the slate was over."""
        from pipeline.jobs import all_jobs

        assert "artifact_freshness_job" in {j.name for j in all_jobs}

    def test_the_off_cycle_schedule_matches_the_writer_cadence_and_self_starts(self):
        """The W12/W9 rule: the CHECK cadence must match the WRITE cadence. And E11.23: a monitor
        that boots STOPPED and silently never fires reproduces the blind spot it closes."""
        from dagster import DefaultScheduleStatus

        from pipeline.schedules.intraday_schedules import all_intraday_schedules

        found = {s.name: s for s in all_intraday_schedules if s.name.startswith("artifact_")}
        assert set(found) == {"artifact_freshness_daytime", "artifact_freshness_overnight"}
        capture = {s.cron_schedule for s in all_intraday_schedules
                   if s.name.startswith("intraday_schedule_capture")}
        assert {s.cron_schedule for s in found.values()} == capture
        for s in found.values():
            assert s.default_status == DefaultScheduleStatus.RUNNING

    def test_the_schedules_are_in_the_monitor_health_critical_set(self):
        """A watchdog nobody watches reproduces the outage it exists to prevent."""
        from betting_ml.monitoring.monitor_health import CRITICAL_SCHEDULES

        assert {"artifact_freshness_daytime", "artifact_freshness_overnight"} <= CRITICAL_SCHEDULES
