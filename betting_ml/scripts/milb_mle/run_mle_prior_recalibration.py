"""run_mle_prior_recalibration.py — MLB Edge-E7.5 CLI: recalibrate the MiLB→MLB MLE into a priceable
rookie prior + the calibration ablation, and land the per-player calibrated prior the served EB build reads.

Reads an `mle_projections` set (per (player, level) MLB-equivalent line + realized MLB label for
graduated players; built SF-FREE by run_milb_mle.py --s3 / run_e7_12_slice1.py --emit), runs the E13.6
recalibration (parameter sd → held-out predictive spread → Beta pseudo-count / Normal prior sd), runs the
purged leave-one-cohort-out calibration ablation vs the incumbent generic prior, and writes:

  * <out>/mle_prior_calibrated.parquet          — one row per batter (MLBAM), highest level: the served prior
  * <out>/e7_5_calibration_summary.json         — per-metric σ_resid / coverage / κ params + ablation
  * ablation_results/e7_5_milb_prior_ablation.md — the AC evidence (rookie calibration vs generic prior)
  * s3://baseball-betting-ml-artifacts/baseball/lakehouse/milb_mle_prior/data.parquet (--s3) — the W8a
    precursor view `milb_mle_prior` that eb_batter_posteriors_raw (DuckDB branch) reads; SINGLE overwrite
    file (the universal `<name>/**/*.parquet` glob layout — no Delta, no glob-dup).

E7.5b — THE HEAD-TO-HEAD GATE (2026-08-01)
------------------------------------------
🚨 This parquet is on a LIVE BETTING CONTRACT: milb_mle_prior → eb_batter_posteriors_raw → avg_eb_* →
the served run_diff / pre_lineup tiers. So re-deriving it from a NEW MLE is NOT a refresh — it is a model
swap on a serving path, and "the new MLE already improved the draft board" is not evidence for it (a
board gate does not transfer to a betting gate; a low-risk farm draft does not make the betting path
low-risk).

`--incumbent-projections` turns on the E7.5b gate: a purged leave-one-debut-cohort-out HEAD-TO-HEAD of
the re-derived prior against the CURRENTLY-SERVED one, on the matched intersection of labelled rows,
with two-sided anchors (`mle_prior.head_to_head`). It is decided PER METRIC — a metric that does not
clear keeps the served incumbent's columns VERBATIM, read out of `--served-prior` (the E7.12 emission
precedent: ship what cleared, drop what did not). If NO metric clears, `--s3` refuses to write.

⚠️ SF-FREE. No Snowflake read/write — the projections are S3/lakehouse, the output is an S3 precursor
parquet. best_alpha = 0 (a rookie prior, never a market bet).

  # E7.5 (original, ungated) — recalibrate and land:
  uv run python -m betting_ml.scripts.milb_mle.run_mle_prior_recalibration --projections <parquet> --s3

  # E7.5b — re-derive from the E7.12 slice-1 MLE, GATED against what is serving today:
  AWS_DEFAULT_REGION=us-east-2 uv run python -m betting_ml.scripts.milb_mle.run_mle_prior_recalibration \
      --projections s3://baseball-betting-ml-artifacts/baseball/milb/derived/mle_projections \
      --incumbent-projections quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3_artifacts/mle_projections.parquet
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

from betting_ml.scripts.milb_mle.mle_prior import (  # noqa: E402
    H2H_ALPHA,
    PRIOR_METRICS,
    ablate,
    bh_fdr,
    build_calibrated_prior_table,
    head_to_head,
    recalibrate,
)

log = logging.getLogger("e7_5.mle_prior")

_DEFAULT_PROJ = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3_artifacts/mle_projections.parquet"
_DEFAULT_PAIRS = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3_artifacts/mle_graduated_pairs.parquet"
_DEFAULT_OUT = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_5_artifacts"
_REPORT_PATH = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_5_milb_prior_ablation.md"
_H2H_REPORT_PATH = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_5b_mle_prior_head_to_head.md"
# The prior that is SERVING right now — the source of VERBATIM columns for a metric that does not clear.
_DEFAULT_SERVED = _DEFAULT_OUT / "mle_prior_calibrated.parquet"

_S3_BUCKET = "baseball-betting-ml-artifacts"
_S3_KEY = "baseball/lakehouse/milb_mle_prior/data.parquet"   # W8a precursor-view glob layout (single file)

MODEL_VERSION = "milb_mle_prior_v1"

# The served columns each metric owns — what a hold-back copies verbatim out of the served parquet.
_METRIC_COLS: dict[str, tuple[str, ...]] = {
    "k_pct": ("mle_k_pct", "k_pct_prior_kappa"),
    "bb_pct": ("mle_bb_pct", "bb_pct_prior_kappa"),
    "iso": ("mle_iso", "iso_prior_sd"),
}


def read_projections(uri: str) -> pd.DataFrame:
    """Load a projections set from a local parquet OR a Delta table URI.

    Reading the PUBLISHED Delta table directly is what makes the provenance of a serving-path re-derive
    unambiguous — a local artifact can silently be a stale copy of the model that was actually published
    (the E7.12 `cache_is_current` lesson)."""
    if uri.startswith("s3://") or uri.startswith("delta://"):
        from deltalake import DeltaTable

        from scripts.utils.delta_lake import storage_options
        path = uri.replace("delta://", "s3://", 1)
        dt = DeltaTable(path, storage_options=storage_options())
        df = dt.to_pandas()
        log.info("read %d rows from Delta %s @ v%d", len(df), path, dt.version())
        return df
    return pd.read_parquet(Path(uri))


def write_report(calib: dict, abl: dict, cov_n: int, path: Path,
                 ship: list[str] | None = None, holdback: list[str] | None = None) -> None:
    lines: list[str] = []
    a = lines.append
    a("# MLB Edge-E7.5 — MiLB MLE → recalibrated rookie prior (wired into `eb_batter_posteriors_raw`)")
    a("")
    a(f"**Model:** `{MODEL_VERSION}` · **generated:** {datetime.now(timezone.utc).isoformat()}")
    a("")
    if holdback:
        # ⚠️ Without this banner the tables below would read as a description of the SERVED prior, and
        # they are not — they are the challenger's recalibration for EVERY metric, including ones the
        # E7.5b gate held back. A report that silently over-claims which model is serving is exactly the
        # divergence E7.5b exists to close.
        a(f"> ⚠️ **This run was gated by E7.5b and the served parquet is MIXED.** The recalibration and "
          f"ablation tables below are the CHALLENGER's, for all metrics. What actually ships: "
          f"**{', '.join(ship) if ship else '(nothing)'}** from the challenger MLE; "
          f"**{', '.join(holdback)}** did NOT clear the head-to-head gate and keeps the previously-served "
          f"`milb_mle_v1` values VERBATIM. Read "
          f"[`e7_5b_mle_prior_head_to_head.md`](e7_5b_mle_prior_head_to_head.md) for the per-metric "
          f"verdict and the numbers that are actually serving for the held-back metric(s).")
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


def apply_holdbacks(challenger: pd.DataFrame, served: pd.DataFrame,
                    holdback: list[str]) -> tuple[pd.DataFrame, dict]:
    """Per-metric hold-back: a metric that did NOT clear the gate keeps the SERVED columns VERBATIM.

    The challenger's player set is used as the row spine (a re-fit can only add players — a served
    player who vanished would silently LOSE his prior, so that is asserted, not assumed). A held-back
    metric's values are copied by `batter_id` out of the parquet that is serving today, so the served
    numbers for that metric are byte-identical before and after the swap."""
    out = challenger.copy()
    served = served.copy()
    served["batter_id"] = served["batter_id"].astype(str)
    out["batter_id"] = out["batter_id"].astype(str)

    lost = set(served["batter_id"]) - set(out["batter_id"])
    if lost:
        raise ValueError(
            f"{len(lost)} batters carry a SERVED prior but are absent from the re-derived table — a swap "
            "would silently drop their rookie prior. Refusing; reconcile the projection sets first.")

    stats: dict = {"holdback_metrics": list(holdback), "rows": int(len(out)),
                   "served_rows": int(len(served)),
                   "n_new_batters": int(len(set(out["batter_id"]) - set(served["batter_id"])))}
    for m in holdback:
        cols = _METRIC_COLS[m]
        src = served[["batter_id", *cols]].rename(columns={c: f"__srv_{c}" for c in cols})
        out = out.merge(src, on="batter_id", how="left")
        for c in cols:
            out[c] = out[f"__srv_{c}"]
            out = out.drop(columns=[f"__srv_{c}"])
        out[f"{m}_source"] = "milb_mle_v1_served"
        stats[f"{m}_held_back_nonnull"] = int(out[cols[0]].notna().sum())

    # ⭐ VERBATIM means VERBATIM — assert it rather than trusting the merge. "the held-back metric keeps
    # what is serving today" is the entire safety argument for a per-metric ship on a live betting
    # contract; a silent join defect would turn a hold-back into an unreviewed swap.
    out = out.reset_index(drop=True)
    if holdback:
        chk = served.merge(out, on="batter_id", how="left", suffixes=("_srv", "_new"))
        for m in holdback:
            for c in _METRIC_COLS[m]:
                a = pd.to_numeric(chk[f"{c}_srv"], errors="coerce").to_numpy(float)
                b = pd.to_numeric(chk[f"{c}_new"], errors="coerce").to_numpy(float)
                same = ((a == b) | (pd.isna(a) & pd.isna(b))).all()
                if not same:
                    raise ValueError(f"held-back metric {m}: column {c} is NOT byte-identical to the "
                                     "prior serving today — refusing to write")
        stats["holdback_verbatim_verified"] = True

    # How far does the SERVED number actually MOVE? The gate says a metric is better; this says how big a
    # change is being pushed onto the live contract — the operator's risk read, and what a box-verify
    # should expect to see. Computed on the FINAL table, so a held-back metric reports the 0.0 it must.
    cmp_ = served.merge(out, on="batter_id", how="inner", suffixes=("_srv", "_new"))
    movement: dict = {}
    for cols in _METRIC_COLS.values():
        for c in cols:
            d = (pd.to_numeric(cmp_[f"{c}_new"], errors="coerce")
                 - pd.to_numeric(cmp_[f"{c}_srv"], errors="coerce")).abs().dropna()
            movement[c] = {"mean_abs_delta": float(d.mean()) if len(d) else 0.0,
                           "p95_abs_delta": float(d.quantile(0.95)) if len(d) else 0.0,
                           "max_abs_delta": float(d.max()) if len(d) else 0.0,
                           "n_moved": int((d > 1e-12).sum())}
    stats["served_movement"] = movement
    return out, stats


def write_head_to_head_report(h2h: dict, fdr: dict, calib_new: dict, calib_inc: dict,
                              ship: list[str], holdback: list[str], provenance: dict,
                              merge_stats: dict, path: Path) -> None:
    lines: list[str] = []
    a = lines.append
    a("# MLB Edge-E7.5b — re-deriving the SERVED rookie prior from the E7.12 MLE, behind E7.5's own "
      "held-out gate")
    a("")
    a(f"**generated:** {datetime.now(timezone.utc).isoformat()}")
    a("")
    a(f"- **challenger projections:** `{provenance['challenger']}`  (model_version "
      f"`{provenance['challenger_version']}`, {provenance['challenger_rows']} rows)")
    a(f"- **incumbent projections:** `{provenance['incumbent']}`  (model_version "
      f"`{provenance['incumbent_version']}`, {provenance['incumbent_rows']} rows)")
    a(f"- **currently-served prior:** `{provenance['served']}` ({provenance['served_rows']} batters)")
    a(f"- **label substrate:** `{provenance['pairs']}`")
    a("")
    a("> 🚨 **This is the BETTING prior, not the draft board.** The board reads `mle_projections` "
      "directly and has carried the E7.12 slice-1 model since it published; the SERVED path reads a "
      "separately-recalibrated parquet (`milb_mle_prior` → `eb_batter_posteriors_raw` → `avg_eb_*` → the "
      "served `run_diff` / `pre_lineup` contract) that is still derived from `milb_mle_v1`. E7.5b is the "
      "sanctioned, gated way to close that divergence for BATTERS. `best_alpha = 0` — a cold-start prior, "
      "never a market bet.")
    a("")
    a("## 0. Pre-registration (the gate, fixed before the head-to-head was run)")
    a("")
    a("The E7.12 gain is a **TRANSLATION-MAE** gain. Rookie-prior CALIBRATION is a different objective, "
      "so a translation win need not survive here — **a null is a valid and expected outcome and is not "
      "shipped.** The incumbent already beats the generic prior, so *beating generic is not evidence for "
      "a swap*; the contest below is challenger vs **what is serving today**.")
    a("")
    a("A metric SHIPS only if **every** condition holds; otherwise it keeps the served incumbent verbatim.")
    a("")
    a("| # | condition | why |")
    a("|:--|:--|:--|")
    a("| 1 | challenger NLL < incumbent NLL | the primary proper score (calibration × sharpness) |")
    a("| 2 | challenger CRPS ≤ incumbent CRPS | E7.5's own `mle_wins` pair — CRPS isolates the MEAN, so a "
      "win on NLL alone could be an sd artifact |")
    a("| 3 | challenger wins ≥60% of evaluable cohorts | E7.12 slice 1's fold-rate bar, verbatim — a "
      "pooled mean cannot tell *systematically better* from *won by a hair* |")
    a("| 4 | one-sided paired p < 0.10 on the per-cohort NLL delta | the same paired instrument, same α |")
    a("| 5 | **BH-FDR@0.10 across the three metrics** | three metrics is a three-test family (NF-D15) |")
    a("| 6 | challenger `cov68 ≥ 0.61` **and** `cov90 ≥ 0.83` | ⭐ the named failure mode: a prior that "
      "gets SHARPER without getting better CALIBRATED. A one-sided **FLOOR** — never a target (E2.1-r) |")
    a("| 7 | both degenerate ceilings LOSE | generic population prior + the challenger's own means "
      "PERMUTED within the held-out cohort (same marginal, pairing destroyed) |")
    a("| 8 | both per-form oracle floors HOLD | each arm floored by the peeking version of **its own** "
      "form — a single shared ceiling would veto a legitimately-better arm (NF-D16 (g‴)) |")
    a("")
    a("**Disclosure.** Conditions 1–8 are the E7.5 / E7.12-slice-1 house gate transplanted verbatim, not "
      "tuned to this result. They were fixed after a *comparability* check (below) that showed the sign "
      "of the per-metric deltas but none of the paired statistics, anchors or coverage the gate turns on.")
    a("")
    a("### Comparability — the archived E7.5 numbers are NOT the baseline")
    a("")
    a("The E7.5 report on file was generated 2026-07-26 against a `mle_graduated_pairs` substrate that "
      "has since gained labelled graduates (its ablation scored **n=534 over 10 cohorts**; re-running "
      f"the SAME `milb_mle_v1` model on today's substrate scores **n={h2h[list(h2h)[0]].n_scored}**). "
      "Quoting the archived numbers as the bar would compare two models over two different populations — "
      "the E7.12 `cache_is_current` lesson. **Both arms below are re-run on today's substrate, on the "
      "matched intersection of labelled rows.**")
    a("")
    a("## 1. Head-to-head — purged leave-one-debut-cohort-out, matched population")
    a("")
    rows = []
    for m, r in h2h.items():
        rows.append({
            "metric": m, "n_scored": r.n_scored, "n_cohorts": r.n_cohorts,
            "chal_nll": round(r.challenger.nll, 5), "inc_nll": round(r.incumbent.nll, 5),
            "chal_crps": round(r.challenger.crps, 6), "inc_crps": round(r.incumbent.crps, 6),
            "chal_mae": round(r.challenger.mae, 6), "inc_mae": round(r.incumbent.mae, 6),
            "chal_cov68": round(r.challenger.cov68, 4), "inc_cov68": round(r.incumbent.cov68, 4),
            "chal_cov90": round(r.challenger.cov90, 4), "inc_cov90": round(r.incumbent.cov90, 4),
            "fold_win_rate": round(r.fold_win_rate, 3),
            "p_one_sided": None if r.p_one_sided is None else round(r.p_one_sided, 5),
            "BH-FDR@0.10": fdr.get(m),
        })
    a(pd.DataFrame(rows).to_markdown(index=False))
    a("")
    a("Every arm is **self-calibrated on its OWN prior-cohort residual sd**, so the comparison is "
      "calibration × sharpness rather than an sd handicap. `n_scored` is the MATCHED intersection — both "
      "arms are scored on byte-identical rows against a byte-identical realized label.")
    a("")
    a("## 2. Anchors — a degenerate that must LOSE and a peeking floor that must WIN")
    a("")
    arows = []
    for m, r in h2h.items():
        arows.append({
            "metric": m,
            "challenger_nll": round(r.challenger.nll, 5),
            "generic_degenerate": round(r.generic.nll, 5),
            "permuted_degenerate": round(r.permuted.nll, 5),
            "oracle_challenger (floor)": round(r.oracle_challenger.nll, 5),
            "oracle_incumbent (floor)": round(r.oracle_incumbent.nll, 5),
            "degenerates_lose": r.degenerates_lose,
            "oracle_floor_holds": r.oracle_floor_holds,
        })
    a(pd.DataFrame(arows).to_markdown(index=False))
    a("")
    a("- **Degenerate ceilings** — the generic population prior, and the challenger's own means PERMUTED "
      "within the held-out cohort. The permutation preserves the marginal distribution EXACTLY and "
      "destroys only the per-player pairing, so it is the cleanest available statement of *is there "
      "per-player content here at all*, and it is well-posed at any n (unlike a fitted oracle, NF1.7 (b)).")
    a("- **Peeking floors are PER FORM** — each arm is floored by itself shifted by the held-out cohort's "
      "own mean residual. Flooring both arms on ONE ceiling would veto a legitimately-better arm as a "
      "false metric inversion (NF-D16 (g‴)). An arm beating its own oracle is mathematically impossible "
      "⇒ the tell that the score is inverted, not a win.")
    a("")
    a("## 3. Per-cohort paired NLL deltas (incumbent − challenger; >0 ⇒ the challenger is better)")
    a("")
    a(pd.DataFrame({m: [round(x, 5) for x in r.cohort_nll_delta] for m, r in h2h.items()}).to_markdown())
    a("")
    a("## 4. σ_resid / κ movement — is it SHARPER, and did it stay CALIBRATED?")
    a("")
    krows = []
    for m in h2h:
        cn, ci = calib_new[m], calib_inc[m]
        krows.append({
            "metric": m,
            "sigma_incumbent": round(ci.resid_sd, 6), "sigma_challenger": round(cn.resid_sd, 6),
            "sigma_delta_%": round(100.0 * (cn.resid_sd - ci.resid_sd) / ci.resid_sd, 3),
            "cov68_incumbent": round(ci.coverage_68, 4), "cov68_challenger": round(cn.coverage_68, 4),
            "cov90_incumbent": round(ci.coverage_90, 4), "cov90_challenger": round(cn.coverage_90, 4),
        })
    a(pd.DataFrame(krows).to_markdown(index=False))
    a("")
    a("A **narrower σ_resid is a STRONGER prior** — for K%/BB% it raises the Beta pseudo-count κ = "
      "m(1−m)/σ² − 1 (the prior's equivalent MLB-PA weight), for ISO it raises κ_iso = 0.25/σ². So a "
      "sharpening that is NOT accompanied by held-out coverage staying at nominal would pull a rookie's "
      "line harder toward a projection that has not earned it. That is exactly what condition 6 gates, "
      "and why the coverage figure is read as a floor rather than minimised toward a target.")
    a("")
    a("## 5. Verdict — per metric, not all-or-nothing")
    a("")
    vrows = []
    for m, r in h2h.items():
        g = r.gate_detail(fdr.get(m))
        vrows.append({"metric": m, **{k: v for k, v in g.items()},
                      "VERDICT": "SHIP (milb_mle_v2_parkctx)" if m in ship else "HOLD (served v1 verbatim)"})
    a(pd.DataFrame(vrows).to_markdown(index=False))
    a("")
    for m, r in h2h.items():
        if m in ship:
            a(f"- **{m}** — ✅ **SHIP.** NLL {r.challenger.nll:.5f} vs {r.incumbent.nll:.5f}, CRPS "
              f"{r.challenger.crps:.6f} vs {r.incumbent.crps:.6f}, MAE {r.challenger.mae:.6f} vs "
              f"{r.incumbent.mae:.6f}; {r.fold_win_rate:.0%} of {r.n_cohorts} cohorts, one-sided "
              f"p={r.p_one_sided:.4f}, BH-FDR@0.10 {fdr.get(m)}.")
        else:
            failed = [k for k, v in r.gate_detail(fdr.get(m)).items() if not v]
            a(f"- **{m}** — 🟡 **HOLD — the served `milb_mle_v1` prior is kept VERBATIM.** Failed: "
              f"{', '.join(failed)}. NLL {r.challenger.nll:.5f} vs {r.incumbent.nll:.5f}, CRPS "
              f"{r.challenger.crps:.6f} vs {r.incumbent.crps:.6f}, MAE {r.challenger.mae:.6f} vs "
              f"{r.incumbent.mae:.6f}; {r.fold_win_rate:.0%} of {r.n_cohorts} cohorts"
              + (f", one-sided p={r.p_one_sided:.4f}." if r.p_one_sided is not None else "."))
    a("")
    for m, r in h2h.items():
        if m in ship:
            continue
        # ⭐ underpowered ≠ absent (NF-D15 (g″)). Say WHICH this is rather than shrugging at a hold.
        mean_d = float(np.mean(r.cohort_nll_delta)) if r.cohort_nll_delta else 0.0
        side = ("the WRONG side of zero" if mean_d < 0 else "the right side of zero but under-powered")
        a(f"> 🔎 **Reading the `{m}` hold honestly.** The mean per-cohort NLL delta is **{mean_d:+.5f}** — "
          f"{side} — and the challenger wins **{int(round(r.fold_win_rate * r.n_cohorts))}/{r.n_cohorts}** "
          f"cohorts. "
          + ("This is a LOSS/TIE, not an under-powered win: more debut cohorts would not turn it, so it "
             "is not a candidate for a scheduled re-validation. "
             if mean_d < 0 else
             "This is a directional win that the instrument cannot resolve at this cohort count — a "
             "candidate for re-validation as cohorts accrue, NOT an absence. ")
          + f"Note the challenger's MAE **is** slightly better ({r.challenger.mae:.6f} vs "
            f"{r.incumbent.mae:.6f}) — the E7.12 translation-MAE gain is directionally present, it simply "
            "does not convert into better PRICING. That is the story's whole premise, measured rather "
            "than assumed: a translation-MAE objective and a rookie-prior CALIBRATION objective are not "
            "the same objective, and a win on one does not transfer to the other (the repo's "
            "pricing-optimal ≠ discrimination-optimal rule, facing the other way).")
        a("")
    a("## 6. What is written — and how far the SERVED numbers actually move")
    a("")
    mv = merge_stats.get("served_movement", {})
    if mv:
        a(pd.DataFrame([{"served column": c, **{k: round(v, 6) for k, v in d.items()}}
                        for c, d in mv.items()]).to_markdown(index=False))
        a("")
        a("Deltas are against the parquet serving today, over the batters both tables share. A held-back "
          "metric reads **0.0 across the board** — that is the verbatim guarantee, measured on the final "
          "table rather than asserted. For a shipped metric this is the magnitude of change entering "
          "`eb_batter_posteriors_raw`; it is diluted further downstream, because the prior only dominates "
          "at low MLB PA and the Beta-Binomial / pseudo-count update hands over to the rookie's own "
          "observed line as PA accrues.")
        a("")
    a("### Provenance and row spine")
    a("")
    a(f"- **Shipped metrics:** {ship or '(none)'} — re-derived from the challenger MLE.")
    a(f"- **Held back:** {holdback or '(none)'} — columns copied VERBATIM from the parquet serving today, "
      "so those served numbers are byte-identical before and after.")
    a(f"- Row spine = the challenger's batter set ({merge_stats['rows']} batters, "
      f"{merge_stats['n_new_batters']} new vs the {merge_stats['served_rows']} serving today). A batter "
      "who carries a served prior but is absent from the re-derived table would silently LOSE it — that "
      "is asserted, not assumed, and the write refuses if it happens.")
    a("- Per-metric provenance is carried in `<metric>_source` columns. They are inert to the dbt "
      "consumer (`eb_batter_posteriors_raw` selects named columns) and exist so a future audit can tell "
      "which arm each served number came from.")
    a("")
    a("## 7. Limitations")
    a("")
    a("- **The eval population is graduated players** (they reached the E7.3 MLB-PA label floor) — "
      "self-selected, and inherited from E7.3/E7.5. Stated, not corrected.")
    a("- **10 evaluable debut cohorts is a weak instrument.** The paired p is reported for what it is; "
      "the fold win rate and the anchors carry more of the load than the p-value does.")
    a("- **PBO/DSR are not reported and would be meaningless here**: this is a two-arm pre-specified "
      "contest, not a search over a candidate field, so there is no in-sample selection to deflate. The "
      "multiplicity that DOES exist — three metrics — is handled by BH-FDR (condition 5).")
    a("- **A held-back metric on a batter whose highest reached level moved between the two projection "
      "sets** keeps the served value, which was translated at the incumbent's level. `mle_level` "
      "describes the challenger. Cosmetic (the dbt consumer never reads `mle_level`), stated for audit.")
    a("- **`best_alpha = 0`** — a cold-start rookie prior, never a market bet.")
    a("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    log.info("head-to-head report → %s", path)


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
    # ── E7.5b — the head-to-head gate against what is SERVING today ──────────────────────
    p.add_argument("--incumbent-projections", default=None,
                   help="E7.5b: the projections the CURRENTLY-SERVED prior was derived from. Supplying "
                        "it turns on the purged head-to-head gate; a metric that does not clear keeps "
                        "the served columns verbatim and `--s3` refuses if NO metric clears.")
    p.add_argument("--served-prior", default=str(_DEFAULT_SERVED),
                   help="E7.5b: the prior parquet serving today — the source of verbatim columns for a "
                        "metric that does not clear the gate")
    p.add_argument("--out-name", default="mle_prior_calibrated.parquet",
                   help="output parquet filename inside --out-dir (use a distinct name for a dry run so "
                        "the artifact that is serving today is not overwritten before the gate is read)")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    # The E7.3 label floor (mlb_pa≥150): recalibration/ablation must exclude thin-sample MLB cameos (a
    # 1-PA realized K% of 1.0) that would otherwise blow up σ_resid. Reconciles to the E7.3 report.
    pairs_path = Path(args.pairs)
    pairs = None
    if pairs_path.exists():
        pairs = pd.read_parquet(pairs_path)
        pairs["player_id"] = pairs["player_id"].astype(str)
    else:
        log.warning("pairs parquet not found at %s — recalibrating WITHOUT the mlb_pa label floor "
                    "(σ_resid may be inflated by thin-sample cameos)", pairs_path)

    def _load(uri: str, what: str) -> pd.DataFrame:
        if not (uri.startswith("s3://") or uri.startswith("delta://")) and not Path(uri).exists():
            p.error(f"{what} projections not found at {uri} — run run_milb_mle.py --s3 first")
        df = read_projections(uri)
        df["player_id"] = df["player_id"].astype(str)
        if pairs is not None:
            keep = ["player_id", "level", "mlb_pa", "has_mlb_label"]
            df = df.merge(pairs[[c for c in keep if c in pairs]], on=["player_id", "level"], how="left")
        log.info("%s: %d (player, level) rows, %d labelled, model_version=%s", what, len(df),
                 int(df.get("has_mlb_label", pd.Series(dtype=bool)).fillna(False).sum()),
                 sorted(df["model_version"].dropna().unique()) if "model_version" in df else "?")
        return df

    proj = _load(args.projections, "challenger")
    metrics = tuple(args.metrics)

    calib = recalibrate(proj, metrics)
    for m, c in calib.items():
        log.info("recalibrated %-6s: σ_resid=%.4f (param_sd≈%.4f, ×%.1f) cov68=%.2f cov90=%.2f n=%d",
                 m, c.resid_sd, c.param_sd_median, c.resid_sd / c.param_sd_median if c.param_sd_median else 0,
                 c.coverage_68, c.coverage_90, c.n)

    abl = ablate(proj, metrics)
    for m, r in abl.items():
        log.info("ablation  %-6s: MLE nll=%.4f vs generic %.4f | MLE mae=%.4f vs %.4f | wins=%s",
                 m, r.mle_nll, r.generic_nll, r.mle_mae, r.generic_mae, r.mle_wins)

    table = build_calibrated_prior_table(proj, calib)
    _chal_version = (sorted(proj["model_version"].dropna().unique())[0]
                     if "model_version" in proj and proj["model_version"].notna().any() else "challenger")
    for m in metrics:
        table[f"{m}_source"] = _chal_version
    log.info("built calibrated prior for %d batters (highest level)", len(table))

    # ══ E7.5b — the head-to-head gate ══════════════════════════════════════════════════
    h2h = fdr = None
    ship: list[str] = list(metrics)
    holdback: list[str] = []
    merge_stats: dict = {}
    if args.incumbent_projections:
        inc_proj = _load(args.incumbent_projections, "incumbent")
        calib_inc = recalibrate(inc_proj, metrics)
        h2h = head_to_head(proj, inc_proj, metrics)
        fdr = bh_fdr({m: h2h[m].p_one_sided for m in h2h}, alpha=H2H_ALPHA)
        ship = [m for m in metrics if h2h[m].ships(fdr.get(m))]
        holdback = [m for m in metrics if m not in ship]
        for m in metrics:
            r = h2h[m]
            log.info("H2H %-6s: chal nll=%.5f vs inc %.5f | crps %.6f vs %.6f | folds %.0f%% | p=%s | "
                     "BH=%s ⇒ %s", m, r.challenger.nll, r.incumbent.nll, r.challenger.crps,
                     r.incumbent.crps, 100 * r.fold_win_rate,
                     "n/a" if r.p_one_sided is None else f"{r.p_one_sided:.4f}", fdr.get(m),
                     "SHIP" if m in ship else "HOLD (served verbatim)")
            for k, v in r.gate_detail(fdr.get(m)).items():
                if not v:
                    log.info("    ✗ %s", k)

        served = pd.read_parquet(Path(args.served_prior))
        table, merge_stats = apply_holdbacks(table, served, holdback)

        if not ship:
            log.warning("[ALERT] NO metric cleared the E7.5b head-to-head gate — the re-derived prior is "
                        "a NULL and must NOT ship. The served prior is unchanged.")
    elif args.s3:
        # roadmap item 13: re-running the recalibration against a NEW MLE and landing it WITHOUT the
        # head-to-head is precisely the "tidy this up" mistake E7.5b exists to prevent. Refusing outright
        # would break the original E7.5 contract (a legitimate same-model refresh), so it is loud instead.
        log.warning("[ALERT] --s3 WITHOUT --incumbent-projections: this lands an UNGATED prior on the "
                    "LIVE run_diff / pre_lineup betting contract. That is only correct for a same-model "
                    "refresh. If the projections come from a NEW MLE, STOP and pass "
                    "--incumbent-projections so the E7.5b head-to-head gate runs (roadmap item 13).")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    local_parquet = out_dir / args.out_name
    table.to_parquet(local_parquet, index=False)
    log.info("wrote %s (%d batters)", local_parquet, len(table))

    (out_dir / "e7_5_calibration_summary.json").write_text(json.dumps({
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": list(metrics),
        "n_batters": int(len(table)),
        "recalibration": {m: calib[m].to_dict() for m in calib},
        "ablation": {m: abl[m].to_dict() for m in abl},
        **({"e7_5b_head_to_head": {
            "challenger_projections": args.projections,
            "incumbent_projections": args.incumbent_projections,
            "served_prior": args.served_prior,
            "bh_fdr_alpha_0.10": fdr,
            "ship": ship, "holdback": holdback, "merge": merge_stats,
            "per_metric": {m: h2h[m].to_dict(fdr.get(m)) for m in h2h},
        }} if h2h else {}),
    }, indent=2, default=float))

    if not args.no_report:
        write_report(calib, abl, len(table), _REPORT_PATH,
                     ship=ship if h2h else None, holdback=holdback if h2h else None)
        if h2h:
            def _rel(u: str) -> str:
                """Repo-relative where possible — an absolute developer path in a committed report is
                provenance nobody else can resolve. A URI is passed through verbatim (`Path()` collapses
                the `//` and would silently corrupt an s3:// key)."""
                if "://" in u:
                    return u
                try:
                    return str(Path(u).resolve().relative_to(_PROJECT_ROOT))
                except (ValueError, OSError):
                    return u

            def _ver(df: pd.DataFrame) -> str:
                v = sorted(df["model_version"].dropna().unique()) if "model_version" in df else []
                return ", ".join(map(str, v)) or "?"
            write_head_to_head_report(
                h2h, fdr, calib, calib_inc, ship, holdback,
                provenance={
                    "challenger": _rel(args.projections), "challenger_version": _ver(proj),
                    "challenger_rows": int(len(proj)),
                    "incumbent": _rel(args.incumbent_projections), "incumbent_version": _ver(inc_proj),
                    "incumbent_rows": int(len(inc_proj)),
                    "served": _rel(args.served_prior),
                    "served_rows": int(merge_stats.get("served_rows", 0)),
                    "pairs": _rel(str(pairs_path)),
                },
                merge_stats=merge_stats, path=_H2H_REPORT_PATH)

    if args.s3:
        if h2h is not None and not ship:
            log.error("REFUSING --s3: no metric cleared the E7.5b gate, so the write would be a pure "
                      "no-op on a live betting contract with a new provenance stamp. Nothing uploaded.")
            return 1
        _upload_s3(local_parquet)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
