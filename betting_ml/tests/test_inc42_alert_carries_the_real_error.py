"""INC-42 — the alert body must DISCRIMINATE between failure causes.

The defect: `intraday_ops` recorded a failed leg as `str(exc)[:300]`, but `_run_script` raises with
the child's whole traceback, whose payload is at the TAIL. So the page carried the traceback header
and the first frames, no DuckDB error at all, and every distinct cause produced byte-identical text.

These guards are written so each one FAILS on the pre-fix source. The load-bearing one is
`test_two_different_causes_do_not_page_identically` — a length assertion alone would pass on a
truncation that is short *and* useless.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from betting_ml.monitoring.alert_text import DEFAULT_LIMIT, exc_digest

_INTRADAY_OPS = Path(__file__).resolve().parents[2] / "pipeline" / "ops" / "intraday_ops.py"

# The real shape: `_run_script` raises f"{script} failed (exit {rc})\n{stderr}", where stderr is the
# child's traceback. Everything before the final line is noise that a head-slice would preserve.
_PREAMBLE = (
    "timestamp-stringify DESCRIBE failed — REFUSING to COPY unwrapped (an unwrapped COPY "
    "would risk a binary parquet timestamp that Snowflake's external table misreads per-row: "
    "the year-~56M EOVERFLOW / W8a 24h serving outage). Most common cause: a date function or "
    "interval arithmetic applied to a column an upstream wrap stringified to ISO VARCHAR — "
    "cast that column ::date at the use site. Underlying DuckDB binder error: "
)


def _traceback_like(real_error: str) -> str:
    """A faithful stand-in for what `_run_script` actually puts in the exception."""
    frames = "\n".join(
        f'  File "/app/scripts/run_w1_lakehouse.py", line {n}, in _frame_{n}\n    do_something()'
        for n in (2831, 2449, 1057, 672, 583)
    )
    return (
        "run_w1_lakehouse.py failed (exit 1)\n"
        "Traceback (most recent call last):\n"
        f"{frames}\n"
        f"RuntimeError: {_PREAMBLE}{real_error}\n"
    )


def test_the_real_error_survives_the_digest():
    real = "HTTPException: HTTP GET error reading 's3://…/part-abc.parquet' (HTTP 404 Not Found)"
    assert real in exc_digest(_traceback_like(real))


def test_two_different_causes_do_not_page_identically():
    """⭐ The load-bearing guard. A head slice returns the SAME text for every cause — that is not
    a short diagnosis, it is no diagnosis (the `curl -f`/301 non-discriminating-output class)."""
    race = _traceback_like("HTTPException: … (HTTP 404 Not Found)")
    throttle = _traceback_like("HTTPException: … (HTTP 503 SlowDown)")
    binder = _traceback_like("Binder Error: No function matches year(VARCHAR)")

    digests = {exc_digest(t) for t in (race, throttle, binder)}
    assert len(digests) == 3, "the digest collapses distinct causes to identical text"

    # And prove the pre-fix behaviour really does collapse them (so this guard is not vacuous).
    assert len({str(t)[:300] for t in (race, throttle, binder)}) == 1


def test_the_digest_respects_its_budget_and_names_the_elision():
    out = exc_digest(_traceback_like("X" * 4000))
    assert len(out) <= DEFAULT_LIMIT
    assert re.search(r"chars elided", out), "a dropped middle must be visible, never silent"


def test_a_short_message_is_passed_through_verbatim():
    assert exc_digest(Exception("boom")) == "boom"


def test_head_is_kept_so_the_script_and_exit_code_survive():
    out = exc_digest(_traceback_like("Binder Error: nope"))
    assert out.startswith("run_w1_lakehouse.py failed (exit 1)")


@pytest.mark.parametrize("marker", ["exc_digest(exc)"])
def test_intraday_ops_uses_the_digest_and_not_a_head_slice(marker):
    """Source guard. Strip comments first — INC-38: prose must not be able to satisfy a guard."""
    src = _INTRADAY_OPS.read_text()
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert marker in code
    assert not re.search(r"str\(exc\)\[:\d+\]", code), "a head slice of a traceback is the INC-42 defect"
