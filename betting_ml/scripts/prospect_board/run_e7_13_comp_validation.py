"""run_e7_13_comp_validation.py — MLB Edge-E7.13 PHASE 2 runner: score the pre-registered arm
field, apply the deflated gates, and write the verdict.

Reads ONE local parquet (E7.8's cohort) — no S3, no Snowflake, no dbt. Runs in well under a minute.

    uv run python -m betting_ml.scripts.prospect_board.run_e7_13_comp_validation

Writes `ablation_results/e7_13_artifacts/e7_13_comp_validation.{json,md}`.

TWO SEPARATE QUESTIONS ARE ANSWERED HERE, AND THEY HAVE DIFFERENT ANSWERS
------------------------------------------------------------------------
1. **The PROJECTION question** (`_score_type`) — may a comp-derived term enter the projection?
   Graded on CRPS, because the target is 47% exact zeros. Verdict: display-only / blend-eligible.
2. **The ORDERING question** (`_ordering_study`) — may a comp term touch the board's RANKING?
   Graded on Spearman rank-IC, because a draft board is purely ordinal and CRPS cannot see an
   ordering. This is the question that licensed `prospect_comps.attach_comp_ranking`.

⚠️ Read `comp_validation`'s module docstring on the FOLD CEILING before quoting any number here.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.prospect_board import comp_validation as cv  # noqa: E402
from betting_ml.scripts.prospect_board.prospect_comps import build_pool, validate_pool  # noqa: E402
from betting_ml.utils.design_block import (  # noqa: E402
    design_block_from_comp_validation_report,
    insert_design_block,
)

log = logging.getLogger("e7_13.validate")

_ABL = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
DEFAULT_POOL = _ABL / "e7_8_artifacts/fv_translation_cohort.parquet"
DEFAULT_OUT = _ABL / "e7_13_artifacts"

#: The incumbent every comp arm must beat to earn a place in the projection.
INCUMBENT = "fv_bucket"
#: Pre-registered flatness constraint (max decile deviation of the randomized PIT).
PIT_MAX_DECILE_DEV = 0.05


def _score_type(cohort: pd.DataFrame, player_type: str, *, strict: bool, seed: int) -> dict:
    pool = build_pool(cohort, player_type=player_type)
    pool_report = validate_pool(pool)
    plan = cv.fold_plan(pool, strict=strict)
    if not plan:
        return {"player_type": player_type, "pool": pool_report, "folds": [],
                "verdict": "NO_USABLE_FOLDS"}

    rng = np.random.default_rng(seed)
    per_row: dict[str, list[pd.DataFrame]] = {a.name: [] for a in cv.ARM_FIELD}

    for fold in plan:
        q = pool.loc[pool["board_season"] == fold["query_season"]].reset_index(drop=True)
        tr = pool.loc[pool["board_season"].isin(fold["train_seasons"])].reset_index(drop=True)
        log.info("%s fold %s: %d query / %d train", player_type, fold["query_season"],
                 len(q), len(tr))
        y = q["fantasy_points"].to_numpy(float)
        for arm in cv.ARM_FIELD:
            samples, weights = cv.score_arm(arm, tr, q, player_type=player_type, seed=seed)
            rows = []
            for i in range(len(q)):
                s, w = samples[i], weights[i]
                if s.size == 0:
                    rows.append({"crps": np.nan, "pit": np.nan, "lo": np.nan, "hi": np.nan})
                    continue
                ww = w / w.sum()
                order = np.argsort(s)
                cwt = np.cumsum(ww[order])
                lo = (float(s[order][np.searchsorted(cwt, 0.10)]) if cwt[-1] >= 0.10
                      else float(s.min()))
                hi_i = min(int(np.searchsorted(cwt, 0.90)), len(s) - 1)
                rows.append({"crps": cv.crps_sample(s, w, y[i]),
                             "pit": cv.randomized_pit(s, w, y[i], rng),
                             "lo": lo, "hi": float(s[order][hi_i])})
            df = pd.DataFrame(rows)
            df["y"] = y
            df["fold"] = fold["query_season"]
            df["cluster"] = q["comp_key"].to_numpy()
            per_row[arm.name].append(df)

    scored = {k: pd.concat(v, ignore_index=True) for k, v in per_row.items()}

    # ── evaluate every arm on the SAME rows: the intersection where every CONTENDER produced a
    # distribution. A comparison over different row sets is not a comparison.
    contenders = [a.name for a in cv.ARM_FIELD if a.selectable]
    usable = np.ones(len(scored[contenders[0]]), dtype=bool)
    for name in contenders + ["random_k15", "oracle_k15"]:
        usable &= np.isfinite(scored[name]["crps"].to_numpy(float))
    n_usable, n_total = int(usable.sum()), int(len(usable))
    log.info("%s: %d/%d rows scoreable by every contender", player_type, n_usable, n_total)

    results, fold_matrix = {}, []
    base = scored[contenders[0]].loc[usable]
    for arm in cv.ARM_FIELD:
        d = scored[arm.name].loc[usable]
        by_fold = d.groupby("fold")["crps"].mean()
        results[arm.name] = {
            "kind": arm.kind, "selectable": arm.selectable,
            "crps": float(d["crps"].mean()),
            "crps_by_fold": {int(k): round(float(v), 3) for k, v in by_fold.items()},
            "pit_max_decile_dev": round(cv.pit_max_decile_deviation(d["pit"].to_numpy(float)), 4),
            "coverage_p10_p90": round(cv.interval_coverage(d["lo"], d["hi"], d["y"]), 4),
        }
        fold_matrix.append(by_fold.reindex(sorted(base["fold"].unique())).to_numpy(float))

    arm_names = [a.name for a in cv.ARM_FIELD]
    fm = np.vstack(fold_matrix).T                            # (n_folds, n_arms)

    # ── two-sided anchors, read every run ────────────────────────────────────────────────────
    best_contender = min(contenders, key=lambda n: results[n]["crps"])
    oracle_c = results["oracle_k15"]["crps"]
    anchors = {
        "oracle_is_the_floor": bool(oracle_c <= min(results[n]["crps"] for n in contenders)),
        "oracle_crps": round(oracle_c, 3),
        "all_zero_loses": bool(results["all_zero"]["crps"] > results[best_contender]["crps"]),
        "all_zero_crps": round(results["all_zero"]["crps"], 3),
        "marginal_loses": bool(results["marginal"]["crps"] > results[best_contender]["crps"]),
        "marginal_crps": round(results["marginal"]["crps"], 3),
        "placebo_loses": bool(results["random_k15"]["crps"] > results["comp_gower_k15"]["crps"]),
        "placebo_crps": round(results["random_k15"]["crps"], 3),
    }
    anchors["all_pass"] = all(anchors[k] for k in
                              ("oracle_is_the_floor", "all_zero_loses", "marginal_loses",
                               "placebo_loses"))

    # ── the matched-foil paired deltas (the attribution, not the leaderboard) ────────────────
    pairs = {
        # ⭐ THE SELECTION TEST. It must be the arm the selection ACTUALLY PICKED, not the shipped
        # default — testing a different arm than the one you would ship is how a leaderboard rank
        # gets quietly substituted for an attributable result (NF-D10 (g)).
        "selected_vs_incumbent": (best_contender, INCUMBENT),
        "comp_vs_incumbent": ("comp_gower_k15", INCUMBENT),
        "blend_vs_incumbent": ("blend_comp_fv", INCUMBENT),
        "blend_vs_comp": ("blend_comp_fv", "comp_gower_k15"),
        "fv_channel": ("comp_gower_k15", "comp_no_fv_k15"),
        "structural_channel": ("comp_gower_k15", "comp_components_only_k15"),
        "similarity_channel": ("comp_gower_k15", "random_k15"),
        "kernel_channel": ("comp_gower_k15", "comp_gower_k15_simweighted"),
    }
    paired = {}
    for label, (a, b) in pairs.items():
        diff = (scored[a].loc[usable, "crps"].to_numpy(float)
                - scored[b].loc[usable, "crps"].to_numpy(float))
        r = cv.cluster_bootstrap_pvalue(diff, base["cluster"].to_numpy(), seed=seed)
        paired[label] = {"arm": a, "foil": b,
                         "mean_crps_delta": round(r["mean"], 3),
                         "p_value": round(r["p_value"], 4),
                         "ci95": [round(r["ci_lo"], 3), round(r["ci_hi"], 3)],
                         "n_clusters": r["n_clusters"],
                         "arm_better": bool(r["mean"] < 0)}

    # ── deflation ────────────────────────────────────────────────────────────────────────────
    c_idx = [arm_names.index(n) for n in contenders]
    pbo_all = cv.pbo_cscv(fm)
    pbo_cont = cv.pbo_cscv(fm[:, c_idx])
    for p in (pbo_all, pbo_cont):
        if p.get("flip_distribution"):
            names = arm_names if p is pbo_all else contenders
            p["flip_distribution"] = {names[int(k)]: v for k, v in p["flip_distribution"].items()}

    skill = -(scored[best_contender].loc[usable, "crps"].to_numpy(float)
              - scored[INCUMBENT].loc[usable, "crps"].to_numpy(float))
    # ⚠️ DSR's effective n is CLUSTERS, not rows. A player sits on several boards, so his rows are
    # not independent draws; feeding the row count would inflate DSR by ~sqrt(rows/clusters) and
    # manufacture a pass. The clustered bootstrap below is the primary inference either way.
    n_clusters = int(pd.Series(base["cluster"].to_numpy()).nunique())
    deflation = {
        "pbo_whole_field": pbo_all,
        "pbo_contender_set": pbo_cont,
        "dsr_n_obs_used": n_clusters,
        "dsr_n_rows": n_usable,
        "dsr_whole_field": round(cv.deflated_sharpe(skill, len(arm_names), n_clusters), 4),
        "dsr_contender_set": round(cv.deflated_sharpe(skill, len(contenders), n_clusters), 4),
        "contender_spread_pct": round(
            100 * (max(results[n]["crps"] for n in contenders)
                   - min(results[n]["crps"] for n in contenders))
            / max(min(results[n]["crps"] for n in contenders), 1e-9), 2),
        "whole_field_spread_pct": round(
            100 * (max(r["crps"] for r in results.values())
                   - min(r["crps"] for r in results.values()))
            / max(min(r["crps"] for r in results.values()), 1e-9), 2),
    }
    fdr_family = ("selected_vs_incumbent", "comp_vs_incumbent", "blend_vs_incumbent",
                  "fv_channel", "structural_channel", "similarity_channel",
                  "kernel_channel")
    fdr = cv.bh_fdr([paired[k]["p_value"] for k in fdr_family])
    fdr["family"] = list(fdr_family)
    deflation["bh_fdr"] = fdr

    # ── verdict ──────────────────────────────────────────────────────────────────────────────
    # 🚨 An FDR REJECTION IS NOT A PASS — it only says the difference is real, and a difference can
    # be real and in the WRONG DIRECTION. The pitcher side is exactly that: `comp_vs_incumbent` is
    # rejected while the arm is CRPS-WORSE. The gate must require BOTH.
    sel = paired["selected_vs_incumbent"]
    pit_ok = results[best_contender]["pit_max_decile_dev"] <= PIT_MAX_DECILE_DEV
    gates = {
        "anchors_pass": anchors["all_pass"],
        "beats_incumbent": bool(sel["arm_better"]),
        "pbo_lt_0_2": bool((pbo_cont.get("pbo") is not None) and pbo_cont["pbo"] < 0.2),
        "dsr_contender_ge_0_95": bool(np.isfinite(deflation["dsr_contender_set"])
                                      and deflation["dsr_contender_set"] >= 0.95),
        "pit_flat": bool(pit_ok),
        "fdr_survives": bool(sel["arm_better"] and fdr["reject"][0]),
    }
    blend_ok = all(gates.values())
    return {
        "player_type": player_type,
        "pool": pool_report,
        "strict_maturity": strict,
        "folds": plan,
        "n_rows_scored": n_usable,
        "n_rows_total": n_total,
        "arms": results,
        "best_contender": best_contender,
        "anchors": anchors,
        "paired": paired,
        "deflation": deflation,
        "gates": gates,
        # ⚖️ Passing every gate earns BLEND-ELIGIBLE, not "wire it in". The gates were cleared on a
        # backtest that CANNOT be made strictly leakage-clean at this archive depth (one matured
        # fold), so the relative result is trustworthy and the absolute level is not. That is the
        # E7.12-S6 / NF-D15 (g″) shape: a real-but-not-cleanly-verifiable effect gets a SCHEDULED
        # re-validation, not a ship.
        "verdict": "BLEND_ELIGIBLE_NOT_WIRED" if blend_ok else "DISPLAY_ONLY",
        "blend_gates_all_pass": bool(blend_ok),
        "revalidation_trigger": "re-run when >=4 strictly-matured folds exist (2029; 2 in 2027)",
    }


def _ordering_study(cohort: pd.DataFrame, player_type: str, *, seed: int,
                    comp_arm: str = "comp_gower_k25", strict: bool = False) -> dict:
    """Does adding a comp term improve the ORDERING the board already produces?

    Separate from the CRPS study on purpose — see `comp_validation` §4. CRPS grades a distribution;
    a draft board is purely ordinal, and an arm can win CRPS on calibration while ordering no
    better. This is the statistic that licensed `prospect_comps.attach_comp_ranking`.

    `strict` selects the production maturity rule for the fold plan. It DEFAULTS TO FALSE so E7.13's
    own run reproduces byte-identically; E7.16 passes True because its cohort (the point-in-time MLB
    Pipeline archive) is deep enough to admit a strictly-matured plan, which E7.13's was not.
    """
    pool = build_pool(cohort, player_type=player_type)
    plan = cv.fold_plan(pool, strict=strict)
    arm = next(a for a in cv.ARM_FIELD if a.name == comp_arm)
    rng = np.random.default_rng(seed)

    per_form: dict[str, dict] = {}
    for form in cv.COMP_SCORE_FORMS:
        rows: list[pd.DataFrame] = []
        for fold in plan:
            q = pool.loc[pool["board_season"] == fold["query_season"]].reset_index(drop=True)
            tr = pool.loc[pool["board_season"].isin(fold["train_seasons"])].reset_index(drop=True)
            y = q["fantasy_points"].to_numpy(float)
            samples, weights = cv.score_arm(arm, tr, q, player_type=player_type, seed=seed)
            stat = np.full(len(q), np.nan)
            for i, (s, w) in enumerate(zip(samples, weights)):
                if s.size:
                    stat[i] = (float(np.average(s, weights=w)) if form == "comp_mean_fp"
                               else float(np.median(s)))
            base = cv.board_proxy_score(q, player_type)
            comp_pct = cv.pctile(pd.Series(stat, index=q.index), higher_is_better=True)
            scores = cv.ordering_scores(base, comp_pct, y, rng)
            df = pd.DataFrame(scores)
            df["y"], df["fold"], df["cluster"] = y, fold["query_season"], q["comp_key"].to_numpy()
            df["has_comp"] = np.isfinite(comp_pct.to_numpy(float))
            rows.append(df)
        d = pd.concat(rows, ignore_index=True)
        d = d.loc[d["board_proxy"].notna()].reset_index(drop=True)

        names = list(cv.ordering_arms(form))
        # ⭐⭐ MATCHED SUPPORT — every arm scored on the SAME rows (E7.16 fix, 2026-08-01).
        #
        # 🚨 THE DEFECT THIS REPLACES, AND WHY IT LOOKED LIKE A RESULT. `rank_ic` drops non-finite
        # rows, and `comp_only` is finite ONLY where the engine produced comps (~64–69% of the pool)
        # while `board_proxy` is finite nearly everywhere. So the two were scored on DIFFERENT
        # POPULATIONS — and the comped subpopulation is intrinsically easier to order, because
        # having comps means having a minor-league record. MEASURED on E7.16's strictly-matured
        # folds: `board_proxy` itself scores +0.4385 over the full population but **+0.5320 on the
        # comped rows alone** (batters). Read the naive way, `comp_only` beat the board by +0.1073;
        # on matched support the same number is **+0.0138** — 87% of the "win" was the population.
        # (Pitchers: +0.0991 → +0.0514.) This is the CRPS half's own `usable`-intersection rule —
        # "a comparison over different row sets is not a comparison" — which this half was missing.
        #
        # ⚖️ The BLEND arms (`board_plus_comp_w*`) were never affected: they fall back to the
        # board's score where a comp is absent, so they were always defined on the same rows as the
        # incumbent. That is why this fix CONFIRMS rather than overturns what E7.13 wired — on
        # matched support the w30 blend's edge over the incumbent GROWS (batters +0.0368 → +0.0436,
        # pitchers +0.0280 → +0.0535). What it corrects is the `comp_only` column, which E7.13
        # measured, reported, and deliberately did NOT wire.
        matched = np.ones(len(d), dtype=bool)
        for n in names:
            matched &= np.isfinite(d[n].to_numpy(float))
        dm = d.loc[matched].reset_index(drop=True)

        def _ic_frame(frame: pd.DataFrame) -> dict[str, float]:
            return {n: float(np.nanmean([cv.rank_ic(g[n].to_numpy(float), g["y"].to_numpy(float))
                                         for _, g in frame.groupby("fold")]))
                    for n in names}

        ic = _ic_frame(dm)
        ic_full = _ic_frame(d)          # reported as CONTEXT only — never selected on
        fm = np.vstack([[-cv.rank_ic(g[n].to_numpy(float), g["y"].to_numpy(float)) for n in names]
                        for _, g in dm.groupby("fold")])
        contenders = [n for n, k in cv.ordering_arms(form).items()
                      if k in ("contender", "incumbent")]
        best = max(contenders, key=lambda n: ic[n])
        pbo = cv.pbo_cscv(fm[:, [names.index(n) for n in contenders]])
        if pbo.get("flip_distribution"):
            pbo["flip_distribution"] = {contenders[int(k)]: v
                                        for k, v in pbo["flip_distribution"].items()}
        deltas = np.array([cv.rank_ic(g[best].to_numpy(float), g["y"].to_numpy(float))
                           - cv.rank_ic(g["board_proxy"].to_numpy(float), g["y"].to_numpy(float))
                           for _, g in dm.groupby("fold")])
        per_form[form] = {
            "rank_ic": {n: round(v, 4) for n, v in ic.items()},
            "rank_ic_unmatched_support": {n: round(v, 4) for n, v in ic_full.items()},
            "best_contender": best,
            "delta_vs_board_proxy": round(float(ic[best] - ic["board_proxy"]), 4),
            "delta_by_fold": [round(float(x), 4) for x in deltas],
            "folds_improved": int((deltas > 0).sum()),
            "n_folds": int(len(deltas)),
            "pbo_contender_set": pbo,
            "anchors": {
                "oracle_is_the_ceiling": bool(ic["oracle_order"] >= max(ic[n] for n in contenders)),
                "oracle_ic": round(ic["oracle_order"], 4),
                "placebo_loses": bool(ic["random_order"] < ic["board_proxy"]),
                "placebo_ic": round(ic["random_order"], 4),
            },
            "rows_with_comp": float(d["has_comp"].mean()),
            "n_rows": int(len(d)),
            "n_rows_matched_support": int(len(dm)),
            "matched_support_share": round(float(matched.mean()), 4),
        }
    return {"player_type": player_type, "comp_arm": comp_arm, "by_form": per_form}


def run(pool_path: Path, out_dir: Path, *, seed: int = 0, write: bool = True) -> dict:
    cohort = pd.read_parquet(pool_path)
    strict_plan = {t: cv.fold_plan(build_pool(cohort, player_type=t), strict=True)
                   for t in ("batter", "pitcher")}
    report = {
        "story": "E7.13 Phase 2 — does the comp distribution earn a place in the projection?",
        "target": "fantasy_points over the 3 seasons after the board (0 for a prospect who never "
                  "reached MLB)",
        "primary_metric": "CRPS (proper — the target is 47% exact zeros; MAE inverts here)",
        "constraint": f"randomized-PIT max decile deviation <= {PIT_MAX_DECILE_DEV}",
        "incumbent": INCUMBENT,
        "fold_ceiling": {
            "strictly_matured_folds": {t: len(p) for t, p in strict_plan.items()},
            "note": "A strictly-matured backtest (production's rule) admits at most ONE fold at "
                    "this archive depth — see comp_validation's FOLD CEILING section. The primary "
                    "run therefore relaxes the pool to 'any strictly earlier board season', which "
                    "grants historical queries hindsight. Every arm reads the identical pool, so "
                    "the HEAD-TO-HEAD stays fair while the LEVELS are optimistic. Re-opens "
                    "mechanically: 2 strictly-matured folds in 2027, 4 in 2029.",
        },
        "by_type": {},
    }
    for ptype in ("batter", "pitcher"):
        report["by_type"][ptype] = _score_type(cohort, ptype, strict=False, seed=seed)

    # ── the ORDERING study: may a comp term touch `blend_score`? (comp_validation §4) ──────────
    report["ordering"] = {t: _ordering_study(cohort, t, seed=seed) for t in ("batter", "pitcher")}

    verdicts = {t: r["verdict"] for t, r in report["by_type"].items()}
    report["verdict"] = ("BLEND_INTO_PROJECTION"
                         if all(v == "BLEND_INTO_PROJECTION" for v in verdicts.values())
                         else "DISPLAY_ONLY")
    report["verdict_by_type"] = verdicts

    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "e7_13_comp_validation.json").write_text(
            json.dumps(report, indent=2, default=str))
        db = design_block_from_comp_validation_report(
            report, fold_rule="forward, relaxed maturity (2 strictly-matured folds; the primary "
            "run relaxes to any strictly-earlier board season — see §Fold ceiling)",
            primary_contrast=report.get("constraint", "forward-outcome comparison"),
            use_fold_census=False)
        (out_dir / "e7_13_comp_validation.md").write_text(
            insert_design_block(_markdown(report), db))
    return report


def _markdown(rep: dict) -> str:
    a = [f"# E7.13 Phase 2 — comp-based projection: {rep['verdict']}", "",
         f"**Target** — {rep['target']}", f"**Primary metric** — {rep['primary_metric']}",
         f"**Constraint** — {rep['constraint']}", f"**Incumbent** — `{rep['incumbent']}`", "",
         "## ⚠️ Fold ceiling", "",
         f"Strictly-matured folds available: `{rep['fold_ceiling']['strictly_matured_folds']}`.", "",
         rep["fold_ceiling"]["note"], ""]
    for ptype, r in rep["by_type"].items():
        a += [f"## {ptype.title()}s — {r['verdict']}", "",
              f"Pool {r['pool']['n_pool']} rows, non-debut share **{r['pool']['bust_share']}** "
              f"(the busts are IN the pool). "
              f"{r['n_rows_scored']}/{r['n_rows_total']} rows scoreable by every contender.", "",
              "| arm | kind | CRPS | PIT max-decile-dev | p10–p90 coverage |",
              "|---|---|---|---|---|"]
        for name, m in sorted(r["arms"].items(), key=lambda kv: kv[1]["crps"]):
            tag = {"anchor": " 🎯 floor", "degenerate": " 🚧 ceiling",
                   "placebo": " 🎲 placebo"}.get(m["kind"], "")
            a.append(f"| `{name}`{tag} | {m['kind']} | {m['crps']:.2f} | "
                     f"{m['pit_max_decile_dev']:.4f} | {m['coverage_p10_p90']:.3f} |")
        a += ["", f"**Best contender** — `{r['best_contender']}`", "",
              "### Two-sided anchors", ""]
        for k, v in r["anchors"].items():
            a.append(f"* `{k}` = **{v}**")
        a += ["", "### Matched foils (paired ΔCRPS, negative = the arm is better)", "",
              "| comparison | arm | foil | ΔCRPS | 95% CI | p | arm better |",
              "|---|---|---|---|---|---|---|"]
        for k, v in r["paired"].items():
            a.append(f"| {k} | `{v['arm']}` | `{v['foil']}` | {v['mean_crps_delta']:+.2f} | "
                     f"[{v['ci95'][0]:+.2f}, {v['ci95'][1]:+.2f}] | {v['p_value']:.4f} | "
                     f"{v['arm_better']} |")
        d = r["deflation"]
        a += ["", "### Deflation", "",
              f"* PBO (contender set) — `{d['pbo_contender_set'].get('pbo')}` over "
              f"{d['pbo_contender_set'].get('n_splits')} splits; whole field "
              f"`{d['pbo_whole_field'].get('pbo')}`",
              f"* Performance degradation — "
              f"`{d['pbo_contender_set'].get('performance_degradation')}`",
              f"* Flip distribution — `{d['pbo_contender_set'].get('flip_distribution')}`",
              f"* DSR — contender set `{d['dsr_contender_set']}`, whole field "
              f"`{d['dsr_whole_field']}` (n = {d['dsr_n_obs_used']} CLUSTERS, not "
              f"{d['dsr_n_rows']} rows)",
              f"* Spread — contender {d['contender_spread_pct']}%, whole field "
              f"{d['whole_field_spread_pct']}%",
              f"* BH-FDR — cutoff `{d['bh_fdr']['cutoff']}`, rejects `{d['bh_fdr']['reject']}`",
              "", "### Gates", ""]
        for k, v in r["gates"].items():
            a.append(f"* `{k}` — **{'PASS' if v else 'FAIL'}**")
        a.append("")
    a += ["## Ordering study — may a comp term touch the board's RANKING?", "",
          "CRPS grades a distribution; a draft board is purely ordinal. This is the statistic that "
          "governs `blend_score` / `model_score`. Incumbent = the board's own formula "
          "(`board_proxy`, reconstructed from `board_assembly`'s constants).", ""]
    for ptype, o in rep.get("ordering", {}).items():
        for form, x in o["by_form"].items():
            a += [f"### {ptype.title()}s — `{form}` (comp arm `{o['comp_arm']}`)", "",
                  f"Best contender `{x['best_contender']}`, ΔIC vs the board's own formula "
                  f"**{x['delta_vs_board_proxy']:+.4f}**, improved in "
                  f"{x['folds_improved']}/{x['n_folds']} folds "
                  f"(per fold {x['delta_by_fold']}). "
                  f"PBO `{x['pbo_contender_set'].get('pbo')}`. "
                  f"Anchors: oracle-is-ceiling `{x['anchors']['oracle_is_the_ceiling']}`, "
                  f"placebo IC `{x['anchors']['placebo_ic']}`.", "",
                  "| arm | rank-IC |", "|---|---|"]
            for n, v in sorted(x["rank_ic"].items(), key=lambda kv: -kv[1]):
                a.append(f"| `{n}` | {v:+.4f} |")
            a.append("")
    return "\n".join(a)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="E7.13 Phase 2 — comp-projection validation")
    p.add_argument("--pool", default=str(DEFAULT_POOL))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT))
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    rep = run(Path(args.pool), Path(args.out_dir), seed=args.seed, write=not args.dry_run)
    print(json.dumps({"verdict": rep["verdict"], "by_type": rep["verdict_by_type"],
                      "fold_ceiling": rep["fold_ceiling"]["strictly_matured_folds"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
