"""target_regression.py — MLB Edge-E7.15 H4: regress the TARGET toward true talent.

THE MECHANISM (pure — no IO, fast-gate-safe)
--------------------------------------------
The label is the realized MLB rate PA-weighted over a player's first `label_window` seasons, admitted at
`mlb_pa >= 150`. A 150-PA label is a far noisier measurement of the same underlying talent than a
1,200-PA one — its binomial sampling sd is ~2.8x larger — yet the fit treats both as equally valid
readings of the map's output. H4 shrinks each label toward a prior by its OWN reliability
`r = PA/(PA+k)`, so the model learns the map to TRUE TALENT rather than to a noisy realization.

⚠️ **THIS CHANGES THE ESTIMAND, WHICH H1 DELIBERATELY DID NOT.** Readiness lock 3 requires board and
betting comparability, so the change is confined to the TRAINING target and the EVALUATION target is
left untouched: every arm is scored against the SAME realized held-out rate. Scoring a shrunken-target
arm against its own shrunken label would be scoring it on a different, easier question — the E7.16
matched-support defect ("an arm that can be scored on an easier population is not comparable"), one
mechanism over. `shrink_training_target_only` enforces that structurally: it takes a train frame and
returns a train frame, and there is no code path that can reach the test rows.

🪤 **THE CENTRAL HAZARD, NAMED BEFORE THE RUN: MAE AGAINST A NOISY TARGET REWARDS SHRINKAGE PER SE.**
Compressing predictions toward the mean lowers mean absolute error against a noisy realization whether
or not the underlying map improved — the E2.1-r / NF-D11 metric-inversion class in a new costume, and
this time the mechanism *is* shrinkage, so the inversion would look exactly like success. Three
anchors, all pre-registered, separate "shrinking helps because shrinking helps" from "a de-noised
target teaches a better map":

  * `A_shrink_constant` — shrink every label by the SAME factor (the PA-weighted mean reliability).
    It has the identical average compression and NO per-player content. **If it ties the real arm, the
    reliability story is refuted and what we measured was a global rescale the regression already had.**
    This is slice 1's `constant_reliability` foil applied to the target instead of the feature — the
    same instrument, the other side of the equation.
  * `A_shrink_full` — shrink all the way (`r = 0`). The training target becomes CONSTANT, so the model
    can learn nothing at all; it is the degenerate ceiling of this family and must lose catastrophically.
    A metric that likes it is inverted.
  * `A_target_identity` — `r = 1`, a byte no-op against the foil.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from betting_ml.scripts.milb_mle.park_context import STABILIZATION_PA, reliability_weight

# Modes, deliberately spanning "no shrink" → "total shrink" so the family's own degenerate is in the
# field rather than assumed away.
TARGET_MODES: tuple[str, ...] = ("off", "eb", "eb_level", "constant", "full", "identity")

# The column carrying each row's label exposure. `build_graduated_pairs` names it `mlb_pa` on BOTH
# sides (the pitcher pairs use mlb_pa for TBF-equivalent exposure) — a missing column must RAISE rather
# than silently disable the shrink, which is how E7.12's `label_weight_col` guard was written after a
# plausible-looking `mlb_tbf` produced an all-null weight and a clean-looking null.
LABEL_EXPOSURE_COL = "mlb_pa"


@dataclass(frozen=True)
class TargetSpec:
    """One pre-registered rung of the H4 ladder. `TargetSpec()` is the incumbent (no shrink)."""

    mode: str = "off"
    k_mult: float = 1.0        # multiplier on the metric's stabilization point

    def __post_init__(self):
        if self.mode not in TARGET_MODES:
            raise ValueError(f"mode={self.mode!r} not in {TARGET_MODES}")
        if not (self.k_mult > 0):
            raise ValueError("k_mult must be > 0")

    @property
    def is_noop(self) -> bool:
        return self.mode in ("off", "identity")

    @property
    def label(self) -> str:
        if self.mode == "off":
            return "baseline"
        return f"target:{self.mode}" + (f"@{self.k_mult:g}k" if self.mode in ("eb", "eb_level") else "")


def label_reliability(train: pd.DataFrame, metric: str, spec: TargetSpec) -> np.ndarray:
    """`r = PA/(PA + k*mult)` per labelled row — the share of the realized label that is SIGNAL.

    Raises when the exposure column is absent: a shrink silently disabled by a missing column would
    report a clean null for a mechanism that never ran (the E7.12 `label_weight_col` lesson, and the
    H2 inert-anchor class).
    """
    if LABEL_EXPOSURE_COL not in train.columns:
        raise KeyError(
            f"the label-exposure column {LABEL_EXPOSURE_COL!r} is absent, so the target shrink would "
            f"silently no-op and report a clean null for a mechanism that never ran.")
    pa = pd.to_numeric(train[LABEL_EXPOSURE_COL], errors="coerce").fillna(0.0)
    k = spec.k_mult * STABILIZATION_PA.get(metric, 200.0)
    return reliability_weight(pa, k)


def shrink_training_target_only(train: pd.DataFrame, metric: str, spec: TargetSpec) -> pd.DataFrame:
    """Return a COPY of `train` with `target` regressed toward its prior. **Train rows only.**

    The anchor a row is pulled toward is the population mean (`eb`, `constant`, `full`) or the row's own
    LEVEL mean (`eb_level`) — both computed on TRAIN, so nothing about the held-out cohort enters.

    ⚠️ There is deliberately no `test` parameter. The evaluation target must stay the realized rate for
    every arm, and the cheapest way to guarantee that is for the shrink to be unable to reach it.
    """
    out = train.copy()
    if spec.is_noop or out.empty:
        out["target_shrink_r"] = 1.0
        return out

    y = pd.to_numeric(out["target"], errors="coerce")
    r = label_reliability(out, metric, spec)
    if spec.mode == "constant":
        # MATCHED FOIL — identical AVERAGE compression, zero per-player content. Exposure-weighted so
        # it matches the real arm's mean shrink rather than an unweighted one.
        pa = pd.to_numeric(out[LABEL_EXPOSURE_COL], errors="coerce").fillna(0.0).to_numpy(float)
        r = np.full(len(out), float(np.average(r, weights=pa)) if pa.sum() > 0 else float(np.mean(r)))
    elif spec.mode == "full":
        r = np.zeros(len(out))

    if spec.mode == "eb_level" and "level" in out.columns:
        anchor = out.groupby("level")["target"].transform("mean")
        anchor = anchor.fillna(float(y.mean(skipna=True)))
    else:
        anchor = pd.Series(float(y.mean(skipna=True)) if y.notna().any() else 0.0, index=out.index)

    out["target"] = anchor + r * (y - anchor)
    out["target_shrink_r"] = r
    return out


def target_coverage(train_shrunk: pd.DataFrame, train_raw: pd.DataFrame, spec: TargetSpec) -> dict:
    """Did the shrink ACT — in the target's own units (the H3 lesson: an inert-anchor guard is only as
    good as its activity metric, and H4's mechanism moves no feature either)."""
    n = len(train_shrunk)
    if not n:
        return {"n_rows": 0, "pct_rows_moved": 0.0}
    a = pd.to_numeric(train_shrunk["target"], errors="coerce").to_numpy(float)
    b = pd.to_numeric(train_raw["target"], errors="coerce").to_numpy(float)
    moved = np.abs(a - b) > 1e-12
    r = pd.to_numeric(train_shrunk.get("target_shrink_r"), errors="coerce").fillna(1.0).to_numpy(float)
    return {
        "n_rows": int(n),
        "pct_rows_moved": round(100.0 * float(moved.mean()), 2),
        "mean_shrink_r": round(float(np.mean(r)), 4),
        "r_p05": round(float(np.percentile(r, 5)), 4),
        "r_p95": round(float(np.percentile(r, 95)), 4),
        "target_sd_ratio": round(float(np.nanstd(a) / np.nanstd(b)), 4) if np.nanstd(b) > 0 else 1.0,
    }


def evaluation_target_is_untouched(test_before: pd.DataFrame, test_after: pd.DataFrame) -> bool:
    """The invariant every H4 arm is asserted against: the HELD-OUT target is byte-identical.

    An arm scored against its own shrunken label would be answering an easier question than the foil,
    and the leaderboard would rank the amount of shrinkage rather than the quality of the map.
    """
    a = pd.to_numeric(test_before["target"], errors="coerce").to_numpy(float)
    b = pd.to_numeric(test_after["target"], errors="coerce").to_numpy(float)
    return bool(a.shape == b.shape and np.allclose(a, b, equal_nan=True))
