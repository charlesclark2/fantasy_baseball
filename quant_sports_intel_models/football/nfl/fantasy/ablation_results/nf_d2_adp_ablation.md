# NF-D2 #6 / NF-D3 — ADP MARKET CONSENSUS (prior + benchmark)

**Generated:** 2026-07-26T07:19:00.646993+00:00 · **seasons:** 2019–2024 (each projected off its own season−1; 2025 absent from FFC) · **baseline:** the SHIPPED model (slices 1/3/4/5 on)

> ADP = Fantasy Football Calculator real-draft consensus, snapshotted the week before Week 1 ⇒ LEAKAGE-SAFE. Every `model*` arm is the shipped `project_veterans` path; the ADP blend is a within-position quantile remap (`blend_adp_prior`, preserves each position's point multiset). **ADP ships OFF (`_ADP_PRIOR_BLEND=0.0`)** — the projection is a non-market product whose edge is the disagreements; this table sizes the ρ-lift-vs-independence tradeoff.

## 1. Within-position ρ — FULL scored set (does ADP lift the board?)

| arm | QB | RB | WR | TE |
|-----|----|----|----|----|
| model_only | 0.702 | 0.738 | 0.767 | 0.741 |
| model+adp@0.25 | 0.704 | 0.743 | 0.760 | 0.730 |
| model+adp@0.50 | 0.684 | 0.723 | 0.727 | 0.703 |
| model+adp@0.75 | 0.658 | 0.672 | 0.651 | 0.636 |
| model+adp@QBRB | 0.674 | 0.706 | 0.767 | 0.741 |
| adp_only | 0.476 | 0.623 | 0.560 | 0.356 |

## 2. NF-D3 BENCHMARK — ADP-covered subset only (does our model add BEYOND consensus?)

Same players for every arm (only those with an ADP), so `adp_only` is a fair yardstick.

| arm | QB | RB | WR | TE |
|-----|----|----|----|----|
| model_only | 0.327 | 0.521 | 0.570 | 0.356 |
| model+adp@0.25 | 0.374 | 0.577 | 0.600 | 0.367 |
| model+adp@0.50 | 0.420 | 0.610 | 0.618 | 0.345 |
| model+adp@0.75 | 0.459 | 0.627 | 0.591 | 0.350 |
| model+adp@QBRB | 0.440 | 0.619 | 0.570 | 0.356 |
| adp_only | 0.476 | 0.623 | 0.560 | 0.356 |

## 3. DISAGREEMENT — when the model fades ADP, who is right?

Among the top-quartile most model-vs-ADP-divergent player-seasons (n=213), within-position-pooled Spearman vs the realized finish:

- **overall** — model **0.505** vs ADP **0.283**

| position | model | ADP | n |
|----------|-------|-----|---|
| QB | -0.043 | 0.377 | 42 |
| RB | 0.275 | 0.573 | 61 |
| WR | 0.436 | 0.382 | 82 |
| TE | 0.311 | 0.054 | 28 |

## Reading it — a clean POSITION SPLIT, not a single verdict

- **A global ADP blend is a NULL / net-negative on the board (§1).** ADP covers only ~37% of the scored universe (the draftable top tier); blending it in disturbs the ordering of covered vs uncovered players and every `model+adp@w` arm is flat-to-down on the full set. An ADP prior only makes sense WITHIN the ADP-covered draftable tier (§2) — which is exactly the draft-board use case.
- **QB & RB — the MARKET out-orders us; a narrow prior is justified.** On the covered tier ADP beats the model at QB (**0.476 vs 0.327**) and RB (**0.623 vs 0.522**), and on the top-quartile FADES (§3) the model is *noise* at QB (**−0.04 vs ADP 0.38**) and loses at RB (**0.28 vs 0.57**). A box-score line structurally misses what drives QB/RB fantasy order — scheme, rushing role, offensive environment, committee splits — which ADP prices. The `model+adp@QBRB` arm lifts the covered tier **QB +0.11, RB +0.10** toward ADP while leaving WR/TE untouched.
- **WR & TE — OUR MODEL wins; keep it independent (do NOT blend).** The model ties/beats ADP on the covered tier (WR **0.570 vs 0.560**; TE **0.356 vs 0.357**), and on the FADES it beats ADP decisively (WR **0.436 vs 0.382**; TE **0.311 vs 0.054**). This is precisely the within-tier ordering edge NF-D2 exists to build — a blanket ADP blend would ERASE it. (At WR a mid blend even beats *both* model and ADP — real orthogonal value on top of consensus.)
- **Ship decision:** `_ADP_PRIOR_BLEND = 0.0` (OFF) — the projection stays a non-market, independent product; its WR/TE edge and its overall fade-edge (**model 0.51 vs ADP 0.28**) are the reason. ADP is delivered as **(a) the NF-D3 benchmark** and **(b) an OPTIONAL, evidence-backed QB/RB-scoped prior** (`blend_adp_prior(..., positions=('QB','RB'))`, applied within the covered tier) that the operator can flip on as a product/market call — it trades QB/RB independence for market parity where we have no edge anyway.

