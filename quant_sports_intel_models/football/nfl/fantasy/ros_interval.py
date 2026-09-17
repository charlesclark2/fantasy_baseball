"""ros_interval.py — NF-ROS1b: the HURDLE predictive for the rest-of-season value.

Pure logic only (no IO, no `pipeline` import — the E11.23 fast-gate rule). Registered in
`ablation_results/nf_ros1b_preregistration.md` §2–§3 (+ amendment 1). A constant here that disagrees
with the registration is a defect, not a tuning choice; nothing here may change after a result.

THE FAMILY (§2.2). For a row with point `ŷ ≥ 0` (the predictor's own point, unchanged) and a
player-specific atom `π = P(Y ≤ 0)`, the quantile at each grid level `τ` is

    q(τ) = 0                                   if τ ≤ π  or  ŷ = 0
    q(τ) = ŷ · Qε_cell((τ − π) / (1 − π))      otherwise

where `Qε_cell` is the empirical quantile function of the ratio `ε = y / ŷ` on training rows with
`ŷ > 0` and `y > 0`, stored on a 199-level grid, interpolated linearly and clamped at its end knots.
The spread therefore scales with the projection by construction, and the atom is per player.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import ros_value as V

STORY = "NF-ROS1b"
INTERVAL_NAME = "hurdle"
LOCATION_SHIFT = "location_shift"

#: §2.2 — the ratio distribution's storage grid (0.005 … 0.995).
FINE_LEVELS = np.round(np.arange(1, 200) * 0.005, 3)

#: §2.3 — the logistic hurdle, fixed.
LOGIT_C = 1.0
LOGIT_MAX_ITER = 2000
PI_FEATURES: tuple[str, ...] = ("a0", "share_played", "no_games", "miss_streak", "log_g_rem",
                                "log_r0", "rookie", "kb_4_6", "kb_7_9", "kb_10_12")

#: amendment 1 item 2 — the reference arm's key and its label.
REFERENCE_KEY = "reference_only_winner_at_location_shift"
REFERENCE_LABEL = "reference only — not a trial, not in V, gates nothing"

#: §8 / amendment 1 item 1 — the name-join outcome taxonomy.
JOIN_OUTCOMES: tuple[str, ...] = ("CORRECT", "WRONG", "MISSED", "CORRECT_ABSENT", "UNVERIFIABLE")


# ── §3.2 miss_streak ──────────────────────────────────────────────────────────────────────────────
def miss_streak(frame: pd.DataFrame, n_col: str = "n") -> pd.Series:
    """The current run of team games the player has not appeared in, through k (rows ≤ k only).

    Per (season, player_id), ordered by k, with n(0) = t(0) = 0:
      team_played(k) = t(k) > t(k−1);  played(k) = n(k) > n(k−1)
      streak = 0 if played; +1 if the team played and he did not; unchanged on a bye.
    A missing k carries the previous available row (it simply is not in the ordered sequence)."""
    out = pd.Series(0, index=frame.index, dtype=float)
    order = frame.sort_values(["season", "player_id", "k"])
    for _, g in order.groupby(["season", "player_id"], sort=False):
        n = g[n_col].to_numpy(dtype=float)
        t = g["t"].to_numpy(dtype=float)
        pn = np.concatenate([[0.0], n[:-1]])
        pt = np.concatenate([[0.0], t[:-1]])
        s = 0.0
        vals = np.empty(len(g))
        for i in range(len(g)):
            if n[i] > pn[i]:
                s = 0.0
            elif t[i] > pt[i]:
                s += 1.0
            vals[i] = s
        out.loc[g.index] = vals
    return out


# ── §2.3 the hurdle probability ───────────────────────────────────────────────────────────────────
def pi_features(df: pd.DataFrame, prefix: str = "") -> np.ndarray:
    """The registered, arm-independent feature matrix. `prefix="perm_"` reads the foil's permuted
    realized columns (n and miss_streak); everything else is the row's own prior/schedule."""
    n = df[f"{prefix}n"].to_numpy(dtype=float)
    t = df["t"].to_numpy(dtype=float)
    k = df["k"].to_numpy()
    kb = V.k_bucket(k)
    cols = {
        "a0": df["a0"].to_numpy(dtype=float),
        "share_played": n / np.maximum(t, 1.0),
        "no_games": (n == 0).astype(float),
        "miss_streak": df[f"{prefix}miss_streak"].to_numpy(dtype=float),
        "log_g_rem": np.log1p(df["g_rem"].to_numpy(dtype=float)),
        "log_r0": np.log1p(np.maximum(df["r0_full_ppr"].to_numpy(dtype=float), 0.0)),
        "rookie": df["rookie"].to_numpy().astype(float),
        "kb_4_6": (kb == 1).astype(float),
        "kb_7_9": (kb == 2).astype(float),
        "kb_10_12": (kb == 3).astype(float),
    }
    return np.column_stack([cols[c] for c in PI_FEATURES])


def fit_pi(X: np.ndarray, z: np.ndarray) -> dict:
    """Standardized L2 logistic (C=1). Zero-SD columns are dropped and counted; a single-class
    target falls back to its base rate (counted)."""
    from sklearn.linear_model import LogisticRegression

    X = np.asarray(X, dtype=float)
    z = np.asarray(z, dtype=int)
    if len(z) == 0:
        raise V.RosError("fit_pi on an empty training set")
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    keep = sd > 1e-12
    model = {"mu": mu, "sd": sd, "keep": keep, "dropped": int((~keep).sum()),
             "single_class": False, "base": float(z.mean())}
    if z.min() == z.max():
        model["single_class"] = True
        return model
    Xs = (X[:, keep] - mu[keep]) / sd[keep]
    lr = LogisticRegression(C=LOGIT_C, solver="lbfgs", max_iter=LOGIT_MAX_ITER)
    lr.fit(Xs, z)
    model["coef"] = lr.coef_[0].copy()
    model["intercept"] = float(lr.intercept_[0])
    return model


def predict_pi(model: dict, X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=float)
    if model["single_class"]:
        return np.full(len(X), model["base"])
    k = model["keep"]
    Xs = (X[:, k] - model["mu"][k]) / model["sd"][k]
    eta = Xs @ model["coef"] + model["intercept"]
    return 1.0 / (1.0 + np.exp(-eta))


# ── §2.3 the ratio table ──────────────────────────────────────────────────────────────────────────
def fit_ratio_table(pos, k, pred, y) -> dict:
    """Ratio quantiles (FINE_LEVELS) per (pos, k-bucket, tercile of ŷ) with the parent's fallbacks.
    Terciles are cut on training rows with ŷ > 0; ratios use rows with ŷ > 0 and y > 0."""
    pos = np.asarray(pos)
    kb = V.k_bucket(k)
    pred = np.asarray(pred, dtype=float)
    y = np.asarray(y, dtype=float)
    table: dict = {"edges": {}, "cell": {}, "kb": {}, "pos": {}, "kind": INTERVAL_NAME}
    for P in np.unique(pos):
        mp = (pos == P) & (pred > 0)
        if not mp.any():
            continue              # a predictor that is 0 everywhere at P never needs a ratio
        edges = V.tercile_edges(pred[mp])
        table["edges"][P] = edges
        terc_all = np.searchsorted(edges, pred, side="right")
        pos_rows = mp & (y > 0)
        if not pos_rows.any():
            continue
        ratio = np.where(pos_rows, y / np.where(pred > 0, pred, 1.0), np.nan)
        table["pos"][P] = np.quantile(ratio[pos_rows], FINE_LEVELS)
        for b in range(len(V.K_BUCKETS)):
            mb = pos_rows & (kb == b)
            if mb.sum() >= V.MIN_CELL_RESIDUALS:
                table["kb"][(P, b)] = np.quantile(ratio[mb], FINE_LEVELS)
            for tt in range(3):
                mc = mb & (terc_all == tt)
                if mc.sum() >= V.MIN_CELL_RESIDUALS:
                    table["cell"][(P, b, tt)] = np.quantile(ratio[mc], FINE_LEVELS)
    return table


def mixture_quantiles(pred, pi, ratio_q: np.ndarray) -> np.ndarray:
    """(n, 19) hurdle quantiles for rows sharing ONE ratio quantile vector (length 199)."""
    pred = np.asarray(pred, dtype=float)
    pi = np.clip(np.asarray(pi, dtype=float), 0.0, 1.0)
    tau = V.LEVELS[None, :]
    denom = np.maximum(1.0 - pi, 1e-300)[:, None]
    u = (tau - pi[:, None]) / denom
    eps = np.interp(u.ravel(), FINE_LEVELS, ratio_q).reshape(u.shape)
    q = pred[:, None] * eps
    q = np.where((tau <= pi[:, None]) | (pred[:, None] <= 0), 0.0, q)
    return q


def apply_hurdle(table: dict, pos, k, pred, pi) -> tuple[np.ndarray, int]:
    """(n, 19) predictive, floored at 0 and sorted; also the count of ratio-fallback rows
    (counted over rows that need a ratio, i.e. ŷ > 0)."""
    pos = np.asarray(pos)
    kb = V.k_bucket(k)
    pred = np.asarray(pred, dtype=float)
    pi = np.asarray(pi, dtype=float)
    if len(pi) != len(pred):
        raise V.RosError("π is not aligned with the predictions")
    out = np.zeros((len(pred), len(V.LEVELS)))
    fallbacks = 0
    for P in np.unique(pos):
        mp = np.where((pos == P) & (pred > 0))[0]
        if not len(mp):
            continue
        if P not in table["pos"]:
            raise V.RosError(f"no ratio table for position {P} but it has positive predictions")
        terc = np.searchsorted(table["edges"][P], pred[mp], side="right")
        for b in np.unique(kb[mp]):
            for tt in np.unique(terc):
                rows = mp[(kb[mp] == b) & (terc == tt)]
                if not len(rows):
                    continue
                rq = table["cell"].get((P, int(b), int(tt)))
                if rq is None:
                    fallbacks += len(rows)
                    rq = table["kb"].get((P, int(b)))
                    if rq is None:
                        rq = table["pos"][P]
                out[rows] = mixture_quantiles(pred[rows], pi[rows], rq)
    return np.sort(np.maximum(out, 0.0), axis=1), fallbacks


# ── the construction the harness hook calls ───────────────────────────────────────────────────────
class HurdleInterval:
    """The object `run_nf_ros1.score_fold(..., interval=)` drives.

    `prepare` fits π once per (fold, preset) on the training seasons — for the real columns and,
    separately, for the foil's permuted columns — and stores the test rows' π. `fit_table` and
    `apply_table` then stand in for the parent's residual table."""

    name = INTERVAL_NAME

    def __init__(self) -> None:
        self._pi: dict = {}
        self.by_fold: dict = {}
        self.diag: dict = {}

    def prepare(self, train: pd.DataFrame, test: pd.DataFrame, preset: str, season: int) -> None:
        for prefix in ("", "perm_"):
            pi_test = np.zeros(len(test))
            zt = (train[f"y_{preset}"].to_numpy(dtype=float) <= 0).astype(int)
            Xtr = pi_features(train, prefix)
            Xte = pi_features(test, prefix)
            trpos = train["pos"].to_numpy()
            tepos = test["pos"].to_numpy()
            for P in V.POSITIONS:
                mtr, mte = trpos == P, tepos == P
                if not mte.any():
                    continue
                if not mtr.any():
                    raise V.RosError(f"no training rows to fit π at {P}")
                model = fit_pi(Xtr[mtr], zt[mtr])
                pi_test[mte] = predict_pi(model, Xte[mte])
                self.diag[(season, preset, prefix or "real", P)] = {
                    "single_class": model["single_class"], "dropped_features": model["dropped"],
                    "train_zero_rate": model["base"]}
            self._pi[(preset, prefix)] = pi_test
            self.by_fold[(season, preset, prefix)] = pi_test

    def pi(self, preset: str, prefix: str = "") -> np.ndarray:
        return self._pi[(preset, prefix)]

    @staticmethod
    def fit_table(pos, k, pred, y) -> dict:
        return fit_ratio_table(pos, k, pred, y)

    def apply_table(self, table: dict, test: pd.DataFrame, pred, preset: str,
                    prefix: str = "") -> tuple[np.ndarray, int]:
        return apply_hurdle(table, test["pos"].to_numpy(), test["k"].to_numpy(), pred,
                            self.pi(preset, prefix))


def diag_key(k: tuple) -> str:
    return "|".join(str(x) for x in k)


# ── §7 mechanism diagnostics (reported, never gates) ─────────────────────────────────────────────
def mechanism_check(y, point, q, pos, rng_seed: int) -> dict:
    """Per position: top-tercile q05 = 0 share vs realized y ≤ 0 share, and the lowest PIT decile mass."""
    y = np.asarray(y, dtype=float)
    point = np.asarray(point, dtype=float)
    pos = np.asarray(pos)
    out = {}
    for i, P in enumerate(V.POSITIONS):
        m = pos == P
        if not m.any():
            continue
        edges = V.tercile_edges(point[m])
        top = m & (point > edges[1])
        u = V.randomized_pit(y[m], q[m], np.random.default_rng(rng_seed + i))
        out[P] = {"top_tercile_rows": int(top.sum()),
                  "top_tercile_q05_zero_share": float((q[top, 0] <= 0).mean()) if top.any() else None,
                  "top_tercile_realized_zero_share": float((y[top] <= 0).mean()) if top.any() else None,
                  "lowest_pit_decile_mass": float((u < 0.1).mean())}
    return out


def pi_reliability(pi, y, pos) -> dict:
    """10 equal-count bins of π per position: mean predicted vs realized y ≤ 0 rate."""
    pi = np.asarray(pi, dtype=float)
    z = (np.asarray(y, dtype=float) <= 0).astype(float)
    pos = np.asarray(pos)
    out = {}
    for P in V.POSITIONS:
        m = pos == P
        if m.sum() < 10:
            continue
        order = np.argsort(pi[m], kind="stable")
        bins = np.array_split(order, 10)
        out[P] = [{"pred": float(pi[m][b].mean()), "realized": float(z[m][b].mean()),
                   "rows": int(len(b))} for b in bins]
    return out


def finite(x) -> float | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)
