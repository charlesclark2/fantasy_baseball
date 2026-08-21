"""ncaaf_val1_clv_week_strat.py — NCAAF-VAL1: early-season CLV stratification.

Tests the NCAAF vertical's FOUNDING premise — "the college book is softest early" — which
motivated the `strength_posterior` form swap but has never itself been measured against a closing
line. P1.4/S1-serve report the vs-close CLV **pooled over 2020–2025**, so a genuine week-1–3 edge
could in principle be hiding under ~2,600 efficient late-season games.

⛔ **This module CHANGES NOTHING.** It is query-only: it re-runs P1.4's finalize path verbatim
(same folds, same OOS collection, same dispersion fit, same joint draws) and stratifies ONLY the
final `_clv_eval` read by a pre-registered `season_order_week` bucket. No refit, no serving write,
no registry edit, `best_alpha = 0` before and after.

The contract lives in `ablation_results/ncaaf_val1_preregistration.md`, committed BEFORE this file
computed a single bucket hit rate. Buckets, config, family, statistic, pass criterion, anchors and
the null-reading rule are all fixed there; this module only executes it.

⭐ **Why the reuse is load-bearing.** Rebuilding the close join would silently change the
population (the P1.2b dead-bridge lesson), and rebuilding the OOS would change the predictions. The
one number that proves neither happened is the REPRODUCTION PIN: the pooled ATS/O/U hit rate,
placebo and n must match the recorded S1-serve figures. The pin is checked FIRST and HALTS, so a
stratification of a read that does not reproduce its own parent can never be reported.

  uv run python -m quant_sports_intel_models.football.ncaaf.models.ncaaf_val1_clv_week_strat
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from betting_ml.utils.cv_power import classify_null
from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_game as B
from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_distribution import (
    JointDispersion, derive_markets, draw_joint, fit_gaussian_dispersion,
    fit_strength_posterior_scale, score_calibration, strength_posterior_sigma,
)

_STORY = "NCAAF-VAL1"
_RESULTS = Path(B._RESULTS_DIR)
_OUT_JSON = _RESULTS / "ncaaf_val1_clv_week_strat.json"

# ── the pre-registered contract (mirrors ncaaf_val1_preregistration.md §1–§8) ────────────────
BREAKEVEN = 0.5238                      # −110 vig
VIG_WIDTH = BREAKEVEN - 0.50            # 0.0238
MEANINGFUL = BREAKEVEN + VIG_WIDTH      # 0.5476 — one full vig-width above breakeven (§8)
BH_ALPHA = 0.05
MIN_BUCKET_N = 200                      # pass clause 5
MIN_SIDE_BALANCE = 0.10                 # pass clause 6 (activity)
POWER = 0.80

#: §1 — the partition. Fixed. ⛔ `season_order_week`, never raw `week` (the P1.1 postseason
#: restart would drop January playoff games into the cold-start bucket).
BUCKETS: tuple[tuple[str, int, int], ...] = (("wk1-3", 1, 3), ("wk4-6", 4, 6), ("wk7+", 7, 999))
WEEK_COL = "season_order_week"

#: §2 — primary is the SERVED v2 config; the P1.4 v1 is a robustness read that CANNOT pass.
PRIMARY = {"label": "served_v2", "mc": "ridge", "contract": "strength_pace",
           "form": "strength_posterior", "binding": True}
SECONDARY = {"label": "p1_4_v1", "mc": "ridge", "contract": "strength_only",
             "form": "strength_posterior", "binding": False}

#: §2a — the reproduction pin against the recorded S1-serve vs-close CLV.
PIN = {"ats_n": 4114, "ou_n": 4135, "ats_hit": 0.509, "ou_hit": 0.513,
       "ats_placebo": 0.501, "tol": 0.010}

MARKETS = ("ats", "ou")


def bucket_of(week: np.ndarray) -> np.ndarray:
    out = np.empty(len(week), dtype=object)
    for name, lo, hi in BUCKETS:
        out[(week >= lo) & (week <= hi)] = name
    return out


# ── statistics ──────────────────────────────────────────────────────────────────────────────

def exact_p_one_sided(wins: int, n: int, p0: float) -> float:
    """P(X >= wins | Binom(n, p0)) — the exact one-sided binomial p. Exact, not normal-approx:
    at n≈700 the normal approximation moves the third decimal, which is where a BH cutoff lives."""
    return float(stats.binom.sf(wins - 1, n, p0))


def upper_bound(wins: int, n: int, alpha: float) -> float:
    """One-sided Clopper–Pearson UPPER bound at level `alpha` (exact, never a normal approx).

    §8a: this is what makes a below-bar bucket DECISIVE rather than merely 'point estimate low'.
    `alpha` is Bonferroni-adjusted across the declared family, because ruling an effect out is a
    SIMULTANEOUS claim — the conservative direction."""
    if wins >= n:
        return 1.0
    return float(stats.beta.ppf(1.0 - alpha, wins + 1, n - wins))


def mde_hit_rate(n: int, p0: float = BREAKEVEN, alpha: float = 0.05, power: float = POWER) -> float:
    """Smallest true hit rate an EXACT one-sided binomial test detects with `power` at `alpha`.

    Computed from `n` ALONE — a design quantity known before any result (the NF1.8 rule), which is
    why it could be, and was, published in the pre-registration."""
    crit = stats.binom.isf(alpha, n, p0)          # smallest k with P(X > k) <= alpha
    lo, hi = p0, 0.999
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if stats.binom.sf(crit, n, mid) >= power:
            hi = mid
        else:
            lo = mid
    return float(hi)


def games_for_effect(p1: float = MEANINGFUL, p0: float = BREAKEVEN,
                     alpha: float = 0.05, power: float = POWER) -> int:
    """Non-push games needed to detect `p1` at `power`. The re-test trigger's unit is GAMES (and
    thence seasons) — never p-decimals (MH2 g″)."""
    lo, hi = 50, 400_000
    while lo < hi:
        mid = (lo + hi) // 2
        crit = stats.binom.isf(alpha, mid, p0)
        if stats.binom.sf(crit, mid, p1) >= power:
            hi = mid
        else:
            lo = mid + 1
    return int(lo)


def bh_cutoffs(p_values: list[float], alpha: float = BH_ALPHA) -> dict[int, float]:
    """Benjamini–Hochberg cutoff per ORIGINAL index: rank i (1-based, ascending p) → i/m·alpha."""
    m = len(p_values)
    order = np.argsort(p_values, kind="stable")
    return {int(idx): (rank + 1) / m * alpha for rank, idx in enumerate(order)}


def bh_reject(p_values: list[float], alpha: float = BH_ALPHA) -> list[bool]:
    """BH step-up: find the largest rank whose p <= i/m·alpha, reject everything at or below it."""
    m = len(p_values)
    order = np.argsort(p_values, kind="stable")
    k = 0
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= rank / m * alpha:
            k = rank
    out = [False] * m
    for rank, idx in enumerate(order, start=1):
        if rank <= k:
            out[int(idx)] = True
    return out


# ── the P1.4 finalize path, verbatim ────────────────────────────────────────────────────────

_FOLD_CACHE: dict[Any, Any] = {}


def _folds(df: pd.DataFrame, feat: list[str], max_folds: int | None):
    """Memoize the fold build. The folds depend ONLY on (frame, features, max_folds) — never on the
    config — so every config and every MC replicate MUST see byte-identical folds. Rebuilding them
    per call would be both slow and a silent way for two configs to be scored on different splits."""
    key = (id(df), len(feat), max_folds)
    if key not in _FOLD_CACHE:
        _FOLD_CACHE[key] = B.build_folds(df, feat, max_folds=max_folds)
    return _FOLD_CACHE[key]


@dataclass
class Scored:
    """Per-game scored rows for one config: the model's side, the anchors', and the outcome."""
    frame: pd.DataFrame
    pooled: dict[str, Any]


def score_config(df: pd.DataFrame, feat: list[str], cfg: dict, *, seed: int, n_draws: int,
                 max_folds: int | None = None) -> Scored:
    """Reproduce P1.4 `stage_finalize` EXACTLY, then return per-game CLV rows instead of a summary.

    ⭐ The rng consumption order is deliberately identical to `stage_finalize`
    (draw_joint → score_calibration → early-season validation → clv) so the PLACEBO — which is the
    next draw off that same stream — reproduces the recorded number bit-for-bit. Reordering these
    calls would silently change the placebo and quietly break the reproduction pin, which is the
    one control proving nothing upstream was rebuilt."""
    folds = _folds(df, feat, max_folds)
    oos = B._collect_oos(folds, cfg["mc"], cfg["contract"], cfg["form"],
                         top_k=B._DEFAULT_TOP_K, seed=seed)
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
    m_s, t_s = draw_joint(cfg["form"], oos["mu_margin"].to_numpy(), oos["mu_total"].to_numpy(),
                          disp, rng, n_draws=n_draws,
                          sigma_margin_native=sig_m, sigma_total_native=sig_t)
    dists = derive_markets(m_s, t_s)
    obs = {"margin": oos["y_margin"].to_numpy(float), "total": oos["y_total"].to_numpy(float),
           "home_win": (oos["y_margin"].to_numpy() > 0).astype(float)}
    score_calibration(dists, obs, rng)                              # rng-stream parity (see above)
    B._early_season_validation(oos, df, dists, obs, rng)            # rng-stream parity (see above)

    close = df[["game_id", "close_home_spread", "close_total", "has_close"]].drop_duplicates("game_id")
    m = oos.merge(close, on="game_id", how="left")
    m = m[m["has_close"] == True].reset_index(drop=True)             # noqa: E712
    idx = m.index.to_numpy()

    line = -m["close_home_spread"].to_numpy()                        # margin the home side must beat
    y_m, y_t = m["y_margin"].to_numpy(), m["y_total"].to_numpy()
    tot_line = m["close_total"].to_numpy()
    p_cover = (dists["margin"][idx] > line[:, None]).mean(axis=1)
    p_over = (dists["total"][idx] > tot_line[:, None]).mean(axis=1)
    home_covered, over_hit = y_m > line, y_t > tot_line

    out = pd.DataFrame({
        "game_id": m["game_id"].to_numpy(), "season": m["season"].to_numpy().astype(int),
        WEEK_COL: m[WEEK_COL].to_numpy().astype(int),
        "p_cover": p_cover, "p_over": p_over,
        "ats_push": y_m == line, "ou_push": y_t == tot_line,
        # model side correct?  (P1.4 `_clv_eval` rule verbatim: side = p >= 0.5)
        "ats_win": np.where(p_cover >= 0.5, home_covered, ~home_covered),
        "ou_win": np.where(p_over >= 0.5, over_hit, ~over_hit),
        # §7 anchors — the two-sided side-bias degenerates
        "ats_always_home": home_covered, "ats_always_away": ~home_covered,
        "ou_always_over": over_hit, "ou_always_under": ~over_hit,
        "ats_side_home": p_cover >= 0.5, "ou_side_over": p_over >= 0.5,
    })
    rand = rng.random(len(m)) >= 0.5                                 # the P1.4 placebo, same stream
    out["ats_placebo"] = np.where(rand, home_covered, ~home_covered)
    rand_ou = rng.random(len(m)) >= 0.5
    out["ou_placebo"] = np.where(rand_ou, over_hit, ~over_hit)
    out["bucket"] = bucket_of(out[WEEK_COL].to_numpy())

    pooled = {mk: _rates(out, mk) for mk in MARKETS}
    return Scored(frame=out, pooled=pooled)


def _rates(f: pd.DataFrame, market: str) -> dict[str, Any]:
    """Hit rate + anchors on the non-push rows of `f` for one market."""
    keep = f[~f[f"{market}_push"]]
    n = int(len(keep))
    if n == 0:
        return {"n": 0}
    anchors = ({"always_home": "ats_always_home", "always_away": "ats_always_away"}
               if market == "ats" else
               {"always_over": "ou_always_over", "always_under": "ou_always_under"})
    side_col = "ats_side_home" if market == "ats" else "ou_side_over"
    side_frac = float(keep[side_col].mean())
    return {
        "n": n, "wins": int(keep[f"{market}_win"].sum()),
        "hit_rate": float(keep[f"{market}_win"].mean()),
        "placebo": float(keep[f"{market}_placebo"].mean()),
        "anchors": {k: float(keep[c].mean()) for k, c in anchors.items()},
        "side_frac": side_frac, "side_balance": float(min(side_frac, 1.0 - side_frac)),
        "n_push": int(f[f"{market}_push"].sum()),
    }


# ── the pre-registered read ─────────────────────────────────────────────────────────────────

def evaluate(scored: Scored, *, binding: bool) -> dict[str, Any]:
    """Execute §4–§8 of the pre-registration for one config."""
    res: dict[str, Any] = {"pooled": {}, "buckets": {}}
    for mk in MARKETS:
        r = _augment(scored.pooled[mk], family_alpha=BH_ALPHA)
        # The §8a band rule is a deterministic function of (hit rate, n, alpha), so applying it to
        # the pooled read is a DESCRIPTIVE extension, not a new test: the pooled row is not a
        # member of either declared family and carries no BH cutoff and no pass verdict.
        r["band_reading"] = ("MEASURED_IMMATERIAL"
                             if r["hit_rate"] < BREAKEVEN and r["upper_bound_bonf"] < MEANINGFUL
                             else "NOT_DECISIVE")
        res["pooled"][mk] = r

    per_market_rows: dict[str, list[tuple[str, dict]]] = {mk: [] for mk in MARKETS}
    for name, _lo, _hi in BUCKETS:
        sub = scored.frame[scored.frame["bucket"] == name]
        for mk in MARKETS:
            r = _augment(_rates(sub, mk), family_alpha=BH_ALPHA / len(BUCKETS))
            r["per_season"] = _per_season(sub, mk)
            per_market_rows[mk].append((name, r))
            res["buckets"].setdefault(name, {})[mk] = r

    # §5 — BH-FDR within each declared 3-test market family (BINDING) ...
    for mk, rows in per_market_rows.items():
        ps = [r["p_one_sided"] for _n, r in rows]
        cuts, rej = bh_cutoffs(ps), bh_reject(ps)
        for i, (name, r) in enumerate(rows):
            r["bh_family"] = mk
            r["bh_cutoff"] = cuts[i]
            r["bh_reject"] = bool(rej[i])
    # ... and the pooled 6-test correction as a conservative SENSITIVITY (never a substitute).
    flat = [(mk, name, r) for mk, rows in per_market_rows.items() for name, r in rows]
    ps6 = [r["p_one_sided"] for _m, _n, r in flat]
    cuts6, rej6 = bh_cutoffs(ps6), bh_reject(ps6)
    for i, (_mk, _name, r) in enumerate(flat):
        r["bh6_cutoff"], r["bh6_reject"] = cuts6[i], bool(rej6[i])

    # §8 — null classification. `var_trials_sr` is the cross-trial dispersion of the DECLARED
    # 3-arm family (MH2: a family gets its own pre-registered field; ⛔ never re-cut below 3).
    for mk, rows in per_market_rows.items():
        # ⚠️ `observed_sr` lives under `per_season`, NOT at the top level. Reading it from the wrong
        # level silently yields an EMPTY list → `var_trials_sr = 0` → `classify_null` skips its DSR
        # branch entirely and every bucket is classified with the deflation leg never evaluated —
        # a wired-but-never-invoked defect that leaves the suite green and the verdicts plausible
        # (NF-C0e). Asserted, not assumed.
        srs = [r["per_season"]["observed_sr"] for _n, r in rows
               if r["per_season"]["observed_sr"] is not None]
        if len(srs) < 2:
            raise SystemExit(
                f"[{_STORY}] the {mk} family yields {len(srs)} usable per-season Sharpes; the "
                "cross-trial dispersion DSR deflates against cannot be formed. Refusing to "
                "classify with the deflation leg silently absent.")
        v = float(np.var(srs, ddof=1))
        for name, r in rows:
            r["family_var_trials_sr"] = v
            r["null"] = _classify(r, metric=f"{mk}_{name}", var_trials_sr=v,
                                  n_arms=len(BUCKETS))

    res["side_tilt"] = _side_tilt(scored.frame)
    res["leave_2020_out"] = _leave_2020_out(scored.frame)
    res["pass"] = {name: {mk: _pass_clauses(res["buckets"][name][mk], binding=binding)
                          for mk in MARKETS} for name, _lo, _hi in BUCKETS}
    return res


def _leave_2020_out(f: pd.DataFrame) -> dict[str, Any]:
    """§3 — the pre-registered COVID sensitivity, reported for EVERY bucket, not just `wk1-3`.

    2020's early weeks were largely cancelled or postponed (31 `wk1-3` games vs ~135 in every other
    season), so that season is anomalous exactly where the story's hypothesis lives. Registered
    forward as a SENSITIVITY (MH2.8's leave-one-anomalous-season discipline) — ⛔ it is never the
    primary, and re-reading the verdict off it would be the E2.1-r inversion."""
    out: dict[str, Any] = {}
    sub = f[f["season"] != 2020]
    for name, _lo, _hi in BUCKETS:
        s = sub[sub["bucket"] == name]
        out[name] = {mk: {k: v for k, v in _rates(s, mk).items()
                          if k in ("n", "hit_rate", "placebo")} for mk in MARKETS}
    return out


def _side_tilt(f: pd.DataFrame) -> dict[str, Any]:
    """DESCRIPTIVE attribution of an already-decided null — ⛔ NOT a hypothesis test.

    Registered nowhere and claiming nothing: it simply records, per bucket, how often the model took
    each side and how often that side won, so the reader can see WHY a bucket landed where it did
    rather than having to infer it. No p-value is computed here and none may be quoted from it."""
    out: dict[str, Any] = {}
    for name, _lo, _hi in BUCKETS:
        sub = f[f["bucket"] == name]
        ats, ou = sub[~sub["ats_push"]], sub[~sub["ou_push"]]
        out[name] = {
            "model_takes_home_ats": float(ats["ats_side_home"].mean()),
            "home_actually_covered": float(ats["ats_always_home"].mean()),
            "model_takes_over_ou": float(ou["ou_side_over"].mean()),
            "over_actually_hit": float(ou["ou_always_over"].mean()),
        }
    return out


def _augment(r: dict, *, family_alpha: float) -> dict:
    if not r.get("n"):
        return r
    n, w = r["n"], r["wins"]
    r["p_one_sided"] = exact_p_one_sided(w, n, BREAKEVEN)
    r["p_one_sided_vs_50"] = exact_p_one_sided(w, n, 0.50)   # §4a — DIAGNOSTIC, never binding
    r["upper_bound_bonf"] = upper_bound(w, n, family_alpha)  # §8a — the decisive bound
    r["upper_bound_nominal"] = upper_bound(w, n, BH_ALPHA)
    r["mde_hit_rate"] = mde_hit_rate(n)
    r["mde_pp"] = 100.0 * (r["mde_hit_rate"] - BREAKEVEN)
    r["edge_pp"] = 100.0 * (r["hit_rate"] - BREAKEVEN)
    r["roi_at_minus_110"] = r["hit_rate"] * (100.0 / 110.0) - (1.0 - r["hit_rate"])
    return r


def _per_season(sub: pd.DataFrame, market: str) -> dict[str, Any]:
    keep = sub[~sub[f"{market}_push"]]
    g = keep.groupby("season")[f"{market}_win"].agg(["mean", "size"])
    edge = (g["mean"] - BREAKEVEN).to_numpy()
    sd = float(np.std(edge, ddof=1)) if len(edge) > 1 else 0.0
    return {
        "seasons": [int(s) for s in g.index],
        "hit_rate": [round(float(x), 4) for x in g["mean"]],
        "n": [int(x) for x in g["size"]],
        "fold_wins": int((g["mean"] > BREAKEVEN).sum()), "n_folds": int(len(g)),
        # observed_sr is the per-season Sharpe of the edge series; a zero-dispersion series has an
        # UNBOUNDED (not zero) Sharpe, so it is reported as None rather than silently as 0.0.
        "observed_sr": (float(np.mean(edge) / sd) if sd > 1e-12 else None),
        "skew": float(stats.skew(edge)) if len(edge) > 2 else 0.0,
        "kurt": float(stats.kurtosis(edge, fisher=False)) if len(edge) > 3 else 3.0,
    }


def _classify(r: dict, *, metric: str, var_trials_sr: float, n_arms: int) -> dict[str, Any]:
    """`classify_null` RAW, plus the §8a call-site band correction, reported side by side."""
    ps = r["per_season"]
    active = r["side_balance"] >= MIN_SIDE_BALANCE
    v = classify_null(
        metric=metric, n_folds=ps["n_folds"], n_arms=n_arms,
        beats_foil=bool(r["hit_rate"] > BREAKEVEN),
        observed_sr=ps["observed_sr"], var_trials_sr=(var_trials_sr or None),
        fold_wins=ps["fold_wins"], p_one_sided=r["p_one_sided"], bh_cutoff=r["bh_cutoff"],
        active=active,
        inactive_reason=(None if active else
                         f"`{metric}`: the model takes the same side on "
                         f"{100 * (1 - r['side_balance']):.0f}% of rows in this bucket, so the "
                         f"read is a side bias, not a scored decision."),
        mde_sd_units=r["mde_pp"], meaningful_sd_units=100.0 * (MEANINGFUL - BREAKEVEN),
        skew=ps["skew"], kurt=ps["kurt"], declared_field_size=n_arms,
        # `V` is measured over the three BUCKETS — every one a real, pre-registered arm. The
        # degenerates in this study (the placebo and the two side-bias anchors, §7) are scored
        # PER BUCKET as anchors and are never trials, so no lose-by-construction arm has ever
        # been inside `V`. Stating that truthfully is a provenance claim (DSR-CONV), not a trim:
        # it changes no STATE, only whether the remedy sentence may be acted on.
        degenerates_excluded_from_v=True,
    )
    raw = {"state": v.state, "reason": v.reason, "retest_trigger": v.retest_trigger,
           "detail": {k: (float(x) if isinstance(x, (int, float, np.floating)) else x)
                      for k, x in (v.detail or {}).items()}}

    # §8a — the NF-W7i band correction, registered FORWARD in the pre-registration.
    if not active:
        corr, why, trigger = v.state, v.reason, v.retest_trigger
    elif r["hit_rate"] >= BREAKEVEN:
        corr, why, trigger = v.state, v.reason, v.retest_trigger
    elif r["upper_bound_bonf"] < MEANINGFUL:
        need = games_for_effect()
        corr = "MEASURED_IMMATERIAL"
        why = (f"`{metric}`: hit rate {r['hit_rate']:.4f} is below the {BREAKEVEN} breakeven AND the "
               f"family-adjusted one-sided upper bound {r['upper_bound_bonf']:.4f} lies BELOW the "
               f"pre-registered meaningful effect {MEANINGFUL:.4f}. The ENTIRE plausible range is "
               f"below a decision-changing edge, so this is decisive — not underpowered. (Detecting "
               f"that effect would need {need:,} non-push games; this bucket has {r['n']:,}, but "
               f"the interval already excludes it, which is the sharper post-data question.)")
        trigger = None
    else:
        need = games_for_effect()
        corr = "POWER_LIMITED"
        why = (f"`{metric}`: hit rate {r['hit_rate']:.4f} is below breakeven, but the family-adjusted "
               f"upper bound {r['upper_bound_bonf']:.4f} still ADMITS the meaningful effect "
               f"{MEANINGFUL:.4f}. ⛔ Do NOT read this as absence — this design cannot separate the "
               f"null from a decision-changing edge.")
        trigger = (f"{need:,} non-push games at 80% power vs {r['n']:,} here "
                   f"(+{need - r['n']:,} ≈ {(need - r['n']) / max(r['n'] / 6, 1):.0f} more seasons "
                   f"at this bucket's rate)")
    return {"raw": raw, "corrected": {"state": corr, "reason": why, "retest_trigger": trigger},
            "correction_applied": corr != raw["state"]}


def _pass_clauses(r: dict, *, binding: bool) -> dict[str, Any]:
    """§6 — the six pass clauses, each reported with its own value so none is vacuous."""
    anchors = r.get("anchors", {})
    best_anchor = max(anchors.values()) if anchors else 0.0
    c = {
        "1_material_point": bool(r["hit_rate"] >= BREAKEVEN),
        "2_bh_significant": bool(r.get("bh_reject", False)),
        "3_beats_placebo": bool(r["hit_rate"] > r["placebo"]),
        "4_beats_degenerates": bool(r["hit_rate"] > best_anchor),
        "5_non_degenerate_n": bool(r["n"] >= MIN_BUCKET_N),
        "6_active": bool(r["side_balance"] >= MIN_SIDE_BALANCE),
    }
    c["values"] = {"hit_rate": r["hit_rate"], "breakeven": BREAKEVEN,
                   "p_one_sided": r["p_one_sided"], "bh_cutoff": r.get("bh_cutoff"),
                   "placebo": r["placebo"], "best_degenerate": best_anchor,
                   "n": r["n"], "side_balance": r["side_balance"]}
    c["CLEARS"] = bool(binding and all(c[k] for k in c if k[0].isdigit()))
    if not binding:
        c["note"] = ("robustness read — pre-registered §2 as INELIGIBLE to pass under any "
                     "circumstance, so CLEARS is False by construction, not by result.")
    return c


# ── reproduction pin ────────────────────────────────────────────────────────────────────────

def check_pin(pooled: dict) -> dict[str, Any]:
    """§2a — HALT if the pooled read does not reproduce the recorded S1-serve CLV."""
    checks = {
        "ats_n": (pooled["ats"]["n"], PIN["ats_n"], pooled["ats"]["n"] == PIN["ats_n"]),
        "ou_n": (pooled["ou"]["n"], PIN["ou_n"], pooled["ou"]["n"] == PIN["ou_n"]),
        "ats_hit": (pooled["ats"]["hit_rate"], PIN["ats_hit"],
                    abs(pooled["ats"]["hit_rate"] - PIN["ats_hit"]) <= PIN["tol"]),
        "ou_hit": (pooled["ou"]["hit_rate"], PIN["ou_hit"],
                   abs(pooled["ou"]["hit_rate"] - PIN["ou_hit"]) <= PIN["tol"]),
        "ats_placebo": (pooled["ats"]["placebo"], PIN["ats_placebo"],
                        abs(pooled["ats"]["placebo"] - PIN["ats_placebo"]) <= PIN["tol"]),
    }
    return {"checks": {k: {"got": v[0], "expected": v[1], "ok": bool(v[2])}
                       for k, v in checks.items()},
            "all_ok": all(v[2] for v in checks.values())}


# ── runner ──────────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=f"{_STORY} — early-season CLV stratification")
    ap.add_argument("--seed", type=int, default=B._SEED)
    ap.add_argument("--n-draws", type=int, default=B._DEFAULT_DRAWS)
    ap.add_argument("--mc-seeds", type=int, nargs="*", default=[7, 1234],
                    help="§9 extra seeds for the MC error bar (cannot change any verdict).")
    ap.add_argument("--mc-draws", type=int, default=20_000, help="§9 high-draw stability run.")
    ap.add_argument("--skip-mc", action="store_true")
    ap.add_argument("--max-folds", type=int, default=None)
    args = ap.parse_args(argv)

    print(f"=== {_STORY} — early-season CLV stratification (QUERY-ONLY, best_alpha=0) ===")
    df, feat, meta = B.load_cache()
    print(f"  cache: {len(df):,} games, {int(df['has_close'].sum()):,} with a leakage-safe close")

    print(f"\n  scoring PRIMARY ({PRIMARY['mc']}/{PRIMARY['contract']}/{PRIMARY['form']}, "
          f"seed={args.seed}, draws={args.n_draws:,}) — the P1.4 finalize path verbatim …")
    primary = score_config(df, feat, PRIMARY, seed=args.seed, n_draws=args.n_draws,
                           max_folds=args.max_folds)

    pin = check_pin(primary.pooled)
    print("\n  ── §2a reproduction pin vs the recorded S1-serve CLV ──")
    for k, v in pin["checks"].items():
        print(f"    {k:<12} got {v['got']!s:<8} expected {v['expected']!s:<8} "
              f"{'✅' if v['ok'] else '❌'}")
    if not pin["all_ok"]:
        raise SystemExit(
            f"[{_STORY}] ⛔ HALT — the pooled read does not reproduce the recorded S1-serve CLV. "
            "Per pre-registration §2a no bucket number is reported until this is diagnosed: a "
            "stratification of a read that does not reproduce its own parent is not evidence.")
    print("    pin PASS ✅ — the close join and the OOS predictions are the recorded ones")

    res_primary = evaluate(primary, binding=True)

    print(f"\n  scoring SECONDARY ({SECONDARY['contract']}) — robustness only, cannot pass …")
    secondary = score_config(df, feat, SECONDARY, seed=args.seed, n_draws=args.n_draws,
                             max_folds=args.max_folds)
    res_secondary = evaluate(secondary, binding=False)

    mc: dict[str, Any] = {"skipped": bool(args.skip_mc)}
    if not args.skip_mc:
        print(f"\n  §9 MC-stability control: seeds {args.mc_seeds} + a {args.mc_draws:,}-draw run "
              "(bounds draw noise; ⛔ cannot change a verdict) …")
        runs: dict[str, dict] = {}
        for s in args.mc_seeds:
            sc = score_config(df, feat, PRIMARY, seed=s, n_draws=args.n_draws,
                              max_folds=args.max_folds)
            runs[f"seed{s}"] = _bucket_hits(sc)
        sc = score_config(df, feat, PRIMARY, seed=args.seed, n_draws=args.mc_draws,
                          max_folds=args.max_folds)
        runs[f"draws{args.mc_draws}"] = _bucket_hits(sc)
        runs["primary"] = _bucket_hits(primary)
        mc["runs"] = runs
        mc["spread_pp"] = {
            key: round(100.0 * (max(r[key] for r in runs.values())
                                - min(r[key] for r in runs.values())), 2)
            for key in runs["primary"]}

    _report(res_primary, res_secondary, mc, meta)

    doc = {"story": _STORY, "run_at": date.today().isoformat(),
           "preregistration": "ablation_results/ncaaf_val1_preregistration.md",
           "config": {"primary": PRIMARY, "secondary": SECONDARY,
                      "seed": args.seed, "n_draws": args.n_draws,
                      "cache_assembled_at": meta.get("assembled_at")},
           "contract": {"breakeven": BREAKEVEN, "meaningful": MEANINGFUL,
                        "bh_alpha": BH_ALPHA, "buckets": [b[0] for b in BUCKETS],
                        "games_for_meaningful_effect": games_for_effect()},
           "reproduction_pin": pin, "primary": res_primary, "secondary": res_secondary,
           "mc_stability": mc, "best_alpha": 0}
    _OUT_JSON.write_text(json.dumps(doc, indent=2, default=str))
    print(f"\n  → {_OUT_JSON.relative_to(B._PROJECT_ROOT)}")
    return 0


def _bucket_hits(sc: Scored) -> dict[str, float]:
    out = {}
    for name, _lo, _hi in BUCKETS:
        sub = sc.frame[sc.frame["bucket"] == name]
        for mk in MARKETS:
            out[f"{mk}_{name}"] = _rates(sub, mk)["hit_rate"]
    return out


def _report(primary: dict, secondary: dict, mc: dict, meta: dict) -> None:
    for mk in MARKETS:
        print(f"\n  ── {mk.upper()} — hit rate vs the closing line (breakeven {BREAKEVEN}) ──")
        print(f"    {'bucket':<9}{'n':>6}{'hit':>8}{'edge pp':>9}{'placebo':>9}{'best deg':>10}"
              f"{'p(>be)':>9}{'BH cut':>8}{'MDE':>8}{'upper':>8}  null state")
        rows = [("pooled", primary["pooled"][mk])] + \
               [(n, primary["buckets"][n][mk]) for n, _l, _h in BUCKETS]
        for name, r in rows:
            if not r.get("n"):
                continue
            best_deg = max(r["anchors"].values())
            state = r.get("null", {}).get("corrected", {}).get("state", "—")
            print(f"    {name:<9}{r['n']:>6}{r['hit_rate']:>8.4f}{r['edge_pp']:>+9.2f}"
                  f"{r['placebo']:>9.4f}{best_deg:>10.4f}{r['p_one_sided']:>9.4f}"
                  f"{(r.get('bh_cutoff') or float('nan')):>8.4f}{r['mde_hit_rate']:>8.4f}"
                  f"{r['upper_bound_bonf']:>8.4f}  {state}")
    print("\n  ── §3 leave-2020-out sensitivity (COVID; ⛔ never the primary) ──")
    for mk in MARKETS:
        cells = "  ".join(f"{n}={primary['leave_2020_out'][n][mk]['hit_rate']:.4f}"
                          f"(n={primary['leave_2020_out'][n][mk]['n']})" for n, _l, _h in BUCKETS)
        print(f"    {mk}: {cells}")
    print("\n  ── side tilt (DESCRIPTIVE attribution — no inferential claim) ──")
    print(f"    {'bucket':<9}{'model→home':>12}{'home covered':>14}{'model→over':>12}{'over hit':>10}")
    for name, _l, _h in BUCKETS:
        t = primary["side_tilt"][name]
        print(f"    {name:<9}{t['model_takes_home_ats']:>12.3f}{t['home_actually_covered']:>14.3f}"
              f"{t['model_takes_over_ou']:>12.3f}{t['over_actually_hit']:>10.3f}")
    print("\n  ── §6 pass criterion ──")
    for name, _l, _h in BUCKETS:
        for mk in MARKETS:
            p = primary["pass"][name][mk]
            failed = [k for k in p if k[0].isdigit() and not p[k]]
            print(f"    {mk}/{name:<8} CLEARS={p['CLEARS']}"
                  + (f"   failed: {', '.join(failed)}" if failed else ""))
    print("\n  ── secondary (P1.4 v1 `strength_only`) — robustness only, cannot pass ──")
    for mk in MARKETS:
        cells = "  ".join(f"{n}={secondary['buckets'][n][mk]['hit_rate']:.4f}"
                          for n, _l, _h in BUCKETS)
        print(f"    {mk}: pooled={secondary['pooled'][mk]['hit_rate']:.4f}   {cells}")
    if not mc.get("skipped"):
        print("\n  ── §9 MC stability (max−min across seeds/draw counts, pp) ──")
        print("    " + "  ".join(f"{k}={v:+.2f}" for k, v in mc["spread_pp"].items()))


if __name__ == "__main__":
    raise SystemExit(main())
