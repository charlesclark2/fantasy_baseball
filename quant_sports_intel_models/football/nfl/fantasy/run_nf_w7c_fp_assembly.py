"""run_nf_w7c_fp_assembly.py — NF-W7c §0.5: the arbitrary-league fantasy-point ASSEMBLY, gated on
whether the cross-stat DEPENDENCE earns its place.

Everything decidable in advance is a CONSTANT in `fp_assembly.py`; this runner READS it (NF-D16).
The narrative pre-registration is committed at `ablation_results/nf_w7c_preregistration.md` BEFORE
the full run.

PIPELINE (one target — `league_fantasy_points` under the DECLARED gate league; four positions):
  · the matrix, folds and PIT gate are NF-W6d's VERBATIM (`build_matrix_w6d` reused);
  · the per-stat MARGINALS are the NF-W6d SERVED MAP, consumed through the SERVING DISPATCH and
    NOT refit or re-selected — this story adds ONLY the dependence structure and the re-scoring;
  · per fold × position: Σ̂ estimated on TRAIN (⭐ Spearman rank correlation of RAW outcomes; a
    residual-PIT variant; a one-factor variant; an ×2 attenuation probe) → four pre-registered
    joint arms, assembled through the SAME weighted-sum scoring, sharing ONE base-normal block
    (common random numbers) with the matched INDEPENDENT foil and the comonotone degenerate;
  · gate: crps_q199 vs the best foil ∧ fold clause ∧ PBO ∧ DSR ∧ BH-FDR ∧ the coverage(80) floor
    ∧ randomized-PIT decile flatness ∧ degenerates/permutation/oracles ∧ the three DEPENDENCE
    clauses (independence-under-disperses / knob-moves-coverage / winner-beats-indep-on-coverage).

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: writes LOCAL artifacts only — no
`--publish`, no S3 client, no boto3, no dbt, no Dagster.

RUN (OPERATOR — LAPTOP; reads the S3 NFL lake read-only, writes local artifacts):

    # path proof: 1 fold, short train window, few draws (seconds-to-minutes; artifact _smoke)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7c_fp_assembly --smoke

    # the full run (>2 min — OPERATOR)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7c_fp_assembly

    # re-derive every verdict from the stored fold scores at ZERO refit cost (NF-W2e/W3)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7c_fp_assembly --rewrite-report
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
from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KW  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import league_presets as LP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w6d_ceiling_gate as W6DA,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w6d_serve_stat_distributions as W6DS,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    stat_distribution_serving_d as SDSD,
)
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions_d as SDD  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_w7c")

SEASONS = W6DA.SEASONS
FEATURES = list(WP.FEATURES)

#: ⭐ THE DECLARED GATE LEAGUE — one league gates, so the field is not multiplied by format. Full
#: PPR is the substrate's own convention (`SD.PPR_WEIGHTS`) and the modal real league. The other
#: presets are re-scored REPORT-ONLY, which is what demonstrates league-generality without
#: buying a multiplicity penalty for it.
GATE_LEAGUE = "full_ppr"
REPORT_LEAGUES: tuple[str, ...] = ("standard", "half_ppr", "te_premium")

#: ⭐ The artifact path is the SERVING module's own constant, not a second copy — the reader
#: (`FA.certified_arms`) and the writer must never be able to drift onto different files.
_ARTIFACT_REL = FA.RECORD_RELPATH


# ── Frame + marginals ───────────────────────────────────────────────────────────────────────────
def realized_matrix(df: pd.DataFrame) -> np.ndarray:
    """(n, 13) realized stat lines in `FA.LEGS` order — the labels the assembly is scored against,
    read through `SDD._y` so the attach conventions are the substrate's, never re-derived."""
    return np.column_stack([SDD._y(df, leg) for leg in FA.LEGS]).astype(float)


def bank_tensor(banks: dict[str, np.ndarray], position: str, n_rows: int) -> np.ndarray:
    """The served per-cell banks re-shaped to (n, 13, 199) for one position, in `FA.LEGS` order."""
    out = np.empty((n_rows, FA.N_LEGS, FA.N_LEVELS), dtype=float)
    for i, leg in enumerate(FA.LEGS):
        cell = f"{position}|{leg}"
        b = np.asarray(banks[cell], dtype=float)
        if b.shape != (n_rows, FA.N_LEVELS):
            raise ValueError(f"{cell}: bank is {b.shape}, expected ({n_rows}, {FA.N_LEVELS})")
        out[:, i, :] = np.sort(b, axis=1)
    return out


def _marginals(train: pd.DataFrame, serve: pd.DataFrame, smap: dict) -> dict[str, np.ndarray]:
    """One `serve_banks` call gives every cell for every position (the dispatch fits per
    form×stat, then slices) — ⛔ the SERVING dispatch, so the assembly can never consume a
    marginal the served substrate would not."""
    banks, _notes = SDSD.serve_banks(train, serve, smap)
    return banks


# ── One fold × position ─────────────────────────────────────────────────────────────────────────
def run_position(position: str, train: pd.DataFrame, test: pd.DataFrame, smap: dict,
                 weights: np.ndarray, *, draws: int) -> dict:
    tr_p = train.loc[train["position"].astype(str) == position].reset_index(drop=True)
    te_p = test.loc[test["position"].astype(str) == position].reset_index(drop=True)
    if len(te_p) == 0 or len(tr_p) < FA.MIN_ESTIMATION_ROWS:
        return {"skipped": f"train {len(tr_p)} / test {len(te_p)} rows — below the estimation "
                           f"floor ({FA.MIN_ESTIMATION_ROWS}); REFUSED, not defaulted"}
    # ⭐⭐ THE ORACLE PEEKS AT THE DEPENDENCE, AND AT NOTHING ELSE.
    #
    # Every arm in this story differs from every other ONLY in Σ — the per-stat marginals are the
    # NF-W6d served map, frozen and shared by every arm, every foil and every anchor. So the
    # peeking ceiling for a dependence arm is "Σ estimated on the TEST outcomes, same marginals",
    # NOT "refit everything on test": an oracle that also refits marginals is a DIFFERENT FAMILY
    # (NF1.7 (b) — same-family AND same-sample), and it would confound peeking-at-dependence with
    # peeking-at-marginals, so a floor violation could not be attributed to either.
    #
    # A first cut did refit the marginals on test (`serve_banks(test, test)`), inheriting NF-W7b's
    # shape. It CRASHED, and the crash was the design telling on itself: the W6d forms need a
    # temporal core/purge/cal split (`MC.calibration_split`), and a single half-season test block
    # cannot be split that way — `core=0 cal=4380`. Peeking at the marginals was never the
    # intent; removing it fixes the crash, tightens the floor onto the channel this story owns,
    # and drops three of the five marginal fits per position.
    ctx_te = _marginals(train, test, smap)          # the real arms' marginals (train → test)
    ctx_tr = _marginals(train, train, smap)         # in-sample train predictives (joint_pit's Σ)
    b_te = bank_tensor(ctx_te, position, len(te_p))
    b_tr = bank_tensor(ctx_tr, position, len(tr_p))

    raw_tr = realized_matrix(tr_p)
    raw_te = realized_matrix(te_p)
    y_te = FA.score_realized(raw_te, weights)

    # The matched-n control (NF1.9 (f)): Σ estimated on a TRAIN slice the size of the test block —
    # same family, same sample size, same marginals. It is a ROW SUBSET of the train context, so
    # it costs no additional fit.
    n_match = max(len(te_p), FA.MIN_ESTIMATION_ROWS)
    order = np.argsort(tr_p["gw"].to_numpy(), kind="stable")
    m_idx = np.sort(order[-n_match:])
    if len(m_idx) < FA.MIN_ESTIMATION_ROWS:
        return {"skipped": f"the matched-n control carries {len(m_idx)} {position} rows, below the "
                           f"estimation floor ({FA.MIN_ESTIMATION_ROWS}) — the per-form oracle "
                           f"floor could not be evaluated at matched n, so this fold is REFUSED "
                           f"rather than scored against an anchor that did not run (NF1.7 (a))"}

    # ── Σ per arm × estimation context (marginals identical throughout — only Σ moves) ──────────
    sig_tr, sig_or, sig_mn, notes = {}, {}, {}, {}
    for arm in FA.REAL_ARMS:
        sig_tr[arm], notes[arm] = FA.sigma_for_arm(arm, raw=raw_tr, banks=b_tr, realized=raw_tr)
        sig_or[arm], _ = FA.sigma_for_arm(arm, raw=raw_te, banks=b_te, realized=raw_te)
        sig_mn[arm], _ = FA.sigma_for_arm(arm, raw=raw_tr[m_idx], banks=b_tr[m_idx],
                                          realized=raw_tr[m_idx])

    # ── arms, foils, anchors — ONE base-normal stream shared by all (common random numbers) ─────
    banks: dict[str, np.ndarray] = {}
    for arm in FA.REAL_ARMS:
        banks[arm] = FA.assemble_fp_bank(b_te, weights, corr=sig_tr[arm], draws=draws)
        banks[f"oracle__{arm}"] = FA.assemble_fp_bank(b_te, weights, corr=sig_or[arm], draws=draws)
        banks[f"matched_n__{arm}"] = FA.assemble_fp_bank(b_te, weights, corr=sig_mn[arm],
                                                         draws=draws)
    # ⛔ `assembled_indep` gets NO oracle, deliberately: it estimates NOTHING, so there is nothing
    # for a peek to improve — its oracle would be byte-identical to itself. A fabricated anchor
    # that cannot differ from its arm is décor, and reporting it as "respected" would be a pass on
    # nothing (NF1.9's "a mechanism that cannot act is a finding", NF1.7 (a)).
    banks["assembled_indep"] = FA.assemble_fp_bank(b_te, weights, mode="indep", draws=draws)
    banks["assembled_comonotone"] = FA.assemble_fp_bank(b_te, weights, mode="comonotone",
                                                        draws=draws)

    # the direct-learned foil: a learner pointed straight at league points (does assembling from
    # per-stat parts beat modelling the total?) + its own-form oracle + the permutation control
    tr_p = tr_p.copy()
    te_p = te_p.copy()
    tr_p[FA.TARGET] = FA.score_realized(raw_tr, weights)
    te_p[FA.TARGET] = y_te
    banks["foil_direct_points"] = KW.fit_direct_points(tr_p, te_p, FEATURES, FA.TARGET)
    banks["oracle__foil_direct_points"] = KW.fit_direct_points(te_p, te_p, FEATURES, FA.TARGET)
    banks["permuted_direct"] = KW.fit_direct_points(
        tr_p, te_p, FEATURES, FA.TARGET,
        y_train=KW.permute_within_group(tr_p[FA.TARGET].to_numpy(float),
                                        tr_p["gw"].to_numpy()))

    # degenerates — SCORED, never reasoned about (NF1.8 / NF-D14)
    med = float(np.quantile(tr_p[FA.TARGET].to_numpy(float), 0.5))
    clim = np.quantile(tr_p[FA.TARGET].to_numpy(float), FA.EVAL_LEVELS)[None, :] \
        * np.ones((len(te_p), 1))
    banks["nihilist_zero"] = np.zeros((len(te_p), FA.N_LEVELS))
    banks["zero_width"] = np.full_like(clim, med)
    banks["max_width"] = med + 3.0 * (clim - med)

    scores: dict[str, float] = {}
    for label, bank in banks.items():
        KW.assert_finite_predictive(bank, f"{position}/{label}")
        scores[label] = float(np.mean(KW.crps_dense(bank, y_te)))
    watched = (*FA.REAL_ARMS, *FA.FOILS, "assembled_comonotone")
    coverage = {lab: KW.coverage80_dense(banks[lab], y_te) for lab in watched}
    pit = {lab: KW.pit_flatness(KW.randomized_pit_from_bank(banks[lab], y_te)) for lab in watched}

    # the ANALYTIC movability half, recorded beside the measured one
    an_sd = {lab: round(float(np.mean(FA.assembled_sum_sd(b_te, weights, sig))), 3)
             for lab, sig in (("indep", np.eye(FA.N_LEGS)),
                              (FA.PRIMARY_ARM, sig_tr[FA.PRIMARY_ARM]))}
    return {
        "scores": scores, "coverage": coverage, "pit_flatness": pit,
        "n_train": int(len(tr_p)), "n_test": int(len(te_p)),
        "sigma_notes": {a: notes[a] for a in FA.REAL_ARMS},
        "sigma_mean_abs_offdiag": {
            a: round(float(np.abs(sig_tr[a][~np.eye(FA.N_LEGS, dtype=bool)]).mean()), 4)
            for a in FA.REAL_ARMS},
        "analytic_sum_sd": an_sd,
    }


def run_fold(fold: WP.Fold, feat: pd.DataFrame, smap: dict, *, draws: int) -> dict:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    cfg = LP.get_preset(GATE_LEAGUE)
    out: dict[str, dict] = {}
    for position in FA.POSITIONS:
        FA.assert_assembly_is_priceable(cfg, position)      # fail-closed on an unmodeled term
        t_p = time.time()
        out[position] = run_position(position, train, test, smap,
                                     FA.leg_weights(cfg, position), draws=draws)
        log.info("[W7c] fold %s %s in %.1fs", fold.label, position, time.time() - t_p)
    log.info("[W7c] fold %s complete in %.1fs", fold.label, time.time() - t0)
    return {"label": fold.label, "n_test": int(len(test)), "positions": out}


# ── Selection (derived from stored fold scores — NF-W2e: zero refit cost) ────────────────────────
def _pooled_coverage(fold_results: list[dict], position: str, label: str) -> dict:
    rows = [fr["positions"][position]["coverage"][label] for fr in fold_results
            if not fr["positions"][position].get("skipped")]
    n_tot = int(sum(r["n"] for r in rows))
    if not n_tot:
        return {"coverage": None, "n_rows": 0, "binomial_se": None, "blocking_shortfall": False}
    cov = sum(r["coverage"] * r["n"] for r in rows) / n_tot
    se = float(np.sqrt(FA.COVERAGE_FLOOR * (1 - FA.COVERAGE_FLOOR) / n_tot))
    return {"coverage": round(float(cov), 4), "n_rows": n_tot, "binomial_se": round(se, 4),
            "blocking_shortfall": bool((FA.COVERAGE_FLOOR - cov) > FA.COVERAGE_BLOCK_SE * se)}


def select_position(fold_results: list[dict], position: str) -> dict | None:
    usable = [fr for fr in fold_results if not fr["positions"][position].get("skipped")]
    if len(usable) < 2:
        return None
    mat = pd.DataFrame({fr["label"]: fr["positions"][position]["scores"] for fr in usable}).T
    mean_s = mat.mean(axis=0)
    winner = str(mean_s[list(FA.REAL_ARMS)].idxmin())
    best_foil = str(mean_s[list(FA.FOILS)].idxmin())
    deltas = (mat[best_foil] - mat[winner]).to_numpy(float)
    mean_d, lo, hi = KW.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(len(usable))
    defl = NF18.deflate(mat[list(FA.ELIGIBLE)], subset=list(FA.ELIGIBLE))
    trial_srs = []
    for arm in FA.REAL_ARMS:
        d = (mat[best_foil] - mat[arm]).to_numpy(float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
    pval = M14.onesided_paired_pvalue(deltas)
    perm_lift = (mat[best_foil] - mat["permuted_direct"]).to_numpy(float)
    p_perm = M14.onesided_paired_pvalue(perm_lift)
    sd = float(np.nanstd(deltas, ddof=1))

    anchors = {
        "degenerates_lose": bool(all(mean_s[d] > mean_s[winner] for d in FA.DEGENERATES)),
        "degenerate_detail": {d: round(float(mean_s[d]), 4) for d in FA.DEGENERATES},
        "winner_beats_permuted": bool(mean_s["permuted_direct"] > mean_s[winner]),
        "permuted_lift_not_significant": bool(
            float(np.nanmean(perm_lift)) <= 0 or (p_perm is not None and p_perm >= 0.05)),
        # NF-D16 (g‴): each arm floored by the peeking version of ITS OWN form — the joint arms
        # NEST one another (Σ=I ⊂ one-factor ⊂ full), so one field-wide ceiling would veto a
        # legitimately-better nested form as a false metric inversion.
        "oracle_floors_respected_at_matched_n": bool(all(
            (mean_s[a] > mean_s[f"oracle__{a}"])
            or (mean_s[f"oracle__{a}"] < mean_s[f"matched_n__{a}"])
            for a in FA.REAL_ARMS)),
        # only the foils that HAVE an oracle — `assembled_indep` estimates nothing, so it has
        # none, and inventing one would score a pass on nothing (NF1.7 (a))
        "foils_respect_own_oracle": bool(all(
            mean_s[f] > mean_s[f"oracle__{f}"] for f in FA.FOILS_WITH_ORACLE)),
    }
    pooled_cov = {lab: _pooled_coverage(fold_results, position, lab)
                  for lab in (*FA.REAL_ARMS, *FA.FOILS, "assembled_comonotone")}
    cov_w, cov_i = pooled_cov[winner], pooled_cov["assembled_indep"]
    cov_c = pooled_cov["assembled_comonotone"]
    pit_w = float(np.mean([fr["positions"][position]["pit_flatness"][winner]["max_decile_dev"]
                           for fr in usable]))
    dependence_checks = {
        # ⭐ the DECLARED simplification must be shown FIRING on this population — the harness
        # has to SEE the defect it claims to fix (NF-W7b's straddle control)
        "independence_under_disperses": bool(cov_i["coverage"] is not None
                                             and cov_i["coverage"] < cov_c["coverage"]),
        # NF-MARGIN2 / NF-D20 — the knob's full range must MOVE the gated statistic
        "dependence_moves_coverage": bool(cov_c["coverage"] > cov_i["coverage"]),
        # the card's binding requirement: correlation must EARN its place on coverage too
        "beats_indep_on_coverage": bool(cov_w["coverage"] > cov_i["coverage"]),
    }
    return {
        "position": position, "winner": winner, "best_foil": best_foil,
        "n_folds_used": len(usable),
        "mean_crps": {k: round(float(v), 4) for k, v in mean_s.items()},
        "deltas_by_fold": [round(float(d), 4) for d in deltas],
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
        "anchors": anchors,
        "oracle_detail": {a: {"arm": round(float(mean_s[a]), 4),
                              "own_form_oracle": round(float(mean_s[f"oracle__{a}"]), 4),
                              "matched_n": round(float(mean_s[f"matched_n__{a}"]), 4)}
                          for a in FA.REAL_ARMS},
        "permutation_detail": {"permuted_lift_vs_foil_mean": round(float(np.nanmean(perm_lift)), 4),
                               "permuted_lift_p_one_sided": p_perm},
        "coverage": {"winner_coverage_80": cov_w["coverage"], "n_rows": cov_w["n_rows"],
                     "binomial_se": cov_w["binomial_se"],
                     "blocking_shortfall": cov_w["blocking_shortfall"]},
        "coverage_by_label": pooled_cov,
        "pit_flatness_winner_max_decile_dev": round(pit_w, 4),
        "pit_flat_ok": bool(pit_w <= FA.PIT_MAX_DECILE_DEV),
        "dependence_checks": dependence_checks,
        "delta_vs_indep_crps": round(float(mean_s["assembled_indep"] - mean_s[winner]), 4),
        "sigma_mean_abs_offdiag": {a: [fr["positions"][position]["sigma_mean_abs_offdiag"][a]
                                       for fr in usable] for a in FA.REAL_ARMS},
        "analytic_sum_sd": [fr["positions"][position]["analytic_sum_sd"] for fr in usable],
    }


def compose_gate(sel: dict, fdr_pass: bool) -> dict:
    checks = {
        "beats_foil": bool(sel["beats_foil"]),
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < FA.PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= FA.DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
        "pit_flat_ok": bool(sel["pit_flat_ok"]),
        "degenerates_lose": bool(sel["anchors"]["degenerates_lose"]),
        "permutation_behaves": bool(sel["anchors"]["winner_beats_permuted"]
                                    and sel["anchors"]["permuted_lift_not_significant"]),
        "oracle_floors_respected": bool(sel["anchors"]["oracle_floors_respected_at_matched_n"]),
        **{k: bool(v) for k, v in sel["dependence_checks"].items()},
    }
    return {"checks": checks, "ship": all(checks.values())}


def classify(sel: dict, checks: dict) -> dict:
    v = cv_power.classify_null(
        metric=f"nf_w7c_fp_assembly|{sel['position']}", n_folds=sel["n_folds_used"],
        n_arms=len(FA.REAL_ARMS), beats_foil=sel["beats_foil"],
        observed_sr=sel["observed_sr"], var_trials_sr=sel["var_trials_sr"],
        fold_wins=sel["fold_wins"], p_one_sided=sel["p_one_sided"], bh_cutoff=FA.FDR_Q,
        degenerates_excluded_from_v=True,
        # MH2.7: the declared field is the pre-registered arm count — the instrument then REFUSES
        # to prescribe a smaller one (a "trim the field" remedy IS the selection bias DSR deflates)
        declared_field_size=len(FA.REAL_ARMS),
    )
    base = KW.flag_unsafe_field_shrink(
        {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger,
         "field_remedy_admissible": getattr(v, "field_remedy_admissible", None),
         "instrument_verdict": {"state": v.state, "reason": v.reason,
                                "retest_trigger": v.retest_trigger}},
        len(FA.REAL_ARMS))
    out = KW.coverage_constraint_refusal(sel, checks, base, mechanism=FA.REFUSAL_MECHANISM,
                                         remedy=FA.REFUSAL_REMEDY)
    if out is base:
        stat_fail = [c for c in FA.STATISTICAL_CHECKS if not checks.get(c, True)]
        anchor_fail = [c for c in FA.ANCHOR_CHECKS if not checks.get(c, True)]
        if not stat_fail and anchor_fail:
            out = dict(base)
            out.update({
                "state": "CONSTRAINT_REFUSED", "hand_corrected": True,
                "reason": ("every statistical gate passed and the null rests entirely on "
                           f"anchor/registration clauses {anchor_fail} — more data cannot change "
                           "this verdict (NF-D18); the remedy is a different mechanism or a PM "
                           "decision, never more seasons."),
                "retest_trigger": None, "failing_anchor_checks": anchor_fail,
            })
    out["pbo_state"] = (
        f"EVALUABLE — PBO over the {len(FA.ELIGIBLE)}-config eligible field "
        f"({len(FA.REAL_ARMS)} joint arms + {len(FA.FOILS)} foils); DSR deflates over the "
        f"{len(FA.REAL_ARMS)}-arm declared family (trial SRs from real arms only; anchors and "
        f"degenerates never enter V — MH2.1 (a) / DSR-CONV).")
    out["gate_sensitivity"] = KW.gate_sensitivity(checks, waived=())
    return out


def derive_verdict_layer(out: dict) -> dict:
    """⭐ Every decision re-derivable from the stored fold scores — no refit (NF-W2e / NF-W3)."""
    frs = out["fold_results"]
    sels = {p: select_position(frs, p) for p in FA.POSITIONS}
    present = {p: s for p, s in sels.items() if s is not None}
    fdr = M14.bh_fdr({f"fp|{p}": s["p_one_sided"] for p, s in present.items()}, q=FA.FDR_Q)
    gates = {p: compose_gate(s, fdr.get(f"fp|{p}", False)) for p, s in present.items()}
    nulls = {p: (None if gates[p]["ship"] else classify(present[p], gates[p]["checks"]))
             for p in present}
    ship = sorted(p for p in present if gates[p]["ship"])
    out["selections"] = present
    out["unavailable_positions"] = sorted(set(FA.POSITIONS) - set(present))
    out["fdr"] = fdr
    out["gates"] = gates
    out["null_states"] = {p: n for p, n in nulls.items() if n}
    out["verdict"] = {
        "story_verdict": "SHIP" if ship else "NULL",
        "ship_positions": ship,
        "null_positions": {p: nulls[p]["state"] for p in present if nulls[p]},
        "gate_league": GATE_LEAGUE,
        "declared_field_size": len(FA.REAL_ARMS),
        "promote_blockers": list(FA.PROMOTE_BLOCKERS),
    }
    return out


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:
    v = out["verdict"]
    L = [f"# NF-W7c — arbitrary-league fantasy-point assembly ({v['story_verdict']})", "",
         f"Generated {out['generated_at']} · gate league **{GATE_LEAGUE}** · "
         f"{out['n_folds']} folds · target `{FA.TARGET}` · metric `{FA.SELECTION_METRIC}`", "",
         "⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record "
         "promotes nothing and publishes nothing.", "",
         "## Verdict", "",
         f"- ship positions: **{v['ship_positions'] or 'none'}**",
         f"- null positions: {v['null_positions'] or 'none'}",
         f"- unavailable: {out['unavailable_positions'] or 'none'}", ""]
    L += ["## Per position", "",
          "| pos | winner | best foil | Δ CRPS vs foil | CI95 | folds | cov80 | "
          "cov80 indep | PIT dev | PBO | DSR | gate |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for p, s in out["selections"].items():
        g = out["gates"][p]
        ci = s["ci95"]
        L.append(
            f"| {p} | `{s['winner']}` | `{s['best_foil']}` | {s['mean_delta']:+.4f} | "
            f"[{ci[0]}, {ci[1]}] | {s['fold_wins']}/{s['n_folds_used']} | "
            f"{s['coverage']['winner_coverage_80']} | "
            f"{s['coverage_by_label']['assembled_indep']['coverage']} | "
            f"{s['pit_flatness_winner_max_decile_dev']} | {s['pbo']} | {s['dsr']} | "
            f"{'SHIP' if g['ship'] else 'NULL'} |")
    L += ["", "## Did correlation earn its place?", "",
          "| pos | Δ CRPS vs the matched INDEPENDENT foil | independence under-disperses | "
          "knob moves coverage | winner beats indep on coverage |", "|---|---|---|---|---|"]
    for p, s in out["selections"].items():
        d = s["dependence_checks"]
        L.append(f"| {p} | {s['delta_vs_indep_crps']:+.4f} | {d['independence_under_disperses']} | "
                 f"{d['dependence_moves_coverage']} | {d['beats_indep_on_coverage']} |")
    L += ["", "## Gate clauses", ""]
    for p, g in out["gates"].items():
        fails = [k for k, ok in g["checks"].items() if not ok]
        L.append(f"- **{p}** — {'all clauses green' if not fails else 'FAILING: ' + ', '.join(fails)}")
        if p in out.get("null_states", {}):
            n = out["null_states"][p]
            L.append(f"  - null state `{n['state']}` — {n['reason']}")
            L.append(f"  - re-test trigger: {n.get('retest_trigger') or 'NONE'}")
    L += ["", "## Anchors (all SCORED, never reasoned about)", ""]
    for p, s in out["selections"].items():
        L.append(f"- **{p}** degenerates {s['anchors']['degenerate_detail']} vs winner "
                 f"{s['mean_crps'][s['winner']]}")
        L.append(f"  - per-form oracle floors (NF-D16 g‴): {s['oracle_detail']}")
    L += ["", "## Promote blockers", ""] + [f"- {b}" for b in v["promote_blockers"]] + [""]
    path.write_text("\n".join(L))


# ── Orchestration ───────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-W7c — arbitrary-league FP assembly (§0.5)")
    ap.add_argument("--smoke", action="store_true",
                    help="path proof: 1 fold, short train window, few draws (artifact _smoke)")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="re-derive every verdict from the stored fold scores (zero refit)")
    ap.add_argument("--rebuild-cache", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    suffix = "_smoke" if args.smoke else ""
    art = _PROJECT_ROOT / _ARTIFACT_REL.replace(".json", f"{suffix}.json")

    if args.rewrite_report:
        out = derive_verdict_layer(json.loads(art.read_text()))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat()
        art.write_text(json.dumps(out, indent=2, default=str))
        write_report(out, art.with_suffix(".md"))
        log.info("NF-W7c report re-derived → %s", art.name)
        return 0

    FA.assert_stat_key_map()
    feat, pit_audit, attach = W6DA.build_matrix_w6d(SEASONS, rebuild_cache=args.rebuild_cache)
    # ⭐ ALWAYS the FULL W6d records — never the `_smoke` variants, even on a smoke run.
    # `suffix` names THIS story's OWN artifact (mine is the path proof); the W6d records are an
    # INPUT DEPENDENCY that is already committed and decision-grade. Letting one variable do both
    # jobs made `--smoke` demand a `nf_w6d_defaults_smoke.json` that has never existed (W6d's
    # Phase-C smoke was only ever run `--only-two-pt`), and — worse — it passed
    # `allow_path_proof=True`, which would have let a PATH PROOF feed the assembly's served map.
    # Reading the real records is both the working path and the stricter one: no path-proof record
    # can reach this story at all, so the fail-closed contract is never relaxed for convenience.
    gate_p, bake_p, def_p = W6DS.record_paths("")
    smap = SDSD.served_map(gate_p, bake_p, def_p)
    folds = WP.build_folds(feat)
    if args.smoke:
        folds = folds[-1:]
    draws = 300 if args.smoke else FA.ASSEMBLY_DRAWS
    log.info("NF-W7c: %d folds × %d positions, %d legs, %d draws%s",
             len(folds), len(FA.POSITIONS), FA.N_LEGS, draws, " [SMOKE]" if args.smoke else "")

    t0 = time.time()
    fold_results = [run_fold(f, feat, smap, draws=draws) for f in folds]
    out = {
        "story": FA.STORY, "phase": "assembly", "smoke": bool(args.smoke),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seasons": list(SEASONS), "n_folds": len(folds), "gate_league": GATE_LEAGUE,
        "report_leagues_report_only": list(REPORT_LEAGUES),
        "matrix_key": W6DA.w6d_matrix_key(SEASONS), "pit_audit": pit_audit,
        "attach_audit": attach, "served_map_sources": {c: v["source"] for c, v in smap.items()},
        "assembly_draws": draws, "row_block": FA.ROW_BLOCK, "seed": FA._SEED,
        "declared_field": {"real_arms": list(FA.REAL_ARMS), "foils": list(FA.FOILS),
                           "degenerates": list(FA.DEGENERATES), "anchors": list(FA.ANCHORS)},
        "labelling": {p: FA.assembled_labelling(smap, LP.get_preset(GATE_LEAGUE), p)
                      for p in FA.POSITIONS},
        "fold_results": fold_results, "runtime_seconds": round(time.time() - t0, 1),
    }
    out = derive_verdict_layer(out)
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(json.dumps(out, indent=2, default=str))
    write_report(out, art.with_suffix(".md"))
    log.info("NF-W7c %s → %s (%.1fs)", out["verdict"]["story_verdict"], art.name,
             out["runtime_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
