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
# Per-player-PER-SEASON realized line over a multi-year window. The weighting into a single
# per-game line (recency + games) happens in pandas — see load_base_season. `week > 0` = reg+post.
_MULTI_SEASON_SQL = """
with wk as (
    select season, week, player_id, player_name, team_id, position, week_start_et,
           (played_flag and not is_bye) as g,
           pass_attempts, pass_completions, passing_yards, passing_touchdowns, interceptions,
           rushing_carries, rushing_yards, rushing_touchdowns,
           receiving_targets, receptions, receiving_yards, receiving_touchdowns,
           fantasy_points_ppr
    from {schema}.fct_player_week
    where season between {lo} and {season} and week > 0
)
select
    player_id, season,
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
    stddev_samp(case when g then fantasy_points_ppr end)          as fp_ppr_sd
from wk group by 1, 2 having count_if(g) > 0
"""

_PERGAME_MAP = {
    "pass_att": "pass_att_tot", "pass_cmp": "pass_cmp_tot", "pass_yds": "pass_yds_tot",
    "pass_td": "pass_td_tot", "pass_int": "pass_int_tot",
    "rush_att": "rush_att_tot", "rush_yds": "rush_yds_tot", "rush_td": "rush_td_tot",
    "targets": "targets_tot", "rec": "rec_tot", "rec_yds": "rec_yds_tot", "rec_td": "rec_td_tot",
}

# Multi-year regression: a season's weight decays by recency and scales by that season's games, so a
# 3-yr window regresses a CAREER-YEAR (or a down/injured year) toward the player's own baseline. This
# is the fix for single-season recency bias — the noisy spike stats (esp. rushing TDs) mean-revert
# instead of anchoring the projection (the Trevor-Lawrence-as-QB2 failure).
_RECENCY_DECAY = 0.6   # weight of a season one year older than the base season
_WINDOW_YEARS = 3      # base season + the two prior


def load_base_season(con, season: int, schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    lo = season - (_WINDOW_YEARS - 1)
    per_season = con.sql(_MULTI_SEASON_SQL.format(schema=schema, season=season, lo=lo)).df()
    if per_season.empty:
        return per_season

    # per-season per-game rates
    gps = per_season["games_played"].clip(lower=1)
    for base, tot in _PERGAME_MAP.items():
        per_season[base + "_pg"] = per_season[tot] / gps
    # season weight = decay^(age) × games (an injury-shortened year contributes less)
    age = season - per_season["season"]
    per_season["_w"] = (_RECENCY_DECAY ** age) * per_season["games_played"]

    pg_cols = [b + "_pg" for b in _PERGAME_MAP]

    def _blend(g: pd.DataFrame) -> pd.Series:
        w = g["_w"].to_numpy()
        wsum = w.sum() or 1.0
        out = {c: float((g[c].to_numpy() * w).sum() / wsum) for c in pg_cols}
        return pd.Series(out)

    weighted = per_season.groupby("player_id").apply(_blend, include_groups=False)

    # anchor on the BASE SEASON: a player must have appeared in the season we project off to be
    # draft-relevant for the upcoming one (excludes retired / out-of-league players the multi-year
    # window would otherwise sweep in). Role/team/sd/durability all come from that base season.
    base = per_season[per_season["season"] == season].set_index("player_id")
    weighted = weighted.join(base[["games_played", "fp_ppr_sd", "position"]], how="inner")
    df = weighted.reset_index()

    # team + display name from the most-recent base-season week
    meta = con.sql(f"""
        select player_id, team_id, player_name
        from {schema}.fct_player_week
        where season = {season} and week > 0
        qualify row_number() over (partition by player_id order by week desc, week_start_et desc) = 1
    """).df()
    df = df.merge(meta, on="player_id", how="left")

    # current depth-chart rank (role signal for expected games)
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


def score_vs_realized(con, proj: pd.DataFrame, target_season: int, schema: str) -> dict:
    """Grade a FULL emitted projection (veterans + rookies) against the realized target season —
    overall + per-position Spearman (rank), MAE, and realized-top-24 hit rate. Only valid for a
    COMPLETED season (realized exists). This is the multi-season backtest the MVP is judged on."""
    real = load_realized_season(con, target_season, schema)
    m = proj.merge(real, on="player_id", how="inner")
    m = m[m["g"] >= 6]
    if len(m) < 30:
        return {"projection_season": target_season, "n": int(len(m)), "note": "thin overlap"}

    def _sp(d):
        return float(d[["proj_fp_ppr", "real_fp_ppr"]].corr(method="spearman").iloc[0, 1])

    top = min(24, len(m))
    hit = len(set(m.nlargest(top, "proj_fp_ppr")["player_id"]) & set(m.nlargest(top, "real_fp_ppr")["player_id"]))
    out = {"projection_season": target_season, "n": int(len(m)),
           "spearman_all": round(_sp(m), 3), "mae_ppr": round(float((m["proj_fp_ppr"] - m["real_fp_ppr"]).abs().mean()), 1),
           f"top{top}_hit": f"{hit}/{top}"}
    for pos in ("QB", "RB", "WR", "TE"):
        d = m[m["position"] == pos]
        if len(d) >= 10 and d["proj_fp_ppr"].std() > 0 and d["real_fp_ppr"].std() > 0:
            out[f"sp_{pos}"] = round(_sp(d), 3)
    return out


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
    p("- **Veterans** — a **3-year recency+games-weighted** per-game line (weight = 0.6^age × games, "
      "so a career year or a down/injured year regresses toward the player's own baseline — the fix "
      "for single-season recency bias, esp. the spiky rushing-TD stat that ranked Trevor Lawrence "
      "QB2 off a fluke 9-rush-TD 2025), shrunk toward a conservative positional prior (position "
      "median) by sample size `w = g/(g+5)`, then scaled by an **EXPECTED-GAMES** estimate = a 50/50 "
      "blend of depth-chart role and base-season durability. Expected-games is the fix for the naïve "
      "`per_game × 17` that ranks small-sample backups at the top of `mart_projections_preseason` "
      "(Malik Willis was its #1).")
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
    p("## 3. Multi-season backtest — this model vs realized outcomes")
    p("")
    p("Each PRIOR season below was projected with the SAME model (base = season−1, 3-yr regression) and "
      "scored against what actually happened — the FULL projection (veterans + rookies), over players "
      "who played ≥6 games. `spearman_all` (rank) is the headline; `sp_<POS>` is within-position rank "
      "correlation (what matters for drafting); `topN_hit` = of the realized top-24, how many the model "
      "ranked top-24. A signal check across seasons, not a calibration claim.")
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
                    help="the primary (forward) season to project (default: base_season + 1)")
    ap.add_argument("--backtest-from", type=int, default=None,
                    help="ALSO emit projections for every prior season from this year through the "
                         "primary season (each projected off its own season-1 with the multi-year "
                         "model), and score each completed one vs realized. E.g. --backtest-from 2019")
    ap.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    ap.add_argument("--s3", action="store_true", help="also land the projection(s) to the S3 sports lake")
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

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.s3 or args.lake_root:
        from quant_sports_intel_models.football.nfl.ingest import s3io

    con = duckdb.connect(args.duckdb, read_only=True)
    try:
        base_season = args.base_season or int(
            con.sql(f"select max(season) from {args.schema}.fct_player_week").fetchone()[0])
        primary_season = args.projection_season or (base_season + 1)
        # the set of projection seasons to emit — the forward one, plus any backtest history
        seasons = [primary_season]
        if args.backtest_from:
            seasons = sorted(set(range(args.backtest_from, primary_season + 1)) | {primary_season})
        log.info("emitting projection seasons: %s", seasons)

        primary_proj = primary_cov = None
        backtests: list[dict] = []
        for y in seasons:
            base_y = y - 1
            proj = build_projection(con, base_y, y, args.schema)
            log.info("  %d (base %d): %d players (%d vets, %d rookies)", y, base_y, len(proj),
                     int((~proj["is_rookie"]).sum()), int(proj["is_rookie"].sum()))

            # local artifacts per season
            proj.to_parquet(out_dir / f"nfl_fantasy_season_projections_{y}.parquet", index=False)
            ranked = proj.copy()
            ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
            ranked.insert(1, "pos_rank", ranked.groupby("position").cumcount() + 1)
            ranked.to_csv(out_dir / f"nfl_fantasy_season_projections_{y}_ranked.csv", index=False)

            # land the Delta partition (season = projection year)
            if args.s3 or args.lake_root:
                n = s3io.write_dataframe(
                    proj.assign(season=int(y)), sport="nfl", source="season_projections",
                    season=int(y), tier="fantasy/derived", local_root=args.lake_root)
                log.info("    landed %d rows → nfl/fantasy/derived/season_projections season=%d", n, y)

            # score vs realized for completed seasons (the backtest)
            if y <= base_season:
                acc = score_vs_realized(con, proj, y, args.schema)
                log.info("    backtest %d: %s", y, acc)
                backtests.append(acc)

            if y == primary_season:
                primary_proj = proj
                primary_cov = coverage_report(proj, load_base_season(con, base_y, args.schema))
                log.info("  primary %d coverage: %s", y, primary_cov)
    finally:
        con.close()

    (out_dir / "nfl_fantasy_projections_summary.json").write_text(
        json.dumps({"model_version": MODEL_VERSION, "primary_season": primary_season,
                    "seasons_emitted": seasons, "coverage": primary_cov,
                    "backtest_vs_realized": backtests,
                    "generated_at": datetime.now(timezone.utc).isoformat()}, indent=2, default=float))
    dest = f"local lake {args.lake_root}" if args.lake_root else (
        "the S3 sports lake" if args.s3 else "(local only — no --s3)")
    log.info("done. landed to %s", dest)

    if not args.no_report and primary_proj is not None:
        write_report(primary_proj, primary_cov, backtests, _REPORT_PATH,
                     primary_season - 1, primary_season)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
