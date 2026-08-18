"""run_nf_w7h_rb_marginal.py — NF-W7h §0.5: the RB MARGINAL-layer zero-mass recalibration, scored
against the SAME reproduced incumbent as NF-W7c/W7d/W7e/W7f and against RB's CRPS-best construction
on record.

Everything decidable in advance is a CONSTANT in `fp_rb_marginal_calibration.py`; this runner READS
it (NF-D16). The narrative pre-registration is committed at
`ablation_results/nf_w7h_preregistration.md` BEFORE the full run.

WHY THIS STORY EXISTS, AND WHY IT IS NOT A RE-RUN OF NF-W7f. NF-W7f cleared QB's assembled
calibration by recalibrating the QB legs' zero mass on the NF-W6d substrate. RB is the other
position NF-W8's four-position optimizer input needs, and it returned `GENUINE_ABSENCE` in both
NF-W7c and NF-W7e. But two quantities read off COMMITTED records make RB a different question, and
both are recorded in the pre-registration §0 before anything here scores:
  1. RB's assembled PIT ALREADY CLEARS (NF-W7e recorded 0.0242 against the 0.05 bar; QB was
     0.0640). So NF-W7f's headline rule would be VACUOUS at RB, and RB gets its own five-state
     rule (`RM.rb_marginal_verdict`) whose states are about the PROPER SCORE while HOLDING that
     calibration — including `RB_CALIBRATION_DAMAGED`, which QB's rule cannot express.
  2. RB's continuous cells OVER-price their zero on NF-W6d's committed serving proof
     (`receptions` −0.0923, `receiving_yards` −0.0707, `rushing_yards` −0.0647) while the splice is
     RAISE-ONLY, so it structurally cannot touch them. ⛔ A HYPOTHESIS off a 126-row proof — this
     runner MEASURES the same table at fold scale on EVERY fold and reports what actually bound the
     cap.

PIPELINE (one target — `league_fantasy_points` under NF-W7c's declared gate league; **RB ONLY**):
  · the matrix, folds, PIT gate, per-stat MARGINALS and league weights are NF-W7c/W7d/W7e/W7f's
    VERBATIM (the marginals through the NF-W6d SERVING DISPATCH — neither refit nor re-selected);
  · per fold: the served RB banks are RE-SPLICED to each arm's zero-mass target
    (`fp_qb_marginal_calibration.resplice_zero_mass`, imported BY IDENTITY), then assembled under
    ⭐ `mix_played` — RB's CRPS-best construction on record (learned π̂ + Σ on ACTIVE rows), NOT
    NF-W7e's `mixall_learned`, which NF-W7e measured as BEATEN at RB — against `mix_played` itself
    (the MATCHED foil, reproduced to 1e-9 vs NF-W7d) and `single_copula` (THE INCUMBENT, reproduced
    to 1e-9 vs NF-W7c), with `zm_cond_copula` and `mix_off` completing the reported 2×2, all on ONE
    base-normal block with every anchor;
  · a first-class DIAGNOSTIC per fold: each leg's predicted vs realized zero mass, which leg
    ATTAINS the row-wise minimum (i.e. which NF-W6d cell caps the atom), the cap before/after, and
    the clamp's binding SHARE *and* its mean MOVE (an activity count is not a magnitude — NF-W7f);
  · gate: crps_q199 vs the best CONTEST foil ∧ the fold clause ∧ PBO ∧ DSR ∧ BH-FDR ∧ the
    coverage(80) floor ∧ randomized-PIT flatness ≤ 0.05 ∧ degenerates / permutations / oracles ∧
    the three inherited DEPENDENCE clauses ∧ `mixture_is_active` ∧ `mixture_preserves_marginals` ∧
    `incumbent_reproduces` ∧ `predecessor_reproduces` ∧ the five clauses this family adds
    (`zero_mass_hits_target`, `positive_law_preserved`, `matched_foil_identity`, `cap_was_lifted`,
    `per_leg_calibration_not_degraded` — the last now MATERIALITY-thresholded from a DESIGN
    quantity, decided FORWARD in the pre-registration §6 and PROVEN not to rescue NF-W7f's own QB
    result);
  · the RB verdict, read by the pre-registered rule `RM.rb_marginal_verdict`.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: writes LOCAL artifacts only — no
`--publish`, no S3 client, no boto3, no dbt, no Dagster.

RUN (OPERATOR — LAPTOP; reads the S3 NFL lake read-only, writes local artifacts):

    # path proof: 1 fold, few draws (artifact _smoke) — no verdict. >2 min: OPERATOR.
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7h_rb_marginal --smoke

    # the decisive run (NF-W7f's QB equivalent took 3,366s; RB carries ~1.6× the test rows)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7h_rb_marginal

    # re-derive every verdict from the stored fold scores at ZERO refit cost (NF-W2e / NF-W3)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7h_rb_marginal \
        --rewrite-report

⭐ Per-fold MARGINAL BANKS are read from and written to **NF-W7e's cache directory**
(`artifacts/nf_w7e_bank_cache/`, gitignored), with NF-W7e's key function BY IDENTITY: the banks are
literally the same object (same matrix key, same served map, same fold labels), and this story
TRANSFORMS them rather than refitting them. So a machine that already ran NF-W7e/NF-W7f's decisive
run pays only for the draws. `--rebuild-banks` forces the fits. ⚠️ A FRESH `git worktree` has NO
cache (it is gitignored), so the first run there pays the full W6d dispatch.
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
    fp_rb_marginal_calibration as RM,
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

log = logging.getLogger("nfl.fantasy.nf_w7h")

SEASONS = W6DA.SEASONS
FEATURES = list(WP.FEATURES)
#: ⛔ NF-W7c's gate league, INHERITED through NF-W7d/W7e/W7f (E2.1-r).
GATE_LEAGUE = W7E.GATE_LEAGUE

_ARTIFACT_REL = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                 "nf_w7h_rb_marginal.json")

# The frame/marginal plumbing and the per-fold bank cache are the predecessors', BY IDENTITY —
# the banks this story re-splices must be the SAME object NF-W7e assembled, or the matched foil is
# not matched (a second cache with a second key is the NF-C0e wrong-key class).
realized_matrix = W7D.realized_matrix
bank_tensor = W7D.bank_tensor
_marginals_cached = W7E._marginals_cached
_usable = W7E._usable
_pooled_coverage = W7E._pooled_coverage
_record_scores = W7E._record_scores


# ── The cap baseline (read from the record, never trusted from a constant) ───────────────────────
def cap_baseline() -> dict:
    """NF-W7e's RECORDED **RB** atom-cap figures — the baseline `cap_was_lifted` is measured against.

    ⛔ Read from the committed record at run time, and REFUSED if the record is absent, a path proof,
    or carries no RB block: a cap lift measured against a hard-coded number could not notice that
    the predecessor's record had been regenerated, and "the mechanism acted" would then be a claim
    about a constant rather than about this run (the NF1.9-R `served_*`-column lesson — never trust
    a NAME for a MEASUREMENT).

    ⚠️ RB's cap lives in the PER-POSITION selection block (`selections.RB.atom_cap_detail.cap_mean`),
    NOT in the record's top-level `atom_cap`, which is NF-W7e's QB-only confirmation. Reading the
    top-level block here would silently baseline RB against QB's 0.2687 and manufacture a cap lift
    of ~0.28 out of nothing."""
    p = _PROJECT_ROOT / RM.CAP_BASELINE_RECORD_RELPATH
    if not p.exists():
        return {"available": False, "reason": f"{p.name} is absent — the cap-lift baseline could "
                                              f"not be read, so `cap_was_lifted` is UNEVALUABLE "
                                              f"and never a pass (NF1.7 (a))"}
    rec = json.loads(p.read_text())
    if rec.get("story") != RM.PREDECESSOR or rec.get("smoke"):
        return {"available": False, "reason": f"{p.name} is story {rec.get('story')} / smoke="
                                              f"{rec.get('smoke')} — a path proof is not a "
                                              f"baseline; REFUSED"}
    sel = (rec.get("selections") or {}).get(RM.CAP_POSITION) or {}
    cap = sel.get("atom_cap_detail") or {}
    mix = sel.get("mixture_detail") or {}
    if cap.get("cap_mean") is None:
        return {"available": False,
                "reason": f"{p.name} carries no `selections.{RM.CAP_POSITION}."
                          f"atom_cap_detail.cap_mean` — REFUSED rather than defaulted (NF1.7 (a))"}
    return {
        "available": True,
        "position": RM.CAP_POSITION,
        "source_path": f"selections.{RM.CAP_POSITION}.atom_cap_detail.cap_mean",
        "atom_cap_mean": float(cap["cap_mean"]),
        "installed_atom": float(mix.get("mean_installed_atom", float("nan"))),
        "realized_all_zero_rate": float(mix.get("observed_atom_rate_test", float("nan"))),
        "clamp_binding_share": float(mix.get("mean_clamp_binding_share", float("nan"))),
        "best_rb_pit": float(sel.get("pit_by_label", {}).get(RM.MATCHED_FOIL, float("nan"))),
        # ⭐ the record must still carry the numbers the pre-registration quoted; a mismatch means
        # the baseline moved under the committed floor and the reader must know (NF1.9-R)
        "matches_preregistered_constants": bool(
            abs(float(cap["cap_mean"]) - RM.PREDECESSOR_CAP_MEAN) <= 1e-4),
    }


def _per_leg_table(served: np.ndarray, recal: np.ndarray, y_leg: np.ndarray,
                   weights: np.ndarray, pi_hat: np.ndarray) -> dict:
    """Per-leg `crps_q199`, served vs recalibrated, plus ⭐ the AVAILABILITY DECOMPOSITION.

    The summed PRICED figure is what `per_leg_calibration_not_degraded` reads. The decomposition on
    FIXED absolute π̂ edges is REPORTED, never gated — and the fixed edges are load-bearing rather
    than stylistic: NF-W7f's headline mechanism claim was REFUTED by its own decisive run because a
    π̂-QUARTILE bucketing on a bimodal covariate fabricated a monotone gradient that did not exist."""
    out: dict[str, dict] = {}
    d_priced = np.zeros(len(y_leg), dtype=float)
    for i, leg in enumerate(RM.LEGS):
        s_row = KW.crps_dense(served[:, i, :], y_leg[:, i])
        r_row = KW.crps_dense(recal[:, i, :], y_leg[:, i])
        d = np.asarray(s_row, dtype=float) - np.asarray(r_row, dtype=float)   # >0 ⇒ improved
        priced_leg = bool(weights[i] != 0.0)
        if priced_leg:
            d_priced = d_priced + d
        out[leg] = {"served_crps": round(float(np.mean(s_row)), 5),
                    "recalibrated_crps": round(float(np.mean(r_row)), 5),
                    "delta": round(float(np.mean(d)), 5),
                    "delta_by_availability": RM.bucket_by_availability(d, pi_hat),
                    "priced": priced_leg}
    priced = [leg for leg, v in out.items() if v["priced"]]
    s_tot = sum(out[leg]["served_crps"] for leg in priced)
    r_tot = sum(out[leg]["recalibrated_crps"] for leg in priced)
    return {"by_leg": out, "priced_legs": priced,
            "served_crps_sum_priced": round(s_tot, 5),
            "recalibrated_crps_sum_priced": round(r_tot, 5),
            "relative_change": round((r_tot - s_tot) / max(s_tot, 1e-9), 6),
            "priced_delta_by_availability": RM.bucket_by_availability(d_priced, pi_hat)}


# ── One fold × position ─────────────────────────────────────────────────────────────────────────
def run_position(position: str, train: pd.DataFrame, test: pd.DataFrame, weights: np.ndarray, *,
                 draws: int, ctx_te: dict) -> dict:
    """Every arm, foil and anchor for one (fold, position), on ONE shared base-normal stream."""
    tr_p = train.loc[train["position"].astype(str) == position].reset_index(drop=True)
    te_p = test.loc[test["position"].astype(str) == position].reset_index(drop=True)
    if len(te_p) == 0 or len(tr_p) < RM.MIN_ESTIMATION_ROWS:
        return {"skipped": f"train {len(tr_p)} / test {len(te_p)} rows — below the estimation "
                           f"floor ({RM.MIN_ESTIMATION_ROWS}); REFUSED, not defaulted"}

    b_te = bank_tensor(ctx_te, position, len(te_p))          # the SERVED marginals, untouched
    raw_tr, raw_te = realized_matrix(tr_p), realized_matrix(te_p)
    y_te = FA.score_realized(raw_te, weights)

    # the matched-n capacity control (NF1.9 (f)): the most recent TRAIN rows sized to the test block
    n_match = max(len(te_p), RM.MIN_ESTIMATION_ROWS)
    m_tr = np.sort(np.argsort(tr_p["gw"].to_numpy(), kind="stable")[-n_match:])
    tr_m = tr_p.iloc[m_tr].reset_index(drop=True)
    raw_m = raw_tr[m_tr]
    # ⛔ EVERY estimation context must clear the floor, not just the train one. The conditional zero
    # rate AND Σ_played are estimated on ACTIVE rows in three contexts (train, the ORACLE's test
    # block, the matched-n slice) and each refuses below the floor — so a context that could not be
    # estimated must SKIP the fold with a named reason rather than raise mid-run and lose the other
    # folds (NF1.7 (a): a context that did not run is never a pass).
    thin = {name: int(RM.activity_indicator(r).sum())
            for name, r in (("train", raw_tr), ("oracle/test", raw_te), ("matched_n", raw_m))
            if int(RM.activity_indicator(r).sum()) < RM.MIN_ESTIMATION_ROWS}
    if thin:
        return {"skipped": f"these estimation contexts carry fewer ACTIVE {position} rows than the "
                           f"floor ({RM.MIN_ESTIMATION_ROWS}): {thin} — the conditional zero rate "
                           f"and Σ_played could not be estimated there, so this fold is REFUSED "
                           f"rather than scored (NF1.7 (a))"}

    # ── Σ: TWO estimators, and which construction gets which is the story's §2 decision.
    #  · `sig_played` (ACTIVE rows) — the pinned joint construction's Σ, used by EVERY real arm and
    #    by the matched foil `mix_played`, because RB's CRPS-best construction on record is
    #    NF-W7d's, whose Σ population is the played one (NF-W7e measured Σ_played WINNING at RB
    #    while Σ_all wins at QB/WR — this is the one substantive difference from NF-W7f's field).
    #  · `sig_all` (ALL rows) — the INCUMBENT's, needed verbatim so `single_copula` reproduces
    #    NF-W7c's `joint_rank` to 1e-9, and used by `zm_cond_copula` (the recalibrated marginals
    #    under the INCUMBENT's copula).
    # ⛔ BOTH are estimated on TRAIN for EVERY context, including the oracle's. The oracle peeks at
    # what THIS story ESTIMATES (π̂ and the two zero rates) and at NOTHING else: peeking Σ as well
    # would (a) change a factor the family holds fixed and (b) reproduce NF-W7e's own finding that
    # a Σ peeked on a small block LOSES more to sample size than the peek gains — which is how a
    # per-form floor goes INACTIVE (NF1.7 (b) / NF-D16 (g‴)).
    sig_played, sig_played_note = RM.sigma_played(raw_tr)
    sig_all, sig_all_note = FA.position_sigma(raw_tr)

    # the per-context estimation inputs: (frame the estimator sees, its raw matrix)
    ctxs = {"": (tr_p, raw_tr), "oracle__": (te_p, raw_te), "matched_n__": (tr_m, raw_m)}
    est_inputs: dict[str, dict] = {}
    for prefix, (frame, raw) in ctxs.items():
        est_inputs[prefix] = {
            "pi": RM.pi_for_arm(RM.PI_ESTIMATOR, frame, te_p, FEATURES, train_raw=raw),
            "cond": RM.conditional_zero_rate(raw),
            "marg": RM.marginal_zero_rate(raw),
        }

    # ⭐ the realized leg values AS THE DRAW PATH REALIZES THEM (clip at 0, round integer legs) —
    # the per-leg CRPS and the marginal's atom must be scored against the SAME event
    y_leg = np.clip(raw_te, 0.0, None)
    for i, leg in enumerate(RM.LEGS):
        if leg in RM.INTEGER_LEGS:
            y_leg[:, i] = np.rint(y_leg[:, i])

    banks: dict[str, np.ndarray] = {}
    clamps: dict[str, dict] = {}
    targets_summary: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    # ⛔ PER ARM, not just the primary. The identities depend on the arm's TARGET and the per-leg
    # clause is read for the WINNER — a table computed only for the primary would describe a
    # DIFFERENT arm than the gate anchors (NF1.7 (a)).
    identities: dict[str, dict] = {}
    per_leg: dict[str, dict] = {}
    recal_primary: np.ndarray | None = None
    for arm in RM.REAL_ARMS:
        for prefix, inp in est_inputs.items():
            t = RM.zero_targets(arm, banks=b_te, pi_hat=inp["pi"], cond_rate=inp["cond"],
                                marg_rate=inp["marg"])
            recal = RM.resplice_zero_mass(b_te, t)
            # ⭐ the clamp still runs — marginal preservation is not optional — but on the
            # RECALIBRATED banks, which is the whole point: the floor it enforces is now high
            # enough to admit the atom π̂ asks for.
            pi_used, note = RM.clamp_pi(inp["pi"], recal)
            banks[f"{prefix}{arm}"] = RM.assemble_mixture_bank(recal, weights, pi=pi_used,
                                                               corr=sig_played, draws=draws)
            if not prefix:
                clamps[arm] = note
                edges[arm] = RM.resplice_edges(b_te, t)
                identities[arm] = {
                    "zero_mass_hits_target": RM.zero_mass_hits_target(b_te, t, recal),
                    "positive_law": RM.positive_law_drift(b_te, recal),
                }
                per_leg[arm] = _per_leg_table(b_te, recal, y_leg, weights, inp["pi"])
                targets_summary[arm] = {
                    "mean": round(float(t.mean()), 4), "sd": round(float(t.std()), 4),
                    "mean_priced": round(float(np.mean(t[:, weights != 0.0])), 4)
                    if np.any(weights != 0.0) else None,
                    "atom_cap_after": round(RM.atom_cap(recal), 4),
                }
                if arm == RM.PRIMARY_ARM:
                    recal_primary, t_primary, pi_primary = recal, t, inp["pi"]
    if recal_primary is None:
        raise ValueError(f"{position}: the primary arm `{RM.PRIMARY_ARM}` produced no train-context "
                         f"recalibration — the foils, the permutation anchor and every identity "
                         f"diagnostic would describe a different splice than the arm they anchor")

    # ── The CONTEST foils.
    #  · `mix_played` = the IDENTICAL joint construction (learned π̂ + Σ_played) on the SERVED
    #    marginals — the MATCHED foil, so `mix_played − zm_*` is the recalibration and nothing else.
    #  · `single_copula` = NF-W7c's incumbent (one Gaussian copula at Σ_all, no split).
    pi_served_used, clamp_served = RM.clamp_pi(est_inputs[""]["pi"], b_te)
    banks[RM.MATCHED_FOIL] = RM.assemble_mixture_bank(b_te, weights, pi=pi_served_used,
                                                      corr=sig_played, draws=draws)
    banks["single_copula"] = FA.assemble_fp_bank(b_te, weights, corr=sig_all, draws=draws)
    # the reported 2×2's other cells (REFERENCE, never gated):
    #  · `zm_cond_copula` — the recalibrated marginals with the availability split OFF: does a
    #    raised atom pay when nothing makes it COMMON across legs?
    #  · `mix_off` — Σ_played with the split OFF (NF-W7d's reference cell), which is what makes the
    #    split channel isolable at a FIXED Σ here (the §12 pre-score amendment).
    banks["zm_cond_copula"] = FA.assemble_fp_bank(recal_primary, weights, corr=sig_all, draws=draws)
    banks["mix_off"] = FA.assemble_fp_bank(b_te, weights, corr=sig_played, draws=draws)
    banks["assembled_indep"] = FA.assemble_fp_bank(b_te, weights, mode="indep", draws=draws)
    banks["assembled_comonotone"] = FA.assemble_fp_bank(b_te, weights, mode="comonotone",
                                                        draws=draws)

    # the zero-mass permutation anchor — the PRIMARY arm's per-row inactivity shuffled across
    # players within a global week, used consistently in the marginal target AND the mixture: the
    # population LEVEL of the atom is preserved, only its per-ROW assignment is destroyed
    pi_perm = KW.permute_within_group(pi_primary, te_p["gw"].to_numpy())
    t_perm = RM.zero_targets(RM.PRIMARY_ARM, banks=b_te, pi_hat=pi_perm,
                             cond_rate=est_inputs[""]["cond"], marg_rate=est_inputs[""]["marg"])
    recal_perm = RM.resplice_zero_mass(b_te, t_perm)
    pi_perm_used, _ = RM.clamp_pi(pi_perm, recal_perm)
    banks["zm_permuted"] = RM.assemble_mixture_bank(recal_perm, weights, pi=pi_perm_used,
                                                    corr=sig_played, draws=draws)

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

    missing = sorted(set(RM.ALL_LABELS) - set(banks))
    if missing:
        raise ValueError(f"{position}: the declared field is incomplete — {missing} produced no "
                         f"predictive. A field scored with an arm silently missing is not the "
                         f"declared field (NF1.7 (a)).")

    scores: dict[str, float] = {}
    for label, bank in banks.items():
        KW.assert_finite_predictive(bank, f"{position}/{label}")
        scores[label] = float(np.mean(KW.crps_dense(bank, y_te)))
    coverage = {lab: KW.coverage80_dense(banks[lab], y_te) for lab in RM.WATCHED}
    pit = {lab: RM.pit_detail(KW.randomized_pit_from_bank(banks[lab], y_te)) for lab in RM.WATCHED}

    # the marginal-preservation diagnostic on the PRIMARY arm's own clamped π over ITS recalibrated
    # banks (one code path); the Σ is the pinned construction's, so the diagnostic describes the
    # construction the arms actually use
    pi_primary_used, _ = RM.clamp_pi(pi_primary, recal_primary)
    drift = RM.mixture_marginal_drift(recal_primary, pi=pi_primary_used, corr=sig_played)

    # the no-op identity is a property of the TRANSFORM itself (target-independent), so it is
    # measured once; the two target-dependent identities are measured PER ARM above
    no_op = RM.matched_foil_identity(b_te)

    zero_mass = {lab: round(float(np.mean(RM.total_zero_mass(banks[lab]))), 4)
                 for lab in (*RM.REAL_ARMS, *RM.CONTEST_FOILS, "zm_cond_copula", "mix_off",
                             "assembled_indep", "assembled_comonotone")}
    return {
        "scores": scores, "coverage": coverage, "pit_flatness": pit,
        "n_train": int(len(tr_p)), "n_test": int(len(te_p)),
        "atom_rate_train": round(RM.atom_rate(raw_tr), 4),
        "atom_rate_test": round(RM.atom_rate(raw_te), 4),
        "clamp": clamps, "clamp_served": clamp_served, "marginal_drift": drift,
        "targets": targets_summary, "resplice_edges": edges,
        "identities": identities, "matched_foil_no_op": no_op, "per_leg_crps": per_leg,
        # ⭐ THE PREMISE, MEASURED at fold scale: which cell caps the atom, and by how much each leg
        # under- or OVER-prices its own zero. §0.2 predicts RB's continuous cells OVER-price theirs.
        "leg_zero_mass_table": RM.leg_zero_mass_table(b_te, raw_te),
        # ⭐ the SAME table AFTER the primary arm's re-splice — the successor needs to know which
        # cells the RAISE-ONLY clamp could not reach as well as which ones it moved
        "leg_zero_mass_table_recalibrated": RM.leg_zero_mass_table(recal_primary, raw_te),
        "binding_leg_share_served": RM.binding_leg_share(b_te),
        "binding_leg_share_recalibrated": RM.binding_leg_share(recal_primary),
        "atom_cap": {
            "cap_served": round(RM.atom_cap(b_te), 4),
            "cap_recalibrated": round(RM.atom_cap(recal_primary), 4),
            "installed_atom_recalibrated": clamps[RM.PRIMARY_ARM]["mean_installed_atom"],
            "installed_atom_served": clamp_served["mean_installed_atom"],
            "clamp_binding_share_recalibrated": clamps[RM.PRIMARY_ARM]["clamp_binding_share"],
            "clamp_binding_share_served": clamp_served["clamp_binding_share"],
            "total_zero_mass_by_arm": zero_mass,
        },
        "sigma_played_note": {k: v for k, v in sig_played_note.items() if k != "loadings"},
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
    log.info("[W7h] fold %s marginals in %.1fs (test %d rows, cache %s)", fold.label,
             time.time() - t_m, len(test), cache_state)
    out: dict[str, dict] = {}
    for position in positions:
        FA.assert_assembly_is_priceable(cfg, position)
        t_p = time.time()
        out[position] = run_position(position, train, test, FA.leg_weights(cfg, position),
                                     draws=draws, ctx_te=ctx_te)
        log.info("[W7h] fold %s %s in %.1fs", fold.label, position, time.time() - t_p)
    log.info("[W7h] fold %s complete in %.1fs", fold.label, time.time() - t0)
    return {"label": fold.label, "n_test": int(len(test)), "positions": out,
            "bank_cache": cache_state}


# ── Selection (derived from stored fold scores — NF-W2e: zero refit cost) ────────────────────────
def _reproduction(usable: list[dict], position: str, foil: str,
                  record: dict[str, float] | None, who: str) -> dict:
    if not record:
        return {"reproduces": False, "n_folds_compared": 0, "max_abs_gap": None,
                "note": (f"the {who} record is absent or is a path proof — the reproduction "
                         f"control DID NOT RUN, which is never a pass (NF1.7 (a))")}
    return RM.incumbent_reproduction(
        {fr["label"]: fr["positions"][position]["scores"][foil] for fr in usable},
        {k.split("|", 1)[1]: v for k, v in record.items() if k.split("|", 1)[0] == position})


def select_position(fold_results: list[dict], position: str) -> dict | None:
    usable = _usable(fold_results, position)
    if len(usable) < 2:
        return None
    mat = pd.DataFrame({fr["label"]: fr["positions"][position]["scores"] for fr in usable}).T
    mean_s = mat.mean(axis=0)
    # ⭐ RANKED ON CRPS, NEVER ON PIT (RM.SELECTION_IS_CRPS_NOT_PIT — NF-W7d §4, inherited)
    winner = str(mean_s[list(RM.REAL_ARMS)].idxmin())
    best_foil = str(mean_s[list(RM.CONTEST_FOILS)].idxmin())
    deltas = (mat[best_foil] - mat[winner]).to_numpy(float)
    mean_d, lo, hi = KW.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(len(usable))
    defl = NF18.deflate(mat[list(RM.ELIGIBLE)], subset=list(RM.ELIGIBLE))
    trial_srs = []
    for arm in RM.REAL_ARMS:
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

    # ⭐ ONE PEEKING ORACLE PER FORM, at MATCHED n (NF-D16 (g‴) + NF1.9 (f)) — the arms nest, so a
    # single field-wide ceiling would veto a legitimately-better nested form as a false inversion.
    # The materiality yardstick for an inversion is a tenth of the arm's claimed effect over its
    # MATCHED foil — here `mix_played`, the construction this story claims to improve on.
    oracle_states = {a: RM.oracle_floor_state(mat[a], mat[f"oracle__{a}"], mat[f"matched_n__{a}"],
                                              indep_by_fold=mat[RM.MATCHED_FOIL])
                     for a in RM.REAL_ARMS}
    oracle_control = {f: RM.oracle_floor_state(mat[f], mat[f"oracle__{f}"], mat[f],
                                               indep_by_fold=mat[RM.MATCHED_FOIL])
                      for f in RM.FOILS_WITH_ORACLE}

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
    # ⭐ THE BINDING *SHARE* IS THE WRONG STATISTIC ALONE — it counts rows where the clamp was
    # ACTIVE, not rows where it MATTERED, so it can stay byte-identical while the distortion
    # collapses (NF-W7f measured 0.917 → 0.917 while the mean move on π̂ fell 112×). The MAGNITUDE
    # is reported beside it (NF-D20: measure whether the mechanism could act, don't infer it from
    # an activity count).
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
    leg_tables = [fr["positions"][position]["per_leg_crps"][winner] for fr in usable]
    priced = list(leg_tables[0]["priced_legs"])
    served_tot = float(np.mean([t["served_crps_sum_priced"] for t in leg_tables]))
    recal_tot = float(np.mean([t["recalibrated_crps_sum_priced"] for t in leg_tables]))
    leg_frac = (recal_tot - served_tot) / max(served_tot, 1e-9)
    # ⭐ the per-leg clause is now MATERIALITY-thresholded (prereg §6, decided FORWARD): a refusal
    # needs the degradation to be DEMONSTRABLE (a majority of folds) AND MATERIAL (≥ 1/10 of the
    # arm's own claimed effect, both on relative scales). The per-FOLD degradation count is what
    # makes "demonstrable" a measurement rather than a mean's sign.
    leg_frac_by_fold = [float(t["relative_change"]) for t in leg_tables]
    degraded_folds = int(sum(1 for x in leg_frac_by_fold if x > 0.0))
    matched_foil_mean = float(mean_s[RM.MATCHED_FOIL])
    rel_claimed_effect = (float(mean_s[RM.MATCHED_FOIL] - mean_s[winner]) / matched_foil_mean
                          if matched_foil_mean > 1e-12 else float("nan"))
    per_leg_verdict = RM.per_leg_degradation_verdict(
        relative_change=leg_frac, relative_claimed_effect=rel_claimed_effect,
        degraded_folds=degraded_folds, n_folds=len(usable))
    # ⭐ the availability decomposition, pooled over FOLDS and ROWS on FIXED absolute edges with the
    # crossover LOCATED — REPORTED, never gated. Pools sums/counts, never means-of-means (NF1.8).
    avail_by_arm = {
        a: RM.pool_availability_buckets(
            [fr["positions"][position]["per_leg_crps"][a]["priced_delta_by_availability"]
             for fr in usable])
        for a in RM.REAL_ARMS}
    avail_winner = avail_by_arm[winner]
    avail_by_leg = {
        leg: RM.pool_availability_buckets(
            [t["by_leg"][leg]["delta_by_availability"] for t in leg_tables])
        for leg in priced}
    leg_frac_by_arm = {a: round(float(np.mean(
        [fr["positions"][position]["per_leg_crps"][a]["relative_change"] for fr in usable])), 6)
        for a in RM.REAL_ARMS}

    # ⭐ CHANNEL ATTRIBUTION as PAIRED per-fold deltas, not ranks (NF-D15 (g′) / NF-D10): each
    # channel is the winner against a foil that keeps EVERYTHING except that one channel. REPORTED.
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
        "recalibration_channel": _paired(RM.MATCHED_FOIL, winner),
        # ⭐ the AVAILABILITY-DERIVED content of the target: `zm_climatology` runs the identical
        # re-splice machinery from a ROW-BLIND target, so this pair isolates "the target knows who
        # probably played" from "the atom was raised at all"
        "availability_derived_target_channel": _paired("zm_climatology", winner),
        # ⭐ the availability SPLIT at a FIXED Σ_played (the §12 amendment's whole point) — ⛔ NOT
        # `single_copula − mix_played`, which at RB bundles the split AND the Σ population
        "split_channel_at_fixed_sigma_played": _paired("mix_off", RM.MATCHED_FOIL),
        "note": ("each entry is (foil − arm) per fold, so POSITIVE means the arm is better. "
                 "A channel whose paired delta is indistinguishable from zero did not act, "
                 "regardless of where either arm ranks (NF-D20 — count whether the mechanism "
                 "could act before crediting it)."),
    }

    # ⭐ PER-FOLD SERIES — so an N-of-8 claim is checkable and the anchors are demonstrably scored on
    # EVERY fold (NF1.8: a degenerate's PIT is printed every run, which is what proves the bar was
    # never promoted into a selection criterion)
    per_fold_series = {
        "folds": [fr["label"] for fr in usable],
        "crps": {lab: [round(float(mat.loc[fr["label"], lab]), 4) for fr in usable]
                 for lab in (winner, RM.MATCHED_FOIL, RM.INCUMBENT_FOIL, *RM.DEGENERATES,
                             "permuted_direct", "zm_permuted", f"oracle__{winner}",
                             f"matched_n__{winner}")},
        "pit_max_decile_dev": {
            lab: [round(float(fr["positions"][position]["pit_flatness"][lab]["max_decile_dev"]), 4)
                  for fr in usable]
            for lab in (winner, RM.MATCHED_FOIL, RM.INCUMBENT_FOIL, *RM.DEGENERATES)},
        "winner_pit_clears_bar_by_fold": [
            bool(fr["positions"][position]["pit_flatness"][winner]["max_decile_dev"]
                 <= RM.PIT_MAX_DECILE_DEV) for fr in usable],
        # ⭐ at RB the MATCHED FOIL's per-fold clearance is the load-bearing series, because RB's
        # calibration ALREADY cleared: the question is whether the recalibration KEEPS it, not
        # whether it wins it (prereg §0.1)
        "matched_foil_pit_clears_bar_by_fold": [
            bool(fr["positions"][position]["pit_flatness"][RM.MATCHED_FOIL]["max_decile_dev"]
                 <= RM.PIT_MAX_DECILE_DEV) for fr in usable],
        "incumbent_pit_clears_bar_by_fold": [
            bool(fr["positions"][position]["pit_flatness"][RM.INCUMBENT_FOIL]["max_decile_dev"]
                 <= RM.PIT_MAX_DECILE_DEV) for fr in usable],
        "priced_leg_relative_change_by_fold": [round(float(x), 6) for x in leg_frac_by_fold],
        "atom_cap_recalibrated_by_fold": [round(float(c), 4) for c in caps_recal],
        "atom_cap_served_by_fold": [round(float(c), 4) for c in caps_served],
    }

    base = cap_baseline()
    cap_mean = float(np.mean(caps_recal))
    cap_lift = (cap_mean - base["atom_cap_mean"]) if base["available"] else None

    repro_inc = _reproduction(usable, position, RM.INCUMBENT_FOIL,
                              _record_scores(RM.INCUMBENT_RECORD_RELPATH, FA.STORY,
                                             RM.INCUMBENT_RECORD_ARM), FA.STORY)
    # ⚠️ `REPRODUCTION_RECORD_STORY` (NF-W7d), NOT `PREDECESSOR` (NF-W7e): `_record_scores`
    # refuses a record whose `story` does not match and returns None, which makes the control
    # report "DID NOT RUN" forever — a silently never-running control (NF1.7 (a)).
    repro_pred = {f: _reproduction(usable, position, f,
                                   _record_scores(RM.PREDECESSOR_RECORD_RELPATH,
                                                  RM.REPRODUCTION_RECORD_STORY, a),
                                   RM.REPRODUCTION_RECORD_STORY)
                  for f, a in RM.PREDECESSOR_RECORD_ARMS.items()}

    pooled_cov = {lab: _pooled_coverage(usable, position, lab) for lab in RM.WATCHED}
    cov_w, cov_i = pooled_cov[winner], pooled_cov["assembled_indep"]
    cov_c = pooled_cov["assembled_comonotone"]

    def _pit_mean(label: str) -> float:
        return float(np.mean([fr["positions"][position]["pit_flatness"][label]["max_decile_dev"]
                              for fr in usable]))

    pit_by_label = {lab: round(_pit_mean(lab), 4) for lab in RM.WATCHED}
    pit_w = _pit_mean(winner)
    pooled = RM.pooled_pit([fr["positions"][position]["pit_flatness"][winner]["decile_counts"]
                            for fr in usable])
    n_per_fold = int(np.mean([fr["positions"][position]["n_test"] for fr in usable]))
    pit_null = RM.pit_null_reference(n_per_fold)

    anchors = {
        "degenerates_lose": bool(all(mean_s[d] > mean_s[winner] for d in RM.DEGENERATES)),
        "degenerate_detail": {d: round(float(mean_s[d]), 4) for d in RM.DEGENERATES},
        "degenerate_pit_detail": {d: pit_by_label[d] for d in RM.DEGENERATES},
        "winner_beats_permuted": bool(mean_s["permuted_direct"] > mean_s[winner]),
        "permuted_lift_not_significant": bool(
            float(np.nanmean(perm_lift)) <= 0 or (p_perm is not None and p_perm >= 0.05)),
        "winner_beats_zm_permuted": bool(mean_s["zm_permuted"] > mean_s[winner]),
        "oracle_floors_respected_at_matched_n": bool(all(
            oracle_states[a]["state"] != RM.ORACLE_VIOLATED for a in RM.REAL_ARMS)),
        "oracle_ceiling_evaluated": bool(
            any(oracle_states[a]["state"] == RM.ORACLE_RESPECTED for a in RM.REAL_ARMS)),
        "winner_oracle_state": oracle_states[winner]["state"],
        "foils_respect_own_oracle": bool(all(
            mean_s[f] > mean_s[f"oracle__{f}"] for f in RM.FOILS_WITH_ORACLE)),
        "mixture_is_active": bool(float(np.mean(atoms)) >= RM.MIN_MIXTURE_ATOM),
        "mixture_preserves_marginals": bool(max(drifts) <= RM.MAX_MARGINAL_DRIFT),
        "incumbent_reproduces": bool(repro_inc["reproduces"]),
        "predecessor_reproduces": bool(all(r["reproduces"] for r in repro_pred.values())),
        # ── the five clauses this family adds ──────────────────────────────────────────────────
        "zero_mass_hits_target": bool(zm_gap <= RM.ZERO_MASS_TOLERANCE),
        # ⛔ an UNEVALUABLE comparison (every cell's conditional law degenerate) is never a pass
        "positive_law_preserved": bool(pl_evaluated
                                       and pl_drift <= RM.MAX_POSITIVE_LAW_DRIFT_RATIO),
        "matched_foil_identity": bool(noop_gap <= RM.NO_OP_TOLERANCE),
        # ⛔ an UNAVAILABLE baseline is UNEVALUABLE, never a pass (NF1.7 (a))
        "cap_was_lifted": bool(cap_lift is not None and cap_lift >= RM.MIN_CAP_LIFT),
        # ⭐ the materiality-thresholded clause (prereg §6); `holds` is False for an UNEVALUABLE
        # read as well as for a refusal, so an unevaluable clause is never a pass
        "per_leg_calibration_not_degraded": bool(per_leg_verdict["holds"]),
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
        "gated": position in RM.GATE_POSITIONS, "n_folds_used": len(usable),
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
        "pit_flat_ok": bool(pit_w <= RM.PIT_MAX_DECILE_DEV),
        "pit_by_label": pit_by_label,
        "pit_pooled_rows": pooled,
        "pit_calibrated_null": pit_null,
        "pit_null_p_value": RM.pit_null_pvalue(pit_w, n_per_fold),
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
            "tolerance": RM.MAX_MARGINAL_DRIFT, "atom_floor": RM.MIN_MIXTURE_ATOM,
            "observed_atom_rate_test": round(float(np.mean(
                [fr["positions"][position]["atom_rate_test"] for fr in usable])), 4),
        },
        "incumbent_reproduction": repro_inc,
        "predecessor_reproduction": repro_pred,
        "transform_detail": {
            "max_zero_mass_target_gap": round(float(zm_gap), 12),
            "zero_mass_tolerance": RM.ZERO_MASS_TOLERANCE,
            "max_positive_law_drift_over_resolution_bound": round(float(pl_drift), 6),
            "positive_law_tolerance_ratio": RM.MAX_POSITIVE_LAW_DRIFT_RATIO,
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
            # ⭐ the FORWARD-decided materiality verdict, with every input reported so a reader can
            # re-derive under another rule (NF-D14)
            "verdict": per_leg_verdict,
            "relative_claimed_effect": round(float(rel_claimed_effect), 8),
            "degraded_folds": degraded_folds,
            "relative_change_by_fold": [round(float(x), 6) for x in leg_frac_by_fold],
            "materiality_fraction": RM.PER_LEG_MATERIALITY_FRACTION,
            "relative_change_by_arm": leg_frac_by_arm,
            "by_leg_last_fold": leg_tables[-1]["by_leg"],
        },
        "availability_decomposition": {
            "arm_read": winner,
            "winner": avail_winner,
            "by_arm": avail_by_arm,
            "by_priced_leg": avail_by_leg,
            "note": ("positive = the recalibration IMPROVED that availability bucket. Buckets are "
                     "FIXED absolute π̂ edges (never per-fold quantiles), pooled as Σsums/Σcounts "
                     "so the 8-fold figure is a row-pooled mean (NF1.8). A bucket below "
                     f"{RM.MIN_BUCKET_ROWS} rows reports None and can never supply a crossover."),
        },
        "channel_attribution": channel_attribution,
        "per_fold_series": per_fold_series,
        "premise_detail": {
            "leg_zero_mass_table_last_fold":
                usable[-1]["positions"][position]["leg_zero_mass_table"],
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
            "min_cap_lift_required": RM.MIN_CAP_LIFT,
            "total_zero_mass_by_arm": zero_mass,
        },
        # ── attribution: the reported 2×2 (marginals {recalibrated, served} × split {on, off}) ──
        "attribution": {
            # THE CLAIM: the recalibration under the identical joint construction (matched foil)
            "recalibration_with_split": round(float(mean_s[RM.MATCHED_FOIL] - mean_s[winner]), 4),
            # the recalibration with the availability split OFF (both at Σ_all — reference cell)
            "recalibration_without_split": round(
                float(mean_s["single_copula"] - mean_s["zm_cond_copula"]), 4),
            # ⭐ the SPLIT at a FIXED Σ_played — the clean channel at RB (§12 amendment)
            "split_at_fixed_sigma_played": round(
                float(mean_s["mix_off"] - mean_s[RM.MATCHED_FOIL]), 4),
            # ⚠️ BUNDLED, and named so: at RB this differs in the split AND the Σ population
            "vs_incumbent_construction_BUNDLED": round(
                float(mean_s["single_copula"] - mean_s[RM.MATCHED_FOIL]), 4),
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
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < RM.PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= RM.DSR_MIN,
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
    """The null state, with the repo's standing hand-corrections applied at REPORT time and the
    instrument's own reading kept VERBATIM for audit (`--rewrite-report` re-derives it at zero
    refit cost — NF-W2e / NF-W3)."""
    v = cv_power.classify_null(
        metric=f"nf_w7h_rb_marginal|{sel['position']}", n_folds=sel["n_folds_used"],
        n_arms=len(RM.REAL_ARMS), beats_foil=sel["beats_foil"],
        observed_sr=sel["observed_sr"], var_trials_sr=sel["var_trials_sr"],
        fold_wins=sel["fold_wins"], p_one_sided=sel["p_one_sided"], bh_cutoff=RM.FDR_Q,
        degenerates_excluded_from_v=True,
        # ⭐ MH2.7: the DECLARED field, sourced to the committed pre-registration, so the machine
        # flag `field_remedy_admissible` is an AUDITABLE claim rather than a post-hoc field size.
        declared_field_size=RM.DECLARED_FIELD_SIZE,
    )
    base = KW.flag_unsafe_field_shrink(
        {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger,
         "field_remedy_admissible": getattr(v, "field_remedy_admissible", None),
         "declared_field_size_source": RM.DECLARED_FIELD_SIZE_SOURCE,
         "instrument_verdict": {"state": v.state, "reason": v.reason,
                                "retest_trigger": v.retest_trigger}},
        RM.DECLARED_FIELD_SIZE)
    out = KW.coverage_constraint_refusal(sel, checks, base, mechanism=RM.REFUSAL_MECHANISM,
                                         remedy=RM.REFUSAL_REMEDY)
    if out is base:
        stat_fail = [c for c in RM.STATISTICAL_CHECKS if not checks.get(c, True)]
        anchor_fail = [c for c in RM.ANCHOR_CHECKS if not checks.get(c, True)]
        # ⭐ the mechanism-inactivity read comes FIRST: if the cap did not move, the contest passed
        # on nothing and the thesis is UNTESTED — not a null about RB (NF1.7 (a) / NF-D20)
        if not checks.get("cap_was_lifted", True):
            out = dict(base)
            out.update({
                "state": "UNDEFINED", "hand_corrected": True,
                "reason": ("the recalibration did NOT lift the marginal-admissible atom cap by the "
                           "pre-registered minimum, so every arm is effectively its own matched "
                           "foil and the field was scored on a knob that did not turn. This is a "
                           "HARNESS reading, never a finding about RB: the thesis is UNTESTED, not "
                           "refuted (NF1.7 (a) / NF-D20 — count whether the mechanism could act "
                           "before crediting or condemning it). ⛔ NO re-test trigger is published: "
                           "the RAISE-ONLY splice cannot reach a cell that already OVER-prices its "
                           "zero, and no fold count changes that."),
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
                "binding_half": "anchor",
            })
        elif stat_fail == ["pit_flat_ok"]:
            out = dict(base)
            out.update({
                "state": "CONSTRAINT_REFUSED", "hand_corrected": True,
                "reason": (
                    f"every other gate is GREEN and the ship is refused by the pre-registered PIT "
                    f"flatness bar alone: {sel['pit_flatness_winner_max_decile_dev']} against "
                    f"{RM.PIT_MAX_DECILE_DEV}. ⚠️ At RB that is a LOSS, not a shortfall: NF-W7e "
                    f"recorded RB's matched foil ALREADY clearing at "
                    f"{RM.PREDECESSOR_BEST_RB_PIT}, so the recalibration COST calibration RB had. "
                    f"A max-decile deviation against a FIXED bar is a deterministic constraint, "
                    f"not a sampling shortfall — more folds shrink nothing that would move it"
                    + RM.REFUSAL_MECHANISM),
                "retest_trigger": RM.REFUSAL_REMEDY, "failing_statistical_checks": stat_fail,
            })
        elif anchor_fail:
            # ⭐ MIXED failure: a statistical gate AND an anchor/registration clause both fail. The
            # BINDING constraint is the one no `n` can move — buying seasons could clear the
            # statistical half and the ship would STILL be refused — so the state is the constraint
            # and the trigger is NONE. Publishing the instrument's "+N folds" here would send a
            # reader to buy data that cannot change the verdict (the misleading direction NF-D18
            # names). The statistical shortfall is REPORTED, never hidden, and the raw instrument
            # reading survives verbatim in `instrument_verdict`.
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
                    + RM.REFUSAL_MECHANISM),
                "retest_trigger": None,
                "failing_anchor_checks": anchor_fail,
                "failing_statistical_checks": stat_fail,
                "binding_half": "anchor",
            })
    out["pbo_state"] = (
        f"EVALUABLE — PBO over the {len(RM.ELIGIBLE)}-config eligible field "
        f"({len(RM.REAL_ARMS)} recalibration arms + {len(RM.CONTEST_FOILS)} contest foils); DSR "
        f"deflates over the {len(RM.REAL_ARMS)}-arm declared family (trial SRs from real arms only "
        f"— anchors, degenerates and the four REFERENCE foils never enter V; MH2.1 (a)).")
    out["gate_sensitivity"] = KW.gate_sensitivity(checks, waived=())
    # ⭐ THE DSR 2×2, computed and REPORTED as a labelled DIAGNOSTIC before any remedy is named
    # (prereg §9). NF-W7f measured that a coherent re-registration cut V 8.8× and moved DSR only
    # 0.0 → 0.174, because the binding quantity was per-fold NOISE, not multiplicity — so "the
    # field did it" is a HYPOTHESIS to measure, never a reflex.
    if not checks.get("dsr_ok", True):
        out["dsr_diagnostic"] = dsr_field_diagnostic(sel)
    return out


def dsr_field_diagnostic(sel: dict) -> dict:
    """⭐ The FIELD half of the DSR 2×2 — computed only when `dsr_ok` fails, and REPORTED as a
    labelled diagnostic that names no remedy on its own (prereg §9).

    `SR0 = √V · z(N)` is taxed through TWO channels: the trial COUNT `N` and the cross-trial Sharpe
    DISPERSION `V` that a far-out arm inflates. This measures what a COHERENT sub-field (the declared
    family minus its single most extreme trial Sharpe) would do to `V` — and then reads whether DSR
    actually MOVES. ⛔ It is NOT a licence to re-cut the field: MH2.2 is explicit that you may
    PRE-REGISTER a family and may not DISCOVER one, and this story's field is committed in
    `ablation_results/nf_w7h_preregistration.md` §3. The number exists so the record can say WHICH
    lever binds — multiplicity or variance — rather than prescribing the reflex."""
    srs = np.asarray(sel.get("trial_srs") or [], dtype=float)
    obs = sel.get("observed_sr")
    if srs.size < 3 or obs is None:
        return {"evaluated": False,
                "reason": ("fewer than 3 trial Sharpes or no observed SR — the field/variance "
                           "decomposition is UNEVALUABLE, never read as either lever (NF1.7 (a))"),
                "declared_field_size": RM.DECLARED_FIELD_SIZE}
    v_declared = float(np.var(srs, ddof=1))
    drop = int(np.argmax(np.abs(srs - float(np.mean(srs)))))
    trimmed = np.delete(srs, drop)
    v_coherent = float(np.var(trimmed, ddof=1)) if trimmed.size > 1 else float("nan")
    dsr_coherent = M14.deflated_sharpe(np.asarray(sel["deltas_by_fold"], dtype=float), trimmed)
    ratio = (v_declared / v_coherent) if np.isfinite(v_coherent) and v_coherent > 1e-12 else None
    moved = (None if dsr_coherent is None or sel.get("dsr") is None
             else round(float(dsr_coherent - sel["dsr"]), 4))
    if dsr_coherent is not None and dsr_coherent >= RM.DSR_MIN:
        lever = "MULTIPLICITY"
        reading = ("a coherent sub-field CLEARS the bar ⇒ the declared field's heterogeneity is "
                   "what refuses this arm. ⛔ That is a HYPOTHESIS about the FIELD, not a licence "
                   "to trim it (MH2.2): the admissible remedy is a FRESH, forward pre-registration "
                   "of a coherent family, never a post-hoc re-cut of a field already scored.")
    else:
        lever = "VARIANCE"
        reading = ("removing the most extreme trial Sharpe collapses V but DSR still does not "
                   "clear ⇒ the binding quantity is PER-FOLD NOISE in the delta, not multiplicity "
                   "(NF-W7f measured exactly this: V fell 8.8× and DSR reached only 0.174). The "
                   "honest lever is a LOWER-VARIANCE design — more assembly draws / a sharper "
                   "metric — ⛔ NOT more seasons and ⛔ NOT a field trim.")
    return {
        "evaluated": True, "lever": lever, "reading": reading,
        "declared_field_size": RM.DECLARED_FIELD_SIZE,
        "declared_field_size_source": RM.DECLARED_FIELD_SIZE_SOURCE,
        "dsr_declared_field": sel.get("dsr"), "dsr_coherent_subfield": dsr_coherent,
        "dsr_moved_by_coherence": moved, "dsr_bar": RM.DSR_MIN,
        "v_declared_field": round(v_declared, 6),
        "v_coherent_subfield": (None if not np.isfinite(v_coherent) else round(v_coherent, 6)),
        "v_ratio_declared_over_coherent": (None if ratio is None else round(ratio, 3)),
        "dropped_trial_index": drop, "dropped_trial_arm": RM.REAL_ARMS[drop],
        "observed_sr": obs, "trial_srs": [round(float(s), 3) for s in srs],
        "note": ("REPORTED as a diagnostic. The gate binds on the DECLARED 4-arm field; this row "
                 "exists so the record names WHICH lever binds rather than prescribing a reflex."),
    }


def rb_verdict_layer(selections: dict) -> dict:
    """The RB verdict, read by the pre-registered five-state rule."""
    sel = selections.get(RM.CAP_POSITION)
    if sel is None:
        return RM.rb_marginal_verdict(
            pit_by_arm={}, cap_mean=float("nan"), predecessor_cap_mean=float("nan"),
            realized_atom=float("nan"), installed_atom=float("nan"),
            clamp_binding_share=float("nan"), clamp_mean_move=None, binding_legs={},
            pit_matched_foil=None, beats_both_foils=None)
    d, base = sel["atom_cap_detail"], sel["atom_cap_detail"]["predecessor_baseline"]
    m = sel["mixture_detail"]
    # ⭐ "beats BOTH contest foils" is read from the MEANS, not from `beats_foil` alone: `beats_foil`
    # binds against the BEST foil only, and the RB rule's PAYS state requires the winner to beat
    # every contest foil (prereg §7) — the two coincide when the best foil is the hardest, and
    # reading the means makes that a measurement rather than an assumption.
    beats_both = bool(all(sel["mean_crps"][f] > sel["mean_crps"][sel["winner"]]
                          for f in RM.CONTEST_FOILS))
    return RM.rb_marginal_verdict(
        pit_by_arm={a: sel["pit_by_label"][a] for a in RM.REAL_ARMS},
        cap_mean=d["cap_recalibrated"],
        predecessor_cap_mean=(base["atom_cap_mean"] if base.get("available") else float("nan")),
        realized_atom=m["observed_atom_rate_test"],
        installed_atom=m["mean_installed_atom"],
        clamp_binding_share=m["mean_clamp_binding_share"],
        clamp_mean_move=m.get("mean_clamp_upward_move"),
        binding_legs=sel["premise_detail"]["binding_leg_share_served"],
        pit_matched_foil=sel["pit_by_label"].get(RM.MATCHED_FOIL),
        beats_both_foils=beats_both)


def derive_verdict_layer(out: dict) -> dict:
    """⭐ Every decision re-derivable from the stored fold scores — no refit (NF-W2e / NF-W3)."""
    frs = out["fold_results"]
    scored = [p for p in RM.POSITIONS if _usable(frs, p)]
    sels = {p: select_position(frs, p) for p in scored}
    present = {p: s for p, s in sels.items() if s is not None}
    gated = {p: s for p, s in present.items() if p in RM.GATE_POSITIONS}
    fdr = M14.bh_fdr({f"fp|{p}": s["p_one_sided"] for p, s in gated.items()}, q=RM.FDR_Q)
    gates = {p: compose_gate(s, fdr.get(f"fp|{p}", False)) for p, s in gated.items()}
    nulls = {p: (None if gates[p]["ship"] else classify(gated[p], gates[p]["checks"]))
             for p in gated}
    ship = sorted(p for p in gated if gates[p]["ship"])
    out["selections"] = present
    attempted = sorted({p for fr in frs for p in fr["positions"]})
    out["unavailable_positions"] = sorted(set(attempted) - set(present))
    out["positions_not_run"] = sorted(set(RM.POSITIONS) - set(attempted))
    out["fdr"] = fdr
    out["gates"] = gates
    out["null_states"] = {p: n for p, n in nulls.items() if n}
    out["marginal_cap"] = rb_verdict_layer(present)
    out["verdict"] = {
        "story_verdict": "SHIP" if ship else "NULL",
        "gate_positions": list(RM.GATE_POSITIONS),
        "ship_positions": ship,
        "null_positions": {p: nulls[p]["state"] for p in gated if nulls[p]},
        "gate_league": GATE_LEAGUE,
        "declared_field_size": RM.DECLARED_FIELD_SIZE,
        "bh_family_size": len(gated),
        "scope_note": ("⛔ RB ONLY — QB/WR/TE were NOT scored here and this record certifies "
                       "nothing about them (NF1.7 (a)). NF-W8's four-position optimizer input is a "
                       "CROSS-POSITION ranking, so an RB certificate alone does not unblock it "
                       "(NF-W7c §4)."),
        "selection_key": RM.SELECTION_IS_CRPS_NOT_PIT,
        "rb_verdict_state": out["marginal_cap"]["state"],
        "joint_construction_held_fixed": RM.JOINT_CONSTRUCTION,
        "promote_blockers": list(RM.PROMOTE_BLOCKERS),
        "positions_with_unevaluated_oracle_ceiling": sorted(
            p for p, s in present.items() if not s["anchors"]["oracle_ceiling_evaluated"]),
        "winner_oracle_state": {p: s["anchors"]["winner_oracle_state"]
                                for p, s in present.items()},
    }
    return out


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:
    v, cap = out["verdict"], out["marginal_cap"]
    L = [f"# NF-W7h — the RB MARGINAL-layer zero-mass recalibration ({v['story_verdict']})", "",
         f"Generated {out['generated_at']} · gate position **{', '.join(v['gate_positions'])}** · "
         f"gate league **{GATE_LEAGUE}** · {out['n_folds']} folds · target `{RM.TARGET}` · "
         f"ranked on `{RM.SELECTION_METRIC}` · gated on `{RM.GATE_STATISTIC}`", "",
         f"⚖️ `best_alpha = 0` · **DEPLOY-HELD** · NF-G0 challenger. "
         f"Joint construction held FIXED at `{v['joint_construction_held_fixed']}` "
         f"(NF-W7d's registered primary — RB's CRPS-best construction on record, ⛔ NOT NF-W7e's "
         f"`mixall_learned`, which NF-W7e measured as BEATEN at RB) — the declared family varies "
         f"the per-leg zero-mass TARGET and nothing else.", "",
         f"> {v['scope_note']}", "",
         "> ⭐ **RB IS NOT A RE-RUN OF NF-W7f.** NF-W7e recorded RB's assembled PIT at "
         f"**{RM.PREDECESSOR_BEST_RB_PIT}** against the {RM.PIT_MAX_DECILE_DEV} bar — it ALREADY "
         "CLEARS, where QB's 0.0640 did not. So the registered question is not *does the "
         "recalibration repair RB's calibration* (there is nothing to repair) but *does removing "
         "the marginal-admissibility constraint improve RB's PROPER SCORE while HOLDING that "
         "calibration*. The verdict rule below has five states, including "
         "`RB_CALIBRATION_DAMAGED`, which QB's rule structurally cannot express.", ""]
    if out.get("smoke"):
        L += ["> ⚠️ **PATH PROOF (`--smoke`)** — one fold, few draws. NOT a verdict: one fold "
              "cannot select, and the reproduction identities cannot hold at reduced draws by "
              "construction.", ""]

    L += ["## RB verdict", "",
          f"**`{cap['state']}`** — {cap['reading']}", "",
          "| quantity | value |", "|---|---|",
          f"| atom cap, SERVED marginals (NF-W7e recorded, RB) | "
          f"{cap['atom_cap_mean_predecessor']} |",
          f"| atom cap, RECALIBRATED | {cap['atom_cap_mean']} |",
          f"| cap lift (required ≥ {cap['min_cap_lift_required']}) | {cap['cap_lift']} |",
          f"| — the floor's derivation | {cap['min_cap_lift_derivation']} |",
          f"| installed atom | {cap['installed_atom']} |",
          f"| realized all-zero rate | {cap['realized_all_zero_rate']} |",
          f"| shortfall (realized − installed) | "
          f"{cap['atom_shortfall_installed_vs_realized']} |",
          f"| clamp binding SHARE (was {cap['clamp_binding_share_predecessor']}) | "
          f"{cap['clamp_binding_share']} ⚠️ a share is not a magnitude — see the next row |",
          f"| clamp mean UPWARD MOVE on π̂ (the magnitude) | {cap['clamp_mean_upward_move']} |",
          f"| PIT: best arm | `{cap['best_pit_arm']}` {cap['best_pit']} vs bar {cap['bar']} |",
          f"| PIT: matched foil (`{RM.MATCHED_FOIL}`) | {cap['pit_matched_foil']} |",
          f"| PIT: already cleared BEFORE this story (NF-W7e) | "
          f"{cap['pit_predecessor_already_cleared']} |",
          f"| PIT moved by the recalibration | {cap['pit_moved_by_recalibration']} |",
          f"| winner beats BOTH contest foils | {cap['beats_both_foils']} |", "",
          "**Which NF-W6d cell caps the atom** (share of rows attaining the row-wise "
          "`min_j P̂_j(0)`):", "",
          f"- SERVED: `{cap['binding_leg_share']}`", ""]

    for p, sel in out.get("selections", {}).items():
        g = out["gates"].get(p, {})
        checks = g.get("checks", {})
        pld = sel["per_leg_detail"]
        L += [f"## {p} — winner `{sel['winner']}` vs best contest foil `{sel['best_foil']}`", "",
              f"Δ`crps_q199` **{sel['mean_delta']}** (CI95 {sel['ci95']}, "
              f"{sel['fold_wins']}/{sel['n_folds_used']} folds) · PBO {sel['pbo']} · "
              f"DSR {sel['dsr']} · p {sel['p_one_sided']} · "
              f"coverage(80) {sel['coverage']['winner_coverage_80']} (floor "
              f"{RM.COVERAGE_FLOOR}) · PIT {sel['pit_flatness_winner_max_decile_dev']} "
              f"(bar {RM.PIT_MAX_DECILE_DEV})", "",
              f"**Gate: {'SHIP' if g.get('ship') else 'NO'}** — "
              + ", ".join(f"{k} {'✅' if val else '❌'}" for k, val in checks.items()), "",
              "### Attribution (the reported 2×2: marginals × availability split)", "",
              "| contrast | Δ |", "|---|---|"]
        for k, val in sel["attribution"].items():
            L.append(f"| {k} | {val} |")
        L += ["", "> ⚠️ `vs_incumbent_construction_BUNDLED` differs in the SPLIT **and** the Σ "
              "population, because RB's pinned construction estimates Σ on ACTIVE rows while the "
              "incumbent uses all rows. `split_at_fixed_sigma_played` is the clean split channel "
              "here (the §12 pre-score amendment).", "",
              "### Mean CRPS by label", "", "| label | crps_q199 | PIT |", "|---|---|---|"]
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
              "### Per-leg calibration — the FORWARD-decided materiality clause", "",
              "> The gating question was resolved FIRST (prereg §6.1): the served paid stat line "
              "does **not** derive from these cells — every consumer of the W6d substrate is a "
              "research runner or a test, and the board's `STAT_FIELD` payload comes from "
              "`season_projection.py`. So the clause cannot be defended as protecting a served "
              "surface; it stays a HARD GATE for its scientific job (a story may not buy the "
              "assembled atom by wrecking the parts), with a MATERIALITY threshold from a design "
              "quantity. ⭐ Applied to NF-W7f's own recorded QB numbers the relaxed rule STILL "
              "REFUSES QB (0.3866% observed against a 0.0712% bar), so it rescues nothing.", "",
              f"- priced legs {pld['priced_legs']}",
              f"- read for the SELECTED arm `{pld['arm_read']}`: summed CRPS served "
              f"{pld['served_crps_sum_priced']} → recalibrated "
              f"{pld['recalibrated_crps_sum_priced']} (relative change {pld['relative_change']})",
              f"- the arm's own claimed effect, relative: {pld['relative_claimed_effect']} ⇒ "
              f"materiality bar {pld['verdict'].get('materiality_bar')} "
              f"({pld['materiality_fraction']} × the claimed effect)",
              f"- degraded on {pld['degraded_folds']}/{sel['n_folds_used']} folds "
              f"{pld['relative_change_by_fold']}",
              f"- **verdict `{pld['verdict']['state']}`** (holds={pld['verdict']['holds']}, "
              f"evaluated={pld['verdict']['evaluated']}) — {pld['verdict']['reason']}",
              f"- by arm: {pld['relative_change_by_arm']}", ""]
        av = sel["availability_decomposition"]["winner"]
        L += [f"### ⭐ Where the per-leg effect lands — the availability decomposition "
              f"(arm `{sel['availability_decomposition']['arm_read']}`)", "",
              f"**`{av['state']}`** — {av['reason']}", "",
              f"> {sel['availability_decomposition']['note']}", "",
              "| π̂ bucket | rows | pooled Δ (priced legs, per row) |", "|---|---|---|"]
        for k in range(len(av["counts"])):
            L.append(f"| {av['edges'][k]}–{av['edges'][k + 1]} | {av['counts'][k]} | "
                     f"{av['mean_delta'][k]} |")
        L += ["", f"- crossovers: {av['crossovers']}",
              f"- pooled Δ over all buckets: {av['pooled_mean_delta']}",
              f"- state by arm: "
              f"{ {a: b['state'] for a, b in sel['availability_decomposition']['by_arm'].items()} }",
              f"- state by priced leg: "
              f"{ {l: b['state'] for l, b in sel['availability_decomposition']['by_priced_leg'].items()} }",
              "", "### ⭐ Channel attribution (paired per-fold deltas, not ranks)", "",
              f"> {sel['channel_attribution']['note']}", "",
              "| channel | foil | Δ (foil − arm) | CI95 | folds | p |", "|---|---|---|---|---|---|"]
        for name, c in sel["channel_attribution"].items():
            if not isinstance(c, dict):
                continue
            L.append(f"| `{name}` | `{c['vs']}` | {c['mean_delta']} | {c['ci95']} | "
                     f"{c['fold_wins']}/{c['n_folds']} | {c['p_one_sided']} |")
        pfs = sel["per_fold_series"]
        L += ["", "### ⭐ Per-fold series (the anchors are scored on every fold)", "",
              "| fold | " + " | ".join(f"`{lab}`" for lab in pfs["crps"]) + " |",
              "|---" * (1 + len(pfs["crps"])) + "|"]
        for i, f in enumerate(pfs["folds"]):
            L.append(f"| {f} | " + " | ".join(str(pfs["crps"][lab][i]) for lab in pfs["crps"])
                     + " |")
        L += ["", f"PIT (max-decile deviation) per fold — bar {RM.PIT_MAX_DECILE_DEV}:", "",
              "| fold | " + " | ".join(f"`{lab}`" for lab in pfs["pit_max_decile_dev"]) + " |",
              "|---" * (1 + len(pfs["pit_max_decile_dev"])) + "|"]
        for i, f in enumerate(pfs["folds"]):
            L.append(f"| {f} | " + " | ".join(str(pfs["pit_max_decile_dev"][lab][i])
                                              for lab in pfs["pit_max_decile_dev"]) + " |")
        L += ["",
              f"- winner clears the PIT bar on "
              f"{sum(pfs['winner_pit_clears_bar_by_fold'])}/{len(pfs['folds'])} folds "
              f"({pfs['winner_pit_clears_bar_by_fold']})",
              f"- ⭐ the MATCHED FOIL (what RB already had) clears it on "
              f"{sum(pfs['matched_foil_pit_clears_bar_by_fold'])}/{len(pfs['folds'])} "
              f"({pfs['matched_foil_pit_clears_bar_by_fold']}) — at RB the question is whether the "
              f"recalibration KEEPS this, not whether it wins it",
              f"- the reproduced incumbent clears it on "
              f"{sum(pfs['incumbent_pit_clears_bar_by_fold'])}/{len(pfs['folds'])} "
              f"({pfs['incumbent_pit_clears_bar_by_fold']})",
              f"- priced-leg relative change by fold: {pfs['priced_leg_relative_change_by_fold']}",
              f"- atom cap by fold — served {pfs['atom_cap_served_by_fold']} → recalibrated "
              f"{pfs['atom_cap_recalibrated_by_fold']}", ""]
        pd_ = sel["premise_detail"]
        L += ["### The premise, measured — per-leg predicted vs realized zero mass (last fold)", "",
              "> §0.2 of the pre-registration predicted, off a 126-row serving proof, that RB's "
              "CONTINUOUS cells OVER-price their zero (gap < 0) and that the RAISE-ONLY splice "
              "therefore cannot reach them. This is the same table at FOLD SCALE — it is free to "
              "overturn that prediction, and what it says is the finding.", "",
              "| leg | predicted P(0) | realized P(0) | gap | AFTER re-splice | gap after |",
              "|---|---|---|---|---|---|"]
        after = pd_["leg_zero_mass_table_recalibrated_last_fold"]
        for leg, r in pd_["leg_zero_mass_table_last_fold"].items():
            a = after.get(leg, {})
            L.append(f"| `{leg}` | {r['predicted_zero_mass']} | {r['realized_zero_rate']} | "
                     f"{r['gap_realized_minus_predicted']} | {a.get('predicted_zero_mass')} | "
                     f"{a.get('gap_realized_minus_predicted')} |")
        L += ["", f"- binding-leg share, SERVED: {pd_['binding_leg_share_served']}",
              f"- binding-leg share, RECALIBRATED: {pd_['binding_leg_share_recalibrated']}", "",
              "### Anchors", "",
              f"- degenerates (CRPS): {sel['anchors']['degenerate_detail']}",
              f"- degenerates (PIT — printed every run so the bar can never become a selection "
              f"criterion, NF1.8): {sel['anchors']['degenerate_pit_detail']}",
              f"- oracle states (one per FORM, at matched n — NF-D16 (g‴)): "
              f"{ {a: o['state'] for a, o in sel['oracle_detail'].items()} }",
              f"- permutations: {sel['permutation_detail']}",
              f"- reproduction — incumbent {sel['incumbent_reproduction']}",
              f"- reproduction — predecessor {sel['predecessor_reproduction']}", ""]
        n = out["null_states"].get(p)
        if n:
            L += [f"### Null state: `{n['state']}`", "", n["reason"], "",
                  f"- failing anchor/registration clauses: {n.get('failing_anchor_checks')}",
                  f"- failing statistical checks: {n.get('failing_statistical_checks')}",
                  f"- binding half: {n.get('binding_half')}",
                  f"- instrument's own reading (kept verbatim for audit): "
                  f"{n.get('instrument_verdict')}",
                  f"- retest trigger: {n.get('retest_trigger')}",
                  f"- `field_remedy_admissible`: {n.get('field_remedy_admissible')}",
                  f"- declared field size source: {n.get('declared_field_size_source')}", ""]
            if n.get("dsr_diagnostic"):
                d = n["dsr_diagnostic"]
                L += ["#### ⭐ The DSR 2×2 — which lever actually binds", "",
                      f"**`{d.get('lever')}`** — {d.get('reading')}", "",
                      f"- DSR on the DECLARED {d.get('declared_field_size')}-arm field: "
                      f"{d.get('dsr_declared_field')} (bar {d.get('dsr_bar')})",
                      f"- DSR on a COHERENT sub-field (dropping the most extreme trial Sharpe, "
                      f"`{d.get('dropped_trial_arm')}`): {d.get('dsr_coherent_subfield')} "
                      f"(moved {d.get('dsr_moved_by_coherence')})",
                      f"- cross-trial dispersion V: {d.get('v_declared_field')} → "
                      f"{d.get('v_coherent_subfield')} (ratio "
                      f"{d.get('v_ratio_declared_over_coherent')}×)",
                      f"- observed SR {d.get('observed_sr')}; trial SRs {d.get('trial_srs')}",
                      f"- {d.get('note')}", ""]

    L += ["## Promote blockers", ""]
    L += [f"- {b}" for b in v["promote_blockers"]]
    path.write_text("\n".join(L) + "\n")


# ── Orchestration ───────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-W7h — the RB marginal-layer zero-mass "
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
    # cosmetic (the predecessors', inherited): the W6d serving dispatch predicts through a numpy
    # view of a frame the learner was fitted on with column names; sklearn warns once per predict.
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    suffix = "_smoke" if args.smoke else ""
    art = _PROJECT_ROOT / _ARTIFACT_REL.replace(".json", f"{suffix}.json")

    if args.rewrite_report:
        out = derive_verdict_layer(json.loads(art.read_text()))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat()
        art.write_text(json.dumps(out, indent=2, default=str))
        write_report(out, art.with_suffix(".md"))
        log.info("NF-W7h report re-derived → %s", art.name)
        return 0

    FA.assert_stat_key_map()
    feat, pit_audit, attach = W6DA.build_matrix_w6d(SEASONS, rebuild_cache=args.rebuild_cache)
    gate_p, bake_p, def_p = W6DS.record_paths("")          # ALWAYS the FULL W6d records
    smap = SDSD.served_map(gate_p, bake_p, def_p)
    folds = WP.build_folds(feat)
    positions: tuple[str, ...] = RM.POSITIONS
    if args.smoke:
        folds = folds[-1:]
    draws = 300 if args.smoke else RM.ASSEMBLY_DRAWS
    matrix_key = W6DA.w6d_matrix_key(SEASONS)
    base = cap_baseline()
    log.info("NF-W7h: %d folds × %d positions, %d legs, %d draws%s — RB cap baseline %s",
             len(folds), len(positions), RM.N_LEGS, draws, " [SMOKE]" if args.smoke else "",
             base.get("atom_cap_mean") if base["available"] else base["reason"])

    t0 = time.time()
    fold_results = [run_fold(f, feat, smap, draws=draws, positions=positions,
                             matrix_key=matrix_key, rebuild_banks=args.rebuild_banks)
                    for f in folds]
    out = {
        "story": RM.STORY, "phase": "rb_marginal_zero_mass_recalibration",
        "smoke": bool(args.smoke),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seasons": list(SEASONS), "n_folds": len(folds), "gate_league": GATE_LEAGUE,
        "gate_positions": list(RM.GATE_POSITIONS),
        "matrix_key": matrix_key, "pit_audit": pit_audit,
        "attach_audit": attach, "served_map_sources": {c: v["source"] for c, v in smap.items()},
        "assembly_draws": draws, "row_block": RM.ROW_BLOCK, "seed": RM._SEED,
        "seed_inherited_from": f"{FA.STORY} via {SA.PREDECESSOR}, {RM.PREDECESSOR} and "
                               f"{RM.TRANSFORM_SOURCE}",
        "avail_stream_offset": RM.AVAIL_STREAM_OFFSET,
        "joint_construction_held_fixed": RM.JOINT_CONSTRUCTION,
        "pi_estimator": RM.PI_ESTIMATOR,
        "transform_imported_from": RM.TRANSFORM_SOURCE,
        "cap_baseline": base,
        "declared_field": {"real_arms": list(RM.REAL_ARMS),
                           "primary_arm": RM.PRIMARY_ARM,
                           "declared_field_size": RM.DECLARED_FIELD_SIZE,
                           "declared_field_size_source": RM.DECLARED_FIELD_SIZE_SOURCE,
                           "contest_foils": list(RM.CONTEST_FOILS),
                           "matched_foil": RM.MATCHED_FOIL,
                           "reference_foils": list(RM.REFERENCE_FOILS),
                           "degenerates": list(RM.DEGENERATES), "anchors": list(RM.ANCHORS)},
        "labelling": {p: FA.assembled_labelling(smap, LP.get_preset(GATE_LEAGUE), p)
                      for p in positions},
        "fold_results": fold_results, "runtime_seconds": round(time.time() - t0, 1),
    }
    out = derive_verdict_layer(out)
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(json.dumps(out, indent=2, default=str))
    write_report(out, art.with_suffix(".md"))
    log.info("NF-W7h %s (RB verdict: %s) → %s (%.1fs)", out["verdict"]["story_verdict"],
             out["marginal_cap"]["state"], art.name, out["runtime_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
