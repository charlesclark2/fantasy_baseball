"""NF-W7k — is QB's `dsr_ok` refusal reachable by a LOWER-VARIANCE design? (the CHEAP GATE)

NF-W7j left QB refused on `dsr_ok` ALONE, `DSR_UNREACHABLE`, with one lever named: a
lower-variance design. NF-W7f had already closed the other two (more folds — `n` enters DSR only
through `√(n−1)`; a coherent narrower field — `V` falls 8.8× and DSR still reaches 0.174).

⭐ THE GATE RUNS FIRST AND GATES THE EXPENSIVE RUN — it does not follow it (NF-W7h's FU1). Phase A
re-scores the SAME 8 folds and the SAME 6 eligible labels at 5 draw SEEDS and 2 draw COUNTS,
holding EVERYTHING else byte-identical, and asks the exact question at a fraction of the cost:
with ALL Monte-Carlo error removed — a CEILING no draw count can beat — does the winner's deflated
Sharpe reach the bar? A ceiling below the bar closes the lever outright.

⛔ NOT a claim it will clear. ⛔ The certification bar is UNCHANGED (`DSR_MIN = 0.95`), the field is
UNCHANGED (no trim — MH2.2), the folds are UNCHANGED. Nothing here can certify QB: `FUND` funds a
MEASUREMENT whose full gate would still have to hold.

Run (LAPTOP):
    uv run python quant_sports_intel_models/football/nfl/fantasy/run_nf_w7k_mc_variance.py
    ... --smoke            # path proof: one fold, tiny draws, 2 seeds
    ... --rewrite-report   # re-derive every verdict from the stored scores, at ZERO refit (NF-W2e)
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils import cv_power  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import fp_mc_variance as MV  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_w7f_qb_marginal as W7F,
)

log = logging.getLogger("nf_w7k")

QM, FA, KW, WP, LP = W7F.QM, W7F.FA, W7F.KW, W7F.WP, W7F.LP
POSITION = "QB"
_ARTIFACT_REL = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                 "nf_w7k_mc_variance.json")
_W7F_RECORD_REL = ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                   "nf_w7f_qb_marginal.json")

#: the 6 labels the DSR field is built from — the 4 declared arms and the 2 contest foils.
#: ⛔ NOT a re-cut field: `dsr_ok` reads exactly these, so scoring exactly these re-measures the
#: gate as NF-W7f computed it. The oracle / matched-n / degenerate contexts do not enter DSR and
#: are deliberately not re-drawn — re-scoring them would cost 4× for labels the clause never reads.
SCORED_LABELS: tuple[str, ...] = tuple(QM.ELIGIBLE)


# ── The NF-W7f object, read from its committed record (never a constant) ─────────────────────────
def w7f_record() -> dict:
    """NF-W7f's committed scores. ⛔ READ, never hard-coded: the reproduction pin exists to prove
    this story measures the object NF-W7f scored, and a pin against a constant could not notice
    that the predecessor's record had been regenerated (the NF1.9-R `served_*`-column lesson)."""
    p = _PROJECT_ROOT / _W7F_RECORD_REL
    if not p.exists():
        raise FileNotFoundError(f"{p} is absent — NF-W7f's stored fold scores are the object this "
                                f"story pins against, so without them the reproduction pin is "
                                f"UNEVALUABLE and can never be scored as passing (NF1.7 (a))")
    rec = json.loads(p.read_text())
    if rec.get("story") != QM.STORY or rec.get("smoke"):
        raise ValueError(f"{p.name} is story {rec.get('story')} / smoke={rec.get('smoke')} — a "
                         f"path proof is not the pinned object; REFUSED")
    return rec


def w7f_scores() -> dict[str, dict[str, float]]:
    """{fold: {label: CRPS}} for the gate position, from NF-W7f's record."""
    out: dict[str, dict[str, float]] = {}
    for fr in w7f_record()["fold_results"]:
        pos = fr["positions"].get(POSITION) or {}
        if "scores" in pos:
            out[fr["label"]] = dict(pos["scores"])
    return out


# ── One fold: the seed-INDEPENDENT setup, then the per-(draws, seed) assemblies ──────────────────
def fold_setup(fold, feat, smap, matrix_key: str, rebuild_banks: bool = False) -> dict:
    """The per-fold, seed-independent context: marginals, Σ, π̂, and every arm's spliced banks."""
    train, test = feat.loc[fold.train_idx], feat.loc[fold.test_idx]
    cfg = LP.get_preset(W7F.GATE_LEAGUE)
    FA.assert_assembly_is_priceable(cfg, POSITION)
    weights = FA.leg_weights(cfg, POSITION)
    t0 = time.time()
    ctx_te, cache_state = W7F._marginals_cached(fold.label, train, test, smap,
                                                matrix_key=matrix_key, rebuild=rebuild_banks)
    log.info("[W7k] fold %s marginals in %.1fs (cache %s)", fold.label, time.time() - t0,
             cache_state)

    tr_p = train.loc[train["position"].astype(str) == POSITION].reset_index(drop=True)
    te_p = test.loc[test["position"].astype(str) == POSITION].reset_index(drop=True)
    if len(te_p) == 0 or len(tr_p) < QM.MIN_ESTIMATION_ROWS:
        raise ValueError(f"fold {fold.label}: train {len(tr_p)} / test {len(te_p)} {POSITION} rows "
                         f"is below the estimation floor ({QM.MIN_ESTIMATION_ROWS}). NF-W7f scored "
                         f"ALL 8 folds here, so a fold that will not score means this run is not "
                         f"looking at NF-W7f's object — REFUSED rather than silently skipped")

    b_te = W7F.bank_tensor(ctx_te, POSITION, len(te_p))
    raw_tr, raw_te = W7F.realized_matrix(tr_p), W7F.realized_matrix(te_p)
    y_te = FA.score_realized(raw_te, weights)
    sig_all, _note = QM.sigma_all(raw_tr)
    pi = QM.pi_for_arm(QM.PI_ESTIMATOR, tr_p, te_p, W7F.FEATURES, train_raw=raw_tr)
    cond, marg = QM.conditional_zero_rate(raw_tr), QM.marginal_zero_rate(raw_tr)

    spliced: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for arm in QM.REAL_ARMS:
        t = QM.zero_targets(arm, banks=b_te, pi_hat=pi, cond_rate=cond, marg_rate=marg)
        recal = QM.resplice_zero_mass(b_te, t)
        pi_used, _ = QM.clamp_pi(pi, recal)
        spliced[arm] = (recal, pi_used)
    pi_served_used, _ = QM.clamp_pi(pi, b_te)
    return {"label": fold.label, "b_te": b_te, "y_te": y_te, "weights": weights,
            "sig_all": sig_all, "spliced": spliced, "pi_served_used": pi_served_used,
            "n_test": int(len(te_p)), "n_train": int(len(tr_p)), "bank_cache": cache_state}


def score_at(setup: dict, *, draws: int, seed: int) -> dict[str, float]:
    """The 6 eligible labels' mean CRPS for one fold at one (draws, seed).

    ⭐ Common random numbers are preserved WITHIN a (fold, draws, seed): every label transforms the
    same base normals, exactly as NF-W7f does. That is what makes the across-seed spread of a
    DELTA the Monte-Carlo error of the PAIRED quantity the gate actually reads — rather than the
    much larger, and irrelevant, Monte-Carlo error of either score on its own."""
    w, corr, y = setup["weights"], setup["sig_all"], setup["y_te"]
    banks: dict[str, np.ndarray] = {}
    for arm, (recal, pi_used) in setup["spliced"].items():
        banks[arm] = QM.assemble_mixture_bank(recal, w, pi=pi_used, corr=corr, draws=draws,
                                              seed=seed)
    banks["mixall_learned"] = QM.assemble_mixture_bank(setup["b_te"], w,
                                                      pi=setup["pi_served_used"], corr=corr,
                                                      draws=draws, seed=seed)
    banks["single_copula"] = FA.assemble_fp_bank(setup["b_te"], w, corr=corr, draws=draws,
                                                 seed=seed)
    missing = sorted(set(SCORED_LABELS) - set(banks))
    if missing:
        raise ValueError(f"{missing} produced no predictive — a field scored with a label silently "
                         f"missing is not the declared field (NF1.7 (a))")
    out: dict[str, float] = {}
    for label in SCORED_LABELS:
        KW.assert_finite_predictive(banks[label], f"{POSITION}/{label}")
        out[label] = float(np.mean(KW.crps_dense(banks[label], y)))
    return out


# ── The verdict layer (derived from stored scores — NF-W2e: correcting it costs zero refit) ──────
def _delta_table(scores: dict, level: str, foil: str) -> dict[str, dict[str, list[float]]]:
    """{arm: {fold: [δ at each seed]}} at one draw level, δ = CRPS(foil) − CRPS(arm)."""
    out: dict[str, dict[str, list[float]]] = {}
    for arm in QM.REAL_ARMS:
        out[arm] = {}
        for fold, by_seed in scores[level].items():
            seeds = sorted(by_seed, key=int)
            out[arm][fold] = [by_seed[s][foil] - by_seed[s][arm] for s in seeds]
    return out


def derive_verdict_layer(out: dict) -> dict:
    scores = out["scores"]
    primary, control = str(out["draws_primary"]), str(out["draws_control"])
    base_seed = str(out["base_seed"])
    folds = sorted(scores[primary])

    # ── G0 reproduction pin ─────────────────────────────────────────────────────────────────────
    stored = w7f_scores()
    gaps: dict[str, dict[str, float]] = {}
    for f in folds:
        if f not in stored:
            continue
        mine = scores[primary][f].get(base_seed, {})
        gaps[f] = {lab: abs(mine[lab] - stored[f][lab])
                   for lab in SCORED_LABELS if lab in mine and lab in stored[f]}
    flat = [g for d in gaps.values() for g in d.values()]
    repro = {
        "evaluable": bool(flat),
        "n_compared": len(flat),
        "max_abs_gap": max(flat) if flat else None,
        "tolerance": MV._REPRO_TOL,
        "reproduces": bool(flat) and max(flat) <= MV._REPRO_TOL,
        "per_fold_max_gap": {f: (max(d.values()) if d else None) for f, d in gaps.items()},
    }

    # ── G1 the seed is live (a dead seed reports ZERO MC error = the FALSE-STOP direction) ──────
    zero_spread = []
    for lvl in (primary, control):
        for f, by_seed in scores[lvl].items():
            for lab in SCORED_LABELS:
                vals = [by_seed[s][lab] for s in sorted(by_seed, key=int)]
                if float(np.std(np.asarray(vals, dtype=float), ddof=1)) <= 0.0:
                    zero_spread.append(f"{lvl}/{f}/{lab}")
    seed_live = {"holds": not zero_spread, "zero_spread_cells": zero_spread,
                 "n_seeds": len(scores[primary][folds[0]])}

    # ⛔ G0 AND G1 RAISE — they do not merely get recorded. The pre-registration calls both
    # "RAISE", and a validity clause that only writes a field into the artifact is decorative: the
    # run would go on to publish a decision derived from an object it had just failed to
    # authenticate (the E11.30 "detected, nobody notified" class, one level over). A path proof
    # is exempt because it deliberately scores at different draw counts than NF-W7f did, so its
    # reproduction pin cannot hold by construction — and an exemption that silently covered a REAL
    # run would be the more dangerous half, so it is keyed on the artifact's own `smoke` flag.
    if not out.get("smoke"):
        if not repro["reproduces"]:
            raise ValueError(
                f"G0 FAILED — the base-seed re-score does not reproduce NF-W7f's stored scores "
                f"(max abs gap {repro['max_abs_gap']} over {repro['n_compared']} cells, tolerance "
                f"{repro['tolerance']}). Every number below would describe a RE-DERIVATION rather "
                f"than the object NF-W7f scored, so the run REFUSES rather than publishing a "
                f"decision about the wrong object (prereg §3 G0).")
        if not seed_live["holds"]:
            raise ValueError(
                f"G1 FAILED — {len(seed_live['zero_spread_cells'])} (fold, label) cells show ZERO "
                f"across-seed spread, e.g. {seed_live['zero_spread_cells'][:3]}. A seed that does "
                f"not reach the draws reports zero Monte-Carlo error, which would close QB's last "
                f"lever on a measurement that never happened — the FALSE-STOP direction. REFUSED "
                f"(prereg §3 G1).")

    # ── the field, exactly as `select_position` builds it ───────────────────────────────────────
    mean_by_label = {lab: float(np.mean([np.mean([scores[primary][f][s][lab]
                                                  for s in scores[primary][f]]) for f in folds]))
                     for lab in SCORED_LABELS}
    winner = min(QM.REAL_ARMS, key=lambda a: mean_by_label[a])
    foil = min(QM.CONTEST_FOILS, key=lambda a: mean_by_label[a])

    d_primary = _delta_table(scores, primary, foil)
    d_control = _delta_table(scores, control, foil)
    dec_primary = {a: MV.decompose(d_primary[a]) for a in QM.REAL_ARMS}
    dec_control = {a: MV.decompose(d_control[a]) for a in QM.REAL_ARMS}

    # ── G2 the 1/D law, MEASURED on the winner's delta ──────────────────────────────────────────
    scaling = MV.scaling_check(dec_control[winner]["mc_var"], out["draws_control"],
                               dec_primary[winner]["mc_var"], out["draws_primary"])
    scaling_all = {a: MV.scaling_check(dec_control[a]["mc_var"], out["draws_control"],
                                       dec_primary[a]["mc_var"], out["draws_primary"])
                   for a in QM.REAL_ARMS}

    # ── the projection, anchored on NF-W7f's OWN base-seed series ───────────────────────────────
    base = {a: np.asarray([scores[primary][f][base_seed][foil] - scores[primary][f][base_seed][a]
                           for f in folds], dtype=float) for a in QM.REAL_ARMS}
    ceiling = MV.ceiling_report(base, dec_primary, winner, draws_primary=out["draws_primary"])
    # a SENSITIVITY on NF-W7f's published series, not a measurement: how much Monte-Carlo error
    # would the run have to FIND for the ceiling to clear? Computed under a stated assumption
    # (one common absolute σ_MC) and reported beside the measured share, never instead of it.
    required = MV.required_mc_share_for_ceiling(base, winner, QM.DSR_MIN)
    ci = MV.bootstrap_ceiling_dsr(d_primary, winner)
    decision = MV.decide(scaling, ceiling["ceiling"]["dsr"], ci, ceiling["rungs"], QM.DSR_MIN,
                         ceiling_unbounded=bool(ceiling["ceiling"].get("unbounded")))

    # ── the null state, from the shared instrument (declared field size, never discovered) ──────
    # ⛔ the OBSERVED row, not a projected one: `classify_null` must describe the null NF-W7f
    # actually recorded. Feeding it a projected series would ask the instrument to classify a
    # hypothetical, and its verdict would then read as a statement about evidence that does not
    # exist. The projection's own reading is the DECISION above, kept separate.
    obs = ceiling["rungs"][0]
    obs_srs = np.asarray(sorted(obs["trial_sharpes"].values()), dtype=float)
    nv = cv_power.classify_null(
        metric=f"nf_w7k_mc_variance|{POSITION}", n_folds=len(folds),
        n_arms=len(QM.REAL_ARMS), beats_foil=bool(base[winner].mean() > 0),
        observed_sr=float(obs["winner_sharpe"]),
        var_trials_sr=float(np.var(obs_srs, ddof=1)),
        fold_wins=int((base[winner] > 0).sum()),
        p_one_sided=obs["p_one_sided"], bh_cutoff=QM.FDR_Q,
        degenerates_excluded_from_v=True,
        declared_field_size=len(QM.REAL_ARMS),
    )
    null = KW.flag_unsafe_field_shrink(
        {"state": nv.state, "reason": nv.reason, "retest_trigger": nv.retest_trigger,
         "field_remedy_admissible": getattr(nv, "field_remedy_admissible", None),
         "declared_field_size_source": ("fp_qb_marginal_calibration.REAL_ARMS, committed in "
                                        "ablation_results/nf_w7f_preregistration.md §3 before "
                                        "any score"),
         "instrument_verdict": {"state": nv.state, "reason": nv.reason,
                                "retest_trigger": nv.retest_trigger}},
        len(QM.REAL_ARMS))

    out["verdict"] = {
        "story_verdict": decision["verdict"],
        "certified_for_nf_w8": False,
        "decision": decision,
        "winner": winner, "best_foil": foil,
        "mean_crps_by_label": mean_by_label,
        "checks": {
            "G0_reproduction_pin": repro,
            "G1_seed_is_live": seed_live,
            "G2_mc_variance_scales_as_one_over_draws": scaling,
            "G2_by_arm": scaling_all,
            "G3_ceiling_ci": ci,
        },
        "required_mc_share_sensitivity": required,
        "decomposition_primary": dec_primary,
        "decomposition_control": dec_control,
        "ceiling": ceiling,
        "base_seed_deltas": {a: [float(x) for x in v] for a, v in base.items()},
        "null_state": null,
        "dsr_min": QM.DSR_MIN,
        "promote_blockers": [
            "NF-W7k decides whether an expensive re-measurement is FUNDED. It certifies nothing, "
            "re-scores no other clause and does not re-open NF-W7f's or NF-W7j's verdicts",
            "the certification bar is UNCHANGED — the full NF-W7f gate including `dsr_ok` stands "
            "(E2.1-r); WR and TE cleared it and RB was held to it",
            "the field is UNCHANGED — no arm was trimmed after scoring (MH2.2)",
            "⛔ QB ONLY. Nothing here certifies RB / WR / TE, and NF-W7c §4's rule still binds: a "
            "per-position-certified distribution may not feed a CROSS-POSITION ranking",
            "NF-W7f's and NF-W7j's promote blockers are inherited in full",
        ],
    }
    return out


# ── Report ──────────────────────────────────────────────────────────────────────────────────────
def _f(x, n=4):
    return "—" if x is None else (f"{x:.{n}f}" if isinstance(x, float) else str(x))


def _share(x):
    """Render an MC share, flagging the >1 case for what it is.

    A share above 1 is not "149% of the variance" — it is the arithmetic shadow of a NEGATIVE
    heterogeneity estimate (`mc / (het + mc)` with `het < 0`). The raw number is kept, because
    clamping it would hide exactly the reading that says the fold spread is no larger than draw
    noise, but it is marked so a reader cannot take it for a proportion."""
    if x is None:
        return "—"
    return f"{x:.4f}" + (" ⚠️ >1 ⇒ σ²_het < 0" if x > 1.0 else "")


def write_report(out: dict, path: Path) -> None:
    v = out["verdict"]
    d, c = v["decision"], v["checks"]
    w, foil = v["winner"], v["best_foil"]
    L = [f"# NF-W7k — is QB's `dsr_ok` refusal reachable by a LOWER-VARIANCE design?", "",
         f"Generated {out['generated_at']} · position **{POSITION}** · {out['n_folds']} folds · "
         f"{out['n_seeds']} draw seeds × draw counts "
         f"{out['draws_primary']:,} and {out['draws_control']:,} · "
         f"winner `{w}` vs best contest foil `{foil}`", "",
         "⚖️ `best_alpha = 0` · **DEPLOY-HELD** · research-only. ⛔ This story decides whether an "
         "expensive re-measurement is FUNDED — it certifies nothing and re-scores no other clause. "
         "The bar is UNCHANGED (`DSR_MIN` "
         f"{v['dsr_min']}), the field is UNCHANGED (no trim — MH2.2), the folds are UNCHANGED.", "",
         f"## Verdict: **`{d['verdict']}`** · Phase B funded: **{'YES' if d['fund_phase_b'] else 'NO'}**"
         + (f" at **{d['d2']:,} draws**" if d.get("d2") else "") + "\n",
         d["reason"], "",
         "## The pre-registered decision rule, in order", "",
         "| # | clause | measured | verdict |", "|---|---|---|---|"]
    repro, live, sc, ci = (c["G0_reproduction_pin"], c["G1_seed_is_live"],
                           c["G2_mc_variance_scales_as_one_over_draws"], c["G3_ceiling_ci"])
    g0 = ("✅" if repro["reproduces"]
          else ("❌ RAISE — UNEVALUABLE" if not repro["evaluable"] else "❌ RAISE"))
    L += [f"| G0 | reproduction pin vs NF-W7f's STORED scores | max abs gap "
          f"{_f(repro['max_abs_gap'], 12)} over {repro['n_compared']} cells "
          f"(tol {repro['tolerance']}) | {g0} |",
          f"| G1 | the seed is live (across-seed sd > 0 everywhere) | "
          f"{len(live['zero_spread_cells'])} zero-spread cells | "
          f"{'✅' if live['holds'] else '❌ RAISE'} |",
          f"| G2 | σ²_MC scales as 1/draws | ratio {_f(sc.get('ratio'), 3)} "
          f"(nominal {_f(sc.get('expected'), 1)}, band {sc.get('band')}) | "
          f"{'✅' if sc.get('holds') else '❌ UNDEFINED_SCALING'} |",
          f"| G3 | the CEILING clears the bar | DSR_ceiling "
          f"{_f(v['ceiling']['ceiling']['dsr'])}, CI95 "
          f"[{_f(ci.get('lo'))}, {_f(ci.get('hi'))}] vs bar {v['dsr_min']} | "
          f"{'✅ FUND' if d['fund_phase_b'] else '❌ ' + d['verdict']} |", ""]

    L += ["## §1 The variance decomposition — Monte-Carlo error vs season-to-season heterogeneity",
          "", "> `σ²_MC` is the WITHIN-fold, ACROSS-seed variance of the paired delta at "
          f"{out['draws_primary']:,} draws — the error NF-W7f's published per-fold numbers actually "
          "carry. `σ_het` is what is left after removing it: genuine season-to-season signal. "
          "⭐ Common random numbers are preserved within a (fold, seed), exactly as NF-W7f does, so "
          "this is the Monte-Carlo error of the PAIRED quantity the gate reads — not the much "
          "larger and irrelevant error of either score alone.", "",
          "| arm vs foil | mean δ | one-seed sd | σ_MC | σ_het | MC share of variance |",
          "|---|---|---|---|---|---|"]
    for a in QM.REAL_ARMS:
        de = v["decomposition_primary"][a]
        L.append(f"| `{a}` | {_f(de['mean_delta'], 5)} | "
                 f"{_f(math.sqrt(max(de['single_seed_var'], 0.0)), 5)} | {_f(de['mc_sd'], 5)} | "
                 f"{_f(de['het_sd'], 5) if de['het_sd'] is not None else '**negative**'} | "
                 f"{_share(de['mc_share_of_single_seed_var'])} |")
    dw = v["decomposition_primary"][w]
    L += ["", f"- the winner `{w}`'s one-seed sd decomposes as σ_MC {_f(dw['mc_sd'], 5)} vs "
              f"σ_het {_f(dw['het_sd'], 5) if dw['het_sd'] is not None else 'NEGATIVE'} "
              f"— MC share **{_share(dw['mc_share_of_single_seed_var'])}**",
          f"- NF-W7f's published per-fold sd for this delta was 0.0182; measured here as "
          f"{_f(math.sqrt(max(dw['single_seed_var'], 0.0)), 5)}",
          "- ⚠️ `σ_het` is reported SIGNED and never clamped: a negative estimate would say the "
          "observed fold spread is no larger than draw noise alone, and silently clamping it to "
          "zero would manufacture an infinite ceiling and a fake `FUND`.", ""]

    L += ["### The 1/draws law, MEASURED rather than assumed", "",
          "| arm | σ²_MC at {:,} | σ²_MC at {:,} | ratio | nominal | in band |".format(
              out["draws_control"], out["draws_primary"]), "|---|---|---|---|---|---|"]
    for a in QM.REAL_ARMS:
        s = v["checks"]["G2_by_arm"][a]
        L.append(f"| `{a}` | {s.get('mc_var_control'):.3e} | {s.get('mc_var_primary'):.3e} | "
                 f"{_f(s.get('ratio'), 3)} | {_f(s.get('expected'), 1)} | "
                 f"{'✅' if s.get('holds') else '❌'} |")

    req = v["required_mc_share_sensitivity"]
    meas = v["decomposition_primary"][w]["mc_share_of_single_seed_var"]
    L += ["", "### ⭐ How much Monte-Carlo error would the ceiling have NEEDED? (a sensitivity)", "",
          "> Arithmetic on NF-W7f's ALREADY-PUBLISHED series — it measures nothing new. Its value "
          "is that it fixes the number the run has to beat BEFORE the run reports anything. "
          "⚠️ Stated assumption: **one common absolute σ_MC across the declared arms** (the right "
          "first-order shape under common random numbers, but an assumption — the run measures "
          "each arm separately).", "",
          f"- a ceiling at the bar {v['dsr_min']} would require Monte-Carlo error to be "
          f"**{_f(req['required_mc_share_of_winner_var'], 4) if req['required_mc_share_of_winner_var'] is not None else 'unreachable at any share'}** "
          f"of the winner's per-fold variance"
          + (f" (σ_MC ≈ {_f(req['required_mc_sd'], 5)} against an observed one-seed sd of "
             f"{_f(req['winner_observed_sd'], 5)})" if req["required_mc_sd"] else ""),
          f"- **MEASURED share: {_f(meas, 4)}**",
          f"- the best DSR anywhere on that sweep is {_f(req['max_dsr_over_sweep'])} — so even the "
          f"most favourable assumed split barely reaches the bar",
          "", "| assumed MC share of winner variance | winner Sharpe | `SR0` | DSR |",
          "|---|---|---|---|"]
    for c in req["curve"]:
        L.append(f"| {_f(c['mc_share_of_winner_var'], 4)} | {_f(c['winner_sharpe'], 3)} | "
                 f"{_f(c['sr0'], 3)} | {_f(c['dsr'])} |")
    L += ["", "⭐ Read the `SR0` column: it climbs WITH the winner's Sharpe, because the winner is "
              "one of the four trials whose dispersion sets the bar. That is the whole reason the "
              "pre-registration made the ceiling bind over the MC-share proxy (§3.1) — a large MC "
              "share does not, on its own, imply a reachable gate.", ""]
    L += ["", "## §2 The gate at every draw count — and at the CEILING", "",
          "> ⭐ **THE WINNER IS A MEMBER OF ITS OWN TRIAL FIELD.** `SR0` is the deflation benchmark "
          "built from the DISPERSION of the four arms' Sharpes, and the winner is one of those four "
          "trials — so removing Monte-Carlo error raises the winner's Sharpe **and** `SR0` "
          "together. Whether the gap closes is arithmetic, which is why the pre-registration made "
          "the CEILING bind over the 'is the MC share large?' proxy (prereg §3.1).", "",
          "| draws | winner Sharpe | `SR0` | DSR | clears "
          f"{v['dsr_min']}? |", "|---|---|---|---|---|"]
    for r in v["ceiling"]["rungs"]:
        lab = r["label"]          # each rung names itself; the identity row is NOT a draw count
        ok = r["dsr"] is not None and r["dsr"] >= v["dsr_min"]
        sr = "**unbounded**" if r.get("unbounded") else _f(r["winner_sharpe"], 3)
        dsr = "**unbounded**" if r.get("unbounded") else _f(r["dsr"])
        mark = "✅" if (ok or r.get("unbounded")) else "❌"
        L.append(f"| {lab} | {sr} | {_f(r['sr0'], 3)} | {dsr} | {mark} |")
    L += ["", f"- the **observed** row is the registered NO-OP identity (prereg §3.2): the "
              f"projection at the observed sds must return NF-W7f's recorded DSR exactly, and it "
              f"returns {_f(v['ceiling']['rungs'][0]['dsr'])}",
          f"- CI95 on the ceiling DSR (folds resampled, {ci.get('n_effective')} usable resamples): "
          f"[{_f(ci.get('lo'))}, {_f(ci.get('hi'))}], median {_f(ci.get('median'))}",
          "- the winner's projected Sharpe is asserted MONOTONE in the draw count — removing noise "
          "can only raise |SR|, so a violation would be a coding defect, not a finding", ""]

    L += ["### Trial Sharpes at the ceiling (what sets the bar)", "",
          "| arm | Sharpe observed | Sharpe at the ceiling |", "|---|---|---|"]
    obs_sr = v["ceiling"]["rungs"][0]["trial_sharpes"]
    cei_sr = v["ceiling"]["ceiling"]["trial_sharpes"]
    for a in sorted(obs_sr):
        L.append(f"| `{a}` | {_f(obs_sr[a], 3)} | {_f(cei_sr[a], 3)} |")

    if v.get("null_state"):
        n = v["null_state"]
        L += ["", "## §3 The null state, from the shared instrument", "",
              f"- state: **`{n.get('state')}`**", f"- reason: {n.get('reason')}",
              f"- re-test trigger: `{n.get('retest_trigger')}`",
              f"- `field_remedy_admissible`: `{n.get('field_remedy_admissible')}`",
              "- ⭐ read as a MACHINE FLAG, never the prose (MH2.7). ⛔ This story publishes NO "
              "draw / fold / season re-test trigger of its own: the ceiling is what no draw count "
              "can beat, so a trigger would be the NF-D18 misleading direction.", ""]

    L += ["## ⭐ Flagged for a 2nd reader (governance)", "",
          "A DSR gate re-read is governance-adjacent. Protections, all registered BEFORE any score "
          "existed (prereg §5): the bar is unchanged at "
          f"`DSR_MIN = {v['dsr_min']}`; the field is unchanged (no post-hoc trim — MH2.2); the "
          "folds are unchanged; the seeds, both draw counts, the decision rule, the "
          "`{16,000 · 64,000 · 256,000}` ladder and its cap were all fixed in advance; and the "
          "only admissible ship path runs through a FULL-gate Phase B, never through this story. "
          f"**`{d['verdict']}` closes a lever; it does not weaken a bar.**", "",
          "## Promote blockers", ""] + [f"- {b}" for b in v["promote_blockers"]] + [""]
    path.write_text("\n".join(L))


# ── Orchestration ───────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-W7k — the Monte-Carlo variance gate (§0.5)")
    ap.add_argument("--smoke", action="store_true", help="path proof: 1 fold, tiny draws, 2 seeds")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="re-derive every verdict from the stored scores (zero refit)")
    ap.add_argument("--rebuild-cache", action="store_true", help="rebuild the W6d matrix cache")
    ap.add_argument("--rebuild-banks", action="store_true", help="refit the per-fold marginals")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    suffix = "_smoke" if args.smoke else ""
    art = _PROJECT_ROOT / _ARTIFACT_REL.replace(".json", f"{suffix}.json")

    if args.rewrite_report:
        out = derive_verdict_layer(json.loads(art.read_text()))
        out["rewritten_at"] = datetime.now(timezone.utc).isoformat()
        art.write_text(json.dumps(out, indent=2, default=str))
        write_report(out, art.with_suffix(".md"))
        log.info("NF-W7k report re-derived → %s", art.name)
        return 0

    FA.assert_stat_key_map()
    feat, pit_audit, _attach = W7F.W6DA.build_matrix_w6d(W7F.SEASONS,
                                                         rebuild_cache=args.rebuild_cache)
    gate_p, bake_p, def_p = W7F.W6DS.record_paths("")
    smap = W7F.SDSD.served_map(gate_p, bake_p, def_p)
    folds = WP.build_folds(feat)
    matrix_key = W7F.W6DA.w6d_matrix_key(W7F.SEASONS)
    seeds = MV.SEEDS[:2] if args.smoke else MV.SEEDS
    levels = (200, 50) if args.smoke else MV.DRAW_LEVELS
    if args.smoke:
        # ⛔ TWO folds, not one: the decomposition compares a WITHIN-fold across-seed spread
        # against an ACROSS-fold spread, so a one-fold path proof could not reach the verdict
        # layer at all — it would prove only that banks assemble. Two is the instrument's own
        # documented floor.
        folds = folds[-2:]
    log.info("[W7k] %d folds × %d seeds × draw levels %s (matrix %s)%s", len(folds), len(seeds),
             levels, matrix_key, " [SMOKE]" if args.smoke else "")

    t0 = time.time()
    scores: dict[str, dict[str, dict[str, dict[str, float]]]] = {str(d): {} for d in levels}
    meta: dict[str, dict] = {}
    for fold in folds:
        setup = fold_setup(fold, feat, smap, matrix_key, rebuild_banks=args.rebuild_banks)
        meta[fold.label] = {k: setup[k] for k in ("n_test", "n_train", "bank_cache")}
        for draws in levels:
            scores[str(draws)][fold.label] = {}
            for seed in seeds:
                ts = time.time()
                scores[str(draws)][fold.label][str(seed)] = score_at(setup, draws=draws, seed=seed)
                log.info("[W7k] fold %s draws %d seed %d in %.1fs", fold.label, draws, seed,
                         time.time() - ts)

    out = {
        "story": MV.STORY, "phase": "monte_carlo_variance_gate", "smoke": bool(args.smoke),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "position": POSITION, "gate_league": W7F.GATE_LEAGUE,
        "seasons": list(W7F.SEASONS), "n_folds": len(folds), "matrix_key": matrix_key,
        "pit_audit": pit_audit,
        "base_seed": MV.BASE_SEED, "seeds": list(seeds), "n_seeds": len(seeds),
        "seed_stride": MV.SEED_STRIDE,
        "draws_primary": levels[0], "draws_control": levels[1],
        "row_block": QM.ROW_BLOCK, "scored_labels": list(SCORED_LABELS),
        "declared_field": {"real_arms": list(QM.REAL_ARMS),
                           "contest_foils": list(QM.CONTEST_FOILS)},
        "fold_meta": meta, "scores": scores,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    out = derive_verdict_layer(out)
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(json.dumps(out, indent=2, default=str))
    write_report(out, art.with_suffix(".md"))
    log.info("NF-W7k %s → %s (%.1fs)", out["verdict"]["story_verdict"], art.name,
             out["runtime_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
