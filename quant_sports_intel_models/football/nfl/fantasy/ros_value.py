"""ros_value.py — NF-ROS1: an in-season REST-OF-SEASON value (preseason prior × 2026 realized).

Pure logic only: the form family, the predictive, the scores and the waiver orderings. No IO, no
`pipeline` import (the E11.23 fast-gate rule) — `run_nf_ros1.py` assembles the frame and runs the
walk-forward; `run_nf_ros1_publish.py` builds the served artifact. Everything here is registered in
`ablation_results/nf_ros1_preregistration.md` (+ amendment 1); a constant below that disagrees with
the registration is a defect, not a tuning choice.

THE FORM (registration §4.1). For a player after week k, with `n` games played, `x̄` realized points
per game, a team that has played `t` games and has `G_rem` REG games left:

    r̂   = (m_r · r0 + n · x̄) / (m_r + n)          # credibility on the per-game RATE
    â   = clip((m_a · a0 + n) / (m_a + t), 0, 1)   # credibility on AVAILABILITY
    ROS = r̂ · â · G_rem

`m = ∞` recovers the prior exactly, so the family NESTS the incumbent (`prior_prorated`), and a fitted
`m` that lands on `∞` is a COLLAPSE — reported as a tie, never as a win.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

# ── registered constants (§3, §4, §6, §7) ─────────────────────────────────────────────────────────
STORY = "NF-ROS1"
SEED = 20260917
POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE", "K")
NOT_EVALUATED_POSITIONS: tuple[str, ...] = ("DST",)
PRESETS: tuple[str, ...] = ("standard", "half_ppr", "full_ppr")
GATE_PRESET = "full_ppr"
EVAL_WEEKS: tuple[int, ...] = tuple(range(1, 13))
PRIOR_SEASONS: tuple[int, ...] = (2019, 2020, 2021, 2022, 2023, 2024, 2025)
EVAL_SEASONS: tuple[int, ...] = (2020, 2021, 2022, 2023, 2024, 2025)
M_GRID: tuple[float, ...] = (0.5, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, math.inf)
LEVELS = np.round(np.arange(1, 20) * 0.05, 2)          # 0.05 … 0.95
Q10_IDX, Q90_IDX = 1, 17
K_BUCKETS: tuple[tuple[int, int], ...] = ((1, 3), (4, 6), (7, 9), (10, 12))
MIN_CELL_RESIDUALS = 40
DECLARED_FIELD_SIZE = 3
FOLD_WINS_REQUIRED = 5          # cv_power.fold_consistency_clause(6)
BH_Q = 0.10
DSR_MIN = 0.95
PBO_MAX = 0.20
PIT_MAX_DECILE_DEV = 0.05
COVERAGE_NOMINAL = 0.80
COVERAGE_TARGET = 0.05
ORACLE_MATERIAL_SHARE = 0.10
ORACLE_P = 0.05
MATCHED_N_TOL = 1e-9
INACTIVE_PAIR_TOL = 1e-4
REPRO_TOL = 1e-9

#: `frontend/lib/fantasy.ts:468` REALIZED_MAX_SEASON_PACE, mirrored (a parity guard pins the two).
#: Full-season pace per 17 games; the per-game cap is value / 17. K is out of that anchor's scope.
REALIZED_MAX_SEASON_PACE: dict[str, float] = {"QB": 471.1, "RB": 512.3, "WR": 435.2, "TE": 414.0}
PACE_GAMES = 17.0

#: §7 — full-PPR 12-team starters (FLEX ignored in the cutoff, declared).
WAIVER_STARTER_CUTOFF: dict[str, int] = {"QB": 12, "RB": 24, "WR": 24, "TE": 12, "K": 12}
WAIVER_K_ROSTERED = 12
WAIVER_SKILL_ROSTERED = 156
WAIVER_TOP_N = 10
WAIVER_ORDERINGS: tuple[str, ...] = ("raw_ros", "starter_vor_ros", "pool_relative", "expected_excess")
WAIVER_PRIMARY = "expected_excess"
WAIVER_FOILS: tuple[str, ...] = ("raw_ros", "starter_vor_ros")

ARMS: tuple[str, ...] = ("eb_rate", "eb_avail", "eb_rate_avail")
PRIMARY_ARM = "eb_rate_avail"
INCUMBENT = "prior_prorated"
DEGENERATES: tuple[str, ...] = ("frozen_full", "naive_pace", "last3_pace", "nihilist_zero",
                                "zero_width", "max_width")
MATCHED_FOIL = "eb_permuted"


class RosError(RuntimeError):
    """A registered precondition failed — the run refuses rather than scoring a different study."""


# ── the form ──────────────────────────────────────────────────────────────────────────────────────
def credibility_rate(r0, n, x_sum, m: float):
    """`(m·r0 + n·x̄)/(m+n)` written on the SUM so `n = 0` needs no division. `m = ∞` ⇒ r0 exactly."""
    r0 = np.asarray(r0, dtype=float)
    n = np.asarray(n, dtype=float)
    x_sum = np.asarray(x_sum, dtype=float)
    if math.isinf(m):
        return r0.copy()
    return (m * r0 + x_sum) / (m + n)


def credibility_avail(a0, n, t, m: float):
    a0 = np.asarray(a0, dtype=float)
    if math.isinf(m):
        return a0.copy()
    n = np.asarray(n, dtype=float)
    t = np.asarray(t, dtype=float)
    return np.clip((m * a0 + n) / (m + t), 0.0, 1.0)


@dataclass(frozen=True)
class FormParams:
    m_r: float
    m_a: float


def form_params(arm: str, m_r: float, m_a: float) -> FormParams:
    """The arm → which channels are live. A dead channel is pinned at ∞ (the prior)."""
    if arm == INCUMBENT:
        return FormParams(math.inf, math.inf)
    if arm == "eb_rate":
        return FormParams(m_r, math.inf)
    if arm == "eb_avail":
        return FormParams(math.inf, m_a)
    if arm in ("eb_rate_avail", MATCHED_FOIL):
        return FormParams(m_r, m_a)
    raise RosError(f"unknown arm {arm!r}")


def ros_point(df: pd.DataFrame, preset: str, p: FormParams, *, prefix: str = "") -> np.ndarray:
    """The ROS point for every row. `prefix` selects the (possibly permuted) realized columns."""
    r = credibility_rate(df[f"r0_{preset}"], df[f"{prefix}n"], df[f"{prefix}xsum_{preset}"], p.m_r)
    a = credibility_avail(df["a0"], df[f"{prefix}n"], df["t"], p.m_a)
    return r * a * df["g_rem"].to_numpy(dtype=float)


def rate_weight(n, m: float):
    """The share of the rate estimate carried by realized production — served, so a consumer can see it."""
    n = np.asarray(n, dtype=float)
    return np.zeros_like(n) if math.isinf(m) else n / (m + n)


def degenerate_point(df: pd.DataFrame, preset: str, name: str) -> np.ndarray:
    if name == "frozen_full":
        return df[f"board_{preset}"].to_numpy(dtype=float)
    if name == "naive_pace":
        n = df["n"].to_numpy(dtype=float)
        s = df[f"xsum_{preset}"].to_numpy(dtype=float)
        return np.where(n > 0, s / np.maximum(n, 1.0), 0.0) * df["g_rem"].to_numpy(dtype=float)
    if name == "last3_pace":
        n = df["last3_n"].to_numpy(dtype=float)
        s = df[f"last3_sum_{preset}"].to_numpy(dtype=float)
        return np.where(n > 0, s / np.maximum(n, 1.0), 0.0) * df["g_rem"].to_numpy(dtype=float)
    if name == "nihilist_zero":
        return np.zeros(len(df))
    raise RosError(f"{name!r} is not a point degenerate")


# ── fitting (§4.3) ────────────────────────────────────────────────────────────────────────────────
def fit_params(df: pd.DataFrame, arm: str, *, prefix: str = "") -> tuple[FormParams, dict]:
    """Grid-search MSE on full-PPR ROS points. Returns params + a small diagnostic dict."""
    y = df[f"y_{GATE_PRESET}"].to_numpy(dtype=float)
    if len(y) == 0:
        raise RosError(f"fit_params({arm}) on an empty frame")
    r_grid = M_GRID if arm in ("eb_rate", "eb_rate_avail", MATCHED_FOIL) else (math.inf,)
    a_grid = M_GRID if arm in ("eb_avail", "eb_rate_avail", MATCHED_FOIL) else (math.inf,)
    g = df["g_rem"].to_numpy(dtype=float)
    rates = {m: credibility_rate(df[f"r0_{GATE_PRESET}"], df[f"{prefix}n"],
                                 df[f"{prefix}xsum_{GATE_PRESET}"], m) for m in r_grid}
    avails = {m: credibility_avail(df["a0"], df[f"{prefix}n"], df["t"], m) for m in a_grid}
    best, best_mse = None, math.inf
    for mr in r_grid:
        for ma in a_grid:
            mse = float(np.mean((rates[mr] * avails[ma] * g - y) ** 2))
            # strict `<` with the grid in ascending order: a tie keeps the SMALLER m (more data-driven);
            # ∞ is last, so a collapse is only chosen when it is strictly better.
            if mse < best_mse - 1e-12:
                best, best_mse = (mr, ma), mse
    p = FormParams(*best)

    def _edge(v, grid):
        # a finite grid END (smallest, or largest finite) — ∞ is reported by the collapse flag
        return len(grid) > 1 and v in (grid[0], grid[-2])

    return p, {"m_r": p.m_r, "m_a": p.m_a, "mse": best_mse,
               "m_r_edge": _edge(p.m_r, r_grid), "m_a_edge": _edge(p.m_a, a_grid),
               # every LIVE channel landed on ∞ ⇒ the arm IS the incumbent (a tie, never a win)
               "collapsed_to_incumbent": all(math.isinf(v) for v in (p.m_r, p.m_a))}


# ── the predictive (§4.3) ─────────────────────────────────────────────────────────────────────────
def k_bucket(k) -> np.ndarray:
    k = np.asarray(k)
    out = np.zeros(len(k), dtype=int)
    for i, (lo, hi) in enumerate(K_BUCKETS):
        out[(k >= lo) & (k <= hi)] = i
    return out


def tercile_edges(pred: np.ndarray) -> np.ndarray:
    return np.quantile(pred, [1 / 3, 2 / 3]) if len(pred) else np.array([0.0, 0.0])


def fit_residual_table(pos, k, pred, y) -> dict:
    """Residual quantiles per (pos, k-bucket, tercile) with the declared fallbacks. Terciles are cut
    per position on the TRAINING predictions and those edges are carried to the test rows."""
    pos = np.asarray(pos)
    kb = k_bucket(k)
    pred = np.asarray(pred, dtype=float)
    res = np.asarray(y, dtype=float) - pred
    table: dict = {"edges": {}, "cell": {}, "kb": {}, "pos": {}}
    for P in np.unique(pos):
        mp = pos == P
        edges = tercile_edges(pred[mp])
        table["edges"][P] = edges
        terc = np.searchsorted(edges, pred[mp], side="right")
        rp, kbp = res[mp], kb[mp]
        table["pos"][P] = np.quantile(rp, LEVELS)
        for b in range(len(K_BUCKETS)):
            mb = kbp == b
            if mb.sum() >= MIN_CELL_RESIDUALS:
                table["kb"][(P, b)] = np.quantile(rp[mb], LEVELS)
            for tt in range(3):
                mc = mb & (terc == tt)
                if mc.sum() >= MIN_CELL_RESIDUALS:
                    table["cell"][(P, b, tt)] = np.quantile(rp[mc], LEVELS)
    return table


def apply_residual_table(table: dict, pos, k, pred) -> tuple[np.ndarray, int]:
    """(n, 19) quantile predictive, floored at 0 and sorted; also the count of fallback rows."""
    pos = np.asarray(pos)
    kb = k_bucket(k)
    pred = np.asarray(pred, dtype=float)
    res = np.empty((len(pred), len(LEVELS)))
    fallbacks = 0
    for P in np.unique(pos):
        if P not in table["pos"]:
            raise RosError(f"no residual table for position {P}")
        mp = np.where(pos == P)[0]
        terc = np.searchsorted(table["edges"][P], pred[mp], side="right")
        for b in np.unique(kb[mp]):
            for tt in np.unique(terc):
                rows = mp[(kb[mp] == b) & (terc == tt)]
                if not len(rows):
                    continue
                q = table["cell"].get((P, int(b), int(tt)))
                if q is None:
                    fallbacks += len(rows)
                    q = table["kb"].get((P, int(b)))
                    if q is None:
                        q = table["pos"][P]
                res[rows] = q
    out = np.sort(np.maximum(pred[:, None] + res, 0.0), axis=1)
    return out, fallbacks


# ── scores ────────────────────────────────────────────────────────────────────────────────────────
def crps_q(y, qgrid: np.ndarray) -> np.ndarray:
    """Per-row CRPS on the 19-level grid: 2 × mean pinball loss (registration §3.1)."""
    y = np.asarray(y, dtype=float)[:, None]
    diff = y - qgrid
    pin = np.maximum(LEVELS * diff, (LEVELS - 1.0) * diff)
    return 2.0 * pin.mean(axis=1)


def coverage80(y, qgrid) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    return (y >= qgrid[:, Q10_IDX]) & (y <= qgrid[:, Q90_IDX])


def randomized_pit(y, qgrid, rng: np.random.Generator) -> np.ndarray:
    """Amendment 1 item 6 (vectorized; identical arithmetic and draws to the per-row form)."""
    y = np.asarray(y, dtype=float)
    q = np.asarray(qgrid, dtype=float)
    n, m = q.shape
    draws = rng.random(n)
    lo = (q < y[:, None]).sum(axis=1)          # searchsorted(q, y, "left")
    hi = (q <= y[:, None]).sum(axis=1)         # searchsorted(q, y, "right")
    u = np.empty(n)
    below = hi == 0
    above = (lo == m) & ~below
    atom = (lo < hi) & ~below & ~above
    inner = ~(below | above | atom)
    u[below] = 0.05 * draws[below]
    u[above] = 0.95 + 0.05 * draws[above]
    a = np.maximum(0.0, LEVELS[np.minimum(lo, m - 1)] - 0.05)
    bb = LEVELS[np.maximum(hi - 1, 0)]
    u[atom] = a[atom] + (bb[atom] - a[atom]) * draws[atom]
    i = np.where(inner)[0]
    li = lo[i]
    x0, x1 = q[i, li - 1], q[i, li]
    f0, f1 = LEVELS[li - 1], LEVELS[li]
    u[i] = f0 + (f1 - f0) * (y[i] - x0) / (x1 - x0)
    return u


def max_decile_dev(u) -> float:
    u = np.asarray(u, dtype=float)
    if len(u) == 0:
        return math.nan
    h = np.histogram(np.clip(u, 0, 1 - 1e-12), bins=10, range=(0, 1))[0] / len(u)
    return float(np.max(np.abs(h - 0.1)))


def expected_excess(qgrid: np.ndarray, cutoff) -> np.ndarray:
    """`E[(X − c)⁺]` over the equal-weight 19-knot predictive (§7)."""
    c = np.asarray(cutoff, dtype=float)[:, None]
    return np.maximum(qgrid - c, 0.0).mean(axis=1)


# ── waiver orderings (§7) ─────────────────────────────────────────────────────────────────────────
def starter_cutoff(values: np.ndarray, pos: np.ndarray) -> dict[str, float]:
    """The S_P-th best value at each position (the predicted OR realized starter cutoff)."""
    out = {}
    for P, s in WAIVER_STARTER_CUTOFF.items():
        v = np.sort(values[pos == P])[::-1]
        out[P] = float(v[s - 1]) if len(v) >= s else (float(v[-1]) if len(v) else 0.0)
    return out


def waiver_scores(ordering: str, ros: np.ndarray, qgrid: np.ndarray, pos: np.ndarray,
                  fa: np.ndarray) -> np.ndarray:
    """Score every row; the caller ranks only the FA rows. `pool_relative` ties are broken by ROS
    (a tiny scaled term, so the tie-break never outranks a real difference)."""
    if ordering == "raw_ros":
        return ros.copy()
    cut = starter_cutoff(ros, pos)
    cvec = np.array([cut.get(P, 0.0) for P in pos])
    if ordering == "starter_vor_ros":
        return ros - cvec
    if ordering == "expected_excess":
        return expected_excess(qgrid, cvec)
    if ordering == "pool_relative":
        best_fa = {P: (float(ros[fa & (pos == P)].max()) if (fa & (pos == P)).any() else 0.0)
                   for P in np.unique(pos)}
        return ros - np.array([best_fa[P] for P in pos]) + 1e-9 * ros
    raise RosError(f"unknown waiver ordering {ordering!r}")


def realized_utility(y: np.ndarray, pos: np.ndarray) -> np.ndarray:
    cut = starter_cutoff(y, pos)
    return np.maximum(0.0, y - np.array([cut.get(P, 0.0) for P in pos]))
