"""run_nf_w6_efficiency_marginals.py — NF-W6: per-stat distributional targets — the ORACLE
DECISION GATE. ⭐ This runner deliberately does NOT run a bake-off: after three consecutive
component nulls (NF-W3/W4/W5) the story opens with the decision object — realized-efficiency
oracle CEILINGS per (position, stat) cell over the champion's per-stat predictive — and only a
demonstrably LARGE ceiling (the pre-registered bands) licenses building the §0.5 bake-off at all.

Everything decidable in advance lives as a CONSTANT in `efficiency_marginals.py`; this runner
READS it (the NF-D16 discipline). The narrative pre-registration is committed at
`ablation_results/nf_w6_preregistration.md` BEFORE the full run.

PIPELINE
  MATRIX: the NF-W1 certified build (`run_nf_w1_weekly_bakeoff.build_matrix` — provenance +
  the NF-W0a PIT gate on EVERY build, cache hit or not) + the three TD label columns attached at
  (season, week, gsis_id) with the frame's retained-zero convention (conservation-guarded,
  duplicate-grain-refusing). NF-W6 introduces NO new features and NO play-by-play join — the
  NF-W3 franchise-code trap is honored by absence.

  PER CELL (12 = QB×4, RB×4, WR×2, TE×2): the two incumbent forms (champion head + purged-cal
  residual bank; per-position climatology), three block-peeking oracles (climatology / head+bank
  / candidate 9-knot quantile + NF-MARGIN1 exponential tail — conditional forms CROSS-FIT within
  the block so no row sees its own label), three matched-n capacity controls (NF1.9 (f)), and the
  three degenerate anchors (nihilist/zero-width/max-width — scored, never reasoned about).
  Metric: `crps_q199` (the dense grid — the 39-level grid is blind to tail headroom).

  THE DECISION: per-cell ceiling vs the BINDING incumbent → the NF-W5 bands (<2% NO · 2–5%
  MARGINAL · ≥5% YES, stat_ok required); story verdict BUILD iff any YES, else RECORDED NULL.

RUN (LAPTOP — reads the S3 NFL lake read-only, writes local artifacts):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6_efficiency_marginals --smoke
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6_efficiency_marginals
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6_efficiency_marginals --rewrite-report
"""
from __future__ import annotations

import argparse
import hashlib
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

from quant_sports_intel_models.football.nfl.fantasy import efficiency_marginals as EM  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf_w1_weekly_bakeoff as W1R  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_w6")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_ARTIFACTS = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
SEASONS = (2016, 2025)
FEATURES = list(WP.FEATURES)


# ── Matrix (the NF-W1 certified build + TD labels; PIT gate on EVERY load — NF-C0e) ─────────────
def w6_matrix_key(seasons: tuple[int, int]) -> str:
    payload = json.dumps({"base": WP.matrix_key(seasons), "td_stats": list(EM.TD_STATS),
                          "schema": 1}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def build_matrix_w6(seasons: tuple[int, int], *, rebuild_cache: bool = False
                    ) -> tuple[pd.DataFrame, dict, dict]:
    """The NF-W1 certified matrix + TD labels. ⭐ THE PIT GATE RUNS ON EVERY BUILD, cache hit or
    not (the NF-C0e wired-≠-invoked shape, cache edition)."""
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    cache = _ARTIFACTS / f"nf_w6_stat_matrix_{w6_matrix_key(seasons)}.parquet"
    if cache.exists() and not rebuild_cache:
        log.info("matrix cache HIT %s — re-running the PIT gate over it", cache.name)
        feat = pd.read_parquet(cache)
        audit = WP.run_pit_gate(feat)
        feat = feat.loc[audit.pop("kept_index")].reset_index(drop=True)
        EM.assert_stat_labels_present(feat)
        return feat, audit, {"cache": "hit"}

    feat, audit = W1R.build_matrix(seasons, rebuild_cache=rebuild_cache)
    stats_feed = W1R.load_sources_w1(seasons)["stats"]
    feat, td_audit = EM.attach_td_labels(feat, stats_feed)
    EM.assert_stat_labels_present(feat)
    feat.to_parquet(cache, index=False)
    log.info("W6 matrix cached → %s (%d rows; TD attach: %s)", cache.name, len(feat),
             {k: v for k, v in td_audit.items() if k.endswith("_total")})
    return feat, audit, td_audit


# ── One fold: every construction per stat, scored per cell ──────────────────────────────────────
def run_fold(fold: WP.Fold, feat: pd.DataFrame) -> dict:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    test_pos = test["position"].to_numpy()
    cells_out: dict[str, dict] = {}

    for stat in EM.STATS:
        pos_for_stat = [p for p in EM.POSITIONS if stat in EM.POSITION_STATS[p]]
        t_stat = time.time()

        y_tr = pd.to_numeric(train[stat], errors="coerce").fillna(0.0).to_numpy(float)
        y_te = pd.to_numeric(test[stat], errors="coerce").fillna(0.0).to_numpy(float)

        inc_hb, cal_note = EM.inc_head_bank(train, test, FEATURES, stat)
        clim_tr = EM.climatology_bank(y_tr, train["position"].to_numpy())
        inc_cl = EM.apply_bank199(np.zeros(len(test)), test_pos, clim_tr)

        banks: dict[str, np.ndarray] = {
            "inc_head_bank": inc_hb,
            "inc_climatology": inc_cl,
            EM.oracle_of("inc_climatology"): EM.oracle_climatology(test, stat),
            EM.oracle_of("inc_head_bank"): EM.oracle_head_bank(test, FEATURES, stat, fold.label),
            EM.matched_n_of("inc_climatology"): EM.matched_climatology(train, test, stat),
            EM.matched_n_of("inc_head_bank"): EM.matched_head_bank(train, test, FEATURES, stat),
            EM.matched_n_of("cand_lgbm_quantile"): EM.matched_cand_quantile(
                train, test, FEATURES, stat),
            "nihilist_zero": EM.anchor_nihilist(len(test)),
            # sharpness degenerates derive from the CONDITIONAL incumbent form (declared)
            "zero_width": EM.anchor_zero_width(inc_hb),
            "max_width": EM.anchor_max_width(inc_hb),
        }
        orc_cq, tails = EM.oracle_cand_quantile(test, FEATURES, stat, fold.label)
        banks[EM.oracle_of("cand_lgbm_quantile")] = orc_cq

        for p in pos_for_stat:
            sel = test_pos == p
            scores = {lab: EM.score_bank(b[sel], y_te[sel]) for lab, b in banks.items()}
            cells_out[EM.cell_key(p, stat)] = {
                "scores": scores,
                "tail_note": {k: tails[p][k] for k in ("beta_hi", "beta_lo", "n_hi", "n_lo",
                                                       "thin_hi", "thin_lo")},
                "cal_split": cal_note,
            }
        # ⭐ ORACLE FIRST (the NF-W3/W4/W5 discipline): the per-form peeking CEILING vs the
        # (per-fold) better incumbent is logged BEFORE any selection layer runs.
        for p in pos_for_stat:
            sc = cells_out[EM.cell_key(p, stat)]["scores"]
            inc_best = min(sc[f]["crps_q199"] for f in EM.INCUMBENT_FORMS)
            ceil = {f: round(inc_best - sc[EM.oracle_of(f)]["crps_q199"], 4)
                    for f in EM.ORACLE_FORMS}
            log.info("[W6] %s %s|%s — ⭐ per-form peeking CEILING vs the better incumbent "
                     "(crps_q199 %.4f): %s", fold.label, p, stat, inc_best, ceil)
        log.info("[W6] fold %s stat %s in %.1fs", fold.label, stat, time.time() - t_stat)

    log.info("[W6] fold %s complete in %.1fs (%d cells)", fold.label, time.time() - t0,
             len(cells_out))
    return {"label": fold.label, "n_test": int(len(test)), "cells": cells_out}


# ── Verdict layer (derived, shared with --rewrite-report — NF-W2e one level up) ─────────────────
def derive_verdict_layer(out: dict) -> dict:
    """⭐ Re-derive EVERY decision from the stored fold scores — no refit (NF-W2e/W3 rule)."""
    n_folds = out["n_folds"]
    frs = out["fold_results"]
    sels = {c: EM.select_cell(frs, c, n_folds) for c in EM.cells()}

    fams = EM.fdr_families()
    yards_p = {k: sels[k.removeprefix("w6_ceiling_")]["p_one_sided"] for k in fams["yards"]}
    tds_p = {k: sels[k.removeprefix("w6_ceiling_")]["p_one_sided"] for k in fams["tds"]}
    fdr = EM.fdr_two_families_w6(yards_p, tds_p)
    for c in sels:
        sels[c]["fdr_binding"] = bool(fdr["binding"].get(f"w6_ceiling_{c}", False))

    decisions = {c: EM.decide_cell(sels[c]) for c in sels}
    story = EM.decide_story(decisions)
    anchor_failures = {c: [k for k, v in sels[c]["anchors"].items() if not v]
                       for c in sels if not all(sels[c]["anchors"].values())}
    verdict = {"story": story["answer"],
               "cells": {c: decisions[c]["answer"] for c in sorted(decisions)}}
    n_yes = len(story["yes_cells"])
    n_marg = len(story["marginal_cells"])
    headline = (f"CEILING-GATE[{story['answer']}] yes={n_yes} marginal={n_marg} "
                f"no={len(decisions) - n_yes - n_marg} of {len(decisions)} cells")
    return {"selections": sels, "fdr": fdr, "cell_decisions": decisions,
            "story_decision": story, "anchor_failures": anchor_failures,
            "verdict": verdict, "headline": headline}


# ── Report (every verdict word DERIVED at report time — never stored; NF-W2e) ───────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    p("# NF-W6 — efficiency + yards + touchdowns as distributional targets: THE ORACLE GATE")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} half-season blocks "
      f"({out['fold_labels'][0]}…{out['fold_labels'][-1]}, the NF-W1 axis verbatim) · "
      f"**rows:** {out['n_rows']} player-weeks · **cells:** {len(out['selections'])}")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** "
      "(research-only, no changelog). ⭐ This is the DECISION GATE, not a bake-off: after three "
      "component nulls (NF-W3/W4/W5) nothing is built unless a per-cell realized-efficiency "
      "ceiling is demonstrably large. Selection metric `crps_q199` (the NF-MARGIN1 dense grid); "
      "TD cells are zero-heavy ⇒ CRPS, never MAE (NF-D11/D14), with the all-zero degenerate "
      "SCORED every cell. Every direction word is three-way and derived at report time, failing "
      "closed to `TIES` (NF-W2e).")
    p("")
    pit = out["pit_audit"]
    p(f"**PIT gate (NF-W0a `assert_point_in_time`):** {pit['weeks_checked']} weeks / "
      f"{pit['records_checked']} records checked; {pit['rows_dropped']} rows dropped.")
    p("")
    sd = out["story_decision"]
    p(f"## Verdict: **{out['headline']}**")
    p("")
    p(f"{sd['reason']}")
    p("")
    p("## Per-cell ceilings (vs the BINDING incumbent; max over per-form block-peeking oracles)")
    p("")
    p("| cell | binding incumbent | inc CRPS | best form | ceiling Δ | ceiling % | CI95 | "
      "wins | p | BH | decision |")
    p("|---|---|---|---|---|---|---|---|---|---|---|")
    for c in sorted(out["selections"]):
        s = out["selections"][c]
        d = out["cell_decisions"][c]
        lo, hi = (s["ci95"] or [None, None])[:2]
        ci = f"[{lo}, {hi}]" if lo is not None else "n/a"
        p(f"| {c} | {s['binding_incumbent']} | {s['mean_incumbent']} | {s['best_form']} | "
          f"{s['mean_delta']} | {s['ceiling_pct']} | {ci} | {s['fold_wins']}/{out['n_folds']} | "
          f"{s['p_one_sided']} | {s['fdr_binding']} | **{d['answer']}** |")
    p("")
    p("## Per-form detail (oracle vs matched-n — NF1.9 (f): a peek is informative only if it "
      "beats its own form at matched n)")
    p("")
    for c in sorted(out["selections"]):
        s = out["selections"][c]
        p(f"### {c}")
        p("")
        p("| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | "
          "CI95 | wins |")
        p("|---|---|---|---|---|---|---|")
        for f, pf in s["per_form"].items():
            lo, hi = (pf["ci95"] or [None, None])[:2]
            ci = f"[{lo}, {hi}]" if lo is not None else "n/a"
            p(f"| {f} | {pf['oracle_mean']} | {pf['matched_n_mean']} | "
              f"{pf['oracle_beats_matched_n']} | {pf['mean_delta']} | {ci} | "
              f"{pf['fold_wins']}/{out['n_folds']} |")
        anc = s["anchors"]
        cal = s["incumbent_calibration"]
        era = s["era_note"]
        p("")
        p(f"- verdict: {EM.verdict_sentence(EM.oracle_of(s['best_form']), s['binding_incumbent'], s['mean_delta'], *(s['ci95'] or [None, None]))}")
        p(f"- anchors: nihilist_loses={anc['nihilist_loses']} zero_width_loses="
          f"{anc['zero_width_loses']} max_width_loses={anc['max_width_loses']} "
          f"(the nihilist losing on a TD cell is the CRPS-soundness proof — NF-D11)")
        p(f"- incumbent calibration: coverage(80) {cal['coverage_80']} · pred P(0) "
          f"{cal['pred_p0_mean']} vs realized {cal['real_p0']}")
        p(f"- era (report-only): capture Δ {era['capture_mean_delta']} vs legacy Δ "
          f"{era['legacy_mean_delta']}")
        p(f"- {s['pbo_state']}")
        p("")
    if out.get("anchor_failures"):
        p(f"⚠️ **Anchor failures:** {json.dumps(out['anchor_failures'])} — a cell whose "
          "degenerate does NOT lose has an unsound metric reading there; its ceiling is "
          "quarantined from the story verdict ONLY if it was a YES (none of this is silent).")
        p("")
    if out.get("positive_control") is not None:
        pc = out["positive_control"]
        p(f"**Instrument positive control (MH2.1 (d), smoke):** ×{pc['scale']} regime shift on "
          f"{pc['position']}|{pc['stat']} → ceiling {pc['ceiling_unshifted']} → "
          f"{pc['ceiling_shifted']} (instrument_sees_the_shift={pc['instrument_sees_the_shift']})")
        p("")
    p("## Pre-registration")
    p("")
    pre = out["preregistration"]
    p(f"- decision bands: NO < {pre['ceiling_bands'][0]}% ≤ MARGINAL < "
      f"{pre['ceiling_bands'][1]}% ≤ YES on ceiling_pct; `stat_ok` = CI95 excludes zero ∧ "
      f"calibrated fold clause ∧ BH binding (own family AND pooled). Not stat_ok → NO.")
    p(f"- incumbent forms: {pre['incumbent_forms']} (the BINDING one sets the bar); oracle "
      f"forms: {pre['oracle_forms']} (block-peeking, conditional forms cross-fit K="
      f"{pre['crossfit_k']}); anchors: {pre['anchors']}.")
    p(f"- FDR families (own + pooled, stricter binds — MH2 (a)): yards="
      f"{len(pre['fdr_families']['yards'])} cells, tds={len(pre['fdr_families']['tds'])} cells.")
    p("- PBO: UNDEFINED at this stage (pre-registered anchor contrast, not a searched field — "
      "the NF-W5 ceiling rule). DSR: does not arise (no arm is selected). `classify_null` is "
      "NOT invoked (the n_arms=1 fold-shortage mis-render — NF-W3 (c)).")
    p("- estimator bias: " + out["selections"][sorted(out["selections"])[0]]["estimator_note"])
    p("")
    p(f"_Runtime: {out['runtime_seconds']}s · seed {pre['seed']} · matrix cache key "
      f"{out['matrix_key']}_")
    path.write_text("\n".join(a))


def main(argv=None) -> int:  # noqa: C901 — orchestration
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-W6 per-stat oracle decision gate")
    ap.add_argument("--smoke", action="store_true",
                    help="2 folds + the instrument positive control, artifacts suffixed _smoke")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="regenerate the .md + verdict layer from the stored .json — no refit")
    args = ap.parse_args(argv)
    suffix = "_smoke" if args.smoke else ""
    json_path = _REPORT_DIR / f"nf_w6_efficiency_marginals{suffix}.json"

    if args.rewrite_report:
        out = json.loads(json_path.read_text())
        before = dict(out.get("verdict", {}))
        out.update(derive_verdict_layer(out))
        moved = {k: (before.get(k), v) for k, v in out["verdict"].items()
                 if before.get(k) != v}
        if moved:
            out["verdict_corrected_from"] = before
            out["verdict_correction_note"] = (
                "re-derived from the stored fold scores without refitting (NF-W2e one level up)")
            log.warning("VERDICT MOVED on re-derivation: %s", json.dumps(moved, default=str))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        json_path.write_text(json.dumps(out, indent=2, default=float))
        write_report(out, _REPORT_DIR / f"nf_w6_efficiency_marginals{suffix}.md")
        log.info("report + verdict layer re-derived from %s (no refit): %s",
                 json_path.name, out["headline"])
        print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                          "moved": moved}, indent=2, default=str))
        return 0

    t_start = time.time()
    feat, pit_audit, td_audit = build_matrix_w6(SEASONS, rebuild_cache=args.rebuild_cache)
    folds = WP.build_folds(feat)
    if args.smoke:
        folds = folds[-2:]
    n_folds = len(folds)
    log.info("NF-W6: %d folds over %d player-weeks; %d cells; labels per cell = %d",
             n_folds, len(feat), len(EM.cells()), len(EM.all_labels()))

    frs = [run_fold(f, feat) for f in folds]

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": EM.STORY, "smoke": bool(args.smoke),
        "runtime_seconds": round(time.time() - t_start, 1),
        "selection_metric": EM.PRIMARY_METRIC,
        "n_folds": n_folds, "fold_labels": [f.label for f in folds],
        "n_rows": int(len(feat)),
        "matrix_key": w6_matrix_key(SEASONS),
        "pit_audit": pit_audit, "td_attach_audit": td_audit,
        "preregistration": {
            "position_stats": {k: list(v) for k, v in EM.POSITION_STATS.items()},
            "incumbent_forms": list(EM.INCUMBENT_FORMS),
            "oracle_forms": list(EM.ORACLE_FORMS),
            "anchors": list(EM.anchors()),
            "primary_metric": EM.PRIMARY_METRIC,
            "crossfit_k": EM.CROSSFIT_K,
            "ceiling_bands": list(EM.CEILING_BANDS),
            "min_bank_rows": EM.MIN_BANK_ROWS, "min_tail_n": EM.MIN_TAIL_N,
            "fit_levels": list(EM.FIT_LEVELS),
            "test_blocks": [list(t) for t in EM.TEST_BLOCKS],
            "purge_weeks": EM.PURGE_WEEKS, "fdr_q": EM.FDR_Q,
            "fdr_families": {k: list(v) for k, v in EM.fdr_families().items()},
            "capture_era_folds": list(EM.CAPTURE_ERA_FOLDS),
            "features": FEATURES, "seed": EM._SEED,
        },
        "fold_results": frs,
        "positive_control": None,
    }

    if args.smoke:
        # ⭐ MH2.1 (d) / NF-W7b smoke-movability: the instrument must SEE a known regime shift
        # BEFORE the full run is trusted. HARD assert — a blind instrument refuses the smoke.
        f_last = folds[-1]
        train, test = feat.loc[f_last.train_idx], feat.loc[f_last.test_idx]
        y_tr = pd.to_numeric(train["passing_yards"], errors="coerce").fillna(0.0).to_numpy(float)
        clim = EM.climatology_bank(y_tr, train["position"].to_numpy())
        pc = EM.positive_control_shift(test, "passing_yards", "QB", clim)
        out["positive_control"] = pc
        if not pc["instrument_sees_the_shift"]:
            raise SystemExit(f"POSITIVE CONTROL FAILED — the ceiling instrument cannot see a "
                             f"×{pc['scale']} regime shift: {pc} (refusing the smoke)")
        log.info("positive control OK: %s", pc)

    out.update(derive_verdict_layer(out))

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, default=float))
    write_report(out, _REPORT_DIR / f"nf_w6_efficiency_marginals{suffix}.md")
    log.info("verdict: %s (%.1fs)", out["headline"], out["runtime_seconds"])
    print(json.dumps({"verdict": out["verdict"], "headline": out["headline"],
                      "story_decision": out["story_decision"],
                      "runtime_seconds": out["runtime_seconds"]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
