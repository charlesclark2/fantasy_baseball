# NF-W4 — pre-registration (availability & playing-time: the availability mixture)

**Committed BEFORE the full run.** Everything decidable in advance is a CONSTANT in
`availability_mixture.py`; this file is the narrative copy of those constants. The runner READS
the module (the NF-D16 discipline) — nothing below may be chosen after seeing a score.

`best_alpha = 0` · projection product · **deploy-held** (serving = NF-W8 / NF-C6 Ph2). This story
promotes nothing, publishes nothing, retrains nothing.

---

## 1. What is being modeled, and why it is TWO layers

Availability is flagged as the **largest single error source** in the v3 accounting — it is the
mechanism that generates the zero atom in the weekly target, and its plausible ceiling is an
order of magnitude above the environment channel NF-W3 just measured (2–3% of champion CRPS,
of which the model captured 2–4%). NF-W4 builds the **distributional availability mixture** —
P(active) × P(plays | active) × snap/usage share, per player-week — **consuming** the certified
injury family (NF-W2/W2b/W2c/W2d + the `nfl/pit/wayback_injuries` capture store), never
re-deriving it.

| target | definition | family |
|---|---|---|
| **T1 `played`** | the certified frame label collapsed to {played, not-played} on the modeled (ex-bye) population — P(played) IS P(active)×P(plays\|active), and the structural decomposition is fielded as an ARM (`two_stage`), tested rather than assumed | two-point |
| **T2 `snap_share`** | realized `offense_pct` CONDITIONAL on played, scored ONLY where measured | rate on [0,1] |

A bye is a deterministic zero knowable at schedule release and never reaches this frame. T2's
population is played+measured; the played-but-unmeasured exclusion is **counted** every fold
(⛔ never fillna(0) — NF-W0b: unmeasured ≠ zero snaps).

**Layer A** is the component bake-off — does either target beat its own honest climatology?
**Layer B** is ⭐ **the gate that decides whether NF-W4 is worth anything**: does injecting the
*projected* availability block into the assembled player projection beat the **injury-aware
champion** — the NF-W2b/W2d certified per-position winners (QB/TE `inj_zero_leg`, RB/WR
`inj_both`) over the NF-W1 `lgbm_hurdle` — on held-out weeks? Registering against the plain
NF-W1 champion would re-discover the already-certified injury lift and mis-attribute it to this
story; the incumbent spec is **imported from `W2B.POST_FLIP_SPEC` and pinned to the committed
NF-W2d artifact** (MH2.1 (b): compare against the object that was validated). A component that
wins Layer A and loses Layer B is a **recorded null, not a served model** (captured-stays-
captured).

## 2. ⭐ Oracle first (NF-W3's transferable discipline)

Before any arm is judged, the **realized-availability oracle** — the peeking substitution of the
target week's realized played indicator (always) and realized snap share (only where measured;
an unmeasured share keeps the projection, never a fabricated value; `share_sd` is not
substituted — a realized value has no spread) — is scored per position, every run, and logged
before selection. It bounds the availability channel from above, two-sided: a null under a small
ceiling is *nothing to find*; a null under a large ceiling is *the models missed it* — different
findings. Layer A gets the same treatment via **one peeking oracle per arm's own form**
(NF-D16 (g‴)) with the **matched-n capacity control** (NF1.9 (f)) so a legitimately-better
nested/conditional form is not vetoed as a false metric inversion.

## 3. Binding NF-W0 constraints (inherited, non-negotiable)

1. **Allowed feature contract only.** Every feature is `<family>__<detail>` against the certified
   contract; the Layer-B block is the registered **derived** family `availability_projection`
   (in-fold model outputs over certified inputs — no new source, no new PIT record class).
   Unknown provenance is a rejection.
2. **Roster-first certified frame** — the NF-W2d two-era matrix (89,954-row frame lineage,
   46.1% retained zeros; injury features nflverse-stamped ≤2024, wayback-capture-stamped 2025
   with per-row `observed` coverage flags — as-of-instant observations, ⛔ no fillna(0):
   uncovered ≠ healthy).
3. **PIT.** `assert_point_in_time` is invoked at the assembly boundary via the NF-W2d gate
   (window records + injury records + rate records, two provenance shapes), fail-closed, on
   every build including cache hits. NF-W4 introduces **no new source**.
4. **Snap features NULL-bearing.** T2 exclusions counted; model-internal TRAIN-fitted median
   imputation is the declared device for NaN-incapable learners (presence flags retained).
5. **⛔ Banned as features:** markets, weather, depth-chart rank, and **game-day inactive
   status — the leak this story is uniquely exposed to** (you predict availability, never read
   it). The provenance guard carries an explicit **target-leak clause**: `offense_pct`, the frame
   `label`, the roster `status` column and the target columns themselves reject the build if they
   appear in any feature list.
6. **No pbp is touched** — both layers run at player-week grain on the W2d matrix, so the
   NF-W3 franchise-code landmine has no join to bite; stated so the constraint's absence is a
   documented fact, not an oversight.
7. **Injury-freshness discipline (NF-W2e):** ⛔ no freshness bound is tightened — NF-W2e
   *measured* that a ≤1d consumption rule LOSES; the family enters exactly as W2d certified it
   (7-day coverage bound, latest-admissible-wins).

## 4. Design

- **Grain / span:** player-week, 2016–2025 REG (the W2d matrix).
- **Folds:** the NF-W1 axis verbatim — 8 expanding-window half-season blocks (2022H1…2025H2),
  purge 2 global weeks. Identical axis = Layer B is a matched comparison. The two 2025 blocks
  are **as-of-capture era** folds: reported separately for lift sizing (NF-W2d: quote the
  capture-era number, not the legacy one), never gated separately (n=2 is a design quantity).
- **Metric: CRPS.** ⛔ MAE never selects and never gates (availability is maximally zero-heavy —
  the NF-D11/NF-D14 inversion regime; the all-zero degenerate is SCORED every run and read).
  T2 + Layer B use the shared 39-level grid identity (`crps_q39`). **T1 is scored by the exact
  closed form of the SAME functional** (`crps_bernoulli` = (y−p)²; the degenerates in their own
  closed forms: point mass |y−x|, Uniform[0,1] = 1/3): a 39-level grid quantizes p to 0.025 and
  silently ties arms — declared here, before any score.

### 4.1 Field (pre-registered; a family may not be discovered later — MH2 (a))

**Layer A real arms — 4 structurally different classes per target:**

| target | arms |
|---|---|
| T1 `played` | `logit_glm` (linear GLM) · `lgbm_binary` (boosting) · `two_stage` (⭐ the story's named STRUCTURAL mixture — P(active)×P(plays\|active) via the frame label's own decomposition, a candidate not an assumption) · `knn_rate` (nonparametric neighbourhood) |
| T2 `snap_share` | `frac_logit` (fractional-logit GLM + empirical residual bank) · `beta_mom` (same mean under a Beta predictive, MoM concentration — the overdispersion hypothesis tested) · `lgbm_quantile` (distributional boosting) · `knn_quantile` (neighbourhood) |

**Foils (must be beaten; never shippable):** `foil_clim` — the player's OWN lagged availability
level (played-share L4 / snap-share L4), EB-shrunk toward the position rate (κ=4 games vs 4
games of L4 evidence; a missing window is honestly the position rate, never 0) — the story's
"snap/usage climatology". `foil_clim_inj` — the same climatology plus a **deterministic
train-fitted injury-designation lookup**: T1 replaces P(played) with the train empirical
P(played | class) for {out, doubtful, questionable, listed_no_designation}; T2 multiplies the
share point by the train mean-share ratio for {questionable, listed_no_designation} (playing
after Out/Doubtful is too rare to fit — those classes keep the climatology point, declared),
clipped to [0.25, 1.50]. A lookup cell thinner than **200 rows falls back to climatology for
that class AND IS COUNTED** in the artifact — loud, never silent (NF1.7 (a)); a hard raise is
the wrong failure mode for the expanding-window refits, where early slices are legitimately
thin. The **best** foil binds.

**Anchors (diagnostic — excluded from the PBO matrix and the DSR trial field, MH2.1 (a)):**
`nihilist_zero` (the all-zero degenerate — for T1, "nobody plays"; measured, never reasoned
about — NF-D14) · `marginal_train` (per-position train climatology) · `zero_width` (point mass
at the foil's point) · `max_width` (T1: Uniform[0,1]; T2: the foil bank ×3) — all four must
LOSE (a constraint a degenerate satisfies is fine; a criterion one wins is fatal — NF1.8) ·
`permuted_within` (the target shuffled within position×global-week, fit by the pre-registered
boosting class — must lose AND its lift must not be significant, **failing CLOSED on a None
p-value**) · `oracle__<arm>` (one peeking ceiling per arm's OWN form) · `matched_n__<arm>`
(the capacity control).

**Layer B field (exactly two arms, declared here and never trimmed or grown):**
`champion_inj` (the per-position W2d-certified incumbent, refit per fold) versus
`champion_avail` (the identical estimator + the `availability_projection` block in **both**
hurdle legs — P(played) generates the zero atom; the share moves conditional usage). Anchors:
`champion_avail_foil` (the block produced by the **foil forms** `foil_clim_inj`/`foil_clim_inj`
— the matched foil-availability arm: `champion_avail` beating it attributes the lift to the
LEARNED component, not to availability-shaped context in any form — NF-D10),
`champion_avail_shuffled` (the block permuted jointly across players within position×week —
same values, wrong players; must not help), and ⭐ `champion_avail_oracle` (§2).

### 4.2 The Layer-B block, and how its train-row values are produced

Injected columns: `availability_projection__{p_played, snap_share, expected_avail, share_sd}`,
where `expected_avail = p_played × snap_share` is **always recomputed from the (possibly
substituted / shuffled) parents** so the vector stays coherent under every variant.

⚠️ A projected feature must be a PROJECTION on both sides of the fold (NF-W3): TEST-row values
come from the Layer-A winner forms fit on the whole fold-train; TRAIN-row values come from
**expanding-window refits inside the training span** (season s predicted by a fit on seasons
< s; the first two seasons are burn-in and in-sample for themselves — a residual optimism that
biases the gate **against** NF-W4, declared here, in that direction, before the run).

A non-vacuity assertion requires the block to attach (≥99% fully-non-NaN on the fold scope) for
every variant — an all-NaN block would compare the champion against itself and the gate would
pass on nothing (NF-C0e wired-≠-invoked / NF1.7 (a)).

## 5. Gates

Layer A, per target (all of): `beats_foil` ∧ `fold_consistency`
(`cv_power.fold_consistency_clause(8)` ⇒ 6/8) ∧ `pbo_ok` (PBO < 0.20 over the 6-config eligible
field) ∧ `dsr_ok` (DSR ≥ 0.95 over the declared 4-arm family) ∧ `fdr_ok` (BH q=0.10 — **two
declared families, component {played, snap_share} and downstream {QB,RB,WR,TE}, corrected
within themselves AND pooled over all 6; the stricter binds**) ∧ `degenerates_lose` ∧
`permutation_behaves` (fails closed on a None p) ∧ `oracle_floors_respected` (per-form, at
matched n; strict reading reported beside it) ∧ `coverage_floor_ok` (0.80 is a FLOOR, blocking
only beyond 3 binomial SE).

Layer B, per position: the same **minus PBO** — Layer B fields exactly ONE pre-registered
contrast, so CSCV has no field to resample. ⭐ **PBO is declared UNDEFINED here, up front, and is
NOT a gate** — NF-W3 registered `pbo_ok` on its Layer B and then had to disclaim it as a
mis-specification; NF-W4 does not repeat that. Checks: `beats_champion` ∧ `fold_consistency` ∧
`dsr_ok` ∧ `fdr_ok` ∧ `permutation_behaves` ∧ `oracle_floor_respected` (the winner may not beat
the peeking realized oracle) ∧ `coverage_floor_ok`.

**Power, checked in advance:** at 8 folds the fold clause is attainable (6/8), Layer A PBO is
evaluable (6 configs), the sign floor 2⁻⁸ = 0.0039 < the 0.10 BH cutoff, and `dsr_ceiling(8)`
≈ 0.9999 against a 0.95 gate. **One clause is structurally near-inactive and named in advance
(NF-D20):** T1's central-80% coverage of a two-point predictive spans {0,1} whenever
p ∈ (0.10, 0.90), so the floor cannot bind on most rows — it is recorded as
`structurally_inactive`, never credited as a pass.

**Null classification:** `cv_power.classify_null` per failure, with the three known instrument
gaps hand-corrected exactly as in NF-W2/NF-W3: an anchor-only refusal is the
`CONSTRAINT_REFUSED` family (no sample-size re-test trigger may be published); a Layer-B
`UNDEFINED` driven by the honest `n_arms=1` is re-read as GENUINE_ABSENCE (negative point
estimate — no trigger) or POWER_LIMITED (shortfall stated in folds); any "smaller field" remedy
below the declared family is flagged SUSPECT (MH2.2). The instrument's own verdict is recorded
beside every hand correction, never discarded.

## 6. Expected-lift sizing (NF-W2d/W2e, binding on the report's language)

Any forward-looking magnitude quotes the **2025 as-of-capture folds** (reported per position as
`era_note`), not the legacy stamp era — the injury lever priced ~⅓ of its vendor-stamped size at
RB on the capture era. ⛔ No freshness bound is tightened (NF-W2e measured that and it loses);
the fresh/stale gradient is real but the lever is capture cadence, not filtering.

## 7. Verdict vocabulary

Every direction word is **three-way and DERIVED at report time** (BEATS / TIES / LOSES TO),
failing closed to `TIES` on an unevaluable interval, with the word and its parenthetical
computed together (NF-W2e). The verdict layer itself is re-derivable from the stored JSON
without a refit (`--rewrite-report`), and a re-derivation that moves a verdict records what it
was before.

## 8. What this story explicitly does NOT do

- No serving, publishing, registry write, S3 write, or retrain (deploy-held; `best_alpha = 0`).
- No re-derivation of the injury family — consumed exactly as NF-W2d certified it.
- No usage/opportunity allocation model (targets/carries share) — that is NF-W5's, and adding it
  here would inflate the trial field that deflates this one.
- No markets, weather, depth-chart, or game-day status features (NF-W0 deferred + the target-
  leak clause).
- No freshness-bound tuning on the injury capture (NF-W2e's measured negative).
