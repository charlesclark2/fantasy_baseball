"""E11.20 phase-2a — the Snowflake-free lineup-monitor detection tick (2026-07-20).

The monitor was one of the last 24/7 warehouse wakers: every ~10-min sensor tick opened a
Snowflake session (lineups/probables joins + the state read + an UNCONDITIONAL audit-log
INSERT), so COMPUTE_WH could never suspend. Under `LINEUP_MONITOR_S3=1` the whole detection
path is DuckDB-over-S3 + DynamoDB, and a quiet tick must touch Snowflake ZERO times.

Source-inspection tests (the fast gate can't import the script's boto3/duckdb/snowflake
stack cleanly, and CI mocks all IO — the same discipline as the other cutover guards).
"""
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[2] / "scripts" / "lineup_monitor.py").read_text()


def _main_body() -> str:
    return _SRC[_SRC.index("def main() -> None:"):]


def test_flag_defaults_off():
    """Default MUST stay the byte-for-byte Snowflake path (build gated, soak, then flip)."""
    assert '_S3_MODE = os.environ.get("LINEUP_MONITOR_S3", "0") == "1"' in _SRC


def test_connection_is_lazy_in_s3_mode():
    """The wake we are killing IS the connect: in S3 mode main() must not open a session up
    front — it creates one lazily only for the trigger/audit/error paths."""
    body = _main_body()
    assert "conn = None if _S3_MODE else get_connection()" in body, (
        "main() must NOT call get_connection() unconditionally — that single call is the "
        "warehouse wake, regardless of what the tick goes on to do"
    )
    assert "def _sf_cursor():" in body


def test_quiet_tick_skips_the_audit_insert():
    """The unconditional pipeline_run_log INSERT was the 24/7 waker: on a tick that triggers
    nothing, S3 mode must skip it entirely (a triggering tick still logs — the job it fires
    is Snowflake-bound anyway)."""
    body = _main_body()
    assert "if _S3_MODE and not all_trigger_pks:" in body
    assert "Quiet tick — Snowflake untouched" in body


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


def test_parity_script_exists_and_covers_both_backends():
    parity = (Path(__file__).resolve().parents[2] / "scripts"
              / "parity_check_lineup_monitor.py").read_text()
    for fn in ("_candidates_s3", "_candidates_sf",
               "_games_with_post_lineup_s3", "_games_with_post_lineup_sf"):
        assert fn in parity, f"parity script must compare {fn}"
    assert "min_slots_filled" in parity, "parity must compare the readiness signal"
