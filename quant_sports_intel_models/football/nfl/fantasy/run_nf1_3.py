"""run_nf1_3.py — NF1.3 CLI/IO: the MARKET-AWARE, position-conditional §0.5 bake-off + grade + build.

NF1.3 = NF1.1's per-position harness with ADP/ECR consensus folded in POSITION-CONDITIONALLY (read
`nf1_3_model.py`'s docstring for the design + the honest frame). This module does the DuckDB reads
(SF-free sports lake), the leakage-safe ADP/ECR join per PROJECTION season, the walk-forward
orchestration (the market-blind classes now carrying the market axes + the market-native blend /
market-only classes, EVERY trial counted toward the deflation), the NF-D3 PRODUCT grade, and the S3
landing to NF1.3's OWN prefix.

🔒 HONEST FRAME (enforced in the report + the served provenance): the market-blind NF1/MVP-1 stays
the baseline; at positions that LEAN on the market (high blend w) we say "we incorporate consensus"
(Δρ→0 vs ADP/ECR is the DESIGN there, not an edge) and NEVER claim to beat the market we use; the
WR/TE independent view + fade edge is what must be PRESERVED. `best_alpha = 0`.

⭐ RUN ON THE LAPTOP (like run_nf1 / run_nf1_1): SF-free, sports-lake DuckDB, S3 I/O only, zero
shared-box CPU. `SPORTS_LAKE_REGION=us-east-2` for the S3 read/write.

MODES:
  * `bakeoff` — the per-position §0.5 selection: for each of QB/RB/WR/TE, Optuna-tune pos_market_blend
                / pos_ridge / pos_gbm / pos_similarity on the walk-forward held-out TOP-TIER ρ (tier
                anchored on the MVP-1 incumbent — fixed across candidates), against the MVP-1 null AND
                the pure-consensus `pos_market_only` reference; deflate the FULL search (CSCV-PBO /
                DSR / BH-FDR across positions); drop-one-group ablation (incl. the `market` group).
                → ablation_results/nf1_3_per_position.{md,json}
  * `grade`   — the PRODUCT-metric verdict: build the NF1.3 board per season and run the NF-D3
                consensus scorecard apples-to-apples with the stored MVP-1 + NF1.1 runs — the QB/RB
                accuracy lift + the preserved WR/TE fade edge are read here.
                → ablation_results/nf1_3_vs_consensus_scorecard.json
  * `build`   — the final projection: per-position winners fit on all history, applied as ORDERING
                only (`apply_learned_ordering` — MVP-1's calibrated point multiset per position),
                calibrated 80% interval, per-position market-lean provenance, landed to its OWN S3
                prefix `nfl/fantasy/derived/nf1_3_season_projections` (never overwrites MVP-1/NF1/NF1.1).

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

from quant_sports_intel_models.football.nfl.fantasy import adp_source as ADP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import fantasypros_source as ECR  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import market_freshness as MF  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_3_model as M13  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_model as M1  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.run_nf1 import (  # noqa: E402
    assemble_features,
    build_training_pool,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf1_1 import (  # noqa: E402
    _finite_top,
    _season_row,
    _sharpe,
    attach_xfp,
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

log = logging.getLogger("nfl.fantasy.nf1_3")

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"

NF1_3_EXTRA_COLS = ["nf1_scale", "nf1_3_learner", "nf1_3_blend_w", "market_lean"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Feature assembly — NF1.1 pool (+ xFP) + the leakage-safe ADP/ECR market join (per PROJECTION season)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _load_market_for_season(con, season: int, schema: str,
                            market_refresh: bool = False) -> pd.DataFrame:
    """ADP (FFC) ⋈ ECR (FantasyPros) for ONE projection season, keyed to our gsis `player_id`. Both
    are preseason snapshots for `season` (leakage-safe forward signals). Returns one row per matched
    player with `player_id, adp, adp_stdev, ecr_rank, ecr_std` (either side may be NaN — a player the
    market does not rank is simply absent / half-covered). Empty frame when neither source has data.

    ⭐ NF-FRESH2 P1 — `market_refresh` is REDUCED THROUGH `should_refresh_market`, which refuses any
    season that is not the clock-derived `current_season()`. So a caller threading the flag through
    a whole 2017→2026 training pool refreshes the CURRENT season only; every historical season
    still reads its pinned snapshot. That is the E5.9 backfill boundary (regrading a past benchmark
    against an ADP that did not exist at the time would be a hindsight benchmark), and it lives in
    the helper precisely so no future call site can forget it."""
    cols = ["player_id", "adp", "adp_stdev", "ecr_rank", "ecr_std"]
    refresh = MF.should_refresh_market(season, market_refresh)
    if market_refresh and not refresh:
        log.info("market refresh REFUSED for %s — not the current season; reading the pinned "
                 "snapshot (the E5.9 backfill boundary)", season)
    try:
        adp = ADP.load_adp_for_season(con, int(season), schema=schema, refresh=refresh)
    except Exception as e:  # noqa: BLE001 — a source outage degrades to the other / to market-blind
        log.warning("ADP load failed for %s: %s", season, e)
        adp = pd.DataFrame()
    try:
        ecr = ECR.load_ecr_for_season(con, int(season), schema=schema, refresh=refresh)
    except Exception as e:  # noqa: BLE001
        log.warning("ECR load failed for %s: %s", season, e)
        ecr = pd.DataFrame()

    def _slim(df, keep):
        if df is None or df.empty or "player_id" not in df.columns:
            return pd.DataFrame(columns=["player_id", *keep.values()])
        d = df[df["player_id"].notna()][["player_id", *keep.keys()]].rename(columns=keep).copy()
        d["player_id"] = d["player_id"].astype(str)
        return d.drop_duplicates(subset=["player_id"], keep="first")

    a = _slim(adp, {"adp": "adp", "adp_stdev": "adp_stdev"})
    e = _slim(ecr, {"rank_ecr": "ecr_rank", "rank_std": "ecr_std"})
    if a.empty and e.empty:
        return pd.DataFrame(columns=cols)
    merged = a.merge(e, on="player_id", how="outer") if not a.empty and not e.empty else (a if e.empty else e)
    for c in cols:
        if c not in merged.columns:
            merged[c] = np.nan
    return merged[cols]


def attach_market(con, frame: pd.DataFrame, schema: str = MARTS_SCHEMA,
                  market_refresh: bool = False) -> pd.DataFrame:
    """LEFT-JOIN the leakage-safe ADP/ECR consensus onto a feature frame per PROJECTION season (each
    row's market snapshot is the season it PROJECTS — `projection_season`, falling back to
    `base_season + 1`), then derive the model-facing market columns (`market_rank` / `market_dispersion`
    / `market_score`) via the pure `build_market_features`. A season with no market data leaves the raw
    columns NaN → `market_rank` NaN → the learners median-impute / fall back to the incumbent."""
    if frame.empty:
        return M13.build_market_features(frame)
    season_col = "projection_season" if "projection_season" in frame.columns else "base_season"
    out = frame.copy()
    out["player_id"] = out["player_id"].astype(str)
    frames = []
    for key, grp in out.groupby(season_col, sort=True):
        proj_season = int(key) if season_col == "projection_season" else int(key) + 1
        mkt = _load_market_for_season(con, proj_season, schema, market_refresh=market_refresh)
        if mkt.empty:
            g = grp.copy()
            for c in ("adp", "adp_stdev", "ecr_rank", "ecr_std"):
                g[c] = np.nan
            frames.append(g)
        else:
            frames.append(grp.merge(mkt, on="player_id", how="left"))
    joined = pd.concat(frames, ignore_index=True, sort=False)
    return M13.build_market_features(joined)


def build_pool(con, base_seasons: list[int], schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    """The NF1 walk-forward training pool (cached per base season) + the xFP join + the ADP/ECR join."""
    pool = build_training_pool(con, base_seasons, schema)
    pool = attach_xfp(con, pool, schema)
    return attach_market(con, pool, schema)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Per-position walk-forward scoring (the selection loop's inner unit) — market-aware learners
# ══════════════════════════════════════════════════════════════════════════════════════════════
def walk_forward_pos(pool: pd.DataFrame, pos: str, name: str, hp: dict,
                     feats: tuple[str, ...], target_seasons: list[int]) -> dict:
    """Backtest ONE (position, learner, hp) config: for each target season Y, fit on that position's
    pool rows with `target_season < Y` (expanding, leakage-safe) and predict Y, scoring the held-out
    TOP-TIER ρ (tier anchored on `mvp1_fp` — fixed across candidates) + full-universe ρ for reference.
    Identical to NF1.1's inner unit; the ONLY change is the M13 registry (market-aware learners)."""
    d = pool[pool["position"] == pos]
    per_top, per_full = {}, {}
    for y in target_seasons:
        tr = d[d["target_season"] < y]
        te = d[d["target_season"] == y]
        if len(tr) < 30 or len(te) < 15:
            continue
        learner = M13.make_pos_learner(name, feats=feats, **hp)
        learner.fit(tr, tr["real_fp_ppr"].to_numpy())
        scored = te.assign(_pred=learner.predict(te))
        top, _ = M13.top_tier_rho(scored, "_pred", top_n={pos: M13.TOP_N[pos]}, degenerate_zero=True)
        if pos in top:
            per_top[y] = top[pos]
        if len(scored) >= 10:
            v = M13.safe_spearman(scored["_pred"], scored["real_fp_ppr"])
            if v is not None:
                per_full[y] = round(v, 4)

    def _mean(dd):
        return round(float(np.mean(list(dd.values()))), 4) if dd else None

    return {"learner": name, "hp": hp, "per_season_top": per_top, "per_season_full": per_full,
            "mean_top": _mean(per_top), "mean_full": _mean(per_full)}


def _optuna_tune_pos(pool: pd.DataFrame, pos: str, name: str, feats: tuple[str, ...],
                     target_seasons: list[int], n_trials: int) -> list[dict]:
    """Optuna-tune ONE learner class for ONE position on the walk-forward held-out top-tier ρ (search
    space from `M13.suggest_hp`). Returns EVERY trial's record (all count toward deflation), best-first."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    records: list[dict] = []

    def objective(trial):
        rec = walk_forward_pos(pool, pos, name, M13.suggest_hp(trial, name), feats, target_seasons)
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
    """Drop-one-GROUP ablation on the position winner (pre-registered groups ∩ the position's set,
    INCLUDING the new `market` group). Negative Δ = removing the group HURT the top-tier ordering =
    the group carries signal. The arms join the deflation trial population (§0.5).

    Skipped for `pos_market_blend` (its only inputs are mvp1_fp + market_score — the drop-one-group
    ablation over the FEATS set does not apply; `blend_w` itself is the market/no-market dial)."""
    if winner["learner"] == "pos_market_blend":
        return []
    full_feats = M13.POSITION_FEATURES[pos]
    rows = []
    for grp, cols in M13.FEATURE_GROUPS.items():
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
# The per-position bake-off + deflation (adds the pure-consensus reference + market coverage)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def run_bakeoff(con, base_from: int, base_to: int, schema: str, n_trials: int) -> dict:
    """The full NF1.3 selection: per position, tune every market-aware candidate class on the top-tier
    metric vs the MVP-1 null (and beside the pure-consensus `pos_market_only` reference), deflate the
    whole search, ablate each winner, and emit the repoint verdicts + the honest market-lean read."""
    base_seasons = list(range(base_from, base_to + 1))
    pool = build_pool(con, base_seasons, schema)
    if pool.empty:
        raise SystemExit("empty training pool — build the NFL marts first")
    targets = sorted(pool["target_season"].unique().tolist())
    scored_targets = [y for y in targets if any(t < y for t in targets)]
    coverage = M13.market_coverage(pool)
    log.info("pool: %d rows, scored targets %s, market top-tier coverage %s",
             len(pool), scored_targets, coverage)

    oracle_ok = all(
        M13.oracle_top_tier_is_ceiling(pool[pool["target_season"] == y].assign(_c=lambda d: d["mvp1_fp"]),
                                       ["_c"]) for y in scored_targets)

    positions_out: dict[str, dict] = {}
    pvals: dict[str, float | None] = {}
    for pos in M13.POSITIONS:
        feats = M13.POSITION_FEATURES[pos]
        null_rec = walk_forward_pos(pool, pos, "pos_null", {}, feats, scored_targets)
        market_only_rec = walk_forward_pos(pool, pos, "pos_market_only", {}, feats, scored_targets)
        trial_records: list[dict] = []
        best_by_class: dict[str, dict] = {}
        for name in M13.LEARNED_CANDIDATES:
            recs = _optuna_tune_pos(pool, pos, name, feats, scored_targets, n_trials)
            trial_records.extend(recs)
            if recs and np.isfinite(_finite_top(recs[0])):
                best_by_class[name] = recs[0]
            log.info("  %s %-16s best top-tier ρ=%s (%d trials)", pos, name,
                     recs[0]["mean_top"] if recs else None, len(recs))
        if not best_by_class:
            positions_out[pos] = {"null": null_rec, "market_only": market_only_rec,
                                  "note": "no scoreable candidate"}
            pvals[pos] = None
            continue
        winner = max(best_by_class.values(), key=_finite_top)

        ablation = feature_ablation_pos(pool, pos, winner, scored_targets)
        trial_records.extend(ablation)

        matrix = np.vstack([_season_row(r, scored_targets) for r in trial_records])
        null_row = _season_row(null_rec, scored_targets)
        winner_row = _season_row(winner, scored_targets)
        deltas = winner_row - null_row
        trial_srs = np.array([_sharpe(_season_row(r, scored_targets) - null_row)
                              for r in trial_records])
        pbo = M13.cscv_pbo(matrix)
        spread = M13.config_spread(matrix)
        dsr = M13.deflated_sharpe(deltas, trial_srs)
        pvals[pos] = M13.onesided_paired_pvalue(deltas)
        beats_null = (winner["mean_top"] is not None and null_rec["mean_top"] is not None
                      and winner["mean_top"] > null_rec["mean_top"])
        beats_market_only = (winner["mean_top"] is not None and market_only_rec["mean_top"] is not None
                             and winner["mean_top"] > market_only_rec["mean_top"])
        # the interpretable market-lean read: the tuned blend weight if the blend won, else a coarse
        # label from whether the market-native candidates are among the strongest for this position
        blend_w = (winner["hp"].get("blend_w") if winner["learner"] == "pos_market_blend"
                   else best_by_class.get("pos_market_blend", {}).get("hp", {}).get("blend_w"))
        positions_out[pos] = {
            "null": null_rec,
            "market_only": market_only_rec,
            "market_top_tier_coverage": coverage.get(pos),
            "best_by_class": best_by_class,
            "winner": winner,
            "n_configs": int(len(trial_records)),
            "pbo": pbo, "config_spread": spread, "dsr": dsr, "pvalue": pvals[pos],
            "beats_null": bool(beats_null),
            "beats_market_only": bool(beats_market_only),
            "blend_w": blend_w,
            "feature_ablation": [{k: r[k] for k in ("drop", "mean_top", "delta")} for r in ablation],
        }

    fdr = M13.bh_fdr(pvals)
    for pos, r in positions_out.items():
        if "winner" not in r:
            r["verdict"] = {"repoint": False, "note": "unscoreable"}
            continue
        r["fdr_pass"] = bool(fdr.get(pos, False))
        r["verdict"] = M13.position_verdict(r["beats_null"], r["pbo"], r["dsr"], r["fdr_pass"])

    return {
        "model_version": M13.MODEL_VERSION,
        "base_seasons": base_seasons, "target_seasons": scored_targets, "n_pool": int(len(pool)),
        "selection_metric": f"top-tier within-position ρ (tier = top-N by the MVP-1 incumbent, N={M13.TOP_N})",
        "market_top_tier_coverage": coverage,
        "oracle_metric_ok": bool(oracle_ok),
        "n_trials_per_class": n_trials,
        "positions": positions_out,
        "fdr_q": M13.FDR_Q, "pbo_max": M13.PBO_MAX, "dsr_min": M13.DSR_MIN,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The final board (ordering-only) + interval calibration + grade
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _market_lean(learner: str, hp: dict) -> str:
    """The honest per-position provenance label served with the board (the 🔒 frame): how much the
    position leans on the market. Blend weight → a graded label; a market-native winner → 'market-aware';
    a market-blind winner or MVP-1 → 'independent'."""
    if learner == "pos_market_only":
        return "market-consensus"
    if learner == "pos_market_blend":
        w = float(hp.get("blend_w", 0.0))
        if w >= 0.66:
            return "market-led"
        if w >= 0.33:
            return "market-blend"
        return "independent-lean"
    if learner in ("mvp1_null",):
        return "independent"
    # a market-blind class (ridge/gbm/similarity) carrying the market feature axes: market-informed
    return "market-informed"


def load_selection(bakeoff: dict, board: str = "beats-null") -> dict[str, dict]:
    """Per-position learner selection from a bake-off result. `board`: 'gated' = only deflation
    survivors repoint (the serving rule); 'beats-null' = every winner that beat the MVP-1 null (the
    research/product grade — the NF-D3 product metric then delivers the verdict). MVP-1 elsewhere."""
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
    """The NF1.3 season projection: fit each selected position's learner on ALL completed history,
    predict the veteran board, apply the learned/blended scores as a WITHIN-POSITION ORDERING over
    MVP-1's calibrated point multiset (the NF1 survivorship lesson — never the learned level), attach
    the calibrated 80% interval + the honest per-position market-lean provenance, concat the unchanged
    rookie slot-curve board. Positions without a selection keep MVP-1's order exactly."""
    base_seasons = [b for b in range(base_from, base_season) if b + 1 < projection_season]
    pool = build_pool(con, base_seasons, schema) if selections else pd.DataFrame()

    feats = assemble_features(con, base_season, projection_season, schema)
    feats = attach_xfp(con, feats, schema)
    feats = attach_market(con, feats, schema)
    position_scores: dict[str, np.ndarray] = {}
    for pos, sel in selections.items():
        pfeats = M13.POSITION_FEATURES[pos]
        tr = pool[pool["position"] == pos] if not pool.empty else pd.DataFrame()
        learner = M13.make_pos_learner(sel["learner"], feats=pfeats, **sel["hp"])
        if len(tr) >= 30:
            learner.fit(tr, tr["real_fp_ppr"].to_numpy())
        te = feats[feats["position"] == pos]
        if not te.empty:
            position_scores[pos] = learner.predict(te)

    score = M13.combined_ordering_score(feats, position_scores)
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
    vets["nf1_3_learner"] = [
        (selections[p]["learner"] if p in selections else "mvp1_null") for p in vets["position"]]
    vets["nf1_3_blend_w"] = [
        (float(selections[p]["hp"].get("blend_w", np.nan))
         if p in selections and selections[p]["learner"] == "pos_market_blend" else np.nan)
        for p in vets["position"]]
    vets["market_lean"] = [
        (_market_lean(selections[p]["learner"], selections[p]["hp"]) if p in selections else "independent")
        for p in vets["position"]]

    rookies_all = pd.read_parquet(_ROOKIE_PARQUET)
    incoming = rookies_all[pd.to_numeric(rookies_all["draft_year"], errors="coerce") == projection_season]
    # NF1.4: the point curve fits the survivor-filtered history (unchanged); `band_hist` is
    # the FULL drafted population (zero-game rookies included) and calibrates the 80% rookie
    # interval, which the legacy `fp × cv` width missed badly (0.678 coverage, 0.444 at QB).
    curve = fit_rookie_slot_curves(
        load_rookie_training(con, base_season, schema),
        band_hist=load_rookie_training(con, base_season, schema, include_zero_game=True))
    rks = project_rookies(incoming, curve, projection_season) if not incoming.empty else pd.DataFrame()
    if not rks.empty:
        rks["nf1_scale"] = 1.0
        rks["nf1_3_learner"] = "rookie_slot_curve"
        rks["nf1_3_blend_w"] = np.nan
        rks["market_lean"] = "independent"

    proj = pd.concat([vets, rks], ignore_index=True, sort=False)
    proj["sport"] = "nfl"
    proj["base_season"] = int(base_season)
    proj["projection_season"] = int(projection_season)
    proj["model_version"] = M13.MODEL_VERSION
    proj["generated_at"] = datetime.now(timezone.utc).isoformat()
    proj = proj[proj["position"].isin(("QB", "RB", "WR", "TE", "FB"))].copy()
    cols = OUTPUT_COLS + [c for c in NF1_3_EXTRA_COLS if c not in OUTPUT_COLS]
    for c in cols:
        if c not in proj.columns:
            proj[c] = np.nan
    proj = proj[cols].sort_values("proj_fp_ppr", ascending=False).reset_index(drop=True)
    proj = proj.drop_duplicates(subset=["player_id"], keep="first").reset_index(drop=True)
    return proj


def calibrate_season_interval(con, base_from: int, base_to: int, schema: str,
                              selections: dict[str, dict]) -> dict:
    """Tune the season dispersion κ on the walk-forward holdout (the E2.1-r FLOOR search — smallest κ
    whose calib_80 ≥ 0.80) + report PIT flatness. Mirrors NF1/NF1.1 over the NF1.3 board."""
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
    """The PRODUCT metric: the NF-D3 consensus scorecard over the NF1.3 board, apples-to-apples with
    the stored MVP-1 (`nf_d3_benchmark_scorecard.json`), NF1 (`nf1_vs_consensus_scorecard.json`), and
    NF1.1 (`nf1_1_vs_consensus_scorecard.json`) runs — same seasons, universes, scorer."""
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
    p("# NF1.3 — MARKET-AWARE, position-conditional per-position models (ADP/ECR consensus)")
    p("")
    p(f"**Model:** `{out['model_version']}` · **generated:** {out['generated_at']} · **base seasons:** "
      f"{out['base_seasons'][0]}–{out['base_seasons'][-1]} · **scored targets:** {out['target_seasons']} "
      f"· **pool:** {out['n_pool']} · **Optuna trials/class:** {out['n_trials_per_class']}")
    p("")
    p("> 🔒 **HONEST FRAME:** this is a PRODUCT variant, NOT a replacement of the market-blind "
      "differentiator. At positions that LEAN on the market (high blend `w`) we INCORPORATE consensus "
      "— a Δρ→0 vs ADP/ECR there is the DESIGN, **not** an edge, and we ⛔ NEVER claim to beat the "
      "market we use. The WR/TE independent view + fade edge is what must be PRESERVED. The "
      "market-blind NF1/MVP-1 remains the baseline. `best_alpha = 0`.")
    p("")
    p(f"> **Selection metric:** {out['selection_metric']} — fixed across candidates, oracle-checked "
      "(E2.1-r). Candidates per position: **pos_market_blend** (the tuned position-conditional blend "
      "weight) / pos_ridge / pos_gbm / pos_similarity — the three market-blind classes now carry the "
      "market axes (`market_rank`, `market_dispersion`). Reference foils: pos_null (MVP-1, "
      "market-blind) + pos_market_only (pure consensus). Deflation gates for a repoint: "
      f"PBO<{out['pbo_max']} · DSR≥{out['dsr_min']} · BH-FDR q={out['fdr_q']}.")
    p("")
    p(f"- **oracle metric sane:** {out['oracle_metric_ok']}")
    p(f"- **market top-tier coverage** (fraction of each draftable tier the consensus ranks): "
      f"{out.get('market_top_tier_coverage')}")
    p("")
    for pos, r in out["positions"].items():
        p(f"## {pos}")
        p("")
        if "winner" not in r:
            p(f"- unscoreable ({r.get('note')})")
            p("")
            continue
        rows = [{"candidate": "pos_null (MVP-1, blind)", "top-tier ρ": _fmt(r["null"]["mean_top"]),
                 "full ρ": _fmt(r["null"]["mean_full"]), "hp": ""},
                {"candidate": "pos_market_only (consensus)", "top-tier ρ": _fmt(r["market_only"]["mean_top"]),
                 "full ρ": _fmt(r["market_only"]["mean_full"]), "hp": ""}]
        for name, rec in r["best_by_class"].items():
            tag = " ⭐" if rec is r["winner"] else ""
            rows.append({"candidate": name + tag, "top-tier ρ": _fmt(rec["mean_top"]),
                         "full ρ": _fmt(rec["mean_full"]), "hp": json.dumps(rec["hp"])})
        p(pd.DataFrame(rows).to_markdown(index=False))
        p("")
        v = r["verdict"]
        p(f"- **winner:** `{r['winner']['learner']}` · beats MVP-1 null: **{r['beats_null']}** "
          f"(Δ top-tier ρ {_fmt((r['winner']['mean_top'] or 0) - (r['null']['mean_top'] or 0), sign=True)}) "
          f"· beats pure-consensus: **{r['beats_market_only']}**")
        lean = _market_lean(r["winner"]["learner"], r["winner"]["hp"])
        p(f"- **market lean:** `{lean}`" + (f" (blend w={r['blend_w']:.3f})" if r.get("blend_w") is not None else "")
          + f" · top-tier coverage {r.get('market_top_tier_coverage')}")
        p(f"- **deflation** ({r['n_configs']} configs): PBO {_fmt(r['pbo'])} (spread "
          f"{_fmt(r['config_spread'])}) · DSR {_fmt(r['dsr'])} · p {_fmt(r['pvalue'])} · "
          f"FDR pass {r.get('fdr_pass')}")
        p(f"- **verdict:** {'REPOINT' if v['repoint'] else 'NULL — MVP-1 stands'} "
          f"({', '.join(k for k, ok in v.items() if k != 'repoint' and not ok) or 'all gates pass'})")
        p("")
        if r["feature_ablation"]:
            p("**Feature ablation on the winner (drop-one group; negative Δ = the group carries signal):**")
            p("")
            ab = pd.DataFrame(r["feature_ablation"])
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
    p("- next: `grade` mode delivers the PRODUCT-metric verdict (NF-D3 vs consensus, apples-to-apples "
      "with the stored MVP-1/NF1/NF1.1 scorecards). The honest read: QB/RB accuracy LIFT (where we now "
      "incorporate the market — NOT an edge claim) WITHOUT eroding the WR/TE independent fade edge.")
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
    ap = argparse.ArgumentParser(description="NF1.3 — market-aware position-conditional per-position models")
    ap.add_argument("--mode", required=True, choices=["bakeoff", "build", "grade"])
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--base-from", type=int, default=2017)
    ap.add_argument("--base-to", type=int, default=2024)
    ap.add_argument("--projection-season", type=int, default=None)
    ap.add_argument("--n-trials", type=int, default=40, help="bakeoff: Optuna trials per learner class")
    ap.add_argument("--selection", default=None,
                    help="build/grade: path to the bake-off json (default ablation_results/nf1_3_per_position.json)")
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
    sel_path = Path(args.selection) if args.selection else (_REPORT_DIR / f"nf1_3_per_position{suffix}.json")
    con = _connect(args.duckdb)
    try:
        if args.mode == "bakeoff":
            bf, bt = (2019, 2022) if args.smoke else (args.base_from, args.base_to)
            n_trials = 2 if args.smoke else args.n_trials
            out = run_bakeoff(con, bf, bt, args.schema, n_trials)
            (_REPORT_DIR / f"nf1_3_per_position{suffix}.json").write_text(
                json.dumps(out, indent=2, default=float))
            write_bakeoff_report(out, _REPORT_DIR / f"nf1_3_per_position{suffix}.md")
            for pos, r in out["positions"].items():
                if "winner" in r:
                    print(f"{pos}: winner={r['winner']['learner']} top ρ={r['winner']['mean_top']} "
                          f"(null {r['null']['mean_top']} / market_only {r['market_only']['mean_top']}) "
                          f"beats_null={r['beats_null']} lean={_market_lean(r['winner']['learner'], r['winner']['hp'])} "
                          f"PBO={r['pbo']} DSR={r['dsr']} repoint={r['verdict']['repoint']}")

        elif args.mode == "grade":
            bakeoff = json.loads(sel_path.read_text())
            selections = load_selection(bakeoff, board=args.board)
            log.info("grading board=%s selections=%s", args.board,
                     {p: (s["learner"], _market_lean(s["learner"], s["hp"])) for p, s in selections.items()})
            seasons = ([2023] if args.smoke
                       else [int(s) for s in (args.seasons or "2019,2020,2021,2022,2023,2024").split(",")])
            sc = grade_vs_consensus(con, seasons, args.schema, selections, base_from=args.base_from)
            sc["board"] = args.board
            sc["selections"] = selections
            sc["market_lean"] = {p: _market_lean(s["learner"], s["hp"]) for p, s in selections.items()}
            (_REPORT_DIR / f"nf1_3_vs_consensus_scorecard{suffix}.json").write_text(
                json.dumps(sc, indent=2, default=float))
            print(json.dumps(sc.get("aggregate", {}), indent=2, default=float))
            # apples-to-apples context: the stored MVP-1 / NF1 / NF1.1 aggregates on the same scorer
            for ref, fname in (("MVP-1", "nf_d3_benchmark_scorecard.json"),
                               ("NF1", "nf1_vs_consensus_scorecard.json"),
                               ("NF1.1", "nf1_1_vs_consensus_scorecard.json")):
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
                     {p: (s["learner"], _market_lean(s["learner"], s["hp"])) for p, s in selections.items()})
            base_season = int(con.sql(
                f"select max(season) from {args.schema}.fct_player_week where played_flag").fetchone()[0])
            proj_season = args.projection_season or (base_season + 1)
            cal = calibrate_season_interval(con, args.base_from, min(args.base_to, base_season),
                                            args.schema, selections)
            kappa = cal.get("kappa", 1.0)
            log.info("season interval calibration: %s", cal)
            proj = build_season_projection(con, base_season, proj_season, args.schema, selections,
                                           base_from=args.base_from, disp_kappa=kappa)
            log.info("NF1.3 %d: %d players (%d vets, %d rookies)", proj_season, len(proj),
                     int((~proj["is_rookie"]).sum()), int(proj["is_rookie"].sum()))
            _ART.mkdir(parents=True, exist_ok=True)
            proj.to_parquet(_ART / f"nf1_3_season_projections_{proj_season}.parquet", index=False)
            ranked = proj.copy()
            ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
            ranked.insert(1, "pos_rank", ranked.groupby("position").cumcount() + 1)
            ranked.to_csv(_ART / f"nf1_3_season_projections_{proj_season}_ranked.csv", index=False)
            if args.s3 or args.lake_root:
                from quant_sports_intel_models.football.nfl.ingest import s3io
                n = s3io.write_dataframe(proj.assign(season=int(proj_season)), sport="nfl",
                                         source="nf1_3_season_projections", season=int(proj_season),
                                         tier="fantasy/derived", local_root=args.lake_root)
                log.info("landed %d rows → nfl/fantasy/derived/nf1_3_season_projections season=%d",
                         n, proj_season)
            (_ART / f"nf1_3_projection_summary_{proj_season}.json").write_text(json.dumps({
                "model_version": M13.MODEL_VERSION, "board": args.board, "selections": selections,
                "market_lean": {p: _market_lean(s["learner"], s["hp"]) for p, s in selections.items()},
                "projection_season": proj_season, "interval_calibration": cal,
                "n_players": int(len(proj)), "generated_at": datetime.now(timezone.utc).isoformat(),
            }, indent=2, default=float))
            print(f"NF1.3 {proj_season} built (board={args.board}); interval κ={kappa}; "
                  f"lean={ {p: _market_lean(s['learner'], s['hp']) for p, s in selections.items()} }; top: "
                  + ", ".join(proj.head(5)["player_name"].tolist()))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
