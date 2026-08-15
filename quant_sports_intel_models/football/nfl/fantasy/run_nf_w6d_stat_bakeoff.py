"""run_nf_w6d_stat_bakeoff.py — NF-W6d PHASE B: the §0.5 bake-off over the cells Phase A
licensed (the NF-W6b methodology, atom-aware, per-class family — fresh registration).

Everything decidable in advance lives as a CONSTANT in `stat_distributions_d.py`; this runner
READS it. The cell list is NOT chosen here: it is READ from the Phase-A record
(`nf_w6d_ceiling_gate.json` → `verdict.licensed_cells`) — the pre-registered license rule
decides, mechanically. `--cells` exists only as a harness PATH PROOF (suffixed, loud).

⚠️ REPRODUCTION CONTROL (NF-W2d) — runs FIRST on every fold, before any new cell is scored: the
7 already-served cells' winning constructions are re-fit through the SERVING DISPATCH
(`stat_distribution_serving.ARM_DISPATCH` → `stat_distributions.arm_*`, by identity) on the fold
and must reproduce the certifying records' fold CRPS BYTE-IDENTICALLY. Any mismatch marks THE RUN
INVALID: the JSON is written with `invalid: true` and NO verdict layer, and the process exits 2.

PIPELINE (per licensed cell): the class family (COUNT: lgbm_quantile_tail / lgbm_hurdle_tail /
knn_quantile / count_negbin; EVENT: lgbm_hurdle_tail / knn_quantile / count_negbin), the class
foils (COUNT: inc_head_bank + inc_climatology; EVENT: inc_climatology), the three degenerates,
the permuted anchor (the class's declared form on labels permuted within position-week), and one
oracle/matched pair per family form + the marginal pair. Metric `crps_q199`. Gates: the W6b-C ten
named clauses (paired lift ∧ calibrated fold clause ∧ PBO<0.2 ∧ DSR≥0.95 ∧ two-family BH-FDR ∧
one-sided coverage floor ∧ degenerates lose ∧ permutation behaves ∧ not a foil tie ∧ the
winner's own-form floor). Null: `cv_power.classify_null(declared_field_size=…)` read through
`field_remedy_admissible`, with the DSR MECHANISM attached (NF-W6b-C).

RUN (OPERATOR — LAPTOP; reads the S3 NFL lake read-only, writes local artifacts; >2 min):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6d_stat_bakeoff --smoke --cells "RB|receptions,WR|receiving_tds"
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6d_stat_bakeoff
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6d_stat_bakeoff --rewrite-report
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

from quant_sports_intel_models.football.nfl.fantasy import efficiency_marginals as EM  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions_d as SDD  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w6d_ceiling_gate as W6DA,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    stat_distribution_serving as SDS,
)

log = logging.getLogger("nfl.fantasy.nf_w6d_b")

_FANTASY_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy"
_REPORT_DIR = _FANTASY_DIR / "ablation_results"
SEASONS = W6DA.SEASONS
FEATURES = list(WP.FEATURES)
GATE_RECORD = _REPORT_DIR / "nf_w6d_ceiling_gate.json"
W6B_RECORD = _PROJECT_ROOT / SDS.RECORD_RELPATH
W6BC_RECORD = _PROJECT_ROOT / SDS.RECORD_RELPATH_W6BC


# ── Licensed cells (READ from the Phase-A record; never chosen here) ────────────────────────────
def licensed_cells_from_gate(path: Path = GATE_RECORD) -> list[str]:
    if not path.exists():
        raise SystemExit(f"Phase-A record missing: {path} — run run_nf_w6d_ceiling_gate (full, "
                         f"not --smoke) first; the bake-off cell list is READ from it")
    rec = json.loads(path.read_text())
    if rec.get("smoke") or rec.get("only_stat"):
        raise SystemExit("refusing to license a bake-off off a --smoke / --only-stat Phase-A "
                         "record — a partial gate is a path proof, not a decision artifact")
    cells = list(rec["verdict"]["licensed_cells"])
    bad = [c for c in cells if c not in SDD.cells()]
    if bad:
        raise SystemExit(f"Phase-A licensed cells outside the declared map: {bad}")
    return cells


# ── Reproduction control (NF-W2d) ───────────────────────────────────────────────────────────────
def reproduce_served_cells(fold: WP.Fold, feat: pd.DataFrame, reference: dict) -> dict:
    """Re-fit the 7 served cells' winners on this fold THROUGH THE SERVING DISPATCH and compare
    each cell's fold CRPS with the certifying record — exact equality required."""
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    test_pos = test["position"].to_numpy()
    observed: dict[str, float] = {}
    for arm, stat in SDS.served_fit_keys():
        bank, _ = SDS.ARM_DISPATCH[arm](train, test, FEATURES, stat)
        y_te = SDD._y(test, stat)
        for cell, cell_arm in SDS.SERVED_CELLS.items():
            pos, cell_stat = cell.split("|", 1)
            if (cell_arm, cell_stat) != (arm, stat):
                continue
            sel = test_pos == pos
            observed[cell] = SDD.score_bank(bank[sel], y_te[sel])[SDD.PRIMARY_METRIC]
    audit = SDD.check_reproduction(reference, fold.label, observed)
    audit["seconds"] = round(time.time() - t0, 1)
    log.info("[W6d-B] fold %s reproduction control: %s (%.1fs)", fold.label,
             "ALL 7 REPRODUCE" if audit["all_reproduce"] else "MISMATCH — RUN INVALID",
             audit["seconds"])
    return audit


# ── One fold: every construction per licensed stat, scored per licensed cell ────────────────────
def run_fold(fold: WP.Fold, feat: pd.DataFrame, cells: list[str]) -> dict:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    test_pos = test["position"].to_numpy()
    cells_out: dict[str, dict] = {}
    stats = sorted({c.split("|", 1)[1] for c in cells})

    for stat in stats:
        cls = SDD.stat_class(stat)
        pos_for_stat = [c.split("|", 1)[0] for c in cells if c.split("|", 1)[1] == stat]
        t_stat = time.time()
        y_tr, y_te = SDD._y(train, stat), SDD._y(test, stat)

        banks: dict[str, np.ndarray] = {}
        for arm in SDD.FAMILY[cls]:
            banks[arm] = SDD.arm_fn(arm)(train, test, FEATURES, stat)
        clim = EM.climatology_bank(y_tr, train["position"].to_numpy())
        banks["inc_climatology"] = EM.apply_bank199(np.zeros(len(test)), test_pos, clim)
        if "inc_head_bank" in SDD.FOILS[cls]:
            banks["inc_head_bank"], _ = EM.inc_head_bank(train, test, FEATURES, stat)
        deg_base = banks.get("inc_head_bank", banks["inc_climatology"])
        banks["nihilist_zero"] = EM.anchor_nihilist(len(test))
        banks["zero_width"] = EM.anchor_zero_width(deg_base)
        banks["max_width"] = EM.anchor_max_width(deg_base)
        # the permuted anchor runs the class's declared arm's IDENTICAL code path on labels
        # permuted within (position, global week)
        perm_arm = SDD.PERMUTED_FORM[cls]
        train_perm = train.copy()
        train_perm[stat] = SDD.permute_stat_within_pos_week(train, stat)
        banks[f"permuted_{perm_arm}"] = SDD.arm_fn(perm_arm)(train_perm, test, FEATURES, stat)
        for form in ("marginal", *(SDD.ARM_FORM[a] for a in SDD.FAMILY[cls])):
            orc, mat = SDD.ORACLE_PAIRS[form]
            banks[orc] = SDD.oracle_fn(form)(test, FEATURES, stat, fold.label)
            banks[mat] = SDD.matched_fn(form)(train, test, FEATURES, stat)
        assert set(banks) == set(SDD.bakeoff_labels(cls)), "fold banks drifted from the field"

        for p in pos_for_stat:
            sel = test_pos == p
            scores = {lab: SDD.score_bank(b[sel], y_te[sel]) for lab, b in banks.items()}
            cells_out[SDD.cell_key(p, stat)] = {"scores": scores, "stat_class": cls}
        log.info("[W6d-B] fold %s stat %s (%s) in %.1fs", fold.label, stat, cls,
                 time.time() - t_stat)
    log.info("[W6d-B] fold %s complete in %.1fs (%d cells)", fold.label, time.time() - t0,
             len(cells_out))
    return {"label": fold.label, "n_test": int(len(test)), "cells": cells_out}


# ── Verdict layer (derived, shared with --rewrite-report) ───────────────────────────────────────
def derive_verdict_layer(out: dict) -> dict:
    n_folds = out["n_folds"]
    frs = out["fold_results"]
    present = sorted(frs[0]["cells"].keys())
    sels = {c: SDD.select_bakeoff_cell(frs, c, n_folds, NF18.deflate) for c in present}
    count_p = {c: sels[c]["p_one_sided"] for c in present if sels[c]["stat_class"] == "count"}
    event_p = {c: sels[c]["p_one_sided"] for c in present if sels[c]["stat_class"] == "event"}
    fdr = SDD.fdr_two_families(count_p, event_p)
    for c in sels:
        sels[c]["fdr_binding"] = bool(fdr["binding"].get(c, False))
    gates = {c: SDD.compose_gate(sels[c], sels[c]["fdr_binding"]) for c in sels}
    null_states = {c: SDD.classify_null(sels[c], gates[c]["checks"], n_folds) for c in sels}
    null_states = {c: v for c, v in null_states.items() if v is not None}
    sensitivity = {c: SDD.gate_sensitivity(gates[c]["checks"], waived=("dsr_ok",))
                   for c in sels if not gates[c]["ship"]}
    story = SDD.decide_bakeoff_story(gates)
    verdict = {"story": story["headline"],
               "cells": {c: ("SHIP" if gates[c]["ship"]
                             else null_states.get(c, {}).get("state", "NULL"))
                         for c in sorted(gates)},
               "ship_cells": story["ship_cells"],
               "winners": {c: sels[c]["winner"] for c in story["ship_cells"]}}
    return {"selections": sels, "fdr": fdr, "gates": gates, "null_states": null_states,
            "gate_sensitivity_dsr_waived": sensitivity, "story_decision": story,
            "verdict": verdict, "headline": story["headline"]}


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def write_report(out: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    p("# NF-W6d Phase B — the §0.5 bake-off over the Phase-A-licensed cells")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} half-season blocks "
      f"({out['fold_labels'][0]}…{out['fold_labels'][-1]}) · **rows:** {out['n_rows']} · "
      f"**cells:** {len(out.get('selections', {}))} · cell source: {out['cell_source']}")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held**, NF-G0 "
      "staged. FRESH registration (seed 20260817). Per-class atom-aware families (⛔ no linear-"
      "residual / plain-quantile arm and no head+bank foil on the EVENT class — the NF-W6b-C "
      "field-inflation lesson). Coverage is a one-sided FLOOR (NF1.9 (e)); a distribution here is "
      "a calibrated RANGE, never an edge or win-rate claim.")
    p("")
    rep = out["reproduction_control"]
    p(f"## Reproduction control (NF-W2d): **{'ALL FOLDS REPRODUCE — run VALID' if rep['valid'] else 'MISMATCH — RUN INVALID'}**")
    p("")
    p("| fold | all 7 reproduce | worst |abs diff| | seconds |")
    p("|---|---|---|---|")
    for f in rep["folds"]:
        worst = max(f["cells"].values(), key=lambda r: r["abs_diff"])["abs_diff"]
        p(f"| {f['fold']} | {f['all_reproduce']} | {worst} | {f['seconds']} |")
    p("")
    if out.get("invalid"):
        p("⛔ The run is INVALID: no verdict layer was derived. Investigate the served-cell "
          "mismatch (matrix / library / thread determinism) before anything else.")
        path.write_text("\n".join(a))
        return
    p(f"## Verdict: **{out['headline']}**")
    p("")
    p(out["story_decision"]["reason"])
    p("")
    p("## Per-cell contests (winner vs the BINDING foil)")
    p("")
    p("| cell | class | winner | foil | foil CRPS | Δ | Δ% | CI95 | wins | p | PBO | DSR | SR0 | "
      "BH | cov80 | verdict |")
    p("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c in sorted(out["selections"]):
        s = out["selections"][c]
        g = out["gates"][c]
        lo, hi = (s["ci95"] or [None, None])[:2]
        ci = f"[{lo}, {hi}]" if lo is not None else "n/a"
        v = "SHIP" if g["ship"] else out["null_states"].get(c, {}).get("state", "NULL")
        p(f"| {c} | {s['stat_class']} | {s['winner']} | {s['binding_foil']} | "
          f"{s['mean_crps'][s['binding_foil']]} | {s['mean_delta']} | {s['lift_pct_of_foil']} | "
          f"{ci} | {s['fold_wins']}/{out['n_folds']} | {s['p_one_sided']} | {s['pbo']} | "
          f"{s['dsr']} | {s['dsr_mechanism']['sr0_this_field']} | {s['fdr_binding']} | "
          f"{s['coverage']['winner_coverage_80']} | **{v}** |")
    p("")
    p("## Per-cell detail")
    p("")
    for c in sorted(out["selections"]):
        s = out["selections"][c]
        g = out["gates"][c]
        p(f"### {c}")
        p("")
        rows = [{"label": k, "mean_crps": v} for k, v in
                sorted(s["mean_crps"].items(), key=lambda kv: kv[1])]
        p(pd.DataFrame(rows).to_markdown(index=False, floatfmt=".5f"))
        p("")
        p(f"- verdict: {SDD.verdict_sentence(s['winner'], s['binding_foil'], s['mean_delta'], *(s['ci95'] or [None, None]))}")
        p(f"- gates: {json.dumps(g['checks'])}")
        p(f"- anchors: {json.dumps({k: v for k, v in s['anchors'].items() if k != 'oracle_pairs'})}")
        p(f"- per-form oracle/matched pairs: {json.dumps(s['anchors']['oracle_pairs'])}")
        p(f"- DSR mechanism: trial SRs {s['trial_srs']}, {json.dumps(s['dsr_mechanism'])}")
        p(f"- coverage: {json.dumps(s['coverage'])} (one-sided floor — NF1.9 (e))")
        p(f"- atom calibration (report-only): {json.dumps(s['atom_calibration'])}")
        p(f"- PPR points-units (report-only, |weight| {SDD.PPR_WEIGHTS[c.split('|', 1)[1]]}): "
          f"{s['ppr_points_units']}")
        if c in out["null_states"]:
            p(f"- null state: {json.dumps(out['null_states'][c], default=str)}")
        if c in out.get("gate_sensitivity_dsr_waived", {}):
            p(f"- gate sensitivity (DSR waived — NF-D15 (g″)): "
              f"{json.dumps(out['gate_sensitivity_dsr_waived'][c])}")
        p("")
    p("## Pre-registration")
    p("")
    pre = out["preregistration"]
    p(f"- families: {pre['family']}; foils: {pre['foils']}; permuted form: {pre['permuted_form']}; "
      f"banned on EVENT: {list(pre['banned_on_event'])}; declared field sizes: "
      f"{pre['declared_field_size']}.")
    p(f"- gates: the W6b-C ten clauses; PBO<{pre['pbo_max']}; DSR≥{pre['dsr_min']} (DSR-CONV "
      f"forward: anchors never enter trials); BH q={pre['fdr_q']} two families (count/event) own "
      f"AND pooled; coverage floor one-sided; tie eps {pre['tie_eps']}.")
    p(f"- cell list READ from the Phase-A record ({pre['cell_source']}); reproduction control on "
      f"{len(pre['reproduction_cells'])} served cells, byte-identical or INVALID.")
    p("")
    p(f"_Runtime: {out['runtime_seconds']}s · seed {pre['seed']} · matrix key {out['matrix_key']}_")
    path.write_text("\n".join(a))


def main(argv=None) -> int:  # noqa: C901 — orchestration
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-W6d Phase B per-stat bake-off")
    ap.add_argument("--smoke", action="store_true", help="2 folds; artifacts suffixed _smoke")
    ap.add_argument("--cells", default=None,
                    help="comma-separated cell override — a harness PATH PROOF (suffixed "
                         "_cells); the decision run reads the Phase-A record")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--rewrite-report", action="store_true")
    args = ap.parse_args(argv)
    suffix = ("_smoke" if args.smoke else "") + ("_cells" if args.cells else "")
    json_path = _REPORT_DIR / f"nf_w6d_stat_bakeoff{suffix}.json"

    if args.rewrite_report:
        out = json.loads(json_path.read_text())
        if out.get("invalid"):
            raise SystemExit("record is INVALID (reproduction control failed) — nothing to derive")
        before = dict(out.get("verdict", {}))
        out.update(derive_verdict_layer(out))
        moved = {k: (before.get(k), v) for k, v in out["verdict"].items() if before.get(k) != v}
        if moved:
            out["verdict_corrected_from"] = before
            log.warning("VERDICT MOVED on re-derivation: %s", json.dumps(moved, default=str))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        json_path.write_text(json.dumps(out, indent=2, default=float))
        write_report(out, _REPORT_DIR / f"nf_w6d_stat_bakeoff{suffix}.md")
        print(json.dumps({"verdict": out["verdict"], "moved": moved}, indent=2, default=str))
        return 0

    if args.cells:
        cells = [c.strip() for c in args.cells.split(",") if c.strip()]
        bad = [c for c in cells if c not in SDD.cells()]
        if bad:
            raise SystemExit(f"--cells outside the declared map: {bad}")
        cell_source = f"--cells override (PATH PROOF, not a decision artifact): {cells}"
        log.warning("⚠️ %s", cell_source)
    else:
        cells = licensed_cells_from_gate()
        cell_source = f"Phase-A record {GATE_RECORD.name} licensed_cells"
    if not cells:
        raise SystemExit("no licensed cells — Phase A licensed nothing; nothing to bake off")

    t_start = time.time()
    feat, pit_audit, attach = W6DA.build_matrix_w6d(SEASONS, rebuild_cache=args.rebuild_cache)
    folds = WP.build_folds(feat)
    if args.smoke:
        folds = folds[-2:]
    n_folds = len(folds)
    reference = SDD.reproduction_reference(W6B_RECORD, W6BC_RECORD, dict(SDS.SERVED_CELLS_FROM_W6B),
                                           dict(SDS.SERVED_CELLS_FROM_W6BC))
    log.info("NF-W6d-B: %d folds over %d player-weeks; cells %s", n_folds, len(feat), cells)

    frs, repro = [], []
    for f in folds:
        audit = reproduce_served_cells(f, feat, reference)
        repro.append(audit)
        if not audit["all_reproduce"]:
            out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "story": SDD.STORY, "phase": "B", "smoke": bool(args.smoke),
                   "invalid": True, "cell_source": cell_source,
                   "reproduction_control": {"valid": False, "folds": repro},
                   "n_folds": n_folds, "fold_labels": [x.label for x in folds],
                   "n_rows": int(len(feat)), "runtime_seconds": round(time.time() - t_start, 1)}
            _REPORT_DIR.mkdir(parents=True, exist_ok=True)
            json_path.write_text(json.dumps(out, indent=2, default=float))
            write_report(out, _REPORT_DIR / f"nf_w6d_stat_bakeoff{suffix}.md")
            log.error("RUN INVALID — a served cell did not reproduce on fold %s: %s", f.label,
                      json.dumps(audit["cells"], default=str))
            return 2
        frs.append(run_fold(f, feat, cells))

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": SDD.STORY, "phase": "B", "smoke": bool(args.smoke), "invalid": False,
        "cell_source": cell_source, "cells": cells,
        "runtime_seconds": round(time.time() - t_start, 1),
        "selection_metric": SDD.PRIMARY_METRIC,
        "n_folds": n_folds, "fold_labels": [f.label for f in folds], "n_rows": int(len(feat)),
        "matrix_key": W6DA.w6d_matrix_key(SEASONS), "pit_audit": pit_audit,
        "attach_audit": attach,
        "reproduction_control": {"valid": True, "folds": repro,
                                 "reference": {c: {"record": r["record"], "winner": r["winner"]}
                                               for c, r in reference.items()}},
        "preregistration": {
            "family": {k: list(v) for k, v in SDD.FAMILY.items()},
            "foils": {k: list(v) for k, v in SDD.FOILS.items()},
            "permuted_form": dict(SDD.PERMUTED_FORM), "banned_on_event": dict(SDD.BANNED_ON_EVENT),
            "declared_field_size": dict(SDD.DECLARED_FIELD_SIZE),
            "oracle_pairs": {k: list(v) for k, v in SDD.ORACLE_PAIRS.items()},
            "arm_form": dict(SDD.ARM_FORM), "degenerates": list(SDD.DEGENERATES),
            "pbo_max": SDD.PBO_MAX, "dsr_min": SDD.DSR_MIN, "fdr_q": SDD.FDR_Q,
            "coverage_floor": SDD.COVERAGE_FLOOR, "coverage_block_se": SDD.COVERAGE_BLOCK_SE,
            "tie_eps": SDD.TIE_EPS_CRPS, "ppr_weights": dict(SDD.PPR_WEIGHTS),
            "cell_source": cell_source, "reproduction_cells": list(SDS.SERVED_CELLS),
            "features": FEATURES, "seed": SDD._SEED, "knn_k": SDD.KNN_K,
        },
        "fold_results": frs,
    }
    out.update(derive_verdict_layer(out))
    if args.smoke:
        bad = {c: [k for k, v in out["selections"][c]["anchors"].items()
                   if k in ("nihilist_loses", "zero_width_loses", "max_width_loses") and not v]
               for c in out["selections"]}
        bad = {c: ks for c, ks in bad.items() if ks}
        if bad:
            raise SystemExit(f"POSITIVE CONTROL FAILED — degenerate anchors do not lose: {bad}")
        log.info("positive control OK: all degenerates lose in every scored cell")

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, default=float))
    write_report(out, _REPORT_DIR / f"nf_w6d_stat_bakeoff{suffix}.md")
    log.info("verdict: %s (%.1fs)", out["headline"], out["runtime_seconds"])
    print(json.dumps({"verdict": out["verdict"], "runtime_seconds": out["runtime_seconds"]},
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
