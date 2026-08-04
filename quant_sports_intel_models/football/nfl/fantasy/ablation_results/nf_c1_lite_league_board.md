# NF-C1-lite — 2026 NFL league-config scoring + VOR boards (MVP-2)

**Engine:** `nfl_fantasy_league_board_v1` (sport-agnostic `fantasy_engine`) · **projection season:** 2026 · **generated:** 2026-08-04T04:49:15.670146+00:00

> 🧮 **Sections 1–3 below are shown at the 12-team reference size** (the modal redraft size); the boards are landed for every scored size — see §4 for the league-size effect. The board grain is (config_name, n_teams, player_id): league size is a normalized dimension, not part of the format name.

> ⚖️ **A PROJECTION PRODUCT, edge-independent** — no `best_alpha`/PBO/DSR/CLV gate. The gate is (1) SCORING CORRECTNESS (hand-calc match — see the fast-gate tests), (2) a TRANSPARENT replacement-level definition (the per-position demand tables below), and (3) FACE-VALID preset deltas (full-PPR lifts pass-catchers; superflex lifts QBs). We **RESCORE the MVP-1 raw stat line** per league — never the `proj_fp_*` convenience columns. Uncertainty is carried through the rescore as a coefficient-of-variation (a first-order interval, not a false-precise point); rookie intervals remain PARAMETER uncertainty and must be recalibrated before pricing.

## 1. Face validity — the preset deltas that prove the scarcity math

| preset    | best_QB    |   best_QB_overall_rank |   WR+TE_in_top10 |   RB_in_top10 |
|:----------|:-----------|-----------------------:|-----------------:|--------------:|
| standard  | JOSH ALLEN |                     13 |                1 |             9 |
| half_ppr  | JOSH ALLEN |                     15 |                4 |             6 |
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
| QB         |                   12 |                0 |              12 |                267.7 |
| RB         |                   24 |                8 |              32 |                 94.8 |
| TE         |                   12 |                0 |              12 |                 71.8 |
| WR         |                   24 |                4 |              28 |                 94.8 |

### full_ppr

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                109.4 |
| K          |                   12 |                0 |              12 |                129.5 |
| QB         |                   12 |                0 |              12 |                267.7 |
| RB         |                   24 |                0 |              24 |                131.4 |
| TE         |                   12 |                0 |              12 |                117.5 |
| WR         |                   24 |               12 |              36 |                131.1 |

### superflex

| position   |   dedicated_starters |   flex_allocated |   total_started |   replacement_points |
|:-----------|---------------------:|-----------------:|----------------:|---------------------:|
| DST        |                   12 |                0 |              12 |                109.4 |
| K          |                   12 |                0 |              12 |                129.5 |
| QB         |                   12 |               12 |              24 |                193.1 |
| RB         |                   24 |                0 |              24 |                131.4 |
| TE         |                   12 |                0 |              12 |                117.5 |
| WR         |                   24 |               12 |              36 |                131.1 |

## 3. Ranked boards — top 20 by VOR

### standard

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | BIJAN ROBINSON      | RB         |                 1 |         15.2 |           223.2 |                 94.8 | 128.4 |     -12.2 |     182.2 |
|              2 | JONATHAN TAYLOR     | RB         |                 2 |         15.4 |           214.9 |                 94.8 | 120.1 |      -3.2 |     212.4 |
|              3 | JAHMYR GIBBS        | RB         |                 3 |         14.4 |           201.7 |                 94.8 | 106.9 |     -10.5 |     188.0 |
|              4 | CHRISTIAN MCCAFFREY | RB         |                 4 |         15.5 |           194.4 |                 94.8 |  99.6 |     -16.7 |     172.7 |
|              5 | JAMES COOK III      | RB         |                 5 |         14.0 |           174.3 |                 94.8 |  79.5 |      -6.8 |     192.9 |
|              6 | DE'VON ACHANE       | RB         |                 6 |         14.4 |           174.3 |                 94.8 |  79.5 |     -16.2 |     167.4 |
|              7 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           166.3 |                 94.8 |  71.5 |     -31.4 |     122.4 |
|              8 | Jeremiyah Love      | RB         |                 7 |         16.0 |           165.0 |                 94.8 |  70.2 |     -69.1 |     202.6 |
|              9 | DERRICK HENRY       | RB         |                 8 |         14.0 |           163.4 |                 94.8 |  68.6 |     -40.2 |     187.5 |
|             10 | ASHTON JEANTY       | RB         |                 9 |         15.3 |           162.1 |                 94.8 |  67.3 |     -16.2 |     166.9 |
|             11 | SAQUON BARKLEY      | RB         |                10 |         15.3 |           161.7 |                 94.8 |  66.9 |     -24.4 |     188.2 |
|             12 | PUKA NACUA          | WR         |                 2 |         15.1 |           160.2 |                 94.8 |  65.4 |     -30.3 |     126.0 |
|             13 | JOSH ALLEN          | QB         |                 1 |         16.5 |           328.5 |                267.7 |  60.8 |    -135.9 |     183.1 |
|             14 | CHASE BROWN         | RB         |                11 |         14.2 |           153.5 |                 94.8 |  58.7 |     -17.3 |     158.6 |
|             15 | AMON-RA ST. BROWN   | WR         |                 3 |         15.8 |           152.9 |                 94.8 |  58.1 |     -29.4 |     124.1 |
|             16 | KYREN WILLIAMS      | RB         |                12 |         15.1 |           151.5 |                 94.8 |  56.8 |     -39.0 |     170.8 |
|             17 | KENNETH WALKER III  | RB         |                13 |         13.9 |           148.9 |                 94.8 |  54.1 |     -34.5 |     175.2 |
|             18 | LAMAR JACKSON       | QB         |                 2 |         14.5 |           320.7 |                267.7 |  53.0 |    -132.7 |     185.0 |
|             19 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           124.4 |                 71.8 |  52.6 |     -33.0 |      63.6 |
|             20 | OMARION HAMPTON     | RB         |                14 |         12.1 |           143.0 |                 94.8 |  48.2 |     -36.9 |     162.1 |

### full_ppr

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | BIJAN ROBINSON      | RB         |                 1 |         15.2 |           280.7 |                131.4 | 149.3 |     -27.5 |     217.0 |
|              2 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           262.0 |                131.1 | 131.0 |     -31.1 |     211.1 |
|              3 | CHRISTIAN MCCAFFREY | RB         |                 2 |         15.5 |           252.2 |                131.4 | 120.8 |     -30.0 |     215.6 |
|              4 | JAHMYR GIBBS        | RB         |                 3 |         14.4 |           248.8 |                131.4 | 117.4 |     -27.3 |     217.4 |
|              5 | PUKA NACUA          | WR         |                 2 |         15.1 |           248.2 |                131.1 | 117.1 |     -31.1 |     211.0 |
|              6 | JONATHAN TAYLOR     | RB         |                 4 |         15.4 |           244.1 |                131.4 | 112.7 |     -27.3 |     217.5 |
|              7 | AMON-RA ST. BROWN   | WR         |                 3 |         15.8 |           239.7 |                131.1 | 108.7 |     -28.6 |     212.1 |
|              8 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           215.0 |                117.5 |  97.6 |     -50.3 |     116.6 |
|              9 | DE'VON ACHANE       | RB         |                 5 |         14.4 |           222.2 |                131.4 |  90.8 |     -31.1 |     202.8 |
|             10 | Jeremiyah Love      | RB         |                 6 |         16.0 |           208.9 |                131.4 |  77.6 |     -98.9 |     245.1 |
|             11 | ASHTON JEANTY       | RB         |                 7 |         15.3 |           208.4 |                131.4 |  77.1 |     -30.3 |     205.0 |
|             12 | JAXON SMITH-NJIGBA  | WR         |                 4 |         15.3 |           204.2 |                131.1 |  73.1 |     -31.4 |     198.4 |
|             13 | CEEDEE LAMB         | WR         |                 5 |         14.4 |           200.7 |                131.1 |  69.6 |     -31.8 |     195.8 |
|             14 | JAMES COOK III      | RB         |                 8 |         14.0 |           200.3 |                131.4 |  68.9 |     -30.3 |     199.2 |
|             15 | CHASE BROWN         | RB         |                 9 |         14.2 |           200.2 |                131.4 |  68.8 |     -30.3 |     199.0 |
|             16 | DRAKE LONDON        | WR         |                 6 |         14.4 |           197.8 |                131.1 |  66.8 |     -31.4 |     194.6 |
|             17 | JUSTIN JEFFERSON    | WR         |                 7 |         16.2 |           195.2 |                131.1 |  64.1 |     -28.6 |     194.5 |
|             18 | Jordyn Tyson        | WR         |                 8 |         13.6 |           191.9 |                131.1 |  60.8 |    -112.6 |     200.6 |
|             19 | JOSH ALLEN          | QB         |                 1 |         16.5 |           328.5 |                267.7 |  60.8 |    -135.9 |     183.1 |
|             20 | SAQUON BARKLEY      | RB         |                10 |         15.3 |           188.7 |                131.4 |  57.3 |     -49.2 |     198.8 |

### superflex

|   overall_rank | player_name         | position   |   positional_rank |   proj_games |   league_points |   replacement_points |   vor |   vor_p10 |   vor_p90 |
|---------------:|:--------------------|:-----------|------------------:|-------------:|----------------:|---------------------:|------:|----------:|----------:|
|              1 | BIJAN ROBINSON      | RB         |                 1 |         15.2 |           280.7 |                131.4 | 149.3 |     -27.5 |     217.0 |
|              2 | JOSH ALLEN          | QB         |                 1 |         16.5 |           328.5 |                193.1 | 135.3 |     -61.3 |     257.7 |
|              3 | JA'MARR CHASE       | WR         |                 1 |         15.8 |           262.0 |                131.1 | 131.0 |     -31.1 |     211.1 |
|              4 | LAMAR JACKSON       | QB         |                 2 |         14.5 |           320.7 |                193.1 | 127.6 |     -58.1 |     259.6 |
|              5 | CHRISTIAN MCCAFFREY | RB         |                 2 |         15.5 |           252.2 |                131.4 | 120.8 |     -30.0 |     215.6 |
|              6 | DRAKE MAYE          | QB         |                 3 |         16.5 |           313.8 |                193.1 | 120.7 |     -58.1 |     257.4 |
|              7 | JAHMYR GIBBS        | RB         |                 3 |         14.4 |           248.8 |                131.4 | 117.4 |     -27.3 |     217.4 |
|              8 | PUKA NACUA          | WR         |                 2 |         15.1 |           248.2 |                131.1 | 117.1 |     -31.1 |     211.0 |
|              9 | JONATHAN TAYLOR     | RB         |                 4 |         15.4 |           244.1 |                131.4 | 112.7 |     -27.3 |     217.5 |
|             10 | AMON-RA ST. BROWN   | WR         |                 3 |         15.8 |           239.7 |                131.1 | 108.7 |     -28.6 |     212.1 |
|             11 | JOE BURROW          | QB         |                 4 |         12.0 |           299.5 |                193.1 | 106.4 |     -57.7 |     252.4 |
|             12 | JAYDEN DANIELS      | QB         |                 5 |         11.5 |           295.6 |                193.1 | 102.4 |     -46.1 |     243.3 |
|             13 | JALEN HURTS         | QB         |                 6 |         16.5 |           293.0 |                193.1 |  99.8 |     -59.3 |     243.7 |
|             14 | TREY MCBRIDE        | TE         |                 1 |         16.6 |           215.0 |                117.5 |  97.6 |     -50.3 |     116.6 |
|             15 | CALEB WILLIAMS      | QB         |                 7 |         16.5 |           286.9 |                193.1 |  93.8 |     -62.9 |     239.7 |
|             16 | JUSTIN HERBERT      | QB         |                 8 |         16.5 |           284.6 |                193.1 |  91.5 |     -61.8 |     239.8 |
|             17 | DE'VON ACHANE       | RB         |                 5 |         14.4 |           222.2 |                131.4 |  90.8 |     -31.1 |     202.8 |
|             18 | TREVOR LAWRENCE     | QB         |                 9 |         16.5 |           281.5 |                193.1 |  88.4 |     -64.9 |     228.4 |
|             19 | DAK PRESCOTT        | QB         |                10 |         16.5 |           273.4 |                193.1 |  80.3 |     -61.4 |     241.2 |
|             20 | Jeremiyah Love      | RB         |                 6 |         16.0 |           208.9 |                131.4 |  77.6 |     -98.9 |     245.1 |

## 4. League-size effect — size is a real dimension of value, not a label

For **full_ppr** across the scored league sizes: replacement level per position + the best QB's overall rank + the count of players carrying positive VOR. Fewer teams ⇒ shallower starter demand ⇒ a HIGHER replacement bar ⇒ fewer players with positive VOR. This is why the board grain includes `n_teams` — each size is a genuinely different value board off the same MVP-1 projections.

| format   |   n_teams |   QB_repl |   RB_repl |   WR_repl |   TE_repl |   best_QB_rank |   players_positive_VOR |
|:---------|----------:|----------:|----------:|----------:|----------:|---------------:|-----------------------:|
| full_ppr |        12 |     267.7 |     131.4 |     131.1 |     117.5 |             19 |                    108 |
| full_ppr |        10 |     270.2 |     138.3 |     137.4 |     118.9 |             17 |                     90 |

## 5. Limitations

- **Presets over the MVP-1 raw line** — the board is only as good as the MVP-1 projection it rescores; the within-tier ordering gap vs The Fantasy Footballers (RB/WR) carries through. NF-D2 closes it upstream.
- **K/DST are now projected, but by a deliberately BASE model (NF1.6)** — those slots RANK instead of rendering "not projected", scored off raw components (distance-bucketed FG; DST takeaways plus a per-game points-allowed TIER expressed exactly as expected-games-per-bucket). ⚠️ K and DST are the LEAST predictable fantasy positions: held-out rank correlation is ~0.32 for DST and ~0.23 among startable kickers, so read those two slots as **streaming tiers, not fine ranks**, and read the wide intervals as the honest part. The board covers QB/RB/WR/TE (FB folded into RB) + K/DST.
- **Uncertainty is a CV rescale**, not a per-format re-derived variance (no per-format game logs). Honest as a first-order interval; recalibrate rookie (parameter) intervals before pricing.
- **Manual formats only** — platform import (NF-C0) populates this SAME config object later; the config schema is the shared contract.

