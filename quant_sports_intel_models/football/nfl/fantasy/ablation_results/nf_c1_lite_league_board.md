# NF-C1-lite — 2026 NFL league-config scoring + VOR boards (MVP-2)

**Engine:** `nfl_fantasy_league_board_v1` (sport-agnostic `fantasy_engine`) · **projection season:** 2026 · **generated:** 2026-08-17T04:31:57.440938+00:00

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
| QB         |                   12 |                0 |              12 |                248.5 |
| RB         |                   24 |               11 |              35 |                103.9 |
| TE         |                   12 |                0 |              12 |                 80.2 |
| WR         |                   24 |                1 |              25 |                104.5 |

### full_ppr

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                109.4 |
| K          |                   12 |                0 |              12 |                129.5 |
| QB         |                   12 |                0 |              12 |                248.5 |
| RB         |                   24 |                7 |              31 |                150.1 |
| TE         |                   12 |                0 |              12 |                130.4 |
| WR         |                   24 |                5 |              29 |                148.3 |

### superflex

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                109.4 |
| K          |                   12 |                0 |              12 |                129.5 |
| QB         |                   12 |               12 |              24 |                179.4 |
| RB         |                   24 |                7 |              31 |                150.1 |
| TE         |                   12 |                0 |              12 |                130.4 |
| WR         |                   24 |                5 |              29 |                148.3 |

## 3. Ranked boards — top 20 by VOR

### standard

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | JAHMYR GIBBS        | RB         |                 1 |         14.4 |           284.3 |                103.9 | 180.4 |     -19.6 |     180.5 |
|              2 | JONATHAN TAYLOR     | RB         |                 2 |         15.4 |           268.2 |                103.9 | 164.2 |     -12.3 |     203.3 |
|              3 | BIJAN ROBINSON      | RB         |                 3 |         15.2 |           246.6 |                103.9 | 142.6 |     -21.3 |     173.1 |
|              4 | CHRISTIAN MCCAFFREY | RB         |                 4 |         15.5 |           242.6 |                103.9 | 138.6 |     -25.8 |     163.6 |
|              5 | JAMES COOK III      | RB         |                 5 |         14.0 |           217.5 |                103.9 | 113.5 |     -15.9 |     183.8 |
|              6 | ASHTON JEANTY       | RB         |                 6 |         15.3 |           215.6 |                103.9 | 111.7 |     -25.9 |     156.1 |
|              7 | DE'VON ACHANE       | RB         |                 7 |         14.4 |           204.1 |                103.9 | 100.1 |     -24.6 |     160.0 |
|              8 | DERRICK HENRY       | RB         |                 8 |         14.0 |           204.0 |                103.9 | 100.0 |     -49.3 |     178.4 |
|              9 | SAQUON BARKLEY      | RB         |                 9 |         15.3 |           201.8 |                103.9 |  97.8 |     -33.5 |     179.1 |
|             10 | CHASE BROWN         | RB         |                10 |         14.2 |           191.6 |                103.9 |  87.6 |     -26.4 |     149.5 |
|             11 | KYREN WILLIAMS      | RB         |                11 |         15.1 |           189.1 |                103.9 |  85.2 |     -48.1 |     161.7 |
|             12 | KENNETH WALKER III  | RB         |                12 |         13.9 |           188.3 |                103.9 |  84.3 |     -42.8 |     167.2 |
|             13 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           183.0 |                104.5 |  78.4 |     -41.1 |     112.7 |
|             14 | OMARION HAMPTON     | RB         |                13 |         12.1 |           176.1 |                103.9 |  72.2 |     -46.7 |     151.9 |
|             15 | PUKA NACUA          | WR         |                 2 |         15.1 |           176.3 |                104.5 |  71.7 |     -40.0 |     116.3 |
|             16 | AMON-RA ST. BROWN   | WR         |                 3 |         15.8 |           168.2 |                104.5 |  63.7 |     -39.1 |     114.4 |
|             17 | JOSH JACOBS         | RB         |                14 |         14.2 |           166.0 |                103.9 |  62.1 |     -68.4 |     133.0 |
|             18 | Jeremiyah Love      | RB         |                15 |         16.0 |           165.0 |                103.9 |  61.1 |     -78.2 |     193.5 |
|             19 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           138.2 |                 80.2 |  58.0 |     -41.4 |      58.1 |
|             20 | JOSH ALLEN          | QB         |                 1 |         16.5 |           305.2 |                248.5 |  56.7 |    -116.7 |     202.3 |

### full_ppr

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | JAHMYR GIBBS        | RB         |                 1 |         14.4 |           350.8 |                150.1 | 200.6 |     -46.0 |     200.7 |
|              2 | CHRISTIAN MCCAFFREY | RB         |                 2 |         15.5 |           314.7 |                150.1 | 164.6 |     -48.7 |     196.9 |
|              3 | BIJAN ROBINSON      | RB         |                 3 |         15.2 |           310.2 |                150.1 | 160.0 |     -46.2 |     198.3 |
|              4 | JONATHAN TAYLOR     | RB         |                 4 |         15.4 |           304.6 |                150.1 | 154.5 |     -46.0 |     198.8 |
|              5 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           288.3 |                148.3 | 140.0 |     -48.3 |     193.9 |
|              6 | ASHTON JEANTY       | RB         |                 5 |         15.3 |           277.3 |                150.1 | 127.2 |     -49.8 |     184.1 |
|              7 | PUKA NACUA          | WR         |                 2 |         15.1 |           273.0 |                148.3 | 124.7 |     -48.3 |     193.8 |
|              8 | AMON-RA ST. BROWN   | WR         |                 3 |         15.8 |           263.8 |                148.3 | 115.4 |     -45.8 |     194.9 |
|              9 | DE'VON ACHANE       | RB         |                 6 |         14.4 |           260.1 |                150.1 | 110.0 |     -49.0 |     186.3 |
|             10 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           239.0 |                130.4 | 108.7 |     -63.2 |     108.8 |
|             11 | JAMES COOK III      | RB         |                 7 |         14.0 |           250.0 |                150.1 |  99.9 |     -49.0 |     180.5 |
|             12 | CHASE BROWN         | RB         |                 8 |         14.2 |           249.8 |                150.1 |  99.7 |     -49.0 |     180.3 |
|             13 | SAQUON BARKLEY      | RB         |                 9 |         15.3 |           235.5 |                150.1 |  85.4 |     -67.9 |     180.1 |
|             14 | KENNETH WALKER III  | RB         |                10 |         13.9 |           232.0 |                150.1 |  81.9 |     -74.8 |     183.9 |
|             15 | OMARION HAMPTON     | RB         |                11 |         12.1 |           229.0 |                150.1 |  78.9 |     -75.7 |     182.5 |
|             16 | JAXON SMITH-NJIGBA  | WR         |                 4 |         15.3 |           224.7 |                148.3 |  76.3 |     -48.6 |     181.2 |
|             17 | CEEDEE LAMB         | WR         |                 5 |         14.4 |           220.8 |                148.3 |  72.5 |     -49.0 |     178.6 |
|             18 | DERRICK HENRY       | RB         |                12 |         14.0 |           220.5 |                150.1 |  70.4 |     -91.1 |     155.1 |
|             19 | DRAKE LONDON        | WR         |                 6 |         14.4 |           217.7 |                148.3 |  69.3 |     -48.6 |     177.4 |
|             20 | KYREN WILLIAMS      | RB         |                13 |         15.1 |           218.8 |                150.1 |  68.7 |     -85.6 |     157.0 |

### superflex

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | JAHMYR GIBBS        | RB         |                 1 |         14.4 |           350.8 |                150.1 | 200.6 |     -46.0 |     200.7 |
|              2 | CHRISTIAN MCCAFFREY | RB         |                 2 |         15.5 |           314.7 |                150.1 | 164.6 |     -48.7 |     196.9 |
|              3 | BIJAN ROBINSON      | RB         |                 3 |         15.2 |           310.2 |                150.1 | 160.0 |     -46.2 |     198.3 |
|              4 | JONATHAN TAYLOR     | RB         |                 4 |         15.4 |           304.6 |                150.1 | 154.5 |     -46.0 |     198.8 |
|              5 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           288.3 |                148.3 | 140.0 |     -48.3 |     193.9 |
|              6 | ASHTON JEANTY       | RB         |                 5 |         15.3 |           277.3 |                150.1 | 127.2 |     -49.8 |     184.1 |
|              7 | JOSH ALLEN          | QB         |                 1 |         16.5 |           305.2 |                179.4 | 125.8 |     -47.6 |     271.4 |
|              8 | PUKA NACUA          | WR         |                 2 |         15.1 |           273.0 |                148.3 | 124.7 |     -48.3 |     193.8 |
|              9 | LAMAR JACKSON       | QB         |                 2 |         14.5 |           298.3 |                179.4 | 118.8 |     -44.4 |     273.3 |
|             10 | AMON-RA ST. BROWN   | WR         |                 3 |         15.8 |           263.8 |                148.3 | 115.4 |     -45.8 |     194.9 |
|             11 | DRAKE MAYE          | QB         |                 3 |         16.5 |           292.1 |                179.4 | 112.6 |     -44.4 |     271.1 |
|             12 | DE'VON ACHANE       | RB         |                 6 |         14.4 |           260.1 |                150.1 | 110.0 |     -49.0 |     186.3 |
|             13 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           239.0 |                130.4 | 108.7 |     -63.2 |     108.8 |
|             14 | JAMES COOK III      | RB         |                 7 |         14.0 |           250.0 |                150.1 |  99.9 |     -49.0 |     180.5 |
|             15 | CHASE BROWN         | RB         |                 8 |         14.2 |           249.8 |                150.1 |  99.7 |     -49.0 |     180.3 |
|             16 | JOE BURROW          | QB         |                 4 |         12.0 |           276.9 |                179.4 |  97.5 |     -44.0 |     257.7 |
|             17 | JAYDEN DANIELS      | QB         |                 5 |         11.5 |           276.5 |                179.4 |  97.0 |     -44.2 |     257.0 |
|             18 | JALEN HURTS         | QB         |                 6 |         16.5 |           271.1 |                179.4 |  91.7 |     -47.7 |     257.4 |
|             19 | Fernando Mendoza    | QB         |                 7 |         12.4 |           270.2 |                179.4 |  90.8 |    -129.2 |     270.5 |
|             20 | CALEB WILLIAMS      | QB         |                 8 |         16.5 |           266.8 |                179.4 |  87.4 |     -49.2 |     254.5 |

## 4. League-size effect — size is a real dimension of value, not a label

For **full_ppr** across the scored league sizes: replacement level per position + the best QB's overall rank + the count of players carrying positive VOR. Fewer teams ⇒ shallower starter demand ⇒ a HIGHER replacement bar ⇒ fewer players with positive VOR. This is why the board grain includes `n_teams` — each size is a genuinely different value board off the same MVP-1 projections.

| format   |   n_teams |   QB_repl |   RB_repl |   WR_repl |   TE_repl |   best_QB_rank |   players_positive_VOR |
|:---------|----------:|----------:|----------:|----------:|----------:|---------------:|-----------------------:|
| full_ppr |        12 |     248.5 |     150.1 |     148.3 |     130.4 |             25 |                    108 |
| full_ppr |        10 |     254.0 |     162.7 |     163.1 |     132.1 |             23 |                     90 |

## 5. Limitations

- **Presets over the MVP-1 raw line** — the board is only as good as the MVP-1 projection it rescores; the within-tier ordering gap vs The Fantasy Footballers (RB/WR) carries through. NF-D2 closes it upstream.
- **K/DST are now projected, but by a deliberately BASE model (NF1.6)** — those slots RANK instead of rendering "not projected", scored off raw components (distance-bucketed FG; DST takeaways plus a per-game points-allowed TIER expressed exactly as expected-games-per-bucket). ⚠️ K and DST are the LEAST predictable fantasy positions: held-out rank correlation is ~0.32 for DST and ~0.23 among startable kickers, so read those two slots as **streaming tiers, not fine ranks**, and read the wide intervals as the honest part. The board covers QB/RB/WR/TE (FB folded into RB) + K/DST.
- **Uncertainty is a CV rescale**, not a per-format re-derived variance (no per-format game logs). Honest as a first-order interval; recalibrate rookie (parameter) intervals before pricing.
- **Manual formats only** — platform import (NF-C0) populates this SAME config object later; the config schema is the shared contract.

