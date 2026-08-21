"""ncaaf_val2_mu_total_offset.py — NCAAF-VAL2: the μ_total − close_total offset, decomposed.

NCAAF-VAL1 recorded that the served model takes the OVER on ~58.5 % of games while the close is
median-unbiased (over hits ~49.8 %), and called that a "directional totals tilt". But VAL1 only ever
computed **P(over)** — a SIDE statistic. A side split says *which way* the model leans; it cannot say
*by how much*, and it cannot say *whose* fault the lean is. This module measures the LEVEL directly
and splits it into its two attributable halves:

    μ_total − close_total   =   (μ_total − y_total)   +   (y_total − close_total)
    ── the offset ──            ── OUR model's ──         ── the close vs the ──
                                   mean error               realised total

That identity is the whole point. The two terms can (and in the cold-start weeks do) point in
OPPOSITE directions, so the offset SYSTEMATICALLY UNDERSTATES the half a μ-recalibration could
actually repair. Deciding VAL3 off the offset alone would size the repair against the wrong number.

⛔ **This module CHANGES NOTHING.** Query-only over the existing P1.4 cache: no refit of the served
artifacts, no serving write, no registry edit, no bet. `best_alpha = 0` before and after. It is
*market-blind* in the sense the vertical uses (the model never sees a market feature — re-asserted
here, not assumed) and it makes **no edge claim**: "our μ sits above the close" is a statement about
our own calibration, never about what the market is worth.

⭐ **Why this read is immune to the defect it uncovers (§ the alignment control).** P1.4's
`_clv_eval` and VAL1's `score_config` both select their close-carrying rows with
`df[mask].reset_index(drop=True)` and then index the (n_games, n_draws) predictive array with the
RESET index `0..n−1`. That is not a recovery of the original row positions — it reads the FIRST n
rows of the draw array, i.e. a different game's predictive distribution. This module never indexes
the draw array at all: it joins on `game_id` and reads each row's own `mu_total`. The alignment
control below proves both halves of that claim on live data and HALTS if it cannot.

  uv run python -m quant_sports_intel_models.football.ncaaf.models.ncaaf_val2_mu_total_offset
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_game as B
from quant_sports_intel_models.football.ncaaf.models import ncaaf_val1_clv_week_strat as V
from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_distribution import (
    JointDispersion, derive_markets, draw_joint, fit_gaussian_dispersion,
    fit_strength_posterior_scale, strength_posterior_sigma,
)
from quant_sports_intel_models.football.ncaaf.models.p2_1_blocks import derive_pace_composites

_STORY = "NCAAF-VAL2"
_RESULTS = Path(B._RESULTS_DIR)
_OUT_JSON = _RESULTS / "ncaaf_val2_mu_total_offset.json"
_OUT_MD = _RESULTS / "ncaaf_val2_mu_total_offset.md"

#: The SERVED config, imported from VAL1 rather than restated — a second literal here could drift
#: away from the config VAL1/S1-serve actually scored and nothing would fail.
SERVED = V.PRIMARY
BUCKETS = V.BUCKETS
WEEK_COL = V.WEEK_COL          # ⛔ `season_order_week`, never raw `week` (the P1.1 postseason restart)

#: The three decomposition terms. `offset` is the quantity the story asks for; the other two are the
#: halves it decomposes into, and their names say WHOSE error each one is.
TERMS: tuple[tuple[str, str], ...] = (
    ("offset", "mu_total - close_total"),
    ("model_err", "mu_total - y_total     (OUR mean error)"),
    ("close_err", "y_total  - close_total (close vs realised)"),
)

#: §AC — the materiality band, stated FORWARD (it is the story's own acceptance criterion, written
#: before a single cell was computed): a real, consistent offset of ~1 point or more hands to VAL3.
#: ⛔ It is never re-derived from an observed value (the E2.1-r inversion).
MATERIAL_PTS = 1.0
POWER = 0.80
ALPHA = 0.05

#: The alignment control's two-sided bar. The served form (`strength_posterior`) is a heteroscedastic
#: **Gaussian**, so its median IS `mu_total` ⇒ `P(over) >= 0.5` and `mu_total > close_total` are the
#: SAME event up to Monte-Carlo noise on P(over). At 4,000 draws the MC SE of P(over) is ~0.0079, so
#: a side can only flip inside |offset| < ~0.33 pts — a thin band that ~2 % of rows occupy. A
#: correctly-aligned read must therefore agree with the direct μ sign on ~98 % of rows.
SIGN_AGREEMENT_FLOOR = 0.97
#: …and a MISaligned read must be materially worse, or the control cannot discriminate and is
#: vacuous (NF1.7 (a)): a check that passes whatever the code does has not checked anything.
MISALIGNED_CEILING = 0.90

#: VAL1's recorded population + side statistics, for PROVENANCE (reported, never a silent pass).
VAL1_RECORDED = {"n_with_close": 4187, "ou_side_frac": 0.585006, "ou_always_over": 0.498186,
                 "ou_hit": 0.5137, "ats_hit": 0.509, "cache_assembled_at": "2026-08-20"}


# ── cache vintage ───────────────────────────────────────────────────────────────────────────

def ensure_pace_composites(df: pd.DataFrame, feat: list[str]) -> tuple[pd.DataFrame, list[str], dict]:
    """Return the frame with the served pace composites present, plus a PROVENANCE record.

    A cache assembled before NCAAF-P2.1-S1-serve carries the pace SOURCE columns but not the two
    derived composites, so the served `strength_pace` contract cannot resolve on it. The derivation
    is the SAME shared function `assemble_cache` calls, over columns already in the frame — it is a
    deterministic local transform, NOT a data pull. It is done loudly and recorded, because a
    silently-repaired cache is a silently-different population.
    """
    if all(c in df.columns for c in ("pace_sum", "pace_diff")):
        return df, feat, {"pace_derived_in_session": False}
    out = derive_pace_composites(df)                      # RAISES if the source columns are absent
    feat2 = B.feature_columns(out)
    B.assert_market_blind(feat2, context=f"{_STORY} pace-repaired cache")
    return out, feat2, {
        "pace_derived_in_session": True,
        "n_features_before": len(feat), "n_features_after": len(feat2),
        "pace_non_null": int(out["pace_sum"].notna().sum()), "n_rows": int(len(out)),
        "note": ("the on-disk cache predates NCAAF-P2.1-S1-serve; the two served pace composites "
                 "were derived in-session by the SAME shared `derive_pace_composites` the assemble "
                 "path calls, from columns already present. No data pull."),
    }


def cache_provenance(df: pd.DataFrame, meta: dict) -> dict[str, Any]:
    """Compare THIS cache's population against the one VAL1 scored — reported, never silent.

    ⚠️ A mismatch is NOT fatal to this story's structural findings (the alignment defect is a
    property of the SOURCE, and the decomposition identity is arithmetic), but the offset LEVEL is a
    property of the population, so a vintage gap must be visible in the artifact rather than
    inferable from it."""
    n_close = int(df["has_close"].sum())
    matches = n_close == VAL1_RECORDED["n_with_close"]
    return {
        "assembled_at": meta.get("assembled_at"), "n_games": int(len(df)), "n_with_close": n_close,
        "val1_n_with_close": VAL1_RECORDED["n_with_close"],
        "matches_val1_population": bool(matches),
        "delta_games": n_close - VAL1_RECORDED["n_with_close"],
        "note": ("population reproduces VAL1" if matches else
                 f"⚠️ this cache carries {n_close:,} closes vs the {VAL1_RECORDED['n_with_close']:,} "
                 f"VAL1/P2.1/S1-serve recorded. The offset LEVEL is vintage-dependent; re-run "
                 f"`bakeoff_ncaaf_game.py --assemble` and re-run this module to quote it against the "
                 f"recorded vintage. The alignment finding and the decomposition identity do not "
                 f"depend on the population."),
    }


# ── the offset frame ────────────────────────────────────────────────────────────────────────

@dataclass
class Offset:
    frame: pd.DataFrame          # one row per close-carrying OOS game
    oos: pd.DataFrame            # the full OOS frame (all eval years)
    sigma_total: float           # the OOS-residual σ the offset is expressed in
    sigma_margin: float
    rho: float


def build_offset_frame(df: pd.DataFrame, feat: list[str], *, seed: int,
                       max_folds: int | None = None) -> Offset:
    """Collect the served OOS predictions and join them to the close BY `game_id`.

    ⭐ The join key is load-bearing. Every quantity here is read off the row's OWN `mu_total`; no
    positional index into a draw array is taken anywhere in this module, which is precisely why this
    read is unaffected by the `_clv_eval` misalignment the control below demonstrates."""
    folds = V._folds(df, feat, max_folds)
    oos = B._collect_oos(folds, SERVED["mc"], SERVED["contract"], SERVED["form"],
                         top_k=B._DEFAULT_TOP_K, seed=seed)
    rm = (oos["y_margin"] - oos["mu_margin"]).to_numpy()
    rt = (oos["y_total"] - oos["mu_total"]).to_numpy()
    g = fit_gaussian_dispersion(rm, rt)

    close = df[["game_id", "close_total", "close_home_spread", "has_close"]].drop_duplicates("game_id")
    merged = oos.merge(close, on="game_id", how="left")
    if len(merged) != len(oos):
        raise SystemExit(f"[{_STORY}] the close join changed the row count "
                         f"({len(oos):,} → {len(merged):,}); a duplicated close key would silently "
                         "re-weight every mean below.")
    m = merged[merged["has_close"] == True].reset_index(drop=True)      # noqa: E712
    if m["close_total"].isna().any():
        raise SystemExit(f"[{_STORY}] {int(m['close_total'].isna().sum())} rows are flagged "
                         "`has_close` with a NULL `close_total`; refusing to average over a NaN.")

    m["offset"] = m["mu_total"] - m["close_total"]
    m["model_err"] = m["mu_total"] - m["y_total"]
    m["close_err"] = m["y_total"] - m["close_total"]
    m["is_push"] = m["y_total"] == m["close_total"]
    m["bucket"] = V.bucket_of(m[WEEK_COL].to_numpy())
    resid = np.abs((m["model_err"] + m["close_err"] - m["offset"]).to_numpy()).max()
    if resid > 1e-9:
        raise SystemExit(f"[{_STORY}] the decomposition identity does not hold (max |resid| "
                         f"{resid:.3e}); the two halves do not sum to the offset.")
    return Offset(frame=m, oos=oos, sigma_total=float(g.sigma_total),
                  sigma_margin=float(g.sigma_margin), rho=float(g.rho))


# ── the alignment control ───────────────────────────────────────────────────────────────────

def alignment_control(off: Offset, *, seed: int, n_draws: int) -> dict[str, Any]:
    """Two-sided proof that (a) our μ IS the served predictive's centre and (b) `_clv_eval` is not.

    Draws the served joint exactly as `score_config` does, then reads P(over) TWICE — once with the
    as-coded reset index `0..n−1` and once with the TRUE positions of the close-carrying rows — and
    compares each against `sign(mu_total − close_total)`.

    Both directions are asserted. The repaired leg is the POSITIVE control (our μ is the same
    quantity the draws are centred on); the as-coded leg is the NEGATIVE control (a check that
    cannot tell the broken code from the fixed code has proven nothing — NF1.7 (a))."""
    oos = off.oos
    rm = (oos["y_margin"] - oos["mu_margin"]).to_numpy()
    rt = (oos["y_total"] - oos["mu_total"]).to_numpy()
    g = fit_gaussian_dispersion(rm, rt)
    disp = JointDispersion(sigma_margin=g.sigma_margin, sigma_total=g.sigma_total, rho=g.rho)
    sv = oos["strength_var"].to_numpy(float)
    disp.sigma0_margin, disp.k_margin = fit_strength_posterior_scale(rm, sv)
    disp.sigma0_total, disp.k_total = fit_strength_posterior_scale(rt, sv)
    sig_m = strength_posterior_sigma(disp.sigma0_margin, disp.k_margin, sv)
    sig_t = strength_posterior_sigma(disp.sigma0_total, disp.k_total, sv)
    rng = np.random.default_rng(seed)
    m_s, t_s = draw_joint(SERVED["form"], oos["mu_margin"].to_numpy(), oos["mu_total"].to_numpy(),
                          disp, rng, n_draws=n_draws,
                          sigma_margin_native=sig_m, sigma_total_native=sig_t)
    dists = derive_markets(m_s, t_s)

    f = off.frame
    tot = f["close_total"].to_numpy()
    direct = f["mu_total"].to_numpy() > tot                 # the sign of the offset
    # the two candidate index vectors, exactly as the two code paths form them
    as_coded = f.index.to_numpy()                            # `_clv_eval` / `score_config`
    true_pos = np.flatnonzero(off.oos["game_id"].isin(f["game_id"]).to_numpy())
    if len(true_pos) != len(f):
        raise SystemExit(f"[{_STORY}] cannot recover the true draw-array positions "
                         f"({len(true_pos)} vs {len(f)} rows); the alignment control cannot run, "
                         "and an unevaluable control is never a pass.")

    y_t = f["y_total"].to_numpy()
    over_hit, push = y_t > tot, y_t == tot

    def read(idx: np.ndarray) -> dict[str, Any]:
        """Agreement with the direct μ sign, PLUS the O/U hit rate VAL1 records off this index.

        The hit rates are what make §2's impact table reproducible from committed code rather than
        from a throwaway script — a claim in a writeup that cannot be regenerated is the first thing
        to rot."""
        p_over = (dists["total"][idx] > tot[:, None]).mean(axis=1)
        side = p_over >= 0.5
        win = np.where(side, over_hit, ~over_hit)
        out = {"agreement": float(np.mean(side == direct)),
               "ou_n": int((~push).sum()), "ou_hit": float(win[~push].mean()),
               "ou_side_frac_over": float(side[~push].mean()), "by_bucket": {}}
        for name, _lo, _hi in BUCKETS:
            k = (f["bucket"].to_numpy() == name) & ~push
            out["by_bucket"][name] = {"n": int(k.sum()), "ou_hit": float(win[k].mean()),
                                      "side_frac_over": float(side[k].mean())}
        return out

    r_rep, r_cod = read(true_pos), read(as_coded)
    rep, cod = r_rep["agreement"], r_cod["agreement"]
    out = {
        "n_rows": int(len(f)), "n_draws": int(n_draws),
        "repaired_agreement": rep, "as_coded_agreement": cod,
        "repaired_read": r_rep, "as_coded_read": r_cod,
        "val1_recorded_ou_hit": VAL1_RECORDED["ou_hit"],
        "val1_recorded_ou_side_frac": VAL1_RECORDED["ou_side_frac"],
        "floor": SIGN_AGREEMENT_FLOOR, "misaligned_ceiling": MISALIGNED_CEILING,
        "index_identical": bool(np.array_equal(as_coded, true_pos)),
        "rows_misindexed_frac": float(np.mean(as_coded != true_pos)),
        "mc_flip_band_pts": float(stats.norm.ppf(0.5 + 1.0 / np.sqrt(4.0 * n_draws))
                                  * off.sigma_total),
        "positive_control_ok": bool(rep >= SIGN_AGREEMENT_FLOOR),
        "negative_control_ok": bool(cod <= MISALIGNED_CEILING),
    }
    if not out["positive_control_ok"]:
        raise SystemExit(
            f"[{_STORY}] ⛔ HALT — the correctly-aligned drawn side agrees with sign(μ − close) on "
            f"only {rep:.4f} of rows (floor {SIGN_AGREEMENT_FLOOR}). `mu_total` is then NOT the "
            "centre of the served predictive, and every offset below would be measuring some other "
            "quantity. Refusing to report a level off an unvalidated μ.")
    if not out["negative_control_ok"]:
        raise SystemExit(
            f"[{_STORY}] ⛔ HALT — the AS-CODED index agrees on {cod:.4f} of rows, at or above the "
            f"{MISALIGNED_CEILING} discriminating ceiling. This control reconstructs the as-coded "
            "index LOCALLY, so a high agreement does not mean the upstream defect was fixed — it "
            "means the close-carrying rows now sit at the FRONT of the OOS frame, where "
            "`arange(n)` happens to coincide with their true positions. The control can then no "
            "longer distinguish a positional read from a joined one, and a control that passes "
            "either way has checked nothing (NF1.7 (a)).")
    return out


# ── statistics ──────────────────────────────────────────────────────────────────────────────

def term_stats(v: np.ndarray, cluster: np.ndarray) -> dict[str, Any]:
    """Pooled level for one term, with BOTH the naive and the season-CLUSTERED standard error.

    ⭐ The clustered one binds. Games inside a season are not independent draws of the model's level
    error — a season shares one fitted strength surface, one scoring environment and one training
    window — so the naive `sd/√n` understates the uncertainty of a LEVEL by roughly the square root
    of the cluster size (NF1.8's per-group rule). It is reported beside the naive figure rather than
    instead of it, so the gap is visible.

    The season SIGN TEST is reported too and is the more robust of the two: at k = 6 clusters a
    t-statistic rests on a variance estimated from 6 points, while the sign test rests on none."""
    v = np.asarray(v, float)
    per = pd.DataFrame({"v": v, "c": cluster}).groupby("c")["v"].mean()
    k = int(len(per))
    naive_se = float(v.std(ddof=1) / np.sqrt(len(v)))
    cm = float(per.mean())
    cse = float(per.std(ddof=1) / np.sqrt(k)) if k > 1 else float("nan")
    df_ = max(k - 1, 1)
    # MDE for the CLUSTERED design, from k and the observed cluster dispersion — a design quantity,
    # so a term whose |mean| sits below it is UNRESOLVABLE by this design rather than "absent".
    mde = float((stats.t.ppf(1 - ALPHA / 2, df_) + stats.t.ppf(POWER, df_)) * cse) if k > 1 else float("nan")
    n_pos = int((per > 0).sum())
    sign_p = float(stats.binomtest(max(n_pos, k - n_pos), k, 0.5).pvalue)
    half = float(stats.t.ppf(1 - ALPHA / 2, df_) * cse) if k > 1 else float("nan")
    lo, hi = cm - half, cm + half
    return {
        "n": int(len(v)), "mean": float(v.mean()), "median": float(np.median(v)),
        "sd": float(v.std(ddof=1)), "naive_se": naive_se,
        "q25": float(np.percentile(v, 25)), "q75": float(np.percentile(v, 75)),
        "frac_positive": float(np.mean(v > 0)),
        "n_clusters": k, "cluster_mean": cm, "cluster_se": cse,
        "cluster_t": float(cm / cse) if cse and np.isfinite(cse) and cse > 0 else None,
        "cluster_t_crit": float(stats.t.ppf(1 - ALPHA / 2, df_)),
        "mde_clustered_pts": mde,
        # ⭐ TWO readings, reported side by side because they answer DIFFERENT questions and this
        # study is a post-data band decision, where they can disagree:
        #   `resolvable`  — |mean| >= MDE: would this DESIGN reliably (80 % power) find an effect
        #                   this size?  A PRE-data question about the design.
        #   `demonstrated`— does the clustered CI exclude zero?  A POST-data question about what
        #                   was actually found. An effect can be demonstrated while sitting below
        #                   the 80 %-power MDE — significance and power are different bars.
        # NF-W7i (recorded before this story): a band/materiality decision consults the INTERVAL;
        # reporting it as merely under-powered when the interval already answers the question is
        # the actively-misleading direction. So `demonstrated` binds and `resolvable` is reported.
        "resolvable": bool(np.isfinite(mde) and abs(cm) >= mde),
        "ci_lo": lo, "ci_hi": hi, "ci_alpha": ALPHA,
        "demonstrated": bool(np.isfinite(lo) and (lo > 0 or hi < 0)),
        "band_pts": MATERIAL_PTS,
        "band_decisive_above": bool(np.isfinite(lo) and lo >= MATERIAL_PTS),
        "band_decisive_below": bool(np.isfinite(hi) and hi < MATERIAL_PTS),
        "seasons_positive": n_pos, "sign_test_p": sign_p,
        "per_cluster": {str(i): round(float(x), 4) for i, x in per.items()},
    }


def summarise(frame: pd.DataFrame, sigma_total: float) -> dict[str, Any]:
    """All three terms on one row-set, plus the σ-normalised and P(over) readings."""
    out: dict[str, Any] = {"n": int(len(frame)), "n_push": int(frame["is_push"].sum())}
    for name, _desc in TERMS:
        s = term_stats(frame[name].to_numpy(), frame["season"].to_numpy())
        s["mean_sigma_units"] = s["mean"] / sigma_total
        # the decision-relevant unit: how far a level shift of this size moves P(over) AT the line,
        # for a Normal predictive (dP/dμ = φ(0)/σ). Reported in percentage points.
        s["p_over_pp"] = 100.0 * stats.norm.pdf(0) / sigma_total * s["mean"]
        out[name] = s
    tot = out["offset"]["mean"]
    out["shares"] = {
        "model_share": (out["model_err"]["mean"] / tot) if abs(tot) > 1e-12 else None,
        "close_share": (out["close_err"]["mean"] / tot) if abs(tot) > 1e-12 else None,
    }
    return out


def close_unit_reading(frame: pd.DataFrame) -> dict[str, Any]:
    """Is the close a MEDIAN line or a MEAN line? — the reading that decides how much of the offset
    a μ-recalibration is even *allowed* to remove.

    Our μ is a conditional MEAN. If the market's number is effectively a conditional MEDIAN and the
    total is right-skewed, then μ sits above the close by the mean−median gap **with no model defect
    at all**, and shifting μ down to close that part would make our μ a WORSE conditional mean. So
    this is not a market claim; it is a unit check on our own quantity (the E2.1-r class: a metric
    that rewards moving toward the wrong target).

    ⚠️ Scope, inherited verbatim from VAL1: the strictly-market reading of `y − close` is NOT a claim
    this study supports. It is reported as the second half of an arithmetic identity."""
    yc = frame["close_err"].to_numpy()
    nonpush = ~frame["is_push"].to_numpy()
    n, w = int(nonpush.sum()), int((yc[nonpush] > 0).sum())
    y = frame["y_total"].to_numpy(float)
    return {
        "p_realised_over_close_nonpush": w / n, "n_nonpush": n,
        "exact_two_sided_p_vs_50": float(stats.binomtest(w, n, 0.5).pvalue),
        "median_close_err": float(np.median(yc)), "mean_close_err": float(yc.mean()),
        "realised_total_mean": float(y.mean()), "realised_total_median": float(np.median(y)),
        "realised_total_skew": float(stats.skew(y)),
        "mean_minus_median_pts": float(y.mean() - np.median(y)),
        "val1_recorded_always_over": VAL1_RECORDED["ou_always_over"],
    }


def sign_stability_controls(frame: pd.DataFrame, *, seed: int, n_perm: int = 2000) -> dict[str, Any]:
    """Three controls on the season-level statistics the verdict leans on. All are two-sided.

    NEGATIVE (season permutation): shuffle each game's season label inside the cell. This asks
    whether the SEASON STRUCTURE is what produces the sign stability. ⚠️ It is expected to come back
    LARGE here and that is not a failure — it is the finding: with a cell mean well above the
    within-season noise, a shuffled field reproduces "positive in every season" most of the time, so
    **the sign test adds no evidence beyond the level** and must not be quoted as if it did (the
    NF1.8 rule that a statistic a degenerate wins cannot select). The clustered MDE, which is a
    design quantity, is what actually discriminates.

    POSITIVE (injection at the MDE): add a known level that the design SHOULD resolve and confirm it
    is found. ⭐ The series is re-centred on its CLUSTER mean, not its pooled mean, because
    `resolvable` reads the cluster mean — centring on the wrong one injects a different level than
    the label claims and makes a working control report a failure.

    NEGATIVE (injection below the MDE): a level the design should NOT resolve must come back
    undetected, or the positive control is just an instrument that always says yes."""
    rng = np.random.default_rng(seed)
    sub = frame[frame["bucket"] == "wk1-3"]
    v, c = sub["model_err"].to_numpy(), sub["season"].to_numpy()
    k = int(len(np.unique(c)))
    base = term_stats(v, c)
    obs, mde = base["seasons_positive"], base["mde_clustered_pts"]
    hits = 0
    for _ in range(n_perm):
        p_ = term_stats(v, rng.permutation(c))["seasons_positive"]
        hits += int(max(p_, k - p_) >= max(obs, k - obs))
    centred = v - base["cluster_mean"]                     # cluster-mean-centred: a true zero level
    big = term_stats(centred + 1.5 * mde, c)               # comfortably above the design's MDE
    small = term_stats(centred + 0.4 * mde, c)             # comfortably below it
    null = term_stats(centred, c)
    return {
        "cell": "wk1-3 / model_err", "n_clusters": k, "observed_seasons_positive": obs,
        "mde_pts": mde,
        "permutation_p": hits / n_perm, "n_perm": n_perm,
        "permutation_reading": ("the sign test is confounded with the LEVEL at this dispersion — it "
                                "adds no evidence beyond it and is reported, not relied on"),
        "injection_above_mde_pts": 1.5 * mde, "injection_above_mde_detected": bool(big["resolvable"]),
        "injection_below_mde_pts": 0.4 * mde, "injection_below_mde_detected": bool(small["resolvable"]),
        "centred_null_detected": bool(null["resolvable"]),
        "discriminates": bool(big["resolvable"] and not small["resolvable"]
                              and not null["resolvable"]),
    }


def cold_start_contrast(frame: pd.DataFrame) -> dict[str, Any]:
    """The MATCHED contrast: is `wk1-3` model error genuinely a COLD-START effect, or just the
    pooled level showing up in the first bucket too?

    A per-bucket read cannot tell those apart — a season-wide level bias is positive in `wk1-3` as
    well. The question VAL3 actually needs answered is whether a WEEK-INDEXED correction has
    anything to correct, so the statistic is the matched difference

        Δ_season  =  mean(model_err | wk1-3, season)  −  mean(model_err | wk4+, season)

    paired WITHIN season (NF-D10: register the with/without pair and read the PAIRED delta; a
    bucket's rank in a table cannot separate "my mechanism is inert" from "my mechanism is a level")
    and then averaged over seasons, so any season-wide level cancels exactly."""
    early = frame[frame["bucket"] == "wk1-3"]
    late = frame[frame["bucket"] != "wk1-3"]
    e = early.groupby("season")["model_err"].mean()
    l = late.groupby("season")["model_err"].mean()
    common = sorted(set(e.index) & set(l.index))
    if len(common) < 2:
        raise SystemExit(f"[{_STORY}] only {len(common)} season(s) carry BOTH an early and a late "
                         "cell; the matched cold-start contrast cannot be formed, and an "
                         "unevaluable contrast is never a pass.")
    d = np.array([e[s] - l[s] for s in common], float)
    k = len(d)
    se = float(d.std(ddof=1) / np.sqrt(k))
    df_ = k - 1
    mde = float((stats.t.ppf(1 - ALPHA / 2, df_) + stats.t.ppf(POWER, df_)) * se)
    n_pos = int((d > 0).sum())
    half = float(stats.t.ppf(1 - ALPHA / 2, df_) * se)
    lo, hi = float(d.mean() - half), float(d.mean() + half)
    return {
        "seasons": [int(s) for s in common], "per_season_delta": [round(float(x), 4) for x in d],
        "mean_delta_pts": float(d.mean()), "se": se, "t": float(d.mean() / se) if se > 0 else None,
        "t_crit": float(stats.t.ppf(1 - ALPHA / 2, df_)), "mde_pts": mde,
        "seasons_positive": n_pos, "n_seasons": k,
        "sign_test_p": float(stats.binomtest(max(n_pos, k - n_pos), k, 0.5).pvalue),
        "resolvable": bool(abs(d.mean()) >= mde),
        "ci_lo": lo, "ci_hi": hi, "demonstrated": bool(lo > 0 or hi < 0),
        "band_decisive_above": bool(lo >= MATERIAL_PTS),
        "band_decisive_below": bool(hi < MATERIAL_PTS),
        "material": bool(abs(d.mean()) >= MATERIAL_PTS),
        "early_mean": float(early["model_err"].mean()), "late_mean": float(late["model_err"].mean()),
    }


# ── verdict ─────────────────────────────────────────────────────────────────────────────────

def verdict(pooled: dict, by_bucket: dict, unit: dict, controls: dict,
            contrast: dict) -> dict[str, Any]:
    """The AC, executed rather than narrated.

    The repairable target is `model_err` (μ − y) — NOT the offset. A μ-recalibration can only move
    our own mean; the `close_err` half is a property of the market's number and of the total's skew,
    and a "repair" that removed it would be shifting our conditional mean away from the realised
    conditional mean."""
    cells: dict[str, dict] = {"pooled": pooled["model_err"]}
    for name, _lo, _hi in BUCKETS:
        cells[name] = by_bucket[name]["model_err"]
    rows = {}
    for cell, s in cells.items():
        rows[cell] = {
            "mean_pts": s["cluster_mean"], "pooled_mean_pts": s["mean"],
            "ci": [s["ci_lo"], s["ci_hi"]],
            "demonstrated": s["demonstrated"],              # BINDING: the CI excludes zero
            "material": bool(abs(s["cluster_mean"]) >= MATERIAL_PTS),
            "band_decisive_above": s["band_decisive_above"],
            "band_decisive_below": s["band_decisive_below"],
            "resolvable_mde": s["resolvable"], "mde_pts": s["mde_clustered_pts"],
            # ⚠️ REPORTED, NEVER A CLAUSE. The season permutation measures this statistic to be
            # confounded with the level at this dispersion, so using it would double-count the
            # level it is derived from (NF1.8: a statistic a degenerate wins cannot select).
            "seasons_positive": f"{s['seasons_positive']}/{s['n_clusters']}",
            "sign_test_p": s["sign_test_p"], "cluster_t": s["cluster_t"],
        }
        rows[cell]["HANDS_TO_VAL3"] = bool(rows[cell]["material"] and rows[cell]["demonstrated"])
    winners = [c for c, r in rows.items() if r["HANDS_TO_VAL3"]]
    scoped = [c for c in winners if c != "pooled"]
    # ⭐ A SCOPED hand-off must survive the matched contrast. Without it, a season-wide level bias
    # would be handed to VAL3 wearing a cold-start costume: it is positive in `wk1-3` too, so the
    # per-bucket clauses alone cannot separate "the early weeks are special" from "everything is
    # shifted" (NF-D10). The pooled cell is exempt — for it the level IS the hypothesis.
    if scoped and not (contrast["demonstrated"] and contrast["material"]):
        scoped = []
    if "pooled" in winners:
        state, target = "HAND_TO_VAL3", ["pooled"] + scoped
    elif scoped:
        state, target = "HAND_TO_VAL3_SCOPED", scoped
    else:
        state, target = "NOT_WORTH_A_REPAIR", []
    return {
        "state": state, "cells": rows, "target_cells": target,
        "material_threshold_pts": MATERIAL_PTS,
        "close_unit_mismatch_pts": unit["mean_minus_median_pts"],
        "offset_share_not_repairable_by_mu": pooled["shares"]["close_share"],
        "controls_discriminate": bool(controls["discriminates"]),
        "cold_start_contrast_pts": contrast["mean_delta_pts"],
        "cold_start_contrast_ci": [contrast["ci_lo"], contrast["ci_hi"]],
        "cold_start_contrast_demonstrated": bool(contrast["demonstrated"]),
        # Full disclosure: where the two readings disagree, and what the verdict would have been
        # under the other one. Stated so a reader can apply either rule without re-running.
        "reading_disagreement": {
            "cells_where_mde_and_ci_disagree":
                [c for c, r in rows.items() if r["resolvable_mde"] != r["demonstrated"]],
            "contrast_mde_says": bool(contrast["resolvable"]),
            "contrast_ci_says": bool(contrast["demonstrated"]),
            "verdict_under_mde_rule": ("HAND_TO_VAL3_SCOPED"
                                       if (scoped and contrast["resolvable"] and contrast["material"])
                                       else "NOT_WORTH_A_REPAIR"),
        },
    }


# ── runner ──────────────────────────────────────────────────────────────────────────────────

def run(*, seed: int = B._SEED, n_draws: int = B._DEFAULT_DRAWS,
        max_folds: int | None = None, n_perm: int = 2000) -> dict[str, Any]:
    df, feat, meta = B.load_cache()
    df, feat, pace = ensure_pace_composites(df, feat)
    prov = cache_provenance(df, meta)
    prov.update(pace)

    off = build_offset_frame(df, feat, seed=seed, max_folds=max_folds)
    align = alignment_control(off, seed=seed, n_draws=n_draws)

    f = off.frame
    pooled = summarise(f, off.sigma_total)
    by_bucket = {n: summarise(f[f["bucket"] == n], off.sigma_total) for n, _l, _h in BUCKETS}
    by_season = {int(y): summarise(s, off.sigma_total) for y, s in f.groupby("season")}
    by_week = {}
    for w, s in f.groupby(WEEK_COL):
        if len(s) < 30:
            continue
        by_week[int(w)] = {"n": int(len(s)),
                           **{t: float(s[t].mean()) for t, _d in TERMS}}
    unit = close_unit_reading(f)
    controls = sign_stability_controls(f, seed=seed, n_perm=n_perm)
    contrast = cold_start_contrast(f)
    ver = verdict(pooled, by_bucket, unit, controls, contrast)

    return {
        "story": _STORY, "run_at": date.today().isoformat(),
        "parent": "ablation_results/ncaaf_val1_clv_week_strat.md",
        "config": {"served": SERVED, "seed": seed, "n_draws": n_draws,
                   "buckets": [b[0] for b in BUCKETS], "week_col": WEEK_COL},
        "cache_provenance": prov,
        "dispersion": {"sigma_total": off.sigma_total, "sigma_margin": off.sigma_margin,
                       "rho": off.rho},
        "alignment_control": align,
        "pooled": pooled, "by_bucket": by_bucket, "by_season": by_season, "by_week": by_week,
        "close_unit_reading": unit, "sign_stability_controls": controls,
        "cold_start_contrast": contrast,
        "verdict": ver, "best_alpha": 0,
    }


def _fmt_terms(d: dict, sigma: float) -> str:
    out = []
    for name, desc in TERMS:
        s = d[name]
        out.append(f"    {desc:<40} mean {s['mean']:+7.3f}  med {s['median']:+7.3f}  "
                   f"sd {s['sd']:6.2f}  {s['mean']/sigma:+.4f}σ  "
                   f"seasons>0 {s['seasons_positive']}/{s['n_clusters']}  "
                   f"clustered t {(s['cluster_t'] or float('nan')):+.2f}")
    return "\n".join(out)


def report(doc: dict) -> None:
    a, sig = doc["alignment_control"], doc["dispersion"]["sigma_total"]
    print(f"=== {_STORY} — μ_total − close_total, decomposed (QUERY-ONLY, best_alpha=0) ===")
    p = doc["cache_provenance"]
    print(f"  cache assembled {p['assembled_at']}  {p['n_games']:,} games  "
          f"{p['n_with_close']:,} with a close  (VAL1 scored {p['val1_n_with_close']:,})"
          f"{'' if p['matches_val1_population'] else '   ⚠️ VINTAGE MISMATCH'}")
    if p.get("pace_derived_in_session"):
        print(f"  ⚠️ pace composites derived in-session ({p['n_features_before']}→"
              f"{p['n_features_after']} features) — pre-S1-serve cache vintage")
    print(f"\n  ── alignment control (two-sided) ──")
    print(f"    repaired index  agrees with sign(μ−close) on {a['repaired_agreement']:.4f} "
          f"(floor {a['floor']})  {'✅' if a['positive_control_ok'] else '❌'}")
    print(f"    AS-CODED index  agrees on                    {a['as_coded_agreement']:.4f} "
          f"(ceiling {a['misaligned_ceiling']})  {'✅ discriminates' if a['negative_control_ok'] else '❌'}")
    print(f"    rows whose as-coded index ≠ true position: {100*a['rows_misindexed_frac']:.1f}%   "
          f"MC side-flip band ±{a['mc_flip_band_pts']:.2f} pts")
    print(f"    what the repair costs the recorded CLV read (VAL1 recorded pooled O/U "
          f"{a['val1_recorded_ou_hit']:.4f}, side {a['val1_recorded_ou_side_frac']:.4f}):")
    print(f"      {'':<9}{'pooled hit':>12}{'side→over':>11}"
          + "".join(f"{n+' hit':>12}{n+' side':>12}" for n, _l, _h in BUCKETS))
    for tag, r in (("as-coded", a["as_coded_read"]), ("repaired", a["repaired_read"])):
        cells = "".join(f"{r['by_bucket'][n]['ou_hit']:>12.4f}"
                        f"{r['by_bucket'][n]['side_frac_over']:>12.4f}" for n, _l, _h in BUCKETS)
        print(f"      {tag:<9}{r['ou_hit']:>12.4f}{r['ou_side_frac_over']:>11.4f}{cells}")
    print(f"\n  ── POOLED  (n={doc['pooled']['n']:,}, σ_total={sig:.3f}) ──")
    print(_fmt_terms(doc["pooled"], sig))
    sh = doc["pooled"]["shares"]
    print(f"    ⇒ of the {doc['pooled']['offset']['mean']:+.3f} pt offset, "
          f"{100*sh['model_share']:.0f}% is OUR mean error and {100*sh['close_share']:.0f}% is the "
          f"close-vs-realised term")
    print(f"    ⇒ offset moves P(over) by {doc['pooled']['offset']['p_over_pp']:+.2f} pp at the line")
    u = doc["close_unit_reading"]
    print(f"\n  ── is the close a MEDIAN line? ──")
    print(f"    P(realised > close) = {u['p_realised_over_close_nonpush']:.4f} on n={u['n_nonpush']:,} "
          f"(exact two-sided p vs .50 = {u['exact_two_sided_p_vs_50']:.4f}); median(y−close) = "
          f"{u['median_close_err']:+.3f}")
    print(f"    realised total mean {u['realised_total_mean']:.3f} vs median "
          f"{u['realised_total_median']:.3f} (skew {u['realised_total_skew']:+.3f}) ⇒ a "
          f"median-set line sits {u['mean_minus_median_pts']:+.3f} pts below the MEAN total")
    for name, _l, _h in BUCKETS:
        b = doc["by_bucket"][name]
        print(f"\n  ── {name}  (n={b['n']:,}) ──")
        print(_fmt_terms(b, sig))
    print(f"\n  ── by season ──")
    print(f"    {'season':<8}{'n':>6}{'μ−close':>10}{'μ−y':>9}{'y−close':>9}")
    for y, s in doc["by_season"].items():
        print(f"    {y:<8}{s['n']:>6}{s['offset']['mean']:>+10.3f}"
              f"{s['model_err']['mean']:>+9.3f}{s['close_err']['mean']:>+9.3f}")
    print(f"\n  ── by season_order_week ──")
    print(f"    {'wk':<5}{'n':>6}{'μ−close':>10}{'μ−y':>9}{'y−close':>9}")
    for w, s in doc["by_week"].items():
        print(f"    {w:<5}{s['n']:>6}{s['offset']:>+10.3f}{s['model_err']:>+9.3f}{s['close_err']:>+9.3f}")
    k = doc["cold_start_contrast"]
    print(f"\n  ── matched cold-start contrast (wk1-3 − wk4+, paired WITHIN season) ──")
    print(f"    early {k['early_mean']:+.3f}  late {k['late_mean']:+.3f}  →  Δ = "
          f"{k['mean_delta_pts']:+.3f} pts   95% CI [{k['ci_lo']:+.3f},{k['ci_hi']:+.3f}]   "
          f"t {(k['t'] or float('nan')):+.2f} (crit {k['t_crit']:.2f})   "
          f"demonstrated {k['demonstrated']}   MDE {k['mde_pts']:.3f} (resolvable "
          f"{k['resolvable']})   seasons>0 {k['seasons_positive']}/{k['n_seasons']}")
    print(f"    per-season Δ: {k['per_season_delta']}")
    c = doc["sign_stability_controls"]
    print(f"\n  ── controls on {c['cell']} ──")
    print(f"    season-permutation p = {c['permutation_p']:.4f} ({c['n_perm']:,} shuffles) — "
          f"{c['permutation_reading']}")
    print(f"    injection +{c['injection_above_mde_pts']:.2f} (above MDE) detected: "
          f"{c['injection_above_mde_detected']} (must be True)")
    print(f"    injection +{c['injection_below_mde_pts']:.2f} (below MDE) detected: "
          f"{c['injection_below_mde_detected']} (must be False)")
    print(f"    centred null detected: {c['centred_null_detected']} (must be False)   "
          f"⇒ discriminates: {c['discriminates']}")
    v = doc["verdict"]
    print(f"\n  ── verdict: {v['state']} ──")
    print(f"    {'cell':<9}{'μ−y pts':>9}{'95% CI':>18}{'demo':>7}{'matl':>7}{'MDE':>7}"
          f"{'mde-ok':>8}{'sign':>7}  hands to VAL3")
    for cell, r in v["cells"].items():
        ci = f"[{r['ci'][0]:+.2f},{r['ci'][1]:+.2f}]"
        print(f"    {cell:<9}{r['mean_pts']:>+9.3f}{ci:>18}{str(r['demonstrated']):>7}"
              f"{str(r['material']):>7}{r['mde_pts']:>7.2f}{str(r['resolvable_mde']):>8}"
              f"{r['seasons_positive']:>7}  {r['HANDS_TO_VAL3']}")
    d = v["reading_disagreement"]
    print(f"    binding clause = `demonstrated` (the clustered 95% CI excludes 0). "
          f"MDE/CI disagree on: {d['cells_where_mde_and_ci_disagree'] or '— no cell —'}; "
          f"contrast MDE={d['contrast_mde_says']} CI={d['contrast_ci_says']}")
    print(f"    verdict under the MDE rule instead: {d['verdict_under_mde_rule']}")
    print(f"    target cells: {v['target_cells'] or '— none —'}")


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=f"{_STORY} — μ_total − close offset decomposition")
    ap.add_argument("--seed", type=int, default=B._SEED)
    ap.add_argument("--n-draws", type=int, default=B._DEFAULT_DRAWS)
    ap.add_argument("--max-folds", type=int, default=None)
    ap.add_argument("--n-perm", type=int, default=2000)
    args = ap.parse_args(argv)
    doc = run(seed=args.seed, n_draws=args.n_draws, max_folds=args.max_folds, n_perm=args.n_perm)
    report(doc)
    _RESULTS.mkdir(parents=True, exist_ok=True)
    _OUT_JSON.write_text(json.dumps(doc, indent=2, default=str))
    print(f"\n  → {_OUT_JSON.relative_to(B._PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
