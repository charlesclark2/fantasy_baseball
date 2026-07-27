"""run_milb_mle_pitchers.py — MLB Edge-E7.3p CLI: fit the PITCHER MiLB→MLB translation MLEs.

The pitcher sibling of run_milb_mle.py (E7.3 — harness reused, not forked). Reads the
`mle_graduated_pairs_pitchers` parquet (built by build_graduated_pairs_pitchers.py), runs the §0.5
bake-off for each pitcher rate metric (K%, BB%, HR-rate, GB%, xwOBA-against), emits a leakage-safe
per-(pitcher, level) MLB-equivalent line + PARAMETER uncertainty, validates the leakage /
plausibility / oracle-floor / null-beat gates, and writes a markdown report with per-metric verdicts.

⚠️ OPERATOR-RUN (>1 min). Leave-one-MLB-debut-cohort-out CV × ~8 configs × 5 metrics, each
partial-pool fit an EB variance-component search + each GBM three quantile fits.

  # 1. assemble the pairs ONCE (SF-free DuckDB/S3; see build_graduated_pairs_pitchers.py)
  uv run python -m betting_ml.scripts.milb_mle.build_graduated_pairs_pitchers --season-floor 2015 --s3
  # 2. the bake-off + emission (reads the cached parquet)
  uv run python -m betting_ml.scripts.milb_mle.run_milb_mle_pitchers \
      --pairs quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3p_artifacts/mle_graduated_pairs_pitchers.parquet \
      --s3

Outputs:
  * <out>/mle_projections_pitchers.parquet — wide per-(pitcher, level) MLB-equivalent line
    (the E8.0 board's pitcher column + the future starter-EB rookie-prior feeder)
  * <out>/milb_mle_pitchers_summary.json — per-metric gates + leaderboards + PBO/DSR
  * s3://baseball-betting-ml-artifacts/baseball/milb/derived/mle_projections_pitchers/ (--s3)
  * quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3p_milb_mle_pitchers.md
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

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.milb_mle.milb_mle import (  # noqa: E402
    MAX_PLAUSIBLE_SD,
    PITCHER_AUX_COLS,
    PITCHER_METRICS,
    PITCHER_MODEL_VERSION,
    PLAUSIBLE_RANGE,
    MleConfig,
    MleRun,
    build_target,
    clone_projector,
    emit_projections,
    run_bakeoff,
)

log = logging.getLogger("e7_3p.mle")

_DEFAULT_OUT = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3p_artifacts"
_REPORT_PATH = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3p_milb_mle_pitchers.md"
_KEYS = ["player_id", "level"]
_S3_DEST = "s3://baseball-betting-ml-artifacts/baseball/milb/derived/mle_projections_pitchers"


def _cfg(metric: str, use_statcast: bool = True) -> MleConfig:
    return MleConfig(metric=metric, use_statcast=use_statcast, aux_cols=PITCHER_AUX_COLS,
                     player_type="pitcher", model_version=PITCHER_MODEL_VERSION)


def join_coverage(pairs: pd.DataFrame) -> dict:
    """How much of the MiLB pitcher substrate bridges to a realized MLB line — the P1.2b dead-bridge
    check (a documented `player_id == pitcher_id` join can be silently dead)."""
    data = build_target(pairs, _cfg("k_pct"))
    n = len(data)
    return {
        "n_rows_player_level": int(n),
        "n_players": int(data["player_id"].nunique()),
        "n_with_minor_line": int(data["has_minor_line"].sum()),
        "n_graduated_labelled": int(data["has_target"].sum()),
        "n_prospects": int(data["is_prospect"].sum()),
        "pct_graduated": round(100.0 * data["has_target"].mean(), 1) if n else 0.0,
        "n_with_statcast": int(data["sc_xwoba_against"].notna().sum()) if "sc_xwoba_against" in data else 0,
        "n_with_gb_label": int(pd.to_numeric(data.get("mlb_gb_pct"), errors="coerce").notna().sum()),
        "levels": data.loc[data["has_target"], "level"].value_counts().to_dict(),
    }


def _validate_metric(metric: str, run, cov: dict) -> tuple[list[str], list[str]]:
    """Per-metric HALT-tier gates (raise) + soft notes. Returns (passed, notes)."""
    proj, bake = run.projections, run.bakeoff
    passed: list[str] = []
    notes: list[str] = []
    mcol, scol = f"mle_{metric}", f"mle_{metric}_sd"
    lo, hi = PLAUSIBLE_RANGE[metric]

    # 1. grain unique (one row per pitcher×level)
    if proj.duplicated(subset=_KEYS).any():
        raise AssertionError(f"[{metric}] duplicate (player_id, level) projection rows")
    passed.append("per-(pitcher, level) grain is unique")

    # 2. seed cohort never emitted + every emission fit on a strictly-prior window
    if (proj["n_prior_cohorts"] < 1).any():
        raise AssertionError(f"[{metric}] a projection was emitted with zero strictly-prior cohorts")
    passed.append("every emission fit on strictly-prior debut cohorts (n_prior ≥ 1) — seed not emitted")

    # 3. finite + physically plausible
    for c in (mcol, scol):
        if not np.isfinite(proj[c]).all():
            raise AssertionError(f"[{metric}] {c} has non-finite values")
    if (proj[scol] <= 0).any():
        raise AssertionError(f"[{metric}] {scol} must be strictly positive")
    if proj[mcol].min() < lo - 1e-9 or proj[mcol].max() > hi + 1e-9:
        raise AssertionError(
            f"[{metric}] mle_{metric} out of the plausible range [{lo}, {hi}] "
            f"(min {proj[mcol].min():.4f}, max {proj[mcol].max():.4f})")
    if proj[scol].max() > MAX_PLAUSIBLE_SD[metric]:
        raise AssertionError(
            f"[{metric}] {scol} reaches {proj[scol].max():.4f} > {MAX_PLAUSIBLE_SD[metric]} — a "
            f"coefficient is unidentified (P1.2's leak, one rung down)")
    passed.append(f"projection finite + plausible (range [{proj[mcol].min():.3f}, {proj[mcol].max():.3f}], "
                  f"sd≤{proj[scol].max():.3f})")

    # 4. oracle-floor (metric not inverted)
    if not bake.oracle_floor_ok:
        raise AssertionError(f"[{metric}] ORACLE-FLOOR VIOLATION — a candidate scored MAE < 0")
    passed.append("oracle-floor holds (no candidate beats a target-seeing oracle → metric not inverted)")

    # 5. does the minor line beat the null FLOOR + the reference benchmarks? (reported, not raised)
    lb = bake.leaderboard
    null_mae = float(lb.loc[lb["config"] == "level_mean", "oos_mae"].iloc[0])
    sel = lb[lb["selectable"]]
    win_mae = float(sel["oos_mae"].min())
    if win_mae >= null_mae:
        notes.append(f"⚠️ [{metric}] NO SIGNAL: winner OOS MAE {win_mae:.4f} ≥ level-mean null "
                     f"{null_mae:.4f} — the minor line adds nothing beyond level. Emitting anyway "
                     f"(degrades to the level mean), flagged for the starter-EB wiring story.")
        passed.append(f"⚠️ winner does NOT beat the null (MAE {win_mae:.4f} ≥ {null_mae:.4f}) — honest no-signal")
    else:
        passed.append(f"winner beats the level-mean null OOS (MAE {win_mae:.4f} < {null_mae:.4f})")
    for ref, tag in (("identity_no_translation", "raw minor line as-is"),
                     ("archetype_prior", "generic population prior")):
        r = lb[lb["config"] == ref]
        if not r.empty:
            rm = float(r["oos_mae"].iloc[0])
            passed.append(f"vs {tag}: MLE winner {'beats' if win_mae < rm else 'does NOT beat'} it "
                          f"(MAE {win_mae:.4f} vs {rm:.4f})")

    # 6. deflation gates — reported honestly (E2.1-r: a tied field's high PBO is the null; a
    #    robust-but-weak DSR<0.95 is a valid feeder here)
    if bake.pbo is not None:
        passed.append(f"PBO = {bake.pbo.pbo:.3f} over {bake.pbo.n_configs} configs "
                      f"({'<0.2 ✅' if bake.pbo.pbo < 0.2 else 'see report — tie vs overfit'})")
    if bake.dsr is not None:
        passed.append(f"DSR = {bake.dsr.dsr:.3f} (n_trials={bake.dsr.n_trials}) — "
                      f"{'≥0.95' if bake.dsr.dsr >= 0.95 else 'robust-but-weak, honest feeder (OK)'}")
    return passed, notes


def _oos_corr(pairs: pd.DataFrame, run, metric: str) -> float | None:
    """OOS correlation of the emitted MLB-equivalent line vs the realized MLB metric (graduated
    pitchers only — each was fit on strictly-prior cohorts)."""
    tgt = build_target(pairs, _cfg(metric))[_KEYS + ["target", "has_target"]]
    m = run.projections.merge(tgt, on=_KEYS, how="left")
    m = m[m["has_target"].fillna(False)]
    col = f"mle_{metric}"
    if len(m) >= 20 and m[col].std() > 0 and m["target"].std() > 0:
        return float(np.corrcoef(m[col], m["target"])[0, 1])
    return None


def write_report(runs: dict, cov: dict, checks: dict, corrs: dict, skipped: dict, path: Path) -> None:
    lines: list[str] = []
    a = lines.append
    a("# MLB Edge-E7.3p — PITCHER MiLB → MLB translation factors (MLEs)")
    a("")
    a(f"**Model:** `{PITCHER_MODEL_VERSION}` · **generated:** {datetime.now(timezone.utc).isoformat()}")
    a("")
    a("> ⚠️ **This is an MLB-equivalent PRIOR/projection, not an edge claim.** It translates a "
      "pitcher's pre-debut MiLB rate line (+ AAA Statcast stuff/velo/spin where present) into a "
      "projected MLB rate line, measured against realized early-career MLB production — never a "
      "market. `best_alpha = 0` holds. The uncertainty is **PARAMETER** uncertainty (a RELATIVE "
      "confidence signal), NOT a calibrated predictive interval — **the starter-EB wiring story "
      "(the E7.5 sibling) MUST recalibrate on held-out data before pricing** (the E13.6 pattern). "
      "A ROBUST-BUT-WEAK result (low PBO, DSR possibly <0.95) is a VALID, VALUABLE feeder — "
      "reported honestly, not forced (P1.2b DSR-0.821; E7.3's wOBA null).")
    a("")
    a("## 1. Join coverage (the P1.2b dead-bridge check)")
    a("")
    a("Does the MiLB `player_id` actually bridge to a realized MLB `pitcher_id` line? The map trains "
      "only on graduated pitchers carrying BOTH a thick pre-debut minor line AND a realized MLB "
      "label; a silently-thin bridge under-trains it.")
    a("")
    a(pd.DataFrame([{k: v for k, v in cov.items() if k != "levels"}]).T.rename(columns={0: "value"}).to_markdown())
    a("")
    a(f"Labelled graduates by level: `{cov.get('levels')}`")
    a("")

    # ── Headline read — classify each metric so the per-metric verdict is explicit, not inferred.
    a("## 1b. Headline read — which pitcher skills translate")
    a("")
    a("Each metric is its own translation; the honest finding is that they DIFFER (E7.3's batter "
      "result: discipline translated, the run-value composite did not — the pitcher priors are "
      "K%/BB%/stuff strong, ERA/BABIP-adjacent noisy). A metric is a **strong** feeder when its "
      "winner beats BOTH the level-mean null AND the generic archetype prior out-of-sample AND "
      "clears DSR≥0.95; **weak-but-real** when it beats both but DSR<0.95 (a valid feeder, P1.2b "
      "precedent); **no-signal** when the winner does not beat the null / archetype (the minor line "
      "adds nothing beyond level → the emission degrades to the population prior).")
    a("")
    rows = []
    for metric in runs:
        lb = runs[metric].bakeoff.leaderboard
        null_mae = float(lb.loc[lb["config"] == "level_mean", "oos_mae"].iloc[0])
        arch = lb[lb["config"] == "archetype_prior"]
        arch_mae = float(arch["oos_mae"].iloc[0]) if not arch.empty else float("nan")
        win_mae = float(lb[lb["selectable"]]["oos_mae"].min())
        dsr = None if runs[metric].bakeoff.dsr is None else runs[metric].bakeoff.dsr.dsr
        beats = win_mae < null_mae - 1e-9 and win_mae < arch_mae - 1e-9
        if not beats:
            verdict = "❌ no-signal (degrades to the population prior)"
        elif dsr is not None and dsr >= 0.95:
            verdict = "✅ STRONG feeder"
        else:
            verdict = "🟡 weak-but-real"
        rows.append({"metric": metric, "winner": runs[metric].bakeoff.winner_name,
                     "oos_corr": corrs.get(metric), "dsr": dsr, "verdict": verdict})
    for metric, why in skipped.items():
        rows.append({"metric": metric, "winner": "—", "oos_corr": None, "dsr": None,
                     "verdict": f"⏭️ SKIPPED (data-thin): {why}"})
    a(pd.DataFrame(rows).to_markdown(index=False, floatfmt=".3f"))
    a("")

    for metric in runs:
        run = runs[metric]
        bake = run.bakeoff
        a(f"## 2.{metric} — bake-off: `{metric}`  (winner: `{bake.winner_name}`)")
        a("")
        a("Leave-one-MLB-debut-cohort-out expanding-window CV; metric = MAE on the raw realized MLB "
          f"`{metric}` (lower = better). `level_mean` is the NULL FLOOR; `identity_no_translation` "
          "(raw minor line) and `archetype_prior` (generic population prior) are REPORTED benchmarks "
          "(`selectable = False`).")
        a("")
        a(bake.leaderboard.to_markdown(index=False, floatfmt=".4f"))
        a("")
        for c in checks[metric]:
            a(f"- ✅ {c}")
        rho = corrs.get(metric)
        if rho is not None:
            a(f"- 📈 OOS projection↔realized `{metric}` correlation (graduated pitchers): **{rho:.3f}**")
        a("")

    a("## 3. The documented path to the starter-EB rookie prior (the betting payoff)")
    a("")
    a("The betting consumer is `eb_starter_posteriors` (dbt, `dbt/models/eb_posteriors/`) — a "
      "debuting rookie starter today gets a generic prior, the exact cold-start E7.5 fixed for "
      "batters. The wiring story (the E7.5 pitcher sibling — NOT this story) should mirror E7.5 "
      "1:1:")
    a("")
    a("1. **Recalibrate first (E13.6):** run the `mle_prior.py` pattern against these projections — "
      "parameter sd → held-out σ_resid per metric on the graduated-pitcher holdout (merge "
      "`has_mlb_label`/`mlb_pa` from `mle_graduated_pairs_pitchers.parquet` and filter to the "
      "HIGHEST level per pitcher — the E7.5 thin-cameo landmine applies verbatim: 1-TBF cameos "
      "inflate σ 2–3×).")
    a("2. **Wire ONLY the metrics this report grades strong / weak-but-real** (weak ones with wide "
      "uncertainty); a no-signal metric stays on the incumbent generic prior (E7.3's wOBA "
      "precedent).")
    a("3. **Land a single-overwrite parquet** (`baseball/lakehouse/milb_mle_pitcher_prior/`) + a "
      "FAIL-SAFE empty-view registration in `run_w1_lakehouse.py` (the `_register_mle_prior_view` "
      "pattern — serving must never HALT on a missing prior).")
    a("4. **Bounded-rate updates use pseudo-count (Beta κ) blends, never Normal-Normal** — the E7.5 "
      "ISO blow-up lesson; K%/BB%/HR-rate/GB% are all bounded rates, so κ-blends throughout.")
    a("5. **Serving-check on a real slate** before calling it live (the E7.5 discipline).")
    a("")
    a("## 4. Limitations")
    a("")
    a("- **Uncertainty is PARAMETER uncertainty, not a calibrated predictive interval** — ranks "
      "confidence correctly, too tight to price. The wiring story MUST recalibrate (E13.6).")
    a("- **Per-(pitcher, level) rows share the pitcher's MLB label** — a correlated-observation "
      "limit; it is what lets the model estimate LEVEL factors. The deflation (PBO/DSR) + "
      "partial-pool shrinkage guard against thin level×league cells.")
    a("- **Graduated pitchers are a SELF-SELECTED population** (they reached the MLB TBF floor) — "
      "the map is calibrated on pitchers who established, which is the population the prior is used "
      "for. Survivorship is stated, not corrected.")
    a("- **Role mix (starter vs reliever) shifts across the translation** — `minor_start_share` is a "
      "GBM-only impute-flagged feature, not a hierarchy level; an AAA reliever's K% translating "
      "differently from a starter's is learned, not structurally modeled.")
    a("- **`gb_pct` is a CROSS-DEFINITION map** — the MiLB feature is the ground-OUT share "
      "GO/(GO+AO) (all the box line offers); the MLB label is Statcast GB/BIP. The regression "
      "learns the rescale; the verdict says whether the proxy carries.")
    a("- **`xwoba_against`'s minor feature exists ONLY for AAA 2022+ rows** (the E7.2 coverage) — "
      "few debut cohorts, so its bake-off may be data-thin or skipped; honest-null, never forced.")
    a("- **The AAA-Statcast add is coverage-conditioned** (AAA-only, 2022+) — only the GBM reads it, "
      "impute-flagged; a pitcher/season without it is honest-null, never fabricated.")
    a("- **Realized MLB label is Statcast-era-bounded** (`mart_pitcher_rolling_stats` is 2015+) — "
      "`--season-floor 2015` keeps the minor lines in the same era as the labels.")
    a("- **Empirical-Bayes plug-in** (partial-pool): variance components are point estimates, not "
      "integrated over — the same posture as P1.2 / the bullpen posteriors.")
    a("- **best_alpha = 0** — a board projection + a betting prior, not a market bet.")
    a("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    log.info("report → %s", path)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.3p — PITCHER MiLB→MLB translation MLEs")
    p.add_argument("--pairs", default=str(_DEFAULT_OUT / "mle_graduated_pairs_pitchers.parquet"),
                   help="the graduated-pairs parquet from build_graduated_pairs_pitchers.py")
    p.add_argument("--metrics", nargs="+", default=list(PITCHER_METRICS),
                   help=f"which rate metrics to translate (default all: {PITCHER_METRICS})")
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    p.add_argument("--no-statcast", action="store_true",
                   help="disable the AAA-Statcast / start-share GBM add")
    p.add_argument("--s3", action="store_true",
                   help="land the wide projections at baseball/milb/derived/mle_projections_pitchers (Delta)")
    p.add_argument("--no-report", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    if not Path(args.pairs).exists():
        p.error(f"pairs parquet not found at {args.pairs} — run build_graduated_pairs_pitchers.py first")
    pairs = pd.read_parquet(args.pairs)
    log.info("loaded %d (pitcher, level) pairs", len(pairs))
    cov = join_coverage(pairs)
    log.info("join coverage: %s", {k: v for k, v in cov.items() if k != "levels"})

    runs, checks, corrs, all_notes = {}, {}, {}, []
    skipped: dict[str, str] = {}
    wide = None
    for metric in args.metrics:
        cfg = _cfg(metric, use_statcast=not args.no_statcast)
        log.info("running the E7.3p bake-off for metric=%s (the multi-minute part) ...", metric)
        try:
            bake = run_bakeoff(pairs, cfg)
        except ValueError as e:
            # xwoba_against's AAA-2022+-only feature can leave <2 evaluable debut cohorts — an
            # HONEST data-thin skip (reported), never a forced fit and never a sweep-killer.
            skipped[metric] = str(e)
            log.warning("metric %s SKIPPED (data-thin): %s", metric, e)
            continue
        proj = emit_projections(pairs, lambda: clone_projector(bake.winner_config), cfg)
        run = MleRun(metric=metric, projections=proj, bakeoff=bake, notes=list(bake.notes))
        runs[metric] = run
        passed, notes = _validate_metric(metric, run, cov)
        checks[metric] = passed
        all_notes += notes
        corrs[metric] = _oos_corr(pairs, run, metric)
        for c in passed:
            log.info("gate ✅ [%s] %s", metric, c)
        # merge into the wide per-(pitcher, level) frame
        keep = _KEYS + ["player_name", "league", "debut_cohort", "is_prospect", "age", "minor_pa",
                        f"minor_{metric}", f"mlb_{metric}", f"mle_{metric}",
                        f"mle_{metric}_sd", "n_prior_cohorts", "model_version"]
        part = proj[[c for c in keep if c in proj.columns]]
        if wide is None:
            wide = part
        else:
            newcols = _KEYS + [f"minor_{metric}", f"mlb_{metric}", f"mle_{metric}", f"mle_{metric}_sd"]
            wide = wide.merge(part[[c for c in newcols if c in part.columns]], on=_KEYS, how="outer")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if wide is not None:
        wide["sport"] = "mlb"
        wide["player_type"] = "pitcher"
        wide.to_parquet(out_dir / "mle_projections_pitchers.parquet", index=False)
        log.info("wrote %d wide (pitcher, level) projections", len(wide))

    (out_dir / "milb_mle_pitchers_summary.json").write_text(json.dumps({
        "model_version": PITCHER_MODEL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": args.metrics,
        "skipped": skipped,
        "join_coverage": {k: v for k, v in cov.items() if k != "levels"},
        "per_metric": {m: {
            "winner": runs[m].bakeoff.winner_name,
            "leaderboard": runs[m].bakeoff.leaderboard.to_dict(orient="records"),
            "pbo": None if runs[m].bakeoff.pbo is None else runs[m].bakeoff.pbo.pbo,
            "dsr": None if runs[m].bakeoff.dsr is None else runs[m].bakeoff.dsr.dsr,
            "oracle_floor_ok": runs[m].bakeoff.oracle_floor_ok,
            "oos_corr": corrs[m],
            "gates_passed": checks[m],
        } for m in runs},
        "notes": all_notes,
    }, indent=2, default=float))

    if args.s3 and wide is not None:
        from scripts.utils.delta_lake import storage_options
        from deltalake import write_deltalake
        write_deltalake(_S3_DEST, wide, mode="overwrite", storage_options=storage_options())
        log.info("landed wide projections at %s", _S3_DEST)

    if not args.no_report:
        write_report(runs, cov, checks, corrs, skipped, _REPORT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
