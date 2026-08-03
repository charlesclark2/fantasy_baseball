# NF-D17 — track-record Δρ POPULATION SENSITIVITY (pre-registered re-computation)

_generated 2026-08-03T04:46:44.242071+00:00 · seasons 2019–2025 · `best_alpha = 0` (a descriptive-accuracy question, no edge claim rides on it)_

⚠️ **The pre-registration is `track_record_population.py`, committed in its own commit BEFORE this harness existed or any number was computed.** Populations, sources, metric, anchors, uncertainty rule and decision rule were all fixed in writing first; nothing below was chosen after seeing a result.

⚠️ **The shipped public headline (Δρ +0.022, FFC-only, 2019–2024) is UNCHANGED by this run** and remains the NF-D13-audited-correct FFC-only figure. This memo produces a SECOND honest reading; any change to the public claim is a disclosed operator decision (§8).

## 0. The finding in one paragraph

**The premise does not hold: on the matched population the shipped number does not move.** Vs **FFC** the shipped per-source population (P0) gives Δρ **+0.022** (~162 players/season) and the pre-registered cross-source MATCHED population (P1 = our universe ∩ FFC ∩ MFL) gives **+0.022** (~161/season) — identical to three decimals, intervals overlapping. The reason is structural and visible in §2: **FFC's ranked players are very nearly a SUBSET of MFL's** (161 of 162 survive the intersection), so matching to MFL removes almost nobody from FFC's population and there is nothing for a population effect to act on. ⭐ **What IS population-sensitive is the OTHER source:** MFL reads **+0.173** [+0.140, +0.207] on its own deeper ~264-player population but collapses to **+0.008** [-0.027, +0.040] once restricted to FFC's shallower one. So the FFC/MFL gap is a **DEPTH** effect, not a source-quality effect: hold the population fixed and the two real-draft ADP crowds agree to within 0.014. ⚠️ **And the finding that matters most for a public claim points the other way from the story's hypothesis:** the shipped +0.022's own 90% paired bootstrap interval is [-0.006, +0.051], which **includes zero** — on FFC's top-~162 population our ordering is not distinguishable from the draft crowd's. Nothing here supports raising the public number; the pre-registered decision rule returns KEEP THE SHIPPED NUMBER.

## 1. Anchors — the reading is void unless all four pass (§5)

**A4 REPRODUCTION** — P0 must reproduce the shipped scorecard's own aggregate before any other number is trusted:

| source | shipped Δρ | this run | shipped n_seasons | this run | pass |
|---|---|---|---|---|---|
| `adp` | +0.022 | +0.022 | 6 | 6 | ✅ |
| `mfl_adp` | +0.173 | +0.173 | 7 | 7 | ✅ |

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
| 2020 | 425 | 160 | 37.6% | 286 | 67.3% | 159 |
| 2021 | 455 | 170 | 37.4% | 266 | 58.5% | 169 |
| 2022 | 440 | 140 | 31.8% | 259 | 58.9% | 140 |
| 2023 | 436 | 169 | 38.8% | 268 | 61.5% | 169 |
| 2024 | 441 | 172 | 39.0% | 262 | 59.4% | 172 |
| 2025 | 463 | — | — | 251 | 54.2% | — |

## 3. Δρ by population × source (every pre-registered reading, labelled, with n)

ρ = within-position Spearman vs realized PPR, position-pooled, season-averaged — the SHIPPED metric, unchanged. CI = 90% paired player-level bootstrap (1000 draws, seed 20260803).

| population | source | seasons | n/season | our ρ | source ρ | **Δρ** | SD across seasons | 90% CI | ≠0 |
|---|---|---|---|---|---|---|---|---|---|
| P0_shipped | 🟩 `adp` | 6 | 162 (140–172) | 0.517 | 0.494 | **+0.022** | +0.040 | [-0.006, +0.051] | no |
| P0_shipped | 🟩 `mfl_adp` | 7 | 264 (251–286) | 0.666 | 0.494 | **+0.173** | +0.067 | [+0.140, +0.207] | yes |
| P0_shipped | · `ecr` | 7 | 381 (340–419) | 0.728 | 0.740 | **-0.012** | +0.007 | [-0.019, -0.004] | yes |
| P0_shipped | · `sleeper` | 7 | 409 (353–435) | 0.731 | 0.841 | **-0.110** | +0.093 | [-0.126, -0.097] | yes |
| P0_shipped | · `espn` | 3 | 446 (436–463) | 0.750 | 0.788 | **-0.038** | +0.036 | [-0.060, -0.015] | yes |
| P1_cross_source_matched | 🟩 `adp` | 6 | 161 (140–172) | 0.519 | 0.497 | **+0.022** | +0.041 | [-0.008, +0.048] | no |
| P1_cross_source_matched | 🟩 `mfl_adp` | 6 | 161 (140–172) | 0.519 | 0.511 | **+0.008** | +0.053 | [-0.027, +0.040] | no |

🟩 = headline-eligible (a real-draft ADP consensus, which is what the public claim is about). `ecr`/`sleeper`/`espn` are CONTEXT ONLY and can never become a headline (§4) — they are carried so this memo cannot be accused of reporting only the sources that flatter us.

## 4. P2 — the depth curve, BOTH truncation sides (§3)

⚠️ **Only the band between the two sides is interpretable.** Truncating to "the top K" by one side's own ordering range-restricts that side and attenuates its ρ, biasing Δρ toward the other. `by_source` is biased toward US; `by_us` is biased toward THEM. A one-sided depth number is inadmissible and must never be quoted. ⛔ No K is selected — the curve is the deliverable.

**`adp`**

| top-K | Δρ (truncated by source · pro-us) | n | Δρ (truncated by us · pro-them) | n |
|---|---|---|---|---|
| 100 | +0.058 | 100 | +0.023 | 100 |
| 150 | +0.019 | 148 | +0.026 | 148 |
| 200 | +0.022 | 162 | +0.022 | 162 |
| 250 | +0.022 | 162 | +0.022 | 162 |
| 300 | +0.022 | 162 | +0.022 | 162 |
| ALL (= P0) | +0.022 | 162 | +0.022 | 162 |

**`mfl_adp`**

| top-K | Δρ (truncated by source · pro-us) | n | Δρ (truncated by us · pro-them) | n |
|---|---|---|---|---|
| 100 | +0.079 | 100 | +0.034 | 100 |
| 150 | +0.197 | 150 | +0.026 | 150 |
| 200 | +0.218 | 200 | +0.016 | 200 |
| 250 | +0.193 | 250 | +0.105 | 250 |
| 300 | +0.173 | 264 | +0.173 | 264 |
| ALL (= P0) | +0.173 | 264 | +0.173 | 264 |

## 5. §7 forensic — placing NF3.2's deferred +0.144 / +0.088

The deferred figures have **no recorded derivation in the repo** (NF3.2 carded the observation, not the code). The pre-registration required this leg be reported either way, and forbade hunting outside the registered set for a definition that hits them.

| source | deferred figure | closest PRE-REGISTERED reading | Δ | reproduced (±0.02)? |
|---|---|---|---|---|
| `adp` | +0.144 | P0_shipped = +0.022 | 0.122 | ❌ no |
| `mfl_adp` | +0.088 | P1_cross_source_matched = +0.008 | 0.08 | ❌ no |

- `adp`: the closest cell of ANY kind is `P2_depth100_by_source` = +0.058 (gap 0.086) — reported for completeness but **NOT a reproduction**: one-sided depth truncation (§3 P2) — range-restricts one side, ruled inadmissible by the pre-registration BEFORE the run.
- `mfl_adp`: the closest cell of ANY kind is `P2_depth100_by_source` = +0.079 (gap 0.009) — reported for completeness but **NOT a reproduction**: one-sided depth truncation (§3 P2) — range-restricts one side, ruled inadmissible by the pre-registration BEFORE the run.

**Neither deferred figure is reproduced by ANY pre-registered population.** Per the §7 pre-commitment this is reported as a finding rather than chased: reverse-engineering a population to hit a remembered number is the same inversion as reverse-engineering one to hit a flattering number, and is strictly worse because the target is already known.

### 5b. DISCLOSED POST-HOC PROBE — was it the `g >= 6` survivor filter?

⚠️ **NOT pre-registered. Added after the pre-registered run and disclosed as such.** NF3.2 described the population as "players … that have a realized outcome"; the shipped metric uses `g >= 6`. This probe asks ONLY whether the deferred figure hides behind that one filter. Admissible in exactly one direction (it can CHECK a claim, never become a headline); it is not in `preregistered_specs()` and never enters the decision rule.

| realized filter | population | source | seasons | n/season | Δρ |
|---|---|---|---|---|---|
| g>=6 (pre-registered / shipped) | P0_shipped | `adp` | 6 | 162 | +0.022 |
| g>=6 (pre-registered / shipped) | P0_shipped | `mfl_adp` | 7 | 264 | +0.173 |
| g>=6 (pre-registered / shipped) | P1_cross_source_matched | `adp` | 6 | 161 | +0.022 |
| g>=6 (pre-registered / shipped) | P1_cross_source_matched | `mfl_adp` | 6 | 161 | +0.008 |
| g>0 (post-hoc probe) | P0_shipped | `adp` | 6 | 169 | +0.025 |
| g>0 (post-hoc probe) | P0_shipped | `mfl_adp` | 7 | 288 | +0.210 |
| g>0 (post-hoc probe) | P1_cross_source_matched | `adp` | 6 | 168 | +0.024 |
| g>0 (post-hoc probe) | P1_cross_source_matched | `mfl_adp` | 6 | 168 | +0.009 |

## 6. §8 decision rule, executed mechanically

- `adp`: P0 +0.022 [-0.006, 0.051] vs P1 +0.022 [-0.008, 0.048] — P1 excludes 0: **False**; P0/P1 materially different (non-overlapping CIs): **False** ⇒ change-eligible: **False**
- `mfl_adp`: P0 +0.173 [0.14, 0.207] vs P1 +0.008 [-0.027, 0.04] — P1 excludes 0: **False**; P0/P1 materially different (non-overlapping CIs): **True** ⇒ change-eligible: **False**


### ⇒ KEEP THE SHIPPED NUMBER — no pre-registered condition for a change was met (§8.3)

### What this run does and does not license

1. ⛔ **It does not license raising the headline.** The pre-registered primary (P1) is +0.022 — the same number that already ships — and its interval includes zero. No population in the registered set makes the FFC claim bigger.

2. ⭐ **It strengthens the case that the shipped claim is honest rather than understated.** The public headline is a bare Δρ with an explicit "multi-season average, not a promise for any single position or season" caveat and no "we beat" language (enforced by `export_track_record_json._CLAIM_DENYLIST`). Given the interval [-0.006, +0.051], that phrasing is doing real work and should not be loosened.

3. 🟡 **There IS a larger, interval-clean reading — and it is a DIFFERENT claim, not a better measurement of the same one.** Vs MFL over all 7 seasons (incl. 2025, which FFC has no archive for at all) Δρ is **+0.173** with a 90% interval [+0.140, +0.207] that excludes zero, on ~264 players/season. P1 shows WHY: it is not that MFL is a worse crowd — restricted to FFC's population MFL reads +0.008 — it is that **a draft-crowd ordering degrades faster than ours as you go deeper into the pool**, and MFL ranks ~102 more players per season than FFC. Quoting +0.173 without stating the depth would be the exact confound this story exists to prevent.

   ⚠️ **This session does NOT recommend that swap and the pre-registered rule does not permit it** (§8.3 allows recommending only the pre-registered primary). Switching the headline source to the one that reads higher is the §4 prohibition, and it would need to be justified on grounds fixed BEFORE the numbers were seen — MFL's genuinely wider coverage (~64% vs ~40% of our scored universe) and its 7-season span are such grounds, but they were not pre-registered as a selection criterion here. If the operator wants that framing, the honest form is to report **both**, each labelled with its population and depth, and to say plainly that the difference between them is depth and not disagreement between the two crowds.

4. 📏 **Two uncertainty readings, both reported, neither hidden.** The 90% intervals above are PAIRED player-level bootstraps holding the season set fixed — they answer "given these seasons, is our ordering better?". The across-season SD column answers the wider question (FFC: SD +0.040 over 6 seasons ⇒ a season-level SE of ~0.016). Both are narrow enough to matter and neither rescues the FFC claim from straddling zero.

## 7. Method lessons (reusable)

- ⭐ **A "matched population" fix does nothing when one population is already a SUBSET of the other — and you cannot know that without computing the intersection SIZE first.** The whole premise of this story was that matching would move the FFC number; §2 shows FFC ∩ MFL retains 159–172 of FFC's 140–172 rows, i.e. essentially all of them. The intersection COUNT is a design quantity available before any ρ is computed, and reading it first would have predicted the null. **Report the population overlap before the metric, not after.**

- ⭐⭐ **A one-sided depth truncation can manufacture an arbitrary Δρ, and this run measures how big the artifact is.** At top-200 vs MFL, truncating by the SOURCE's own ordering gives **+0.218** and truncating by OURS gives **+0.016** — a band of **0.20**, an order of magnitude wider than the effect under study, from nothing but which side you range-restricted. Any "top-N" benchmark comparison that does not state which side defined the N is uninterpretable. This is why §3 pre-registered BOTH sides as mandatory rather than picking one.

- ⭐ **The forensic leg needed its own admissibility rule, and that rule fired.** The closest cell to the deferred +0.088 (MFL) across the whole run is `P2_depth100_by_source` = +0.079, a gap of 0.009 — inside the ±0.02 "match" tolerance. Had the pre-registration not already ruled one-sided depth readings inadmissible, that coincidence would have been reported as a REPRODUCTION of the deferred figure by a reading the same document calls meaningless. **A near-match found by a method you already disqualified is a coincidence, not a corroboration** — and the only defence is to have written the disqualification down first.

- ⭐ **The identity anchor (A1) is cheap and is the one that proves the population machinery cannot manufacture a gap.** Scoring a source against ITSELF must return exactly 0.0 on every population; it did, on all 57 cells. A population filter with a sign error, a mis-aligned merge or an asymmetric tie-break would break this before it broke anything a human would notice in a Δρ table.

- ⭐⭐ **A GUARD ON A MULTI-CLAUSE RULE IS VACUOUS UNLESS ITS FIXTURE SATISFIES EVERY *OTHER* CLAUSE — and this story's most important guard shipped that way in its first cut.** The decision rule refuses a change unless BOTH "P1's interval excludes 0" AND "P0/P1 are materially different". The test named for the first clause used this run's real shape (P1 +0.144, interval straddling 0, intervals overlapping) — but the OVERLAP clause already refused it, so **deleting `excludes_zero` from the source left the suite GREEN**. Found only by deliberately breaking the source, and fixed by constructing a fixture where every other clause is SATISFIED so the named clause is the only thing that can refuse (and a mirror fixture for the other clause). Both are now verified RED on their own defect. **Generalises to any AND-composed gate in this repo: a fixture that trips two clauses at once tests neither.** The NF1.7 (a) vacuous-anchor class, one level up — in the TEST rather than in the anchor.

## 8. Closing

`best_alpha = 0`. The shipped public claim is untouched by this run. Any change to it is a DISCLOSED product change (re-export via the guarded `--publish` + a changelog entry), decided by the operator from the fully-reported pre-registered set above — never a quiet edit, and never the best of several definitions tried.