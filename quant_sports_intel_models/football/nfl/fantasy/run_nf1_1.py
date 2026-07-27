"""run_nf1_1.py — NF1.1 CLI/IO: the per-position §0.5 bake-off, the deflation gate, build + grade.

NF1.1 = PER-POSITION INDEPENDENT models re-selected on the TOP-TIER (draftable) metric — the two
fixes NF1 v1's own verdict prescribed (`nf1_1_model.py` is the pure logic; read its docstring for
the full design). This module does the DuckDB reads (SF-free sports lake), the leakage-safe
walk-forward orchestration (candidate learners × Optuna per position, EVERY trial counted toward
the deflation), the NF-D3 product grade, and the S3 landing.

⭐ RUN ON THE LAPTOP (like run_nf1): SF-free, sports-lake DuckDB, S3 I/O only, zero shared-box CPU.
`SPORTS_LAKE_REGION=us-east-2` for the S3 read/write.

MODES:
  * `bakeoff` — the per-position §0.5 selection: for each of QB/RB/WR/TE, Optuna-tune pos_ridge /
                pos_gbm / pos_similarity on the walk-forward held-out TOP-TIER ρ (tier anchored on
                the MVP-1 incumbent — fixed across candidates), against the MVP-1 per-position null;
                deflate the FULL search (CSCV-PBO / DSR / BH-FDR across positions); drop-one-group
                feature ablation on each winner. → ablation_results/nf1_1_per_position.{md,json}
  * `grade`   — the PRODUCT-metric verdict: build the NF1.1 board per season (per-position winners
                from the bake-off json) and run the NF-D3 consensus scorecard apples-to-apples.
                → ablation_results/nf1_1_vs_consensus_scorecard.json
  * `build`   — the final projection: per-position winners fit on all history, applied as ORDERING
                only (`apply_learned_ordering` — MVP-1's calibrated point multiset per position),
                calibrated 80% interval, landed to its OWN S3 prefix
                `nfl/fantasy/derived/nf1_1_season_projections` (never overwrites MVP-1 or NF1).

Heavy runs (the full bake-off, the 6-season grade) are >1 min ⇒ hand them to the operator;
`--smoke` runs a tiny subset (and writes `*_smoke` reports so a smoke never clobbers the real one).
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

from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M11  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_model as M1  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import xfp_source as X  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.run_nf1 import (  # noqa: E402
    assemble_features,
    build_training_pool,
)
from quant_sports_intel_models.football.nfl.fantasy.run_season_projection import (  # noqa: E402
    MARTS_SCHEMA,
    OUTPUT_COLS,
    fit_rookie_slot_curves,
    load_realized_season,
    load_rookie_training,
    project_rookies,
    _ROOKIE_PARQUET,
)

log = logging.getLogger("nfl.fantasy.nf1_1")

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"

NF1_1_EXTRA_COLS = ["nf1_scale", "nf1_1_learner"]

_LEARNED_CANDIDATES = ("pos_ridge", "pos_gbm", "pos_similarity")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Feature assembly — the NF1 pool + the NF-D7 xFP features (assemble-once via the existing caches)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def attach_xfp(con, frame: pd.DataFrame, schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    """LEFT-JOIN the leakage-safe NF-D7 xFP features onto a feature frame, per BASE season (each
    row's xFP window ends at its own `base_season` — nothing peeks forward). A base season with no
    play-by-play coverage leaves the columns NaN (the learners impute; the null ignores them)."""
    if frame.empty or "base_season" not in frame.columns:
        return frame
    frames = []
    for b, grp in frame.groupby("base_season", sort=True):
        feats = X.load_xfp_features(con, int(b), schema)
        cols = ["player_id", *M11.XFP_FEATURES]
        if feats.empty or any(c not in feats.columns for c in cols):
            grp = grp.copy()
            for c in M11.XFP_FEATURES:
                grp[c] = np.nan
            frames.append(grp)
        else:
            frames.append(grp.merge(feats[cols], on="player_id", how="left"))
    return pd.concat(frames, ignore_index=True, sort=False)


def build_pool(con, base_seasons: list[int], schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    """The NF1 walk-forward training pool (cached per base season) + the xFP feature join."""
    pool = build_training_pool(con, base_seasons, schema)
    return attach_xfp(con, pool, schema)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Per-position walk-forward scoring (the selection loop's inner unit)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def walk_forward_pos(pool: pd.DataFrame, pos: str, name: str, hp: dict,
                     feats: tuple[str, ...], target_seasons: list[int]) -> dict:
    """Backtest ONE (position, learner, hp) config: for each target season Y, fit on that position's
    pool rows with `target_season < Y` (expanding, leakage-safe) and predict Y, scoring the held-out
    TOP-TIER ρ (tier anchored on `mvp1_fp` — fixed across candidates) + the full-universe ρ for
    reference. Returns per-season dicts + means."""
    d = pool[pool["position"] == pos]
    per_top, per_full = {}, {}
    for y in target_seasons:
        tr = d[d["target_season"] < y]
        te = d[d["target_season"] == y]
        if len(tr) < 30 or len(te) < 15:
            continue
        learner = M11.make_pos_learner(name, feats=feats, **hp)
        learner.fit(tr, tr["real_fp_ppr"].to_numpy())
        scored = te.assign(_pred=learner.predict(te))
        # degenerate_zero: a constant prediction over a scoreable tier scores 0.0 (zero ordering
        # skill), keeping every config's season coverage identical to the null's
        top, _ = M11.top_tier_rho(scored, "_pred", top_n={pos: M11.TOP_N[pos]}, degenerate_zero=True)
        if pos in top:
            per_top[y] = top[pos]
        if len(scored) >= 10:
            v = M11.safe_spearman(scored["_pred"], scored["real_fp_ppr"])
            if v is not None:
                per_full[y] = round(v, 4)

    def _mean(dd):
        return round(float(np.mean(list(dd.values()))), 4) if dd else None

    return {"learner": name, "hp": hp, "per_season_top": per_top, "per_season_full": per_full,
            "mean_top": _mean(per_top), "mean_full": _mean(per_full)}


def _season_row(rec: dict, target_seasons: list[int]) -> np.ndarray:
    return np.array([rec["per_season_top"].get(y, np.nan) for y in target_seasons], dtype=float)


def _sharpe(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if len(x) < 3 or x.std(ddof=1) < 1e-12:
        return float("nan")
    return float(x.mean() / x.std(ddof=1))


def _finite_top(rec: dict) -> float:
    """Sort/selection key: a record with a None/NaN mean sinks below every real score."""
    v = rec.get("mean_top")
    return v if v is not None and np.isfinite(v) else float("-inf")


def _optuna_tune_pos(pool: pd.DataFrame, pos: str, name: str, feats: tuple[str, ...],
                     target_seasons: list[int], n_trials: int) -> list[dict]:
    """Optuna-tune ONE learner class for ONE position on the walk-forward held-out top-tier ρ.
    Returns EVERY trial's full record (all of them count toward the deflation), best-first."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    records: list[dict] = []

    def space(trial):
        if name == "pos_ridge":
            return {"alpha": trial.suggest_float("alpha", 0.5, 300.0, log=True)}
        if name == "pos_gbm":
            return {"n_estimators": trial.suggest_int("n_estimators", 100, 500, step=50),
                    "num_leaves": trial.suggest_int("num_leaves", 4, 20),
                    "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
                    "min_child_samples": trial.suggest_int("min_child_samples", 5, 40),
                    "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 20.0, log=True)}
        if name == "pos_similarity":
            return {"k": trial.suggest_int("k", 5, 75),
                    "weight_power": trial.suggest_float("weight_power", 0.0, 3.0),
                    "mvp1_emphasis": trial.suggest_float("mvp1_emphasis", 0.5, 4.0, log=True)}
        return {}

    def objective(trial):
        rec = walk_forward_pos(pool, pos, name, space(trial), feats, target_seasons)
        records.append(rec)
        v = rec["mean_top"]
        return v if v is not None and np.isfinite(v) else -1.0

    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=17))
    study.optimize(objective, n_trials=max(n_trials, 1), show_progress_bar=False)
    records.sort(key=_finite_top, reverse=True)
    return records


def feature_ablation_pos(pool: pd.DataFrame, pos: str, winner: dict,
                         target_seasons: list[int]) -> list[dict]:
    """Drop-one-GROUP ablation on the position winner (pre-registered groups ∩ the position's set).
    Negative Δ = removing the group HURT the top-tier ordering = the group carries signal. Returns
    the arms (they are appended to the deflation trial population by the caller — §0.5: deflation
    makes a wide ablation safe)."""
    full_feats = M11.POSITION_FEATURES[pos]
    rows = []
    for grp, cols in M11.FEATURE_GROUPS.items():
        drop = tuple(f for f in full_feats if f in cols)
        if not drop:
            continue
        feats = tuple(f for f in full_feats if f not in cols)
        rec = walk_forward_pos(pool, pos, winner["learner"], winner["hp"], feats, target_seasons)
        rec["drop"] = grp
        rec["delta"] = (round(rec["mean_top"] - winner["mean_top"], 4)
                        if rec["mean_top"] is not None and winner["mean_top"] is not None else None)
        rows.append(rec)
    return rows


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The per-position bake-off + deflation
# ══════════════════════════════════════════════════════════════════════════════════════════════
def run_bakeoff(con, base_from: int, base_to: int, schema: str, n_trials: int) -> dict:
    """The full NF1.1 selection: per position, tune every candidate class on the top-tier metric vs
    the MVP-1 null, deflate the whole search (PBO/spread/DSR per position, BH-FDR across positions),
    ablate each winner's features, and emit the repoint verdicts."""
    base_seasons = list(range(base_from, base_to + 1))
    pool = build_pool(con, base_seasons, schema)
    if pool.empty:
        raise SystemExit("empty training pool — build the NFL marts first")
    targets = sorted(pool["target_season"].unique().tolist())
    scored_targets = [y for y in targets if any(t < y for t in targets)]
    log.info("pool: %d rows, scored targets %s", len(pool), scored_targets)

    # E2.1-r oracle-ceiling check on the SELECTION metric, per scored target (mvp1 as the probe)
    oracle_ok = all(
        M11.oracle_top_tier_is_ceiling(pool[pool["target_season"] == y].assign(_c=lambda d: d["mvp1_fp"]),
                                       ["_c"]) for y in scored_targets)

    positions_out: dict[str, dict] = {}
    pvals: dict[str, float | None] = {}
    for pos in M11.POSITIONS:
        feats = M11.POSITION_FEATURES[pos]
        null_rec = walk_forward_pos(pool, pos, "pos_null", {}, feats, scored_targets)
        trial_records: list[dict] = []
        best_by_class: dict[str, dict] = {}
        for name in _LEARNED_CANDIDATES:
            recs = _optuna_tune_pos(pool, pos, name, feats, scored_targets, n_trials)
            trial_records.extend(recs)
            if recs and np.isfinite(_finite_top(recs[0])):
                best_by_class[name] = recs[0]
            log.info("  %s %-14s best top-tier ρ=%s (%d trials)", pos, name,
                     recs[0]["mean_top"] if recs else None, len(recs))
        if not best_by_class:
            positions_out[pos] = {"null": null_rec, "note": "no scoreable candidate"}
            pvals[pos] = None
            continue
        winner = max(best_by_class.values(), key=_finite_top)

        # winner feature ablation — the arms join the deflation population
        ablation = feature_ablation_pos(pool, pos, winner, scored_targets)
        trial_records.extend(ablation)

        # deflation over EVERY evaluated config for this position
        matrix = np.vstack([_season_row(r, scored_targets) for r in trial_records])
        null_row = _season_row(null_rec, scored_targets)
        winner_row = _season_row(winner, scored_targets)
        deltas = winner_row - null_row
        trial_srs = np.array([_sharpe(_season_row(r, scored_targets) - null_row)
                              for r in trial_records])
        pbo = M11.cscv_pbo(matrix)
        spread = M11.config_spread(matrix)
        dsr = M11.deflated_sharpe(deltas, trial_srs)
        pvals[pos] = M11.onesided_paired_pvalue(deltas)
        beats_null = (winner["mean_top"] is not None and null_rec["mean_top"] is not None
                      and winner["mean_top"] > null_rec["mean_top"])
        positions_out[pos] = {
            "null": null_rec,
            "best_by_class": best_by_class,
            "winner": winner,
            "n_configs": int(len(trial_records)),
            "pbo": pbo, "config_spread": spread, "dsr": dsr, "pvalue": pvals[pos],
            "beats_null": bool(beats_null),
            "feature_ablation": [{k: r[k] for k in ("drop", "mean_top", "delta")} for r in ablation],
        }

    fdr = M11.bh_fdr(pvals)
    for pos, r in positions_out.items():
        if "winner" not in r:
            r["verdict"] = {"repoint": False, "note": "unscoreable"}
            continue
        r["fdr_pass"] = bool(fdr.get(pos, False))
        r["verdict"] = M11.position_verdict(r["beats_null"], r["pbo"], r["dsr"], r["fdr_pass"])

    return {
        "model_version": M11.MODEL_VERSION,
        "base_seasons": base_seasons, "target_seasons": scored_targets, "n_pool": int(len(pool)),
        "selection_metric": f"top-tier within-position ρ (tier = top-N by the MVP-1 incumbent, N={M11.TOP_N})",
        "oracle_metric_ok": bool(oracle_ok),
        "n_trials_per_class": n_trials,
        "positions": positions_out,
        "fdr_q": M11.FDR_Q, "pbo_max": M11.PBO_MAX, "dsr_min": M11.DSR_MIN,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The final board (ordering-only) + interval calibration + grade
# ══════════════════════════════════════════════════════════════════════════════════════════════
def load_selection(bakeoff: dict, board: str = "beats-null") -> dict[str, dict]:
    """Per-position learner selection from a bake-off result. `board`: 'gated' = only deflation
    survivors repoint (the serving rule); 'beats-null' = every winner that beat the MVP-1 null (the
    research grade — the product metric then delivers the verdict); anything else → MVP-1 only."""
    sel = {}
    for pos, r in bakeoff.get("positions", {}).items():
        if "winner" not in r:
            continue
        use = r["verdict"]["repoint"] if board == "gated" else bool(r.get("beats_null"))
        if use:
            sel[pos] = {"learner": r["winner"]["learner"], "hp": r["winner"]["hp"]}
    return sel


def build_season_projection(con, base_season: int, projection_season: int, schema: str,
                            selections: dict[str, dict], base_from: int = 2017,
                            disp_kappa: float = 1.0) -> pd.DataFrame:
    """The NF1.1 season projection: fit each selected position's learner on ALL completed history
    (base_from ≤ base < base_season, target < projection_season), predict the veteran board, apply
    the learned scores as a WITHIN-POSITION ORDERING over MVP-1's calibrated point multiset (the NF1
    survivorship lesson — never the learned level), attach the calibrated 80% interval, concat the
    unchanged rookie slot-curve board. Positions without a selection keep MVP-1's order exactly."""
    base_seasons = [b for b in range(base_from, base_season) if b + 1 < projection_season]
    pool = build_pool(con, base_seasons, schema) if selections else pd.DataFrame()

    feats = assemble_features(con, base_season, projection_season, schema)
    feats = attach_xfp(con, feats, schema)
    position_scores: dict[str, np.ndarray] = {}
    for pos, sel in selections.items():
        pfeats = M11.POSITION_FEATURES[pos]
        tr = pool[pool["position"] == pos] if not pool.empty else pd.DataFrame()
        learner = M11.make_pos_learner(sel["learner"], feats=pfeats, **sel["hp"])
        if len(tr) >= 30:
            learner.fit(tr, tr["real_fp_ppr"].to_numpy())
        te = feats[feats["position"] == pos]
        if not te.empty:
            position_scores[pos] = learner.predict(te)

    score = M11.combined_ordering_score(feats, position_scores)
    vets = M1.apply_learned_ordering(feats, score)
    vets = SP.score_line(vets, prefix="proj_")

    fp = vets["proj_fp_ppr"].to_numpy()
    season_sd = pd.to_numeric(vets.get("fp_ppr_sd"), errors="coerce").fillna(0.0).to_numpy() * disp_kappa
    z80 = 1.2815515594
    vets["fp_ppr_sd"] = np.round(season_sd, 2)
    vets["fp_ppr_p10"] = np.round(np.clip(fp - z80 * season_sd, 0.0, None), 1)
    vets["fp_ppr_p90"] = np.round(fp + z80 * season_sd, 1)
    vets["uncertainty_type"] = "calibrated"
    vets["is_rookie"] = False
    vets["source"] = "veteran"
    vets["draft_overall"] = np.nan
    g = pd.to_numeric(vets["base_games"], errors="coerce").fillna(0).to_numpy()
    vets["confidence"] = np.where(g >= 10, "high", np.where(g >= 5, "medium", "low"))
    vets["nf1_1_learner"] = [
        (selections[p]["learner"] if p in selections else "mvp1_null") for p in vets["position"]]

    rookies_all = pd.read_parquet(_ROOKIE_PARQUET)
    incoming = rookies_all[pd.to_numeric(rookies_all["draft_year"], errors="coerce") == projection_season]
    curve = fit_rookie_slot_curves(load_rookie_training(con, base_season, schema))
    rks = project_rookies(incoming, curve, projection_season) if not incoming.empty else pd.DataFrame()
    if not rks.empty:
        rks["nf1_scale"] = 1.0
        rks["nf1_1_learner"] = "rookie_slot_curve"

    proj = pd.concat([vets, rks], ignore_index=True, sort=False)
    proj["sport"] = "nfl"
    proj["base_season"] = int(base_season)
    proj["projection_season"] = int(projection_season)
    proj["model_version"] = M11.MODEL_VERSION
    proj["generated_at"] = datetime.now(timezone.utc).isoformat()
    proj = proj[proj["position"].isin(("QB", "RB", "WR", "TE", "FB"))].copy()
    cols = OUTPUT_COLS + [c for c in NF1_1_EXTRA_COLS if c not in OUTPUT_COLS]
    for c in cols:
        if c not in proj.columns:
            proj[c] = np.nan
    proj = proj[cols].sort_values("proj_fp_ppr", ascending=False).reset_index(drop=True)
    proj = proj.drop_duplicates(subset=["player_id"], keep="first").reset_index(drop=True)
    return proj


def calibrate_season_interval(con, base_from: int, base_to: int, schema: str,
                              selections: dict[str, dict]) -> dict:
    """Tune the season dispersion κ on the walk-forward holdout (the E2.1-r FLOOR search — smallest
    κ whose calib_80 ≥ 0.80) + report PIT flatness. Mirrors the NF1 calibration exactly, over the
    NF1.1 board."""
    resid, sd, cdf_all = [], [], []
    for y in range(base_from + 1, base_to + 2):
        if y - 1 < base_from:
            continue
        proj = build_season_projection(con, y - 1, y, schema, selections, base_from=base_from,
                                       disp_kappa=1.0)
        real = load_realized_season(con, y, schema)
        m = proj[~proj["is_rookie"]].merge(real, on="player_id", how="inner")
        m = m[m["g"] >= 6]
        if len(m) < 30:
            continue
        r = (m["real_fp_ppr"] - m["proj_fp_ppr"]).to_numpy()
        s = np.clip(pd.to_numeric(m["fp_ppr_sd"], errors="coerce").fillna(0.0).to_numpy(), 1e-6, None)
        resid.append(r)
        sd.append(s)
        from scipy.stats import norm
        cdf_all.append(norm.cdf(r / s))
    if not resid:
        return {"kappa": 1.0, "note": "insufficient holdout"}
    resid, sd = np.concatenate(resid), np.concatenate(sd)
    kappa = M1.calibrate_dispersion(resid, sd, target_cov=0.80)
    z80 = 1.2815515594
    cov80 = M1.calib_coverage(resid, -z80 * kappa * sd, z80 * kappa * sd)
    cdf = np.concatenate(cdf_all)
    pit = M1.randomized_pit(resid, cdf, cdf)
    return {"kappa": float(kappa), "calib_80": round(float(cov80), 3),
            "pit_max_decile_dev": round(float(M1.pit_max_decile_deviation(pit)), 4),
            "n": int(len(resid))}


def grade_vs_consensus(con, seasons: list[int], schema: str, selections: dict[str, dict],
                       base_from: int = 2017) -> dict:
    """The PRODUCT metric: the NF-D3 consensus scorecard over the NF1.1 board, apples-to-apples with
    the stored MVP-1 (`nf_d3_benchmark_scorecard.json`) and NF1 (`nf1_vs_consensus_scorecard.json`)
    runs — same seasons, same universes, same scorer."""
    from quant_sports_intel_models.football.nfl.fantasy import benchmark_scorecard as BS

    def project_fn(c, y, sch):
        return build_season_projection(c, y - 1, y, sch, selections, base_from=base_from)[
            ["player_id", "position", "proj_fp_ppr"]]

    return BS.build_scorecard(con, seasons, schema, project_fn=project_fn,
                              load_realized_fn=load_realized_season)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _fmt(v, sign=False):
    if v is None:
        return "—"
    return f"{v:+.4f}" if sign else f"{v:.4f}"


def write_bakeoff_report(out: dict, path: Path) -> None:
    a = []
    p = a.append
    p("# NF1.1 — per-position independent models, TOP-TIER-weighted selection (market-blind)")
    p("")
    p(f"**Model:** `{out['model_version']}` · **generated:** {out['generated_at']} · **base seasons:** "
      f"{out['base_seasons'][0]}–{out['base_seasons'][-1]} · **scored targets:** {out['target_seasons']} "
      f"· **pool:** {out['n_pool']} · **Optuna trials/class:** {out['n_trials_per_class']}")
    p("")
    p(f"> **Selection metric:** {out['selection_metric']} — fixed across candidates (a candidate "
      "cannot game its own tier), oracle-ceiling-checked (E2.1-r). Candidates per position: "
      "pos_ridge / pos_gbm / pos_similarity (the comparables learner) vs the MVP-1 per-position "
      "null. MARKET-BLIND (no ADP/ECR). xFP features (NF-D7) join as candidates — the heuristic "
      "blend null is NOT re-litigated. Deflation gates for a repoint: "
      f"PBO<{out['pbo_max']} · DSR≥{out['dsr_min']} · BH-FDR q={out['fdr_q']}. `best_alpha = 0`.")
    p("")
    p(f"- **oracle metric sane:** {out['oracle_metric_ok']}")
    p("")
    for pos, r in out["positions"].items():
        p(f"## {pos}")
        p("")
        if "winner" not in r:
            p(f"- unscoreable ({r.get('note')})")
            p("")
            continue
        rows = [{"candidate": "pos_null (MVP-1)", "top-tier ρ": _fmt(r["null"]["mean_top"]),
                 "full ρ": _fmt(r["null"]["mean_full"]), "hp": ""}]
        for name, rec in r["best_by_class"].items():
            tag = " ⭐" if rec is r["winner"] else ""
            rows.append({"candidate": name + tag, "top-tier ρ": _fmt(rec["mean_top"]),
                         "full ρ": _fmt(rec["mean_full"]), "hp": json.dumps(rec["hp"])})
        p(pd.DataFrame(rows).to_markdown(index=False))
        p("")
        v = r["verdict"]
        p(f"- **winner:** `{r['winner']['learner']}` · beats null: **{r['beats_null']}** "
          f"(Δ top-tier ρ {_fmt((r['winner']['mean_top'] or 0) - (r['null']['mean_top'] or 0), sign=True)})")
        p(f"- **deflation** ({r['n_configs']} configs): PBO {_fmt(r['pbo'])} (spread "
          f"{_fmt(r['config_spread'])}) · DSR {_fmt(r['dsr'])} · p {_fmt(r['pvalue'])} · "
          f"FDR pass {r.get('fdr_pass')}")
        p(f"- **verdict:** {'REPOINT' if v['repoint'] else 'NULL — MVP-1 stands'} "
          f"({', '.join(k for k, ok in v.items() if k != 'repoint' and not ok) or 'all gates pass'})")
        p("")
        p("**Feature ablation on the winner (drop-one group; negative Δ = the group carries signal):**")
        p("")
        ab = pd.DataFrame(r["feature_ablation"])
        if not ab.empty:
            ab["mean_top"] = ab["mean_top"].map(_fmt)
            ab["delta"] = ab["delta"].map(lambda x: _fmt(x, sign=True))
            p(ab.to_markdown(index=False))
        p("")
    repoints = [pos for pos, r in out["positions"].items() if r.get("verdict", {}).get("repoint")]
    beats = [pos for pos, r in out["positions"].items() if r.get("beats_null")]
    p("## Verdict")
    p("")
    p(f"- positions beating the MVP-1 null on the top-tier metric: **{beats or 'none'}**")
    p(f"- positions passing the FULL deflation gate (repoint-eligible): **{repoints or 'none'}**")
    p("- next: `grade` mode delivers the PRODUCT-metric verdict (NF-D3 draftable-tier vs consensus, "
      "apples-to-apples with the stored MVP-1/NF1 scorecards); a null here KEEPS MVP-1 and is the "
      "market-blind-ceiling evidence for the operator's market-aware decision.")
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NF1.1 — per-position models + top-tier selection")
    ap.add_argument("--mode", required=True, choices=["bakeoff", "build", "grade"])
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--base-from", type=int, default=2017)
    ap.add_argument("--base-to", type=int, default=2024)
    ap.add_argument("--projection-season", type=int, default=None)
    ap.add_argument("--n-trials", type=int, default=40, help="bakeoff: Optuna trials per learner class")
    ap.add_argument("--selection", default=None,
                    help="build/grade: path to the bake-off json (default ablation_results/nf1_1_per_position.json)")
    ap.add_argument("--board", choices=["gated", "beats-null"], default="beats-null",
                    help="build/grade: 'gated' = deflation survivors only (serving rule); "
                         "'beats-null' = every null-beating winner (the research/product grade)")
    ap.add_argument("--seasons", default=None, help="grade: comma seasons (default 2019-2024)")
    ap.add_argument("--smoke", action="store_true", help="tiny subset; writes *_smoke reports")
    ap.add_argument("--s3", action="store_true", help="build: land the projection to S3")
    ap.add_argument("--lake-root", default=None, help="build: land to a LOCAL Delta tree instead of S3")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    suffix = "_smoke" if args.smoke else ""
    sel_path = Path(args.selection) if args.selection else (_REPORT_DIR / f"nf1_1_per_position{suffix}.json")
    con = _connect(args.duckdb)
    try:
        if args.mode == "bakeoff":
            bf, bt = (2019, 2022) if args.smoke else (args.base_from, args.base_to)
            n_trials = 2 if args.smoke else args.n_trials
            out = run_bakeoff(con, bf, bt, args.schema, n_trials)
            (_REPORT_DIR / f"nf1_1_per_position{suffix}.json").write_text(
                json.dumps(out, indent=2, default=float))
            write_bakeoff_report(out, _REPORT_DIR / f"nf1_1_per_position{suffix}.md")
            for pos, r in out["positions"].items():
                if "winner" in r:
                    print(f"{pos}: winner={r['winner']['learner']} top ρ={r['winner']['mean_top']} "
                          f"(null {r['null']['mean_top']}) beats_null={r['beats_null']} "
                          f"PBO={r['pbo']} DSR={r['dsr']} repoint={r['verdict']['repoint']}")

        elif args.mode == "grade":
            bakeoff = json.loads(sel_path.read_text())
            selections = load_selection(bakeoff, board=args.board)
            log.info("grading board=%s selections=%s", args.board,
                     {p: s["learner"] for p, s in selections.items()})
            seasons = ([2023] if args.smoke
                       else [int(s) for s in (args.seasons or "2019,2020,2021,2022,2023,2024").split(",")])
            sc = grade_vs_consensus(con, seasons, args.schema, selections, base_from=args.base_from)
            sc["board"] = args.board
            sc["selections"] = selections
            (_REPORT_DIR / f"nf1_1_vs_consensus_scorecard{suffix}.json").write_text(
                json.dumps(sc, indent=2, default=float))
            print(json.dumps(sc.get("aggregate", {}), indent=2, default=float))
            # apples-to-apples context: the stored MVP-1 + NF1 aggregates on the same scorer
            for ref, fname in (("MVP-1", "nf_d3_benchmark_scorecard.json"),
                               ("NF1", "nf1_vs_consensus_scorecard.json")):
                f = _REPORT_DIR / fname
                if f.exists():
                    agg = json.loads(f.read_text()).get("aggregate", {})
                    brief = {s: {"delta_rho_pooled": v.get("delta_rho_pooled"),
                                 "delta_rho_by_pos": v.get("delta_rho_by_pos")}
                             for s, v in agg.items()}
                    print(f"\n{ref} (stored, same scorer): {json.dumps(brief, default=float)}")

        elif args.mode == "build":
            bakeoff = json.loads(sel_path.read_text())
            selections = load_selection(bakeoff, board=args.board)
            log.info("building board=%s selections=%s", args.board,
                     {p: s["learner"] for p, s in selections.items()})
            base_season = int(con.sql(
                f"select max(season) from {args.schema}.fct_player_week where played_flag").fetchone()[0])
            proj_season = args.projection_season or (base_season + 1)
            cal = calibrate_season_interval(con, args.base_from, min(args.base_to, base_season),
                                            args.schema, selections)
            kappa = cal.get("kappa", 1.0)
            log.info("season interval calibration: %s", cal)
            proj = build_season_projection(con, base_season, proj_season, args.schema, selections,
                                           base_from=args.base_from, disp_kappa=kappa)
            log.info("NF1.1 %d: %d players (%d vets, %d rookies)", proj_season, len(proj),
                     int((~proj["is_rookie"]).sum()), int(proj["is_rookie"].sum()))
            _ART.mkdir(parents=True, exist_ok=True)
            proj.to_parquet(_ART / f"nf1_1_season_projections_{proj_season}.parquet", index=False)
            ranked = proj.copy()
            ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
            ranked.insert(1, "pos_rank", ranked.groupby("position").cumcount() + 1)
            ranked.to_csv(_ART / f"nf1_1_season_projections_{proj_season}_ranked.csv", index=False)
            if args.s3 or args.lake_root:
                from quant_sports_intel_models.football.nfl.ingest import s3io
                n = s3io.write_dataframe(proj.assign(season=int(proj_season)), sport="nfl",
                                         source="nf1_1_season_projections", season=int(proj_season),
                                         tier="fantasy/derived", local_root=args.lake_root)
                log.info("landed %d rows → nfl/fantasy/derived/nf1_1_season_projections season=%d",
                         n, proj_season)
            (_ART / f"nf1_1_projection_summary_{proj_season}.json").write_text(json.dumps({
                "model_version": M11.MODEL_VERSION, "board": args.board, "selections": selections,
                "projection_season": proj_season, "interval_calibration": cal,
                "n_players": int(len(proj)), "generated_at": datetime.now(timezone.utc).isoformat(),
            }, indent=2, default=float))
            print(f"NF1.1 {proj_season} built (board={args.board}); interval κ={kappa}; top: "
                  + ", ".join(proj.head(5)["player_name"].tolist()))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
