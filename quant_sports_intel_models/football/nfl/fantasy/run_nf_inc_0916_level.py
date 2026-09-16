"""NF-INC-0916 node 3 — the POPULATION-MATCHED LEVEL MEASUREMENT, and the zero-atom read.

⭐ WHY THIS IS A RUNNER RATHER THAN AN AD-HOC READ. NF-WK-TD1 produced the BEFORE table by hand.
An after table computed by a second hand-written read is not comparable to it — the whole value of
a before/after pair is that one method produced both. This module IS the method, and it is checked
against TD1's recorded figures by `test_nf_inc_0916_level.py`, so a drift shows up as a failing
test rather than as two tables nobody can reconcile.

══ THE METHOD, and the correction that produced it ══════════════════════════════════════════════

TD1's own first cut compared the served projection against the REALIZED TOP-24 BY REALIZED POINTS
and got 0.17-0.37. That comparison has a SELECTION CONFOUND and overstates the effect: the realized
top-24 selects the players who actually boomed, which no unbiased projection can or should match.
⛔ Those figures are SUPERSEDED and must not be quoted.

The clean comparison is POPULATION-MATCHED. Both sides are game-day-rostered QB/RB/WR/TE
player-weeks, and the argument is a one-liner: an unbiased projection's MEAN over a population must
equal that population's realized mean. It does not require the projection to be accurate on any
player; it only requires it not to be systematically displaced.

  SERVED side   — every projected player in the published payload, by position.
  REALIZED side — every historical player-week in the lake that HAD A GAME, built through the same
                  `weekly_frame` path the model trains on, so the population is the model's own.

⚠️ BYE ROWS ARE EXCLUDED FROM THE REALIZED SIDE and NOT from the served side, and that asymmetry is
correct rather than an oversight: a bye is a DETERMINISTIC zero we publish on purpose, so it
belongs in what we served; on the realized side it is not a player-week anyone could have scored
in, and including it would drag the benchmark down and FLATTER the projection.

══ THE ZERO-ATOM READ ═══════════════════════════════════════════════════════════════════════════

The level ratio says the number is wrong; the band says WHY. Every one of the before-payload's top
ten projections carried `fpP10 = 0.00` against a plausible `fpP90` (McCaffrey 0.00/10.45/27.17).
An elite back's 10th percentile is not zero, and the p90 ceilings were roughly right — so the
conditional-on-playing half of the hurdle was intact and the inflation sat in the ZERO ATOM, which
is exactly what a training week of fabricated zeros does to a `P(zero)` classifier.

⛔ NO THRESHOLD IS INVENTED HERE. This module MEASURES and REPORTS; it does not pass or fail a
retrain. The operator reads the table (spec node 3).
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

POSITIONS = ("QB", "RB", "WR", "TE")

#: The realized population: COMPLETED seasons, REGULAR season only.
#:
#: ⭐ RECOVERED BY REPRODUCTION, not assumed. TD1 recorded the before table without stating its
#: population bounds, so four candidates were scored against its figures:
#:
#:     2016-2026 all weeks   ALL n=89,554 mean 5.334   (TD1: 84,553 / 5.357)
#:     2016-2026 REG only    ALL n=86,291 mean 5.323
#:     2016-2025 all weeks   ALL n=88,534 mean 5.365
#:     2016-2025 REG only    ALL n=85,271 mean 5.355   ← WR mean reproduces EXACTLY (5.743);
#:                                                        QB/RB/TE/ALL within 0.008
#:
#: It is also the defensible choice on its own terms: a partial current season should not define
#: the benchmark a current projection is judged against, and the postseason is a different
#: population (a 31-row conference-championship week is not a slate).
#:
#: ⚠️ DO NOT MOVE THIS WHILE A BEFORE/AFTER PAIR IS LIVE. Both tables must be computed over the
#: same realized population or the ratio change confounds "the model improved" with "the benchmark
#: moved". `test_nf_inc_0916_level.py` pins it against TD1's recorded figures.
REALIZED_SEASONS = (2016, 2025)

#: The last REG week. Weeks beyond it are postseason and are excluded from the realized population.
LAST_REG_WEEK = 18


def realized_population(seasons: tuple[int, int] = REALIZED_SEASONS) -> pd.DataFrame:
    """Every game-day-rostered QB/RB/WR/TE player-week in the lake, with its realized PPR.

    Built through `weekly_frame`'s own spine + label path so the population is the MODEL'S
    population rather than a second definition of one.
    """
    from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
    from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q

    lo, hi = seasons
    rng = f"season between {lo} and {hi}"
    frame = WF.attach_labels(
        WF.build_spine(q(f"select * from {delta('weekly_rosters')} where {rng}"),
                       q(f"select * from {delta('schedules')} where {rng}")),
        q(f"select * from {delta('stats_player_week')} where {rng}"),
        label_version="nf-inc-0916-level", label_as_of_timestamp="measurement",
        snaps=q(f"select * from {delta('snap_counts')} where {rng}"),
    )
    # ⚠️ `_has_game` ONLY. A bye is not a player-week anyone could have scored in; including it
    # would drag the benchmark down and FLATTER the projection being judged.
    # ⚠️ REG ONLY. The postseason is a different population — a 31-row conference-championship week
    # is not a slate — and mixing it in moves the benchmark for reasons unrelated to the model.
    return frame[frame["_has_game"] & (frame["week"] <= LAST_REG_WEEK)]


def level_table(payload: dict, realized: pd.DataFrame) -> pd.DataFrame:
    """The population-matched table, per position and pooled."""
    served = pd.DataFrame(payload["players"])
    rows = []
    for pos in (*POSITIONS, "ALL"):
        s = served if pos == "ALL" else served[served["pos"] == pos]
        r = realized if pos == "ALL" else realized[realized["position"] == pos]
        rows.append({
            "pos": pos,
            "n_served": int(len(s)),
            "mean_projection": float(s["fpPpr"].mean()) if len(s) else float("nan"),
            "n_realized": int(len(r)),
            "mean_realized": float(r["fantasy_points"].mean()) if len(r) else float("nan"),
            "ratio": (float(s["fpPpr"].mean()) / float(r["fantasy_points"].mean())
                      if len(s) and len(r) and r["fantasy_points"].mean() else float("nan")),
        })
    return pd.DataFrame(rows)


def zero_atom_read(payload: dict, top_n: int = 10) -> dict:
    """How many of the top projections carry a ZERO 10th percentile.

    ⭐ THE DISCRIMINATING READ, and the reason the level ratio alone is not enough: a uniform scale
    error and an inflated zero atom both depress the mean, and they are different defects with
    different fixes. A top-tier back whose p10 is 0.00 while his p90 is plausible is the atom.
    """
    served = sorted(payload["players"], key=lambda p: -(p.get("fpPpr") or 0.0))[:top_n]
    zero_p10 = [p for p in served if float(p.get("fpP10") or 0.0) == 0.0]
    return {
        "top_n": top_n,
        "n_top_with_zero_p10": len(zero_p10),
        "share_top_with_zero_p10": len(zero_p10) / top_n if top_n else float("nan"),
        "rows": [{"name": p["name"], "pos": p["pos"], "fpP10": p.get("fpP10"),
                  "fpPpr": p.get("fpPpr"), "fpP90": p.get("fpP90")} for p in served],
    }


def render(table: pd.DataFrame, atom: dict, payload: dict, *, label: str) -> str:
    out = [f"## {label} — season {payload.get('season')} week {payload.get('week')}",
           f"generated_at: `{payload.get('generated_at')}`", "",
           "### Population-matched level",
           "",
           "| POS | n served | mean PROJECTION | n realized | mean REALIZED | ratio |",
           "|---|---:|---:|---:|---:|---:|"]
    for r in table.itertuples():
        bold = "**" if r.pos == "ALL" else ""
        out.append(f"| {bold}{r.pos}{bold} | {bold}{r.n_served}{bold} | "
                   f"{bold}{r.mean_projection:.3f}{bold} | {bold}{r.n_realized:,}{bold} | "
                   f"{bold}{r.mean_realized:.3f}{bold} | **{r.ratio:.3f}** |")
    out += ["", f"### Zero atom — {atom['n_top_with_zero_p10']} of the top {atom['top_n']} "
                f"projections carry `fpP10 = 0.00`", "",
            "| player | pos | p10 | point | p90 |", "|---|---|---:|---:|---:|"]
    for r in atom["rows"]:
        out.append(f"| {r['name']} | {r['pos']} | {r['fpP10']:.2f} | {r['fpPpr']:.2f} | "
                   f"{r['fpP90']:.2f} |")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="NF-INC-0916 node 3 — population-matched level read.")
    ap.add_argument("--payload", required=True, help="a weekly players.json (served or staged)")
    ap.add_argument("--label", default="AFTER", help="table label, e.g. BEFORE / AFTER")
    ap.add_argument("--out", help="write a JSON report here")
    ap.add_argument("--out-md", help="write a markdown table here")
    ap.add_argument("--season-lo", type=int, default=REALIZED_SEASONS[0])
    ap.add_argument("--season-hi", type=int, default=REALIZED_SEASONS[1])
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    payload = json.loads(Path(args.payload).read_text())
    realized = realized_population((args.season_lo, args.season_hi))
    table = level_table(payload, realized)
    atom = zero_atom_read(payload)

    md = render(table, atom, payload, label=args.label)
    print(md)
    if args.out:
        Path(args.out).write_text(json.dumps(
            {"label": args.label, "season": payload.get("season"), "week": payload.get("week"),
             "generated_at": payload.get("generated_at"),
             "realized_seasons": [args.season_lo, args.season_hi],
             "level": table.to_dict("records"), "zero_atom": atom}, indent=2) + "\n")
        log.info("wrote %s", args.out)
    if args.out_md:
        Path(args.out_md).write_text(md)
        log.info("wrote %s", args.out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
