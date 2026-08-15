"""run_nf_w6c_serve_stat_distributions.py — NF-W6c: build the served per-stat distributions.

Fits the SIX NF-W6b SHIP cells fresh on full train through the identical pinned code path
(`stat_distribution_serving` dispatches into `stat_distributions.arm_*`; nothing is re-derived
here) and writes the served 199-level artifact plus its manifest.

⛔ NO BAKE-OFF, NO SELECTION, NO GATE. NF-W6b's verdicts are settled; this runner serves them.
The realized-label readout it prints is a SERVING SMOKE — it shows a fresh full-train fit lands in
family with the certified record, so a wiring defect is visible. A number that moves is a bug to
investigate, never a verdict to revise (E2.1-r).

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD: writes LOCAL artifacts only. There is no
`--publish`, no S3 client and no boto3 import in this file, by design — the weekly serving path
does not exist yet (NF-C6 Phase 2) and a publish flag that cannot legally be used is a loaded gun
(the documented-but-never-set class). Governance staging is a separate script,
`run_nf_w6c_stage_registry.py`.

RUN (OPERATOR — LAPTOP; reads the S3 NFL lake read-only, writes local artifacts):

    # smoke: the full path on a short train window, artifacts suffixed _smoke (~1 min)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6c_serve_stat_distributions --smoke

    # the real build — full train through gw-1, serving the most recent completed week (>2 min)
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w6c_serve_stat_distributions
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
    run_nf_w6_efficiency_marginals as W6R,
)

log = logging.getLogger("nfl.fantasy.nf_w6c")

_FANTASY_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy"
_REPORT_DIR = _FANTASY_DIR / "ablation_results"
_ARTIFACT_DIR = _FANTASY_DIR / "artifacts"
RECORD_JSON = _PROJECT_ROOT / SDS.RECORD_RELPATH
SEASONS = W6R.SEASONS
#: `--smoke` trains on the most recent SMOKE_TRAIN_WEEKS global weeks only — a PATH PROOF that the
#: dispatch, the representation contract and the report all run end to end. ⛔ Its artifact is NOT
#: servable (a short train is a different fit) and is suffixed `_smoke` so it cannot be mistaken
#: for one.
SMOKE_TRAIN_WEEKS = 36


def resolve_serve_gw(feat: pd.DataFrame, requested: int | None) -> int:
    """The week to serve. Default = the most recent global week in the matrix.

    ⚠️ That week's labels are REALIZED, which is exactly what makes the serving smoke checkable —
    and exactly why the train mask is `gw < serve_gw`: the fit never sees the served week."""
    gws = pd.to_numeric(feat["gw"], errors="coerce")
    if requested is None:
        return int(gws.max())
    if not (gws == int(requested)).any():
        raise SystemExit(f"--serve-gw {requested} has no rows in the matrix "
                         f"(range {int(gws.min())}…{int(gws.max())})")
    return int(requested)


def build(feat: pd.DataFrame, serve_gw: int, *, smoke: bool) -> tuple[pd.DataFrame, dict]:
    """Fit + emit. Returns (served frame, provenance)."""
    containment = SDS.assert_serving_train_is_a_superset(feat, serve_gw)
    train_mask = SDS.serving_train_mask(feat, serve_gw)
    if smoke:
        gw = pd.to_numeric(feat["gw"], errors="coerce").to_numpy()
        train_mask = train_mask & (gw >= serve_gw - SMOKE_TRAIN_WEEKS)
    train = feat.loc[train_mask].reset_index(drop=True)
    serve = feat.loc[(pd.to_numeric(feat["gw"], errors="coerce") == serve_gw).to_numpy()
                     ].reset_index(drop=True)
    if serve.empty:
        raise SystemExit(f"no rows at gw={serve_gw} — nothing to serve")

    log.info("NF-W6c: fitting %d cells (%d distinct arm×stat fits) on %d train rows → %d serve "
             "rows at gw=%d%s", len(SDS.SERVED_CELLS), len(SDS.served_fit_keys()), len(train),
             len(serve), serve_gw, " [SMOKE]" if smoke else "")
    t0 = time.time()
    frame, notes = SDS.serve_frame(train, serve)
    log.info("NF-W6c: served %d rows across %d cells in %.1fs", len(frame),
             frame["cell"].nunique(), time.time() - t0)
    return frame, {
        "serve_gw": serve_gw,
        "serve_season": int(serve["season"].iloc[0]), "serve_week": int(serve["week"].iloc[0]),
        "n_train_rows": int(len(train)), "n_serve_player_weeks": int(len(serve)),
        "train_containment": containment, "fit_notes": notes,
        "fit_seconds": round(time.time() - t0, 1),
        "smoke_train_weeks": SMOKE_TRAIN_WEEKS if smoke else None,
    }


def serving_smoke(frame: pd.DataFrame, serve: pd.DataFrame, reference: dict) -> dict:
    """Score each served cell against its realized labels and set it beside the record.

    ⛔ NOT A GATE (see the module docstring). Reported so a wiring defect — a mis-sliced cell, a
    dropped tail, a bank that lost its atom — is VISIBLE instead of silently served."""
    out: dict[str, dict] = {}
    for cell, rows in frame.groupby("cell", sort=True):
        pos, stat = str(cell).split("|", 1)
        sel = serve.loc[serve["position"].astype(str) == pos].reset_index(drop=True)
        y = pd.to_numeric(sel[stat], errors="coerce").fillna(0.0).to_numpy(float)
        bank = np.vstack(rows["quantiles"].to_numpy())
        scored = SDS.readout(bank, y)
        ref = reference.get(str(cell), {})
        out[str(cell)] = {
            "n": scored["n"],
            "fresh": {k: round(float(scored[k]), 4)
                      for k in ("crps_q199", "coverage_80", "pred_p0", "real_p0")},
            "nf_w6b_record": ref,
            "note": ("SERVING SMOKE — in-family check on ONE week; ⛔ never a gate. The record's "
                     "figures pool 8 half-season folds, so a single week differs by sampling "
                     "alone; only a structural break (a dead atom, a collapsed band, a "
                     "wrong-form fit) is a finding here."),
        }
    return out


def _md(cell: str) -> str:
    """Cell keys are `POS|stat` — the pipe MUST be escaped or every table row it appears in
    silently gains a phantom column and the report renders wrong."""
    return str(cell).replace("|", r"\|")


def write_report(payload: dict, path: Path) -> None:  # noqa: C901 — a report, not logic
    a: list[str] = []
    p = a.append
    man, prov = payload["representation"], payload["provenance"]
    p("# NF-W6c — the NF-W6b per-stat distributions wired onto the served raw line")
    p("")
    p(f"**Generated:** {payload['generated_at']} · **serve:** {prov['serve_season']} wk "
      f"{prov['serve_week']} (gw {prov['serve_gw']}) · **served rows:** {payload['n_rows']} "
      f"across {len(man['cells'])} cells · **train rows:** {prov['n_train_rows']}"
      + (" · ⚠️ **SMOKE**" if payload["smoke"] else ""))
    p("")
    p("> ⚖️ **Edge-independent projection product** — `best_alpha = 0`, **deploy-held**. This "
      "story WIRES an already-certified result: NF-W6b's six SHIP cells are fitted fresh on full "
      "train through the identical pinned code path and emitted in the served 199-level "
      "representation. ⛔ No bake-off, no selection, no gate, no re-reading of a settled verdict. "
      "The distributions are honest predictive UNCERTAINTY (a quantile bank and its P(0)); they "
      "make no edge, ROI or win-rate claim. The points hurdle champion (total fantasy points) is "
      "UNTOUCHED — these sit beside it on the raw line.")
    p("")
    p("## Served cells (cell → the NF-W6b winning form → the pinned constructing function)")
    p("")
    p("| cell | form | constructing function | serve rows | P(0) served | q10 | q50 | q90 |")
    p("|---|---|---|---|---|---|---|---|")
    for cell, s in sorted(payload["cell_summary"].items()):
        p(f"| {_md(cell)} | {man['cells'][cell]} | `SD.arm_{man['cells'][cell]}` | {s['n']} | "
          f"{s['p_zero_mean']} | {s['q10_mean']} | {s['q50_mean']} | {s['q90_mean']} |")
    p("")
    p("## Serving smoke — fresh full-train fit vs the NF-W6b record (⛔ NEVER a gate)")
    p("")
    p("A single week against a record that pools 8 half-season folds: these differ by sampling "
      "alone. What this table is FOR is the structural break — a dead zero atom, a collapsed "
      "band, a cell served by the wrong form — which is what a wiring defect looks like.")
    p("")
    p("| cell | n | CRPS fresh | CRPS record | cov80 fresh | cov80 record | P(0) fresh | "
      "P(0) record | realized P(0) |")
    p("|---|---|---|---|---|---|---|---|---|")
    for cell, s in sorted(payload["serving_smoke"].items()):
        f, r = s["fresh"], s["nf_w6b_record"]
        p(f"| {_md(cell)} | {s['n']} | {f['crps_q199']} | {r.get('crps_q199', '—')} | "
          f"{f['coverage_80']} | {r.get('coverage_80', '—')} | {f['pred_p0']} | "
          f"{r.get('pred_p0', '—')} | {f['real_p0']} |")
    p("")
    p("## The served representation (the consumer contract)")
    p("")
    p("```json")
    p(json.dumps({k: v for k, v in man.items() if k != "features"}, indent=2))
    p("```")
    p("")
    p("## Provenance")
    p("")
    p(f"- matrix: the NF-W6 certified build (`build_matrix_w6`, cache key "
      f"`{payload['matrix_key']}`) — the NF-W0a PIT gate ran on load: "
      f"{payload['pit_audit']['weeks_checked']} weeks / "
      f"{payload['pit_audit']['records_checked']} records, "
      f"{payload['pit_audit']['rows_dropped']} rows dropped.")
    c = prov["train_containment"]
    p(f"- serving train ⊇ validated fold train, PROVED at this boundary: {c['n_serving_train']} "
      f"serving-train rows vs {c['n_fold_train']} in NF-W6b's purged fold train "
      f"(+{c['extra_rows_vs_fold_train']}; purge = {c['purge_weeks']} weeks). Serving with MORE "
      f"data than was certified is the safe direction; the containment is measured, not asserted.")
    p(f"- features: the champion set, {len(man['features'])} columns (⛔ no new features — the "
      f"NF-W6b prereg constraint carries to serving).")
    p(f"- withheld NULL cells (⛔ not served): {list(man['withheld_null_cells'])} — RB "
      f"receiving_yards is PM Decision B (calendar-bound re-test), RB rushing_tds is PM Decision "
      f"C (deferred NF-W6b-C, a FRESH atom-aware family).")
    p(f"- CLOSED cells (⛔ re-opening needs a different mechanism): {list(man['closed_cells'])}.")
    art = payload.get("built_artifact") or {}
    p(f"- built artifact: `{art.get('path')}` — {art.get('rows')} rows, {art.get('bytes')} bytes, "
      f"sha256 `{art.get('sha256')}` (gitignored; this manifest is what the registry pins).")
    p("")
    p("## Deploy hold — why nothing publishes")
    p("")
    for b in SDS.PROMOTE_BLOCKERS:
        p(f"- {b}")
    p("")
    p(f"_Runtime: {payload['runtime_seconds']}s · fit {prov['fit_seconds']}s · "
      f"served_version `{man['served_version']}`_")
    path.write_text("\n".join(a))


def main(argv=None) -> int:
    import warnings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    ap = argparse.ArgumentParser(description="NF-W6c served per-stat distributions")
    ap.add_argument("--smoke", action="store_true",
                    help=f"path proof: train on the last {SMOKE_TRAIN_WEEKS} global weeks only; "
                         f"artifacts suffixed _smoke and NOT servable")
    ap.add_argument("--serve-gw", type=int, default=None,
                    help="global week to serve (default: the most recent in the matrix)")
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="regenerate the .md from the stored manifest — no refit (NF-W6b idiom)")
    args = ap.parse_args(argv)
    suffix = "_smoke" if args.smoke else ""
    t_start = time.time()

    if args.rewrite_report:
        json_path = _REPORT_DIR / f"nf_w6c_served_stat_distributions{suffix}.json"
        payload = json.loads(json_path.read_text())
        write_report(payload, _REPORT_DIR / f"nf_w6c_served_stat_distributions{suffix}.md")
        log.info("report re-rendered from %s (no refit)", json_path.name)
        return 0

    feat, pit_audit, _ = W6R.build_matrix_w6(SEASONS, rebuild_cache=args.rebuild_cache)
    serve_gw = resolve_serve_gw(feat, args.serve_gw)
    frame, provenance = build(feat, serve_gw, smoke=args.smoke)
    serve = feat.loc[(pd.to_numeric(feat["gw"], errors="coerce") == serve_gw).to_numpy()
                     ].reset_index(drop=True)

    _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    parquet_path = _ARTIFACT_DIR / f"nf_w6c_served_stat_distributions{suffix}.parquet"
    frame.to_parquet(parquet_path, index=False)
    raw = parquet_path.read_bytes()

    cell_summary = {
        str(cell): {"n": int(len(g)),
                    "p_zero_mean": round(float(g["p_zero"].mean()), 4),
                    "q10_mean": round(float(g["q10"].mean()), 3),
                    "q50_mean": round(float(g["q50"].mean()), 3),
                    "q90_mean": round(float(g["q90"].mean()), 3)}
        for cell, g in frame.groupby("cell", sort=True)}

    payload = {
        "story": SDS.STORY, "smoke": bool(args.smoke),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runtime_seconds": round(time.time() - t_start, 1),
        "matrix_key": W6R.w6_matrix_key(SEASONS), "pit_audit": pit_audit,
        "n_rows": int(len(frame)),
        "representation": SDS.representation_manifest(),
        "provenance": provenance,
        "cell_summary": cell_summary,
        "serving_smoke": serving_smoke(frame, serve, SDS.record_reference(RECORD_JSON)),
        "promote_blockers": list(SDS.PROMOTE_BLOCKERS),
        "built_artifact": {
            "path": str(parquet_path.relative_to(_PROJECT_ROOT)),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw), "rows": int(len(frame)),
            "note": ("gitignored (a built artifact, never committed). The registry stages THIS "
                     "manifest, which pins the parquet by digest."),
        },
    }
    json_path = _REPORT_DIR / f"nf_w6c_served_stat_distributions{suffix}.json"
    json_path.write_text(json.dumps(payload, indent=2, default=float))
    write_report(payload, _REPORT_DIR / f"nf_w6c_served_stat_distributions{suffix}.md")

    log.info("NF-W6c: %d served rows → %s (%.1fs)", len(frame), parquet_path.name,
             payload["runtime_seconds"])
    print(json.dumps({"served_version": SDS.SERVED_VERSION, "cells": list(SDS.SERVED_CELLS),
                      "n_rows": payload["n_rows"], "serve_gw": serve_gw,
                      "smoke": payload["smoke"],
                      "runtime_seconds": payload["runtime_seconds"]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
