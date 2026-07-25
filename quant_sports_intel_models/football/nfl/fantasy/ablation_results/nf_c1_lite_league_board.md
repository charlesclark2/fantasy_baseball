# NF-C1-lite — 2026 NFL league-config scoring + VOR boards (MVP-2)

**Engine:** `nfl_fantasy_league_board_v1` (sport-agnostic `fantasy_engine`) · **projection season:** 2026 · **generated:** 2026-07-25T07:03:02.205253+00:00

> 🧮 **Sections 1–3 below are shown at the 12-team reference size** (the modal redraft size); the boards are landed for every scored size — see §4 for the league-size effect. The board grain is (config_name, n_teams, player_id): league size is a normalized dimension, not part of the format name.

> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate. The gate is (1) SCORING CORRECTNESS (hand-calc match — see the fast-gate tests), (2) a TRANSPARENT replacement-level definition (the per-position demand tables below), and (3) FACE-VALID preset deltas (full-PPR lifts pass-catchers; superflex lifts QBs). We **RESCORE the MVP-1 raw stat line** per league — never the `proj_fp_*` convenience columns. Uncertainty is carried through the rescore as a coefficient-of-variation (a first-order interval, not a false-precise point); rookie intervals remain PARAMETER uncertainty and must be recalibrated before pricing.

## 1. Face validity — the preset deltas that prove the scarcity math

| preset    | best_QB    |   best_QB_overall_rank |   WR+TE_in_top10 |   RB_in_top10 |
|:----------|:-----------|-----------------------:|-----------------:|--------------:|
| standard  | JOSH ALLEN |                     17 |                0 |            10 |
| half_ppr  | JOSH ALLEN |                     20 |                3 |             7 |
| full_ppr  | JOSH ALLEN |                     26 |                4 |             6 |
| superflex | JOSH ALLEN |                      8 |                3 |             6 |

- ✅ **Superflex lifts QBs:** the best QB's overall rank should jump sharply from full-PPR to superflex (a QB-eligible SUPERFLEX slot roughly doubles QB starter demand → QB replacement drops → QB VOR rises). This is the direct check the flex-allocation math is right.
- ✅ **PPR lifts pass-catchers:** WR/TE representation in the top 10 should rise from standard → half → full PPR as receptions gain value.

## 2. Positional scarcity — the replacement-level definition (auditable)

Replacement level per position = the points of the FIRST non-startable player (the best player available for free). DEMAND = dedicated starter spots + the position's allocated share of the FLEX/SUPERFLEX pool (allocated greedily, most-restrictive slot first). VOR = league points − this replacement level.

### standard

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                  0.0 |
| K          |                   12 |                0 |              12 |                  0.0 |
| QB         |                   12 |                0 |              12 |                259.0 |
| RB         |                   24 |               11 |              35 |                 96.0 |
| TE         |                   12 |                0 |              12 |                 74.0 |
| WR         |                   24 |                1 |              25 |                 97.0 |

### full_ppr

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                  0.0 |
| K          |                   12 |                0 |              12 |                  0.0 |
| QB         |                   12 |                0 |              12 |                259.9 |
| RB         |                   24 |                5 |              29 |                135.5 |
| TE         |                   12 |                0 |              12 |                124.1 |
| WR         |                   24 |                7 |              31 |                135.5 |

### superflex

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                  0.0 |
| K          |                   12 |                0 |              12 |                  0.0 |
| QB         |                   12 |               12 |              24 |                205.2 |
| RB         |                   24 |                5 |              29 |                135.5 |
| TE         |                   12 |                0 |              12 |                124.1 |
| WR         |                   24 |                7 |              31 |                135.5 |

## 3. Ranked boards — top 20 by VOR

### standard

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | JONATHAN TAYLOR     | RB         |                 1 |         16.2 |           230.6 |                 96.0 | 134.6 |      60.8 |     208.3 |
|              2 | CHRISTIAN MCCAFFREY | RB         |                 2 |         16.2 |           226.3 |                 96.0 | 130.4 |      66.7 |     194.0 |
|              3 | JAHMYR GIBBS        | RB         |                 3 |         16.2 |           222.4 |                 96.0 | 126.5 |      53.8 |     199.1 |
|              4 | BIJAN ROBINSON      | RB         |                 4 |         16.2 |           213.8 |                 96.0 | 117.8 |      57.0 |     178.6 |
|              5 | DERRICK HENRY       | RB         |                 5 |         16.2 |           213.4 |                 96.0 | 117.5 |      52.6 |     182.2 |
|              6 | DE'VON ACHANE       | RB         |                 6 |         15.8 |           190.2 |                 96.0 |  94.2 |      45.2 |     143.2 |
|              7 | SAQUON BARKLEY      | RB         |                 7 |         16.2 |           189.3 |                 96.0 |  93.3 |      41.3 |     145.2 |
|              8 | JAMES COOK III      | RB         |                 8 |         16.2 |           187.2 |                 96.0 |  91.2 |      31.0 |     151.4 |
|              9 | KYREN WILLIAMS      | RB         |                 9 |         16.2 |           185.4 |                 96.0 |  89.4 |      37.3 |     141.4 |
|             10 | JOSH JACOBS         | RB         |                10 |         15.8 |           172.1 |                 96.0 |  76.1 |      21.1 |     131.1 |
|             11 | PUKA NACUA          | WR         |                 1 |         16.2 |           166.1 |                 97.0 |  69.1 |      14.5 |     123.7 |
|             12 | Jeremiyah Love      | RB         |                11 |         16.0 |           164.6 |                 96.0 |  68.6 |     -96.0 |     253.9 |
|             13 | JA'MARR CHASE       | WR         |                 2 |         15.8 |           164.8 |                 97.0 |  67.8 |      19.8 |     115.9 |
|             14 | AMON-RA ST. BROWN   | WR         |                 3 |         16.2 |           161.9 |                 97.0 |  64.9 |      16.0 |     113.9 |
|             15 | ASHTON JEANTY       | RB         |                12 |         16.2 |           155.1 |                 96.0 |  59.1 |      11.9 |     106.3 |
|             16 | CHASE BROWN         | RB         |                13 |         16.2 |           154.3 |                 96.0 |  58.4 |      15.4 |     101.3 |
|             17 | JOSH ALLEN          | QB         |                 1 |         16.5 |           314.1 |                259.0 |  55.0 |     -36.8 |     147.0 |
|             18 | BREECE HALL         | RB         |                14 |         15.8 |           150.9 |                 96.0 |  55.0 |      10.8 |      99.1 |
|             19 | TRAVIS ETIENNE JR.  | RB         |                15 |         16.2 |           148.5 |                 96.0 |  52.6 |       8.4 |      96.6 |
|             20 | DAVID MONTGOMERY    | RB         |                16 |         16.2 |           146.3 |                 96.0 |  50.4 |       8.1 |      92.5 |

### full_ppr

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | CHRISTIAN MCCAFFREY | RB         |                 1 |         16.2 |           293.9 |                135.5 | 158.4 |      75.8 |     241.0 |
|              2 | JAHMYR GIBBS        | RB         |                 2 |         16.2 |           274.7 |                135.5 | 139.1 |      49.4 |     228.9 |
|              3 | BIJAN ROBINSON      | RB         |                 3 |         16.2 |           269.1 |                135.5 | 133.6 |      57.1 |     210.1 |
|              4 | JONATHAN TAYLOR     | RB         |                 4 |         16.2 |           262.0 |                135.5 | 126.5 |      42.7 |     210.3 |
|              5 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           260.1 |                135.5 | 124.5 |      48.8 |     200.4 |
|              6 | PUKA NACUA          | WR         |                 2 |         16.2 |           257.6 |                135.5 | 122.1 |      37.5 |     206.8 |
|              7 | AMON-RA ST. BROWN   | WR         |                 3 |         16.2 |           254.3 |                135.5 | 118.7 |      41.9 |     195.6 |
|              8 | DE'VON ACHANE       | RB         |                 5 |         15.8 |           242.7 |                135.5 | 107.2 |      44.7 |     169.7 |
|              9 | DERRICK HENRY       | RB         |                 6 |         16.2 |           230.8 |                135.5 |  95.3 |      25.2 |     165.4 |
|             10 | TREY MCBRIDE        | TE         |                 1 |         16.2 |           210.8 |                124.1 |  86.7 |      25.6 |     147.8 |
|             11 | SAQUON BARKLEY      | RB         |                 7 |         16.2 |           221.0 |                135.5 |  85.5 |      24.9 |     146.2 |
|             12 | JAXON SMITH-NJIGBA  | WR         |                 4 |         16.2 |           216.4 |                135.5 |  80.9 |      11.4 |     150.5 |
|             13 | JAMES COOK III      | RB         |                 8 |         16.2 |           215.3 |                135.5 |  79.7 |      10.5 |     149.0 |
|             14 | KYREN WILLIAMS      | RB         |                 9 |         16.2 |           214.5 |                135.5 |  79.0 |      18.7 |     139.3 |
|             15 | Jeremiyah Love      | RB         |                10 |         16.0 |           208.4 |                135.5 |  72.9 |    -135.5 |     307.7 |
|             16 | JOSH JACOBS         | RB         |                11 |         15.8 |           203.1 |                135.5 |  67.5 |       2.6 |     132.5 |
|             17 | CEEDEE LAMB         | WR         |                 5 |         14.8 |           202.2 |                135.5 |  66.6 |       9.2 |     124.1 |
|             18 | CHASE BROWN         | RB         |                12 |         16.2 |           201.4 |                135.5 |  65.9 |       9.8 |     122.0 |
|             19 | JUSTIN JEFFERSON    | WR         |                 6 |         16.2 |           201.4 |                135.5 |  65.9 |      14.9 |     116.9 |
|             20 | ASHTON JEANTY       | RB         |                13 |         16.2 |           199.6 |                135.5 |  64.1 |       3.3 |     124.8 |

### superflex

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | CHRISTIAN MCCAFFREY | RB         |                 1 |         16.2 |           293.9 |                135.5 | 158.4 |      75.8 |     241.0 |
|              2 | JAHMYR GIBBS        | RB         |                 2 |         16.2 |           274.7 |                135.5 | 139.1 |      49.4 |     228.9 |
|              3 | BIJAN ROBINSON      | RB         |                 3 |         16.2 |           269.1 |                135.5 | 133.6 |      57.1 |     210.1 |
|              4 | JONATHAN TAYLOR     | RB         |                 4 |         16.2 |           262.0 |                135.5 | 126.5 |      42.7 |     210.3 |
|              5 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           260.1 |                135.5 | 124.5 |      48.8 |     200.4 |
|              6 | PUKA NACUA          | WR         |                 2 |         16.2 |           257.6 |                135.5 | 122.1 |      37.5 |     206.8 |
|              7 | AMON-RA ST. BROWN   | WR         |                 3 |         16.2 |           254.3 |                135.5 | 118.7 |      41.9 |     195.6 |
|              8 | JOSH ALLEN          | QB         |                 1 |         16.5 |           314.1 |                205.2 | 108.9 |      17.0 |     200.8 |
|              9 | DE'VON ACHANE       | RB         |                 5 |         15.8 |           242.7 |                135.5 | 107.2 |      44.7 |     169.7 |
|             10 | DERRICK HENRY       | RB         |                 6 |         16.2 |           230.8 |                135.5 |  95.3 |      25.2 |     165.4 |
|             11 | JALEN HURTS         | QB         |                 2 |         16.5 |           296.5 |                205.2 |  91.3 |      16.4 |     166.2 |
|             12 | TREY MCBRIDE        | TE         |                 1 |         16.2 |           210.8 |                124.1 |  86.7 |      25.6 |     147.8 |
|             13 | SAQUON BARKLEY      | RB         |                 7 |         16.2 |           221.0 |                135.5 |  85.5 |      24.9 |     146.2 |
|             14 | JAXON SMITH-NJIGBA  | WR         |                 4 |         16.2 |           216.4 |                135.5 |  80.9 |      11.4 |     150.5 |
|             15 | JAMES COOK III      | RB         |                 8 |         16.2 |           215.3 |                135.5 |  79.7 |      10.5 |     149.0 |
|             16 | KYREN WILLIAMS      | RB         |                 9 |         16.2 |           214.5 |                135.5 |  79.0 |      18.7 |     139.3 |
|             17 | JARED GOFF          | QB         |                 3 |         16.5 |           282.4 |                205.2 |  77.3 |       8.1 |     146.4 |
|             18 | DAK PRESCOTT        | QB         |                 4 |         16.5 |           281.1 |                205.2 |  75.9 |       4.6 |     147.2 |
|             19 | TREVOR LAWRENCE     | QB         |                 5 |         16.5 |           278.5 |                205.2 |  73.4 |      -2.3 |     149.0 |
|             20 | Jeremiyah Love      | RB         |                10 |         16.0 |           208.4 |                135.5 |  72.9 |    -135.5 |     307.7 |

## 4. League-size effect — size is a real dimension of value, not a label

For **full_ppr** across the scored league sizes: replacement level per position + the best QB's overall rank + the count of players carrying positive VOR. Fewer teams ⇒ shallower starter demand ⇒ a HIGHER replacement bar ⇒ fewer players with positive VOR. This is why the board grain includes `n_teams` — each size is a genuinely different value board off the same MVP-1 projections.

| format   |   n_teams |   QB_repl |   RB_repl |   WR_repl |   TE_repl |   best_QB_rank |   players_positive_VOR |
|:---------|----------:|----------:|----------:|----------:|----------:|---------------:|-----------------------:|
| full_ppr |        12 |     259.9 |     135.5 |     135.5 |     124.1 |             26 |                     84 |
| full_ppr |        10 |     262.0 |     143.9 |     144.7 |     126.0 |             21 |                     70 |

## 5. Limitations

- **Presets over the MVP-1 raw line** — the board is only as good as the MVP-1 projection it rescores; the within-tier ordering gap vs The Fantasy Footballers (RB/WR) carries through. NF-D2 closes it upstream.
- **K/DST carry no projection line** (MVP-1 is offensive skill players only) → those slots create no ranked players; the board covers QB/RB/WR/TE (FB folded into RB).
- **Uncertainty is a CV rescale**, not a per-format re-derived variance (no per-format game logs). Honest as a first-order interval; recalibrate rookie (parameter) intervals before pricing.
- **Manual formats only** — platform import (NF-C0) populates this SAME config object later; the config schema is the shared contract.

