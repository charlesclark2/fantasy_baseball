"""mh2_1_conditional_calibration.py — MH2.1 follow-up: does the homoscedastic winner lose
per-game variance where it matters?

WHY THIS EXISTS
---------------------------------------------------------------------------------------------------
MH2.1's wide-window bake-off returned SHIP_CHALLENGER with `plus_eb::glm_elasticnet` leading. That
arm is `model_bakeoff.PointNormalSpec` — a **HOMOSCEDASTIC** Normal: `Normal(pred, sigma_hat)` with
ONE constant sigma taken from the in-fold training residuals. The incumbent `ngboost_normal` is
**HETEROSCEDASTIC** — it predicts a per-game sigma, and E2.1-r selected it precisely for that
"honest variance".

The served totals model prices `P(over)` at a line FROM ITS PREDICTIVE DISTRIBUTION, so replacing a
per-game sigma with a constant is a change in serving behaviour, not a like-for-like swap. And
**neither metric the bake-off scored can see it**:

  * CRPS is a proper score, but it is dominated by the MEAN. A model can win CRPS on sharper means
    while being conditionally wrong about spread.
  * PIT-KS is a **MARGINAL** statistic. A homoscedastic model that over-covers the calm games by
    exactly as much as it under-covers the volatile ones has a **flat marginal PIT** and a clean
    PIT-KS while being badly miscalibrated CONDITIONALLY. The errors cancel in the pooled histogram.

So this script asks the question the bake-off structurally could not: **stratify by where variance
actually differs, and check calibration WITHIN each stratum.**

THE SIGNATURE WE ARE LOOKING FOR
--------------------------------
If per-game variance is real and the homoscedastic arm has thrown it away, its central-80% coverage
must drift MONOTONICALLY across strata ordered by predicted sigma: **over-covering the low-sigma
games and under-covering the high-sigma ones**, while a heteroscedastic arm stays flat near 0.80.
The headline statistic is therefore the coverage SPREAD across sigma-deciles (and its trend), not
the pooled number.

⚠️ **TWO-SIDED ANCHORS, OR THIS DIAGNOSTIC PROVES NOTHING (NF1.7 (a): a check that cannot fail is
not a check).** A "no meaningful difference" verdict is only worth something if the instrument can
DETECT the defect when it is definitely present. So the field carries:

  * a **POSITIVE CONTROL** — `plus_eb::ngboost_FLATTENED`: the heteroscedastic arm's OWN means with
    its per-game sigma replaced by a constant of the SAME average variance
    (`sqrt(mean(sigma^2))`). It differs from its parent in exactly ONE respect — the per-game
    VARIATION in sigma — so it isolates the mechanism under test and it MUST show the drift. If it
    does not, the metric is blind and no conclusion may be drawn from it.
  * a **NEGATIVE CONTROL** — its heteroscedastic parent `plus_eb::ngboost_normal`, which should be
    flattest. This is also the MATCHED FOIL (NF-D15 g'): same features as the leader, different
    variance model, so a difference between them is attributable to the variance model rather than
    to the `plus_eb` block.

💸 **SNOWFLAKE-FREE AND NETWORK-FREE BY CONSTRUCTION.** It reads ONLY the local training-matrix
parquet that MH2.1's bake-off already cached, and it **HALTS rather than pulling** if that cache is
absent. No Snowflake, no S3, no warehouse wake. (The E11.20-COST finding: ~80% of the Snowflake bill
is warehouse wake/idle, so a diagnostic that quietly triggers a pull is a real cost, not a rounding
error.) Compute is 2 NGBoost + 1 GLM fit per fold — strictly CHEAPER than the 4-arm bake-off that
produced the result being checked.

🔒 `best_alpha = 0`. This is a calibration diagnostic. It says nothing about win rate, edge or ROI.

Usage:
    uv run python betting_ml/scripts/mh2_1_conditional_calibration.py
    uv run python betting_ml/scripts/mh2_1_conditional_calibration.py --exclude-seasons 2020
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_ABL = PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
_JSON_DIR = PROJECT_ROOT / "betting_ml/evaluation/feature_selection/bakeoff"
_CACHE = PROJECT_ROOT / "betting_ml/data/cache/edge_e1_training_from2016.parquet"

STORY = "MH2.1-cal"
BEST_ALPHA = 0
TARGET, TIER = "total_runs", "post_lineup"
NOMINAL = 0.80                 # central interval whose coverage we track
N_STRATA = 10                  # sigma deciles
N_PERM = 400                   # permutation draws for the slope null

#: Below this coefficient of variation the incumbent's per-game sigma is effectively constant, so
#: there is no per-game variance for a homoscedastic arm to lose and the check cannot discriminate.
MIN_SIGMA_CV = 0.02

#: The homoscedastic arm's coverage may drift this far across sigma-deciles before we call the loss
#: of per-game variance MATERIAL for pricing. Set from the serving question, not from the answer:
#: an 80% interval whose true coverage swings by more than 5 points across the volatility range is
#: mispricing the tails of a totals market in a way a bettor could systematically exploit.
COVERAGE_SPREAD_TOLERANCE = 0.05


def _var_z_slope(z: np.ndarray, lab: np.ndarray, k: int) -> float:
    """OLS slope of per-stratum Var(z) on the stratum index.

    ⭐ **A SLOPE, NOT A RANGE — and this is the correction that makes the whole diagnostic
    work.** The first cut of this script used `max − min` of per-stratum coverage. That statistic
    is NOISE-DOMINATED and its expectation GROWS with the number of strata: at ~320 rows per
    decile a PERFECTLY calibrated model posts an expected max−min of **0.069** (p95 0.100),
    which swallowed every real signal — all four arms scored inside the null band and the
    instrument read blind. A range over k noisy estimates measures k and n, not miscalibration.
    A slope pools every stratum, has a null centred at zero, and is testable by permutation.
    """
    vz = np.array([z[lab == s].var(ddof=1) if (lab == s).sum() > 2 else np.nan
                   for s in range(k)], float)
    ok = np.isfinite(vz)
    if ok.sum() < 2:
        return float("nan")
    return float(np.polyfit(np.arange(k, dtype=float)[ok], vz[ok], 1)[0])


def _pit(y, out) -> np.ndarray:
    """Probability-integral transform of each observation under its own predictive."""
    from scipy.stats import norm

    y = np.asarray(y, float)
    if out.kind == "normal":
        return norm.cdf((y - out.loc) / np.maximum(out.scale, 1e-12))
    if out.kind == "lognormal":
        with np.errstate(divide="ignore"):
            return norm.cdf((np.log(np.maximum(y, 1e-12)) - out.loc) / np.maximum(out.scale, 1e-12))
    raise SystemExit(f"{STORY} handles normal/lognormal predictives; got {out.kind}")


def _interval(out, nominal: float = NOMINAL):
    from scipy.stats import norm

    z = norm.ppf(0.5 + nominal / 2.0)
    if out.kind == "normal":
        return out.loc - z * out.scale, out.loc + z * out.scale
    lo = np.exp(out.loc - z * out.scale)
    hi = np.exp(out.loc + z * out.scale)
    return lo, hi


def _flatten(out):
    """POSITIVE CONTROL — same means, same AVERAGE variance, ZERO per-game variation.

    `sqrt(mean(sigma^2))` keeps the average predictive variance identical to the parent's, so the
    control differs from it in exactly one respect: whether sigma moves game to game. Matching on
    average sharpness is what makes any difference attributable to the VARIATION rather than to the
    control simply being wider or narrower overall (the NF-D15 g' matched-foil discipline).
    """
    from betting_ml.utils.promotion_gate import PredictiveOutput

    const = float(np.sqrt(np.mean(np.asarray(out.scale, float) ** 2)))
    return PredictiveOutput.normal(out.loc, np.full(len(out.loc), const))


def run(exclude_seasons: tuple[int, ...] = (), seed: int = 42, smoke: bool = False) -> dict:
    if not _CACHE.exists():
        # ⚠️ `relative_to` RAISES when the path sits outside the project, so the guard's own error
        # path must not use it bare — an error handler that errors replaces a helpful message with a
        # confusing traceback exactly when the user most needs the message.
        try:
            shown = _CACHE.relative_to(PROJECT_ROOT)
        except ValueError:
            shown = _CACHE
        raise SystemExit(
            f"❌ {shown} is absent.\n"
            f"   This script deliberately REFUSES to pull it — a pull would wake the Snowflake\n"
            f"   warehouse, and this diagnostic exists to be free. Run MH2.1's bake-off first\n"
            f"   (it writes this cache), then re-run."
        )

    from betting_ml.scripts.e7_9_train_serve_consistency import (
        INCUMBENT_CLASS, build_arm_contracts, contract_coverage_by_season,
    )
    from betting_ml.scripts.model_bakeoff import _TARGETS, _candidates, load_clean_matrix
    from betting_ml.scripts.promotion_gate_eval import _impute, make_gate_splitter

    cfg = _TARGETS[TARGET]
    metric, tcol = cfg["metric"], cfg["col"]

    # refresh_cache=False + the guard above ⇒ a pure local parquet read.
    df = load_clean_matrix(refresh_cache=False, smoke=smoke, min_year=2016)
    if exclude_seasons:
        keep = ~df["game_year"].astype(int).isin([int(y) for y in exclude_seasons])
        df = df.loc[keep].reset_index(drop=True)
    seasons = sorted(df["game_year"].astype(int).unique())

    variants = build_arm_contracts(TARGET, TIER, set(df.columns), family="mh2_1")
    classes = {c.name: c for c in _candidates("reg", TARGET, df, seed=seed, smoke=smoke)}
    inc_cls = INCUMBENT_CLASS[TARGET]

    # The field: the served champion, the MATCHED FOIL (same features, heteroscedastic), and the
    # MH2.1 leader (same features, homoscedastic). The positive control is derived from the foil.
    arms = {
        "incumbent::ngboost_normal": ("incumbent", inc_cls),
        "plus_eb::ngboost_normal": ("plus_eb", inc_cls),
        "plus_eb::glm_elasticnet": ("plus_eb", "glm_elasticnet"),
    }
    control = "plus_eb::ngboost_FLATTENED"

    union = sorted({c for cols in variants.values() for c in cols})
    splitter, _ = make_gate_splitter(True, feature_cols=union, embargo_days=3)
    folds = list(splitter(df))
    print(f"[{STORY}] {TARGET}/{TIER}: window {seasons[0]}–{seasons[-1]} "
          f"({len(seasons)} seasons) → {len(folds)} folds · {len(df):,} rows · SNOWFLAKE-FREE")
    print(f"[{STORY}] field: {list(arms)} + POSITIVE CONTROL `{control}`")

    rec: dict[str, list] = {n: [] for n in list(arms) + [control]}
    strat_sigma, strat_mean, strat_park, ys = [], [], [], []

    for tr, ev in folds:
        ytr, yev = df.loc[tr, tcol].values, df.loc[ev, tcol].values
        cache: dict[str, tuple] = {}
        outs = {}
        for name, (v, cls) in arms.items():
            if v not in cache:
                cache[v] = _impute(df.loc[tr, variants[v]], df.loc[ev, variants[v]])
            Xtr, Xev = cache[v]
            outs[name] = classes[cls].fit_predict(Xtr, ytr, Xev, yev)
        outs[control] = _flatten(outs["plus_eb::ngboost_normal"])

        for name, out in outs.items():
            lo, hi = _interval(out)
            rec[name].append(pd.DataFrame({
                "pit": _pit(yev, out),
                "covered": ((yev >= lo) & (yev <= hi)).astype(float),
                "crps": out.score_to_truth(yev, metric),
                "sigma": np.asarray(out.scale, float),
                # ⭐ THE PRIMARY QUANTITY. `z = (y − μ)/σ` must have variance 1 in EVERY stratum for a
                # conditionally-calibrated model. A homoscedastic arm divides by a constant, so
                # Var(z) falls below 1 where the true spread is small and rises above 1 where it is
                # large — a graded, continuous signal that uses every row, unlike a binary coverage
                # indicator which throws away all magnitude information.
                "z": (np.asarray(yev, float) - out.loc) / np.maximum(out.scale, 1e-12),
            }))
        # ⭐ ONE SHARED STRATIFIER for every arm — the MATCHED FOIL's predicted sigma. It must be
        # shared or the arms sit on different row groupings and are incomparable; and it must be the
        # FOIL's (not the incumbent's) because the positive control is derived from the foil, so the
        # foil's sigma is exactly the per-game variance the control destroys. Stratifying by a
        # different model's sigma would blunt the control and understate the instrument's power.
        strat_sigma.append(np.asarray(outs["plus_eb::ngboost_normal"].scale, float))
        strat_mean.append(np.asarray(outs["plus_eb::ngboost_normal"].mean, float))
        strat_park.append(df.loc[ev, "park_run_factor_3yr"].to_numpy(dtype=float))
        ys.append(yev)

    sigma = np.concatenate(strat_sigma)
    pooled = {n: pd.concat(v, ignore_index=True) for n, v in rec.items()}
    base = pd.DataFrame({
        "sigma_stratum": pd.qcut(sigma, N_STRATA, labels=False, duplicates="drop"),
        "mean_stratum": pd.qcut(np.concatenate(strat_mean), N_STRATA, labels=False, duplicates="drop"),
        "park_stratum": pd.qcut(pd.Series(np.concatenate(strat_park)).rank(method="first"),
                                3, labels=False, duplicates="drop"),
    })

    from scipy.stats import kstest

    def _profile(key: str) -> dict:
        lab = base[key].to_numpy()
        k = int(np.nanmax(lab)) + 1
        out: dict = {}
        for name, d in pooled.items():
            rows = []
            for s in range(k):
                g = d.loc[lab == s]
                if g.empty:
                    continue
                rows.append({
                    "stratum": int(s), "n": int(len(g)),
                    "coverage": float(g["covered"].mean()),
                    "var_z": float(g["z"].var(ddof=1)),
                    "pit_ks": float(kstest(g["pit"].clip(1e-9, 1 - 1e-9), "uniform").statistic),
                    "crps": float(g["crps"].mean()),
                    "mean_sigma": float(g["sigma"].mean()),
                })
            z = d["z"].to_numpy(float)
            out[name] = {
                "strata": rows,
                "var_z_slope": _var_z_slope(z, lab, k),
                "pooled_var_z": float(np.var(z, ddof=1)),
                "pooled_coverage": float(d["covered"].mean()),
                "pooled_pit_ks": float(kstest(d["pit"].clip(1e-9, 1 - 1e-9), "uniform").statistic),
                "pooled_crps": float(d["crps"].mean()),
            }
        return out

    profiles = {kk: _profile(kk) for kk in ("sigma_stratum", "mean_stratum", "park_stratum")}
    sig = profiles["sigma_stratum"]
    foil, leader = "plus_eb::ngboost_normal", "plus_eb::glm_elasticnet"

    # ── Can the mechanism ACT at all? (NF1.9: "a mechanism that cannot act is a finding") ──────────
    # If the heteroscedastic model's own sigma barely moves game to game, then there is no per-game
    # variance to lose and the entire concern is moot — a SCOPE finding, not a clean bill of health.
    sig_vals = pooled[foil]["sigma"].to_numpy(float)
    sigma_cv = float(np.std(sig_vals) / np.mean(sig_vals)) if np.mean(sig_vals) else float("nan")

    # ── PERMUTATION NULL on the slope DIFFERENCE vs the matched foil ──────────────────────────────
    # Shuffling the stratum labels destroys any relationship between sigma and Var(z) while keeping
    # every arm's marginal z-distribution and every stratum's size intact — so it gives the exact
    # null this statistic needs, with no distributional assumption.
    lab = base["sigma_stratum"].to_numpy()
    k = int(np.nanmax(lab)) + 1
    rng = np.random.default_rng(seed)
    zf = pooled[foil]["z"].to_numpy(float)
    perm = {n: [] for n in (control, leader)}
    obs = {n: sig[n]["var_z_slope"] - sig[foil]["var_z_slope"] for n in (control, leader)}
    for _ in range(N_PERM):
        pl = rng.permutation(lab)
        base_s = _var_z_slope(zf, pl, k)
        for n in perm:
            perm[n].append(_var_z_slope(pooled[n]["z"].to_numpy(float), pl, k) - base_s)

    def _z(name: str) -> dict:
        d = np.asarray(perm[name], float)
        sd = float(np.std(d, ddof=1))
        return {
            "slope_vs_foil": round(float(obs[name]), 5),
            "null_sd": round(sd, 5),
            "z_score": (round(float(obs[name] / sd), 2) if sd > 0 else None),
            "p_one_sided": round(float((np.sum(d >= obs[name]) + 1) / (len(d) + 1)), 4),
        }

    ctrl_stat, lead_stat = _z(control), _z(leader)
    detects = bool(ctrl_stat["z_score"] is not None and ctrl_stat["z_score"] >= 2.0)
    verdict_detail = {
        "stratifier": f"{foil} predicted sigma (deciles)",
        "sigma_coefficient_of_variation": round(sigma_cv, 4),
        "var_z_slope_foil_heteroscedastic": round(sig[foil]["var_z_slope"], 5),
        "positive_control": ctrl_stat,
        "leader": lead_stat,
        "instrument_detects_variance_loss": detects,
        "n_permutations": N_PERM,
    }

    if sigma_cv < MIN_SIGMA_CV:
        verdict = "MECHANISM_INACTIVE"
        reading = (
            f"⚪ **THE MECHANISM CANNOT ACT ON THIS POPULATION — a SCOPE finding, not a clean bill of "
            f"health (NF1.9).** The heteroscedastic incumbent's own per-game σ has a coefficient of "
            f"variation of just **{sigma_cv:.3f}** (below the {MIN_SIGMA_CV} floor), i.e. it is "
            f"nearly constant already. There is essentially no per-game variance for the "
            f"homoscedastic winner to throw away, so this check cannot distinguish the two and "
            f"NEITHER a pass nor a fail may be read from it. If that is genuinely true of the "
            f"served model, the variance objection to the swap is itself moot — but verify it on a "
            f"FULL (non-smoke) fit before relying on it, because an undertrained NGBoost compresses "
            f"σ toward a constant.")
    elif not detects:
        verdict = "INSTRUMENT_BLIND"
        reading = (
            f"❌ **NO CONCLUSION MAY BE DRAWN.** The POSITIVE CONTROL — a deliberately flattened copy "
            f"of the heteroscedastic arm — did NOT separate from its parent "
            f"(z = {ctrl_stat['z_score']}, p = {ctrl_stat['p_one_sided']}). The instrument cannot "
            f"detect the very defect it exists to detect, so a clean result from it would be "
            f"vacuous (NF1.7 (a)). Fix the diagnostic before reading anything into the leader.")
    else:
        material = bool(lead_stat["z_score"] is not None and lead_stat["z_score"] >= 2.0)
        share = (obs[leader] / obs[control]) if obs[control] else float("nan")
        verdict_detail["share_of_the_full_flattening_penalty"] = (
            round(float(share), 3) if np.isfinite(share) else None)
        verdict = "VARIANCE_LOSS_MATERIAL" if material else "VARIANCE_LOSS_NOT_MATERIAL"
        reading = (
            f"The instrument is **PROVEN SENSITIVE**: the positive control separates from its "
            f"heteroscedastic parent at z = {ctrl_stat['z_score']} "
            f"(p = {ctrl_stat['p_one_sided']}), so a null here would be informative. "
            + (f"⚠️ **The MH2.1 leader ALSO separates** (z = {lead_stat['z_score']}, "
               f"p = {lead_stat['p_one_sided']}), carrying **{share:.0%}** of the full flattening "
               f"penalty. Its intervals are systematically wrong in a way that varies with game "
               f"volatility — exactly what a totals price is made of. **Do not promote on CRPS "
               f"alone.**"
               if material else
               f"✅ **The MH2.1 leader does NOT separate** (z = {lead_stat['z_score']}, "
               f"p = {lead_stat['p_one_sided']}) — it carries only **{share:.0%}** of the full "
               f"flattening penalty that the control shows is detectable. On this window the "
               f"per-game variance the incumbent models is not buying enough conditional "
               f"calibration to block the swap."))

    result = {
        "story": STORY, "best_alpha": BEST_ALPHA, "target": TARGET, "tier": TIER,
        "seasons": [int(s) for s in seasons], "excluded_seasons": [int(y) for y in exclude_seasons],
        "n_folds": len(folds), "n_rows": int(len(df)), "nominal_coverage": NOMINAL,
        "seed": seed, "snowflake_free": True, "smoke": bool(smoke),
        "verdict": verdict, "verdict_detail": verdict_detail, "reading": reading,
        "profiles": profiles,
        "contract_coverage_by_season": {
            str(k): {"rows": v["rows"], "coverage": v["coverage"],
                     "structurally_absent": v["structurally_absent"]}
            for k, v in contract_coverage_by_season(df, variants["incumbent"]).items()},
    }
    _write(result)
    print(f"\n[{STORY}] VERDICT: {verdict}")
    print(f"[{STORY}] {reading}")
    return result


def _write(r: dict) -> None:
    _ABL.mkdir(parents=True, exist_ok=True)
    _JSON_DIR.mkdir(parents=True, exist_ok=True)
    stem = ("mh2_1_conditional_calibration" + ("_no2020" if r["excluded_seasons"] else "")
            + ("_smoke" if r.get("smoke") else ""))
    (_JSON_DIR / f"{stem}.json").write_text(json.dumps(r, indent=2, default=float))

    sig = r["profiles"]["sigma_stratum"]
    d = r["verdict_detail"]
    a: list[str] = []
    w = a.append
    w("# MH2.1 — conditional calibration: does the homoscedastic winner lose per-game variance?")
    w("")
    w(f"> ⚠️ **Not an edge claim.** `best_alpha = {BEST_ALPHA}`. A calibration diagnostic; it says "
      "nothing about win rate, edge or ROI.")
    w("")
    w("> 💸 **Snowflake-free and network-free** — reads only the local training-matrix parquet "
      "MH2.1's bake-off already cached, and HALTs rather than pulling if it is absent.")
    w("")
    if r.get("smoke"):
        w("> ⚠️ **SMOKE RUN** — rows/estimators capped. A harness check, NOT a result.")
        w("")
    w(f"**VERDICT: `{r['verdict']}`**")
    w("")
    w(r["reading"])
    w("")
    w(f"- Window {r['seasons'][0]}–{r['seasons'][-1]} · {r['n_folds']} purged folds · "
      f"{r['n_rows']:,} rows · nominal central interval {r['nominal_coverage']:.0%}"
      + (f" · seasons excluded: {r['excluded_seasons']}" if r["excluded_seasons"] else ""))
    w(f"- Stratifier: **{d['stratifier']}** · σ coefficient of variation "
      f"**{d['sigma_coefficient_of_variation']:.4f}** · {d['n_permutations']} permutations")
    w("")
    w("## Why CRPS and PIT-KS could not answer this")
    w("")
    w("CRPS is dominated by the MEAN, and PIT-KS is a **MARGINAL** statistic — a homoscedastic model "
      "that over-covers calm games by as much as it under-covers volatile ones has a **flat pooled "
      "PIT** and a clean PIT-KS while being badly miscalibrated CONDITIONALLY. The errors cancel in "
      "the pooled histogram. Stratifying by predicted volatility stops them cancelling.")
    w("")
    w("## The statistic, and why it is a SLOPE and not a RANGE")
    w("")
    w("For a conditionally-calibrated model the standardised residual `z = (y − μ)/σ` has "
      "**Var(z) = 1 in every stratum**. A homoscedastic arm divides by a constant, so Var(z) sits "
      "below 1 where the true spread is small and above 1 where it is large — a graded signal across "
      "σ-deciles, summarised by the OLS **slope** of Var(z) on the stratum index.")
    w("")
    w("⚠️ **The first cut of this script used `max − min` of per-stratum coverage and it did not "
      "work.** That range is noise-dominated and its expectation GROWS with the number of strata: at "
      "~320 rows per decile a *perfectly* calibrated model posts an expected max−min of **0.069** "
      "(p95 0.100), which swallowed every real signal and made the instrument read blind. A range "
      "over k noisy estimates measures k and n, not miscalibration. The slope pools every stratum, "
      "has a null centred at zero, and is tested here by **permuting the stratum labels** — which "
      "destroys the σ↔Var(z) relationship while preserving each arm's marginal z-distribution and "
      "each stratum's size, giving an exact null with no distributional assumption.")
    w("")
    w("## Var(z) by predicted-σ decile — 1.000 everywhere is perfect")
    w("")
    names = list(sig)
    w("| σ decile | mean σ | n | " + " | ".join(f"`{n}`" for n in names) + " |")
    w("|---:|---:|---:|" + "---:|" * len(names))
    n_str = len(sig[names[0]]["strata"])
    for i in range(n_str):
        row0 = sig[names[0]]["strata"][i]
        cells = " | ".join(f"{sig[n]['strata'][i]['var_z']:.3f}" for n in names)
        w(f"| {i} | {row0['mean_sigma']:.3f} | {row0['n']:,} | {cells} |")
    w("")
    w("| statistic | " + " | ".join(f"`{n}`" for n in names) + " |")
    w("|---|" + "---:|" * len(names))
    for label, key in (("**Var(z) slope per decile**", "var_z_slope"),
                       ("pooled Var(z)", "pooled_var_z"),
                       ("pooled coverage", "pooled_coverage"),
                       ("pooled PIT-KS (the blind one)", "pooled_pit_ks"),
                       ("pooled CRPS", "pooled_crps")):
        w(f"| {label} | " + " | ".join(f"{sig[n][key]:+.5f}" if "slope" in key
                                       else f"{sig[n][key]:.4f}" for n in names) + " |")
    w("")
    w("### ⚠️ The anchors — read these BEFORE the leader's numbers")
    w("")
    w(f"- **NEGATIVE CONTROL / MATCHED FOIL** `{ 'plus_eb::ngboost_normal' }` (same features as the "
      f"leader, heteroscedastic) is the baseline; every slope below is stated as a DIFFERENCE from "
      f"it (its own slope: {d['var_z_slope_foil_heteroscedastic']:+.5f}).")
    w(f"- **POSITIVE CONTROL** `plus_eb::ngboost_FLATTENED` — the foil's own means with its per-game "
      f"σ replaced by a constant of the SAME average variance, so it differs in exactly one respect: "
      f"whether σ moves game to game. Slope vs foil **{d['positive_control']['slope_vs_foil']:+.5f}**, "
      f"z = **{d['positive_control']['z_score']}**, p = {d['positive_control']['p_one_sided']}.")
    w(f"- Instrument detects the defect: **{d['instrument_detects_variance_loss']}** — if this were "
      f"False, nothing in this report could be concluded (NF1.7 (a): a check that cannot fail is not "
      f"a check).")
    w(f"- σ coefficient of variation **{d['sigma_coefficient_of_variation']:.4f}** (floor "
      f"{MIN_SIGMA_CV}) — if σ is effectively constant there is no per-game variance to lose and the "
      f"whole question is moot (NF1.9).")
    w(f"- **MH2.1 LEADER** `plus_eb::glm_elasticnet` (homoscedastic): slope vs foil "
      f"**{d['leader']['slope_vs_foil']:+.5f}**, z = **{d['leader']['z_score']}**, "
      f"p = {d['leader']['p_one_sided']}"
      + (f", i.e. **{d['share_of_the_full_flattening_penalty']:.0%}** of the full flattening penalty."
         if d.get("share_of_the_full_flattening_penalty") is not None else "."))
    w("")
    w("Because the foil shares the leader's FEATURES and differs only in its variance model, any gap "
      "between them is attributable to the variance model rather than to the `plus_eb` block "
      "(NF-D15 g′).")
    w("")
    for key, title in (("mean_stratum", "predicted-mean decile"), ("park_stratum", "park tercile")):
        pr = r["profiles"][key]
        w(f"## Secondary stratification — by {title}")
        w("")
        w("| statistic | " + " | ".join(f"`{n}`" for n in names) + " |")
        w("|---|" + "---:|" * len(names))
        for label, kk in (("Var(z) slope", "var_z_slope"), ("pooled coverage", "pooled_coverage")):
            w(f"| {label} | " + " | ".join(f"{pr[n][kk]:+.5f}" if "slope" in kk
                                           else f"{pr[n][kk]:.4f}" for n in names) + " |")
        w("")
    (_ABL / f"{stem}.md").write_text("\n".join(a) + "\n")
    print(f"[{STORY}] report → {(_ABL / f'{stem}.md').relative_to(PROJECT_ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="MH2.1 conditional-calibration check (Snowflake-free)")
    ap.add_argument("--exclude-seasons", type=int, nargs="*", default=[],
                    help="Mirror MH2.1's declared Lock-1 sensitivity, e.g. --exclude-seasons 2020.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--smoke", action="store_true",
                    help="Cap rows/estimators for a fast harness check. NOT a result.")
    args = ap.parse_args()
    run(tuple(args.exclude_seasons or ()), seed=args.seed, smoke=args.smoke)


if __name__ == "__main__":
    main()
