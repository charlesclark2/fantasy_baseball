# NF-C-LDA-6 — what a BENCH pick should be measured against

120 simulated drafts per arm (10 seasons x 12 draft slots), common random numbers across arms.
Metric: expected STARTING-LINEUP points over an 18-week season with byes and absence.

| arm | mean season pts | vs incumbent | 95% CI | won | of | players differing from incumbent | note |
|---|---:|---:|---:|---:|---:|---:|---|
| `oracle` | 1919.9 | +93.1 | ±7.7 | 118 | 120 | 4.4 | ⚓ anchor |
| `insurance` | 1904.0 | +77.3 | ±7.9 | 118 | 120 | 4.5 |  |
| `own_worst_starter` | 1884.5 | +57.7 | ±7.9 | 107 | 120 | 4.8 |  |
| `incumbent` | 1826.7 | +0.0 | — | 0 | 120 | 0.0 |  |
| `seats_covered` | 1800.1 | -26.6 | ±5.4 | 15 | 120 | 1.2 |  |
| `raw_points` | 1788.8 | -38.0 | ±5.9 | 7 | 120 | 3.3 | reference |
| `nihilist` | 1724.6 | -102.2 | ±7.4 | 0 | 120 | 6.3 | ⚓ anchor |

## What each rule actually puts on the bench

| arm | QB | RB | WR | TE | K | DST |
|---|---:|---:|---:|---:|---:|---:|
| `oracle` | 35% | 10% | 32% | 23% | 0% | 0% |
| `insurance` | 21% | 17% | 38% | 24% | 0% | 0% |
| `own_worst_starter` | 27% | 12% | 41% | 21% | 0% | 0% |
| `incumbent` | 47% | 0% | 0% | 53% | 0% | 0% |
| `seats_covered` | 31% | 0% | 1% | 68% | 0% | 0% |
| `raw_points` | 100% | 0% | 0% | 0% | 0% | 0% |
| `nihilist` | 0% | 0% | 2% | 98% | 0% | 0% |

### `insurance` vs `own_worst_starter`, paired

* mean delta **+19.5** pts, 95% CI ±6.5
* `insurance` wins **77 of 120** paired drafts
* verdict: **separable**

### By draft slot (vs incumbent)

| arm | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `oracle` | +120 | +118 | +70 | +107 | +108 | +68 | +86 | +93 | +78 | +92 | +90 | +86 |
| `insurance` | +109 | +88 | +57 | +84 | +94 | +52 | +68 | +78 | +68 | +77 | +72 | +80 |
| `own_worst_starter` | +67 | +60 | +36 | +76 | +77 | +46 | +41 | +67 | +53 | +66 | +56 | +48 |
| `seats_covered` | -16 | -9 | -21 | -16 | -10 | -36 | -21 | -28 | -38 | -33 | -50 | -42 |
| `raw_points` | -23 | -29 | -50 | -31 | -21 | -52 | -52 | -30 | -50 | -33 | -40 | -43 |
| `nihilist` | -92 | -90 | -104 | -88 | -70 | -85 | -88 | -109 | -129 | -117 | -133 | -120 |

✅ Anchors held: the peeking oracle is not beaten, the nihilist is last.

