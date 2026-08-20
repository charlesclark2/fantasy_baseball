# NF-C-LDA-6 — what a BENCH pick should be measured against

120 simulated drafts per arm (10 seasons x 12 draft slots), common random numbers across arms.
Metric: expected STARTING-LINEUP points over an 18-week season with byes and absence.

| arm | mean season pts | vs incumbent | 95% CI | won | of | players differing from incumbent | note |
|---|---:|---:|---:|---:|---:|---:|---|
| `oracle` | 1908.0 | +94.4 | ±7.9 | 119 | 120 | 4.5 | ⚓ anchor |
| `insurance` | 1884.4 | +70.7 | ±8.7 | 110 | 120 | 4.5 |  |
| `own_worst_starter` | 1857.0 | +43.3 | ±8.6 | 94 | 120 | 4.8 |  |
| `incumbent` | 1813.7 | +0.0 | — | 0 | 120 | 0.0 |  |
| `seats_covered` | 1787.5 | -26.1 | ±5.3 | 13 | 120 | 1.2 |  |
| `raw_points` | 1773.3 | -40.4 | ±6.3 | 9 | 120 | 3.3 | reference |
| `nihilist` | 1719.8 | -93.9 | ±6.4 | 0 | 120 | 6.3 | ⚓ anchor |

## What each rule actually puts on the bench

| arm | QB | RB | WR | TE | K | DST |
|---|---:|---:|---:|---:|---:|---:|
| `oracle` | 30% | 13% | 33% | 23% | 0% | 0% |
| `insurance` | 21% | 17% | 38% | 24% | 0% | 0% |
| `own_worst_starter` | 27% | 12% | 41% | 21% | 0% | 0% |
| `incumbent` | 47% | 0% | 0% | 53% | 0% | 0% |
| `seats_covered` | 31% | 0% | 1% | 68% | 0% | 0% |
| `raw_points` | 100% | 0% | 0% | 0% | 0% | 0% |
| `nihilist` | 0% | 0% | 2% | 98% | 0% | 0% |

### `insurance` vs `own_worst_starter`, paired

* mean delta **+27.4** pts, 95% CI ±6.8
* `insurance` wins **83 of 120** paired drafts
* verdict: **separable**

### By draft slot (vs incumbent)

| arm | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `oracle` | +129 | +112 | +72 | +120 | +102 | +57 | +86 | +96 | +79 | +94 | +80 | +106 |
| `insurance` | +101 | +71 | +43 | +94 | +87 | +53 | +65 | +64 | +62 | +67 | +54 | +88 |
| `own_worst_starter` | +66 | +40 | +16 | +65 | +54 | +29 | +33 | +42 | +32 | +61 | +33 | +49 |
| `seats_covered` | -16 | -10 | -24 | -12 | -19 | -35 | -10 | -29 | -40 | -34 | -47 | -36 |
| `raw_points` | -15 | -36 | -53 | -30 | -24 | -68 | -51 | -35 | -53 | -36 | -42 | -41 |
| `nihilist` | -77 | -82 | -100 | -74 | -67 | -86 | -83 | -109 | -113 | -110 | -119 | -108 |

✅ Anchors held: the peeking oracle is not beaten, the nihilist is last.

