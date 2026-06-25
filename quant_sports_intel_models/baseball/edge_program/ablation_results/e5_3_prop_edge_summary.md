# E5.3 — Per-book de-vig + model-vs-market K-prop edge table (TRANSPARENCY, not a bet rec)

_Served model: poisson_glm_k (strikeout_glm_v1, λ=0.85, 10,000 draws). 63,765 (pitcher×date×book×line) rows · 7,076 pitcher×dates · 14 books._

## What this is
- De-vig each book's two-way K over/under price (additive method, integer-line PUSH handled) → the book's fair no-vig P(over).
- Price the E5.2 served K distribution at the book's EXACT line (half-line vs integer-push).
- **EDGE = model P(side | not push) − book de-vigged P(side)**; **EV per $1** at the offered price. Pinnacle carried as the sharp fair-value anchor where it prices the K prop.

## Distributions (de-viggable rows only)

| quantity | distribution |
|---|---|
| book hold (vig / overround) | mean 0.0702 · median 0.0693 · p05 0.0587 · p95 0.0919 (n=63,606) |
| edge_over = model − book (two-sided) | mean -0.0126 · median -0.0101 · p05 -0.1906 · p95 0.1529 (n=63,606) |
| \|model − book\| disagreement (NOT a tradeable edge) | mean 0.0842 · median 0.0716 · p05 0.0067 · p95 0.206 (n=63,606) |
| EV per $1, blind OVER (unbiased, net of vig) | mean -0.087 · median -0.0852 · p05 -0.434 · p95 0.2484 (n=63,606) |
| best-side EV per $1 (favourable-side, BIASED) | mean 0.0992 · median 0.0698 · p05 -0.0534 · p95 0.3556 (n=63,606) |
| edge vs Pinnacle (same line) | mean -0.0096 · median -0.0067 · p05 -0.192 · p95 0.1577 (n=51,824) |

- Two-sided `edge_over` mean ≈ -0.0126 (centred near 0 ⇒ the model neither systematically over- nor under-shoots the K market on average).
- **Blind-over EV ≈ -0.087/$1 (NEGATIVE)** — the honest unbiased read: betting these prices without selection just pays the vig.
- `best-side EV>0` fraction = 73.8% looks large but is **gross of the line-selection bias** (we always read the favourable side) and **unproven** — E5.4 is the gate.
- One-sided quotes (no de-vig): 159  ·  integer lines (push-handled): 2
- Pinnacle-anchored rows: 51,824 (81.3%) — Pinnacle prices the K prop broadly here (NOT thin).

## Median book hold (the prop vig is LARGE — the honest-framing point)

| book | median hold |
|---|---|
| fanduel | 0.060 |
| betonlineag | 0.064 |
| draftkings | 0.065 |
| bovada | 0.067 |
| betmgm | 0.068 |
| fanatics | 0.068 |
| pointsbetus | 0.070 |
| pinnacle | 0.071 |
| unibet_us | 0.071 |
| betrivers | 0.072 |
| barstool | 0.074 |
| williamhill_us | 0.078 |
| mybookieag | 0.080 |
| superbook | 0.100 |

> 🔒 **best_alpha = 0.** The edge column is MODEL-RELATIVE and UNPROVEN — net-of-vig is the only honest read, and the prop hold above is large. This table is the input to the **E5.4** hard gate (PBO<0.2/DSR>0 per market, multiple-comparison-corrected, + forward CLV net of the prop vig). No +EV claim is made here.
