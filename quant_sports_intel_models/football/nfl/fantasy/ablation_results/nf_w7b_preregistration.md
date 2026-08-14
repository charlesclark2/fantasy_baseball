# NF-W7b pre-registration — DST dependence successor: joint/copula draw over the co-moving component legs

**Committed BEFORE any full-run scoring** (the §0.5 discipline). Everything below lives as
constants in `kdst_weekly_joint.py` / `joint_draw.py`; the runner `run_nf_w7b_dst_joint.py`
READS them (NF-D16). A smoke run (2 folds, artifacts suffixed `_smoke`) may be used to prove the
code path AND to record the pre-declared arm-movability check (§5) — no verdict, and no constant
may change in response to a smoke score after this file is committed.

⚖️ Edge-independent projection product — `best_alpha` N/A, **deploy-held**. Research-only: no
changelog entry.

## 0. The thesis under test (not assumed)

NF-W7's assembled `dst_points` won the score contest against all three foils (+0.0338 CRPS vs
the best, CI95 [+0.0094, +0.0582], DSR 0.961, 7/8 folds) and was **CONSTRAINT_REFUSED** by the
pre-registered coverage(80) floor alone: 0.7603 vs 0.80 at n=2,174 (≈4.6 binomial SE). The
recorded mechanism is the DECLARED independence simplification firing: the component banks
(sacks / INT / FR / rares / PA-bucket) co-move — a dominant defensive day produces counting
stats AND a low points-allowed tier together — so an independent draw under-disperses the
assembled sum. The thesis here: adding a **Gaussian-copula joint draw** over the SAME frozen
marginals restores the missing dispersion, clearing the floor while keeping the score win. A
null is a legitimate published outcome naming exactly which dependence structures were tried and
how they fell short.

## 1. Binding constraints (inherited, unchanged)

- ⛔ **The component marginals are NOT refit.** The assembly consumes NF-W7's Layer-A
  score-best DST arms verbatim (`FROZEN_DST_WINNERS`: def_sacks/def_int/def_fumble_rec =
  `negbin_glm`, dst_td/def_blocked_kick = `eb_pois`, def_safety = `hurdle_pois`, pa_bucket =
  `ordered_logit`), asserted against the committed NF-W7 record at load. The copula layer
  provably changes only the joint law: each leg's values are still inverse-CDF draws of a
  marginally-U(0,1) variate, and at Σ=I the draw is BYTE-IDENTICAL to the independent draw
  (common random numbers — every arm transforms the same base normals).
- ⛔ **The coverage(80) floor is NF-W7's verbatim** (0.80, blocking beyond 3 binomial SE) — it
  may not move in either direction (NF-D18 / E2.1-r / NF1.8).
- **Frames, folds, PIT gate, foils, scoring**: the NF-W7 DST frame + the NF-W1 8-fold axis
  (2022H1…2025H2, purge 2) + the fail-closed per-week PIT gate + the same three foils
  (`foil_climatology` / `foil_board_eb` / `foil_direct`) + `crps_q199` on the dense grid with
  the inherited MARGIN tail discipline (parametric integer-support banks; 9-knot learners
  exponential-tail-extended, never flat). NF-W0 constraints (leak-clean PIT frame, ⛔ no
  fillna(0), provenance-checkable features, no markets/weather) are inherited through the reused
  frame builder unchanged. The NF-W2d two-era read stays REPORT-ONLY (2025 fold deltas).

## 2. The declared real-arm family (4 arms — a hypothesis-driven magnitude/structure grid)

All four arms share one mechanism (Gaussian copula over the frozen marginals) and differ ONLY in
how Σ is estimated — the family brackets the dependence axis, with the anchors at its endpoints
(independent = 0×, comonotone = 1.0):

| arm | Σ̂ estimator |
|---|---|
| `joint_rankcorr` | Pearson correlation of latent z-scores Φ⁻¹(randomized PIT) of each realized component outcome under the frozen marginals' **in-sample TRAIN predictions** — the model-RESIDUAL scale (the co-movement the marginals' features do not already explain). The card's "empirical rank correlation across component residuals". |
| `joint_factor` | The nearest ONE-FACTOR structure Σ = λλᵀ + diag(1−λ²) of that Σ̂ (principal eigenpair, signs free) — the shared-latent game-state reading (opponent quality / script / pace as the single common factor). |
| `joint_raw` | Spearman rank correlation of the RAW outcomes (ties midranked), mapped 2·sin(π·ρ_s/6) — the unconditional scale, an upper-ish read that includes feature-explained co-movement. |
| `joint_double` | `joint_rankcorr`'s Σ̂ with off-diagonals ×2 (clipped ±0.99, PSD-repaired) — the ATTENUATION PROBE: randomized PITs on zero-heavy discrete margins bias ρ̂ toward 0 by a factor with no closed form (the zero atom's span is filled with uniform noise), so the magnitude axis must be probed. Registered as a REAL arm (NF-D20: an under-correcting estimator must not be discoverable only through an ineligible anchor). |

Estimation is per fold, TRAIN-side only (causal); an estimate over fewer than 50 complete rows
REFUSES (raises) rather than silently becoming identity (NF1.7 (a)). Selection = argmin mean
`crps_q199` among the four arms; the coverage floor GATES the selected arm and never selects
(NF1.8 — a floor is a constraint, not a target).

## 3. Anchors (all scored, every run)

- `assembled_indep` — **the refused NF-W7 incumbent**, re-scored in this harness (Σ=I). Its
  roles: (a) the straddle control — its pooled cov(80) shortfall must REPRODUCE as blocking
  (`incumbent_refusal_reproduces`), or the harness does not see the defect it claims to fix and
  no credit may be claimed; (b) the baseline the winner must beat on coverage
  (`beats_indep_on_coverage` — the card's requirement). Report-only reproduction references:
  NF-W7 recorded CRPS 2.6975 / cov(80) 0.7603 (a different RNG stream; tolerance is a
  report-only note, never a gate).
- `assembled_comonotone` — **the over-correlated degenerate**: ONE shared uniform drives every
  leg, with the PA leg taking 1−u so everything co-moves in the POINTS direction. It must LOSE
  the score contest (it sits in the degenerate set for `degenerates_lose`); it is EXPECTED to
  satisfy the coverage floor trivially — a constraint a degenerate satisfies is fine, the metric
  eliminates it (NF1.8); its coverage is scored and reported to prove the floor was never a
  selection criterion.
- `nihilist_zero`, `zero_width`, `max_width` — NF-W7's Layer-B degenerates, unchanged.
- `permuted_direct` — the direct-form control with labels permuted within week; must lose, and
  its lift must be non-significant (failing closed on a None p).
- `oracle__<arm>` (marginals refit on the test block + Σ estimated on the test block, per the
  arm's own estimator) and `matched_n__<arm>` capacity controls, for each of the 4 arms — the
  floor enforced AT MATCHED n (NF1.9 (f) / NF-D16 (g‴)). Foils carry their own-form oracles.

## 4. Gate (ship rule) — all clauses green ⇒ SHIP

Statistical: beats the BEST foil on mean fold CRPS ∧ fold clause (`fold_consistency_clause(8)` ⇒
6/8) ∧ PBO < 0.20 over the 7-config eligible field (4 arms + 3 foils; anchors never — MH2.1 (a))
∧ DSR ≥ 0.95 over the 4-arm declared family (trial SRs from real arms only) ∧ BH-FDR q=0.10 over
the declared single-member downstream family {dst_points_joint} ∧ the coverage(80) floor on the
SELECTED arm (0.80, blocking beyond 3 SE).

Anchor/registration: degenerates lose (incl. comonotone) ∧ permutation behaves ∧ oracle floors
at matched n ∧ the three DEPENDENCE clauses: `incumbent_refusal_reproduces` ∧
`dependence_moves_coverage` (cov(comonotone) > cov(indep) — the knob's full range moves the
gated statistic) ∧ `beats_indep_on_coverage` (cov(winner) > cov(indep)).

Null classification: a refusal whose ONLY red clause is the coverage floor →
**CONSTRAINT_REFUSED** via the shared `KW.coverage_constraint_refusal` branch with THIS story's
mechanism prose ("the registered dependence structures UNDER-CORRECT…") — never NF-W7's
independence prose, which would be false of a joint arm, and never POWER_LIMITED (NF-D18: the
reason derives its CI wording). A refusal resting only on anchor/registration clauses with every
statistical gate green → CONSTRAINT_REFUSED with the failing clauses named. Anything else →
`cv_power.classify_null` at the honest n_arms=4, with `flag_unsafe_field_shrink` applied and the
instrument verdict recorded beside any hand correction.

## 5. Arm-movability (NF-MARGIN2 / NF-D20 — proven BEFORE the coverage gate is trusted)

A statistic the arm cannot move is décor, not a gate. Two halves, both pre-declared:

- **Analytic**: Var(Σ wᵢXᵢ) = (w∘σ)ᵀ Σ (w∘σ) is strictly increasing in every off-diagonal ρᵢⱼ
  with wᵢσᵢwⱼσⱼ > 0 — the dependence knob changes the assembled sum's dispersion, hence its
  central-interval coverage. (Unit-tested via `weighted_sum_variance` on synthetic banks.)
- **Measured**: the smoke run must show pooled cov(80)(comonotone) > cov(80)(indep) on its 2
  folds before the full run is launched; the full run re-records the same check as the
  `dependence_moves_coverage` gate clause. The smoke result is appended to §7 of this file
  verbatim (a recorded check result — no constant changes).

## 6. Power, checked in advance

Identical design to NF-W7's Layer B except the arm count: at 8 folds the fold clause is
attainable (6/8); PBO is evaluable (7-config eligible field); the sign floor 2⁻⁸ ≈ 0.0039 < the
0.10 BH cutoff; `dsr_ceiling(8) = 0.9999` vs the 0.95 gate, now with a real 4-arm deflation
field (near-clone arms ⇒ a small V by construction — the contender-set reading is reported
beside the whole-field figure per MH2.5). No gate is structurally unattainable ⇒ any null is a
finding. The three dependence clauses are evaluable by construction (indep and comonotone are
scored every run).

## 7. What is deliberately OUT of scope

Refitting or re-selecting any component marginal (⛔ binding); t/vine/non-Gaussian copulas and
week-level dependence regimes (a successor's magnitude/shape axis if THIS family under-corrects
— the refusal prose points there); the K side (shipped in NF-W7, untouched); YA tiers (not in
the modal default, unchanged); any serving/deploy wiring. The joint-draw machinery
(`joint_draw.py`) is deliberately story-agnostic — the NF-W10 same-game / team-total / stack
substrate.

---

### §7-addendum — smoke movability result (recorded before the full run)

Smoke run 2026-08-14 (2 folds 2025H1+2025H2, n=544, runtime 106.4s; artifacts
`nf_w7b_dst_joint_smoke.{json,md}`). Pooled cov(80): `assembled_indep` **0.7629** ·
`joint_rankcorr` 0.8125 · `joint_factor` 0.8107 · `joint_raw` 0.8217 · `joint_double` 0.8548 ·
`assembled_comonotone` **0.9467**. **`dependence_moves_coverage` = TRUE** (comonotone > indep by
+0.184) — the knob provably moves the gated statistic; the arm-movability requirement of §5 is
met and the coverage gate stands as registered. (`incumbent_refusal_reproduces` read False at
smoke-n only because 3·SE(544) = 0.051 exceeds the 0.037 shortfall — the blocking read is the
full-run n≈2,174 check, exactly why the clause is registered there.) No constant changed after
this smoke; the smoke's leaderboard carries no verdict by design.
