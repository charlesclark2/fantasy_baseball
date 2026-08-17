# NF-W7e pre-registration — the availability SPLIT over the ALL-ROWS Σ, and the ATOM-CAP confirmation

**Committed BEFORE any full-run scoring** (the §0.5 discipline). Everything below lives as
constants in `fp_availability_split_allrows.py`; the runner `run_nf_w7e_split_allrows.py` READS
them (NF-D16). A smoke run (1 fold, QB only, 300 draws, artifacts suffixed `_smoke`) may be used to
prove the code path — no verdict, and **no constant may change in response to a smoke score after
this file is committed** except as an explicitly recorded SMOKE AMENDMENT (§11).

⚖️ Edge-independent projection product — `best_alpha = 0`, **deploy-held**, NF-G0 challenger.
Research-only: no changelog entry. Every emitted string is a calibrated RANGE, never an edge /
ROI / win-rate claim.

---

## 0. The thesis under test (not assumed)

NF-W7d registered an availability MIXTURE for the assembled fantasy-point distribution — Bernoulli
(plays) × a conditional-on-playing joint draw, marginal-preserving by algebra — with **Σ estimated
on ACTIVE rows only**, and returned a QB null (`GENUINE_ABSENCE`, Δ −0.0031 CRPS vs the incumbent).
Its matched foil `mix_off` (the same Σ_played in a single copula, availability term OFF) split the
bundle, and the two halves point in OPPOSITE directions:

| channel | measured by (NF-W7d) | QB | RB | WR | TE |
|---|---|---|---|---|---|
| the availability **SPLIT** | `mixture − mix_off` | **+0.0149** | **+0.0161** | **+0.0058** | **+0.0036** |
| the **Σ POPULATION** (active rows only) | `mix_off − single_copula` | **−0.0180** | −0.0044 | −0.0042 | −0.0015 |
| net vs the incumbent | | −0.0031 | +0.0117 | +0.0016 | +0.0021 |

The split is positive at all four positions; the Σ population is negative at all four; the bundle
netted negative at QB alone because QB's Σ penalty is ~4× any other position's (QB's ρ̄ all-rows ÷
active-rows ratio is 1.79–1.85× across every fold — restricting Σ to active rows is where QB loses
the most information).

⛔ NF-W7d §12.1 is explicit: *"`mixture with the ALL-ROWS Σ` was not in the declared field and is
not measured here; the split's +0.0149 is measured CONDITIONAL ON Σ_played. Asserting that
combination would win is exactly the post-hoc field construction MH2.2 forbids. It is a SUCCESSOR,
registered forward."* This is that successor. **The thesis:** keep the half that pays (the split),
drop the half that costs (Σ_played → Σ_all), and the resulting assembled distribution beats the
same reproduced incumbent AND NF-W7d's own registered arm at every position, clearing every gate
clause at RB/WR/TE — the positions the optimizer needs — and moving QB in the modelled direction.
A null is a legitimate published outcome; §8 says what each null would mean.

⭐ **The second, cheaper hypothesis folded in — the ATOM CAP.** NF-W7d §12.4 measured that the
MARGINALS bound how much atom the mixture may install: the marginal-admissible floor
`π ≥ 1 − min_i P̂_i(0)` clamps π̂ on 91.7% of QB rows, so only **0.267** of atom is installed against
a realized all-zero rate of **0.516**, and §12.3's decile vector is the signature of an
under-priced zero atom. The cap is a function of the per-stat banks and π̂ ALONE — Σ never enters
`clamp_pi`. **Prediction, registered:** the all-rows Σ cannot move the INSTALLED atom (an identity,
measured per fold); it can move QB's PIT only through the conditional joint-zero probability
(NF-W7d measured that Σ_all vs Σ_played is worth ~0.009 of PIT with the split OFF: `single_copula`
0.0646 vs `mix_off` 0.0731). So QB's PIT under the all-rows arm is a genuine test with a rule fixed
in advance (§7): if QB still fails the bar with EVERY joint-layer knob exercised across
NF-W7c/W7d/W7e, the ceiling is the marginals' and no joint-layer story clears it.

---

## 1. Binding constraints

- ⛔ **The per-stat marginals are NOT refit or re-selected.** The assembly consumes the NF-W6d
  SERVED MAP through the SERVING DISPATCH (`SDSD.serve_banks`), exactly as NF-W7c/W7d did.
- ⛔ **Nothing new is estimated.** π̂ comes from NF-W7d's three pre-registered estimators, IMPORTED
  by identity (`MX.pi_for_arm`); Σ is the incumbent's own estimator (`FA.position_sigma` on all
  train rows) — the matrix NF-W7c's `joint_rank` draws under. The mixture machinery is NF-W7d's
  one code path (`MX.mixture_leg_draws` / `assemble_mixture_bank`), so the marginal-preservation
  algebra, the clamp and its counting are inherited unchanged.
- ⭐ **THE INCUMBENT IS THE MATCHED FOIL — by identity, guard-tested.** The mixture over Σ_all at
  π ≡ 1 is BYTE-IDENTICAL to `FA.assemble_fp_bank(corr=Σ_all)` = `single_copula`. So
  `single_copula − mixall` is the split's contribution over the all-rows Σ with nothing else moving.
- ⛔ **Every gate constant is INHERITED BY REFERENCE** — the PIT bar (0.05), the coverage(80)
  floor, PBO/DSR/FDR, the gate league, the oracle α and materiality fraction, the mixture-activity
  floor and the marginal-drift tolerance. Guard-tested by identity, not by value.
- **Frames, folds, PIT gate**: NF-W6d's matrix builder + the NF-W1 8-fold axis (2022H1…2025H2,
  purge 2) + the fail-closed per-week PIT gate, all reused unchanged.
- **Σ and π are always estimated on TRAIN**, never on the slate being scored; the oracle and
  matched-n contexts are the only exceptions and are labelled as such.
- **The per-fold marginal banks are CACHED to disk** (`artifacts/nf_w7e_bank_cache/`, gitignored),
  keyed on the matrix key + fold label + a hash of the served map, and REFUSED on any shape or
  cell mismatch. NF-W7d's `incumbent_reproduces` (max gap 0.0 on 8/8 folds) is the proof the
  dispatch is byte-identical across runs; the cache changes nothing scored and exists so a harness
  fix costs the draws, not the fits.

### ⭐ The draw seed is INHERITED, twice over

NF-W7d inherited NF-W7c's seed so `single_copula` reproduces NF-W7c exactly. This story inherits
the same seed AND NF-W7d's availability-stream offset, so `single_copula` reproduces NF-W7c AND
`mix_off` / `mix_played` reproduce NF-W7d — per fold, to 1e-9. Nothing can be shopped: the three
all-rows arms did not exist under this seed. (NF-W7d §2's argument, verbatim.)

---

## 2. Scope: FOUR gated positions, all registered SHIPPABLE

NF-W7d gated QB alone and scored RB/WR/TE report-only; its record says a report-only position that
would have passed every clause "is a hypothesis for a successor to register FORWARD". **This story
registers all four positions as GATED and SHIPPABLE.** The optimizer needs all four, and the BH
family therefore carries FOUR members — the multiplicity is bought, not dodged.

⛔ NF-W7d's report-only wins (RB +0.0117 8/8, WR +0.0016 8/8, TE +0.0021 8/8) are **NOT carried
forward as evidence** — they were measured on the Σ_played bundle, a different arm, and a report-only
result may not be re-classified into shippability (E2.1-r). Every position earns its verdict here.

---

## 3. The declared field (⛔ never trimmed or grown after a score — MH2 (a) / MH2.2)

**Three real arms, a COHERENT family**: they differ ONLY in how π is estimated, over identical
mixture machinery and the identical ALL-ROWS Σ. The three π estimators are NF-W7d's, imported.

| arm | π̂ estimator (NF-W7d's) | Σ |
|---|---|---|
| `mixall_learned` ⭐ PRIMARY | the NF-W4 certified binary-learner SPEC on the champion feature set (`mix_learned`) | ALL train rows |
| `mixall_clim` | the player's own EB-shrunk lagged availability (`mix_clim`) | ALL train rows |
| `mixall_const` | the position's TRAIN activity rate — per-row BLIND (`mix_const`; registered SHIPPABLE per NF-D20) | ALL train rows |

**CONTEST FOILS (`beats_foil` binds against these and only these):**

- `single_copula` — **THE INCUMBENT** (NF-W7c's `joint_rank`: one Gaussian copula, Σ on ALL rows)
  — and, by the π ≡ 1 identity, **THE MATCHED FOIL**. Reproduced to 1e-9 vs NF-W7c's record.
- `mix_played` — **NF-W7d's registered PRIMARY** (`mix_learned`: Σ on ACTIVE rows + the SAME
  learned π̂, same estimator, same fit). Reproduced to 1e-9 vs NF-W7d's record. ⭐ The all-rows arm
  must beat the bundle it claims to improve on, or "Σ_played was the costly half" is not earned;
  `mix_played − mixall` is the Σ-population effect WITH the split on — the 2×2 cell NF-W7d could
  not measure.

**REFERENCE FOILS (SCORED and REPORTED; they do NOT bind `beats_foil`; excluded from the PBO/DSR
trial field per MH2.1 (a)):** `mix_off` (Σ_played, split OFF — completes the 2×2 and reproduces
NF-W7d's `mix_off` to 1e-9), `assembled_indep` (carries the three inherited dependence clauses),
`foil_direct_points` (the ARCHITECTURE question, NF-W7c §11.4 — never this story's gate).

**The 2×2 the field completes**, every cell on common random numbers:

| | Σ ALL rows | Σ ACTIVE rows |
|---|---|---|
| **split ON** | `mixall_*` (THIS STORY) | `mix_played` (NF-W7d) |
| **split OFF** | `single_copula` (NF-W7c, the incumbent) | `mix_off` (NF-W7d's matched foil) |

with the identity `(A−D) − (B−C) = (A−B) + (C−D)` (guard-tested on the attribution object).

**DEGENERATES (registered to LOSE the selection metric):** `nihilist_zero`, `zero_width` (at the
train mean), `max_width`, `assembled_comonotone` — the last is also the PIT-table control (§4).

**ANCHORS:** `permuted_direct`; `pi_permuted` (the primary arm's own π̂ shuffled across players
within a global week, over the arm's own Σ_all — aimed at the availability SIGNAL channel);
per-form oracle + matched-n controls for every real arm (π on the test block + Σ_all on the test
block; the matched-n control on the most recent train rows sized to the test block); an own-form
oracle for `foil_direct_points` as the ACTIVITY POSITIVE CONTROL. ⛔ `single_copula`, `mix_played`,
`mix_off`, `assembled_indep` carry NO oracle — an anchor that cannot differ from what it anchors is
décor (NF1.7 (a)). The three-state oracle evaluator (RESPECTED / VIOLATED / INACTIVE) is
NF-W7c's, imported, with its materiality clause (an inversion counts only if BOTH significant at
α = 0.05 AND ≥ one tenth of the arm's claimed effect over its matched foil — here the incumbent).

**Eligible set for PBO**: the 3 arms + 2 contest foils (5 configs). **DSR** deflates over the 3-arm
declared family; anchors, degenerates and the three reference foils never enter `V`.

---

## 4. PIT gates but does NOT select (NF-W7d §4, inherited verbatim)

Arms are RANKED on `crps_q199`; the SELECTED arm must clear the PIT bar (0.05, per-fold mean of
max-decile deviations — NF-W7c's convention, the row-pooled figure reported beside it); the
degenerates are scored on PIT every run and the table is printed. `assembled_comonotone` has posted
the best PIT in the QB field two runs running while losing CRPS by ~0.1 — a criterion a degenerate
wins is fatal (NF1.8). The decile VECTOR is stored per label per fold (NF-W7d's instrumentation).
The calibrated null (MH2.6) is reported and does not move the bar.

---

## 5. Gate (all clauses must pass, per position; composed in code)

`crps_q199` vs the best CONTEST foil ∧ the calibrated fold-consistency clause (`cv_power`) ∧
PBO < 0.20 over the 5-config eligible field ∧ DSR ≥ 0.95 over the 3-arm declared family ∧ BH-FDR
at q = 0.10 over the FOUR gated hypotheses ∧ the coverage(80) floor ∧ randomized-PIT decile
flatness ≤ 0.05 ∧ degenerates lose ∧ permutation behaves (the label permutation AND the π
permutation) ∧ per-form oracle floors respected at matched n ∧ the three inherited DEPENDENCE
clauses ∧ NF-W7d's two mechanism clauses (`mixture_is_active` ≥ 0.01 installed atom;
`mixture_preserves_marginals` ≤ 0.01 sup drift, the diagnostic run over the arm's own Σ_all with the
incumbent's draw path as the reference side) ∧ `incumbent_reproduces` (`single_copula` vs NF-W7c,
1e-9) ∧ the two clauses this story ADDS:

- ⭐ **`predecessor_reproduces`** — `mix_off` and `mix_played` must reproduce NF-W7d's recorded
  per-fold `mix_off` / `mix_learned` to 1e-9. The contest foil `mix_played` IS NF-W7d's arm; if it
  does not reproduce, the "Σ population with the split on" cell is measuring drift.
- ⭐ **`atom_is_sigma_invariant`** — the PRIMARY arm's installed atom under Σ_all and `mix_played`'s
  under Σ_played (same π̂, same banks, same clamp) must agree to 1e-9 per fold. It is an identity of
  the construction and it is MEASURED, because the atom-cap verdict (§7) rests on it: an identity
  that failed would mean the two arms did not share a π̂, and the confirmation is then UNDEFINED.

`cv_power.classify_null(declared_field_size=3)` classifies any null, read through
`field_remedy_admissible` (MH2.7); the source of the declared size is recorded on the verdict. A
PIT-only or anchor-only refusal is `CONSTRAINT_REFUSED` with NO data trigger (NF-D18); its remedy
text names the MARGINAL layer, not more seasons.

---

## 6. Pre-declared arm-movability

- The availability knob provably moves the gate statistic (NF-W7d §7): ~54% of QB rows realize
  exactly the atom, and π moves those rows' PIT directly; `mixture_is_active` measures the knob was
  turned.
- ⭐ **The Σ population provably moves the assembled predictive**: `sd(Σ wᵢXᵢ)` is strictly
  increasing in every off-diagonal with a positive weight product, and Σ_all ≠ Σ_played on every
  atom-bearing slice (guard-tested); NF-W7d measured `mix_off − single_copula` at −0.0180 (QB).
- The Σ population does NOT move the installed atom (§7's identity) — declared so the reader knows
  in advance which statistic the arm cannot touch and why that is the point, not décor.

---

## 7. ⭐ The ATOM-CAP rule (fixed in advance; read on QB's selection by `SA.atom_cap_verdict`)

Inputs: the per-arm PIT (per-fold mean) of the three real arms at QB; the installed atom under
Σ_all (primary arm) and under Σ_played (`mix_played`); the mean atom CAP `mean_i (1 − π_floor,i)`
(what the marginals ADMIT); the realized all-zero rate; the assembled TOTAL zero mass each
construction actually carries (`SA.total_zero_mass`, read conservatively off the sampler's grid,
negative totals excluded).

| state | rule | reading |
|---|---|---|
| **`QB_BLOCKED_AT_THE_MARGINAL_LAYER`** (CONFIRMED) | identity holds AND no real arm's QB PIT ≤ 0.05 | every joint-layer knob has been exercised (split on/off × Σ_all/Σ_played + the comonotone ceiling): the ceiling is the marginals'; **no joint-layer story clears QB; the QB roadmap moves to the 52-cell substrate** |
| **`QB_CLEARS_UNDER_THE_ALL_ROWS_SIGMA`** (REFUTED) | identity holds AND some real arm's QB PIT ≤ 0.05 | the joint layer CAN clear QB; the marginal cap was NOT the binding constraint |
| **`UNDEFINED`** | identity fails, or QB not scored | never read as either (NF1.7 (a)) |

Reported beside the state: `pit_moved_by_sigma_all` (primary arm's PIT − `mix_played`'s), the
cap-vs-realized shortfall, and the per-construction total zero mass — the magnitudes a reader needs
to check the rule, not to re-decide it.

---

## 8. What a null would mean

- **A position beaten by `single_copula`** ⇒ the split does not pay over the all-rows Σ there:
  NF-W7d's +split was CONDITIONAL on Σ_played after all (an interaction), and the 2×2 shows it.
- **A position beaten by `mix_played` but not by `single_copula`** ⇒ the split pays, but Σ_played
  was NOT the costly half with the split ON — the interaction cell reverses NF-W7d's Σ-population
  reading. A sharper finding than the ship: it says the two halves are not additive.
- **PIT-only refusal at a position** ⇒ `CONSTRAINT_REFUSED`, NO data trigger; at QB it is the
  atom-cap CONFIRMED state and the remedy is the MARGINAL layer under a fresh registration.
- **DSR failure** ⇒ read for its mechanism (which trial arm inflates `V`) BEFORE filing
  POWER_LIMITED; the three arms sit within ~0.001 CRPS of each other by NF-W7d's measurement, so a
  DSR failure here is unlikely to be a field-dispersion artifact — but it is read, not assumed.
- ⭐ Whatever the state, read WHICH FOIL it is against and which 2×2 cell it names before repeating
  it (NF-W7c §11.4 / NF-W7d §12.2).

---

## 9. Deploy hold

Nothing here promotes, publishes or retrains. NF-W7c's serving path stays fail-closed on ITS
record; this story writes no serving path of its own. `PROMOTE_BLOCKERS` are carried onto the
artifact and into the report; NF-W7c's promote blockers are inherited in full.

---

## 10. Power, checked in advance

At 8 folds the calibrated fold clause is attainable and PBO is evaluable over the 5-config
eligible field; the sign floor `2⁻⁸ = 0.0039` sits below the 0.10 BH cutoff at family size 4;
`dsr_ceiling(8) ≈ 0.9999` against a 0.95 gate. NF-W7d's report-only RB/WR/TE deltas (+0.0117 /
+0.0016 / +0.0021, all 8/8) were measured on the Σ_played bundle; if the Σ-population effect is
additive, this arm's margins are LARGER by |Σ penalty| (~0.004 / 0.004 / 0.0015), so a WR-scale
effect (+0.006) at 8 folds and DSR over 3 near-identical arms is comfortably inside the design's
power. QB is the exception by design: the PIT bar is a constraint, and §7 is the rule for reading
it.

---

## 11. Smoke amendments

*(A path-proof smoke — 1 fold (2025H2), QB only, 300 draws — may be run to prove the code path.
Any constant changed in response to it is recorded HERE, before the decisive run, and never
silently.)*

- **None.** The path proof (2025H2, QB, 300 draws, 602 s — 568 s of it the W6d marginal dispatch,
  now cached for the decisive run) exercised the full field, every anchor and every clause without
  a constant change. Determinism of the learned-π fit was checked BEFORE committing (two separate
  processes produce a byte-identical π̂ vector on the smoke fold, sha `89341fb8bd96feb5`), so the
  1e-9 `predecessor_reproduces` clause on `mix_played` is fair rather than hopeful.

### 11.1 Smoke OBSERVATIONS — ⛔ no constant, gate, arm or bar changed

*(1 fold — 2025H2 — QB only, 300 draws. **NOT a verdict**: one fold cannot select, the runner
correctly produced no selection and the atom-cap layer correctly returned UNDEFINED. Recorded so a
reader knows what was seen at the moment the registration was frozen.)*

- ✅ **The mechanism ACTS and the algebra holds**, and the identity holds by measurement: the
  primary arm's installed atom **0.2641** under Σ_all is byte-identical to `mix_played`'s under
  Σ_played (same clamp note field-for-field: binding share 0.9215, π̂ mean 0.4857 → used 0.7359);
  the atom CAP on this fold is 0.2658 (the clamp binds on 92% of rows, so the installed atom sits
  ~at the cap); marginal drift 0.002 against the 0.01 tolerance; ρ̄ all-rows 0.247 vs active 0.137
  (1.80×, NF-W7d's figure on the same fold).
- 📋 **The 2×2 on this one fold at 300 draws** (⚠️ 300-draw banks are coarse; NF-W7d's smoke moved
  ~0.01 between 300 and 4000 draws): `mixall_learned` 2.6390 · `single_copula` 2.6426 · `mix_played`
  2.6580 · `mix_off` 2.6698 ⇒ split over Σ_all **+0.0036**, split over Σ_played +0.0118,
  Σ-population with the split +0.0190, without +0.0272. The three all-rows arms sit within 0.0014 of
  each other (a coherent family, as declared). Direction consistent with NF-W7d; magnitude not
  evidence.
- ⚠️ **The observation the decisive run should be read against — and the reason it is a TEST:** on
  this fold at 300 draws the all-rows arm's QB PIT is **0.0854**, WORSE than `mix_played`'s
  0.0598 and than `single_copula`'s 0.0812, with the excess in the FIRST decile (0.185 vs 0.160 vs
  0.181) — the under-priced-atom signature is LARGER under Σ_all + split than under Σ_played +
  split, even though the assembled total carries slightly MORE zero mass (0.292 vs 0.287). Read
  literally, Σ_all already carries the availability co-movement (its ρ̄ is 1.8× the conditional
  one) and the Bernoulli split on top of it re-prices availability a second time — CRPS-better,
  calibration-worse. One fold at 300 draws is not evidence and ⛔ nothing may be tuned in response
  (E2.1-r); if it reproduces at full scale it is a §8 finding (a CRPS win with a PIT refusal at QB
  ⇒ `CONSTRAINT_REFUSED`, atom-cap CONFIRMED) and the record will say so.
- ⚠️ `incumbent_reproduces` / `predecessor_reproduces` cannot pass at 300 draws by construction
  (as in NF-W7d's smoke); the identity is checked at 4000 draws in the decisive run.

---

## 12. POST-RUN FINDINGS (added AFTER the decisive run — 2026-08-17; run by the operator, 4,933 s)

⛔ **Nothing in this section changes a gate, a threshold, an arm, or a verdict.** The run's result
stands exactly as §§0–11 defined it: **SHIP at WR** (`mixall_learned`, +0.0034 CRPS vs the
incumbent 8/8, +0.0018 vs NF-W7d's `mix_played` 7/8, DSR 0.985, PIT 0.0145) · **QB
`CONSTRAINT_REFUSED`** on the PIT bar alone (every other clause green; +0.0064 vs the incumbent 8/8,
+0.0095 vs `mix_played` 8/8, DSR 0.9999, PIT 0.0648) · **RB `GENUINE_ABSENCE` against
`mix_played`** (−0.0039, 1/8 — while beating the incumbent +0.0078 8/8) · **TE `GENUINE_ABSENCE`
against `mix_played`** (−0.0005, CI95 [−0.0015, +0.0005], 4/8 — a TIE; +0.0016 vs the incumbent
7/8). **Atom cap: `QB_BLOCKED_AT_THE_MARGINAL_LAYER` (CONFIRMED).** All three reproduction
identity proofs exact — max gap **0.0 on 8/8 folds** for `single_copula` (vs NF-W7c), `mix_off`
and `mix_played` (vs NF-W7d) at every position; `atom_is_sigma_invariant` gap 0.0.

### 12.1 ⭐⭐ The two halves are NOT additive — the interaction is roughly HALF the split

NF-W7d's attribution measured the split OVER Σ_played and the Σ population WITHOUT the split;
the additive reading predicted the split over Σ_all would be worth the same +0.0149/+0.0161/
+0.0058/+0.0036. Measured, the whole 2×2:

| pos | split over Σ_all (THE CLAIM) | split over Σ_played (NF-W7d) | ratio | Σ pop WITH split (`mix_played` − arm) | Σ pop WITHOUT split (NF-W7d) |
|---|---|---|---|---|---|
| QB | **+0.0064** (8/8) | +0.0149 | 0.43 | **+0.0095** (8/8) | −0.0180 |
| RB | **+0.0078** (8/8) | +0.0161 | 0.48 | **−0.0039** (1/8) | −0.0044 |
| WR | **+0.0034** (8/8) | +0.0058 | 0.59 | **+0.0018** (7/8) | −0.0042 |
| TE | **+0.0016** (7/8) | +0.0036 | 0.44 | **−0.0005** (4/8) | −0.0015 |

- ⭐ **The split is worth roughly HALF as much over Σ_all as over Σ_played, at every position.**
  Σ_all already carries part of the availability co-movement (its ρ̄ is 1.2–1.8× the conditional
  one), so an explicit Bernoulli split has less left to price. NF-W7d's "+0.0149 at QB" was a
  statement about the split *conditional on* Σ_played — exactly what §12.1 there warned, now
  measured.
- ⭐ **The Σ-population sign is POSITION-SPECIFIC once the split is on.** With the split off, Σ_played
  cost at all four positions (NF-W7d). With the split on, Σ_all is better only where the
  availability ratio is largest (QB 1.8×, +0.0095) and at WR (+0.0018); at RB `mix_played` (Σ_played
  + split) is the better construction (−0.0039, 1/8) and at TE the two tie. **NF-W7d's "Σ_played
  was the costly half" was true of the split-OFF row and does not transfer to the split-ON row.**
  A bundled comparison against the incumbent alone would have read RB and TE as clean wins
  (+0.0078 8/8, +0.0016 7/8) — registering `mix_played` as a CONTEST foil is what makes the record
  say "not the best construction available at RB" instead.

### 12.2 ⭐ QB: the CRPS claim is earned, the calibration is not — and the smoke observation reproduced

- Every clause is green at QB except PIT: the arm beats BOTH foils 8/8, DSR 0.9999, oracle floors
  respected and ACTIVE, π permutation loses, coverage 0.831. Refused by the bar alone ⇒
  `CONSTRAINT_REFUSED`, no data trigger (§8).
- ⭐ **The all-rows Σ moved QB's PIT the WRONG way: 0.0595 (`mix_played`) → 0.0648 (+0.0053)**,
  even though the assembled total carries MORE zero mass (0.302 vs 0.296 — vs a realized 0.516). The
  decile vector is the same under-priced-atom shape ([0.162, 0.139, 0.117, …, 0.090], worst
  decile 0). The smoke's §11.1 observation reproduced in direction at 4,000 draws (smaller
  magnitude). Reading: Σ_all carries the availability co-movement AND the split installs an
  explicit atom — the joint layer prices availability twice; CRPS rewards the sharper conditional
  draw, PIT punishes the double-pricing. `assembled_comonotone` still posts the best PIT in the QB
  field (0.0563) for the third run running and still loses CRPS by 0.11 — the §4 discipline
  (PIT gates, never ranks) did real work again.
- ⭐⭐ **THE ATOM-CAP CONFIRMATION, plainly:** the installed atom is Σ-invariant to the last digit
  (0.267125 under Σ_all and Σ_played, max fold gap 0.0); the marginals ADMIT at most 0.2687 of
  atom against a realized all-zero rate of 0.5162 (shortfall 0.2475, the clamp binding on 91.7% of
  rows); and with every joint-layer knob now exercised — split on/off × Σ_all/Σ_played across
  NF-W7c/W7d/W7e, plus the comonotone ceiling — the best PIT any real arm posts at QB is 0.064.
  **QB is BLOCKED AT THE MARGINAL LAYER. No joint-layer story clears it. The QB roadmap moves to
  the 52-cell substrate** — specifically the QB cells whose own zero mass is smaller than the
  realized all-zero rate (they cap `1 − min_i P̂_i(0)`); a marginal that admits the atom is the
  precondition for any assembled QB distribution to be calibrated.

### 12.3 RB / TE: read WHICH FOIL the null is against (NF-W7c §11.4, again)

`classify_null` names the foil. At RB and TE the binding foil is `mix_played` — NF-W7d's own arm —
so `GENUINE_ABSENCE` says *"the all-rows Σ is not better than the active-rows Σ, with the split
on, at this position"*; it does NOT say the split is dead (the split over Σ_all is +0.0078 8/8 at
RB, +0.0016 7/8 at TE against the incumbent). TE is a **tie** (CI spans zero, 4/8), which the
two-way state word cannot express (NF-W2e's three-way lesson). RB's DSR 0.0076 / TE's 0.0036 are
negative-delta arithmetic (trial SRs all negative), not a field-dispersion artifact.

### 12.4 WR: the first shippable assembled arm at WR (deploy-held)

NF-W7c certified TE only. `mixall_learned` at WR clears every clause: +0.0034 vs the incumbent
8/8, +0.0018 vs `mix_played` 7/8, PBO 0.0, DSR 0.985, BH-FDR pass at family size 4, coverage
0.867 vs the 0.80 floor, PIT 0.0145 (perfect-calibration median 0.0135 at this n — i.e.
indistinguishable from calibrated), oracle floor RESPECTED and active, degenerates and both
permutations lose. Deploy-held: an NF-G0 challenger, served by nothing until governance promotes.

### 12.5 What the successors are (registered FORWARD, never selected here)

1. ⭐ **A MARGINAL-layer story for QB** on the 52-cell substrate — the cap `1 − min_i P̂_i(0)` is now
   measured at 0.2687 vs a 0.516 realized atom; the cells that bind it are identifiable from the
   served map (the leg with the least zero mass on each row). This is the ONLY route to a
   calibrated assembled QB distribution.
2. **The Σ population as an in-fold, per-position choice** — the 2×2 says the better joint
   construction is Σ_all at QB/WR and Σ_played at RB (TE a tie). ⛔ Picking per position from this
   record is post-hoc; a legitimate successor selects the population IN-FOLD (validation-chosen,
   the NF-D20 shape) and scores it against both incumbents.
3. **`mix_played` at RB (and TE)** — NF-W7d's arm is the better construction at RB by this record's
   own measurement and can only ship through a fresh registration there (as NF-W7d §5 permits for a
   report-only win) — but the honest count is that this line has now spent three stories on the
   same folds, and a PM decision on whether a fourth is warranted belongs to the roadmap, not here.

### 12.6 Anchors and controls, all green

Reproduction exact ×3 at every position; `atom_is_sigma_invariant` gap 0.0; `mixture_is_active`
(atom 0.26–0.39) and `mixture_preserves_marginals` (drift ≤ 0.0047 vs 0.01) pass on measurement;
all four degenerates lose everywhere (nearest: `assembled_comonotone`, by 0.03–0.11); the label
permutation and the π permutation lose everywhere; all per-form oracle floors RESPECTED (the
learned-π peek acts: gains 0.0023–0.0146); the activity positive control peeks 0.69–1.04; the
three inherited dependence clauses pass ×4. ⇒ every verdict above is a measurement, not an
artifact of a harness that could not have seen the effect.

Process note (recorded so it is not repeated): the decisive run was launched in-session after the
smoke and STOPPED by the operator under the >2-minute rule; the operator ran it. A predecessor
session having run its own decisive run is not a precedent.
