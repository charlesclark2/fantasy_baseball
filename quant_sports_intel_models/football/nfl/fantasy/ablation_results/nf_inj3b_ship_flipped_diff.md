# NF-INJ3b-SHIP node 4 — the FLIPPED rebuild, diffed

_generated 2026-08-25T02:56:55.061571+00:00_ · season 2026 · `best_alpha = 0` · **DRY RUN — nothing published** · `SERVING_ENABLED` on disk = **True**

This builds the board the operator would publish — the flip **as committed**, the covariate feed **as the board build derives it for itself**, nothing forced in memory and nothing hand-supplied. NF-INJ3b-M could not do that (neither existed), so this is the first measurement of the real serving path.

## 1. The D6 stamp guard, on the board that would publish

**FLIPPED_AND_MOVED** — 22 of 22 fitted row(s) differ materially from the incumbent cap (largest move 4 games) under the fitted stamp nfl_fantasy_nf_inj3b_injury_games_v1.

certified rows 22 · produced by the fitted arm 22 · materially moved 22 · largest move 4 games

## 2. The noise floor and the same-commit control

| quantity | rows differing | max abs | p99 abs |
|---|---|---|---|
| `proj_games` (same-commit replicate) | 9 | 1.78e-15 | 8.88e-16 |
| `proj_fp_ppr` (same-commit replicate) | 131 | 2.27e-13 | 8.53e-14 |

Replicate overall-rank order identical: **True**.

### Rookie-band motion, read against the control FIRST

NF-INJ3c §6 (card QkpAHBYa): same-commit rebuilds differ in the rookie band at 0–21 material cells, so a rookie-band move is read against SAME-COMMIT controls before it is attributed to this change. ⛔ Never bitwise, and ⛔ never against a SINGLE control draw — the rule states a RANGE, so one draw that moves nothing cannot establish that a column is deterministic.

Controls drawn: **5** — an envelope, not one draw.

| column | moved (flipped) | moved (control range) | max abs (flipped) | max abs (control range) | attributable to the flip |
|---|---|---|---|---|---|
| `fp_ppr_sd` | 8 | 11–12 | 2.00e-02 | 3.00e-02–7.00e-02 | **False** |
| `fp_ppr_p10` | 0 | 0–4 | 0.00e+00 | 0.00e+00–1.00e-01 | **False** |
| `fp_ppr_p90` | 3 | 6–11 | 1.00e-01 | 1.00e-01–1.00e-01 | **False** |

every observed move on both sides is one unit of the column's own display rounding (0.01 on `fp_ppr_sd`, 0.1 on `fp_ppr_p10`/`p90`) — the documented signature of the build's non-determinism, not of a model change.

Any rookie-band move attributable to this change: **False**. structurally: the formal cap runs INSIDE `project_veterans`, and `project_rookies` is a separate frame concatenated afterwards which routes the INCUMBENT constants (NF-INJ3c AC-1). So any rookie motion here is the build's own noise, and the envelope is what MEASURES that rather than asserting it from this sentence.

## 3. The population-scoped material diff

rtol = atol = 1e-09, **never bitwise**.

| population | n | cells moved (flipped) | cells moved (control) |
|---|---|---|---|
| `rookie` | 81 | 11 | 23 |
| `veteran_fitted` | 22 | 121 | 0 |
| `veteran_other` | 691 | 1626 | 0 |

## 4. The served-POINT impact, and the sanity anchor

**22 rows served by the fitted arm** of 794 board rows.

| | flagged | unflagged |
|---|---|---|
| mean Δ `proj_games` | **-2.610** | — |
| mean Δ `pts` (PPR) | **-1.351** | — |
| points down / up | 19 / 3 | 340 changed |
| rank moves | 19 | 519 |

### Sanity anchor vs NF-INJ3b-M: **REPRODUCES**

NF-INJ3b-M measured the served impact by forcing the policy on IN MEMORY with a hand-supplied feed. This run measures the COMMITTED flip with the feed the board build derives for itself. The two differ in TWO known, intended ways — the returner boundary (4 flagged returners now hold the incumbent) and a feed built over the whole board rather than the study's 22 rows — so an exact match would be the surprising result. What this catches is an order-of-magnitude divergence.

| quantity | NF-INJ3b-M | this run | deviation | tolerance |
|---|---|---|---|---|
| `mean_d_proj_games` | -2.6104 | -2.6104 | +0.0000 | ±0.75 |
| `mean_d_pts_ppr` | -1.2341 | -1.3509 | -0.1168 | ±0.75 |

The committed flip reproduces the measurement the operator accepted.

## 5. Per-config placement — all 14 published configs

| config | rank moves | max \|move\| | top-60 moved | within-pos order | rookie cap |
|---|---|---|---|---|---|
| `standard_10` | 484/794 | 57 | 0 | False | True |
| `standard_12` | 507/794 | 106 | 0 | False | True |
| `standard_3wr_10` | 460/794 | 99 | 0 | False | True |
| `standard_3wr_12` | 508/794 | 118 | 0 | False | True |
| `half_ppr_10` | 480/794 | 48 | 0 | False | True |
| `half_ppr_12` | 515/794 | 72 | 0 | False | True |
| `half_ppr_3wr_10` | 499/794 | 95 | 0 | False | True |
| `half_ppr_3wr_12` | 518/794 | 86 | 0 | False | True |
| `full_ppr_10` | 488/794 | 60 | 0 | False | True |
| `full_ppr_12` | 481/794 | 103 | 0 | False | True |
| `full_ppr_3wr_10` | 497/794 | 94 | 0 | False | True |
| `full_ppr_3wr_12` | 521/794 | 78 | 0 | False | True |
| `superflex_10` ⭐SF | 491/794 | 62 | 0 | False | True |
| `superflex_12` ⭐SF | 508/794 | 105 | 0 | False | True |

⚠️ `within-pos order` is **False at RB/TE/WR on every config, and that is the measured, expected consequence of the flip** — NF1.5 re-assigns each position's POINT MULTISET in learned-rank order, so moving a flagged veteran's games moves which player gets which level. NF-INJ3b-M measured exactly the same. It is NOT a regression introduced here, and it is the mis-specification NF-INJ2b owns.

## 6. The FLAGGED COHORT — every row the fitted arm served

| player | pos | games inc→flip | Δgames | pts inc→flip | Δpts | rank inc→flip |
|---|---|---|---|---|---|---|
| ISAAC GUERENDO | RB | 5.19 → 2.05 | **-3.14** | 37.6 → 28.6 | **-9.0** | 348 → 430 |
| NIKOLA KALINIC | TE | 4.24 → 1.06 | **-3.18** | 9.7 → 5.2 | **-4.5** | 736 → 782 |
| RICKY PEARSALL | WR | 5.65 → 4.01 | **-1.64** | 45.0 → 42.5 | **-2.6** | 298 → 311 |
| TIP REIMAN | TE | 5.00 → 2.62 | **-2.38** | 18.0 → 15.8 | **-2.2** | 547 → 600 |
| JAYDEN HIGGINS | WR | 6.66 → 4.09 | **-2.56** | 101.1 → 99.1 | **-1.9** | 154 → 155 |
| PRINCETON FANT | TE | 3.90 → 1.27 | **-2.63** | 11.0 → 9.4 | **-1.7** | 703 → 734 |
| TREY SERMON | RB | 4.14 → 1.37 | **-2.78** | 17.9 → 16.4 | **-1.5** | 551 → 589 |
| JULIAN HILL | TE | 5.40 → 3.03 | **-2.38** | 20.9 → 19.5 | **-1.4** | 499 → 519 |
| JUSTIN SHORTER | WR | 4.22 → 1.61 | **-2.61** | 8.5 → 7.3 | **-1.1** | 758 → 763 |
| JAMARI THRASH | WR | 4.84 → 3.70 | **-1.14** | 6.7 → 5.7 | **-1.0** | 776 → 777 |
| BRENDEN BATES | TE | 4.80 → 2.13 | **-2.67** | 10.9 → 10.0 | **-0.9** | 707 → 723 |
| QUENTIN SKINNER | WR | 4.16 → 1.46 | **-2.70** | 13.7 → 13.1 | **-0.6** | 653 → 655 |
| ROBBIE OUZTS | FB | 5.41 → 1.41 | **-4.00** | 0.5 → 0.1 | **-0.4** | 794 → 794 |
| GUNNER OLSZEWSKI | WR | 5.19 → 3.25 | **-1.93** | 11.1 → 10.8 | **-0.4** | 699 → 702 |
| DAN CHISENA | WR | 3.02 → 1.24 | **-1.78** | 11.0 → 10.7 | **-0.3** | 704 → 705 |
| MASON TIPTON | WR | 5.42 → 3.41 | **-2.00** | 15.2 → 15.0 | **-0.2** | 616 → 614 |
| TYRELL SHAVERS | WR | 5.71 → 3.16 | **-2.56** | 19.1 → 19.0 | **-0.1** | 529 → 527 |
| JEROME FORD | RB | 5.40 → 4.22 | **-1.18** | 37.1 → 37.1 | **-0.0** | 350 → 346 |
| GEORGE KITTLE | TE | 7.32 → 3.33 | **-3.98** | 112.3 → 112.3 | **-0.0** | 141 → 141 |
| ALEC PIERCE | WR | 7.35 → 3.66 | **-3.69** | 118.3 → 118.3 | **+0.0** | 131 → 131 |
| ZACH CHARBONNET | RB | 6.90 → 3.71 | **-3.19** | 83.1 → 83.1 | **+0.0** | 180 → 179 |
| LUKE MUSGRAVE | TE | 6.49 → 3.20 | **-3.30** | 27.7 → 27.7 | **+0.0** | 437 → 436 |

⚠️ Superflex is read on its OWN rows: NF-TR2b's VOR shield is ADDITIVE-ONLY and assumes the group is not cross-pooled, and QB IS cross-pooled there.

## 7. NF-INJ1 coherence — does this flip widen the (games, stat-line) gap?

NF-INJ1: the served (games, stat-line) pair must be physically possible. NF1.5 rescales the line to a re-assigned POINT and leaves `proj_games` where the availability chain put it, so moving a flagged veteran's games without moving his point widens that gap. ALERT-tier on the published board by PM decision, never a HALT — but a change that moves the count owes the operator the number.

| board | violating players | rows in scope |
|---|---|---|
| incumbent | 9 | 777 |
| flipped | 12 | 777 |

Δ violating: **+3**. Newly violating and FLAGGED: ['ALEC PIERCE', 'GEORGE KITTLE', 'JAYDEN HIGGINS']. Newly violating and unflagged: none.

Owned by NF-INJ2b (the ordering-learner successor). ⛔ Nothing here touches NF1.5.

## 8. What is still the OPERATOR's

This is a DRY RUN. Nothing was published, no lake write, no `--publish` flag exists on this runner, and the D10 combined read gates the first publish. The ship/hold call is the operator's.
