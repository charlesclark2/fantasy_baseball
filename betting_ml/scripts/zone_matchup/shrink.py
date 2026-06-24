"""E13.10 empirical-Bayes shrinkage for the per-cell profiles — PURE logic (unit-tested).

Zone × pitch-group × handedness cells are SPARSE (a hitter sees only a few dozen sliders
low-and-away all year), so a raw per-cell rate is mostly variance. We shrink HARD toward a
tiered prior — the same discipline E13.4 §5 and the E13.7 cold-start baseline use:

    value' = (n · raw + k · prior) / (n + k)          (mean of a continuous quantity)
    rate'  = (succ + k · prior_rate) / (tot + k)        (a binomial rate, e.g. whiff%)

The prior is resolved by FALLBACK: a cell's own (hand, group, cell) league mean, then the
(hand, group) marginal, then the global mean — so a never-before-seen cell still gets a sane,
honest value. `k` is the pseudo-count: larger ⇒ shrink harder (cells get k≈big because sparse).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Pseudo-counts (HEAVY by default — cells are sparse, per E13.10).
K_VALUE = 120.0     # run-value mean shrink strength (pitches)
K_RATE = 150.0      # whiff/contact-rate shrink strength (swings/pitches)
K_XWOBA = 60.0      # xwOBA-on-contact shrink strength (batted balls)


def eb_mean(raw: np.ndarray, n: np.ndarray, prior: np.ndarray, k: float) -> np.ndarray:
    """Shrink a per-cell continuous mean `raw` (over `n` obs) toward `prior` by pseudo-count `k`.
    n=0 or NaN raw → collapses to prior."""
    raw = np.asarray(raw, float)
    n = np.where(np.isnan(np.asarray(n, float)), 0.0, np.clip(np.asarray(n, float), 0.0, None))
    prior = np.asarray(prior, float)
    safe_raw = np.where(np.isnan(raw), 0.0, raw)
    return (n * safe_raw + k * prior) / (n + k)


def eb_rate(succ: np.ndarray, tot: np.ndarray, prior_rate: np.ndarray, k: float) -> np.ndarray:
    """Shrink a per-cell binomial rate (succ/tot) toward `prior_rate` by pseudo-count `k`.
    tot=0 → collapses to prior_rate."""
    succ = np.where(np.isnan(np.asarray(succ, float)), 0.0, np.asarray(succ, float))
    tot = np.where(np.isnan(np.asarray(tot, float)), 0.0, np.clip(np.asarray(tot, float), 0.0, None))
    prior_rate = np.asarray(prior_rate, float)
    return (succ + k * prior_rate) / (tot + k)


def tiered_prior(df: pd.DataFrame, value_col: str, weight_col: str,
                 keys: tuple[str, ...] = ("p_hand", "pgroup")) -> dict:
    """Build a fallback-prior lookup from a league-aggregated frame.

    Returns {"by_keys": {tuple→value}, "by_group": {(hand,group)→value}, "global": float} where
    each level is the weight-averaged `value_col`. Consumers fall back keys → group → global so a
    cell with no league history still resolves to the marginal/global mean.
    """
    d = df.copy()
    d[value_col] = pd.to_numeric(d[value_col], errors="coerce")
    d[weight_col] = pd.to_numeric(d[weight_col], errors="coerce").fillna(0.0)
    d = d[d[value_col].notna() & (d[weight_col] > 0)]

    def _wavg(g: pd.DataFrame) -> float:
        w = g[weight_col].to_numpy(float)
        v = g[value_col].to_numpy(float)
        return float(np.sum(w * v) / np.sum(w)) if np.sum(w) > 0 else float("nan")

    by_keys = {tuple(k if isinstance(k, tuple) else (k,)): _wavg(g)
               for k, g in d.groupby(list(keys))}
    grp_keys = [c for c in ("p_hand", "pgroup", "b_hand") if c in keys]
    by_group = {tuple(k if isinstance(k, tuple) else (k,)): _wavg(g)
                for k, g in d.groupby(grp_keys)} if grp_keys else {}
    glob = _wavg(d)
    return {"by_keys": by_keys, "by_group": by_group, "global": glob, "keys": keys,
            "group_keys": grp_keys}


def resolve_prior(prior: dict, key_tuple: tuple, group_tuple: tuple) -> float:
    """Fallback lookup: exact keys → group marginal → global."""
    v = prior["by_keys"].get(key_tuple)
    if v is not None and not (isinstance(v, float) and np.isnan(v)):
        return v
    v = prior["by_group"].get(group_tuple)
    if v is not None and not (isinstance(v, float) and np.isnan(v)):
        return v
    return prior["global"]
