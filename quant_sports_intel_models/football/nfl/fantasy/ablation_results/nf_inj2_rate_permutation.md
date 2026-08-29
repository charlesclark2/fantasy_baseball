# NF-INJ2 — permute the per-game RATE, not the season POINT

**VERDICT: CONSTRAINT_REFUSED** — the pre-registered ORDERING constraint is breached at QB by a margin distinguishable from noise — §6 branch 3: do not ship. `best_alpha = 0`. Generated 2026-08-22T05:24:55Z in 37.4s.

> Pre-registration: `nf_inj1_preregistration.md` (committed during NF-INJ1, before any arm was scored; PM-funded 2026-08-21). ⛔ Not edited by this run — E2.1-r.

> 🔒 DEPLOY-HELD: `nf_inj2_rate_permutation.SERVED_ARM` is still `"incumbent"`. Nothing here serves until the PM records a disposition.


## 1. The field, as declared

Folds **2019–2025** (7), inherited from NF1.5 stage-1 `score_from` — not chosen here. Declared field **6** arms + the matched foil `rate_permute_games_frozen`; pre-registered degenerates `mvp1_null`, `random_order`.

| arm | CRPS | MAE | cov80 | ρ (pooled) | coherence violations | folds beating incumbent |
|---|---|---|---|---|---|---|
| oracle_incumbent | 18.3882 | 23.0150 | 0.9811 | 0.9746 | 147 | 7 |
| oracle_feasibility_clamp | 18.5120 | 23.4059 | 0.9796 | 0.9681 | 14 | 7 |
| oracle_stratified | 20.2093 | 26.7093 | 0.9718 | 0.9113 | 71 | 7 |
| oracle_rate_permute | 21.4770 | 29.1967 | 0.9629 | 0.8707 | 3 | 7 |
| stratified | 26.0616 | 37.1693 | 0.9026 | 0.7004 | 60 | 7 |
| rate_permute | 26.1990 | 37.6163 | 0.9065 | 0.7095 | 2 | 5 |
| feasibility_clamp | 26.3577 | 37.4578 | 0.8950 | 0.6536 | 5 | 5 |
| incumbent | 26.5117 | 37.6944 | 0.8953 | 0.6506 | 134 | 0 |
| mvp1_null | 27.5102 | 39.5993 | 0.8923 | 0.6902 | 0 | 1 |
| rate_permute_games_frozen | 33.2956 | 48.7931 | 0.8789 | 0.6554 | 249 | 0 |
| random_order | 45.3611 | 62.8947 | 0.7452 | 0.2525 | 253 | 0 |


⛔ **CRPS selects. MAE never does** — the target is skewed and the low-availability cohort is exactly where the conditional median sits near the floor (NF-D11 / NF-D14). It is disclosed, not used.

⚠️ **The coherence column is a PRECONDITION, not a discriminator.** The pre-registration says so in advance: `rate_permute` satisfies it by construction, so it must not be presented as evidence that it beat anything. It is reported for EVERY arm — including the degenerates — because a constraint a degenerate satisfies is fine (the metric then eliminates it), while a criterion a degenerate WINS would be fatal (NF1.8).


## 2. The primary vs the incumbent

Mean CRPS lift **0.3126** over 7 folds, winning **5/7**. Tie band ±0.2003 (the per-fold SE of the winner's own lift — a dispersion quantity fixed by the design, not a threshold chosen to reach a verdict).

| fold | lift |
|---|---|
| 2019 | -0.1819 |
| 2020 | -0.3838 |
| 2021 | 0.1969 |
| 2022 | 0.5471 |
| 2023 | 0.0920 |
| 2024 | 0.9930 |
| 2025 | 0.9252 |


### Matched foil — is the mechanism what we say it is?

`rate_permute_games_frozen` mean lift **-6.7839** vs the primary's **0.3126**.

the matched foil (`rate_permute_games_frozen`) LOSES while the primary wins ⇒ the lift is the PER-PLAYER AVAILABILITY channel, which is the stated mechanism (NF-D15 g′)


## 3. Gates

| gate | value | bar | verdict |
|---|---|---|---|
| PBO (eligible = the declared field) | 0.0286 | < 0.2 | True |
| DSR (degenerates ∉ V, n_trials = declared) | 0.1081 | ≥ 0.95 | False |
| DSR (whole field, reported beside it) | 0.0000 | ≥ 0.95 | — |
| fold consistency | 5 | ≥ 6 wins | False |
| BH-FDR across positions | {"QB": false, "RB": false, "WR": false, "TE": true} | q = 0.1 | False |
| ordering not regressed (draftable tier) | {"QB": [0.3504, 0.4807], "RB": [0.6485, 0.6564], "WR": [0.5691, 0.5741], "TE": [0.5292, 0.5105]} | ρ ≥ incumbent | False |
| ordering not regressed (full population, disclosed) | {"QB": [0.7075, 0.6497], "RB": [0.737, 0.7046], "WR": [0.7186, 0.6887], "TE": [0.675, 0.5593]} | ρ ≥ incumbent | True |
| coherence restored | 2 | = 0 | False |


NF1.8 triad beside PBO — a rank statistic alone cannot tell an unstable pick from a tied one: flip distribution `{"stratified": 0.7714, "rate_permute": 0.2286}`, Bailey performance degradation **0.000%**, contender spread **0.4501** against a whole-field spread of **19.2995** (the whole-field figure includes this field's own declared degenerates, so it measures the degenerates — MH2/NF1.8).


Trial Sharpes: `{"incumbent": 0.0, "rate_permute": 0.59, "stratified": 2.0033, "feasibility_clamp": 0.8688, "mvp1_null": -1.2977, "random_order": -10.8856}`.


## 4. Anchors

- Degenerates scored every run and READ, not reasoned about: `{"mvp1_null": 27.5102, "random_order": 45.3611}` against the winner's **26.1990** ⇒ every degenerate loses: **True**.

- Own-form peeking ceiling (one PER FORM — the forms nest, so a single field-wide ceiling would veto a legitimately better nested form, NF-D16 g‴): **21.4770**, gap **4.7220**, respected **True**. ACTIVE


## 5. Could the mechanism act? (NF-D20)

A fold on which the learner has no edge over MVP-1's own ordering is UNINFORMATIVE about which permutation rule is better — no rule can improve a board there. Counted, never used to drop a fold from the registered window.

| fold | edge (draftable tier) | edge (full population) | mechanism can act |
|---|---|---|---|
| 2019 | 0.2018 | -0.0595 | True |
| 2020 | 0.2588 | -0.0332 | True |
| 2021 | 0.1640 | -0.0355 | True |
| 2022 | 0.1642 | -0.0252 | True |
| 2023 | 0.1459 | -0.0343 | True |
| 2024 | 0.0685 | -0.0171 | True |
| 2025 | 0.1479 | -0.1063 | True |


⭐ The two readings can disagree, and on this population they do: the learner's edge lives on the DRAFTABLE TIER (the metric NF1.5 was selected on), not over the full veteran population. That is worth knowing before reading any wide-window sensitivity — on a season where the ordering mechanism has no edge, no permutation rule can improve the board and the fold is uninformative about which rule is better.


## 6. The 2026 board — the CURRENT served vintage

Built off `generated_at` **2026-08-21T05:22:20.99191**, the vintage on the wire. Injury-capped cohort n=**26** (`load_forward_roster_status(2026).proj_status ∈ ['NFI', 'PUP', 'RES', 'SUS'] — the cap's own input`).


**Reproduction pin:** the incumbent arm rebuilt through this story's code matches the SERVED artifact to **2.56e-13** over 794 rows (tolerance 1e-09) ⇒ **True**. the incumbent arm rebuilt through this story's code vs the SERVED 2026 artifact — if this does not hold, every arm delta is measured against a board nobody is served (the CLV / NF-INJ1 stale-vintage trap)


⭐ **ATTRIBUTION BY CONTROL, not by scope declaration.** `mvp1_null` is the ordering step switched entirely OFF, so any violation it ALSO produces is a defect of the underlying MVP-1 board that no permutation rule can be causing. The primary leaves **1** raw violating row(s), of which **0** are attributable to it. The residual is `MEN516487|Fernando Mendoza`, a ROOKIE produced by `rookie_projection`'s own `fp_target` ↔ slot-bucket-games decoupling — a different code path that the pre-registration puts explicitly OUT OF SCOPE (§5; NF-INJ1 §2.2/§5c).

| arm | impossible rows | …attributable | injury give-back % | median point ratio | n scaled UP | n scaled DOWN | ρ(games, ratio) | clamp hi/lo |
|---|---|---|---|---|---|---|---|---|
| incumbent | 10 | 9 | 33.9600 | 1.2280 | 18 | 6 | -0.2120 | 7/24 |
| rate_permute | 1 | 0 | -11.9900 | 0.9293 | 7 | 18 | 0.2070 | 1/7 |
| stratified | 8 | 7 | 6.8800 | 1.0007 | 13 | 10 | -0.0609 | 1/7 |
| feasibility_clamp | 4 | 3 | 33.9600 | 1.2280 | 18 | 6 | -0.2085 | 5/24 |
| mvp1_null | 1 | 0 | -0.0000 | 1.0000 | 0 | 0 | — | 0/0 |
| random_order | 35 | 34 | 20.3700 | 1.5249 | 16 | 9 | -0.5844 | 138/149 |
| rate_permute_games_frozen | 31 | 30 | 40.9000 | 1.6410 | 21 | 4 | -0.8144 | 31/8 |


⚠️ ρ(games, ratio) → ~0 is a PRECONDITION the primary satisfies by construction, ⛔ not a discriminator between arms (pre-registration §1).


### The §4 placement read

BUILD FRAME, ranked by PPR — ⛔ NOT the served per-config VOR read (NF-TR2b). Best rookie overall rank **13**; cap breach **False**. Cross-position movement (top 100): `{"n_board": 794, "median_abs_rank_move": 26.0, "p90_abs_rank_move": 142.1, "max_abs_rank_move": 334.0, "n_moved": 775, "top100_churn": 7, "top100_membership_stable": false, "top10_order_stable": false}`. Within-position movement: `{"max_rank_move_by_pos": {"QB": 27.0, "RB": 81.0, "WR": 131.0, "TE": 78.0}, "worst_rank_move": 131.0, "within_position_rho": {"QB": 0.9742852104693049, "RB": 0.9001039126722017, "WR": 0.9311167545057176, "TE": 0.914526657751235}}`.

⚠️ The NF-W8-0 VOR "shield" does NOT excuse this read: the shield holds for an ADDITIVE per-position level shift, whose effect a position's own replacement level absorbs. This correction re-levels each row by a RATIO, so it can reorder across positions — and under the two SUPERFLEX configs QB is cross-pooled, which is the position this arm moves most (NF-TR2b).


## 6b. WHY the ordering moved where it did — the decomposition

`rate_permute`'s served point is `assigned_rate × own_games`, so its ordering is a BLEND of the learned rank and expected games; the incumbent's IS the learned ordering exactly. So the question is how good an ordering signal expected games is, per position, on the draftable tier — a labelled DIAGNOSTIC, ⛔ never a trial (MH2.1 (a): an anchor that polices the metric must not end up setting the gate's own bar).

| signal | QB | RB | WR | TE |
|---|---|---|---|---|
| learned_score | 0.4807 | 0.6564 | 0.5741 | 0.5105 |
| expected_games_alone | 0.1609 | 0.2727 | 0.2382 | 0.3698 |
| mvp1_point | 0.2984 | 0.4726 | 0.4078 | 0.3852 |
| **observed Δ tier-ρ (arm − incumbent)** | -0.1303 | -0.0079 | -0.0050 | 0.0187 |


⭐ **The damage ranks exactly with the games signal's deficit.** Expected games is the WEAKEST ordering signal at QB and the relatively strongest at TE — and QB is the position that loses most while TE actually GAINS. Blending availability into the ordering costs precisely where availability is least informative.


⭐ **And the deeper reason, which names the successor.** NF1.5's learner is fitted on `real_fp_ppr` — a SEASON TOTAL — so it was selected to order POINTS. Handing it a per-game RATE multiset asks it a question it was never validated on, and the mismatch is largest exactly where the games spread is widest (QB: a 17-game starter beside a 1-game QB3). The coherence fix and the ordering are therefore not independently satisfiable with THIS learner: a successor that wants both should re-select the ordering learner on a per-game RATE target, rather than re-using a points-ordering learner to order rates.


## 7. Null classification

```json
"NullVerdict(state='DSR_UNREACHABLE', reason=\"`crps`: the winner's per-fold Sharpe 0.590 sits at or BELOW the 6-arm field's deflated benchmark SR0 1.093, so DSR is unreachable at ANY fold count \u2014 `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, PRE-REGISTERED field, not more seasons \u2014 and \u26d4 only if such a field was pre-registered; this is NOT a licence to re-cut a field you have already scored (MH2.7). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.\", retest_trigger='field size is NOT a lever here \u2014 even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)', folds_have=7, folds_needed=None, extra_seasons=None, max_field_size=0, detail={'n_folds': 7, 'n_arms': 6, 'observed_sr': 0.59, 'sr0': 1.0928, 'var_trials_sr': 0.7065300758333333, 'degenerates_excluded_from_v': True, 'var_trials_sr_with_degenerates': 22.52397641466667, 'v_inflation_factor_from_degenerates': 31.8797, 'declared_field_size': 6, 'declared_field_size_source': 'stated', 'field_remedy_admissible': None}, field_remedy_admissible=None)"
```


### Reading the DSR failure — and correcting the instrument

Winner per-fold Sharpe **0.5900** against the declared field's benchmark SR0 **1.0928** ⇒ **DSR_UNREACHABLE**.


The 2×2, computed as a labelled diagnostic BEFORE naming any remedy (NF-W7f): dropping the most extreme DECLARED non-degenerate arm (`stratified`, Sharpe 2.0033) collapses `V` **0.7065 → 0.1968** and moves DSR **0.1081 → 0.5130** — a large move that still does NOT reach 0.95. So field heterogeneity is a REAL contributor (a declared sibling genuinely beats the incumbent 7/7 and inflates the dispersion) and it is NOT sufficient. ⛔ `stratified` is a DECLARED arm and is NOT trimmed: you get to pre-register a family, you do not get to discover one (MH2.2).


⚠️ **TWO CORRECTIONS TO `cv_power.classify_null`'S REMEDY TEXT, applied by hand here — the Nth time this instrument has needed one downstream (CLAUDE.md already cards the shared fix):**

1. Its `reason` prescribes *"a SMALLER, PRE-REGISTERED field"* while its own `retest_trigger` says *"field size is NOT a lever here"* (`max_field_size=0`). Those contradict; the trigger is the correct half. And `field_remedy_admissible` came back **None** rather than False even though `declared_field_size=6` was passed, so the machine flag MH2.7 tells callers to read instead of the prose could not adjudicate it either.

2. Its surviving prescription — *"a lower-variance design (more rows per fold / a sharper metric)"* — is **deterministically VOID** here. The winner is itself one of the trials, so a SHARED-variance lever that scales every arm's per-fold dispersion by `c` scales every trial Sharpe by `1/c`, hence `SR0` by `1/c`, hence `SR − SR0` by `1/c`: **its SIGN is invariant** (NF-W8-0d's lockstep invariant). With `SR < SR0`, no shared-variance design change can create the positive gap. The only real levers are a DIFFERENTIAL-variance design (shrink the WINNER's dispersion, not the field's), a bigger effect, or a genuine absence.


## 8. Reading, against the pre-registration's §6

- **CONSTRAINT_REFUSED** — the pre-registered ORDERING constraint is breached at QB by a margin distinguishable from noise — §6 branch 3: do not ship.

- ⭐ **What the arm DID do, and it is not small.** On the served 2026 board it removes every veteran impossible row (**10 → 0 attributable**), turns the injury give-back from **+33.96%** into **−11.99%** — i.e. flagged players now project DOWN relative to MVP-1 rather than being marked back up — and wins the selecting metric overall (+0.3126 CRPS, 5/7 folds, PBO 0.0286). The matched foil loses by a mile and makes the give-back WORSE (+40.9%), so the mechanism is ATTRIBUTED to the per-player availability channel from both directions (NF-D15 g′).

- ⛔ **And why that is still not a ship.** The pre-registration makes the ordering a CONSTRAINT, and the arm breaches it at QB on the draftable tier by a margin distinguishable from noise. Relaxing that clause after seeing it fail is exactly the E2.1-r inversion this program has been burned by, so the gate is left to say no.

- ⚠️ **The two ordering readings DISAGREE, and both are reported.** Over the FULL veteran population the arm improves ρ at every position; on the DRAFTABLE TIER it regresses at QB. The tier is the metric NF1.5 was selected on and the one a drafter actually uses, so it binds — but a reader should know the disagreement exists rather than meet only the half that supports the verdict.

- ⭐ A TIE on the selecting metric still ships. That is written down in the pre-registration in advance, precisely so it cannot look like a post-hoc rescue: coherence is a correctness constraint the INCUMBENT FAILS, and a tie is not a reason to keep serving a stat line that is physically impossible. It is the pricing-vs-discrimination family rule, ⛔ NOT the E2.1-r inversion. It did not decide this story — the arm WON the metric and was refused on the ordering constraint instead.

- ⛔ **NO "more data" re-test trigger** is published. The binding refusal is a constraint the arm BREACHES (more folds would make a real regression MORE significant, not less), and the DSR shortfall is unreachable at any `n`. Publishing a season trigger here would be the actively-misleading direction NF-D18 warns about.


### ⚠️ A pre-registered prediction this run OVERTURNED (recorded, not edited — NF-W7f)

The pre-registration's §1 states that a successful arm drives ρ(expected games, point ratio) **to ~0 by construction**. It does NOT. Measured on the served board the incumbent's **−0.211** becomes **+0.207** — the gradient FLIPS SIGN rather than vanishing. The reason is informative: under `rate_permute` the point ratio is `r_j / r_i`, a pure ratio of per-game rates that carries no games term at all, so what remains is the LEARNER's own preference for high-availability players, no longer masked by the mechanical transfer. The pre-registration is left verbatim; this paragraph is the correction. ⚠️ It also means the gradient must not be read as "still broken, other way" — the incumbent's −0.211 is a MECHANICAL artifact of permuting a composite, the arm's +0.207 is a modelling opinion the board is entitled to hold.


(A second, smaller correction: the first cut of that same statistic reported **+0.1476** for `mvp1_null`, an arm that by construction moves no point at all. Its ratio is identically 1, so the figure was a rank correlation over floating-point noise. The reducer now refuses the row as unevaluable — NF1.7 (a).)


## 9. The DISCLOSED wide-window sensitivity (2013–2025)

Reported, ⛔ never selected on. Mean lift **-0.2975**, 5/13 folds — i.e. the arm LOSES over the wider window. The ordering mechanism could act on only **10/13** of those folds (NF-D20), and the pre-2019 seasons are exactly the ones NF1.5's own selection excluded via `score_from = 2019`. That does not rescue the arm — it bounds what the wide window can certify, and it is disclosed rather than dropped.


---

## ⚠️ ANNOTATION — added 2026-08-29 by NF-INJ2c (PM ruling D4 on NF-INJ2b). ⛔ NOTHING ABOVE IS EDITED.

> This block is a POST-HOC ANNOTATION, not output of `write_report_md`. Everything above it — the
> verdict, every figure, every table — is left exactly as the decisive run produced it (E2.1-r: a
> record is annotated, never rewritten). ⚠️ The generator would not reproduce this block, so if
> `run_nf_inj2_rate_permutation` is ever re-run the annotation must be re-appended; the ruling that
> created it is **annotate, never re-run**, so that should not arise.

**What the ruling asked to be flagged.** NF-INJ2b found a real defect in the `apply_2026` code this
story shipped: `injury_giveback(mvp1, served if served is not None else board, board, capped_ids)`
substitutes the ARM'S OWN BOARD for a missing served baseline. Under that fallback every
served-relative figure compares an arm **to itself**, so a structural zero is reported as a
measurement and "we compared against the served board" reads as a check that ran (the NF1.7 (a)
vacuity, in a baseline rather than in a guard). NF-INJ2b replaced it with a REFUSAL that names the
staging command. The concern was that this story's own `served_giveback_pct` might therefore be its
arm's number rather than the served board's.

**What the record actually establishes — measured, not assumed.** ⭐ **The fallback did NOT fire on
this run.** Two independent signatures in the committed `nf_inj2_rate_permutation.json`, both
decisive:

1. `application_2026.reproduction_pin` is PRESENT (`n=794`, worst abs diff `2.56e-13`). That block is
   written only inside `if served is not None and "incumbent" in arms:` — so `served` was a real,
   staged artifact at run time.
2. `served_giveback_pct` is **33.96 on all seven arms**, including `random_order` (own give-back
   `20.37`), `mvp1_null` (own `-0.00`) and `rate_permute_games_frozen` (own `40.90`). That is exactly
   the two-sided proof NF-INJ2b names: with a real baseline the served-relative figure is IDENTICAL
   across arms because it is a property of the SERVED BOARD, not of the arm; under the fallback each
   arm returns its own number and the seven would differ.

⇒ the `injury give-back %` column above (incumbent `+33.96`, `rate_permute` `−11.99`) is the arm's
own figure against MVP-1 and never touched the fallback, and `served_giveback_pct` is the served
board's. **The figures stand as recorded.**

**And it did not decide this verdict either way.** `CONSTRAINT_REFUSED` came from the pre-registered
ORDERING constraint at QB (draftable-tier ρ 0.481 → 0.350, BH-significant). The give-back is reported
under "what the arm DID do"; no branch of §6 reads it.

**The forward fix** is NF-INJ2b's `served_baseline()` — read the baseline from the PUBLISHED artifact
and REFUSE with the staging command named when it is absent, never fall through to a rebuild
(`run_nf_inj2b_rate_ordering.served_baseline` / `_assert_baseline_is_current`). ⚠️ Note the two
guards answer different questions: on NF-INJ2b's decisive run the freshness bar PASSED at 7.30h/48h
while the reproduction pin FAILED at 40.58 over 797 rows, because the ADP/ECR snapshot that feeds the
ordering moves intraday. A pin over a live-snapshot-fed surface must bind a CAPTURED artifact, never
a re-pull (PM ruling D3, 2026-08-29).

**One figure above that a later measurement DOES bear on, recorded here rather than edited.** §8
attributes NF-INJ2's refusal to a MECHANISM: *"NF1.5's ordering learner is fitted on `real_fp_ppr`, a
season TOTAL, so it was selected to order POINTS"*, and NF-INJ2b was funded to act on exactly that.
NF-INJ2b's matched pair isolating the FIT TARGET measured **−0.0873 CRPS, 1/7 folds, p=0.977** — the
target re-fit is mildly HARMFUL — while the pair isolating the ASSIGNMENT rule in point space read
**+0.4452, 7/7, p=0.0009**. ⇒ **the stated mechanism is refuted by measurement; the lever is the
assignment rule, not the fit target.** The VERDICT is untouched (`CONSTRAINT_REFUSED` stands, and the
mechanism claim was never what refused the arm), and §8 is left verbatim — this paragraph is the
correction, in the shape §8's own "a pre-registered prediction this run OVERTURNED" block uses.
