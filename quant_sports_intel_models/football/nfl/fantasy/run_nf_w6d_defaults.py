"""run_nf_w6d_defaults.py — NF-W6d PHASE C: a principled, CALIBRATED DEFAULT distribution for
every substrate cell that has no bake-off winner.

The optimizer (and the frontend range) needs a distribution for EVERY scored stat of EVERY
player — including the cells Phase A found no headroom on, the cells Phase B nulls, the one
withheld W6b cell (RB|receiving_yards, PM Decision B) and the minor channels outside the modeled
map. This runner scores, on the SAME fold axis, the pre-registered default forms in their declared
ORDER for every NON-served substrate cell (45 = 52 − the 7 served) and records the FIRST that is
CALIBRATED — the one-sided coverage floor AND randomized-PIT decile flatness (E2.1-r). ⛔ NO CRPS
contest picks a default (a default is not a selected model); the nihilist is still SCORED against
it (NF-D14). A cell where no form calibrates is emitted with the LAST form and a LOUD warning.

Which cells the served artifact actually takes a default for is decided at SERVE time by
subtraction (a SHIP verdict from W6b / W6b-C / W6d-B wins over a default) — so this record can
be built independently of Phase B's outcome and is complete either way.

RUN (OPERATOR — LAPTOP; reads the S3 NFL lake read-only, writes local artifacts; >2 min):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6d_defaults --smoke
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6d_defaults
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6d_defaults --rewrite-report
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

log = logging.getLogger("nfl.fantasy.nf_w6d_c")

_FANTASY_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy"
_REPORT_DIR = _FANTASY_DIR / "ablation_results"
SEASONS = W6DA.SEASONS
FEATURES = list(WP.FEATURES)


def default_cells() -> tuple[str, ...]:
    """Every substrate cell that is not already served — the set a default may be needed for."""
    return tuple(c for c in SDD.substrate_cells() if c not in SDD.SERVED_CELLS_PRIOR)


# ── One fold: each default form per stat, calibration-scored per cell ───────────────────────────
def run_fold(fold: WP.Fold, feat: pd.DataFrame, cells: tuple[str, ...]) -> dict:
    t0 = time.time()
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    test_pos = test["position"].to_numpy()
    cells_out: dict[str, dict] = {}
    by_stat: dict[str, list[str]] = {}
    for c in cells:
        by_stat.setdefault(c.split("|", 1)[1], []).append(c)
    for stat, stat_cells in sorted(by_stat.items()):
        t_stat = time.time()
        y_te = SDD._y(test, stat)
        forms_needed = sorted({f for c in stat_cells for f in SDD.default_order_for(c)},
                              key=SDD.DEFAULT_FORMS.index)
        banks: dict[str, np.ndarray] = {}
        for form in forms_needed:
            banks[form], _ = SDD.DEFAULT_DISPATCH[form](train, test, FEATURES, stat)
        nihil = EM.anchor_nihilist(len(test))
        for c in stat_cells:
            pos = c.split("|", 1)[0]
            sel = test_pos == pos
            scores: dict[str, dict] = {"nihilist_zero": SDD.score_bank(nihil[sel], y_te[sel])}
            for form in SDD.default_order_for(c):
                scores[form] = SDD.calibration_scores(
                    banks[form][sel], y_te[sel], SDD.pit_rng(fold.label, c, form))
            cells_out[c] = {"scores": scores, "kind": "minor" if c in SDD.minor_cells()
                            else "modeled"}
        log.info("[W6d-C] fold %s stat %s (%d cells, forms %s) in %.1fs", fold.label, stat,
                 len(stat_cells), forms_needed, time.time() - t_stat)
    log.info("[W6d-C] fold %s complete in %.1fs (%d cells)", fold.label, time.time() - t0,
             len(cells_out))
    return {"label": fold.label, "n_test": int(len(test)), "cells": cells_out}


def derive_verdict_layer(out: dict) -> dict:
    frs = out["fold_results"]
    present = sorted(frs[0]["cells"].keys())
    decisions = {c: SDD.decide_default(frs, c) for c in present}
    summary = SDD.summarize_defaults(decisions)
    return {"decisions": decisions, "summary": summary,
            "verdict": {"story": summary["headline"],
                        "defaults": {c: decisions[c]["chosen"] for c in present},
                        "uncalibrated_cells": summary["uncalibrated_cells"]},
            "headline": summary["headline"]}


def write_report(out: dict, path: Path) -> None:
    a: list[str] = []
    p = a.append
    p("# NF-W6d Phase C — calibrated DEFAULT distributions for the no-winner cells")
    p("")
    p(f"**Generated:** {out['generated_at']} · **folds:** {out['n_folds']} "
      f"({out['fold_labels'][0]}…{out['fold_labels'][-1]}) · **rows:** {out['n_rows']} · "
      f"**cells:** {len(out['decisions'])}")
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held**. A "
      "default is chosen by pre-registered ORDER + calibration gates (one-sided coverage floor ∧ "
      f"randomized-PIT max-decile-deviation ≤ {SDD.PIT_MAX_DECILE_DEV}); ⛔ NOT a bake-off "
      "winner, NOT selected on CRPS. The nihilist is scored against every default (NF-D14). A "
      "distribution here is a calibrated RANGE, never an edge or win-rate claim.")
    p("")
    p(f"## Verdict: **{out['headline']}**")
    p("")
    p("| cell | kind | order | chosen | cov80 | PIT max-dev | calibrated | nihilist loses | "
      "CRPS | pred P(0) / real P(0) | warning |")
    p("|---|---|---|---|---|---|---|---|---|---|---|")
    for c in sorted(out["decisions"]):
        d = out["decisions"][c]
        r = d["reads"][d["chosen"]]
        kind = out["fold_results"][0]["cells"][c]["kind"]
        p(f"| {c} | {kind} | {'→'.join(d['order'])} | **{d['chosen']}** | {r['coverage_80']} | "
          f"{r['pit_max_decile_dev']} | {r['calibrated']} | {r['nihilist_loses']} | "
          f"{r['crps_q199']} | {r['pred_p0']} / {r['real_p0']} | "
          f"{d['calibration_warning'] or '—'} |")
    p("")
    p("## Per-cell reads (every form in the order, so the choice is auditable)")
    p("")
    for c in sorted(out["decisions"]):
        d = out["decisions"][c]
        p(f"### {c}")
        p("")
        for f in d["order"]:
            r = d["reads"][f]
            p(f"- `{f}`: cov80 {r['coverage_80']} (floor ok {r['coverage_floor_ok']}, SE "
              f"{r['binomial_se']}, structural {r['structural_expectation']}) · PIT max-dev "
              f"{r['pit_max_decile_dev']} (flat ok {r['pit_flat_ok']}) deciles "
              f"{r['pit_decile_freq']} · CRPS {r['crps_q199']} vs nihilist {r['nihilist_crps']} "
              f"· pred P(0) {r['pred_p0']} vs real {r['real_p0']} · n {r['n_rows']}")
        p("")
    p("## Pre-registration")
    p("")
    pre = out["preregistration"]
    p(f"- order: {pre['default_order']}; PIT max-decile-dev ≤ {pre['pit_max_decile_dev']}; "
      f"coverage floor {pre['coverage_floor']} (one-sided, {pre['coverage_block_se']} SE); "
      f"cells = substrate − served ({pre['n_cells']}).")
    p("")
    p(f"_Runtime: {out['runtime_seconds']}s · seed {pre['seed']} · matrix key {out['matrix_key']}_")
    path.write_text("\n".join(a))


def main(argv=None) -> int:
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-W6d Phase C calibrated defaults")
    ap.add_argument("--smoke", action="store_true", help="2 folds; artifacts suffixed _smoke")
    ap.add_argument("--only-stat", default=None, choices=list(SDD.ALL_STATS),
                    help="one stat's cells — a harness PATH PROOF")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--rewrite-report", action="store_true")
    args = ap.parse_args(argv)
    suffix = ("_smoke" if args.smoke else "") + (
        f"_only_{args.only_stat}" if args.only_stat else "")
    json_path = _REPORT_DIR / f"nf_w6d_defaults{suffix}.json"

    if args.rewrite_report:
        out = json.loads(json_path.read_text())
        before = dict(out.get("verdict", {}))
        out.update(derive_verdict_layer(out))
        moved = {k: (before.get(k), v) for k, v in out["verdict"].items() if before.get(k) != v}
        if moved:
            out["verdict_corrected_from"] = before
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        json_path.write_text(json.dumps(out, indent=2, default=float))
        write_report(out, _REPORT_DIR / f"nf_w6d_defaults{suffix}.md")
        print(json.dumps({"verdict": out["verdict"], "moved": moved}, indent=2, default=str))
        return 0

    t_start = time.time()
    SDD.assert_substrate_is_complete()
    cells = default_cells()
    if args.only_stat:
        cells = tuple(c for c in cells if c.split("|", 1)[1] == args.only_stat)
        log.warning("⚠️ --only-stat %s: PATH PROOF, not a decision artifact", args.only_stat)
    feat, pit_audit, attach = W6DA.build_matrix_w6d(SEASONS, rebuild_cache=args.rebuild_cache)
    folds = WP.build_folds(feat)
    if args.smoke:
        folds = folds[-2:]
    n_folds = len(folds)
    log.info("NF-W6d-C: %d folds; %d default cells", n_folds, len(cells))
    frs = [run_fold(f, feat, cells) for f in folds]
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": SDD.STORY, "phase": "C", "smoke": bool(args.smoke), "only_stat": args.only_stat,
        "runtime_seconds": round(time.time() - t_start, 1),
        "n_folds": n_folds, "fold_labels": [f.label for f in folds], "n_rows": int(len(feat)),
        "matrix_key": W6DA.w6d_matrix_key(SEASONS), "pit_audit": pit_audit,
        "attach_audit": attach,
        "preregistration": {
            "default_order": {k: list(v) for k, v in SDD.DEFAULT_ORDER.items()},
            "pit_max_decile_dev": SDD.PIT_MAX_DECILE_DEV,
            "coverage_floor": SDD.COVERAGE_FLOOR, "coverage_block_se": SDD.COVERAGE_BLOCK_SE,
            "n_cells": len(cells), "cells": list(cells), "seed": SDD._SEED,
            "served_cells_excluded": list(SDD.SERVED_CELLS_PRIOR),
        },
        "fold_results": frs,
    }
    out.update(derive_verdict_layer(out))
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(out, indent=2, default=float))
    write_report(out, _REPORT_DIR / f"nf_w6d_defaults{suffix}.md")
    log.info("verdict: %s (%.1fs)", out["headline"], out["runtime_seconds"])
    print(json.dumps({"verdict": out["verdict"], "runtime_seconds": out["runtime_seconds"]},
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
