# NF-D2 slice 2 — NGS + PFR advanced. **VERDICT: NULL (dropped, not shipped)**

**Generated:** 2026-07-26T05:05:15.406058+00:00 · **seasons:** 2019–2025 · **baseline:** slice-1 model (`usage_role_blend=0.4`)

> The NF-D2 gate is a positive, held-out WITHIN-POSITION ρ lift over the prior shipped model. NGS/PFR advanced metrics fail it: they correlate with next-season production in absolute terms but do NOT reorder within-tier RANK on top of slice-1. Per the discipline — *a null add is DROPPED, not shipped* — the feature is not wired into the production model. Edge-independent.

## Best-shot test — in-fold learned ridge residual on the full NGS feature set (no peek)

| | QB | RB | WR | TE |
|--|----|----|----|----|
| slice-1 baseline | 0.642 | 0.717 | 0.716 | 0.727 |
| + NGS learned | 0.648 | 0.712 | 0.716 | 0.723 |
| **Δ** | +0.006 | -0.005 | -0.000 | -0.004 |

Net-zero to slightly negative — only QB shows a small isolated +; RB/WR/TE flat-to-negative. Two simpler mechanisms (a per-game `exp(λ·z)` tilt, λ swept 0→0.8; and swapping the WR expected-games role signal from snap→target/air-yards share) were also null.

## Why (mechanism)

- Controlling for current fp/g, the orthogonal forward signal is weak: WR intended-air-yards share partial-r ≈ +0.13, TE target/air-yards ≈ +0.20, RB rush-over-expected ≈ +0.04, WR snap share ≈ 0. Individually too weak, and collinear with production, to flip within-tier ranks.
- The recency-weighted multi-year production line + the slice-1 usage-role already carry the ordering signal these metrics re-encode.
- **Implication for the NF-D2 sequence:** the remaining ordering lift is in information-BEARING sources that carry signal ORTHOGONAL to the past line — injuries/availability (the games channel slice-1 proved works), Vegas team environment, vacated opportunity, ADP — not in advanced-efficiency data. NF1 (a learned model) may still consume NGS jointly; this documents that a heuristic add does not earn its pipeline.

