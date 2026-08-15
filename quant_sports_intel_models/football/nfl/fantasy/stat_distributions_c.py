"""stat_distributions_c.py — NF-W6b-C: RB rushing_tds fresh-family successor (pure).

THE STORY IN ONE PARAGRAPH. NF-W6b found a REAL winner on RB|rushing_tds — `knn_quantile` beat
the discrete climatology by +13.0% CRPS, 8/8 folds, CI excluding zero — that could never clear
DSR *in that field*: the pre-registered linear-residual arm (`enet_residual`, trial Sharpe
−9.199 on an 86%-zero cell) lost enormously and consistently, inflating the cross-trial
dispersion DSR deflates against (sr0 ≈ 7.32 > the winner's per-fold Sharpe 6.47). ⛔ MH2.2
forbids trimming a field after seeing results, so the admissible path — PM Decision C — is THIS
fresh registration: a coherent, atom-aware candidate family declared up front, which also
removes the actual cause (a position-constant residual bank around a linear mean cannot express
an 86% atom, and its guaranteed huge loss re-inflates the very deflation bar that refused the
cell). ⛔ NO linear-residual arm; ⛔ the champion-faithful `inc_head_bank` foil (the same
non-atom-aware bank in the incumbent costume, 27% behind the climatology here) is likewise out;
the four TD-NO cells stay closed (they need a different MECHANISM, not this).

⭐ FRESH REGISTRATION (MH2.2/E2.1-r): this is a NEW field with a NEW seed, not a re-score of
NF-W6b's — nothing is promoted from the old field, and the W6b record stands untouched. The
climatology foil, the two carried arm FORMS (their pinned code paths imported verbatim), and a
newly-built discrete-count class are declared here on MECHANISTIC grounds (each prices the zero
atom by construction) before any scoring.

METRIC + ANCHORS (an 86%-zero cell — the metric inverts if this is wrong): CRPS (`crps_q199`)
primary, ⛔ never MAE (NF-D11/D14 — MAE pays for pessimism at a near-floor conditional median).
The all-zero nihilist and both sharpness degenerates are SCORED every run, never reasoned
about. Per-form peeking oracles floored at matched-n (NF-D16 (g‴)/NF1.9 (f)): one ceiling per
candidate form, because `knn_quantile` NESTS the marginal (k → n reproduces the climatology)
and a single marginal ceiling would falsely veto a legitimately-better nested form. A
`tie_with_foil` guard (Batter-Props Ph2): a near-zero CRPS "lead" from a nested collapse is a
TIE, never a win. Coverage(80) is a one-sided FLOOR (NF1.9 (e): the atom makes a two-sided
coverage target structurally inverted); the two-sidedness lives in the sharpness degenerates.

NULL HANDLING: a statistical null goes to `cv_power.classify_null` WITH
`declared_field_size=DECLARED_FIELD_SIZE`, and the record reads `field_remedy_admissible` —
the machine flag, never the prose (MH2.7 / guide §0.5.4 rules 5/5b; the NF-W3 (c)
hand-derivation exception is retired for this story: the n_arms=1 mis-render is fixed and this
is a 3-arm field). A constraint/anchor-only refusal is hand-classified CONSTRAINT_REFUSED
(cv_power has no such state, and a fold trigger for a directional refusal is the NF-D18
actively-misleading direction). DSR-CONV is NOT adopted: no degenerate sits in this trial
field at all (anchors never enter trials — MH2.1 (a)), so there is nothing to exclude from V;
`degenerates_excluded_from_v=True` is passed as the provenance statement of that fact.

⚖️ EDGE-INDEPENDENT (`best_alpha` N/A) · DEPLOY-HELD: promotes nothing, publishes nothing,
retrains nothing; research-only, no changelog. A SHIP here does NOT join NF-W6c's serving
dispatch — `stat_distribution_serving.WITHHELD_NULL_CELLS` keeps RB|rushing_tds pinned OUT
until a future wiring story moves it under NF-G0 governance (guard-tested).

Pure module — no lake IO. The runner is `run_nf_w6b_c_rb_rush_tds.py`.
"""
from __future__ import annotations

import zlib
from dataclasses import asdict

import numpy as np
import pandas as pd

from betting_ml.utils import cv_power
from quant_sports_intel_models.football.nfl.fantasy import efficiency_marginals as EM
from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions as SD
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

# ── Pre-registration constants ──────────────────────────────────────────────────────────────────
STORY = "NF-W6b-C"
PRIMARY_METRIC = "crps_q199"
EVAL_LEVELS: np.ndarray = MC.EVAL_LEVELS
#: ⭐ FRESH registration ⇒ fresh seed, deliberately ≠ SD._SEED (20260815).
_SEED = 20260816

#: ONE cell. ⛔ The 4 TD-NO cells stay closed; the other 7 W6b cells are decided and untouched.
POSITION = "RB"
STAT = "rushing_tds"
CELL = "RB|rushing_tds"

#: The declared family — 3 learner classes, EVERY one atom-aware by construction (the coherence
#: requirement that makes DSR honestly evaluable). The two carried forms are the PINNED W6b code
#: paths (imported verbatim below); the discrete-count class is the PM-named third.
REAL_ARMS: tuple[str, ...] = ("lgbm_hurdle_tail", "knn_quantile", "count_negbin")
#: One foil — the W6b BINDING incumbent on this cell (per-position empirical discrete
#: climatology; atom-aware by construction). Never shippable; sets the bar.
FOILS: tuple[str, ...] = ("inc_climatology",)
#: ⭐ MH2.7: the smallest field PRE-REGISTERED for this mechanism — passed to
#: `cv_power.classify_null(declared_field_size=…)`; the record reads `field_remedy_admissible`.
DECLARED_FIELD_SIZE = len(REAL_ARMS)

#: ⛔ The excluded classes, ON THE RECORD (a guard fails if either enters the field):
BANNED_ARM_CLASSES: dict[str, str] = {
    "enet_residual": (
        "the W6b field-inflating defect: a position-constant residual bank around a linear mean "
        "cannot express an 86% atom; its guaranteed huge loss (trial Sharpe −9.199) inflated "
        "the cross-trial dispersion and set sr0 above the real winner's Sharpe"),
    "inc_head_bank": (
        "the same non-atom-aware residual-bank class in the incumbent costume — 27% behind the "
        "climatology on this cell; a coherent atom-aware field excludes it for the same "
        "mechanistic reason (its W6b score, 0.18987, is already on the record)"),
}

#: Degenerate anchors — scored every run, never reasoned about (NF-D11/NF-D14). ⚠️ On this cell
#: the climatology's median is 0 (86% atom), so `zero_width` NUMERICALLY COINCIDES with the
#: nihilist — a property of the atom, recorded, not a defect; both must still lose.
DEGENERATES: tuple[str, ...] = ("nihilist_zero", "zero_width", "max_width")
#: ⭐ NF-D16 (g‴)/NF1.9 (f): one peeking-ceiling-plus-matched-n pair PER FORM (candidate forms
#: nest the marginal, so one field-wide ceiling would be a false veto). The `marginal` pair is
#: the foil's own form (the W6b pair, imported); the other three are this story's.
ORACLE_PAIRS: dict[str, tuple[str, str]] = {
    "marginal": ("oracle_marginal", "matched_marginal"),
    "knn_quantile": ("oracle_knn", "matched_knn"),
    "lgbm_hurdle_tail": ("oracle_hurdle", "matched_hurdle"),
    "count_negbin": ("oracle_negbin", "matched_negbin"),
}
ANCHORS: tuple[str, ...] = (
    *DEGENERATES, "permuted_knn",
    *(lab for pair in ORACLE_PAIRS.values() for lab in pair))

#: ⭐ Batter-Props Ph2 `tie_with_foil`: `knn_quantile` NESTS the foil (k → n_position rows
#: reproduces the per-position climatology exactly), so a winner's lead within numerical
#: precision of zero is a COLLAPSE onto the foil = a TIE, never a win. 1e-4 CRPS sits ~200×
#: below the W6b real effect on this cell (0.0194) and ~100× above a float-precision tie.
TIE_EPS_CRPS = 1e-4

#: REPORT-ONLY points-units weight (⛔ never a gate): a rushing TD is 6 PPR points.
PPR_WEIGHT_RUSH_TD = 6.0

#: NB2 dispersion bounds: Var = μ + α·μ²; α at the floor ⇒ the Poisson special case (nested,
#: declared — the Batter-Props Ph2 collapse direction, visible in the recorded alpha).
NB_ALPHA_FLOOR = 1e-6
NB_ALPHA_CEIL = 50.0
NB_MU_FLOOR = 1e-6

KNN_K = SD.KNN_K
MIN_TAIL_N = SD.MIN_TAIL_N
FIT_LEVELS: tuple[float, ...] = WP.FIT_LEVELS
TEST_BLOCKS = WP.TEST_BLOCKS                    # the NF-W1 fold axis, verbatim
PURGE_WEEKS = WP.PURGE_WEEKS
POSITIONS = WP.POSITIONS
PBO_MAX, DSR_MIN, FDR_Q = WP.PBO_MAX, WP.DSR_MIN, WP.FDR_Q
COVERAGE_FLOOR, COVERAGE_BLOCK_SE = WP.COVERAGE_FLOOR, WP.COVERAGE_BLOCK_SE
CAPTURE_ERA_FOLDS: tuple[str, ...] = EM.CAPTURE_ERA_FOLDS

# Shared machinery — IMPORTED, never re-typed (NF-W2d discipline). The two carried arms ARE the
# W6b pinned code paths, by identity (guard-tested), so this field re-derives nothing.
arm_lgbm_hurdle_tail = SD.arm_lgbm_hurdle_tail
arm_knn_quantile = SD.arm_knn_quantile
mixture_quantiles199 = SD.mixture_quantiles199
structural_coverage_note = SD.structural_coverage_note
score_bank = EM.score_bank                       # ONE reducer; refuses non-finite (NF-W3 (b))
cell_crps_matrix = EM.cell_crps_matrix
paired_ci95 = GE.paired_ci95
direction_word = GE.direction_word
verdict_sentence = GE.verdict_sentence
gate_sensitivity = GE.gate_sensitivity
matched_n_train = GE.matched_n_train


def cells() -> tuple[str, ...]:
    return (CELL,)


def all_labels() -> tuple[str, ...]:
    return (*REAL_ARMS, *FOILS, *ANCHORS)


def eligible_labels() -> list[str]:
    """The set the selection actually searches — real arms + the foil. Anchors NEVER enter
    (NF1.8/MH2.1 (a): a deflation statistic over a field containing its own anchors measures
    the anchors)."""
    return [*REAL_ARMS, *FOILS]


def _y(df: pd.DataFrame, stat: str = STAT) -> np.ndarray:
    return pd.to_numeric(df[stat], errors="coerce").fillna(0.0).to_numpy(dtype=float)


# ── Permutation substrate (the SD shape, re-seeded for the FRESH field) ─────────────────────────
def permute_stat_within_pos_week(train: pd.DataFrame, stat: str = STAT) -> np.ndarray:
    """Labels permuted WITHIN (position, global week) — destroys the row-level feature→label
    link, preserves every position-week marginal. Same substrate shape as
    `SD.permute_stat_within_pos_week`, seeded from THIS story's fresh seed (a fresh
    registration re-seeds its permutation, it does not inherit the old field's draw)."""
    rng = np.random.default_rng(np.random.SeedSequence([_SEED, zlib.crc32(stat.encode())]))
    y = _y(train, stat).copy()
    keys = train["position"].astype(str) + "|" + train["gw"].astype(str)
    for _, idx in pd.Series(np.arange(len(train)), index=keys.to_numpy()).groupby(level=0):
        posn = idx.to_numpy()
        if len(posn) > 1:
            y[posn] = y[rng.permutation(posn)]
    return y


# ── The discrete-count class (the PM-named third arm) ───────────────────────────────────────────
def _assert_integer_counts(y: np.ndarray) -> np.ndarray:
    """A count likelihood on non-integer labels silently scores garbage (scipy's discrete pmf is
    0 off the lattice → −inf loglik) — REFUSE loudly instead (NF1.7 (a) / NF-W3 (b))."""
    yv = np.asarray(y, dtype=float)
    if not np.isfinite(yv).all() or not np.allclose(yv, np.round(yv)):
        raise ValueError("count_negbin: labels are not integer-valued counts — refusing "
                         "(a discrete pmf off the integer lattice is 0, not an approximation)")
    return np.round(yv).astype(int)


def _nb2_negloglik(alpha: float, y: np.ndarray, mu: np.ndarray) -> float:
    from scipy.stats import nbinom
    r = 1.0 / max(float(alpha), NB_ALPHA_FLOOR)
    p = r / (r + np.maximum(mu, NB_MU_FLOOR))
    return -float(np.sum(nbinom.logpmf(y, r, p)))


def fit_nb2_dispersion_by_pos(mu: np.ndarray, y: np.ndarray, pos: np.ndarray) -> dict[str, float]:
    """Per-position NB2 dispersion α (Var = μ + α·μ²) by bounded MLE around the given means.
    A thin position falls back to the POOLED fit (the `residual_bank199` convention); a thin
    POOLED sample REFUSES (NF1.7 (a)). α at `NB_ALPHA_FLOOR` ⇒ Poisson (nested, declared)."""
    from scipy.optimize import minimize_scalar
    yv = _assert_integer_counts(y)
    muv = np.maximum(np.asarray(mu, dtype=float), NB_MU_FLOOR)
    if len(yv) < EM.MIN_BANK_ROWS:
        raise ValueError(f"NB2 dispersion fit on {len(yv)} rows < {EM.MIN_BANK_ROWS} — "
                         f"refusing (NF1.7 (a))")

    def _fit(sel: np.ndarray) -> float:
        res = minimize_scalar(_nb2_negloglik, bounds=(NB_ALPHA_FLOOR, NB_ALPHA_CEIL),
                              args=(yv[sel], muv[sel]), method="bounded")
        return float(res.x)

    pooled = _fit(np.ones(len(yv), dtype=bool))
    out: dict[str, float] = {}
    for p in POSITIONS:
        sel = np.asarray(pos) == p
        out[p] = _fit(sel) if int(sel.sum()) >= EM.MIN_BANK_ROWS else pooled
    return out


def nb2_bank199(mu: np.ndarray, alpha_by_pos: dict[str, float], pos: np.ndarray) -> np.ndarray:
    """The NB2 quantile function at the dense grid, per row (Poisson at the α floor). Monotone
    by construction (a ppf is nondecreasing in its level)."""
    from scipy.stats import nbinom, poisson
    muv = np.maximum(np.asarray(mu, dtype=float), NB_MU_FLOOR)
    out = np.empty((len(muv), len(EVAL_LEVELS)))
    for p in POSITIONS:
        sel = np.asarray(pos) == p
        if not sel.any():
            continue
        a = float(alpha_by_pos[p])
        m = muv[sel][:, None]
        if a <= NB_ALPHA_FLOOR * (1.0 + 1e-9):
            out[sel] = poisson.ppf(EVAL_LEVELS[None, :], m)
        else:
            r = 1.0 / a
            out[sel] = nbinom.ppf(EVAL_LEVELS[None, :], r, r / (r + m))
    return out


def arm_count_negbin(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                     stat: str = STAT) -> tuple[np.ndarray, dict]:
    """The discrete-count class: champion-head LGBM mean (`EM.fit_head_mean`, verbatim) +
    per-position NB2 dispersion fit by MLE on the PURGED calibration slice (the NF-MARGIN1
    lesson applied to a variance parameter: in-sample dispersion around a boosted mean is
    optimistically small). Predictive = the NB2 quantile function at the dense grid. Prices
    the atom PARAMETRICALLY — P(0) = NB2(0; μᵢ, α) — so a conditional mean signal moves P(0)
    row by row."""
    core, cal, note = MC.calibration_split(train)
    mu_cal = EM.fit_head_mean(core, cal, features, stat)
    alpha = fit_nb2_dispersion_by_pos(mu_cal, _y(cal, stat), cal["position"].to_numpy())
    mu_te = EM.fit_head_mean(train, test, features, stat)
    return (nb2_bank199(mu_te, alpha, test["position"].to_numpy()),
            {"alpha_by_pos": {k: round(v, 6) for k, v in alpha.items()}, **note})


# ── Per-form peeking oracles + matched-n controls (NF-D16 (g‴)/NF1.9 (f)) ───────────────────────
# Ceilings CROSS-FIT within the test block (no row sees its own label; `EM.crossfit_ids`,
# K = EM.CROSSFIT_K). Matched-n controls fit on a recent train window sized to the ORACLE'S
# EFFECTIVE fit size — (K−1)/K of the block, because a K-fold cross-fit peek trains on that
# many rows per fold — with WINDOW-IN-SAMPLE calibration (the `EM.matched_cand_quantile`
# declared bias: any optimism favors matched_n, making `oracle_beats_matched` HARDER to pass —
# conservative for the floor; the real arms' purged `calibration_split` cannot run on a
# block-sized window and would raise — NF1.7 (a)).
# ⚠️ Smoke amendment (2026-08-15, before the full run — recorded in the prereg §5): the first
# cut used the W6b `GE.matched_n_train` (a FULL block-size window), which handed the CONTROL
# ~1.5× the rows the cross-fit PEEK trains on — the pair was same-family but NOT same-sample
# (NF1.7 (b): a peeking kNN's capacity depends on n), and read as a near-tie for kNN/hurdle.
# The marginal pair keeps the W6b sizing (imported; the climatology is n-insensitive at these
# sizes) so its figure stays comparable to the W6b record.
def matched_window(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """The most recent train slice with about as many rows as the cross-fit oracle FITS ON —
    `len(test)·(K−1)/K` — the same-sample half of NF1.7 (b)."""
    n = max(int(round(len(test) * (EM.CROSSFIT_K - 1) / EM.CROSSFIT_K)), 50)
    return train.sort_values("gw").tail(n)


def oracle_knn(test: pd.DataFrame, features: list[str], stat: str, fold_label: str) -> np.ndarray:
    ids = EM.crossfit_ids(len(test), EM.CROSSFIT_K, fold_label, stat + "|knn")
    out = np.empty((len(test), len(EVAL_LEVELS)))
    for j in range(EM.CROSSFIT_K):
        hold = ids == j
        out[hold] = arm_knn_quantile(test.loc[~hold], test.loc[hold], features, stat)
    return out


def matched_knn(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                stat: str) -> np.ndarray:
    return arm_knn_quantile(matched_window(train, test), test, features, stat)


def oracle_hurdle(test: pd.DataFrame, features: list[str], stat: str,
                  fold_label: str) -> np.ndarray:
    """The hurdle form's block peek: cross-fit P(0) + cross-fit conditional knots; tails from
    the block's own nonzero exceedances over those knots (the residual-DISTRIBUTION peek is
    deliberate — that IS the realized regime, mirroring `EM.oracle_head_bank`)."""
    ids = EM.crossfit_ids(len(test), EM.CROSSFIT_K, fold_label, stat + "|hurdle")
    y = _y(test, stat)
    p0 = np.empty(len(test))
    knots = np.empty((len(test), len(FIT_LEVELS)))
    for j in range(EM.CROSSFIT_K):
        hold = ids == j
        tr = test.loc[~hold]
        y_tr = _y(tr, stat)
        clf = SD._hurdle_clf()
        clf.fit(EM._X_pos(tr, features), (y_tr == 0.0).astype(int))
        p0[hold] = clf.predict_proba(EM._X_pos(test.loc[hold], features))[:, 1]
        knots[hold] = EM.fit_cand_knots(tr.loc[y_tr != 0.0], test.loc[hold], features, stat)
    nz = y != 0.0
    tails = EM.tail_betas_by_pos(knots[nz], y[nz], test["position"].to_numpy()[nz])
    cond199 = EM.knots_to_eval(knots, tails, test["position"].to_numpy())
    out = np.empty((len(test), len(EVAL_LEVELS)))
    for i in range(len(test)):
        out[i] = mixture_quantiles199(p0[i], cond199[i])
    return out


def matched_hurdle(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                   stat: str) -> np.ndarray:
    window = matched_window(train, test)
    y_w = _y(window, stat)
    clf = SD._hurdle_clf()
    clf.fit(EM._X_pos(window, features), (y_w == 0.0).astype(int))
    p0 = clf.predict_proba(EM._X_pos(test, features))[:, 1]
    nz_w = window.loc[y_w != 0.0]
    knots_te = EM.fit_cand_knots(nz_w, test, features, stat)
    w_knots = EM.fit_cand_knots(nz_w, nz_w, features, stat)
    tails = EM.tail_betas_by_pos(w_knots, y_w[y_w != 0.0], nz_w["position"].to_numpy())
    cond199 = EM.knots_to_eval(knots_te, tails, test["position"].to_numpy())
    out = np.empty((len(test), len(EVAL_LEVELS)))
    for i in range(len(test)):
        out[i] = mixture_quantiles199(p0[i], cond199[i])
    return out


def oracle_negbin(test: pd.DataFrame, features: list[str], stat: str,
                  fold_label: str) -> np.ndarray:
    ids = EM.crossfit_ids(len(test), EM.CROSSFIT_K, fold_label, stat + "|negbin")
    mu = np.empty(len(test))
    for j in range(EM.CROSSFIT_K):
        hold = ids == j
        mu[hold] = EM.fit_head_mean(test.loc[~hold], test.loc[hold], features, stat)
    alpha = fit_nb2_dispersion_by_pos(mu, _y(test, stat), test["position"].to_numpy())
    return nb2_bank199(mu, alpha, test["position"].to_numpy())


def matched_negbin(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                   stat: str) -> np.ndarray:
    window = matched_window(train, test)
    mu_w = EM.fit_head_mean(window, window, features, stat)
    alpha = fit_nb2_dispersion_by_pos(mu_w, _y(window, stat), window["position"].to_numpy())
    mu_te = EM.fit_head_mean(window, test, features, stat)
    return nb2_bank199(mu_te, alpha, test["position"].to_numpy())


# ── Multiplicity (single-cell family, declared) ─────────────────────────────────────────────────
def fdr_single_cell(p_one_sided: float | None) -> dict:
    """BH at q over a ONE-member family reduces to p ≤ q (m=1 ⇒ cutoff q·1/1). Declared up
    front: this fresh registration's multiplicity family is exactly this cell — there is no
    second member to pool with, and borrowing W6b's families would re-open the retired field.
    An unevaluable p can never pass (NF1.7 (a))."""
    ok = p_one_sided is not None and float(p_one_sided) <= FDR_Q
    return {"family": [CELL], "m": 1, "binding_cutoff": FDR_Q, "pass": bool(ok)}


# ── Gate composition (SEPARATE named clauses — NF-D20: never bundle) ────────────────────────────
W6BC_STATISTICAL_CHECKS: tuple[str, ...] = (
    "beats_foil", "fold_consistency", "pbo_ok", "dsr_ok", "fdr_ok")
#: The coverage floor is a CONSTRAINT (NF1.8) — its refusal classifies CONSTRAINT_REFUSED,
#: never POWER_LIMITED (the NF-W7 classifier rule).
W6BC_CONSTRAINT_CHECKS: tuple[str, ...] = ("coverage_floor_ok",)
W6BC_ANCHOR_CHECKS: tuple[str, ...] = (
    "degenerates_lose", "permutation_behaves", "not_a_foil_tie", "winner_own_form_floor")


def compose_gate_w6bc(sel: dict, fdr_pass: bool) -> dict:
    checks = {
        "beats_foil": bool(sel["beats_foil"]),
        "fold_consistency": bool(sel["fold_clause"]["passes"]),
        "pbo_ok": sel["pbo"] is not None and sel["pbo"] < PBO_MAX,
        "dsr_ok": sel["dsr"] is not None and sel["dsr"] >= DSR_MIN,
        "fdr_ok": bool(fdr_pass),
        "coverage_floor_ok": not sel["coverage"]["blocking_shortfall"],
        "degenerates_lose": bool(sel["anchors"]["nihilist_loses"]
                                 and sel["anchors"]["zero_width_loses"]
                                 and sel["anchors"]["max_width_loses"]),
        "permutation_behaves": bool(sel["anchors"]["winner_beats_permuted"]
                                    and sel["anchors"]["permuted_lift_not_significant"]),
        # ⭐ Batter-Props Ph2: `knn_quantile` nests the foil — a lead within numerical precision
        # is a COLLAPSE, classified TIE, never a win.
        "not_a_foil_tie": bool(sel["mean_delta"] is not None
                               and sel["mean_delta"] > TIE_EPS_CRPS),
        # ⭐ NF-D16 (g‴)/NF1.9 (f): the winner's OWN form's block peek must beat that form's
        # matched-n control — per form, because nested forms make a single field-wide ceiling
        # a false veto. An absent reading fails closed (NF1.7 (a)).
        "winner_own_form_floor": bool(sel["anchors"].get(
            "winner_own_form_oracle_beats_matched", False)),
    }
    return {"checks": checks, "ship": all(checks.values())}


# ── Null classification ─────────────────────────────────────────────────────────────────────────
def classify_w6bc_null(sel: dict, checks: dict, n_folds: int) -> dict | None:
    """SHIP → None. A null resting ONLY on constraint/anchor clauses → CONSTRAINT_REFUSED
    (hand — `cv_power` has no such state, and a sample-size trigger for a directional refusal
    is the NF-D18 actively-misleading direction). A STATISTICAL null → `cv_power.classify_null`
    with `declared_field_size` stated (MH2.7), the verdict carrying the machine flag
    `field_remedy_admissible` — read that, never the prose (guide §0.5.4 rules 5/5b)."""
    if all(checks.values()):
        return None
    stat_fail = [c for c in W6BC_STATISTICAL_CHECKS if not checks[c]]
    other_fail = [c for c in (*W6BC_CONSTRAINT_CHECKS, *W6BC_ANCHOR_CHECKS) if not checks[c]]
    if not stat_fail:
        return {
            "state": "CONSTRAINT_REFUSED",
            "reason": (f"every statistical gate passed and the null rests entirely on "
                       f"constraint/anchor clauses {other_fail} — more data cannot change a "
                       f"directional constraint refusal (NF-D18/NF-W7)."),
            "retest_trigger": None,
            "failing_checks": other_fail,
            "classifier": "hand (the cv_power CONSTRAINT_REFUSED gap — NF-D18/NF-W7)",
        }
    from scipy.stats import kurtosis, skew
    d = np.asarray(sel["deltas_by_fold"], dtype=float)
    trial_srs = np.asarray(sel["trial_srs"], dtype=float)
    var_trials = (float(np.var(trial_srs, ddof=1)) if len(trial_srs) >= 2 else None)
    v = cv_power.classify_null(
        metric=f"{PRIMARY_METRIC}|{CELL}",
        n_folds=int(n_folds), n_arms=len(REAL_ARMS),
        beats_foil=bool(sel["beats_foil"]),
        observed_sr=sel["observed_sr"],
        var_trials_sr=var_trials,
        fold_wins=sel["fold_wins"],
        p_one_sided=sel["p_one_sided"], bh_cutoff=FDR_Q,
        skew=float(skew(d)) if len(d) >= 3 else 0.0,
        kurt=float(kurtosis(d, fisher=False)) if len(d) >= 3 else 3.0,
        # Provenance (DSR-CONV): TRUE means the V handed over contains no pre-registered
        # lose-by-construction degenerate — here none is in the trial field AT ALL (anchors
        # never enter trials — MH2.1 (a)), so the statement is structural, not a convention.
        degenerates_excluded_from_v=True,
        declared_field_size=DECLARED_FIELD_SIZE,
    )
    out = asdict(v)
    out["failing_checks"] = stat_fail + other_fail
    out["classifier"] = ("cv_power.classify_null (declared_field_size stated — MH2.7; "
                         "read field_remedy_admissible, never the prose)")
    return out


# ── REPORT-ONLY layers ──────────────────────────────────────────────────────────────────────────
def benchmark_sr0(trial_srs: list[float] | np.ndarray) -> float | None:
    """The field's deflated benchmark SR0 (√V·z(N)) — REPORTED so the W6b→W6b-C mechanism is
    legible: the fresh coherent family should carry a far smaller cross-trial dispersion than
    the field the linear arm inflated (W6b: sr0 ≈ 7.32 against the winner's 6.47)."""
    srs = np.asarray(trial_srs, dtype=float)
    srs = srs[np.isfinite(srs)]
    if len(srs) < 2:
        return None
    return round(float(cv_power.dsr_benchmark_sr0(len(srs),
                                                  float(np.var(srs, ddof=1)))), 4)


def ppr_points_note(mean_delta: float | None) -> dict:
    """CRPS lift × 6.0 (a rushing TD's PPR weight) = a points-units MARGINAL contribution.
    ⛔ REPORT-ONLY (the W6b PM ruling): never a gate, never an assembled joint-points claim."""
    pts = None if mean_delta is None else round(float(mean_delta) * PPR_WEIGHT_RUSH_TD, 4)
    return {"points_units": pts,
            "note": ("REPORT-ONLY — winner-vs-foil CRPS lift × the 6.0 PPR rushing-TD weight; "
                     "a MARGINAL contribution in points units, NOT an assembled-points claim.")}
