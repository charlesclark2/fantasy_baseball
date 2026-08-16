"""season_level_recalibration.py — NF-TR2 pure model logic + PRE-REGISTRATION: recalibrate the
served VETERAN season-projection LEVEL (the per-game RATE) so the draft board's "expected points"
sits at the realized level, without moving the draft order.

⚠️ THIS FILE IS THE PRE-REGISTRATION. The population, the tier anchor, the forms, the estimator, the
band treatment, the metric, the constraints, the level gates, the deflation reading and its declared
field, and the anchor set are CONSTANTS written before the run; `run_nf_tr2_level.py` READS them.

════════════════════════════════════════════════════════════════════════════════════════════════════
0. WHAT THIS STORY IS, AND WHAT IT IS NOT (the NF-RECAL1 → NF-C3-REREAD → NF-B3 chain)
════════════════════════════════════════════════════════════════════════════════════════════════════
The veteran LEVEL has been selected on three times: NF-RECAL1 (refused by a mis-specified C3),
NF-C3-REREAD (the refusal corrected → POWER_LIMITED at 7 folds), NF-B3 (the full 13-fold selection →
POWER_LIMITED, whole-field DSR 0.877 < 0.95 over its declared 11-arm field, winner `pos_const·infold`
λ=0.25). None shipped. Nothing here re-litigates those records.

NF-TR2 is a FRESH REGISTRATION on the PM's brief, and it differs from NF-B3 in three ways that are
each stated up front, because the difference between "a coherent family declared in advance" and
"a field trimmed after it lost" is the whole of MH2 (a):

  (1) THE FAMILY. The brief declares it: "per-position constant vs per-position affine (slope) vs a
      no-op foil" — THREE trials. Mechanistic ground: NF-D16 ratified a per-position constant beating
      the incumbent on the rookie leg; the affine is the nested learned foil that contains the constant
      (a LOSS for it is the strongest evidence a constant is the right shape); the no-op is the null.
      ⛔ NOT re-derived by dropping NF-B3's losers: NF-B3's field held FIVE forms × TWO λ-rules and
      the whole-field DSR is reported here BESIDE the declared-field reading (`B3_FIELD_SR0`), so a
      reader sees both taxes on the same winner. NF-W6b-C / MARGIN2→3 / W7→W7b are the precedents:
      a DSR failure over a HETEROGENEOUS declared field is a hypothesis about the FIELD, and the
      sanctioned successor is a coherent registration up front — never a re-run and never a post-hoc
      trim. Whether the brief's family is admissible is the PM's call, and it is a fact about the
      brief (`DECLARED_FIELD_SOURCE`), not about this run.

  (2) THE ESTIMATOR. "Recalibrate to realized" — the per-position constant is the MEAN-MATCH
      `k_q = Σ realized / Σ projected` over the in-fold TIER rows, so the recalibrated tier level
      EQUALS the realized tier level in-fold BY CONSTRUCTION. There is no λ knob: NF-B3's λ was a
      shrink of a mean-of-ratios fit selected in-fold on CRPS; here the magnitude is a property of the
      estimator, and the interior-optimum question NF-D20 raises is answered by SCORING a λ-sweep of
      the mean-match as ANCHORS (none shippable) rather than by selecting on it. The affine is the
      per-GAME OLS `y ~ a·g + b·p` (NF-RECAL1's PRIMARY space, inherited by import) so an intercept
      enters the season total as `a·g` and the availability discount is never double-counted.

  (3) ⭐ THE BAND TREATMENT — measured, and it is the finding that explains NF-B3's λ. The band on
      the wire (`knn_norm k300`) is the q10/q90 of the REALIZED outcomes of the k training players
      NEAREST the incumbent's own projection, normalised by the position's realized level. It is a
      function of the LEVEL MODEL'S projections. NF-RECAL1/B3 applied every correction to the point
      AND both band edges (`apply_to_band`) — but the served path does not do that: NF1.5's derived
      board RE-DERIVES the band through `attach_season_interval` at whatever point it is handed. If
      the level model is recalibrated, the honest band is the one REFIT ON THE RECALIBRATED HISTORY,
      and because the knn's normaliser is the REALIZED level, that band is (to the cross-position
      neighbour composition) the incumbent's band UNCHANGED — the band already sat at the realized
      level; the POINT did not (measured on the 2013–2025 tier: the point sits at 0.46 of its band,
      the band midpoint 8 PPR above it at RB, the realized mean above both).
      Under the FIXED band the tier CRPS improves MONOTONICALLY through the mean-match (49.89 → 49.36
      at λ=1, in-sample optimum ≈ 1.25); under the SCALED band it turns at λ≈0.5 — which is exactly
      where NF-B3's in-fold rule landed.
      ⇒ `BAND_TREATMENT = "fixed"` is PRIMARY: the LEVEL moves, the NF1.9-validated band stays
      byte-identical (bracketed to the new point), and serving reproduces that exactly by querying
      the band model at the INCUMBENT-EQUIVALENT point (`invert_level`; the frame carries the form +
      params as stamp columns, so NF1.5's re-derivation through `attach_season_interval` lands on the
      same band). `"refit"` (band model refit on the recalibrated history, queried at the new point)
      and `"scaled"` (NF-B3's) are DISCLOSURES computed beside it.
      ⚠️ DECISION RECORD — decided after a 3-fold SMOKE and before the 13-fold run: `refit` was the
      first-cut primary. The smoke showed its cross-position neighbour RESHUFFLE (the pool is
      normalised by realized level and the correction is per position, so a query's neighbours
      change) moves per-position coverage by NOISE (−0.017 pooled) and trips C3's govern-the-change
      clause at TE — which sits under the floor for reasons NF1.9-R already recorded (0.739,
      CARRIED). That refusal measures band-model noise, not the level correction; the principle
      above ("the band already sits at the realized level; only the point moves") is stated EXACTLY
      by `fixed`, so `fixed` became primary on principle. Both are reported every run.

  Everything else is INHERITED BY IMPORT from `level_recalibration` (NF-RECAL1): the tier anchor and
  size, the CRPS reducer, the coverage-floor clause with NF-B3's canonical equality boundary, the
  ordering clause, the C2 placement machinery, the metric hierarchy (CRPS selects; MAE forbidden),
  the anchor set and the deflation levels (PBO < 0.2, whole-field DSR ≥ 0.95, α = 0.10).

════════════════════════════════════════════════════════════════════════════════════════════════════
1. STEP 1 — THE DECOMPOSITION (a measurement, computed before anything is fitted)
════════════════════════════════════════════════════════════════════════════════════════════════════
With `p = r̂·ĝ` (served point = per-game rate × expected games) and `y = r·g` (realized), the row
identity `p − y = r̂·(ĝ − g) + g·(r̂ − r)` is EXACT: the first term is the AVAILABILITY part (the
projected rate applied to the games shortfall — the honest injury discount, which STAYS), the second
the per-game RATE part (realized games × the rate gap; a zero-game season contributes nothing to it,
because there is no realized rate to be wrong about). `decompose_bias` reports both per position with
the pooled rate ratio `(Σp/Σĝ)/(Σy/Σg)`. Measured on the 2013–2025 incumbent-anchored tier: pooled bias
−12.85 = availability **+3.7** (we slightly OVER-project games on the tier) + rate **−16.6**; rate
ratio RB 0.864 · TE 0.837 · WR 0.848 · QB 0.985 ⇒ the miss is a per-position PROPORTIONAL rate
lowball, QB essentially calibrated — the shape a per-position constant on the RATE addresses.

════════════════════════════════════════════════════════════════════════════════════════════════════
2. THE GATES (all pre-registered; the level gates are THIS story's, the rest inherited)
════════════════════════════════════════════════════════════════════════════════════════════════════
  ELIGIBILITY (out-of-sample, EVERY fold, inherited): C1 within-position ρ ≥ 1 − 0.02 per position ·
  C2 the whole-board rookie placement cap (activity counted; a lift is structurally inactive on it) ·
  C3 per-position 80% coverage ≥ min(0.80, incumbent), equality-exact, pooled over rows.
  SELECTION: best out-of-fold pooled tier CRPS among the eligible; the winner must BEAT the no-op.
  DEFLATION: PBO(eligible) < 0.2 · whole-field DSR ≥ 0.95 over the DECLARED 3-trial field (anchors and
  disclosures are never trials) · one-sided paired p < 0.10. `classify_null(declared_field_size=3)`.
  LEVEL GATES on the winner (out-of-fold, pooled over the 13 folds' tier rows):
    L1 pooled |bias| reduced by ≥ `LEVEL_REDUCTION_MIN` (50%) vs the incumbent;
    L2 at EVERY position |bias| ≤ max(0.5·|bias_inc|, 2·SE) — a cold position must halve its miss,
       an already-calibrated one (QB) must stay within noise; SE = sd(y − p)/√n on that position's
       tier rows (a DESIGN quantity, known before any result);
    L3 NO INFLATION: the estimator targets the realized level (unit-tested: in-fold recalibrated mean
       == realized mean to 1e-9), the winner's pooled OOF bias ≤ +2·SE (never significantly HOT), and
       `over_scale` (2× the correction) LOSES the metric — a registered-to-lose anchor that wins is a
       refuted MAGNITUDE hypothesis and is reported as such, never re-labelled (NF-D20);
    L4 AVAILABILITY PRESERVED: `proj_games` is byte-identical before/after (the correction is on the
       rate); for the constant, season/ĝ scales by exactly k;
    L5 RANK PRESERVED: within-position order unchanged (ρ = 1 for the constant; the affine only iff
       b > 0 at every position — C1 refuses it otherwise) and the per-position Δρ vs realized is
       IDENTICAL to the incumbent's for a monotone map (asserted to 1e-12, not assumed);
    ⛔ NOTHING is selected on coverage headroom (NF1.8) and NO floor is moved (E2.1-r).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import level_recalibration as LR

# ══════════════════════════════════════════════════════════════════════════════════════════════
# The registration
# ══════════════════════════════════════════════════════════════════════════════════════════════
STORY = "NF-TR2"
MODEL_VERSION = "nfl_fantasy_nf_tr2_veteran_level_v1"
RECALIBRATES = LR.RECALIBRATES                      # the LEVEL model; ⛔ NOT the NF1.5 ordering layer
RECALIBRATED_POSITIONS = LR.RECALIBRATED_POSITIONS  # QB / RB / WR / TE
RECALIBRATED_LEG = "veteran"                        # ⛔ rookie leg CLOSED (NF-D21), inherited by import
EXCLUDED_LEGS = LR.EXCLUDED_LEGS

#: The declared trial field — the PM's brief, verbatim, is the document a reviewer audits this
#: claim against (MH2.7: `declared_field_size` is an auditable CLAIM about a document).
DECLARED_FIELD_SOURCE = (
    "NF-TR2 brief (2026-08-15): \"Pre-register the recalibration forms against matched foils, "
    "selected in-fold: per-position constant vs per-position affine (slope) vs a no-op foil.\"")
FORMS = ("pos_const", "pos_affine")                 # + the incumbent no-op = 3 trials
NOOP = "incumbent"
DECLARED_FIELD_SIZE = len(FORMS) + 1
LEARNED_FOIL = "pos_affine"
SPACE = LR.PRIMARY_SPACE                            # per_game — the intercept enters as a·g
FORM_NESTING = (("pos_const", "pos_affine"),)       # affine ⊃ constant (a = 0)

#: NF-B3's recorded whole-field expected-max-SR — the tax the SAME winner would carry inside NF-B3's
#: declared 11-arm field. Reported beside the declared-field DSR every run, so the narrower family
#: cannot quietly launder a result: both numbers sit on the same page.
B3_FIELD_SR0 = 0.271
B3_RECORDED = {"story": "NF-B3", "winner": "pos_const · infold λ=0.25", "dsr_whole_field": 0.8773,
               "n_trials_in_field": 8, "verdict": "RECORDED NULL — POWER_LIMITED"}

#: The estimator: mean-match on the in-fold TIER, per position. Below `MIN_FIT_ROWS` a position is
#: left at k = 1 (a missing estimate degrades to "leave it alone", never to a silent zero).
ESTIMATOR = "mean_match"
MIN_FIT_ROWS = 30
MULT_CLIP = LR.MULT_CLIP                            # inherited (0.5, 2.5) — a sanity clamp, not a tuner
LAMBDA = 1.0                                        # ⛔ NOT A KNOB — the magnitude is the estimator's
#: The λ-sweep of the mean-match, scored as ANCHORS (non-shippable): where the metric optimum sits
#: relative to the level target (NF-D20's interior-optimum question, MEASURED). 2.0 = `over_scale`.
LAMBDA_SWEEP = (0.25, 0.5, 0.75, 1.25, 1.5, 2.0)
OVER_SCALE_LAMBDA = 2.0

#: The band treatments. PRIMARY = the served path (band model refit on the recalibrated history);
#: the two others are DISCLOSURES computed beside it.
BAND_TREATMENTS = ("fixed", "refit", "scaled")
BAND_TREATMENT = "fixed"

#: Population + folds — inherited from the NF-B3 wide window.
TIER_ANCHOR = LR.TIER_ANCHOR
FOLD_SEASONS = tuple(LR.WIDE_WINDOW_SEASONS)        # 2013–2025 → 13 folds
TRAIN_PANEL_START = 2007
ROOKIE_SUBSTRATE_START = 2016

#: Metric + deflation — inherited by import so the bar cannot drift between stories.
SELECTION_METRIC = LR.SELECTION_METRIC              # crps
FORBIDDEN_SELECTION_METRICS = LR.FORBIDDEN_SELECTION_METRICS
PBO_MAX, DSR_MIN, ALPHA = LR.PBO_MAX, LR.DSR_MIN, LR.ALPHA
COVERAGE_FLOOR = LR.COVERAGE_FLOOR
ORDERING_DO_NO_HARM = LR.ORDERING_DO_NO_HARM
PREREGISTERED_FRAMING = "pooled"
PREREGISTERED_DSR_READING = "whole_field_declared"

#: The level gates.
LEVEL_REDUCTION_MIN = 0.50                          # L1: pooled |bias| must at least halve
LEVEL_SE_MULT = 2.0                                 # L2/L3: the noise allowance, in SEs
NON_SHIPPABLE = ("over_scale", "wide_band", "zero_project", "pos_median",
                 "oracle_perplayer", "permuted_across", "permuted_within") + tuple(
    f"lambda_sweep@{lam:g}" for lam in LAMBDA_SWEEP)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ NF-TR2b — THE TRAILING-WINDOW SUCCESSOR (declared AFTER NF-TR2's level-gate refusal, BEFORE its
#    own run; the MARGIN2→MARGIN3 shape: a refused magnitude ESTIMATOR gets a better estimator under a
#    fresh registration — never a re-run, never a post-hoc λ)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# WHY: NF-TR2's full-history mean-match passed every inherited gate (CRPS 49.42 vs 49.92, PBO 0.0,
# DSR 0.991 declared / 0.974 under NF-B3's field) and was REFUSED by L1–L3: it OVER-corrects out of
# fold (pooled OOF bias −12.85 → +7.88; QB −0.6 → +12.6). The mechanism is visible in the per-season
# needed k: 2007–2009 sit in a different regime (TE 2.3–2.6, WR 1.4–1.5, pooled 1.25–1.33) and a
# Σy/Σp over ALL prior seasons carries them forever (the 2013 TE fit is 1.35 vs a needed 1.03; the
# 2025 QB fit 1.03 vs a needed 0.93 — QB has run slightly HOT since 2019). The level is
# NON-STATIONARY, and an estimator that cannot track a drift is the wrong estimator, not the wrong
# form. The successor is the same family with a TRAILING window.
#
# THE WINDOW IS DERIVED, NOT TUNED: the smallest number of prior seasons that gives EVERY position at
# least `WINDOW_MIN_ROWS` tier rows to fit on — computed from the incumbent's own tier composition
# (rows per position per season, a design quantity that reads no outcome). On the 156-row tier TE is
# the thinnest at ~19 rows/season ⇒ ceil(90/19) = 5. `WINDOW_SEASONS` is PINNED here and the runner
# RAISES if the derivation disagrees. Windows 3 and 8 and the full history are SENSITIVITY ANCHORS
# (non-shippable) so the reader can see the window's effect without a knob entering the field.
WINDOW_MIN_ROWS = 90
WINDOW_SEASONS = 5
WINDOW_SENSITIVITY = (3, 8, None)                   # None = full history (NF-TR2's estimator)
TR2B_STORY = "NF-TR2b"
TR2B_MODEL_VERSION = "nfl_fantasy_nf_tr2b_veteran_level_v1"


def window_seasons_for(rows_per_position_per_season: dict, *, min_rows: int = WINDOW_MIN_ROWS
                       ) -> int:
    """The trailing window, DERIVED: `ceil(min_rows / min_position_rows_per_season)`."""
    thin = min(float(v) for v in rows_per_position_per_season.values())
    return int(np.ceil(min_rows / max(thin, 1e-9)))


def window_mask(seasons, target_season: int, window: int | None) -> np.ndarray:
    """Rows in the trailing `window` seasons strictly before `target_season` (None = all prior)."""
    s = pd.to_numeric(pd.Series(seasons), errors="coerce").to_numpy(dtype=float)
    keep = s < float(target_season)
    if window is not None:
        keep &= s >= float(target_season) - float(window)
    return keep


def registration() -> dict:
    """The pre-registration as data, for the artifact and the guard tests."""
    return {
        "story": STORY, "model_version": MODEL_VERSION, "recalibrates": RECALIBRATES,
        "recalibrated_leg": RECALIBRATED_LEG, "excluded_legs": list(EXCLUDED_LEGS),
        "positions": list(RECALIBRATED_POSITIONS),
        "forms": list(FORMS), "noop": NOOP, "declared_field_size": DECLARED_FIELD_SIZE,
        "declared_field_source": DECLARED_FIELD_SOURCE, "learned_foil": LEARNED_FOIL,
        "space": SPACE, "estimator": ESTIMATOR, "min_fit_rows": MIN_FIT_ROWS,
        "mult_clip": list(MULT_CLIP), "lambda": LAMBDA, "lambda_sweep": list(LAMBDA_SWEEP),
        "band_treatment": BAND_TREATMENT, "band_treatments_disclosed": list(BAND_TREATMENTS),
        "tier_anchor": TIER_ANCHOR, "tier_n": LR.draftable_tier_size(),
        "fold_seasons": list(FOLD_SEASONS), "train_panel_start": TRAIN_PANEL_START,
        "selection_metric": SELECTION_METRIC, "framing": PREREGISTERED_FRAMING,
        "dsr_reading": PREREGISTERED_DSR_READING,
        "gates": {"pbo_max": PBO_MAX, "dsr_min": DSR_MIN, "alpha": ALPHA,
                  "coverage_floor": COVERAGE_FLOOR, "ordering_do_no_harm": ORDERING_DO_NO_HARM,
                  "level_reduction_min": LEVEL_REDUCTION_MIN, "level_se_mult": LEVEL_SE_MULT},
        "b3_field_sr0_disclosed": B3_FIELD_SR0, "b3_recorded": dict(B3_RECORDED),
        "non_shippable": list(NON_SHIPPABLE),
        "tr2b": {"story": TR2B_STORY, "model_version": TR2B_MODEL_VERSION,
                 "window_seasons": WINDOW_SEASONS, "window_min_rows": WINDOW_MIN_ROWS,
                 "window_sensitivity": list(WINDOW_SENSITIVITY)},
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Step 1 — the decomposition
# ══════════════════════════════════════════════════════════════════════════════════════════════
def decompose_bias(point, real, proj_games, real_games, positions=None) -> dict:
    """`bias = availability + rate` per position (+ pooled), from the EXACT row identity
    `p − y = r̂·(ĝ − g) + g·(r̂ − r)`; a zero-game season carries no rate term. Also the pooled
    rate ratio `(Σp/Σĝ)/(Σy/Σg)`, the games ratio and the mean-match k, so a reader can see whether the
    miss is proportional (a constant on the rate) or not."""
    p = np.asarray(point, dtype=float)
    y = np.asarray(real, dtype=float)
    gh = np.clip(np.asarray(proj_games, dtype=float), 1e-9, None)
    gr = np.asarray(real_games, dtype=float)
    pos = (np.array([str(q).upper() for q in positions], dtype=object) if positions is not None
           else np.array(["ALL"] * len(p), dtype=object))
    rh = p / gh
    r_row = np.where(gr > 0, y / np.where(gr > 0, gr, 1.0), 0.0)
    avail = rh * (gh - gr)
    rate = np.where(gr > 0, gr * (rh - r_row), 0.0)

    def _one(sel: np.ndarray) -> dict:
        n = int(sel.sum())
        if n == 0:
            return {"n": 0}
        return {
            "n": n, "bias": float(np.mean(p[sel] - y[sel])),
            "availability_part": float(np.mean(avail[sel])),
            "rate_part": float(np.mean(rate[sel])),
            "our_over_actual": float(p[sel].sum() / max(y[sel].sum(), 1e-9)),
            "proj_games_mean": float(gh[sel].mean()), "real_games_mean": float(gr[sel].mean()),
            "games_ratio": float(gh[sel].mean() / max(gr[sel].mean(), 1e-9)),
            "proj_rate_pooled": float(p[sel].sum() / gh[sel].sum()),
            "real_rate_pooled": float(y[sel].sum() / max(gr[sel].sum(), 1e-9)),
            "rate_ratio_pooled": float((p[sel].sum() / gh[sel].sum())
                                       / max(y[sel].sum() / max(gr[sel].sum(), 1e-9), 1e-9)),
            "mean_match_k": float(y[sel].sum() / max(p[sel].sum(), 1e-9)),
            "zero_outcome_frac": float(np.mean(y[sel] == 0)),
        }

    out = {"pooled": _one(np.ones(len(p), dtype=bool)), "per_position": {}}
    for q in np.unique(pos):
        out["per_position"][str(q)] = _one(pos == q)
    pooled = out["pooled"]
    out["identity_holds"] = bool(abs(pooled["availability_part"] + pooled["rate_part"]
                                     - pooled["bias"]) < 1e-6)
    out["miss_is_rate"] = bool(abs(pooled["rate_part"]) > abs(pooled["availability_part"]))
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The forms — fit strictly in-fold, on the tier
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pos(positions) -> np.ndarray:
    return np.array([str(q).upper() for q in positions], dtype=object)


def fit_pos_const(point, real, positions, *, min_rows: int = MIN_FIT_ROWS,
                  clip: tuple = MULT_CLIP) -> dict:
    """The MEAN-MATCH constant per position: `k_q = Σy / Σp` over the rows given (the caller passes
    the in-fold TIER rows). By construction the recalibrated in-fold mean equals the realized mean —
    that is the "recalibrate to realized" contract, and `test_estimator_targets_realized` pins it.
    A thin position is LEFT ALONE (k = 1), never zeroed."""
    p = np.asarray(point, dtype=float)
    y = np.asarray(real, dtype=float)
    pos = _pos(positions)
    fin = np.isfinite(p) & np.isfinite(y)
    out = {}
    for q in RECALIBRATED_POSITIONS:
        sel = fin & (pos == q)
        if int(sel.sum()) >= min_rows and p[sel].sum() > 0:
            out[q] = float(np.clip(y[sel].sum() / p[sel].sum(), *clip))
        else:
            out[q] = 1.0
    return out


def fit_pos_affine(point, real, positions, games) -> dict:
    """The per-GAME affine `y ~ a·g + b·p` per position — NF-RECAL1's estimator, INHERITED (a
    re-implementation is where a foil silently stops being matched). Empty for a thin position."""
    return LR.fit_form("pos_affine", SPACE, point, real, positions, games)


def fit_form(form: str, point, real, positions, games) -> dict:
    if form == "pos_const":
        return fit_pos_const(point, real, positions)
    if form == "pos_affine":
        return fit_pos_affine(point, real, positions, games)
    raise ValueError(f"unknown NF-TR2 form {form!r}")


def predict_level(form: str, params: dict, point, positions, games, lam: float = LAMBDA
                  ) -> np.ndarray:
    """The recalibrated POINT for one form (λ blends toward the incumbent — used ONLY by the
    λ-sweep anchors; every trial runs at λ = 1). Rows without a parameter keep the incumbent."""
    p = np.asarray(point, dtype=float)
    adj = LR.predict_form(form, SPACE, params, p, positions, games)
    return np.clip(p + float(lam) * (adj - p), 0.0, None)


def per_row_scale(form: str, params: dict, point, positions, games, lam: float = LAMBDA,
                  min_point: float = LR.MIN_POINT) -> np.ndarray:
    """The per-row multiplicative scale that carries the level correction onto the whole stat LINE
    (`new_point / old_point`), so every scoring format the board serves moves consistently. For
    `pos_const` it is exactly k; for the affine `(a·g + b·p)/p`, LEFT AT 1 below `min_point` (a
    ratio needs a denominator with signal in it — the inherited NF-RECAL1 floor)."""
    p = np.asarray(point, dtype=float)
    newp = predict_level(form, params, p, positions, games, lam)
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(p >= min_point, newp / np.where(p > 0, p, 1.0), 1.0)
    return np.where(np.isfinite(s), s, 1.0)


def invert_level(form: str, params: dict, newp, positions, games) -> np.ndarray:
    """The INCUMBENT-EQUIVALENT point for a recalibrated point — the level the band model was fitted
    against. `pos_const`: new/k; `pos_affine`: (new − a·g)/b. Rows without a parameter (or a
    non-positive slope) map to themselves. This is what keeps the served band BYTE-IDENTICAL under
    the level shift (`BAND_TREATMENT = "fixed"`), including through NF1.5's re-derivation."""
    n = np.asarray(newp, dtype=float)
    pos = _pos(positions)
    g = np.asarray(games, dtype=float)
    out = n.copy()
    if form == "pos_const":
        for q, k in (params or {}).items():
            k = float(k)
            if k > 0:
                out[pos == q] = n[pos == q] / k
    elif form == "pos_affine":
        for q, (a, b) in (params or {}).items():
            a, b = float(a), float(b)
            if b > 0:
                sel = pos == q
                out[sel] = (n[sel] - a * g[sel]) / b
    elif form:
        raise ValueError(f"unknown NF-TR2 form {form!r}")
    return np.clip(np.where(np.isfinite(out), out, n), 0.0, None)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The level gates
# ══════════════════════════════════════════════════════════════════════════════════════════════
def level_se(real, point, positions) -> dict:
    """SE of the mean bias per position (and pooled) — sd(y − p)/√n on the tier rows. A DESIGN
    quantity: it depends on the incumbent's residuals and n, never on any candidate."""
    y = np.asarray(real, dtype=float)
    p = np.asarray(point, dtype=float)
    pos = _pos(positions)
    out = {}
    for q in list(RECALIBRATED_POSITIONS) + ["pooled"]:
        sel = np.ones(len(y), dtype=bool) if q == "pooled" else (pos == q)
        n = int(sel.sum())
        out[q] = float(np.std(y[sel] - p[sel], ddof=1) / np.sqrt(n)) if n > 2 else float("inf")
    return out


def level_gate(*, bias_inc: dict, bias_win: dict, se: dict, over_scale_loses: bool | None,
               games_untouched: bool, reduction_min: float = LEVEL_REDUCTION_MIN,
               se_mult: float = LEVEL_SE_MULT) -> dict:
    """L1–L4 (L5 is measured by the ordering clause + the Δρ identity check). `bias_*` are dicts
    keyed by position + 'pooled' (OOF, pooled over rows across folds)."""
    b_inc, b_win = float(bias_inc["pooled"]), float(bias_win["pooled"])
    l1 = bool(abs(b_win) <= (1.0 - reduction_min) * abs(b_inc) + 1e-12)
    l2 = {}
    for q in RECALIBRATED_POSITIONS:
        bi, bw, s = abs(float(bias_inc[q])), abs(float(bias_win[q])), float(se[q])
        l2[q] = bool(bw <= max((1.0 - reduction_min) * bi, se_mult * s) + 1e-12)
    l3_not_hot = bool(b_win <= se_mult * float(se["pooled"]) + 1e-12)
    l3 = bool(l3_not_hot and (over_scale_loses is True))
    return {
        "L1_pooled_reduced": l1, "L1_detail": {"incumbent": b_inc, "winner": b_win,
                                                "reduction": (1 - abs(b_win) / abs(b_inc))
                                                if b_inc else None},
        "L2_per_position": l2, "L2_all": bool(all(l2.values())),
        "L3_no_inflation": l3, "L3_detail": {"not_significantly_hot": l3_not_hot,
                                             "over_scale_loses": over_scale_loses,
                                             "pooled_se": float(se["pooled"])},
        "L4_availability_preserved": bool(games_untouched),
        "pass": bool(l1 and all(l2.values()) and l3 and games_untouched),
    }


def rank_identity(point, adjusted, real, positions) -> dict:
    """L5 — the within-position order and the per-position Δρ vs realized, before/after. For a
    monotone map both are IDENTITIES; asserted to `tol`, never assumed (NF-D16 (2))."""
    from scipy.stats import spearmanr

    p = np.asarray(point, dtype=float)
    a = np.asarray(adjusted, dtype=float)
    y = np.asarray(real, dtype=float)
    pos = _pos(positions)
    out = {}
    for q in RECALIBRATED_POSITIONS:
        sel = pos == q
        if sel.sum() < 3:
            continue
        rho_pa = spearmanr(p[sel], a[sel]).correlation
        rho_py = spearmanr(p[sel], y[sel]).correlation
        rho_ay = spearmanr(a[sel], y[sel]).correlation
        out[q] = {"within_position_rho": float(rho_pa),
                  "rho_vs_realized_incumbent": float(rho_py),
                  "rho_vs_realized_winner": float(rho_ay),
                  "delta_rho_identical": bool(abs(rho_py - rho_ay) < 1e-12),
                  "order_identical": bool(rho_pa > 1 - 1e-12)}
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# SERVING — apply the correction to a projected VETERAN frame (the whole stat line moves)
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: The season-total counting stats the level scale carries (the same set the mover / environment /
#: injury steps in `project_veterans` rescale — one scalar per player keeps the line consistent).
_SCALED_LINE_COLS = ("proj_pass_att", "proj_pass_cmp", "proj_pass_yds", "proj_pass_td",
                     "proj_pass_int", "proj_rush_att", "proj_rush_yds", "proj_rush_td",
                     "proj_targets", "proj_rec", "proj_rec_yds", "proj_rec_td")
SCALE_COL = "veteran_level_scale"


def recalibrate_projected_frame(df: pd.DataFrame, form: str, params: dict, *,
                                score_line, lam: float = LAMBDA) -> pd.DataFrame:
    """Carry the level correction onto a projected veteran frame BEFORE its band is attached: scale
    the season line by the per-row factor, re-clamp cmp ≤ att / rec ≤ targets, recompute fumbles, and
    re-score through the SERVED scorer. `proj_games` is NOT touched — that is L4, and it is asserted."""
    if not form or not params:
        return df
    out = df.copy()
    games_before = pd.to_numeric(out["proj_games"], errors="coerce").to_numpy(dtype=float).copy()
    pos = out["position"].astype(str).str.upper().to_numpy()
    p = pd.to_numeric(out["proj_fp_ppr"], errors="coerce").to_numpy(dtype=float)
    g = pd.to_numeric(out["proj_games"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    scale = per_row_scale(form, params, p, pos, g, lam)
    # ⛔ scope: only the recalibrated positions move; anything else (FB, an unknown position) is left
    #    at 1 — the same "a missing estimate leaves the row alone" rule as the fit.
    scale = np.where(np.isin(pos, RECALIBRATED_POSITIONS), scale, 1.0)
    for col in _SCALED_LINE_COLS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").to_numpy(dtype=float) * scale
    if {"proj_pass_cmp", "proj_pass_att"} <= set(out.columns):
        out["proj_pass_cmp"] = np.minimum(out["proj_pass_cmp"], out["proj_pass_att"])
    if {"proj_rec", "proj_targets"} <= set(out.columns):
        out["proj_rec"] = np.minimum(out["proj_rec"], out["proj_targets"])
    if {"proj_rush_att", "proj_rec"} <= set(out.columns):
        out["proj_fumbles_lost"] = np.round(
            (pd.to_numeric(out["proj_rush_att"], errors="coerce").fillna(0.0).to_numpy()
             + pd.to_numeric(out["proj_rec"], errors="coerce").fillna(0.0).to_numpy()) * 0.006, 2)
    out = score_line(out, prefix="proj_")
    out[SCALE_COL] = scale
    games_after = pd.to_numeric(out["proj_games"], errors="coerce").to_numpy(dtype=float)
    if not np.array_equal(games_before, games_after, equal_nan=True):
        raise AssertionError("NF-TR2 L4 violated: proj_games moved under the level recalibration")
    return out


def recalibrate_panel_points(panel: pd.DataFrame, form: str, params: dict,
                             lam: float = LAMBDA) -> pd.DataFrame:
    """The historical panel with its `point` recalibrated by the SAME map — the band model is then
    fitted on the level model's OWN history (§0 (3)). Rows outside the recalibrated positions and rows
    without a parameter keep the incumbent point."""
    if not form or not params or panel is None or panel.empty:
        return panel
    out = panel.copy()
    pos = out["position"].astype(str).str.upper().to_numpy()
    p = pd.to_numeric(out["point"], errors="coerce").to_numpy(dtype=float)
    g = pd.to_numeric(out.get("proj_games", pd.Series(np.full(len(out), 17.0))),
                      errors="coerce").fillna(0.0).to_numpy(dtype=float)
    newp = predict_level(form, params, p, pos, g, lam)
    out["point"] = np.where(np.isin(pos, RECALIBRATED_POSITIONS) & np.isfinite(newp), newp, p)
    return out


def fit_level_from_panel(panel: pd.DataFrame, form: str, projection_season: int, tier_n: int,
                         window: int | None = None) -> dict:
    """The serving-time fit: params from the veteran band panel's rows STRICTLY BEFORE
    `projection_season`, restricted to the incumbent-anchored TIER of each season (the population the
    correction was selected on). Walk-forward by construction, so a backtest board for season Y is
    fitted on < Y (the E5.9 in-sample boundary) exactly as the harness folds are. `window` = the
    trailing-season window (NF-TR2b; None = the full history, NF-TR2)."""
    from quant_sports_intel_models.football.nfl.fantasy.season_projection import _tier_row_mask

    if panel is None or panel.empty or not form:
        return {}
    d = panel.copy()
    d["target_season"] = pd.to_numeric(d["target_season"], errors="coerce")
    d = d[window_mask(d["target_season"], int(projection_season), window)]
    d["position"] = d["position"].astype(str).str.upper()
    d = d[d["position"].isin(RECALIBRATED_POSITIONS)]
    for c in ("point", "real_fp_ppr", "proj_games"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["point", "real_fp_ppr"]).reset_index(drop=True)
    if d.empty:
        return {}
    tier = _tier_row_mask(d["point"].to_numpy(dtype=float), d["target_season"].to_numpy(),
                          int(tier_n))
    t = d[tier]
    return fit_form(form, t["point"].to_numpy(dtype=float), t["real_fp_ppr"].to_numpy(dtype=float),
                    t["position"].to_numpy(), t["proj_games"].fillna(0.0).to_numpy(dtype=float))


def params_to_json(params: dict) -> str:
    """The stamp: a JSON string (a Delta-friendly scalar) — `{"QB": 1.003, ...}` or the affine
    `{"QB": [a, b], ...}`."""
    return json.dumps({str(k): (list(v) if isinstance(v, (tuple, list)) else float(v))
                       for k, v in (params or {}).items()}, sort_keys=True)
