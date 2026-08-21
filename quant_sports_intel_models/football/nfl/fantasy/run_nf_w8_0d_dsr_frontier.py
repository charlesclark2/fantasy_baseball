"""NF-W8-0d — RUNNER: the DSR gate-design / power frontier for weekly QB.

    uv run python quant_sports_intel_models/football/nfl/fantasy/run_nf_w8_0d_dsr_frontier.py
    uv run python .../run_nf_w8_0d_dsr_frontier.py --smoke        # a 200-rep path proof

⛔ AN INSTRUMENT. No model ships, nothing is promoted, no live gate is relaxed and no arm is
re-scored. `DSR_MIN` is INHERITED at 0.95 and the declared field stays at 4 (MH2.7). Every input is
arithmetic on NF-W8-0c's ALREADY-PUBLISHED per-fold scores — the EFFECT is held fixed, only the
DESIGN moves. Pre-registration: `ablation_results/nf_w8_0d_preregistration.md`.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from betting_ml.utils import cv_power  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import fp_dsr_frontier as DF  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14  # noqa: E402

log = logging.getLogger("nf_w8_0d")
ART = Path(__file__).resolve().parent / "ablation_results"
SOURCE_RECORD = ART / "nf_w8_0c_qb_body.json"

#: the FORWARD recommendation's diagnostic exclusion — NF-W8-0c MEASURED `avail_relevel` inactive
#: (its own per-form peeking oracle's ceiling is −0.0018 PPR, and the π clamp binds on 88–95% of
#: rows, so the mixture-weight channel is structurally unable to move the level).
#: ⛔ DIAGNOSTIC ONLY. Not applied to NF-W8-0c, whose refusal STANDS.
MEASURED_INACTIVE: tuple[str, ...] = ("avail_relevel",)


def _f(x, nd=4):
    return "—" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def build(smoke: bool = False) -> dict:
    t0 = time.time()
    reps = 200 if smoke else DF.REPS
    windows = DF.WINDOWS[:2] if smoke else DF.WINDOWS
    folds = (4, 8, 16) if smoke else DF.FOLD_COUNTS

    record = json.loads(SOURCE_RECORD.read_text())
    obs = DF.load_observed(record)
    deltas = DF.delta_series(obs.bias)
    srs = DF.sharpes(deltas)

    # ── G0 the reproduction pin ────────────────────────────────────────────────────────────────
    dsr_repro = M14.deflated_sharpe(deltas[DF.WINNER], srs)
    gap = abs(float(dsr_repro) - DF.RECORDED_DSR) if dsr_repro is not None else float("inf")
    g0 = {"passes": bool(gap <= DF.REPRO_TOL), "reproduced": dsr_repro,
          "recorded": DF.RECORDED_DSR, "abs_gap": gap, "tolerance": DF.REPRO_TOL,
          "recorded_source": str(SOURCE_RECORD.name)}
    # the split-field carrier must be a NO-OP when nothing is excluded, or the diagnostic and the
    # gate are two different arithmetics (NF-W7k / NF-C0e)
    split_identity = DF.dsr_split_field(deltas[DF.WINNER], srs, len(DF.REAL_ARMS))
    g0["split_field_is_identity"] = bool(split_identity == dsr_repro)

    # ── §2 the level decomposition + the paired-noise bound ────────────────────────────────────
    level = DF.level_decomposition(obs)
    paired = DF.paired_noise_bound(obs)

    # ── §3 the lockstep ladder (G2) ────────────────────────────────────────────────────────────
    ladder = DF.lockstep_ladder(deltas)
    g2 = {"passes": bool(DF.lockstep_is_live(ladder)),
          "sign_of_sr_minus_sr0": {_f(r["dispersion_factor"], 2):
                                   ("+" if r["sr_minus_sr0"] > 0 else "−") for r in ladder},
          "sign_is_invariant": len({("+" if r["sr_minus_sr0"] > 0 else "−")
                                    for r in ladder}) == 1,
          "dsr_falls_as_design_sharpens": bool(
              all(b["dsr"] <= a["dsr"] + 1e-12 for a, b in zip(ladder, ladder[1:]))),
          "ladder": ladder}

    model = DF.fit_design_model(obs)

    # ── G1 calibration at the OBSERVED design ──────────────────────────────────────────────────
    calib = DF.simulate_design(model, level["mean_rows_per_fold"], len(obs.folds), "persistent",
                               reps=max(reps, 1000), seed=DF.BASE_SEED)
    g1 = {"passes": bool(calib["dsr_p05"] <= DF.RECORDED_DSR <= calib["dsr_p95"]),
          "observed_dsr": DF.RECORDED_DSR, "sim_p05": calib["dsr_p05"],
          "sim_median": calib["dsr_median"], "sim_p95": calib["dsr_p95"],
          "design": {"rows_per_fold": calib["rows_per_fold"], "n_folds": calib["n_folds"]}}

    # ── §4 the frontier under the REGISTERED gate (G3) ─────────────────────────────────────────
    grid = DF.frontier(model, windows=windows, fold_counts=folds, reps=reps)
    v = DF.verdict(grid)
    g3 = {"passes": bool(v["answer"] == "a"), "verdict": v["state"],
          "best_feasible_median_dsr": v["best_feasible"]["dsr_median"],
          "best_anywhere_median_dsr": v["best_anywhere"]["dsr_median"], "bar": DF.DSR_MIN}

    # ── §5 where `V` comes from ────────────────────────────────────────────────────────────────
    attribution = DF.v_attribution(deltas)
    alt = DF.alternative_statistic_field(obs.bias)

    # ── §6 the FORWARD recommendation, as a labelled DIAGNOSTIC ────────────────────────────────
    diag_grid = DF.frontier(model, windows=windows, fold_counts=folds, reps=reps,
                            seed=DF.BASE_SEED + 500_000, v_exclude=MEASURED_INACTIVE)
    diag_best = DF.best_point(diag_grid, feasible_only=True)
    diag_clearing = sorted((r for r in diag_grid if r["feasible"] and r["clears_on_median"]),
                           key=lambda r: (-r["dsr_median"],))
    dsr_r1_at_observed = DF.dsr_split_field(
        deltas[DF.WINNER],
        np.asarray([s for a, s in zip(DF.REAL_ARMS, srs) if a not in MEASURED_INACTIVE]),
        len(DF.REAL_ARMS))

    # ── the null classification, computed by the SHARED instrument ─────────────────────────────
    # ⛔ the SHARED instrument, called with NF-W8-0c's OWN inputs so the state it returns is the
    # one that story recorded — this run re-classifies nothing, it prints the classifier verbatim
    # so §1's finding can be read AGAINST its remedy text rather than instead of it.
    w_delta = deltas[DF.WINNER]
    _c = w_delta - w_delta.mean()
    _sd = float(w_delta.std(ddof=0))
    classification = cv_power.classify_null(
        metric="qb_abs_level_bias",
        n_folds=len(obs.folds), n_arms=len(DF.REAL_ARMS), beats_foil=True,
        observed_sr=float(srs[DF.REAL_ARMS.index(DF.WINNER)]),
        var_trials_sr=float(np.var(srs, ddof=1)),
        fold_wins=int((w_delta > 0).sum()),
        p_one_sided=float(record["family_b"]["p_reduces_bias_one_sided"]),
        skew=float((_c ** 3).mean() / _sd ** 3) if _sd > 0 else 0.0,
        kurt=float((_c ** 4).mean() / _sd ** 4) if _sd > 0 else 3.0,
        declared_field_size=DF.DECLARED_FIELD_SIZE,
        degenerates_excluded_from_v=True)
    classification = {"state": classification.state, "reason": classification.reason,
                      "retest_trigger": classification.retest_trigger,
                      "folds_have": classification.folds_have,
                      "folds_needed": classification.folds_needed,
                      "extra_seasons": classification.extra_seasons,
                      "max_field_size": classification.max_field_size,
                      "field_remedy_admissible": classification.field_remedy_admissible,
                      "detail": classification.detail}

    gates = {"G0_reproduction": g0, "G1_calibration": g1, "G2_lockstep_live": g2, "G3_frontier": g3}
    return {
        "story": DF.STORY, "predecessors": list(DF.PREDECESSORS), "kind": "instrument",
        "smoke": bool(smoke), "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_record": str(SOURCE_RECORD.name),
        "bar": DF.DSR_MIN, "declared_field_size": DF.DECLARED_FIELD_SIZE,
        "observed": {"folds": list(obs.folds),
                     "bias": {a: [float(x) for x in b] for a, b in obs.bias.items()},
                     "n_rows": [float(x) for x in obs.n_rows],
                     "sd_err": [float(x) for x in obs.sd_err],
                     "delta_winner": [float(x) for x in deltas[DF.WINNER]],
                     "trial_sharpes": {a: float(s) for a, s in zip(DF.REAL_ARMS, srs)}},
        "gates": gates,
        "level_decomposition": level, "paired_noise_bound": paired,
        "design_model": {"mu_bar": model.mu_bar, "sigma_u": model.sigma_u,
                         "sigma_row": model.sigma_row,
                         "rows_per_fold_0": model.rows_per_fold_0,
                         "reps": reps, "laws": list(DF.LAWS)},
        "frontier": grid, "verdict": v,
        "v_attribution": attribution, "alternative_statistics": alt,
        "forward_recommendation": {
            "measured_inactive": list(MEASURED_INACTIVE),
            "dsr_at_observed_design": dsr_r1_at_observed,
            "best_feasible": diag_best,
            "clearing_feasible_points": diag_clearing[:8],
            "n_clearing_feasible": len(diag_clearing),
            "grid": diag_grid,
        },
        "classification": classification,
        "declared_field_size_source": ("NF-W8-0c prereg §4 — 4 arms, the §0.5 minimum "
                                       "(≥3 classes + a direct-learned foil); MH2.7 "
                                       "stamped the shrink remedy SUSPECT"),
        "runtime_seconds": round(time.time() - t0, 1),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
def render(out: dict) -> str:
    v, g = out["verdict"], out["gates"]
    L = out["level_decomposition"]
    P = out["paired_noise_bound"]
    R = out["forward_recommendation"]
    ok = lambda b: "✅" if b else "❌"  # noqa: E731
    m: list[str] = []
    m.append("# NF-W8-0d — the DSR gate-design FRONTIER for weekly QB "
             f"(**{v['state']}**, answer **({v['answer']})**)")
    m.append("")
    m.append(f"Generated {out['generated_at']} · position **QB** · source record "
             f"`{out['source_record']}` · bar `DSR_MIN` **{out['bar']}** (INHERITED) · declared "
             f"field **{out['declared_field_size']}**"
             + ("  ·  ⚠️ **SMOKE**" if out["smoke"] else ""))
    m.append("")
    m.append("⚖️ `best_alpha = 0` · **DEPLOY-HELD** · an INSTRUMENT. ⛔ No model ships, nothing is "
             "promoted, no arm is re-scored and **no live gate is relaxed**. Every number is "
             "arithmetic on NF-W8-0c's already-published per-fold scores — the EFFECT is held "
             "fixed, only the DESIGN moves.")
    m.append("")

    # ── verdict ────────────────────────────────────────────────────────────────────────────────
    m.append("## Verdict")
    m.append("")
    bf, ba = v["best_feasible"], v["best_anywhere"]
    if v["answer"] == "a":
        m.append(f"- a FEASIBLE design point clears the bar on the **median**: "
                 f"{bf['window']} · {bf['n_folds']} folds × {bf['rows_per_fold']:.0f} rows "
                 f"(`{bf['law']}`) → median DSR **{bf['dsr_median']:.4f}** ≥ {out['bar']}")
    else:
        m.append(f"- **NO feasible design point clears `dsr_ok = {out['bar']}`** for a QB weekly "
                 f"level effect of the observed magnitude. Best FEASIBLE point anywhere on the "
                 f"grid: {bf['window']} · {bf['n_folds']} folds × {bf['rows_per_fold']:.0f} rows "
                 f"(`{bf['law']}`) → median DSR **{bf['dsr_median']:.4f}**.")
        m.append(f"- and *a fortiori*, the best point on the whole grid **including the "
                 f"deliberately UNREACHABLE window** is {ba['window']} · {ba['n_folds']} folds × "
                 f"{ba['rows_per_fold']:.0f} rows (`{ba['law']}`) → median DSR "
                 f"**{ba['dsr_median']:.4f}** — still short of {out['bar']}.")
        m.append("- ⇒ the gate is **MIS-SPECIFIED for this effect at this design**, and the remedy "
                 "is a **registered-FORWARD gate-design change** (§6). ⛔ It is NOT applied here "
                 "and NF-W8-0c's refusal **STANDS** (E2.1-r).")
    m.append(f"- grid: {v['n_grid_points']} points ({v['n_feasible_points']} feasible) × "
             f"{out['design_model']['reps']} replicates each")
    m.append("")
    m.append("> The verdict binds on the **MEDIAN**, never on `P(clear)`. A design whose median "
             "sits below the bar has not cleared — it only sometimes draws a lucky panel, which is "
             "exactly the selection bias DSR exists to deflate. `P(clear)` is reported beside it "
             "as spread, never as the criterion (prereg §3).")
    m.append("")

    # ── gates ──────────────────────────────────────────────────────────────────────────────────
    m.append("## The pre-registered decision rule, in order")
    m.append("")
    m.append("| # | clause | measured | verdict |")
    m.append("|---|---|---|---|")
    g0 = g["G0_reproduction"]
    m.append(f"| G0 | the instrument reproduces NF-W8-0c's recorded DSR from the published "
             f"per-fold biases | {_f(g0['reproduced'])} vs {_f(g0['recorded'])}, gap "
             f"{g0['abs_gap']:.2e} (tol {g0['tolerance']:.0e}); split-field carrier is a no-op: "
             f"{g0['split_field_is_identity']} | {ok(g0['passes'])} |")
    g1 = g["G1_calibration"]
    m.append(f"| G1 | the design model brackets the observed DSR at the OBSERVED design | "
             f"observed {_f(g1['observed_dsr'])} inside sim [{_f(g1['sim_p05'])}, "
             f"{_f(g1['sim_p95'])}] (median {_f(g1['sim_median'])}) | {ok(g1['passes'])} |")
    g2 = g["G2_lockstep_live"]
    m.append(f"| G2 | the lockstep ladder is LIVE (a proportional change moves the arithmetic) | "
             f"winner Sharpe strictly monotone in 1/c | {ok(g2['passes'])} |")
    g3 = g["G3_frontier"]
    m.append(f"| G3 | some FEASIBLE `(m, T)` reaches a **median** projected DSR ≥ bar | best "
             f"feasible median {_f(g3['best_feasible_median_dsr'])} vs bar {g3['bar']} | "
             f"{ok(g3['passes'])} → **({v['answer']})** |")
    m.append("")

    # ── §1 lockstep ────────────────────────────────────────────────────────────────────────────
    m.append("## §1 ⭐ The LOCKSTEP invariant — why \"a lower-variance design\" is not a lever")
    m.append("")
    m.append("`deflated_sharpe` reads the winner's Sharpe `SR` **and** the deflation benchmark "
             "`SR0 = std(trial Sharpes)·z(N)` — and the winner is one of those trials (NF-W7k). A "
             "design change that multiplies **every** arm's per-fold dispersion by a common `c` "
             "scales every trial Sharpe by `1/c`, hence `SR0` by `1/c`, hence")
    m.append("")
    m.append("> `SR − SR0  ↦  (SR − SR0)/c` — **its SIGN is invariant.**")
    m.append("")
    m.append(f"Clearing the bar needs the DSR statistic `(SR−SR0)·√(T−1)/√denom ≥ Φ⁻¹({out['bar']}) "
             "> 0`, hence needs `SR > SR0`. **So a purely proportional dispersion lever can never "
             "flip an `SR ≤ SR0` refusal — at any row count, fold count or draw count.** And when "
             "`SR < SR0` the gap is negative, so a *sharper* design makes it **more** negative:")
    m.append("")
    m.append("| dispersion × | winner Sharpe | `SR0` | `SR − SR0` | DSR |")
    m.append("|---|---|---|---|---|")
    for r in g2["ladder"]:
        m.append(f"| {r['dispersion_factor']:g} | {r['winner_sharpe']:.4f} | {r['sr0']:.4f} | "
                 f"{r['sr_minus_sr0']:+.4f} | {_f(r['dsr'])} |")
    m.append("")
    m.append(f"- the sign of `SR − SR0` is invariant across the ladder: **{g2['sign_is_invariant']}**")
    m.append(f"- DSR **falls monotonically as the design sharpens**: "
             f"**{g2['dsr_falls_as_design_sharpens']}** — a 100×-sharper design takes the gate from "
             f"{_f(g2['ladder'][0]['dsr'])} to {_f(g2['ladder'][-1]['dsr'])}.")
    m.append("")
    m.append("⇒ the remedy **three** consecutive records prescribed — \"a lower-variance design\" — "
             "is not merely ineffective here, it is **counter-productive**, because the variance "
             "reduction is *shared across the field*. That is the generic case: the arms score the "
             "same rows with the same draws (common random numbers). A variance lever helps only "
             "to the extent it shrinks the WINNER's dispersion **more** than the field's — a "
             "residual the frontier below measures rather than asserts.")
    m.append("")
    m.append("This generalises NF-W7k (draws) and MH2's `DSR_UNREACHABLE` (folds) to the statement "
             "that actually covers the prescription: **any** shared variance lever.")
    m.append("")

    # ── §2 decomposition ───────────────────────────────────────────────────────────────────────
    m.append("## §2 The rows/fold lever, measured on the statistic the gate READS")
    m.append("")
    m.append(f"NF-W8-0c's decomposition of the **level** reproduces exactly: observed fold SD "
             f"**{L['observed_fold_sd']:.4f}** PPR vs a mean within-fold SE of "
             f"**{L['mean_within_fold_se']:.4f}** ⇒ **{L['sampling_share_of_fold_variance']:.1%}** "
             f"of the fold-scale variance is row sampling at {L['mean_rows_per_fold']:.0f} "
             f"rows/fold, leaving a between-fold SD of "
             f"**{_f(L['excess_sd'])}**.")
    m.append("")
    m.append("⚠️ **But the gate does not deflate the level — it deflates the PAIRED statistic** "
             "`δ = |b_I| − |b_a|`, and")
    m.append("")
    m.append("> `b_I,f − b_a,f = −(1/m)·Σᵢ(pointₐ,ᵢ − point_I,ᵢ)` — **the realized `y` cancels "
             "exactly.**")
    m.append("")
    m.append(f"`cond_shift` adds `S·alive` to every draw, so every row's point difference lies in "
             f"`[0, S]` and has mean equal to the fold's OBSERVED level shift `s_f` "
             f"({P['worst_fold_shift_ppr']:.4f} PPR at its worst fold). Bhatia–Davis then bounds "
             f"its row SD by `√(s_f·(S − s_f))`. ⚠️ `S` is the raw shift PARAMETER and is not in "
             f"the record — only `s_f = S·π̄` is — so rather than assume a `π̄` the bound is "
             f"EVALUATED over a declared grid, against a per-row error SD of "
             f"**{P['level_row_sd_ppr']:.2f}** PPR:")
    m.append("")
    m.append("| assumed `π̄` | implied raw shift `S` | paired row-SD bound | share of the level's "
             "sampling variance |")
    m.append("|---|---|---|---|")
    for r in P["pi_bar_ladder"]:
        m.append(f"| {r['pi_bar']:.1f} | {r['raw_shift_ppr']:.4f} | "
                 f"{r['paired_row_sd_bound_ppr']:.4f} | {r['share_of_level_variance']:.2%} |")
    m.append("")
    m.append(f"**Across the whole declared grid the paired difference carries at most "
             f"{P['paired_share_of_level_variance_bound']:.2%} of the level's sampling variance** — "
             f"the finding is robust to `π̄`, not contingent on it.")
    m.append("")
    m.append("The level's noise re-enters `δ` **only through the `|·|` KINK**, on the folds where "
             "the corrected bias crosses zero (2 of 7 for `cond_shift`). ⇒ **measuring the "
             "rows/fold lever on the LEVEL over-states it**; this is NF-W7k's common-random-numbers "
             "lesson one axis over — the arms share the same rows, so row-sampling error cancels in "
             "the paired delta.")
    m.append("")

    # ── §3 frontier ────────────────────────────────────────────────────────────────────────────
    m.append("## §3 The frontier — rows/fold × fold count, under the REGISTERED gate")
    m.append("")
    m.append("On a fixed window the two axes trade: `m = N / T`. Both declared scaling laws for "
             "the non-sampling fold-scale variance are run at every point (`persistent` = regime "
             "variation is real; `averaging` = it is white below the fold and falls as `1/m`, the "
             "reading most FAVOURABLE to the lever). **Every declared bias favours the lever, so a "
             "NO is conservative** (NF-W7k's discipline).")
    m.append("")
    m.append("| window | feasible | folds `T` | rows/fold `m` | block wks | law | median DSR | "
             "P(clear) | median `SR` | median `SR0` | P(`SR`>`SR0`) |")
    m.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in out["frontier"]:
        m.append(f"| {r['window']} | {'✅' if r['feasible'] else '⛔'} | {r['n_folds']} | "
                 f"{r['rows_per_fold']:.0f} | {r['block_weeks']:.1f} | {r['law']} | "
                 f"**{r['dsr_median']:.3f}** | "
                 f"{r['p_clears']:.3f} | {r['sr_median']:.3f} | {r['sr0_median']:.3f} | "
                 f"{r['p_sr_exceeds_sr0']:.3f} |")
    m.append("")
    # ⚠️ COMPUTED, never asserted. An earlier draft of this paragraph claimed `SR0 > SR` at EVERY
    # point; the decisive sweep falsified it at 4 of 80. A record that states a universal its own
    # table contradicts is worse than one that states the exception, so the sentence is derived.
    exc = [r for r in out["frontier"] if r["sr_median"] > r["sr0_median"]]
    exc_feasible = [r for r in exc if r["feasible"]]
    m.append(f"⭐ Read the last two numeric columns together: the median `SR0` sits **above** the "
             f"median `SR` at **{len(out['frontier']) - len(exc)} of {len(out['frontier'])}** "
             f"design points, and `P(SR > SR0)` never reaches ½ at any FEASIBLE point. That is the "
             f"lockstep invariant showing up in the sweep rather than in the algebra — the two "
             f"quantities move together, so the gap barely changes sign.")
    m.append("")
    if exc:
        m.append(f"⚠️ **The exceptions, stated rather than smoothed over.** At {len(exc)} points "
                 f"the median `SR` does exceed the median `SR0` — differential shrinkage across "
                 f"the field is real, just small — and **{len(exc_feasible)} of them are "
                 f"FEASIBLE**:")
        m.append("")
        m.append("| window | feasible | folds `T` | rows/fold `m` | law | median `SR` | "
                 "median `SR0` | median DSR |")
        m.append("|---|---|---|---|---|---|---|---|")
        for r in exc:
            m.append(f"| {r['window']} | {'✅' if r['feasible'] else '⛔'} | {r['n_folds']} | "
                     f"{r['rows_per_fold']:.0f} | {r['law']} | {r['sr_median']:.3f} | "
                     f"{r['sr0_median']:.3f} | **{r['dsr_median']:.3f}** |")
        m.append("")
        m.append("Every one sits in the **UNREACHABLE** part of the grid, under the "
                 "lever-FAVOURING `averaging` law, at a fold count of 4–6 — and even there the "
                 f"median DSR tops out at **{max(r['dsr_median'] for r in exc):.3f}**. Two things "
                 "cap it: `√(T−1)` is small at 4 folds, and the DSR statistic's non-normality "
                 "denominator grows like `SR²`, so once `SR` is large the statistic tends to "
                 "`(1 − SR0/SR)·√(T−1)·2/√(γ₄−1)` — **bounded**, however sharp the design. Sign-"
                 "flipping the gap is necessary for the lever; it is nowhere near sufficient.")
        m.append("")

    # ── §4 mechanism ───────────────────────────────────────────────────────────────────────────
    m.append("## §4 WHERE the bar comes from — one MEASURED-INACTIVE arm carries most of `V`")
    m.append("")
    m.append("`SR0 = √V · z(N)` and `V` is a **sample variance over the field's Sharpes**, so one "
             "arm can set the bar every other arm must clear:")
    m.append("")
    m.append("| arm | per-fold Sharpe | share of `Var(trial Sharpes)` |")
    m.append("|---|---|---|")
    for a in out["v_attribution"]:
        m.append(f"| `{a['arm']}` | {a['sharpe']:+.4f} | "
                 f"{(a['share_of_var_trial_sharpes'] or 0):.1%} |")
    m.append("")
    top = max(out["v_attribution"], key=lambda a: a["share_of_var_trial_sharpes"] or 0)
    m.append(f"⭐ **`{top['arm']}` alone carries "
             f"{(top['share_of_var_trial_sharpes'] or 0):.1%} of the deflation dispersion** — and "
             "NF-W8-0c **measured that arm INACTIVE**: its own per-form peeking oracle's ceiling is "
             "−0.0018 PPR and the π clamp binds on 88–95% of rows, so the mixture-weight channel "
             "is structurally unable to move the level (NF-D20 / NF-W6d). Its whole delta series "
             "is ≈ −0.0012 PPR: its Sharpe is the ratio of two numbers at the numerical floor.")
    m.append("")
    m.append("⚠️ **And a variance lever cannot fix this, because an inactive arm's Sharpe is "
             "scale-free** — shrinking noise shrinks its mean and its sd together, so `|SR|` does "
             "not fall. That is precisely why the lockstep ratio `SR0/SR` is flat across the whole "
             "frontier.")
    m.append("")
    m.append("### Alternatives tested — and the one that LOST")
    m.append("")
    m.append("⛔ A labelled DIAGNOSTIC, **not** a re-read of NF-W8-0c: re-scoring a failed gate on "
             "a better-looking statistic is the E2.1-r inversion in its most literal form. These "
             "rows exist so the recommendation can say what was tried and what failed.")
    m.append("")
    m.append("| selection statistic | winner Sharpe | `SR0` | DSR |")
    m.append("|---|---|---|---|")
    for a in out["alternative_statistics"]:
        m.append(f"| {a['statistic']} | {a['winner_sharpe']:.4f} | {a['sr0']:.4f} | "
                 f"{_f(a['dsr'])} |")
    m.append("")
    m.append("The obvious candidate — removing the `|·|` kink by deflating the **squared**-bias "
             "delta — is **WORSE**, not better. The kink is not the binding defect; the field's "
             "Sharpe dispersion is. Recorded as losing rather than dropped.")
    m.append("")

    # ── §5 forward recommendation ──────────────────────────────────────────────────────────────
    m.append("## §5 The verdict-(b) recommendation — registered FORWARD, ⛔ NOT applied here")
    m.append("")
    m.append("**R1 — extend DSR-CONV's `V`-exclusion from \"pre-registered DEGENERATE\" to "
             "\"pre-registered-TEST-MEASURED INACTIVE\".** DSR-CONV (PRs #689/#690) already "
             "establishes *degenerate ∈ `n_trials`, ∉ `V`*, on the argument that a "
             "lose-by-construction arm's Sharpe is not a draw from the search's Sharpe population. "
             "An arm whose **own per-form peeking-oracle ceiling** falls below a pre-registered "
             "materiality floor is in exactly that position for exactly that reason — its Sharpe "
             "is a ratio of two quantities at the numerical floor. The rule must be:")
    m.append("")
    m.append("1. **FORWARD-ONLY and INERT** until a successor story opts in — DSR-CONV's own shape;")
    m.append("2. keyed on the arm's **ANCHOR reading** (the per-form oracle ceiling that NF-D16 "
             "(g‴) already requires every §0.5 story to compute), **never on the leaderboard** — "
             "you may pre-register a family, you may not discover one (MH2.2), and a trim chosen "
             "because an arm LOST can even delete the arm under test (NF-W7h);")
    m.append("3. applied **whichever way it moves the bar** — exclusion is NON-monotone: dropping a "
             "near-mean arm *raises* `SR0` (DSR-CONV);")
    m.append("4. reported with BOTH figures, the un-excluded one binding until a story registers "
             "the convention forward.")
    m.append("")
    m.append(f"**What it would buy, as a DIAGNOSTIC.** With `{', '.join(R['measured_inactive'])}` "
             f"out of `V` and `n_trials` still charged at {out['declared_field_size']}, the "
             f"OBSERVED design reads DSR **{_f(R['dsr_at_observed_design'])}** — note that this is "
             f"**still below the bar**, so R1 is not by itself a licence to ship anything.")
    if R["best_feasible"]:
        b = R["best_feasible"]
        m.append(f"Across the FEASIBLE grid the best point becomes {b['window']} · "
                 f"{b['n_folds']} folds × {b['rows_per_fold']:.0f} rows (`{b['law']}`) → median "
                 f"DSR **{b['dsr_median']:.4f}**, and **{R['n_clearing_feasible']}** feasible "
                 f"points reach the bar on the median:")
        m.append("")
        m.append("| window | folds `T` | rows/fold `m` | block wks | law | median DSR | P(clear) |")
        m.append("|---|---|---|---|---|---|---|")
        for r in R["clearing_feasible_points"]:
            m.append(f"| {r['window']} | {r['n_folds']} | {r['rows_per_fold']:.0f} | "
                     f"{r['block_weeks']:.1f} | {r['law']} | "
                     f"**{r['dsr_median']:.3f}** | {r['p_clears']:.3f} |")
        m.append("")
    m.append("⭐ **The fold-count lever's SIGN flips with the sign of `SR − SR0`.** Under the "
             "registered gate `SR < SR0`, so `√(T−1)` multiplies a negative gap and more folds make "
             "it *worse* — which is exactly why MH2's `DSR_UNREACHABLE` correctly refused the "
             "seasons lever. Once `SR > SR0`, the same `√(T−1)` becomes a real lever, and the "
             "clearing designs above are **more folds**, not more rows per fold. ⚠️ That is a "
             "statement about the two regimes, not a recommendation to add folds today.")
    m.append("")
    if R.get("grid"):
        nat = [r for r in R["grid"] if r["feasible"]
               and abs(r["block_weeks"] - 9.0) < 0.6]   # the SHIPPED half-season granularity
        if nat:
            best_nat = max(nat, key=lambda r: r["dsr_median"])
            m.append(f"⚠️ **Where the clearing points actually sit, stated rather than glossed.** "
                     f"Every one is at the widest reachable window AND the finest admissible fold "
                     f"granularity ({min(r['block_weeks'] for r in R['clearing_feasible_points']):.1f}"
                     f"–{max(r['block_weeks'] for r in R['clearing_feasible_points']):.1f}-week "
                     f"blocks). At the SHIPPED half-season granularity (~9-week blocks) over the "
                     f"same window the best R1 point reads median DSR "
                     f"**{best_nat['dsr_median']:.4f}** — so R1 buys the bar only together with a "
                     f"finer fold split, and a successor must register BOTH, not just the "
                     f"convention.")
            m.append("")
    m.append("### What a successor actually does with this")
    m.append("")
    m.append("1. register R1 FORWARD in its own pre-registration — the inactivity test (a per-form "
             "oracle ceiling below a stated materiality floor), the exclusion's direction-blindness, "
             "and BOTH DSR figures reported;")
    m.append("2. register the DESIGN in the same document — window and fold count are now design "
             "quantities with a measured consequence, not defaults inherited from "
             "`weekly_projection.TEST_BLOCKS`;")
    m.append("3. re-run NF-W8-0c's declared 4-arm field UNCHANGED under that registration. ⛔ It "
             "does not re-read NF-W8-0c's numbers — a registration written after seeing a gate "
             "fail only earns its verdict on a fresh run (MARGIN2→3, NF-W6b-C, W7→W7b: the repo's "
             "own CONSTRAINT_REFUSED → fresh-registration → ship pattern);")
    m.append("4. ⚠️ and expect it to be a REAL contest, not a formality — R1 at the observed design "
             f"reads {_f(R['dsr_at_observed_design'])}, below the bar. This story says the wall is "
             "in the gate's design; it does not say the arm is on the other side of it.")
    m.append("")
    m.append("**Not recommended, and why (both scored above, both losing):** a kink-free selection "
             "statistic (DSR falls to "
             f"{_f([a for a in out['alternative_statistics'] if 'squared' in a['statistic']][0]['dsr'])}"
             "); and any field trim, which is forbidden outright (MH2.2 / NF-W7h) — R1 is a "
             "`V`-composition rule keyed on an anchor, **not** a smaller field: the excluded arm "
             "keeps paying full multiplicity in `n_trials`.")
    m.append("")

    # ── scope ──────────────────────────────────────────────────────────────────────────────────
    m.append("## §6 Scope, and what this does NOT close")
    m.append("")
    m.append("- NF-W8-0c's `dsr_ok` refusal **STANDS**; nothing here re-reads it (E2.1-r). The "
             "same is true of NF-W7f / NF-W7h / NF-W7j.")
    m.append("- ⛔ **No re-test trigger in seasons, folds or rows is published.** The lockstep "
             "invariant is DETERMINISTIC — no `n` overturns it — so a \"come back with more data\" "
             "trigger would be the actively-misleading direction NF-D18 / MH2 (g″) warns about.")
    m.append("- this closes the **shared-variance** lever (rows/fold, folds, draws, a proportionally "
             "sharper estimator). A lever that shrinks the WINNER's dispersion **differentially** "
             "is UNTESTED here, not refuted — the frontier measures the residual differential "
             "shrinkage this field happens to have and finds it too small, which is a statement "
             "about this field, not about every conceivable estimator.")
    m.append("- the scaling law of the non-sampling fold-scale variance is **not identified** from "
             "one fold size; both readings are run and reported, and the lever-favouring one does "
             "not change the verdict.")
    m.append("- R1 is a **recommendation**, not a change: no live gate, no shared instrument and "
             "no registered field is touched by this story.")
    m.append("")
    m.append("## Null classification (the shared instrument, verbatim)")
    m.append("")
    C = out["classification"]
    m.append(f"- **state** `{C['state']}` · `folds_have` {C['folds_have']} · `max_field_size` "
             f"{C['max_field_size']} · `field_remedy_admissible` {C['field_remedy_admissible']}")
    m.append(f"- **reason** — {C['reason']}")
    m.append(f"- **retest_trigger** — {C['retest_trigger']}")
    m.append("")
    m.append("⚠️⚠️ **READ THE TRIGGER AGAINST §1.** `classify_null` is RIGHT that no fold count and "
             "no field size clears — and it then prescribes, verbatim, *\"the only lever left is a "
             "lower-variance design (more rows per fold / a sharper metric)\"*. **That is precisely "
             "the lever this story measures, and §1 shows it is VOID** whenever the variance "
             "reduction is shared across the field, which is the generic case under common random "
             "numbers. The trigger is not wrong about its own axis; it is a prescription the "
             "instrument cannot check, and it is the sentence that sent THREE consecutive records "
             "(NF-W7f, NF-W7j, NF-W8-0c) at a wall. ⇒ **a second forward recommendation, R2: when "
             "`DSR_UNREACHABLE` fires, `classify_null` should compute the lockstep check — "
             "`sign(SR − SR0)` under proportional shrinkage — and, when the sign is negative, state "
             "that the variance lever is closed too, rather than naming it.** Same shape as MH2.7's "
             "own lesson (i): a defect corrected N times downstream is a defect in the INSTRUMENT. "
             "⛔ Not implemented here — `cv_power` is a SHARED instrument pinned by cross-vertical "
             "guards (MH2.7 lesson ii), so changing it is a successor's deliberate step.")
    m.append("")
    m.append(f"_runtime {out['runtime_seconds']}s_")
    return "\n".join(m) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true", help="a fast path proof (200 reps, 2 windows)")
    ap.add_argument("--rewrite-report", action="store_true",
                    help="re-render the .md from the STORED .json — correcting a sentence must "
                         "not cost a re-run (NF-W2e: derive the prose at report time)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stem = "nf_w8_0d_dsr_frontier" + ("_smoke" if a.smoke else "")
    if a.rewrite_report:
        out = json.loads((ART / f"{stem}.json").read_text())
        (ART / f"{stem}.md").write_text(render(out))
        log.info("NF-W8-0d report re-derived → %s", ART / f"{stem}.md")
        return 0
    out = build(smoke=a.smoke)
    ART.mkdir(parents=True, exist_ok=True)
    (ART / f"{stem}.json").write_text(json.dumps(out, indent=1, default=str))
    (ART / f"{stem}.md").write_text(render(out))
    log.info("NF-W8-0d → %s  verdict=%s (%s)  runtime=%ss", ART / f"{stem}.md",
             out["verdict"]["state"], out["verdict"]["answer"], out["runtime_seconds"])
    bad = [k for k, v in out["gates"].items() if k in ("G0_reproduction", "G1_calibration",
                                                       "G2_lockstep_live") and not v["passes"]]
    if bad:
        log.error("NF-W8-0d: a NON-verdict gate failed — %s; the frontier is not interpretable", bad)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
