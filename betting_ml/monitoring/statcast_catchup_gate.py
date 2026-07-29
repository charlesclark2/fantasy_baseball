"""E11.24 — the statcast catch-up NO-OP GATE (a literal-zero-Snowflake wake source).

THE FINDING (2026-07-29 wake census). `statcast_freshness_sensor` fires
`statcast_catchup_job` on an **hourly** ``run_key`` from 04:00 ET until yesterday's Statcast
publishes. On a normal morning Savant lands around 12:00–13:00 UTC, so the job fires ~6 times
and **five of those runs land nothing** — yet each one still executes the full chain:
two `refresh_w1_external_tables.py` passes (an `ALTER EXTERNAL TABLE … REFRESH` storm), the
bullpen-posterior dbt build, the three sequential-posterior writers, `compute_elo`, the umpire
feature rebuild, `predict_today_morning` and a serving write.

That is the *mechanism* behind the census's "hourly `CREATE TABLE IF NOT EXISTS …
team_elo_history` — 14% of remaining resumes, 08:00–13:00, NOT the daily op". The DDL was the
visible symptom; the redundant re-fire is the cause, and it multiplies every Snowflake touch in
the chain by ~6.

⭐ WHY A GATE IS SAFE. The whole chain exists to fold *newly landed pitches* into today's slate.
If the ingest landed no pitches for yesterday, nothing downstream can produce a different
answer than it did an hour ago — the work is definitionally a no-op. The sensor keeps firing
on the next hourly ``run_key``, so the first fire that actually lands data runs the full chain.
The gate therefore removes only work that cannot change an output; it never removes a retry.

Kept in ``betting_ml`` (not ``pipeline``) on purpose: fast-gate tests may not import
``pipeline`` (it reads the dbt manifest at import, which is absent in CI).
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

# Default-OFF cutover lever. The catch-up chain contains `predict_today_morning`, so the flip
# is an operator action taken AFTER the E11.20 W8b soak closes and after one observed morning
# on the box — the runtime-gate rule (CI mocks all IO and cannot see this behaviour).
CATCHUP_GATE_ENV = "E11_24_STATCAST_CATCHUP_GATE"


def catchup_gate_on() -> bool:
    """True when a catch-up fire that landed no pitches should skip the downstream chain."""
    return os.environ.get(CATCHUP_GATE_ENV, "0").strip() == "1"


def yesterday_et(today: date | None = None) -> date:
    """The baseball 'yesterday' the catch-up is chasing — ET, matching the sensor exactly."""
    if today is None:
        from datetime import datetime

        today = datetime.now(_ET).date()
    return today - timedelta(days=1)


def pitches_present(conn, day: date) -> bool:
    """Do we hold ANY Statcast pitches for `day` in the S3 lakehouse?

    Reads the single ``year=YYYY/`` partition (a full glob metadata scan is ~10s, the partition
    ~2s) and treats a missing partition as 'no pitches' — the season-start case, not an error.
    Deliberately the SAME predicate `statcast_freshness_sensor._pitches_present` uses, so the
    gate can never disagree with the sensor that fired it (a gate that skipped work the sensor
    would immediately re-request is an infinite no-op loop).
    """
    from betting_ml.utils.lakehouse_monitor import is_missing_glob, lh_year

    try:
        (n,) = conn.execute(
            f"SELECT COUNT(*) FROM read_parquet('{lh_year('stg_batter_pitches', day.year)}', "
            f"union_by_name=true) WHERE game_date = ?",
            [day.isoformat()],
        ).fetchone()
    except Exception as exc:  # noqa: BLE001
        if is_missing_glob(exc):
            return False
        raise
    return int(n) > 0


def catchup_landed_pitches(day: date | None = None, conn_factory=None) -> bool:
    """Fail-OPEN wrapper: True (⇒ run the chain) unless we can positively prove nothing landed.

    A lakehouse read error must NOT silently suppress the catch-up — that would convert a
    transient S3 blip into a skipped self-heal, the 'silently never runs' outage class. So any
    exception resolves to True and the chain proceeds exactly as it does today.
    """
    if conn_factory is None:
        from betting_ml.utils.lakehouse_monitor import duck as conn_factory  # noqa: N813
    target = day or yesterday_et()
    try:
        conn = conn_factory()
    except Exception:  # noqa: BLE001
        return True
    try:
        return pitches_present(conn, target)
    except Exception:  # noqa: BLE001
        return True
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
