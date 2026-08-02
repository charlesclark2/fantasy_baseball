"""mh2_backfill_design_blocks.py — MH2.3: backfill the MH2-DESIGN-BLOCK into the 46 reports MH2's
mechanical inventory found unclassifiable (`mh2_cv_power.scan_markdown`'s `unextractable_reports`).

Run (LAPTOP, seconds — pure reads of stored artifacts + a text edit, NO re-fit, NO Snowflake):

    uv run python -m betting_ml.scripts.mh2_backfill_design_blocks [--dry-run]

WHAT THIS DOES, AND WHAT IT DELIBERATELY DOES NOT
---------------------------------------------------------------------------------------------------
For each of the 46 reports this is a THREE-WAY, per-report, hand-registered decision — not a
generic scan — because the corpus is genuinely heterogeneous (readiness lock 3):

  1. **RECOVERED.** The report's own JSON artifact (or, for the E7.12/E7.15 family, the SAME
     `*_summary.json` `mh2_cv_power.scan_e7_summaries` already trusts for the rich tier) still
     exists on disk and carries fold/arm/verdict structure. The design block is built FROM that
     stored artifact — never a re-fit, never a guess.
  2. **EXEMPT.** The report was never a bake-off/verdict document at all — a pre-registration
     (written before any arm was scored), a research spike (GO/NO-GO, not a statistical gate), a
     data/join-coverage audit, an operational data-grab log. Forcing a fold-count field onto one of
     these would itself be the LOCK-2 fabrication the block format exists to prevent.
  3. **UNRECOVERABLE.** The report reads like a genuine bake-off, but no stored artifact with its
     per-fold/per-arm data survives in the repo (checked by `find`/`grep`, not assumed). Named
     explicitly, with the specific missing piece, rather than left silently opaque.

Every report in the registry below was read (not pattern-matched) to reach its classification —
see the `# ` comment on each entry for the one-line reason. The registry is intentionally a plain
Python dict of small functions, not a generic "try every JSON shape" resolver: this corpus has at
least 8 distinct JSON shapes across its history, and a generic matcher risks silently attributing
one study's stored numbers to a different report's design block, which would be worse than leaving
it unrecoverable.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from betting_ml.scripts.mh2_cv_power import ABL, TIER_WINDOWS, scan_e7_summaries
from betting_ml.utils.design_block import (
    DesignBlock,
    design_block_from_comp_validation_report,
    design_block_from_source_accuracy_report,
    has_design_block,
    insert_design_block,
)

log = logging.getLogger("mh2.backfill")

_TIER = {t.tier: t for t in TIER_WINDOWS}
_MILB_FOLD_RULE = _TIER["MiLB→MLB translation (batter)"].fold_rule
_STRICT_FOLD_RULE = _TIER["Prospect comps — strict maturity"].fold_rule
_RELAXED_FOLD_RULE = _TIER["Prospect comps — relaxed context"].fold_rule
_SOURCE_H2H_FOLD_RULE = _TIER["Prospect source head-to-head"].fold_rule
_SOURCE_H2H_CONTRAST = _TIER["Prospect source head-to-head"].primary_contrast


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# RECOVERED — shape 1: the E7.12/E7.15 rich tier `scan_e7_summaries` already resolves
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _from_rich_tier(study: str, side: str) -> DesignBlock:
    rich, _ = scan_e7_summaries()
    rows = [r for r in rich if r.study == f"{study} ({side})"]
    if not rows:
        raise LookupError(f"no rich-tier rows resolved for {study} ({side}) — "
                          f"scan_e7_summaries's own resolver found nothing")
    per_metric = [{"metric": r.metric, "verdict": r.verdict, "n_folds": r.n_folds,
                   "n_arms": r.n_arms, "pbo": r.pbo, "dsr": r.dsr,
                   "fold_win_rate": r.fold_win_rate} for r in rows]
    folds = {r.n_folds for r in rows if r.n_folds}
    return DesignBlock(
        status="recovered", fold_rule=_MILB_FOLD_RULE,
        n_folds=(next(iter(folds)) if len(folds) == 1 else None),
        n_arms=max((r.n_arms or 0) for r in rows) or None,
        primary_contrast="paired-t",
        verdict=", ".join(f"{r.metric}={r.verdict}" for r in rows),
        per_metric=per_metric, source_artifact=rows[0].source_file,
        reason=None)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# RECOVERED — shape 2: the prospect-comp "fold_census / by_type / verdict_by_type" family
# (e7_13's own `e7_13_comp_validation.json`, e7_16's `e7_16_comp_validation.json`)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _comp_validation(json_rel: str, *, use_fold_census: bool) -> DesignBlock:
    d = json.loads((ABL / json_rel).read_text())
    fold_rule = _STRICT_FOLD_RULE if (d.get("primary_fold_rule") == "strict"
                                       or use_fold_census) else _RELAXED_FOLD_RULE
    return design_block_from_comp_validation_report(
        d, fold_rule=fold_rule, primary_contrast="forward-outcome comparison",
        use_fold_census=use_fold_census, source_artifact=json_rel)


def _e7_14_source_accuracy() -> DesignBlock:
    json_rel = "e7_16_artifacts/e7_14_source_accuracy.json"
    d = json.loads((ABL / json_rel).read_text())
    return design_block_from_source_accuracy_report(
        d, fold_rule=_SOURCE_H2H_FOLD_RULE, primary_contrast=_SOURCE_H2H_CONTRAST,
        source_artifact=json_rel)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# RECOVERED — shape 3: the "lift.json" family (target/metric/n_eval/n_configs/pbo/candidates)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _e13_2b_retest() -> DesignBlock:
    per_metric = []
    for name in ("miss_distance_home_win_lift", "miss_distance_perside_runs_lift",
                 "zone_profile_home_win_lift", "zone_profile_perside_runs_lift"):
        p = ABL / f"e13_2b_{name}.json"
        d = json.loads(p.read_text())
        pbo = d.get("pbo") or {}
        cand = (d.get("candidates") or {}).get("candidate") or {}
        lift = ((cand.get("lift") or {}).get("all") or {}).get("lift")
        cand_dsr = cand.get("dsr")
        dsr_scalar = cand_dsr.get("dsr") if isinstance(cand_dsr, dict) else cand_dsr
        per_metric.append({
            "metric": f"{d.get('target')}/{d.get('metric')} ({name.split('_lift')[0].rsplit('_', 2)[0]})",
            "verdict": ("ADD" if (pbo.get("clears_live") and (lift or 0) > 0) else "NULL"),
            "n_folds": None, "n_arms": d.get("n_configs"),
            "pbo": pbo.get("pbo"), "dsr": dsr_scalar})
    return DesignBlock(
        status="recovered", fold_rule="CSCV combinatorial slices (not a walk-forward fold count — "
        "see gates.n_slices per metric; n_folds intentionally left null rather than conflated with it)",
        n_folds=None, n_arms=2, primary_contrast="CSCV/PBO on held-out slices",
        verdict="zone_profile CONCLUSIVE (2015-2025 history); miss_distance EXPLORATORY/degenerate "
                "(2026-only, n_eval=0 on perside_runs — see report's own §Half-2 caveat)",
        per_metric=per_metric,
        source_artifact="e13_2b_{miss_distance,zone_profile}_{home_win,perside_runs}_lift.json",
        reason=None)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# RECOVERED — shape 4: the "coherence" family (meta / deflation{pbo,dsr,fdr} / candidates)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _e13_14_coherence(json_name: str) -> DesignBlock:
    """`candidates` here is ONE summary object (`{candidates:[], control_breaks:[],
    control_consistent, n_fragile, verdict}`), not keyed-by-relation — per-relation detail instead
    lives in `meta.status` (RAN vs DEFERRED, with the games/rows each relation ran on)."""
    p = ABL / json_name
    d = json.loads(p.read_text())
    meta, defl, summary = d.get("meta") or {}, d.get("deflation") or {}, d.get("candidates") or {}
    dsr, pbo, fdr = defl.get("dsr") or {}, defl.get("pbo") or {}, defl.get("fdr") or {}
    per_metric = [{"metric": rel, "verdict": status, "n_arms": None, "n_folds": None}
                  for rel, status in (meta.get("status") or {}).items()]
    # ⚠️ `dsr.n_obs` is a control-break OBSERVATION count for the deflated-Sharpe calc, not a
    # walk-forward fold count — recording it as `n_folds` would repeat exactly the E7.9/E7.15
    # "months-in-a-season aren't independent folds" conflation `mh2_cv_power.py` §5 Defect 2 warns
    # about. Left null; the honest number is reported under `gates.dsr_n_obs` instead.
    return DesignBlock(
        status="recovered", fold_rule="per-relation control-break slices over the seasons in "
        "`meta.seasons` (see gates.dsr_n_obs — an observation count for the DSR calc, not a "
        "walk-forward fold count)", n_folds=None,
        n_arms=int(dsr.get("n_trials")) if dsr.get("n_trials") else int(pbo.get("n_configs") or 0) or None,
        primary_contrast="deflated Sharpe over relation×config trials",
        verdict=str(summary.get("verdict")),
        gates={"pbo": pbo.get("pbo"), "dsr": dsr.get("dsr"), "dsr_n_obs": dsr.get("n_obs"),
               "fdr_q": fdr.get("q"), "n_survive": fdr.get("n_survive"),
               "n_tested": fdr.get("n_tested"), "n_fragile": summary.get("n_fragile"),
               "control_consistent": summary.get("control_consistent")},
        per_metric=per_metric, source_artifact=json_name, reason=None)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# RECOVERED — shape 5: e7_5's calibration summary (`ablation` + `e7_5b_head_to_head`, ONE json,
# TWO reports)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _e7_5_ablation() -> DesignBlock:
    p = ABL / "e7_5_artifacts/e7_5_calibration_summary.json"
    d = json.loads(p.read_text())
    abl = d.get("ablation") or {}
    per_metric = [{"metric": m, "verdict": ("ADD" if info.get("mle_wins") else "DROP"),
                   "n_folds": info.get("n_cohorts"), "n_arms": 2}
                  for m, info in abl.items()]
    folds = {e["n_folds"] for e in per_metric if e["n_folds"]}
    return DesignBlock(
        status="recovered", fold_rule=_MILB_FOLD_RULE,
        n_folds=(next(iter(folds)) if len(folds) == 1 else None), n_arms=2,
        primary_contrast="MLE-recalibrated prior vs generic experience-band prior",
        verdict=", ".join(f"{e['metric']}={e['verdict']}" for e in per_metric),
        per_metric=per_metric,
        source_artifact="e7_5_artifacts/e7_5_calibration_summary.json", reason=None)


def _e7_5b_head_to_head() -> DesignBlock:
    p = ABL / "e7_5_artifacts/e7_5_calibration_summary.json"
    d = json.loads(p.read_text())
    h2h = d.get("e7_5b_head_to_head") or {}
    fdr = h2h.get("bh_fdr_alpha_0.10") or {}
    ship, holdback = set(h2h.get("ship") or []), set(h2h.get("holdback") or [])
    per_metric = [{"metric": m, "verdict": ("ADD" if m in ship else "DROP" if m in holdback else "?"),
                   "n_folds": None, "n_arms": 2, "pbo": None} for m in fdr]
    return DesignBlock(
        status="recovered", fold_rule="BH-FDR over the ablation's per-metric p-values "
        f"(alpha=0.10)", n_folds=None, n_arms=2,
        primary_contrast="challenger (recalibrated) vs incumbent served prior, per metric",
        verdict=f"ship={sorted(ship)}, holdback={sorted(holdback)}",
        per_metric=per_metric,
        source_artifact="e7_5_artifacts/e7_5_calibration_summary.json", reason=None)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# RECOVERED — shape 6: e7_8's `fv_translation.json` (gates/pvalues/fdr_survives/verdicts/per_cell)
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _e7_8_fv_translation() -> DesignBlock:
    p = ABL / "e7_8_fv_translation.json"
    d = json.loads(p.read_text())
    gates, per_cell = d.get("gates") or {}, d.get("per_cell") or {}
    verdicts = d.get("verdicts") or []
    per_metric = [{
        "metric": f"{v.get('player_type')}/{v.get('stage')}",
        "verdict": ("ADD" if v.get("adds_lift") else "DROP"),
        "n_folds": len((per_cell.get(f"{v.get('player_type')}/{v.get('stage')}") or {})
                       .get("fold_cohorts") or []) or None,
        "n_arms": len((per_cell.get(f"{v.get('player_type')}/{v.get('stage')}") or {})
                      .get("leaderboard") or []) or None,
        "pbo": v.get("pbo"), "dsr": v.get("dsr")} for v in verdicts]
    folds = {e["n_folds"] for e in per_metric if e["n_folds"]}
    return DesignBlock(
        status="recovered", fold_rule="leave-one-MLB-debut-cohort-out over `fold_cohorts`",
        n_folds=(next(iter(folds)) if len(folds) == 1 else None),
        n_arms=max((e["n_arms"] or 0) for e in per_metric) or None,
        primary_contrast="paired-t (BH-FDR corrected)",
        verdict=", ".join(f"{e['metric']}={e['verdict']}" for e in per_metric),
        gates={"pbo_max": gates.get("pbo_max"), "dsr_min": gates.get("dsr_min"),
               "fdr_q": gates.get("fdr_q")},
        per_metric=per_metric, source_artifact="e7_8_fv_translation.json", reason=None)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# RECOVERED — shape 7: e13_2's PA-outcome `{folds, summary, kappa}`
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def _e13_2_pa_outcome(json_name: str) -> DesignBlock:
    p = ABL / json_name
    d = json.loads(p.read_text())
    folds, summary = d.get("folds") or [], d.get("summary") or {}
    beats = bool(summary.get("beats_log5_all_folds") and summary.get("beats_marginal_all_folds"))
    noise_floor_ok = summary.get("clears_noise_floor_vs_log5")
    verdict = "ADD" if beats and (noise_floor_ok is not False) else (
        "POWER_LIMITED (beats both foils every fold, but below the pre-registered NLL noise floor)"
        if beats else "DROP")
    return DesignBlock(
        status="recovered", fold_rule="expanding-window by season (train < eval_year)",
        n_folds=len(folds) or None, n_arms=1, primary_contrast="paired vs log5 + marginal foils",
        verdict=verdict,
        gates={"mean_delta_vs_log5": summary.get("mean_delta_vs_log5"),
               "nll_noise_floor": summary.get("nll_noise_floor")},
        source_artifact=json_name, reason=None)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The registry — every report in MH2's 46, read (not pattern-matched) to reach its classification.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def exempt(reason: str):
    return lambda: DesignBlock(status="exempt", reason=reason)


def unrecoverable(reason: str):
    return lambda: DesignBlock(status="unrecoverable", reason=reason)


REGISTRY: dict[str, callable] = {
    # ── RECOVERED — rich tier (E7.12/E7.15, via scan_e7_summaries) ──────────────────────────────
    "e7_12_slice1_park_level_context.md": lambda: _from_rich_tier("e7_12_slice1", "batter"),
    "e7_12_slice1p_park_level_context_pitchers.md": lambda: _from_rich_tier("e7_12_slice1", "pitcher"),
    "e7_15_h1_level_ladder.md": lambda: _from_rich_tier("e7_15_h1", "batter"),
    "e7_15_h1_level_ladder_pitchers.md": lambda: _from_rich_tier("e7_15_h1", "pitcher"),
    "e7_15_h2_opponent_quality.md": lambda: _from_rich_tier("e7_15_h2", "batter"),
    "e7_15_h2_opponent_quality_pitchers.md": lambda: _from_rich_tier("e7_15_h2", "pitcher"),
    "e7_15_h3_player_structure_pitchers.md": lambda: _from_rich_tier("e7_15_h3", "pitcher"),

    # ── RECOVERED — comp_validation family ──────────────────────────────────────────────────────
    "e7_13_artifacts/e7_13_comp_validation.md": lambda: _comp_validation(
        "e7_13_artifacts/e7_13_comp_validation.json", use_fold_census=False),
    "e7_13_prospect_comps.md": lambda: _comp_validation(
        "e7_13_artifacts/e7_13_comp_validation.json", use_fold_census=False),
    "e7_16_artifacts/e7_16_comp_validation.md": lambda: _comp_validation(
        "e7_16_artifacts/e7_16_comp_validation.json", use_fold_census=True),
    "e7_16_pipeline_comp_pool.md": lambda: _comp_validation(
        "e7_16_artifacts/e7_16_comp_validation.json", use_fold_census=True),
    "e7_16_artifacts/e7_14_source_accuracy.md": _e7_14_source_accuracy,

    # ── RECOVERED — lift / coherence / calibration / fv_translation / pa_outcome shapes ─────────
    "e13_2b_feature_augmented_retest.md": _e13_2b_retest,
    "e13_14_cross_market_coherence.md": lambda: _e13_14_coherence(
        "e13_14_cross_market_coherence.json"),
    "e13_14_cross_market_coherence_smoke.md": lambda: _e13_14_coherence(
        "e13_14_cross_market_coherence_smoke.json"),
    "e7_5_milb_prior_ablation.md": _e7_5_ablation,
    "e7_5b_mle_prior_head_to_head.md": _e7_5b_head_to_head,
    "e7_8_fv_translation.md": _e7_8_fv_translation,
    "e13_2_pa_outcome_v1_cv.md": lambda: _e13_2_pa_outcome("e13_2_pa_outcome_v1_cv.json"),
    "e13_2_pa_outcome_v2_cv.md": lambda: _e13_2_pa_outcome("e13_2_pa_outcome_v2_cv.json"),

    # ── EXEMPT — never a bake-off/verdict document (read, not guessed — see each reason) ───────
    "E13_2_phase0_report.md": exempt(
        "Phase-0 completion report (cost-hygiene guard + W1 parity check) — a plumbing/parity "
        "gate, not an arm bake-off; no fold/arm/verdict concept in the document."),
    "e13_8_market_accuracy_benchmark.md": exempt(
        "a market-accuracy BENCHMARK ('what are we targeting'), not a model bake-off — no arms, "
        "no candidate being selected against a foil."),
    "e2_2_copula_decision.md": exempt(
        "a single-fit dependence-structure DECISION record (rho estimate + a conditioning "
        "choice) — one fit, not a multi-arm bake-off with folds/PBO/DSR."),
    "e2_3_convolution_calibration.md": exempt(
        "a calibration record for one convolution pipeline (per-side dispersion fit) — no "
        "competing arms."),
    "e2_5_signal_registration.md": exempt(
        "a serving-registration write-up for the E2.1-r winner (already gated elsewhere) — "
        "registers a decision already made, runs no bake-off of its own."),
    "e2_6_preregistration.md": exempt(
        "explicitly a PRE-REGISTRATION, written before any arm was scored — by definition carries "
        "no verdict yet; the results (when run) land in e2_6_derivative_gates.md, which the header "
        "regex already extracts."),
    "e5_3_join_coverage.md": exempt(
        "a name-to-ID join-coverage AUDIT (resolution rate table) — a data-quality check, not a "
        "model comparison."),
    "e7_4_prospect_xref.md": exempt(
        "an identity/ETA cross-reference BUILD status report (rows landed, tripwires clear) — no "
        "arms, no fold structure."),
    "e7_9_historical_backfill_procedure.md": exempt(
        "explicitly 'Status: NOT TRIGGERED' — a pre-agreed CONDITIONAL procedure document with no "
        "run behind it yet."),
    "e7_9_train_serve_audit.md": exempt(
        "a train/serve feature-EXPOSURE scoping table (which served contracts touch the MLE "
        "columns) — an audit, not a bake-off; no fold/PBO/DSR anywhere in its own artifact either."),
    "e7_11_prospect_consensus.md": exempt(
        "states its own standing explicitly: 'A consensus is a DESCRIPTION, not a claim ... no "
        "accuracy test against realized outcomes was run and none is implied.'"),
    "e7_11_artifacts/manual_source_ACCESS.md": exempt(
        "an access-probe NOTES file (which prospect sources needed manual vs automated ingestion) "
        "— gitignored build artifact, regenerated by build_consensus.py; not a bake-off. (Also not "
        "present in this checkout — gitignored artifacts aren't in the git tree at all, so there is "
        "no file here to insert a block into; this entry documents the classification for when it "
        "is regenerated.)"),
    "e7_15_h1_preregistration.md": exempt(
        "a pre-registration ('written before any arm was scored', per run_e7_15_h1.py's own "
        "citation) — the results land in e7_15_h1_level_ladder.md, covered above."),
    "e7_15_h3_preregistration.md": exempt(
        "same as h1: a pre-registration, cited by run_e7_15_h3.py as 'written before any arm was "
        "scored'; results land in e7_15_h3_player_structure(_pitchers).md."),
    "e8_0_prospect_board.md": exempt(
        "states its own standing explicitly: 'best_alpha = 0 ... not a ranking that claims to beat "
        "FanGraphs ... nothing here has been validated as a ranking.'"),
    "e8_2a_cbs_access_probe.md": exempt(
        "a feasibility SPIKE with a GO/NO-GO recommendation (four access paths tried live) — not a "
        "statistical gate; explicitly 'research spike only'."),
    "odds_market_grab_2026-06-30.md": exempt(
        "an operational data-GRAB log (credits spent, probe results, a value-ranked queue handed "
        "to the operator) — no model, no arms."),
    "odds_market_inventory_2026-06-30.md": exempt(
        "a read-only S3 market-INVENTORY audit (which Odds-API keys are present/stale) — a coverage "
        "check, not a bake-off."),

    # ── UNRECOVERABLE — genuinely bake-off-shaped, no surviving per-fold artifact ───────────────
    "e7_12_slice2_survivorship.md": unrecoverable(
        "no `*_summary.json` (or any other JSON) exists anywhere under ablation_results for "
        "slice2 — `find … -iname '*slice2*'` returns only the two .md files. run_e7_12_slice2.py "
        "still exists and could re-emit a summary artifact on a future run (LOCK 1: that re-run is "
        "not this story's to trigger)."),
    "e7_12_slice2_survivorship_pitchers.md": unrecoverable(
        "same as the batter report — no stored artifact survives for slice2 (pitcher side)."),
    "e7_12_slice4_tool_grades.md": unrecoverable(
        "no `*_summary.json` (or any other JSON) exists for slice4 — same gap as slice2. "
        "run_e7_12_slice4.py still exists."),
    "e7_12_slice4_tool_grades_pitchers.md": unrecoverable(
        "same as the batter report — no stored artifact survives for slice4 (pitcher side)."),
    "e7_12_slice5_aging_curves.md": unrecoverable(
        "no `*_summary.json` (or any other JSON) exists for slice5. run_e7_12_slice5.py still "
        "exists."),
    "e7_12_slice5_aging_curves_pitchers.md": unrecoverable(
        "same as the batter report — no stored artifact survives for slice5 (pitcher side)."),
    "e7_12_slice6_feasibility.md": unrecoverable(
        "no `*_summary.json` (or any other JSON) exists for slice6 (a feasibility ceiling-probe, "
        "not a leaderboard bake-off — s6_feasibility.py still exists)."),
    "e7_12_slice6_feasibility_pitchers.md": unrecoverable(
        "same as the batter report — no stored artifact survives for slice6 (pitcher side)."),
}


def run(dry_run: bool = False) -> dict:
    result = {"recovered": [], "exempt": [], "unrecoverable": [], "already_had_block": [],
              "missing_file": [], "extraction_failed": []}
    for rel, make in sorted(REGISTRY.items()):
        p = ABL / rel
        if not p.exists():
            result["missing_file"].append(rel)
            log.warning("skip %s — file not present in this checkout", rel)
            continue
        txt = p.read_text(errors="ignore")
        if has_design_block(txt):
            result["already_had_block"].append(rel)
            continue
        try:
            db = make()
        except Exception as e:                                   # noqa: BLE001 - corpus hygiene
            result["extraction_failed"].append({"file": rel, "error": str(e)})
            log.error("extraction failed for %s: %s", rel, e)
            continue
        bucket = {"recorded": "recovered", "recovered": "recovered",
                 "exempt": "exempt", "unrecoverable": "unrecoverable"}[db.status]
        result[bucket].append(rel)
        if not dry_run:
            p.write_text(insert_design_block(txt, db))
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    recorded_unextractable = set(
        json.loads((ABL / "mh2_cv_power.json").read_text())["extraction"]["unextractable_reports"])
    unregistered = sorted(recorded_unextractable - set(REGISTRY))
    if unregistered:
        log.error("REGISTRY is missing %d of MH2's recorded unextractable reports: %s",
                  len(unregistered), unregistered)
        return 1

    result = run(dry_run=args.dry_run)
    log.info("recovered=%d exempt=%d unrecoverable=%d already_had_block=%d missing_file=%d "
             "extraction_failed=%d%s",
             len(result["recovered"]), len(result["exempt"]), len(result["unrecoverable"]),
             len(result["already_had_block"]), len(result["missing_file"]),
             len(result["extraction_failed"]), "  [DRY RUN]" if args.dry_run else "")
    if result["extraction_failed"]:
        for f in result["extraction_failed"]:
            log.error("  FAILED %s: %s", f["file"], f["error"])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
