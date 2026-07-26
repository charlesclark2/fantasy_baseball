"""run_mle_prior_recalibration.py — MLB Edge-E7.5 CLI: recalibrate the E7.3 MLE into a priceable rookie
prior + the calibration ablation, and land the per-player calibrated prior the served EB build reads.

Reads the E7.3 `mle_projections` (per (player, level) MLB-equivalent line + realized MLB label for
graduated players; built SF-FREE by run_milb_mle.py --s3), runs the E13.6 recalibration (parameter sd →
held-out predictive spread → Beta pseudo-count / Normal prior sd), runs the purged leave-one-cohort-out
calibration ablation vs the incumbent generic prior, and writes:

  * <out>/mle_prior_calibrated.parquet          — one row per batter (MLBAM), highest level: the served prior
  * <out>/e7_5_calibration_summary.json         — per-metric σ_resid / coverage / κ params + ablation
  * ablation_results/e7_5_milb_prior_ablation.md — the AC evidence (rookie calibration vs generic prior)
  * s3://baseball-betting-ml-artifacts/baseball/lakehouse/milb_mle_prior/data.parquet (--s3) — the W8a
    precursor view `milb_mle_prior` that eb_batter_posteriors_raw (DuckDB branch) reads; SINGLE overwrite
    file (the universal `<name>/**/*.parquet` glob layout — no Delta, no glob-dup).

⚠️ SF-FREE. No Snowflake read/write — the projections are S3/lakehouse, the output is an S3 precursor
parquet. best_alpha = 0 (a rookie prior, never a market bet).

  # after run_milb_mle.py --s3 has landed the projections:
  uv run python -m betting_ml.scripts.milb_mle.run_mle_prior_recalibration \
      --projections quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3_artifacts/mle_projections.parquet \
      --s3
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

from betting_ml.scripts.milb_mle.mle_prior import (  # noqa: E402
    PRIOR_METRICS,
    ablate,
    build_calibrated_prior_table,
    recalibrate,
)

log = logging.getLogger("e7_5.mle_prior")

_DEFAULT_PROJ = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3_artifacts/mle_projections.parquet"
_DEFAULT_PAIRS = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3_artifacts/mle_graduated_pairs.parquet"
_DEFAULT_OUT = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_5_artifacts"
_REPORT_PATH = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_5_milb_prior_ablation.md"

_S3_BUCKET = "baseball-betting-ml-artifacts"
_S3_KEY = "baseball/lakehouse/milb_mle_prior/data.parquet"   # W8a precursor-view glob layout (single file)

MODEL_VERSION = "milb_mle_prior_v1"


def write_report(calib: dict, abl: dict, cov_n: int, path: Path) -> None:
    lines: list[str] = []
    a = lines.append
    a("# MLB Edge-E7.5 — MiLB MLE → recalibrated rookie prior (wired into `eb_batter_posteriors_raw`)")
    a("")
    a(f"**Model:** `{MODEL_VERSION}` · **generated:** {datetime.now(timezone.utc).isoformat()}")
    a("")
    a("> ⚠️ **This wires a performance-based PRIOR for low-MLB-PA rookies, not an edge claim.** For a "
      "called-up batter with ~0 MLB PAs the served build previously shrank toward a GENERIC archetype/slot "
      "prior; E7.5 replaces that with the E7.3 MiLB→MLB MLE line for the metrics that TRANSLATE — **K%, "
      "BB%, and ISO (wide)** — and shrinks the rookie's own MLB line toward it as PAs accrue. **wOBA is "
      "NOT wired** (E7.3: no translatable signal beyond level). The E7.3 parameter sd is too tight to "
      "price, so E7.5 RECALIBRATES it on held-out MLB data (E13.6): the prior sd is the held-out "
      "predictive spread of the MLE mean around realized early-career MLB production. `best_alpha = 0`.")
    a("")
    a("## 1. Recalibration — parameter sd → held-out predictive spread (E13.6)")
    a("")
    a("`σ_resid = std(realized MLB rate − MLE mean)` over graduated players (leakage-safe: each `mle_<m>` "
      "was fit only on strictly-prior debut cohorts). It REPLACES the tighter parameter sd `mle_<m>_sd`. "
      "The Beta pseudo-count κ = m(1−m)/σ_resid² − 1 (clipped) is the equivalent MLB-PA weight of the "
      "prior; ISO uses σ_resid as the Normal prior sd directly. Coverage of ±σ_resid / ±1.645σ_resid "
      "against the honest ~0.68 / ~0.90 shows the recalibrated sd is calibrated, not the tight one.")
    a("")
    a(pd.DataFrame([calib[m].to_dict() for m in calib]).to_markdown(index=False))
    a("")
    a("- `tightness_ratio` = σ_resid ÷ median parameter sd — how much wider the honest predictive sd is "
      "than the E7.3 parameter sd (>1 confirms the parameter sd was too tight to price).")
    a("- `true_sd_est` = variance-decomposed between-player prior sd (σ_resid² − label-sampling-var); a "
      "diagnostic only — the SERVED prior sd stays σ_resid (conservative: the prior is a touch weaker, so "
      "the rookie's own MLB line takes over a touch faster — the safe direction).")
    a("")
    a("## 2. Calibration ablation — MLE prior vs the incumbent generic prior (purged, leave-one-cohort-out)")
    a("")
    a("For each debut cohort Y (≥1 strictly-prior cohort): the GENERIC baseline mean = the population mean "
      "of the realized MLB metric over PRIOR cohorts (what the generic archetype/level prior collapses to "
      "at PA≈0 — E7.3's `archetype_prior` benchmark); the MLE mean = the OOS `mle_<m>`. Each method uses "
      "its OWN prior-cohort residual sd (both self-calibrated → the comparison is calibration × SHARPNESS, "
      "not a sd handicap). Scored on the cohort-Y rookies. Lower NLL/CRPS/MAE = better; coverage ≈ "
      "0.68/0.90 = honest.")
    a("")
    a(pd.DataFrame([abl[m].to_dict() for m in abl]).to_markdown(index=False))
    a("")
    for m in abl:
        r = abl[m]
        verdict = ("✅ MLE prior improves rookie calibration" if r.mle_wins
                   else "🟡 MLE prior does not beat the generic prior on NLL+CRPS")
        a(f"- **{m}** — {verdict}: NLL {r.mle_nll:.4f} vs {r.generic_nll:.4f}, CRPS {r.mle_crps:.5f} vs "
          f"{r.generic_crps:.5f}, MAE {r.mle_mae:.5f} vs {r.generic_mae:.5f} "
          f"(n={r.n_scored} rookies over {r.n_cohorts} cohorts).")
    a("")
    a("## 3. What is wired (and what is not)")
    a("")
    a("- **Served build:** `dbt/models/eb_posteriors/eb_batter_posteriors_raw.sql` (DuckDB branch, the "
      "SF-free lakehouse compute). A `milb_mle_prior` precursor view (this script's S3 output) is joined "
      "on `batter_id` (MLBAM). For K%/BB% the MLE mean + κ become the Beta prior (α=m·κ, β=(1−m)·κ); for "
      "ISO the MLE mean + σ_resid become the Normal prior. A low-PA rookie WITH an MLE gets the MLE line; "
      "the existing generic archetype/slot prior stays for players WITHOUT one, and wOBA is untouched.")
    a("- **PA-accrual blend EXTENDED, not duplicated:** the existing Beta-Binomial / Normal-Normal update "
      "shrinks from the MLE prior toward the rookie's observed MLB line as season PA grows (κ = equivalent "
      "PA). When an MLE prior is present the ZiPS low-PA blend is bypassed for that metric (no "
      "double-counted projection).")
    a("- **Leakage-safe:** only pre-debut minor-league stats enter the MLE (the E7.3 as-of guard); the "
      "prior table is static (rebuilt when the MLE is retrained), read as a W8a precursor.")
    a("")
    a("## 4. Limitations")
    a("")
    a("- **σ_resid carries finite-PA label sampling noise** — so it slightly over-states the between-player "
      "prior sd, making the prior marginally weaker (safe). `true_sd_est` reports the decomposed value.")
    a("- **Graduated players are self-selected** (they reached the MLB PA floor) — the calibration is on "
      "players who established, which is the served population (a rookie getting playing time). Stated, "
      "not corrected (inherited from E7.3).")
    a(f"- **Prospect coverage:** {cov_n} batters carry a calibrated prior (graduated + active prospects).")
    a("- **best_alpha = 0** — a rookie betting prior, never a market bet.")
    a("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    log.info("report → %s", path)


def _upload_s3(local_parquet: Path) -> None:
    """Upload the single calibrated-prior parquet to the W8a precursor-view key (instance-role-safe:
    the shared make_s3_client() resolves the botocore chain — never pass possibly-None env keys, per
    CLAUDE.md's boto3 landmine)."""
    from scripts.utils.lakehouse_raw_writer import make_s3_client

    client = make_s3_client()
    client.upload_file(str(local_parquet), _S3_BUCKET, _S3_KEY)
    log.info("landed calibrated prior → s3://%s/%s", _S3_BUCKET, _S3_KEY)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.5 — recalibrate the MiLB MLE into a served rookie prior")
    p.add_argument("--projections", default=str(_DEFAULT_PROJ),
                   help="the E7.3 mle_projections parquet (run_milb_mle.py output)")
    p.add_argument("--pairs", default=str(_DEFAULT_PAIRS),
                   help="the E7.3 mle_graduated_pairs parquet — supplies mlb_pa + has_mlb_label "
                        "(the E7.3 mlb_pa≥150 label floor) so σ_resid excludes thin-sample cameos")
    p.add_argument("--metrics", nargs="+", default=list(PRIOR_METRICS),
                   help=f"which translated metrics to wire (default {PRIOR_METRICS}; wOBA is never wired)")
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    p.add_argument("--s3", action="store_true",
                   help="upload the calibrated prior to the milb_mle_prior W8a precursor key")
    p.add_argument("--no-report", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    proj_path = Path(args.projections)
    if not proj_path.exists():
        p.error(f"projections parquet not found at {proj_path} — run run_milb_mle.py --s3 first")
    proj = pd.read_parquet(proj_path)
    proj["player_id"] = proj["player_id"].astype(str)
    log.info("loaded %d (player, level) MLE projection rows", len(proj))

    # Attach the E7.3 label floor (mlb_pa≥150) so recalibration/ablation excludes thin-sample MLB cameos
    # (a 1-PA realized K% of 1.0) that would otherwise blow up σ_resid. Reconciles to the E7.3 report.
    pairs_path = Path(args.pairs)
    if pairs_path.exists():
        pairs = pd.read_parquet(pairs_path)
        pairs["player_id"] = pairs["player_id"].astype(str)
        keep = ["player_id", "level", "mlb_pa", "has_mlb_label"]
        proj = proj.merge(pairs[[c for c in keep if c in pairs]], on=["player_id", "level"], how="left")
        log.info("merged label floor from pairs: %d labelled (has_mlb_label) rows",
                 int(proj.get("has_mlb_label", pd.Series(dtype=bool)).fillna(False).sum()))
    else:
        log.warning("pairs parquet not found at %s — recalibrating WITHOUT the mlb_pa label floor "
                    "(σ_resid may be inflated by thin-sample cameos)", pairs_path)

    calib = recalibrate(proj, tuple(args.metrics))
    for m, c in calib.items():
        log.info("recalibrated %-6s: σ_resid=%.4f (param_sd≈%.4f, ×%.1f) cov68=%.2f cov90=%.2f n=%d",
                 m, c.resid_sd, c.param_sd_median, c.resid_sd / c.param_sd_median if c.param_sd_median else 0,
                 c.coverage_68, c.coverage_90, c.n)

    abl = ablate(proj, tuple(args.metrics))
    for m, r in abl.items():
        log.info("ablation  %-6s: MLE nll=%.4f vs generic %.4f | MLE mae=%.4f vs %.4f | wins=%s",
                 m, r.mle_nll, r.generic_nll, r.mle_mae, r.generic_mae, r.mle_wins)

    table = build_calibrated_prior_table(proj, calib)
    log.info("built calibrated prior for %d batters (highest level)", len(table))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    local_parquet = out_dir / "mle_prior_calibrated.parquet"
    table.to_parquet(local_parquet, index=False)

    (out_dir / "e7_5_calibration_summary.json").write_text(json.dumps({
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": args.metrics,
        "n_batters": int(len(table)),
        "recalibration": {m: calib[m].to_dict() for m in calib},
        "ablation": {m: abl[m].to_dict() for m in abl},
    }, indent=2, default=float))

    if not args.no_report:
        write_report(calib, abl, len(table), _REPORT_PATH)

    if args.s3:
        _upload_s3(local_parquet)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
