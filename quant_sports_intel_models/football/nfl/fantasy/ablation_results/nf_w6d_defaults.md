# NF-W6d Phase C — calibrated DEFAULT distributions for the no-winner cells

**Generated:** 2026-08-16T01:14:18+00:00 · **folds:** 8 (2022H1…2025H2) · **rows:** 84553 · **cells:** 45

> ⚖️ **Edge-independent projection product** — `best_alpha` N/A, **deploy-held**. A default is chosen by pre-registered ORDER + calibration gates (one-sided coverage floor ∧ randomized-PIT max-decile-deviation ≤ 0.03); ⛔ NOT a bake-off winner, NOT selected on CRPS. The nihilist is scored against every default (NF-D14). A distribution here is a calibrated RANGE, never an edge or win-rate claim.

## Verdict: **DEFAULTS 45 cells → {'climatology': 25, 'count_negbin': 20}; 0 uncalibrated (flagged)**

| cell | kind | order | chosen | cov80 | PIT max-dev | calibrated | nihilist loses | CRPS | pred P(0) / real P(0) | warning |
|---|---|---|---|---|---|---|---|---|---|---|
| QB|attempts | modeled | count_negbin→climatology | **climatology** | 0.9293 | 0.02416 | True | True | 8.50961 | 0.5559 / 0.54 | — |
| QB|carries | modeled | count_negbin→climatology | **count_negbin** | 0.932 | 0.01668 | True | True | 0.86836 | 0.5344 / 0.5741 | — |
| QB|fumbles_lost | modeled | count_negbin→climatology | **count_negbin** | 0.9657 | 0.00629 | True | True | 0.07933 | 0.9267 / 0.9207 | — |
| QB|passing_interceptions | modeled | count_negbin→climatology | **count_negbin** | 0.9562 | 0.00939 | True | True | 0.2147 | 0.7979 / 0.7916 | — |
| QB|receiving_tds | minor | climatology | **climatology** | 0.9985 | 0.00611 | True | False | 0.00146 | 1.0 / 0.9985 | — |
| QB|receiving_yards | minor | climatology | **climatology** | 0.9912 | 0.00647 | True | True | 0.10279 | 0.995 / 0.9912 | — |
| QB|receptions | minor | climatology | **climatology** | 0.9916 | 0.00574 | True | True | 0.01302 | 0.995 / 0.9916 | — |
| QB|rushing_tds | modeled | count_negbin→climatology | **count_negbin** | 0.9703 | 0.00629 | True | True | 0.06816 | 0.939 / 0.9329 | — |
| QB|targets | minor | climatology | **climatology** | 0.9898 | 0.00501 | True | True | 0.01662 | 0.9899 / 0.9898 | — |
| QB|two_pt | modeled | count_negbin→climatology | **count_negbin** | 0.9759 | 0.00866 | True | True | 0.03292 | 0.9721 / 0.9679 | — |
| RB|attempts | minor | climatology | **climatology** | 0.9976 | 0.00746 | True | False | 0.00254 | 1.0 / 0.9976 | — |
| RB|carries | modeled | count_negbin→climatology | **climatology** | 0.9061 | 0.00977 | True | True | 3.56436 | 0.4172 / 0.3898 | — |
| RB|fumbles_lost | modeled | count_negbin→climatology | **count_negbin** | 0.9744 | 0.00397 | True | True | 0.02901 | 0.9728 / 0.9707 | — |
| RB|passing_interceptions | minor | climatology | **climatology** | 0.9998 | 0.0043 | True | False | 0.00022 | 1.0 / 0.9998 | — |
| RB|passing_tds | minor | climatology | **climatology** | 0.9988 | 0.00572 | True | False | 0.00117 | 1.0 / 0.9988 | — |
| RB|passing_yards | minor | climatology | **climatology** | 0.9986 | 0.00932 | True | False | 0.01448 | 1.0 / 0.9986 | — |
| RB|receiving_tds | modeled | count_negbin→climatology | **count_negbin** | 0.9701 | 0.00558 | True | True | 0.0416 | 0.9625 / 0.9584 | — |
| RB|receiving_yards | modeled | climatology | **climatology** | 0.8954 | 0.01095 | True | True | 6.52054 | 0.5628 / 0.5459 | — |
| RB|receptions | modeled | count_negbin→climatology | **count_negbin** | 0.9452 | 0.01421 | True | True | 0.59338 | 0.5064 / 0.5364 | — |
| RB|targets | modeled | count_negbin→climatology | **count_negbin** | 0.9425 | 0.0191 | True | True | 0.71948 | 0.4456 / 0.4898 | — |
| RB|two_pt | modeled | count_negbin→climatology | **count_negbin** | 0.9921 | 0.0079 | True | True | 0.00814 | 0.9946 / 0.992 | — |
| TE|attempts | minor | climatology | **climatology** | 0.9978 | 0.006 | True | False | 0.00341 | 1.0 / 0.9978 | — |
| TE|carries | minor | climatology | **climatology** | 0.9796 | 0.0123 | True | True | 0.0352 | 0.9899 / 0.9796 | — |
| TE|fumbles_lost | modeled | count_negbin→climatology | **count_negbin** | 0.992 | 0.00718 | True | True | 0.00795 | 0.9934 / 0.992 | — |
| TE|passing_interceptions | minor | climatology | **climatology** | 0.9999 | 0.00927 | True | False | 0.00013 | 1.0 / 0.9999 | — |
| TE|passing_tds | minor | climatology | **climatology** | 0.9999 | 0.00574 | True | False | 0.00013 | 1.0 / 0.9999 | — |
| TE|passing_yards | minor | climatology | **climatology** | 0.9987 | 0.00888 | True | False | 0.03139 | 1.0 / 0.9987 | — |
| TE|receiving_tds | modeled | count_negbin→climatology | **count_negbin** | 0.9599 | 0.00469 | True | True | 0.08781 | 0.914 / 0.9098 | — |
| TE|receptions | modeled | count_negbin→climatology | **count_negbin** | 0.9319 | 0.00629 | True | True | 0.66427 | 0.4575 / 0.4946 | — |
| TE|rushing_tds | minor | climatology | **climatology** | 0.9978 | 0.00522 | True | False | 0.00259 | 1.0 / 0.9978 | — |
| TE|rushing_yards | minor | climatology | **climatology** | 0.9824 | 0.00731 | True | True | 0.145 | 0.9931 / 0.9824 | — |
| TE|targets | modeled | count_negbin→climatology | **count_negbin** | 0.9277 | 0.01711 | True | True | 0.85378 | 0.3762 / 0.4318 | — |
| TE|two_pt | modeled | count_negbin→climatology | **count_negbin** | 0.9946 | 0.00642 | True | False | 0.00537 | 0.9961 / 0.9946 | — |
| WR|attempts | minor | climatology | **climatology** | 0.9957 | 0.00384 | True | False | 0.00436 | 0.995 / 0.9957 | — |
| WR|carries | minor | climatology | **climatology** | 0.8998 | 0.00774 | True | True | 0.12622 | 0.9077 / 0.8998 | — |
| WR|fumbles_lost | modeled | count_negbin→climatology | **count_negbin** | 0.988 | 0.01058 | True | True | 0.01217 | 0.9892 / 0.9878 | — |
| WR|passing_interceptions | minor | climatology | **climatology** | 0.9995 | 0.0038 | True | False | 0.00047 | 1.0 / 0.9995 | — |
| WR|passing_tds | minor | climatology | **climatology** | 0.9993 | 0.0045 | True | False | 0.0007 | 1.0 / 0.9993 | — |
| WR|passing_yards | minor | climatology | **climatology** | 0.9981 | 0.00434 | True | False | 0.03007 | 1.0 / 0.9981 | — |
| WR|receiving_tds | modeled | count_negbin→climatology | **count_negbin** | 0.9629 | 0.00645 | True | True | 0.12428 | 0.8715 / 0.867 | — |
| WR|receptions | modeled | count_negbin→climatology | **count_negbin** | 0.9183 | 0.01276 | True | True | 0.86347 | 0.3597 / 0.4091 | — |
| WR|rushing_tds | minor | climatology | **climatology** | 0.9942 | 0.00462 | True | False | 0.00583 | 0.9975 / 0.9942 | — |
| WR|rushing_yards | minor | climatology | **climatology** | 0.9046 | 0.01066 | True | True | 0.85158 | 0.9259 / 0.9046 | — |
| WR|targets | modeled | count_negbin→climatology | **count_negbin** | 0.904 | 0.01788 | True | True | 1.23667 | 0.2575 / 0.3398 | — |
| WR|two_pt | modeled | count_negbin→climatology | **count_negbin** | 0.9922 | 0.00322 | True | False | 0.00781 | 0.9951 / 0.9922 | — |

## Per-cell reads (every form in the order, so the choice is auditable)

### QB|attempts

- `count_negbin`: cov80 0.9438 (floor ok True, SE 0.0054, structural 0.954) · PIT max-dev 0.17274 (flat ok False) deciles [0.09626, 0.09243, 0.0979, 0.08605, 0.07748, 0.05743, 0.07201, 0.27274, 0.08897, 0.05871] · CRPS 7.38808 vs nihilist 13.04102 · pred P(0) 0.5039 vs real 0.54 · n 5485
- `climatology`: cov80 0.9293 (floor ok True, SE 0.0054, structural 0.954) · PIT max-dev 0.02416 (flat ok True) deciles [0.09644, 0.0917, 0.09335, 0.09772, 0.10428, 0.11048, 0.12416, 0.11139, 0.09298, 0.07748] · CRPS 8.50961 vs nihilist 13.04102 · pred P(0) 0.5559 vs real 0.54 · n 5485

### QB|carries

- `count_negbin`: cov80 0.932 (floor ok True, SE 0.0054, structural 0.9574) · PIT max-dev 0.01668 (flat ok True) deciles [0.09991, 0.09699, 0.09681, 0.09736, 0.10556, 0.11376, 0.11522, 0.10757, 0.0835, 0.08332] · CRPS 0.86836 vs nihilist 1.69921 · pred P(0) 0.5344 vs real 0.5741 · n 5485
- `climatology`: cov80 0.8999 (floor ok True, SE 0.0054, structural 0.9574) · PIT max-dev 0.02543 (flat ok True) deciles [0.08624, 0.09736, 0.09043, 0.101, 0.09389, 0.10027, 0.10283, 0.09699, 0.10556, 0.12543] · CRPS 1.26281 vs nihilist 1.69921 · pred P(0) 0.6036 vs real 0.5741 · n 5485

### QB|fumbles_lost

- `count_negbin`: cov80 0.9657 (floor ok True, SE 0.0054, structural 0.9921) · PIT max-dev 0.00629 (flat ok True) deciles [0.10119, 0.10337, 0.10337, 0.09699, 0.09973, 0.09973, 0.09572, 0.09663, 0.09699, 0.10629] · CRPS 0.07933 vs nihilist 0.08693 · pred P(0) 0.9267 vs real 0.9207 · n 5485
- `climatology`: cov80 0.9207 (floor ok True, SE 0.0054, structural 0.9921) · PIT max-dev 0.00775 (flat ok True) deciles [0.10173, 0.10684, 0.09225, 0.09754, 0.09881, 0.10046, 0.09626, 0.10392, 0.09973, 0.10246] · CRPS 0.081 vs nihilist 0.08693 · pred P(0) 0.9234 vs real 0.9207 · n 5485

### QB|passing_interceptions

- `count_negbin`: cov80 0.9562 (floor ok True, SE 0.0054, structural 0.9792) · PIT max-dev 0.00939 (flat ok True) deciles [0.09772, 0.10939, 0.09517, 0.09298, 0.10137, 0.10574, 0.10319, 0.09626, 0.10228, 0.0959] · CRPS 0.2147 vs nihilist 0.29273 · pred P(0) 0.7979 vs real 0.7916 · n 5485
- `climatology`: cov80 0.9333 (floor ok True, SE 0.0054, structural 0.9792) · PIT max-dev 0.00921 (flat ok True) deciles [0.10009, 0.099, 0.10921, 0.1041, 0.10046, 0.09736, 0.09644, 0.10027, 0.10173, 0.09134] · CRPS 0.24589 vs nihilist 0.29273 · pred P(0) 0.7889 vs real 0.7916 · n 5485

### QB|receiving_tds

- `climatology`: cov80 0.9985 (floor ok True, SE 0.0054, structural 0.9999) · PIT max-dev 0.00611 (flat ok True) deciles [0.09389, 0.10392, 0.09991, 0.10392, 0.09845, 0.10082, 0.10046, 0.0979, 0.09717, 0.10356] · CRPS 0.00146 vs nihilist 0.00146 · pred P(0) 1.0 vs real 0.9985 · n 5485

### QB|receiving_yards

- `climatology`: cov80 0.9912 (floor ok True, SE 0.0054, structural 0.9991) · PIT max-dev 0.00647 (flat ok True) deciles [0.10064, 0.09845, 0.09663, 0.09772, 0.10647, 0.09426, 0.10264, 0.10593, 0.09663, 0.10064] · CRPS 0.10279 vs nihilist 0.1028 · pred P(0) 0.995 vs real 0.9912 · n 5485

### QB|receptions

- `climatology`: cov80 0.9916 (floor ok True, SE 0.0054, structural 0.9992) · PIT max-dev 0.00574 (flat ok True) deciles [0.099, 0.09936, 0.10119, 0.10301, 0.09644, 0.10428, 0.09827, 0.09426, 0.09845, 0.10574] · CRPS 0.01302 vs nihilist 0.01306 · pred P(0) 0.995 vs real 0.9916 · n 5485

### QB|rushing_tds

- `count_negbin`: cov80 0.9703 (floor ok True, SE 0.0054, structural 0.9933) · PIT max-dev 0.00629 (flat ok True) deciles [0.10374, 0.09644, 0.09991, 0.09991, 0.09553, 0.09954, 0.10629, 0.09936, 0.09973, 0.09954] · CRPS 0.06816 vs nihilist 0.07877 · pred P(0) 0.939 vs real 0.9329 · n 5485
- `climatology`: cov80 0.9329 (floor ok True, SE 0.0054, structural 0.9933) · PIT max-dev 0.01194 (flat ok True) deciles [0.09407, 0.10119, 0.10283, 0.08806, 0.09736, 0.0979, 0.10447, 0.10593, 0.09644, 0.11176] · CRPS 0.0746 vs nihilist 0.07877 · pred P(0) 0.9435 vs real 0.9329 · n 5485

### QB|targets

- `climatology`: cov80 0.9898 (floor ok True, SE 0.0054, structural 0.999) · PIT max-dev 0.00501 (flat ok True) deciles [0.10465, 0.10064, 0.10501, 0.10064, 0.09572, 0.09626, 0.09572, 0.10027, 0.09827, 0.10283] · CRPS 0.01662 vs nihilist 0.01667 · pred P(0) 0.9899 vs real 0.9898 · n 5485

### QB|two_pt

- `count_negbin`: cov80 0.9759 (floor ok True, SE 0.0054, structural 0.9968) · PIT max-dev 0.00866 (flat ok True) deciles [0.10155, 0.10392, 0.10191, 0.09189, 0.09681, 0.10356, 0.09134, 0.10264, 0.0979, 0.10848] · CRPS 0.03292 vs nihilist 0.03376 · pred P(0) 0.9721 vs real 0.9679 · n 5485
- `climatology`: cov80 0.9679 (floor ok True, SE 0.0054, structural 0.9968) · PIT max-dev 0.0052 (flat ok True) deciles [0.10337, 0.10009, 0.10283, 0.09918, 0.0948, 0.10046, 0.09499, 0.09608, 0.1052, 0.10301] · CRPS 0.03288 vs nihilist 0.03376 · pred P(0) 0.9698 vs real 0.9679 · n 5485

### RB|attempts

- `climatology`: cov80 0.9976 (floor ok True, SE 0.0043, structural 0.9998) · PIT max-dev 0.00746 (flat ok True) deciles [0.10697, 0.10441, 0.09754, 0.09254, 0.10162, 0.09743, 0.0965, 0.09789, 0.10185, 0.10325] · CRPS 0.00254 vs nihilist 0.00254 · pred P(0) 1.0 vs real 0.9976 · n 8591

### RB|carries

- `count_negbin`: cov80 0.9214 (floor ok True, SE 0.0043, structural 0.939) · PIT max-dev 0.03561 (flat ok False) deciles [0.10534, 0.08951, 0.08753, 0.08567, 0.10139, 0.12129, 0.13561, 0.11594, 0.08032, 0.07741] · CRPS 2.29942 vs nihilist 5.50654 · pred P(0) 0.3109 vs real 0.3898 · n 8591
- `climatology`: cov80 0.9061 (floor ok True, SE 0.0043, structural 0.939) · PIT max-dev 0.00977 (flat ok True) deciles [0.09312, 0.09848, 0.09254, 0.09056, 0.09568, 0.10139, 0.10418, 0.10907, 0.10977, 0.10523] · CRPS 3.56436 vs nihilist 5.50654 · pred P(0) 0.4172 vs real 0.3898 · n 8591

### RB|fumbles_lost

- `count_negbin`: cov80 0.9744 (floor ok True, SE 0.0043, structural 0.9971) · PIT max-dev 0.00397 (flat ok True) deciles [0.09708, 0.1029, 0.10371, 0.09603, 0.10115, 0.1015, 0.10139, 0.09882, 0.09859, 0.09882] · CRPS 0.02901 vs nihilist 0.03008 · pred P(0) 0.9728 vs real 0.9707 · n 8591
- `climatology`: cov80 0.9707 (floor ok True, SE 0.0043, structural 0.9971) · PIT max-dev 0.007 (flat ok True) deciles [0.09906, 0.093, 0.10301, 0.10325, 0.10592, 0.09813, 0.09871, 0.09999, 0.10115, 0.09778] · CRPS 0.02937 vs nihilist 0.03008 · pred P(0) 0.9711 vs real 0.9707 · n 8591

### RB|passing_interceptions

- `climatology`: cov80 0.9998 (floor ok True, SE 0.0043, structural 1.0) · PIT max-dev 0.0043 (flat ok True) deciles [0.09906, 0.1022, 0.1008, 0.09999, 0.09871, 0.09708, 0.10173, 0.1043, 0.10022, 0.09591] · CRPS 0.00022 vs nihilist 0.00022 · pred P(0) 1.0 vs real 0.9998 · n 8591

### RB|passing_tds

- `climatology`: cov80 0.9988 (floor ok True, SE 0.0043, structural 0.9999) · PIT max-dev 0.00572 (flat ok True) deciles [0.10267, 0.10173, 0.1036, 0.09836, 0.10278, 0.09789, 0.09801, 0.09428, 0.10127, 0.09941] · CRPS 0.00117 vs nihilist 0.00117 · pred P(0) 1.0 vs real 0.9988 · n 8591

### RB|passing_yards

- `climatology`: cov80 0.9986 (floor ok True, SE 0.0043, structural 0.9999) · PIT max-dev 0.00932 (flat ok True) deciles [0.10243, 0.10325, 0.10278, 0.10313, 0.10418, 0.09068, 0.09626, 0.09824, 0.09638, 0.10267] · CRPS 0.01448 vs nihilist 0.01448 · pred P(0) 1.0 vs real 0.9986 · n 8591

### RB|receiving_tds

- `count_negbin`: cov80 0.9701 (floor ok True, SE 0.0043, structural 0.9958) · PIT max-dev 0.00558 (flat ok True) deciles [0.09743, 0.09917, 0.09754, 0.09882, 0.10104, 0.09743, 0.10045, 0.1001, 0.10243, 0.10558] · CRPS 0.0416 vs nihilist 0.04433 · pred P(0) 0.9625 vs real 0.9584 · n 8591
- `climatology`: cov80 0.9584 (floor ok True, SE 0.0043, structural 0.9958) · PIT max-dev 0.00883 (flat ok True) deciles [0.10499, 0.10232, 0.09615, 0.09417, 0.09603, 0.09894, 0.10883, 0.09941, 0.09952, 0.09964] · CRPS 0.04281 vs nihilist 0.04433 · pred P(0) 0.9585 vs real 0.9584 · n 8591

### RB|receiving_yards

- `climatology`: cov80 0.8954 (floor ok True, SE 0.0043, structural 0.9546) · PIT max-dev 0.01095 (flat ok True) deciles [0.10197, 0.09754, 0.0951, 0.09941, 0.10232, 0.1079, 0.10779, 0.10639, 0.09254, 0.08905] · CRPS 6.52054 vs nihilist 8.47395 · pred P(0) 0.5628 vs real 0.5459 · n 8591

### RB|receptions

- `count_negbin`: cov80 0.9452 (floor ok True, SE 0.0043, structural 0.9536) · PIT max-dev 0.01421 (flat ok True) deciles [0.10115, 0.10511, 0.09673, 0.10383, 0.11256, 0.10092, 0.10336, 0.09836, 0.09219, 0.08579] · CRPS 0.59338 vs nihilist 1.13619 · pred P(0) 0.5064 vs real 0.5364 · n 8591
- `climatology`: cov80 0.9451 (floor ok True, SE 0.0043, structural 0.9536) · PIT max-dev 0.01212 (flat ok True) deciles [0.09789, 0.1029, 0.10197, 0.09405, 0.09999, 0.09999, 0.10208, 0.10569, 0.10755, 0.08788] · CRPS 0.79685 vs nihilist 1.13619 · pred P(0) 0.5402 vs real 0.5364 · n 8591

### RB|targets

- `count_negbin`: cov80 0.9425 (floor ok True, SE 0.0043, structural 0.949) · PIT max-dev 0.0191 (flat ok True) deciles [0.10057, 0.10115, 0.11046, 0.1029, 0.10965, 0.10453, 0.10336, 0.09498, 0.09149, 0.0809] · CRPS 0.71948 vs nihilist 1.45732 · pred P(0) 0.4456 vs real 0.4898 · n 8591
- `climatology`: cov80 0.9454 (floor ok True, SE 0.0043, structural 0.949) · PIT max-dev 0.01736 (flat ok True) deciles [0.0958, 0.09941, 0.09964, 0.10162, 0.10371, 0.1015, 0.10802, 0.10453, 0.10313, 0.08264] · CRPS 0.99252 vs nihilist 1.45732 · pred P(0) 0.4912 vs real 0.4898 · n 8591

### RB|two_pt

- `count_negbin`: cov80 0.9921 (floor ok True, SE 0.0043, structural 0.9992) · PIT max-dev 0.0079 (flat ok True) deciles [0.10232, 0.10185, 0.09754, 0.10069, 0.09615, 0.1079, 0.09929, 0.09906, 0.09952, 0.09568] · CRPS 0.00814 vs nihilist 0.00817 · pred P(0) 0.9946 vs real 0.992 · n 8591
- `climatology`: cov80 0.992 (floor ok True, SE 0.0043, structural 0.9992) · PIT max-dev 0.00721 (flat ok True) deciles [0.09964, 0.10651, 0.1015, 0.09813, 0.09731, 0.09347, 0.10173, 0.10721, 0.09545, 0.09906] · CRPS 0.00814 vs nihilist 0.00817 · pred P(0) 0.995 vs real 0.992 · n 8591

### TE|attempts

- `climatology`: cov80 0.9978 (floor ok True, SE 0.0046, structural 0.9998) · PIT max-dev 0.006 (flat ok True) deciles [0.1025, 0.09439, 0.09936, 0.10394, 0.10367, 0.10315, 0.09844, 0.094, 0.1008, 0.09975] · CRPS 0.00341 vs nihilist 0.00341 · pred P(0) 1.0 vs real 0.9978 · n 7649

### TE|carries

- `climatology`: cov80 0.9796 (floor ok True, SE 0.0046, structural 0.998) · PIT max-dev 0.0123 (flat ok True) deciles [0.10067, 0.1025, 0.09884, 0.09413, 0.09727, 0.10302, 0.09805, 0.09674, 0.09648, 0.1123] · CRPS 0.0352 vs nihilist 0.03546 · pred P(0) 0.9899 vs real 0.9796 · n 7649

### TE|fumbles_lost

- `count_negbin`: cov80 0.992 (floor ok True, SE 0.0046, structural 0.9992) · PIT max-dev 0.00718 (flat ok True) deciles [0.09688, 0.09766, 0.09282, 0.09701, 0.09635, 0.10394, 0.10472, 0.10302, 0.10289, 0.10472] · CRPS 0.00795 vs nihilist 0.00797 · pred P(0) 0.9934 vs real 0.992 · n 7649
- `climatology`: cov80 0.992 (floor ok True, SE 0.0046, structural 0.9992) · PIT max-dev 0.00509 (flat ok True) deciles [0.09622, 0.10119, 0.10145, 0.09805, 0.10132, 0.09688, 0.1025, 0.10289, 0.09491, 0.10459] · CRPS 0.00794 vs nihilist 0.00797 · pred P(0) 0.995 vs real 0.992 · n 7649

### TE|passing_interceptions

- `climatology`: cov80 0.9999 (floor ok True, SE 0.0046, structural 1.0) · PIT max-dev 0.00927 (flat ok True) deciles [0.09635, 0.09727, 0.10054, 0.09622, 0.10799, 0.09073, 0.10498, 0.10197, 0.10119, 0.10276] · CRPS 0.00013 vs nihilist 0.00013 · pred P(0) 1.0 vs real 0.9999 · n 7649

### TE|passing_tds

- `climatology`: cov80 0.9999 (floor ok True, SE 0.0046, structural 1.0) · PIT max-dev 0.00574 (flat ok True) deciles [0.09844, 0.10106, 0.09426, 0.10263, 0.10459, 0.10446, 0.10237, 0.09491, 0.09478, 0.1025] · CRPS 0.00013 vs nihilist 0.00013 · pred P(0) 1.0 vs real 0.9999 · n 7649

### TE|passing_yards

- `climatology`: cov80 0.9987 (floor ok True, SE 0.0046, structural 0.9999) · PIT max-dev 0.00888 (flat ok True) deciles [0.10655, 0.10485, 0.0991, 0.10145, 0.09152, 0.09674, 0.10132, 0.09112, 0.1059, 0.10145] · CRPS 0.03139 vs nihilist 0.03139 · pred P(0) 1.0 vs real 0.9987 · n 7649

### TE|receiving_tds

- `count_negbin`: cov80 0.9599 (floor ok True, SE 0.0046, structural 0.991) · PIT max-dev 0.00469 (flat ok True) deciles [0.09962, 0.10237, 0.10106, 0.10394, 0.10145, 0.0974, 0.09557, 0.09531, 0.10237, 0.10093] · CRPS 0.08781 vs nihilist 0.10182 · pred P(0) 0.914 vs real 0.9098 · n 7649
- `climatology`: cov80 0.9464 (floor ok True, SE 0.0046, structural 0.991) · PIT max-dev 0.00927 (flat ok True) deciles [0.09818, 0.09661, 0.10472, 0.10524, 0.09648, 0.10577, 0.10106, 0.10093, 0.10027, 0.09073] · CRPS 0.09416 vs nihilist 0.10182 · pred P(0) 0.902 vs real 0.9098 · n 7649

### TE|receptions

- `count_negbin`: cov80 0.9319 (floor ok True, SE 0.0046, structural 0.9495) · PIT max-dev 0.00629 (flat ok True) deciles [0.09753, 0.0991, 0.09701, 0.10171, 0.10485, 0.1008, 0.10027, 0.10629, 0.09531, 0.09714] · CRPS 0.66427 vs nihilist 1.4113 · pred P(0) 0.4575 vs real 0.4946 · n 7649
- `climatology`: cov80 0.9121 (floor ok True, SE 0.0046, structural 0.9495) · PIT max-dev 0.00652 (flat ok True) deciles [0.10472, 0.10119, 0.09714, 0.10027, 0.10158, 0.09936, 0.09348, 0.09753, 0.0991, 0.10563] · CRPS 0.97154 vs nihilist 1.4113 · pred P(0) 0.4906 vs real 0.4946 · n 7649

### TE|rushing_tds

- `climatology`: cov80 0.9978 (floor ok True, SE 0.0046, structural 0.9998) · PIT max-dev 0.00522 (flat ok True) deciles [0.10197, 0.10197, 0.10145, 0.09766, 0.1021, 0.09478, 0.09727, 0.10067, 0.10054, 0.10158] · CRPS 0.00259 vs nihilist 0.00259 · pred P(0) 1.0 vs real 0.9978 · n 7649

### TE|rushing_yards

- `climatology`: cov80 0.9824 (floor ok True, SE 0.0046, structural 0.9982) · PIT max-dev 0.00731 (flat ok True) deciles [0.10328, 0.09884, 0.09374, 0.10093, 0.10563, 0.09923, 0.09857, 0.10145, 0.09269, 0.10563] · CRPS 0.145 vs nihilist 0.14526 · pred P(0) 0.9931 vs real 0.9824 · n 7649

### TE|targets

- `count_negbin`: cov80 0.9277 (floor ok True, SE 0.0046, structural 0.9432) · PIT max-dev 0.01711 (flat ok True) deciles [0.10903, 0.10001, 0.10237, 0.10276, 0.10642, 0.10433, 0.10433, 0.09884, 0.08903, 0.08289] · CRPS 0.85378 vs nihilist 1.98109 · pred P(0) 0.3762 vs real 0.4318 · n 7649
- `climatology`: cov80 0.9205 (floor ok True, SE 0.0046, structural 0.9432) · PIT max-dev 0.00799 (flat ok True) deciles [0.10093, 0.10328, 0.09949, 0.10184, 0.10799, 0.09988, 0.09871, 0.09779, 0.09714, 0.09295] · CRPS 1.31859 vs nihilist 1.98109 · pred P(0) 0.424 vs real 0.4318 · n 7649

### TE|two_pt

- `count_negbin`: cov80 0.9946 (floor ok True, SE 0.0046, structural 0.9995) · PIT max-dev 0.00642 (flat ok True) deciles [0.10289, 0.09583, 0.09792, 0.09936, 0.09491, 0.10642, 0.09805, 0.10106, 0.10119, 0.10237] · CRPS 0.00537 vs nihilist 0.00536 · pred P(0) 0.9961 vs real 0.9946 · n 7649
- `climatology`: cov80 0.9946 (floor ok True, SE 0.0046, structural 0.9995) · PIT max-dev 0.01005 (flat ok True) deciles [0.1025, 0.09897, 0.1008, 0.10119, 0.09871, 0.08995, 0.10328, 0.09975, 0.10472, 0.10014] · CRPS 0.00536 vs nihilist 0.00536 · pred P(0) 0.995 vs real 0.9946 · n 7649

### WR|attempts

- `climatology`: cov80 0.9957 (floor ok True, SE 0.0035, structural 0.9996) · PIT max-dev 0.00384 (flat ok True) deciles [0.09948, 0.09714, 0.10306, 0.098, 0.10384, 0.09815, 0.10143, 0.10073, 0.10104, 0.09714] · CRPS 0.00436 vs nihilist 0.00436 · pred P(0) 0.995 vs real 0.9957 · n 12827

### WR|carries

- `climatology`: cov80 0.8998 (floor ok True, SE 0.0035, structural 0.99) · PIT max-dev 0.00774 (flat ok True) deciles [0.09831, 0.09979, 0.09854, 0.09581, 0.09971, 0.09729, 0.10018, 0.10205, 0.10057, 0.10774] · CRPS 0.12622 vs nihilist 0.13623 · pred P(0) 0.9077 vs real 0.8998 · n 12827

### WR|fumbles_lost

- `count_negbin`: cov80 0.988 (floor ok True, SE 0.0035, structural 0.9988) · PIT max-dev 0.01058 (flat ok True) deciles [0.09706, 0.09722, 0.10189, 0.10743, 0.10057, 0.08942, 0.1015, 0.09854, 0.10135, 0.10501] · CRPS 0.01217 vs nihilist 0.01225 · pred P(0) 0.9892 vs real 0.9878 · n 12827
- `climatology`: cov80 0.9878 (floor ok True, SE 0.0035, structural 0.9988) · PIT max-dev 0.00403 (flat ok True) deciles [0.09597, 0.09979, 0.10135, 0.10065, 0.09971, 0.0987, 0.09971, 0.0994, 0.10221, 0.10252] · CRPS 0.01215 vs nihilist 0.01225 · pred P(0) 0.9899 vs real 0.9878 · n 12827

### WR|passing_interceptions

- `climatology`: cov80 0.9995 (floor ok True, SE 0.0035, structural 1.0) · PIT max-dev 0.0038 (flat ok True) deciles [0.10166, 0.09722, 0.09948, 0.10275, 0.09909, 0.09948, 0.0962, 0.10197, 0.10221, 0.09995] · CRPS 0.00047 vs nihilist 0.00047 · pred P(0) 1.0 vs real 0.9995 · n 12827

### WR|passing_tds

- `climatology`: cov80 0.9993 (floor ok True, SE 0.0035, structural 0.9999) · PIT max-dev 0.0045 (flat ok True) deciles [0.10384, 0.09924, 0.10026, 0.1001, 0.1015, 0.09714, 0.0955, 0.0994, 0.10002, 0.10299] · CRPS 0.0007 vs nihilist 0.0007 · pred P(0) 1.0 vs real 0.9993 · n 12827

### WR|passing_yards

- `climatology`: cov80 0.9981 (floor ok True, SE 0.0035, structural 0.9998) · PIT max-dev 0.00434 (flat ok True) deciles [0.10322, 0.09698, 0.10041, 0.1033, 0.09714, 0.09761, 0.09566, 0.10416, 0.10034, 0.10119] · CRPS 0.03007 vs nihilist 0.03007 · pred P(0) 1.0 vs real 0.9981 · n 12827

### WR|receiving_tds

- `count_negbin`: cov80 0.9629 (floor ok True, SE 0.0035, structural 0.9867) · PIT max-dev 0.00645 (flat ok True) deciles [0.09792, 0.09488, 0.10189, 0.10111, 0.10353, 0.10018, 0.09355, 0.10345, 0.1026, 0.10088] · CRPS 0.12428 vs nihilist 0.15183 · pred P(0) 0.8715 vs real 0.867 · n 12827
- `climatology`: cov80 0.9828 (floor ok True, SE 0.0035, structural 0.9867) · PIT max-dev 0.00673 (flat ok True) deciles [0.10431, 0.0948, 0.09948, 0.09714, 0.10143, 0.10158, 0.10673, 0.1033, 0.09737, 0.09386] · CRPS 0.13454 vs nihilist 0.15183 · pred P(0) 0.8625 vs real 0.867 · n 12827

### WR|receptions

- `count_negbin`: cov80 0.9183 (floor ok True, SE 0.0035, structural 0.9409) · PIT max-dev 0.01276 (flat ok True) deciles [0.10985, 0.10143, 0.09698, 0.10369, 0.09753, 0.1072, 0.10252, 0.10143, 0.08724, 0.09215] · CRPS 0.86347 vs nihilist 1.99664 · pred P(0) 0.3597 vs real 0.4091 · n 12827
- `climatology`: cov80 0.9351 (floor ok True, SE 0.0035, structural 0.9409) · PIT max-dev 0.00855 (flat ok True) deciles [0.1033, 0.10189, 0.09893, 0.10073, 0.10782, 0.10805, 0.09987, 0.09457, 0.09145, 0.0934] · CRPS 1.26409 vs nihilist 1.99664 · pred P(0) 0.4014 vs real 0.4091 · n 12827

### WR|rushing_tds

- `climatology`: cov80 0.9942 (floor ok True, SE 0.0035, structural 0.9994) · PIT max-dev 0.00462 (flat ok True) deciles [0.1008, 0.10119, 0.1015, 0.09901, 0.09854, 0.09581, 0.09995, 0.09909, 0.09948, 0.10462] · CRPS 0.00583 vs nihilist 0.00583 · pred P(0) 0.9975 vs real 0.9942 · n 12827

### WR|rushing_yards

- `climatology`: cov80 0.9046 (floor ok True, SE 0.0035, structural 0.9905) · PIT max-dev 0.01066 (flat ok True) deciles [0.10634, 0.09839, 0.10041, 0.09956, 0.09901, 0.08934, 0.10377, 0.09885, 0.09885, 0.10548] · CRPS 0.85158 vs nihilist 0.8845 · pred P(0) 0.9259 vs real 0.9046 · n 12827

### WR|targets

- `count_negbin`: cov80 0.904 (floor ok True, SE 0.0035, structural 0.934) · PIT max-dev 0.01788 (flat ok True) deciles [0.11788, 0.09737, 0.10119, 0.10291, 0.10392, 0.10938, 0.10065, 0.09293, 0.09004, 0.08373] · CRPS 1.23667 vs nihilist 3.16579 · pred P(0) 0.2575 vs real 0.3398 · n 12827
- `climatology`: cov80 0.9318 (floor ok True, SE 0.0035, structural 0.934) · PIT max-dev 0.01253 (flat ok True) deciles [0.09729, 0.10049, 0.10299, 0.1125, 0.10548, 0.10322, 0.10384, 0.09729, 0.08747, 0.08942] · CRPS 1.89546 vs nihilist 3.16579 · pred P(0) 0.336 vs real 0.3398 · n 12827

### WR|two_pt

- `count_negbin`: cov80 0.9922 (floor ok True, SE 0.0035, structural 0.9992) · PIT max-dev 0.00322 (flat ok True) deciles [0.10034, 0.09698, 0.09823, 0.10275, 0.10182, 0.09839, 0.0987, 0.09831, 0.10322, 0.10127] · CRPS 0.00781 vs nihilist 0.00779 · pred P(0) 0.9951 vs real 0.9922 · n 12827
- `climatology`: cov80 0.9922 (floor ok True, SE 0.0035, structural 0.9992) · PIT max-dev 0.0061 (flat ok True) deciles [0.09831, 0.09729, 0.1001, 0.0987, 0.09846, 0.09948, 0.0994, 0.10135, 0.1008, 0.1061] · CRPS 0.00776 vs nihilist 0.00779 · pred P(0) 0.995 vs real 0.9922 · n 12827

## Pre-registration

- order: {'modeled': ['count_negbin', 'climatology'], 'minor': ['climatology']}; PIT max-decile-dev ≤ 0.03; coverage floor 0.8 (one-sided, 3.0 SE); cells = substrate − served (45).

_Runtime: 411.6s · seed 20260817 · matrix key 26c34fbe778c9d87_