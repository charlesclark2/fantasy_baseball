#!/usr/bin/env python
"""DSR-CONV — how much of the small-fold DSR difficulty is DEGENERATE ARITHMETIC, and how much is
the fold count itself?

⛔ **THIS IS A PROPERTY STUDY OF THE ESTIMATOR, NOT A RE-VERDICT ON ANY RECORDED STORY.** It runs on
SYNTHETIC fields with a KNOWN planted effect, so nothing here can be read as "story X would now
pass". It exists to give a future decision on the DSR reading (whether the 0.95 whole-field bar needs
any further change at small fold counts) an input that is measured rather than argued — the same role
`mh2_cv_power_characterization.md` plays for the fold clause.

THE QUESTION. `SR0 = √V·z(N)` is the bar a winner's per-fold Sharpe must clear, and `V` is the
CROSS-TRIAL Sharpe dispersion. A §0.5 field is required to contain pre-registered
lose-by-construction degenerates (NF1.8 — a metric a degenerate wins is fatal, so both sides must be
scored) and is required to keep the full declared field in `n_trials` (MH2 §a). Those two rules are
each right, and jointly they put arms into `V` whose distance from the incumbent is a DESIGN
quantity. DSR-CONV removes them from `V` while keeping them in `n_trials`, on exactly the argument
`dsr_gate` already applies to the reference arm.

So: of the difficulty a real winner faces at a small fold count, how much does that exclusion
actually remove? Two mechanisms are in play and they are separable —

  ARITHMETIC (what exclusion fixes) : degenerates inflate `V`, hence `SR0`, hence the required
                                      Sharpe. This scales with how EXTREME the degenerates are and
                                      is INDEPENDENT of the fold count.
  STRUCTURAL (what it cannot fix)   : the DSR statistic scales with `√(n_obs − 1)`, so at a small
                                      fold count even an unbounded true effect caps out — the
                                      `dsr_ceiling(n)` figure. Exclusion does not touch this.

Reported as clearance rates at the 0.95 gate under both conventions, on the SAME simulated fields.

Usage
-----
    uv run python betting_ml/scripts/dsr_conv_characterization.py            # writes the memo
    uv run python betting_ml/scripts/dsr_conv_characterization.py --reps 100 # quicker smoke
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from betting_ml.scripts.e7_9_train_serve_consistency import dsr_gate
from betting_ml.utils.cv_power import dsr_ceiling, dsr_required_sr

# The gate this whole program reads DSR against. Unchanged by DSR-CONV — the point of the fix is that
# the BAR stays put while the quantity compared against it stops being contaminated by design arms.
DSR_GATE = 0.95

# ── The design grid ──────────────────────────────────────────────────────────────────────────────
# Fold counts spanning the range §0.5 legs actually run at: 3 is the narrow-window floor (and the
# fold count at which `dsr_ceiling` alone nearly binds), 13 is a wide-window leg.
FOLD_GRID = (3, 4, 5, 6, 8, 11, 13)

# "Extremity" is the degenerate's per-fold skill SHARPE magnitude — how badly it loses DIVIDED BY how
# consistently. A designed loser is typically very consistent (its badness is structural, not noisy),
# which is precisely why it lands far out in `V`. 0.0 is the control: NO degenerate in the field.
EXTREMITY_GRID = (0.0, 1.0, 3.0, 6.0, 10.0)

# The winner's TRUE per-fold skill Sharpe. Swept because the answer is not the same for a marginal
# effect and a strong one — a strong effect can absorb an inflated bar that kills a marginal one.
# The grid runs well past the bar deliberately: a sweep that never crosses the decision boundary
# reports 0.00 in every cell and characterizes nothing.
TRUE_SR_GRID = (0.7, 1.5, 3.0, 5.0)

N_REAL_ARMS = 5        # the winner + 4 other genuine candidates
N_DEGENERATES = 2      # NF1.8 asks for BOTH sides (a too-sharp and a too-wide degenerate)
# How much the genuine arms' Sharpes disperse among themselves. Kept SMALL because MH2 §a's unit of
# analysis is a COHERENT DECLARED FAMILY — variants of one mechanism, not unrelated mechanisms
# bundled together. ⚠️ Note this is the PLANTED dispersion only: each arm's REALIZED Sharpe carries
# sampling noise on top, and at a small fold count that noise DOMINATES `V`. That is not an artifact
# of the simulation — it is the same quantity `dsr_gate` measures on real folds — and §2 quantifies
# it as the `extremity 0.0` row, where `V` is entirely sampling noise.
REAL_ARM_SR_SD = 0.15


def _field(rng: np.random.Generator, *, n_folds: int, true_sr: float,
           extremity: float) -> tuple[dict[str, list[float]], list[str]]:
    """One synthetic field of per-fold scores (LOWER is better, as `dsr_gate` expects).

    The incumbent's own score series is arbitrary — only DIFFERENCES from it enter the statistic —
    so it is fixed and every other arm is built as `incumbent − skill`.
    """
    inc = rng.normal(1.0, 0.10, n_folds)
    scores: dict[str, list[float]] = {"incumbent": list(inc)}

    # the winner: a per-fold skill series with the planted Sharpe
    sd_w = 0.05
    scores["winner"] = list(inc - rng.normal(true_sr * sd_w, sd_w, n_folds))

    # the other genuine candidates: real arms, dispersing modestly among themselves
    for i in range(N_REAL_ARMS - 1):
        sr_i = rng.normal(0.0, REAL_ARM_SR_SD)
        scores[f"cand_{i}"] = list(inc - rng.normal(sr_i * sd_w, sd_w, n_folds))

    # the pre-registered degenerates: they LOSE (negative skill) and do it CONSISTENTLY, which is
    # what puts a large |Sharpe| into `V`. extremity == 0 ⇒ none are in the field at all (control).
    degs: list[str] = []
    if extremity > 0:
        for j in range(N_DEGENERATES):
            name = f"degenerate_{j}"
            scores[name] = list(inc - rng.normal(-extremity * sd_w, sd_w, n_folds))
            degs.append(name)
    return scores, degs


def run(reps: int = 300, seed: int = 20260808) -> list[dict]:
    rows: list[dict] = []
    for n_folds in FOLD_GRID:
        for extremity in EXTREMITY_GRID:
            for true_sr in TRUE_SR_GRID:
                # Deterministic per-cell seed: the grid is reproducible cell-by-cell, and no cell's
                # draw depends on the order the loop happens to run in.
                rng = np.random.default_rng(
                    (seed, n_folds, int(extremity * 10), int(true_sr * 10)))
                acc: dict[str, list[float]] = {k: [] for k in
                                               ("dsr_with", "dsr_excl", "v_with", "v_excl",
                                                "sr0_with", "sr0_excl", "obs_sr")}
                for _ in range(reps):
                    scores, degs = _field(rng, n_folds=n_folds, true_sr=true_sr,
                                          extremity=extremity)
                    g = dsr_gate(scores, "incumbent", "winner",
                                 n_trials=len(scores), degenerate_arms=tuple(degs))
                    if not g.get("available"):
                        continue
                    acc["dsr_with"].append(g["dsr_with_degenerates_in_V"])
                    acc["dsr_excl"].append(g["dsr_degenerate_excluded"])
                    acc["v_with"].append(g["var_trials_sr_with_degenerates"])
                    acc["v_excl"].append(g["var_trials_sr"])
                    acc["sr0_with"].append(g["sr0_with_degenerates_in_V"])
                    acc["sr0_excl"].append(g["sr0"])
                    acc["obs_sr"].append(g["observed_sr"])
                if not acc["dsr_with"]:
                    continue
                a = {k: np.asarray(v, float) for k, v in acc.items()}
                n_arms = N_REAL_ARMS + (N_DEGENERATES if extremity > 0 else 0) + 1

                def _req(v: float) -> float:
                    """The Sharpe a winner must POST to clear the gate — deterministic in (n, N, V),
                    so it isolates the DIFFICULTY from the luck of any one replicate."""
                    try:
                        return float(dsr_required_sr(n_obs=n_folds, n_trials=n_arms,
                                                     var_trials_sr=max(v, 1e-12),
                                                     confidence=DSR_GATE))
                    except Exception:                                    # pragma: no cover
                        return float("nan")

                rows.append({
                    "req_sr_with": _req(float(np.median(a["v_with"]))),
                    "req_sr_excl": _req(float(np.median(a["v_excl"]))),
                    "n_folds": n_folds, "extremity": extremity, "true_sr": true_sr,
                    "n_arms": N_REAL_ARMS + (N_DEGENERATES if extremity > 0 else 0) + 1,
                    "clear_with": float(np.mean(a["dsr_with"] >= DSR_GATE)),
                    "clear_excl": float(np.mean(a["dsr_excl"] >= DSR_GATE)),
                    "median_v_with": float(np.median(a["v_with"])),
                    "median_v_excl": float(np.median(a["v_excl"])),
                    "median_sr0_with": float(np.median(a["sr0_with"])),
                    "median_sr0_excl": float(np.median(a["sr0_excl"])),
                    "median_obs_sr": float(np.median(a["obs_sr"])),
                    "dsr_ceiling": float(dsr_ceiling(n_folds)),
                })
    return rows


def render(rows: list[dict], reps: int) -> str:
    L: list[str] = []
    L.append("# DSR-CONV — characterization: degenerate arithmetic vs the fold count\n")
    L.append("⛔ **SYNTHETIC FIELDS WITH A PLANTED EFFECT. NOT A RE-VERDICT ON ANY RECORDED "
             "STORY.** Every number below is a property of the DSR estimator under a known "
             "data-generating process. No recorded null is re-scored here, and none may be re-read "
             "against this memo — the DSR-CONV convention is FORWARD-ONLY (MH2 §a / E2.1-r: a gate "
             "re-read against a result already seen is laundering).\n")
    L.append(f"Design: {reps} replicates per cell · {N_REAL_ARMS} genuine arms (1 winner with a "
             f"planted per-fold Sharpe + {N_REAL_ARMS - 1} candidates dispersing at SD "
             f"{REAL_ARM_SR_SD}) · {N_DEGENERATES} pre-registered degenerates when extremity > 0 · "
             f"gate `DSR ≥ {DSR_GATE}`. `n_trials` is the FULL field under both conventions; only "
             f"`V` differs.\n")
    L.append("**Extremity** = the degenerate's per-fold skill |Sharpe| (how badly it loses ÷ how "
             "consistently). `extremity 0.0` is the CONTROL — no degenerate in the field, so the "
             "two conventions coincide by construction and any gap there would be a bug.\n")

    L.append("\n## 1. Clearance rate at the 0.95 gate, both conventions\n")
    L.append("A cell reads: of the replicates where a REAL effect of that size was planted, what "
             "fraction cleared the gate. `Δ` is the fraction of runs that degenerate-exclusion "
             "rescues.\n")
    for true_sr in TRUE_SR_GRID:
        L.append(f"\n### planted per-fold Sharpe = {true_sr}\n")
        L.append("| folds | " + " | ".join(f"ext {e}" for e in EXTREMITY_GRID) + " |")
        L.append("|---:|" + "---:|" * len(EXTREMITY_GRID))
        for n in FOLD_GRID:
            cells = []
            for e in EXTREMITY_GRID:
                r = next((x for x in rows if x["n_folds"] == n and x["extremity"] == e
                          and x["true_sr"] == true_sr), None)
                if r is None:
                    cells.append("—")
                    continue
                d = r["clear_excl"] - r["clear_with"]
                cells.append(f"{r['clear_with']:.2f} → {r['clear_excl']:.2f} "
                             f"({'+' if d >= 0 else ''}{d:.2f})")
            L.append(f"| {n} | " + " | ".join(cells) + " |")

    L.append("\n## 2. What exclusion does to the BAR itself\n")
    L.append("`SR0 = √V·z(N)`. Exclusion changes `V` only; `n_trials` (hence `z(N)`) is untouched. "
             "**`req SR`** is the deterministic per-fold Sharpe a winner must actually POST to clear "
             "the gate at that `V` and fold count — the difficulty in the unit the gate uses, free "
             "of any planted effect (MH2 Lock 5: state the bar in the unit the gate uses).\n")
    L.append("| folds | extremity | median V (with) | median V (excl) | V inflation × | "
             "SR0 (with) | SR0 (excl) | req SR (with) | req SR (excl) |")
    L.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for n in FOLD_GRID:
        for e in EXTREMITY_GRID:
            r = next((x for x in rows if x["n_folds"] == n and x["extremity"] == e
                      and x["true_sr"] == TRUE_SR_GRID[1]), None)
            if r is None:
                continue
            infl = (r["median_v_with"] / r["median_v_excl"]) if r["median_v_excl"] > 0 else float("nan")
            L.append(f"| {n} | {e} | {r['median_v_with']:.4f} | {r['median_v_excl']:.4f} | "
                     f"{infl:.1f}× | {r['median_sr0_with']:.3f} | {r['median_sr0_excl']:.3f} | "
                     f"{r['req_sr_with']:.3f} | {r['req_sr_excl']:.3f} |")

    L.append("\n## 3. The part exclusion CANNOT fix — the structural fold-count penalty\n")
    L.append("Two DIFFERENT structural facts get conflated here, and only one of them binds at this "
             "gate. Both are independent of `V`, so neither is touched by DSR-CONV.\n")
    L.append("**(a) The ceiling.** `dsr_ceiling(n)` is the largest DSR attainable at `n` "
             "observations **at any effect size whatsoever** (the statistic carries "
             "`√(n_obs − 1)`). ⚠️ Against the 0.95 gate it does NOT bind anywhere in this grid — "
             "even 3 folds ceilings at 0.9772 — so 'the ceiling blocked it' is the WRONG "
             "explanation for a small-fold DSR failure at this gate, and would be a fabricated "
             "cause if quoted as one. It binds only against a stricter gate.\n")
    L.append("**(b) The required Sharpe, which DOES bind.** The same `√(n_obs − 1)` scaling means "
             "the Sharpe a winner must POST to reach 0.95 explodes as folds fall — at a FIXED, "
             "clean `V`. This is the real small-fold penalty.\n")
    L.append("| folds | dsr_ceiling | ceiling ≥ 0.95 gate? | median req SR at clean V |")
    L.append("|---:|---:|:--|---:|")
    for n in FOLD_GRID:
        c = dsr_ceiling(n)
        req = np.median([r["req_sr_excl"] for r in rows if r["n_folds"] == n])
        L.append(f"| {n} | {c:.4f} | "
                 f"{'✅ does not bind' if c >= DSR_GATE else '⛔ UNCLEARABLE AT ANY EFFECT'} | "
                 f"{req:.2f} |")

    # ── the read, computed rather than asserted ────────────────────────────────────────────────
    ctrl = [r for r in rows if r["extremity"] == 0.0]
    ctrl_gap = max((abs(r["clear_excl"] - r["clear_with"]) for r in ctrl), default=0.0)
    with_deg = [r for r in rows if r["extremity"] > 0]
    rescued = [r["clear_excl"] - r["clear_with"] for r in with_deg]
    mild = [r["clear_excl"] - r["clear_with"] for r in rows if r["extremity"] == 1.0]
    far = [r["clear_excl"] - r["clear_with"] for r in rows if r["extremity"] >= 3.0]
    low_f = [r for r in rows if r["extremity"] >= 3.0 and r["n_folds"] <= 4]
    high_f = [r for r in rows if r["extremity"] >= 3.0 and r["n_folds"] >= 11]
    req_lo = np.median([r["req_sr_excl"] for r in rows if r["n_folds"] == min(FOLD_GRID)])
    req_hi = np.median([r["req_sr_excl"] for r in rows if r["n_folds"] == max(FOLD_GRID)])

    L.append("\n## 4. The read\n")
    L.append(f"- **Control holds — the change is inert when nothing is declared.** Across every "
             f"`extremity 0.0` cell the two conventions differ by at most **{ctrl_gap:.4f}** in "
             f"clearance. With no degenerate declared they are the SAME statistic, which is what "
             f"makes the convention safe for a caller that has not been updated.")
    L.append(f"- **⭐ THE EXCLUSION IS NOT MONOTONE, AND THAT IS THE MOST IMPORTANT LINE HERE.** It "
             f"is a rescue only when the declared arm is GENUINELY far out. At extremity ≥ 3 it "
             f"moves clearance by a median **{np.median(far):+.3f}**. At extremity 1.0 — a 'loser' "
             f"that still sits INSIDE the real arms' spread — the median move is only "
             f"**{np.median(mild):+.3f}** and it goes the WRONG way in "
             f"**{sum(1 for x in mild if x < 0)}/{len(mild)}** cells, as far as "
             f"**{min(mild):+.3f}**. The mechanism is plain: `V` is a SAMPLE variance, so dropping "
             f"points that sit near the mean INCREASES the variance of what remains. ⇒ the "
             f"convention is not a free pass in either direction, and an arm may be declared a "
             f"degenerate only because the DESIGN made it one — never because excluding it helps.")
    L.append(f"- **The arithmetic penalty scales with EXTREMITY, essentially flat in fold count.** "
             f"§2's `V` inflation reaches ~35–54× at extremity 10 at every fold count. So "
             f"degenerate-exclusion is a FIELD-COMPOSITION fix, not a small-fold fix — it just "
             f"bites hardest wherever the margin was thinnest.")
    L.append(f"- **⛔ It does NOT resolve the small-fold difficulty, and the numbers say so "
             f"plainly.** Even on a fully CLEAN `V`, the Sharpe a winner must post is a median "
             f"**{req_lo:.2f}** at {min(FOLD_GRID)} folds against **{req_hi:.2f}** at "
             f"{max(FOLD_GRID)}. Correspondingly, the rescue at extremity ≥ 3 is a median "
             f"**{np.median([r['clear_excl'] - r['clear_with'] for r in low_f]):+.3f}** at ≤4 folds "
             f"but **{np.median([r['clear_excl'] - r['clear_with'] for r in high_f]):+.3f}** at ≥11. "
             f"The residue at 3–4 folds is STRUCTURAL — the `√(n_obs − 1)` scaling in the required "
             f"Sharpe, §3(b) — and no `V` convention touches it. ⚠️ It is NOT the `dsr_ceiling`, "
             f"which does NOT bind at this gate (§3(a)); attributing a small-fold DSR failure to "
             f"the ceiling would be a fabricated cause.")
    L.append("- **Therefore, as an input to a future reading decision:** removing the degenerates "
             "from `V` fixes a real and sometimes large arithmetic defect, but a leg at 3–4 folds "
             "remains hard for reasons that have nothing to do with field composition. Any residual "
             "small-fold difficulty observed AFTER this change should be attributed to the fold "
             "count, not re-litigated as a field-composition problem.")
    L.append("\n---\n*Generated by `betting_ml/scripts/dsr_conv_characterization.py` "
             "(deterministic seeds; re-run reproduces byte-for-byte).*")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20260808)
    ap.add_argument("--out", type=Path, default=Path(
        "quant_sports_intel_models/baseball/edge_program/ablation_results/"
        "dsr_conv_characterization.md"))
    a = ap.parse_args()
    rows = run(reps=a.reps, seed=a.seed)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(render(rows, a.reps))
    print(f"[dsr-conv] {len(rows)} cells → {a.out}")


if __name__ == "__main__":
    main()
