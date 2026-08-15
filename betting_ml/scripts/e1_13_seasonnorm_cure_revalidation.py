"""e1_13_seasonnorm_cure_revalidation.py — MLB Edge E1.13: the §0.5 retrain-vs-incumbent
decision for the ONE served contract the E9.53 seasonnorm NULL cure reaches.

WHY THIS EXISTS
---------------
E1.13 applied the E9.53 seasonnorm NULL cure (a missing RAW feature is now served as NULL,
never a fabricated 0.0 "exactly league average") in BOTH copies of the wrapper expression.
That changes a SERVED model input, and the served-contract intersection (recorded in
ablation_results/e1_13_injury_seasonnorm_revalidation.md) found it reaches exactly ONE of
the six served champion contracts:

    total_runs / pre_lineup — feature_columns_v6_total_runs_pre_lineup_served.json,
    6 of its 14 base features are `_seasonnorm` columns.

The champion pickle was fit on data where a raw-NULL row carried the fabricated 0.0; after
the cure, serving routes those rows through the artifact's imputer instead. Measured
exposure: 290 of 14,017 rows 2021–2026 (2.07%) carry ≥1 fabricated value among the six.
This harness answers, under §0.5 discipline, whether that earns a REFIT of the champion or
the incumbent stands.

THE PRE-REGISTERED DESIGN (locks, stated in source before any arm is scored)
----------------------------------------------------------------------------
TARGET/TIER  total_runs / pre_lineup only (the only reached contract — measured, not assumed).
WINDOW       min_year=2021 — the champion's own training convention (registry
             `training_cutoff: 2021+`). Widening the window here would conflate a window
             change with the cure (MH2.1 is the story that owns window changes).
ARMS (2 — a single pre-registered contrast; the default verdict is INCUMBENT_STANDS)
    incumbent_asfit  fit on the PRE-CURE matrix (fabricated 0.0), scored on the CURED eval
                     rows THROUGH ITS OWN pre-cure-fit imputer — byte-for-byte the live
                     state if the cure ships with no retrain.
    refit_cured      fit on the CURED matrix, scored on the same CURED eval rows — the
                     retrain candidate.
    Both arms: ngboost_normal (the incumbent class) at the champion bake-off config
    (n_estimators=400, Normal), identical folds, identical eval rows, global RNG seeded
    (MH2.5: NGBRegressor(random_state=…) does NOT seed its base learner).
METRIC       CRPS (closed-form Normal — the totals distributional metric, as E7.9/MH2.1).
             The reducer REFUSES a non-finite predictive (NF-W3: an arm scored on a
             silently smaller population is not in the same contest).
GATES        SHIP_RETRAIN iff ALL of:
               1. pooled CRPS margin (incumbent_asfit − refit_cured) > NOISE_FLOOR['crps'];
               2. DSR ≥ 0.95 on the per-fold paired delta (fixed convention: observations
                  are the FOLDS; n_trials=2 = the full declared field; asymptotic
                  V = 1/n_folds stated as such — with ONE non-reference arm a measured
                  cross-trial V does not exist, per the dsr_gate small-family rule);
               3. PIT-KS of refit_cured not degraded beyond calibration_tolerance.
             PBO: a single contrast has no search to overfit — reported UNDEFINED when
             cv_power.pbo_evaluable says so, NEVER "failed" (the NF-W3 rule).
CONTROLS (what makes a tiny-exposure null readable instead of vacuous)
    skew          incumbent_asfit's own fits scored on PRE-CURE vs CURED eval rows (same
                  fitted model, two inputs) — the pure serving-input-shift cost of
                  shipping the cure without a retrain. This is the E7.9 "how big is the
                  skew" number, measured not reasoned.
    touched-rows  the cure changes ~2% of rows, so the pooled delta dilutes ~50×. The
                  paired per-row delta is ALSO reported restricted to the eval rows the
                  cure actually touched (the population where the mechanism CAN act —
                  NF1.9: "a mechanism that cannot act is a finding, not an omission"),
                  with their count. Zero touched eval rows across all folds ⇒ the
                  contrast is INACTIVE and the run says so rather than reporting a null.
    untouched-rows on eval rows the cure does NOT touch, incumbent_asfit's two scoring
                  passes see IDENTICAL inputs ⇒ identical per-row CRPS. Asserted exactly
                  (max |Δ| == 0), proving the transform touched only what it claims.
STORE-VINTAGE ROBUSTNESS
    The harness constructs BOTH views from whichever store vintage the cached matrix
    carries — `apply_cure` (seasonnorm := NULL where raw IS NULL) and `apply_precure`
    (seasonnorm := 0.0 where raw IS NULL) are each idempotent and together reconstruct
    both sides of the wrapper expression exactly — so it runs identically BEFORE or AFTER
    the operator's --full-refresh box rebuild. (The stale-cache lesson, NF-D10: the run
    report records the cache vintage; the operator run uses --refresh-cache.)

⚠️ best_alpha = 0. This is a train/serve-consistency exercise; nothing here licenses an
edge, win-rate, or ROI claim. bet_paused for totals is unchanged either way.

RUNTIME: 2 NGBoost fits × n_folds (+1 oracle-free — no extra fits for the controls; they
re-score existing fits). Minutes → HAND THE FULL RUN TO THE OPERATOR (>2-min rule).
`--smoke` caps rows + estimators for a fast end-to-end path check.

Usage:
    # smoke (laptop, ~1 min — proves the code path, NOT a result):
    uv run python betting_ml/scripts/e1_13_seasonnorm_cure_revalidation.py --smoke --s3
    # the real run (LAPTOP, per the data-fix-on-laptop rule; needs AWS + .env):
    uv run python betting_ml/scripts/e1_13_seasonnorm_cure_revalidation.py --s3 --refresh-cache
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]

STORY = "E1.13"
TARGET = "total_runs"
TIER = "pre_lineup"
SEED = 42
EMBARGO_DAYS = 3
MIN_YEAR = 2021
N_TRIALS = 2                      # the full declared field: incumbent_asfit + refit_cured
DSR_BAR = 0.95
SERVED_SIDECAR = ("betting_ml/models/total_runs/"
                  "feature_columns_v6_total_runs_pre_lineup_served.json")
# build_imputation_pipeline() re-adds these; the base contract strips them (finalize_v6 rule)
_IMPUTER_ADDED = ("has_starter_platoon_data", "is_new_venue")

ABLATION_DIR = PROJECT_ROOT / "ablation_results"


# ── the cure / pre-cure transforms (pure; unit-tested) ───────────────────────────────────
#
# ⚠️ THE MASK MUST COME FROM THE PRE-SWAP (STORE) FRAME, NOT THE CLEAN MATRIX.
# load_clean_matrix applies the E1 de-leak swaps IN MEMORY — _swap_bullpen_v3 REPLACES the
# raw `*_bp_eb_xwoba` values with bullpen_v3, filling cells whose STORE (static) value is
# NULL. The served wrapper's cure keys on the STORE's raw twin, so a mask read off the
# post-swap matrix would silently under-count the touched rows (measured: the smoke sample
# read 0 touched where the store carries ~2%). The mask is therefore computed on the
# PRE-swap cached frame — the same parquet, before swaps — and joined by game_pk.

def seasonnorm_pairs(cols: list[str], available_cols) -> list[tuple[str, str]]:
    """[(seasonnorm_col, raw_twin), …] for the contract's seasonnorm columns.

    RAISES if a raw twin is absent — the transforms would silently no-op on that column
    otherwise (the vacuous-guard class)."""
    pairs = []
    for c in cols:
        if c.endswith("_seasonnorm"):
            raw = c[: -len("_seasonnorm")]
            if raw not in available_cols:
                raise SystemExit(
                    f"❌ {STORY}: raw twin {raw!r} for contract column {c!r} is not in the "
                    f"matrix — the cure transform cannot be constructed.")
            pairs.append((c, raw))
    if not pairs:
        raise SystemExit(
            f"❌ {STORY}: the contract carries no _seasonnorm columns — this harness exists "
            f"only for the contract the cure reaches; check the sidecar path.")
    return pairs


def store_null_masks(raw_frame: pd.DataFrame, pairs: list[tuple[str, str]]) -> pd.DataFrame:
    """Per-game booleans: is the STORE's raw twin NULL for each contract seasonnorm column.

    Built from the PRE-swap cached frame (the store's static values). Columns are named
    after the seasonnorm column; index = game_pk (string-normalized). RAISES on a
    duplicate game_pk — a mask joined on a dup key would silently fan out."""
    gpk = raw_frame["game_pk"].astype(str)
    if gpk.duplicated().any():
        raise SystemExit(f"❌ {STORY}: duplicate game_pk in the pre-swap frame — "
                         f"the store-null mask join would fan out.")
    m = pd.DataFrame({sn: raw_frame[raw].isna().to_numpy() for sn, raw in pairs})
    m.index = gpk.to_numpy()
    return m


def _aligned(masks: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """masks re-indexed to df's rows via game_pk. A game absent from the mask frame maps
    to False (raw twin unknown ⇒ leave the stored value alone — never fabricate)."""
    return masks.reindex(df["game_pk"].astype(str).to_numpy()).fillna(False).astype(bool)


def apply_cure(df: pd.DataFrame, masks: pd.DataFrame) -> pd.DataFrame:
    """The shipped SQL cure, in memory: seasonnorm := NULL where the STORE's raw twin is
    NULL. Idempotent; exact on either store vintage."""
    out = df.copy()
    a = _aligned(masks, out)
    for sn in masks.columns:
        out.loc[a[sn].to_numpy(), sn] = np.nan
    return out


def apply_precure(df: pd.DataFrame, masks: pd.DataFrame) -> pd.DataFrame:
    """The PRE-cure wrapper, in memory: seasonnorm := 0.0 where the STORE's raw twin is
    NULL (the fabricated "exactly league average"). Idempotent; exact on either vintage."""
    out = df.copy()
    a = _aligned(masks, out)
    for sn in masks.columns:
        out.loc[a[sn].to_numpy(), sn] = 0.0
    return out


def touched_mask(df: pd.DataFrame, masks: pd.DataFrame) -> pd.Series:
    """Rows of df where the cure changes at least one contract seasonnorm value."""
    a = _aligned(masks, df)
    return pd.Series(a.any(axis=1).to_numpy(), index=df.index)


def _finite_or_refuse(scores: np.ndarray, arm: str) -> np.ndarray:
    """NF-W3: a leaderboard whose arms are scored on different populations is not a
    comparison — refuse a non-finite per-row score outright."""
    s = np.asarray(scores, float)
    if not np.isfinite(s).all():
        raise SystemExit(f"❌ {STORY}: non-finite CRPS from arm {arm!r} "
                         f"({int((~np.isfinite(s)).sum())} rows) — refusing to nan-mean past it.")
    return s


def derive_verdict(*, margin: float, noise_floor: float, dsr: float | None,
                   calibration_ok: bool, touched_eval_rows: int) -> tuple[str, str]:
    """Three-way, derived at report time, failing closed (NF-W2e).

    Returns (verdict, contest) where contest ∈ {BEATS, TIES, LOSES, INACTIVE}."""
    if touched_eval_rows == 0:
        return "INCUMBENT_STANDS", "INACTIVE"
    if margin > noise_floor:
        contest = "BEATS"
    elif margin < -noise_floor:
        contest = "LOSES"
    else:
        contest = "TIES"
    ship = (contest == "BEATS" and dsr is not None and dsr >= DSR_BAR and calibration_ok)
    return ("SHIP_RETRAIN" if ship else "INCUMBENT_STANDS"), contest


# ── the run ──────────────────────────────────────────────────────────────────────────────

def _impute_multi(train_raw: pd.DataFrame, *eval_raws: pd.DataFrame):
    """`_impute` semantics (fit on train, transform each eval, reindex to train columns)
    but with ONE fitted pipeline shared across several eval inputs — needed because
    incumbent_asfit's fitted model must score BOTH the pre-cure and cured eval rows
    through the SAME imputer (the skew control re-scores, it never re-fits)."""
    from betting_ml.utils.preprocessing import build_imputation_pipeline
    pipe = build_imputation_pipeline()
    Xtr = pipe.fit_transform(train_raw).select_dtypes(include=[np.number])
    outs = []
    for ev in eval_raws:
        Xev = pipe.transform(ev)
        Xev = (Xev[[c for c in Xtr.columns if c in Xev.columns]]
               .reindex(columns=Xtr.columns, fill_value=0.0))
        outs.append(Xev)
    return Xtr, outs


def run(*, smoke: bool, refresh_cache: bool, s3: bool, embargo_days: int = EMBARGO_DAYS) -> dict:
    from betting_ml.scripts.e7_9_train_serve_consistency import (
        calibration_tolerance, design_bar,
    )
    from betting_ml.scripts.model_bakeoff import _assert_market_blind, load_clean_matrix
    from betting_ml.scripts.promotion_gate_eval import NGBoostSpec, make_gate_splitter
    from betting_ml.utils.overfitting import deflated_sharpe
    from betting_ml.utils.promotion_gate import NOISE_FLOOR, calibration_report

    if s3:
        from betting_ml.utils.data_loader import set_s3_mode
        set_s3_mode(True)
        print(f"[{STORY}] reading the training matrix from the S3 lakehouse (Snowflake-free)")

    # smoke sampling is done HERE (not by load_clean_matrix): a plain head-400-per-season
    # sample contains ZERO cure-touched rows (measured — the missing-bp games sit past the
    # head), which would smoke-test only the INACTIVE path. The smoke sample is therefore
    # head-400 ∪ the touched rows, so every control (touched-subset delta, untouched
    # exactness) is exercised end-to-end.
    df = load_clean_matrix(refresh_cache=refresh_cache, smoke=False, min_year=MIN_YEAR)
    df = df.reset_index(drop=True)

    # the PRE-swap frame (the store's static values) — same parquet, cache hit, no swaps.
    # Loaded AFTER load_clean_matrix so a --refresh-cache has already refreshed the key.
    from betting_ml.utils.data_loader import load_features
    from betting_ml.utils.training_cache import get_cached_df
    raw_frame = get_cached_df("edge_e1_training",
                              lambda: load_features(min_year=MIN_YEAR), refresh=False)

    sidecar = json.loads((PROJECT_ROOT / SERVED_SIDECAR).read_text())["feature_cols"]
    cols = [c for c in sidecar if c not in _IMPUTER_ADDED]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise SystemExit(f"❌ {STORY}: served contract columns absent from the matrix: {missing}")
    _assert_market_blind(cols)
    pairs = seasonnorm_pairs(cols, set(raw_frame.columns))
    masks = store_null_masks(raw_frame, pairs)

    if smoke:
        base = df.groupby("game_year", group_keys=False).head(400)
        extra = df.loc[touched_mask(df, masks)]
        df = (pd.concat([base, extra]).drop_duplicates(subset="game_pk")
              .sort_index().reset_index(drop=True))
        print(f"[{STORY}] --smoke: {len(df):,} rows (head-400/season ∪ touched rows)")

    df_pre = apply_precure(df, masks)     # the store the champion was fit on
    df_cured = apply_cure(df, masks)      # the store serving carries after the cure
    touched = touched_mask(df, masks)
    n_touched = int(touched.sum())
    print(f"[{STORY}] contract: {len(cols)} base cols, {len(pairs)} seasonnorm; "
          f"cure touches {n_touched:,} of {len(df):,} rows ({100*n_touched/len(df):.2f}%)")

    tcol = "total_runs"
    noise_floor = float(NOISE_FLOOR["crps"])
    splitter, _ = make_gate_splitter(True, feature_cols=cols, embargo_days=embargo_days)
    folds = list(splitter(df))
    bar = design_bar(len(folds), N_TRIALS)
    print(f"[{STORY}] {len(folds)} purged folds × 2 arms — PRE-REGISTERED BAR: required "
          f"per-fold Sharpe {bar['dsr_required_per_fold_sr_asymptotic_V']} (asymptotic V), "
          f"DSR ceiling {bar['dsr_ceiling_at_any_effect']}, pbo_evaluable={bar['pbo_evaluable']}")

    n_est = 60 if smoke else 400
    spec = NGBoostSpec(n_est, "Normal", name="ngboost_normal", seed=SEED)

    per_fold = []
    pooled = {"incumbent_asfit": [], "refit_cured": [], "incumbent_on_precure": []}
    pooled_touched_delta, pooled_untouched_maxdiff = [], 0.0
    pit_pool = {"incumbent_asfit": [], "refit_cured": []}
    yev_pool = []
    for k, (tr, ev) in enumerate(folds):
        ytr = df.loc[tr, tcol].values
        yev = df.loc[ev, tcol].values
        ev_touched = touched.loc[ev].values

        # incumbent_asfit: ONE fit on the pre-cure train; scored on cured AND pre-cure eval
        np.random.seed(SEED)  # MH2.5 — NGBoost's base learner reads the global RNG
        Xtr_pre, (Xev_cured_via_pre, Xev_pre) = _impute_multi(
            df_pre.loc[tr, cols], df_cured.loc[ev, cols], df_pre.loc[ev, cols])
        fitted_pre = spec.fit(Xtr_pre, ytr)
        out_inc = fitted_pre.output(Xev_cured_via_pre)
        out_inc_precure = fitted_pre.output(Xev_pre)

        # refit_cured: fit on the cured train; scored on the same cured eval rows
        np.random.seed(SEED)
        Xtr_cur, (Xev_cured,) = _impute_multi(df_cured.loc[tr, cols], df_cured.loc[ev, cols])
        fitted_cur = spec.fit(Xtr_cur, ytr)
        out_ref = fitted_cur.output(Xev_cured)

        s_inc = _finite_or_refuse(out_inc.score_to_truth(yev, "crps"), "incumbent_asfit")
        s_ref = _finite_or_refuse(out_ref.score_to_truth(yev, "crps"), "refit_cured")
        s_inc_pre = _finite_or_refuse(out_inc_precure.score_to_truth(yev, "crps"),
                                      "incumbent_on_precure")

        # untouched-rows control: identical inputs ⇒ identical scores, exactly
        untouched_diff = float(np.max(np.abs(s_inc[~ev_touched] - s_inc_pre[~ev_touched]))
                               if (~ev_touched).any() else 0.0)
        if untouched_diff != 0.0:
            raise SystemExit(
                f"❌ {STORY}: fold {k}: the cure transform changed an UNTOUCHED eval row "
                f"(max |ΔCRPS| {untouched_diff:.3e}) — the transform is not what it claims.")

        pooled["incumbent_asfit"].append(s_inc)
        pooled["refit_cured"].append(s_ref)
        pooled["incumbent_on_precure"].append(s_inc_pre)
        pooled_touched_delta.append(s_inc[ev_touched] - s_ref[ev_touched])
        pooled_untouched_maxdiff = max(pooled_untouched_maxdiff, untouched_diff)
        yev_pool.append(yev)
        pit_pool["incumbent_asfit"].append(out_inc)
        pit_pool["refit_cured"].append(out_ref)

        per_fold.append({
            "fold": k,
            "eval_year": int(pd.Series(df.loc[ev, "game_year"]).astype(int).mode().iloc[0]),
            "n_eval": int(len(ev)),
            "n_eval_touched": int(ev_touched.sum()),
            "crps_incumbent_asfit": float(np.mean(s_inc)),
            "crps_refit_cured": float(np.mean(s_ref)),
            "crps_incumbent_on_precure": float(np.mean(s_inc_pre)),
        })
        print(f"[{STORY}]   fold {k} (eval {per_fold[-1]['eval_year']}, n={len(ev)}, "
              f"touched={int(ev_touched.sum())}): incumbent_asfit {np.mean(s_inc):.4f}  "
              f"refit_cured {np.mean(s_ref):.4f}  (incumbent on pre-cure {np.mean(s_inc_pre):.4f})")

    # ── gates ────────────────────────────────────────────────────────────────────────────
    inc_all = np.concatenate(pooled["incumbent_asfit"])
    ref_all = np.concatenate(pooled["refit_cured"])
    incpre_all = np.concatenate(pooled["incumbent_on_precure"])
    y_all = np.concatenate(yev_pool)
    margin = float(inc_all.mean() - ref_all.mean())           # >0 ⇒ the refit is better
    skew = float(np.mean(np.abs(inc_all - incpre_all)))       # per-row input-shift cost
    touched_all = np.concatenate(pooled_touched_delta) if pooled_touched_delta else np.array([])
    n_touched_eval = int(touched_all.size)

    delta_series = [f["crps_incumbent_asfit"] - f["crps_refit_cured"] for f in per_fold]
    # single non-reference arm ⇒ no measured cross-trial V exists; the asymptotic
    # V = 1/n_folds is the declared convention (design_bar's) and is stated as such.
    dsr_res = deflated_sharpe(np.asarray(delta_series, float), n_trials=N_TRIALS,
                              var_trials_sr=1.0 / max(len(folds), 1))
    dsr = float(dsr_res.dsr)

    # calibration: PIT-KS on the pooled predictive (both arms Normal on the same rows)
    def _pooled_pit_ks(outs) -> float:
        from betting_ml.utils.promotion_gate import PredictiveOutput
        locs = np.concatenate([np.asarray(o.loc, float) for o in outs])
        scales = np.concatenate([np.asarray(o.scale, float) for o in outs])
        rep = calibration_report(y_all, PredictiveOutput.normal(locs, scales))
        return float(rep["pit_ks"])
    pit_inc = _pooled_pit_ks(pit_pool["incumbent_asfit"])
    pit_ref = _pooled_pit_ks(pit_pool["refit_cured"])
    cal_tol = float(calibration_tolerance(pit_inc))
    calibration_ok = bool(pit_ref <= pit_inc + cal_tol)

    verdict, contest = derive_verdict(margin=margin, noise_floor=noise_floor, dsr=dsr,
                                      calibration_ok=calibration_ok,
                                      touched_eval_rows=n_touched_eval)

    result = {
        "story": STORY, "target": TARGET, "tier": TIER, "smoke": bool(smoke),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": {"min_year": MIN_YEAR, "n_rows": int(len(df)),
                   "n_folds": len(folds), "embargo_days": embargo_days},
        "contract": {"sidecar": SERVED_SIDECAR, "n_base_cols": len(cols),
                     "seasonnorm_cols": [sn for sn, _ in pairs]},
        "exposure": {"rows_touched": n_touched, "rows_total": int(len(df)),
                     "share": round(n_touched / len(df), 4),
                     "touched_eval_rows": n_touched_eval},
        "design_bar": bar,
        "arms": {"incumbent_asfit": "fit pre-cure, scored on cured eval (ship-cure-no-retrain)",
                 "refit_cured": "fit cured, scored on cured eval (the retrain candidate)"},
        "per_fold": per_fold,
        "gates": {
            "crps_margin": round(margin, 5), "noise_floor": noise_floor,
            "dsr_fixed_convention": round(dsr, 4), "dsr_bar": DSR_BAR,
            "dsr_convention": "folds as observations; n_trials=2 (full declared field); "
                              "asymptotic V=1/n_folds (single non-reference arm ⇒ no "
                              "measured cross-trial V exists)",
            "pbo": "UNDEFINED" if not bar["pbo_evaluable"] else "see pbo_cscv",
            "pit_ks_incumbent_asfit": round(pit_inc, 4),
            "pit_ks_refit_cured": round(pit_ref, 4),
            "calibration_tolerance": round(cal_tol, 4),
            "calibration_ok": calibration_ok,
        },
        "controls": {
            "input_shift_cost_mean_abs_crps": round(skew, 5),
            "touched_rows_paired_delta_mean": (round(float(touched_all.mean()), 5)
                                               if n_touched_eval else None),
            "untouched_rows_max_abs_crps_diff": pooled_untouched_maxdiff,
        },
        "verdict": verdict, "contest": contest,
        "best_alpha": 0,
    }
    return result


def write_report(result: dict) -> Path:
    stem = "e1_13_seasonnorm_cure_bakeoff" + ("_smoke" if result["smoke"] else "")
    ABLATION_DIR.mkdir(exist_ok=True)
    jpath = ABLATION_DIR / f"{stem}.json"
    jpath.write_text(json.dumps(result, indent=2))
    g = result["gates"]
    lines = [
        f"# {STORY} — seasonnorm-cure retrain-vs-incumbent ({TARGET}/{TIER})",
        "",
        f"*Generated {result['generated_at']}"
        + ("  — ⚠️ SMOKE RUN: capped rows/estimators, NOT a result*" if result["smoke"] else "*"),
        "",
        f"**VERDICT: {result['verdict']}**  (contest: {result['contest']}; default was "
        f"INCUMBENT_STANDS; `best_alpha=0` — no edge claim either way)",
        "",
        f"- window {result['window']['min_year']}+ · {result['window']['n_rows']:,} rows · "
        f"{result['window']['n_folds']} purged folds (embargo {result['window']['embargo_days']}d)",
        f"- exposure: cure touches {result['exposure']['rows_touched']:,} rows "
        f"({100*result['exposure']['share']:.2f}%); touched EVAL rows "
        f"{result['exposure']['touched_eval_rows']}",
        f"- CRPS margin (incumbent_asfit − refit_cured): **{g['crps_margin']:+.5f}** vs noise "
        f"floor {g['noise_floor']}",
        f"- DSR (fixed convention) {g['dsr_fixed_convention']} vs bar {g['dsr_bar']} · "
        f"PBO {g['pbo']}",
        f"- PIT-KS incumbent_asfit {g['pit_ks_incumbent_asfit']} · refit_cured "
        f"{g['pit_ks_refit_cured']} (tol {g['calibration_tolerance']}; "
        f"ok={g['calibration_ok']})",
        f"- input-shift cost (same fit, pre-cure vs cured eval): mean |ΔCRPS| "
        f"{result['controls']['input_shift_cost_mean_abs_crps']}",
        f"- touched-rows paired delta: {result['controls']['touched_rows_paired_delta_mean']}",
        "",
        "Per fold:",
        "",
        "| fold | eval year | n | touched | incumbent_asfit | refit_cured | incumbent on pre-cure |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in result["per_fold"]:
        lines.append(f"| {f['fold']} | {f['eval_year']} | {f['n_eval']} | {f['n_eval_touched']} "
                     f"| {f['crps_incumbent_asfit']:.4f} | {f['crps_refit_cured']:.4f} "
                     f"| {f['crps_incumbent_on_precure']:.4f} |")
    mpath = ABLATION_DIR / f"{stem}.md"
    mpath.write_text("\n".join(lines) + "\n")
    print(f"[{STORY}] wrote {jpath} + {mpath}")
    return mpath


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--smoke", action="store_true", help="capped rows/estimators path check")
    ap.add_argument("--refresh-cache", action="store_true")
    ap.add_argument("--s3", action="store_true", help="read the matrix from the S3 lakehouse")
    ap.add_argument("--embargo-days", type=int, default=EMBARGO_DAYS)
    args = ap.parse_args()
    result = run(smoke=args.smoke, refresh_cache=args.refresh_cache, s3=args.s3,
                 embargo_days=args.embargo_days)
    write_report(result)
    print(f"[{STORY}] VERDICT: {result['verdict']} (contest {result['contest']})")


if __name__ == "__main__":
    main()
