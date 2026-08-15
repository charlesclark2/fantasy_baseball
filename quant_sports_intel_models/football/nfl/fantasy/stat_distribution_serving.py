"""stat_distribution_serving.py — NF-W6c: the NF-W6b / NF-W6b-C per-stat distributions on the
served raw line (pure).

THE STORY IN ONE PARAGRAPH. NF-W6b's §0.5 bake-off shipped 6 of 8 per-stat cells: an honest
DISTRIBUTION (quantiles + a correctly-priced P(0)) beats the champion's per-stat point mean by
11.5–22.1% of CRPS on QB passing_tds / passing_yards / rushing_yards, RB rushing_yards, TE
receiving_yards and WR receiving_yards. NF-W6c wired those six. NF-W6c-wire adds a SEVENTH: RB
rushing_tds, which W6b's OWN field could never clear DSR for (an excluded linear-residual arm
inflated the field's cross-trial dispersion), but which NF-W6b-C — a FRESH, coherent, atom-aware
registration under PM Decision C — shipped cleanly (`knn_quantile`, +12.966% CRPS, DSR 1.0). Today
the raw line carries a POINT per stat and cannot express uncertainty at all; this module fits the
seven winning constructions FRESH ON FULL TRAIN through the identical pinned code path and emits
the served 199-level representation, so any league's scoring can eventually be priced off per-stat
distributions.

⭐ WHY THERE IS A FIT HERE AT ALL — the hand-off caveat that shapes the module. Neither NF-W6b nor
NF-W6b-C produced fitted pickles, deliberately: a CV bake-off fits per fold, so what the gates
certified is the CONSTRUCTION + SELECTION, not one serialized object. Serving therefore requires a
fresh full-train fit — and the MH2.1 (b) serve-what-was-validated rule then binds on the FORM: this
module DISPATCHES into `stat_distributions` (`SD.arm_*`) verbatim and re-derives nothing. There is
no second implementation of the hurdle, the quantile bank, the tail, or the mixture here; a
`SERVED_CELLS` entry is a POINTER at the certified function, and `test_nf_w6c_stat_distribution_
serving.py` pins both the winner map and the dispatch against the certifying record — NF-W6b's for
six cells, NF-W6b-C's for RB|rushing_tds (a SEPARATE record: MH2.2 forbids re-scoring W6b's
retired field, so the successor's SHIP verdict is read from its own record, never from a
re-interpretation of W6b's null — W6b's own verdict for this cell stays a null, untouched).

⛔ WHAT THIS MODULE DELIBERATELY DOES NOT DO.
  · It does NOT touch the points hurdle champion (total fantasy points). NF-W6b never tested it
    and never beat it; the per-stat distributions sit BESIDE it on the raw line.
  · It does NOT open the 1 remaining recorded-null cell (RB receiving_yards = the calendar-bound
    re-test, PM Decision B) or the 4 CLOSED TD-NO cells. Both are pinned out and guard-tested.
  · It does NOT select, re-score, re-tune or re-derive anything. The realized-label readout the
    runner prints is a SERVING SMOKE — a well-formedness + in-family check — never a gate and
    never a re-decision (re-reading a shipped verdict off a fresh fit would be the E2.1-r
    inversion).

THE SERVING TRAIN IS A SUPERSET OF THE VALIDATED TRAIN, WHICH IS THE SAFE DIRECTION. NF-W6b's
folds train on `gw <= start_gw - 1 - PURGE_WEEKS` — the 2-week purge is a CV device that makes the
held-out estimate conservative against week-adjacent autocorrelation. At SERVE time the target
week's labels do not exist, so no purge is needed and withholding two weeks of data would serve a
model weaker than the one certified. `serving_train_mask` therefore takes every completed week
(`gw < serve_gw`); `assert_serving_train_is_a_superset` PROVES the containment rather than
asserting it (the claim is mechanical, so it is checked mechanically).

⚖️ EDGE-INDEPENDENT PROJECTION PRODUCT — `best_alpha = 0`, no edge/ROI/win-rate claim anywhere in
what this emits: a quantile bank is honest UNCERTAINTY, and it is framed as that. · DEPLOY-HELD:
this module publishes nothing and promotes nothing. The weekly serving path does not exist yet
(NF-C6 Phase 2), so the artifact lands as an NF-G0 CHALLENGER and no scoring surface consumes it —
which is also why the three-implementations parity tax (fantasy_engine / browser TS / Lambda
scorer) does NOT trigger for this story, and why `betting_ml/tests/test_nf_w6c_stat_distribution_
serving.py` guards that no scorer reads it.

Pure module — no lake IO, no S3, no boto3 (fast-gate import-safe). The runners are
`run_nf_w6c_serve_stat_distributions.py` (build) and `run_nf_w6c_stage_registry.py` (govern).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import efficiency_marginals as EM
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions as SD
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

# ── Identity ────────────────────────────────────────────────────────────────────────────────────
STORY = "NF-W6c"
#: The NF-G0 registry coordinates. ⚠️ `weekly_projection` is a DIFFERENT target (NF-W2b's staged
#: points challenger) — per-stat distributions version apart from the points model, so they get
#: their own target rather than sharing a version string that would make one unrepresentable.
MODEL_FAMILY = "nfl_fantasy"
REGISTRY_TARGET = "weekly_stat_distribution"
SERVED_VERSION = "nfl_fantasy_w6c_v1"
#: The certified record this whole module is a pointer at (NF-W6b's 6 cells). Read by the guards,
#: never at serve.
RECORD_RELPATH = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                  "nf_w6b_stat_distributions.json")
#: NF-W6c-wire: the NF-W6b-C fresh-family successor record that ships the 7th cell
#: (RB|rushing_tds) — a SEPARATE §0.5 record from RECORD_RELPATH (MH2.2: nothing is promoted
#: from W6b's retired field; this is a fresh registration, read on its own terms).
RECORD_RELPATH_W6BC = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                       "nf_w6b_c_rb_rush_tds.json")

# ── The served cells: NF-W6b's 6 SHIP verdicts + NF-W6b-C's 1, cell → the winning form ──────────
#: NF-W6b's 6 SHIP verdicts (certified by RECORD_RELPATH).
SERVED_CELLS_FROM_W6B: dict[str, str] = {
    "QB|passing_tds": "knn_quantile",
    "QB|passing_yards": "lgbm_quantile_tail",
    "QB|rushing_yards": "lgbm_hurdle_tail",
    "RB|rushing_yards": "lgbm_hurdle_tail",
    "TE|receiving_yards": "lgbm_hurdle_tail",
    "WR|receiving_yards": "lgbm_hurdle_tail",
}
#: NF-W6b-C's 1 SHIP verdict (certified by RECORD_RELPATH_W6BC — NOT RECORD_RELPATH: W6b's own
#: field never cleared DSR for this cell, and MH2.2 forbids re-scoring that field. The fresh,
#: coherent atom-aware registration cleared DSR (1.0, sr0 1.33 vs W6b's own field's ≈7.32) where
#: W6b's field could not; THAT record, not a re-read of W6b's null, licenses serving it).
SERVED_CELLS_FROM_W6BC: dict[str, str] = {
    "RB|rushing_tds": "knn_quantile",
}
#: ⭐ A CONSTANT (the NF-D16 discipline: everything decidable in advance is pinned, not recomputed
#: at run time) — and guard-pinned against each source record's own `verdict`/`selections`, so a
#: hand edit here that disagrees with what the gates certified fails the fast gate.
SERVED_CELLS: dict[str, str] = {**SERVED_CELLS_FROM_W6B, **SERVED_CELLS_FROM_W6BC}
#: ⛔ Recorded NULL — NOT served. RB receiving_yards is PM Decision B (calendar-bound re-test on
#: the same harness once the 2026 folds exist). RB rushing_tds (PM Decision C) is no longer
#: withheld: NF-W6c-wire moved it from here into SERVED_CELLS once NF-W6b-C's fresh atom-aware
#: family shipped it under NF-G0 governance.
WITHHELD_NULL_CELLS: tuple[str, ...] = ("RB|receiving_yards",)
#: ⛔ CLOSED by NF-W6's measurement — re-opening needs a different MECHANISM, not this wiring.
CLOSED_CELLS: tuple[str, ...] = SD.CLOSED_CELLS

#: The features the certified constructions consume — the champion set, imported (⛔ no new
#: features: the NF-W6b prereg constraint carries to serving).
FEATURES: list[str] = list(WP.FEATURES)

# ── The served representation (the NF-W6b record's pins, imported — never re-typed) ─────────────
#: The 199-level dense grid, 0.005…0.995. ONE source (NF-MARGIN1's), reached through SD.
EVAL_LEVELS: np.ndarray = SD.EVAL_LEVELS
N_LEVELS = int(len(EVAL_LEVELS))
#: The record's consumer contract, verbatim: "consumers read P(0) as the share of grid levels at 0
#: and central intervals by level index (q10/q90 at indices 19/179)". DERIVED by searchsorted so
#: the grid stays the single source; the literal indices are asserted in the guards, not here.
IDX_Q10 = int(np.searchsorted(EVAL_LEVELS, 0.10))
IDX_Q50 = int(np.searchsorted(EVAL_LEVELS, 0.50))
IDX_Q90 = int(np.searchsorted(EVAL_LEVELS, 0.90))
#: A grid quantile at or below this counts as the zero atom (the `EM.score_bank` convention,
#: verbatim — one definition of "priced at zero" across the bake-off and the served artifact).
ATOM_EPS = 1e-9

#: Identity columns carried onto every served row (the matrix's own canonical identity — the
#: NF-W0 resolved `gsis_id`, never a display name: a name is a rendering, not a key).
ID_COLUMNS: tuple[str, ...] = ("gsis_id", "position", "team", "season", "week", "gw")
#: Summary columns DERIVED from the bank (never computed independently — a second computation of
#: q10 would be a second implementation of the contract).
SUMMARY_COLUMNS: tuple[str, ...] = ("p_zero", "q10", "q50", "q90", "mean")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Dispatch — POINTERS at the certified constructions; no construction lives here
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _knn(train: pd.DataFrame, serve: pd.DataFrame, features: list[str],
         stat: str) -> tuple[np.ndarray, dict]:
    """`SD.arm_knn_quantile` returns a bare bank (it fits no calibration slice); the uniform
    (bank, note) shape is this adapter's ONLY job."""
    return SD.arm_knn_quantile(train, serve, features, stat), {"calibration_split": None}


#: cell-winner name → the pinned constructing function. ⛔ Every value is an `SD.arm_*`
#: attribute; the guards prove that (an inline re-implementation could not pass).
ARM_DISPATCH = {
    "lgbm_quantile_tail": SD.arm_lgbm_quantile_tail,
    "lgbm_hurdle_tail": SD.arm_lgbm_hurdle_tail,
    "knn_quantile": _knn,
}


def served_stats() -> tuple[str, ...]:
    """The distinct stats the served cells span, in a stable order."""
    seen: list[str] = []
    for cell in SERVED_CELLS:
        stat = cell.split("|", 1)[1]
        if stat not in seen:
            seen.append(stat)
    return tuple(seen)


def served_fit_keys() -> tuple[tuple[str, str], ...]:
    """The distinct (arm, stat) FITS the six cells require, in a stable order.

    ⭐ Two cells can share ONE fit: `SD.arm_*` is a pure function of (train, serve, features,
    stat) with NO position argument — the position enters only as a model feature and as the
    per-row tail lookup — so QB/RB `rushing_yards` and TE/WR `receiving_yards` are literally the
    same call. Sharing is therefore an identity, not an approximation, and `serve_banks` slices
    each cell's own rows out of the shared result."""
    keys: list[tuple[str, str]] = []
    for cell, arm in SERVED_CELLS.items():
        key = (arm, cell.split("|", 1)[1])
        if key not in keys:
            keys.append(key)
    return tuple(keys)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The serving train/serve split
# ══════════════════════════════════════════════════════════════════════════════════════════════
def serving_train_mask(feat: pd.DataFrame, serve_gw: int) -> np.ndarray:
    """Every completed global week strictly before the serve week.

    No purge: the purge is a CV device (NF-W6b's folds hold out a 2-week gap so the held-out
    estimate cannot ride week-adjacent autocorrelation). At serve time the target week's labels do
    not exist, so there is nothing to leak, and withholding the two most recent weeks would serve
    a model fit on LESS data than the certified one."""
    return (pd.to_numeric(feat["gw"], errors="coerce") < int(serve_gw)).to_numpy(dtype=bool)


def fold_train_mask(feat: pd.DataFrame, serve_gw: int) -> np.ndarray:
    """The NF-W6b FOLD train rule at the same boundary (`WP.build_folds`, verbatim arithmetic) —
    the reference the serving split is proved to contain."""
    return (pd.to_numeric(feat["gw"], errors="coerce")
            <= int(serve_gw) - 1 - WP.PURGE_WEEKS).to_numpy(dtype=bool)


def assert_serving_train_is_a_superset(feat: pd.DataFrame, serve_gw: int) -> dict:
    """PROVE the serving train contains the validated fold train at the same boundary.

    The direction is the whole safety argument (serve with MORE data than was certified, never
    less), so it is measured, not asserted in prose. RAISES on violation, and on an EMPTY fold
    train — a vacuously-satisfied containment is not evidence (NF1.7 (a))."""
    serving, fold = serving_train_mask(feat, serve_gw), fold_train_mask(feat, serve_gw)
    n_fold, n_serving = int(fold.sum()), int(serving.sum())
    if not n_fold:
        raise ValueError(
            f"the NF-W6b fold train is EMPTY at serve_gw={serve_gw} — containment would hold "
            f"vacuously and prove nothing about the serving split (NF1.7 (a)); refusing")
    missing = int((fold & ~serving).sum())
    if missing:
        raise ValueError(
            f"serving train does not contain the validated fold train: {missing} rows are in the "
            f"fold train and NOT in the serving train — the serving fit would see LESS data than "
            f"the certified one; refusing")
    return {"serve_gw": int(serve_gw), "n_serving_train": n_serving, "n_fold_train": n_fold,
            "extra_rows_vs_fold_train": n_serving - n_fold, "purge_weeks": int(WP.PURGE_WEEKS)}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The served representation
# ══════════════════════════════════════════════════════════════════════════════════════════════
def assert_served_representation(bank: np.ndarray, cell: str) -> None:
    """The served contract, fail-closed: an (n, 199) FINITE, MONOTONE quantile bank.

    ⛔ It does NOT sort-and-continue. `EM.score_bank` sorts before scoring (a uniform treatment
    across arms is what makes a bake-off fair), but a served bank that needs sorting is a broken
    construction, and silently repairing it at the serving boundary would hide exactly the defect
    this check exists to catch."""
    b = np.asarray(bank, dtype=float)
    if b.ndim != 2 or b.shape[1] != N_LEVELS:
        raise ValueError(f"{cell}: served bank is {b.shape}, expected (n, {N_LEVELS}) at "
                         f"MC.EVAL_LEVELS — the served representation is pinned by the NF-W6b "
                         f"record")
    if not np.isfinite(b).all():
        raise ValueError(f"{cell}: {int((~np.isfinite(b)).sum())} non-finite values in the served "
                         f"bank — refusing to serve a broken predictive (NF-W3 (b))")
    if b.size and float(np.min(np.diff(b, axis=1))) < -1e-9:
        worst = int(np.argmin(np.diff(b, axis=1).min(axis=1)))
        raise ValueError(f"{cell}: served bank is NOT monotone (worst row {worst}) — the "
                         f"constructions are monotone by construction, so this is a real defect, "
                         f"not something to sort away")


def encode_bank(bank: np.ndarray) -> dict[str, np.ndarray]:
    """The consumer-facing summaries, DERIVED from the bank by the record's own reading rule.

    P(0) = the share of grid levels at zero; q10/q50/q90 = level-index reads; `mean` = the grid
    mean (the quantile-function integral on this uniform grid). ⭐ Nothing here re-computes a
    quantity from features — a summary that disagreed with the bank would be a second, silently
    divergent implementation of the served contract (the NF-C0e wrong-key class)."""
    b = np.asarray(bank, dtype=float)
    return {
        "p_zero": (b <= ATOM_EPS).mean(axis=1),
        "q10": b[:, IDX_Q10],
        "q50": b[:, IDX_Q50],
        "q90": b[:, IDX_Q90],
        "mean": b.mean(axis=1),
    }


def served_rows(serve: pd.DataFrame, bank: np.ndarray, cell: str) -> pd.DataFrame:
    """One served frame for one cell: identity + the 199-level bank + the derived summaries."""
    assert_served_representation(bank, cell)
    if len(serve) != len(bank):
        raise ValueError(f"{cell}: {len(serve)} serve rows vs {len(bank)} bank rows — the slice "
                         f"and the predictive disagree; refusing")
    pos, stat = cell.split("|", 1)
    out = serve.loc[:, [c for c in ID_COLUMNS if c in serve.columns]].reset_index(drop=True)
    out.insert(0, "cell", cell)
    out.insert(1, "stat", stat)
    out.insert(2, "form", SERVED_CELLS[cell])
    if "position" in out.columns and not (out["position"].astype(str) == pos).all():
        raise ValueError(f"{cell}: served rows carry a position other than {pos} — the cell grain "
                         f"is broken")
    summaries = encode_bank(bank)
    # ⭐ SUMMARY_COLUMNS is the DECLARED contract, so it must have a consumer — a column list
    # nothing checks is the NF-C0e wired-≠-invoked shape, and this module argues against exactly
    # that. Reconciled here, so a summary added to one and not the other cannot ship.
    if tuple(summaries) != SUMMARY_COLUMNS:
        raise ValueError(f"{cell}: encode_bank emits {tuple(summaries)} but the served contract "
                         f"declares {SUMMARY_COLUMNS} — the declaration and its producer drifted")
    for name in SUMMARY_COLUMNS:
        out[name] = summaries[name]
    out["quantiles"] = list(np.asarray(bank, dtype=float))
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The fit (dispatch only)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def serve_banks(train: pd.DataFrame, serve: pd.DataFrame,
                features: list[str] | None = None) -> tuple[dict[str, np.ndarray], dict]:
    """Fit every served cell FRESH on `train` and emit its (n_cell, 199) bank over `serve`.

    Returns ({cell: bank}, notes). Each distinct (arm, stat) is dispatched ONCE into the pinned
    `SD.arm_*` over the WHOLE serve frame — byte-identically to how NF-W6b scored it — and each
    cell then takes its own position's rows out of that result."""
    feats = list(FEATURES if features is None else features)
    bad = set(pd.Series(serve["position"]).astype(str)) - set(SD.POSITIONS)
    if bad:
        raise ValueError(f"serve frame carries positions outside the modeled set: {sorted(bad)} — "
                         f"`knots_to_eval` fills per position and would leave those rows "
                         f"uninitialized; refusing")
    serve_pos = serve["position"].astype(str).to_numpy()

    banks: dict[str, np.ndarray] = {}
    notes: dict[str, dict] = {}
    for arm, stat in served_fit_keys():
        full, note = ARM_DISPATCH[arm](train, serve, feats, stat)
        notes[f"{arm}|{stat}"] = dict(note or {})
        for cell, cell_arm in SERVED_CELLS.items():
            pos, cell_stat = cell.split("|", 1)
            if (cell_arm, cell_stat) != (arm, stat):
                continue
            banks[cell] = np.asarray(full, dtype=float)[serve_pos == pos]
    missing = [c for c in SERVED_CELLS if c not in banks]
    if missing:
        raise ValueError(f"no bank produced for {missing} — the dispatch missed a served cell")
    return banks, {"fits": notes, "n_fits": len(notes), "n_cells": len(banks)}


def serve_frame(train: pd.DataFrame, serve: pd.DataFrame,
                features: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """The full served artifact: every cell's rows, concatenated, contract-checked."""
    banks, notes = serve_banks(train, serve, features)
    serve_pos = serve["position"].astype(str).to_numpy()
    frames = [served_rows(serve.loc[serve_pos == cell.split("|", 1)[0]].reset_index(drop=True),
                          bank, cell)
              for cell, bank in banks.items()]
    return pd.concat(frames, ignore_index=True), notes


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Serving smoke readout — ⛔ NEVER a gate, NEVER a re-decision
# ══════════════════════════════════════════════════════════════════════════════════════════════
def readout(bank: np.ndarray, y: np.ndarray) -> dict:
    """Score a served bank against realized labels with the bake-off's OWN reducer (`EM.score_bank`
    — one reducer, refuses a non-finite predictive).

    ⚠️ FRAMING, and it is load-bearing: NF-W6b's verdicts are SETTLED. This readout exists to show
    a fresh full-train fit lands IN FAMILY with the certified record — i.e. that the wiring did not
    silently produce a different object. It re-selects nothing, re-gates nothing, and a number that
    moves is a wiring bug to investigate, never a verdict to revise (re-reading a shipped decision
    off a fresh fit is the E2.1-r inversion)."""
    return EM.score_bank(np.asarray(bank, dtype=float), np.asarray(y, dtype=float))


def record_reference(record_path: Path) -> dict:
    """The NF-W6b record's per-cell reference figures for the served cells (winner, coverage,
    atom) — read from the certified JSON, never re-typed. `sels` is keyed by cell (the W6b
    multi-cell record shape); a cell this record never contested (RB|rushing_tds — that's
    NF-W6b-C's, a different record) is silently absent, not an error."""
    rec = json.loads(Path(record_path).read_text())
    sels = rec["selections"]
    return {cell: {"winner": sels[cell]["winner"],
                   "coverage_80": sels[cell]["coverage"]["winner_coverage_80"],
                   "real_p0": sels[cell]["atom_calibration"]["real_p0"],
                   "pred_p0": sels[cell]["atom_calibration"]["winner_pred_p0"],
                   "crps_q199": sels[cell]["mean_crps"][sels[cell]["winner"]]}
            for cell in SERVED_CELLS if cell in sels}


def record_reference_single_cell(record_path: Path) -> dict:
    """The same reference SHAPE as `record_reference`, read from a single-cell §0.5 record (the
    NF-W6b-C shape: `selection` is one dict, not keyed by cell, because the fresh registration
    only ever contested one). Nothing is re-derived — only re-shaped into the shared contract."""
    rec = json.loads(Path(record_path).read_text())
    sel = rec["selection"]
    cell = sel["cell"]
    if cell not in SERVED_CELLS:
        return {}
    return {cell: {"winner": sel["winner"],
                   "coverage_80": sel["coverage"]["winner_coverage_80"],
                   "real_p0": sel["atom_calibration"]["real_p0"],
                   "pred_p0": sel["atom_calibration"]["winner_pred_p0"],
                   "crps_q199": sel["mean_crps"][sel["winner"]]}}


def all_record_references(record_path: Path, record_path_w6bc: Path) -> dict:
    """The full reference set spanning both certifying records, merged — so a caller (the
    serving smoke) never has to know how many records back the served set."""
    return {**record_reference(record_path), **record_reference_single_cell(record_path_w6bc)}


def representation_manifest() -> dict:
    """What the served bank IS — emitted beside the artifact so a consumer reads the contract from
    the artifact rather than from prose in a docstring."""
    return {
        "story": STORY,
        "served_version": SERVED_VERSION,
        "levels": N_LEVELS,
        "level_grid": "MC.EVAL_LEVELS (0.005…0.995, step 0.005)",
        "level_min": float(EVAL_LEVELS[0]), "level_max": float(EVAL_LEVELS[-1]),
        "monotone": True,
        "zero_atom": (f"P(0) = the share of grid levels at or below {ATOM_EPS} "
                      f"(column `p_zero`)"),
        "index_q10": IDX_Q10, "index_q50": IDX_Q50, "index_q90": IDX_Q90,
        "central_80_interval": "quantiles[index_q10] … quantiles[index_q90]",
        "cells": dict(SERVED_CELLS),
        "withheld_null_cells": list(WITHHELD_NULL_CELLS),
        "closed_cells": list(CLOSED_CELLS),
        "features": list(FEATURES),
        "uncertainty_framing": (
            "honest predictive uncertainty for one player-week stat — a quantile bank and its "
            "P(0). Not a market comparison and not an edge/ROI claim of any kind."),
    }


#: Reasons a promote/publish of this artifact is BLOCKED — recorded in the registry entry so the
#: gate is a fact in the system of record, not a sentence in a PR description.
PROMOTE_BLOCKERS: tuple[str, ...] = (
    "NF-C6 Phase 2 — no weekly serving path exists (the deployed fantasy surface is the SEASON "
    "raw line `projections.json`; there is no weekly endpoint to attach a player-week "
    "distribution to)",
    "NF-G0 promotion review — the ten gates plus a PM decision; NF-W6b promoted nothing and this "
    "story stages, it does not promote",
    "the downstream arbitrary-league re-scoring consumer is a FOLLOW-ON story — the moment a "
    "scorer reads these distributions the three-implementations parity tax (fantasy_engine / the "
    "browser TS scorer / the Lambda scorer) triggers under the merge-gate parity test",
)
