"""run_nf1_5.py — NF1.5 CLI/IO: the CAPSTONE feature-combination bake-off (both stages), the
placebo control, the product grade, the serving recommendation + calibration verify, the build.

Read `nf1_5_model.py`'s docstring for the design. This module does the DuckDB reads (SF-free
sports lake), the ONE cached feature matrix (the NF1.2 extended pool + the NF1.3 market join —
every model × bundle × trial × fold reads the cache, never re-pulls), the walk-forward
orchestration with Optuna (EVERY config counted toward the deflation), the placebo re-run, the
NF-D3 product grade, and the S3 landing to NF1.5's own prefix.

⭐ RUN ON THE LAPTOP (like run_nf1_1/2/3): SF-free, sports-lake DuckDB + local caches only.
`SPORTS_LAKE_REGION=us-east-2` for any S3 write.

MODES (staged per the story — the market pass FIRST, no peeking across stages):
  * `market` — ⭐ STAGE 1 (PRIMARY): the market-aware refinement pass. Per position, Optuna-tune
               the refinement family (learned-anchor × dispersion-adaptive blends + the flat
               blend re-tuned) against THREE fixed foils — the MVP-1 blind null, pure consensus,
               and the NF1.3 STORED incumbent (the bar to beat). Deflated + placebo'd.
  * `blind`  — STAGE 2 (CEILING-PROOF, expected null): the bounded bundle × class sweep
               (7 pre-registered bundles × ridge/gbm/similarity/MLP, deduped per position)
               vs the MVP-1 null, with the NF1.1 stored winner as a fixed reference arm.
               Deflated + placebo'd.
    Both stages append into ONE report: ablation_results/nf1_5_feature_combination_bakeoff.{md,json}
  * `grade`  — the PRODUCT-metric verdict + the SERVING DECISION: build the refined market-aware
               board per season, run the NF-D3 consensus scorecard apples-to-apples with the
               stored MVP-1/NF1.3 runs, run the interval-calibration verify (the NF1.3
               refinement-#5), and emit the serving recommendation.
               → ablation_results/nf1_5_vs_consensus_scorecard.json (+ recommendation into the report json)
  * `build`  — the final refined projection (ordering-only over MVP-1's calibrated multiset),
               landed to `nfl/fantasy/derived/nf1_5_season_projections` (never overwrites the
               MVP-1/NF1.x boards).

Heavy runs (full bake-offs, the 6-season grade) are >2 min ⇒ HAND TO THE OPERATOR;
`--smoke` runs a tiny subset and writes `*_smoke` reports (never clobbers the real ones).
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

from quant_sports_intel_models.football.nfl.fantasy import nf1_2_model as M12  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_3_model as M13  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_5_model as M15  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_model as M1  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.run_nf1_1 import (  # noqa: E402
    _finite_top,
    _season_row,
    _sharpe,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf1_2 import (  # noqa: E402
    build_extended_frame,
    build_pool as build_nf1_2_pool,
    cache_is_current,
    load_inputs,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf1_3 import (  # noqa: E402
    attach_market,
)
from quant_sports_intel_models.football.nfl.fantasy.run_season_projection import (  # noqa: E402
    MARTS_SCHEMA,
    OUTPUT_COLS,
    build_projection,
    load_realized_season,
)

log = logging.getLogger("nfl.fantasy.nf1_5")

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_FEATURE_CACHE = _ART / "nf1_5_feature_cache"
_NF1_1_JSON = _REPORT_DIR / "nf1_1_per_position.json"
_NF1_3_JSON = _REPORT_DIR / "nf1_3_per_position.json"
_NF1_3_SCORECARD = _REPORT_DIR / "nf1_3_vs_consensus_scorecard.json"

NF1_5_EXTRA_COLS = ["nf1_scale", "nf1_5_learner", "nf1_5_blend_w", "nf1_5_disp_slope", "market_lean"]

PLACEBO_SEED = 20260727


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The ONE cached feature matrix — NF1.2 extended pool (families attached on the FULL pre-filter
# universe, the survivorship-order contract) + the NF1.3 leakage-safe market join.
# ══════════════════════════════════════════════════════════════════════════════════════════════
def build_pool(con, base_seasons: list[int], schema: str = MARTS_SCHEMA,
               use_cache: bool = True) -> pd.DataFrame:
    _FEATURE_CACHE.mkdir(parents=True, exist_ok=True)
    frames, missing = [], []
    for b in base_seasons:
        cache = _FEATURE_CACHE / f"pool_base{b}.parquet"
        # a cache written before a family was registered lacks its columns — rebuild, never trust
        # (see `run_nf1_2.cache_is_current`; NF-D10 is the family that surfaced this)
        if use_cache and cache.exists():
            cached = pd.read_parquet(cache)
            if cache_is_current(cached):
                frames.append(cached)
            else:
                log.info("nf1_5 pool cache base%d predates a registered family — rebuilding", b)
                missing.append(b)
        else:
            missing.append(b)
    if missing:
        inputs = load_inputs(con, missing, schema)
        for b in missing:
            part = build_nf1_2_pool(con, [b], inputs, schema, use_cache=use_cache)
            if part.empty:
                continue
            part = attach_market(con, part, schema)
            part.to_parquet(_FEATURE_CACHE / f"pool_base{b}.parquet", index=False)
            frames.append(part)
    if not frames:
        return pd.DataFrame()
    pool = pd.concat(frames, ignore_index=True, sort=False)
    return pool.sort_values(["target_season", "position", "player_id"]).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Generic walk-forward (factory-based — one inner unit serves both stages + the foils)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def walk_forward_pos(pool: pd.DataFrame, pos: str, factory, target_seasons: list[int],
                     label: str, hp: dict | None = None, **extra) -> dict:
    """Backtest ONE config: per target season Y, fit on `target_season < Y` (expanding,
    leakage-safe), predict Y, score the held-out TOP-TIER ρ (tier anchored on `mvp1_fp` — fixed
    across candidates; degenerate→0). `factory()` returns a FRESH learner each fold."""
    d = pool[pool["position"] == pos]
    per_top, per_full = {}, {}
    for y in target_seasons:
        tr = d[d["target_season"] < y]
        te = d[d["target_season"] == y]
        if len(tr) < 30 or len(te) < 15:
            continue
        learner = factory()
        learner.fit(tr, tr["real_fp_ppr"].to_numpy())
        scored = te.assign(_pred=learner.predict(te))
        top, _ = M15.top_tier_rho(scored, "_pred", top_n={pos: M15.TOP_N[pos]}, degenerate_zero=True)
        if pos in top:
            per_top[y] = top[pos]
        if len(scored) >= 10:
            v = M15.safe_spearman(scored["_pred"], scored["real_fp_ppr"])
            if v is not None:
                per_full[y] = round(v, 4)

    def _mean(dd):
        return round(float(np.mean(list(dd.values()))), 4) if dd else None

    return {"learner": label, "hp": hp or {}, "per_season_top": per_top,
            "per_season_full": per_full, "mean_top": _mean(per_top),
            "mean_full": _mean(per_full), **extra}


def _optuna_tune(pool: pd.DataFrame, pos: str, name: str, factory_of_hp, target_seasons: list[int],
                 n_trials: int, **extra) -> list[dict]:
    """Tune ONE candidate for ONE position; EVERY trial's record is returned (all deflate)."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    records: list[dict] = []

    def objective(trial):
        hp = M15.suggest_hp(trial, name)
        rec = walk_forward_pos(pool, pos, factory_of_hp(hp), target_seasons, name, hp, **extra)
        records.append(rec)
        v = rec["mean_top"]
        return v if v is not None and np.isfinite(v) else -1.0

    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=17))
    study.optimize(objective, n_trials=max(n_trials, 1), show_progress_bar=False)
    records.sort(key=_finite_top, reverse=True)
    return records


def _deflate(trial_records: list[dict], null_rec: dict, winner: dict,
             scored_targets: list[int]) -> dict:
    matrix = np.vstack([_season_row(r, scored_targets) for r in trial_records])
    null_row = _season_row(null_rec, scored_targets)
    deltas = _season_row(winner, scored_targets) - null_row
    trial_srs = np.array([_sharpe(_season_row(r, scored_targets) - null_row)
                          for r in trial_records])
    return {"pbo": M15.cscv_pbo(matrix), "config_spread": M15.config_spread(matrix),
            "dsr": M15.deflated_sharpe(deltas, trial_srs),
            "pvalue": M15.onesided_paired_pvalue(deltas),
            "n_configs": int(len(trial_records))}


def _load_incumbents() -> tuple[dict, dict]:
    nf11 = M15.extract_winners(json.loads(_NF1_1_JSON.read_text())) if _NF1_1_JSON.exists() else {}
    nf13 = M15.extract_winners(json.loads(_NF1_3_JSON.read_text())) if _NF1_3_JSON.exists() else {}
    return nf11, nf13


def _anchor_spec(pos: str, nf11: dict) -> M15.AnchorSpec:
    """The pre-registered learned anchor = the NF1.1 stored winner on its market-BLIND set."""
    w = nf11.get(pos, {})
    return M15.AnchorSpec(learner=w.get("learner", "pos_ridge"), hp=w.get("hp", {}),
                          feats=M12.BASE_POSITION_FEATURES[pos])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STAGE 1 — the market-aware refinement pass (PRIMARY)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _scored_targets(pool: pd.DataFrame, score_from: int | None) -> list[int]:
    """Seasons that get SCORED (each still trains on every earlier pool season). `score_from`
    bounds the scoring window without shrinking the training history — the data-expansion lever:
    e.g. base 2006 pool + score_from 2019 keeps the market-era metric while every fold trains on
    13 extra seasons."""
    targets = sorted(pool["target_season"].unique().tolist())
    return [y for y in targets
            if any(t < y for t in targets) and (score_from is None or y >= score_from)]


def run_market_stage(pool: pd.DataFrame, n_trials: int, placebo_trials: int,
                     score_from: int | None = None) -> dict:
    scored_targets = _scored_targets(pool, score_from)
    nf11, nf13 = _load_incumbents()
    coverage = M15.market_coverage(pool)

    oracle_ok = all(
        M15.oracle_top_tier_is_ceiling(pool[pool["target_season"] == y].assign(_c=lambda d: d["mvp1_fp"]),
                                       ["_c"]) for y in scored_targets)

    def _search(p: pd.DataFrame, trials: int, tag: str) -> dict:
        positions_out: dict[str, dict] = {}
        pvals: dict[str, float | None] = {}
        for pos in M15.POSITIONS:
            spec = _anchor_spec(pos, nf11)
            null_rec = walk_forward_pos(
                p, pos, lambda: M13.make_pos_learner("pos_null", feats=()), scored_targets,
                "pos_null")
            mkt_only = walk_forward_pos(
                p, pos, lambda: M13.make_pos_learner("pos_market_only", feats=()), scored_targets,
                "pos_market_only")
            inc = nf13.get(pos)
            inc_rec = None
            if inc:
                inc_feats = M13.POSITION_FEATURES[pos]
                inc_rec = walk_forward_pos(
                    p, pos,
                    lambda inc=inc, f=inc_feats: M13.make_pos_learner(inc["learner"], feats=f, **inc["hp"]),
                    scored_targets, f"nf1_3_incumbent({inc['learner']})", inc["hp"])
            trial_records: list[dict] = ([inc_rec] if inc_rec else [])
            best_by_class: dict[str, dict] = {}
            for name in M15.STAGE1_CANDIDATES:
                recs = _optuna_tune(
                    p, pos, name,
                    lambda hp, n=name, s=spec: (lambda: M15.make_stage1_learner(n, inner=s, **hp)),
                    scored_targets, trials)
                trial_records.extend(recs)
                if recs and np.isfinite(_finite_top(recs[0])):
                    best_by_class[name] = recs[0]
                log.info("  [%s] %s %-27s best top-tier ρ=%s (%d trials)", tag, pos, name,
                         recs[0]["mean_top"] if recs else None, len(recs))
            if not best_by_class:
                positions_out[pos] = {"null": null_rec, "market_only": mkt_only,
                                      "note": "no scoreable candidate"}
                pvals[pos] = None
                continue
            winner = max(best_by_class.values(), key=_finite_top)
            defl = _deflate(trial_records, null_rec, winner, scored_targets)
            pvals[pos] = defl["pvalue"]
            inc_top = inc_rec["mean_top"] if inc_rec else None
            positions_out[pos] = {
                "null": null_rec, "market_only": mkt_only,
                "nf1_3_incumbent": ({k: inc_rec[k] for k in ("learner", "hp", "mean_top", "per_season_top")}
                                    if inc_rec else None),
                "learned_anchor": {"learner": spec.learner, "hp": spec.hp},
                "market_top_tier_coverage": coverage.get(pos),
                "best_by_class": best_by_class, "winner": winner, **defl,
                "beats_null": bool(winner["mean_top"] is not None and null_rec["mean_top"] is not None
                                   and winner["mean_top"] > null_rec["mean_top"]),
                "beats_market_only": bool(winner["mean_top"] is not None and mkt_only["mean_top"] is not None
                                          and winner["mean_top"] > mkt_only["mean_top"]),
                "beats_nf1_3_incumbent": bool(winner["mean_top"] is not None and inc_top is not None
                                              and winner["mean_top"] > inc_top),
                "delta_vs_nf1_3_incumbent": (round(winner["mean_top"] - inc_top, 4)
                                             if winner["mean_top"] is not None and inc_top is not None
                                             else None),
            }
        fdr = M15.bh_fdr(pvals)
        for pos, r in positions_out.items():
            if "winner" not in r:
                r["verdict"] = {"repoint": False, "note": "unscoreable"}
                continue
            r["fdr_pass"] = bool(fdr.get(pos, False))
            # the stage-1 repoint bar: beat the NF1.3 INCUMBENT (not merely the blind null) + gates
            r["verdict"] = M15.position_verdict(r["beats_nf1_3_incumbent"], r["pbo"], r["dsr"],
                                                r["fdr_pass"])
        return positions_out

    log.info("STAGE 1 (market refinements): pool %d rows, targets %s", len(pool), scored_targets)
    positions = _search(pool, n_trials, "real")
    log.info("STAGE 1 placebo (shuffled labels, %d trials)", placebo_trials)
    placebo = _search(M15.placebo_shuffle(pool, PLACEBO_SEED), placebo_trials, "placebo")
    placebo_summary = {
        pos: {"winner_mean_top": r.get("winner", {}).get("mean_top"),
              "null_mean_top": r.get("null", {}).get("mean_top"),
              "naive_delta_vs_null": (round(r["winner"]["mean_top"] - r["null"]["mean_top"], 4)
                                      if r.get("winner", {}).get("mean_top") is not None
                                      and r.get("null", {}).get("mean_top") is not None else None),
              "gates_pass": bool(r.get("verdict", {}).get("repoint", False))}
        for pos, r in placebo.items()}
    return {
        "stage": "market_refinements",
        "pool_base_seasons": [int(pool["base_season"].min()), int(pool["base_season"].max())]
        if "base_season" in pool.columns else None,
        "score_from": score_from,
        "target_seasons": scored_targets, "n_pool": int(len(pool)),
        "selection_metric": f"top-tier within-position ρ (tier = top-N by the MVP-1 incumbent, N={M15.TOP_N})",
        "oracle_metric_ok": bool(oracle_ok),
        "market_top_tier_coverage": coverage,
        "n_trials_per_class": n_trials, "placebo_trials": placebo_trials,
        "candidates": list(M15.STAGE1_CANDIDATES),
        "positions": positions,
        "placebo": placebo_summary,
        "pbo_max": M15.PBO_MAX, "dsr_min": M15.DSR_MIN, "fdr_q": M15.FDR_Q,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STAGE 2 — the market-blind ceiling-proof bundle × class sweep
# ══════════════════════════════════════════════════════════════════════════════════════════════
def run_blind_stage(pool: pd.DataFrame, n_trials: int, placebo_trials: int,
                    score_from: int | None = None) -> dict:
    scored_targets = _scored_targets(pool, score_from)
    nf11, _ = _load_incumbents()

    oracle_ok = all(
        M15.oracle_top_tier_is_ceiling(pool[pool["target_season"] == y].assign(_c=lambda d: d["mvp1_fp"]),
                                       ["_c"]) for y in scored_targets)

    def _search(p: pd.DataFrame, trials: int, tag: str) -> dict:
        positions_out: dict[str, dict] = {}
        pvals: dict[str, float | None] = {}
        for pos in M15.POSITIONS:
            bundles = M15.effective_bundles(pos)
            null_rec = walk_forward_pos(
                p, pos, lambda: M13.make_pos_learner("pos_null", feats=()), scored_targets,
                "pos_null")
            ref = nf11.get(pos)
            ref_rec = None
            if ref:
                ref_rec = walk_forward_pos(
                    p, pos,
                    lambda ref=ref, pos=pos: M15.make_blind_learner(
                        ref["learner"], feats=M12.BASE_POSITION_FEATURES[pos], **ref["hp"]),
                    scored_targets, f"nf1_1_winner({ref['learner']})", ref["hp"],
                    bundle="base_xfp")
            trial_records: list[dict] = ([ref_rec] if ref_rec else [])
            best_by_cell: dict[str, dict] = {}
            for name in M15.BLIND_CANDIDATES:
                for bname, feats in bundles.items():
                    recs = _optuna_tune(
                        p, pos, name,
                        lambda hp, n=name, f=feats: (lambda: M15.make_blind_learner(n, feats=f, **hp)),
                        scored_targets, trials, bundle=bname)
                    trial_records.extend(recs)
                    if recs and np.isfinite(_finite_top(recs[0])):
                        best_by_cell[f"{name}×{bname}"] = recs[0]
                log.info("  [%s] %s %-14s swept %d bundles", tag, pos, name, len(bundles))
            if not best_by_cell:
                positions_out[pos] = {"null": null_rec, "note": "no scoreable candidate"}
                pvals[pos] = None
                continue
            winner = max(best_by_cell.values(), key=_finite_top)
            defl = _deflate(trial_records, null_rec, winner, scored_targets)
            pvals[pos] = defl["pvalue"]
            # compact cell table: best per class×bundle (means only)
            cells = {cell: {"mean_top": r["mean_top"]} for cell, r in best_by_cell.items()}
            positions_out[pos] = {
                "null": null_rec,
                "nf1_1_winner_ref": ({k: ref_rec[k] for k in ("learner", "hp", "mean_top")}
                                     if ref_rec else None),
                "bundles": {b: list(f) for b, f in bundles.items()},
                "best_by_cell": cells,
                "winner": winner, **defl,
                "beats_null": bool(winner["mean_top"] is not None and null_rec["mean_top"] is not None
                                   and winner["mean_top"] > null_rec["mean_top"]),
                "beats_nf1_1_ref": bool(winner["mean_top"] is not None and ref_rec is not None
                                        and ref_rec["mean_top"] is not None
                                        and winner["mean_top"] > ref_rec["mean_top"]),
            }
        fdr = M15.bh_fdr(pvals)
        for pos, r in positions_out.items():
            if "winner" not in r:
                r["verdict"] = {"repoint": False, "note": "unscoreable"}
                continue
            r["fdr_pass"] = bool(fdr.get(pos, False))
            r["verdict"] = M15.position_verdict(r["beats_null"], r["pbo"], r["dsr"], r["fdr_pass"])
        return positions_out

    log.info("STAGE 2 (blind ceiling-proof): pool %d rows, targets %s", len(pool), scored_targets)
    positions = _search(pool, n_trials, "real")
    log.info("STAGE 2 placebo (shuffled labels, %d trials)", placebo_trials)
    placebo = _search(M15.placebo_shuffle(pool, PLACEBO_SEED), placebo_trials, "placebo")
    placebo_summary = {
        pos: {"winner_mean_top": r.get("winner", {}).get("mean_top"),
              "null_mean_top": r.get("null", {}).get("mean_top"),
              "naive_delta_vs_null": (round(r["winner"]["mean_top"] - r["null"]["mean_top"], 4)
                                      if r.get("winner", {}).get("mean_top") is not None
                                      and r.get("null", {}).get("mean_top") is not None else None),
              "gates_pass": bool(r.get("verdict", {}).get("repoint", False))}
        for pos, r in placebo.items()}
    return {
        "stage": "blind_ceiling_proof",
        "pool_base_seasons": [int(pool["base_season"].min()), int(pool["base_season"].max())]
        if "base_season" in pool.columns else None,
        "score_from": score_from,
        "target_seasons": scored_targets, "n_pool": int(len(pool)),
        "selection_metric": f"top-tier within-position ρ (tier = top-N by the MVP-1 incumbent, N={M15.TOP_N})",
        "oracle_metric_ok": bool(oracle_ok),
        "n_trials_per_cell": n_trials, "placebo_trials": placebo_trials,
        "bundle_registry": {b: list(f) for b, f in M15.BLIND_BUNDLES.items()},
        "candidates": list(M15.BLIND_CANDIDATES),
        "positions": positions,
        "placebo": placebo_summary,
        "pbo_max": M15.PBO_MAX, "dsr_min": M15.DSR_MIN, "fdr_q": M15.FDR_Q,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Board / grade / calibration / serving recommendation
# ══════════════════════════════════════════════════════════════════════════════════════════════
def load_selection(report: dict, board: str = "beats-incumbent") -> dict[str, dict]:
    """Per-position stage-1 selection for the refined board. `board`: 'beats-incumbent' = winners
    that beat the NF1.3 stored incumbent (positions that don't, keep the NF1.3 incumbent);
    'gated' = full-deflation survivors only. Positions with neither fall back to the NF1.3
    incumbent (or MVP-1 when NF1.3 has none)."""
    _, nf13 = _load_incumbents()
    sel: dict[str, dict] = {}
    for pos, r in report.get("stage1", {}).get("positions", {}).items():
        use_winner = False
        if "winner" in r:
            use_winner = (r["verdict"]["repoint"] if board == "gated"
                          else bool(r.get("beats_nf1_3_incumbent")))
        if use_winner:
            sel[pos] = {"learner": r["winner"]["learner"], "hp": r["winner"]["hp"],
                        "source": "nf1_5_refined"}
        elif pos in nf13:
            sel[pos] = {"learner": nf13[pos]["learner"], "hp": nf13[pos]["hp"],
                        "source": "nf1_3_incumbent"}
    return sel


def _make_selected_learner(pos: str, sel: dict, nf11: dict):
    name = sel["learner"]
    if name in M15._STAGE1_VARIANTS:
        return M15.make_stage1_learner(name, inner=_anchor_spec(pos, nf11), **sel["hp"])
    return M13.make_pos_learner(name, feats=M13.POSITION_FEATURES[pos], **sel["hp"])


def learned_scores_by_player(con, base_season: int, projection_season: int, schema: str,
                             selections: dict[str, dict], inputs,
                             pool: pd.DataFrame) -> dict[str, float]:
    """`{player_id -> learned ordering score}` for the selected positions, fit on ALL completed
    history in `pool` and applied to the NF1.5 research feature frame for `projection_season`.

    Keyed by player rather than returned as a per-position array because the frame it is APPLIED to
    (the shipped board) is a different, wider universe than the frame it is COMPUTED on — see
    `build_season_projection`."""
    nf11, _ = _load_incumbents()
    feats = build_extended_frame(con, base_season, projection_season, inputs, schema)
    if feats.empty:
        return {}
    feats = attach_market(con, feats, schema)
    out: dict[str, float] = {}
    for pos, sel in selections.items():
        tr = pool[pool["position"] == pos] if not pool.empty else pd.DataFrame()
        learner = _make_selected_learner(pos, sel, nf11)
        if len(tr) >= 30:
            learner.fit(tr, tr["real_fp_ppr"].to_numpy())
        te = feats[feats["position"] == pos]
        if te.empty:
            continue
        s = np.asarray(learner.predict(te), dtype=float)
        for pid, v in zip(te["player_id"].astype(str), s):
            if np.isfinite(v):
                out[pid] = float(v)
    return out


def build_season_projection(con, base_season: int, projection_season: int, schema: str,
                            selections: dict[str, dict], inputs, base_from: int = 2017,
                            pool: pd.DataFrame | None = None,
                            band_panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """The NF1.5 refined board = **the SHIPPED MVP-1 board with the veteran ORDER re-assigned**.

    ⭐ NF1.5b REBUILT THIS AS A TRANSFORM OF THE SHIPPED BOARD rather than a parallel assembly, and
    that is the whole substance of the re-land. The refined board is ORDERING-ONLY by design (each
    position's players are handed that position's own MVP-1 point multiset in learned-rank order), so
    everything except the order must be INHERITED. The previous implementation re-derived the board
    from `run_nf1_2.build_extended_frame`'s research frame instead, and drifted on three axes that
    all reached users:

      * **UNIVERSE** — the research frame is assembled from `load_base_season` WITHOUT NF-D11's
        base-anchor rescue, so the refined board carried **716 players against the shipped 784**: 68
        returning veterans would have VANISHED from the draft board on the flip.
      * **INTERVAL** — it re-priced every band as `point ± 1.2816·κ·sd`, i.e. the PRE-NF1.9 normal
        approximation whose measured coverage is ~0.55 of its nominal 0.80, and stamped it
        `calibrated`. Flipping the served board would have silently reverted the NF1.9 per-player
        band (`calibrated_per_player`) on ~90% of the draft board — a straight regression of the
        exact quantity NF1.7/1.8/1.9 exist to protect.
      * **ROOKIES / provenance** — a private copy of the rookie leg, drifting from the shipped one
        (which now carries NF-D16's held opt-in and NF-D11's confidence demotion).

    Now: the shipped `build_projection` runs unchanged, and the re-order is injected as its
    `veteran_postprocess` hook. The interval is re-derived through MVP-1's OWN
    `attach_season_interval` at the new level (an interval must follow the point it prices), so the
    refined board serves the NF1.9 per-player band exactly as the incumbent does.

    ⚠️ ORDERING-ONLY is enforced, not asserted: the per-position point MULTISET is unchanged by
    construction (a within-position permutation), so the board's estimand — MVP-1's calibrated point
    level — is preserved. What NF1.5 changes is WHICH player gets which level.

    A veteran the research frame cannot score (the rescued 68) is left EXACTLY as MVP-1 projected
    him — point, line and band — via `apply_learned_ordering(eligible=...)`. Guessing his rank from
    his MVP-1 points would interleave two different scales."""
    if pool is None:
        base_seasons = [b for b in range(base_from, base_season) if b + 1 < projection_season]
        pool = build_pool(con, base_seasons, schema) if selections else pd.DataFrame()

    scores = (learned_scores_by_player(con, base_season, projection_season, schema, selections,
                                       inputs, pool) if selections else {})
    positions = tuple(p for p in M1.LEARN_POSITIONS if p in selections)
    scale_by_pid: dict[str, float] = {}

    def _reorder(vets: pd.DataFrame, band_model):
        pid = vets["player_id"].astype(str)
        elig = pid.isin(scores).to_numpy()
        score = np.array([scores.get(x, np.nan) for x in pid], dtype=float)
        n_by_pos = {p: int(((vets["position"] == p) & elig).sum()) for p in positions}
        log.info("refined re-order: %d/%d veterans scored %s; %d left at their MVP-1 level",
                 int(elig.sum()), len(vets), n_by_pos, int((~elig).sum()))
        out = M1.apply_learned_ordering(vets, score, positions=positions, eligible=elig)
        out = SP.score_line(out, prefix="proj_")
        # `nf1_scale` is the per-row raw-line rescale the re-level needed. Stashed here because
        # `build_projection` trims to `OUTPUT_COLS` and would drop it — and it is the diagnostic that
        # says whether the CLAMP bound (0.30/3.5) is binding, which is the one way a within-multiset
        # promotion can silently fail to land on its assigned level.
        scale_by_pid.update(zip(out["player_id"].astype(str),
                                pd.to_numeric(out["nf1_scale"], errors="coerce")))
        sat = int(((out["nf1_scale"] <= 0.3001) | (out["nf1_scale"] >= 3.4999)).sum())
        if sat:
            log.warning("[ALERT] %d veteran row(s) SATURATED the raw-line rescale clamp — their "
                        "served points cannot reach the level the ordering assigned them", sat)
        # the interval must follow the point it prices — re-derived through MVP-1's own code, so the
        # refined board carries the SAME NF1.9 per-player band tier the incumbent does
        return SP.attach_season_interval(out, band_model=band_model)

    proj = build_projection(con, base_season, projection_season, schema,
                            band_panel=band_panel, veteran_postprocess=_reorder)

    # ── provenance: which learner ordered each row, and how market-leaning it is ───────────────
    is_rk = proj["is_rookie"].astype(bool).to_numpy()
    pos_arr = proj["position"].to_numpy()
    proj["nf1_5_learner"] = np.where(
        is_rk, "rookie_slot_curve",
        [(selections[p]["learner"] if p in selections else "mvp1_null") for p in pos_arr])
    proj["nf1_5_blend_w"] = np.where(is_rk, np.nan, [
        (float(selections[p]["hp"].get("blend_w", np.nan)) if p in selections else np.nan)
        for p in pos_arr])
    proj["nf1_5_disp_slope"] = np.where(is_rk, np.nan, [
        (float(selections[p]["hp"].get("disp_slope", np.nan)) if p in selections else np.nan)
        for p in pos_arr])
    proj["market_lean"] = np.where(is_rk, "independent", [
        (_market_lean(selections[p]) if p in selections else "independent") for p in pos_arr])
    proj["nf1_scale"] = [scale_by_pid.get(str(p), np.nan) for p in proj["player_id"]]
    proj["model_version"] = M15.MODEL_VERSION
    cols = OUTPUT_COLS + [c for c in NF1_5_EXTRA_COLS if c not in OUTPUT_COLS]
    for c in cols:
        if c not in proj.columns:
            proj[c] = np.nan
    return proj[cols].sort_values("proj_fp_ppr", ascending=False).reset_index(drop=True)


def _market_lean(sel: dict) -> str:
    """Honest per-position provenance for the served board (the NF1.3 label scheme extended for
    the refinement family — an adaptive blend is labelled by its BASE weight)."""
    name = sel["learner"]
    if name == "pos_market_only":
        return "market-consensus"
    if name in M15._STAGE1_VARIANTS or name == "pos_market_blend":
        w = float(sel["hp"].get("blend_w", 0.0))
        adaptive = float(sel["hp"].get("disp_slope", 0.0)) > 0
        base = ("market-led" if w >= 0.66 else "market-blend" if w >= 0.33 else "independent-lean")
        return base + ("-adaptive" if adaptive else "")
    return "market-informed"


def verify_season_interval(con, base_from: int, base_to: int, schema: str,
                           selections: dict[str, dict], inputs) -> dict:
    """Does the SERVED 80% band still cover 0.80 once the veteran ORDER is re-assigned?

    ⭐ NF1.5b replaced a κ CALIBRATION with a COVERAGE VERIFY, and the difference is the point. The
    old version tuned a dispersion multiplier κ and the board applied it — a second, NF1.5-private
    interval model layered on top of the shipped one. The refined board now re-derives MVP-1's own
    NF1.9 per-player band at the re-assigned level (`season_projection.attach_season_interval`), so
    there is no κ to fit: the only open question is whether the SAME band, moved onto a different
    player, still covers. That is a check, not a knob.

    ⚠️ COVERAGE IS A **FLOOR**, NEVER A TARGET (E2.1-r / NF1.8): this reports how far ABOVE 0.80 the
    band lands and never rescales toward it. Reported per position as well as pooled, because a
    pooled number can hide a position that broke (NF1.8's per-group floor lesson), and pooled over
    ROWS — not as a mean of per-season means — for the same reason.

    Held-out by construction: for each target season Y the board is built from base season Y-1 with
    a band fitted only on panel seasons strictly before Y."""
    per_season, rows = {}, []
    for y in range(base_from + 1, base_to + 2):
        if y - 1 < base_from:
            continue
        proj = build_season_projection(con, y - 1, y, schema, selections, inputs,
                                       base_from=base_from)
        real = load_realized_season(con, y, schema)
        m = proj[~proj["is_rookie"].astype(bool)].merge(real, on="player_id", how="inner")
        m = m[m["g"] >= 6]
        if len(m) < 30:
            continue
        hit = ((m["real_fp_ppr"] >= m["fp_ppr_p10"])
               & (m["real_fp_ppr"] <= m["fp_ppr_p90"])).to_numpy()
        per_season[y] = round(float(hit.mean()), 3)
        rows.append(pd.DataFrame({"position": m["position"].to_numpy(), "hit": hit,
                                  "width": (m["fp_ppr_p90"] - m["fp_ppr_p10"]).to_numpy()}))
    if not rows:
        return {"note": "insufficient holdout"}
    allrows = pd.concat(rows, ignore_index=True)
    by_pos = {p: {"calib_80": round(float(g["hit"].mean()), 3),
                  "mean_width": round(float(g["width"].mean()), 1), "n": int(len(g))}
              for p, g in allrows.groupby("position")}
    return {"calib_80": round(float(allrows["hit"].mean()), 3),
            "per_position": by_pos, "per_season": per_season,
            "mean_width": round(float(allrows["width"].mean()), 1),
            "floor": 0.80, "n": int(len(allrows)),
            "uncertainty_tiers": {str(k): int(v) for k, v in
                                  proj["uncertainty_type"].value_counts().items()}}


def grade_vs_consensus(con, seasons: list[int], schema: str, selections: dict[str, dict],
                       inputs, base_from: int = 2017) -> dict:
    """The NF-D3 product-metric scorecard over the refined board — same scorer/universes as the
    stored MVP-1 / NF1 / NF1.1 / NF1.2 / NF1.3 runs."""
    from quant_sports_intel_models.football.nfl.fantasy import benchmark_scorecard as BS

    def project_fn(c, y, sch):
        return build_season_projection(c, y - 1, y, sch, selections, inputs, base_from=base_from)[
            ["player_id", "position", "proj_fp_ppr"]]

    return BS.build_scorecard(con, seasons, schema, project_fn=project_fn,
                              load_realized_fn=load_realized_season)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Combined report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _fmt(v, sign=False):
    if v is None:
        return "—"
    return f"{v:+.4f}" if sign else f"{v:.4f}"


def _load_report(suffix: str) -> dict:
    p = _REPORT_DIR / f"nf1_5_feature_combination_bakeoff{suffix}.json"
    return json.loads(p.read_text()) if p.exists() else {"model_version": M15.MODEL_VERSION}


def _save_report(report: dict, suffix: str) -> None:
    report["model_version"] = M15.MODEL_VERSION
    report["updated_at"] = datetime.now(timezone.utc).isoformat()
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"nf1_5_feature_combination_bakeoff{suffix}.json").write_text(
        json.dumps(report, indent=2, default=float))
    write_report_md(report, _REPORT_DIR / f"nf1_5_feature_combination_bakeoff{suffix}.md")


def write_report_md(report: dict, path: Path) -> None:
    a = []
    p = a.append
    p("# NF1.5 — CAPSTONE feature-combination bake-off (market-aware refinements + the "
      "market-blind ceiling proof)")
    p("")
    p(f"**Model:** `{report.get('model_version')}` · **updated:** {report.get('updated_at')}")
    p("")
    p("> 🔒 **HONEST FRAME:** stage 1's bar is the NF1.3 STORED incumbent per position (the "
      "market-aware winner); stage 2's bar is the market-blind MVP-1 null — with the blind space "
      "exhausted 4×, a clean stage-2 NULL is the LIKELY + valuable outcome (it PROVES the "
      "incumbent is the feature-library ceiling). At market-leaning positions we INCORPORATE "
      "consensus and ⛔ never claim to beat the market we use. `best_alpha = 0`.")
    p("")
    s1 = report.get("stage1")
    if s1:
        p("## Stage 1 — MARKET-AWARE refinements (PRIMARY: blend-vs-learned + dispersion-weighted)")
        p("")
        p(f"targets {s1['target_seasons']} · pool {s1['n_pool']} · {s1['n_trials_per_class']} "
          f"trials/class · oracle sane: {s1['oracle_metric_ok']} · market top-tier coverage "
          f"{s1.get('market_top_tier_coverage')}")
        p("")
        for pos, r in s1["positions"].items():
            p(f"### {pos}")
            p("")
            if "winner" not in r:
                p(f"- unscoreable ({r.get('note')})")
                p("")
                continue
            rows = [{"candidate": "pos_null (MVP-1, blind)", "top-tier ρ": _fmt(r["null"]["mean_top"]), "hp": ""},
                    {"candidate": "pos_market_only (consensus)", "top-tier ρ": _fmt(r["market_only"]["mean_top"]), "hp": ""}]
            if r.get("nf1_3_incumbent"):
                rows.append({"candidate": f"NF1.3 incumbent ({r['nf1_3_incumbent']['learner']}) 🔒",
                             "top-tier ρ": _fmt(r["nf1_3_incumbent"]["mean_top"]),
                             "hp": json.dumps(r["nf1_3_incumbent"]["hp"])})
            for name, rec in r["best_by_class"].items():
                tag = " ⭐" if rec is r["winner"] else ""
                rows.append({"candidate": name + tag, "top-tier ρ": _fmt(rec["mean_top"]),
                             "hp": json.dumps(rec["hp"])})
            p(pd.DataFrame(rows).to_markdown(index=False))
            p("")
            v = r["verdict"]
            p(f"- **winner:** `{r['winner']['learner']}` · beats NF1.3 incumbent: "
              f"**{r['beats_nf1_3_incumbent']}** (Δ {_fmt(r['delta_vs_nf1_3_incumbent'], sign=True)}) "
              f"· beats blind null: {r['beats_null']} · beats pure consensus: {r['beats_market_only']}")
            p(f"- **deflation** ({r['n_configs']} configs): PBO {_fmt(r['pbo'])} (spread "
              f"{_fmt(r['config_spread'])}) · DSR {_fmt(r['dsr'])} · p {_fmt(r['pvalue'])} · "
              f"FDR pass {r.get('fdr_pass')}")
            p(f"- **verdict (vs the NF1.3 incumbent + full gates):** "
              f"{'REPOINT-ELIGIBLE' if v['repoint'] else 'NULL — the NF1.3 incumbent stands'} "
              f"({', '.join(k for k, ok in v.items() if k != 'repoint' and not ok) or 'all gates pass'})")
            p("")
        p("**Placebo (labels shuffled within position×season — the same search must find nothing):**")
        p("")
        p(pd.DataFrame([{"pos": k, **v} for k, v in s1.get("placebo", {}).items()]).to_markdown(index=False))
        p("")
    s2 = report.get("stage2")
    if s2:
        p("## Stage 2 — MARKET-BLIND combination sweep (ceiling proof; expected null)")
        p("")
        p(f"targets {s2['target_seasons']} · pool {s2['n_pool']} · {s2['n_trials_per_cell']} "
          f"trials/cell · bundles: {list(s2['bundle_registry'])} · candidates: {s2['candidates']} "
          f"· oracle sane: {s2['oracle_metric_ok']}")
        p("")
        for pos, r in s2["positions"].items():
            p(f"### {pos}")
            p("")
            if "winner" not in r:
                p(f"- unscoreable ({r.get('note')})")
                p("")
                continue
            cells = pd.DataFrame([{"class×bundle": c, "top-tier ρ": _fmt(v["mean_top"])}
                                  for c, v in r["best_by_cell"].items()])
            cells = cells.sort_values("top-tier ρ", ascending=False)
            p(cells.to_markdown(index=False))
            p("")
            v = r["verdict"]
            ref = r.get("nf1_1_winner_ref")
            p(f"- null (MVP-1) {_fmt(r['null']['mean_top'])}"
              + (f" · NF1.1 winner ref {_fmt(ref['mean_top'])}" if ref else ""))
            p(f"- **winner:** `{r['winner']['learner']}` × `{r['winner'].get('bundle')}` "
              f"ρ {_fmt(r['winner']['mean_top'])} · beats null: **{r['beats_null']}** · "
              f"beats NF1.1 ref: {r.get('beats_nf1_1_ref')}")
            p(f"- **deflation** ({r['n_configs']} configs): PBO {_fmt(r['pbo'])} (spread "
              f"{_fmt(r['config_spread'])}) · DSR {_fmt(r['dsr'])} · p {_fmt(r['pvalue'])} · "
              f"FDR pass {r.get('fdr_pass')}")
            p(f"- **verdict:** {'REPOINT-ELIGIBLE' if v['repoint'] else 'NULL — the incumbent stands'} "
              f"({', '.join(k for k, ok in v.items() if k != 'repoint' and not ok) or 'all gates pass'})")
            p("")
        p("**Placebo (labels shuffled — the same sweep must find nothing):**")
        p("")
        p(pd.DataFrame([{"pos": k, **v} for k, v in s2.get("placebo", {}).items()]).to_markdown(index=False))
        p("")
    rec = report.get("serving_recommendation")
    if rec:
        p("## Serving decision (NF1.5-owned)")
        p("")
        p(f"- **serve:** `{rec['serve']}`")
        p(f"- why: {rec['why']}")
        p(f"- calibration verify: calib_80 = {rec.get('calib_80')} (floor 0.80, tolerance ≥0.78) · "
          f"product Δρ-vs-ADP (refined − NF1.3): {rec.get('product_delta_vs_nf1_3')}")
        p("")
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _connect(duckdb_path: str):
    import duckdb
    if not Path(duckdb_path).exists():
        raise SystemExit(f"DuckDB not found at {duckdb_path} — build the NFL marts first")
    return duckdb.connect(duckdb_path, read_only=True)


def _resolve_build_base_season(latest_played_season: int, proj_season: int) -> int:
    """NF3.2 — the base season `--mode build` anchors a projection on.

    For the FORWARD (current) build, `proj_season == latest_played_season + 1` and the latest played
    season IS the correct base — the pre-existing, unchanged behavior. For a PAST-season (backtest)
    build (`--projection-season <a past year>`), anchoring on the latest played season would build
    that past season's board off data from AFTER it — a leakage-safe holdout inverted, and silently
    so (nothing about the output shape signals it). The base must instead be `proj_season - 1`, the
    same convention `run_season_projection.build_projection` itself uses. This is what makes NF3.2's
    per-past-season NF1.5 board builds (`--mode build --projection-season 2019`, `2020`, …) genuine
    holdouts rather than the forward build's base repeated onto a different projection season."""
    return proj_season - 1 if proj_season <= latest_played_season else latest_played_season


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF1.5 — capstone feature-combination bake-off")
    ap.add_argument("--mode", required=True, choices=["market", "blind", "grade", "build"])
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--base-from", type=int, default=2017)
    ap.add_argument("--base-to", type=int, default=2024)
    ap.add_argument("--projection-season", type=int, default=None)
    ap.add_argument("--n-trials", type=int, default=None,
                    help="Optuna trials (default: 40 for market, 15 per cell for blind)")
    ap.add_argument("--score-from", type=int, default=None,
                    help="market/blind: first SCORED target season (training still uses every "
                         "earlier pool season — the data-expansion lever). E.g. --base-from 2006 "
                         "--score-from 2010 scores 16 seasons off a 20-season pool.")
    ap.add_argument("--placebo-trials", type=int, default=None,
                    help="placebo search trials (default: n_trials // 4, min 2)")
    ap.add_argument("--board", choices=["gated", "beats-incumbent"], default="beats-incumbent",
                    help="grade/build: which stage-1 winners repoint (default beats-incumbent; "
                         "positions without a win keep the NF1.3 incumbent)")
    ap.add_argument("--seasons", default=None, help="grade: comma seasons (default 2019-2024)")
    ap.add_argument("--no-cache", action="store_true", help="rebuild the feature pool cache")
    ap.add_argument("--smoke", action="store_true", help="tiny subset; writes *_smoke reports")
    ap.add_argument("--s3", action="store_true", help="build: land the projection to S3")
    ap.add_argument("--lake-root", default=None)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    suffix = "_smoke" if args.smoke else ""
    con = _connect(args.duckdb)
    try:
        if args.mode in ("market", "blind"):
            bf, bt = (2019, 2022) if args.smoke else (args.base_from, args.base_to)
            default_trials = 40 if args.mode == "market" else 15
            n_trials = 2 if args.smoke else (args.n_trials or default_trials)
            placebo_trials = 1 if args.smoke else (args.placebo_trials or max(2, n_trials // 4))
            pool = build_pool(con, list(range(bf, bt + 1)), args.schema,
                              use_cache=not args.no_cache)
            if pool.empty:
                raise SystemExit("empty training pool — build the NFL marts first")
            report = _load_report(suffix)
            # a re-run (e.g. the data-expansion re-bake-off) ARCHIVES the stage it replaces —
            # every config stays logged, nothing is silently overwritten (no-cherry-pick AC)
            stage_key = "stage1" if args.mode == "market" else "stage2"
            if stage_key in report:
                report.setdefault("archived_stages", []).append(report[stage_key])
            if args.mode == "market":
                report["stage1"] = run_market_stage(pool, n_trials, placebo_trials,
                                                    score_from=args.score_from)
                for pos, r in report["stage1"]["positions"].items():
                    if "winner" in r:
                        print(f"{pos}: winner={r['winner']['learner']} hp={r['winner']['hp']} "
                              f"ρ={r['winner']['mean_top']} (nf1_3_inc "
                              f"{(r.get('nf1_3_incumbent') or {}).get('mean_top')}, null "
                              f"{r['null']['mean_top']}) beats_incumbent={r['beats_nf1_3_incumbent']} "
                              f"PBO={r['pbo']} DSR={r['dsr']} repoint={r['verdict']['repoint']}")
            else:
                report["stage2"] = run_blind_stage(pool, n_trials, placebo_trials,
                                                   score_from=args.score_from)
                for pos, r in report["stage2"]["positions"].items():
                    if "winner" in r:
                        print(f"{pos}: winner={r['winner']['learner']}×{r['winner'].get('bundle')} "
                              f"ρ={r['winner']['mean_top']} (null {r['null']['mean_top']}) "
                              f"beats_null={r['beats_null']} PBO={r['pbo']} DSR={r['dsr']} "
                              f"repoint={r['verdict']['repoint']}")
            _save_report(report, suffix)

        elif args.mode == "grade":
            report = _load_report(suffix)
            if "stage1" not in report:
                raise SystemExit("run --mode market first (grade reads its stage-1 selections)")
            selections = load_selection(report, board=args.board)
            log.info("grading board=%s selections=%s", args.board,
                     {p: (s["learner"], s["source"]) for p, s in selections.items()})
            seasons = ([2023] if args.smoke
                       else [int(s) for s in (args.seasons or "2019,2020,2021,2022,2023,2024").split(",")])
            base_seasons = list(range(args.base_from, max(seasons)))
            inputs = load_inputs(con, base_seasons, args.schema)
            sc = grade_vs_consensus(con, seasons, args.schema, selections, inputs,
                                    base_from=args.base_from)
            sc["board"] = args.board
            sc["selections"] = selections
            cal = verify_season_interval(con, args.base_from,
                                         min(args.base_to, max(seasons) - 1),
                                         args.schema, selections, inputs)
            sc["interval_verify"] = cal
            (_REPORT_DIR / f"nf1_5_vs_consensus_scorecard{suffix}.json").write_text(
                json.dumps(sc, indent=2, default=float))
            print(json.dumps(sc.get("aggregate", {}), indent=2, default=float))
            print(f"interval verify (coverage is a FLOOR): {json.dumps(cal, default=float)}")

            # the serving recommendation: refined vs the stored NF1.3 scorecard on Δρ-vs-ADP pooled
            nf13_adp = None
            if _NF1_3_SCORECARD.exists():
                nf13_adp = (json.loads(_NF1_3_SCORECARD.read_text())
                            .get("aggregate", {}).get("adp", {}).get("delta_rho_pooled"))
            ours_adp = sc.get("aggregate", {}).get("adp", {}).get("delta_rho_pooled")
            product_delta = (round(ours_adp - nf13_adp, 4)
                             if ours_adp is not None and nf13_adp is not None else None)
            s1 = report["stage1"]["positions"]
            rec = M15.serving_recommendation(
                refined_beats_incumbent={p: bool(r.get("beats_nf1_3_incumbent"))
                                         for p, r in s1.items() if "winner" in r},
                refined_gates={p: r.get("verdict", {}) for p, r in s1.items()},
                product_delta_vs_nf1_3=product_delta,
                calib_80=cal.get("calib_80"))
            report["serving_recommendation"] = rec
            _save_report(report, suffix)
            print(f"serving recommendation: {rec['serve']} — {rec['why']}")

        elif args.mode == "build":
            report = _load_report(suffix)
            if "stage1" not in report:
                raise SystemExit("run --mode market first (build reads its stage-1 selections)")
            selections = load_selection(report, board=args.board)
            log.info("building board=%s selections=%s", args.board,
                     {p: (s["learner"], s["source"]) for p, s in selections.items()})
            latest_played_season = int(con.sql(
                f"select max(season) from {args.schema}.fct_player_week where played_flag").fetchone()[0])
            proj_season = args.projection_season or (latest_played_season + 1)
            base_season = _resolve_build_base_season(latest_played_season, proj_season)
            base_seasons = [b for b in range(args.base_from, base_season) if b + 1 < proj_season]
            inputs = load_inputs(con, sorted(set(base_seasons + [base_season])), args.schema)
            # NF1.5b: no κ to fit — the band is MVP-1's own NF1.9 per-player band, re-derived at the
            # re-assigned level. The held-out coverage VERIFY lives in `--mode grade`.
            proj = build_season_projection(con, base_season, proj_season, args.schema, selections,
                                           inputs, base_from=args.base_from)
            cal = {"note": "band inherited from the shipped NF1.9 per-player fit; "
                           "held-out coverage verified in --mode grade",
                   "uncertainty_tiers": {str(k): int(v) for k, v in
                                         proj["uncertainty_type"].value_counts().items()}}
            log.info("NF1.5 %d: %d players (%d vets, %d rookies); interval tiers %s",
                     proj_season, len(proj), int((~proj["is_rookie"]).sum()),
                     int(proj["is_rookie"].sum()), cal["uncertainty_tiers"])
            _ART.mkdir(parents=True, exist_ok=True)
            proj.to_parquet(_ART / f"nf1_5_season_projections_{proj_season}.parquet", index=False)
            ranked = proj.copy()
            ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
            ranked.insert(1, "pos_rank", ranked.groupby("position").cumcount() + 1)
            ranked.to_csv(_ART / f"nf1_5_season_projections_{proj_season}_ranked.csv", index=False)
            if args.s3 or args.lake_root:
                from quant_sports_intel_models.football.nfl.ingest import s3io
                n = s3io.write_dataframe(proj.assign(season=int(proj_season)), sport="nfl",
                                         source="nf1_5_season_projections", season=int(proj_season),
                                         tier="fantasy/derived", local_root=args.lake_root)
                log.info("landed %d rows → nfl/fantasy/derived/nf1_5_season_projections season=%d",
                         n, proj_season)
            (_ART / f"nf1_5_projection_summary_{proj_season}.json").write_text(json.dumps({
                "model_version": M15.MODEL_VERSION, "board": args.board, "selections": selections,
                "market_lean": {p: _market_lean(s) for p, s in selections.items()},
                "projection_season": proj_season, "interval": cal,
                "n_players": int(len(proj)), "generated_at": datetime.now(timezone.utc).isoformat(),
            }, indent=2, default=float))
            print(f"NF1.5 {proj_season} built (board={args.board}); interval tiers "
                  f"{cal['uncertainty_tiers']}; top: "
                  + ", ".join(proj.head(5)["player_name"].tolist()))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
