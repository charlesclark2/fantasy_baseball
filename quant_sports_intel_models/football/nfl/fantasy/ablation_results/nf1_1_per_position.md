# NF1.1 — per-position independent models, TOP-TIER-weighted selection (market-blind)

**Model:** `nfl_fantasy_nf1_1_v1` · **generated:** 2026-07-27T04:05:24.486836+00:00 · **base seasons:** 2017–2024 · **scored targets:** [2019, 2020, 2021, 2022, 2023, 2024, 2025] · **pool:** 2995 · **Optuna trials/class:** 40

> **Selection metric:** top-tier within-position ρ (tier = top-N by the MVP-1 incumbent, N={'QB': 24, 'RB': 36, 'WR': 48, 'TE': 24}) — fixed across candidates (a candidate cannot game its own tier), oracle-ceiling-checked (E2.1-r). Candidates per position: pos_ridge / pos_gbm / pos_similarity (the comparables learner) vs the MVP-1 per-position null. MARKET-BLIND (no ADP/ECR). xFP features (NF-D7) join as candidates — the heuristic blend null is NOT re-litigated. Deflation gates for a repoint: PBO<0.2 · DSR≥0.95 · BH-FDR q=0.1. `best_alpha = 0`.

- **oracle metric sane:** True

## QB

| candidate        |   top-tier ρ |   full ρ | hp                                                                                                                                      |
|:-----------------|-------------:|---------:|:----------------------------------------------------------------------------------------------------------------------------------------|
| pos_null (MVP-1) |       0.3681 |   0.6485 |                                                                                                                                         |
| pos_ridge        |       0.4041 |   0.6591 | {"alpha": 9.347566053529972}                                                                                                            |
| pos_gbm ⭐       |       0.4199 |   0.6484 | {"n_estimators": 150, "num_leaves": 18, "learning_rate": 0.03698206177627045, "min_child_samples": 7, "reg_lambda": 1.7949736030439343} |
| pos_similarity   |       0.3584 |   0.6503 | {"k": 53, "weight_power": 1.2974871837731616, "mvp1_emphasis": 2.2968046579903363}                                                      |

- **winner:** `pos_gbm` · beats null: **True** (Δ top-tier ρ +0.0518)
- **deflation** (127 configs): PBO 0.8286 (spread 0.1780) · DSR 0.0279 · p 0.1855 · FDR pass False
- **verdict:** NULL — MVP-1 stands (pbo_ok, dsr_ok, fdr_ok)

**Feature ablation on the winner (drop-one group; negative Δ = the group carries signal):**

| drop   |   mean_top |   delta |
|:-------|-----------:|--------:|
| usage  |     0.3811 | -0.0388 |
| mover  |     0.4199 |  0      |
| env    |     0.3928 | -0.0271 |
| injury |     0.4199 |  0      |
| age    |     0.3938 | -0.0261 |
| role   |     0.3914 | -0.0285 |
| xfp    |     0.394  | -0.0259 |

## RB

| candidate        |   top-tier ρ |   full ρ | hp                                                                                                                                        |
|:-----------------|-------------:|---------:|:------------------------------------------------------------------------------------------------------------------------------------------|
| pos_null (MVP-1) |       0.5095 |   0.7341 |                                                                                                                                           |
| pos_ridge ⭐     |       0.6083 |   0.7426 | {"alpha": 0.9504011684640693}                                                                                                             |
| pos_gbm          |       0.5685 |   0.7456 | {"n_estimators": 100, "num_leaves": 16, "learning_rate": 0.010435008681262032, "min_child_samples": 27, "reg_lambda": 2.1722477273994953} |
| pos_similarity   |       0.5709 |   0.7302 | {"k": 39, "weight_power": 0.8489644825709736, "mvp1_emphasis": 0.9286308759985785}                                                        |

- **winner:** `pos_ridge` · beats null: **True** (Δ top-tier ρ +0.0988)
- **deflation** (127 configs): PBO 0.3429 (spread 0.1747) · DSR 0.6827 · p 0.0047 · FDR pass True
- **verdict:** NULL — MVP-1 stands (pbo_ok, dsr_ok)

**Feature ablation on the winner (drop-one group; negative Δ = the group carries signal):**

| drop   |   mean_top |   delta |
|:-------|-----------:|--------:|
| usage  |     0.5962 | -0.0121 |
| mover  |     0.6006 | -0.0077 |
| env    |     0.6097 |  0.0014 |
| injury |     0.6052 | -0.0031 |
| age    |     0.5669 | -0.0414 |
| role   |     0.5895 | -0.0188 |
| xfp    |     0.5896 | -0.0187 |

## WR

| candidate        |   top-tier ρ |   full ρ | hp                                                                                                                                        |
|:-----------------|-------------:|---------:|:------------------------------------------------------------------------------------------------------------------------------------------|
| pos_null (MVP-1) |       0.4113 |   0.7503 |                                                                                                                                           |
| pos_ridge ⭐     |       0.5421 |   0.7733 | {"alpha": 1.380137655222368}                                                                                                              |
| pos_gbm          |       0.5334 |   0.7595 | {"n_estimators": 300, "num_leaves": 20, "learning_rate": 0.022389269739651246, "min_child_samples": 15, "reg_lambda": 19.243355452298985} |
| pos_similarity   |       0.5267 |   0.7542 | {"k": 43, "weight_power": 2.4251381241153758, "mvp1_emphasis": 0.8221692076762326}                                                        |

- **winner:** `pos_ridge` · beats null: **True** (Δ top-tier ρ +0.1308)
- **deflation** (127 configs): PBO 0.4857 (spread 0.0863) · DSR 0.8650 · p 0.0053 · FDR pass True
- **verdict:** NULL — MVP-1 stands (pbo_ok, dsr_ok)

**Feature ablation on the winner (drop-one group; negative Δ = the group carries signal):**

| drop   |   mean_top |   delta |
|:-------|-----------:|--------:|
| usage  |     0.5406 | -0.0015 |
| mover  |     0.5407 | -0.0014 |
| env    |     0.5382 | -0.0039 |
| injury |     0.539  | -0.0031 |
| age    |     0.4649 | -0.0772 |
| role   |     0.5336 | -0.0085 |
| xfp    |     0.5511 |  0.009  |

## TE

| candidate         |   top-tier ρ |   full ρ | hp                                                                                                                                      |
|:------------------|-------------:|---------:|:----------------------------------------------------------------------------------------------------------------------------------------|
| pos_null (MVP-1)  |       0.4307 |   0.7398 |                                                                                                                                         |
| pos_ridge         |       0.4657 |   0.7511 | {"alpha": 7.840288575687636}                                                                                                            |
| pos_gbm           |       0.4152 |   0.7236 | {"n_estimators": 200, "num_leaves": 13, "learning_rate": 0.015542496811557178, "min_child_samples": 7, "reg_lambda": 6.469595821576644} |
| pos_similarity ⭐ |       0.4994 |   0.745  | {"k": 35, "weight_power": 2.638285885412706, "mvp1_emphasis": 3.030090628490117}                                                        |

- **winner:** `pos_similarity` · beats null: **True** (Δ top-tier ρ +0.0687)
- **deflation** (127 configs): PBO 0.3429 (spread 0.2132) · DSR 0.1993 · p 0.0344 · FDR pass True
- **verdict:** NULL — MVP-1 stands (pbo_ok, dsr_ok)

**Feature ablation on the winner (drop-one group; negative Δ = the group carries signal):**

| drop   |   mean_top |   delta |
|:-------|-----------:|--------:|
| usage  |     0.4959 | -0.0035 |
| mover  |     0.4897 | -0.0097 |
| env    |     0.4837 | -0.0157 |
| injury |     0.495  | -0.0044 |
| age    |     0.4594 | -0.04   |
| role   |     0.4877 | -0.0117 |
| xfp    |     0.4766 | -0.0228 |

## Verdict

- positions beating the MVP-1 null on the top-tier metric: **['QB', 'RB', 'WR', 'TE']**
- positions passing the FULL deflation gate (repoint-eligible): **none**

### Reading the deflation honestly (the §0.5 PBO discriminators)

- **QB is a genuine null** — the +0.052 is sign-INCONSISTENT across seasons (+0.24, +0.10, −0.01,
  +0.05, −0.13, −0.09, +0.21), PBO 0.83 over a real 0.178 spread (instability, NOT a tied field),
  DSR 0.03, p 0.19, FDR fail. The story's warning holds: **top-tier QB is structurally the market
  signal a market-blind model excludes.**
- **RB/WR/TE beat the null with consistent sign** (RB positive in 7/7 seasons p=0.0047; WR 6/7
  p=0.0053, DSR 0.865 — the closest miss; TE 5/7 p=0.034, the SIMILARITY learner's one win) and all
  pass FDR — but none clears PBO<0.2 ∧ DSR≥0.95, so under the pre-registered serving rule **no
  position repoints**.
- **Feature ablation:** `age` is the biggest carrier at RB/WR/TE (−0.04…−0.08 when dropped); the
  **NF-D7 xFP features carry learned signal at QB/RB/TE** (−0.019…−0.026) but not WR (+0.009) —
  the NF1.1-owned open question answers "yes, modestly, except WR."

## Product-metric verdict (grade, 2019–2024, beats-null board QB=gbm/RB=ridge/WR=ridge/TE=similarity)

**FINAL: NULL — the MVP-1 incumbent STANDS as the served board.** Same scorer, same seasons, same
universes as the stored MVP-1 / NF1 scorecards (`nf1_1_vs_consensus_scorecard.json`):

| vs system | MVP-1 Δρ | NF1(pooled) Δρ | **NF1.1 Δρ** | NF1.1 by pos (QB/RB/WR/TE) |
|-----------|---------:|---------------:|-------------:|:---------------------------|
| adp | −0.060 | −0.031 | **−0.020** ✅ best | −0.143 / **−0.024** / +0.006 / **+0.078** |
| ecr | −0.060 | −0.074 | −0.081 | −0.144 / −0.069 / −0.050 / −0.059 |
| espn | −0.059 | −0.079 | −0.082 | −0.071 / −0.082 / −0.109 / −0.068 |
| sleeper | −0.136 | −0.157 | **−0.164** | −0.223 / −0.160 / −0.147 / −0.126 |

- **Where NF1.1 improves:** the ADP head-to-head is the best of our three systems (−0.020 pooled;
  RB −0.024 vs MVP-1's −0.101 is a real RB repair; TE +0.078 now BEATS ADP), and the **ADP fade
  edge improves again — 0.543 vs 0.274** (MVP-1: 0.478 vs 0.247; NF1: 0.540 vs 0.313). The narrow
  public claim gets slightly stronger: *where we most disagree with ADP, our picks out-predict the
  market.*
- **Where it doesn't:** the deep-coverage systems (ECR/ESPN/Sleeper) still out-order every
  market-blind variant we've built, and QB loses everywhere. Two independent market-blind passes —
  NF1's pooled learner and NF1.1's per-position learners — now bracket the approach: the
  within-our-own-holdout top-tier lift (+0.05…+0.13) does NOT translate into beating the consensus
  on their shared universe. **The market-blind ceiling is established; the remaining lever for the
  QB/deep-system tier is the MARKET-AWARE variant (ADP/ECR as position-conditional features) — a
  deliberate operator product/identity decision, not a modeling gap.**
- **Disposition:** no `build --s3` (the deflation gate + product grade agree: no repoint). NF1.1
  stands as the research record: the per-position machinery, the similarity learner (TE's winner),
  the top-tier selection harness, and the deflation kit are the reusable substrate for any
  market-aware follow-up. `best_alpha = 0`.

