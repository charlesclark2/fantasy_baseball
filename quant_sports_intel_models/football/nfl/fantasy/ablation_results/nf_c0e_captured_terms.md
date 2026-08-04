# NF-C0e — projecting the commonly-captured scoring terms

**Status:** shipped, partial — 15 terms graduated from CAPTURED to APPLIED, 4 tested and
**deliberately left captured**, 6 recorded as having no substrate at all, and one **live scoring
outage** found and fixed along the way.

**Honest frame:** a projection product. No `best_alpha`, no PBO/DSR — this is not an edge claim.
The gate is a held-out degenerate baseline, and everything below is measured.

---

## 0. The thing that mattered most was not in the story

While reading the NF-C0d telemetry to prioritise the work, the ESPN adapter's own rows showed
`pass_yd`, `rush_yd`, `rec_yd` and `fum_lost` sitting in the **captured** list.

Those are **Sleeper's platform keys**. The canonical keys are `pass_yds` / `rush_yds` / `rec_yds` /
`fumbles_lost`, which Sleeper's and Yahoo's adapters both map to correctly. `espn.py` had been
mapping ESPN's stat ids 3 / 24 / 42 / 72 onto the wrong spelling.

Nothing errored, because NF-C0's contract is that an unrecognised key passes through verbatim and
is reported CAPTURED. So **every ESPN-imported league scored zero for passing, rushing and
receiving yardage** — the bulk of fantasy points — behind a coverage panel that said so, and that
nobody read.

Measured on the real league-998005 payload, before and after:

| | applied | captured |
|---|---|---|
| before | 23 | 16 |
| after | 27 | 12 |

**Why it survived.** `test_core_scoring_is_applied` existed and passed. It asserted
`per_stat["pass_yd"] == 0.04` — i.e. it read the value back under *whatever key the adapter happened
to write*. That is a restatement of the code, not a test of it, and a mapping table pointing at a
key that exists nowhere in the catalog satisfies it exactly as happily as a correct one. The test
now asserts the canonical key **and the APPLIED verdict from the real engine**, which a wrong key
cannot satisfy by construction.

**The durable guard** is `test_every_adapter_target_is_a_real_canonical_key`, which checks every
target of every adapter against the catalog. A key one character off is otherwise indistinguishable
from a genuinely unprojected term — that ambiguity is intrinsic to the honest-capture design, so the
check has to be mechanical and live outside any one adapter. RED-proven against the original bug.

**And a lesson about the telemetry ranking itself.** `pass_yd` scored **0.04** on
frequency × |weight| — dead last of 38 rows, below `fumble_rec_td` at 6.0. But 0.04 × ~4,500 passing
yards is ~180 points a season, while 6.0 × ~0.004 fumble-recovery touchdowns is ~0.02. **|weight| is
not impact; |weight| × the stat's VOLUME is.** The ranking is a useful prioritiser and a bad
prioritiser for low-weight/high-volume terms, and it ranked the single most consequential captured
term in the corpus last.

---

## STEP 0 — the telemetry purge

The live `fantasy-import-telemetry/` prefix held **exactly two objects**, both stamped
`2026-08-03T05:26–05:27Z` — entirely inside the operator's NF-C0d Preview-testing window. There was
no organic sample to separate the QA rows from.

They were **moved, not deleted**, to
`s3://credence-prod-s3-api-cache/fantasy-import-telemetry-qa-archive/nf-c0d-preview-testing-2026-08-03/`.
The live ranking now honestly reads empty; the evidence survives. Their contents are reproduced in
§5 because the *settings* in them are real even though the *frequencies* are meaningless at n=2.

⚠️ There is still **no purge/exclusion endpoint**, so the next round of QA imports will pollute the
ranking the same way. Flagged for the operator; not fixed here.

---

## 1. The gate

For each candidate: walk forward season by season, fit strictly on prior seasons, project the
held-out season, score against realized outcomes.

> A term graduates only if it beats a **degenerate** arm on **both** MAE and RMSE, in enough folds
> to satisfy `cv_power.fold_consistency_clause`.

**Requiring both losses is load-bearing, not caution.** These targets are heavily zero-inflated, and
MAE on a zero-heavy target is minimised at the conditional median — so it pays for pessimism and can
rank a systematically under-projecting arm first (the NF-D11 inversion). It is exactly what caught
`fum`: 7/7 folds on MAE, 0/7 on RMSE.

Both anchors are reported every run:

* **degenerate ceiling** (must lose) — league-mean rate for every team; position-mean count for
  every player.
* **oracle floor** (nothing may beat it) — the same form fed the realized season rate. Same family
  and same n by construction, so NF1.7 (b)'s "peeking can only help" actually holds here.

Reproduce with:

```
uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_c0e_captured_terms \
    --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --out ablation_results
```

---

## 2. GRADUATED

### 2a. D/ST yards-allowed tiers — the story's ⭐ item

Nine `proj_dst_ya_g_*` columns = the **expected number of games** the defense lands in each
yards-allowed bucket, so a per-game tier table scores a season as
`Σ_bucket tier_points × expected_games` — **linear in the emitted columns**, hence the league's own
table applied *exactly* rather than approximated, with no engine change. Structurally identical to
NF1.6's already-shipped points-allowed construction.

**The substantive reason it works:** yards allowed per game is **more** persistent season to season
than points allowed — lag-1 ρ = **0.401** vs **0.316** on the same 829 team-season pairs. (The 0.316
reproduces NF1.6's published figure exactly, which is what validates the measurement pipeline.)

Scored under the two real league tables the telemetry surfaced, 16 held-out seasons × 32 teams:

| family / table | MAE | degen | gain | RMSE | degen | gain | MAE folds | RMSE folds | req | ρ |
|---|---|---|---|---|---|---|---|---|---|---|
| yards / Sleeper (+6…−6) | 9.94 | 10.96 | **+9.3%** | 12.45 | 13.68 | **+9.0%** | 12/16 | 12/16 | 11 | 0.268 |
| yards / ESPN (+5…−7) | 10.86 | 11.99 | **+9.5%** | 13.50 | 14.87 | **+9.2%** | 13/16 | 12/16 | 11 | 0.276 |
| **points / ESPN — CONTROL** | 8.01 | 8.61 | +7.0% | 9.89 | 10.64 | +7.0% | 15/16 | 14/16 | 11 | 0.316 |

Oracle floor respected and degenerate beaten in all three. The **control** is what makes this
readable: the new family's held-out margin is *larger* than that of the tier family the program
already serves.

**⚠️ The caveat, published because a reader deserves it.** The last three seasons are weak — rank
correlation 0.057 (Sleeper) / 0.045 (ESPN) against a full-sample 0.27, and MAE actually **loses** to
the degenerate over that window. The points-allowed control holds up better (0.245).

It is reported and **not gated on**, deliberately: that window was chosen *after* seeing the season
table, so selecting on it would be the post-hoc trim MH2 warns about ("you get to pre-register a
family, you do not get to discover one") applied to a time window. At n=32 the SE of a season's
Spearman is ~0.18, so three seasons averaging 0.057 against a true 0.27 is ≈2 SE — suggestive, not
decisive — and 2024 is weak for *both* families, which a yards-specific regime change would not
explain. **Re-validation trigger:** re-run after the 2026 season. If the weak stretch reaches five
consecutive seasons it is a regime change and the family should be re-scored, not a fluctuation.

**On the bucket edges.** Unlike the points ladder — where ESPN splits 18-21 / 22-27 against our
18-20 / 21-27 and exactly one boundary is disclosed as approximate — the nine yards rungs are
**identical on both platforms**. `espn.py`'s identity evidence had fixed the *order* of ids 128–136
but explicitly not their extent; Sleeper's self-describing keys (`yds_allow_0_100` … `yds_allow_550p`)
supply exactly the missing half. Two independent payloads agreeing is evidence; one payload plus a
guess is not. One residual ambiguity is disclosed: Sleeper spells the top rung `0_100` and ESPN calls
it "under 100"; we resolve as `< 100`, and exactly **1 team-game in 13,912 since 1999** sits on 100.

**⭐ The measurement trap worth carrying forward.** nflverse `total_yards` is **gross**
(`passing_yards + rushing_yards`, verified as an identity on all 13,912 team-games). The platforms
grade a D/ST on the official box score's **total net** yards, which removes sack yardage. Using the
gross column overstates every defense by ~15 yards/game and shifts the whole league roughly one tier
rung — uniform, silent, and invisible to any per-team sanity check. Validated against published
league averages: net gives **331.6** yards/g in 2023 against the NFL's published **331.1**; gross
gives 349.0. Pinned by `test_yards_allowed_is_NET_of_sack_yardage_not_gross`.

### 2b. `def_forced_fumble`

`def_fumbles_forced` was sitting in `stg_nfl_team_week` the whole time and was simply never selected
by the loader — so a league paying for a forced fumble (the operator's Sleeper league does, at +1)
had that rule captured for want of one line of SQL.

| | MAE | degen | gain | RMSE | degen | gain | folds | req |
|---|---|---|---|---|---|---|---|---|
| `def_forced_fumble` | 3.47 | 3.75 | **+7.4%** | 4.31 | 4.60 | **+6.4%** | **16/16 both** | 11 |
| `def_sacks` — CONTROL, already applied | 6.32 | 6.50 | +2.8% | 7.90 | 8.13 | +2.8% | 12/16, 14/16 | 11 |

Fitted forward slope 0.29. It carries a **wider** held-out margin than a component the program
already ships as applied.

### 2c. `two_pt`, and the three long-TD bonuses

7 held-out seasons (2019–2025), scored against the *actual* shipped MVP-1 projection artifacts —
never a realized predictor. Clause requires 6/7.

| term | MAE gain | RMSE gain | MAE folds | RMSE folds | ρ |
|---|---|---|---|---|---|
| `pass_td_40p` | +32.9% | +20.8% | 7/7 | 7/7 | 0.672 |
| `rec_td_40p` | +24.8% | +7.1% | 7/7 | 7/7 | 0.358 |
| `rush_td_40p` | +22.9% | +4.9% | 7/7 | 7/7 | 0.287 |
| `two_pt` | +22.7% | +4.9% | 7/7 | 7/7 | 0.335 |

**What the long-TD terms do and do not claim.** `<x>_td_40p = proj_<x>_td × league_40p_share`, with
the share measured in-fold per play type (~0.13 of passing TDs, ~0.06 of rushing). A receiving TD's
length *is* its passing play's, so one measured pass share serves both. The share is a **league
constant on purpose**: there is no evidence the 40+ share of a player's touchdowns is a per-player
skill, and inventing one would manufacture precision. The honest claim is "your long-TD bonus is
applied in proportion to the touchdowns we project", not "we predict who scores long touchdowns".
It still beats the degenerate decisively because touchdown volume varies enormously and *is*
forecastable — which is a skill we already have.

The share is also **not stationary** (0.149 in 2010 → 0.090 in 2025), which is why it is re-measured
in-fold rather than pinned.

`proj_two_pt` was a live trap: MVP-1 declared the column and set it to `NaN` for every player. That
was honest downstream (the exporter drops an all-null field, so the term reported CAPTURED) but a
consumer reading the frame directly would have seen a real column name and scored `weight × NaN`.
Graduating the term closes that too.

---

## 3. TESTED AND DELIBERATELY LEFT CAPTURED

This is the story's central discipline: *"project it so it's applied" is not automatically an
improvement.* A term projected with no skill still moves the board — on noise — while wearing the
"applied" label, which is strictly worse than an honest "captured", because the user now believes we
modelled it.

### `pat_missed` — the sharpest case

It is **one subtraction** from two columns we already emit (`pat_att − pat_made`). It is left
captured anyway.

| MAE | degen | gain | RMSE | degen | gain | MAE folds | req |
|---|---|---|---|---|---|---|---|
| 0.9899 | 0.9920 | **+0.21%** | 1.3086 | 1.3160 | +0.56% | **8/16** | 11 |

8/16 is a coin flip. The reason is one NF1.6 already measured: kicker accuracy is near-random
(ρ = 0.085), so the projection collapses to `volume × a league constant`, and **44% of
kicker-seasons record zero misses**. Availability is not evidence — a term graduates by beating a
baseline, never by being cheap to compute. Pinned by
`test_pat_missed_is_rejected_even_though_its_inputs_are_BOTH_projected`.

*(Incidental measurement: the league PAT miss rate more than tripled, 0.008 in 2010–15 → 0.034 in
2022–25, the 33-yard-PAT rule change. Another reason in-fold rates matter.)*

### `fum` (total fumbles) — the metric inversion, caught live

| | MAE | RMSE |
|---|---|---|
| gain vs degenerate | **+7.4%** | **−21.1%** |
| fold wins | **7/7** | **0/7** |

A systematic sign disagreement, not noise. **67% of players record zero fumbles**, realized SD is
1.5–1.9 against the projection's 0.46–0.57, and realized max is 13 against a projected max of 3.3.
The touch-rate arm cannot track the tail, and MAE is simply rewarding it for being small — the
NF-D11 inversion, firing for real on a pre-registered check. Graduating this needs an actual fumble
model, not a rescaling of `proj_fumbles_lost` (itself a `touches × 0.006` heuristic).

### `st_player_td` and `fumble_rec_td` — a mechanism that cannot act

We project **no return volume of any kind**, so the only arm constructible is the league mean —
which *is* the degenerate. Measured gain is exactly **0.000**, by construction. This is a scope
finding, not a power finding: the remedy is a return-usage projection, not more data or a better
fit. (Realized means: 0.022 and 0.004 per player-season.)

---

## 4. NO SUBSTRATE — not tested, because they cannot be

`st_ff`, `st_fum_rec`, `def_st_ff`, `def_st_fum_rec` — the special-teams / defensive **phase split**
of forced fumbles and fumble recoveries. nflverse carries `def_fumbles_forced` and
`fumble_recovery_opp` as all-phase totals and does not split them by phase, in either the team-week
or player-week feeds. There is no column to project and no baseline to beat.

This is a **different kind of null** from §3 and the report keeps them apart: §3 terms were measured
and lost; these were never measurable. The story predicted these would stay captured, and they do —
but for a reason that no amount of modelling effort would change.

---

## 5. What the archived telemetry actually said

Two imports, two real leagues. Frequencies are meaningless at n=2; the *settings* are real.

**Sleeper 998005** (12-team half-PPR): the full nine-rung yards ladder +6…−6 (the 350-399 rung at 0,
which is why only eight appear — zero-weight terms are not reported), `pass_td_40p` / `rush_td_40p` /
`rec_td_40p` at +2, `two_pt` +2, `def_forced_fumble` +1, `pat_missed` −1, `fum` −1, `st_ff` /
`st_fum_rec` / `def_st_ff` / `def_st_fum_rec` +1, `fumble_rec_td` / `st_player_td` +6.

**ESPN 642070**: the yards ladder 128–136 at +5 / +3 / +2 / (0) / −1 / −3 / −5 / −6 / −7, plus
`fumble_rec_td` and `st_player_td` at +6 — **and** `pass_yd` / `rush_yd` / `rec_yd` / `fum_lost`,
which is where the outage in §0 surfaced.

---

## 6. Left undone, on purpose

**ESPN's long-TD ids (15/16, 35/36, 45/46) stay CAPTURED even though the 40+ column now exists.**
Each pair is a 40+ and a 50+ bonus and **no payload we hold distinguishes them**. Every id in that
map earned its place by an identity a wrong map fails; there is no such identity here. Guessing
would not be a harmless mislabel — mapping a 50+ bonus onto the 40+ column pays it on ~13% of
touchdown passes where the league pays on ~6%, i.e. mispricing the league by roughly double.

So the graduation is **asymmetric on purpose**: Sleeper's long-TD terms are applied because its keys
*state* the threshold; ESPN's wait for one payload that sets a pair apart, or for the human-readable
settings page. No league we have seen is affected — 642070 sets none of these six ids.

The stale ESPN warning *"We don't project yards allowed … a defence that wins by suppressing yardage
will be under-rated on your board"* was **deleted, not reworded**. A caveat that has stopped being
true is not harmlessly stale: it tells the user their board ignores a rule it now applies, which is
the same class of wrong as claiming to apply one we ignore.

---

## 6b. ⚠️ The module shipped without being CALLED (found post-merge, fixed in a follow-up)

The first cut of this story wrote `captured_terms.py`, graduated its four terms against the gate,
wired them into `NFL_PROFILE`, the editor catalog, both frontend mirrors and the exporter's key
list — and **nothing in the pipeline ever invoked `project_captured_terms`**. The columns would have
exported as `null`, been dropped by `availableFields`, and the four terms would have gone on
reporting CAPTURED. Everything looked complete because every *declaration* was in place; only the
*production* was missing. It surfaced when the operator ran the handoff commands.

The fix is a derived-column step on the **read** path rather than in the model build (these terms
are `already-projected volume × a measured league rate`, so rebuilding NF1.5 to re-measure a rate
would be absurd) — but that immediately reproduces the repo's most-repeated failure shape: **one
logical thing with many execution owners** (INC-30's crontab under two users, INC-36's deploy,
INC-38's per-caller flag). **Four** loaders read this projection, and `two_pt` carries weight **2.0
in every preset**, so a loader that skipped the step would produce a board scored a few points
*below* the exported payload — silently, for the same player, from the same artifact. The exporter
already refuses to publish when its projection *source* disagrees with the boards'; this is that
invariant one level down.

So: one `apply_to_projection`, a `CONSUMER_CALLERS` registry, a guard asserting **every** listed
loader calls it, and a second guard asserting the registry is still **exhaustive** against the
source (INC-38's lesson that a per-caller rule fails exactly where its registry is incomplete).

The league rates live in a small committed artifact
(`artifacts/nf_c0e_captured_term_rates_<season>.json`, built by `--emit-rates`) stamped with the
season it was fitted **through**. Pinning the constants in code would let them rot silently — the
40+ pass share moved 0.149 → 0.090 between 2010 and 2025 — and doing a lake read inside a loader
would put a network dependency on every offline board build. A missing or malformed artifact reads
as **absent**, which emits no columns and reports CAPTURED; it never falls back to the pinned
constants, because that would make every rate look measured when none were (NF1.7 (a)).

**The generalisable lesson:** *a term is not applied because a column name appears in the profile,
the catalog, and the export map. It is applied when something computes it.* The coverage machinery
is mechanical about the column EXISTING and says nothing about who fills it — so a story that
graduates a term must verify the value end-to-end through a real loader, not the declarations.

## 6c. ⚠️ …and then a STALE CACHE published one graduated term as all-NULL (found in prod)

The republish after §6b succeeded and `two_pt` / the three long-TD bonuses landed correctly — but a
read of the published artifact showed **`proj_def_forced_fumble` at 0 of 32 non-null**, while every
sibling D/ST component was fully populated. §2b's graduation was real; the value never reached the
board.

**Cause.** `load_team_defense_seasons` cached to `team_defense_{lo}_{hi}.parquet` — keyed on the
season range **alone**, with nothing about the query in the key. NF-C0e added `def_fumbles_forced`
to `_TEAM_DEF_SQL`; the on-disk cache in the operator's checkout was written 2026-07-30, four days
earlier, so the loader returned the pre-NF-C0e column set. From there every step behaved correctly:
`build_dst_training_panel` skipped the absent component, `fit_dst_component_model` never fitted it,
`project_dst` emitted nothing, and the coverage machinery reported the truth about a column that
did not exist.

**Why no warning would have helped, and why the fix is the cache KEY.** That silence is the
*correct* behaviour: a component the history genuinely lacks must be skipped, never zero-filled — a
zero-filled component gets fitted, projected and scored as APPLIED against fabricated data (§2's
whole discipline). The honest fallback is exactly what converts "my cache is stale" into "this
feature isn't available," with nothing anywhere to notice. So a stale cache has to be impossible to
*read*, not merely noisy: the cache key now carries a fingerprint of the query text.

**⭐ Why the §6b end-to-end verification did not catch it.** That check ran in a fresh worktree,
which has no `artifacts/` directory — so it rebuilt from the lake and passed, while the operator's
working checkout with a four-day-old parquet failed. This is the on-disk **artifact-precedence**
landmine in CLAUDE.md (the board-export stale-source case), in the direction that ships: *a clean
checkout cannot reproduce a bug whose trigger is a file a clean checkout lacks.* The fix was
re-validated by copying the real stale parquet **into** the worktree first — reproducing the
failure environment before claiming the fix.

**Scope.** Exactly one column. `_KICKER_SQL` was untouched by NF-C0e, so its cache was never stale,
and `load_team_yards` — the yards-allowed family — does not cache at all, which is precisely why
that family shipped correctly while forced fumbles did not.

**The two lessons together.** §6b: a term is applied when something *computes* it. §6c: and when
that computation reads *this* checkout's data, not a snapshot of an older schema. Both are the same
failure with different surfaces — a declaration that outran its production — and neither is visible
to a test suite, because both mechanisms were behaving exactly as designed.

## 7. Guards

`betting_ml/tests/test_nf_c0e_captured_terms.py` (46 tests, fast gate). Five were RED-proven
against deliberately broken source before being trusted:

* reverting the ESPN canonical key → 2 RED
* dropping the net-yards sack correction → 1 RED
* silently graduating `pat_missed` with no evidence → 2 RED
* a projection loader skipping `apply_to_projection` → 1 RED
* hiding the measured rates artifact → 1 RED

The rejection registry lives *in the test file* keyed by its evidence, so graduating one of those
terms later means producing a better number rather than deleting a line.

`betting_ml/tests/test_kdst_cache_invalidation.py` (7 tests, fast gate) covers §6c. Three go RED
when the query fingerprint is reverted, verified before being trusted. The set is deliberately
two-sided: a stale cache must not be served, **and** an unchanged query must still hit the cache —
without the second, "always miss" would satisfy every other assertion while turning an instant
re-run into a full lake scan. One test reconstructs the pre-fix reader and asserts it *does* return
the stale column set, so a future revert cannot leave the suite green on a fixture some other
clause happens to reject (NF-D17). A registry test pins that every cached reader routes through the
shared helper, since the original defect was a per-reader implementation detail.
