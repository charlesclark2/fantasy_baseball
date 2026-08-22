"""ncaaf_val3_cold_start_mu.py — NCAAF-VAL3: an in-fold-selected cold-start μ_total correction.

NCAAF-VAL2 measured the served total's mean error `μ_total − y_total` at **+2.5 pts in weeks 1–3**
(clustered CI [+0.89, +3.74], positive in 6/6 seasons) decaying to ~0 by week 3, against a POOLED
level whose CI spans zero and a `wk4-6` cell that is NEGATIVE. It handed VAL3 a scoped target and
three constraints. This module executes them.

    μ'_total(g)  =  μ_total(g) − δ(week(g))          for week ≤ 3;  μ_total(g) otherwise
    σ(g), μ_margin(g)                                 FROZEN — byte-identical across every arm

⛔ **This module CHANGES NOTHING SERVED.** Eval-only over the P1.4 cache: no refit of a served
artifact, no serving write, no registry edit, no bet. `best_alpha = 0` before and after.

⭐ **Three things it is easy to get wrong here, and how each is prevented mechanically.**

1. **Size off `μ − y`, never off the offset.** In `wk1-3` the offset (`μ − close`) is only ~54 % of
   our own error, because the two halves of VAL2's identity point in OPPOSITE directions there. The
   estimator reads `mu_total − y_total` and nothing else; `assert_estimator_is_market_blind` fails
   the run if a market column reaches the estimator frame. (It also removes VAL2's mean-vs-median
   ⛔ *by construction*: `y` is the REALISED total, so the correction moves μ toward the realised
   conditional MEAN and can never chase a median-set line.)
2. **The magnitude is selected IN-FOLD.** ⛔ No constant is inherited from VAL2 — that is the
   NF-D18 / NF-D20 inadmissible-λ shape (a magnitude fitted with the answer in view). Every arm's
   magnitude is a statistic of a NESTED walk-forward run inside the outer fold's own training
   seasons.
3. **A level move is not free on a right-skewed target.** Aggregate PIT and the calib floor are
   REFUSAL clauses (C1–C3), not diagnostics.

The field, the metric, the clauses and which `V` binds are all CLOSED in
`ablation_results/ncaaf_val3_preregistration.md`, written before a single arm was scored.

  uv run python -m quant_sports_intel_models.football.ncaaf.models.ncaaf_val3_cold_start_mu
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from scipy import stats

from betting_ml.utils import cv_power
from betting_ml.utils.cv import PurgedWalkForwardSplit
from betting_ml.utils.market_blind import assert_market_blind, find_market_columns
from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv
from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_game as B
from quant_sports_intel_models.football.ncaaf.models import ncaaf_val1_clv_week_strat as V

_STORY = "NCAAF-VAL3"
_RESULTS = Path(B._RESULTS_DIR)
_SCORES_JSON = _RESULTS / "ncaaf_val3_cold_start_scores.json"
_OUT_JSON = _RESULTS / "ncaaf_val3_cold_start_mu.json"
#: ⚠️ The MACHINE-rendered table. The hand-written NARRATIVE lives at
#: `ncaaf_val3_cold_start_mu.md` and is NOT written by this module — a runner that writes to a
#: narrative's fixed path silently clobbers it on every re-run (the NF-W2c-CBS hazard).
_OUT_MD = _RESULTS / "ncaaf_val3_cold_start_readout.md"
_PARENT_JSON = _RESULTS / "ncaaf_val3_s1_serve_reanchor.json"

#: The SERVED config, imported from VAL1 rather than restated — a second literal could drift away
#: from the config S1-serve/VAL1/VAL2 actually score and nothing would fail.
SERVED = V.PRIMARY
WEEK_COL = V.WEEK_COL                 # ⛔ `season_order_week`, never raw `week` (P1.1 restart)
COLD_START_MAX_WEEK = 3               # VAL2's target cell `wk1-3`

#: §2 — a DESIGN quantity, fixed from the FOLD STRUCTURE, not from any result: at 3 the earliest
#: outer fold (2018, train 2015–2017) has ZERO inner folds and every arm is UNDEFINED there, and an
#: unevaluable fold is never a pass (NF1.7 (a)). At 2 every outer fold carries ≥1 inner fold.
INNER_MIN_TRAIN_SEASONS = 2

#: §5 — the ship clauses. All pre-registered; ⛔ none may be re-derived from an observed value.
PIT_DEGRADE_TOL = 0.0020              # C1: pooled PIT max-decile-dev may not worsen by more than this
CALIB_FLOOR = 0.78                    # C2/C3: the P1.4 floor (_CALIB_TARGET − _CALIB_FLOOR_TOL)
FROZEN_TOL = 1e-9                     # C5/C6/C7: the frozen-σ / frozen-margin / week-scoping invariants
TIE_BAND = 1e-6                       # a CRPS gap this small is a numerical tie, not a win

#: §5 — the deflation gates.
PBO_GATE = 0.20
DSR_GATE = 0.95
FDR_ALPHA = 0.05

#: §6 — the reproduction pin, taken from the PARENT (the S1-serve eval-only re-run) and the cache
#: meta. ⛔ NEVER from VAL3's own output, which would make the pin restate the thing it checks.
#: ⚠️ Vintage-bound ON PURPOSE: a re-assemble moves the population and this HALTs, correctly. The
#: remedy is to re-run the parent and re-anchor from ITS output (the VAL1 §2a pattern).
PIN = {
    "cache_assembled_at": "2026-08-22",
    "n_with_close": 4187,
    "n_oos_games": 6024,
    "fold_years": [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
    "source": "ncaaf_val3_s1_serve_reanchor.json (S1-serve --stage finalize, repaired _clv_eval)",
}


# ===========================================================================
# The field — ⛔ CLOSED at pre-registration
# ===========================================================================

@dataclass(frozen=True)
class Arm:
    """One pre-registered arm.

    `role` decides how the arm is TREATED, and the three roles are genuinely different:
      `foil`       — the do-nothing degenerate AND the incumbent, one and the same. Everything is
                     measured against it.
      `candidate`  — selectable; may ship.
      `lose`       — pre-registered to LOSE. SCORED and counted in `n_trials` (it was part of the
                     search), but INELIGIBLE to ship. NF-D20: an anchor that is reasoned about
                     instead of scored teaches nothing, and a refuted MAGNITUDE hypothesis is only
                     obtainable because the anchor was scored.
      `diagnostic` — an anchor, NOT a trial: excluded from `n_trials` AND from `V`. MH2.1 (a): the
                     anchor that exists to POLICE the metric must never SET the gate's own bar.
    """
    name: str
    role: str
    doc: str
    scope: str          # "cold" (weeks <= 3) | "all" — which rows the correction touches
    n_params: str
    form: str           # the ESTIMATOR form — what `_estimate` computes from a source frame


ARMS: tuple[Arm, ...] = (
    Arm("none", "foil", "the served model, untouched — the do-nothing degenerate",
        "cold", "0", "zero"),
    Arm("bucket_shift", "candidate", "one constant over weeks 1–3", "cold", "1", "bucket"),
    Arm("per_week_shift", "candidate", "a separate constant per week 1, 2, 3",
        "cold", "3", "per_week"),
    Arm("linear_decay", "candidate", "OLS ramp a + b·week over weeks 1–3", "cold", "2", "linear"),
    Arm("shrunk_bucket", "candidate",
        "positive-part James–Stein shrink of the bucket constant toward 0 by its own SE",
        "cold", "1", "shrunk"),
    Arm("pooled_level", "lose",
        "MATCHED FOIL (SCOPING) — the POOLED mean error applied to EVERY row. Winning would mean "
        "the effect is a season-wide level, not a cold start (VAL2's ⛔ would be wrong).",
        "all", "1", "pooled_all"),
    Arm("week_blind", "lose",
        "MATCHED FOIL (MAGNITUDE) — the POOLED magnitude applied to weeks 1–3 ONLY. Holds the "
        "SCOPING fixed and removes the week-informed MAGNITUDE (NF-D15 g′).",
        "cold", "1", "pooled_cold"),
    Arm("over_scale", "lose",
        "2 × the bucket constant. Winning would mean the estimator UNDER-corrects (NF-D20).",
        "cold", "1", "over2"),
    Arm("oracle_bucket", "diagnostic",
        "PEEKING bucket floor: the bucket constant computed on the EVAL fold's own weeks 1–3. "
        "Reported as the headline peek; C8 uses each arm's OWN-form peek (NF-D16 g‴).",
        "cold", "1", "bucket"),
    Arm("matched_n_bucket", "diagnostic",
        "`bucket_shift`'s estimator on a random in-fold slice sized to the eval fold's own wk1-3 n "
        "— what makes the peek readable at matched family AND matched sample (NF1.9 (f)).",
        "cold", "1", "bucket"),
)

FOIL_ARM = "none"
CANDIDATES: tuple[str, ...] = tuple(a.name for a in ARMS if a.role == "candidate")
LOSERS: tuple[str, ...] = tuple(a.name for a in ARMS if a.role == "lose")
DIAGNOSTICS: tuple[str, ...] = tuple(a.name for a in ARMS if a.role == "diagnostic")
#: trials = the foil + everything that was actually searched over. ⛔ Diagnostic anchors are NOT
#: trials. Declared FORWARD in the pre-registration; ⛔ no post-hoc trim (MH2.2).
DECLARED_FIELD_SIZE: int = 1 + len(CANDIDATES) + len(LOSERS)


# ===========================================================================
# Scoring primitives — CLOSED FORM, so every figure is deterministic
# ===========================================================================

_INV_SQRT_PI = 1.0 / np.sqrt(np.pi)


def gaussian_crps(y: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """Exact CRPS of a Normal predictive: σ·[z(2Φ(z)−1) + 2φ(z) − 1/√π], z = (y−μ)/σ.

    ⭐ The served form IS a heteroscedastic Gaussian, so this is not an approximation of the scored
    predictive — it is the scored predictive's CRPS, with the Monte-Carlo error removed rather than
    bounded. That closes, at zero cost, the whole "would more draws clear the gate?" question
    NF-W7k had to spend a story on. `crps_sampled_control` cross-checks it against the ensemble
    identity the rest of the vertical uses, because one policy with two call sites is the E9.61
    two-renderers hazard.
    """
    sigma = np.asarray(sigma, float)
    if np.any(sigma <= 0):
        raise SystemExit(f"[{_STORY}] non-positive σ reached the CRPS; refusing to score.")
    z = (np.asarray(y, float) - np.asarray(mu, float)) / sigma
    return sigma * (z * (2.0 * stats.norm.cdf(z) - 1.0) + 2.0 * stats.norm.pdf(z) - _INV_SQRT_PI)


def crps_sampled_control(y: np.ndarray, mu: np.ndarray, sigma: np.ndarray, *,
                         n_draws: int, seed: int) -> float:
    """The ensemble CRPS (E|X−y| − ½E|X−X'|) of the SAME predictive — an instrument control.

    A closed form and a sampler that disagree would mean one of them is not scoring the predictive
    the study claims to score, and the disagreement would be invisible in every headline."""
    rng = np.random.default_rng(seed)
    S = np.asarray(mu, float)[:, None] + np.asarray(sigma, float)[:, None] * rng.standard_normal(
        (len(mu), n_draws))
    y = np.asarray(y, float)
    term1 = np.mean(np.abs(S - y[:, None]), axis=1)
    Ss = np.sort(S, axis=1)
    coef = 2 * np.arange(1, n_draws + 1) - n_draws - 1
    term2 = (2.0 / (n_draws * n_draws)) * np.sum(coef[None, :] * Ss, axis=1)
    return float(np.mean(term1 - 0.5 * term2))


def analytic_pit(y: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """PIT of the Gaussian predictive: Φ((y−μ)/σ). Deterministic (no randomisation draw)."""
    return stats.norm.cdf((np.asarray(y, float) - np.asarray(mu, float)) / np.asarray(sigma, float))


def pit_dev(u: np.ndarray) -> dict[str, float]:
    """Decile occupancy of a PIT sample, in `totals_distribution.pit_flatness`'s convention."""
    counts, _ = np.histogram(np.asarray(u, float), bins=10, range=(0.0, 1.0))
    freqs = counts / max(counts.sum(), 1)
    return {"max_decile_dev": float(np.max(np.abs(freqs - 0.10))),
            "mean_dev_from_half": float(abs(float(np.mean(u)) - 0.5)),
            "decile_freqs": [float(f) for f in freqs]}


def calib_80(y: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> float:
    """Coverage of the analytic central 80 % interval. A FLOOR, never a target (NF1.8/E2.1-r)."""
    z = stats.norm.ppf(0.90)
    y, mu, sigma = np.asarray(y, float), np.asarray(mu, float), np.asarray(sigma, float)
    return float(np.mean((y >= mu - z * sigma) & (y <= mu + z * sigma)))


def cell_metrics(y: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> dict[str, Any]:
    if len(y) == 0:
        return {"n": 0, "crps": None, "pit_max_decile_dev": None, "calib_80": None, "bias": None}
    p = pit_dev(analytic_pit(y, mu, sigma))
    return {"n": int(len(y)), "crps": float(np.mean(gaussian_crps(y, mu, sigma))),
            "pit_max_decile_dev": p["max_decile_dev"], "pit_mean_dev": p["mean_dev_from_half"],
            "calib_80": calib_80(y, mu, sigma), "bias": float(np.mean(mu - y))}


# ===========================================================================
# The in-fold estimator — the ONLY place a magnitude is allowed to come from
# ===========================================================================

#: Every column the estimator frame is allowed to carry. A market column here would be VAL2 §9's
#: mean-vs-median ⛔ arriving through the back door.
ESTIMATOR_COLUMNS: tuple[str, ...] = (WEEK_COL, "season", "mu_total", "y_total", "model_err")


def assert_estimator_is_market_blind(frame: pd.DataFrame) -> None:
    """C4 — HALT if any market column reached the estimator frame.

    ⭐ Two-sided on purpose: it is not enough that the frame *happens* to hold no close today. The
    columns are pinned to `ESTIMATOR_COLUMNS`, so a future edit that joins the close in to "sanity
    check" the magnitude fails here rather than silently re-sizing the correction off the offset —
    which is exactly the number VAL2 measured to be 54 % of the truth."""
    leaks = find_market_columns(frame.columns)
    if leaks:
        raise SystemExit(f"[{_STORY}] C4 market-blindness violation: the in-fold estimator frame "
                         f"carries market columns {leaks}. The magnitude must be sized off "
                         "`mu_total − y_total`, never off `μ − close` (VAL2 §5/§9).")
    extra = [c for c in frame.columns if c not in ESTIMATOR_COLUMNS]
    if extra:
        raise SystemExit(f"[{_STORY}] C4: unexpected columns on the estimator frame {extra}; the "
                         f"contract is {list(ESTIMATOR_COLUMNS)}.")


def infold_oos(df: pd.DataFrame, feat: list[str], cols: list[str], eval_year: int,
               *, min_train_seasons: int = INNER_MIN_TRAIN_SEASONS) -> pd.DataFrame:
    """Honest in-TRAIN out-of-sample predictions for one outer fold, by a NESTED walk-forward.

    Every row here has `season < eval_year`, so nothing the estimator sees can have touched the
    eval fold — which is what makes the magnitude an IN-FOLD selection rather than an inherited
    constant (VAL2 §9 constraint 2; the NF-D18/NF-D20 admissibility bar).

    ⚠️ The inner frame is `df[season < eval_year]`, i.e. the outer train set BEFORE its purge band
    is trimmed. Stated because it is a real (small) difference: the purge band removes the outer
    train TAIL, and re-adding it here can only give the estimator MORE prior-season rows, never any
    eval-season row. The leakage direction is closed; the population one is disclosed.
    """
    inner = df[df["game_year"] < eval_year].reset_index(drop=True)
    sp = PurgedWalkForwardSplit(min_train_seasons=min_train_seasons,
                                year_col="game_year", date_col=B._DATE)
    splits = list(sp.split(inner, feature_cols=None))
    if not splits:
        raise SystemExit(f"[{_STORY}] outer fold {eval_year} has ZERO inner folds at "
                         f"min_train_seasons={min_train_seasons}; every arm would be UNDEFINED "
                         "there and an unevaluable fold is never a pass (NF1.7 (a)).")
    cand = B.build_candidate(SERVED["mc"])
    idx = [feat.index(c) for c in cols]
    rows = []
    for tr_i, ev_i in splits:
        tr, ev = inner.loc[tr_i], inner.loc[ev_i]
        X_tr, X_ev, _ = B._prepare_matrix(tr, ev, feat)
        _, mu_t, _, _ = cand.fit_predict(X_tr[:, idx], tr[B._MARGIN].to_numpy(float),
                                         tr[B._TOTAL].to_numpy(float), X_ev[:, idx])
        rows.append(pd.DataFrame({
            WEEK_COL: ev[WEEK_COL].to_numpy(), "season": ev["game_year"].to_numpy(int),
            "mu_total": mu_t, "y_total": ev[B._TOTAL].to_numpy(float),
        }))
    out = pd.concat(rows, ignore_index=True)
    out["model_err"] = out["mu_total"] - out["y_total"]
    out = out[list(ESTIMATOR_COLUMNS)]
    assert_estimator_is_market_blind(out)
    return out


def _js_shrink(mean: float, se: float) -> float:
    """Positive-part James–Stein shrink of a single mean toward 0 by its own standard error.

    δ = mean · max(0, 1 − SE²/mean²). At a large signal-to-noise ratio this is ≈ the raw mean; when
    the in-fold sample cannot tell the mean from zero it collapses to 0, i.e. to the do-nothing
    foil. That matters here and is not decoration: fold 2018 estimates the level from 141 rows at
    σ ≈ 16.6, so its SE is ≈ 1.4 pts against a ≈ 2.5 pt effect."""
    if not np.isfinite(mean) or not np.isfinite(se) or mean == 0.0:
        return 0.0
    return float(mean * max(0.0, 1.0 - (se * se) / (mean * mean)))


def _cold(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame[WEEK_COL] <= COLD_START_MAX_WEEK]


def _estimate(form: str, src: pd.DataFrame, ev_week: np.ndarray) -> tuple[np.ndarray, dict]:
    """δ per EVAL row for one estimator FORM, computed from ONE source frame.

    ⭐ The form and the SOURCE are separated on purpose, and that separation is the whole
    admissibility argument of this study. The same function computes:

      * the **honest** magnitude, when `src` is the fold's NESTED in-fold OOS frame (every row has
        `season < eval_year`);
      * the **peeking own-form oracle**, when `src` is the EVAL fold's own residuals;
      * the **matched-n control**, when `src` is a random in-fold slice sized to the eval fold.

    So the peek is guaranteed SAME-FAMILY by construction rather than by care (NF1.7 (b)), and a
    single field-wide bucket ceiling cannot veto a legitimately-better nested form (NF-D16 g‴).
    """
    is_cold = ev_week <= COLD_START_MAX_WEEK
    d = np.zeros(len(ev_week), float)
    info: dict[str, Any] = {"form": form, "n_source": int(len(src))}
    if form == "zero":
        info["delta"] = 0.0
        return d, info

    cold_src = _cold(src)
    if form in ("bucket", "shrunk", "over2"):
        v = cold_src["model_err"].to_numpy(float)
        if len(v) == 0:
            raise SystemExit(f"[{_STORY}] form {form!r} has no cold-start source rows; an "
                             "unevaluable magnitude is never a pass (NF1.7 (a)).")
        m = float(np.mean(v))
        se = float(np.std(v, ddof=1) / np.sqrt(len(v))) if len(v) > 1 else float("nan")
        delta = {"bucket": m, "over2": 2.0 * m, "shrunk": _js_shrink(m, se)}[form]
        d[is_cold] = delta
        info.update({"delta": delta, "raw_mean": m, "se": se, "n_cold_source": int(len(v))})
        return d, info

    if form == "per_week":
        per = {}
        for w in range(1, COLD_START_MAX_WEEK + 1):
            v = cold_src.loc[cold_src[WEEK_COL] == w, "model_err"].to_numpy(float)
            if len(v) == 0:
                raise SystemExit(f"[{_STORY}] form 'per_week' has no source rows for week {w}; an "
                                 "unevaluable magnitude is never a pass (NF1.7 (a)).")
            per[w] = float(np.mean(v))
            d[is_cold & (ev_week == w)] = per[w]
        info.update({"delta_by_week": {str(k): v for k, v in per.items()},
                     "delta": float(np.mean(d[is_cold])) if is_cold.any() else 0.0})
        return d, info

    if form == "linear":
        w = cold_src[WEEK_COL].to_numpy(float)
        v = cold_src["model_err"].to_numpy(float)
        if len(np.unique(w)) < 2:
            raise SystemExit(f"[{_STORY}] form 'linear' needs ≥2 distinct source weeks; an "
                             "unevaluable magnitude is never a pass (NF1.7 (a)).")
        A = np.column_stack([np.ones_like(w), w])
        coef, *_ = np.linalg.lstsq(A, v, rcond=None)
        d[is_cold] = coef[0] + coef[1] * ev_week[is_cold].astype(float)
        info.update({"intercept": float(coef[0]), "slope": float(coef[1]),
                     "delta": float(np.mean(d[is_cold])) if is_cold.any() else 0.0})
        return d, info

    if form in ("pooled_all", "pooled_cold"):
        m = float(src["model_err"].mean())
        if form == "pooled_all":
            d[:] = m                      # ⛔ EVERY row — the SCOPING foil
        else:
            d[is_cold] = m                # weeks 1–3 only — the MAGNITUDE foil
        info.update({"delta": m})
        return d, info

    raise KeyError(f"unknown estimator form {form!r}")


def _eval_source(ev_week: np.ndarray, ev_err: np.ndarray, ev_season: int) -> pd.DataFrame:
    """The EVAL fold's own residuals, shaped as an estimator source frame — the PEEK.

    ⛔ Only ever handed to a diagnostic anchor. Its columns are pinned to `ESTIMATOR_COLUMNS` and
    market-blindness is re-asserted, so the peek cannot become a back door for a market column
    either."""
    src = pd.DataFrame({WEEK_COL: ev_week, "season": ev_season,
                        "mu_total": np.nan, "y_total": np.nan, "model_err": ev_err})
    src = src[list(ESTIMATOR_COLUMNS)]
    assert_estimator_is_market_blind(src)
    return src


# ===========================================================================
# Stage 1 — score every arm on every fold
# ===========================================================================

def _bucket_slices(n: int, *, min_bucket: int = 40, max_slices: int = 2) -> list[np.ndarray]:
    """Split a fold's cold-start rows into PBO buckets, never below `min_bucket` rows.

    ⚠️ A fold thin enough to yield one bucket contributes ONE bucket and says so; it is not padded
    and it is not dropped (2020's staggered COVID start leaves only 34 cold-start rows)."""
    k = max(1, min(max_slices, n // min_bucket))
    return [a for a in np.array_split(np.arange(n), k) if len(a) > 0]


def stage_score(args) -> dict[str, Any]:
    df, feat, meta = B.load_cache()
    df, feat, pace = B.ensure_pace_composites(df, feat, context=_STORY)
    print(f"=== {_STORY} stage 1 — SCORE ({len(ARMS)} arms; field {DECLARED_FIELD_SIZE}) ===")
    print(f"  cache {meta.get('assembled_at')} · {len(df):,} games · "
          f"{int(df['has_close'].sum()):,} closes · pace derived in-session: "
          f"{pace.get('pace_derived_in_session')}")

    folds = B.build_folds(df, feat, max_folds=args.max_folds)
    df_sorted = df.sort_values([B._YEAR, "season_order_week", B._DATE]).reset_index(drop=True)
    cand = B.build_candidate(SERVED["mc"])
    rng = np.random.default_rng(args.seed)

    arm_folds: dict[str, list[dict]] = {a.name: [] for a in ARMS}
    per_fold_meta: list[dict] = []
    oos_rows: list[pd.DataFrame] = []

    for fold in folds:
        cols = B.resolve_contract(SERVED["contract"], fold.X_tr, fold.feat_cols, fold.ranking,
                                  top_k=B._DEFAULT_TOP_K)
        assert_market_blind(cols, context=f"{_STORY} fold {fold.eval_year}")
        cols_idx = np.array([fold.feat_cols.index(c) for c in cols])
        _, mu_t, _, _ = cand.fit_predict(fold.X_tr[:, cols_idx], fold.y_m_tr, fold.y_t_tr,
                                         fold.X_ev[:, cols_idx])
        # σ — fitted per fold on the INNER HOLDOUT exactly as `_fit_dispersion` does, then FROZEN
        # across every arm (C7). The contest is about μ and only μ.
        _disp, dinfo, _sig_m, sig_t = B._fit_dispersion(cand, fold, cols_idx, SERVED["form"],
                                                        None, None)
        y_t = fold.y_t_ev
        wk = fold.ev_meta[WEEK_COL].to_numpy()
        infold = infold_oos(df_sorted, feat, cols, fold.eval_year)
        n_cold = int((wk <= COLD_START_MAX_WEEK).sum())
        print(f"  fold {fold.eval_year}: {len(y_t):,} eval ({n_cold} cold-start) | in-fold "
              f"{len(infold):,} rows / {len(_cold(infold)):,} cold-start | σ_total med "
              f"{float(np.median(sig_t)):.2f}")
        per_fold_meta.append({
            "eval_year": int(fold.eval_year), "n_eval": int(len(y_t)), "n_cold": n_cold,
            "n_infold": int(len(infold)), "n_infold_cold": int(len(_cold(infold))),
            "sigma_total_median": float(np.median(sig_t)), "dispersion": dinfo,
        })
        oos_rows.append(pd.DataFrame({
            "game_id": fold.ev_meta["game_id"].to_numpy(), "season": int(fold.eval_year),
            WEEK_COL: wk, "mu_total": mu_t, "y_total": y_t, "sigma_total": sig_t,
        }))

        ev_err = mu_t - y_t          # ⛔ handed ONLY to the peeking anchors
        peek_src = _eval_source(wk, ev_err, int(fold.eval_year))
        cold_mask = wk <= COLD_START_MAX_WEEK
        late_mask = ~cold_mask
        # the matched-n source: an in-fold slice the size of THIS fold's cold-start cell, so the
        # peek is readable at matched family AND matched SAMPLE (NF1.9 (f)).
        infold_cold = _cold(infold)
        n_match = min(int(cold_mask.sum()), len(infold_cold))
        matched_src = infold_cold.iloc[rng.choice(len(infold_cold), size=n_match, replace=False)]

        def _score(mu_prime: np.ndarray) -> dict[str, Any]:
            return {
                "cold": cell_metrics(y_t[cold_mask], mu_prime[cold_mask], sig_t[cold_mask]),
                "pooled": cell_metrics(y_t, mu_prime, sig_t),
                "late": cell_metrics(y_t[late_mask], mu_prime[late_mask], sig_t[late_mask]),
                "sigma_checksum": float(np.sum(sig_t)),
                "buckets": [float(np.mean(gaussian_crps(
                    y_t[cold_mask][sl], mu_prime[cold_mask][sl], sig_t[cold_mask][sl])))
                    for sl in _bucket_slices(int(cold_mask.sum()))],
            }

        for a in ARMS:
            # the SOURCE is what separates an honest arm from an anchor; the FORM is shared.
            src = {"oracle_bucket": peek_src, "matched_n_bucket": matched_src}.get(a.name, infold)
            d, info = _estimate(a.form, src, wk)
            row = {"eval_year": int(fold.eval_year), "fitted": info, **_score(mu_t - d)}
            if a.role in ("candidate", "lose"):
                # ⭐ C8's own-form floor: the peeking version of THIS arm's own estimator, and its
                # own matched-n control. One field-wide ceiling would falsely veto a legitimately
                # better nested form (NF-D16 g‴), and a peek that cannot beat its own matched-n
                # control could not act at all (NF-W6d).
                d_pk, i_pk = _estimate(a.form, peek_src, wk)
                d_mn, i_mn = _estimate(a.form, matched_src, wk)
                row["own_form_peek"] = {"crps_cold": _score(mu_t - d_pk)["cold"]["crps"],
                                        "delta": i_pk.get("delta")}
                row["own_form_matched_n"] = {"crps_cold": _score(mu_t - d_mn)["cold"]["crps"],
                                             "delta": i_mn.get("delta"), "n_source": n_match}
            if a.name == FOIL_ARM:
                # ⭐ Scored at TWO draw counts. A single gap cannot distinguish "the two estimators
                # disagree" from "the sampler has not converged yet" — the gap must SHRINK ~1/√n,
                # and only that convergence is evidence they score the same predictive.
                row["crps_sampled_control"] = {
                    str(n): crps_sampled_control(
                        y_t[cold_mask], (mu_t - d)[cold_mask], sig_t[cold_mask],
                        n_draws=n, seed=args.seed + int(fold.eval_year))
                    for n in (args.n_draws, 4 * args.n_draws)}
            arm_folds[a.name].append(row)

    oos = pd.concat(oos_rows, ignore_index=True)
    doc = {
        "story": _STORY, "scored_at": date.today().isoformat(),
        "served_config": dict(SERVED), "cache": {k: meta.get(k) for k in
                                                 ("assembled_at", "n_games", "n_with_close")},
        "n_oos_games": int(len(oos)), "fold_years": [f["eval_year"] for f in per_fold_meta],
        "n_folds": len(folds), "folds": per_fold_meta,
        "declared_field_size": DECLARED_FIELD_SIZE,
        "arms": {a.name: {"role": a.role, "scope": a.scope, "n_params": a.n_params, "doc": a.doc,
                          "folds": arm_folds[a.name]} for a in ARMS},
        "reproduction_pin": check_pin(meta, oos, [f["eval_year"] for f in per_fold_meta]),
        "over_tilt": over_tilt_report(df, oos, arm_folds),
        "inner_min_train_seasons": INNER_MIN_TRAIN_SEASONS,
        "market_blind": True, "best_alpha": 0,
    }
    _SCORES_JSON.write_text(json.dumps(doc, indent=2, default=float))
    print(f"\n  scores → {_SCORES_JSON.relative_to(B._PROJECT_ROOT)}")
    return doc


def check_pin(meta: dict, oos: pd.DataFrame, fold_years: list[int]) -> dict[str, Any]:
    """§6 — HALT if the population is not the one this study was pre-registered against."""
    checks = {
        "cache_assembled_at": (meta.get("assembled_at"), PIN["cache_assembled_at"]),
        "n_with_close": (int(meta.get("n_with_close", -1)), PIN["n_with_close"]),
        "n_oos_games": (int(len(oos)), PIN["n_oos_games"]),
        "fold_years": (list(map(int, fold_years)), PIN["fold_years"]),
    }
    out = {k: {"got": g, "expected": e, "ok": bool(g == e)} for k, (g, e) in checks.items()}
    return {"checks": out, "all_ok": all(v["ok"] for v in out.values()), "source": PIN["source"]}


def over_tilt_report(df: pd.DataFrame, oos: pd.DataFrame, arm_folds: dict) -> dict[str, Any]:
    """The AC's headline, on the close-carrying `wk1-3` rows: does the correction actually reduce
    the over-tilt?

    ⚠️ This is the ONLY market-touching number in the study and it is **DESCRIPTIVE** — it is not a
    clause, not a selection criterion and not an edge claim. The estimator never sees it (C4).
    Joined on `game_id` and read off each row's own μ, so it takes no positional index into any
    array — the NCAAF-VAL2 §2 / CLV-repair misalignment cannot reach it.
    """
    close = df[["game_id", "close_total", "has_close"]].drop_duplicates("game_id")
    merged = oos.merge(close, on="game_id", how="left")
    if len(merged) != len(oos):
        raise SystemExit(f"[{_STORY}] the close join changed the row count; refusing to report.")
    m = merged[(merged["has_close"] == True) &                                    # noqa: E712
               (merged[WEEK_COL] <= COLD_START_MAX_WEEK)].reset_index(drop=True)
    if len(m) == 0:
        # Reachable on a truncated (`--max-folds`) run whose eval seasons all predate the 2020 odds
        # floor. Reported as UNEVALUABLE rather than as a NaN that reads like a measurement — an
        # unevaluable check is never a pass (NF1.7 (a)).
        return {"n_close_carrying_cold": 0, "over_actually_hit": None, "arms": {},
                "state": "UNEVALUABLE",
                "note": ("no close-carrying cold-start rows in this run's eval seasons (the odds "
                         "floor is 2020); the over-tilt report is UNEVALUABLE, not zero.")}
    out: dict[str, Any] = {"n_close_carrying_cold": int(len(m)), "state": "EVALUABLE",
                           "over_actually_hit": float(np.mean(
                               m["y_total"].to_numpy() > m["close_total"].to_numpy())),
                           "note": ("DESCRIPTIVE. The model's side vs the close on the cold-start "
                                    "rows, before and after each arm's shift. Never a clause; "
                                    "best_alpha = 0 and no edge claim is made.")}
    tilt: dict[str, Any] = {}
    for name, folds in arm_folds.items():
        d_by_year = {int(f["eval_year"]): f["fitted"] for f in folds}
        shift = np.array([_delta_for_row(d_by_year[int(s)], int(w))
                          for s, w in zip(m["season"], m[WEEK_COL])], float)
        mu_p = m["mu_total"].to_numpy() - shift
        tilt[name] = {"model_to_over": float(np.mean(mu_p > m["close_total"].to_numpy())),
                      "mean_offset_pts": float(np.mean(mu_p - m["close_total"].to_numpy()))}
    out["arms"] = tilt
    return out


def _delta_for_row(fitted: dict, week: int) -> float:
    """The δ one arm applied to one cold-start row, recovered from its recorded fit."""
    if "delta_by_week" in fitted:
        return float(fitted["delta_by_week"][str(week)])
    if "slope" in fitted:
        return float(fitted["intercept"] + fitted["slope"] * week)
    return float(fitted.get("delta") or 0.0)


# ===========================================================================
# Stage 2 — the gates, executed rather than narrated
# ===========================================================================

def fold_series(foil: list[dict], arm: list[dict], cell: str = "cold") -> np.ndarray:
    """Per-fold IMPROVEMENT in CRPS (foil − arm), so POSITIVE = the arm is better."""
    return np.array([f[cell]["crps"] - a[cell]["crps"] for f, a in zip(foil, arm)], float)


def sharpe(s: np.ndarray) -> float:
    sd = float(np.std(s, ddof=1))
    return float(np.mean(s) / sd) if sd > 1e-15 else 0.0


def series_moments(s: np.ndarray) -> tuple[float, float]:
    """(skew, kurtosis) in `deflated_sharpe`'s convention — MEASURED, never the Gaussian default.

    ⭐ Load-bearing: `deflated_sharpe`'s benchmark uses the series' own higher moments, and handing
    it the default (0, 3) on an 8-point series silently changes the bar (the P2.5 note)."""
    if len(s) < 4:
        return 0.0, 3.0
    return float(stats.skew(s, bias=False)), float(stats.kurtosis(s, bias=False, fisher=False))


def paired_p(s: np.ndarray) -> float:
    """One-sided paired t on the per-fold improvement (H1: the arm beats the foil)."""
    if len(s) < 2 or float(np.std(s, ddof=1)) <= 1e-15:
        return 1.0
    t, p = stats.ttest_1samp(s, 0.0)
    return float(p / 2.0 if t > 0 else 1.0 - p / 2.0)


def bh(pvals: dict[str, float], alpha: float = FDR_ALPHA) -> tuple[dict[str, bool], float]:
    names = list(pvals)
    p = np.array([pvals[n] for n in names], float)
    order = np.argsort(p, kind="stable")
    m, k = len(p), 0
    for rank, i in enumerate(order, start=1):
        if p[i] <= rank / m * alpha:
            k = rank
    cut = (k / m * alpha) if k else (1.0 / m * alpha)
    keep = {n: False for n in names}
    for rank, i in enumerate(order, start=1):
        if rank <= k:
            keep[names[i]] = True
    return keep, float(cut)


def ship_clauses(arm: str, arm_folds: list[dict], foil_folds: list[dict],
                 anchors: dict[str, Any]) -> dict[str, Any]:
    """C1–C8. Every clause is a REFUSAL condition, and each is isolable (NF-D17: a fixture that
    trips two clauses proves neither, so each reads exactly one quantity)."""
    def _agg(rows: list[dict], cell: str, key: str) -> float:
        return float(np.mean([r[cell][key] for r in rows if r[cell]["n"]]))

    pooled_pit = _agg(arm_folds, "pooled", "pit_max_decile_dev")
    foil_pit = _agg(foil_folds, "pooled", "pit_max_decile_dev")
    pooled_cal = _agg(arm_folds, "pooled", "calib_80")
    cold_cal = _agg(arm_folds, "cold", "calib_80")
    scope = next(a.scope for a in ARMS if a.name == arm)
    late_gap = max(abs(a["late"]["crps"] - f["late"]["crps"])
                   for a, f in zip(arm_folds, foil_folds) if a["late"]["n"])
    sigma_gap = max(abs(a["sigma_checksum"] - f["sigma_checksum"])
                    for a, f in zip(arm_folds, foil_folds))
    orc = anchors["per_form_oracle"].get(arm, {})
    return {
        "C1_pooled_pit_not_degraded": {
            "ok": bool(pooled_pit <= foil_pit + PIT_DEGRADE_TOL),
            "arm": round(pooled_pit, 5), "foil": round(foil_pit, 5), "tol": PIT_DEGRADE_TOL},
        "C2_pooled_calib_floor": {"ok": bool(pooled_cal >= CALIB_FLOOR),
                                  "value": round(pooled_cal, 4), "floor": CALIB_FLOOR},
        "C3_cold_calib_floor": {"ok": bool(cold_cal >= CALIB_FLOOR),
                                "value": round(cold_cal, 4), "floor": CALIB_FLOOR},
        # C4 is enforced at the ESTIMATOR (assert_estimator_is_market_blind raises), so by the time
        # a score exists it has already held. Recorded so the clause is visible in the artifact.
        "C4_market_blind_estimator": {"ok": True, "enforced_at": "assert_estimator_is_market_blind"},
        "C5_week_scoped": {
            # `pooled_level` is DECLARED to touch every row, so the week-scoping invariant does not
            # apply to it — it is the foil that removes exactly that channel.
            "ok": bool(scope == "all" or late_gap <= FROZEN_TOL),
            "max_late_crps_gap": late_gap, "scope": scope, "tol": FROZEN_TOL},
        "C6_margin_frozen": {"ok": True, "enforced_at": "no arm touches mu_margin (by construction)"},
        "C7_sigma_frozen": {"ok": bool(sigma_gap <= FROZEN_TOL), "max_gap": sigma_gap,
                            "tol": FROZEN_TOL},
        "C8_own_form_oracle_floor": {"ok": orc.get("state") != "BEATEN", "state": orc.get("state"),
                                     "gap": orc.get("gap")},
    }


def anchor_report(arms: dict[str, Any], foil: list[dict]) -> dict[str, Any]:
    """The PER-FORM peeking floor and, beside each, its OWN matched-n control.

    Two rules the vertical has paid for, both enforced here rather than described:

    * **NF-D16 (g‴) — one ceiling per FORM.** `per_week_shift` and `linear_decay` both CONTAIN the
      bucket constant as a special case, so either can legitimately beat a *bucket* peek by pure
      capacity. Flooring the whole field on one bucket ceiling would veto a real winner as a metric
      inversion, which is the closest that lesson's story came to a wrong answer.
    * **NF-W6d / NF-D20 — an anchor pair that could not ACT is `INACTIVE`, not a refusal.** If a
      form's peek does not beat its own matched-n control, the peek bought nothing at that sample
      size and its floor is uninformative: never a pass and never a fail.
    """
    def _mean(rows: list[dict], path: tuple[str, ...]) -> float:
        vals = []
        for r in rows:
            v: Any = r
            for k in path:
                v = v[k]
            vals.append(float(v))
        return float(np.mean(vals))

    foil_crps = _mean(foil, ("cold", "crps"))
    per_form: dict[str, Any] = {}
    for a in ARMS:
        if a.role not in ("candidate", "lose"):
            continue
        rows = arms[a.name]["folds"]
        arm_crps = _mean(rows, ("cold", "crps"))
        peek = _mean(rows, ("own_form_peek", "crps_cold"))
        mn = _mean(rows, ("own_form_matched_n", "crps_cold"))
        peek_gain = mn - peek                      # > 0 ⇒ the peek genuinely bought something
        active = bool(peek_gain > TIE_BAND)
        gap = arm_crps - peek                      # > 0 ⇒ the arm is WORSE than its own peek
        state = ("INACTIVE" if not active else
                 "BEATEN" if gap < -TIE_BAND else
                 "TIED" if abs(gap) <= TIE_BAND else "FLOORED")
        per_form[a.name] = {"form": a.form, "arm_crps": arm_crps, "peek_crps": peek,
                            "matched_n_crps": mn, "peek_gain_over_matched_n": peek_gain,
                            "anchor_pair_active": active, "gap": gap, "state": state}
    head_orc = _mean(arms["oracle_bucket"]["folds"], ("cold", "crps"))
    head_mn = _mean(arms["matched_n_bucket"]["folds"], ("cold", "crps"))
    return {
        "headline_bucket_oracle_crps_cold": head_orc,
        "headline_matched_n_crps_cold": head_mn,
        "headline_peek_gain": head_mn - head_orc,
        "headline_pair_active": bool(head_mn - head_orc > TIE_BAND),
        "foil_crps_cold": foil_crps,
        "reading": ("a peeking oracle is a floor only at MATCHED family AND MATCHED sample "
                    "(NF1.7 (b) / NF1.9 (f)); it is computed PER FORM (NF-D16 g‴) and a peek that "
                    "does not beat its own matched-n control could not act, so its floor is "
                    "INACTIVE — uninformative, never a pass and never a fail (NF-W6d / NF-D20)."),
        "per_form_oracle": per_form,
    }


def channel_attribution(arms: dict[str, Any], foil: list[dict]) -> dict[str, Any]:
    """Which CHANNEL the effect lives in — read as PAIRED deltas, never as a leaderboard rank.

    ⚠️ **A structural fact about this design, and it is arithmetic rather than a result** (so it is
    stated here rather than treated as a finding): `pooled_level` and `week_blind` apply the SAME δ
    to the SAME cold-start rows, so on the PRIMARY (cold-cell) metric they are IDENTICAL BY
    CONSTRUCTION. The primary metric is therefore structurally BLIND to the scoping channel, and the
    two channels have to be read on different cells:

      * **MAGNITUDE** (is the magnitude week-informed?) — `bucket_shift` vs `week_blind` on the COLD
        cell. Scoping is held fixed; only the number changes.
      * **SCOPING** (should the correction be confined to weeks 1–3?) — `week_blind` vs
        `pooled_level` on the POOLED cell, the only cell in which the two differ at all.

    Each pair keeps the entire machinery and removes exactly one claimed channel, so a win is
    ATTRIBUTABLE rather than merely observed (NF-D10 / NF-D15 g′).
    """
    def _fold(name: str, cell: str) -> np.ndarray:
        return np.array([f[cell]["crps"] for f in arms[name]["folds"]], float)

    foil_cold = np.array([f["cold"]["crps"] for f in foil], float)
    foil_pool = np.array([f["pooled"]["crps"] for f in foil], float)
    mag = _fold("week_blind", "cold") - _fold("bucket_shift", "cold")
    sco = _fold("pooled_level", "pooled") - _fold("week_blind", "pooled")
    return {
        "magnitude_channel": {
            "pair": "bucket_shift − week_blind", "cell": "wk1-3",
            "mean_gain": float(np.mean(mag)), "folds_positive": int(np.sum(mag > 0)),
            "n_folds": int(len(mag)), "p_one_sided": paired_p(mag),
            "reading": ("> 0 ⇒ a week-informed magnitude beats the pooled one with the scoping "
                        "held fixed."),
        },
        "scoping_channel": {
            "pair": "week_blind − pooled_level", "cell": "pooled (all rows)",
            "mean_gain": float(np.mean(sco)), "folds_positive": int(np.sum(sco > 0)),
            "n_folds": int(len(sco)), "p_one_sided": paired_p(sco),
            "reading": ("> 0 ⇒ confining the SAME magnitude to weeks 1–3 beats spreading it over "
                        "every row. Read on the POOLED cell because the two arms are identical by "
                        "construction on the cold cell."),
        },
        "foil_cold_crps": float(np.mean(foil_cold)),
        "foil_pooled_crps": float(np.mean(foil_pool)),
        "why_two_cells": ("the primary metric is the wk1-3 cell (the only rows the mechanism can "
                          "move — NCAAF-P2.1 (f)); the scoping channel is invisible there BY "
                          "CONSTRUCTION and is therefore read on the pooled cell. Stated as an "
                          "arithmetic property of the design, not discovered from a score."),
    }


def _pbo_over(arms: dict[str, Any], names: list[str]) -> dict[str, Any]:
    """CSCV/PBO over one arm SUBSET's per-bucket CRPS matrix."""
    perf = np.array([[b for f in arms[a]["folds"] for b in f["buckets"]] for a in names], float).T
    n_bk = perf.shape[0]
    res = pbo_cscv(perf, higher_is_better=False, n_splits=max(2, min(16, n_bk - (n_bk % 2))))
    return {"arms": names, "n_arms": len(names), "n_buckets": int(n_bk),
            "pbo": float(res.pbo), "n_combos": int(res.n_combos)}


def stage_decide(args) -> dict[str, Any]:
    if not _SCORES_JSON.exists():
        raise SystemExit(f"[{_STORY}] no scores — run `--stage score` first.")
    doc = json.loads(_SCORES_JSON.read_text())
    arms, n_folds = doc["arms"], int(doc["n_folds"])
    foil = arms[FOIL_ARM]["folds"]
    real = [a for a in (CANDIDATES + LOSERS)]

    pin = doc["reproduction_pin"]
    if not pin["all_ok"] and not args.allow_pin_fail:
        raise SystemExit(f"[{_STORY}] §6 reproduction pin FAILED: "
                         f"{json.dumps(pin['checks'], indent=1)}\nThe population is not the one "
                         "this study was pre-registered against. Re-run the PARENT and re-anchor "
                         "from ITS output (⛔ never from VAL3's own).")

    anchors = anchor_report(arms, foil)
    channels = channel_attribution(arms, foil)
    series = {a: fold_series(foil, arms[a]["folds"]) for a in real}
    # ⭐ V over the REAL (non-foil, non-diagnostic) arms ONLY — a diagnostic anchor must never set
    # the gate's own bar (MH2.1 (a)). The FULL-FIELD reading BINDS; the DSR-CONV variant (designed
    # losers excluded from V) is reported as a labelled diagnostic. Declared FORWARD in §5.
    sr_all = np.array([sharpe(series[a]) for a in real], float)
    sr_sel = np.array([sharpe(series[a]) for a in CANDIDATES], float)
    V_binding = float(np.var(sr_all, ddof=1)) if len(sr_all) > 1 else None
    V_convention = float(np.var(sr_sel, ddof=1)) if len(sr_sel) > 1 else None

    bucket_arms = [FOIL_ARM] + real
    n_b = min(len(arms[a]["folds"][i]["buckets"]) for a in bucket_arms for i in range(n_folds))
    perf = np.array([[b for f in arms[a]["folds"] for b in f["buckets"]] for a in bucket_arms],
                    float).T
    n_bk = perf.shape[0]
    n_splits = max(2, min(16, n_bk - (n_bk % 2)))
    pbo_res = pbo_cscv(perf, higher_is_better=False, n_splits=n_splits)
    pbo = float(pbo_res.pbo)

    clause = cv_power.fold_consistency_clause(n_folds)
    pvals = {a: paired_p(series[a]) for a in real}
    bh_pass, bh_cut = bh(pvals)

    rows: dict[str, Any] = {}
    for a in real:
        s = series[a]
        spec = next(x for x in ARMS if x.name == a)
        gain = float(np.mean([f["cold"]["crps"] for f in foil])
                     - np.mean([f["cold"]["crps"] for f in arms[a]["folds"]]))
        sk, ku = series_moments(s)
        # `deflated_sharpe` needs >=3 observations; below that DSR is UNDEFINED, not failed
        # (cv_power's own rule for a stat that could not be COMPUTED).
        d = (deflated_sharpe(s, n_trials=DECLARED_FIELD_SIZE, var_trials_sr=V_binding)
             if len(s) >= 3 else None)
        d_conv = (deflated_sharpe(s, n_trials=DECLARED_FIELD_SIZE, var_trials_sr=V_convention)
                  if len(s) >= 3 else None)
        wins = int(np.sum(s > 0))
        rows[a] = {
            "arm": a, "role": spec.role, "scope": spec.scope, "n_params": spec.n_params,
            "doc": spec.doc,
            "cold_crps": float(np.mean([f["cold"]["crps"] for f in arms[a]["folds"]])),
            "gain_vs_foil_cold": gain,
            "pooled_gain_vs_foil": float(np.mean([f["pooled"]["crps"] for f in foil])
                                         - np.mean([f["pooled"]["crps"] for f in arms[a]["folds"]])),
            "tie_with_foil": bool(abs(gain) <= TIE_BAND),
            "fold_wins": wins, "n_folds": n_folds,
            "fold_consistency_required": clause.wins_required,
            "fold_consistency_ok": bool(clause.passes(wins)),
            "sharpe": sharpe(s), "series_skew": sk, "series_kurt": ku,
            "dsr": None if d is None else float(d.dsr),
            "sr0": None if d is None else float(d.sr0),
            "dsr_convention_variant": None if d_conv is None else float(d_conv.dsr),
            "p_one_sided": float(pvals[a]), "bh_pass": bool(bh_pass[a]),
            "calibration": {
                cell: {k: float(np.mean([f[cell][k] for f in arms[a]["folds"] if f[cell]["n"]]))
                       for k in ("crps", "pit_max_decile_dev", "calib_80", "bias")}
                for cell in ("cold", "pooled", "late")},
            "mean_delta_pts": float(np.mean([abs(f["fitted"].get("delta") or 0.0)
                                             for f in arms[a]["folds"]])),
            "per_fold_delta": [f["fitted"].get("delta") for f in arms[a]["folds"]],
            "clauses": ship_clauses(a, arms[a]["folds"], foil, anchors),
        }
        rows[a]["clauses"]["all_ok"] = all(v["ok"] for k, v in rows[a]["clauses"].items()
                                           if k.startswith("C"))

    def _ships(a: str) -> bool:
        r = rows[a]
        spec = next(x for x in ARMS if x.name == a)
        return bool(spec.role == "candidate" and r["clauses"]["all_ok"] and not r["tie_with_foil"]
                    and r["gain_vs_foil_cold"] > 0 and r["dsr"] is not None
                    and r["dsr"] >= DSR_GATE and r["bh_pass"]
                    and r["fold_consistency_ok"] and pbo < PBO_GATE)

    survivors = [a for a in CANDIDATES if _ships(a)]
    best = min(real, key=lambda a: rows[a]["cold_crps"])
    best_candidate = min(CANDIDATES, key=lambda a: rows[a]["cold_crps"])
    verdict = "SHIP_CORRECTION" if survivors else "INCUMBENT_STANDS"

    # ── the null, classified ────────────────────────────────────────────────────────────────────
    null: dict[str, Any] = {}
    if not survivors:
        r = rows[best_candidate]
        s = series[best_candidate]
        failed = [k for k, v in r["clauses"].items() if k.startswith("C") and not v["ok"]]
        # which GATE actually refused? Three genuinely different answers, and conflating them is
        # how a record ends up publishing the wrong remedy.
        deflation_failed = [g for g, ok in (
            ("pbo", pbo < PBO_GATE),
            ("dsr", r["dsr"] is not None and r["dsr"] >= DSR_GATE),
            ("bh_fdr", r["bh_pass"]),
            ("fold_consistency", r["fold_consistency_ok"]),
        ) if not ok]
        v = cv_power.classify_null(
            metric="crps_total_wk1_3", n_folds=n_folds, n_arms=len(real),
            beats_foil=bool(r["gain_vs_foil_cold"] > TIE_BAND),
            observed_sr=r["sharpe"], var_trials_sr=V_binding, fold_wins=r["fold_wins"],
            p_one_sided=r["p_one_sided"], bh_cutoff=bh_cut,
            skew=r["series_skew"], kurt=r["series_kurt"],
            declared_field_size=DECLARED_FIELD_SIZE, degenerates_excluded_from_v=False)
        null = {
            "best_candidate": best_candidate,
            "instrument_state": v.state, "instrument_reason": v.reason,
            "instrument_retest_trigger": v.retest_trigger, "instrument_detail": v.detail,
            "field_remedy_admissible": v.detail.get("field_remedy_admissible"),
            "constraint_clauses_failed": failed,
            "deflation_gates_failed": deflation_failed,
            "binding_half": ("constraint" if failed else
                             "deflation" if deflation_failed else "statistical"),
            "recorded_state": ("CONSTRAINT_REFUSED" if failed else
                               f"DEFLATION_REFUSED_{deflation_failed[0].upper()}"
                               if deflation_failed else v.state),
            "why_recorded_state": (
                "the refusal is caused by a pre-registered SHIP CLAUSE, not by the statistic — no "
                "fold count moves a clause, so publishing a `POWER_LIMITED`-style 'more seasons' "
                "trigger would be actively misleading (NF-D18). The instrument's own state is "
                "preserved above, never replaced." if failed else
                "the refusal is caused by a pre-registered DEFLATION gate that WAS evaluated and "
                "FAILED. ⚠️ `cv_power.classify_null` takes no PBO argument at all — it can express "
                "PBO-UNDEFINED (too few folds/arms) but NOT PBO-EVALUATED-AND-FAILED — so its own "
                "state structurally cannot see the gate that bound here. That is an INSTRUMENT GAP, "
                "recorded rather than worked around; the instrument's state is preserved above and "
                "is not the verdict. ⛔ No fold/season re-test trigger is published: the admissible "
                "remedy for a PBO refusal is a FORWARD-registered narrower coherent family (or a "
                "forward-registered PBO population), never more seasons and NEVER a post-hoc re-cut "
                "of a field already scored (MH2.2)." if deflation_failed else
                "no ship clause and no deflation gate bound; the statistic is what refused, so the "
                "instrument's state stands as recorded."),
            "meaningful_effect_not_preregistered": (
                "⚠️ This study pre-registered a materiality band in POINTS (inherited from VAL2) but "
                "NOT a practically-meaningful CRPS effect in SD units, so `classify_null` correctly "
                "falls through to its honest default rather than certifying the null as powered. "
                "⛔ Supplying one now would be re-deriving a bar from the answer (E2.1-r); it is a "
                "pre-registration gap, recorded as such, and a successor registers it forward."),
        }

    # ── PBO companions (NF1.8: a rank statistic alone cannot tell UNSTABLE from TIED) ───────────
    # ⭐ NF-D15 (g″): prove the null does not rest on the GATE CHOICE. The PRE-REGISTERED
    # population (foil + all 7 arms) BINDS; these are labelled diagnostics that quantify how much
    # of it is the pre-registered INELIGIBLE arms out-ranking the candidates. ⛔ Reading the null
    # off one of them after seeing the binding one fail would be the E2.1-r inversion / MH2.2
    # post-hoc field trim, and it is not done: the verdict above is computed on `pbo` alone.
    pbo_sensitivity = {
        "binding_preregistered": {**_pbo_over(arms, bucket_arms), "binds": True,
                                  "note": "§5's declared population: the foil + all 7 scored arms."},
        "eligible_set_only": {**_pbo_over(arms, [FOIL_ARM] + list(CANDIDATES)), "binds": False,
                              "note": ("the search the SELECTION actually ran — the foil + the 4 "
                                       "SELECTABLE candidates. Reported because CLAUDE.md's own "
                                       "PBO note says the eligible set is the right population; "
                                       "⛔ but it was NOT what this study pre-registered, so it "
                                       "cannot be adopted here (MH2.2).")},
        "two_arm_decision": {**_pbo_over(arms, [FOIL_ARM, best_candidate]), "binds": False,
            "note": ("the question a PM actually faces — correct vs do nothing. A 2-arm CSCV has "
                     "almost no search to overfit, so this is a lower bound, not a gate.")},
    }
    pooled_cold = {a: rows[a]["cold_crps"] for a in real}
    cand_cold = {a: rows[a]["cold_crps"] for a in CANDIDATES}
    flips: dict[str, int] = {a: 0 for a in bucket_arms}
    for i in range(n_folds):
        flips[min(bucket_arms, key=lambda a: arms[a]["folds"][i]["cold"]["crps"])] += 1

    # instrument control: the closed form vs the ensemble identity, on the foil, at two draw counts
    draw_ns = sorted(int(k) for k in foil[0]["crps_sampled_control"])
    ctl_gaps = {n: max(abs(f["cold"]["crps"] - f["crps_sampled_control"][str(n)]) for f in foil)
                for n in draw_ns}
    ctl_gap = ctl_gaps[draw_ns[-1]]
    ctl_converges = bool(ctl_gaps[draw_ns[-1]] < ctl_gaps[draw_ns[0]])

    out = {
        "story": _STORY, "decided_at": date.today().isoformat(),
        "verdict": verdict, "survivors": survivors,
        "best_arm_any_role": best, "best_candidate": best_candidate,
        "n_folds": n_folds, "fold_years": doc["fold_years"], "n_oos_games": doc["n_oos_games"],
        "cache": doc["cache"], "served_config": doc["served_config"],
        "declared_field_size": DECLARED_FIELD_SIZE,
        "reproduction_pin": pin,
        "crps_instrument_control": {
            "max_abs_gap_by_draws": {str(n): g for n, g in ctl_gaps.items()},
            "max_abs_gap_closed_form_vs_ensemble": ctl_gap,
            "gap_shrinks_with_draws": ctl_converges,
            "gap_pct_of_crps": float(100.0 * ctl_gap / np.mean([f["cold"]["crps"] for f in foil])),
            "reading": ("the closed-form Gaussian CRPS and the ensemble identity score the SAME "
                        "predictive; a disagreement would mean one of them is not scoring what "
                        "this study claims to score, and it would be invisible in every headline. "
                        "Read the CONVERGENCE, not the single gap: a fixed residual gap would be a "
                        "real disagreement, a gap that shrinks ~1/√n is the sampler's own error."),
        },
        "deflation": {
            "pbo": pbo, "pbo_gate": PBO_GATE, "pbo_pass": bool(pbo < PBO_GATE),
            "n_buckets": int(n_bk), "n_cscv_combos": int(pbo_res.n_combos),
            "dsr_gate": DSR_GATE, "bh_alpha": FDR_ALPHA, "bh_cutoff": bh_cut,
            "var_trials_sr_binding": V_binding,
            "var_trials_sr_convention_variant": V_convention,
            "v_binding_note": ("FULL-FIELD V (all 7 non-foil, non-diagnostic arms) BINDS, declared "
                               "forward in §5. The DSR-CONV variant (designed losers excluded from "
                               "V) is reported as a labelled diagnostic. Declaring the generous "
                               "reading NON-binding is the conservative direction and forecloses "
                               "the NF-W7h failure in which a post-hoc re-read of V deletes the "
                               "arm under test."),
            "fold_consistency": {"n_folds": n_folds, "required_wins": clause.wins_required,
                                 "attainable": bool(clause.attainable),
                                 "attained_false_fire": float(clause.attained_false_fire),
                                 "legacy_required": clause.legacy_wins_required,
                                 "legacy_false_fire": float(clause.legacy_false_fire)},
        },
        "pbo_sensitivity": pbo_sensitivity,
        "pbo_companions": {
            # ⭐ NF1.8: a spread computed over a field that CONTAINS its own pre-registered nulls
            # measures the NULLS, not the contest. Both are reported; the CANDIDATE spread is the
            # one that answers "do the selectable arms genuinely tie?".
            "whole_field_spread_crps": float(max(pooled_cold.values()) - min(pooled_cold.values())),
            "contender_spread_crps": float(max(cand_cold.values()) - min(cand_cold.values())),
            "contender_spread_pct_of_foil": float(
                (max(cand_cold.values()) - min(cand_cold.values()))
                / np.mean([f["cold"]["crps"] for f in foil]) * 100.0),
            "fold_flip_distribution": flips,
            "reading": ("E2.1-r/NF1.8: a HIGH PBO over a field whose candidates genuinely TIE is "
                        "the NULL, not evidence of overfitting; a high PBO with a WIDE spread IS "
                        "overfitting. The SPREAD is the discriminator, reported beside the flips."),
        },
        "anchors": anchors, "channel_attribution": channels,
        "foil": {"arm": FOIL_ARM,
                 "cold_crps": float(np.mean([f["cold"]["crps"] for f in foil])),
                 "pooled_crps": float(np.mean([f["pooled"]["crps"] for f in foil])),
                 "cold_bias_pts": float(np.mean([f["cold"]["bias"] for f in foil])),
                 "pooled_bias_pts": float(np.mean([f["pooled"]["bias"] for f in foil]))},
        "arms": rows, "_foil_folds": foil,
        "null_classification": null,
        "over_tilt": doc["over_tilt"],
        "folds": doc["folds"], "inner_min_train_seasons": doc["inner_min_train_seasons"],
        "market_blind": True, "best_alpha": 0,
        "serving_change": None,
    }
    _OUT_JSON.write_text(json.dumps(out, indent=2, default=float))
    _OUT_MD.write_text(render_md(out))
    return out


# ===========================================================================
# Report
# ===========================================================================

def _f(x: float | None, nd: int = 3) -> str:
    """Render a possibly-UNDEFINED statistic. A stat that could not be computed must never render
    as a number a reader can compare (cv_power's UNDEFINED rule)."""
    return "n/a" if x is None else f"{x:.{nd}f}"


def render_md(d: dict) -> str:
    A: list[str] = []
    a = A.append
    f = d["foil"]
    a(f"# {_STORY} — cold-start μ_total correction (weeks 1–3, in-fold selected)")
    a("")
    a(f"**Verdict: `{d['verdict']}`.** Market-blind · `best_alpha = 0` · no serving change, no "
      "registry edit, no refit of a served artifact, no bet.")
    a("")
    a(f"_Cache {d['cache']['assembled_at']} · {d['n_oos_games']:,} OOS games · {d['n_folds']} purged "
      f"folds {d['fold_years'][0]}–{d['fold_years'][-1]} · served config "
      f"`{d['served_config']['mc']}`/`{d['served_config']['contract']}`/"
      f"`{d['served_config']['form']}` · declared field {d['declared_field_size']}_")
    a("")
    a("## 1. The field and what each arm did")
    a("")
    a("| arm | role | δ̄ (pts) | CRPS wk1-3 | gain vs foil | folds won | DSR | p | clauses |")
    a("|---|---|---|---|---|---|---|---|---|")
    a(f"| `none` (foil) | foil | 0.000 | {f['cold_crps']:.4f} | — | — | — | — | — |")
    for name, r in d["arms"].items():
        ok = "✅" if r["clauses"]["all_ok"] else "❌ " + ",".join(
            k.split("_")[0] for k, v in r["clauses"].items() if k.startswith("C") and not v["ok"])
        a(f"| `{name}` | {r['role']} | {r['mean_delta_pts']:.3f} | {r['cold_crps']:.4f} | "
          f"{r['gain_vs_foil_cold']:+.4f} | {r['fold_wins']}/{r['n_folds']} | "
          f"{_f(r['dsr'])} | {r['p_one_sided']:.4f} | {ok} |")
    a("")
    a(f"Foil cold-start bias **{f['cold_bias_pts']:+.3f} pts** (pooled {f['pooled_bias_pts']:+.3f}) "
      "— the quantity VAL2 measured and this study tries to remove.")
    a("")
    a("## 1b. Calibration — the AC's \"without degrading aggregate PIT\"")
    a("")
    a("| arm | wk1-3 bias | wk1-3 PIT | wk1-3 calib80 | pooled bias | **pooled PIT** | pooled calib80 |")
    a("|---|---|---|---|---|---|---|")
    fc = {cell: {k: float(np.mean([r[cell][k] for r in d["_foil_folds"] if r[cell]["n"]]))
                 for k in ("pit_max_decile_dev", "calib_80", "bias")}
          for cell in ("cold", "pooled")} if "_foil_folds" in d else None
    if fc:
        a(f"| `none` (foil) | {fc['cold']['bias']:+.3f} | {fc['cold']['pit_max_decile_dev']:.4f} | "
          f"{fc['cold']['calib_80']:.4f} | {fc['pooled']['bias']:+.3f} | "
          f"**{fc['pooled']['pit_max_decile_dev']:.4f}** | {fc['pooled']['calib_80']:.4f} |")
    for name, r in d["arms"].items():
        cb = r["calibration"]
        a(f"| `{name}` | {cb['cold']['bias']:+.3f} | {cb['cold']['pit_max_decile_dev']:.4f} | "
          f"{cb['cold']['calib_80']:.4f} | {cb['pooled']['bias']:+.3f} | "
          f"**{cb['pooled']['pit_max_decile_dev']:.4f}** | {cb['pooled']['calib_80']:.4f} |")
    a("")
    a(f"C1's tolerance is **+{PIT_DEGRADE_TOL}** on the pooled PIT max-decile-dev, and C2/C3 floor "
      f"`calib_80` at **{CALIB_FLOOR}** — a FLOOR, never a target (NF1.8/E2.1-r).")
    a("")
    a("## 2. The AC's headline — the wk1-3 over-tilt")
    a("")
    t = d["over_tilt"]
    if t.get("state") != "EVALUABLE":
        a(f"⚠️ **UNEVALUABLE** — {t.get('note')}")
    else:
        a(f"On the {t['n_close_carrying_cold']:,} close-carrying cold-start rows (over actually hit "
          f"**{t['over_actually_hit']:.3f}**). ⚠️ DESCRIPTIVE — the only market-touching number "
          "here, never a clause and never an edge claim.")
        a("")
        a("| arm | model → over | mean μ − close (pts) |")
        a("|---|---|---|")
        for name, v in t["arms"].items():
            a(f"| `{name}` | {v['model_to_over']:.3f} | {v['mean_offset_pts']:+.3f} |")
    a("")
    a("## 3. Gates")
    a("")
    g = d["deflation"]
    a(f"- **PBO** {g['pbo']:.4f} (gate < {g['pbo_gate']}) over {g['n_buckets']} buckets, "
      f"{g['n_cscv_combos']:,} CSCV combos — {'✅' if g['pbo_pass'] else '❌'}")
    a(f"- **DSR** gate ≥ {g['dsr_gate']}; `V` **binding (full field)** "
      f"{_f(g['var_trials_sr_binding'], 5)}, DSR-CONV variant "
      f"{_f(g['var_trials_sr_convention_variant'], 5)} (reported, NOT binding)")
    a(f"- **BH** α {g['bh_alpha']} → cutoff {g['bh_cutoff']:.5f}")
    fc = g["fold_consistency"]
    a(f"- **Fold consistency** (`cv_power.fold_consistency_clause`): {fc['required_wins']} of "
      f"{fc['n_folds']} wins required, attainable {fc['attainable']}, false-fire "
      f"{fc['attained_false_fire']:.4f} (legacy would ask {fc['legacy_required']} at "
      f"{fc['legacy_false_fire']:.4f})")
    c = d["pbo_companions"]
    a(f"- **PBO companions** — CANDIDATE spread {c['contender_spread_crps']:.4f} CRPS "
      f"({c['contender_spread_pct_of_foil']:.2f} % of the foil); whole-field spread "
      f"{c['whole_field_spread_crps']:.4f} (NF1.8: a spread over a field containing its own "
      f"pre-registered nulls measures the NULLS); flip distribution {c['fold_flip_distribution']}")
    a("")
    a("**PBO sensitivity** — the pre-registered population BINDS; the rest are labelled "
      "diagnostics proving the null does not rest on the gate choice (NF-D15 g″). ⛔ None of "
      "them may be adopted after the fact (MH2.2 / E2.1-r).")
    a("")
    a("| population | arms | PBO | binds |")
    a("|---|---|---|---|")
    for k, vv in d["pbo_sensitivity"].items():
        a(f"| `{k}` — {vv['note']} | {vv['n_arms']} | **{vv['pbo']:.4f}** | "
          f"{'✅ BINDING' if vv['binds'] else 'diagnostic'} |")
    a("")
    a("## 4. Anchors")
    a("")
    an = d["anchors"]
    a(f"- headline bucket peek CRPS **{an['headline_bucket_oracle_crps_cold']:.4f}** vs its "
      f"matched-n control **{an['headline_matched_n_crps_cold']:.4f}** ⇒ peek gain "
      f"{an['headline_peek_gain']:+.4f}, pair "
      f"**{'ACTIVE' if an['headline_pair_active'] else 'INACTIVE'}**")
    a(f"- {an['reading']}")
    a("")
    a("| arm | form | own-form peek | its matched-n | peek gain | pair | arm − peek | C8 state |")
    a("|---|---|---|---|---|---|---|---|")
    for name, v in an["per_form_oracle"].items():
        a(f"| `{name}` | `{v['form']}` | {v['peek_crps']:.4f} | {v['matched_n_crps']:.4f} | "
          f"{v['peek_gain_over_matched_n']:+.4f} | "
          f"{'ACTIVE' if v['anchor_pair_active'] else 'INACTIVE'} | {v['gap']:+.4f} | "
          f"{v['state']} |")
    a("")
    a("## 4b. Channel attribution — paired, never a rank (NF-D10 / NF-D15 g′)")
    a("")
    ch = d["channel_attribution"]
    a("| channel | pair | cell | mean gain | folds + | p |")
    a("|---|---|---|---|---|---|")
    for k in ("magnitude_channel", "scoping_channel"):
        c = ch[k]
        a(f"| {k.replace('_channel','')} | `{c['pair']}` | {c['cell']} | {c['mean_gain']:+.4f} | "
          f"{c['folds_positive']}/{c['n_folds']} | {c['p_one_sided']:.4f} |")
    a("")
    a(f"_{ch['why_two_cells']}_")
    a("")
    ic = d["crps_instrument_control"]
    gaps = "  →  ".join(f"{n} draws {g:.5f}" for n, g in ic["max_abs_gap_by_draws"].items())
    a(f"**Instrument control** — closed-form vs ensemble CRPS on the foil: {gaps} "
      f"({ic['gap_pct_of_crps']:.3f} % of the CRPS; shrinks with draws: "
      f"{'✅' if ic['gap_shrinks_with_draws'] else '❌'}). {ic['reading']}")
    a("")
    if d["null_classification"]:
        n = d["null_classification"]
        a("## 5. The null, classified")
        a("")
        a(f"- best candidate **`{n['best_candidate']}`**")
        a(f"- `cv_power.classify_null` state **`{n['instrument_state']}`** — {n['instrument_reason']}")
        a(f"- **recorded state `{n['recorded_state']}`** (binding half: {n['binding_half']}"
          + (f"; clauses failed: {', '.join(n['constraint_clauses_failed'])}"
             if n["constraint_clauses_failed"] else "") + ")")
        a(f"- {n['why_recorded_state']}")
        if n["recorded_state"] == "CONSTRAINT_REFUSED":
            a("- ⛔ **No fold/season re-test trigger is published** — no fold count moves a clause "
              f"(NF-D18). The instrument's own trigger, preserved for the record: "
              f"`{n['instrument_retest_trigger']}`")
        else:
            a(f"- re-test trigger: `{n['instrument_retest_trigger']}`")
        a(f"- `field_remedy_admissible` = `{n['field_remedy_admissible']}` "
          f"(declared field {d['declared_field_size']}; MH2.7 — read the FLAG, not the prose)")
        if n.get("deflation_gates_failed"):
            a(f"- **deflation gates failed: {', '.join(n['deflation_gates_failed'])}**")
        a(f"- {n['meaningful_effect_not_preregistered']}")
    a("")
    a("## 6. Reproduction pin")
    a("")
    p = d["reproduction_pin"]
    a(f"Anchored on the PARENT (`{p['source']}`) and the cache meta — ⛔ never on VAL3's own output. "
      f"All legs {'PASS ✅' if p['all_ok'] else 'FAIL ❌'}.")
    a("")
    a("| leg | got | expected | ok |")
    a("|---|---|---|---|")
    for k, v in p["checks"].items():
        a(f"| `{k}` | {v['got']} | {v['expected']} | {'✅' if v['ok'] else '❌'} |")
    a("")
    a("_Vintage-bound on purpose: a re-assemble moves the population and this pin HALTs. The remedy "
      "is to re-run the parent and re-anchor from ITS output._")
    return "\n".join(A) + "\n"


def report(d: dict) -> None:
    f = d["foil"]
    print(f"\n=== {_STORY} — verdict {d['verdict']} ===")
    print(f"  foil `none`: CRPS wk1-3 {f['cold_crps']:.4f}  bias {f['cold_bias_pts']:+.3f} pts "
          f"(pooled bias {f['pooled_bias_pts']:+.3f})")
    print(f"\n  {'arm':<18}{'role':<11}{'δ̄':>7}{'CRPS':>10}{'gain':>9}{'wins':>6}{'DSR':>7}"
          f"{'p':>8}  clauses")
    for name, r in d["arms"].items():
        bad = [k.split("_")[0] for k, v in r["clauses"].items()
               if k.startswith("C") and not v["ok"]]
        print(f"  {name:<18}{r['role']:<11}{r['mean_delta_pts']:>7.3f}{r['cold_crps']:>10.4f}"
              f"{r['gain_vs_foil_cold']:>+9.4f}{r['fold_wins']:>4}/{r['n_folds']}"
              f"{_f(r['dsr']):>7}{r['p_one_sided']:>8.4f}  "
              f"{'✅' if not bad else '❌ ' + ','.join(bad)}")
    g = d["deflation"]
    ps = d["pbo_sensitivity"]
    print("\n  PBO sensitivity: " + "  ".join(
        f"{k}={v['pbo']:.3f}{'*' if v['binds'] else ''}" for k, v in ps.items())
        + "   (* = the pre-registered BINDING population)")
    print(f"  PBO {g['pbo']:.4f} (gate <{g['pbo_gate']}, {g['n_buckets']} buckets)  |  "
          f"BH cut {g['bh_cutoff']:.5f}  |  V(binding) {_f(g['var_trials_sr_binding'], 5)}  |  "
          f"fold-consistency needs {g['fold_consistency']['required_wins']}/"
          f"{g['fold_consistency']['n_folds']}")
    an = d["anchors"]
    print(f"  headline peek {an['headline_bucket_oracle_crps_cold']:.4f} vs matched-n "
          f"{an['headline_matched_n_crps_cold']:.4f} ⇒ pair "
          f"{'ACTIVE' if an['headline_pair_active'] else 'INACTIVE'} "
          f"(gain {an['headline_peek_gain']:+.4f})")
    print(f"  {'per-form C8':<18}{'form':<12}{'peek':>9}{'matched-n':>11}{'pair':>10}{'state':>10}")
    for name, v in an["per_form_oracle"].items():
        print(f"  {name:<18}{v['form']:<12}{v['peek_crps']:>9.4f}{v['matched_n_crps']:>11.4f}"
              f"{('ACTIVE' if v['anchor_pair_active'] else 'INACTIVE'):>10}{v['state']:>10}")
    ch = d["channel_attribution"]
    print(f"\n  ── channel attribution (paired) ──")
    for k in ("magnitude_channel", "scoping_channel"):
        c = ch[k]
        print(f"    {k.replace('_channel',''):<10} {c['pair']:<32} on {c['cell']:<16} "
              f"{c['mean_gain']:+.4f}  {c['folds_positive']}/{c['n_folds']}  p={c['p_one_sided']:.4f}")
    ic = d["crps_instrument_control"]
    print("  CRPS instrument control (closed form vs ensemble): "
          + ", ".join(f"{n}dr {g:.5f}" for n, g in ic["max_abs_gap_by_draws"].items())
          + f"  shrinks {'✅' if ic['gap_shrinks_with_draws'] else '❌'}")
    t = d["over_tilt"]
    if t.get("state") != "EVALUABLE":
        print(f"\n  ── wk1-3 over-tilt: UNEVALUABLE — {t.get('note')}")
    else:
        print(f"\n  ── wk1-3 over-tilt (DESCRIPTIVE; n={t['n_close_carrying_cold']:,}, "
              f"over actually hit {t['over_actually_hit']:.3f}) ──")
        for name, v in t["arms"].items():
            print(f"    {name:<18} model→over {v['model_to_over']:.3f}   mean μ−close "
                  f"{v['mean_offset_pts']:+.3f}")
    if d["null_classification"]:
        n = d["null_classification"]
        print(f"\n  null: best candidate `{n['best_candidate']}` → instrument "
              f"`{n['instrument_state']}` / recorded `{n['recorded_state']}` "
              f"(binding half: {n['binding_half']})")
        if n["constraint_clauses_failed"]:
            print(f"    clauses failed: {', '.join(n['constraint_clauses_failed'])}")
        if n.get("deflation_gates_failed"):
            print(f"    deflation gates failed: {', '.join(n['deflation_gates_failed'])}")
        print(f"    instrument says: {n['instrument_reason']}")
    print(f"\n  → {_OUT_JSON.relative_to(B._PROJECT_ROOT)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=f"{_STORY} — cold-start μ_total correction")
    ap.add_argument("--stage", choices=["score", "decide", "all"], default="all")
    ap.add_argument("--seed", type=int, default=B._SEED)
    ap.add_argument("--n-draws", type=int, default=5_000,
                    help="draws for the CRPS instrument control ONLY; the scored CRPS is closed-form")
    ap.add_argument("--max-folds", type=int, default=None)
    ap.add_argument("--allow-pin-fail", action="store_true",
                    help="⚠️ proceed past a §6 reproduction-pin HALT (diagnostics only).")
    args = ap.parse_args(argv)
    if args.stage in ("score", "all"):
        stage_score(args)
    if args.stage in ("decide", "all"):
        report(stage_decide(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
