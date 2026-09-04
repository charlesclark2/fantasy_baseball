# NF-INJ4 — PRE-REGISTRATION

**Committed before any arm was scored.** ⛔ Editing this document after a result is not a
pre-registration (E2.1-r). Everything decidable in advance is a CONSTANT in
`nf_inj4_designation_duration.py`; this document is the reasoning, and the runner restates neither.

**Read `nf_inj4_data_census.md` first.** The census ran BEFORE this registration and it BINDS: it
is why the source set is two and not three, why a NULL designation is missing rather than a level,
why the fold unit is the player, and why the conditioning family carries a declared backoff instead
of a position-conditional promise this depth cannot keep.

`best_alpha = 0`. **DEPLOY-HELD** — nothing serves without the gated ship path (§8) and explicit
operator approval.

---

## 1. The defect, traced

`season_projection.injury_availability_games` caps expected games only for
`_INJURY_STATUS_GAMES_CAP = {RES, PUP, NFI, SUS}`, and `sleeper_injuries_source.map_injury_status`
returns `None` — no override — for a weekly game-report tag. So **Questionable, Doubtful and Out
apply an availability discount of exactly zero**: the board reacts to a roster TRANSACTION and to
nothing else. The trace is `ablation_results/nf_c8_injury_designation_gap.md`.

That is leakage-safe and defensible, and from Week 1 (2026-09-09) the Q/D/O channel is the primary
live availability signal the paying user base sees. The honest fix is a DURATION model, because a
weekly designation carries no duration — `sleeper_injuries_source.WEEKLY_DESIGNATIONS` carries a
standing prohibition against ever mapping one to a games number, and names the empirical
distribution fitted on history as the alternative. This is that story.

**Capability (b) — a news/NLP ingest — is out of scope entirely** (new data source, live leakage
question, operator-gated spend).

---

## 2. The target

**`spell` — the number of the player's own team's games, starting with the designation week's game,
that he misses CONSECUTIVELY before his next appearance.** Zero when he plays that week.

Why the consecutive spell and not "every game missed to season's end": the board's availability
input needs a DURATION, this is that quantity, it is week-invariant modulo censoring, it is the
exact input the shipped reported-absence cap already takes (`expected_games_missed`), and it does
not conflate this injury with an unrelated one in December. `total_missed_rest` is carried beside it
as a declared diagnostic and gates nothing.

**A missed game is a team game with no certified APPEARANCE**, not merely a row labelled `inactive`.
`weekly_frame.build_spine` keeps only `ACT`/`INA` rows, so a player who lands on IR or is demoted
disappears from it; counting only `inactive` would systematically under-count exactly the long
spells a duration model exists to price. Byes are skipped, never counted as misses. (Measured: for
the modelled positions the certified appearance flag is a strict SUPERSET of the weekly stats rows —
0 stat-bearing player-weeks fall outside it — so this cannot manufacture a false miss.)

**Right-censoring is real, reported, and never imputed.** 77 of 1,309 rows (5.88%) are still absent
at the end of the regular season. The registered target is the OBSERVED count, so every arm predicts
the same bounded, decision-relevant quantity. Declared diagnostic, never a gate: the same scoring
re-run excluding censored rows.

**Metric: exact discrete CRPS** on the count support, each row's predictive truncated to
`{0..games_remaining}` and renormalised — identically for every arm and every anchor.
⛔ **Never a point MAE.** 65.6% of this target is zero and its conditional median is 0, so MAE is
minimised by the all-zero nihilist (NF-D11's inversion, measurably present here). MAE is DISCLOSED
per arm so the inversion is on the record, and it selects nothing.

⚠️ **Stated limitation.** The empirical pmf is estimated over training rows of varying remaining-
schedule length, so it is a mixture, and the per-row truncation is the uniform declared handling.
`games_remaining` is deliberately NOT a conditioner: at this depth it would multiply cells past
usefulness. The residual late-season conservatism is a known property of the estimator, not a bug.

---

## 3. Population and provenance

**Source: the landed NF-W2c / NF-W2c-CBS capture store (`nfl/pit/wayback_injuries`), 2025, read and
never rebuilt.** Realized: 1,309 (player, week) rows / 398 players / 18 of 18 weeks.

**The NF-W0a forward capture contributes ZERO rows** and the spec's premise that it would does not
hold today: it holds 12,136 rows, all `season = 2025`, all captured on one date (2026-08-05) — a
post-season backfill whose capture instant is months after every 2025 gameday, hence inadmissible
for it — and 0 rows for 2026. See §9.

**ESPN is excluded on ADMISSIBILITY, not performance** (census §3a). Its `out` rows show a realized
miss rate of 0.484 on the week they are attributed to and 0.986 on the week before (n=141); CBS
reads 1.000/0.522 and nfl.com 0.931/0.414 on the identical probe, so only ESPN inverts. Read at `w`
its designation describes a different game; re-attributed to `w−1` the capture instant no longer
bounds it and the row LEAKS. No admissible week exists in either reading. Cost: 97 distinct
player-weeks. ⛔ This was settled before any arm existed.

**Stamp rule, per source.** Both admissible sources are Wayback captures: `capture_timestamp` /
`feature_timestamp` / `ingestion_timestamp` are the archive's capture instant (a third-party-attested
moment at which the page's content demonstrably existed); `source_timestamp` is a DECLARED absence
with its reason on the row, because the page publishes no per-row vendor as-of and laundering the
archive's instant into a vendor claim would be a false provenance. Admissibility is the NF-W2 bound
verbatim: **capture strictly before the player's own gameday 00:00 UTC.** nfl.com declares its week
at page level; CBS declares its week PER ROW (its page mixes the current week with a preview of the
next). Nothing post-designation — the following practice report, the transaction that followed —
enters the row that predicts that week.

**`assert_point_in_time` is wired AND invoked** on the assembled frame, per (week, gameday):
**1,309 records checked, 0 dropped, no findings.** These rows passed NF-W2c's gate at landing; this
frame is a NEW assembly (different source set, different resolution rule), and a gate that only ever
ran upstream is a gate this story never ran (NF-C0e). `store_index={}` matches NF-W2/W2b/W2d —
consuming the latest admissible capture of a player-week is a correct as-of read, not a vendor
restatement. The store's revision clause is reported **INACTIVE** (no subject holds more than one
capture): it had nothing to act on, which is not a pass (NF-D20).

**Designation resolution: the LATEST admissible capture that CARRIES a designation wins.** A NULL
`report_status` is MISSING within a capture, not a resolved absence — nfl.com publishes practice
participation from Wednesday and fills the game-status column only on the final report, so all 50 of
its Thursday captures are blank, Friday runs 352 blank to 45 designated, and blank rows sit a median
1.52 days before kickoff against 0.34 for designated ones (census §3b). Letting a blank win on
recency would erase a real earlier CBS designation — NF-W0's "NULL ≠ healthy", in the direction that
costs signal. A player-week designated in NO admissible capture resolves to `none_listed`, which
means *"never designated in the captures we hold"*, not *"never designated by the NFL"*.

**Pre-registered sensitivity: most-severe-wins.** ⚠️ The census MEASURED it **INACTIVE**: all 18
player-weeks whose captures carry more than one distinct designation resolve identically under both
rules, because in this population a designation only ever escalates (questionable → out) and never
de-escalates. Its agreement therefore carries NO information and will be reported as inactive, never
as a passed check (NF-D20). It is registered anyway so the 2026 re-test inherits it.

**Frame integrity, checked and recorded rather than hidden** (census §5): zero-spell share by
designation reads `doubtful` 0.000 · `out` 0.020 · `questionable` 0.744 · `none_listed` 0.954 —
monotone and physically sensible. A frame in which `out` players play is broken, and registering a
study on one would be the most expensive kind of silent null. No arm is fitted, ranked or chosen on
this check.

---

## 4. The field — 7 arms, declared forward

| arm | what it is | shippable |
|---|---|---|
| `desig_empirical` | **PRIMARY.** In-fold empirical spell pmf per designation level | ✅ |
| `desig_x_posgroup` | + position (QB/RB/WR/TE), with the `MIN_CELL_N` backoff | ✅ |
| `desig_x_practice` | + practice participation (dnp/limited/full/unknown), same backoff | ✅ |
| `fixed_penalty` | the naive constant: out→1, doubtful→1, questionable→0, none_listed→0 | ⛔ |
| `status_blind_foil` | **MATCHED FOIL** — identical machinery, designation content stripped | ⛔ |
| `always_zero` | **DEGENERATE** + the served incumbent's implicit model | ⛔ |
| `always_max` | **DEGENERATE** — point mass at `games_remaining` | ⛔ |

`DECLARED_FIELD_SIZE = 7`.

**The conditioning family carries a declared BACKOFF because the census says this depth cannot
certify a position-conditional distribution.** `doubtful` holds 29 rows and `doubtful × QB` holds
**one**. A cell with fewer than `MIN_CELL_N = 30` in-fold training rows falls back to its
designation-only parent, then to the pooled distribution. 30 is a conventional a-priori floor for an
empirical distribution over a count support; ⛔ no variant is scored and nothing selects on it. This
is the spec's "coarser conditioning declared FORWARD as the family, never chosen after seeing fits".

**No smoothing**, and that is a decision: CRPS is finite for any predictive, so a smoothing constant
would buy nothing and cost a free parameter. Thin cells are the backoff's job.

**`fixed_penalty` is NOT SHIPPABLE by registration.** It is the guess the gap record names and the
disclosure map forbids. It is SCORED so the empirical forms must beat it. ⭐ If it beats every real
arm, that is a REFUTED-MAGNITUDE finding reported plainly as *a null resting on a registration
choice rather than on a gate level* — ⛔ never re-labelled shippable afterwards (NF-D20; E2.1-r in
its most literal form).

**Both degenerates sit at OPPOSITE ends of the support** (NF1.8): a constraint a degenerate
satisfies is fine because the metric eliminates it, but a criterion a degenerate WINS is fatal, so
the maximally-optimistic and the maximally-pessimistic point masses are both scored and both must
lose.

### Anchors — scored, never shippable; a missing or unfittable anchor RAISES

- **`own_form_oracle`** — a per-FORM peeking oracle: each arm's own form fitted on the test fold's
  own rows. Nothing may beat its own form's oracle. Per-form and not field-wide, because the forms
  NEST (`status_blind_foil` ⊂ `desig_empirical` ⊂ the conditioned arms) and a single ceiling would
  veto a legitimately better nested form as a false metric inversion (NF-D16 (g‴)).
- **`matched_n_control`** — the winner's own form trained on a training set the size of the oracle's
  peek, so the floor is enforced at equal family AND equal resolution (NF1.7 (b) / NF1.9 (f)).
- ⭐ **DECLARED FORWARD (NF-W6d):** an oracle whose CRPS does not beat its matched-n control by more
  than `1e-6` is an **INACTIVE anchor pair**, not a refusal. NF-W6d lost three shippable arms to
  exactly that misreading; declaring the reading in advance is the fix it asked for. An inactive
  pair is reported as UNINFORMATIVE and gates nothing; ⛔ it is never scored as a pass either.
- **`permutation`** — the winner's form fitted on designations SHUFFLED within the fold. Must LOSE.
  A permutation is well-posed at any n, which a fitted oracle is not (NF1.7 (b)).

---

## 5. Design

**PRIMARY: grouped 10-fold cross-validation by player** (`FOLD_UNIT = gsis_id`, `FOLD_SEED`
declared). A player contributes up to 14 rows whose spells overlap, so grouping keeps them together;
and at one season it is the only design giving both an admissible fold count and usable training
depth.

`N_FOLDS = 10` is the smallest count clearing the MLB-TV2-2 margin rule (`sign_floor ≤ ½ × cutoff`)
under BOTH declared BH readings — computed by `cv_power.validate_sign_certifiability` **in the
census, before this file declared it**, which is the PLAT-CVP2 discipline: a refusal re-shapes the
folds BEFORE scoring, never after.

| n_folds | sign floor | vs cutoff 0.05 | vs cutoff 0.00714 | fold-consistency wins | MDE (sd) |
|---|---|---|---|---|---|
| 7 | 0.00781 | ✅ headroom 0.156 | ⛔ **REFUSED** (need 8) | 6/7 | 1.20 |
| 8 | 0.00391 | ✅ 0.078 | ✅ 0.547 (no margin) | 6/8 | 0.95 |
| **10** | **0.00098** | ✅ **0.020** | ✅ **0.137** | **7/10** | **0.80** |
| 12 | 0.00024 | ✅ 0.005 | ✅ 0.034 | 8/12 | 0.75 |

⚠️ **THE LIMITATIONS, STATED FORWARD.** Grouped-by-player folds share WEEKS between train and test,
so week-level shocks are not held out. And at `n_seasons = 1` **season-transfer is structurally
unmeasurable** — this design certifies "does the population distribution generalise to unseen
PLAYERS", never "to an unseen SEASON". Neither is fixable at this depth; both are what make 2026 the
named re-test (§9).

**SECONDARY, declared forward and REPORTED, never a gate:** forward-chained purged week blocks
(`(7,8) … (17,18)`, 6 folds), purging on the training row's own outcome window (`w + spell < t`).
It carries a **sign-consistency reading only** — at 6 folds its sign floor (0.0156) REFUSES the
conservative cutoff, which is precisely why it is not the primary. Registering a threshold-free
sign reading is a falsifiable forward commitment that cannot be cherry-picked.

---

## 6. Gates, in the order they are read

Every gate is classified EXPLICITLY. ⛔ This registration declares `gate_classes=`; it does not fall
back on the instrument's name heuristic (PLAT-CVP2 defect 2 — a vocabulary that names nothing in a
study cannot have partitioned it, and the resulting `BLIND`/`DEFLATION_BLOCKED` inversion had to be
hand-annotated twice before the instrument learned to refuse).

| gate | class | passes when |
|---|---|---|
| `beats_incumbent` | metric | winner's pooled CRPS < `always_zero`'s |
| `beats_foil` | metric | winner's pooled CRPS < `status_blind_foil`'s |
| `fold_consistency` | metric | ≥ 7 of 10 fold wins (`cv_power.fold_consistency_clause`) |
| `bh_ok` | metric | one-sided paired p ≤ the binding cutoff |
| `oracle_respected` | metric | no arm beats its OWN-FORM oracle; matched-n control evaluable |
| `beats_permutation` | metric | winner beats its designation-shuffled self |
| `dsr_ok` | **deflation** | DSR-CONV ≥ 0.95 |
| `degenerates_lose` | **invariant** | both degenerates lose to the winner |

**`degenerates_lose` is DECLARED INJECTION-INVARIANT, forward.** Planting a stronger designation →
duration relationship cannot make a point mass at 0 or a point mass at `games_remaining` win, so an
arm stopped by this clause ALONE cleared every movable gate and is `CONSTRAINT_BLOCKED`, not
`BLIND`. Declaring it before the control runs is what stops it laundering: a gate cannot be
reclassified as injection-invariant after seeing that it blocked (E2.1-r).

**`pbo` is a FIELD-LEVEL statistic and is NOT in the per-arm gate table.** Carrying it per-arm
converts "the search was unstable" into "this arm failed", which is not a statement PBO makes.
`pbo_application = "field"` is passed to `classify_null`. Reported over the DECLARED field (7) and
over the ELIGIBLE set (the 3 shippable arms the selection actually ran over — NF1.8), with the
ELIGIBLE figure binding, alongside the NF1.8 triad (flip distribution, performance degradation,
contender spread).

### The BH family, named before scoring

This study tests **ONE mechanism on ONE population with NO position axis in the hypothesis**: does
the weekly-designation channel improve the games-missed predictive over its matched status-blind
foil? That is a **single hypothesis**, so **`BH_CUTOFF_BINDING = 0.05` BINDS**. Correcting across
ARMS would deflate a second time for the search `dsr` already deflates (the NF-INJ3b PM ruling). The
conservative arm-corrected reading `0.05 / 7 = 0.00714` is REPORTED beside it; both are
sign-certifiable at 10 folds with margin. Saying which binds, and why, before scoring is the rule.

### `V`'s membership, named before scoring

`V` (the cross-trial Sharpe dispersion `dsr` deflates against) is measured over the **five
non-degenerate arms**. The two pre-registered degenerates are EXCLUDED from `V` and RETAINED in
`n_trials = 7` for multiplicity (DSR-CONV; this registration opts in explicitly and forward, the
convention being forward-only and otherwise inert). ⭐ The incumbent REFERENCE arm for the lift
series is `always_zero`, which is already a degenerate, so MH2.1 (a) — a reference arm's identically
zero skill series inflates a small family's `V` exactly as a diagnostic anchor does — is satisfied
**by construction** rather than by a second rule that could be forgotten.

⚠️ The exclusion is NON-MONOTONE and is therefore not a lever: dropping a NEAR-MEAN arm WIDENS the
sample variance and RAISES the bar. It applies to the two arms named degenerate before any score and
to nothing else. ⛔ **No post-hoc trim of any kind** (MH2.2), and ⛔ no menu of per-candidate-family
DSRs will be published — that is what would contaminate a successor's family choice (NF-INJ3 §0a).

### The positive control (PLAT-CVP2), declared forward

`cv_power.injected_effect_positive_control` runs against the study's **own** registered gate
function — re-implementing it here would restate the harness's assumptions instead of testing them.
`inject(effect)` adds `effect` extra missed games to rows designated `out`/`doubtful` (clipped to
`games_remaining`); `inject(0.0)` returns the unmodified payload, so the two-sided null-control leg
genuinely runs. Declared effect: **1.0 game** — the smallest unit the target can express and the
magnitude the product cares about. `gate_classes`, `invariant_gates` and the null-control leg are
all passed explicitly.

⚠️ **Declared in advance:** the injection is a UNIFORM additive shift on the treated rows, so it may
make the designation-aware arms simultaneously strong NEAR-CLONES. Under MLB-HV2-1's mechanism that
raises PBO and inflates `V`, and a `DEFLATION_BLOCKED` verdict would be a statement about the
family's deflation half over THIS field, not evidence the mechanism is absent. `pbo` is not in the
per-arm table (above), so the control's field-level-gate detector should report nothing there; if it
does, that is a defect in this registration and will be reported as one.

---

## 7. Application semantics, registered forward

**One owner. No second discount path.** Expected games missed maps into the board through the
EXISTING availability machinery in `season_projection`, using the SAME remaining-season RATE the
shipped reported-absence cap already uses:

```
new_games = min(current, current × (SEASON_GAMES − E[spell]) / SEASON_GAMES)
```

`E[spell]` is read off the fitted predictive at the row's current `games_remaining`. The rate form
(not a ceiling) is the PM's 2026-08-23 ruling 1, adopted here verbatim rather than re-derived: a
ceiling `min(current, 17 − missed)` was MEASURED INERT on the real board because the model already
projects starters at 11–16 games.

**DISJOINTNESS — the single strongest applicable discount, never a stacked one.** Three channels can
touch `proj_games`: the formal roster-status cap (RES/PUP/NFI/SUS), this designation cap, and the
curated news cap. All three are min-caps on one quantity, so "strongest" is the smallest resulting
games figure; **exactly one channel is recorded as the applied owner**.

⚠️ **The NEWS-1 rule must SEE this channel or the disjointness silently breaks.** Its existing rule
is "the override is not applied when a formal discount WAS APPLIED", reading a per-row
`_formal_discount_applied` flag. If the designation cap does not set that flag, a player carrying
both a news cap and a live designation would take BOTH — precisely the stacking the rule exists to
prevent. So the designation path SETS the same flag, and the invariant is asserted on a CONSTRUCTED
both-channels row rather than trusted to a reading of the code.

⛔ **SCOPE: REGULAR-SEASON designations only.** The fitted population is 2025 REG weeks 1–18. A
PRESEASON tag is a different animal — the live 2026 snapshot of 2026-08-21 carried 116 `Questionable`
and ZERO `Out`/`Doubtful`, because the game-status report only publishes those once the season
starts. Applying an in-season fit to a preseason tag is an out-of-population read and is refused,
not quietly extended. **A consequence worth stating before anyone measures it: a counterfactual
board built TODAY (2026-09-03, before Week 1) may move almost nothing.** The value arrives with the
Week-1 report. The counterfactual will be MEASURED, not asserted.

**In-season cadence: unchanged.** The discount updates when designations update, on the existing
publish cadence. No new schedule is invented here.

**Downstream guards that must stay green on any counterfactual board:** NF-INJ1's realized-max
envelope and NF-RATE1's render suppression.

**If it ships, `test_nf_c9_designation_disclosure.py` needs a DELIBERATE amendment** — it currently
pins that the model's availability path never reads the weekly designation, which is exactly the
property this story changes. It is re-anchored onto the new implementation, ⛔ never weakened or
deleted (MH2.7), and NF-C9's user-facing copy is revisited as a NAMED follow-up, not silently.

---

## 8. The gated ship path — all deploy-held; the publish decision is the operator's

Fired ONLY if §6 clears, in this order:
1. Counterfactual board rebuild against a **capture-pinned** baseline (the D3 convention: capture
   the published board and stamp input vintages; NF-INJ2c's market-vintage preconditions are the
   pattern, and its lesson binds — a pin whose market inputs are a different day is not a pin).
2. **Population-scoped material diff at 1e-9, never bitwise** — the rookie band is not bitwise
   reproducible at the same commit, so rookie-band motion is read against the ≥5-draw envelope.
3. Whole-board placement read + interval revalidation via `--out` stems.
4. Operator packet: top-25 moves per config **including superflex** (a per-position level change is
   NOT shielded there — NF-TR2b).
5. Combined read on the EXACT publish-candidate board.

---

## 9. What a null means here, and the re-test

A POWER_LIMITED or refused verdict is an acceptable, publishable outcome. `cv_power.classify_null`
is called in the registered order with `declared_field_size = 7`, `pbo_application = "field"` and
`degenerates_excluded_from_v = True`.

**The named re-test is the 2026 season**, and it is NF-D18-clean in principle: designations accrue
weekly from Week 1 (2026-09-09), so a second season roughly doubles the depth and makes
season-transfer measurable for the first time.

⚠️ **BUT THE TRIGGER IS ONLY REACHABLE IF THE FORWARD CAPTURE ACTUALLY RUNS, AND TODAY IT DOES NOT.**
The census measured `nfl/pit/injuries` holding exactly one capture date in its entire life
(2026-08-05) and zero 2026 rows. A re-test trigger that depends on a capture which has fired once is
the actively-misleading kind unless the dependency is named, so it is named here: **the 2026 re-test
requires the NF-W0a injury capture to be running on a weekly cadence through the season.** That is a
finding for the PM (§10), not a modelling assumption.

---

## 10. Findings this registration hands forward (PM triage, not this story's to card)

1. **NF-W2c's ESPN leg has a one-week-late week attribution** — measured fingerprint, mechanism
   undiagnosed. 537 landed rows, ~25% of the substrate, currently unusable. The store is
   append-only and NF-W2c is Done, so this story reads around it rather than rebuilding it.
2. **The NF-W0a forward injury capture has fired once (2026-08-05) and holds no 2026 rows.** It is
   the substrate for every future injury re-test, including this story's own named trigger.

---

## 11. Disclosure — what had been run when this document was committed

A **single-fold code-path smoke** (fold 0 of the primary design) was executed before this commit, to
prove the arms, the reducer, the truncation and the fold builders execute and to time the run. Its
numbers are disclosed here rather than concealed: `desig_x_practice` 0.5601 · `desig_empirical` 0.5880
· `desig_x_posgroup` 0.5929 · `fixed_penalty` 0.6980 · `status_blind_foil` 0.7075 · `always_zero`
0.8725 · `always_max` 8.1007 mean CRPS.

⭐ **Every element of §§2–9 — the target, the population, the field, shippability, the folds, the
gates, the BH family, `V`'s membership, the invariant declaration and the application semantics —
was AUTHORED BEFORE that smoke ran**, and is committed here unchanged: the smoke imports those
constants, so it could not have run before they existed. Nothing in §§2–9 was written or altered
after seeing a number. Disclosing a code-path smoke is the honest handling; concealing it would not
make the registration cleaner, only less checkable.

⛔ **What the smoke is NOT.** One fold of ten, no anchors, no gates, no deflation, no fold
consistency, and no verdict. It cannot and does not select an arm: `PRIMARY_ARM` was declared
`desig_empirical` before it ran and stays `desig_empirical` — which the smoke's own ordering would
not have chosen.
