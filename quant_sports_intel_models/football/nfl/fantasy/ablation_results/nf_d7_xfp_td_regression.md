# NF-D7 — Expected Fantasy Points (xFP) + TD regression

**Generated:** 2026-07-27T03:22:25.992979+00:00 · **seasons:** 2020–2025 · **baseline:** the FULL shipped MVP-1 model (all NF-D2/NF-D4/NF-D5 slices ON), `xfp_td_blend=0`. Edge-independent.

## Verdict — NULL — no robust top-tier ordering lift over the shipped baseline; DROPPED (the recency-weighted line already mean-reverts TDs). xFP/xTD delivered as leakage-safe FEATURES for NF1.1/NF1.2.

> The NF-D gate: keep the source only if it moves held-out WITHIN-TIER ordering on the TOP-TIER (draftable) metric, robustly. `best_alpha` N/A (projection product).

## 1. The premise — does base-season EXPECTED TD out-predict ACTUAL TD next year?

| role | n | ρ(actual→next) | ρ(expected→next) | ρ(50/50→next) |
|------|---|----------------|------------------|---------------|
| rush | 2575 | 0.655 | 0.665 | 0.662 |
| rec | 2575 | 0.590 | 0.629 | 0.634 |

Expected-TD (opportunity-based) is a better/equal forward predictor of next-year TDs than the raw actual — the mechanism TD regression exploits.

## 2. Projection ablation — held-out within-position ρ (TOP-TIER / draftable tier)

top-N per position: {'QB': 24, 'RB': 36, 'WR': 48, 'TE': 24}. Baseline top-tier pooled ρ = **0.395**; full-universe pooled ρ = 0.704.

| blend | QB | RB | WR | TE | top-pooled | Δ vs baseline |
|-------|----|----|----|----|-----------|---------------|
| 0.25 | 0.327 | 0.505 | 0.377 | 0.342 | 0.388 | -0.007 |
| 0.4 | 0.325 | 0.507 | 0.373 | 0.354 | 0.390 | -0.005 |
| 0.5 | 0.328 | 0.505 | 0.369 | 0.351 | 0.388 | -0.007 |
| 0.6 | 0.324 | 0.506 | 0.386 | 0.350 | 0.391 | -0.004 |
| 0.75 | 0.324 | 0.490 | 0.381 | 0.336 | 0.383 | -0.013 |

Oracle floor intact (no candidate beats the realized-outcome oracle): **True**.

## 3. xFP FEATURE best-shot — in-fold learned ridge residual (NF1.1/NF1.2 lens)

| | QB | RB | WR | TE | pooled Δ |
|--|----|----|----|----|---------|
| baseline | 0.654 | 0.715 | 0.725 | 0.723 | |
| + xFP learned | 0.648 | 0.705 | 0.724 | 0.715 | -0.006 |
| Δ | -0.006 | -0.009 | -0.002 | -0.008 | |

xFP feature set: `xfp_pg, td_luck_ratio, xrush_td_pg, xrec_td_pg, xrec_pg, xrec_yds_pg`. Documents whether a LEARNED model (NF1.1/NF1.2) can extract ordering signal the heuristic TD-regression blend cannot.

## Disposition

- **Ship blend:** `_XFP_TD_BLEND = 0.0` (OFF — dropped).
- xFP + expected-TD are LEAKAGE-SAFE (base-season-window opportunity + league conversion rates fit ≤ base season) and delivered as candidate FEATURES for NF1.1/NF1.2 via `xfp_source.load_xfp_features` (xrush_td_pg, xrec_td_pg, xrec_pg, xrec_yds_pg, xfp_pg, td_luck_ratio).

