# NF-INJ2c node 4 — the decisive run (DEFLATION_REFUSED)

> ⛔ `best_alpha = 0`. Nothing serves; DEPLOY-HELD; `SERVED_ARM` stays `incumbent`. Bands are READ from `nf_inj2c_margin_construction_rule.md` (node 3a, BINDING, committed before the re-measure); ⛔ none is defined here.

Generated 2026-09-05T18:53:02.582956+00:00. Primary arm **`stratified`** — FIXED by the registration, ⛔ never selected as 'the best CRPS'.

## 1. The verdict

**DEFLATION_REFUSED** — M1–M6 dominate but a binding deflation gate refuses → read against §7's control, with the lockstep check FIRST and §2.3(b)'s structural unavailability stated. The diagnostic field publishes beside it and ⛔ does not rescue it.

| measure | what | band rule | verdict |
|---|---|---|---|
| M1 | CRPS mean lift vs incumbent over the registered folds | R1 | **IMPROVES** |
| M2 | coherence violating players per fold (attribution-controlled) | R1 | **IMPROVES** |
| M3 | worst breach as a multiple of the envelope (max times_over) | R2 | **IMPROVES** |
| M4 | injury give-back as max(give_back_pct, 0) | R2 | **IMPROVES** |
| M5 | draftable-tier Spearman rho, per position | R3 | **TIES_OR_BETTER** |
| M6 | per-group interval coverage against its NF-D22 power floor | R3 | **CLEARS** |

⭐ improve-or-tie on EVERY measure and regress nowhere (node 3a §2). ⛔ An UNEVALUABLE measure is NOT a pass — a dominance claim missing a measure is not a dominance claim (NF1.7 (a)).

## 2. The deflation gates

- BINDING field (NF-INJ2c BINDING five-arm point-space field (PM ruling 2026-09-01)): DSR **0.9306** vs 0.95 · PBO **0.0** vs 0.2 (`pbo_application=field`)
- NON-BINDING DIAGNOSTIC (inherited NF-INJ2b 10-arm field): DSR **0.933** — declared in advance, publishes either way, ⛔ cannot rescue a binding refusal
- fold consistency: 7 of 7 wins vs 6 required (⛔ never the raw 0.60 rate — MH2 H8)
- field-trim 2×2: STRUCTURALLY UNAVAILABLE — `V` has exactly two members, so the only available drops are the arm under test (inadmissible outright, NF-W7h) or the sole other contributor (leaving `V` undefined at one point). Any refusal is stated A FORTIORI on the design, ⛔ never as a trimmed number (pre-registration §2.3(b)).

### The lockstep variance lever, run BEFORE any remedy is named (NF-W8-0d)

- SR **1.908** vs SR0 **0.8771** · lever closed: **False** · sign-invariant: **True**
- 2026 fold trigger publishable: **True** — a fold trigger only means anything when SR > SR0: `n` enters through √(n−1), which scales a positive gap but can never CREATE one (NF-W8-0d). Under DSR_UNREACHABLE the calendar-bound 2026 trigger is WITHHELD with this reason stated, ⛔ never published — that is the NF-D18 misleading direction.

## 3. The injected-effect positive control

⭐ Read under **pre-registration amendment 1** (PM ruling #6 D1, 2026-09-05): the instrument's badge is recorded VERBATIM and does ⛔ NOT bind; the **INJECTED leg** is the control's binding substance, and it can still FAIL the study.

- **BINDING (amendment 1 §4): PASSES**
  - the injected leg detected the planted effect (['stratified', 'feasibility_clamp'] cleared every injection-MOVABLE gate) and no declared degenerate survived either leg. ⛔ This is the control's binding substance under amendment 1 §4; the instrument's own badge ('DETECTED') is recorded verbatim beside it and does not bind.
- instrument badge (recorded, ⛔ non-binding): **DETECTED**
- amendment 1 §3 declaration applies to this badge: **False**
- blockers on the declared INVARIANT side: ['m2_coherence', 'm3_worst_times_over', 'm4_giveback', 'm6_interval_floor']; on the SENSITIVE side: ['dsr', 'fold_consistency', 'm1_crps_lift', 'm5_tier_rho']
- PLAT-CVP2 landed: **True** · PLAT-CVP3 (the advantage-removed null construction) is the CARDED true fix; this study does not wait for it

## 3b. The gitignored inputs this run was scored on

- NF1.5 pool cache: 8 file(s), newest 2026-09-01T06:38:41.765958+00:00
- NF1.9 veteran panels: 19 file(s), newest 2026-07-30T04:47:05.462910+00:00

⛔ RECORDED, ⛔ not gated. The pool cache REBUILDS itself from a live upstream when absent, with no error — so a checkout missing it is scored on a different feature vintage silently. A run is internally consistent either way; a CROSS-RUN comparison is what this makes checkable.


## 4. The node-3b baseline this run reads

- source `/Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_inj2c_dominance_baseline.json`, generated 2026-09-04T06:07:26.316035+00:00
- reproduction pin: worst **0.05000000000000071** vs 0.05 ⇒ **True**

⛔ M3, M4 and M2's BASELINE are BOARD measures READ from that report, never recomputed here — a second computation of a committed baseline is a second answer to one question.
