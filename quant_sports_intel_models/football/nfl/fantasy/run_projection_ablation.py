"""run_projection_ablation.py — NF-D2 the reusable projection-quality ABLATION HARNESS.

NF-D2 ("projection-quality data sources") ships as a SEQUENCE of focused slices — each slice
ingests/wires one source and must EARN its place by lifting held-out WITHIN-POSITION rank
correlation (ρ) over the MVP-1 baseline. A source that doesn't move within-tier ordering is dropped,
not shipped. This harness is that gate, run once per slice.

WHAT IT DOES — for each configured "arm" (a set of `build_projection` kwargs), it replays the full
multi-season backtest: for every target season Y in the window it projects Y off its own season-1
with the SAME model + arm, scores the emitted board against the realized season Y, and reports the
within-position Spearman (sp_QB/RB/WR/TE) + overall. The headline is the DELTA vs the baseline arm —
a positive, position-targeted, per-season-stable lift is the ship criterion; the honest null is a
flat/negative delta ⇒ drop the add.

⭐ LEAKAGE-SAFE by construction: every arm projects season Y strictly off data ≤ Y-1 (the base loader
reads `season ≤ base`), and each new feature is a realized BASE-season quantity known at projection
time. Feature selection for a slice is PRE-REGISTERED in the slice's arm definition (a hypothesis,
not an open subset search) and reported here in full.

RUN ON THE LAPTOP (like run_season_projection): SF-free, sports-lake DuckDB, zero shared-box CPU.
Prereq — the NFL marts built into the DuckDB (see run_season_projection.py docstring). Then:

    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_projection_ablation \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --from 2019 --to 2025

Slice registry — `SLICES` maps a slice key → its pre-registered arms. Slice 1 (`snap_role`) is the
snap/target usage-share → expected-games lever. A future slice (NGS/PFR advanced, vacated targets,
team environment, injuries, ADP) adds a new key + arms + whatever base-loader columns it needs.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy.run_season_projection import (  # noqa: E402
    MARTS_SCHEMA,
    build_projection,
    load_realized_season,
    score_vs_realized,
)

log = logging.getLogger("nfl.fantasy.ablation")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_POSITIONS = ("QB", "RB", "WR", "TE")

# ── Slice registry. Each slice = an ordered list of arms; the FIRST arm is the baseline (MVP-1) that
#    every later arm's delta is measured against. An arm = (label, build_projection kwargs). New
#    NF-D2 slices append here — the harness, scoring, and report are slice-agnostic. ──────────────
SLICES: dict[str, list[tuple[str, dict]]] = {
    # Slice 1 (2026-07-25): base-season SNAP share (RB/WR) + TARGET share (TE) → expected games.
    "snap_role": [
        ("MVP-1 baseline (no usage role)", {"usage_role_blend": 0.0}),
        ("+ snap/target usage role", {"usage_role_blend": 0.4}),
    ],
}


def run_arm(con, label: str, kwargs: dict, seasons: list[int], schema: str) -> dict:
    """Backtest one arm across the season window → mean within-position + overall ρ (+ per-season)."""
    per_season = []
    for y in seasons:
        proj = build_projection(con, y - 1, y, schema, **kwargs)
        acc = score_vs_realized(con, proj, y, schema)
        per_season.append(acc)
    def _mean(key):
        vals = [a[key] for a in per_season if key in a and isinstance(a[key], (int, float))]
        return round(float(np.mean(vals)), 4) if vals else None
    out = {
        "label": label, "kwargs": kwargs, "n_seasons": len(seasons),
        "spearman_all": _mean("spearman_all"),
        **{f"sp_{p}": _mean(f"sp_{p}") for p in _POSITIONS},
        "per_season": per_season,
    }
    return out


def ablate(con, slice_key: str, seasons: list[int], schema: str) -> dict:
    arms = SLICES[slice_key]
    log.info("ablating slice '%s' — %d arms over seasons %s", slice_key, len(arms), seasons)
    results = [run_arm(con, label, kw, seasons, schema) for label, kw in arms]
    baseline = results[0]
    for r in results[1:]:
        r["delta_vs_baseline"] = {
            k: (round(r[k] - baseline[k], 4) if r.get(k) is not None and baseline.get(k) is not None else None)
            for k in ["spearman_all", *[f"sp_{p}" for p in _POSITIONS]]
        }
    return {"slice": slice_key, "seasons": seasons, "arms": results}


def _fmt_row(r: dict) -> str:
    cells = [f"{r.get('spearman_all', float('nan')):.3f}"]
    for p in _POSITIONS:
        v = r.get(f"sp_{p}")
        cells.append(f"{v:.3f}" if v is not None else "  -  ")
    return " | ".join(cells)


def write_report(out: dict, path: Path) -> None:
    a, p = [], None
    p = a.append
    slice_key = out["slice"]
    p(f"# NF-D2 slice ablation — `{slice_key}` (held-out within-position ρ)")
    p("")
    p(f"**Generated:** {datetime.now(timezone.utc).isoformat()} · **seasons:** "
      f"{out['seasons'][0]}–{out['seasons'][-1]} ({len(out['seasons'])} held-out targets)")
    p("")
    p("> Each target season Y is projected off its own season−1 with the SAME model + arm and scored "
      "against realized Y (full board, players ≥6 g). `sp_<POS>` = within-position Spearman (the "
      "within-tier ORDERING metric that matters for drafting — the FF gap). The ship criterion is a "
      "positive, position-targeted delta vs the MVP-1 baseline; a flat/negative delta is the honest "
      "null ⇒ the add is DROPPED, not shipped. Edge-independent (projection quality, no best_alpha).")
    p("")
    p("## Mean within-position ρ by arm")
    p("")
    p("| arm | ALL | QB | RB | WR | TE |")
    p("|-----|-----|----|----|----|----|")
    for r in out["arms"]:
        p(f"| {r['label']} | {_fmt_row(r)} |")
    p("")
    p("## Δ vs MVP-1 baseline")
    p("")
    p("| arm | ΔALL | ΔQB | ΔRB | ΔWR | ΔTE |")
    p("|-----|------|-----|-----|-----|-----|")
    for r in out["arms"][1:]:
        d = r["delta_vs_baseline"]
        cells = " | ".join(
            f"{d[k]:+.3f}" if d[k] is not None else "  -  "
            for k in ["spearman_all", "sp_QB", "sp_RB", "sp_WR", "sp_TE"])
        p(f"| {r['label']} | {cells} |")
    p("")
    p("## Per-season within-position ρ (each arm)")
    p("")
    for r in out["arms"]:
        p(f"### {r['label']}")
        p("")
        rows = []
        for a2 in r["per_season"]:
            rows.append({"season": a2.get("projection_season"), "n": a2.get("n"),
                         "ALL": a2.get("spearman_all"),
                         **{p2: a2.get(f"sp_{p2}") for p2 in _POSITIONS}})
        try:
            p(pd.DataFrame(rows).to_markdown(index=False, floatfmt=".3f"))
        except Exception:  # noqa: BLE001
            p(pd.DataFrame(rows).to_string(index=False))
        p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-D2 projection-quality ablation harness")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--slice", default="snap_role", choices=sorted(SLICES.keys()))
    ap.add_argument("--from", dest="from_season", type=int, default=2019)
    ap.add_argument("--to", dest="to_season", type=int, default=2025)
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if not Path(args.duckdb).exists():
        ap.error(f"DuckDB not found at {args.duckdb} — build the NFL marts first "
                 "(see run_season_projection.py docstring)")

    import duckdb

    seasons = list(range(args.from_season, args.to_season + 1))
    con = duckdb.connect(args.duckdb, read_only=True)
    try:
        out = ablate(con, args.slice, seasons, args.schema)
    finally:
        con.close()

    # console summary
    print(f"\n=== NF-D2 slice '{args.slice}' — mean within-position ρ, seasons "
          f"{seasons[0]}–{seasons[-1]} ===")
    print(f"{'arm':40s} {'ALL':>6s} {'QB':>6s} {'RB':>6s} {'WR':>6s} {'TE':>6s}")
    for r in out["arms"]:
        print(f"{r['label']:40s} {_fmt_row(r).replace(' | ', ' ')}")
    for r in out["arms"][1:]:
        d = r["delta_vs_baseline"]
        print(f"{'  Δ ' + r['label']:40s} "
              + " ".join(f"{d[k]:+6.3f}" if d[k] is not None else "   -  "
                         for k in ["spearman_all", "sp_QB", "sp_RB", "sp_WR", "sp_TE"]))

    report_path = _REPORT_DIR / f"nf_d2_{args.slice}_ablation.md"
    (_REPORT_DIR / f"nf_d2_{args.slice}_ablation.json").write_text(
        json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
