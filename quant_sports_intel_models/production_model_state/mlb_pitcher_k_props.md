# Production model state — MLB Pitcher-Strikeout Props (E5.x)

_PROD-STATE-1d · written 2026-08-04 · grounded in the served S3/DynamoDB artifact (live-read 2026-08-04), the E5.x ablation memos, and the serving code — NOT roadmap prose. best_alpha = 0._

> **One-line state:** a well-calibrated pitcher-strikeout predictive distribution (`strikeout_glm_v1`, calib_80 = 0.8104) served as an **honest projection + model-vs-book transparency surface** on `/props`. The prop **edge thesis is a CLEAN NULL** (E5.4: PBO 0.421 / DSR 0.246 / broad ROI −3.14% net of vig) — **no edge claim rides on this model anywhere**, and the serving payload structurally cannot make one (`is_bet_recommendation: False` baked into every payload, enforced by a forbidden-language guard test).

---

## (1) What it predicts + market/output

- **Target:** the full per-start **strikeout-count predictive distribution** for each of today's MLB probable starting pitchers (not a point estimate — a 19-point quantile grid, mean, median, std, p05–p95).
- **Market context:** the `pitcher_strikeouts` prop (over/under at the book's posted K line). The model prices `P(over/under/push)` at each book's **exact** line (half-line vs integer-line push convention handled).
- **Output surface:** the `/props` page (daily cards, one per probable starter) + `/props/[pitcherId]` detail — projection distribution, the books' posted lines, the book's **de-vigged** implied P(over), and two neutral deltas (`model_vs_book_p_over`, `model_mean_minus_line`). **No edge / EV / win-rate field exists in the payload** (E5.5 reframe, post-E5.4-null).
- Also priced at fit time but **not surfaced**: `pitcher_outs` (analytic, off the `starter_ip_v1` NegBin; calib_80 0.9016 = over-covered, diagnostic only).

## (2) Architecture — champion + why it won

- **Champion: `poisson_glm_k`** — a scikit-learn `PoissonRegressor` GLM (bundle = regressor + scaler + imputer + feature list + λ) on the market-blind recency feature set, with a coverage recalibration **λ = 0.85** applied to the spread; the predictive distribution is realized by **10,000-draw Monte-Carlo** at serve time. Source: `betting_ml/scripts/prop_pricing/fit_prop_pricing.py` (+ `betting_ml/utils/prop_pricing.py`).
- **Bake-off (E5.2, 2026-06-25, `bakeoff_strikeouts.py` → `ablation_results/e5_2_strikeout_bakeoff.md`):** 9 pre-registered configs = 7 hand-built **compound Beta-Binomial** variants (K = K-rate × batters-faced; rate-construction × framing × lineup-log5 ablations) + **LightGBM-Poisson** + **Poisson GLM**, scored under E1.1 purged walk-forward CV on CRPS + coverage@80 + PIT-KS + at-the-line ECE, **one PBO over the full grid = 0.0** (overfit risk low).
- **Why the GLM won:** selection rule = min-CRPS **among well-calibrated**. LGBM had the best raw CRPS (1.2265 vs the GLM's 1.2358) but worse PIT-KS (0.1042 vs 0.0813); the GLM had the best PIT-KS + near-best CRPS + near-zero bias (+0.087) and is interpretable. Both learned classes beat every hand-built compound variant (best compound CRPS 1.2703).
- **Fallback:** the compound Beta-Binomial (`--model compound`, analytic params JSON) is retained as the interpretable fallback; it is **not** what serves.

## (3) Feature contract (served)

Market-blind by contract (`assert_market_blind`; the K line enters only at the ECE/transparency comparison, never the model). Every predictor is strictly-prior / pregame:

- **Trailing K-rate components** (leak-clean `ROWS … 1 PRECEDING` windows): career + season strikeouts / batters-faced / outs; EB-shrunk season→career→league (pseudo-counts 250/400).
- **Recency (the E5.2 "in-season stuff change" fix, the winning feature family):** `k_pct_7d` / `k_pct_30d` trailing-window rates (effective-PA shrink 45/140 toward the career posterior), CSW last-3-starts, velocity trend — fed **raw** to the GLM (the bake-off showed recency helps only when a model weights it).
- **Workload / BF denominator:** `starter_ip_v1` outs μ + dispersion (the pre-game sub-model signal) + trailing reach rate.
- **Matchup / context (carried but proven weak):** opposing-lineup `avg_k_pct_30d` (log5; COALESCE→league), catcher framing-runs z (tempered γ = 0.04, pre-registered).
- **Serve-time frame:** `scripts/write_pitcher_k_projections.py::_TODAY_FRAME_QUERY` mirrors the fit-time `_FRAME_QUERY` as-of today (DuckDB over the S3 lakehouse), concatenated with the cached historical frame so `build_predictors` derives league/EB/log5/framing exactly as at fit time.

## (4) Training data

- **Source (fit-time):** Snowflake `baseball_data.betting.mart_starting_pitcher_game_log` (per-start K/BF/outs) + the pregame signal/feature marts (`starter_ip_signals`, lineup K, framing). ⚠️ The fit script still reads Snowflake — flagged in (9) against the lakehouse decommission. The at-the-line ECE joins the E5.1 S3 props parquet (`mlb/props/market=pitcher_strikeouts/`).
- **Window:** seasons **2021–2026**, **26,062 / 26,320 eligible starts** (BF ≥ 1, outs ≥ 1).
- **CV scheme:** **E1.1 `PurgedWalkForwardSplit`** — purged walk-forward, fit prior seasons / evaluate the next (leak-honest; recency lives in the features, not the protocol); the Beta-Binomial concentration / λ nuisance calibrations are expanding-window (season T sees only < T), fitted in-fold only.

## (5) Validation — the §0.5 gate it passed

Two separate verdicts, deliberately separated (the program's central honest-framing move):

- **Calibration (product value — PASSED; `ablation_results/e5_2_prop_pricing_calibration.md`):** purged walk-forward calib_80 = **0.8104** (floor ≥ 0.80 ✅), PIT max-decile-deviation 0.0505, mean at-the-line ECE **0.0202** (per-line 0.013–0.029 across the 3.5–9.5 ladder). Bake-off selection deflated: **PBO = 0.0** over the full 9-config grid.
- **Edge (cashability — FAILED = the E5.4 CLEAN NULL; `ablation_results/e5_4_prop_gate.md`, 2026-06-29):** over a **660-config pre-registered grid** (book-group × line-bucket × conviction τ × anchor; 582 selectable, all logged in `e5_4_config_grid_results.csv`): **PBO 0.421** (≥ 0.2 — in-sample-best does not persist OOS), **DSR 0.246** (< 0.95; observed SR +0.068 vs deflated benchmark SR0 +0.113 over 582 trials), pre-committed broad-strategy **ROI −3.14% net of vig over 44,851 bets** — negative in **every** season (2023 −5.8% … 2026 −3.6%) and **every** book (−0.7%…−5.5%). The in-sample best config (+9.30%, 214 bets) placed **0 bets out of sample**. The ~6.9% median prop hold (E5.3) eats the model's disagreement. Only-not-falsified leg: forward LIVE captured CLV (shadow harness **not built**; prior poor).

⇒ DSR is the E5.4 leg only; the served surface rests on the calibration gate, which is the correct gate for a projection product.

## (6) Serving path ⭐ (the key difference from the game models)

**NOT served through `daily_model_predictions` / `write_serving_store` / Railway PG.** The chain is:

1. **Bundle:** `s3://baseball-betting-ml-artifacts/mlb/models/prop_pricing_v1/strikeout_glm_v1.pkl` (operator-promoted; `load_artifact` S3 → gitignored local fallback).
2. **Writer:** `scripts/write_pitcher_k_projections.py` — scores today's probable starters (10,000 MC draws), joins the live K-prop book lines, assembles payloads via `betting_ml/utils/k_projection_serving.py` (the pure honest-framing module).
3. **Stores:** **DynamoDB serving cache (primary)** + **S3 fallback** at `baseball/serving/pitcher_k_projection/as_of=<date>/{<pitcher_id>.json, index.json}`.
4. **API:** `app/backend/routers/players.py` — `GET /players/k-projections` (daily index) + `GET /players/{pitcher_id}/k-projection?as_of=` (DynamoDB date-keyed → S3, today→T-2 lookback).
5. **Frontend:** `frontend/app/props/page.tsx` (cards) + `/props/[pitcherId]` (detail, `?as_of=` threaded).

**Cadence (two invokers of the same script):** the daily Dagster op **`write_pitcher_k_projections_op`** (WARN-tier, fanned from `predict_today_morning` in `daily_ingestion_job` — a failure never blocks predictions/serving) **plus** an **hourly host cron** `15 13-23,0-4 UTC` (`services/dagster/aws/capture.crontab`) so cards refresh against moving lines intraday. ⚠️ Correction to the task-brief shorthand: `write_pitcher_k_projections_op` is **not** `PROPS_DAILY_INGEST`-gated — that flag gates **`ingest_player_props_op`** (the Odds-API *lines* catch-up op, default OFF because it double-pays credits against the already-active host cron).

**Lines feed (upstream data, not the model):** `mlb/props/market=pitcher_strikeouts/` S3 parquet — hourly live capture (`backfill_multisport_props_to_s3.py --mode live`, 13-23,0-4 UTC) + daily historical catch-up (`0 13 UTC`, `--force-recent 2`). `/props` consumes **only** `pitcher_strikeouts` even though E5.0/E5.0b widened capture to 8 markets.

**Snowflake-free serving (E11.20 phase-2a, 2026-07-20):** all four writer reads (bundle, pregame frame, names/first-pitch, lines) are DuckDB-over-S3. The only residual SF touch is the `starter_ip_v1` **self-heal fallback** (fires only when today's signal is missing from S3).

## (7) Version + last retrain + cadence (reconciled against the SERVED artifact)

| what | value | evidence |
|---|---|---|
| Served `model_version` | **`strikeout_glm_v1`** | **Live S3 read 2026-08-04** of `as_of=2026-08-03/index.json` + per-pitcher payloads — matches `k_projection_serving.MODEL_VERSION` and the E5.2 memo. ✅ reconciled |
| Served bundle | `mlb/models/prop_pricing_v1/strikeout_glm_v1.pkl`, S3 LastModified **2026-07-03** | = the **sklearn-1.8.0 re-fit + re-promotion** (pickle-pin incident, roadmap 2026-07-03: "K re-fit under 1.8.0, train==serve"). Same model spec as the 2026-06-25 bake-off winner. |
| Original fit / selection | 2026-06-25 (E5.2 bake-off) | `e5_2_strikeout_bakeoff.md`, `e5_2_prop_pricing_calibration.md` |
| Serving freshness (checked) | Projections present through `as_of=2026-08-03` (16 pitchers), last write 04:15 UTC 08-04 | live S3 list (note: `aws s3 ls` prints local time — CLAUDE.md landmine) |
| Registry | ⚠️ **NOT in `sub_model_registry.yaml`** (grep: zero hits) — the version-of-record is `MODEL_VERSION` in code + the S3 bundle path | unlike the game champions, there is no registry entry to reconcile; reconciliation is code ↔ served payload ↔ memo, done above |
| Retrain cadence | **None scheduled** — fit-on-demand, operator-run (`fit_prop_pricing.py`, >1-min job). Last (re)fit 2026-07-03; no drift monitor on K calibration | fit script docstring; no cron/op invokes it |
| Payload honesty flags (live-read) | `best_alpha: 0`, `is_bet_recommendation: False`, caption + disclaimer present | `as_of=2026-08-03/index.json` |

## (8) Honest-framing status — **TRANSPARENCY-ONLY, confirmed**

`/props` carries **NO edge claim**. Verified at three layers (2026-08-04):

1. **Payload (live-read):** every served blob carries `best_alpha: 0`, `is_bet_recommendation: False`, the caption ("A projection and transparency comparison only.") and the disclaimer ("…not betting advice and we make no profitability claim…"). No edge/EV/win-rate field exists in the schema — `k_projection_serving.py` deliberately emits none; `model_vs_book_p_over` is a labeled transparency delta, not an edge.
2. **Guard test:** `test_k_projection_serving.py` greps the frontend surfaces (`pitcher-k-projection.tsx`, `/props` pages, `log-prop-button.tsx`, `log-past-prop-dialog.tsx`) for banned profitability language (`+EV` / `edge` / `value play` / `win-rate` / `profit`) — the build fails if any creeps in.
3. **Record:** E5.4's null is the reason the surface exists in this form (the post-null reframe is explicit in `k_projection_serving.py` and the E5.5 catalog entry). E9.42's "Log this prop" is bookkeeping into the user's own Bet Log, deliberately built self-contained to stay inside the honest-framing scan.

## (9) Known limitations + open follow-ups

- **No cashable edge, and no live shadow harness to ever detect one.** The E5.4 forward-CLV plan (decision-time price vs the prop's own close, ≥100 forward bets) was never built. Until it exists, the edge thesis stays closed — the offline legs are exhausted.
- **No registry entry / no drift monitoring / no scheduled retrain.** The model is a 2026-07-03 snapshot; per-season calib_80 already showed soft years in the E5.4 record (2023 0.7455, 2026 0.7622 vs the pooled 0.8104). Nothing re-checks calibration on 2026 H2 data.
- **Fit-time Snowflake dependency:** `fit_prop_pricing._FRAME_QUERY` reads `mart_starting_pitcher_game_log` via Snowflake — per the decommission rule a future re-fit needs a lakehouse repoint (the serve path is already SF-free).
- **`starter_ip_v1` hard dependency + self-heal:** the pipeline never generates *today's* `starter_ip_v1` signal (daily ops score T-2/T-1 only); the writer self-heals by regenerating on demand (`_ensure_starter_ip_signal`, incl. the S3 re-mirror per INC-25 ordering). The self-heal's fallback is still a Snowflake MERGE. If both fail, that starter is skipped (WARN, fail-soft).
- **Book-line coverage on served payloads is time-of-write-dependent:** the live lines feed overwrites `date=<today>` hourly, and the writer's last fire of a slate (04:15 UTC) can see few remaining posted lines (observed 2026-08-03: `book_count > 0` on 2/16 pitchers in the final index write; projections themselves unaffected). Earlier intraday writes carry fuller book tables. Operator-verifiable; not asserted as a defect — but worth knowing before reading a late-night index as "no lines existed."
- **Endpoint lookback is 3 days** (today→T-2 per-pitcher; use `?as_of=` for older slates).
- **Settlement of user-logged K props lags Finals** unless the Stats-API boxscore fallback path is healthy (E9.49: mart-based grading lags ≥1 day; fallback + `settled_at` shipped 2026-07-29).
- **Residual research thread (low prior):** E13.14's R4 — K-props → opposing-team-total cross-market gap — is the one un-run relation; everything else adjacent is a recorded null.

## (10) ⭐ TRIED & RESULT ledger

_So a future audit never re-recommends a dead approach. Null states per `cv_power.classify_null` where applicable._

| candidate / mechanism | when | result | source |
|---|---|---|---|
| **Compound Beta-Binomial pricer** (K = EB K-rate × BF; 7 rate/feature variants) | E5.2, 2026-06 | **LOST** the bake-off to both learned classes (best compound CRPS 1.2703 vs GLM 1.2358); retained as interpretable fallback only | `e5_2_strikeout_bakeoff.md` |
| **Hand-rolled recency K-rates** (7d/30d/blend inside the compound) | E5.2 | **HURT** (recency_vs_flat ΔCRPS +0.0337, CI excludes 0) — recency helps **only when a model weights it** (the GLM's raw-recency features), not as a constructed rate | same |
| **LightGBM-Poisson on K** | E5.2 | **LOST on calibration** — best CRPS (1.2265) but worst PIT-KS (0.1042); selection rule = min-CRPS among well-calibrated | same |
| **Poisson GLM + λ=0.85 recalibration** | E5.2 | **WON + SHIPPED** (`strikeout_glm_v1`); PBO 0.0 over the grid | same + `e5_2_prop_pricing_calibration.md` |
| **Opposing-lineup log5 matchup term** | E5.2 | **HURTS** (ΔCRPS +0.0203, CI excludes 0) — corroborates E13.2 "matchup ≈ identity". Do not re-add | `e5_2_strikeout_bakeoff.md` |
| **Catcher-framing z (tempered γ=0.04)** | E5.2 | ~inert-to-slightly-harmful (+0.0016, CI barely excludes 0); documented, not load-bearing | same |
| **K-prop betting edge (the softest-market hypothesis)** | E5.4, 2026-06-29 | **CLEAN NULL — GENUINE ABSENCE** for the offline legs: PBO 0.421, DSR 0.246, broad ROI **−3.14%** net of vig × 44,851 bets, negative every season & every book; IS-best config placed 0 OOS bets. The vig (~6.9% median hold) eats the disagreement. Re-open **only** via a live forward-CLV shadow harness (≥100 forward bets, +captured CLV net of vig) — not by re-running the backtest | `e5_4_prop_gate.md` |
| **Per-book / line-bucket / τ / anchor config search** (660 pre-registered) | E5.4 | All deflated away — 20.3% of configs positive IS, mean −2.80%; the search itself is the PBO/DSR trial count. Do not cherry-pick a book/line cell from this grid again | `e5_4_config_grid_results.csv` |
| **De-vig + model-vs-Pinnacle anchor** | E5.3, 2026-06-25 | Built (product substrate). Honest read: two-sided edge_over ≈ 0, blind-over EV **−8.7%/$1**. Name→ID bridge solved 42%→**94.6%** (normalize + last-name-first-initial + ±1-day UTC window) | `e5_3_prop_edge_summary.md`, `e5_3_join_coverage.md` |
| **Derivative markets (F5 h2h/totals, NRFI)** as the adjacent edge lane | E13.13, 2026-06-30 | **CLEAN NULL** (0/246 FDR survivors; the "3 candidates" first flagged were correlated-quote inflation — score GAME-level). Closes the derivative hope beside E5.4 | `e13_13_*` |
| **Cross-market info arbitrage (props↔team totals etc.)** | E13.14, 2026-06-30 | **CLEAN NULL** (info_gain < 0 in all 3 relations run). Residual: R4 K-props→opposing-team-total never run (low prior) | `e13_14_*` |
| **Zone-matchup signal → K pricing (E5.6)** | E13.10, 2026-06-24 | Signal = **TRUSTWORTHY NULL** (inert; 5th no-edge confirmation) → the E5.6 consumer never activated; viz shipped separately | E13.10 catalog entry |
| **E5.7 NLP injury/availability enrichment** | — | **NEVER RUN** (gated on E5.2 promise; future) — not a recorded null, just unstarted | catalog stub |
| **Slow-gate Monte-Carlo trim** (test discipline) | TD2, 2026-07-27 | Cut **DRAWS, never GAMES**: `n_games` is the statistical-power knob of the PIT/decile gates (SE = √(0.1·0.9/n)); draws only refine each CDF. draws 2000→500 = 3.9× faster, no tolerance weakened, re-proven to FAIL two-sided on known-bad r. K-pricing MC guards in `test_prop_pricing.py` are `@slow` (E11.13) | CLAUDE.md TD2 entry |
| **`starter_ip_v1` today-signal self-heal** | 2026-07-03 | **SHIPPED** — the K writer skipped every slate ("no scorable starters") because no daily op generates *today's* signal; `_ensure_starter_ip_signal` regenerates on demand + re-mirrors to S3 (INC-25 ordering). Guard: `test_k_projection_starter_ip_selfheal.py` | E5.5 memory / roadmap 2026-07-03 |
| **Serving-pickle version pin + re-fit** | 2026-07-03 | Unpinned Docker ML libs floated sklearn → `strikeout_glm_v1` failed to unpickle (`No module named '_loss'`). Cure: exact pins + build-time assert + **K re-fit under sklearn 1.8.0** and re-promoted (the served bundle's 2026-07-03 mtime). Rule: bump a pinned ML lib only alongside re-fit + re-promote | `project_serving_pickle_version_pin` memory / roadmap |
| **Snowflake-free serve path** | E11.20 phase-2a, 2026-07-20 | **SHIPPED** — all 4 hourly-writer reads moved to DuckDB-over-S3 (the hourly cron was a top-tier warehouse waker); residual SF only in the self-heal fallback | writer docstring |
| **Lines-feed hardening** (`--mode live` hourly + `--force-recent 2`) | E5.5/E9.42, 2026-07-02→09 | **SHIPPED** — the thin end-of-day live snapshot was blocking the daily backfill's idempotent skip (8 sparse dates); `--force-recent N` re-pulls the last N days. Use `backfill_multisport_props_to_s3.py`, **never** `backfill_mlb_props_to_s3.py` (422 on props) | E9.42 memory |
| **"Log this prop" bookkeeping + settlement** | E9.42 2026-07-08 / E9.49 2026-07-29 | **SHIPPED** — prop market type + settlement branch; E9.49 audit: 16/16 settled correctly but **late** (mart lags ≥1 day) → Stats-API boxscore fallback (live-Final-confirmed, starter-only, fail-safe) + `settled_at`/`settle_source`. Grading inputs now required at write time | E9.49 memory |
| **`pitcher_outs` pricing** | E5.2 | Priced analytically (calib_80 0.9016 = over-covered, diagnostic); **never surfaced** — `/props` is strikeouts-only by deliberate scope | `e5_2_prop_pricing_calibration.md` |

---

### Reconciliation summary (for the umbrella index)

- **Served version `strikeout_glm_v1` reconciled ✅** — live S3 payload (2026-08-03 slate) matches code (`k_projection_serving.MODEL_VERSION`) and the E5.2 served-record memo. Bundle mtime 2026-07-03 = the documented sklearn-1.8.0 re-fit.
- **Headline nuance for the index:** this model has **no `sub_model_registry.yaml` entry** — version-of-record lives in code + S3, so registry-based reconciliation is structurally impossible here (doc it, don't "fix" it silently).
- **Honest framing confirmed:** transparency-only; `best_alpha=0`; no edge claim anywhere on the surface, enforced by test.
