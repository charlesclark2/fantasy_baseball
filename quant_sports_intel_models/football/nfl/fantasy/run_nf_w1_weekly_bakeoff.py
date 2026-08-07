"""run_nf_w1_weekly_bakeoff.py — NF-W1 §0.5 bake-off: the lean weekly per-game distributional
fantasy projection vs the honest degenerate weekly baseline (season ÷ games + matchup).

Everything decidable-in-advance lives as a CONSTANT in `weekly_projection.py` (the pure module) and
this runner READS it — the NF-D16 discipline. The narrative pre-registration is committed at
`ablation_results/nf_w1_preregistration.md` BEFORE the full run.

PIPELINE: certified NF-W0 frame (rebuilt in memory, label pinned `v1.nflverse.stats_player_week`)
→ `assemble_matrix` (feature engineering + provenance + THE NF-W0a PIT GATE — `assert_point_in_time`
runs per target week, first real caller of the guard) → 8 purged expanding-window half-season folds
over weeks → 4 real arms + 2 foils + 6 diagnostic anchors through ONE reducer → per-position CRPS
selection → NF17/NF18 PBO + M14 DSR/FDR + cv_power fold-consistency → ship-or-null per position.

⚠️ BYE ROWS: excluded from scoring by pre-registration (a deterministic schedule-known zero; the
serving identity emits 0 exactly). Including them adds identical zero-CRPS rows to EVERY arm that
emits the identity — it rescales every mean by the same (n / (n + n_bye)) and cannot reorder arms,
so the with-bye sensitivity is an analytic note, not a computation.

RUN (LAPTOP — reads the S3 NFL lake read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w1_weekly_bakeoff
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w1_weekly_bakeoff --smoke
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
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_w0_audit import (  # noqa: E402
    _resolve_snap_identities,
)

log = logging.getLogger("nfl.fantasy.nf_w1")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_ARTIFACTS = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
SEASONS = (2016, 2025)


# ── Lake reads (widened for components + opponent matchup; snaps via the NF-W0b ladder) ─────────
def load_sources_w1(seasons: tuple[int, int]) -> dict[str, pd.DataFrame]:
    from quant_sports_intel_models.football.nfl.ingest.query_lake import q, delta
    lo, hi = seasons
    yrs = f"between {lo} and {hi}"
    rosters = q(f"""
        select season, week, team, position, status, gsis_id
        from {delta('weekly_rosters')}
        where season {yrs} and game_type = 'REG' and gsis_id is not null
    """)
    identity = q(f"""
        select season, week, team, position, gsis_id,
               coalesce(full_name, concat(first_name, ' ', last_name)) as full_name,
               espn_id, sportradar_id, yahoo_id, rotowire_id, pff_id, pfr_id,
               fantasy_data_id, sleeper_id, esb_id, gsis_it_id, smart_id
        from {delta('weekly_rosters')}
        where gsis_id is not null
    """)
    schedule = q(f"""
        select season, week, home_team, away_team, gameday, div_game
        from {delta('schedules')}
        where season {yrs} and game_type = 'REG'
    """)
    stats = q(f"""
        select season, week, player_id, position, team, opponent_team,
               fantasy_points_ppr, carries, targets, attempts, receptions,
               passing_yards, passing_tds, passing_interceptions,
               rushing_yards, rushing_tds, receiving_yards, receiving_tds
        from {delta('stats_player_week')}
        where season {yrs} and season_type = 'REG'
    """)
    snaps_raw = q(f"""
        select season, week, team, position, player, pfr_player_id, offense_snaps, offense_pct
        from {delta('snap_counts')}
        where season {yrs} and game_type = 'REG'
    """)
    snaps = _resolve_snap_identities(snaps_raw, identity)
    return {"rosters": rosters, "schedule": schedule, "stats": stats, "snaps": snaps}


def build_matrix(seasons: tuple[int, int], *, rebuild_cache: bool = False) -> tuple[pd.DataFrame, dict]:
    """Assemble (or reload) the modeled matrix. ⭐ THE PIT GATE RUNS ON EVERY BUILD, cache hit or
    not — a cached matrix must re-prove its point-in-time cleanliness, or the guard is invoked
    only on the day the cache was written (the NF-C0e wired-≠-invoked shape, cache edition)."""
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    key = WP.matrix_key(seasons)
    cache = _ARTIFACTS / f"nf_w1_weekly_matrix_{key}.parquet"
    if cache.exists() and not rebuild_cache:
        log.info("matrix cache HIT %s — re-running the PIT gate over it", cache.name)
        feat = pd.read_parquet(cache)
        audit = WP.run_pit_gate(feat)
        feat = feat.loc[audit.pop("kept_index")].reset_index(drop=True)
        return feat, audit

    src = load_sources_w1(seasons)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    spine = WF.build_spine(src["rosters"], src["schedule"])
    frame = WF.attach_labels(
        spine, src["stats"],
        label_version=WP.LABEL_VERSION,
        label_as_of_timestamp=stamp,
        scoring_system_id=WP.SCORING_SYSTEM_ID,
        snaps=src["snaps"],
    )
    log.info("certified frame: %d rows (%d zeros retained)", len(frame), int(frame["is_zero"].sum()))
    modeled, audit = WP.assemble_matrix(frame, src["stats"], src["snaps"], src["schedule"])
    modeled.to_parquet(cache, index=False)
    log.info("matrix cached → %s (%d rows; PIT: %d weeks / %d records checked, %d rows dropped)",
             cache.name, len(modeled), audit["weeks_checked"], audit["records_checked"],
             audit["rows_dropped"])
    return modeled, audit


# ── One reducer for candidates AND anchors ──────────────────────────────────────────────────────
def score_qmat(qmat: np.ndarray, test: pd.DataFrame) -> dict:
    """Per-position mean CRPS (+ report-only MAE via the median) — candidates and anchors go
    through THIS function and nothing else, so they demonstrably answer the same question."""
    y = test["fantasy_points"].to_numpy(dtype=float)
    crps = WP.crps_from_quantiles(qmat, y)
    med = np.sort(qmat, axis=1)[:, len(WP.Q_LEVELS) // 2]
    out: dict = {"pooled": float(np.mean(crps)), "mae_pooled": float(np.mean(np.abs(y - med)))}
    for p in WP.POSITIONS:
        sel = (test["position"] == p).to_numpy()
        out[p] = float(np.mean(crps[sel])) if sel.any() else float("nan")
        out[f"mae_{p}"] = float(np.mean(np.abs(y[sel] - med[sel]))) if sel.any() else float("nan")
    return out


def run_fold(fold: WP.Fold, feat: pd.DataFrame, features: list[str]) -> dict:
    """Fit every arm + anchor for one fold. Foil points/banks are computed once and shared."""
    train = feat.loc[fold.train_idx]
    test = feat.loc[fold.test_idx]
    t0 = time.time()

    pos_mean = WP.train_pos_mean_ppg(train)
    foil_tr_point = WP.foil_point(train, pos_mean, matchup=False)
    bank = WP.residual_bank(train["fantasy_points"].to_numpy(float), foil_tr_point,
                            train["position"].to_numpy())
    foil_te_flat = WP.foil_point(test, pos_mean, matchup=False)
    foil_te_matchup = WP.foil_point(test, pos_mean, matchup=True)
    te_pos = test["position"].to_numpy()

    qmats: dict[str, np.ndarray] = {
        "foil_flat": WP.apply_bank(foil_te_flat, te_pos, bank),
        "foil_matchup": WP.apply_bank(foil_te_matchup, te_pos, bank),
        "lgbm_quantile": WP.fit_lgbm_quantile(train, test, features),
        "lgbm_hurdle": WP.fit_lgbm_hurdle(train, test, features),
        "enet_residual": WP.fit_enet_residual(train, test, features),
        "knn_quantile": WP.fit_knn_quantile(train, test, features),
        # anchors — diagnostic, never trials
        "nihilist_zero": WP.anchor_nihilist(test),
        "pos_marginal": WP.anchor_pos_marginal(train, test),
        "oracle_marginal": WP.anchor_oracle_marginal(test),
        "permuted_within": WP.fit_lgbm_quantile(
            train, test, features, y_train=WP.permute_within_pos_week(train)),
        "zero_width": WP.anchor_zero_width(foil_te_flat),
        "max_width": WP.anchor_max_width(foil_te_flat, te_pos, bank),
    }
    scores = {label: score_qmat(m, test) for label, m in qmats.items()}
    coverage = {label: {p: WP.interval_coverage(
        qmats[label][(test["position"] == p).to_numpy()],
        test.loc[test["position"] == p, "fantasy_points"].to_numpy(dtype=float))
        for p in WP.POSITIONS}
        for label in (*WP.REAL_ARMS, *WP.FOILS)}
    log.info("fold %s scored in %.1fs (train %d / test %d)",
             fold.label, time.time() - t0, len(train), len(test))
    return {"label": fold.label, "scores": scores, "coverage": coverage,
            "n_train": int(len(train)), "n_test": int(len(test))}


# ── Selection + deflation per position ──────────────────────────────────────────────────────────
def select_position(pos: str, fold_results: list[dict], n_folds: int) -> dict:
    """Per-position verdict: winner among REAL_ARMS on mean fold CRPS, gated per pre-registration."""
    crps = pd.DataFrame({
        fr["label"]: {label: fr["scores"][label][pos] for label in fr["scores"]}
        for fr in fold_results
    }).T  # rows = folds, cols = labels

    mean_crps = crps.mean(axis=0)
    winner = str(mean_crps[list(WP.REAL_ARMS)].idxmin())
    best_foil = str(mean_crps[list(WP.FOILS)].idxmin())
    deltas = (crps[best_foil] - crps[winner]).to_numpy(dtype=float)  # >0 = winner better
    beats_foil = bool(np.nanmean(deltas) > 0)
    fold_wins = int((deltas > 0).sum())
    clause = cv_power.fold_consistency_clause(n_folds)

    eligible = list(WP.REAL_ARMS) + list(WP.FOILS)
    defl = NF18.deflate(crps[eligible], subset=eligible)

    trial_srs = []
    for arm in WP.REAL_ARMS:
        d = (crps[best_foil] - crps[arm]).to_numpy(dtype=float)
        sd = float(np.nanstd(d, ddof=1))
        trial_srs.append(float(np.nanmean(d)) / sd if sd > 1e-12 else 0.0)
    dsr = M14.deflated_sharpe(deltas, np.asarray(trial_srs))
    pval = M14.onesided_paired_pvalue(deltas)

    anchor_checks = {
        "nihilist_loses": bool(mean_crps["nihilist_zero"] > mean_crps[winner]),
        "pos_marginal_loses": bool(mean_crps["pos_marginal"] > mean_crps[winner]),
        "permuted_loses": bool(mean_crps["permuted_within"] > mean_crps[winner]),
        "zero_width_loses": bool(mean_crps["zero_width"] > mean_crps[winner]),
        "max_width_loses": bool(mean_crps["max_width"] > mean_crps[winner]),
        # reported, never a veto — a conditional arm may legitimately beat the marginal peeker
        "oracle_marginal_beaten_by_winner": bool(mean_crps["oracle_marginal"] > mean_crps[winner]),
    }

    # winner's pooled-over-folds coverage (floor discipline — NF1.8)
    covs = [fr["coverage"][winner][pos] for fr in fold_results]
    n_total = sum(c["n"] for c in covs)
    cov_pooled = (sum(c["coverage"] * c["n"] for c in covs) / n_total) if n_total else float("nan")
    se = float(np.sqrt(WP.COVERAGE_FLOOR * (1 - WP.COVERAGE_FLOOR) / n_total)) if n_total else float("nan")
    coverage = {
        "winner_coverage_80": round(cov_pooled, 4), "n_rows": n_total, "binomial_se": round(se, 4),
        "blocking_shortfall": bool(n_total and (0.80 - cov_pooled) > WP.COVERAGE_BLOCK_SE * se),
    }

    sd = float(np.nanstd(deltas, ddof=1))
    observed_sr = float(np.nanmean(deltas)) / sd if sd > 1e-12 else None
    var_trials = float(np.var(np.asarray(trial_srs), ddof=1)) if len(trial_srs) > 1 else None

    return {
        "winner": winner, "best_foil": best_foil,
        "mean_crps": {k: round(float(v), 4) for k, v in mean_crps.items()},
        "mean_mae_report_only": {
            label: round(float(np.mean([fr["scores"][label][f"mae_{pos}"] for fr in fold_results])), 4)
            for label in (winner, best_foil, "nihilist_zero")
        },
        "deltas_by_fold": [round(float(d), 4) for d in deltas],
        "beats_foil": beats_foil, "fold_wins": fold_wins,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable,
                        "passes": clause.passes(fold_wins)},
        "pbo": defl.get("pbo"), "os_gap_pct": defl.get("os_gap_pct"),
        "contender_spread_pct": defl.get("contender_spread_pct"), "flips": defl.get("flips"),
        "dsr": dsr, "p_one_sided": pval,
        "trial_srs": [round(t, 3) for t in trial_srs],
        "observed_sr": None if observed_sr is None else round(observed_sr, 3),
        "var_trials_sr": None if var_trials is None else round(var_trials, 5),
        "anchors": anchor_checks, "coverage": coverage,
    }


def position_gate(sel: dict, fdr_pass: bool) -> dict:
    checks = {
        "beats_foil": sel["beats_foil"],
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < WP.PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= WP.DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "degenerates_lose": bool(sel["anchors"]["nihilist_loses"]
                                 and sel["anchors"]["pos_marginal_loses"]
                                 and sel["anchors"]["zero_width_loses"]
                                 and sel["anchors"]["max_width_loses"]),
        "permutation_beaten": bool(sel["anchors"]["permuted_loses"]),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
    }
    return {"checks": checks, "ship": all(checks.values())}


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    p("# NF-W1 — the lean weekly per-game distributional fantasy projection (§0.5 bake-off)")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} half-season blocks over "
      f"weeks ({out['fold_labels'][0]}…{out['fold_labels'][-1]}) · **modeled rows:** "
      f"{out['n_rows']} (byes excluded by pre-registration) · **label:** "
      f"`{out['evaluation_label_version']}` / `{out['scoring_system_id']}`")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, no CLV/ROI claim. "
      "Selection metric is CRPS (`crps_q39`); MAE is reported and NEVER selects — it is inverted "
      "at QB/TE on this frame (conditional median 0.0, NF-W0 §2.3).")
    p("")
    p(f"**PIT gate (NF-W0a `assert_point_in_time` — first real caller):** "
      f"{out['pit_audit']['weeks_checked']} weeks / {out['pit_audit']['records_checked']} records "
      f"checked; {out['pit_audit']['rows_dropped']} rows in "
      f"{len(out['pit_audit']['weeks_dropped'])} weeks dropped fail-closed "
      f"(the un-provable-window class).")
    p("")
    p("## Per-position verdicts")
    p("")
    for pos in WP.POSITIONS:
        sel, gate = out["positions"][pos], out["gates"][pos]
        verdict = "SHIP" if gate["ship"] else f"NULL ({out['null_states'].get(pos, {}).get('state', 'n/a')})"
        p(f"### {pos} — **{verdict}**")
        p("")
        rows = [{"arm": k, "mean_crps": v} for k, v in sel["mean_crps"].items()]
        p(pd.DataFrame(rows).sort_values("mean_crps").to_markdown(index=False, floatfmt=".4f"))
        p("")
        p(f"- winner `{sel['winner']}` vs best foil `{sel['best_foil']}`: mean lift "
          f"{np.mean(sel['deltas_by_fold']):+.4f} CRPS, fold wins {sel['fold_wins']}/{out['n_folds']} "
          f"(clause requires {sel['fold_clause']['required']}) · PBO {sel['pbo']} · DSR {sel['dsr']} "
          f"· p {sel['p_one_sided']} · FDR pass {gate['checks']['fdr_ok']}")
        p(f"- anchors: {sel['anchors']} · coverage(80) {sel['coverage']}")
        p(f"- MAE (report-only): {sel['mean_mae_report_only']}")
        p("")
    p("## Gate detail")
    p("")
    p("```json")
    p(json.dumps(out["gates"], indent=2, default=str))
    p("```")
    p("")
    p("## Null-state classification (failing positions)")
    p("")
    p("```json")
    p(json.dumps(out["null_states"], indent=2, default=str))
    p("```")
    p("")
    p("## With-bye sensitivity (analytic)")
    p("")
    p("A bye row's honest projection is the identity point-mass at 0 (CRPS 0 for every arm that "
      "emits it, including the nihilist). Including byes therefore multiplies every arm's mean "
      "CRPS by the same factor n/(n+n_bye) and CANNOT reorder arms — which is why the scoring "
      "population excludes them.")
    p("")
    path.write_text("\n".join(a))


# ── Runner ──────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:  # noqa: C901 — orchestration
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="NF-W1 weekly per-game distributional bake-off")
    ap.add_argument("--smoke", action="store_true",
                    help="2 folds, artifacts suffixed _smoke — never mistakable for the real search")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args(argv)

    feat, pit_audit = build_matrix(SEASONS, rebuild_cache=args.rebuild_cache)
    features = list(WP.FEATURES)
    folds = WP.build_folds(feat)
    if args.smoke:
        folds = folds[-2:]
    n_folds = len(folds)
    log.info("running %d folds × %d arms/anchors over %d rows",
             n_folds, len(WP.REAL_ARMS) + len(WP.FOILS) + len(WP.ANCHORS), len(feat))

    fold_results = [run_fold(fold, feat, features) for fold in folds]

    positions = {pos: select_position(pos, fold_results, n_folds) for pos in WP.POSITIONS}
    pvals = {pos: positions[pos]["p_one_sided"] for pos in WP.POSITIONS}
    fdr = M14.bh_fdr(pvals, q=WP.FDR_Q)
    gates = {pos: position_gate(positions[pos], fdr[pos]) for pos in WP.POSITIONS}

    null_states: dict[str, dict] = {}
    for pos in WP.POSITIONS:
        if gates[pos]["ship"]:
            continue
        sel = positions[pos]
        v = cv_power.classify_null(
            metric=f"nf_w1_weekly_crps_{pos}", n_folds=n_folds, n_arms=len(WP.REAL_ARMS),
            beats_foil=sel["beats_foil"], observed_sr=sel["observed_sr"],
            var_trials_sr=sel["var_trials_sr"], fold_wins=sel["fold_wins"],
            p_one_sided=sel["p_one_sided"], bh_cutoff=WP.FDR_Q,
        )
        null_states[pos] = {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger}

    # component-head + ROS demonstration on the final fold (advisory raw lines, never gated)
    last = folds[-1]
    comp = WP.fit_component_head(feat.loc[last.train_idx], feat.loc[last.test_idx], features)
    demo_q = WP.fit_lgbm_quantile(feat.loc[last.train_idx], feat.loc[last.test_idx], features)
    test_df = feat.loc[last.test_idx]
    q16 = np.sort(demo_q, axis=1)[:, int(np.argmin(np.abs(WP.Q_LEVELS - 0.15)))]
    q84 = np.sort(demo_q, axis=1)[:, int(np.argmin(np.abs(WP.Q_LEVELS - 0.85)))]
    weekly_demo = pd.DataFrame({
        "gsis_id": test_df["gsis_id"].to_numpy(), "position": test_df["position"].to_numpy(),
        "week": test_df["week"].to_numpy(), "mean": demo_q.mean(axis=1),
        "q16": q16, "q84": q84,
    })
    ros_demo = WP.ros_projection(weekly_demo)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": "NF-W1", "smoke": bool(args.smoke),
        "evaluation_label_version": WP.LABEL_VERSION,
        "scoring_system_id": WP.SCORING_SYSTEM_ID,
        "selection_metric": WP.SELECTION_METRIC,
        "n_rows": int(len(feat)), "n_folds": n_folds,
        "fold_labels": [f.label for f in folds],
        "pit_audit": pit_audit,
        "preregistration": {
            "real_arms": list(WP.REAL_ARMS), "foils": list(WP.FOILS),
            "anchors": list(WP.ANCHORS), "non_shippable": list(WP.NON_SHIPPABLE),
            "test_blocks": [list(t) for t in WP.TEST_BLOCKS], "purge_weeks": WP.PURGE_WEEKS,
            "pbo_max": WP.PBO_MAX, "dsr_min": WP.DSR_MIN, "fdr_q": WP.FDR_Q,
            "coverage_floor": WP.COVERAGE_FLOOR, "eb_kappa": WP.EB_KAPPA,
            "dvp_clip": list(WP.DVP_CLIP), "features": list(WP.FEATURES),
            "unused_allowed_families": list(WP.UNUSED_ALLOWED_FAMILIES),
            "era_forbidden_tokens": list(WP.ERA_FORBIDDEN_TOKENS),
        },
        "positions": positions, "gates": gates, "fdr": fdr, "null_states": null_states,
        "component_head_sample": comp.head(8).to_dict(orient="records"),
        "ros_demo_sample": ros_demo.sort_values("ros_mean", ascending=False).head(8)
                                   .to_dict(orient="records"),
        "fold_results": [{k: fr[k] for k in ("label", "scores", "n_train", "n_test")}
                         for fr in fold_results],
    }
    verdicts = {pos: ("SHIP" if gates[pos]["ship"] else null_states.get(pos, {}).get("state", "NULL"))
                for pos in WP.POSITIONS}
    out["verdict"] = verdicts
    out["headline"] = " · ".join(f"{pos}:{v}" for pos, v in verdicts.items())

    suffix = "_smoke" if args.smoke else ""
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"nf_w1_weekly_bakeoff{suffix}.json").write_text(
        json.dumps(out, indent=2, default=float))
    if not args.no_report:
        write_report(out, _REPORT_DIR / f"nf_w1_weekly_bakeoff{suffix}.md")
    log.info("verdict: %s", out["headline"])
    print(json.dumps({"verdict": verdicts, "headline": out["headline"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
