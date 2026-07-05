# E13.16 — Line-Movement Microstructure · PRE-REGISTRATION

**Written 2026-07-04, BEFORE any outcome or closing line was joined to a signal.** This is the
anti-data-mining contract (guide §0.5 + the E13.13 / E13.14 mirage lesson): the trajectory feature
set, the microstructure hypotheses, the segments, the bet-time anchors, the thresholds, and the
deflation are fixed HERE so the verdict is decided by the gate — not by a post-hoc search for "the
signal × segment × threshold cell where we'd have beaten the close." Every config defined here is
logged in `e13_16_signal_grid_results.csv` (no cherry-pick).

## The mechanism (why this is DIFFERENT from every prior program null)
Every prior edge probe asked **"is the PRICE right?"** — H2H (E13.8/28.5), totals (E2/E13.8), props
(E5.4), derivatives (E13.13), cross-market coherence (E13.14). All efficient (PBO≈0.5). This asks a
**different question: "does the price's own MOVEMENT reveal structure?"** Treat each game's odds line
from first-posted → first-pitch as a PRICE TIME-SERIES. The CLOSING line is efficient; the line's
TRAJECTORY toward the close may not be. The gold-standard skill measure in sports betting is **CLV —
beating the close** — and CLV is a price-vs-price quantity that does **not depend on the realized
game outcome**, so it is measurable on the trajectory alone (robust to our thin realized-outcome
sample). That is the primary gate here.

## ⚠️ ALREADY KNOWN — do NOT re-run as if new
- **"Follow Pinnacle / the sharp book" (12.10′)** → MARGINAL / no-edge (+0.0095 vs the 0.01 gate).
  The naive steam-follow is ~tapped. We include `sharp_convergence` as a **pre-registered, low-prior**
  signal (soft-book value diverges from Pinnacle → bet toward Pinnacle) only to re-measure it in
  CLV-timing units on the trajectory; a survivor would have to clear the SAME deflated bar, and the
  prior is that it does not.
- **Line-movement as a PREDICTIVE feature (Card 7.P3)** → regressed home_win Brier (+0.0011); the
  four open→close deltas add noise to prediction. That was a *prediction* question; this is a
  *timing / CLV* question — orthogonal, so 7.P3's null does not pre-decide this.

## ⚠️ THE HONEST DATA CONSTRAINT (the gating fact — states the verdict's own limits up front)
Microstructure needs FINE intra-window snapshots.
- **FINE (30-min, all books) exists only for 2026+** via the live `odds_capture` (`mart_odds_outcomes`).
  As of 2026-07-04 that is ~2.5 months of accrual.
- **HISTORICAL (2021–2025) is COARSE** — the Odds API `/odds` backfill lands ~3 snaps/day at best and,
  due to credit exhaustion, holds fine trajectories for only a few hundred events. `open→close` is
  available (via `mart_odds_line_movement` / `mart_closing_line_value`) but the intra-window PATH
  (velocity, reversals, mid-window reversion) is thin historically.

⇒ **This is a FORWARD-ACCRUING study, not a pure backtest.** The historical run is *suggestive only*;
the CLEAN honest verdict is PROSPECTIVE forward-CLV on the 30-min captures accruing NOW. The harness
is built to (a) run today on whatever fine trajectory exists, and (b) re-run as data accrues.

**Backfill lever (operator, 2026-07-04):** we hold API credits and MAY backfill additional historical
`/odds` snapshots **scoped to the two main markets (`h2h`, `totals`) only** to thicken the historical
fine-trajectory leg. If run, this upgrades the historical leg from *suggestive* toward *real* for the
static + reversion/continuation signals; it does NOT create weather/public-% history (those two are
forward-only — see H4/H5). The harness consumes a thicker snapshot cache transparently (no code change).

---

## Data sources (§0.5 — cached S3 via DuckDB, NO Snowflake at eval time; one read → parquet)
- **Odds trajectory (the price series):** `mart_odds_outcomes` (`_history` + `_current` S3 parquet) —
  one row per (snapshot_ts × event × book × market). Markets `h2h`, `totals`. Books: the curated US
  set `{pinnacle, betmgm, caesars(williamhill_us), fanduel, draftkings, fanatics, bovada}`. Leakage
  guard: `ingestion_ts < commence_time`. game_pk via `mart_game_odds_bridge`.
  — **NOT `stg_parlayapi_*`** (that source is decommissioned; excluded).
- **Realized outcomes (secondary ROI only):** settled totals + winner from `stg_batter_pitches`
  (W1–W3 stable). The PRIMARY gate (CLV) needs no outcome.
- **Weather series (H4, deferred):** `lakehouse_raw/weather_intraday_series` (S3-only, forward-only
  from 2026-07-01; `game_pk`, `captured_at`, `temp_f`, `wind_speed_mph`, `wind_direction_deg`,
  `humidity_pct`; outdoor parks only; NO precip-prob column).
- **Public-% series (H5, deferred):** `lakehouse_raw/public_betting_intraday_series` (S3-only,
  forward-only from 2026-07-01; `an_game_id` + team abbrs → game_pk via the
  `stg_actionnetwork_public_betting_snapshots` crosswalk; ML + totals money%/ticket%; FanDuel book 15).

---

## The price series (per game × book × market)
- **h2h:** the de-vigged home-win fair probability `p_home(t)` (movement in probability points).
- **totals:** the total LINE `L(t)` in runs (steam moves the number) — the classic totals-CLV unit —
  plus the de-vigged over fair prob `p_over(t)` for diagnostics.

## Trajectory features (pre-registered; computed on pre-commence snapshots, per game × book × market)
`open_val`, `close_val`, `open_close_gap` (= close − open, the total drift), `n_snaps`, `velocity`
(gap / hours spanned), `n_reversals` (sign changes of consecutive Δ), `path_length` (Σ|Δ|, total
variation), `realized_vol` (std of Δ), `max_excursion` (max |val(t) − open|), and
`retention` (= open_close_gap / max_excursion — how much of the peak move stuck vs reverted). These
are LOGGED per game; the signals below are functions of them evaluated **at a bet-time anchor** (no
peeking past the anchor).

## The bet-time anchors (WHEN we "bet now" — pre-registered, no future peeking)
The signal is evaluated using only snapshots at or before the anchor; CLV is measured anchor → close.
- `open` — the first snapshot (for the static probes).
- `t50`, `t75` — the snapshot nearest to 50% / 75% of the open→close time window (for the
  path-dependent signals). A game with only open+close (coarse-history) has no interior anchor →
  the path-dependent signals are **undefined and excluded (logged), never imputed**.

## Pre-registered microstructure signals (FORCED side — sign from trajectory only, ZERO outcome DOF)
Each signal, at its anchor and threshold θ, picks WHICH side to bet; the side is a deterministic
function of the observed trajectory, never of the realized outcome or the closing line.

| # | signal | market(s) | rule (forced side) | anchor | prior |
|---|---|---|---|---|---|
| **P** | `static_over` / `static_under` / `static_home` / `static_away` | totals / h2h | fixed side, every game | `open` | retail-bias / open-staleness probe |
| **H1** | `reversion` | totals, h2h | trigger \|open→anchor move\| ≥ θ → bet **AGAINST** the early move | t50, t75 | over-reaction → mean-reversion |
| **H2** | `continuation` (steam) | totals, h2h | same trigger → bet **WITH** the early move | t50, t75 | steam persists (opposite of H1; ≤1 can win) |
| **H3** | `sharp_convergence` | totals, h2h | \|soft_book_val − pinnacle_val\| ≥ θ at anchor → bet soft book **toward** Pinnacle | t50, t75 | LOW (12.10′ ~tapped) |
| **CTRL** | `placebo` | totals, h2h | side = parity of `game_pk` (independent of trajectory) | open | **NEGATIVE CONTROL — must NOT survive** |

**H4 (weather → total, DEFERRED — engine-ready):** align `weather_intraday_series` (hourly, per
game_pk) to the totals line trajectory; test whether a wind/temp/humidity change PRECEDES a total
move with a LAG (book latency ⇒ bet the total before it reacts). Forward-only data (from 2026-07-01)
⇒ pre-registered + assembled the moment the S3 prefix has depth; LOGGED, never silently dropped.
**H5 (public-% → line / reverse-line-movement, DEFERRED — engine-ready):** align
`public_betting_intraday_series` to the line trajectory; test reverse line movement (line moves
AGAINST the public ticket %) and whether public-% divergence predicts the remaining move. Forward-only.

## Thresholds θ (pre-registered, NOT tuned to outcomes)
- totals (line, runs): `{0.5, 1.0}` · h2h (prob points): `{0.02, 0.04}` · sharp spread: same per market.

## Segments (the multiple-comparison surface — every cell logged & deflated)
- market: `{totals, h2h}` (each signal on its natural market)
- book-group: `{all, pinnacle, soft, majors, bovada}`
- line-bucket (totals only): `{all, low ≤7.5, mid 8–9, high ≥9.5}`

Config = signal × market × book-group × (line-bucket) × θ × anchor. This is a LARGE grid → deflation
is MANDATORY.

## Primary gate metric = FORWARD CLV, net of vig, game-level, deflated
- **CLV (beat-the-close), the gate:**
  - h2h: `clv_prob(side) = p_side(close) − p_side(anchor)` (de-vigged). Positive ⇒ the market moved
    toward your side after you bet ⇒ you beat the close.
  - totals: `clv_runs(side) = (L_close − L_anchor)` for OVER, `(L_anchor − L_close)` for UNDER — the
    classic half-run-of-CLV unit; positive ⇒ the number moved in your favor.
  - **Net of vig:** the anchor price you locked embeds the offered overround; CLV is measured on the
    de-vigged fair series so the hold is not double-counted, and the realized-ROI cross-check (below)
    settles at the offered American price (vig-loaded), exactly as E13.13/E5.4.
- **Realized ROI net of vig (SECONDARY cross-check, thin sample):** settle the anchor bet at its
  offered price vs the realized outcome (`payoff_vec` / `h2h_payoff_vec`), game-level. Reported, not
  the gate — the CLV series is the gate.
- **GAME-LEVEL collapse FIRST** (the E13.13 honest bar): the book quotes on one game are correlated,
  not independent bets → per-(game×book) CLV is averaged to ONE return per game before any t-test /
  DSR / PBO (`score_game_level`).

## Deflation (anti-data-mining — the whole point)
Run PER MARKET (h2h CLV in prob-points and totals CLV in runs are different units → deflated in their
own grids; FDR pooled since p-values are unit-free), reusing the program primitives
(`betting_ml/utils/cross_market_eval.deflate_configs`):
- **PBO via CSCV** over year-month slices × selectable configs — require **< 0.2**.
- **DSR** on the in-sample-best config, deflated by the selectable-config count — require **≥ 0.95**.
- **BH-FDR** (q=0.10) over every selectable config's one-sided "CLV > 0" test.
- **Selectable** = ≥ `MIN_GAMES` (50) unique games; a survivor below `FRAGILE_GAMES` (250) is FRAGILE.
- **Season sign-consistency** required (a single-season hit is selection noise — the E5.4 trap).

## The negative control (method check — mirrors E13.14's F5 control)
`placebo` (side = game_pk parity, independent of the trajectory) MUST NOT produce a surviving
candidate. If it does, the harness manufactures CLV where none exists → the result is a method bug,
not an edge → investigate before trusting anything. The synthetic `--smoke` run additionally PLANTS a
reversion edge (must FIRE) alongside an efficient market (must stay null) to prove the engine detects
AND rejects correctly.

## Outputs
- `e13_16_line_microstructure.{json,md}` — CLV ranking per signal × segment + the deflated verdict
  (candidate shortlist for the forward-CLV leg, OR a clean "trajectory is efficient too" null) +
  honest framing (granularity caveat + forward = the real test) + the H4/H5 deferral + the accrual plan.
- `e13_16_signal_grid_results.csv` — EVERY config logged (the no-cherry-pick ledger feeding deflation).
- `_smoke` twins — synthetic proof of the engine + the control (NEVER confused with the real run).

## Going-in expectation (does NOT soften the gate)
Prior is guarded: 8 program no-edge confirmations; CLV is the hardest bar (books watch their own line
movement). A clean null CLOSES the "the trajectory is inefficient" hope and strengthens "value =
product-quality + transparency + fantasy." A survivor is a **CANDIDATE for the forward-CLV leg**
(E2.6), confirmed prospectively on the accruing 30-min captures at PBO<0.2/DSR>0 — **never declared a
live edge from the granularity-limited historical run.**
