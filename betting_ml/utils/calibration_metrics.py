"""Canonical calibration primitives — reliability curve + ECE + Brier (E9.26).

One implementation of the classification-calibration metrics so the per-market
reliability artifact, the H2H audit and any future surface agree on the bin-edge
convention (the repo had ~4 slightly-divergent copies; this is the blessed one).

All functions are pure and numpy-only — no Snowflake, no serving cache — so they
unit-test cleanly and can be fed probabilities from any source (the E9.26 artifact
feeds them per-market probs read from the serving-cache game-detail blobs).

Convention (matches betting_ml/scripts/h2h_calibration_audit_e13_6.py): 10 equal-
width bins on [0, 1], half-open [lo, hi) except the last bin includes 1.0.
"""

from __future__ import annotations

import numpy as np

_EPS = 1e-6


def brier(p: np.ndarray, y: np.ndarray) -> float:
    """Mean squared error of the probability vs the binary outcome."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    return float(np.mean((p - y) ** 2))


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(np.asarray(p, float), _EPS, 1 - _EPS)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def ece(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error — |confidence − accuracy| weighted by bin population."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    n = len(p)
    if n == 0:
        return float("nan")
    bins = np.linspace(0, 1, n_bins + 1)
    out = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.sum() == 0:
            continue
        out += (m.sum() / n) * abs(p[m].mean() - y[m].mean())
    return float(out)


def reliability_table(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> list[dict]:
    """Per-bin reliability rows: predicted vs observed frequency."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    bins = np.linspace(0, 1, n_bins + 1)
    rows: list[dict] = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.sum() == 0:
            continue
        rows.append({
            "bin_lo": round(float(lo), 2),
            "bin_hi": round(float(hi), 2),
            "n": int(m.sum()),
            "avg_pred": round(float(p[m].mean()), 4),
            "avg_actual": round(float(y[m].mean()), 4),
        })
    return rows


def metric_block(p: np.ndarray, y: np.ndarray) -> dict:
    """Summary calibration/discrimination block for one (prob, outcome) set."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    n = int(len(p))
    if n == 0:
        return {"n": 0, "brier": None, "log_loss": None, "ece": None,
                "spread": None, "mean_pred": None, "base_rate": None, "corr": None}
    spread = float(np.std(p))
    return {
        "n": n,
        "brier": round(brier(p, y), 4),
        "log_loss": round(log_loss(p, y), 4),
        "ece": round(ece(p, y), 4),
        "spread": round(spread, 4),
        "mean_pred": round(float(np.mean(p)), 4),
        "base_rate": round(float(np.mean(y)), 4),
        "corr": round(float(np.corrcoef(p, y)[0, 1]), 4) if spread > 0 and np.std(y) > 0 else 0.0,
    }
