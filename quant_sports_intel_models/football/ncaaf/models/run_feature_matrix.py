"""run_feature_matrix.py — NCAAF-P1.3 CLI: cache the pregame feature matrix + prove it clean.

The JOIN is dbt (`feature_ncaaf_pregame_matrix`). This driver does the four things the story asks
that dbt cannot: (1) pulls the matrix ONCE → a cached parquet the P1.4 bake-off reads (the MLB
cost-hygiene one-pull rule); (2) VERIFIES every join on the REAL build — grain 1:1 (fan-out guard),
no dropped games, and a per-family per-season COVERAGE report so a silently-dead family surfaces
here, not in P1.4 (banner A); (3) runs the DATE-based leakage gate on the real build AND proves it
BITES by tampering a row (banner B); (4) writes the report + optionally lands the parquet in S3.

Usage (LAPTOP, after a sports dbt build incl. the P1.2 + P1.2b scripts + `--select +ncaaf_p1_3`):
    uv run python -m quant_sports_intel_models.football.ncaaf.models.run_feature_matrix \
        --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb

Usage (EC2 BOX, after `sports_ncaaf_dbt_build_job` + the P1.2/P1.2b scripts + the ncaaf_p1_3 build):
    docker compose -f services/dagster/aws/docker-compose.yml exec -T \
        -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \
        python -m quant_sports_intel_models.football.ncaaf.models.run_feature_matrix \
        --duckdb /tmp/sports_ncaaf.duckdb --s3

Outputs:
  * <out-dir>/feature_ncaaf_pregame_matrix.parquet         — the cached matrix (P1.4's input)
  * <out-dir>/ncaaf_feature_matrix_summary.json            — gates + coverage + shape
  * s3://credence-sports-lakehouse/ncaaf/derived/feature_pregame_matrix/ (--s3)
  * quant_sports_intel_models/football/ncaaf/ablation_results/ncaaf_p1_3_feature_matrix.md
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

from quant_sports_intel_models.football.ncaaf.models.feature_matrix import (  # noqa: E402
    FAMILIES,
    family_coverage,
    leakage_violations,
    verify_join_grain,
)

log = logging.getLogger("ncaaf.p1_3")

MARTS_SCHEMA = "main_ncaaf_marts"
MATRIX_TABLE = "feature_ncaaf_pregame_matrix"
FACT_TABLE = "fact_ncaaf_team_game"
GAME_DIM = "dim_ncaaf_game"

_DEFAULT_OUT = _PROJECT_ROOT / "quant_sports_intel_models/football/ncaaf/models/artifacts"
_REPORT_PATH = (
    _PROJECT_ROOT
    / "quant_sports_intel_models/football/ncaaf/ablation_results/ncaaf_p1_3_feature_matrix.md"
)


def _load(duckdb_path: str, schema: str):
    import duckdb

    con = duckdb.connect(duckdb_path, read_only=True)
    try:
        matrix = con.sql(f"select * from {schema}.{MATRIX_TABLE}").df()
        team_games = con.sql(
            f"select season, team_id, game_id, is_completed, season_order_week, game_date "
            f"from {schema}.{FACT_TABLE}"
        ).df()
        n_fbs_games = con.sql(
            f"select count(*) from {schema}.{GAME_DIM} where is_fbs_matchup"
        ).fetchone()[0]
    finally:
        con.close()
    log.info("loaded %-32s %7d rows", MATRIX_TABLE, len(matrix))
    log.info("loaded %-32s %7d rows", FACT_TABLE, len(team_games))
    return matrix, team_games, int(n_fbs_games)


def validate(matrix: pd.DataFrame, team_games: pd.DataFrame, n_fbs_games: int) -> tuple[list[str], dict]:
    """The join + leakage gates. Raises on a violation (HALT-tier). Returns (checks, shape)."""
    checks: list[str] = []

    # 1. Grain — 1:1, no fan-out (a broadcast join that fanned out duplicates game_id).
    shape = verify_join_grain(matrix)
    checks.append(f"grain is 1-row-per-game — no join fanned out ({shape['n_games']:,} games, unique)")

    # 2. No dropped games — the spine is every FBS-vs-FBS game (LEFT joins never shrink it).
    if shape["n_games"] != n_fbs_games:
        raise AssertionError(
            f"matrix has {shape['n_games']:,} games but dim_ncaaf_game has {n_fbs_games:,} "
            f"FBS-vs-FBS games — a join DROPPED rows (should be a LEFT-join spine)."
        )
    checks.append(f"no games dropped — matrix == dim_ncaaf_game FBS universe ({n_fbs_games:,})")

    # 3. Labels are POST-KICKOFF and prefixed; every feature-side column is NOT label-prefixed.
    label_cols = [c for c in matrix.columns if c.startswith("label_")]
    if not label_cols:
        raise AssertionError("no label_* columns — P1.4 has no target")
    checks.append(f"{len(label_cols)} label_* target columns present + prefixed (never a feature)")

    # 4. LEAKAGE GATE on the real build — must be EMPTY.
    viol = leakage_violations(matrix, team_games)
    if len(viol):
        raise AssertionError(
            f"LEAKAGE: {len(viol)} matchup-sides fail the point-in-time gate. Sample:\n"
            f"{viol.head(10).to_string(index=False)}"
        )
    checks.append(f"DATE-based leakage gate PASSES on the real build ({2 * shape['n_games']:,} sides, 0 violations)")

    # 5. PROVE THE GATE BITES (banner B) — tamper a row so a prior game post-dates its kickoff.
    #    Pick a matchup with ≥1 prior game and shove its kickoff BEFORE its window → clock-sanity fires.
    played = matrix[(matrix["home_games_played"].fillna(0) > 0)].copy()
    if len(played):
        tampered = matrix.copy()
        idx = played.index[0]
        tampered.loc[idx, "game_date"] = pd.Timestamp("2000-01-01")  # long before any prior game
        tviol = leakage_violations(tampered, team_games)
        if not len(tviol):
            raise AssertionError(
                "the leakage gate did NOT fire on a tampered (back-dated) row — the gate is a "
                "no-op and its green means nothing. FIX the gate before trusting the matrix."
            )
        checks.append(f"leakage gate PROVEN to fail on a tampered/back-dated row ({len(tviol)} violations raised)")
    else:
        checks.append("⚠️ no game with a prior-game window to tamper — gate-bite proof deferred to the unit test")

    return checks, shape


def write_report(matrix, cov, checks, shape, path: Path) -> None:
    lines: list[str] = []
    a = lines.append
    seasons = sorted(matrix["season"].unique())
    feat_cols = [c for c in matrix.columns if c.startswith(("home_", "away_"))]
    label_cols = [c for c in matrix.columns if c.startswith("label_")]

    a("# NCAAF-P1.3 — the pregame feature matrix (`feature_ncaaf_pregame_matrix`)")
    a("")
    a(f"**Generated:** {datetime.now(timezone.utc).isoformat()}")
    a(f"**Shape:** {shape['n_games']:,} FBS-vs-FBS games ({seasons[0]}–{seasons[-1]}) × "
      f"{len(matrix.columns)} columns — {len(feat_cols)} home_/away_ feature columns across "
      f"{len(FAMILIES)} families, {len(label_cols)} POST-KICKOFF `label_*` targets.")
    a("")
    a("> ⚠️ **This is a leakage-safe FEATURE matrix, not an edge claim.** Every `home_*`/`away_*` "
      "column is snapshot AS OF that game's own kickoff (as_of_week = its `season_order_week`); "
      "`label_*` is the POST-KICKOFF target P1.4 predicts and must NEVER be fed as a feature. "
      "`best_alpha = 0` holds — whether any of this beats a closing line is P1.4's question under "
      "full §0.5 deflation. NULL = unknown and is kept NULL; P1.4's learners handle missingness.")
    a("")

    a("## 1. Gates (all HALT-tier)")
    a("")
    for c in checks:
        a(f"- ✅ {c}")
    a("")

    a("## 2. Per-family coverage (% non-null, pooled over both sides, per season) — banner A")
    a("")
    a("A family reading ~0% where it should be present is a silently-dead join (the F2/INC-31 "
      "class) and must be caught HERE, not in P1.4. A LEGITIMATELY-empty cell is expected and "
      "labelled below — read the table, do not just scan for green:")
    a("")
    a("- **strength (P1.2)** is NULL for **2014** (P1.2 emits 2015+) and thin at each season's "
      "week 1 only in `_sd` terms — the point estimate is a preseason posterior, never NULL.")
    a("- **portal_flux (P0.4)** is a real 0 (not NULL) from **2021** on; pre-2021 the portal feed "
      "does not exist (`portal_data_covered = false`) — do not read pre-2021 portal as 'no churn'.")
    a("- **efficiency / opp_adj / drive / pace / qb** are NULL at each team's **week 1** and for "
      "teams with no play coverage — the honest 'no games yet' unknown.")
    a("- **travel/altitude** is NULL on **neutral sites** by design (venue geography is not "
      "attributed to a neutral game — §7 gap 2) and wherever a venue lat/long is missing.")
    a("")
    pivot = cov.pivot(index="family", columns="season", values="coverage_pct").fillna(0.0)
    a(pivot.to_markdown(floatfmt=".0f"))
    a("")

    a("## 3. The families + their sources / grain / as-of semantics")
    a("")
    a("| Family | Representative cols | Source mart | Join grain | As-of |")
    a("|---|---|---|---|---|")
    a("| Team strength | `{home,away}_strength_margin`, `_offense`, `_defense`, `_sd` | "
      "`ncaaf_team_strength_week` (P1.2) | (season, team_id, as_of_week) **1:1** | kickoff week |")
    a("| Efficiency (raw) | `{home,away}_off_ppa`, `_success_rate`, `_explosiveness`, `_clean_*` | "
      "`rollup_ncaaf_team_week_asof` (P1.1) | (season, team_id, as_of_week) **1:1** | kickoff week |")
    a("| Efficiency (opp-adj) | `{home,away}_adj_net_ppa`, `_adj_off/def_*`, `_sos_opponent_net_ppa` | "
      "`rollup_ncaaf_team_week_opponent_adjusted` (P1.1) | (season, team_id, as_of_week) **1:1** | kickoff week |")
    a("| Pace / style | `{home,away}_off_plays_per_game`, `_seconds_per_play`, `_possession_seconds_per_game` | "
      "`rollup_ncaaf_team_week_asof` | 1:1 | kickoff week |")
    a("| Line / trench (UNIT proxies) | `{home,away}_off/def_line_yards`, `_off/def_stuff_rate` | "
      "`rollup_ncaaf_team_week_asof` | 1:1 | kickoff week |")
    a("| Drive quality | `{home,away}_points_per_drive`, `_scoring_opportunity_rate`, `_three_and_out_rate` | "
      "`rollup_ncaaf_team_week_asof` | 1:1 | kickoff week |")
    a("| Roster continuity / portal / talent | `{home,away}_returning_ppa_pct`, `_roster_continuity_pct`, "
      "`_portal_net_count`, `_team_talent` | `ncaaf_team_roster_continuity` (P0.4) | (season, team) **BROADCAST** | pre-season |")
    a("| Freshman prior | `{home,away}_freshman_proj_production`, `_top_proj_production`, `_avg_rating`, "
      "`_blue_chip_count` | `ncaaf_team_freshman_prior` (P1.2b) | (season, team) **BROADCAST** | pre-season |")
    a("| Coaching (HC-only) | `{home,away}_hc_tenure_years`, `_hc_change_from_prev`, `_hc_prior_sp_*` | "
      "`ncaaf_team_coaching_change` (P0.5) | (season, team) **BROADCAST** | pre-season |")
    a("| QB continuity | `{home,away}_qb_starts_prior`, `_qb_distinct_starters_prior`, "
      "`_qb_starter_changed_recent`, `_qb_trailing_ypa/qbr` | `fact_ncaaf_player_game` (derived) | "
      "per matchup side, prior starts only | strictly prior games |")
    a("| Situational | `is_neutral_site`, `is_conference_game`, `{home,away}_rest_days`, `season_order_week` | "
      "`dim_ncaaf_game` + schedule | game-level | kickoff |")
    a("| Environment (travel/altitude) | `away_travel_km`, `away_altitude_change_m`, "
      "`game_venue_elevation_m`, `game_venue_is_dome/grass` | `dim_ncaaf_team` venue geo | game-level, non-neutral | kickoff |")
    a("")

    a("## 4. Honest scope notes (what is NOT in the matrix, and why)")
    a("")
    a("- **QB has no injury flag** — college football has no mandated injury report and P0.1 "
      "established no injury source, so the QB block is the DERIVABLE half only: starter "
      "continuity + a trailing efficiency proxy from strictly-prior starts. Not an availability signal.")
    a("- **Coaching is HEAD-COACH-only** — OC/DC coordinators have no free CFBD endpoint (P0.5 "
      "deferred them, gated like NIL-$). No `is_rivalry` — no confirmed CFBD field / maintained "
      "pair list was available, so it is dropped rather than guessed (banner (3b)).")
    a("- **Line/trench is UNIT-level** — individual-OL production is the confirmed PFF-only gap; "
      "sack-rate-allowed / DL-havoc are not in the rollup (a §7 refinement if a P1.4 ablation wants them).")
    a("- **Travel DISTANCE is included (non-neutral) — a deliberate, verified departure from the "
      "P1.1-update banner's 'drop travel/altitude'.** That banner predates confirming `venue_latitude`"
      "/`venue_longitude` are in fact staged on `stg_ncaaf_teams` → travel/altitude ARE buildable "
      "for the ~non-neutral majority, so they ship coverage-flagged for P1.4 to ablate. Neutral-site "
      "venue geography stays NULL (§7 gap 2 — not attributed).")
    a("- **Uncertainty columns (`_strength_margin_sd`) are PARAMETER uncertainty** — relative "
      "confidence only, ~1.5× too tight to price directly. P1.4 recalibrates (the E13.6 pattern).")
    a("- **NULL is kept NULL, never imputed to 0** — week-1, no-coverage, first-time HC, pre-2021 "
      "portal, 2014 strength. The imputation choice belongs to P1.4's learners, not the matrix.")
    a("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    log.info("report → %s", path)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="NCAAF-P1.3 pregame feature-matrix cache + gates")
    p.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb",
                   help="path to the sports dbt DuckDB (box: /tmp/sports_ncaaf.duckdb)")
    p.add_argument("--schema", default=MARTS_SCHEMA)
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    p.add_argument("--s3", action="store_true", help="also land the cached matrix in the sports lake")
    p.add_argument("--no-report", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    if not Path(args.duckdb).exists():
        p.error(f"DuckDB not found at {args.duckdb} — run the sports dbt build first (needs "
                f"{MATRIX_TABLE}; build order: P1.1 marts → strength + freshman scripts → "
                f"dbt run --select +feature_ncaaf_pregame_matrix)")

    matrix, team_games, n_fbs_games = _load(args.duckdb, args.schema)
    if matrix.empty:
        log.error("feature matrix is EMPTY — check the build order (the ncaaf_p1_3 tag is opt-in)")
        return 1

    checks, shape = validate(matrix, team_games, n_fbs_games)
    for c in checks:
        log.info("gate ✅ %s", c)

    cov = family_coverage(matrix)
    log.info("per-family coverage (latest season):\n%s",
             cov[cov["season"] == cov["season"].max()][["family", "coverage_pct"]].to_string(index=False))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix.to_parquet(out_dir / "feature_ncaaf_pregame_matrix.parquet", index=False)
    log.info("cached matrix → %s", out_dir / "feature_ncaaf_pregame_matrix.parquet")

    (out_dir / "ncaaf_feature_matrix_summary.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_games": shape["n_games"],
        "n_columns": int(len(matrix.columns)),
        "n_feature_columns": int(len([c for c in matrix.columns if c.startswith(("home_", "away_"))])),
        "n_label_columns": int(len([c for c in matrix.columns if c.startswith("label_")])),
        "seasons": [int(s) for s in sorted(matrix["season"].unique())],
        "families": list(FAMILIES.keys()),
        "coverage": cov.to_dict(orient="records"),
        "gates_passed": checks,
    }, indent=2, default=float))

    if args.s3:
        from quant_sports_intel_models.football.ncaaf.ingest import s3io

        for season, part in matrix.groupby("season"):
            s3io.write_dataframe(part, sport="ncaaf", source="feature_pregame_matrix",
                                 season=int(season), tier="derived")
        log.info("landed the cached matrix in the sports lake (derived tier)")

    if not args.no_report:
        write_report(matrix, cov, checks, shape, _REPORT_PATH)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
