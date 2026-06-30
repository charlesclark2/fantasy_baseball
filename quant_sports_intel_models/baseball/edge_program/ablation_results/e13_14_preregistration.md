# E13.14 — Cross-Market Relative-Value (constellation coherence) · PRE-REGISTRATION

**Written 2026-06-30, BEFORE any realized outcome was joined.** This is the anti-data-mining
contract (guide §0.5 + the E13.13 lesson). The relations tested, the implied-quantity formula
for each, the bet rule, the Bayesian selection gate, and the deflation plan are fixed HERE so the
verdict is decided by the gate — not by a post-hoc search for "the relation/threshold where we'd
have won." Every relation × credence-threshold × bet-book-group config is logged in
`e13_14_relation_grid_results.csv` (no cherry-pick).

## The mechanism (why this is a DIFFERENT question than every prior null)
E5.4 / E13.13 / E13.8 all asked **"is OUR prediction better than ONE line?"** → efficient,
PBO≈0.5 (our disagreement was noise). This probe asks: **"are the BOOKS' OWN markets on a game
mutually COHERENT, and where two markets CONTRADICT each other, does the side the SHARP / implied
market favors win net of the bet-market's vig?"** An edge here does NOT require beating an efficient
market on average — it requires the LAZY markets (props, team-totals, F5) to be INCONSISTENT with
each other or with the sharp main line. Books price these on different desks/models at different
times, so an internal inconsistency is a plausible, untested inefficiency (the sharpest reading of
Miller-Davidow). The play is **RELATIVE** (market-vs-market) → partly market-NEUTRAL: we do not
predict the game; we arbitrage the books' own disagreement, and our rule only picks WHICH side of
an inconsistency to take.

## Honest bar (non-negotiable — the E13.13 trap)
- **Game-level collapse FIRST.** Book quotes on the same game are correlated, not independent bets.
  Every per-(game × book) PnL is averaged to ONE return per `game_pk` BEFORE any t-test / DSR / PBO.
  (E13.13's correlated-quote inflation manufactured a +29% mirage at quote level; game-level scoring
  removed it.) `n` = unique GAMES, never quotes.
- **In-fold selection only.** The systematic offset that centers each relation's residual (the
  "expected wedge" between two coherent markets) is estimated **leave-one-season-out** — a game in
  season *s* is centered on the median residual of the OTHER seasons. No same-season, no same-game
  leakage. The credence width uses only same-game across-book dispersion (no outcome peeking).
- **Forced side (zero outcome DOF).** The bet side is the SIGN of the cross-market deviation — never
  chosen from the realized outcome. The only selection DOF is *which games* (credence gate) and
  *which bet-book-group*, both pre-registered and both counted in the deflation.
- **Deflate for EVERYTHING.** PBO (CSCV over year-month slices × configs) < 0.2 AND DSR (deflated by
  the total config count) reported, AND each candidate config's edge must survive Benjamini–Hochberg
  FDR (q=0.10) across **all relations × thresholds × book-groups**. A single relation/threshold's
  apparent +ROI is multiple-comparison noise until it clears all three.
- **The F5↔main control MUST come back "consistent."** E13.13 found F5 IS correctly derived off the
  main line (slopes matched → efficient). If our method flags the F5↔main relation as an exploitable
  inconsistency, the **method is broken** — that is a calibration check on the harness, not a finding.
- **Cashability proxy honesty.** With only CLOSING odds cached, the gate metric is **realized-outcome
  ROI net of the bet-market's own vig** (the offered American price embeds the overround — exactly the
  E13.13 / E5.4 unit). True beat-the-close forward CLV needs the opening→close capture (E2.0b/forward);
  a survivor here is a CANDIDATE for that forward leg, not a declared edge.

## Data sources (§0.5 — cached S3 via DuckDB, NO Snowflake; one read → parquet)
| Quantity | Store (S3 lakehouse) | Key columns |
|---|---|---|
| Game total + h2h (sharp main line) | `mart_odds_outcomes` | `event_id`, `bookmaker_key`, `market_key∈{totals,h2h}`, `outcome_name`, `outcome_point`, `outcome_price_american` |
| Team totals / alternate totals | `mart_derivative_closes` | `game_pk`, `market_key='team_totals'`, **team = `outcome_description`**, side = `outcome_name`(Over/Under), `outcome_point`, `outcome_price_american` |
| F5 / NRFI / batter & pitcher props | `mlb/props/market={key}/season=*/date=*` | `event_id`, `bookmaker_key`, `player_name`, `line`, `over_price`, `under_price` |
| Run-line (spreads) | `mlb/props/market=spreads` | as above (🟡 stalled 2025-08-11 → relation 5 = 2023–25 only) |
| `event_id → game_pk` | `mart_game_odds_bridge` | `odds_api_event_id`, `game_pk`, `home_team_name`, `away_team_name` |
| Realized runs + batter→side map | `stg_batter_pitches` | `game_pk`, `inning`, `inning_topbot` (Top⇒away bats, Bot⇒home bats), `player_name` (batter), `post_pitch_home_score`, `post_pitch_away_score` |

Coverage note (per the 2026-06-30 S3 audit + W11 coordination): the derivative store (`team_totals`)
is complete on the historical window but its *recent-2026* tail lands only when **W11** wires `--w3pre`
into the daily op. E13.14 only READS — it is parallel-safe with W11 — and runs on **2023 → ~Apr-2026**
now; W11 later extends the recent edge. Relation 5 (`spreads`) runs **2023–2025** until the 2026
catch-up grab.

## The pre-registered relations (constellation edges)
For each: `implied_A` is computed from market A; `posted_B` is the line in the bet-market B (always
the cleaner-settling market). The residual `r = implied_A − posted_B`; the **deviation**
`d = r − offset_LOSO` is the inconsistency. Side = `over` if `d>0` else `under` on market B; settle on
the realized B outcome; PnL net of B's vig; collapse to game level.

| # | Relation (A → B) | implied_A | posted_B (bet market) | realized B | prior |
|---|---|---|---|---|---|
| 1 ⭐ | **Props → team offense** | Σ over a team's batters of implied E[runs] (Poisson-mean inversion of the de-vigged `batter_runs_scored`/`batter_rbis` 0.5-line P(≥1)); batter→side from pitch data | that side's **team-total** line | side's realized full-game runs | **highest** — the two laziest markets |
| 2 | **Team-totals → game-total** | home_tt + away_tt | **game-total** line | realized full-game total | medium — link-priced but on different tickets |
| 3 | **F5 → full game = NEGATIVE CONTROL** | F5 total line ÷ `frac_LOSO` (F5≈0.52–0.56 of full) | **game-total** line | realized full-game total | **must be CONSISTENT** (E13.13: F5 correctly derived) |
| 4 | **K-props → opposing team-total** | `a+b·projK` (LOSO fit of realized opp runs on the starter's de-vig-tilted `pitcher_strikeouts` projection) | opposing **team-total** line | opposing side's realized runs | low — single-starter signal |
| 5 | **Sides ↔ totals** | P(home win) implied by the run-line price + total (normal-margin, σ scaled by √total) | de-vig **moneyline** P(home) | realized home win | low — ML & run-line are tightly link-priced (near-control) |

`offset_LOSO` (the coherent-market "wedge") and (for 3/4) the slope/fraction are estimated
leave-one-season-out. The Poisson-mean inversion + the across-book dispersion give the **Bayesian
posterior** on `implied_A`; combined with the across-book dispersion of `posted_B` this yields the
deviation's `joint_sd`. (The parametric E2.3 totals / E5.2 prop distributions are the conceptual basis
for that posterior; the leakage-free same-game across-book dispersion is the tractable estimator used.)

## The Bayesian selection gate ("bet only where the inconsistency beats the joint uncertainty")
Per game the deviation posterior is `d ~ Normal(d, joint_sd)`; the **credence** that the true deviation
carries the observed sign = `Φ(|d| / joint_sd)`. A config bets a game only when `credence ≥ τ`. The
pre-registered credence grid is `τ ∈ {0.75, 0.85, 0.90, 0.95, 0.975}`. (A higher τ = only the most
confident inconsistencies; the grid is swept and every τ counts in the deflation.)

## The deflation grid (every config counted)
`config = relation × τ × bet-book-group`, book-group ∈ `{all, pinnacle, soft, majors}` on market B.
A config is **selectable** if it bets ≥ `MIN_GAMES = 50` unique games; selectable below
`FRAGILE_GAMES = 250` is flagged FRAGILE. Deflation:
- **PBO** via CSCV over year-month slices × selectable configs — must be `< 0.2`.
- **DSR** on the in-sample-best config, deflated by the selectable-config count — reported (`≥ 0.95`).
- **BH-FDR** (q=0.10) over every selectable config's ROI t-test.

A relation is a **CANDIDATE** only if a config of it has: ROI > 0 net of vig (game-level) **AND**
season-sign-consistent **AND** survives FDR across all configs **AND** the grid PBO < 0.2. Even then it
is a candidate for the **forward-CLV leg**, not a declared edge. **The F5↔main control (relation 3)
producing a candidate ⇒ the harness is mis-calibrated** (reported as a method failure, not an edge).

## Outputs
- `e13_14_cross_market_coherence.{json,md}` — per-relation coherence diagnostics + the F5-control
  result + the credence-gated config grid + deflation + candidate shortlist (or a clean null).
- `e13_14_relation_grid_results.csv` — EVERY relation × τ × book-group config logged (the no-cherry-
  pick ledger feeding the deflation count).

## Going-in expectation (does NOT soften the gate)
Prior is guarded: books link-price the constellation and sharps arbitrage cross-market gaps fast. BUT
this is a genuinely different mechanism with real value-of-information, and the LAZY↔LAZY pairs
(props↔team-total, relation 1) are the least-arbed → the single most plausible survivor. A clean null
closes the cross-market angle (with E5.4 / E13.13): "value = product-quality calibration + transparency
+ fantasy," not a cashable cross-market edge. The gate, not the hunch, decides.
