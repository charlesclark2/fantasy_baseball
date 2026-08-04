"""fv_starter_prior.py — MLB Edge-E7.10: is the pre-debut FanGraphs FV grade an INCREMENTAL cold-start
RATE prior for debuting STARTERS, over the E7.5p MiLB-MLE prior that is already served?

WHAT THIS IS (and what it is NOT)
---------------------------------
E7.5p wired the E7.3p MiLB→MLB MLE line (GB% / K% / BB%) as the prior a debuting starter gets in
`eb_starter_posteriors` instead of a generic experience-band prior. E7.8 separately found that FV
COMPLEMENTS our own performance read *for pitchers* — but on a completely different target (3-year
dynasty FANTASY POINTS) and a different population. **E7.10 needs its own validation and this module is
it:** does the pre-debut grade improve the RATE prior at the debut, per metric, once the MLE prior is
already in the model?

⛔ **NOT an edge claim.** `best_alpha = 0`. The deliverable is a better-CALIBRATED cold-start starter
rate prior; a NULL is a valid, likely and fully shippable outcome.

⭐ THE ONE DESIGN DECISION EVERYTHING TURNS ON — THE MATCHED FOIL
-----------------------------------------------------------------
Every FV arm here is an in-fold regression, so it also gets a free intercept and slope on `mle_<m>`.
Scored against the SERVED prior (`L0_mle_served`, the raw MLE mean) an FV arm can win on **recalibration
of the MLE alone**, and the win would be mis-attributed to the scouting grade. So the primary defender
is `C0_mle_recal` — the identical regression MINUS the FV columns. It holds the recalibration constant
and varies only the FV channel, which is what earns an *attributable* verdict in either direction
(NF-D10 (g) — a leaderboard rank cannot separate "my feature is inert" from "my feature is in a tie";
NF-D15 (g′) — "my arm won" is not "it won for the reason I said").

`L0_mle_served` is scored and reported beside them, so "in-fold recalibration alone helps" surfaces as
its own finding rather than hiding inside an FV number.

SCORING — CRPS, NOT MAE (NF-D11 / E2.1-r)
-----------------------------------------
The primary score is held-out **CRPS** of a Normal predictive, each arm carrying its OWN in-fold
self-calibrated σ. A proper score grades the point AND the spread jointly, so neither a pessimism
degenerate nor a sharpness degenerate can win it. MAE and NLL are reported as sensitivities. Interval
coverage is published but **gates nothing** — a coverage figure is a FLOOR, never a target (E2.1-r).

And per NF-D14 we do not *reason* about whether the point score inverts on this population: the
degenerate anchors stay in the field EVERY run and their scores are READ.

Pure numpy/pandas — no S3, no DuckDB, no `pipeline` import (the fast-gate rule), so the whole study
mechanism is exercised by CI on fixtures.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

log = logging.getLogger("e7_10.fv_starter_prior")

# The three metrics E7.5p actually wires into the served starter prior. hr_rate / xwoba_against are NOT
# here for the same reason they are not there: E7.3p graded them a tied-field null and a no-signal
# translation. A metric with no MLE prior to be incremental TO is not an E7.10 question.
PRIOR_METRICS: tuple[str, ...] = ("gb_pct", "k_pct", "bb_pct")

# Evidence unit per metric (E7.5p `EVIDENCE_COUNT`) — carried so the wiring half, if it ever runs,
# cannot silently blend a GB prior against a batters-faced count.
EVIDENCE_COUNT: dict[str, str] = {"gb_pct": "bip", "k_pct": "bf", "bb_pct": "bf"}

# ── Pre-registered constants (fixed in `e7_10_preregistration.md` BEFORE any arm was scored) ─────────
#: FV bucket edges. FIXED, never tuned in-fold — an in-fold edge search would be a hidden extra trial
#: that PBO/DSR would not see.
FV_BUCKET_EDGES: tuple[float, ...] = (40.0, 45.0, 50.0)
#: Minimum pre-debut MiLB start share for the PRIMARY `starter` population (leakage-safe: knowable at
#: call-up, conditions on nothing that happens after the debut).
MIN_START_SHARE = 0.50
#: A practically-meaningful FV increment, in RELATIVE held-out CRPS over the matched foil. Basis: E7.5p's
#: recorded gain of the WHOLE MLE prior over the generic prior was −23.0% / −10.4% / −7.6% CRPS; a term
#: worth under roughly a third of the smallest cannot move a served rate enough to change a priced total.
#: Set from a PRIOR story's recorded result, before this run — not from this run's spread.
MEANINGFUL_REL_CRPS_GAIN = 0.03
#: Seed for the permutation placebo. Fixed so the anchor is reproducible run to run.
PLACEBO_SEED = 7

FOIL = "C0_mle_recal"            # the MATCHED foil — the primary defender (see the module docstring)
SERVED_REFERENCE = "L0_mle_served"  # what serving does today; reported, never the defender
MECHANISM_ARM = "A1_mle_fv"      # the pre-registered PRIMARY mechanism arm

#: The DECLARED family (MH2 (a): you pre-register a family, you do not discover one). These three FV
#: FORMS are the eligible/selectable set and the DSR trial field. Foils and anchors are neither.
ELIGIBLE_ARMS: tuple[str, ...] = ("A1_mle_fv", "A2_mle_fv_bucket", "A3_mle_fv_eta_risk")


# ══════════════════════════════════════════════════════════════════════════════════════
# Proper scoring for a Normal predictive
# ══════════════════════════════════════════════════════════════════════════════════════


def _erf(x: np.ndarray) -> np.ndarray:
    """Vectorised erf (Abramowitz-Stegun 7.1.26, max err ~1.5e-7) — the same approximation
    `mle_prior._erf` uses, so E7.5p and E7.10 CRPS numbers are comparable on their face."""
    x = np.asarray(x, float)
    sign = np.sign(x)
    ax = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * ax)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t
               + 0.254829592) * t * np.exp(-ax * ax)
    return sign * y


def normal_crps(y: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    """Closed-form CRPS for a Normal predictive (Gneiting & Raftery 2007). Lower is better.

    ⭐ This is the PRIMARY score. At σ→0 it degenerates to |y−μ| (i.e. MAE), and at σ→∞ it diverges —
    which is exactly why the two-sided sharpness anchors (`Z_sigma_sharp` / `Z_sigma_wide`) are a
    meaningful test here rather than decoration (NF1.7 (3))."""
    from math import pi, sqrt

    sd = np.maximum(np.asarray(sd, float), 1e-9)
    z = (np.asarray(y, float) - np.asarray(mu, float)) / sd
    phi = np.exp(-0.5 * z * z) / sqrt(2.0 * pi)
    Phi = 0.5 * (1.0 + _erf(z / sqrt(2.0)))
    return sd * (z * (2.0 * Phi - 1.0) + 2.0 * phi - 1.0 / sqrt(pi))


def normal_nll(y: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    sd = np.maximum(np.asarray(sd, float), 1e-9)
    return 0.5 * np.log(2.0 * np.pi * sd * sd) + (np.asarray(y, float) - np.asarray(mu, float)) ** 2 \
        / (2.0 * sd * sd)


# ══════════════════════════════════════════════════════════════════════════════════════
# Design matrices — one place, so an arm's identity is its FEATURE SET and nothing else
# ══════════════════════════════════════════════════════════════════════════════════════


def fv_bucket_labels(fv: pd.Series, edges: tuple[float, ...] = FV_BUCKET_EDGES) -> pd.Series:
    """FV → ordinal bucket label. FIXED edges (see `FV_BUCKET_EDGES`) — never fitted."""
    v = pd.to_numeric(fv, errors="coerce")
    out = pd.Series("lt%g" % edges[0], index=v.index, dtype=object)
    for i, e in enumerate(edges):
        hi = edges[i + 1] if i + 1 < len(edges) else None
        out = out.mask(v >= e, ("ge%g" % e) if hi is None else ("%g_%g" % (e, hi)))
    return out.mask(v.isna(), "missing")


def _one_hot(train_vals: pd.Series, vals: pd.Series) -> np.ndarray:
    """One-hot over the categories present in TRAIN, drop-first. A category unseen in train maps to the
    all-zero baseline row — never to a new column, which would make train and test different widths."""
    cats = sorted(set(train_vals.dropna().astype(str)))
    if len(cats) <= 1:
        return np.zeros((len(vals), 0))
    keep = cats[1:]                                   # drop-first
    v = vals.astype(str).to_numpy()
    return np.column_stack([(v == c).astype(float) for c in keep])


@dataclass(frozen=True)
class ArmSpec:
    """An arm IS its feature set. `uses_fv` marks the mechanism channel so the report can say which
    arms could possibly carry the effect."""
    label: str
    uses_fv: bool
    kind: str = "regression"       # "regression" | "served" | "cohort_mean"
    with_bucket: bool = False
    with_eta_risk: bool = False
    permute_fv: bool = False       # the PLACEBO — FV shuffled within each fold, marginal preserved
    sigma_scale: float = 1.0       # the two-sided sharpness anchors
    drop_mle: bool = False         # the DIAGNOSTIC arm — FV alone, no MLE column


ARMS: tuple[ArmSpec, ...] = (
    # ── references / foils ──────────────────────────────────────────────────────────────────────
    ArmSpec(SERVED_REFERENCE, uses_fv=False, kind="served"),
    ArmSpec(FOIL, uses_fv=False),
    # ── the DECLARED family (eligible; the DSR trial field) ─────────────────────────────────────
    ArmSpec("A1_mle_fv", uses_fv=True),
    ArmSpec("A2_mle_fv_bucket", uses_fv=True, with_bucket=True),
    ArmSpec("A3_mle_fv_eta_risk", uses_fv=True, with_eta_risk=True),
    # ── anchors (never eligible, always in the whole field) ─────────────────────────────────────
    ArmSpec("Z_fv_permuted", uses_fv=True, permute_fv=True),
    ArmSpec("Z_cohort_mean", uses_fv=False, kind="cohort_mean"),
    ArmSpec("Z_sigma_sharp", uses_fv=True, sigma_scale=0.1),
    ArmSpec("Z_sigma_wide", uses_fv=True, sigma_scale=10.0),
    # ── a POST-HOC DIAGNOSTIC, deliberately NOT a trial ─────────────────────────────────────────
    # ⚠️ **A DIAGNOSTIC ANCHOR IS NEVER A TRIAL (MH2.1 (a)).** `D_fv_over_generic` is FV with the MLE
    # column REMOVED, scored against `Z_cohort_mean` (the generic prior). It answers the question a
    # bare null cannot — is FV UNINFORMATIVE on this population, or is it informative but a SUBSTITUTE
    # for what our own MLE already knows? (E7.8's substitute/complement decomposition, on the E7.10
    # target.) It is `selectable=False`, is excluded from `ELIGIBLE_ARMS`, and therefore enters
    # neither the PBO eligible set nor the DSR trial field — an arm that exists to POLICE the reading
    # must never set the gate's own bar.
    ArmSpec("D_fv_over_generic", uses_fv=True, drop_mle=True),
)
ARM_BY_LABEL: dict[str, ArmSpec] = {a.label: a for a in ARMS}


def _design(spec: ArmSpec, train: pd.DataFrame, frame: pd.DataFrame, metric: str,
            rng: np.random.Generator | None) -> np.ndarray:
    """Design matrix for `frame` with categories/levels taken from `train` (so train and test are
    column-aligned by construction). Column 0 is always the intercept, column 1 the served MLE mean."""
    n = len(frame)
    cols = [np.ones(n)]
    if not spec.drop_mle:
        cols.append(pd.to_numeric(frame[f"mle_{metric}"], errors="coerce").to_numpy(float))
    if spec.uses_fv:
        fv = pd.to_numeric(frame["fv"], errors="coerce")
        if spec.permute_fv:
            # ⭐ THE PLACEBO. Shuffling WITHIN the frame preserves the FV marginal distribution EXACTLY
            # and destroys only the per-player pairing — so if this arm still wins, the win is not
            # about the grade (NF-D15 g′ / the E7.5b permutation anchor).
            idx = (rng or np.random.default_rng(PLACEBO_SEED)).permutation(n)
            fv = pd.Series(fv.to_numpy()[idx], index=fv.index)
        cols.append(fv.to_numpy(float))
        if spec.with_bucket:
            cols.append(_one_hot(fv_bucket_labels(train["fv"]), fv_bucket_labels(fv)))
        if spec.with_eta_risk:
            # years-to-arrival is scale-free; a raw ETA year would encode the cohort itself
            eta = (pd.to_numeric(frame.get("eta"), errors="coerce")
                   - pd.to_numeric(frame["fv_board_season"], errors="coerce"))
            cols.append(eta.to_numpy(float))
            cols.append(_one_hot(train["risk"].astype(str), frame["risk"].astype(str)))
    X = np.column_stack([c.reshape(n, -1) if np.ndim(c) == 1 else c for c in cols])
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)


def _fit_predict(spec: ArmSpec, train: pd.DataFrame, test: pd.DataFrame, metric: str,
                 rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, float]:
    """`(test_mu, train_resid, sigma)` for one arm on one fold.

    σ is each arm's OWN train-fold residual sd (self-calibrated) — neither arm is handicapped by the
    other's spread, so the contest is calibration × sharpness, exactly as in E7.5p's `ablate_metric`."""
    y_tr = pd.to_numeric(train[f"mlb_{metric}"], errors="coerce").to_numpy(float)
    if spec.kind == "served":
        mu_te = pd.to_numeric(test[f"mle_{metric}"], errors="coerce").to_numpy(float)
        resid = y_tr - pd.to_numeric(train[f"mle_{metric}"], errors="coerce").to_numpy(float)
    elif spec.kind == "cohort_mean":
        mu_te = np.full(len(test), float(np.nanmean(y_tr)))
        resid = y_tr - float(np.nanmean(y_tr))
    else:
        # the permutation placebo must be shuffled INDEPENDENTLY in train and test — shuffling only one
        # side would leave a real (if scrambled) association on the other and weaken the placebo
        X_tr = _design(spec, train, train, metric, rng)
        X_te = _design(spec, train, test, metric, rng)
        ok = np.isfinite(y_tr)
        beta, *_ = np.linalg.lstsq(X_tr[ok], y_tr[ok], rcond=None)
        mu_te = X_te @ beta
        resid = y_tr - X_tr @ beta
    resid = resid[np.isfinite(resid)]
    sigma = float(np.std(resid, ddof=1)) if len(resid) > 2 else float("nan")
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = 1e-6
    return mu_te, resid, sigma * float(spec.sigma_scale)


# ══════════════════════════════════════════════════════════════════════════════════════
# The fold run
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class MetricStudy:
    """One metric's complete E7.10 result — everything the report and the gate read."""
    metric: str
    population: str
    leaderboard: pd.DataFrame                 # arm × pooled scores (+ the harness's `oos_mae` key)
    mae_by_fold: pd.DataFrame                 # ⚠️ folds × arms of the PRIMARY score (CRPS). The column
                                              # name is the harness's (`h_harness.numeric_gate` /
                                              # `null_analysis` read `oos_mae`/`mae_by_fold`); it is
                                              # retained verbatim so those functions run UNMODIFIED.
                                              # The report labels it CRPS everywhere a human reads it.
    mae_by_fold_pointscore: pd.DataFrame      # the same frame scored on MAE — the sensitivity
    fold_cohorts: list[int]
    coverage: dict
    anchor_moves: dict                        # arm → {"pct_rows_moved": …} for the inert-anchor guard
    oracle_floor: dict                        # per-FORM peeking floor (NF-D16 g‴)
    primary_delta: list[float]                # per-fold  C0 − A1  (>0 ⇒ the FV arm is better)
    p_one_sided: float | None
    deflation: dict = field(default_factory=dict)
    dsr: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def eligible_rows(df: pd.DataFrame, metric: str, population: str = "starter") -> pd.DataFrame:
    """The scored population for one metric: labelled, FV-carrying, finite on both sides.

    The thin-sample floors are E7.5p's VERBATIM (`has_mlb_label` = mlb_pa ≥ 150 TBF, plus mlb_bip ≥ 50
    for GB%) — a re-derivation here would let the two stories drift apart silently."""
    d = df.copy()
    if "has_mlb_label" in d:
        d = d[d["has_mlb_label"].fillna(False).astype(bool)]
    if EVIDENCE_COUNT.get(metric) == "bip" and "mlb_bip" in d:
        d = d[pd.to_numeric(d["mlb_bip"], errors="coerce").fillna(0) >= 50]
    if population == "starter":
        d = d[pd.to_numeric(d.get("milb_start_share"), errors="coerce").fillna(0.0) >= MIN_START_SHARE]
    for c in (f"mle_{metric}", f"mlb_{metric}", "fv", "debut_cohort"):
        d = d[pd.to_numeric(d[c], errors="coerce").notna()]
    return d.copy()


def run_metric(df: pd.DataFrame, metric: str, population: str = "starter",
               seed: int = PLACEBO_SEED) -> MetricStudy:
    """Purged leave-one-debut-cohort-out study for one metric.

    A cohort is EVALUABLE iff at least one strictly-prior cohort is present in the FV-carrying
    population — the in-fold FV term must be fittable, and a fold that cannot fit it is not a fold the
    mechanism was given a chance on."""
    rows = eligible_rows(df, metric, population)
    if rows.empty:
        raise ValueError(f"[{metric}/{population}] no eligible rows")
    rows["debut_cohort"] = pd.to_numeric(rows["debut_cohort"], errors="coerce").astype(int)
    cohorts = sorted(rows["debut_cohort"].unique())
    eval_cohorts = [y for y in cohorts if any(c < y for c in cohorts)]

    rng = np.random.default_rng(seed)
    crps_rows: list[dict] = []
    mae_rows: list[dict] = []
    detail: dict[str, list[np.ndarray]] = {}
    moved_num: dict[str, float] = {}
    moved_den = 0.0
    oracle: dict[str, list[float]] = {}
    used: list[int] = []

    for y in eval_cohorts:
        train = rows[rows["debut_cohort"] < y]
        test = rows[rows["debut_cohort"] == y]
        if len(train) < 5 or test.empty:
            continue
        y_te = pd.to_numeric(test[f"mlb_{metric}"], errors="coerce").to_numpy(float)
        fold_crps: dict[str, float] = {}
        fold_mae: dict[str, float] = {}
        mus: dict[str, np.ndarray] = {}
        sds: dict[str, float] = {}

        for spec in ARMS:
            base = ARM_BY_LABEL[MECHANISM_ARM] if spec.sigma_scale != 1.0 else spec
            mu, _resid, sd = _fit_predict(base, train, test, metric, rng)
            if spec.sigma_scale != 1.0:
                sd = sd * spec.sigma_scale
            mus[spec.label], sds[spec.label] = mu, sd
            fold_crps[spec.label] = float(np.nanmean(normal_crps(y_te, mu, np.full(len(mu), sd))))
            fold_mae[spec.label] = float(np.nanmean(np.abs(y_te - mu)))
            detail.setdefault(spec.label, []).append(np.abs(y_te - mu))
            # per-FORM peeking floor: the arm's OWN predictions shifted by the held-out cohort's mean
            # residual. A single shared ceiling would veto a legitimately-better nested form (NF-D16 g‴)
            # — and A1 NESTS C0, so C0's ceiling emphatically cannot floor A1.
            orc = mu + float(np.nanmean(y_te - mu))
            oracle.setdefault(spec.label, []).append(
                float(np.nanmean(normal_crps(y_te, orc, np.full(len(orc), sd)))))

        # inert-anchor evidence: does the placebo actually MOVE rows vs the arm it defends? (NF1.7 (a))
        for lbl, ref in (("Z_fv_permuted", MECHANISM_ARM), ("Z_sigma_sharp", MECHANISM_ARM),
                         ("Z_sigma_wide", MECHANISM_ARM), ("Z_cohort_mean", MECHANISM_ARM)):
            if lbl in ("Z_sigma_sharp", "Z_sigma_wide"):
                d = abs(sds[lbl] - sds[ref]) > 1e-12       # these move the SPREAD, not the mean
                moved_num[lbl] = moved_num.get(lbl, 0.0) + (len(y_te) if d else 0.0)
            else:
                moved_num[lbl] = moved_num.get(lbl, 0.0) + float(
                    np.sum(np.abs(mus[lbl] - mus[ref]) > 1e-12))
        moved_den += len(y_te)

        crps_rows.append({"fold": int(y), **fold_crps})
        mae_rows.append({"fold": int(y), **fold_mae})
        used.append(int(y))

    if not used:
        raise ValueError(f"[{metric}/{population}] no evaluable folds")

    crps = pd.DataFrame(crps_rows).set_index("fold")
    mae = pd.DataFrame(mae_rows).set_index("fold")
    delta = (crps[FOIL] - crps[MECHANISM_ARM]).to_numpy(float)   # >0 ⇒ the FV arm is better

    foil_mean = float(crps[FOIL].mean())
    lb_rows = []
    for spec in ARMS:
        s = crps[spec.label]
        lb_rows.append({
            "arm": spec.label,
            "uses_fv": spec.uses_fv,
            # ⚠️ `oos_mae` holds the PRIMARY score (CRPS) — the harness key name, kept so
            # `h_harness.numeric_gate` / `null_analysis` run unmodified. `oos_crps` is the honest alias.
            "oos_mae": float(s.mean()),
            "oos_crps": float(s.mean()),
            "oos_pointscore_mae": float(mae[spec.label].mean()),
            "fold_win_rate": float(np.mean((crps[FOIL] - s).to_numpy(float) > 0)),
            "pct_lift_vs_foil": 100.0 * (foil_mean - float(s.mean())) / max(1e-12, foil_mean),
            "selectable": spec.label in ELIGIBLE_ARMS,
            "active": True,
            "note": "",
        })
    leaderboard = pd.DataFrame(lb_rows).sort_values("oos_mae").reset_index(drop=True)

    coverage = {
        "population": population,
        "n_scored": int(sum(len(a) for a in detail[MECHANISM_ARM])),
        "n_rows_total": int(len(rows)),
        "n_cohorts_present": len(cohorts),
        "cohorts_present": [int(c) for c in cohorts],
        "eval_cohorts": [int(c) for c in used],
        "n_folds": len(used),
        "rows_per_fold": {int(y): int(len(rows[rows["debut_cohort"] == y])) for y in used},
        "fv_mean": float(pd.to_numeric(rows["fv"], errors="coerce").mean()),
        "fv_sd": float(pd.to_numeric(rows["fv"], errors="coerce").std(ddof=1)),
        "fv_distinct_values": int(pd.to_numeric(rows["fv"], errors="coerce").nunique()),
    }
    anchor_moves = {k: {"pct_rows_moved": 100.0 * v / max(1e-12, moved_den)}
                    for k, v in moved_num.items()}
    return MetricStudy(
        metric=metric, population=population, leaderboard=leaderboard,
        mae_by_fold=crps, mae_by_fold_pointscore=mae, fold_cohorts=used, coverage=coverage,
        anchor_moves=anchor_moves,
        oracle_floor={k: float(np.mean(v)) for k, v in oracle.items()},
        primary_delta=[float(x) for x in delta],
        p_one_sided=one_sided_paired_p(delta),
    )


def one_sided_paired_p(delta: np.ndarray) -> float | None:
    """One-sided paired t over the per-fold deltas. H1: the FV arm is systematically better.

    ⚠️ A ZERO-VARIANCE delta is NOT untestable — a constant advantage is the most systematic case there
    is, so it is decided on the sign (the NF1.7 (a) hole, facing the other way; same convention as
    `mle_prior._one_sided_paired_p` and `run_e7_12_slice1.paired_anchor`)."""
    d = np.asarray(delta, float)
    d = d[np.isfinite(d)]
    if len(d) < 3:
        return None
    if np.std(d, ddof=1) == 0:
        return 0.0 if float(np.mean(d)) > 0 else 1.0
    from scipy import stats
    t = float(np.mean(d) / (np.std(d, ddof=1) / np.sqrt(len(d))))
    return float(stats.t.sf(t, df=len(d) - 1))


def oracle_floor_holds(study: MetricStudy, arm: str) -> bool:
    """Is `arm` at or above the peeking version of ITS OWN form? An arm beating its own oracle is
    mathematically impossible ⇒ the tell that the score is INVERTED, not a win (NF-D16 (g‴))."""
    got = float(study.leaderboard.loc[study.leaderboard["arm"] == arm, "oos_mae"].iloc[0])
    return got >= study.oracle_floor[arm] - 1e-9


def relative_gain_vs_foil(study: MetricStudy, arm: str = MECHANISM_ARM) -> float:
    """Held-out CRPS gain of `arm` over the MATCHED foil, as a fraction (the unit
    `MEANINGFUL_REL_CRPS_GAIN` is pre-registered in)."""
    f = float(study.leaderboard.loc[study.leaderboard["arm"] == FOIL, "oos_mae"].iloc[0])
    a = float(study.leaderboard.loc[study.leaderboard["arm"] == arm, "oos_mae"].iloc[0])
    return (f - a) / max(1e-12, f)


__all__ = [
    "PRIOR_METRICS", "EVIDENCE_COUNT", "FV_BUCKET_EDGES", "MIN_START_SHARE",
    "MEANINGFUL_REL_CRPS_GAIN", "PLACEBO_SEED", "FOIL", "SERVED_REFERENCE", "MECHANISM_ARM",
    "ELIGIBLE_ARMS", "ARMS", "ARM_BY_LABEL", "ArmSpec", "MetricStudy",
    "normal_crps", "normal_nll", "fv_bucket_labels", "eligible_rows", "run_metric",
    "one_sided_paired_p", "oracle_floor_holds", "relative_gain_vs_foil",
]
