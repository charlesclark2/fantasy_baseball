# NF-ROS1b amendment 3 — the RB-rookie C9 read

Generated 2026-09-18T02:12:54+00:00 · commit `e702a625` · winner `eb_rate_avail` · rule declared in `nf_ros1b_preregistration_amendment_3.md` before this number existed.

**Decision: `STOP_TO_PM`** (bar ≤ 0.05).

| stratum | rows | player-seasons | PIT max-decile dev | cov80 |
|---|---|---|---|---|
| RB rookie | 1464 | 122 | 0.08101092896174864 | 0.7636612021857924 |
| RB veteran (context only) | 11676 | 973 | 0.012041795135320318 | 0.8704179513532031 |

Design quantity (amendment 3, computed before this read): under a perfectly calibrated predictive the statistic exceeds 0.05 with probability ≈ 0.000 if rows were independent and ≈ 0.51 if a player-season's 12 rows shared one PIT value.

RB-rookie decile shares: [0.09, 0.079, 0.07, 0.077, 0.092, 0.105, 0.079, 0.098, 0.13, 0.181]

---

## Amendment 5 — the per-player spread (descriptive; gates nothing)

✅ Reproduces the prior read exactly — `pit_max_decile_dev` 0.08101092896174864, decision `STOP_TO_PM` — so the spread below describes the same reading the rule already fired on.

The excess sits in the top decile. Of 265 rookie rows there, 54 distinct player-seasons contribute; the ten largest contributors carry 37.7% of them, and 1 player-season(s) sit entirely inside it.

Per-player-season mean PIT: median 0.594, mean 0.567, with 77 of 122 above 0.5 (veteran control: median 0.435, 403 of 973 above 0.5).

Decile shares in SEs of a calibrated predictive, under both dependence readings (amendment 3's framing, extended from the maximum to the shape):

| decile | rookie share | z (rows independent) | z (fully clustered) | veteran share |
|---|---|---|---|---|
| 1 | 0.090 | -1.25 | -0.36 | 0.104 |
| 2 | 0.079 | -2.74 | -0.79 | 0.100 |
| 3 | 0.070 | -3.87 | -1.12 | 0.103 |
| 4 | 0.077 | -2.91 | -0.84 | 0.106 |
| 5 | 0.092 | -1.08 | -0.31 | 0.103 |
| 6 | 0.105 | +0.66 | +0.19 | 0.104 |
| 7 | 0.079 | -2.65 | -0.76 | 0.103 |
| 8 | 0.098 | -0.30 | -0.09 | 0.096 |
| 9 | 0.130 | +3.80 | +1.10 | 0.094 |
| 10 | 0.181 | +10.33 | +2.98 | 0.088 |

⛔ No threshold for 'few' versus 'broad' is declared here. The disposition is the PM's (amendment 3 / PM R2): a disclosed rookie-stratum note, or rookie rows served as a stated absence.
