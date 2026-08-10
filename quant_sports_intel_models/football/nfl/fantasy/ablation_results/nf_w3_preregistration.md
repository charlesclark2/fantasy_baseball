# NF-W3 — pre-registration (game environment: team play-volume + pass/rush allocation)

**Committed BEFORE the full run.** Everything decidable in advance is a CONSTANT in
`game_environment.py`; this file is the narrative copy of those constants. The runner READS the
module (the NF-D16 discipline) — nothing below may be chosen after seeing a score.

`best_alpha = 0` · projection product · **deploy-held** (serving = NF-W8 / NF-C6 Ph2). This story
promotes nothing, publishes nothing, retrains nothing.

---

## 1. What is being modeled, and why it is TWO layers

NF-W3 is the first V1 **component** of the v3 weekly system (doc §2): the game environment sits at
the top of the causal chain `environment → volume → allocation → availability → opportunity →
efficiency`. It emits, per team-game, a **distribution** (not a point) for:

| target | definition | family |
|---|---|---|
| **T1 `off_plays`** | count of scrimmage plays with `posteam = team` and `play_type ∈ {pass, run}` | count |
| **T2 `pass_share`** | `pass_plays / off_plays`, `pass_plays = count(play_type='pass')` | rate/share on a known denominator |

The `play_type` split is chosen because it is the one that composes downstream: `play_type='run'`
**is** team carries (designed runs + QB scrambles) and `play_type='pass' − sacks` **is** team pass
attempts, which is exactly the pair NF-W5 needs. Sacks are reported as a diagnostic, not gated.

Measured on the modeled span (2016–2025 REG, 5,278 team-games): mean 62.4 plays (sd 8.4), mean pass
share 0.583 (sd 0.105), with a real era drift (63.3 plays in 2016 → 60.5 in 2025) that the foils are
free to exploit.

**Layer A** is the component bake-off — does either target beat its own honest baseline?
**Layer B** is ⭐ **the gate that decides whether NF-W3 is worth anything**: does the environment
layer improve the *assembled player projection* against the **NF-W1 `lgbm_hurdle` champion** as the
permanent direct foil (doc §10.3)? A component that wins Layer A and loses Layer B is a **recorded
null, not a served model** — captured-stays-captured. Both verdicts are reported; neither is
allowed to stand in for the other.

## 2. Binding NF-W0 constraints (inherited, non-negotiable)

1. **Allowed feature contract only.** NF-W3 consumes exactly three of the ten certified families —
   `game_context`, `team_environment`, `opponent_matchup` — all lagged nflverse `pbp` / `schedules`.
   Every column is named `<family>__<detail>`; unknown provenance is a **rejection, not a warning**.
2. **Era.** ⛔ No `pbp_participation`-derived leg is used **at all** (the 2023 provider replacement
   means pressure/coverage/route rates may not be pooled across the boundary). Honored by
   exclusion and enforced by `ERA_FORBIDDEN_TOKENS`, not by a comment.
3. **PIT.** `assert_point_in_time` (NF-W0a) is invoked at the team-game assembly boundary, per
   target week, fail-closed: a week whose window cannot be proven clean is DROPPED and counted.
4. **⛔ No `fillna(0)`.** A missing lagged window (a team's first games in the span, a
   prior-season column for an expansion/relocation-renamed franchise) is **NaN**, never 0 — 0 plays
   is a legal, meaningful value. Learners that cannot pass NaN use TRAIN-fitted **median**
   imputation as a device inside the arm, with the presence pattern carried by
   `team_environment__games_prior_season`.
5. **⛔ Banned as features:** markets (spread/total/moneyline/`vegas_*`), weather, depth-chart rank,
   game-day inactive status. The realized-weather trap (`schedules.temp`/`wind`) is excluded by
   never reading those columns.
6. **Roster-first frame.** Layer B scores on the NF-W0 certified player-week frame
   (`v1.nflverse.stats_player_week`, 46.1% retained zeros) — ⛔ never `stats_player_week` directly,
   which deletes the zero atom.

## 3. Design (identical fold axis to NF-W1 — that is what makes Layer B a matched comparison)

- **Grain / span:** team-game, 2016–2025 REG.
- **Folds:** the NF-W1 blocks verbatim — 8 expanding-window half-season test blocks
  (2022H1 … 2025H2), train = every row at least `PURGE_WEEKS = 2` **global weeks** before the
  block's first week. Purged/embargoed over WEEKS, never a shuffle. 2016–2021 is burn-in.
- **Predictive representation:** a 39-level quantile vector (`Q_LEVELS`), identical for every arm
  and both layers, so a single reducer scores everything.
- **Selection metric: CRPS** (`crps_q39`, the 2×mean-pinball identity). ⛔ **MAE never selects and
  never gates** — reported only.

### 3.1 Field (pre-registered; a family may not be discovered later — MH2 (a))

**Layer A real arms — 4 structurally different classes per target:**

| target | arms |
|---|---|
| T1 `off_plays` | `pois_glm` (Poisson GLM, log link → Poisson quantiles) · `negbin_glm` (NB2 GLM — the overdispersion *hypothesis*, refit under a MoM-estimated dispersion, not a hardcoded decision) · `lgbm_quantile` (distributional boosting) · `knn_quantile` (nonparametric neighbourhood) |
| T2 `pass_share` | `binom_glm` (binomial logistic GLM) · `betabinom` (beta-binomial — overdispersion) · `lgbm_quantile` · `knn_quantile` |

⚠️ **T2 is UNCONDITIONAL on the realized denominator.** The obvious binomial formulation
(doc §2.3, `PassAttempts ~ Binomial(n_g, p_g)`) evaluates the share *given* the game's realized play
count — but the realized count encodes game script (a trailing team both passes more and runs more
plays), so letting it into a T2 arm's features or its test-time trial count would hand every arm a
value serving does not have. Therefore: the realized `off_plays` is used **only as the binomial
weight in TRAINING** (labels are known in train — no leak), and at TEST time the binomial /
beta-binomial arms use the lagged `team_environment__off_plays_l4`, **rounded to an integer**, as
the trial count (`scipy`'s `binom`/`betabinom` return NaN for a non-integer `n`, and a 4-game
rolling mean is non-integer almost always — a detail that is load-bearing, not cosmetic). Sampling the
denominator from T1 and then the share from T2 remains the correct *simulation* composition
(doc §8 steps 2–3); it is simply not how the component is **scored** here.

**Foils (must be beaten; never shippable), mirroring NF-W1's pair:** `foil_team_eb` (the team's own
EB-shrunk lagged level, κ = 4 team-games, + an empirical residual bank — the team-grain analogue of
"season ÷ games") and `foil_team_eb_matchup` (that level × a clipped opponent multiplier — the
"spread by a matchup adjustment" analogue, which also tests whether opponent adjustment is worth
anything at all at this grain). The **best** foil binds.

**Anchors (diagnostic — excluded from the PBO matrix and the DSR trial field, MH2.1 (a)):**

- `nihilist_zero` — the literal all-zero degenerate. Scored because the rule is *measure it, never
  reason about it* (NF-D14), and reported as such even though it is trivially terrible here.
- `marginal_train` — the train marginal quantiles (league climatology, the "all-mean" analogue).
  Conditioning must beat it.
- `zero_width` — point mass at the foil's point (maximally sharp). Must LOSE.
- `max_width` — the foil bank ×3 (satisfies every coverage floor). Must LOSE. A constraint a
  degenerate satisfies is fine; a **criterion** one wins is fatal (NF1.8).
- `permuted_within_week` — the winner's own estimator with the target permuted **within global
  week**, destroying team identity while preserving every week-level marginal. Must lose, **and**
  its lift over the foil must not be significant.
- `oracle_<arm>` — **one peeking oracle PER ARM, of that arm's OWN form** (NF-D16 (g‴)): the same
  estimator fit ON the test block. A single shared ceiling would veto a legitimately-better nested
  form as a false metric inversion.
- `matched_n_<arm>` — the arm trained on a single block-sized recent window (NF1.9 (f)), so an
  arm that beats its own oracle can be checked against capacity rather than assumed to be leaking.

**Layer B field (exactly two arms, declared here and never trimmed or grown — MH2 (a)):**
`champion` = the NF-W1 `lgbm_hurdle` spec on `WP.FEATURES` (the permanent direct foil) versus
`champion_env` = the identical estimator with the NF-W3 environment block appended. Anchors:
`champion_env_shuffled` (env columns permuted across teams within week — must not help) and
⭐ `champion_env_oracle` (the **realized** week-w team/opponent volume and pass share substituted
for the projections) — a peeking **upper bound on everything the environment chain can buy at the
player level**. If even the oracle does not move player CRPS, no amount of environment modeling
helps the direct projection, and that reshapes NF-W5/NF-W8. It is an anchor, never a trial.

### 3.2 The Layer-B env block, and how its train-row values are produced

Injected columns (provenance-clean, all derived from the same lagged pbp):
`team_environment__proj_off_plays`, `__proj_pass_plays`, `__proj_rush_plays`, `__proj_pass_share`,
`__proj_off_plays_sd`, `opponent_matchup__proj_opp_off_plays`, `__proj_opp_pass_plays`.

⚠️ **A projected feature must be a PROJECTION on both sides of the fold or the player model learns
to trust a value serving will never have.** So: TEST-row env values come from the NF-W3 winner fit
on the whole fold-train; **TRAIN-row env values come from leave-one-season-out refits inside the
training window**, so a train row's environment feature is out-of-sample for the env model too. The
residual in-sample optimism this leaves is small and biases the gate **against** NF-W3 (the player
model would over-trust a feature that is noisier at serve time) — declared here, in that direction,
before the run.

## 4. Gates

Per target (Layer A) and per position (Layer B), **all** of:

1. `beats_foil` — winner beats the best foil on mean fold CRPS (Layer B: beats `champion`).
2. `fold_consistency` — `cv_power.fold_consistency_clause(8)` ⇒ **6 of 8** fold wins required
   (calibrated, false-fire ≤ 0.20; attainable at 8).
3. `pbo_ok` — PBO < 0.20 over the **eligible** set (real arms + foils; Layer B: the two arms).
4. `dsr_ok` — DSR ≥ 0.95 over the declared real family.
5. `fdr_ok` — BH at q = 0.10. ⭐ **Two families are declared, and the STRICTER reading binds:** the
   component family {T1, T2} and the downstream family {QB, RB, WR, TE} are corrected separately
   *and* the pooled 6-hypothesis correction is computed; a SHIP must survive **both**. This is
   deliberately conservative so no verdict can turn on which family was chosen (MH2 (a) — you may
   pre-register a family, you may not discover one).
6. `degenerates_lose` — `nihilist_zero`, `marginal_train`, `zero_width`, `max_width` all lose.
7. `permutation_behaves` — the winner beats the permuted arm **and** the permuted arm's lift over
   the foil is not significant. ⛔ **Fails CLOSED on a `None` p-value** (an unevaluable clause is
   never a pass — NF1.7 (a)).
8. `oracle_floors_respected` — the per-form peeking floor, enforced **at matched n** (NF1.9 (f)):
   for every arm, either the arm loses to the peeking version of **its own form**, or that oracle
   beats the same form trained on a block-sized sample (`matched_n__<arm>`) — i.e. an arm may beat
   its own oracle only when the gap is **capacity**, not leakage. The STRICT reading
   (`no_arm_beats_own_oracle`) is reported beside it so nothing hides behind the admission.
   ⚠️ Limitation stated up front: `matched_n` matches the oracle's SAMPLE SIZE but not its ERA (it
   is the most recent block-sized slice of train, the oracle is the test block itself), so the
   control bounds capacity and recency together, not capacity alone.
9. `coverage_floor_ok` — the winner's central-80% coverage is a **FLOOR, never a target**;
   blocking only when the shortfall exceeds 3 binomial SE (NF1.8 rows-not-decimals).

A failure is classified by `cv_power.classify_null`, **except** when every statistical gate passes
and only anchor/registration clauses fail — that is the `CONSTRAINT_REFUSED` family and is
hand-classified with **no sample-size re-test trigger** (the NF-D18 / MH2.7 instrument gap, which
has now mis-fired twice in this vertical).

**Power is checked in advance, not after:** at 8 folds the fold clause is attainable (6/8), PBO is
evaluable (≥4 folds), the sign floor is 0.0039 < the 0.10 BH cutoff, and `dsr_ceiling(8) = 0.9999`
against a 0.95 gate. **No gate is structurally unattainable**, so a null here is a real finding
rather than a design artifact.

## 5. Verdict vocabulary

Every direction word is **three-way and DERIVED, never stored** (NF-W2e): `BEATS` / `TIES` /
`LOSES TO`, failing closed to `TIES` when the interval is absent or unevaluable, and the word and
its parenthetical are computed together so they cannot contradict each other.

The headline is the pair `(layer A verdict per target, layer B verdict per position)`. ⭐ The
**story's answer** is Layer B: *NF-W3 is served only if the assembled projection improves.*

## 6. What this story explicitly does NOT do

- No serving, publishing, registry write, S3 write, or retrain (guard-scanned).
- No touchdown / drive-outcome / red-zone volume model (doc §2.2's wider target list) — those are
  NF-W6's, and adding them here would inflate the trial field that deflates this one.
- No coaching / play-caller identity features (NF-D10 found that family inert on the season board;
  re-registering it here would spend multiplicity on a measured null).
- No market, weather, or props anchor — all four are in the NF-W0 **deferred** contract.
