# NF-D3 — competitor projection scorecard (us vs consensus)

**Generated:** 2026-07-26T21:01:28.095663+00:00 · **seasons scored:** 2019–2024 · **model:** the SHIPPED projection (slices 1/3/4/5 on), each season built from ≤season−1 data.

> ⚖️ **The honesty bar (this is a GTM proof asset — a cherry-picked claim backfires):** every system is graded on the SHARED universe of players it AND our model both cover with ≥6 realized games, PPR format held fixed, same realized truth. Ordering is measured by within-position Spearman ρ (what wins drafts) + rank-MAE (rank-space, so a RANKING system — ADP/ECR/Fantasy Footballers — grades identically to our point projection). Our projection is a genuine holdout (≤season−1 data); ADP/ECR are frozen PRESEASON snapshots. `+Δ` favours US.

## 1. Aggregate — us vs each system (averaged across the seasons each covers)

`ρ` = position-pooled within-tier Spearman vs realized (higher = better ordering). `Δρ`/`ΔrankMAE` = us − system (Δρ>0 and ΔrankMAE<0 favour us). `fade ρ` = when we most disagree with the system, who predicts the realized finish (the non-market edge).

| system | seasons | our ρ | their ρ | Δρ | Δrank-MAE | our fade ρ | their fade ρ |
|--------|--------:|------:|--------:|---:|---------:|-----------:|-------------:|
| adp | 6 | 0.444 | 0.504 | -0.060 | 0.59 | 0.478 | 0.247 |
| ecr | 6 | 0.692 | 0.753 | -0.060 | 1.35 | 0.701 | 0.746 |

### Δρ by position (us − system)

| system | QB | RB | WR | TE |
|--------|---:|---:|---:|---:|
| adp | -0.150 | -0.101 | 0.010 | -0.000 |
| ecr | -0.109 | -0.053 | -0.026 | -0.053 |

## 2. Per-season detail

### 2019 — scored universe n=342

| system | cover% | n_aligned | our ρ | their ρ | Δρ | our rank-MAE | their rank-MAE |
|--------|-------:|----------:|------:|--------:|---:|-------------:|---------------:|
| adp | 42.1 | 144 | 0.436 | 0.501 | -0.065 | 10.06 | 8.94 |
| ecr | 85.1 | 291 | 0.666 | 0.747 | -0.081 | 14.48 | 12.53 |

### 2020 — scored universe n=352

| system | cover% | n_aligned | our ρ | their ρ | Δρ | our rank-MAE | their rank-MAE |
|--------|-------:|----------:|------:|--------:|---:|-------------:|---------------:|
| adp | 39.2 | 138 | 0.400 | 0.526 | -0.126 | 8.91 | 7.75 |
| ecr | 84.7 | 298 | 0.633 | 0.707 | -0.074 | 15.13 | 14.33 |

### 2021 — scored universe n=386

| system | cover% | n_aligned | our ρ | their ρ | Δρ | our rank-MAE | their rank-MAE |
|--------|-------:|----------:|------:|--------:|---:|-------------:|---------------:|
| adp | 38.3 | 148 | 0.545 | 0.527 | 0.018 | 9.91 | 9.27 |
| ecr | 92.0 | 355 | 0.756 | 0.793 | -0.037 | 16.93 | 15.66 |

### 2022 — scored universe n=366

| system | cover% | n_aligned | our ρ | their ρ | Δρ | our rank-MAE | their rank-MAE |
|--------|-------:|----------:|------:|--------:|---:|-------------:|---------------:|
| adp | 33.3 | 122 | 0.386 | 0.453 | -0.067 | 7.97 | 8.11 |
| ecr | 85.8 | 314 | 0.681 | 0.735 | -0.054 | 15.39 | 14.43 |

### 2023 — scored universe n=366

| system | cover% | n_aligned | our ρ | their ρ | Δρ | our rank-MAE | their rank-MAE |
|--------|-------:|----------:|------:|--------:|---:|-------------:|---------------:|
| adp | 41.0 | 150 | 0.413 | 0.462 | -0.049 | 9.64 | 9.62 |
| ecr | 86.3 | 316 | 0.672 | 0.759 | -0.087 | 15.53 | 13.86 |

### 2024 — scored universe n=374

| system | cover% | n_aligned | our ρ | their ρ | Δρ | our rank-MAE | their rank-MAE |
|--------|-------:|----------:|------:|--------:|---:|-------------:|---------------:|
| adp | 40.1 | 150 | 0.481 | 0.554 | -0.073 | 10.51 | 9.75 |
| ecr | 94.9 | 355 | 0.746 | 0.776 | -0.030 | 16.67 | 15.22 |

## 3. Reading it — scope the claim to what is TRUE

- The **defensible public claim** is per-system, per-position, out-of-sample — read it straight off §1 (aggregate) and the Δρ-by-position table. A `+Δρ` averaged over multiple seasons at a position is a real, reproducible win; a negative one is a place we do NOT yet beat that system (say so — the honesty bar).
- ADP/ECR are RANKINGS; we grade them in rank-space (ρ + rank-MAE), never on a points-MAE they don't emit. A file benchmark (Fantasy Footballers / PFF / ESPN) is scored identically the moment its `<system>_<season>.csv` is dropped in — the scorecard is standing, not a one-off.
- Consistent with the NF-D2 #6 ADP finding: our edge is strongest at **WR/TE** and on our **high-conviction fades**; the market tends to out-order us at **QB/RB**. Scope every public statement to the position + the fades, not a blanket 'we beat the consensus'.

## 4. Forward view — 2026 (NO realized truth yet ⇒ AGREEMENT, not accuracy)

> ⚠️ There is no realized outcome for an in-progress season, so this section makes **NO 'we beat X' claim** — it only shows how aligned our board is with each system, and our most CONTRARIAN picks (draft content, not a proof point). The accuracy grade lands here automatically once the season completes and `build_scorecard` can score it vs realized.

| system | n_aligned | agreement ρ (pooled) | QB | RB | WR | TE |
|--------|----------:|---------------------:|---:|---:|---:|---:|
| adp | 164 | 0.746 | 0.586 | 0.890 | 0.849 | 0.658 |
| ecr | 360 | 0.855 | 0.841 | 0.870 | 0.870 | 0.838 |
| fantasy_footballers | 259 | 0.821 | 0.644 | 0.921 | 0.863 | 0.857 |

**Biggest disagreements vs adp** (our z − their z; +we higher):

| player | pos | direction | gap (z) |
|--------|-----|-----------|--------:|
| JOE BURROW | QB | we_lower | -2.35 |
| TUCKER KRAFT | TE | we_lower | -1.99 |
| JAYDEN DANIELS | QB | we_lower | -1.77 |
| COLSTON LOVELAND | TE | we_lower | -1.63 |
| LUTHER BURDEN III | WR | we_lower | -1.57 |
| BHAYSHUL TUTEN | RB | we_lower | -1.46 |
| COOPER KUPP | WR | we_higher | +1.39 |
| MALIK WILLIS | QB | we_lower | -1.35 |
| ALVIN KAMARA | RB | we_higher | +1.33 |
| BAKER MAYFIELD | QB | we_higher | +1.29 |

**Biggest disagreements vs ecr** (our z − their z; +we higher):

| player | pos | direction | gap (z) |
|--------|-----|-----------|--------:|
| ZACH ERTZ | TE | we_higher | +1.78 |
| CHRISTIAN MCCAFFREY | RB | we_higher | +1.67 |
| TRAVIS HUNTER | WR | we_lower | -1.65 |
| JA'MARR CHASE | WR | we_higher | +1.63 |
| AMON-RA ST. BROWN | WR | we_higher | +1.42 |
| ISAIAH LIKELY | TE | we_lower | -1.32 |
| JONNU SMITH | TE | we_higher | +1.31 |
| BHAYSHUL TUTEN | RB | we_lower | -1.27 |
| MATTHEW GOLDEN | WR | we_lower | -1.26 |
| LUTHER BURDEN III | WR | we_lower | -1.25 |

**Biggest disagreements vs fantasy_footballers** (our z − their z; +we higher):

| player | pos | direction | gap (z) |
|--------|-----|-----------|--------:|
| MALIK WILLIS | QB | we_lower | -1.87 |
| JAYDEN DANIELS | QB | we_lower | -1.75 |
| BHAYSHUL TUTEN | RB | we_lower | -1.41 |
| JA'MARR CHASE | WR | we_higher | +1.36 |
| JOE BURROW | QB | we_lower | -1.36 |
| HOLLYWOOD BROWN | WR | we_higher | +1.35 |
| CHRISTIAN MCCAFFREY | RB | we_higher | +1.34 |
| LUTHER BURDEN III | WR | we_lower | -1.33 |
| TRAVIS HUNTER | WR | we_lower | -1.32 |
| TUCKER KRAFT | TE | we_lower | -1.25 |

> ℹ️ Operator file benchmarks scored: fantasy_footballers 2026.

