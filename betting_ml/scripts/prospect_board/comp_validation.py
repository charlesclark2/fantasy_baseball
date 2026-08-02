"""comp_validation.py — MLB Edge-E7.13 PHASE 2: does the comp distribution EARN a place in the
projection, or is it display-only?

Pure numpy / pandas, no IO — the fast gate exercises every scoring rule directly. The runner
(`run_e7_13_comp_validation.py`) does the parquet reads and writes the report.

THE QUESTION
------------
Phase 1 ships a comp DISPLAY, which is honest regardless of accuracy. Phase 2 asks the separate,
harder question the §0.5 discipline requires before any comp-derived number may touch a projection:
**does the comp neighbourhood's realized-outcome distribution predict a prospect's realized dynasty
value better than what the board already knows without it?**

═══════════════════════════════════════════════════════════════════════════════════════════════
🧮 THE SELECTION METRIC — AND WHY IT IS NOT MAE
═══════════════════════════════════════════════════════════════════════════════════════════════
The target is **47% exact zeros** (a prospect who never reaches the majors accumulates nothing) and
the surviving 53% is heavily right-skewed. That is the NF-D11 / E7.12 landmine cohort exactly, and
on it **MAE is minimised by pessimism** — a "project zero for everyone" nihilist can beat every real
candidate, so a point-error metric cannot select here.

  * **PRIMARY = CRPS** (continuous ranked probability score) of each arm's full predictive
    distribution. Proper: it grades location AND spread jointly, so neither a nihilist nor a
    hedger can win it.
  * **CONSTRAINT = randomized-PIT flatness** (max decile deviation). The predictive has an ATOM at
    zero and so does the observation, so a plain PIT is degenerate — the randomized version
    (`u = F(y⁻) + v·[F(y) − F(y⁻)]`, `v ~ U(0,1)`) is uniform under a correctly specified discrete
    /mixed predictive and is the only flatness statistic that is well-posed here.
  * **Interval coverage is reported as a FLOOR, never a target** (E2.1-r). On a floored, zero-heavy
    target a coverage TARGET is structurally inverted — hitting 0.80 would require deliberately
    under-covering the right tail (NF1.9 (e)). It is reported and never optimised.

⚖️ **TWO-SIDED ANCHORS, SCORED EVERY RUN** (NF-D11 / NF-D14 (g) — "don't reason about whether the
metric will invert, keep the anchors in the field and READ them"):

  * **ORACLE FLOOR** `oracle_k15` — the same k-NN family, same k, same eligible set, but neighbours
    chosen by proximity in the REALIZED outcome. Nothing may beat it. Matched capacity is the point
    (NF1.7 (b) / NF1.9 (f)): a peeking arm is a floor only at equal family AND equal sample.
  * **DEGENERATE CEILINGS** `all_zero` (a point mass at zero — the nihilist that wins MAE) and
    `marginal` (the pool's unconditional outcome distribution). BOTH must lose. A real arm scoring
    worse than either means the metric is inverted, not that the arm is bad.
  * **MATCHED PLACEBO** `random_k15` — identical machinery, k neighbours drawn at RANDOM. It
    isolates "does SIMILARITY matter" from "does k-NN estimation matter"; the engine beating the
    marginal but not the placebo would mean the neighbourhood adds nothing.

🎏 **MATCHED FOILS, NOT A LEADERBOARD RANK** (NF-D10 (g)). A rank cannot tell a tie from a loss, so
every mechanism claim here is registered as a PAIR differing in exactly one thing:

  * `comp_no_fv_k15`        — the engine minus the scouting grade → is the comp carried by FV?
  * `comp_components_only`  — the performance block alone → do the structural terms add?
  * `fv_bucket`             — **THE INCUMBENT.** The empirical outcome distribution of same-grade,
                              same-position historical prospects. This is what a board already
                              knows with NO similarity engine at all, and it is the bar the comp
                              engine has to clear to earn anything.
  * `blend_comp_fv`         — an equal mixture of the two. The BLEND question in the story's own
                              terms: does the comp distribution ADD over the coarser read?

═══════════════════════════════════════════════════════════════════════════════════════════════
🚨 THE FOLD CEILING — READ THIS BEFORE INTERPRETING ANY VERDICT
═══════════════════════════════════════════════════════════════════════════════════════════════
The comp pool is E7.8's cohort: board seasons **2018–2022**, outcome horizon **3 seasons**.

A STRICTLY-MATURED backtest (a comp's outcome window must have closed before the query's board
date, which is what `matured_pool` enforces in production) admits, at this archive depth:

    query 2022 → pool {2018}          (2018+3 = 2021 < 2022) ✅
    query 2021 → pool {}              (2018+3 = 2021 ≮ 2021)  ✗
    query 2020 → pool {}                                       ✗
    query 2019 → pool {}                                       ✗

**Exactly ONE fold.** A one-fold backtest cannot compute PBO, cannot deflate, and cannot support any
verdict at all. So this harness runs the pre-registered primary under an explicitly RELAXED pool
rule — *any strictly earlier board season* — which yields **4 folds (2019–2022)**.

⚠️ **STATE THE DEVIATION PLAINLY, DO NOT BURY IT.** Under the relaxed rule a 2020 query sees comps
whose outcome windows run to 2021 — knowledge that board did not have. That is hindsight, and it is
why no absolute accuracy number from this harness may be quoted as "the comp engine's accuracy".
Two things bound the damage, and both are load-bearing:

  1. **It is the SHIPPED path that must be clean, and it is.** Production comps the 2026 board
     against 2018–2022, every window closed by 2025. `matured_pool` enforces that and
     `test_prospect_comps.py` pins it. The relaxation exists only inside this backtest.
  2. **Every arm reads the identical pool**, so the hindsight accrues equally to the incumbent, the
     degenerates and the placebo. The HEAD-TO-HEAD — which is the question the story actually asks —
     is therefore still a fair comparison, even though the levels are optimistic.

🔁 **RE-OPEN MECHANICALLY.** Each board season whose 3-year window closes adds one strictly-matured
fold. The 2023 board's window closes after the 2026 season ⇒ **the first strictly-matured 2-fold
backtest becomes possible in 2027**, and 4 folds in 2029. Until then a strictly-matured verdict is
STRUCTURALLY unavailable, exactly as E7.12-S6 recorded for AAA-Statcast — and an unpowered test
reported as a null is worse than not running it.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any, Sequence

import numpy as np
import pandas as pd

from betting_ml.scripts.prospect_board.prospect_comps import (
    COMPONENT_FEATURES,
    FEATURE_WEIGHTS,
    CompConfig,
    find_comps,
    fit_pool_stats,
    tricube_weights,
)

__all__ = [
    "ARM_FIELD",
    "bh_fdr",
    "cluster_bootstrap_pvalue",
    "crps_sample",
    "deflated_sharpe",
    "fold_plan",
    "board_proxy_score",
    "interval_coverage",
    "ordering_arms",
    "ordering_scores",
    "pbo_cscv",
    "pctile",
    "pit_max_decile_deviation",
    "randomized_pit",
    "rank_ic",
    "score_arm",
]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Proper scoring
# ══════════════════════════════════════════════════════════════════════════════════════════════


def crps_sample(samples: np.ndarray, weights: np.ndarray, y: float) -> float:
    """CRPS of a weighted empirical predictive against a scalar observation.

        CRPS = E|X − y| − ½·E|X − X'|

    Both terms are computed exactly from the weighted sample (no Monte-Carlo), so the score is
    deterministic — a stochastic selection metric would make the deflation statistics meaningless.
    """
    s = np.asarray(samples, dtype=float)
    w = np.asarray(weights, dtype=float)
    ok = np.isfinite(s) & np.isfinite(w) & (w > 0)
    s, w = s[ok], w[ok]
    if s.size == 0 or not np.isfinite(y):
        return float("nan")
    w = w / w.sum()
    term1 = float(np.sum(w * np.abs(s - float(y))))
    # ½·E|X−X'| via the sorted-CDF identity: ∫F(1−F) = Σ over sorted gaps
    order = np.argsort(s)
    ss, ws = s[order], w[order]
    cw = np.cumsum(ws)[:-1]
    term2 = float(np.sum(np.diff(ss) * cw * (1.0 - cw)))
    return term1 - term2


def randomized_pit(samples: np.ndarray, weights: np.ndarray, y: float,
                   rng: np.random.Generator) -> float:
    """`u = F(y⁻) + v·[F(y) − F(y⁻)]`, `v ~ U(0,1)` — uniform under a correct mixed predictive.

    The plain PIT is degenerate here: both the predictive and the observation put a large atom at
    exactly zero, so `F(y)` jumps and the raw transform piles up at the jump. Randomizing across the
    jump is the standard, and the only well-posed, flatness statistic for this target.
    """
    s = np.asarray(samples, dtype=float)
    w = np.asarray(weights, dtype=float)
    ok = np.isfinite(s) & np.isfinite(w) & (w > 0)
    s, w = s[ok], w[ok]
    if s.size == 0 or not np.isfinite(y):
        return float("nan")
    w = w / w.sum()
    lo = float(np.sum(w[s < y]))
    hi = float(np.sum(w[s <= y]))
    return lo + float(rng.random()) * (hi - lo)


def pit_max_decile_deviation(pits: np.ndarray) -> float:
    """Max |observed − 0.10| decile frequency. 0 = perfectly flat."""
    p = np.asarray(pits, dtype=float)
    p = p[np.isfinite(p)]
    if p.size == 0:
        return float("nan")
    counts, _ = np.histogram(np.clip(p, 0, 1), bins=10, range=(0.0, 1.0))
    return float(np.max(np.abs(counts / p.size - 0.10)))


def interval_coverage(lo: np.ndarray, hi: np.ndarray, y: np.ndarray) -> float:
    """Empirical coverage. ⚠️ REPORTED AS A FLOOR, NEVER MINIMISED TOWARD A TARGET (E2.1-r)."""
    lo, hi, y = (np.asarray(a, dtype=float) for a in (lo, hi, y))
    ok = np.isfinite(lo) & np.isfinite(hi) & np.isfinite(y)
    return float(np.mean((y[ok] >= lo[ok]) & (y[ok] <= hi[ok]))) if ok.any() else float("nan")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Deflation
# ══════════════════════════════════════════════════════════════════════════════════════════════


def pbo_cscv(fold_scores: np.ndarray) -> dict[str, Any]:
    """Probability of Backtest Overfitting by combinatorially-symmetric CV (Bailey et al.).

    `fold_scores` is (n_folds, n_arms) of a score where LOWER IS BETTER (CRPS). Splits the folds
    into every balanced in-/out-of-sample pair, picks the in-sample winner and reads its
    out-of-sample rank; PBO = P(the in-sample winner lands in the bottom half out of sample).

    Also returns the two statistics NF1.8 requires beside it, because PBO alone cannot tell an
    unstable pick from a TIE:
      * `flip_distribution` — which arm wins each in-sample half, and how often. Mass concentrated
        on two arms a fraction of a percent apart IS a tie; mass spread thinly over a dozen
        unrelated arms is a search that learnt nothing.
      * `performance_degradation` — Bailey's median out-of-sample gap between the in-sample winner
        and the out-of-sample best. This asks the decision-relevant question ("did picking it COST
        anything?") rather than the rank question.
    """
    s = np.asarray(fold_scores, dtype=float)
    n_folds, n_arms = s.shape
    if n_folds < 4:
        return {"pbo": None, "n_splits": 0, "computable": False,
                "reason": f"CSCV needs >=4 folds, got {n_folds}"}
    half = n_folds // 2
    ranks, degradations, winners = [], [], []
    for combo in combinations(range(n_folds), half):
        is_idx = list(combo)
        oos_idx = [i for i in range(n_folds) if i not in combo]
        is_mean = np.nanmean(s[is_idx], axis=0)
        oos_mean = np.nanmean(s[oos_idx], axis=0)
        w = int(np.nanargmin(is_mean))
        winners.append(w)
        r = float(np.sum(oos_mean < oos_mean[w])) / max(n_arms - 1, 1)   # share strictly better
        ranks.append(r)
        degradations.append(float(oos_mean[w] - np.nanmin(oos_mean)))
    ranks = np.asarray(ranks)
    return {
        "pbo": float(np.mean(ranks > 0.5)),
        "n_splits": len(ranks),
        "computable": True,
        "median_oos_rank_of_is_winner": float(np.median(ranks)),
        "performance_degradation": float(np.median(degradations)),
        "flip_distribution": {int(k): int(v) for k, v in
                              zip(*np.unique(winners, return_counts=True))},
    }


def deflated_sharpe(scores: np.ndarray, n_trials: int, n_obs: int) -> float:
    """Bailey/Lopez de Prado DSR of the best arm against a field of `n_trials`.

    `scores` = per-observation SKILL (higher better) of the winning arm; the expected-max term uses
    the field's trial dispersion. ⚠️ Report BOTH the whole-field and the contender-set value and
    pre-register which binds (NF-D14): a field containing its own deliberate nulls has a huge
    dispersion, so a whole-field DSR measures the NULLS, not the contest.
    """
    from scipy.stats import norm
    x = np.asarray(scores, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 8 or x.std(ddof=1) == 0:
        return float("nan")
    sr = float(x.mean() / x.std(ddof=1))
    gamma = 0.5772156649
    e_max = ((1 - gamma) * norm.ppf(1 - 1.0 / max(n_trials, 2))
             + gamma * norm.ppf(1 - 1.0 / (max(n_trials, 2) * np.e)))
    sk = float(pd.Series(x).skew())
    ku = float(pd.Series(x).kurtosis()) + 3.0
    denom = np.sqrt(max(1 - sk * sr + (ku - 1) / 4.0 * sr ** 2, 1e-9))
    z = (sr - e_max / np.sqrt(max(n_obs, 2))) * np.sqrt(max(n_obs - 1, 1)) / denom
    return float(norm.cdf(z))


def bh_fdr(pvalues: Sequence[float], alpha: float = 0.05) -> dict[str, Any]:
    """Benjamini–Hochberg. Returns the cutoff and the reject mask, both reported."""
    p = np.asarray(list(pvalues), dtype=float)
    m = len(p)
    if m == 0:
        return {"cutoff": None, "reject": [], "alpha": alpha}
    order = np.argsort(p)
    thresh = alpha * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    k = int(np.max(np.flatnonzero(passed)) + 1) if passed.any() else 0
    cutoff = float(thresh[k - 1]) if k else float(thresh[0])
    reject = np.zeros(m, dtype=bool)
    if k:
        reject[order[:k]] = True
    return {"cutoff": cutoff, "reject": reject.tolist(), "alpha": alpha, "n_tests": m}


def cluster_bootstrap_pvalue(diff: np.ndarray, cluster: np.ndarray, *, n_boot: int = 2000,
                             seed: int = 0) -> dict[str, float]:
    """Two-sided p-value + CI for `mean(diff) < 0`, resampling CLUSTERS not rows.

    A player appears in several board seasons, so his rows are not independent draws — the NF1.8
    per-group lesson, one level over. Clustering on the person is what stops the CI being a
    function of how long each prospect stayed on the board.
    """
    d = np.asarray(diff, dtype=float)
    c = np.asarray(cluster)
    ok = np.isfinite(d)
    d, c = d[ok], c[ok]
    if d.size == 0:
        return {"mean": float("nan"), "p_value": float("nan"), "ci_lo": float("nan"),
                "ci_hi": float("nan")}
    keys, inv = np.unique(c, return_inverse=True)
    groups = [d[inv == i] for i in range(len(keys))]
    rng = np.random.default_rng(seed)
    obs = float(np.mean(d))
    boots = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        boots[b] = float(np.mean(np.concatenate([groups[i] for i in pick])))
    centred = boots - obs
    p = float(np.mean(np.abs(centred) >= abs(obs)))
    return {"mean": obs, "p_value": p, "ci_lo": float(np.quantile(boots, 0.025)),
            "ci_hi": float(np.quantile(boots, 0.975)), "n_clusters": int(len(keys))}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The arm field
# ══════════════════════════════════════════════════════════════════════════════════════════════


def _reweighted(player_type: str, drop: Sequence[str]) -> dict[str, float]:
    """A matched foil's weights: identical set minus `drop`, renormalized. Everything else is
    byte-identical, which is what makes the paired delta attributable (NF-D10 (g))."""
    w = {k: v for k, v in FEATURE_WEIGHTS[player_type].items() if k not in set(drop)}
    tot = sum(w.values())
    return {k: v / tot for k, v in w.items()}


@dataclass(frozen=True)
class Arm:
    name: str
    kind: str            # 'comp' | 'bucket' | 'blend' | 'degenerate' | 'anchor' | 'placebo'
    selectable: bool     # counted in the contender set / the selection
    cfg: dict[str, Any] = None


#: PRE-REGISTERED before any score was read. `selectable` marks the CONTENDER set — the arms a
#: selection could actually pick. The anchors and degenerates are scored every run and MUST land on
#: their pre-registered side; they are not candidates.
ARM_FIELD: tuple[Arm, ...] = (
    Arm("comp_gower_k15", "comp", True, {"k": 15}),
    Arm("comp_gower_k10", "comp", True, {"k": 10}),
    Arm("comp_gower_k25", "comp", True, {"k": 25}),
    #: the matched foil for the similarity KERNEL: identical neighbourhood, weighted instead of
    #: equal. This pair is what measured that the kernel over-sharpens (see CompConfig).
    Arm("comp_gower_k15_simweighted", "comp", True, {"k": 15, "similarity_weighted": True}),
    Arm("comp_mahalanobis_k15", "comp", True, {"k": 15, "metric": "mahalanobis"}),
    Arm("comp_no_fv_k15", "comp", True, {"k": 15, "drop": ("fv",)}),
    Arm("comp_components_only_k15", "comp", True,
        {"k": 15, "drop": ("fv", "age_vs_level", "level_rank", "pro_experience_years")}),
    Arm("fv_bucket", "bucket", True, None),
    Arm("blend_comp_fv", "blend", True, {"k": 15}),
    Arm("random_k15", "placebo", False, {"k": 15, "neighbour_rule": "random"}),
    Arm("marginal", "degenerate", False, None),
    Arm("all_zero", "degenerate", False, None),
    Arm("oracle_k15", "anchor", False, {"k": 15, "neighbour_rule": "oracle"}),
)


def fold_plan(pool: pd.DataFrame, *, strict: bool) -> list[dict[str, Any]]:
    """Forward-chained folds. `strict` = the production maturity rule; see the module docstring.

    Returned in ascending query season so the report reads chronologically.
    """
    seasons = sorted(int(s) for s in pool["board_season"].dropna().unique())
    horizon = int(pd.to_numeric(pool["horizon_seasons"], errors="coerce").max() or 3)
    plan = []
    for s in seasons:
        if strict:
            train = [t for t in seasons if t + horizon < s]
        else:
            train = [t for t in seasons if t < s]
        if train:
            plan.append({"query_season": s, "train_seasons": train,
                         "n_query": int((pool["board_season"] == s).sum()),
                         "n_train": int(pool["board_season"].isin(train).sum())})
    return plan


def _bucket_samples(train: pd.DataFrame, query: pd.DataFrame, *,
                    by: Sequence[str]) -> list[tuple[np.ndarray, np.ndarray]]:
    """The INCUMBENT: the empirical outcome distribution of same-bucket historical prospects.

    Bucketed on the FV grade (rounded to the 5-point scouting grid it is actually reported on) and
    the position group. A bucket thinner than 10 players falls back to the whole player type — an
    honest widening, recorded, rather than a distribution off three careers.
    """
    out = []
    grp = {k: g["fantasy_points"].to_numpy(float) for k, g in train.groupby(list(by), dropna=False)}
    allfp = train["fantasy_points"].to_numpy(float)
    for _, row in query.iterrows():
        key = tuple(row.get(b) for b in by)
        s = grp.get(key if len(key) > 1 else key[0], None)
        if s is None or len(s) < 10:
            s = allfp
        out.append((s, np.ones(len(s), dtype=float)))
    return out


def _fv_bucket_col(df: pd.DataFrame) -> pd.Series:
    """FV on its native 5-point grid; NaN → its own bucket rather than a fabricated grade."""
    fv = pd.to_numeric(df.get("fv"), errors="coerce")
    return (fv / 5.0).round() * 5.0


def score_arm(arm: Arm, train: pd.DataFrame, query: pd.DataFrame, *, player_type: str,
              seed: int = 0) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Return (samples, weights) per query row — the arm's predictive distribution.

    Every arm returns the same object shape, which is what lets one scorer grade all of them and
    keeps the comparison paired at the row level.
    """
    n = len(query)
    if arm.kind == "degenerate":
        if arm.name == "all_zero":
            return [np.zeros(1)] * n, [np.ones(1)] * n
        fp = train["fantasy_points"].to_numpy(float)
        return [fp] * n, [np.ones(len(fp))] * n

    if arm.kind == "bucket":
        tr = train.assign(_fvb=_fv_bucket_col(train))
        q = query.assign(_fvb=_fv_bucket_col(query))
        pairs = _bucket_samples(tr, q, by=("_fvb", "position_group"))
        return [p[0] for p in pairs], [p[1] for p in pairs]

    if arm.kind == "blend":
        a = Arm("comp_gower_k15", "comp", True, {"k": 15})
        s_c, w_c = score_arm(a, train, query, player_type=player_type, seed=seed)
        s_b, w_b = score_arm(Arm("fv_bucket", "bucket", True, None), train, query,
                             player_type=player_type, seed=seed)
        samples, weights = [], []
        for sc, wc, sb, wb in zip(s_c, w_c, s_b, w_b):
            # equal MIXTURE weight on the two predictives, not on the two sample counts — otherwise
            # the larger bucket sample would silently dominate the mixture
            if sc.size == 0:
                samples.append(sb); weights.append(wb); continue
            samples.append(np.concatenate([sc, sb]))
            weights.append(np.concatenate([0.5 * wc / wc.sum(), 0.5 * wb / wb.sum()]))
        return samples, weights

    # --- comp / placebo / oracle: all the same k-NN machinery, differing only where registered ---
    cfg_kw = dict(arm.cfg or {})
    drop = cfg_kw.pop("drop", ())
    weights_map = _reweighted(player_type, drop) if drop else None
    cfg = CompConfig(
        k=int(cfg_kw.pop("k", 15)),
        metric=str(cfg_kw.pop("metric", "gower")),
        neighbour_rule=str(cfg_kw.pop("neighbour_rule", "nearest")),
        similarity_weighted=bool(cfg_kw.pop("similarity_weighted",
                                            CompConfig.similarity_weighted)),
        weights=weights_map,
        features=tuple(weights_map) if weights_map else None,
        component_features=tuple(f for f in COMPONENT_FEATURES[player_type]
                                 if weights_map is None or f in weights_map) or None,
        name=arm.name, seed=seed, **cfg_kw)
    stats = fit_pool_stats(train, player_type=player_type,
                           features=cfg.features, weights=cfg.weights)
    _, detail = find_comps(query, train, stats, cfg,
                           query_outcome_col=("fantasy_points" if arm.name.startswith("oracle")
                                              else None))
    samples = [np.empty(0)] * n
    weights = [np.empty(0)] * n
    if not detail.empty:
        for qi, grp in detail.groupby("query_index"):
            fp = grp["comp_fantasy_points"].to_numpy(float)
            d = grp["distance"].to_numpy(float)
            samples[int(qi)] = fp
            weights[int(qi)] = tricube_weights(d) if cfg.similarity_weighted else np.ones(len(fp))
    return samples, weights


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. THE ORDERING STUDY — the statistic that actually governs a draft board
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# 🚨 CRPS AND RANK-IC ARE DIFFERENT QUESTIONS, AND ONLY ONE OF THEM GOVERNS A BOARD.
# Everything above grades a PREDICTIVE DISTRIBUTION: given this prospect, how well-calibrated is
# the outcome distribution we put on him? That is the right question for a projection term. It is
# NOT the question a draft board asks, which is purely ORDINAL — of these two players, who should I
# take first? An arm can win CRPS by being better CALIBRATED (sharper where it should be sharp,
# wider where it should be wide) while ordering players no better than the incumbent, because CRPS
# rewards the width of the band and a ranking cannot see the band at all.
#
# So a comp term may NOT enter `blend_score` on the strength of the CRPS result. This section
# measures the ordinal statistic directly: **Spearman rank-IC against realized dynasty value**,
# same folds, same clustering, same deflation, same two-sided anchors.
#
# ⚖️ THE INCUMBENT IS THE BOARD'S OWN FORMULA, NOT FV. `board_proxy` reconstructs
# `board_assembly.attach_scores` on the historical cohort using the SAME constants
# (`FV_WEIGHT_BY_TYPE`, `MLE_METRIC_WEIGHTS`, `AGE_WEIGHT_IN_MODEL_SCORE`), so the question asked is
# the operational one — "does adding comps improve the ordering the board ALREADY produces?" —
# rather than the easier "do comps beat a bare scouting grade?".
#
# ⚠️ STATED DEVIATION: the historical cohort carries the RAW MiLB component line but not E7.3's
# TRANSLATED line, so `board_proxy`'s `mle_score` is built from the raw components under the same
# weights and directions rather than from the MLE output. It is a PROXY for the board's `mle_score`
# and is labelled as one everywhere. It preserves the ordering content of the component block (the
# translation is close to monotone within a level) but it is not byte-identical to what the live
# board computes, so a small residual mis-attribution between the comp term and the MLE term is
# possible. It cannot be removed without an E7.3 back-projection of every historical board season.

#: Pre-registered comp→score forms. Both counted as configs toward the deflation.
COMP_SCORE_FORMS: tuple[str, ...] = ("comp_mean_fp", "comp_median_fp")
#: Pre-registered blend weights for the comp term inside `blend_score`.
COMP_BLEND_WEIGHTS: tuple[float, ...] = (0.10, 0.20, 0.30, 0.40)


def pctile(s: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Percentile rank in [0, 100], mirroring `board_assembly._pctile`'s semantics."""
    v = pd.to_numeric(s, errors="coerce")
    r = v.rank(pct=True, na_option="keep")
    return (r if higher_is_better else 1.0 - r) * 100.0


def board_proxy_score(df: pd.DataFrame, player_type: str) -> pd.DataFrame:
    """Reconstruct the board's `blend_score` on the historical cohort. See the section note.

    Mirrors `board_assembly.attach_scores`: a per-metric weighted percentile composite (weights =
    E7.3's out-of-sample translation correlations, direction per metric), blended with
    age-relative-to-level at `AGE_WEIGHT_IN_MODEL_SCORE`, then blended with the scouting grade at
    `FV_WEIGHT_BY_TYPE`.
    """
    from betting_ml.scripts.prospect_board.board_assembly import (
        AGE_WEIGHT_IN_MODEL_SCORE, FV_WEIGHT_BY_TYPE, MLE_METRIC_WEIGHTS,
    )
    out = pd.DataFrame(index=df.index)
    # the live board reads `mle_<metric>`; the cohort carries the raw `minor_<metric>` (see the
    # stated deviation above). Same metrics, same weights, same directions.
    spec = {k.replace("mle_p_", "minor_").replace("mle_", "minor_"): v
            for k, v in MLE_METRIC_WEIGHTS[player_type].items()}
    num = pd.Series(0.0, index=df.index)
    den = pd.Series(0.0, index=df.index)
    for metric, (w, higher) in spec.items():
        if metric not in df.columns:
            continue
        p = pctile(df[metric], higher_is_better=higher)
        ok = p.notna()
        num = num.add((p * w).where(ok, 0.0), fill_value=0.0)
        den = den.add(pd.Series(np.where(ok, w, 0.0), index=df.index), fill_value=0.0)
    out["mle_score"] = np.where(den > 0, num / den.replace(0, np.nan), np.nan)

    lvl_med = df.groupby("level_rank")["age"].transform("median")
    out["age_score"] = pctile(df["age"] - lvl_med, higher_is_better=False)
    out["fv_pctile"] = pctile(df["fv"], higher_is_better=True)

    model = (out["mle_score"] * (1 - AGE_WEIGHT_IN_MODEL_SCORE)
             + out["age_score"] * AGE_WEIGHT_IN_MODEL_SCORE)
    out["model_score"] = model.where(out["mle_score"].notna() & out["age_score"].notna(),
                                     out["mle_score"].fillna(out["age_score"]))
    fv_w = FV_WEIGHT_BY_TYPE[player_type]
    blend = fv_w * out["fv_pctile"] + (1 - fv_w) * out["model_score"]
    out["blend_score"] = blend.where(out["fv_pctile"].notna() & out["model_score"].notna(),
                                     out["fv_pctile"].fillna(out["model_score"]))
    return out


def rank_ic(score: np.ndarray, y: np.ndarray) -> float:
    """Spearman rank correlation of a score against the realized outcome. NaN-safe."""
    from scipy.stats import spearmanr
    s, t = np.asarray(score, dtype=float), np.asarray(y, dtype=float)
    ok = np.isfinite(s) & np.isfinite(t)
    if ok.sum() < 10 or np.unique(s[ok]).size < 2:
        return float("nan")
    return float(spearmanr(s[ok], t[ok]).statistic)


def ordering_arms(comp_form: str) -> dict[str, str]:
    """The pre-registered ordering field. Anchors keyed by name so the runner can read them."""
    arms = {"fv_only": "contender", "board_proxy": "incumbent", "comp_only": "contender"}
    arms.update({f"board_plus_comp_w{int(w * 100):02d}": "contender" for w in COMP_BLEND_WEIGHTS})
    arms.update({"oracle_order": "anchor", "random_order": "placebo"})
    return arms


def ordering_scores(base: pd.DataFrame, comp_pct: pd.Series, y: np.ndarray,
                    rng: np.random.Generator) -> dict[str, np.ndarray]:
    """Every ordering arm's score vector for one fold."""
    bp = base["blend_score"].to_numpy(float)
    cp = comp_pct.to_numpy(float)
    out = {
        "fv_only": base["fv_pctile"].to_numpy(float),
        "board_proxy": bp,
        "comp_only": cp,
        # 🎯 the peeking floor: ordering BY the realized outcome. IC is 1.0 by construction and
        # nothing may beat it — the inversion check for a rank statistic.
        "oracle_order": np.asarray(y, dtype=float),
        # 🎲 the matched placebo: same machinery, ordering destroyed.
        "random_order": rng.permutation(bp),
    }
    for w in COMP_BLEND_WEIGHTS:
        # a row with no comps keeps the board's own score rather than dropping out of the ranking —
        # the same rule `attach_scores` already applies to an un-projected player.
        mixed = (1 - w) * bp + w * cp
        out[f"board_plus_comp_w{int(w * 100):02d}"] = np.where(np.isfinite(cp), mixed, bp)
    return out

