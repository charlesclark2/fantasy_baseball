# E13.13 — Derivative-Market Mispricing Evaluation · PRE-REGISTRATION

**Written 2026-06-29, BEFORE any outcome was joined.** This is the anti-data-mining
contract (guide §0.5 + the E5.4 lesson): the markets assessed, the directional strategies
tested, and the deviation hypotheses are fixed here so the verdict is decided by the gate,
not by a post-hoc search for "the cell where we'd have won." Every cell defined here is
logged in `e13_13_market_grid_results.csv` (no cherry-pick). Scope = **angles 1+2 only**
(pure cached-data analysis, no model); angle 3 (model-vs-market gate) is deferred to E2.6.

## Honest bar (Miller-Davidow + E13.8)
A derivative being *less efficient* than the main line is the THESIS, not a free lunch.
Derivatives carry **higher vig + lower limits**. Nothing in this evaluation is an "edge":
the only outputs are (a) an efficiency ranking, (b) a mechanical-derivation deviation map,
and (c) a **CANDIDATE shortlist** handed to E2.6. A candidate is forward-CLV-positive net of
the derivative's own vig at PBO<0.2/DSR>0 — that verdict is E2.6/forward, **NOT here.**

## Data sources (§0.5 — cached S3, no fresh Snowflake)
- Derivative CLOSING odds: the E5.1 `s3://…/mlb/props/market={key}/season=*/date=*` backfill
  (`backfill_multisport_props_to_s3.py` — the corrected-key source the K-prop pipeline reads),
  game_pk via `mart_game_odds_bridge`.
- Realized outcomes: settled from `stg_batter_pitches` (W1–W3 stable). Main close (angle 2):
  `mart_closing_line_value`.

## Markets assessed (pre-registered)
Settled from our migrated pitch data (`stg_batter_pitches`, W1–W3 stable):

| Market key (Odds API) | Outcome | Settlement from pitch data |
|---|---|---|
| `totals_1st_5_innings` | Over/Under | F5 total runs = home + away runs through inning ≤ 5 |
| `h2h_1st_5_innings` | Home / Away (/ Draw) | sign(F5 home − F5 away); tie handled per 2-way (push) or 3-way (draw) |
| `totals_1st_1_innings` (NRFI) | Over/Under 0.5 | 1st-inning total runs; Under 0.5 = NRFI, Over 0.5 = YRFI |
| `team_totals`, `alternate_totals` | Over/Under | included IFF present (coverage stalls 2025-08-11 — flagged, not dropped) |

**Books:** every `bookmaker_key` present in the closing data is assessed individually, plus
the pre-registered groups `{all, pinnacle, soft, majors}` (majors = draftkings/fanduel/
betmgm/williamhill_us per A0.4.32). Pinnacle is the sharp anchor for the soft-vs-sharp spread.

**Seasons:** every season present (2023–2026). Reported per-season AND pooled; consistency
across seasons is a required candidate condition (a single-season hit is selection noise — the
E5.4 trap, where the in-sample winner placed 0 OOS bets).

## Angle 1 — efficiency benchmark (per market × book × season)
Extends the E13.8 main-market benchmark to derivatives. Per cell:
- **Closing Brier** of the de-vigged closing probability vs the realized binary
  (totals: P(over) vs over-hit; h2h: P(home|not-tie) vs home-won-F5, ties excluded).
- **Closing log-loss** (clamped), **vig/hold** (= implied_over+implied_under−1; expected
  higher than the ~2–5% main line), **soft-vs-sharp spread** (= |book fair − Pinnacle fair|).
- **Line MAE / RMSE** vs realized (totals), **over-rate / favorite-rate / push-rate**.
- **Calibration bias** = realized_rate − de-vigged implied_rate, with a two-sided z-test;
  multiple-comparison-controlled across all cells via Benjamini–Hochberg FDR (q=0.10). A cell
  is "mis-calibrated" only if it survives FDR AND the bias is consistent in sign across seasons.

### Pre-registered static directional strategies (the retail-bias / shading probe)
Pure data, **no model, no outcome-based side selection** (zero overfitting DOF). Each bets the
SAME side every game at the offered American price; per-$1 PnL is net of the offered vig:
- Totals (F5, NRFI, team/alt): `always_over`, `always_under`.
- H2H F5: `always_home`, `always_away`, `always_favorite` (de-vig favorite), `always_dog`.

Reported per (strategy × market × book-group × line-bucket × season). **Deflation:** the
in-sample-best static strategy is checked with **PBO via CSCV** (season-month slices × strategy)
and **DSR deflated by the number of static strategies tried**. A static strategy is a CANDIDATE
only if ROI>0 net of vig, sign-consistent across seasons, PBO<0.2 AND DSR>0. Even then it is a
CANDIDATE for E2.6, not an edge.

Line buckets (totals): `all`, `low (≤4.5)`, `mid (5–6)`, `high (≥6.5)`.

## Angle 2 — mechanical-derivation check (no outcomes used to fit the book mapping)
Do books derive F5/NRFI by a fixed rule off the consensus main line (`mart_closing_line_value`:
`close_total_line`, `close_vf_home`)? For each derivative market we fit two mappings and compare:
1. **Book's implied mapping** — book F5/NRFI implied (line or de-vig prob) ~ main close.
2. **True mapping** — realized F5/NRFI outcome ~ main close.

Pre-registered deviation hypotheses (where the TRUE relationship is expected to deviate from a
fixed fraction):
- **F5 total / main total**: a fixed fraction (~0.52–0.56) is the null; the candidate is a
  *systematic* residual of (realized F5 − book-implied F5) vs the main total (e.g. high-total
  games where the book under-shrinks, or ace-suppressed games — proxied by the main total here;
  the per-starter refinement is an E2.6 extension).
- **NRFI / main total**: P(YRFI) should rise with the main total; the candidate is a region
  where realized YRFI systematically exceeds/falls short of the book's NRFI implied.
- **F5 h2h / main h2h**: F5 home-win prob should be *less extreme* than full-game (fewer
  innings → more variance → compressed toward 0.5). The candidate is a book that fails to
  compress correctly (residual of realized F5 home-rate vs book F5 implied vs main implied).

A deviation is a CANDIDATE only if (a) the residual is systematic (sign-consistent, magnitude >
half the cell's hold), and (b) it survives the same FDR control. Magnitude < half-hold ⇒ not
exploitable ⇒ efficient (null).

## Outputs
- `e13_13_derivative_efficiency.{json,md}` — efficiency ranking + deviation map + candidate
  shortlist (or a clean "all efficient" null) + honest framing.
- `e13_13_market_grid_results.csv` — EVERY (market × book × line-bucket × season) cell and
  EVERY static strategy logged (the no-cherry-pick ledger feeding the deflation count).

## Going-in expectation (does NOT soften the gate)
Prior is poor: H2H dead ×5, main total a coin-flip (E13.8), 6 model-track no-edge confirmations.
A clean null here closes the derivative hope (with E5.4) → "value = product-quality + transparency
+ fantasy" stands. The known public lean on **NRFI unders** and the lower F5 limits are the
single most plausible place a static-bias candidate survives — the gate, not the hunch, decides.
