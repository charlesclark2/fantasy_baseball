"""run_freshman_projection.py — NCAAF-P1.2b CLI: fit the recruit→freshman-production MLE.

Reads `ncaaf_recruit_production_pairs` from the sports dbt DuckDB, runs the §0.5 bake-off,
emits a leakage-safe per-recruit freshman prior + the (season, team) aggregate P1.3 consumes,
validates the leakage + plausibility + oracle-floor gates, and writes a markdown report.

Usage (LAPTOP, after a sports dbt build):
    uv run python -m quant_sports_intel_models.football.ncaaf.models.run_freshman_projection \
        --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb

Usage (EC2 BOX, after `sports_ncaaf_dbt_build_job`):
    docker compose -f services/dagster/aws/docker-compose.yml exec -T \
        -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \
        python -m quant_sports_intel_models.football.ncaaf.models.run_freshman_projection \
        --duckdb /tmp/sports_ncaaf.duckdb --s3

Outputs:
  * <out-dir>/ncaaf_freshman_priors.parquet          — per-recruit prior (the feature)
  * <out-dir>/ncaaf_team_freshman_prior.parquet      — (season, team) aggregate for P1.3
  * <out-dir>/ncaaf_freshman_projection_summary.json — gates + bake-off leaderboard + PBO/DSR
  * s3://credence-sports-lakehouse/ncaaf/derived/{freshman_priors,team_freshman_prior}/ (--s3)
  * quant_sports_intel_models/football/ncaaf/ablation_results/ncaaf_p1_2b_freshman_projection.md

⚠️ RUNTIME: the full bake-off (leave-one-class-out CV × ~7 configs incl. GBM quantile fits) is
minutes on the real ~15k-pair build. Per the repo's >1-minute rule this is an OPERATOR-run
script, not something a session executes inline.
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

from quant_sports_intel_models.football.ncaaf.models.freshman_projection import (  # noqa: E402
    MODEL_VERSION,
    SEED_ARRIVAL_SEASON,
    _MAX_PLAUSIBLE_Z,
    _MAX_PLAUSIBLE_Z_SD,
    FreshmanConfig,
    run_freshman_projection,
)

log = logging.getLogger("ncaaf.p1_2b")

MARTS_SCHEMA = "main_ncaaf_marts"
PAIRS_TABLE = "ncaaf_recruit_production_pairs"

_DEFAULT_OUT = _PROJECT_ROOT / "quant_sports_intel_models/football/ncaaf/models/artifacts"
_REPORT_PATH = (
    _PROJECT_ROOT
    / "quant_sports_intel_models/football/ncaaf/ablation_results/ncaaf_p1_2b_freshman_projection.md"
)


def load_pairs(duckdb_path: str, schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    import duckdb

    con = duckdb.connect(duckdb_path, read_only=True)
    try:
        df = con.sql(f"select * from {schema}.{PAIRS_TABLE}").df()
    finally:
        con.close()
    log.info("loaded %-32s %7d rows", PAIRS_TABLE, len(df))
    return df


# ══════════════════════════════════════════════════════════════════════════════════════
# Gates — leakage + plausibility + oracle-floor + PBO/DSR (behavioural, per the P1.2 lesson)
# ══════════════════════════════════════════════════════════════════════════════════════


def validate(run, config: FreshmanConfig) -> list[str]:
    """Assert the P1.2b contract. Raises on a violation — HALT-tier. Returns passed checks."""
    priors = run.priors
    bake = run.bakeoff
    passed: list[str] = []

    # 1. The seed class is NEVER emitted (its map would need a <seed class the floor forbids).
    if (priors["arrival_season"] <= SEED_ARRIVAL_SEASON).any():
        raise AssertionError(
            f"arrival season {SEED_ARRIVAL_SEASON} (the seed) was emitted — its rating→production "
            f"map has no strictly-prior class and is in-sample"
        )
    passed.append(f"seed class {SEED_ARRIVAL_SEASON} not emitted (no strictly-prior map exists)")

    # 2. Every emitted prior used a STRICTLY-PRIOR training window (leakage contract, by class).
    if (priors["n_prior_classes"] < 1).any():
        raise AssertionError("a prior was emitted with zero strictly-prior training classes")
    passed.append("every emitted prior was fit on strictly-prior recruit classes (n_prior ≥ 1)")

    # 3. Grain is unique.
    dupes = priors.duplicated(subset=["player_id", "arrival_season"]).sum()
    if dupes:
        raise AssertionError(f"{dupes} duplicate (player_id, arrival_season) prior rows")
    passed.append("per-recruit grain (player_id, arrival_season) is unique")

    # 4. The projection + its uncertainty are finite and physically plausible.
    for col in ("projected_production_z", "projected_production_z_sd"):
        if not np.isfinite(priors[col]).all():
            raise AssertionError(f"{col} contains non-finite values")
    if (priors["projected_production_z_sd"] <= 0).any():
        raise AssertionError("projected_production_z_sd must be strictly positive")
    if float(priors["projected_production_z"].abs().max()) > _MAX_PLAUSIBLE_Z:
        w = priors.reindex(priors["projected_production_z"].abs().sort_values(ascending=False).index).iloc[0]
        raise AssertionError(
            f"projected_production_z reaches {w['projected_production_z']:.2f} sd "
            f"({w['arrival_season']} {w['recruit_name']}, {w['position_group']}) — above the "
            f"±{_MAX_PLAUSIBLE_Z} plausibility ceiling; the rating→production map is broken."
        )
    if float(priors["projected_production_z_sd"].max()) > _MAX_PLAUSIBLE_Z_SD:
        raise AssertionError(
            f"projected_production_z_sd reaches {priors['projected_production_z_sd'].max():.2f} — "
            f"above the {_MAX_PLAUSIBLE_Z_SD} ceiling; a coefficient is unidentified (P1.2's "
            f"±913-point leak, one rung down)."
        )
    passed.append(
        f"projection finite + plausible (|z|≤{priors['projected_production_z'].abs().max():.2f}, "
        f"sd≤{priors['projected_production_z_sd'].max():.2f})"
    )

    # 5. ORACLE-FLOOR: no candidate beat the target-seeing oracle (the metric is not inverted).
    if not bake.oracle_floor_ok:
        raise AssertionError(
            "ORACLE-FLOOR VIOLATION — a candidate scored a LOWER MAE than a model that sees the "
            "target. That is mathematically impossible and means the selection metric is inverted."
        )
    passed.append("oracle-floor holds (no candidate beats a target-seeing oracle → metric not inverted)")

    # 6. Rating must beat the null FLOOR out-of-sample (else the honest answer is 'no signal').
    lb = bake.leaderboard
    null_mae = float(lb.loc[lb["config"] == "position_mean", "oos_mae"].iloc[0])
    win_mae = float(lb["oos_mae"].min())
    if win_mae >= null_mae:
        run.notes.append(
            f"⚠️ NO SIGNAL: the winning config's OOS MAE ({win_mae:.4f}) does not beat the "
            f"position-mean null ({null_mae:.4f}) — recruiting rating adds nothing here. Emitting "
            f"the prior anyway (it degrades to the position mean), flagged for P1.3."
        )
        passed.append(f"⚠️ winner does NOT beat the null (MAE {win_mae:.4f} ≥ {null_mae:.4f}) — honest no-signal")
    else:
        passed.append(f"winner beats the position-mean null OOS (MAE {win_mae:.4f} < {null_mae:.4f})")

    # 7. Deflation gates (PBO<0.2 / DSR≥0.95) — reported, not raised: a TIED field yields a high
    #    PBO that is the NULL, not overfitting (the E2.1-r reading). Interpreted in the report.
    if bake.pbo is not None:
        passed.append(f"PBO computed = {bake.pbo.pbo:.3f} over {bake.pbo.n_configs} configs "
                      f"({'<0.2 ✅' if bake.pbo.pbo < 0.2 else 'see report — tie vs overfit'})")
    if bake.dsr is not None:
        passed.append(f"DSR computed = {bake.dsr.dsr:.3f} (n_trials={bake.dsr.n_trials})")

    return passed


# ══════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════


def write_report(run, config: FreshmanConfig, checks: list[str], corr: dict, path: Path) -> None:
    priors, team, bake = run.priors, run.team_priors, run.bakeoff
    seasons = sorted(priors["arrival_season"].unique())
    lines: list[str] = []
    a = lines.append

    a("# NCAAF-P1.2b — recruit-rating → freshman-production projection (the HS→college MLE)")
    a("")
    a(f"**Model:** `{MODEL_VERSION}` · **generated:** {datetime.now(timezone.utc).isoformat()}")
    a(f"**Classes emitted:** {seasons[0]}–{seasons[-1]} ({len(priors):,} recruit priors) · "
      f"**seed (not emitted):** {SEED_ARRIVAL_SEASON}")
    a("")
    a("> ⚠️ **This is a freshman PRIOR, not an edge claim.** It projects a recruit's first-season "
      "production from their recruiting rating, measured against realized production — never a "
      "market. `best_alpha = 0` holds; P1.4 decides whether a freshman feature earns its place. "
      "The uncertainty is **PARAMETER** uncertainty (a RELATIVE confidence signal), NOT a "
      "calibrated predictive interval — a pricing consumer MUST recalibrate on held-out data.")
    a("")

    a("## 1. Gates")
    a("")
    for c in checks:
        a(f"- ✅ {c}")
    a("")

    a("## 2. The §0.5 bake-off leaderboard (leave-one-class-out expanding-window CV)")
    a("")
    a("Every candidate is fit on STRICTLY-PRIOR classes and scored on the held-out class; the "
      "metric is MAE on the standardized production target (lower = better). `position_mean` is "
      "the NULL FLOOR (ignores rating). `oos_skill_vs_null` = how much MAE the config removes vs "
      "that null (>0 ⇒ the recruiting rating carries signal).")
    a("")
    a(bake.leaderboard.to_markdown(index=False, floatfmt=".4f"))
    a("")
    a(f"**Winner:** `{bake.winner_name}`, refit on all {len(seasons)} emittable classes for "
      f"emission.")
    a("")

    a("## 3. Overfitting deflation (PBO / DSR)")
    a("")
    if bake.pbo is not None:
        a(f"- **PBO** = {bake.pbo.pbo:.3f} over {bake.pbo.n_configs} configs × "
          f"{bake.pbo.n_splits} CSCV splits.")
        a("  - ⚠️ **Reading a high PBO correctly (E2.1-r):** if the top configs genuinely TIE, a "
          "high PBO is the NULL (which tied candidate wins is noise), not evidence of overfitting. "
          "A high PBO with a WIDE leaderboard spread IS overfitting. Read the spread above.")
    else:
        a("- PBO not computed (need ≥4 folds and ≥2 configs with a complete performance column).")
    if bake.dsr is not None:
        a(f"- **DSR** = {bake.dsr.dsr:.3f} (observed skill-Sharpe {bake.dsr.observed_sr:.3f} vs "
          f"deflated floor {bake.dsr.sr0:.3f}, n_trials={bake.dsr.n_trials}). ≥0.95 = the winner's "
          f"OOS skill survives the multiple-testing deflation.")
    else:
        a("- DSR not computed (winner skill series too short or degenerate).")
    a("")

    a("## 4. Does the projection track reality? (rating → realized freshman production)")
    a("")
    a("Correlation of the emitted `projected_production_z` with the recruit's REALIZED "
      "standardized production, per position group (emitted rows that DID produce — a true "
      "out-of-sample read, since each class's prior was fit only on strictly-prior classes). A "
      "positive, position-plausible correlation is the behavioural gate that the map learned "
      "something; a flat correlation means the recruiting rating does not predict production and "
      "the honest verdict is no signal.")
    a("")
    if corr:
        a(pd.DataFrame([{"group": k, "proj↔realized corr": v} for k, v in sorted(corr.items())])
          .to_markdown(index=False, floatfmt=".3f"))
    else:
        a("_(insufficient produced-recruit rows to estimate a stable correlation.)_")
    a("")

    a("## 5. Face validity — the top projected freshmen (most recent class)")
    a("")
    latest = seasons[-1]
    top = priors[priors["arrival_season"] == latest].nlargest(12, "projected_production_z")
    a(f"**{latest} class:**")
    a("")
    a(top[["recruit_name", "arrival_team", "position_group", "stars", "composite_rating",
           "projected_production_z", "projected_production_z_sd"]]
      .to_markdown(index=False, floatfmt=".3f"))
    a("")
    a("Read the list, do not just count it: the top projected freshmen should be blue-chip "
      "recruits at skill positions. If they are not, the map is picking up something else.")
    a("")

    a("## 6. The P1.3 team aggregate (the join contract)")
    a("")
    a("Grain **(season, team)** — a PRE-SEASON constant that P1.3 broadcasts to every "
      "`as_of_week` by joining on `(season = arrival_season, team = arrival_team)`. Columns: "
      "`n_incoming_freshmen`, `freshman_class_projected_production` (Σ over the class), "
      "`freshman_class_avg_projected_production`, `freshman_class_top_projected_production`, "
      "`freshman_class_avg_rating`, `blue_chip_count`. A team absent from this table has no "
      "bridged incoming class — LEFT JOIN and read the absence as zero projected contribution.")
    a("")
    if not team.empty:
        a(f"{len(team):,} (season, team) rows. Top projected incoming classes ({latest}):")
        a("")
        a(team[team["season"] == latest]
          .nlargest(10, "freshman_class_projected_production")
          [["team", "n_incoming_freshmen", "freshman_class_projected_production",
            "freshman_class_avg_rating", "blue_chip_count"]]
          .to_markdown(index=False, floatfmt=".2f"))
    a("")

    a("## 7. Limitations")
    a("")
    a("- **Uncertainty is PARAMETER uncertainty, not a calibrated predictive interval** — ranks "
      "confidence correctly, too tight to price. P1.3/P1.4 must recalibrate (E13.6 pattern).")
    a("- **OL and special teams have NO box production** (`box_production_available = False`): a "
      "lineman logs no stat line, so participation-via-stats reads ~0 for all of them. They get a "
      "rating-only prior from the global line and are excluded from the production VALIDATION. "
      "Their prior is a talent signal, not a validated production projection.")
    a("- **The target is WITHIN-(group, season) standardized** — it captures who produced more "
      "AMONG their positional peers that class, not an absolute yardage. That is the honestly "
      "learnable signal (rating orders within-class production); absolute cross-position "
      "production is not comparable and is not claimed.")
    a("- **The bridge is roster.recruit_ids ↔ recruiting.id** (NOT athleteId — the data-inventory "
      "doc was wrong; corrected). ~19k pairs; a recruit with no roster recruitIds link (walk-ons, "
      "some transfers) is simply absent — a coverage limit, not a bias claim.")
    a("- **JUCO/PrepSchool recruits are excluded by default** (`recruit_types`) — they arrive "
      "older and are a different translation than the clean HS→college signal.")
    a("- **Empirical-Bayes plug-in** (partial-pool winner): the variance components are point "
      "estimates, not integrated over — the same posture as P1.2 and MLB's bullpen posteriors.")
    a("")

    if run.notes:
        a("## 8. Run notes")
        a("")
        for n in run.notes:
            a(f"- {n}")
        a("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    log.info("report → %s", path)


def _by_group_projection_corr(run) -> dict:
    """OOS correlation of the emitted projection vs realized standardized production, per group."""
    from quant_sports_intel_models.football.ncaaf.models.freshman_projection import build_target

    tgt = build_target(run._pairs)[["player_id", "arrival_season", "production_z", "has_target"]]
    merged = run.priors.merge(tgt, on=["player_id", "arrival_season"], how="left")
    merged = merged[merged["has_target"].fillna(False)]
    out = {}
    for grp, g in merged.groupby("position_group"):
        if len(g) >= 20 and g["projected_production_z"].std() > 0 and g["production_z"].std() > 0:
            out[grp] = float(np.corrcoef(g["projected_production_z"], g["production_z"])[0, 1])
    if len(merged) >= 20:
        out["ALL"] = float(np.corrcoef(merged["projected_production_z"], merged["production_z"])[0, 1])
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="NCAAF-P1.2b recruit→freshman-production MLE")
    p.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb",
                   help="path to the sports dbt DuckDB (box: /tmp/sports_ncaaf.duckdb)")
    p.add_argument("--schema", default=MARTS_SCHEMA)
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    p.add_argument("--s3", action="store_true", help="also land the priors in the sports lake")
    p.add_argument("--recruit-types", default="HighSchool",
                   help="comma list of recruit types to model (default HighSchool)")
    p.add_argument("--no-report", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    if not Path(args.duckdb).exists():
        p.error(f"DuckDB not found at {args.duckdb} — run the sports dbt build first "
                f"(needs {PAIRS_TABLE}), or point --duckdb at the box's /tmp/sports_ncaaf.duckdb")

    pairs = load_pairs(args.duckdb, args.schema)
    config = FreshmanConfig(recruit_types=tuple(t.strip() for t in args.recruit_types.split(",") if t.strip()))

    log.info("running the P1.2b bake-off (this is the multi-minute part) ...")
    run = run_freshman_projection(pairs, config)
    run._pairs = pairs  # for the OOS correlation diagnostic
    if run.priors.empty:
        log.error("no priors produced — check the pairs mart / recruit types")
        return 1
    log.info("emitted %d recruit priors across %d classes; winner=%s",
             len(run.priors), run.priors["arrival_season"].nunique(), run.bakeoff.winner_name)

    checks = validate(run, config)
    for c in checks:
        log.info("gate ✅ %s", c)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run.priors.to_parquet(out_dir / "ncaaf_freshman_priors.parquet", index=False)
    run.team_priors.to_parquet(out_dir / "ncaaf_team_freshman_prior.parquet", index=False)

    corr = _by_group_projection_corr(run)
    (out_dir / "ncaaf_freshman_projection_summary.json").write_text(json.dumps({
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_priors": int(len(run.priors)),
        "n_team_rows": int(len(run.team_priors)),
        "classes": [int(s) for s in sorted(run.priors["arrival_season"].unique())],
        "winner": run.bakeoff.winner_name,
        "leaderboard": run.bakeoff.leaderboard.to_dict(orient="records"),
        "pbo": None if run.bakeoff.pbo is None else run.bakeoff.pbo.pbo,
        "dsr": None if run.bakeoff.dsr is None else run.bakeoff.dsr.dsr,
        "oracle_floor_ok": run.bakeoff.oracle_floor_ok,
        "by_group_projection_corr": corr,
        "gates_passed": checks,
        "notes": run.notes,
    }, indent=2, default=float))
    log.info("by-group OOS projection↔realized corr: %s", corr)

    if args.s3:
        from quant_sports_intel_models.football.ncaaf.ingest import s3io

        for season, part in run.priors.groupby("arrival_season"):
            s3io.write_dataframe(part.assign(season=int(season)), sport="ncaaf",
                                 source="freshman_priors", season=int(season), tier="derived")
        for season, part in run.team_priors.groupby("season"):
            s3io.write_dataframe(part, sport="ncaaf", source="team_freshman_prior",
                                 season=int(season), tier="derived")
        log.info("landed priors + team aggregate in the sports lake (derived tier)")

    if not args.no_report:
        write_report(run, config, checks, corr, _REPORT_PATH)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
