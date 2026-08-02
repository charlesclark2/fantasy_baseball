"""run_e7_16_pipeline_comps.py — MLB Edge-E7.16: re-run E7.13's BOTH phases on the point-in-time
MLB Pipeline comp pool, and answer the question E7.13 had to defer to 2029.

    uv run python -m betting_ml.scripts.prospect_board.run_e7_16_pipeline_comps

Reads ONE local parquet (`build_pipeline_cohort.py`'s output) — no S3, no Snowflake. Seconds.

WHAT CHANGES FROM E7.13, AND WHAT DOES NOT
------------------------------------------
**Nothing in the engine or the harness.** `prospect_comps` (Gower + robust-z + the position filter +
k=25-distinct + `_dedupe_by_person`) and `comp_validation` (CRPS, randomized-PIT, the four two-sided
anchors, the matched foils, PBO/CSCV, DSR, BH-FDR, the clustered bootstrap) are imported and used
verbatim, and the scoring functions are literally the E7.13 runner's own `_score_type` /
`_ordering_study`. Only the FUEL changes.

**The fuel changes in exactly two ways, and both are the point:**

  1. **THE POOL IS POINT-IN-TIME.** E7.13's pool is FanGraphs' RETAINED board, whose `level` column
     is a near-perfect one-sided bust tell and whose `fv` carries an unquantifiable "may embed a
     later revision" caveat. The Pipeline archive serves the ranking as published, and its grade is
     read from the season's own scouting report. §1 crosstabs every as-of column on BOTH cohorts and
     requires the scan to FIRE on E7.8's `level` in the same pass it comes back clean here — a leak
     detector that has never fired on a known positive is not evidence (NF1.7 (a)).

  2. **THE BACKTEST CAN BE STRICTLY MATURED.** This is the whole story. E7.13's archive depth
     admitted exactly ONE strictly-matured fold, so its primary run RELAXED the maturity rule and
     granted historical queries hindsight — which is precisely why a cleared gate earned
     "BLEND-ELIGIBLE-NOT-WIRED, re-check 2029" rather than a ship. §2 reports the matured-fold count
     that this cohort actually supports (measured, not assumed) before a single score is read.

⚠️ THE FOLD COUNT IS NOT 13, AND THE REASON IS OURS NOT MLB'S. The Pipeline archive is 17 seasons
deep; the binding constraint is our own realized-outcome substrate (see `build_pipeline_cohort`).
§2 prints the number and what bounds it.
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

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.prospect_board import comp_validation as cv  # noqa: E402
from betting_ml.scripts.prospect_board.prospect_comps import build_pool, validate_pool  # noqa: E402
from betting_ml.utils.design_block import (  # noqa: E402
    design_block_from_comp_validation_report,
    insert_design_block,
)
from betting_ml.scripts.prospect_board.run_e7_13_comp_validation import (  # noqa: E402
    _ordering_study,
    _score_type,
)

log = logging.getLogger("e7_16.run")

_ABL = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
DEFAULT_COHORT = _ABL / "e7_16_artifacts/pipeline_comp_cohort.parquet"
#: E7.13's own pool — read ONLY as the leakage scan's positive control, never scored here.
E7_8_COHORT = _ABL / "e7_8_artifacts/fv_translation_cohort.parquet"
DEFAULT_OUT = _ABL / "e7_16_artifacts"

#: The as-of columns a comp built on this cohort could touch. Every one is crosstabbed.
SCAN_COLUMNS: tuple[str, ...] = (
    "fv", "age", "position", "top_level_pre_board", "pro_experience_years",
    "minor_k_pct", "minor_bb_pct", "minor_iso", "minor_gb_pct", "minor_start_share", "minor_pa",
    "pre_board_mlb_exposure", "overall_rank", "org_rank", "eta", "draft_year", "org",
    "bio_season", "milb_games", "last_milb_season",
)
#: The same scan on E7.8's cohort. `level` is the KNOWN POSITIVE (E7.13 §2.1) and `fv` the known
#: negative; the run asserts the first flags and reports the second beside it.
CONTROL_COLUMNS: tuple[str, ...] = ("level", "fv", "age", "top_level_pre_board", "position")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The leakage scan (with its positive control)
# ══════════════════════════════════════════════════════════════════════════════════════════════


class LeakageControlError(RuntimeError):
    """The leakage scan failed to flag the column it is KNOWN to flag.

    HARD stop. If the detector cannot reproduce E7.13's measured `level` leak, then its clean verdict
    on the Pipeline cohort carries no information — it would be the NF1.7 (a) failure exactly: a
    check that passes on nothing, read as a check that passed.
    """


def leakage_report(pipeline_cohort: pd.DataFrame, control_cohort: pd.DataFrame | None) -> dict:
    scan = cv.leakage_scan(pipeline_cohort, SCAN_COLUMNS)
    flag = (scan["leak_flag"].fillna(False).astype(bool) if "leak_flag" in scan.columns
            else pd.Series(False, index=scan.index))
    out: dict = {
        "pipeline_scan": scan.to_dict("records"),
        "pipeline_flagged": sorted(scan.loc[flag, "column"].tolist()),
    }
    if control_cohort is None:
        out["control"] = {"ran": False,
                          "note": "E7.8 cohort absent — the scan's clean verdict is UNVERIFIED"}
        return out
    ctl = cv.leakage_scan(control_cohort, CONTROL_COLUMNS)
    ctl_map = {r["column"]: r for r in ctl.to_dict("records")}
    level = ctl_map.get("level", {})
    if not level.get("leak_flag"):
        raise LeakageControlError(
            "the leakage scan did NOT flag E7.8's `level`, the column E7.13 measured as a "
            f"near-perfect one-sided bust tell ({level}). Until it does, its clean reading on the "
            "Pipeline cohort proves nothing."
        )
    out["control"] = {
        "ran": True, "scan": ctl.to_dict("records"),
        "positive_control_fired": True,
        "positive_control": {k: level.get(k) for k in
                             ("column", "auc_vs_outcome", "one_sided_bin_n",
                              "one_sided_bin_share", "one_sided_bin_debut_rate")},
        "negative_control": {k: ctl_map.get("fv", {}).get(k) for k in
                             ("column", "auc_vs_outcome", "one_sided_bin_share", "leak_flag")},
    }
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The fold census — REPORTED BEFORE ANY SCORE IS READ
# ══════════════════════════════════════════════════════════════════════════════════════════════


def fold_census(cohort: pd.DataFrame) -> dict:
    """What the cohort's depth actually buys, and what bounds it. See the module docstring."""
    out: dict = {"board_seasons": sorted(int(s) for s in cohort["board_season"].dropna().unique()),
                 "rows": int(len(cohort)),
                 "distinct_players": int(cohort["player_key"].nunique()),
                 "horizon_seasons": int(pd.to_numeric(cohort["horizon_seasons"],
                                                      errors="coerce").max()),
                 "by_type": {}}
    for ptype in ("batter", "pitcher"):
        pool = build_pool(cohort, player_type=ptype)
        strict = cv.fold_plan(pool, strict=True)
        relaxed = cv.fold_plan(pool, strict=False)
        out["by_type"][ptype] = {
            "pool": validate_pool(pool),
            "strictly_matured_folds": len(strict),
            "strict_plan": strict,
            "relaxed_folds": len(relaxed),
            "cscv_computable_strict": len(strict) >= 4,
        }
    out["label_coverage_bound"] = {
        "outcome_source": "mart_batter_rolling_stats / mart_pitcher_rolling_stats (Statcast era)",
        "earliest_covered_mlb_season": 2015,
        "note": "The BINDING bound on the fold count is our realized-outcome substrate, not the "
                "Pipeline archive (17 seasons) and not the MiLB game logs (2005+). A board season "
                "earlier than 2015 opens its 3-season outcome window before the marts begin, so a "
                "real player would be scored as a partial bust.",
    }
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The run
# ══════════════════════════════════════════════════════════════════════════════════════════════


def gate_sensitivity(scored: dict) -> dict:
    """For a side that FAILS: does the null rest on OUR gate choice, or on the data? (NF-D15 (g″)(b))

    Recording "we tested it, nothing there" without this is the trap that rule exists to prevent. Two
    questions, both answerable from the run's own numbers:

      1. **Would dropping the deflation gate flip it?** If another gate fails too, the binding
         constraint is not DSR and saying "it just missed DSR" would be wrong.
      2. **How wide is the tie the selection was resolved inside?** The pre-registered rule is
         min-CRPS over the contenders, and it is honoured — but if the top of the field is a fraction
         of a percent wide, "which arm was selected" is noise, and the arm that happened to lose the
         coin flip may be the one carrying the significant paired test. Reporting that is the NF1.8
         flip-distribution discipline; RE-PICKING on it after the fact would be the E2.1-r inversion.
    """
    gates = dict(scored.get("gates", {}))
    contenders = {n: m["crps"] for n, m in scored["arms"].items() if m.get("selectable")}
    best = min(contenders, key=contenders.get)
    ordered = sorted(contenders.items(), key=lambda kv: kv[1])
    runner_up = ordered[1] if len(ordered) > 1 else (None, float("nan"))
    tie_pct = (100.0 * (runner_up[1] - ordered[0][1]) / max(ordered[0][1], 1e-9)
               if runner_up[0] else float("nan"))
    without_dsr = {k: v for k, v in gates.items() if k != "dsr_contender_ge_0_95"}
    paired = scored.get("paired", {})
    return {
        "failing_gates": sorted(k for k, v in gates.items() if not v),
        "would_pass_without_the_dsr_gate": bool(all(without_dsr.values())),
        "binding_constraint": ("dsr_only" if all(without_dsr.values())
                               else "not_dsr_alone"),
        "selected": best,
        "runner_up": runner_up[0],
        "selection_margin_pct": round(float(tie_pct), 3),
        "runner_up_beats_incumbent_p": (paired.get("blend_vs_incumbent", {}).get("p_value")
                                        if runner_up[0] == "blend_comp_fv" else None),
        "note": "The pre-registered selection (min CRPS over the contender set) is reported as-run "
                "and NOT revisited; this block exists so the null is attributable, not so the pick "
                "can be changed after seeing the p-values.",
    }


def _verdict(scored: dict, *, strict: bool) -> str:
    """E7.13's gates, read on a fold plan that may now be CLEAN.

    E7.13 withheld the wiring for one stated reason and one only: its gates were cleared on a
    backtest that could not be made strictly leakage-clean at that archive depth, and the NF-D15 (g″)
    discipline says a real-but-not-cleanly-verifiable effect earns a scheduled re-validation rather
    than a ship. When the SAME gates clear on a STRICTLY-MATURED plan, that reason is discharged.
    """
    if not scored.get("blend_gates_all_pass"):
        return "DISPLAY_ONLY"
    return "BLEND_WIRE" if strict else "BLEND_ELIGIBLE_NOT_WIRED"


def run(cohort_path: Path, out_dir: Path, *, seed: int = 0, write: bool = True,
        control_path: Path | None = E7_8_COHORT) -> dict:
    cohort = pd.read_parquet(cohort_path)
    control = (pd.read_parquet(control_path)
               if control_path is not None and Path(control_path).exists() else None)

    report: dict = {
        "story": "E7.16 — E7.13's comp engine on the POINT-IN-TIME MLB Pipeline archive",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cohort_path": str(cohort_path),
        "cohort_built_at": datetime.fromtimestamp(Path(cohort_path).stat().st_mtime,
                                                  timezone.utc).isoformat(timespec="seconds"),
        "target": "fantasy_points over the 3 seasons after the board (0 for a prospect who never "
                  "reached MLB)",
        "primary_metric": "CRPS (proper — the target is ~57% exact zeros; MAE inverts here)",
        "incumbent": "fv_bucket (the empirical outcome distribution of same-grade, same-position "
                     "historical prospects — here the grade is MLB Pipeline's published Overall)",
    }

    # ── §1 leakage, WITH its positive control ────────────────────────────────────────────────
    report["leakage"] = leakage_report(cohort, control)
    log.info("leakage scan: flagged=%s (control fired=%s)",
             report["leakage"]["pipeline_flagged"],
             report["leakage"].get("control", {}).get("positive_control_fired"))

    # ── §2 the fold census, BEFORE any score ─────────────────────────────────────────────────
    report["fold_census"] = fold_census(cohort)
    for ptype, c in report["fold_census"]["by_type"].items():
        log.info("%s: matured folds = %d (relaxed %d); pool %d rows, bust share %s",
                 ptype, c["strictly_matured_folds"], c["relaxed_folds"],
                 c["pool"]["n_pool"], c["pool"]["bust_share"])

    strict_ok = all(c["cscv_computable_strict"]
                    for c in report["fold_census"]["by_type"].values())
    report["primary_fold_rule"] = "strict" if strict_ok else "relaxed"
    if not strict_ok:
        log.warning("[ALERT] fewer than 4 strictly-matured folds — PBO is UNDEFINED there, so the "
                    "primary falls back to the relaxed rule and the E7.13 caveat still stands.")

    # ── §3 phase 2A: the PROJECTION question, on the primary (strict) plan ───────────────────
    report["by_type"] = {}
    for ptype in ("batter", "pitcher"):
        r = _score_type(cohort, ptype, strict=strict_ok, seed=seed)
        r["verdict"] = _verdict(r, strict=strict_ok)
        if not r["blend_gates_all_pass"]:
            r["gate_sensitivity"] = gate_sensitivity(r)
        report["by_type"][ptype] = r
        log.info("%s projection: best=%s verdict=%s", ptype, r.get("best_contender"), r["verdict"])

    # …and the RELAXED plan beside it, as context only. E7.13's numbers came off a relaxed plan, so
    # showing both is what makes the two studies comparable — it is NOT a second selection.
    if strict_ok:
        report["relaxed_context"] = {
            t: {k: v for k, v in _score_type(cohort, t, strict=False, seed=seed).items()
                if k in ("arms", "best_contender", "gates", "deflation", "anchors", "folds")}
            for t in ("batter", "pitcher")}

    # ── §4 phase 2B: the ORDERING question ───────────────────────────────────────────────────
    report["ordering"] = {t: _ordering_study(cohort, t, seed=seed, strict=strict_ok)
                          for t in ("batter", "pitcher")}
    if strict_ok:
        report["ordering_relaxed_context"] = {
            t: _ordering_study(cohort, t, seed=seed, strict=False) for t in ("batter", "pitcher")}

    verdicts = {t: r["verdict"] for t, r in report["by_type"].items()}
    report["verdict_by_type"] = verdicts
    report["verdict"] = ("BLEND_WIRE" if all(v == "BLEND_WIRE" for v in verdicts.values())
                         else "SPLIT" if any(v == "BLEND_WIRE" for v in verdicts.values())
                         else "DISPLAY_ONLY")

    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "e7_16_comp_validation.json").write_text(json.dumps(report, indent=2, default=str))
        db = design_block_from_comp_validation_report(
            report, fold_rule="forward, 3-season outcome horizon matured "
            f"(primary_fold_rule={report.get('primary_fold_rule')!r})",
            primary_contrast="forward-outcome comparison", use_fold_census=True)
        (out_dir / "e7_16_comp_validation.md").write_text(
            insert_design_block(_markdown(report), db))
    return report


def _markdown(rep: dict) -> str:
    fc = rep["fold_census"]
    a = [f"# E7.16 — comps on the point-in-time Pipeline archive: {rep['verdict']}", "",
         f"**Cohort** — `{rep['cohort_path']}` built {rep['cohort_built_at']}",
         f"**Target** — {rep['target']}",
         f"**Primary metric** — {rep['primary_metric']}",
         f"**Incumbent** — {rep['incumbent']}", "",
         "## 1. Leakage scan (as-of columns vs the realized outcome)", ""]
    ctl = rep["leakage"].get("control", {})
    if ctl.get("ran"):
        pc, nc = ctl["positive_control"], ctl["negative_control"]
        a += [f"**Positive control fired** — E7.8's `level`: AUC {pc['auc_vs_outcome']}, largest "
              f"one-sided bin {pc['one_sided_bin_n']} rows "
              f"({pc['one_sided_bin_share']:.1%} of the cohort) at debut rate "
              f"{pc['one_sided_bin_debut_rate']}. Negative control `fv`: AUC "
              f"{nc['auc_vs_outcome']}, flag `{nc['leak_flag']}`.", ""]
    a += [f"**Pipeline cohort flagged columns: `{rep['leakage']['pipeline_flagged']}`**", "",
          "| column | kind | n | AUC vs outcome | largest one-sided bin | share | its debut rate | flag |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rep["leakage"]["pipeline_scan"]:
        if not r.get("present"):
            a.append(f"| `{r['column']}` | — | — | — | — | — | — | absent |")
            continue
        a.append(f"| `{r['column']}` | {r['kind']} | {r['n_observed']} | {r['auc_vs_outcome']} | "
                 f"`{r['largest_one_sided_bin']}` | {r['one_sided_bin_share']} | "
                 f"{r['one_sided_bin_debut_rate']} | {'🚨' if r['leak_flag'] else 'clean'} |")

    a += ["", "## 2. The fold census — read before any score", "",
          f"Board seasons `{fc['board_seasons']}`, {fc['rows']} rows, "
          f"{fc['distinct_players']} distinct players, horizon {fc['horizon_seasons']}.", "",
          "| type | pool rows | bust share | **strictly-matured folds** | relaxed folds | CSCV computable |",
          "|---|---|---|---|---|---|"]
    for t, c in fc["by_type"].items():
        a.append(f"| {t} | {c['pool']['n_pool']} | {c['pool']['bust_share']} | "
                 f"**{c['strictly_matured_folds']}** | {c['relaxed_folds']} | "
                 f"{c['cscv_computable_strict']} |")
    a += ["", fc["label_coverage_bound"]["note"], "",
          f"**Primary fold rule: `{rep['primary_fold_rule']}`.**", ""]

    for ptype, r in rep["by_type"].items():
        a += [f"## 3. {ptype.title()}s — projection: {r['verdict']}", "",
              f"Pool {r['pool']['n_pool']} rows, non-debut share **{r['pool']['bust_share']}**. "
              f"{r['n_rows_scored']}/{r['n_rows_total']} rows scoreable by every contender. "
              f"Folds: `{[f['query_season'] for f in r['folds']]}`.", "",
              "| arm | kind | CRPS | PIT max-decile-dev | p10–p90 coverage |", "|---|---|---|---|---|"]
        for name, m in sorted(r["arms"].items(), key=lambda kv: kv[1]["crps"]):
            tag = {"anchor": " 🎯 floor", "degenerate": " 🚧 ceiling",
                   "placebo": " 🎲 placebo"}.get(m["kind"], "")
            a.append(f"| `{name}`{tag} | {m['kind']} | {m['crps']:.2f} | "
                     f"{m['pit_max_decile_dev']:.4f} | {m['coverage_p10_p90']:.3f} |")
        a += ["", f"**Best contender** — `{r['best_contender']}`", "", "### Two-sided anchors", ""]
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
              f"* Performance degradation — `{d['pbo_contender_set'].get('performance_degradation')}`",
              f"* Flip distribution — `{d['pbo_contender_set'].get('flip_distribution')}`",
              f"* DSR — contender set `{d['dsr_contender_set']}`, whole field `{d['dsr_whole_field']}` "
              f"(n = {d['dsr_n_obs_used']} CLUSTERS, not {d['dsr_n_rows']} rows)",
              f"* Spread — contender {d['contender_spread_pct']}%, whole field "
              f"{d['whole_field_spread_pct']}%",
              f"* BH-FDR — cutoff `{d['bh_fdr']['cutoff']}`, rejects `{d['bh_fdr']['reject']}`",
              "", "### Gates", ""]
        for k, v in r["gates"].items():
            a.append(f"* `{k}` — **{'PASS' if v else 'FAIL'}**")
        if "gate_sensitivity" in r:
            g = r["gate_sensitivity"]
            a += ["", "### Is the null OURS or the data's? (gate sensitivity)", "",
                  f"* failing gates — `{g['failing_gates']}`",
                  f"* would it pass with the DSR gate REMOVED — **{g['would_pass_without_the_dsr_gate']}** "
                  f"⇒ binding constraint `{g['binding_constraint']}`",
                  f"* the selection was resolved inside a **{g['selection_margin_pct']}%** gap "
                  f"(`{g['selected']}` over `{g['runner_up']}`)"
                  + (f"; that runner-up's own paired test against the incumbent sits at p = "
                     f"{g['runner_up_beats_incumbent_p']}"
                     if g["runner_up_beats_incumbent_p"] is not None else ""),
                  f"* {g['note']}"]
        a.append("")

    a += ["## 4. Ordering — may a comp term touch the board's RANKING?", "",
          "⚖️ **Every arm is scored on MATCHED SUPPORT** (the rows on which all arms are defined) — "
          "see the E7.16 fix in `_ordering_study`. The unmatched column is shown beside it because "
          "the gap between them IS the finding: it is the comped subpopulation being easier to "
          "order, not the comp term ordering it better.", ""]
    for ptype, o in rep.get("ordering", {}).items():
        for form, x in o["by_form"].items():
            a += [f"### {ptype.title()}s — `{form}` (comp arm `{o['comp_arm']}`)", "",
                  f"Best contender `{x['best_contender']}`, ΔIC vs the board's own formula "
                  f"**{x['delta_vs_board_proxy']:+.4f}**, improved in "
                  f"{x['folds_improved']}/{x['n_folds']} folds (per fold {x['delta_by_fold']}). "
                  f"PBO `{x['pbo_contender_set'].get('pbo')}`. Anchors: oracle-is-ceiling "
                  f"`{x['anchors']['oracle_is_the_ceiling']}`, placebo IC "
                  f"`{x['anchors']['placebo_ic']}`. "
                  f"Matched support {x['n_rows_matched_support']}/{x['n_rows']} rows "
                  f"({x['matched_support_share']:.1%}); {x['rows_with_comp']:.1%} of rows have "
                  f"comps at all.", "",
                  "| arm | rank-IC (matched support) | rank-IC (unmatched — context only) |",
                  "|---|---|---|"]
            unm = x.get("rank_ic_unmatched_support", {})
            for n, v in sorted(x["rank_ic"].items(), key=lambda kv: -kv[1]):
                a.append(f"| `{n}` | {v:+.4f} | {unm.get(n, float('nan')):+.4f} |")
            a.append("")
    return "\n".join(a)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="E7.16 — comps on the point-in-time Pipeline archive")
    p.add_argument("--cohort", default=str(DEFAULT_COHORT))
    p.add_argument("--control", default=str(E7_8_COHORT),
                   help="E7.8's cohort, used ONLY as the leakage scan's positive control")
    p.add_argument("--out-dir", default=str(DEFAULT_OUT))
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    rep = run(Path(args.cohort), Path(args.out_dir), seed=args.seed, write=not args.dry_run,
              control_path=Path(args.control) if args.control else None)
    print(json.dumps({
        "verdict": rep["verdict"], "by_type": rep["verdict_by_type"],
        "primary_fold_rule": rep["primary_fold_rule"],
        "matured_folds": {t: c["strictly_matured_folds"]
                          for t, c in rep["fold_census"]["by_type"].items()},
        "leak_flagged": rep["leakage"]["pipeline_flagged"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
