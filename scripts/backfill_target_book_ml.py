"""backfill_target_book_ml.py — E9.52 repair of the target-book (Bovada) ML columns.

WHY (two distinct defects in the same read, both fixed at the source in scripts/predict_today.py):

  (1) BLANK — `daily_model_predictions.layer4_h2h_bovada_ml_home/away` wrote 100% NULL from
      2026-07-25 onward (and on the `morning` tier for longer) because the bridge date predicate
      compared a string-wrapped TIMESTAMP against a bare date (INC-23 class): the S3/DuckDB
      branch matched NOTHING, silently, with no exception for the graceful `except` to see.

  (2) WRONG — where the columns WERE populated, the value was not a real quote. The read took
      `MAX(price)` per side over the ENTIRE snapshot history (its trailing QUALIFY was a no-op
      over a group already collapsed to one row per event_id), so each side carried the most
      favourable price ever posted, mixed across snapshots and including IN-PLAY quotes. Game
      823601 on 2026-07-25 was graded home +900 / away +100 — BOTH POSITIVE, i.e. no single real
      quote could have produced it (both sides paying better than even loses the book money on
      balanced action). This inflates kill-criterion ROI, which is worse than NULL because it
      looks like data. ⚠️ Note a both-NEGATIVE pair (-109/-111) is the NORMAL near-pick'em quote,
      NOT a defect — the both-positive count is the honest smell test, and treating both-negative
      as broken over-counted this by ~40%. Only the live-capture era is affected (2026-05 onward, when
      intraday snapshots became dense); earlier rows came from a single-snapshot historical
      source where the per-side max coincides with the real pair.

WHAT IT WRITES:
    The AS-OF price: the latest SNAPSHOT-ALIGNED (both sides quoted in one ingestion_ts),
    STRICTLY PRE-FIRST-PITCH Bovada h2h quote with `ingestion_ts <= the row's own inserted_at`.
    Not the closing line — these columns feed the kill-criterion monitors as "the real-book
    price taken", and backfilling a closing price would grade a bet with information the bettor
    did not have. A row with no such snapshot is left NULL (honest: no price to take yet).

    Default: only rows where BOTH columns are currently NULL (defect 1) — idempotent, can never
    overwrite a genuine price. `--repair-existing` also rewrites rows whose stored pair DIFFERS
    from the as-of quote (defect 2). The dry run always reports both counts, so the operator
    sees the blast radius before authorising the rewrite.

TIER: operator-run repair, not a pipeline op. Snowflake writes are gated behind --apply; the
    default run is a DRY RUN that reports and exits 0.

Usage (EC2 BOX — needs the Snowflake write role):
    # 1. dry run — see how much is blank and how much is wrong
    docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
      python scripts/backfill_target_book_ml.py --env prod --start 2026-07-25 --end 2026-07-29
    # 2. fill the blanks
    docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
      python scripts/backfill_target_book_ml.py --env prod --start 2026-07-25 --end 2026-07-29 --apply
    # 3. (optional, wider) also correct the mixed-snapshot values in the live-capture era
    docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
      python scripts/backfill_target_book_ml.py --env prod --start 2026-05-01 --end 2026-07-29 \
      --repair-existing --apply
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

# Never roll a private Snowflake auth resolver — the shared one handles the box's INLINE key
# (INC-22 hardening); a local _load_private_key is the documented time-bomb.
from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.monitoring.target_book_coverage import TARGET_BOOK

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)


def _pred_schema(env: str) -> str:
    return "baseball_data.betting_ml" if env == "prod" else "baseball_data.dev_betting_ml"


# ⚠️ ONE SQL BODY, NO CTEs — deliberate. Snowflake's UPDATE grammar has NO CTE slot: a leading
# `with ... update ...` is a compile error (`unexpected 'update'`), unlike Postgres. Rather than
# keep a CTE version for the SELECT and a nested version for the UPDATE (two bodies that would
# drift), the whole pipeline is ONE self-contained nested SELECT that both statements wrap — the
# diagnose aggregates over it, the update joins to it. Portable, and impossible to desync.
#
# `game_date::date` on the bridge and the `::timestamp` casts on the leakage guard are the E9.52
# fixes — both columns are string-wrapped TIMESTAMPs in the lakehouse chain (INC-23), so an
# un-cast compare either matches nothing or raises.
_CLASSIFIED_BODY = """
select
    game_pk, prediction_type, score_date, inserted_at,
    stored_home, stored_away, ml_home, ml_away,
    (stored_home is null and stored_away is null)                    as is_blank,
    (not (stored_home is null and stored_away is null)
     and (stored_home is distinct from ml_home
          or stored_away is distinct from ml_away))                  as is_mismatch,
    -- ⚠️ BOTH-POSITIVE ONLY — do not "restore symmetry" here. A both-NEGATIVE pair is the NORMAL
    -- near-pick'em quote (-109/-111, -116/-104): it is exactly what a four-point-vig coin-flip
    -- game looks like, and 215 of the 964 CORRECT aligned quotes in 2026-05..07 are both-negative.
    -- Only both-POSITIVE is arithmetically impossible (both sides paying better than even means
    -- the book loses on balanced action; 0 of those 964 correct quotes are both-positive). The
    -- original symmetric form over-counted the defect (825 vs the real 583) and — worse — flagged
    -- freshly REPAIRED rows as broken, reporting stored-differs=0 alongside impossible>0.
    -- NOTE: keep this string free of literal per-cent signs. The connector binds by pyformat
    -- interpolation, so a bare one is read as a format spec and raises ValueError before the
    -- query is ever sent. Pinned by test_no_bare_percent_in_any_bound_sql.
    -- coalesce: a blank row's comparison is NULL, and a NULL flows through count_if into a
    -- NULL count, which then blows up int() in the reporting loop.
    coalesce(stored_home > 0 and stored_away > 0, false)            as is_impossible
from (
    select
        sv.game_pk, sv.prediction_type, sv.score_date, sv.inserted_at,
        sv.stored_home, sv.stored_away,
        s.ml_home, s.ml_away,
        row_number() over (
            partition by sv.game_pk, sv.prediction_type, sv.inserted_at
            order by s.ingestion_ts desc
        ) as rn
    from (
        select game_pk, prediction_type, score_date, inserted_at,
               layer4_h2h_bovada_ml_home as stored_home,
               layer4_h2h_bovada_ml_away as stored_away
        from {schema}.daily_model_predictions
        where score_date between %(s)s and %(e)s
    ) sv
    join (
        select game_pk, event_id
        from baseball_data.betting.mart_game_odds_bridge
        where game_date::date between %(s)s and %(e)s
          and event_id is not null
    ) b on b.game_pk = sv.game_pk
    -- Snapshot-ALIGNED pairs only (both sides quoted in the same ingestion_ts), strictly
    -- pre-first-pitch. Alignment stops a partial feed update pairing a fresh home price with a
    -- stale away price; the leakage guard stops an in-play quote being graded as the price taken.
    join (
        select o.event_id, o.ingestion_ts,
               max(case when o.is_home_outcome then o.outcome_price_american end) as ml_home,
               max(case when not o.is_home_outcome then o.outcome_price_american end) as ml_away
        from baseball_data.betting.mart_odds_outcomes o
        join (
            select event_id
            from baseball_data.betting.mart_game_odds_bridge
            where game_date::date between %(s)s and %(e)s
              and event_id is not null
        ) bb on bb.event_id = o.event_id
        where o.bookmaker_key = '{book}'
          and o.market_key = 'h2h'
          and o.ingestion_ts::timestamp < o.commence_time::timestamp
        group by o.event_id, o.ingestion_ts
        having count(distinct o.outcome_name) >= 2
    ) s on s.event_id = b.event_id
       and s.ingestion_ts::timestamp <= sv.inserted_at::timestamp
) ranked
where rn = 1
"""

_DIAGNOSE_SQL = """
select score_date,
       prediction_type,
       count(*)                    as rows_matched,
       count_if(is_blank)          as blank_rows,
       count_if(is_mismatch)       as mismatched_rows,
       count_if(is_impossible)     as impossible_stored_pairs
from (""" + _CLASSIFIED_BODY + """) c
group by score_date, prediction_type
order by score_date, prediction_type
"""

# Rows in the window with no as-of snapshot at all (they cannot be repaired — reported so the
# operator is not left wondering why a count does not reconcile).
_UNREPAIRABLE_SQL = """
select count(*)
from {schema}.daily_model_predictions
where score_date between %(s)s and %(e)s
  and layer4_h2h_bovada_ml_home is null
  and layer4_h2h_bovada_ml_away is null
"""

# ⚠️ NULL-SAFE JOIN ON prediction_type — load-bearing. 251 rows in 2026-05-08..2026-06-09 carry
# `prediction_type IS NULL`, and a plain `=` makes `NULL = NULL` UNKNOWN → those rows are reported
# as repairable by the diagnose (which GROUPs BY the column, and grouping DOES collapse NULLs
# together) and then SILENTLY SKIPPED by the write. That mismatch between "counted" and "written"
# is the exact silent-skip class this whole story is about, so the join must match NULL to NULL.
# Written as the explicit ANSI OR-form rather than `is not distinct from`: this is the statement
# that already failed once on a Snowflake grammar assumption, and the OR-form is valid everywhere
# (and is exercised against DuckDB in test_target_book_coverage_guard.py).
_UPDATE_SQL = """
update {schema}.daily_model_predictions dmp
set layer4_h2h_bovada_ml_home = c.ml_home,
    layer4_h2h_bovada_ml_away = c.ml_away
from (""" + _CLASSIFIED_BODY + """) c
where dmp.game_pk     = c.game_pk
  and dmp.inserted_at = c.inserted_at
  and (dmp.prediction_type = c.prediction_type
       or (dmp.prediction_type is null and c.prediction_type is null))
  and (c.ml_home is not null or c.ml_away is not null)
  and ({write_predicate})
"""

# ── --null-implausible: retire the both-positive rows the repair cannot fix ──────────────
# After --repair-existing has run, any REMAINING both-positive stored pair is one for which no
# aligned pre-game snapshot exists at or before the row's own inserted_at — so there is no honest
# value to write. Those rows hold an arithmetically impossible price (both sides paying better
# than even), which the kill-criterion ROI monitors consume as if it were real. A known-wrong
# number is worse than a missing one: NULL makes the monitors SKIP the row (they already count
# and report skips), whereas an impossible price silently inflates measured ROI.
_BOTH_POSITIVE_TOTAL_SQL = """
select count(*)
from {schema}.daily_model_predictions
where score_date between %(s)s and %(e)s
  and layer4_h2h_bovada_ml_home > 0
  and layer4_h2h_bovada_ml_away > 0
"""

# ⚠️ SAFETY INTERLOCK. A both-positive row that DOES have an as-of quote must be REPAIRED, not
# nulled — nulling it would throw away a recoverable real price. So --null-implausible refuses to
# run while any repairable both-positive row remains, and tells the operator to run
# --repair-existing first. Without this, running the flags in the wrong order destroys data.
_BOTH_POSITIVE_REPAIRABLE_SQL = """
select count(*)
from (""" + _CLASSIFIED_BODY + """) c
where c.is_impossible
  and (c.ml_home is not null or c.ml_away is not null)
"""

_NULL_IMPLAUSIBLE_SQL = """
update {schema}.daily_model_predictions
set layer4_h2h_bovada_ml_home = null,
    layer4_h2h_bovada_ml_away = null
where score_date between %(s)s and %(e)s
  and layer4_h2h_bovada_ml_home > 0
  and layer4_h2h_bovada_ml_away > 0
"""



def _null_implausible(args, start: date, end: date) -> int:
    """NULL the residual BOTH-POSITIVE rows — the ones no as-of quote can replace.

    Refuses while any repairable both-positive row remains, so running the passes out of order
    can never discard a recoverable price."""
    schema = _pred_schema(args.env)
    params = {"s": start, "e": end}
    log.info(f"[{args.env.upper()}] {TARGET_BOOK} ML — NULL implausible (both-positive) "
             f"{start}..{end} ({'APPLY' if args.apply else 'DRY RUN'})")

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_BOTH_POSITIVE_TOTAL_SQL.format(schema=schema), params)
        total = int(cur.fetchone()[0])
        cur.execute(_BOTH_POSITIVE_REPAIRABLE_SQL.format(schema=schema, book=TARGET_BOOK), params)
        repairable = int(cur.fetchone()[0])
        residual = total - repairable

        log.info(f"  both-positive stored rows: {total}  "
                 f"(repairable with a real as-of quote: {repairable}; residual: {residual})")
        print(f"[METRIC] target_book_both_positive_total={total}")
        print(f"[METRIC] target_book_both_positive_repairable={repairable}")
        print(f"[METRIC] target_book_both_positive_residual={residual}")

        if repairable > 0:
            log.error(
                f"REFUSING to null: {repairable} both-positive row(s) have a real as-of quote and "
                f"must be REPAIRED, not discarded. Run with --repair-existing --apply first, then "
                f"re-run this pass."
            )
            return 2
        if total == 0:
            log.info("No both-positive rows in the window — nothing to do.")
            return 0
        if not args.apply:
            log.info(f"DRY RUN — {total} row(s) would be set to NULL on both columns. "
                     f"Re-run with --apply.")
            return 0

        cur.execute(_NULL_IMPLAUSIBLE_SQL.format(schema=schema), params)
        nulled = cur.rowcount
        conn.commit()
        log.info(f"Nulled {nulled} row(s). The ROI monitors will now SKIP them (and say so) "
                 f"instead of grading a bet at a price that could not exist.")
        print(f"[METRIC] target_book_both_positive_nulled={nulled}")
    finally:
        conn.close()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=f"Repair the {TARGET_BOOK} ML columns on daily_model_predictions (E9.52)")
    p.add_argument("--env", choices=["prod", "dev"], default="prod")
    p.add_argument("--start", required=True, metavar="YYYY-MM-DD")
    p.add_argument("--end", required=True, metavar="YYYY-MM-DD")
    p.add_argument("--repair-existing", action="store_true",
                   help="Also rewrite rows whose STORED pair differs from the as-of quote "
                        "(defect 2 — the mixed-snapshot / in-play values). Default: blanks only.")
    p.add_argument("--null-implausible", action="store_true",
                   help="Separate mode: NULL the remaining BOTH-POSITIVE rows (arithmetically "
                        "impossible prices that no as-of quote can replace). Refuses to run while "
                        "any repairable both-positive row is left — run --repair-existing first.")
    p.add_argument("--apply", action="store_true",
                   help="Actually write. Without it this is a DRY RUN (reports only).")
    args = p.parse_args()

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if end < start:
        log.error("--end is before --start.")
        return 2
    if args.null_implausible and args.repair_existing:
        # Kept separate on purpose: one writes real prices, the other retires unusable ones, and
        # the interlock below depends on the repair having ALREADY completed.
        log.error("--null-implausible and --repair-existing are separate passes — run "
                  "--repair-existing (with --apply) first, then --null-implausible.")
        return 2
    if args.null_implausible:
        return _null_implausible(args, start, end)
    schema = _pred_schema(args.env)
    params = {"s": start, "e": end}
    mode = "blanks + mismatches" if args.repair_existing else "blanks only"
    log.info(f"[{args.env.upper()}] {TARGET_BOOK} ML repair {start}..{end} — scope: {mode}, "
             f"{'APPLY' if args.apply else 'DRY RUN'}")

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()

        cur.execute(_DIAGNOSE_SQL.format(schema=schema, book=TARGET_BOOK), params)
        blank = mismatch = impossible = 0
        null_tier_rows = 0
        tiers_seen: set[str] = set()
        for d, tier, n_rows, n_blank, n_mm, n_imp in cur.fetchall():
            blank += int(n_blank)
            mismatch += int(n_mm)
            impossible += int(n_imp)
            # `prediction_type` is NULL on 251 rows (2026-05-08..2026-06-09). str() because a bare
            # `{tier:<12}` on None raises TypeError and kills the whole run mid-report.
            label = "<null-tier>" if tier is None else str(tier)
            if tier is None:
                null_tier_rows += int(n_rows)
            tiers_seen.add(label)
            log.info(f"  {d} {label:<12} matched={int(n_rows):4d}  blank={int(n_blank):4d}  "
                     f"stored-differs={int(n_mm):4d}  both-positive={int(n_imp):4d}")

        cur.execute(_UNREPAIRABLE_SQL.format(schema=schema), params)
        still_blank = int(cur.fetchone()[0])
        no_snapshot = max(0, still_blank - blank)

        log.info(f"Blank rows repairable: {blank}  |  stored values that differ from the as-of "
                 f"quote: {mismatch} (of which {impossible} are BOTH-POSITIVE = arithmetically impossible)")
        if no_snapshot:
            log.warning(f"  {no_snapshot} blank row(s) have NO pre-game aligned {TARGET_BOOK} "
                        f"snapshot at or before their insert time — left NULL on purpose.")
        if null_tier_rows:
            log.warning(f"  {null_tier_rows} row(s) carry prediction_type IS NULL — included via a "
                        f"null-safe join (a plain '=' would count them here and skip them on write).")
        if "backfill" in tiers_seen:
            # Honest caveat: a `backfill` row's inserted_at postdates first pitch, so "as of
            # inserted_at" degenerates to the LAST PRE-GAME quote. That is the only defensible
            # value for a re-scored historical row (there was no scoring-time price), but it is
            # NOT the same semantics as a live morning/post_lineup row — do not read the two as
            # interchangeable when computing retrospective ROI.
            log.warning("  'backfill' tier rows are re-scores whose inserted_at postdates first "
                        f"pitch → their as-of price degenerates to the LAST PRE-GAME {TARGET_BOOK} "
                        "quote (not a price taken at scoring time).")
        print(f"[METRIC] target_book_repair_blank_rows={blank}")
        print(f"[METRIC] target_book_repair_mismatched_rows={mismatch}")
        print(f"[METRIC] target_book_repair_impossible_pairs={impossible}")
        print(f"[METRIC] target_book_repair_null_tier_rows={null_tier_rows}")

        target = blank + (mismatch if args.repair_existing else 0)
        if target == 0:
            log.info("Nothing in scope — nothing to do.")
            return 0
        if not args.apply:
            log.info(f"DRY RUN — {target} row(s) would be written. Re-run with --apply."
                     + ("" if args.repair_existing else
                        "  (Add --repair-existing to also correct the stored mixed-snapshot "
                        "values; the closing line is NOT a substitute for a missing price.)"))
            return 0

        predicate = ("c.is_blank or c.is_mismatch" if args.repair_existing else "c.is_blank")
        cur.execute(_UPDATE_SQL.format(schema=schema, book=TARGET_BOOK,
                                       write_predicate=predicate), params)
        updated = cur.rowcount
        conn.commit()
        log.info(f"Updated {updated} row(s).")
        print(f"[METRIC] target_book_repair_updated_rows={updated}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
