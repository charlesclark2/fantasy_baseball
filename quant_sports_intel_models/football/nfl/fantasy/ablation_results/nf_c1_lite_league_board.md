# NF-C1-lite — 2026 NFL league-config scoring + VOR boards (MVP-2)

**Engine:** `nfl_fantasy_league_board_v1` (sport-agnostic `fantasy_engine`) · **projection season:** 2026 · **generated:** 2026-08-21T05:22:47.988645+00:00

> 🧮 **Sections 1–3 below are shown at the 12-team reference size** (the modal redraft size); the boards are landed for every scored size — see §4 for the league-size effect. The board grain is (config_name, n_teams, player_id): league size is a normalized dimension, not part of the format name.

> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate. The gate is (1) SCORING CORRECTNESS (hand-calc match — see the fast-gate tests), (2) a TRANSPARENT replacement-level definition (the per-position demand tables below), and (3) FACE-VALID preset deltas (full-PPR lifts pass-catchers; superflex lifts QBs). We **RESCORE the MVP-1 raw stat line** per league — never the `proj_fp_*` convenience columns. Uncertainty is carried through the rescore as a coefficient-of-variation (a first-order interval, not a false-precise point); rookie intervals remain PARAMETER uncertainty and must be recalibrated before pricing.

## 1. Face validity — the preset deltas that prove the scarcity math

| preset    | best_QB    |   best_QB_overall_rank |   WR+TE_in_top10 |   RB_in_top10 |
|:----------|:-----------|-----------------------:|-----------------:|--------------:|
| standard  | JOSH ALLEN |                     20 |                0 |            10 |
| half_ppr  | JOSH ALLEN |                     20 |                2 |             8 |
| full_ppr  | JOSH ALLEN |                     25 |                4 |             6 |
| superflex | JOSH ALLEN |                      7 |                3 |             5 |

- ✅ **Superflex lifts QBs:** the best QB's overall rank should jump sharply from full-PPR to superflex (a QB-eligible SUPERFLEX slot roughly doubles QB starter demand → QB replacement drops → QB VOR rises). This is the direct check the flex-allocation math is right.
- ✅ **PPR lifts pass-catchers:** WR/TE representation in the top 10 should rise from standard → half → full PPR as receptions gain value.

## 2. Positional scarcity — the replacement-level definition (auditable)

Replacement level per position = the points of the FIRST non-startable player (the best player available for free). DEMAND = dedicated starter spots + the position's allocated share of the FLEX/SUPERFLEX pool (allocated greedily, most-restrictive slot first). VOR = league points − this replacement level.

### standard

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                109.4 |
| K          |                   12 |                0 |              12 |                129.5 |
| QB         |                   12 |                0 |              12 |                248.4 |
| RB         |                   24 |                9 |              33 |                102.6 |
| TE         |                   12 |                0 |              12 |                 80.2 |
| WR         |                   24 |                3 |              27 |                101.7 |

### full_ppr

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                109.4 |
| K          |                   12 |                0 |              12 |                129.5 |
| QB         |                   12 |                0 |              12 |                248.4 |
| RB         |                   24 |                7 |              31 |                150.1 |
| TE         |                   12 |                0 |              12 |                130.4 |
| WR         |                   24 |                5 |              29 |                148.3 |

### superflex

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                109.4 |
| K          |                   12 |                0 |              12 |                129.5 |
| QB         |                   12 |               12 |              24 |                179.5 |
| RB         |                   24 |                7 |              31 |                150.1 |
| TE         |                   12 |                0 |              12 |                130.4 |
| WR         |                   24 |                5 |              29 |                148.3 |

## 3. Ranked boards — top 20 by VOR

### standard

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | JAHMYR GIBBS        | RB         |                 1 |         14.4 |           284.3 |                102.6 | 181.7 |     -18.3 |     181.8 |
|              2 | JONATHAN TAYLOR     | RB         |                 2 |         15.4 |           268.2 |                102.6 | 165.6 |     -11.0 |     204.6 |
|              3 | BIJAN ROBINSON      | RB         |                 3 |         15.2 |           250.0 |                102.6 | 147.4 |     -22.0 |     173.1 |
|              4 | CHRISTIAN MCCAFFREY | RB         |                 4 |         15.5 |           239.2 |                102.6 | 136.6 |     -22.4 |     166.2 |
|              5 | JAMES COOK III      | RB         |                 5 |         14.0 |           217.5 |                102.6 | 114.9 |     -14.6 |     185.1 |
|              6 | ASHTON JEANTY       | RB         |                 6 |         15.3 |           215.6 |                102.6 | 113.0 |     -24.6 |     157.4 |
|              7 | DE'VON ACHANE       | RB         |                 7 |         14.4 |           204.1 |                102.6 | 101.4 |     -23.3 |     161.3 |
|              8 | DERRICK HENRY       | RB         |                 8 |         14.0 |           204.0 |                102.6 | 101.3 |     -48.0 |     179.7 |
|              9 | SAQUON BARKLEY      | RB         |                 9 |         15.3 |           201.8 |                102.6 |  99.1 |     -32.2 |     180.4 |
|             10 | Jeremiyah Love      | RB         |                10 |         16.0 |           198.0 |                102.6 |  95.4 |     -77.6 |     212.7 |
|             11 | CHASE BROWN         | RB         |                11 |         14.2 |           191.6 |                102.6 |  88.9 |     -25.1 |     150.8 |
|             12 | KYREN WILLIAMS      | RB         |                12 |         15.1 |           189.1 |                102.6 |  86.5 |     -46.8 |     163.0 |
|             13 | KENNETH WALKER III  | RB         |                13 |         13.9 |           188.3 |                102.6 |  85.7 |     -41.5 |     168.5 |
|             14 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           183.0 |                101.7 |  81.3 |     -38.3 |     115.5 |
|             15 | PUKA NACUA          | WR         |                 2 |         15.1 |           176.3 |                101.7 |  74.6 |     -37.2 |     119.1 |
|             16 | OMARION HAMPTON     | RB         |                14 |         12.1 |           176.1 |                102.6 |  73.5 |     -45.4 |     153.2 |
|             17 | AMON-RA ST. BROWN   | WR         |                 3 |         15.8 |           168.2 |                101.7 |  66.5 |     -36.3 |     117.2 |
|             18 | JOSH JACOBS         | RB         |                15 |         14.2 |           166.0 |                102.6 |  63.4 |     -67.1 |     134.3 |
|             19 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           138.2 |                 80.2 |  58.0 |     -41.4 |      58.1 |
|             20 | JOSH ALLEN          | QB         |                 1 |         16.5 |           305.2 |                248.4 |  56.8 |    -116.6 |     202.4 |

### full_ppr

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | JAHMYR GIBBS        | RB         |                 1 |         14.4 |           350.8 |                150.1 | 200.6 |     -46.0 |     200.7 |
|              2 | BIJAN ROBINSON      | RB         |                 2 |         15.2 |           314.5 |                150.1 | 164.4 |     -48.8 |     196.7 |
|              3 | CHRISTIAN MCCAFFREY | RB         |                 3 |         15.5 |           310.3 |                150.1 | 160.2 |     -46.1 |     198.5 |
|              4 | JONATHAN TAYLOR     | RB         |                 4 |         15.4 |           304.6 |                150.1 | 154.5 |     -46.0 |     198.8 |
|              5 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           288.3 |                148.3 | 140.0 |     -48.3 |     193.9 |
|              6 | ASHTON JEANTY       | RB         |                 5 |         15.3 |           277.3 |                150.1 | 127.2 |     -49.8 |     184.1 |
|              7 | PUKA NACUA          | WR         |                 2 |         15.1 |           273.0 |                148.3 | 124.7 |     -48.3 |     193.8 |
|              8 | AMON-RA ST. BROWN   | WR         |                 3 |         15.8 |           263.8 |                148.3 | 115.4 |     -45.8 |     194.9 |
|              9 | DE'VON ACHANE       | RB         |                 6 |         14.4 |           260.1 |                150.1 | 110.0 |     -49.0 |     186.3 |
|             10 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           239.0 |                130.4 | 108.7 |     -63.2 |     108.8 |
|             11 | Jeremiyah Love      | RB         |                 7 |         16.0 |           250.6 |                150.1 | 100.5 |    -118.5 |     249.1 |
|             12 | JAMES COOK III      | RB         |                 8 |         14.0 |           250.0 |                150.1 |  99.9 |     -49.0 |     180.5 |
|             13 | CHASE BROWN         | RB         |                 9 |         14.2 |           249.8 |                150.1 |  99.7 |     -49.0 |     180.3 |
|             14 | SAQUON BARKLEY      | RB         |                10 |         15.3 |           235.5 |                150.1 |  85.4 |     -67.9 |     180.1 |
|             15 | KENNETH WALKER III  | RB         |                11 |         13.9 |           232.0 |                150.1 |  81.9 |     -74.8 |     183.9 |
|             16 | OMARION HAMPTON     | RB         |                12 |         12.1 |           229.0 |                150.1 |  78.9 |     -75.7 |     182.5 |
|             17 | JAXON SMITH-NJIGBA  | WR         |                 4 |         15.3 |           224.7 |                148.3 |  76.3 |     -48.6 |     181.2 |
|             18 | CEEDEE LAMB         | WR         |                 5 |         14.4 |           220.8 |                148.3 |  72.5 |     -49.0 |     178.6 |
|             19 | DERRICK HENRY       | RB         |                13 |         14.0 |           220.5 |                150.1 |  70.4 |     -91.1 |     155.1 |
|             20 | DRAKE LONDON        | WR         |                 6 |         14.4 |           217.7 |                148.3 |  69.3 |     -48.6 |     177.4 |

### superflex

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | JAHMYR GIBBS        | RB         |                 1 |         14.4 |           350.8 |                150.1 | 200.6 |     -46.0 |     200.7 |
|              2 | BIJAN ROBINSON      | RB         |                 2 |         15.2 |           314.5 |                150.1 | 164.4 |     -48.8 |     196.7 |
|              3 | CHRISTIAN MCCAFFREY | RB         |                 3 |         15.5 |           310.3 |                150.1 | 160.2 |     -46.1 |     198.5 |
|              4 | JONATHAN TAYLOR     | RB         |                 4 |         15.4 |           304.6 |                150.1 | 154.5 |     -46.0 |     198.8 |
|              5 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           288.3 |                148.3 | 140.0 |     -48.3 |     193.9 |
|              6 | ASHTON JEANTY       | RB         |                 5 |         15.3 |           277.3 |                150.1 | 127.2 |     -49.8 |     184.1 |
|              7 | JOSH ALLEN          | QB         |                 1 |         16.5 |           305.2 |                179.5 | 125.7 |     -47.7 |     271.3 |
|              8 | PUKA NACUA          | WR         |                 2 |         15.1 |           273.0 |                148.3 | 124.7 |     -48.3 |     193.8 |
|              9 | LAMAR JACKSON       | QB         |                 2 |         14.5 |           298.3 |                179.5 | 118.7 |     -44.5 |     273.2 |
|             10 | AMON-RA ST. BROWN   | WR         |                 3 |         15.8 |           263.8 |                148.3 | 115.4 |     -45.8 |     194.9 |
|             11 | DRAKE MAYE          | QB         |                 3 |         16.5 |           292.1 |                179.5 | 112.5 |     -44.5 |     271.0 |
|             12 | DE'VON ACHANE       | RB         |                 6 |         14.4 |           260.1 |                150.1 | 110.0 |     -49.0 |     186.3 |
|             13 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           239.0 |                130.4 | 108.7 |     -63.2 |     108.8 |
|             14 | Jeremiyah Love      | RB         |                 7 |         16.0 |           250.6 |                150.1 | 100.5 |    -118.5 |     249.1 |
|             15 | JAMES COOK III      | RB         |                 8 |         14.0 |           250.0 |                150.1 |  99.9 |     -49.0 |     180.5 |
|             16 | CHASE BROWN         | RB         |                 9 |         14.2 |           249.8 |                150.1 |  99.7 |     -49.0 |     180.3 |
|             17 | JOE BURROW          | QB         |                 4 |         12.0 |           276.9 |                179.5 |  97.4 |     -44.1 |     257.6 |
|             18 | JAYDEN DANIELS      | QB         |                 5 |         11.5 |           276.5 |                179.5 |  97.0 |     -44.3 |     256.9 |
|             19 | JALEN HURTS         | QB         |                 6 |         16.5 |           271.1 |                179.5 |  91.6 |     -47.8 |     257.3 |
|             20 | Fernando Mendoza    | QB         |                 7 |         12.4 |           270.2 |                179.5 |  90.7 |    -131.8 |     296.8 |

## 4. League-size effect — size is a real dimension of value, not a label

For **full_ppr** across the scored league sizes: replacement level per position + the best QB's overall rank + the count of players carrying positive VOR. Fewer teams ⇒ shallower starter demand ⇒ a HIGHER replacement bar ⇒ fewer players with positive VOR. This is why the board grain includes `n_teams` — each size is a genuinely different value board off the same MVP-1 projections.

| format   |   n_teams |   QB_repl |   RB_repl |   WR_repl |   TE_repl |   best_QB_rank |   players_positive_VOR |
|:---------|----------:|----------:|----------:|----------:|----------:|---------------:|-----------------------:|
| full_ppr |        12 |     248.4 |     150.1 |     148.3 |     130.4 |             25 |                    108 |
| full_ppr |        10 |     254.0 |     163.0 |     163.1 |     132.1 |             24 |                     90 |

## 5. Limitations

- **Presets over the MVP-1 raw line** — the board is only as good as the MVP-1 projection it rescores; the within-tier ordering gap vs The Fantasy Footballers (RB/WR) carries through. NF-D2 closes it upstream.
- **K/DST are now projected, but by a deliberately BASE model (NF1.6)** — those slots RANK instead of rendering "not projected", scored off raw components (distance-bucketed FG; DST takeaways plus a per-game points-allowed TIER expressed exactly as expected-games-per-bucket). ⚠️ K and DST are the LEAST predictable fantasy positions: held-out rank correlation is ~0.32 for DST and ~0.23 among startable kickers, so read those two slots as **streaming tiers, not fine ranks**, and read the wide intervals as the honest part. The board covers QB/RB/WR/TE (FB folded into RB) + K/DST.
- **Uncertainty is a CV rescale**, not a per-format re-derived variance (no per-format game logs). Honest as a first-order interval; recalibrate rookie (parameter) intervals before pricing.
- **Manual formats only** — platform import (NF-C0) populates this SAME config object later; the config schema is the shared contract.

