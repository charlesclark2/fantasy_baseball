"""INC-39 — the DAILY INVOCATION path of `check_w11_tail_coverage_op`, end to end.

WHY THIS FILE EXISTS
    INC-37 wired `check_w11_tail_coverage_op` ALERT-tier, and it was covered from both ends:
    `test_w11_tail_coverage.py` tests the script's classifier, `test_w11_tail_coverage_alerting.py`
    tests the paging policy, and `test_check_ops_alerting_execution.py` executes the op — but with
    `_run_script` MONKEYPATCHED AWAY. So the link between them was never exercised: the op's argv,
    the real script's CLI accepting it, the real script's printed `[METRIC]` lines, and the real
    parsers reading them back. Every test asserted against a stdout string a TEST author wrote, so
    the whole suite would have stayed green if the script's print format and the monitor's regex
    had drifted apart.

    That untested leg is exactly where 2026-08-02's false CRITICAL landed: a
    `public_betting BUILD_GAP 0/15` page arrived for a slate whose built table held 15/15, with a
    non-date ("SMOKE-TEST") sitting in the slot the op fills with `_today()`. The numbers parsed
    fine; they were simply not this slate's, and NOTHING in the chain could tell.

WHAT IS REAL HERE (the point — these are execution guards, not source inspection)
    - the REAL `scripts/check_w11_tail_coverage.py` `main()`, with only its lakehouse read stubbed;
    - its REAL stdout, captured, never hand-written;
    - the REAL `betting_ml.monitoring.w11_tail_coverage` parsers + `classify`;
    - the REAL `_run_script` subprocess leg (Popen, drain threads, timeout, stdout return);
    - the REAL op, executed in a Dagster job.
    Only the S3/DuckDB read and SNS are stubbed, so the fast gate stays hermetic (no network).

Fast-gate-safe: imports `pipeline` ONLY inside tests guarded on the dbt manifest (E11.23).
"""

from __future__ import annotations

import importlib.util
import io
import contextlib
import stat
import sys
from pathlib import Path
from unittest import mock

import pytest

from betting_ml.monitoring.w11_tail_coverage import (
    classify,
    parse_block_coverage,
    parse_block_verdicts,
    parse_date,
    parse_evaluated,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _PROJECT_ROOT / "scripts" / "check_w11_tail_coverage.py"

# `pipeline/__init__.py` reads the dbt manifest, which is absent in the fast gate — importing it
# at module scope would crash COLLECTION rather than skip (E11.23).
_MANIFEST = _PROJECT_ROOT / "dbt" / "target" / "manifest.json"
requires_pipeline = pytest.mark.skipif(
    not _MANIFEST.exists(), reason="needs the dbt manifest to import `pipeline` (E11.23)"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("_inc39_w11_check", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


w11 = _load_script()


def _blocks(**verdict_by_block: str) -> list:
    """Build the script's OWN dataclass so the verdicts come from its real property, not a string.

    umpire/weather/public_betting each get numbers that genuinely produce the named verdict.
    """
    shapes = {
        "OK": (15, 15, 15),
        "BUILD_GAP": (15, 15, 0),
        "FEED_PENDING": (15, 0, 0),
        "PARTIAL": (15, 15, 7),
    }
    out = []
    for block, verdict in verdict_by_block.items():
        slate, raw, feature = shapes[verdict]
        cov = w11.BlockCoverage(block=block, slate_games=slate, raw_games=raw,
                                feature_games=feature)
        assert cov.verdict == verdict, f"fixture does not produce {verdict}: {cov.verdict}"
        out.append(cov)
    return out


def _real_stdout(served: str, **verdict_by_block: str) -> str:
    """Run the REAL script main() for `served` with only the lakehouse read stubbed, and return
    its REAL stdout. This is the contract under test — nothing here is hand-authored."""
    argv = ["check_w11_tail_coverage.py", "--date", served]
    buf = io.StringIO()
    with mock.patch.object(w11, "_fetch", return_value=_blocks(**verdict_by_block)), \
            mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(buf):
        rc = w11.main()
    assert rc == 0, "ALERT tier: the script must never exit non-zero without --strict"
    return buf.getvalue()


# ── 1. The script's REAL output must round-trip through the REAL monitor parsers ──────────
# This is the link the mocked-stdout tests could not cover: print format ↔ regex.

class TestTheScriptsRealOutputParses:
    def test_every_block_verdict_survives_the_round_trip(self):
        out = _real_stdout("2026-08-02", umpire="FEED_PENDING", weather="OK",
                           public_betting="BUILD_GAP")
        assert parse_evaluated(out) is True
        assert parse_block_verdicts(out) == {
            "umpire": "FEED_PENDING", "weather": "OK", "public_betting": "BUILD_GAP",
        }
        assert parse_block_coverage(out)["public_betting"] == (0, 15)

    def test_the_script_stamps_the_slate_on_the_success_path(self):
        assert parse_date(_real_stdout("2026-08-02", weather="OK")) == "2026-08-02"

    def test_the_script_stamps_the_slate_even_when_the_read_fails(self):
        """NF1.7 (a): the op's date cross-check must not be vacuously satisfiable by an absent
        line, so the stamp has to survive the exit path where nothing else is printed."""
        buf = io.StringIO()
        with mock.patch.object(w11, "_fetch", side_effect=RuntimeError("s3 unreachable")), \
                mock.patch.object(sys, "argv", ["x", "--date", "2026-08-02"]), \
                contextlib.redirect_stdout(buf):
            assert w11.main() == 0
        out = buf.getvalue()
        assert parse_date(out) == "2026-08-02"
        assert parse_evaluated(out) is False


# ── 2. THE REGRESSION — the real 2026-08-02 slate must not page ───────────────────────────
# Verdicts recorded from the live lakehouse on 2026-08-02 (laptop, AWS_DEFAULT_REGION=us-east-2):
#   2026-08-02  umpire 0/15 BUILD_GAP · weather 0/15 BUILD_GAP · public_betting 15/15 OK
#   2026-08-01  umpire 15/15 OK       · weather 14/14 OK       · public_betting 15/15 OK
# umpire+weather gapping on the CURRENT slate is the designed one-build-cycle lag, which is why
# they are judged on the prior slate. The op must be SILENT on this.

_REAL_0802 = dict(umpire="BUILD_GAP", weather="BUILD_GAP", public_betting="OK")
_REAL_0801 = dict(umpire="OK", weather="OK", public_betting="OK")


class TestTheRealIncidentSlate:
    def test_the_healthy_2026_08_02_slate_produces_no_page(self):
        severity, msg = classify(
            _real_stdout("2026-08-02", **_REAL_0802),
            _real_stdout("2026-08-01", **_REAL_0801),
            today_date="2026-08-02", prior_date="2026-08-01",
        )
        assert severity is None, f"paged on a healthy slate: {msg}"

    def test_a_genuine_same_day_public_betting_gap_still_pages_critical(self):
        """The cure must not blunt the detector INC-37 exists for."""
        severity, _ = classify(
            _real_stdout("2026-08-02", umpire="BUILD_GAP", weather="BUILD_GAP",
                         public_betting="BUILD_GAP"),
            _real_stdout("2026-08-01", **_REAL_0801),
            today_date="2026-08-02", prior_date="2026-08-01",
        )
        assert severity == "CRITICAL"


# ── 3. A leg that describes a DIFFERENT slate can never page ──────────────────────────────

class TestWrongSlateOutputCannotPage:
    def test_output_for_another_date_is_unverified_not_critical(self):
        """The 2026-08-02 shape: real BUILD_GAP numbers, wrong slate. Must not read as CRITICAL,
        and must not read as healthy either (NF1.7 (a))."""
        severity, msg = classify(
            _real_stdout("2026-07-01", umpire="OK", weather="OK", public_betting="BUILD_GAP"),
            _real_stdout("2026-08-01", **_REAL_0801),
            today_date="2026-08-02", prior_date="2026-08-01",
        )
        assert severity == "WARN"
        assert "UNVERIFIED" in msg
        assert "2026-07-01" in msg and "2026-08-02" in msg

    def test_a_human_label_caller_is_unaffected(self):
        """`classify`'s date args default to prose ("today"); the cross-check must stay inert
        there rather than declaring every such call a wrong slate."""
        severity, _ = classify(_real_stdout("2026-08-02", **_REAL_0802),
                               _real_stdout("2026-08-01", **_REAL_0801))
        assert severity is None


# ── 4. THE SUBPROCESS LEG — the op's real `_run_script`, really shelling out ───────────────
# The link no existing test touched. A stub script stands in for the lakehouse read (the fast gate
# does no IO), but everything around it is production code: argv construction, Popen, the drain
# threads, the timeout wiring, the returned stdout, the parsers, classify, and the page decision.

_STUB = '''\
import sys
# Assert the op handed us EXACTLY the argv contract the real script's CLI accepts.
assert sys.argv[1] == "--date", sys.argv
served = sys.argv[2]
assert len(served) == 10 and served[4] == "-" and served[7] == "-", f"not an ISO date: {served!r}"
print(f"[METRIC] w11_tail_date={served}")
print("[METRIC] w11_tail_evaluated=1")
for line in open(%(replay)r).read().splitlines():
    if line.startswith(served + "|"):
        print(line.split("|", 1)[1])
'''


@pytest.fixture
def stub_scripts_dir(tmp_path):
    """A SCRIPTS_DIR whose check script replays recorded real verdicts, keyed by the --date it
    is given — so the op's two legs genuinely disagree, as they do in production."""
    replay = tmp_path / "replay.txt"
    lines = []
    for served, verdicts in (("2026-08-02", _REAL_0802), ("2026-08-01", _REAL_0801)):
        for block, verdict in verdicts.items():
            n = 0 if verdict == "BUILD_GAP" else 15
            lines.append(f"{served}|[METRIC] w11_tail_{block}_covered={n}/15 verdict={verdict}")
    replay.write_text("\n".join(lines) + "\n")

    script = tmp_path / "check_w11_tail_coverage.py"
    script.write_text(_STUB % {"replay": str(replay)})
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return tmp_path, replay


@requires_pipeline
class TestTheOpRunsTheRealSubprocessLeg:
    @staticmethod
    def _execute(monkeypatch, scripts_dir):
        from dagster import DagsterInstance, in_process_executor, job
        from pipeline.ops import daily_ingestion_ops as dio
        from pipeline.utils import alerting

        monkeypatch.setattr(dio, "SCRIPTS_DIR", str(scripts_dir))
        # `_run_script` runs with cwd=APP_DIR ("/app", the box layout), which does not exist off
        # the box — leave it and every subprocess dies before exec, which the op reports as
        # UNVERIFIED/WARN. That is a plausible-looking result, and it is how two of these tests
        # first passed WITHOUT the subprocess ever running.
        monkeypatch.setattr(dio, "APP_DIR", str(_PROJECT_ROOT))
        monkeypatch.setattr(dio, "_today", lambda: "2026-08-02")
        monkeypatch.setattr(dio, "_one_day_ago", lambda: "2026-08-01")
        mock_alert = mock.MagicMock()
        monkeypatch.setattr(alerting, "send_alert", mock_alert)

        @job(executor_def=in_process_executor)
        def _j():
            dio.check_w11_tail_coverage_op()

        assert _j.execute_in_process(instance=DagsterInstance.ephemeral()).success
        return mock_alert

    @staticmethod
    def _assert_subprocess_really_ran(monkeypatch, scripts_dir):
        """Both legs must have produced parseable output. Without this, "the op stayed silent"
        is indistinguishable from "the subprocess never started" — and a guard that passes when
        its subject never ran is the vacuous-anchor class (NF1.7 (a))."""
        from pipeline.ops import daily_ingestion_ops as dio

        captured = []
        real = dio._run_script
        monkeypatch.setattr(
            dio, "_run_script",
            lambda ctx, s, a=None, **k: captured.append(real(ctx, s, a, **k)) or captured[-1],
        )
        return captured

    def test_the_op_goes_silent_on_the_real_2026_08_02_slate(self, monkeypatch, stub_scripts_dir):
        """THE INCIDENT REGRESSION, through the real subprocess leg: the op must NOT page on the
        slate that produced the 2026-08-02 CRITICAL."""
        scripts_dir, _ = stub_scripts_dir
        captured = self._assert_subprocess_really_ran(monkeypatch, scripts_dir)
        assert self._execute(monkeypatch, scripts_dir).call_count == 0
        # ...and prove the silence was earned by a real, parsed read of BOTH slates.
        assert len(captured) == 2
        assert [parse_date(o) for o in captured] == ["2026-08-02", "2026-08-01"]
        assert all(parse_evaluated(o) is True for o in captured)
        assert parse_block_verdicts(captured[0])["public_betting"] == "OK"

    def test_the_op_still_pages_critical_through_the_real_leg_on_a_true_gap(
        self, monkeypatch, stub_scripts_dir
    ):
        scripts_dir, replay = stub_scripts_dir
        replay.write_text(
            replay.read_text().replace(
                "2026-08-02|[METRIC] w11_tail_public_betting_covered=15/15 verdict=OK",
                "2026-08-02|[METRIC] w11_tail_public_betting_covered=0/15 verdict=BUILD_GAP",
            )
        )
        mock_alert = self._execute(monkeypatch, scripts_dir)
        assert mock_alert.call_count == 1
        assert mock_alert.call_args.kwargs["severity"] == "CRITICAL"

    def test_a_leg_reporting_another_slate_cannot_page_critical_through_the_real_leg(
        self, monkeypatch, stub_scripts_dir
    ):
        """The 2026-08-02 shape end to end: the subprocess returns a real-looking BUILD_GAP whose
        stamped slate is not the one the op asked for."""
        scripts_dir, replay = stub_scripts_dir
        stub = scripts_dir / "check_w11_tail_coverage.py"
        stub.write_text(
            stub.read_text().replace(
                'print(f"[METRIC] w11_tail_date={served}")',
                'print("[METRIC] w11_tail_date=2026-07-01")',
            ).replace('verdict=OK', 'verdict=BUILD_GAP')
        )
        replay.write_text(
            replay.read_text().replace(
                "2026-08-02|[METRIC] w11_tail_public_betting_covered=15/15 verdict=OK",
                "2026-08-02|[METRIC] w11_tail_public_betting_covered=0/15 verdict=BUILD_GAP",
            )
        )
        mock_alert = self._execute(monkeypatch, scripts_dir)
        assert mock_alert.call_args.kwargs["severity"] == "WARN", "a wrong slate paged CRITICAL"

    def test_the_op_passes_a_finite_timeout_to_the_subprocess(self, monkeypatch,
                                                              stub_scripts_dir):
        """INC-32: an un-timed-out subprocess on a daemon path wedges the worker thread. Asserted
        on the real call, not by reading the source."""
        from pipeline.ops import daily_ingestion_ops as dio

        scripts_dir, _ = stub_scripts_dir
        seen = []
        real = dio._run_script

        def _spy(context, script, args=None, **kwargs):
            seen.append(kwargs.get("timeout"))
            return real(context, script, args, **kwargs)

        monkeypatch.setattr(dio, "_run_script", _spy)
        self._execute(monkeypatch, scripts_dir)
        assert seen and all(isinstance(t, int) and t > 0 for t in seen), seen


# ── 5. The op must never invent a date the script cannot parse ────────────────────────────

@requires_pipeline
def test_the_op_asks_for_real_iso_dates(monkeypatch):
    """`_today()`/`_one_day_ago()` feed the script's `date.fromisoformat`. A non-date there is
    how a synthetic universe reaches a real page — the stub in §4 asserts the format, this pins
    the producers themselves."""
    import datetime as _dt

    from pipeline.ops import daily_ingestion_ops as dio

    for fn in (dio._today, dio._one_day_ago):
        _dt.date.fromisoformat(fn())
