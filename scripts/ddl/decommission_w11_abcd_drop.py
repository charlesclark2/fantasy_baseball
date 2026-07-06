"""
scripts/ddl/decommission_w11_abcd_drop.py
E11.22 cost-banking — DROP the W11 A/B/C/D Snowflake RAW tables after the both→s3 cutover.

This is the step that actually banks the Snowflake bill: while the box is
W11_RAW_WRITE_MODE=both it pays for the dual write. This script drops the SF raw tables
whose prod consumers already read the S3 lakehouse (lakehouse_ext external tables), so
serving is provably unaffected.

REQUIRED ORDER (do NOT skip — dropping while writers still write SF breaks the next ingest):
  1. [both mode]  parity green:  python scripts/parity_check_w11.py     ← confirm S3 mirror == SF
  2. [host]       flip the env:  W11_RAW_WRITE_MODE: both → s3  in services/dagster/aws/.env
                  then redeploy:  docker compose -f services/dagster/aws/docker-compose.yml up -d --build
  3. [s3 mode]    run ONE clean daily_ingestion_job (writers now S3-only; serving green)
  4. [s3 mode]    THIS script --apply   (drops the SF raws)
  5. [laptop]     trim the now-dead SF-read bridges + monitor entries, commit + deploy (see FOLLOW-UPS
                  printed at the end of a run)

SAFETY (this script):
  * DRY-RUN by default; --apply is required to execute any DROP.
  * REFUSES to run unless W11_RAW_WRITE_MODE == 's3' (enforces flip-first). --force-mode overrides
    only if you have separately confirmed the writers no longer write these SF tables.
  * Per table, it confirms the prod lakehouse_ext CONSUMER returns rows BEFORE dropping the SF raw
    (so serving provably no longer depends on the SF table). A table whose consumer is empty/errors
    is SKIPPED, never dropped. NOTE: this is a NON-EMPTY backstop, NOT a completeness check — a
    consumer can have rows while its S3 mirror is still SHORT a few rows vs SF. So parity_check_w11.py
    (Step 1) is the AUTHORITATIVE per-table gate: pass ONLY the parity-GREEN sources via --tables.
  * --tables restricts the drop to an explicit allow-list (the sources that JUST passed parity).
    Omit it and the script only DRY-RUNs the full certified-safe set (it will still refuse --apply
    without --tables, so you can never bulk-drop a stale mirror by accident).
  * DDL runs through betting_ml.utils.data_loader.get_snowflake_connection (the box inline-key
    resolver); the Snowflake MCP role cannot run DDL.

player_transactions was cut over (E11.22): stg_statsapi_transactions now reads
lakehouse_ext.stg_statsapi_transactions, so it moved into DROP_SAFE + NIGHTLY_PREREQ
(W11TX_TRANSACTIONS_NIGHTLY must be ON so the ext table stays fresh — else it FREEZES on drop).

EXCLUDED (still deferred; do NOT drop here):
  * baseball_data.fangraphs.savant_park_factors_raw — fit_granular_park_priors.py now DEFAULTS to
    --s3 (nothing reads SF by accident), but its S3 input path must be reconciled to the writer-
    maintained lakehouse_raw mirror + box-verified before its drop.

Usage:
  # dry-run over the full certified-safe set (prints the plan; drops nothing):
  python scripts/ddl/decommission_w11_abcd_drop.py
  # execute — restricted to the parity-GREEN sources (required for --apply):
  python scripts/ddl/decommission_w11_abcd_drop.py --apply \
      --tables fg_stuff_plus_raw,fg_hitting_leaderboard_raw,catcher_framing_raw,sprint_speed_raw,umpire_game_log,public_betting_raw
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# (SF raw table to drop, the prod lakehouse_ext consumer that must return rows first).
# Every SF raw here was certified (E11.22 entry gate) to have its prod dbt model read the
# lakehouse_ext external table (source=0), not the SF source — so dropping it cannot affect serving
# once the consumer is confirmed populated AND kept fresh (see NIGHTLY_PREREQ).
DROP_SAFE: list[tuple[str, str]] = [
    ("baseball_data.fangraphs.fg_stuff_plus_raw",          "baseball_data.lakehouse_ext.stg_fangraphs__stuff_plus"),
    ("baseball_data.fangraphs.fg_hitting_leaderboard_raw", "baseball_data.lakehouse_ext.stg_fangraphs__hitting_leaderboard"),
    ("baseball_data.savant.sprint_speed_raw",              "baseball_data.lakehouse_ext.stg_batter_sprint_speed"),
    ("baseball_data.savant.catcher_framing_raw",           "baseball_data.lakehouse_ext.mart_catcher_framing"),
    ("baseball_data.external.oaa_team_season_raw",         "baseball_data.lakehouse_ext.mart_team_fielding_oaa"),
    ("baseball_data.statsapi.umpire_game_log",             "baseball_data.lakehouse_ext.stg_statsapi_umpire_game_log"),
    ("baseball_data.statsapi.weather_raw",                 "baseball_data.lakehouse_ext.stg_weather_raw"),
    ("baseball_data.actionnetwork.public_betting_raw",     "baseball_data.lakehouse_ext.stg_actionnetwork_public_betting"),
    # E11.22 read-cutover (was DEFERRED): stg_statsapi_transactions now reads lakehouse_ext.
    ("baseball_data.statsapi.player_transactions",         "baseball_data.lakehouse_ext.stg_statsapi_transactions"),
]

# A lakehouse_ext consumer reads a BUILT-model parquet that only stays fresh if its nightly rebuild
# gate is ON. A frozen-but-non-empty ext table would pass the "consumer returns rows" check yet
# FREEZE the feature on drop (the F2 umpire-null class). So for these, the drop ALSO requires the
# nightly flag = '1'. (fangraphs/sprint/catcher/oaa are W4/W5-tier and slow-moving — their freshness
# is confirmed by parity_check_w11 + the operator, not gated here.)
NIGHTLY_PREREQ = {
    "baseball_data.statsapi.umpire_game_log":         "W11B_UMPIRE_NIGHTLY",
    "baseball_data.statsapi.weather_raw":             "W11C_WEATHER_NIGHTLY",
    "baseball_data.actionnetwork.public_betting_raw": "W11D_PUBLIC_BETTING_NIGHTLY",
    "baseball_data.statsapi.player_transactions":     "W11TX_TRANSACTIONS_NIGHTLY",
}

# Deferred — a live consumer still reads the SF source; drop only after it is repointed + verified.
# savant_park_factors_raw: fit_granular_park_priors.py now DEFAULTS to --s3 (E11.22) so nothing reads
# SF by accident, but its S3 input path (baseball/lakehouse/savant_park_factors_raw/, maintained by
# export_w4) must be reconciled to the writer-maintained lakehouse_raw mirror + box-verified first.
DEFERRED = [
    "baseball_data.fangraphs.savant_park_factors_raw",
]


def _scalar(cur, sql: str) -> int | None:
    try:
        cur.execute(sql)
        return int(cur.fetchone()[0])
    except Exception as e:  # noqa: BLE001
        log.warning(f"    query failed ({e})")
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="E11.22 W11 A/B/C/D SF raw DROP (cost-banking).")
    ap.add_argument("--apply", action="store_true", help="Execute the DROPs (default: dry-run).")
    ap.add_argument("--tables", default=None,
                    help="Comma-separated table names (short or FQN) to restrict the drop to — pass "
                         "ONLY the sources that just passed parity_check_w11.py. REQUIRED with --apply.")
    ap.add_argument("--force-mode", action="store_true",
                    help="Skip the W11_RAW_WRITE_MODE=='s3' guard (only if you've confirmed the "
                         "writers no longer write these SF tables).")
    args = ap.parse_args()

    if args.apply and not args.tables:
        log.error(
            "[ABORT] --apply requires --tables (the parity-GREEN sources). Refusing to bulk-drop the "
            "full set — parity_check_w11.py is the authoritative gate and some mirrors may be stale "
            "(e.g. oaa_team_season_raw / weather_raw failed parity 2026-07-07)."
        )
        return 2

    mode = os.environ.get("W11_RAW_WRITE_MODE", "snowflake")
    log.info(f"W11_RAW_WRITE_MODE = {mode!r}; apply={args.apply}; force_mode={args.force_mode}")
    if mode != "s3" and not args.force_mode:
        log.error(
            "[ABORT] W11_RAW_WRITE_MODE is not 's3'. Dropping the SF raws while the writers still "
            "write them (both/snowflake mode) breaks the next ingest. Flip the env both→s3, redeploy, "
            "run one clean daily job, THEN re-run this. (--force-mode to override if already confirmed.)"
        )
        return 2

    log.info(f"DEFERRED (not dropped — live SF-source consumer): {', '.join(DEFERRED)}")

    selected = DROP_SAFE
    if args.tables:
        wanted = {t.strip().lower() for t in args.tables.split(",") if t.strip()}
        selected = [(r, c) for (r, c) in DROP_SAFE
                    if r.lower() in wanted or r.split(".")[-1].lower() in wanted]
        matched = {r.lower() for r, _ in selected} | {r.split(".")[-1].lower() for r, _ in selected}
        unknown = sorted(w for w in wanted if w not in matched)
        if unknown:
            log.warning(f"--tables names not in the certified-safe set (ignored): {unknown} "
                        f"(deferred/unknown — e.g. savant_park_factors_raw is intentionally not "
                        f"droppable here yet; see DEFERRED).")
        if not selected:
            log.error("[ABORT] --tables matched none of the certified-safe set.")
            return 2
        log.info(f"Restricted to {len(selected)} table(s) via --tables.")

    conn = get_snowflake_connection()
    to_drop: list[str] = []
    try:
        cur = conn.cursor()
        for raw, consumer in selected:
            log.info(f"• {raw}")
            raw_n = _scalar(cur, f"select count(*) from {raw}")
            if raw_n is None:
                log.info("    SF table not present (already dropped?) — skipping.")
                continue
            cons_n = _scalar(cur, f"select count(*) from {consumer}")
            if not cons_n:
                log.error(
                    f"    [SKIP] consumer {consumer} returned {cons_n} rows — the S3 mirror is NOT "
                    f"serving; refusing to drop {raw} (would risk a serving gap)."
                )
                continue
            prereq = NIGHTLY_PREREQ.get(raw)
            if prereq and os.environ.get(prereq) != "1":
                log.error(
                    f"    [SKIP] {prereq} is not '1' — the consumer {consumer.split('.')[-1]} reads a "
                    f"built-model parquet whose daily rebuild is NOT wired, so it would FREEZE on drop "
                    f"(the F2 umpire-null class). Flip {prereq}=1, confirm one daily job keeps it fresh, "
                    f"then drop {raw}."
                )
                continue
            log.info(f"    SF rows={raw_n:,}; consumer {consumer.split('.')[-1]} rows={cons_n:,}"
                     f"{f'; {prereq}=1' if prereq else ''} → SAFE to drop.")
            to_drop.append(raw)

        if not to_drop:
            log.warning("Nothing safe to drop (all skipped/absent). Check the consumer ext tables.")
            return 0

        if not args.apply:
            log.info("─" * 70)
            log.info("DRY-RUN. Would execute:")
            for raw in to_drop:
                log.info(f"    DROP TABLE IF EXISTS {raw};")
            log.info("Re-run with --apply to execute.")
            return 0

        for raw in to_drop:
            log.info(f"DROP TABLE IF EXISTS {raw} …")
            cur.execute(f"DROP TABLE IF EXISTS {raw}")
            log.info(f"    dropped {raw}")
        cur.close()
    finally:
        conn.close()

    log.info("─" * 70)
    log.info(f"DONE — dropped {len(to_drop)} SF raw table(s).")
    log.info("FOLLOW-UPS (laptop code — commit + deploy):")
    log.info("  1. Trim the now-dead SF→S3 bridges so they don't read dropped tables:")
    log.info("     export_w11_raw_to_s3.py, export_w4_raw_to_s3.py, export_w5_raw_to_s3.py,")
    log.info("     export_w7b_precursors_to_s3.py, parity_check_w11.py — remove the dropped tables.")
    log.info("  2. Remove the dropped tables' entries from check_data_freshness.py FRESHNESS_THRESHOLDS")
    log.info("     (they now point at dropped SF tables → would alert). COORDINATE — that file is")
    log.info("     owned by a concurrent session this cycle.")
    log.info("  3. Leave savant_park_factors_raw for its own repoint PR (S3 input path reconcile).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
