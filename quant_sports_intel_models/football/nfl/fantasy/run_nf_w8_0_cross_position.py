"""run_nf_w8_0_cross_position.py — NF-W8-0 §0.5: the cross-position comparability layer for the
weekly optimizer input, plus the registered-forward QB consumption decision (Option B).

Everything decidable in advance is a CONSTANT in `fp_cross_position.py`; this runner READS it
(NF-D16). The narrative pre-registration is committed at
`ablation_results/nf_w8_0_preregistration.md` BEFORE any scoring run.

PIPELINE (target `league_fantasy_points`, gate league `full_ppr`, NF-W7c's 8-fold axis verbatim):
  · per fold × position: the PINNED consumed generator (QB `zm_floor` · RB `direct_points` ·
    WR `mixall_learned` · TE `single_copula` — each BY IDENTITY of its certifying story's code
    path, same seed, same Σ/π̂ estimators) + the swap ALTERNATIVE, both scored on the identical
    test rows; the consumed generator's per-fold CRPS must reproduce its record pin at 1e-9;
  · per-row (point, y) OOF rows are written to a fold parquet (`artifacts/nf_w8_0_rows*/`) — the
    derive layer fits every recalibration on PRIOR folds' rows only (fold 1 = identity by
    construction) and re-derives every verdict from stored rows at zero refit cost;
  · family A: the 6 pairwise per-fold-paired position bias contrasts, BH q=0.10 → `gap_detected`;
  · family B: {identity, level_add, level_affine} + anchors (zero_point / position_mean_point /
    level_add_permuted / level_add_oracle) on the per-fold cross-position bias RANGE, with
    do-no-harm RMSE, PBO/DSR over the eligible field, and the §6 generator-swap clause;
  · the verdict via `XP.comparability_verdict` (four pre-registered states), then the 4-position
    VOR-ranked input parquet (`artifacts/nf_w8_0_input*/`) under the shipped arm.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: writes LOCAL artifacts only — no
`--publish`, no S3 client, no boto3, no dbt, no Dagster.

RUN (OPERATOR — LAPTOP; reads the S3 NFL lake read-only, writes local artifacts):

    # path proof: 1 fold, all four positions, few draws (artifact _smoke) — no verdict
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w8_0_cross_position --smoke

    # the decisive run (>2 min — OPERATOR; dominated by the W6d marginal dispatch per fold)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w8_0_cross_position

    # re-derive every verdict from the stored fold rows at ZERO refit cost (NF-W2e / NF-W3)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w8_0_cross_position --rewrite-report

⭐ Per-fold MARGINAL BANKS are cached under `artifacts/nf_w7e_bank_cache/` — deliberately NF-W7e's
own cache directory and key scheme (matrix key + fold + served-map hash; shape/cell-refused on
mismatch), so a machine already holding the W7e/W7f cache pays only for draws + LGBM fits.
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
from quant_sports_intel_models.fantasy_engine import vor as FVOR  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    fp_availability_split_allrows as SA,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    fp_cross_position as XP,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    fp_qb_marginal_calibration as QM,
)
from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE  # noqa: E402
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
    run_nf_w7e_split_allrows as W7E,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    stat_distribution_serving_d as SDSD,
)
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_w8_0")

SEASONS = W6DA.SEASONS
FEATURES = list(WP.FEATURES)
GATE_LEAGUE = W7C.GATE_LEAGUE                      # ⛔ inherited (E2.1-r)

_ARTIFACT_REL = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                 "nf_w8_0_cross_position.json")
_ROWS_DIR = Path(__file__).resolve().parent / "artifacts" / "nf_w8_0_rows"
_INPUT_DIR = Path(__file__).resolve().parent / "artifacts" / "nf_w8_0_input"

#: consumed / swap generator → the bank label built in `build_position_banks`
CONSUMED_BANK_LABEL: dict[str, str] = {"QB": "zm_floor", "RB": "direct_points",
                                       "WR": "mixall_learned", "TE": "single_copula"}
SWAP_BANK_LABEL: dict[str, str] = dict(XP.SWAP_GENERATOR_OF)
#: NF-W7c's per-position assembly labelling carries NF-W6d calibrated DEFAULTS among priced legs
#: for the three assembled positions; RB's direct-points learner carries none (a single learner
#: on the total, no per-stat defaults). Prereg §7's `calibration_warning` column.
CALIBRATION_WARNING_OF: dict[str, bool] = {"QB": True, "RB": False, "WR": True, "TE": True}
#: the bank quantile columns carried into the input (indices on the 199-level grid)
_QIDX = {q: int(np.searchsorted(np.round(FA.EVAL_LEVELS, 6), q)) for q in (0.10, 0.50, 0.90)}

# the marginal-bank cache is NF-W7e's, by identity (same key scheme, same refusal logic)
_marginals_cached = W7E._marginals_cached


# ── One fold × position: the pinned generators on the shared test rows ──────────────────────────
def build_position_banks(position: str, tr_p: pd.DataFrame, te_p: pd.DataFrame,
                         weights: np.ndarray, *, draws: int, b_te: np.ndarray,
                         raw_tr: np.ndarray, y_te: np.ndarray) -> dict[str, np.ndarray]:
    """The consumed + swap constructions for one (fold, position), each BY IDENTITY of its
    certifying story's code path (one code path — NF-W7d's RED-proof lesson)."""
    sig_all, _ = SA.sigma_all(raw_tr)
    banks: dict[str, np.ndarray] = {}

    trc, tec = tr_p.copy(), te_p.copy()
    trc[FA.TARGET] = FA.score_realized(raw_tr, weights)
    tec[FA.TARGET] = y_te
    banks["direct_points"] = KW.fit_direct_points(trc, tec, FEATURES, FA.TARGET)

    if position in ("TE", "RB"):
        banks["single_copula"] = FA.assemble_fp_bank(b_te, weights, corr=sig_all, draws=draws)
    if position == "WR":
        pi_hat = SA.pi_for_arm(SA.PI_ESTIMATOR_OF[SA.PRIMARY_ARM], tr_p, te_p, FEATURES,
                               train_raw=raw_tr)
        pi_used, _note = SA.clamp_pi(pi_hat, b_te)
        banks["mixall_learned"] = SA.assemble_mixture_bank(b_te, weights, pi=pi_used,
                                                           corr=sig_all, draws=draws)
    if position == "QB":
        pi_hat = QM.pi_for_arm(QM.PI_ESTIMATOR, tr_p, te_p, FEATURES, train_raw=raw_tr)
        t = QM.zero_targets("zm_floor", banks=b_te, pi_hat=pi_hat,
                            cond_rate=QM.conditional_zero_rate(raw_tr),
                            marg_rate=QM.marginal_zero_rate(raw_tr))
        recal = QM.resplice_zero_mass(b_te, t)
        pi_used, _note = QM.clamp_pi(pi_hat, recal)
        banks["zm_floor"] = QM.assemble_mixture_bank(recal, weights, pi=pi_used,
                                                     corr=sig_all, draws=draws)
    return banks


def run_position(position: str, train: pd.DataFrame, test: pd.DataFrame, weights: np.ndarray, *,
                 draws: int, ctx_te: dict) -> tuple[dict, pd.DataFrame | None]:
    """One (fold, position): the pinned generators, their CRPS (for the reproduction pins), the
    ranking points, and the per-row frame the derive layer fits recalibrations on."""
    tr_p = train.loc[train["position"].astype(str) == position].reset_index(drop=True)
    te_p = test.loc[test["position"].astype(str) == position].reset_index(drop=True)
    if len(te_p) == 0 or len(tr_p) < FA.MIN_ESTIMATION_ROWS:
        return ({"skipped": f"train {len(tr_p)} / test {len(te_p)} rows — below the estimation "
                            f"floor ({FA.MIN_ESTIMATION_ROWS}); REFUSED, not defaulted"}, None)
    raw_tr, raw_te = W7C.realized_matrix(tr_p), W7C.realized_matrix(te_p)
    if position == "QB" and int(QM.activity_indicator(raw_tr).sum()) < QM.MIN_ESTIMATION_ROWS:
        return ({"skipped": f"QB train carries {int(QM.activity_indicator(raw_tr).sum())} ACTIVE "
                            f"rows, below the floor ({QM.MIN_ESTIMATION_ROWS}) — the zm_floor "
                            f"conditional zero rate could not be estimated; REFUSED (NF1.7 (a))"},
                None)
    y_te = FA.score_realized(raw_te, weights)
    b_te = W7C.bank_tensor(ctx_te, position, len(te_p))

    banks = build_position_banks(position, tr_p, te_p, weights, draws=draws, b_te=b_te,
                                 raw_tr=raw_tr, y_te=y_te)
    consumed, swap = CONSUMED_BANK_LABEL[position], SWAP_BANK_LABEL[position]
    missing = {consumed, swap} - set(banks)
    if missing:
        raise ValueError(f"{position}: pinned constructions missing {sorted(missing)} — a field "
                         f"scored with a generator silently absent is not the declared field "
                         f"(NF1.7 (a))")

    scores: dict[str, float] = {}
    for label, bank in banks.items():
        KW.assert_finite_predictive(bank, f"{position}/{label}")
        scores[label] = float(np.mean(KW.crps_dense(bank, y_te)))

    bank_c = np.sort(np.asarray(banks[consumed], float), axis=1)
    rows = pd.DataFrame({
        "season": te_p["season"].to_numpy(), "week": te_p["week"].to_numpy(),
        "gw": te_p["gw"].to_numpy(), "gsis_id": te_p["gsis_id"].astype(str).to_numpy(),
        "position": position, "y": y_te,
        "point_consumed": XP.bank_point(banks[consumed]),
        "point_swap": XP.bank_point(banks[swap]),
        "p10": bank_c[:, _QIDX[0.10]], "p50": bank_c[:, _QIDX[0.50]],
        "p90": bank_c[:, _QIDX[0.90]],
    })
    summary = {
        # ⛔ FULL PRECISION — the reproduction pins compare these against the predecessor
        # records at 1e-9; a round(…, 6) here caps every pin at ~5e-7 and the decisive run
        # returns UNDEFINED at all four positions (caught by the smoke: RB's draw-independent
        # construction reproduced to 4.15e-7 = exactly the rounding, not a real gap)
        "scores": {k: float(v) for k, v in scores.items()},
        "consumed": consumed, "swap": swap,
        "n_train": int(len(tr_p)), "n_test": int(len(te_p)),
        "bias_identity": XP.bias_detail(rows["point_consumed"].to_numpy(), y_te),
        "bias_swap": XP.bias_detail(rows["point_swap"].to_numpy(), y_te),
        "calibration_slope": XP.calibration_slope(rows["point_consumed"].to_numpy(), y_te),
    }
    return summary, rows


def run_fold(fold: WP.Fold, feat: pd.DataFrame, smap: dict, *, draws: int, matrix_key: str,
             rows_dir: Path, rebuild_banks: bool = False) -> dict:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    cfg = LP.get_preset(GATE_LEAGUE)
    ctx_te, cache_state = _marginals_cached(fold.label, train, test, smap, matrix_key=matrix_key,
                                            rebuild=rebuild_banks)
    out: dict[str, dict] = {}
    fold_rows: list[pd.DataFrame] = []
    for position in XP.POSITIONS:
        FA.assert_assembly_is_priceable(cfg, position)
        t_p = time.time()
        summary, rows = run_position(position, train, test, FA.leg_weights(cfg, position),
                                     draws=draws, ctx_te=ctx_te)
        out[position] = summary
        if rows is not None:
            fold_rows.append(rows)
        log.info("[W8-0] fold %s %s in %.1fs", fold.label, position, time.time() - t_p)
    rows_dir.mkdir(parents=True, exist_ok=True)
    rows_path = rows_dir / f"{fold.label}.parquet"
    if fold_rows:
        pd.concat(fold_rows, ignore_index=True).to_parquet(rows_path, index=False)
    log.info("[W8-0] fold %s complete in %.1fs (bank cache %s)", fold.label, time.time() - t0,
             cache_state)
    return {"label": fold.label, "n_test": int(len(test)), "positions": out,
            "bank_cache": cache_state, "rows_path": str(rows_path)}


# ── Reproduction pins ───────────────────────────────────────────────────────────────────────────
def _generator_record_scores(position: str) -> dict[str, float] | None:
    """The certifying record's per-fold CRPS for this position's consumed generator — the
    reproduction target. None if the record is absent or a path proof (⇒ DID NOT RUN)."""
    relpath, story, arm = XP.GENERATOR_RECORD_PINS[position]
    p = _PROJECT_ROOT / relpath
    if not p.exists():
        return None
    rec = json.loads(p.read_text())
    if rec.get("story") != story or rec.get("smoke"):
        return None
    out: dict[str, float] = {}
    for fr in rec.get("fold_results", []):
        block = fr.get("positions", {}).get(position)
        if block and not block.get("skipped") and arm in block.get("scores", {}):
            out[fr["label"]] = float(block["scores"][arm])
    return out or None


def _reproduction(fold_results: list[dict], position: str) -> dict:
    record = _generator_record_scores(position)
    usable = [fr for fr in fold_results
              if not fr["positions"].get(position, {}).get("skipped")]
    if not record:
        return {"reproduces": False, "n_folds_compared": 0, "max_abs_gap": None,
                "note": (f"the {XP.GENERATOR_RECORD_PINS[position][1]} record is absent or a "
                         f"path proof — the reproduction control DID NOT RUN, which is never a "
                         f"pass (NF1.7 (a))")}
    label = CONSUMED_BANK_LABEL[position]
    return SA.incumbent_reproduction(
        {fr["label"]: fr["positions"][position]["scores"][label] for fr in usable}, record)


# ── The derive layer (NF-W2e: every verdict from stored rows, zero refit) ───────────────────────
def _load_rows(fold_results: list[dict]) -> dict[str, pd.DataFrame]:
    rows: dict[str, pd.DataFrame] = {}
    for fr in sorted(fold_results, key=lambda r: r["label"]):
        p = Path(fr["rows_path"])
        if not p.exists():
            raise FileNotFoundError(
                f"fold {fr['label']}: row artifact {p} is absent — the derive layer fits every "
                f"recalibration from stored OOF rows; re-run the fold (or run on the machine "
                f"holding the artifacts). ⛔ deriving without it would silently change the "
                f"estimator population.")
        rows[fr["label"]] = pd.read_parquet(p)
    return rows


def _fit_recal_tables(rows_by_fold: dict[str, pd.DataFrame]) -> dict:
    """Per (fold, position, generator∈{consumed,swap}) recal parameters, fit on PRIOR folds'
    OOF rows ONLY (fold 1 ⇒ identity by construction, prereg §4). Also the oracle (peek) params
    per fold and the trailing-3 sensitivity (report-only)."""
    labels = sorted(rows_by_fold)
    out: dict[str, dict] = {}
    for k, label in enumerate(labels):
        prior = [rows_by_fold[l] for l in labels[:k]]
        prior_df = pd.concat(prior, ignore_index=True) if prior else None
        trail = [rows_by_fold[l] for l in labels[max(0, k - 3):k]]
        trail_df = pd.concat(trail, ignore_index=True) if trail else None
        fold_df = rows_by_fold[label]
        entry: dict = {"has_prior": prior_df is not None, "n_prior_folds": k}
        for gen_col in ("point_consumed", "point_swap"):
            per_pos: dict[str, dict] = {}
            for pos in XP.POSITIONS:
                cell: dict = {}
                if prior_df is not None:
                    sel = prior_df["position"] == pos
                    pp, yy = prior_df.loc[sel, gen_col].to_numpy(), prior_df.loc[sel, "y"].to_numpy()
                    cell["level_add"] = XP.fit_level_add(pp, yy)
                    cell["level_affine"] = XP.fit_level_affine(pp, yy)
                else:
                    cell["level_add"] = {"delta": 0.0, "fitted": False, "n_prior": 0,
                                         "note": "fold 1 — no prior OOF; identity by construction"}
                    cell["level_affine"] = {"a": 0.0, "b": 1.0, "fitted": False, "n_prior": 0,
                                            "note": "fold 1 — no prior OOF; identity by construction"}
                if trail_df is not None:
                    sel = trail_df["position"] == pos
                    cell["level_add_trail3"] = XP.fit_level_add(
                        trail_df.loc[sel, gen_col].to_numpy(), trail_df.loc[sel, "y"].to_numpy())
                sel_f = fold_df["position"] == pos
                cell["level_add_oracle"] = XP.fit_level_add(
                    fold_df.loc[sel_f, gen_col].to_numpy(), fold_df.loc[sel_f, "y"].to_numpy())
                per_pos[pos] = cell
            entry[gen_col] = per_pos
        entry["pos_mean"] = (
            {p: float(prior_df.loc[prior_df["position"] == p, "y"].mean())
             for p in XP.POSITIONS} if prior_df is not None else None)
        out[label] = entry
    return out


def _points_under_arm(fold_df: pd.DataFrame, params_by_pos: dict[str, dict], arm: str,
                      gen_col: str, pos_mean: dict[str, float] | None) -> np.ndarray | None:
    """The fold's ranking points under one arm/anchor. None ⇒ the arm is unevaluable this fold."""
    pts = fold_df[gen_col].to_numpy(float).copy()
    pos = fold_df["position"].astype(str).to_numpy()
    if arm == XP.INCUMBENT:
        return pts
    if arm == "zero_point":
        return np.zeros_like(pts)
    if arm == "position_mean_point":
        if pos_mean is None:
            return None
        out = np.full_like(pts, np.nan)
        for p, mu in pos_mean.items():
            out[pos == p] = mu
        return out
    if arm == "level_add_permuted":
        base = {p: params_by_pos[p]["level_add"] for p in XP.POSITIONS}
        table = XP.permuted_params(base)
        out = pts.copy()
        for p, prm in table.items():
            out[pos == p] = XP.apply_level_add(pts[pos == p], prm)
        return out
    key = "level_add_oracle" if arm == "level_add_oracle" else arm
    out = pts.copy()
    for p in XP.POSITIONS:
        prm = params_by_pos[p][key]
        sel = pos == p
        if key == "level_affine":
            out[sel] = XP.apply_level_affine(pts[sel], prm)
        else:
            out[sel] = XP.apply_level_add(pts[sel], prm)
    return out


def _affine_eligibility(recal_tables: dict, evaluable: list[str]) -> dict:
    """⛔ NF-D16: ANY fitted slope ≤ AFFINE_MIN_SLOPE at any (position, evaluable fold) makes
    `level_affine` ineligible outright (a non-positive slope inverts a board)."""
    bad: list[str] = []
    for label in evaluable:
        for pos in XP.POSITIONS:
            prm = recal_tables[label]["point_consumed"][pos]["level_affine"]
            if prm["fitted"] and prm["b"] <= XP.AFFINE_MIN_SLOPE:
                bad.append(f"{label}|{pos} (b={prm['b']:.4f})")
    return {"eligible": not bad, "violations": bad}


def _weekly_displacement(fold_df: pd.DataFrame, pts_a: np.ndarray, pts_b: np.ndarray,
                         swapped_pos: str, cfg, profile) -> dict:
    """Merged-board rank displacement between two point vectors, per global week, pooled by
    rows: the swapped position's own movement and OTHER positions' movement (the level-mediated
    channel through flex allocation + interleaving)."""
    own_moves: list[float] = []
    other_moves: list[float] = []
    df = fold_df[["gw", "gsis_id", "position"]].copy()
    df["a"], df["b"] = pts_a, pts_b
    for _, wk in df.groupby("gw", sort=False):
        ba = FVOR.build_board(wk.rename(columns={"a": "league_points"}), cfg, profile)
        bb = FVOR.build_board(wk.rename(columns={"b": "league_points"}), cfg, profile)
        m = ba[["gsis_id", "position", "overall_rank"]].merge(
            bb[["gsis_id", "overall_rank"]], on="gsis_id", suffixes=("_a", "_b"))
        move = (m["overall_rank_a"] - m["overall_rank_b"]).abs()
        own_moves.extend(move[m["position"] == swapped_pos].tolist())
        other_moves.extend(move[m["position"] != swapped_pos].tolist())
    return {"own_mean_abs_rank_move": round(float(np.mean(own_moves)), 3) if own_moves else None,
            "other_mean_abs_rank_move": (round(float(np.mean(other_moves)), 3)
                                         if other_moves else None)}


def derive_verdict_layer(out: dict) -> dict:  # noqa: C901 — the pre-registered derivation
    fold_results = out["fold_results"]
    labels = sorted(fr["label"] for fr in fold_results)
    skipped = {fr["label"]: [p for p, b in fr["positions"].items() if b.get("skipped")]
               for fr in fold_results}
    any_skipped = any(v for v in skipped.values())

    repro = {pos: _reproduction(fold_results, pos) for pos in XP.POSITIONS}
    all_reproduce = all(r["reproduces"] for r in repro.values())

    rows_by_fold = _load_rows(fold_results)
    recal_tables = _fit_recal_tables(rows_by_fold)

    # ── family A: identity biases per (fold, position), all folds ───────────────────────────────
    bias_by_pos: dict[str, list[float]] = {p: [] for p in XP.POSITIONS}
    for label in labels:
        df = rows_by_fold[label]
        for pos in XP.POSITIONS:
            sel = df["position"] == pos
            bias_by_pos[pos].append(
                float((df.loc[sel, "point_consumed"] - df.loc[sel, "y"]).mean())
                if sel.any() else np.nan)
    family_a = XP.pairwise_gap_tests(bias_by_pos)
    pooled_identity_bias = {
        pos: XP.pooled_bias([XP.bias_detail(
            rows_by_fold[l].loc[rows_by_fold[l]["position"] == pos, "point_consumed"].to_numpy(),
            rows_by_fold[l].loc[rows_by_fold[l]["position"] == pos, "y"].to_numpy())
            for l in labels]) for pos in XP.POSITIONS}

    # ── family B: the recal contest on the 7 evaluable folds ────────────────────────────────────
    evaluable = [l for l in labels if recal_tables[l]["has_prior"]]
    stats: dict[str, dict] = {a: {"range_by_fold": [], "rmse_by_fold": {p: [] for p in XP.POSITIONS},
                                  "bias_by_fold": {p: [] for p in XP.POSITIONS}}
                              for a in XP.ALL_POINT_LABELS}
    for label in evaluable:
        df = rows_by_fold[label]
        tbl = recal_tables[label]["point_consumed"]
        gm = recal_tables[label]["pos_mean"]
        pos = df["position"].astype(str).to_numpy()
        y = df["y"].to_numpy(float)
        for arm in XP.ALL_POINT_LABELS:
            pts = _points_under_arm(df, tbl, arm, "point_consumed", gm)
            if pts is None:
                continue
            per_pos_bias = {}
            for p in XP.POSITIONS:
                sel = pos == p
                per_pos_bias[p] = float((pts[sel] - y[sel]).mean())
                stats[arm]["bias_by_fold"][p].append(per_pos_bias[p])
                stats[arm]["rmse_by_fold"][p].append(XP.rmse(pts[sel], y[sel]))
            stats[arm]["range_by_fold"].append(XP.fold_range(per_pos_bias))

    def _pooled_rmse(arm: str, p: str) -> float | None:
        v = stats[arm]["rmse_by_fold"][p]
        return round(float(np.sqrt(np.mean(np.square(v)))), 4) if v else None

    affine_elig = _affine_eligibility(recal_tables, evaluable)
    range_by_arm = {a: {"range_by_fold": stats[a]["range_by_fold"],
                        "pooled": (round(float(np.mean(stats[a]["range_by_fold"])), 4)
                                   if stats[a]["range_by_fold"] else None),
                        "eligible": (affine_elig["eligible"] if a == "level_affine" else True)}
                    for a in XP.ALL_POINT_LABELS}
    winner = XP.select_arm({a: range_by_arm[a] for a in XP.REAL_ARMS}) if evaluable else None

    # per-arm clauses for the winner (prereg §5.2)
    clauses: dict[str, bool | None] = {}
    dsr = pbo = p_gap = None
    deflate_detail: dict = {}
    swap = None
    if winner is not None and len(evaluable) >= 4:
        r_id = np.asarray(range_by_arm[XP.INCUMBENT]["range_by_fold"], float)
        r_w = np.asarray(range_by_arm[winner]["range_by_fold"], float)
        deltas = r_id - r_w                     # positive ⇒ the arm reduced the range
        p_gap = XP.paired_onesided_p(deltas)
        clauses["reduces_gap"] = bool(p_gap is not None and p_gap < XP.ALPHA
                                      and float(np.mean(deltas)) > 0)
        perm = range_by_arm["level_add_permuted"]["pooled"]
        clauses["beats_permuted"] = (None if perm is None or range_by_arm[winner]["pooled"] is None
                                     else bool(range_by_arm[winner]["pooled"] < perm))
        harm = []
        for p in XP.POSITIONS:
            hd = (np.asarray(stats[winner]["rmse_by_fold"][p], float)
                  - np.asarray(stats[XP.INCUMBENT]["rmse_by_fold"][p], float))
            ph = XP.paired_onesided_p(hd)       # small ⇒ the arm is reliably WORSE
            harm.append(bool(ph is not None and ph < XP.ALPHA and float(np.mean(hd)) > 0))
        clauses["no_rmse_harm"] = not any(harm)
        clauses["degenerates_lose"] = bool(all(
            _pooled_rmse(d, p) is not None and _pooled_rmse(winner, p) is not None
            and _pooled_rmse(d, p) > _pooled_rmse(winner, p)
            for d in ("zero_point", "position_mean_point") for p in XP.POSITIONS))
        # PBO over the eligible field + DSR on the winner-vs-identity range deltas
        mat = pd.DataFrame({a: stats[a]["range_by_fold"] for a in XP.ELIGIBLE},
                           index=evaluable)
        deflate_detail = NF18.deflate(mat, subset=list(XP.ELIGIBLE))
        pbo = deflate_detail.get("pbo")
        trial_srs = []
        for a in XP.REAL_ARMS:
            d = r_id - np.asarray(stats[a]["range_by_fold"], float)
            sd = float(np.nanstd(d, ddof=1))
            trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
        dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
        # the NF1.8 tied-field discipline, pre-registered (prereg §5.2 (g)): a high PBO whose
        # Bailey degradation is ≤ OS_GAP_TIE_PCT is a TIE between near-clone arms, not overfitting
        os_gap = deflate_detail.get("os_gap_pct")
        clauses["pbo_ok"] = bool(
            (pbo is not None and pbo < XP.PBO_MAX)
            or (os_gap is not None and os_gap <= XP.OS_GAP_TIE_PCT))
        clauses["dsr_ok"] = bool(dsr is not None and dsr >= XP.DSR_MIN)

    # ── §6 the generator-swap verification ──────────────────────────────────────────────────────
    if evaluable:
        before: dict[str, np.ndarray] = {}
        after: dict[str, np.ndarray] = {}
        arm_for_swap = winner if winner is not None else "level_add"
        for p in XP.POSITIONS:
            b_f, a_f = [], []
            for label in evaluable:
                df = rows_by_fold[label]
                sel = df["position"] == p
                pc = df.loc[sel, "point_consumed"].to_numpy(float)
                ps = df.loc[sel, "point_swap"].to_numpy(float)
                b_f.append(float((pc - ps).mean()))
                tbl_c = recal_tables[label]["point_consumed"][p][
                    "level_affine" if arm_for_swap == "level_affine" else "level_add"]
                tbl_s = recal_tables[label]["point_swap"][p][
                    "level_affine" if arm_for_swap == "level_affine" else "level_add"]
                if arm_for_swap == "level_affine":
                    a_f.append(float((XP.apply_level_affine(pc, tbl_c)
                                      - XP.apply_level_affine(ps, tbl_s)).mean()))
                else:
                    a_f.append(float((XP.apply_level_add(pc, tbl_c)
                                      - XP.apply_level_add(ps, tbl_s)).mean()))
            before[p], after[p] = np.asarray(b_f), np.asarray(a_f)
        swap = XP.swap_clause(before, after)
        swap["arm_used"] = arm_for_swap
        clauses["swap_clause"] = swap["passes"]

    # `banks_untouched` — the PIT-preservation identity, measured at input-write time and
    # verified here against the stored rows (a writer that shifted a quantile goes RED)
    clauses["banks_untouched"] = None            # set by _write_input below

    # ── board displacement decomposition (reported) ─────────────────────────────────────────────
    cfg, profile = LP.get_preset(GATE_LEAGUE), LP.NFL_PROFILE
    board_decomp: dict[str, dict] = {}
    if evaluable:
        label = evaluable[-1]                    # the most recent fold, reported as the exemplar
        df = rows_by_fold[label]
        tbl_c = recal_tables[label]["point_consumed"]
        tbl_s = recal_tables[label]["point_swap"]
        for p in XP.POSITIONS:
            sel = (df["position"] == p).to_numpy()
            pts_cons = df["point_consumed"].to_numpy(float).copy()
            pts_swapped = pts_cons.copy()
            pts_swapped[sel] = df.loc[sel, "point_swap"].to_numpy(float)
            shift = float(np.mean(pts_cons[sel] - pts_swapped[sel]))
            pts_matched = pts_swapped.copy()
            pts_matched[sel] = pts_swapped[sel] + shift
            board_decomp[p] = {
                "fold": label, "level_shift": round(shift, 4),
                "total": _weekly_displacement(df, pts_cons, pts_swapped, p, cfg, profile),
                "ordering_only": _weekly_displacement(df, pts_cons, pts_matched, p, cfg, profile),
            }

    harness_ok = bool(all_reproduce and not any_skipped and len(labels) >= 1)
    if len(evaluable) < 4:                       # prereg §5.4: <4 evaluable folds ⇒ UNDEFINED
        winner = None
        harness_ok = False
    gap_detected = family_a["gap_detected"] if harness_ok else None

    # PROVISIONAL verdict: `banks_untouched` is measured AT WRITE TIME (below), so the shipped-arm
    # decision is taken with it PENDING; the FINAL verdict is recomputed from the measured value
    # by `_write_input`, and a write that broke the identity demotes the ship (never the reverse).
    provisional = dict(clauses)
    provisional["banks_untouched"] = True if winner is not None else None
    verdict = XP.comparability_verdict(
        harness_ok=harness_ok, gap_detected=gap_detected,
        max_mde_ppr=family_a.get("max_mde_ppr"), winner=winner,
        winner_clauses=provisional if winner is not None else None,
        swap_state=swap["state"] if swap else None)

    # ── null classification, per the vertical's rule ────────────────────────────────────────────
    classification: dict | None = None
    if verdict["state"] == XP.V_UNREPAIRED and winner is not None:
        failing = [c for c in XP.ARM_CLAUSES
                   if clauses.get(c) is False or (clauses.get(c) is None and c != "swap_clause")]
        anchor_fail = [c for c in failing if c in XP.ANCHOR_CLAUSES]
        stat_fail = [c for c in failing if c in XP.STATISTICAL_CLAUSES]
        r_id = np.asarray(range_by_arm[XP.INCUMBENT]["range_by_fold"], float)
        r_w = np.asarray(range_by_arm[winner]["range_by_fold"], float)
        deltas = r_id - r_w
        sd = float(np.nanstd(deltas, ddof=1))
        instrument = cv_power.classify_null(
            metric="cross_position_bias_range", n_folds=len(evaluable),
            n_arms=len(XP.REAL_ARMS),
            beats_foil=bool(float(np.nanmean(deltas)) > 0),
            observed_sr=(float(np.nanmean(deltas)) / sd if sd > 1e-12 else None),
            var_trials_sr=(float(np.var(np.asarray([
                float(np.nanmean(r_id - np.asarray(stats[a]["range_by_fold"], float)))
                / max(float(np.nanstd(r_id - np.asarray(stats[a]["range_by_fold"], float),
                                      ddof=1)), 1e-12)
                for a in XP.REAL_ARMS]), ddof=1)) if len(XP.REAL_ARMS) > 1 else None),
            fold_wins=int((deltas > 0).sum()), p_one_sided=p_gap,
            degenerates_excluded_from_v=True,
            declared_field_size=XP.DECLARED_FIELD_SIZE)
        if anchor_fail:
            classification = {
                "state": "CONSTRAINT_REFUSED", "binding_half": "anchor",
                "failing_anchor_checks": anchor_fail,
                "failing_statistical_checks": stat_fail,
                "retest_trigger": None,
                "reason": ("the refusal rests on anchor/constraint clauses — more data makes the "
                           "refusal MORE certain, never less (NF-D18); no data trigger is "
                           "published"),
                "instrument_verdict": {"state": instrument.state, "reason": instrument.reason,
                                       "retest_trigger": instrument.retest_trigger},
            }
        else:
            classification = GE.flag_unsafe_field_shrink(
                {"state": instrument.state, "reason": instrument.reason,
                 "retest_trigger": instrument.retest_trigger,
                 "failing_statistical_checks": stat_fail,
                 "field_remedy_admissible": getattr(instrument, "detail", {}).get(
                     "field_remedy_admissible") if hasattr(instrument, "detail") else None},
                len(XP.REAL_ARMS))

    out["reproduction"] = repro
    out["family_a"] = family_a
    out["identity_bias"] = {"pooled": pooled_identity_bias, "by_fold": bias_by_pos}
    out["recal"] = {
        "evaluable_folds": evaluable, "n_evaluable": len(evaluable),
        "affine_eligibility": affine_elig,
        "range_by_arm": {a: {k: v for k, v in d.items() if k != "range_by_fold"}
                         | {"range_by_fold": [round(float(x), 4) for x in d["range_by_fold"]]}
                         for a, d in range_by_arm.items()},
        "rmse_pooled": {a: {p: _pooled_rmse(a, p) for p in XP.POSITIONS}
                        for a in XP.ALL_POINT_LABELS},
        "winner": winner, "winner_clauses": clauses,
        "p_reduces_gap_one_sided": p_gap, "pbo": pbo, "dsr": dsr,
        "deflate_detail": {k: deflate_detail.get(k) for k in
                           ("pbo", "os_gap_pct", "contender_spread_pct", "flips")},
        "oracle_ceiling": {
            "note": ("`level_add_oracle` peeks the test fold's own mean error — its RMSE "
                     "improvement is the CEILING of the level channel (NF-D16 (e)); never a "
                     "trial"),
            "rmse_pooled": {p: _pooled_rmse("level_add_oracle", p) for p in XP.POSITIONS}},
        "trailing3_sensitivity_note": ("report-only (prereg §4): trailing-3 δs are recorded in "
                                       "the recal tables; ⛔ never selected here"),
    }
    out["swap_verification"] = swap
    out["board_decomposition"] = board_decomp
    out["skipped"] = skipped
    out["verdict"] = verdict
    out["classification"] = classification
    out["qb_consumption"] = {
        "decision": XP.QB_CONSUMPTION, "rationale": XP.QB_CONSUMPTION_RATIONALE,
        "caveat": XP.QB_CONSUMPTION_CAVEAT}
    out["second_reader"] = XP.SECOND_READER
    out["promote_blockers"] = list(XP.PROMOTE_BLOCKERS)

    # ── the deliverable: the 4-position VOR-ranked input (prereg §7) ────────────────────────────
    out = _write_input(out, rows_by_fold, recal_tables, range_by_arm, pooled_identity_bias,
                       cfg, profile)
    return out


def _write_input(out: dict, rows_by_fold: dict[str, pd.DataFrame], recal_tables: dict,
                 range_by_arm: dict, pooled_identity_bias: dict, cfg, profile) -> dict:
    """The input parquets under the SHIPPED arm (identity unless the verdict is
    LEVEL_ARTIFACT_REMOVED), plus the `banks_untouched` identity: the written quantiles must be
    byte-identical to the stored generator quantiles (a writer that 'helpfully' shifts the band
    by δ — the NF-TR2 apply_to_band mistake — goes RED here)."""
    shipped = (out["verdict"]["winner"]
               if out["verdict"]["state"] == XP.V_REMOVED else XP.INCUMBENT)
    input_dir = Path(out["input_dir"])
    input_dir.mkdir(parents=True, exist_ok=True)
    max_q_drift = 0.0
    summaries: dict[str, dict] = {}
    for label, df in rows_by_fold.items():
        w = df.copy()
        tbl = recal_tables[label]["point_consumed"]
        pts = _points_under_arm(w, tbl, shipped, "point_consumed", None)
        w["point_raw"] = w["point_consumed"]
        w["point_recal"] = pts
        w["recal_arm"] = shipped
        w["point_vs_bank_offset"] = w["point_recal"] - w["point_raw"]
        w["generator"] = w["position"].map(XP.CONSUMED_GENERATOR_OF)
        w["level_gap_disclosure"] = w["position"].map(
            {p: pooled_identity_bias[p]["bias_pooled"] for p in XP.POSITIONS})
        w["qb_option_b"] = w["position"] == "QB"
        w["calibration_warning"] = w["position"].map(CALIBRATION_WARNING_OF)
        # the identity: the written p10/p50/p90 ARE the stored generator quantiles
        max_q_drift = max(max_q_drift, float(np.max(np.abs(
            w[["p10", "p50", "p90"]].to_numpy() - df[["p10", "p50", "p90"]].to_numpy()))))
        boards = []
        for _, wk in w.groupby("gw", sort=False):
            boards.append(FVOR.build_board(wk.rename(columns={"point_recal": "league_points"}),
                                           cfg, profile))
        b = pd.concat(boards, ignore_index=True).rename(
            columns={"league_points": "point_recal"})
        b = b[[c for c in XP.INPUT_SCHEMA if c in b.columns]]
        b.to_parquet(input_dir / f"{label}.parquet", index=False)
        top = b.sort_values(["gw", "overall_rank"]).groupby("gw").head(3)
        summaries[label] = {
            "n_rows": int(len(b)),
            "vor_top3_sample": top[["gw", "gsis_id", "position", "vor"]].head(9)
            .to_dict("records"),
            "replacement_by_week_mean": {
                p: round(float(b.loc[b["position"] == p, "replacement_points"].mean()), 3)
                for p in XP.POSITIONS},
        }
    banks_untouched = bool(max_q_drift == 0.0)
    out["recal"]["winner_clauses"]["banks_untouched"] = banks_untouched
    if out["verdict"]["winner"] is not None and out["verdict"]["state"] in (
            XP.V_REMOVED, XP.V_UNREPAIRED):
        # the FINAL verdict, from the full clause set with the MEASURED identity value
        out["verdict"] = XP.comparability_verdict(
            harness_ok=True, gap_detected=out["verdict"]["gap_detected"],
            max_mde_ppr=out["verdict"]["max_mde_ppr"], winner=out["verdict"]["winner"],
            winner_clauses=out["recal"]["winner_clauses"],
            swap_state=out["verdict"]["swap_state"])
        if out["verdict"]["state"] != XP.V_REMOVED and shipped != XP.INCUMBENT:
            # the write broke the identity ⇒ demote to identity and rewrite (never ship a
            # band-shifting layer — the NF-TR2 apply_to_band mistake, caught at the artifact)
            out["input_rewritten_as_identity"] = True
            out["verdict_before_demotion"] = XP.V_REMOVED
            return _write_input(out, rows_by_fold, recal_tables, range_by_arm,
                                pooled_identity_bias, cfg, profile)
    out["input"] = {"dir": str(input_dir), "shipped_arm": shipped,
                    "schema": list(XP.INPUT_SCHEMA), "banks_untouched": banks_untouched,
                    "max_quantile_drift": max_q_drift,
                    # prereg §5.3: an UNREPAIRED (or UNDEFINED) verdict flags the input
                    # not-cross-rankable — per-position use stays valid, the merged VOR does not
                    "cross_rankable": out["verdict"]["state"] in (XP.V_COMPARABLE, XP.V_REMOVED),
                    "fold_summaries": summaries}
    return out


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:
    v = out["verdict"]
    lines = [
        f"# NF-W8-0 — the cross-position comparability layer ({v['state']})",
        "",
        f"Generated {out['generated_at']} · gate league **{out['gate_league']}** · "
        f"{out['n_folds']} folds · target `{XP.TARGET}`",
        "",
        "⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 challenger — this record "
        "promotes nothing and publishes nothing.",
        "",
        "## §1 The QB consumption decision (Option B, registered forward)",
        "",
        f"- decision: **{out['qb_consumption']['decision']}**",
        f"- rationale: {out['qb_consumption']['rationale']}",
        f"- ⚠️ caveat: {out['qb_consumption']['caveat']}",
        f"- 🚩 second reader: {out['second_reader']['status']}",
        "",
        "## Verdict",
        "",
        f"- state: **{v['state']}**",
        f"- {v['reason']}",
        f"- shipped arm: `{out.get('input', {}).get('shipped_arm')}`",
        "",
        "## Reproduction pins (the consumed generators, by identity)",
        "",
        "| pos | generator | reproduces | folds | max gap |",
        "|---|---|---|---|---|",
    ]
    for pos in XP.POSITIONS:
        r = out["reproduction"][pos]
        lines.append(f"| {pos} | `{XP.CONSUMED_GENERATOR_OF[pos]}` | {r['reproduces']} | "
                     f"{r.get('n_folds_compared')} | {r.get('max_abs_gap')} |")
    fa = out["family_a"]
    lines += ["", "## Family A — the pairwise level-gap tests",
              "",
              f"- gap_detected: **{fa['gap_detected']}** (BH q={fa['bh_q']}, "
              f"{fa['n_pairs_evaluable']} evaluable pairs, max pairwise MDE "
              f"{fa['max_mde_ppr']} PPR at 80% power)",
              "",
              "| pair | gap (PPR) | se | p (2-sided) | BH rejected | MDE |",
              "|---|---|---|---|---|---|"]
    for name, pr in fa["pairs"].items():
        lines.append(f"| {name} | {pr['gap']} | {pr['se']} | {pr['p_two_sided']} | "
                     f"{pr.get('bh_rejected')} | {pr['mde_ppr']} |")
    lines += ["", "## Identity bias by position (pooled Σerr/Σn)",
              "",
              "| pos | bias (PPR) | n rows | calibration slope (last fold) |",
              "|---|---|---|---|"]
    slope_by_pos = {}
    for fr in out["fold_results"]:
        for pos, blk in fr["positions"].items():
            if not blk.get("skipped"):
                slope_by_pos[pos] = blk["calibration_slope"].get("slope")
    for pos in XP.POSITIONS:
        pb = out["identity_bias"]["pooled"][pos]
        lines.append(f"| {pos} | {None if pb['bias_pooled'] is None else round(pb['bias_pooled'], 4)} "
                     f"| {pb['n']} | {slope_by_pos.get(pos)} |")
    rc = out["recal"]
    lines += ["", "## Family B — the recalibration contest",
              "",
              f"- evaluable folds: {rc['n_evaluable']} ({', '.join(rc['evaluable_folds'])})",
              f"- winner: `{rc['winner']}` · p(reduces gap) {rc['p_reduces_gap_one_sided']} · "
              f"PBO {rc['pbo']} · DSR {rc['dsr']}",
              f"- affine eligibility: {rc['affine_eligibility']}",
              f"- winner clauses: {rc['winner_clauses']}",
              "",
              "| arm | pooled cross-position bias range (PPR) |",
              "|---|---|"]
    for a in XP.ALL_POINT_LABELS:
        lines.append(f"| `{a}` | {rc['range_by_arm'][a]['pooled']} |")
    sw = out.get("swap_verification")
    lines += ["", "## §6 Generator-swap verification", ""]
    if sw:
        lines.append(f"- state: **{sw['state']}** ({sw['n_active_positions']} active positions, "
                     f"arm `{sw['arm_used']}`)")
        for pos, d in sw["detail"].items():
            lines.append(f"  - {pos}: {d}")
    for pos, d in out.get("board_decomposition", {}).items():
        lines.append(f"- board decomposition {pos} (fold {d['fold']}): level shift "
                     f"{d['level_shift']} PPR · total move {d['total']} · ordering-only "
                     f"{d['ordering_only']}")
    if out.get("classification"):
        lines += ["", "## Null classification", "", f"- {out['classification']}"]
    lines += ["", "## The input", "",
              f"- dir: `{out.get('input', {}).get('dir')}` · shipped arm "
              f"`{out.get('input', {}).get('shipped_arm')}` · banks_untouched "
              f"{out.get('input', {}).get('banks_untouched')}",
              f"- schema: {out.get('input', {}).get('schema')}",
              "", "## Promote blockers", ""]
    lines += [f"- {b}" for b in out["promote_blockers"]]
    path.write_text("\n".join(lines) + "\n")


# ── Main ────────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-W8-0 — the cross-position comparability layer "
                                             "(§0.5)")
    ap.add_argument("--smoke", action="store_true",
                    help="path proof: 1 fold, all four positions, few draws (artifact _smoke) — "
                         "no verdict (reproduction pins cannot hit at smoke draws)")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="re-derive every verdict from the stored fold rows (zero refit)")
    ap.add_argument("--rebuild-cache", action="store_true", help="rebuild the W6d matrix cache")
    ap.add_argument("--rebuild-banks", action="store_true",
                    help="ignore the per-fold marginal-bank cache and refit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    suffix = "_smoke" if args.smoke else ""
    art = _PROJECT_ROOT / _ARTIFACT_REL.replace(".json", f"{suffix}.json")
    rows_dir = _ROWS_DIR.with_name(_ROWS_DIR.name + suffix)
    input_dir = _INPUT_DIR.with_name(_INPUT_DIR.name + suffix)

    if args.rewrite_report:
        out = json.loads(art.read_text())
        out["input_dir"] = str(input_dir)
        out = derive_verdict_layer(out)
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat()
        art.write_text(json.dumps(out, indent=2, default=str))
        write_report(out, art.with_suffix(".md"))
        log.info("NF-W8-0 report re-derived → %s", art.name)
        return 0

    FA.assert_stat_key_map()
    feat, pit_audit, attach = W6DA.build_matrix_w6d(SEASONS, rebuild_cache=args.rebuild_cache)
    gate_p, bake_p, def_p = W6DS.record_paths("")
    smap = SDSD.served_map(gate_p, bake_p, def_p)
    folds = WP.build_folds(feat)
    if args.smoke:
        folds = folds[-1:]
    draws = 300 if args.smoke else FA.ASSEMBLY_DRAWS
    matrix_key = W6DA.w6d_matrix_key(SEASONS)
    log.info("NF-W8-0: %d folds × %d positions, %d draws%s", len(folds), len(XP.POSITIONS),
             draws, " [SMOKE]" if args.smoke else "")

    t0 = time.time()
    fold_results = [run_fold(f, feat, smap, draws=draws, matrix_key=matrix_key,
                             rows_dir=rows_dir, rebuild_banks=args.rebuild_banks)
                    for f in folds]
    out = {
        "story": XP.STORY, "phase": "cross_position_comparability", "smoke": bool(args.smoke),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seasons": list(SEASONS), "n_folds": len(folds), "gate_league": GATE_LEAGUE,
        "matrix_key": matrix_key, "pit_audit": pit_audit, "attach_audit": attach,
        "served_map_sources": {c: v["source"] for c, v in smap.items()},
        "assembly_draws": draws, "seed": SA._SEED,
        "consumed_generators": dict(XP.CONSUMED_GENERATOR_OF),
        "swap_generators": dict(XP.SWAP_GENERATOR_OF),
        "declared_field": {"incumbent": XP.INCUMBENT, "real_arms": list(XP.REAL_ARMS),
                           "anchors": list(XP.ANCHOR_ARMS),
                           "declared_field_size": XP.DECLARED_FIELD_SIZE},
        "input_dir": str(input_dir),
        "fold_results": fold_results, "runtime_seconds": round(time.time() - t0, 1),
    }
    out = derive_verdict_layer(out)
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(json.dumps(out, indent=2, default=str))
    write_report(out, art.with_suffix(".md"))
    log.info("NF-W8-0 %s → %s (%.1fs)", out["verdict"]["state"], art.name,
             out["runtime_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
