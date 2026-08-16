"""run_nf_w6d_ceiling_gate.py — NF-W6d PHASE A: ceiling-gate every remaining optimizer-input
stat cell BEFORE anything is built (the NF-W6 oracle-first discipline, extended with the
NF-W6b-C matched-n refinement and the atom-aware forms).

Everything decidable in advance lives as a CONSTANT in `stat_distributions_d.py`; this runner
READS it (the NF-D16 discipline). The narrative pre-registration is committed at
`ablation_results/nf_w6d_preregistration.md` BEFORE the full run.

PIPELINE
  MATRIX: the NF-W6 certified build (`run_nf_w6_efficiency_marginals.build_matrix_w6` — the
  NF-W1 matrix + TD labels; PIT gate on EVERY load) + the three attached labels (INT / fumbles
  lost / 2-pt) at (season, week, gsis_id), conservation-guarded. No new FEATURES.

  PER CELL (22 = QB×6, RB×6, WR×5, TE×5): the class's incumbents (COUNT: head+bank and
  climatology; EVENT: climatology only), the three degenerates, and one block-peeking ORACLE +
  MATCHED-n CONTROL pair per declared form (COUNT: marginal / head_bank / cand_quantile / knn /
  hurdle / negbin; EVENT: marginal / knn / hurdle / negbin) — the conditional forms cross-fit
  within the block and their controls sized to the peek's effective (K−1)/K n. Metric `crps_q199`.

  THE DECISION: per-cell ceiling vs the BINDING incumbent → the NF-W5/W6 bands (<2% NO · 2–5%
  MARGINAL · ≥5% YES, stat_ok required) → the pre-registered LICENSE rule (YES or MARGINAL
  licenses the Phase-B bake-off; NO = point-only, a Phase-C default).

RUN (OPERATOR — LAPTOP; reads the S3 NFL lake read-only, writes local artifacts; >2 min):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6d_ceiling_gate --smoke
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6d_ceiling_gate
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6d_ceiling_gate --rewrite-report
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
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions_d as SDD  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w6_efficiency_marginals as W6R,
)

log = logging.getLogger("nfl.fantasy.nf_w6d")

_FANTASY_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy"
_REPORT_DIR = _FANTASY_DIR / "ablation_results"
_ARTIFACTS = _FANTASY_DIR / "artifacts"
SEASONS = W6R.SEASONS
FEATURES = list(WP.FEATURES)     # the champion feature set — ⛔ no exotic features


# ── Matrix (the NF-W6 build + the attached labels; PIT gate on EVERY load) ──────────────────────
def w6d_matrix_key(seasons: tuple[int, int]) -> str:
    payload = json.dumps({"base": W6R.w6_matrix_key(seasons), "attach": SDD.ATTACH_SOURCES,
                          "schema": 1}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def load_extra_feed(seasons: tuple[int, int]) -> pd.DataFrame:
    """The nflverse columns the attached labels are summed from — a lake read (DuckDB over the
    Delta raw tier), season/type-scoped exactly like `W1R.load_sources_w1`'s stats read."""
    from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q
    lo, hi = seasons
    cols = sorted({c for srcs in SDD.ATTACH_SOURCES.values() for c in srcs})
    return q(f"""
        select season, week, player_id, {', '.join(cols)}
        from {delta('stats_player_week')}
        where season between {lo} and {hi} and season_type = 'REG'
    """)


def build_matrix_w6d(seasons: tuple[int, int], *, rebuild_cache: bool = False
                     ) -> tuple[pd.DataFrame, dict, dict]:
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    cache = _ARTIFACTS / f"nf_w6d_stat_matrix_{w6d_matrix_key(seasons)}.parquet"
    if cache.exists() and not rebuild_cache:
        log.info("W6d matrix cache HIT %s — re-running the PIT gate over it", cache.name)
        feat = pd.read_parquet(cache)
        audit = WP.run_pit_gate(feat)
        feat = feat.loc[audit.pop("kept_index")].reset_index(drop=True)
        SDD.assert_all_stat_labels_present(feat)
        return feat, audit, {"cache": "hit"}
    feat, audit, _td = W6R.build_matrix_w6(seasons, rebuild_cache=rebuild_cache)
    feat, attach = SDD.attach_extra_labels(feat, load_extra_feed(seasons))
    SDD.assert_all_stat_labels_present(feat)
    feat.to_parquet(cache, index=False)
    log.info("W6d matrix cached → %s (%d rows; attach: %s)", cache.name, len(feat),
             {k: v for k, v in attach.items() if k.endswith("_total")})
    return feat, audit, attach


# ── One fold: every construction per stat, scored per cell ──────────────────────────────────────
def _score_or_none(bank, y, sel) -> dict | None:
    return None if bank is None else SDD.score_bank(bank[sel], y[sel])


def run_fold(fold: WP.Fold, feat: pd.DataFrame, stats: tuple[str, ...]) -> dict:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    test_pos = test["position"].to_numpy()
    cells_out: dict[str, dict] = {}
    inapplicable: dict[str, str] = {}

    for stat in stats:
        pos_for_stat = [p for p in SDD.POSITIONS if stat in SDD.POSITION_STATS[p]]
        if not pos_for_stat:
            continue
        cls = SDD.stat_class(stat)
        t_stat = time.time()
        y_tr, y_te = SDD._y(train, stat), SDD._y(test, stat)

        clim_tr = EM.climatology_bank(y_tr, train["position"].to_numpy())
        inc_cl = EM.apply_bank199(np.zeros(len(test)), test_pos, clim_tr)
        banks: dict[str, np.ndarray | None] = {"inc_climatology": inc_cl}
        if "inc_head_bank" in SDD.FOILS[cls]:
            banks["inc_head_bank"], _ = EM.inc_head_bank(train, test, FEATURES, stat)
        # sharpness degenerates derive from the class's CONDITIONAL incumbent where one exists
        # (COUNT: head+bank, the W6 convention), else the marginal foil (EVENT: the W6b-C one)
        deg_base = banks.get("inc_head_bank", inc_cl)
        banks["nihilist_zero"] = EM.anchor_nihilist(len(test))
        banks["zero_width"] = EM.anchor_zero_width(deg_base)
        banks["max_width"] = EM.anchor_max_width(deg_base)

        for form in SDD.CEILING_FORMS[cls]:
            orc, mat = SDD.ORACLE_PAIRS[form]
            try:
                banks[orc] = SDD.oracle_fn(form)(test, FEATURES, stat, fold.label)
            except SDD.InapplicableForm as e:
                banks[orc] = None
                inapplicable[f"{stat}|{orc}"] = str(e)
                log.warning("[W6d-A] fold %s %s: %s", fold.label, orc, e)
            try:
                banks[mat] = SDD.matched_fn(form)(train, test, FEATURES, stat)
            except SDD.InapplicableForm as e:
                banks[mat] = None
                inapplicable[f"{stat}|{mat}"] = str(e)
                log.warning("[W6d-A] fold %s %s: %s", fold.label, mat, e)
        assert set(banks) == set(SDD.ceiling_labels(cls)), "fold banks drifted from the field"

        for p in pos_for_stat:
            sel = test_pos == p
            scores = {lab: _score_or_none(b, y_te, sel) for lab, b in banks.items()}
            cells_out[SDD.cell_key(p, stat)] = {"scores": scores, "stat_class": cls}
        log.info("[W6d-A] fold %s stat %s (%s) in %.1fs", fold.label, stat, cls,
                 time.time() - t_stat)

    log.info("[W6d-A] fold %s complete in %.1fs (%d cells)", fold.label, time.time() - t0,
             len(cells_out))
    return {"label": fold.label, "n_test": int(len(test)), "cells": cells_out,
            "inapplicable": inapplicable}


# ── Verdict layer (derived, shared with --rewrite-report) ───────────────────────────────────────
def derive_verdict_layer(out: dict) -> dict:
    n_folds = out["n_folds"]
    frs = out["fold_results"]
    present = sorted(frs[0]["cells"].keys())
    sels = {c: SDD.select_ceiling(frs, c, n_folds) for c in present}
    count_p = {c: sels[c]["p_one_sided"] for c in present if sels[c]["stat_class"] == "count"}
    event_p = {c: sels[c]["p_one_sided"] for c in present if sels[c]["stat_class"] == "event"}
    fdr = SDD.fdr_two_families(count_p, event_p)
    for c in sels:
        sels[c]["fdr_binding"] = bool(fdr["binding"].get(c, False))
    decisions = {c: SDD.decide_ceiling(sels[c]) for c in sels}
    story = SDD.decide_ceiling_story(decisions)
    return {"selections": sels, "fdr": fdr, "decisions": decisions, "story_decision": story,
            "verdict": {"story": story["headline"],
                        "cells": {c: decisions[c]["answer"] for c in sorted(decisions)},
                        "licensed_cells": story["licensed_cells"]},
            "headline": story["headline"]}


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    p("# NF-W6d Phase A — the ceiling gate over every remaining optimizer-input stat cell")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} half-season blocks "
      f"({out['fold_labels'][0]}…{out['fold_labels'][-1]}, the NF-W1 axis verbatim) · "
      f"**rows:** {out['n_rows']} player-weeks · **cells:** {len(out['selections'])}")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held** "
      "(research-only, no changelog). THE DECISION GATE, not a bake-off: per-form block-peeking "
      "oracles floored at matched-n controls sized to the peek's effective n (NF-W6b-C). A cell "
      "with no ceiling is a recorded finding — its point mean is already near-optimal — and gets "
      "a calibrated Phase-C default. Metric `crps_q199`; the nihilist is SCORED every cell "
      "(NF-D11). Every direction word is three-way and derived at report time (NF-W2e).")
    p("")
    pit = out["pit_audit"]
    p(f"**PIT gate (NF-W0a `assert_point_in_time`):** {pit['weeks_checked']} weeks / "
      f"{pit['records_checked']} records checked; {pit['rows_dropped']} rows dropped. "
      f"Label attach: {out['attach_audit']}")
    p("")
    p(f"## Verdict: **{out['headline']}**")
    p("")
    sd = out["story_decision"]
    p(f"- LICENSED for the Phase-B bake-off (YES or MARGINAL ∧ stat_ok): {sd['licensed_cells']}")
    p(f"- YES: {sd['yes_cells']} · MARGINAL: {sd['marginal_cells']} · NO (point-only → "
      f"Phase-C default): {sd['no_cells']}")
    p("")
    p("## Per-cell ceilings (vs the BINDING incumbent; max over per-form block-peeking oracles)")
    p("")
    p("| cell | class | binding incumbent | inc CRPS | best form | ceiling Δ | ceiling % | CI95 "
      "| wins | p | BH | peek>matched | inapplicable | decision |")
    p("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c in sorted(out["selections"], key=lambda k: (out["selections"][k]["stat_class"], k)):
        s = out["selections"][c]
        d = out["decisions"][c]
        lo, hi = (s["ci95"] or [None, None])[:2]
        ci = f"[{lo}, {hi}]" if lo is not None else "n/a"
        p(f"| {c} | {s['stat_class']} | {s['binding_incumbent']} | {s['mean_incumbent']} | "
          f"{s['best_form']} | {s['mean_delta']} | {s['ceiling_pct']} | {ci} | "
          f"{s['fold_wins']}/{out['n_folds']} | {s['p_one_sided']} | {s['fdr_binding']} | "
          f"{s['best_form_oracle_beats_matched_n']} | "
          f"{', '.join(s['inapplicable_forms']) or '—'} | **{d['answer']}**"
          f"{' → BAKE-OFF' if d['licensed_for_bakeoff'] else ' → default'} |")
    p("")
    p("## Per-form detail (oracle vs matched-n — NF1.9 (f); conditional controls at (K−1)/K)")
    p("")
    for c in sorted(out["selections"]):
        s = out["selections"][c]
        p(f"### {c}")
        p("")
        p("| form | oracle CRPS | matched-n CRPS | oracle beats matched-n | Δ vs binding inc | "
          "CI95 | wins |")
        p("|---|---|---|---|---|---|---|")
        for f, r in s["per_form"].items():
            p(f"| {f} | {r['oracle_mean']} | {r['matched_n_mean']} | "
              f"{r['oracle_beats_matched_n']} | {r['mean_delta']} | {r['ci95']} | "
              f"{r['fold_wins']}/{out['n_folds']} |")
        for f, why in s["inapplicable_forms"].items():
            p(f"| {f} | INAPPLICABLE | — | — | — | — | {why} |")
        p("")
        p(f"- verdict: {SDD.verdict_sentence('oracle__' + s['best_form'], s['binding_incumbent'], s['mean_delta'], *(s['ci95'] or [None, None]))}")
        p(f"- anchors: {json.dumps(s['anchors'])}")
        p(f"- incumbent calibration: {json.dumps(s['incumbent_calibration'])}")
        p(f"- era (report-only): capture Δ {s['era_note']['capture_mean_delta']} vs legacy Δ "
          f"{s['era_note']['legacy_mean_delta']}")
        p(f"- decision: {out['decisions'][c]['reason']}")
        p("")
    p("## Pre-registration")
    p("")
    pre = out["preregistration"]
    p(f"- cells: {pre['cells']}; classes: count={pre['count_stats']} event={pre['event_stats']}; "
      f"forms per class: {pre['ceiling_forms']}; incumbents per class: {pre['foils']}.")
    p(f"- decision: bands {pre['bands']} on ceiling_pct ∧ stat_ok (CI excludes 0 ∧ calibrated fold "
      f"clause ∧ BH q={pre['fdr_q']} binding own AND pooled over two families); LICENSE rule: "
      f"{pre['license_bands']} ∧ stat_ok → Phase B; NO → Phase-C default. PBO UNDEFINED "
      f"(anchor contrast); no arm is selected.")
    p(f"- matched-n sizing: marginal = full block (W6); conditional forms = (K−1)/K of the block "
      f"(K={pre['crossfit_k']}, the NF-W6b-C refinement). MIN_COND_ROWS={pre['min_cond_rows']} "
      f"(a hurdle form below it is INAPPLICABLE, recorded, never scored on a constant).")
    p("")
    p(f"_Runtime: {out['runtime_seconds']}s · seed {pre['seed']} · matrix cache key "
      f"{out['matrix_key']}_")
    path.write_text("\n".join(a))


def main(argv=None) -> int:  # noqa: C901 — orchestration
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-W6d Phase A ceiling gate")
    ap.add_argument("--smoke", action="store_true",
                    help="2 folds, all cells; degenerate movability HARD-asserted; "
                         "artifacts suffixed _smoke")
    ap.add_argument("--only-stat", default=None, choices=list(SDD.GATED_STATS),
                    help="restrict to one stat — a harness PATH PROOF, never a decision artifact")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--rewrite-report", action="store_true")
    args = ap.parse_args(argv)
    suffix = ("_smoke" if args.smoke else "") + (
        f"_only_{args.only_stat}" if args.only_stat else "")
    json_path = _REPORT_DIR / f"nf_w6d_ceiling_gate{suffix}.json"

    if args.rewrite_report:
        out = json.loads(json_path.read_text())
        before = dict(out.get("verdict", {}))
        out.update(derive_verdict_layer(out))
        moved = {k: (before.get(k), v) for k, v in out["verdict"].items() if before.get(k) != v}
        if moved:
            out["verdict_corrected_from"] = before
            log.warning("VERDICT MOVED on re-derivation: %s", json.dumps(moved, default=str))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        json_path.write_text(json.dumps(out, indent=2, default=float))
        write_report(out, _REPORT_DIR / f"nf_w6d_ceiling_gate{suffix}.md")
        print(json.dumps({"verdict": out["verdict"], "moved": moved}, indent=2, default=str))
        return 0

    if args.only_stat:
        log.warning("⚠️ --only-stat %s: a harness PATH PROOF — partial field, partial FDR; NOT "
                    "a decision artifact (suffixed %s)", args.only_stat, suffix)
    t_start = time.time()
    SDD.assert_substrate_is_complete()
    feat, pit_audit, attach = build_matrix_w6d(SEASONS, rebuild_cache=args.rebuild_cache)
    folds = WP.build_folds(feat)
    if args.smoke:
        folds = folds[-2:]
    n_folds = len(folds)
    stats = (args.only_stat,) if args.only_stat else SDD.GATED_STATS
    log.info("NF-W6d-A: %d folds over %d player-weeks; %d cells", n_folds, len(feat),
             len(SDD.cells()))
    frs = [run_fold(f, feat, stats) for f in folds]

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": SDD.STORY, "phase": "A", "smoke": bool(args.smoke), "only_stat": args.only_stat,
        "runtime_seconds": round(time.time() - t_start, 1),
        "selection_metric": SDD.PRIMARY_METRIC,
        "n_folds": n_folds, "fold_labels": [f.label for f in folds], "n_rows": int(len(feat)),
        "matrix_key": w6d_matrix_key(SEASONS), "pit_audit": pit_audit, "attach_audit": attach,
        "preregistration": {
            "cells": list(SDD.cells()), "count_stats": list(SDD.COUNT_STATS),
            "event_stats": list(SDD.EVENT_STATS),
            "ceiling_forms": {k: list(v) for k, v in SDD.CEILING_FORMS.items()},
            "foils": {k: list(v) for k, v in SDD.FOILS.items()},
            "oracle_pairs": {k: list(v) for k, v in SDD.ORACLE_PAIRS.items()},
            "bands": list(SDD.CEILING_BANDS), "license_bands": list(SDD.LICENSE_BANDS),
            "fdr_q": SDD.FDR_Q, "crossfit_k": SDD.CROSSFIT_K,
            "min_cond_rows": SDD.MIN_COND_ROWS, "features": FEATURES, "seed": SDD._SEED,
            "test_blocks": [list(t) for t in SDD.TEST_BLOCKS], "purge_weeks": SDD.PURGE_WEEKS,
        },
        "fold_results": frs,
    }
    out.update(derive_verdict_layer(out))

    if args.smoke:
        # MH2.1 (d) movability control: every degenerate must LOSE in every scored cell
        bad = {c: [k for k, v in out["selections"][c]["anchors"].items() if not v]
               for c in out["selections"]}
        bad = {c: ks for c, ks in bad.items() if ks}
        if bad:
            raise SystemExit(f"POSITIVE CONTROL FAILED — degenerate anchors do not lose: {bad}")
        log.info("positive control OK: all degenerates lose in every scored cell")

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, default=float))
    write_report(out, _REPORT_DIR / f"nf_w6d_ceiling_gate{suffix}.md")
    log.info("verdict: %s (%.1fs)", out["headline"], out["runtime_seconds"])
    print(json.dumps({"verdict": out["verdict"], "runtime_seconds": out["runtime_seconds"]},
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
