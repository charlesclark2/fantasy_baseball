# E1.8 — Full Feature-Surface Leakage Audit

**Story:** Edge Program E1.8 · **Date:** 2026-06-18 · **Status:** ✅ AUDIT COMPLETE (construction/source + serving-parity synthesis); ⏳ two leak-signature A/B confirmations staged for the operator · **Author:** model session

> **Purpose:** generalize the E2.1b/E1.7 bullpen-leak discovery to the *whole* ~370-feature surface. E2.1b proved the program's #1/#2 feature (`bp_eb_xwoba`) was a within-row peek that purged CV missed. The PM's question: **is the bullpen leak the tip of an iceberg that explains the broad H2H+Totals offline→live collapse (corr 0.42 → 0.001), or a one-off?** This audit answers it.

---

## 1. TL;DR — the bullpen leak was the standout, not the tip of an iceberg

Swept every signal-bearing + slim-contract feature across all three targets with the E2.1b 3-test template (within-row peek / unguarded inclusive window / season-to-date including G), tracing each to its constructing dbt SQL.

**Result: the construction surface is, post-E1.7, essentially leak-free.** Exactly **two** residual construction leaks were found, **both low-magnitude**, and **neither is a major driver of the offline→live gap**:

| # | Leak | Verdict | Magnitude | In a slim contract? | Severity |
|---|---|---|---|---|---|
| 1 | **FanGraphs Stuff+ / arsenal block** (`*_stuff_plus`, `starter_avg_fastball_velo`, `fastball/breaking/offspeed_pct`, `primary_pitch_type`, `max_pitch_break_in`) | **LEAKY-season-to-date** | LOW (Stuff+ is a stable pitch-*shape* metric; a slider's shape in April ≈ September) | **YES** — `home_starter_stuff_plus` (#9 totals) + `away_starter_avg_fastball_velo` (both in the totals slim-14→21) | **MEDIUM** (gates E1.9: the contract feeds the v6 retrain) |
| 2 | **Catcher framing/defense block** (`catcher_defensive_runs`, `catcher_framing_runs`, `stolen_base_runs`) | **LEAKY-blended-current-season** (70% weight on a latest-snapshot season total) | LOW | No (noise-ranked, CI crosses 0 on home_win) | **LOW** |

Everything else — **bullpen EB (E1.7 fix confirmed present), all team/pitcher rolling, standings, ELO, pythagorean, base-state splits, lineup matchups, park, ump, injuries, OAA, and the Epic-16 sequential posteriors** — is **AS-OF-SAFE**. The single high-importance within-row leak in the whole program was the bullpen one, and it is already fixed (E1.7).

**Bottom line:** no offline number needs to be distrusted beyond the bullpen de-leak (E1.7) plus the two minor de-leaks above. The broad offline→live collapse is **NOT** explained by a pervasive family of bullpen-style construction leaks — it is dominated by **point-in-time serving skew** (the lineup-dependent strong-tier going null at morning serve), which is a serving problem already on the Epic-30.3 track, not new construction leakage. See §6.

---

## 2. Method (the E2.1b template, applied to the surface)

For each prioritized feature I traced its constructing dbt model + source mart(s) and applied:

- **T1 — within-row / same-game peek** (the `outs_in_game` pattern): does the value read game-G's own outcome, box score, usage, or actual-played roster? If it can't be computed before first pitch → LEAKY.
- **T2 — as-of guard on rolling windows**: is the window consumed via a strict `< game_date` as-of join (`row_number() … desc` rn=1) or a `… preceding and '1 day' preceding` frame? An inclusive `… preceding and current row` is LEAKY **unless** a downstream as-of join repairs it — I verified the *actual consumption*, not just the mart.
- **T3 — season-to-date including G**: do `*_season` / cumulative aggregates include game-G's contribution?
- **T4 — sequential/chained posterior**: does the posterior attached to game-G's row incorporate G's own result (chained *through* G) or only the state *entering* G (through G-1)?
- **T5 — serving-null** (the other half of the gap): is the feature important offline but null/imputed/degraded live (spined on completed-games-only, or lineup-dependent)?

**Prioritization (per AC):** top-importance clusters per target (from the E1.3 `clustered_feature_importance_{total_runs,home_win,run_diff}.md` rankings) + the three **de-leaked slim contracts** (`feature_columns_*_pruned_clustered_deleaked_2026.json`, 21/21/15). Every slim-contract feature carries an explicit verdict in §5.

---

## 3. Confirmed leaks — evidence + remediation

### Leak 1 — FanGraphs Stuff+ / arsenal block · `LEAKY-season-to-date`

**Construction (T3 fail):**
- `dbt/models/staging/fangraphs/stg_fangraphs__stuff_plus.sql:31-34,65` — grain is **one row per `fg_pitcher_id × season`**, keeping the **latest ingestion** (`row_number() over (partition by fg_pitcher_id, season order by ingestion_ts desc) … where _rn = 1`). The retained `stuff_plus` is the **full-season** value as of the last scrape.
- `dbt/models/marts/fangraphs/fct_fangraphs_pitcher_arsenal_wide.sql:7,79` — "Grain: one row per fg_pitcher_id × season"; every per-pitch Stuff+/velo/usage is a `group by fg_pitcher_id, season` aggregate.
- `dbt/models/feature/feature_pregame_starter_features.sql:609-611` — joined `af.season = year(pp.game_date)` (**current season, no `< game_date` guard**).

⇒ For any historical game G, the served Stuff+/velo/usage reflects pitches thrown **in G and every later start that season**. This is a genuine within-season future peek — and exactly the class purged CV is blind to (a within-row season aggregate, like `outs_in_game`).

**Magnitude caveat (honest):** Stuff+ is a pitch-*shape*/process metric, far more stable across a season than any outcome stat, so the *realized* leak is small. Importance is modest: `home_starter_stuff_plus` = #9 on totals (Δmae +0.0065, CI>0 — a real but small signal); **noise** on home_win (#9, CI crosses 0) and run_diff. So this is a correctness/contract-hygiene fix, not a large skill mover — but it **must** be resolved before E1.9 trusts the totals slim contract, because the contract feeds the v6 retrain.

**✅ A/B + MDA CONFIRMED (operator ran `--stuff-plus-version deleaked` on total_runs, 2026-06-18; `clustered_feature_importance_total_runs_stuffplus_deleaked.md`):** repointing the whole arsenal block to the starter's prior-season value **collapses `home_starter_stuff_plus` importance ~88%** — from #9 / Δmae **+0.00650** [+0.0017, +0.0111] (clear signal) to #21 / Δmae **+0.00075** [+0.0001, +0.0014] (near-noise-floor residual). `away_starter_avg_fastball_velo` and the pitch-type stuff_plus columns were already noise and stay noise. **Verdict: the vast majority of the Stuff+ feature's importance was the within-season peek** (same direction as bullpen, milder — bullpen → 0%, Stuff+ retains a tiny *genuine* prior-season residual). Pooled baseline MAE barely moved (3.3767→3.3769) ⇒ small accuracy impact, large *importance* inflation. Caveat: the de-leaked arm kept ~15.6% of arsenal cells leaky (28,638/155,160 rookie/no-prior fallbacks) so +0.00075 is an upper bound on the surviving signal. **Remediation = (A) prior-season repoint** (keeps the real residual, removes the peek); re-derive the totals slim contract on the clean matrix (`home_starter_stuff_plus` likely survives the prune as a marginal member; `away_starter_avg_fastball_velo` may drop as noise).

**Affected columns (all from the same source):** `*_stuff_plus` (overall + fastball/slider/curveball/changeup), `starter_avg_fastball_velo`, `starter_fastball/breaking/offspeed_pct`, `starter_primary_pitch_type`, `max_pitch_break_in` — and their home/away mirrors.

**Remediation (two options):**
- **(A) Prior-season repoint** — join `af.season = year(pp.game_date) - 1`, matching how the platoon splits (`mart_pitcher_vs_handedness_splits`, `game_year-1`) and `team_oaa_prior_season` already handle season-grain FanGraphs data. Trivially leak-free; loses within-season info; **null for rookies / first-MLB-season starters** (would impute).
- **(B) Weekly-snapshot as-of** — the raw `fg_stuff_plus_raw` is scraped repeatedly (it has `ingestion_ts`); if it retains per-week snapshots, change staging to keep them and select the latest snapshot **before** `game_date`. Cleaner (keeps current-season signal), but only as good as the snapshot cadence and requires verifying the raw history isn't already collapsed to end-state.
- **Recommendation:** ship **(A) prior-season** as the safe default for E1.9, and open (B) as a follow-up if the A/B (§7) shows the within-season signal is worth recovering. Either way, **gate via the leak-signature A/B + MDA in §7 first** — do not just swap blindly.

**✅ APPLIED (2026-06-18): option (A) shipped in dbt.** `feature_pregame_starter_features.sql:611` changed `af.season = year(pp.game_date)` → `... - 1` (arsenal join only; ZiPS left current-season — it's a safe pre-season projection). `dbtf compile` clean (14/14). ⏭️ Operator: rebuild `feature_pregame_starter_features+` (cascades to `feature_pregame_game_features`), then re-derive the totals slim contract on the refreshed matrix. ⚠️ **Interim train/serve note:** the live **v5** champions were trained on current-season Stuff+; once the rebuild lands they serve on prior-season Stuff+ → a small train/serve mismatch until **E1.9** retrains on the clean matrix. This is the **same accepted pattern as the E1.7 bullpen de-leak** (correctness now, retrain in the E1.9 batch) and is even lower-magnitude here (pooled MAE moved only 3.3767→3.3769).

### Leak 2 — Catcher framing/defense block · `LEAKY-blended-current-season` (low severity)

**Construction (T3 fail, partial):** `dbt/models/mart/mart_catcher_framing.sql:3,40-44,69-78` — metrics are `0.70 * current_season + 0.30 * prior_season`, where `current_season` = the **latest weekly snapshot per `player_id × season`** (`row_number() … order by snapshot_date desc`). Joined `cf.season = year(official_date)` (`feature_pregame_lineup_features.sql:128`). So 70% of `defensive_runs_above_average` is a season-cumulative value that, for historical games, includes post-G framing.

**Severity LOW:** `catcher_defensive_runs` is **noise-ranked** (home_win #55, CI crosses 0) and is in **no slim contract** → negligible blast radius. Also lineup-dependent (catcher identified from the posted lineup) → SERVING-NULL pre-lineup anyway.

**Remediation:** the raw `catcher_framing_raw` carries `snapshot_date`, so a proper **as-of join (latest snapshot_date `< game_date`)** is available and is the right fix; the cheap alternative is dropping the current-season weight (prior-season only). Low priority — fix opportunistically; not worth blocking E1.9.

### Non-leak worth monitoring — `starter_proj_fip` / `proj_xfip`
`feature_pregame_starter_features.sql:612-614` joins ZiPS on the **current** season (`zf.season = year(pp.game_date)`), which would be a leak **except** ZiPS is a **pre-season** projection (published before opening day, fixed thereafter) → safe today. **Flag:** flips to LEAKY the day in-season ZiPS refreshes are ingested. Add an ingestion assertion if that ever changes.

---

## 4. Per-family construction verdicts (condensed; full evidence traced to file:line)

| Family | Representative features | Verdict | Key evidence |
|---|---|---|---|
| **Bullpen EB** (E1.7) | `bp_eb_xwoba`, `bp_eb_uncertainty`, `bp_eb_coverage_pct` | **AS-OF-SAFE** ✅ (fix confirmed present) | `eb_bullpen_team_posteriors.sql:111,126` — `outs_in_game` weight + appeared-roster GONE; now `avg()` over `appearance_date < game_date` trailing-30d pool, spined on `mart_game_spine`. |
| **Sequential posteriors** (Epic 16) | `team_sequential_{woba,bullpen_xwoba,win_prob}`, `avg_eb_woba_sequential` | **AS-OF-SAFE** ✅ (consumer-enforced) | Producers write a *through-G* `posterior_mu`, but consumers read **`prior_mu`** (entering-G; `feature_pregame_game_features_raw.sql:215`, invariant `prior_mu[N]==posterior_mu[N-1]`) or apply strict `sp.game_date < l.game_date` + rn=1 (`eb_batter_posteriors_raw.sql:105`). **Hardening recommended — see §7.3.** |
| **EB batter offense** | `avg_eb_woba`, `avg_eb_iso`, `avg_eb_bb_pct` | **AS-OF-SAFE** ✅ | `eb_batter_posteriors_raw.sql:63` — `r.game_date::date < l.game_date  -- LEAKAGE GUARD`; season-to-date stats are strictly prior games. |
| **Team rolling offense** | `off_xwoba_30d`, `off_runs_per_game_*`, `avg_woba/xwoba_*`, `off_bb_pct_std` | **AS-OF-SAFE** ✅ | `mart_team_rolling_offense` uses inclusive windows BUT repaired by `offense_asof` carry-forward (`feature_pregame_team_features.sql:85-131`, `order by evt_date asc, is_demand desc` → strict `<`). No column bypasses it. |
| **Team rolling pitching** | `pit_woba_against_*`, `pit_k_pct_std`, `pit_bb_pct_*`, `pit_xwoba_7d_minus_30d` | **AS-OF-SAFE** ✅ | Same `pitching_asof` repair (`feature_pregame_team_features.sql:147-194`). Prior-audit "inclusive-repaired-downstream" claim re-verified for every column. |
| **Platoon splits (team)** | `vs_lhp_*`, `vs_rhp_*` (woba/xwoba/k/bb/hard_hit 30d) | **AS-OF-SAFE** ✅ | `mart_team_vs_pitcher_hand` inclusive → `vs_{lhp,rhp}_asof` repair (`…:211-296`). |
| **Base-state splits** | `woba_with_risp_30d`, `xwoba_with_runners_on_30d`, `woba_against_with_risp_30d` | **AS-OF-SAFE** ✅ | `mart_team_base_state_splits.sql:266-267` — `range between '30 days' preceding and '1 day' preceding` (strict-prior); state anchored at PA-start, not outcome. |
| **Bullpen rolling / usage** | `bp_xwoba_against_*`, `bp_innings_pitched_*`, `bullpen_pitches_prev_7d`, `closer_used_prev_1d/2d` | **AS-OF-SAFE** ✅ | `mart_bullpen_effectiveness` + `mart_bullpen_workload` windows all `… and '1 day' preceding`; `prev_*` strictly exclude G. |
| **Starter rolling / IP / CSW / FIP / EB** | `starter_k_pct_30d`, `whiff_rate_14d`, `csw_pct_season`, `avg_ip_season/last_3`, `appearances_30d`, `trailing_ra9/fip_30g`, `eb_*`, `eb_*_sequential` | **AS-OF-SAFE** ✅ | Marts inclusive, but consumer universally guards `… game_date < pp.game_date` + rn=1 (`feature_pregame_starter_features.sql:113,152,190,319`). "season"/"appearances" names are misleading — strict `<` excludes G. |
| **Starter platoon** | `starter_xwoba_vs_rhb`, `bb_pct_vs_rhb`, `k_pct_vs_lhb` | **AS-OF-SAFE** ✅ | `mart_pitcher_vs_handedness_splits` joined `game_year - 1` (prior season). |
| **🟥 Stuff+ / arsenal** | `*_stuff_plus`, `starter_avg_fastball_velo`, arsenal usage pcts | **LEAKY-season-to-date** ⚠️ | See §3 Leak 1 (`feature_pregame_starter_features.sql:611`, current-season, no guard). |
| **Standings / record** | `away_wins`, `away_losses`, `win_pct`, `games_back`, `pythagorean_*`, `pythagorean_win_exp_diff` | **AS-OF-SAFE** ✅ | `mart_team_season_record` cumulative-through-day BUT consumer joins `record_date = game_date - 1` (strict `<` scheduled) at `feature_pregame_team_features.sql:331-333`. The #3-on-totals `away_wins` is **clean**. |
| **ELO** | `home_elo`, `away_elo`, `elo_diff` | **AS-OF-SAFE** ✅ | `compute_elo.py:147-160` snapshots `*_before` pre-result; served = `elo_before_game` (completed) / strict-prior `elo_after_game` (scheduled), `feature_pregame_team_features.sql:444-455` (A2.3). |
| **Lineup matchups** | `lineup_avg_xwoba_vs_cluster`, `lineup_iso_vs_starter_archetype`, `lineup_vs_starter_h2h_xwoba`, `*_adj`, `lineup_archetype_pa_coverage`, comp counts | **AS-OF-SAFE** ✅ (+ **SERVING-NULL** pre-lineup) | All prior-meeting / prior-season joins: h2h `h.game_date < g.game_date` (`feature_pitcher_batter_h2h_matchups.sql:125`), cluster `bwc.game_date < g.game_date`, archetype `game_year-1`. **No within-row peek.** Lineup-dependent → null pre-lineup (§6). |
| **Park / venue** | `park_run_factor_3yr`, `runs_per_game_at_park`, `*_ft` dims, `elevation_ft`, `is_new_venue` | **AS-OF-SAFE** ✅ | `mart_park_run_factors` 3yr window joined `game_year - 1`; dims are static venue attributes. |
| **Umpire** | `ump_accuracy_zscore`, `ump_run_impact_zscore` | **AS-OF-SAFE** ✅ (+ assignment-latency serving risk) | Trailing-3yr `b.game_date < a.game_date` guard (`feature_pregame_umpire_features.sql:69`). Not an outcome leak; assigned morning (30.5). |
| **Injuries** | `injured_player_count` | **AS-OF-SAFE** ✅ (+ SERVING-NULL) | SCD-2 point-in-time `inj.valid_from <= official_date and (valid_to > official_date or null)` (`feature_pregame_lineup_features.sql:251-255`). |
| **🟨 Catcher framing** | `catcher_defensive_runs`, `catcher_framing_runs` | **LEAKY-blended-current-season** ⚠️ (low severity) | See §3 Leak 2 (`mart_catcher_framing.sql:69-78`, 70% current-season). |
| **Team OAA** | `team_oaa_prior_season` | **AS-OF-SAFE** ✅ | `prior.game_year = g.game_year - 1`; current-season OAA exists in the mart but is **NOT** surfaced as a feature (verify trainer never reads `*_current_season`). |

---

## 5. Slim-contract leakage coverage (AC: every contract feature carries a verdict)

The three de-leaked slim contracts (`*_pruned_clustered_deleaked_2026.json`) feed the E1.9 v6 retrain. Verdict for every member:

**`total_runs` (21)** — all **AS-OF-SAFE** EXCEPT:
- 🟥 `home_starter_stuff_plus` → **LEAKY-season-to-date** (Leak 1) — remediate before E1.9
- 🟥 `away_starter_avg_fastball_velo` → **LEAKY-season-to-date** (Leak 1) — remediate before E1.9
- (`away_lineup_bat_speed_vs_starter_velo` is AS-OF-SAFE but **SERVING-NULL pre-lineup**)
- Clean: `away_avg_k_pct_std`, `away_bp_eb_coverage_pct`, `away_bp_eb_uncertainty`, `away_losses`, `away_pit_k_pct_std`, `away_starter_hard_hit_pct_std`, `away_wins`, `home_bp_eb_coverage_pct`, `home_bp_eb_uncertainty`, `home_off_bb_pct_std`, `home_off_xwoba_30d`, `home_pit_woba_against_14d/30d/std`, `home_starter_avg_ip_season`, `home_starter_whiff_rate_14d`, `home_team_sequential_woba`, `park_run_factor_3yr`.

**`home_win` (21)** — **ALL AS-OF-SAFE.** (`away_lineup_iso_vs_starter_archetype`, `home_lineup_avg_woba_vs_cluster`, `home_lineup_avg_xwoba_vs_cluster` are SERVING-NULL pre-lineup.) Includes `home_bp_eb_xwoba` — AS-OF-SAFE post-E1.7; retained only as a correlated passenger of `home_team_sequential_bullpen_xwoba` (E6.7 may drop it). `elo_diff` + `pythagorean_win_exp_diff` both clean.

**`run_diff` (15)** — **ALL AS-OF-SAFE.** (`away_lineup_archetype_pa_coverage`, `home_injured_player_count` are SERVING-NULL pre-lineup.) `home_starter_csw_pct_season` despite the "season" name is strict-`<`-guarded. `home_bp_eb_xwoba` passenger as above.

➡️ **Net contract impact: 2 of 57 slim-contract slots (both totals, both Stuff+/velo) are leaky.** The H2H and run_diff contracts are fully clean. This is the only contract change E1.8 forces on E1.9.

---

## 6. Serving-parity synthesis — the *other* half of the offline→live gap

Construction-clean ≠ live-served. The dominant driver of the 0.42→0.001 collapse is **point-in-time serving skew**, already root-caused in Epic 30.3 and the Jun-2026 prod audit, and **re-confirmed here at the construction level**:

- **The feature store is not AS-OF-snapshotted.** The morning predict_today serve reads the **sparse pre-game row**; the offline 0.42 re-reads the **same game_pks after they're played (dense)**. `serving_parity_report.py` quantifies it: morning serve imputes **~110–140 of 376 features to training-median constants** (coverage 0.65–0.81); by post_lineup the slate is dense (coverage ≈0.98). On a diffuse model (top-10 ≈ 9% of |SHAP|), flattening ~30% of columns collapses the edge → live corr ≈ 0.
- **The strong-tier carriers that go null at morning serve are exactly the lineup-dependent families this audit flagged SERVING-NULL** (construction-safe, absent live): lineup-vs-cluster / archetype / vs-starter / h2h, `_adj` handedness, bat-tracking, `injured_player_count`, catcher defense — all need a confirmed lineup. Plus the bullpen-state block (pitch-derived, no scheduled carry-forward in `feature_pregame_bullpen_state_features.sql`).
- **The bullpen EB leak (now fixed) was a *double* contributor:** it was #1/#2 importance, ~100% within-row leak (MDA → 0% retained on all 3 targets), **AND** serving-null (the old appeared-roster only produced rows for completed games). E1.7 fixed both halves (de-leak + re-spine onto `mart_game_spine` → 37/37 scheduled games now populate).

**Already-shipped mitigations (not re-litigated here):** A2.3 ELO carry-forward, A2.4 archetype/RISP scheduled serving, 30.3 `predict_today` bind-to-post_lineup + per-game serving-degraded abstain, Epic-33 expected-lineup pre-lineup features.

---

## 7. Offline→live gap attribution + staged confirmations

### 7.1 How much of the 0.42→0.001 gap do the *leaks* explain?

| Contributor | Class | Share of the gap | Status |
|---|---|---|---|
| **Bullpen `bp_eb_xwoba` within-row leak** | construction leak (+ serving-null) | **Largest *named construction* slice** — it was the #1/#2 importance cluster on every target (totals Δmae +0.078, the single biggest signal cluster; home_win Δbrier +0.035 #1), and MDA showed **~100% of that rank was the peek** (collapses to 0% retained de-leaked). Removing it removes the largest offline-importance contributor on all 3 targets. | ✅ Fixed (E1.7) |
| **Stuff+ season-to-date leak** | construction leak | **Small** — modest importance (#9 totals, noise on H2H/run_diff) and a stable process metric → minor offline inflation only. Put a number on it via §7.2. | ⏳ Remediate for E1.9 |
| **Catcher framing leak** | construction leak | **Negligible** — noise-ranked, no contract. | Opportunistic |
| **Point-in-time serving skew** (lineup-dependent strong-tier null at morning serve) | **serving, not construction** | **The dominant remaining driver** — ~30% of the matrix imputed to constants at morning serve. | On the 30.3 track (bind-to-post_lineup, expected-lineup) |

**Conclusion (the trust-restoring answer the PM asked for):** the offline→live collapse is **not** a pervasive construction-leak problem. **Exactly one** high-importance within-row construction leak existed in the entire program (bullpen), and it is fixed. The two leaks E1.8 newly surfaces are both low-magnitude. The bulk of the live gap is **serving skew** — a point-in-time/availability problem, addressed by the 30.3 serving track, not by de-leaking more features. After E1.7 + the two E1.8 de-leaks, **the offline numbers (and the slim-contract choice) are trustworthy** as the *upper-bound/dense-surface* benchmark — with the standing caveat that the honest live KPI is the post_lineup `honest_live_skill.py` read, not the 0.42 dense-re-read ceiling.

### 7.2 ✅ DONE — Stuff+ leak-signature A/B + MDA collapse (the E2.1b template)
Built `clustered_feature_importance.py --stuff-plus-version deleaked` (repoints the whole season-arsenal block to the starter's prior-season arsenal, `fct_fangraphs_pitcher_arsenal_wide` `season = game_year - 1`; rookies keep the leaky value; unit-tested in `betting_ml/tests/test_stuff_plus_deleak.py`) and **the operator ran it on total_runs (2026-06-18)**:
```bash
uv run python betting_ml/scripts/clustered_feature_importance.py --target total_runs --stuff-plus-version deleaked
```
**RESULT (`clustered_feature_importance_total_runs_stuffplus_deleaked.md`):** `home_starter_stuff_plus` **#9 / Δmae +0.00650 [+0.0017, +0.0111] → #21 / +0.00075 [+0.0001, +0.0014]** — **~88% importance collapse**; the rest of the block was already noise and stayed noise; pooled baseline MAE 3.3767→3.3769 (small accuracy impact). Swap log: 155,160 cells repointed, 28,638 (~15.6%) kept leaky as rookie fallback → +0.00075 is an upper bound on the surviving signal. **Confirmed: the leak was ~the entire Stuff+ importance, with a tiny genuine prior-season residual** — direction matches bullpen, milder. home_win/run_diff not run (Stuff+ already noise there + absent from both contracts → expected no-op).
**→ Remediation = (A) prior-season repoint** at `feature_pregame_starter_features.sql:611` (`af.season = year(pp.game_date) - 1`); then **re-derive the totals slim contract** on the clean matrix before E1.9 (`home_starter_stuff_plus` likely survives the prune as a marginal CI>0 member; `away_starter_avg_fastball_velo` may drop as noise). The arm's prior-season swap IS that fix, validated.
Then: pick remediation (A prior-season in the dbt feature, or B weekly-snapshot as-of), apply it to `feature_pregame_starter_features.sql:609-611`, and **re-derive the totals slim contract on the clean matrix BEFORE E1.9 consumes it.**

### 7.3 ✅ DONE — dbt hardening tests (prevent silent regressions)
The sequential-posterior safety is **consumer-enforced** (read `prior_mu` / strict `<`), so it would silently break if anyone repoints a join to `posterior_mu`-by-game_pk or `is_current`. Shipped:
- ✅ **`dbt/tests/assert_no_leakage_sequential_posteriors.sql`** — asserts the producer chain invariant `prior_mu = lag(posterior_mu)` per (team, metric, season) on `team_sequential_posteriors`. **⚠️ Calibration note (found during CI):** a strict `> 1e-6` threshold false-fails on **405/78,735 rows (0.5%)** — verified ALL are doubleheader/re-backfill **reconstruction artifacts** (the table carries up to 3 `update_ts` versions per grain; reconstructing the chain post-hoc across versions has a noise floor of **max 0.0092**, all in one re-backfilled season). **Not leakage** — the live consumer reads `prior_mu` per game_pk and never reconstructs the chain. Threshold set to **0.02** (≈2× the artifact ceiling; a real producer break like "raw EB every game" is 0.05–0.2). **0 violations at 0.02; compiles clean.**
- ✅ **`betting_ml/tests/test_seq_asof_guard.py`** — pins the strict `<` (never `<=`, never `is_current`) in `asof_lookup.load_seq_posteriors_asof` (the player-path guard). 2 tests, green.
- (deferred) an ingestion assertion that ZiPS stays pre-season (guards `starter_proj_fip`) — low priority, only matters if in-season ZiPS refreshes are ever ingested.

### 7.4 Remediation queue (priority order)
1. ✅ **Stuff+ de-leak** (Leak 1) — **applied** (prior-season repoint in dbt); ⏭️ operator rebuild `feature_pregame_starter_features+` + re-derive totals slim contract before E1.9.
2. ✅ **Sequential-posterior regression guards** (§7.3) — **shipped** (dbt singular test @ 0.02 tolerance + asof unit test), CI green.
3. **Catcher framing as-of** (Leak 2) — low priority, opportunistic (snapshot_date as-of).

---

## 8. AC checklist

- [x] **Every top-importance + slim-contract feature carries a documented leakage verdict** — §4 (families) + §5 (all 57 slim-contract slots itemized).
- [x] **Confirmed leaks listed with remediation** — §3 (Stuff+, catcher) + §7.4 queue; owner = E1.9 prep (operator runs §7.2 first).
- [x] **Quantify how much of the offline→live gap the leaks explain** — §7.1: bullpen = largest named construction slice (fixed); Stuff+/catcher = minor; remainder = serving skew (30.3), not construction leakage.
- [x] **Honest-validation caveat respected** — de-leaking lowers offline metrics *by design*; judged on serving-parity + forward, never offline (§1, §6, §7).

**Inputs:** `clustered_feature_importance_{total_runs,home_win,run_diff}.md` (E1.3) · the three `*_deleaked_2026.json` contracts (E1.7) · `serving_parity_report.py` + Epic-30.3 / Jun-2026 prod audit. **No git commit/push (operator handles).** Model/correctness change only — no `frontend/data/changelog.json` entry.
