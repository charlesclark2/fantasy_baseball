"""ncaaf_val3b_single_contrast.py — NCAAF-VAL3b: the cold-start μ correction as ONE contrast.

NCAAF-VAL3 measured a real cold-start μ_total bias in weeks 1–3 and a correction that removes most
of it on 8/8 folds, then was refused by **PBO 0.5300** over a declared field of 8 — and MEASURED the
refusal to be a **field-composition artifact**: the 2-arm decision PBO is 0.0000 while the
eligible-set PBO is 0.7010, i.e. *worse*. That signature is near-clones (four near-identical
correction forms), not an unstable winner.

The admissible successor is therefore **a fresh FORWARD registration of a coherent family**, never a
post-hoc trim of a field already scored (MH2.2 / NF-W6b-C / NCAAF-P2.1-S1). This module executes
that registration, and the family has **two members**:

    μ'_total(g) = μ_total(g) − d̂_bucket(fold)      for season_order_week ≤ 3
    σ(g), μ_margin(g)                               FROZEN — byte-identical to the foil

⛔ **CHANGES NOTHING SERVED.** Eval-only over the P1.4 cache: no refit of a served artifact, no
serving write, no registry edit, no bet. `best_alpha = 0` before and after.

⭐ **What is genuinely different from VAL3, and why each difference is admissible.**

1. **The field has ONE selectable arm**, so **CSCV/PBO is INAPPLICABLE — not passed.** No two-arm
   PBO number is computed even as a diagnostic: VAL3 already reported that figure as a labelled
   lower bound, and reproducing it inside the successor's own gate block would read as "the gate we
   failed now passes" (§4.1 of the pre-registration).
2. **`V` is `deflated_sharpe`'s asymptotic no-field default `1/n_obs`**, because a cross-trial
   dispersion needs ≥2 trials. ⛔ Importing VAL3's measured `V` is inadmissible in either direction.
   The resulting `SR0 = 0.18376` is LOWER than VAL3's 0.35374 and the pre-registration says so in
   those words — that IS the arithmetic content of the successor shape, and it is legitimate only
   because the family is declared forward and scored whole.
3. **Two NEW materiality clauses BIND** (M1/M2), closing the pre-registration gap VAL3 recorded and
   handed forward. Both have ZERO free parameters: they are closed-form functions of constants VAL2
   recorded before VAL3 existed.
4. ⛔ **NO δ-scaling.** `over_scale` topped VAL3's raw leaderboard but its PAIRED read is a TIE and
   it was BEATEN by its own-form peek. A rank cannot tell a tie from a win (NF1.8); a magnitude
   adopted after seeing it rank is the inadmissible-λ shape (NF-D18 / NF-D20).

⭐ **The estimator, the metric, the folds, the population and clauses C1–C8 are IMPORTED from
`ncaaf_val3_cold_start_mu`, not restated.** One policy with two call sites is the E9.61
two-renderers hazard, and a restated constant is exactly how a successor silently stops scoring what
its parent scored.

The field, the metric, the clauses, `V` and the verdict rule are all CLOSED in
`ablation_results/ncaaf_val3b_preregistration.md`, written and committed before a single arm was
scored.

  uv run python -m quant_sports_intel_models.football.ncaaf.models.ncaaf_val3b_single_contrast
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from betting_ml.utils import cv_power
from betting_ml.utils.market_blind import assert_market_blind
from betting_ml.utils.overfitting import deflated_sharpe
from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_game as B
from quant_sports_intel_models.football.ncaaf.models import ncaaf_val3_cold_start_mu as V3

_STORY = "NCAAF-VAL3b"
_RESULTS = Path(B._RESULTS_DIR)
#: ⛔ VAL3b's OWN paths. A runner that writes to its parent's fixed path silently clobbers a DECIDED
#: story's record on every re-run (the NF-W2c-CBS hazard; NF-W7f: a decided record is not rewritten).
_SCORES_JSON = _RESULTS / "ncaaf_val3b_single_contrast_scores.json"
_OUT_JSON = _RESULTS / "ncaaf_val3b_single_contrast.json"
#: the MACHINE-rendered table. The hand-written narrative is `ncaaf_val3b_readout.md` and is not
#: written here.
_OUT_MD = _RESULTS / "ncaaf_val3b_single_contrast_table.md"
_PARENT_JSON = _RESULTS / "ncaaf_val3_s1_serve_reanchor.json"

#: Imported, never restated (see the docstring's point about a second literal drifting).
SERVED = V3.SERVED
WEEK_COL = V3.WEEK_COL
COLD_START_MAX_WEEK = V3.COLD_START_MAX_WEEK
CALIB_FLOOR = V3.CALIB_FLOOR
PIT_DEGRADE_TOL = V3.PIT_DEGRADE_TOL
TIE_BAND = V3.TIE_BAND

DSR_GATE = V3.DSR_GATE
FDR_ALPHA = V3.FDR_ALPHA

#: §5 — MATERIALITY, registered FORWARD, ZERO free parameters.
#: M1: VAL2's own acceptance band, in the native unit. Inherited, ⛔ never re-derived.
MATERIAL_BIAS_PTS = 1.00
#: M2: the RELATIVE wk1-3 CRPS gain that removing M1 is worth, at the calibrated-Gaussian ideal.
#: Closed form, σ-free: with C(β) = E[g(Z)], Z ~ N(−β,1), g the Gaussian-CRPS kernel, and VAL2's
#: RECORDED cold-start bias of 0.15 σ and 1.0-pt band of 0.065 σ:
#:     C(0.150) = 0.57053077 ; C(0.085) = 0.56622711 ; (C(0.150) − C(0.085)) / C(0.150) = 0.007543
#: `verify_m2_derivation()` recomputes it from those two constants, so the number cannot rot into a
#: literal nobody can reproduce. Anchoring at VAL2's 0.15 σ is the CONSERVATIVE direction: a smaller
#: true starting bias means a smaller achievable gain and a HARDER bar, not an easier one.
MATERIAL_REL_CRPS_GAIN = 0.007543
_M2_BETA_FOIL = 0.150         # VAL2: the recorded wk1-3 bias, in σ units
_M2_BETA_BAND = 0.065         # VAL2: the 1.0-pt materiality band, in σ units

#: §4.2 — `n_trials` = the DECLARED field (VAL3's convention: the foil counts).
DECLARED_FIELD_SIZE = 2
#: ⛔ `V` is UNDEFINED at one selectable arm. `None` selects `deflated_sharpe`'s documented
#: asymptotic fallback `V = 1/n_obs` — a DESIGN quantity (it depends only on the fold count).
#: ⛔ Importing VAL3's measured V (0.05878) would be a dispersion from a field this study lacks.
VAR_TRIALS_SR: float | None = None

#: §7 — the reproduction pin, from the PARENT (`ncaaf_val3_s1_serve_reanchor.json`: n_oos_games
#: 6024, clv_eval.n_with_close 4187, fit_at 2026-08-22) and the fold structure. ⛔ NEVER from
#: VAL3b's own output.
PIN = {
    "n_with_close": 4187,
    "n_oos_games": 6024,
    "fold_years": [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025],
    "source": "ncaaf_val3_s1_serve_reanchor.json (S1-serve --stage finalize, repaired _clv_eval)",
}
#: ⭐ Declared FORWARD in §7 so it cannot look like a loosening after a failure: `assemble_cache`
#: stamps `assembled_at = date.today()`, so a re-assemble stamps TODAY whatever the population is.
#: VAL3 assembled and ran on one day and paid nothing for pinning the literal; VAL3b must
#: re-assemble (the checkout holds the 07-22 vintage) and would fail that leg for a reason carrying
#: NO information about the population, burying the three legs that DO define it. Reported, not
#: pinned — and the population legs still HALT.
PIN_REPORTED_ONLY: tuple[str, ...] = ("cache_assembled_at",)


@dataclass(frozen=True)
class Arm:
    name: str
    role: str          # "foil" | "candidate" | "diagnostic"
    doc: str
    scope: str
    form: str


#: ⛔ CLOSED at pre-registration. TWO members, plus two PEEKING diagnostics that were never
#: candidates for selection (they read the eval fold's own residuals) and are therefore excluded
#: from `n_trials` AND from `V` (MH2.1 (a) — the anchor that POLICES the metric must never SET the
#: gate's own bar).
#: ⛔ VAL3's matched foils (`week_blind`, `pooled_level`) are OUT. They are honest,
#: in-principle-shippable estimators, and calling one a "diagnostic" to keep it out of the
#: multiplicity count would be exactly the laundering MH2.2 forbids. The channel attribution is
#: CITED from VAL3's record (§1 of the pre-registration), not re-measured here.
ARMS: tuple[Arm, ...] = (
    Arm("none", "foil",
        "the served model, untouched — the do-nothing degenerate and the incumbent, one and the "
        "same", "cold", "zero"),
    Arm("bucket_shift", "candidate",
        "THE single pre-registered contrast: one constant over weeks 1–3, selected IN-FOLD from a "
        "nested walk-forward inside the outer fold's own training seasons", "cold", "bucket"),
    Arm("oracle_bucket", "diagnostic",
        "PEEKING own-form floor: the bucket constant computed on the EVAL fold's own weeks 1–3 "
        "(NF-D16 g‴ — one ceiling per FORM)", "cold", "bucket"),
    Arm("matched_n_bucket", "diagnostic",
        "the same estimator on a random IN-FOLD slice sized to the eval fold's own cold-start n — "
        "what makes the peek readable at matched family AND matched SAMPLE (NF1.9 (f))",
        "cold", "bucket"),
)

FOIL_ARM = "none"
CANDIDATE = "bucket_shift"
CANDIDATES: tuple[str, ...] = (CANDIDATE,)
DIAGNOSTICS: tuple[str, ...] = tuple(a.name for a in ARMS if a.role == "diagnostic")


def verify_m2_derivation(tol: float = 5e-6) -> dict[str, float]:
    """Recompute M2 from VAL2's two recorded constants and HALT if the module literal has drifted.

    ⭐ A pre-registered bar that exists only as a literal is a bar nobody can reproduce, and the
    first thing a sceptical reader asks of a bar written by an author who had already seen the
    parent's scores is "where did that number come from?". This answers it mechanically: the only
    inputs are VAL2's recorded 0.15 σ cold-start bias and its 1.0-pt (= 0.065 σ) acceptance band.
    """
    from scipy import integrate, stats

    def C(beta: float) -> float:
        g = lambda z: z * (2 * stats.norm.cdf(z) - 1) + 2 * stats.norm.pdf(z) - V3._INV_SQRT_PI
        v, _ = integrate.quad(lambda z: g(z) * stats.norm.pdf(z, loc=-beta, scale=1.0),
                              -12 - abs(beta), 12 + abs(beta), limit=400)
        return float(v)

    c_foil, c_corr = C(_M2_BETA_FOIL), C(_M2_BETA_FOIL - _M2_BETA_BAND)
    derived = (c_foil - c_corr) / c_foil
    if abs(derived - MATERIAL_REL_CRPS_GAIN) > tol:
        raise SystemExit(
            f"[{_STORY}] M2 has drifted from its derivation: the module literal is "
            f"{MATERIAL_REL_CRPS_GAIN:.6f} but VAL2's constants give {derived:.6f}. A materiality "
            "bar that no longer follows from its stated inputs is a bar chosen by hand (E2.1-r).")
    return {"C_foil": c_foil, "C_corrected": c_corr, "derived_rel_gain": derived,
            "module_literal": MATERIAL_REL_CRPS_GAIN,
            "full_removal_rel_gain": (c_foil - C(0.0)) / c_foil}


# ===========================================================================
# Stage 1 — score the contrast on every fold
# ===========================================================================

def stage_score(args) -> dict[str, Any]:
    m2 = verify_m2_derivation()
    df, feat, meta = B.load_cache()
    df, feat, pace = B.ensure_pace_composites(df, feat, context=_STORY)
    print(f"=== {_STORY} stage 1 — SCORE (single contrast; declared field {DECLARED_FIELD_SIZE}) ===")
    print(f"  cache {meta.get('assembled_at')} · {len(df):,} games · "
          f"{int(df['has_close'].sum()):,} closes · pace derived in-session: "
          f"{pace.get('pace_derived_in_session')}")
    print(f"  M2 re-derived from VAL2's constants: {m2['derived_rel_gain']*100:.4f} % "
          f"(literal {MATERIAL_REL_CRPS_GAIN*100:.4f} %) ✅")

    folds = B.build_folds(df, feat, max_folds=args.max_folds)
    df_sorted = df.sort_values([B._YEAR, "season_order_week", B._DATE]).reset_index(drop=True)
    cand = B.build_candidate(SERVED["mc"])
    rng = np.random.default_rng(args.seed)

    arm_folds: dict[str, list[dict]] = {a.name: [] for a in ARMS}
    per_fold_meta: list[dict] = []
    oos_rows: list[pd.DataFrame] = []

    for fold in folds:
        cols = B.resolve_contract(SERVED["contract"], fold.X_tr, fold.feat_cols, fold.ranking,
                                  top_k=B._DEFAULT_TOP_K)
        assert_market_blind(cols, context=f"{_STORY} fold {fold.eval_year}")
        cols_idx = np.array([fold.feat_cols.index(c) for c in cols])
        _, mu_t, _, _ = cand.fit_predict(fold.X_tr[:, cols_idx], fold.y_m_tr, fold.y_t_tr,
                                         fold.X_ev[:, cols_idx])
        # σ — fitted per fold on the INNER HOLDOUT exactly as `_fit_dispersion` does, then FROZEN
        # across the arm and the foil (C7). The contest is about μ and only μ.
        _disp, dinfo, _sig_m, sig_t = B._fit_dispersion(cand, fold, cols_idx, SERVED["form"],
                                                        None, None)
        y_t = fold.y_t_ev
        wk = fold.ev_meta[WEEK_COL].to_numpy()
        infold = V3.infold_oos(df_sorted, feat, cols, fold.eval_year)
        n_cold = int((wk <= COLD_START_MAX_WEEK).sum())
        print(f"  fold {fold.eval_year}: {len(y_t):,} eval ({n_cold} cold-start) | in-fold "
              f"{len(infold):,} rows / {len(V3._cold(infold)):,} cold-start | σ_total med "
              f"{float(np.median(sig_t)):.2f}")
        per_fold_meta.append({
            "eval_year": int(fold.eval_year), "n_eval": int(len(y_t)), "n_cold": n_cold,
            "n_infold": int(len(infold)), "n_infold_cold": int(len(V3._cold(infold))),
            "sigma_total_median": float(np.median(sig_t)), "dispersion": dinfo,
        })
        oos_rows.append(pd.DataFrame({
            "game_id": fold.ev_meta["game_id"].to_numpy(), "season": int(fold.eval_year),
            WEEK_COL: wk, "mu_total": mu_t, "y_total": y_t, "sigma_total": sig_t,
        }))

        ev_err = mu_t - y_t                                  # ⛔ handed ONLY to the peeking anchors
        peek_src = V3._eval_source(wk, ev_err, int(fold.eval_year))
        cold_mask = wk <= COLD_START_MAX_WEEK
        late_mask = ~cold_mask
        infold_cold = V3._cold(infold)
        n_match = min(int(cold_mask.sum()), len(infold_cold))
        matched_src = infold_cold.iloc[rng.choice(len(infold_cold), size=n_match, replace=False)]

        def _score(mu_prime: np.ndarray) -> dict[str, Any]:
            return {
                "cold": V3.cell_metrics(y_t[cold_mask], mu_prime[cold_mask], sig_t[cold_mask]),
                "pooled": V3.cell_metrics(y_t, mu_prime, sig_t),
                "late": V3.cell_metrics(y_t[late_mask], mu_prime[late_mask], sig_t[late_mask]),
                "sigma_checksum": float(np.sum(sig_t)),
            }

        for a in ARMS:
            src = {"oracle_bucket": peek_src, "matched_n_bucket": matched_src}.get(a.name, infold)
            d, info = V3._estimate(a.form, src, wk)
            row = {"eval_year": int(fold.eval_year), "fitted": info, **_score(mu_t - d)}
            if a.role == "candidate":
                # C8's OWN-FORM floor and its own matched-n control (NF-D16 g‴ / NF-W6d).
                d_pk, i_pk = V3._estimate(a.form, peek_src, wk)
                d_mn, i_mn = V3._estimate(a.form, matched_src, wk)
                row["own_form_peek"] = {"crps_cold": _score(mu_t - d_pk)["cold"]["crps"],
                                        "delta": i_pk.get("delta")}
                row["own_form_matched_n"] = {"crps_cold": _score(mu_t - d_mn)["cold"]["crps"],
                                             "delta": i_mn.get("delta"), "n_source": n_match}
            if a.name == FOIL_ARM:
                # scored at TWO draw counts: a single gap cannot distinguish "the estimators
                # disagree" from "the sampler has not converged". Read the CONVERGENCE.
                row["crps_sampled_control"] = {
                    str(n): V3.crps_sampled_control(
                        y_t[cold_mask], (mu_t - d)[cold_mask], sig_t[cold_mask],
                        n_draws=n, seed=args.seed + int(fold.eval_year))
                    for n in (args.n_draws, 4 * args.n_draws)}
            arm_folds[a.name].append(row)

    oos = pd.concat(oos_rows, ignore_index=True)
    doc = {
        "story": _STORY, "scored_at": date.today().isoformat(),
        "served_config": dict(SERVED),
        "cache": {k: meta.get(k) for k in ("assembled_at", "n_games", "n_with_close")},
        "n_oos_games": int(len(oos)), "fold_years": [f["eval_year"] for f in per_fold_meta],
        "n_folds": len(folds), "folds": per_fold_meta,
        "declared_field_size": DECLARED_FIELD_SIZE,
        "m2_derivation": m2,
        "arms": {a.name: {"role": a.role, "scope": a.scope, "doc": a.doc,
                          "folds": arm_folds[a.name]} for a in ARMS},
        "reproduction_pin": check_pin(meta, oos, [f["eval_year"] for f in per_fold_meta]),
        # ⭐ the `_clv_leg`-IMMUNE implementation, NAMED: `ncaaf_val3_cold_start_mu.over_tilt_report`
        # joins on `game_id` and reads each row's own μ, so it takes NO positional index into any
        # array. ⛔ NEVER the row-misaligned `_clv_eval` (a recorded INC).
        "over_tilt": V3.over_tilt_report(df, oos, arm_folds),
        "over_tilt_implementation": ("ncaaf_val3_cold_start_mu.over_tilt_report — a `game_id` join "
                                     "that takes no positional index into any array (the "
                                     "`_clv_leg`-immune implementation). ⛔ NOT `_clv_eval`."),
        "inner_min_train_seasons": V3.INNER_MIN_TRAIN_SEASONS,
        "market_blind": True, "best_alpha": 0,
    }
    _SCORES_JSON.write_text(json.dumps(doc, indent=2, default=float))
    print(f"\n  scores → {_SCORES_JSON.relative_to(B._PROJECT_ROOT)}")
    return doc


def check_pin(meta: dict, oos: pd.DataFrame, fold_years: list[int]) -> dict[str, Any]:
    """§7 — HALT if the POPULATION is not the one this study was pre-registered against.

    `cache_assembled_at` is REPORTED, never pinned — declared forward in §7 (see
    `PIN_REPORTED_ONLY`), because it moves with the clock and carries no population information."""
    binding = {
        "n_with_close": (int(meta.get("n_with_close", -1)), PIN["n_with_close"]),
        "n_oos_games": (int(len(oos)), PIN["n_oos_games"]),
        "fold_years": (list(map(int, fold_years)), PIN["fold_years"]),
    }
    out = {k: {"got": g, "expected": e, "ok": bool(g == e), "binds": True}
           for k, (g, e) in binding.items()}
    out["cache_assembled_at"] = {
        "got": meta.get("assembled_at"), "expected": None, "ok": None, "binds": False,
        "note": ("REPORTED provenance, not a population quantity — `assemble_cache` stamps "
                 "`date.today()`, so this leg moves with the clock whatever the population is. "
                 "Declared forward in §7 of the pre-registration.")}
    return {"checks": out, "all_ok": all(v["ok"] for v in out.values() if v["binds"]),
            "binding_legs": [k for k, v in out.items() if v["binds"]],
            "reported_only": list(PIN_REPORTED_ONLY), "source": PIN["source"]}


# ===========================================================================
# Stage 2 — the gates, executed rather than narrated
# ===========================================================================

def anchor_report(arms: dict[str, Any], foil: list[dict]) -> dict[str, Any]:
    """The candidate's OWN-FORM peeking floor beside its OWN matched-n control.

    NF-W6d / NF-D20: a peek that does not beat its own matched-n control could not ACT at that
    sample size, so its floor is `INACTIVE` — uninformative, never a pass and never a fail."""
    def _mean(rows: list[dict], path: tuple[str, ...]) -> float:
        vals = []
        for r in rows:
            v: Any = r
            for k in path:
                v = v[k]
            vals.append(float(v))
        return float(np.mean(vals))

    rows = arms[CANDIDATE]["folds"]
    arm_crps = _mean(rows, ("cold", "crps"))
    peek = _mean(rows, ("own_form_peek", "crps_cold"))
    mn = _mean(rows, ("own_form_matched_n", "crps_cold"))
    peek_gain = mn - peek                     # > 0 ⇒ the peek genuinely bought something
    active = bool(peek_gain > TIE_BAND)
    gap = arm_crps - peek                     # > 0 ⇒ the arm is WORSE than its own peek
    state = ("INACTIVE" if not active else
             "BEATEN" if gap < -TIE_BAND else
             "TIED" if abs(gap) <= TIE_BAND else "FLOORED")
    per_form = {CANDIDATE: {"form": "bucket", "arm_crps": arm_crps, "peek_crps": peek,
                            "matched_n_crps": mn, "peek_gain_over_matched_n": peek_gain,
                            "anchor_pair_active": active, "gap": gap, "state": state}}
    head_orc = _mean(arms["oracle_bucket"]["folds"], ("cold", "crps"))
    head_mn = _mean(arms["matched_n_bucket"]["folds"], ("cold", "crps"))
    return {
        "headline_bucket_oracle_crps_cold": head_orc,
        "headline_matched_n_crps_cold": head_mn,
        "headline_peek_gain": head_mn - head_orc,
        "headline_pair_active": bool(head_mn - head_orc > TIE_BAND),
        "foil_crps_cold": _mean(foil, ("cold", "crps")),
        "reading": ("a peeking oracle is a floor only at MATCHED family AND MATCHED sample "
                    "(NF1.7 (b) / NF1.9 (f)); it is computed PER FORM (NF-D16 g‴) and a peek that "
                    "does not beat its own matched-n control could not act, so its floor is "
                    "INACTIVE — uninformative, never a pass and never a fail (NF-W6d / NF-D20)."),
        "per_form_oracle": per_form,
    }


def materiality(arm_folds: list[dict], foil_folds: list[dict]) -> dict[str, Any]:
    """M1 / M2 — the bars VAL3 recorded as a pre-registration gap and handed forward.

    Both BIND. Both have ZERO free parameters: M1 is VAL2's own acceptance band in the native unit
    and M2 is a closed-form function of two constants VAL2 recorded (`verify_m2_derivation`)."""
    def _agg(rows: list[dict], cell: str, key: str) -> float:
        return float(np.mean([r[cell][key] for r in rows if r[cell]["n"]]))

    foil_bias, arm_bias = _agg(foil_folds, "cold", "bias"), _agg(arm_folds, "cold", "bias")
    foil_crps, arm_crps = _agg(foil_folds, "cold", "crps"), _agg(arm_folds, "cold", "crps")
    bias_reduction = abs(foil_bias) - abs(arm_bias)
    rel_gain = (foil_crps - arm_crps) / foil_crps
    return {
        "M1_bias_reduction_pts": {
            "ok": bool(bias_reduction >= MATERIAL_BIAS_PTS),
            "value": bias_reduction, "band": MATERIAL_BIAS_PTS,
            "foil_bias": foil_bias, "arm_bias": arm_bias,
            "note": "VAL2's own acceptance band, inherited as a constant and ⛔ never re-derived."},
        "M2_relative_crps_gain": {
            "ok": bool(rel_gain >= MATERIAL_REL_CRPS_GAIN),
            "value": rel_gain, "band": MATERIAL_REL_CRPS_GAIN,
            "foil_crps": foil_crps, "arm_crps": arm_crps,
            "note": ("the closed-form relative CRPS gain of removing VAL2's 1.0-pt band from VAL2's "
                     "recorded 0.15 σ cold-start bias — σ-free, zero free parameters, re-derived at "
                     "run time by `verify_m2_derivation`.")},
    }


#: ⭐ §4.2 sensitivity — VAL3's OWN recorded `V`/`n_trials`, and the strictest combination
#: constructible from either study's declared quantities. NON-BINDING, and it can only make the
#: record stricter: the binding reading is the one declared forward in the pre-registration.
DSR_SENSITIVITY: tuple[tuple[str, int, float | None], ...] = (
    ("val3_full_field", 8, 0.05878),
    ("val3_dsr_conv_variant", 8, 0.09080),
    ("strictest_constructible", 8, None),
)


def dsr_sensitivity(series: np.ndarray) -> dict[str, Any]:
    """Would the verdict survive VAL3's HARSHER deflation bar?

    ⭐ This is the question a sceptical reader asks first of a successor whose declared field is
    smaller than its parent's: *did you clear the gate, or did you lower it?* The answer must be
    COMPUTED, not asserted — and it is reported whichever way it comes out. ⛔ It changes no
    verdict: the binding reading is §4.2's, declared forward before scoring, and reading the null
    off a sensitivity after the binding one failed would be the E2.1-r inversion (NF-D15 g″).
    """
    out: dict[str, Any] = {}
    for name, n_trials, v in DSR_SENSITIVITY:
        r = deflated_sharpe(series, n_trials=n_trials, var_trials_sr=v)
        out[name] = {"n_trials": n_trials, "var_trials_sr": v if v is not None else 1.0 / r.n_obs,
                     "sr0": float(r.sr0), "dsr": float(r.dsr),
                     "clears_gate": bool(r.dsr >= DSR_GATE), "binds": False}
    return out


def stage_decide(args) -> dict[str, Any]:
    if not _SCORES_JSON.exists():
        raise SystemExit(f"[{_STORY}] no scores — run `--stage score` first.")
    doc = json.loads(_SCORES_JSON.read_text())
    arms, n_folds = doc["arms"], int(doc["n_folds"])
    foil = arms[FOIL_ARM]["folds"]
    arm_rows = arms[CANDIDATE]["folds"]

    pin = doc["reproduction_pin"]
    if not pin["all_ok"] and not args.allow_pin_fail:
        raise SystemExit(f"[{_STORY}] §7 reproduction pin FAILED on a BINDING leg: "
                         f"{json.dumps(pin['checks'], indent=1)}\nThe population is not the one "
                         "this study was pre-registered against. Re-assemble, or re-run the PARENT "
                         "and re-anchor from ITS output (⛔ never from VAL3b's own).")

    anchors = anchor_report(arms, foil)
    # ⭐ C1–C8 are the PARENT's function, called — not a copy. `bucket_shift` is in `V3.ARMS` with
    # scope "cold", so the clause set VAL3b is judged by is byte-identically the one VAL3 used.
    clauses = V3.ship_clauses(CANDIDATE, arm_rows, foil, anchors)
    clauses["all_ok"] = all(v["ok"] for k, v in clauses.items() if k.startswith("C"))
    mat = materiality(arm_rows, foil)
    mat_ok = all(v["ok"] for v in mat.values())

    s = V3.fold_series(foil, arm_rows)                 # per-fold CRPS improvement (foil − arm)
    sk, ku = V3.series_moments(s)
    p_one = V3.paired_p(s)
    wins = int(np.sum(s > 0))
    clause_fc = cv_power.fold_consistency_clause(n_folds)
    # BH over ONE hypothesis ⇒ the cutoff IS α. Computed through the same helper so the degenerate
    # case is exercised rather than asserted.
    bh_pass, bh_cut = V3.bh({CANDIDATE: p_one}, FDR_ALPHA)
    d = (deflated_sharpe(s, n_trials=DECLARED_FIELD_SIZE, var_trials_sr=VAR_TRIALS_SR)
         if len(s) >= 3 else None)
    dsr_sens = dsr_sensitivity(s) if len(s) >= 3 else {}

    foil_cold = float(np.mean([f["cold"]["crps"] for f in foil]))
    arm_cold = float(np.mean([f["cold"]["crps"] for f in arm_rows]))
    gain = foil_cold - arm_cold
    lift_sd = float(np.mean(s) / np.std(s, ddof=1)) if float(np.std(s, ddof=1)) > 1e-15 else 0.0
    mde = cv_power.mde_in_sd_units(n_folds=n_folds, n_metrics=1)

    row = {
        "arm": CANDIDATE, "role": "candidate",
        "cold_crps": arm_cold, "gain_vs_foil_cold": gain,
        "pooled_gain_vs_foil": float(np.mean([f["pooled"]["crps"] for f in foil])
                                     - np.mean([f["pooled"]["crps"] for f in arm_rows])),
        "tie_with_foil": bool(abs(gain) <= TIE_BAND),
        "fold_wins": wins, "n_folds": n_folds,
        "fold_consistency_required": clause_fc.wins_required,
        "fold_consistency_ok": bool(clause_fc.passes(wins)),
        "sharpe": V3.sharpe(s), "series_skew": sk, "series_kurt": ku,
        "per_fold_improvement": [float(x) for x in s],
        "dsr": None if d is None else float(d.dsr),
        "sr0": None if d is None else float(d.sr0),
        "dsr_var_trials_sr_used": None if d is None else float(d.n_obs and 1.0 / d.n_obs),
        "p_one_sided": p_one, "bh_pass": bool(bh_pass[CANDIDATE]),
        "lift_in_fold_delta_sd": lift_sd,
        "calibration": {
            cell: {k: float(np.mean([f[cell][k] for f in arm_rows if f[cell]["n"]]))
                   for k in ("crps", "pit_max_decile_dev", "calib_80", "bias")}
            for cell in ("cold", "pooled", "late")},
        "mean_delta_pts": float(np.mean([abs(f["fitted"].get("delta") or 0.0) for f in arm_rows])),
        "per_fold_delta": [f["fitted"].get("delta") for f in arm_rows],
        "clauses": clauses, "materiality": mat,
    }

    ships = bool(clauses["all_ok"] and mat_ok and not row["tie_with_foil"] and gain > 0
                 and row["dsr"] is not None and row["dsr"] >= DSR_GATE and row["bh_pass"]
                 and row["fold_consistency_ok"])
    verdict = "SHIP_CORRECTION" if ships else "INCUMBENT_STANDS"

    # ── the null, classified ────────────────────────────────────────────────────────────────────
    null: dict[str, Any] = {}
    if not ships:
        failed_c = [k for k, v in clauses.items() if k.startswith("C") and not v["ok"]]
        failed_m = [k for k, v in mat.items() if not v["ok"]]
        deflation_failed = [g for g, ok in (
            ("dsr", row["dsr"] is not None and row["dsr"] >= DSR_GATE),
            ("bh_fdr", row["bh_pass"]),
            ("fold_consistency", row["fold_consistency_ok"]),
        ) if not ok]
        v = cv_power.classify_null(
            metric="crps_total_wk1_3", n_folds=n_folds, n_arms=len(CANDIDATES),
            beats_foil=bool(gain > TIE_BAND), observed_sr=row["sharpe"],
            var_trials_sr=None, fold_wins=wins, p_one_sided=p_one, bh_cutoff=bh_cut,
            skew=sk, kurt=ku, mde_sd_units=mde,
            meaningful_sd_units=None,
            declared_field_size=DECLARED_FIELD_SIZE, degenerates_excluded_from_v=None)
        null = {
            "instrument_state": v.state, "instrument_reason": v.reason,
            "instrument_retest_trigger": v.retest_trigger, "instrument_detail": v.detail,
            "constraint_clauses_failed": failed_c, "materiality_clauses_failed": failed_m,
            "deflation_gates_failed": deflation_failed,
            "binding_half": ("constraint" if failed_c else "materiality" if failed_m else
                             "deflation" if deflation_failed else "statistical"),
            "recorded_state": ("CONSTRAINT_REFUSED" if failed_c else
                               "IMMATERIAL" if failed_m else
                               f"DEFLATION_REFUSED_{deflation_failed[0].upper()}"
                               if deflation_failed else v.state),
            "why_recorded_state": (
                "a pre-registered SHIP CLAUSE refused, not the statistic — no fold count moves a "
                "clause, so a 'more seasons' trigger would be actively misleading (NF-D18)."
                if failed_c else
                "the effect is real but below a pre-registered MATERIALITY band — likewise not a "
                "power shortfall: more seasons sharpen the estimate of an effect already measured "
                "to be smaller than the band the product needs (E1.13's bounded-by-exposure shape)."
                if failed_m else
                "a pre-registered DEFLATION gate was evaluated and FAILED." if deflation_failed else
                "no clause and no gate bound; the statistic is what refused."),
            "mde_sd_units": mde, "observed_lift_sd_units": lift_sd,
            "power_reading": (
                f"the design detects a true per-fold lift of {mde} fold-delta SDs at 80 % power; "
                f"the observed lift is {lift_sd:.3f} SDs "
                + ("— ABOVE the MDE, so the design COULD have seen an effect of this size and the "
                   "binding gate above is the finding, not a power shortfall."
                   if mde is not None and lift_sd >= mde else
                   "— BELOW the MDE, so this design could not reliably detect an effect of this "
                   "size; read the null as POWER-LIMITED on that axis.")),
        }

    flips = {a: 0 for a in (FOIL_ARM, CANDIDATE)}
    for i in range(n_folds):
        flips[min((FOIL_ARM, CANDIDATE),
                  key=lambda a: arms[a]["folds"][i]["cold"]["crps"])] += 1
    draw_ns = sorted(int(k) for k in foil[0]["crps_sampled_control"])
    ctl_gaps = {n: max(abs(f["cold"]["crps"] - f["crps_sampled_control"][str(n)]) for f in foil)
                for n in draw_ns}

    out = {
        "story": _STORY, "decided_at": date.today().isoformat(),
        "verdict": verdict, "ships": ships,
        "n_folds": n_folds, "fold_years": doc["fold_years"], "n_oos_games": doc["n_oos_games"],
        "cache": doc["cache"], "served_config": doc["served_config"],
        "declared_field_size": DECLARED_FIELD_SIZE,
        "selectable_arms": len(CANDIDATES),
        "reproduction_pin": pin,
        "m2_derivation": doc["m2_derivation"],
        "deflation": {
            # ⛔ §4.1 — INAPPLICABLE, and no number is computed. Not "passed".
            "pbo": None,
            "pbo_state": "INAPPLICABLE",
            "pbo_note": (
                "a SINGLE pre-registered contrast has NO SEARCH to overfit — CSCV/PBO asks whether "
                "the in-sample winner of a search holds up out of sample, and there is no winner to "
                "pick. `cv_power.classify_null`'s own n_arms<2 branch says exactly this and emits "
                "NO re-test trigger. ⛔ Recorded INAPPLICABLE, never 'passed'; a two-arm CSCV number "
                "is deliberately NOT computed even as a diagnostic, because reproducing the figure "
                "VAL3 already reported as a lower bound would read as 'the gate we failed now "
                "passes' — the misreading this successor shape exists to avoid (§4.1)."),
            "dsr_gate": DSR_GATE,
            "var_trials_sr": VAR_TRIALS_SR,
            "var_trials_sr_effective": None if d is None else 1.0 / d.n_obs,
            "sr0": None if d is None else float(d.sr0),
            "v_note": (
                "`V` is UNDEFINED at one selectable arm (a variance needs ≥2 points), so "
                "`deflated_sharpe`'s documented fallback — the ASYMPTOTIC null variance of a Sharpe "
                "estimate, V = 1/n_obs — is what this study DECLARED FORWARD. It is a DESIGN "
                "quantity: it depends only on the fold count. ⛔ Importing VAL3's measured V "
                "(0.05878) would be a dispersion from a field this registration does not have. "
                "⭐ The resulting bar SR0 = 0.18376 is LOWER than VAL3's 0.35374, and that is the "
                "whole arithmetic content of the successor shape: a 2-arm design carries almost no "
                "expected-max inflation. It is legitimate ONLY because the family is declared "
                "FORWARD on a mechanism argument and scored whole — never trimmed after the fact "
                "(MH2.2). The NF-W8-0d lockstep invariant does NOT apply: V is not a field variance."),
            "dsr_sensitivity": dsr_sens,
            "dsr_sensitivity_note": (
                "⭐ NON-BINDING, and it answers the first question a sceptical reader asks of a "
                "successor whose field is smaller than its parent's: did the arm CLEAR the gate, or "
                "was the gate LOWERED? Re-scored under VAL3's own recorded `V`/`n_trials` and under "
                "the strictest combination constructible from either study's declared quantities. "
                "⛔ It changes no verdict — the binding reading is §4.2's, declared forward before "
                "scoring; adopting a different one after the fact would be the E2.1-r inversion."),
            "dsr_ceiling_at_n_folds": cv_power.dsr_ceiling(n_folds),
            "bh_alpha": FDR_ALPHA, "bh_cutoff": bh_cut,
            "bh_note": ("ONE hypothesis ⇒ the Benjamini–Hochberg cutoff IS α. Stated so a reader "
                        "sees the multiplicity correction became trivial as a CONSEQUENCE of the "
                        "declared design, not because it was switched off."),
            "fold_consistency": {"n_folds": n_folds, "required_wins": clause_fc.wins_required,
                                 "attainable": bool(clause_fc.attainable),
                                 "attained_false_fire": float(clause_fc.attained_false_fire),
                                 "legacy_required": clause_fc.legacy_wins_required,
                                 "legacy_false_fire": float(clause_fc.legacy_false_fire)},
            "fold_flip_distribution": flips,
        },
        "materiality_bars": {
            "M1_bias_reduction_pts": MATERIAL_BIAS_PTS,
            "M2_relative_crps_gain": MATERIAL_REL_CRPS_GAIN,
            "mde_sd_units": mde,
            "note": ("registered FORWARD, closing the gap VAL3 recorded. Both BIND and both are "
                     "STRICTER than VAL3's clause set — a new refusal condition, not a loosened "
                     "one. Zero free parameters: closed-form functions of constants VAL2 recorded "
                     "before VAL3 existed."),
        },
        "crps_instrument_control": {
            "max_abs_gap_by_draws": {str(n): g for n, g in ctl_gaps.items()},
            "gap_shrinks_with_draws": bool(ctl_gaps[draw_ns[-1]] < ctl_gaps[draw_ns[0]]),
            "gap_pct_of_crps": float(100.0 * ctl_gaps[draw_ns[-1]] / foil_cold),
            "reading": ("the closed-form Gaussian CRPS and the ensemble identity score the SAME "
                        "predictive. Read the CONVERGENCE, not the single gap."),
        },
        "anchors": anchors,
        "channel_attribution_cited_from_val3": {
            "magnitude": {"pair": "bucket_shift − week_blind", "cell": "wk1-3",
                          "mean_gain": 0.0704, "folds_positive": 7, "n_folds": 8, "p": 0.0051},
            "scoping": {"pair": "week_blind − pooled_level", "cell": "pooled",
                        "mean_gain": 0.0000, "folds_positive": 3, "n_folds": 8, "p": 0.4928},
            "note": ("⛔ CITED from `ncaaf_val3_cold_start_mu.md` §4b, NOT re-measured here. VAL3's "
                     "matched foils are honest, in-principle-shippable estimators; calling one a "
                     "'diagnostic' to keep it out of VAL3b's multiplicity count would be exactly "
                     "the laundering MH2.2 forbids, so they are OUT of this field entirely. The "
                     "cost is disclosed: VAL3b does not independently re-attribute the channel."),
        },
        "foil": {"arm": FOIL_ARM, "cold_crps": foil_cold,
                 "pooled_crps": float(np.mean([f["pooled"]["crps"] for f in foil])),
                 "cold_bias_pts": float(np.mean([f["cold"]["bias"] for f in foil])),
                 "pooled_bias_pts": float(np.mean([f["pooled"]["bias"] for f in foil]))},
        "arm": row, "_foil_folds": foil,
        "null_classification": null,
        "over_tilt": doc["over_tilt"],
        "over_tilt_implementation": doc["over_tilt_implementation"],
        "folds": doc["folds"], "inner_min_train_seasons": doc["inner_min_train_seasons"],
        "market_blind": True, "best_alpha": 0,
        "serving_change": None,
        "ship_gating": ("⛔ SHIP_CORRECTION does NOT serve anything. A pre-opener ship needs the "
                        "S1-serve-class train/serve PARITY check against the SERVED artifact "
                        "contract AND explicit operator approval; otherwise DEPLOY-HELD with the "
                        "gap named (spec AC (a)/(b)). Nothing serves from this session."),
    }
    _OUT_JSON.write_text(json.dumps(out, indent=2, default=float))
    _OUT_MD.write_text(render_md(out))
    return out


# ===========================================================================
# Report
# ===========================================================================

def _f(x: float | None, nd: int = 4) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def render_md(d: dict) -> str:
    A: list[str] = []
    a = A.append
    f, r = d["foil"], d["arm"]
    a(f"# {_STORY} — the cold-start μ_total correction as ONE pre-registered contrast")
    a("")
    a(f"**Verdict: `{d['verdict']}`.** Market-blind · `best_alpha = 0` · no serving change, no "
      "registry edit, no refit of a served artifact, no bet.")
    a("")
    a(f"_Cache assembled {d['cache']['assembled_at']} · {d['n_oos_games']:,} OOS games · "
      f"{d['n_folds']} purged folds {d['fold_years'][0]}–{d['fold_years'][-1]} · served config "
      f"`{d['served_config']['mc']}`/`{d['served_config']['contract']}`/"
      f"`{d['served_config']['form']}` · declared field {d['declared_field_size']} "
      f"({d['selectable_arms']} selectable)_")
    a("")
    a("## 1. The contrast")
    a("")
    a("| arm | role | δ̄ (pts) | CRPS wk1-3 | gain vs foil | folds won | DSR | p | C1–C8 | M1/M2 |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    a(f"| `none` (foil) | foil | 0.000 | {f['cold_crps']:.4f} | — | — | — | — | — | — |")
    bad = [k.split("_")[0] for k, v in r["clauses"].items() if k.startswith("C") and not v["ok"]]
    badm = [k.split("_")[0] for k, v in r["materiality"].items() if not v["ok"]]
    a(f"| `{r['arm']}` | candidate | {r['mean_delta_pts']:.3f} | {r['cold_crps']:.4f} | "
      f"{r['gain_vs_foil_cold']:+.4f} | {r['fold_wins']}/{r['n_folds']} | {_f(r['dsr'], 3)} | "
      f"{r['p_one_sided']:.4f} | {'✅' if not bad else '❌ ' + ','.join(bad)} | "
      f"{'✅' if not badm else '❌ ' + ','.join(badm)} |")
    a("")
    a(f"Foil cold-start bias **{f['cold_bias_pts']:+.3f} pts** (pooled {f['pooled_bias_pts']:+.3f}); "
      f"after the correction **{r['calibration']['cold']['bias']:+.3f}** (pooled "
      f"{r['calibration']['pooled']['bias']:+.3f}).")
    a("")
    a("Per-fold CRPS improvement (foil − arm): " +
      ", ".join(f"{y} {v:+.4f}" for y, v in zip(d["fold_years"], r["per_fold_improvement"])))
    a("")
    a("## 2. Materiality — the bars VAL3 recorded as a pre-registration gap and handed FORWARD")
    a("")
    m = r["materiality"]
    a("| bar | required | observed | ok |")
    a("|---|---|---|---|")
    m1, m2 = m["M1_bias_reduction_pts"], m["M2_relative_crps_gain"]
    a(f"| **M1** — wk1-3 \\|bias\\| reduction (VAL2's inherited band) | ≥ {m1['band']:.2f} pts | "
      f"**{m1['value']:+.3f} pts** ({m1['foil_bias']:+.3f} → {m1['arm_bias']:+.3f}) | "
      f"{'✅' if m1['ok'] else '❌'} |")
    a(f"| **M2** — relative wk1-3 CRPS gain (closed form from VAL2's 0.15 σ / 1.0 pt) | "
      f"≥ {m2['band']*100:.4f} % | **{m2['value']*100:.4f} %** | {'✅' if m2['ok'] else '❌'} |")
    a("")
    md = d["m2_derivation"]
    a(f"_M2 re-derived at run time from VAL2's two constants: C(0.150) = {md['C_foil']:.8f}, "
      f"C(0.085) = {md['C_corrected']:.8f} ⇒ {md['derived_rel_gain']*100:.4f} % (module literal "
      f"{md['module_literal']*100:.4f} %). Removing the bias ENTIRELY is worth "
      f"{md['full_removal_rel_gain']*100:.4f} %, so M2 asks for "
      f"{md['derived_rel_gain']/md['full_removal_rel_gain']*100:.0f} % of the whole available "
      "headroom. Zero free parameters._")
    a("")
    a("## 3. Calibration — the AC's \"without degrading aggregate PIT\"")
    a("")
    a("| arm | wk1-3 bias | wk1-3 PIT | wk1-3 calib80 | pooled bias | **pooled PIT** | pooled calib80 |")
    a("|---|---|---|---|---|---|---|")
    fc = {cell: {k: float(np.mean([x[cell][k] for x in d["_foil_folds"] if x[cell]["n"]]))
                 for k in ("pit_max_decile_dev", "calib_80", "bias")} for cell in ("cold", "pooled")}
    a(f"| `none` (foil) | {fc['cold']['bias']:+.3f} | {fc['cold']['pit_max_decile_dev']:.4f} | "
      f"{fc['cold']['calib_80']:.4f} | {fc['pooled']['bias']:+.3f} | "
      f"**{fc['pooled']['pit_max_decile_dev']:.4f}** | {fc['pooled']['calib_80']:.4f} |")
    cb = r["calibration"]
    a(f"| `{r['arm']}` | {cb['cold']['bias']:+.3f} | {cb['cold']['pit_max_decile_dev']:.4f} | "
      f"{cb['cold']['calib_80']:.4f} | {cb['pooled']['bias']:+.3f} | "
      f"**{cb['pooled']['pit_max_decile_dev']:.4f}** | {cb['pooled']['calib_80']:.4f} |")
    a("")
    a(f"C1's tolerance is **+{PIT_DEGRADE_TOL}** on the pooled PIT max-decile-dev; C2/C3 floor "
      f"`calib_80` at **{CALIB_FLOOR}** — a FLOOR, never a target (NF1.8/E2.1-r).")
    a("")
    a("## 4. Ship clauses C1–C8 — the PARENT's function, called (not a copy)")
    a("")
    a("| clause | ok | detail |")
    a("|---|---|---|")
    for k, v in r["clauses"].items():
        if not k.startswith("C"):
            continue
        det = ", ".join(f"{kk}={vv}" for kk, vv in v.items() if kk != "ok")
        a(f"| `{k}` | {'✅' if v['ok'] else '❌'} | {det} |")
    a("")
    a("## 5. Gates")
    a("")
    g = d["deflation"]
    a(f"- **PBO / CSCV — `{g['pbo_state']}`.** {g['pbo_note']}")
    a(f"- **DSR** {_f(r['dsr'], 4)} (gate ≥ {g['dsr_gate']}); observed SR {r['sharpe']:.4f} vs "
      f"**SR0 {_f(g['sr0'])}**, `V` = {_f(g['var_trials_sr_effective'], 5)} "
      f"(the asymptotic 1/n_obs default); ceiling at {d['n_folds']} folds "
      f"{g['dsr_ceiling_at_n_folds']:.5f} ⇒ the gate is REACHABLE at this design.")
    a(f"  - {g['v_note']}")
    if g.get("dsr_sensitivity"):
        a(f"  - **DSR sensitivity — did the arm clear the gate, or was the gate lowered?** "
          f"{g['dsr_sensitivity_note']}")
        a("")
        a("    | reading | n_trials | `V` | SR0 | DSR | clears ≥0.95 | binds |")
        a("    |---|---|---|---|---|---|---|")
        a(f"    | **VAL3b, declared forward** | {DECLARED_FIELD_SIZE} | "
          f"{_f(g['var_trials_sr_effective'], 5)} | {_f(g['sr0'], 5)} | {_f(r['dsr'], 6)} | "
          f"{'✅' if r['dsr'] >= g['dsr_gate'] else '❌'} | ✅ **BINDING** |")
        for nm, v in g["dsr_sensitivity"].items():
            a(f"    | `{nm}` | {v['n_trials']} | {v['var_trials_sr']:.5f} | {v['sr0']:.5f} | "
              f"{v['dsr']:.6f} | {'✅' if v['clears_gate'] else '❌'} | sensitivity |")
        a("")
    a(f"- **BH** α {g['bh_alpha']} → cutoff {g['bh_cutoff']:.5f}, p {r['p_one_sided']:.4f} — "
      f"{'✅' if r['bh_pass'] else '❌'}. {g['bh_note']}")
    fcs = g["fold_consistency"]
    a(f"- **Fold consistency** (`cv_power.fold_consistency_clause`): {fcs['required_wins']} of "
      f"{fcs['n_folds']} required, attained {r['fold_wins']} — "
      f"{'✅' if r['fold_consistency_ok'] else '❌'}; false-fire {fcs['attained_false_fire']:.4f} "
      f"(legacy would ask {fcs['legacy_required']} at {fcs['legacy_false_fire']:.4f})")
    a(f"- **Fold flips** (which arm wins each fold's cold cell): {g['fold_flip_distribution']}")
    a("")
    a("## 6. Anchors")
    a("")
    an = d["anchors"]
    a(f"- headline bucket peek CRPS **{an['headline_bucket_oracle_crps_cold']:.4f}** vs its "
      f"matched-n control **{an['headline_matched_n_crps_cold']:.4f}** ⇒ peek gain "
      f"{an['headline_peek_gain']:+.4f}, pair "
      f"**{'ACTIVE' if an['headline_pair_active'] else 'INACTIVE'}**")
    a(f"- {an['reading']}")
    a("")
    a("| arm | form | own-form peek | its matched-n | peek gain | pair | arm − peek | C8 state |")
    a("|---|---|---|---|---|---|---|---|")
    for name, v in an["per_form_oracle"].items():
        a(f"| `{name}` | `{v['form']}` | {v['peek_crps']:.4f} | {v['matched_n_crps']:.4f} | "
          f"{v['peek_gain_over_matched_n']:+.4f} | "
          f"{'ACTIVE' if v['anchor_pair_active'] else 'INACTIVE'} | {v['gap']:+.4f} | "
          f"{v['state']} |")
    a("")
    ch = d["channel_attribution_cited_from_val3"]
    a("**Channel attribution — CITED from VAL3, not re-measured.** magnitude "
      f"(`{ch['magnitude']['pair']}`, {ch['magnitude']['cell']}) {ch['magnitude']['mean_gain']:+.4f}, "
      f"{ch['magnitude']['folds_positive']}/{ch['magnitude']['n_folds']}, p {ch['magnitude']['p']}; "
      f"scoping (`{ch['scoping']['pair']}`, {ch['scoping']['cell']}) "
      f"{ch['scoping']['mean_gain']:+.4f}, {ch['scoping']['folds_positive']}/"
      f"{ch['scoping']['n_folds']}, p {ch['scoping']['p']}. {ch['note']}")
    a("")
    ic = d["crps_instrument_control"]
    a("**Instrument control** — closed-form vs ensemble CRPS on the foil: "
      + "  →  ".join(f"{n} draws {gg:.5f}" for n, gg in ic["max_abs_gap_by_draws"].items())
      + f" ({ic['gap_pct_of_crps']:.3f} % of the CRPS; shrinks with draws: "
        f"{'✅' if ic['gap_shrinks_with_draws'] else '❌'}). {ic['reading']}")
    a("")
    a("## 7. The wk1-3 over-tilt — DESCRIPTIVE")
    a("")
    t = d["over_tilt"]
    if t.get("state") != "EVALUABLE":
        a(f"⚠️ **UNEVALUABLE** — {t.get('note')}")
    else:
        a(f"On the {t['n_close_carrying_cold']:,} close-carrying cold-start rows (over actually hit "
          f"**{t['over_actually_hit']:.3f}**). ⚠️ DESCRIPTIVE — the only market-touching number "
          "here, never a clause and never an edge claim.")
        a("")
        a(f"⭐ **Implementation, NAMED:** {d['over_tilt_implementation']}")
        a("")
        a("| arm | model → over | mean μ − close (pts) |")
        a("|---|---|---|")
        for name, v in t["arms"].items():
            a(f"| `{name}` | {v['model_to_over']:.3f} | {v['mean_offset_pts']:+.3f} |")
    a("")
    if d["null_classification"]:
        n = d["null_classification"]
        a("## 8. The null, classified")
        a("")
        a(f"- `cv_power.classify_null` state **`{n['instrument_state']}`** — {n['instrument_reason']}")
        a(f"- **recorded state `{n['recorded_state']}`** (binding half: {n['binding_half']})")
        a(f"- {n['why_recorded_state']}")
        a(f"- {n['power_reading']}")
        if n["recorded_state"] in ("CONSTRAINT_REFUSED", "IMMATERIAL"):
            a("- ⛔ **No fold/season re-test trigger is published.** The instrument's own trigger, "
              f"preserved for the record: `{n['instrument_retest_trigger']}`")
        else:
            a(f"- re-test trigger: `{n['instrument_retest_trigger']}`")
    a("")
    a("## 9. Reproduction pin")
    a("")
    p = d["reproduction_pin"]
    a(f"Anchored on the PARENT (`{p['source']}`) and the fold structure — ⛔ never on VAL3b's own "
      f"output. Binding legs {'PASS ✅' if p['all_ok'] else 'FAIL ❌'}.")
    a("")
    a("| leg | got | expected | binds | ok |")
    a("|---|---|---|---|---|")
    for k, v in p["checks"].items():
        a(f"| `{k}` | {v['got']} | {v['expected'] if v['binds'] else '— (reported)'} | "
          f"{'✅' if v['binds'] else '❌ reported only'} | "
          f"{'✅' if v['ok'] else ('—' if v['ok'] is None else '❌')} |")
    a("")
    a("_The `cache_assembled_at` leg is REPORTED, not pinned — declared forward in §7 of the "
      "pre-registration, because `assemble_cache` stamps `date.today()` and that leg moves with the "
      "clock whatever the population is. The three population legs HALT._")
    a("")
    a(f"## 10. Ship gating")
    a("")
    a(d["ship_gating"])
    return "\n".join(A) + "\n"


def report(d: dict) -> None:
    f, r = d["foil"], d["arm"]
    print(f"\n=== {_STORY} — verdict {d['verdict']} ===")
    print(f"  foil `none`     CRPS wk1-3 {f['cold_crps']:.4f}  bias {f['cold_bias_pts']:+.3f} pts")
    print(f"  `{r['arm']}`  CRPS wk1-3 {r['cold_crps']:.4f}  bias "
          f"{r['calibration']['cold']['bias']:+.3f} pts  gain {r['gain_vs_foil_cold']:+.4f}  "
          f"wins {r['fold_wins']}/{r['n_folds']}  δ̄ {r['mean_delta_pts']:.3f}")
    m = r["materiality"]
    for k, v in m.items():
        print(f"  {k:<28} {'✅' if v['ok'] else '❌'}  value {v['value']:.6f}  band {v['band']}")
    bad = [k for k, v in r["clauses"].items() if k.startswith("C") and not v["ok"]]
    print(f"  clauses C1–C8: {'✅ all ok' if not bad else '❌ ' + ', '.join(bad)}")
    g = d["deflation"]
    print(f"  PBO {g['pbo_state']} (no number computed — see the note)")
    print(f"  DSR {_f(r['dsr'])} (gate ≥{g['dsr_gate']}) | SR {r['sharpe']:.4f} vs SR0 "
          f"{_f(g['sr0'])} | V {_f(g['var_trials_sr_effective'], 5)} (asymptotic 1/n_obs) | "
          f"ceiling {g['dsr_ceiling_at_n_folds']:.5f}")
    for nm, v in g.get("dsr_sensitivity", {}).items():
        print(f"    sensitivity {nm:<26} n_trials={v['n_trials']} V={v['var_trials_sr']:.5f} "
              f"SR0={v['sr0']:.5f} DSR={v['dsr']:.6f} "
              f"{'clears' if v['clears_gate'] else 'FAILS'}")
    print(f"  BH cut {g['bh_cutoff']:.5f}, p {r['p_one_sided']:.4f} "
          f"{'✅' if r['bh_pass'] else '❌'} | fold consistency needs "
          f"{g['fold_consistency']['required_wins']}/{g['fold_consistency']['n_folds']} "
          f"{'✅' if r['fold_consistency_ok'] else '❌'}")
    an = d["anchors"]["per_form_oracle"][CANDIDATE]
    print(f"  C8 own-form floor: arm {an['arm_crps']:.4f} vs peek {an['peek_crps']:.4f} "
          f"(matched-n {an['matched_n_crps']:.4f}) → pair "
          f"{'ACTIVE' if an['anchor_pair_active'] else 'INACTIVE'}, state {an['state']}")
    t = d["over_tilt"]
    if t.get("state") == "EVALUABLE":
        print(f"\n  ── wk1-3 over-tilt (DESCRIPTIVE; n={t['n_close_carrying_cold']:,}, over hit "
              f"{t['over_actually_hit']:.3f}; `_clv_leg`-immune impl) ──")
        for name, v in t["arms"].items():
            print(f"    {name:<18} model→over {v['model_to_over']:.3f}   mean μ−close "
                  f"{v['mean_offset_pts']:+.3f}")
    if d["null_classification"]:
        n = d["null_classification"]
        print(f"\n  null: instrument `{n['instrument_state']}` / recorded `{n['recorded_state']}` "
              f"(binding half: {n['binding_half']})")
        print(f"    {n['power_reading']}")
    print(f"\n  → {_OUT_JSON.relative_to(B._PROJECT_ROOT)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=f"{_STORY} — the cold-start μ correction, one contrast")
    ap.add_argument("--stage", choices=["score", "decide", "all"], default="all")
    ap.add_argument("--seed", type=int, default=B._SEED)
    ap.add_argument("--n-draws", type=int, default=5_000,
                    help="draws for the CRPS instrument control ONLY; the scored CRPS is closed-form")
    ap.add_argument("--max-folds", type=int, default=None)
    ap.add_argument("--allow-pin-fail", action="store_true",
                    help="⚠️ proceed past a §7 reproduction-pin HALT (diagnostics only).")
    args = ap.parse_args(argv)
    if args.stage in ("score", "all"):
        stage_score(args)
    if args.stage in ("decide", "all"):
        report(stage_decide(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
