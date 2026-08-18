"""NF-W7i — the DIRECT-POINTS improvement ceiling at RB (an oracle-first MEASUREMENT, not a bake-off).

⚖️ `best_alpha = 0` · **deploy-held** · research-only · promotes nothing, publishes nothing.

## Why this module exists

NF-W7h settled the RB architecture question: assembly-from-parts genuinely LOSES at RB — the
direct-points foil beat the assembly winner by **0.0263 CRPS** even after the marginal-layer
zero-mass recalibration. RB's remaining value therefore lives in the DIRECT-POINTS form. NF-W6
exists precisely to SIZE that headroom **before** committing a §0.5 bake-off to it: a small
ceiling is a COMPLETE result ("RB is already near-optimal in direct-points") at a fraction of a
bake-off's cost, and a large one licenses a successor.

## ⭐ The premise correction this module is built on (measured, not assumed)

The story card motivates the work with NF-W7h's recorded `oracle__foil_direct_points` = **1.4933**
against the honest arm's 2.4692 — a ~39.5% apparent ceiling. **That figure is not a ceiling.**
`run_nf_w7h_rb_marginal.py` builds it as `KW.fit_direct_points(te_p, te_p, ...)` — nine
200-estimator LGBM quantile learners FIT ON THE TEST BLOCK AND PREDICTED ON THE SAME ROWS. Every
row sees its own label, so the number is a **row-level in-sample memorisation degenerate**, which
the NF-W6 pre-registration names in as many words: *"A ROW-level peek is a zero-CRPS degenerate,
not a ceiling."* It was harmless in NF-W7h (it gated nothing there — `FOILS_WITH_ORACLE` only ever
asked the arm to beat it) but it cannot carry a ceiling claim, and this story's whole object is
that ceiling. Reproduced on fold `2025H2`: in-sample 1.4663 vs the honest arm 2.4347.

⇒ NF-W7i measures the ceiling with **cross-fit (K=3) peeks that no row's own label reaches**, and
every form carries a **matched-n control** so a peek that merely fits differently cannot be read
as headroom (NF1.7 (b) / NF1.9 (f) / NF-W6b-C).

## ⭐ The measurement problem this module had to solve, and the bracket that solves it

A block-only cross-fit peek — NF-W6's literal construction — is **capacity-starved** here. RB test
blocks are ~1,025-1,126 rows; cross-fit at K=3 leaves the peek ~700 rows to fit a nine-knot,
200-estimator quantile bank, against an honest arm trained on 13k-20k rows. Measured on fold
`2025H2`: the block-only peek scores **2.6180 — WORSE than the arm's 2.4347**, i.e. a NEGATIVE
ceiling, and it loses to its OWN matched-n control (2.5483). That is precisely the failure mode
NF-W7h's own §2 note predicts ("a Σ peeked on a small block LOSES more to sample size than the
peek gains — which is how a per-form floor goes INACTIVE") and NF-W6d's rule for reading it: an
oracle that ties or loses to its own matched-n control is **INACTIVE — uninformative, never a NO**
(NF-D20: count whether the mechanism could ACT before crediting a pass or a refusal).

So the block-only peek alone cannot answer the question. The cure is to **bracket** the ceiling
with peeks that differ in how much regime knowledge they carry at FULL capacity:

| form | what it knows | the bias it carries |
|---|---|---|
| `direct_blockonly` | the block's regime ONLY, at ~700 rows | starved — a LOWER bound dominated by sample size |
| `direct_augmented` | everything the arm knows **+** the block's own rows at weight 1 | the CEILING-MAXIMISING same-family peek (measured); the headline |
| `direct_upweighted` | the same, with the block upweighted to `LAMBDA_DIAG` | the starvation BRIDGE — a declared diagnostic, not a ceiling candidate |
| `recal_block` | the arm's own conditional location **+** the block's realised residual law | a calibration-layer ceiling (low-capacity, never starved) |
| `climatology_block` | the block's unconditional marginal | n-insensitive; the honest discrete null |

The augmented peeks hold CAPACITY fixed at the arm's (train ∪ block) and turn only the knob that
matters — how much the fit is allowed to learn the test block's own regime. Their **matched-n
control is the same construction with the peeked block replaced by an equally-sized,
equally-weighted slice of the most recent TRAIN rows**, so the pair differs in exactly one thing:
whether the extra rows are the future (peek) or the recent past (honest). That is the same-family
AND same-sample control NF1.7 (b) requires, and it is what makes "the gap is FORM" vs "the gap
needs INFORMATION" an attribution rather than an assertion — in particular it is the ONLY thing
that separates a genuine regime peek from plain RECENCY WEIGHTING, which at λ=1 would otherwise
look identical.

⭐ **The weight sweep is the bridge between the brackets.** Measured on fold `2025H2`, the ceiling
falls MONOTONICALLY as the block's weight rises (λ=1 → +0.54%; λ=5 → +0.13%; λ=20 → −5.13%; λ=60 →
numerically degenerate). Since the block-only peek is the λ→∞ limit, that monotonicity is what
PROVES its negative ceiling is sample starvation rather than an absence of headroom — and it is
why λ=1 is the honest, ceiling-maximising headline.

⭐ **Declared bias direction (the NF-W5/NF-W6 rule): every choice here favours a BUILD.** The
ceiling is the MAX over declared forms (selection on the oracle side is upward-biased); the peek
sees the future; the headline λ is the sweep's most generous setting. **So a NO is conservative** —
and a NO is the outcome the bands are most likely to return.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from betting_ml.utils import cv_power
from quant_sports_intel_models.football.nfl.fantasy import efficiency_marginals as EM
from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA
from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KW
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

STORY = "NF-W7i"
PREDECESSOR = "NF-W7h"

#: ⛔ RB ONLY. NF-W7h certified the architecture question at RB and nowhere else; this record
#: certifies nothing about QB/WR/TE (NF1.7 (a)).
POSITION = "RB"

#: The dense grid + the metric, imported — never re-declared (the 39-level native grid is
#: structurally blind to beyond-grid tail work, NF-MARGIN2).
EVAL_LEVELS = FA.EVAL_LEVELS
N_LEVELS = FA.N_LEVELS
PRIMARY_METRIC = "crps_q199"

#: Cross-fit K and the ceiling bands are IMPORTED from the NF-W6 gate, so a band can never drift
#: between the story that set it and the story that reads it (NF-D16: the runner READS the constant).
CROSSFIT_K = EM.CROSSFIT_K
CEILING_BANDS = EM.CEILING_BANDS          # (2.0, 5.0): <2 NO · 2-5 MARGINAL · >=5 YES
FDR_Q = WP.FDR_Q                          # 0.10
MIN_BANK_ROWS = EM.MIN_BANK_ROWS          # 50 — a bank below this REFUSES (NF1.7 (a))

#: The incumbent: the honest, full-train direct-points arm — `KW.fit_direct_points`, the SAME
#: construction NF-W7h scored as `foil_direct_points`, by identity (a second implementation would
#: make this ceiling a claim about a re-derivation, not about the thing NF-W7h measured).
INCUMBENT = "direct_points"

#: ⭐ The block weights, DECLARED BEFORE THE FULL RUN from the 1-fold smoke sweep (fold `2025H2`,
#: recorded verbatim in the pre-registration §4) — the runner stamps what it ran with.
#:
#: The sweep measured the augmented ceiling as **MONOTONE DECREASING in the block's weight**:
#: λ=1 → +0.54% · λ=5 → +0.13% · λ=20 → −5.13% · λ=60 → numerically degenerate (CRPS 235.6, a
#: blown tail fit). So `LAMBDA_AUGMENTED = 1` is the CEILING-MAXIMISING setting — the declared
#: bias favours BUILD and cannot manufacture a NO.
#:
#: ⭐ That monotonicity is itself the story's key diagnostic, which is why λ=5 is carried as a
#: declared form rather than dropped: it is the BRIDGE between the two brackets. The block-only
#: peek is the λ→∞ limit, so a ceiling that falls monotonically as the block's weight RISES proves
#: the block-only peek's negative ceiling is SAMPLE STARVATION, not an absence of headroom. Reading
#: the block-only figure as "no headroom" without this bridge would be the NF-W6d error (an
#: INACTIVE anchor pair read as a refusal).
LAMBDA_AUGMENTED = 1.0
LAMBDA_DIAG = 5.0

#: A peek that blows up numerically must never be scored as a ceiling. λ=60's tail fit produced a
#: CRPS ~97× the climatology null; `assert_finite_predictive` cannot see that (the bank is finite,
#: just absurd), so the activity clause is what excludes it — an oracle worse than its own matched-n
#: control is INACTIVE and never enters the headline max (NF1.7 (a)).
LAMBDA_BY_FORM = {"direct_augmented": LAMBDA_AUGMENTED, "direct_upweighted": LAMBDA_DIAG}

#: The declared oracle forms. Each is a (peek, matched-n control) PAIR — NF-D16 (g‴): one ceiling
#: per FORM, never one ceiling for the field, because a single ceiling falsely vetoes a
#: legitimately-better nested form.
ORACLE_FORMS: tuple[str, ...] = (
    "direct_blockonly", "direct_augmented", "direct_upweighted", "recal_block", "climatology_block",
)

#: Degenerate anchors — scored EVERY run and never reasoned about (NF-D14). `nihilist_zero` losing
#: is the metric-soundness proof on a zero-heavy target (RB's realised all-zero rate is 0.3359 per
#: NF-W7h): an all-zero arm winning would mean the metric is inverted (NF-D11's MAE trap).
DEGENERATES: tuple[str, ...] = ("nihilist_zero", "zero_width", "max_width")

#: The permutation anchor: the incumbent form fit on labels shuffled WITHIN a global week — the
#: level of the target is preserved, only its per-row assignment is destroyed. It must LOSE.
PERMUTATION = "permuted_direct"

ALL_LABELS: tuple[str, ...] = (
    (INCUMBENT,)
    + tuple(f"oracle__{f}" for f in ORACLE_FORMS)
    + tuple(f"matched_n__{f}" for f in ORACLE_FORMS)
    + DEGENERATES + (PERMUTATION,)
)

oracle_of = EM.oracle_of if hasattr(EM, "oracle_of") else (lambda f: f"oracle__{f}")
matched_n_of = EM.matched_n_of if hasattr(EM, "matched_n_of") else (lambda f: f"matched_n__{f}")
paired_ci95 = GE.paired_ci95
direction_word = GE.direction_word


# ── The target ─────────────────────────────────────────────────────────────────────────────────
def points_target(frame: pd.DataFrame, realized: np.ndarray, weights: np.ndarray) -> pd.DataFrame:
    """Attach `FA.TARGET` (league points) through `FA.score_realized` — the SAME linear form the
    predecessors score, so this story's target can never drift from NF-W7h's."""
    out = frame.copy()
    out[FA.TARGET] = FA.score_realized(realized, weights)
    return out


def _bank(values: np.ndarray) -> np.ndarray:
    """An RB-scoped empirical bank on the dense grid. REFUSES a thin sample (NF1.7 (a)) — a bank
    that failed to fit must never silently become a passing anchor.

    ⛔ Deliberately NOT `EM.climatology_bank`/`EM.residual_bank199`: those iterate the four-position
    `EM.POSITIONS` and raise on any position absent from the frame, which is every frame in this
    RB-only story. Same arithmetic, RB scope, explicit refusal.
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) < MIN_BANK_ROWS:
        raise ValueError(f"{STORY}: bank fit on {len(v)} rows < {MIN_BANK_ROWS} — REFUSED, never "
                         f"defaulted (NF1.7 (a))")
    return np.quantile(v, EVAL_LEVELS)


# ── The incumbent form, and the same-family weighted variant the upweighted peek needs ──────────
def fit_direct(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
               *, y_train: np.ndarray | None = None,
               sample_weight: np.ndarray | None = None) -> np.ndarray:
    """`KW.fit_count_lgbm` with an OPTIONAL sample weight — hyperparameters, knot levels and the
    exponential mean-excess tail construction BYTE-IDENTICAL to `KW.fit_direct_points`.

    ⭐ The weight is the ONLY difference, and it exists so `direct_upweighted` can hold CAPACITY
    fixed while turning the regime-knowledge knob (see the module docstring). With
    `sample_weight=None` this delegates to `KW.fit_direct_points` outright, so the incumbent is the
    predecessor's object by identity rather than by a re-implementation that could drift.
    """
    if sample_weight is None:
        return KW.fit_direct_points(train, test, features, FA.TARGET, y_train=y_train)

    Xtr, Xte = KW._X(train, features), KW._X(test, features)
    y = train[FA.TARGET].to_numpy(float) if y_train is None else np.asarray(y_train, float)
    w = np.asarray(sample_weight, dtype=float)
    if len(w) != len(y):
        raise ValueError(f"{STORY}: sample_weight is {len(w)} for {len(y)} rows — REFUSED")
    ok = np.isfinite(y)
    knots_te = np.empty((len(test), len(KW.FIT_LEVELS)))
    knots_tr = np.empty((int(ok.sum()), len(KW.FIT_LEVELS)))
    for j, a in enumerate(KW.FIT_LEVELS):
        m = WP._lgbm({"objective": "quantile", "alpha": a, "n_estimators": 200,
                      "num_leaves": 31, "min_child_samples": 30})
        m.fit(Xtr[ok], y[ok], sample_weight=w[ok])
        knots_te[:, j] = m.predict(Xte)
        knots_tr[:, j] = m.predict(Xtr[ok])
    tail = KW.fit_knot_tail_betas(knots_tr, y[ok])
    return KW.dense_bank_from_knots(knots_te, tail, clip_lo=0.0)


# ── The peeks (cross-fit; no row's own label reaches its own prediction) ────────────────────────
def _ids(n: int, fold_label: str, tag: str) -> np.ndarray:
    """`EM.crossfit_ids` by identity — it REFUSES K < 2 ('a 1-fold cross-fit is an in-sample fit
    and the oracle would memorize rows'), which is the exact defect this story corrects."""
    return EM.crossfit_ids(n, CROSSFIT_K, fold_label, tag)


def matched_window(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """The most recent TRAIN slice sized to what the cross-fit peek actually FITS ON —
    `len(test)·(K−1)/K` — the same-sample half of NF1.7 (b).

    ⛔ NOT `GE.matched_n_train` (a FULL block-size window): that hands the control ~1.5× the rows
    the peek trains on, which is what made NF-W6b-C's kNN/hurdle pairs read as false near-ties.
    """
    n = max(int(round(len(test) * (CROSSFIT_K - 1) / CROSSFIT_K)), MIN_BANK_ROWS)
    return train.sort_values("gw").tail(n)


def oracle_blockonly(test: pd.DataFrame, features: list[str], fold_label: str) -> np.ndarray:
    """NF-W6's literal construction: the incumbent form re-fit WITHIN the block, cross-fit."""
    ids = _ids(len(test), fold_label, "blockonly")
    out = np.empty((len(test), N_LEVELS))
    for j in range(CROSSFIT_K):
        hold = ids == j
        out[hold] = fit_direct(test.loc[~hold], test.loc[hold], features)
    return out


def _augmented(train: pd.DataFrame, test: pd.DataFrame, extra: pd.DataFrame,
               features: list[str], lam: float, hold: np.ndarray) -> np.ndarray:
    """One cross-fit leaf of an augmented fit: train ∪ (λ-weighted `extra`) → predict the held rows."""
    aug = pd.concat([train, extra], ignore_index=True)
    w = np.concatenate([np.ones(len(train)), np.full(len(extra), float(lam))])
    return fit_direct(aug, test.loc[hold], features, sample_weight=w)


def oracle_augmented(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                     fold_label: str, lam: float, tag: str) -> np.ndarray:
    """The NON-starved same-family peek: everything the arm knows PLUS the block's own rows
    (weight `lam`), cross-fit so no row's own label reaches it."""
    ids = _ids(len(test), fold_label, tag)
    out = np.empty((len(test), N_LEVELS))
    for j in range(CROSSFIT_K):
        hold = ids == j
        out[hold] = _augmented(train, test, test.loc[~hold], features, lam, hold)
    return out


def matched_augmented(train: pd.DataFrame, test: pd.DataFrame, features: list[str],
                      fold_label: str, lam: float, tag: str) -> np.ndarray:
    """⭐ The control that makes the augmented peek an ATTRIBUTION rather than an assertion: the
    IDENTICAL construction with the peeked block replaced by an equally-sized, equally-weighted
    slice of the most recent TRAIN rows. Same family, same n, same weighting — the pair differs in
    exactly one thing: whether the extra rows are the FUTURE (peek) or the recent PAST (honest).
    """
    ids = _ids(len(test), fold_label, tag)
    out = np.empty((len(test), N_LEVELS))
    for j in range(CROSSFIT_K):
        hold = ids == j
        extra = train.sort_values("gw").tail(int((~hold).sum()))
        out[hold] = _augmented(train, test, extra, features, lam, hold)
    return out


def oracle_recal(arm_bank: np.ndarray, y: np.ndarray, fold_label: str) -> np.ndarray:
    """The calibration-layer peek: the ARM's own conditional location (its median, trained
    honestly) re-dressed in the BLOCK's realised residual law, cross-fit. Low-capacity by
    construction, so — unlike the full-form block peek — it can never be sample-starved."""
    n = len(y)
    loc = np.sort(arm_bank, axis=1)[:, N_LEVELS // 2]
    resid = np.asarray(y, float) - loc
    ids = _ids(n, fold_label, "recal")
    out = np.empty((n, N_LEVELS))
    for j in range(CROSSFIT_K):
        hold = ids == j
        out[hold] = loc[hold][:, None] + _bank(resid[~hold])[None, :]
    return out


def matched_recal(arm_bank: np.ndarray, train: pd.DataFrame, test: pd.DataFrame,
                  features: list[str]) -> np.ndarray:
    """The recalibration control: the same location re-dressed in the residual law of the matched
    recent-TRAIN window (window-in-sample — declared: any optimism here favours the CONTROL, i.e.
    makes `oracle_beats_matched_n` HARDER to claim, which is conservative for the floor)."""
    win = matched_window(train, test)
    loc_w = np.sort(fit_direct(win, win, features), axis=1)[:, N_LEVELS // 2]
    resid_w = win[FA.TARGET].to_numpy(float) - loc_w
    loc = np.sort(arm_bank, axis=1)[:, N_LEVELS // 2]
    return loc[:, None] + _bank(resid_w)[None, :]


def oracle_climatology(y: np.ndarray) -> np.ndarray:
    """The block's own unconditional marginal — n-insensitive, the honest discrete null."""
    return np.repeat(_bank(y)[None, :], len(y), axis=0)


def matched_climatology(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    return np.repeat(_bank(matched_window(train, test)[FA.TARGET].to_numpy(float))[None, :],
                     len(test), axis=0)


# ── Selection + decision (derived from stored fold scores — NF-W2e: zero refit to re-report) ────
def crps_matrix(fold_results: list[dict]) -> pd.DataFrame:
    rows = [fr["scores"] for fr in fold_results if "scores" in fr]
    if not rows:
        raise ValueError(f"{STORY}: no scored folds — REFUSED (NF1.7 (a))")
    # ⛔ The runner refuses a missing BANK, but `--rewrite-report` re-derives from a STORED
    # artifact and never passes through that check — and `pd.DataFrame` would quietly fill a
    # missing label with NaN, so a field scored with a label silently absent would be read as the
    # declared field (NF1.7 (a)). Refuse here too, on the path that re-reads the record.
    for i, r in enumerate(rows):
        missing = sorted(set(ALL_LABELS) - set(r))
        if missing:
            raise ValueError(f"{STORY}: fold {i} is missing declared labels {missing} — REFUSED; "
                             f"a field scored with a label silently absent is not the declared "
                             f"field (NF1.7 (a))")
    return pd.DataFrame(rows)


def select_ceiling(fold_results: list[dict], n_folds: int) -> dict:
    """The per-form ceilings, the headline ceiling (max over forms) and every anchor reading.

    ⭐ ACTIVITY IS READ BEFORE MAGNITUDE (NF-W6d / NF-D20). A form whose peek does not BEAT its own
    matched-n control could not ACT — its ceiling is UNINFORMATIVE and must never be read as a NO.
    The headline is the max over ACTIVE forms; if no form is active the ceiling is UNEVALUABLE,
    which is a statement about the instrument, not about RB.
    """
    crps = crps_matrix(fold_results)
    mean_crps = crps.mean(axis=0)
    inc = crps[INCUMBENT].to_numpy(dtype=float)
    mean_inc = float(np.mean(inc))
    clause = cv_power.fold_consistency_clause(n_folds)

    per_form: dict[str, dict] = {}
    for f in ORACLE_FORMS:
        d = inc - crps[oracle_of(f)].to_numpy(dtype=float)
        m, lo, hi = paired_ci95(d)
        o_mean, m_mean = float(mean_crps[oracle_of(f)]), float(mean_crps[matched_n_of(f)])
        active = bool(o_mean < m_mean)
        per_form[f] = {
            "oracle_mean": round(o_mean, 5), "matched_n_mean": round(m_mean, 5),
            "mean_delta": None if m is None else round(m, 5),
            "ci95": [None if lo is None else round(lo, 5), None if hi is None else round(hi, 5)],
            "fold_wins": int((d > 0).sum()),
            "ceiling_pct": None if mean_inc <= 0 or m is None else round(100.0 * m / mean_inc, 3),
            # NF1.9 (f) / NF-W6d: the peek is INFORMATIVE only if it beats the SAME form at matched
            # n. A tie or a loss = INACTIVE (the anchor pair could not act), never a refusal.
            "oracle_beats_matched_n": active,
            "activity": "ACTIVE" if active else "INACTIVE",
            "peek_gain_vs_matched_n": round(m_mean - o_mean, 5),
            "p_one_sided": M14.onesided_paired_pvalue(d),
        }

    active_forms = [f for f in ORACLE_FORMS if per_form[f]["oracle_beats_matched_n"]
                    and per_form[f]["mean_delta"] is not None]
    best = (max(active_forms, key=lambda f: per_form[f]["mean_delta"]) if active_forms else None)

    out = {
        "position": POSITION, "selection_metric": PRIMARY_METRIC,
        "n_rows": int(sum(fr["n"] for fr in fold_results if "n" in fr)),
        "fold_labels": [fr["label"] for fr in fold_results],
        "mean_crps": {k: round(float(v), 5) for k, v in mean_crps.items()},
        "incumbent": INCUMBENT, "mean_incumbent": round(mean_inc, 5),
        "per_form": per_form,
        "active_forms": active_forms,
        "best_form": best,
        "fold_clause": {"required": clause.wins_required, "attainable": clause.attainable},
        "anchors": {
            "nihilist_loses": bool(mean_crps[DEGENERATES[0]] > mean_inc),
            "zero_width_loses": bool(mean_crps[DEGENERATES[1]] > mean_inc),
            "max_width_loses": bool(mean_crps[DEGENERATES[2]] > mean_inc),
            "permutation_loses": bool(mean_crps[PERMUTATION] > mean_inc),
        },
        "estimator_note": (
            "MAX over the per-form cross-fit peeks vs the honest full-train incumbent. Every bias "
            "here favours a BUILD — selection over forms is upward-biased on the oracle side, the "
            "peek sees the future, and the headline block weight is the smoke sweep's most "
            "generous (ceiling-maximising) value — "
            "so a NO is CONSERVATIVE (the NF-W5/NF-W6 rule, declared before the run)."),
        "pbo": None,
        "pbo_state": ("UNDEFINED — the ceiling is a pre-registered anchor contrast, not a searched "
                      "field (the NF-W5/NF-W6 ceiling rule). DSR does not arise: no arm is "
                      "selected and nothing is promoted."),
    }
    if best is None:
        out.update({"deltas_by_fold": [], "mean_delta": None, "ci95": [None, None],
                    "fold_wins": 0, "p_one_sided": None, "ceiling_pct": None})
        return out

    deltas = inc - crps[oracle_of(best)].to_numpy(dtype=float)
    m, lo, hi = paired_ci95(deltas)
    out.update({
        "deltas_by_fold": [round(float(x), 5) for x in deltas],
        "mean_delta": None if m is None else round(m, 5),
        "ci95": [None if lo is None else round(lo, 5), None if hi is None else round(hi, 5)],
        "fold_wins": int((deltas > 0).sum()),
        "p_one_sided": M14.onesided_paired_pvalue(deltas),
        "ceiling_pct": None if m is None else round(100.0 * m / mean_inc, 3),
        # ⭐ the interval in the SAME units as the bands, so "does the evidence rule out a MATERIAL
        # ceiling?" is a direct read rather than an arithmetic exercise for the reader
        "ceiling_ci_pct": [None if lo is None else round(100.0 * lo / mean_inc, 3),
                           None if hi is None else round(100.0 * hi / mean_inc, 3)],
    })
    out["fold_clause"]["passes"] = clause.passes(out["fold_wins"])
    return out


def bh_binding(per_form: dict, q: float = FDR_Q) -> dict:
    """Benjamini-Hochberg over the DECLARED FORM FAMILY — the headline is a MAX over these five
    peeks, so the multiplicity the selection actually spends is the family, and BH must be read
    over it rather than over the single winner (MH2 (a))."""
    items = [(f, d["p_one_sided"]) for f, d in per_form.items() if d["p_one_sided"] is not None]
    if not items:
        return {"binding": {}, "cutoff": None, "family_size": 0,
                "note": "no evaluable p-value in the family — BH UNDEFINED, fails closed"}
    items.sort(key=lambda kv: kv[1])
    n = len(items)
    cutoff, k = None, 0
    for i, (_, p) in enumerate(items, start=1):
        if p <= q * i / n:
            cutoff, k = p, i
    return {"binding": {f: bool(cutoff is not None and p <= cutoff) for f, p in items},
            "cutoff": cutoff, "family_size": n, "n_rejected": k,
            "note": f"BH at q={q} over the {n} declared oracle forms"}


def decide(sel: dict, fdr: dict) -> dict:
    """NO / MARGINAL / YES on the NF-W5/NF-W6 bands, plus the two states those bands cannot
    express. Fails closed."""
    pct = sel.get("ceiling_pct")
    best = sel.get("best_form")
    lo = (sel.get("ci95") or [None, None])[0]

    if not sel["active_forms"]:
        return {
            "answer": "UNEVALUABLE", "licensed_for_bakeoff": False, "stat_ok": False,
            "reason": ("no declared form's peek beat its own matched-n control — every anchor pair "
                       "was INACTIVE, so the ceiling was not measured. NF1.7 (a): a check that "
                       "could not run is never a pass, and NF-W6d: an inactive pair is "
                       "UNINFORMATIVE, never a refusal. This is a statement about the instrument "
                       "at this block size, NOT a finding that RB has no headroom."),
        }

    stat_ok = bool(pct is not None and lo is not None and lo > 0
                   and sel["fold_clause"].get("passes")
                   and fdr.get("binding", {}).get(best) is True)
    if pct is None or not stat_ok:
        answer = "NO"
        reason = ("ceiling unevaluable — NO (fails closed)" if pct is None else
                  f"ceiling {pct:.2f}% on `{best}` is not statistically demonstrable "
                  f"(CI-excludes-zero {bool(lo is not None and lo > 0)}, fold clause "
                  f"{sel['fold_clause'].get('passes')}, BH binding "
                  f"{fdr.get('binding', {}).get(best)}) — NO regardless of magnitude")
    elif pct < CEILING_BANDS[0]:
        answer = "NO"
        reason = (f"ceiling {pct:.2f}% < the {CEILING_BANDS[0]}% band — RB's direct-points "
                  f"predictive is already near its ceiling; DEMONSTRABLE but IMMATERIAL, which "
                  f"the bands refuse by design (NF-W6's 'demonstrable ≠ material')")
    elif pct < CEILING_BANDS[1]:
        answer = "MARGINAL"
        reason = (f"ceiling {pct:.2f}% sits in the {CEILING_BANDS[0]}-{CEILING_BANDS[1]}% band — a "
                  f"PM decision; nothing is built in-session")
    else:
        answer = "YES"
        reason = (f"ceiling {pct:.2f}% >= {CEILING_BANDS[1]}% — a §0.5 bake-off on RB's "
                  f"direct-points form is licensed under a FRESH registration")
    return {"answer": answer, "stat_ok": stat_ok,
            "licensed_for_bakeoff": bool(answer in ("YES", "MARGINAL") and stat_ok),
            "reason": reason,
            "license_rule": ("licensed iff answer ∈ ('YES','MARGINAL') ∧ stat_ok — the NF-W6d "
                             "LICENSE_BANDS convention, declared before the run")}


def null_state(sel: dict, decision: dict, *, n_folds: int) -> dict:
    """`cv_power.classify_null` with `declared_field_size=` — and the machine flag read, never the
    prose (MH2.7: the instrument's own remedy text can prescribe a field below the declared
    minimum, which re-commits the selection bias it exists to deflate)."""
    if decision["answer"] == "UNEVALUABLE":
        return {"state": "UNDEFINED", "hand_note": (
            "every anchor pair INACTIVE ⇒ no verdict was reached; classify_null is NOT invoked "
            "(there is no measured contrast to classify)."), "field_remedy_admissible": None}
    v = cv_power.classify_null(
        metric=PRIMARY_METRIC, n_folds=n_folds, n_arms=len(ORACLE_FORMS),
        # ⛔ `bool(x or 0 > 0)` parses as `bool(x or (0 > 0))` and is TRUE for a NEGATIVE delta —
        # it would tell the classifier a negative ceiling beat its foil, inverting the null state.
        beats_foil=bool((sel.get("mean_delta") or 0.0) > 0),
        fold_wins=sel.get("fold_wins"), p_one_sided=sel.get("p_one_sided"),
        declared_field_size=len(ORACLE_FORMS))
    d = dataclasses.asdict(v) if dataclasses.is_dataclass(v) else (
        v._asdict() if hasattr(v, "_asdict") else dict(v))
    d["field_remedy_admissible"] = getattr(v, "field_remedy_admissible",
                                           (d.get("detail") or {}).get("field_remedy_admissible"))
    # ⛔ SCOPE GUARD (the story card, verbatim): RB gets NO season/fold re-test trigger. NF-W7h
    # measured RB's DSR as variance-bound and unreachable at any n, and the only sub-field that
    # moved it deleted the winning arm. A "come back with more seasons" trigger here would be the
    # misleading direction NF-D18/MH2 (g″) forbid.
    d["retest_trigger"] = None
    d["retest_trigger_note"] = (
        "⛔ NO season/fold re-test trigger is published for RB — pre-registered scope guard. A "
        "ceiling below the band is a MEASUREMENT of the form's headroom, not a power shortfall, "
        "and more seasons cannot move it.")

    # ⭐⭐ HAND-CORRECTION (the Nth in this vertical; `classify_null` is a shared instrument and its
    # DEFAULT branch is wrong for a BAND decision).
    #
    # `classify_null` answers "is the effect > 0?" and, given no detectability figure, FALLS THROUGH
    # to POWER_LIMITED — its own reason says "insufficient recorded statistics to certify the null
    # as powered". This story does not ask that question. It asks "is the ceiling ≥ the
    # pre-registered MATERIALITY band?", and on that question the evidence is DECISIVE rather than
    # thin: when the whole 95% interval lies BELOW the band, more folds tighten the interval around
    # a point estimate that is already far too small, so no fold count can change the verdict.
    #
    # Publishing POWER_LIMITED here would read as "underpowered — buy more seasons" for a bar the
    # data already exclude: the actively-misleading direction NF-D18 / MH2 (g″) forbid, and the very
    # thing this story's scope guard was pre-registered to prevent.
    # ⛔ The raw verdict is RETAINED verbatim under `classify_null_raw`, never overwritten (NF-D20).
    # ⛔ NARROW BY DESIGN — it fires ONLY on the instrument's POWER fall-through. A decisive state
    # must never be overwritten: `GENUINE_ABSENCE` (a NEGATIVE point estimate, which MH2 ranks
    # ABOVE the power states precisely because no n rescues it), `INACTIVE` and `UNDEFINED` all
    # carry strictly more information than "immaterial" and are left exactly as the instrument
    # returned them. Caught by an existing guard, which fired when a first cut swallowed a
    # GENUINE_ABSENCE.
    hi_pct = (sel.get("ceiling_ci_pct") or [None, None])[1]
    if d["state"] == "POWER_LIMITED" and hi_pct is not None and hi_pct < CEILING_BANDS[0]:
        d = {
            "state": "MEASURED_IMMATERIAL",
            "hand_corrected": True,
            "corrected_from": d["state"],
            "reason": (
                f"the 95% interval on the ceiling is [{sel['ceiling_ci_pct'][0]}%, {hi_pct}%] and "
                f"its UPPER bound sits {round(CEILING_BANDS[0] / hi_pct, 2)}× BELOW the "
                f"{CEILING_BANDS[0]}% materiality band — the evidence RULES OUT a material ceiling "
                f"rather than failing to detect one. This is a MEASUREMENT, not a power shortfall: "
                f"more folds tighten the interval around a point estimate {round(CEILING_BANDS[0] / (sel['ceiling_pct'] or 1), 1)}× "
                f"too small to reach the band."),
            "remedy": ("a DIFFERENT MECHANISM, never more data and never a smaller field — a "
                       "bake-off confined to this form cannot pay, which is exactly the question "
                       "the oracle gate was run to answer before funding one"),
            "retest_trigger": None,
            "retest_trigger_note": d["retest_trigger_note"],
            "classify_null_raw": {k: v for k, v in d.items() if k != "retest_trigger_note"},
            "field_remedy_admissible": d.get("field_remedy_admissible"),
            "field_remedy_note": (
                "absent because no FIELD remedy was prescribed — the instrument emits the MH2.7 "
                "flag only where it recommends a field size, and this state does not (the machine "
                "flag is read, never the prose)."),
        }
    return d
