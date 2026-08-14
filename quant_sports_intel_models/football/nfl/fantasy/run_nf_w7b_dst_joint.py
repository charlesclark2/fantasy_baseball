"""run_nf_w7b_dst_joint.py — NF-W7b §0.5: the DST dependence successor (joint/copula draw over
the co-moving component legs), gated on the SAME coverage(80) floor and the SAME three foils
that refused NF-W7's independent draw.

Everything decidable in advance lives as a CONSTANT in `kdst_weekly_joint.py`; this runner READS
it (NF-D16). The narrative pre-registration is committed at
`ablation_results/nf_w7b_preregistration.md` BEFORE the full run.

PIPELINE (one target — `dst_points`; the K side shipped in NF-W7 and is untouched):
  · the DST frame, folds and PIT gate are NF-W7's VERBATIM (`build_frames` reused);
  · the component MARGINALS are NF-W7's Layer-A score-best arms, FROZEN — asserted against the
    committed NF-W7 record before any scoring (⛔ this story adds only dependence);
  · per fold: Σ̂ estimated on TRAIN (in-sample randomized-PIT z-scores under the frozen
    marginals; a raw-Spearman variant; a one-factor variant; an attenuation-probe ×2 variant) →
    four pre-registered joint arms, assembled through the SAME exact-tier composition, sharing
    ONE base-normal block (common random numbers) with the indep + comonotone anchors;
  · gate: crps_q199 vs the best foil ∧ fold clause ∧ PBO ∧ DSR ∧ BH-FDR ∧ the coverage(80)
    floor ∧ degenerates/permutation/oracles ∧ the three DEPENDENCE clauses
    (incumbent-refusal-reproduces / knob-moves-coverage / winner-beats-indep-on-coverage).

RUN (LAPTOP — reads the S3 NFL lake read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7b_dst_joint --smoke
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7b_dst_joint
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7b_dst_joint --rewrite-report
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import cv_power  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KW  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly_joint as KWJ  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7_kdst_weekly as W7R  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)

log = logging.getLogger("nfl.fantasy.nf_w7b")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_W7_RECORD = _REPORT_DIR / "nf_w7_kdst_weekly.json"

#: The correlation pairs worth naming in the report (indices into COMPONENT_LEGS).
_NAMED_PAIRS = (("def_sacks", "pa_bucket"), ("def_int", "pa_bucket"), ("def_sacks", "def_int"),
                ("def_int", "def_fumble_rec"), ("dst_td", "def_int"))


def assert_frozen_winners_match_the_record() -> dict:
    """⛔ The frozen-marginal contract, checked against the COMMITTED NF-W7 record — a drifted
    constant would silently re-select the marginals this story promises not to touch."""
    rec = json.loads(_W7_RECORD.read_text())
    recorded = {leg: rec["winners"][leg] for leg in KWJ.COMPONENT_LEGS}
    if recorded != KWJ.FROZEN_DST_WINNERS:
        raise RuntimeError(
            f"FROZEN_DST_WINNERS drifted from the NF-W7 record: record={recorded} vs "
            f"frozen={KWJ.FROZEN_DST_WINNERS} — this story may not re-select marginals")
    return rec


# ── Per-fold engine ─────────────────────────────────────────────────────────────────────────────
def _marginal_banks(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, np.ndarray]:
    """The frozen marginals, fit on `train`, predicting `test` — count banks + the PA proba."""
    return {leg: W7R._fit_bank(leg, KWJ.FROZEN_DST_WINNERS[leg], train, test)
            for leg in KWJ.COMPONENT_LEGS}


def _split(banks: dict[str, np.ndarray]):
    return {leg: banks[leg] for leg in KWJ.COMPONENT_LEGS[:-1]}, banks["pa_bucket"]


def _sigma_pairs(corr: np.ndarray) -> dict[str, float]:
    idx = {leg: i for i, leg in enumerate(KWJ.COMPONENT_LEGS)}
    out = {f"{a}~{b}": round(float(corr[idx[a], idx[b]]), 3) for a, b in _NAMED_PAIRS}
    mask = ~np.eye(len(KWJ.COMPONENT_LEGS), dtype=bool)
    out["mean_abs_offdiag"] = round(float(np.mean(np.abs(np.asarray(corr)[mask]))), 3)
    return out


def run_fold(fold: WP.Fold, frame: pd.DataFrame) -> dict:
    t0 = time.time()
    train, test = frame.loc[fold.train_idx], frame.loc[fold.test_idx]
    y_te = test[KWJ.TARGET].to_numpy(float)
    mtrain = KW.matched_n_train(train, test)

    contexts = {"te": (train, test), "tr_in": (train, train), "or_in": (test, test),
                "mn_te": (mtrain, test), "mn_in": (mtrain, mtrain)}
    ctx = {name: _marginal_banks(tr, te) for name, (tr, te) in contexts.items()}
    cb_te, pa_te = _split(ctx["te"])
    cb_or, pa_or = _split(ctx["or_in"])
    cb_mn, pa_mn = _split(ctx["mn_te"])

    sig_tr = {arm: KWJ.sigma_for_arm(arm, ctx["tr_in"], train) for arm in KWJ.REAL_ARMS}
    sig_or = {arm: KWJ.sigma_for_arm(arm, ctx["or_in"], test) for arm in KWJ.REAL_ARMS}
    sig_mn = {arm: KWJ.sigma_for_arm(arm, ctx["mn_in"], mtrain) for arm in KWJ.REAL_ARMS}

    banks: dict[str, np.ndarray] = {}
    for arm in KWJ.REAL_ARMS:
        banks[arm] = KWJ.assembled_bank(cb_te, pa_te, corr=sig_tr[arm])
        banks[f"oracle__{arm}"] = KWJ.assembled_bank(cb_or, pa_or, corr=sig_or[arm])
        banks[f"matched_n__{arm}"] = KWJ.assembled_bank(cb_mn, pa_mn, corr=sig_mn[arm])
    banks["assembled_indep"] = KWJ.assembled_bank(cb_te, pa_te, mode="indep")
    banks["assembled_comonotone"] = KWJ.assembled_bank(cb_te, pa_te, mode="comonotone")

    # foils + their oracles + degenerates + the permuted control — NF-W7 Layer B verbatim
    banks["foil_climatology"] = KW.foil_climatology_bank(train, test, KWJ.TARGET)
    banks["foil_board_eb"] = KW.foil_board_eb_points(train, test, KWJ.TARGET, "team")
    banks["foil_direct"] = KW.fit_direct_points(train, test, KW.FEATURES_D, KWJ.TARGET)
    banks["oracle__foil_climatology"] = KW.foil_climatology_bank(test, test, KWJ.TARGET)
    banks["oracle__foil_board_eb"] = KW.foil_board_eb_points(test, test, KWJ.TARGET, "team")
    banks["oracle__foil_direct"] = KW.fit_direct_points(test, test, KW.FEATURES_D, KWJ.TARGET)
    banks["permuted_direct"] = KW.fit_direct_points(
        train, test, KW.FEATURES_D, KWJ.TARGET,
        y_train=KW.permute_within_group(train[KWJ.TARGET].to_numpy(float),
                                        train["gw"].to_numpy()))
    banks["nihilist_zero"] = np.zeros((len(test), len(KW.EVAL_LEVELS)))
    y_tr = train[KWJ.TARGET].to_numpy(float)
    y_tr = y_tr[np.isfinite(y_tr)]
    med = float(np.quantile(y_tr, 0.5))
    clim = banks["foil_climatology"]
    banks["zero_width"] = np.full_like(clim, med)
    banks["max_width"] = med + 3.0 * (clim - med)

    scores: dict[str, float] = {}
    for label, bank in banks.items():
        KW.assert_finite_predictive(bank, f"{KWJ.TARGET}/{label}")
        scores[label] = float(np.mean(KW.crps_dense(bank, y_te)))
    coverage, pit = {}, {}
    for label in (*KWJ.REAL_ARMS, "assembled_indep", "assembled_comonotone"):
        coverage[label] = KW.coverage80_dense(banks[label], y_te)
        pit[label] = KW.pit_flatness(KW.randomized_pit_from_bank(banks[label], y_te))
    log.info("[W7b] fold %s in %.1fs (train %d / test %d)",
             fold.label, time.time() - t0, len(train), len(test))
    return {"label": fold.label, "scores": scores, "coverage": coverage, "pit_flatness": pit,
            "sigma_train_pairs": {a: _sigma_pairs(sig_tr[a]) for a in KWJ.REAL_ARMS},
            "sigma_train_full": {a: np.round(sig_tr[a], 3).tolist()
                                 for a in ("joint_rankcorr", "joint_raw")},
            "n_train": int(len(train)), "n_test": int(len(test))}


# ── Selection (over the stored fold results — everything re-derivable, NF-W2e) ──────────────────
def _pooled_coverage(fold_results: list[dict], label: str) -> dict:
    covs = [fr["coverage"][label] for fr in fold_results]
    n_tot = int(sum(c["n"] for c in covs))
    cov = (sum(c["coverage"] * c["n"] for c in covs) / n_tot) if n_tot else float("nan")
    se = float(np.sqrt(KWJ.COVERAGE_FLOOR * (1 - KWJ.COVERAGE_FLOOR) / n_tot)) if n_tot else float("nan")
    return {"coverage": round(cov, 4), "n_rows": n_tot, "binomial_se": round(se, 4),
            "blocking_shortfall": bool(n_tot and (KWJ.COVERAGE_FLOOR - cov)
                                       > KWJ.COVERAGE_BLOCK_SE * se)}


def select_joint(fold_results: list[dict], n_folds: int, fold_seasons: dict[str, int]) -> dict:
    mat = pd.DataFrame({fr["label"]: fr["scores"] for fr in fold_results}).T
    mean_s = mat.mean(axis=0)
    winner = str(mean_s[list(KWJ.REAL_ARMS)].idxmin())
    best_foil = str(mean_s[list(KWJ.FOILS)].idxmin())
    deltas = (mat[best_foil] - mat[winner]).to_numpy(float)
    mean_d, lo, hi = KW.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)
    eligible = list(KWJ.ELIGIBLE)
    defl = NF18.deflate(mat[eligible], subset=eligible)
    trial_srs = []
    for arm in KWJ.REAL_ARMS:
        d = (mat[best_foil] - mat[arm]).to_numpy(float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
    pval = M14.onesided_paired_pvalue(deltas)
    perm_lift = (mat[best_foil] - mat["permuted_direct"]).to_numpy(float)
    p_perm = M14.onesided_paired_pvalue(perm_lift)
    anchors = {
        "degenerates_lose": bool(all(mean_s[d] > mean_s[winner] for d in KWJ.DEGENERATES)),
        "degenerate_detail": {d: round(float(mean_s[d]), 4) for d in KWJ.DEGENERATES},
        "winner_beats_permuted": bool(mean_s["permuted_direct"] > mean_s[winner]),
        "permuted_lift_not_significant": bool(
            float(np.nanmean(perm_lift)) <= 0 or (p_perm is not None and p_perm >= 0.05)),
        "no_arm_beats_own_oracle": bool(all(
            mean_s[a] > mean_s[KW.oracle_of(a)] for a in KWJ.REAL_ARMS)),
        "oracle_floors_respected_at_matched_n": bool(all(
            (mean_s[a] > mean_s[KW.oracle_of(a)])
            or (mean_s[KW.oracle_of(a)] < mean_s[KW.matched_n_of(a)])
            for a in KWJ.REAL_ARMS)),
        "foils_respect_own_oracle": bool(all(
            mean_s[f] > mean_s[KW.oracle_of(f)] for f in KWJ.FOILS)),
    }
    oracle_detail = {
        a: {"arm": round(float(mean_s[a]), 4),
            "own_form_oracle": round(float(mean_s[KW.oracle_of(a)]), 4),
            "matched_n": round(float(mean_s[KW.matched_n_of(a)]), 4)}
        for a in KWJ.REAL_ARMS
    }
    pooled_cov = {label: _pooled_coverage(fold_results, label)
                  for label in (*KWJ.REAL_ARMS, "assembled_indep", "assembled_comonotone")}
    cov_w = pooled_cov[winner]
    cov_i = pooled_cov["assembled_indep"]
    cov_c = pooled_cov["assembled_comonotone"]
    dependence_checks = {
        # the harness must SEE the defect it claims to fix: NF-W7's refusal (0.7603, blocking)
        # must reproduce on the re-scored independent draw (the straddle control)
        "incumbent_refusal_reproduces": bool(cov_i["blocking_shortfall"]),
        # NF-MARGIN2/NF-D20: the knob's full range must MOVE the gated statistic
        "dependence_moves_coverage": bool(cov_c["coverage"] > cov_i["coverage"]),
        # the card's requirement: the refused baseline must be beaten on coverage
        "beats_indep_on_coverage": bool(cov_w["coverage"] > cov_i["coverage"]),
    }
    reproduction = {
        "recorded_indep_crps": KWJ.NF_W7_RECORDED["assembled_crps"],
        "measured_indep_crps": round(float(mean_s["assembled_indep"]), 4),
        "recorded_indep_cov80": KWJ.NF_W7_RECORDED["assembled_cov80"],
        "measured_indep_cov80": cov_i["coverage"],
    }
    era_deltas = {lbl: round(float(dd), 4) for lbl, dd in zip(mat.index, deltas)
                  if fold_seasons.get(lbl) == KW.CAPTURE_ERA_SEASON}
    sd = float(np.nanstd(deltas, ddof=1))
    return {
        "target": KWJ.TARGET, "winner": winner, "best_foil": best_foil,
        "mean_crps": {k: round(float(v), 4) for k, v in mean_s.items()},
        "deltas_by_fold": [round(float(dd), 4) for dd in deltas],
        "mean_delta": None if mean_d is None else round(mean_d, 4),
        "ci95": [None if lo is None else round(lo, 4), None if hi is None else round(hi, 4)],
        "beats_foil": bool(np.nanmean(deltas) > 0), "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        "pbo": defl.get("pbo"), "os_gap_pct": defl.get("os_gap_pct"),
        "contender_spread_pct": defl.get("contender_spread_pct"), "flips": defl.get("flips"),
        "dsr": dsr, "p_one_sided": pval, "trial_srs": [round(t, 3) for t in trial_srs],
        "observed_sr": round(float(np.nanmean(deltas)) / sd, 3) if sd > 1e-12 else None,
        "var_trials_sr": (round(float(np.var(np.asarray(trial_srs), ddof=1)), 5)
                          if len(trial_srs) > 1 else None),
        "anchors": anchors, "oracle_detail": oracle_detail,
        "permutation_detail": {"permuted_lift_vs_foil_mean": round(float(np.nanmean(perm_lift)), 4),
                               "permuted_lift_p_one_sided": p_perm},
        "coverage": {"winner_coverage_80": cov_w["coverage"], "n_rows": cov_w["n_rows"],
                     "binomial_se": cov_w["binomial_se"],
                     "blocking_shortfall": cov_w["blocking_shortfall"]},
        "coverage_by_label": pooled_cov,
        "dependence_checks": dependence_checks,
        "nf_w7_reproduction_report_only": reproduction,
        "delta_vs_indep_crps": round(float(mean_s["assembled_indep"] - mean_s[winner]), 4),
        "pit_flatness_report_only": {
            label: [fr["pit_flatness"][label] for fr in fold_results]
            for label in (*KWJ.REAL_ARMS, "assembled_indep")},
        "sigma_report": {a: [fr["sigma_train_pairs"][a] for fr in fold_results]
                         for a in KWJ.REAL_ARMS},
        "capture_era_deltas_report_only": era_deltas,
    }


# ── Gate + classification ───────────────────────────────────────────────────────────────────────
def compose_gate_joint(sel: dict, fdr_pass: bool) -> dict:
    checks = {
        "beats_foil": bool(sel["beats_foil"]),
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < KWJ.PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= KWJ.DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "degenerates_lose": bool(sel["anchors"]["degenerates_lose"]),
        "permutation_behaves": bool(sel["anchors"]["winner_beats_permuted"]
                                    and sel["anchors"]["permuted_lift_not_significant"]),
        "oracle_floors_respected": bool(sel["anchors"]["oracle_floors_respected_at_matched_n"]),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
        **{k: bool(v) for k, v in sel["dependence_checks"].items()},
    }
    return {"checks": checks, "ship": all(checks.values())}


def classify_joint(sel: dict, checks: dict, n_folds: int) -> dict:
    v = cv_power.classify_null(
        metric="nf_w7b_dst_points_joint", n_folds=n_folds, n_arms=len(KWJ.REAL_ARMS),
        beats_foil=sel["beats_foil"], observed_sr=sel["observed_sr"],
        var_trials_sr=sel["var_trials_sr"], fold_wins=sel["fold_wins"],
        p_one_sided=sel["p_one_sided"], bh_cutoff=KWJ.FDR_Q,
        degenerates_excluded_from_v=True,
    )
    base = KW.flag_unsafe_field_shrink(
        {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger,
         "instrument_verdict": {"state": v.state, "reason": v.reason,
                                "retest_trigger": v.retest_trigger}},
        len(KWJ.REAL_ARMS))
    # NF-D18 via the SHARED branch (mechanism prose is THIS story's — the W7 default would
    # falsely blame an independence simplification the arms no longer make)
    out = KW.coverage_constraint_refusal(sel, checks, base,
                                         mechanism=KWJ.REFUSAL_MECHANISM,
                                         remedy=KWJ.REFUSAL_REMEDY)
    if out is base:
        # not a pure coverage refusal — is it an anchor/registration-clause refusal?
        stat_fail = [c for c in KWJ.STATISTICAL_CHECKS if not checks.get(c, True)]
        anchor_fail = [c for c in KWJ.ANCHOR_CHECKS if not checks.get(c, True)]
        if not stat_fail and anchor_fail:
            out = dict(base)
            out.update({
                "state": "CONSTRAINT_REFUSED", "hand_corrected": True,
                "reason": ("every statistical gate passed and the null rests entirely on "
                           f"anchor/registration clauses {anchor_fail} — more data cannot "
                           "change this verdict (NF-D18/GE.hand_classify_refusal semantics, "
                           "W7b clause set)."),
                "retest_trigger": None, "failing_anchor_checks": anchor_fail,
            })
    out["pbo_state"] = (
        "EVALUABLE — PBO is computed over the 7-config eligible field (4 joint arms + 3 foils); "
        "DSR deflates over the 4-arm declared family (trial SRs from real arms only; anchors "
        "never enter V — MH2.1 (a)).")
    out["gate_sensitivity"] = KW.gate_sensitivity(checks, waived=())
    return out


def derive_verdict_layer(out: dict) -> dict:
    """⭐ Every decision re-derivable from the stored selection — no refit (NF-W2e/W3)."""
    n_folds = out["n_folds"]
    sel = out["selection"]
    fdr = M14.bh_fdr({"dst_points_joint": sel["p_one_sided"]}, q=KWJ.FDR_Q)
    gate = compose_gate_joint(sel, fdr.get("dst_points_joint", False))
    null_state = None if gate["ship"] else classify_joint(sel, gate["checks"], n_folds)
    verdict = "SHIP" if gate["ship"] else (null_state or {}).get("state", "NULL")
    return {"fdr": fdr, "gate": gate, "null_state": null_state,
            "verdict": {KWJ.TARGET: verdict},
            "headline": f"B[{KWJ.TARGET}:{verdict} · winner {sel['winner']} · "
                        f"cov80 {sel['coverage']['winner_coverage_80']} vs floor "
                        f"{KWJ.COVERAGE_FLOOR} · indep {sel['coverage_by_label']['assembled_indep']['coverage']}]"}


# ── Report (every verdict word DERIVED at report time — NF-W2e) ─────────────────────────────────
def write_report(out: dict, path: Path) -> None:
    sel, gate = out["selection"], out["gate"]
    a: list[str] = []
    p = a.append
    p("# NF-W7b — DST dependence successor: joint/copula draw over the co-moving component legs "
      "(§0.5)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} "
      f"({out['fold_labels'][0]}…{out['fold_labels'][-1]}, the NF-W1 axis verbatim) · "
      f"**team-weeks:** {out['n_rows']} · marginals FROZEN to NF-W7's Layer-A winners "
      f"(asserted against the committed record)")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held**. This "
      "story adds ONLY a dependence structure over NF-W7's frozen component marginals; the "
      "coverage(80) floor and the three foils are NF-W7's verbatim (⛔ the floor may not move — "
      "NF-D18/E2.1-r). Every direction word is derived at report time, failing closed to `TIES` "
      "(NF-W2e).")
    p("")
    audit = out["pit_audit"]
    p(f"**PIT gate (dst):** {audit['weeks_checked']} weeks / {audit['records_checked']} records; "
      f"{audit['rows_dropped']} rows dropped fail-closed.")
    p("")
    p("## ⭐ Headline")
    p("")
    p(f"- **`dst_points` (joint draw): {out['verdict'][KWJ.TARGET]}** — winner `{sel['winner']}`")
    p(f"- coverage(80): winner **{sel['coverage']['winner_coverage_80']}** vs floor "
      f"{KWJ.COVERAGE_FLOOR} (n={sel['coverage']['n_rows']}, blocking_shortfall="
      f"{sel['coverage']['blocking_shortfall']}) · independent draw "
      f"{sel['coverage_by_label']['assembled_indep']['coverage']} (NF-W7 recorded "
      f"{KWJ.NF_W7_RECORDED['assembled_cov80']}) · comonotone "
      f"{sel['coverage_by_label']['assembled_comonotone']['coverage']}")
    p("")
    p(KW.verdict_sentence(sel["winner"], sel["best_foil"], sel["mean_delta"],
                          sel["ci95"][0], sel["ci95"][1]))
    p("")
    p(pd.DataFrame([{"label": k, "mean_crps_q199": v} for k, v in sel["mean_crps"].items()])
      .sort_values("mean_crps_q199").to_markdown(index=False, floatfmt=".4f"))
    p("")
    p(f"- fold wins {sel['fold_wins']}/{out['n_folds']} (clause requires "
      f"{sel['fold_clause']['required']}) · PBO {sel['pbo']} (7-config eligible field) · DSR "
      f"{sel['dsr']} (4-arm declared family) · p {sel['p_one_sided']} · BH "
      f"{out['fdr'].get('dst_points_joint')}")
    p(f"- anchors: {sel['anchors']}")
    p(f"- oracle floors (matched-n admission — NF-D16 (g‴)/NF1.9 (f)): {sel['oracle_detail']}")
    p(f"- permutation: {sel['permutation_detail']}")
    p(f"- coverage by label: {sel['coverage_by_label']}")
    p(f"- ⭐ dependence clauses: {sel['dependence_checks']}")
    p(f"- Δcrps vs the refused independent draw: {sel['delta_vs_indep_crps']:+.4f} (winner "
      f"minus-side positive = the joint draw also SCORES better than indep)")
    p(f"- NF-W7 reproduction (report-only): {sel['nf_w7_reproduction_report_only']}")
    p(f"- capture-era (2025) fold deltas, report-only (NF-W2d): "
      f"{sel['capture_era_deltas_report_only']}")
    p(f"- gate: {gate['checks']}")
    ns = out.get("null_state")
    if ns:
        p(f"- null state: **{ns.get('state')}** — {ns.get('reason')} Re-test: "
          f"{ns.get('retest_trigger')}")
        p(f"- instrument verdict recorded beside: {ns.get('instrument_verdict')}")
        p(f"- gate sensitivity (NF-D15 (g″)): {ns.get('gate_sensitivity')}")
    p("")
    p("## The estimated dependence structure (train-side Σ̂, per fold)")
    p("")
    p("Named pairs are latent-scale correlations under the frozen marginals (model-residual "
      "scale for `joint_rankcorr`, raw-outcome Spearman→Gaussian for `joint_raw`). A NEGATIVE "
      "sacks~PA / int~PA correlation is the co-movement the independent draw ignored: a "
      "dominant defensive day produces counting stats AND a low PA tier together.")
    p("")
    for arm in KWJ.REAL_ARMS:
        rows = sel["sigma_report"][arm]
        df = pd.DataFrame(rows, index=out["fold_labels"][:len(rows)])
        p(f"### `{arm}`")
        p("")
        p(df.to_markdown(floatfmt=".3f"))
        p("")
    p("- randomized-PIT flatness by fold (report-only, winner + indep): "
      f"{ {k: v for k, v in sel['pit_flatness_report_only'].items() if k in (sel['winner'], 'assembled_indep')} }")
    p("")
    p("## Pre-registration echo")
    p("")
    p("```json")
    p(json.dumps(out["preregistration"], indent=2, default=str))
    p("```")
    path.write_text("\n".join(a))


# ── Runner ──────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-W7b DST joint-draw successor")
    ap.add_argument("--smoke", action="store_true",
                    help="2 folds, artifacts suffixed _smoke — code-path + movability proof only")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="re-derive gates/verdicts from the stored JSON — no refit (NF-W2e)")
    args = ap.parse_args(argv)
    suffix = "_smoke" if args.smoke else ""
    json_path = _REPORT_DIR / f"nf_w7b_dst_joint{suffix}.json"

    if args.rewrite_report:
        out = json.loads(json_path.read_text())
        before = dict(out.get("verdict", {}))
        out.update(derive_verdict_layer(out))
        moved = {k: (before.get(k), v) for k, v in out["verdict"].items()
                 if before.get(k) != v}
        if moved:
            out["verdict_corrected_from"] = before
            log.warning("VERDICT MOVED on re-derivation: %s", json.dumps(moved))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        json_path.write_text(json.dumps(out, indent=2, default=float))
        write_report(out, _REPORT_DIR / f"nf_w7b_dst_joint{suffix}.md")
        print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                          "moved": moved}, indent=2))
        return 0

    t_start = time.time()
    w7_record = assert_frozen_winners_match_the_record()
    frames, pit_audits = W7R.build_frames(KW.SEASONS, rebuild_cache=args.rebuild_cache)
    frame = frames["dst"]
    folds = WP.build_folds(frame)
    if args.smoke:
        folds = folds[-2:]
    labels = [f.label for f in folds]
    n_folds = len(labels)
    fold_seasons = {f.label: f.test_season for f in folds}

    fold_results = [run_fold(f, frame) for f in folds]
    selection = select_joint(fold_results, n_folds, fold_seasons)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": KWJ.STORY, "smoke": bool(args.smoke),
        "runtime_seconds": round(time.time() - t_start, 1),
        "selection_metric": KWJ.SELECTION_METRIC,
        "n_folds": n_folds, "fold_labels": labels, "n_rows": int(len(frame)),
        "pit_audit": pit_audits["dst"],
        "frozen_marginals": dict(KWJ.FROZEN_DST_WINNERS),
        "nf_w7_record_generated_at": w7_record.get("generated_at"),
        "preregistration": {
            "story": KWJ.STORY, "target": KWJ.TARGET,
            "real_arms": list(KWJ.REAL_ARMS), "foils": list(KWJ.FOILS),
            "eligible": list(KWJ.ELIGIBLE), "anchors": list(KWJ.ANCHORS),
            "degenerates": list(KWJ.DEGENERATES),
            "component_legs": list(KWJ.COMPONENT_LEGS),
            "comonotone_flip": list(KWJ.COMONOTONE_FLIP),
            "double_scale": KWJ.DOUBLE_SCALE,
            "frozen_marginals": dict(KWJ.FROZEN_DST_WINNERS),
            "test_blocks": [list(t) for t in KW.TEST_BLOCKS], "purge_weeks": KW.PURGE_WEEKS,
            "pbo_max": KWJ.PBO_MAX, "dsr_min": KWJ.DSR_MIN, "fdr_q": KWJ.FDR_Q,
            "fdr_families": {k: list(v) for k, v in KWJ.FDR_FAMILIES.items()},
            "coverage_floor": KWJ.COVERAGE_FLOOR,
            "coverage_block_se": KWJ.COVERAGE_BLOCK_SE,
            "assembly_draws": KWJ.ASSEMBLY_DRAWS,
            "statistical_checks": list(KWJ.STATISTICAL_CHECKS),
            "anchor_checks": list(KWJ.ANCHOR_CHECKS),
            "min_estimation_rows": KWJ.MIN_ESTIMATION_ROWS,
        },
        "selection": selection,
        "fold_results": [{k: fr[k] for k in ("label", "scores", "coverage", "n_train", "n_test",
                                             "sigma_train_pairs")}
                         for fr in fold_results],
    }
    out.update(derive_verdict_layer(out))

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, default=float))
    write_report(out, _REPORT_DIR / f"nf_w7b_dst_joint{suffix}.md")
    log.info("verdict: %s (%.1fs)", out["headline"], out["runtime_seconds"])
    print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                      "dependence_checks": selection["dependence_checks"],
                      "coverage_by_label": selection["coverage_by_label"],
                      "runtime_seconds": out["runtime_seconds"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
