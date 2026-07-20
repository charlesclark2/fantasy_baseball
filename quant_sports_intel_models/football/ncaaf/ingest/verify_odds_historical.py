"""verify_odds_historical.py  (NCAAF-P0.6 — the historical-odds backfill verifier)
===================================================================================
A re-runnable acceptance check for the `odds_ncaaf_historical` Delta table (the paid
`/historical` CLOSING game lines landed by `odds_backfill.py`). Reads the lake back through
`query_lake` (DuckDB over the S3 Delta — no warehouse, no credits) and reports the things
that actually gate P1.4's vs-market eval + Phase 2:

  A. Per-season coverage — rows, distinct events, commence + snapshot date ranges.
  B. FBS coverage vs the CFBD schedule — distinct odds events ÷ FBS games/season. This is the
     STRONGEST completeness signal: a capped verification stub (e.g. `--max-events 3`) or a
     partial pull shows up here as a tiny % (the 2024 backfill skipped by `--skip-existing`
     read 0.3% until re-pulled). ≥80% = complete (odds can exceed 100% — it also prices some
     FCS games the FBS count omits).
  C. Market coverage — share of events whose bookmakers carry h2h / spreads / totals.
  D. Leakage guard — the belt-and-suspenders `_snapshot_ts < commence_time`. A ~20-25% row-level
     "violation" rate is EXPECTED and harmless: the ±30-min window captures a game under a
     neighbouring FBS kickoff's snapshot too, and P1.4 keeps only the latest snapshot < commence
     per event. What matters is that every distinct game retains ≥1 leakage-safe close. A small
     ORPHAN count (a game with NO safe row) is also expected: `_season_kickoffs` anchors snapshots
     on FBS kickoffs ONLY, so a non-FBS game swept in as ±30-min collateral can lack an own-window
     snapshot. Those are outside the modelling universe and P1.4 drops them — so orphans FAIL the
     run only above `ORPHAN_FAIL_FRAC` of all games (a systemic snapshot/time bug), not a handful.
  E. Distinct sportsbooks present (incl. Bovada, the target book).

The asserted season range defaults CLOCK-DERIVED (floor → last COMPLETED season), so a newly
finished season shows up as a MISSING partition instead of silently going unnoticed.

Run on the LAPTOP (has AWS read creds), repo root — a pure read, instant:
  uv run python -m quant_sports_intel_models.football.ncaaf.ingest.verify_odds_historical
  uv run python -m quant_sports_intel_models.football.ncaaf.ingest.verify_odds_historical --seasons 2020-2025

Exit code 0 = PASS, 1 = FAIL (a genuinely missing/partial partition, a below-floor partition, or
a systemic orphan rate) — so it can gate a CI/handoff step, not just print.
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from .handler import _parse_seasons
from .query_lake import delta, q
from .sources import NCAAF_HISTORICAL_FLOOR, default_backfill_seasons

# A partition covering < this fraction of the CFBD FBS schedule is a partial/stub pull → FAIL.
COVERAGE_MIN_FRAC = 0.80
# Orphaned games (no leakage-safe close) above this fraction of ALL games = a systemic snapshot/
# time bug → FAIL. Below it = expected non-FBS neighbour-window collateral (informational).
ORPHAN_FAIL_FRAC = 0.01


def _fmt(df: pd.DataFrame) -> str:
    return df.to_string(index=False)


def verify(seasons: list[int], *, source: str = "odds_ncaaf_historical") -> bool:
    D = delta(source)
    pd.set_option("display.width", 240)
    pd.set_option("display.max_colwidth", 40)
    ok = True

    print("=" * 90)
    print("A. Per-season coverage (rows, distinct events, commence range, snapshot range)")
    print("=" * 90)
    a = q(f"""
        select season,
               count(*)                                                as rows,
               count(distinct json_extract_string(raw_json,'$.id'))    as events,
               min(json_extract_string(raw_json,'$.commence_time'))    as first_game,
               max(json_extract_string(raw_json,'$.commence_time'))    as last_game,
               min(json_extract_string(raw_json,'$._snapshot_ts'))     as first_snap,
               max(json_extract_string(raw_json,'$._snapshot_ts'))     as last_snap
        from {D} group by 1 order by 1
    """)
    print(_fmt(a))
    present = set(a["season"].astype(int))
    missing = [s for s in seasons if s not in present]
    below_floor = sorted(s for s in present if s < NCAAF_HISTORICAL_FLOOR)

    print("\n" + "=" * 90)
    print("B. FBS coverage vs the CFBD schedule (distinct odds events ÷ FBS games/season)")
    print(f"   < {COVERAGE_MIN_FRAC:.0%} ⇒ a partial/stub pull → re-pull that season WITHOUT --skip-existing")
    print("=" * 90)
    b = q(f"""
        with g as (
            select json_extract_string(raw_json,'$.season')::int as season,
                   count(*) filter (where json_extract_string(raw_json,'$.homeClassification')='fbs'
                                       or json_extract_string(raw_json,'$.awayClassification')='fbs') as fbs_games
            from {delta('games')} group by 1
        ),
        o as (
            select season, count(distinct json_extract_string(raw_json,'$.id')) as odds_events
            from {D} group by 1
        )
        select o.season, g.fbs_games, o.odds_events,
               round(100.0*o.odds_events/nullif(g.fbs_games,0),1) as pct_covered
        from o left join g using(season) order by o.season
    """)
    print(_fmt(b))
    partial = b[(b["fbs_games"].notna()) & (b["pct_covered"] < COVERAGE_MIN_FRAC * 100)]

    print("\n" + "=" * 90)
    print("C. Market coverage per season (share of events whose bookmakers carry each market key)")
    print("=" * 90)
    c = q(f"""
        with mk as (
            select ev.season, json_extract_string(ev.raw_json,'$.id') as event_id,
                   json_extract_string(m,'$.key') as market
            from (select season, raw_json from {D}) ev,
                 unnest(cast(json_extract(ev.raw_json,'$.bookmakers') as json[])) as b(bm),
                 unnest(cast(json_extract(bm,'$.markets')            as json[])) as t(m)
        ),
        per_ev as (
            select season, event_id,
                   max((market='h2h')::int) h2h, max((market='spreads')::int) spreads,
                   max((market='totals')::int) totals
            from mk group by 1,2
        )
        select season, count(*) events,
               round(100.0*avg(h2h),1) pct_h2h,
               round(100.0*avg(spreads),1) pct_spreads,
               round(100.0*avg(totals),1) pct_totals
        from per_ev group by 1 order by 1
    """)
    print(_fmt(c))

    print("\n" + "=" * 90)
    print("D. Leakage guard + orphan analysis (see module docstring — orphans are usually non-FBS)")
    print("=" * 90)
    d = q(f"""
        select season, count(*) total,
               sum((json_extract_string(raw_json,'$._snapshot_ts')
                    <  json_extract_string(raw_json,'$.commence_time'))::int) leakage_safe,
               sum((json_extract_string(raw_json,'$._snapshot_ts')
                    >= json_extract_string(raw_json,'$.commence_time'))::int) violations
        from {D} group by 1 order by 1
    """)
    d["viol_pct"] = (100.0 * d["violations"] / d["total"]).round(2)
    print(_fmt(d))

    orphans = q(f"""
        with ev as (
            select json_extract_string(raw_json,'$.id') event_id,
                   any_value(season) part_season,
                   any_value(json_extract_string(raw_json,'$.home_team')) home,
                   any_value(json_extract_string(raw_json,'$.away_team')) away,
                   any_value(json_extract_string(raw_json,'$.commence_time')) commence,
                   max((json_extract_string(raw_json,'$._snapshot_ts')
                        < json_extract_string(raw_json,'$.commence_time'))::int) has_safe
            from {D} group by 1
        )
        select part_season, home, away, commence from ev where has_safe = 0 order by commence
    """)
    n_games = int(q(f"select count(distinct json_extract_string(raw_json,'$.id')) n from {D}")["n"].iloc[0])
    n_orphan = len(orphans)
    orphan_frac = n_orphan / n_games if n_games else 0.0
    print(f"\n  distinct games={n_games}  orphaned (no leakage-safe close)={n_orphan} "
          f"({orphan_frac:.2%})")
    if n_orphan:
        print("  orphaned games (expected: non-FBS collateral swept into an FBS kickoff window):")
        print(_fmt(orphans))

    print("\n" + "=" * 90)
    print("E. Distinct sportsbooks across the table (unnest bookmakers[])")
    print("=" * 90)
    e = q(f"""
        with ev as (select raw_json from {D})
        select json_extract_string(bm,'$.key') book, json_extract_string(bm,'$.title') title,
               count(*) event_book_rows
        from ev, unnest(cast(json_extract(ev.raw_json,'$.bookmakers') as json[])) as t(bm)
        group by 1,2 order by 3 desc
    """)
    print(_fmt(e))
    has_bovada = "bovada" in set(e["book"])

    print("\n" + "=" * 90)
    print("VERDICT")
    print("=" * 90)
    if missing:
        print(f"  ✗ MISSING season partitions: {missing}"); ok = False
    else:
        print(f"  ✓ all expected season partitions present: {sorted(present)}")
    if below_floor:
        print(f"  ✗ partitions below the {NCAAF_HISTORICAL_FLOOR} floor (should not exist): {below_floor}"); ok = False
    else:
        print("  ✓ no below-floor partitions")
    if len(partial):
        print(f"  ✗ PARTIAL/STUB partition(s) under {COVERAGE_MIN_FRAC:.0%} FBS coverage — re-pull without "
              f"--skip-existing:\n{_fmt(partial[['season','fbs_games','odds_events','pct_covered']])}"); ok = False
    else:
        print(f"  ✓ every season ≥ {COVERAGE_MIN_FRAC:.0%} of its FBS schedule (complete pull)")
    bad_mkt = c[(c.pct_h2h < 90) | (c.pct_spreads < 90) | (c.pct_totals < 90)]
    if len(bad_mkt):
        print(f"  ⚠ a season has <90% coverage of a core market — inspect:\n{_fmt(bad_mkt)}")
    else:
        print("  ✓ h2h/spreads/totals each cover >90% of events every season")
    if orphan_frac > ORPHAN_FAIL_FRAC:
        print(f"  ✗ orphan rate {orphan_frac:.2%} > {ORPHAN_FAIL_FRAC:.0%} — SYSTEMIC (not just non-FBS "
              f"collateral); check the snapshot/kickoff-time logic"); ok = False
    else:
        print(f"  ✓ orphan rate {orphan_frac:.2%} ≤ {ORPHAN_FAIL_FRAC:.0%} (expected non-FBS neighbour-window "
              f"collateral; P1.4 filters — no FBS close lost)")
    print(f"  {'✓' if has_bovada else '⚠'} Bovada present (the target book): {has_bovada}")
    print("\n  OVERALL:", "PASS ✓" if ok else "FAIL ✗ — see above")
    return ok


def main() -> None:
    # CLOCK-DERIVED default so the asserted range tracks the calendar (a pinned year would go
    # stale and stop flagging a newly-completed season as missing — see P0.6's 2025 gap).
    default_seasons = default_backfill_seasons()
    p = argparse.ArgumentParser(description="Verify the odds_ncaaf_historical backfill (P0.6).")
    p.add_argument("--seasons", default=default_seasons,
                   help=f"expected season partitions to assert present (default {default_seasons} — "
                        f"clock-derived through the last COMPLETED season)")
    p.add_argument("--source", default="odds_ncaaf_historical")
    args = p.parse_args()
    ok = verify(_parse_seasons(args.seasons), source=args.source)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
