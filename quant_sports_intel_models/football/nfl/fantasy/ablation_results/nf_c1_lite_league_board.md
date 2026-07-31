# NF-C1-lite — 2026 NFL league-config scoring + VOR boards (MVP-2)

**Engine:** `nfl_fantasy_league_board_v1` (sport-agnostic `fantasy_engine`) · **projection season:** 2026 · **generated:** 2026-07-31T19:08:17.787961+00:00

> 🧮 **Sections 1–3 below are shown at the 12-team reference size** (the modal redraft size); the boards are landed for every scored size — see §4 for the league-size effect. The board grain is (config_name, n_teams, player_id): league size is a normalized dimension, not part of the format name.

> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate. The gate is (1) SCORING CORRECTNESS (hand-calc match — see the fast-gate tests), (2) a TRANSPARENT replacement-level definition (the per-position demand tables below), and (3) FACE-VALID preset deltas (full-PPR lifts pass-catchers; superflex lifts QBs). We **RESCORE the MVP-1 raw stat line** per league — never the `proj_fp_*` convenience columns. Uncertainty is carried through the rescore as a coefficient-of-variation (a first-order interval, not a false-precise point); rookie intervals remain PARAMETER uncertainty and must be recalibrated before pricing.

## 1. Face validity — the preset deltas that prove the scarcity math

| preset    | best_QB    |   best_QB_overall_rank |   WR+TE_in_top10 |   RB_in_top10 |
|:----------|:-----------|-----------------------:|-----------------:|--------------:|
| standard  | JOSH ALLEN |                     15 |                1 |             9 |
| half_ppr  | JOSH ALLEN |                     15 |                3 |             7 |
| full_ppr  | JOSH ALLEN |                     19 |                4 |             6 |
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
| QB         |                   12 |                0 |              12 |                265.2 |
| RB         |                   24 |               10 |              34 |                 89.5 |
| TE         |                   12 |                0 |              12 |                 71.9 |
| WR         |                   24 |                2 |              26 |                 90.8 |

### full_ppr

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                109.4 |
| K          |                   12 |                0 |              12 |                129.5 |
| QB         |                   12 |                0 |              12 |                265.4 |
| RB         |                   24 |                1 |              25 |                129.9 |
| TE         |                   12 |                0 |              12 |                117.0 |
| WR         |                   24 |               11 |              35 |                131.0 |

### superflex

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                109.4 |
| K          |                   12 |                0 |              12 |                129.5 |
| QB         |                   12 |               12 |              24 |                191.8 |
| RB         |                   24 |                1 |              25 |                129.9 |
| TE         |                   12 |                0 |              12 |                117.0 |
| WR         |                   24 |               11 |              35 |                131.0 |

## 3. Ranked boards — top 20 by VOR

### standard

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | JONATHAN TAYLOR     | RB         |                 1 |         15.4 |           218.1 |                 89.5 | 128.6 |       1.7 |     216.3 |
|              2 | CHRISTIAN MCCAFFREY | RB         |                 2 |         15.5 |           215.6 |                 89.5 | 126.1 |      -9.7 |     178.1 |
|              3 | BIJAN ROBINSON      | RB         |                 3 |         15.2 |           199.7 |                 89.5 | 110.2 |      -9.2 |     185.3 |
|              4 | JAHMYR GIBBS        | RB         |                 4 |         14.4 |           196.8 |                 89.5 | 107.4 |      -5.6 |     191.9 |
|              5 | DERRICK HENRY       | RB         |                 5 |         14.0 |           184.5 |                 89.5 |  95.1 |       3.7 |     215.0 |
|              6 | SAQUON BARKLEY      | RB         |                 6 |         15.3 |           177.9 |                 89.5 |  88.5 |      -3.2 |     197.7 |
|              7 | DE'VON ACHANE       | RB         |                 7 |         14.4 |           173.5 |                 89.5 |  84.1 |     -11.2 |     171.6 |
|              8 | KYREN WILLIAMS      | RB         |                 8 |         15.1 |           172.4 |                 89.5 |  83.0 |      -2.5 |     195.1 |
|              9 | Jeremiyah Love      | RB         |                 9 |         16.0 |           164.6 |                 89.5 |  75.1 |     -63.9 |     207.1 |
|             10 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           165.6 |                 90.8 |  74.8 |     -27.6 |     125.5 |
|             11 | JAMES COOK III      | RB         |                10 |         14.0 |           161.2 |                 89.5 |  71.7 |     -24.2 |     200.1 |
|             12 | AMON-RA ST. BROWN   | WR         |                 2 |         15.8 |           157.7 |                 90.8 |  66.9 |     -27.3 |     126.6 |
|             13 | JOSH JACOBS         | RB         |                11 |         14.2 |           155.0 |                 89.5 |  65.6 |     -26.7 |     191.6 |
|             14 | PUKA NACUA          | WR         |                 3 |         15.1 |           154.2 |                 90.8 |  63.3 |     -24.9 |     129.9 |
|             15 | JOSH ALLEN          | QB         |                 1 |         16.5 |           325.7 |                265.2 |  60.5 |    -134.5 |     181.8 |
|             16 | ASHTON JEANTY       | RB         |                12 |         15.3 |           146.1 |                 89.5 |  56.7 |     -25.8 |     166.3 |
|             17 | JALEN HURTS         | QB         |                 2 |         16.5 |           318.2 |                265.2 |  53.0 |    -131.2 |     183.9 |
|             18 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           123.9 |                 71.9 |  52.0 |     -33.2 |      63.0 |
|             19 | BREECE HALL         | RB         |                13 |         14.3 |           137.4 |                 89.5 |  47.9 |     -38.9 |     151.2 |
|             20 | JARED GOFF          | QB         |                 3 |         16.5 |           311.1 |                265.2 |  46.0 |    -131.4 |     181.5 |

### full_ppr

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | CHRISTIAN MCCAFFREY | RB         |                 1 |         15.5 |           279.9 |                129.9 | 150.0 |     -26.2 |     217.5 |
|              2 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           261.4 |                131.0 | 130.3 |     -31.2 |     210.3 |
|              3 | BIJAN ROBINSON      | RB         |                 2 |         15.2 |           251.3 |                129.9 | 121.4 |     -28.8 |     215.9 |
|              4 | JONATHAN TAYLOR     | RB         |                 3 |         15.4 |           247.8 |                129.9 | 117.9 |     -26.2 |     217.5 |
|              5 | AMON-RA ST. BROWN   | WR         |                 2 |         15.8 |           247.6 |                131.0 | 116.6 |     -31.2 |     210.3 |
|              6 | JAHMYR GIBBS        | RB         |                 4 |         14.4 |           243.0 |                129.9 | 113.1 |     -26.2 |     217.5 |
|              7 | PUKA NACUA          | WR         |                 3 |         15.1 |           239.1 |                131.0 | 108.0 |     -28.7 |     211.2 |
|              8 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           214.6 |                117.0 |  97.6 |     -49.9 |     116.6 |
|              9 | DE'VON ACHANE       | RB         |                 5 |         14.4 |           221.5 |                129.9 |  91.5 |     -29.9 |     203.2 |
|             10 | Jeremiyah Love      | RB         |                 6 |         16.0 |           208.4 |                129.9 |  78.5 |     -97.4 |     245.7 |
|             11 | SAQUON BARKLEY      | RB         |                 7 |         15.3 |           207.8 |                129.9 |  77.8 |     -29.1 |     205.4 |
|             12 | JAXON SMITH-NJIGBA  | WR         |                 4 |         15.3 |           203.7 |                131.0 |  72.7 |     -31.5 |     197.8 |
|             13 | DERRICK HENRY       | RB         |                 8 |         14.0 |           199.6 |                129.9 |  69.6 |     -29.1 |     199.4 |
|             14 | KYREN WILLIAMS      | RB         |                 9 |         15.1 |           199.5 |                129.9 |  69.6 |     -29.1 |     199.4 |
|             15 | JUSTIN JEFFERSON    | WR         |                 5 |         16.2 |           200.3 |                131.0 |  69.3 |     -31.8 |     195.2 |
|             16 | CEEDEE LAMB         | WR         |                 6 |         14.4 |           197.3 |                131.0 |  66.3 |     -31.5 |     193.9 |
|             17 | A.J. BROWN          | WR         |                 7 |         15.7 |           194.8 |                131.0 |  63.8 |     -28.6 |     194.0 |
|             18 | Jordyn Tyson        | WR         |                 8 |         13.6 |           191.4 |                131.0 |  60.4 |    -112.5 |     199.9 |
|             19 | JOSH ALLEN          | QB         |                 1 |         16.5 |           325.7 |                265.4 |  60.3 |    -134.7 |     181.6 |
|             20 | ASHTON JEANTY       | RB         |                10 |         15.3 |           188.1 |                129.9 |  58.1 |     -47.9 |     199.2 |

### superflex

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | CHRISTIAN MCCAFFREY | RB         |                 1 |         15.5 |           279.9 |                129.9 | 150.0 |     -26.2 |     217.5 |
|              2 | JOSH ALLEN          | QB         |                 1 |         16.5 |           325.7 |                191.8 | 133.9 |     -61.1 |     255.2 |
|              3 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           261.4 |                131.0 | 130.3 |     -31.2 |     210.3 |
|              4 | JALEN HURTS         | QB         |                 2 |         16.5 |           318.2 |                191.8 | 126.4 |     -57.8 |     257.3 |
|              5 | BIJAN ROBINSON      | RB         |                 2 |         15.2 |           251.3 |                129.9 | 121.4 |     -28.8 |     215.9 |
|              6 | JARED GOFF          | QB         |                 3 |         16.5 |           311.4 |                191.8 | 119.6 |     -57.8 |     255.2 |
|              7 | JONATHAN TAYLOR     | RB         |                 3 |         15.4 |           247.8 |                129.9 | 117.9 |     -26.2 |     217.5 |
|              8 | AMON-RA ST. BROWN   | WR         |                 2 |         15.8 |           247.6 |                131.0 | 116.6 |     -31.2 |     210.3 |
|              9 | JAHMYR GIBBS        | RB         |                 4 |         14.4 |           243.0 |                129.9 | 113.1 |     -26.2 |     217.5 |
|             10 | PUKA NACUA          | WR         |                 3 |         15.1 |           239.1 |                131.0 | 108.0 |     -28.7 |     211.2 |
|             11 | LAMAR JACKSON       | QB         |                 4 |         14.5 |           296.9 |                191.8 | 105.1 |     -57.5 |     249.7 |
|             12 | DAK PRESCOTT        | QB         |                 5 |         16.5 |           293.4 |                191.8 | 101.7 |     -45.8 |     241.4 |
|             13 | JUSTIN HERBERT      | QB         |                 6 |         16.5 |           290.6 |                191.8 |  98.8 |     -59.0 |     241.4 |
|             14 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           214.6 |                117.0 |  97.6 |     -49.9 |     116.6 |
|             15 | MATTHEW STAFFORD    | QB         |                 7 |         16.5 |           284.8 |                191.8 |  93.0 |     -62.5 |     237.8 |
|             16 | DE'VON ACHANE       | RB         |                 5 |         14.4 |           221.5 |                129.9 |  91.5 |     -29.9 |     203.2 |
|             17 | TREVOR LAWRENCE     | QB         |                 8 |         16.5 |           282.5 |                191.8 |  90.7 |     -61.4 |     237.8 |
|             18 | BAKER MAYFIELD      | QB         |                 9 |         16.5 |           279.2 |                191.8 |  87.4 |     -64.6 |     226.2 |
|             19 | PATRICK MAHOMES     | QB         |                10 |         15.0 |           271.2 |                191.8 |  79.4 |     -61.1 |     238.9 |
|             20 | Jeremiyah Love      | RB         |                 6 |         16.0 |           208.4 |                129.9 |  78.5 |     -97.4 |     245.7 |

## 4. League-size effect — size is a real dimension of value, not a label

For **full_ppr** across the scored league sizes: replacement level per position + the best QB's overall rank + the count of players carrying positive VOR. Fewer teams ⇒ shallower starter demand ⇒ a HIGHER replacement bar ⇒ fewer players with positive VOR. This is why the board grain includes `n_teams` — each size is a genuinely different value board off the same MVP-1 projections.

| format   |   n_teams |   QB_repl |   RB_repl |   WR_repl |   TE_repl |   best_QB_rank |   players_positive_VOR |
|:---------|----------:|----------:|----------:|----------:|----------:|---------------:|-----------------------:|
| full_ppr |        12 |     265.4 |     129.9 |     131.0 |     117.0 |             19 |                    108 |
| full_ppr |        10 |     268.3 |     132.0 |     137.9 |     118.6 |             17 |                     90 |

## 5. Limitations

- **Presets over the MVP-1 raw line** — the board is only as good as the MVP-1 projection it rescores; the within-tier ordering gap vs The Fantasy Footballers (RB/WR) carries through. NF-D2 closes it upstream.
- **K/DST are now projected, but by a deliberately BASE model (NF1.6)** — those slots RANK instead of rendering "not projected", scored off raw components (distance-bucketed FG; DST takeaways plus a per-game points-allowed TIER expressed exactly as expected-games-per-bucket). ⚠️ K and DST are the LEAST predictable fantasy positions: held-out rank correlation is ~0.32 for DST and ~0.23 among startable kickers, so read those two slots as **streaming tiers, not fine ranks**, and read the wide intervals as the honest part. The board covers QB/RB/WR/TE (FB folded into RB) + K/DST.
- **Uncertainty is a CV rescale**, not a per-format re-derived variance (no per-format game logs). Honest as a first-order interval; recalibrate rookie (parameter) intervals before pricing.
- **Manual formats only** — platform import (NF-C0) populates this SAME config object later; the config schema is the shared contract.

