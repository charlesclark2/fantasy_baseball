"""
validate_fangraphs_pipeline.py
-------------------------------
End-to-end validation of the FanGraphs ingestion pipeline.

Checks:
  1. Raw table row counts (raw tables populated)
  2. MLBAM ID join rate for ZiPS pitchers (≥95% match to ref_players)
  3. Null rate for Stuff+ in staging model (< 10% null)
  4. Duplicate grain check on mart models (0 duplicates)

Results are written to betting_ml/evaluation/fangraphs_validation.md.

Usage:
    uv run python scripts/validate_fangraphs_pipeline.py --season 2026
    uv run python scripts/validate_fangraphs_pipeline.py --season 2025
"""

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "utils"))
from snowflake_loader import get_snowflake_connection  # noqa: E402

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def _query(conn: snowflake.connector.SnowflakeConnection, sql: str):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def validate(season: int, conn) -> dict:
    results = {}

    # Step 1 — Raw table row counts
    # E11.22 DROPPED (2026-07-09): fg_stuff_plus_raw + fg_hitting_leaderboard_raw were dropped from
    # Snowflake post both→s3 cutover (now S3-only via lakehouse_raw/). Their freshness/coverage is now
    # validated by parity_check_w11.py + the served feature-block coverage guard, NOT this SF-side tool.
    # The window-type check on fg_hitting_leaderboard_raw was removed for the same reason. Only the
    # not-yet-migrated ZiPS SF tables remain checkable here:
    log.info("Step 1: Raw table row counts")
    for table, label, minimum in [
        ("baseball_data.fangraphs.fg_zips_pitching_raw",    "zips_pitching_raw",    400),
        ("baseball_data.fangraphs.fg_zips_hitting_raw",     "zips_hitting_raw",     700),
    ]:
        rows = _query(conn, f"SELECT COUNT(*) FROM {table}")[0][0]
        status = "PASS" if rows >= minimum else "FAIL"
        log.info("  %s: %d rows  [%s ≥ %d]", label, rows, status, minimum)
        results[f"{label}_count"] = rows
        results[f"{label}_count_status"] = status

    # Step 2 — MLBAM ID join rate for ZiPS pitchers (MLB-active only)
    # Minor league / prospect pitchers use 'sa'-prefixed fg_pitcher_id and are absent
    # from savant.ref_players by design — they have no MLB appearances. Scoping to
    # numeric fg_pitcher_id restricts the check to players who have appeared in MLB.
    log.info("Step 2: MLBAM ID join rate (ZiPS MLB pitchers → ref_players)")
    join_sql = f"""
        WITH zips AS (
            SELECT DISTINCT
                raw_json:MLBAMID::varchar AS mlbam_id,
                raw_json:Name::varchar    AS pitcher_name
            FROM baseball_data.fangraphs.fg_zips_pitching_raw
            WHERE season = {season}
              AND source_endpoint = 'csv_manual_download'
              AND NOT STARTSWITH(fg_pitcher_id, 'sa')
        ),
        ref AS (
            SELECT DISTINCT mlb_bam_id::varchar AS mlb_bam_id
            FROM baseball_data.savant.ref_players
        )
        SELECT
            COUNT(*)                                     AS total_pitchers,
            COUNT(r.mlb_bam_id)                          AS matched,
            COUNT(*) - COUNT(r.mlb_bam_id)               AS unmatched,
            ROUND(COUNT(r.mlb_bam_id) * 100.0 / NULLIF(COUNT(*), 0), 2) AS match_pct
        FROM zips z
        LEFT JOIN ref r ON z.mlbam_id = r.mlb_bam_id
        WHERE z.mlbam_id IS NOT NULL
    """
    row = _query(conn, join_sql)[0]
    total, matched, unmatched, match_pct = row
    match_pct = float(match_pct or 0)
    join_ok = match_pct >= 95.0
    log.info(
        "  ZiPS pitchers season=%d: total=%d matched=%d unmatched=%d match_pct=%.1f%%  [%s]",
        season, total, matched, unmatched, match_pct, "PASS" if join_ok else "FAIL",
    )
    results["zips_pitcher_join_total"] = total
    results["zips_pitcher_join_matched"] = matched
    results["zips_pitcher_join_unmatched"] = unmatched
    results["zips_pitcher_join_pct"] = match_pct
    results["zips_pitcher_join_status"] = "PASS" if join_ok else "FAIL"

    # Log unmatched names for manual review
    if unmatched > 0:
        unmatched_rows = _query(conn, f"""
            WITH zips AS (
                SELECT DISTINCT
                    raw_json:MLBAMID::varchar AS mlbam_id,
                    raw_json:Name::varchar    AS pitcher_name
                FROM baseball_data.fangraphs.fg_zips_pitching_raw
                WHERE season = {season}
                  AND source_endpoint = 'csv_manual_download'
                  AND NOT STARTSWITH(fg_pitcher_id, 'sa')
            ),
            ref AS (
                SELECT DISTINCT mlb_bam_id::varchar AS mlb_bam_id
                FROM baseball_data.savant.ref_players
            )
            SELECT z.pitcher_name, z.mlbam_id
            FROM zips z
            LEFT JOIN ref r ON z.mlbam_id = r.mlb_bam_id
            WHERE r.mlb_bam_id IS NULL
              AND z.mlbam_id IS NOT NULL
            ORDER BY 1
            LIMIT 20
        """)
        results["zips_pitcher_unmatched_sample"] = [{"name": r[0], "mlbam_id": r[1]} for r in unmatched_rows]
        for name, mlbam in unmatched_rows[:10]:
            log.info("    unmatched: %s (mlbam=%s)", name, mlbam)

    # Step 3 — Null Stuff+ rate in staging
    log.info("Step 3: Null Stuff+ rate in stg_fangraphs__stuff_plus")
    null_sql = f"""
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN stuff_plus IS NULL THEN 1 END) AS null_stuff
        FROM baseball_data.betting.stg_fangraphs__stuff_plus
        WHERE season = {season}
    """
    row = _query(conn, null_sql)[0]
    total_stg, null_stuff = row
    null_rate = (null_stuff / total_stg * 100) if total_stg else 0
    null_ok = null_rate < 10.0
    log.info(
        "  season=%d: total=%d null_stuff=%d null_rate=%.1f%%  [%s]",
        season, total_stg, null_stuff, null_rate, "PASS" if null_ok else "FAIL",
    )
    results["stuff_plus_staging_total"] = total_stg
    results["stuff_plus_null_count"] = null_stuff
    results["stuff_plus_null_pct"] = round(null_rate, 2)
    results["stuff_plus_null_status"] = "PASS" if null_ok else "FAIL"

    # Step 4 — Duplicate grain check on mart models
    log.info("Step 4: Duplicate grain checks on mart models")
    for model, grain in [
        ("baseball_data.betting.fct_fangraphs_pitching_analytics", "fg_pitcher_id, season"),
        ("baseball_data.betting.fct_fangraphs_hitting_analytics",  "fg_batter_id, season"),
    ]:
        model_short = model.split(".")[-1]
        dup_rows = _query(conn, f"""
            SELECT {grain}, COUNT(*) AS cnt
            FROM {model}
            GROUP BY {grain}
            HAVING cnt > 1
            LIMIT 5
        """)
        dup_ok = len(dup_rows) == 0
        log.info("  %s: %d duplicate grains  [%s]", model_short, len(dup_rows), "PASS" if dup_ok else "FAIL")
        results[f"{model_short}_dup_status"] = "PASS" if dup_ok else "FAIL"
        results[f"{model_short}_dup_count"] = len(dup_rows)

    return results


def write_validation_md(season: int, results: dict) -> Path:
    out_path = Path(__file__).parent.parent / "betting_ml" / "evaluation" / "fangraphs_validation.md"
    overall = "PASS" if all(v == "PASS" for k, v in results.items() if k.endswith("_status")) else "FAIL"

    lines = [
        f"# FanGraphs Pipeline Validation — Season {season}",
        "",
        f"**Date:** {date.today().isoformat()}  ",
        f"**Overall:** {overall}",
        "",
        "## Raw Table Row Counts",
        "",
        "| Table | Rows | Status |",
        "|-------|------|--------|",
        f"| fg_stuff_plus_raw | {results.get('stuff_plus_raw_count', 'N/A')} | {results.get('stuff_plus_raw_count_status', 'N/A')} |",
        f"| fg_zips_pitching_raw | {results.get('zips_pitching_raw_count', 'N/A')} | {results.get('zips_pitching_raw_count_status', 'N/A')} |",
        f"| fg_zips_hitting_raw | {results.get('zips_hitting_raw_count', 'N/A')} | {results.get('zips_hitting_raw_count_status', 'N/A')} |",
        f"| fg_hitting_leaderboard_raw | {results.get('hitting_leaderboard_raw_count', 'N/A')} | {results.get('hitting_leaderboard_raw_count_status', 'N/A')} |",
        "",
        f"Hitting leaderboard window types present: {results.get('hitting_leaderboard_window_types', [])}",
        "",
        "## MLBAM ID Join Rate (ZiPS Pitchers)",
        "",
        f"- Total ZiPS pitchers (season={season}): {results.get('zips_pitcher_join_total', 'N/A')}",
        f"- Matched to ref_players: {results.get('zips_pitcher_join_matched', 'N/A')}",
        f"- Unmatched: {results.get('zips_pitcher_join_unmatched', 'N/A')}",
        f"- Match rate: {results.get('zips_pitcher_join_pct', 'N/A')}%  **{results.get('zips_pitcher_join_status', 'N/A')}**",
        "",
    ]

    unmatched = results.get("zips_pitcher_unmatched_sample", [])
    if unmatched:
        lines += [
            "### Unmatched Pitchers (sample)",
            "",
            "| Name | MLBAM ID |",
            "|------|----------|",
        ]
        for p in unmatched[:20]:
            lines.append(f"| {p['name']} | {p['mlbam_id']} |")
        lines.append("")

    lines += [
        "## Stuff+ Null Rate (Staging)",
        "",
        f"- Total pitchers in stg_fangraphs__stuff_plus (season={season}): {results.get('stuff_plus_staging_total', 'N/A')}",
        f"- Null stuff_plus: {results.get('stuff_plus_null_count', 'N/A')}",
        f"- Null rate: {results.get('stuff_plus_null_pct', 'N/A')}%  **{results.get('stuff_plus_null_status', 'N/A')}**",
        "",
        "## Mart Model Duplicate Grain Checks",
        "",
        f"- fct_fangraphs_pitching_analytics: {results.get('fct_fangraphs_pitching_analytics_dup_count', 'N/A')} duplicate grains  **{results.get('fct_fangraphs_pitching_analytics_dup_status', 'N/A')}**",
        f"- fct_fangraphs_hitting_analytics: {results.get('fct_fangraphs_hitting_analytics_dup_count', 'N/A')} duplicate grains  **{results.get('fct_fangraphs_hitting_analytics_dup_status', 'N/A')}**",
        "",
        "## Known Gaps",
        "",
        "- **MLBAM join rate (MLB-active pitchers only)**: ZiPS projects minor league and prospect pitchers",
        "  whose `fg_pitcher_id` has an 'sa' prefix. These players have no MLB appearances and are absent",
        "  from `savant.ref_players`. The join rate check excludes 'sa'-prefixed IDs to measure only",
        "  MLB-active pitchers, where ≥95% match is expected.",
        "- ZiPS CSV projections do not include K% or BB% directly (K/9 and BB/9 are available instead).",
        "- xFIP is not included in ZiPS CSV exports; proj_xfip will be null for CSV-sourced rows.",
        "- Stuff+ rolling windows (14d, 30d) are stored in raw table but staging dedups to one row per pitcher×season.",
    ]

    out_path.write_text("\n".join(lines) + "\n")
    log.info("Validation results written to %s", out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the FanGraphs ingestion pipeline")
    parser.add_argument("--season", type=int, default=date.today().year)
    args = parser.parse_args()

    conn = get_snowflake_connection()
    try:
        results = validate(args.season, conn)
    finally:
        conn.close()

    out_path = write_validation_md(args.season, results)

    all_pass = all(v == "PASS" for k, v in results.items() if k.endswith("_status"))
    if not all_pass:
        log.warning("One or more validation checks FAILED — see %s", out_path)
        sys.exit(1)
    log.info("All validation checks PASSED.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Validation failed")
        sys.exit(1)
