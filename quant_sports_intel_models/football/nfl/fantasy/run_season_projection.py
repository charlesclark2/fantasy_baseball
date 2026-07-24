"""run_season_projection.py — NF-FASTPATH CLI: build the 2026 season raw-stat-line projection.

Reads the built NFL marts from the sports dbt DuckDB (SF-free, no box) + the NCAAF-P1A rookie
parquet, runs the pure `season_projection` model for veterans + the incoming rookie class, validates
(coverage report + face-validity + a holdout-season rank-correlation sanity check), lands the raw
projections to the S3 sports lake under `nfl/fantasy/derived/season_projections/`, and writes a
readable ranked output + a markdown report.

⭐ RUN ON THE LAPTOP (like NCAAF-P1A). The sports lake is a SEPARATE bucket from MLB's; a laptop run
is laptop compute + S3 I/O, ZERO shared-box CPU/RAM — it cannot contend with the live MLB pipeline.
SF-free throughout; `SPORTS_LAKE_REGION=us-east-2` for the S3 read/write.

Prereq — the NFL marts must be built into the DuckDB first (dbt-core, NOT dbtf; the delta_scan
staging segfaults fusion). From `quant_sports_intel_models/sports_dbt`:
    export SPORTS_LAKE_REGION=us-east-2
    python -m dbt.cli.main run --select nfl.staging --threads 1
    python -m dbt.cli.main run --select nfl.marts --threads 1

Then (laptop):
    SPORTS_LAKE_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_season_projection \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --s3

Outputs:
  * <out-dir>/nfl_fantasy_season_projections_<year>.parquet   — the raw stat-line projection
  * <out-dir>/nfl_fantasy_season_projections_<year>_ranked.csv — a readable ranked board
  * s3://credence-sports-lakehouse/nfl/fantasy/derived/season_projections/season=<year>/  (--s3)
  * quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_fastpath_season_projection.md
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

from quant_sports_intel_models.football.nfl.fantasy.season_projection import (  # noqa: E402
    MODEL_VERSION,
    RAW_STAT_COLS,
    ROOKIE_POSITIONS,
    fit_rookie_slot_curves,
    positional_pergame_priors,
    project_rookies,
    project_veterans,
)

log = logging.getLogger("nfl.fantasy.fastpath")

MARTS_SCHEMA = "main_nfl_marts"
_DEFAULT_OUT = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_PATH = (
    _PROJECT_ROOT
    / "quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_fastpath_season_projection.md"
)
_ROOKIE_PARQUET = (
    _PROJECT_ROOT
    / "quant_sports_intel_models/football/ncaaf/models/artifacts/ncaaf_nfl_rookie_projections.parquet"
)

# The final emitted schema (the input contract for MVP-2 / NF-C1). Ordered for readability.
OUTPUT_COLS = [
    "sport", "projection_season", "base_season", "player_id", "player_name", "position",
    "team_id", "source", "is_rookie", "draft_overall", "confidence",
    *RAW_STAT_COLS,
    "proj_fp_std", "proj_fp_half", "proj_fp_ppr",
    "fp_ppr_sd", "fp_ppr_p10", "fp_ppr_p90", "uncertainty_type",
    "model_version", "generated_at",
]

# ── The per-player base-season raw line. Realized season totals ÷ played games → per-game counting
#    stats, plus game-to-game PPR sd, current depth-chart rank/team, and position. All from the
#    already-built NFL marts (SF-free). `week > 0` = regular+post; a played game = played_flag & not
#    bye (matches mart_player_season's games_played).
_BASE_SEASON_SQL = """
with wk as (
    select season, week, player_id, player_name, team_id, position, week_start_et,
           (played_flag and not is_bye) as g,
           pass_attempts, pass_completions, passing_yards, passing_touchdowns, interceptions,
           rushing_carries, rushing_yards, rushing_touchdowns,
           receiving_targets, receptions, receiving_yards, receiving_touchdowns,
           fantasy_points_ppr
    from {schema}.fct_player_week
    where season = {season} and week > 0
),
agg as (
    select
        player_id,
        count_if(g) as games_played,
        max(position) as position,
        sum(case when g then pass_attempts else 0 end)::double        as pass_att_tot,
        sum(case when g then pass_completions else 0 end)::double      as pass_cmp_tot,
        sum(case when g then passing_yards else 0 end)::double         as pass_yds_tot,
        sum(case when g then passing_touchdowns else 0 end)::double    as pass_td_tot,
        sum(case when g then interceptions else 0 end)::double         as pass_int_tot,
        sum(case when g then rushing_carries else 0 end)::double       as rush_att_tot,
        sum(case when g then rushing_yards else 0 end)::double         as rush_yds_tot,
        sum(case when g then rushing_touchdowns else 0 end)::double    as rush_td_tot,
        sum(case when g then receiving_targets else 0 end)::double     as targets_tot,
        sum(case when g then receptions else 0 end)::double            as rec_tot,
        sum(case when g then receiving_yards else 0 end)::double       as rec_yds_tot,
        sum(case when g then receiving_touchdowns else 0 end)::double  as rec_td_tot,
        stddev_samp(case when g then fantasy_points_ppr end)          as fp_ppr_sd,
        avg(case when g then fantasy_points_ppr end)                  as fp_ppr_pg
    from wk group by 1
),
last_team as (  -- most-recent base-season team + display name
    select player_id, team_id, player_name
    from wk qualify row_number() over (partition by player_id order by week desc, week_start_et desc) = 1
)
select a.*, lt.team_id, lt.player_name
from agg a left join last_team lt using (player_id)
where a.games_played > 0
"""

_PERGAME_MAP = {
    "pass_att": "pass_att_tot", "pass_cmp": "pass_cmp_tot", "pass_yds": "pass_yds_tot",
    "pass_td": "pass_td_tot", "pass_int": "pass_int_tot",
    "rush_att": "rush_att_tot", "rush_yds": "rush_yds_tot", "rush_td": "rush_td_tot",
    "targets": "targets_tot", "rec": "rec_tot", "rec_yds": "rec_yds_tot", "rec_td": "rec_td_tot",
}


def load_base_season(con, season: int, schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    df = con.sql(_BASE_SEASON_SQL.format(schema=schema, season=season)).df()
    g = df["games_played"].clip(lower=1)
    for base, tot in _PERGAME_MAP.items():
        df[base + "_pg"] = df[tot] / g
    # attach current depth-chart rank (the role signal for expected games)
    role = con.sql(f"""
        select player_id, depth_chart_position_rank
        from {schema}.dim_player_role where current_record_indicator = 'Y'
        qualify row_number() over (partition by player_id order by record_effective_ts desc) = 1
    """).df()
    df = df.merge(role, on="player_id", how="left")
    return df


def load_rookie_training(con, upto_season: int, schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    """Historical drafted rookies (skill positions, draft_year ≤ base season) joined to their
    rookie-year raw stat TOTALS — the training base for the draft-slot production curves."""
    rk = pd.read_parquet(_ROOKIE_PARQUET)
    rk = rk[
        rk["position_group"].isin(ROOKIE_POSITIONS)
        & pd.to_numeric(rk["draft_overall"], errors="coerce").notna()
        & (pd.to_numeric(rk["draft_year"], errors="coerce") <= upto_season)
    ][["gsis_id", "position_group", "draft_overall", "draft_year"]].copy()
    con.register("rk_train", rk)
    hist = con.sql(f"""
        with ry as (
            select r.gsis_id, r.position_group, r.draft_overall,
                count_if(f.played_flag and not f.is_bye) as games,
                sum(case when f.played_flag then f.pass_attempts else 0 end)::double as pass_att,
                sum(case when f.played_flag then f.pass_completions else 0 end)::double as pass_cmp,
                sum(case when f.played_flag then f.passing_yards else 0 end)::double as pass_yds,
                sum(case when f.played_flag then f.passing_touchdowns else 0 end)::double as pass_td,
                sum(case when f.played_flag then f.interceptions else 0 end)::double as pass_int,
                sum(case when f.played_flag then f.rushing_carries else 0 end)::double as rush_att,
                sum(case when f.played_flag then f.rushing_yards else 0 end)::double as rush_yds,
                sum(case when f.played_flag then f.rushing_touchdowns else 0 end)::double as rush_td,
                sum(case when f.played_flag then f.receiving_targets else 0 end)::double as targets,
                sum(case when f.played_flag then f.receptions else 0 end)::double as rec,
                sum(case when f.played_flag then f.receiving_yards else 0 end)::double as rec_yds,
                sum(case when f.played_flag then f.receiving_touchdowns else 0 end)::double as rec_td,
                sum(case when f.played_flag then f.fantasy_points_ppr else 0 end)::double as rookie_fp_ppr
            from rk_train r
            join {schema}.fct_player_week f
              on f.player_id = r.gsis_id and f.season = r.draft_year and f.week > 0
            group by 1,2,3
        )
        select * from ry where games > 0
    """).df()
    return hist


def load_realized_season(con, season: int, schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    """Realized convenience PPR total for a season (for the holdout backtest)."""
    return con.sql(f"""
        select player_id, count_if(played_flag and not is_bye) as g,
               sum(case when played_flag then fantasy_points_ppr else 0 end) as real_fp_ppr
        from {schema}.fct_player_week where season = {season} and week > 0
        group by 1 having g > 0
    """).df()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Projection assembly
# ══════════════════════════════════════════════════════════════════════════════════════════════
def build_projection(con, base_season: int, projection_season: int, schema: str) -> pd.DataFrame:
    base = load_base_season(con, base_season, schema)
    priors = positional_pergame_priors(base)
    vets = project_veterans(base, priors, projection_season)

    rookies_all = pd.read_parquet(_ROOKIE_PARQUET)
    incoming = rookies_all[pd.to_numeric(rookies_all["draft_year"], errors="coerce") == projection_season]
    curve = fit_rookie_slot_curves(load_rookie_training(con, base_season, schema))
    rks = project_rookies(incoming, curve, projection_season) if not incoming.empty else pd.DataFrame()

    proj = pd.concat([vets, rks], ignore_index=True, sort=False)
    proj["sport"] = "nfl"
    proj["base_season"] = int(base_season)
    proj["model_version"] = MODEL_VERSION
    proj["generated_at"] = datetime.now(timezone.utc).isoformat()
    # keep only draft-relevant offensive positions (drop K/DEF/defensive rows with no fantasy line)
    proj = proj[proj["position"].isin(("QB", "RB", "WR", "TE", "FB"))].copy()
    for c in OUTPUT_COLS:
        if c not in proj.columns:
            proj[c] = np.nan
    proj = proj[OUTPUT_COLS].sort_values("proj_fp_ppr", ascending=False).reset_index(drop=True)
    return proj


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Validation — coverage + face-validity + holdout sanity (the edge-independent gate)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def coverage_report(proj: pd.DataFrame, base: pd.DataFrame) -> dict:
    by_pos = proj.groupby("position").size().to_dict()
    vets = proj[~proj["is_rookie"]]
    rks = proj[proj["is_rookie"]]
    # draft-relevant base-season players that did NOT get a projection (gap)
    projected_ids = set(proj["player_id"])
    relevant = base[base["games_played"] >= 4]
    gap = relevant[~relevant["player_id"].isin(projected_ids)]
    return {
        "n_total": int(len(proj)),
        "n_veterans": int(len(vets)),
        "n_rookies": int(len(rks)),
        "by_position": {k: int(v) for k, v in sorted(by_pos.items())},
        "n_rookies_by_pos": {k: int(v) for k, v in rks.groupby("position").size().items()},
        "n_base_relevant_players_ge4g": int(len(relevant)),
        "n_relevant_gap": int(len(gap)),
        "pct_relevant_covered": round(100.0 * (1 - len(gap) / max(1, len(relevant))), 1),
    }


def holdout_backtest(con, base_season: int, target_season: int, schema: str) -> dict:
    """Replicate the VETERAN method for an earlier base season and score its projected PPR ranking
    against the realized next season. The behavioural sanity check that the method has signal (rank
    correlation), not a calibration claim."""
    base = load_base_season(con, base_season, schema)
    priors = positional_pergame_priors(base)
    vets = project_veterans(base, priors, target_season)
    vets = vets[vets["position"].isin(("QB", "RB", "WR", "TE", "FB"))]
    real = load_realized_season(con, target_season, schema)
    m = vets.merge(real, on="player_id", how="inner")
    m = m[m["g"] >= 6]  # players who actually played the target season
    if len(m) < 30:
        return {"n": int(len(m)), "note": "insufficient overlap for a stable read"}
    sp = m[["proj_fp_ppr", "real_fp_ppr"]].corr(method="spearman").iloc[0, 1]
    pr = m[["proj_fp_ppr", "real_fp_ppr"]].corr(method="pearson").iloc[0, 1]
    mae = float((m["proj_fp_ppr"] - m["real_fp_ppr"]).abs().mean())
    # top-24 overlap (a "did we identify the studs" read)
    top_proj = set(m.nlargest(24, "proj_fp_ppr")["player_id"])
    top_real = set(m.nlargest(24, "real_fp_ppr")["player_id"])
    return {
        "base_season": base_season, "target_season": target_season, "n": int(len(m)),
        "spearman": round(float(sp), 3), "pearson": round(float(pr), 3), "mae_ppr": round(mae, 1),
        "top24_overlap": len(top_proj & top_real), "top24_of": 24,
    }


def _md_table(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False, floatfmt=".1f")
    except Exception:  # noqa: BLE001
        return df.to_string(index=False)


def write_report(proj: pd.DataFrame, cov: dict, backtests: list[dict], path: Path,
                 base_season: int, projection_season: int) -> None:
    a = []
    p = a.append
    p(f"# NF-FASTPATH — {projection_season} NFL fantasy season projections (raw stat-line, MVP-1)")
    p("")
    p(f"**Model:** `{MODEL_VERSION}` · **base season:** {base_season} → **projects:** {projection_season} "
      f"· **generated:** {datetime.now(timezone.utc).isoformat()}")
    p("")
    p("> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate (that is the "
      "betting posture). The gate is FACE-VALIDITY + COVERAGE + a holdout rank-correlation sanity "
      "check. The emitted `proj_*` columns are a **RAW STAT LINE** (season totals); the `proj_fp_*` "
      "points are a CONVENIENCE (standard nflverse scoring) for ranking/validation only — **MVP-2 / "
      "NF-C1 rescore the raw line per league**. Uncertainty is surfaced (an 80% PPR interval), not "
      "hidden; NULL = unknown kept NULL. Rookie intervals use PARAMETER uncertainty (slot-curve + "
      "P1A) and must be recalibrated before pricing.")
    p("")
    p("## 1. The projection method (honest framing)")
    p("")
    p("- **Veterans** — realized base-season per-game line, shrunk toward a conservative positional "
      "prior (position median over qualified players) by sample size `w = g/(g+5)`, then scaled by "
      "an **EXPECTED-GAMES** estimate = a 50/50 blend of depth-chart role and base-season durability. "
      "Expected-games is the fix for the naïve `per_game × 17` that ranks small-sample backups at the "
      "top of `mart_projections_preseason` (Malik Willis was its #1).")
    p("- **Rookies (QB/RB/WR/TE)** — a historical draft-slot → rookie-year production curve (power-law "
      "per position, fit on prior classes) nudged by the **NCAAF-P1A residual** (`projected_nfl_z` vs "
      "the slot-expected z — talent the draft board disagreed with), with deliberately wide intervals. "
      "Defensive/OL rookies carry no fantasy line and are excluded (≈0, per P1A).")
    p("")
    p("## 2. Coverage report")
    p("")
    p("```json")
    p(json.dumps(cov, indent=2))
    p("```")
    p("")
    p("## 3. Holdout-season sanity check (does the veteran method have signal?)")
    p("")
    p("Replicate the veteran projection for an earlier base season and score its projected PPR ranking "
      "against the realized next season, over players who actually played the target season. Spearman "
      "(rank) is the headline; this is a signal check, not a calibration claim.")
    p("")
    if backtests:
        p(_md_table(pd.DataFrame(backtests)))
    p("")
    p("## 4. Face validity — top 25 overall (projected PPR)")
    p("")
    show = ["player_name", "position", "team_id", "source", "proj_games",
            "proj_fp_ppr", "fp_ppr_p10", "fp_ppr_p90"]
    p(_md_table(proj.head(25)[show]))
    p("")
    for pos in ("QB", "RB", "WR", "TE"):
        p(f"### Top 12 {pos}")
        p("")
        p(_md_table(proj[proj["position"] == pos].head(12)[show]))
        p("")
    p("## 5. Face validity — top 15 ROOKIES (P1A-attached)")
    p("")
    rk = proj[proj["is_rookie"]].head(15)[
        ["player_name", "position", "draft_overall", "proj_games", "proj_fp_ppr", "fp_ppr_p10", "fp_ppr_p90"]
    ]
    p(_md_table(rk))
    p("")
    p("## 6. Limitations")
    p("")
    p("- **First-pass MVP** — the full NF1 model (posterior-predictive, weekly, §0.5 bake-off) refines "
      "this. The gate here is face-validity + coverage, not a selected model.")
    p("- **Expected-games is a role heuristic, not a depth-chart oracle** — offseason moves (trades, "
      "signings, camp battles, holdouts) are not yet ingested; a base-season backup who wins a 2026 "
      "job is under-projected until depth charts refresh. Surfaced via the wide games interval.")
    p("- **Rookie uncertainty is PARAMETER uncertainty** (slot curve + P1A `sd`), not a calibrated "
      "predictive interval — NF-C1/pricing must recalibrate (the E13.6 pattern).")
    p("- **Rookie team = NULL** (2026 draftees are not in the base-season role dimension) — kept NULL, "
      "not guessed.")
    p("- **Two-point conversions kept NULL** (rare/idiosyncratic); fumbles-lost is a modest per-touch "
      "estimate. Both are small scoring nuisance terms.")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-FASTPATH — 2026 NFL fantasy season projections")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--base-season", type=int, default=None,
                    help="completed base season (default: max(season) in fct_player_week)")
    ap.add_argument("--projection-season", type=int, default=None,
                    help="season to project (default: base_season + 1)")
    ap.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    ap.add_argument("--s3", action="store_true", help="also land the projection to the S3 sports lake")
    ap.add_argument("--lake-root", default=None, help="land to a LOCAL-FS Delta tree instead of S3")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if args.s3 and args.lake_root:
        ap.error("--s3 and --lake-root are mutually exclusive")
    if not Path(args.duckdb).exists():
        ap.error(f"DuckDB not found at {args.duckdb} — build the NFL marts first (see module docstring)")

    import duckdb

    con = duckdb.connect(args.duckdb, read_only=True)
    try:
        base_season = args.base_season or int(
            con.sql(f"select max(season) from {args.schema}.fct_player_week").fetchone()[0])
        projection_season = args.projection_season or (base_season + 1)
        log.info("base season %d → projecting %d", base_season, projection_season)

        proj = build_projection(con, base_season, projection_season, args.schema)
        log.info("projected %d players (%d veterans, %d rookies)",
                 len(proj), int((~proj["is_rookie"]).sum()), int(proj["is_rookie"].sum()))

        base = load_base_season(con, base_season, args.schema)
        cov = coverage_report(proj, base)
        log.info("coverage: %s", cov)

        backtests = []
        for bs in (base_season - 3, base_season - 2):
            if bs >= 2003:
                bt = holdout_backtest(con, bs, bs + 1, args.schema)
                log.info("holdout %d→%d: %s", bs, bs + 1, bt)
                backtests.append(bt)
    finally:
        con.close()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pq = out_dir / f"nfl_fantasy_season_projections_{projection_season}.parquet"
    proj.to_parquet(pq, index=False)
    log.info("wrote %s", pq)

    ranked = proj.copy()
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
    ranked.insert(1, "pos_rank", ranked.groupby("position").cumcount() + 1)
    csv = out_dir / f"nfl_fantasy_season_projections_{projection_season}_ranked.csv"
    ranked.to_csv(csv, index=False)
    log.info("wrote %s", csv)

    (out_dir / f"nfl_fantasy_season_projections_{projection_season}_summary.json").write_text(
        json.dumps({"model_version": MODEL_VERSION, "base_season": base_season,
                    "projection_season": projection_season, "coverage": cov,
                    "holdout_backtests": backtests,
                    "generated_at": datetime.now(timezone.utc).isoformat()}, indent=2, default=float))

    if args.s3 or args.lake_root:
        from quant_sports_intel_models.football.nfl.ingest import s3io

        n = s3io.write_dataframe(
            proj.assign(season=int(projection_season)), sport="nfl", source="season_projections",
            season=int(projection_season), tier="fantasy/derived", local_root=args.lake_root)
        dest = f"local lake {args.lake_root}" if args.lake_root else "the S3 sports lake"
        log.info("landed %d projection rows in %s (nfl/fantasy/derived/season_projections)", n, dest)

    if not args.no_report:
        write_report(proj, cov, backtests, _REPORT_PATH, base_season, projection_season)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
