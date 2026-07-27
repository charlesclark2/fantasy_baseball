# NF1.2 — projection-refinement families (SOS / system / corr / O-line-cap / opportunity / spillover / contract), market-blind

**Model:** `nfl_fantasy_nf1_2_v1` · **generated:** 2026-07-27T07:42:41.680208+00:00 · **base seasons:** 2017–2024 · **scored targets:** [2019, 2020, 2021, 2022, 2023, 2024, 2025] · **pool:** 2995 · **Optuna trials/class:** 40

> **Selection metric:** top-tier within-position ρ (tier = top-N by the MVP-1 incumbent, N={'QB': 24, 'RB': 36, 'WR': 48, 'TE': 24}) — incumbent-anchored, oracle-checked. Candidates per position: pos_ridge / pos_gbm / pos_similarity on the FULL extended set vs the MVP-1 null, + attribution arms (NF1.1-baseline / add-one-family / drop-one-group) — every config deflated. Gates: PBO<0.2 · DSR≥0.95 · BH-FDR q=0.1. MARKET-BLIND — the honest win condition is WR/TE + the fade universe (NF1.3's market-aware board owns QB/RB product ordering). `best_alpha = 0`.

- **oracle metric sane:** True
- **probed-unavailable (honest gaps):** {'yprr': 'routes-run not in any free nflverse table (PFF-gated)', 'catchable_rate': 'catchable-target flag not available'}

**Family registration + pool coverage (non-null share):**

| family   | columns                                                                          | positions   | coverage                                                                                               |
|:---------|:---------------------------------------------------------------------------------|:------------|:-------------------------------------------------------------------------------------------------------|
| sos      | sos_pass_strength, sos_rush_strength                                             | QB/RB/WR/TE | sos_pass_strength=1.0, sos_rush_strength=1.0                                                           |
| system   | team_pass_rate, team_pace, pass_rate_delta                                       | QB/RB/WR/TE | team_pass_rate=0.644, team_pace=0.644, pass_rate_delta=0.644                                           |
| qbcorr   | team_qb_quality                                                                  | WR/TE       | team_qb_quality=0.959                                                                                  |
| oline    | team_ol_cap_pct                                                                  | QB/RB       | team_ol_cap_pct=1.0                                                                                    |
| contract | log_investment, guaranteed_ratio, cap_hit_pct_team, team_skill_cap_concentration | QB/RB/WR/TE | log_investment=0.988, guaranteed_ratio=0.988, cap_hit_pct_team=0.988, team_skill_cap_concentration=1.0 |
| opp      | air_yards_share, wopr                                                            | RB/WR/TE    | air_yards_share=1.0, wopr=1.0                                                                          |
| spill    | teammate_fp, vacated_volume                                                      | QB/RB/WR/TE | teammate_fp=1.0, vacated_volume=1.0                                                                    |

## QB

| candidate                      |   top-tier ρ |   full ρ | hp                                                                                                                                        |
|:-------------------------------|-------------:|---------:|:------------------------------------------------------------------------------------------------------------------------------------------|
| pos_null (MVP-1)               |       0.3681 |   0.6485 |                                                                                                                                           |
| pos_ridge ⭐                   |       0.4127 |   0.6386 | {"alpha": 1.1138931477414304}                                                                                                             |
| pos_gbm                        |       0.391  |   0.6428 | {"n_estimators": 450, "num_leaves": 14, "learning_rate": 0.016633389591414596, "min_child_samples": 16, "reg_lambda": 13.729444426655268} |
| pos_similarity                 |       0.4046 |   0.6598 | {"k": 23, "weight_power": 1.8473283985738926, "mvp1_emphasis": 3.2346134540252645}                                                        |
| winner class on NF1.1 BASE set |       0.3973 |   0.6599 | (attribution arm)                                                                                                                         |

- **winner:** `pos_ridge` · beats MVP-1 null: **True** (Δ +0.0446) · beats NF1.1-baseline arm: **True** (families' joint Δ +0.0154)
- **deflation** (138 configs): PBO 0.6857 (spread 0.1688) · DSR 0.1561 · p 0.2336 · FDR pass False
- **verdict:** NULL — MVP-1 stands (pbo_ok, dsr_ok, fdr_ok)

**Add-one family (base + family; Δ vs the NF1.1-baseline arm — isolated lift):**

| family   |   mean_top |   delta_vs_baseline |
|:---------|-----------:|--------------------:|
| sos      |     0.3691 |             -0.0282 |
| system   |     0.3535 |             -0.0438 |
| oline    |     0.3743 |             -0.023  |
| contract |     0.3855 |             -0.0118 |
| spill    |     0.3887 |             -0.0086 |

**Drop-one group on the winner (negative Δ = the group carries signal):**

| drop     |   mean_top |   delta |
|:---------|-----------:|--------:|
| usage    |     0.3866 | -0.0261 |
| mover    |     0.4127 |  0      |
| env      |     0.4093 | -0.0034 |
| injury   |     0.3912 | -0.0215 |
| age      |     0.3968 | -0.0159 |
| role     |     0.3935 | -0.0192 |
| xfp      |     0.4099 | -0.0028 |
| sos      |     0.3587 | -0.054  |
| system   |     0.4303 |  0.0176 |
| oline    |     0.3942 | -0.0185 |
| contract |     0.3727 | -0.04   |
| spill    |     0.3687 | -0.044  |

## RB

| candidate                      |   top-tier ρ |   full ρ | hp                                                                                                                                      |
|:-------------------------------|-------------:|---------:|:----------------------------------------------------------------------------------------------------------------------------------------|
| pos_null (MVP-1)               |       0.5095 |   0.7341 |                                                                                                                                         |
| pos_ridge                      |       0.5736 |   0.7437 | {"alpha": 128.29965923732277}                                                                                                           |
| pos_gbm ⭐                     |       0.5812 |   0.7546 | {"n_estimators": 250, "num_leaves": 17, "learning_rate": 0.02041894478474734, "min_child_samples": 17, "reg_lambda": 19.52172379005253} |
| pos_similarity                 |       0.5582 |   0.7299 | {"k": 36, "weight_power": 2.1041438996968846, "mvp1_emphasis": 2.435239025190187}                                                       |
| winner class on NF1.1 BASE set |       0.555  |   0.7377 | (attribution arm)                                                                                                                       |

- **winner:** `pos_gbm` · beats MVP-1 null: **True** (Δ +0.0717) · beats NF1.1-baseline arm: **True** (families' joint Δ +0.0262)
- **deflation** (140 configs): PBO 0.7429 (spread 0.1174) · DSR 0.5001 · p 0.0726 · FDR pass True
- **verdict:** NULL — MVP-1 stands (pbo_ok, dsr_ok)

**Add-one family (base + family; Δ vs the NF1.1-baseline arm — isolated lift):**

| family   |   mean_top |   delta_vs_baseline |
|:---------|-----------:|--------------------:|
| sos      |     0.5559 |              0.0009 |
| system   |     0.553  |             -0.002  |
| oline    |     0.5556 |              0.0006 |
| contract |     0.5763 |              0.0213 |
| opp      |     0.5526 |             -0.0024 |
| spill    |     0.5647 |              0.0097 |

**Drop-one group on the winner (negative Δ = the group carries signal):**

| drop     |   mean_top |   delta |
|:---------|-----------:|--------:|
| usage    |     0.5784 | -0.0028 |
| mover    |     0.5703 | -0.0109 |
| env      |     0.5772 | -0.004  |
| injury   |     0.5771 | -0.0041 |
| age      |     0.5216 | -0.0596 |
| role     |     0.5708 | -0.0104 |
| xfp      |     0.5727 | -0.0085 |
| sos      |     0.5775 | -0.0037 |
| system   |     0.5747 | -0.0065 |
| oline    |     0.5796 | -0.0016 |
| contract |     0.5517 | -0.0295 |
| opp      |     0.5778 | -0.0034 |
| spill    |     0.5651 | -0.0161 |

## WR

| candidate                      |   top-tier ρ |   full ρ | hp                                                                                                                                        |
|:-------------------------------|-------------:|---------:|:------------------------------------------------------------------------------------------------------------------------------------------|
| pos_null (MVP-1)               |       0.4113 |   0.7503 |                                                                                                                                           |
| pos_ridge ⭐                   |       0.5322 |   0.7748 | {"alpha": 4.932082324144322}                                                                                                              |
| pos_gbm                        |       0.5313 |   0.7794 | {"n_estimators": 350, "num_leaves": 13, "learning_rate": 0.012176643976524633, "min_child_samples": 23, "reg_lambda": 1.2754665799774776} |
| pos_similarity                 |       0.5266 |   0.7538 | {"k": 36, "weight_power": 2.9711788657247435, "mvp1_emphasis": 2.0121924044847295}                                                        |
| winner class on NF1.1 BASE set |       0.5513 |   0.7763 | (attribution arm)                                                                                                                         |

- **winner:** `pos_ridge` · beats MVP-1 null: **True** (Δ +0.1209) · beats NF1.1-baseline arm: **False** (families' joint Δ -0.0191)
- **deflation** (139 configs): PBO 0.5429 (spread 0.0983) · DSR 0.5745 · p 0.0076 · FDR pass True
- **verdict:** NULL — MVP-1 stands (pbo_ok, dsr_ok)

**Add-one family (base + family; Δ vs the NF1.1-baseline arm — isolated lift):**

| family   |   mean_top |   delta_vs_baseline |
|:---------|-----------:|--------------------:|
| sos      |     0.5525 |              0.0012 |
| system   |     0.5441 |             -0.0072 |
| qbcorr   |     0.5508 |             -0.0005 |
| contract |     0.5423 |             -0.009  |
| opp      |     0.5475 |             -0.0038 |
| spill    |     0.5527 |              0.0014 |

**Drop-one group on the winner (negative Δ = the group carries signal):**

| drop     |   mean_top |   delta |
|:---------|-----------:|--------:|
| usage    |     0.5274 | -0.0048 |
| mover    |     0.532  | -0.0002 |
| env      |     0.5271 | -0.0051 |
| injury   |     0.5315 | -0.0007 |
| age      |     0.4697 | -0.0625 |
| role     |     0.5277 | -0.0045 |
| sos      |     0.5316 | -0.0006 |
| system   |     0.5363 |  0.0041 |
| qbcorr   |     0.5302 | -0.002  |
| contract |     0.545  |  0.0128 |
| opp      |     0.5296 | -0.0026 |
| spill    |     0.5355 |  0.0033 |

## TE

| candidate                      |   top-tier ρ |   full ρ | hp                                                                                                                                       |
|:-------------------------------|-------------:|---------:|:-----------------------------------------------------------------------------------------------------------------------------------------|
| pos_null (MVP-1)               |       0.4307 |   0.7398 |                                                                                                                                          |
| pos_ridge                      |       0.4542 |   0.7221 | {"alpha": 2.614430851062619}                                                                                                             |
| pos_gbm                        |       0.4496 |   0.741  | {"n_estimators": 350, "num_leaves": 13, "learning_rate": 0.011108204303911308, "min_child_samples": 5, "reg_lambda": 0.6480201271047638} |
| pos_similarity ⭐              |       0.4979 |   0.7417 | {"k": 21, "weight_power": 2.6585914133120587, "mvp1_emphasis": 3.9616124363501117}                                                       |
| winner class on NF1.1 BASE set |       0.4684 |   0.7421 | (attribution arm)                                                                                                                        |

- **winner:** `pos_similarity` · beats MVP-1 null: **True** (Δ +0.0672) · beats NF1.1-baseline arm: **True** (families' joint Δ +0.0295)
- **deflation** (140 configs): PBO 0.1429 (spread 0.3180) · DSR 0.2435 · p 0.0197 · FDR pass True
- **verdict:** NULL — MVP-1 stands (dsr_ok)

**Add-one family (base + family; Δ vs the NF1.1-baseline arm — isolated lift):**

| family   |   mean_top |   delta_vs_baseline |
|:---------|-----------:|--------------------:|
| sos      |     0.5116 |              0.0432 |
| system   |     0.5081 |              0.0397 |
| qbcorr   |     0.4871 |              0.0187 |
| contract |     0.4591 |             -0.0093 |
| opp      |     0.486  |              0.0176 |
| spill    |     0.4899 |              0.0215 |

**Drop-one group on the winner (negative Δ = the group carries signal):**

| drop     |   mean_top |   delta |
|:---------|-----------:|--------:|
| usage    |     0.4901 | -0.0078 |
| mover    |     0.4871 | -0.0108 |
| env      |     0.482  | -0.0159 |
| injury   |     0.4911 | -0.0068 |
| age      |     0.4646 | -0.0333 |
| role     |     0.4852 | -0.0127 |
| xfp      |     0.5278 |  0.0299 |
| sos      |     0.4867 | -0.0112 |
| system   |     0.4553 | -0.0426 |
| qbcorr   |     0.4857 | -0.0122 |
| contract |     0.5417 |  0.0438 |
| opp      |     0.4911 | -0.0068 |
| spill    |     0.454  | -0.0439 |

## Verdict

- positions beating the MVP-1 null on the top-tier metric: **['QB', 'RB', 'WR', 'TE']**
- positions passing the FULL deflation gate (repoint-eligible): **none**
- honest frame: NF1.2 is market-BLIND — it gates against the market-blind baseline (the fade board). A QB/RB win would additionally have to beat the NF1.3 market-aware board to change the served product there; WR/TE + fades are the honest win condition.


## Reading (session 2026-07-27) — the per-family verdict

**Headline: NULL — no position survives the deflation gate; MVP-1 stands as the market-blind
(fade-claim) board and the NF1.3 dual-board keeps QB/RB product ordering. Every family is now
TESTED, not merely untried.** Per-family attribution (add-one Δ vs the NF1.1-baseline arm; the
drop-one confirms from the other side):

- **H-CONTRACT** — the ONLY family with a positive isolated lift at RB (+0.0213 add-one;
  −0.0295 drop-one), consistent with the "revealed team belief" hypothesis living mostly in RB
  contracts. At WR it is a mild NEGATIVE (−0.009 add-one; dropping it HELPS +0.0128) — the $
  signal is position-conditional, not universal.
- **TE is the near-miss position**: the ONLY position passing PBO (0.1429 < 0.2), with a wide
  supporting cluster — add-one sos +0.0432, system +0.0397, spill +0.0215, qbcorr +0.0187,
  opp +0.0176 — and the drop-one agrees (spill −0.0439, system −0.0426). But DSR 0.24 fails:
  a +0.03 mean lift over 7 seasons is too noisy vs a 140-trial search to claim as real. The
  environment-cluster-at-TE hypothesis is the one thing a future story might re-test on more
  seasons; it does NOT repoint anything today.
- **H-SOS / H-SYSTEM / H-CORR / H-OLINE / H-OPP / H-SPILL at QB/RB/WR** — nulls. At QB every
  add-one is negative (the full-set win over the null is the tuned-search artifact the
  deflation exists to catch — PBO 0.69). At WR the extended set is a net DRAG (joint
  Δ −0.0191 vs the NF1.1 base arm): on the honest win-condition position, the refinement set
  cleanly fails.
- **§0.5 PBO reading**: the QB/RB/WR high PBOs come with moderate spreads (0.10–0.17) that are
  inflated by the deliberately-crippled ablation arms in the trial population; the top of the
  field is tight → read as "no candidate robustly separates," not as a wide-spread overfit.
  Oracle-ceiling check passed (metric sane).
- **Honest gaps recorded**: YPRR + catchable-target-rate probed UNAVAILABLE (routes-run/
  catchable flags are PFF-gated, in no free nflverse table we ingest); contract rookie rows may
  lag the nflverse refresh; `team_total_cap` is a proxy denominator; the `system` family's
  coverage floor is 2020 (team-rate rollup start). Contract join coverage on the pool: 98.8%
  (the played_flag-filtered read, per NF-D8's lesson).

**Serving consequence: none.** No repoint; the NF1.2 board is NOT built/landed. The candidate
machinery (`nf1_2_model.py` / `run_nf1_2.py`) stays as the harness for any future re-test
(e.g. TE environment cluster with more target seasons).
