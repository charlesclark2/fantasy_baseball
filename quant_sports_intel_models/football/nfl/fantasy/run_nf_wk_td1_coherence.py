"""run_nf_wk_td1_coherence.py — NF-WK-TD1 node 3: points-head-vs-component-line coherence.

    LAPTOP (the before side, from the committed capture):
      uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_wk_td1_coherence \
        --before quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_wk_td1_before_week2_players.json

    LAPTOP (before + after, once a post-emission payload has been staged):
      uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_wk_td1_coherence \
        --before …/nf_wk_td1_before_week2_players.json \
        --after  …/artifacts/weekly_serving/2026/2/players.json \
        --out    …/ablation_results/nf_wk_td1_coherence.json

⭐ THE METHOD IS MT1's, VERBATIM, AND DEVIATING FROM IT BREAKS COMPARABILITY. Component sum uses
FULL-PPR weights (`passYds*0.04 + rec*1.00 + recYds*0.10 + rushYds*0.10`, plus the four TD/INT terms
once they exist), `None` counts as 0.0, and `gap = head − components`. Full PPR deliberately: the
head is full-PPR-native, so this isolates the SUBSTRATE rather than mixing in a league's settings.

⛔ NO RESCALING, EVER (MH2.2). Nothing here calibrates, shrinks or fits anything to move the
component sum toward the head. The residual is reported as it falls. If it stays material that is a
finding about two independent heads, to be reported — not a defect in this story's plumbing to
absorb.

⭐ PER-POSITION AND SIGNED, NEVER POOLED-ONLY. The per-position gaps carry opposite signs and cancel
to roughly nothing pooled, which reads as "nothing to see" and is the single most misleading way to
report this measurement.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

#: Full-PPR weights for the SEVEN components the pre-TD payload already carried.
BASE_WEIGHTS: dict[str, float] = {
    "passYds": 0.04, "rushYds": 0.10, "rec": 1.00, "recYds": 0.10,
}
#: …and the FOUR this story adds. Split out rather than merged so the before/after decomposition is
#: readable, and so `passInt`'s NEGATIVE weight is visible at the point it matters.
TD_WEIGHTS: dict[str, float] = {
    "passTd": 4.00, "passInt": -2.00, "rushTd": 6.00, "recTd": 6.00,
}
#: Volume-only fields carry no PPR weight in a standard league and are excluded from both sides.
POSITIONS = ("QB", "RB", "WR", "TE")
TOP_N = 24


def _sum(row: dict, weights: dict[str, float]) -> float:
    return sum(w * (row.get(k) or 0.0) for k, w in weights.items())


def components(row: dict, *, with_td: bool) -> float:
    v = _sum(row, BASE_WEIGHTS)
    return v + _sum(row, TD_WEIGHTS) if with_td else v


def td_coverage(players: list[dict]) -> dict:
    """How many rows carry a NON-NULL value per TD field — never a key check.

    ⭐ THE DISTINCTION THAT DEFINES THIS STORY. The pre-TD payload carried every TD KEY on every
    row, so a "which fields does this payload carry?" check reports full coverage and passes. Only
    a non-null COUNT separates the two artifacts.
    """
    return {k: sum(1 for r in players if r.get(k) is not None) for k in TD_WEIGHTS}


def read(payload: dict) -> list[dict]:
    rows = [r for r in (payload.get("players") or []) if r.get("status") == "projected"]
    if not rows:
        raise SystemExit("payload carries no `projected` rows — refusing to report on nothing")
    return rows


def table(players: list[dict], *, with_td: bool) -> dict:
    """Per-position signed gaps, on the top-N by head and on the whole position."""
    out: dict = {"n": len(players), "with_td": with_td, "positions": {}}
    gaps_all = []
    for pos in POSITIONS:
        g = [r for r in players if r.get("pos") == pos]
        if not g:
            continue
        top = sorted(g, key=lambda r: -r["fpPpr"])[:TOP_N]
        rows = {}
        for label, sel in (("top24", top), ("all", g)):
            gaps = [r["fpPpr"] - components(r, with_td=with_td) for r in sel]
            rows[label] = {
                "n": len(sel),
                "mean_head": round(st.fmean(r["fpPpr"] for r in sel), 4),
                "mean_gap": round(st.fmean(gaps), 4),
                "median_abs_gap": round(st.median(abs(x) for x in gaps), 4),
                "p95_abs_gap": round(sorted(abs(x) for x in gaps)[int(0.95 * (len(gaps) - 1))], 4),
                "max_abs_gap": round(max(abs(x) for x in gaps), 4),
            }
        out["positions"][pos] = rows
        gaps_all.extend(r["fpPpr"] - components(r, with_td=with_td) for r in g)
    out["pooled"] = {
        "n": len(gaps_all),
        "mean_gap": round(st.fmean(gaps_all), 4),
        "median_abs_gap": round(st.median(abs(x) for x in gaps_all), 4),
        "max_abs_gap": round(max(abs(x) for x in gaps_all), 4),
        "⚠️": "POOLED CANCELS OPPOSITE-SIGNED PER-POSITION GAPS — read `positions`, not this.",
    }
    return out


def render(label: str, t: dict) -> None:
    print(f"\n{label}  (n={t['n']}, TD terms {'INCLUDED' if t['with_td'] else 'absent'})")
    print(f"  {'POS':4s} {'tier':7s} {'n':>4s} {'mean head':>10s} {'mean gap':>10s} "
          f"{'med |gap|':>10s} {'p95 |gap|':>10s} {'max |gap|':>10s}")
    for pos, rows in t["positions"].items():
        for tier, r in rows.items():
            print(f"  {pos:4s} {tier:7s} {r['n']:4d} {r['mean_head']:10.3f} {r['mean_gap']:+10.3f} "
                  f"{r['median_abs_gap']:10.3f} {r['p95_abs_gap']:10.3f} {r['max_abs_gap']:10.3f}")
    p = t["pooled"]
    print(f"  {'ALL':4s} {'pooled':7s} {p['n']:4d} {'':10s} {p['mean_gap']:+10.3f} "
          f"{p['median_abs_gap']:10.3f} {'':10s} {p['max_abs_gap']:10.3f}   ← cancels; do not quote alone")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-WK-TD1 component-coherence before/after")
    ap.add_argument("--before", required=True, help="the committed pre-TD payload capture")
    ap.add_argument("--after", default=None, help="a post-emission payload (staged or published)")
    ap.add_argument("--out", default=None, help="write the record as JSON")
    args = ap.parse_args(argv)

    before_payload = json.loads(Path(args.before).read_text())
    before = read(before_payload)
    rec: dict = {
        "before_vintage": {
            "season": before_payload.get("season"), "week": before_payload.get("week"),
            "generated_at": before_payload.get("generated_at"), "n_players": len(before_payload.get("players") or []),
        },
        "before_td_nonnull": td_coverage(before),
        "before": table(before, with_td=False),
    }
    print(f"BEFORE vintage: {rec['before_vintage']}")
    print(f"BEFORE TD non-null counts: {rec['before_td_nonnull']}")
    render("BEFORE — components exclude TDs because the payload has none", rec["before"])

    if args.after:
        after_payload = json.loads(Path(args.after).read_text())
        after = read(after_payload)
        rec["after_vintage"] = {
            "season": after_payload.get("season"), "week": after_payload.get("week"),
            "generated_at": after_payload.get("generated_at"), "n_players": len(after_payload.get("players") or []),
        }
        rec["after_td_nonnull"] = td_coverage(after)
        # ⭐ THE CONTROLLED PAIR. Both sides come from the SAME build, so the comparison isolates the
        # TD terms rather than mixing in a vintage change. `after_without_td` is what the pre-TD code
        # would have produced from this build: NF-WK-TD1's ARM1/ARM2 smoke measured the seven served
        # components BIT-IDENTICAL with and without the TD labels (max |diff| 0.000e+00), so
        # dropping the TD terms from the sum reconstructs the old payload's arithmetic exactly.
        rec["after_without_td"] = table(after, with_td=False)
        rec["after"] = table(after, with_td=True)
        print(f"\nAFTER vintage: {rec['after_vintage']}")
        print(f"AFTER TD non-null counts: {rec['after_td_nonnull']}")
        render("AFTER (same build, TD terms dropped) — the CONTROLLED before side", rec["after_without_td"])
        render("AFTER (same build, TD terms included)", rec["after"])
        rec["delta"] = {
            pos: {
                tier: round(rec["after"]["positions"][pos][tier]["mean_gap"]
                            - rec["after_without_td"]["positions"][pos][tier]["mean_gap"], 4)
                for tier in ("top24", "all")
            }
            for pos in rec["after"]["positions"]
        }
        print("\nΔ mean gap from adding the TD terms (after_with − after_without):")
        for pos, d in rec["delta"].items():
            print(f"  {pos:4s} top24 {d['top24']:+8.3f}   all {d['all']:+8.3f}")
        # A DRIFT DIAGNOSTIC, reported beside the controlled pair and never folded into it: how far
        # the substrate itself moved between the captured vintage and the rebuilt one.
        if rec["after_vintage"].get("generated_at") != rec["before_vintage"].get("generated_at"):
            rec["vintage_drift"] = {
                "note": ("the after build is a DIFFERENT vintage from the captured before; the "
                         "controlled comparison is after_without_td vs after, both from this build"),
                "before_generated_at": rec["before_vintage"].get("generated_at"),
                "after_generated_at": rec["after_vintage"].get("generated_at"),
                "before_mean_gap_pooled": rec["before"]["pooled"]["mean_gap"],
                "after_without_td_mean_gap_pooled": rec["after_without_td"]["pooled"]["mean_gap"],
            }
            print(f"\n⚠️ vintage drift: {json.dumps(rec['vintage_drift'], indent=2)}")

    if args.out:
        Path(args.out).write_text(json.dumps(rec, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
