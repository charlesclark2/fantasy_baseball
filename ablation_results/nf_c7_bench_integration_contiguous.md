# NF-C-LDA-6 — what a BENCH pick should be measured against

120 simulated drafts per arm (10 seasons x 12 draft slots), common random numbers across arms.
Metric: expected STARTING-LINEUP points over an 18-week season with byes and absence.

| arm | mean season pts | vs incumbent | 95% CI | won | of | players differing from incumbent | note |
|---|---:|---:|---:|---:|---:|---:|---|
| `oracle` | 1908.1 | +92.5 | ±7.6 | 118 | 120 | 4.5 | ⚓ anchor |
| `insurance` | 1884.1 | +68.5 | ±8.5 | 110 | 120 | 4.5 |  |
| `insurance_seat` | 1865.5 | +50.0 | ±7.9 | 102 | 120 | 2.9 |  |
| `insurance_sorted` | 1862.5 | +46.9 | ±8.2 | 99 | 120 | 3.3 |  |
| `own_worst_starter` | 1857.0 | +41.4 | ±8.4 | 94 | 120 | 4.8 |  |
| `incumbent` | 1815.6 | +0.0 | — | 0 | 120 | 0.0 |  |
| `seats_covered` | 1792.3 | -23.3 | ±5.0 | 14 | 120 | 1.2 |  |
| `raw_points` | 1773.3 | -42.2 | ±5.9 | 5 | 120 | 3.1 | reference |
| `nihilist` | 1719.8 | -95.8 | ±6.0 | 0 | 120 | 6.3 | ⚓ anchor |

## What each rule actually puts on the bench

| arm | QB | RB | WR | TE | K | DST |
|---|---:|---:|---:|---:|---:|---:|
| `oracle` | 30% | 13% | 33% | 23% | 0% | 0% |
| `insurance` | 21% | 17% | 38% | 24% | 0% | 0% |
| `insurance_seat` | 27% | 16% | 22% | 36% | 0% | 0% |
| `insurance_sorted` | 19% | 16% | 22% | 44% | 0% | 0% |
| `own_worst_starter` | 27% | 12% | 41% | 21% | 0% | 0% |
| `incumbent` | 51% | 0% | 0% | 49% | 0% | 0% |
| `seats_covered` | 36% | 0% | 1% | 63% | 0% | 0% |
| `raw_points` | 100% | 0% | 0% | 0% | 0% | 0% |
| `nihilist` | 0% | 0% | 2% | 98% | 0% | 0% |

### `insurance` vs `insurance_seat`, paired

* mean delta **+18.5** pts, 95% CI ±6.6
* `insurance` wins **84 of 120** paired drafts
* verdict: **separable**

### By draft slot (vs incumbent)

| arm | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `oracle` | +116 | +108 | +69 | +118 | +100 | +58 | +86 | +94 | +80 | +94 | +80 | +107 |
| `insurance` | +89 | +67 | +41 | +92 | +85 | +53 | +64 | +62 | +60 | +67 | +54 | +88 |
| `insurance_seat` | +79 | +63 | +18 | +74 | +57 | +31 | +40 | +48 | +38 | +56 | +39 | +57 |
| `insurance_sorted` | +78 | +62 | +19 | +73 | +51 | +29 | +41 | +41 | +29 | +54 | +33 | +53 |
| `own_worst_starter` | +54 | +36 | +13 | +63 | +52 | +30 | +33 | +40 | +33 | +61 | +33 | +49 |
| `seats_covered` | -8 | -4 | -20 | -11 | -15 | -31 | -11 | -30 | -39 | -34 | -43 | -34 |
| `raw_points` | -27 | -40 | -55 | -32 | -26 | -68 | -51 | -36 | -53 | -36 | -42 | -41 |
| `nihilist` | -90 | -85 | -102 | -76 | -69 | -85 | -82 | -111 | -112 | -110 | -119 | -108 |

✅ Anchors held: the peeking oracle is not beaten, the nihilist is last.

