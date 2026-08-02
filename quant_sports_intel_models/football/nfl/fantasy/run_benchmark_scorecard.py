"""run_benchmark_scorecard.py — NF-D3: the standing us-vs-consensus scorecard (CLI + report).

Grades our SHIPPED projection against every obtainable competitor system — ADP (Fantasy Football
Calculator), ECR (FantasyPros), and any operator-supplied FILE benchmark (Fantasy Footballers / PFF /
ESPN, dropped into `artifacts/benchmarks_manual/<system>_<season>.csv`) — apples-to-apples, per
season, on the shared player universe vs realized outcomes. This is the reproducible replacement for
the one-off "FF 2025 file" comparison: run it any season and it re-grades automatically.

The model arm is the EXACT shipped `project_veterans` path (slices 1/3/4/5 on), via the same
`_prep_base`/`_project` helpers the ADP + team-context ablations use — so the scorecard measures what
production ships, built strictly from ≤season−1 data (leakage-safe holdout).

RUN (LAPTOP, SF-free sports lake; the FFC/FP pulls cache to artifacts/*_cache so it is reproducible):
    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_benchmark_scorecard \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --from 2019 --to 2024

Add `--s3` to also land a per-(system, season) scorecard summary to `nfl/fantasy/benchmarks/scorecard`.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import benchmark_scorecard as BS  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import season_projection as sp  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.run_season_projection import (  # noqa: E402
    MARTS_SCHEMA,
    load_realized_season,
)
from quant_sports_intel_models.football.nfl.fantasy.run_team_context_ablation import (  # noqa: E402
    _prep_base,
    _project,
)

log = logging.getLogger("nfl.fantasy.scorecard_cli")
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_POSITIONS = ("QB", "RB", "WR", "TE")


def _shipped_projection(con, season, schema):
    """The SHIPPED model for `season` (base = season−1, slices 1/3/4/5 on) — the same path the ADP
    ablation grades, so the scorecard reflects production."""
    base = _prep_base(con, season, schema)
    return _project(base, sp.positional_pergame_priors(base), season,
                    mover_vol=0.35, injury_blend=0.7)


def _nf1_5_projection(con, season, schema):
    """The NF1.5 refined-board projection for `season` — NF1.5b's market-aware re-ordering of the
    shipped MVP-1 board, which is what NF3.2's track-record backtest must grade (the SAME board the
    2026 app surfaces serve, never a re-derivation of it). Read from its persisted local artifact
    (`nf1_5_season_projections_<season>.parquet`, built via `run_nf1_5.py --mode build
    --projection-season <season>`) — reuses `export_draft_board_json.load_projections_local` so there
    is exactly one place that knows how to read that artifact. Raises `FileNotFoundError` (via that
    loader) if the season hasn't been built yet, rather than silently falling back to MVP-1."""
    from quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json import (
        load_projections_local,
    )
    return load_projections_local(season, source="nf1_5")


def _fmt(v, nd=3):
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else " - "


def write_report(out, path, manual_dir=None):
    a = []
    p = a.append
    seasons = out["seasons_scored"]
    p("# NF-D3 — competitor projection scorecard (us vs consensus)")
    p("")
    span = f"{seasons[0]}–{seasons[-1]}" if seasons else "(none)"
    p(f"**Generated:** {datetime.now(timezone.utc).isoformat()} · **seasons scored:** {span} "
      f"· **model:** the SHIPPED projection (slices 1/3/4/5 on), each season built from ≤season−1 data.")
    p("")
    p("> ⚖️ **The honesty bar (this is a GTM proof asset — a cherry-picked claim backfires):** every "
      "system is graded on the SHARED universe of players it AND our model both cover with ≥6 realized "
      "games, PPR format held fixed, same realized truth. Ordering is measured by within-position "
      "Spearman ρ (what wins drafts) + rank-MAE (rank-space, so a RANKING system — ADP/ECR/Fantasy "
      "Footballers — grades identically to our point projection). Our projection is a genuine holdout "
      "(≤season−1 data); ADP/ECR are frozen PRESEASON snapshots. `+Δ` favours US.")
    p("")

    # ── Aggregate head-to-head (the durable, multi-season claim) ──────────────────────────────
    p("## 1. Aggregate — us vs each system (averaged across the seasons each covers)")
    p("")
    p("`ρ` = position-pooled within-tier Spearman vs realized (higher = better ordering). "
      "`Δρ`/`ΔrankMAE` = us − system (Δρ>0 and ΔrankMAE<0 favour us). `fade ρ` = when we most "
      "disagree with the system, who predicts the realized finish (the non-market edge).")
    p("")
    p("| system | seasons | our ρ | their ρ | Δρ | Δrank-MAE | our fade ρ | their fade ρ |")
    p("|--------|--------:|------:|--------:|---:|---------:|-----------:|-------------:|")
    for name, g in out["aggregate"].items():
        p(f"| {name} | {g['n_seasons']} | {_fmt(g['us_rho_pooled'])} | {_fmt(g['system_rho_pooled'])} "
          f"| {_fmt(g['delta_rho_pooled'])} | {_fmt(g['delta_rank_mae'], 2)} "
          f"| {_fmt(g['disagreement_us'])} | {_fmt(g['disagreement_system'])} |")
    p("")
    p("### Δρ by position (us − system)")
    p("")
    p("| system | QB | RB | WR | TE |")
    p("|--------|---:|---:|---:|---:|")
    for name, g in out["aggregate"].items():
        bp = g["delta_rho_by_pos"]
        p(f"| {name} | " + " | ".join(_fmt(bp.get(pos)) for pos in _POSITIONS) + " |")
    p("")

    # ── Per-season detail ─────────────────────────────────────────────────────────────────────
    p("## 2. Per-season detail")
    p("")
    for r in out["per_season"]:
        p(f"### {r['season']} — scored universe n={r['n_scored_universe']}")
        p("")
        p("| system | cover% | n_aligned | our ρ | their ρ | Δρ | our rank-MAE | their rank-MAE |")
        p("|--------|-------:|----------:|------:|--------:|---:|-------------:|---------------:|")
        for name, s in r["systems"].items():
            if "us" not in s:
                p(f"| {name} | - | {s.get('n_aligned', 0)} | (thin) | | | | |")
                continue
            p(f"| {name} | {_fmt(s.get('coverage_pct'), 1)} | {s['n_aligned']} "
              f"| {_fmt(s['us']['rho_pooled'])} | {_fmt(s['system']['rho_pooled'])} "
              f"| {_fmt(s['delta_rho_pooled'])} | {_fmt(s['us']['rank_mae'], 2)} "
              f"| {_fmt(s['system']['rank_mae'], 2)} |")
        p("")

    # ── Reading it / honest scope ─────────────────────────────────────────────────────────────
    p("## 3. Reading it — scope the claim to what is TRUE")
    p("")
    p("- The **defensible public claim** is per-system, per-position, out-of-sample — read it straight "
      "off §1 (aggregate) and the Δρ-by-position table. A `+Δρ` averaged over multiple seasons at a "
      "position is a real, reproducible win; a negative one is a place we do NOT yet beat that system "
      "(say so — the honesty bar).")
    p("- ADP/ECR are RANKINGS; we grade them in rank-space (ρ + rank-MAE), never on a points-MAE they "
      "don't emit. A file benchmark (Fantasy Footballers / PFF / ESPN) is scored identically the "
      "moment its `<system>_<season>.csv` is dropped in — the scorecard is standing, not a one-off.")
    p("- Consistent with the NF-D2 #6 ADP finding: our edge is strongest at **WR/TE** and on our "
      "**high-conviction fades**; the market tends to out-order us at **QB/RB**. Scope every public "
      "statement to the position + the fades, not a blanket 'we beat the consensus'.")
    p("")
    if out.get("forward"):
        fw = out["forward"]
        p(f"## 4. Forward view — {fw['season']} (NO realized truth yet ⇒ AGREEMENT, not accuracy)")
        p("")
        p("> ⚠️ There is no realized outcome for an in-progress season, so this section makes **NO "
          "'we beat X' claim** — it only shows how aligned our board is with each system, and our most "
          "CONTRARIAN picks (draft content, not a proof point). The accuracy grade lands here "
          "automatically once the season completes and `build_scorecard` can score it vs realized.")
        p("")
        p("| system | n_aligned | agreement ρ (pooled) | QB | RB | WR | TE |")
        p("|--------|----------:|---------------------:|---:|---:|---:|---:|")
        for name, s in fw["systems"].items():
            bp = s["agreement_rho_by_pos"]
            p(f"| {name} | {s['n_aligned']} | {_fmt(s['agreement_rho_pooled'])} | "
              + " | ".join(_fmt(bp.get(pos)) for pos in _POSITIONS) + " |")
        p("")
        for name, s in fw["systems"].items():
            if not s.get("top_disagreements"):
                continue
            p(f"**Biggest disagreements vs {name}** (our z − their z; +we higher):")
            p("")
            p("| player | pos | direction | gap (z) |")
            p("|--------|-----|-----------|--------:|")
            for dnr in s["top_disagreements"][:10]:
                p(f"| {dnr['player']} | {dnr['position']} | {dnr['direction']} | {dnr['gap_z']:+.2f} |")
            p("")

    fbs = BS.discover_file_benchmarks(manual_dir)
    if not fbs:
        p("> ℹ️ No operator file benchmarks found under `artifacts/benchmarks_manual/`. To add Fantasy "
          "Footballers / PFF / ESPN, drop a `<system>_<season>.csv` there — see the format below.")
        p("")
        p("```")
        p(BS.FILE_BENCHMARK_README.rstrip())
        p("```")
    else:
        got = ", ".join(f"{f['system']} {f['season']}" for f in fbs)
        p(f"> ℹ️ Operator file benchmarks scored: {got}.")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


def _scorecard_asset(out) -> pd.DataFrame:
    """Flatten per-(system, season) into a tidy frame for the lake (one row per system-season)."""
    rows = []
    for r in out["per_season"]:
        for name, s in r["systems"].items():
            if "us" not in s:
                continue
            dz = s.get("disagreement") or {}
            rows.append({
                "season": r["season"], "system": name, "scored_universe": r["n_scored_universe"],
                "n_aligned": s["n_aligned"], "coverage_pct": s.get("coverage_pct"),
                "us_rho_pooled": s["us"]["rho_pooled"], "system_rho_pooled": s["system"]["rho_pooled"],
                "delta_rho_pooled": s["delta_rho_pooled"], "us_rank_mae": s["us"]["rank_mae"],
                "system_rank_mae": s["system"]["rank_mae"], "delta_rank_mae": s["delta_rank_mae"],
                "us_fade_rho": dz.get("us"), "system_fade_rho": dz.get("system"),
                "delta_rho_QB": s["delta_rho_by_pos"].get("QB"),
                "delta_rho_RB": s["delta_rho_by_pos"].get("RB"),
                "delta_rho_WR": s["delta_rho_by_pos"].get("WR"),
                "delta_rho_TE": s["delta_rho_by_pos"].get("TE"),
            })
    return pd.DataFrame(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description="NF-D3 — us-vs-consensus benchmark scorecard")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--from", dest="from_season", type=int, default=2019)
    ap.add_argument("--to", dest="to_season", type=int, default=2024)
    ap.add_argument("--manual-dir", default=None, help="override the benchmarks_manual/ dir")
    ap.add_argument("--projection-source", choices=("mvp1", "nf1_5"), default="mvp1",
                    help="which projection to grade — 'mvp1' the market-blind shipped model (default; "
                         "existing behavior, unchanged output filenames) or 'nf1_5' the market-aware "
                         "refined board NF1.5b serves (NF3.2 backtest; requires each season's "
                         "nf1_5_season_projections_<year>.parquet to already exist — see "
                         "run_nf1_5.py --mode build --projection-season <year>). Output lands under a "
                         "'_nf1_5' suffixed filename so it never clobbers the mvp1 baseline report.")
    ap.add_argument("--forward-season", type=int, default=None,
                    help="also emit an AGREEMENT view for an in-progress season (e.g. 2026 — no "
                         "realized truth yet, so no accuracy claim; usable for a forward FF file)")
    ap.add_argument("--s3", action="store_true", help="land the scorecard summary to the S3 sports lake")
    ap.add_argument("--lake-root", default=None, help="land the scorecard to a LOCAL-FS Delta tree")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if not Path(args.duckdb).exists():
        ap.error(f"DuckDB not found at {args.duckdb} — build the NFL marts first")

    import duckdb

    seasons = list(range(args.from_season, args.to_season + 1))
    project_fn = _nf1_5_projection if args.projection_source == "nf1_5" else _shipped_projection
    con = duckdb.connect(args.duckdb, read_only=True)
    try:
        out = BS.build_scorecard(con, seasons, args.schema, project_fn=project_fn,
                                 load_realized_fn=load_realized_season, manual_dir=args.manual_dir)
        if args.forward_season is not None:
            out["forward"] = BS.forward_comparison(con, args.forward_season, args.schema,
                                                   project_fn=project_fn,
                                                   manual_dir=args.manual_dir)
    finally:
        con.close()

    print(f"\n=== NF-D3 scorecard — us vs consensus, {seasons[0]}–{seasons[-1]} ===")
    for name, g in out["aggregate"].items():
        print(f"  {name:20s} seasons={g['n_seasons']}  our ρ={_fmt(g['us_rho_pooled'])} "
              f"their ρ={_fmt(g['system_rho_pooled'])}  Δρ={_fmt(g['delta_rho_pooled'])}  "
              f"ΔrankMAE={_fmt(g['delta_rank_mae'], 2)}  by_pos={g['delta_rho_by_pos']}")
    if not out["aggregate"]:
        print("  (no systems scored — check FFC/FP reachability + that the marts cover these seasons)")
    if out.get("forward"):
        fw = out["forward"]
        print(f"\n  [forward {fw['season']} — AGREEMENT only, no accuracy claim]")
        for name, s in fw["systems"].items():
            print(f"    {name:20s} n={s['n_aligned']:4d}  agreement ρ={_fmt(s['agreement_rho_pooled'])} "
                  f"by_pos={s['agreement_rho_by_pos']}")

    suffix = "" if args.projection_source == "mvp1" else f"_{args.projection_source}"
    (_REPORT_DIR / f"nf_d3_benchmark_scorecard{suffix}.json").write_text(
        json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _REPORT_DIR / f"nf_d3_benchmark_scorecard{suffix}.md", manual_dir=args.manual_dir)

    if (args.s3 or args.lake_root) and out["per_season"]:
        from quant_sports_intel_models.football.nfl.ingest import s3io
        asset = _scorecard_asset(out)
        source_name = f"scorecard{suffix}"
        for y, sub in asset.groupby("season"):
            n = s3io.write_dataframe(sub.assign(season=int(y)), sport="nfl", source=source_name,
                                     season=int(y), tier="fantasy/benchmarks", local_root=args.lake_root)
            log.info("  landed %d scorecard rows → nfl/fantasy/benchmarks/%s season=%d", n, source_name, y)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
