"""INC-41 (2026-08-06) — the three things that turned one bad vendor price into a lost slate.

A MyBookie.ag h2h price of -2147483648 (INT32_MIN) made `abs()` overflow inside
`stg_oddsapi_odds`. That alone should have cost one table for one tick. It cost the evening
because of three amplifiers, each guarded here:

  1. **The failed COPY wrote to the SERVED key.** `_build_marts` did
     `COPY (...) TO '<LAKEHOUSE>/<model>/data.parquet'` — the live location. DuckDB writes the
     parquet footer LAST, so the dead write left a truncated object and readers got
     `Invalid Input Error: No magic bytes found at end of file` for ~7h. A build failure must
     leave the previous GOOD parquet in place, never a corrupt one.
  2. **Two independent rebuilds shared one try block.** When `--w3pre-only` raised, the next
     line — `--w7b-only`, the LINEUPS rebuild — was never reached. An odds-flatten failure
     silently froze the lineups the monitor reads.
  3. **The ALERT-tier handler only `log.warning`'d.** Its text predicts this outage verbatim and
     printed every 30 minutes into a step log nobody watched, while the job reported SUCCESS.

Fast-gate safe: `scripts.run_w1_lakehouse` imports cleanly, and the op-level invariants are
checked by source inspection (importing `pipeline` would crash collection — the E11.23 rule).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INTRADAY_OPS = ROOT / "pipeline" / "ops" / "intraday_ops.py"


# ── 1. a failed COPY must not touch the served key ──────────────────────────────────
class _FakeConn:
    """Raises on COPY, like the real DuckDB did on abs(INT32_MIN)."""

    def __init__(self, fail: bool):
        self.fail = fail
        self.copied_to: list[str] = []

    def execute(self, sql: str):
        m = re.search(r"TO '([^']+)'", sql)
        if m:
            self.copied_to.append(m.group(1))
        if self.fail:
            raise RuntimeError("Out of Range Error: Overflow on abs(-2147483648)")
        return self


class _FakeS3:
    def __init__(self):
        self.copied: list[tuple] = []
        self.deleted: list[str] = []

    def copy_object(self, *, Bucket, Key, CopySource):
        self.copied.append((CopySource["Bucket"], CopySource["Key"], Bucket, Key))

    def delete_object(self, *, Bucket, Key):
        self.deleted.append(f"{Bucket}/{Key}")


def _mod():
    import scripts.run_w1_lakehouse as m
    return m


def _patch_s3(monkeypatch, fake):
    import scripts.utils.lakehouse_raw_writer as w
    monkeypatch.setattr(w, "make_s3_client", lambda *a, **k: fake)


def test_a_failed_copy_never_writes_to_the_served_key(monkeypatch):
    """THE INCIDENT. The COPY dies mid-stream; the served parquet must be untouched.

    RED-proves: point the COPY back at `loc` and the served key appears in copied_to.
    """
    m = _mod()
    fake_s3 = _FakeS3()
    _patch_s3(monkeypatch, fake_s3)
    conn = _FakeConn(fail=True)
    served = f"{m.LAKEHOUSE}/stg_oddsapi_odds/data.parquet"

    with pytest.raises(RuntimeError):
        m._copy_to_s3_atomically(conn, "select 1", served, "stg_oddsapi_odds")

    assert served not in conn.copied_to, (
        "a failing COPY targeted the SERVED key — that is exactly what left a truncated, "
        "unreadable parquet in production for 7 hours"
    )
    assert fake_s3.copied == [], "nothing may be promoted when the COPY failed"


def test_a_successful_build_promotes_staging_to_the_served_key(monkeypatch):
    """The happy path must still land at the served location (else the fix breaks every build)."""
    m = _mod()
    fake_s3 = _FakeS3()
    _patch_s3(monkeypatch, fake_s3)
    conn = _FakeConn(fail=False)
    served = f"{m.LAKEHOUSE}/mart_x/data.parquet"

    m._copy_to_s3_atomically(conn, "select 1", served, "mart_x")

    assert len(fake_s3.copied) == 1, "a successful build must promote exactly once"
    _sb, _sk, dst_bucket, dst_key = fake_s3.copied[0]
    assert m._split_s3_uri(served) == (dst_bucket, dst_key), "promote must target the served key"


def test_the_staging_object_is_cleaned_up_on_both_paths(monkeypatch):
    """A leaked staging object is a slow S3 bill and a confusing artifact."""
    m = _mod()
    for fail in (True, False):
        fake_s3 = _FakeS3()
        _patch_s3(monkeypatch, fake_s3)
        conn = _FakeConn(fail=fail)
        served = f"{m.LAKEHOUSE}/mart_y/data.parquet"
        try:
            m._copy_to_s3_atomically(conn, "select 1", served, "mart_y")
        except RuntimeError:
            pass
        assert fake_s3.deleted, f"staging object not cleaned up (fail={fail})"


def test_staging_lives_outside_every_models_glob():
    """⚠️ The ext tables glob `lakehouse/<model>/**/*.parquet`.

    A staging file under that prefix would be UNIONED into the external table and DOUBLE the
    rows — the documented glob-dup landmine. This is the one way the fix could be worse than the
    bug, so it is pinned rather than assumed.
    """
    m = _mod()
    assert not m.LAKEHOUSE_STAGING.startswith(m.LAKEHOUSE + "/"), (
        "staging prefix sits INSIDE lakehouse/ — an ext-table glob would double-count it"
    )
    assert "lakehouse_staging" in m.LAKEHOUSE_STAGING


# ── 2 & 3. op-level invariants (source inspection — cannot import `pipeline`) ────────
def _ops_src() -> str:
    src = INTRADAY_OPS.read_text()
    # Strip comments: the fix DOCUMENTS the defect, so the explanation names the old shape.
    return "\n".join(line.split("#", 1)[0] for line in src.splitlines())


def test_w3pre_failure_cannot_prevent_the_lineups_rebuild():
    """The two legs must not sit in one try block.

    RED-proves: put `--w3pre-only` and `--w7b-only` back as consecutive bare statements under a
    single `try:` and the per-leg handler disappears.
    """
    src = _ops_src()
    assert "_legs_failed" in src, "per-leg failure tracking is gone — the legs are coupled again"
    # Both legs must be driven by the SAME loop construct, so neither can short-circuit the other.
    assert re.search(r'for\s+_flag,\s*_what\s+in\s*\(', src), (
        "the two rebuild legs must each be attempted independently; a shared try block means an "
        "odds-flatten failure silently skips the lineups rebuild (the INC-41 mechanism)"
    )


def test_the_intraday_refresh_failure_actually_pages():
    """ALERT-tier must call send_alert, not just log.warning (the E11.30 rule)."""
    src = _ops_src()
    assert "send_alert(" in src, (
        "the intraday lakehouse refresh failure path does not page. It printed a warning that "
        "named this exact outage every 30 min for 6.5h while the job reported SUCCESS."
    )
    assert "intraday_lakehouse_refresh_failed" in src, "the page needs a stable dedup_key"
    assert re.search(r'severity\s*=\s*["\']CRITICAL["\']', src), (
        "a frozen lineups/game-state feed stops post_lineup predictions for the rest of the "
        "slate — that is CRITICAL, not a warning"
    )
