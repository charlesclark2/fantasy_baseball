"""
lineup_monitor.py
-----------------
Checks Snowflake for newly confirmed starting lineups and writes the result
to $GITHUB_OUTPUT so the caller (lineup_monitor.yml) can decide whether to
trigger a dbt feature rebuild.

Logic:
  1. Query stg_statsapi_lineups_wide for today's games where both home and
     away lineups are posted, and apply the INC-32 readiness gate: a game is
     only eligible to score once BOTH sides carry a COMPLETE 9-slot order (or,
     best-effort, a still-incomplete lineup within the SLA window). Games with
     a partial order are HELD and retried on the next sensor tick, so a
     re-score never freezes on a half-posted lineup (select_ready_games).
  2. Compare against lineup_monitor_state to find games not yet triggered.
  3. For already-triggered games, check if the starting pitcher changed —
     if so, re-trigger so updated features and predictions are produced.
  4. Insert new entries into lineup_monitor_state (idempotent with NOT EXISTS).
     Update existing entries when a pitcher change is detected.
  5. Write has_new_games (true/false) and new_game_pks (comma-separated) to
     $GITHUB_OUTPUT. If not running in GHA, prints to stdout instead.

Snowflake authentication — private key (preferred) or password fallback:
    SNOWFLAKE_ACCOUNT
    SNOWFLAKE_USER
    SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH      path to PEM private key
    SNOWFLAKE_PRIVATE_KEY_PASSPHRASE  (optional)
    SNOWFLAKE_ROLE                  (optional)
    SNOWFLAKE_PASSWORD              fallback when no private key is set

Usage:
    uv run lineup_monitor.py
"""

import logging
import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import snowflake.connector

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

TASK = "lineup_monitor"

# INC-32 (2026-07-19) — PER-GAME LINEUP-READINESS GATE + retry.
# ROOT CAUSE of the 0.811 post_lineup coverage (14/15 games' lineup block dead on 7/19):
# a RE-SCORE-TOO-EARLY race. The old detection was "both sides have posted SOME lineup"
# (stg_statsapi_lineups_wide keeps a row per side as soon as slot_1 is non-null, and the
# monitor only required COUNT(DISTINCT home_away)=2). MLB posts a batting order slot-by-slot,
# and the capture→flatten→lineups_wide chain can surface a PARTIAL order (e.g. slots 1–4)
# minutes before the full 9. Firing the re-score on that partial state rebuilds the SCD-2 /
# aggregator from an incomplete lineup → the served lineup block (avg_eb_woba etc.) is dead.
# And post_lineup is ONE-AND-DONE: once a game has a post_lineup row it is never re-triggered
# (Step 2b only re-fires games MISSING a post_lineup row), so that first degraded attempt is
# frozen forever — the actual defect.
# FIX: a game is only "ready" to score once BOTH sides carry a COMPLETE 9-slot lineup. An
# incomplete game is HELD (not triggered, not recorded in lineup_monitor_state, no post_lineup
# row) so it stays eligible and the sensor's next tick (~10 min in the active window) retries —
# by which time the full order has landed. SLA safety valve: if a lineup is still incomplete
# within _SLA_FALLBACK_MINUTES of first pitch we score it best-effort anyway, so the readiness
# gate can never make us BLOW the Epic A1 "post_lineup >= 30 min pre-pitch" SLA on the rare
# never-completes-to-9 game.
_FULL_LINEUP_SLOTS = 9
_SLA_FALLBACK_MINUTES = 40.0

# ── E11.20 PHASE-2a — the SNOWFLAKE-FREE DETECTION TICK (2026-07-20) ────────────────────
# The E11.20-COST measurement found ~80% of Snowflake spend is warehouse WAKE/IDLE, not
# query compute, and named this monitor one of the last 24/7 wakers: the sensor evaluates
# it every ~10 min through the game window, and EVERY tick opened a Snowflake session
# (lineups/probables joins + the lineup_monitor_state read + an unconditional audit-log
# INSERT) — so the warehouse could never suspend.
#
# ⭐ THE DESIGN LINE: the DETECTION TICK must be Snowflake-free; the TRIGGERED JOB may stay
# on Snowflake. A tick that finds nothing must not touch SF at all (that is the wake we are
# killing). When a lineup DOES confirm we fire lineup_monitor_job, which runs dbt/predict on
# Snowflake anyway — one wake there is legitimate and unavoidable, so the audit-log write is
# kept but made CONDITIONAL on an actual trigger instead of firing every quiet tick.
#
# Under LINEUP_MONITOR_S3=1:
#   reads  → DuckDB over the S3 lakehouse (stg_statsapi_lineups_wide, probable_pitchers,
#            daily_model_predictions). All three are rebuilt intraday by the capture chain /
#            written by predict_today's own S3 export, so they are as fresh as the SF views
#            were — the SF views are literally external tables over these same parquet files.
#   state  → DynamoDB (the lineup_monitor_state replacement), same table + `pk="ops"` layout
#            as the INC-16-P6 daily heartbeat; tiny, idempotent, single-digit items per day.
# Flag OFF (default) = the byte-for-byte Snowflake path, unchanged. This is the W7a/W7b/W8a
# convention: build gated, soak, then flip.
#
# Once this flips, the intraday capture tick's `refresh_w1_external_tables.py` leg exists
# only for the remaining SF consumers (K-projection cron, zone overlays) — repoint those and
# the whole 30-min chain goes SF-free, which is where the bulk of the remaining wake burn is.
_S3_MODE = os.environ.get("LINEUP_MONITOR_S3", "0") == "1"
_STATE_TABLE = os.environ.get("SERVING_CACHE_TABLE", "credence-prod-serving-cache")
_STATE_SK_PREFIX = "lineup_monitor#"


def _duck_lakehouse(tables: list[str]):
    """A DuckDB connection with the given lakehouse tables registered as bare-name views,
    routed per storage backend (the phase-1.5 Delta-aware registrar)."""
    from betting_ml.utils.delta_lakehouse import register_lakehouse_views
    from betting_ml.utils.lakehouse_monitor import duck

    conn = duck()
    register_lakehouse_views(conn, tables)
    return conn


def _candidates_s3(today_iso: str) -> dict[int, dict]:
    """Step 1 (candidates + per-game lineup completeness), Snowflake-free. Mirrors the SF
    query exactly: MIN over both sides of the filled-slot count, both sides required."""
    conn = _duck_lakehouse(["stg_statsapi_lineups_wide", "stg_statsapi_probable_pitchers"])
    try:
        slots = " + ".join(
            f"(CASE WHEN slot_{i}_player_id IS NOT NULL THEN 1 ELSE 0 END)"
            for i in range(1, _FULL_LINEUP_SLOTS + 1)
        )
        rows = conn.execute(
            f"""
            SELECT l.game_pk, p_home.probable_pitcher_id, p_away.probable_pitcher_id,
                   l.min_slots_filled
            FROM (
                SELECT game_pk, MIN({slots}) AS min_slots_filled
                FROM stg_statsapi_lineups_wide
                WHERE official_date::date = ?::date
                GROUP BY game_pk
                HAVING COUNT(DISTINCT home_away) = 2
            ) l
            LEFT JOIN (SELECT game_pk, probable_pitcher_id FROM stg_statsapi_probable_pitchers
                       WHERE side = 'home') p_home ON l.game_pk = p_home.game_pk
            LEFT JOIN (SELECT game_pk, probable_pitcher_id FROM stg_statsapi_probable_pitchers
                       WHERE side = 'away') p_away ON l.game_pk = p_away.game_pk
            """,
            [today_iso],
        ).fetchall()
        return {
            int(r[0]): {"home": r[1], "away": r[2], "min_slots_filled": r[3]}
            for r in rows
        }
    finally:
        conn.close()


def _games_with_post_lineup_s3(today_iso: str) -> set[int]:
    """Step 2b, Snowflake-free. predict_today exports daily_model_predictions to this same
    parquet immediately after each write, so the S3 copy is current within one predict."""
    conn = _duck_lakehouse(["daily_model_predictions"])
    try:
        rows = conn.execute(
            "SELECT DISTINCT game_pk FROM daily_model_predictions "
            "WHERE game_date::date = ?::date AND prediction_type = 'post_lineup'",
            [today_iso],
        ).fetchall()
        return {int(r[0]) for r in rows}
    finally:
        conn.close()


def _state_table():
    import boto3

    return boto3.resource("dynamodb").Table(_STATE_TABLE)


def _already_triggered_dynamo(today_iso: str) -> dict[int, tuple]:
    """Step 2 (games already triggered today), Snowflake-free. Query on the sk prefix for
    this run_date — one small query per tick."""
    from boto3.dynamodb.conditions import Key

    resp = _state_table().query(
        KeyConditionExpression=Key("pk").eq("ops")
        & Key("sk").begins_with(f"{_STATE_SK_PREFIX}{today_iso}#")
    )
    out: dict[int, tuple] = {}
    for item in resp.get("Items", []):
        try:
            pk = int(str(item["sk"]).rsplit("#", 1)[1])
        except (KeyError, IndexError, ValueError):
            continue
        home, away = item.get("home_starter_id"), item.get("away_starter_id")
        out[pk] = (int(home) if home is not None else None,
                   int(away) if away is not None else None)
    return out


def _record_trigger_dynamo(today_iso: str, game_pk: int, home, away) -> None:
    """Steps 3/3b, Snowflake-free. A plain put_item is the idempotent-insert AND the
    starter-change update in one (the SF path needed separate INSERT-WHERE-NOT-EXISTS and
    UPDATE statements; last-write-wins on a fixed key is equivalent here because the only
    mutation is refreshing the starters + triggered_at)."""
    _state_table().put_item(Item={
        "pk": "ops",
        "sk": f"{_STATE_SK_PREFIX}{today_iso}#{int(game_pk)}",
        "run_date": today_iso,
        "game_pk": int(game_pk),
        "home_starter_id": int(home) if home is not None else None,
        "away_starter_id": int(away) if away is not None else None,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "is_permanent": False,
        "cache_date": today_iso,
    })


def select_ready_games(candidates, first_pitch, now):
    """PURE readiness-gate decision (unit-tested; no IO).

    candidates: {game_pk: {"home": starter_id|None, "away": starter_id|None,
                           "min_slots_filled": int}}  — one entry per game whose BOTH sides
        have posted at least a partial lineup (COUNT(DISTINCT home_away)=2). min_slots_filled
        is the MIN over the two sides of how many of the 9 batting slots are filled, so it is
        9 only when BOTH sides carry a complete order.
    first_pitch: {game_pk: tz-aware datetime | None} — first-pitch instant (UTC).
    now: tz-aware datetime (UTC).

    Returns (ready, held):
      ready: {game_pk: (home_starter_id, away_starter_id)} — games safe to trigger/score.
      held:  [(game_pk, min_slots_filled, reason)] — games withheld this tick (retry next tick).
    """
    ready: dict[int, tuple] = {}
    held: list[tuple] = []
    for pk, info in candidates.items():
        filled = info.get("min_slots_filled") or 0
        pair = (info.get("home"), info.get("away"))
        if filled >= _FULL_LINEUP_SLOTS:
            ready[pk] = pair
            continue
        # Incomplete lineup — only score best-effort if we're up against the SLA deadline.
        fp = first_pitch.get(pk)
        mins = None
        if fp is not None:
            mins = (fp - now).total_seconds() / 60.0
        if mins is not None and mins <= _SLA_FALLBACK_MINUTES:
            ready[pk] = pair
            held.append((pk, filled, f"SLA-fallback: {filled}/9 slots, first pitch in {mins:.0f} min"))
        else:
            when = "unknown" if mins is None else f"{mins:.0f} min"
            held.append((pk, filled, f"held: {filled}/9 slots, first pitch in {when}"))
    return ready, held


def get_connection() -> snowflake.connector.SnowflakeConnection:
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE, and has NO SNOWFLAKE_PASSWORD — the old
    # file-path→password resolver KeyError'd on the box. Delegate to the shared
    # PATH-if-exists→inline→password resolver. Queries are fully-qualified, so the default
    # schema is immaterial. See CLAUDE.md INC-22 landmine.
    import sys as _sys
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in _sys.path:
        _sys.path.insert(0, _root)
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection()


def _norm_pid(x) -> int | None:
    """Normalize a probable-pitcher id to int|None so a stored INT never miscompares against a
    Decimal/str the staging read may return. A verbatim `!=` on mixed types reads as a change
    every tick → the 823523 pitcher-change flip-flop (2026-07-19)."""
    if x is None:
        return None
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def is_real_pitcher_change(stored: tuple, current: tuple) -> bool:
    """PURE (unit-tested) — True ONLY when a game's probable starters genuinely changed
    side-for-side. Guards the 823523 flip-flop (2026-07-19, re-triggered every tick for 4h):
    a transient NULL current probable (a LEFT JOIN gap in stg_statsapi_probable_pitchers) or a
    stored-INT-vs-Decimal/str type mismatch is NOT a scratch. Both stored AND current must be
    fully known and differ after int-normalization. stored=(home,away), current=(home,away)."""
    sh, sa = _norm_pid(stored[0]), _norm_pid(stored[1])
    ch, ca = _norm_pid(current[0]), _norm_pid(current[1])
    if sh is None or sa is None:   # stored unknown (pre-migration rows) — wait, don't churn
        return False
    if ch is None or ca is None:   # current probable temporarily missing — a data gap, not a scratch
        return False
    return sh != ch or sa != ca


def _pregame_first_pitch(today_iso: str) -> dict[int, datetime | None] | None:
    """{game_pk: first-pitch instant (UTC)} for today's PRE-GAME (`abstract_game_state='Preview'`)
    regular-season games, read Snowflake-free from the S3 lakehouse (stg_statsapi_games) via
    DuckDB — the same proven read the lineup sensor's cadence gate uses. Returns None on a read
    failure so the caller can FAIL-OPEN (no pregame filter) rather than go dark.

    Two jobs:
      1. PRE-GAME GATE — the monitor must only ever trigger a re-score for a game that has NOT
         started. A Live/Final game's post_lineup re-score is pointless (the bet is off the board)
         and past the Epic A1 30-min SLA; scoring one drove game 823523's infinite re-trigger loop
         (2026-07-19, every tick 14:10→18:11, incl. ~10 AFTER its 16:35 first pitch). Restricting
         candidates to this Preview set excludes Live/Final AND Postponed (postponed reads
         abstract_game_state='Final' — the DH landmine — plus the explicit exclusion below).
      2. SLA SAFETY VALVE — supplies first pitch to the readiness gate (select_ready_games).

    game_date is stored ISO-VARCHAR in the lakehouse (INC-23) → coerced via to_utc_datetime."""
    try:
        from betting_ml.utils.lakehouse_monitor import duck, lh, to_utc_datetime
    except Exception as e:  # noqa: BLE001 — never break the monitor on an optional read
        log.warning("pregame lakehouse import failed (%s); proceeding without the pregame filter.", e)
        return None
    conn = duck()
    try:
        rows = conn.execute(
            f"SELECT game_pk, MIN(game_date) FROM read_parquet('{lh('stg_statsapi_games')}', "
            f"union_by_name=true) WHERE official_date = ? AND game_type = 'R' "
            f"AND abstract_game_state = 'Preview' AND coalesce(detailed_state, '') != 'Postponed' "
            f"GROUP BY game_pk",
            [today_iso],
        ).fetchall()
    except Exception as e:  # noqa: BLE001
        log.warning("pregame lakehouse read failed (%s); proceeding without the pregame filter.", e)
        return None
    finally:
        conn.close()
    return {int(r[0]): to_utc_datetime(r[1]) for r in rows}


# ── Snowflake read helpers (the DEFAULT path — unchanged behaviour, flag OFF) ───────────
# Extracted verbatim from main() so the phase-2a S3 branch is a clean either/or rather than
# interleaved conditionals inside one long function.
def _candidates_sf(cur, today_iso: str) -> dict[int, dict]:
    slots = "\n                      + ".join(
        f"(CASE WHEN slot_{i}_player_id IS NOT NULL THEN 1 ELSE 0 END)"
        for i in range(1, _FULL_LINEUP_SLOTS + 1)
    )
    cur.execute(
        f"""
        SELECT
            l.game_pk,
            p_home.probable_pitcher_id AS home_starter_id,
            p_away.probable_pitcher_id AS away_starter_id,
            l.min_slots_filled
        FROM (
            SELECT game_pk, MIN({slots}) AS min_slots_filled
            FROM baseball_data.betting.stg_statsapi_lineups_wide
            WHERE official_date = %s::date
            GROUP BY game_pk
            HAVING COUNT(DISTINCT home_away) = 2
        ) l
        LEFT JOIN baseball_data.betting.stg_statsapi_probable_pitchers p_home
            ON l.game_pk = p_home.game_pk AND p_home.side = 'home'
        LEFT JOIN baseball_data.betting.stg_statsapi_probable_pitchers p_away
            ON l.game_pk = p_away.game_pk AND p_away.side = 'away'
        """,
        [today_iso],
    )
    return {
        row[0]: {"home": row[1], "away": row[2], "min_slots_filled": row[3]}
        for row in cur.fetchall()
    }


def _already_triggered_sf(cur, today_iso: str) -> dict[int, tuple]:
    cur.execute(
        """
        SELECT game_pk, home_starter_id, away_starter_id
        FROM baseball_data.config.lineup_monitor_state
        WHERE run_date = %s::date
        """,
        [today_iso],
    )
    return {row[0]: (row[1], row[2]) for row in cur.fetchall()}


def _games_with_post_lineup_sf(cur, today_iso: str) -> set[int]:
    cur.execute(
        """
        SELECT DISTINCT game_pk
        FROM baseball_data.betting_ml.daily_model_predictions
        WHERE game_date = %s::date
          AND prediction_type = 'post_lineup'
        """,
        [today_iso],
    )
    return {row[0] for row in cur.fetchall()}


def write_github_output(key: str, value: str) -> None:
    gho = os.environ.get("GITHUB_OUTPUT")
    if gho:
        with open(gho, "a") as f:
            f.write(f"{key}={value}\n")
    else:
        print(f"[OUTPUT] {key}={value}")


def main() -> None:
    # Use America/New_York for "today" so late-night West Coast lineups (which
    # confirm at ~02:00 UTC) still resolve to the correct MLB calendar day.
    # GitHub Actions runs in UTC, so date.today() rolls over at 00:00 UTC and
    # would otherwise miss confirmations between 00:00 UTC and ~05:00 UTC.
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    # PHASE-2a: under LINEUP_MONITOR_S3 the whole detection path is Snowflake-free, so we do
    # not open a session at all — opening one is itself the warehouse wake we are killing.
    # The connection is created LAZILY, only if a trigger fires (audit log) or on failure.
    conn = None if _S3_MODE else get_connection()
    cur = None if conn is None else conn.cursor()

    def _sf_cursor():
        """Lazily open the Snowflake session (trigger/audit/error paths only, in S3 mode)."""
        nonlocal conn, cur
        if cur is None:
            conn = get_connection()
            cur = conn.cursor()
        return cur

    try:
        # Step 1 — candidate games (both batting lineups posted) with current probable pitchers
        # AND per-game lineup COMPLETENESS. In the universal DH era pitchers don't appear in
        # batting lineups, so we join stg_statsapi_probable_pitchers to track starter changes
        # separately. min_slots_filled = the MIN over the two sides of how many of the 9 batting
        # slots are non-null, so it is 9 only when BOTH sides carry a complete order — the
        # INC-32 readiness-gate signal (see select_ready_games): a re-score must not fire on a
        # partially-posted lineup.
        if _S3_MODE:
            candidates = _candidates_s3(today)
        else:
            candidates = _candidates_sf(cur, today)
        log.info("Candidate games today (both sides posted): %d", len(candidates))

        # INC-32 PRE-GAME GATE (2026-07-19) — restrict candidates to games that have NOT started.
        # A post_lineup re-score only makes sense before first pitch; scoring a Live/Final game is
        # pointless + past the SLA and drove game 823523's infinite re-trigger loop. Fail-open: if
        # the game-state read is unavailable (None), keep all candidates (old behavior) so the
        # monitor never goes dark.
        pregame = _pregame_first_pitch(today)
        if pregame is not None:
            dropped = [pk for pk in candidates if pk not in pregame]
            if dropped:
                log.info(
                    "Dropping %d non-pregame game(s) (Live/Final/Postponed — no re-score): %s",
                    len(dropped), sorted(dropped),
                )
            candidates = {pk: v for pk, v in candidates.items() if pk in pregame}
            first_pitch: dict[int, datetime | None] = pregame
        else:
            log.warning("Pregame game-state lookup unavailable — proceeding without the pregame filter.")
            first_pitch = {}

        # INC-32 readiness gate — only games whose BOTH sides carry a COMPLETE 9-slot lineup are
        # eligible to trigger/score (or, best-effort, a still-incomplete game within the SLA
        # window). Held games are simply not in `confirmed` this tick, so they are neither
        # recorded in lineup_monitor_state nor scored — the sensor's next tick retries them once
        # the full order lands. This is the fix for the one-and-done partial-lineup freeze.
        ready, held = select_ready_games(candidates, first_pitch, datetime.now(timezone.utc))
        confirmed: dict[int, tuple[int | None, int | None]] = ready
        log.info("Ready (complete-lineup) games today: %d", len(confirmed))
        if held:
            log.info(
                "Held %d game(s) with incomplete lineups (readiness gate; will retry next tick): %s",
                len(held), held,
            )
            # Loud line for any SLA-fallback score (an incomplete lineup scored to protect the SLA).
            for pk, filled, reason in held:
                if reason.startswith("SLA-fallback"):
                    log.warning(
                        "[ALERT] game_pk=%d scored with INCOMPLETE lineup — %s. Full order never "
                        "reached lineups_wide before the Epic A1 SLA deadline; investigate the "
                        "schedule capture→flatten chain if this recurs.", pk, reason,
                    )

        # Step 2 — games already triggered today, with stored starter IDs
        if _S3_MODE:
            already_triggered = _already_triggered_dynamo(today)
        else:
            already_triggered = _already_triggered_sf(cur, today)
        log.info("Already triggered today: %d", len(already_triggered))

        # Step 2b — games that have a post_lineup prediction written for today.
        # A game can be in lineup_monitor_state but still lack a post_lineup row if
        # the lineup_monitor_job failed after recording the trigger but before
        # lineup_predict completed (e.g., a dbt step errored mid-run). Without this
        # check, the game is skipped forever on subsequent ticks because it's already
        # in already_triggered.
        if _S3_MODE:
            games_with_post_lineup = _games_with_post_lineup_s3(today)
        else:
            games_with_post_lineup = _games_with_post_lineup_sf(cur, today)
        log.info("Games with existing post_lineup prediction: %d", len(games_with_post_lineup))

        new_game_pks: list[int] = []
        pitcher_change_pks: list[int] = []

        for pk, (home_starter, away_starter) in confirmed.items():
            if pk not in already_triggered:
                new_game_pks.append(pk)
            elif pk not in games_with_post_lineup:
                # Triggered but post_lineup prediction never written — job must have
                # failed mid-run. Re-trigger so the prediction is produced.
                log.info(
                    "Re-triggering game_pk=%d: in lineup_monitor_state but no "
                    "post_lineup prediction found.",
                    pk,
                )
                new_game_pks.append(pk)
            else:
                stored_home, stored_away = already_triggered[pk]
                # Only re-trigger on a GENUINE side-for-side starter change. is_real_pitcher_change
                # guards the 823523 flip-flop (2026-07-19): a NULL current probable (LEFT JOIN gap)
                # or a stored-INT-vs-Decimal/str type mismatch is NOT a scratch — comparing those
                # verbatim re-triggered the game every tick for 4h. Both stored and current must be
                # fully known and differ after int-normalization.
                if is_real_pitcher_change((stored_home, stored_away), (home_starter, away_starter)):
                    log.info(
                        "Pitcher change detected for game_pk=%d: "
                        "home %s→%s, away %s→%s",
                        pk, stored_home, home_starter, stored_away, away_starter,
                    )
                    pitcher_change_pks.append(pk)

        all_trigger_pks = sorted(new_game_pks + pitcher_change_pks)
        log.info(
            "New game_pks: %s | Pitcher change pks: %s",
            new_game_pks,
            pitcher_change_pks,
        )

        # Step 3 — record new entries; update starter IDs for pitcher changes
        for pk in new_game_pks:
            home_starter, away_starter = confirmed[pk]
            if _S3_MODE:
                _record_trigger_dynamo(today, pk, home_starter, away_starter)
                continue
            # Probable pitcher may be NULL if not yet announced — store NULL rather than cast error
            home_cast = f"{home_starter}::int" if home_starter is not None else "NULL::int"
            away_cast = f"{away_starter}::int" if away_starter is not None else "NULL::int"
            cur.execute(
                f"""
                INSERT INTO baseball_data.config.lineup_monitor_state
                    (run_date, game_pk, triggered_at, home_starter_id, away_starter_id)
                SELECT %s::date, %s::int, CURRENT_TIMESTAMP(), {home_cast}, {away_cast}
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM baseball_data.config.lineup_monitor_state
                    WHERE run_date = %s::date AND game_pk = %s::int
                )
                """,
                [today, pk, today, pk],
            )

        for pk in pitcher_change_pks:
            home_starter, away_starter = confirmed[pk]
            if _S3_MODE:
                # put_item on the fixed (run_date, game_pk) key IS the update (last write wins).
                _record_trigger_dynamo(today, pk, home_starter, away_starter)
                continue
            home_cast = f"{home_starter}::int" if home_starter is not None else "NULL::int"
            away_cast = f"{away_starter}::int" if away_starter is not None else "NULL::int"
            cur.execute(
                f"""
                UPDATE baseball_data.config.lineup_monitor_state
                SET home_starter_id = {home_cast},
                    away_starter_id = {away_cast},
                    triggered_at    = CURRENT_TIMESTAMP()
                WHERE run_date = %s::date AND game_pk = %s::int
                """,
                [today, pk],
            )

        # Audit log. PHASE-2a: in S3 mode a QUIET tick (nothing triggered) must not open a
        # Snowflake session at all — that unconditional INSERT was the 24/7 wake. On a tick
        # that DID trigger we still log it: the lineup_monitor_job it fires runs dbt/predict
        # on Snowflake anyway, so the session is already being paid for.
        if _S3_MODE and not all_trigger_pks:
            log.info("[phase-2a] Quiet tick — Snowflake untouched (audit log skipped).")
        else:
            _sf_cursor().execute(
                """
                INSERT INTO baseball_data.config.pipeline_run_log
                    (task_name, run_ts, status, rows_affected)
                VALUES (%s, CURRENT_TIMESTAMP(), 'SUCCESS', %s)
                """,
                [TASK, len(all_trigger_pks)],
            )
            conn.commit()

        # Step 4 — write GHA outputs
        write_github_output("has_new_games", "true" if all_trigger_pks else "false")
        write_github_output("new_game_pks", ",".join(str(pk) for pk in all_trigger_pks))
        log.info("Done. has_new_games=%s", bool(all_trigger_pks))

    except Exception as e:
        log.error("lineup_monitor failed: %s", e)
        try:
            # A failure is worth a Snowflake session even in S3 mode (rare + diagnostic).
            _sf_cursor().execute(
                """
                INSERT INTO baseball_data.config.pipeline_run_log
                    (task_name, run_ts, status, rows_affected, error_message)
                VALUES (%s, CURRENT_TIMESTAMP(), 'FAILED', 0, %s)
                """,
                [TASK, str(e)[:400]],
            )
            conn.commit()
        except Exception:
            pass
        raise
    finally:
        # In S3 mode the session may never have been opened (the point of the exercise).
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
