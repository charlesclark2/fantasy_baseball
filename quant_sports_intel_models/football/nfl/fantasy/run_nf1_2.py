"""run_nf1_2.py — NF1.2 CLI/IO: the projection-refinement family bake-off + deflation + report.

NF1.2 = the pre-registered "what NF1 doesn't yet account for" FEATURE FAMILIES (H-SOS / H-SYSTEM /
H-CORR / H-OLINE-via-cap / H-OPP / H-SPILL / H-CONTRACT — see `nf1_2_model.py` for the full
registration) folded into NF1.1's per-position harness and ablated for held-out TOP-TIER lift under
the full deflation kit. MARKET-BLIND; the verdict is vs the market-BLIND baseline (MVP-1, the
fade-claim board — NF1.3's market-aware dual-board owns QB/RB product ordering).

⭐ RUN ON THE LAPTOP (like run_nf1/run_nf1_1): SF-free, sports-lake DuckDB + local caches only.

MODES:
  * `bakeoff` — per position: Optuna-tune pos_ridge / pos_gbm / pos_similarity on the FULL
                extended set vs the MVP-1 null; then the ATTRIBUTION arms — the winner's class+hp
                on the NF1.1 BASE set (how much do the new families jointly add?), ADD-ONE-family
                arms (base + one family — the per-family lift a drop-one can mask under overlap),
                and DROP-ONE-group arms (full − one group). EVERY config counts toward the
                deflation (CSCV-PBO / spread / DSR / BH-FDR across positions).
                → ablation_results/nf1_2_refinements.{md,json}
  * `grade`   — the NF-D3 consensus scorecard over the NF1.2 board (survivor/beats-null
                selections), apples-to-apples with the stored MVP-1/NF1/NF1.1/NF1.3 runs.
  * `build`   — the final projection (ordering-only over MVP-1's calibrated multiset), landed to
                its own S3 prefix `nfl/fantasy/derived/nf1_2_season_projections`.

Heavy runs (>1 min) are the operator's; `--smoke` runs a tiny subset and writes `*_smoke` reports.
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

from quant_sports_intel_models.football.nfl.fantasy import contract_source as CS  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import defense_source as DS  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M11  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_2_model as M12  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_model as M1  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.run_nf1 import (  # noqa: E402
    assemble_features,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf1_1 import (  # noqa: E402
    _finite_top,
    _optuna_tune_pos,
    _season_row,
    _sharpe,
    attach_xfp,
    walk_forward_pos,
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

log = logging.getLogger("nfl.fantasy.nf1_2")

_ART = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_FEATURE_CACHE = _ART / "nf1_2_feature_cache"

NF1_2_EXTRA_COLS = ["nf1_scale", "nf1_2_learner"]

_LEARNED_CANDIDATES = ("pos_ridge", "pos_gbm", "pos_similarity")

_STAGING_SCHEMA = "main_nfl_staging"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Input loaders (assemble-once; every family input loaded a single time per run)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def load_schedule(con, proj_seasons: list[int], staging: str = _STAGING_SCHEMA) -> pd.DataFrame:
    seasons = ",".join(str(int(s)) for s in proj_seasons)
    return con.sql(f"""
        select season, home_team, away_team from {staging}.stg_nfl_schedules
        where is_regular_season and season in ({seasons})
    """).df()


def load_team_rates(con, schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    """Realized per-team-season pass rate + pace (rollup coverage starts 2020 — earlier base
    seasons stay NaN, same posture as `team_env`'s 2020 floor)."""
    return con.sql(f"""
        select season, team, off_pass_rate, off_plays_per_game
        from {schema}.rollup_nfl_team_season
    """).df()


def load_opp_shares(con, base_seasons: list[int], schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    """Base-season opportunity-share anchors per player: mean over played, non-bye weeks of
    `air_yards_share` + `weighted_opportunity_rating` (WOPR) from the weekly mart."""
    seasons = ",".join(str(int(s)) for s in base_seasons)
    return con.sql(f"""
        select season, player_id,
               avg(air_yards_share) as air_yards_share,
               avg(weighted_opportunity_rating) as wopr
        from {schema}.fct_player_week
        where played_flag and not is_bye and week > 0 and season in ({seasons})
          and player_id is not null
        group by 1, 2
    """).df()


def load_defense(con, proj_seasons: list[int]) -> pd.DataFrame:
    """NF-D6 forward defense strength per projection season, computed from the LOCAL strength
    cache (`defense_strength_cache`, seasons 2015–2025 → projections 2016–2026). Continuity is
    passed EMPTY on purpose: the SHIP config's churn levers are 0 (NF-D6's null), so the strength
    point estimate is continuity-free and the S3 snap/roster read is skipped."""
    frames = []
    for s in proj_seasons:
        try:
            d = DS.build_forward_defense(con, int(s), continuity=pd.DataFrame())
        except Exception as exc:  # noqa: BLE001 — a season without cached strengths stays NaN
            log.warning("forward defense unavailable for %s (%s)", s, str(exc)[:120])
            continue
        if d is None or d.empty:
            log.warning("forward defense EMPTY for %s", s)
            continue
        frames.append(d[["projection_season", "team", "pass_def_strength", "rush_def_strength"]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_contracts(proj_seasons: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """NF-D8 contract features per projection season (leakage-safe: `year_signed ≤ season`),
    computed from the cached nflverse contracts release (no network when the cache is warm).
    Returns (player_frames, team_frames) stacked across seasons."""
    players, teams = [], []
    raw = CS.fetch_historical_contracts()
    for s in proj_seasons:
        p, t = CS.build_contract_features(int(s), contracts=raw)
        if not p.empty:
            players.append(p)
        if not t.empty:
            teams.append(t)
    return (pd.concat(players, ignore_index=True) if players else pd.DataFrame(),
            pd.concat(teams, ignore_index=True) if teams else pd.DataFrame())


def load_coach(proj_seasons: list[int]) -> pd.DataFrame:
    """NF-D10 coaching-regime features per projection season (leakage-safe: built from stints
    known as of March 15 of that season). The stint table is assembled ONCE across the whole
    window — tenure and 'who finished last season' both need seasons before the window's floor —
    and every projection season's row set is derived from that one frame (assemble-once)."""
    from quant_sports_intel_models.football.nfl.fantasy import coaching_source as CO

    if not proj_seasons:
        return pd.DataFrame()
    lo, hi = min(proj_seasons), max(proj_seasons)
    try:
        stints = CO.build_coach_stints(list(range(lo - 1, hi + 1)), current_season=hi)
    except Exception as exc:  # noqa: BLE001 — an unreachable source leaves the family NaN
        log.warning("coaching source unavailable (%s) — H-COACH stays NaN", str(exc)[:120])
        return pd.DataFrame()
    frames = [CO.build_team_coach_features(stints, int(s)) for s in proj_seasons]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_inputs(con, base_seasons: list[int], schema: str = MARTS_SCHEMA) -> M12.RefinementInputs:
    proj_seasons = sorted({b + 1 for b in base_seasons})
    pc, tc = load_contracts(proj_seasons)
    return M12.RefinementInputs(
        schedule=load_schedule(con, proj_seasons),
        defense=load_defense(con, proj_seasons),
        team_rates=load_team_rates(con, schema),
        opp_shares=load_opp_shares(con, base_seasons, schema),
        player_contracts=pc,
        team_caps=tc,
        coach=load_coach(proj_seasons),
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Feature assembly — FULL veteran frame + families, THEN the realized filter (survivorship order)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def build_extended_frame(con, base_season: int, projection_season: int,
                         inputs: M12.RefinementInputs, schema: str = MARTS_SCHEMA) -> pd.DataFrame:
    """The NF1 veteran feature frame + xFP + every refinement family, for one base season.
    Families attach on the FULL universe (before any target-season filter) — `qbcorr`/`spill`
    derive team aggregates from the frame itself (see `add_refinement_features`)."""
    feats = assemble_features(con, base_season, projection_season, schema)
    if feats.empty:
        return feats
    feats = attach_xfp(con, feats, schema)
    return M12.add_refinement_features(feats, inputs)


def cache_is_current(pool: pd.DataFrame) -> bool:
    """Does a cached pool carry EVERY currently-registered refinement column?

    🧨 The landmine this closes (found wiring NF-D10): the per-base-season parquet caches are
    keyed only by season, so adding a family leaves stale caches that silently lack its columns —
    and a bundle that then asks for them either KeyErrors deep in the matrix prep or, worse, gets
    a median-imputed all-NaN column and reports a clean null for a family that was never actually
    present. A cache missing any registered column is rebuilt instead of trusted. PURE."""
    if pool is None or pool.empty:
        return False
    return all(c in pool.columns for c in M12.REFINEMENT_COLS)


def build_pool(con, base_seasons: list[int], inputs: M12.RefinementInputs,
               schema: str = MARTS_SCHEMA, use_cache: bool = True) -> pd.DataFrame:
    """The NF1.2 walk-forward pool: extended frame per base season joined to the realized target
    season (≥6 games), cached per base season under `nf1_2_feature_cache/`."""
    _FEATURE_CACHE.mkdir(parents=True, exist_ok=True)
    frames = []
    for b in base_seasons:
        y = b + 1
        cache = _FEATURE_CACHE / f"pool_base{b}.parquet"
        if use_cache and cache.exists():
            cached = pd.read_parquet(cache)
            if cache_is_current(cached):
                frames.append(cached)
                continue
            log.info("pool cache base%d predates a registered family — rebuilding", b)
        feats = build_extended_frame(con, b, y, inputs, schema)
        if feats.empty:
            continue
        real = load_realized_season(con, y, schema)
        m = feats.merge(real, on="player_id", how="inner")
        m = m[m["g"] >= 6].copy()
        m = m.rename(columns={"g": "real_games"})
        m["target_season"] = int(y)
        if not m.empty:
            m.to_parquet(cache, index=False)
            frames.append(m)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def family_coverage(pool: pd.DataFrame) -> dict:
    """Non-null coverage per refinement column over the pool (the honest join-health read; the
    contract columns' completed-season coverage cross-checks NF-D8's played_flag lesson)."""
    cov = {}
    for fam, cols in M12.REFINEMENT_FAMILIES.items():
        cov[fam] = {c: round(float(pool[c].notna().mean()), 3) if c in pool.columns else 0.0
                    for c in cols}
    return cov


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The bake-off: full-set tuning + attribution arms (baseline / add-one / drop-one), all deflated
# ══════════════════════════════════════════════════════════════════════════════════════════════
def family_arms(pool: pd.DataFrame, pos: str, winner: dict,
                target_seasons: list[int]) -> tuple[dict, list[dict], list[dict]]:
    """The attribution arms for one position's winner (same class+hp, different feature sets —
    the NF1.1 `feature_ablation_pos` pattern extended for the family question):
      * baseline — the NF1.1 BASE set (no new families): Δ vs the winner = the families' JOINT lift.
      * add-one  — base + ONE family: the family's isolated lift over the NF1.1 baseline (what a
                   drop-one can mask when two families overlap, e.g. qbcorr↔spill).
      * drop-one — full − one group (legacy groups + families): what the winner loses without it.
    """
    base_feats = M12.BASE_POSITION_FEATURES[pos]
    full_feats = M12.POSITION_FEATURES[pos]

    baseline = walk_forward_pos(pool, pos, winner["learner"], winner["hp"], base_feats,
                                target_seasons)
    baseline["arm"] = "nf1_1_baseline"

    add_one = []
    for fam in M12.REFINEMENT_FAMILIES:
        cols = M12._family_cols(fam, pos)
        if not cols:
            continue
        rec = walk_forward_pos(pool, pos, winner["learner"], winner["hp"],
                               base_feats + cols, target_seasons)
        rec["family"] = fam
        rec["delta_vs_baseline"] = (round(rec["mean_top"] - baseline["mean_top"], 4)
                                    if rec["mean_top"] is not None and baseline["mean_top"] is not None
                                    else None)
        add_one.append(rec)

    drop_one = []
    for grp, cols in M12.FEATURE_GROUPS.items():
        drop = tuple(f for f in full_feats if f in cols)
        if not drop:
            continue
        feats = tuple(f for f in full_feats if f not in cols)
        rec = walk_forward_pos(pool, pos, winner["learner"], winner["hp"], feats, target_seasons)
        rec["drop"] = grp
        rec["delta"] = (round(rec["mean_top"] - winner["mean_top"], 4)
                        if rec["mean_top"] is not None and winner["mean_top"] is not None else None)
        drop_one.append(rec)
    return baseline, add_one, drop_one


def run_bakeoff(con, base_from: int, base_to: int, schema: str, n_trials: int,
                use_cache: bool = True) -> dict:
    base_seasons = list(range(base_from, base_to + 1))
    inputs = load_inputs(con, base_seasons, schema)
    pool = build_pool(con, base_seasons, inputs, schema, use_cache=use_cache)
    if pool.empty:
        raise SystemExit("empty training pool — build the NFL marts first")
    targets = sorted(pool["target_season"].unique().tolist())
    scored_targets = [y for y in targets if any(t < y for t in targets)]
    log.info("pool: %d rows, scored targets %s", len(pool), scored_targets)

    oracle_ok = all(
        M11.oracle_top_tier_is_ceiling(pool[pool["target_season"] == y].assign(_c=lambda d: d["mvp1_fp"]),
                                       ["_c"]) for y in scored_targets)

    positions_out: dict[str, dict] = {}
    pvals: dict[str, float | None] = {}
    for pos in M11.POSITIONS:
        feats = M12.POSITION_FEATURES[pos]
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

        baseline, add_one, drop_one = family_arms(pool, pos, winner, scored_targets)
        trial_records.append(baseline)
        trial_records.extend(add_one)
        trial_records.extend(drop_one)

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
        beats_baseline = (winner["mean_top"] is not None and baseline["mean_top"] is not None
                          and winner["mean_top"] > baseline["mean_top"])
        positions_out[pos] = {
            "null": null_rec,
            "best_by_class": best_by_class,
            "winner": winner,
            "nf1_1_baseline": {k: baseline[k] for k in ("mean_top", "mean_full", "per_season_top")},
            "delta_vs_nf1_1_baseline": (round(winner["mean_top"] - baseline["mean_top"], 4)
                                        if winner["mean_top"] is not None and baseline["mean_top"] is not None
                                        else None),
            "beats_baseline": bool(beats_baseline),
            "n_configs": int(len(trial_records)),
            "pbo": pbo, "config_spread": spread, "dsr": dsr, "pvalue": pvals[pos],
            "beats_null": bool(beats_null),
            "family_add_one": [{k: r.get(k) for k in ("family", "mean_top", "delta_vs_baseline")}
                               for r in add_one],
            "feature_ablation": [{k: r.get(k) for k in ("drop", "mean_top", "delta")}
                                 for r in drop_one],
        }

    fdr = M11.bh_fdr(pvals)
    for pos, r in positions_out.items():
        if "winner" not in r:
            r["verdict"] = {"repoint": False, "note": "unscoreable"}
            continue
        r["fdr_pass"] = bool(fdr.get(pos, False))
        r["verdict"] = M11.position_verdict(r["beats_null"], r["pbo"], r["dsr"], r["fdr_pass"])

    return {
        "model_version": M12.MODEL_VERSION,
        "base_seasons": base_seasons, "target_seasons": scored_targets, "n_pool": int(len(pool)),
        "selection_metric": ("top-tier within-position ρ (tier = top-N by the MVP-1 incumbent, "
                             f"N={M11.TOP_N})"),
        "oracle_metric_ok": bool(oracle_ok),
        "n_trials_per_class": n_trials,
        "family_coverage": family_coverage(pool),
        "families": {fam: {"cols": list(cols), "positions": list(M12.FAMILY_POSITIONS[fam])}
                     for fam, cols in M12.REFINEMENT_FAMILIES.items()},
        "unavailable_probed": {"yprr": "routes-run not in any free nflverse table (PFF-gated)",
                               "catchable_rate": "catchable-target flag not available"},
        "positions": positions_out,
        "fdr_q": M11.FDR_Q, "pbo_max": M11.PBO_MAX, "dsr_min": M11.DSR_MIN,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Board / grade (ordering-only over MVP-1's calibrated multiset — the NF1 survivorship lesson)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def load_selection(bakeoff: dict, board: str = "beats-null") -> dict[str, dict]:
    sel = {}
    for pos, r in bakeoff.get("positions", {}).items():
        if "winner" not in r:
            continue
        use = r["verdict"]["repoint"] if board == "gated" else bool(r.get("beats_null"))
        if use:
            sel[pos] = {"learner": r["winner"]["learner"], "hp": r["winner"]["hp"]}
    return sel


def build_season_projection(con, base_season: int, projection_season: int, schema: str,
                            selections: dict[str, dict], inputs: M12.RefinementInputs,
                            base_from: int = 2017, disp_kappa: float = 1.0,
                            pool: pd.DataFrame | None = None) -> pd.DataFrame:
    """The NF1.2 board: selected positions' winners fit on all completed history and applied as a
    WITHIN-POSITION ORDERING over MVP-1's calibrated point multiset (never the learned level);
    unselected positions keep MVP-1's order. Mirrors `run_nf1_1.build_season_projection` with the
    extended feature frame."""
    if pool is None:
        base_seasons = [b for b in range(base_from, base_season) if b + 1 < projection_season]
        pool = (build_pool(con, base_seasons, inputs, schema) if selections else pd.DataFrame())

    feats = build_extended_frame(con, base_season, projection_season, inputs, schema)
    position_scores: dict[str, np.ndarray] = {}
    for pos, sel in selections.items():
        pfeats = M12.POSITION_FEATURES[pos]
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
    vets["nf1_2_learner"] = [
        (selections[p]["learner"] if p in selections else "mvp1_null") for p in vets["position"]]

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
        rks["nf1_2_learner"] = "rookie_slot_curve"

    proj = pd.concat([vets, rks], ignore_index=True, sort=False)
    proj["sport"] = "nfl"
    proj["base_season"] = int(base_season)
    proj["projection_season"] = int(projection_season)
    proj["model_version"] = M12.MODEL_VERSION
    proj["generated_at"] = datetime.now(timezone.utc).isoformat()
    proj = proj[proj["position"].isin(("QB", "RB", "WR", "TE", "FB"))].copy()
    cols = OUTPUT_COLS + [c for c in NF1_2_EXTRA_COLS if c not in OUTPUT_COLS]
    for c in cols:
        if c not in proj.columns:
            proj[c] = np.nan
    proj = proj[cols].sort_values("proj_fp_ppr", ascending=False).reset_index(drop=True)
    proj = proj.drop_duplicates(subset=["player_id"], keep="first").reset_index(drop=True)
    return proj


def grade_vs_consensus(con, seasons: list[int], schema: str, selections: dict[str, dict],
                       base_from: int = 2017) -> dict:
    """The NF-D3 product-metric scorecard over the NF1.2 board — same scorer/universes as the
    stored MVP-1 / NF1 / NF1.1 / NF1.3 runs."""
    from quant_sports_intel_models.football.nfl.fantasy import benchmark_scorecard as BS

    base_seasons = list(range(base_from, max(seasons)))
    inputs = load_inputs(con, base_seasons, schema)

    def project_fn(c, y, sch):
        return build_season_projection(c, y - 1, y, sch, selections, inputs, base_from=base_from)[
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
    p("# NF1.2 — projection-refinement families (SOS / system / corr / O-line-cap / opportunity / "
      "spillover / contract), market-blind")
    p("")
    p(f"**Model:** `{out['model_version']}` · **generated:** {out['generated_at']} · "
      f"**base seasons:** {out['base_seasons'][0]}–{out['base_seasons'][-1]} · **scored targets:** "
      f"{out['target_seasons']} · **pool:** {out['n_pool']} · **Optuna trials/class:** "
      f"{out['n_trials_per_class']}")
    p("")
    p(f"> **Selection metric:** {out['selection_metric']} — incumbent-anchored, oracle-checked. "
      "Candidates per position: pos_ridge / pos_gbm / pos_similarity on the FULL extended set vs "
      "the MVP-1 null, + attribution arms (NF1.1-baseline / add-one-family / drop-one-group) — "
      f"every config deflated. Gates: PBO<{out['pbo_max']} · DSR≥{out['dsr_min']} · BH-FDR "
      f"q={out['fdr_q']}. MARKET-BLIND — the honest win condition is WR/TE + the fade universe "
      "(NF1.3's market-aware board owns QB/RB product ordering). `best_alpha = 0`.")
    p("")
    p(f"- **oracle metric sane:** {out['oracle_metric_ok']}")
    p(f"- **probed-unavailable (honest gaps):** {out['unavailable_probed']}")
    p("")
    p("**Family registration + pool coverage (non-null share):**")
    p("")
    rows = []
    for fam, meta in out["families"].items():
        cov = out["family_coverage"].get(fam, {})
        rows.append({"family": fam, "columns": ", ".join(meta["cols"]),
                     "positions": "/".join(meta["positions"]),
                     "coverage": ", ".join(f"{c}={v}" for c, v in cov.items())})
    p(pd.DataFrame(rows).to_markdown(index=False))
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
        rows.append({"candidate": "winner class on NF1.1 BASE set",
                     "top-tier ρ": _fmt(r["nf1_1_baseline"]["mean_top"]),
                     "full ρ": _fmt(r["nf1_1_baseline"]["mean_full"]), "hp": "(attribution arm)"})
        p(pd.DataFrame(rows).to_markdown(index=False))
        p("")
        v = r["verdict"]
        p(f"- **winner:** `{r['winner']['learner']}` · beats MVP-1 null: **{r['beats_null']}** "
          f"(Δ {_fmt((r['winner']['mean_top'] or 0) - (r['null']['mean_top'] or 0), sign=True)}) · "
          f"beats NF1.1-baseline arm: **{r['beats_baseline']}** "
          f"(families' joint Δ {_fmt(r['delta_vs_nf1_1_baseline'], sign=True)})")
        p(f"- **deflation** ({r['n_configs']} configs): PBO {_fmt(r['pbo'])} (spread "
          f"{_fmt(r['config_spread'])}) · DSR {_fmt(r['dsr'])} · p {_fmt(r['pvalue'])} · "
          f"FDR pass {r.get('fdr_pass')}")
        p(f"- **verdict:** {'REPOINT-ELIGIBLE' if v['repoint'] else 'NULL — MVP-1 stands'} "
          f"({', '.join(k for k, ok in v.items() if k != 'repoint' and not ok) or 'all gates pass'})")
        p("")
        p("**Add-one family (base + family; Δ vs the NF1.1-baseline arm — isolated lift):**")
        p("")
        ao = pd.DataFrame(r["family_add_one"])
        if not ao.empty:
            ao["mean_top"] = ao["mean_top"].map(_fmt)
            ao["delta_vs_baseline"] = ao["delta_vs_baseline"].map(lambda x: _fmt(x, sign=True))
            p(ao.to_markdown(index=False))
        p("")
        p("**Drop-one group on the winner (negative Δ = the group carries signal):**")
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
    p("- honest frame: NF1.2 is market-BLIND — it gates against the market-blind baseline (the "
      "fade board). A QB/RB win would additionally have to beat the NF1.3 market-aware board to "
      "change the served product there; WR/TE + fades are the honest win condition.")
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
    ap = argparse.ArgumentParser(description="NF1.2 — projection-refinement family bake-off")
    ap.add_argument("--mode", required=True, choices=["bakeoff", "grade", "build"])
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--base-from", type=int, default=2017)
    ap.add_argument("--base-to", type=int, default=2024)
    ap.add_argument("--projection-season", type=int, default=None)
    ap.add_argument("--n-trials", type=int, default=40)
    ap.add_argument("--selection", default=None,
                    help="grade/build: path to the bake-off json (default ablation_results/nf1_2_refinements.json)")
    ap.add_argument("--board", choices=["gated", "beats-null"], default="beats-null")
    ap.add_argument("--seasons", default=None, help="grade: comma seasons (default 2019-2024)")
    ap.add_argument("--no-cache", action="store_true", help="bakeoff: rebuild the feature pool cache")
    ap.add_argument("--smoke", action="store_true", help="tiny subset; writes *_smoke reports")
    ap.add_argument("--s3", action="store_true", help="build: land the projection to S3")
    ap.add_argument("--lake-root", default=None)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    suffix = "_smoke" if args.smoke else ""
    sel_path = Path(args.selection) if args.selection else (_REPORT_DIR / f"nf1_2_refinements{suffix}.json")
    con = _connect(args.duckdb)
    try:
        if args.mode == "bakeoff":
            bf, bt = (2019, 2022) if args.smoke else (args.base_from, args.base_to)
            n_trials = 2 if args.smoke else args.n_trials
            out = run_bakeoff(con, bf, bt, args.schema, n_trials, use_cache=not args.no_cache)
            (_REPORT_DIR / f"nf1_2_refinements{suffix}.json").write_text(
                json.dumps(out, indent=2, default=float))
            write_bakeoff_report(out, _REPORT_DIR / f"nf1_2_refinements{suffix}.md")
            for pos, r in out["positions"].items():
                if "winner" in r:
                    print(f"{pos}: winner={r['winner']['learner']} top ρ={r['winner']['mean_top']} "
                          f"(null {r['null']['mean_top']}, nf1.1-base {r['nf1_1_baseline']['mean_top']}) "
                          f"beats_null={r['beats_null']} PBO={r['pbo']} DSR={r['dsr']} "
                          f"repoint={r['verdict']['repoint']}")

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
            (_REPORT_DIR / f"nf1_2_vs_consensus_scorecard{suffix}.json").write_text(
                json.dumps(sc, indent=2, default=float))
            print(json.dumps(sc.get("aggregate", {}), indent=2, default=float))

        elif args.mode == "build":
            bakeoff = json.loads(sel_path.read_text())
            selections = load_selection(bakeoff, board=args.board)
            log.info("building board=%s selections=%s", args.board,
                     {p: s["learner"] for p, s in selections.items()})
            base_season = int(con.sql(
                f"select max(season) from {args.schema}.fct_player_week where played_flag").fetchone()[0])
            proj_season = args.projection_season or (base_season + 1)
            base_seasons = [b for b in range(args.base_from, base_season) if b + 1 < proj_season]
            inputs = load_inputs(con, sorted(set(base_seasons + [base_season])), args.schema)
            proj = build_season_projection(con, base_season, proj_season, args.schema, selections,
                                           inputs, base_from=args.base_from)
            log.info("NF1.2 %d: %d players (%d vets, %d rookies)", proj_season, len(proj),
                     int((~proj["is_rookie"]).sum()), int(proj["is_rookie"].sum()))
            _ART.mkdir(parents=True, exist_ok=True)
            proj.to_parquet(_ART / f"nf1_2_season_projections_{proj_season}.parquet", index=False)
            ranked = proj.copy()
            ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
            ranked.insert(1, "pos_rank", ranked.groupby("position").cumcount() + 1)
            ranked.to_csv(_ART / f"nf1_2_season_projections_{proj_season}_ranked.csv", index=False)
            if args.s3 or args.lake_root:
                from quant_sports_intel_models.football.nfl.ingest import s3io
                n = s3io.write_dataframe(proj.assign(season=int(proj_season)), sport="nfl",
                                         source="nf1_2_season_projections", season=int(proj_season),
                                         tier="fantasy/derived", local_root=args.lake_root)
                log.info("landed %d rows → nfl/fantasy/derived/nf1_2_season_projections season=%d",
                         n, proj_season)
            print(f"NF1.2 {proj_season} built (board={args.board}); top: "
                  + ", ".join(proj.head(5)["player_name"].tolist()))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
