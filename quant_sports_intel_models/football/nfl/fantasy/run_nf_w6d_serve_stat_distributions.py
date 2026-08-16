"""run_nf_w6d_serve_stat_distributions.py — NF-W6d: build the COMPLETE served per-stat
distribution substrate (52 cells) and, with `--stage`, register it as an NF-G0 challenger.

The served map is READ from the three NF-W6d records (Phase A gate → licensed cells; Phase B →
SHIP winners; Phase C → calibrated defaults) plus the 7 NF-W6c/W6c-wire cells, and every cell is
fit FRESH on full train through the pinned dispatch (`stat_distribution_serving_d.ARM_DISPATCH_D`
→ the certified `SD.arm_*` / `SDC.arm_count_negbin` / `SDD.default_climatology`). ⛔ NO BAKE-OFF,
NO SELECTION, NO GATE here. The realized-label readout is a SERVING SMOKE (in-family check), never
a re-decision.

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: writes LOCAL artifacts only — no
`--publish`, no S3 client, no boto3 (a publish flag that cannot legally be used is a loaded gun).
`--stage` writes the registry CHALLENGER entry (`nfl_fantasy_w6d_v1` on `weekly_stat_distribution`)
— inert at serve by construction (`served_entry()` returns champion-status entries only).

RUN (OPERATOR — LAPTOP; reads the S3 NFL lake read-only, writes local artifacts):

    # path proof off the _smoke records (artifact suffixed _smoke — NOT servable, NOT stageable)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6d_serve_stat_distributions --smoke

    # the real build (>2 min) — AFTER the full Phase A / B / C runs have written their records
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6d_serve_stat_distributions
    # then stage the challenger (seconds)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6d_serve_stat_distributions --stage
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

from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    stat_distribution_serving as SDS,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    stat_distribution_serving_d as SDSD,
)
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions_d as SDD  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w6c_serve_stat_distributions as W6CS,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w6d_ceiling_gate as W6DA,
)

log = logging.getLogger("nfl.fantasy.nf_w6d_serve")

_FANTASY_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy"
_REPORT_DIR = _FANTASY_DIR / "ablation_results"
_ARTIFACT_DIR = _FANTASY_DIR / "artifacts"
SEASONS = W6DA.SEASONS
SMOKE_TRAIN_WEEKS = W6CS.SMOKE_TRAIN_WEEKS
ARTIFACT_REL = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                "nf_w6d_served_stat_distributions.json")


def record_paths(suffix: str) -> tuple[Path, Path, Path]:
    def _p(rel: str) -> Path:
        return _PROJECT_ROOT / rel.replace(".json", f"{suffix}.json")
    return (_p(SDSD.RECORD_RELPATH_GATE), _p(SDSD.RECORD_RELPATH_BAKEOFF),
            _p(SDSD.RECORD_RELPATH_DEFAULTS))


def build(feat: pd.DataFrame, serve_gw: int, smap: dict, *, smoke: bool) -> tuple[pd.DataFrame, dict]:
    containment = SDS.assert_serving_train_is_a_superset(feat, serve_gw)
    train_mask = SDS.serving_train_mask(feat, serve_gw)
    if smoke:
        gw = pd.to_numeric(feat["gw"], errors="coerce").to_numpy()
        train_mask = train_mask & (gw >= serve_gw - SMOKE_TRAIN_WEEKS)
        containment = containment | {"applies_to_this_run": False,
                                     "note": f"SMOKE: last {SMOKE_TRAIN_WEEKS} weeks only"}
    else:
        containment = containment | {"applies_to_this_run": True}
    train = feat.loc[train_mask].reset_index(drop=True)
    serve = feat.loc[(pd.to_numeric(feat["gw"], errors="coerce") == serve_gw).to_numpy()
                     ].reset_index(drop=True)
    if serve.empty:
        raise SystemExit(f"no rows at gw={serve_gw} — nothing to serve")
    log.info("NF-W6d: fitting %d cells (%d distinct form×stat fits) on %d train rows → %d serve "
             "rows at gw=%d%s", len(smap), len(SDSD.fit_keys(smap)), len(train), len(serve),
             serve_gw, " [SMOKE]" if smoke else "")
    t0 = time.time()
    frame, notes = SDSD.serve_frame(train, serve, smap)
    return frame, {
        "serve_gw": serve_gw,
        "serve_season": int(serve["season"].iloc[0]), "serve_week": int(serve["week"].iloc[0]),
        "n_train_rows": int(len(train)), "n_serve_player_weeks": int(len(serve)),
        "train_containment": containment, "fit_notes": notes,
        "fit_seconds": round(time.time() - t0, 1),
        "smoke_train_weeks": SMOKE_TRAIN_WEEKS if smoke else None,
    }


def serving_smoke(frame: pd.DataFrame, serve: pd.DataFrame) -> dict:
    """Score each served cell against realized labels — an in-family readout, ⛔ never a gate."""
    out: dict[str, dict] = {}
    for cell, rows in frame.groupby("cell", sort=True):
        pos, stat = str(cell).split("|", 1)
        sel = serve.loc[serve["position"].astype(str) == pos].reset_index(drop=True)
        y = pd.to_numeric(sel[stat], errors="coerce").fillna(0.0).to_numpy(float)
        scored = SDS.readout(np.vstack(rows["quantiles"].to_numpy()), y)
        out[str(cell)] = {"n": scored["n"], "form": str(rows["form"].iloc[0]),
                          "source": str(rows["source"].iloc[0]),
                          "fresh": {k: round(float(scored[k]), 4)
                                    for k in ("crps_q199", "coverage_80", "pred_p0", "real_p0")}}
    return out


def write_report(payload: dict, path: Path) -> None:
    a: list[str] = []
    p = a.append
    p("# NF-W6d — the served per-stat distribution substrate (52 cells)")
    p("")
    p(f"**Generated:** {payload['generated_at']} · smoke: {payload['smoke']} · rows "
      f"{payload['n_rows']} · serve gw {payload['provenance']['serve_gw']} "
      f"({payload['provenance']['serve_season']} wk {payload['provenance']['serve_week']})")
    p("")
    p("> ⚖️ Edge-independent projection product — `best_alpha = 0`, deploy-held, NF-G0 challenger. "
      "Every cell is a calibrated RANGE; `source` says whether it is a bake-off winner "
      "(nf_w6b / nf_w6b_c / nf_w6d_b_ship) or a Phase-C calibrated default (nf_w6d_c_default). "
      "No edge / ROI / win-rate claim.")
    p("")
    rep = payload["representation"]
    p(f"cells by source: {rep['cells_by_source']}; calibration warnings: "
      f"{rep['calibration_warnings'] or 'none'}")
    p("")
    p("| cell | form | source | n | fresh CRPS | cov80 | pred P(0) | real P(0) |")
    p("|---|---|---|---|---|---|---|---|")
    for c, r in payload["serving_smoke"].items():
        f = r["fresh"]
        p(f"| {c} | {r['form']} | {r['source']} | {r['n']} | {f['crps_q199']} | "
          f"{f['coverage_80']} | {f['pred_p0']} | {f['real_p0']} |")
    p("")
    p(f"built artifact: `{payload['built_artifact']['path']}` sha256 "
      f"{payload['built_artifact']['sha256']} ({payload['built_artifact']['rows']} rows)")
    p("")
    p("promote blockers: " + "; ".join(payload["promote_blockers"]))
    path.write_text("\n".join(a))


def stage_entry(registry_path=None) -> dict:
    from betting_ml.governance import publish as P
    from betting_ml.governance import registry as R
    registry_path = registry_path or R._REGISTRY_PATH
    artifact_path = _PROJECT_ROOT / ARTIFACT_REL
    staged_digest = P.digest_file(artifact_path)
    if staged_digest is None:
        raise SystemExit(f"staged manifest missing: {artifact_path} — run the build first")
    manifest = json.loads(artifact_path.read_text())
    if manifest.get("smoke"):
        raise SystemExit("refusing to stage a --smoke manifest")
    rep = manifest["representation"]
    prov = manifest["provenance"]
    lineage = {
        "served_version": SDSD.SERVED_VERSION,
        "base_model_version": "nfl_fantasy_nf_w1_v1",
        "per_cell_form": dict(rep["cells"]), "per_cell_source": dict(rep["cell_sources"]),
        "calibration_warnings": dict(rep["calibration_warnings"]),
        "served_representation": {"levels": SDS.N_LEVELS,
                                  "grid": "MC.EVAL_LEVELS (0.005…0.995, step 0.005)",
                                  "index_q10": SDS.IDX_Q10, "index_q50": SDS.IDX_Q50,
                                  "index_q90": SDS.IDX_Q90,
                                  "zero_atom": "P(0) = the share of grid levels at 0"},
        "feature_bundle": (f"weekly_projection.FEATURES ({len(SDS.FEATURES)} columns) + "
                           f"position code — the champion set; no new features"),
        "matrix_key": manifest["matrix_key"],
        "built_artifact_sha256": manifest["built_artifact"]["sha256"],
        "fallback_artifact_uri": "repo:" + SDS.RECORD_RELPATH.replace(".json", ".md"),
        "validation_report": SDD.screen_copy("validation_report", (
            "NF-W6d completes the per-stat distribution substrate: 52 (position, stat) cells = "
            "the 7 NF-W6b/W6b-C SHIP cells + NF-W6d Phase-B SHIP cells (fresh atom-aware per-class "
            "§0.5 bake-off, seed 20260817, reproduction control on the 7 served cells) + Phase-C "
            "CALIBRATED DEFAULTS (pre-registered order, coverage floor + PIT flatness) for every "
            "cell with no ceiling / a null / a minor channel. Records: nf_w6d_ceiling_gate.md, "
            "nf_w6d_stat_bakeoff.md, nf_w6d_defaults.md. Cells by source: "
            f"{rep['cells_by_source']}. Serve gw {prov['serve_gw']} ({prov['serve_season']} wk "
            f"{prov['serve_week']}), {prov['n_train_rows']} train rows.")),
        "reviewed_by": "operator/PM — NF-W6d closeout (staged, promote blocked)",
        "notes": SDD.screen_copy("notes", (
            "STAGED CHALLENGER (NF-W6d) on the same target as NF-W6c — inert at serve. PROMOTE/"
            "PUBLISH BLOCKED until: " + "; ".join(f"({i}) {b}" for i, b in
                                                 enumerate(SDSD.PROMOTE_BLOCKERS, 1))
            + ". A default cell is a calibrated range, never a conditional projection; the "
            "assembly consumer reads `source`. Edge-independent (best_alpha = 0).")),
    }
    result = P.stage(model_family=SDSD.MODEL_FAMILY, target=SDSD.REGISTRY_TARGET, lineage=lineage,
                     artifact_uri=f"repo:{ARTIFACT_REL}", staged_digest=staged_digest,
                     registry_path=registry_path)
    assert R.served_entry(SDSD.MODEL_FAMILY, SDSD.REGISTRY_TARGET, registry_path) is None, (
        "staging produced a SERVED per-stat entry — the build/publish separation is broken")
    return result.as_dict()


def main(argv=None) -> int:
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-W6d served per-stat distribution substrate")
    ap.add_argument("--smoke", action="store_true",
                    help="path proof off the _smoke records, short train; suffixed _smoke")
    ap.add_argument("--serve-gw", type=int, default=None)
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--stage", action="store_true", help="stage the built manifest (no build)")
    args = ap.parse_args(argv)
    if args.stage:
        out = stage_entry()
        print(json.dumps(out, indent=2, default=str))
        return 0
    suffix = "_smoke" if args.smoke else ""
    t_start = time.time()
    gate_p, bake_p, def_p = record_paths(suffix)
    smap = SDSD.served_map(gate_p, bake_p, def_p, allow_path_proof=bool(args.smoke))
    feat, pit_audit, _ = W6DA.build_matrix_w6d(SEASONS, rebuild_cache=args.rebuild_cache)
    serve_gw = W6CS.resolve_serve_gw(feat, args.serve_gw)
    frame, provenance = build(feat, serve_gw, smap, smoke=args.smoke)
    serve = feat.loc[(pd.to_numeric(feat["gw"], errors="coerce") == serve_gw).to_numpy()
                     ].reset_index(drop=True)
    _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    parquet_path = _ARTIFACT_DIR / f"nf_w6d_served_stat_distributions{suffix}.parquet"
    frame.to_parquet(parquet_path, index=False)
    raw = parquet_path.read_bytes()
    payload = {
        "story": SDSD.STORY, "smoke": bool(args.smoke),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runtime_seconds": round(time.time() - t_start, 1),
        "matrix_key": W6DA.w6d_matrix_key(SEASONS), "pit_audit": pit_audit,
        "n_rows": int(len(frame)),
        "records": {"gate": str(gate_p.name), "bakeoff": str(bake_p.name),
                    "defaults": str(def_p.name)},
        "representation": SDSD.representation_manifest(smap),
        "provenance": provenance,
        "serving_smoke": serving_smoke(frame, serve),
        "promote_blockers": list(SDSD.PROMOTE_BLOCKERS),
        "built_artifact": {"path": str(parquet_path.relative_to(_PROJECT_ROOT)),
                           "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                           "rows": int(len(frame))},
    }
    json_path = _REPORT_DIR / f"nf_w6d_served_stat_distributions{suffix}.json"
    json_path.write_text(json.dumps(payload, indent=2, default=float))
    write_report(payload, _REPORT_DIR / f"nf_w6d_served_stat_distributions{suffix}.md")
    log.info("NF-W6d: %d served rows over %d cells → %s (%.1fs)", len(frame),
             frame["cell"].nunique(), parquet_path.name, payload["runtime_seconds"])
    print(json.dumps({"served_version": SDSD.SERVED_VERSION, "n_cells": len(smap),
                      "cells_by_source": payload["representation"]["cells_by_source"],
                      "n_rows": payload["n_rows"], "serve_gw": serve_gw, "smoke": payload["smoke"],
                      "runtime_seconds": payload["runtime_seconds"]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
