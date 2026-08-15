# NCAAF-P2.1 — game-model structural refinement: design, verification and handoff

**Status (2026-08-15): ✅ COMPLETE — the full battery ran (22 configs × 8 folds × 8,325 games).
Verdict `REFERENCE_STANDS`. All six anchor checks passed, so the run is interpretable.** Results are
in [§9](#9-results) below and in the auto-generated `ncaaf_p2_1_structural_battery.md`; this document
is the design + verification companion, the same split P1.4 used.

**One-line result:** of 16 pre-registered structural hypotheses, **15 are nulls and one (`pace`)
is a real, reproducible effect that cannot clear deflation at any fold count or field size**. The
top-prior hypothesis — H1, team/venue HFA, registered as "the biggest clean win" — is a **tie**, and
its per-team variant is actively harmful.

**Pre-registration:** [`ncaaf_p2_1_preregistration.md`](./ncaaf_p2_1_preregistration.md) — written
and **committed before the first hypothesis was scored** (commit `b9951df3`). That commit ordering is
the E1.11/E13.16 anti-mirage artifact and is the reason this battery's eventual verdict — survivor or
null — is trustworthy rather than merely computed.

---

## 1. The structural verification — the session's substantive finding

The story required verifying each hypothesis *against the actual model* rather than the spec. The
spec describes `margin = hfa + (θ_home − θ_away)`, `θ = μ_conf + Zβ + u` with an offense/defense
split. **That is NCAAF-P1.2 (`team_strength.py`), not the P1.4 game model.** P1.4 fits a learner on a
feature matrix to predict (μ_margin, μ_total); the P1.2 ratings enter only as *features*. Six premises
changed on contact with the code, and three of them change what the battery tests.

### V1 — the shipped model has NO home-field term at all ⭐

The shipped reference is `ridge / strength_only / strength_posterior`. `strength_only` resolves to the
25 columns prefixed `home_strength*` / `away_strength*` plus `strength_margin_diff`.
**`is_neutral_site` is not among them**, and `strength_margin_diff` is a *rating difference* carrying
no home-field component (P1.2 estimates `home_field` as a separate fixed coefficient that never
reaches the P1.4 matrix).

⇒ The ridge **intercept** absorbs a single constant home bump, blended over a training mix that is
**7.93 % neutral-site (660 games)**. The shipped model gives a neutral-site bowl game the same home
bump as a genuine road trip. H1 is therefore a *stronger* hypothesis than the spec stated — not
"replace a constant HFA with a per-venue one" but "there is no HFA term to replace."

### V2 — H2's stated premise is FALSE; the real gap is the interaction ⛔

The spec says the spread "runs on NET `strength_margin`, so two same-net teams with opposite profiles
get an identical spread." **`home_strength_offense`, `home_strength_defense` and their away twins are
all already in `strength_only`** as linear terms, so opposite profiles already produce different
spreads. What a ridge structurally *cannot* express is the **interaction** — a strong offence facing a
weak defence being worth more than the sum of the two levels. H2 is re-scoped to the product term, and
the correction is recorded here rather than quietly absorbed.

### V3 — no P1.4 arm ever saw a bowl flag

`is_postseason` sits in `_ID_COLS`, so it is excluded from **every** P1.4 contract — none of the 125
configs in P1.4's search could condition on the postseason regime. 441 bowl/playoff games (5.30 %).

### V4 — H12 answered: garbage time IS excluded, but score-margin-gated, not WP-gated

`fact_ncaaf_play.is_garbage_time` = score margin > **43/37/27/22** by quarter. That is the repo's one
definition, applied everywhere. It is *not* the win-probability gate P1.1's NFL flag used
(WP ∉ [0.05, 0.95]). The `*_clean_*` (excluded) variants exist and are **not** in `strength_only`, so
H12 is a genuine matched clean-vs-raw pair — and the answer to the story's literal question is
recorded above.

### V5 — H10 (weather) is NOT REGISTERED ⛔

The story said to confirm venue weather is available first. It is not: CFBD `/games` `raw_json`
carries no weather keys, `ingest/sources.py` defines no weather source, and the P1.3 matrix has no
weather column. A hypothesis that cannot be measured must not enter the deflation field — registering
it would spend multiplicity on a config that can never be scored. Recorded as a **data-unavailable
scope finding**, not a null.

### V6 — the doc §6.2 compact set is only 4/9 constructible from the matrix

| doc §6.2 interaction | in the P1.3 matrix? |
|---|---|
| rush-off vs rush-def | ✅ `off/def_line_yards`, `off/def_stuff_rate` |
| explosiveness gen-vs-allowed | ✅ `off/def_explosiveness` |
| pace | ✅ `seconds_per_play`, `off_plays_per_game` |
| run/pass stylistic conflict | ✅ `rushing/passing_yards_per_game` |
| **pass-off vs pass-def** | ❌ `completion_rate`/`passing_yards_per_game` are OFFENSE-ONLY |
| **standard / passing downs** | ❌ no down-split column |
| **havoc** | ❌ |
| **finishing drives vs red-zone-D** | ❌ `points_per_drive`, `scoring_opportunity_rate` are offense-only |
| **pressure susceptibility vs generation** | ❌ no sack column |

⚠️ **Source caveat, stated because it is easy to misread:** the 2026-08-03 stress-test doc itself
(`ncaaf_model_current_state_evaluation_and_recommendations.md`) is **not in this repo** — `find`
returns nothing for it or for the pushback response. The §6.2 compact set above was taken from the
**verbatim enumeration inside `ncaaf_story_prompts.md`'s P2.1 cross-ref**, which lists all nine
interactions by name, so the registered set is complete with respect to that list. What I could
*not* read is doc **§5** (the fuller hierarchical-HFA bake-off), which the cross-ref only describes
as "compatible" — so H1a/H1b/H1c are built from the story's own H1 wording plus the V1 code finding,
and may not match whatever §5 specifies in detail. If §5 matters, it should be located before the
H1 result is read as a verdict on the doc's proposal rather than on this battery's own H1.

An H2b registered on the matrix alone would silently test **half** the doc's set while reporting the
doc's name. The missing five are all derivable from the `plays` Delta (2.20 M plays, 2014–2025,
carrying `playType`, `down`, `distance`, `yardsGained`, `yardsToGoal`, `ppa` and the running score),
so P2.1 builds them (§3) and H2b tests the **full** set.

---

## 2. Design — what makes the verdict readable

**Matched pairs, not a leaderboard.** Every arm is `reference ∪ one block`, everything else
byte-identical (ridge α = 10, form `strength_posterior`, the same 8 season-forward date-purged folds,
the same seed, the same draw count). The read is the **paired delta versus the reference** — NF-D10:
a rank cannot distinguish "my structure is inert" from "my structure is tied."

**CRPS is the selector; calibration is a constraint.** CRPS (proper — grades point *and* spread
jointly) is the §0.5-correct metric for a structural hypothesis, which moves the MEAN; P1.4's
PIT-sum was the right selector for its own question ("which distributional FORM") but is close to
blind to a better mean. It is reported as a secondary. MAE is forbidden (NF-D11/NF-D14).

**Total PIT-flatness is deliberately not a gating clause.** The shipped reference itself fails it
(P1.4 total PITdev 0.0218). Gating on a clause the incumbent fails is the MH2.1(b) inversion — an
incumbent-relative gate inverts exactly when the incumbent is the defective one. Total shape belongs
to **NCAAF-P2.5**; here it is measured and decides nothing. This is pre-registered with its reason,
not discovered afterwards.

**Five anchors, every run.** An oracle floor nothing may beat; a permutation that must lose; two
degenerates that must lose the metric *from opposite directions*; and a matched level-only foil that
decides whether H1b's per-team content earned its win or a global level did (NF-D15 g′). An anchor
that cannot fit **raises** — it is never treated as a pass (NF1.7 a).

**DSR-CONV, declared forward.** `n_trials` keeps the full declared field (reference + 16 arms +
5 anchors = 22); `V` is measured over the non-anchor arms only. Both figures are reported; the
degenerate-excluded one binds. This mattered materially in the smoke: whole-field DSR collapsed to
**0.000** purely because the oracle's improvement Sharpe inflates `V` — the exact MH2.1(a) arithmetic
the convention exists to prevent, visible in a real run rather than argued.

**Nested-form tie guard.** Every arm strictly nests the reference, and a ridge shrinks an
uninformative block toward zero — collapsing the arm onto its own foil. A `|ΔCRPS| < 1e-3` margin is
declared a TIE and refused as a win.

**Null classification.** Every non-survivor goes through
`cv_power.classify_null(declared_field_size=16, degenerates_excluded_from_v=True)`, and the report
reads the machine flag `field_remedy_admissible`, not the prose (MH2.7). A null caused by the
calibration *constraint* rather than by the metric is classified **`CONSTRAINT_REFUSED`** (NF-D18)
and gets **no "more seasons" trigger** — no sampling error accumulates against a hard constraint.

---

## 3. The plays-derived block (H2b + H13) and its leakage guarantee

One DuckDB pass over the `plays` Delta → per-(season, game, team) offence and defence aggregates →
**season-to-date cumulative over strictly prior game DATES** within a team-season. Ordering is by
calendar date, never by `week`: monotone with `season_order_week` and immune to the postseason
`week` = 1 collision, exactly as the P1.1/P1.4 CV axis requires. A week-`w` row therefore cannot see
week-`w` plays, and week-1 rows are NULL by construction. Efficiency aggregates exclude garbage time
using the repo's single definition, so they are directly comparable with the matrix's `*_clean_*`
family.

### A verified-semantics catch worth recording

CFBD's `yardsGained` on a `Punt` row is the **return** yardage, not the punt distance — the gross
appears only in `playText` ("… punt for 36 yds …"). Measured on 2023: mean `yardsGained` **2.09**,
median **0.0**. Taken naively as "punt average" it produced **1.27 yards**, a silently wrong feature
that still looks like a number and would have entered H13 unnoticed. The gross is now parsed from the
play text and the return kept separately, so the net is derivable: **gross 42.0 / return 1.3 / net
40.0**, which is the right order for CFB. A guard pins the parse at the source and the ambiguous name
`st_punt_avg` is retired.

Other sanity readings from the same smoke (2023): offence and defence PPA medians agree to 3 decimals
(0.222 / 0.222) and sack-rate allowed/made agree (0.054 / 0.056) — the symmetry a for-and-against
rollup must satisfy; FG% 0.750.

---

## 4. What was validated in-session, and what was not

**Validated (plumbing, not results):** the full pipeline runs end-to-end on a scoped 5-season /
2-fold smoke — assembly (14 s), all 16 registered arms, all 5 anchors, and `--stage decide`. ⚠️ Those
smoke numbers are **not** findings and appear nowhere in this dossier as such; a 2-fold subset cannot
support a verdict.

**The anchors behaved exactly as pre-registered**, which is the smoke's real payload:

| anchor | smoke reading | pre-registered expectation | |
|---|---|---|---|
| `oracle_peek` | CRPS 1.41 vs best real 18.09 | nothing may beat it | ✅ |
| `permute` | 21.04 > reference 18.15 | must lose | ✅ |
| `zero_width` | 22.61, calib 0.199/0.183 | must lose **and fail** the floor | ✅ |
| `max_width` | 26.75, calib 1.000/0.999 | must **satisfy** the floor and still lose | ✅ |

The `max_width` row is the NF1.8 proof in its exact shape: a constraint a degenerate *satisfies* is
fine, because the metric then eliminates it.

**The smoke also caught a real bug in my own gate.** The first cut read the `max_width` anchor
through the bundled eligibility predicate, so it reported "coverage floor FAILED" at calib **1.000** —
destroying the very proof that anchor exists for. The two clauses (coverage floor, margin-PIT
flatness) are now separately readable, and *both* the clause functions and the **call site** are
pinned by guards.

**Not validated in-session:** the battery on all 8 folds and 11 seasons — that is the operator run in
§6. Until it completes there is no verdict, and none is stated here.

---

## 5. Guards — 23 tests, 9/9 RED-proven

`betting_ml/tests/test_ncaaf_p2_1_structural.py` (fast gate, `football` shard, imports no `pipeline`).
Every load-bearing guard was proven to go RED against deliberately broken source, with the harness
asserting each mutation actually landed before trusting the result:

| deliberate break | guard | |
|---|---|---|
| anchor report reverts to the bundled predicate (**the real bug**) | `…reads_the_coverage_floor_at_the_CALL_SITE` | RED ✅ |
| the coverage-floor clause starts gating on PIT | `…clauses_are_read_separately` | RED ✅ |
| punt gross reverts to `yardsGained` | `…parsed_from_play_text…` | RED ✅ |
| drop the strictly-prior shift (leakage) | `…strictly_prior_games_only` | RED ✅ |
| unfittable anchor returns instead of raising | `…raises_rather_than_returning_none…` | RED ✅ |
| level-only foil stops being level-only | `…foil_is_genuinely_level_only` | RED ✅ |
| garbage-time thresholds drift from the dbt definition | `…repo_single_definition` | RED ✅ |
| `V` measured over the whole field incl. anchors | `…excluded_from_V_but_kept_in_n_trials` | RED ✅ |
| a doc §6.2 pair silently dropped | `…covers_the_doc_items…` | RED ✅ |

⭐ **The RED proof earned its keep twice.** It found the first version of the coverage-floor guard to
be **vacuous** — the test exercised the clause *functions*, while the actual defect lived at the
*call site*, so the guard stayed green through the bug it was written for (NF-D17: a clause is only
defended if it is independently RED-provable). That is why there are now two guards, not one.

---

## 6. The run — commands, and how to read it

✅ **Executed 2026-08-15** (LAPTOP, Snowflake-free, off the MLB serving lane). Results in §9.

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/ncaaf-p2.1
AWS_DEFAULT_REGION=us-east-2 uv run python -m \
    quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_1 --assemble        # 19 s
AWS_DEFAULT_REGION=us-east-2 uv run python -m \
    quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_1 --stage battery   # ~2.5 min
AWS_DEFAULT_REGION=us-east-2 uv run python -m \
    quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_1 --stage decide    # ~10 s
```

**Read it in this order — the leaderboard is not the verdict:**

1. **`anchors valid`.** If any of the six checks fails the run is **not interpretable**, and an
   oracle-floor breach means the metric is inverted (E2.1-r), not that a great model was found.
   (This run: all six passed.)
2. **`survivors`, then each survivor's NULL STATE.** A survivor can clear every ARM-level gate and
   still not ship because a RUN-level gate (PBO / DSR) failed — which is exactly what happened to
   `pace`. Its state is what separates "buy more seasons" from "no `n` ever clears".
3. **The null-state table.** `GENUINE_ABSENCE` and `CONSTRAINT_REFUSED` carry **no** re-test
   trigger; `DSR_UNREACHABLE` carries none either, and its field-size remedy is only advice when
   `field_remedy_admissible` is true. Only a reachable `POWER_LIMITED` implies a future re-run.
4. **`field_remedy_admissible`** — read the machine flag, never the prose (MH2.7).

### ⏭️ Nothing to deploy

**No retrain, no P1.5 re-point, no served-artifact change.** The verdict is `REFERENCE_STANDS`, so
the shipped `ncaaf_game_distribution_v1.json` is unchanged and correct as-is. `--stage decide` never
writes the served artifact. `best_alpha = 0` is unaffected — the vs-close leg is a clean null (§9.7).

### ⏭️ Successors this run earns (each needs a FRESH pre-registration — ⛔ never a re-read of these folds)

| # | successor | why |
|---|---|---|
| S1 | **`pace` on a lower-variance design** — pre-register the DSR return series SEPARATELY from the PBO bucket series (§9.6) | the only lever `classify_null` names; the effect is real (8/8 folds) but the gate series taxes it |
| S2 | **H1b with OUT-OF-FOLD target encoding** (nested CV) | the registered EB estimator is target-encoded and overfits in-fold; its 0/8 collapse is plausibly an artifact, so per-team HFA is not cleanly refuted (§9.4) |
| S3 | **H1a scored on the NEUTRAL-SITE SUBSET** | the mechanism can move 7.93 % of rows; a pooled metric over all 8,325 games dilutes it toward zero (NF-D20 active-rows rule) |
| S4 | **`matchup_unit` at unit level** in NFL-N1.1 / NCAAB | second-best arm (+0.0539) and the only other one carrying signal |

⛔ **Not a successor:** re-scoring this run against a trimmed field. `classify_null` reports
`max_field_size = 0` — even a 2-arm field does not clear — and trimming a field you have already
scored is the discovered-family laundering MH2.2 forbids.

## 7. Files

- `models/bakeoff_ncaaf_p2_1.py` — the battery harness (assemble · battery · decide + dossier render).
- `models/p2_1_blocks.py` — the pre-registered blocks + the in-fold builders (EB HFA and its matched
  level-only foil, the strength interaction, the doc §6.2 MatchupGap set, turnover shrink, preseason
  weight). `DECLARED_FIELD_SIZE` lives here and is pinned to the pre-registration by a guard.
- `models/p2_1_plays_rollup.py` — the leakage-safe plays rollup (H2b's missing 5 doc items + H13).
- `betting_ml/tests/test_ncaaf_p2_1_structural.py` — 25 fast-gate guards, 10 RED-proven.
- `ablation_results/ncaaf_p2_1_preregistration.md` — the contract, committed before any score.
- `ablation_results/ncaaf_p2_1_structural_battery.{json,md}` — the run's own output (leaderboard,
  anchors, deflation, per-arm null states), written by `--stage decide`.
- `ablation_results/ncaaf_p2_1_battery_scores.json` — every arm × fold, the input `decide` reads.
- artifacts (gitignored): `betting_ml/data/cache/ncaaf_p2_1_battery.parquet`.

## 8. Honest framing

`best_alpha = 0`. Everything in this battery is a **calibration** question — honest 3-market
probabilities — and a calibration win is product value, never an edge claim. The honest prior, stated
before the run and unchanged by it, is that **most of these hypotheses will be null**; a clean,
correctly-classified null is the expected and valid deliverable, and it bounds what P1.4's own
`REFERENCE_STANDS` null means: P1.4 showed the conventional search finds nothing, and P2.1 asks
whether *structure* does.

---

## 9. Results

_Operator run 2026-08-15: assemble 19 s (8,325 games 2015–2025; 23,054 play-rollup game-team rows;
4,187 CLV closes joined) · battery 22 arms × 8 folds (2018–2025) · decide._

### 9.1 The run is interpretable — all six anchor checks passed

| anchor | reading | expectation | |
|---|---|---|---|
| `oracle_peek` | CRPS **1.404** vs best real 18.457 | nothing may beat it | ✅ |
| `permute` | 21.798 vs reference 18.519 | must lose | ✅ |
| `zero_width` | 23.189, calib 0.195/0.185 | must lose **and fail** the floor | ✅ |
| `max_width` | 27.459, calib **1.000/0.999** | must **satisfy** the floor and still lose | ✅ |

`max_width` is the NF1.8 proof in its exact shape: a maximally-wide degenerate satisfies the
coverage floor and the METRIC eliminates it — which is what makes the floor a constraint rather than
a criterion a degenerate can win.

⭐ **The DSR-CONV convention was load-bearing, and now has a number on it.** Cross-trial dispersion
`V` measured over the 16 real arms is **0.2025**; measured over the whole field including anchors it
is **56.61 — a 279× inflation**, driven almost entirely by the oracle's improvement Sharpe. Whole-field
DSR is consequently **0.000** for every arm. Had the convention not been pre-registered forward, this
battery would have been structurally incapable of clearing DSR for a purely arithmetic reason
(MH2.1(a)). The degenerate-excluded figure binds, as declared.

### 9.2 Leaderboard — ΔCRPS vs the reference (positive = arm better)

Reference `ridge / strength_only / strength_posterior`: **CRPS 18.5190**, calib80 0.799/0.804,
H2H Brier 0.1816.

| arm | ΔCRPS | fold wins | p | BH | eligible | tie | null state |
|---|---|---|---|---|---|---|---|
| **`pace`** | **+0.0620** | **8/8** | **0.0020** | ✅ | ✅ | — | **DSR_UNREACHABLE** (arm-gates cleared) |
| `matchup_unit` | +0.0539 | 5/8 | 0.0691 | — | ✅ | — | DSR_UNREACHABLE |
| `recency` | +0.0092 | 6/8 | 0.0366 | — | ✅ | — | DSR_UNREACHABLE |
| `preseason_weight` | +0.0015 | 3/8 | 0.4702 | — | ✅ | — | DSR_UNREACHABLE |
| `hfa_venue` | −0.0000 | 5/8 | 0.4692 | — | ✅ | ≈ | GENUINE_ABSENCE |
| `lookahead_letdown` | −0.0004 | 5/8 | 0.4942 | — | ❌ | ≈ | CONSTRAINT_REFUSED |
| `matchup_interaction` | −0.0007 | 4/8 | 0.4939 | — | ✅ | ≈ | GENUINE_ABSENCE |
| `qb_regime` | −0.0054 | 3/8 | 0.5322 | — | ✅ | — | GENUINE_ABSENCE |
| `turnover_luck` | −0.0063 | 2/8 | 0.9099 | — | ✅ | — | GENUINE_ABSENCE |
| `bowl` | −0.0087 | 2/8 | 0.8415 | — | ✅ | — | GENUINE_ABSENCE |
| `garbage_clean` | −0.0089 | 3/8 | 0.7309 | — | ✅ | — | GENUINE_ABSENCE |
| `rivalry` | −0.0091 | 3/8 | 0.8431 | — | ✅ | — | GENUINE_ABSENCE |
| `rest` | −0.0123 | 2/8 | 0.9450 | — | ✅ | — | GENUINE_ABSENCE |
| `special_teams` | −0.0477 | 0/8 | 0.9957 | — | ✅ | — | GENUINE_ABSENCE |
| `hfa_full` | −0.1420 | 0/8 | 0.9988 | — | ✅ | — | GENUINE_ABSENCE |
| `hfa_team_eb` | −0.1452 | 0/8 | 0.9989 | — | ✅ | — | GENUINE_ABSENCE |

**Deflation:** PBO **0.023** (PASS < 0.2) · DSR(degenerate-excluded) **0.0409** (FAIL < 0.95) ·
BH-FDR cutoff 0.003125 · calibrated fold-consistency clause requires 6 of 8 wins (false-fire 0.145).

### 9.3 `pace` — a real effect that deflation cannot certify, and no amount of data will

`pace` is the only arm to clear every ARM-level gate: **+0.0620 CRPS, positive in 8 of 8 folds**
(2018 +0.066, 2019 +0.032, 2020 +0.106, 2021 +0.033, 2022 +0.062, 2023 +0.004, 2024 +0.067,
2025 +0.136), p = 0.0020 against a BH cutoff of 0.003125, eligible, not a nested-form tie, on a field
whose PBO is a very clean 0.023. It is not a fluke of ranking.

It fails DSR, and the classification matters:

```
observed per-bucket Sharpe   0.532
deflated benchmark SR0       0.874   (N = 22 trials, V = 0.2025)
                             ⇒ SR ≤ SR0  in this field
```

⇒ **`DSR_UNREACHABLE`, not `POWER_LIMITED`.** `n` enters DSR only through `√(n−1)`, so it scales a
positive gap but cannot create one: **no number of additional seasons clears this.** ⛔ This null
therefore gets **no "re-test with more data" trigger** — publishing one would be actively misleading
(the NF-D18 direction).

**Nor is a smaller field the remedy.** `cv_power.classify_null` reports `max_field_size = 0` and
states it explicitly: *"field size is NOT a lever here — even a 2-arm field does not clear at this
fold count and dispersion."* ⭐ Worth recording that this **overturned my own arithmetic**: I had
estimated a ~2-arm field might clear, and the instrument was right and I was wrong. Reading the
instrument rather than trusting the algebra is the reason this dossier does not carry a false
"pre-register a narrow family and it will pass" recommendation.

The one lever the instrument does name is **a lower-variance design** (more rows per fold, or a
sharper metric), which points at a genuine design finding — see §9.6.

### 9.4 H1 (team/venue HFA) — the top-prior hypothesis is a tie, and per-team HFA is harmful

Registered as "the biggest clean win", and strengthened by V1 (the shipped model has *no* home-field
term at all). The result:

| arm | CRPS | ΔCRPS | folds |
|---|---|---|---|
| `hfa_venue` (venue + travel context) | 18.5190 | **−0.0000** | 5/8 |
| `hfa_global` (matched level-only foil) | 18.5169 | +0.0021 | — |
| `hfa_team_eb` (EB per-home-team HFA) | 18.6642 | **−0.1453** | **0/8** |
| `hfa_full` (both) | 18.6610 | −0.1420 | 0/8 |

The matched foil did its job: `per_team_content_earns_it = false` (the EB arm loses to its own
level-only foil by 0.147). So the per-team claim is **refuted, not merely unsupported** (NF-D15 g′).

⚠️ **Two honest limits on how far this null generalises — both were foreseeable and neither is a
reason to reinterpret the registered result:**

1. **The per-team arm's loss is partly an artifact of MY estimator, not necessarily of the
   hypothesis.** `eb_team_hfa` is a **target-encoded** feature: it is built from `label_home_margin`
   on the fold's train rows and then used as a predictor on those same rows, so the ridge over-trusts
   a value that is partly self-predicting in-sample and generalises worse out of sample. That is
   textbook target-encoding overfitting, and it explains a 0/8 collapse better than "per-team HFA
   does not exist" does. The matched foil is a CONSTANT and therefore structurally immune to it, so
   the comparison is confounded: the two arms differ in per-team content **and** in exposure to this
   artifact. A clean test needs **out-of-fold target encoding** (nested CV). The registered null
   stands as a null about the registered estimator; it is not a clean null about per-team HFA.
2. **`hfa_venue`'s pooled null is low-information by construction.** Its mechanism can only move the
   660 neutral-site games (7.93 %) plus altitude/travel extremes; 92 % of rows are untouchable, so a
   pooled CRPS averaged over all 8,325 games dilutes any real effect toward zero. This is the NF-D20
   "count the rows the mechanism can ACT on" point, and the exposure counts were pre-registered
   precisely so it could be read this way. The pooled metric was also pre-registered, so the pooled
   null is the registered result — but a **neutral-site-subset** read is the honest successor, and it
   must be **registered forward**, not computed now off this run.

### 9.5 The rest of the battery

**`GENUINE_ABSENCE` ×11** — the best arm loses on average; no `n` and no field size rescues a negative
point estimate, so none of these carries a re-test trigger. Notably the entire Tier-2 situational
block (rest, lookahead/letdown, rivalry proxy, bowl) is absent, as is special teams (0/8) and the
garbage-time clean-vs-raw pair.

**`CONSTRAINT_REFUSED` ×1** — `lookahead_letdown` was refused by the calibration CONSTRAINT (margin
PIT flat in only 3 of 8 folds, needing ≥4), not by the metric. Its ΔCRPS is −0.0004, an exact tie
anyway. Per NF-D18 the remedy is a different mechanism or a PM decision, never more data.

**`DSR_UNREACHABLE` ×4** (`pace`, `matchup_unit`, `recency`, `preseason_weight`) — all report field
size is not a lever.

⭐ **Three arms were caught by the nested-form tie guard** (`hfa_venue`, `matchup_interaction`,
`lookahead_letdown`, all |ΔCRPS| < 1e-3). Every arm nests the reference, so a ridge shrinks an
uninformative block toward zero and the arm collapses onto its own foil. Without the guard,
`hfa_venue`'s −0.0000 would have been reported as a directional result.

### 9.6 The design finding worth carrying forward

**The return series PBO wants is not the series DSR wants, and sharing one silently taxes DSR.**
CSCV needs many buckets, so the battery slices each fold into quarters (8 folds × 4 = 32 buckets) —
and I then reused that same series for DSR. Chopping a fold into quarters adds within-fold noise
without adding independent information:

```
pace, per-FOLD improvement Sharpe    1.492   (8 observations)
pace, per-BUCKET improvement Sharpe  0.532   (32 observations)  ← the pre-registered gate series
```

⛔ **I am deliberately not quoting a counterfactual per-fold DSR.** The bucket series was
pre-registered as the gate; re-reading the gate on the series that happens to look better is exactly
the E2.1-r inversion, and a number computed that way would be read as the real answer no matter how
it were captioned. The transferable lesson is for the NEXT story: **pre-register the DSR return
series separately from the PBO bucket series**, and prefer per-fold (or larger blocks) for DSR. That
does not rescue `pace` here — a successor must re-register forward and re-run, never re-read.

### 9.7 Edge: still a clean null

| | ATS | placebo | O/U | breakeven |
|---|---|---|---|---|
| reference | 0.4996 | 0.4897 | 0.5070 | 0.5238 |
| `pace` | 0.5045 | 0.4897 | 0.5126 | 0.5238 |

n = 4,115 ATS / 4,134 O/U over 2020–2025. Both sides sit below the −110 breakeven;
`clears_edge_bar = false` for both. Consistent with P1.4 (ATS 0.496 / O/U 0.523). **`best_alpha = 0`
stands** — nothing here is an edge claim, and `pace`'s calibration result would not have become one
even had it cleared DSR.

### 9.8 Cross-sport carry (story AC)

- **H1 (venue/team HFA) → NFL-N1.1 + NCAAB: the answer is "don't lead with it."** A model with *no*
  HFA term gained nothing measurable from adding one, and the per-team variant hurt. ⚠️ Carry the two
  §9.4 caveats with the finding — an out-of-fold-encoded per-team HFA and a neutral-site-subset read
  are both untested, so this bounds the *pooled* value of venue HFA, not the mechanism itself. The
  cheap first check in those verticals is still V1: *does the model actually have an HFA term, or is
  an intercept absorbing one blended over neutral-site games?*
- **H2/H2b (matchup) → carries as a weak positive.** `matchup_unit` (the full doc §6.2 set, including
  the five interactions built from the plays Delta) is the second-best arm at +0.0539 but only 5/8
  folds and p = 0.069; the strength-level `matchup_interaction` is an exact tie. So the *unit-level*
  matchup carries some signal and the *strength-level* interaction carries none — worth registering
  in the NFL/NCAAB analogues, at unit level, not as a strength product term.
- **`pace` is the one to carry.** It is the largest and by far the most consistent effect in the
  battery (8/8 folds), it is sport-agnostic (possessions drive total variance and game script), and
  its failure here is a deflation-arithmetic failure rather than an evidential one.

### 9.9 What this says about P1.4's null

P1.4 showed the conventional search (learner × feature-subset × parametric form) finds nothing.
P2.1 asked whether richer STRUCTURE does, and the answer is **very nearly no**: 15 of 16
pre-registered structural hypotheses are nulls, and the one real effect cannot be certified under
the battery's own deflation. That is a meaningful bound on P1.4's null rather than a repeat of it —
the strength-prior reference is not merely un-beaten by feature engineering, it is un-beaten by the
structural gaps the model provably has, including a completely absent home-field term.
