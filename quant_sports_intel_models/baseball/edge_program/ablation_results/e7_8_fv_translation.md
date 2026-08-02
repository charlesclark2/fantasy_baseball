# MLB Edge-E7.8 — do FanGraphs prospect rankings translate to MLB projection?

<!-- MH2-DESIGN-BLOCK
{
 "fold_rule": "leave-one-MLB-debut-cohort-out over `fold_cohorts`",
 "gates": {
  "dsr_min": 0.95,
  "fdr_q": 0.1,
  "pbo_max": 0.2
 },
 "n_arms": 36,
 "n_folds": 4,
 "per_metric": [
  {
   "dsr": 0.882744496438857,
   "metric": "batter/debut",
   "n_arms": 36,
   "n_folds": 4,
   "pbo": 0.0,
   "verdict": "DROP"
  },
  {
   "dsr": 0.11165734282290174,
   "metric": "batter/conditional",
   "n_arms": 36,
   "n_folds": 4,
   "pbo": 0.5,
   "verdict": "DROP"
  },
  {
   "dsr": 0.7989440670821045,
   "metric": "batter/unconditional",
   "n_arms": 36,
   "n_folds": 4,
   "pbo": 0.6666666666666666,
   "verdict": "DROP"
  },
  {
   "dsr": 0.9983693571330434,
   "metric": "pitcher/debut",
   "n_arms": 36,
   "n_folds": 4,
   "pbo": 0.0,
   "verdict": "ADD"
  },
  {
   "dsr": 0.8249767289411034,
   "metric": "pitcher/conditional",
   "n_arms": 36,
   "n_folds": 4,
   "pbo": 0.16666666666666666,
   "verdict": "DROP"
  },
  {
   "dsr": 0.997985702077806,
   "metric": "pitcher/unconditional",
   "n_arms": 36,
   "n_folds": 4,
   "pbo": 0.0,
   "verdict": "ADD"
  }
 ],
 "primary_contrast": "paired-t (BH-FDR corrected)",
 "reason": null,
 "schema": 1,
 "source_artifact": "e7_8_fv_translation.json",
 "status": "recovered",
 "verdict": "batter/debut=DROP, batter/conditional=DROP, batter/unconditional=DROP, pitcher/debut=ADD, pitcher/conditional=DROP, pitcher/unconditional=ADD"
}
-->


**Study:** `e7.8-v1` · **generated:** 2026-07-27T22:47:02.865052+00:00 · **outcome window:** 3 MLB seasons · **learner for the headline contrast:** `linear`

> ⚠️ **This is a projection-VALIDATION study, not an edge claim — `best_alpha = 0`.** It asks one question: does The Board's as-of FV/rank add incremental projection lift on realized dynasty-FANTASY value **over an age-relative-to-level + level + pedigree null**, once the survivorship and level confounds are controlled? A CLEAN NULL is a valid, high-value answer (it says: lean on our own MLE + age-relative-to-level, do not pay up for FV hype) and is NOT forced into a survivor.

## 0. Verdict

| player_type   | stage         | adds_lift   |   mean_lift |   p_value |    dsr |    pbo |   config_spread |   full_spread |
|:--------------|:--------------|:------------|------------:|----------:|-------:|-------:|----------------:|--------------:|
| batter        | debut         | False       |      0.0129 |    0.0110 | 0.8827 | 0.0000 |          0.0158 |        0.1180 |
| batter        | conditional   | False       |      0.0283 |    0.2571 | 0.1117 | 0.5000 |          0.0468 |        0.1754 |
| batter        | unconditional | False       |      0.0337 |    0.0159 | 0.7989 | 0.6667 |          0.0116 |        0.1705 |
| pitcher       | debut         | True        |      0.0268 |    0.0040 | 0.9984 | 0.0000 |          0.0148 |        0.1480 |
| pitcher       | conditional   | False       |      0.0477 |    0.0196 | 0.8250 | 0.1667 |          0.0340 |        0.1746 |
| pitcher       | unconditional | True        |      0.0411 |    0.0034 | 0.9980 | 0.0000 |          0.0333 |        0.2357 |

**🎯 DRAFT TAKEAWAY —** TRUST FV FOR PITCHER — it adds deflated, confound-controlled lift on realized dynasty-fantasy value. Use FV/rank as a headline ordering input for those, alongside (not instead of) our MLE + age-relative-to-level. For batter, FV did NOT clear the deflated gates — lean on our MLE + age-relative-to-level there and treat the grade as confirmation, not evidence.


### 0b. WHY — is FV a substitute for our own MLE, or a complement to it?

A positive contrast says FV adds something; it does not say whether FV adds something our own model already knew. This decomposes the same leaderboard into **how much our MiLB performance read adds over the null**, and **how much FV adds ON TOP of it** (each feature set at its best learner):

| player_type   | stage         |   null |   null+perf |   perf_adds |   fv_adds_over_perf |
|:--------------|:--------------|-------:|------------:|------------:|--------------------:|
| batter        | debut         | 0.8606 |      0.8973 |      0.0366 |              0.0129 |
| batter        | conditional   | 0.1953 |      0.2654 |      0.0701 |              0.0283 |
| batter        | unconditional | 0.6424 |      0.6775 |      0.0351 |              0.0041 |
| pitcher       | debut         | 0.8244 |      0.8392 |      0.0149 |              0.0268 |
| pitcher       | conditional   | 0.1791 |      0.2222 |      0.0431 |              0.0477 |
| pitcher       | unconditional | 0.6303 |      0.6152 |     -0.0152 |              0.0184 |

- **`batter`** — SUBSTITUTES — our MiLB performance read adds +0.0473 on average and FV only a further +0.0151 on top, so the MLE already captures most of what the grade would tell us.
- **`pitcher`** — COMPLEMENTS — our MiLB performance read adds +0.0142 on average while FV adds a further +0.0310 ON TOP of it, so the scouting grade carries information the statistical record does not.

> This is a *computed* read, not a narrative imposed on the numbers — a future re-run can overturn it. Where it lands as COMPLEMENTS, note the independent corroboration from **E7.3 vs E7.3p**: minor-league rates translate far better for bats than for arms (batter K% OOS corr **0.637** vs pitcher K% **0.366** on the same harness), so the statistical record leaves more unexplained on the pitching side — exactly the room a scouting grade would fill.

Gates: PBO < 0.2 · DSR ≥ 0.95 · BH-FDR q = 0.1 across the 6-test family (player_type × stage). Every stage's PBO reading:
- `batter/debut` — clears the bar
- `batter/conditional` — TIED FIELD → read as the NULL, not as overfitting (E2.1-r): the CONTENDERS are within 0.047 of each other, so 'which one wins' is noise
- `batter/unconditional` — TIED FIELD → read as the NULL, not as overfitting (E2.1-r): the CONTENDERS are within 0.012 of each other, so 'which one wins' is noise
- `pitcher/debut` — clears the bar
- `pitcher/conditional` — clears the bar
- `pitcher/unconditional` — clears the bar

## 1. The outcome target (stated + defended)

The consumers are a **dynasty board and a fantasy draft**, not a front office — so the target is fantasy VALUE, never WAR. Concretely, for each (board season, prospect):

* **Batter fantasy points** = `1.3·(H − HR) + 4.0·HR + 1.0·BB − 0.5·K`, accumulated over the **3 MLB seasons following the board snapshot**. The `1.3` weight on non-HR hits is the population mean total bases per non-home-run hit — it recovers total bases in expectation without the 2B/3B split, which the Statcast-derived mart does not expose at game grain.
* **Pitcher fantasy points** = `3.0·IP + 1.0·K − 1.0·H − 1.0·BB − 3.0·HR`, with `IP = (BF − H − BB)/3`.
* **A prospect who never reaches the majors inside the window scores ZERO** — for a dynasty owner that is a realized outcome, not missing data. This is what makes the headline stage survivorship-free.

**Why accumulated points and not a rate:** dynasty value is `playing time × quality`, and the single biggest source of prospect value dispersion is whether he plays at all. A rate target would hand the study back the survivorship confound it exists to control.

**Known target limitations (stated, not buried):** R / RBI / SB are absent from the Statcast substrate. R and RBI are lineup-context terms that largely track playing time and production (both already in the target), but **SB is a genuinely distinct speed skill this target cannot see** — a speed-first prospect is under-valued here. Pitcher W / SV / ER are likewise unavailable; HR carries the earned-run weight as the proxy, and innings are reconstructed from batters faced minus baserunners.

## 2. The cohort (and how thin it is)

| player_type   |   board_season |   prospects |   debut_rate |   median_fv |   mean_fantasy_points |
|:--------------|---------------:|------------:|-------------:|------------:|----------------------:|
| batter        |           2018 |         368 |        0.495 |          40 |                 103.5 |
| batter        |           2019 |         493 |        0.383 |          40 |                  81.2 |
| batter        |           2020 |         568 |        0.37  |          40 |                  79.4 |
| batter        |           2021 |         583 |        0.36  |          40 |                  87.8 |
| batter        |           2022 |         585 |        0.385 |          40 |                  97.8 |
| pitcher       |           2018 |         351 |        0.464 |          40 |                 145   |
| pitcher       |           2019 |         454 |        0.436 |          40 |                 136.4 |
| pitcher       |           2020 |         566 |        0.385 |          40 |                 134.7 |
| pitcher       |           2021 |         622 |        0.334 |          40 |                 125.5 |
| pitcher       |           2022 |         655 |        0.356 |          40 |                 130.1 |

Total study rows **5,245** across **2,452** distinct prospects and **5** board cohorts.

⚠️ **Small-N is the defining constraint** (the NF1.4 rookie-prior situation). The CV fold unit is the BOARD COHORT, and a full outcome window costs one cohort per horizon season, so the study has a handful of folds — enough for an honest read, not enough to resolve a small true effect. Where PBO is not computable it is reported as such, never quietly omitted.

## 3. Design — the confounds, and how each is controlled

**Survivorship.** Modelled as its own channel rather than corrected after the fact: the `debut` stage predicts WHO ARRIVES on the full cohort, the `conditional` stage measures production among survivors (and is explicitly labelled as the survivorship-exposed one), and the `unconditional` stage — the headline — scores the whole cohort with a hard zero for non-arrivals, so no selection is applied at all.

**Level confound.** `level` (one-hot) and **age-relative-to-level** (age minus the TRAIN-fold mean age at that level) are in the NULL arm, so FV is never credited for what level already told us. The level means are fitted in-fold and applied verbatim to the eval cohort.

**Leakage.** Board attributes are read at the season's as-of snapshot; the MiLB line aggregates only games STRICTLY BEFORE that date; the outcome window opens strictly AFTER it. The CV **purges from every training fold any player who appears in the eval cohort** — the same prospect sits on 3–5 consecutive boards sharing one overlapping outcome window, so without the purge a 'projection' is partly a memory.

**The pre-registered contrasts** (fixed in advance — no post-hoc winner picking): PRIMARY `null+perf+fv` vs `null+perf` (does FV add over our own performance read plus the null?) and SECONDARY `null+fv` vs `null` (is FV informative at all, before our read?). The wider feature-set × FV-transform × learner search is run too and deflated — it answers the different question 'could a cherry-picked FV configuration look good by chance?'.

**⚠️ Two documented deviations, both biasing TOWARD finding FV lift (so a null is conservative):**
1. **Pedigree is a proxy, not draft round/bonus.** MLB draft round and signing bonus are NOT in the lake (no StatsAPI draft ingest exists — that is a real follow-up story). The null uses `pro_experience_years` + level-for-age instead, which makes the null WEAKER than the story pre-registered.
2. **Pre-2026 as-of dating is approximate.** FanGraphs serves the RETAINED past board rather than a true point-in-time snapshot (E7.7 stamps those rows `<season>-07-01`), so a pre-2026 grade may embed a later revision — i.e. hindsight. The forward daily capture builds the genuine point-in-time series from 2026 onward.

## 4. `batter` — stage `debut`

> SELECTION channel — P(reach MLB with real playing time inside the window), scored by AUC on the FULL board cohort. This is the survivorship mechanism modelled EXPLICITLY instead of being allowed to inflate a production fit.

Folds (board cohorts scored): `[2019, 2020, 2021, 2022]` · train rows 2,311 (after purging 2,359 rows of prospects who recur in the eval cohort) · eval rows 2,229 · oracle ceiling 1.000 (holds ✅)

**Leaderboard** (mean out-of-sample AUC, higher is better; `uses_fangraphs` marks the FV/rank arms):

| config                                  | feature_set              | learner        | uses_fangraphs   |   oos_metric |
|:----------------------------------------|:-------------------------|:---------------|:-----------------|-------------:|
| null+perf+fv@linear                     | null+perf+fv             | linear         | True             |       0.9101 |
| null+perf+fv#bucket@linear              | null+perf+fv#bucket      | linear         | True             |       0.9064 |
| null+perf+fv+rank@linear                | null+perf+fv+rank        | linear         | True             |       0.9055 |
| null+fv@linear                          | null+fv                  | linear         | True             |       0.9029 |
| null+perf+rank@linear                   | null+perf+rank           | linear         | True             |       0.9028 |
| null+perf+fv+rank#bucket@linear         | null+perf+fv+rank#bucket | linear         | True             |       0.9020 |
| null+perf@linear                        | null+perf                | linear         | False            |       0.8973 |
| null+fv#bucket@linear                   | null+fv#bucket           | linear         | True             |       0.8965 |
| null+perf+fv+rank@gbm@200-2-0.05        | null+perf+fv+rank        | gbm@200-2-0.05 | True             |       0.8943 |
| null+perf+fv@gbm@200-2-0.05             | null+perf+fv             | gbm@200-2-0.05 | True             |       0.8938 |
| null+perf+fv+rank#bucket@gbm@200-2-0.05 | null+perf+fv+rank#bucket | gbm@200-2-0.05 | True             |       0.8937 |
| null+perf+rank@gbm@200-2-0.05           | null+perf+rank           | gbm@200-2-0.05 | True             |       0.8933 |
| null+rank@linear                        | null+rank                | linear         | True             |       0.8905 |
| null+perf+fv#bucket@gbm@200-2-0.05      | null+perf+fv#bucket      | gbm@200-2-0.05 | True             |       0.8895 |
| null+perf@gbm@200-2-0.05                | null+perf                | gbm@200-2-0.05 | False            |       0.8885 |
| null+fv@gbm@200-2-0.05                  | null+fv                  | gbm@200-2-0.05 | True             |       0.8879 |
| null+rank@gbm@200-2-0.05                | null+rank                | gbm@200-2-0.05 | True             |       0.8875 |
| null+perf+fv@gbm@400-3-0.03             | null+perf+fv             | gbm@400-3-0.03 | True             |       0.8872 |
| null+perf+fv+rank@gbm@400-3-0.03        | null+perf+fv+rank        | gbm@400-3-0.03 | True             |       0.8859 |
| null+perf+fv+rank#bucket@gbm@400-3-0.03 | null+perf+fv+rank#bucket | gbm@400-3-0.03 | True             |       0.8851 |
| null+perf+fv#bucket@gbm@400-3-0.03      | null+perf+fv#bucket      | gbm@400-3-0.03 | True             |       0.8841 |
| null+perf+rank@gbm@400-3-0.03           | null+perf+rank           | gbm@400-3-0.03 | True             |       0.8839 |
| null+perf@gbm@400-3-0.03                | null+perf                | gbm@400-3-0.03 | False            |       0.8825 |
| null+rank@gbm@400-3-0.03                | null+rank                | gbm@400-3-0.03 | True             |       0.8825 |
| null+fv#bucket@gbm@200-2-0.05           | null+fv#bucket           | gbm@200-2-0.05 | True             |       0.8813 |
| null+fv@gbm@400-3-0.03                  | null+fv                  | gbm@400-3-0.03 | True             |       0.8802 |
| null+fv#bucket@gbm@400-3-0.03           | null+fv#bucket           | gbm@400-3-0.03 | True             |       0.8709 |
| null@gbm@400-3-0.03                     | null                     | gbm@400-3-0.03 | False            |       0.8606 |
| null@gbm@200-2-0.05                     | null                     | gbm@200-2-0.05 | False            |       0.8604 |
| null@linear                             | null                     | linear         | False            |       0.8560 |
| fv_only@linear                          | fv_only                  | linear         | True             |       0.8321 |
| fv_only#bucket@linear                   | fv_only#bucket           | linear         | True             |       0.8218 |
| fv_only@gbm@200-2-0.05                  | fv_only                  | gbm@200-2-0.05 | True             |       0.8141 |
| fv_only@gbm@400-3-0.03                  | fv_only                  | gbm@400-3-0.03 | True             |       0.8068 |
| fv_only#bucket@gbm@200-2-0.05           | fv_only#bucket           | gbm@200-2-0.05 | True             |       0.8015 |
| fv_only#bucket@gbm@400-3-0.03           | fv_only#bucket           | gbm@400-3-0.03 | True             |       0.7921 |

**PRIMARY contrast — `null+perf+fv` − `null+perf`:**

| learner        |   mean_lift |   p_value |    dsr | per_fold_delta                   |
|:---------------|------------:|----------:|-------:|:---------------------------------|
| linear         |      0.0129 |    0.0110 | 0.8827 | [0.0194, 0.0148, 0.0053, 0.012]  |
| gbm@200-2-0.05 |      0.0053 |    0.0148 | 0.8201 | [0.0017, 0.0082, 0.0051, 0.0064] |
| gbm@400-3-0.03 |      0.0047 |    0.0698 | 0.4425 | [0.0006, 0.0103, 0.0011, 0.0066] |

**SECONDARY contrast — `null+fv` − `null`:**

| learner        |   mean_lift |   p_value |    dsr | per_fold_delta                    |
|:---------------|------------:|----------:|-------:|:----------------------------------|
| linear         |      0.0469 |    0.0072 | 0.9582 | [0.0472, 0.0701, 0.0254, 0.045]   |
| gbm@200-2-0.05 |      0.0274 |    0.0457 | 0.6221 | [0.0043, 0.0579, 0.0214, 0.0261]  |
| gbm@400-3-0.03 |      0.0196 |    0.0946 | 0.3646 | [-0.0096, 0.0469, 0.0215, 0.0195] |

## 4. `batter` — stage `conditional`

> PRODUCTION GIVEN ARRIVAL — fantasy points among prospects who debuted, Spearman ρ. ⚠️ This stage is survivorship-EXPOSED by construction (its population is the survivors); it is reported so the inflation is visible, and it is NOT the headline.

Folds (board cohorts scored): `[2019, 2020, 2021, 2022]` · train rows 1,064 (after purging 861 rows of prospects who recur in the eval cohort) · eval rows 834 · oracle ceiling 1.000 (holds ✅)

**Leaderboard** (mean out-of-sample Spearman ρ, higher is better; `uses_fangraphs` marks the FV/rank arms):

| config                                  | feature_set              | learner        | uses_fangraphs   |   oos_metric |
|:----------------------------------------|:-------------------------|:---------------|:-----------------|-------------:|
| null+rank@linear                        | null+rank                | linear         | True             |       0.3339 |
| null+perf+rank@linear                   | null+perf+rank           | linear         | True             |       0.3103 |
| null+fv@gbm@200-2-0.05                  | null+fv                  | gbm@200-2-0.05 | True             |       0.3047 |
| null+perf+fv+rank@linear                | null+perf+fv+rank        | linear         | True             |       0.3012 |
| null+perf+rank@gbm@200-2-0.05           | null+perf+rank           | gbm@200-2-0.05 | True             |       0.2958 |
| null+perf+fv@linear                     | null+perf+fv             | linear         | True             |       0.2936 |
| null+perf+fv+rank#bucket@gbm@200-2-0.05 | null+perf+fv+rank#bucket | gbm@200-2-0.05 | True             |       0.2902 |
| null+rank@gbm@200-2-0.05                | null+rank                | gbm@200-2-0.05 | True             |       0.2881 |
| null+perf+fv+rank#bucket@linear         | null+perf+fv+rank#bucket | linear         | True             |       0.2871 |
| null+perf+fv+rank@gbm@200-2-0.05        | null+perf+fv+rank        | gbm@200-2-0.05 | True             |       0.2853 |
| null+perf+fv#bucket@linear              | null+perf+fv#bucket      | linear         | True             |       0.2824 |
| fv_only@gbm@200-2-0.05                  | fv_only                  | gbm@200-2-0.05 | True             |       0.2730 |
| null+perf+rank@gbm@400-3-0.03           | null+perf+rank           | gbm@400-3-0.03 | True             |       0.2709 |
| null+perf+fv@gbm@200-2-0.05             | null+perf+fv             | gbm@200-2-0.05 | True             |       0.2689 |
| null+fv#bucket@linear                   | null+fv#bucket           | linear         | True             |       0.2679 |
| null+fv@linear                          | null+fv                  | linear         | True             |       0.2678 |
| null+fv@gbm@400-3-0.03                  | null+fv                  | gbm@400-3-0.03 | True             |       0.2674 |
| null+perf@linear                        | null+perf                | linear         | False            |       0.2654 |
| null+perf+fv+rank@gbm@400-3-0.03        | null+perf+fv+rank        | gbm@400-3-0.03 | True             |       0.2502 |
| fv_only#bucket@linear                   | fv_only#bucket           | linear         | True             |       0.2449 |
| null+fv#bucket@gbm@200-2-0.05           | null+fv#bucket           | gbm@200-2-0.05 | True             |       0.2447 |
| null+perf+fv#bucket@gbm@200-2-0.05      | null+perf+fv#bucket      | gbm@200-2-0.05 | True             |       0.2447 |
| fv_only@linear                          | fv_only                  | linear         | True             |       0.2444 |
| null+rank@gbm@400-3-0.03                | null+rank                | gbm@400-3-0.03 | True             |       0.2426 |
| null+perf@gbm@400-3-0.03                | null+perf                | gbm@400-3-0.03 | False            |       0.2398 |
| null+perf+fv@gbm@400-3-0.03             | null+perf+fv             | gbm@400-3-0.03 | True             |       0.2388 |
| null+perf+fv+rank#bucket@gbm@400-3-0.03 | null+perf+fv+rank#bucket | gbm@400-3-0.03 | True             |       0.2360 |
| null+perf+fv#bucket@gbm@400-3-0.03      | null+perf+fv#bucket      | gbm@400-3-0.03 | True             |       0.2341 |
| fv_only@gbm@400-3-0.03                  | fv_only                  | gbm@400-3-0.03 | True             |       0.2304 |
| null+fv#bucket@gbm@400-3-0.03           | null+fv#bucket           | gbm@400-3-0.03 | True             |       0.2226 |
| null+perf@gbm@200-2-0.05                | null+perf                | gbm@200-2-0.05 | False            |       0.2214 |
| fv_only#bucket@gbm@200-2-0.05           | fv_only#bucket           | gbm@200-2-0.05 | True             |       0.2168 |
| null@gbm@200-2-0.05                     | null                     | gbm@200-2-0.05 | False            |       0.1953 |
| null@linear                             | null                     | linear         | False            |       0.1867 |
| fv_only#bucket@gbm@400-3-0.03           | fv_only#bucket           | gbm@400-3-0.03 | True             |       0.1729 |
| null@gbm@400-3-0.03                     | null                     | gbm@400-3-0.03 | False            |       0.1585 |

**PRIMARY contrast — `null+perf+fv` − `null+perf`:**

| learner        |   mean_lift |   p_value |    dsr | per_fold_delta                     |
|:---------------|------------:|----------:|-------:|:-----------------------------------|
| linear         |      0.0283 |    0.2571 | 0.1117 | [-0.0262, -0.0482, 0.1041, 0.0833] |
| gbm@200-2-0.05 |      0.0475 |    0.0136 | 0.9004 | [0.0555, 0.0202, 0.0389, 0.0752]   |
| gbm@400-3-0.03 |     -0.0010 |    0.5260 | 0.0284 | [0.0071, -0.023, -0.0251, 0.0368]  |

**SECONDARY contrast — `null+fv` − `null`:**

| learner        |   mean_lift |   p_value |    dsr | per_fold_delta                   |
|:---------------|------------:|----------:|-------:|:---------------------------------|
| linear         |      0.0811 |    0.2368 | 0.1555 | [-0.1889, 0.0558, 0.251, 0.2066] |
| gbm@200-2-0.05 |      0.1094 |    0.0299 | 0.6767 | [0.009, 0.1204, 0.1877, 0.1206]  |
| gbm@400-3-0.03 |      0.1088 |    0.0150 | 0.8672 | [0.0417, 0.0862, 0.1408, 0.1667] |

## 4. `batter` — stage `unconditional`

> ⭐ THE DRAFT-RELEVANT STAGE — fantasy points over the WHOLE cohort with a hard 0 for a prospect who never arrived, Spearman ρ. Zero is a realized dynasty outcome, not missing data, so this stage carries NO survivorship selection.

Folds (board cohorts scored): `[2019, 2020, 2021, 2022]` · train rows 2,311 (after purging 2,359 rows of prospects who recur in the eval cohort) · eval rows 2,229 · oracle ceiling 1.000 (holds ✅)

**Leaderboard** (mean out-of-sample Spearman ρ, higher is better; `uses_fangraphs` marks the FV/rank arms):

| config                                  | feature_set              | learner        | uses_fangraphs   |   oos_metric |
|:----------------------------------------|:-------------------------|:---------------|:-----------------|-------------:|
| null+perf+rank@gbm@200-2-0.05           | null+perf+rank           | gbm@200-2-0.05 | True             |       0.6888 |
| null+fv@gbm@400-3-0.03                  | null+fv                  | gbm@400-3-0.03 | True             |       0.6816 |
| null+perf+fv@gbm@400-3-0.03             | null+perf+fv             | gbm@400-3-0.03 | True             |       0.6815 |
| null+rank@linear                        | null+rank                | linear         | True             |       0.6802 |
| null+fv@linear                          | null+fv                  | linear         | True             |       0.6799 |
| null+perf+fv+rank@gbm@400-3-0.03        | null+perf+fv+rank        | gbm@400-3-0.03 | True             |       0.6777 |
| null+perf@gbm@400-3-0.03                | null+perf                | gbm@400-3-0.03 | False            |       0.6775 |
| null+fv@gbm@200-2-0.05                  | null+fv                  | gbm@200-2-0.05 | True             |       0.6774 |
| null+perf+rank@gbm@400-3-0.03           | null+perf+rank           | gbm@400-3-0.03 | True             |       0.6772 |
| null+perf+fv+rank@gbm@200-2-0.05        | null+perf+fv+rank        | gbm@200-2-0.05 | True             |       0.6762 |
| null+perf+fv+rank#bucket@gbm@200-2-0.05 | null+perf+fv+rank#bucket | gbm@200-2-0.05 | True             |       0.6757 |
| null+perf+rank@linear                   | null+perf+rank           | linear         | True             |       0.6716 |
| null+perf+fv+rank#bucket@gbm@400-3-0.03 | null+perf+fv+rank#bucket | gbm@400-3-0.03 | True             |       0.6714 |
| null+perf+fv@linear                     | null+perf+fv             | linear         | True             |       0.6703 |
| null+perf+fv@gbm@200-2-0.05             | null+perf+fv             | gbm@200-2-0.05 | True             |       0.6694 |
| null+perf@gbm@200-2-0.05                | null+perf                | gbm@200-2-0.05 | False            |       0.6681 |
| null+rank@gbm@200-2-0.05                | null+rank                | gbm@200-2-0.05 | True             |       0.6675 |
| null+perf+fv+rank@linear                | null+perf+fv+rank        | linear         | True             |       0.6656 |
| null+perf+fv+rank#bucket@linear         | null+perf+fv+rank#bucket | linear         | True             |       0.6586 |
| null+perf+fv#bucket@gbm@400-3-0.03      | null+perf+fv#bucket      | gbm@400-3-0.03 | True             |       0.6577 |
| null+fv#bucket@gbm@200-2-0.05           | null+fv#bucket           | gbm@200-2-0.05 | True             |       0.6571 |
| null+fv#bucket@linear                   | null+fv#bucket           | linear         | True             |       0.6565 |
| null+rank@gbm@400-3-0.03                | null+rank                | gbm@400-3-0.03 | True             |       0.6559 |
| null+perf+fv#bucket@gbm@200-2-0.05      | null+perf+fv#bucket      | gbm@200-2-0.05 | True             |       0.6501 |
| null+fv#bucket@gbm@400-3-0.03           | null+fv#bucket           | gbm@400-3-0.03 | True             |       0.6496 |
| null+perf+fv#bucket@linear              | null+perf+fv#bucket      | linear         | True             |       0.6484 |
| null@gbm@200-2-0.05                     | null                     | gbm@200-2-0.05 | False            |       0.6424 |
| null+perf@linear                        | null+perf                | linear         | False            |       0.6366 |
| null@linear                             | null                     | linear         | False            |       0.6254 |
| null@gbm@400-3-0.03                     | null                     | gbm@400-3-0.03 | False            |       0.6082 |
| fv_only@linear                          | fv_only                  | linear         | True             |       0.5947 |
| fv_only@gbm@200-2-0.05                  | fv_only                  | gbm@200-2-0.05 | True             |       0.5676 |
| fv_only#bucket@linear                   | fv_only#bucket           | linear         | True             |       0.5583 |
| fv_only@gbm@400-3-0.03                  | fv_only                  | gbm@400-3-0.03 | True             |       0.5517 |
| fv_only#bucket@gbm@200-2-0.05           | fv_only#bucket           | gbm@200-2-0.05 | True             |       0.5439 |
| fv_only#bucket@gbm@400-3-0.03           | fv_only#bucket           | gbm@400-3-0.03 | True             |       0.5183 |

**PRIMARY contrast — `null+perf+fv` − `null+perf`:**

| learner        |   mean_lift |   p_value |    dsr | per_fold_delta                     |
|:---------------|------------:|----------:|-------:|:-----------------------------------|
| linear         |      0.0337 |    0.0159 | 0.7989 | [0.034, 0.0518, 0.0393, 0.0096]    |
| gbm@200-2-0.05 |      0.0013 |    0.3622 | 0.0766 | [-0.0077, 0.0012, 0.0073, 0.0042]  |
| gbm@400-3-0.03 |      0.0041 |    0.2839 | 0.0590 | [0.0228, -0.0049, 0.0007, -0.0023] |

**SECONDARY contrast — `null+fv` − `null`:**

| learner        |   mean_lift |   p_value |    dsr | per_fold_delta                   |
|:---------------|------------:|----------:|-------:|:---------------------------------|
| linear         |      0.0545 |    0.0408 | 0.6230 | [0.0025, 0.1057, 0.0575, 0.0522] |
| gbm@200-2-0.05 |      0.0350 |    0.1168 | 0.2067 | [-0.0047, 0.103, 0.0245, 0.0171] |
| gbm@400-3-0.03 |      0.0734 |    0.0407 | 0.6765 | [0.1475, 0.0872, 0.0379, 0.021]  |

## 4. `pitcher` — stage `debut`

> SELECTION channel — P(reach MLB with real playing time inside the window), scored by AUC on the FULL board cohort. This is the survivorship mechanism modelled EXPLICITLY instead of being allowed to inflate a production fit.

Folds (board cohorts scored): `[2019, 2020, 2021, 2022]` · train rows 2,270 (after purging 2,250 rows of prospects who recur in the eval cohort) · eval rows 2,297 · oracle ceiling 1.000 (holds ✅)

**Leaderboard** (mean out-of-sample AUC, higher is better; `uses_fangraphs` marks the FV/rank arms):

| config                                  | feature_set              | learner        | uses_fangraphs   |   oos_metric |
|:----------------------------------------|:-------------------------|:---------------|:-----------------|-------------:|
| null+perf+fv+rank@linear                | null+perf+fv+rank        | linear         | True             |       0.8677 |
| null+perf+fv@linear                     | null+perf+fv             | linear         | True             |       0.8660 |
| null+fv@linear                          | null+fv                  | linear         | True             |       0.8657 |
| null+rank@linear                        | null+rank                | linear         | True             |       0.8627 |
| null+perf+rank@linear                   | null+perf+rank           | linear         | True             |       0.8620 |
| null+perf+fv+rank#bucket@linear         | null+perf+fv+rank#bucket | linear         | True             |       0.8618 |
| null+perf+fv#bucket@linear              | null+perf+fv#bucket      | linear         | True             |       0.8550 |
| null+fv@gbm@200-2-0.05                  | null+fv                  | gbm@200-2-0.05 | True             |       0.8531 |
| null+fv#bucket@linear                   | null+fv#bucket           | linear         | True             |       0.8529 |
| null+fv#bucket@gbm@200-2-0.05           | null+fv#bucket           | gbm@200-2-0.05 | True             |       0.8493 |
| null+fv@gbm@400-3-0.03                  | null+fv                  | gbm@400-3-0.03 | True             |       0.8458 |
| null+perf+fv@gbm@200-2-0.05             | null+perf+fv             | gbm@200-2-0.05 | True             |       0.8449 |
| null+perf+fv+rank#bucket@gbm@200-2-0.05 | null+perf+fv+rank#bucket | gbm@200-2-0.05 | True             |       0.8434 |
| null+perf+fv#bucket@gbm@200-2-0.05      | null+perf+fv#bucket      | gbm@200-2-0.05 | True             |       0.8431 |
| null+perf+fv+rank@gbm@200-2-0.05        | null+perf+fv+rank        | gbm@200-2-0.05 | True             |       0.8428 |
| null+perf+rank@gbm@200-2-0.05           | null+perf+rank           | gbm@200-2-0.05 | True             |       0.8421 |
| null+fv#bucket@gbm@400-3-0.03           | null+fv#bucket           | gbm@400-3-0.03 | True             |       0.8417 |
| null+rank@gbm@200-2-0.05                | null+rank                | gbm@200-2-0.05 | True             |       0.8398 |
| null+perf@linear                        | null+perf                | linear         | False            |       0.8392 |
| null+rank@gbm@400-3-0.03                | null+rank                | gbm@400-3-0.03 | True             |       0.8356 |
| null+perf+fv+rank#bucket@gbm@400-3-0.03 | null+perf+fv+rank#bucket | gbm@400-3-0.03 | True             |       0.8355 |
| null+perf+fv+rank@gbm@400-3-0.03        | null+perf+fv+rank        | gbm@400-3-0.03 | True             |       0.8353 |
| null+perf+fv@gbm@400-3-0.03             | null+perf+fv             | gbm@400-3-0.03 | True             |       0.8341 |
| null+perf@gbm@200-2-0.05                | null+perf                | gbm@200-2-0.05 | False            |       0.8336 |
| null+perf+rank@gbm@400-3-0.03           | null+perf+rank           | gbm@400-3-0.03 | True             |       0.8326 |
| null+perf+fv#bucket@gbm@400-3-0.03      | null+perf+fv#bucket      | gbm@400-3-0.03 | True             |       0.8325 |
| null+perf@gbm@400-3-0.03                | null+perf                | gbm@400-3-0.03 | False            |       0.8245 |
| null@linear                             | null                     | linear         | False            |       0.8244 |
| null@gbm@200-2-0.05                     | null                     | gbm@200-2-0.05 | False            |       0.8238 |
| null@gbm@400-3-0.03                     | null                     | gbm@400-3-0.03 | False            |       0.8205 |
| fv_only@linear                          | fv_only                  | linear         | True             |       0.7708 |
| fv_only#bucket@linear                   | fv_only#bucket           | linear         | True             |       0.7497 |
| fv_only@gbm@200-2-0.05                  | fv_only                  | gbm@200-2-0.05 | True             |       0.7388 |
| fv_only#bucket@gbm@200-2-0.05           | fv_only#bucket           | gbm@200-2-0.05 | True             |       0.7303 |
| fv_only@gbm@400-3-0.03                  | fv_only                  | gbm@400-3-0.03 | True             |       0.7242 |
| fv_only#bucket@gbm@400-3-0.03           | fv_only#bucket           | gbm@400-3-0.03 | True             |       0.7197 |

**PRIMARY contrast — `null+perf+fv` − `null+perf`:**

| learner        |   mean_lift |   p_value |    dsr | per_fold_delta                   |
|:---------------|------------:|----------:|-------:|:---------------------------------|
| linear         |      0.0268 |    0.0040 | 0.9984 | [0.0287, 0.0184, 0.0379, 0.0223] |
| gbm@200-2-0.05 |      0.0113 |    0.0094 | 0.9345 | [0.0055, 0.0096, 0.0132, 0.0168] |
| gbm@400-3-0.03 |      0.0096 |    0.0001 | 1.0000 | [0.0085, 0.0105, 0.0092, 0.0101] |

**SECONDARY contrast — `null+fv` − `null`:**

| learner        |   mean_lift |   p_value |    dsr | per_fold_delta                   |
|:---------------|------------:|----------:|-------:|:---------------------------------|
| linear         |      0.0413 |    0.0265 | 0.7394 | [0.0084, 0.0735, 0.0419, 0.0415] |
| gbm@200-2-0.05 |      0.0292 |    0.0002 | 0.9997 | [0.0259, 0.0282, 0.0336, 0.0293] |
| gbm@400-3-0.03 |      0.0253 |    0.0254 | 0.6925 | [0.0024, 0.0262, 0.0366, 0.0362] |

## 4. `pitcher` — stage `conditional`

> PRODUCTION GIVEN ARRIVAL — fantasy points among prospects who debuted, Spearman ρ. ⚠️ This stage is survivorship-EXPOSED by construction (its population is the survivors); it is reported so the inflation is visible, and it is NOT the headline.

Folds (board cohorts scored): `[2019, 2020, 2021, 2022]` · train rows 1,135 (after purging 755 rows of prospects who recur in the eval cohort) · eval rows 857 · oracle ceiling 1.000 (holds ✅)

**Leaderboard** (mean out-of-sample Spearman ρ, higher is better; `uses_fangraphs` marks the FV/rank arms):

| config                                  | feature_set              | learner        | uses_fangraphs   |   oos_metric |
|:----------------------------------------|:-------------------------|:---------------|:-----------------|-------------:|
| null+perf+fv@linear                     | null+perf+fv             | linear         | True             |       0.2699 |
| null+rank@gbm@200-2-0.05                | null+rank                | gbm@200-2-0.05 | True             |       0.2622 |
| null+fv@linear                          | null+fv                  | linear         | True             |       0.2515 |
| null+rank@linear                        | null+rank                | linear         | True             |       0.2504 |
| null+perf+rank@gbm@200-2-0.05           | null+perf+rank           | gbm@200-2-0.05 | True             |       0.2495 |
| null+perf+rank@linear                   | null+perf+rank           | linear         | True             |       0.2415 |
| null+perf+fv+rank@gbm@200-2-0.05        | null+perf+fv+rank        | gbm@200-2-0.05 | True             |       0.2410 |
| null+perf+fv#bucket@linear              | null+perf+fv#bucket      | linear         | True             |       0.2387 |
| null+perf+fv+rank#bucket@gbm@200-2-0.05 | null+perf+fv+rank#bucket | gbm@200-2-0.05 | True             |       0.2359 |
| null+perf+fv+rank@linear                | null+perf+fv+rank        | linear         | True             |       0.2350 |
| null+fv#bucket@linear                   | null+fv#bucket           | linear         | True             |       0.2350 |
| null+rank@gbm@400-3-0.03                | null+rank                | gbm@400-3-0.03 | True             |       0.2327 |
| null+perf+fv+rank#bucket@gbm@400-3-0.03 | null+perf+fv+rank#bucket | gbm@400-3-0.03 | True             |       0.2238 |
| fv_only@linear                          | fv_only                  | linear         | True             |       0.2232 |
| null+perf@linear                        | null+perf                | linear         | False            |       0.2222 |
| null+perf+rank@gbm@400-3-0.03           | null+perf+rank           | gbm@400-3-0.03 | True             |       0.2200 |
| null+perf+fv+rank@gbm@400-3-0.03        | null+perf+fv+rank        | gbm@400-3-0.03 | True             |       0.2193 |
| null+perf+fv+rank#bucket@linear         | null+perf+fv+rank#bucket | linear         | True             |       0.2167 |
| null+fv@gbm@200-2-0.05                  | null+fv                  | gbm@200-2-0.05 | True             |       0.2164 |
| null+perf+fv@gbm@200-2-0.05             | null+perf+fv             | gbm@200-2-0.05 | True             |       0.2159 |
| fv_only#bucket@linear                   | fv_only#bucket           | linear         | True             |       0.2112 |
| null+perf+fv#bucket@gbm@200-2-0.05      | null+perf+fv#bucket      | gbm@200-2-0.05 | True             |       0.2006 |
| null+perf+fv@gbm@400-3-0.03             | null+perf+fv             | gbm@400-3-0.03 | True             |       0.1963 |
| null+perf+fv#bucket@gbm@400-3-0.03      | null+perf+fv#bucket      | gbm@400-3-0.03 | True             |       0.1867 |
| null@linear                             | null                     | linear         | False            |       0.1791 |
| fv_only@gbm@200-2-0.05                  | fv_only                  | gbm@200-2-0.05 | True             |       0.1783 |
| null+perf@gbm@200-2-0.05                | null+perf                | gbm@200-2-0.05 | False            |       0.1713 |
| null+fv#bucket@gbm@200-2-0.05           | null+fv#bucket           | gbm@200-2-0.05 | True             |       0.1693 |
| fv_only#bucket@gbm@200-2-0.05           | fv_only#bucket           | gbm@200-2-0.05 | True             |       0.1607 |
| null+perf@gbm@400-3-0.03                | null+perf                | gbm@400-3-0.03 | False            |       0.1527 |
| null+fv@gbm@400-3-0.03                  | null+fv                  | gbm@400-3-0.03 | True             |       0.1525 |
| null@gbm@200-2-0.05                     | null                     | gbm@200-2-0.05 | False            |       0.1525 |
| fv_only@gbm@400-3-0.03                  | fv_only                  | gbm@400-3-0.03 | True             |       0.1460 |
| fv_only#bucket@gbm@400-3-0.03           | fv_only#bucket           | gbm@400-3-0.03 | True             |       0.1344 |
| null+fv#bucket@gbm@400-3-0.03           | null+fv#bucket           | gbm@400-3-0.03 | True             |       0.1193 |
| null@gbm@400-3-0.03                     | null                     | gbm@400-3-0.03 | False            |       0.0953 |

**PRIMARY contrast — `null+perf+fv` − `null+perf`:**

| learner        |   mean_lift |   p_value |    dsr | per_fold_delta                   |
|:---------------|------------:|----------:|-------:|:---------------------------------|
| linear         |      0.0477 |    0.0196 | 0.8250 | [0.0159, 0.0743, 0.0348, 0.0658] |
| gbm@200-2-0.05 |      0.0446 |    0.0048 | 0.9399 | [0.054, 0.0578, 0.0244, 0.0422]  |
| gbm@400-3-0.03 |      0.0436 |    0.0783 | 0.4229 | [0.0656, 0.0925, -0.0148, 0.031] |

**SECONDARY contrast — `null+fv` − `null`:**

| learner        |   mean_lift |   p_value |    dsr | per_fold_delta                     |
|:---------------|------------:|----------:|-------:|:-----------------------------------|
| linear         |      0.0724 |    0.0124 | 0.8917 | [0.0303, 0.0975, 0.0579, 0.1037]   |
| gbm@200-2-0.05 |      0.0639 |    0.1468 | 0.1945 | [-0.0214, -0.0101, 0.1933, 0.0938] |
| gbm@400-3-0.03 |      0.0572 |    0.0128 | 0.9967 | [0.0545, 0.0343, 0.0968, 0.0433]   |

## 4. `pitcher` — stage `unconditional`

> ⭐ THE DRAFT-RELEVANT STAGE — fantasy points over the WHOLE cohort with a hard 0 for a prospect who never arrived, Spearman ρ. Zero is a realized dynasty outcome, not missing data, so this stage carries NO survivorship selection.

Folds (board cohorts scored): `[2019, 2020, 2021, 2022]` · train rows 2,270 (after purging 2,250 rows of prospects who recur in the eval cohort) · eval rows 2,297 · oracle ceiling 1.000 (holds ✅)

**Leaderboard** (mean out-of-sample Spearman ρ, higher is better; `uses_fangraphs` marks the FV/rank arms):

| config                                  | feature_set              | learner        | uses_fangraphs   |   oos_metric |
|:----------------------------------------|:-------------------------|:---------------|:-----------------|-------------:|
| null+fv@gbm@200-2-0.05                  | null+fv                  | gbm@200-2-0.05 | True             |       0.6693 |
| null+fv@linear                          | null+fv                  | linear         | True             |       0.6660 |
| null+fv@gbm@400-3-0.03                  | null+fv                  | gbm@400-3-0.03 | True             |       0.6650 |
| null+rank@gbm@200-2-0.05                | null+rank                | gbm@200-2-0.05 | True             |       0.6621 |
| null+fv#bucket@gbm@200-2-0.05           | null+fv#bucket           | gbm@200-2-0.05 | True             |       0.6581 |
| null+rank@linear                        | null+rank                | linear         | True             |       0.6565 |
| null+perf+rank@gbm@200-2-0.05           | null+perf+rank           | gbm@200-2-0.05 | True             |       0.6436 |
| null+fv#bucket@gbm@400-3-0.03           | null+fv#bucket           | gbm@400-3-0.03 | True             |       0.6412 |
| null+perf+fv+rank#bucket@gbm@200-2-0.05 | null+perf+fv+rank#bucket | gbm@200-2-0.05 | True             |       0.6360 |
| null+perf+fv+rank@gbm@200-2-0.05        | null+perf+fv+rank        | gbm@200-2-0.05 | True             |       0.6342 |
| null+perf+fv@gbm@200-2-0.05             | null+perf+fv             | gbm@200-2-0.05 | True             |       0.6335 |
| null+fv#bucket@linear                   | null+fv#bucket           | linear         | True             |       0.6325 |
| null@gbm@200-2-0.05                     | null                     | gbm@200-2-0.05 | False            |       0.6303 |
| null+rank@gbm@400-3-0.03                | null+rank                | gbm@400-3-0.03 | True             |       0.6287 |
| null+perf+fv#bucket@gbm@200-2-0.05      | null+perf+fv#bucket      | gbm@200-2-0.05 | True             |       0.6271 |
| null@gbm@400-3-0.03                     | null                     | gbm@400-3-0.03 | False            |       0.6237 |
| null+perf+fv+rank#bucket@gbm@400-3-0.03 | null+perf+fv+rank#bucket | gbm@400-3-0.03 | True             |       0.6206 |
| null+perf+rank@gbm@400-3-0.03           | null+perf+rank           | gbm@400-3-0.03 | True             |       0.6194 |
| null+perf+fv@gbm@400-3-0.03             | null+perf+fv             | gbm@400-3-0.03 | True             |       0.6163 |
| null+perf@gbm@200-2-0.05                | null+perf                | gbm@200-2-0.05 | False            |       0.6152 |
| null+perf+rank@linear                   | null+perf+rank           | linear         | True             |       0.6151 |
| null+perf+fv#bucket@gbm@400-3-0.03      | null+perf+fv#bucket      | gbm@400-3-0.03 | True             |       0.6147 |
| null+perf+fv+rank@gbm@400-3-0.03        | null+perf+fv+rank        | gbm@400-3-0.03 | True             |       0.6139 |
| null+perf+fv@linear                     | null+perf+fv             | linear         | True             |       0.6057 |
| null+perf+fv+rank@linear                | null+perf+fv+rank        | linear         | True             |       0.6016 |
| null@linear                             | null                     | linear         | False            |       0.5951 |
| null+perf@gbm@400-3-0.03                | null+perf                | gbm@400-3-0.03 | False            |       0.5840 |
| null+perf+fv+rank#bucket@linear         | null+perf+fv+rank#bucket | linear         | True             |       0.5820 |
| null+perf+fv#bucket@linear              | null+perf+fv#bucket      | linear         | True             |       0.5758 |
| null+perf@linear                        | null+perf                | linear         | False            |       0.5647 |
| fv_only@linear                          | fv_only                  | linear         | True             |       0.5061 |
| fv_only#bucket@linear                   | fv_only#bucket           | linear         | True             |       0.4575 |
| fv_only#bucket@gbm@200-2-0.05           | fv_only#bucket           | gbm@200-2-0.05 | True             |       0.4552 |
| fv_only@gbm@200-2-0.05                  | fv_only                  | gbm@200-2-0.05 | True             |       0.4523 |
| fv_only@gbm@400-3-0.03                  | fv_only                  | gbm@400-3-0.03 | True             |       0.4383 |
| fv_only#bucket@gbm@400-3-0.03           | fv_only#bucket           | gbm@400-3-0.03 | True             |       0.4336 |

**PRIMARY contrast — `null+perf+fv` − `null+perf`:**

| learner        |   mean_lift |   p_value |    dsr | per_fold_delta                    |
|:---------------|------------:|----------:|-------:|:----------------------------------|
| linear         |      0.0411 |    0.0034 | 0.9980 | [0.0338, 0.0503, 0.0525, 0.0276]  |
| gbm@200-2-0.05 |      0.0184 |    0.1666 | 0.1379 | [0.0639, -0.0107, 0.0112, 0.0091] |
| gbm@400-3-0.03 |      0.0323 |    0.0893 | 0.2953 | [0.0859, 0.0177, 0.0238, 0.0018]  |

**SECONDARY contrast — `null+fv` − `null`:**

| learner        |   mean_lift |   p_value |    dsr | per_fold_delta                   |
|:---------------|------------:|----------:|-------:|:---------------------------------|
| linear         |      0.0709 |    0.0055 | 0.9989 | [0.0858, 0.0986, 0.0493, 0.0498] |
| gbm@200-2-0.05 |      0.0390 |    0.0052 | 0.9777 | [0.0551, 0.0231, 0.0432, 0.0344] |
| gbm@400-3-0.03 |      0.0414 |    0.0039 | 0.9606 | [0.0444, 0.0405, 0.056, 0.0245]  |

## 5. Limitations

- **Small-N by construction** — one CV fold per board cohort with a closed outcome window. A true small effect is not resolvable here; the study can honestly rule out a LARGE one.
- **The CV is cohort-out, not strictly real-time.** A model tested on cohort *S* trains on earlier boards whose outcome windows had not fully closed by *S*. The strictly-real-time variant (`--strict-realtime`) leaves too few folds for PBO at this cohort count; it is run as a sensitivity where the folds exist.
- **Pedigree proxy, not draft round/bonus** (see §3) — the null is weaker than pre-registered.
- **Pre-2026 as-of is approximate** (see §3) — a retained board, not a point-in-time snapshot.
- **The target cannot see stolen bases** (nor pitcher W/SV/ER) — see §1.
- **The board is FanGraphs' graded population**, ~1.3k names a season. Prospects FanGraphs never graded are outside the study, so this measures 'is the GRADE informative among the graded', not 'is the board's coverage complete'.
- **`best_alpha = 0`** — a Dynasty projection-validation study, never a market claim.

