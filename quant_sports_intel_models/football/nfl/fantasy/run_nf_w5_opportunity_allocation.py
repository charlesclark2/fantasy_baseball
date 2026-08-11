"""run_nf_w5_opportunity_allocation.py — NF-W5 §0.5 bake-off on the JOINT gate: does the
correlation structure of same-team opportunity allocation carry value the marginal per-player
gate is structurally blind to — and ⭐ is the joint-allocation CEILING large enough to justify
NF-W8 (the simulator)? That decision is this story's deliverable.

Everything decidable in advance lives as a CONSTANT in `opportunity_allocation.py`; this runner
READS it (the NF-D16 discipline). The narrative pre-registration is committed at
`ablation_results/nf_w5_preregistration.md` BEFORE the full run.

PIPELINE
  MATRIX: the NF-W2d two-era matrix through the W2d assembly boundary (provenance + the NF-W0a
  PIT gate). NF-W5 introduces NO new source, NO new features, NO play-by-play join.

  MARGINALS: the injury-aware champion (the NF-W2b/W2d certified per-position winners, pinned to
  the committed W2d artifact), refit per fold; every construction shares byte-identical marginal
  quantile banks and differs ONLY in the copula (the Sklar split — the dead LEVEL channels are
  excluded by construction, asserted numerically per fold).

  THE JOINT GATE: team-week vectors scored by sample-based team-total CRPS (primary), energy
  score + variogram score (co-reported), S=512 draws under common random numbers. 4 copula arms +
  2 foils + anchors (incl. ⭐ ONE PEEKING ORACLE PER PARAMETRIZED FORM, fit on the TEST fold's
  PITs — the CEILING, scored and logged FIRST, every fold).

RUN (LAPTOP — reads the S3 NFL lake read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w5_opportunity_allocation --smoke
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w5_opportunity_allocation
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w5_opportunity_allocation --rewrite-report
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import cv_power  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import availability_mixture as AV  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import opportunity_allocation as OA  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2 as W2  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2d as W2D  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
# ⭐ the matrix build, the incumbent pin, the two-family FDR composer and the capture-era fold
# list are IMPORTED from the stories that shipped them, never re-implemented (NF-W2d discipline).
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w2d_2025_regate import (  # noqa: E402
    build_matrix_w2d,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w3_game_environment import (  # noqa: E402
    fdr_two_families,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w4_availability_bakeoff import (  # noqa: E402
    CAPTURE_ERA_FOLDS,
    assert_incumbents_match_the_w2d_artifact,
)

log = logging.getLogger("nfl.fantasy.nf_w5")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
SEASONS = (2016, 2025)


# ── The champion marginal bank (per position, the certified incumbent form) ─────────────────────
def champion_qmat(train: pd.DataFrame, predict_on: pd.DataFrame) -> np.ndarray:
    """One 39-level quantile bank per row of `predict_on`, under each position's certified
    incumbent form. One fitting pass serves train-side (in-sample, for copula fitting — declared)
    and test-side (honest OOS) predictions."""
    full = list(W2D.FEATURES_W2D)
    rate = list(W2D.FEATURES_BASE_RATE_W2D)
    p0_full, cond_full = W2.hurdle_parts(train, predict_on, full, full)
    _, cond_rate = W2.hurdle_parts(train, predict_on, full, rate)
    q_forms = {
        "inj_both": W2.mix_parts(p0_full, cond_full),
        "inj_zero_leg": W2.mix_parts(p0_full, cond_rate),
    }
    pos_arr = predict_on["position"].to_numpy(dtype=object)
    out = np.empty((len(predict_on), len(WP.Q_LEVELS)))
    for pos in WP.POSITIONS:
        sel = pos_arr == pos
        out[sel] = q_forms[AV.INCUMBENT_OF_POSITION[pos]][sel]
    return out


def _digest_paircorr(paircorr: dict) -> dict:
    return {f"{k[0]}|{k[1]}": {kk: (round(vv, 5) if isinstance(vv, float) else vv)
                               for kk, vv in d.items()}
            for k, d in sorted(paircorr.items())}


# ── One fold on the joint gate ──────────────────────────────────────────────────────────────────
def run_joint_fold(fold: WP.Fold, feat: pd.DataFrame) -> dict:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    both = pd.concat([train, test])
    champ = champion_qmat(train, both)
    n_tr = len(train)
    champ_train, champ_test = champ[:n_tr], champ[n_tr:]
    champ_test_sorted = np.sort(champ_test, axis=1)

    pit_rng = np.random.default_rng(
        np.random.SeedSequence([OA._SEED, zlib.crc32(fold.label.encode()), 1]))
    pf_train = OA.pit_frame(train, champ_train, pit_rng)
    pf_test = OA.pit_frame(test, champ_test, pit_rng)

    pair_tr = OA.fit_pair_correlations(pf_train)
    pair_te = OA.fit_pair_correlations(pf_test)
    pf_matched = OA.matched_n_pit(pf_train, len(pf_test))
    pair_mn = OA.fit_pair_correlations(pf_matched)
    pair_shuf = OA.fit_pair_correlations(OA.shuffle_teams_within_week(pf_train))

    params: dict[str, object] = {
        "independence": None,
        "comonotonic": None,
        "constant_rho": OA.fit_constant_rho(pair_tr),
        "gauss_pos_factor": OA.fit_factor_loadings(pair_tr),
        "gauss_pos_pairwise": pair_tr,
        "dirichlet_alloc": OA.fit_dirichlet_params(pf_train, pair_tr),
        "empirical_role_resample": OA.fit_empirical_bank(pf_train),
        "shuffled_teams": pair_shuf,
        # ⭐ the peeking oracles — every parametrized form re-fit on the TEST fold's PITs
        # (NF-D16 (g‴); the empirical form is leave-one-out at sample time).
        OA.oracle_of("constant_rho"): OA.fit_constant_rho(pair_te),
        OA.oracle_of("gauss_pos_factor"): OA.fit_factor_loadings(pair_te),
        OA.oracle_of("gauss_pos_pairwise"): pair_te,
        OA.oracle_of("dirichlet_alloc"): OA.fit_dirichlet_params(pf_test, pair_te),
        OA.oracle_of("empirical_role_resample"): OA.fit_empirical_bank(pf_test),
        # NF1.9 (f): the same forms at the oracle's sample scale — the capacity controls.
        OA.matched_n_of("gauss_pos_factor"): OA.fit_factor_loadings(pair_mn),
        OA.matched_n_of("gauss_pos_pairwise"): pair_mn,
        OA.matched_n_of("dirichlet_alloc"): OA.fit_dirichlet_params(pf_matched, pair_mn),
        OA.matched_n_of("empirical_role_resample"): OA.fit_empirical_bank(pf_matched),
    }

    groups, excl = OA.build_team_weeks(test)
    labels = OA.all_labels()
    y_all = test["fantasy_points"].to_numpy(dtype=float)
    metric_sums = {lab: dict.fromkeys(OA.ALL_METRICS, 0.0) for lab in labels}
    inside = dict.fromkeys(labels, 0)
    marg = dict.fromkeys(labels, 0.0)
    marg_rows = 0

    for g in groups:
        rows = g["rows"]
        y = y_all[rows]
        qs = champ_test_sorted[rows]
        cm = qs.mean(axis=1)
        base = OA.group_base(fold.label, g["team"], g["gw"], len(rows))
        for lab in labels:
            U = OA.sample_uniforms(lab, params[lab], g, base, cm)
            X = np.column_stack([OA.x_from_uniforms(qs[j], U[:, j])
                                 for j in range(len(rows))])
            OA.assert_finite_samples(X, lab)
            sc = OA.score_group(X, y)
            for m in OA.ALL_METRICS:
                metric_sums[lab][m] += sc[m]
            inside[lab] += int(sc["total_inside_80"])
            marg[lab] += sc["marginal_crps_sum"]
        marg_rows += len(rows)

    n_g = len(groups)
    scores = {lab: {m: metric_sums[lab][m] / n_g for m in OA.ALL_METRICS} for lab in labels}
    coverage = {lab: {"coverage": inside[lab] / n_g, "n": n_g} for lab in labels}
    marginal_crps = {lab: marg[lab] / marg_rows for lab in labels}
    spread = OA.assert_marginal_identity(marginal_crps, fold.label)

    # ⭐ ORACLE FIRST (the NF-W3/W4 discipline, on the joint metric): the per-form peeking
    # ceiling vs independence is logged BEFORE any arm is judged.
    ceiling_by_form = {
        f: round(scores["independence"][OA.PRIMARY_METRIC]
                 - scores[OA.oracle_of(f)][OA.PRIMARY_METRIC], 4)
        for f in OA.PARAMETRIZED_FORMS
    }
    log.info("[J] fold %s in %.1fs (%d team-weeks; %d rows scored / %d excluded) — ⭐ per-form "
             "peeking CEILING vs independence (%s): %s", fold.label, time.time() - t0, n_g,
             excl["n_rows_scored"], excl["n_rows_excluded"], OA.PRIMARY_METRIC, ceiling_by_form)
    return {
        "label": fold.label, "scores": scores, "coverage": coverage,
        "marginal_crps": {k: round(v, 5) for k, v in marginal_crps.items()},
        "marginal_identity_spread": round(spread, 5),
        "exclusions": excl, "ceiling_by_form": ceiling_by_form,
        "pair_te_table": _digest_paircorr(pair_te),
        "params_digest": {
            "constant_rho": round(float(params["constant_rho"]), 5),
            "factor_loadings": {k: round(v, 4)
                                for k, v in params["gauss_pos_factor"].items()},
            "dirichlet": {k: (round(v, 5) if isinstance(v, float) else v)
                          for k, v in params["dirichlet_alloc"].items()},
        },
    }


# ── Selection: the arm bake-off ─────────────────────────────────────────────────────────────────
def _crps_matrix(fold_results: list[dict], metric: str = OA.PRIMARY_METRIC) -> pd.DataFrame:
    return pd.DataFrame({fr["label"]: {lab: fr["scores"][lab][metric] for lab in fr["scores"]}
                         for fr in fold_results}).T


def select_joint_arm(fold_results: list[dict], n_folds: int) -> dict:
    crps = _crps_matrix(fold_results)
    mean_crps = crps.mean(axis=0)
    arms = list(OA.REAL_ARMS)
    winner = str(mean_crps[arms].idxmin())
    best_foil = str(mean_crps[list(OA.FOILS)].idxmin())
    deltas = (crps[best_foil] - crps[winner]).to_numpy(dtype=float)
    mean_d, lo, hi = OA.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)

    eligible = OA.eligible_labels()
    defl = NF18.deflate(crps[eligible], subset=eligible)
    trial_srs = []
    for arm in arms:
        d = (crps[best_foil] - crps[arm]).to_numpy(dtype=float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
    pval = M14.onesided_paired_pvalue(deltas)

    shuf_lift = (crps["independence"] - crps["shuffled_teams"]).to_numpy(dtype=float)
    p_shuf = M14.onesided_paired_pvalue(shuf_lift)
    anchors = {
        "comonotonic_loses": bool(mean_crps["comonotonic"] > mean_crps[winner]),
        "winner_beats_shuffled": bool(mean_crps["shuffled_teams"] > mean_crps[winner]),
        # ⛔ an unevaluable p FAILS CLOSED — never a pass (NF1.7 (a))
        "shuffled_lift_not_significant": bool(
            float(np.nanmean(shuf_lift)) <= 0 or (p_shuf is not None and p_shuf >= 0.05)),
        # NF-D16 (g‴) per-form floors; ⭐ STRICT reading reported, NOT the gate:
        "no_arm_beats_own_oracle": bool(all(
            mean_crps[a] > mean_crps[OA.oracle_of(a)] for a in arms)),
        # ⭐ THE GATED reading — NF1.9 (f): a peeking oracle is a floor only AT MATCHED n.
        "oracle_floors_respected_at_matched_n": bool(all(
            (mean_crps[a] > mean_crps[OA.oracle_of(a)])
            or (mean_crps[OA.oracle_of(a)] < mean_crps[OA.matched_n_of(a)])
            for a in arms)),
        "foil_respects_own_oracle": bool(
            mean_crps["constant_rho"] > mean_crps[OA.oracle_of("constant_rho")]),
    }
    oracle_detail = {
        a: {"arm": round(float(mean_crps[a]), 5),
            "own_form_oracle": round(float(mean_crps[OA.oracle_of(a)]), 5),
            "matched_n": round(float(mean_crps[OA.matched_n_of(a)]), 5),
            "oracle_beats_matched_n": bool(mean_crps[OA.matched_n_of(a)]
                                           > mean_crps[OA.oracle_of(a)])}
        for a in arms
    }

    covs = [fr["coverage"][winner] for fr in fold_results]
    n_tot = sum(c["n"] for c in covs)
    cov = (sum(c["coverage"] * c["n"] for c in covs) / n_tot) if n_tot else float("nan")
    se = (float(np.sqrt(OA.COVERAGE_FLOOR * (1 - OA.COVERAGE_FLOOR) / n_tot))
          if n_tot else float("nan"))

    sd = float(np.nanstd(deltas, ddof=1))
    return {
        "winner": winner, "best_foil": best_foil,
        "selection_metric": OA.PRIMARY_METRIC,
        "mean_crps": {k: round(float(v), 5) for k, v in mean_crps.items()},
        "co_metrics": {
            m: {lab: round(float(np.mean([fr["scores"][lab][m] for fr in fold_results])), 5)
                for lab in (winner, best_foil, "independence", "comonotonic")}
            for m in OA.CO_METRICS},
        "deltas_by_fold": [round(float(d), 5) for d in deltas],
        "fold_labels": [fr["label"] for fr in fold_results],
        "mean_delta": None if mean_d is None else round(mean_d, 5),
        "ci95": [None if lo is None else round(lo, 5), None if hi is None else round(hi, 5)],
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
        "shuffle_detail": {"shuffled_lift_vs_independence_mean":
                           round(float(np.nanmean(shuf_lift)), 5),
                           "shuffled_lift_p_one_sided": p_shuf},
        "coverage": {"winner_coverage_80": round(cov, 4), "n_rows": int(n_tot),
                     "binomial_se": round(se, 4),
                     "blocking_shortfall": bool(n_tot and (OA.COVERAGE_FLOOR - cov)
                                                > OA.COVERAGE_BLOCK_SE * se)},
    }


# ── Selection: ⭐ the ceiling (the NF-W8 decision object) ────────────────────────────────────────
def select_ceiling(fold_results: list[dict], n_folds: int) -> dict:
    crps = _crps_matrix(fold_results)
    indep = crps["independence"].to_numpy(dtype=float)
    clause = cv_power.fold_consistency_clause(n_folds)

    per_form: dict[str, dict] = {}
    for f in OA.PARAMETRIZED_FORMS:
        d = indep - crps[OA.oracle_of(f)].to_numpy(dtype=float)
        m, lo, hi = OA.paired_ci95(d)
        per_form[f] = {"mean_delta": None if m is None else round(m, 5),
                       "ci95": [None if lo is None else round(lo, 5),
                                None if hi is None else round(hi, 5)],
                       "fold_wins": int((d > 0).sum())}
    best_form = max(per_form,
                    key=lambda f: (per_form[f]["mean_delta"]
                                   if per_form[f]["mean_delta"] is not None else -np.inf))
    deltas = indep - crps[OA.oracle_of(best_form)].to_numpy(dtype=float)
    mean_d, lo, hi = OA.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    pval = M14.onesided_paired_pvalue(deltas)
    mean_indep = float(np.mean(indep))
    pct = (100.0 * mean_d / mean_indep) if (mean_d is not None and mean_indep > 0) else None

    co_ceiling = {}
    for m in OA.CO_METRICS:
        cm = _crps_matrix(fold_results, m)
        d = cm["independence"].to_numpy(float) - cm[OA.oracle_of(best_form)].to_numpy(float)
        md, clo, chi = OA.paired_ci95(d)
        base = float(np.mean(cm["independence"]))
        co_ceiling[m] = {
            "mean_delta": None if md is None else round(md, 5),
            "ci95": [None if clo is None else round(clo, 5),
                     None if chi is None else round(chi, 5)],
            "pct_of_independence": (None if md is None or base <= 0
                                    else round(100.0 * md / base, 2)),
        }

    fold_labels = [fr["label"] for fr in fold_results]
    cap_idx = [i for i, lbl in enumerate(fold_labels) if lbl in CAPTURE_ERA_FOLDS]
    leg_idx = [i for i, lbl in enumerate(fold_labels) if lbl not in CAPTURE_ERA_FOLDS]
    era_note = {
        "capture_folds": [fold_labels[i] for i in cap_idx],
        "capture_mean_delta": (round(float(np.mean(deltas[cap_idx])), 4) if cap_idx else None),
        "legacy_mean_delta": (round(float(np.mean(deltas[leg_idx])), 4) if leg_idx else None),
        "note": "REPORT-ONLY (NF-W2d/W2e): forward-looking sizing quotes the capture era.",
    }
    return {
        "best_form": best_form, "per_form": per_form,
        "selection_metric": OA.PRIMARY_METRIC,
        "mean_independence": round(mean_indep, 5),
        "deltas_by_fold": [round(float(d), 5) for d in deltas],
        "fold_labels": fold_labels,
        "mean_delta": None if mean_d is None else round(mean_d, 5),
        "ci95": [None if lo is None else round(lo, 5), None if hi is None else round(hi, 5)],
        "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        "p_one_sided": pval,
        "ceiling_pct": None if pct is None else round(pct, 3),
        "co_metric_ceilings": co_ceiling,
        "era_note": era_note,
        # ⭐ upward-bias declaration: the max over the peeking forms favors YES ⇒ a NO is
        # conservative. PBO is UNDEFINED by design (one pre-registered contrast per form; the
        # max is a ceiling ESTIMATOR, not a shippable selection).
        "estimator_note": ("max over the per-form peeking oracles — upward-biased by selection "
                           "over the declared forms; the bias FAVORS a YES, so a NO is "
                           "conservative (pre-registered)."),
        "pbo": None,
        "pbo_state": ("UNDEFINED — the ceiling is a pre-registered anchor contrast, not a "
                      "searched field; declared before the run (the NF-W3/W4 rule)."),
        "fdr_binding": None,   # injected by derive_verdict_layer
    }


# ── Verdict layer (derived, shared with --rewrite-report — NF-W2e one level up) ─────────────────
def _classify_arm(sel: dict, n_folds: int, checks: dict) -> dict:
    hand = OA.hand_classify_refusal(checks)
    if hand is not None:
        return hand
    v = cv_power.classify_null(
        metric="nf_w5_joint_alloc_crps", n_folds=n_folds, n_arms=len(OA.REAL_ARMS),
        beats_foil=sel["beats_foil"], observed_sr=sel["observed_sr"],
        var_trials_sr=sel["var_trials_sr"], fold_wins=sel["fold_wins"],
        p_one_sided=sel["p_one_sided"], bh_cutoff=OA.FDR_Q,
        degenerates_excluded_from_v=True,
    )
    return OA.flag_unsafe_field_shrink(
        {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger},
        len(OA.REAL_ARMS))


def derive_verdict_layer(out: dict) -> dict:
    """⭐ Re-derive EVERY decision from the stored selections — no refit (NF-W2e one level up)."""
    n_folds = out["n_folds"]
    fdr = fdr_two_families({"joint_alloc_arm": out["arm"]["p_one_sided"]},
                           {"joint_alloc_ceiling": out["ceiling"]["p_one_sided"]})
    out["ceiling"]["fdr_binding"] = bool(fdr["binding"].get("joint_alloc_ceiling", False))
    gate_arm = OA.compose_gate_joint(out["arm"], fdr["binding"].get("joint_alloc_arm", False))
    decision = OA.decide_nf_w8(out["ceiling"])

    null_states: dict[str, dict] = {}
    if not gate_arm["ship"]:
        null_states["arm"] = _classify_arm(out["arm"], n_folds, gate_arm["checks"])
    verdict = {
        "nf_w8_decision": decision["answer"],
        "arm": ("SHIP" if gate_arm["ship"] else null_states.get("arm", {}).get("state", "NULL")),
    }
    headline = (f"CEILING[{decision['answer']}"
                + (f" {out['ceiling']['ceiling_pct']}%" if out["ceiling"]["ceiling_pct"]
                   is not None else "")
                + f"] ARM[{verdict['arm']}]")
    return {"fdr": fdr, "gate_arm": gate_arm, "decision": decision,
            "null_states": null_states, "verdict": verdict, "headline": headline}


def pooled_dependence_table(fold_results: list[dict]) -> list[dict]:
    """The model-free mechanism measurement: realized same-team PIT correlations by position
    pair, pooled over the TEST folds (report-only)."""
    acc: dict[str, dict] = {}
    for fr in fold_results:
        for key, d in fr["pair_te_table"].items():
            a = acc.setdefault(key, {"rn": 0.0, "n": 0, "groups": 0})
            a["rn"] += d["r"] * d["n_pairs"]
            a["n"] += d["n_pairs"]
            a["groups"] += d["n_groups"]
    return [{"pair": k, "r_pooled": round(v["rn"] / v["n"], 4), "n_pairs": v["n"],
             "n_team_weeks": v["groups"]}
            for k, v in sorted(acc.items()) if v["n"]]


# ── Report (every verdict word DERIVED at report time — never stored; NF-W2e) ───────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    ceil, arm = out["ceiling"], out["arm"]
    p("# NF-W5 — opportunity allocation on the JOINT gate (§0.5 bake-off + the NF-W8 decision)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} half-season blocks "
      f"({out['fold_labels'][0]}…{out['fold_labels'][-1]}, the NF-W1 axis on the NF-W2d two-era "
      f"matrix) · **player-weeks:** {out['n_rows']} · **team-weeks scored:** "
      f"{out['n_team_weeks']}")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held** (serving "
      "is NF-W8 / NF-C6 Ph2). Primary metric is sample-based **team-total CRPS** (roster-grain "
      "lineup CRPS; S=512, common random numbers); energy + variogram scores are co-reported and "
      "never select. Marginals are PINNED to the injury-aware champion — every construction "
      "differs ONLY in the copula (the Sklar split), asserted numerically per fold. Every "
      "direction word below is three-way and **derived from the interval at report time**, "
      "failing closed to `TIES` (NF-W2e).")
    p("")
    pa = out["pit_audit"]
    p(f"**PIT gate (NF-W0a, via the NF-W2d assembly — NO new source in NF-W5):** "
      f"{pa['game_groups_checked']} game-groups / {pa['records_checked']} records checked; "
      f"{pa['rows_dropped']} rows dropped fail-closed.")
    p("")
    p("## ⭐ THE NF-W8 DECISION (the story's deliverable)")
    p("")
    d = out["decision"]
    p(f"# **{d['answer']}** — {d['reason']}")
    p("")
    p(f"- decision rule (pre-registered): stat_ok (CI>0 ∧ fold clause ∧ BH binding) then bands "
      f"NO < {d['bands'][0]}% ≤ MARGINAL < {d['bands'][1]}% ≤ YES on ceiling_pct.")
    p(f"- context: the NF-W3 environment ceiling was 2.0–3.1% of champion CRPS (recorded as "
      f"'cannot justify the chain alone'); the NF-W4 availability ceiling was 8.1–27.8% "
      f"(largest single error source, forecastable slice already priced).")
    p("")
    p("## ⭐ Oracle first — the joint-allocation ceiling")
    p("")
    p(f"Best peeking form: `{ceil['best_form']}` — "
      + OA.verdict_sentence(f"oracle__{ceil['best_form']}", "independence",
                            ceil["mean_delta"], ceil["ci95"][0], ceil["ci95"][1])
      + f" = **{ceil['ceiling_pct']}%** of the independence {OA.PRIMARY_METRIC} "
        f"({ceil['mean_independence']}), fold wins {ceil['fold_wins']}/{out['n_folds']} "
        f"(clause requires {ceil['fold_clause']['required']}), p {ceil['p_one_sided']}, "
        f"BH binding {ceil['fdr_binding']}.")
    p("")
    p(pd.DataFrame([{"form": f, **v} for f, v in ceil["per_form"].items()])
      .to_markdown(index=False))
    p("")
    p(f"- co-metric ceilings (report-only): {ceil['co_metric_ceilings']}")
    p(f"- estimator note: {ceil['estimator_note']}")
    p(f"- PBO: {ceil['pbo_state']}")
    p(f"- 📅 era note: {ceil['era_note']}")
    p("")
    p("## The mechanism, model-free — realized same-team PIT correlation by position pair")
    p("")
    p(pd.DataFrame(out["dependence_table"]).to_markdown(index=False))
    p("")
    p("## The arm bake-off (secondary to the decision)")
    p("")
    p(f"### winner `{arm['winner']}` vs best foil `{arm['best_foil']}` — "
      f"**{out['verdict']['arm']}**")
    p("")
    p(OA.verdict_sentence(arm["winner"], arm["best_foil"], arm["mean_delta"],
                          arm["ci95"][0], arm["ci95"][1]))
    p("")
    p(pd.DataFrame([{"label": k, "mean_team_total_crps": v}
                    for k, v in arm["mean_crps"].items()])
      .sort_values("mean_team_total_crps").to_markdown(index=False, floatfmt=".5f"))
    p("")
    p(f"- fold wins {arm['fold_wins']}/{out['n_folds']} (clause requires "
      f"{arm['fold_clause']['required']}) · PBO {arm['pbo']} · DSR {arm['dsr']} · "
      f"p {arm['p_one_sided']} · BH own-family "
      f"{out['fdr']['own_family'].get('joint_alloc_arm')} / pooled "
      f"{out['fdr']['pooled'].get('joint_alloc_arm')} (binding "
      f"{out['fdr']['binding'].get('joint_alloc_arm')})")
    p(f"- anchors: {arm['anchors']}")
    p(f"- per-form oracle floors (NF-D16 (g‴)) + matched-n capacity control (NF1.9 (f)): "
      f"{arm['oracle_detail']}")
    p(f"- shuffle: {arm['shuffle_detail']} · team-total coverage(80) {arm['coverage']}")
    p(f"- co-metrics (never select): {arm['co_metrics']}")
    p(f"- gate: {out['gate_arm']['checks']}")
    ns = out["null_states"].get("arm", {})
    if ns.get("field_shrink_flag"):
        f = ns["field_shrink_flag"]
        p(f"- ⚠️ **field-shrink remedy is {f['status']}** — {f['note']}")
    p("")
    p("## Marginal identity (the Sklar guard, §10.1A made structural)")
    p("")
    p(pd.DataFrame([{"fold": fr["label"], "spread": fr["marginal_identity_spread"],
                     "tolerance": OA.MARGINAL_IDENTITY_TOL,
                     "exclusions": fr["exclusions"]["n_rows_excluded"],
                     "team_weeks": fr["exclusions"]["n_groups"]}
                    for fr in out["fold_results"]]).to_markdown(index=False))
    p("")
    p("## Null-state classification")
    p("")
    p("```json")
    p(json.dumps(out["null_states"], indent=2, default=str))
    p("```")
    p("")
    p("## Pre-registration echo")
    p("")
    p("```json")
    p(json.dumps(out["preregistration"], indent=2, default=str))
    p("```")
    path.write_text("\n".join(a))


# ── Runner ──────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:  # noqa: C901 — orchestration
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-W5 joint-gate bake-off + the NF-W8 decision")
    ap.add_argument("--smoke", action="store_true", help="2 folds, artifacts suffixed _smoke")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="regenerate the .md + verdict layer from the stored .json — no refit")
    args = ap.parse_args(argv)
    suffix = "_smoke" if args.smoke else ""
    json_path = _REPORT_DIR / f"nf_w5_opportunity_allocation{suffix}.json"

    if args.rewrite_report:
        out = json.loads(json_path.read_text())
        before = dict(out.get("verdict", {}))
        out.update(derive_verdict_layer(out))
        moved = {k: (before.get(k), v) for k, v in out["verdict"].items()
                 if before.get(k) != v}
        if moved:
            out["verdict_corrected_from"] = before
            out["verdict_correction_note"] = (
                "re-derived from the stored selections without refitting (NF-W2e one level up)")
            log.warning("VERDICT MOVED on re-derivation: %s", json.dumps(moved))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        json_path.write_text(json.dumps(out, indent=2, default=float))
        write_report(out, _REPORT_DIR / f"nf_w5_opportunity_allocation{suffix}.md")
        log.info("report + verdict layer re-derived from %s (no refit): %s",
                 json_path.name, out["headline"])
        print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                          "moved": moved}, indent=2))
        return 0

    t_start = time.time()
    assert_incumbents_match_the_w2d_artifact()
    feat, pit_audit, _store_raw = build_matrix_w2d(SEASONS, rebuild_cache=args.rebuild_cache)
    if "team" not in feat.columns:
        raise ValueError("the W2d matrix carries no `team` column — the joint object cannot be "
                         "grouped; refusing to proceed")
    folds = W2.build_folds_w2(feat, OA.TEST_BLOCKS)
    if args.smoke:
        folds = folds[-2:]
    n_folds = len(folds)
    log.info("NF-W5: %d folds over %d player-weeks (matrix = the NF-W2d two-era build); "
             "field = %d arms + %d foils + %d anchors, S=%d",
             n_folds, len(feat), len(OA.REAL_ARMS), len(OA.FOILS), len(OA.anchors()),
             OA.N_SAMPLES)

    frs = [run_joint_fold(f, feat) for f in folds]
    arm = select_joint_arm(frs, n_folds)
    ceiling = select_ceiling(frs, n_folds)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": OA.STORY, "smoke": bool(args.smoke),
        "runtime_seconds": round(time.time() - t_start, 1),
        "selection_metric": OA.PRIMARY_METRIC, "co_metrics": list(OA.CO_METRICS),
        "n_folds": n_folds, "fold_labels": [f.label for f in folds],
        "n_rows": int(len(feat)),
        "n_team_weeks": int(sum(fr["exclusions"]["n_groups"] for fr in frs)),
        "pit_audit": pit_audit,
        "preregistration": {
            "real_arms": list(OA.REAL_ARMS), "foils": list(OA.FOILS),
            "anchors": list(OA.anchors()), "eligible": OA.eligible_labels(),
            "parametrized_forms": list(OA.PARAMETRIZED_FORMS),
            "primary_metric": OA.PRIMARY_METRIC, "co_metrics": list(OA.CO_METRICS),
            "n_samples": OA.N_SAMPLES, "variogram_p": OA.VARIOGRAM_P,
            "min_team_k": OA.MIN_TEAM_K, "role_caps": dict(OA.ROLE_CAPS),
            "marginal_identity_tol": OA.MARGINAL_IDENTITY_TOL,
            "ceiling_bands": list(OA.CEILING_BANDS),
            "incumbent_of_position": dict(AV.INCUMBENT_OF_POSITION),
            "test_blocks": [list(t) for t in OA.TEST_BLOCKS], "purge_weeks": OA.PURGE_WEEKS,
            "pbo_max": OA.PBO_MAX, "dsr_min": OA.DSR_MIN, "fdr_q": OA.FDR_Q,
            "fdr_families": {k: list(v) for k, v in OA.FDR_FAMILIES.items()},
            "coverage_floor": OA.COVERAGE_FLOOR,
            "capture_era_folds": list(CAPTURE_ERA_FOLDS),
            "seed": OA._SEED,
        },
        "arm": arm, "ceiling": ceiling,
        "dependence_table": pooled_dependence_table(frs),
        "fold_results": [{k: fr[k] for k in ("label", "scores", "marginal_identity_spread",
                                             "exclusions", "ceiling_by_form",
                                             "params_digest")} for fr in frs],
    }
    out.update(derive_verdict_layer(out))

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, default=float))
    write_report(out, _REPORT_DIR / f"nf_w5_opportunity_allocation{suffix}.md")
    log.info("verdict: %s (%.1fs)", out["headline"], out["runtime_seconds"])
    print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                      "decision": out["decision"],
                      "runtime_seconds": out["runtime_seconds"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
