"""
ingest_umpires.py
-----------------
Fetch today's HP umpire assignments from the MLB Stats API and upsert rows
into baseball_data.statsapi.umpire_game_log.

Endpoint: https://statsapi.mlb.com/api/v1/schedule
  ?sportId=1&date=YYYY-MM-DD&hydrate=officials

The officials array in each game contains entries with officialType.
Filter for officialType == "Home Plate" to get the HP umpire.

HP umpire assignments are announced morning of the game — run after 08:00 ET
before predict_today.py. Only umpire_name and umpire_id are written; tendency
metrics (k_pct, bb_pct, etc.) remain NULL. The dbt feature model computes
trailing z-scores from UmpScorecards historical rows; this script just stamps
the umpire_name so today's game_pk can join via umpire_name.

FU-3 / E11.24-6a-PRE (2026-08-02) — ``--skip-if-exists`` IS NOW PER-GAME AND WORKS ON
THE S3 LEG. Two defects were fixed together:

  1. IT NEVER RAN IN PRODUCTION. The guard was gated
     ``if args.skip_if_exists and not args.dry_run and do_sf`` — SF-leg-only — while the
     box runs ``W11_RAW_WRITE_MODE=s3`` ⇒ ``do_sf=False`` ⇒ the conjunct silently
     disabled it. So every ~30-min lineup_monitor tick re-fetched the Stats API and
     re-wrote the WHOLE slate, re-stamping ``loaded_at`` on unchanged rows (measured over
     lakehouse_raw/umpire_game_log/, 14 slates 07-20..08-02: median 8 distinct same-day
     ``loaded_at`` instants, range 6-20). That is the documented-but-never-set landmine
     class (cf. ``W7B_LAKEHOUSE_S3``): a conjunct nobody re-read after an S3 cutover.
  2. IT WAS AN ANY-ROW CHECK. ``COUNT(*) > 0`` for the date ⇒ once the FIRST game's
     umpire landed it would have skipped the rest of the slate forever. MLB announces HP
     umpires in WAVES across the afternoon (7/31: 1→5→7→9→10→11→13→15 games over 7h), so
     the any-row form would have SWALLOWED every later-announced assignment. Fixing (1)
     without (2) would have shipped that swallow into production.

The guard is therefore PER-GAME **and CONTENT-AWARE**: it reads the latest
``data_source='statsapi'`` row per game_pk from the append-only S3 raw mirror and writes
only the games whose (umpire_id, umpire_name) is absent or CHANGED. Content-awareness is
free (the Stats API returns the whole slate in one call either way) and buys two things an
existence-only per-game check does not: a mid-slate UMPIRE REASSIGNMENT is still ingested,
and the write is skipped only when it provably could not change any output.

⚠️ THE ACHIEVABLE FLOOR IS THE NUMBER OF ANNOUNCEMENT WAVES, NOT ~1 (measured, do not
   re-litigate). Replaying all 14 slates through this exact filter: 126 write-instants →
   91 (−28%), median 8 → 6. EVERY surviving write carries at least one genuinely NEW game
   assignment, so the residual is IRREDUCIBLE — driving it lower necessarily means
   swallowing a late-announced assignment, which is the regression this change exists to
   prevent. Two slates (07-28, 08-02) cut to ZERO because every tick on them brought a new
   game. A one-sided "fewer instants" reading of this lever is therefore WRONG.

FAIL-OPEN on every path (the block has an INC-31/F2 history of silently zeroing): an
unreadable mirror, a missing glob, or a Snowflake-only write mode resolves to "write
everything", never to "skip". A guard that could not run is never scored as a pass.

Usage:
    # Dry-run: print extracted assignments without writing
    uv run python scripts/ingest_umpires.py --date 2026-05-01 --dry-run

    # Live upsert for today
    uv run python scripts/ingest_umpires.py --date $(date +%Y-%m-%d)

    # Intraday tick: write only games whose assignment is new or changed
    uv run python scripts/ingest_umpires.py --date $(date +%Y-%m-%d) --skip-if-exists
"""

import argparse
import logging
import os
import sys
import requests
from dotenv import load_dotenv

# E11.1-W11 Tier-B: leg-gated dual-write (W11_RAW_WRITE_MODE). SF INSERT on 'snowflake'/'both';
# an S3 mirror to lakehouse_raw/umpire_game_log/ on 's3'/'both'. Default 'snowflake' → unchanged.
from utils.lakehouse_raw_writer import (  # noqa: E402
    lakehouse_write_legs,
    umpire_mirror_rows,
    w11_write_mode,
    write_raw_rows_s3,
)

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

_LAKEHOUSE_SOURCE = "umpire_game_log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

STATSAPI_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
TABLE_FQN = "baseball_data.statsapi.umpire_game_log"

INSERT_SQL = f"""
INSERT INTO {TABLE_FQN} (
    game_pk, game_date, season, umpire_name, umpire_id,
    k_pct, bb_pct, total_runs, called_strikes_above_avg,
    run_expectancy_delta, total_run_impact, accuracy_above_expected,
    data_source, loaded_at
)
SELECT
    %(game_pk)s::INTEGER,
    %(game_date)s::DATE,
    %(season)s::INTEGER,
    %(umpire_name)s::VARCHAR,
    %(umpire_id)s::VARCHAR,
    NULL::FLOAT,
    NULL::FLOAT,
    NULL::INTEGER,
    NULL::FLOAT,
    NULL::FLOAT,
    NULL::FLOAT,
    NULL::FLOAT,
    'statsapi'::VARCHAR,
    CURRENT_TIMESTAMP()
"""


def get_snowflake_conn():
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE, and has NO SNOWFLAKE_PASSWORD — the old
    # file-path→password resolver KeyError'd on the box. Delegate to the shared
    # PATH-if-exists→inline→password resolver. Queries are fully-qualified, so the default
    # schema is immaterial. See CLAUDE.md INC-22 landmine.
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema="statsapi")


def fetch_hp_umpires(game_date: str) -> list[dict]:
    """Fetch HP umpire assignments for all games on game_date from MLB Stats API."""
    params = {
        "sportId": 1,
        "date": game_date,
        "hydrate": "officials",
    }
    try:
        resp = requests.get(STATSAPI_SCHEDULE_URL, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.error("MLB Stats API request failed: %s", exc)
        sys.exit(1)

    data = resp.json()
    season = int(game_date[:4])
    results = []

    total_games = 0
    assigned = 0

    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            game_pk = game.get("gamePk")
            total_games += 1
            officials = game.get("officials", [])

            hp_official = None
            for official in officials:
                if official.get("officialType") == "Home Plate":
                    hp_official = official.get("official", {})
                    break

            if not hp_official:
                log.warning("[WARN] No HP umpire listed for game_pk=%s on %s — skipping.", game_pk, game_date)
                continue

            results.append({
                "game_pk": game_pk,
                "game_date": game_date,
                "season": season,
                "umpire_name": hp_official.get("fullName", "Unknown"),
                "umpire_id": str(hp_official.get("id", "")) or None,
            })
            assigned += 1

    log.info("Loaded HP umpire for %d of %d games on %s", assigned, total_games, game_date)
    return results


# ── FU-3: the per-game, content-aware skip guard ──────────────────────────────────────────

def _norm(value) -> str | None:
    """Normalize an umpire_id / umpire_name for comparison against the S3 mirror.

    The mirror UNIONs rows from four writers plus the one-time Snowflake bridge, so the same
    logical id can arrive as ``'664983'``, ``664983`` or — the nullable-int→DOUBLE poisoning
    class — ``664983.0``. Collapse all three to one string. Empty/None collapse to None so a
    missing id never compares equal to a present one.

    A normalization MISS costs exactly one redundant write (the row is re-stamped), never a
    swallowed assignment — the failure direction is deliberately the safe one.
    """
    if value is None:
        return None
    if isinstance(value, float) and value == int(value):
        value = int(value)
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text or None


def _key(row: dict) -> tuple[str | None, str | None]:
    """The comparison key for one assignment: (umpire_id, umpire_name)."""
    return (_norm(row.get("umpire_id")), _norm(row.get("umpire_name")))


def existing_statsapi_assignments(game_date: str, *, conn_factory=None) -> dict | None:
    """{game_pk: (umpire_id, umpire_name)} already recorded for `game_date`, from the S3 mirror.

    Reads the APPEND-ONLY raw mirror (``lakehouse_raw/umpire_game_log/``) via DuckDB, taking the
    latest ``loaded_at`` row per game_pk — the same dedup ``stg_statsapi_umpire_game_log`` applies,
    so this sees exactly what the feature build will see. Scoped to ``data_source='statsapi'``,
    matching the DELETE scope of insert_rows(), so an ``umpscorecards`` tendency row for a settled
    game never masks a missing assignment.

    Returns None when the answer could NOT be established (no mirror yet, read error, DuckDB
    absent). The caller treats None as "write everything" — a check that did not run is not a pass
    (NF1.7 (a)); the block has an incident history (INC-31, F2) of zeroing unnoticed.

    ⚠️ NEVER hardcode the parquet glob here — ``lh_raw()`` is the shared helper. A hardcoded
    lakehouse path is the 2026-07-20 phase-1.5 P0 (a deleted key took the whole daily job down).
    """
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    try:
        from betting_ml.utils.lakehouse_monitor import duck, is_missing_glob, lh_raw
    except Exception as exc:  # noqa: BLE001 — no duckdb/betting_ml ⇒ unevaluable, not a pass
        log.warning("[FU-3] skip-guard unavailable (%s) — writing every assignment.", exc)
        return None

    conn = None
    try:
        conn = duck()
        # QUALIFY over the RAW rows — deliberately no GROUP BY. A trailing QUALIFY on a grouped
        # query selects row 1 of 1 and is a silent no-op (the E9.52 mixed-snapshot defect).
        # try_cast at every use-site: game_date/loaded_at are ISO VARCHAR for live-writer rows and
        # real DATE/TIMESTAMP for the SF-bridged ones, which union_by_name reconciles to VARCHAR
        # (the INC-23 landmine).
        rows = conn.execute(
            f"""
            SELECT try_cast(game_pk AS BIGINT) AS game_pk, umpire_id, umpire_name
            FROM read_parquet('{lh_raw(_LAKEHOUSE_SOURCE)}', union_by_name=true)
            WHERE try_cast(game_date AS DATE) = try_cast(? AS DATE)
              AND data_source = 'statsapi'
              AND try_cast(game_pk AS BIGINT) IS NOT NULL
            QUALIFY row_number() OVER (
                PARTITION BY try_cast(game_pk AS BIGINT)
                ORDER BY try_cast(loaded_at AS TIMESTAMP) DESC NULLS LAST
            ) = 1
            """,
            [game_date],
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        try:
            missing = is_missing_glob(exc)
        except Exception:  # noqa: BLE001
            missing = False
        if missing:
            return {}  # mirror exists but holds nothing for this source yet — nothing to skip
        log.warning("[FU-3] skip-guard read failed (%s) — writing every assignment.", exc)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    return {int(gp): (_norm(uid), _norm(uname)) for gp, uid, uname in rows}


def filter_new_assignments(assignments: list[dict], existing: dict | None) -> list[dict]:
    """The games worth writing: those absent from `existing` or whose umpire CHANGED.

    PURE (no IO) so the decision is unit-testable offline. `existing` None ⇒ fail OPEN (every
    assignment is written), which is what an unevaluable guard must resolve to.
    """
    if existing is None:
        return list(assignments)
    return [a for a in assignments if existing.get(int(a["game_pk"])) != _key(a)]


def insert_rows(conn, rows: list[dict]) -> int:
    # Idempotent: replace any existing statsapi assignment rows for these game_pks
    # before inserting. The append-only INSERT used to bloat the table when the
    # daily early+late ops AND the afternoon lineup_monitor ticks (Story 30.5) each
    # re-ran for the same day. Scoped to data_source='statsapi' so it never touches
    # the umpscorecards tendency rows for the same game_pk (settled games carry
    # both; the dbt staging model prefers umpscorecards).
    game_pks = [int(r["game_pk"]) for r in rows if r.get("game_pk") is not None]
    with conn.cursor() as cur:
        if game_pks:
            pk_list = ", ".join(str(pk) for pk in game_pks)
            cur.execute(
                f"DELETE FROM {TABLE_FQN} "
                f"WHERE data_source = 'statsapi' AND game_pk IN ({pk_list})"
            )
        for row in rows:
            cur.execute(INSERT_SQL, row)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Ingest daily HP umpire assignments from MLB Stats API")
    parser.add_argument("--date", required=True,
                        help="Game date in YYYY-MM-DD format")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print extracted assignments without writing to Snowflake")
    parser.add_argument("--skip-if-exists", action="store_true",
                        help=(
                            "FU-3 (was E11.11): write only the games whose HP-umpire assignment "
                            "is NEW or CHANGED versus the S3 raw mirror, so a repeated "
                            "lineup_monitor tick stops re-stamping loaded_at on unchanged rows. "
                            "PER-GAME and content-aware — a later-announced assignment still "
                            "lands on the next tick. Fails OPEN (writes everything) whenever the "
                            "mirror cannot be read."
                        ))
    args = parser.parse_args()

    # E11.1-W11 Tier-B: which legs run (SF INSERT and/or S3 mirror) per W11_RAW_WRITE_MODE.
    do_sf, do_s3 = lakehouse_write_legs(w11_write_mode())

    # FU-3: read what is ALREADY recorded for this slate BEFORE hitting the Stats API, so the
    # filter below is decided against pre-fetch state. This replaces the E11.11 any-row COUNT(*)
    # over Snowflake — deleting a per-tick Snowflake CONNECT from the guard path (see the module
    # docstring: on the box it was already unreachable behind `and do_sf`, so this removes a
    # LATENT waker that would fire the moment W11_RAW_WRITE_MODE went back to snowflake|both,
    # not a live one).
    #
    # The Stats API returns the WHOLE slate in one request, so there is nothing to gain by
    # short-circuiting the fetch — and a short-circuit would need to know the slate size, which is
    # exactly the assumption that made the any-row form swallow late announcements. Fetch, then
    # filter.
    existing = None
    if args.skip_if_exists and not args.dry_run:
        if do_s3:
            existing = existing_statsapi_assignments(args.date)
        else:
            # Snowflake-only write mode writes no S3 mirror, so there is nothing to compare
            # against. Stay OPEN and say so — a silently-inert guard is the landmine this
            # story exists to remove, not one to re-introduce facing the other way.
            log.warning(
                "[FU-3] --skip-if-exists is a no-op under W11_RAW_WRITE_MODE=%s (no S3 mirror "
                "to compare against) — writing every assignment.", w11_write_mode(),
            )

    assignments = fetch_hp_umpires(args.date)

    if args.dry_run:
        print(f"\n--- DRY RUN: HP umpire assignments for {args.date} ---")
        for a in assignments:
            print(f"  game_pk={a['game_pk']}  umpire={a['umpire_name']}  id={a['umpire_id']}")
        print(f"Total: {len(assignments)} assignments")
        return

    if not assignments:
        log.warning("No HP umpire assignments found for %s — nothing to write.", args.date)
        return

    if args.skip_if_exists and not args.dry_run:
        fetched = len(assignments)
        assignments = filter_new_assignments(assignments, existing)
        skipped = fetched - len(assignments)
        if not assignments:
            log.info(
                "[FU-3] all %d assignment(s) for %s are unchanged since the last write — "
                "skipping (no loaded_at re-stamp).", fetched, args.date,
            )
            return
        log.info(
            "[FU-3] %d of %d assignment(s) for %s are new or changed (%d unchanged, skipped).",
            len(assignments), fetched, args.date, skipped,
        )

    if do_sf:
        log.info("Connecting to Snowflake...")
        conn = get_snowflake_conn()
        try:
            loaded = insert_rows(conn, assignments)
            log.info("Inserted %d HP umpire assignments for %s", loaded, args.date)
        except Exception as exc:
            log.error("Snowflake write failed: %s", exc)
            conn.close()
            sys.exit(1)
        finally:
            conn.close()

    if do_s3:
        # data_source='statsapi' (today's HP-name assignment); tendency cols NULL.
        mirror_rows = umpire_mirror_rows(assignments, data_source="statsapi")
        n_s3 = write_raw_rows_s3(_LAKEHOUSE_SOURCE, mirror_rows, mode="append")
        log.info("mirrored %d row(s) → S3 lakehouse_raw/%s/", n_s3, _LAKEHOUSE_SOURCE)


if __name__ == "__main__":
    main()
