# NCAAF-P2.1 — game-model structural refinement: design, verification and handoff

**Status (2026-08-15): harness BUILT, GUARDED and SMOKE-VALIDATED end-to-end. The heavy battery run
is an OPERATOR step** (it exceeds the repo's 2-minute in-session limit — measured extrapolation
~3–5 min). `--stage decide` auto-generates the results dossier
`ncaaf_p2_1_structural_battery.md`; this document is the design + verification companion, the same
split P1.4 used.

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

## 6. ⏭️ Operator run plan — LAPTOP, Snowflake-free

All three commands run on the **LAPTOP** (off the MLB serving lane; DuckDB over S3, no Snowflake, no
box state needed). Stages 0 and 1 exceed 2 minutes, which is why they are handed off rather than run
in-session.

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/ncaaf-p2.1

# 0) ONE pull → ONE parquet (matrix + plays rollup + derived blocks + CLV closes).  ~2-4 min
AWS_DEFAULT_REGION=us-east-2 uv run python -m \
    quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_1 --assemble

# 1) the full battery: reference + 16 registered arms + 5 anchors, 8 purged folds.  ~3-5 min
AWS_DEFAULT_REGION=us-east-2 uv run python -m \
    quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_1 --stage battery

# 2) deflate (PBO / DSR-CONV / BH-FDR), classify every null, render the dossier.  ~10 s
AWS_DEFAULT_REGION=us-east-2 uv run python -m \
    quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_1 --stage decide
```

Step 2 writes `ablation_results/ncaaf_p2_1_structural_battery.{json,md}`.

**Read the run in this order — the first line is not the verdict:**

1. **`anchors valid`.** If any of the six anchor checks fails, the run is **not interpretable** and
   nothing else on the page should be read. In particular a breach of the oracle floor means the
   metric is inverted (E2.1-r), not that a great model was found.
2. **`survivors`.** Empty is the honest prior and is a valid deliverable.
3. **The null-state table.** A `GENUINE_ABSENCE` carries no re-test trigger; a `CONSTRAINT_REFUSED`
   carries none either and its remedy is a different mechanism or a PM decision, never more data.
   Only a reachable `POWER_LIMITED` implies a future re-run.
4. **`field_remedy_admissible`.** Read the machine flag, not the prose (MH2.7).

### If the battery produces a survivor (do NOT pre-empt this)

A survivor is a **calibration** result and ships as product value, `best_alpha = 0`. The retrain +
P1.5 re-point is a **post-merge operator step**, deploy-held, and is only warranted once the run has
actually produced one:

```bash
# ONLY if `--stage decide` reports a survivor — refit P1.4's served distribution with the winning
# block and re-point P1.5. Deploy-held; the served artifact is NOT overwritten by --stage decide.
AWS_DEFAULT_REGION=us-east-2 uv run python -m \
    quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_game --stage finalize \
    --model-class ridge --contract strength_only --form strength_posterior
```

⚠️ An **edge** claim needs more than a survivor: the deflated vs-close leg must show model-side
ATS/OU **> 0.5238 breakeven AND > the placebo** (pre-registration §1.10). P1.4's reference measured
ATS 0.496 (placebo 0.497), O/U 0.523 — a clean null. Until that bar is cleared, nothing here is an
edge claim.

### Cross-sport carry (story AC)

**H1 (venue/team HFA)** and **H2/H2b (matchup)** are sport-agnostic structure. Whatever the battery
returns for those two — survivor *or* null — carries to **NFL-N1.1** and **NCAAB**, and a null is
just as informative there: it bounds how much structure the conventional contract is leaving on the
table. ⚠️ V1 is the transferable part worth checking first in those verticals: *does the model
actually have a home-field term, or is the intercept absorbing one blended over neutral-site games?*
That was a code fact here, not a modelling opinion, and it is cheap to check elsewhere.

---

## 7. Files

- `models/bakeoff_ncaaf_p2_1.py` — the battery harness (assemble · battery · decide + dossier render).
- `models/p2_1_blocks.py` — the pre-registered blocks + the in-fold builders (EB HFA and its matched
  level-only foil, the strength interaction, the doc §6.2 MatchupGap set, turnover shrink, preseason
  weight). `DECLARED_FIELD_SIZE` lives here and is pinned to the pre-registration by a guard.
- `models/p2_1_plays_rollup.py` — the leakage-safe plays rollup (H2b's missing 5 doc items + H13).
- `betting_ml/tests/test_ncaaf_p2_1_structural.py` — 23 fast-gate guards, 9 RED-proven.
- `ablation_results/ncaaf_p2_1_preregistration.md` — the contract, committed before any score.
- artifacts (gitignored): `betting_ml/data/cache/ncaaf_p2_1_battery.parquet`.

## 8. Honest framing

`best_alpha = 0`. Everything in this battery is a **calibration** question — honest 3-market
probabilities — and a calibration win is product value, never an edge claim. The honest prior, stated
before the run and unchanged by it, is that **most of these hypotheses will be null**; a clean,
correctly-classified null is the expected and valid deliverable, and it bounds what P1.4's own
`REFERENCE_STANDS` null means: P1.4 showed the conventional search finds nothing, and P2.1 asks
whether *structure* does.
