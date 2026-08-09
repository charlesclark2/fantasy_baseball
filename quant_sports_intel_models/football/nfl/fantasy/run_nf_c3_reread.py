"""run_nf_c3_reread.py — NF-C3-REREAD: NF-RECAL1's C3 and NF-D21's interval-floor gate, RE-READ
under the CORRECT served band.

⚠️ THIS IS A GATE RE-READ, NOT A BAKE-OFF. No new model, no new arm, no new floor. NF1.9-R proved
(2026-08-08) that the veteran panel's `served_p10`/`served_p90` columns carry the LITERAL emitted
PRE-NF1.9 normal band — frozen so NF1.9's incumbent arm stays reproducible — and NOT the band on the
wire (`knn_norm k300`, `calibrated_per_player`), which covers 0.845 on the 2019–2025 draftable tier
(0.833 full-window) against the panel columns' 0.5046. NF-RECAL1's C3
(`coverage_λ ≥ min(floor, coverage_incumbent)`) read its `coverage_incumbent` — and scored every
arm's shifted band — off those panel columns, so its refusals were computed against a MIS-SPECIFIED
incumbent. This runner recomputes the gate with the band actually on the wire, refit through the
model path, and reports per-arm per-fold PASS/REFUSE at the corrected bar.

⭐ STEP 0 IS THE WHOLE POINT: prove WHICH band is being gated on before gating on it. The incumbent
band here is refit through `season_projection.fit_veteran_band_model` (the served code path) and must
REPRODUCE NF1.9's recorded universe IS80 (160.888, Δ 0.00%) and NF1.9-R's recorded tier readings
(0.8452 tier coverage 2019–2025; 0.5046 for the panel columns) before any gate is read. A `served_*`
COLUMN NAME on a research panel is never again the source of `coverage_incumbent`.

⛔ THE FLOOR IS NOT MOVED (E2.1-r). The bar CHANGES here only because the INCUMBENT term of
`min(floor, coverage_incumbent)` was mis-measured: the corrected incumbent covers MORE, so the bar
RISES from the ~0.50-class to the full 0.80 floor at most positions — a STRICTER gate, not a looser
one. If an arm clears a stricter bar that the mis-specified gate refused it under, that is a finding
about the OLD gate's arm-side band (the shifted PRE-NF1.9 band under-covered), not a loosening.

TWO READS, both from the pre-registered machinery, nothing new invented:
  · READ 1 (the headline) — the arms AS RECORDED (their recorded λ paths, reproduced exactly from
    the as-recorded harness) re-gated on the corrected C3: the served band shifted by each arm's own
    recorded correction, against `min(0.80, coverage_incumbent(served))` per fold per position.
    This answers the only question this story asks: were the refusals correct?
  · READ 2 (disclosure, the B3 escalation input) — the identical pre-registered machinery REPLAYED
    end-to-end with the served band everywhere (λ rules re-derived from corrected in-fold scores and
    corrected admissibility; selection + deflation under the corrected metric). This answers "what
    would NF-RECAL1 have concluded had it held the right band?" ⛔ It ships nothing and selects
    nothing — the successor story (B3, joint level+band) owns any ship decision.

NF-D21's half: its `interval_floors` gate reads the ROOKIE band, refit through the rookie model path
(`NF17.build_folds` + `NF18.run_arm` with `shipped_rookie_cfg()` read off `season_projection`
constants) — NOT a `served_*` panel column. Whether the trap reaches it is MEASURED here, not
assumed: the sweep is reproduced against the recorded JSON, then re-read under the corrected C3
STRUCTURE (`coverage_λ ≥ min(0.80, coverage_λ=0)` per position) so the two stories' gates are
finally the same clause on their own correct incumbents.

⚖️ `best_alpha = 0` — nothing serves either way; the output of this runner is a DECISION RECORD.

RUN ON THE LAPTOP (no Snowflake, no network — reads the cached veteran band panel + merged boards +
rookie pool; a fresh worktree must copy those gitignored artifacts in first):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_c3_reread
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

from quant_sports_intel_models.football.nfl.fantasy import level_recalibration as LR  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import run_nf_recal1_level as R1  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf1_9r_veteran_tier_band as R19,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_interval_ablation as NF17,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_rookie_perposition_ablation as NF18,
)
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_veteran_interval_ablation as VA,
)
from quant_sports_intel_models.football.nfl.fantasy.run_nf_d21_publish import (  # noqa: E402
    floor_sweep,
)

log = logging.getLogger("nfl.fantasy.nf_c3_reread")

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_STEM = "nf_c3_reread"

# ── The recorded figures this runner must REPRODUCE before reading any gate (step 0) ──────────
#: NF1.9's recorded universe IS80 for the served band — the reproduction proof NF1.9-R used.
_NF19_UNIVERSE_IS80 = 160.888
#: NF1.9-R's recorded tier readings (2019–2025): the SERVED band vs the panel's `served_*` columns.
_NF19R_SERVED_TIER_COV_2019_2025 = 0.8452
_NFRECAL1_PANEL_TIER_COV_2019_2025 = 0.5046
#: Reproduction tolerances: the IS80 must match to the displayed digit; coverages to 5e-5.
_IS80_RTOL = 1e-5
_COV_ATOL = 5e-5

_D21_FROM, _D21_TO = 2019, 2025


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STEP 0 — refit the SERVED band through the model path; prove which band is held
# ══════════════════════════════════════════════════════════════════════════════════════════════
def served_band_by_row(years: tuple) -> tuple[pd.DataFrame, dict]:
    """The band ON THE WIRE (`knn_norm k300`), refit per walk-forward fold through the served code
    path, keyed by (target_season, player_id) — plus the row frame the reproduction proofs score.

    ⛔ NEVER the panel's `served_p10`/`served_p90` columns: those carry the PRE-NF1.9 normal band
    (documented in `VET_PANEL_COLS`, proven by NF1.9-R §0) and are exactly the trap this exists to
    close."""
    panel = VA.load_panel()
    folds = VA.build_folds(panel, list(years))
    tier_n = LR.draftable_tier_size()
    inc_cfg = R19.candidate_configs()[0]
    assert inc_cfg["arm"] == "incumbent" and inc_cfg["form"] == "knn_norm" \
        and inc_cfg["k"] == 300, f"the incumbent config drifted: {inc_cfg}"

    parts, lookup = [], {}
    for f in folds:
        got = R19.candidate_band(f, inc_cfg, tier_n)
        if got is None:
            raise SystemExit(f"the served band did not fit for fold {f.year} — a missing incumbent "
                             "is a broken instrument, not a pass (NF1.7 (a)).")
        lo, hi, fell = got
        pid = f.test["player_id"].to_numpy()
        if len(set(zip([f.year] * len(pid), pid))) != len(pid):
            raise SystemExit(f"fold {f.year}: duplicate player_id — the (season, player) key is not "
                             "unique and the served-band join would be ambiguous.")
        for i, p in enumerate(pid):
            lookup[(int(f.year), p)] = (float(lo[i]), float(hi[i]))
        parts.append(pd.DataFrame({
            "year": f.year, "player_id": pid,
            "pos": f.test["position"].astype(str).str.upper().to_numpy(),
            "lo": lo, "hi": hi, "y": f.test_real, "point": f.test_pred, "fell_back": fell,
            "panel_lo": f.served_lo, "panel_hi": f.served_hi,
            "tier": R19.fold_tier_mask(f, tier_n)}))
    return pd.concat(parts, ignore_index=True), lookup


def reproduction_proofs(rows: pd.DataFrame) -> dict:
    """⭐ The step-0 gate: this runner holds the band on the wire, or it stops."""
    universe = NF18.score_rows(rows)
    tier = rows[rows["tier"]].reset_index(drop=True)
    tier_1925 = tier[tier["year"] >= 2019]
    served_cov_1925 = float(np.mean((tier_1925["y"] >= tier_1925["lo"])
                                    & (tier_1925["y"] <= tier_1925["hi"])))
    panel_cov_1925 = float(np.mean((tier_1925["y"] >= tier_1925["panel_lo"])
                                   & (tier_1925["y"] <= tier_1925["panel_hi"])))
    out = {
        "universe_is80": universe["interval_score"],
        "universe_is80_recorded": _NF19_UNIVERSE_IS80,
        "universe_is80_delta_pct": round(
            100.0 * abs(universe["interval_score"] - _NF19_UNIVERSE_IS80) / _NF19_UNIVERSE_IS80, 6),
        "tier_coverage_full_window": round(
            float(np.mean((tier["y"] >= tier["lo"]) & (tier["y"] <= tier["hi"]))), 4),
        "served_tier_coverage_2019_2025": round(served_cov_1925, 4),
        "served_tier_coverage_2019_2025_recorded": _NF19R_SERVED_TIER_COV_2019_2025,
        "panel_column_tier_coverage_2019_2025": round(panel_cov_1925, 4),
        "panel_column_tier_coverage_2019_2025_recorded": _NFRECAL1_PANEL_TIER_COV_2019_2025,
        "incumbent_fallback_frac": round(float(rows["fell_back"].mean()), 4),
        "n_universe": int(len(rows)), "n_tier": int(len(tier)),
    }
    if abs(universe["interval_score"] - _NF19_UNIVERSE_IS80) > _IS80_RTOL * _NF19_UNIVERSE_IS80:
        raise SystemExit(
            f"step-0 REPRODUCTION FAILED: universe IS80 {universe['interval_score']} vs the recorded "
            f"{_NF19_UNIVERSE_IS80} — this runner does NOT hold the served band; no gate may be "
            "read off it (the very defect this story exists to fix).")
    if abs(served_cov_1925 - _NF19R_SERVED_TIER_COV_2019_2025) > _COV_ATOL:
        raise SystemExit(
            f"step-0 REPRODUCTION FAILED: served tier coverage {served_cov_1925:.4f} vs recorded "
            f"{_NF19R_SERVED_TIER_COV_2019_2025} (NF1.9-R §0).")
    if abs(panel_cov_1925 - _NFRECAL1_PANEL_TIER_COV_2019_2025) > _COV_ATOL:
        raise SystemExit(
            f"step-0 REPRODUCTION FAILED: panel-column tier coverage {panel_cov_1925:.4f} vs the "
            f"recorded 0.5046 — the panel columns are not what NF-RECAL1's C3 read, so the "
            "'mis-specified bar' premise itself would not reproduce.")
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF-RECAL1 — the corrected evidence, arms and gate (READ 1 + READ 2)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def substitute_served_band(folds: list[dict], lookup: dict) -> list[dict]:
    """The identical NF-RECAL1 folds with the band COLUMNS replaced by the band on the wire.

    Every downstream function then reads the corrected band through the unchanged pre-registered
    machinery — `score_arm`, `build_fold_evidence`, `coverage_floor_check` — so the corrected read
    cannot quietly diverge from the recorded one in anything but the band."""
    out = []
    for f in folds:
        g = dict(f)
        for key in ("test", "test_universe"):
            d = f[key].copy()
            bands = [lookup.get((int(y), p))
                     for y, p in zip(d["target_season"].astype(int), d["player_id"])]
            if any(b is None for b in bands):
                missing = int(sum(b is None for b in bands))
                raise SystemExit(
                    f"fold {f['year']}/{key}: {missing} row(s) have no refit served band — an "
                    "unmatched row would silently keep the pre-NF1.9 panel band, which is the trap "
                    "this runner exists to close. RAISE, never fall through (NF1.7 (a)).")
            d["served_p10"] = [b[0] for b in bands]
            d["served_p90"] = [b[1] for b in bands]
            g[key] = d
        out.append(g)
    return out


def trimmed_fits(fold: dict) -> dict:
    """Exactly the fitted objects the GATE re-read needs — the candidate form fits (strictly
    in-fold, identical to the recorded run because `fit_form` never sees a band) plus the
    incumbent-coverage term C3 is built on, computed from whatever band the fold carries.

    The peeking ceilings and permutation anchors are NOT refit here: they are METRIC diagnostics the
    recorded run already owns, and this runner re-reads a CONSTRAINT. The degenerate/oracle scrutiny
    set (`oracle_perplayer`, `zero_project`, `pos_median`, `over_scale`, `wide_band`) needs only the
    keys below."""
    tr, te = fold["train"], fold["test"]
    y_tr = tr["real_fp_ppr"].to_numpy(dtype=float)
    pos_tr = tr["position"].to_numpy()
    args_tr = (tr["point"].to_numpy(dtype=float), y_tr, pos_tr,
               tr["proj_games"].to_numpy(dtype=float))
    fits: dict = {}
    for form in LR.FORMS:
        fits[(form, LR.PRIMARY_SPACE)] = LR.fit_form(form, LR.PRIMARY_SPACE, *args_tr)
    fits["_pos_median"] = {q: float(np.median(y_tr[pos_tr == q]))
                           for q in LR.RECALIBRATED_POSITIONS if (pos_tr == q).any()}
    fits["_inc_coverage"] = LR.per_position_coverage(
        te["real_fp_ppr"].to_numpy(dtype=float), te["served_p10"].to_numpy(dtype=float),
        te["served_p90"].to_numpy(dtype=float), te["position"].to_numpy())
    return fits


def score_lambda_grid(folds: list[dict], fits: dict) -> dict:
    """The constant-λ substrate every rule reads, PRIMARY space only (the shippable arms' space)."""
    out: dict = {}
    for form in LR.FORMS:
        out[form] = {}
        for lam in LR.LAMBDA_GRID:
            out[form][float(lam)] = R1.score_arm(
                folds, fits,
                R1.form_adjuster(form, LR.PRIMARY_SPACE, (form, LR.PRIMARY_SPACE),
                                 lambda f, L=lam: L),
                f"{form}·{LR.PRIMARY_SPACE}·λ={lam:g}")
    return out


def build_arms(folds: list[dict], fits: dict, lam_scored: dict, evidence: dict,
               *, lam_paths: dict | None = None) -> tuple[list[dict], dict, dict]:
    """The 11-arm pre-registered field, either replaying each rule's own λ path against the given
    evidence (READ 2) or pinning the RECORDED λ paths (READ 1, `lam_paths`)."""
    incumbent = R1.score_arm(
        folds, fits,
        R1.form_adjuster("pos_const", LR.PRIMARY_SPACE, ("pos_const", LR.PRIMARY_SPACE),
                         lambda f: 0.0),
        "incumbent (NULL)",
        extra={"form": "incumbent", "space": LR.PRIMARY_SPACE, "rule": None,
               "recalibrates": False, "shippable": True, "is_foil": False})
    arms = [incumbent]
    placements = {"incumbent (NULL)": {"holds_out": True, "per_fold": {}, "c2_only": True,
                                       "c3_only": True, "failing_folds": []}}
    paths: dict = {}
    for cfg in [c for c in LR.candidate_configs() if c["form"] != "incumbent"]:
        form, label = cfg["form"], f"{cfg['form']} · {cfg['rule']}"
        if lam_paths is not None:
            lam_map = dict(lam_paths[label])
        else:
            lam_by_fold = R1.rule_lambdas(form, cfg, folds, {form: lam_scored[form]}, evidence)
            lam_map = {y: v["lam"] for y, v in lam_by_fold.items()}
        paths[label] = lam_map
        rec = R1.score_arm(
            folds, fits,
            R1.form_adjuster(form, LR.PRIMARY_SPACE, (form, LR.PRIMARY_SPACE),
                             lambda f, M=lam_map: M[f["year"]]),
            label,
            extra={"key": LR.config_key(cfg), "form": form, "space": LR.PRIMARY_SPACE,
                   "rule": cfg["rule"], "recalibrates": True, "shippable": True,
                   "is_foil": False, "lam_by_fold": lam_map})
        arms.append(rec)
        placements[label] = R1.holds_out(form, lam_map, evidence)
    return arms, placements, paths


def _unrounded_cov(y, p10, p90, positions) -> dict:
    """`per_position_coverage` WITHOUT the 6-dp rounding — the ε-sensitivity's incumbent term."""
    yy = np.asarray(y, dtype=float)
    lo = np.minimum(np.asarray(p10, dtype=float), np.asarray(p90, dtype=float))
    hi = np.maximum(np.asarray(p10, dtype=float), np.asarray(p90, dtype=float))
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    cov = (yy >= lo) & (yy <= hi)
    return {q: (float(cov[pos == q].mean()) if (pos == q).any() else None)
            for q in LR.RECALIBRATED_POSITIONS}


def _cov_check_eps(y, p10, p90, positions, inc: dict) -> dict:
    """⭐ THE ε-TOLERANT C3 — the SENSITIVITY read, never the recorded clause.

    The recorded `coverage_floor_check` computes `need = ceil(round(inc, 6) · n)`, so when the 6-dp
    rounding rounds the incumbent's own coverage UP, an arm whose coverage EQUALS the incumbent's —
    including λ = 0, which IS the incumbent — fails by exactly one row. That artifact is in the
    RECORDED NF-RECAL1 run too (its λ=0 arms 'fail C3' on 6 of 7 folds), where it was cosmetic; here
    it is re-read with `need = ceil(bind·n − 1e-9)` on the UNROUNDED incumbent so the equality
    boundary holds, and the report shows what the artifact did and did not decide."""
    yy = np.asarray(y, dtype=float)
    lo = np.minimum(np.asarray(p10, dtype=float), np.asarray(p90, dtype=float))
    hi = np.maximum(np.asarray(p10, dtype=float), np.asarray(p90, dtype=float))
    pos = np.asarray([str(q).upper() for q in np.asarray(positions, dtype=object)], dtype=object)
    covered = (yy >= lo) & (yy <= hi)
    per, breaches = {}, []
    for q in LR.RECALIBRATED_POSITIONS:
        sel = pos == q
        n = int(sel.sum())
        if n == 0:
            continue
        bind = min(float(LR.COVERAGE_FLOOR), float(inc[q])) if inc.get(q) is not None \
            else float(LR.COVERAGE_FLOOR)
        need = int(np.ceil(bind * n - 1e-9))
        got = int(covered[sel].sum())
        per[q] = {"n": n, "coverage": round(got / n, 4), "binding_level": round(bind, 4),
                  "rows_of_slack": got - need, "ok": bool(got >= need)}
        if got < need:
            breaches.append(f"{q} {got / n:.4f}<{bind:.4f} ({got - need} rows)")
    return {"ok": bool(per) and all(v["ok"] for v in per.values()),
            "per_position": per, "breaches": breaches, "evaluable": bool(per)}


def build_evidence_eps(folds: list[dict], fits: dict, boards: dict) -> dict:
    """`R1.build_fold_evidence` with the ε-tolerant C3 — identical C1/C2, sensitivity C3 only."""
    ev: dict = {}
    for form in LR.FORMS:
        ev[form] = {}
        for f in folds:
            y = f["year"]
            params = fits[y][(form, LR.PRIMARY_SPACE)]
            ranks = R1.board_rank_by_lambda(boards[y], form, LR.PRIMARY_SPACE, params)
            inc_rank = ranks["rank_by_lambda"][0.0]
            p, lo, hi, pos, g, real = R1._triples(f)
            inc_cov = _unrounded_cov(real, lo, hi, pos)
            per_lam = {}
            for lam in LR.LAMBDA_GRID:
                ap, alo, ahi = LR.apply_to_band(form, LR.PRIMARY_SPACE, params, p, lo, hi, pos, g,
                                                float(lam))
                c1 = LR.ordering_movement(p, ap, pos)
                c1_ok = all(v >= 1.0 - LR.ORDERING_DO_NO_HARM
                            for v in c1["within_position_rho"].values())
                c2 = R1.board_admits(ranks["rank_by_lambda"].get(float(lam)), inc_rank)
                c3 = _cov_check_eps(real, alo, ahi, pos, inc_cov)
                per_lam[float(lam)] = {
                    "c1_ordering_ok": bool(c1_ok), "c2_placement_ok": bool(c2["admits"]),
                    "c3_coverage_ok": bool(c3["ok"]),
                    "admissible": bool(c1_ok and c2["admits"] and c3["ok"]),
                    "rank": c2.get("rank"), "worst_rank_move": c1["worst_rank_move"],
                    "coverage_breaches": c3["breaches"]}
            ev[form][y] = {
                "per_lambda": per_lam,
                "admissible": tuple(sorted(l for l, v in per_lam.items() if v["admissible"])),
                "incumbent_rank": inc_rank,
                "rank_by_lambda": ranks["rank_by_lambda"],
                "constraint_can_act": bool(len(set(
                    v for v in ranks["rank_by_lambda"].values() if v is not None)) > 1)}
    return ev


def reproduce_recorded_constraints(placements: dict, recorded: list[dict]) -> dict:
    """⭐ The as-recorded reproduction gate: the re-derived λ paths + panel-band evidence must
    reproduce the recorded out-of-sample constraint table EXACTLY, or nothing downstream is a
    re-read of THAT record."""
    rec_by_arm = {r["arm"]: r for r in recorded}
    mism = []
    for label, p in placements.items():
        r = rec_by_arm.get(label)
        if r is None:
            mism.append(f"{label}: not in the recorded table")
            continue
        got = (bool(p["holds_out"]), bool(p["c2_only"]), bool(p["c3_only"]),
               sorted(p["failing_folds"]))
        want = (bool(r["holds out (C1∧C2∧C3)"]), bool(r["C2 only"]), bool(r["C3 only"]),
                sorted(int(x) for x in r["failing folds"]))
        if got != want:
            mism.append(f"{label}: reproduced {got} vs recorded {want}")
    if mism:
        raise SystemExit("as-recorded REPRODUCTION FAILED — the re-derived arms are not the "
                         "recorded arms, so no corrected read of them means anything:\n  "
                         + "\n  ".join(mism))
    return {"reproduced": True, "n_arms": len(placements)}


def anchor_scrutiny(folds: list[dict], fits: dict, boards: dict) -> list[dict]:
    """The two-sided constraint teeth, re-measured on the CORRECTED band (NF1.8 / NF-D20): the
    do-nothing degenerates must still be eliminated by the METRIC (not the gate), `wide_band` must
    still SATISFY C3 while losing, and an over-correction must still be REFUSABLE."""
    out = []
    for tag in ("zero_project", "over_scale", "wide_band"):
        out.append(R1.anchor_constraint_state(folds, fits, boards,
                                              R1.anchor_adjuster(tag, folds), tag))
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF-D21 — reproduce the rookie floor sweep; re-read it under the corrected C3 STRUCTURE
# ══════════════════════════════════════════════════════════════════════════════════════════════
def d21_reread() -> dict:
    """NF-D21's gate re-read. Two questions, both MEASURED:

    (1) Does the trap reach it at all? Its band is refit through the ROOKIE model path
        (`shipped_rookie_cfg()` off `season_projection` constants), never a `served_*` panel
        column — proven by reproducing the recorded sweep row-for-row from that path.
    (2) Does the corrected C3 STRUCTURE change the verdict? The clause NF-RECAL1 fixed
        (`coverage_λ ≥ min(floor, coverage_incumbent)`) is applied with the incumbent = the λ=0
        band through the same path — the gate the two stories SHOULD share.

    ⛔ The floor itself is untouched, λ is untouched, and no thin-group fallback floor is derived
    here (that is NF-D22, post-launch, with this story explicitly out of its scope)."""
    recorded = json.load(open(_REPORT_DIR / "nf_g0_d21_governance_publish.json"))["floor_sweep"]
    sweep = floor_sweep(_D21_FROM, _D21_TO)
    rec_rows = {float(r["lambda"]): r for r in recorded["rows"]}
    for row in sweep["rows"]:
        want = rec_rows.get(float(row["lambda"]))
        if want is None or row.get("error"):
            raise SystemExit(f"NF-D21 sweep row λ={row['lambda']} did not reproduce (missing/error).")
        for p, cov in row["coverage"].items():
            if abs(float(cov) - float(want["coverage"][p])) > _COV_ATOL:
                raise SystemExit(
                    f"NF-D21 REPRODUCTION FAILED at λ={row['lambda']} {p}: {cov} vs recorded "
                    f"{want['coverage'][p]} — the sweep is not reading the recorded band source.")

    lam0 = next(r for r in sweep["rows"] if float(r["lambda"]) == 0.0)
    served_lam = next(r for r in sweep["rows"] if float(r["lambda"]) == 0.5)
    corrected = []
    for row in sweep["rows"]:
        per, breaches = {}, []
        for p, cov in row["coverage"].items():
            n = int(row["n_by_position"][p])
            inc = float(lam0["coverage"][p])
            bind = min(0.80, inc)
            need = int(np.ceil(bind * n))
            got = int(round(float(cov) * n))
            ok = got >= need
            per[p] = {"coverage": float(cov), "incumbent_coverage": inc,
                      "binding_level": round(bind, 4), "n": n,
                      "rows_of_slack": got - need, "ok": bool(ok)}
            if not ok:
                breaches.append(f"{p} {float(cov):.4f}<{bind:.3f} ({got - need} rows)")
        corrected.append({"lambda": float(row["lambda"]), "per_position": per,
                          "breaches": breaches, "ok": not breaches})

    # Per-draft-class RB coverage at the two λs that matter — the per-fold disclosure.
    pool = NF17.load_pool(Path(NF17._POOL_CACHE))
    cfg = __import__(
        "quant_sports_intel_models.football.nfl.fantasy.run_interval_revalidation",
        fromlist=["shipped_rookie_cfg"]).shipped_rookie_cfg()
    per_class = {}
    for lam in (0.0, 0.5):
        folds = NF17.build_folds(pool, list(range(_D21_FROM, _D21_TO + 1)),
                                 recalibrate=bool(lam), recal_lambda=float(lam))
        rows = NF18.arm_rows(folds, cfg)
        rb = rows[rows["pos"] == "RB"]
        per_class[f"lambda_{lam:g}"] = {
            int(yy): {"n": int(len(g)),
                      "coverage": round(float(((g["y"] >= g["lo"]) & (g["y"] <= g["hi"])).mean()), 4)}
            for yy, g in rb.groupby("year")}

    lam05 = next(c for c in corrected if c["lambda"] == 0.5)
    return {
        "band_source": ("rookie model path (`shipped_rookie_cfg()` off season_projection constants) "
                        "— NOT a `served_*` panel column; the NF1.9-R trap does NOT reach this gate, "
                        "proven by row-for-row reproduction of the recorded sweep from that path"),
        "sweep_reproduced": True,
        "sweep": sweep,
        "corrected_c3_structure": corrected,
        "rb_per_class_coverage": per_class,
        "verdict": {
            "lambda_0_5_ok_under_corrected_structure": bool(lam05["ok"]),
            "breaches": lam05["breaches"],
            "note": ("the incumbent (λ=0) RB coverage is "
                     f"{lam0['coverage']['RB']:.4f} ≥ 0.80, so min(floor, incumbent) = 0.80 — the "
                     "corrected structure reduces to the bare floor NF-D21 was refused under; the "
                     f"λ=0.5 RB coverage is {served_lam['coverage']['RB']:.4f}"),
        },
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    t0 = time.time()

    # ── STEP 0 — hold the served band, provably ──
    years_wide = tuple(sorted(set(LR.WIDE_WINDOW_SEASONS) | set(LR.PANEL_SEASONS)))
    rows, lookup = served_band_by_row(years_wide)
    proofs = reproduction_proofs(rows)
    log.info("STEP 0 — served band held: universe IS80 %.3f (recorded %.3f, Δ %.4f%%) · "
             "tier cov 19–25 %.4f (recorded %.4f) · panel-column cov %.4f (recorded %.4f)",
             proofs["universe_is80"], _NF19_UNIVERSE_IS80, proofs["universe_is80_delta_pct"],
             proofs["served_tier_coverage_2019_2025"], _NF19R_SERVED_TIER_COV_2019_2025,
             proofs["panel_column_tier_coverage_2019_2025"], _NFRECAL1_PANEL_TIER_COV_2019_2025)

    # ── NF-RECAL1: as-recorded reproduction, then the corrected reads ──
    recorded = json.load(open(_REPORT_DIR / "nf_recal1_level_recalibration.json"))
    tier_n = LR.draftable_tier_size()
    d = R1.load_panel(years_wide)
    boards = R1.load_boards(LR.PANEL_SEASONS)
    tier = R1.tier_mask(d, tier_n)
    folds_panel = R1.build_folds(d, tier, LR.PANEL_SEASONS)
    years = [f["year"] for f in folds_panel]

    fits_panel = {f["year"]: trimmed_fits(f) for f in folds_panel}
    lam_panel = score_lambda_grid(folds_panel, fits_panel)
    ev_panel = R1.build_fold_evidence(folds_panel, fits_panel, boards)
    arms_panel, plc_panel, paths_recorded = build_arms(folds_panel, fits_panel, lam_panel, ev_panel)
    repro = reproduce_recorded_constraints(plc_panel, recorded["constraint_table"])
    inc_crps_rec = next(r["CRPS"] for r in recorded["leaderboard"]
                        if r["arm"] == "incumbent (NULL)")
    inc_crps_got = arms_panel[0][LR.SELECTION_METRIC]
    if abs(float(inc_crps_got) - float(inc_crps_rec)) > 1e-3:
        raise SystemExit(f"as-recorded incumbent CRPS {inc_crps_got} vs recorded {inc_crps_rec} — "
                         "the panel-band reproduction is broken.")
    log.info("NF-RECAL1 as-recorded REPRODUCED: %d arms, incumbent CRPS %.4f (recorded %.4f)",
             repro["n_arms"], inc_crps_got, float(inc_crps_rec))

    folds_served = substitute_served_band(folds_panel, lookup)
    fits_served = {f["year"]: trimmed_fits(f) for f in folds_served}
    ev_served = R1.build_fold_evidence(folds_served, fits_served, boards)

    # READ 1 — the RECORDED arms re-gated on the corrected C3.
    arms_r1, plc_r1, _ = build_arms(folds_served, fits_served, None, ev_served,
                                    lam_paths=paths_recorded)
    # READ 2 — the pre-registered machinery replayed end-to-end on the corrected band.
    lam_served = score_lambda_grid(folds_served, fits_served)
    arms_r2, plc_r2, paths_r2 = build_arms(folds_served, fits_served, lam_served, ev_served)
    sel_r2 = R1.select_pooled(arms_r2, arms_r2[0], years, plc_r2)
    teeth = anchor_scrutiny(folds_served, fits_served, boards)

    # ε-SENSITIVITY — the round-then-ceil artifact removed from C3's equality boundary (see
    # `_cov_check_eps`). Both reads repeated against the ε-tolerant evidence, as a sensitivity ONLY.
    ev_eps = build_evidence_eps(folds_served, fits_served, boards)
    _, plc_r1_eps, _ = build_arms(folds_served, fits_served, None, ev_eps,
                                  lam_paths=paths_recorded)
    arms_r2e, plc_r2e, paths_r2e = build_arms(folds_served, fits_served, lam_served, ev_eps)
    sel_r2e = R1.select_pooled(arms_r2e, arms_r2e[0], years, plc_r2e)

    # The corrected-band METRIC sanity beside READ 1 (scrutiny): the oracle floor + degenerates.
    inc_served = arms_r1[0]
    scrutiny = {
        "incumbent_crps_served_band": inc_served[LR.SELECTION_METRIC],
        "oracle_perplayer_crps": R1.score_arm(
            folds_served, fits_served, R1.anchor_adjuster("oracle_perplayer", folds_served),
            "oracle_perplayer")[LR.SELECTION_METRIC],
        "zero_project_crps": R1.score_arm(
            folds_served, fits_served, R1.anchor_adjuster("zero_project", folds_served),
            "zero_project")[LR.SELECTION_METRIC],
        "pos_median_crps": R1.score_arm(
            folds_served, fits_served, R1.anchor_adjuster("pos_median", folds_served),
            "pos_median")[LR.SELECTION_METRIC],
        "wide_band_crps": R1.score_arm(
            folds_served, fits_served, R1.anchor_adjuster("wide_band", folds_served),
            "wide_band")[LR.SELECTION_METRIC],
        "over_scale_crps": R1.score_arm(
            folds_served, fits_served, R1.anchor_adjuster("over_scale", folds_served),
            "over_scale")[LR.SELECTION_METRIC],
    }
    scrutiny["oracle_is_the_floor"] = bool(
        scrutiny["oracle_perplayer_crps"] < min(r[LR.SELECTION_METRIC] for r in arms_r1))
    scrutiny["degenerates_lose"] = bool(
        min(scrutiny["zero_project_crps"], scrutiny["pos_median_crps"])
        > max(r[LR.SELECTION_METRIC] for r in arms_r1))
    best_real_crps = min(r[LR.SELECTION_METRIC] for r in arms_r2 if r.get("recalibrates"))
    scrutiny["over_scale_loses_to_best_real"] = bool(
        scrutiny["over_scale_crps"] > best_real_crps)
    # NF-D15 (g′) — a genuine LEVEL fix moves pooled bias TOWARD zero while accuracy improves.
    scrutiny["attribution_signature_read2"] = LR.attribution_signature(
        incumbent_bias=arms_r2[0].get("bias"),
        winner_bias=(sel_r2.get("winner") or {}).get("bias"),
        incumbent_metric=sel_r2.get("incumbent_metric"),
        winner_metric=(sel_r2.get("winner") or {}).get("metric"))
    # The pre-registered pooled SHIP gate, evaluated on the corrected READ 2 selection.
    gate_r2 = LR.pooled_ship(
        winner=sel_r2.get("winner"), incumbent_metric=sel_r2.get("incumbent_metric"),
        ordering=sel_r2.get("ordering") or {}, placement=sel_r2.get("placement"),
        coverage=sel_r2.get("coverage"),
        pbo=(sel_r2.get("deflation") or {}).get("pbo"),
        dsr=(sel_r2.get("deflation") or {}).get("dsr"), pvalue=sel_r2.get("pvalue"))
    gate_r2e = LR.pooled_ship(
        winner=sel_r2e.get("winner"), incumbent_metric=sel_r2e.get("incumbent_metric"),
        ordering=sel_r2e.get("ordering") or {}, placement=sel_r2e.get("placement"),
        coverage=sel_r2e.get("coverage"),
        pbo=(sel_r2e.get("deflation") or {}).get("pbo"),
        dsr=(sel_r2e.get("deflation") or {}).get("dsr"), pvalue=sel_r2e.get("pvalue"))

    # ── the corrected null's CLASSIFICATION: once the deterministic refusal is gone, the null (if
    #    any) is STATISTICAL, and cv_power IS the right instrument (mirrors R1.classify_this_null) ──
    from betting_ml.utils import cv_power as CP
    inc_row = np.array([arms_r2[0]["per_fold_metric"][y] for y in years], dtype=float)
    recal_elig = [r for r in arms_r2 if r.get("recalibrates")
                  and plc_r2.get(r["label"], {}).get("holds_out")]
    classification = {"note": "no eligible recalibrating arm under the corrected gate"}
    if recal_elig:
        best = min(recal_elig, key=lambda r: r[LR.SELECTION_METRIC])
        dd = inc_row - np.array([best["per_fold_metric"][y] for y in years], dtype=float)
        dd = dd[np.isfinite(dd)]
        sr = float(dd.mean() / dd.std(ddof=1)) if len(dd) >= 3 and dd.std(ddof=1) > 1e-12 else None
        v = CP.classify_null(metric=LR.SELECTION_METRIC, n_folds=len(years),
                             n_arms=len(arms_r2), beats_foil=bool(dd.mean() > 0),
                             observed_sr=sr, fold_wins=int((dd > 0).sum()))
        classification = {
            "state": v.state, "remedy": getattr(v, "remedy", None),
            "best_eligible_arm": best["label"], "observed_sr": None if sr is None else round(sr, 4),
            "fold_wins": int((dd > 0).sum()), "n_folds": len(dd),
            "dsr_ceiling_at_this_fold_count": (round(float(CP.dsr_ceiling(len(years))), 4)
                                               if hasattr(CP, "dsr_ceiling") else None),
            "detail": {k: getattr(v, k) for k in dir(v)
                       if not k.startswith("_") and isinstance(getattr(v, k), (int, float, str, bool,
                                                                              type(None)))}}

    # ── NF-D21 ──
    d21 = d21_reread()

    # ── the verdicts ──
    def _c3_rows(arms, placements):
        rows_out = []
        for r in arms:
            p = placements[r["label"]]
            per_fold = {}
            for y, v in p.get("per_fold", {}).items():
                cov = (r.get("per_fold", {}).get(y, {}) or {}).get("coverage", {})
                per_fold[y] = {
                    "lam": v.get("lam"),
                    "c3_ok": v.get("c3_coverage_ok"),
                    "c2_ok": v.get("c2_placement_ok"),
                    "admissible": v.get("admissible"),
                    "breaches": v.get("coverage_breaches"),
                    # the arm's OWN C3 detail at its λ for this fold (coverage / bind / slack rows)
                    "coverage_detail": {q: {"coverage": w.get("coverage"),
                                            "binding_level": w.get("binding_level"),
                                            "rows_of_slack": w.get("rows_of_slack"),
                                            "n": w.get("n"), "ok": w.get("ok")}
                                        for q, w in (cov.get("per_position") or {}).items()}}
            rows_out.append({
                "arm": r["label"], "rule": r.get("rule"),
                "lam_by_fold": r.get("lam_by_fold"),
                "crps": r[LR.SELECTION_METRIC], "bias": r.get("bias"),
                "cov80": r.get("coverage80"),
                "c3_every_fold": p.get("c3_only"), "holds_out": p.get("holds_out"),
                "failing_folds": p.get("failing_folds"), "per_fold": per_fold,
                "coverage_pooled": r.get("coverage_pooled")})
        return rows_out

    read1 = _c3_rows(arms_r1, plc_r1)
    read2 = _c3_rows(arms_r2, plc_r2)
    read2_eps = _c3_rows(arms_r2e, plc_r2e)
    recal_r1 = [r for r in read1 if r["arm"] != "incumbent (NULL)"]
    moving_r1 = [r for r in recal_r1 if any(v > 0 for v in (r["lam_by_fold"] or {}).values())]
    cleared_r1 = [r for r in moving_r1 if r["holds_out"]]
    cleared_r1_eps = [r["label"] for r in arms_r1
                      if r.get("recalibrates")
                      and any(v > 0 for v in (r.get("lam_by_fold") or {}).values())
                      and plc_r1_eps.get(r["label"], {}).get("holds_out")]
    constraint_refusal_overturned = bool(cleared_r1)

    verdict = {
        "nf_recal1": {
            "recorded_null_state": "CONSTRAINT_REFUSED",
            "recorded_null_stands": not constraint_refusal_overturned,
            "corrected_state": (
                "CONSTRAINT_REFUSED (corrected bar)" if not constraint_refusal_overturned
                else classification.get("state", "see classification")),
            "reading": (
                "the recorded refusal STANDS at the corrected bar" if not constraint_refusal_overturned
                else "the recorded CONSTRAINT_REFUSED does NOT stand: arms clear the corrected C3 "
                     "out-of-sample on every fold, so the corrected null (nothing ships) is "
                     "STATISTICAL — it now rests on the pre-registered deflation gate, not on a "
                     "deterministic constraint — and its state is the cv_power classification"),
            "classification_note": (
                "a DETERMINISTIC gate refusal is CONSTRAINT_REFUSED (NF-D18's 8th state) — ⛔ never "
                "POWER_LIMITED and never a '+N seasons' trigger. Once arms CLEAR the corrected "
                "constraint, the surviving refusal (the deflation gate) IS statistical, and "
                "cv_power.classify_null becomes the right instrument — applied above."),
            "arms_recorded_lambda_cleared_corrected_c3": [r["arm"] for r in cleared_r1],
            "arms_recorded_lambda_cleared_corrected_c3_eps": cleared_r1_eps,
            "arms_with_any_correction_read1": [r["arm"] for r in moving_r1],
            "read2_ship_gate": gate_r2,
            "read2_ship_gate_eps": gate_r2e,
            "nothing_ships": bool(not gate_r2["ship"] and not gate_r2e["ship"]),
        },
        "nf_d21": {
            "recorded_null_state": "CONSTRAINT_REFUSED",
            "recorded_null_stands": not d21["verdict"]["lambda_0_5_ok_under_corrected_structure"],
            "corrected_state": ("CONSTRAINT_REFUSED (unchanged — the trap never reached this gate)"
                                if not d21["verdict"]["lambda_0_5_ok_under_corrected_structure"]
                                else "NULL_FALLS — see escalation"),
            "band_source": d21["band_source"],
        },
    }

    res = {
        "story": "NF-C3-REREAD",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "best_alpha": 0,
        "wall_time_s": None,
        "step0_reproduction": proofs,
        "as_recorded_reproduction": {
            **repro, "incumbent_crps": inc_crps_got,
            "recorded_lambda_paths": paths_recorded},
        "read1_recorded_arms_corrected_gate": read1,
        "read2_full_replay": read2,
        "read2_lambda_paths": paths_r2,
        "read2_selection": sel_r2,
        "read2_classification": classification,
        "eps_sensitivity": {
            "note": ("the recorded C3 computes need = ceil(round(inc,6)·n); when the 6-dp rounding "
                     "rounds UP, coverage EQUAL to the incumbent's — including λ=0, which IS the "
                     "incumbent — fails by one row. Present in the RECORDED run too (its λ=0 arms "
                     "'fail C3' on 6/7 folds). The ε read uses need = ceil(bind·n − 1e-9) on the "
                     "unrounded incumbent, as a SENSITIVITY only — the recorded clause is not edited."),
            "read1_holds_out_eps": {lbl: {"holds_out": p.get("holds_out"),
                                          "failing_folds": p.get("failing_folds")}
                                    for lbl, p in plc_r1_eps.items()},
            "read2_full_replay_eps": read2_eps,
            "read2_lambda_paths_eps": paths_r2e,
            "read2_selection_eps": sel_r2e,
        },
        "anchor_constraint_teeth_corrected": [
            {k: v for k, v in t.items() if k != "per_fold"} for t in teeth],
        "metric_scrutiny_served_band": scrutiny,
        "nf_d21": d21,
        "verdict": verdict,
    }
    res["wall_time_s"] = round(time.time() - t0, 1)

    if not args.no_report:
        jp = _REPORT_DIR / f"{_STEM}.json"
        jp.write_text(json.dumps(res, indent=2, default=str))
        log.info("wrote %s", jp)
    log.info("VERDICT — NF-RECAL1 recorded null stands: %s (corrected state: %s) · "
             "NF-D21 recorded null stands: %s · nothing ships: %s · %.1fs",
             verdict["nf_recal1"]["recorded_null_stands"],
             verdict["nf_recal1"]["corrected_state"],
             verdict["nf_d21"]["recorded_null_stands"],
             verdict["nf_recal1"]["nothing_ships"], res["wall_time_s"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
