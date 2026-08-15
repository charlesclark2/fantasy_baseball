"""run_nf_tr2_level.py — NF-TR2: season-projection LEVEL recalibration (draft-board credibility).

Runs the pre-registration in `season_level_recalibration.py` (read it first — every choice lives
there): STEP 0 holds the served band through the model path (RAISE); STEP 1 DECOMPOSES the tier
bias into availability vs per-game rate; STEP 2 fits the two declared forms strictly in-fold on the
13 wide-window folds (2013–2025), with the served band held FIXED (bracketed to the moved point —
the served path) and the REFIT / SCALED treatments computed beside it; STEP 3
gates — the inherited constraints (C1 ordering / C2 placement / C3 coverage), the §0.5 deflation over
the DECLARED 3-trial field (with NF-B3's field tax reported on the same winner), the level gates
L1–L5, and the two-sided anchors — then applies the serving-time fit to the 2026 boards for the
before/after board diff (same order, shifted level).

⚖️ `best_alpha = 0` — a projection-quality product; no CLV/ROI claim.
⛔ ROOKIE LEG OUT OF SCOPE (NF-D21 CLOSED; inherited by import). ⛔ NF1.5's ORDERING untouched.
🔒 CODE-READY, deploy-HELD — nothing serves from this run; the board rebuild + republish is a
POST-MERGE operator step (see the closeout).

RUN ON THE LAPTOP (no Snowflake, no network — reads the cached veteran band panel + the 2013-rebuilt
merged boards; a fresh worktree must copy those gitignored artifacts in first):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_tr2_level
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

from quant_sports_intel_models.football.nfl.fantasy import level_recalibration as LR  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import season_level_recalibration as SLR  # noqa: E402,E501
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf_b3_joint as B3  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf_c3_reread as C3R  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf_recal1_level as R1  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M11  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_veteran_interval_ablation as VA,
)
from quant_sports_intel_models.football.nfl.fantasy.run_rookie_interval_ablation import (  # noqa: E402,E501
    _finish,
)

log = logging.getLogger("nfl.fantasy.nf_tr2_level")

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_STEM = "nf_tr2_level_recalibration"
_SPACE = SLR.SPACE


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Fits (strictly in-fold) — the R1 fold fits, with THIS story's estimator laid over `pos_const`
# ══════════════════════════════════════════════════════════════════════════════════════════════
def tr2_fits(fold: dict, *, seed: int = 20260808, window: int | None = None) -> dict:
    """R1's per-fold fits (the affine, the CRPS-peeking ceilings, the pos_median, the incumbent
    coverage) with `pos_const` REPLACED by the mean-match — and its permutation anchors re-fitted
    with the same estimator on the same shuffles (an anchor must differ from its candidate in exactly
    one thing: which outcome vector it saw). `window` (NF-TR2b) restricts BOTH candidate fits (and
    their permutation anchors) to the trailing seasons; the window SENSITIVITY fits are stored
    beside them under `("pos_const@w{N}", space)`."""
    fits = R1.fold_fits(fold, seed=seed, cov_rounding=None)
    tr = fold["train"]
    p_all, y_all = tr["point"].to_numpy(dtype=float), tr["real_fp_ppr"].to_numpy(dtype=float)
    pos_all = tr["position"].to_numpy()
    g_all = tr["proj_games"].to_numpy(dtype=float)
    seas = tr["target_season"].to_numpy()

    def _sub(w):
        m = SLR.window_mask(seas, int(fold["year"]), w)
        return p_all[m], y_all[m], pos_all[m], g_all[m]

    p, y, pos, g = _sub(window)
    fits[("pos_const", _SPACE)] = SLR.fit_pos_const(p, y, pos)
    fits[("pos_affine", _SPACE)] = SLR.fit_pos_affine(p, y, pos, g)
    fits["_window_rows"] = {"window": window, "n_rows": int(len(p)),
                            "rows_by_position": {q: int((pos == q).sum())
                                                 for q in LR.RECALIBRATED_POSITIONS}}
    for w in SLR.WINDOW_SENSITIVITY:
        pw, yw, posw, gw = _sub(w)
        fits[(f"pos_const@w{w}", _SPACE)] = SLR.fit_pos_const(pw, yw, posw)
    rng = np.random.default_rng(seed + int(fold["year"]))
    y_across = rng.permutation(y)
    y_within = y.copy()
    for q in LR.RECALIBRATED_POSITIONS:
        sel = np.flatnonzero(pos == q)
        if len(sel) > 1:
            y_within[sel] = rng.permutation(y_within[sel])
    fits[("_perm_across", "pos_const")] = SLR.fit_pos_const(p, y_across, pos)
    fits[("_perm_within", "pos_const")] = SLR.fit_pos_const(p, y_within, pos)
    fits[("_perm_across", "pos_affine")] = SLR.fit_pos_affine(p, y_across, pos, g)
    fits[("_perm_within", "pos_affine")] = SLR.fit_pos_affine(p, y_within, pos, g)
    # the peeking mean-match on the held-out fold (the LS-analogue ceiling init, reported)
    te = fold["test"]
    fits[("_peek_mm", "pos_const")] = SLR.fit_pos_const(
        te["point"].to_numpy(dtype=float), te["real_fp_ppr"].to_numpy(dtype=float),
        te["position"].to_numpy())
    return fits


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The band under each treatment
# ══════════════════════════════════════════════════════════════════════════════════════════════
class BandRefitter:
    """The REFIT treatment (a DISCLOSURE): the band model on the wire (`knn_norm k300`) refit on the RECALIBRATED
    training panel of each fold, queried at the recalibrated point — what `build_projection` does
    when the level model changes (the panel is recalibrated before `fit_veteran_band_from_panel`).
    Cached per (fold, form, params, λ). Falls back to the incumbent's served band on a row the refit
    cannot speak to (recorded), never to a fabricated interval."""

    def __init__(self, va_folds: dict):
        self.va = va_folds
        self.cache: dict = {}
        self.fallback_rows = 0
        self.rows = 0

    def band(self, year: int, frame: pd.DataFrame, form: str, params: dict, lam: float,
             served_lo: np.ndarray, served_hi: np.ndarray, newp: np.ndarray
             ) -> tuple[np.ndarray, np.ndarray]:
        key = (int(year), form, SLR.params_to_json(params), float(lam))
        if key not in self.cache:
            train = self.va[int(year)].train
            train_recal = SLR.recalibrate_panel_points(train, form, params, lam)
            self.cache[key] = SP.fit_veteran_band_model(
                train_recal, form=SP._VET_BAND_FORM, k=SP._VET_BAND_K, sd_gain=0.0,
                qreg_alpha=0.01)
        m = self.cache[key]
        pos = frame["position"].astype(str).str.upper().to_numpy()
        inp = SP.veteran_band_inputs(
            pos, newp, pd.to_numeric(frame["season_sd"], errors="coerce").to_numpy(dtype=float),
            proj_games=frame.get("proj_games"), base_games=frame.get("base_games"),
            snap_share=frame.get("snap_share"), seasons_missed=frame.get("seasons_missed"))
        if m is None:
            lo, hi = np.full(len(newp), np.nan), np.full(len(newp), np.nan)
        else:
            lo, hi = m.band_many(inp)
        bad = ~(np.isfinite(lo) & np.isfinite(hi))
        self.rows += len(newp)
        self.fallback_rows += int(bad.sum())
        lo = np.where(bad, served_lo, lo)
        hi = np.where(bad, served_hi, hi)
        return _finish(lo, hi, newp)


def make_triple_fn(form: str | None, params_by_fold: dict, lam: float, treatment: str,
                   refitter: BandRefitter):
    """`triple_fn(fold, key) -> (point, lo, hi)` for one arm under one band treatment. `form=None`
    is the incumbent (the served triple, untouched)."""
    def _fn(fold: dict, key: str) -> tuple:
        d = fold[key]
        p = d["point"].to_numpy(dtype=float)
        lo = d["served_p10"].to_numpy(dtype=float)
        hi = d["served_p90"].to_numpy(dtype=float)
        if form is None:
            return p, lo, hi
        pos = d["position"].to_numpy()
        g = d["proj_games"].to_numpy(dtype=float)
        params = params_by_fold[fold["year"]]
        newp = SLR.predict_level(form, params, p, pos, g, lam)
        if treatment == "fixed":
            return newp, np.clip(np.minimum(lo, newp), 0.0, None), np.maximum(hi, newp)
        if treatment == "scaled":
            return LR.apply_to_band(form, _SPACE, params, p, lo, hi, pos, g, lam)
        if treatment == "refit":
            rlo, rhi = refitter.band(fold["year"], d, form, params, lam, lo, hi, newp)
            return newp, rlo, rhi
        raise ValueError(treatment)
    return _fn


def make_anchor_fn(tag: str, fits_by_fold: dict, refitter: BandRefitter):
    """The two-sided anchors that are NOT a form at a λ (those go through `make_triple_fn`)."""
    def _fn(fold: dict, key: str) -> tuple:
        d = fold[key]
        p = d["point"].to_numpy(dtype=float)
        lo = d["served_p10"].to_numpy(dtype=float)
        hi = d["served_p90"].to_numpy(dtype=float)
        y = d["real_fp_ppr"].to_numpy(dtype=float)
        pos = d["position"].to_numpy()
        if tag == "oracle_perplayer":
            yy = np.clip(y, 0, None)
            return yy, yy, yy
        if tag == "zero_project":
            z = np.zeros_like(p)
            return z, z, z
        if tag == "wide_band":
            w = LR.WIDE_BAND_FACTOR
            return p, np.clip(p - w * (p - lo), 0, None), p + w * (hi - p)
        if tag == "pos_median":
            med = fits_by_fold[fold["year"]]["_pos_median"]
            adj = np.array([med.get(q, np.nan) for q in pos], dtype=float)
            adj = np.where(np.isfinite(adj), adj, p)
            return adj, adj, adj
        raise ValueError(tag)
    return _fn


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring — the R1 record shape, from precomputed triples
# ══════════════════════════════════════════════════════════════════════════════════════════════
def score_fold(fold: dict, triple_fn, inc_cov: dict) -> dict:
    p0, _, _, pos, g, y = R1._triples(fold)
    ap, alo, ahi = triple_fn(fold, "test")
    m = LR.band_metrics(ap, alo, ahi, y)
    m["ordering"] = LR.ordering_movement(p0, ap, pos)
    m["coverage"] = LR.coverage_floor_check(y, alo, ahi, pos, incumbent_coverage=inc_cov,
                                            equality_exact=True)
    m["per_position"] = {q: LR.band_metrics(ap[pos == q], alo[pos == q], ahi[pos == q], y[pos == q])
                         for q in LR.RECALIBRATED_POSITIONS if (pos == q).any()}
    m["rows"] = {"point": p0, "adj": ap, "lo": alo, "hi": ahi, "y": y, "pos": pos, "g": g}
    pu, _, _, posu, gu, yu = R1._triples(fold, "test_universe")
    apu, alou, ahiu = triple_fn(fold, "test_universe")
    um = LR.band_metrics(apu, alou, ahiu, yu)
    m["universe"] = {"crps": um[LR.SELECTION_METRIC], "mae": um["mae"], "bias": um["bias"],
                     "coverage80": um["coverage80"], "n": um["n"]}
    if not np.array_equal(g, fold["test"]["proj_games"].to_numpy(dtype=float)):
        raise AssertionError("L4: the games vector moved inside scoring")
    return m


def score_arm(folds: list, fits: dict, triple_fn, label: str, extra: dict | None = None) -> dict:
    per = {f["year"]: score_fold(f, triple_fn, fits[f["year"]]["_inc_coverage"]) for f in folds}
    years = list(per)

    def _m(key, nd=4):
        v = [per[y].get(key) for y in years if per[y].get(key) is not None]
        return round(float(np.mean(v)), nd) if v else None

    out = {"label": label, "per_fold": {y: {k: v for k, v in per[y].items() if k != "rows"}
                                        for y in years},
           "per_fold_metric": {y: per[y].get(LR.SELECTION_METRIC) for y in years},
           LR.SELECTION_METRIC: _m(LR.SELECTION_METRIC),
           **{k: _m(k) for k in LR.DISCLOSED_METRICS},
           "universe_crps": round(float(np.mean([per[y]["universe"]["crps"] for y in years])), 4),
           "universe_bias": round(float(np.mean([per[y]["universe"]["bias"] for y in years])), 4),
           "universe_coverage80": round(
               float(np.mean([per[y]["universe"]["coverage80"] for y in years])), 4),
           **(extra or {})}
    for q in LR.RECALIBRATED_POSITIONS:
        vals = [per[y]["per_position"].get(q, {}) for y in years]
        for k in (LR.SELECTION_METRIC, "mae", "bias", "coverage80"):
            v = [x.get(k) for x in vals if x.get(k) is not None]
            out[f"{k}_{q}"] = round(float(np.mean(v)), 3) if v else None
        rho = [per[y]["ordering"]["within_position_rho"].get(q) for y in years]
        rho = [x for x in rho if x is not None and np.isfinite(x)]
        out[f"rho_{q}"] = round(float(np.mean(rho)), 4) if rho else None
    # pooled-over-rows state (NF1.8: never a mean of per-fold means for a floor or a level)
    rows = {k: np.concatenate([per[y]["rows"][k] for y in years])
            for k in ("point", "adj", "lo", "hi", "y", "pos", "g")}
    inc_lo = np.concatenate([f["test"]["served_p10"].to_numpy(dtype=float) for f in folds])
    inc_hi = np.concatenate([f["test"]["served_p90"].to_numpy(dtype=float) for f in folds])
    inc_pooled = LR.per_position_coverage(rows["y"], inc_lo, inc_hi, rows["pos"], rounding=None)
    out["coverage_pooled"] = LR.coverage_floor_check(rows["y"], rows["lo"], rows["hi"], rows["pos"],
                                                     incumbent_coverage=inc_pooled,
                                                     equality_exact=True)
    out["worst_rank_move"] = max(per[y]["ordering"]["worst_rank_move"] for y in years)
    pooled_bias = {"pooled": float(np.mean(rows["adj"] - rows["y"]))}
    for q in LR.RECALIBRATED_POSITIONS:
        s = rows["pos"] == q
        pooled_bias[q] = float(np.mean(rows["adj"][s] - rows["y"][s])) if s.any() else float("nan")
    out["bias_pooled_rows"] = pooled_bias
    out["_rows"] = rows
    out["_per_fold_rows"] = {y: per[y]["rows"] for y in years}
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Constraints, out-of-sample per fold, at λ = 1 under the PRIMARY treatment
# ══════════════════════════════════════════════════════════════════════════════════════════════
def constraint_state(folds, fits, boards, structural, form: str, params_by_fold: dict, lam: float,
                     triple_fn) -> dict:
    per, activity = {}, {}
    for f in folds:
        y = f["year"]
        p, _, _, pos, g, real = R1._triples(f)
        ap, alo, ahi = triple_fn(f, "test")
        c1 = LR.ordering_movement(p, ap, pos)
        c1_ok = all(v >= 1.0 - LR.ORDERING_DO_NO_HARM for v in c1["within_position_rho"].values())
        board = boards[y]
        vet = ~board["is_rookie"].fillna(False).astype(bool).to_numpy()
        bp = pd.to_numeric(board["proj_fp_ppr"], errors="coerce").to_numpy(dtype=float)
        bpos = board["position"].astype(str).str.upper().to_numpy()
        bg = pd.to_numeric(board.get("proj_games", pd.Series(np.full(len(board), 17.0))),
                           errors="coerce").fillna(0.0).to_numpy(dtype=float)
        adj = bp.copy()
        adj[vet] = SLR.predict_level(form, params_by_fold[y], bp[vet], bpos[vet], bg[vet], lam)
        inc_rank = LR.board_placement(board).get("best_rookie_overall_rank")
        new_rank = LR.board_placement(board.assign(proj_fp_ppr=adj)).get("best_rookie_overall_rank")
        c2 = R1.board_admits(new_rank, inc_rank)
        if y in structural and not c2.get("evaluable"):
            c2 = {**c2, "admits": True, "inactive_structural": True}
        c3 = LR.coverage_floor_check(real, alo, ahi, pos, incumbent_coverage=fits[y]["_inc_coverage"],
                                     equality_exact=True)
        per[y] = {"lam": float(lam), "c1_ordering_ok": bool(c1_ok), "c2_placement_ok": bool(c2["admits"]),
                  "c2_inactive_structural": bool(c2.get("inactive_structural", False)),
                  "c3_coverage_ok": bool(c3["ok"]),
                  "admissible": bool(c1_ok and c2["admits"] and c3["ok"]),
                  "rank": c2.get("rank"), "incumbent_rank": inc_rank,
                  "worst_rank_move": c1["worst_rank_move"], "coverage_breaches": c3["breaches"],
                  "within_position_rho": c1["within_position_rho"]}
        activity[y] = (inc_rank is not None and new_rank is not None and new_rank != inc_rank)
    return {"holds_out": all(v["admissible"] for v in per.values()), "per_fold": per,
            "c1_only": all(v["c1_ordering_ok"] for v in per.values()),
            "c2_only": all(v["c2_placement_ok"] for v in per.values()),
            "c3_only": all(v["c3_coverage_ok"] for v in per.values()),
            "failing_folds": [y for y, v in per.items() if not v["admissible"]],
            "c2_active_folds": [y for y, a in activity.items() if a],
            "c2_structurally_absent_folds": [y for y, v in per.items() if v["c2_inactive_structural"]]}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The peeking ceilings per form under the FIXED band (matched treatment for the ceiling check)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def peek_fixed(form: str, fold: dict, init: dict) -> dict:
    from scipy.optimize import minimize

    te = fold["test"]
    p = te["point"].to_numpy(dtype=float)
    lo = te["served_p10"].to_numpy(dtype=float)
    hi = te["served_p90"].to_numpy(dtype=float)
    y = te["real_fp_ppr"].to_numpy(dtype=float)
    pos = te["position"].to_numpy()
    g = te["proj_games"].to_numpy(dtype=float)

    def _score(sel, params):
        newp = SLR.predict_level(form, params, p[sel], pos[sel], g[sel], 1.0)
        return float(np.mean(LR.crps_from_band(
            newp, np.clip(np.minimum(lo[sel], newp), 0, None), np.maximum(hi[sel], newp), y[sel])))

    out = {}
    for q in LR.RECALIBRATED_POSITIONS:
        sel = pos == q
        if sel.sum() < 5:
            continue
        if form == "pos_const":
            r = minimize(lambda x, s=sel, qq=q: _score(s, {qq: float(np.clip(x[0], *LR.MULT_CLIP))}),
                         [float(init.get(q, 1.0))], method="Nelder-Mead",
                         options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 200})
            out[q] = float(np.clip(r.x[0], *LR.MULT_CLIP))
        else:
            a0, b0 = init.get(q, (0.0, 1.0))
            r = minimize(lambda x, s=sel, qq=q: _score(s, {qq: (float(x[0]), float(x[1]))}),
                         [float(a0), float(b0)], method="Nelder-Mead",
                         options={"xatol": 1e-3, "fatol": 1e-6, "maxiter": 400})
            out[q] = (float(r.x[0]), float(r.x[1]))
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The serving-time fit + the board diff (same order, shifted level)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def board_diff(board: pd.DataFrame, form: str, params: dict, label: str) -> dict:
    from scipy.stats import kendalltau, spearmanr

    b = board.copy()
    b["position"] = b["position"].astype(str).str.upper()
    vet = ~b["is_rookie"].fillna(False).astype(bool).to_numpy()
    p = pd.to_numeric(b["proj_fp_ppr"], errors="coerce").to_numpy(dtype=float)
    g = pd.to_numeric(b.get("proj_games", pd.Series(np.full(len(b), 17.0))),
                      errors="coerce").fillna(0.0).to_numpy(dtype=float)
    pos = b["position"].to_numpy()
    adj = p.copy()
    adj[vet] = SLR.predict_level(form, params, p[vet], pos[vet], g[vet], 1.0)
    rows = []
    for q in LR.RECALIBRATED_POSITIONS:
        s = vet & (pos == q)
        if s.sum() < 3:
            continue
        rows.append({"position": q, "n_veterans": int(s.sum()),
                     "mean_before": round(float(p[s].mean()), 2),
                     "mean_after": round(float(adj[s].mean()), 2),
                     "level_shift_pct": round(100 * float(adj[s].sum() / p[s].sum() - 1), 2),
                     "spearman_before_after": round(float(spearmanr(p[s], adj[s]).correlation), 6),
                     "kendall_before_after": round(float(kendalltau(p[s], adj[s]).correlation), 6),
                     "order_identical": bool(np.array_equal(np.argsort(-p[s], kind="stable"),
                                                            np.argsort(-adj[s], kind="stable")))})
    top = b.assign(_adj=adj)
    t_before = top.sort_values("proj_fp_ppr", ascending=False)["player_name"].head(24).tolist()
    t_after = top.sort_values("_adj", ascending=False)["player_name"].head(24).tolist()
    return {"board": label, "n": int(len(b)), "n_veterans": int(vet.sum()), "per_position": rows,
            "rookies_untouched": bool(np.array_equal(p[~vet], adj[~vet])),
            "top24_before": t_before, "top24_after": t_after,
            "top24_membership_stable": set(t_before) == set(t_after)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md_table(rows: list[dict], cols: list[str] | None = None) -> str:
    if not rows:
        return "_(none)_"
    cols = cols or list(rows[0].keys())
    fmt = lambda v: (f"{v:.4f}" if isinstance(v, float) else str(v))  # noqa: E731
    return "\n".join(["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
                     + ["| " + " | ".join(fmt(r.get(c)) for c in cols) + " |" for r in rows])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true", help="3 folds, no λ-sweep; proves the path")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("--window", type=int, default=None,
                    help="NF-TR2b: the trailing-season window for the candidate fits (the "
                         "pre-registered value is season_level_recalibration.WINDOW_SEASONS; "
                         "omit for NF-TR2's full-history estimator)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    t0 = time.time()

    window = args.window
    story = SLR.TR2B_STORY if window is not None else SLR.STORY
    model_version = SLR.TR2B_MODEL_VERSION if window is not None else SLR.MODEL_VERSION
    stem = f"{_STEM}_b" if window is not None else _STEM
    seasons = tuple(SLR.FOLD_SEASONS[-3:] if args.smoke else SLR.FOLD_SEASONS)
    tier_n = LR.draftable_tier_size()
    reg = SLR.registration()
    log.info("%s — level recalibration · folds %s · tier %d/season · declared field %d · window %s",
             story, list(seasons), tier_n, SLR.DECLARED_FIELD_SIZE, window)

    # ── STEP 0: hold the served band (RAISE) + board provenance ─────────────────────────────────
    proofs, lookup = B3.step0(tuple(SLR.FOLD_SEASONS))
    boards, structural = B3.load_boards_b3(seasons)
    va_folds = {f.year: f for f in VA.build_folds(VA.load_panel(), list(seasons))}
    refitter = BandRefitter(va_folds)
    log.info("STEP 0 — served band held (IS80 %.3f Δ%.4f%%; tier cov 2019–25 %.4f)",
             proofs["universe_is80"], proofs["universe_is80_delta_pct"],
             proofs["served_tier_coverage_2019_2025"])

    panel_years = tuple(range(SLR.TRAIN_PANEL_START, max(seasons) + 1))
    d = R1.load_panel(panel_years)
    tier = R1.tier_mask(d, tier_n)
    folds = C3R.substitute_served_band(R1.build_folds(d, tier, seasons), lookup)
    years = [f["year"] for f in folds]

    # ── STEP 1: premise + decomposition on the fold window ──────────────────────────────────────
    d_win = d[d["target_season"] >= min(seasons)].reset_index(drop=True)
    premise = R1.premise_check(d_win, tier_n)
    tt = pd.concat([f["test"] for f in folds], ignore_index=True)
    tu = pd.concat([f["test_universe"] for f in folds], ignore_index=True)
    decomposition = {
        "tier": SLR.decompose_bias(tt["point"], tt["real_fp_ppr"], tt["proj_games"],
                                   tt["real_games"], tt["position"]),
        "universe": SLR.decompose_bias(tu["point"], tu["real_fp_ppr"], tu["proj_games"],
                                       tu["real_games"], tu["position"]),
    }
    dt = decomposition["tier"]["pooled"]
    log.info("STEP 1 — tier bias %.2f = availability %+.2f + rate %+.2f (identity %s; miss is rate: %s)",
             dt["bias"], dt["availability_part"], dt["rate_part"],
             decomposition["tier"]["identity_holds"], decomposition["tier"]["miss_is_rate"])

    # ── STEP 2: fits + arms ─────────────────────────────────────────────────────────────────────
    fits = {f["year"]: tr2_fits(f, window=window) for f in folds}
    # ⭐ the window DERIVATION (a design quantity: tier rows per position per season, no outcome
    #    read) — the pinned WINDOW_SEASONS must agree with it, or this run STOPS.
    rows_pp = tt.groupby("position").size() / float(len(years))
    derived_window = SLR.window_seasons_for(rows_pp.to_dict())
    window_derivation = {"tier_rows_per_position_per_season": {k: round(float(v), 2)
                                                                for k, v in rows_pp.items()},
                         "min_rows": SLR.WINDOW_MIN_ROWS, "derived_window": derived_window,
                         "pinned_window": SLR.WINDOW_SEASONS}
    if window is not None and window == SLR.WINDOW_SEASONS and derived_window != SLR.WINDOW_SEASONS \
            and not args.smoke:
        raise SystemExit(f"the pinned window {SLR.WINDOW_SEASONS} disagrees with its own derivation "
                         f"{derived_window} ({window_derivation}) — STOP; the registration is stale.")
    inc_fn = make_triple_fn(None, {}, 0.0, "refit", refitter)
    incumbent = score_arm(folds, fits, inc_fn, "incumbent (NULL)",
                          extra={"form": "incumbent", "rule": None, "recalibrates": False,
                                 "shippable": True, "is_foil": False, "treatment": "served"})
    arms, disclosures, placements = [incumbent], [], {}
    placements["incumbent (NULL)"] = {"holds_out": True, "per_fold": {}, "c2_only": True,
                                      "c3_only": True, "c1_only": True, "failing_folds": []}
    params_by = {form: {y: fits[y][(form, _SPACE)] for y in years} for form in SLR.FORMS}
    for form in SLR.FORMS:
        for treat in SLR.BAND_TREATMENTS:
            fn = make_triple_fn(form, params_by[form], SLR.LAMBDA, treat, refitter)
            primary = treat == SLR.BAND_TREATMENT
            label = f"{form} · λ=1 · mean-match" if form == "pos_const" else f"{form} · λ=1 · OLS"
            label = label if primary else f"{label} [{treat} band DISCLOSURE]"
            rec = score_arm(folds, fits, fn, label,
                            extra={"form": form, "rule": "fixed λ=1", "recalibrates": True,
                                   "shippable": primary, "is_foil": not primary,
                                   "treatment": treat, "lam_by_fold": {y: 1.0 for y in years},
                                   "params_by_fold": {y: SLR.params_to_json(params_by[form][y])
                                                      for y in years}})
            (arms if primary else disclosures).append(rec)
            if primary:
                placements[label] = constraint_state(folds, fits, boards, structural, form,
                                                     params_by[form], SLR.LAMBDA, fn)

    # ── anchors (PRIMARY treatment) ─────────────────────────────────────────────────────────────
    anchors: dict = {}
    for tag in ("oracle_perplayer", "zero_project", "pos_median", "wide_band"):
        anchors[tag] = score_arm(folds, fits, make_anchor_fn(tag, fits, refitter), tag)
    for form in SLR.FORMS:
        for which in ("permuted_across", "permuted_within"):
            pb = {y: fits[y][("_perm_across" if which == "permuted_across" else "_perm_within", form)]
                  for y in years}
            anchors[f"{which}@{form}"] = score_arm(
                folds, fits, make_triple_fn(form, pb, 1.0, SLR.BAND_TREATMENT, refitter),
                f"{which}@{form}")
        anchors[f"over_scale@{form}"] = score_arm(
            folds, fits, make_triple_fn(form, params_by[form], SLR.OVER_SCALE_LAMBDA,
                                        SLR.BAND_TREATMENT, refitter), f"over_scale@{form}")
    anchors["over_scale"] = anchors["over_scale@pos_const"]
    # the λ-sweep of the mean-match, under all three treatments (the interior-optimum question)
    sweep_rows = []
    sweep_lams = () if args.smoke else SLR.LAMBDA_SWEEP
    for treat in SLR.BAND_TREATMENTS:
        for lam in (0.0,) + tuple(sweep_lams) + (1.0,):
            if lam == 0.0:
                rec = incumbent
            elif lam == 1.0:
                rec = next(r for r in arms + disclosures
                           if r.get("form") == "pos_const" and r.get("treatment") == treat)
            else:
                rec = score_arm(folds, fits, make_triple_fn("pos_const", params_by["pos_const"],
                                                            lam, treat, refitter),
                                f"lambda_sweep@{lam:g} [{treat}]")
                if treat == SLR.BAND_TREATMENT:
                    anchors[f"lambda_sweep@{lam:g}"] = rec
            sweep_rows.append({"treatment": treat, "λ": lam, "CRPS": rec[LR.SELECTION_METRIC],
                               "bias": rec["bias_pooled_rows"]["pooled"], "cov80": rec["coverage80"],
                               "MAE": rec["mae"]})
    sweep_rows.sort(key=lambda r: (SLR.BAND_TREATMENTS.index(r["treatment"]), r["λ"]))
    # window sensitivity (anchors, never trials): the mean-match at each sensitivity window
    window_rows = []
    for w in SLR.WINDOW_SENSITIVITY:
        pbw = {y: fits[y][(f"pos_const@w{w}", _SPACE)] for y in years}
        rec = score_arm(folds, fits, make_triple_fn("pos_const", pbw, 1.0, SLR.BAND_TREATMENT,
                                                    refitter), f"window_sensitivity@w{w}")
        anchors[f"window_sensitivity@w{w}"] = rec
        window_rows.append({"window": ("full history" if w is None else w),
                            "is_registered": (w == window), "CRPS": rec[LR.SELECTION_METRIC],
                            "bias": rec["bias_pooled_rows"]["pooled"],
                            **{f"bias_{q}": rec["bias_pooled_rows"].get(q)
                               for q in LR.RECALIBRATED_POSITIONS},
                            "cov80": rec["coverage80"], "MAE": rec["mae"]})
    reg_rec = next(r for r in arms if r.get("form") == "pos_const")
    window_rows.append({"window": ("full history" if window is None else window),
                        "is_registered": True, "CRPS": reg_rec[LR.SELECTION_METRIC],
                        "bias": reg_rec["bias_pooled_rows"]["pooled"],
                        **{f"bias_{q}": reg_rec["bias_pooled_rows"].get(q)
                           for q in LR.RECALIBRATED_POSITIONS},
                        "cov80": reg_rec["coverage80"], "MAE": reg_rec["mae"]})

    # family ceilings under the FIXED band (matched treatment) + the arms under FIXED to compare
    ceilings, fixed_arms = {}, {}
    for form in SLR.FORMS:
        init_key = ("_peek_mm", "pos_const") if form == "pos_const" else ("_peek_ls", form)
        pk = {y: peek_fixed(form, f, fits[y][init_key]) for f in folds for y in [f["year"]]}
        ceilings[form] = score_arm(folds, fits, make_triple_fn(form, pk, 1.0, "fixed", refitter),
                                   f"oracle_{form} [fixed band, CRPS-fitted, PEEKING]")
        fixed_arms[form] = next(r for r in arms + disclosures
                                if r.get("form") == form and r.get("treatment") == "fixed")
        anchors[f"oracle_{form}"] = ceilings[form]
    family_ok = {f: bool(ceilings[f][LR.SELECTION_METRIC] <= fixed_arms[f][LR.SELECTION_METRIC] + 1e-9)
                 for f in SLR.FORMS}
    order_ok = all(ceilings[b][LR.SELECTION_METRIC] <= ceilings[a][LR.SELECTION_METRIC] + 1e-9
                   for a, b in SLR.FORM_NESTING)

    # ── STEP 3: selection + deflation over the DECLARED field ───────────────────────────────────
    sel = R1.select_pooled(arms, incumbent, years, placements)
    per_pos = R1.per_position_disclosure(arms, incumbent, years, placements)
    inc_m = incumbent[LR.SELECTION_METRIC]
    best_real = min((r[LR.SELECTION_METRIC] for r in arms if r.get("recalibrates")), default=inc_m)
    winner_rec = next((r for r in arms if sel["winner"] and r["label"] == sel["winner"]["label"]), None)

    # the SAME winner under NF-B3's declared field (the conservative disclosure)
    dsr_b3 = None
    if sel.get("per_fold_delta"):
        from scipy.stats import kurtosis, norm, skew
        dd = np.asarray(sel["per_fold_delta"], dtype=float)
        sr = float(dd.mean() / dd.std(ddof=1))
        g3, g4 = float(skew(dd)), float(kurtosis(dd, fisher=False))
        denom = 1 - g3 * sr + (g4 - 1) / 4.0 * sr ** 2
        dsr_b3 = (round(float(norm.cdf((sr - SLR.B3_FIELD_SR0) * np.sqrt(len(dd) - 1)
                                       / np.sqrt(denom))), 4) if denom > 0 else None)
    # the declared-field SR0 (the trial Sharpes select_pooled deflated against)
    inc_row = R1._row(incumbent, years)
    trial_srs = []
    for r in arms:
        dd_ = inc_row - R1._row(r, years)
        dd_ = dd_[np.isfinite(dd_)]
        if len(dd_) >= 3 and dd_.std(ddof=1) > 1e-12:
            trial_srs.append(float(dd_.mean() / dd_.std(ddof=1)))
    trial_srs = np.asarray(trial_srs)
    em = 0.5772156649015329
    from scipy.stats import norm as _norm
    sr0_declared = (float(trial_srs.std(ddof=1)) * ((1 - em) * _norm.ppf(1 - 1 / len(trial_srs))
                                                    + em * _norm.ppf(1 - 1 / (len(trial_srs) * np.e)))
                    if len(trial_srs) >= 2 and trial_srs.std(ddof=1) > 0 else 0.0)

    # ── the level gates on the winner ───────────────────────────────────────────────────────────
    level, rank_id = None, None
    if winner_rec is not None:
        rows_i, rows_w = incumbent["_rows"], winner_rec["_rows"]
        se = SLR.level_se(rows_i["y"], rows_i["point"], rows_i["pos"])
        level = SLR.level_gate(
            bias_inc=incumbent["bias_pooled_rows"], bias_win=winner_rec["bias_pooled_rows"], se=se,
            over_scale_loses=bool(anchors["over_scale"][LR.SELECTION_METRIC] > best_real),
            games_untouched=bool(np.array_equal(rows_i["g"], rows_w["g"])))
        level["se"] = se
        # ⭐ L5 is a PER-FOLD identity (k differs by fold, so a pooled read would compare rows
        #    corrected by different constants and report a phantom re-order — the first cut did).
        rank_id, per_fold_ids = {}, []
        for y_ in years:
            pf = winner_rec["_per_fold_rows"][y_]
            per_fold_ids.append(SLR.rank_identity(pf["point"], pf["adj"], pf["y"], pf["pos"]))
        for q in LR.RECALIBRATED_POSITIONS:
            got = [r_[q] for r_ in per_fold_ids if q in r_]
            rank_id[q] = {
                "folds": len(got),
                "min_within_position_rho": min(x["within_position_rho"] for x in got),
                "delta_rho_identical": all(x["delta_rho_identical"] for x in got),
                "order_identical": all(x["order_identical"] for x in got),
                "max_abs_delta_rho_change": max(abs(x["rho_vs_realized_winner"]
                                                    - x["rho_vs_realized_incumbent"]) for x in got)}

    gate = LR.pooled_ship(winner=sel["winner"], incumbent_metric=sel["incumbent_metric"],
                          ordering=sel["ordering"] or {"per_position": {}},
                          placement=sel["placement"], coverage=sel["coverage"],
                          pbo=sel["deflation"].get("pbo"), dsr=sel["deflation"].get("dsr"),
                          pvalue=sel["pvalue"])
    l5_ok = bool(rank_id) and all(v["delta_rho_identical"] and v["order_identical"]
                                  for v in rank_id.values())
    ship = bool(gate["ship"] and level and level["pass"] and l5_ok
                and premise["premise_confirmed"] and decomposition["tier"]["miss_is_rate"])
    sanity = {t: anchors[t][LR.SELECTION_METRIC] for t in ("zero_project", "pos_median", "wide_band")}
    verdict = {
        "ship": ship, "pooled_gate": gate, "level_gate_pass": bool(level and level["pass"]),
        "L5_rank_identity": l5_ok, "premise_confirmed": premise["premise_confirmed"],
        "miss_is_rate": decomposition["tier"]["miss_is_rate"],
        "sanity_degenerates_lose": all(v > best_real for v in sanity.values()),
        "oracle_respected": bool(anchors["oracle_perplayer"][LR.SELECTION_METRIC] <= best_real + 1e-9),
        "permutation_across_beaten": all(anchors[f"permuted_across@{f}"][LR.SELECTION_METRIC] > best_real
                                         for f in SLR.FORMS),
        "over_scale_loses": bool(anchors["over_scale"][LR.SELECTION_METRIC] > best_real),
        "wide_band_loses": bool(anchors["wide_band"][LR.SELECTION_METRIC] > best_real),
        "family_ceiling_respected_fixed_band": all(family_ok.values()),
        "ceilings_order_by_capacity": bool(order_ok),
        "rookie_leg_untouched": True,
    }

    # ── null classification (declared field, MH2.7) ─────────────────────────────────────────────
    from betting_ml.utils import cv_power as CP
    null = None
    if not ship:
        best = min((r for r in arms if r.get("recalibrates")), key=lambda r: r[LR.SELECTION_METRIC])
        dd = inc_row - R1._row(best, years)
        dd = dd[np.isfinite(dd)]
        sr = float(dd.mean() / dd.std(ddof=1)) if len(dd) >= 3 and dd.std(ddof=1) > 1e-12 else None
        v = CP.classify_null(metric=LR.SELECTION_METRIC, n_folds=len(years), n_arms=len(arms),
                             beats_foil=bool(dd.mean() > 0), observed_sr=sr,
                             var_trials_sr=(float(trial_srs.var(ddof=1)) if len(trial_srs) >= 2
                                            else None),
                             fold_wins=int((dd > 0).sum()), p_one_sided=sel.get("pvalue"),
                             declared_field_size=SLR.DECLARED_FIELD_SIZE)
        refused_by_constraint = (not (placements.get(best["label"], {}) or {}).get("holds_out")
                                 and best[LR.SELECTION_METRIC] < inc_m)
        refused_by_level = bool(gate["ship"] and level and not level["pass"])
        null = {"state": ("CONSTRAINT_REFUSED" if (refused_by_constraint or refused_by_level)
                          else v.state),
                "taxonomy_would_say": v.state, "remedy": getattr(v, "remedy", None),
                "detail": getattr(v, "detail", None),
                "field_remedy_admissible": (getattr(v, "detail", {}) or {}).get(
                    "field_remedy_admissible"),
                "refused_by_constraint": refused_by_constraint, "refused_by_level_gate": refused_by_level,
                "best_arm": best["label"], "observed_sr": sr}

    # ── serving-time fit + board diff (the runtime-gate proof, in memory) ───────────────────────
    serve_form = (sel["winner"] or {}).get("form")
    serve_form = serve_form if serve_form in SLR.FORMS else None
    serving = {}
    if serve_form:
        panel_all = VA.load_panel()
        params_2026 = SLR.fit_level_from_panel(panel_all, serve_form, 2026, tier_n, window=window)
        serving = {"form": serve_form, "params_2026": params_2026, "window": window,
                   "fitted_on": (f"panel target seasons < 2026, trailing window {window} "
                                 f"(tier top {tier_n}/season)"),
                   "diffs": []}
        for label, path in (("fastpath 2026 (nfl_fantasy_season_projections_2026)",
                             _ART / "nfl_fantasy_season_projections_2026.parquet"),
                            ("NF1.5 served 2026 (nf1_5_season_projections_2026)",
                             _ART / "nf1_5_season_projections_2026.parquet")):
            if path.exists():
                serving["diffs"].append(board_diff(pd.read_parquet(path), serve_form, params_2026,
                                                   label))
        # refit-vs-fixed agreement for the winner (the §0 (3) claim, MEASURED)
        w_fixed = fixed_arms[serve_form]
        serving["refit_vs_fixed"] = {
            "crps_refit": winner_rec[LR.SELECTION_METRIC], "crps_fixed": w_fixed[LR.SELECTION_METRIC],
            "cov80_refit": winner_rec["coverage80"], "cov80_fixed": w_fixed["coverage80"],
            "cov80_incumbent": incumbent["coverage80"],
            "band_fallback_rows_frac": round(refitter.fallback_rows / max(refitter.rows, 1), 5)}

    res = {
        "story": story, "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": model_version, "recalibrates": SLR.RECALIBRATES, "best_alpha": 0,
        "smoke": bool(args.smoke), "wall_time_s": None,
        "window": window, "window_derivation": window_derivation,
        "window_sensitivity": window_rows,
        "window_rows_by_fold": {y: fits[y]["_window_rows"] for y in years},
        "preregistration": reg, "step0_reproduction": proofs, "folds": years,
        "structurally_rookieless_boards": structural,
        "premise": premise, "decomposition": decomposition,
        "leaderboard": [
            {"arm": r["label"], "form": r.get("form"), "treatment": r.get("treatment"),
             "CRPS": r[LR.SELECTION_METRIC], "MAE": r["mae"], "bias (pooled rows)": r["bias_pooled_rows"]["pooled"],
             "cov80": r["coverage80"], "universe CRPS": r["universe_crps"],
             "universe bias": r["universe_bias"], "trial": r["label"] in [a["label"] for a in arms],
             "eligible": r["label"] in sel["eligible_labels"],
             **{f"bias_{q}": r["bias_pooled_rows"].get(q) for q in LR.RECALIBRATED_POSITIONS},
             **{f"cov_{q}": r.get(f"coverage80_{q}") for q in LR.RECALIBRATED_POSITIONS}}
            for r in sorted(arms + disclosures, key=lambda x: x[LR.SELECTION_METRIC])],
        "fitted_params_final_fold": {f: SLR.params_to_json(params_by[f][max(years)]) for f in SLR.FORMS},
        "fitted_params_by_fold": {f: {y: SLR.params_to_json(params_by[f][y]) for y in years}
                                  for f in SLR.FORMS},
        "anchor_table": [
            {"anchor": t, "role": R1._anchor_role(t),
             "expected": ("beats every real arm" if R1._anchor_role(t) == "ceiling"
                          else "loses to every real arm"),
             "CRPS": anchors[t][LR.SELECTION_METRIC], "MAE": anchors[t]["mae"],
             "bias": anchors[t]["bias_pooled_rows"]["pooled"], "cov80": anchors[t]["coverage80"],
             "behaves as expected": (bool(anchors[t][LR.SELECTION_METRIC] <= best_real + 1e-9)
                                     if R1._anchor_role(t) == "ceiling"
                                     else bool(anchors[t][LR.SELECTION_METRIC] > best_real))}
            for t in anchors if not t.startswith("over_scale@")],
        "lambda_sweep": sweep_rows,
        "predecessor": (None if window is None else {
            "story": SLR.STORY, "record": f"ablation_results/{_STEM}.md",
            "why_a_successor": ("NF-TR2's full-history mean-match passed every inherited gate and was "
                                "REFUSED by its own level gates (over-correction out of fold from a "
                                "non-stationary level — see season_level_recalibration.py, the "
                                "TR2b block); the successor is the same family with the trailing "
                                "window DERIVED from the tier's thinnest position, declared before "
                                "this run")}),
        "family_ceiling_check_fixed_band": {"per_form": family_ok, "ceilings": {
            f: {"ceiling_crps": ceilings[f][LR.SELECTION_METRIC],
                "arm_crps_fixed_band": fixed_arms[f][LR.SELECTION_METRIC]} for f in SLR.FORMS},
            "ceilings_order_by_capacity": bool(order_ok)},
        "constraint_table": [{"arm": lab, "holds out (C1∧C2∧C3)": v.get("holds_out"),
                              "C1 only": v.get("c1_only"), "C2 only": v.get("c2_only"),
                              "C3 only": v.get("c3_only"), "failing folds": v.get("failing_folds"),
                              "C2 active folds": v.get("c2_active_folds"),
                              "C2 structurally absent": v.get("c2_structurally_absent_folds")}
                             for lab, v in placements.items()],
        "selection": sel, "per_position": per_pos, "gate_table": gate,
        "deflation_disclosure": {
            "declared_field_size": SLR.DECLARED_FIELD_SIZE, "declared_field_source": SLR.DECLARED_FIELD_SOURCE,
            "n_trial_sharpes": int(len(trial_srs)), "trial_sharpes": [round(x, 4) for x in trial_srs],
            "sr0_declared_field": round(sr0_declared, 4),
            "dsr_declared_field": sel["deflation"].get("dsr"),
            "b3_field_sr0": SLR.B3_FIELD_SR0, "dsr_under_b3_field": dsr_b3,
            "b3_recorded": SLR.B3_RECORDED,
            "note": ("the SAME winner, the SAME folds: the declared-field DSR is the pre-registered "
                     "gate; the NF-B3-field DSR is the tax the winner would carry inside NF-B3's "
                     "11-arm heterogeneous field. Both are on this page so a narrower family "
                     "cannot launder a result — whether the brief's 3-trial family is admissible "
                     "is a fact about the brief (see declared_field_source), not about this run.")},
        "level_gate": level, "rank_identity": rank_id, "verdict": verdict, "null": null,
        "serving": serving,
        "registry_action": ({"registry": "betting_ml/models/model_family_registry.yaml (NF-G0)",
                             "action": ("STAGE a challenger — level_model_version → "
                                        f"{model_version} (operator, post-merge, via the NF-G0 "
                                        "publish flow)") if ship else "NONE — nothing was promoted"}),
    }
    res["wall_time_s"] = round(time.time() - t0, 1)
    if not args.no_report:
        jp, mp = write_report(res, stem)
        log.info("wrote %s and %s", jp, mp)
    log.info("VERDICT: %s · winner %s · CRPS %s vs %s · DSR(declared) %s · DSR(B3 field) %s · %.1fs",
             "SHIP" if ship else f"NULL ({(null or {}).get('state')})",
             (sel["winner"] or {}).get("label"), (sel["winner"] or {}).get("metric"), inc_m,
             sel["deflation"].get("dsr"), dsr_b3, res["wall_time_s"])
    return 0


# ══════════════════════════════════════════════════════════════════════════════════════════════
def _strip(o):
    if isinstance(o, dict):
        return {str(k): _strip(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_strip(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def write_report(res: dict, stem: str = _STEM) -> tuple[Path, Path]:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    jp = _REPORT_DIR / f"{stem}.json"
    mp = _REPORT_DIR / f"{stem}.md"
    clean = _strip(res)
    jp.write_text(json.dumps(clean, indent=1, default=str))
    mp.write_text(_md(clean))
    return jp, mp


def _md(r: dict) -> str:
    sel, v, lv = r["selection"], r["verdict"], r.get("level_gate") or {}
    dec = r["decomposition"]["tier"]
    w = sel.get("winner") or {}
    L = []
    L.append(f"# {r['story']} — season-projection LEVEL recalibration (draft-board credibility)"
             + (f" · trailing window {r['window']} seasons" if r.get("window") else
                " · full-history mean-match"))
    L.append(f"_generated {r['generated_at']}_ · `best_alpha = 0` · model `{r['model_version']}` · "
             f"recalibrates `{r['recalibrates']}` · wall {r['wall_time_s']}s"
             + (" · ⚠️ SMOKE" if r.get("smoke") else ""))
    L.append(f"## Verdict: **{'SHIP' if v['ship'] else 'RECORDED NULL — ' + str((r.get('null') or {}).get('state'))}**")
    L.append(f"Winner `{w.get('label')}` · tier CRPS **{w.get('metric')}** vs incumbent "
             f"{sel['incumbent_metric']} · pooled tier bias {r['leaderboard'][0].get('bias (pooled rows)') if False else (lv.get('L1_detail') or {}).get('winner')} "
             f"vs {(lv.get('L1_detail') or {}).get('incumbent')} · PBO(elig) {sel['deflation'].get('pbo')} · "
             f"DSR(declared 3-trial field) **{sel['deflation'].get('dsr')}** · "
             f"DSR under NF-B3's field {r['deflation_disclosure'].get('dsr_under_b3_field')} · "
             f"p {sel.get('pvalue')}")
    L.append("\n## 0. Pre-registration + provenance")
    reg = r["preregistration"]
    L.append(f"- Declared field: **{reg['declared_field_size']} trials** — {reg['declared_field_source']}")
    L.append(f"- Forms `{reg['forms']}` + no-op · estimator `{reg['estimator']}` · λ fixed {reg['lambda']} · "
             f"band treatment PRIMARY `{reg['band_treatment']}` (disclosed: {reg['band_treatments_disclosed']}) · "
             f"space `{reg['space']}` · tier top {reg['tier_n']}/season by the INCUMBENT anchor · folds {reg['fold_seasons'][0]}–{reg['fold_seasons'][-1]}")
    p0 = r["step0_reproduction"]
    L.append(f"- Served band held through the model path: universe IS80 {p0['universe_is80']} (Δ {p0['universe_is80_delta_pct']}%), "
             f"tier cov 2019–25 {p0['served_tier_coverage_2019_2025']}. Structurally rookie-less boards: {r['structurally_rookieless_boards']}.")
    L.append("\n## 1. Decomposition — availability vs per-game rate (tier, pooled over the 13 folds)")
    rows = [{"position": q, **{k: (round(vv, 3) if isinstance(vv, float) else vv) for k, vv in d_.items()}}
            for q, d_ in dec["per_position"].items()] + [{"position": "POOLED", **{k: (round(vv, 3) if isinstance(vv, float) else vv) for k, vv in dec["pooled"].items()}}]
    L.append(_md_table(rows, ["position", "n", "bias", "availability_part", "rate_part", "our_over_actual",
                              "games_ratio", "rate_ratio_pooled", "mean_match_k", "zero_outcome_frac"]))
    L.append(f"\nidentity holds: {dec['identity_holds']} · the miss is the RATE: **{dec['miss_is_rate']}** "
             f"(availability {dec['pooled']['availability_part']:+.2f} vs rate {dec['pooled']['rate_part']:+.2f}). "
             f"Universe pooled bias {r['decomposition']['universe']['pooled']['bias']:+.2f}.")
    pr = r["premise"]["draftable_tier_incumbent_anchor"]
    L.append(f"Premise (NF-RECAL1's reading, reproduced): tier bias {pr['mean_bias']} (n {pr['n']}), universe "
             f"{r['premise']['universe']['mean_bias']} — premise confirmed: {r['premise']['premise_confirmed']}.")
    L.append("\n## 2. The field + disclosures")
    L.append(_md_table(r["leaderboard"], ["arm", "treatment", "trial", "eligible", "CRPS", "MAE",
                                          "bias (pooled rows)", "bias_QB", "bias_RB", "bias_WR", "bias_TE",
                                          "cov80", "universe CRPS", "universe bias"]))
    L.append(f"\nFitted params (final fold {r['folds'][-1]}): `{r['fitted_params_final_fold']}`")
    L.append("\n### Anchors (two-sided, scored every run, PRIMARY treatment; ceilings under the FIXED band)")
    L.append(_md_table(r["anchor_table"]))
    fc = r["family_ceiling_check_fixed_band"]
    L.append(f"\nFamily ceiling (matched FIXED-band treatment): {fc['per_form']} · ceilings order by capacity: {fc['ceilings_order_by_capacity']} · {fc['ceilings']}")
    L.append("\n### λ-sweep of the mean-match (the interior-optimum question, MEASURED — anchors, never selected on)")
    L.append(_md_table(r["lambda_sweep"]))
    L.append("\n### Window sensitivity (anchors, never trials) — the registered window is DERIVED, not tuned")
    L.append(f"derivation: `{r.get('window_derivation')}`")
    L.append(_md_table(r.get("window_sensitivity") or []))
    if r.get("predecessor"):
        L.append(f"\nPredecessor: `{r['predecessor']}`")
    L.append("\n## 3. Constraints (out-of-sample, every fold)")
    L.append(_md_table(r["constraint_table"]))
    L.append("\n## 4. Deflation over the DECLARED field")
    dd = r["deflation_disclosure"]
    L.append(_md_table([{k: vv for k, vv in dd.items() if k not in ("note", "b3_recorded", "declared_field_source")}]))
    L.append(f"\n{dd['note']}\n\nNF-B3 recorded: {dd['b3_recorded']}")
    L.append("\n### Gate table (pooled framing)")
    L.append(_md_table([r["gate_table"]]))
    L.append("\n### Per-position disclosure (computed, never selected on)")
    pp = r["per_position"]
    if isinstance(pp, dict) and pp.get("rows"):
        L.append(_md_table(pp["rows"]))
    else:
        L.append(f"```\n{json.dumps(pp, indent=1, default=str)[:3000]}\n```")
    L.append("\n## 5. Level gates (L1–L5)")
    L.append(f"```\n{json.dumps(lv, indent=1, default=str)}\n```")
    L.append(f"\nL5 rank identity: `{json.dumps(r.get('rank_identity'), indent=1, default=str)}`")
    L.append("\n## 6. Verdict flags")
    L.append(_md_table([{k: vv for k, vv in v.items() if k != 'pooled_gate'}]))
    if r.get("null"):
        L.append("\n### Null classification (declared field)")
        L.append(f"```\n{json.dumps(r['null'], indent=1, default=str)}\n```")
    L.append("\n## 7. Serving — the fit that would ship + the before/after board diff")
    if r.get("serving"):
        s = r["serving"]
        L.append(f"form `{s['form']}` · params 2026 `{s['params_2026']}` · {s['fitted_on']}")
        L.append(f"refit-vs-fixed band agreement (winner): {s.get('refit_vs_fixed')}")
        for dfx in s.get("diffs", []):
            L.append(f"\n**{dfx['board']}** — n {dfx['n']} · veterans {dfx['n_veterans']} · rookies untouched {dfx['rookies_untouched']} · top-24 membership stable {dfx['top24_membership_stable']}")
            L.append(_md_table(dfx["per_position"]))
    L.append(f"\n## 8. Registry action\n{r['registry_action']}")
    L.append("\n## 9. Scope + serving\n- ⛔ Rookie leg out of scope (NF-D21 CLOSED; inherited).\n- ⛔ NF1.5's ORDERING layer untouched — levels only.\n"
             "- 🔒 CODE-READY, deploy-HELD: the board rebuild + republish + `run_interval_revalidation` re-run are POST-MERGE OPERATOR steps.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
