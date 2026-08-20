#!/usr/bin/env python3
"""
migrate_prediction_log_to_s3.py   (E11.24 P1 — ONE-TIME)
---------------------------------------------------------
Move `baseball_data.config.prediction_log` to the S3 lakehouse, repairing the rows a
known defect destroyed on the way.

This is the ONLY script in the story that reads Snowflake, and it is meant to be run
ONCE, by the operator, from the laptop. It writes NOTHING to Snowflake.

TWO THINGS, IN ONE PASS, ON PURPOSE
  1. REPAIR (the story's Step 0). Until the #885 fix landed on 2026-08-16, every scoped
     `predict_today --game-pks` run issued a DATE-WIDE `DELETE`, so each slate's log
     ended the day holding only the LAST batch's games. Measured: 1-2 games/date through
     2026-07-20..2026-08-15 against 8-15 in `daily_model_predictions`. Those rows are
     reconstructible — `daily_model_predictions` carries every input prediction_log
     derives from — so they are rebuilt here rather than migrating a hole.
  2. EXPORT. Every prediction_log row (repaired set included) is written to
     s3://.../lakehouse/prediction_log/dt=YYYY-MM-DD/part-<uuid>.parquet.

  Doing both in one pass is what keeps the repair out of Snowflake: the reconstruction
  reads `daily_model_predictions` from the S3 MIRROR (verified byte-parity with the
  Snowflake table: 59,337 rows total, 527/187 over the repair window), so no UPDATE or
  INSERT is ever issued against the warehouse.

WHAT THE REPAIR RECONSTRUCTS, AND FROM WHAT
  Per (score_date, game_pk) it takes the LATEST non-backfill `daily_model_predictions`
  row — which is exactly the run whose rows prediction_log would have been left holding —
  and derives:
      h2h    : model_prob = calibrated_win_prob, market = h2h_market_implied_prob,
               kelly = h2h_kelly_fraction
      totals : model_prob = totals_model_prob,   market = over_prob_consensus,
               kelly = totals_kelly_fraction
      decimal_odds = 1/market, ev = model_prob*(decimal_odds-1) - (1-model_prob)
  — the same projection `predict_today._prediction_log_rows` performs, and the same
  emit-only-when-the-market-price-exists rule.

  It only ADDS keys that are MISSING. A row that survived in Snowflake is migrated
  verbatim; the repair never overwrites a real logged value.

  `actual_outcome` / `closing_market_prob` are left NULL on reconstructed rows —
  `backfill_prediction_log.py` fills them on its next run, from the marts, which is
  strictly better than guessing them here.

VERIFY BEFORE YOU COMMIT TO IT
  `--dry-run` prints the per-date game-count parity table (prediction_log vs
  daily_model_predictions), before and after the repair, and writes nothing. Read it, then
  re-run without the flag. `--verify` re-reads the written parquet through the real
  `prediction_log` view and diffs it against Snowflake row-for-row.

Usage:
    uv run python scripts/migrate_prediction_log_to_s3.py --dry-run
    uv run python scripts/migrate_prediction_log_to_s3.py
    uv run python scripts/migrate_prediction_log_to_s3.py --verify
    uv run python scripts/migrate_prediction_log_to_s3.py --repair-start 2026-07-20
    uv run python scripts/migrate_prediction_log_to_s3.py --no-repair
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.utils import prediction_log_store as pred_log  # noqa: E402
from scripts.utils.lakehouse_read import duck_connect, register_views  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# The window the #885 defect actually damaged. Defaults match the story's Step 0; the
# parity table this script prints covers EVERY date, so the operator can widen it (the
# shortfall is visible from ~2026-07-20, not only from 08-02).
DEFAULT_REPAIR_START = date(2026, 8, 2)
DEFAULT_REPAIR_END = date(2026, 8, 15)

_SF_SELECT = """
SELECT prediction_date, game_pk, market, model_prob, market_prob_at_prediction,
       closing_market_prob, actual_outcome, decimal_odds, ev, kelly_fraction,
       model_version, loaded_at
FROM baseball_data.config.prediction_log
"""

_RECONSTRUCT_SQL = """
WITH latest AS (
    SELECT *
    FROM daily_model_predictions
    WHERE score_date >= $start AND score_date <= $end
      AND COALESCE(is_backfill, FALSE) = FALSE
    QUALIFY row_number() OVER (
        PARTITION BY score_date, game_pk ORDER BY inserted_at DESC
    ) = 1
)
SELECT score_date AS prediction_date, game_pk, 'h2h' AS market,
       calibrated_win_prob AS model_prob,
       h2h_market_implied_prob AS market_prob_at_prediction,
       model_version, inserted_at
FROM latest WHERE h2h_market_implied_prob IS NOT NULL
UNION ALL
SELECT score_date, game_pk, 'totals',
       totals_model_prob,
       over_prob_consensus,
       model_version, inserted_at
FROM latest WHERE over_prob_consensus IS NOT NULL
"""


def _snowflake_rows() -> list[dict]:
    """Every Snowflake prediction_log row, with `loaded_at` already canonicalised.

    ⚠️ The driver returns `loaded_at` as a `datetime` (it is TIMESTAMP_NTZ there) while the
    parquet column is a fixed-width ISO string. Coercing at the READ boundary, not at the
    write, is what keeps `_normalise_loaded_at` comparing like with like: a partially
    damaged game can have its h2h row surviving in Snowflake (datetime) and its totals row
    RECONSTRUCTED (already a string), and `max()` over a mixed group raises TypeError.
    """
    from betting_ml.utils.data_loader import get_snowflake_connection
    conn = get_snowflake_connection(schema="config")
    try:
        cur = conn.cursor()
        cur.execute(_SF_SELECT)
        cols = [d[0].lower() for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()
    for r in rows:
        r["loaded_at"] = pred_log.canonical_stamp(r["loaded_at"])
    return rows


def _reconstructed_rows(start: date, end: date) -> list[dict]:
    conn = duck_connect()
    register_views(conn, ["daily_model_predictions"])
    try:
        cur = conn.execute(_RECONSTRUCT_SQL, {"start": start, "end": end})
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def _project(row: dict) -> dict:
    """Reconstructed daily_model_predictions row → prediction_log row.

    ⚠️ `kelly_fraction` is RECOMPUTED here, NOT read from daily_model_predictions.
    The two tables mean different things by the same word: prediction_log stores
    `implied_kelly_fraction` = compute_kelly(compute_edge(model_prob, market), market) —
    the RAW calibrated-vs-market edge — while daily_model_predictions' `h2h_kelly_fraction`
    is derived from the POSTERIOR edge, which is ~0 because `best_alpha = 0`. Copying the
    column across would have silently zeroed every reconstructed Kelly.

    This was caught by diffing a reconstruction of four HEALTHY (post-#885-fix) dates
    against the rows predict_today actually logged: 112/112 keys matched, every column
    agreed to 1e-9 — except kelly_fraction, which was 0.0/None against real values like
    -0.0276. Verifying the reconstruction on dates where the real answer still EXISTS is
    the only way that difference surfaces.
    """
    from betting_ml.utils.probability_layer import compute_edge, compute_kelly

    mkt = row["market_prob_at_prediction"]
    model_prob = row["model_prob"]
    if mkt and mkt > 0:
        decimal_odds = 1.0 / mkt
        ev = (model_prob * (decimal_odds - 1) - (1 - model_prob)
              if model_prob is not None else None)
    else:
        decimal_odds = None
        ev = None
    return {
        "prediction_date":           row["prediction_date"],
        "game_pk":                   row["game_pk"],
        "market":                    row["market"],
        "model_prob":                model_prob,
        "market_prob_at_prediction": mkt,
        "closing_market_prob":       None,
        "actual_outcome":            None,
        "decimal_odds":              decimal_odds,
        "ev":                        ev,
        "kelly_fraction":            (compute_kelly(compute_edge(model_prob, mkt), mkt)
                                      if model_prob is not None and mkt else None),
        "model_version":             row["model_version"],
        "loaded_at":                 pred_log.utc_stamp(row["inserted_at"]),
    }


def _key(row) -> tuple:
    return (pred_log._iso_date(row["prediction_date"]), int(row["game_pk"]), row["market"])


def _games_per_date(rows) -> dict[str, set]:
    out: dict[str, set] = {}
    for r in rows:
        out.setdefault(pred_log._iso_date(r["prediction_date"]), set()).add(int(r["game_pk"]))
    return out


def _dmp_games_per_date() -> dict[str, set]:
    conn = duck_connect()
    register_views(conn, ["daily_model_predictions"])
    try:
        rows = conn.execute(
            "SELECT score_date, game_pk FROM daily_model_predictions "
            "WHERE COALESCE(is_backfill, FALSE) = FALSE"
        ).fetchall()
    finally:
        conn.close()
    out: dict[str, set] = {}
    for d, pk in rows:
        out.setdefault(pred_log._iso_date(d), set()).add(int(pk))
    return out


# A date is "SHORT" whenever prediction_log holds fewer games than
# daily_model_predictions — but that is NOT by itself the #885 defect. The 2024/2025
# historical dates are short for an unrelated and legitimate reason: the `--is-backfill`
# range scoring only ever logged the games it could price, so it was ALWAYS a subset.
# The #885 signature is specific and unmistakable — a near-EMPTY log (<=2 games) against
# a real slate (>=5) — and only that is worth repairing. Flagging the two differently is
# the difference between a readable table and 495 lines of noise.
_DEFECT_MAX_LOGGED = 2
_DEFECT_MIN_SLATE = 5


def _is_defect_signature(n_pl: int, n_dmp: int) -> bool:
    return n_pl <= _DEFECT_MAX_LOGGED and n_dmp >= _DEFECT_MIN_SLATE


def _print_parity(label: str, pl: dict[str, set], dmp: dict[str, set],
                  since: str | None) -> None:
    log.info("── per-date game-count parity (%s) ──", label)
    log.info("    %-12s %8s %8s  %s", "date", "pred_log", "dmp", "")
    short = defect = shown = 0
    for d in sorted(pl):
        n_pl, n_dmp = len(pl[d]), len(dmp.get(d, set()))
        is_defect = _is_defect_signature(n_pl, n_dmp)
        short += n_pl < n_dmp
        defect += is_defect
        if since is not None and d < since:
            continue
        shown += 1
        flag = "#885 DEFECT" if is_defect else ("short" if n_pl < n_dmp else "ok")
        log.info("    %-12s %8d %8d  %s", d, n_pl, n_dmp, flag)
    log.info("    shown %d date(s) from %s; over ALL %d date(s): %d short, "
             "%d carrying the #885 signature (<=%d logged vs >=%d scheduled).",
             shown, since or "the beginning", len(pl), short, defect,
             _DEFECT_MAX_LOGGED, _DEFECT_MIN_SLATE)


def _normalise_loaded_at(rows: list[dict]) -> None:
    """One `loaded_at` per (date, game) — the view resolves a game to the latest batch
    that OWNED it, so two markets of one game carrying different stamps would drop the
    older one. Measured on the live table this is a no-op (0 games carry >1 distinct
    loaded_at); it is here so the migration cannot depend on that staying true."""
    newest: dict[tuple, str] = {}
    for r in rows:
        k = (pred_log._iso_date(r["prediction_date"]), int(r["game_pk"]))
        stamp = r["loaded_at"]
        if k not in newest or stamp > newest[k]:
            newest[k] = stamp
    for r in rows:
        r["loaded_at"] = newest[(pred_log._iso_date(r["prediction_date"]), int(r["game_pk"]))]


def _verify(sf_rows: list[dict]) -> int:
    conn = pred_log.connect()
    try:
        cur = conn.execute(
            "SELECT prediction_date, game_pk, market, model_prob, actual_outcome, "
            "closing_market_prob FROM prediction_log"
        )
        s3 = {(pred_log._iso_date(r[0]), int(r[1]), r[2]): (r[3], r[4], r[5])
              for r in cur.fetchall()}
    finally:
        conn.close()
    sf = {_key(r): (r["model_prob"], r["actual_outcome"], r["closing_market_prob"])
          for r in sf_rows}
    only_sf = set(sf) - set(s3)
    only_s3 = set(s3) - set(sf)
    mism = [k for k in set(sf) & set(s3) if not _values_match(sf[k], s3[k])]
    log.info("VERIFY: snowflake=%d  s3=%d  only_in_sf=%d  only_in_s3=%d  value_mismatch=%d",
             len(sf), len(s3), len(only_sf), len(only_s3), len(mism))
    for k in list(only_sf)[:5]:
        log.warning("  only in snowflake: %s", k)
    for k in list(mism)[:5]:
        log.warning("  mismatch %s: sf=%s s3=%s", k, sf[k], s3[k])
    return len(only_sf) + len(mism)


def _values_match(a, b) -> bool:
    """Row-value equality with a float tolerance (parquet float64 vs Snowflake FLOAT)."""
    for x, y in zip(a, b):
        if x is None or y is None:
            if x is not y and (x is None) != (y is None):
                return False
            continue
        if abs(float(x) - float(y)) > 1e-9:
            return False
    return True


def run(*, repair_start: date | None, repair_end: date, dry_run: bool,
        verify: bool, parity_since: str | None = "2026-07-01") -> None:
    log.info("Reading baseball_data.config.prediction_log …")
    sf_rows = _snowflake_rows()
    log.info("  %d row(s), %d date(s)", len(sf_rows), len(_games_per_date(sf_rows)))

    dmp = _dmp_games_per_date()
    _print_parity("BEFORE repair", _games_per_date(sf_rows), dmp, since=parity_since)

    rows = list(sf_rows)
    if repair_start is not None:
        have = {_key(r) for r in rows}
        candidates = _reconstructed_rows(repair_start, repair_end)
        added = [_project(r) for r in candidates if _key(r) not in have]
        log.info("Repair window %s..%s: %d candidate row(s), %d missing key(s) reconstructed.",
                 repair_start, repair_end, len(candidates), len(added))
        rows.extend(added)
        _print_parity("AFTER repair", _games_per_date(rows), dmp, since=parity_since)

    _normalise_loaded_at(rows)

    by_date: dict[str, list[dict]] = {}
    for r in rows:
        by_date.setdefault(pred_log._iso_date(r["prediction_date"]), []).append(r)

    if dry_run:
        # ⚠️ A DRY RUN THAT SKIPS SERIALISATION IS NOT A REHEARSAL. The first cut returned
        # here, so `--dry-run` validated the parity arithmetic and NOTHING about whether the
        # rows could actually be written — and the real run then died on the first partition
        # (`Expected bytes, got a 'datetime.datetime' object`, a `loaded_at` the Snowflake
        # driver returns as a datetime). Build every partition's arrow table here; it is the
        # whole write path minus the PUT, costs ~a second, and would have caught it.
        for d, part in sorted(by_date.items()):
            parquet_rows, dropped = pred_log.normalise_rows(part, d, loaded_at=pred_log.utc_stamp())
            pred_log.rows_to_arrow_table(parquet_rows)
            if dropped:
                log.warning("  %s: %d row(s) would be DROPPED (un-coercible game_pk): %s",
                            d, len(dropped), dropped)
        log.info("[DRY RUN] would write %d row(s) across %d partition(s) to %s — every "
                 "partition serialised OK; nothing written.",
                 len(rows), len(by_date), pred_log.LOC)
        return

    written = 0
    for i, (d, part) in enumerate(sorted(by_date.items()), start=1):
        result = pred_log.write_rows(part, d, scoped_game_pks=None)
        written += result["data_rows"]
        if i % 50 == 0 or i == len(by_date):
            log.info("  %d/%d partitions written (%d rows so far)", i, len(by_date), written)
    log.info("Migration complete — %d row(s) across %d partition(s) → %s",
             written, len(by_date), pred_log.LOC)

    if verify:
        bad = _verify(sf_rows)
        if bad:
            log.error("VERIFY FAILED — %d row(s) did not round-trip.", bad)
            sys.exit(1)
        log.info("VERIFY OK — every Snowflake row round-trips through the S3 view.")


def main() -> None:
    ap = argparse.ArgumentParser(description="One-time prediction_log Snowflake → S3 migration.")
    ap.add_argument("--repair-start", default=DEFAULT_REPAIR_START.isoformat())
    ap.add_argument("--repair-end", default=DEFAULT_REPAIR_END.isoformat())
    ap.add_argument("--no-repair", action="store_true",
                    help="Migrate verbatim; do not reconstruct the rows the #885 defect ate.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the parity tables and the write plan; write nothing.")
    ap.add_argument("--parity-since", default="2026-07-01", metavar="YYYY-MM-DD",
                    help="Earliest date printed in the parity table (the counts are "
                         "computed over EVERY date regardless). Use 1900-01-01 for all.")
    ap.add_argument("--verify", action="store_true",
                    help="After writing, diff the S3 view against Snowflake row-for-row.")
    args = ap.parse_args()

    run(
        repair_start=None if args.no_repair else date.fromisoformat(args.repair_start),
        repair_end=date.fromisoformat(args.repair_end),
        dry_run=args.dry_run,
        verify=args.verify,
        parity_since=args.parity_since,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        log.error("Migration failed: %s", exc)
        sys.exit(1)
