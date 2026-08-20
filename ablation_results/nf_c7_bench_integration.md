# NF-C-LDA-6 — what a BENCH pick should be measured against

120 simulated drafts per arm (10 seasons x 12 draft slots), common random numbers across arms.
Metric: expected STARTING-LINEUP points over an 18-week season with byes and absence.

| arm | mean season pts | vs incumbent | 95% CI | won | of | players differing from incumbent | note |
|---|---:|---:|---:|---:|---:|---:|---|
| `oracle` | 1919.9 | +92.4 | ±7.5 | 118 | 120 | 4.4 | ⚓ anchor |
| `insurance` | 1903.9 | +76.5 | ±7.6 | 118 | 120 | 4.5 |  |
| `own_worst_starter` | 1884.5 | +57.1 | ±7.7 | 108 | 120 | 4.8 |  |
| `insurance_seat` | 1872.7 | +45.2 | ±8.0 | 102 | 120 | 2.9 |  |
| `insurance_sorted` | 1868.1 | +40.7 | ±8.5 | 97 | 120 | 3.3 |  |
| `incumbent` | 1827.4 | +0.0 | — | 0 | 120 | 0.0 |  |
| `seats_covered` | 1802.8 | -24.6 | ±5.1 | 16 | 120 | 1.2 |  |
| `raw_points` | 1788.8 | -38.6 | ±5.6 | 5 | 120 | 3.1 | reference |
| `nihilist` | 1724.6 | -102.8 | ±7.2 | 0 | 120 | 6.3 | ⚓ anchor |

## What each rule actually puts on the bench

| arm | QB | RB | WR | TE | K | DST |
|---|---:|---:|---:|---:|---:|---:|
| `oracle` | 35% | 10% | 32% | 23% | 0% | 0% |
| `insurance` | 21% | 17% | 38% | 24% | 0% | 0% |
| `own_worst_starter` | 27% | 12% | 41% | 21% | 0% | 0% |
| `insurance_seat` | 27% | 16% | 22% | 36% | 0% | 0% |
| `insurance_sorted` | 19% | 16% | 22% | 44% | 0% | 0% |
| `incumbent` | 51% | 0% | 0% | 49% | 0% | 0% |
| `seats_covered` | 36% | 0% | 1% | 63% | 0% | 0% |
| `raw_points` | 100% | 0% | 0% | 0% | 0% | 0% |
| `nihilist` | 0% | 0% | 2% | 98% | 0% | 0% |

### `insurance` vs `own_worst_starter`, paired

* mean delta **+19.4** pts, 95% CI ±6.5
* `insurance` wins **77 of 120** paired drafts
* verdict: **separable**

### By draft slot (vs incumbent)

| arm | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `oracle` | +114 | +116 | +68 | +107 | +106 | +69 | +86 | +93 | +79 | +93 | +90 | +86 |
| `insurance` | +102 | +86 | +56 | +84 | +92 | +55 | +68 | +78 | +66 | +78 | +73 | +80 |
| `own_worst_starter` | +61 | +58 | +34 | +76 | +75 | +47 | +41 | +67 | +54 | +67 | +56 | +48 |
| `insurance_seat` | +69 | +56 | +25 | +61 | +67 | +32 | +27 | +48 | +40 | +32 | +48 | +38 |
| `insurance_sorted` | +68 | +56 | +15 | +58 | +60 | +26 | +30 | +44 | +31 | +30 | +39 | +31 |
| `seats_covered` | -10 | -7 | -16 | -14 | -10 | -32 | -21 | -28 | -39 | -30 | -49 | -39 |
| `raw_points` | -29 | -31 | -51 | -31 | -23 | -51 | -52 | -30 | -49 | -32 | -40 | -43 |
| `nihilist` | -99 | -92 | -105 | -88 | -72 | -84 | -88 | -109 | -128 | -117 | -132 | -120 |

✅ Anchors held: the peeking oracle is not beaten, the nihilist is last.

