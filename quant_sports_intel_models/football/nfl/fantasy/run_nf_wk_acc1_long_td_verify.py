"""run_nf_wk_acc1_long_td_verify.py — the 40+ yard touchdown derivation, verified. COMMITTED.

⭐ WHY THIS FILE EXISTS. Part 2's field-by-field D/ST verification was an in-session probe and its
figures live only in a spec's prose. RC1 already paid for that once: "a baseline nobody can re-run is
not a baseline" (RC1 closeout ⑥, which is why `run_nf_wk_acc1_crosscheck.py` exists). So part 3's
numbers ship as a runnable check over the SAME function the box publish and the recap call —
`realized_player_pbp.player_long_td_counts`.

⭐ TWO CHECKS, AND NEITHER CAN SUBSTITUTE FOR THE OTHER. That is the whole design, and it is measured
rather than argued (`--controls` prints the table):

  1. AGGREGATE vs Sleeper's own per-player stat lines, SUMMED per week so it needs no player-id
     crosswalk at all. This is the check that pins the THRESHOLD.
     ⭐ Summing is not laziness — it is what makes the check possible. Sleeper's `gsis_id` is NULL
     for most recent players (measured 2026-09-18: 3,125 of 9,421 active players carry one; Bijan
     Robinson and Michael Penix both null), so a per-player join to Sleeper would silently drop
     exactly the players a fantasy league cares about — the NF-W9-0 rookie-crosswalk trap.

  2. SUBSET IDENTITY vs `stats_player_week` — nobody's 40+ yard touchdown count can exceed his
     touchdown count of that type. Both sides are nflverse `gsis_id`, so this needs no name join
     either. This is the check that pins the ATTRIBUTION.

  ⇒ measured: a wrong THRESHOLD is invisible to check 2, and a wrong ATTRIBUTION is invisible to
  check 1. Reporting either alone would be a guard that cannot fail in the direction that matters.

RUN (LAPTOP — reads the S3 NFL lake + Sleeper's public API, writes nothing):

    env -u TOKEN AWS_DEFAULT_REGION=us-east-2 uv run python -m \\
      quant_sports_intel_models.football.nfl.fantasy.run_nf_wk_acc1_long_td_verify \\
        --season 2025 --identity-from 1999 --controls

⚠️ `env -u TOKEN` is not decoration: a bare `TOKEN` in the shell is swallowed by delta-rs as an S3
session token and every lake read fails `400 InvalidToken` (NF-ROS1b).
"""
from __future__ import annotations

import argparse
import collections
import json
import logging
import sys
import urllib.request
from pathlib import Path

from quant_sports_intel_models.football.nfl.fantasy import realized_player_pbp as PP

log = logging.getLogger("nfl.fantasy.acc1_long_td")

_SLEEPER_WEEK_STATS = "https://api.sleeper.app/v1/stats/nfl/regular/{season}/{week}"

#: The scorer key → the `stats_player_week` touchdown column that BOUNDS it. Stated here rather than
#: inside the pure helper so the pairing is visible at the call site (a bound paired with the wrong
#: column would pass everything).
_TD_BOUND_COLUMN: dict[str, str] = {
    "pass_td_40p": "passing_tds",
    "rush_td_40p": "rushing_tds",
    "rec_td_40p": "receiving_tds",
}


def _fetch_json(url: str, cache: Path | None) -> dict:
    if cache and cache.is_file():
        return json.loads(cache.read_text())
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 — a public vendor endpoint
        blob = json.loads(resp.read())
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(blob))
    return blob


def _plays(season: int, *, q, delta, lo: int | None = None) -> list[dict]:
    """Every qualifying touchdown play. Filtered in SQL to the long ones, because the derivation's own
    threshold is what the aggregate check is testing — so the read must not pre-judge it."""
    cols = ", ".join(PP.PBP_PLAYER_COLUMNS)
    where = f"season = {int(season)}" if lo is None else f"season between {int(lo)} and {int(season)}"
    return q(f"""
        select {cols}
        from {delta('pbp')}
        where {where} and season_type = 'REG' and coalesce(touchdown, 0) = 1
    """).to_dict("records")


def aggregate_check(season: int, plays: list[dict], *, cache_dir: Path | None) -> dict:
    """Per week, our derived total for each term against Sleeper's own. Crosswalk-free."""
    by_week: dict[int, list[dict]] = collections.defaultdict(list)
    for play in plays:
        by_week[int(play["week"])].append(play)

    rows, disagreeing = [], []
    for week in sorted(by_week):
        counts = PP.player_long_td_counts(by_week[week])
        ours = {k: sum(v.get(k, 0.0) for v in counts.values()) for k in PP.LONG_TD_KEYS}
        blob = _fetch_json(
            _SLEEPER_WEEK_STATS.format(season=season, week=week),
            cache_dir / f"sleeper_stats_{season}_{week}.json" if cache_dir else None)
        theirs = {k: sum(float(v.get(k) or 0.0) for v in blob.values() if isinstance(v, dict))
                  for k in PP.LONG_TD_KEYS}
        agree = all(abs(ours[k] - theirs[k]) < 1e-9 for k in PP.LONG_TD_KEYS)
        rows.append({"week": week, "ours": ours, "sleeper": theirs, "agree": agree})
        if not agree:
            disagreeing.append(week)
    return {"weeks": rows, "weeksCompared": len(rows), "weeksDisagreeing": disagreeing}


def identity_check(plays: list[dict], *, q, delta, lo: int, hi: int) -> dict:
    """Every derived player-week against that player's own touchdown counts. Crosswalk-free."""
    touchdowns = q(f"""
        select season, week, player_id,
               coalesce(passing_tds, 0)   as passing_tds,
               coalesce(rushing_tds, 0)   as rushing_tds,
               coalesce(receiving_tds, 0) as receiving_tds
        from {delta('stats_player_week')}
        where season between {int(lo)} and {int(hi)} and season_type = 'REG'
    """).to_dict("records")
    bound = {(int(r["season"]), int(r["week"]), str(r["player_id"])): r for r in touchdowns}

    by_key: dict[tuple[int, int], list[dict]] = collections.defaultdict(list)
    for play in plays:
        by_key[(int(play["season"]), int(play["week"]))].append(play)

    violations, unjoined, player_weeks = [], 0, 0
    for (season, week), group in by_key.items():
        counts = PP.player_long_td_counts(group)
        player_weeks += len(counts)
        caps: dict[str, dict[str, float]] = {}
        for pid in counts:
            row = bound.get((season, week, str(pid)))
            if row is None:
                # ⛔ COUNTED AND REPORTED, never skipped silently: a derived player who has no weekly
                # line at all is a JOIN failure, and treating it as "nothing to check" is the NF1.7(a)
                # vacuous pass that would hide exactly the id-vocabulary mismatch this check relies on.
                unjoined += 1
                continue
            caps[pid] = {term: float(row[col]) for term, col in _TD_BOUND_COLUMN.items()}
        for bad in PP.subset_identity_violations({p: counts[p] for p in caps}, caps):
            violations.append({"season": season, "week": week, **bad})
    return {"playerWeeks": player_weeks, "unjoined": unjoined,
            "violations": violations, "violationCount": len(violations)}


def controls(season: int, plays: list[dict], *, q, delta, cache_dir: Path | None) -> list[dict]:
    """⭐ THE TWO-SIDED PROOF: each check must FAIL on the error class it owns, and each is BLIND to
    the other's. Without this table the two figures are decoration (NF1.7(a))."""
    import copy

    out = []
    for label, mutate in (
        ("the rule as frozen", None),
        ("threshold 41 (too strict)", ("threshold", 41)),
        ("threshold 39 (too loose)", ("threshold", 39)),
        ("passer/receiver swapped", ("swap", None)),
    ):
        plays_used = plays
        original = PP.LONG_TD_YARDS
        try:
            if mutate and mutate[0] == "threshold":
                PP.LONG_TD_YARDS = mutate[1]
            if mutate and mutate[0] == "swap":
                plays_used = copy.deepcopy(plays)
                for play in plays_used:
                    play["passer_player_id"], play["receiver_player_id"] = (
                        play["receiver_player_id"], play["passer_player_id"])
            agg = aggregate_check(season, plays_used, cache_dir=cache_dir)
            ident = identity_check(plays_used, q=q, delta=delta, lo=season, hi=season)
            out.append({"variant": label,
                        "weeksDisagreeing": len(agg["weeksDisagreeing"]),
                        "weeksCompared": agg["weeksCompared"],
                        "subsetViolations": ident["violationCount"]})
        finally:
            PP.LONG_TD_YARDS = original
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--season", type=int, default=2025,
                   help="the season the AGGREGATE check compares against Sleeper")
    p.add_argument("--identity-from", type=int, default=None,
                   help="run the SUBSET IDENTITY check from this season through --season "
                        "(default: --season only). 1999 covers the whole lake.")
    p.add_argument("--controls", action="store_true",
                   help="also print the two-sided control table (each check vs a deliberately "
                        "wrong rule) — slower, and what makes the figures evidence")
    p.add_argument("--cache-dir", type=Path, default=None,
                   help="cache the Sleeper fetches so a re-run is offline")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q

    season_plays = _plays(args.season, q=q, delta=delta)
    agg = aggregate_check(args.season, season_plays, cache_dir=args.cache_dir)

    lo = args.identity_from if args.identity_from is not None else args.season
    ident_plays = season_plays if lo == args.season else _plays(args.season, q=q, delta=delta, lo=lo)
    ident = identity_check(ident_plays, q=q, delta=delta, lo=lo, hi=args.season)

    out = {"season": args.season, "aggregate": agg, "identity": {**ident, "fromSeason": lo}}
    if args.controls:
        out["controls"] = controls(args.season, season_plays, q=q, delta=delta,
                                   cache_dir=args.cache_dir)

    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return 0 if not agg["weeksDisagreeing"] and not ident["violations"] else 1

    print(f"── AGGREGATE vs Sleeper, {args.season} REG (no crosswalk)")
    print(f"   weeks agreeing on all three terms: "
          f"{agg['weeksCompared'] - len(agg['weeksDisagreeing'])}/{agg['weeksCompared']}")
    for week in agg["weeksDisagreeing"]:
        row = next(r for r in agg["weeks"] if r["week"] == week)
        print(f"   wk{week} MISMATCH ours={row['ours']} sleeper={row['sleeper']}")
    print(f"── SUBSET IDENTITY vs stats_player_week, {lo}-{args.season} REG")
    print(f"   derived player-weeks: {ident['playerWeeks']} · unjoined: {ident['unjoined']} · "
          f"VIOLATIONS: {ident['violationCount']}")
    for bad in ident["violations"][:20]:
        print(f"      {bad}")
    if args.controls:
        print("── CONTROLS (each check must fail on the class it owns, and only that class)")
        print(f"   {'variant':30s} {'weeks disagreeing':>18s} {'subset violations':>18s}")
        for row in out["controls"]:
            print(f"   {row['variant']:30s} "
                  f"{str(row['weeksDisagreeing']) + '/' + str(row['weeksCompared']):>18s} "
                  f"{row['subsetViolations']:>18d}")
    return 0 if not agg["weeksDisagreeing"] and not ident["violations"] else 1


if __name__ == "__main__":
    sys.exit(main())
