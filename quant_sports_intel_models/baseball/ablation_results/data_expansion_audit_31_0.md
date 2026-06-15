# Story 31.0 — Data-Expansion Utilization & Orthogonality Audit

**Run:** 2026-06-15 · read-only (code mapping + Snowflake MCP coverage queries) · window 2023–2026.

**Question:** for the totals/h2h impasse — is there *unused signal content* we already have on disk, or are we
genuinely tapped out? Classify every ingested data class as **(A) tapped-out / (B) skew-pruned / (C) under-wired /
(D) new-needed**, with coverage + orthogonality behind each.

**Deployed contracts audited:** home_win v6 (`xgb_tuned_seasonnorm`, 217 cols) · run_diff v5 (`ngboost_tuned`,
175 cols) · total_runs v5 (`ngboost_tuned_seasonnorm`, 119 cols).

---

## Headline

**The orthogonal classes are mostly genuinely tapped-out or redundant — with ONE real exception: WEATHER, which is
absent from the store due to a broken staging transformation, not because it's non-predictive.** There are **zero
classic (B) skew-pruned false-negatives** among the out-of-contract classes (the serving-skew signature 30.12 found
lives in *in-contract* features → owned by 30.6, not here). So the impasse is *narrowly* solvable on the data side
(weather → totals) and otherwise confirms the signal set is largely exhausted for the base point models.

---

## Classification table

| Data class | Ingested? | In store? | In any deployed contract? | Serve coverage | Bucket | Verdict |
|---|---|---|---|---|---|---|
| **Weather** (temp/wind/humidity) | ✅ `ingest_weather` + `backfill_observed_weather` | ✅ `feature_pregame_weather_features` → joined into `game_features_raw` | **0/0/0 (pruned)** | **100% NULL 2023–25, 65% NULL 2026** | **(C) BROKEN PIPELINE** | ⭐ **FIX** — raw exists (26.6k rows) but `stg_weather_raw_snapshots` collapses to 440 → 396 feature rows (~4%). Repair the staging join → real totals run-env signal. |
| **Team OAA** (`team_oaa_prior/blended`) | ✅ `ingest_oaa` | ✅ | home_win ✓, run_diff ✓, **totals ✗** | dense (0% null) | retained / **force-include** | Dense + dropped *by totals only* → cheap forced-ablation candidate for totals (run-prevention), **low prior** (was available, dropped). |
| **Catcher framing** (`catcher_framing_runs`) | ✅ `ingest_catcher_framing` | ✅ | 0/0/0 | dense (0% null) | **(A) redundant** | Selection kept the correlated `catcher_defensive_runs` (which IS in home_win + totals); framing adds nothing over it. Leave pruned. |
| **Sprint / defense-quality** (`defense_quality_sprint_z/oaa_z/mu`) | ✅ `ingest_sprint_speed` | ✅ `sub_model_signals` + `mart_team_defense_quality_rolling` | 0/0/0 | ~80% available, 0% null (imputed) | **(A) tapped-out** | Dense-enough + dropped → non-predictive over retained defense. Leave pruned. |
| **wRC+ / fWAR** (FanGraphs hitting) | ✅ `ingest_fangraphs_hitting_leaderboard` | ✅ `lineup_features` | 0/0/0 | — | **(A) redundant** | Redundant with the wOBA/xwOBA the lineup EB already uses; lineage dead-ends at profile marts (fantasy asset). Leave pruned. |
| **Public betting %** (ActionNetwork) | ✅ `ingest_actionnetwork_betting` | ✅ dedicated `feature_pregame_public_betting_features` + `meta_model_features` | 0/0/0 | — | **BY-DESIGN (not a gap)** | Built for the **Layer-4 / CLV meta-model**, correctly excluded from base point models. Points at the bet-SELECTION layer as where edge may live. |
| **Stuff+ / Location+ / CSW** | ✅ `ingest_fangraphs_stuff_plus` | ✅ | 4/6/7 (heavily used) | retained | retained | Already a workhorse signal. |
| **Bat-tracking** (bat_speed/swing_length) | ✅ (Statcast) | ✅ | 5/1/3 | retained (2024+ era) | retained | Era-boundary note (null pre-2024) per 30.12. |
| Park / Umpire / ELO / Pythag / cluster-archetype | ✅ | ✅ | retained (various) | dense (cluster has the 24.7% coverage gap → Story 7.6) | retained | Already wired; cluster coverage = 7.6. |

---

## Ranked go / no-go list

1. **⭐ WEATHER — repair `stg_weather_raw_snapshots` (FIX, high-value-for-totals, cheap).** The single genuine new
   orthogonal signal on disk. Raw weather is plentiful (`STATSAPI.WEATHER_RAW` 26,602 rows; `STG_WEATHER_RAW`
   25,760) but the snapshot-selection/join collapses it to 440 → 396 feature rows (~4% of games), so it reads ~100%
   NULL across the train window and feature-selection had nothing to keep. Wind/temp/air-density are textbook
   run-environment drivers → directly relevant to the **totals** central estimate + the Epic-27 regime question.
   *Action:* a repair story (fix the staging join, backfill the historical feature, re-run feature selection with
   weather forced into the candidate pool). Gate the *promotion* on the champion-delta + totals calibration gate.
2. **Team-OAA for totals — ❌ CLOSED 2026-06-15, NO SIGNAL (do not fold into the retrain).** Resolved by two
   independent tests instead of a fresh hour-long retrain: (a) Story **30.4b** already classified
   `home_team_oaa_blended` + `away_team_oaa_prior_season` as **deadweight** for totals (joint ΔMAE −0.0015); (b) a
   direct univariate check on the 12,677-game training population gives combined-OAA-vs-total-runs **corr −0.023**
   (correct sign, negligible magnitude; ~0.05% of variance). Multivariate ablation and univariate correlation agree
   → genuinely tapped-out for totals. Keep it in the totals deadweight exclusion; the totals model's run-prevention
   signal already lives in bullpen xwOBA / pitcher quality. **Do NOT add team_oaa to the weather retrain candidate
   pool.**
3. **Everything else — NO-GO (leave pruned).** framing, sprint/defense-quality, wRC+/fWAR are dense-and-dropped =
   genuinely redundant/tapped-out. Public-betting is correctly Layer-4. Re-ingesting or re-wiring these is wasted
   effort.

**No (B) skew-pruned re-evaluation list** → Story 31.1 is effectively a no-op for these classes (nothing was
pruned by serving skew). 31.1's value, if any, is re-checking *after* the 30.6 serving fix lands, but this audit
predicts no false-negatives to recover here.

---

## Strategic verdict for the totals / h2h impasse

- **Totals:** one concrete data win (weather) + the architecture levers already identified (30.2 distributional
  wiring; Epic 32 generative per-side for variance). Weather is the cheapest *new-information* move; it does NOT
  replace the variance work, it complements it (better central estimate vs honest distribution are different gaps).
- **H2H:** **no data rescue.** Every orthogonal class is tapped-out, redundant, or defense (which h2h already
  has via OAA/defensive_runs). This *reinforces* the 5+ no-edge confirmations — full-game moneyline looks
  efficient to our entire feature set, old and newly-audited. Do **not** expect a base-model h2h edge from data
  expansion.
- **Where unexploited edge most plausibly lives:** the **bet-selection / CLV layer (Epic 19 / Layer 4)** — the only
  fully-built-but-base-excluded class (public-betting %) lives there by design, and market-sentiment vs model
  disagreement is a likelier edge source than squeezing an efficient full-game point model. Worth weighting in
  sequencing.

**Bottom line:** we are *mostly* tapped out on base-model data — the exception is **weather (fix the broken
pipeline)**, which is a real, cheap totals opportunity. Beyond that, totals improvement is an *architecture/variance*
problem (30.2 → Epic 32), and h2h base-model edge is unlikely from any data we have — pivot h2h energy toward
bet-selection / alt-markets.

---

## Addendum (2026-06-15) — weather root cause confirmed; "broken join" was the wrong label → see Story 31.4

The deeper dig (Story 31.4) **disproves the "broken staging join" hypothesis above.** The collapse to 396 games is
**by design, not a bug**: the entire SCD-2 chain filters `weather_observation_type = 'forecast_pregame'`, and that
observation type **only exists from 2026-05-01** (Epic T.2). The 2021–2025 history is all `observed_at_first_pitch`
(~2,300 games/yr, 100% populated) and was deliberately excluded to avoid train/serve skew. So the feature read
~null across the train window because there was *nothing of the allowed type* to read — not because a join dropped
rows.

The fix is therefore a **modeling decision** (train on observed, serve on forecast), justified by a measured,
near-unbiased substitution (2026 overlap: temp corr 0.97 / bias +0.3°F, wind corr 0.73 / bias +0.6 mph). The
pipeline rework shipped under **Story 31.4** lifts coverage **396 → 12,708 games**; the totals retrain with weather
forced into the candidate pool is the remaining signal-capture step.
