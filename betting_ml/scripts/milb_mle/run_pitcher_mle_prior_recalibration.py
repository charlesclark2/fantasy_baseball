"""run_pitcher_mle_prior_recalibration.py — MLB Edge-E7.5p CLI: recalibrate the E7.3p PITCHER MLE into a
priceable rookie-STARTER prior + the calibration ablation, and land the per-pitcher prior the served EB
starter build reads.

Reads the E7.3p `mle_projections_pitchers` (per (pitcher, level) MLB-equivalent rate line + the realized
MLB label for graduated pitchers; built SF-FREE by run_milb_mle_pitchers.py --s3), runs the E13.6
recalibration (parameter sd → held-out predictive spread → pseudo-count κ), runs the purged
leave-one-debut-cohort-out calibration ablation vs the incumbent generic prior, and writes:

  * <out>/mle_prior_calibrated_pitchers.parquet     — one row per pitcher (MLBAM), highest level
  * <out>/e7_5p_calibration_summary.json            — per-metric σ_resid / coverage / κ params + ablation
  * ablation_results/e7_5p_pitcher_prior_ablation.md — the AC evidence (rookie-starter calibration)
  * s3://baseball-betting-ml-artifacts/baseball/lakehouse/milb_mle_pitcher_prior/data.parquet (--s3) —
    the W8a precursor view `milb_mle_pitcher_prior` that eb_starter_posteriors (DuckDB branch) reads;
    SINGLE overwrite file (the universal `<name>/**/*.parquet` glob layout — no Delta, no glob-dup).

WIRED: gb_pct (STRONG) + k_pct / bb_pct (weak-but-real, wide recalibrated uncertainty).
NOT WIRED: hr_rate (E7.3p tied-field null) and xwoba_against (no-signal) — they stay on the incumbent
generic experience-band prior. ⚠️ Pitcher K% translates weakly (0.366 vs the batter side's 0.637), so the
expected lift is MODEST and concentrated in GB%. ⚠️ SF-FREE. best_alpha = 0 (a cold-start prior).

  # after run_milb_mle_pitchers.py --s3 has landed the pitcher projections:
  uv run python -m betting_ml.scripts.milb_mle.run_pitcher_mle_prior_recalibration --s3
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.milb_mle.mle_prior_pitcher import (  # noqa: E402
    EVIDENCE_COUNT,
    MIN_MLB_BIP,
    PITCHER_NOT_WIRED,
    PITCHER_PRIOR_METRICS,
    ablate_pitcher,
    build_calibrated_pitcher_prior_table,
    recalibrate_pitcher,
)

log = logging.getLogger("e7_5p.mle_prior_pitcher")

_ABL = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
_DEFAULT_PROJ = _ABL / "e7_3p_artifacts/mle_projections_pitchers.parquet"
_DEFAULT_PAIRS = _ABL / "e7_3p_artifacts/mle_graduated_pairs_pitchers.parquet"
_DEFAULT_OUT = _ABL / "e7_5p_artifacts"
_REPORT_PATH = _ABL / "e7_5p_pitcher_prior_ablation.md"

_S3_BUCKET = "baseball-betting-ml-artifacts"
_S3_KEY = "baseball/lakehouse/milb_mle_pitcher_prior/data.parquet"  # W8a precursor view (single file)

MODEL_VERSION = "milb_mle_pitcher_prior_v1"


def write_report(calib: dict, abl: dict, cov_n: int, n_prospects: int, path: Path) -> None:
    lines: list[str] = []
    a = lines.append
    a("# MLB Edge-E7.5p — PITCHER MiLB MLE → recalibrated rookie-STARTER prior "
      "(wired into `eb_starter_posteriors`)")
    a("")
    a(f"**Model:** `{MODEL_VERSION}` · **generated:** {datetime.now(timezone.utc).isoformat()}")
    a("")
    a("> ⚠️ **This wires a performance-based PRIOR for cold-start starters, not an edge claim.** A "
      "debuting / low-BF rookie starter previously shrank toward a GENERIC experience-band prior; E7.5p "
      "replaces that with the E7.3p MiLB→MLB MLE line for the pitcher metrics that TRANSLATE — **GB% "
      "(strong), K% and BB% (weak-but-real, wide)** — and shrinks the rookie's own MLB line toward it as "
      "batters-faced accrue. **HR-rate and xwOBA-against are NOT wired** (E7.3p: a tied-field null and a "
      "no-signal translation). The E7.3p parameter sd is too tight to price, so E7.5p RECALIBRATES it on "
      "held-out MLB data (E13.6). `best_alpha = 0`.")
    a("")
    a("> 📉 **Expectation-set (recorded up front, per the story):** pitcher K% translates FAR more weakly "
      "than batter K% (E7.3p OOS corr **0.366** vs E7.3's **0.637** — same harness, same CV, so a real "
      "asymmetry: pitcher outcomes are more role/park/defense-confounded). The rookie-STARTER prior's "
      "lift is therefore expected to be **MORE MODEST than the batter version's**, and the biggest single "
      "contribution should come from **GB% (contact management, corr 0.551 / DSR 1.000)** — not K%. "
      "Anything larger than that would be the surprising result, and would deserve suspicion first.")
    a("")
    a("## 1. Recalibration — parameter sd → held-out predictive spread (E13.6)")
    a("")
    a("`σ_resid = std(realized MLB rate − MLE mean)` over graduated pitchers (leakage-safe: each "
      "`mle_<m>` was fit only on strictly-prior debut cohorts). It REPLACES the tighter parameter sd "
      "`mle_<m>_sd`. The pseudo-count κ = m(1−m)/σ_resid² − 1 (clipped) is the prior's weight in the "
      "metric's own EVIDENCE UNITS — batters faced for K%/BB%, balls in play for GB%. Coverage of "
      "±σ_resid / ±1.645σ_resid against the honest ~0.68 / ~0.90 shows the recalibrated sd is calibrated, "
      "not the tight one.")
    a("")
    tbl = pd.DataFrame([{**calib[m].to_dict(), "evidence_unit": EVIDENCE_COUNT[m]} for m in calib])
    a(tbl.to_markdown(index=False))
    a("")
    a("- `tightness_ratio` = σ_resid ÷ median parameter sd (>1 confirms the E7.3p parameter sd was too "
      "tight to price).")
    a("- `true_sd_est` = variance-decomposed between-pitcher prior sd (σ_resid² − label-sampling-var); a "
      "diagnostic only — the SERVED prior sd stays σ_resid (conservative: a marginally weaker prior, so "
      "the rookie's own MLB line takes over a touch faster — the safe direction).")
    a(f"- **Thin-cameo floor (the E7.5 landmine, verbatim):** rows are kept only at `has_mlb_label` "
      f"(`mlb_pa ≥ 150` TBF); GB% additionally requires `mlb_bip ≥ {MIN_MLB_BIP}`. Without the floor "
      f"σ_resid inflates ~1.7–2.2× on all three metrics and the prior would be needlessly weak.")
    a("")
    a("## 2. Calibration ablation — MLE prior vs the incumbent generic prior (purged, "
      "leave-one-cohort-out)")
    a("")
    a("For each debut cohort Y (≥1 strictly-prior cohort): the GENERIC baseline mean = the population "
      "mean of the realized MLB metric over PRIOR cohorts (what the generic experience-band prior "
      "collapses to at BF≈0 — E7.3p's `archetype_prior` benchmark); the MLE mean = the OOS `mle_<m>`. "
      "Each method uses its OWN prior-cohort residual sd (both self-calibrated → the comparison is "
      "calibration × SHARPNESS, not a sd handicap). Scored on the cohort-Y rookie starters. Lower "
      "NLL/CRPS/MAE = better; coverage ≈ 0.68/0.90 = honest.")
    a("")
    a(pd.DataFrame([abl[m].to_dict() for m in abl]).to_markdown(index=False))
    a("")
    for m in abl:
        r = abl[m]
        verdict = ("✅ MLE prior improves rookie-starter calibration" if r.mle_wins
                   else "🟡 MLE prior does NOT beat the generic prior on NLL+CRPS — that metric stays "
                        "honest-null (report it, do not force it)")
        a(f"- **{m}** — {verdict}: NLL {r.mle_nll:.4f} vs {r.generic_nll:.4f}, CRPS {r.mle_crps:.5f} vs "
          f"{r.generic_crps:.5f}, MAE {r.mle_mae:.5f} vs {r.generic_mae:.5f} "
          f"(n={r.n_scored} rookie starters over {r.n_cohorts} cohorts).")
    a("")
    a("## 3. What is wired (and what is not)")
    a("")
    a("- **Served build:** `dbt/models/eb_posteriors/eb_starter_posteriors.sql` (DuckDB branch — the "
      "SF-free lakehouse compute; the Snowflake branch is a thin `select *` over the ext table). A "
      "`milb_mle_pitcher_prior` precursor view (this script's S3 output) is joined on `pitcher_id` "
      "(MLBAM).")
    a("- **COLD-START GATE (this is stricter than the batter sibling, on purpose):** the MLE prior is "
      "applied ONLY to a starter with NO qualifying prior MLB experience (`n_prior_seasons = 0`, i.e. "
      "`age_band = 'u25'` — fewer than 10 career prior starts AND under 150 career prior BF). The E7.3p "
      "map is calibrated on a pitcher's FIRST TWO MLB seasons; applying a 2015 minor-league line to an "
      "established starter would be out-of-distribution. An experienced starter keeps the incumbent "
      "band prior / IL-return blend, unchanged.")
    a("- **κ-BLEND EVERYWHERE, never Normal-Normal (the E7.5 ISO lesson, applied pre-emptively):** all "
      "three wired metrics are bounded rates, so the MLE update is the pseudo-count blend "
      "`(m·κ + obs·n)/(κ + n)` — K%/BB% with n = current-season BF (the existing accrual), GB% with "
      "n = prior-season balls in play. A Normal-Normal update with a measurement-variance floor lets a "
      "tiny-sample extreme observation overwhelm the prior; a variance floor cannot save it.")
    a("- **`eb_gb_pct` is a NEW served column.** The starter EB table carried no ground-ball metric at "
      "all, so GB% — the STRONGEST pitcher translation — had nowhere to land. It is populated for EVERY "
      "starter (MLE prior for cold-start pitchers, prior-season league GB% mean otherwise), shrunk "
      "toward the pitcher's own prior-season GB% weighted by balls in play. **It has no downstream "
      "consumer yet** — wiring it into `feature_pregame_starter_features` means retraining the models "
      "that read that feature block (the E7.9 train/serve-consistency class), which is a separate story. "
      "K% and BB% flow to serving IMMEDIATELY through the existing "
      "`starter_eb_k_pct` / `starter_eb_bb_pct` features.")
    a("- **`eb_xwoba_against` is UNTOUCHED** — E7.3p graded that translation no-signal, so the "
      "experience-band prior stays (E7.3's wOBA precedent).")
    a("- **Leakage-safe:** only pre-debut minor-league stats enter the MLE (the E7.3p as-of guard); the "
      "observed GB% component joins on `game_year = season − 1` (the repo's batted-ball leakage "
      "doctrine); the prior table is static, read as a W8a precursor view.")
    a("- **Fail-safe:** the precursor view degrades to an EMPTY typed view when the parquet is absent → "
      "every MLE column reads NULL → the generic prior is used everywhere (exactly pre-E7.5p behaviour). "
      "A missing artifact can NEVER HALT the serving-critical W8a build.")
    a("")
    a("## 4. Limitations")
    a("")
    a("- **Pitcher translations are weaker than batter translations** — see the expectation-set note "
      "above. GB% is the only STRONG feeder; K%/BB% are weak-but-real and carry a WIDE recalibrated "
      "σ_resid, which is exactly why the κ they imply is small enough for a rookie's own line to take "
      "over quickly.")
    a("- **`gb_pct` is a CROSS-DEFINITION map** (inherited from E7.3p): the MiLB feature is the "
      "ground-OUT share GO/(GO+AO); the MLB label — and the served observed component — is Statcast "
      "GB/BIP. The regression learned the rescale; both served sides use the Statcast definition.")
    a("- **The observed GB% component is PRIOR-SEASON, not season-to-date.** `mart_pitcher_batted_ball_"
      "profile` is season-grain, so a within-season as-of GB% would require a pitch-level re-aggregation; "
      "joining on `season − 1` is the leakage-safe doctrine used by every other batted-ball consumer "
      "here. Consequence: a veteran's `eb_gb_pct` does not move during the season.")
    a("- **σ_resid carries finite-sample label noise** → the prior is marginally weaker than truth (safe).")
    a("- **Graduated pitchers are self-selected** (they reached the TBF floor) — the calibration is on "
      "pitchers who established, which is the served population. Stated, not corrected (from E7.3p).")
    a(f"- **Coverage:** {cov_n} pitchers carry a calibrated prior ({n_prospects} of them prospects with "
      f"no MLB debut yet — the population the cold-start gate actually serves).")
    a("- **Not wired, with reasons:**")
    for m, why in PITCHER_NOT_WIRED.items():
        a(f"  - `{m}` — {why}")
    a("- **best_alpha = 0** — a cold-start betting prior, never a market bet.")
    a("")
    a("## 5. Train/serve consistency (the E7.9 class) — read before promoting")
    a("")
    a("The served models that consume `starter_eb_k_pct` / `starter_eb_bb_pct` (via "
      "`feature_pregame_starter_features` → `feature_pregame_game_features_raw`) were **TRAINED on the "
      "OLD generic-prior values**. E7.5p changes those two features for exactly one slice of rows — "
      "COLD-START starters — so a model sees a feature drawn from a slightly different distribution "
      "than it was fit on. Three things bound the exposure, and one follow-up closes it:")
    a("")
    a("1. **Bounded slice.** Only `n_prior_seasons = 0` starters move at all; every experienced "
      "starter's row is byte-identical (pinned by a test). Cold-start starters are a small share of "
      "any slate.")
    a("2. **Bounded magnitude.** The change is a PRIOR swap, not a scale change: both the old band "
      "prior and the new MLE mean live in the same range, and the κ-blend converges to the pitcher's "
      "own line as BF accrue — the divergence is largest at BF≈0 and decays from there.")
    a("3. **Direction is toward truth.** §2 is the evidence that the new value is BETTER calibrated for "
      "exactly those rows; a stale model reading a better-calibrated input is a smaller error than the "
      "same model reading a worse one, though it is not zero.")
    a("")
    a("**The close-out is a RETRAIN of the starter-consuming models after this lands and a few weeks of "
      "cold-start rows have accrued** — the same posture E7.5 took on the batter side. Until then the "
      "honest framing is: improved cold-start CALIBRATION in the EB layer, with the downstream models "
      "still carrying their old fit. **This is also why `eb_gb_pct` is deliberately NOT joined into "
      "`feature_pregame_starter_features` yet** — adding a brand-new feature to a trained model's input "
      "block is the strong form of the same problem, and belongs with the retrain.")
    a("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    log.info("report → %s", path)


def _upload_s3(local_parquet: Path) -> None:
    """Upload the single calibrated-prior parquet to the W8a precursor-view key (instance-role-safe: the
    shared make_s3_client() resolves the botocore chain — never pass possibly-None env keys, per
    CLAUDE.md's boto3 landmine)."""
    from scripts.utils.lakehouse_raw_writer import make_s3_client

    client = make_s3_client()
    client.upload_file(str(local_parquet), _S3_BUCKET, _S3_KEY)
    log.info("landed calibrated pitcher prior → s3://%s/%s", _S3_BUCKET, _S3_KEY)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="E7.5p — recalibrate the PITCHER MiLB MLE into a served rookie-starter prior")
    p.add_argument("--projections", default=str(_DEFAULT_PROJ),
                   help="the E7.3p mle_projections_pitchers parquet (run_milb_mle_pitchers.py output)")
    p.add_argument("--pairs", default=str(_DEFAULT_PAIRS),
                   help="the E7.3p mle_graduated_pairs_pitchers parquet — supplies mlb_pa (TBF), mlb_bip "
                        "and has_mlb_label (the mlb_pa≥150 floor) so σ_resid excludes thin cameos")
    p.add_argument("--metrics", nargs="+", default=list(PITCHER_PRIOR_METRICS),
                   help=f"which translated metrics to wire (default {PITCHER_PRIOR_METRICS}; "
                        f"hr_rate/xwoba_against are never wired)")
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    p.add_argument("--s3", action="store_true",
                   help="upload the calibrated prior to the milb_mle_pitcher_prior W8a precursor key")
    p.add_argument("--no-report", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    bad = [m for m in args.metrics if m in PITCHER_NOT_WIRED]
    if bad:
        p.error(f"refusing to wire {bad} — E7.3p graded them no-signal: "
                + "; ".join(f"{m}: {PITCHER_NOT_WIRED[m]}" for m in bad))

    proj_path = Path(args.projections)
    if not proj_path.exists():
        p.error(f"projections parquet not found at {proj_path} — run run_milb_mle_pitchers.py --s3 first")
    proj = pd.read_parquet(proj_path)
    proj["player_id"] = proj["player_id"].astype(str)
    log.info("loaded %d (pitcher, level) MLE projection rows", len(proj))

    # Attach the E7.3p label floor (mlb_pa≥150 TBF) + mlb_bip so recalibration/ablation exclude thin MLB
    # cameos (the E7.5 landmine: a handful of TBF makes a realized rate ~pure noise and blows up σ_resid).
    pairs_path = Path(args.pairs)
    if pairs_path.exists():
        pairs = pd.read_parquet(pairs_path)
        pairs["player_id"] = pairs["player_id"].astype(str)
        keep = ["player_id", "level", "mlb_pa", "mlb_bip", "has_mlb_label"]
        proj = proj.merge(pairs[[c for c in keep if c in pairs]], on=["player_id", "level"], how="left")
        log.info("merged label floor from pairs: %d labelled (has_mlb_label) rows",
                 int(proj.get("has_mlb_label", pd.Series(dtype=bool)).fillna(False).sum()))
    else:
        log.warning("pairs parquet not found at %s — recalibrating WITHOUT the mlb_pa/mlb_bip label "
                    "floor (σ_resid WILL be inflated by thin-sample cameos)", pairs_path)

    metrics = tuple(args.metrics)
    calib = recalibrate_pitcher(proj, metrics)
    for m, c in calib.items():
        log.info("recalibrated %-6s: σ_resid=%.4f (param_sd≈%.4f, ×%.1f) cov68=%.2f cov90=%.2f n=%d "
                 "[evidence=%s]", m, c.resid_sd, c.param_sd_median,
                 c.resid_sd / c.param_sd_median if c.param_sd_median else 0,
                 c.coverage_68, c.coverage_90, c.n, EVIDENCE_COUNT.get(m, "bf"))

    abl = ablate_pitcher(proj, metrics)
    for m, r in abl.items():
        log.info("ablation  %-6s: MLE nll=%.4f vs generic %.4f | MLE mae=%.4f vs %.4f | wins=%s",
                 m, r.mle_nll, r.generic_nll, r.mle_mae, r.generic_mae, r.mle_wins)

    table = build_calibrated_pitcher_prior_table(proj, calib)
    n_prospects = int(table["is_prospect"].sum()) if "is_prospect" in table else 0
    log.info("built calibrated prior for %d pitchers (highest level; %d prospects)",
             len(table), n_prospects)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    local_parquet = out_dir / "mle_prior_calibrated_pitchers.parquet"
    table.to_parquet(local_parquet, index=False)

    (out_dir / "e7_5p_calibration_summary.json").write_text(json.dumps({
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": list(metrics),
        "not_wired": PITCHER_NOT_WIRED,
        "evidence_units": {m: EVIDENCE_COUNT[m] for m in metrics},
        "n_pitchers": int(len(table)),
        "n_prospects": n_prospects,
        "recalibration": {m: calib[m].to_dict() for m in calib},
        "ablation": {m: abl[m].to_dict() for m in abl},
    }, indent=2, default=float))

    if not args.no_report:
        write_report(calib, abl, len(table), n_prospects, _REPORT_PATH)

    if args.s3:
        _upload_s3(local_parquet)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
