"""odds_current_rebuild_sensor — Story 12.3.7 / A2.18.

Fires the LIGHT current-odds dbt rebuild (`odds_current_rebuild_job` → stg_oddsapi_odds +
mart_odds_outcomes) on a DYNAMIC, game-hours window derived from today's actual slate:

    * window opens  3h before the first game's first pitch
    * fires hourly  while open
    * one extra fire in the 10-min run-up to the LAST game's first pitch (near-close)
    * window closes at the last first pitch (pre-game edge no longer needed after that)
    * NO games today  → never fires (0 warehouse spend on dark days)

Why a sensor and not a schedule: the window depends on external state (tonight's pitch
times) AND we want to read the slate only ONCE/day. A schedule would have to re-query the
slate on every tick; the sensor caches first/last pitch in its cursor and only re-queries
when the ET date rolls over. The 30-min host-cron capture keeps `mlb_odds_raw` dense
regardless — this sensor only governs when the *marts* get rebuilt.

Cadence vs the old per-capture trigger: ~12-14 light rebuilds on a game day (vs ~48), and
the heavy post-hoc CLV/line-movement marts are split off to a once/day post-game schedule.

E11.1-W12 (INC-21 cure): the slate read was the literal INC-21 footgun. It used a raw
`open(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"])` + `snowflake.connector`; on the EC2 box
`pipeline.resources` sets that PATH env var UNCONDITIONALLY but only writes the key file when
the inline `SNOWFLAKE_PRIVATE_KEY` is present, so any gap (empty inline key / transient
connect failure) made `_query_slate` throw → the broad `except` below swallowed it into a
SkipReason → the odds rebuild silently never fired → empty dashboard, NO alert. The read now
goes to the S3 lakehouse (`stg_statsapi_games`) via DuckDB's instance-role credential_chain —
the SAME substrate the serving path already trusts, with no Snowflake/key-file dependency.
"""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dagster import RunRequest, SensorEvaluationContext, SkipReason, sensor

from pipeline.jobs.intraday_jobs import odds_current_rebuild_job

_ET = ZoneInfo("America/New_York")
_OPEN_LEAD = timedelta(hours=3)        # window opens 3h before first pitch
_NEAR_CLOSE_LEAD = timedelta(minutes=10)  # extra fire in the 10 min before last first pitch


def _query_slate(et_date: str):
    """Return (first_pitch, last_pitch) as tz-aware UTC datetimes for the ET slate, or
    (None, None) if the slate isn't loaded yet / no games. Reads stg_statsapi_games from the
    S3 lakehouse via DuckDB (instance-role credential_chain — Snowflake-free). game_date is
    stored as a tz-aware UTC timestamp, so MIN/MAX already give the first/last first-pitch
    instant in UTC."""
    from betting_ml.utils.lakehouse_monitor import duck, lh, to_utc_datetime

    conn = duck()
    try:
        first, last = conn.execute(
            f"SELECT MIN(game_date), MAX(game_date) "
            f"FROM read_parquet('{lh('stg_statsapi_games')}', union_by_name=true) "
            f"WHERE official_date = ? AND game_type = 'R'",
            [et_date],
        ).fetchone()
    finally:
        conn.close()
    if first is None or last is None:
        return None, None
    # game_date reads back as an ISO VARCHAR from the lakehouse (INC-23) — coerce, don't .astimezone().
    return to_utc_datetime(first), to_utc_datetime(last)


@sensor(job=odds_current_rebuild_job, minimum_interval_seconds=600)
def odds_current_rebuild_sensor(context: SensorEvaluationContext):
    """Evaluate every ~10 min; fire the light current-odds rebuild on the dynamic window.

    Cursor is JSON: {et_date, first_pitch, last_pitch, fired:[...]}. The Snowflake slate
    query runs only when et_date changes (≤ once/day); all other ticks are pure-Python and
    cost nothing. `fired` holds the hour-buckets ("YYYY-MM-DDTHH") and the literal "close"
    already dispatched, so a 10-min tick cadence never double-fires an hour.
    """
    now = datetime.now(timezone.utc)
    et_date = datetime.now(_ET).date().isoformat()

    state = {}
    if context.cursor:
        try:
            state = json.loads(context.cursor)
        except (ValueError, TypeError):
            state = {}

    # (Re)load the slate window once per ET day. Fail-open: if the slate isn't loaded yet,
    # skip and retry next tick (don't cache an empty window).
    if state.get("et_date") != et_date or "first_pitch" not in state:
        try:
            first, last = _query_slate(et_date)
        except Exception as exc:  # noqa: BLE001 — transient infra; skip, retry next tick
            yield SkipReason(f"Could not read today's slate: {exc}")
            return
        if first is None:
            yield SkipReason(f"No regular-season slate loaded for {et_date} yet.")
            return
        state = {
            "et_date": et_date,
            "first_pitch": first.isoformat(),
            "last_pitch": last.isoformat(),
            "fired": [],
        }
        context.update_cursor(json.dumps(state))

    first_pitch = datetime.fromisoformat(state["first_pitch"])
    last_pitch = datetime.fromisoformat(state["last_pitch"])
    fired = set(state.get("fired", []))

    if now < first_pitch - _OPEN_LEAD:
        yield SkipReason(f"Before window (opens {(first_pitch - _OPEN_LEAD).isoformat()}).")
        return
    if now > last_pitch:
        yield SkipReason(f"After last first pitch ({last_pitch.isoformat()}) — window closed.")
        return

    # Inside the 10-min run-up to the last game's first pitch: ONLY the single near-close
    # rebuild fires here (this is the terminal "last one, 10 min before last first pitch").
    # Hourly is suppressed in this zone so we don't double-fire near the close.
    if now >= last_pitch - _NEAR_CLOSE_LEAD:
        if "close" not in fired:
            fired.add("close")
            state["fired"] = sorted(fired)
            context.update_cursor(json.dumps(state))
            yield RunRequest(run_key=f"{et_date}:close", tags={"odds_window": "near_close"})
        else:
            yield SkipReason("Near-close rebuild already fired.")
        return

    # Hourly tick: fire once per clock hour while the window is open.
    bucket = now.strftime("%Y-%m-%dT%H")
    if bucket not in fired:
        fired.add(bucket)
        state["fired"] = sorted(fired)
        context.update_cursor(json.dumps(state))
        yield RunRequest(run_key=f"{et_date}:{bucket}", tags={"odds_window": "hourly"})
        return

    yield SkipReason(f"Already rebuilt for hour {bucket}.")
