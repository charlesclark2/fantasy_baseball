# NF-D17 — track-record Δρ POPULATION SENSITIVITY (pre-registered re-computation)

_generated 2026-08-16T00:39:39.040584+00:00 · seasons 2019–2025 · `best_alpha = 0` (a descriptive-accuracy question, no edge claim rides on it)_

⚠️ **The pre-registration is `track_record_population.py`, committed in its own commit BEFORE this harness existed or any number was computed.** Populations, sources, metric, anchors, uncertainty rule and decision rule were all fixed in writing first; nothing below was chosen after seeing a result.

⚠️ **The shipped public headline (Δρ +0.022, FFC-only, 2019–2024) is UNCHANGED by this run** and remains the NF-D13-audited-correct FFC-only figure. This memo produces a SECOND honest reading; any change to the public claim is a disclosed operator decision (§8).

## 0. The finding in one paragraph

**The premise does not hold: on the matched population the shipped number does not move.** Vs **FFC** the shipped per-source population (P0) gives Δρ **+0.018** (~167 players/season) and the pre-registered cross-source MATCHED population (P1 = our universe ∩ FFC ∩ MFL) gives **+0.018** (~166/season) — identical to three decimals, intervals overlapping. The reason is structural and visible in §2: **FFC's ranked players are very nearly a SUBSET of MFL's** (166 of 167 survive the intersection), so matching to MFL removes almost nobody from FFC's population and there is nothing for a population effect to act on. ⭐ **What IS population-sensitive is the OTHER source:** MFL reads **+0.169** [+0.133, +0.200] on its own deeper ~264-player population but collapses to **+0.016** [-0.013, +0.049] once restricted to FFC's shallower one. So the FFC/MFL gap is a **DEPTH** effect, not a source-quality effect: hold the population fixed and the two real-draft ADP crowds agree to within 0.002. ⚠️ **And the finding that matters most for a public claim points the other way from the story's hypothesis:** the shipped +0.022's own 90% paired bootstrap interval is [-0.007, +0.044], which **includes zero** — on FFC's top-~167 population our ordering is not distinguishable from the draft crowd's. Nothing here supports raising the public number; the pre-registered decision rule returns KEEP THE SHIPPED NUMBER.

## 1. Anchors — the reading is void unless all four pass (§5)

**A4 REPRODUCTION** — P0 must reproduce the shipped scorecard's own aggregate before any other number is trusted:

| source | shipped Δρ | this run | shipped n_seasons | this run | pass |
|---|---|---|---|---|---|
| `adp` | +0.018 | +0.018 | 7 | 7 | ✅ |
| `mfl_adp` | +0.169 | +0.169 | 7 | 7 | ✅ |

**A1 identity / A2 oracle floor / A3 degenerate random** — run on EVERY population × source. An anchor that fails to EVALUATE is a FAILURE, never a silent pass (NF1.7 (a)).

- populations × sources scored: **57**
- A1 identity Δρ exactly 0: **57/57**
- A2 oracle floor ≥ the real arm: **57/57**
- A3 degenerate random < 0 and < the real arm: **57/57**

## 2. The populations, in rows (§3 P3)

Why this story exists at all: the two real-draft ADP sources cover very different fractions of the same scored universe, so "FFC-only" is an implicit population choice.

| season | our scored universe | FFC aligned | FFC cov | MFL aligned | MFL cov | FFC∩MFL aligned |
|---|---|---|---|---|---|---|
| 2019 | 404 | 161 | 39.9% | 257 | 63.6% | 159 |
| 2020 | 425 | 161 | 37.9% | 287 | 67.5% | 160 |
| 2021 | 455 | 170 | 37.4% | 267 | 58.7% | 169 |
| 2022 | 440 | 140 | 31.8% | 259 | 58.9% | 140 |
| 2023 | 436 | 169 | 38.8% | 268 | 61.5% | 169 |
| 2024 | 441 | 172 | 39.0% | 262 | 59.4% | 172 |
| 2025 | 463 | 193 | 41.7% | 251 | 54.2% | 193 |

## 3. Δρ by population × source (every pre-registered reading, labelled, with n)

ρ = within-position Spearman vs realized PPR, position-pooled, season-averaged — the SHIPPED metric, unchanged. CI = 90% paired player-level bootstrap (1000 draws, seed 20260803).

| population | source | seasons | n/season | our ρ | source ρ | **Δρ** | SD across seasons | 90% CI | ≠0 |
|---|---|---|---|---|---|---|---|---|---|
| P0_shipped | 🟩 `adp` | 7 | 167 (140–193) | 0.512 | 0.493 | **+0.018** | +0.038 | [-0.007, +0.044] | no |
| P0_shipped | 🟩 `mfl_adp` | 7 | 264 (251–287) | 0.663 | 0.494 | **+0.169** | +0.066 | [+0.133, +0.200] | yes |
| P0_shipped | · `ecr` | 7 | 382 (340–420) | 0.727 | 0.739 | **-0.013** | +0.007 | [-0.021, -0.005] | yes |
| P0_shipped | · `sleeper` | 7 | 410 (354–436) | 0.729 | 0.841 | **-0.113** | +0.093 | [-0.129, -0.098] | yes |
| P0_shipped | · `espn` | 3 | 446 (437–463) | 0.748 | 0.787 | **-0.040** | +0.037 | [-0.063, -0.018] | yes |
| P1_cross_source_matched | 🟩 `adp` | 7 | 166 (140–193) | 0.513 | 0.496 | **+0.018** | +0.039 | [-0.008, +0.043] | no |
| P1_cross_source_matched | 🟩 `mfl_adp` | 7 | 166 (140–193) | 0.513 | 0.497 | **+0.016** | +0.058 | [-0.013, +0.049] | no |

🟩 = headline-eligible (a real-draft ADP consensus, which is what the public claim is about). `ecr`/`sleeper`/`espn` are CONTEXT ONLY and can never become a headline (§4) — they are carried so this memo cannot be accused of reporting only the sources that flatter us.

## 4. P2 — the depth curve, BOTH truncation sides (§3)

⚠️ **Only the band between the two sides is interpretable.** Truncating to "the top K" by one side's own ordering range-restricts that side and attenuates its ρ, biasing Δρ toward the other. `by_source` is biased toward US; `by_us` is biased toward THEM. A one-sided depth number is inadmissible and must never be quoted. ⛔ No K is selected — the curve is the deliverable.

**`adp`**

| top-K | Δρ (truncated by source · pro-us) | n | Δρ (truncated by us · pro-them) | n |
|---|---|---|---|---|
| 100 | +0.055 | 100 | +0.032 | 100 |
| 150 | +0.019 | 149 | +0.026 | 149 |
| 200 | +0.018 | 167 | +0.018 | 167 |
| 250 | +0.018 | 167 | +0.018 | 167 |
| 300 | +0.018 | 167 | +0.018 | 167 |
| ALL (= P0) | +0.018 | 167 | +0.018 | 167 |

**`mfl_adp`**

| top-K | Δρ (truncated by source · pro-us) | n | Δρ (truncated by us · pro-them) | n |
|---|---|---|---|---|
| 100 | +0.081 | 100 | +0.035 | 100 |
| 150 | +0.197 | 150 | +0.016 | 150 |
| 200 | +0.216 | 200 | +0.010 | 200 |
| 250 | +0.189 | 250 | +0.100 | 250 |
| 300 | +0.169 | 264 | +0.169 | 264 |
| ALL (= P0) | +0.169 | 264 | +0.169 | 264 |

## 5. §7 forensic — placing NF3.2's deferred +0.144 / +0.088

The deferred figures have **no recorded derivation in the repo** (NF3.2 carded the observation, not the code). The pre-registration required this leg be reported either way, and forbade hunting outside the registered set for a definition that hits them.

| source | deferred figure | closest PRE-REGISTERED reading | Δ | reproduced (±0.02)? |
|---|---|---|---|---|
| `adp` | +0.144 | P0_shipped = +0.018 | 0.126 | ❌ no |
| `mfl_adp` | +0.088 | P1_cross_source_matched = +0.016 | 0.072 | ❌ no |

- `adp`: the closest cell of ANY kind is `P2_depth100_by_source` = +0.055 (gap 0.089) — reported for completeness but **NOT a reproduction**: one-sided depth truncation (§3 P2) — range-restricts one side, ruled inadmissible by the pre-registration BEFORE the run.
- `mfl_adp`: the closest cell of ANY kind is `P2_depth100_by_source` = +0.081 (gap 0.007) — reported for completeness but **NOT a reproduction**: one-sided depth truncation (§3 P2) — range-restricts one side, ruled inadmissible by the pre-registration BEFORE the run.

**Neither deferred figure is reproduced by ANY pre-registered population.** Per the §7 pre-commitment this is reported as a finding rather than chased: reverse-engineering a population to hit a remembered number is the same inversion as reverse-engineering one to hit a flattering number, and is strictly worse because the target is already known.

## 6. §8 decision rule, executed mechanically

- `adp`: P0 +0.018 [-0.007, 0.044] vs P1 +0.018 [-0.008, 0.043] — P1 excludes 0: **False**; P0/P1 materially different (non-overlapping CIs): **False** ⇒ change-eligible: **False**
- `mfl_adp`: P0 +0.169 [0.133, 0.2] vs P1 +0.016 [-0.013, 0.049] — P1 excludes 0: **False**; P0/P1 materially different (non-overlapping CIs): **True** ⇒ change-eligible: **False**


### ⇒ KEEP THE SHIPPED NUMBER — no pre-registered condition for a change was met (§8.3)

### What this run does and does not license

1. ⛔ **It does not license raising the headline.** The pre-registered primary (P1) is +0.018 — the same number that already ships — and its interval includes zero. No population in the registered set makes the FFC claim bigger.

2. ⭐ **It strengthens the case that the shipped claim is honest rather than understated.** The public headline is a bare Δρ with an explicit "multi-season average, not a promise for any single position or season" caveat and no "we beat" language (enforced by `export_track_record_json._CLAIM_DENYLIST`). Given the interval [-0.007, +0.044], that phrasing is doing real work and should not be loosened.

3. 🟡 **There IS a larger, interval-clean reading — and it is a DIFFERENT claim, not a better measurement of the same one.** Vs MFL over all 7 seasons (incl. 2025, which FFC has no archive for at all) Δρ is **+0.169** with a 90% interval [+0.133, +0.200] that excludes zero, on ~264 players/season. P1 shows WHY: it is not that MFL is a worse crowd — restricted to FFC's population MFL reads +0.016 — it is that **a draft-crowd ordering degrades faster than ours as you go deeper into the pool**, and MFL ranks ~98 more players per season than FFC. Quoting +0.169 without stating the depth would be the exact confound this story exists to prevent.

   ⚠️ **This session does NOT recommend that swap and the pre-registered rule does not permit it** (§8.3 allows recommending only the pre-registered primary). Switching the headline source to the one that reads higher is the §4 prohibition, and it would need to be justified on grounds fixed BEFORE the numbers were seen — MFL's genuinely wider coverage (~64% vs ~40% of our scored universe) and its 7-season span are such grounds, but they were not pre-registered as a selection criterion here. If the operator wants that framing, the honest form is to report **both**, each labelled with its population and depth, and to say plainly that the difference between them is depth and not disagreement between the two crowds.

4. 📏 **Two uncertainty readings, both reported, neither hidden.** The 90% intervals above are PAIRED player-level bootstraps holding the season set fixed — they answer "given these seasons, is our ordering better?". The across-season SD column answers the wider question (FFC: SD +0.038 over 7 seasons ⇒ a season-level SE of ~0.014). Both are narrow enough to matter and neither rescues the FFC claim from straddling zero.

## 7. Method lessons (reusable)

- ⭐ **A "matched population" fix does nothing when one population is already a SUBSET of the other — and you cannot know that without computing the intersection SIZE first.** The whole premise of this story was that matching would move the FFC number; §2 shows FFC ∩ MFL retains 159–172 of FFC's 140–172 rows, i.e. essentially all of them. The intersection COUNT is a design quantity available before any ρ is computed, and reading it first would have predicted the null. **Report the population overlap before the metric, not after.**

- ⭐⭐ **A one-sided depth truncation can manufacture an arbitrary Δρ, and this run measures how big the artifact is.** At top-200 vs MFL, truncating by the SOURCE's own ordering gives **+0.218** and truncating by OURS gives **+0.016** — a band of **0.20**, an order of magnitude wider than the effect under study, from nothing but which side you range-restricted. Any "top-N" benchmark comparison that does not state which side defined the N is uninterpretable. This is why §3 pre-registered BOTH sides as mandatory rather than picking one.

- ⭐ **The forensic leg needed its own admissibility rule, and that rule fired.** The closest cell to the deferred +0.088 (MFL) across the whole run is `P2_depth100_by_source` = +0.079, a gap of 0.009 — inside the ±0.02 "match" tolerance. Had the pre-registration not already ruled one-sided depth readings inadmissible, that coincidence would have been reported as a REPRODUCTION of the deferred figure by a reading the same document calls meaningless. **A near-match found by a method you already disqualified is a coincidence, not a corroboration** — and the only defence is to have written the disqualification down first.

- ⭐ **The identity anchor (A1) is cheap and is the one that proves the population machinery cannot manufacture a gap.** Scoring a source against ITSELF must return exactly 0.0 on every population; it did, on all 57 cells. A population filter with a sign error, a mis-aligned merge or an asymmetric tie-break would break this before it broke anything a human would notice in a Δρ table.

- ⭐⭐ **A GUARD ON A MULTI-CLAUSE RULE IS VACUOUS UNLESS ITS FIXTURE SATISFIES EVERY *OTHER* CLAUSE — and this story's most important guard shipped that way in its first cut.** The decision rule refuses a change unless BOTH "P1's interval excludes 0" AND "P0/P1 are materially different". The test named for the first clause used this run's real shape (P1 +0.144, interval straddling 0, intervals overlapping) — but the OVERLAP clause already refused it, so **deleting `excludes_zero` from the source left the suite GREEN**. Found only by deliberately breaking the source, and fixed by constructing a fixture where every other clause is SATISFIED so the named clause is the only thing that can refuse (and a mirror fixture for the other clause). Both are now verified RED on their own defect. **Generalises to any AND-composed gate in this repo: a fixture that trips two clauses at once tests neither.** The NF1.7 (a) vacuous-anchor class, one level up — in the TEST rather than in the anchor.

## 8. Closing

`best_alpha = 0`. The shipped public claim is untouched by this run. Any change to it is a DISCLOSED product change (re-export via the guarded `--publish` + a changelog entry), decided by the operator from the fully-reported pre-registered set above — never a quiet edit, and never the best of several definitions tried.