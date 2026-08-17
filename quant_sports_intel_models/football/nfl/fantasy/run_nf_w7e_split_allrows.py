"""run_nf_w7e_split_allrows.py — NF-W7e §0.5: the availability SPLIT over the ALL-ROWS Σ, scored
against the same reproduced incumbent as NF-W7d, with every position registered SHIPPABLE — plus
the ATOM-CAP confirmation (is QB's PIT ceiling set by the marginal layer?).

Everything decidable in advance is a CONSTANT in `fp_availability_split_allrows.py`; this runner
READS it (NF-D16). The narrative pre-registration is committed at
`ablation_results/nf_w7e_preregistration.md` BEFORE the full run.

PIPELINE (one target — `league_fantasy_points` under NF-W7c's declared gate league; ALL FOUR
positions gate):
  · the matrix, folds, PIT gate, per-stat MARGINALS and league weights are NF-W7c/W7d's VERBATIM
    (the marginals through the NF-W6d SERVING DISPATCH — neither refit nor re-selected);
  · per fold × position: Σ̂ on ALL rows (the incumbent's own estimator) + π̂ from NF-W7d's three
    estimators → three all-rows mixture arms, against the incumbent `single_copula` (reproduced
    to 1e-9 vs NF-W7c) and NF-W7d's registered arm `mix_played` (reproduced to 1e-9 vs NF-W7d),
    with `mix_off` completing the 2×2, all on ONE base-normal block with every anchor;
  · gate: crps_q199 vs the best CONTEST foil ∧ the fold clause ∧ PBO ∧ DSR ∧ BH-FDR over the four
    positions ∧ the coverage(80) floor ∧ randomized-PIT flatness ≤ 0.05 ∧ degenerates /
    permutations / oracles ∧ the three inherited DEPENDENCE clauses ∧ `mixture_is_active` ∧
    `mixture_preserves_marginals` ∧ `incumbent_reproduces` ∧ `predecessor_reproduces` ∧
    `atom_is_sigma_invariant`;
  · the ATOM-CAP verdict, read on QB by the pre-registered rule `SA.atom_cap_verdict`.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: writes LOCAL artifacts only — no
`--publish`, no S3 client, no boto3, no dbt, no Dagster.

RUN (OPERATOR — LAPTOP; reads the S3 NFL lake read-only, writes local artifacts):

    # path proof: 1 fold, QB only, few draws (artifact _smoke) — no verdict
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7e_split_allrows --smoke

    # the decisive run (>2 min — OPERATOR; ~90 min on the laptop, dominated by the W6d marginals)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7e_split_allrows

    # re-derive every verdict from the stored fold scores at ZERO refit cost (NF-W2e / NF-W3)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w7e_split_allrows --rewrite-report

⭐ Per-fold MARGINAL BANKS are cached under `artifacts/nf_w7e_bank_cache/` (gitignored), keyed on
the matrix key + fold label + a hash of the served map: the W6d dispatch is ~370–470 s per fold and
is byte-identical across runs (NF-W7d's `incumbent_reproduces` proved it), so a re-score after a
harness fix pays only for the draws. A cache hit is LOGGED with its key; `--rebuild-banks` forces
the fits.
"""
from __future__ import annotations

import argparse
import hashlib
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
    fp_availability_mixture as MX,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    fp_availability_split_allrows as SA,
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
    run_nf_w7d_qb_availability as W7D,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    stat_distribution_serving_d as SDSD,
)
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_w7e")

SEASONS = W6DA.SEASONS
FEATURES = list(WP.FEATURES)
#: ⛔ NF-W7c's gate league, INHERITED through NF-W7d (E2.1-r).
GATE_LEAGUE = W7D.GATE_LEAGUE

_ARTIFACT_REL = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                 "nf_w7e_split_allrows.json")
_BANK_CACHE_DIR = Path(__file__).resolve().parent / "artifacts" / "nf_w7e_bank_cache"

# The frame/marginal plumbing is NF-W7c's, by IDENTITY (through NF-W7d).
realized_matrix = W7D.realized_matrix
bank_tensor = W7D.bank_tensor


# ── Marginal banks, cached per fold ─────────────────────────────────────────────────────────────
def _smap_key(smap: dict) -> str:
    payload = json.dumps({c: (v["form"], v["source"]) for c, v in sorted(smap.items())},
                         sort_keys=True)
    return hashlib.sha1(payload.encode()).hexdigest()[:12]


def _marginals_cached(fold_label: str, train: pd.DataFrame, test: pd.DataFrame, smap: dict, *,
                      matrix_key: str, rebuild: bool = False) -> tuple[dict[str, np.ndarray], str]:
    """The SERVING dispatch's per-cell banks for one fold — from disk when a byte-identical build
    is already cached, else fitted and cached. Returns (banks, 'hit'|'miss')."""
    path = _BANK_CACHE_DIR / f"{matrix_key}_{fold_label}_{_smap_key(smap)}.npz"
    if path.exists() and not rebuild:
        with np.load(path) as z:
            banks = {k: z[k] for k in z.files}
        # ⛔ a stale cache must be impossible to READ (NF-C0e (c)): the served map's cells and the
        # test frame's per-position row counts must match exactly, or the cache is refused
        pos = test["position"].astype(str).to_numpy()
        ok = set(banks) == set(smap) and all(
            banks[c].shape == (int((pos == c.split("|", 1)[0]).sum()), FA.N_LEVELS)
            for c in smap)
        if ok:
            log.info("[W7e] fold %s marginal banks: cache HIT %s", fold_label, path.name)
            return banks, "hit"
        log.warning("[W7e] fold %s marginal bank cache %s does not match the served map / test "
                    "frame — REFUSED and rebuilt", fold_label, path.name)
    banks, _notes = SDSD.serve_banks(train, test, smap)
    _BANK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(path, **{k: np.asarray(v, dtype=float) for k, v in banks.items()})
    log.info("[W7e] fold %s marginal banks: cache MISS → fitted and cached %s", fold_label,
             path.name)
    return banks, "miss"


# ── One fold × position ─────────────────────────────────────────────────────────────────────────
def run_position(position: str, train: pd.DataFrame, test: pd.DataFrame, weights: np.ndarray, *,
                 draws: int, ctx_te: dict) -> dict:
    """Every arm, foil and anchor for one (fold, position), on ONE shared base-normal stream."""
    tr_p = train.loc[train["position"].astype(str) == position].reset_index(drop=True)
    te_p = test.loc[test["position"].astype(str) == position].reset_index(drop=True)
    if len(te_p) == 0 or len(tr_p) < SA.MIN_ESTIMATION_ROWS:
        return {"skipped": f"train {len(tr_p)} / test {len(te_p)} rows — below the estimation "
                           f"floor ({SA.MIN_ESTIMATION_ROWS}); REFUSED, not defaulted"}

    b_te = bank_tensor(ctx_te, position, len(te_p))
    raw_tr, raw_te = realized_matrix(tr_p), realized_matrix(te_p)
    y_te = FA.score_realized(raw_te, weights)

    # the matched-n capacity control (NF1.9 (f)): the most recent TRAIN rows sized to the test
    # block — same family, same sample size, same marginals
    n_match = max(len(te_p), SA.MIN_ESTIMATION_ROWS)
    m_tr = np.sort(np.argsort(tr_p["gw"].to_numpy(), kind="stable")[-n_match:])
    tr_m = tr_p.iloc[m_tr].reset_index(drop=True)
    raw_m = raw_tr[m_tr]
    if int(SA.activity_indicator(raw_m).sum()) < SA.MIN_ESTIMATION_ROWS:
        return {"skipped": f"the matched-n control carries "
                           f"{int(SA.activity_indicator(raw_m).sum())} ACTIVE {position} rows, "
                           f"below the estimation floor ({SA.MIN_ESTIMATION_ROWS}) — the "
                           f"predecessor's Σ_played foil could not be evaluated at matched n, so "
                           f"this fold is REFUSED rather than scored (NF1.7 (a))"}

    # ── Σ: the ALL-ROWS estimator (the incumbent's) in three contexts, + the predecessor's Σ_played
    sig_all, sig_all_note = SA.sigma_all(raw_tr)
    sig_all_or, _ = SA.sigma_all(raw_te)
    sig_all_mn, _ = SA.sigma_all(raw_m)
    sig_played, sig_played_note = SA.sigma_played(raw_tr)

    banks: dict[str, np.ndarray] = {}
    clamps: dict[str, dict] = {}
    pi_summary: dict[str, dict] = {}
    pi_primary_hat: np.ndarray | None = None
    pi_primary_used: np.ndarray | None = None
    for arm in SA.REAL_ARMS:
        est = SA.PI_ESTIMATOR_OF[arm]
        ctxs = {
            "": (SA.pi_for_arm(est, tr_p, te_p, FEATURES, train_raw=raw_tr), sig_all),
            "oracle__": (SA.pi_for_arm(est, te_p, te_p, FEATURES, train_raw=raw_te), sig_all_or),
            "matched_n__": (SA.pi_for_arm(est, tr_m, te_p, FEATURES, train_raw=raw_m),
                            sig_all_mn),
        }
        for prefix, (pi_hat, sig) in ctxs.items():
            pi_used, note = SA.clamp_pi(pi_hat, b_te)
            banks[f"{prefix}{arm}"] = SA.assemble_mixture_bank(
                b_te, weights, pi=pi_used, corr=sig, draws=draws)
            if not prefix:
                clamps[arm] = note
                if arm == SA.PRIMARY_ARM:
                    pi_primary_hat, pi_primary_used = pi_hat, pi_used
                pi_summary[arm] = {
                    "mean": round(float(pi_hat.mean()), 4), "sd": round(float(pi_hat.std()), 4),
                    "p10": round(float(np.quantile(pi_hat, 0.10)), 4),
                    "p90": round(float(np.quantile(pi_hat, 0.90)), 4),
                }
    if pi_primary_hat is None or pi_primary_used is None:
        raise ValueError(f"{position}: the primary arm `{SA.PRIMARY_ARM}` produced no train-context "
                         f"π — the foils, the permutation anchor and the marginal diagnostic would "
                         f"run against a different fit than the arm they describe")

    # ── The CONTEST foils. `single_copula` is NF-W7c's `joint_rank` (Σ_all, no split) — and the
    # mixture over Σ_all at π ≡ 1 is byte-identical to it, so it is ALSO the matched foil.
    # `mix_played` is NF-W7d's registered primary: the SAME learned π̂ (same estimator, same fit)
    # over Σ_played. `mix_off` (reference) completes the 2×2.
    banks["single_copula"] = FA.assemble_fp_bank(b_te, weights, corr=sig_all, draws=draws)
    pi_played_used, clamp_played = SA.clamp_pi(pi_primary_hat, b_te)
    banks["mix_played"] = SA.assemble_mixture_bank(b_te, weights, pi=pi_played_used,
                                                   corr=sig_played, draws=draws)
    banks["mix_off"] = FA.assemble_fp_bank(b_te, weights, corr=sig_played, draws=draws)
    banks["assembled_indep"] = FA.assemble_fp_bank(b_te, weights, mode="indep", draws=draws)
    banks["assembled_comonotone"] = FA.assemble_fp_bank(b_te, weights, mode="comonotone",
                                                        draws=draws)

    # the π permutation anchor — the primary arm's own π̂ shuffled across players within a global
    # week (same marginal, wrong rows), permuted BEFORE the clamp, over the arm's own Σ_all
    pi_perm, _ = SA.clamp_pi(KW.permute_within_group(pi_primary_hat, te_p["gw"].to_numpy()), b_te)
    banks["pi_permuted"] = SA.assemble_mixture_bank(b_te, weights, pi=pi_perm, corr=sig_all,
                                                    draws=draws)

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

    missing = sorted(set(SA.ALL_LABELS) - set(banks))
    if missing:
        raise ValueError(f"{position}: the declared field is incomplete — {missing} produced no "
                         f"predictive. A field scored with an arm silently missing is not the "
                         f"declared field (NF1.7 (a)).")

    scores: dict[str, float] = {}
    for label, bank in banks.items():
        KW.assert_finite_predictive(bank, f"{position}/{label}")
        scores[label] = float(np.mean(KW.crps_dense(bank, y_te)))
    coverage = {lab: KW.coverage80_dense(banks[lab], y_te) for lab in SA.WATCHED}
    pit = {lab: SA.pit_detail(KW.randomized_pit_from_bank(banks[lab], y_te)) for lab in SA.WATCHED}

    # the marginal-preservation diagnostic on the PRIMARY arm's own clamped π over ITS Σ_all;
    # the reference side is the incumbent's path (`mix_off`-style FA draw at Σ_all)
    drift = SA.mixture_marginal_drift(b_te, pi=pi_primary_used, corr=sig_all)

    # ⭐ THE ATOM-CAP DETAIL, per fold: what the marginals admit, what each arm carries, and the
    # identity that Σ does not enter the installed atom
    zero_mass = {lab: round(float(np.mean(SA.total_zero_mass(banks[lab]))), 4)
                 for lab in (*SA.REAL_ARMS, "mix_played", "single_copula", "mix_off",
                             "assembled_indep", "assembled_comonotone")}
    return {
        "scores": scores, "coverage": coverage, "pit_flatness": pit,
        "n_train": int(len(tr_p)), "n_test": int(len(te_p)),
        "atom_rate_train": round(SA.atom_rate(raw_tr), 4),
        "atom_rate_test": round(SA.atom_rate(raw_te), 4),
        "pi_summary": pi_summary, "clamp": clamps, "clamp_played": clamp_played,
        "marginal_drift": drift,
        "atom_cap": {"cap_mean": round(SA.atom_cap(b_te), 4),
                     "installed_atom_all_rows": clamps[SA.PRIMARY_ARM]["mean_installed_atom"],
                     "installed_atom_played": clamp_played["mean_installed_atom"],
                     "total_zero_mass_by_arm": zero_mass},
        "sigma_all_note": {k: v for k, v in sig_all_note.items() if k != "loadings"},
        "sigma_played_note": {k: v for k, v in sig_played_note.items() if k != "loadings"},
        "mean_abs_offdiag": {
            "all_rows": round(float(np.abs(sig_all[~np.eye(FA.N_LEGS, dtype=bool)]).mean()), 4),
            "active_rows": round(float(np.abs(sig_played[~np.eye(FA.N_LEGS, dtype=bool)]).mean()),
                                 4),
        },
    }


def run_fold(fold: WP.Fold, feat: pd.DataFrame, smap: dict, *, draws: int,
             positions: tuple[str, ...], matrix_key: str, rebuild_banks: bool = False) -> dict:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    cfg = LP.get_preset(GATE_LEAGUE)
    t_m = time.time()
    ctx_te, cache_state = _marginals_cached(fold.label, train, test, smap, matrix_key=matrix_key,
                                            rebuild=rebuild_banks)
    log.info("[W7e] fold %s marginals in %.1fs (test %d rows, cache %s)", fold.label,
             time.time() - t_m, len(test), cache_state)
    out: dict[str, dict] = {}
    for position in positions:
        FA.assert_assembly_is_priceable(cfg, position)
        t_p = time.time()
        out[position] = run_position(position, train, test, FA.leg_weights(cfg, position),
                                     draws=draws, ctx_te=ctx_te)
        log.info("[W7e] fold %s %s in %.1fs", fold.label, position, time.time() - t_p)
    log.info("[W7e] fold %s complete in %.1fs", fold.label, time.time() - t0)
    return {"label": fold.label, "n_test": int(len(test)), "positions": out,
            "bank_cache": cache_state}


# ── Selection (derived from stored fold scores — NF-W2e: zero refit cost) ────────────────────────
_usable = W7D._usable


def _pooled_coverage(usable: list[dict], position: str, label: str) -> dict:
    return W7D._pooled_coverage(usable, position, label)


def _record_scores(relpath: str, story: str, arm: str) -> dict[str, float] | None:
    """A predecessor's recorded per-fold CRPS for one arm, keyed `pos|fold` — a reproduction
    target. None if the record is absent or a path proof (⇒ the control DID NOT RUN)."""
    p = _PROJECT_ROOT / relpath
    if not p.exists():
        return None
    rec = json.loads(p.read_text())
    if rec.get("story") != story or rec.get("smoke"):
        return None
    out: dict[str, float] = {}
    for fr in rec.get("fold_results", []):
        for pos, block in fr.get("positions", {}).items():
            if not block.get("skipped") and arm in block.get("scores", {}):
                out[f"{pos}|{fr['label']}"] = float(block["scores"][arm])
    return out or None


def _incumbent_record_scores() -> dict[str, float] | None:
    return _record_scores(SA.INCUMBENT_RECORD_RELPATH, FA.STORY, SA.INCUMBENT_RECORD_ARM)


def _predecessor_record_scores(foil: str) -> dict[str, float] | None:
    return _record_scores(SA.PREDECESSOR_RECORD_RELPATH, SA.PREDECESSOR,
                          SA.PREDECESSOR_RECORD_ARMS[foil])


def _reproduction(usable: list[dict], position: str, foil: str,
                  record: dict[str, float] | None, who: str) -> dict:
    if not record:
        return {"reproduces": False, "n_folds_compared": 0, "max_abs_gap": None,
                "note": (f"the {who} record is absent or is a path proof — the reproduction "
                         f"control DID NOT RUN, which is never a pass (NF1.7 (a))")}
    return SA.incumbent_reproduction(
        {fr["label"]: fr["positions"][position]["scores"][foil] for fr in usable},
        {k.split("|", 1)[1]: v for k, v in record.items() if k.split("|", 1)[0] == position})


def select_position(fold_results: list[dict], position: str) -> dict | None:
    usable = _usable(fold_results, position)
    if len(usable) < 2:
        return None
    mat = pd.DataFrame({fr["label"]: fr["positions"][position]["scores"] for fr in usable}).T
    mean_s = mat.mean(axis=0)
    # ⭐ RANKED ON CRPS, NEVER ON PIT (SA.SELECTION_IS_CRPS_NOT_PIT — NF-W7d §4, inherited)
    winner = str(mean_s[list(SA.REAL_ARMS)].idxmin())
    best_foil = str(mean_s[list(SA.CONTEST_FOILS)].idxmin())
    deltas = (mat[best_foil] - mat[winner]).to_numpy(float)
    mean_d, lo, hi = KW.paired_ci95(deltas)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(len(usable))
    defl = NF18.deflate(mat[list(SA.ELIGIBLE)], subset=list(SA.ELIGIBLE))
    trial_srs = []
    for arm in SA.REAL_ARMS:
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

    # the materiality yardstick for an oracle inversion is a tenth of the arm's claimed effect
    # over its MATCHED foil — here the incumbent itself
    oracle_states = {a: SA.oracle_floor_state(mat[a], mat[f"oracle__{a}"], mat[f"matched_n__{a}"],
                                              indep_by_fold=mat[SA.INCUMBENT_FOIL])
                     for a in SA.REAL_ARMS}
    oracle_control = {f: SA.oracle_floor_state(mat[f], mat[f"oracle__{f}"], mat[f],
                                               indep_by_fold=mat[SA.INCUMBENT_FOIL])
                      for f in SA.FOILS_WITH_ORACLE}

    atoms = [fr["positions"][position]["clamp"][winner]["mean_installed_atom"] for fr in usable]
    drifts = [fr["positions"][position]["marginal_drift"]["max_probability_drift"] for fr in usable]
    clamp_binding = [fr["positions"][position]["clamp"][winner]["clamp_binding_share"]
                     for fr in usable]
    # ⭐ the identity: the PRIMARY arm's installed atom under Σ_all vs the predecessor foil's
    # under Σ_played — same π̂, same banks, same clamp ⇒ the same float, per fold
    atom_gaps = [abs(fr["positions"][position]["atom_cap"]["installed_atom_all_rows"]
                     - fr["positions"][position]["atom_cap"]["installed_atom_played"])
                 for fr in usable]

    repro_inc = _reproduction(usable, position, SA.INCUMBENT_FOIL, _incumbent_record_scores(),
                              FA.STORY)
    repro_pred = {f: _reproduction(usable, position, f, _predecessor_record_scores(f),
                                   SA.PREDECESSOR) for f in SA.PREDECESSOR_RECORD_ARMS}

    pooled_cov = {lab: _pooled_coverage(usable, position, lab)
                  for lab in (*SA.REAL_ARMS, *SA.FOILS, "assembled_comonotone")}
    cov_w, cov_i = pooled_cov[winner], pooled_cov["assembled_indep"]
    cov_c = pooled_cov["assembled_comonotone"]

    def _pit_mean(label: str) -> float:
        return float(np.mean([fr["positions"][position]["pit_flatness"][label]["max_decile_dev"]
                              for fr in usable]))

    pit_by_label = {lab: round(_pit_mean(lab), 4) for lab in SA.WATCHED}
    pit_w = _pit_mean(winner)
    pooled = SA.pooled_pit([fr["positions"][position]["pit_flatness"][winner]["decile_counts"]
                            for fr in usable])
    n_per_fold = int(np.mean([fr["positions"][position]["n_test"] for fr in usable]))
    pit_null = SA.pit_null_reference(n_per_fold)

    anchors = {
        "degenerates_lose": bool(all(mean_s[d] > mean_s[winner] for d in SA.DEGENERATES)),
        "degenerate_detail": {d: round(float(mean_s[d]), 4) for d in SA.DEGENERATES},
        "winner_beats_permuted": bool(mean_s["permuted_direct"] > mean_s[winner]),
        "permuted_lift_not_significant": bool(
            float(np.nanmean(perm_lift)) <= 0 or (p_perm is not None and p_perm >= 0.05)),
        "winner_beats_pi_permuted": bool(mean_s["pi_permuted"] > mean_s[winner]),
        "oracle_floors_respected_at_matched_n": bool(all(
            oracle_states[a]["state"] != SA.ORACLE_VIOLATED for a in SA.REAL_ARMS)),
        "oracle_ceiling_evaluated": bool(
            any(oracle_states[a]["state"] == SA.ORACLE_RESPECTED for a in SA.REAL_ARMS)),
        "winner_oracle_state": oracle_states[winner]["state"],
        "foils_respect_own_oracle": bool(all(
            mean_s[f] > mean_s[f"oracle__{f}"] for f in SA.FOILS_WITH_ORACLE)),
        "mixture_is_active": bool(float(np.mean(atoms)) >= SA.MIN_MIXTURE_ATOM),
        "mixture_preserves_marginals": bool(max(drifts) <= SA.MAX_MARGINAL_DRIFT),
        "incumbent_reproduces": bool(repro_inc["reproduces"]),
        "predecessor_reproduces": bool(all(r["reproduces"] for r in repro_pred.values())),
        "atom_is_sigma_invariant": bool(max(atom_gaps) <= SA.ATOM_INVARIANCE_TOLERANCE),
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
    return {
        "position": position, "winner": winner, "best_foil": best_foil,
        "gated": position in SA.GATE_POSITIONS, "n_folds_used": len(usable),
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
        "pit_flatness_winner_max_decile_dev": round(pit_w, 4),
        "pit_flat_ok": bool(pit_w <= SA.PIT_MAX_DECILE_DEV),
        "pit_by_label": pit_by_label,
        "pit_pooled_rows": pooled,
        "pit_calibrated_null": pit_null,
        "pit_null_p_value": SA.pit_null_pvalue(pit_w, n_per_fold),
        "pit_winner_decile_freq": [
            round(float(v), 4) for v in np.mean(
                [fr["positions"][position]["pit_flatness"][winner]["decile_freq"]
                 for fr in usable], axis=0)],
        "mixture_detail": {
            "mean_installed_atom": round(float(np.mean(atoms)), 4),
            "atom_by_fold": [round(float(a), 4) for a in atoms],
            "mean_clamp_binding_share": round(float(np.mean(clamp_binding)), 4),
            "max_marginal_drift": round(float(max(drifts)), 5),
            "tolerance": SA.MAX_MARGINAL_DRIFT, "atom_floor": SA.MIN_MIXTURE_ATOM,
            "observed_atom_rate_test": round(float(np.mean(
                [fr["positions"][position]["atom_rate_test"] for fr in usable])), 4),
            "pi_summary_last_fold": usable[-1]["positions"][position]["pi_summary"],
        },
        "incumbent_reproduction": repro_inc,
        "predecessor_reproduction": repro_pred,
        # ⭐ the atom cap, pooled over folds — the inputs the confirmation rule reads
        "atom_cap_detail": {
            "cap_mean": round(float(np.mean(
                [fr["positions"][position]["atom_cap"]["cap_mean"] for fr in usable])), 4),
            "installed_atom_all_rows": round(float(np.mean(
                [fr["positions"][position]["atom_cap"]["installed_atom_all_rows"]
                 for fr in usable])), 6),
            "installed_atom_played": round(float(np.mean(
                [fr["positions"][position]["atom_cap"]["installed_atom_played"]
                 for fr in usable])), 6),
            "max_atom_gap_by_fold": round(float(max(atom_gaps)), 12),
            "total_zero_mass_by_arm": zero_mass,
        },
        # ── attribution: the FULL 2×2 (split on/off × Σ_all/Σ_played) ────────────────────────
        "attribution": {
            # THE CLAIM: the split over the all-rows Σ, vs the incumbent (its own matched foil)
            "split_over_sigma_all": round(float(mean_s["single_copula"] - mean_s[winner]), 4),
            # the Σ population WITH the split on (this arm vs NF-W7d's registered arm)
            "sigma_population_with_split": round(float(mean_s["mix_played"] - mean_s[winner]), 4),
            # NF-W7d's two numbers, re-scored on the same common random numbers
            "split_over_sigma_played": round(float(mean_s["mix_off"] - mean_s["mix_played"]), 4),
            "sigma_population_without_split": round(
                float(mean_s["single_copula"] - mean_s["mix_off"]), 4),
            "delta_vs_indep": round(float(mean_s["assembled_indep"] - mean_s[winner]), 4),
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
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < SA.PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= SA.DSR_MIN,
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
        "predecessor_reproduces": bool(sel["anchors"]["predecessor_reproduces"]),
        "atom_is_sigma_invariant": bool(sel["anchors"]["atom_is_sigma_invariant"]),
        **{k: bool(v) for k, v in sel["dependence_checks"].items()},
    }
    return {"checks": checks, "ship": all(checks.values())}


def classify(sel: dict, checks: dict) -> dict:
    v = cv_power.classify_null(
        metric=f"nf_w7e_split_allrows|{sel['position']}", n_folds=sel["n_folds_used"],
        n_arms=len(SA.REAL_ARMS), beats_foil=sel["beats_foil"],
        observed_sr=sel["observed_sr"], var_trials_sr=sel["var_trials_sr"],
        fold_wins=sel["fold_wins"], p_one_sided=sel["p_one_sided"], bh_cutoff=SA.FDR_Q,
        degenerates_excluded_from_v=True,
        declared_field_size=len(SA.REAL_ARMS),
    )
    base = KW.flag_unsafe_field_shrink(
        {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger,
         "field_remedy_admissible": getattr(v, "field_remedy_admissible", None),
         "declared_field_size_source": ("fp_availability_split_allrows.REAL_ARMS, committed in "
                                        "ablation_results/nf_w7e_preregistration.md §3 before "
                                        "any score"),
         "instrument_verdict": {"state": v.state, "reason": v.reason,
                                "retest_trigger": v.retest_trigger}},
        len(SA.REAL_ARMS))
    out = KW.coverage_constraint_refusal(sel, checks, base, mechanism=SA.REFUSAL_MECHANISM,
                                         remedy=SA.REFUSAL_REMEDY)
    if out is base:
        stat_fail = [c for c in SA.STATISTICAL_CHECKS if not checks.get(c, True)]
        anchor_fail = [c for c in SA.ANCHOR_CHECKS if not checks.get(c, True)]
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
                    f"{SA.PIT_MAX_DECILE_DEV}. A max-decile deviation against a FIXED bar is a "
                    f"deterministic constraint, not a sampling shortfall — more folds shrink "
                    f"nothing that would move it" + SA.REFUSAL_MECHANISM),
                "retest_trigger": SA.REFUSAL_REMEDY, "failing_statistical_checks": stat_fail,
            })
    out["pbo_state"] = (
        f"EVALUABLE — PBO over the {len(SA.ELIGIBLE)}-config eligible field "
        f"({len(SA.REAL_ARMS)} mixture arms + {len(SA.CONTEST_FOILS)} contest foils); DSR deflates "
        f"over the {len(SA.REAL_ARMS)}-arm declared family (trial SRs from real arms only — "
        f"anchors, degenerates and the three REFERENCE foils never enter V; MH2.1 (a) / DSR-CONV).")
    out["gate_sensitivity"] = KW.gate_sensitivity(checks, waived=())
    return out


def atom_cap_layer(selections: dict) -> dict:
    """The ATOM-CAP confirmation, read on QB by the pre-registered rule."""
    sel = selections.get(SA.ATOM_CAP_POSITION)
    if sel is None:
        return SA.atom_cap_verdict(pit_by_arm={}, atom_all_rows=float("nan"),
                                  atom_played=float("nan"), atom_cap_mean=float("nan"),
                                  realized_atom=float("nan"), total_zero_mass_by_arm={},
                                  pit_predecessor=None)
    d = sel["atom_cap_detail"]
    return SA.atom_cap_verdict(
        pit_by_arm={a: sel["pit_by_label"][a] for a in SA.REAL_ARMS},
        atom_all_rows=d["installed_atom_all_rows"], atom_played=d["installed_atom_played"],
        atom_cap_mean=d["cap_mean"],
        realized_atom=sel["mixture_detail"]["observed_atom_rate_test"],
        total_zero_mass_by_arm=d["total_zero_mass_by_arm"],
        pit_predecessor=sel["pit_by_label"].get(SA.PREDECESSOR_FOIL),
        tolerance=SA.ATOM_INVARIANCE_TOLERANCE)


def derive_verdict_layer(out: dict) -> dict:
    """⭐ Every decision re-derivable from the stored fold scores — no refit (NF-W2e / NF-W3)."""
    frs = out["fold_results"]
    scored = [p for p in SA.POSITIONS if _usable(frs, p)]
    sels = {p: select_position(frs, p) for p in scored}
    present = {p: s for p, s in sels.items() if s is not None}
    # ⭐ FOUR GATED HYPOTHESES — every position may ship, so the BH family carries all four
    gated = {p: s for p, s in present.items() if p in SA.GATE_POSITIONS}
    fdr = M14.bh_fdr({f"fp|{p}": s["p_one_sided"] for p, s in gated.items()}, q=SA.FDR_Q)
    gates = {p: compose_gate(s, fdr.get(f"fp|{p}", False)) for p, s in gated.items()}
    nulls = {p: (None if gates[p]["ship"] else classify(gated[p], gates[p]["checks"]))
             for p in gated}
    ship = sorted(p for p in gated if gates[p]["ship"])
    out["selections"] = present
    attempted = sorted({p for fr in frs for p in fr["positions"]})
    out["unavailable_positions"] = sorted(set(attempted) - set(present))
    out["positions_not_run"] = sorted(set(SA.POSITIONS) - set(attempted))
    out["fdr"] = fdr
    out["gates"] = gates
    out["null_states"] = {p: n for p, n in nulls.items() if n}
    out["atom_cap"] = atom_cap_layer(present)
    out["verdict"] = {
        "story_verdict": "SHIP" if ship else "NULL",
        "gate_positions": list(SA.GATE_POSITIONS),
        "ship_positions": ship,
        "null_positions": {p: nulls[p]["state"] for p in gated if nulls[p]},
        "gate_league": GATE_LEAGUE,
        "declared_field_size": len(SA.REAL_ARMS),
        "selection_key": SA.SELECTION_IS_CRPS_NOT_PIT,
        "atom_cap_state": out["atom_cap"]["state"],
        "promote_blockers": list(SA.PROMOTE_BLOCKERS),
        "positions_with_unevaluated_oracle_ceiling": sorted(
            p for p, s in present.items() if not s["anchors"]["oracle_ceiling_evaluated"]),
        "winner_oracle_state": {p: s["anchors"]["winner_oracle_state"]
                                for p, s in present.items()},
    }
    return out


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:
    v = out["verdict"]
    cap = out["atom_cap"]
    L = [f"# NF-W7e — the availability split over the ALL-ROWS Σ ({v['story_verdict']})", "",
         f"Generated {out['generated_at']} · gate positions **{', '.join(v['gate_positions'])}** · "
         f"gate league **{GATE_LEAGUE}** · {out['n_folds']} folds · target `{FA.TARGET}` · "
         f"ranked on `{FA.SELECTION_METRIC}` · gated on `{SA.GATE_STATISTIC}`", "",
         "⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record "
         "promotes nothing and publishes nothing.", "",
         "## Verdict", "",
         f"- ship positions: **{v['ship_positions'] or 'none'}**",
         f"- null positions: {v['null_positions'] or 'none'}",
         f"- ⭐ atom-cap confirmation (QB): **{cap['state']}** — {cap['reading']}",
         f"- scored but unusable: {out['unavailable_positions'] or 'none'}",
         f"- not run in this invocation: {out.get('positions_not_run') or 'none'}", "",
         f"⭐ **Selection key.** {v['selection_key']}", ""]

    L += ["## Per position", "",
          "| pos | winner | best contest foil | Δ CRPS vs foil | CI95 | folds | **PIT dev** | "
          "bar | cov80 | PBO | DSR | gate |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for p, s in out["selections"].items():
        g = out["gates"].get(p)
        ci = s["ci95"]
        L.append(
            f"| {p} | `{s['winner']}` | `{s['best_foil']}` | {s['mean_delta']:+.4f} | "
            f"[{ci[0]}, {ci[1]}] | {s['fold_wins']}/{s['n_folds_used']} | "
            f"**{s['pit_flatness_winner_max_decile_dev']}** | {SA.PIT_MAX_DECILE_DEV} | "
            f"{s['coverage']['winner_coverage_80']} | {s['pbo']} | {s['dsr']} | "
            f"{'SHIP' if g and g['ship'] else ('NULL' if g else '—')} |")

    L += ["", "## ⭐ The 2×2 — split {on, off} × Σ {all rows, active rows}, per position", "",
          "NF-W7d measured two of these cells and could not measure the third. Every cell is scored "
          "here on common random numbers against the reproduced incumbent. `single_copula` is the "
          "incumbent AND the matched foil (the mixture over Σ_all at π ≡ 1 is byte-identical to "
          "it); `mix_played` is NF-W7d's registered primary; `mix_off` completes the square.", "",
          "| pos | **split over Σ_all** (THE CLAIM: `single_copula` − winner) | Σ population WITH "
          "the split (`mix_played` − winner) | split over Σ_played (`mix_off` − `mix_played`, "
          "NF-W7d) | Σ population WITHOUT the split (`single_copula` − `mix_off`, NF-W7d) | "
          "Δ vs indep | Δ vs direct points (report-only) |",
          "|---|---|---|---|---|---|---|"]
    for p, s in out["selections"].items():
        a = s["attribution"]
        L.append(f"| {p} | **{a['split_over_sigma_all']:+.4f}** | "
                 f"{a['sigma_population_with_split']:+.4f} | {a['split_over_sigma_played']:+.4f} | "
                 f"{a['sigma_population_without_split']:+.4f} | {a['delta_vs_indep']:+.4f} | "
                 f"{a['delta_vs_direct_points_REPORT_ONLY']:+.4f} |")
    L += ["", "⚠️ **The last column never gates** (NF-W7c §11.4 — an ARCHITECTURE question, not "
          "this story's).", ""]

    L += ["", "## ⭐ The atom-cap confirmation", "",
          f"**State: `{cap['state']}`** — {cap['reading']}", "",
          "| identity holds | installed atom (Σ_all) | installed atom (Σ_played) | atom CAP "
          "(what the marginals admit) | realized all-zero rate | shortfall (realized − cap) | "
          "PIT (`mix_played`, NF-W7d) | best PIT here | moved by Σ_all | bar |",
          "|---|---|---|---|---|---|---|---|---|---|",
          f"| {cap['atom_identity_holds']} | {cap['installed_atom_all_rows_sigma']} | "
          f"{cap['installed_atom_played_sigma']} | {cap['atom_cap_mean']} | "
          f"{cap['realized_all_zero_rate']} | {cap['atom_shortfall_cap_vs_realized']} | "
          f"{cap['pit_predecessor_played_sigma']} | {cap['best_pit']} (`{cap['best_pit_arm']}`) | "
          f"{cap['pit_moved_by_sigma_all']} | {cap['bar']} |", "",
          "Total zero mass the ASSEMBLED predictive actually carries at QB, per construction "
          "(vs a realized all-zero rate of "
          f"{cap['realized_all_zero_rate']}): "
          + ", ".join(f"`{k}` {v}" for k, v in cap["total_zero_mass_by_arm"].items()), ""]

    L += ["", "## The gate statistic — randomized-PIT decile flatness (gates, never ranks)", "",
          "| pos | winner PIT (per-fold mean, BINDS) | pooled over rows | perfect-calibration "
          "median at this n | P(this rough \\| calibrated) | worst decile |",
          "|---|---|---|---|---|---|"]
    for p, s in out["selections"].items():
        pooled, null = s["pit_pooled_rows"], s["pit_calibrated_null"]
        L.append(f"| {p} | {s['pit_flatness_winner_max_decile_dev']} | "
                 f"{pooled['max_decile_dev']} (n={pooled['n']}) | {null['median']} "
                 f"(n={null['n']}) | {s['pit_null_p_value']} | {pooled['worst_decile']} |")
    L += ["", "| pos | " + " | ".join(f"`{k}`" for k in SA.WATCHED) + " |",
          "|---" * (1 + len(SA.WATCHED)) + "|"]
    for p, s in out["selections"].items():
        L.append(f"| {p} | " + " | ".join(str(s["pit_by_label"][k]) for k in SA.WATCHED) + " |")
    L += ["", "| pos | winner decile vector (low → high) |", "|---|---|"]
    for p, s in out["selections"].items():
        L.append(f"| {p} | {s['pit_winner_decile_freq']} |")

    L += ["", "## Could the mechanism act? (measured before it is credited)", "",
          "| pos | mean installed atom | observed all-zero rate | clamp binding share | "
          "max marginal drift | tolerance | active? | marginals preserved? |",
          "|---|---|---|---|---|---|---|---|"]
    for p, s in out["selections"].items():
        m, a = s["mixture_detail"], s["anchors"]
        L.append(f"| {p} | {m['mean_installed_atom']} | {m['observed_atom_rate_test']} | "
                 f"{m['mean_clamp_binding_share']} | {m['max_marginal_drift']} | "
                 f"{m['tolerance']} | {a['mixture_is_active']} | "
                 f"{a['mixture_preserves_marginals']} |")

    L += ["", "## ⭐ The reproduction identity proofs", "",
          "`single_copula` must reproduce NF-W7c's recorded `joint_rank`; `mix_off` and "
          "`mix_played` must reproduce NF-W7d's `mix_off` and `mix_learned` — per fold, to 1e-9. "
          "Every comparison here is against those foils; a drifted harness would still produce a "
          "plausible contest.", "",
          "| pos | vs NF-W7c (`single_copula`) folds / max gap / ok | vs NF-W7d (`mix_off`) | "
          "vs NF-W7d (`mix_played`) |", "|---|---|---|---|"]
    for p, s in out["selections"].items():
        r = s["incumbent_reproduction"]
        pr = s["predecessor_reproduction"]
        L.append(f"| {p} | {r['n_folds_compared']} / {r.get('max_abs_gap')} / {r['reproduces']} | "
                 f"{pr['mix_off']['n_folds_compared']} / {pr['mix_off'].get('max_abs_gap')} / "
                 f"{pr['mix_off']['reproduces']} | "
                 f"{pr['mix_played']['n_folds_compared']} / "
                 f"{pr['mix_played'].get('max_abs_gap')} / {pr['mix_played']['reproduces']} |")

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
                     f"{o['peek_gain_vs_arm']}")

    L += ["", "## The mechanism, re-measured per fold", "",
          "| pos | all-zero rate (test) | ρ̄ ratio by fold (all rows ÷ active rows) |",
          "|---|---|---|"]
    for p, s in out["selections"].items():
        L.append(f"| {p} | {s['mixture_detail']['observed_atom_rate_test']} | "
                 f"{s['availability_ratio_by_fold']} |")

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
    path.write_text("\n".join(L))


# ── Orchestration ───────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-W7e — the availability split over the all-rows "
                                             "Σ + the atom-cap confirmation (§0.5)")
    ap.add_argument("--smoke", action="store_true",
                    help="path proof: 1 fold, QB only, few draws (artifact _smoke)")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="re-derive every verdict from the stored fold scores (zero refit)")
    ap.add_argument("--rebuild-cache", action="store_true", help="rebuild the W6d matrix cache")
    ap.add_argument("--rebuild-banks", action="store_true",
                    help="ignore the per-fold marginal-bank cache and refit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # cosmetic: the NF-W6d serving dispatch predicts through a numpy view of a frame the learner
    # was fitted on with column names; sklearn warns once per predict call (~hundreds per fold)
    # and drowns the run log. Behaviour is unchanged (added after the decisive run; nothing scored
    # depends on it).
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    suffix = "_smoke" if args.smoke else ""
    art = _PROJECT_ROOT / _ARTIFACT_REL.replace(".json", f"{suffix}.json")

    if args.rewrite_report:
        out = derive_verdict_layer(json.loads(art.read_text()))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat()
        art.write_text(json.dumps(out, indent=2, default=str))
        write_report(out, art.with_suffix(".md"))
        log.info("NF-W7e report re-derived → %s", art.name)
        return 0

    FA.assert_stat_key_map()
    feat, pit_audit, attach = W6DA.build_matrix_w6d(SEASONS, rebuild_cache=args.rebuild_cache)
    gate_p, bake_p, def_p = W6DS.record_paths("")          # ALWAYS the FULL W6d records
    smap = SDSD.served_map(gate_p, bake_p, def_p)
    folds = WP.build_folds(feat)
    positions: tuple[str, ...] = (SA.ATOM_CAP_POSITION,) if args.smoke else SA.POSITIONS
    if args.smoke:
        folds = folds[-1:]
    draws = 300 if args.smoke else SA.ASSEMBLY_DRAWS
    matrix_key = W6DA.w6d_matrix_key(SEASONS)
    log.info("NF-W7e: %d folds × %d positions, %d legs, %d draws%s", len(folds), len(positions),
             SA.N_LEGS, draws, " [SMOKE]" if args.smoke else "")

    t0 = time.time()
    fold_results = [run_fold(f, feat, smap, draws=draws, positions=positions,
                             matrix_key=matrix_key, rebuild_banks=args.rebuild_banks)
                    for f in folds]
    out = {
        "story": SA.STORY, "phase": "split_over_all_rows_sigma", "smoke": bool(args.smoke),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seasons": list(SEASONS), "n_folds": len(folds), "gate_league": GATE_LEAGUE,
        "gate_positions": list(SA.GATE_POSITIONS),
        "matrix_key": matrix_key, "pit_audit": pit_audit,
        "attach_audit": attach, "served_map_sources": {c: v["source"] for c, v in smap.items()},
        "assembly_draws": draws, "row_block": SA.ROW_BLOCK, "seed": SA._SEED,
        "seed_inherited_from": f"{FA.STORY} via {SA.PREDECESSOR}",
        "avail_stream_offset": SA.AVAIL_STREAM_OFFSET,
        "declared_field": {"real_arms": list(SA.REAL_ARMS),
                           "contest_foils": list(SA.CONTEST_FOILS),
                           "reference_foils": list(SA.REFERENCE_FOILS),
                           "degenerates": list(SA.DEGENERATES), "anchors": list(SA.ANCHORS)},
        "labelling": {p: FA.assembled_labelling(smap, LP.get_preset(GATE_LEAGUE), p)
                      for p in positions},
        "fold_results": fold_results, "runtime_seconds": round(time.time() - t0, 1),
    }
    out = derive_verdict_layer(out)
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(json.dumps(out, indent=2, default=str))
    write_report(out, art.with_suffix(".md"))
    log.info("NF-W7e %s (atom cap: %s) → %s (%.1fs)", out["verdict"]["story_verdict"],
             out["atom_cap"]["state"], art.name, out["runtime_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
