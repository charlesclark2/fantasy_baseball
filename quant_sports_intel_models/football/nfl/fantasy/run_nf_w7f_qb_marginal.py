"""run_nf_w7f_qb_marginal.py — NF-W7f §0.5: the QB MARGINAL-layer zero-mass recalibration, scored
against the SAME reproduced incumbent as NF-W7c/W7d/W7e and against NF-W7e's own registered QB arm.

Everything decidable in advance is a CONSTANT in `fp_qb_marginal_calibration.py`; this runner READS
it (NF-D16). The narrative pre-registration is committed at
`ablation_results/nf_w7f_preregistration.md` BEFORE the full run.

WHY THIS STORY EXISTS. NF-W7e CONFIRMED — measured, not inferred — that QB's PIT ceiling is set by
the MARGINAL layer: the installed atom is Σ-invariant (0.267125 under both Σ populations, max fold
gap 0.0), the marginals ADMIT 0.2687 of atom against a realized all-zero rate of 0.5162, and the
clamp binds on 91.7% of QB rows. Three stories exhausted the joint-layer knobs. ⛔ This one opens
NONE of them: Σ, π̂, the mixture machinery and the draw stream are all inherited BY IDENTITY, and the
only thing the declared family varies is the per-leg zero-mass TARGET of the QB marginals.

PIPELINE (one target — `league_fantasy_points` under NF-W7c's declared gate league; **QB ONLY**):
  · the matrix, folds, PIT gate, per-stat MARGINALS and league weights are NF-W7c/W7d/W7e's
    VERBATIM (the marginals through the NF-W6d SERVING DISPATCH — neither refit nor re-selected);
  · per fold: the served QB banks are RE-SPLICED to each arm's zero-mass target
    (`fp_qb_marginal_calibration.resplice_zero_mass`), then assembled under NF-W7e's registered
    joint construction (the learned π̂ + the incumbent's all-rows Σ) — against `mixall_learned`
    (the MATCHED foil: the identical construction on the SERVED marginals, reproduced to 1e-9 vs
    NF-W7e) and `single_copula` (THE INCUMBENT, reproduced to 1e-9 vs NF-W7c), with
    `zm_cond_copula` completing the 2×2, all on ONE base-normal block with every anchor;
  · a first-class DIAGNOSTIC per fold: each leg's predicted vs realized zero mass, which leg
    ATTAINS the row-wise minimum (i.e. which NF-W6d cell caps the atom), the cap before/after, and
    the clamp's binding share — so the story's premise is auditable rather than asserted;
  · gate: crps_q199 vs the best CONTEST foil ∧ the fold clause ∧ PBO ∧ DSR ∧ BH-FDR ∧ the
    coverage(80) floor ∧ randomized-PIT flatness ≤ 0.05 ∧ degenerates / permutations / oracles ∧
    the three inherited DEPENDENCE clauses ∧ `mixture_is_active` ∧ `mixture_preserves_marginals` ∧
    `incumbent_reproduces` ∧ `predecessor_reproduces` ∧ the four clauses this story ADDS
    (`zero_mass_hits_target`, `positive_law_preserved`, `matched_foil_identity`, `cap_was_lifted`,
    `per_leg_calibration_not_degraded`);
  · the MARGINAL-CAP verdict, read by the pre-registered rule `QM.marginal_cap_verdict`.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: writes LOCAL artifacts only — no
`--publish`, no S3 client, no boto3, no dbt, no Dagster.

RUN (OPERATOR — LAPTOP; reads the S3 NFL lake read-only, writes local artifacts):

    # path proof: 1 fold, few draws (artifact _smoke) — no verdict. >2 min: OPERATOR.
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7f_qb_marginal --smoke

    # the decisive run (>2 min — OPERATOR; dominated by the W6d marginal dispatch)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7f_qb_marginal

    # re-derive every verdict from the stored fold scores at ZERO refit cost (NF-W2e / NF-W3)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7f_qb_marginal \
        --rewrite-report

⭐ Per-fold MARGINAL BANKS are read from and written to **NF-W7e's cache directory**
(`artifacts/nf_w7e_bank_cache/`, gitignored), with NF-W7e's key function BY IDENTITY: the banks are
literally the same object (same matrix key, same served map, same fold labels), and this story
TRANSFORMS them rather than refitting them. So a machine that already ran NF-W7e's decisive run pays
only for the draws. `--rebuild-banks` forces the fits.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import cv_power  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    fp_availability_split_allrows as SA,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    fp_qb_marginal_calibration as QM,
)
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
    run_nf_w7d_qb_availability as W7D,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w7e_split_allrows as W7E,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    stat_distribution_serving_d as SDSD,
)
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_w7f")

SEASONS = W6DA.SEASONS
FEATURES = list(WP.FEATURES)
#: ⛔ NF-W7c's gate league, INHERITED through NF-W7d/W7e (E2.1-r).
GATE_LEAGUE = W7E.GATE_LEAGUE

_ARTIFACT_REL = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                 "nf_w7f_qb_marginal.json")

# The frame/marginal plumbing and the per-fold bank cache are the predecessors', BY IDENTITY —
# the banks this story re-splices must be the SAME object NF-W7e assembled, or the matched foil is
# not matched (a second cache with a second key is the NF-C0e wrong-key class).
realized_matrix = W7D.realized_matrix
bank_tensor = W7D.bank_tensor
_marginals_cached = W7E._marginals_cached
_usable = W7E._usable
_pooled_coverage = W7E._pooled_coverage
_record_scores = W7E._record_scores


# ── The predecessor's recorded cap baseline (read, never trusted from a constant) ────────────────
def predecessor_cap_baseline() -> dict:
    """NF-W7e's RECORDED QB atom-cap figures — the baseline `cap_was_lifted` is measured against.

    ⛔ Read from the committed record at run time, and REFUSED if the record is absent or a path
    proof: a cap lift measured against a hard-coded number could not notice that the predecessor's
    record had been regenerated, and "the mechanism acted" would then be a claim about a constant
    rather than about this run (the NF1.9-R `served_*`-column lesson: never trust a name for a
    measurement)."""
    p = _PROJECT_ROOT / QM.PREDECESSOR_RECORD_RELPATH
    if not p.exists():
        return {"available": False, "reason": f"{p.name} is absent — the cap-lift baseline could "
                                             f"not be read, so `cap_was_lifted` is UNEVALUABLE "
                                             f"and never a pass (NF1.7 (a))"}
    rec = json.loads(p.read_text())
    if rec.get("story") != QM.PREDECESSOR or rec.get("smoke"):
        return {"available": False, "reason": f"{p.name} is story {rec.get('story')} / smoke="
                                             f"{rec.get('smoke')} — a path proof is not a "
                                             f"baseline; REFUSED"}
    cap = rec.get("atom_cap") or {}
    if cap.get("atom_cap_mean") is None:
        return {"available": False, "reason": f"{p.name} carries no `atom_cap.atom_cap_mean` — "
                                             f"REFUSED rather than defaulted"}
    return {
        "available": True,
        "atom_cap_mean": float(cap["atom_cap_mean"]),
        "realized_all_zero_rate": float(cap.get("realized_all_zero_rate", float("nan"))),
        "installed_atom": float(cap.get("installed_atom_all_rows_sigma", float("nan"))),
        "best_qb_pit": float(cap.get("best_pit", float("nan"))),
        "state": cap.get("state"),
        "matches_preregistered_constants": bool(
            abs(float(cap["atom_cap_mean"]) - QM.PREDECESSOR_CAP_MEAN) <= 1e-4),
    }


def _per_leg_table(served: np.ndarray, recal: np.ndarray, y_leg: np.ndarray,
                   weights: np.ndarray, pi_hat: np.ndarray) -> dict:
    """Per-leg `crps_q199`, served vs recalibrated, plus ⭐ the AVAILABILITY DECOMPOSITION.

    The summed PRICED figure is what `per_leg_calibration_not_degraded` reads. The decomposition by
    π̂ quartile is REPORTED, never gated, and it exists because the smoke measured that the sign of
    the per-leg effect FLIPS with availability: raising a leg's atom helps where the player probably
    did not play and hurts where he probably did. Without it a refusal would say "the parts got
    worse" and a successor would not know WHERE — which is the difference between a null that names
    where the answer lives (NF-D18 / MARGIN2→3) and one that just closes a door."""
    out: dict[str, dict] = {}
    d_priced = np.zeros(len(y_leg), dtype=float)
    for i, leg in enumerate(QM.LEGS):
        s_row = KW.crps_dense(served[:, i, :], y_leg[:, i])
        r_row = KW.crps_dense(recal[:, i, :], y_leg[:, i])
        d = np.asarray(s_row, dtype=float) - np.asarray(r_row, dtype=float)   # >0 ⇒ improved
        priced_leg = bool(weights[i] != 0.0)
        if priced_leg:
            d_priced = d_priced + d
        out[leg] = {"served_crps": round(float(np.mean(s_row)), 5),
                    "recalibrated_crps": round(float(np.mean(r_row)), 5),
                    "delta": round(float(np.mean(d)), 5),
                    # ⭐ sums+counts on FIXED π̂ edges, so the 8-fold pool is exact (QM.bucket_*)
                    "delta_by_availability": QM.bucket_by_availability(d, pi_hat),
                    "priced": priced_leg}
    priced = [leg for leg, v in out.items() if v["priced"]]
    s_tot = sum(out[leg]["served_crps"] for leg in priced)
    r_tot = sum(out[leg]["recalibrated_crps"] for leg in priced)
    return {"by_leg": out, "priced_legs": priced,
            "served_crps_sum_priced": round(s_tot, 5),
            "recalibrated_crps_sum_priced": round(r_tot, 5),
            "relative_change": round((r_tot - s_tot) / max(s_tot, 1e-9), 6),
            # the summed PRICED delta per ROW, bucketed — the quantity the GATE reads, decomposed
            # by availability. This is the successor's premise, so it is measured on every fold.
            "priced_delta_by_availability": QM.bucket_by_availability(d_priced, pi_hat)}


# ── One fold × position ─────────────────────────────────────────────────────────────────────────
def run_position(position: str, train: pd.DataFrame, test: pd.DataFrame, weights: np.ndarray, *,
                 draws: int, ctx_te: dict) -> dict:
    """Every arm, foil and anchor for one (fold, position), on ONE shared base-normal stream."""
    tr_p = train.loc[train["position"].astype(str) == position].reset_index(drop=True)
    te_p = test.loc[test["position"].astype(str) == position].reset_index(drop=True)
    if len(te_p) == 0 or len(tr_p) < QM.MIN_ESTIMATION_ROWS:
        return {"skipped": f"train {len(tr_p)} / test {len(te_p)} rows — below the estimation "
                           f"floor ({QM.MIN_ESTIMATION_ROWS}); REFUSED, not defaulted"}

    b_te = bank_tensor(ctx_te, position, len(te_p))          # the SERVED marginals, untouched
    raw_tr, raw_te = realized_matrix(tr_p), realized_matrix(te_p)
    y_te = FA.score_realized(raw_te, weights)

    # the matched-n capacity control (NF1.9 (f)): the most recent TRAIN rows sized to the test block
    n_match = max(len(te_p), QM.MIN_ESTIMATION_ROWS)
    m_tr = np.sort(np.argsort(tr_p["gw"].to_numpy(), kind="stable")[-n_match:])
    tr_m = tr_p.iloc[m_tr].reset_index(drop=True)
    raw_m = raw_tr[m_tr]
    # ⛔ EVERY estimation context must clear the floor, not just the train one. The conditional zero
    # rate is estimated on ACTIVE rows in three contexts (train, the ORACLE's test block, the
    # matched-n slice) and refuses below the floor — so a context that could not be estimated must
    # SKIP the fold with a named reason rather than raise mid-run and lose the other folds
    # (NF1.7 (a): a context that did not run is never a pass). Measured on NF-W7e's real folds: QB
    # test blocks carry 671–710 rows at ~49% active ≈ 330, against a floor of 50 — comfortable, and
    # checked rather than assumed.
    thin = {name: int(QM.activity_indicator(r).sum())
            for name, r in (("train", raw_tr), ("oracle/test", raw_te), ("matched_n", raw_m))
            if int(QM.activity_indicator(r).sum()) < QM.MIN_ESTIMATION_ROWS}
    if thin:
        return {"skipped": f"these estimation contexts carry fewer ACTIVE {position} rows than the "
                           f"floor ({QM.MIN_ESTIMATION_ROWS}): {thin} — the conditional zero rate "
                           f"could not be estimated there, so this fold is REFUSED rather than "
                           f"scored (NF1.7 (a))"}

    # ── Σ: the INCUMBENT's all-rows estimator, on TRAIN, for EVERY arm and context.
    # ⛔ The oracle peeks at what THIS story ESTIMATES (π̂ and the two zero rates) and at NOTHING
    # else. Peeking Σ as well would (a) change a factor the family holds fixed and (b) reproduce
    # NF-W7e's own finding that a Σ peeked on a ~700-row block LOSES more to sample size than the
    # peek gains — which is how a per-form floor goes INACTIVE (NF1.7 (b) / NF-W6d).
    sig_all, sig_all_note = QM.sigma_all(raw_tr)

    # the per-context estimation inputs: (frame the estimator sees, its raw matrix)
    ctxs = {"": (tr_p, raw_tr), "oracle__": (te_p, raw_te), "matched_n__": (tr_m, raw_m)}
    est_inputs: dict[str, dict] = {}
    for prefix, (frame, raw) in ctxs.items():
        est_inputs[prefix] = {
            "pi": QM.pi_for_arm(QM.PI_ESTIMATOR, frame, te_p, FEATURES, train_raw=raw),
            "cond": QM.conditional_zero_rate(raw),
            "marg": QM.marginal_zero_rate(raw),
        }

    # ⭐ the realized leg values AS THE DRAW PATH REALIZES THEM (clip at 0, round integer legs) —
    # the per-leg CRPS and the marginal's atom must be scored against the SAME event
    y_leg = np.clip(raw_te, 0.0, None)
    for i, leg in enumerate(QM.LEGS):
        if leg in QM.INTEGER_LEGS:
            y_leg[:, i] = np.rint(y_leg[:, i])

    banks: dict[str, np.ndarray] = {}
    clamps: dict[str, dict] = {}
    targets_summary: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    # ⛔ PER ARM, not just the primary. The identities depend on the arm's TARGET and the per-leg
    # clause is read for the WINNER — a table computed only for the primary would describe a
    # DIFFERENT arm than the gate anchors, which is the "an anchor that describes something other
    # than what it anchors" defect (NF1.7 (a)). Found by the smoke: all four arms move the per-leg
    # CRPS by different amounts (+0.60% to +48.6%), so which arm the clause reads is decisive.
    identities: dict[str, dict] = {}
    per_leg: dict[str, dict] = {}
    recal_primary: np.ndarray | None = None
    for arm in QM.REAL_ARMS:
        for prefix, inp in est_inputs.items():
            t = QM.zero_targets(arm, banks=b_te, pi_hat=inp["pi"], cond_rate=inp["cond"],
                                marg_rate=inp["marg"])
            recal = QM.resplice_zero_mass(b_te, t)
            # ⭐ the clamp still runs — marginal preservation is not optional — but on the
            # RECALIBRATED banks, which is the whole point: the floor it enforces is now high
            # enough to admit the atom π̂ asks for.
            pi_used, note = QM.clamp_pi(inp["pi"], recal)
            banks[f"{prefix}{arm}"] = QM.assemble_mixture_bank(recal, weights, pi=pi_used,
                                                               corr=sig_all, draws=draws)
            if not prefix:
                clamps[arm] = note
                edges[arm] = QM.resplice_edges(b_te, t)
                identities[arm] = {
                    "zero_mass_hits_target": QM.zero_mass_hits_target(b_te, t, recal),
                    "positive_law": QM.positive_law_drift(b_te, recal),
                }
                per_leg[arm] = _per_leg_table(b_te, recal, y_leg, weights, inp["pi"])
                targets_summary[arm] = {
                    "mean": round(float(t.mean()), 4), "sd": round(float(t.std()), 4),
                    "mean_priced": round(float(np.mean(t[:, weights != 0.0])), 4)
                    if np.any(weights != 0.0) else None,
                    "atom_cap_after": round(QM.atom_cap(recal), 4),
                }
                if arm == QM.PRIMARY_ARM:
                    recal_primary, t_primary, pi_primary = recal, t, inp["pi"]
    if recal_primary is None:
        raise ValueError(f"{position}: the primary arm `{QM.PRIMARY_ARM}` produced no train-context "
                         f"recalibration — the foils, the permutation anchor and every identity "
                         f"diagnostic would describe a different splice than the arm they anchor")

    # ── The CONTEST foils. `mixall_learned` is NF-W7e's registered QB arm: the IDENTICAL joint
    # construction on the SERVED marginals — the MATCHED foil, so `mixall_learned − zm_*` is the
    # recalibration and nothing else. `single_copula` is NF-W7c's incumbent.
    pi_served_used, clamp_served = QM.clamp_pi(est_inputs[""]["pi"], b_te)
    banks["mixall_learned"] = QM.assemble_mixture_bank(b_te, weights, pi=pi_served_used,
                                                       corr=sig_all, draws=draws)
    banks["single_copula"] = FA.assemble_fp_bank(b_te, weights, corr=sig_all, draws=draws)
    # the 2×2's fourth cell: the recalibrated marginals with the availability split OFF — does a
    # raised atom pay when nothing makes it COMMON across legs? (reference, never gated)
    banks["zm_cond_copula"] = FA.assemble_fp_bank(recal_primary, weights, corr=sig_all, draws=draws)
    banks["assembled_indep"] = FA.assemble_fp_bank(b_te, weights, mode="indep", draws=draws)
    banks["assembled_comonotone"] = FA.assemble_fp_bank(b_te, weights, mode="comonotone",
                                                        draws=draws)

    # the zero-mass permutation anchor — the PRIMARY arm's per-row inactivity shuffled across
    # players within a global week, used consistently in the marginal target AND the mixture: the
    # population LEVEL of the atom is preserved, only its per-ROW assignment is destroyed
    pi_perm = KW.permute_within_group(pi_primary, te_p["gw"].to_numpy())
    t_perm = QM.zero_targets(QM.PRIMARY_ARM, banks=b_te, pi_hat=pi_perm,
                             cond_rate=est_inputs[""]["cond"], marg_rate=est_inputs[""]["marg"])
    recal_perm = QM.resplice_zero_mass(b_te, t_perm)
    pi_perm_used, _ = QM.clamp_pi(pi_perm, recal_perm)
    banks["zm_permuted"] = QM.assemble_mixture_bank(recal_perm, weights, pi=pi_perm_used,
                                                    corr=sig_all, draws=draws)

    tr_p, te_p = tr_p.copy(), te_p.copy()
    tr_p[FA.TARGET] = FA.score_realized(raw_tr, weights)
    te_p[FA.TARGET] = y_te
    banks["foil_direct_points"] = KW.fit_direct_points(tr_p, te_p, FEATURES, FA.TARGET)
    banks["oracle__foil_direct_points"] = KW.fit_direct_points(te_p, te_p, FEATURES, FA.TARGET)
    banks["permuted_direct"] = KW.fit_direct_points(
        tr_p, te_p, FEATURES, FA.TARGET,
        y_train=KW.permute_within_group(tr_p[FA.TARGET].to_numpy(float),
                                        tr_p["gw"].to_numpy()))

    pts_tr = tr_p[FA.TARGET].to_numpy(float)
    loc = float(np.mean(pts_tr))
    clim = np.quantile(pts_tr, FA.EVAL_LEVELS)[None, :] * np.ones((len(te_p), 1))
    banks["nihilist_zero"] = np.zeros((len(te_p), FA.N_LEVELS))
    banks["zero_width"] = np.full_like(clim, loc)
    banks["max_width"] = loc + 3.0 * (clim - loc)

    missing = sorted(set(QM.ALL_LABELS) - set(banks))
    if missing:
        raise ValueError(f"{position}: the declared field is incomplete — {missing} produced no "
                         f"predictive. A field scored with an arm silently missing is not the "
                         f"declared field (NF1.7 (a)).")

    scores: dict[str, float] = {}
    for label, bank in banks.items():
        KW.assert_finite_predictive(bank, f"{position}/{label}")
        scores[label] = float(np.mean(KW.crps_dense(bank, y_te)))
    coverage = {lab: KW.coverage80_dense(banks[lab], y_te) for lab in QM.WATCHED}
    pit = {lab: QM.pit_detail(KW.randomized_pit_from_bank(banks[lab], y_te)) for lab in QM.WATCHED}

    # the marginal-preservation diagnostic on the PRIMARY arm's own clamped π over ITS recalibrated
    # banks (NF-W7d's one code path); the reference side is the same construction with π ≡ 1
    pi_primary_used, _ = QM.clamp_pi(pi_primary, recal_primary)
    drift = QM.mixture_marginal_drift(recal_primary, pi=pi_primary_used, corr=sig_all)

    # the no-op identity is a property of the TRANSFORM itself (target-independent), so it is
    # measured once; the two target-dependent identities are measured PER ARM above
    no_op = QM.matched_foil_identity(b_te)

    zero_mass = {lab: round(float(np.mean(QM.total_zero_mass(banks[lab]))), 4)
                 for lab in (*QM.REAL_ARMS, *QM.CONTEST_FOILS, "zm_cond_copula",
                             "assembled_indep", "assembled_comonotone")}
    return {
        "scores": scores, "coverage": coverage, "pit_flatness": pit,
        "n_train": int(len(tr_p)), "n_test": int(len(te_p)),
        "atom_rate_train": round(QM.atom_rate(raw_tr), 4),
        "atom_rate_test": round(QM.atom_rate(raw_te), 4),
        "clamp": clamps, "clamp_served": clamp_served, "marginal_drift": drift,
        "targets": targets_summary, "resplice_edges": edges,
        # per-arm (the target-dependent identities + the per-leg table the gate reads for the
        # WINNER), and the target-independent no-op measured once
        "identities": identities, "matched_foil_no_op": no_op, "per_leg_crps": per_leg,
        # ⭐ THE PREMISE, MEASURED: which cell caps the atom, and by how much each leg under-prices
        # its own zero. NF-W7e named `QB|passing_yards` as the suspect off an 89-row serving proof.
        "leg_zero_mass_table": QM.leg_zero_mass_table(b_te, raw_te),
        # ⭐ the SAME table AFTER the primary arm's re-splice — the successor needs to know which
        # cells the raise-only clamp could not reach (the smoke found `attempts` already ABOVE its
        # realized rate, so no raise-only target can correct it) as well as which ones it fixed
        "leg_zero_mass_table_recalibrated": QM.leg_zero_mass_table(recal_primary, raw_te),
        "binding_leg_share_served": QM.binding_leg_share(b_te),
        "binding_leg_share_recalibrated": QM.binding_leg_share(recal_primary),
        "atom_cap": {
            "cap_served": round(QM.atom_cap(b_te), 4),
            "cap_recalibrated": round(QM.atom_cap(recal_primary), 4),
            "installed_atom_recalibrated": clamps[QM.PRIMARY_ARM]["mean_installed_atom"],
            "installed_atom_served": clamp_served["mean_installed_atom"],
            "clamp_binding_share_recalibrated": clamps[QM.PRIMARY_ARM]["clamp_binding_share"],
            "clamp_binding_share_served": clamp_served["clamp_binding_share"],
            "total_zero_mass_by_arm": zero_mass,
        },
        "sigma_all_note": {k: v for k, v in sig_all_note.items() if k != "loadings"},
    }


def run_fold(fold: WP.Fold, feat: pd.DataFrame, smap: dict, *, draws: int,
             positions: tuple[str, ...], matrix_key: str, rebuild_banks: bool = False) -> dict:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    cfg = LP.get_preset(GATE_LEAGUE)
    t_m = time.time()
    ctx_te, cache_state = _marginals_cached(fold.label, train, test, smap, matrix_key=matrix_key,
                                            rebuild=rebuild_banks)
    log.info("[W7f] fold %s marginals in %.1fs (test %d rows, cache %s)", fold.label,
             time.time() - t_m, len(test), cache_state)
    out: dict[str, dict] = {}
    for position in positions:
        FA.assert_assembly_is_priceable(cfg, position)
        t_p = time.time()
        out[position] = run_position(position, train, test, FA.leg_weights(cfg, position),
                                     draws=draws, ctx_te=ctx_te)
        log.info("[W7f] fold %s %s in %.1fs", fold.label, position, time.time() - t_p)
    log.info("[W7f] fold %s complete in %.1fs", fold.label, time.time() - t0)
    return {"label": fold.label, "n_test": int(len(test)), "positions": out,
            "bank_cache": cache_state}


# ── Selection (derived from stored fold scores — NF-W2e: zero refit cost) ────────────────────────
def _reproduction(usable: list[dict], position: str, foil: str,
                  record: dict[str, float] | None, who: str) -> dict:
    if not record:
        return {"reproduces": False, "n_folds_compared": 0, "max_abs_gap": None,
                "note": (f"the {who} record is absent or is a path proof — the reproduction "
                         f"control DID NOT RUN, which is never a pass (NF1.7 (a))")}
    return QM.incumbent_reproduction(
        {fr["label"]: fr["positions"][position]["scores"][foil] for fr in usable},
        {k.split("|", 1)[1]: v for k, v in record.items() if k.split("|", 1)[0] == position})


def select_position(fold_results: list[dict], position: str) -> dict | None:
    usable = _usable(fold_results, position)
    if len(usable) < 2:
        return None
    mat = pd.DataFrame({fr["label"]: fr["positions"][position]["scores"] for fr in usable}).T
    mean_s = mat.mean(axis=0)
    # ⭐ RANKED ON CRPS, NEVER ON PIT (QM.SELECTION_IS_CRPS_NOT_PIT — NF-W7d §4, inherited)
    winner = str(mean_s[list(QM.REAL_ARMS)].idxmin())
    best_foil = str(mean_s[list(QM.CONTEST_FOILS)].idxmin())
    deltas = (mat[best_foil] - mat[winner]).to_numpy(float)
    mean_d, lo, hi = KW.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(len(usable))
    defl = NF18.deflate(mat[list(QM.ELIGIBLE)], subset=list(QM.ELIGIBLE))
    trial_srs = []
    for arm in QM.REAL_ARMS:
        d = (mat[best_foil] - mat[arm]).to_numpy(float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
    pval = M14.onesided_paired_pvalue(deltas)
    perm_lift = (mat[best_foil] - mat["permuted_direct"]).to_numpy(float)
    p_perm = M14.onesided_paired_pvalue(perm_lift)
    zm_perm_lift = (mat[best_foil] - mat["zm_permuted"]).to_numpy(float)
    p_zm_perm = M14.onesided_paired_pvalue(zm_perm_lift)
    sd = float(np.nanstd(deltas, ddof=1))

    # the materiality yardstick for an oracle inversion is a tenth of the arm's claimed effect over
    # its MATCHED foil — here NF-W7e's own arm, which is what this story claims to improve on
    oracle_states = {a: QM.oracle_floor_state(mat[a], mat[f"oracle__{a}"], mat[f"matched_n__{a}"],
                                              indep_by_fold=mat[QM.MATCHED_FOIL])
                     for a in QM.REAL_ARMS}
    oracle_control = {f: QM.oracle_floor_state(mat[f], mat[f"oracle__{f}"], mat[f],
                                               indep_by_fold=mat[QM.MATCHED_FOIL])
                      for f in QM.FOILS_WITH_ORACLE}

    def _fold(path: tuple[str, ...]) -> list:
        out = []
        for fr in usable:
            node = fr["positions"][position]
            for k in path:
                node = node[k]
            out.append(node)
        return out

    atoms = [fr["positions"][position]["clamp"][winner]["mean_installed_atom"] for fr in usable]
    drifts = [d["max_probability_drift"] for d in _fold(("marginal_drift",))]
    clamp_binding = [fr["positions"][position]["clamp"][winner]["clamp_binding_share"]
                     for fr in usable]
    # ⭐ THE BINDING *SHARE* IS THE WRONG STATISTIC ONCE THE CAP MOVES — it counts rows where the
    # clamp was ACTIVE, not rows where it MATTERED, so it can stay byte-identical while the
    # distortion collapses (measured here: 0.9006 → 0.9006 while the mean move on π̂ fell 0.2602 →
    # 0.0022, a 118× reduction). Reporting the share alone reads as "nothing changed" and would
    # make this record's headline actively misleading, so the MAGNITUDE is reported beside it
    # (NF-D20: measure whether the mechanism could act, don't infer it from an activity count).
    clamp_move = [fr["positions"][position]["clamp"][winner]["mean_upward_move"] for fr in usable]
    clamp_move_served = [fr["positions"][position]["clamp_served"]["mean_upward_move"]
                         for fr in usable]
    caps_recal = _fold(("atom_cap", "cap_recalibrated"))
    caps_served = _fold(("atom_cap", "cap_served"))

    # ── the transform's three identities, pooled over folds ─────────────────────────────────────
    # ⭐ the two TARGET-DEPENDENT identities are read for the WINNER (the arm the gate anchors),
    # and the target-independent no-op once. A primary-only read would describe a different arm.
    zm_gap = max(d["identities"][winner]["zero_mass_hits_target"]["max_abs_gap"] for d in
                 (fr["positions"][position] for fr in usable))
    pl = [fr["positions"][position]["identities"][winner]["positive_law"] for fr in usable]
    pl_drift = max(d["max_drift_over_bound"] for d in pl)
    pl_evaluated = all(d["evaluated"] for d in pl)
    noop_gap = max(d["max_abs_draw_gap"] for d in _fold(("matched_foil_no_op",)))
    # per-leg calibration for the WINNER, pooled over the PRICED legs (the story may not buy the
    # assembled atom by wrecking the parts) — a fraction of the served banks' own CRPS, so scales
    # cannot hide a real degradation inside a yardage leg
    leg_tables = [fr["positions"][position]["per_leg_crps"][winner] for fr in usable]
    priced = list(leg_tables[0]["priced_legs"])
    served_tot = float(np.mean([t["served_crps_sum_priced"] for t in leg_tables]))
    recal_tot = float(np.mean([t["recalibrated_crps_sum_priced"] for t in leg_tables]))
    leg_frac = (recal_tot - served_tot) / max(served_tot, 1e-9)
    # ⭐ the availability decomposition, pooled over FOLDS and ROWS with the crossover LOCATED —
    # REPORTED, never gated: it is what lets a refusal name WHERE the per-leg damage lands rather
    # than only that it happened, and it is the successor's entire premise so it is measured on
    # every fold and for every ARM (a claim about one arm's sign flip is not a claim about the
    # mechanism). Pools sums/counts, never means-of-means (NF1.8).
    avail_by_arm = {
        a: QM.pool_availability_buckets(
            [fr["positions"][position]["per_leg_crps"][a]["priced_delta_by_availability"]
             for fr in usable])
        for a in QM.REAL_ARMS}
    avail_winner = avail_by_arm[winner]
    avail_by_leg = {
        leg: QM.pool_availability_buckets(
            [t["by_leg"][leg]["delta_by_availability"] for t in leg_tables])
        for leg in priced}
    leg_frac_by_arm = {a: round(float(np.mean(
        [fr["positions"][position]["per_leg_crps"][a]["relative_change"] for fr in usable])), 6)
        for a in QM.REAL_ARMS}

    # ⭐ CHANNEL ATTRIBUTION as PAIRED per-fold deltas, not ranks (NF-W7d (g′) / NF-D10): each
    # channel is the winner against a foil that keeps EVERYTHING except that one channel, so the
    # double-pricing story is a measured paired delta rather than a leaderboard position. REPORTED.
    def _paired(foil: str, arm: str) -> dict:
        """(foil − arm) per fold, so POSITIVE = `arm` is better. `vs` names the FOIL — the thing the
        channel is isolated against — because that is what a reader needs to interpret the sign."""
        d = (mat[foil] - mat[arm]).to_numpy(float)
        m, lo_, hi_ = KW.paired_ci95(d)
        return {"vs": foil, "arm": arm, "mean_delta": None if m is None else round(m, 5),
                "ci95": [None if lo_ is None else round(lo_, 5),
                         None if hi_ is None else round(hi_, 5)],
                "fold_wins": int((d > 0).sum()), "n_folds": int(len(d)),
                "p_one_sided": M14.onesided_paired_pvalue(d),
                "by_fold": [round(float(x), 5) for x in d]}

    channel_attribution = {
        # the zero-mass recalibration itself, joint construction byte-identical
        "recalibration_channel": _paired(QM.MATCHED_FOIL, winner),
        # ⭐ the AVAILABILITY-DERIVED content of the target: `zm_climatology` runs the identical
        # re-splice machinery from a ROW-BLIND target, so this pair isolates "the target knows who
        # probably played" from "the atom was raised at all" — the double-pricing channel
        "availability_derived_target_channel": _paired("zm_climatology", winner),
        # NF-W7e's own claim (the availability SPLIT on served marginals), on the same CRN
        "split_channel_on_served_marginals": _paired("single_copula", QM.MATCHED_FOIL),
        "note": ("each entry is (foil − winner) per fold, so POSITIVE means the winner is better. "
                 "A channel whose paired delta is indistinguishable from zero did not act, "
                 "regardless of where either arm ranks (NF-D20 — count whether the mechanism "
                 "could act before crediting it)."),
    }

    # ⭐ PER-FOLD SERIES — so "clears the PIT bar for the first time" is an N-of-8 claim and the
    # anchors are demonstrably scored on EVERY fold, not just pooled (NF1.8: a degenerate's PIT is
    # printed every run, which is what proves the bar was never promoted into a selection criterion)
    per_fold_series = {
        "folds": [fr["label"] for fr in usable],
        "crps": {lab: [round(float(mat.loc[fr["label"], lab]), 4) for fr in usable]
                 for lab in (winner, QM.MATCHED_FOIL, QM.INCUMBENT_FOIL, *QM.DEGENERATES,
                             "permuted_direct", "zm_permuted", f"oracle__{winner}",
                             f"matched_n__{winner}")},
        "pit_max_decile_dev": {
            lab: [round(float(fr["positions"][position]["pit_flatness"][lab]["max_decile_dev"]), 4)
                  for fr in usable]
            for lab in (winner, QM.MATCHED_FOIL, QM.INCUMBENT_FOIL, *QM.DEGENERATES)},
        "winner_pit_clears_bar_by_fold": [
            bool(fr["positions"][position]["pit_flatness"][winner]["max_decile_dev"]
                 <= QM.PIT_MAX_DECILE_DEV) for fr in usable],
        "incumbent_pit_clears_bar_by_fold": [
            bool(fr["positions"][position]["pit_flatness"][QM.INCUMBENT_FOIL]["max_decile_dev"]
                 <= QM.PIT_MAX_DECILE_DEV) for fr in usable],
        "priced_leg_relative_change_by_fold": [
            round(float(t["relative_change"]), 6) for t in leg_tables],
        "atom_cap_recalibrated_by_fold": [round(float(c), 4) for c in caps_recal],
        "atom_cap_served_by_fold": [round(float(c), 4) for c in caps_served],
    }

    base = predecessor_cap_baseline()
    cap_mean = float(np.mean(caps_recal))
    cap_lift = (cap_mean - base["atom_cap_mean"]) if base["available"] else None

    repro_inc = _reproduction(usable, position, QM.INCUMBENT_FOIL,
                              _record_scores(QM.INCUMBENT_RECORD_RELPATH, FA.STORY,
                                             QM.INCUMBENT_RECORD_ARM), FA.STORY)
    repro_pred = {f: _reproduction(usable, position, f,
                                   _record_scores(QM.PREDECESSOR_RECORD_RELPATH, QM.PREDECESSOR,
                                                  a), QM.PREDECESSOR)
                  for f, a in QM.PREDECESSOR_RECORD_ARMS.items()}

    pooled_cov = {lab: _pooled_coverage(usable, position, lab) for lab in QM.WATCHED}
    cov_w, cov_i = pooled_cov[winner], pooled_cov["assembled_indep"]
    cov_c = pooled_cov["assembled_comonotone"]

    def _pit_mean(label: str) -> float:
        return float(np.mean([fr["positions"][position]["pit_flatness"][label]["max_decile_dev"]
                              for fr in usable]))

    pit_by_label = {lab: round(_pit_mean(lab), 4) for lab in QM.WATCHED}
    pit_w = _pit_mean(winner)
    pooled = QM.pooled_pit([fr["positions"][position]["pit_flatness"][winner]["decile_counts"]
                            for fr in usable])
    n_per_fold = int(np.mean([fr["positions"][position]["n_test"] for fr in usable]))
    pit_null = QM.pit_null_reference(n_per_fold)

    anchors = {
        "degenerates_lose": bool(all(mean_s[d] > mean_s[winner] for d in QM.DEGENERATES)),
        "degenerate_detail": {d: round(float(mean_s[d]), 4) for d in QM.DEGENERATES},
        "degenerate_pit_detail": {d: pit_by_label[d] for d in QM.DEGENERATES},
        "winner_beats_permuted": bool(mean_s["permuted_direct"] > mean_s[winner]),
        "permuted_lift_not_significant": bool(
            float(np.nanmean(perm_lift)) <= 0 or (p_perm is not None and p_perm >= 0.05)),
        "winner_beats_zm_permuted": bool(mean_s["zm_permuted"] > mean_s[winner]),
        "oracle_floors_respected_at_matched_n": bool(all(
            oracle_states[a]["state"] != QM.ORACLE_VIOLATED for a in QM.REAL_ARMS)),
        "oracle_ceiling_evaluated": bool(
            any(oracle_states[a]["state"] == QM.ORACLE_RESPECTED for a in QM.REAL_ARMS)),
        "winner_oracle_state": oracle_states[winner]["state"],
        "foils_respect_own_oracle": bool(all(
            mean_s[f] > mean_s[f"oracle__{f}"] for f in QM.FOILS_WITH_ORACLE)),
        "mixture_is_active": bool(float(np.mean(atoms)) >= QM.MIN_MIXTURE_ATOM),
        "mixture_preserves_marginals": bool(max(drifts) <= QM.MAX_MARGINAL_DRIFT),
        "incumbent_reproduces": bool(repro_inc["reproduces"]),
        "predecessor_reproduces": bool(all(r["reproduces"] for r in repro_pred.values())),
        # ── the four clauses this story ADDS ───────────────────────────────────────────────────
        "zero_mass_hits_target": bool(zm_gap <= QM.ZERO_MASS_TOLERANCE),
        # ⛔ an UNEVALUABLE comparison (every cell's conditional law degenerate) is never a pass
        "positive_law_preserved": bool(pl_evaluated
                                       and pl_drift <= QM.MAX_POSITIVE_LAW_DRIFT_RATIO),
        "matched_foil_identity": bool(noop_gap <= QM.NO_OP_TOLERANCE),
        # ⛔ an UNAVAILABLE baseline is UNEVALUABLE, never a pass (NF1.7 (a))
        "cap_was_lifted": bool(cap_lift is not None and cap_lift >= QM.MIN_CAP_LIFT),
        "per_leg_calibration_not_degraded": bool(leg_frac <= QM.MAX_PER_LEG_CRPS_DEGRADATION),
    }
    dependence_checks = {
        "independence_under_disperses": bool(cov_i["coverage"] is not None
                                             and cov_i["coverage"] < cov_c["coverage"]),
        "dependence_moves_coverage": bool(cov_c["coverage"] > cov_i["coverage"]),
        "beats_indep_on_coverage": bool(cov_w["coverage"] > cov_i["coverage"]),
    }
    zero_mass = {lab: round(float(np.mean(
        [fr["positions"][position]["atom_cap"]["total_zero_mass_by_arm"][lab] for fr in usable])), 4)
        for lab in usable[0]["positions"][position]["atom_cap"]["total_zero_mass_by_arm"]}
    binding_served = _fold(("binding_leg_share_served",))
    binding_recal = _fold(("binding_leg_share_recalibrated",))

    def _pool_share(rows: list[dict]) -> dict[str, float]:
        keys = sorted({k for r in rows for k in r})
        return {k: round(float(np.mean([r.get(k, 0.0) for r in rows])), 4) for k in keys}

    return {
        "position": position, "winner": winner, "best_foil": best_foil,
        "gated": position in QM.GATE_POSITIONS, "n_folds_used": len(usable),
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
        "anchors": anchors, "oracle_detail": oracle_states,
        "oracle_activity_control": oracle_control,
        "permutation_detail": {
            "permuted_direct_lift_vs_foil_mean": round(float(np.nanmean(perm_lift)), 4),
            "permuted_direct_lift_p_one_sided": p_perm,
            "zm_permuted_lift_vs_foil_mean": round(float(np.nanmean(zm_perm_lift)), 4),
            "zm_permuted_lift_p_one_sided": p_zm_perm},
        "coverage": {"winner_coverage_80": cov_w["coverage"], "n_rows": cov_w["n_rows"],
                     "binomial_se": cov_w["binomial_se"],
                     "blocking_shortfall": cov_w["blocking_shortfall"]},
        "coverage_by_label": pooled_cov,
        "dependence_checks": dependence_checks,
        "pit_flatness_winner_max_decile_dev": round(pit_w, 4),
        "pit_flat_ok": bool(pit_w <= QM.PIT_MAX_DECILE_DEV),
        "pit_by_label": pit_by_label,
        "pit_pooled_rows": pooled,
        "pit_calibrated_null": pit_null,
        "pit_null_p_value": QM.pit_null_pvalue(pit_w, n_per_fold),
        "pit_winner_decile_freq": [
            round(float(v), 4) for v in np.mean(
                [fr["positions"][position]["pit_flatness"][winner]["decile_freq"]
                 for fr in usable], axis=0)],
        "mixture_detail": {
            "mean_installed_atom": round(float(np.mean(atoms)), 4),
            "atom_by_fold": [round(float(a), 4) for a in atoms],
            "mean_clamp_binding_share": round(float(np.mean(clamp_binding)), 4),
            "mean_clamp_upward_move": round(float(np.mean(clamp_move)), 5),
            "mean_clamp_upward_move_served": round(float(np.mean(clamp_move_served)), 5),
            "clamp_binding_share_served": round(float(np.mean(
                [fr["positions"][position]["clamp_served"]["clamp_binding_share"]
                 for fr in usable])), 4),
            "max_marginal_drift": round(float(max(drifts)), 5),
            "tolerance": QM.MAX_MARGINAL_DRIFT, "atom_floor": QM.MIN_MIXTURE_ATOM,
            "observed_atom_rate_test": round(float(np.mean(
                [fr["positions"][position]["atom_rate_test"] for fr in usable])), 4),
        },
        "incumbent_reproduction": repro_inc,
        "predecessor_reproduction": repro_pred,
        # ⭐ the transform's identities + the premise, pooled over folds
        "transform_detail": {
            "max_zero_mass_target_gap": round(float(zm_gap), 12),
            "zero_mass_tolerance": QM.ZERO_MASS_TOLERANCE,
            "max_positive_law_drift_over_resolution_bound": round(float(pl_drift), 6),
            "positive_law_tolerance_ratio": QM.MAX_POSITIVE_LAW_DRIFT_RATIO,
            "positive_law_evaluated": bool(pl_evaluated),
            "positive_law_last_fold": pl[-1],
            "max_matched_foil_draw_gap": round(float(noop_gap), 12),
            "identity_arm_read": winner,
            "targets_last_fold": usable[-1]["positions"][position]["targets"],
            "resplice_edges_last_fold": usable[-1]["positions"][position]["resplice_edges"],
        },
        "per_leg_detail": {
            "arm_read": winner,
            "priced_legs": priced,
            "served_crps_sum_priced": round(served_tot, 5),
            "recalibrated_crps_sum_priced": round(recal_tot, 5),
            "relative_change": round(float(leg_frac), 6),
            "tolerance": QM.MAX_PER_LEG_CRPS_DEGRADATION,
            # ⭐ REPORTED, never gated — where the per-leg effect lands, and how every arm fares
            "relative_change_by_arm": leg_frac_by_arm,
            "by_leg_last_fold": leg_tables[-1]["by_leg"],
        },
        # ⭐ PM capture 1 — the availability decomposition, pooled over folds AND rows, per arm and
        # per priced leg, with the sign crossover located. REPORTED; nothing gates on it.
        "availability_decomposition": {
            "arm_read": winner,
            "winner": avail_winner,
            "by_arm": avail_by_arm,
            "by_priced_leg": avail_by_leg,
            "note": ("positive = the recalibration IMPROVED that availability bucket. Buckets are "
                     "FIXED absolute π̂ edges (never per-fold quantiles), pooled as Σsums/Σcounts "
                     "so the 8-fold figure is a row-pooled mean (NF1.8). A bucket below "
                     f"{QM.MIN_BUCKET_ROWS} rows reports None and can never supply a crossover."),
        },
        # ⭐ PM capture 4 — each channel as a PAIRED per-fold delta against a foil that keeps
        # everything except that channel
        "channel_attribution": channel_attribution,
        # ⭐ PM captures 3 + 5 — the per-fold series for the winner, the reproduced incumbent, the
        # matched foil, every degenerate and both permutations
        "per_fold_series": per_fold_series,
        "premise_detail": {
            "leg_zero_mass_table_last_fold":
                usable[-1]["positions"][position]["leg_zero_mass_table"],
            # ⭐ PM capture 2 — the same table AFTER the re-splice, so the successor can see which
            # cells were reached and which the raise-only clamp structurally cannot correct
            "leg_zero_mass_table_recalibrated_last_fold":
                usable[-1]["positions"][position]["leg_zero_mass_table_recalibrated"],
            "binding_leg_share_served": _pool_share(binding_served),
            "binding_leg_share_recalibrated": _pool_share(binding_recal),
        },
        "atom_cap_detail": {
            "cap_served": round(float(np.mean(caps_served)), 4),
            "cap_recalibrated": round(cap_mean, 4),
            "cap_lift_vs_predecessor": None if cap_lift is None else round(float(cap_lift), 4),
            "predecessor_baseline": base,
            "min_cap_lift_required": QM.MIN_CAP_LIFT,
            "total_zero_mass_by_arm": zero_mass,
        },
        # ── attribution: the FULL 2×2 (marginals {recalibrated, served} × split {on, off}) ──────
        "attribution": {
            # THE CLAIM: the recalibration under the identical joint construction (matched foil)
            "recalibration_with_split": round(float(mean_s[QM.MATCHED_FOIL] - mean_s[winner]), 4),
            # the recalibration with the availability split OFF (reference cell)
            "recalibration_without_split": round(
                float(mean_s["single_copula"] - mean_s["zm_cond_copula"]), 4),
            # NF-W7e's own claim, re-scored on the same common random numbers
            "split_on_served_marginals": round(
                float(mean_s["single_copula"] - mean_s[QM.MATCHED_FOIL]), 4),
            "vs_incumbent": round(float(mean_s["single_copula"] - mean_s[winner]), 4),
            "delta_vs_indep": round(float(mean_s["assembled_indep"] - mean_s[winner]), 4),
            "beats_direct_points_REPORT_ONLY": bool(
                mean_s["foil_direct_points"] > mean_s[winner]),
            "delta_vs_direct_points_REPORT_ONLY": round(
                float(mean_s["foil_direct_points"] - mean_s[winner]), 4),
        },
    }


def compose_gate(sel: dict, fdr_pass: bool) -> dict:
    checks = {
        "beats_foil": bool(sel["beats_foil"]),
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < QM.PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= QM.DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
        "pit_flat_ok": bool(sel["pit_flat_ok"]),
        "degenerates_lose": bool(sel["anchors"]["degenerates_lose"]),
        "permutation_behaves": bool(sel["anchors"]["winner_beats_permuted"]
                                    and sel["anchors"]["permuted_lift_not_significant"]
                                    and sel["anchors"]["winner_beats_zm_permuted"]),
        "oracle_floors_respected": bool(sel["anchors"]["oracle_floors_respected_at_matched_n"]),
        "mixture_is_active": bool(sel["anchors"]["mixture_is_active"]),
        "mixture_preserves_marginals": bool(sel["anchors"]["mixture_preserves_marginals"]),
        "incumbent_reproduces": bool(sel["anchors"]["incumbent_reproduces"]),
        "predecessor_reproduces": bool(sel["anchors"]["predecessor_reproduces"]),
        "zero_mass_hits_target": bool(sel["anchors"]["zero_mass_hits_target"]),
        "positive_law_preserved": bool(sel["anchors"]["positive_law_preserved"]),
        "matched_foil_identity": bool(sel["anchors"]["matched_foil_identity"]),
        "cap_was_lifted": bool(sel["anchors"]["cap_was_lifted"]),
        "per_leg_calibration_not_degraded": bool(
            sel["anchors"]["per_leg_calibration_not_degraded"]),
        **{k: bool(v) for k, v in sel["dependence_checks"].items()},
    }
    return {"checks": checks, "ship": all(checks.values())}


def classify(sel: dict, checks: dict) -> dict:
    v = cv_power.classify_null(
        metric=f"nf_w7f_qb_marginal|{sel['position']}", n_folds=sel["n_folds_used"],
        n_arms=len(QM.REAL_ARMS), beats_foil=sel["beats_foil"],
        observed_sr=sel["observed_sr"], var_trials_sr=sel["var_trials_sr"],
        fold_wins=sel["fold_wins"], p_one_sided=sel["p_one_sided"], bh_cutoff=QM.FDR_Q,
        degenerates_excluded_from_v=True,
        declared_field_size=len(QM.REAL_ARMS),
    )
    base = KW.flag_unsafe_field_shrink(
        {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger,
         "field_remedy_admissible": getattr(v, "field_remedy_admissible", None),
         "declared_field_size_source": ("fp_qb_marginal_calibration.REAL_ARMS, committed in "
                                        "ablation_results/nf_w7f_preregistration.md §3 before "
                                        "any score"),
         "instrument_verdict": {"state": v.state, "reason": v.reason,
                                "retest_trigger": v.retest_trigger}},
        len(QM.REAL_ARMS))
    out = KW.coverage_constraint_refusal(sel, checks, base, mechanism=QM.REFUSAL_MECHANISM,
                                         remedy=QM.REFUSAL_REMEDY)
    if out is base:
        stat_fail = [c for c in QM.STATISTICAL_CHECKS if not checks.get(c, True)]
        anchor_fail = [c for c in QM.ANCHOR_CHECKS if not checks.get(c, True)]
        # ⭐ the mechanism-inactivity read comes FIRST: if the cap did not move, the contest passed
        # on nothing and the thesis is UNTESTED — not a null about QB (NF1.7 (a) / NF-D20)
        if not checks.get("cap_was_lifted", True):
            out = dict(base)
            out.update({
                "state": "UNDEFINED", "hand_corrected": True,
                "reason": ("the recalibration did NOT lift the marginal-admissible atom cap by the "
                           "pre-registered minimum, so every arm is effectively its own matched "
                           "foil and the field was scored on a knob that did not turn. This is a "
                           "HARNESS reading, never a finding about QB: the thesis is UNTESTED, not "
                           "refuted (NF1.7 (a) / NF-D20 — count whether the mechanism could act "
                           "before crediting or condemning it)."),
                "retest_trigger": None, "failing_anchor_checks": anchor_fail,
            })
        elif not stat_fail and anchor_fail:
            out = dict(base)
            out.update({
                "state": "CONSTRAINT_REFUSED", "hand_corrected": True,
                "reason": ("every statistical gate passed and the null rests entirely on "
                           f"anchor/registration clauses {anchor_fail} — more data cannot change "
                           "this verdict (NF-D18); the remedy is a different mechanism or a PM "
                           "decision, never more seasons."),
                "retest_trigger": None, "failing_anchor_checks": anchor_fail,
            })
        elif stat_fail == ["pit_flat_ok"]:
            out = dict(base)
            out.update({
                "state": "CONSTRAINT_REFUSED", "hand_corrected": True,
                "reason": (
                    f"every other gate is GREEN and the ship is refused by the pre-registered PIT "
                    f"flatness bar alone: {sel['pit_flatness_winner_max_decile_dev']} against "
                    f"{QM.PIT_MAX_DECILE_DEV}. A max-decile deviation against a FIXED bar is a "
                    f"deterministic constraint, not a sampling shortfall — more folds shrink "
                    f"nothing that would move it" + QM.REFUSAL_MECHANISM),
                "retest_trigger": QM.REFUSAL_REMEDY, "failing_statistical_checks": stat_fail,
            })
        elif anchor_fail:
            # ⭐ MIXED failure: a statistical gate AND an anchor/registration clause both fail. The
            # BINDING constraint is the one no `n` can move — buying seasons could clear the
            # statistical half and the ship would STILL be refused — so the state is the constraint
            # and the trigger is NONE. Publishing the instrument's "+N folds" here would send a
            # reader to buy data that cannot change the verdict (exactly the misleading direction
            # NF-D18 names). The statistical shortfall is REPORTED, never hidden, and the raw
            # instrument reading survives verbatim in `instrument_verdict`.
            out = dict(base)
            out.update({
                "state": "CONSTRAINT_REFUSED", "hand_corrected": True,
                "reason": (
                    f"the null rests on BOTH statistical checks {stat_fail} and "
                    f"anchor/registration clauses {anchor_fail}. The anchor half is not rescuable "
                    f"by data, so it BINDS: more folds could clear the statistical half and the "
                    f"ship would still be refused ⇒ no fold/season trigger is published "
                    f"(NF-D18). The statistical shortfall is recorded below and the instrument's "
                    f"own reading is kept verbatim in `instrument_verdict` for audit"
                    + QM.REFUSAL_MECHANISM),
                "retest_trigger": None,
                "failing_anchor_checks": anchor_fail,
                "failing_statistical_checks": stat_fail,
                "binding_half": "anchor",
            })
    out["pbo_state"] = (
        f"EVALUABLE — PBO over the {len(QM.ELIGIBLE)}-config eligible field "
        f"({len(QM.REAL_ARMS)} recalibration arms + {len(QM.CONTEST_FOILS)} contest foils); DSR "
        f"deflates over the {len(QM.REAL_ARMS)}-arm declared family (trial SRs from real arms only "
        f"— anchors, degenerates and the three REFERENCE foils never enter V; MH2.1 (a)).")
    out["gate_sensitivity"] = KW.gate_sensitivity(checks, waived=())
    return out


def marginal_cap_layer(selections: dict) -> dict:
    """The MARGINAL-CAP verdict, read on QB by the pre-registered rule."""
    sel = selections.get(QM.CAP_POSITION)
    if sel is None:
        return QM.marginal_cap_verdict(
            pit_by_arm={}, cap_mean=float("nan"), predecessor_cap_mean=float("nan"),
            realized_atom=float("nan"), installed_atom=float("nan"),
            clamp_binding_share=float("nan"), binding_legs={}, pit_matched_foil=None)
    d, base = sel["atom_cap_detail"], sel["atom_cap_detail"]["predecessor_baseline"]
    out = QM.marginal_cap_verdict(
        pit_by_arm={a: sel["pit_by_label"][a] for a in QM.REAL_ARMS},
        cap_mean=d["cap_recalibrated"],
        predecessor_cap_mean=(base["atom_cap_mean"] if base.get("available")
                              else float("nan")),
        realized_atom=sel["mixture_detail"]["observed_atom_rate_test"],
        installed_atom=sel["mixture_detail"]["mean_installed_atom"],
        clamp_binding_share=sel["mixture_detail"]["mean_clamp_binding_share"],
        binding_legs=sel["premise_detail"]["binding_leg_share_served"],
        pit_matched_foil=sel["pit_by_label"].get(QM.MATCHED_FOIL))
    # ⛔ REPORTED-ONLY, added AFTER the decisive run and changing no state (the verdict rule reads
    # the cap lift and the PIT, never these): the clamp's MAGNITUDE, because its binding SHARE is
    # invariant to the level it binds at and alone reads as "nothing changed". See the comment on
    # `clamp_move` in `select_position`.
    m = sel["mixture_detail"]
    out["clamp_mean_upward_move_winner"] = m.get("mean_clamp_upward_move")
    out["clamp_mean_upward_move_served"] = m.get("mean_clamp_upward_move_served")
    return out


def derive_verdict_layer(out: dict) -> dict:
    """⭐ Every decision re-derivable from the stored fold scores — no refit (NF-W2e / NF-W3)."""
    frs = out["fold_results"]
    scored = [p for p in QM.POSITIONS if _usable(frs, p)]
    sels = {p: select_position(frs, p) for p in scored}
    present = {p: s for p, s in sels.items() if s is not None}
    gated = {p: s for p, s in present.items() if p in QM.GATE_POSITIONS}
    fdr = M14.bh_fdr({f"fp|{p}": s["p_one_sided"] for p, s in gated.items()}, q=QM.FDR_Q)
    gates = {p: compose_gate(s, fdr.get(f"fp|{p}", False)) for p, s in gated.items()}
    nulls = {p: (None if gates[p]["ship"] else classify(gated[p], gates[p]["checks"]))
             for p in gated}
    ship = sorted(p for p in gated if gates[p]["ship"])
    out["selections"] = present
    attempted = sorted({p for fr in frs for p in fr["positions"]})
    out["unavailable_positions"] = sorted(set(attempted) - set(present))
    out["positions_not_run"] = sorted(set(QM.POSITIONS) - set(attempted))
    out["fdr"] = fdr
    out["gates"] = gates
    out["null_states"] = {p: n for p, n in nulls.items() if n}
    out["marginal_cap"] = marginal_cap_layer(present)
    out["verdict"] = {
        "story_verdict": "SHIP" if ship else "NULL",
        "gate_positions": list(QM.GATE_POSITIONS),
        "ship_positions": ship,
        "null_positions": {p: nulls[p]["state"] for p in gated if nulls[p]},
        "gate_league": GATE_LEAGUE,
        "declared_field_size": len(QM.REAL_ARMS),
        "bh_family_size": len(gated),
        "scope_note": ("⛔ QB ONLY — RB/WR/TE were NOT scored here and this record certifies "
                       "nothing about them (NF1.7 (a)); NF-W8's four-position optimizer input "
                       "additionally requires an RB certificate, a separate story."),
        "selection_key": QM.SELECTION_IS_CRPS_NOT_PIT,
        "marginal_cap_state": out["marginal_cap"]["state"],
        "joint_construction_held_fixed": QM.JOINT_CONSTRUCTION,
        "promote_blockers": list(QM.PROMOTE_BLOCKERS),
        "positions_with_unevaluated_oracle_ceiling": sorted(
            p for p, s in present.items() if not s["anchors"]["oracle_ceiling_evaluated"]),
        "winner_oracle_state": {p: s["anchors"]["winner_oracle_state"]
                                for p, s in present.items()},
    }
    return out


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:
    v, cap = out["verdict"], out["marginal_cap"]
    L = [f"# NF-W7f — the QB MARGINAL-layer zero-mass recalibration ({v['story_verdict']})", "",
         f"Generated {out['generated_at']} · gate position **{', '.join(v['gate_positions'])}** · "
         f"gate league **{GATE_LEAGUE}** · {out['n_folds']} folds · target `{QM.TARGET}` · "
         f"ranked on `{QM.SELECTION_METRIC}` · gated on `{QM.GATE_STATISTIC}`", "",
         f"⚖️ `best_alpha = 0` · **DEPLOY-HELD** · NF-G0 challenger. "
         f"Joint construction held FIXED at `{v['joint_construction_held_fixed']}` "
         f"(NF-W7e's registered arm) — the declared family varies the per-leg zero-mass TARGET and "
         f"nothing else.", "",
         f"> {v['scope_note']}", ""]
    if out.get("smoke"):
        L += ["> ⚠️ **PATH PROOF (`--smoke`)** — one fold, few draws. NOT a verdict: one fold "
              "cannot select, and the reproduction identities cannot hold at reduced draws by "
              "construction.", ""]

    L += ["## Marginal-cap verdict", "",
          f"**`{cap['state']}`** — {cap['reading']}", "",
          "| quantity | value |", "|---|---|",
          f"| atom cap, SERVED marginals (NF-W7e recorded) | {cap['atom_cap_mean_predecessor']} |",
          f"| atom cap, RECALIBRATED | {cap['atom_cap_mean']} |",
          f"| cap lift (required ≥ {cap['min_cap_lift_required']}) | {cap['cap_lift']} |",
          f"| installed atom | {cap['installed_atom']} |",
          f"| realized all-zero rate | {cap['realized_all_zero_rate']} |",
          f"| shortfall (realized − installed) | "
          f"{cap['atom_shortfall_installed_vs_realized']} |",
          f"| clamp binding SHARE (was {cap['clamp_binding_share_predecessor']}) | "
          f"{cap['clamp_binding_share']} ⚠️ see below |",
          f"| clamp mean upward move on π̂ — SERVED → winner | "
          f"{cap.get('clamp_mean_upward_move_served')} → "
          f"{cap.get('clamp_mean_upward_move_winner')} |",
          f"| PIT: best arm | `{cap['best_pit_arm']}` {cap['best_pit']} vs bar {cap['bar']} |",
          f"| PIT: matched foil (`{QM.MATCHED_FOIL}`) | {cap['pit_matched_foil']} |",
          f"| PIT moved by the recalibration | {cap['pit_moved_by_recalibration']} |", "",
          "**Which NF-W6d cell caps the atom** (share of rows attaining the row-wise "
          "`min_j P̂_j(0)`):", "",
          f"- SERVED: `{cap['binding_leg_share']}`", ""]

    for p, sel in out.get("selections", {}).items():
        g = out["gates"].get(p, {})
        checks = g.get("checks", {})
        L += [f"## {p} — winner `{sel['winner']}` vs best contest foil `{sel['best_foil']}`", "",
              f"Δ`crps_q199` **{sel['mean_delta']}** (CI95 {sel['ci95']}, "
              f"{sel['fold_wins']}/{sel['n_folds_used']} folds) · PBO {sel['pbo']} · "
              f"DSR {sel['dsr']} · p {sel['p_one_sided']} · "
              f"coverage(80) {sel['coverage']['winner_coverage_80']} (floor "
              f"{QM.COVERAGE_FLOOR}) · PIT {sel['pit_flatness_winner_max_decile_dev']} "
              f"(bar {QM.PIT_MAX_DECILE_DEV})", "",
              f"**Gate: {'SHIP' if g.get('ship') else 'NO'}** — "
              + ", ".join(f"{k} {'✅' if val else '❌'}" for k, val in checks.items()), "",
              "### Attribution (the 2×2: marginals × availability split)", "",
              "| contrast | Δ |", "|---|---|"]
        for k, val in sel["attribution"].items():
            L.append(f"| {k} | {val} |")
        L += ["", "### Mean CRPS by label", "", "| label | crps_q199 | PIT |", "|---|---|---|"]
        for lab, s in sorted(sel["mean_crps"].items(), key=lambda kv: kv[1]):
            L.append(f"| `{lab}` | {s} | {sel['pit_by_label'].get(lab, '—')} |")
        t = sel["transform_detail"]
        L += ["", "### The transform's measured identities", "",
              f"- `zero_mass_hits_target`: max gap {t['max_zero_mass_target_gap']} "
              f"(tol {t['zero_mass_tolerance']})",
              f"- `positive_law_preserved`: max drift / resolution bound "
              f"{t['max_positive_law_drift_over_resolution_bound']} (tol ≤ "
              f"{t['positive_law_tolerance_ratio']}; evaluated "
              f"{t['positive_law_evaluated']}) — {t['positive_law_last_fold']}",
              f"- `matched_foil_identity` (re-splice to own atom is a no-op through `draw_legs`): "
              f"max draw gap {t['max_matched_foil_draw_gap']}",
              f"- resplice edges (last fold): {t['resplice_edges_last_fold']}", "",
              "### Per-leg calibration (the story must not buy the atom by wrecking the parts)", "",
              f"- priced legs {sel['per_leg_detail']['priced_legs']}",
              f"- read for the SELECTED arm `{sel['per_leg_detail']['arm_read']}`: summed CRPS "
              f"served {sel['per_leg_detail']['served_crps_sum_priced']} → recalibrated "
              f"{sel['per_leg_detail']['recalibrated_crps_sum_priced']} (relative change "
              f"{sel['per_leg_detail']['relative_change']}, tolerance "
              f"{sel['per_leg_detail']['tolerance']})",
              f"- by arm: {sel['per_leg_detail']['relative_change_by_arm']}", ""]

        av = sel["availability_decomposition"]
        w_av = av["winner"]
        L += [f"### ⭐ Where the per-leg effect lands — the availability decomposition "
              f"(arm `{av['arm_read']}`)", "",
              f"**`{w_av['state']}`** — {w_av['reason']}", "",
              f"> {av['note']}", "",
              "| π̂ bucket | rows | pooled Δ (priced legs, per row) |", "|---|---|---|"]
        for k in range(len(w_av["edges"]) - 1):
            m = w_av["mean_delta"][k]
            L.append(f"| {w_av['edges'][k]}–{w_av['edges'][k + 1]} | {w_av['counts'][k]} | "
                     f"{'—' if m is None else m} |")
        L += ["", f"- crossovers: {w_av['crossovers']}",
              f"- pooled Δ over all buckets: {w_av['pooled_mean_delta']}",
              f"- state by arm: { {a: d['state'] for a, d in av['by_arm'].items()} }",
              f"- crossover π̂ by arm: "
              f"{ {a: [c['pi_hat'] for c in d['crossovers']] for a, d in av['by_arm'].items()} }",
              f"- state by priced leg: "
              f"{ {leg: d['state'] for leg, d in av['by_priced_leg'].items()} }", ""]

        ch = sel["channel_attribution"]
        L += ["### ⭐ Channel attribution (paired per-fold deltas, not ranks)", "",
              f"> {ch['note']}", "",
              "| channel | foil | Δ (foil − winner) | CI95 | folds | p |", "|---|---|---|---|---|---|"]
        for name, d in ch.items():
            if name == "note":
                continue
            L.append(f"| `{name}` | `{d['vs']}` | {d['mean_delta']} | {d['ci95']} | "
                     f"{d['fold_wins']}/{d['n_folds']} | {d['p_one_sided']} |")

        pf = sel["per_fold_series"]
        L += ["", "### ⭐ Per-fold series (the anchors are scored on every fold)", "",
              "| fold | " + " | ".join(f"`{lab}`" for lab in pf["crps"]) + " |",
              "|---|" + "---|" * len(pf["crps"])]
        for i, f in enumerate(pf["folds"]):
            L.append(f"| {f} | " + " | ".join(str(v[i]) for v in pf["crps"].values()) + " |")
        L += ["", "PIT (max-decile deviation) per fold — "
              f"bar {QM.PIT_MAX_DECILE_DEV}:", "",
              "| fold | " + " | ".join(f"`{lab}`" for lab in pf["pit_max_decile_dev"]) + " |",
              "|---|" + "---|" * len(pf["pit_max_decile_dev"])]
        for i, f in enumerate(pf["folds"]):
            L.append(f"| {f} | "
                     + " | ".join(str(v[i]) for v in pf["pit_max_decile_dev"].values()) + " |")
        L += ["", f"- winner clears the PIT bar on "
                  f"{sum(pf['winner_pit_clears_bar_by_fold'])}/{len(pf['folds'])} folds "
                  f"({pf['winner_pit_clears_bar_by_fold']})",
              f"- the reproduced incumbent clears it on "
              f"{sum(pf['incumbent_pit_clears_bar_by_fold'])}/{len(pf['folds'])} "
              f"({pf['incumbent_pit_clears_bar_by_fold']})",
              f"- priced-leg relative change by fold: "
              f"{pf['priced_leg_relative_change_by_fold']}",
              f"- atom cap by fold — served {pf['atom_cap_served_by_fold']} → recalibrated "
              f"{pf['atom_cap_recalibrated_by_fold']}", "",
              "### The premise, measured — per-leg predicted vs realized zero mass (last fold)", "",
              "| leg | predicted P(0) | realized P(0) | gap | AFTER re-splice | gap after |",
              "|---|---|---|---|---|---|"]
        after = sel["premise_detail"]["leg_zero_mass_table_recalibrated_last_fold"]
        for leg, row in sel["premise_detail"]["leg_zero_mass_table_last_fold"].items():
            a = after.get(leg, {})
            L.append(f"| `{leg}` | {row['predicted_zero_mass']} | {row['realized_zero_rate']} | "
                     f"{row['gap_realized_minus_predicted']} | "
                     f"{a.get('predicted_zero_mass', '—')} | "
                     f"{a.get('gap_realized_minus_predicted', '—')} |")
        L += ["", f"- binding-leg share, SERVED: "
                  f"{sel['premise_detail']['binding_leg_share_served']}",
              f"- binding-leg share, RECALIBRATED: "
              f"{sel['premise_detail']['binding_leg_share_recalibrated']}", "",
              "### Anchors", "",
              f"- degenerates (CRPS): {sel['anchors']['degenerate_detail']}",
              f"- degenerates (PIT — printed every run so the bar can never become a selection "
              f"criterion, NF1.8): {sel['anchors']['degenerate_pit_detail']}",
              f"- oracle states: "
              f"{ {a: d['state'] for a, d in sel['oracle_detail'].items()} }",
              f"- permutations: {sel['permutation_detail']}",
              f"- reproduction — incumbent {sel['incumbent_reproduction']}",
              f"- reproduction — predecessor {sel['predecessor_reproduction']}", ""]
        if p in out.get("null_states", {}):
            n = out["null_states"][p]
            L += [f"### Null state: `{n['state']}`", "", n["reason"], "",
                  f"- failing anchor/registration clauses: {n.get('failing_anchor_checks')}",
                  f"- failing statistical checks: {n.get('failing_statistical_checks')}",
                  f"- binding half: {n.get('binding_half', 'n/a')}",
                  f"- instrument's own reading (kept verbatim for audit): "
                  f"{n.get('instrument_verdict')}",
                  f"- retest trigger: {n.get('retest_trigger')}",
                  f"- `field_remedy_admissible`: {n.get('field_remedy_admissible')}",
                  f"- declared field size source: {n.get('declared_field_size_source')}", ""]

    L += ["## Promote blockers", ""] + [f"- {b}" for b in v["promote_blockers"]] + [""]
    path.write_text("\n".join(L))


# ── Orchestration ───────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-W7f — the QB marginal-layer zero-mass "
                                             "recalibration (§0.5)")
    ap.add_argument("--smoke", action="store_true",
                    help="path proof: 1 fold, few draws (artifact _smoke)")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="re-derive every verdict from the stored fold scores (zero refit)")
    ap.add_argument("--rebuild-cache", action="store_true", help="rebuild the W6d matrix cache")
    ap.add_argument("--rebuild-banks", action="store_true",
                    help="ignore the per-fold marginal-bank cache and refit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # cosmetic (NF-W7e's, inherited): the W6d serving dispatch predicts through a numpy view of a
    # frame the learner was fitted on with column names; sklearn warns once per predict call.
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    suffix = "_smoke" if args.smoke else ""
    art = _PROJECT_ROOT / _ARTIFACT_REL.replace(".json", f"{suffix}.json")

    if args.rewrite_report:
        out = derive_verdict_layer(json.loads(art.read_text()))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat()
        art.write_text(json.dumps(out, indent=2, default=str))
        write_report(out, art.with_suffix(".md"))
        log.info("NF-W7f report re-derived → %s", art.name)
        return 0

    FA.assert_stat_key_map()
    feat, pit_audit, attach = W6DA.build_matrix_w6d(SEASONS, rebuild_cache=args.rebuild_cache)
    gate_p, bake_p, def_p = W6DS.record_paths("")          # ALWAYS the FULL W6d records
    smap = SDSD.served_map(gate_p, bake_p, def_p)
    folds = WP.build_folds(feat)
    positions: tuple[str, ...] = QM.POSITIONS
    if args.smoke:
        folds = folds[-1:]
    draws = 300 if args.smoke else QM.ASSEMBLY_DRAWS
    matrix_key = W6DA.w6d_matrix_key(SEASONS)
    base = predecessor_cap_baseline()
    log.info("NF-W7f: %d folds × %d positions, %d legs, %d draws%s — cap baseline %s", len(folds),
             len(positions), QM.N_LEGS, draws, " [SMOKE]" if args.smoke else "",
             base.get("atom_cap_mean") if base["available"] else base["reason"])

    t0 = time.time()
    fold_results = [run_fold(f, feat, smap, draws=draws, positions=positions,
                             matrix_key=matrix_key, rebuild_banks=args.rebuild_banks)
                    for f in folds]
    out = {
        "story": QM.STORY, "phase": "qb_marginal_zero_mass_recalibration",
        "smoke": bool(args.smoke),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seasons": list(SEASONS), "n_folds": len(folds), "gate_league": GATE_LEAGUE,
        "gate_positions": list(QM.GATE_POSITIONS),
        "matrix_key": matrix_key, "pit_audit": pit_audit,
        "attach_audit": attach, "served_map_sources": {c: v["source"] for c, v in smap.items()},
        "assembly_draws": draws, "row_block": QM.ROW_BLOCK, "seed": QM._SEED,
        "seed_inherited_from": f"{FA.STORY} via {SA.PREDECESSOR} and {QM.PREDECESSOR}",
        "avail_stream_offset": QM.AVAIL_STREAM_OFFSET,
        "joint_construction_held_fixed": QM.JOINT_CONSTRUCTION,
        "pi_estimator": QM.PI_ESTIMATOR,
        "predecessor_cap_baseline": base,
        "declared_field": {"real_arms": list(QM.REAL_ARMS),
                           "primary_arm": QM.PRIMARY_ARM,
                           "contest_foils": list(QM.CONTEST_FOILS),
                           "reference_foils": list(QM.REFERENCE_FOILS),
                           "degenerates": list(QM.DEGENERATES), "anchors": list(QM.ANCHORS)},
        "labelling": {p: FA.assembled_labelling(smap, LP.get_preset(GATE_LEAGUE), p)
                      for p in positions},
        "fold_results": fold_results, "runtime_seconds": round(time.time() - t0, 1),
    }
    out = derive_verdict_layer(out)
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(json.dumps(out, indent=2, default=str))
    write_report(out, art.with_suffix(".md"))
    log.info("NF-W7f %s (marginal cap: %s) → %s (%.1fs)", out["verdict"]["story_verdict"],
             out["marginal_cap"]["state"], art.name, out["runtime_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
