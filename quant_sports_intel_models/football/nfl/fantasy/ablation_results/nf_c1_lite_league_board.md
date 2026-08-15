# NF-C1-lite — 2026 NFL league-config scoring + VOR boards (MVP-2)

**Engine:** `nfl_fantasy_league_board_v1` (sport-agnostic `fantasy_engine`) · **projection season:** 2026 · **generated:** 2026-08-15T07:06:41.406973+00:00

> 🧮 **Sections 1–3 below are shown at the 12-team reference size** (the modal redraft size); the boards are landed for every scored size — see §4 for the league-size effect. The board grain is (config_name, n_teams, player_id): league size is a normalized dimension, not part of the format name.

> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate. The gate is (1) SCORING CORRECTNESS (hand-calc match — see the fast-gate tests), (2) a TRANSPARENT replacement-level definition (the per-position demand tables below), and (3) FACE-VALID preset deltas (full-PPR lifts pass-catchers; superflex lifts QBs). We **RESCORE the MVP-1 raw stat line** per league — never the `proj_fp_*` convenience columns. Uncertainty is carried through the rescore as a coefficient-of-variation (a first-order interval, not a false-precise point); rookie intervals remain PARAMETER uncertainty and must be recalibrated before pricing.

## 1. Face validity — the preset deltas that prove the scarcity math

| preset    | best_QB    |   best_QB_overall_rank |   WR+TE_in_top10 |   RB_in_top10 |
|:----------|:-----------|-----------------------:|-----------------:|--------------:|
| standard  | JOSH ALLEN |                     15 |                0 |            10 |
| half_ppr  | JOSH ALLEN |                     16 |                3 |             7 |
| full_ppr  | JOSH ALLEN |                     18 |                4 |             6 |
| superflex | JOSH ALLEN |                      2 |                3 |             4 |

- ✅ **Superflex lifts QBs:** the best QB's overall rank should jump sharply from full-PPR to superflex (a QB-eligible SUPERFLEX slot roughly doubles QB starter demand → QB replacement drops → QB VOR rises). This is the direct check the flex-allocation math is right.
- ✅ **PPR lifts pass-catchers:** WR/TE representation in the top 10 should rise from standard → half → full PPR as receptions gain value.

## 2. Positional scarcity — the replacement-level definition (auditable)

Replacement level per position = the points of the FIRST non-startable player (the best player available for free). DEMAND = dedicated starter spots + the position's allocated share of the FLEX/SUPERFLEX pool (allocated greedily, most-restrictive slot first). VOR = league points − this replacement level.

### standard

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                109.4 |
| K          |                   12 |                0 |              12 |                129.5 |
| QB         |                   12 |                0 |              12 |                267.6 |
| RB         |                   24 |                9 |              33 |                 85.5 |
| TE         |                   12 |                0 |              12 |                 72.2 |
| WR         |                   24 |                3 |              27 |                 92.4 |

### full_ppr

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                109.4 |
| K          |                   12 |                0 |              12 |                129.5 |
| QB         |                   12 |                0 |              12 |                267.6 |
| RB         |                   24 |                1 |              25 |                130.2 |
| TE         |                   12 |                0 |              12 |                117.3 |
| WR         |                   24 |               11 |              35 |                131.4 |

### superflex

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                109.4 |
| K          |                   12 |                0 |              12 |                129.5 |
| QB         |                   12 |               12 |              24 |                193.2 |
| RB         |                   24 |                1 |              25 |                130.2 |
| TE         |                   12 |                0 |              12 |                117.3 |
| WR         |                   24 |               11 |              35 |                131.4 |

## 3. Ranked boards — top 20 by VOR

### standard

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | JAHMYR GIBBS        | RB         |                 1 |         14.4 |           227.8 |                 85.5 | 142.4 |      -1.2 |     197.3 |
|              2 | JONATHAN TAYLOR     | RB         |                 2 |         15.4 |           214.9 |                 85.5 | 129.4 |       6.1 |     221.7 |
|              3 | BIJAN ROBINSON      | RB         |                 3 |         15.2 |           197.6 |                 85.5 | 112.1 |      -2.9 |     191.5 |
|              4 | CHRISTIAN MCCAFFREY | RB         |                 4 |         15.5 |           194.4 |                 85.5 | 108.9 |      -7.4 |     182.0 |
|              5 | JAMES COOK III      | RB         |                 5 |         14.0 |           174.3 |                 85.5 |  88.8 |       2.5 |     202.2 |
|              6 | ASHTON JEANTY       | RB         |                 6 |         15.3 |           172.8 |                 85.5 |  87.3 |      -7.5 |     174.5 |
|              7 | DERRICK HENRY       | RB         |                 7 |         14.0 |           172.2 |                 85.5 |  86.7 |     -15.8 |     223.9 |
|              8 | Jeremiyah Love      | RB         |                 8 |         16.0 |           165.0 |                 85.5 |  79.6 |     -59.8 |     211.9 |
|              9 | DE'VON ACHANE       | RB         |                 9 |         14.4 |           163.5 |                 85.5 |  78.0 |      -6.2 |     178.4 |
|             10 | SAQUON BARKLEY      | RB         |                10 |         15.3 |           161.7 |                 85.5 |  76.2 |     -15.1 |     197.5 |
|             11 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           166.3 |                 92.4 |  73.9 |     -29.0 |     124.8 |
|             12 | CHASE BROWN         | RB         |                11 |         14.2 |           153.5 |                 85.5 |  68.0 |      -8.0 |     167.9 |
|             13 | PUKA NACUA          | WR         |                 2 |         15.1 |           160.2 |                 92.4 |  67.8 |     -27.9 |     128.4 |
|             14 | KYREN WILLIAMS      | RB         |                12 |         15.1 |           151.5 |                 85.5 |  66.1 |     -29.7 |     180.1 |
|             15 | JOSH ALLEN          | QB         |                 1 |         16.5 |           328.6 |                267.6 |  61.0 |    -135.8 |     183.2 |
|             16 | AMON-RA ST. BROWN   | WR         |                 3 |         15.8 |           152.9 |                 92.4 |  60.5 |     -27.0 |     126.5 |
|             17 | KENNETH WALKER III  | RB         |                13 |         13.9 |           143.2 |                 85.5 |  57.7 |     -37.7 |     161.8 |
|             18 | OMARION HAMPTON     | RB         |                14 |         12.1 |           141.1 |                 85.5 |  55.6 |     -28.3 |     170.3 |
|             19 | LAMAR JACKSON       | QB         |                 2 |         14.5 |           321.1 |                267.6 |  53.5 |    -132.6 |     185.1 |
|             20 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           124.4 |                 72.2 |  52.2 |     -33.4 |      63.2 |

### full_ppr

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | JAHMYR GIBBS        | RB         |                 1 |         14.4 |           281.1 |                130.2 | 150.8 |     -26.1 |     218.6 |
|              2 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           262.0 |                131.4 | 130.7 |     -31.4 |     210.8 |
|              3 | CHRISTIAN MCCAFFREY | RB         |                 2 |         15.5 |           252.2 |                130.2 | 121.9 |     -28.8 |     216.8 |
|              4 | BIJAN ROBINSON      | RB         |                 3 |         15.2 |           248.5 |                130.2 | 118.3 |     -26.3 |     218.2 |
|              5 | PUKA NACUA          | WR         |                 2 |         15.1 |           248.2 |                131.4 | 116.8 |     -31.4 |     210.7 |
|              6 | JONATHAN TAYLOR     | RB         |                 4 |         15.4 |           244.1 |                130.2 | 113.8 |     -26.1 |     218.7 |
|              7 | AMON-RA ST. BROWN   | WR         |                 3 |         15.8 |           239.7 |                131.4 | 108.4 |     -28.9 |     211.8 |
|              8 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           215.0 |                117.3 |  97.8 |     -50.1 |     116.8 |
|              9 | ASHTON JEANTY       | RB         |                 5 |         15.3 |           222.2 |                130.2 |  91.9 |     -29.9 |     204.0 |
|             10 | Jeremiyah Love      | RB         |                 6 |         16.0 |           208.9 |                130.2 |  78.7 |     -97.7 |     246.3 |
|             11 | DE'VON ACHANE       | RB         |                 7 |         14.4 |           208.5 |                130.2 |  78.2 |     -29.1 |     206.2 |
|             12 | JAXON SMITH-NJIGBA  | WR         |                 4 |         15.3 |           204.2 |                131.4 |  72.8 |     -31.7 |     198.1 |
|             13 | JAMES COOK III      | RB         |                 8 |         14.0 |           200.3 |                130.2 |  70.1 |     -29.1 |     200.4 |
|             14 | CHASE BROWN         | RB         |                 9 |         14.2 |           200.2 |                130.2 |  69.9 |     -29.1 |     200.2 |
|             15 | CEEDEE LAMB         | WR         |                 5 |         14.4 |           200.7 |                131.4 |  69.3 |     -32.1 |     195.5 |
|             16 | DRAKE LONDON        | WR         |                 6 |         14.4 |           197.8 |                131.4 |  66.5 |     -31.7 |     194.3 |
|             17 | JUSTIN JEFFERSON    | WR         |                 7 |         16.2 |           196.4 |                131.4 |  65.0 |     -30.0 |     194.1 |
|             18 | JOSH ALLEN          | QB         |                 1 |         16.5 |           328.6 |                267.6 |  61.0 |    -135.8 |     183.2 |
|             19 | Jordyn Tyson        | WR         |                 8 |         13.6 |           191.9 |                131.4 |  60.5 |    -112.9 |     200.3 |
|             20 | SAQUON BARKLEY      | RB         |                10 |         15.3 |           188.7 |                130.2 |  58.5 |     -48.0 |     200.0 |

### superflex

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | JAHMYR GIBBS        | RB         |                 1 |         14.4 |           281.1 |                130.2 | 150.8 |     -26.1 |     218.6 |
|              2 | JOSH ALLEN          | QB         |                 1 |         16.5 |           328.6 |                193.2 | 135.4 |     -61.4 |     257.6 |
|              3 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           262.0 |                131.4 | 130.7 |     -31.4 |     210.8 |
|              4 | LAMAR JACKSON       | QB         |                 2 |         14.5 |           321.1 |                193.2 | 128.0 |     -58.2 |     259.5 |
|              5 | CHRISTIAN MCCAFFREY | RB         |                 2 |         15.5 |           252.2 |                130.2 | 121.9 |     -28.8 |     216.8 |
|              6 | DRAKE MAYE          | QB         |                 3 |         16.5 |           314.5 |                193.2 | 121.3 |     -58.2 |     257.3 |
|              7 | BIJAN ROBINSON      | RB         |                 3 |         15.2 |           248.5 |                130.2 | 118.3 |     -26.3 |     218.2 |
|              8 | PUKA NACUA          | WR         |                 2 |         15.1 |           248.2 |                131.4 | 116.8 |     -31.4 |     210.7 |
|              9 | JONATHAN TAYLOR     | RB         |                 4 |         15.4 |           244.1 |                130.2 | 113.8 |     -26.1 |     218.7 |
|             10 | AMON-RA ST. BROWN   | WR         |                 3 |         15.8 |           239.7 |                131.4 | 108.4 |     -28.9 |     211.8 |
|             11 | JOE BURROW          | QB         |                 4 |         12.0 |           298.2 |                193.2 | 105.0 |     -57.8 |     243.9 |
|             12 | JAYDEN DANIELS      | QB         |                 5 |         11.5 |           297.7 |                193.2 | 104.5 |     -58.0 |     243.2 |
|             13 | JALEN HURTS         | QB         |                 6 |         16.5 |           291.9 |                193.2 |  98.7 |     -61.5 |     243.6 |
|             14 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           215.0 |                117.3 |  97.8 |     -50.1 |     116.8 |
|             15 | CALEB WILLIAMS      | QB         |                 7 |         16.5 |           287.3 |                193.2 |  94.1 |     -63.0 |     240.7 |
|             16 | ASHTON JEANTY       | RB         |                 5 |         15.3 |           222.2 |                130.2 |  91.9 |     -29.9 |     204.0 |
|             17 | JUSTIN HERBERT      | QB         |                 8 |         16.5 |           284.9 |                193.2 |  91.7 |     -61.9 |     237.2 |
|             18 | TREVOR LAWRENCE     | QB         |                 9 |         16.5 |           280.2 |                193.2 |  87.0 |     -67.5 |     234.7 |
|             19 | DAK PRESCOTT        | QB         |                10 |         16.5 |           273.5 |                193.2 |  80.3 |     -61.5 |     241.1 |
|             20 | JAXSON DART         | QB         |                11 |         15.0 |           271.9 |                193.2 |  78.7 |     -59.4 |     243.1 |

## 4. League-size effect — size is a real dimension of value, not a label

For **full_ppr** across the scored league sizes: replacement level per position + the best QB's overall rank + the count of players carrying positive VOR. Fewer teams ⇒ shallower starter demand ⇒ a HIGHER replacement bar ⇒ fewer players with positive VOR. This is why the board grain includes `n_teams` — each size is a genuinely different value board off the same MVP-1 projections.

| format   |   n_teams |   QB_repl |   RB_repl |   WR_repl |   TE_repl |   best_QB_rank |   players_positive_VOR |
|:---------|----------:|----------:|----------:|----------:|----------:|---------------:|-----------------------:|
| full_ppr |        12 |     267.6 |     130.2 |     131.4 |     117.3 |             18 |                    108 |
| full_ppr |        10 |     271.9 |     132.6 |     134.8 |     118.9 |             19 |                     90 |

## 5. Limitations

- **Presets over the MVP-1 raw line** — the board is only as good as the MVP-1 projection it rescores; the within-tier ordering gap vs The Fantasy Footballers (RB/WR) carries through. NF-D2 closes it upstream.
- **K/DST are now projected, but by a deliberately BASE model (NF1.6)** — those slots RANK instead of rendering "not projected", scored off raw components (distance-bucketed FG; DST takeaways plus a per-game points-allowed TIER expressed exactly as expected-games-per-bucket). ⚠️ K and DST are the LEAST predictable fantasy positions: held-out rank correlation is ~0.32 for DST and ~0.23 among startable kickers, so read those two slots as **streaming tiers, not fine ranks**, and read the wide intervals as the honest part. The board covers QB/RB/WR/TE (FB folded into RB) + K/DST.
- **Uncertainty is a CV rescale**, not a per-format re-derived variance (no per-format game logs). Honest as a first-order interval; recalibrate rookie (parameter) intervals before pricing.
- **Manual formats only** — platform import (NF-C0) populates this SAME config object later; the config schema is the shared contract.

