"""run_nf_w8_0e_qb_passing_cell.py — NF-W8-0e §0.5: the QB | `passing_yards` cell, the joint 2×2.

Everything decidable in advance is a CONSTANT in `fp_qb_passing_cell.py`; this runner READS it
(NF-D16). The narrative pre-registration is committed at
`ablation_results/nf_w8_0e_preregistration.md` BEFORE any scoring run.

⭐ ONE CODE PATH FOR EVERY CERTIFIED GENERATOR. The four consumed generators are built by
`run_nf_w8_0_cross_position.run_position` — the predecessors' own function, driven through
NF-W8-0b's DECIDED `point_reader` — so the reproduction pins cannot drift and the non-QB side is
byte-identical to NF-W8-0b's record. At QB this story ADDS a 2 × 3 grid of CELL arms whose
`identity` assembly is PROVEN exactly equal (CRPS and ranking point, 0.0) to that certified path
before any arm is scored.

PIPELINE (8 folds, gate league `full_ppr`, NF-W7c's fold axis verbatim):
  · per fold: the four consumed generators (pins) at every position;
  · family A — the CELL contest: the 2 × 3 grid `{Z: off,on} × {C: none,shift,scale}` on the served
    `QB|passing_yards` bank, scored with `EM.score_bank` + randomized-PIT flatness, with per-form
    peeking oracles, matched-n controls, a two-sided magnitude bracket, four degenerates and the
    §5.2 expected-tie permutation;
  · family B — the 2×2 READ: `Δ_Z`, `Δ_C`, `Δ_joint` and the INTERACTION, on the cell's CRPS and on
    the cell's level, for BOTH the primary (shift) and the alternative (scale) square;
  · family C — the ASSEMBLED QB read under every arm: CRPS, randomized-PIT flatness against the
    inherited 0.05 bar, and the ranking-point level bias;
  · family D — the DOWNSTREAM verification: the six cross-position contrasts re-tested under the
    winner through `XP.pairwise_gap_tests` (one implementation — E9.61);
  · the verdict via `PC.cell_verdict` (four pre-registered states).

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: writes LOCAL artifacts only — no `--publish`,
no S3 client, no boto3, no dbt, no Dagster. ⛔ It re-serves NO NF-W6d cell, writes NO optimizer
input and NO predecessor path (prereg §11).

RUN (OPERATOR — LAPTOP; reads the S3 NFL lake read-only, writes local artifacts):

    # path proof: the last TWO folds, few draws (artifact _smoke) — no verdict
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w8_0e_qb_passing_cell \
        --smoke

    # the decisive run (>2 min — OPERATOR; dominated by the W6d marginal dispatch per fold)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w8_0e_qb_passing_cell

    # re-derive every verdict from the stored per-fold summaries at ZERO refit cost
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w8_0e_qb_passing_cell \
        --rewrite-report

⭐ Per-fold MARGINAL BANKS are cached under `artifacts/nf_w7e_bank_cache/` — NF-W7e's own cache
directory and key scheme, inherited through `W80`. ⚠️ That directory is GITIGNORED and is therefore
ABSENT in a fresh worktree (the NF-INFRA1 class): a first run in a new checkout pays the full
marginal fit for every fold.
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
from quant_sports_intel_models.football.nfl.fantasy import fp_cross_position as XP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import fp_qb_body as QB  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import fp_qb_passing_cell as PC  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    fp_qb_marginal_calibration as QM,
)
from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KW  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import league_presets as LP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w6d_ceiling_gate as W6DA,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w6d_serve_stat_distributions as W6DS,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w7c_fp_assembly as W7C,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w8_0_cross_position as W80,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    stat_distribution_serving_d as SDSD,
)
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_w8_0e")

SEASONS = W6DA.SEASONS
FEATURES = list(WP.FEATURES)
GATE_LEAGUE = W80.GATE_LEAGUE                      # ⛔ inherited (E2.1-r)

_ARTIFACT_REL = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                 "nf_w8_0e_qb_passing_cell.json")
_ROWS_DIR = Path(__file__).resolve().parent / "artifacts" / "nf_w8_0e_rows"

#: ⛔ Every predecessor record is DECIDED. A successor that writes a decided story's paths destroys
#: its audit trail with no error and no test failure (the NCAAF-P2.1 S1-serve lesson). Enforced at
#: import, not by review.
_DECIDED_PATHS: tuple[str, ...] = (
    "nf_w8_0_cross_position", "nf_w8_0_rows", "nf_w8_0_input",
    "nf_w8_0b_tail_point", "nf_w8_0b_rows", "nf_w8_0b_input",
    "nf_w8_0c_qb_body", "nf_w8_0c_rows", "nf_w8_0d_dsr_frontier",
    "nf_w7f_qb_marginal", "nf_w6d_stat_bakeoff", "nf_w6d_defaults", "nf_w6d_ceiling_gate",
    "nf_w6d_served_stat_distributions",
)
for _own in (_ARTIFACT_REL, str(_ROWS_DIR)):
    for _dec in _DECIDED_PATHS:
        if Path(_own).name.startswith(_dec) or f"/{_dec}" in _own:
            raise RuntimeError(f"NF-W8-0e would write a DECIDED predecessor artifact path "
                               f"({_own}) — refused (a successor never writes a decided story's "
                               f"paths)")

_ABL = "quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
_W7F_REL = _ABL + "nf_w7f_qb_marginal.json"
_W8_0B_REL = _ABL + "nf_w8_0b_tail_point.json"
_W8_0C_REL = _ABL + "nf_w8_0c_qb_body.json"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The QB assembly — the certified `zm_floor` construction, called on an ARBITRARY leg tensor
# ══════════════════════════════════════════════════════════════════════════════════════════════
def assemble_qb_from_tensor(tensor: np.ndarray, weights: np.ndarray, *, pi_hat: np.ndarray,
                            cond_rate: np.ndarray, marg_rate: np.ndarray, corr: np.ndarray,
                            draws: int) -> np.ndarray:
    """`build_position_banks`' QB branch, verbatim, on a caller-supplied leg tensor.

    ⭐ The four calls below are byte-for-byte the QB branch of
    `run_nf_w8_0_cross_position.build_position_banks`; a guard asserts that this function and that
    branch produce an identical bank on the SERVED tensor, so there is exactly one QB assembly in
    the repo and this is a call into it rather than a second copy (NF-W7d / NF-C0e)."""
    t = QM.zero_targets("zm_floor", banks=tensor, pi_hat=pi_hat, cond_rate=cond_rate,
                        marg_rate=marg_rate)
    recal = QM.resplice_zero_mass(tensor, t)
    pi_used, note = QM.clamp_pi(pi_hat, recal)
    # ⭐ `QB.assemble_qb` at `played_shift=0` is BYTE-IDENTICAL to `QM.assemble_mixture_bank` (same
    # block loop, same seeds, legs from `MX.mixture_leg_draws`) and additionally returns the mean
    # LEG DRAWS and the mean ASSEMBLED TOTAL — the two quantities `QB.mechanism_decomposition`
    # needs, and the second of which is what keeps that identity from being tautological.
    bank, leg_means, total_mean = QB.assemble_qb(recal, weights, pi=pi_used, corr=corr,
                                                 draws=draws)
    return bank, {"clamp": note, "recal": recal, "pi_used": pi_used,
                  "leg_means": leg_means, "total_mean": total_mean}


def _cell_scores(cell_bank: np.ndarray, y_leg: np.ndarray, label: str) -> dict:
    KW.assert_finite_predictive(cell_bank, f"{PC.CELL}/{label}")
    s = PC.score_bank(cell_bank, y_leg)
    pit = QM.pit_detail(KW.randomized_pit_from_bank(cell_bank, y_leg))
    grid_mean = float(np.mean(np.sort(cell_bank, axis=1).mean(axis=1)))
    return {
        # ⛔ FULL PRECISION — the pins compare at 1e-9; a round(…, 6) caps every pin at ~5e-7 and
        # the decisive run returns UNDEFINED (the NF-W8-0 smoke's catch)
        "crps_q199": float(s["crps_q199"]), "coverage_80": float(s["coverage_80"]),
        "pred_p0": float(s["pred_p0"]), "real_p0": float(s["real_p0"]), "n": int(s["n"]),
        "pit": pit, "grid_mean": grid_mean,
        "level_bias": float(grid_mean - float(np.mean(y_leg))),
    }


def _assembled_scores(bank: np.ndarray, y_te: np.ndarray, label: str) -> dict:
    KW.assert_finite_predictive(bank, f"QB/{label}")
    point = PC.POINT_READER(bank)
    return {"crps": float(np.mean(KW.crps_dense(bank, y_te))),
            "pit": QM.pit_detail(KW.randomized_pit_from_bank(bank, y_te)),
            "coverage": KW.coverage80_dense(bank, y_te),
            "bias": PC.bias_detail(point, y_te),
            "point": [float(v) for v in point]}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# One fold × QB — every arm, foil and anchor
# ══════════════════════════════════════════════════════════════════════════════════════════════
def run_qb_cell_arms(tr_p: pd.DataFrame, te_p: pd.DataFrame, weights: np.ndarray, *, draws: int,
                     b_te: np.ndarray, raw_tr: np.ndarray, raw_te: np.ndarray, y_te: np.ndarray,
                     prior_ledgers: list[dict], certified: dict,
                     certified_point: np.ndarray, fold_label: str) -> tuple[dict, dict]:
    """The 2 × 3 grid + anchors for one fold, plus this fold's ledger for the NEXT fold's fits."""
    j = PC.LEG_INDEX
    y_leg = np.asarray(raw_te[:, j], dtype=float)
    sig_all, _ = SA.sigma_all(raw_tr)
    pi_hat = QM.pi_for_arm(QM.PI_ESTIMATOR, tr_p, te_p, FEATURES, train_raw=raw_tr)
    cond_rate = QM.conditional_zero_rate(raw_tr)
    marg_rate = QM.marginal_zero_rate(raw_tr)

    # ── Z, leg-scoped: the certified `zm_floor` target on `passing_yards`, a no-op elsewhere ──────
    full_targets = QM.zero_targets("zm_floor", banks=b_te, pi_hat=pi_hat, cond_rate=cond_rate,
                                   marg_rate=marg_rate)
    targets = PC.leg_scoped_targets(b_te, full_targets)
    banks_z_on = PC.resplice_zero_mass(b_te, targets)
    columns = {"z_off": np.asarray(b_te, dtype=float), "z_on": banks_z_on}

    # ── the transform's MEASURED identities (§7 clause 14) ───────────────────────────────────────
    identities = {
        "zero_mass_hits_target": PC.zero_mass_hits_target(b_te, targets, banks_z_on),
        "positive_law_preserved": PC.positive_law_drift(b_te, banks_z_on),
        "matched_foil_identity": PC.matched_foil_identity(b_te),
        "other_legs_untouched": PC.other_legs_untouched(b_te, banks_z_on),
        "resplice_edges": PC.resplice_edges(b_te, targets),
    }

    # ── the arms: parameters from PRIOR folds' OOF ledger of the arm's OWN Z column ──────────────
    params: dict[str, dict] = {}
    tensors: dict[str, np.ndarray] = {PC.INCUMBENT: np.asarray(b_te, dtype=float)}

    def _build(label: str, arm: str, p: dict) -> None:
        params[label] = p
        z_on, form = PC.ARM_GRID[arm]
        if form is not None and not p.get("eligible"):
            tensors[label] = tensors[PC.INCUMBENT]     # identity, RECORDED (NF1.7 (a))
            return
        tensors[label] = PC.build_arm(b_te, targets, z_on=z_on, form=form,
                                      value=p.get("value"))

    for arm in PC.REAL_ARMS:
        _build(arm, arm, PC.fit_cell_params(arm, prior_ledgers))

    # ── this fold's own ledger (the peek's source) + the matched-n control's source (A1) ─────────
    this_fold = PC.cell_ledger(banks_by_column=columns, realized_leg=y_leg)
    recent_prior = [prior_ledgers[-1]] if prior_ledgers else []

    # ── per-FORM peeking oracles (NF-D16 (g‴)) and matched-n controls (NF1.9 (f) / A1) ───────────
    for arm in PC.REAL_ARMS:
        z_on, form = PC.ARM_GRID[arm]
        if form is None:
            # ⭐ A3′: `zm_only` has no fitted scalar — its ONE estimated input is π̂. The SAME-FORM
            # peek therefore replaces π̂ with the test fold's REALIZED activity indicator
            # (`q_i = 1 − active_i`) inside the certified `zm_floor` rule, so the oracle differs
            # from its arm in exactly that estimate and nothing else (NF-D16 (g‴): the peek must be
            # the arm's own FORM). ⛔ The first cut peeked the realized MARGINAL zero rate instead,
            # which is ROW-BLIND — a different form, and the path proof showed it losing outright.
            oracle_q = 1.0 - QM.activity_indicator(raw_te).astype(float)
            oracle_full = QM.zero_targets("zm_floor", banks=b_te, pi_hat=1.0 - oracle_q,
                                          cond_rate=cond_rate, marg_rate=marg_rate)
            tensors[PC.ORACLE_OF[arm]] = PC.resplice_zero_mass(
                b_te, PC.leg_scoped_targets(b_te, oracle_full))
            params[PC.ORACLE_OF[arm]] = {
                "eligible": True, "form": None,
                "peek": "the TEST fold's realized activity indicator in place of π̂, inside the "
                        "certified `zm_floor` rule — same form, one peeked input (prereg A3′)"}
            # its control is the certified train-side rule = the arm itself. The control carries
            # MORE data than the peek (full train vs the test block), which is the CONSERVATIVE
            # direction for an oracle floor: a peek that still wins wins a fortiori.
            tensors[PC.MATCHED_OF[arm]] = PC.resplice_zero_mass(b_te, targets)
            params[PC.MATCHED_OF[arm]] = {
                "eligible": True, "form": None,
                "note": "the certified train-side π̂ rule; the control is data-ADVANTAGED, so a "
                        "peek that still wins clears the floor a fortiori (prereg A1/A3′)"}
            continue
        p_or = PC.fit_cell_params(arm, [this_fold])
        params[PC.ORACLE_OF[arm]] = p_or
        tensors[PC.ORACLE_OF[arm]] = (
            PC.build_arm(b_te, targets, z_on=z_on, form=form, value=p_or.get("value"))
            if p_or.get("eligible") else tensors[PC.INCUMBENT])
        p_mn = PC.fit_cell_params(arm, recent_prior)
        params[PC.MATCHED_OF[arm]] = p_mn | {
            "matched_n_source": "the most recent PRIOR fold (prereg §12A A1)",
            "n_matched": int(recent_prior[0]["n"]) if recent_prior else 0}
        tensors[PC.MATCHED_OF[arm]] = (
            PC.build_arm(b_te, targets, z_on=z_on, form=form, value=p_mn.get("value"))
            if p_mn.get("eligible") else tensors[PC.INCUMBENT])

    # ── the two-sided MAGNITUDE bracket, both registered to LOSE ─────────────────────────────────
    p_joint = params["joint_shift"]
    for label, mult in (("over_joint_shift", PC.OVER_SCALE), ("reverse_joint_shift", -1.0)):
        if p_joint.get("eligible"):
            params[label] = p_joint | {"value": float(p_joint["value"]) * mult,
                                       "magnitude_multiplier": mult}
            tensors[label] = PC.build_arm(b_te, targets, z_on=True, form="shift",
                                          value=float(p_joint["value"]) * mult)
        else:
            params[label] = {"eligible": False,
                             "reason": "`joint_shift` is ineligible this fold, so its magnitude "
                                       "anchor cannot be formed"}
            tensors[label] = tensors[PC.INCUMBENT]

    # ── the §5.2 permutation anchor — registered FORWARD as an EXPECTED EXACT TIE ────────────────
    rng = np.random.default_rng(abs(hash((FA._SEED, fold_label, "permuted"))) % (2**32))
    p_perm = PC.fit_cell_params("joint_shift", PC.permuted_ledgers(prior_ledgers, rng))
    params[PC.PERMUTED_ANCHOR] = p_perm | {
        "registered": "an EXPECTED EXACT TIE with `joint_shift` (prereg §5.2) — a pooled scalar "
                      "has no per-row content for a within-fold permutation to destroy; it is "
                      "SCORED and its tie ASSERTED, and it enters NO gate clause"}
    tensors[PC.PERMUTED_ANCHOR] = (
        PC.build_arm(b_te, targets, z_on=True, form="shift", value=p_perm.get("value"))
        if p_perm.get("eligible") else tensors[PC.INCUMBENT])

    # ── the cell banks + the four degenerates (scored EVERY run — NF-D11 / NF1.8) ────────────────
    cell_banks = {label: np.asarray(t[:, j, :], dtype=float) for label, t in tensors.items()}
    inc_cell = cell_banks[PC.INCUMBENT]
    cell_banks["nihilist_zero"] = PC.anchor_nihilist(len(y_leg))
    cell_banks["zero_width"] = PC.anchor_zero_width(inc_cell)
    cell_banks["max_width"] = PC.anchor_max_width(inc_cell)
    prior_y = np.concatenate([np.asarray(l["y_leg_values"], float) for l in prior_ledgers
                              if l.get("y_leg_values")]) if prior_ledgers else np.asarray([])
    if len(prior_y) >= 2:
        cell_banks["climatology_bank"] = np.repeat(
            np.quantile(prior_y, PC.EVAL_LEVELS)[None, :], len(y_leg), axis=0)
        params["climatology_bank"] = {"eligible": True, "n_prior_rows": int(len(prior_y))}
    else:
        cell_banks["climatology_bank"] = inc_cell
        params["climatology_bank"] = {"eligible": False,
                                      "reason": "no prior realized rows — the climatology anchor "
                                                "could not be formed on this fold"}

    cell_arms = {label: _cell_scores(bank, y_leg, label) for label, bank in cell_banks.items()}
    for label in cell_arms:
        cell_arms[label]["params"] = params.get(label, {"eligible": True})
        cell_arms[label]["acts"] = (label == PC.INCUMBENT) or bool(
            np.max(np.abs(cell_banks[label] - inc_cell)) > 0.0)

    # ⭐ the §5.2 tie, ASSERTED (not argued): the permuted anchor must be byte-identical to its arm
    perm_gap = float(np.max(np.abs(cell_banks[PC.PERMUTED_ANCHOR] - cell_banks["joint_shift"])))
    permutation_is_inactive = {
        "max_abs_gap": perm_gap, "holds": bool(perm_gap <= PC.REPRODUCTION_TOLERANCE),
        "registered_expectation": "an EXPECTED EXACT TIE (prereg §5.2) — enters NO gate clause"}

    # ── family C: the ASSEMBLED QB read under every arm (the certified construction) ─────────────
    assembled: dict[str, dict] = {}
    active = QM.activity_indicator(raw_te)
    for label in (PC.INCUMBENT, *PC.REAL_ARMS):
        bank, det = assemble_qb_from_tensor(
            tensors[label], weights, pi_hat=pi_hat, cond_rate=cond_rate, marg_rate=marg_rate,
            corr=sig_all, draws=draws)
        assembled[label] = _assembled_scores(bank, y_te, label)
        # ⭐ NF-W8-0c's EXACT additive identity, imported BY IDENTITY (one implementation — E9.61),
        # so this story's "what does the cell contribute NOW" reading is the SAME measurement the
        # predecessor localised the defect with, not a re-derivation of it.
        assembled[label]["decomposition"] = QB.mechanism_decomposition(
            point=PC.POINT_READER(bank), y=y_te, leg_means=det["leg_means"], realized=raw_te,
            weights=weights, pi_used=det["pi_used"], active=active,
            total_draw_mean=det["total_mean"])

    # ⭐ THE CROSS-CHECK: the re-derived incumbent assembly must BE the certified generator,
    # exactly. A tolerance here would let a silently different intermediate score as `zm_floor`.
    inc_crps = assembled[PC.INCUMBENT]["crps"]
    inc_point = np.asarray(assembled[PC.INCUMBENT]["point"], float)
    check = {
        "certified_crps": float(certified["scores"]["zm_floor"]),
        "rederived_crps": inc_crps,
        "crps_gap": abs(inc_crps - float(certified["scores"]["zm_floor"])),
        "point_gap": float(np.max(np.abs(inc_point - np.asarray(certified_point, float)))),
    }
    check["matches"] = bool(check["crps_gap"] == 0.0 and check["point_gap"] == 0.0)
    if not check["matches"]:
        raise ValueError(
            f"the re-derived QB incumbent assembly is NOT the certified `zm_floor` (CRPS gap "
            f"{check['crps_gap']:.3e}, point gap {check['point_gap']:.3e}) — refused rather than "
            f"scoring arms against a silently different incumbent (NF-W7d / NF1.7 (a))")

    # ⭐ prereg §8.1 — the assembled Z column's activity, MEASURED (never assumed)
    z_gap = {
        "identity_vs_zm_only": abs(assembled["zm_only"]["crps"] - assembled[PC.INCUMBENT]["crps"]),
        "cond_shift_vs_joint_shift": abs(assembled["joint_shift"]["crps"]
                                         - assembled["cond_shift"]["crps"]),
        "cond_scale_vs_joint_scale": abs(assembled["joint_scale"]["crps"]
                                         - assembled["cond_scale"]["crps"]),
    }

    # ── the commutation diagnostic (prereg §4) — on the winner form's fitted value ───────────────
    commute = (PC.commutation_gap(b_te, targets, "shift", float(p_joint["value"]))
               if p_joint.get("eligible") else
               {"evaluable": False, "note": "`joint_shift` ineligible this fold"})

    ledger = this_fold | {"y_leg_values": [float(v) for v in y_leg]}
    detail = {
        "cells": cell_arms, "assembled": assembled,
        "identities": identities, "permutation_is_inactive": permutation_is_inactive,
        "identity_matches_certified": check, "assembled_z_column_gap": z_gap,
        "commutation": commute,
        "n_test": int(len(y_te)), "n_test_cell": int(len(y_leg)),
        "correction_edges": ({f: PC.correction_edges(banks_z_on, "shift",
                                                     float(params[f]["value"]))
                              for f in ("joint_shift",) if params[f].get("eligible")}),
    }
    return detail, ledger


# ── One fold ────────────────────────────────────────────────────────────────────────────────────
def run_fold(fold: WP.Fold, feat: pd.DataFrame, smap: dict, *, draws: int, matrix_key: str,
             rows_dir: Path, prior_ledgers: list[dict],
             rebuild_banks: bool = False) -> tuple[dict, dict]:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    cfg = LP.get_preset(GATE_LEAGUE)
    ctx_te, cache_state = W80._marginals_cached(fold.label, train, test, smap,
                                                matrix_key=matrix_key, rebuild=rebuild_banks)
    positions: dict[str, dict] = {}
    fold_rows: list[pd.DataFrame] = []
    qb_detail: dict | None = None
    ledger: dict | None = None
    for position in XP.POSITIONS:
        FA.assert_assembly_is_priceable(cfg, position)
        weights = FA.leg_weights(cfg, position)
        # ⭐ the certified generators, through the PREDECESSORS' own function and NF-W8-0b's
        # DECIDED point reader — one code path, so the pins cannot drift
        summary, rows = W80.run_position(position, train, test, weights, draws=draws,
                                         ctx_te=ctx_te, point_reader=PC.POINT_READER,
                                         bank_detail=PC.BANK_DETAIL)
        positions[position] = summary
        if rows is None:
            continue
        if position == PC.POSITION:
            tr_p = train.loc[train["position"].astype(str) == position].reset_index(drop=True)
            te_p = test.loc[test["position"].astype(str) == position].reset_index(drop=True)
            raw_tr, raw_te = W7C.realized_matrix(tr_p), W7C.realized_matrix(te_p)
            y_te = FA.score_realized(raw_te, weights)
            b_te = W7C.bank_tensor(ctx_te, position, len(te_p))
            qb_detail, ledger = run_qb_cell_arms(
                tr_p, te_p, weights, draws=draws, b_te=b_te, raw_tr=raw_tr, raw_te=raw_te,
                y_te=y_te, prior_ledgers=prior_ledgers, certified=summary,
                certified_point=rows["point_consumed"].to_numpy(float), fold_label=fold.label)
            for label, sc in qb_detail["assembled"].items():
                rows[f"point__{label}"] = np.asarray(sc["point"], float)
        fold_rows.append(rows)
    rows_dir.mkdir(parents=True, exist_ok=True)
    rows_path = rows_dir / f"{fold.label}.parquet"
    if fold_rows:
        pd.concat(fold_rows, ignore_index=True).to_parquet(rows_path, index=False)
    if qb_detail is not None:                     # the rows parquet carries them; keep JSON lean
        for sc in qb_detail["assembled"].values():
            sc.pop("point", None)
    log.info("[W8-0e] fold %s complete in %.1fs (bank cache %s)", fold.label, time.time() - t0,
             cache_state)
    return ({"label": fold.label, "n_test": int(len(test)), "positions": positions,
             "qb": qb_detail, "bank_cache": cache_state, "rows_path": str(rows_path)},
            ledger or {})


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Reproduction pins (prereg §9)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _record(relpath: str, story: str) -> dict | None:
    p = _PROJECT_ROOT / relpath
    if not p.exists():
        return None
    rec = json.loads(p.read_text())
    if rec.get("story") != story or rec.get("smoke"):
        return None
    return rec


def _w7f_qb_pins(fold_results: list[dict]) -> dict:
    """The assembled QB incumbent's per-fold CRPS AND randomized-PIT vs the NF-W7f record."""
    rec = _record(_W7F_REL, "NF-W7f")
    if rec is None:
        return {"reproduces": False, "n_folds_compared": 0,
                "note": ("the NF-W7f record is absent or a path proof — the QB incumbent's "
                         "reproduction control DID NOT RUN, which is never a pass (NF1.7 (a))")}
    want = {fr["label"]: fr["positions"]["QB"] for fr in rec["fold_results"]
            if not fr["positions"].get("QB", {}).get("skipped")}
    gaps_c, gaps_p, n = [], [], 0
    for fr in fold_results:
        qb = fr.get("qb")
        if not qb or fr["label"] not in want:
            continue
        got = qb["assembled"][PC.INCUMBENT]
        gaps_c.append(abs(got["crps"] - float(want[fr["label"]]["scores"]["zm_floor"])))
        gaps_p.append(abs(got["pit"]["max_decile_dev"]
                          - float(want[fr["label"]]["pit_flatness"]["zm_floor"]["max_decile_dev"])))
        n += 1
    if not n:
        return {"reproduces": False, "n_folds_compared": 0,
                "note": "no fold could be compared — DID NOT RUN, never a pass (NF1.7 (a))"}
    return {"reproduces": bool(max(gaps_c) <= PC.REPRODUCTION_TOLERANCE
                               and max(gaps_p) <= PC.REPRODUCTION_TOLERANCE),
            "n_folds_compared": n, "max_abs_crps_gap": float(max(gaps_c)),
            "max_abs_pit_gap": float(max(gaps_p))}


def _w8_0b_non_qb_pins(fold_results: list[dict]) -> dict:
    """Every position's per-fold identity bias on the tail-completed point vs NF-W8-0b."""
    rec = _record(_W8_0B_REL, "NF-W8-0b")
    if rec is None:
        return {"reproduces": False, "n_folds_compared": 0,
                "note": "the NF-W8-0b record is absent or a path proof — DID NOT RUN (NF1.7 (a))"}
    want: dict[str, dict[str, float]] = {}
    for fr in rec["fold_results"]:
        got = {}
        for pos, s in fr["positions"].items():
            if s.get("skipped") or "bias_identity" not in s:
                continue
            got[pos] = float(s["bias_identity"]["bias"])
        want[fr["label"]] = got
    gaps: dict[str, float] = {}
    n = 0
    for fr in fold_results:
        ref = want.get(fr["label"])
        if not ref:
            continue
        for pos, s in fr["positions"].items():
            if s.get("skipped") or pos not in ref:
                continue
            g = abs(float(s["bias_identity"]["bias"]) - ref[pos])
            gaps[pos] = max(gaps.get(pos, 0.0), g)
        n += 1
    if not n or not gaps:
        return {"reproduces": False, "n_folds_compared": n,
                "note": "no position could be compared — DID NOT RUN, never a pass (NF1.7 (a))"}
    return {"reproduces": bool(max(gaps.values()) <= PC.REPRODUCTION_TOLERANCE),
            "n_folds_compared": n,
            "max_abs_gap_by_position": {k: float(v) for k, v in gaps.items()}}


def _incumbent_leg_channel(fold_results: list[dict], arm: str = PC.INCUMBENT
                           ) -> tuple[float | None, float | None]:
    """The row-pooled `passing_yards` contribution + conditional part under one arm (NF1.8: pooled
    over ROWS across folds, never a mean of fold means)."""
    cells = [(fr["qb"]["n_test"], fr["qb"]["assembled"][arm]["decomposition"]["legs"][PC.LEG])
             for fr in fold_results if fr.get("qb")]
    if not cells:
        return None, None
    n = sum(c[0] for c in cells)

    def _p(key):
        vals = [d.get(key) for _, d in cells]
        if any(v is None for v in vals):
            return None
        return float(sum(c[0] * v for c, v in zip(cells, vals)) / n)

    return _p("contribution_ppr"), _p("conditional_part_ppr")


def _w8_0c_leg_pin(leg_contribution: float | None, leg_conditional: float | None) -> dict:
    """The recomputed `passing_yards` leg channel vs NF-W8-0c's recorded −0.3975 / −0.3878.

    ⚠️ A TOLERANCE pin, not a 1e-9 identity: NF-W8-0c pooled over its own 7 evaluable folds under
    its own arm set, so this is a CONSISTENCY check that this story is measuring the same channel,
    stated as such rather than dressed as a reproduction."""
    rec = _record(_W8_0C_REL, "NF-W8-0c")
    if rec is None or leg_contribution is None:
        return {"comparable": False,
                "note": "the NF-W8-0c record is absent, a path proof, or the channel was not "
                        "recomputed — DID NOT RUN, never a pass (NF1.7 (a))"}
    legs = rec["family_a"]["mechanism"]["legs"][PC.LEG]
    d_c = abs(float(leg_contribution) - float(legs["contribution_ppr"]))
    d_k = (None if leg_conditional is None
           else abs(float(leg_conditional) - float(legs["conditional_part_ppr"])))
    return {"comparable": True, "recorded_contribution_ppr": float(legs["contribution_ppr"]),
            "recomputed_contribution_ppr": float(leg_contribution),
            "abs_gap_contribution": float(d_c),
            "recorded_conditional_ppr": float(legs["conditional_part_ppr"]),
            "recomputed_conditional_ppr": (None if leg_conditional is None
                                           else float(leg_conditional)),
            "abs_gap_conditional": (None if d_k is None else float(d_k)),
            "consistent_within_0_05_ppr": bool(d_c <= PC.CHANNEL_MATERIAL_PPR)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The derive layer — every verdict re-derivable from the stored per-fold summaries (zero refit)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _matrix(fold_results: list[dict], section: str, key: str) -> pd.DataFrame:
    rows: dict[str, dict[str, float]] = {}
    for fr in fold_results:
        qb = fr.get("qb")
        if not qb:
            continue
        vals: dict[str, float] = {}
        for label, sc in qb[section].items():
            v = sc
            for part in key.split("."):
                v = v.get(part) if isinstance(v, dict) else None
            if v is not None:
                vals[label] = float(v)
        rows[fr["label"]] = vals
    return pd.DataFrame(rows).T


def derive_0e(out: dict) -> dict:
    fold_results = out["fold_results"]
    n_folds = int(out["n_folds"])
    cell_crps = _matrix(fold_results, "cells", "crps_q199")
    cell_pit = _matrix(fold_results, "cells", "pit.max_decile_dev")
    cell_level = _matrix(fold_results, "cells", "level_bias")
    asm_crps = _matrix(fold_results, "assembled", "crps")
    asm_pit = _matrix(fold_results, "assembled", "pit.max_decile_dev")
    asm_bias = _matrix(fold_results, "assembled", "bias.bias")

    harness = {
        "identity_matches_certified": all(
            fr["qb"]["identity_matches_certified"]["matches"]
            for fr in fold_results if fr.get("qb")),
        "transform_identities": all(
            fr["qb"]["identities"]["zero_mass_hits_target"]["holds"]
            and fr["qb"]["identities"]["positive_law_preserved"]["holds"]
            and fr["qb"]["identities"]["matched_foil_identity"]["holds"]
            and fr["qb"]["identities"]["other_legs_untouched"]["holds"]
            for fr in fold_results if fr.get("qb")),
        "permutation_is_inactive": all(
            fr["qb"]["permutation_is_inactive"]["holds"]
            for fr in fold_results if fr.get("qb")),
        "commutation": [fr["qb"]["commutation"] for fr in fold_results if fr.get("qb")],
    }
    out["harness"] = harness

    # ── family B: the 2×2 read, on the cell's CRPS and on the cell's LEVEL ───────────────────────
    def _by_arm(df: pd.DataFrame) -> dict[str, np.ndarray]:
        return {c: df[c].to_numpy(dtype=float) for c in df.columns}

    out["family_b"] = {
        "primary_square_crps": PC.interaction_read(_by_arm(cell_crps), PC.PRIMARY_SQUARE),
        "alt_square_crps": PC.interaction_read(_by_arm(cell_crps), PC.ALT_SQUARE),
        "primary_square_level": PC.interaction_read(_by_arm(cell_level.abs()), PC.PRIMARY_SQUARE),
        "alt_square_level": PC.interaction_read(_by_arm(cell_level.abs()), PC.ALT_SQUARE),
        "note": ("the LEVEL square is read on |level bias| so a smaller value is better and the "
                 "square has the same orientation as the CRPS square (Δ positive = better)"),
    }

    # ── family A: the cell contest ───────────────────────────────────────────────────────────────
    mean_cell = {c: float(cell_crps[c].mean()) for c in cell_crps.columns}
    winner = PC.select_winner(mean_cell)
    sel: dict = {"mean_cell_crps": mean_cell, "winner": winner,
                 "mean_cell_pit": {c: float(cell_pit[c].mean()) for c in cell_pit.columns},
                 "mean_cell_level_bias": {c: float(cell_level[c].mean())
                                          for c in cell_level.columns},
                 "mean_assembled_crps": {c: float(asm_crps[c].mean()) for c in asm_crps.columns},
                 "mean_assembled_pit": {c: float(asm_pit[c].mean()) for c in asm_pit.columns},
                 "mean_assembled_bias": {c: float(asm_bias[c].mean()) for c in asm_bias.columns},
                 "fold_labels": list(cell_crps.index)}
    checks = None
    classification = None
    if winner is not None:
        deltas = (cell_crps[PC.INCUMBENT] - cell_crps[winner]).to_numpy(dtype=float)
        mean_d, lo, hi = PC.paired_ci95(deltas)
        clause = cv_power.fold_consistency_clause(n_folds)
        fold_wins = int((deltas > 0).sum())
        eligible = [c for c in PC.ELIGIBLE if c in cell_crps.columns]
        defl = NF18.deflate(cell_crps[eligible], subset=eligible)
        trial_srs = []
        for arm in PC.REAL_ARMS:
            d = (cell_crps[PC.INCUMBENT] - cell_crps[arm]).to_numpy(dtype=float)
            sd = float(np.nanstd(d, ddof=1))
            trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
        dsr = PC.deflated_sharpe(deltas, np.asarray(trial_srs))
        sd_d = float(np.nanstd(deltas, ddof=1))
        observed_sr = float(np.nanmean(deltas)) / sd_d if sd_d > 1e-12 else None

        # A2: BH over ALL FIVE real arms' contrasts (stricter than the registered two)
        pvals = {a: PC.onesided_paired_pvalue(
            (cell_crps[PC.INCUMBENT] - cell_crps[a]).to_numpy(dtype=float))
            for a in PC.REAL_ARMS}
        bh = PC.bh_reject(pvals, PC.FDR_Q)

        n_rows = sum(fr["qb"]["n_test_cell"] for fr in fold_results if fr.get("qb"))
        cov = float(np.average([fr["qb"]["cells"][winner]["coverage_80"] for fr in fold_results
                                if fr.get("qb")],
                               weights=[fr["qb"]["n_test_cell"] for fr in fold_results
                                        if fr.get("qb")]))
        coverage = PC.coverage_verdict(cov, n_rows)
        assembled_pit = PC.assembled_pit_verdict(list(asm_pit[winner].to_numpy(dtype=float)))
        asm_delta = float((asm_crps[PC.INCUMBENT] - asm_crps[winner]).mean())
        own_pair = PC.oracle_pair_state(mean_cell.get(PC.ORACLE_OF[winner]),
                                        mean_cell.get(PC.MATCHED_OF[winner]))
        degen = {d: bool(mean_cell[d] > mean_cell[winner]) for d in PC.DEGENERATE_ARMS
                 if d in mean_cell}
        magn = {a: bool(mean_cell[a] > mean_cell[winner]) for a in PC.MAGNITUDE_ANCHORS
                if a in mean_cell}
        pins = out["pins"]
        gate = PC.compose_gate(
            beats_foil=bool(np.nanmean(deltas) > 0), mean_delta=mean_d,
            fold_clause_passes=clause.passes(fold_wins),
            pbo=defl.get("pbo"), dsr=dsr, fdr_pass=bool(bh.get(winner)),
            coverage=coverage, assembled_pit=assembled_pit, assembled_crps_delta=asm_delta,
            cell_pit_winner=float(cell_pit[winner].mean()),
            cell_pit_incumbent=float(cell_pit[PC.INCUMBENT].mean()),
            degenerate_losses=degen, magnitude_losses=magn, own_form_pair=own_pair,
            identities={"transform": harness["transform_identities"]},
            incumbent_reproduces=bool(pins["qb_assembly_matches_w7f"].get("reproduces")))
        checks = gate["checks"]
        sel |= {
            "deltas_by_fold": [float(v) for v in deltas],
            "mean_delta": None if mean_d is None else float(mean_d),
            "ci95": [None if lo is None else float(lo), None if hi is None else float(hi)],
            "lift_pct_of_incumbent": (None if mean_d is None else
                                      100.0 * mean_d / float(cell_crps[PC.INCUMBENT].mean())),
            "beats_foil": bool(np.nanmean(deltas) > 0), "fold_wins": fold_wins,
            "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                            "passes": clause.passes(fold_wins)},
            "p_one_sided": PC.onesided_paired_pvalue(deltas),
            "pbo": defl.get("pbo"), "os_gap_pct": defl.get("os_gap_pct"),
            "contender_spread_pct": defl.get("contender_spread_pct"), "flips": defl.get("flips"),
            "dsr": dsr, "trial_srs": [float(t) for t in trial_srs], "observed_sr": observed_sr,
            "bh": {"pvals": {k: (None if v is None else float(v)) for k, v in pvals.items()},
                   "rejected": {k: bool(v) for k, v in bh.items()}, "q": PC.FDR_Q,
                   "note": "prereg §12A A2 — BH over ALL FIVE real arms (stricter than the two "
                           "registered contrasts; it can only prevent a false ADD)"},
            "coverage": coverage, "assembled_pit": assembled_pit,
            "assembled_crps_delta": asm_delta,
            "cell_pit": {"winner": float(cell_pit[winner].mean()),
                         "incumbent": float(cell_pit[PC.INCUMBENT].mean()),
                         "w6d_default_bar_disclosure": PC.W6D_DEFAULT_PIT_BAR,
                         "note": "a NO-HARM clause against the served cell; the 0.03 figure is "
                                 "NF-W6d's Phase-C DEFAULT bar, disclosed and NEVER a gate here "
                                 "(E2.1-r)"},
            "oracle_pairs": {a: PC.oracle_pair_state(mean_cell.get(PC.ORACLE_OF[a]),
                                                     mean_cell.get(PC.MATCHED_OF[a]))
                             for a in PC.REAL_ARMS},
            "winner_own_form_pair": own_pair,
            "degenerate_losses": degen, "magnitude_losses": magn,
            "lockstep": PC.lockstep_reading(observed_sr, trial_srs),
        }
        classification = PC.classify_null(checks, sel=sel, n_folds=n_folds, cv_power=cv_power)
    out["family_a"] = sel
    out["gate"] = {"checks": checks, "ship": bool(checks and all(checks.values()))}
    out["classification"] = classification

    # ── family C: the assembled read + the §8.1 measured Z-column activity ───────────────────────
    out["family_c"] = {
        "mean_assembled_crps": sel["mean_assembled_crps"],
        "mean_assembled_pit": sel["mean_assembled_pit"],
        "mean_assembled_bias": sel["mean_assembled_bias"],
        "assembled_z_column_activity": {
            k: PC.assembly_activity([fr["qb"]["assembled_z_column_gap"][k]
                                     for fr in fold_results if fr.get("qb")])
            for k in ("identity_vs_zm_only", "cond_shift_vs_joint_shift",
                      "cond_scale_vs_joint_scale")},
    }

    # ⭐ the cell's OWN channel, before and after — the quantity NF-W8-0c localised, recomputed
    # through the predecessor's identity so the two records read the same measurement
    out["family_c"]["leg_channel_ppr"] = {
        arm: dict(zip(("contribution_ppr", "conditional_part_ppr"),
                      _incumbent_leg_channel(fold_results, arm)))
        for arm in (PC.INCUMBENT, *PC.REAL_ARMS)
        if any(arm in (fr.get("qb") or {}).get("assembled", {}) for fr in fold_results)}
    out["family_c"]["leg_channel_note"] = (
        f"NF-W8-0c recorded `{PC.LEG}` at {PC.PRED_LEG_CONTRIBUTION_PPR} PPR "
        f"(conditional {PC.PRED_LEG_CONDITIONAL_PPR}) under `identity`; a row-pooled read (NF1.8), "
        f"never a mean of fold means")

    # ── family D: the DOWNSTREAM cross-position verification ─────────────────────────────────────
    def _bias_by_pos(arm: str | None) -> dict[str, list[float]]:
        out_b: dict[str, list[float]] = {}
        for fr in fold_results:
            for pos, s in fr["positions"].items():
                if s.get("skipped") or "bias_identity" not in s:
                    continue
                if pos == PC.POSITION and arm is not None and fr.get("qb"):
                    v = float(fr["qb"]["assembled"][arm]["bias"]["bias"])
                else:
                    v = float(s["bias_identity"]["bias"])
                out_b.setdefault(pos, []).append(v)
        n = {len(v) for v in out_b.values()}
        return out_b if len(n) == 1 else {}

    # ⭐ prereg §12A A8 — the downstream read is computed under EVERY real arm, REPORT-ONLY. It is
    # free (pure arithmetic on stored per-fold biases) and it is the story's downstream question, so
    # a `CELL_NOT_CORRECTED` verdict still RECORDS what the cross-position read would have said.
    # ⛔ It is NOT a selection: `PC.cell_verdict` reads the closure of the §7 winner and nothing
    # else, so an arm that lost the registered contest can never be promoted on this table (that
    # would be the E2.1-r inversion).
    family_d: dict[str, dict] = {}
    for arm in (PC.INCUMBENT, *PC.REAL_ARMS):
        bb = _bias_by_pos(None if arm == PC.INCUMBENT else arm)
        if not bb:
            family_d[arm] = {"evaluable": False,
                             "note": "unpaired fold vectors across positions — UNDEFINED, never a "
                                     "clean read (NF1.7 (a))"}
            continue
        gt = PC.pairwise_gap_tests(bb)
        family_d[arm] = {"evaluable": True, "gap_tests": gt, "closure": PC.gap_closed(gt),
                         "qb_pooled_bias": float(np.mean(bb.get(PC.POSITION, [np.nan])))}
    out["family_d"] = family_d

    closure = (family_d.get(sel["winner"], {}).get("closure")
               if sel.get("winner") and gate_ok(out) else None)
    out["verdict"] = PC.cell_verdict(
        harness_ok=bool(harness["identity_matches_certified"] and harness["transform_identities"]
                        and harness["permutation_is_inactive"]),
        winner=sel.get("winner"), checks=checks, closure=closure,
        own_form_pair=sel.get("winner_own_form_pair"))
    out["cross_rankable"] = bool(out["verdict"].get("cross_rankable"))
    out["promote_blockers"] = list(PC.PROMOTE_BLOCKERS)
    return out


def gate_ok(out: dict) -> bool:
    return bool(out.get("gate", {}).get("ship"))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _fmt(v, nd: int = 4) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "✅" if v else "❌"
    if isinstance(v, (int, float)):
        return f"{float(v):.{nd}f}"
    return str(v)


def write_report(out: dict, path: Path) -> None:
    v = out["verdict"]
    a = out["family_a"]
    L: list[str] = []
    L.append(f"# NF-W8-0e — the QB | `passing_yards` CELL, zero-mass × conditional-level "
             f"(**{v['state']}**)")
    L.append("")
    L.append(f"Generated {out['generated_at']} · gate league **{out['gate_league']}** · "
             f"{out['n_folds']} folds · cell **{PC.CELL}** · ranked on `{PC.CELL_METRIC}`"
             + (" · ⚠️ **PATH PROOF (`--smoke`) — no verdict**" if out.get("smoke") else ""))
    L.append("")
    L.append("⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record "
             "promotes nothing, publishes nothing, re-serves NO NF-W6d cell and writes NO "
             "optimizer input.")
    L.append("")
    L.append("## Verdict")
    L.append("")
    L.append(f"- state: **{v['state']}**")
    L.append(f"- winner: `{v.get('winner')}` · **`cross_rankable`: {out['cross_rankable']}**")
    L.append(f"- {v['reason']}")
    L.append("")
    L.append("## Harness controls (a control that did not run is never a pass — NF1.7 (a))")
    L.append("")
    if out.get("smoke"):
        L.append("> ⚠️ **PATH PROOF.** Two folds at 300 draws: the reproduction pins compare against "
                 "records built at 4000 draws, so `qb_assembly_matches_w7f` and "
                 "`non_qb_bias_matches_w8_0b` CANNOT hit here and their ❌ is the draw count, not a "
                 "defect. Every C arm is identity on fold 1 BY REGISTRATION (prereg §4.1), so the "
                 "statistical clauses are structurally unreachable at n=2 and no verdict is "
                 "claimed.")
        L.append("")
    L.append("| control | holds |")
    L.append("|---|---|")
    for k in ("identity_matches_certified", "transform_identities", "permutation_is_inactive"):
        L.append(f"| `{k}` | {_fmt(out['harness'][k])} |")
    for k, p in out["pins"].items():
        L.append(f"| pin `{k}` | {_fmt(p.get('reproduces', p.get('consistent_within_0_05_ppr')))}"
                 f" — {json.dumps({x: y for x, y in p.items() if x not in ('reproduces',)})[:180]} |")
    L.append("")
    L.append("## ⭐ Family B — the 2×2 (the read this story exists for)")
    L.append("")
    L.append("> `Δ` positive = the arm IMPROVES the metric. `interaction = Δ_joint − (Δ_Z + Δ_C)`. "
             "A SUB_ADDITIVE interaction means the halves OVERLAP — together they buy less than "
             "the sum of their separate effects, which is the NF-W7e shape and exactly why fixing "
             "one then the other would mis-price both.")
    L.append("")
    for name, sq in (("primary (shift) · CRPS", "primary_square_crps"),
                     ("alternative (scale) · CRPS", "alt_square_crps"),
                     ("primary (shift) · |level bias|", "primary_square_level"),
                     ("alternative (scale) · |level bias|", "alt_square_level")):
        r = out["family_b"][sq]
        L.append(f"### {name} — **{r['state']}**")
        L.append("")
        if r["state"] == PC.I_UNDEFINED and "delta_z" not in r:
            L.append(f"- {r.get('reason')}")
            L.append("")
            continue
        L.append("| quantity | mean | CI95 | folds won | p |")
        L.append("|---|---|---|---|---|")
        for k, lab in (("delta_z", "Δ_Z (zero-mass alone)"),
                       ("delta_c", "Δ_C (conditional level alone)"),
                       ("delta_joint", "Δ_joint (both)")):
            d = r[k]
            L.append(f"| {lab} | {_fmt(d['mean'], 5)} | [{_fmt(d['ci95'][0], 5)}, "
                     f"{_fmt(d['ci95'][1], 5)}] | {d['fold_wins']}/{d['n_folds']} | "
                     f"{_fmt(d['p_one_sided'], 4)} |")
        i = r["interaction"]
        L.append(f"| **interaction** | **{_fmt(i['mean'], 5)}** | [{_fmt(i['ci95'][0], 5)}, "
                 f"{_fmt(i['ci95'][1], 5)}] | — | — |")
        L.append(f"| Δ_Z + Δ_C (the sum of the halves) | {_fmt(r['sum_of_halves'], 5)} | — | — | "
                 f"— |")
        L.append(f"| joint ÷ sum-of-halves | {_fmt(r['joint_over_sum_ratio'], 4)} | — | — | — |")
        L.append("")
    L.append("## Family A — the cell contest")
    L.append("")
    L.append(f"- winner `{a.get('winner')}` vs the SERVED cell (`identity`): Δ`{PC.CELL_METRIC}` "
             f"**{_fmt(a.get('mean_delta'), 5)}** "
             f"(CI95 [{_fmt((a.get('ci95') or [None, None])[0], 5)}, "
             f"{_fmt((a.get('ci95') or [None, None])[1], 5)}], "
             f"{a.get('fold_wins')}/{out['n_folds']} folds) · "
             f"lift {_fmt(a.get('lift_pct_of_incumbent'), 3)}% · PBO {_fmt(a.get('pbo'))} · "
             f"DSR {_fmt(a.get('dsr'))} · p {_fmt(a.get('p_one_sided'), 4)}")
    L.append("")
    L.append("| arm | cell CRPS | cell PIT | cell level bias | pred P(0) | assembled CRPS | "
             "assembled PIT | assembled bias |")
    L.append("|---|---|---|---|---|---|---|---|")
    order = [PC.INCUMBENT, *PC.REAL_ARMS, *PC.ANCHOR_ARMS]
    p0 = {}
    for fr in out["fold_results"]:
        if fr.get("qb"):
            for lab, sc in fr["qb"]["cells"].items():
                p0.setdefault(lab, []).append(sc["pred_p0"])
    for lab in order:
        if lab not in a.get("mean_cell_crps", {}):
            continue
        L.append(f"| `{lab}` | {_fmt(a['mean_cell_crps'][lab], 5)} | "
                 f"{_fmt(a['mean_cell_pit'].get(lab))} | "
                 f"{_fmt(a['mean_cell_level_bias'].get(lab), 3)} | "
                 f"{_fmt(float(np.mean(p0[lab])) if lab in p0 else None)} | "
                 f"{_fmt(a['mean_assembled_crps'].get(lab), 5)} | "
                 f"{_fmt(a['mean_assembled_pit'].get(lab))} | "
                 f"{_fmt(a['mean_assembled_bias'].get(lab), 4)} |")
    L.append("")
    L.append(f"- realized cell `P(0)` (pooled): "
             f"{_fmt(float(np.mean([fr['qb']['cells'][PC.INCUMBENT]['real_p0'] for fr in out['fold_results'] if fr.get('qb')])))}"
             f" · NF-W7f recorded {PC.PRED_CELL_REAL_P0} against a served {PC.PRED_CELL_PRED_P0}")
    L.append("")
    if out.get("gate", {}).get("checks"):
        L.append("### The registered clause battery")
        L.append("")
        L.append("| clause | class | verdict |")
        L.append("|---|---|---|")
        for c, ok in out["gate"]["checks"].items():
            cls = ("statistical" if c in PC.STATISTICAL_CLAUSES else
                   "constraint" if c in PC.CONSTRAINT_CLAUSES else "anchor")
            L.append(f"| `{c}` | {cls} | {_fmt(ok)} |")
        L.append("")
        L.append(f"- coverage: {json.dumps(a.get('coverage'))}")
        L.append(f"- assembled PIT (bar {PC.ASSEMBLED_PIT_MAX_DECILE_DEV}): "
                 f"{json.dumps(a.get('assembled_pit'))}")
        L.append(f"- cell PIT: {json.dumps(a.get('cell_pit'))}")
        L.append(f"- per-form oracle pairs (a TIE is INACTIVE, never a refusal — NF-W6d/NF-D20): "
                 f"{json.dumps(a.get('oracle_pairs'))}")
        L.append(f"- degenerates lose: {json.dumps(a.get('degenerate_losses'))} · magnitude "
                 f"bracket loses: {json.dumps(a.get('magnitude_losses'))}")
        L.append(f"- BH (§12A A2, over all five real arms): {json.dumps(a.get('bh'))}")
        L.append("")
    L.append("## Family C — the assembled QB read, and the §8.1 measured Z-column activity")
    L.append("")
    L.append("> ⭐ The consumed QB generator is `zm_floor`, which ALREADY re-splices all thirteen "
             "legs, and the re-splice is idempotent under the RAISE-ONLY rule — so the Z column "
             "was PREDICTED (before the run) to be a structural no-op at the ASSEMBLED layer. "
             "Measured, never assumed; an inactive arm is UNINFORMATIVE, never a pass (NF-D20).")
    L.append("")
    L.append("| comparison | active folds / folds | max abs CRPS gap | inactive |")
    L.append("|---|---|---|---|")
    for k, r in out["family_c"]["assembled_z_column_activity"].items():
        L.append(f"| `{k}` | {r['n_active_folds']}/{r['n_folds']} | "
                 f"{_fmt(r['max_abs_gap'], 9)} | {_fmt(r['inactive'])} |")
    L.append("")
    L.append("### ⭐ The cell's own channel, before and after")
    L.append("")
    L.append(f"> {out['family_c']['leg_channel_note']}")
    L.append("")
    L.append("| arm | `passing_yards` contribution (PPR) | its conditional part (PPR) |")
    L.append("|---|---|---|")
    for arm, d in out["family_c"]["leg_channel_ppr"].items():
        L.append(f"| `{arm}` | {_fmt(d.get('contribution_ppr'))} | "
                 f"{_fmt(d.get('conditional_part_ppr'))} |")
    L.append("")
    L.append("## Family D — the DOWNSTREAM cross-position verification")
    L.append("")
    L.append("> ⭐ Every arm's row is REPORT-ONLY (prereg §12A A8). The verdict reads the closure of "
             "the §7 winner and nothing else — an arm that lost the registered contest can never "
             "be promoted on this table (E2.1-r).")
    L.append("")
    for arm, r in out["family_d"].items():
        if not r.get("evaluable"):
            L.append(f"- under `{arm}`: {r.get('note')}")
            continue
        gt, cl = r["gap_tests"], r["closure"]
        L.append(f"### under `{arm}` — `gap_detected` **{gt.get('gap_detected')}** · QB pooled "
                 f"bias {_fmt(r.get('qb_pooled_bias'))} PPR")
        L.append("")
        L.append("| pair | gap (PPR) | SE | MDE | below MDE | BH rejected |")
        L.append("|---|---|---|---|---|---|")
        for name, p in gt["pairs"].items():
            c = cl["pairs"].get(name, {})
            L.append(f"| {name} | {_fmt(p.get('gap'))} | {_fmt(p.get('se'))} | "
                     f"{_fmt(p.get('mde_ppr'))} | {_fmt(c.get('below_mde'))} | "
                     f"{_fmt(p.get('bh_rejected'))} |")
        L.append("")
        L.append(f"- QB pairs all below their MDEs: {_fmt(cl.get('all_below_mde'))} · none BH "
                 f"rejected: {_fmt(cl.get('none_bh_rejected'))}")
        L.append("")
    if out.get("classification"):
        L.append("## Null classification")
        L.append("")
        L.append(f"```\n{json.dumps(out['classification'], indent=2, default=str)}\n```")
        L.append("")
        L.append("⚠️ The classification describes **family A** — the FITTED cell contest. Family B "
                 "is a deterministic decomposition of stored per-fold scores and family D's bar is "
                 "INHERITED; reading a fold trigger onto either would be the NF-D18 "
                 "misleading-trigger class.")
        L.append("")
    L.append("## Promote blockers")
    L.append("")
    for b in out["promote_blockers"]:
        L.append(f"- {b}")
    L.append("")
    L.append(f"_runtime {out.get('runtime_seconds')}s_")
    path.write_text("\n".join(L) + "\n")


# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-W8-0e — the QB|passing_yards cell 2×2 (§0.5)")
    ap.add_argument("--smoke", action="store_true",
                    help="path proof: the last TWO folds, few draws (artifact _smoke) — no "
                         "verdict. Two, not one: on a single fold every C arm is identity BY "
                         "REGISTRATION (prereg §4.1)")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="re-derive every verdict from the stored per-fold summaries (zero refit)")
    ap.add_argument("--rebuild-cache", action="store_true", help="rebuild the W6d matrix cache")
    ap.add_argument("--rebuild-banks", action="store_true",
                    help="ignore the per-fold marginal-bank cache and refit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    suffix = "_smoke" if args.smoke else ""
    art = _PROJECT_ROOT / _ARTIFACT_REL.replace(".json", f"{suffix}.json")
    rows_dir = _ROWS_DIR.with_name(_ROWS_DIR.name + suffix)

    if args.rewrite_report:
        out = json.loads(art.read_text())
        out = derive_0e(out)
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat()
        art.write_text(json.dumps(out, indent=2, default=str))
        write_report(out, art.with_suffix(".md"))
        log.info("NF-W8-0e report re-derived → %s", art.name)
        return 0

    FA.assert_stat_key_map()
    feat, pit_audit, attach = W6DA.build_matrix_w6d(SEASONS, rebuild_cache=args.rebuild_cache)
    gate_p, bake_p, def_p = W6DS.record_paths("")
    smap = SDSD.served_map(gate_p, bake_p, def_p)
    folds = WP.build_folds(feat)
    if args.smoke:
        folds = folds[-2:]
    draws = 300 if args.smoke else FA.ASSEMBLY_DRAWS
    matrix_key = W6DA.w6d_matrix_key(SEASONS)
    log.info("NF-W8-0e: %d folds × %d positions, %d draws%s [cell %s; field %s]", len(folds),
             len(XP.POSITIONS), draws, " [SMOKE]" if args.smoke else "", PC.CELL,
             list(PC.REAL_ARMS))

    t0 = time.time()
    fold_results: list[dict] = []
    ledgers: list[dict] = []          # ⭐ PRIOR folds only, in chronological order (prereg §4.1)
    for f in folds:
        fr, ledger = run_fold(f, feat, smap, draws=draws, matrix_key=matrix_key,
                              rows_dir=rows_dir, prior_ledgers=list(ledgers),
                              rebuild_banks=args.rebuild_banks)
        fold_results.append(fr)
        if ledger:
            ledgers.append(ledger)
    out = {
        "story": PC.STORY, "predecessors": list(PC.PREDECESSORS), "phase": "qb_passing_cell_2x2",
        "smoke": bool(args.smoke),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seasons": list(SEASONS), "n_folds": len(folds), "gate_league": GATE_LEAGUE,
        "cell": PC.CELL, "declared_field": list(PC.REAL_ARMS),
        "declared_field_size": PC.DECLARED_FIELD_SIZE,
        "matrix_key": matrix_key, "pit_audit": pit_audit, "attach_audit": attach,
        "served_map_sources": {c: v["source"] for c, v in smap.items()},
        "served_cell_form": smap[PC.CELL]["form"], "served_cell_source": smap[PC.CELL]["source"],
        "assembly_draws": draws, "seed": SA._SEED,
        "point_reader": getattr(PC.POINT_READER, "__qualname__", str(PC.POINT_READER)),
        "consumed_generators": dict(XP.CONSUMED_GENERATOR_OF),
        "fold_results": fold_results, "runtime_seconds": round(time.time() - t0, 1),
    }
    leg_c, leg_k = _incumbent_leg_channel(fold_results)
    out["pins"] = {
        "qb_assembly_matches_w7f": _w7f_qb_pins(fold_results),
        "non_qb_bias_matches_w8_0b": _w8_0b_non_qb_pins(fold_results),
        "w8_0c_leg_contribution": _w8_0c_leg_pin(leg_c, leg_k),
        "incumbent_cell_is_the_served_cell": {
            "reproduces": all(fr["qb"]["identity_matches_certified"]["matches"]
                              for fr in fold_results if fr.get("qb")),
            "note": "the identity assembly reproduces the certified `zm_floor` exactly, which "
                    "is only possible if the identity CELL is the served cell"},
    }
    out = derive_0e(out)
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(json.dumps(out, indent=2, default=str))
    write_report(out, art.with_suffix(".md"))
    log.info("NF-W8-0e %s (cross_rankable=%s) → %s (%.1fs)", out["verdict"]["state"],
             out["cross_rankable"], art.name, out["runtime_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
