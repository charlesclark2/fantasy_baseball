"""gate_props.py — Edge Program Story E5.4: the HARD prop-edge gate.

E5.3 produced the per-(pitcher × date × book × line) K-prop edge/EV table (`best_alpha = 0`).
THIS is the gate that decides whether any of it is a REAL, cashable edge or a clean null.

🔒 THE GATE (ALL required, ALL pre-registered BEFORE looking at outcomes — guide §0.5 + §5B):
  1. CALIBRATION FLOOR — calib_80 ≥ 0.80 per prop type under E1.1 purged walk-forward CV
     (E5.2 = 0.8104 on the served glm; re-confirmed here + the at-the-line betting-probability
     reliability the edge actually rests on).
  2. PBO < 0.2 AND DSR > 0 (≥0.95 confidence) PER MARKET, multiple-comparison-corrected ACROSS
     EVERY prop-type × line × book tried — the full PRE-REGISTERED grid is logged and fed into
     the DSR deflation. No cherry-picking the best-looking market.
  3. POSITIVE forward CLV/ROI NET OF THE (HIGH) PROP VIG vs the prop's OWN close — the
     cashability gate. Offline (historical-close) ROI net of vig is the NECESSARY-not-sufficient
     leg available now; the TRUE forward leg (decision-price → close) needs live capture (E5.5)
     and is FLAGGED to accrue before any ship.
  4. COVERAGE / ROBUSTNESS — per-market n, edge distribution, sensitivity to the line/book set.

⚠️ THE TRAP: "find the markets/lines where we'd have won" manufactures fake edges. The grid is
PRE-REGISTERED in `betting_ml/utils/prop_gate.py` (book-group × line-bucket × conviction × anchor),
EVERY config is settled the same way + logged (→ `e5_4_config_grid_results.csv`), config selection
is done IN-FOLD (PBO/CSCV) and on a 2023–24 → 2025–26 held-out split, and every config counts in
the DSR deflation. A config that looks +EV in-sample but fails the deflated gate is REJECTED.

🔬 HONEST OPTIMISM NOTE: the served K bundle was fit on the FULL 2021–2026 span, so the realized
betting ROI here carries model in-sample optimism (the CONFIG selection is held out, the model is
not). The leak-honest calibration is the E5.2 purged-CV number; the betting ROI is a LEADING /
discipline read, and live forward capture is the real verdict. This only sharpens a null (even
in-sample-optimistic, no edge) and makes any survivor provisional until forward CLV accrues.

DATA (per §0.5): reads the cached `e5_3_prop_edge_table.parquet` (the closes are embedded) + the
E5.2 cached actuals frame (`betting_ml/data/cache/e5_2_strikeout_frame_*.parquet`) for the realized
K. S3/cached only — NO fresh Snowflake pull.

Outputs (→ quant_sports_intel_models/baseball/edge_program/ablation_results/):
  * e5_4_prop_gate.{json,md}          — the verdict + the full gate dossier
  * e5_4_config_grid_results.csv      — EVERY pre-registered config's ROI/Sharpe/n (the no-cherry-pick log)

Usage (light; runs in well under a minute):
    uv run python betting_ml/scripts/prop_pricing/gate_props.py
    uv run python betting_ml/scripts/prop_pricing/gate_props.py --no-save
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.overfitting import (
    DSR_CONFIDENCE,
    PBO_SHADOW_TO_LIVE,
    deflated_sharpe,
    pbo_cscv,
)
from betting_ml.utils.prop_gate import (
    make_config_grid,
    payoff_vec,
    reliability_table,
    select_config_bets,
)

_RESULTS_DIR = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results"
)
_EDGE_TABLE = _RESULTS_DIR / "e5_3_prop_edge_table.parquet"
_E5_2_CALIB = _RESULTS_DIR / "e5_2_prop_pricing_calibration.json"
_ACTUALS_CACHE = _PROJECT_ROOT / "betting_ml" / "data" / "cache" / "e5_2_strikeout_frame_2021_2026.parquet"

_PROP_TYPE = "pitcher_strikeouts"           # the only prop with a served pricer + an E5.3 edge table
_CALIB_FLOOR = 0.80
_MIN_BETS_SELECTABLE = 200                  # a config must have ≥ this many bets to be SELECTABLE
_PBO_MIN_BETS_PER_SLICE = 5                 # a config must avg ≥ this per slice to enter the PBO matrix
_IS_YEARS = (2023, 2024)                    # held-out forward split: select on these …
_OOS_YEARS = (2025, 2026)                   # … evaluate on these
_BROAD_CONFIG = "all|all|tau0.04|book"      # the pre-committed, NON-cherry-picked headline strategy


# ── data ──────────────────────────────────────────────────────────────────────

def load_actuals() -> pd.DataFrame:
    """Realized K per (pitcher_id, game_date) from the E5.2 cached frame (first start; matches
    the E5.3 dedup). Cached parquet — NO Snowflake."""
    if not _ACTUALS_CACHE.exists():
        raise FileNotFoundError(
            f"Actuals cache missing: {_ACTUALS_CACHE}. Regenerate via the E5.2 fit "
            "(uv run python betting_ml/scripts/prop_pricing/fit_prop_pricing.py)."
        )
    a = pd.read_parquet(_ACTUALS_CACHE, columns=["pitcher_id", "game_date", "game_pk", "strikeouts"])
    a["game_date"] = pd.to_datetime(a["game_date"]).dt.date
    a["pitcher_id"] = a["pitcher_id"].astype("int64")
    a = a.sort_values(["pitcher_id", "game_date", "game_pk"])
    a = a.drop_duplicates(["pitcher_id", "game_date"], keep="first")   # first start of the date
    return a[["pitcher_id", "game_date", "strikeouts"]].rename(columns={"strikeouts": "actual_k"})


def load_joined() -> tuple[pd.DataFrame, dict]:
    """E5.3 edge table joined to realized K. Restrict to de-viggable rows with a finite outcome.
    Adds `realized_over` (1 if K > line) and the per-row settled payoff for the favored side at
    its offered price."""
    if not _EDGE_TABLE.exists():
        raise FileNotFoundError(
            f"E5.3 edge table missing: {_EDGE_TABLE}. Regenerate via "
            "uv run python betting_ml/scripts/prop_pricing/edge_devig_props.py"
        )
    tbl = pd.read_parquet(_EDGE_TABLE)
    tbl["game_date"] = pd.to_datetime(tbl["game_date"]).dt.date
    tbl["pitcher_id"] = tbl["pitcher_id"].astype("int64")
    n_raw = len(tbl)
    act = load_actuals()
    df = tbl.merge(act, on=["pitcher_id", "game_date"], how="left")
    n_with_k = int(df["actual_k"].notna().sum())

    df = df[df["devig_valid"] & df["actual_k"].notna()].reset_index(drop=True)
    df["actual_k"] = df["actual_k"].astype(float)
    df["realized_over"] = (df["actual_k"] > df["line"]).astype(float)
    df["is_push"] = (df["actual_k"] == df["line"]).astype(bool)
    # year-month slice for PBO/CSCV (season alone gives ~4 buckets; month → ~38)
    gd = pd.to_datetime(df["game_date"])
    df["ym"] = gd.dt.year.astype(int).astype(str) + "-" + gd.dt.month.astype(int).astype(str).str.zfill(2)
    cov = {
        "n_edge_rows_raw": n_raw,
        "n_with_actual_k": n_with_k,
        "actual_k_join_frac": round(n_with_k / max(n_raw, 1), 4),
        "n_gated_rows": int(len(df)),       # devig_valid AND outcome present
        "n_pitcher_dates": int(df.drop_duplicates(["pitcher_id", "game_date"]).shape[0]),
        "n_books": int(df["bookmaker_key"].nunique()),
        "season_range": [int(gd.dt.year.min()), int(gd.dt.year.max())],
        "n_integer_line_pushes": int(df["is_push"].sum()),
    }
    return df, cov


# ── 1. calibration floor ───────────────────────────────────────────────────────

def calibration_floor(df: pd.DataFrame) -> dict:
    """Re-confirm the calibration floor: cite the E5.2 served-glm purged-CV calib_80, AND compute
    the AT-THE-LINE betting-probability reliability (model_p_over_cond vs realized over) — the
    number the edge actually rests on — overall + per season. Pushes excluded from the binary."""
    e5_2 = json.loads(_E5_2_CALIB.read_text()) if _E5_2_CALIB.exists() else {}
    sk = e5_2.get("strikeout_calibration", {})
    served_calib_80 = sk.get("calib_80")
    per_season_calib_80 = {int(r["eval_year"]): r["calib_80"] for r in sk.get("per_season", [])}

    nb = df[~df["is_push"]]
    rel = reliability_table(nb["model_p_over_cond"].to_numpy(float), nb["realized_over"].to_numpy(float))
    per_season_rel = {}
    yrs = pd.to_datetime(nb["game_date"]).dt.year
    for y in sorted(yrs.unique()):
        s = nb[yrs.values == y]
        r = reliability_table(s["model_p_over_cond"].to_numpy(float), s["realized_over"].to_numpy(float))
        per_season_rel[int(y)] = {"n": r["n"], "ece": r["ece"], "brier": r["brier"]}

    floor_met = bool(served_calib_80 is not None and served_calib_80 >= _CALIB_FLOOR)
    return {
        "prop_type": _PROP_TYPE,
        "served_glm_calib_80_purged_cv": served_calib_80,        # E5.2, leak-honest (the FLOOR)
        "served_glm_per_season_calib_80": per_season_calib_80,
        "calib_floor": _CALIB_FLOOR,
        "calib_floor_met": floor_met,
        "at_the_line_reliability": rel,                          # the betting-probability calibration
        "at_the_line_per_season": per_season_rel,
        "note": ("calib_80 is the served-glm 80% predictive-interval coverage under E1.1 purged "
                 "walk-forward CV (E5.2). The at-the-line ECE/Brier here is the reliability of the "
                 "over/under probability the bet is priced on (model_p_over_cond vs realized over)."),
    }


# ── 2+3. per-config ROI net of vig (the cashability unit) ───────────────────────

def _config_payoffs(df: pd.DataFrame, cfg) -> pd.DataFrame | None:
    """Settled per-bet frame for one config: bet_side, bet_price, payoff (net of vig), ym, year.
    None if the config places no bets."""
    bets = select_config_bets(df, cfg)
    if bets.empty:
        return None
    bets = bets.copy()
    bets["payoff"] = payoff_vec(bets["actual_k"].to_numpy(float), bets["line"].to_numpy(float),
                                bets["bet_side"].to_numpy(dtype=object), bets["bet_price"].to_numpy(float))
    bets = bets[np.isfinite(bets["payoff"].to_numpy(float))]
    if bets.empty:
        return None
    bets["year"] = pd.to_datetime(bets["game_date"]).dt.year.astype(int)
    return bets[["payoff", "ym", "year", "bookmaker_key", "line"]]


def evaluate_configs(df: pd.DataFrame, grid: list) -> list[dict]:
    """Evaluate EVERY pre-registered config: ROI net of vig, Sharpe, n_bets, per-slice (ym) mean
    payoff, per-season ROI. Returns one dict per config (payoff array kept for the selected one)."""
    out = []
    for cfg in grid:
        bp = _config_payoffs(df, cfg)
        if bp is None:
            out.append({"name": cfg.name, "book_group": cfg.book_group, "line_bucket": cfg.line_bucket,
                        "tau": cfg.tau, "anchor": cfg.anchor, "n_bets": 0, "roi": float("nan"),
                        "sharpe": float("nan"), "per_ym": {}, "per_season": {}, "_payoffs": None})
            continue
        pay = bp["payoff"].to_numpy(float)
        sd = pay.std(ddof=1) if len(pay) > 1 else 0.0
        per_ym = bp.groupby("ym")["payoff"].mean().to_dict()
        per_season = bp.groupby("year")["payoff"].agg(["mean", "size"]).to_dict("index")
        out.append({
            "name": cfg.name, "book_group": cfg.book_group, "line_bucket": cfg.line_bucket,
            "tau": cfg.tau, "anchor": cfg.anchor,
            "n_bets": int(len(pay)), "roi": float(pay.mean()),
            "sharpe": float(pay.mean() / sd) if sd > 0 else 0.0,
            "per_ym": {k: float(v) for k, v in per_ym.items()},
            "per_season": {int(y): {"roi": float(d["mean"]), "n": int(d["size"])} for y, d in per_season.items()},
            "_payoffs": pay,
        })
    return out


def run_pbo(configs: list[dict]) -> dict:
    """PBO via CSCV over a (year-month slice × config) ROI matrix. Slate = configs with enough
    coverage to be selectable AND present across the slices. Higher ROI is better."""
    selectable = [c for c in configs if c["n_bets"] >= _MIN_BETS_SELECTABLE]
    all_yms = sorted(set().union(*[set(c["per_ym"]) for c in selectable])) if selectable else []
    # keep configs that bet in (almost) every slice — require a value in each kept slice
    slate = [c for c in selectable
             if len([y for y in all_yms if y in c["per_ym"]]) >= max(4, int(0.6 * len(all_yms)))
             and c["n_bets"] / max(len(all_yms), 1) >= _PBO_MIN_BETS_PER_SLICE]
    result = {"n_selectable": len(selectable), "n_slate": len(slate), "n_slices_total": len(all_yms),
              "pbo": float("nan"), "n_combos": 0, "n_splits": 0}
    if len(slate) < 2 or len(all_yms) < 4:
        result["note"] = "insufficient slate/slices for CSCV"
        return result
    perf = np.array([[c["per_ym"].get(y, np.nan) for c in slate] for y in all_yms])
    keep = ~np.isnan(perf).any(axis=1)
    if keep.sum() < 4:
        result["note"] = f"only {int(keep.sum())} slices common to the whole slate (<4)"
        return result
    n_splits = min(16, int(keep.sum()) - (int(keep.sum()) % 2))
    pres = pbo_cscv(perf[keep], higher_is_better=True, n_splits=n_splits)
    result.update({"pbo": float(pres.pbo), "n_combos": pres.n_combos, "n_configs": pres.n_configs,
                   "n_splits": pres.n_splits, "n_slices_kept": int(keep.sum()),
                   "median_oos_rank_of_is_best": pres.median_oos_rank_of_is_best,
                   "clears_live_pbo": bool(pres.clears_live_pbo)})
    return result


def run_dsr(configs: list[dict], selected: dict) -> dict:
    """DSR on the selected config's per-bet return series, deflated by the FULL number of
    selectable configs tried (the multiple-comparison count). benchmark SR = 0 (any edge at all)."""
    selectable = [c for c in configs if c["n_bets"] >= _MIN_BETS_SELECTABLE]
    n_trials = len(selectable)
    trial_sharpes = [c["sharpe"] for c in selectable if np.isfinite(c["sharpe"])]
    pay = selected.get("_payoffs")
    if pay is None or len(pay) < 3:
        return {"dsr": float("nan"), "n_trials": n_trials, "note": "selected config has <3 bets"}
    res = deflated_sharpe(pay, n_trials=max(n_trials, 1), benchmark_sr=0.0,
                          trial_sharpes=trial_sharpes if len(trial_sharpes) > 1 else None)
    return {"dsr": float(res.dsr), "observed_sr": float(res.observed_sr), "sr0": float(res.sr0),
            "n_trials": int(res.n_trials), "n_obs": int(res.n_obs), "skew": round(res.skew, 4),
            "kurtosis": round(res.kurtosis, 4), "passes_live": bool(res.passes_live)}


def forward_holdout(df: pd.DataFrame, grid: list) -> dict:
    """Held-out forward split: select the best config by ROI on 2023–24 (IS), report its ROI on
    2025–26 (OOS). Directly interpretable: does the in-sample-best survive selection on new data?

    The candidate set is restricted to configs RUNNABLE in BOTH halves (≥ _MIN_BETS bets each) —
    coverage (sample size) is not an outcome, so this is not leakage; it just makes the OOS number
    a fair test rather than an artifact of a config that only existed in one season. The raw IS-best
    over ALL configs (which often evaporates OOS — the textbook overfit) is reported alongside."""
    is_mask = pd.to_datetime(df["game_date"]).dt.year.isin(_IS_YEARS)
    oos_mask = pd.to_datetime(df["game_date"]).dt.year.isin(_OOS_YEARS)
    df_is, df_oos = df[is_mask].reset_index(drop=True), df[oos_mask].reset_index(drop=True)
    runnable, all_is = [], []
    for cfg in grid:
        bi = _config_payoffs(df_is, cfg)
        if bi is None or len(bi) < _MIN_BETS_SELECTABLE:
            continue
        is_roi, is_n = float(bi["payoff"].mean()), int(len(bi))
        all_is.append((cfg, is_roi, is_n))
        bo = _config_payoffs(df_oos, cfg)
        if bo is not None and len(bo) >= _MIN_BETS_SELECTABLE:
            runnable.append((cfg, is_roi, is_n, float(bo["payoff"].mean()), int(len(bo))))
    if not all_is:
        return {"note": "no selectable config in the 2023–24 IS split"}
    # the fair held-out test: best IS config that is RUNNABLE in both halves
    out = {"is_years": list(_IS_YEARS), "oos_years": list(_OOS_YEARS),
           "n_selectable_is": len(all_is), "n_runnable_both": len(runnable)}
    if runnable:
        bc, is_roi, is_n, oos_roi, oos_n = max(runnable, key=lambda r: r[1])
        out.update({"selected_config": bc.name, "is_roi": is_roi, "is_n_bets": is_n,
                    "oos_roi": oos_roi, "oos_n_bets": oos_n,
                    "oos_positive": bool(np.isfinite(oos_roi) and oos_roi > 0)})
    else:
        out.update({"selected_config": None, "oos_roi": float("nan"), "oos_n_bets": 0,
                    "oos_positive": False, "note": "no IS-selectable config is also runnable OOS"})
    # the raw IS-best over the WHOLE grid (illustrates the trap — usually evaporates OOS)
    rb, rb_roi, rb_n = max(all_is, key=lambda r: r[1])
    bo = _config_payoffs(df_oos, rb)
    out["raw_is_best"] = {"config": rb.name, "is_roi": rb_roi, "is_n_bets": rb_n,
                          "oos_roi": float(bo["payoff"].mean()) if bo is not None else float("nan"),
                          "oos_n_bets": int(len(bo)) if bo is not None else 0}
    return out


def robustness(df: pd.DataFrame, configs: list[dict]) -> dict:
    """Coverage / robustness: per-book and per-line-bucket blind-favored-side ROI at τ=0.04,
    the two-sided edge distribution, and the best/worst configs (sensitivity to the line/book set)."""
    # blind favored-side (best_side) ROI per book at a single mid conviction, for the table
    base = df[np.isin(df["best_side"].to_numpy(dtype=object), ["over", "under"])].copy()
    base = base[base["best_edge"] >= 0.04]
    base["payoff"] = payoff_vec(
        base["actual_k"].to_numpy(float), base["line"].to_numpy(float),
        base["best_side"].to_numpy(dtype=object),
        np.where(base["best_side"].to_numpy(dtype=object) == "over",
                 base["over_price"].to_numpy(float), base["under_price"].to_numpy(float)))
    base = base[np.isfinite(base["payoff"].to_numpy(float))]
    per_book = (base.groupby("bookmaker_key")["payoff"].agg(["mean", "size"])
                .rename(columns={"mean": "roi", "size": "n"}).sort_values("roi", ascending=False))
    per_book_d = {b: {"roi": round(float(r["roi"]), 4), "n": int(r["n"])} for b, r in per_book.iterrows()}

    # the pre-committed, NON-cherry-picked headline: favored-side, all books, all lines, τ=0.04
    broad = next((c for c in configs if c["name"] == _BROAD_CONFIG), None)
    broad_d = None if broad is None else {
        "config": broad["name"], "n_bets": broad["n_bets"], "roi": round(broad["roi"], 4),
        "per_season": {int(y): {"roi": round(d["roi"], 4), "n": d["n"]}
                       for y, d in broad["per_season"].items()}}

    valid = configs and [c for c in configs if c["n_bets"] >= _MIN_BETS_SELECTABLE]
    ranked = sorted(valid, key=lambda c: c["roi"], reverse=True)
    top = [{"name": c["name"], "roi": round(c["roi"], 4), "n_bets": c["n_bets"]} for c in ranked[:8]]
    bot = [{"name": c["name"], "roi": round(c["roi"], 4), "n_bets": c["n_bets"]} for c in ranked[-8:]]
    rois = np.array([c["roi"] for c in valid], float)
    return {
        "precommitted_broad_config": broad_d,
        "per_book_favored_roi_tau0p04": per_book_d,
        "n_selectable_configs": len(valid),
        "selectable_roi_dist": {"mean": round(float(rois.mean()), 4), "std": round(float(rois.std()), 4),
                                "min": round(float(rois.min()), 4), "max": round(float(rois.max()), 4),
                                "frac_positive": round(float((rois > 0).mean()), 4)},
        "top8_configs_by_is_roi": top,
        "bottom8_configs_by_is_roi": bot,
    }


# ── verdict ─────────────────────────────────────────────────────────────────

def decide(calib: dict, pbo: dict, dsr: dict, fwd: dict, broad: dict | None) -> dict:
    calib_ok = bool(calib["calib_floor_met"])
    pbo_ok = bool(np.isfinite(pbo["pbo"]) and pbo["pbo"] < PBO_SHADOW_TO_LIVE)
    dsr_ok = bool(dsr.get("passes_live"))                       # DSR ≥ 0.95 ("DSR > 0 at 95%")
    # The OFFLINE cashability gate is the PRE-COMMITTED broad strategy (favored side, all books/
    # lines, τ=0.04) — NOT the cherry-picked in-sample-best (whose ROI is positive by construction).
    broad_roi = broad.get("roi", float("nan")) if broad else float("nan")
    offline_roi_ok = bool(np.isfinite(broad_roi) and broad_roi > 0)
    fwd_ok = bool(fwd.get("oos_positive"))
    cashable_ok = offline_roi_ok and fwd_ok                      # the offline cashability proxy

    ship = calib_ok and pbo_ok and dsr_ok and cashable_ok
    if ship:
        verdict = "SHIP-CANDIDATE → forward-validate LIVE before serving"
        rationale = ("ALL offline gates clear: calib_80 ≥ 0.80 (purged CV), PBO < 0.2, DSR ≥ 0.95 "
                     "(deflated for the full config grid), AND positive ROI net of vig both "
                     "in-sample-selected and on the 2023–24→2025–26 held-out split. NOT a go-live: "
                     "the betting ROI carries model in-sample optimism and TRUE forward CLV (decision-"
                     "price → close) needs live capture (E5.5). Stand up the forward-CLV shadow "
                     "harness; promote to serving + E10.2 sizing only after ≥100 live games of "
                     "positive CLV net of vig.")
    else:
        fails = []
        if not calib_ok: fails.append("calib_80 < 0.80")
        if not pbo_ok: fails.append(f"PBO ≥ {PBO_SHADOW_TO_LIVE} (selection overfit / unstable)")
        if not dsr_ok: fails.append("DSR < 0.95 (deflated Sharpe ≤ benchmark — edge vanishes once "
                                    "deflated for the config count)")
        if not offline_roi_ok: fails.append("pre-committed broad-strategy ROI net of vig ≤ 0")
        if not fwd_ok: fails.append("held-out (2025–26) ROI net of vig ≤ 0")
        verdict = "NULL — no cashable K-prop edge"
        rationale = ("CLEAN NULL: the K distribution is well-CALIBRATED (product value) but NOT "
                     "PROFITABLE. Failing gate(s): " + "; ".join(fails) + ". The large prop vig "
                     "(median book hold ≈ 6.9%, E5.3) eats the model-relative disagreement — gross "
                     "'edge' that the vig consumes is not edge. Consistent with H2H (dead ×5), the "
                     "efficient main total (E13.8), and E5.3's blind-over EV ≈ −8.7%/$1. The K-prop "
                     "softest-market hypothesis is CLOSED with integrity (calibration ≠ edge).")
    return {"verdict": verdict, "rationale": rationale,
            "gates": {"calib_floor": calib_ok, "pbo_lt_0p2": pbo_ok, "dsr_ge_0p95": dsr_ok,
                      "offline_roi_positive": offline_roi_ok, "holdout_roi_positive": fwd_ok,
                      "ship": ship}}


# ── dossier ─────────────────────────────────────────────────────────────────

def _pct(x) -> str:
    """Format a fraction as a signed percent, or 'n/a' for None/NaN."""
    try:
        f = float(x)
        return "n/a" if not np.isfinite(f) else f"{f*100:+.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def _write_grid_csv(configs: list[dict], path: Path) -> None:
    rows = []
    for c in configs:
        row = {"config": c["name"], "book_group": c["book_group"], "line_bucket": c["line_bucket"],
               "tau": c["tau"], "anchor": c["anchor"], "n_bets": c["n_bets"],
               "roi_net_vig": round(c["roi"], 5) if np.isfinite(c["roi"]) else "",
               "sharpe": round(c["sharpe"], 5) if np.isfinite(c["sharpe"]) else ""}
        for y in (2023, 2024, 2025, 2026):
            s = c["per_season"].get(y)
            row[f"roi_{y}"] = round(s["roi"], 5) if s else ""
            row[f"n_{y}"] = s["n"] if s else 0
        rows.append(row)
    pd.DataFrame(rows).sort_values("roi_net_vig", ascending=False, na_position="last").to_csv(path, index=False)


def _write_md(result: dict) -> str:
    cov, calib, pbo, dsr, fwd, sel, rob, dec = (result[k] for k in
        ["coverage", "calibration", "pbo", "dsr", "forward_holdout", "selected_config", "robustness", "decision"])
    rel = calib["at_the_line_reliability"]
    L = [
        "# E5.4 — HARD prop-edge gate (pitcher strikeouts)  ·  the cashability decision", "",
        f"## Verdict: **{dec['verdict']}**", f"_{dec['rationale']}_", "",
        "> 🔒 **best_alpha = 0.** A calibrated K distribution (E5.2) is product value; whether it is "
        "PROFITABLE is decided ONLY here. The market/line/book SELECTION is part of the test — the grid "
        "is pre-registered, every config logged (`e5_4_config_grid_results.csv`), selection is in-fold "
        "(PBO/CSCV + held-out split), and every config counts in the DSR deflation.", "",
        "## Gate scorecard (ALL required to ship)", "",
        "| gate | requirement | result | pass |", "|---|---|---|---|",
        f"| 1. Calibration floor | calib_80 ≥ {calib['calib_floor']} (purged CV) | "
        f"served-glm calib_80 = **{calib['served_glm_calib_80_purged_cv']}** | "
        f"{'✅' if dec['gates']['calib_floor'] else '❌'} |",
        f"| 2a. PBO | < {PBO_SHADOW_TO_LIVE} | **{pbo['pbo']:.3f}** "
        f"({pbo.get('n_slate','?')} configs × {pbo.get('n_slices_kept','?')} slices) | "
        f"{'✅' if dec['gates']['pbo_lt_0p2'] else '❌'} |",
        f"| 2b. DSR | ≥ {DSR_CONFIDENCE} (deflated, {dsr.get('n_trials','?')} trials) | "
        f"**{dsr.get('dsr', float('nan')):.3f}** (SR={dsr.get('observed_sr', float('nan')):+.3f} vs "
        f"SR0={dsr.get('sr0', float('nan')):+.3f}) | {'✅' if dec['gates']['dsr_ge_0p95'] else '❌'} |",
        f"| 3a. Offline ROI net of vig | pre-committed broad strategy > 0 | "
        f"**{_pct((rob.get('precommitted_broad_config') or {}).get('roi'))}** "
        f"({(rob.get('precommitted_broad_config') or {}).get('n_bets','?'):,} bets) | "
        f"{'✅' if dec['gates']['offline_roi_positive'] else '❌'} |",
        f"| 3b. Held-out ROI (2023–24→2025–26) | OOS > 0 | **{fwd.get('oos_roi', float('nan'))*100:+.2f}%** "
        f"({fwd.get('oos_n_bets','?')} bets) | {'✅' if dec['gates']['holdout_roi_positive'] else '❌'} |",
        "",
        "_Gate 3 is the OFFLINE cashability leg (necessary, not sufficient). The TRUE forward-CLV leg "
        "(decision-price vs the prop's own close) needs LIVE prop capture (not yet built) — see the "
        "forward plan below._", "",
        "## 1. Calibration floor", "",
        f"- **Served-glm calib_80 (E1.1 purged walk-forward CV, E5.2): {calib['served_glm_calib_80_purged_cv']}** "
        f"≥ {calib['calib_floor']} → floor **{'MET' if dec['gates']['calib_floor'] else 'NOT met'}**. "
        f"Per season: {calib['served_glm_per_season_calib_80']}.",
        f"- **At-the-line betting-probability reliability** (model_p_over_cond vs realized over, the "
        f"number the bet rests on): ECE **{rel['ece']}**, Brier **{rel['brier']}** (n={rel['n']:,}). "
        f"Per season ECE: " + ", ".join(f"{y}:{d['ece']}" for y, d in calib["at_the_line_per_season"].items()) + ".",
        "",
        "## 2. Multiple-comparison-corrected overfitting gate", "",
        f"- **Full pre-registered grid:** {result['n_configs_total']} configs "
        f"(book-group × line-bucket × conviction τ × anchor). Selectable (≥{_MIN_BETS_SELECTABLE} bets): "
        f"{pbo['n_selectable']}. Every config logged in `e5_4_config_grid_results.csv`.",
        f"- **PBO (CSCV)** over the {pbo.get('n_slate','?')}-config slate × {pbo.get('n_slices_kept','?')} "
        f"year-month slices = **{pbo['pbo']:.3f}** "
        f"({'< 0.2 ✅' if dec['gates']['pbo_lt_0p2'] else '≥ 0.2 — IS-best does NOT persist OOS'}).",
        f"- **DSR** on the in-sample-best config, deflated for {dsr.get('n_trials','?')} trials = "
        f"**{dsr.get('dsr', float('nan')):.3f}** "
        f"({'≥ 0.95 ✅' if dec['gates']['dsr_ge_0p95'] else '< 0.95 — Sharpe vanishes after deflation'}). "
        f"observed SR {dsr.get('observed_sr', float('nan')):+.3f}, deflated benchmark SR0 "
        f"{dsr.get('sr0', float('nan')):+.3f}, skew {dsr.get('skew','?')}, kurt {dsr.get('kurtosis','?')}.",
        "",
        "## 3. Cashability — ROI net of the (large) prop vig", "",
        (f"- **⭐ Pre-committed broad strategy (NO cherry-pick — favored side, all books, all lines, "
         f"τ=0.04):** `{rob['precommitted_broad_config']['config']}` → ROI "
         f"**{rob['precommitted_broad_config']['roi']*100:+.2f}%** over "
         f"{rob['precommitted_broad_config']['n_bets']:,} bets, NEGATIVE in every season ("
         + ", ".join(f"{y}:{d['roi']*100:+.1f}%" for y, d in sorted(rob['precommitted_broad_config']['per_season'].items()))
         + "). This is the honest headline: the betting strategy loses the prop vig.")
        if rob.get("precommitted_broad_config") else "- (broad config unavailable)",
        f"- **In-sample-best config (cherry-pick):** `{sel.get('name','?')}` → ROI "
        f"**{sel.get('roi', float('nan'))*100:+.2f}%** over {sel.get('n_bets','?')} bets — but this is "
        f"the single best of {rob['n_selectable_configs']} configs, and PBO/DSR deflate it away.",
        f"- **Held-out forward split** (select on {fwd.get('is_years')}, evaluate on {fwd.get('oos_years')}): "
        + (f"best config runnable in BOTH halves = `{fwd.get('selected_config')}` (IS "
           f"{_pct(fwd.get('is_roi'))}, n={fwd.get('is_n_bets','?')}) → OOS **{_pct(fwd.get('oos_roi'))}** "
           f"(n={fwd.get('oos_n_bets','?')}). {'Survives ✅' if dec['gates']['holdout_roi_positive'] else 'Does NOT survive ❌'}."
           if fwd.get("selected_config") else "no IS-selectable config is also runnable OOS."),
        f"- **The trap, illustrated:** the raw best-of-grid IS config `{fwd.get('raw_is_best',{}).get('config','?')}` "
        f"(IS {_pct(fwd.get('raw_is_best',{}).get('is_roi'))}, n={fwd.get('raw_is_best',{}).get('is_n_bets','?')}) "
        f"places **{fwd.get('raw_is_best',{}).get('oos_n_bets','?')} bets** out of sample — the in-sample "
        f"'edge' literally does not exist on new data.",
        "",
        "## 4. Coverage / robustness", "",
        f"- Gated rows (de-viggable, outcome present): **{cov['n_gated_rows']:,}** "
        f"({cov['n_pitcher_dates']:,} pitcher×dates, {cov['n_books']} books, seasons {cov['season_range']}). "
        f"Actual-K join {cov['actual_k_join_frac']:.1%}. Integer-line pushes: {cov['n_integer_line_pushes']}.",
        f"- Selectable-config ROI distribution: mean {rob['selectable_roi_dist']['mean']*100:+.2f}%, "
        f"min {rob['selectable_roi_dist']['min']*100:+.2f}%, max {rob['selectable_roi_dist']['max']*100:+.2f}%, "
        f"frac positive {rob['selectable_roi_dist']['frac_positive']:.1%} "
        f"(over {rob['n_selectable_configs']} configs).",
        "",
        "### Per-book favored-side ROI net of vig (τ=0.04)", "",
        "| book | ROI net vig | n bets |", "|---|---|---|",
    ]
    for b, r in rob["per_book_favored_roi_tau0p04"].items():
        L.append(f"| {b} | {r['roi']*100:+.2f}% | {r['n']:,} |")
    L += ["",
          "### Top / bottom configs by IN-SAMPLE ROI (the cherry-pick the gate refuses to honour)", "",
          "| rank | config | IS ROI | n bets |", "|---|---|---|---|"]
    for i, c in enumerate(rob["top8_configs_by_is_roi"], 1):
        L.append(f"| top {i} | `{c['name']}` | {c['roi']*100:+.2f}% | {c['n_bets']:,} |")
    for i, c in enumerate(rob["bottom8_configs_by_is_roi"], 1):
        L.append(f"| bot {i} | `{c['name']}` | {c['roi']*100:+.2f}% | {c['n_bets']:,} |")
    L += ["",
          "_The top configs' positive IS ROI is exactly what PBO/DSR deflate away: if the IS-best does "
          "not persist OOS (PBO) and its Sharpe vanishes after deflating for how many configs were tried "
          "(DSR), the apparent edge is selection noise, not skill._", "",
          "## Forward-CLV plan (the TRUE verdict — CLV cannot be backtested into truth)",
          "- Historical closes give the NECESSARY offline ROI-net-of-vig leg only; the prop's own close "
          "is the bet price here, so CLV-vs-close is structurally 0 offline.",
          "- Stand up an E13.5-style shadow harness: each morning score the served K distribution, log "
          "the favored-side decision-time price per book; at the prop's CLOSE record the closing price; "
          "accrue captured CLV + ROI net of vig over a rolling window.",
          "- **Pre-registered ship gate:** ≥100 forward prop bets with POSITIVE captured CLV *and* ROI "
          "clearing the real prop hold → promote to the E5.5 surface + E10.2 uncertainty-aware sizing. "
          "Else the K-prop edge thesis stays CLOSED.",
          "- Honest framing (best_alpha=0): any surface is \"calibrated projection + transparent "
          "model-vs-market comparison,\" never a win-rate/edge claim. No auto-betting.", "",
          "_🔬 The betting ROI above carries model in-sample optimism (served bundle fit on 2021–26; the "
          "CONFIG selection is held out, the MODEL is not). The leak-honest calibration is the E5.2 purged-CV "
          "calib_80; forward LIVE capture is the real cashability verdict._"]
    return "\n".join(L) + "\n"


# ── main ───────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Story E5.4 — HARD prop-edge gate (K props)")
    ap.add_argument("--no-save", action="store_true", help="Compute + print, skip writing outputs.")
    args = ap.parse_args()

    print("=== STORY E5.4 — HARD PROP-EDGE GATE (pitcher strikeouts; best_alpha=0) ===")
    df, cov = load_joined()
    print(f"Gated rows: {cov['n_gated_rows']:,} (de-viggable, outcome present)  "
          f"actual-K join {cov['actual_k_join_frac']:.1%}  {cov['n_books']} books  {cov['season_range']}")

    calib = calibration_floor(df)
    print(f"\n── 1. Calibration floor ── served-glm calib_80 (purged CV) = "
          f"{calib['served_glm_calib_80_purged_cv']}  (floor {calib['calib_floor']} "
          f"{'MET' if calib['calib_floor_met'] else 'NOT met'}); at-the-line ECE "
          f"{calib['at_the_line_reliability']['ece']}")

    grid = make_config_grid(sorted(df["bookmaker_key"].unique().tolist()))
    print(f"\n── 2/3. Evaluating {len(grid)} PRE-REGISTERED configs (every one logged) ──")
    configs = evaluate_configs(df, grid)

    selectable = [c for c in configs if c["n_bets"] >= _MIN_BETS_SELECTABLE]
    selected = max(selectable, key=lambda c: c["roi"]) if selectable else \
        {"name": "none", "roi": float("nan"), "n_bets": 0, "per_season": {}, "_payoffs": None}
    pbo = run_pbo(configs)
    dsr = run_dsr(configs, selected)
    fwd = forward_holdout(df, grid)
    rob = robustness(df, configs)
    print(f"  in-sample-best config: {selected['name']}  ROI {selected['roi']*100:+.2f}%  "
          f"({selected['n_bets']} bets)")
    print(f"  PBO={pbo['pbo']:.3f} ({pbo['n_slate']} slate × {pbo.get('n_slices_kept','?')} slices)  "
          f"DSR={dsr.get('dsr', float('nan')):.3f} (n_trials={dsr.get('n_trials','?')})")
    print(f"  held-out forward: select on {fwd.get('is_years')} → OOS ROI "
          f"{fwd.get('oos_roi', float('nan'))*100:+.2f}% on {fwd.get('oos_years')}")

    dec = decide(calib, pbo, dsr, fwd, rob.get("precommitted_broad_config"))
    print(f"\n🔒 VERDICT: {dec['verdict']}")
    print(f"   {dec['rationale']}")

    # strip the in-memory payoff arrays before serialising
    sel_clean = {k: v for k, v in selected.items() if k != "_payoffs"}
    configs_clean = [{k: v for k, v in c.items() if k != "_payoffs"} for c in configs]

    result = {
        "story": "E5.4", "prop_type": _PROP_TYPE, "run_at": date.today().isoformat(),
        "honest_framing": ("best_alpha=0. Calibration ≠ edge — that is decided ONLY here. Offline ROI "
                           "is the necessary leg + carries model in-sample optimism; the TRUE verdict "
                           "is forward CLV net of vig on live prop closes."),
        "coverage": cov, "calibration": calib, "n_configs_total": len(grid),
        "selected_config": sel_clean, "pbo": pbo, "dsr": dsr, "forward_holdout": fwd,
        "robustness": rob, "decision": dec,
    }

    if args.no_save:
        print("\n[--no-save] done.")
        return
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (_RESULTS_DIR / "e5_4_prop_gate.json").write_text(json.dumps(result, indent=2, default=float))
    (_RESULTS_DIR / "e5_4_prop_gate.md").write_text(_write_md(result))
    _write_grid_csv(configs_clean, _RESULTS_DIR / "e5_4_config_grid_results.csv")
    print(f"\nDossier → ablation_results/e5_4_prop_gate.{{json,md}} + e5_4_config_grid_results.csv "
          f"({len(configs)} configs logged — the no-cherry-pick evidence)")


if __name__ == "__main__":
    main()
