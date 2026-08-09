# MLB batter props — PHASE-2 pre-registration (pricing bake-off)

**Committed BEFORE the run** (the NF-D20 discipline). `best_alpha = 0` — this is a PRICING and
CALIBRATION product. It makes **no edge, win-rate, or beat-the-market claim**, and nothing here
auto-deploys (deploy-held; Phase 2 ships no serving change either).

Phase 1 (this branch) delivered the substrate. This document registers what Phase 2 may do with
it, and — more importantly — what would make Phase 2 a recorded **NULL**.

---

## 0. What Phase 1 actually established (the premise, measured not assumed)

The story brief assumed batter prop lines still had to be bought. **They do not.** All six batter
markets were already fully backfilled in S3 to the Odds API historical floor:

| market | S3 date-partitions | span | rows | events | players |
|---|---|---|---|---|---|
| `batter_hits` | 721 | 2023-05-03 → 2026-08-08 | 990,612 | 6,926 | 1,215 |
| `batter_home_runs` | 722 | 2023-05-03 → 2026-08-08 | 852,038 | 6,926 | 1,212 |
| `batter_total_bases` | 721 | 2023-05-03 → 2026-08-08 | 1,106,508 | 6,922 | 1,207 |

⇒ **the Phase-1 credit spend is 0.** The cost-scoping exercise the brief asked for resolves to
"buy nothing"; re-pulling would have been pure waste. Details + the forward-cadence caveat are in
the session handoff.

Substrate: `scripts/build_batter_prop_substrate.py` →
`s3://baseball-betting-ml-artifacts/baseball/research/batter_prop_substrate/batter_prop_substrate_v1.parquet`
Grain: one row per `(game_pk, batter_id, market_key)`.

---

## 1. Frame (binding; a Phase-2 run may not renegotiate these)

- **Population**: batter-games that carry at least one pregame prop quote in the market being
  modelled. ⚠️ This is a **selected** population, not all batter-games — books quote better
  hitters. Measured 2025: substrate mean hits **0.872** vs the all-batter-game population
  **0.822**. Every figure is conditional on "the market quoted this batter"; a claim about all
  batters is out of scope.
- **Seasons**: 2023 (from 2023-05-03) – 2026.
- **Leakage contract** (enforced in the builder, not asserted in prose):
  - prop lines: only snapshots with `snapshot_ts < commence_time`; the **latest** such snapshot
    per (event, book, player, line) = the closing line.
  - `mart_batter_rolling_stats` windows are `RANGE … PRECEDING AND CURRENT ROW`, i.e. **inclusive
    of the labelled game** — they are **lagged one game per batter**. Using them unlagged leaks
    the label outright.
  - `eb_batter_posteriors_raw` is already pregame (confirmed-lineup build) and is used as-is.
  - park factors joined on the **prior** season.
- **Folds**: expanding-window **half-season blocks**, purged + embargoed at the block boundary
  (2023H2, 2024H1, 2024H2, 2025H1, 2025H2, 2026H1) ⇒ **6 gated folds**.
  ⭐ Registered deliberately as half-seasons, not seasons. Season blocks would give 3 folds, and
  per MH2 the maximum attainable DSR at 3 observations is **0.977** against a 0.95 gate — i.e. the
  gate would be a statement about the design before it was one about the model. The fold count is
  a **window choice**, and this registration spends it up front rather than discovering later that
  the null was structural.

---

## 2. Targets — three separate models, registered separately

| market | target | mean | median | % zero | MAE-inversion risk |
|---|---|---|---|---|---|
| `batter_hits` | hits/game | 0.872 | 1 | 39.8% | lower (median > floor) |
| `batter_total_bases` | total bases/game | 1.441 | 1 | 39.8% | lower (median > floor) |
| `batter_home_runs` | HR/game | 0.124 | **0** | **88.4%** | **HIGH** |

All three are **counts**, so the predictive is a **discrete distribution**, not a point estimate.

---

## 3. Selection metric — and why it is not MAE

**Primary: CRPS** (lower better), per market, pooled over rows within a fold then averaged over
folds.

⛔ **MAE is forbidden as the primary.** NF-D11: MAE is minimised at the conditional median, so on a
cohort whose conditional median sits at the floor it **pays for pessimism** and a
"predict zero for everyone" arm can win outright. NF-D14 refined the test — the trigger is **not**
"zero-heavy", it is **the conditional median being at the floor**. Measured above, `batter_home_runs`
has median 0 (88.4% zeros) and is squarely in the inverting regime; hits/TB have median 1 and are
not. This registration therefore does **not** reason about which markets will invert:

> ⭐ **The degenerate ceiling is SCORED EVERY RUN, for EVERY market, and its score is READ.**
> That is the NF-D14 rule precisely — don't predict whether MAE inverts, measure it.

**Secondary / reported, never selecting**: randomized-PIT flatness (max-decile deviation) as the
discrete-calibration check per E2.1-r; interval coverage as a **FLOOR**, ⛔ never as a target to
minimise distance to (E2.1-r's inversion; NF1.8's "a constraint a degenerate satisfies is fine, a
criterion a degenerate wins is fatal").

---

## 4. Anchors — two-sided, per-form, and non-vacuous

| anchor | role | registered expectation |
|---|---|---|
| `oracle_floor` | peeking, **same family AND same sample** | nothing beats it |
| `degenerate_zero` | predict 0 with probability 1 | **must lose CRPS**; expected to WIN MAE on HR |
| `degenerate_marginal` | the market-wide marginal count distribution, no per-batter content | must lose |
| `matched_n_candidate` | the winner's own arm trained on one prior block | oracle must beat it |

Binding rules carried in from the §0.5 record:

- **NF1.7 (a)** — an anchor that fails to fit **raises**; it is never treated as a pass. A `None`
  anchor makes its check vacuously true, which is the failure mode this row exists to prevent.
- **NF-D16 (g‴)** — where candidate forms **nest**, the peeking ceiling is computed **per form**.
  One ceiling for the whole field would veto a legitimately-better nested form as a false metric
  inversion.
- **NF1.9 (f)** — the oracle is a floor only at **matched n**; hence `matched_n_candidate`.
- **⭐ Anchors are DIAGNOSTIC and are excluded from the DSR trial field** (MH2.1 (a)): an
  `oracle_floor` that sees the target has a huge per-fold Sharpe and, left in `V`, sets the gate's
  own bar for a purely arithmetic reason.

---

## 5. Market-blind — what the de-vigged line is and is not

⭐ **The de-vigged market probability is a BENCHMARK, never a fit target.** No arm may take
`p_over_consensus`, `line_consensus`, or any book price as a **feature**. The model prices
`P(over)` from pregame baseball features alone; the market is what it is **graded against**.

`best_alpha = 0`: no bet, no edge claim, no ROI figure. "Our number differs from the market" is
**not** a finding this story may report as value.

**Measured market behaviour** (2025, from the substrate) — the benchmark to be calibrated against:

| market | n | pred P(over) | observed | Brier | max abs bin gap |
|---|---|---|---|---|---|
| `batter_hits` | 39,692 | 0.5700 | 0.5528 | 0.2380 | 0.030 (populated bins) |
| `batter_total_bases` | 39,750 | 0.4991 | 0.4766 | 0.2434 | 0.035 (populated bins) |
| `batter_home_runs` | 37,700 | 0.1368 | 0.1066 | 0.0944 | 0.043 |

The de-vigged market tracks realized outcomes **monotonically across every populated bin**
(hits: 0.35→0.32, 0.46→0.41, 0.56→0.54, 0.64→0.63). Two consequences:

1. This is the **join-correctness proof** for the whole substrate — a mis-joined player or game
   would flatten these bins. It is reported as such, not as a modelling result.
2. There is a **persistent ~2–3pp negative gap** (the market's de-vigged `P(over)` slightly
   overstates the over) in all three markets. That is a **level** effect and it is the honest,
   registered target of Phase 2's calibration work.
   ⚠️ **NF-D15 (g′) binds here**: to attribute any improvement to a level mechanism, the run must
   register a **matched level-only foil** and read the **bias signature** — a genuine level
   correction moves pooled bias **toward** zero. "My arm won" is not "it won for the reason I
   said." A residual-vig explanation and a market-bias explanation are **not** distinguishable
   without that foil, and this registration does not assume which it is.

---

## 6. Candidate model classes (≥3, per §0.5 — a bake-off, not one architecture)

Pre-registered, hypothesis-driven, **not** an open search:

1. **Poisson / Negative-Binomial GLM** on the lagged rate features (the direct-learned foil).
2. **Hurdle / zero-inflated NB** — registered specifically because HR is 88.4% zeros. Its
   *matched foil* is the plain NB, so the zero-inflation component earns its place by a paired
   delta (NF-D10 (g)), not by a leaderboard rank.
3. **Gradient-boosted distributional learner** (NGBoost / LightGBM multi-quantile).
   ⚠️ `NGBRegressor(random_state=…)` **does not seed its base learner** — the global RNG must be
   seeded or identical specs disagree by up to 0.30 in per-game σ.
4. **PA-decomposition structural model** — draw PA count, then a multinomial over
   {1B, 2B, 3B, HR, other}. `betting_ml/utils/prop_pricing.draw_batter_bases_hits` already
   implements exactly this and is the natural reuse of the E2.x machinery. It is **one candidate
   among several**, always with the direct-learned foil (2) beside it — a prescribed structure
   never wins by prescription.

Feature selection is **pre-registered and in-fold** (bounded, hypothesis-driven; never an open
subset search, never peeking at the eval fold), and **every configuration counts toward
PBO / DSR**.

---

## 7. Deflation gates

- **PBO < 0.2**, reported with the three NF1.8 companions — the **flip distribution**, Bailey's
  **performance degradation**, and the **contender-set** spread — because a rank statistic alone
  cannot tell a tie from a loss, and a spread over a field containing its own nulls measures the
  nulls.
- **DSR > 0.95** via `dsr_gate(...)`
  (`betting_ml/scripts/e7_9_train_serve_consistency.py`), observations = **folds**,
  `trial_sharpes` measured from each arm's own per-fold skill series.
- ⭐ **DSR-CONV declared FORWARD, here, before the run**: the degenerate arms named in §4
  (`degenerate_zero`, `degenerate_marginal`) are passed as `degenerate_arms=` — they stay in
  `n_trials` (we did try them) and are **excluded from `V`**. This is legitimate **only** because
  they are declared as designed losers **now**; ⛔ applying it after a failed gate would be
  laundering (E2.1-r), and ⛔ an arm qualifies **by design, never by declaration** — exclusion is
  **non-monotone** and can *raise* the bar. Both figures (`dsr` and
  `dsr_with_degenerates_in_V`) are reported every run; `dsr` binds.
  ⚠️ DSR-CONV does **not** rescue a small-fold null — that residue is the `√(n_obs − 1)` penalty,
  which is why §1 buys 6 folds rather than 3.
- **BH-FDR** across the three markets (3 hypotheses), reported alongside the pooled
  single-hypothesis p so that a multiplicity-bound null is distinguishable from an absent effect
  (NF-D15 (g″)).

---

## 8. What makes this a NULL, and how it gets classified

A null is the expected, publishable outcome. It is classified with
`betting_ml/utils/cv_power.classify_null` into the seven MH2 states, **plus** the
`CONSTRAINT_REFUSED` family (NF-D18) for any anchor/registration-driven refusal —
`classify_null` has no state for those and mislabels them `POWER_LIMITED`, which would emit an
actively misleading "re-test with more seasons" trigger.

Two guards on the classifier's own output:

- **MH2.2** — a `DSR-UNREACHABLE` / "smaller field" remedy is valid only if the smaller field was
  itself pre-registered. ⛔ Never shrink below the declared family.
- **State the margin in the unit that grows** (folds / half-seasons / rows) and say whether it is
  reachable **now**. A trigger reachable by a wider window is a live re-test; only a
  calendar-bound one is a future note.

**Registered a-priori expectation**: the market is a strong, well-calibrated benchmark (§5). The
honest prior is that a market-blind model **does not** out-price it, and that Phase 2's
publishable result is a **calibration characterisation** — where our distribution is sharp and
honest, and where it is not. An arm that fails to beat the market is **not** a failed story.

---

## 9. Known substrate limitations Phase 2 must carry (not discover)

1. **HR de-vig is effectively single-book.** Two-sidedness is a **book property**, not noise:
   betmgm ~99%, draftkings ~99.9%, pointsbetus/unibet_us 100%; fanduel, williamhill_us,
   mybookieag **0%** (they offer the one-way "anytime HR" form). Across the whole HR market only
   **33.2%** of quotes are two-sided, and the substrate's mean books-per-quote is 5.16 while mean
   **two-sided** books is **0.95**. So `p_over_consensus` for HR rests on ~1 book even though
   `line_consensus` uses ~5. `n_books_two_sided` is carried on every row — **any HR calibration
   claim must condition on it**, and a "consensus" framing for HR would overstate the evidence.
   (hits 75.7% / TB 81.2% two-sided at quote level are comfortable.)
2. **~3% of prop events never resolve to a `game_pk`** (§ handoff). Unresolved events are dropped,
   not guessed. This is not missing-at-random and should not be characterised as such without
   checking.
3. **~5.3% of batter-games are switch-hitters** whose upstream rolling-stat rows are
   hand-conditional and were collapsed PA-weighted (see the builder). The season-to-date `_std`
   features are therefore a reconstruction, not a stored value.
4. **The population is market-selected** (§1).

---

## 10. Explicitly out of scope for Phase 2

- Any serving change, any surfacing in the app (deploy-held).
- Any edge / ROI / win-rate claim (`best_alpha = 0`).
- Any use of book prices as model features.
- Re-deciding any recorded verdict elsewhere in the program with DSR-CONV.
