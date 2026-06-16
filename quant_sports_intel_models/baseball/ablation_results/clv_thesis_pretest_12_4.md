# Story 12.4 — CLV thesis pre-test

**Question:** does the market-blind MORNING model edge predict open→close CLV (the line moving toward our side)?

**Verdict:** SIGNAL — the market-blind morning H2H edge predicts open→close CLV (Pearson +0.216, 95% CI [0.1114, 0.3229], n=959). The morning model anticipates line movement ⇒ the Epic-12 market-meta model is worth building. Totals weaker (r=+0.082).

Paired games: 968 (2026 live morning predictions ⋈ Bovada open→close movement, snapshot_count>1). Edge measured vs the OPEN line; CLV = pregame−open line movement.

## H2H
- n = 959
- Pearson r = **+0.2164** (95% CI [0.1114, 0.3229], p=1.3e-11)
- Spearman r = +0.2436 (p=2.0e-14)
- Directional hit (centered, moved-only) = 0.604 (n_moved=907)
- CLV top-edge decile = +0.0396; bottom-edge decile = -0.0087
- By source (n, r): {'historical': (891, 0.2021), 'live': (68, 0.4458)}
- CLV by edge quintile (Q1→Q5 should rise):
  - Q1: -0.0107 (n=192)
  - Q2: +0.0016 (n=192)
  - Q3: +0.0020 (n=191)
  - Q4: +0.0110 (n=192)
  - Q5: +0.0230 (n=192)

## Totals
- n = 897
- Pearson r = **+0.0818** (95% CI [0.0034, 0.166], p=1.4e-02)
- Spearman r = +0.1390 (p=3.0e-05)
- Directional hit (centered, moved-only) = 0.610 (n_moved=431)
- CLV top-edge decile = +0.0000; bottom-edge decile = -0.0611
- By source (n, r): {'historical': (874, 0.0836)}
- CLV by edge quintile (Q1→Q5 should rise):
  - Q1: -0.0722 (n=180)
  - Q2: -0.1564 (n=179)
  - Q3: +0.0084 (n=179)
  - Q4: +0.1397 (n=179)
  - Q5: +0.0944 (n=180)

## Caveats
- `h2h_edge` uses `open_home_win_prob` (carries vig — the mart stores only the home implied prob, so a true de-vig isn't possible yet); correlation is vig-robust, the directional hit uses the MEDIAN-CENTERED edge to neutralize the constant bias.
- Mean-reversion is not controlled; a positive corr is consistent with (not proof of) the morning model carrying leading information. A sharp-anchor control is the 12.4 follow-up.