"""E11.20 phase-2a — the Snowflake-free lineup-monitor detection tick (2026-07-20).

The monitor was one of the last 24/7 warehouse wakers: every ~10-min sensor tick opened a
Snowflake session (lineups/probables joins + the state read + an UNCONDITIONAL audit-log
INSERT), so COMPUTE_WH could never suspend. Under `LINEUP_MONITOR_S3=1` the whole detection
path is DuckDB-over-S3 + DynamoDB, and a quiet tick must touch Snowflake ZERO times.

E11.24 (2026-08-06) finishes the job: the ONE surviving Snowflake touch — the pipeline_run_log
audit INSERT, which phase-2a kept on triggering ticks — moved to DynamoDB, so the invariant is
now unconditional (NO tick opens a session) rather than conditional.

Mostly source-inspection tests, because the wiring being guarded IS structural (which branch
calls what) and CI mocks all IO — the same discipline as the other cutover guards. The E11.24
audit-path guards at the bottom are BEHAVIOURAL: the script imports cleanly in the fast gate
(only logging/os/datetime/snowflake.connector at module scope — boto3 and duckdb are imported
inside the functions), so that path can be executed for real against a fake DynamoDB Table.
"""
from pathlib import Path

import pytest

from scripts.lineup_monitor import (
    TASK,
    _AUDIT_SK_PREFIX,
    _STATE_SK_PREFIX,
    _record_audit_dynamo,
    build_audit_item,
)

_SRC = (Path(__file__).resolve().parents[2] / "scripts" / "lineup_monitor.py").read_text()


def _main_body() -> str:
    return _SRC[_SRC.index("def main() -> None:"):]


def _main_code() -> str:
    """main() with COMMENT lines stripped.

    INC-38's lesson, and it fired for real while writing the E11.24 guards below: a
    source-inspection assertion that reads comments is satisfiable (or breakable) by PROSE.
    Here the explanatory comment "so `get_connection()` is unreachable" made the call-site
    COUNT read 2. Counting call sites must see CODE only — otherwise the guard measures the
    documentation, and the failure mode runs both ways (a comment can also make a deleted
    call site look present)."""
    return "\n".join(
        ln for ln in _main_body().splitlines() if not ln.lstrip().startswith("#")
    )


def test_flag_defaults_off():
    """Default MUST stay the byte-for-byte Snowflake path (build gated, soak, then flip)."""
    assert '_S3_MODE = os.environ.get("LINEUP_MONITOR_S3", "0") == "1"' in _SRC


def test_connection_is_never_opened_in_s3_mode():
    """The wake we are killing IS the connect. Phase-2a made it LAZY (one session, only if a
    trigger/audit/error fired); E11.24 makes it NEVER — with the audit sink on DynamoDB there
    is no remaining S3-mode path to Snowflake, so `get_connection()` must appear exactly once
    in main(), inside the `None if _S3_MODE else …` guard. A second call site would be a lazy
    re-open, i.e. the loophole the census billed us for."""
    code = _main_code()
    assert "conn = None if _S3_MODE else get_connection()" in code, (
        "main() must NOT call get_connection() unconditionally — that single call is the "
        "warehouse wake, regardless of what the tick goes on to do"
    )
    assert code.count("get_connection()") == 1, (
        "a second get_connection() in main() re-arms the lazy-open path E11.24 removed"
    )
    assert "_sf_cursor" not in code, (
        "the lazy-cursor helper must be gone — while it exists, 'the tick never touches "
        "Snowflake' is only a claim about today's call sites, not a structural property"
    )


def test_no_tick_writes_the_audit_log_to_snowflake():
    """E11.24 — SUPERSEDES the phase-2a `test_quiet_tick_skips_the_audit_insert` guard, which
    asserted only that a QUIET tick skipped the INSERT. The census measured the surviving
    TRIGGERING-tick INSERT still paying the provisioning wait (it is the FIRST statement of
    the trigger sequence, so it buys the resume the later dbt step then rides for free), so
    the sink moved to DynamoDB and the invariant is now unconditional: NO tick, quiet or
    triggering, may INSERT into pipeline_run_log. Strictly stronger than what it replaces."""
    assert "pipeline_run_log" not in _main_code(), (
        "main() still references pipeline_run_log — the audit write must go to DynamoDB "
        "(_record_audit_dynamo), never to COMPUTE_WH"
    )


def test_all_three_read_paths_are_branched():
    body = _main_body()
    for s3_fn, sf_fn in [
        ("_candidates_s3(today)", "_candidates_sf(cur, today)"),
        ("_already_triggered_dynamo(today)", "_already_triggered_sf(cur, today)"),
        ("_games_with_post_lineup_s3(today)", "_games_with_post_lineup_sf(cur, today)"),
    ]:
        assert s3_fn in body, f"missing S3 branch: {s3_fn}"
        assert sf_fn in body, f"missing Snowflake branch: {sf_fn}"


def test_state_writes_branch_to_dynamo():
    """Both the new-trigger insert and the pitcher-change update must route to DynamoDB in
    S3 mode — a leftover SF write would re-wake the warehouse on every trigger."""
    body = _main_body()
    assert body.count("_record_trigger_dynamo(today, pk, home_starter, away_starter)") == 2


def test_finally_tolerates_never_opened_connection():
    """In S3 mode the session may never exist — an unguarded cur.close() would raise on the
    very ticks the flag is supposed to make cheapest."""
    body = _main_body()
    assert "if cur is not None:" in body and "if conn is not None:" in body


def test_s3_reads_route_through_the_delta_aware_registrar():
    """Phase-1.5 lesson: a hardcoded lakehouse parquet glob breaks the moment a table moves
    to Delta (the 2026-07-20 P0). The monitor's reads must use the shared registrar."""
    assert "register_lakehouse_views" in _SRC
    for table in ("stg_statsapi_lineups_wide", "stg_statsapi_probable_pitchers",
                  "daily_model_predictions"):
        assert f"lakehouse/{table}" not in _SRC, f"hardcoded parquet path for {table}"


def test_readiness_gate_slot_count_preserved_in_s3_query():
    """The INC-32 readiness signal (MIN over both sides of filled slots) must be computed
    identically on the S3 path — a drift changes WHICH games are held vs scored."""
    s3_fn = _SRC[_SRC.index("def _candidates_s3"):_SRC.index("def _games_with_post_lineup_s3")]
    assert "MIN({slots})" in s3_fn
    assert "HAVING COUNT(DISTINCT home_away) = 2" in s3_fn
    assert "range(1, _FULL_LINEUP_SLOTS + 1)" in s3_fn


def test_lineup_predict_mirrors_predictions_to_s3():
    """THE FLIP BLOCKER (found by the parity gate 2026-07-20, SF=9 post_lineup vs S3=0):
    lineup_predict must export daily_model_predictions to S3 after scoring, like
    predict_today_morning always has. Without it the monitor's Step-2b reads a stale ZERO
    under LINEUP_MONITOR_S3=1 and re-triggers every game on every tick (the INC-32
    infinite re-trigger loop). Serving is unaffected — the intraday serve reads Snowflake."""
    ops = (Path(__file__).resolve().parents[2] / "pipeline" / "ops" / "sensor_ops.py").read_text()
    body = ops[ops.index("def lineup_predict"):]
    body = body[:body.index("\n@op")]
    assert '"export_w6_raw_to_s3.py", ["--table", "daily_model_predictions"]' in body, (
        "lineup_predict must mirror post_lineup rows to S3 or the LINEUP_MONITOR_S3 flip "
        "re-arms the infinite re-trigger loop"
    )
    assert "context.log.warning" in body, "the mirror must be ALERT-tier, not a silent swallow"


def test_parity_script_exists_and_covers_both_backends():
    parity = (Path(__file__).resolve().parents[2] / "scripts"
              / "parity_check_lineup_monitor.py").read_text()
    for fn in ("_candidates_s3", "_candidates_sf",
               "_games_with_post_lineup_s3", "_games_with_post_lineup_sf"):
        assert fn in parity, f"parity script must compare {fn}"
    assert "min_slots_filled" in parity, "parity must compare the readiness signal"


# ── E11.24 — the audit write moves off COMPUTE_WH (2026-08-06) ─────────────────────────────
# The last Snowflake touch on the tick was the pipeline_run_log audit INSERT. It is now a
# DynamoDB put on the same `pk="ops"` table the state + retry-counter items already use.
#
# These are BEHAVIOURAL, not source-inspection: the audit path is executed for real against a
# fake Table. A source-inspection guard here would only restate the code.


class _FakeTable:
    """Records put_item calls. `explode=True` makes every write raise, to prove fail-open."""

    def __init__(self, explode: bool = False):
        self.items: list[dict] = []
        self.explode = explode

    def put_item(self, Item):  # noqa: N803 — boto3's kwarg name
        if self.explode:
            raise RuntimeError("dynamo is down")
        self.items.append(Item)


@pytest.fixture
def fake_table(monkeypatch):
    t = _FakeTable()
    monkeypatch.setattr("scripts.lineup_monitor._state_table", lambda: t)
    return t


def test_audit_sk_prefix_cannot_collide_with_the_state_query():
    """THE CORRECTNESS GUARD, not a cost one. `_already_triggered_dynamo` reads state with
    begins_with(_STATE_SK_PREFIX + date + '#') on the SAME pk. If the audit prefix were a
    string prefix of the state prefix (or vice versa) every audit row would be returned as an
    already-triggered GAME — the monitor would then skip real games (they'd look triggered)
    and the sk tail would fail to parse as a game_pk. Cheap to assert, silent and slate-wide
    if wrong."""
    assert not _AUDIT_SK_PREFIX.startswith(_STATE_SK_PREFIX)
    assert not _STATE_SK_PREFIX.startswith(_AUDIT_SK_PREFIX)
    # And the concrete keys the two writers actually emit must not match each other's query.
    audit_sk = build_audit_item("2026-08-06", "2026-08-06T18:00:00+00:00", "SUCCESS", 3)["sk"]
    assert not audit_sk.startswith(f"{_STATE_SK_PREFIX}2026-08-06#")


def test_audit_item_carries_every_pipeline_run_log_column():
    """The runbook read must be a RENAME, not a re-interpretation — a dropped column is a
    silently degraded audit log that still looks like it is working."""
    item = build_audit_item("2026-08-06", "2026-08-06T18:00:00+00:00", "SUCCESS", 3)
    assert item["pk"] == "ops"
    assert item["task_name"] == TASK
    assert item["run_ts"] == "2026-08-06T18:00:00+00:00"
    assert item["status"] == "SUCCESS"
    assert item["rows_affected"] == 3
    assert item["run_date"] == "2026-08-06"
    # A SUCCESS row carries no error_message, exactly like the old NULL column.
    assert "error_message" not in item


def test_audit_log_is_append_only_across_ticks():
    """Unlike the state items (one per game, last-write-wins on a fixed key) every tick must
    survive as its own record — a fixed sk would silently keep only the day's last tick."""
    a = build_audit_item("2026-08-06", "2026-08-06T18:00:00+00:00", "SUCCESS", 0)
    b = build_audit_item("2026-08-06", "2026-08-06T18:10:00+00:00", "SUCCESS", 2)
    assert a["sk"] != b["sk"]


def test_failure_record_is_written_and_truncated():
    item = build_audit_item("2026-08-06", "2026-08-06T18:00:00+00:00", "FAILED", 0, "x" * 900)
    assert item["status"] == "FAILED"
    assert len(item["error_message"]) == 400, "error_message must stay within the old 400 cap"


def test_record_audit_writes_to_dynamo_not_snowflake(fake_table):
    """The whole point: the audit write must reach DynamoDB. If this ever regressed to a
    Snowflake INSERT the fake Table would simply never be called."""
    _record_audit_dynamo("2026-08-06", "SUCCESS", 2)
    assert len(fake_table.items) == 1
    assert fake_table.items[0]["task_name"] == TASK
    assert fake_table.items[0]["rows_affected"] == 2


def test_record_audit_fails_open(monkeypatch, caplog):
    """A write-only diagnostic must never break detection — and must NOT fall back to
    Snowflake, which would re-arm the waker on exactly the flaky days it fires most."""
    monkeypatch.setattr("scripts.lineup_monitor._state_table", lambda: _FakeTable(explode=True))
    with caplog.at_level("WARNING"):
        _record_audit_dynamo("2026-08-06", "SUCCESS", 1)   # must not raise
    assert any("audit write failed" in r.message for r in caplog.records), (
        "a swallowed audit failure must still be LOUD (E11.7: never a silent pass)"
    )


def test_audit_write_passes_no_explicit_aws_credentials():
    """AKID landmine: the box has no AWS_ACCESS_KEY_ID, so passing os.environ.get(...) would
    hand boto3 None and DISABLE the instance-role credential chain."""
    assert 'boto3.resource("dynamodb")' in _SRC
    assert "aws_access_key_id" not in _SRC


def test_snowflake_path_still_commits_its_state_writes():
    """The commit used to ride along with the audit INSERT. Removing that INSERT without an
    explicit commit would make the flag-OFF ROLLBACK path silently stop recording triggers in
    lineup_monitor_state — a rollback lever that is itself broken is worse than no lever."""
    body = _main_body()
    assert "if conn is not None:\n            conn.commit()" in body
