"""run_nf_w7d_qb_availability.py — NF-W7d §0.5: does an explicit AVAILABILITY MIXTURE fix the QB
assembled fantasy-point distribution that NF-W7c's single Gaussian copula could not calibrate?

Everything decidable in advance is a CONSTANT in `fp_availability_mixture.py`; this runner READS it
(NF-D16). The narrative pre-registration is committed at
`ablation_results/nf_w7d_preregistration.md` BEFORE the full run.

PIPELINE (one target — `league_fantasy_points` under NF-W7c's declared gate league; QB GATES, the
other three positions are REPORT-ONLY):
  · the matrix, folds, PIT gate, per-stat MARGINALS and league weights are NF-W7c's VERBATIM — the
    marginals come through the NF-W6d SERVING DISPATCH and are neither refit nor re-selected, so
    this story adds ONLY the availability mixture over the joint law;
  · per fold × position: Σ̂ on ACTIVE rows only (the conditional half) + π̂ from three pre-registered
    estimators (the availability half) → three mixture arms, against the NF-W7c incumbent
    (`single_copula`, reproduced EXACTLY) and the matched foil (`mix_off` — the mixture's own Σ,
    availability term off), sharing ONE base-normal block with every anchor;
  · gate: crps_q199 vs the best CONTEST foil ∧ the fold clause ∧ PBO ∧ DSR ∧ BH-FDR ∧ the
    coverage(80) floor ∧ ⭐ randomized-PIT decile flatness (the statistic NF-W7c refused QB on)
    ∧ degenerates/permutation/oracles ∧ the three inherited DEPENDENCE clauses ∧ the two clauses
    this story adds (`mixture_is_active`, `mixture_preserves_marginals`) ∧ `incumbent_reproduces`.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: writes LOCAL artifacts only — no
`--publish`, no S3 client, no boto3, no dbt, no Dagster.

RUN (OPERATOR — LAPTOP; reads the S3 NFL lake read-only, writes local artifacts):

    # path proof: 1 fold, QB only, few draws (artifact _smoke) — no verdict
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7d_qb_availability --smoke

    # the decisive run (>2 min — OPERATOR)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7d_qb_availability

    # re-derive every verdict from the stored fold scores at ZERO refit cost (NF-W2e / NF-W3)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7d_qb_availability --rewrite-report
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
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    fp_availability_mixture as MX,
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
    run_nf_w7c_fp_assembly as W7C,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    stat_distribution_serving_d as SDSD,
)
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_w7d")

SEASONS = W6DA.SEASONS
FEATURES = list(WP.FEATURES)
#: ⛔ NF-W7c's gate league, INHERITED. Re-choosing the league in the successor to a refusal would
#: be shopping the population until the bar clears (E2.1-r).
GATE_LEAGUE = W7C.GATE_LEAGUE

_ARTIFACT_REL = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                 "nf_w7d_qb_availability.json")

# The frame/marginal plumbing is NF-W7c's, by IDENTITY — a second copy of a matrix builder is a
# copy that drifts, and this story's whole comparison rests on the marginals being the same ones.
realized_matrix = W7C.realized_matrix
bank_tensor = W7C.bank_tensor


def _marginals(train: pd.DataFrame, serve: pd.DataFrame, smap: dict) -> dict[str, np.ndarray]:
    """⛔ The SERVING dispatch, so the assembly can never consume a marginal the served substrate
    would not.

    ⭐ ONE serve context, not NF-W7c's two: `joint_pit` is not in this story's declared field, so
    the residual-PIT window it needed (8,000 extra predict rows per fold) is not built. That is a
    consequence of the field, never a performance shortcut applied to a shared path."""
    banks, _notes = SDSD.serve_banks(train, serve, smap)
    return banks


# ── One fold × position ─────────────────────────────────────────────────────────────────────────
def run_position(position: str, train: pd.DataFrame, test: pd.DataFrame, weights: np.ndarray, *,
                 draws: int, ctx_te: dict) -> dict:
    """Every arm, foil and anchor for one (fold, position), on ONE shared base-normal stream.

    `ctx_te` is the fold's marginal context, built ONCE by `run_fold` — `serve_banks` fits per
    (form, stat) across every position and then slices, so building it inside this function would
    redo the identical ~113 LightGBM fits once per position (NF-W7c measured that at 868.7s for a
    single position)."""
    tr_p = train.loc[train["position"].astype(str) == position].reset_index(drop=True)
    te_p = test.loc[test["position"].astype(str) == position].reset_index(drop=True)
    if len(te_p) == 0 or len(tr_p) < MX.MIN_ESTIMATION_ROWS:
        return {"skipped": f"train {len(tr_p)} / test {len(te_p)} rows — below the estimation "
                           f"floor ({MX.MIN_ESTIMATION_ROWS}); REFUSED, not defaulted"}

    b_te = bank_tensor(ctx_te, position, len(te_p))
    raw_tr, raw_te = realized_matrix(tr_p), realized_matrix(te_p)
    y_te = FA.score_realized(raw_te, weights)

    # The matched-n capacity control (NF1.9 (f)): the most recent TRAIN rows sized to the test
    # block — same family, same sample size, same marginals. A row SUBSET, so it costs no fits.
    n_match = max(len(te_p), MX.MIN_ESTIMATION_ROWS)
    m_tr = np.sort(np.argsort(tr_p["gw"].to_numpy(), kind="stable")[-n_match:])
    tr_m = tr_p.iloc[m_tr].reset_index(drop=True)
    raw_m = raw_tr[m_tr]
    if int(MX.activity_indicator(raw_m).sum()) < MX.MIN_ESTIMATION_ROWS:
        return {"skipped": f"the matched-n control carries "
                           f"{int(MX.activity_indicator(raw_m).sum())} ACTIVE {position} rows, "
                           f"below the estimation floor ({MX.MIN_ESTIMATION_ROWS}) — the per-form "
                           f"oracle floor could not be evaluated at matched n, so this fold is "
                           f"REFUSED rather than scored against an anchor that did not run "
                           f"(NF1.7 (a))"}

    # ── Σ: the conditional (ACTIVE-rows-only) half, in three estimation contexts + the incumbent's
    sig_played, sig_note = MX.sigma_played(raw_tr)
    sig_played_or, _ = MX.sigma_played(raw_te)
    sig_played_mn, _ = MX.sigma_played(raw_m)
    sig_all, sig_all_note = FA.position_sigma(raw_tr)          # NF-W7c's `joint_rank` Σ, verbatim

    banks: dict[str, np.ndarray] = {}
    clamps: dict[str, dict] = {}
    pi_summary: dict[str, dict] = {}
    #: the PRIMARY arm's train-context π̂ / clamped π, kept so the permutation anchor and the
    #: marginal diagnostic reuse the SAME fit rather than paying for it twice more per fold
    pi_primary_hat: np.ndarray | None = None
    pi_primary_used: np.ndarray | None = None
    for arm in MX.REAL_ARMS:
        ctxs = {
            "": (MX.pi_for_arm(arm, tr_p, te_p, FEATURES, train_raw=raw_tr), sig_played),
            "oracle__": (MX.pi_for_arm(arm, te_p, te_p, FEATURES, train_raw=raw_te),
                         sig_played_or),
            "matched_n__": (MX.pi_for_arm(arm, tr_m, te_p, FEATURES, train_raw=raw_m),
                            sig_played_mn),
        }
        for prefix, (pi_hat, sig) in ctxs.items():
            pi_used, note = MX.clamp_pi(pi_hat, b_te)
            banks[f"{prefix}{arm}"] = MX.assemble_mixture_bank(
                b_te, weights, pi=pi_used, corr=sig, draws=draws)
            if not prefix:
                clamps[arm] = note
                if arm == MX.PRIMARY_ARM:
                    pi_primary_hat, pi_primary_used = pi_hat, pi_used
                pi_summary[arm] = {
                    "mean": round(float(pi_hat.mean()), 4),
                    "sd": round(float(pi_hat.std()), 4),
                    "p10": round(float(np.quantile(pi_hat, 0.10)), 4),
                    "p90": round(float(np.quantile(pi_hat, 0.90)), 4),
                }

    # ── The two CONTEST foils. `single_copula` IS NF-W7c's `joint_rank` construction, and
    # `mix_off` is the MATCHED foil: this story's own conditional Σ with the availability term
    # off. So (mixture − mix_off) isolates the SPLIT and (mix_off − single_copula) isolates the
    # Σ-estimation population — a two-step attribution rather than one bundled claim.
    banks["single_copula"] = FA.assemble_fp_bank(b_te, weights, corr=sig_all, draws=draws)
    banks["mix_off"] = FA.assemble_fp_bank(b_te, weights, corr=sig_played, draws=draws)
    # the REFERENCE foils — scored and reported, never binding `beats_foil` (see MX.REFERENCE_FOILS)
    banks["assembled_indep"] = FA.assemble_fp_bank(b_te, weights, mode="indep", draws=draws)
    banks["assembled_comonotone"] = FA.assemble_fp_bank(b_te, weights, mode="comonotone",
                                                        draws=draws)

    # ⭐ THE π PERMUTATION ANCHOR — the primary arm's own availability probabilities, shuffled
    # across players WITHIN a global week: the same π marginal, the wrong players. It tests the
    # per-row availability SIGNAL directly (NF-D10's matched-pair discipline aimed at the exact
    # channel), and it must LOSE. ⛔ Permuted BEFORE the clamp, so every row's marginal-admissible
    # floor is still applied to the value it actually receives.
    if pi_primary_hat is None or pi_primary_used is None:
        raise ValueError(f"{position}: the primary arm `{MX.PRIMARY_ARM}` produced no train-context "
                         f"π — the permutation anchor and the marginal diagnostic would run "
                         f"against a different fit than the arm they describe")
    pi_perm, _ = MX.clamp_pi(
        KW.permute_within_group(pi_primary_hat, te_p["gw"].to_numpy()), b_te)
    banks["pi_permuted"] = MX.assemble_mixture_bank(b_te, weights, pi=pi_perm, corr=sig_played,
                                                    draws=draws)

    # the direct-learned reference + its own oracle (the ACTIVITY POSITIVE CONTROL: a peek that
    # provably ACTS, run through the identical evaluator) + the label permutation
    tr_p, te_p = tr_p.copy(), te_p.copy()
    tr_p[FA.TARGET] = FA.score_realized(raw_tr, weights)
    te_p[FA.TARGET] = y_te
    banks["foil_direct_points"] = KW.fit_direct_points(tr_p, te_p, FEATURES, FA.TARGET)
    banks["oracle__foil_direct_points"] = KW.fit_direct_points(te_p, te_p, FEATURES, FA.TARGET)
    banks["permuted_direct"] = KW.fit_direct_points(
        tr_p, te_p, FEATURES, FA.TARGET,
        y_train=KW.permute_within_group(tr_p[FA.TARGET].to_numpy(float),
                                        tr_p["gw"].to_numpy()))

    # degenerates — SCORED, never reasoned about. `zero_width` sits at the train MEAN, not the
    # median: NF-W7c's smoke measured a median-located point mass collapsing onto `nihilist_zero`
    # on this zero-heavy cohort, which silently costs the sharpness degenerate its distinctness.
    pts_tr = tr_p[FA.TARGET].to_numpy(float)
    loc = float(np.mean(pts_tr))
    clim = np.quantile(pts_tr, FA.EVAL_LEVELS)[None, :] * np.ones((len(te_p), 1))
    banks["nihilist_zero"] = np.zeros((len(te_p), FA.N_LEVELS))
    banks["zero_width"] = np.full_like(clim, loc)
    banks["max_width"] = loc + 3.0 * (clim - loc)

    missing = sorted(set(MX.ALL_LABELS) - set(banks))
    if missing:
        raise ValueError(f"{position}: the declared field is incomplete — {missing} produced no "
                         f"predictive. A field scored with an arm silently missing is not the "
                         f"declared field (NF1.7 (a)).")

    scores: dict[str, float] = {}
    for label, bank in banks.items():
        KW.assert_finite_predictive(bank, f"{position}/{label}")
        scores[label] = float(np.mean(KW.crps_dense(bank, y_te)))
    watched = (*MX.REAL_ARMS, *MX.FOILS, "assembled_comonotone", "pi_permuted")
    coverage = {lab: KW.coverage80_dense(banks[lab], y_te) for lab in watched}
    # ⭐ the DECILE VECTOR, not just its max — NF-W7c §11.2's carded instrumentation gap
    pit = {lab: MX.pit_detail(KW.randomized_pit_from_bank(banks[lab], y_te)) for lab in watched}

    # the diagnostic runs on the PRIMARY arm's own clamped π — the same vector the scored arm used
    drift = MX.mixture_marginal_drift(b_te, pi=pi_primary_used, corr=sig_played)
    return {
        "scores": scores, "coverage": coverage, "pit_flatness": pit,
        "n_train": int(len(tr_p)), "n_test": int(len(te_p)),
        "atom_rate_train": round(MX.atom_rate(raw_tr), 4),
        "atom_rate_test": round(MX.atom_rate(raw_te), 4),
        "pi_summary": pi_summary, "clamp": clamps, "marginal_drift": drift,
        "sigma_note_played": sig_note,
        # ⭐ THE MECHANISM, MEASURED PER FOLD: §11.1's availability RATIO on this fold's own train
        # rows. It is the statistic that ORDERS the PIT failure across positions, so recording it
        # beside the score makes the mechanism auditable rather than inherited.
        "mean_abs_offdiag": {
            "all_rows": round(float(np.abs(sig_all[~np.eye(FA.N_LEGS, dtype=bool)]).mean()), 4),
            "active_rows": round(float(np.abs(sig_played[~np.eye(FA.N_LEGS, dtype=bool)]).mean()),
                                 4),
        },
        "sigma_all_note": {k: v for k, v in sig_all_note.items() if k != "loadings"},
    }


def run_fold(fold: WP.Fold, feat: pd.DataFrame, smap: dict, *, draws: int,
             positions: tuple[str, ...]) -> dict:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    cfg = LP.get_preset(GATE_LEAGUE)
    t_m = time.time()
    ctx_te = _marginals(train, test, smap)
    log.info("[W7d] fold %s marginals in %.1fs (test %d rows)", fold.label, time.time() - t_m,
             len(test))
    out: dict[str, dict] = {}
    for position in positions:
        FA.assert_assembly_is_priceable(cfg, position)      # fail-closed on an unmodeled term
        t_p = time.time()
        out[position] = run_position(position, train, test, FA.leg_weights(cfg, position),
                                     draws=draws, ctx_te=ctx_te)
        log.info("[W7d] fold %s %s in %.1fs", fold.label, position, time.time() - t_p)
    log.info("[W7d] fold %s complete in %.1fs", fold.label, time.time() - t0)
    return {"label": fold.label, "n_test": int(len(test)), "positions": out}


# ── Selection (derived from stored fold scores — NF-W2e: zero refit cost) ────────────────────────
def _usable(fold_results: list[dict], position: str) -> list[dict]:
    return [fr for fr in fold_results
            if position in fr["positions"] and not fr["positions"][position].get("skipped")]


def _pooled_coverage(usable: list[dict], position: str, label: str) -> dict:
    rows = [fr["positions"][position]["coverage"][label] for fr in usable]
    n_tot = int(sum(r["n"] for r in rows))
    if not n_tot:
        return {"coverage": None, "n_rows": 0, "binomial_se": None, "blocking_shortfall": False}
    cov = sum(r["coverage"] * r["n"] for r in rows) / n_tot
    se = float(np.sqrt(MX.COVERAGE_FLOOR * (1 - MX.COVERAGE_FLOOR) / n_tot))
    return {"coverage": round(float(cov), 4), "n_rows": n_tot, "binomial_se": round(se, 4),
            "blocking_shortfall": bool((MX.COVERAGE_FLOOR - cov) > MX.COVERAGE_BLOCK_SE * se)}


def _incumbent_record_scores() -> dict[str, float] | None:
    """NF-W7c's recorded per-fold `joint_rank` CRPS, per position — the reproduction target."""
    p = _PROJECT_ROOT / MX.INCUMBENT_RECORD_RELPATH
    if not p.exists():
        return None
    rec = json.loads(p.read_text())
    if rec.get("story") != FA.STORY or rec.get("smoke"):
        return None
    out: dict[str, float] = {}
    for fr in rec.get("fold_results", []):
        for pos, block in fr.get("positions", {}).items():
            if not block.get("skipped"):
                out[f"{pos}|{fr['label']}"] = float(block["scores"][MX.INCUMBENT_ARM])
    return out or None


def select_position(fold_results: list[dict], position: str) -> dict | None:
    usable = _usable(fold_results, position)
    if len(usable) < 2:
        return None
    mat = pd.DataFrame({fr["label"]: fr["positions"][position]["scores"] for fr in usable}).T
    mean_s = mat.mean(axis=0)
    # ⭐ RANKED ON CRPS, NEVER ON PIT — see MX.SELECTION_IS_CRPS_NOT_PIT. The PIT bar is a gate
    # clause on the arm this line selects; letting PIT rank would hand the contest to the
    # over-correlated degenerate, which NF-W7c measured posting the best PIT in the QB field.
    winner = str(mean_s[list(MX.REAL_ARMS)].idxmin())
    best_foil = str(mean_s[list(MX.CONTEST_FOILS)].idxmin())
    deltas = (mat[best_foil] - mat[winner]).to_numpy(float)
    mean_d, lo, hi = KW.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(len(usable))
    defl = NF18.deflate(mat[list(MX.ELIGIBLE)], subset=list(MX.ELIGIBLE))
    trial_srs = []
    for arm in MX.REAL_ARMS:
        d = (mat[best_foil] - mat[arm]).to_numpy(float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
    pval = M14.onesided_paired_pvalue(deltas)
    perm_lift = (mat[best_foil] - mat["permuted_direct"]).to_numpy(float)
    p_perm = M14.onesided_paired_pvalue(perm_lift)
    pi_perm_lift = (mat[best_foil] - mat["pi_permuted"]).to_numpy(float)
    p_pi_perm = M14.onesided_paired_pvalue(pi_perm_lift)
    sd = float(np.nanstd(deltas, ddof=1))

    oracle_states = {a: MX.oracle_floor_state(mat[a], mat[f"oracle__{a}"], mat[f"matched_n__{a}"],
                                              indep_by_fold=mat["mix_off"])
                     for a in MX.REAL_ARMS}
    oracle_control = {f: MX.oracle_floor_state(mat[f], mat[f"oracle__{f}"], mat[f],
                                               indep_by_fold=mat["mix_off"])
                      for f in MX.FOILS_WITH_ORACLE}

    # ── the two clauses this story ADDS, both about whether its mechanism could act at all ───────
    atoms = [fr["positions"][position]["clamp"][winner]["mean_installed_atom"] for fr in usable]
    drifts = [fr["positions"][position]["marginal_drift"]["max_probability_drift"] for fr in usable]
    clamp_binding = [fr["positions"][position]["clamp"][winner]["clamp_binding_share"]
                     for fr in usable]

    # ⭐ the incumbent-reproduction identity proof (see MX.incumbent_reproduction)
    record = _incumbent_record_scores()
    repro = MX.incumbent_reproduction(
        {fr["label"]: fr["positions"][position]["scores"][MX.INCUMBENT_FOIL] for fr in usable},
        {k.split("|", 1)[1]: v for k, v in (record or {}).items()
         if k.split("|", 1)[0] == position},
    ) if record else {"reproduces": False, "n_folds_compared": 0, "max_abs_gap": None,
                      "note": ("the NF-W7c record is absent or is a path proof — the reproduction "
                               "control DID NOT RUN, which is never a pass (NF1.7 (a))")}

    pooled_cov = {lab: _pooled_coverage(usable, position, lab)
                  for lab in (*MX.REAL_ARMS, *MX.FOILS, "assembled_comonotone")}
    cov_w, cov_i = pooled_cov[winner], pooled_cov["assembled_indep"]
    cov_c = pooled_cov["assembled_comonotone"]

    # ── PIT: the gate statistic, both conventions, with its direction and a calibrated null ──────
    def _pit_mean(label: str) -> float:
        return float(np.mean([fr["positions"][position]["pit_flatness"][label]["max_decile_dev"]
                              for fr in usable]))

    pit_by_label = {lab: round(_pit_mean(lab), 4)
                    for lab in (*MX.REAL_ARMS, *MX.FOILS, "assembled_comonotone", "pi_permuted")}
    pit_w = _pit_mean(winner)
    pooled = MX.pooled_pit([fr["positions"][position]["pit_flatness"][winner]["decile_counts"]
                            for fr in usable])
    n_per_fold = int(np.mean([fr["positions"][position]["n_test"] for fr in usable]))
    pit_null = MX.pit_null_reference(n_per_fold)

    anchors = {
        "degenerates_lose": bool(all(mean_s[d] > mean_s[winner] for d in MX.DEGENERATES)),
        "degenerate_detail": {d: round(float(mean_s[d]), 4) for d in MX.DEGENERATES},
        "winner_beats_permuted": bool(mean_s["permuted_direct"] > mean_s[winner]),
        "permuted_lift_not_significant": bool(
            float(np.nanmean(perm_lift)) <= 0 or (p_perm is not None and p_perm >= 0.05)),
        # ⭐ the availability-SIGNAL permutation: shuffling π across players must not win
        "winner_beats_pi_permuted": bool(mean_s["pi_permuted"] > mean_s[winner]),
        "oracle_floors_respected_at_matched_n": bool(all(
            oracle_states[a]["state"] != MX.ORACLE_VIOLATED for a in MX.REAL_ARMS)),
        "oracle_ceiling_evaluated": bool(
            any(oracle_states[a]["state"] == MX.ORACLE_RESPECTED for a in MX.REAL_ARMS)),
        "winner_oracle_state": oracle_states[winner]["state"],
        "oracle_floors_respected_PRE_AMENDMENT": bool(all(
            oracle_states[a]["pre_amendment_respected"] for a in MX.REAL_ARMS)),
        "foils_respect_own_oracle": bool(all(
            mean_s[f] > mean_s[f"oracle__{f}"] for f in MX.FOILS_WITH_ORACLE)),
        # ⭐ NF1.9 / NF-D20: a mechanism that cannot act is a FINDING, and it must not be scored
        # as a pass. The clamp can in principle return π ≈ 1 everywhere, at which point the
        # mixture IS its own matched foil and the contest is an arm against itself.
        "mixture_is_active": bool(float(np.mean(atoms)) >= MX.MIN_MIXTURE_ATOM),
        "mixture_preserves_marginals": bool(max(drifts) <= MX.MAX_MARGINAL_DRIFT),
        "incumbent_reproduces": bool(repro["reproduces"]),
    }
    dependence_checks = {
        "independence_under_disperses": bool(cov_i["coverage"] is not None
                                             and cov_i["coverage"] < cov_c["coverage"]),
        "dependence_moves_coverage": bool(cov_c["coverage"] > cov_i["coverage"]),
        "beats_indep_on_coverage": bool(cov_w["coverage"] > cov_i["coverage"]),
    }
    return {
        "position": position, "winner": winner, "best_foil": best_foil,
        "gated": position == MX.GATE_POSITION, "n_folds_used": len(usable),
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
            "pi_permuted_lift_vs_foil_mean": round(float(np.nanmean(pi_perm_lift)), 4),
            "pi_permuted_lift_p_one_sided": p_pi_perm},
        "coverage": {"winner_coverage_80": cov_w["coverage"], "n_rows": cov_w["n_rows"],
                     "binomial_se": cov_w["binomial_se"],
                     "blocking_shortfall": cov_w["blocking_shortfall"]},
        "coverage_by_label": pooled_cov,
        "dependence_checks": dependence_checks,
        # ── the gate statistic ──────────────────────────────────────────────────────────────────
        "pit_flatness_winner_max_decile_dev": round(pit_w, 4),
        "pit_flat_ok": bool(pit_w <= MX.PIT_MAX_DECILE_DEV),
        "pit_by_label": pit_by_label,
        "pit_pooled_rows": pooled,
        "pit_calibrated_null": pit_null,
        "pit_null_p_value": MX.pit_null_pvalue(pit_w, n_per_fold),
        "pit_winner_decile_freq": [
            round(float(v), 4) for v in np.mean(
                [fr["positions"][position]["pit_flatness"][winner]["decile_freq"]
                 for fr in usable], axis=0)],
        # ── the mixture's own diagnostics ───────────────────────────────────────────────────────
        "mixture_detail": {
            "mean_installed_atom": round(float(np.mean(atoms)), 4),
            "atom_by_fold": [round(float(a), 4) for a in atoms],
            "mean_clamp_binding_share": round(float(np.mean(clamp_binding)), 4),
            "max_marginal_drift": round(float(max(drifts)), 5),
            "tolerance": MX.MAX_MARGINAL_DRIFT, "atom_floor": MX.MIN_MIXTURE_ATOM,
            "observed_atom_rate_test": round(float(np.mean(
                [fr["positions"][position]["atom_rate_test"] for fr in usable])), 4),
            "pi_summary_last_fold": usable[-1]["positions"][position]["pi_summary"],
        },
        "incumbent_reproduction": repro,
        # ── attribution: the split, the Σ population, and the architecture reference ────────────
        "attribution": {
            "delta_vs_mix_off_the_split": round(float(mean_s["mix_off"] - mean_s[winner]), 4),
            "delta_vs_single_copula_total": round(
                float(mean_s["single_copula"] - mean_s[winner]), 4),
            "delta_mix_off_vs_single_copula_sigma_population": round(
                float(mean_s["single_copula"] - mean_s["mix_off"]), 4),
            "delta_vs_indep": round(float(mean_s["assembled_indep"] - mean_s[winner]), 4),
            # ⛔ REPORT-ONLY and it may never gate: NF-W7c §11.4 — this answers the ARCHITECTURE
            # question (does assembling from parts beat modelling the total?), not this story's.
            "beats_direct_points_REPORT_ONLY": bool(
                mean_s["foil_direct_points"] > mean_s[winner]),
            "delta_vs_direct_points_REPORT_ONLY": round(
                float(mean_s["foil_direct_points"] - mean_s[winner]), 4),
        },
        "availability_ratio_by_fold": [
            round(fr["positions"][position]["mean_abs_offdiag"]["all_rows"]
                  / max(fr["positions"][position]["mean_abs_offdiag"]["active_rows"], 1e-9), 3)
            for fr in usable],
    }


def compose_gate(sel: dict, fdr_pass: bool) -> dict:
    checks = {
        "beats_foil": bool(sel["beats_foil"]),
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < MX.PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= MX.DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
        "pit_flat_ok": bool(sel["pit_flat_ok"]),
        "degenerates_lose": bool(sel["anchors"]["degenerates_lose"]),
        "permutation_behaves": bool(sel["anchors"]["winner_beats_permuted"]
                                    and sel["anchors"]["permuted_lift_not_significant"]
                                    and sel["anchors"]["winner_beats_pi_permuted"]),
        "oracle_floors_respected": bool(sel["anchors"]["oracle_floors_respected_at_matched_n"]),
        "mixture_is_active": bool(sel["anchors"]["mixture_is_active"]),
        "mixture_preserves_marginals": bool(sel["anchors"]["mixture_preserves_marginals"]),
        "incumbent_reproduces": bool(sel["anchors"]["incumbent_reproduces"]),
        **{k: bool(v) for k, v in sel["dependence_checks"].items()},
    }
    return {"checks": checks, "ship": all(checks.values())}


def classify(sel: dict, checks: dict) -> dict:
    v = cv_power.classify_null(
        metric=f"nf_w7d_qb_availability|{sel['position']}", n_folds=sel["n_folds_used"],
        n_arms=len(MX.REAL_ARMS), beats_foil=sel["beats_foil"],
        observed_sr=sel["observed_sr"], var_trials_sr=sel["var_trials_sr"],
        fold_wins=sel["fold_wins"], p_one_sided=sel["p_one_sided"], bh_cutoff=MX.FDR_Q,
        degenerates_excluded_from_v=True,
        # MH2.7: the declared field is the pre-registered arm count, so the instrument REFUSES to
        # prescribe a smaller one — "trim the field" IS the selection bias DSR exists to deflate.
        declared_field_size=len(MX.REAL_ARMS),
    )
    base = KW.flag_unsafe_field_shrink(
        {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger,
         "field_remedy_admissible": getattr(v, "field_remedy_admissible", None),
         "declared_field_size_source": ("fp_availability_mixture.REAL_ARMS, committed in "
                                        "ablation_results/nf_w7d_preregistration.md §3 before "
                                        "any score"),
         "instrument_verdict": {"state": v.state, "reason": v.reason,
                                "retest_trigger": v.retest_trigger}},
        len(MX.REAL_ARMS))
    out = KW.coverage_constraint_refusal(sel, checks, base, mechanism=MX.REFUSAL_MECHANISM,
                                         remedy=MX.REFUSAL_REMEDY)
    if out is base:
        stat_fail = [c for c in MX.STATISTICAL_CHECKS if not checks.get(c, True)]
        anchor_fail = [c for c in MX.ANCHOR_CHECKS if not checks.get(c, True)]
        # ⭐ NF-D18's 8th state, and the PIT bar is exactly its shape: a per-fold decile deviation
        # against a fixed bar accumulates no sampling error that more folds can remove, so a null
        # resting on it is a CONSTRAINT refusal and must NOT publish a "+N folds" trigger.
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
        elif stat_fail == ["pit_flat_ok"]:
            out = dict(base)
            out.update({
                "state": "CONSTRAINT_REFUSED", "hand_corrected": True,
                "reason": (
                    f"every other gate is GREEN and the ship is refused by the pre-registered PIT "
                    f"flatness bar alone: {sel['pit_flatness_winner_max_decile_dev']} against "
                    f"{MX.PIT_MAX_DECILE_DEV} (NF-W7c's incumbent posted "
                    f"{sel['mean_crps'].get(MX.INCUMBENT_FOIL)} CRPS at 0.0888 on the same "
                    f"statistic). A max-decile deviation against a FIXED bar is a deterministic "
                    f"constraint, not a sampling shortfall — more folds shrink nothing that would "
                    f"move it" + MX.REFUSAL_MECHANISM),
                "retest_trigger": MX.REFUSAL_REMEDY, "failing_statistical_checks": stat_fail,
            })
    out["pbo_state"] = (
        f"EVALUABLE — PBO over the {len(MX.ELIGIBLE)}-config eligible field "
        f"({len(MX.REAL_ARMS)} mixture arms + {len(MX.CONTEST_FOILS)} contest foils); DSR deflates "
        f"over the {len(MX.REAL_ARMS)}-arm declared family (trial SRs from real arms only — "
        f"anchors, degenerates and the two REFERENCE foils never enter V; MH2.1 (a) / DSR-CONV).")
    out["gate_sensitivity"] = KW.gate_sensitivity(checks, waived=())
    return out


def derive_verdict_layer(out: dict) -> dict:
    """⭐ Every decision re-derivable from the stored fold scores — no refit (NF-W2e / NF-W3)."""
    frs = out["fold_results"]
    scored = [p for p in MX.POSITIONS if _usable(frs, p)]
    sels = {p: select_position(frs, p) for p in scored}
    present = {p: s for p, s in sels.items() if s is not None}
    # ⭐ ONE GATED HYPOTHESIS. QB is the position NF-W7c refused; the others are diagnostic, so the
    # BH family carries exactly one member and buys no multiplicity penalty for a report.
    gated = {p: s for p, s in present.items() if p == MX.GATE_POSITION}
    fdr = M14.bh_fdr({f"fp|{p}": s["p_one_sided"] for p, s in gated.items()}, q=MX.FDR_Q)
    gates = {p: compose_gate(s, fdr.get(f"fp|{p}", False)) for p, s in gated.items()}
    nulls = {p: (None if gates[p]["ship"] else classify(gated[p], gates[p]["checks"]))
             for p in gated}
    ship = sorted(p for p in gated if gates[p]["ship"])
    out["selections"] = present
    # ⚠️ "scored but unusable" and "never run" are DIFFERENT findings and must not share a label —
    # a smoke scopes itself to the gate position, and reporting the other three as `unavailable`
    # would claim a measurement that was never attempted (NF1.7 (a), on the reporting side).
    attempted = sorted({p for fr in frs for p in fr["positions"]})
    out["unavailable_positions"] = sorted(set(attempted) - set(present))
    out["positions_not_run"] = sorted(set(MX.POSITIONS) - set(attempted))
    out["fdr"] = fdr
    out["gates"] = gates
    out["null_states"] = {p: n for p, n in nulls.items() if n}
    out["verdict"] = {
        "story_verdict": "SHIP" if ship else "NULL",
        "gate_position": MX.GATE_POSITION,
        "report_only_positions": [p for p in present if p != MX.GATE_POSITION],
        "ship_positions": ship,
        "null_positions": {p: nulls[p]["state"] for p in gated if nulls[p]},
        "gate_league": GATE_LEAGUE,
        "declared_field_size": len(MX.REAL_ARMS),
        "selection_key": MX.SELECTION_IS_CRPS_NOT_PIT,
        "promote_blockers": list(MX.PROMOTE_BLOCKERS),
        "positions_with_unevaluated_oracle_ceiling": sorted(
            p for p, s in present.items() if not s["anchors"]["oracle_ceiling_evaluated"]),
        "winner_oracle_state": {p: s["anchors"]["winner_oracle_state"]
                                for p, s in present.items()},
        # ⛔ stated on the verdict itself so it cannot be missed: a report-only win is a successor
        # hypothesis, never a ship from this record.
        "report_only_note": (
            "RB/WR/TE are DIAGNOSTIC on this record. A report-only position that would have "
            "passed every clause is a hypothesis for a successor to register FORWARD — "
            "re-classifying a result into shippability after seeing it is the E2.1-r inversion."),
    }
    return out


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:
    v = out["verdict"]
    gp = v["gate_position"]
    L = [f"# NF-W7d — QB availability mixture for the assembled FP distribution "
         f"({v['story_verdict']})", "",
         f"Generated {out['generated_at']} · gate position **{gp}** · gate league "
         f"**{GATE_LEAGUE}** · {out['n_folds']} folds · target `{FA.TARGET}` · ranked on "
         f"`{FA.SELECTION_METRIC}` · gated on `{MX.GATE_STATISTIC}`", "",
         "⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record "
         "promotes nothing and publishes nothing.", "",
         "## Verdict", "",
         f"- ship positions: **{v['ship_positions'] or 'none'}**",
         f"- null positions: {v['null_positions'] or 'none'}",
         f"- report-only (diagnostic, never shippable from this record): "
         f"{v['report_only_positions'] or 'none'}",
         f"- scored but unusable: {out['unavailable_positions'] or 'none'}",
         f"- not run in this invocation: {out.get('positions_not_run') or 'none'}", "",
         f"⭐ **Selection key.** {v['selection_key']}", ""]

    L += ["## Per position", "",
          "| pos | gated | winner | best contest foil | Δ CRPS vs foil | CI95 | folds | "
          "**PIT dev** | bar | cov80 | PBO | DSR | gate |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for p, s in out["selections"].items():
        g = out["gates"].get(p)
        ci = s["ci95"]
        L.append(
            f"| {p} | {'**YES**' if s['gated'] else 'report-only'} | `{s['winner']}` | "
            f"`{s['best_foil']}` | {s['mean_delta']:+.4f} | [{ci[0]}, {ci[1]}] | "
            f"{s['fold_wins']}/{s['n_folds_used']} | "
            f"**{s['pit_flatness_winner_max_decile_dev']}** | {MX.PIT_MAX_DECILE_DEV} | "
            f"{s['coverage']['winner_coverage_80']} | {s['pbo']} | {s['dsr']} | "
            f"{'SHIP' if g and g['ship'] else ('NULL' if g else '—')} |")

    L += ["", "## ⭐ The gate statistic — randomized-PIT decile flatness", "",
          "⚠️ **Read the baseline like-for-like.** NF-W7c's QB record reports 0.0888, but that is "
          "its SELECTED winner `joint_double`; the construction this story actually contests is its "
          "pre-registered PRIMARY `joint_rank`, which NF-W7c §11.1 measured at 0.065 and which "
          "appears below as `single_copula` (reproduced here to 1e-9). Comparing a mixture arm "
          "against 0.0888 would overstate the gain by attributing another arm's miscalibration to "
          "it. The whole field is shown "
          "because the bar is a **CONSTRAINT, not a ranking key**: the over-correlated degenerate "
          "`assembled_comonotone` posts a strong PIT precisely *because* perfect dependence is a "
          "crude availability factor, and it loses CRPS by a mile. A criterion a degenerate wins "
          "would be fatal (NF1.8); a constraint it satisfies is fine.", "",
          "| pos | winner PIT (per-fold mean, BINDS) | pooled over rows | perfect-calibration "
          "median at this n | P(this rough \\| calibrated) | worst decile |",
          "|---|---|---|---|---|---|"]
    for p, s in out["selections"].items():
        pooled, null = s["pit_pooled_rows"], s["pit_calibrated_null"]
        L.append(f"| {p} | {s['pit_flatness_winner_max_decile_dev']} | "
                 f"{pooled['max_decile_dev']} (n={pooled['n']}) | {null['median']} "
                 f"(n={null['n']}) | {s['pit_null_p_value']} | {pooled['worst_decile']} |")
    L += ["", "| pos | " + " | ".join(f"`{k}`" for k in
                                      (*MX.REAL_ARMS, *MX.FOILS, "assembled_comonotone")) + " |",
          "|---" * (1 + len(MX.REAL_ARMS) + len(MX.FOILS) + 1) + "|"]
    for p, s in out["selections"].items():
        L.append(f"| {p} | " + " | ".join(
            str(s["pit_by_label"][k])
            for k in (*MX.REAL_ARMS, *MX.FOILS, "assembled_comonotone")) + " |")

    L += ["", "## Attribution — which half of the mixture earned it?", "",
          "`mixture − mix_off` isolates the **split** (the Bernoulli × conditional-rescale "
          "structure) holding the conditional Σ fixed; `mix_off − single_copula` isolates the "
          "**Σ-estimation population** (active rows only vs all rows). A bundled Δ against the "
          "incumbent alone could not tell them apart (NF-D15 (g′)).", "",
          "| pos | Δ vs `mix_off` (the SPLIT) | Δ vs `single_copula` (TOTAL) | "
          "`mix_off` − `single_copula` (the Σ POPULATION) | Δ vs indep | "
          "Δ vs direct points (report-only) |", "|---|---|---|---|---|---|"]
    for p, s in out["selections"].items():
        a = s["attribution"]
        L.append(f"| {p} | {a['delta_vs_mix_off_the_split']:+.4f} | "
                 f"{a['delta_vs_single_copula_total']:+.4f} | "
                 f"{a['delta_mix_off_vs_single_copula_sigma_population']:+.4f} | "
                 f"{a['delta_vs_indep']:+.4f} | "
                 f"{a['delta_vs_direct_points_REPORT_ONLY']:+.4f} |")
    L += ["", "⚠️ **The last column never gates.** NF-W7c §11.4: `classify_null` names the FOIL, "
          "not the hypothesis. `foil_direct_points` answers *does assembling from per-stat parts "
          "beat modelling the total directly* — an ARCHITECTURE question §11.3 cards as its own "
          "successor, and not the question this story asks.", ""]

    L += ["", "## Could the mechanism act? (⭐ measured before it is credited)", "",
          "| pos | mean installed atom | observed all-zero rate | clamp binding share | "
          "max marginal drift | tolerance | active? | marginals preserved? |",
          "|---|---|---|---|---|---|---|---|"]
    for p, s in out["selections"].items():
        m, a = s["mixture_detail"], s["anchors"]
        L.append(f"| {p} | {m['mean_installed_atom']} | {m['observed_atom_rate_test']} | "
                 f"{m['mean_clamp_binding_share']} | {m['max_marginal_drift']} | "
                 f"{m['tolerance']} | {a['mixture_is_active']} | "
                 f"{a['mixture_preserves_marginals']} |")
    L += ["", "A mixture whose clamp binds everywhere IS its own matched foil — an arm compared "
          "against itself, passing on nothing (NF1.9 / NF-D20). The atom is measured, not assumed.",
          ""]

    L += ["", "## ⭐ The incumbent-reproduction identity proof", "",
          "`single_copula` is NF-W7c's pre-registered primary construction. Reproducing its "
          "RECORDED per-fold scores to float precision is what proves the marginals, folds, draws "
          "and scoring did not drift — without it, a drifted harness would still produce a "
          "perfectly plausible contest. It is checkable only because the draw seed was "
          "deliberately INHERITED rather than refreshed.", "",
          "| pos | folds compared | max abs gap | tolerance | reproduces |", "|---|---|---|---|---|"]
    for p, s in out["selections"].items():
        r = s["incumbent_reproduction"]
        L.append(f"| {p} | {r['n_folds_compared']} | {r.get('max_abs_gap')} | "
                 f"{r.get('tolerance', MX.INCUMBENT_TOLERANCE)} | {r['reproduces']} |")

    L += ["", "## Dependence clauses (inherited from NF-W7c)", "",
          "| pos | independence under-disperses | knob moves coverage | winner beats indep on "
          "coverage |", "|---|---|---|---|"]
    for p, s in out["selections"].items():
        d = s["dependence_checks"]
        L.append(f"| {p} | {d['independence_under_disperses']} | "
                 f"{d['dependence_moves_coverage']} | {d['beats_indep_on_coverage']} |")

    L += ["", "## Gate clauses", ""]
    for p, g in out["gates"].items():
        fails = [k for k, ok in g["checks"].items() if not ok]
        L.append(f"- **{p}** — {'all clauses green' if not fails else 'FAILING: ' + ', '.join(fails)}")
        if p in out.get("null_states", {}):
            n = out["null_states"][p]
            L.append(f"  - null state `{n['state']}` — {n['reason']}")
            L.append(f"  - re-test trigger: {n.get('retest_trigger') or 'NONE'}")
            L.append(f"  - field remedy admissible: {n.get('field_remedy_admissible')}")

    L += ["", "## Anchors (all SCORED, never reasoned about)", ""]
    for p, s in out["selections"].items():
        L.append(f"- **{p}** degenerates {s['anchors']['degenerate_detail']} vs winner "
                 f"{s['mean_crps'][s['winner']]}")
        L.append(f"  - π permutation (the availability SIGNAL): `pi_permuted` "
                 f"{s['mean_crps']['pi_permuted']}, winner beats it "
                 f"{s['anchors']['winner_beats_pi_permuted']}")
        for a, o in s["oracle_detail"].items():
            L.append(f"  - oracle floor `{a}`: **{o['state']}** (arm {o['arm']}, own-form oracle "
                     f"{o['own_form_oracle']}, matched-n {o['matched_n']}, peek gain vs arm "
                     f"{o['peek_gain_vs_arm']}, inversion p {o['inversion_p_one_sided']})")
        for f_, o in s.get("oracle_activity_control", {}).items():
            L.append(f"  - ⭐ activity POSITIVE CONTROL `{f_}`: **{o['state']}**, peek gain "
                     f"{o['peek_gain_vs_arm']} — proves the detector can see an oracle that acts")
        if not s["anchors"]["oracle_ceiling_evaluated"]:
            L.append("  - ⚠️ every per-form oracle here is INACTIVE: the peek estimates Σ and π on "
                     "the test block while its arm estimates them on the full train window, so "
                     "the ceiling is NOT a ceiling. UNEVALUATED — uninformative, not a pass "
                     "(NF-D20 / NF-W6d).")

    L += ["", "## The mechanism, re-measured per fold", "",
          "NF-W7c §11.1 found the availability RATIO (ρ̄ all rows ÷ ρ̄ played-only) orders the PIT "
          "failure across positions while the zero-atom SIZE does not. Recorded here per fold so "
          "the mechanism is auditable rather than inherited.", "",
          "| pos | all-zero rate (test) | ρ̄ ratio by fold |", "|---|---|---|"]
    for p, s in out["selections"].items():
        L.append(f"| {p} | {s['mixture_detail']['observed_atom_rate_test']} | "
                 f"{s['availability_ratio_by_fold']} |")

    L += ["", "## Relation to NF-W4 (which nulled an availability mixture ×4)", "",
          "- NF-W4 **Layer A** modelled the roster PLAYED label and **SHIPPED** it — availability "
          "is modelable, a certified result this story CONSUMES.",
          "- NF-W4 **Layer B** injected projected availability as a **FEATURE** into the "
          "point/quantile champion and returned GENUINE_ABSENCE ×3 + POWER_LIMITED. That is the "
          "null: a learner already given lagged usage cannot be told anything new by an "
          "availability COLUMN.",
          "- NF-W7d consumes availability as a **component of the predictive's draw law** and is "
          "gated on a statistic NF-W4 never scored — the assembled total's joint-zero atom and its "
          "randomized-PIT flatness. A feature cannot put an atom in a distribution.",
          "- ⛔ A null here does NOT re-decide NF-W4; a ship here does NOT re-open its Layer B.", ""]

    # ⭐ The labelling belongs IN the record, not only in the JSON: a promote blocker below points
    # the consumer at `calibration_warning`, and a report that never SHOWS it asks a reader to
    # trust a field they cannot see (NF-W6d's labelling carry, inherited from NF-W7c).
    L += ["", "## What the assembled row is actually made of (inherited from NF-W7c)", "",
          "| pos | source | priced legs from a bake-off winner | on a calibrated DEFAULT |",
          "|---|---|---|---|"]
    for p, lab in out.get("labelling", {}).items():
        defaults = set(lab.get("default_priced_legs") or ())
        won = [x for x in lab.get("priced_legs", ()) if x not in defaults]
        L.append(f"| {p} | `{lab.get('source')}` | {len(won)} of {len(lab.get('priced_legs', ()))}"
                 f" | {len(defaults)} |")
    for p, lab in out.get("labelling", {}).items():
        if lab.get("calibration_warning"):
            L.append(f"- **{p}** — {lab['calibration_warning']}")

    L += ["", "## Promote blockers", ""] + [f"- {b}" for b in v["promote_blockers"]] + [""]
    L += [v["report_only_note"], ""]
    path.write_text("\n".join(L))


# ── Orchestration ───────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-W7d — QB availability mixture (§0.5)")
    ap.add_argument("--smoke", action="store_true",
                    help="path proof: 1 fold, gate position only, few draws (artifact _smoke)")
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
        log.info("NF-W7d report re-derived → %s", art.name)
        return 0

    FA.assert_stat_key_map()
    feat, pit_audit, attach = W6DA.build_matrix_w6d(SEASONS, rebuild_cache=args.rebuild_cache)
    # ⭐ ALWAYS the FULL W6d records — never the `_smoke` variants, even on a smoke run: `suffix`
    # names THIS story's own artifact, and letting one variable do both jobs would let a PATH PROOF
    # feed the served map (NF-W7c's own finding, inherited).
    gate_p, bake_p, def_p = W6DS.record_paths("")
    smap = SDSD.served_map(gate_p, bake_p, def_p)
    folds = WP.build_folds(feat)
    positions: tuple[str, ...] = (MX.GATE_POSITION,) if args.smoke else MX.POSITIONS
    if args.smoke:
        folds = folds[-1:]
    draws = 300 if args.smoke else MX.ASSEMBLY_DRAWS
    log.info("NF-W7d: %d folds × %d positions, %d legs, %d draws%s", len(folds), len(positions),
             MX.N_LEGS, draws, " [SMOKE]" if args.smoke else "")

    t0 = time.time()
    fold_results = [run_fold(f, feat, smap, draws=draws, positions=positions) for f in folds]
    out = {
        "story": MX.STORY, "phase": "availability_mixture", "smoke": bool(args.smoke),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seasons": list(SEASONS), "n_folds": len(folds), "gate_league": GATE_LEAGUE,
        "gate_position": MX.GATE_POSITION,
        "matrix_key": W6DA.w6d_matrix_key(SEASONS), "pit_audit": pit_audit,
        "attach_audit": attach, "served_map_sources": {c: v["source"] for c, v in smap.items()},
        "assembly_draws": draws, "row_block": MX.ROW_BLOCK, "seed": MX._SEED,
        "seed_inherited_from": FA.STORY,
        "avail_stream_offset": MX.AVAIL_STREAM_OFFSET,
        "declared_field": {"real_arms": list(MX.REAL_ARMS),
                           "contest_foils": list(MX.CONTEST_FOILS),
                           "reference_foils": list(MX.REFERENCE_FOILS),
                           "degenerates": list(MX.DEGENERATES), "anchors": list(MX.ANCHORS)},
        "labelling": {p: FA.assembled_labelling(smap, LP.get_preset(GATE_LEAGUE), p)
                      for p in positions},
        "fold_results": fold_results, "runtime_seconds": round(time.time() - t0, 1),
    }
    out = derive_verdict_layer(out)
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(json.dumps(out, indent=2, default=str))
    write_report(out, art.with_suffix(".md"))
    log.info("NF-W7d %s → %s (%.1fs)", out["verdict"]["story_verdict"], art.name,
             out["runtime_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
