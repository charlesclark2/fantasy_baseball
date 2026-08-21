# NF-TR2b — whole-board CROSS-POSITION placement read (the NF-D16 class)
_generated 2026-08-21T00:54:11.754745+00:00_ · read from `s3://credence-prod-s3-api-cache/fantasy/nfl/2026/` · `best_alpha = 0` · served `nfl_fantasy_nf_tr2b_veteran_level_v1` · status `recalibrated` · board built 2026-08-20T14:22:29.512306+00:00

## Verdict: **SANE**

The WITHIN-position guarantee (a positive constant is monotone) is exact and already pinned by the TR2b record's L5 identity. This read answers the question that guarantee is silent on — what the correction does ACROSS positions on the VOR board a drafter reads.

⚠️ VOR does not absorb it: NF-W8-0's finding that a per-group level shift cancels in VOR space is about an ADDITIVE shift. TR2b is MULTIPLICATIVE, so `vor -> k*vor` does not cancel AND the greedy FLEX allocation (a cross-position draft on points) re-runs.

### Gates — structural or inherited, never tuned to the measured answer

| gate | verdict | detail |
|---|---|---|
| G1 within-position order preserved | PASS | failing: none |
| G2 rookie placement cap (DELEGATED to NF-D18/D20) | PASS | failing: none |
| G3 no recalibrated position wiped from top 100 | PASS | failing: none |
| G4 served band integrity (p10 <= point <= p90) | PASS | n=871, above p90 0, below p10 0, order violations 0 |

`k` READ FROM THE SERVED ARTIFACT: QB 0.9288 · RB 1.2480 · TE 1.1116 · WR 1.0995

### Movement — REPORTED, NEVER GATED

| config | n | top 1-24 mean\|move\| | 301+ mean\|move\| | vet mean move | rookie mean move | rho(ADP) inc -> rec |
|---|---|---|---|---|---|---|
| standard_10 | 871 | 2.42 | 33.99 | 1.44 | -14.05 | 0.6871 -> 0.6686 (-0.0185) |
| standard_12 | 871 | 2.25 | 20.22 | 1.7 | -16.58 | 0.7434 -> 0.7268 (-0.0165) |
| standard_3wr_10 | 871 | 1.96 | 28.67 | 2.95 | -28.75 | 0.7543 -> 0.756 (+0.0017) |
| standard_3wr_12 | 871 | 2.0 | 49.32 | 2.27 | -22.12 | 0.8103 -> 0.8111 (+0.0008) |
| half_ppr_10 | 871 | 4.17 | 40.67 | 3.18 | -30.99 | 0.7194 -> 0.6892 (-0.0302) |
| half_ppr_12 | 871 | 2.96 | 11.2 | 2.39 | -23.35 | 0.7513 -> 0.7549 (+0.0036) |
| half_ppr_3wr_10 | 871 | 2.29 | 48.27 | 2.57 | -25.09 | 0.7587 -> 0.7584 (-0.0002) |
| half_ppr_3wr_12 | 871 | 3.38 | 33.55 | 2.7 | -26.31 | 0.8203 -> 0.812 (-0.0083) |
| full_ppr_10 | 871 | 4.33 | 27.51 | 3.02 | -29.41 | 0.7078 -> 0.6644 (-0.0434) |
| full_ppr_12 | 871 | 4.04 | 10.63 | 2.54 | -24.75 | 0.7276 -> 0.7334 (+0.0058) |
| full_ppr_3wr_10 | 871 | 3.71 | 16.03 | 2.5 | -24.37 | 0.7312 -> 0.7349 (+0.0036) |
| full_ppr_3wr_12 | 871 | 4.42 | 39.78 | 3.48 | -33.9 | 0.7888 -> 0.7872 (-0.0016) |
| superflex_10 | 871 | 3.79 | 33.07 | 3.13 | -30.56 | 0.7288 -> 0.7044 (-0.0244) |
| superflex_12 | 871 | 5.25 | 20.75 | 2.43 | -23.73 | 0.774 -> 0.784 (+0.01) |

⭐ The churn concentrates in the DEEP board where VOR is flat and overall rank is near-noise; the decision-relevant top-24 moves by a few ranks. Market agreement is a READ, never a target (`best_alpha = 0`).

### G2 is ACTIVE, not vacuously passing

The INCUMBENT board breaches the inherited rookie-placement cap on `['standard_12']` config(s), and TR2b REPAIRS it on `['standard_12']`. That matters for how the pass should be read: a gate no board could ever trip would be passing on nothing (NF-D20 — count the cases the mechanism can move before crediting a pass). Here the cap demonstrably CAN fire on this board, and the correction moves it the right way.

### The rookie/veteran boundary — a measured, DISCLOSED consequence

TR2b touches VETERANS only; the rookie leg is held at incumbent (NF-D21 CLOSED, CONSTRAINT_REFUSED). So rookies move purely as a RELATIVE consequence, and because three of four `k` exceed 1 they move DOWN — per position tracking the `k` of the veterans they compete with, QB rookies (the only `k` < 1) being the ones that RISE.

⚠️ The whole-board rookie mean is dominated by the ~76 rookies in the flat-VOR tail, where a large rank move is near-noise. The DECISION-RELEVANT figure is the 3-5 rookies inside the top 60, and it is NOT simply a smaller version of the headline — it runs both above and below it by config (`standard_10` moves -34.8 in the top 60 against a -14.1 whole-board mean; `superflex_10` moves -11.8 against -30.6). Read this table, not the headline:

| config | rookies in top 60 | mean move | median move |
|---|---|---|---|
| standard_10 | 4 | -34.75 | -29.0 |
| standard_12 | 3 | -19.0 | -20.0 |
| standard_3wr_10 | 3 | -13.33 | -13.0 |
| standard_3wr_12 | 3 | -13.0 | -12.0 |
| half_ppr_10 | 4 | -28.0 | -23.0 |
| half_ppr_12 | 4 | -19.5 | -20.5 |
| half_ppr_3wr_10 | 4 | -18.0 | -16.0 |
| half_ppr_3wr_12 | 3 | -17.0 | -14.0 |
| full_ppr_10 | 4 | -17.75 | -16.5 |
| full_ppr_12 | 4 | -16.75 | -16.5 |
| full_ppr_3wr_10 | 4 | -16.25 | -14.5 |
| full_ppr_3wr_12 | 4 | -19.0 | -20.0 |
| superflex_10 | 5 | -11.8 | -20.0 |
| superflex_12 | 4 | -12.0 | -15.0 |

⭐ That direction is why G2 cannot be breached here: `rookie_placement_breach` caps a rookie placing TOO HIGH, and this correction moves them away from that cap. ⚠️ The honest converse: there is NO guard on the opposite side, so veterans are re-priced against an UNCORRECTED rookie leg by construction. Disclosed, not adjudicated by this read.

