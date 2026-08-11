# NF-W5 pre-registration — opportunity allocation on the JOINT gate

**Committed BEFORE the full run.** Constants live in `opportunity_allocation.py`; the runner
(`run_nf_w5_opportunity_allocation.py`) reads them (NF-D16 discipline). This file is the
narrative copy.

> ⚖️ Edge-independent projection product — `best_alpha = 0`, **deploy-held**: this story promotes
> nothing, publishes nothing, retrains nothing. Serving is NF-W8 / NF-C6 Ph2.

## 1. What NF-W5 is NOT, and what it is

Both predecessor LEVEL channels are measured inert against the injury-aware champion on the
marginal per-player CRPS gate:

- **NF-W3 (environment):** GENUINE_ABSENCE / POWER_LIMITED at every position; the realized-
  environment oracle ceiling is **2.0–3.1% of champion CRPS** — real but small, and the modeled
  environment captures 2–4% of it.
- **NF-W4 (availability):** GENUINE_ABSENCE ×3 / POWER_LIMITED (TE); the realized-availability
  oracle ceiling is **8.1–27.8% of champion CRPS** — large, but the pregame-forecastable slice is
  already priced into the champion; the remainder is game-day activation (banned as a feature
  because it IS the answer) and realized in-game share (unknowable pregame).

⛔ NF-W5 therefore does NOT build a better pregame point forecast of opportunity conditioned on
projected environment/availability — that inherits two measured-dead channels. ⭐ NF-W5 measures
the one place the assembled projection can still gain: the **correlation structure** a shared team
play budget creates — teammates share one play budget, shares sum to 1, so opportunity is a
COMPOSITIONAL joint object. A marginal per-player gate is structurally blind to it; the v3 doc's
own justification for the simulator (§9 / §9.1 / §10.1A) rests on it. NF-W5 is the decision gate
for whether NF-W8 (the simulator, the big build) is worth buying.

## 2. The Sklar split — why this design isolates the correlation channel

A joint predictive = per-player marginals ⊗ a copula. NF-W3/W4 measured the MARGINAL channel.
NF-W5 pins the marginals to the **injury-aware champion** (the NF-W2b/W2d certified per-position
winners over the NF-W1 `lgbm_hurdle`, pinned to the committed W2d artifact, refit per fold) and
varies ONLY the copula. Every construction in the field shares byte-identical per-player marginal
quantile banks; a **marginal-identity guard** asserts the pooled per-player sample CRPS spread
across constructions is inside MC tolerance every fold (this is also §10.1A's "must not degrade
marginal CRPS" clause, made structural).

## 3. The joint object

- **Grain:** team-week — the vector of ALL modeled player-weeks (the NF-W2d two-era matrix,
  ex-bye, positions QB/RB/WR/TE, zeros retained) for one (team, global week) in a TEST fold.
- Teams with **K < 2** modeled players carry no joint structure: excluded and COUNTED, never
  silently dropped. A row-conservation assert requires kept + excluded == fold test rows.
- Target vector: `fantasy_points` (PPR, the frame's certified label).
- ⛔ No pbp source, no new features, no new joins of any kind — the only inputs are the W2d
  matrix and the champion's own predictive quantiles. The NF-W3 franchise-code landmine is out of
  scope BY CONSTRUCTION (guard-asserted: no pbp import in the module/runner).
- Opponent/bring-back pairs (QB vs opposing WR) are game-environment dependence — the NF-W3 dead
  channel — and are OUT OF SCOPE here (same-team allocation only). Declared, not discovered.

## 4. Metrics — declared before any score

- **PRIMARY (selects + gates): `team_total_crps`** — sample-based CRPS of the team-week TOTAL
  (the roster-grain "lineup CRPS" the story card names). Correlations move the distribution of a
  sum; marginals alone cannot.
- Co-reported (never select): `energy_score` (half-pairing cross-term estimator) and
  `variogram_score` (p = 0.5) — the §12.7 dependence diagnostics; VS is the most
  dependence-specific and is reported for mechanism attribution.
- MAE appears nowhere. All metrics are sample-based with **S = 512** draws per construction per
  team-week under **common random numbers** (identical base normals/uniforms per team-week across
  constructions, seeded deterministically from (fold, team, gw) — no wall-clock anywhere).
- The 39-level grid identity (`Q_LEVELS`) carries the marginals: inverse-CDF sampling and
  randomized PIT both live on the same grid, tails clamped at q025/q975 **identically for every
  construction** (paired comparisons unaffected). The zero atom is carried by the grid's repeated
  zeros. No binary/two-point sub-target exists in this story, so the NF-W4 closed-form rule is
  N/A — declared, not skipped.
- ⭐ **Instrument validation (MH2.1 (d)):** the guards carry a POSITIVE control
  (a known equicorrelated copula at study-scale n and S must be detected: the true-dependence
  construction beats independence on the primary metric) and a NEGATIVE control (under true
  independence the dependence construction must not beat independence beyond MC noise). A null
  from an instrument that cannot see a known defect is INSTRUMENT_BLIND, not a finding.

## 5. ⭐ Oracle-first — the decision gate (scored and logged before any arm is judged)

**Per-form peeking oracles** (NF-D16 (g‴)): every parametrized construction form is re-fit on the
TEST fold's realized PITs (the `empirical_role_resample` oracle uses leave-one-out donors so it
never reads its own outcome). `independence` has no parameters — its peeking version is itself
(declared). **The ceiling = the best (max) peeking form's improvement over `independence` on the
primary metric.** A max over 5 peeking forms is upward-biased by selection — the bias direction
FAVORS a YES, so a NO under this estimator is conservative; stated here, in advance. Per-form
ceilings are all reported. Matched-n controls (NF1.9 (f)) accompany every real arm.

**The pre-registered decision rule (the story's deliverable):**

- `ceiling_stat_ok` = CI95 of the ceiling excludes zero ∧ fold wins ≥ the cv_power clause
  (6 of 8) ∧ BH-FDR (binding reading) passes.
- `ceiling_pct` = 100 × ceiling / mean independence `team_total_crps`.
- **Bands:** `ceiling_pct < 2.0` → **NO** — the §9 simulator premise fails at the allocation
  channel; report and stop, do not build toward it. `2.0 ≤ ceiling_pct < 5.0` → **MARGINAL** —
  a PM decision, both readings reported. `ceiling_pct ≥ 5.0` → **YES** — NF-W8 is justified on
  the allocation channel. Not `ceiling_stat_ok` → **NO** regardless of magnitude.
- Bands are calibrated against the program's own precedents: 2–3% (NF-W3) was recorded as
  "cannot justify the chain alone"; 8–28% (NF-W4) as the largest single error source.
- PBO for the ceiling contrast is **UNDEFINED by design** (one pre-registered contrast — no field
  to resample; the NF-W3 mis-specification is not repeated). The known `classify_null` n_arms=1
  fold-shortage mis-render is pre-declared an instrument bug: any "+N folds/seasons" trigger it
  prints for a single-contrast design is recorded beside the hand classification, never obeyed.
- Report-only context rows: the ceiling on `energy_score` and `variogram_score`; the 2025
  capture-era folds separately (NF-W2d/W2e sizing discipline); and the model-free realized
  same-team PIT correlation table by position-pair with team-week-clustered dispersion — the
  mechanism measurement.

## 6. The field (declared here; never trimmed or grown after a score)

**Foils (never shippable; the best foil binds):**
- `independence` — the incumbent: what the marginally-assembled champion serves today, and what
  NF-W8-less serving samples.
- `constant_rho` — one pooled same-team Gaussian-copula correlation fit on train: the
  climatology-of-dependence, the matched NON-learned foil (NF-D10 (g)) — a structured arm beating
  `independence` but not `constant_rho` has not earned its structure.

**Real arms — 4 structurally different classes (§0.5):**
1. `gauss_pos_factor` — one-factor Gaussian copula, per-position loadings on a shared team latent
   (the §9 `z_g` shared-game-state class).
2. `gauss_pos_pairwise` — Gaussian copula with the full position-pair correlation matrix
   (within-position pairs included, PSD-projected; the §10.1A structured empirical-covariance
   class; the only Gaussian form that can express NEGATIVE within-position competition).
3. `dirichlet_alloc` — the §5 compositional class: latent volume shock × Dirichlet share
   allocation over teammates (weights ∝ champion predictive means), converted to a copula by
   per-player rank transform; concentration + volume-sd fit on train by method of moments.
4. `empirical_role_resample` — nonparametric empirical copula: donor team-weeks resampled from
   train, players aligned by role cell (position × within-team rank by champion predictive mean,
   caps QB2/RB4/WR5/TE3), per-cell rank-normalized; unmatched cells fall back to independent draws.

**Anchors (diagnostic, never trials — excluded from the PBO matrix and the DSR trial field,
MH2.1 (a)):** per-form peeking oracles (5) · matched-n forms (4, NF1.9 (f)) · `comonotonic` (the
maximal-dependence degenerate — MUST lose; `independence` itself is the zero-dependence end, so
the degenerate pair brackets the dependence axis two-sidedly, NF1.7 (c)) · `shuffled_teams` (the
permutation anchor: the pairwise form fit on train PITs whose team labels are permuted within
global week — destroys real team structure, keeps marginals; must not beat `independence`
significantly, and the check FAILS CLOSED on an unevaluable p — NF1.7 (a)).

**Copula parameters are fit on TRAIN-side PITs, which are IN-SAMPLE for the champion** (the
champion is fit on train and predicted back onto train). Declared: the expected bias direction is
attenuation of fitted dependence — i.e. AGAINST the train-fit arms; the ceiling (test-fit) is
unaffected, and the ceiling is the decision object. Test-side PITs are honest out-of-sample.

## 7. Gates

**Folds:** the NF-W1 axis verbatim — 8 expanding half-season blocks 2022H1…2025H2, purge 2
global weeks, on the NF-W2d two-era matrix (seasons 2016–2025).

**Arm gate (secondary to the decision):** beats the best foil ∧ fold-consistency clause
(cv_power, 6/8) ∧ PBO < 0.20 over the 6-config eligible field (4 arms + 2 foils; anchors never
enter) ∧ DSR ≥ 0.95 over the declared 4-arm family ∧ BH-FDR q = 0.10 (two pre-registered
families: `{joint_alloc_arm}` and `{joint_alloc_ceiling}`; own-family AND pooled computed, the
stricter binds — MH2 (a)) ∧ `comonotonic` loses ∧ permutation behaves (fails closed) ∧ per-form
oracle floors respected AT MATCHED n (NF-D16 (g‴)/NF1.9 (f); strict reading reported beside) ∧
team-total coverage(80) floor 0.80 (a FLOOR, never a target — NF1.8; blocking only beyond
3 binomial SE).

**Power, checked in advance:** at 8 folds the fold clause is attainable (6/8); PBO is evaluable
for the arm field (6 configs); the sign floor 2⁻⁸ = 0.0039 < the 0.10 BH cutoff; dsr_ceiling(8) ≈
0.9999 against the 0.95 gate. The ceiling contrast's PBO is UNDEFINED (declared above).

**Verdicts:** derived at report time from stored per-fold selections, three-way, failing closed
to TIES (NF-W2e); `--rewrite-report` re-derives gates, both BH families, null states, the NF-W8
decision and every verdict sentence with zero refit, stamping `verdict_corrected_from` when
anything moves.

## 8. NF-W0 binding constraints, honored mechanically

(1) No new source, no new features — the only feature lists touched are the W2d-certified
champion lists, already provenance-gated; the availability/environment projection families are
NOT consumed (their level channels are the measured-dead predecessors). (2) The certified
roster-first frame IS the input; the NF-W0a PIT gate runs at the matrix build on every run,
cache hit or not. (3) Snap/usage columns are not read here at all. (4) ⛔ no markets / weather /
depth-rank / game-day inactive anywhere (nothing new is joined). (5) No pbp legs → no
era-normalization surface and no franchise-code join surface (guard-asserted). (6) Team-week
grouping conserves rows (asserted fail-closed).

## 9. Seeds and reproducibility

`_SEED = 20260811`; S = 512; per-team-week seeds derived from crc32 of `fold|team|gw` mixed with
`_SEED` (no wall clock, no `Date.now` analogues). The dirichlet MoM grid and factor least-squares
are deterministic. NGBoost is not used (the NF-W3 seeding landmine is N/A; LightGBM arms carry
`random_state=_SEED` through the shared `hurdle_parts`).
