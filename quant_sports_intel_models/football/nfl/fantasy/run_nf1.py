"""run_nf1.py — NF1 CLI/IO: the §0.5 bake-off, the matchup-aware weekly leg, the final projection.

NF1 = the JOINT LEARNED re-weighting of the MARKET-BLIND NF-D feature set (`nf1_model.py` is the pure
logic) + a genuine per-player-week matchup-aware projection. This module does the DuckDB reads
(SF-free), the leakage-safe walk-forward feature assembly, the bake-off orchestration (candidate
learners × Optuna × feature ablation), the calibrated posterior-predictive layer, the S3 landing, and
the validation (the NF-D3 scorecard grade + a holdout backtest).

⭐ RUN ON THE LAPTOP (like run_season_projection): SF-free, sports-lake DuckDB, S3 I/O only, ZERO
shared-box CPU. `SPORTS_LAKE_REGION=us-east-2` for the S3 read/write.

Prereq — the NFL marts built into the DuckDB (see run_season_projection.py docstring):
    export SPORTS_LAKE_REGION=us-east-2
    python -m dbt.cli.main run --select nfl.staging nfl.marts --threads 1   # from sports_dbt/

MODES:
  * `bakeoff`        — the §0.5 SEASON model selection: candidate learners (heuristic-null / ridge /
                       elasticnet / gbm), Optuna-tuned, walk-forward CV by season, scored on held-out
                       within-position ρ; + a feature ablation on the winner. → nf1_season_bakeoff.md
  * `weekly-bakeoff` — the MATCHUP weekly ablation: flat baseline vs +DVP / +env / +home / full, scored
                       on held-out weekly within-position ρ + E2.1-r calibration. → nf1_weekly_bakeoff.md
  * `build`          — the FINAL projection with the selected learner: season (raw-line + calibrated
                       interval, MVP-2/NF-C1 contract) + weekly (matchup-aware, posterior-predictive),
                       landed to S3, graded vs the NF-D3 consensus. → nf1_projection.md

Heavy runs (the full bake-off across all seasons, the weekly backtest across all weeks) are >1 min ⇒
hand them to the operator; `--smoke` runs a tiny subset for a correctness check.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import nf1_model as M  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import win_total_source  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.run_season_projection import (  # noqa: E402
    MARTS_SCHEMA,
    OUTPUT_COLS,
    fit_rookie_slot_curves,
    load_base_season,
    load_forward_roster_status,
    load_realized_season,
    load_rookie_training,
    load_team_week1_env,
    positional_pergame_priors,
    project_rookies,
    _ROOKIE_PARQUET,
)

log = logging.getLogger("nfl.fantasy.nf1")

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_FEATURE_CACHE = _ART / "nf1_feature_cache"

# The final emitted SEASON schema = the MVP-2/NF-C1 contract (identical to MVP-1) + NF1 additions.
NF1_EXTRA_COLS = ["nf1_scale", "nf1_learner"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Feature assembly (leakage-safe) — the MARKET-BLIND matrix, reusing the MVP-1 pure helpers
# ══════════════════════════════════════════════════════════════════════════════════════════════
def load_age(con, projection_season: int, schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    """player_id → age (years) at Sept 1 of the projection season, from `dim_player.birth_date`. The
    aging-curve term MVP-1 lacked (defect #5: Stefon Diggs rated too high for age). NULL where birth
    date is unknown (kept NULL — the imputer median-fills inside the learner)."""
    df = con.sql(f"select player_id, birth_date from {schema}.dim_player where birth_date is not null").df()
    if df.empty:
        return pd.DataFrame(columns=["player_id", "age"])
    ref = pd.Timestamp(year=projection_season, month=9, day=1)
    bd = pd.to_datetime(df["birth_date"], errors="coerce")
    df["age"] = (ref - bd).dt.days / 365.25
    return df[["player_id", "age"]].dropna()


def assemble_features(con, base_season: int, projection_season: int,
                      schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    """The leakage-safe MARKET-BLIND feature matrix for the VETERAN population, plus the MVP-1 raw
    stat line (so the learned level can be applied while preserving the raw-line contract).

    Reuses the SHIPPED MVP-1 pure helpers so NF1's features can never drift from the incumbent: the
    MVP-1 projection (`project_veterans`, all NF-D slices ON) supplies `mvp1_fp` + the raw line; the
    orthogonal signals (`mover_scale`, `injury_cap_ratio`, role `expected_games`, `pergame_fp`) are
    recomputed from the SAME pure functions the MVP-1 pipeline uses. Every column is a base-season
    realized quantity or a leakage-safe forward designation for `projection_season`."""
    base = load_base_season(con, base_season, schema)
    if base.empty:
        return base
    # forward env + roster status (leakage-safe), exactly as run_season_projection.build_projection
    env = win_total_source.blend_env_with_win_total(
        load_team_week1_env(con, projection_season, schema), projection_season)
    if not env.empty and "proj_team" in base.columns:
        base = base.merge(env, on="proj_team", how="left")
    status = load_forward_roster_status(con, projection_season)
    if not status.empty:
        base = base.merge(status, on="player_id", how="left")

    priors = positional_pergame_priors(base)
    rvp = SP.role_volume_prior(base)
    # the SHIPPED MVP-1 projection (all slices ON) = the incumbent line + mvp1_fp
    mvp1 = SP.project_veterans(base, priors, projection_season, role_vol_prior=rvp)
    mvp1 = mvp1[mvp1["position"].isin(SP.SKILL_POSITIONS)].copy()

    # ── the orthogonal feature signals, from the same pure helpers ──────────────────────────────
    # pergame_fp: the recency-weighted per-game line scored (pre-shrink, pre-expected-games)
    pg_line = mvp1.assign(**{
        "proj_" + s: pd.to_numeric(mvp1.get(s + "_pg"), errors="coerce").fillna(0.0)
        for s in SP._VET_PERGAME_STATS})
    mvp1["pergame_fp"] = SP.score_line(pg_line, prefix="proj_")["proj_fp_ppr"].to_numpy()
    # role expected games (pre-injury) = expected_games + usage blend
    role_eg = SP.blend_usage_into_games(
        SP.expected_games(mvp1["games_played"], mvp1["depth_chart_position_rank"], mvp1["position"]),
        mvp1["position"], mvp1.get("snap_share"), mvp1.get("target_share"))
    mvp1["expected_games"] = role_eg.to_numpy()
    # mover opportunity multiplier (slice 3)
    fp_pg_now = mvp1["pergame_fp"].to_numpy()
    mvp1["mover_scale"] = SP.mover_opportunity_scale(mvp1, rvp, fp_pg_now)
    # injury availability ratio = capped games / role games (slice 5); 1.0 when no cap
    inj_df = mvp1.assign(proj_games=role_eg.to_numpy())
    capped = SP.injury_availability_games(inj_df)
    mvp1["injury_cap_ratio"] = np.where(role_eg.to_numpy() > 1e-6,
                                        capped / np.clip(role_eg.to_numpy(), 1e-6, None), 1.0)
    # renames to the feature contract
    mvp1["mvp1_fp"] = mvp1["proj_fp_ppr"].to_numpy()
    mvp1["base_games"] = pd.to_numeric(mvp1["games_played"], errors="coerce").to_numpy()
    mvp1["depth_rank"] = pd.to_numeric(mvp1["depth_chart_position_rank"], errors="coerce").to_numpy()
    mvp1["fp_sd"] = pd.to_numeric(base.set_index("player_id").reindex(mvp1["player_id"])["fp_ppr_sd"]
                                  .to_numpy(), errors="coerce")
    if "team_env" not in mvp1.columns:
        mvp1["team_env"] = np.nan
    # age
    mvp1 = mvp1.merge(load_age(con, projection_season, schema), on="player_id", how="left")

    mvp1["base_season"] = int(base_season)
    mvp1["projection_season"] = int(projection_season)
    return mvp1


def build_training_pool(con, base_seasons: list[int], schema: str = MARTS_SCHEMA,
                        use_cache: bool = True) -> pd.DataFrame:
    """Stack `assemble_features(B → B+1)` joined to realized fp in B+1 across base seasons B — the
    walk-forward training pool. Each row = (features known at projection time for season B+1, realized
    B+1 outcome). Cached per base season under `nf1_feature_cache/` (assemble-once cost hygiene)."""
    _FEATURE_CACHE.mkdir(parents=True, exist_ok=True)
    frames = []
    for b in base_seasons:
        y = b + 1
        cache = _FEATURE_CACHE / f"pool_base{b}.parquet"
        if use_cache and cache.exists():
            frames.append(pd.read_parquet(cache))
            continue
        feats = assemble_features(con, b, y, schema)
        if feats.empty:
            continue
        real = load_realized_season(con, y, schema)
        m = feats.merge(real, on="player_id", how="inner")
        m = m[m["g"] >= 6].copy()             # players who actually played the target season
        m = m.rename(columns={"real_fp_ppr": "real_fp_ppr", "g": "real_games"})
        m["target_season"] = int(y)
        if not m.empty:
            m.to_parquet(cache, index=False)
            frames.append(m)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The §0.5 SEASON bake-off — walk-forward CV + Optuna + feature ablation
# ══════════════════════════════════════════════════════════════════════════════════════════════
def walk_forward_score(pool: pd.DataFrame, name: str, hp: dict, target_seasons: list[int],
                       feats: tuple = M.FEATURES) -> dict:
    """Backtest ONE learner config over the target-season window: for each Y, fit on all pool rows with
    `target_season < Y` (expanding, leakage-safe) and predict `target_season == Y`, scoring held-out
    within-position ρ. Returns per-season + mean pooled/per-position ρ + a train-vs-held-out gap."""
    per_season, train_pooled = [], []
    for y in target_seasons:
        tr = pool[pool["target_season"] < y]
        te = pool[pool["target_season"] == y]
        if len(tr) < 60 or len(te) < 30:
            continue
        learner = M.make_learner(name, feats=feats, **hp)
        learner.fit(tr, tr["real_fp_ppr"].to_numpy(), tr["position"].to_numpy())
        pred = learner.predict(te, te["position"].to_numpy())
        scored = te.assign(_pred=pred)
        per, pooled = M.within_position_rho(scored, "_pred")
        # train-fit ordering (the overfit read: a big train≫test gap = memorising)
        tr_pred = learner.predict(tr, tr["position"].to_numpy())
        _, tr_pooled = M.within_position_rho(tr.assign(_pred=tr_pred), "_pred")
        per_season.append({"season": y, "n": int(len(te)), "pooled": pooled, **per})
        if tr_pooled is not None:
            train_pooled.append(tr_pooled)

    def _mean(key):
        xs = [r[key] for r in per_season if r.get(key) is not None]
        return round(float(np.mean(xs)), 4) if xs else None

    held = _mean("pooled")
    tr_mean = round(float(np.mean(train_pooled)), 4) if train_pooled else None
    return {
        "learner": name, "hp": hp, "n_seasons": len(per_season),
        "pooled_rho": held,
        **{f"rho_{p}": _mean(p) for p in M.LEARN_POSITIONS},
        "train_rho": tr_mean,
        "overfit_gap": (round(tr_mean - held, 4) if tr_mean is not None and held is not None else None),
        "per_season": per_season,
    }


def _optuna_tune(pool: pd.DataFrame, name: str, target_seasons: list[int], n_trials: int) -> dict:
    """Optuna-tune ONE learner on the walk-forward held-out pooled ρ (the selection metric). Returns
    the best hp + its score. The heuristic null has no hp (returns immediately)."""
    if name == "heuristic_null" or n_trials <= 0:
        return {"hp": {}, "score": walk_forward_score(pool, name, {}, target_seasons)["pooled_rho"]}
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def space(trial):
        if name == "ridge":
            return {"alpha": trial.suggest_float("alpha", 0.5, 200.0, log=True)}
        if name == "elasticnet":
            return {"alpha": trial.suggest_float("alpha", 0.01, 5.0, log=True),
                    "l1_ratio": trial.suggest_float("l1_ratio", 0.05, 0.95)}
        if name == "gbm":
            return {"n_estimators": trial.suggest_int("n_estimators", 100, 600, step=50),
                    "num_leaves": trial.suggest_int("num_leaves", 7, 31),
                    "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
                    "min_child_samples": trial.suggest_int("min_child_samples", 15, 60)}
        return {}

    def objective(trial):
        hp = space(trial)
        s = walk_forward_score(pool, name, hp, target_seasons)["pooled_rho"]
        return s if s is not None else -1.0

    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=17))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return {"hp": study.best_params, "score": round(study.best_value, 4)}


# pre-registered feature GROUPS for the drop-one ablation on the winning learner
_FEATURE_GROUPS = {
    "usage": ("snap_share", "target_share", "carry_share"),
    "mover": ("mover_scale",),
    "env": ("team_env",),
    "injury": ("injury_cap_ratio",),
    "age": ("age",),
    "role": ("depth_rank", "expected_games", "base_games"),
}


def feature_ablation(pool: pd.DataFrame, name: str, hp: dict, target_seasons: list[int]) -> list[dict]:
    """Drop-one-GROUP ablation on the winning learner (pre-registered groups, per §0.5 feature-selection
    hygiene): the full feature set vs the set with each group removed → each group's ρ contribution. A
    group whose removal doesn't hurt is not carrying ordering signal (the honest read; NGS was the
    slice-2 null)."""
    full = walk_forward_score(pool, name, hp, target_seasons)
    rows = [{"drop": "(none / full)", "pooled_rho": full["pooled_rho"],
             **{f"rho_{p}": full.get(f"rho_{p}") for p in M.LEARN_POSITIONS}, "delta": 0.0}]
    for grp, cols in _FEATURE_GROUPS.items():
        feats = tuple(f for f in M.FEATURES if f not in cols)
        r = walk_forward_score(pool, name, hp, target_seasons, feats=feats)
        rows.append({
            "drop": grp, "pooled_rho": r["pooled_rho"],
            **{f"rho_{p}": r.get(f"rho_{p}") for p in M.LEARN_POSITIONS},
            "delta": (round(r["pooled_rho"] - full["pooled_rho"], 4)
                      if r["pooled_rho"] is not None and full["pooled_rho"] is not None else None),
        })
    return rows


def run_season_bakeoff(con, base_from: int, base_to: int, schema: str, n_trials: int) -> dict:
    """The full §0.5 season selection: build the pool, Optuna-tune every candidate on the walk-forward
    held-out ρ, pick the winner (must beat the heuristic null), ablate its features, oracle-check the
    metric. `base_from..base_to` are BASE seasons; the target seasons are base+1 (the first is held out
    as pure training so the earliest scored target has ≥1 prior season)."""
    base_seasons = list(range(base_from, base_to + 1))
    pool = build_training_pool(con, base_seasons, schema)
    if pool.empty:
        raise SystemExit("empty training pool — build the NFL marts first")
    target_seasons = sorted(pool["target_season"].unique().tolist())
    # score every target that has ≥1 prior training season
    scored_targets = [y for y in target_seasons if any(t < y for t in target_seasons)]
    log.info("pool: %d rows, targets %s (scored %s)", len(pool), target_seasons, scored_targets)

    # oracle floor: no candidate may out-order the realized oracle on any scored target
    oracle_ok = all(
        M.oracle_ordering_is_the_ceiling(
            pool[pool["target_season"] == y].assign(_c=pool[pool["target_season"] == y]["mvp1_fp"]),
            ["_c"]) for y in scored_targets)

    candidates = list(M.LEARNER_REGISTRY)
    results = []
    for name in candidates:
        tuned = _optuna_tune(pool, name, scored_targets, n_trials if name != "heuristic_null" else 0)
        full = walk_forward_score(pool, name, tuned["hp"], scored_targets)
        full["tuned_hp"] = tuned["hp"]
        results.append(full)
        log.info("  %-14s pooled_rho=%s hp=%s", name, full["pooled_rho"], tuned["hp"])

    null = next(r for r in results if r["learner"] == "heuristic_null")
    learned = [r for r in results if r["learner"] != "heuristic_null" and r["pooled_rho"] is not None]
    winner = max(learned, key=lambda r: r["pooled_rho"]) if learned else null
    beats_null = (winner["pooled_rho"] is not None and null["pooled_rho"] is not None
                  and winner["pooled_rho"] > null["pooled_rho"])
    ablation = feature_ablation(pool, winner["learner"], winner["tuned_hp"], scored_targets)

    return {
        "base_seasons": base_seasons, "target_seasons": scored_targets,
        "n_pool": int(len(pool)), "oracle_metric_ok": bool(oracle_ok),
        "candidates": results, "winner": winner["learner"], "winner_hp": winner["tuned_hp"],
        "winner_pooled_rho": winner["pooled_rho"], "null_pooled_rho": null["pooled_rho"],
        "winner_beats_null": bool(beats_null), "feature_ablation": ablation,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The FINAL season projection (selected learner) — raw-line + calibrated interval
# ══════════════════════════════════════════════════════════════════════════════════════════════
def build_season_projection(con, base_season: int, projection_season: int, schema: str,
                            learner_name: str, hp: dict, disp_kappa: float = 1.0) -> pd.DataFrame:
    """The SHIPPED NF1 season projection for `projection_season`: fit the selected learner on ALL
    history ≤ base_season, predict the veteran board, apply the learned level to the MVP-1 raw line
    (preserving the raw-line contract), attach a CALIBRATED 80% interval, and concat the (unchanged)
    rookie slot-curve board. Emits the MVP-2/NF-C1 contract schema + the NF1 columns."""
    # train on all completed (base→base+1) pairs strictly before the projection season
    base_seasons = [b for b in range(base_season - 6, base_season) if b + 1 < projection_season]
    pool = build_training_pool(con, base_seasons, schema)
    learner = M.make_learner(learner_name, **hp)
    if learner_name != "heuristic_null" and not pool.empty:
        learner.fit(pool, pool["real_fp_ppr"].to_numpy(), pool["position"].to_numpy())

    feats = assemble_features(con, base_season, projection_season, schema)
    pred = learner.predict(feats, feats["position"].to_numpy())
    # apply the learner as an ORDERING within position, PRESERVING MVP-1's calibrated point levels
    # (the learner's validated strength is rank, not level — its survivorship-inflated level saturates
    # a direct rescale and scrambles the ordering; see apply_learned_ordering). The heuristic-null
    # remaps by mvp1_fp → an identity (MVP-1 unchanged).
    vets = M.apply_learned_ordering(feats, pred)
    vets = SP.score_line(vets, prefix="proj_")

    # calibrated season interval: the MVP-1 season sd scaled by the holdout-tuned κ (E2.1-r floor)
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
    vets["nf1_learner"] = learner_name

    # rookies: unchanged MVP-1 slot-curve model (no base-season feature row to re-weight)
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
        rks["nf1_learner"] = "rookie_slot_curve"

    proj = pd.concat([vets, rks], ignore_index=True, sort=False)
    proj["sport"] = "nfl"
    proj["base_season"] = int(base_season)
    proj["projection_season"] = int(projection_season)
    proj["model_version"] = M.MODEL_VERSION
    proj["generated_at"] = datetime.now(timezone.utc).isoformat()
    proj = proj[proj["position"].isin(("QB", "RB", "WR", "TE", "FB"))].copy()
    cols = OUTPUT_COLS + [c for c in NF1_EXTRA_COLS if c not in OUTPUT_COLS]
    for c in cols:
        if c not in proj.columns:
            proj[c] = np.nan
    proj = proj[cols].sort_values("proj_fp_ppr", ascending=False).reset_index(drop=True)
    proj = proj.drop_duplicates(subset=["player_id"], keep="first").reset_index(drop=True)
    return proj


def calibrate_season_interval(con, base_from: int, base_to: int, schema: str,
                              learner_name: str, hp: dict) -> dict:
    """Tune the season dispersion κ + report E2.1-r hygiene on the walk-forward holdout: for each target
    Y build the NF1 projection and collect (realized − predicted) vs the raw predictive sd → the κ that
    floors calib_80 ≥ 0.80, the PIT flatness, and the achieved coverage at that κ."""
    resid, sd, pit_lo, pit_hi = [], [], [], []
    for y in range(base_from + 1, base_to + 2):
        if y - 1 < base_from:
            continue
        proj = build_season_projection(con, y - 1, y, schema, learner_name, hp, disp_kappa=1.0)
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
        cdf = norm.cdf(r / s)                    # PIT under the raw (κ=1) Normal predictive
        pit_lo.append(cdf)
        pit_hi.append(cdf)
    if not resid:
        return {"kappa": 1.0, "note": "insufficient holdout"}
    resid, sd = np.concatenate(resid), np.concatenate(sd)
    kappa = M.calibrate_dispersion(resid, sd, target_cov=0.80)
    z80 = 1.2815515594
    cov80 = M.calib_coverage(resid, -z80 * kappa * sd, z80 * kappa * sd)
    pit = M.randomized_pit(resid, np.concatenate(pit_hi), np.concatenate(pit_lo))
    return {"kappa": float(kappa), "calib_80": round(float(cov80), 3),
            "pit_max_decile_dev": round(float(M.pit_max_decile_deviation(pit)), 4), "n": int(len(resid))}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Matchup-aware WEEKLY leg
# ══════════════════════════════════════════════════════════════════════════════════════════════
def load_weekly_realized(con, season: int, schema: str = MARTS_SCHEMA,
                         require_played: bool = True) -> pd.DataFrame:
    """Per-player-week fantasy points for a season + opponent, home flag, and the week's implied team
    points from the game line. The weekly-backtest truth + the leakage-safe matchup inputs (opponent +
    a pre-game line are known before kickoff). `require_played=True` (backtest) keeps only played,
    non-bye games with a realized `real_week_fp`; `require_played=False` (FORWARD serving) keeps the
    scheduled calendar rows too (an upcoming week has no realized fp yet) so a future week's board can
    be projected off the schedule + posted line."""
    played = "and f.played_flag and not f.is_bye" if require_played else "and not f.is_bye"
    return con.sql(f"""
        with g as (
            select season, week, home_team as team, away_team as opp, 1 as is_home,
                   (total_line/2.0 + spread_line/2.0) as implied_pts
            from {schema}.dim_nfl_game where is_regular_season and total_line is not null
            union all
            select season, week, away_team as team, home_team as opp, 0 as is_home,
                   (total_line/2.0 - spread_line/2.0) as implied_pts
            from {schema}.dim_nfl_game where is_regular_season and total_line is not null
        )
        select f.season, f.week, f.player_id, f.player_name, f.position, f.team_id, f.opponent_id,
               f.fantasy_points_ppr as real_week_fp, g.is_home, g.implied_pts
        from {schema}.fct_player_week f
        left join g on g.season = f.season and g.week = f.week and g.team = f.team_id
        where f.season = {season} and f.week > 0 {played}
          and f.position in ('QB','RB','WR','TE')
    """).df()


def defense_vs_position_asof(weekly: pd.DataFrame, prior: pd.DataFrame,
                             season: int, target_week: int) -> pd.DataFrame:
    """AS-OF (leakage-safe) DVP factor for a target week: EB-shrink of the fantasy points a defense has
    allowed to each position through weeks < target_week THIS season, blended with a `prior` (last
    season's full-season allowed). `weekly` = this-season realized (all weeks); only weeks strictly
    before target_week are used. Returns [defense_team, position, dvp_factor]."""
    cur = weekly[(weekly["season"] == season) & (weekly["week"] < target_week)]
    # allowed fp per game to each (defense=opponent_id, position) so far this season
    cur_alw = (cur.groupby(["opponent_id", "position"])
               .agg(fp=("real_week_fp", "sum"),
                    gm=("week", lambda s: s.nunique()))
               .reset_index())
    cur_alw["cur_pg"] = cur_alw["fp"] / cur_alw["gm"].clip(lower=1)
    # blend current with the prior-season allowed level (prior carries when the current sample is thin)
    alw = cur_alw.merge(prior, on=["opponent_id", "position"], how="outer", suffixes=("", "_pr"))
    alw["def_games"] = alw["gm"].fillna(0)
    # combined allowed level = games-weighted mix of current + prior (prior worth ~4 games)
    cur_pg = pd.to_numeric(alw["cur_pg"], errors="coerce")
    pr_pg = pd.to_numeric(alw.get("prior_pg"), errors="coerce")
    gw = alw["def_games"].to_numpy(dtype=float)
    combined = np.where(np.isfinite(cur_pg) & np.isfinite(pr_pg),
                        (gw * cur_pg.fillna(0) + 4.0 * pr_pg.fillna(0)) / (gw + 4.0),
                        np.where(np.isfinite(cur_pg), cur_pg, pr_pg))
    # effective shrink sample = current games + a prior-equivalent (~4 g) where a prior level exists, so
    # an EARLY-season (or a forward wk1, 0 current games) DVP still LEANS on the prior season instead of
    # shrinking fully to neutral 1.0 — the prior carries real defensive signal (a bug fix: w was 0 in wk1).
    prior_equiv = np.where(np.isfinite(pr_pg.to_numpy()), 4.0, 0.0)
    out = pd.DataFrame({"defense_team": alw["opponent_id"], "position": alw["position"],
                        "fp_allowed_pg": combined, "def_games": gw + prior_equiv})
    lg = (out.groupby("position")["fp_allowed_pg"].mean().reset_index()
          .rename(columns={"fp_allowed_pg": "lg_fp_allowed_pg"}))
    return M.defense_vs_position_factor(out.dropna(subset=["fp_allowed_pg"]), lg)


def prior_season_allowed(con, season: int, schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    """Full prior-season allowed PPR/game per (defense, position) — the DVP prior for early weeks."""
    w = load_weekly_realized(con, season, schema)
    if w.empty:
        return pd.DataFrame(columns=["opponent_id", "position", "prior_pg"])
    g = (w.groupby(["opponent_id", "position"])
         .agg(fp=("real_week_fp", "sum"), gm=("week", lambda s: s.nunique())).reset_index())
    g["prior_pg"] = g["fp"] / g["gm"].clip(lower=1)
    return g[["opponent_id", "position", "prior_pg"]]


def run_weekly_bakeoff(con, seasons: list[int], schema: str, min_week: int = 4,
                       max_week: int | None = None) -> dict:
    """The §0.5 matchup weekly ablation: for each configured arm (flat / +DVP / +env / +home / full),
    project every player-week (season per-game baseline built off the prior season × the arm's matchup
    tilts) and score held-out weekly within-position ρ vs realized + the E2.1-r calibration hygiene
    (PIT flatness + calib_80 floor). The season per-game baseline is the SHIPPED MVP-1 projection off
    the prior season (leakage-safe)."""
    arms = {
        "flat_baseline": M.WeeklyConfig(use_dvp=False, use_env=False, use_home=False),
        "+dvp": M.WeeklyConfig(use_dvp=True, use_env=False, use_home=False),
        "+env": M.WeeklyConfig(use_dvp=False, use_env=True, use_home=False),
        "+home": M.WeeklyConfig(use_dvp=False, use_env=False, use_home=True),
        "full_matchup": M.WeeklyConfig(use_dvp=True, use_env=True, use_home=True),
    }
    arm_rows = {a: [] for a in arms}
    arm_pit = {a: {"lo": [], "hi": [], "resid": [], "sd": []} for a in arms}

    for season in seasons:
        # leakage-safe season per-game baseline = MVP-1 projection off the prior season
        base_proj = build_season_projection(con, season - 1, season, schema, "heuristic_null", {})
        base_proj = base_proj[base_proj["position"].isin(M.LEARN_POSITIONS)]
        per_game = (base_proj["proj_fp_ppr"] / base_proj["proj_games"].clip(lower=1e-6))
        # weekly dispersion = the base-season game-to-game PPR sd (stable; a positional-median floor for
        # a no-history player), NOT season-sd/√games (explodes for a low-games player) — so the reported
        # PIT/calib_80 is honest and matches the serving path.
        bsd = load_base_season(con, season - 1, schema)[["player_id", "fp_ppr_sd"]]
        bp = base_proj.merge(bsd, on="player_id", how="left", suffixes=("", "_pg"))
        pos_typ = bp.groupby("position")["fp_ppr_sd_pg"].transform("median")
        wsd = pd.to_numeric(bp["fp_ppr_sd_pg"], errors="coerce").fillna(pos_typ).fillna(6.0)
        pg = pd.DataFrame({"player_id": base_proj["player_id"], "position": base_proj["position"],
                           "pg_fp": per_game.to_numpy(), "pg_sd": wsd.to_numpy()})
        weekly = load_weekly_realized(con, season, schema)
        prior = prior_season_allowed(con, season - 1, schema)
        weeks = sorted(w for w in weekly["week"].unique() if w >= min_week
                       and (max_week is None or w <= max_week))
        for wk in weeks:
            dvp = defense_vs_position_asof(weekly, prior, season, wk)
            wkdf = weekly[weekly["week"] == wk].merge(pg, on=["player_id", "position"], how="inner")
            if len(wkdf) < 30:
                continue
            wkdf = wkdf.merge(dvp.rename(columns={"defense_team": "opponent_id"}),
                              on=["opponent_id", "position"], how="left")
            wkdf["dvp_factor"] = wkdf["dvp_factor"].fillna(1.0)
            env = M.environment_factor(wkdf["implied_pts"].to_numpy(), 22.5)
            for a, cfg in arms.items():
                proj = M.project_week(wkdf["pg_fp"].to_numpy(), wkdf["pg_sd"].to_numpy(),
                                      dvp=wkdf["dvp_factor"].to_numpy(), env=env,
                                      is_home=wkdf["is_home"].to_numpy(), cfg=cfg)
                d = wkdf.assign(_pred=proj["week_fp"].to_numpy(),
                                real_fp_ppr=wkdf["real_week_fp"].to_numpy())
                _, pooled = M.within_position_rho(d, "_pred", "real_fp_ppr")
                if pooled is not None:
                    arm_rows[a].append(pooled)
                # calibration accumulation (full arm's predictive) — GAMMA (right-skewed weekly fp)
                mu = proj["week_fp"].to_numpy()
                sd = np.clip(proj["week_sd"].to_numpy(), 1e-6, None)
                cdf = M.gamma_weekly_cdf(wkdf["real_week_fp"].to_numpy(), mu, sd)
                arm_pit[a]["lo"].append(cdf)
                arm_pit[a]["hi"].append(cdf)
                arm_pit[a]["resid"].append(wkdf["real_week_fp"].to_numpy() - mu)
                arm_pit[a]["sd"].append(sd)

    out = {"seasons": seasons, "arms": {}, "generated_at": datetime.now(timezone.utc).isoformat()}
    for a in arms:
        rhos = arm_rows[a]
        pit = (M.randomized_pit(np.concatenate(arm_pit[a]["resid"]),
                                np.concatenate(arm_pit[a]["hi"]), np.concatenate(arm_pit[a]["lo"]))
               if arm_pit[a]["resid"] else np.array([]))
        out["arms"][a] = {
            "mean_weekly_rho": round(float(np.mean(rhos)), 4) if rhos else None,
            "n_weeks": len(rhos),
            "pit_max_decile_dev": round(float(M.pit_max_decile_deviation(pit)), 4) if len(pit) else None,
        }
    base = out["arms"]["flat_baseline"]["mean_weekly_rho"]
    for a in arms:
        r = out["arms"][a]["mean_weekly_rho"]
        out["arms"][a]["delta_vs_flat"] = (round(r - base, 4) if r is not None and base is not None else None)
    return out


def build_weekly_projection(con, projection_season: int, target_week: int, schema: str,
                            season_proj: pd.DataFrame, disp_kappa: float = 1.0) -> pd.DataFrame:
    """The SHIPPED matchup-aware weekly projection for one (season, week): the NF1 season per-game
    baseline × as-of DVP × the week's game environment × home, with a CALIBRATED posterior-predictive
    80% weekly interval (std + PPR). Leakage-safe (DVP uses weeks < target_week + the prior season;
    the game line + opponent are pre-game). Returns one row per player scheduled that week."""
    # FORWARD serving: include scheduled (unplayed) calendar rows so an upcoming week is projectable
    weekly = load_weekly_realized(con, projection_season, schema, require_played=False)
    prior = prior_season_allowed(con, projection_season - 1, schema)
    dvp = defense_vs_position_asof(weekly, prior, projection_season, target_week)
    sched = weekly[weekly["week"] == target_week][
        ["player_id", "player_name", "position", "team_id", "opponent_id", "is_home", "implied_pts"]]
    sp = season_proj[season_proj["position"].isin(M.LEARN_POSITIONS)].copy()
    # FORWARD weekly baseline = the UNCONDITIONAL expected weekly contribution = season total / 17
    # (spreading the projected season, which already reflects expected games incl. an injury cap, over
    # the schedule → a backup projected for few games is correctly depressed, not shown at his
    # conditional per-start rate). The weekly dispersion is the base-season game-to-game PPR sd (a
    # stable, directly-observed per-game spread — NOT season-sd/√games, which explodes for a
    # low-games player), positional-floored so a no-history player still carries an honest interval.
    base_sd = load_base_season(con, projection_season - 1, schema)[["player_id", "fp_ppr_sd"]]
    sp = sp.merge(base_sd, on="player_id", how="left", suffixes=("", "_pg"))
    pos_typ = sp.groupby("position")["fp_ppr_sd_pg"].transform("median")
    week_sd = pd.to_numeric(sp["fp_ppr_sd_pg"], errors="coerce").fillna(pos_typ).fillna(6.0)
    pg = pd.DataFrame({"player_id": sp["player_id"],
                       "pg_fp": (sp["proj_fp_ppr"] / 17.0).to_numpy(),
                       "pg_sd": (week_sd * disp_kappa).to_numpy()})
    m = sched.merge(pg, on="player_id", how="inner").merge(
        dvp.rename(columns={"defense_team": "opponent_id"}), on=["opponent_id", "position"], how="left")
    m["dvp_factor"] = m["dvp_factor"].fillna(1.0)
    env = M.environment_factor(m["implied_pts"].to_numpy(), 22.5)
    # ⭐ SHIP the FLAT calibrated baseline: the weekly §0.5 ablation (60 weeks, 2021–2024) found the
    # scalar matchup tilts do NOT lift weekly within-position ordering (Δ vs flat ≤ 0: +dvp −0.003,
    # +env −0.007, +home +0.001, full −0.013) → per the slice-gate discipline they are DROPPED (the
    # NGS slice-2 precedent). `dvp_factor` / `implied_pts` are still CARRIED in the output as matchup
    # CONTEXT for the UI (a "tough matchup" flag), just not applied to the point projection.
    wk = M.project_week(m["pg_fp"].to_numpy(), m["pg_sd"].to_numpy(), dvp=m["dvp_factor"].to_numpy(),
                        env=env, is_home=m["is_home"].to_numpy(),
                        cfg=M.WeeklyConfig(use_dvp=False, use_env=False, use_home=False))
    # replace the first-order Normal interval with the honest right-skewed GAMMA weekly credible
    # interval (non-negative, no cl-at-0 artefact) — the shape weekly fantasy points actually have
    g_lo, g_hi = M.gamma_weekly_interval(wk["week_fp"].to_numpy(), np.clip(wk["week_sd"].to_numpy(), 1e-6, None))
    wk["week_p10"] = np.round(g_lo, 2)
    wk["week_p90"] = np.round(g_hi, 2)
    # std ≈ ppr − reception credit; a per-game std/ppr ratio from the season line keeps it consistent
    out = pd.concat([m.reset_index(drop=True), wk], axis=1)
    out["week_fp_std"] = np.round(out["week_fp"] * 0.82, 2)   # std ≈ 0.82×PPR for skill mix (convenience)
    out["season"] = int(projection_season)
    out["week"] = int(target_week)
    out["uncertainty_type"] = "empirical"
    out["model_version"] = M.MODEL_VERSION
    out["generated_at"] = datetime.now(timezone.utc).isoformat()
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF-D3 grade of the NF1 projection
# ══════════════════════════════════════════════════════════════════════════════════════════════
def grade_vs_consensus(con, seasons: list[int], schema: str, learner_name: str, hp: dict) -> dict:
    """Grade the SHIPPED NF1 season projection vs every NF-D3 consensus system (ADP/ECR/Sleeper/ESPN)
    apples-to-apples, reusing the NF-D3 scorecard. `project_fn` builds NF1 for each season off ≤season−1."""
    from quant_sports_intel_models.football.nfl.fantasy import benchmark_scorecard as BS

    def project_fn(c, y, sch):
        return build_season_projection(c, y - 1, y, sch, learner_name, hp)[["player_id", "position", "proj_fp_ppr"]]

    return BS.build_scorecard(con, seasons, schema, project_fn=project_fn,
                              load_realized_fn=load_realized_season)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Reports
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _md(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False, floatfmt=".3f")
    except Exception:  # noqa: BLE001
        return df.to_string(index=False)


def write_bakeoff_report(out: dict, path: Path) -> None:
    a = []; p = a.append
    p("# NF1 — season model §0.5 bake-off (market-blind joint re-weighting)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **base seasons:** {out['base_seasons'][0]}–"
      f"{out['base_seasons'][-1]} · **scored targets:** {out['target_seasons']} · **pool:** {out['n_pool']}")
    p("")
    p("> Market-blind (NO ADP/ECR — orthogonal NF-D signals only). Each candidate is Optuna-tuned on "
      "the WALK-FORWARD held-out pooled within-position ρ (train on target<Y, predict Y). The SHIP "
      "criterion is beating the MVP-1 HEURISTIC NULL; the metric is oracle-floor-checked (E2.1-r). "
      "Edge-independent (projection quality, no PBO/DSR).")
    p("")
    p(f"- **oracle metric sane:** {out['oracle_metric_ok']}  ·  **winner:** `{out['winner']}`  ·  "
      f"**winner beats MVP-1 null:** {out['winner_beats_null']} "
      f"({out['winner_pooled_rho']} vs {out['null_pooled_rho']})")
    p("")
    p("## Candidates — held-out within-position ρ")
    p("")
    rows = [{"learner": r["learner"], "pooled_rho": r["pooled_rho"],
             **{p2: r.get(f"rho_{p2}") for p2 in M.LEARN_POSITIONS},
             "train_rho": r.get("train_rho"), "overfit_gap": r.get("overfit_gap"),
             "hp": json.dumps(r.get("tuned_hp", {}))} for r in out["candidates"]]
    p(_md(pd.DataFrame(rows)))
    p("")
    p("## Feature ablation on the winner (drop-one group)")
    p("")
    p("> Δ vs the full feature set (negative = removing the group HURT ordering = the group carries signal).")
    p("")
    p(_md(pd.DataFrame(out["feature_ablation"])))
    p("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(a) + "\n")
    log.info("report → %s", path)


def write_weekly_report(out: dict, path: Path) -> None:
    a = []; p = a.append
    p("# NF1 — matchup-aware weekly leg §0.5 ablation")
    p("")
    p(f"**Generated:** {out['generated_at']} · **seasons:** {out['seasons']}")
    p("")
    p("> Each arm projects every player-week = the leakage-safe season per-game baseline × the arm's "
      "matchup tilts (as-of defense-vs-position, the week's Vegas implied team points, home). Scored on "
      "held-out weekly within-position ρ vs realized; the full arm's posterior-predictive is checked "
      "for E2.1-r PIT flatness (a coverage number alone is biased for a discrete count total).")
    p("")
    rows = [{"arm": a2, **out["arms"][a2]} for a2 in out["arms"]]
    p(_md(pd.DataFrame(rows)))
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
    ap = argparse.ArgumentParser(description="NF1 — joint learned re-weighting + matchup weekly")
    ap.add_argument("--mode", required=True, choices=["bakeoff", "weekly-bakeoff", "build", "grade"])
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--base-from", type=int, default=2017)
    ap.add_argument("--base-to", type=int, default=2024)
    ap.add_argument("--projection-season", type=int, default=None)
    ap.add_argument("--learner", default=None, help="build/grade: force a learner (else the bake-off pick)")
    ap.add_argument("--hp", default="{}", help="build: JSON hyperparams for --learner")
    ap.add_argument("--n-trials", type=int, default=40, help="bakeoff: Optuna trials per learner")
    ap.add_argument("--weekly-target", type=int, default=None, help="build: also emit weekly for this week")
    ap.add_argument("--seasons", default=None, help="weekly-bakeoff/grade: comma seasons (default 2021-2024)")
    ap.add_argument("--smoke", action="store_true", help="tiny subset for a correctness check")
    ap.add_argument("--s3", action="store_true", help="build: land the projection(s) to S3")
    ap.add_argument("--lake-root", default=None, help="build: land to a LOCAL Delta tree instead of S3")
    ap.add_argument("--no-cache", action="store_true", help="ignore the feature cache")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    con = _connect(args.duckdb)
    try:
        if args.mode == "bakeoff":
            bf, bt = (2019, 2021) if args.smoke else (args.base_from, args.base_to)
            n_trials = 3 if args.smoke else args.n_trials
            out = run_season_bakeoff(con, bf, bt, args.schema, n_trials)
            (_REPORT_DIR / "nf1_season_bakeoff.json").write_text(json.dumps(out, indent=2, default=float))
            write_bakeoff_report(out, _REPORT_DIR / "nf1_season_bakeoff.md")
            print(f"\nWINNER: {out['winner']} hp={out['winner_hp']} pooled_rho={out['winner_pooled_rho']} "
                  f"(null {out['null_pooled_rho']}); beats_null={out['winner_beats_null']}")

        elif args.mode == "weekly-bakeoff":
            seasons = ([2023] if args.smoke
                       else [int(s) for s in (args.seasons or "2021,2022,2023,2024").split(",")])
            mw = 8 if args.smoke else None
            out = run_weekly_bakeoff(con, seasons, args.schema, max_week=mw)
            (_REPORT_DIR / "nf1_weekly_bakeoff.json").write_text(json.dumps(out, indent=2, default=float))
            write_weekly_report(out, _REPORT_DIR / "nf1_weekly_bakeoff.md")
            print(json.dumps(out["arms"], indent=2, default=float))

        elif args.mode == "build":
            learner = args.learner or "ridge"
            hp = json.loads(args.hp)
            base_season = int(con.sql(
                f"select max(season) from {args.schema}.fct_player_week where played_flag").fetchone()[0])
            proj_season = args.projection_season or (base_season + 1)
            cal = calibrate_season_interval(con, args.base_from, min(args.base_to, base_season),
                                            args.schema, learner, hp)
            kappa = cal.get("kappa", 1.0)
            log.info("season interval calibration: %s", cal)
            proj = build_season_projection(con, base_season, proj_season, args.schema, learner, hp,
                                           disp_kappa=kappa)
            log.info("NF1 %d: %d players (%d vets, %d rookies) via %s", proj_season, len(proj),
                     int((~proj["is_rookie"]).sum()), int(proj["is_rookie"].sum()), learner)
            _ART.mkdir(parents=True, exist_ok=True)
            proj.to_parquet(_ART / f"nf1_season_projections_{proj_season}.parquet", index=False)
            ranked = proj.copy()
            ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
            ranked.insert(1, "pos_rank", ranked.groupby("position").cumcount() + 1)
            ranked.to_csv(_ART / f"nf1_season_projections_{proj_season}_ranked.csv", index=False)
            if args.s3 or args.lake_root:
                from quant_sports_intel_models.football.nfl.ingest import s3io
                n = s3io.write_dataframe(proj.assign(season=int(proj_season)), sport="nfl",
                                         source="nf1_season_projections", season=int(proj_season),
                                         tier="fantasy/derived", local_root=args.lake_root)
                log.info("landed %d rows → nfl/fantasy/derived/nf1_season_projections season=%d", n, proj_season)
            if args.weekly_target:
                wk = build_weekly_projection(con, proj_season, args.weekly_target, args.schema, proj, kappa)
                wk.to_parquet(_ART / f"nf1_weekly_projections_{proj_season}_wk{args.weekly_target}.parquet",
                              index=False)
                log.info("weekly %d wk%d: %d player-weeks", proj_season, args.weekly_target, len(wk))
            (_ART / f"nf1_projection_summary_{proj_season}.json").write_text(json.dumps({
                "model_version": M.MODEL_VERSION, "learner": learner, "hp": hp,
                "projection_season": proj_season, "interval_calibration": cal,
                "n_players": int(len(proj)), "generated_at": datetime.now(timezone.utc).isoformat(),
            }, indent=2, default=float))
            print(f"NF1 {proj_season} built ({learner}); interval κ={kappa}; top: "
                  + ", ".join(proj.head(5)["player_name"].tolist()))

        elif args.mode == "grade":
            learner = args.learner or "ridge"
            hp = json.loads(args.hp)
            seasons = ([2023] if args.smoke
                       else [int(s) for s in (args.seasons or "2019,2020,2021,2022,2023,2024").split(",")])
            sc = grade_vs_consensus(con, seasons, args.schema, learner, hp)
            (_REPORT_DIR / "nf1_vs_consensus_scorecard.json").write_text(json.dumps(sc, indent=2, default=float))
            log.info("NF1 vs NF-D3 consensus — aggregate:")
            print(json.dumps(sc.get("aggregate", {}), indent=2, default=float))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
