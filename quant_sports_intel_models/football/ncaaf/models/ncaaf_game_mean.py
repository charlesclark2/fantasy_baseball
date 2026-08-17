"""ncaaf_game_mean.py — NCAAF-P2.1-S1-serve: the served MEAN artifact (μ), made explicit.

WHY THIS MODULE EXISTS
----------------------
P1.4 shipped a served DISPERSION artifact (`ncaaf_game_distribution_v1.json` = σ₀/k/ρ/form + a
contract NAME) and **no mean model**. μ was implicit: the game predictor made the caller supply it,
and P1.5's season sim rebuilt it ANALYTICALLY from the P1.2 strengths. That was fine while the
served contract was `strength_only` — the analytic map *is* that model to within its σ.

NCAAF-P2.1 S1 certified a real calibration improvement on a *feature* the analytic map cannot
express (`pace`: +0.062 CRPS, 8/8 folds, DSR 0.998 — `ablation_results/ncaaf_p2_1_s1_readout.md`).
Re-fitting σ under a pace contract while serving a pace-free μ would be a **train/serve mismatch**
(the E7.9 class): σ calibrated on pace-mean residuals, served against a strength-only mean. So the
mean has to become an ARTIFACT, persisted beside the dispersion and read by every consumer.

⭐ THE ONE PROPERTY EVERYTHING ELSE RESTS ON — A MISSING FEATURE IS EXACTLY INERT
--------------------------------------------------------------------------------
The served learner is a `StandardScaler → Ridge` pipeline whose NaNs are filled with the TRAIN MEAN
of each column *before* standardization. Mean-imputation preserves a column's mean, so the scaler's
own `mean_` equals that same train mean, and

    μ = intercept + Σ_k coef_k · (x_k − scaler_mean_k) / scale_k

contributes **exactly 0.0** for any column whose value is missing. That is not an approximation and
not a tolerance: a NULL feature moves μ by 0, bit for bit.

This is what makes the pace term safe to ship before the season opens. Every week-1 row has NULL
pace (the team-week rollup's honest empty row; S1-V6/V7 measured 100 %), so `pace_delta(...)` on a
pre-season board is identically zero and the board is BYTE-IDENTICAL to the pre-S1-serve one. The
term only starts acting once teams have played — which is exactly the regime S1 certified it in.

WHAT IS PERSISTED, AND WHAT IS DELIBERATELY NOT
-----------------------------------------------
Persisted: the ordered column list, the train-mean impute vector, the scaler mean/scale, and the
standardized ridge coefficients + intercept for BOTH targets (margin and total). That is the whole
linear model — `predict()` here reproduces the sklearn pipeline exactly (guard-pinned to 1e-9).

Not persisted: a pickle. A pickled estimator is the MLB `_loss` landmine (an unpinned sklearn
rebuild breaks the load); a coefficient table is version-proof, diffable, and reviewable. The cost
is that only a LINEAR served learner can be persisted this way — `fit_mean_params` RAISES for
anything else rather than writing an artifact that silently does not describe the served model.

CONSUMERS
---------
* `bakeoff_ncaaf_game.stage_finalize` — fits and writes it beside the dispersion.
* `season_simulation` / `run_season_simulation` — read the PACE coefficients only, as an additive
  delta on top of the analytic strength map (see `PaceAdjustment`; the sim cannot use the full
  ridge because it draws only margin/offense/defense per team, not the 25-column strength contract).
* a standalone game distribution can use `predict()` directly for the full served μ.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

#: the artifact's schema version — bumped only when the FIELD SET changes, never per refit.
MEAN_ARTIFACT_VERSION = "ncaaf_game_mean_v2"

#: the two targets the served joint model carries.
TARGETS: tuple[str, ...] = ("margin", "total")

#: learners whose mean model is fully described by (scaler, coefficients). Anything else must RAISE.
LINEAR_LEARNERS: frozenset[str] = frozenset({"ridge"})


@dataclass
class NcaafGameMeanParams:
    """The served mean model as a coefficient table (see the module docstring)."""

    contract: str
    columns: list[str]
    impute_means: list[float]          # TRAIN mean per column — the NaN fill
    scaler_mean: list[float]
    scaler_scale: list[float]
    coef_margin: list[float]           # standardized-space coefficients
    intercept_margin: float
    coef_total: list[float]
    intercept_total: float
    pace_columns: list[str] = field(default_factory=list)
    learner: str = "ridge"
    alpha: float | None = None
    n_train_rows: int = 0
    train_seasons: list[int] = field(default_factory=list)
    fit_at: str = ""
    version: str = MEAN_ARTIFACT_VERSION
    notes: str = ""

    # ── invariants ────────────────────────────────────────────────────────────────────────
    def __post_init__(self) -> None:
        n = len(self.columns)
        for name in ("impute_means", "scaler_mean", "scaler_scale", "coef_margin", "coef_total"):
            got = len(getattr(self, name))
            if got != n:
                raise ValueError(f"{name} has {got} entries for {n} columns — a mean artifact whose "
                                 "vectors disagree with its column list cannot be served")
        if len(set(self.columns)) != n:
            raise ValueError("duplicate column in the served mean contract")
        missing = [c for c in self.pace_columns if c not in self.columns]
        if missing:
            raise ValueError(f"pace_columns {missing} are not in the served contract — a declared "
                             "term with no column is the wired-but-never-invoked class (NF-C0e)")
        if np.any(np.asarray(self.scaler_scale, float) <= 0):
            raise ValueError("a non-positive scaler scale would divide by zero at score time")

    # ── serialization ─────────────────────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "NcaafGameMeanParams":
        known = {f for f in cls.__dataclass_fields__}          # noqa: SLF001 — dataclass API
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def load(cls, path: str | Path) -> "NcaafGameMeanParams":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2))
        return p

    # ── the model ─────────────────────────────────────────────────────────────────────────
    def _idx(self, column: str) -> int:
        try:
            return self.columns.index(column)
        except ValueError:                                       # pragma: no cover — guarded above
            raise KeyError(f"{column!r} is not in the served mean contract") from None

    def _coef(self, target: str) -> np.ndarray:
        if target not in TARGETS:
            raise KeyError(f"unknown target {target!r}; known: {TARGETS}")
        return np.asarray(self.coef_margin if target == "margin" else self.coef_total, float)

    def _intercept(self, target: str) -> float:
        return float(self.intercept_margin if target == "margin" else self.intercept_total)

    def raw_coefficient(self, target: str, column: str) -> float:
        """∂μ/∂x in ORIGINAL units (points per unit of `column`) — `coef_std / scale`."""
        i = self._idx(column)
        return float(self._coef(target)[i] / self.scaler_scale[i])

    def center(self, column: str) -> float:
        """The value at which `column` contributes exactly 0 — its train mean (= the NaN fill)."""
        return float(self.impute_means[self._idx(column)])

    def predict(self, values: Mapping[str, Any], target: str) -> np.ndarray:
        """μ for one or many rows. `values` maps column → scalar/array; an ABSENT or NaN column is
        imputed to its train mean and therefore contributes exactly 0 (see the module docstring)."""
        coef, scale = self._coef(target), np.asarray(self.scaler_scale, float)
        cmean, imean = np.asarray(self.scaler_mean, float), np.asarray(self.impute_means, float)
        shape: tuple[int, ...] = ()
        for c in self.columns:
            v = values.get(c)
            if v is not None:
                shape = np.shape(np.asarray(v, float)) or shape
        out = np.full(shape or (1,), self._intercept(target), dtype=float)
        for i, c in enumerate(self.columns):
            v = values.get(c)
            x = np.full(out.shape, imean[i]) if v is None else np.asarray(v, float).astype(float)
            x = np.where(np.isfinite(x), x, imean[i])
            out = out + coef[i] * (np.broadcast_to(x, out.shape) - cmean[i]) / scale[i]
        return out

    def term_delta(self, columns: Sequence[str], values: Mapping[str, Any], target: str) -> np.ndarray:
        """The additive contribution of `columns` alone to μ — the piece a consumer that already
        has the rest of the mean (the season sim's analytic strength map) adds on top.

        Exactly 0 wherever a value is missing/NaN, by the centering identity. Returns an array
        broadcast over whatever shape the supplied values carry.
        """
        shape: tuple[int, ...] = ()
        for c in columns:
            v = values.get(c)
            if v is not None:
                shape = np.shape(np.asarray(v, float)) or shape
        out = np.zeros(shape or (1,), dtype=float)
        for c in columns:
            i = self._idx(c)
            v = values.get(c)
            if v is None:
                continue                                     # absent ⇒ imputed ⇒ contributes 0
            x = np.broadcast_to(np.asarray(v, float).astype(float), out.shape)
            contrib = self._coef(target)[i] * (x - self.scaler_mean[i]) / self.scaler_scale[i]
            out = out + np.where(np.isfinite(x), contrib, 0.0)
        return out

    def pace_delta(self, values: Mapping[str, Any], target: str = "margin") -> np.ndarray:
        """The certified pace term alone (`term_delta` over `pace_columns`)."""
        return self.term_delta(self.pace_columns, values, target)


def fit_mean_params(
    X: np.ndarray, y_margin: np.ndarray, y_total: np.ndarray, columns: Sequence[str], *,
    learner: str, contract: str, alpha: float, pace_columns: Sequence[str] = (),
    n_train_rows: int | None = None, train_seasons: Sequence[int] = (), fit_at: str = "",
    notes: str = "",
) -> NcaafGameMeanParams:
    """Fit the served mean model on `X` (already TRAIN-mean imputed) and return the artifact.

    ⛔ RAISES for a non-linear learner rather than writing an artifact that does not describe the
    served model — a mean artifact that silently omits the mean is worse than none (NF1.7 a).
    """
    if learner not in LINEAR_LEARNERS:
        raise ValueError(
            f"the served mean artifact can only be persisted as coefficients for a LINEAR learner "
            f"(known: {sorted(LINEAR_LEARNERS)}); got {learner!r}. Serving a coefficient table that "
            "does not describe the fitted model would be the E7.9 train/serve mismatch this "
            "artifact exists to prevent — add a persistence path for that learner first.")
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    cols = list(columns)
    Xa = np.asarray(X, float)
    if Xa.shape[1] != len(cols):
        raise ValueError(f"X has {Xa.shape[1]} columns for {len(cols)} names")
    if not np.isfinite(Xa).all():
        raise ValueError("the mean-artifact fit matrix carries non-finite values — impute BEFORE "
                         "fitting, or the persisted scaler mean will not equal the NaN fill and the "
                         "missing-is-inert identity breaks")
    impute_means = Xa.mean(axis=0)          # X arrives imputed ⇒ this IS the train mean
    sc = StandardScaler().fit(Xa)
    Z = sc.transform(Xa)
    mm = Ridge(alpha=alpha).fit(Z, np.asarray(y_margin, float))
    mt = Ridge(alpha=alpha).fit(Z, np.asarray(y_total, float))
    return NcaafGameMeanParams(
        contract=contract, columns=cols,
        impute_means=[float(v) for v in impute_means],
        scaler_mean=[float(v) for v in sc.mean_],
        scaler_scale=[float(v) for v in sc.scale_],
        coef_margin=[float(v) for v in mm.coef_], intercept_margin=float(mm.intercept_),
        coef_total=[float(v) for v in mt.coef_], intercept_total=float(mt.intercept_),
        pace_columns=[c for c in pace_columns if c in cols],
        learner=learner, alpha=float(alpha),
        n_train_rows=int(n_train_rows if n_train_rows is not None else len(Xa)),
        train_seasons=[int(s) for s in train_seasons], fit_at=fit_at, notes=notes,
    )
