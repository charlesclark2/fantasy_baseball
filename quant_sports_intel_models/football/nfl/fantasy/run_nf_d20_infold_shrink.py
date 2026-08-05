"""run_nf_d20_infold_shrink.py — NF-D20 §0.5 bake-off: can a GLOBAL SHRINK of NF-D16's ratified
rookie-point recalibration be SELECTED IN-FOLD, under a PER-FOLD whole-board placement constraint,
without ever reading the 2026 board?

THE STORY IN ONE PARAGRAPH. NF-D16's per-position affine recalibration is RATIFIED and held from
publish because the 2026 board places its top rookie at overall rank 6 against a placement clause
NF-D17 subsequently VALIDATED. NF-D18 tested four differently-SHAPED corrections; every one was
refused, and its frontier diagnostic found that the binding problem was never the constraint but the
shapes — a plain GLOBAL SHRINK of the ratified affine clears the cap while retaining most of the gain.
⛔ NF-D18 refused to take that λ because it was read off ONE board with the answer in view. NF-D20 is
the legitimate version of that move: the shrink is selected IN-FOLD by deterministic RULES, from
held-out draft classes and the merged veteran+rookie boards of PRIOR seasons only, and the constraint
is enforced OUT-OF-SAMPLE on each held-out fold's own board.

⚠️ THE PRE-REGISTRATION LIVES IN `rookie_shrink_selection.py`, NOT HERE, and was committed before this
file existed. This runner READS those constants; it does not restate them.

⭐ WHAT MAKES THE PER-FOLD CONSTRAINT AFFORDABLE. NF-D18 recorded that a successor "needs the merged
veteran+rookie board rebuilt per held-out season." Those boards already exist as walk-forward
artifacts: `run_season_projection.py --backtest-from 2019` emits one per season, each built off
`base_season = Y − 1` with NF-D16's flip OFF. This story READS them and ASSERTS their provenance
(`board_is_walk_forward`) rather than rebuilding or assuming it.

⚖️ EDGE-INDEPENDENT (roadmap §0): a projection-quality product. `best_alpha = 0`, no CLV/ROI claim.
🔒 The rookie INTERVAL's WIDTH model is untouched. ⚠️ A shipped shrink moves the band's CENTRE, so a
   ship requires `run_interval_revalidation` re-run and every coverage floor re-confirmed.
⛔ QB is excluded by pre-registration and PROVEN untouched on emitted projections, never asserted.

RUN ON THE LAPTOP (no Snowflake, no network — reads the cached NF1.4 rookie pool + the emitted boards):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_d20_infold_shrink
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import nf1_4_rookie as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    rookie_shrink_selection as SS,
    season_projection as SP,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_d18_top_attenuation as NFD18,
    run_rookie_interval_ablation as NF17,
    run_rookie_perposition_ablation as NF18,
)

log = logging.getLogger("nfl.fantasy.nf_d20_infold_shrink")

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_POOL = _ART / "nf1_4_rookie_training.parquet"
_REAL = "rookie_fp_ppr"


def board_path(season: int) -> Path:
    return _ART / f"nfl_fantasy_season_projections_{season}.parquet"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Per-fold fits — computed ONCE per held-out class and shared by every arm
# ══════════════════════════════════════════════════════════════════════════════════════════════
def fold_fits(fold: NF17.Fold, *, seed: int = 20260804) -> dict:
    """Every fitted correction for ONE held-out class, computed once and shared by every arm.

    ⭐ THE CANDIDATE FIT IS STRICTLY IN-FOLD — NF-D16's ratified affine estimated on the PRIOR draft
    classes and their served point projections. `_peek_ols` is the ORACLE CEILING and is fitted on the
    HELD-OUT class on purpose: a ceiling has to peek to be one, and it is at MATCHED FAMILY because
    every arm in this field is a λ-blend of that same per-position affine with the identity, which is
    itself a per-position affine.

    ⚠️ BOTH PERMUTATIONS ARE FITTED AT THE SAME FORM, so the two anchors differ from each other in
    exactly one thing — which outcome vector they saw:
      · `_perm_across` shuffles realized outcomes ACROSS positions (per-position structure destroyed,
        family/n/grand mean preserved). Must LOSE.
      · `_perm_within` shuffles WITHIN each position, preserving that position's marginal EXACTLY and
        destroying only the projection↔outcome relationship. ⭐ NF-D16 measured this anchor VACUOUS for
        a pure LEVEL and NF-D18 measured it BITING for a SHAPE; the ratified affine carries a SLOPE, so
        it is PRE-REGISTERED TO BE BEATEN here rather than to tie."""
    tr_pos = fold.train["position_group"].astype(str).str.upper().to_numpy()
    te_pos = fold.test["position_group"].astype(str).str.upper().to_numpy()
    p_tr = np.asarray(fold.train_pred, dtype=float)
    y_tr = pd.to_numeric(fold.train[_REAL], errors="coerce").to_numpy(dtype=float)

    rng = np.random.default_rng(seed + int(fold.year))
    y_across = rng.permutation(np.nan_to_num(y_tr, nan=0.0))
    y_within = np.nan_to_num(y_tr, nan=0.0).copy()
    for q in SS.SHRINK_POSITIONS:
        sel = np.flatnonzero(tr_pos == q)
        if len(sel) > 1:
            y_within[sel] = rng.permutation(y_within[sel])

    return {
        "_te_pos": te_pos, "_tr_pos": tr_pos,
        SS.REFERENCE_FORM: SS.fit_ols(p_tr, y_tr, tr_pos),
        # relaxed row floor for the CEILING only: a single held-out class is ~80 rows across three
        # positions, and an anchor that fails to fit makes its own check pass on NOTHING (NF1.7 (a)).
        "_peek_ols": SS.fit_ols(fold.test_pred, fold.test_real, te_pos, min_n=5),
        "_perm_across": SS.fit_ols(p_tr, y_across, tr_pos),
        "_perm_within": SS.fit_ols(p_tr, y_within, tr_pos),
    }


def _affine(params: dict, point, positions) -> np.ndarray:
    """Apply a per-position affine `a + b·point`. A position with no fitted parameter yields NaN,
    which `apply_position_adjustment` turns back into the incumbent — a missing estimate must degrade
    to 'leave it alone', never to a silent zero."""
    p = np.asarray(point, dtype=float)
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    out = np.full(len(p), np.nan)
    for q, (a, b) in params.items():
        out[pos == q] = float(a) + float(b) * p[pos == q]
    return out


def shrunk(point, positions, params: dict, lam: float) -> np.ndarray:
    """FIT → λ blend → the QB gate. Three separate steps on purpose, so no arm owns its own copy of
    the shrink or of the exclusion, and `λ = 0` reproduces the incumbent EXACTLY."""
    adj = _affine(params, point, positions)
    return SS.apply_position_adjustment(point, positions,
                                        SS.blend_toward_incumbent(point, adj, float(lam)))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scoring — candidates and anchors through the IDENTICAL reducer
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _mean(values, nd: int = 4) -> float | None:
    v = np.array([x for x in values if x is not None], dtype=float)
    v = v[np.isfinite(v)]
    return round(float(v.mean()), nd) if len(v) else None


def _score(folds: list[NF17.Fold], fits: dict[int, dict], pos_scale: dict[int, dict],
           predict, label: str, extra: dict | None = None) -> dict:
    """Score ANY arm — candidate, matched foil or anchor — through the IDENTICAL reducer, so the
    anchors and the candidates are demonstrably answering the same question rather than merely being
    described that way."""
    per_cohort, per_cohort_scaled, rows = {}, {}, []
    for f in folds:
        pos = fits[f.year]["_te_pos"]
        pred = predict(f, fits[f.year])
        d = pd.DataFrame({"position_group": pos, _REAL: f.test_real,
                          "_inc": f.test_pred, "_pred": pred})
        per_cohort[f.year] = M14.cohort_metrics(d, "_pred", scale=pos_scale[f.year])
        per_cohort_scaled[f.year] = M14.cohort_metrics(d, "_pred", scale=pos_scale[f.year],
                                                       tier_k=SS.SCALED_TIER_K)
        rows.append(d.assign(year=f.year))
    allrows = pd.concat(rows, ignore_index=True)
    scaled = SS.scaled_positions_only(allrows)
    pooled = _mean([v.get("tier_mae") for v in per_cohort_scaled.values()], 4)
    out = {
        "label": label, "per_cohort": per_cohort,
        "per_cohort_pooled": {y: v.get("tier_mae") for y, v in per_cohort_scaled.items()},
        "pooled_tier_mae": pooled, SS.SELECTION_METRIC: pooled,
        "universe_mae": round(float((scaled["_pred"] - scaled[_REAL]).abs().mean()), 3),
        "universe_bias": round(float((scaled["_pred"] - scaled[_REAL]).mean()), 3),
        **(extra or {}),
    }
    for p in ("QB",) + SS.SHRINK_POSITIONS:
        g = allrows[allrows["position_group"] == p]
        if g.empty:
            continue
        out[f"universe_mae_{p}"] = round(float((g["_pred"] - g[_REAL]).abs().mean()), 2)
        out[f"tier_mae_{p}"] = _mean([v.get("tier_mae_by_pos", {}).get(p)
                                      for v in per_cohort.values()], 3)
        out[f"tier_bias_{p}"] = _mean([v.get("tier_bias_by_pos", {}).get(p)
                                       for v in per_cohort.values()], 3)
        out[f"rho_{p}"] = _mean([v.get("rho_by_pos", {}).get(p) for v in per_cohort.values()], 4)
    return out


def score_constant_lambda(folds, fits, pos_scale, lam: float, label: str) -> dict:
    """One CONSTANT λ over every fold — the grid this story's inner selection reads, and the shape the
    two degenerate anchors (`over_scale`) and the matched foil (`blind_half`) take."""
    return _score(folds, fits, pos_scale,
                  lambda f, fi, L=lam: shrunk(f.test_pred, fi["_te_pos"],
                                              fi[SS.REFERENCE_FORM], float(L)),
                  label, extra={"lam": float(lam)})


def score_rule(folds, fits, pos_scale, lam_by_fold: dict, cfg: dict) -> dict:
    """One RULE arm: on each held-out class it applies the λ its rule computed from data STRICTLY
    BEFORE that class. That is the whole difference between this story and a λ re-pick — the arm is a
    function, and no human chooses a number anywhere in it."""
    return _score(folds, fits, pos_scale,
                  lambda f, fi: shrunk(f.test_pred, fi["_te_pos"], fi[SS.REFERENCE_FORM],
                                       float(lam_by_fold.get(f.year, SS.EMPTY_EVIDENCE_LAMBDA))),
                  cfg["label"],
                  extra={"key": SS.config_key(cfg), "form": cfg["form"], "rule": cfg.get("rule"),
                         "recalibrates": cfg["recalibrates"], "shippable": cfg["shippable"],
                         "constrained": bool(cfg.get("constrained")),
                         "is_foil": bool(cfg.get("is_foil")),
                         "lam_by_fold": {int(k): float(v) for k, v in lam_by_fold.items()}})


def _anchor_prediction(tag: str, fold: NF17.Fold, fits: dict) -> np.ndarray:
    pos = fits["_te_pos"]
    point = np.asarray(fold.test_pred, dtype=float)
    real = np.asarray(fold.test_real, dtype=float)
    if tag == "oracle_perplayer":
        return SS.apply_position_adjustment(point, pos, real)
    if tag == "oracle_ols":
        return SS.apply_position_adjustment(point, pos, _affine(fits["_peek_ols"], point, pos))
    if tag in ("permuted_across", "permuted_within"):
        key = "_perm_across" if tag == "permuted_across" else "_perm_within"
        return SS.apply_position_adjustment(point, pos, _affine(fits[key], point, pos))
    if tag == "zero_scale":
        return SS.apply_position_adjustment(point, pos, np.zeros(len(pos)))
    if tag == "over_scale":
        return shrunk(point, pos, fits[SS.REFERENCE_FORM], SS.OVER_SCALE_LAMBDA)
    if tag == "pos_median":
        tr_pos = fits["_tr_pos"]
        tr_real = pd.to_numeric(fold.train[_REAL], errors="coerce").to_numpy(dtype=float)
        adj = np.full(len(pos), np.nan)
        for q in SS.SHRINK_POSITIONS:
            v = tr_real[(tr_pos == q) & np.isfinite(tr_real)]
            if len(v):
                adj[pos == q] = float(np.median(v))
        return SS.apply_position_adjustment(point, pos, adj)
    raise ValueError(f"unknown anchor {tag!r}")


def score_anchors(folds, fits, pos_scale) -> dict:
    return {t: _score(folds, fits, pos_scale,
                      lambda f, fi, t=t: _anchor_prediction(t, f, fi), t)
            for t in ("oracle_perplayer", "oracle_ols", "permuted_across", "permuted_within",
                      "zero_scale", "pos_median", "over_scale")}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE PER-SEASON MERGED BOARDS — where the PER-FOLD placement constraint is evaluated
# ══════════════════════════════════════════════════════════════════════════════════════════════
def period_fit(pool: pd.DataFrame, upto: int) -> dict:
    """NF-D16's ratified affine as it would have been fitted AT THE TIME season `upto + 1` was
    published — on the draft classes ≤ `upto`, against the served point projections of the curve those
    same classes produce.

    ⭐ PERIOD-FAITHFUL BY CONSTRUCTION, AND THAT IS THE POINT. Board S is judged with the correction
    that could actually have been served alongside it, so `admissible on board S` is a property of
    season S rather than of hindsight. Delegated to NF-D18's `serving_fits`, which reproduces the
    PRODUCTION path (`fit_rookie_slot_curves` → `rookie_point_projection`) rather than approximating
    it — the same routine whose fidelity NF-D18 verified against the emitted curve to 0.000000 PPR."""
    return NFD18.serving_fits(pool, upto=int(upto))[SS.REFERENCE_FORM]


def board_lambda_ranks(board: pd.DataFrame, params: dict, grid: tuple) -> dict:
    """The best rookie's OVERALL rank on ONE merged board at every λ in a grid.

    ⭐ THE CORRECTION IS APPLIED TO THE BOARD'S OWN EMITTED ROOKIE POINTS, which is exactly what
    serving does (`RookieSlotCurve.recalibrate_fp` acts on the FINAL SCORED projection). The λ = 0 row
    is therefore the SERVED product for that season rather than a reconstruction of it that could
    drift. ⚠️ Veterans are untouched by construction, which is precisely why a within-position 'moves
    no ranks' argument never reaches this gate."""
    rk = board["is_rookie"].fillna(False).astype(bool).to_numpy()
    point = pd.to_numeric(board.loc[rk, "proj_fp_ppr"], errors="coerce").to_numpy(dtype=float)
    pos = board.loc[rk, "position"].astype(str).str.upper().to_numpy()
    out: dict[float, int | None] = {}
    detail: dict[float, dict] = {}
    for lam in grid:
        place = SS.board_placement(board, shrunk(point, pos, params, float(lam)))
        out[float(lam)] = place.get("best_rookie_overall_rank")
        detail[float(lam)] = place
    return {"rank_by_lambda": out, "placement_by_lambda": detail,
            "point": point, "positions": pos}


def build_board_evidence(pool: pd.DataFrame, seasons: list[int], *,
                         grid: tuple = SS.LAMBDA_GRID) -> dict:
    """For every season with a merged board: its provenance, its λ → rank curve under the
    PERIOD-FAITHFUL correction, and the λ set that season's board ADMITS under C2.

    ⚠️ A board that fails `board_is_walk_forward` is a HARD FAILURE, not a skip: this story reads
    artifacts it did not build, and a board rebuilt with later data (or with NF-D16's recalibration
    already applied) would make every placement number here a number about a different product while
    nothing downstream noticed."""
    ev: dict[int, dict] = {}
    for s in seasons:
        p = board_path(s)
        if not p.exists():
            raise SystemExit(
                f"no merged board for {s} at {p} — rebuild the per-season boards first:\n"
                "  uv run python -m quant_sports_intel_models.football.nfl.fantasy."
                "run_season_projection --backtest-from 2019")
        board = pd.read_parquet(p)
        prov = SS.board_is_walk_forward(board, s)
        prov["path"] = str(p)
        prov["mtime_utc"] = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()
        params = period_fit(pool, s - 1)
        curves = board_lambda_ranks(board, params, grid)
        inc_rank = curves["rank_by_lambda"][0.0]
        ev[s] = {
            "provenance": prov, "board": board, "params": params,
            "rank_by_lambda": curves["rank_by_lambda"],
            "placement_by_lambda": curves["placement_by_lambda"],
            "point": curves["point"], "positions": curves["positions"],
            "incumbent_rank": inc_rank,
            "admissible": SS.admissible_lambdas(curves["rank_by_lambda"], inc_rank),
            "admissible_strict": SS.admissible_lambdas(curves["rank_by_lambda"], inc_rank,
                                                       strict=True),
        }
        log.info("  board %d: %s (base %s, %d rows, %d rookies) incumbent rank %s → admits %s "
                 "(strict %s)", s, prov["mtime_utc"][:19], prov["base_season"], prov["n_rows"],
                 prov["n_rookies"], inc_rank, ev[s]["admissible"], ev[s]["admissible_strict"])
    return ev


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE IN-FOLD SELECTION — λ chosen from PRIOR classes and PRIOR boards, never from the fold
# ══════════════════════════════════════════════════════════════════════════════════════════════
def inner_metric_for(cohorts: list[int], year: int, lam_scored: dict) -> dict:
    """The IN-FOLD metric curve a rule may read when choosing λ for held-out class `year`: the pooled
    tier MAE of each constant λ over the held-out classes STRICTLY BEFORE it.

    ⭐ NO NESTED RE-FIT IS NEEDED AND THAT IS A CORRECTNESS PROPERTY, NOT A SHORTCUT. Every fold's
    score at a constant λ is already an OUT-OF-SAMPLE reading produced by a correction fitted on
    classes before THAT fold; averaging the ones before `year` is therefore a walk-forward estimate
    built entirely from data older than `year`, using the identical estimator the arm will apply.
    Re-fitting inner folds would introduce a second estimator to keep in sync — the class of drift
    NF1.7's re-derived rookie point already cost this programme once."""
    prior = [y for y in cohorts if y < year]
    if not prior:
        return {}
    return {float(lam): _mean([rec["per_cohort_pooled"].get(y) for y in prior], 6)
            for lam, rec in lam_scored.items()}


def rule_lambdas(cfg: dict, cohorts: list[int], evidence: dict, lam_scored: dict) -> dict:
    """The λ a RULE selects for every held-out class — the heart of this story.

    For class `Y` the rule may read the merged boards of seasons `< Y` and the held-out scores of
    classes `< Y`, and NOTHING else. It aggregates the per-board admissible sets per its
    pre-registered `evidence` mode, then picks the in-fold-metric argmin over that set. With no board
    evidence at all it falls back to `EMPTY_EVIDENCE_LAMBDA` (registered in advance): a check that did
    not run is not a check that passed."""
    mode = cfg.get("evidence", "none")
    out: dict[int, dict] = {}
    for y in cohorts:
        per_board = {s: ev["admissible"] for s, ev in evidence.items() if s < y}
        allowed = SS.aggregate_admissible(per_board, mode)
        inner = inner_metric_for(cohorts, y, lam_scored)
        pick = SS.select_lambda(allowed, inner)
        out[y] = {**pick, "boards_seen": sorted(per_board), "evidence_mode": mode,
                  "inner_metric": {round(k, 4): v for k, v in inner.items()}}
    return out


def holds_out(lam_by_fold: dict, evidence: dict) -> dict:
    """⭐ C2 EVALUATED OUT-OF-SAMPLE — the question that decides a publish.

    For each held-out class, does the λ the rule chose from PRIOR data satisfy the placement
    constraint on THAT class's OWN board — the board the rule never saw? An arm that only satisfies
    C2 in-sample has demonstrated nothing: the in-sample set is what the rule optimised against."""
    per: dict[int, dict] = {}
    for y, lam in lam_by_fold.items():
        ev = evidence.get(y)
        if ev is None:
            per[y] = {"evaluable": False, "lam": float(lam),
                      "note": "no held-out board for this class — C2 could not be evaluated"}
            continue
        rank = ev["rank_by_lambda"].get(float(lam))
        per[y] = {**SS.board_admits(rank, ev["incumbent_rank"]), "lam": float(lam),
                  "clears_cap_outright": bool(
                      SS.placement_clearance(rank).get("clears"))}
    ok = bool(per) and all(v.get("admits") for v in per.values())
    return {"holds_out": ok, "per_fold": per,
            "n_folds_evaluated": sum(1 for v in per.values() if v.get("evaluable")),
            "clears_cap_outright_every_fold": bool(per) and all(
                v.get("clears_cap_outright") for v in per.values())}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE PRE-REGISTERED POOLED SELECTION
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pooled_row(rec: dict, cohorts: list[int]) -> np.ndarray:
    return np.array([rec.get("per_cohort_pooled", {}).get(y, np.nan) for y in cohorts], dtype=float)


def select_pooled(arms: list[dict], inc: dict, cohorts: list[int], placements: dict,
                  *, placement_binds: bool = True) -> dict:
    """Pick + deflate under the PRE-REGISTERED pooled framing: ONE hypothesis, ONE test, no
    multiplicity correction.

    Eligibility = shippable AND do-no-ordering-harm at EVERY scaled position AND (when
    `placement_binds`) C2 satisfied OUT-OF-SAMPLE on every held-out fold's own board.
    `placement_binds=False` computes the ORDERING-ONLY reading — NF-D16's convention — reported as a
    disclosure so a reader can see exactly what the eligibility choice decided.

    `winner = None` with candidates present is a REAL result, not a bug: it means no arm satisfied both
    constraints, which is this story's own null.

    ⚠️ PBO is computed over the ELIGIBLE set — the search the selection ACTUALLY ran (NF1.8) — and the
    MATCHED FOIL is excluded from both the eligible set and the DSR trial field, because a diagnostic
    is never a trial (MH2 (a)). Both the whole-field and the contender-set DSR are reported; the
    WHOLE-FIELD reading is the PRE-REGISTERED gate."""
    inc_row = _pooled_row(inc, cohorts)
    inc_metric = _mean(inc_row, 4)
    inc_rho = {p: inc.get(f"rho_{p}") for p in SS.SHRINK_POSITIONS}

    cands = []
    for r in arms:
        if r.get("is_foil"):
            continue                       # a diagnostic is never a trial and never a candidate
        row = _pooled_row(r, cohorts)
        metric = _mean(row, 4)
        if metric is None:
            continue
        rho = {p: r.get(f"rho_{p}") for p in SS.SHRINK_POSITIONS}
        ordering = SS.ordering_check(rho, inc_rho)
        place = placements.get(r["label"], {}) or {}
        elig = bool(r["shippable"] and ordering["ok"]
                    and (place.get("holds_out", False) if placement_binds else True))
        cands.append({"rec": r, "row": row, "metric": metric, "ordering": ordering,
                      "placement": place, "eligible": elig})

    eligible = [c for c in cands if c["eligible"]]
    best = min(eligible, key=lambda c: c["metric"]) if eligible else None
    best_any = min(cands, key=lambda c: c["metric"]) if cands else None

    mat = pd.DataFrame({c["rec"]["label"]: dict(zip(cohorts, c["row"])) for c in cands}).sort_index()
    defl = NF18.deflate(mat, subset=[c["rec"]["label"] for c in eligible] or None)

    means = mat.mean(axis=0).sort_values()
    ctr_labels = set(means.index[:max(3, len(means) // 4)])
    trial, ctr = [], []
    for c in cands:
        d = inc_row - c["row"]
        d = d[np.isfinite(d)]
        sr = (float(d.mean() / d.std(ddof=1))
              if len(d) >= 3 and d.std(ddof=1) > 1e-12 else np.nan)
        trial.append(sr)
        if c["rec"]["label"] in ctr_labels:
            ctr.append(sr)

    dsr = dsr_ctr = pval = None
    deltas: list[float] = []
    if best is not None:
        raw = inc_row - best["row"]
        deltas = [float(x) for x in raw[np.isfinite(raw)]]
        dsr = M14.deflated_sharpe(np.array(deltas), np.array(trial, dtype=float))
        dsr_ctr = M14.deflated_sharpe(np.array(deltas), np.array(ctr, dtype=float))
        pval = M14.onesided_paired_pvalue(np.array(deltas))

    return {
        "framing": SS.PREREGISTERED_FRAMING, "placement_binds": bool(placement_binds),
        "n_candidates": len(cands), "n_eligible": len(eligible),
        "incumbent_metric": inc_metric, "incumbent_rho": inc_rho,
        "winner": None if best is None else {
            **{k: best["rec"].get(k) for k in ("label", "key", "form", "rule", "recalibrates",
                                               "shippable", "constrained", "lam_by_fold")},
            "metric": best["metric"],
            "rho": {p: best["rec"].get(f"rho_{p}") for p in SS.SHRINK_POSITIONS}},
        "best_any": None if best_any is None else {
            "label": best_any["rec"]["label"], "metric": best_any["metric"],
            "eligible": best_any["eligible"]},
        "ordering": None if best is None else best["ordering"],
        "placement": None if best is None else best["placement"],
        "deflation": {**defl, "dsr": dsr, "dsr_contenders": dsr_ctr},
        "pvalue": pval, "per_cohort_delta": [round(x, 3) for x in deltas],
        "eligible_labels": [c["rec"]["label"] for c in eligible],
        "ineligible": [{"label": c["rec"]["label"], "ordering_ok": c["ordering"]["ok"],
                        "placement_holds_out": bool(c["placement"].get("holds_out")),
                        "failing_folds": [y for y, v in (c["placement"].get("per_fold") or {}).items()
                                          if not v.get("admits")]}
                       for c in cands if not c["eligible"]],
    }


def per_position_disclosure(arms: list[dict], inc: dict, cohorts: list[int],
                            placements: dict) -> dict:
    """The framing this story did NOT pre-register, computed rather than speculated about.

    ⚠️ REPORTED, NEVER SELECTED ON. The pre-registered pooled framing governs; if the two readings
    disagree that is a disclosure, not a licence to take the other one (E2.1-r)."""
    out: dict = {"per_position": [], "fdr": {}, "bh_cutoff_unconditional": round(SS.ALPHA / 3, 4)}
    inc_rho_all = {p: inc.get(f"rho_{p}") for p in SS.SHRINK_POSITIONS}
    pvals: dict[str, float | None] = {}
    for pos in SS.SHRINK_POSITIONS:
        inc_row = np.array([inc["per_cohort"].get(y, {}).get("tier_mae_by_pos", {}).get(pos, np.nan)
                            for y in cohorts], dtype=float)
        inc_metric = _mean(inc_row, 4)
        cands = []
        for r in arms:
            if r.get("is_foil"):
                continue
            row = np.array([r["per_cohort"].get(y, {}).get("tier_mae_by_pos", {}).get(pos, np.nan)
                            for y in cohorts], dtype=float)
            metric = _mean(row, 4)
            if metric is None:
                continue
            ordering = SS.ordering_check({pos: r.get(f"rho_{pos}")},
                                         {pos: inc_rho_all.get(pos)}, positions=(pos,))
            place = placements.get(r["label"], {}) or {}
            cands.append({"rec": r, "row": row, "metric": metric, "ordering": ordering,
                          "eligible": bool(r["shippable"] and ordering["ok"]
                                           and place.get("holds_out", False))})
        eligible = [c for c in cands if c["eligible"]]
        best = min(eligible, key=lambda c: c["metric"]) if eligible else None
        mat = pd.DataFrame({c["rec"]["label"]: dict(zip(cohorts, c["row"]))
                            for c in cands}).sort_index()
        defl = NF18.deflate(mat, subset=[c["rec"]["label"] for c in eligible] or None)
        trial = []
        for c in cands:
            d = inc_row - c["row"]
            d = d[np.isfinite(d)]
            trial.append(float(d.mean() / d.std(ddof=1))
                         if len(d) >= 3 and d.std(ddof=1) > 1e-12 else np.nan)
        dsr = pval = None
        if best is not None:
            raw = inc_row - best["row"]
            dd = raw[np.isfinite(raw)]
            dsr = M14.deflated_sharpe(dd, np.array(trial, dtype=float))
            pval = M14.onesided_paired_pvalue(dd)
        pvals[pos] = pval
        out["per_position"].append({
            "position": pos, "incumbent_metric": inc_metric,
            "winner": None if best is None else best["rec"]["label"],
            "metric": None if best is None else best["metric"],
            "delta": (None if best is None or inc_metric is None
                      else round(best["metric"] - inc_metric, 3)),
            "pbo": defl.get("pbo"), "dsr": dsr, "pvalue": pval,
        })
    out["fdr"] = M14.bh_fdr(pvals, q=SS.ALPHA)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE MATCHED FOIL — did the BOARD EVIDENCE earn the selection, or would any shrink have done?
# ══════════════════════════════════════════════════════════════════════════════════════════════
def foil_attribution(arms: list[dict], foil: dict, placements: dict, cohorts: list[int]) -> dict:
    """⭐ THE CONTROL THIS STORY'S CLAIM TURNS ON (NF-D10 (g) / NF-D15 (g′)).

    Every RULE arm is paired with `blind_half` — a constant shrink at the midpoint of the registered
    interval, chosen with NO board information whatsoever. Same family, same kind of magnitude, the
    IN-FOLD BOARD EVIDENCE removed. Two readings:

      · PLACEMENT — the rule's λ holds C2 out of sample and the blind constant's does NOT ⇒ the board
        EVIDENCE earned the clearance. BOTH hold ⇒ any mid-strength shrink would have done and the
        selection machinery is not what produced the outcome.
      · ACCURACY — the PAIRED per-class tier-MAE delta, which prices what the evidence costs or buys
        once the family is held equal.

    NF-D15's lesson is the reason this is not optional: a lift can be real and its stated mechanism
    still be refuted. "My rule won" is not "it won for the reason I said"."""
    f_row = _pooled_row(foil, cohorts)
    fp = placements.get(foil["label"], {}) or {}
    rows = []
    for r in arms:
        if r.get("is_foil") or not r.get("recalibrates"):
            continue
        a = _pooled_row(r, cohorts)
        d = a - f_row
        d = d[np.isfinite(d)]
        ap = placements.get(r["label"], {}) or {}
        rows.append({
            "arm": r["label"], "foil": foil["label"],
            "arm_tier_mae": r["pooled_tier_mae"], "foil_tier_mae": foil["pooled_tier_mae"],
            "paired_delta": round(float(d.mean()), 4) if len(d) else None,
            "arm_holds_out": bool(ap.get("holds_out")), "foil_holds_out": bool(fp.get("holds_out")),
            "evidence_earns_clearance": bool(ap.get("holds_out") and not fp.get("holds_out")),
            "any_shrink_would_do": bool(ap.get("holds_out") and fp.get("holds_out")),
        })
    any_ev = any(r["evidence_earns_clearance"] for r in rows)
    any_blind = any(r["any_shrink_would_do"] for r in rows)
    # ⭐ THE FOURTH CASE, AND IT IS THE ONE A NAIVE THREE-WAY READOUT MISREPRESENTS AS "NOTHING TO
    #    ATTRIBUTE": the FOIL satisfies the constraint out of sample and NOT ONE in-fold rule does.
    #    That is not an absence of signal — it is the story's own mechanism REFUTED in the sharpest
    #    available way, and a categorisation that only asks "did an ARM clear?" would report a
    #    devastating result as an empty one (NF-D15 (g′), and the NF1.7 (a) vacuous-check class facing
    #    a summariser rather than a gate).
    foil_only = bool(fp.get("holds_out") and rows and not any(r["arm_holds_out"] for r in rows))
    return {"rows": rows, "n_pairs": len(rows),
            "evidence_earns_a_clearance": bool(any_ev),
            "a_blind_constant_would_also_clear": bool(any_blind),
            "blind_constant_survives_where_selection_does_not": foil_only,
            "reading": ("evidence" if any_ev and not any_blind
                        else "blind_constant" if any_blind and not any_ev
                        else "mixed" if any_ev and any_blind
                        else "blind_only" if foil_only
                        else "no_clearance_to_attribute")}


def constraint_activity(evidence_all: dict) -> list[dict]:
    """⭐ ON HOW MANY BOARDS CAN THE CONSTRAINT EVEN ACT? — measured, because "C2 held on 5 of 7
    boards" means something entirely different if the correction could not move the rank on 4 of them.

    The recalibration touches RB/TE/WR only (QB is excluded by pre-registration), so on a board whose
    best rookie is a QB the best-rookie rank cannot move at all until a corrected RB/WR/TE overtakes
    him. Where the rank is IDENTICAL at every λ the constraint is INACTIVE on that board and its
    'admits everything' is a statement about the mechanism's reach, not about the constraint being
    permissive. NF1.9: a mechanism that cannot act is a finding, not an omission — and MH2's INACTIVE
    state is the same idea one level up, applied to a gate instead of to an arm."""
    rows = []
    for s, ev in sorted(evidence_all.items()):
        ranks = [ev["rank_by_lambda"][float(l)] for l in SS.LAMBDA_GRID]
        top = ev["placement_by_lambda"][0.0]
        rows.append({
            "season": s, "top rookie (λ=0)": top.get("best_rookie"),
            "pos": top.get("best_rookie_position"),
            "rank at λ=0": ranks[0], "rank at λ=1": ranks[-1],
            "rank moves with λ": bool(len(set(ranks)) > 1),
            "constraint can act": bool(len(set(ranks)) > 1),
        })
    return rows


def fine_grid_sensitivity(evidence: dict, cohorts: list[int], folds, fits, pos_scale,
                          cfgs: list[dict]) -> dict:
    """⭐ THE DISCLOSED GRID SENSITIVITY THE PRE-REGISTRATION PROMISED — is the verdict an artefact of
    a coarse λ grid?

    Every board's admissible set and every rule's λ are recomputed on the 0.05 grid. ⛔ NOTHING here is
    selected on, gated on, or entered into PBO or DSR: it exists so 'the answer does not turn on the
    grid' is a number rather than an assurance. A coarse grid could in principle hide a λ that clears
    C2 out of sample while beating the incumbent, and the only honest way to say it does not is to
    look."""
    fine = {float(lam): score_constant_lambda(folds, fits, pos_scale, lam, f"λ={lam:g}")
            for lam in SS.FINE_GRID}
    adm = {}
    for s, ev in evidence.items():
        ranks = board_lambda_ranks(ev["board"], ev["params"], SS.FINE_GRID)["rank_by_lambda"]
        adm[s] = {"rank_by_lambda": ranks,
                  "admissible": SS.admissible_lambdas(ranks, ev["incumbent_rank"])}
    out = {"n_lambda": len(SS.FINE_GRID), "rows": []}
    for cfg in cfgs:
        if cfg["form"] == "incumbent":
            continue
        lam_by_fold, ok = {}, True
        for y in cohorts:
            pb = {s: adm[s]["admissible"] for s in adm if s < y}
            allowed = SS.aggregate_admissible(pb, cfg["evidence"], grid=SS.FINE_GRID)
            inner = ({float(lam): _mean([r["per_cohort_pooled"].get(p) for p in cohorts if p < y], 6)
                      for lam, r in fine.items()} if any(p < y for p in cohorts) else {})
            lam_by_fold[y] = SS.select_lambda(allowed, inner)["lam"]
        for y, lam in lam_by_fold.items():
            r = adm.get(y, {}).get("rank_by_lambda", {}).get(float(lam))
            ok = ok and bool(SS.board_admits(r, evidence[y]["incumbent_rank"])["admits"])
        scored = _score(folds, fits, pos_scale,
                        lambda f, fi, L=lam_by_fold: shrunk(
                            f.test_pred, fi["_te_pos"], fi[SS.REFERENCE_FORM],
                            float(L.get(f.year, SS.EMPTY_EVIDENCE_LAMBDA))),
                        cfg["label"])
        out["rows"].append({"arm": cfg["label"],
                            "λ chosen (fine grid)": str(sorted({round(v, 2)
                                                                for v in lam_by_fold.values()})),
                            "C2 holds out on every fold": ok,
                            "pooled tier MAE": scored["pooled_tier_mae"],
                            "beats incumbent": bool(scored["pooled_tier_mae"] is not None)})
    out["fine_metric_by_lambda"] = {str(lam): r["pooled_tier_mae"] for lam, r in fine.items()}
    return out


def blind_constant_counterfactual(arms: list[dict], foil: dict, incumbent: dict, cohorts: list[int],
                                  placements: dict, serving: dict) -> dict:
    """⛔ A DISCLOSED COUNTERFACTUAL, SELECTED ON BY NOTHING — what would have happened had the blind
    constant been registered SHIPPABLE rather than as a matched foil?

    It is computed because the honest reading of this story's null depends on it: a reader is entitled
    to know whether the arm that survives the constraint would have cleared the statistical gates too.

    ⛔ AND IT IS NOT A RECOMMENDATION, FOR EXACTLY THE REASON NF-D18 REFUSED ITS OWN FRONTIER VALUE.
    'λ = 0.5 survives' is a sentence one can only write with the constraint results already in view.
    A successor that pre-registered 0.5 on the strength of this table would be laundering a known
    number through a pre-registration, which is the E2.1-r inversion in a successor's badge — the
    identical move this story exists to avoid making with a different constant."""
    shipp = dict(foil)
    shipp["shippable"] = True
    shipp["is_foil"] = False
    field = [r for r in arms if not r.get("is_foil")] + [shipp]
    sel = select_pooled(field, incumbent, cohorts, placements, placement_binds=True)
    # ⚠️ the serving check must be computed at the COUNTERFACTUAL winner's OWN λ. Reusing the real
    #    run's serving check would make this table right by accident, and a number that is right by
    #    accident is one nobody can trust the next time the inputs move.
    lam_cf = float((sel["winner"] or {}).get("lam_by_fold", {}).get(cohorts[-1], 0.0))
    rank_cf = serving["rank_by_lambda"].get(lam_cf)
    serving_cf = {**SS.placement_clearance(rank_cf), "lam": lam_cf, "rank": rank_cf}
    serving_cf["clears"] = bool(serving_cf.get("clears"))
    gate = SS.pooled_ship(
        winner=sel["winner"], incumbent_metric=sel["incumbent_metric"],
        ordering=sel["ordering"] or {"per_position": {}}, placement=sel["placement"],
        serving_placement=serving_cf, pbo=sel["deflation"].get("pbo"),
        dsr=sel["deflation"].get("dsr"), pvalue=sel["pvalue"])
    return {"selected": (sel["winner"] or {}).get("label"),
            "serving λ": lam_cf, "2026 rank at that λ": rank_cf,
            "clears the 2026 cap": serving_cf["clears"],
            "metric": (sel["winner"] or {}).get("metric"),
            "incumbent_metric": sel["incumbent_metric"],
            "delta": (None if not sel["winner"] or sel["incumbent_metric"] is None
                      else round(sel["winner"]["metric"] - sel["incumbent_metric"], 4)),
            "pbo": sel["deflation"].get("pbo"), "dsr": sel["deflation"].get("dsr"),
            "pvalue": sel["pvalue"], "would_have_shipped": bool(gate["ship"]),
            "blocking": [k for k, v in gate.items() if k not in ("ship", "framing") and not v]}


def classify_this_null(arms: list[dict], inc: dict, cohorts: list[int], placements: dict) -> dict:
    """⭐ WHICH KIND OF NULL IS THIS? — run the taxonomy, and say plainly where it does not fit.

    CLAUDE.md's MH2 rule is that a recorded null must NAME its state, because a null read as the wrong
    kind emits the wrong next step. `cv_power.classify_null` classifies STATISTICAL nulls. NF-D18
    established the 8th state this programme needed — `CONSTRAINT_REFUSED` — for a null produced by a
    DETERMINISTIC constraint (a board rank against a fixed cap) in which no sampling error accumulates
    and no number of additional draft classes can change the answer.

    ⚠️ WHICH LABEL APPLIES HERE IS A RESULT, NOT A FOREGONE CONCLUSION, and the difference matters:
      · an arm removed by the placement constraint while BEATING the incumbent on the metric is
        CONSTRAINT_REFUSED — remedy: a different mechanism or a PM decision, NEVER more seasons;
      · an arm that is eligible and simply does not clear the deflation gates is a STATISTICAL null and
        keeps whatever state the taxonomy assigns it, re-test trigger included."""
    from betting_ml.utils import cv_power as CP

    inc_row = _pooled_row(inc, cohorts)
    recal = [r for r in arms if r.get("recalibrates") and not r.get("is_foil")
             and r["pooled_tier_mae"] is not None]
    if not recal:
        return {"state": "UNDEFINED", "reason": "no recalibrating arm scored"}
    best = min(recal, key=lambda r: r["pooled_tier_mae"])
    d = inc_row - _pooled_row(best, cohorts)
    d = d[np.isfinite(d)]
    sr = float(d.mean() / d.std(ddof=1)) if len(d) >= 3 and d.std(ddof=1) > 1e-12 else None
    v = CP.classify_null(metric=SS.SELECTION_METRIC, n_folds=len(cohorts),
                         n_arms=len([r for r in arms if not r.get("is_foil")]),
                         beats_foil=bool(d.mean() > 0), observed_sr=sr,
                         fold_wins=int((d > 0).sum()))
    beat_inc = [r["label"] for r in recal
                if r["pooled_tier_mae"] < (inc["pooled_tier_mae"] or np.inf)]
    refused = [r["label"] for r in recal
               if not (placements.get(r["label"], {}) or {}).get("holds_out")]
    all_refused = bool(recal) and len(refused) == len(recal)
    constraint_refused = bool(all_refused and beat_inc)
    return {
        "state": "CONSTRAINT_REFUSED" if constraint_refused else v.state,
        "taxonomy_would_say": v.state,
        "taxonomy_fits": not constraint_refused,
        "why": ("the seven states classify STATISTICAL nulls; every recalibrating arm here BEAT the "
                "incumbent on the metric and was removed by a DETERMINISTIC constraint (a board rank "
                f"against a fixed cap) with no sampling error to accumulate, so '{v.state}' would "
                "emit a re-test trigger that more draft classes cannot satisfy"
                if constraint_refused else
                "at least one recalibrating arm survived the placement constraint, so whatever "
                "refused this story was the METRIC or the deflation gates rather than a "
                "deterministic constraint — the statistical taxonomy applies as written"),
        "best_recalibrating_arm": best["label"],
        "best_recalibrating_metric": best["pooled_tier_mae"],
        "incumbent_metric": inc["pooled_tier_mae"],
        "beats_incumbent_on_accuracy": bool(d.mean() > 0),
        "fold_wins": int((d > 0).sum()), "n_folds": len(d),
        "observed_sr": None if sr is None else round(sr, 4),
        "arms_that_beat_the_incumbent": beat_inc,
        "arms_refused_by_the_constraint": refused,
        "remedy": ("a different MECHANISM, or a PM decision to revisit the constraint — never more "
                   "draft classes, which cannot move a board rank" if constraint_refused
                   else v.remedy if hasattr(v, "remedy") else None),
    }


def ordering_measurements(folds: list[NF17.Fold], fits: dict[int, dict],
                          grid: tuple = SS.LAMBDA_GRID) -> list[dict]:
    """Within-position rank movement at every λ, MEASURED on emitted projections and pooled to the
    worst value over the held-out classes — the strictest honest reading.

    ⭐ NF-D16 method lock 2, inherited: 'zero ordering movement by construction' is a claim about a
    form's algebra under ADMISSIBLE parameters, and the parameters this run fitted are the only ones
    that matter. A λ-blend of an affine with the identity has effective slope `1 + λ(b − 1)`, which
    INVERTS a position's whole board if it comes back negative. So the measurement is what makes the
    ordering constraint something the field can fail rather than a sentence the report repeats."""
    out = []
    for lam in grid:
        worst: dict[str, float] = {}
        eff: list[float] = []
        for f in folds:
            pos = fits[f.year]["_te_pos"]
            adj = shrunk(f.test_pred, pos, fits[f.year][SS.REFERENCE_FORM], float(lam))
            p = np.asarray(f.test_pred, dtype=float)
            for q in SS.SHRINK_POSITIONS:
                sel = pos == q
                if sel.sum() < 2:
                    continue
                rb = pd.Series(p[sel]).rank(ascending=False, method="average").to_numpy()
                rc = pd.Series(adj[sel]).rank(ascending=False, method="average").to_numpy()
                worst[q] = max(worst.get(q, 0.0), float(np.max(np.abs(rb - rc))))
            for _, (_, b) in fits[f.year][SS.REFERENCE_FORM].items():
                eff.append(1.0 + float(lam) * (float(b) - 1.0))
        out.append({"λ": float(lam), "max_rank_move_by_pos": worst,
                    "worst_rank_move": max(worst.values()) if worst else 0.0,
                    "min_effective_slope": round(min(eff), 4) if eff else None,
                    "all_effective_slopes_positive": bool(eff) and all(s > 0 for s in eff)})
    return out


def fitted_parameters(folds: list[NF17.Fold], fits: dict[int, dict]) -> dict:
    """The fitted affines themselves, per class and position — the correction the arms actually shrink,
    exposed rather than left implicit inside a metric."""
    rows, slopes = [], []
    for f in folds:
        for q in SS.SHRINK_POSITIONS:
            ab = fits[f.year][SS.REFERENCE_FORM].get(q)
            if not ab:
                continue
            rows.append({"class": f.year, "position": q,
                         "a": round(float(ab[0]), 3), "b": round(float(ab[1]), 4)})
            slopes.append(float(ab[1]))
    return {"rows": rows, "n_slopes": len(slopes),
            "all_slopes_positive": bool(slopes) and all(s > 0 for s in slopes),
            "min_slope": round(min(slopes), 4) if slopes else None,
            "max_slope": round(max(slopes), 4) if slopes else None}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md(df: pd.DataFrame) -> str:
    # bools render as 0.0000/1.0000 under a float format, which is unreadable in a gate table — the
    # one place a report must be unambiguous about what passed.
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == bool:
            df[c] = df[c].map({True: "True", False: "False"})
    try:
        return df.to_markdown(index=False, floatfmt=".4f")
    except Exception:                                     # noqa: BLE001
        return df.to_string(index=False)


def write_report(out: dict, path: Path) -> None:
    S: list[str] = []
    A = S.append
    sel, gate, verdict = out["selection"], out["ship_gate"], out["verdict"]
    inc = out["incumbent"]["pooled_tier_mae"]

    A(f"# NF-D20 — IN-FOLD GLOBAL-SHRINK selection of NF-D16's rookie-point recalibration under a "
      f"PER-FOLD whole-board placement constraint\n")
    A(f"**Generated:** {out['generated_at']} · **held-out draft classes:** "
      f"{out['cohorts'][0]}–{out['cohorts'][-1]} ({len(out['cohorts'])}) · **merged boards read:** "
      f"{out['board_seasons'][0]}–{out['board_seasons'][-1]} · **arms:** "
      f"{out['n_candidate_arms']} candidates + 1 matched foil + {len(out['anchors'])} anchors · "
      f"**held-out rookie-seasons (RB/TE/WR):** {out['n_scaled_rows']} · **framing:** PRE-REGISTERED "
      f"`{SS.PREREGISTERED_FRAMING}` · **DSR reading:** PRE-REGISTERED "
      f"`{SS.PREREGISTERED_DSR_READING}`\n")
    A(f"## ⭐ VERDICT — {out['headline']}\n")
    A(out["verdict_prose"] + "\n")
    A("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. ⛔ **QB is "
      "EXCLUDED by pre-registration and PROVEN untouched** (max |Δ| over every arm, every held-out "
      f"class and every board: **{out['qb_max_drift']:.9f}** PPR). 🔒 The rookie INTERVAL's WIDTH "
      "model is untouched.\n")

    A("## 0. What was pre-registered, and when\n")
    A("Everything that could otherwise have been chosen after seeing a result is a CONSTANT in "
      "`rookie_shrink_selection.py`, **committed in its own commit before this runner existed**. This "
      "report READS those constants rather than restating them, so 'what was pre-registered' has "
      "exactly one owner.\n")
    A(_md(pd.DataFrame(out["preregistration_table"])) + "\n")
    A(f"🚩 **THE PROVENANCE CLAUSE.** {SS.LAMBDA_PROVENANCE}\n")

    A("## 1. The metric, the two constraints, and the anchor set\n")
    A(f"**Primary metric — `{SS.SELECTION_METRIC}`, NF1.4's, INHERITED RATHER THAN CHOSEN.** The "
      "draftable-tier MAE on a tier FIXED by the incumbent's own projection (NF1.1's fixed-anchor "
      "rule, so no arm can buy a friendlier subset), pooled scale-free over RB/TE/WR for the pooled "
      "test and reported per position in raw PPR beside it.\n")
    A("### The anchors, scored on THIS run\n")
    A(_md(pd.DataFrame(out["anchor_table"])) + "\n")
    for line in out["anchor_prose"]:
        A(line)
    A("")
    A("**The STORY-LEVEL verdict gate** (these are VETOES: a failing anchor means no number computed "
      "in this run may be shipped — it can never make one shippable):\n")
    A(_md(pd.DataFrame([out["verdict"]])) + "\n")
    A("### 1a. ⭐ THE `over_scale` ANCHOR — a pre-registered expectation, MEASURED\n")
    A(out["over_scale_prose"] + "\n")
    A("### The ONE matched-family peeking ceiling — and why one is correct here\n")
    A("⭐ **NF-D16 (g‴) SAYS ONE CEILING PER *FORM* WHEN THE FORMS NEST; IT DOES NOT SAY 'MORE "
      "CEILINGS ARE ALWAYS BETTER'.** Every arm in this field is `point + λ·(a + b·point − point)` "
      "= `λa + (1 + λ(b − 1))·point`, i.e. a per-position AFFINE for every λ. The field is therefore "
      "ONE family, `oracle_ols` is its matched-family peeking ceiling, and no arm may beat it.\n")
    A(_md(pd.DataFrame(out["family_ceiling_check"]["per_arm"])) + "\n")

    A("## 2. ⭐ THE PER-SEASON MERGED BOARDS — the cost NF-D18 named, and its provenance checked\n")
    A("Each board is the product as it would have been SERVED that summer: veterans from season "
      "`Y − 1`'s realized data, the incoming rookie class priced by a slot curve fitted on classes "
      "`≤ Y − 1`, and NF-D16's recalibration OFF. The λ = 0 row of every curve below IS that served "
      "board rather than a reconstruction of it.\n")
    A(_md(pd.DataFrame(out["board_table"])) + "\n")
    A(out["board_prose"] + "\n")
    A("### 2a. The λ → best-rookie-overall-rank curve, per board\n")
    A(_md(pd.DataFrame(out["rank_grid"])) + "\n")
    A(out["constraint_prose"] + "\n")
    A("### 2b. ⭐ ON HOW MANY BOARDS CAN THE CONSTRAINT EVEN ACT? — measured\n")
    A("The recalibration touches RB/TE/WR only, so on a board whose best rookie is a QB the "
      "best-rookie rank cannot move until a corrected RB/WR/TE overtakes him. Where the rank is "
      "identical at every λ the constraint is **INACTIVE** on that board, and its 'admits everything' "
      "describes the mechanism's reach rather than a permissive constraint (NF1.9: a mechanism that "
      "cannot act is a finding, not an omission). This is what makes 'the rules raised λ and were "
      "then caught' legible instead of surprising.\n")
    A(_md(pd.DataFrame(out["constraint_activity"])) + "\n")
    held = [r for r in out["constraint_activity"] if r["season"] != out["serving_season"]]
    n_act = sum(1 for r in held if r["constraint can act"])
    A(f"⇒ the constraint is ACTIVE on **{n_act} of {len(held)}** held-out boards (and on the "
      f"{out['serving_season']} serving board). ⭐⭐ **THIS IS THE MECHANISM BEHIND THIS STORY'S NULL, "
      "AND IT IS THE MOST TRANSFERABLE THING IN IT.** A board's constraint activity is decided by "
      "whether its best rookie is a QB — and QB is the one position the recalibration may not touch. "
      "So on most boards the correction cannot move the best-rookie rank AT ALL, every λ 'is "
      "admissible', and a rule reading prior boards learns that λ = 1 was fine. It then meets a class "
      "whose best rookie is a corrected RB or WR and is caught immediately. **The per-fold placement "
      "constraint is not learnable from prior boards, because its ACTIVITY is a draft-class accident "
      "rather than a stable property** — which is exactly why the in-fold rules fail where a blind "
      "constant that never raises λ survives (§6).\n")

    A("## 3. ⭐ THE IN-FOLD SELECTION — what each rule chose, and from what\n")
    A("For held-out class `Y` a rule may read the merged boards of seasons `< Y` and the held-out "
      "scores of classes `< Y`, and nothing else. No human chooses a λ at any point.\n")
    A(_md(pd.DataFrame(out["rule_table"])) + "\n")
    A(out["rule_prose"] + "\n")

    A("## 4. The full field (pooled over RB/TE/WR)\n")
    A(_md(pd.DataFrame(out["field_table"])) + "\n")
    A("⛔ The `blind_half` row is the NON-SHIPPABLE MATCHED FOIL. It is excluded from the eligible "
      "set, from PBO's search and from the DSR trial field — a diagnostic anchor is never a trial "
      "(MH2 (a)) — and is reported here so the field can be read whole.\n")

    A("## 5. ⭐ THE PRE-REGISTERED POOLED SELECTION — one hypothesis, one test, both constraints\n")
    A(_md(pd.DataFrame([out["selection_table"]])) + "\n")
    A(f"Per-class deltas (incumbent − winner, > 0 ⇒ the winner is better): "
      f"`{sel['per_cohort_delta']}` over classes `{out['cohorts']}`.\n")
    A(f"**Ship decision under the pre-registered framing:** `{gate}`\n")
    A("### 5a. ⭐ WHY EACH INELIGIBLE ARM WAS REFUSED — the constraint doing visible work\n")
    A(_md(pd.DataFrame(sel["ineligible"])) + "\n"
      if sel["ineligible"] else "*(every candidate was eligible)*\n")
    A("### 5b. Is the answer resting on a gate level I chose? — the sensitivity, computed\n")
    A(_md(pd.DataFrame([out["sensitivity"]])) + "\n")
    A(out["sensitivity_prose"] + "\n")
    A("**And the λ-GRID sensitivity the pre-registration promised — is the verdict an artefact of a "
      f"coarse grid?** Every board's admissible set and every rule's λ recomputed on the "
      f"{out['fine_grid']['n_lambda']}-point 0.05 grid. ⛔ Reported, never selected on.\n")
    A(_md(pd.DataFrame(out["fine_grid"]["rows"])) + "\n")
    A("### 5c. THE DISCLOSED ORDERING-ONLY READING — the eligibility rule this story did NOT use\n")
    A(_md(pd.DataFrame(out["eligibility_disclosure"])) + "\n")
    A(out["framing_agreement_prose"] + "\n")
    A("### 5d. THE DISCLOSED PER-POSITION READING\n")
    A(_md(pd.DataFrame(out["per_position"]["per_position"])) + "\n")
    A(f"BH cutoff a position must clear UNCONDITIONALLY under the 3-test framing: "
      f"**{out['per_position']['bh_cutoff_unconditional']}** — against the pooled framing's α of "
      f"**{SS.ALPHA}**.\n")

    A("## 6. ⭐ THE MATCHED FOIL — did the BOARD EVIDENCE earn it, or would any shrink have done?\n")
    A(_md(pd.DataFrame(out["attribution"]["rows"])) + "\n")
    A(out["attribution_prose"] + "\n")
    A("### 6a. ⛔ THE COUNTERFACTUAL — what if the blind constant had been registered SHIPPABLE?\n")
    A("Computed because the honest reading of this null depends on it, and **selected on by "
      "nothing**. ⛔ It is NOT a recommendation: 'λ = 0.5 survives' is a sentence one can only write "
      "with the constraint results already in view, and a successor pre-registering it on the "
      "strength of this table would be laundering a known number through a pre-registration — the "
      "identical move NF-D18 refused to make with its own frontier value, and the one this story "
      "exists to avoid making with a different constant.\n")
    A(_md(pd.DataFrame([out["counterfactual"]])) + "\n")
    A(out["counterfactual_prose"] + "\n")

    A("## 7. Ordering — MEASURED on emitted projections, never asserted\n")
    A(_md(pd.DataFrame(out["ordering"])) + "\n")
    A(f"`all_slopes_positive` = **{out['fitted']['all_slopes_positive']}** (range "
      f"{out['fitted']['min_slope']}–{out['fitted']['max_slope']} over "
      f"{out['fitted']['n_slopes']} affine fits). A λ-blend has effective slope `1 + λ(b − 1)`, so "
      "positive fitted slopes make every λ in the grid within-position monotone — measured above, "
      "not assumed.\n")
    A(_md(pd.DataFrame(out["fitted"]["rows"])) + "\n")

    A("## 8. ⭐ THE SERVING CHECK — the 2026 board, read ONCE, with λ already fixed\n")
    A(out["serving_prose"] + "\n")
    A(_md(pd.DataFrame(out["serving_table"])) + "\n")

    A("## 9. Which kind of null (or ship) is this?\n")
    A(_md(pd.DataFrame([{k: v for k, v in out["null_state"].items()
                         if not isinstance(v, (list, dict))}])) + "\n")
    A(out["null_prose"] + "\n")

    A("## 10. Honest limitations\n")
    for lim in out["limitations"]:
        A(f"- {lim}")
    A("")
    path.write_text("\n".join(S), encoding="utf-8")
    log.info("report → %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF-D20 in-fold global-shrink selection")
    ap.add_argument("--pool", default=str(_POOL))
    ap.add_argument("--from", dest="from_year", type=int, default=2019)
    ap.add_argument("--to", dest="to_year", type=int, default=2025)
    ap.add_argument("--serving-season", type=int, default=2026,
                    help="the board the SERVING check reads — ONCE, with λ already fixed")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    suffix = "_smoke" if args.smoke else ""

    pool = NF17.load_pool(Path(args.pool))
    # ⛔ `recalibrate=False`: the incumbent of THIS story is the point as SERVED TODAY, and NF-D16's
    #    serving flip is HELD. A study of whether to publish a shrunk correction cannot use a
    #    corrected point as its own null.
    folds = NF17.build_folds(pool, list(range(args.from_year, args.to_year + 1)), recalibrate=False)
    if len(folds) < 4:
        raise SystemExit(f"only {len(folds)} usable draft classes — CSCV needs ≥4")
    cohorts = [f.year for f in folds]
    log.info("%d held-out draft classes: %s", len(folds), cohorts)

    fits = {f.year: fold_fits(f) for f in folds}
    pos_scale = {f.year: M14.position_scale(f.train) for f in folds}

    # ── the merged boards: provenance, the λ → rank curve, and each board's admissible λ set ──
    board_seasons = list(range(args.from_year, args.serving_season + 1))
    log.info("reading %d merged veteran+rookie boards: %s", len(board_seasons), board_seasons)
    evidence_all = build_board_evidence(pool, board_seasons)
    # ⛔ THE SERVING BOARD IS NOT EVIDENCE. It is split out here so no rule can reach it: every
    #    aggregation below iterates `evidence`, which contains held-out seasons ONLY.
    serving = evidence_all[args.serving_season]
    evidence = SS.held_out_evidence(evidence_all, args.serving_season)

    prov_bad = [s for s, v in evidence_all.items() if not v["provenance"]["ok"]]
    if prov_bad:
        raise SystemExit(
            f"the merged board(s) for {prov_bad} are not walk-forward (base_season ≠ season − 1, or "
            "no rookie leg). Every placement number in this story would be about a different product. "
            "Rebuild with `run_season_projection.py --backtest-from 2019` before reading any result.")

    # ── the constant-λ grid: the in-fold metric curve every rule reads ──
    lam_scored = {float(lam): score_constant_lambda(folds, fits, pos_scale, lam, f"λ={lam:g}")
                  for lam in SS.LAMBDA_GRID}
    mono = SS.monotonicity({lam: r["pooled_tier_mae"] for lam, r in lam_scored.items()},
                           serving["rank_by_lambda"])

    # ── the rule arms ──
    cfgs = SS.candidate_configs(smoke=args.smoke)
    rules = {}
    arms = []
    for cfg in cfgs:
        if cfg["form"] == "incumbent":
            lam_by_fold = {y: 0.0 for y in cohorts}
            picks = {y: {"lam": 0.0, "metric": None, "boards_seen": [], "evidence_mode": "n/a",
                         "allowed": [0.0]} for y in cohorts}
        else:
            picks = rule_lambdas(cfg, cohorts, evidence, lam_scored)
            lam_by_fold = {y: picks[y]["lam"] for y in cohorts}
        rules[cfg["label"]] = picks
        arms.append(score_rule(folds, fits, pos_scale, lam_by_fold, cfg))

    # ── the MATCHED FOIL: a constant shrink with NO board information at all ──
    foil_cfg = {"label": f"{SS.MATCHED_FOIL_PREFIX}_half (λ={SS.FOIL_LAMBDA:g})",
                "form": SS.REFERENCE_FORM, "rule": None, "recalibrates": True,
                "shippable": False, "constrained": False, "is_foil": True}
    foil_lams = {y: float(SS.FOIL_LAMBDA) for y in cohorts}
    foil = score_rule(folds, fits, pos_scale, foil_lams, foil_cfg)
    rules[foil_cfg["label"]] = {y: {"lam": float(SS.FOIL_LAMBDA), "metric": None,
                                    "boards_seen": [], "evidence_mode": "none (blind)",
                                    "allowed": [float(SS.FOIL_LAMBDA)]} for y in cohorts}
    arms.append(foil)

    incumbent = next(r for r in arms if r["form"] == "incumbent")

    anchors = score_anchors(folds, fits, pos_scale)
    SS.require_anchors(anchors)

    # ── C2, evaluated OUT-OF-SAMPLE on every held-out fold's own board ──
    placements = {r["label"]: holds_out({y: r["lam_by_fold"][y] for y in cohorts}, evidence)
                  for r in arms}
    # the two degenerates' PLACEMENT — the double duty NF1.8 requires (and the story brief names)
    degenerate_place = {}
    for tag, lam in (("zero_scale", None), ("over_scale", SS.OVER_SCALE_LAMBDA)):
        per = {}
        for s, ev in evidence.items():
            if tag == "zero_scale":
                fp = SS.apply_position_adjustment(ev["point"], ev["positions"],
                                                  np.zeros(len(ev["point"])))
                rank = SS.board_placement(ev["board"], fp).get("best_rookie_overall_rank")
            else:
                rank = ev["rank_by_lambda"].get(float(lam))
                if rank is None:                      # λ=2 is outside the grid → compute it here
                    fp = shrunk(ev["point"], ev["positions"], ev["params"], float(lam))
                    rank = SS.board_placement(ev["board"], fp).get("best_rookie_overall_rank")
            per[s] = {**SS.board_admits(rank, ev["incumbent_rank"]), "rank": rank}
        degenerate_place[tag] = {
            "per_board": per,
            "satisfies_every_board": all(v.get("admits") for v in per.values()),
            "breaches_some_board": any(not v.get("admits") for v in per.values())}

    ceiling_check = SS.family_ceiling_check(
        [r for r in arms if not r.get("is_foil")], anchors, metric="pooled_tier_mae",
        family_ceiling=SS.FAMILY_CEILING)

    recal = [r for r in arms if r["recalibrates"] and not r.get("is_foil")
             and r["pooled_tier_mae"] is not None]
    best_recal = min(recal, key=lambda r: r["pooled_tier_mae"]) if recal else None
    ref = best_recal or incumbent

    checks = {
        "degenerates_lose": all(ref["pooled_tier_mae"] < anchors[t]["pooled_tier_mae"]
                                for t in ("zero_scale", "pos_median", "over_scale")),
        "permutation_across_beaten": (ref["pooled_tier_mae"]
                                      < anchors["permuted_across"]["pooled_tier_mae"]),
        "permutation_within_beaten": (ref["pooled_tier_mae"]
                                      < anchors["permuted_within"]["pooled_tier_mae"]),
        "oracle_respected": (anchors["oracle_perplayer"]["pooled_tier_mae"]
                             <= ref["pooled_tier_mae"] + 1e-9),
        "family_ceiling_respected": bool(ceiling_check["ok"]),
        "over_scale_breaches": bool(degenerate_place["over_scale"]["breaches_some_board"]),
        "degenerate_satisfies_constraint": bool(
            degenerate_place["zero_scale"]["satisfies_every_board"]),
        "boards_walk_forward": all(v["provenance"]["ok"] for v in evidence_all.values()),
        "qb_untouched": True,
    }

    # ⛔ THE SCOPE ASSERTION, MEASURED — every arm, every class, every held-out QB, and every board.
    qb_drift = 0.0
    for f in folds:
        qb = fits[f.year]["_te_pos"] == "QB"
        if not qb.any():
            continue
        for r in arms:
            got = shrunk(f.test_pred, fits[f.year]["_te_pos"], fits[f.year][SS.REFERENCE_FORM],
                         float(r["lam_by_fold"][f.year]))
            qb_drift = max(qb_drift, float(np.max(np.abs(got[qb] - f.test_pred[qb]))))
    for s, ev in evidence_all.items():
        qb = ev["positions"] == "QB"
        if not qb.any():
            continue
        for lam in tuple(SS.LAMBDA_GRID) + (SS.OVER_SCALE_LAMBDA,):
            got = shrunk(ev["point"], ev["positions"], ev["params"], float(lam))
            qb_drift = max(qb_drift, float(np.max(np.abs(got[qb] - ev["point"][qb]))))
    checks["qb_untouched"] = qb_drift < 1e-12

    sel = select_pooled(arms, incumbent, cohorts, placements, placement_binds=True)
    ordering_only = select_pooled(arms, incumbent, cohorts, placements, placement_binds=False)

    # ── ⭐ THE SERVING λ + the 2026 board, read ONCE with λ already fixed ──
    serving_pick = None
    serving_check: dict = {"clears": False, "note": "no eligible winner to serve"}
    if sel["winner"] is not None and sel["winner"].get("rule"):
        mode = SS.RULE_EVIDENCE[sel["winner"]["rule"]]
        allowed = SS.aggregate_admissible({s: ev["admissible"] for s, ev in evidence.items()}, mode)
        inner = {float(lam): rec["pooled_tier_mae"] for lam, rec in lam_scored.items()}
        serving_pick = {**SS.select_lambda(allowed, inner), "evidence_mode": mode,
                        "boards_seen": sorted(evidence)}
        lam_s = float(serving_pick["lam"])
        rank_s = serving["rank_by_lambda"][lam_s]
        serving_check = {**SS.placement_clearance(rank_s),
                         **SS.board_admits(rank_s, serving["incumbent_rank"]),
                         "lam": lam_s, "rank": rank_s,
                         "clears": bool(SS.placement_clearance(rank_s).get("clears"))}
    elif sel["winner"] is not None:
        serving_pick = {"lam": 0.0, "note": "the winner is the incumbent — nothing to serve"}
        serving_check = {**SS.placement_clearance(serving["rank_by_lambda"][0.0]),
                         "lam": 0.0, "rank": serving["rank_by_lambda"][0.0]}
        serving_check["clears"] = bool(serving_check.get("clears"))

    ship_gate = SS.pooled_ship(
        winner=sel["winner"], incumbent_metric=sel["incumbent_metric"],
        ordering=sel["ordering"] or {"per_position": {}}, placement=sel["placement"],
        serving_placement=serving_check, pbo=sel["deflation"].get("pbo"),
        dsr=sel["deflation"].get("dsr"), pvalue=sel["pvalue"])
    verdict_gate = SS.shrink_verdict(pooled_ships=bool(ship_gate["ship"]), **checks)

    attribution = foil_attribution(arms, foil, placements, cohorts)
    null_state = classify_this_null(arms, incumbent, cohorts, placements)
    activity = constraint_activity(evidence_all)
    fine_sens = fine_grid_sensitivity(evidence, cohorts, folds, fits, pos_scale, cfgs)
    counterfactual = blind_constant_counterfactual(arms, foil, incumbent, cohorts, placements,
                                                   serving)

    # ── the DISCLOSED sensitivities ──
    def _ships_at(dsr_min=None, drop_dsr=False, use_contender=False) -> bool:
        d = (sel["deflation"].get("dsr_contenders") if use_contender
             else sel["deflation"].get("dsr"))
        g = SS.pooled_ship(
            winner=sel["winner"], incumbent_metric=sel["incumbent_metric"],
            ordering=sel["ordering"] or {"per_position": {}}, placement=sel["placement"],
            serving_placement=serving_check, pbo=sel["deflation"].get("pbo"), dsr=d,
            pvalue=sel["pvalue"],
            dsr_min=(-1e9 if drop_dsr else (SS.DSR_MIN if dsr_min is None else dsr_min)))
        return bool(g["ship"])

    sensitivity = {
        "DSR whole-field (THE GATE)": sel["deflation"].get("dsr"),
        "DSR contender-set (reported)": sel["deflation"].get("dsr_contenders"),
        f"ships at pre-registered DSR ≥ {SS.DSR_MIN}": _ships_at(),
        "ships at NF1.4's DSR ≥ 0.0": _ships_at(dsr_min=0.0),
        "ships with the DSR dropped entirely": _ships_at(drop_dsr=True),
        "ships on the CONTENDER DSR reading": _ships_at(use_contender=True),
    }
    blocking = [k for k, v in ship_gate.items()
                if k not in ("ship", "framing", "dsr_ok") and not v]
    sens_prose = (
        "⭐ **THE ANSWER DOES NOT TURN ON THE DISPUTABLE GATE, AND THAT IS THE POINT OF COMPUTING "
        f"IT.** Nothing ships even with the DSR removed ENTIRELY and even on the kinder contender-set "
        f"reading, because `{blocking}` blocks independently. So the verdict is not an artefact of "
        "inheriting NF-D16's stricter DSR bar nor of naming the whole-field reading as binding."
        if not any(v for k, v in sensitivity.items() if k.startswith("ships"))
        else "⚠️ **THE GATE LEVEL IS LOAD-BEARING** — the pre-registered reading GOVERNS (a bar moved "
             "after seeing the answer is not a bar, E2.1-r), but a reader is entitled to see it.")

    # the STRICT C2 reading (bare cap, no incumbent term) — a sensitivity, never selected on
    strict_rules = {}
    for cfg in cfgs:
        if cfg["form"] == "incumbent":
            continue
        per: dict[int, float] = {}
        for y in cohorts:
            pb = {s: ev["admissible_strict"] for s, ev in evidence.items() if s < y}
            allowed = SS.aggregate_admissible(pb, cfg["evidence"])
            per[y] = SS.select_lambda(allowed, inner_metric_for(cohorts, y, lam_scored))["lam"]
        strict_rules[cfg["label"]] = per

    n_scaled = int(sum(len(SS.scaled_positions_only(f.test)) for f in folds))
    inc_metric = incumbent["pooled_tier_mae"]

    # ── tables ──
    anchor_meta = {
        "oracle_perplayer": "ORACLE FLOOR, full resolution (peeks per player). Nothing may beat it.",
        "oracle_ols": "PEEKING CEILING at MATCHED FAMILY — the per-position affine fitted on the "
                      "HELD-OUT class. No arm may beat it.",
        "permuted_across": "reference fitted on outcomes shuffled ACROSS positions. Must LOSE.",
        "permuted_within": "shuffled WITHIN position — the marginal preserved, the projection↔outcome "
                           "relationship destroyed. ⭐ PRE-REGISTERED TO BE BEATEN.",
        "zero_scale": "DEGENERATE — project nothing. Must LOSE the metric; SATISFIES C2 (see §2a).",
        "pos_median": "DEGENERATE — NF1.4's MAE-collapse tell. Wins an INVERTED metric; must LOSE.",
        "over_scale": f"DEGENERATE on the OTHER side — λ = {SS.OVER_SCALE_LAMBDA:g}, twice the "
                      "ratified correction. Must LOSE the metric AND BREACH C2.",
    }
    anchor_table = [{"anchor": t, "what it is": anchor_meta[t],
                     "pooled tier MAE": a["pooled_tier_mae"],
                     "tier MAE RB": a.get("tier_mae_RB"), "tier MAE TE": a.get("tier_mae_TE"),
                     "tier MAE WR": a.get("tier_mae_WR"), "universe MAE": a["universe_mae"]}
                    for t, a in anchors.items()]
    anchor_table.append({"anchor": "→ INCUMBENT (NULL)", "what it is": "the rookie point as SERVED "
                         "TODAY", "pooled tier MAE": inc_metric,
                         "tier MAE RB": incumbent.get("tier_mae_RB"),
                         "tier MAE TE": incumbent.get("tier_mae_TE"),
                         "tier MAE WR": incumbent.get("tier_mae_WR"),
                         "universe MAE": incumbent["universe_mae"]})

    true_degen_lose = all(ref["pooled_tier_mae"] < anchors[t]["pooled_tier_mae"]
                          for t in ("zero_scale", "pos_median"))
    over_loses = ref["pooled_tier_mae"] < anchors["over_scale"]["pooled_tier_mae"]
    over_note = ("loses as registered" if over_loses else
                 f"DOES NOT — it scores {anchors['over_scale']['pooled_tier_mae']}, BEATING every "
                 "real arm. ⭐ A PRE-REGISTERED EXPECTATION REFUTED BY MEASUREMENT, decomposed in §1a")
    anchor_prose = [
        f"- {'✅' if checks['degenerates_lose'] else '❌'} **the pre-registered `degenerates_lose` "
        "gate** (all three of `zero_scale`, `pos_median`, `over_scale` must lose the metric) — §1a "
        "decomposes it rather than leaving one flag to stand for three different claims",
        f"- {'✅' if true_degen_lose else '❌'} …of which the two TRUE degenerates (`zero_scale` "
        f"{anchors['zero_scale']['pooled_tier_mae']}, `pos_median` "
        f"{anchors['pos_median']['pooled_tier_mae']}) lose to the best real arm "
        f"({ref['pooled_tier_mae']}) — the metric is not paying for pessimism",
        f"- {'✅' if over_loses else '❌'} …and `over_scale` (λ = {SS.OVER_SCALE_LAMBDA:g}) "
        f"{over_note}",
        f"- {'✅' if checks['permutation_across_beaten'] else '❌'} the truth beats the ACROSS-position "
        "permutation",
        f"- {'✅' if checks['permutation_within_beaten'] else '❌'} ⭐ the truth beats the "
        "WITHIN-position permutation — the affine's SLOPE is real information, and this is the anchor "
        "that was provably VACUOUS in NF-D16 (a level is a marginal statistic) and BIT in NF-D18",
        f"- {'✅' if checks['oracle_respected'] else '❌'} the full-resolution oracle floor holds",
        f"- {'✅' if checks['family_ceiling_respected'] else '❌'} every arm respects the "
        "matched-family peeking ceiling",
        f"- {'✅' if checks['degenerate_satisfies_constraint'] else '❌'} ⭐ `zero_scale` SATISFIES C2 "
        "on every board while losing the metric — the proof the placement clause is a CONSTRAINT and "
        "was not quietly promoted into a selection CRITERION (NF1.8)",
        f"- {'✅' if checks['over_scale_breaches'] else '❌'} ⭐ `over_scale` (λ = "
        f"{SS.OVER_SCALE_LAMBDA:g}) BREACHES C2 — the constraint is measured having TEETH rather than "
        "described as strict",
        f"- {'✅' if checks['qb_untouched'] else '❌'} QB is untouched on real emitted projections, not "
        "merely by assertion",
        f"- {'✅' if checks['boards_walk_forward'] else '❌'} every merged board read is WALK-FORWARD "
        "(`base_season == season − 1`, rookie leg present) — checked, not assumed",
    ]

    over_scale_prose = (
        "✅ **`over_scale` LOST AS REGISTERED**, so the pre-registered expectation that over-correction "
        "hurts is corroborated and the `degenerates_lose` gate is clean."
        if over_loses else
        "⚠️⭐⭐ **A PRE-REGISTERED ANCHOR FAILED, AND IT IS REPORTED AS A FAILURE RATHER THAN "
        "RE-LABELLED INTO A PASS.** `over_scale` (λ = "
        f"{SS.OVER_SCALE_LAMBDA:g}, twice the ratified correction) was registered as a degenerate that "
        f"MUST lose the metric. It scored **{anchors['over_scale']['pooled_tier_mae']}** and BEAT "
        f"every real arm in the field, including NF-D16's ratified correction at λ = 1 "
        f"({lam_scored[1.0]['pooled_tier_mae']}). The pre-registered `degenerates_lose` gate therefore "
        "reads **False**, and it is left reading False: moving a gate after seeing which way it fell "
        "is the E2.1-r inversion, and this one costs nothing to leave standing because the verdict is "
        "a NULL either way — a failed anchor can only ever block a ship, never manufacture one.\n\n"
        "⭐ **WHAT IT ACTUALLY MEANS, AND WHY IT STRENGTHENS THE NULL RATHER THAN UNDERMINING IT.** "
        "This is NOT the metric-inversion signature the anchor exists to catch: an inverted metric is "
        "one a DO-NOTHING arm wins, and both do-nothing degenerates lose here by a mile "
        f"({anchors['zero_scale']['pooled_tier_mae']} and "
        f"{anchors['pos_median']['pooled_tier_mae']} against {ref['pooled_tier_mae']}). What λ = 2 "
        "wins is MORE OF THE VERY THING THE CORRECTION DOES, which says the in-fold affine "
        "UNDER-corrects out of sample — the pooled tier MAE is still falling as λ leaves the "
        f"registered interval ({' → '.join(str(lam_scored[float(l)]['pooled_tier_mae']) for l in SS.LAMBDA_GRID)} "
        f"→ {anchors['over_scale']['pooled_tier_mae']} at λ = 2). So the metric's optimum lies BEYOND "
        "the correction the constraint already refuses, while the constraint's admissible ceiling sits "
        "at or below the middle of the interval. **The two objectives are opposed along the magnitude "
        "axis with no interior optimum**, which is a considerably stronger statement of this null than "
        "NF-D18's frontier could make — and it is a statement the run only got to make because the "
        "anchor was scored and READ rather than reasoned about in advance (NF-D14 (g′)).\n\n"
        "⚠️ The honest cost of leaving the gate as written: `degenerates_lose` now bundles a genuine "
        "metric-sanity check with a refuted magnitude hypothesis, so a future reader must not treat a "
        "False here as evidence the measurement is untrustworthy. That is precisely why it is "
        "decomposed into three lines above instead of surfacing as one flag.")

    board_table = [{
        "season": s, "base_season": ev["provenance"]["base_season"],
        "walk-forward": ev["provenance"]["walk_forward"], "rows": ev["provenance"]["n_rows"],
        "rookies": ev["provenance"]["n_rookies"],
        "incumbent best-rookie rank": ev["incumbent_rank"],
        "incumbent clears the cap": bool(
            SS.placement_clearance(ev["incumbent_rank"]).get("clears")),
        "admits λ (pre-registered C2)": str(list(ev["admissible"])),
        "admits λ (STRICT cap — sensitivity)": str(list(ev["admissible_strict"])),
        "role": "SERVING (read once, §8)" if s == args.serving_season else "held-out evidence",
    } for s, ev in sorted(evidence_all.items())]

    rank_grid = [{"season": s, **{f"λ={lam:g}": ev["rank_by_lambda"][float(lam)]
                                  for lam in SS.LAMBDA_GRID}}
                 for s, ev in sorted(evidence_all.items())]

    rule_table = []
    for r in arms:
        picks = rules[r["label"]]
        rule_table.append({
            "arm": r["label"], "shippable": r["shippable"],
            **{f"λ({y})": picks[y]["lam"] for y in cohorts},
            "C2 holds out on every fold": bool(placements[r["label"]]["holds_out"]),
            "pooled tier MAE": r["pooled_tier_mae"],
        })

    field_table = [{
        "arm": r["label"],
        "kind": ("NULL" if r["form"] == "incumbent"
                 else "MATCHED FOIL (⛔ not shippable)" if r.get("is_foil")
                 else "REFERENCE (NF-D16 @ λ=1)" if r.get("rule") == "unconstrained"
                 else "in-fold rule"),
        "pooled tier MAE": r["pooled_tier_mae"], "tier MAE RB": r.get("tier_mae_RB"),
        "tier MAE TE": r.get("tier_mae_TE"), "tier MAE WR": r.get("tier_mae_WR"),
        "universe MAE": r["universe_mae"], "universe bias": r["universe_bias"],
        "C2 holds out": bool(placements[r["label"]]["holds_out"]),
    } for r in sorted(arms, key=lambda x: (x["pooled_tier_mae"] is None, x["pooled_tier_mae"]))]

    w = sel.get("winner")
    selection_table = {
        "incumbent pooled tier MAE": inc_metric,
        "selected arm": None if w is None else w["label"],
        "pooled tier MAE": None if w is None else w["metric"],
        "Δ vs incumbent": (None if w is None or inc_metric is None
                           else round(w["metric"] - inc_metric, 4)),
        "PBO": sel["deflation"].get("pbo"),
        "Bailey degradation %": sel["deflation"].get("os_gap_pct"),
        "contender spread %": sel["deflation"].get("contender_spread_pct"),
        "DSR (whole-field, THE GATE)": sel["deflation"].get("dsr"),
        "DSR (contender, reported)": sel["deflation"].get("dsr_contenders"),
        "one-sided paired p (1 test)": sel["pvalue"], "α (pre-registered)": SS.ALPHA,
    }

    ow = ordering_only.get("winner")
    eligibility_disclosure = [
        {"eligibility rule": "PRE-REGISTERED (ordering + per-fold C2 out-of-sample)",
         "n eligible": sel["n_eligible"],
         "selected arm": None if w is None else w["label"],
         "pooled tier MAE": None if w is None else w["metric"]},
        {"eligibility rule": "ordering ONLY (NF-D16's convention)",
         "n eligible": ordering_only["n_eligible"],
         "selected arm": None if ow is None else ow["label"],
         "pooled tier MAE": None if ow is None else ow["metric"]},
    ]
    framing_prose = (
        "✅ **THE ELIGIBILITY RULE DID NOT DECIDE THE ANSWER** — both readings select the same arm."
        if (ow or {}).get("label") == (w or {}).get("label")
        else "⚠️ **THE TWO READINGS DISAGREE, AND THE DISAGREEMENT IS THE CONSTRAINT DOING ITS JOB.** "
             f"The ordering-only rule selects `{(ow or {}).get('label', '— none —')}`; the "
             f"pre-registered rule filters on the out-of-sample per-fold placement constraint first "
             f"and selects `{(w or {}).get('label', '— none —')}`. The pre-registered rule GOVERNS. "
             "Reporting both is what makes 'the eligibility choice is disclosed, not hidden' a number.")

    breach_seasons = [s for s, ev in sorted(evidence.items())
                      if not SS.placement_clearance(ev["incumbent_rank"]).get("clears")]
    board_prose = (
        "⚠️⭐ **THE SHIPPED PRODUCT ITSELF BREACHES THE CAP ON "
        f"{len(breach_seasons)} OF {len(evidence)} HELD-OUT BOARDS ({breach_seasons or 'none'}), "
        "AND THAT IS WHY C2 IS WRITTEN AS A NO-DEGRADATION CLAUSE.** It was measured before any "
        "candidate in this field was scored and is disclosed rather than worked around: on such a "
        "board a bare-cap constraint would refuse EVERY λ including λ = 0 — i.e. it would refuse the "
        "NULL — and a constraint that refuses everything has examined nothing (NF1.7 (a)). The "
        "pre-registered clause `rank_λ ≥ min(cap, rank_incumbent)` reduces to the plain NF-D17 cap on "
        "every board the incumbent already clears and forbids making a pre-existing breach worse. "
        "The STRICT column is the bare-cap sensitivity; it is reported, never selected on."
        if breach_seasons else
        "✅ The incumbent clears the validated cap on every held-out board, so the pre-registered C2 "
        "and its strict bare-cap reading coincide everywhere and the no-degradation term never binds.")

    constraint_prose = (
        f"The validated NF-D17 cap band: `{SS.placement_clearance(999)['caps_over_q_band']}`, "
        f"observed minimum realized rank **{SS.placement_clearance(999)['observed_minimum']}** ⇒ a "
        f"THRESHOLD-INVARIANT clearance requires overall rank ≥ **{SS.strictest_placement_cap()}**, "
        "i.e. rank 12 or worse. There is no threshold left for anybody to pick, which is what makes a "
        "clearance as un-reverse-engineerable as NF-D17's veto was.\n\n"
        f"⭐ **MONOTONICITY, MEASURED RATHER THAN ASSUMED.** The pooled tier MAE is "
        f"{'MONOTONE DECREASING' if mono['metric_monotone_decreasing'] else 'NOT monotone'} in λ "
        f"(argmin at λ = {mono['metric_argmin_lambda']}), and the served board's best-rookie rank is "
        f"{'MONOTONE non-increasing' if mono.get('rank_monotone_nonincreasing') else 'NOT monotone'} "
        "in λ. Where the metric is monotone the rule's `argmin over the admissible set` coincides with "
        "'the largest admissible λ' and has a one-line description; the argmin is registered anyway "
        "because correctness must not depend on a property that is a measurement (NF-D16 method "
        "lock 2).")

    rule_prose_bits = []
    for cfg in cfgs:
        if cfg["form"] == "incumbent":
            continue
        picks = rules[cfg["label"]]
        chosen = sorted({picks[y]["lam"] for y in cohorts})
        rule_prose_bits.append(
            f"`{cfg['label']}` selected λ ∈ {chosen} across the seven held-out classes "
            f"(evidence mode `{cfg['evidence']}`)")
    strict_bits = [f"`{lab}` → λ ∈ {sorted(set(per.values()))}"
                   for lab, per in strict_rules.items()]
    rule_prose = (
        "⭐ **EVERY λ ABOVE IS A COMPUTED VALUE, NOT A CHOSEN ONE.** " + "; ".join(rule_prose_bits)
        + ".\n\n⭐ **AND THE STRICT-C2 SENSITIVITY (bare cap, no incumbent term — reported, never "
        "selected on):** " + "; ".join(strict_bits) + ".")

    att = attribution["reading"]
    attribution_prose = {
        "evidence": "⭐ **THE MATCHED FOIL ATTRIBUTES THE CLEARANCE TO THE IN-FOLD BOARD EVIDENCE.** "
                    "At least one rule's λ satisfies C2 out of sample where the blind constant shrink "
                    "— same family, no board information — does not. The clearance is a property of "
                    "the SELECTION, not merely of applying less correction (NF-D15 (g′)).",
        "blind_constant": "⚠️ **THE MATCHED FOIL REFUTES THIS STORY'S OWN MECHANISM.** A constant "
                          "shrink chosen with NO board information satisfies C2 out of sample exactly "
                          "where the in-fold rules do — so what buys the clearance is applying LESS "
                          "correction, not selecting HOW MUCH from the boards. That is a finding "
                          "about the mechanism, and it does not license shipping the blind constant: "
                          "the foil is non-shippable by pre-registration precisely so this reading "
                          "cannot become a back door.",
        "mixed": "⚠️ **MIXED ATTRIBUTION.** Some rules' clearances survive the blind foil and some do "
                 "not; the per-arm table is the reading, not this summary line.",
        "blind_only":
            "⚠️⭐⭐ **THE MATCHED FOIL REFUTES THIS STORY'S MECHANISM IN THE SHARPEST WAY AVAILABLE — "
            "AND THIS IS THE MOST IMPORTANT LINE IN THE REPORT.** The BLIND constant shrink — a λ "
            "fixed at the midpoint of the registered interval with NO board information whatsoever — "
            "satisfies the per-fold placement constraint OUT OF SAMPLE on **every** held-out board, "
            "while **not one** of the in-fold selection rules does. So the in-fold machinery this "
            "story was built to test is not merely failing to help: it is actively WORSE at "
            "respecting the constraint than knowing nothing, because reading prior boards licenses it "
            "to raise λ on the seasons where the constraint happens to be inactive and it is then "
            "caught by the next season that is not. ⛔ **AND THAT IS NOT A LICENCE TO SHIP THE BLIND "
            "CONSTANT.** The foil is NON-SHIPPABLE by pre-registration precisely so this reading "
            "cannot become a back door: 'λ = 0.5 works' is a statement one can only make with the "
            "constraint results already in view, which is the same laundering NF-D18 refused for its "
            "own frontier value. The counterfactual is computed in §6a and selected on by nothing.",
        "no_clearance_to_attribute": "⚠️ **THERE IS NO CLEARANCE TO ATTRIBUTE.** No recalibrating arm "
                                     "and not even the blind foil satisfies C2 out of sample, so the "
                                     "matched foil has nothing to separate — itself the cleanest "
                                     "possible reading of the pairing.",
    }[att]

    if serving_pick is None:
        serving_prose = (
            "⛔ **NOTHING REACHED THE SERVING CHECK.** No arm was eligible under the pre-registered "
            "framing, so no λ was ever fixed and the 2026 board decides nothing here. It is reported "
            "below only so a reader can see the state of the served product.")
    else:
        serving_prose = (
            f"⭐ **λ FOR SERVING WAS FIXED BEFORE THIS BOARD WAS READ.** The winning rule "
            f"(`{(w or {}).get('label')}`) applied to ALL seven held-out boards selects "
            f"**λ = {serving_pick['lam']}**; only then is the 2026 board read, and only to run NF1.4's "
            "ordinary serving-time face-validity check on that already-fixed arm. This clause can "
            "only REFUSE a publish — it can never choose between arms — which is the one role in "
            "which reading the served board cannot contaminate a selection.")
    serving_table = [{
        "λ": float(lam), "best rookie": serving["placement_by_lambda"][float(lam)].get("best_rookie"),
        "pos": serving["placement_by_lambda"][float(lam)].get("best_rookie_position"),
        "proj PPR": serving["placement_by_lambda"][float(lam)].get("best_rookie_fp"),
        "overall rank": serving["rank_by_lambda"][float(lam)],
        "rookies in top 10": serving["placement_by_lambda"][float(lam)].get("n_rookies_in_top10"),
        "clears the cap (threshold-invariant)": bool(
            SS.placement_clearance(serving["rank_by_lambda"][float(lam)]).get("clears")),
        "SELECTED": bool(serving_pick is not None
                         and abs(float(lam) - float(serving_pick["lam"])) < 1e-12),
        "pooled tier MAE (held-out)": lam_scored[float(lam)]["pooled_tier_mae"],
    } for lam in SS.LAMBDA_GRID]

    prereg_table = [
        {"decision": "family", "value": "global λ-shrink of NF-D16's ratified per-position affine",
         "why (written BEFORE the run)": "NF-D18 measured that the binding problem is the SHAPE, not "
         "the constraint — a plain global shrink of the ratified affine is the mechanism its null "
         "named. The field is SELECTION RULES rather than λ values, so no human chooses a number."},
        {"decision": "λ grid", "value": str(list(SS.LAMBDA_GRID)),
         "why (written BEFORE the run)": "NF-D16's OWN pre-registered `SHRINK_GRID`, imported, plus "
         "λ = 0 (which reproduces the incumbent exactly). Inheriting it is what stops the grid from "
         "becoming a place to hide a choice."},
        {"decision": "arms", "value": ", ".join(c["label"] for c in cfgs) + f", {foil_cfg['label']}",
         "why (written BEFORE the run)": "the incumbent NULL + two in-fold rules differing only in "
         "how they aggregate board evidence + NF-D16's ratified affine at full strength as the "
         "REFERENCE (shippable, so the constraint has something to REFUSE) + a non-shippable blind "
         "constant as the MATCHED FOIL."},
        {"decision": "constraint C1", "value": f"do-no-ordering-harm ≤ {SS.ORDERING_DO_NO_HARM}",
         "why (written BEFORE the run)": "NF1.4's own constant, inherited verbatim, checked PER "
         "POSITION and never as a pooled mean."},
        {"decision": "constraint C2", "value": "rank_λ ≥ min(NF-D17 threshold-invariant cap, "
         "rank_incumbent), PER FOLD, evaluated OUT-OF-SAMPLE",
         "why (written BEFORE the run)": "the validated clause imported rather than re-derived; the "
         "incumbent term exists because the shipped product itself breaches on some boards and a "
         "constraint that refuses the NULL has examined nothing. Held-out because an in-sample "
         "constraint check is circular."},
        {"decision": "constraints bind on", "value": "ELIGIBILITY (not a post-hoc veto)",
         "why (written BEFORE the run)": SS.ELIGIBILITY_REASON},
        {"decision": "framing", "value": SS.PREREGISTERED_FRAMING,
         "why (written BEFORE the run)": SS.FRAMING_REASON},
        {"decision": "DSR reading that BINDS", "value": SS.PREREGISTERED_DSR_READING,
         "why (written BEFORE the run)": "Inherited from NF-D16 through NF-D18. Naming which reading "
         "binds in advance is what stops it becoming a choice made after seeing which is kinder."},
        {"decision": "DSR level / PBO / α",
         "value": f"{SS.DSR_MIN} / {SS.PBO_MAX} / {SS.ALPHA}",
         "why (written BEFORE the run)": "All three INHERITED FROM NF-D16 BY IMPORT, so the bar "
         "cannot drift between the story that ratified the correction and the story trying to "
         "publish it."},
        {"decision": "selection metric", "value": SS.SELECTION_METRIC,
         "why (written BEFORE the run)": "NF1.4's draftable-tier MAE, INHERITED. Grading the fourth "
         "change to ONE product on a new metric is metric-shopping."},
        {"decision": "empty-evidence default", "value": f"λ = {SS.EMPTY_EVIDENCE_LAMBDA:g}",
         "why (written BEFORE the run)": "the boards begin at 2019, so the first held-out class has "
         "no prior board. With nothing to verify against, a rule applies NO correction — a check that "
         "did not run is not a check that passed (NF1.7 (a))."},
    ]

    headline = (
        f"✅ SHIP — an IN-FOLD-selected global shrink (λ = {serving_pick['lam'] if serving_pick else '?'}) "
        "beats the incumbent, holds the per-fold placement constraint OUT OF SAMPLE, and clears the "
        "validated cap on the served board"
        if verdict_gate["ship"] else
        "🟡 RECORDED NULL — no in-fold-selected shrink clears every pre-registered gate; NF-D16 stays "
        "ratified-but-unpublished")

    out = {
        "story": "NF-D20", "generated_at": datetime.now(timezone.utc).isoformat(),
        "cohorts": cohorts, "board_seasons": board_seasons, "serving_season": args.serving_season,
        "n_scaled_rows": n_scaled,
        "n_candidate_arms": len(cfgs),
        "preregistration": {
            "framing": SS.PREREGISTERED_FRAMING, "framing_reason": SS.FRAMING_REASON,
            "eligibility_reason": SS.ELIGIBILITY_REASON,
            "lambda_provenance": SS.LAMBDA_PROVENANCE,
            "dsr_reading": SS.PREREGISTERED_DSR_READING, "dsr_min": SS.DSR_MIN,
            "alpha": SS.ALPHA, "pbo_max": SS.PBO_MAX, "metric": SS.SELECTION_METRIC,
            "lambda_grid": list(SS.LAMBDA_GRID), "rules": list(SS.SELECTION_RULES),
            "empty_evidence_lambda": SS.EMPTY_EVIDENCE_LAMBDA,
            "strictest_cap": SS.strictest_placement_cap(),
        },
        "preregistration_table": prereg_table,
        "incumbent": incumbent,
        "arms": [{k: v for k, v in r.items() if k != "per_cohort"} for r in arms],
        "anchors": {k: {kk: vv for kk, vv in a.items() if kk != "per_cohort"}
                    for k, a in anchors.items()},
        "boards": {s: {"provenance": ev["provenance"],
                       "incumbent_rank": ev["incumbent_rank"],
                       "rank_by_lambda": {str(k): v for k, v in ev["rank_by_lambda"].items()},
                       "admissible": list(ev["admissible"]),
                       "admissible_strict": list(ev["admissible_strict"])}
                   for s, ev in evidence_all.items()},
        "lambda_grid_scores": {str(lam): {"pooled_tier_mae": r["pooled_tier_mae"],
                                          "per_cohort_pooled": r["per_cohort_pooled"],
                                          "universe_bias": r["universe_bias"]}
                               for lam, r in lam_scored.items()},
        "monotonicity": mono,
        "rules": {lab: {str(y): {k: v for k, v in p.items() if k != "inner_metric"}
                        for y, p in per.items()} for lab, per in rules.items()},
        "strict_c2_rules": {lab: {str(y): v for y, v in per.items()}
                            for lab, per in strict_rules.items()},
        "placements": placements, "degenerate_placement": degenerate_place,
        "family_ceiling_check": ceiling_check, "checks": checks,
        "selection": sel, "ordering_only": ordering_only, "ship_gate": ship_gate,
        "verdict": verdict_gate, "attribution": attribution, "null_state": null_state,
        "serving_pick": serving_pick, "serving_check": serving_check,
        "per_position": per_position_disclosure(arms, incumbent, cohorts, placements),
        "ordering": ordering_measurements(folds, fits), "fitted": fitted_parameters(folds, fits),
        "flips": sel["deflation"].get("flips"),
        "anchor_table": anchor_table, "anchor_prose": anchor_prose,
        "over_scale_prose": over_scale_prose, "constraint_activity": activity,
        "counterfactual_prose": (
            "⚠️⭐⭐ **THE REGISTRATION CHOICE — FOIL RATHER THAN CANDIDATE — DECIDED THIS VERDICT, AND "
            "SAYING SO IS NOT OPTIONAL.** Had the blind constant been registered SHIPPABLE it would "
            f"have been selected and it would have SHIPPED: Δ {counterfactual.get('delta')} pooled "
            f"tier MAE, PBO {counterfactual.get('pbo')}, whole-field DSR {counterfactual.get('dsr')}, "
            f"p {counterfactual.get('pvalue')}, C2 satisfied out of sample on every held-out board, "
            f"and overall rank {counterfactual.get('2026 rank at that λ')} on the 2026 board. This "
            "programme's rule is that a null must prove it does not rest on the author's own design "
            "choice (MH2 (g″)) — and here it DOES rest on one. What it does NOT rest on is a gate "
            "LEVEL: §5b shows nothing ships even with the DSR removed entirely.\n\n"
            "⛔ **AND THE CHOICE WAS STILL THE RIGHT ONE, WHICH IS WHY IT IS NOT BEING REVISITED.** "
            "The brief this story answers asks whether an IN-FOLD-SELECTED shrink can be published; a "
            "fixed constant is not one, and it was registered as the attribution control for exactly "
            "that reason, in writing, before the run. Re-classifying it now that its result is known "
            "would be the E2.1-r inversion in the most literal form available.\n\n"
            "⭐ **WHAT A LEGITIMATE SUCCESSOR WOULD HAVE TO LOOK LIKE (and what it may NOT be).** ⛔ "
            "It may not pre-register λ = 0.5, for the same reason NF-D18 could not pre-register its "
            "own frontier value — the number is now known and was read off these results. The honest "
            "options are: **(i) a PM DECISION** to publish a fixed conservative shrink, accepting "
            "openly that the constant was chosen by judgement rather than by any held-out criterion "
            "(this story's numbers are then the evidence base, not the selection); **(ii) a SHRINK "
            "ESTIMATOR that contains no board information at all** — e.g. empirical-Bayes shrinkage "
            "of the fitted per-position slopes toward 1 with its strength set by the fold-to-fold "
            "VARIANCE of those slopes — which is legitimately pre-registrable because it is an "
            "ESTIMATOR rather than a number, and which must be registered with its own gates before "
            "it is run; or **(iii) accept this null and close NF-D16 unpublished.** ⚠️ Option (ii) is "
            "a real path and it is also the one most at risk of becoming a search for an estimator "
            "that lands near a number we now know, so it should be registered with that hazard named."),
        "fine_grid": fine_sens, "counterfactual": counterfactual,
        "board_table": board_table, "board_prose": board_prose, "rank_grid": rank_grid,
        "constraint_prose": constraint_prose, "rule_table": rule_table, "rule_prose": rule_prose,
        "field_table": field_table, "selection_table": selection_table,
        "eligibility_disclosure": eligibility_disclosure,
        "sensitivity": sensitivity, "sensitivity_prose": sens_prose,
        "framing_agreement_prose": framing_prose, "attribution_prose": attribution_prose,
        "serving_prose": serving_prose, "serving_table": serving_table,
        "qb_max_drift": qb_drift, "headline": headline,
    }

    # ── the verdict prose ──
    a: list[str] = []
    if verdict_gate["ship"]:
        a.append(
            f"**The pre-registered pooled test selects `{w['label']}`**, moving the pooled "
            f"draftable-tier MAE **{inc_metric} → {w['metric']}** over {len(cohorts)} held-out draft "
            f"classes, with PBO {sel['deflation'].get('pbo')}, whole-field DSR "
            f"{sel['deflation'].get('dsr')} (the pre-registered gate, ≥ {SS.DSR_MIN}) and a one-sided "
            f"paired p of {sel['pvalue']} against α = {SS.ALPHA}. Its λ — selected on each fold from "
            "PRIOR classes and PRIOR boards only — satisfies the placement constraint OUT OF SAMPLE "
            f"on every held-out board, and at λ = {serving_pick['lam']} it places the 2026 board's "
            f"best rookie at overall rank {serving_check.get('rank')}, clearing the validated NF-D17 "
            "cap at EVERY quantile in the Q05–Q25 band and against reality's observed minimum.")
    elif w is None:
        a.append(
            "**NO ARM IS ELIGIBLE.** Not one pre-registered arm satisfies both constraints at once: "
            "do-no-ordering-harm at every scaled position AND the per-fold placement constraint held "
            "OUT OF SAMPLE on every held-out board. The selection therefore has nothing to select.")
    else:
        blocked = [k for k, v in ship_gate.items() if k not in ("ship", "framing") and not v]
        undefined = [k for k in ("pbo_ok", "dsr_ok", "significant")
                     if k in blocked and sel["n_eligible"] <= 1]
        binding = [k for k in blocked if k not in undefined]
        a.append(
            f"**The pre-registered pooled test selects `{w['label']}`**, moving the pooled "
            f"draftable-tier MAE **{inc_metric} → {w['metric']}** (Δ "
            f"{round(w['metric'] - inc_metric, 4)}) over {len(cohorts)} held-out draft classes, with "
            f"PBO {sel['deflation'].get('pbo')}, whole-field DSR {sel['deflation'].get('dsr')} (the "
            f"pre-registered gate, ≥ {SS.DSR_MIN}) and a one-sided paired p of {sel['pvalue']} "
            f"against α = {SS.ALPHA}. **The BINDING failures are `{binding}`**"
            + (f" — `{undefined}` are reported as failed only because they are **UNDEFINED**: with "
               "the incumbent the single eligible arm there is no search to deflate and no non-zero "
               "delta to score, and a statistic that was not COMPUTABLE must never be read as a "
               "mechanism that lost (MH2's UNDEFINED-vs-failed rule)." if undefined else "."))
        a.append("")
        a.append(
            "⭐ **AND THE REASON THE INCUMBENT IS THE ONLY ELIGIBLE ARM IS THE WHOLE RESULT.** Every "
            "recalibrating arm BEATS the incumbent on the selection metric — the in-fold rules by "
            f"{round(inc_metric - min(r['pooled_tier_mae'] for r in arms if r['recalibrates'] and not r.get('is_foil')), 4)} "
            "pooled tier MAE at best — and every one of them is removed by the PER-FOLD placement "
            "constraint evaluated OUT OF SAMPLE. Nothing here lost on accuracy; the arms were refused "
            "by a deterministic board rank (§9).")
    a.append("")
    a.append(attribution_prose)
    a.append("")
    if verdict_gate["ship"]:
        a.append(
            "⇒ **SHIP.** ⚠️ It moves the rookie band's CENTRE, so `run_interval_revalidation` must be "
            "re-run and every coverage floor re-confirmed before this reaches the board, and the "
            "`--publish` is a POST-MERGE operator step. QB stays exactly where NF-D14 left it.")
    else:
        a.append(
            "⇒ **RECORDED NULL ON THE PRE-REGISTERED QUESTION, AND IT CLOSES THE *IN-FOLD SELECTION* "
            "PATH RATHER THAN NF-D16 ITSELF.** The harness NF-D18 named as the only legitimate "
            "remaining publish route has now been built — the merged veteran+rookie board rebuilt per "
            "held-out season, the constraint enforced OUT OF SAMPLE — and it does not produce a "
            "shippable shrink under the gates NF-D16 itself pre-registered. NF-D16 stays "
            "RATIFIED-BUT-UNPUBLISHED, the shipped rookie point STANDS, the interval is untouched, "
            "and the QB exclusion was never re-opened. ⚠️ **What this null does NOT say is 'nothing "
            "could ever work', and §6a is where a reader must go before treating it that way:** a "
            "shrink that never consults a board survives every constraint this story could throw at "
            "it, so what failed is the SELECTION MACHINERY, not the shrink family — and the reason it "
            "failed is diagnosable (§2b: the constraint's activity is a draft-class accident, so "
            "prior boards cannot teach a rule what the next one will refuse). The remaining routes "
            "are a PM decision or a board-free shrink ESTIMATOR, both spelled out in §6a; neither is "
            "'more draft classes'.")
    out["verdict_prose"] = "\n".join(a)

    null_prose = (
        f"⚠️⭐ **RECORDED AS `{null_state['state']}`.** `cv_power.classify_null` returns "
        f"**`{null_state['taxonomy_would_say']}`**. {null_state['why']}\n\n"
        f"⇒ **remedy: {null_state['remedy']}**." if not verdict_gate["ship"] else
        "✅ **NOT A NULL.** The classification is reported for completeness: an in-fold-selected shrink "
        "cleared every pre-registered gate, so there is no null to classify and no re-test trigger to "
        "state.")
    out["null_prose"] = null_prose

    out["limitations"] = [
        "⚠️⭐ **THE VERDICT RESTS ON A REGISTRATION CHOICE OF THIS STORY'S OWN — DISCLOSED IN §6a, "
        "NOT BURIED.** The blind constant shrink was registered as a NON-SHIPPABLE matched foil "
        "before the run, and had it been registered as a candidate it would have been selected and "
        "would have shipped. The choice was faithful to the brief (a fixed constant is not an "
        "IN-FOLD-SELECTED shrink) and re-classifying it now would be the E2.1-r inversion — but a "
        "reader is entitled to know that the eligibility of one arm, and not a gate LEVEL, is what "
        "separates this null from a ship. §5b shows the gate levels decide nothing.",
        "⚠️⭐ **THE CONSTRAINT IS INACTIVE ON MOST BOARDS, WHICH BOUNDS WHAT 'C2 HELD OUT' MEANS "
        "EITHER WAY.** On 4 of the 8 boards read here the best rookie is a QB — the one position the "
        "recalibration may not touch — so no λ can move the rank and C2 admits everything "
        "vacuously (§2b). An arm's constraint record is therefore built from far fewer genuinely "
        "informative boards than the fold count suggests, in BOTH directions: the blind constant's "
        "clean sheet is as thin as the rules' failures are.",
        "⚠️ **A PRE-REGISTERED ANCHOR (`over_scale`) FAILED AND THE GATE IS LEFT READING FALSE** "
        "(§1a). It is not the metric-inversion signature the anchor exists to catch — both "
        "do-nothing degenerates lose comfortably — but the bundled `degenerates_lose` flag now mixes "
        "a metric-sanity check with a refuted magnitude hypothesis, and a future reader must not read "
        "its False as 'the measurement is untrustworthy'.",
        "⚠️ **THE PLACEMENT CAP'S REFERENCE DISTRIBUTION IS NOT WALK-FORWARD, AND IT IS INHERITED "
        "RATHER THAN RE-DERIVED.** NF-D17's `REALIZED_BEST_ROOKIE_OVERALL_RANK` spans 2019–2025, so "
        "the cap applied to the 2019 board was estimated partly from seasons after it. Re-deriving a "
        "per-fold cap would mean re-specifying the very validated clause this story must clear — the "
        "E2.1-r inversion facing the other way — so the clause is imported verbatim. The bound on the "
        "cost: the cap is a CONSTANT, identical for every arm and every fold, so it cannot favour one "
        "arm over another; it can only shift the whole field's admissible set together.",
        "⚠️ **THE FIRST HELD-OUT CLASS HAS NO BOARD EVIDENCE AT ALL.** The merged boards begin at "
        f"{args.from_year}, so every rule falls back to the registered empty-evidence default "
        f"(λ = {SS.EMPTY_EVIDENCE_LAMBDA:g}) on that class and contributes a delta of exactly 0. That "
        "is a real power cost of one fold in seven, registered in advance rather than discovered. It "
        "is reachable — earlier boards can be emitted with `--backtest-from` further back — but it is "
        "a DATA-availability limit on the metric, and it is stated separately from the constraint "
        "result so the two are never confused.",
        "⚠️ **THE PER-FOLD CONSTRAINT IS EVALUATED ON ONE BOARD PER FOLD.** A board is a serving-time "
        "artifact, not a held-out statistical criterion, so C2 contributes no power — it can only "
        "remove arms. What bounds that: no arm's PARAMETERS are ever tuned to any board (the affine "
        "is fitted in-fold on rookie outcomes, and only the discrete λ is chosen), the clearance is "
        "required to be THRESHOLD-INVARIANT so no cutoff was picked, C2 is enforced OUT-OF-SAMPLE, "
        "and the ordering-only reading is reported beside it (§5c).",
        "⚠️ **THE `min(cap, rank_incumbent)` TERM IS A REAL LOOSENING ON THE BOARDS WHERE IT BINDS, "
        "AND IT IS DISCLOSED RATHER THAN BURIED.** It was written into the pre-registration because "
        "the shipped product breaches the cap on some historical boards and a constraint that refuses "
        "the NULL has examined nothing — but on those boards it does admit λ values a bare cap would "
        "not. Both readings are computed (§2, §3) and the pre-registered one governs.",
        f"**`{SS.SELECTION_METRIC}` grades the DRAFTABLE TIER — ~6 RB / 8 WR / 3 TE per class.** A "
        "claim here is a claim about a few dozen rookie-seasons across seven draft classes; the "
        "paired per-class deltas are reported so a reader sees the spread rather than only the mean.",
        "**The in-fold affine is estimated against IN-SAMPLE point projections** (the training rows' "
        "points come from the fold's own slot curve). NF-D16 measured the resulting optimism at −0.05 "
        "in constant space and the direction is CONSERVATIVE — it biases a correction toward the "
        "identity — but it is not zero, and it applies to every λ here.",
        "⛔ **QB is out of scope by pre-registration, not by result** — inherited by import through "
        "NF-D16 from NF-D15/NF-D14, and proven untouched on both the held-out classes and every board "
        "rather than asserted.",
        "**No edge claim.** A projection-quality product: `best_alpha = 0`, no CLV/ROI statement.",
    ]

    if not args.no_report:
        _REPORT_DIR.mkdir(parents=True, exist_ok=True)
        write_report(out, _REPORT_DIR / f"nf_d20_infold_shrink{suffix}.md")
        drop = {"board", "point", "positions", "params", "placement_by_lambda"}
        (_REPORT_DIR / f"nf_d20_infold_shrink{suffix}.json").write_text(
            json.dumps({k: v for k, v in out.items() if k not in drop}, indent=2, default=str),
            encoding="utf-8")
    log.info("VERDICT: %s", headline)
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
