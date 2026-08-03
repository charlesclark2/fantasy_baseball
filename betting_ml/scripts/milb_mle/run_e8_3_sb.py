"""run_e8_3_sb.py — E8.3: the pre-registered stolen-base translation bake-off.

Runs the §0.5 bake-off that decides whether the prospect board can carry a REAL stolen-base read or
must keep E8.1's "SB is invisible to us" caveat.

    uv run python -m betting_ml.scripts.milb_mle.run_e8_3_sb            # primary target, full field
    uv run python -m betting_ml.scripts.milb_mle.run_e8_3_sb --drop-censored   # robustness arm

PRE-REGISTRATION (fixed before the first run; see `sb_translation` for the mechanism rationale)
-----------------------------------------------------------------------------------------------
* **CV**: leave-one-MLB-debut-cohort-out, EXPANDING window — fold Y trains on players who debuted
  strictly before Y and scores on cohort Y. Identical in design to E7.3's, so an SB weight is
  commensurable with the k_pct/bb_pct/iso weights it would sit beside.
* **Selector**: CRPS (proper). MAE is reported and never selected on (NF-D11/NF-D14).
* **Primary target**: `sb_rate = SB/SBO`. Standard roto 5×5 scores GROSS SB, so this is the
  category-relevant ability read; the decomposition (attempt × success) and the coarser `sb_per_pa`
  run as a separate, smaller target-FORM family so the primary field stays one coherent declared
  family (MH2 (a)).
* **Field**: 12 arms — foil + 2 degenerates + no-translation reference + 8 learner configs across 4
  classes, era variants registered as MATCHED FOILS (NF-D10).
* **Anchors, every fold**: `degenerate_zero` and `degenerate_mean` must LOSE; the peeking `oracle`
  must not be beaten by the MATCHED-n candidate; the `permutation` must lose. A failure to FIT raises
  (NF1.7 (a)).
* **Gates**: `h_harness.numeric_gate` — beats the foil, calibrated fold-consistency clause,
  PBO < 0.20, DSR ≥ 0.95 over the ELIGIBLE (non-anchor) field.
* **A null is classified**, not shrugged: `cv_power.classify_null` names which of the seven states.
* **Ship rule**: a pass wires the metric into `MLE_METRIC_WEIGHTS` at its MEASURED OOS translation
  correlation — the same rule every other metric obeys. A null gets ZERO weight and is EXCLUDED;
  carrying it at a token weight would launder a null into a ranking.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.milb_mle import sb_translation as sbt  # noqa: E402
from betting_ml.scripts.milb_mle.h_harness import (  # noqa: E402
    MIN_DSR, MAX_PBO, numeric_gate, pbo_reading,
)
from betting_ml.scripts.milb_mle.run_e7_12_slice1 import deflation_report, paired_anchor  # noqa: E402

log = logging.getLogger("e8_3.run")

ARTIFACTS = (_PROJECT_ROOT
             / "quant_sports_intel_models/baseball/edge_program/ablation_results/e8_3_artifacts")
REPORT = (_PROJECT_ROOT
          / "quant_sports_intel_models/baseball/edge_program/ablation_results/e8_3_sb_translation.md")


# ══════════════════════════════════════════════════════════════════════════════════════
# The CV loop
# ══════════════════════════════════════════════════════════════════════════════════════

def run_cv(data: pd.DataFrame, field: list[sbt.ArmSpec], *,
           min_test: int = 10) -> dict:
    """Expanding-window leave-one-debut-cohort-out CV over the whole field + the anchors.

    Returns per-fold CRPS and MAE matrices (folds × arms), the pooled OOS predictions for the
    translation correlation, and the anchor panel.
    """
    lab = data[data["usable"]].copy()
    cohorts = sorted(int(c) for c in lab["debut_cohort"].dropna().unique())
    folds = [c for c in cohorts
             if any(p < c for p in cohorts) and int((lab["debut_cohort"] == c).sum()) >= min_test]
    if len(folds) < 2:
        raise ValueError(f"need ≥2 evaluable debut cohorts; got {folds} from {cohorts}")

    labels = [a.label for a in field]
    crps = pd.DataFrame(index=folds, columns=labels, dtype=float)
    mae = pd.DataFrame(index=folds, columns=labels, dtype=float)
    anchor_crps = pd.DataFrame(index=folds, dtype=float,
                               columns=["oracle_peek", "matched_n", "permutation"])
    pooled: list[pd.DataFrame] = []
    notes: list[str] = []

    for year in folds:
        train = lab[lab["debut_cohort"] < year]
        test = lab[lab["debut_cohort"] == year]
        if train.empty or test.empty:
            continue
        y = test["target"].to_numpy(float)
        fold_pred: dict[str, np.ndarray] = {}
        for spec in field:
            try:
                arm = spec.factory().fit(train)
                mu, sd = arm.predict(test)
                s = sbt.score_predictions(mu, sd, y)
                crps.loc[year, spec.label] = s["crps"]
                mae.loc[year, spec.label] = s["mae"]
                fold_pred[spec.label] = mu
            except Exception as e:  # noqa: BLE001 - a degenerate fold must not kill the sweep
                notes.append(f"fold {year} arm {spec.label}: {type(e).__name__}: {e}")

        # ── anchors: fitted against the BEST SELECTABLE arm's own family, this fold ────────────
        sel = [a for a in field if a.selectable and np.isfinite(crps.loc[year, a.label])]
        if sel:
            best_here = min(sel, key=lambda a: crps.loc[year, a.label])
            for key, fn in (("oracle_peek", sbt.fit_oracle),
                            ("matched_n", sbt.fit_matched_n_candidate),
                            ("permutation", sbt.fit_permutation)):
                mu, sd = fn(best_here.factory, train, test)   # RAISES on failure (NF1.7 (a))
                anchor_crps.loc[year, key] = sbt.score_predictions(mu, sd, y)["crps"]
            pooled.append(pd.DataFrame({
                "debut_cohort": year, "player_id": test["player_id"].to_numpy(),
                "level": test["level"].to_numpy(), "y": y,
                "yhat": fold_pred[best_here.label], "arm": best_here.label,
            }))

    return {"crps": crps.astype(float), "mae": mae.astype(float),
            "anchors": anchor_crps.astype(float), "folds": folds,
            "pooled": pd.concat(pooled, ignore_index=True) if pooled else pd.DataFrame(),
            "notes": notes, "n_labelled": int(len(lab))}


def leaderboard(cv: dict, field: list[sbt.ArmSpec], foil: str = "L0_foil") -> pd.DataFrame:
    """Per-arm mean CRPS/MAE, fold win rate vs the foil, and % lift — sorted by the SELECTOR."""
    crps, mae = cv["crps"], cv["mae"]
    foil_crps = crps[foil]
    rows = []
    for spec in field:
        c = crps[spec.label]
        rows.append({
            "arm": spec.label,
            "selectable": spec.selectable,
            "oos_mae": float(c.mean(skipna=True)),          # the SELECTOR (CRPS) under the
                                                            # harness's generic lower-is-better name
            "crps": float(c.mean(skipna=True)),
            "mae_reported": float(mae[spec.label].mean(skipna=True)),
            "fold_win_rate": float((c < foil_crps).mean()),
            "pct_lift_vs_foil": float(100.0 * (foil_crps.mean() - c.mean()) / max(1e-12, foil_crps.mean())),
            "pair_with": spec.pair_with,
            "note": spec.note,
        })
    return pd.DataFrame(rows).sort_values("crps").reset_index(drop=True)


def read_anchors(cv: dict, lb: pd.DataFrame, foil: str = "L0_foil") -> dict:
    """Evaluate every anchor and say plainly what each one means. BLOCKS where NF1.7 says it must."""
    crps, anc = cv["crps"], cv["anchors"]
    sel = lb[lb["selectable"]]
    if sel.empty:
        return {"ok": False, "reason": "no selectable arm produced a finite score"}
    best = str(sel.iloc[0]["arm"])
    out: dict = {"best_arm": best, "violations": [], "readings": {}}

    # (c) BOTH degenerates must lose — on the SELECTOR. Their MAE is reported beside it so the
    #     inversion is measured, not reasoned about (NF-D14).
    for deg in ("degenerate_zero", "degenerate_mean"):
        row = lb[lb["arm"] == deg]
        if row.empty:
            out["violations"].append(f"{deg} ABSENT — a missing anchor is a hard failure (NF1.7 (a))")
            continue
        beats = paired_anchor(crps, deg, best)
        wins_crps = bool(row.iloc[0]["crps"] < sel.iloc[0]["crps"])
        wins_mae = bool(row.iloc[0]["mae_reported"] < sel.iloc[0]["mae_reported"])
        out["readings"][deg] = {
            "crps": round(float(row.iloc[0]["crps"]), 6),
            "mae": round(float(row.iloc[0]["mae_reported"]), 6),
            "beats_best_on_crps": wins_crps,
            "beats_best_on_mae": wins_mae,
            "paired": beats,
        }
        if wins_crps:
            out["violations"].append(
                f"⛔ {deg} BEATS the best arm on CRPS — the SELECTION METRIC IS INVERTED (NF-D11). "
                f"Nothing downstream of this is trustworthy.")

    # (b) the peeking oracle is a floor only at MATCHED n
    orc, mn = float(anc["oracle_peek"].mean()), float(anc["matched_n"].mean())
    out["readings"]["oracle_floor"] = {
        "oracle_crps": round(orc, 6), "matched_n_crps": round(mn, 6),
        "oracle_respected_at_matched_n": bool(orc <= mn + 1e-12),
        "best_arm_crps": round(float(sel.iloc[0]["crps"]), 6),
        "best_beats_oracle": bool(float(sel.iloc[0]["crps"]) < orc),
    }
    if orc > mn + 1e-12:
        out["violations"].append(
            f"⛔ the PEEKING oracle ({orc:.6f}) loses to its own MATCHED-n candidate ({mn:.6f}) — "
            f"peeking must help at equal family AND equal resolution, so the metric or the harness "
            f"is mis-specified (NF1.7 (b) / NF1.9 (f)).")

    # ── PERMUTATION ────────────────────────────────────────────────────────────────────────────
    # The gated question is "does it SYSTEMATICALLY lose to the BEST ARM?" — shuffling destroys the
    # feature→label relation, so an arm that still competed would mean the winner's margin came from
    # something other than the feature.
    #
    # ⚠️ The permutation-vs-FOIL comparison is reported as a PRE-REGISTERED EXPECTED TIE, not gated.
    # A shuffle destroys the feature relation but PRESERVES the label's marginal and level structure,
    # which is exactly what the level-mean foil encodes — so ≈equality is the predicted result. The
    # first cut of this story gated on it and "caught" a 1.4% gap the paired test scores at p=0.87
    # (5/11 folds): a numerical tie read as fatal, the error `paired_anchor` exists to prevent.
    perm = float(anc["permutation"].mean())
    foil_c = float(crps[foil].mean())
    best_c = float(sel.iloc[0]["crps"])
    perm_df = pd.DataFrame({"permutation": anc["permutation"].to_numpy(float),
                            foil: crps[foil].to_numpy(float),
                            best: crps[best].to_numpy(float)}, index=crps.index)
    vs_best = paired_anchor(perm_df, "permutation", best)
    vs_foil = paired_anchor(perm_df, "permutation", foil)
    out["readings"]["permutation"] = {
        "crps": round(perm, 6), "best_arm_crps": round(best_c, 6), "foil_crps": round(foil_c, 6),
        "loses_to_best_arm": bool(perm > best_c),
        "paired_vs_best": vs_best,
        "expected_tie_vs_foil": {
            "gap": round(perm - foil_c, 6),
            "pct_of_foil": round(100.0 * (perm - foil_c) / max(1e-12, foil_c), 3),
            "paired": vs_foil,
            "reading": ("TIE as predicted — a shuffle preserves the marginal/level structure the "
                        "foil encodes, so ≈equality is the pre-registered expectation"
                        if not vs_foil.get("violated") else
                        "⚠️ the permutation SYSTEMATICALLY beats the foil — investigate the harness"),
        },
    }
    if perm <= best_c:
        out["violations"].append(
            f"⛔ the PERMUTATION arm ({perm:.6f}) is not beaten by the best arm ({best_c:.6f}) — the "
            f"winner's margin does not come from the feature. This is a LEAK or a dead feature.")

    out["ok"] = not out["violations"]
    return out


def dsr_panel(cv: dict, field: list[sbt.ArmSpec], foil: str = "L0_foil") -> dict:
    """Deflated Sharpe reported over BOTH trial fields, with V measured per MH2.1 (a).

    ⭐ **MH2.1 (a): A DIAGNOSTIC ANCHOR IS NEVER A TRIAL.** `SR0 = √V · z(N)` is taxed through the
    trial COUNT `N` *and* the cross-trial Sharpe DISPERSION `V`. Measured on this run the whole-field
    trial-Sharpe series is `[-1.83, 0.06, -0.15, 1.88, 2.61, 1.88, 1.97, 1.74, 2.12, 1.77, 1.94]` —
    the three leading entries are `degenerate_zero`, `degenerate_mean` and `identity_no_translation`,
    i.e. the arms that exist to POLICE the metric, and they inflate `V` **23×** (1.776 vs 0.0785).
    That is exactly MH2.1's finding: the anchor that polices the metric silently SETS the gate's bar.

    ⚠️ **AND THIS IS NOT POST-HOC TRIMMING (the MH2 (a) hazard, which points the other way).** The
    `selectable` flag is set in `build_field` BEFORE any run — the excluded arms were never candidates
    the selection could have chosen, so this is a pre-registered partition, not a family discovered
    after seeing who lost. To keep that verifiable rather than asserted, ALL THREE figures are
    reported and the binding one is named:

      * `whole_field`   — every arm in the trial field. The most conservative reading.
      * `learner_family`— the 8 selectable arms: the search the selection actually ran.
      * `mh2_1`         — **the pre-registered binding figure**: `V` measured over the selectable
                          arms only (the MH2.1 prescription) while `n_trials` stays at the FULL field
                          size, so the multiplicity tax is paid in full and only the dispersion
                          contamination is removed.
    """
    from betting_ml.utils.overfitting import deflated_sharpe

    crps = cv["crps"]
    if foil not in crps.columns:
        return {"available": False, "note": f"no {foil} column — DSR undefined"}
    skill = pd.DataFrame(crps[[foil]].to_numpy(float) - crps.to_numpy(float),
                         index=crps.index, columns=crps.columns)

    def _sr(s: np.ndarray) -> float:
        s = s[np.isfinite(s)]
        return float(np.mean(s) / np.std(s, ddof=1)) if len(s) > 2 and np.std(s, ddof=1) > 0 else 0.0

    learners = [a.label for a in field if a.selectable and a.label in skill.columns]
    whole = [c for c in skill.columns if c != foil]
    out: dict = {"available": True, "binds": "mh2_1"}

    def _one(v_cols: list[str], n_trials: int, tag: str) -> dict | None:
        if not v_cols:
            return None
        best = str(skill[v_cols].mean(axis=0, skipna=True).idxmax())
        series = skill[best].to_numpy(float)
        series = series[np.isfinite(series)]
        if len(series) < 3 or np.std(series) == 0:
            return {"arm": best, "dsr": None, "note": "too few folds / zero variance"}
        ts = [_sr(skill[c].to_numpy(float)) for c in v_cols]
        res = deflated_sharpe(series, n_trials=n_trials, trial_sharpes=ts)
        return {"arm": best, "n_trials": int(n_trials), "v_measured_over": len(v_cols),
                "var_trial_sharpe": round(float(np.var(ts, ddof=1)) if len(ts) > 1 else 0.0, 5),
                "dsr": float(res.dsr), "observed_sr": float(res.observed_sr),
                "sr0": float(res.sr0), "passes": bool(res.dsr >= MIN_DSR),
                "trial_sharpes": [round(t, 3) for t in ts]}

    out["whole_field"] = _one(whole, len(whole), "whole_field")
    out["learner_family"] = _one(learners, len(learners), "learner_family")
    out["mh2_1"] = _one(learners, len(whole), "mh2_1")   # V over learners, N over the full field
    # `numeric_gate` reads the "eligible" key — point it at the pre-registered binding figure.
    out["eligible"] = out["mh2_1"]
    return out


def era_bias(data: pd.DataFrame, folds: list[int]) -> pd.DataFrame:
    """Per-fold BIAS of the era-blind winner beside its era-corrected matched foil.

    ⭐ NF-D15 (g′): a mechanism's stated story has a SIGNATURE, and a level claim's signature is
    BIAS, not accuracy. CRPS can rank the era term last while the era term is still the only thing
    correcting a systematic level error — the two questions are different and both must be reported.
    """
    rows = []
    for year in folds:
        tr = data[data["usable"] & (data["debut_cohort"] < year)]
        te = data[data["usable"] & (data["debut_cohort"] == year)]
        if tr.empty or te.empty:
            continue
        y = te["target"].to_numpy(float)
        rec = {"fold": year, "n": len(te), "realized_mean": float(np.mean(y))}
        for nm, use_era in (("gbm", False), ("gbm_era", True)):
            mu, _ = sbt.GBMProjector(300, 2, 0.03, use_era=use_era).fit(tr).predict(te)
            rec[f"bias_{nm}"] = float(np.mean(mu - y))
        rows.append(rec)
    return pd.DataFrame(rows)


def era_matched_foils(cv: dict, field: list[sbt.ArmSpec]) -> list[dict]:
    """The era family read as PAIRED deltas, never as a leaderboard rank (NF-D10).

    A rank confuses "my feature is inert" with "my feature is in a tie". The paired test asks the
    only question that separates them: does the era-corrected twin SYSTEMATICALLY beat its own
    byte-identical foil across folds?
    """
    crps = cv["crps"]
    out = []
    for spec in field:
        if not spec.pair_with:
            continue
        res = paired_anchor(crps, spec.label, spec.pair_with)
        delta = float(crps[spec.label].mean() - crps[spec.pair_with].mean())
        out.append({"era_arm": spec.label, "matched_foil": spec.pair_with,
                    "mean_crps_delta": round(delta, 6),
                    "era_arm_better": bool(delta < 0), "paired": res})
    return out


def translation_corr(pooled: pd.DataFrame) -> dict:
    """The OOS translation correlation — THE NUMBER THAT BECOMES THE WEIGHT if this ships.

    Pooled over every held-out fold (never in-sample), exactly as E7.3 reports its 0.637/0.491/0.429.
    Spearman is carried beside Pearson because the board consumes a RANK percentile, so rank
    agreement is the property the score actually uses.
    """
    if pooled.empty:
        return {"pearson": None, "spearman": None, "n": 0}
    ok = pooled["y"].notna() & pooled["yhat"].notna()
    p = pooled[ok]
    if len(p) < 3:
        return {"pearson": None, "spearman": None, "n": int(len(p))}
    return {"pearson": round(float(p["y"].corr(p["yhat"])), 4),
            "spearman": round(float(p["y"].corr(p["yhat"], method="spearman")), 4),
            "n": int(len(p)),
            "by_level": {lv: round(float(g["y"].corr(g["yhat"])), 4)
                         for lv, g in p.groupby("level") if len(g) >= 20}}


def classify(cv: dict, lb: pd.DataFrame, defl: dict, dsr: dict, passed: bool,
             metric: str = sbt.PRIMARY_TARGET) -> dict:
    """Name the null's state when the gate does not pass (`cv_power.classify_null`)."""
    from betting_ml.utils.cv_power import classify_null

    sel = lb[lb["selectable"]]
    best = sel.iloc[0]
    foil_crps = float(lb[lb["arm"] == "L0_foil"].iloc[0]["crps"])
    crps = cv["crps"]
    eligible = [a for a in crps.columns if a not in sbt.ANCHOR_ARMS]
    skill = (crps["L0_foil"].to_numpy(float)[:, None] - crps[eligible].to_numpy(float))
    best_i = eligible.index(str(best["arm"]))
    series = skill[:, best_i]
    series = series[np.isfinite(series)]
    sr = float(np.mean(series) / np.std(series, ddof=1)) if len(series) > 2 and np.std(series, ddof=1) > 0 else 0.0
    trial_sr = []
    for j in range(skill.shape[1]):
        s = skill[:, j][np.isfinite(skill[:, j])]
        trial_sr.append(float(np.mean(s) / np.std(s, ddof=1))
                        if len(s) > 2 and np.std(s, ddof=1) > 0 else 0.0)
    v = float(np.var(trial_sr, ddof=1)) if len(trial_sr) > 1 else 1.0

    verdict = classify_null(
        metric=metric, n_folds=len(cv["folds"]), n_arms=len(eligible),
        beats_foil=bool(float(best["crps"]) < foil_crps),
        observed_sr=sr, var_trials_sr=v,
        fold_wins=int(round(float(best["fold_win_rate"]) * len(cv["folds"]))),
    )
    return {"state": verdict.state, "reason": verdict.reason,
            "retest_trigger": verdict.retest_trigger,
            "folds_have": verdict.folds_have, "folds_needed": verdict.folds_needed,
            "detail": verdict.detail, "passed": passed}


# ══════════════════════════════════════════════════════════════════════════════════════
# Orchestration
# ══════════════════════════════════════════════════════════════════════════════════════

def run(pairs: pd.DataFrame, target_form: str = sbt.PRIMARY_TARGET,
        drop_censored: bool = False, min_support: int = 20) -> dict:
    data = sbt.build_target(pairs, target_form)
    if drop_censored:
        # ⚠️ NF1.7 (a): a robustness arm that cannot RUN must not silently become a pass. A pairs
        # file built before `debut_censored` existed would otherwise drop zero rows and report a
        # clean "the artifact does not drive the result" — a check passing on nothing.
        if "debut_censored" not in data.columns:
            raise ValueError(
                "--drop-censored requires the `debut_censored` flag, which this pairs file does not "
                "carry. Rebuild it with `build_sb_pairs`. Refusing to run a robustness arm that "
                "would drop no rows and report a vacuous pass (NF1.7 (a)).")
        before = int(data["usable"].sum())
        data = data[~data["debut_censored"].fillna(False).astype(bool)].copy()
        log.info("dropped left-censored rows: %d → %d usable", before, int(data["usable"].sum()))
    field = sbt.build_field(min_support)
    cv = run_cv(data, field)
    lb = leaderboard(cv, field)
    anchors = read_anchors(cv, lb)

    crps = cv["crps"]
    # PBO over the ELIGIBLE set — the search the selection actually ran (NF1.8). The degenerate
    # ceilings and the no-translation reference were never selectable, so including them would
    # measure the anchors rather than the contest.
    eligible = [a.label for a in field if a.selectable]
    defl = deflation_report(crps, eligible=eligible)
    dsr = dsr_panel(cv, field, foil="L0_foil")

    sel = lb[lb["selectable"]]
    cand = sel.iloc[0]
    foil_crps = float(lb[lb["arm"] == "L0_foil"].iloc[0]["crps"])
    passed, reason = numeric_gate(cand, foil_crps, defl, dsr, mechanism="E8.3 SB translation",
                                  n_folds=len(cv["folds"]))
    # an anchor violation overrides a numeric pass — a gate cleared on an inverted metric is not a pass
    if anchors.get("violations"):
        passed = False
        reason = " ".join(anchors["violations"]) + " || numeric read was: " + str(reason)

    return {
        "target_form": target_form, "drop_censored": drop_censored,
        "n_labelled": cv["n_labelled"], "folds": cv["folds"],
        "leaderboard": lb, "anchors": anchors, "deflation": defl, "dsr": dsr,
        "era_pairs": era_matched_foils(cv, field),
        "era_bias": era_bias(data, cv["folds"]),
        "translation_corr": translation_corr(cv["pooled"]),
        "passed": bool(passed), "gate_reason": reason,
        "null": None if passed else classify(cv, lb, defl, dsr, passed, target_form),
        "cv": cv,
    }


def _fmt(res: dict) -> str:
    lb = res["leaderboard"]
    out = [f"### target `{res['target_form']}`"
           f"{' (left-censored rows DROPPED)' if res['drop_censored'] else ''}",
           f"- labelled rows: **{res['n_labelled']}**, folds: **{len(res['folds'])}** "
           f"({res['folds'][0]}–{res['folds'][-1]})",
           "",
           "| arm | CRPS ↓ | MAE (reported) | fold wins vs foil | % lift | selectable |",
           "|---|---|---|---|---|---|"]
    for _, r in lb.iterrows():
        out.append(f"| `{r['arm']}` | {r['crps']:.6f} | {r['mae_reported']:.6f} | "
                   f"{r['fold_win_rate']:.0%} | {r['pct_lift_vs_foil']:+.2f}% | "
                   f"{'yes' if r['selectable'] else '—'} |")
    a = res["anchors"]
    out += ["", f"**Anchors** (best selectable arm: `{a.get('best_arm')}`) — "
                f"{'✅ all respected' if a.get('ok') else '⛔ VIOLATED'}"]
    for k, v in (a.get("readings") or {}).items():
        out.append(f"- `{k}`: {json.dumps(v, default=str)}")
    for v in a.get("violations") or []:
        out.append(f"- {v}")
    out += ["", f"**Deflation** — PBO(eligible) = {res['deflation'].get('pbo')}, "
                f"contender spread {res['deflation'].get('contender_spread_pct')}%, "
                f"Bailey degradation {res['deflation'].get('os_gap_pct')}%"]
    dsr = res["dsr"] or {}
    out.append(f"- DSR reported over three fields; the pre-registered binding figure is "
               f"`{dsr.get('binds')}` (MH2.1 (a) — V over non-diagnostic arms, N over the full field):")
    for tag in ("whole_field", "learner_family", "mh2_1"):
        d = dsr.get(tag) or {}
        if not d:
            continue
        mark = " ⭐ BINDS" if tag == dsr.get("binds") else ""
        out.append(f"  - `{tag}`{mark}: DSR **{d.get('dsr')}** (SR {d.get('observed_sr'):.4f} vs SR0 "
                   f"{d.get('sr0'):.4f}; n_trials {d.get('n_trials')}, V measured over "
                   f"{d.get('v_measured_over')} arms, Var(trial SR) {d.get('var_trial_sharpe')})")
    wf = dsr.get("whole_field") or {}
    out.append(f"  - trial Sharpes, whole field: {wf.get('trial_sharpes')}")
    out += ["", "**Era matched foils** (NF-D10 — paired, not ranked):"]
    for p in res["era_pairs"]:
        pa = p["paired"]
        out.append(f"- `{p['era_arm']}` vs `{p['matched_foil']}`: ΔCRPS {p['mean_crps_delta']:+.6f} "
                   f"({'era better' if p['era_arm_better'] else 'era WORSE'}), "
                   f"era-arm fold wins {pa.get('challenger_fold_wins')}/{pa.get('n_folds')}, "
                   f"p(era better)={pa.get('p_challenger_better')}")
    eb = res.get("era_bias")
    if eb is not None and not eb.empty:
        out += ["", "**Era BIAS read** (NF-D15 (g′) — a level claim's signature is BIAS, not accuracy):",
                "", "| fold | n | realized mean | bias (era-blind) | bias (era-corrected) |",
                "|---|---|---|---|---|"]
        for _, r in eb.iterrows():
            out.append(f"| {int(r['fold'])} | {int(r['n'])} | {r['realized_mean']:.5f} | "
                       f"{r['bias_gbm']:+.5f} | {r['bias_gbm_era']:+.5f} |")
        post = eb[eb["fold"] >= 2023]
        out.append(f"- pooled bias: era-blind {eb['bias_gbm'].mean():+.5f}, "
                   f"era-corrected {eb['bias_gbm_era'].mean():+.5f}; "
                   f"2023+ folds: {post['bias_gbm'].mean():+.5f} vs {post['bias_gbm_era'].mean():+.5f}")
    tc = res["translation_corr"]
    out += ["", f"**OOS translation correlation** — Pearson **{tc.get('pearson')}**, "
                f"Spearman {tc.get('spearman')} (n={tc.get('n')})",
            f"- by level: {tc.get('by_level')}",
            "", f"**GATE: {'✅ PASS' if res['passed'] else '🟡 NO SHIP'}** — {res['gate_reason']}"]
    if res.get("null"):
        n = res["null"]
        out += ["", f"**Null state: `{n['state']}`** — {n['reason']}",
                f"- re-test trigger: {n.get('retest_trigger')}"]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E8.3 — the stolen-base translation bake-off")
    p.add_argument("--pairs", default=str(ARTIFACTS / "sb_translation_pairs.parquet"))
    p.add_argument("--target-form", default=sbt.PRIMARY_TARGET, choices=tuple(sbt.TARGET_FORMS))
    p.add_argument("--drop-censored", action="store_true",
                   help="robustness arm: exclude the 2015 left-censoring pile-up")
    p.add_argument("--all-forms", action="store_true",
                   help="also run the secondary target-FORM family")
    p.add_argument("--report", default=str(REPORT))
    p.add_argument("--emit", action="store_true",
                   help="emit the per-prospect SB line (only if the gate PASSES)")
    p.add_argument("--s3", action="store_true",
                   help="with --emit, also land the projections at baseball/milb/derived/sb_projections")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    pairs = pd.read_parquet(args.pairs)
    sections = [f"# E8.3 — stolen-base translation bake-off\n",
                f"Cohort: `{args.pairs}` · selector **CRPS** (MAE reported, never selected on).\n"]

    primary = run(pairs, args.target_form, drop_censored=args.drop_censored)
    sections.append("## Primary\n" + _fmt(primary))

    if args.all_forms:
        sections.append("\n## Secondary — target-FORM family")
        for form in sbt.TARGET_FORMS:
            if form == args.target_form:
                continue
            try:
                sections.append(_fmt(run(pairs, form, drop_censored=args.drop_censored)))
            except Exception as e:  # noqa: BLE001
                sections.append(f"### target `{form}` — could not run: {type(e).__name__}: {e}")
        sections.append("\n## Robustness — left-censored rows dropped")
        try:
            sections.append(_fmt(run(pairs, args.target_form, drop_censored=True)))
        except Exception as e:  # noqa: BLE001
            sections.append(f"could not run: {type(e).__name__}: {e}")

    if args.emit:
        # ⛔ A FAILED GATE MUST NOT EMIT. Emitting a line the gate rejected is exactly the
        # "launder a null into a ranking" failure the ship rule exists to prevent — the board would
        # then carry a column no measurement supports.
        if not primary["passed"]:
            log.error("REFUSING to emit: the gate did not pass (%s)", primary["gate_reason"])
            return 2
        winner = str(primary["leaderboard"].query("selectable").iloc[0]["arm"])
        factory = next(a.factory for a in sbt.build_field() if a.label == winner)
        data = sbt.build_target(pairs, args.target_form)
        proj = sbt.emit_projections(data, factory, args.target_form)
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        dest = ARTIFACTS / "sb_projections.parquet"
        proj.to_parquet(dest, index=False)
        log.info("emitted %d SB projections (winner=%s) → %s", len(proj), winner, dest)
        if args.s3:
            from deltalake import write_deltalake
            from scripts.utils.delta_lake import storage_options

            uri = "s3://baseball-betting-ml-artifacts/baseball/milb/derived/sb_projections"
            write_deltalake(uri, proj, mode="overwrite", schema_mode="overwrite",
                            storage_options=storage_options())
            log.info("landed projections at %s", uri)

    text = "\n\n".join(sections) + "\n"
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(text)
    log.info("wrote %s", args.report)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
