"""run_nf_wk_acc1_crosscheck.py — the recap ↔ league cross-check harness, COMMITTED (NF-WK-ACC1).

⭐ WHY THIS FILE EXISTS. NF-WK-RC1's 14/48 (team totals) and 35/48 (D/ST) baselines came from a
one-off in-session probe that was never committed (RC1 closeout ⑥). A baseline nobody can re-run is
not a baseline. This harness re-derives both from the SAME production functions the recap route and
the divergence recorder call — `realized_week.build` / `build_dst_inputs` (the box's lake reads),
`weekly_recap.score_week`, and `weekly_recap_divergence.build_record` — so the harness and the
recorded stream cannot measure two different constructions.

⭐ WHAT IT COMPARES AGAINST. Sleeper publishes its own score for every started player and defence
(`starters_points`) and every team (`points`), under the league's own settings. Those are external
authorities our scorer had no hand in.

Measured baseline (2026-09-17, league 1268257036043292672 = the operator's 2025 league, weeks 1-4):
    team totals agreeing       14/48
    player seats diverging     61/375
    D/ST constructions agreeing 35/48

RUN (LAPTOP — reads the S3 NFL lake + Sleeper's public API, writes nothing; ~40s cold, ~5s cached):

    AWS_DEFAULT_REGION=us-east-2 uv run python -m \\
      quant_sports_intel_models.football.nfl.fantasy.run_nf_wk_acc1_crosscheck \\
        --league 1268257036043292672 --season 2025 --weeks 1-4

`--cache-dir` keeps the fetched inputs so a re-run is offline; `--json` prints the full record.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger("nfl.fantasy.acc1_crosscheck")

#: The published team total and our itemised total are both floats; a real gap is ≥ 0.01.
TOLERANCE = 1e-6


def _weeks(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(w) for w in spec.split(",") if w]


def load_inputs(league: str, season: int, weeks: list[int], cache_dir: Path | None) -> dict:
    """Sleeper config + weeks, and the lake's realized rows + D/ST inputs. Cached per (league, season)."""
    cache = cache_dir / f"acc1_{league}_{season}.json" if cache_dir else None
    got = json.loads(cache.read_text()) if cache and cache.is_file() else {"weeks": {}}
    missing = [w for w in weeks if str(w) not in got["weeks"]]
    if "cfg" not in got or missing:
        from app.backend.services.platform_import import sleeper, sleeper_matchups
        from quant_sports_intel_models.football.nfl.fantasy import realized_week
        from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q

        if "cfg" not in got:
            got["cfg"] = sleeper.import_league(league, include_draft=False).config
        for w in missing:
            built = realized_week.build(season, w, q=q, delta=delta)
            got["weeks"][str(w)] = {
                "fetched": sleeper_matchups.fetch_week(league, w),
                "players": built["players"],
                "dst_inputs": realized_week.build_dst_inputs(season, w, q=q, delta=delta),
            }
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(got, default=str))
    return got


def crosscheck(inputs: dict, weeks: list[int]) -> dict:
    """PURE over the loaded inputs — the agreement tables, per week and in total."""
    from app.backend.services import weekly_recap, weekly_recap_divergence

    cfg = inputs["cfg"]
    per_week, records = [], {}
    tot = {"teams": 0, "teamsAgree": 0, "playerCompared": 0, "playerDiverging": 0,
           "playerUnexplained": 0, "dstCompared": 0, "dstDiverging": 0, "dstUnexplained": 0,
           "dstPending": 0}
    for w in weeks:
        blob = inputs["weeks"][str(w)]
        by_seat: dict = {}
        scored = weekly_recap.score_week(fetched=blob["fetched"], realized_rows=blob["players"],
                                         cfg=cfg, realized_by_seat=by_seat)
        rec = weekly_recap_divergence.build_record(
            scored=scored, scoring=cfg.get("scoring") or {},
            dst_inputs=blob["dst_inputs"], realized_by_seat=by_seat)
        cmp_ = rec["comparison"]
        teams_agree = sum(1 for t in scored["teams"]
                          if t["itemisationGap"] is not None
                          and abs(t["itemisationGap"]) <= TOLERANCE)
        row = {
            "week": w,
            "teams": len(scored["teams"]), "teamsAgree": teams_agree,
            "playerCompared": cmp_["playerSeats"]["compared"],
            "playerDiverging": cmp_["playerSeats"]["diverging"],
            "playerUnexplained": cmp_["playerSeats"]["unexplained"],
            "dstCompared": cmp_["dstSeats"]["compared"],
            "dstDiverging": cmp_["dstSeats"]["diverging"],
            "dstUnexplained": cmp_["dstSeats"]["divergingUnexplained"],
            "dstPending": cmp_["dstSeats"]["divergingScheduleResultPending"],
            "gapNote": scored.get("itemisationGapNote"),
            "dstRows": [
                {k: r[k] for k in ("name", "ours", "platform", "delta", "scheduleResultPending")}
                for r in cmp_["dstSeats"]["rows"]
            ],
        }
        per_week.append(row)
        records[w] = rec
        for k in tot:
            tot[k] += row[k]
    return {"weeks": per_week, "total": tot, "records": records}


def _print(out: dict) -> None:
    t = out["total"]
    for r in out["weeks"]:
        print(f"wk{r['week']}: teams {r['teamsAgree']}/{r['teams']} · players diverging "
              f"{r['playerDiverging']}/{r['playerCompared']} ({r['playerUnexplained']} unexplained) · "
              f"D/ST diverging {r['dstDiverging']}/{r['dstCompared']} "
              f"({r['dstUnexplained']} unexplained, {r['dstPending']} MNF-pending)")
        for d in r["dstRows"]:
            tag = "  [MNF result pending — yOhLHprC]" if d["scheduleResultPending"] else ""
            print(f"      {d['name']}: ours {d['ours']:.2f} vs league {d['platform']:.2f}{tag}")
    print(f"TOTAL: team totals agree {t['teamsAgree']}/{t['teams']} · player seats diverging "
          f"{t['playerDiverging']}/{t['playerCompared']} ({t['playerUnexplained']} unexplained) · "
          f"D/ST agree {t['dstCompared'] - t['dstDiverging']}/{t['dstCompared']} "
          f"({t['dstUnexplained']} unexplained, {t['dstPending']} MNF-pending)")
    notes = {r["gapNote"] for r in out["weeks"]}
    for n in notes:
        print(f"gap note: {n}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--league", required=True)
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--weeks", default="1-4")
    p.add_argument("--cache-dir", type=Path, default=None)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    weeks = _weeks(args.weeks)
    out = crosscheck(load_inputs(args.league, args.season, weeks, args.cache_dir), weeks)
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        _print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
