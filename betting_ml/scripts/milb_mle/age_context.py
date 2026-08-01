"""E7.12 slice 5 — the age transforms the aging-curve arms are built on.

Deliberately NOT a precomputed artifact (unlike `park_context.py` / `grade_context.py`). Everything
here is a pure function of the pairs frame plus a TRAIN-ONLY reference, because the one quantity that
needs care — the level's median age — is a population aggregate, and computing it over the full frame
would let a held-out cohort's ages set the origin its own feature is measured from. It is cheap enough
to recompute per fold, so there is no artifact to go stale and no build step for the operator.

WHAT `age_vs_level` IS AND WHY IT IS THE HONEST FORM
---------------------------------------------------------------------------------------------------
Age is a property of the LEVEL, not of the player: a 22-year-old is OLD for Single-A and YOUNG for
Triple-A. Absolute age therefore confounds "young" with "assigned low". `age_vs_level` = age − the
level's median age is the same form `board_assembly.py` already publishes, and on the labelled
population it is far better balanced across buckets than absolute age (the level medians run
21.0 / 22.0 / 22.8 / 24.0 on the batter side), which matters because a partial-pooled block with an
almost-empty cell contributes a shrunk-to-zero coefficient and no information.

WHY FIXED EDGES RATHER THAN TRAIN QUANTILES
---------------------------------------------------------------------------------------------------
Quantile edges are a second train-only quantity to thread through every fold, they move the bucket
DEFINITION between folds (so a coefficient is not the same thing in fold 2016 and fold 2026), and they
buy nothing here — the fixed edges below are already near-balanced on `age_vs_level` by construction.
Fixed edges also cannot leak, which removes the whole question.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# The bucket column names the projector's `bucket_col` points at.
AGE_BUCKET = "age_bucket"
REL_BUCKET = "rel_bucket"
REL_COL = "age_vs_level"

# Absolute-age edges, in years. Chosen on baseball meaning rather than on the sample: 20 and under is
# a genuine prodigy at any full-season level, 26+ is an org veteran. Right-closed, matching pd.cut.
AGE_EDGES: tuple[float, ...] = (-np.inf, 20.0, 21.5, 23.0, 24.5, 26.0, np.inf)
AGE_LABELS: tuple[str, ...] = ("<=20", "20-21.5", "21.5-23", "23-24.5", "24.5-26", "26+")

# Age-relative-to-level edges, in years either side of the level's median.
REL_EDGES: tuple[float, ...] = (-np.inf, -1.5, -0.5, 0.5, 1.5, np.inf)
REL_LABELS: tuple[str, ...] = ("<=-1.5", "-1.5..-0.5", "-0.5..0.5", "0.5..1.5", "1.5+")


def level_median_age(train: pd.DataFrame) -> pd.Series:
    """The per-level median age, computed on TRAIN rows only — the origin `age_vs_level` is measured
    from. Returned as a Series indexed by level so a caller must pass it explicitly to
    `attach_age_features`; there is no default that silently recomputes it over the test rows.
    """
    if "age" not in train.columns or "level" not in train.columns:
        raise KeyError("level_median_age needs both `age` and `level`")
    med = train.groupby("level", dropna=True)["age"].median()
    return med[np.isfinite(med)]


def attach_age_features(frame: pd.DataFrame, medians: pd.Series) -> pd.DataFrame:
    """Add `age_vs_level`, `age_bucket` and `rel_bucket` using TRAIN-derived level medians.

    A level absent from `medians` (an unseen level in a held-out cohort) falls back to the pooled median
    of the medians rather than to NaN — a NaN would drop the row out of every bucket and quietly shrink
    the mechanism's reach without appearing anywhere in the leaderboard. A row with a missing AGE stays
    NaN and is genuinely bucket-less, which is correct: we do not know how old that player was.
    """
    if "age" not in frame.columns:
        raise KeyError("attach_age_features needs an `age` column")
    out = frame.copy()
    age = pd.to_numeric(out["age"], errors="coerce")
    fallback = float(medians.median()) if len(medians) else float(age.median())
    ref = out["level"].map(medians).astype(float).fillna(fallback)
    out[REL_COL] = age - ref
    out[AGE_BUCKET] = pd.cut(age, list(AGE_EDGES), labels=list(AGE_LABELS)).astype(object)
    out[REL_BUCKET] = pd.cut(out[REL_COL], list(REL_EDGES),
                             labels=list(REL_LABELS)).astype(object)
    return out


def permute_bucket(frame: pd.DataFrame, col: str, rng: np.random.Generator,
                   within: tuple[str, ...] = ("level", "debut_cohort")) -> pd.Series:
    """The placebo bucket assignment — permuted WITHIN `within` so the marginal age distribution of
    each (level, cohort) cell is preserved and only the player↔bucket pairing is destroyed.

    ⭐ **IT PERMUTES THE BUCKET, NOT `age` — and that distinction is the whole point.** `age` is
    already an unpenalized main effect in the incumbent design. Permuting `age` itself would corrupt
    the BASELINE the arm is being compared against, so a placebo loss would be evidence about the main
    effect rather than about the interaction. Permuting only the bucket column leaves the main effect
    exactly as it ships and isolates the one channel under test: does knowing WHICH age group a player
    is in change how his line translates, beyond the linear age term already present?
    """
    keys = [k for k in within if k in frame.columns]
    s = frame[col]
    if not keys:
        return pd.Series(rng.permutation(s.to_numpy()), index=frame.index)
    grouper = [frame[k].fillna(-1) if frame[k].dtype.kind in "ifc" else frame[k].fillna("__na__")
               for k in keys]
    return s.groupby(grouper, dropna=False).transform(lambda g: rng.permutation(g.to_numpy()))


def bucket_coverage(frame: pd.DataFrame) -> pd.DataFrame:
    """Row counts per bucket for both bucketings — the diagnostic that tells a reader whether a
    coefficient had support. An almost-empty bucket is not a bug, but a mechanism that is inert in the
    cell it was designed for (the youngest one) has to be visible rather than inferred."""
    rows = []
    for col, labels in ((AGE_BUCKET, AGE_LABELS), (REL_BUCKET, REL_LABELS)):
        if col not in frame.columns:
            continue
        vc = frame[col].value_counts()
        for lab in labels:
            rows.append({"bucketing": col, "bucket": lab, "n": int(vc.get(lab, 0))})
    return pd.DataFrame(rows)
