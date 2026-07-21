"""E11.20 phase-2a — the monthly_schedule raw writer's S3 dual-write + retention.

`scripts/ingest_statsapi.py::run_schedule` gains a gated Snowflake→S3 dual-write so the 30-min
capture tick's SCHEDULE leg stops reading Snowflake (it retires the
`export_odds_raw_to_s3 --source monthly_schedule` bridge). Design:
docs/monthly_schedule_s3_flip_design.md.

These tests exercise the REAL writer (`write_raw_rows_s3` → arrow → parquet) + the REAL
`prune_same_month_partitions` against an in-memory fake S3, so they validate the exact on-disk S3
contract (2 columns, `json_field` serialized to a JSON string, `dt=<ingestion date>` partition) and
the INC-20 latest-per-month retention — not just that some function was called. All IO is faked; no
network, no boto3 creds, no Snowflake.
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import scripts.ingest_statsapi as isa            # noqa: E402
import utils.lakehouse_raw_writer as lrw         # noqa: E402  — the SAME module run_schedule imports

_RAW_PREFIX = lrw.RAW_PREFIX
_SRC = "monthly_schedule"


class FakeS3:
    """Minimal S3 stand-in: stores object bodies, supports paginate/delete/put — enough for
    write_raw_rows_s3 (put + overwrite_partition delete) and prune (list + delete)."""

    def __init__(self, keys: dict[str, bytes] | None = None):
        self.objects: dict[str, bytes] = dict(keys or {})
        self.deleted: list[str] = []

    def get_paginator(self, _op):
        return self

    def paginate(self, Bucket, Prefix):  # noqa: N803 — boto3 kwarg names
        yield {"Contents": [{"Key": k} for k in sorted(self.objects) if k.startswith(Prefix)]}

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.objects.pop(Key, None)
        self.deleted.append(Key)

    def put_object(self, Bucket, Key, Body, **_kw):  # noqa: N803
        self.objects[Key] = Body


def _part_key(dt: str, name: str = "part-abc.parquet") -> str:
    return f"{_RAW_PREFIX}/{_SRC}/dt={dt}/{name}"


# ── prune_same_month_partitions ────────────────────────────────────────────────────────────

def test_prune_collapses_same_month_keeps_other_months_and_nullts():
    fake = FakeS3({
        _part_key("2026-07-18"): b"a",
        _part_key("2026-07-19"): b"b",
        _part_key("2026-07-20"): b"c",   # keep_dt
        _part_key("2026-06-30"): b"d",   # PRIOR month — must survive
        _part_key("__nullts__"): b"e",   # sentinel — must survive
    })
    deleted = lrw.prune_same_month_partitions(_SRC, "2026-07-20", s3_client=fake)

    assert deleted == ["2026-07-18", "2026-07-19"]
    surviving = {k for k in fake.objects}
    assert _part_key("2026-07-20") in surviving      # keep_dt kept
    assert _part_key("2026-06-30") in surviving      # prior month untouched
    assert _part_key("__nullts__") in surviving      # sentinel never matched


def test_prune_is_noop_when_month_already_collapsed():
    fake = FakeS3({_part_key("2026-07-20"): b"c", _part_key("2026-06-30"): b"d"})
    assert lrw.prune_same_month_partitions(_SRC, "2026-07-20", s3_client=fake) == []
    assert len(fake.objects) == 2


def test_prune_rejects_a_non_date_keep_dt():
    with pytest.raises(ValueError):
        lrw.prune_same_month_partitions(_SRC, "__nullts__", s3_client=FakeS3())


# ── run_schedule: mode gating + the exact S3 contract ──────────────────────────────────────

@pytest.fixture
def _patched(monkeypatch):
    """Patch the network + the S3 client factory; capture SF inserts. Returns (fake_s3, sf_calls)."""
    payloads = {"2026-07": {"totalGames": 3, "dates": [{"games": []}]}}

    def fake_fetch(month_start, month_end):
        return payloads[month_start.strftime("%Y-%m")]

    sf_calls: list = []

    def fake_insert(conn, ms, me, cnt, payload, reason):
        sf_calls.append((ms, me, cnt, reason))

    fake = FakeS3()
    monkeypatch.setattr(isa, "fetch_schedule", fake_fetch)
    monkeypatch.setattr(isa, "insert_month", fake_insert)
    monkeypatch.setattr(isa.time, "sleep", lambda *_a, **_k: None)
    # run_schedule calls write_raw_rows_s3/prune WITHOUT an s3_client → they build one via
    # _make_s3_client. Patch that factory on the module so the real writer runs against the fake.
    monkeypatch.setattr(lrw, "_make_s3_client", lambda: fake)
    monkeypatch.setattr(lrw, "make_s3_client", lambda: fake)
    return fake, sf_calls


def _only_parquet(fake: FakeS3) -> tuple[str, bytes]:
    items = [(k, v) for k, v in fake.objects.items() if k.endswith(".parquet")]
    assert len(items) == 1, f"expected exactly one parquet, got {[k for k, _ in items]}"
    return items[0]


def test_snowflake_mode_writes_no_s3(monkeypatch, _patched):
    fake, sf_calls = _patched
    monkeypatch.setenv("W11_RAW_WRITE_MODE", "snowflake")

    isa.run_schedule(object(), isa.date(2026, 7, 20), isa.date(2026, 7, 20))

    assert sf_calls, "snowflake mode must still INSERT to Snowflake"
    assert not fake.objects, "snowflake mode must write NOTHING to S3"


def test_both_mode_writes_sf_and_the_exact_s3_contract(monkeypatch, _patched):
    fake, sf_calls = _patched
    monkeypatch.setenv("W11_RAW_WRITE_MODE", "both")

    isa.run_schedule(object(), isa.date(2026, 7, 20), isa.date(2026, 7, 20))

    assert sf_calls, "both mode must INSERT to Snowflake"
    key, body = _only_parquet(fake)
    # dt= partition is the ingestion date (today, UTC) — an ISO YYYY-MM-DD under the source prefix.
    assert key.startswith(f"{_RAW_PREFIX}/{_SRC}/dt=")
    dt = key.split("/dt=", 1)[1].split("/", 1)[0]
    assert len(dt) == 10 and dt[4] == "-" and dt[7] == "-"
    # Exact 2-column contract, and json_field serialized to a JSON STRING (matches the bridge's
    # to_json(json_field)) — a downstream flatten does from_json on it.
    table = pq.read_table(io.BytesIO(body))
    assert set(table.column_names) == {"ingestion_ts", "json_field"}
    jf = table.column("json_field").to_pylist()[0]
    assert isinstance(jf, str)
    assert json.loads(jf)["totalGames"] == 3
    ts = table.column("ingestion_ts").to_pylist()[0]
    assert isinstance(ts, str) and ts[:10] == dt   # partition date == the stamp's date


def test_s3_mode_writes_s3_without_touching_snowflake(monkeypatch, _patched):
    fake, sf_calls = _patched
    monkeypatch.setenv("W11_RAW_WRITE_MODE", "s3")

    isa.run_schedule(None, isa.date(2026, 7, 20), isa.date(2026, 7, 20))

    assert sf_calls == [], "s3 mode must NOT insert to Snowflake"
    assert _only_parquet(fake), "s3 mode must write the S3 parquet"


def test_intraday_rewrite_overwrites_the_day_and_prunes_earlier_same_month(monkeypatch, _patched):
    """Two fires same UTC day → one partition (overwrite); an earlier same-month partition is
    pruned; a prior-month partition survives. (The live INC-20 retention.)"""
    fake, _sf = _patched
    monkeypatch.setenv("W11_RAW_WRITE_MODE", "s3")
    # Seed an earlier same-month snapshot + a prior-month one.
    fake.objects[_part_key("2026-07-01")] = b"old-july"
    fake.objects[_part_key("2026-06-30")] = b"june"

    isa.run_schedule(None, isa.date(2026, 7, 20), isa.date(2026, 7, 20))
    parquet_dts = {k.split("/dt=", 1)[1].split("/", 1)[0]
                   for k in fake.objects if k.endswith(".parquet")}
    # The seeded earlier-same-month raw partition is pruned; the prior month survives.
    assert _part_key("2026-07-01") not in fake.objects
    assert _part_key("2026-06-30") in fake.objects           # prior month untouched
    # Exactly one partition remains in the WRITE month (today's), i.e. same-month collapsed to one.
    today_dt = next(d for d in parquet_dts if d != "2026-06-30")
    same_month = {d for d in parquet_dts if d[:7] == today_dt[:7]}
    assert same_month == {today_dt}


# ── main(): the Snowflake connection is conditional on the SF leg ──────────────────────────

@pytest.fixture
def _no_run(monkeypatch):
    monkeypatch.setattr(isa, "run_schedule", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv",
                        ["ingest_statsapi.py", "schedule",
                         "--start-date", "2026-07-20", "--end-date", "2026-07-20"])


def test_main_opens_no_snowflake_session_in_s3_mode(monkeypatch, _no_run):
    monkeypatch.setenv("W11_RAW_WRITE_MODE", "s3")
    opened = []
    monkeypatch.setattr(isa, "get_snowflake_connection", lambda *a, **k: opened.append(1))
    isa.main()
    assert opened == [], "s3 mode must not connect to Snowflake (the connect IS the wake)"


def test_main_connects_in_snowflake_mode(monkeypatch, _no_run):
    monkeypatch.setenv("W11_RAW_WRITE_MODE", "snowflake")

    class _Conn:
        def close(self):
            pass

    opened = []
    monkeypatch.setattr(isa, "get_snowflake_connection", lambda *a, **k: (opened.append(1) or _Conn()))
    isa.main()
    assert opened == [1], "snowflake mode must connect exactly once"
