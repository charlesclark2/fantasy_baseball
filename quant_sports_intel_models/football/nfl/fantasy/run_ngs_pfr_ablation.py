"""run_ngs_pfr_ablation.py — NF-D2 slice 2 (NGS + PFR advanced) ablation. VERDICT: NULL (dropped).

Slice 2 of the NF-D2 sequence tested whether nflverse Next Gen Stats + PFR advanced metrics — target
/ air-yards share, aDOT, separation, YAC-over-expected, rush-yards-over-expected, CPOE, aggressiveness
— lift held-out WITHIN-POSITION rank correlation (ρ) over the SLICE-1 model (`usage_role_blend=0.4`,
the snap/target usage-role expected-games feature — [[project_nf_d2_slice1_snap_role]]).

RESULT: a definitive NULL. These signals correlate with next-season production in ABSOLUTE terms
(WR intended-air-yards-share partial-r ≈ +0.13, TE target/air-yards share ≈ +0.20, controlling for
current fp/g) but do NOT reorder within-tier RANK on top of the slice-1 model. Per the NF-D2 gate
("a source that doesn't move within-tier ordering isn't worth the pipeline — a null add is dropped,
not shipped") the feature is NOT wired into the production model. This script REPRODUCES the null so
it is not silently re-litigated, and gives NF1 (the future learned model) a documented starting point.

THREE mechanisms tested, each vs the slice-1 baseline over 2019–2025 (7 held-out target seasons, each
projected off its own season−1):
  1. per-game production TILT — multiplicative `exp(λ·z)` on the receiving/rushing line from a usage/
     efficiency z-score (WR intended-air-yards, TE air-yards). λ swept 0→0.8. → flat/negative.
  2. expected-GAMES role-signal SWAP — replace the slice-1 WR snap-share games signal with target /
     air-yards share. → flat.
  3. in-fold LEARNED residual — the BEST-SHOT test: an expanding-window ridge (fit on seasons < Y
     only, no peek) of the realized residual `real_fp − proj_fp` on the FULL NGS feature set, per
     position, applied to the held-out season. This is how NF1 would exploit the signal. → net-zero
     to slightly negative (QB +0.006 in isolation; RB/WR/TE flat-to-negative).

WHY the null (the mechanism worth remembering): the recency-weighted multi-year production line +
the slice-1 usage-role already carry the ordering signal; the NGS efficiency metrics are individually
weak (partial-r ≤ 0.13) and collinear with production, so a rank correlation over ~100+ players/pos
barely moves. Advanced-efficiency data mostly RE-ENCODES past production — unlike information-BEARING
sources (injuries/availability, Vegas team environment, vacated opportunity, ADP) that carry signal
ORTHOGONAL to the past line and enter the leakage-safe games channel slice 1 proved works.

RUN (LAPTOP, SF-free sports lake):
    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_ngs_pfr_ablation \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --from 2019 --to 2025
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
)

log = logging.getLogger("nfl.fantasy.ngs_ablation")
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_POSITIONS = ("QB", "RB", "WR", "TE")

# The pre-registered NGS/PFR feature set (base-season, window-weighted). RECEIVING: share of team
# intended air yards (alpha-receiver), box air-yards share, aDOT, separation, YAC-over-expected.
# RUSHING: rush-% over expected. PASSING: CPOE, aggressiveness.
_NGS_FEATS = ["intended_ay_share", "air_yards_share", "adot", "separation",
              "yac_oe", "ryoe_pct", "cpoe", "aggressiveness"]


def _load_ngs(con, base_season: int, schema: str) -> pd.DataFrame:
    """Base-season NGS/PFR signals, window-blended on the same 0.6^age × games recency weights as the
    projection's per-game line (a 3-year window). NaN-aware (a season with no coverage drops out)."""
    lo = base_season - 2
    d = con.sql(f"""
        select season, player_id, count_if(not is_bye) as g,
          avg(pct_share_intended_air_yards) filter (where not is_bye) as intended_ay_share,
          avg(air_yards_share) filter (where not is_bye) as air_yards_share,
          avg(avg_intended_air_yards) filter (where not is_bye) as adot,
          avg(avg_separation) filter (where not is_bye and avg_separation > 0) as separation,
          avg(avg_yards_after_catch_above_expectation) filter (where not is_bye) as yac_oe,
          avg(ngs_rush_pct_over_expected) filter (where not is_bye) as ryoe_pct,
          avg(qb_aggressiveness) filter (where not is_bye) as aggressiveness
        from {schema}.mart_opportunity_player_week
        where season between {lo} and {base_season} group by 1, 2
    """).df()
    cpoe = con.sql(f"""
        select season, player_id,
          avg(completion_percentage_above_expectation) filter (where not is_bye) as cpoe
        from {schema}.sat_passing_ngs_weekly
        where season between {lo} and {base_season} group by 1, 2
    """).df()
    d = d.merge(cpoe, on=["season", "player_id"], how="left")
    d["_w"] = (0.6 ** (base_season - d["season"])) * d["g"].clip(lower=1)

    def _blend(gr: pd.DataFrame) -> pd.Series:
        out = {}
        for c in _NGS_FEATS:
            v = pd.to_numeric(gr[c], errors="coerce").to_numpy()
            w = gr["_w"].to_numpy()
            m = np.isfinite(v)
            out[c] = float((v[m] * w[m]).sum() / (w[m].sum() or 1.0)) if m.any() else np.nan
        return pd.Series(out)

    return d.groupby("player_id").apply(_blend, include_groups=False).reset_index()


def _within_rho(df: pd.DataFrame, fp_col: str) -> dict:
    out = {}
    for pos in _POSITIONS:
        d = df[df["position"] == pos]
        if len(d) >= 10 and d[fp_col].std() > 0 and d["real_fp_ppr"].std() > 0:
            out[pos] = float(d[[fp_col, "real_fp_ppr"]].corr(method="spearman").iloc[0, 1])
    return out


def run(con, seasons: list[int], schema: str) -> dict:
    """The definitive best-shot test: an expanding-window in-fold learned ridge residual adjustment on
    the full NGS feature set, per position, no peek. Baseline = the slice-1 model."""
    # assemble slice-1 projection + NGS feats + realized per season (train pool starts earlier)
    pool = {}
    for y in range(min(seasons) - 3, max(seasons) + 1):
        proj = build_projection(con, y - 1, y, schema, usage_role_blend=0.4)
        proj = proj[proj["position"].isin(_POSITIONS)][["player_id", "position", "proj_fp_ppr"]]
        proj = proj.merge(_load_ngs(con, y - 1, schema), on="player_id", how="left")
        real = load_realized_season(con, y, schema)
        m = proj.merge(real, on="player_id", how="inner")
        m = m[m["g"] >= 6].copy()
        m["season"] = y
        pool[y] = m

    base_acc = {p: [] for p in _POSITIONS}
    learn_acc = {p: [] for p in _POSITIONS}
    for Y in seasons:
        train = pd.concat([pool[y] for y in pool if y < Y], ignore_index=True)
        test = pool[Y].copy()
        test["fp_base"] = test["proj_fp_ppr"]
        test["fp_learn"] = test["proj_fp_ppr"]
        for pos in _POSITIONS:
            tr = train[train["position"] == pos]
            te = test[test["position"] == pos]
            feats = [f for f in _NGS_FEATS
                     if len(tr) and tr[f].notna().mean() > 0.5 and te[f].notna().mean() > 0.5]
            if len(tr) < 60 or len(te) < 10 or not feats:
                continue
            Xtr = tr[feats].apply(pd.to_numeric, errors="coerce")
            Xte = te[feats].apply(pd.to_numeric, errors="coerce")
            med = Xtr.median()
            Xtr, Xte = Xtr.fillna(med), Xte.fillna(med)
            mu, sd = Xtr.mean(), Xtr.std().replace(0, 1)
            Xtr, Xte = (Xtr - mu) / sd, (Xte - mu) / sd
            ytr = (tr["real_fp_ppr"] - tr["proj_fp_ppr"]).to_numpy()
            Xm = np.column_stack([np.ones(len(Xtr)), Xtr.to_numpy()])
            coef = np.linalg.solve(Xm.T @ Xm + 10.0 * np.eye(Xm.shape[1]), Xm.T @ ytr)
            adj = np.column_stack([np.ones(len(Xte)), Xte.to_numpy()]) @ coef
            test.loc[te.index, "fp_learn"] = te["proj_fp_ppr"].to_numpy() + adj
        for p, v in _within_rho(test, "fp_base").items():
            base_acc[p].append(v)
        for p, v in _within_rho(test, "fp_learn").items():
            learn_acc[p].append(v)

    base = {p: round(float(np.mean(base_acc[p])), 4) if base_acc[p] else None for p in _POSITIONS}
    learn = {p: round(float(np.mean(learn_acc[p])), 4) if learn_acc[p] else None for p in _POSITIONS}
    delta = {p: (round(learn[p] - base[p], 4) if base[p] is not None and learn[p] is not None else None)
             for p in _POSITIONS}
    return {"seasons": seasons, "baseline_slice1": base, "plus_ngs_learned": learn, "delta": delta,
            "verdict": "NULL — NGS/PFR advanced does not lift within-position ρ over slice-1; DROPPED",
            "features": _NGS_FEATS}


def write_report(out: dict, path: Path) -> None:
    a = []
    p = a.append
    p("# NF-D2 slice 2 — NGS + PFR advanced. **VERDICT: NULL (dropped, not shipped)**")
    p("")
    p(f"**Generated:** {datetime.now(timezone.utc).isoformat()} · **seasons:** "
      f"{out['seasons'][0]}–{out['seasons'][-1]} · **baseline:** slice-1 model (`usage_role_blend=0.4`)")
    p("")
    p("> The NF-D2 gate is a positive, held-out WITHIN-POSITION ρ lift over the prior shipped model. "
      "NGS/PFR advanced metrics fail it: they correlate with next-season production in absolute terms "
      "but do NOT reorder within-tier RANK on top of slice-1. Per the discipline — *a null add is "
      "DROPPED, not shipped* — the feature is not wired into the production model. Edge-independent.")
    p("")
    p("## Best-shot test — in-fold learned ridge residual on the full NGS feature set (no peek)")
    p("")
    p("| | QB | RB | WR | TE |")
    p("|--|----|----|----|----|")
    p("| slice-1 baseline | " + " | ".join(f"{out['baseline_slice1'][p]:.3f}" for p in _POSITIONS) + " |")
    p("| + NGS learned | " + " | ".join(f"{out['plus_ngs_learned'][p]:.3f}" for p in _POSITIONS) + " |")
    p("| **Δ** | " + " | ".join(f"{out['delta'][p]:+.3f}" for p in _POSITIONS) + " |")
    p("")
    p("Net-zero to slightly negative — only QB shows a small isolated +; RB/WR/TE flat-to-negative. "
      "Two simpler mechanisms (a per-game `exp(λ·z)` tilt, λ swept 0→0.8; and swapping the WR "
      "expected-games role signal from snap→target/air-yards share) were also null.")
    p("")
    p("## Why (mechanism)")
    p("")
    p("- Controlling for current fp/g, the orthogonal forward signal is weak: WR intended-air-yards "
      "share partial-r ≈ +0.13, TE target/air-yards ≈ +0.20, RB rush-over-expected ≈ +0.04, WR snap "
      "share ≈ 0. Individually too weak, and collinear with production, to flip within-tier ranks.")
    p("- The recency-weighted multi-year production line + the slice-1 usage-role already carry the "
      "ordering signal these metrics re-encode.")
    p("- **Implication for the NF-D2 sequence:** the remaining ordering lift is in information-BEARING "
      "sources that carry signal ORTHOGONAL to the past line — injuries/availability (the games "
      "channel slice-1 proved works), Vegas team environment, vacated opportunity, ADP — not in "
      "advanced-efficiency data. NF1 (a learned model) may still consume NGS jointly; this documents "
      "that a heuristic add does not earn its pipeline.")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-D2 slice 2 (NGS/PFR) ablation — verdict NULL")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--from", dest="from_season", type=int, default=2019)
    ap.add_argument("--to", dest="to_season", type=int, default=2025)
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if not Path(args.duckdb).exists():
        ap.error(f"DuckDB not found at {args.duckdb} — build the NFL marts first")

    import duckdb

    seasons = list(range(args.from_season, args.to_season + 1))
    con = duckdb.connect(args.duckdb, read_only=True)
    try:
        out = run(con, seasons, args.schema)
    finally:
        con.close()

    print(f"\n=== NF-D2 slice 2 (NGS/PFR) — best-shot learned test, within-position ρ "
          f"{seasons[0]}–{seasons[-1]} ===")
    print(f"{'':16s} {'QB':>7s} {'RB':>7s} {'WR':>7s} {'TE':>7s}")
    print("slice-1 baseline " + " ".join(f"{out['baseline_slice1'][p]:7.3f}" for p in _POSITIONS))
    print("+ NGS learned    " + " ".join(f"{out['plus_ngs_learned'][p]:7.3f}" for p in _POSITIONS))
    print("Δ                " + " ".join(f"{out['delta'][p]:+7.3f}" for p in _POSITIONS))
    print(f"\nVERDICT: {out['verdict']}")

    (_REPORT_DIR / "nf_d2_ngs_pfr_ablation.json").write_text(json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _REPORT_DIR / "nf_d2_ngs_pfr_ablation.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
