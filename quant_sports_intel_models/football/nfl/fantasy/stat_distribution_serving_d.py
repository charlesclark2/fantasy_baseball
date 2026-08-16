"""stat_distribution_serving_d.py — NF-W6d: the COMPLETE per-stat distribution substrate on the
served raw line (pure, dispatch-only).

WHAT THIS IS. NF-W6c serves 7 certified cells. NF-W6d completes the substrate to EVERY optimizer-
input (position, stat) cell — 4 positions × 13 weekly stats = 52 — so a per-player fantasy-point
distribution can be assembled for any league's scoring. Each cell is served by exactly ONE of:
  · a NF-W6b / NF-W6b-C SHIP winner (the 7 already served — `stat_distribution_serving`),
  · a NF-W6d Phase-B SHIP winner (read from the Phase-B record, `nf_w6d_stat_bakeoff.json`),
  · a NF-W6d Phase-C CALIBRATED DEFAULT (read from `nf_w6d_defaults.json`) — for the cells with
    no ceiling / a Phase-B null / the withheld W6b cell / the minor channels.
Priority is a SHIP verdict over a default (a bake-off winner beats a default by construction),
and the map is asserted COMPLETE (52 cells, once each) at serve time.

⭐ THE SERVED MAP IS READ FROM THE RECORDS, NOT HAND-TYPED. NF-W6c pinned its cells as constants
guard-tested against the record; here the Phase-B/C records are produced by an operator run AFTER
this module ships, so the map is DERIVED from them at build time — fail-closed: a record that is
absent / a smoke / partial / INVALID / of the wrong phase or story is REFUSED, never served from.
The forms are POINTERS at the certified constructions (`SD.arm_*` / `SDC.arm_count_negbin` /
`SDD.default_climatology`), by identity — no learner is imported here (AST-guarded), no
fit/predict verb reaches this code, and the representation contract (`SDS.assert_served_
representation` / `SDS.encode_bank`) is reused, never re-derived (a second implementation of the
contract is the NF-C0e wrong-key class).

⚖️ EDGE-INDEPENDENT (`best_alpha = 0`) · DEPLOY-HELD · NF-G0 CHALLENGER: publishes nothing,
promotes nothing; every string is a calibrated RANGE, screened against the shared denylist. The
arbitrary-league re-scoring ASSEMBLY (the moment a scorer READS these) is the named follow-on and
triggers the three-implementations parity tax — nothing scores these yet.

Pure module — no lake IO, no S3, no boto3. Runner: `run_nf_w6d_serve_stat_distributions.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import stat_distribution_serving as SDS
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions_d as SDD

STORY = "NF-W6d"
MODEL_FAMILY = SDS.MODEL_FAMILY
REGISTRY_TARGET = SDS.REGISTRY_TARGET            # the same target — this VERSIONS the substrate
SERVED_VERSION = "nfl_fantasy_w6d_v1"

_ABL = "quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
RECORD_RELPATH_GATE = _ABL + "nf_w6d_ceiling_gate.json"
RECORD_RELPATH_BAKEOFF = _ABL + "nf_w6d_stat_bakeoff.json"
RECORD_RELPATH_DEFAULTS = _ABL + "nf_w6d_defaults.json"

SOURCE_W6B = "nf_w6b"
SOURCE_W6BC = "nf_w6b_c"
SOURCE_W6D_SHIP = "nf_w6d_b_ship"
SOURCE_W6D_DEFAULT = "nf_w6d_c_default"

#: cell-form name → the pinned constructing function. ⛔ Every value is a certified arm / default
#: (SD / SDC / SDD attributes or the W6c adapter), by identity — guard-tested.
ARM_DISPATCH_D = {
    **SDS.ARM_DISPATCH,                             # lgbm_quantile_tail / lgbm_hurdle_tail / knn
    "count_negbin": SDD.arm_count_negbin,           # SDC.arm_count_negbin by identity
    "climatology": SDD.default_climatology,
}
FEATURES: list[str] = list(SDS.FEATURES)
ID_COLUMNS = SDS.ID_COLUMNS
SUMMARY_COLUMNS = SDS.SUMMARY_COLUMNS
N_LEVELS = SDS.N_LEVELS


# ── Record readers (fail-closed) ────────────────────────────────────────────────────────────────
def _load_record(path: Path, *, phase: str, allow_path_proof: bool = False) -> dict:
    """`allow_path_proof=True` exists ONLY for the runner's --smoke build (its artifact is suffixed
    _smoke and is not servable/stageable); the default REFUSES path proofs."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"NF-W6d Phase-{phase} record missing: {p} — run the full "
                                f"(non-smoke) Phase-{phase} runner first; the served map is READ "
                                f"from it, never typed")
    rec = json.loads(p.read_text())
    if rec.get("story") != SDD.STORY or rec.get("phase") != phase:
        raise ValueError(f"{p.name}: story/phase {rec.get('story')}/{rec.get('phase')} ≠ "
                         f"{SDD.STORY}/{phase} — refusing")
    is_path_proof = bool(rec.get("smoke") or rec.get("only_stat")
                         or str(rec.get("cell_source", "")).startswith("--cells"))
    if is_path_proof and not allow_path_proof:
        raise ValueError(f"{p.name}: a --smoke / --only-stat / --cells path proof is not a "
                         f"decision record — refusing to serve from it")
    if rec.get("invalid"):
        raise ValueError(f"{p.name}: the record is INVALID (reproduction control failed) — "
                         f"refusing")
    if "verdict" not in rec:
        raise ValueError(f"{p.name}: no verdict layer — refusing")
    return rec


def gate_licensed_cells(gate_path: Path, *, allow_path_proof: bool = False) -> list[str]:
    return list(_load_record(gate_path, phase="A", allow_path_proof=allow_path_proof)
                ["verdict"]["licensed_cells"])


def bakeoff_ship_cells(bakeoff_path: Path, *, allow_path_proof: bool = False) -> dict[str, str]:
    """{cell: winner} for the Phase-B SHIP verdicts."""
    rec = _load_record(bakeoff_path, phase="B", allow_path_proof=allow_path_proof)
    return {c: rec["verdict"]["winners"][c] for c in rec["verdict"]["ship_cells"]}


def default_cells(defaults_path: Path, *, allow_path_proof: bool = False) -> dict[str, dict]:
    """{cell: {"form", "calibration_warning"}} for every Phase-C default cell."""
    rec = _load_record(defaults_path, phase="C", allow_path_proof=allow_path_proof)
    return {c: {"form": rec["decisions"][c]["chosen"],
                "calibration_warning": rec["decisions"][c]["calibration_warning"]}
            for c in rec["verdict"]["defaults"]}


def served_map(gate_path: Path, bakeoff_path: Path, defaults_path: Path, *,
               allow_path_proof: bool = False) -> dict[str, dict]:
    """cell → {"form", "source", "calibration_warning"} for ALL 52 substrate cells.

    Order of precedence: W6b/W6b-C served (7) → W6d-B SHIP → W6d-C default. The Phase-B record
    may be ABSENT only if the Phase-A record licensed NOTHING (then there was no bake-off to run)
    — any other absence refuses. Completeness (52 cells, once each) is asserted."""
    out: dict[str, dict] = {}
    for cell, form in SDS.SERVED_CELLS_FROM_W6B.items():
        out[cell] = {"form": form, "source": SOURCE_W6B, "calibration_warning": None}
    for cell, form in SDS.SERVED_CELLS_FROM_W6BC.items():
        out[cell] = {"form": form, "source": SOURCE_W6BC, "calibration_warning": None}
    licensed = gate_licensed_cells(gate_path, allow_path_proof=allow_path_proof)
    if licensed:
        ships = bakeoff_ship_cells(bakeoff_path, allow_path_proof=allow_path_proof)
    else:
        ships = {}
        if Path(bakeoff_path).exists():
            ships = bakeoff_ship_cells(bakeoff_path, allow_path_proof=allow_path_proof)
    for cell, form in ships.items():
        if cell in out:
            raise ValueError(f"{cell}: a Phase-B SHIP collides with an already-served cell")
        if cell not in licensed:
            raise ValueError(f"{cell}: Phase-B shipped a cell Phase A did not license — refusing")
        out[cell] = {"form": form, "source": SOURCE_W6D_SHIP, "calibration_warning": None}
    for cell, d in default_cells(defaults_path, allow_path_proof=allow_path_proof).items():
        if cell in out:
            continue                                # a SHIP verdict wins over a default
        out[cell] = {"form": d["form"], "source": SOURCE_W6D_DEFAULT,
                     "calibration_warning": d["calibration_warning"]}
    want = set(SDD.substrate_cells())
    have = set(out)
    if have != want:
        raise ValueError(f"served map incomplete: missing {sorted(want - have)}, extra "
                         f"{sorted(have - want)}")
    bad = {c: v["form"] for c, v in out.items() if v["form"] not in ARM_DISPATCH_D}
    if bad:
        raise ValueError(f"served map names forms with no dispatch target: {bad}")
    return {c: out[c] for c in SDD.substrate_cells()}


def fit_keys(smap: dict[str, dict]) -> tuple[tuple[str, str], ...]:
    """Distinct (form, stat) fits — cells sharing a form+stat share ONE fit (an identity: the
    constructions take no position argument; see `SDS.served_fit_keys`)."""
    keys: list[tuple[str, str]] = []
    for cell, v in smap.items():
        key = (v["form"], cell.split("|", 1)[1])
        if key not in keys:
            keys.append(key)
    return tuple(keys)


# ── The served representation (SDS's contract, reused) ──────────────────────────────────────────
def served_rows(serve: pd.DataFrame, bank: np.ndarray, cell: str, form: str, source: str,
                warning: str | None) -> pd.DataFrame:
    SDS.assert_served_representation(bank, cell)
    if len(serve) != len(bank):
        raise ValueError(f"{cell}: {len(serve)} serve rows vs {len(bank)} bank rows — refusing")
    pos, stat = cell.split("|", 1)
    out = serve.loc[:, [c for c in ID_COLUMNS if c in serve.columns]].reset_index(drop=True)
    out.insert(0, "cell", cell)
    out.insert(1, "stat", stat)
    out.insert(2, "form", form)
    out.insert(3, "source", source)
    out.insert(4, "calibration_warning", warning)
    if "position" in out.columns and not (out["position"].astype(str) == pos).all():
        raise ValueError(f"{cell}: served rows carry a position other than {pos}")
    summaries = SDS.encode_bank(bank)
    if tuple(summaries) != SUMMARY_COLUMNS:
        raise ValueError(f"{cell}: encode_bank emits {tuple(summaries)} but the contract "
                         f"declares {SUMMARY_COLUMNS}")
    for name in SUMMARY_COLUMNS:
        out[name] = summaries[name]
    out["quantiles"] = list(np.asarray(bank, dtype=float))
    return out


def serve_banks(train: pd.DataFrame, serve: pd.DataFrame, smap: dict[str, dict],
                features: list[str] | None = None) -> tuple[dict[str, np.ndarray], dict]:
    feats = list(FEATURES if features is None else features)
    bad = set(pd.Series(serve["position"]).astype(str)) - set(SDD.POSITIONS)
    if bad:
        raise ValueError(f"serve frame carries positions outside the modeled set: {sorted(bad)}")
    serve_pos = serve["position"].astype(str).to_numpy()
    banks: dict[str, np.ndarray] = {}
    notes: dict[str, dict] = {}
    for form, stat in fit_keys(smap):
        full, note = ARM_DISPATCH_D[form](train, serve, feats, stat)
        notes[f"{form}|{stat}"] = dict(note or {})
        for cell, v in smap.items():
            pos, cell_stat = cell.split("|", 1)
            if (v["form"], cell_stat) != (form, stat):
                continue
            banks[cell] = np.asarray(full, dtype=float)[serve_pos == pos]
    missing = [c for c in smap if c not in banks]
    if missing:
        raise ValueError(f"no bank produced for {missing} — the dispatch missed a cell")
    return banks, {"fits": notes, "n_fits": len(notes), "n_cells": len(banks)}


def serve_frame(train: pd.DataFrame, serve: pd.DataFrame, smap: dict[str, dict],
                features: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    banks, notes = serve_banks(train, serve, smap, features)
    serve_pos = serve["position"].astype(str).to_numpy()
    frames = [served_rows(serve.loc[serve_pos == cell.split("|", 1)[0]].reset_index(drop=True),
                          bank, cell, smap[cell]["form"], smap[cell]["source"],
                          smap[cell]["calibration_warning"])
              for cell, bank in banks.items()]
    return pd.concat(frames, ignore_index=True), notes


def representation_manifest(smap: dict[str, dict]) -> dict:
    by_source: dict[str, int] = {}
    for v in smap.values():
        by_source[v["source"]] = by_source.get(v["source"], 0) + 1
    base = SDS.representation_manifest()
    return {
        **base, "story": STORY, "served_version": SERVED_VERSION,
        "cells": {c: v["form"] for c, v in smap.items()},
        "cell_sources": {c: v["source"] for c, v in smap.items()},
        "calibration_warnings": {c: v["calibration_warning"] for c, v in smap.items()
                                 if v["calibration_warning"]},
        "n_cells": len(smap), "cells_by_source": by_source,
        "stats": list(SDD.ALL_STATS), "positions": list(SDD.POSITIONS),
        "withheld_null_cells": [], "closed_cells": [],
        "uncertainty_framing": SDD.screen_copy("uncertainty_framing", (
            "honest predictive uncertainty for one player-week stat — a quantile bank and its "
            "P(0), for every scored weekly stat. A calibrated RANGE (a default where no "
            "conditional form earned a lift); not a market comparison and not an edge / ROI / "
            "win-rate claim of any kind.")),
        "follow_on": ("the arbitrary-league re-scoring ASSEMBLY (per-stat distributions → one "
                      "per-player fantasy-point distribution under a league's scoring, with "
                      "cross-stat correlation) — a separate story: it triggers the three-"
                      "implementations parity tax (fantasy_engine / browser TS / Lambda)."),
    }


PROMOTE_BLOCKERS: tuple[str, ...] = (
    *SDS.PROMOTE_BLOCKERS,
    "NF-W6d Phase-C DEFAULT cells are calibrated ranges, not bake-off winners — the assembly "
    "consumer must read `source`/`calibration_warning` and never present a default as a "
    "conditional projection",
)
