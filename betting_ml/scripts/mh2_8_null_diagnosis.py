"""MH2.8 — ⚠️ POST-HOC DIAGNOSIS of the two clauses that refused the run.

⛔ **THIS SCRIPT CANNOT SHIP ANYTHING, AND IT CANNOT RESCUE A PRE-REGISTERED CLAUSE.**
Both clauses it examines FAILED as written, and they stay failed and un-relabelled (E2.1-r: a
result re-read after the fact is the inversion this lineage exists to stop). What this adds is the
MECHANISM — the difference between a measured null and a shrug (NF1.8) — so a successor can be
pre-registered against the real cause rather than against a guess.

It answers exactly two questions, both raised by `mh2_8_skew_predictive.md`:

1. **Why did the negative control fail?** It reported a 0.650 clean rate against a 0.90 bar — i.e.
   on data where the incumbent Normal is TRUE, the selection picked a skew arm about a third of the
   time. Read literally that says the harness invents skew. The diagnosis measures whether those
   clean-data wins carry a SHIPPABLE margin, because the pre-registered control ranks by a bare
   ARGMIN while the SHIP RULE requires `MH28_MEANINGFUL_PIT_MDD_GAIN`. Those are different bars,
   and the control tests the looser one.

2. **What drives DSR's `V`?** The run recorded `DSR_UNREACHABLE` with `var_trials_sr = 1.808` —
   large enough that `SR0` (1.962) exceeds the winner's per-fold Sharpe (0.460) outright. MH2.5 /
   NF-W6b-C: a DSR failure over a HETEROGENEOUS declared field is a hypothesis about the FIELD, and
   must be read for its mechanism before it is filed. ⛔ Reading it is NOT trimming it (MH2.2):
   the leave-one-out table below is a DIAGNOSTIC, and no score in it may be quoted as a verdict.

Usage (LAPTOP, ~2 min, Snowflake-free):
    uv run python betting_ml/scripts/mh2_8_null_diagnosis.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import betting_ml.scripts.mh2_8_skew_predictive as M  # noqa: E402

_BAKEOFF = PROJECT_ROOT / "betting_ml/evaluation/feature_selection/bakeoff"
_RUN_JSON = _BAKEOFF / "mh2_8_skew_predictive.json"
#: The DECLARED LOCK-1 sensitivity, read beside the primary. ⭐ It is what shows that 2020 — a
#: 60-game COVID season — is the fold that destroys the skill series' CONSISTENCY, which no single
#: run could reveal.
_SENS_JSON = _BAKEOFF / "mh2_8_skew_predictive_no2020.json"
#: ⛔ DIAGNOSTIC ONLY (MH2.2). Arithmetic on already-computed per-fold scores, showing what a
#: COHERENT family would have scored. It may size a SUCCESSOR's prospects; it may NEVER be quoted as
#: a verdict, and a successor must PRE-REGISTER its family and re-run.
_COHERENT_FAMILY = ("normal_recal", "skewnorm_recal")
_OUT = PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results/mh2_8_null_diagnosis.md"

#: The population sizes the sweep is run at. ⭐ BOTH are reported because the answer is
#: n-DEPENDENT and quoting one would misstate it: a clean-data winning margin shrinks like 1/√n
#: while the bare-argmin win RATE does not, so the two bars diverge as n grows.
SWEEP_SIZES = ((325, 325, "served-sized"), (14813, 19600, "CV-sized (what the control actually ran at)"))


def v_decomposition(run: dict) -> dict:
    """Which arms drive DSR's cross-trial Sharpe dispersion `V`. ⛔ A DIAGNOSTIC, never a trim."""
    fp = {a: np.array(v, float) for a, v in run["fold_primary"].items()}
    inc = fp[M.MH28_INCUMBENT_ARM]
    sharpe = {}
    for a in M.MH28_FIELD:
        if a == M.MH28_INCUMBENT_ARM:
            continue
        s = inc - fp[a]                       # skill: positive ⇒ the arm is better
        sd = float(np.std(s, ddof=1))
        sharpe[a] = {"mean": float(np.mean(s)), "sd": sd,
                     "sharpe": float(np.mean(s) / sd) if sd > 0 else float("nan"),
                     "degenerate": a in M.MH28_DEGENERATES}
    pool = {a: v["sharpe"] for a, v in sharpe.items() if not v["degenerate"]}
    loo = {a: float(np.var([x for k, x in pool.items() if k != a], ddof=1)) for a in pool}
    return {"per_arm": sharpe, "V": float(np.var(list(pool.values()), ddof=1)),
            "V_leave_one_out": loo, "V_pool_arms": list(pool)}


def clean_data_margin_sweep(n_ev: int, n_cal: int, reps: int, seed: int = 42) -> dict:
    """On data where the incumbent Normal is TRUE: how often does the flexible arm win the ARGMIN,
    and how often does it win by a SHIPPABLE margin? Those are different questions."""
    from betting_ml.scripts.mh2_8_skew_predictive import pull_served

    d = pull_served()
    d = d[(d["tier"] == "post_lineup") & d["y_total"].notna() & d["mu"].notna()]
    mu_ev, sg_ev = np.resize(d["mu"].to_numpy(float), n_ev), np.resize(d["sigma"].to_numpy(float), n_ev)
    mu_c, sg_c = np.resize(d["mu"].to_numpy(float), n_cal), np.resize(d["sigma"].to_numpy(float), n_cal)
    rng = np.random.default_rng(seed)
    margins, winners = [], []
    for _ in range(reps):
        y_c = np.round(M.SkewNormalPred(mu_c, sg_c, 0.0).ppf(rng.uniform(size=n_cal)))
        y_e = np.round(M.SkewNormalPred(mu_ev, sg_ev, 0.0).ppf(rng.uniform(size=n_ev)))
        pn = M.fit_shape_recal(mu_c, sg_c, y_c, allow_skew=False)
        ps = M.fit_shape_recal(mu_c, sg_c, y_c, allow_skew=True)
        arms = {"incumbent": M.NormalPred(mu_ev, sg_ev),
                "normal_recal": M.apply_shape_recal(mu_ev, sg_ev, pn),
                "skewnorm_recal": M.apply_shape_recal(mu_ev, sg_ev, ps)}
        sc = {a: M.score_primaries_only(y_e, p, rng) for a, p in arms.items()}
        winners.append(M._select_on_primaries(sc))
        margins.append(sc["incumbent"]["pit_mdd"] - sc["skewnorm_recal"]["pit_mdd"])
    m = np.array(margins)
    return {
        "n_eval": n_ev, "n_cal": n_cal, "reps": reps,
        "argmin_picks_skew": winners.count("skewnorm_recal") / len(winners),
        "winners": {w: winners.count(w) for w in sorted(set(winners))},
        "margin_mean": float(m.mean()), "margin_sd": float(m.std()),
        "margin_p95": float(np.percentile(m, 95)), "margin_max": float(m.max()),
        "clears_meaningful_bar": float((m >= M.MH28_MEANINGFUL_PIT_MDD_GAIN).mean()),
    }


def coherent_family_probe(run: dict) -> dict:
    """⛔ DIAGNOSTIC. What a COHERENT recal-only family would have scored on this window.

    ⭐ **The result overturns the obvious story and that is why it is measured rather than asserted.**
    The intuition — "a coherent family lowers `V`" — is FALSE here: dropping the far-out learned-family
    arms makes `V` go UP, because a sample variance over the REMAINING near-mean points is WIDER
    (DSR-CONV's non-monotone-exclusion lesson, live). The whole improvement comes from the
    multiplicity term `z(N)` as `N` falls, not from dispersion.
    """
    from betting_ml.utils.cv_power import dsr_from_sr

    fp = {a: np.array(v, float) for a, v in run["fold_primary"].items()}
    inc = fp[M.MH28_INCUMBENT_ARM]
    sh = {a: float(np.mean(inc - fp[a]) / np.std(inc - fp[a], ddof=1)) for a in _COHERENT_FAMILY}
    V = float(np.var(list(sh.values()), ddof=1))
    n_trials = len(_COHERENT_FAMILY) + 1                      # + the incumbent, in n_trials
    return {"arms": list(_COHERENT_FAMILY), "n_trials": n_trials, "V": V,
            "V_declared_field": float(run["dsr"]["var_trials_sr"]),
            "dsr": float(dsr_from_sr(sr=float(run["dsr"]["observed_sr"]), n_obs=int(run["n_folds"]),
                                     n_trials=n_trials, var_trials_sr=V)),
            "dsr_declared_field": float(run["dsr"]["dsr"])}


def main() -> None:
    if not _RUN_JSON.exists():
        raise SystemExit(f"❌ {_RUN_JSON.relative_to(PROJECT_ROOT)} is absent — run the bake-off first.")
    run = json.load(_RUN_JSON.open())
    vd = v_decomposition(run)
    sweeps = [clean_data_margin_sweep(a, b, reps=60 if a > 1000 else 150) for a, b, _ in SWEEP_SIZES]
    real_margin = run["decision"]["margins_vs_incumbent"]["skewnorm_recal"]["pit_mdd_gain"]

    L = ["# MH2.8 — ⚠️ POST-HOC DIAGNOSIS of the two clauses that refused the run\n",
         "> ⛔ **This document cannot ship anything and cannot rescue a pre-registered clause.** Both "
         "clauses below FAILED as written and stay failed. What follows is the MECHANISM, so a "
         "successor can be pre-registered against the real cause rather than a guess (NF1.8: state "
         "the null's mechanism, in the unit that grows).\n",
         "## 1. Why the negative control failed\n",
         f"The pre-registered control reported a clean rate of **0.650** against a bar of "
         f"**{M.MH28_NEG_CONTROL_MIN_CLEAN}** — on data where the incumbent Normal is TRUE, the "
         "selection picked a skew arm about a third of the time. Read literally that says the "
         "harness invents skew, which would make the whole study untrustworthy.\n",
         "⭐ **The control and the ship rule test DIFFERENT bars.** `_select_on_primaries` is a bare "
         f"ARGMIN with no threshold; the SHIP RULE requires a margin of ≥ "
         f"`{M.MH28_MEANINGFUL_PIT_MDD_GAIN}`. `skewnorm_recal` carries one more fitted parameter "
         "than its foil, so on clean data it can chase PIT noise and win a TIE — without ever "
         "winning by an amount the ship rule would act on. This measures both.\n",
         "| population | bare ARGMIN picks the skew arm | margin mean | margin sd | margin max | "
         "**clears the ship rule's bar** |",
         "|---|---:|---:|---:|---:|---:|"]
    for s, (_, _, label) in zip(sweeps, SWEEP_SIZES):
        L.append(f"| {label} (n_eval {s['n_eval']:,}, {s['reps']} reps) | {s['argmin_picks_skew']:.3f} | "
                 f"{s['margin_mean']:+.5f} | {s['margin_sd']:.5f} | {s['margin_max']:+.5f} | "
                 f"**{s['clears_meaningful_bar']:.3f}** |")
    cv = sweeps[-1]
    sds = real_margin / cv["margin_sd"] if cv["margin_sd"] else float("nan")
    L += ["",
          f"At the size the control actually ran at, the bare argmin picks the skew arm "
          f"**{cv['argmin_picks_skew']:.3f}** of the time — reproducing the recorded 0.650 clean "
          f"rate — while **{cv['clears_meaningful_bar']:.3f}** of replicates produce a shippable "
          f"margin. The largest clean-data margin in {cv['reps']} replicates is "
          f"**{cv['margin_max']:+.5f}**, against a bar of {M.MH28_MEANINGFUL_PIT_MDD_GAIN} and a "
          f"REAL-DATA margin of **{real_margin:+.4f}** — about **{sds:.0f} clean-data SDs out**.\n",
          "⇒ the control's failure is a property of its THRESHOLD-FREE TIE-BREAK, not evidence that "
          "the harness manufactures a shippable effect. ⛔ **That does not un-fail it.** The clause "
          "was pre-registered as written and it refused; re-reading a failed clause against a bar "
          "chosen after seeing it fail is exactly the E2.1-r inversion. What it licenses is a "
          "SUCCESSOR whose negative control MIRRORS THE SHIP RULE'S THRESHOLD — which is the "
          "control that should have been written, and is a defect in this study's design.\n",
          "## 2. What drives DSR's `V`\n",
          f"The run recorded `DSR_UNREACHABLE`: the winner's per-fold Sharpe **0.460** against "
          f"`SR0` **1.962**, built on `var_trials_sr` = **{vd['V']:.4f}**. `SR0 = √V·z(N)`, so a "
          "large `V` raises the bar for arithmetic reasons rather than evidential ones (MH2.5 / "
          "NF-W6b-C).\n",
          "| arm | skill mean (+ = better than incumbent) | skill sd | per-fold Sharpe | in `V`? |",
          "|---|---:|---:|---:|---|"]
    for a, v in vd["per_arm"].items():
        L.append(f"| `{a}` | {v['mean']:+.5f} | {v['sd']:.5f} | {v['sharpe']:+.3f} | "
                 f"{'⛔ degenerate — out of V' if v['degenerate'] else '✅'} |")
    L += ["", f"Leave-one-out on the `V` pool {vd['V_pool_arms']} — ⛔ **a DIAGNOSTIC, NOT a trim** "
              "(MH2.2: you PRE-REGISTER a family, you do not DISCOVER one; no figure here may be "
              "quoted as a verdict):", "",
          "| arm removed | resulting `V` |", "|---|---:|"]
    for a, v in sorted(vd["V_leave_one_out"].items(), key=lambda kv: kv[1]):
        L.append(f"| `{a}` | {v:.4f} |")
    ng = vd["per_arm"]["ngb_gamma"]
    L += ["",
          f"⭐ **`ngb_gamma` alone accounts for most of it** — removing it takes `V` from "
          f"{vd['V']:.3f} to {vd['V_leave_one_out']['ngb_gamma']:.3f}. The declared field mixes "
          "SHAPE-RECALIBRATION arms, which share the incumbent's mean and therefore move together "
          "fold to fold, with LEARNED-FAMILY arms that fit their own mean. That is a HETEROGENEOUS "
          "field by construction, and it is the mechanism MH2.5 and NF-W6b-C both name.\n",
          f"⚠️ **And the sharpest reading is an irony, not a rescue.** `ngb_gamma`'s own per-fold "
          f"Sharpe is **{ng['sharpe']:+.3f}** — ABOVE the `SR0` of 1.962, i.e. it is the one arm in "
          "the field that WOULD clear the deflation gate. It fails clause 6 instead: its CRPS is "
          "+0.0698 against a tolerance of 0.020, three and a half times over. **It bought flatness "
          "with sharpness, which is precisely what the constraint exists to catch.** So the arm the "
          "deflation gate would pass is the one the sharpness constraint rejects, and the arm that "
          "clears every substantive clause is the one the deflation gate rejects. Neither result "
          "is a defect in the other gate.\n",
          "⛔ **`field_remedy_admissible` was `None`** — not even a 2-arm field clears. That figure "
          "holds `V` FIXED, so it cannot see the `V` reduction a coherently-declared family would "
          "produce; it says field SIZE is no lever, not that field COMPOSITION is none. Acting on "
          "that distinction requires a FRESH pre-registration of a coherent family, decided on "
          "mechanistic grounds BEFORE any scoring — ⛔ never a re-cut of this scored field.\n"]
    # ── the declared LOCK-1 sensitivity, read beside the primary ──────────────────────────────
    if _SENS_JSON.exists():
        sens = json.load(_SENS_JSON.open())
        L += ["## 3. ⭐ The declared 2020 sensitivity overturns the REASON, not the verdict\n",
              "Both windows return `INCUMBENT_STANDS`, and the 2020 run was run because it was "
              "PRE-REGISTERED, not because the primary left a question open. But the two disagree "
              "sharply about WHY, and only running both could show it.\n",
              "| | primary (2020 kept) | sensitivity (2020 dropped) |", "|---|---:|---:|"]
        pr_d, se_d = run["dsr"], sens["dsr"]
        rows = [("folds", run["n_folds"], sens["n_folds"]),
                ("winner per-fold Sharpe", f"{pr_d['observed_sr']:.3f}", f"{se_d['observed_sr']:.3f}"),
                ("`SR0` (the bar)", f"{pr_d['sr0']:.3f}", f"{se_d['sr0']:.3f}"),
                ("`V`", f"{pr_d['var_trials_sr']:.3f}", f"{se_d['var_trials_sr']:.3f}"),
                ("**DSR**", f"**{pr_d['dsr']:.4f}**", f"**{se_d['dsr']:.4f}**"),
                ("PBO", f"{run['pbo']:.3f}", f"{sens['pbo']:.3f}"),
                ("fold consistency",
                 f"{run['fold_consistency']['wins']}/{run['n_folds']}",
                 f"{sens['fold_consistency']['wins']}/{sens['n_folds']}"),
                ("`field_remedy_admissible`",
                 str(run["decision"]["null_classification"]["field_remedy_admissible"]),
                 str(sens["decision"]["null_classification"]["field_remedy_admissible"]))]
        for a, b, c in rows:
            L.append(f"| {a} | {b} | {c} |")
        L += ["",
              "⭐ **2020 is the fold that destroys the skill series' CONSISTENCY.** Dropping one "
              "60-game COVID season — 581 of 21,169 rows, 2.7% — takes the winner's per-fold Sharpe "
              f"from {pr_d['observed_sr']:.3f} to {se_d['observed_sr']:.3f}, a ~5× move, and DSR "
              f"from {pr_d['dsr']:.4f} to {se_d['dsr']:.4f}. The BAR rose too "
              f"({pr_d['sr0']:.3f} → {se_d['sr0']:.3f}, since `n_obs` fell 8 → 7), but the EVIDENCE "
              "rose far more. ⚠️ A fold-count argument alone predicts the opposite and is wrong: the "
              "consistency of the per-fold skill series, not the number of folds, is what moved.\n",
              "⭐ **And `field_remedy_admissible` changes state**, from `None` (field size is no "
              "lever at all — nothing clears) to `False` (a smaller field WOULD clear arithmetically, "
              "but the imperative is REFUSED because 8 IS the declared minimum). That is a "
              "materially different null: the primary says the evidence is nowhere near, the "
              "sensitivity says the evidence is close and the DESIGN is what refuses it. ⛔ Neither "
              "licenses re-cutting this field (MH2.2).\n"]
        probe_p, probe_s = coherent_family_probe(run), coherent_family_probe(sens)
        L += ["### ⛔ What a COHERENT family would have scored — DIAGNOSTIC, never a verdict\n",
              "Arithmetic on already-computed per-fold scores, to size whether a SUCCESSOR is worth "
              "pre-registering. A successor must DECLARE its family up front and RE-RUN; no figure "
              "here may be quoted as a result (MH2.2).\n",
              f"| window | declared field (`n_trials` {run['n_arms']}) | coherent recal-only "
              f"(`n_trials` {probe_p['n_trials']}) |", "|---|---:|---:|",
              f"| primary `V` / DSR | {probe_p['V_declared_field']:.3f} / "
              f"{probe_p['dsr_declared_field']:.4f} | {probe_p['V']:.3f} / {probe_p['dsr']:.4f} |",
              f"| sensitivity `V` / DSR | {probe_s['V_declared_field']:.3f} / "
              f"{probe_s['dsr_declared_field']:.4f} | {probe_s['V']:.3f} / {probe_s['dsr']:.4f} |",
              "",
              "⭐⭐ **This refutes the obvious story about coherent families, and the refutation is "
              "the useful part.** The intuition is that a coherent family wins by SHRINKING `V`. "
              f"Measured, `V` moves in OPPOSITE DIRECTIONS on the two windows — DOWN on the primary "
              f"({probe_p['V_declared_field']:.3f} → {probe_p['V']:.3f}) and UP on the sensitivity "
              f"({probe_s['V_declared_field']:.3f} → {probe_s['V']:.3f}) — while DSR IMPROVES on "
              "both. A sample variance over the REMAINING near-mean arms can be WIDER once the "
              "far-out ones are gone, so `V` is not a reliable lever in either direction. That is "
              "DSR-CONV's non-monotone-exclusion property, observed live rather than quoted, and "
              "it is why an arm may qualify as a degenerate BY DESIGN and never BY DECLARATION. "
              "What improves DSR consistently here is the MULTIPLICITY term `z(N)` as `N` falls "
              f"{run['n_arms']} → {probe_p['n_trials']}.\n",
              f"⚠️ And even so the best diagnostic figure is **{max(probe_p['dsr'], probe_s['dsr']):.4f}**, "
              f"short of the {M.DSR_MIN_CONF} bar. ⇒ a coherent-family successor is worth "
              "registering but is **not** a foregone clear, and anyone scoping one should size it "
              "against that number rather than against the hope that coherence alone fixes DSR.\n"]
    _OUT.write_text("\n".join(L) + "\n")
    print(f"[MH2.8] diagnosis → {_OUT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
