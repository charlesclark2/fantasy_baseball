# NF-W0 — V0: Weekly Data-Source Audit & Point-in-Time Feasibility

**Date:** 2026-08-04 · **Story:** NF-W0 (delivery-epic story 5) · **Branch:** `nf-w0-v0-data-audit`
**Status:** ✅ **GATE PASSED — NF-W1 is UNBLOCKED, on the `allowed_feature_contract` only.**
**`best_alpha`:** N/A (no modelling in this story) · **Parent:** `nfl_fantasy_football_weekly_projections_system_hardened_v3.md` §14 (V0)

> **How this was produced.** Every number below is **measured live** against the NFL lake
> (`s3://credence-sports-lakehouse/nfl/raw/`, DuckDB `delta_scan`) or against the nflverse release
> Parquet directly, on 2026-08-04. Appendix A of the v3 doc was treated as a **hypothesis to verify,
> not a source of truth** — and it is wrong in **both** directions (§1.2). Reproduce with the command
> in §5.

---

## 0. TL;DR — the seven decisions

1. ✅ **A leak-clean point-in-time weekly frame EXISTS and is certified.** 89,954 player-weeks,
   2016–2025 REG, QB/RB/WR/TE/FB. Train/serve parity **PASS**, leakage guard **PASS**, and the parity
   canary reads **DETECTED** (§2.4 — a parity PASS whose instrument cannot fail is worthless).
2. 🚨 **The obvious frame is the wrong one, and wrong in the flattering direction.** Building on
   `stats_player_week` — one row per player-week, `fantasy_points_ppr` included — silently deletes
   the entire zero atom. Measured 2024 wk1: 983 skill players sat on a game-day roster and only 346
   have a stats row. **41,479 of our 89,954 rows (46.1%) are retained zeros** that a stats-first
   frame would never have seen.
3. ⭐ **MAE is INVERTED for QB and TE, and is not for RB and WR — measured, per position, across all
   10 seasons.** QB and TE carry a **conditional median of exactly 0.0 in every season**; RB (~1.5)
   and WR (~2.0) do not. Per NF-D14, the median-at-the-floor is the actual test for MAE inversion
   (not the zero share). ⇒ **NF-W1 must select on CRPS and must score a degenerate all-zero ceiling
   every run** (§2.3).
4. 🎉 **The paid-charting tier is a NO-GO, and cheaply so — most of what gates V2 in the v3 doc is
   FREE for NFL.** Coverage shell, man/zone, box counts, pressure, separation, YAC-over-expected and
   aDOT are all Tier-0 via `pbp_participation` / NGS / PFR (§1.2). The genuinely gated residue is
   small: true route participation (⇒ TPRR/YPRR), first-read share, and individual OL grades.
   **Recommended spend: $0** (§1.7).
5. 🚨 **Three PIT defects found that would each have shipped silently** — realized weather posing as a
   forecast, the injury feed's only as-of timestamp deleted upstream in 2025, and a depth-chart
   schema replacement whose *semantics* shifted (§1.5). None is visible to CI; all three are now
   either in `deferred_feature_contract` or guarded.
6. ⚠️ **The current season is the weakest, not the strongest.** 2025 has no landed odds, no injury
   timestamp, and the new depth-chart shape. A historical Tuesday build is reconstructible for
   Tier-0; it is **not** reconstructible for markets or weather at all (§1.8).
7. ⛔ **NF-W1 may fit only on `allowed_feature_contract`** (10 families). `deferred_feature_contract`
   (8 families) is blocked pending named, scoped follow-ups (§3).

---

# PART 1 — THE SOURCE AUDIT

## 1.1 Reconciliation — what already lands (do NOT re-ingest)

The betting side already built essentially all of this. NF-W0 re-audits **nothing** it already owns.

| Layer | Status | Owner | What it gives the weekly model |
|---|---|---|---|
| **nflverse lake** — 32 sources, Delta, season-partitioned | ✅ LIVE | N0.2 (`football/nfl/ingest/`) | The whole Tier-0 stack: PBP, participation, player/team weeks, rosters, snaps, NGS, PFR advanced, FTN, injuries, schedules, QBR, feeder |
| **Odds API** — game lines + props | ✅ LANDED 2020–2024 (lines) / 2023–2024 (props) | N0.4 | Closing lines only — see §1.5 for why that is not a Tuesday feature |
| **`sports_dbt` NFL marts** — 22 marts + 22 staging | ✅ BUILT | N0.3 + N1.0 | `fct_player_week`, `mart_opportunity_player_week`, NGS/snap satellites, team-game + CLV marts, 3 HALT leakage gates |
| **Weather** | ❌ **NOT INGESTED** | — | *nothing* — and the field that looks like weather is a leak (§1.5) |

**Two corrections to the existing record, both measured:**

- **`nfl_mart_inventory.md` overstates `mart_opportunity_player_week`** as carrying "routes". It does
  not — `grep -i route` on that model returns nothing, and routes are not free anyway (§1.2). Harmless
  today, but it is exactly the kind of line a future story would build on.
- **`fct_player_week`'s spine-fix comment says depth_charts "has NO 2025 rows".** It has **554,215**
  — they simply carry a NULL `week`, so a week-keyed consumer saw nothing. Same symptom, different
  cause, and the difference mattered: it would **not** have self-healed, because it is a permanent
  schema replacement rather than a lagging feed. `stg_nfl_depth_charts` has **since** been fixed to
  union both eras (ASOF-bucketing the new daily `dt` snapshots to weeks) — verified working, ~590
  skill players/week for 2025 — so the plumbing is closed. The **semantic** gap is not (§1.5).

## 1.2 ⭐ Appendix A verification — it is wrong in BOTH directions

The story required verifying Appendix A rather than trusting it. It over-gates seven feature families
and under-gates one. Both errors are consequential: the first would have bought a charting contract we
do not need, the second would have shipped a feature we cannot actually build.

### (a) Appendix A says `GATED`; measured **FREE** for NFL

| Feature | Appendix A | **Measured reality (this lake)** |
|---|---|---|
| Coverage shell / man-zone | `GATED` — PFF/FTN/SIS/licensed NGS | ✅ FREE — `pbp_participation.defense_man_zone_type` + `defense_coverage_type`. man/zone **100.0%** of plays 2023-25 (38% 2018-22); coverage type 48.8% (2023-25) |
| Defensive box counts | `GATED` — NGS/PFF/FTN/SIS | ✅ FREE — `defenders_in_box` **99.98%** of plays 2023-25, 73.6% 2016-22 |
| Pressure rate | "partial free" | ✅ FREE — `was_pressure` **99.98%** 2023-25; plus PFR `times_pressured/hurried/hit/blitzed` (2018+) |
| Receiver separation | `GATED` for a stable API | ✅ FREE — NGS `avg_separation`, `avg_cushion`, **100%** non-null on covered rows ⚠️ but see the coverage caveat below |
| YAC over expectation | `GATED` for a product feed | ✅ FREE — NGS `avg_yac_above_expectation`, 99.5-99.8% of covered rows |
| aDOT / air-yard share | "free partial; paid preferred" | ✅ FREE — NGS `avg_intended_air_yards` 100%; `stats_player_week.air_yards_share`/`wopr` native |
| Personnel / formation / motion | `GATED` | ✅ FREE — `offense_personnel` **100%** 2023-25; `offense_formation`; FTN `is_motion`/`is_play_action`/`is_rpo` (2022+) |

⚠️ **The one real caveat, and it is a big one: the NGS overlay is QUALIFYING-PLAYERS-ONLY.**
`ngs_receiving` holds ~58 player-weeks per week. Against WR/TE player-weeks that **actually drew a
target** in 2024, NGS covers **39.5%** (1,253 of 3,171) — and **0%** of the frame's zero rows. So
separation / YAC-oe / aDOT are a **sparse overlay with structural missingness**, not population
features. They must carry an explicit present/absent flag and must **never be imputed to 0** (an
imputed 0 separation is a *bad* receiver, so the imputation would encode "unmeasured ⇒ bad").

### (b) Appendix A is right, and the free substitute is weaker than it sounds

**Route participation is genuinely GATED.** `pbp_participation.route` looks like the answer and is
not: it is a **single play-level string naming the route of the TARGETED receiver only** — 14 route
names over ~41% of plays. There is no per-player route attribution, so **routes-run, routes-per-
dropback, TPRR and YPRR remain unavailable free.** Appendix A's verdict stands.

What *is* free, and is the honest substitute: **`players_on_play` / `offense_players` is 100%
non-null in every season 2016–2025.** That yields per-player participation at play level, so
**dropback participation, red-zone, goal-line, third-down and two-minute participation** are all
derivable. It is an **upper bound** on routes (a blocking TE is on the field and ran no route), not a
route count — and it must be named that way in NF-W1, never labelled "routes".

## 1.3 Feature → source inventory

The machine-readable version is `ablation_results/nf_w0_feature_contract.csv` (18 families with
source, tier, license, availability, history, PIT label, fallback). It is generated from
`weekly_frame.ALLOWED_FEATURE_CONTRACT` / `DEFERRED_FEATURE_CONTRACT`, so the audit table and the
code the serving guard enforces **cannot drift apart** — the contract is the same object.

## 1.4 Licensing / redistribution review

- **nflverse (Tier 0, $0)** — free public release Parquet. ⚠️ Individual datasets have different
  *upstream* sources: `snap_counts` and `pfr_advstats` originate at **Pro-Football-Reference**, whose
  terms are not nflverse's. Fitting on them is fine; **commercial display of PFR-derived values
  warrants a licensing re-read before it reaches a paying surface.** Flagged, not blocking.
- **NGS aggregates** are published free; **raw 10 Hz tracking is not a free production API** (v3 A.1
  — confirmed, we use only the published aggregates).
- **A consumer PFF+ subscription does not include API/product rights** — product use requires PFF
  B2B. Unchanged from A.1; no contract exists.
- **The Odds API** — existing paid subscription, already used by the betting side; no new licence.
- **Open-Meteo** (the recommended weather source) — free, no key, already proven in-repo
  (`scripts/ingest_weather.py`). Commercial terms should be confirmed before a paid tier is needed.
- **No vendor was contacted in this story.** Every cost in §1.7 is a planning estimate carried from
  v3 Appendix A, which itself states costs are "planning estimates, not vendor quotes."

## 1.5 🚨 Point-in-time fidelity — the three defects that would have shipped silently

### Defect 1 — realized weather posing as a forecast (a hard leak)

`schedules.temp` / `.wind` look like weather features and are **game-book conditions recorded after
the fact**. Measured: **0 of 177** unplayed 2026 outdoor games carry a temperature, vs **173 of 178**
played 2024 games. Using them for an upcoming game injects a value that does not exist yet; using
them in a backtest injects the realized outcome. **There is no NFL weather ingestion at all**, so the
honest V1 position is roof/surface only (known at schedule release). `temp`/`wind` are in
`LEAKY_COLUMNS` and `assert_no_leakage` rejects any frame carrying them.

**⭐ CURE — reuse the MLB weather mechanism; it already has both legs NFL needs.**
`scripts/ingest_weather.py` (Open-Meteo primary, no API key; OpenWeatherMap fallback) captures three
observation types, and two of them map straight onto the weekly product:

| MLB observation type | MLB behaviour | NFL use |
|---|---|---|
| `forecast_pregame` | forecast fetched hours before first pitch | **the weekly-build feature** (Tue/Fri projection timestamps) |
| `forecast_intraday` | rolling snapshots at fixed hours-to-first-pitch checkpoints (`[24, 6, 3, 1]`, ±20 min) | **the right-before-kickoff feature** (Sunday-morning model, late swap) |
| `observed_at_first_pitch` | archive endpoint, post-game | realized conditions for evaluation only — **still a leak as a feature** |

**Three adaptations NFL needs (this is a reuse, not a copy):**

1. ⭐ **The checkpoint ladder must extend much further out.** MLB's longest checkpoint is **T-24h**,
   because a baseball slate is set a day ahead. An NFL **Tuesday** build sits ~**5 days** before a
   Sunday kickoff, and Open-Meteo forecasts 7–15 days ahead. ⇒ NFL needs roughly
   **`[120, 72, 48, 24, 3, 1]`** hours-to-kickoff so that **every projection timestamp the weekly
   product actually serves has a forecast captured at that timestamp**. Capturing only at T-24h
   would leave the Tuesday and Friday builds with no honest weather feature at all.
2. **Write S3-native, not Snowflake.** The MLB script's writer targets `statsapi.weather_raw`;
   Snowflake is being decommissioned and the NFL lake is Delta-on-S3. Reuse the **fetch + checkpoint
   + retention logic**, land it at `nfl/raw/weather/` via the existing `ingest/s3io.py` writer.
3. **Stadium coordinates are ALREADY BUILT** — `stg_nfl_team_geo` carries lat/long for all 32 teams
   (N1.0 built it for the travel-distance feature), with relocations already resolved. ⚠️ Use the
   **per-game `roof`** to decide whether a game needs weather at all, not the team's `is_dome_home` —
   that column is explicitly informational, and a dome team can play a neutral-site/international
   game outdoors.

⏳ **This is time-critical and cannot be recovered later.** A forecast is only PIT-honest if it was
captured *at the time*; the Open-Meteo **archive returns observations, not the forecast that was
current on a historical Tuesday**. The 2026 season opens **2026-09-10** — every week that passes
without capture is permanently absent from the training frame. Standing this up before week 1 is the
difference between weather being a V1 feature in 2026 and a V2 feature in 2027.

### Defect 2 — the injury feed's only as-of timestamp was deleted upstream in 2025

`injuries.date_modified` is a genuine `TIMESTAMP WITH TIME ZONE` (e.g. `2024-10-02 10:37:50-05:00`) —
the single real PIT stamp in the whole free stack. It is **100% NULL for all of 2025**. Verified
against the live nflverse release, not just our lake: **nflverse dropped the column entirely** from
`injuries_2025.parquet` (16 cols both years: `date_modified` out, `season_type` in). Our ingest's
`schema_mode='merge'` then backfilled NULLs, so **the column still appears to exist** — a silent
degradation of exactly the kind this audit is for. ⇒ from 2025 the as-of time must come from **our
own capture** (NF-W0a), which is why `injury_report` is labelled `prospective_shadow`, not
`retrospective`.

Second, subtler trap in the same feed: `report_status` is only **~46% non-null**. A NULL means *"on
the report, no designation yet"* (a Wed/Thu practice row), **not** "healthy". Treating NULL as
healthy would mislabel every mid-week injury row.

### Defect 3 — a depth-chart schema replacement with shifted semantics

nflverse replaced the feed at 2025:

| | ≤2024 | 2025+ |
|---|---|---|
| Grain | weekly, keyed (season, week, depth_team) | ESPN **near-daily snapshots** on a `dt` capture stamp (221 in 2025) |
| Rows | ~37k/season | **554,215** (2025) |
| `week` / `depth_team` | populated | **100% NULL** |
| Capture timestamp | **none** (backfilled ⇒ not PIT-reconstructible) | **`dt` present** ⇒ genuinely PIT |

A translation layer **already exists and works** — `stg_nfl_depth_charts` ASOF-buckets `dt`→week
(verified: ~590 skill players/week for 2025). So this is **not** a plumbing gap. What is unproven is
**comparability**: measured RB depth ranks run **1–3 in 2024** (≈1.08 rank-1 RBs per team-week) but
**1–6+ in 2025**. "Rank 3" denotes a different player in each era, and ranks 4–6 are unseen in
training. ⇒ deferred pending a **cross-era comparability check**, which is a scoped, cheap piece of
work — not a rebuild.

### And one label/feature boundary worth stating plainly

`weekly_rosters.status == 'INA'` is published **~90 minutes before kickoff**. It is a fine **label**
and a **leak** as a Tuesday feature. There is no nflverse game-day inactives release; the honest
pre-kickoff signal is `report_status == 'Out'`, which is a weaker and different thing. `INA` is used
in this frame to *build the label* and is in `deferred_feature_contract` as a feature.

## 1.6 The free-data minimum-viable set vs the charting-gated set

**FREE-DATA MVP (V1 — `allowed_feature_contract`, 10 families):** game context (schedule-release
facts, incl. roof/surface/rest/travel) · prior-week box + native target/air-yard shares · snap share ·
participation proxies (dropback / red-zone / goal-line / third-down / two-minute) · team environment
(pace, PROE, EPA, drives) · opponent matchup (defensive EPA/success/explosive, **coverage shell,
man/zone, box counts, pressure**) · PFR advanced (2018+) · NGS qualifying overlay (**flagged sparse**)
· injury report (split fidelity) · prior-season/draft/combine priors.

**CHARTING-GATED (V2 — genuinely unavailable free):** true route participation ⇒ routes-per-dropback,
TPRR, YPRR · first-read target share · individual OL pass-block/run-block grades and
pressures-allowed-per-lineman.

**Blocked for non-charting reasons (not a vendor problem):** weather forecast (not captured — cure is a free reuse of the MLB Open-Meteo mechanism, §1.5 Defect 1) ·
market/props at the projection timestamp (only closing snapshots landed, and none for 2025) ·
depth-chart rank (era comparability).

## 1.7 Paid-charting go/no-go — **NO-GO. Recommended spend: $0.**

The v3 doc's V2 case rests on features that, for NFL specifically, turned out to be free (§1.2a). The
residue that genuinely needs a contract is three families, and each has a defensible free substitute:

| Gated family | Planning estimate (v3 A.1 — *not* a quote) | Free substitute we already have |
|---|---|---|
| Route participation ⇒ TPRR/YPRR | FTN / PFF B2B custom quote; SIS DataHub ~$100/mo with **API rights separate** | Dropback participation from `offense_players` (upper bound, 100% coverage 2016+) |
| First-read target share | same contracts | none — excluded from V1 |
| Individual OL grades | PFF B2B quote | Unit-level: snap continuity + team pressure rate + yards-before-contact |

**Decision: do not buy for V1 or V2.** Rationale: (a) the free tier now covers most of what motivated
the buy; (b) the paid tier must prove *incremental* out-of-sample CRPS after cost (v3 §14 V2), and we
have no measurement of the free proxies' shortfall yet — buying first would make that comparison
impossible to interpret; (c) charting vendors typically supply **current** data without historical
release-time snapshots, so their value would have to be proven **prospectively** anyway (v3 §14).
**Re-evaluate only after V1 quantifies how much the dropback proxy loses against true routes** — that
measurement is the actual decision input, and it costs nothing to obtain.

## 1.8 Synthetic as-of backtest feasibility — reconstructible for WHICH features

| Feature family | Historical Tuesday build reconstructible? | Why |
|---|---|---|
| Game context, prior-week box, snaps, participation, team env, opponent, PFR, NGS | ✅ **YES — `retrospective`** | A completed game's record is immutable; nothing about week ≤ w-1 changes after the fact |
| Injury report **2009–2024** | ✅ YES | `date_modified` gives a true as-of |
| Injury report **2025+** | ⚠️ **NO — `prospective_shadow`** | Upstream deleted the timestamp (§1.5 Defect 2) |
| Depth chart **≤2024** | ❌ NO | Backfilled table, no capture stamp |
| Depth chart **2025+** | ✅ YES (but see comparability) | `dt` is a real capture series |
| **Markets / props** | ❌ **NO** | Only kickoff-minus-5min **closing** snapshots landed; a Tuesday line was never captured. 2025 not landed at all |
| **Weather forecast** | ❌ **NO** | Never captured. Open-Meteo *archive* returns **observations**, not the forecast that was current on a historical Tuesday |

⚠️ **One structural lag to design around:** a Tuesday-morning build cannot include **Monday Night
Football**. The nflverse release cadence for MNF relative to a Tuesday projection timestamp is
**unmeasured** (we have no capture history to measure it from) — so NF-W1 must either set its
projection timestamp late enough on Tuesday or treat the MNF game as a known-missing prior week.
Establishing the real lag requires forward capture ⇒ **NF-W0a**.

---

# PART 2 — THE CERTIFIED POINT-IN-TIME LABELED FRAME

Code: `football/nfl/fantasy/weekly_frame.py` (pure/IO-free) + `run_nf_w0_audit.py` (lake runner).
Guards: `betting_ml/tests/test_nf_w0_weekly_frame.py` — 19 tests, **every one RED-proven** against
deliberately-broken source (§2.7).

## 2.1 The player-week spine

**Roster-first, never stats-first.** One row per (season, week, player) for every player on the
**game-day roster** (`status ∈ {ACT, INA}`) at QB/RB/WR/TE/FB, plus constructed bye rows.

- Practice squad (`DEV`), waived (`CUT`), reserve/IR (`RES`), retired (`RET`) are excluded — measured
  2024 wk1, those four statuses contributed **474 roster rows and zero stat rows**, so they would add
  only uninformative zeros.
- **Byes are constructed, because the roster feed omits them entirely.** Measured 2024 REG:
  `weekly_rosters` holds 544 team-weeks and the schedule holds exactly 544 team-week games (32×18−32
  byes) — i.e. no roster row exists for a bye. A spine built straight off the feed silently drops
  every bye, and the model never learns that a bye is a zero knowable at schedule release.
- Bye attribution is bounded to the player's own observed roster tenure with that team, so a player
  traded in week 10 is not handed a phantom bye for his new team's week-5 off week.

**Result: 89,954 rows, 2016–2025 REG** (~9,000/season, stable across all ten seasons).

## 2.2 Versioned labels, zeros RETAINED

Every row carries `label_version`, `label_as_of_timestamp`, `scoring_system_id`, `stat_source` — a
fantasy label is itself point-in-time data (v3 §12B): official stats get corrected, and re-scoring an
old leaderboard against a later label silently changes model rankings.

| Label | Rows | Meaning |
|---|---|---|
| `played` | 63,755 | Stat line or an offensive snap |
| `dressed_no_stat` | 13,127 | ACT, team played, no line and no snap — a coaching decision |
| `inactive` | 7,671 | Declared inactive — a Sunday-morning event |
| `bye` | 5,401 | Team had no game — deterministic, knowable at schedule release |

**41,479 of 89,954 rows (46.1%) are zeros, and all are retained.** The three zero classes are kept
**distinct** rather than collapsed to "0.0": they have different knowability and different causes, and
a model that cannot tell them apart cannot express start/sit risk honestly.

`label_conflict` (flagged INA yet carrying a stat line) resolves to `played` — he demonstrably
appeared — and is **counted**, not silently resolved. Measured over 2016–2025: **0 conflicts.**

## 2.3 ⭐ Coverage by year and position — and the metric finding it forces

Full table: `ablation_results/nf_w0_coverage_by_year_position.csv`.

**Zero share** (stable across all ten seasons):

| Position | 2016 | 2020 | 2024 | 2025 | **Median fantasy points** |
|---|---|---|---|---|---|
| QB | 0.606 | 0.566 | 0.546 | 0.546 | **0.0 in all 10 seasons** |
| TE | 0.541 | 0.528 | 0.531 | 0.504 | **0.0 in 9 of 10 seasons** |
| WR | 0.429 | 0.415 | 0.426 | 0.439 | ~1.7–2.2 |
| RB | 0.440 | 0.422 | 0.379 | 0.392 | ~0.9–1.8 |

⭐ **This is the NF-D11/NF-D14 signature, measured per position over a decade.** NF-D14's refinement
is that MAE inverts when the **conditional median sits at the floor**, *not* merely when the cohort is
zero-heavy. QB and TE have a median of **exactly 0.0 in every season** ⇒ **an all-zero nihilist beats
a real projection on MAE at those positions**. RB and WR have positive medians ⇒ MAE would *not*
invert there. A single pooled metric choice would therefore be wrong for half the board.

**⇒ Binding requirement on NF-W1:** select on **CRPS** (a proper score, grading point and spread
jointly), keep interval coverage a **floor** and never a target, and **score a degenerate all-zero
ceiling every run and read its score** — do not reason about whether MAE will invert, measure it
(NF-D14's rule exists precisely because that reasoning failed once).

## 2.4 Train/serve parity — and the canary that makes the PASS mean something

**Design.** Training features are assembled from the full lake; serving features are assembled by
**the same function** from a lake slice **truncated at the projection week**. A correctly-lagged
feature is identical either way; a feature that peeks at the target week differs the moment
truncation removes it.

**Result (2024 week 10):** `train_serve_parity = PASS` — 1,588 rows both sides, 0 key-only rows
either way, 0 value mismatches.

⭐ **A parity PASS is worthless unless the instrument can fail** (NF1.7 (a): a check that cannot fail
is vacuously true). So the run also scores a **canary** — an assembly identical except for `<= week`
instead of `< week` — against the same live data:

```
parity_canary: DETECTED
  key sets differ: 25 train-only, 0 serve-only
  value mismatches: prior_week_box (285 rows), snap_share (326 rows)
```

**Certification requires all three**: leakage guard PASS **and** parity PASS **and** canary DETECTED.
A `BLIND` canary blocks exactly as a `FAIL` would, because it means the PASS carries no information.

## 2.5 Emitted status fields (`ablation_results/nf_w0_frame_status.json`)

```text
weekly_training_frame_status : CERTIFIED
weekly_serving_frame_status  : CERTIFIED_TIER0_LAGGED
point_in_time_safe           : per-feature — 10 allowed True / 8 deferred False
train_serve_parity           : PASS   (canary DETECTED)
known_missingness            : see §2.6
allowed_feature_contract     : 10 families (§1.6)
deferred_feature_contract    : 8 families (§1.6)
```

`point_in_time_safe` is stated **per feature**, not once for the frame — that is the only form in
which it is a useful answer.

## 2.6 Known missingness

| Item | Value |
|---|---|
| Overall zero share | **0.4611** (41,479 / 89,954) |
| Injury `date_modified` dropped upstream | **from 2025** |
| NGS weekly is qualifying-players-only | **true** — 39.5% of targeted WR/TE weeks, 0% of zero rows |
| depth_charts schema replaced | **at 2025** (semantics shifted, §1.5) |
| Weather forecast not ingested | **true** |
| Market snapshots landed | **2020–2024, closing only** (2025 absent) |
| Label conflicts (INA with stats) | **0** |

## 2.7 Guards — all RED-proven

19 tests, fast-gate safe (pure pandas, no IO, no `pipeline` import). Each was verified to go **red**
against deliberately-broken source before being trusted:

| Break applied to source | Result |
|---|---|
| Label join flipped to `how='inner'` (the stats-first mistake) | **3 failed** |
| Bye construction removed | **2 failed** |
| Leaky-column clause deleted | **1 failed** |
| Unknown-provenance clause deleted | **1 failed** |
| Parity's one-sided-column report removed | **1 failed** |

⭐ **On isolating an `and`-composed guard (NF-D17).** `assert_no_leakage` rejects for three
independent reasons, and a fixture tripping two of them proves neither. The unknown-provenance and
source-week clauses get fixtures satisfying every *other* clause. The leaky-column clause **cannot**
be isolated that way — every leaky name is necessarily also absent from the allowed contract — so that
test asserts on the **raised message**. A bare `pytest.raises` there would have stayed green with the
clause deleted, because the unknown-provenance clause would raise in its place. That is exactly the
break the table above proves it catches.

---

# PART 3 — THE GATE OUTPUT (what NF-W1 may and may not do)

✅ **NF-W1 is UNBLOCKED** under these binding conditions:

1. **Fit only on `allowed_feature_contract`.** `assert_no_leakage` rejects an unaudited feature —
   unknown provenance is a rejection, not a warning, because an unaudited feature has no as-of rule.
2. **Build the frame roster-first and keep the zeros.** Do not train on `stats_player_week` directly.
   ⚠️ **`fct_player_week` may or may not be a substitute — this audit did not measure it, and NF-W1
   must before relying on it.** It is spine-based and bye-inclusive by design, and its universe is
   `role_windowed UNION stat_rows`. But `role_windowed` comes from `dim_player_role`, which is
   **driven by** `stg_nfl_depth_charts` (`FROM depth_charts LEFT JOIN weekly_rosters`), so its
   population is the **depth-chart** universe (~590 skill players/week in 2025 by the translated
   path), not the **game-day-roster** universe this frame uses (~500/week). Those are different
   populations with different zero atoms, and roster `status` arrives through a LEFT JOIN that can
   yield `UNK`. ⇒ **the check to run is a row-count and zero-share diff against
   `nf_w0_coverage_by_year_position.csv`**, per season, before substituting it.
3. **Select on CRPS. Score a degenerate all-zero ceiling every run** (§2.3). MAE is inverted at QB
   and TE. Interval coverage is a floor, never a target.
4. **Treat NGS as a sparse overlay** — carry a present/absent flag; never impute 0.
5. **Do not use markets, weather, depth-chart rank, or game-day inactive status** as features.
6. **State which label version every result was scored against** (v3 §12B.3). A leaderboard compares
   candidates only within one pinned label version.

⛔ **Still blocked:** V2 charting (no contract, and NO-GO recommended), anything market-conditioned,
and anything requiring a reconstructed historical Tuesday market or forecast.

---

# PART 4 — FINDINGS HANDED TO NF-W0a / NF-W0b

**→ NF-W0a (immutable capture store)** — now has three concrete, measured justifications rather than a
general principle:
1. Capture the **injury report with our own timestamp** — upstream deleted the only as-of stamp in
   2025 (§1.5 Defect 2). Without this, current-season injury features cannot be PIT-certified.
2. Capture a **Tuesday/Friday market snapshot** — only closing lines exist, so no Tuesday market
   feature can ever be backtested (§1.8). Forward capture is the only route.
3. ⏳ **Capture weather forecasts — the most time-critical item in this audit, and the cheapest.**
   Reuse MLB's `scripts/ingest_weather.py` mechanism wholesale: `forecast_pregame` for the weekly
   build + `forecast_intraday` at hours-to-kickoff checkpoints for the right-before-kickoff surface
   (§1.5 Defect 1). Open-Meteo is free and needs no key; **stadium coordinates already exist**
   (`stg_nfl_team_geo`). Three adaptations: extend the checkpoint ladder to ~`[120, 72, 48, 24, 3, 1]`
   hours (an NFL Tuesday build is ~5 days out vs MLB's 24h max — otherwise the Tue/Fri builds get no
   weather at all), write S3-native to `nfl/raw/weather/` rather than Snowflake, and gate on the
   per-game `roof` rather than the team's informational `is_dome_home`. **A forecast cannot be
   backfilled** — the 2026 opener is **2026-09-10**, so every uncaptured week is permanently lost.
4. Also **measure the nflverse release lag**, especially for MNF, which is currently unknown.
5. Snapshot **nflverse schemas per ingest** — the 2025 `date_modified` deletion turned into an
   all-NULL column via `schema_mode='merge'`, i.e. a silent degradation that looked like a live field.

**→ NF-W0b (entity resolution)** — the lake already carries a strong crosswalk (`rosters`/`players`
hold espn/sportradar/pff/pfr/yahoo/sleeper/esb/smart ids), so the cross-vendor problem is *narrower*
than v3 §12A assumes. Two joins still need real resolution: **snap_counts** keys on `pfr_player_id`
(bridged via `weekly_rosters.pfr_id` — the unmatched rate is currently unmeasured), and **name-only
prop identities** from the Odds API, which must never be fuzzy-joined on name alone.

---

# 5. Reproduce

```bash
# LAPTOP — read-only over the S3 lake; writes the three artifacts locally. ~2 min.
cd <repo>
set -a && . ./.env && set +a
uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w0_audit \
    --seasons 2016-2025 --parity-season 2024 --parity-week 10 \
    --out quant_sports_intel_models/football/nfl/fantasy/ablation_results

# guards (fast gate)
uv run pytest betting_ml/tests/test_nf_w0_weekly_frame.py -q
```

**Artifacts:** `ablation_results/nf_w0_frame_status.json` (the seven status fields) ·
`nf_w0_coverage_by_year_position.csv` · `nf_w0_feature_contract.csv`.

_Measured live 2026-08-04 against the NFL Delta lake and the nflverse release Parquet. Row counts,
null rates and coverage shares are observed, not documented. Re-verify before any schema-dependent
build — this audit found three upstream changes in one season._
