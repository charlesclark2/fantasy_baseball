"""E9.31b — daily zone-overlay generator.

Resolves batter × opposing-starter pairs from today's (or --date's) lineup and
probable-pitcher tables, builds zone profiles from the S3 lakehouse (DuckDB,
3-year rolling window), and writes overlay JSONs to the serving S3 prefix.

⭐ E11.20 phase-2a REVIVAL (2026-07-20). This generator produced ZERO overlays on the
organic path between 2026-06-30 and 2026-07-20 — the app's "Matchup Zone Analysis"
surface was dead for three weeks and NOBODY noticed, because the script is WARN-tier and
exits 0 whether it writes 500 overlays or none. Three compounding defects, all fixed here
plus one in the caller:
  (a) the target date came from `date.today()` — the RAW UTC box clock (INC-22). Now routed
      through betting_ml.utils.game_day.current_game_date_iso() (the US baseball-day).
  (b) the ONLY trigger was the pre-dawn daily job (~11:40pm PT), when today's lineups
      CANNOT exist yet, so `pairs` was always empty. Fixed in the caller: the op is now
      also a WARN-tier leaf of lineup_monitor_job, which fires when lineups actually
      confirm (see pipeline/jobs/sensor_jobs.py).
  (c) the pair query hit Snowflake. Now DuckDB over the S3 lakehouse — this script is one
      of the last intraday Snowflake consumers whose freshness the 30-min capture tick's
      external-table refresh existed to serve.
⇒ This script is now SNOWFLAKE-FREE end to end. Verifying it "exits 0" proves nothing;
verify the overlay COUNT for a live slate.

WARN-tier: peripheral/app-cosmetic.  Any failure logs a warning to stderr and the
script exits 0 so the Dagster op never blocks predictions or serving.

For backfill: --days-back N also generates overlays for the N calendar days before
--date, using the SAME as-of profiles.  All overlays land at
  s3://baseball-betting-ml-artifacts/baseball/serving/zone_matchup/overlay/as_of=<date>/
The backend endpoint tries today → yesterday → 2-days-ago, so writing at today's
as-of date means past-slate overlays are reachable without per-date S3 keys.

Usage:
    # daily (Dagster-called):
    uv run python scripts/generate_zone_overlays_today.py

    # manual backfill of the past 14 days (>1 min — hand to operator):
    uv run python scripts/generate_zone_overlays_today.py --days-back 14

    # specific date smoke test:
    uv run python scripts/generate_zone_overlays_today.py --date 2026-06-27 --dry-run

Lakehouse-only: ALL reads — the heavy pitch aggregation AND the lineup / probable-pitcher
IDs — are DuckDB over S3. Snowflake is never opened.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.zone_matchup import lakehouse, profiles, viz
from betting_ml.scripts.zone_matchup.grid import GridSpec
from betting_ml.utils.game_day import current_game_date_iso  # INC-22 — US baseball-day, not UTC

_S3_BUCKET = "baseball-betting-ml-artifacts"
_S3_OVERLAY_PREFIX = "baseball/serving/zone_matchup/overlay"

# 3-year rolling window: enough seasonal history for stable EB profiles;
# mirrors the operator run-command in e13_10_zone_matchup_design.md §6.
_PROFILE_WINDOW_YEARS = 3


def _s3_put(key: str, body: bytes, content_type: str) -> str:
    import boto3
    boto3.client("s3", region_name="us-east-2").put_object(
        Bucket=_S3_BUCKET, Key=key, Body=body, ContentType=content_type,
    )
    return f"s3://{_S3_BUCKET}/{key}"


def _get_matchup_pairs(date_str: str) -> list[tuple[int, int]]:
    """Batter × opposing-starter pairs for date_str, from the S3 lakehouse (DuckDB).

    Batters from stg_statsapi_lineups (batting_order ≤ 9) crossed with the
    probable starter from the OPPOSING side in stg_statsapi_probable_pitchers.
    Returns list of (batter_id, pitcher_id) deduplicated pairs.
    Returns [] when lineup / starter data is not yet posted.

    Views are registered through the Delta-aware registrar — never a hardcoded
    lakehouse glob (the 2026-07-20 P0). Both date columns are real DATE types in
    the parquet (checked 2026-07-20), so no INC-23 VARCHAR cast is needed.
    """
    from betting_ml.utils.delta_lakehouse import register_lakehouse_views
    from betting_ml.utils.lakehouse_monitor import duck

    sql = """
    WITH lineups AS (
        SELECT game_pk,
               home_away,
               player_id AS batter_id
        FROM stg_statsapi_lineups
        WHERE official_date = ?::date
          AND player_id IS NOT NULL
          AND batting_order <= 9
    ),
    starters AS (
        SELECT game_pk,
               side AS starter_side,
               probable_pitcher_id AS pitcher_id
        FROM stg_statsapi_probable_pitchers
        WHERE game_date = ?::date
          AND probable_pitcher_id IS NOT NULL
    )
    SELECT DISTINCT l.batter_id, s.pitcher_id
    FROM lineups l
    JOIN starters s ON l.game_pk = s.game_pk
      -- home batters face the away starter; away batters face the home starter
      AND (
            (l.home_away = 'home' AND s.starter_side = 'away')
         OR (l.home_away = 'away' AND s.starter_side = 'home')
      )
    ORDER BY l.batter_id, s.pitcher_id
    """
    conn = duck()
    try:
        register_lakehouse_views(
            conn, ["stg_statsapi_lineups", "stg_statsapi_probable_pitchers"]
        )
        rows = conn.execute(sql, [date_str, date_str]).fetchall()
        return [(int(r[0]), int(r[1])) for r in rows]
    finally:
        conn.close()


def _hand_of_batter(bval: pd.DataFrame, batter_id: int) -> str:
    sub = bval[bval["batter_id"] == batter_id]
    return sub["b_hand"].mode().iloc[0] if not sub.empty else "R"


def _hand_of_pitcher(pfreq: pd.DataFrame, pitcher_id: int) -> str:
    sub = pfreq[pfreq["pitcher_id"] == pitcher_id]
    return sub["p_hand"].mode().iloc[0] if not sub.empty else "R"


def _player_names(con, ids: list[int]) -> dict:
    """Best-effort id→name from stg_ref_players in S3 (failures are non-fatal — names are cosmetic)."""
    if not ids:
        return {}
    try:
        glob = f"{lakehouse.BUCKET}/stg_ref_players/**/*.parquet"
        df = con.execute(
            f"SELECT * FROM read_parquet('{glob}', union_by_name=true) LIMIT 1"
        ).fetchdf()
        cols = {c.lower(): c for c in df.columns}
        idc = next((cols[c] for c in ("mlb_bam_id", "player_id", "mlbam_id", "mlb_id",
                                      "key_mlbam", "id") if c in cols), None)
        if not idc:
            return {}
        if "first_name" in cols and "last_name" in cols:
            namesel = f"trim({cols['first_name']} || ' ' || {cols['last_name']})"
        else:
            namec = next((cols[c] for c in cols if "name" in c), None)
            if not namec:
                return {}
            namesel = namec
        idlist = ",".join(str(int(i)) for i in ids)
        nm = con.execute(
            f"SELECT {idc} AS id, {namesel} AS nm "
            f"FROM read_parquet('{glob}', union_by_name=true) "
            f"WHERE {idc} IN ({idlist})"
        ).fetchdf()
        return {int(r.id): r.nm for r in nm.itertuples() if r.nm}
    except Exception as e:  # noqa: BLE001
        print(f"  [names] skipped ({e})", file=sys.stderr)
        return {}


def main() -> None:
    ap = argparse.ArgumentParser(description="E9.31b daily zone-overlay generator (WARN-tier)")
    ap.add_argument(
        "--date", default=None,
        help="Target date (YYYY-MM-DD); default = today",
    )
    ap.add_argument(
        "--days-back", type=int, default=0,
        help="Also generate for the N days before --date (backfill; >1 min for N≥14 — operator only)",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Print matched pairs; do not write to S3",
    )
    args = ap.parse_args()

    # INC-22 — the US baseball-day, NOT the raw UTC box clock. This op fires from the daily job
    # AND (post-E11.20-phase-2a) from lineup_monitor_job through the evening; a UTC date.today()
    # rolls to TOMORROW after ~17:00 PT, so the pair query asked for a date with no lineups and
    # the generator wrote nothing while still exiting 0. That is defect (a) of the three-week
    # zone-overlay outage.
    today_str = args.date or current_game_date_iso()
    today_dt = date.fromisoformat(today_str)

    # --- Step 1: Build profiles (once; reused for every target date) ---
    # Profile window: [start, today) exclusive — includes pitches through yesterday.
    # Using the same as-of date for all backfill dates keeps it fast (one profile build)
    # and quality-equivalent (EB is heavily regularised; a few extra days negligible).
    profile_start = (today_dt - timedelta(days=365 * _PROFILE_WINDOW_YEARS)).strftime("%Y-%m-%d")
    profile_end = today_str  # exclusive; pitches through (today - 1 day)

    grid = GridSpec()
    print(f"[zone-overlay] building profiles [{profile_start}, {profile_end}) from S3 lakehouse ...")
    con = lakehouse.connect()
    window = lakehouse.Window(profile_start, profile_end)

    league = lakehouse.league_raw(con, grid, window)
    braw = lakehouse.batter_raw(con, grid, window)
    praw = lakehouse.pitcher_raw(con, grid, window)
    bval = profiles.build_batter_value(braw, league, grid=grid)
    pfreq = profiles.build_pitcher_freq(praw, league)
    zbounds = lakehouse.batter_zone_bounds(con, window)
    sz_map = {int(r.batter_id): (r.sz_top, r.sz_bot) for r in zbounds.itertuples()}

    print(
        f"[zone-overlay] profiles ready — "
        f"batters:{bval['batter_id'].nunique()}  "
        f"pitchers:{pfreq['pitcher_id'].nunique()}  "
        f"cold-start batters:{bval.groupby('batter_id')['is_cold_start'].any().sum()}"
    )

    # Load player names (cosmetic; failure is non-fatal)
    all_ids = (bval["batter_id"].unique().tolist() + pfreq["pitcher_id"].unique().tolist())
    names = _player_names(con, all_ids)
    con.close()

    # --- Step 2: For each target date, fetch pairs and write overlays ---
    target_dates = [
        (today_dt - timedelta(days=d)).isoformat()
        for d in range(args.days_back + 1)
    ]

    total_written = 0
    total_skipped = 0

    for target_date in target_dates:
        print(f"[zone-overlay] fetching pairs for {target_date} from the S3 lakehouse ...")
        try:
            pairs = _get_matchup_pairs(target_date)
        except Exception as e:  # noqa: BLE001
            print(
                f"WARNING [zone-overlay] pair query failed for {target_date} "
                f"(non-fatal, skipping date): {e}",
                file=sys.stderr,
            )
            continue

        if not pairs:
            # ALERT-loud-but-continue, not a silent skip. A stdout note here is precisely how the
            # 2026-06-30 → 07-20 outage stayed invisible: every organic run found 0 pairs, said so
            # on stdout, and exited 0. On the pre-dawn daily run this is EXPECTED (no lineups yet);
            # from lineup_monitor_job it means something is actually wrong.
            print(
                f"WARNING [zone-overlay] {target_date}: 0 batter×starter pairs — no overlays will "
                f"be written for this date. Expected on a pre-lineup (pre-dawn) run; from an "
                f"intraday/lineup-triggered run it means lineups or probable pitchers are missing "
                f"from the lakehouse.",
                file=sys.stderr,
            )
            continue

        if args.dry_run:
            print(f"[zone-overlay] {target_date}: DRY-RUN — {len(pairs)} pairs (no S3 writes)")
            for bid, pid in pairs[:5]:
                b_name = names.get(bid, str(bid))
                p_name = names.get(pid, str(pid))
                print(f"    {b_name} ({bid}) vs {p_name} ({pid})")
            if len(pairs) > 5:
                print(f"    … ({len(pairs) - 5} more)")
            total_written += len(pairs)
            continue

        # Overlays land at today's as-of date so the backend's 3-day lookback finds them.
        as_of = today_str
        date_written = 0

        for bid, pid in pairs:
            try:
                b_hand = _hand_of_batter(bval, bid)
                p_hand = _hand_of_pitcher(pfreq, pid)
                sz_top, sz_bot = sz_map.get(bid, (None, None))
                overlay = viz.build_overlay(
                    bval, pfreq,
                    batter_id=bid, b_hand=b_hand,
                    pitcher_id=pid, p_hand=p_hand,
                    grid=grid, as_of_date=as_of,
                    sz_top=sz_top, sz_bot=sz_bot,
                    batter_name=names.get(bid),
                    pitcher_name=names.get(pid),
                )
                stem = f"{bid}_vs_{pid}"
                jkey = f"{_S3_OVERLAY_PREFIX}/as_of={as_of}/{stem}.json"
                _s3_put(jkey, json.dumps(overlay).encode(), "application/json")
                date_written += 1
            except Exception as e:  # noqa: BLE001
                print(
                    f"WARNING [zone-overlay] {bid}_vs_{pid} failed (non-fatal, skipping pair): {e}",
                    file=sys.stderr,
                )
                total_skipped += 1

        print(
            f"[zone-overlay] {target_date}: {date_written}/{len(pairs)} overlays → "
            f"s3://{_S3_BUCKET}/{_S3_OVERLAY_PREFIX}/as_of={as_of}/"
        )
        total_written += date_written

    if args.dry_run:
        print(f"[zone-overlay] DRY-RUN complete — {total_written} pairs would be written across {len(target_dates)} date(s)")
    else:
        print(f"[zone-overlay] done — {total_written} overlays written, {total_skipped} skipped")
        if total_written == 0:
            print(
                "WARNING [zone-overlay] wrote ZERO overlays across every target date — the "
                "Matchup Zone Analysis surface will have no data for this slate.",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
