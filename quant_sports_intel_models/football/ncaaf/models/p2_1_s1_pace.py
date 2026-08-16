"""p2_1_s1_pace.py — NCAAF-P2.1 S1: `pace` under a lower-variance GATE design (fresh §0.5 registration).

WHAT THIS IS
------------
P2.1 found ONE real structural effect (`pace`: +0.062 CRPS, 8/8 folds, p=0.002, PBO 0.023) and it
failed DSR (0.041) for a DESIGN reason: the pre-registered gate SHARED one return series between
PBO (which wants MANY buckets) and DSR (which wants LOW-NOISE INDEPENDENT observations). This
harness is the successor P2.1 §9.6 earned: it re-registers `pace` with the two series declared
SEPARATELY (per-BUCKET for PBO, per-FOLD for DSR), a COHERENT 3-arm field (the pace feature + its
representation set — every arm a strict subset of the P2.1 H9 columns; NO new feature), the same
four generic anchors, and the P2.1 fold/learner/form/seed/draw machinery byte-for-byte.

⭐ READ THE PRE-REGISTRATION FIRST — `ablation_results/ncaaf_p2_1_s1_preregistration.md`, committed
BEFORE the first S1 score. The one thing S1 changes is the gate's SERIES design; ⛔ nothing here may
be changed to chase a result (E2.1-r), and the per-fold DSR series is FIXED forward — no third
series if it fails.

USAGE
-----
    # 0) the P2.1 cache (identical parquet; re-assemble if absent — 29 s, Snowflake-free)
    AWS_DEFAULT_REGION=us-east-2 uv run python -m \\
        quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_1 --assemble
    # 1) score the S1 field (reference + 3 arms + 4 anchors) on the P2.1 folds  (~1 min)
    uv run python -m quant_sports_intel_models.football.ncaaf.models.p2_1_s1_pace --stage battery
    # 2) deflate on the DECLARED series, classify, render
    uv run python -m quant_sports_intel_models.football.ncaaf.models.p2_1_s1_pace --stage decide
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import cv_power  # noqa: E402
from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv  # noqa: E402
from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_p2_1 as p21  # noqa: E402
from quant_sports_intel_models.football.ncaaf.models.p2_1_blocks import BLOCK_BY_ARM, Block  # noqa: E402

_STORY = "NCAAF-P2.1-S1"
_RESULTS_DIR = Path(__file__).resolve().parent.parent / "ablation_results"
_SCORES_JSON = _RESULTS_DIR / "ncaaf_p2_1_s1_pace_scores.json"
_DECISION_JSON = _RESULTS_DIR / "ncaaf_p2_1_s1_pace.json"
_DECISION_MD = _RESULTS_DIR / "ncaaf_p2_1_s1_pace.md"
_P21_SCORES = _RESULTS_DIR / "ncaaf_p2_1_battery_scores.json"   # the reproduction target (check R)

# ── the pre-registered constants — every one inherited from P2.1 (⛔ never edited here) ─────────
_PBO_GATE, _DSR_GATE, _FDR_ALPHA = p21._PBO_GATE, p21._DSR_GATE, p21._FDR_ALPHA
_TIE_BAND, _BREAKEVEN = p21._TIE_BAND, p21._BREAKEVEN
_REPRO_TOL = 1e-4                 # check R: |S1 fold CRPS − P2.1 recorded| must be < this
_P21_FIELD_N_TRIALS = 22          # the P2.1 field in which `pace` was FOUND (lineage disclosure)

#: ⭐ THE PRIMARY — the only arm that can ship. Fixed here, before the run.
PRIMARY = "pace"

_pace_p21 = BLOCK_BY_ARM["pace"]

#: The declared S1 field. Every arm is `reference ∪ block`; every block is a STRICT SUBSET of the
#: P2.1 H9 columns (no new feature enters — S1 changes the gate design, not the hypothesis).
S1_BLOCKS: tuple[Block, ...] = (
    Block("pace", "S1-A", 4, "the P2.1 H9 block, VERBATIM (PRIMARY)", raw=_pace_p21.raw),
    Block("pace_axis", "S1-B", 4, "game-level tempo composites only (total + margin axes)",
          raw=("pace_sum", "pace_diff")),
    Block("pace_total_axis", "S1-C", 4, "the possessions channel on the TOTAL axis only",
          raw=("pace_sum",)),
)
S1_BLOCK_BY_ARM: dict[str, Block] = {b.arm: b for b in S1_BLOCKS}
DECLARED_FIELD_SIZE_S1: int = len(S1_BLOCKS)          # 3

#: the four GENERIC anchors (P2.1 §1.7); `hfa_global` is H1b's foil and is not part of S1
S1_ANCHORS: tuple[str, ...] = ("oracle_peek", "permute", "zero_width", "max_width")


def n_trials_declared() -> int:
    """reference + the 3 real arms + the 4 anchors — the DSR multiplicity count (MH2)."""
    return 1 + len(S1_BLOCKS) + len(S1_ANCHORS)


# ===========================================================================
# The two return series — declared SEPARATELY (the design change)
# ===========================================================================

def fold_series(ref_arm: dict, arm: dict) -> np.ndarray:
    """The DSR return series: per-FOLD improvement `reference − arm` pooled CRPS (>0 ⇔ arm better).
    One observation per season-forward fold — the independent unit of the design."""
    r = np.asarray(ref_arm["fold_crps"], float)
    a = np.asarray(arm["fold_crps"], float)
    n = min(len(r), len(a))
    return r[:n] - a[:n]


def bucket_series(ref_arm: dict, arm: dict) -> np.ndarray:
    """The PBO return series (P2.1's gate series): per-BUCKET improvement over the fold quarters.
    Many buckets ⇒ CSCV can form its combinations; NOT the DSR series (within-fold noise)."""
    r = np.asarray(ref_arm["buckets"], float)
    a = np.asarray(arm["buckets"], float)
    n = min(len(r), len(a))
    return r[:n] - a[:n]


def sharpe(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    s = x.std(ddof=1) if len(x) > 1 else 0.0
    return float(x.mean() / s) if s > 0 else 0.0


# ===========================================================================
# Stage 1 — battery: the P2.1 scoring function, S1's registry
# ===========================================================================

def stage_battery(args) -> None:
    df, _meta = p21.load_cache()
    ref_cols = p21.reference_columns(df)
    folds = p21.build_folds(df, max_folds=args.max_folds)
    arms = ["reference"] + [b.arm for b in S1_BLOCKS] + list(S1_ANCHORS)
    if args.arm:
        arms = ["reference"] + [a for a in args.arm.split(",") if a != "reference"]
    print(f"=== {_STORY} stage 1 — BATTERY ({len(arms)} arms × {len(folds)} folds, {len(df):,} games, "
          f"reference contract = {len(ref_cols)} cols) ===")
    print(f"  folds: {[f.eval_year for f in folds]}")

    out: dict[str, Any] = {"story": _STORY, "run_at": date.today().isoformat(),
                           "n_folds": len(folds), "n_games": int(len(df)),
                           "reference_n_cols": len(ref_cols), "arms": {}}
    for arm in arms:
        t0 = time.time()
        rng = np.random.default_rng(p21._SEED)     # identical stream per arm ⇒ paired
        rows = [p21.score_arm_fold(arm, f, ref_cols, rng, n_draws=args.n_draws, blocks=S1_BLOCKS)
                for f in folds]
        clv = p21._clv_leg(rows, np.random.default_rng(p21._SEED)) if not args.no_clv else {}
        slim = [{k: v for k, v in r.items() if not isinstance(v, np.ndarray)} for r in rows]
        pooled = float(np.mean(np.concatenate([r["per_game_crps"] for r in rows])))
        out["arms"][arm] = {
            "arm": arm, "folds": slim, "clv": clv,
            "pooled_crps": round(pooled, 5),
            "mean_crps": round(float(np.mean([r["crps"] for r in rows])), 5),
            "fold_crps": [r["crps"] for r in rows],
            "fold_years": [r["eval_year"] for r in rows],
            "buckets": [b for r in rows for b in r["buckets"]],
            "mean_pit_sum": round(float(np.mean([r["pit_sum"] for r in rows])), 5),
            "pooled_margin_calib": round(float(np.mean([r["margin_calib_80"] for r in rows])), 4),
            "pooled_total_calib": round(float(np.mean([r["total_calib_80"] for r in rows])), 4),
            "margin_pit_flat_folds": int(sum(r["margin_pit_flat"] for r in rows)),
            "total_pit_flat_folds": int(sum(r["total_pit_flat"] for r in rows)),
            "mean_h2h_brier": round(float(np.mean([r["h2h_brier"] for r in rows])), 4),
            "n_features": rows[0]["n_features"],
        }
        a = out["arms"][arm]
        print(f"  {arm:<18} CRPS {a['pooled_crps']:.4f}  calib80(m/t) {a['pooled_margin_calib']:.3f}/"
              f"{a['pooled_total_calib']:.3f}  feat {a['n_features']:>3}  ({time.time() - t0:.0f}s)")
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _SCORES_JSON.write_text(json.dumps(out, indent=2, default=float))
    print(f"\n  scores → {_SCORES_JSON.relative_to(_PROJECT_ROOT)}\n  Next: `--stage decide`")


# ===========================================================================
# Stage 2 — decide on the DECLARED series
# ===========================================================================

def reproduction_check(arms: dict, tol: float = _REPRO_TOL) -> dict[str, Any]:
    """Check R — S1 must REPRODUCE P2.1's recorded per-fold CRPS for `reference` and `pace` (the
    harness is byte-identical). A mismatch ⇒ the design drifted ⇒ the run is NOT S1."""
    if not _P21_SCORES.exists():
        return {"holds": False, "reason": f"P2.1 scores missing at {_P21_SCORES.name}", "max_abs_dev": None}
    p21doc = json.loads(_P21_SCORES.read_text())["arms"]
    devs: dict[str, float] = {}
    for a in ("reference", PRIMARY):
        if a not in arms or a not in p21doc:
            return {"holds": False, "reason": f"arm {a!r} missing", "max_abs_dev": None}
        x, y = np.asarray(arms[a]["fold_crps"], float), np.asarray(p21doc[a]["fold_crps"], float)
        if len(x) != len(y):
            return {"holds": False, "reason": f"fold count differs for {a!r} ({len(x)} vs {len(y)})",
                    "max_abs_dev": None}
        devs[a] = float(np.max(np.abs(x - y)))
    mx = max(devs.values())
    return {"holds": bool(mx < tol), "max_abs_dev": mx, "per_arm": devs, "tolerance": tol,
            "reason": "" if mx < tol else f"max |Δ| {mx:.2e} ≥ {tol:g} — the harness drifted"}


def lever_decomposition(arms: dict, V_fold_s1: float | None, V_bucket_s1: float | None,
                        n_trials_s1: int) -> dict[str, Any]:
    """POST-VERDICT DISCLOSURE (never a gate): which of S1's two design levers did the work?

    S1 changed TWO things relative to P2.1's DSR: the RETURN SERIES (bucket → fold) and the FIELD
    (16 heterogeneous arms → 3 pace representations, which sets `V` and `N`). The pre-registered
    binding cell is (fold, S1 field). The other three cells are computed from the P2.1 record so a
    reader can see whether the verdict rests on the series, the field, or both. The (bucket, P2.1
    field) cell must reproduce P2.1's recorded 0.0409 — that reproduction is what makes the other
    cells trustworthy. ⛔ None of these cells re-decides anything; the binding figure was fixed
    before the run (E2.1-r)."""
    if not _P21_SCORES.exists() or PRIMARY not in arms:
        return {"available": False}
    p21 = json.loads(_P21_SCORES.read_text())["arms"]
    p21_real = [a for a in p21 if a not in ("reference",) and a not in p21_anchor_names()]
    ref = p21["reference"]
    sr_fold_16 = [sharpe(fold_series(ref, p21[a])) for a in p21_real]
    sr_bkt_16 = [sharpe(bucket_series(ref, p21[a])) for a in p21_real]
    V_fold_16 = float(np.var(sr_fold_16, ddof=1))
    V_bkt_16 = float(np.var(sr_bkt_16, ddof=1))
    N16 = 1 + len(p21_real) + len(p21_anchor_names())
    f_series = fold_series(ref, p21[PRIMARY])
    b_series = bucket_series(ref, p21[PRIMARY])

    def cell(series, N, V):
        r = deflated_sharpe(series, n_trials=N, var_trials_sr=V)
        return {"dsr": round(float(r.dsr), 4), "sr": round(float(r.observed_sr), 4),
                "sr0": round(float(r.sr0), 4), "N": int(N), "V": round(float(V), 4)}
    return {
        "available": True,
        "note": "rows = return series; cols = field. Binding = (fold, S1 field). "
                "(bucket, P2.1 field) must reproduce P2.1's recorded DSR 0.0409.",
        "p21_field": {"n_real_arms": len(p21_real), "N": N16, "V_per_fold": round(V_fold_16, 4),
                      "V_per_bucket": round(V_bkt_16, 4)},
        "cells": {
            "bucket__p21_field": cell(b_series, N16, V_bkt_16),
            "fold__p21_field": cell(f_series, N16, V_fold_16),
            "bucket__s1_field": cell(b_series, n_trials_s1, V_bucket_s1) if V_bucket_s1 else None,
            "fold__s1_field__BINDING": cell(f_series, n_trials_s1, V_fold_s1) if V_fold_s1 else None,
        },
    }


def p21_anchor_names() -> tuple[str, ...]:
    return tuple(p21.ANCHORS)


def stage_decide(args) -> None:
    if not _SCORES_JSON.exists():
        raise SystemExit(f"[{_STORY}] no scores — run `--stage battery` first.")
    doc = json.loads(_SCORES_JSON.read_text())
    arms = doc["arms"]
    ref = arms["reference"]
    n_folds = doc["n_folds"]
    real = [b.arm for b in S1_BLOCKS if b.arm in arms]
    anchors = [a for a in S1_ANCHORS if a in arms]
    ref_crps = ref["pooled_crps"]

    # ── A: anchors first (a misbehaving anchor invalidates the run) ────────────────────────────
    anchor_report: dict[str, Any] = {}
    best_real = min(arms[a]["pooled_crps"] for a in real) if real else ref_crps
    if "oracle_peek" in arms:
        o = arms["oracle_peek"]["pooled_crps"]
        anchor_report["oracle_floor"] = {"oracle_crps": o, "best_real_crps": best_real,
                                         "holds": bool(o <= best_real + 1e-9)}
    for name, expect in (("permute", "must LOSE"), ("zero_width", "must LOSE + FAIL the floor"),
                         ("max_width", "must SATISFY the floor + LOSE")):
        if name in arms:
            a = arms[name]
            cov_ok, _ = p21._coverage_floor_ok(a)     # the COVERAGE FLOOR alone (P2.1's fixed bug)
            anchor_report[name] = {"crps": a["pooled_crps"],
                                   "loses_to_reference": bool(a["pooled_crps"] > ref_crps),
                                   "satisfies_coverage_floor": cov_ok,
                                   "margin_calib": a["pooled_margin_calib"],
                                   "total_calib": a["pooled_total_calib"], "expectation": expect}

    def _anchor(name, key, default):
        return bool(anchor_report.get(name, {}).get(key, default))

    anchor_checks = {
        "oracle_floor_holds": _anchor("oracle_floor", "holds", True),
        "permute_loses": _anchor("permute", "loses_to_reference", True),
        "zero_width_loses": _anchor("zero_width", "loses_to_reference", True),
        "max_width_loses": _anchor("max_width", "loses_to_reference", True),
        "zero_width_fails_floor": not _anchor("zero_width", "satisfies_coverage_floor", True),
        "max_width_satisfies_floor": _anchor("max_width", "satisfies_coverage_floor", False),
    }
    anchors_ok = all(anchor_checks.values())

    # ── R: reproduction of P2.1 ────────────────────────────────────────────────────────────────
    repro = reproduction_check(arms)

    # ── per-arm read on BOTH series ────────────────────────────────────────────────────────────
    clause = cv_power.fold_consistency_clause(n_folds)
    rows: dict[str, Any] = {}
    pvals: dict[str, float] = {}
    for arm in real:
        a = arms[arm]
        d_fold = fold_series(ref, a)
        d_bucket = bucket_series(ref, a)
        gain = ref_crps - a["pooled_crps"]
        elig, why = p21._eligible(a)
        p = p21._paired_p(d_fold)
        wins = int((d_fold > 0).sum())
        rows[arm] = {
            "arm": arm, "gain_crps": round(float(gain), 5), "pooled_crps": a["pooled_crps"],
            "fold_deltas": [round(float(x), 5) for x in d_fold], "fold_years": a.get("fold_years"),
            "fold_wins": wins, "n_folds": n_folds, "all_folds_positive": bool(wins == n_folds),
            "fold_clause_required": clause.wins_required, "fold_clause_attainable": clause.attainable,
            "fold_clause_passes": bool(clause.passes(wins)),
            "eligible": elig, "ineligible_reason": why,
            "tie_with_foil": bool(abs(gain) < _TIE_BAND),
            "p_one_sided": round(p, 6),
            "sharpe_per_fold": round(sharpe(d_fold), 4),        # the DSR series (binding)
            "sharpe_per_bucket": round(sharpe(d_bucket), 4),    # P2.1's series (reported)
            "n_obs_fold": int(len(d_fold)), "n_obs_bucket": int(len(d_bucket)),
            "margin_calib": a["pooled_margin_calib"], "total_calib": a["pooled_total_calib"],
            "total_pit_flat_folds": a["total_pit_flat_folds"],
            "n_features": a["n_features"], "clv": a.get("clv", {}),
        }
        pvals[arm] = p
    bh_pass, bh_cutoff = p21._bh(pvals, alpha=_FDR_ALPHA)
    for arm in real:
        rows[arm]["bh_pass"] = bool(bh_pass[arm])

    # ── PBO on the per-BUCKET series (eligible real set + reference) ───────────────────────────
    elig_arms = [a for a in real if rows[a]["eligible"]] + (["reference"] if p21._eligible(ref)[0] else [])
    nb = min(len(arms[a]["buckets"]) for a in elig_arms) if elig_arms else 0
    pbo = float("nan")
    if len(elig_arms) >= 2 and nb >= 4:
        perf = np.array([arms[a]["buckets"][:nb] for a in elig_arms], float).T
        pbo = float(pbo_cscv(perf, higher_is_better=False,
                             n_splits=max(2, min(16, nb - nb % 2))).pbo)

    # ── DSR on the per-FOLD series; V over the REAL arms only (DSR-CONV) ───────────────────────
    sr_fold_real = [sharpe(fold_series(ref, arms[a])) for a in real]
    sr_fold_all = sr_fold_real + [sharpe(fold_series(ref, arms[a])) for a in anchors]
    V_clean = float(np.var(sr_fold_real, ddof=1)) if len(sr_fold_real) > 1 else None
    V_all = float(np.var(sr_fold_all, ddof=1)) if len(sr_fold_all) > 1 else None
    n_trials = 1 + len(real) + len(anchors)
    # per-BUCKET V too, so the reported per-bucket DSR is P2.1's construction, not a hybrid
    sr_bucket_real = [sharpe(bucket_series(ref, arms[a])) for a in real]
    V_bucket_clean = float(np.var(sr_bucket_real, ddof=1)) if len(sr_bucket_real) > 1 else None

    def _dsr(series: np.ndarray, N: int, V: float | None) -> dict:
        # a per-FOLD series needs ≥3 folds to carry a DSR at all — below that the statistic is
        # UNDEFINED (MH2: "not computable" is a state, never a pass and never a crash-into-silence)
        if len(series) < 3:
            return {"dsr": None, "sr": round(sharpe(series), 4), "sr0": None, "n_trials": int(N),
                    "n_obs": int(len(series)), "undefined": "fewer than 3 observations"}
        r = deflated_sharpe(series, n_trials=N, var_trials_sr=V)
        return {"dsr": round(float(r.dsr), 4), "sr": round(float(r.observed_sr), 4),
                "sr0": round(float(r.sr0), 4), "n_trials": int(r.n_trials), "n_obs": int(r.n_obs)}

    prim = rows.get(PRIMARY)
    dsr: dict[str, Any] = {}
    if prim and prim["gain_crps"] > 0:
        f_series = fold_series(ref, arms[PRIMARY])
        b_series = bucket_series(ref, arms[PRIMARY])
        dsr = {
            "binding": "per_fold_declared_field_degenerate_excluded",
            "per_fold_declared_field_degenerate_excluded": _dsr(f_series, n_trials, V_clean),
            "per_fold_whole_field": _dsr(f_series, n_trials, V_all),
            "per_fold_lineage_inclusive": _dsr(f_series, n_trials + _P21_FIELD_N_TRIALS, V_clean),
            "per_bucket_p21_series_REPORTED_ONLY": _dsr(b_series, n_trials, V_bucket_clean),
        }
    dsr_binding = dsr.get("per_fold_declared_field_degenerate_excluded", {}).get("dsr", float("nan"))
    dsr_binding = float(dsr_binding) if dsr_binding is not None else float("nan")

    # ── attribution reads (declared; reported, never gated) ────────────────────────────────────
    def _delta(a: str, b: str) -> dict:
        if a in arms and b in arms:
            d = arms[b]["pooled_crps"] - arms[a]["pooled_crps"]   # >0 ⇔ a better than b
            return {"crps_a": arms[a]["pooled_crps"], "crps_b": arms[b]["pooled_crps"],
                    "a_minus_b_gain": round(float(d), 5),
                    "a_beats_b": bool(d > _TIE_BAND), "tie": bool(abs(d) <= _TIE_BAND)}
        return {}
    attribution = {
        "levels_add_beyond_composites (pace vs pace_axis)": _delta("pace", "pace_axis"),
        "margin_axis_content (pace_axis vs pace_total_axis)": _delta("pace_axis", "pace_total_axis"),
    }

    # ── verdict ────────────────────────────────────────────────────────────────────────────────
    arm_gates = bool(prim and prim["eligible"] and not prim["tie_with_foil"] and prim["gain_crps"] > 0
                     and prim["bh_pass"] and prim["fold_clause_passes"])
    pbo_ok = bool(np.isfinite(pbo) and pbo < _PBO_GATE)
    dsr_ok = bool(np.isfinite(dsr_binding) and dsr_binding >= _DSR_GATE)
    interpretable = bool(anchors_ok and repro["holds"])
    verdict = "SHIP" if (interpretable and arm_gates and pbo_ok and dsr_ok) else "REFERENCE_STANDS"
    if not interpretable:
        verdict = "NOT_INTERPRETABLE"

    # ── null classification — every non-promoted arm, on the DECLARED (per-fold) series ────────
    promoted = {PRIMARY} if verdict == "SHIP" else set()
    nulls: dict[str, Any] = {}
    for arm in real:
        if arm in promoted:
            continue
        r = rows[arm]
        sib_cleared = bool(r["eligible"] and not r["tie_with_foil"] and r["gain_crps"] > 0
                           and r["bh_pass"] and r["fold_clause_passes"])
        if arm != PRIMARY and sib_cleared:
            # ⭐ NOT A NULL. A non-primary field member that cleared every ARM-level gate is simply
            # not PROMOTABLE (the ship candidate was fixed as the primary before the run — "pick
            # the best of three" is the search this registration bounds). Running `classify_null`
            # on it would print a POWER_LIMITED default about a null that does not exist.
            nulls[arm] = {
                "is_primary": False, "arm_level_gates_cleared": True,
                "state": "FIELD_MEMBER_CLEARED_NOT_PROMOTABLE",
                "reason": "cleared every arm-level gate; not promotable — the primary was fixed as "
                          f"`{PRIMARY}` in the pre-registration. Reported as a successor "
                          "representation hypothesis, never shipped from this run.",
                "retest_trigger": None, "folds_have": n_folds, "folds_needed": None,
                "extra_seasons": None, "max_field_size": None, "field_remedy_admissible": None,
                "reclassified_from": None,
            }
            continue
        override = None
        if not r["eligible"]:
            override = ("CONSTRAINT_REFUSED",
                        f"refused by the calibration constraint ({r['ineligible_reason']}), not by "
                        "the metric — remedy is a different mechanism or a PM decision, never more "
                        "seasons (NF-D18).")
        v = cv_power.classify_null(
            metric="CRPS(margin)+CRPS(total)", n_folds=n_folds, n_arms=len(real),
            beats_foil=bool(r["gain_crps"] > 0),
            observed_sr=r["sharpe_per_fold"], var_trials_sr=V_clean, fold_wins=r["fold_wins"],
            p_one_sided=r["p_one_sided"], bh_cutoff=bh_cutoff,
            degenerates_excluded_from_v=True, var_trials_sr_with_degenerates=V_all,
            declared_field_size=DECLARED_FIELD_SIZE_S1)
        nulls[arm] = {
            "is_primary": arm == PRIMARY,
            "arm_level_gates_cleared": bool(arm == PRIMARY and arm_gates) if arm == PRIMARY else bool(
                r["eligible"] and not r["tie_with_foil"] and r["gain_crps"] > 0 and r["bh_pass"]
                and r["fold_clause_passes"]),
            "state": override[0] if override else v.state,
            "reason": override[1] if override else v.reason,
            "retest_trigger": None if override else v.retest_trigger,
            "folds_have": v.folds_have, "folds_needed": v.folds_needed,
            "extra_seasons": v.extra_seasons, "max_field_size": v.max_field_size,
            "field_remedy_admissible": v.field_remedy_admissible,
            "reclassified_from": v.state if override else None,
        }

    levers = lever_decomposition(arms, V_clean, V_bucket_clean, n_trials)

    out = {
        "story": _STORY, "decided_at": date.today().isoformat(),
        "preregistration": "ablation_results/ncaaf_p2_1_s1_preregistration.md",
        "verdict": verdict, "primary": PRIMARY,
        "interpretable": interpretable, "anchors_ok": anchors_ok, "anchor_checks": anchor_checks,
        "anchors": anchor_report, "reproduction": repro,
        "n_folds": n_folds, "n_games": doc["n_games"],
        "declared_field_size": DECLARED_FIELD_SIZE_S1, "n_trials": n_trials,
        "series": {"pbo": "per-BUCKET (8 folds × 4 quarters = 32) — P2.1's series, unchanged",
                   "dsr": "per-FOLD (8 season-forward folds) — DECLARED FORWARD, BINDING"},
        "reference": {"pooled_crps": ref_crps, "margin_calib": ref["pooled_margin_calib"],
                      "total_calib": ref["pooled_total_calib"], "h2h_brier": ref["mean_h2h_brier"],
                      "clv": ref.get("clv", {})},
        "arms": rows,
        "fold_consistency": {"n_folds": n_folds, "wins_required": clause.wins_required,
                             "attainable": clause.attainable, "false_fire": clause.attained_false_fire},
        "bh_cutoff": round(bh_cutoff, 6), "fdr_alpha": _FDR_ALPHA,
        "pbo": round(pbo, 4) if np.isfinite(pbo) else None, "pbo_gate": _PBO_GATE,
        "pbo_over": f"eligible real set + reference on the per-bucket series ({nb} buckets)",
        "dsr": dsr, "dsr_gate": _DSR_GATE, "dsr_binding_value": round(dsr_binding, 4) if np.isfinite(dsr_binding) else None,
        "V_per_fold_degenerate_excluded": V_clean, "V_per_fold_whole_field": V_all,
        "V_per_bucket_degenerate_excluded": V_bucket_clean,
        "gates": {"anchors_ok": anchors_ok, "reproduction_ok": repro["holds"],
                  "primary_arm_gates": arm_gates, "pbo_ok": pbo_ok, "dsr_ok": dsr_ok},
        "attribution": attribution, "nulls": nulls,
        "lever_decomposition": levers, "best_alpha": 0,
    }
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _DECISION_JSON.write_text(json.dumps(out, indent=2, default=float))
    _DECISION_MD.write_text(render_dossier(out))
    _print_decision(out)
    print(f"\n  → {_DECISION_JSON.relative_to(_PROJECT_ROOT)}\n  → {_DECISION_MD.relative_to(_PROJECT_ROOT)}")
    _ = args


def _print_decision(d: dict) -> None:
    print("=" * 88)
    print(f"{_STORY} DECISION — {d['n_trials']} configs, {d['n_folds']} folds, declared field "
          f"{d['declared_field_size']}, primary `{d['primary']}`")
    print("=" * 88)
    print(f"  anchors valid: {'YES ✅' if d['anchors_ok'] else 'NO ❌'}   reproduction of P2.1: "
          f"{'YES ✅' if d['reproduction']['holds'] else 'NO ❌'} (max |Δ| {d['reproduction'].get('max_abs_dev')})")
    for k, v in d["anchor_checks"].items():
        print(f"    {'✅' if v else '❌'} {k}")
    print(f"\n  reference CRPS {d['reference']['pooled_crps']:.4f}")
    print(f"  {'arm':<18}{'ΔCRPS':>9}{'folds':>7}{'p':>10}{'BH':>5}{'elig':>6}{'tie':>5}"
          f"{'SR/fold':>9}{'SR/bkt':>8}")
    for r in sorted(d["arms"].values(), key=lambda r: -r["gain_crps"]):
        print(f"  {r['arm']:<18}{r['gain_crps']:>+9.4f}{r['fold_wins']:>4}/{r['n_folds']:<2}"
              f"{r['p_one_sided']:>10.4f}{'✓' if r['bh_pass'] else '·':>5}"
              f"{'✓' if r['eligible'] else '✗':>6}{'≈' if r['tie_with_foil'] else '·':>5}"
              f"{r['sharpe_per_fold']:>9.3f}{r['sharpe_per_bucket']:>8.3f}")
    print(f"\n  PBO {d['pbo']} (gate < {d['pbo_gate']}, per-bucket)")
    for k, v in d.get("dsr", {}).items():
        if isinstance(v, dict):
            print(f"  DSR[{k}] {v['dsr']}  (SR {v['sr']} vs SR0 {v['sr0']}, N={v['n_trials']}, "
                  f"n={v['n_obs']}{'  UNDEFINED: ' + v['undefined'] if v.get('undefined') else ''})")
    print(f"  gates: {d['gates']}")
    print(f"\n  VERDICT: {d['verdict']}")


def render_dossier(d: dict) -> str:
    g = d["gates"]
    L = [f"# {_STORY} — `pace` under a lower-variance gate design (fresh §0.5 registration)", "",
         f"_Decided {d['decided_at']} · {d['n_trials']} configs · {d['n_folds']} purged folds · "
         f"{d['n_games']:,} games · declared real-arm field {d['declared_field_size']} · primary "
         f"`{d['primary']}`_", "",
         "**Pre-registration:** [`ncaaf_p2_1_s1_preregistration.md`](./ncaaf_p2_1_s1_preregistration.md)"
         " — written and committed BEFORE the first S1 score. The ONE design change vs P2.1: the DSR "
         "return series is per-FOLD (declared forward, binding); PBO stays on P2.1's per-BUCKET "
         "series. Same folds, learner, form, seed, draws; NO new feature.", "",
         "## Verdict", "", f"**{d['verdict']}**", "",
         "| gate | value | bar | |", "|---|---|---|---|",
         f"| anchors valid | {d['anchors_ok']} | all six checks | {'✅' if d['anchors_ok'] else '❌'} |",
         f"| reproduction of P2.1 (`reference` + `pace` per-fold CRPS) | max abs dev "
         f"{d['reproduction'].get('max_abs_dev')} | < {d['reproduction'].get('tolerance', _REPRO_TOL)} | "
         f"{'✅' if d['reproduction']['holds'] else '❌'} |",
         f"| primary arm-level gates (eligible · not tie · ΔCRPS>0 · BH-FDR · fold clause) | "
         f"{g['primary_arm_gates']} | all | {'✅' if g['primary_arm_gates'] else '❌'} |",
         f"| PBO (per-BUCKET series, eligible real set + reference) | {d['pbo']} | < {d['pbo_gate']} | "
         f"{'✅' if g['pbo_ok'] else '❌'} |",
         f"| **DSR (per-FOLD series, declared field, degenerate-excluded — BINDING)** | "
         f"**{d['dsr_binding_value']}** | ≥ {d['dsr_gate']} | {'✅' if g['dsr_ok'] else '❌'} |",
         f"| BH-FDR cutoff | {d['bh_cutoff']} | α = {d['fdr_alpha']} | — |",
         f"| fold-consistency (calibrated) | {d['fold_consistency']['wins_required']} of "
         f"{d['n_folds']} wins | false-fire ≤ 0.20 | — |", "",
         "## Anchors — the two-sided proof the metric is not inverted", "",
         "| anchor | reading | expectation | holds |", "|---|---|---|---|"]
    a = d["anchors"]
    if "oracle_floor" in a:
        o = a["oracle_floor"]
        L.append(f"| `oracle_peek` (ORACLE FLOOR) | CRPS {o['oracle_crps']:.4f} vs best real "
                 f"{o['best_real_crps']:.4f} | nothing may beat it | {'✅' if o['holds'] else '❌ METRIC INVERTED'} |")
    for n in ("permute", "zero_width", "max_width"):
        if n in a:
            v = a[n]
            want = {"zero_width": False, "max_width": True}.get(n)
            ok = want is None or bool(v["satisfies_coverage_floor"]) is want
            L.append(f"| `{n}` | CRPS {v['crps']:.4f}, calib80 {v['margin_calib']:.3f}/{v['total_calib']:.3f}, "
                     f"coverage floor {'satisfied' if v['satisfies_coverage_floor'] else 'FAILED'} | "
                     f"{v['expectation']} | {'✅' if (v['loses_to_reference'] and ok) else '❌'} |")
    L += ["", "## The field — both series, side by side (the audit the story asks for)", "",
          "ΔCRPS > 0 = arm beats the reference. `SR/fold` is the DECLARED DSR series (8 obs); `SR/bucket` "
          "is P2.1's gate series (32 obs) — same folds, same effect, the gap is the SERIES DEFINITION.", "",
          "| arm | ΔCRPS | fold wins | p (1-sided) | BH | eligible | tie | SR per FOLD | SR per BUCKET | state |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(d["arms"].values(), key=lambda x: -x["gain_crps"]):
        st = d["nulls"].get(r["arm"], {}).get("state", "**PROMOTED**")
        L.append(f"| `{r['arm']}`{' ⭐' if r['arm'] == d['primary'] else ''} | {r['gain_crps']:+.4f} | "
                 f"{r['fold_wins']}/{r['n_folds']} | {r['p_one_sided']:.4f} | {'✅' if r['bh_pass'] else '—'} | "
                 f"{'✅' if r['eligible'] else '❌'} | {'≈' if r['tie_with_foil'] else '—'} | "
                 f"{r['sharpe_per_fold']:.3f} | {r['sharpe_per_bucket']:.3f} | {st} |")
    prim = d["arms"].get(d["primary"], {})
    if prim:
        L += ["", f"`{d['primary']}` per-fold ΔCRPS by eval season: " +
              ", ".join(f"{y} {x:+.4f}" for y, x in zip(prim.get("fold_years") or [], prim["fold_deltas"])) + "."]
    L += ["", "## DSR — the declared series binds; the others are disclosure", "",
          "| figure | DSR | SR | SR0 | N trials | n obs | status |", "|---|---|---|---|---|---|---|"]
    for k, v in d.get("dsr", {}).items():
        if isinstance(v, dict):
            tag = ("⭐ **BINDING**" if k == d["dsr"].get("binding") else
                   ("P2.1's series — reported only" if "REPORTED" in k else "reported"))
            L.append(f"| `{k}` | {v['dsr']} | {v['sr']} | {v['sr0']} | {v['n_trials']} | {v['n_obs']} | {tag} |")
    def _v(x):
        return "—" if x is None else f"{float(x):.4f}"
    L += ["", f"`V` (cross-trial per-fold Sharpe dispersion): degenerate-excluded {_v(d['V_per_fold_degenerate_excluded'])}"
          f" · whole field {_v(d['V_per_fold_whole_field'])} · per-bucket degenerate-excluded "
          f"{_v(d['V_per_bucket_degenerate_excluded'])}.", ""]
    lv = d.get("lever_decomposition") or {}
    if lv.get("available"):
        c = lv["cells"]
        L += ["## Which lever did the work? — the 2×2 (series × field), post-verdict DISCLOSURE, never a gate", "",
              "S1 changed TWO things vs P2.1's DSR: the return SERIES (bucket→fold) and the FIELD (16 "
              "heterogeneous arms → 3 pace representations, which sets `V` and `N`). The binding cell "
              "was fixed before the run; the other three are computed from the P2.1 record so the "
              "verdict's dependence on each lever is auditable. The (bucket, P2.1 field) cell reproduces "
              "P2.1's recorded 0.0409.", "",
              f"P2.1 field: {lv['p21_field']['n_real_arms']} real arms, N = {lv['p21_field']['N']}, "
              f"V per-fold = {lv['p21_field']['V_per_fold']}, V per-bucket = {lv['p21_field']['V_per_bucket']}.", "",
              "| series ＼ field | P2.1 field (16 heterogeneous arms) | S1 field (3 pace representations) |",
              "|---|---|---|"]
        def _c(x):
            return f"DSR **{x['dsr']}** (SR {x['sr']}, SR0 {x['sr0']}, N {x['N']}, V {x['V']})" if x else "—"
        L += [f"| per-BUCKET (P2.1's series) | {_c(c['bucket__p21_field'])} ← P2.1 record | {_c(c['bucket__s1_field'])} |",
              f"| per-FOLD (S1's series) | {_c(c['fold__p21_field'])} | {_c(c['fold__s1_field__BINDING'])} ⭐ BINDING |", ""]
    L += ["## Attribution reads (declared; reported, never gated)", ""]
    for k, v in d["attribution"].items():
        L.append(f"- **{k}** — `{json.dumps(v)}`")
    L += ["", "## Null classification", "",
          f"Each non-promoted arm is classified with `cv_power.classify_null(n_arms={d['declared_field_size']}, "
          f"declared_field_size={d['declared_field_size']}, degenerates_excluded_from_v=True)` on the "
          "DECLARED per-fold series; the MACHINE flag `field_remedy_admissible` is read, not the prose (MH2.7).", "",
          "| arm | primary | arm-gates | state | field remedy admissible | re-test trigger |",
          "|---|---|---|---|---|---|"]
    for arm, v in d["nulls"].items():
        L.append(f"| `{arm}` | {'⭐' if v['is_primary'] else '—'} | {'✅' if v['arm_level_gates_cleared'] else '—'} | "
                 f"{v['state']} | {v['field_remedy_admissible']} | {v['retest_trigger'] or '—'} |")
    if not d["nulls"] or d["primary"] not in d["nulls"]:
        L.append(f"| `{d['primary']}` | ⭐ | ✅ | **PROMOTED** | — | — |")
    L += ["", "## Honest framing", "",
          f"`best_alpha = {d['best_alpha']}`. A calibration ship is **product value** (honest 3-market "
          f"probabilities), never an edge claim; the edge bar (model-side ATS/OU > {_BREAKEVEN} AND > placebo) "
          "is unchanged and unclaimed.", "",
          f"- reference vs-close: `{json.dumps(d['reference'].get('clv', {}))}`"]
    if prim:
        L.append(f"- `{d['primary']}` vs-close: `{json.dumps(prim.get('clv', {}))}`")
    L.append("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description=f"Story {_STORY} — pace under a lower-variance gate design")
    ap.add_argument("--stage", choices=["battery", "decide"], required=True)
    ap.add_argument("--no-clv", action="store_true")
    ap.add_argument("--arm", type=str, default=None, help="comma-separated subset (smoke only)")
    ap.add_argument("--max-folds", type=int, default=None)
    ap.add_argument("--n-draws", type=int, default=p21._N_DRAWS)
    args = ap.parse_args()
    if args.stage == "battery":
        stage_battery(args)
    else:
        stage_decide(args)


if __name__ == "__main__":
    main()
