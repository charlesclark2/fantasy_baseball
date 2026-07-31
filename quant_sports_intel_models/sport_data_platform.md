# Sport Data Platform — Lean Lakehouse Architecture (shared)

**Status:** v1.0 — the canonical pre-profit data architecture for **all new sport spinoffs**.
**Last updated:** 2026-06-18 _(refresh on any material change)_
**Used by:** `football/nfl/`, `football/ncaaf/`, `basketball/ncaab/` — each sport **instantiates this pattern; it does not re-invent it.** (MLB stays on its established Snowflake/Dagster stack; this is for the pre-profit sports.)
**Parents:** `multi_sport_roadmap.md` (esp. §6) · MLB `baseball/edge_program/` conventions (§0/§6).

> **One-line thesis:** land free sport data as **Parquet in an S3 data lake**, orchestrate the pulls with **Lambda + EventBridge** (pennies, serverless, already in our AWS footprint), transform with **`dbt-duckdb` over S3** (free, in-process), serve precomputed results from the existing **Railway PG**. When a sport earns it, **swap only the layers above S3** (Lambda→Dagster, DuckDB→Snowflake) — the lake stays.

> 🚩🚩 **STALENESS CORRECTIONS — READ BEFORE COPYING ANYTHING BELOW (2026-07-13, from NCAAF-P0.1; applies to NFL + NCAAB too):** two recommendations in this doc are now WRONG — the inline examples below (Dockerfile, `sources.py`, the diagram, the reverse-ETL) are NOT yet rewritten, so do NOT copy them verbatim:
> 1. **`nfl_data_py` IS ABANDONED** — it pins `pandas==1.5.3`, which will NOT build on py3.12 (§4/§10 still recommend it). ⇒ **read the nflverse release Parquet DIRECTLY via DuckDB** `read_parquet('https://github.com/nflverse/nflverse-data/releases/download/<asset>/<asset>.parquet')` — dependency-free + lakehouse-native. Drop the `nfl_data_py` Docker dep.
> 2. **"Railway PG" is DECOMMISSIONED (INC-16).** Serving = **DynamoDB (primary) → S3 (fallback)**, same as MLB post-decommission. Do NOT stand up Railway anywhere in a new sport.
> 3. **CFBD wrong-path gotcha (NCAAF, likely other REST sources):** a wrong CFBD path returns **`200 text/html`** (a Swagger page), not a 404 → every fetcher must assert `Content-Type: application/json` + that the body parses; status 200 is NOT a success signal.
> _(A fuller doc-refresh to rewrite the inline `nfl_data_py`/Railway references is a small queued fix-up — until then this banner governs.)_

> ## 🏛️ CROSS-SPORT ARCHITECTURE DECISIONS (operator Q&A 2026-07-13 — apply to NCAAF + NFL + NCAAB)
> 1. **dbt: a SEPARATE `dbt-duckdb` project for the new sports — NOT the MLB dbt project.** MLB's dbt is Snowflake-targeted with its own manifest / `state:modified+` CI / type-contract guards; the new sports are DuckDB/S3-native with a fully DISJOINT DAG (zero cross-sport refs). Mixing adapters + inheriting MLB's Snowflake CI baggage = a mess. ⇒ **ONE new `dbt-duckdb` project shared across NCAAF/NFL/NCAAB**, with per-sport model folders + per-sport schemas (`ncaaf_staging`/`ncaaf_marts`, etc.); split into per-sport projects ONLY if they later diverge. Keeps each sport's build unable to break MLB's, and vice-versa.
> 2. **S3: a NEW sport-agnostic bucket, PREFIX-separated by sport — not the MLB bucket, not one bucket per sport.** The MLB bucket (`baseball-betting-ml-artifacts`) is baseball-named; a new bucket (e.g. `credence-sports-lakehouse`) with `s3://…/<sport>/raw/<source>/season=YYYY/…` keeps naming clean + IAM/lifecycle isolated while sharing one bucket across the new sports (cheaper + simpler than per-sport buckets). Operator: create the bucket + the instance-role grant. (Scripts are ALREADY accounted for by §2's per-sport `<sport>/ingest/` layout + shared `s3io/handler/backfill` utils.)
> 3. **Orchestration: the EXISTING self-hosted Dagster EC2 — NOT Lambda + EventBridge (the §1/§4 recommendation is now STALE).** The Lambda+EventBridge choice existed to dodge **Dagster+ metered run-minutes** — but Dagster+ is GONE (INC-16); we self-host Dagster OSS on EC2, which is UNMETERED, and the box runs 24/7 for MLB already ⇒ NCAAF's weekly ops are ~free marginal cost + inherit the box's proven patterns (dbt-runner, the tiered HALT/WARN/ALERT failure contract, the monitors). ⚠️ **ISOLATE per sport:** separate jobs/schedules/code-location namespacing so a new-sport failure can't touch MLB serving (and vice-versa). ⇒ **update §1/§4: pulls run as Dagster ops on the box, not Lambda.**

---

## 1. The pattern
```
                 EventBridge cron (weekly in-season)
                          │  {sport, sources, seasons, mode}
                          ▼
   free APIs ──▶  Lambda ingest ──▶  S3 data lake (Parquet)
   (nfl_data_py,    (fetch→Parquet)    s3://<bucket>/<sport>/raw/<source>/season=YYYY/part-*.parquet
    CFBD, Odds API)                          │
                                             ▼
                              dbt-duckdb  (reads S3 Parquet)
                              staging → marts  (free, in-process)
                                             │
                         serving marts ──────┼────▶ Railway PG  ──▶ Credence app
                         (reverse-ETL)       └────▶ (optional) marts back to S3 Parquet
   backfill (2015–present): one-off OFF-Lambda (container/EC2) using the SAME ingest fns
   migrate later: Lambda→Dagster, DuckDB→Snowflake (COPY/external tables from the SAME S3)
```

## 2. Repo layout (identical shape per sport)
```
quant_sports_intel_models/<sport>/
  <sport>_guide.md
  <sport>_data_inventory.md          # the sport's master data file
  ingest/
    s3io.py            # SHARED util: DataFrame → partitioned Parquet in S3 (copy or symlink across sports)
    sources.py         # SPORT-SPECIFIC registry: source name → fetch fn + season col + table name
    handler.py         # SHARED Lambda entrypoint (registry-driven; sport passed in the event)
    backfill.py        # SHARED off-Lambda runner for full-history pulls
    Dockerfile         # container image (deps too big for a zip)
    requirements.txt
  dbt/                 # dbt-duckdb project
    profiles.yml
    dbt_project.yml
    models/_sources.yml
    models/staging/*.sql
    models/marts/*.sql
  infra/
    eventbridge.tf     # (or serverless.yml) schedule + Lambda + IAM
```
`s3io.py`, `handler.py`, `backfill.py`, `tools/query_lake.py` (§7A), the dbt-duckdb `profiles.yml`, and the EventBridge module are **shared boilerplate** — only `sources.py`, the dbt models, and the schedule payload are sport-specific.

> 🧨 **REUSABLE BACKFILL LANDMINES (carry across ALL sports — surfaced by NCAAF-P0.6, apply equally to NFL-N0.4 + MLB backfills):**
> 1. **Season defaults MUST be clock-derived, never pinned.** A hard-coded season range (e.g. `2020–2024`) is **stale by a full season the day it merges** — P0.6 shipped pinned and silently missed 2025. Derive the default from the clock (`last_completed_season()`), and handle January conservatively so a default run never pulls an in-progress season.
> 2. **`--skip-existing` will silently PROTECT a partial/stub partition.** A 3-event `--max-events N` verification stub was preserved by a later full backfill because `--skip-existing` saw the partition as "present" — caught only by the coverage check, not the run. ⇒ re-pull a stubbed season WITHOUT the flag; never trust partition-presence as completeness.
> 3. **Ship a re-runnable acceptance check with exit 0/1** (like P0.6's `verify_odds_historical.py`) so coverage/quality can gate CI or a handoff — it's what caught both #2 and an FBS-orphan misclassification here.
> 4. **Paid per-event sources: `on_demand`-gate them out of the default backfill** so a routine free pull can never burn paid credits; the paid source must be named explicitly.
> 5. 🧨🧨 **DuckDB `CREATE SECRET … credential_chain` FAILS EAGERLY IN A ZERO-CREDENTIAL ENV → a CI-only "credential" error on a PURELY-LOCAL test (surfaced NCAAF-P0.6b 2026-07-25; the fix is SHARED so nothing else needs to change, but know the class).** `tools/query_lake._connect()` unconditionally ran `CREATE OR REPLACE SECRET … PROVIDER credential_chain`, and DuckDB VALIDATES it eagerly → raises `Secret Validation Failure: … Credential Chain: 'config'` on ANY env with zero AWS credential sources (no env vars, no profile, no instance role) — even for a query that only reads a LOCAL filesystem path. The **CI fast-gate sandbox is exactly such an env**, so any `query_lake.q()/delta()/local()` call on a local-root test/dev path fails at CONNECTION SETUP, before the query runs. ⚠️ **this masquerades as a FLAKY test** — if a swallow-any-exception bug elsewhere absorbs it (P0.6b's `_existing_raw_rows` returned `None` = "fresh partition", a silent data-loss risk), it looks like an intermittent read-after-write timing issue rather than the deterministic credential problem it is. **FIX (already shipped, shared/general): wrap the `CREATE SECRET` in try/except in `query_lake._connect()`** — a local-only read never needs it; a real S3 read with no creds still fails, just naturally at actual S3 access. Repro: strip all AWS creds from the shell → the error reproduces deterministically. ⇒ **if a future session sees a CI-only DuckDB/S3 "credential"/"Secret Validation" error on what looks like a local test, this is the class — the shared fix already covers it; don't re-swallow it.**

> 🧨🧨 **REUSABLE POINT-IN-TIME / LEAKAGE LANDMINE (cross-sport — surfaced by NCAAF-P1.1; flag to whoever owns NFL + NCAAB + any as-of mart):**
> - **A WRONG ORDERING SILENTLY SATISFIES A RIGHT FILTER — so a filter-based leakage test is worthless.** NCAAF-P1.1 found CFBD **restarts `week` at 1 for the postseason** → ordering a season by raw `week` puts the national championship *before* regular-season week 2 (2024 Ohio State had 5 games at `week≤1`, absorbed into every as-of row). The naive leakage test (recompute with `week < W` and compare) **PASSED GREEN** because it reused the model's own broken ordering. ⇒ **the as-of leakage gate MUST be DATE-based** — every contributing game must predate its own window's first kickoff (a `game_date`/kickoff-timestamp check an ordering bug cannot fool), never a same-column filter comparison. Use a monotone-in-date order column (NCAAF's `season_order_week`), never the raw reporting week/round, for any window or filter. Assume this applies to EVERY sport's calendar with a postseason/round reset (NFL playoffs, NCAAB conf tourney + March Madness).
> - **CD/CI must trigger on model-only paths.** NCAAF-P1.1 found CD didn't fire on `sports_dbt/**` (missing since N0.3) → a model-only change runs STALE on the box with a green run, AND **NFL was exposed too.** Any new dbt/model directory must be added to the CD path filter. (Also: a dbt selector matching NOTHING exits 0 → add a non-empty-selector assertion to CI.)
> - **Re-measure documented figures AFTER a fix — never carry pre-fix numbers forward** (two P1.1 doc figures were measured pre-ordering-fix and were wrong until re-audited).

> 🧨🧨 **REUSABLE SEASON-ROLLFORWARD LANDMINE — "max season PRESENT ≠ max season PLAYED" (cross-sport; hit NCAAF-P0.7 once + NFL-NF-D1 TWICE; WILL recur in NF-D2 + any NCAAB/NCAAF rollforward):** an annual roll-forward ingests the upcoming season's SCHEDULE + ROSTERS (+ depth charts) BEFORE any game is played. The instant that lands, any downstream that assumes "the newest season present = the newest season with results" silently breaks:
> - **Calendar-spine tables grow all-unplayed rows.** A roster×schedule spine (NFL `fct_player_week`, MLB `mart_game_spine`, NCAAF's scheduled universe) gains a full season of `played_flag=false` rows on ingest. ⇒ any "detect the current/base season" heuristic MUST gate on `where played_flag` (or `where <result_col> is not null`) — NF-D1's auto-detect picked the unplayed new season and tried to project the season AFTER it off nothing (opaque `KeyError`). NCAAF-P0.7's P1.2 built its universe from results-only `fact_ncaaf_team_game` (0 new-season rows) and couldn't emit — same class, inverse symptom.
> - **A pre-kickoff snapshot is not a played-week snapshot.** NFL depth-chart ASOF only maps a snapshot to a week AFTER that week's schedule start → ALL pre-kickoff snapshots are dropped by design → role/features stay pinned to LAST season. ⇒ a "current role/state" consumer needs a NO-WEEK-REQUIREMENT freshest-snapshot view (NF-D1's `stg_nfl_depth_charts_current`), not the week-mapped SCD.
> - **🔑 A (name,pos)→id CROSSWALK MUST BE DETERMINISTIC, and `played_flag` is a TIEBREAK not a FILTER (NF-D2 #6 ADP, 2026-07-26 — the same not-yet-started-season trap, inverted):** building a name→`gsis`/`player_id` map with a bare `SELECT DISTINCT` (or any un-ordered dedup) has NO stable ordering → a name-collision resolves to a DIFFERENT id per run (non-reproducible crosswalk). Fix = `group by (name,pos)` + a deterministic tiebreak like `count(*) FILTER (WHERE played_flag)` to prefer the more-established player. ⚠️ but that filter must be the TIEBREAK ONLY — using `where played_flag` as a hard FILTER kills the current not-yet-started season (all its roster rows are `played_flag=false`) → the crosswalk returns **0 matches on the live board** (e.g. the 2026 board). Same "present≠played" root, one level down in the join.
> - **⇒ AC WORDING TRAP: "populates once the schedule lands" is WRONG — it needs the season to have STARTED, not just be SCHEDULED.** Any rollforward story's acceptance for a live-data consumer must distinguish scheduled-vs-played; the pre-kickoff state is a legit no-op (verify a real prior season + a dry-run no-op, per the P0.6b "build now, verify at kickoff" pattern). CI is BLIND to all of this (mocks IO) → these only surface on a real rebuild after the season rolls.

> 🧨🧨 **REUSABLE LAKEHOUSE-MIGRATION LANDMINES (from MLB E11.20 — apply to EVERY multi-sport lakehouse replay):**
> 1. **Deleting a storage LAYOUT: grep for readers of the PATH, not the table NAME.** MLB's step-6 `s3 rm` of a compat mirror passed a pre-drop zero-reader check — but that check ran over Snowflake `access_history`, which **cannot see DuckDB/S3 path readers**. Consumers pointed at `read_parquet('<prefix>/**/*.parquet')` silently read nothing → the daily job died before predictions → **a full slate served ZERO predictions (P0)**. ⇒ before deleting/moving any S3 layout, `grep -rIn` the repo for the **PATH string** (prefix/glob), not just the table name; a table can have zero SQL consumers and many path consumers. Route reads through ONE central registrar (Delta-vs-legacy per table) + a guard test that fails any new hardcoded glob.
> 2. **Warehouse wake/idle cost follows BUCKETS-TOUCHED, not QUERY COUNT.** Halving a cron's query count barely moved the bill — a 30-min cron firing once vs twice wakes the same buckets. ⇒ attribute cost by **wake frequency / buckets touched**, never elapsed-seconds or query counts; the fix is to stop the WAKERS, not to shrink queries. Corollary design line: **the DETECTION TICK must be warehouse-free; the TRIGGERED JOB may still hit the warehouse** (the connect itself is the wake).
> 3. **Metering latency: never trust a credit read <12h after day-close** (a read showing 2.04 finalized at 4.46).

> ⭐ **REUSABLE MODELING ASSET + LESSON (from NCAAF-P1.2, 2026-07-20):**
> - **`hierarchical.py` is SPORT-AGNOSTIC — reuse it, don't rewrite.** 📍 **CANONICAL HOME = `betting_ml/utils/hierarchical.py` (PROMOTED there 2026-07-26 by E7.3 from the old football tree; football now re-exports it via a thin shim — import from the `betting_ml/utils` home, NOT the football path).** ONE solver now proven across BOTH trees: NCAAF-P1.2/P1.2b/P1A **and** baseball E7.3 (MiLB→MLB MLE) — all fast-gate green through the shim. A general penalized-Gaussian / mixed-effects (partial-pooling) engine built for NCAAF team-strength (team nested in conference). **NFL + NCAAB can use it UNCHANGED** — any sport with many entities, few games each, and a schedule too sparse for raw records to be comparable is the same problem shape. It uses a **closed-form Gaussian solver, not PyMC/NUTS** — deliberate: the model refits ~200× (season × as-of-week on leakage-safe windows), which is ~2 min closed-form vs a multi-hour NUTS job nobody re-runs; the tradeoff is an **empirical-Bayes plug-in for the variance components** (same posture as the MLB bullpen posteriors) — state it, don't hide it.
> - 🐞 **MODEL QUALITY GATES ARE BEHAVIORAL, NOT GREEN-CHECKMARK.** P1.2 found **4 real bugs that only a REAL-DATA run could catch — 3 of them SILENT** (CI mocks all IO): a maximum-likelihood **variance collapse** that silently deleted the team level (the likelihood genuinely peaks at "all teams identical" on thin fits); a **"flat" prior that was secretly a 1,000-point prior and leaked** (±913 pts of reported uncertainty on one team); a **recency-weighting bug that surfaced only as MIScalibration**, never as an error; and a **sign trap** (defense = "points prevented" ⇒ net = SUM, not difference). ⇒ **every model story needs calibration + plausibility checks on real data as an explicit gate** — a green unit-test suite cannot see this class.
> - ✅ **A leakage gate must be PROVEN to fail.** P1.2 verified its date-based gate actually fails on a **tampered row** — "so its green means something." Make that the standard for every leakage/invariant test (it's the same lesson as the P1.1 filter-vs-ordering trap, one level up).
> - ⚠️ **Distinguish PARAMETER uncertainty from a CALIBRATED predictive interval.** P1.2's `strength_margin_sd` is the former and is ~1.5× too tight to price with — any consumer must recalibrate on held-out data before deriving intervals/probabilities. Applies to every posterior-emitting model we ship. (P1.2b's freshman-prior `_sd` is the same class.)
> - ⭐ **PARTIAL-POOL IS THE PROVEN DEFAULT FOR ANY FEEDER / LEVEL-TRANSLATION PROBLEM (E7.3p, 2026-07-27).** The shared `hierarchical.py` partial-pool has now WON its bake-off **4× across 2 sports** — NCAAF-P1.2b (recruit→college) + the NFL rookie feeder + E7.3 (batter MiLB→MLB MLE) + E7.3p (pitcher MLE) — and the classic MULTIPLICATIVE factor MLE (Davenport) UNDERPERFORMED THE NULL on every metric of both E7.3 and E7.3p. ⇒ any new level-translation/feeder story LEADS with partial-pool + keeps the multiplicative form only as the interpretable FOIL; do NOT expect the factor MLE to win.
> - ⭐ **"COMPOSITE RUN-VALUE METRICS DON'T TRANSLATE ACROSS LEVELS; COMPONENT SKILLS DO" (twice-replicated — E7.3 batter + E7.3p pitcher).** wOBA (batter) AND xwOBA-against (pitcher) both came back NO-SIGNAL (tie the population/archetype prior); the COMPONENT rates translate — batter K% 0.637 / BB% 0.491 / ISO 0.429; pitcher GB% 0.551 strong, K%/BB% ~0.366 weak-but-real. ⚠️ ASYMMETRY to carry: pitcher K% translates FAR weaker than batter K% (0.366 vs 0.637 — pitcher outcomes are more role/park/defense-confounded), and for pitchers the STRONG feeder is BATTED-BALL TILT (GB%), not Ks. ⇒ a future translation story targets COMPONENT skills, never a composite; and sets edge expectations by which component is strong for that side.
> - ⭐ **BLOCKED EXTERNAL SOURCE → CHECK A TRUSTED UPSTREAM VENDOR BEFORE SCRAPING (NF-D8, 2026-07-27).** When a story names a specific site to scrape: PROBE `robots.txt` / ToS LIVE FIRST; if it disallows our crawler (`Anthropic-AI`) or blocks automation (Spotrac 403s), ⛔ do NOT build a scraper — Anthropic honors robots.txt (a hard stop, not a workaround). Then check whether an ALREADY-TRUSTED upstream vendor this repo already reads (nflverse, CFBD, MLB Stats API, Odds API) REDISTRIBUTES the same data openly — NF-D8's OverTheCap contract data was on **nflverse as CC-BY-4.0 with our exact `gsis_id`** (better than the literal ask: a plain join, no fuzzy crosswalk). If neither works, STOP and get an explicit operator call — don't improvise around a ToS block.
> - ⚠️ **`fct_player_week` COVERAGE DIAGNOSTICS MUST FILTER `played_flag` (NF-D8, NFL-fantasy).** `fct_player_week` carries STALE never-played historical-roster rows (a long-retired player still on a team's current-season week grid), so any join-match-rate / coverage denominator against it for a COMPLETED season is silently DILUTED — NF-D8 read a false ~20% that was truly 97–99% once filtered. Filter to `played_flag` for a completed season (the NF-D7 posture); not source-specific — it bites the next NFL-fantasy source doing a similar check.
> - ⭐ **DELTA-TABLE READ LANDMINES (E7.4, 2026-07-27 — two, both bit a first pass):** (1) **an ALL-NULL column POISONS a Delta table for EVERY reader** — an all-None object column → pyarrow infers `null` → Delta records `void` → `delta_scan` HARD-ERRORS `Unsupported Delta table type: 'void'` on the WHOLE table (same family as INC-17's nullable-int→DOUBLE mirror poisoning). CURE: pin dtypes at the WRITER (a typed placeholder, not None) — one place heals all consumers; ⚠️ already-written partitions keep the void schema until a full re-backfill, so consumers use the pyarrow-dataset / registered reader meanwhile. (2) **a Delta table has NO valid glob reader** — a `read_parquet('…/**/*.parquet')` glob SILENTLY reads TOMBSTONED (superseded) files, not the ACID current state (E7.4 read 3,870 rows across 3 dead generations vs the true 1,290 → FABRICATED an 84.2% match where truth was 99.3%). CURE: read a Delta table ONLY via `delta_scan` / a registered reader (e.g. `player_xref.register_board`), NEVER a parquet glob. E11.20 phase-1.5 class (the read-side sibling of the delete-a-layout landmine).
> - ⭐ **VENDOR-ID BRIDGES ARE SEASON-AGNOSTIC — join career-stable, not same-season (E7.4).** A same-season vendor-id join LOOKS reasonable but silently drops ~5% of every board — and reads 0% for 2020 (the board publishes a 2020 list, but COVID cancelled the MiLB season so the leaderboard is empty). A vendor id PAIR (FanGraphs `fg_minor_id`↔`xMLBAMID`) is CAREER-stable → take the NEWEST observation of the pair; do NOT constrain the bridge to the row's season.
> - ⭐ **A NULL SEARCH ≠ A DEFECT — keep them SEPARATE so a null-verdict story can still ship a real fix (NF1.4, 2026-07-27).** A NULL on a model SEARCH is a recorded outcome that must pass the deflation gate to CHANGE anything; a MIS-STATED INTERVAL / bad NULL-handling / miscalibrated band is a CORRECTNESS DEFECT that needs a fix, NOT a deflation gate (same as a null-handling bug). NF1.4's bake-off was a clean null AND it shipped the rookie 80% interval fix (coverage 0.680→0.790, point projection pinned unchanged) precisely because it treated the interval as a DEFECT, not a search result. ⇒ when a §0.5 story nulls, still fix the correctness defects it surfaced — don't let "the search nulled" bury a real bug. (NF1.4 corollary: a reported "level/bias" symptom can actually be a RANK/uncertainty effect around an unbiased point — MEASURE the bias before recalibrating the level.)
> - 🚨 **VENDOR-CATEGORY RELABEL / MISLABEL — NO deflation gate can see it (E7.8, 2026-07-27; PLATFORM-WIDE).** Any ingest whose VENDOR CATEGORY drives a TARGET or a POPULATION SPLIT (position, role, market type, book identity) carries this failure: mislabelled rows are WRONG BEFORE any model runs, so CV / PBO / DSR / FDR faithfully deflate a CORRUPTED target and hand back a CONFIDENT WRONG answer. E7.8: FanGraphs relabelled pitchers mid-panel (RHP/LHP →2020, then SP/SIRP/MIRP from 2021); a regex miss typed 666 relievers as batters → a fake "TRUST FV" verdict on the first run. CURE: (a) when the vendor string is ambiguous, CLASSIFY from OBJECTIVE data (E7.8 used the MiLB game logs — pitcher-majority logs ⇒ pitcher), not the vendor label; (b) a TRIPWIRE that raises when the split looks wrong (>5% of a season's "batters" have pitcher-majority logs); (c) a COHORT-COMPOSITION-by-season table is what exposed it (pitchers 565→275 while batters 569→930) — inspect population composition OVER TIME, not just aggregate rates.
> - ⭐ **DECOMPOSE AN EXTERNAL-SIGNAL LIFT AGAINST THE INCUMBENT'S OWN CONTRIBUTION (E7.8 — standard for any §0.5 study of an external signal).** "Their signal adds lift" and "their signal adds lift WE DIDN'T ALREADY HAVE" are DIFFERENT claims — only the second changes what you build. Evaluate as null → null+OURS → null+ours+THEIRS. E7.8: FanGraphs FV was REDUNDANT with our batter MLE (substitute) but COMPLEMENTARY to our pitcher MLE (adds) → the actionable "lead with FV on arms, our MLE on bats" came from the decomposition, not the raw positive lift.
> - ⭐ **A LIFT ON A SUB-MODEL'S OWN METRIC IS NOT EVIDENCE IT MOVES THE SERVED OUTCOME (E7.9, 2026-07-28 — §0.5 discipline).** E7.3p's MiLB→MLB pitcher prior cut GB% cold-start MAE −23% — a real win AT THE PITCHER-METRIC LEVEL — but wiring the resulting `eb_gb_pct` into the served totals/run-diff models returned a clean NULL (all effects ≤¼ the noise floor; every target/tier bake-off `INCUMBENT_STANDS`). The sub-model got better at its own number; that number does not propagate to game-level served skill. ⇒ **a component/sub-model metric improvement earns its place ONLY by an ablation against the SERVED outcome, never by its own-metric lift — the two are different claims, and "it improved the input by Y" is not "it changed the served prediction by X."** (E7.9 corollary — margin-gate attribution: a promotion gate that compares (contract × learner) arms conflates the FEATURE effect with a LEARNER swap; when you credit a margin to a features study, DECOMPOSE learner-fixed vs contract-fixed before attributing it, or the report claims a feature win that was mostly a learner change.)
> - 🚨 **A RAW GAP BETWEEN TWO CORRELATED RANKINGS IS REGRESSION-TO-THE-MEAN, NOT DISAGREEMENT — use the RESIDUAL (E8.0, 2026-07-29; PLATFORM-WIDE, applies to EVERY "where X and Y disagree" surface).** E8.0's first "disagreement" column was `our_score − FV_pctile`; on the real 1,286-player distribution it flagged 10 of the top 12 as "scouts higher" — including a player OUR line ranked 95th-pctile. That's not disagreement: two rankings correlated below 1.0 pull toward each other at the extremes, so the raw gap is just FV rank re-encoded (a top player is "below" the even-more-extreme scout read by construction). ⚠️ INVISIBLE on test fixtures — only the real full distribution shows it. **CURE: define disagreement as the RESIDUAL after removing the fitted X↔Y relationship** (regress one on the other, take the residual) → E8.0's column went centred (mean 0.02, sd 13.3) with symmetric labels (139 scouts-higher / 129 we're-higher / 755 agree). This is the SELECTION-METRIC-HYGIENE rule (E2.1-r) applied to a DISPLAY metric: ask what the metric must MECHANICALLY produce on the real distribution before trusting what it says. ⭐ **APPLIES TO every disagreement/fade surface we ship — the NFL "fade" view (NF3), the MLB model-vs-market confidence surface (E13.9), E13.18, the prospect board (E8.1) — a raw model-minus-market gap there is the same broken metric; use the residual.** ✅ **NOW ONE SHARED IMPLEMENTATION (E7.11, 2026-07-29): `board_assembly.residual_vs_fit`** — E8.0's ours-vs-FV and E7.11's per-source-vs-consensus and ours-vs-consensus all route through it, so the lesson can only be learned once. **QUANTIFIED on synthetic rankings that agree in expectation: the raw gap carries ≈20.6 percentile points of tail bias, the residual ≈3.6 (−82%)** — comfortably under the 15-point threshold at which either board calls something a disagreement. ⚠️ **NOT exactly unbiased, and don't claim it is:** the fit is LINEAR while two bounded rank-percentiles are related S-shaped, so a little curvature survives in the extreme deciles. Pinned by `test_prospect_consensus.py::TestResidualNotRawGap`, which asserts BOTH that the raw gap IS broken (the oracle) and that the residual is ≥3× better. 🚨 **E7.11 ALSO FOUND THE SIBLING TRAP: a source cannot disagree with a consensus it ALONE constitutes.** Its first real run reported a lopsided 89-vs-35 flag split — caused not by the rankings but by comparing 1-source rows against themselves through two different percentile denominators (the source's own ranked pool vs the consensus pool). Restricting the residual to rows ≥2 sources made it 64/63 and 100/130. **RULE: any aggregate-vs-member disagreement column must be NULL where the member IS the aggregate** — and, relatedly, a spread/`max−min` over ONE value must be NULL, never `0.0` (which renders as "every source agrees exactly", the precise opposite of what one opinion means).
> - 🧨 **A VENDOR ENCODES "NOT TRACKED HERE" AS THE NUMBER `0` → IT RENDERS AS A PERFECT SCORE (E8.0, 2026-07-29; the sentinel-zero landmine).** Prospect Savant writes `xwoba=0.0 / ev=0.0 / velo=0.0` for levels below Triple-A (batted-ball/velo tracking is AAA-only) rather than omitting the field — so a 0.000 expected-wOBA-against shipped verbatim renders a low-level pitcher as UNHITTABLE. **CURE: null the entire tracking-gated group together where the vendor uses 0 as a sentinel** (E8.0 nulled the AAA-only stats below AAA → 1,006 players have `whiff_pct` but only 404 have `xwoba`). GENERAL: any external numeric feed — CHECK whether `0` means "zero" or "absent/not-tracked" before displaying or modeling on it (a real-distribution check: an impossible-perfect `0` cluster at exactly the rows a level/coverage boundary predicts = the tell). Same family as NULL-vs-0 hygiene, but vendor-imposed and silent.
> - 🧨 **A YEAR-SCOPED / ARCHIVED VENDOR PAGE CAN SERVE LIVE (CURRENT) ENTITIES — grade the archive off the ARCHIVE, never a live join (E7.11, 2026-07-29; CROSS-SPORT + silent).** MLB's point-in-time prospect archive (a 2015 board) is genuinely as-of for the RANKS, but the `Person`/`Team` entities its page references resolve to CURRENT values — a 2015-archived Buxton returns age 32, Bryant returns COL (his current team) — so joining those live attributes onto the archived rank = HINDSIGHT LEAKAGE, invisible (no error, plausible values). Sibling trap: a bio/report LIST on an archived page can run PAST the archive season — taking the "newest" bio graded a 2015 board off a 2018 report. **CURES: (a) when reading an archived/year-scoped page, take ONLY entities/reports dated ≤ the archive season (never "newest"); (b) suffix any live-resolved field `_current` so a downstream join can't silently treat it as as-of; (c) sanity-check a known player's archived attributes against that season, not today.** ⚠️ CROSS-SPORT: any NFL/NCAAF/NCAAB vendor with a year-scoped URL (roster/rankings archives) can do exactly this — audit every as-of read of an archived page. (Also from E7.11: `.isdigit()` is NOT "is a year" — a `contentTitle` of `"201"` parsed as year 201 and won the "newest bio ≤ season" fallback; parse a 4-digit year explicitly.)
> - 🧮 **A UNIVERSE CHANGE SILENTLY REPRICES INCUMBENTS THROUGH POPULATION STATISTICS — verify max|Δ|≈0 on incumbents after adding/removing rows (NF-D11, 2026-07-29; any sport).** NF-D11 added 61 players to the projection universe (716→777) and it MOVED existing players' outputs — because in-fold POPULATION priors (positional/role per-game priors) and a z-score ENV tilt standardise their moments over the whole field, so a bigger field shifts every incumbent. First pass: **36/716 adjacent rank swaps — small enough to read as noise, large enough to be a lie.** CURE: scope every in-fold population statistic (priors, z-score means/sds) to a STABLE reference set (NF-D11 used base-anchored rows only), then ASSERT incumbents are byte-stable — after the fix, max|Δ| across all 716 = 4.5e-13, and the property was re-verified THROUGH the downstream VOR layer (all preset best-QB ranks byte-identical). **RULE: any change to a projection/ranking UNIVERSE (add rows, drop rows, merge a source — E8.0b, the multi-sport replays) must (a) compute population priors over a fixed reference, not the mutated field, and (b) prove incumbents didn't move (max|Δ|≈0) end-to-end incl. the value/scarcity layer — a handful of "noise" rank swaps is the tell that a population coupling leaked.**
> - 🧨 **A VENDOR'S PRIMARY JOIN KEY CAN BE TRANSIENTLY NULL ON FRESH ROWS (a two-release DATA RACE) → a `where key is not null` filter SILENTLY DROPS them; backfill via a SHARED SECONDARY id BEFORE the filter (NF-D12, 2026-07-29; any multi-release vendor feed).** nflverse ships `draft_picks` and `nflverse_players` as SEPARATE releases on DIFFERENT refresh cadences — a just-drafted class can land in `draft_picks` with `gsis_id` still NULL while `nflverse_players` already has the id, both keyed by the same ESPN athlete id. A pairs-mart `where gsis_id is not null` (the join key) then drops the fresh rows before the model sees them — **NOT rare: 27 of 257 (10.5%) of the 2026 class, all positions.** ⚠️ SILENT (no error), and it manifests SEASONALLY (only the newest class). **CURE: backfill the null primary key via the shared SECONDARY id (ESPN athlete id here) BEFORE the filter runs, degrade gracefully if the lookup fails; do NOT resolve rows that are legitimately null (a drafted-but-never-played player has no gsis_id forever — verify no false matches).** ⭐ THE TELL: a coverage / null-ratchet DQ test creeping toward its cap is this race accumulating — NF-D12's null-`gsis_id` ratchet (8-cap) was about to fail CI. Cross-sport: any sport joining two vendor releases on a key one release fills late (CFBD↔nflverse, MLB StatsAPI↔Savant, etc.).

> - 🎯 **FOR AN INTERVAL/COVERAGE READ, THE JOIN TO REALIZED OUTCOMES IS THE WHOLE BALLGAME — `inner` + a games filter is CORRECT FOR A RANK READ AND FATAL FOR AN INTERVAL (NF1.9, 2026-07-29; ANY population, ANY sport).** Every veteran backtest in the repo (`holdout_backtest`, `score_vs_realized`, the NF1.2/1.5 pools) joins realized `how="inner"` then keeps `g>=6` — which is right for grading a RANKING but DELETES exactly the injury / benching / release seasons an uncertainty band exists to price. NF1.9's veteran band had covered **0.545 vs nominal 0.80, unmeasured across FIVE stories**, precisely because no panel had ever scored the players who didn't play. CURE: an interval panel LEFT-joins outcomes and scores a projected-but-never-played entity as a real **0** (31% of veteran-seasons ARE 0). **RULE: before ANY interval/coverage study on ANY population (props, totals, fantasy, prospects), inspect the outcome JOIN first — an `inner` join or a min-games filter silently removes the tail the interval is supposed to cover, and the coverage number you get is off the wrong population.** (Two §0.5 corollaries from the same story live in CLAUDE.md §0.5: a zero-atom population makes a coverage *target* structurally inverted, and a peeking oracle is a floor only at MATCHED n.)
> - 📐 **A DELTA BETWEEN TWO DIFFERENTLY-SCOPED RANK SPACES IS MEANINGLESS — an OVERALL pick number minus a WITHIN-POSITION rank was silently wrong on EVERY position tab since the column shipped (NF1.6, 2026-07-30; ANY "vs consensus/ADP/market" surface).** The NF3 board's "vs ADP" delta subtracted ADP (an OVERALL draft-pick number, 1..N across all players) from the row's WITHIN-POSITION rank (1..n) → Jake Bates read **+131** (K#1 vs overall pick 131.9) and Josh Allen **+26** (QB#1 vs pick 26.6) on rows where our board and the draft room AGREE exactly. The fake delta scales with the position's draft slot, so it was invisible on early-slot positions and only K/DST (deep slots) made it obvious — but it had been wrong on QB/RB/WR/TE the whole time. CURE: rank ADP WITHIN the position first, then diff like-for-like. **RULE: before differencing two ranks/positions/percentiles, confirm they live in the SAME index space (same population, same 1..n scope) — a cross-scope subtraction produces a plausible number that scales with the scope offset, not with real disagreement.** Sibling of the E8.0 raw-gap-is-regression-to-mean lesson (a display metric whose mechanics you didn't check) and the E2.1-r selection-metric hygiene rule.
> - 🖼️ **A NEW ENTITY CLASS CAN BE CORRECT END-TO-END IN THE BACKEND AND DISCARDED/MISREAD AT THE LAST INCH BY THE FRONTEND — invisible to every backend check (NF1.6, 2026-07-30; any new position/market/entity the app surfaces).** K/DST projected, landed 74 board rows, and published to prod JSON — all backend-green — while the frontend hard-filtered them out (`SKILL_POSITIONS` check + no K/DST tab), rendered a caveat "Tier" BADGE that parsed as a tier-ONE rating (the opposite of its warning), and gap-tiered a field too flat to tier. Four operator-caught rounds, none catchable by a backend/JSON test. Also: a DST↔ADP join silently matched ZERO ("Denver Defense" vs "DEN D/ST" — normalized, no shared token) and looked identical to honest undrafted blanks (join on TEAM CODE). **RULES: when adding a new entity CLASS to a served surface, (a) grep the frontend for allow-list filters (`SKILL_POSITIONS`-style) and per-type tabs/columns that silently exclude it; (b) a caveat rendered as a BADGE/COLUMN in a rating layout reads as a rating — put low-confidence framing in PROSE, not a chip beside real ratings; (c) verify the render, not just the payload (the E9.41 dropped-field lesson, on the frontend side); (d) a name-join miss on a new class looks identical to an honest blank — join on a stable code, and assert non-zero match on a class you KNOW should match.**
> 🧨🧨 **REUSABLE LANDMINE — A DOCUMENTED JOIN KEY CAN BE WRONG, AND IT SHIPS A SILENTLY-EMPTY MART (NCAAF-P1.2b, 2026-07-21; the 3rd+ instance of the "documented ≠ real, CI can't see IO" class):** P1.2b's story AND `ncaaf_data_inventory.md` said the recruit↔college bridge was `recruiting.athleteId ↔ roster.recruitIds`. On the REAL S3 Delta lake that join matched **7 rows across 12 seasons**; the correct key `roster.recruitIds ↔ recruiting.id` (the recruiting-RECORD id, not the ESPN-style athlete id, a different number space) matched **60,883** → ~18k usable pairs. **Had the session coded to the docs, the whole mart would have been EMPTY, compiled GREEN, passed CI (which mocks IO), and shipped a silently-DEAD feature** — undetectable except by hitting the real data. ⇒ **RULE: for ANY real-data JOIN, verify the KEY on the real lake before trusting it — match-row-count the documented key AND at least one alternative; a plausible-but-wrong key produces a green-everywhere empty result.** Compile-green + CI-green are necessary-NOT-sufficient for a join (the runtime-gate rule, applied to keys). Same family as the E11.20 "grep the PATH not the table name" P0 and the P1.1 "verify the ordering on real data" leak. Fix the inventory doc when you find a bad key so the next session doesn't rediscover it.

## 3. S3 lake conventions
- **Key scheme:** `s3://<bucket>/<sport>/raw/<source>/season=YYYY/part-0000.parquet` (one logical table per `source`; partition by `season`, add `/week=NN/` only where natural).
- **Idempotent writes:** each run **overwrites the (source, season) partition** (delete-prefix → put). Weekly incremental = re-pull the *current* season and rewrite just that partition. Backfill = all seasons, once, off-Lambda.
- **Format:** Parquet (snappy) via pyarrow; preserve dtypes (pandas→pyarrow). Lowercase column names.
- **One bucket, many sports** (prefix-isolated) keeps IAM + cost simple.

## 4. Ingest scaffold (copy-paste starting point)

**`ingest/s3io.py`** — shared:
```python
import io, boto3, pyarrow as pa, pyarrow.parquet as pq
_s3 = boto3.client("s3")

def write_partition(df, bucket, sport, source, season, *, week=None):
    """Overwrite one (source, season[, week]) partition with a single Parquet object."""
    prefix = f"{sport}/raw/{source}/season={season}" + (f"/week={week}" if week is not None else "")
    # clear existing objects under the partition (idempotent)
    for page in _s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix + "/"):
        objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if objs: _s3.delete_objects(Bucket=bucket, Delete={"Objects": objs})
    buf = io.BytesIO()
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), buf, compression="snappy")
    _s3.put_object(Bucket=bucket, Key=f"{prefix}/part-0000.parquet", Body=buf.getvalue())
    return len(df)
```

**`ingest/sources.py`** — sport-specific (NFL shown; the prior notebook's exact list):
```python
import nfl_data_py as nfl
# registry: source_name -> (fetch(seasons)->DataFrame, season_col)
SOURCES = {
    "weekly_data":            (lambda yrs: nfl.import_weekly_data(yrs),                 "season"),
    "weekly_rosters":         (lambda yrs: nfl.import_weekly_rosters(yrs),              "season"),
    "rosters":                (lambda yrs: nfl.import_seasonal_rosters(yrs),            "season"),
    "schedules":              (lambda yrs: nfl.import_schedules(yrs),                   "season"),
    "depth_charts":           (lambda yrs: nfl.import_depth_charts(yrs),                "season"),
    "snap_counts":            (lambda yrs: nfl.import_snap_counts(yrs),                 "season"),
    "combine_data":           (lambda yrs: nfl.import_combine_data(yrs),                "season"),
    "draft_picks":            (lambda yrs: nfl.import_draft_picks(yrs),                 "season"),
    "injuries":               (lambda yrs: nfl.import_injuries(yrs),                    "season"),  # NEW (was missing)
    "passing_next_gen_stats":   (lambda yrs: nfl.import_ngs_data("passing", yrs),       "season"),
    "rushing_next_gen_stats":   (lambda yrs: nfl.import_ngs_data("rushing", yrs),       "season"),
    "receiving_next_gen_stats": (lambda yrs: nfl.import_ngs_data("receiving", yrs),     "season"),
    "passing_pro_football_ref":   (lambda yrs: nfl.import_weekly_pfr("pass", yrs),      "season"),
    "rushing_pro_football_ref":   (lambda yrs: nfl.import_weekly_pfr("rush", yrs),      "season"),
    "receiving_pro_football_ref": (lambda yrs: nfl.import_weekly_pfr("rec", yrs),       "season"),
}
```

**`ingest/handler.py`** — shared Lambda entrypoint (registry-driven):
```python
import os, importlib
from s3io import write_partition

def lambda_handler(event, _ctx=None):
    sport   = event["sport"]                       # "nfl" | "ncaaf" | "ncaab"
    seasons = event["seasons"]                     # e.g. [2026] incremental, or a backfill range
    names   = event.get("sources")                 # None => all
    reg     = importlib.import_module(f"{sport}.ingest.sources").SOURCES
    bucket  = os.environ["LAKE_BUCKET"]
    manifest = {}
    for name in (names or reg):
        fetch, season_col = reg[name]
        df = fetch(seasons)
        for season, part in df.groupby(season_col):
            manifest[f"{name}/{season}"] = write_partition(part, bucket, sport, name, int(season))
    return {"ok": True, "rows": manifest}
```
**`ingest/backfill.py`** — same logic, run OFF-Lambda for full history (no 15-min cap): `python -m ingest.backfill --sport nfl --seasons 2015-2026`.

**Packaging (`Dockerfile`)** — deps (nfl_data_py + pandas + pyarrow) exceed the zip limit, so use a container image:
```dockerfile
FROM public.ecr.aws/lambda/python:3.12
COPY ingest/ ${LAMBDA_TASK_ROOT}/ingest/
RUN pip install --no-cache-dir nfl_data_py pandas pyarrow boto3
CMD ["ingest.handler.lambda_handler"]
```
- **Lambda config:** memory 2–3 GB, timeout 5–15 min (weekly incremental fits; backfill runs off-Lambda).
- **IAM:** least-privilege role — `s3:PutObject/GetObject/DeleteObject/ListBucket` scoped to `<bucket>/<sport>/*`; API keys (Odds API) via Lambda env / SSM Parameter Store. **No** `ACCOUNTADMIN`, no warehouse, no keys in code.

## 5. Schedule (`infra/eventbridge.tf`, sketch)
```hcl
resource "aws_scheduler_schedule" "nfl_weekly" {
  schedule_expression = "cron(0 12 ? * TUE *)"      # weekly in-season, after MNF (UTC)
  target {
    arn      = aws_lambda_function.sport_ingest.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ sport = "nfl", seasons = [2026], mode = "incremental" })
  }
}
```
One Lambda + one schedule per sport (or per sport×source if you want isolation). Odds API gets its own schedule (more frequent in-season).

## 6. Transform — `dbt-duckdb` over S3 (scaffold)

**`dbt/profiles.yml`** (DuckDB reads S3 directly; creds via IAM credential chain):
```yaml
sport_lake:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: "{{ env_var('DBT_DUCKDB_PATH', 'build/sport.duckdb') }}"
      extensions: [httpfs, parquet]
      settings:
        s3_region: us-east-1
        # prefer the credential chain (IAM role) over inline keys:
        s3_use_ssl: true
      # for marts written back to the lake:
      external_root: "s3://{{ env_var('LAKE_BUCKET') }}/{{ env_var('SPORT') }}/marts"
```

**`dbt/models/_sources.yml`** (raw Parquet as external sources):
```yaml
version: 2
sources:
  - name: nfl_raw
    meta: { external_location: "s3://{{ env_var('LAKE_BUCKET') }}/nfl/raw/{name}/**/*.parquet" }
    tables: [{name: weekly_data}, {name: schedules}, {name: depth_charts},
             {name: snap_counts}, {name: combine_data}, {name: injuries},
             {name: passing_next_gen_stats}, {name: rushing_next_gen_stats},
             {name: receiving_next_gen_stats}, {name: passing_pro_football_ref},
             {name: rushing_pro_football_ref}, {name: receiving_pro_football_ref},
             {name: weekly_rosters}, {name: rosters}, {name: draft_picks}]
```

**`dbt/models/staging/stg_weekly_data.sql`** (clean/rename — port the prior `jaffle_shop` logic here):
```sql
select *  -- replace with the explicit select/renames from the prior staging model
from {{ source('nfl_raw', 'weekly_data') }}
```
Marts (`fct_player_week`, `mart_player_season`, `mart_projections_preseason`, `dim_nfl_betting`, …) port over **unchanged in SQL** — only the source layer differs. Materialize marts as DuckDB tables, and/or `external` Parquet back to S3 for reuse.

- **Where dbt runs:** in-process — a small container (CI, a second Lambda, or a tiny scheduled Fargate task) reading/writing S3. Free compute; no warehouse.

## 7. Serving
Reverse-ETL the **serving marts** (projections, picks, transparency rows) into **Railway PG**, mirroring MLB's `write_serving_store.py` — the Credence app reads PG, never the lake at request time. (DuckDB can write to Postgres via its `postgres` extension, or a tiny loader does `df → PG`.)

## 7A. Querying the lake — the dev loop (humans **and** Claude Code)  ⚠️ critical
**The lake is fully queryable, and the iteration loop is as fast or faster than Snowflake-via-MCP — via DuckDB.** DuckDB reads S3 Parquet directly (`read_parquet('s3://…')`, `httpfs`), with no warehouse to resume, no credits, instant. **This must be a first-class affordance, or the agent rewrites connection boilerplate every session (the slow pattern).** Today a Claude Code session reaches for the **Snowflake MCP** to run SQL; the lake's **parity tool is `query_lake.py`** (below) — point every new-session prompt at it.

**Ways to query, fastest dev-loop first:**
1. **`query_lake.py` helper (the parity tool):** preconfigured DuckDB + `httpfs` + S3 credential chain → `q(sql) -> DataFrame`. Any session does `from tools.query_lake import q; q("select … from read_parquet('s3://…/**/*.parquet')")`.
2. **DuckDB CLI / one-liner (ad hoc):** `duckdb -c "INSTALL httpfs; LOAD httpfs; SELECT … read_parquet('s3://…')"`.
3. **Local sync for zero-latency heavy iteration:** `aws s3 sync s3://<bucket>/<sport>/ ./.lake/` then DuckDB over local Parquet — no per-query S3 latency/cost.
4. **The `dbt-duckdb` build file** (`build/sport.duckdb`) is itself directly queryable — it holds the staging + marts after `dbt build`.
5. **Athena** (optional): serverless SQL-over-S3 if you want a hosted endpoint or an Athena MCP later; pay-per-query.

**Requirement (the only gotcha):** the session needs **AWS credentials** (env vars or an IAM profile) with read on the bucket — the same machine that already has S3 access. DuckDB uses the standard credential chain; `INSTALL/LOAD httpfs+parquet` once.

**Why it's ≥ the Snowflake-MCP loop:** local, free, no warehouse resume, and you can pull a slice down for instant iteration. The cost was never query *capability* — it's just a different engine (DuckDB) reached via a helper instead of an MCP.

**`tools/query_lake.py`** (shared — ship it with the scaffold):
```python
import os, duckdb
_con = duckdb.connect()
_con.sql("INSTALL httpfs; LOAD httpfs; INSTALL parquet; LOAD parquet;")
_con.sql(f"SET s3_region='{os.environ.get('AWS_REGION', 'us-east-1')}';")  # creds via the IAM chain
LAKE = f"s3://{os.environ['LAKE_BUCKET']}"

def q(sql: str):
    """Run SQL against the lake; returns a pandas DataFrame. Use read_parquet('{LAKE}/<sport>/raw/<src>/**/*.parquet')."""
    return _con.sql(sql).df()
# e.g. q(f"select season, count(*) from read_parquet('{LAKE}/nfl/raw/weekly_data/**/*.parquet') group by 1 order by 1")
```
> **Snowflake parity for MLB-after-migration (E11.1):** once baseball moves to the lake, the same `query_lake.py` is how a session explores the baseball lake — the Snowflake-MCP loop is replaced by the DuckDB loop, not lost. (Snowflake-resident MLB data stays MCP-queryable until/unless it migrates.)

## 8. How a new sport plugs in (checklist)
1. `mkdir <sport>/ingest <sport>/dbt <sport>/infra`; copy `s3io.py`, `handler.py`, `backfill.py`, `tools/query_lake.py`, `profiles.yml`, the EventBridge module.
2. Write **`<sport>/ingest/sources.py`** — the sport's fetchers (NFL=`nfl_data_py`, NCAAF=CFBD, NCAAB=efficiency source; all + The Odds API).
3. Backfill once off-Lambda → S3; wire the weekly EventBridge schedule.
4. Write `dbt/models/_sources.yml` + staging + marts; `dbt build`.
5. Reverse-ETL serving marts → Railway PG; surface in Credence.
6. Write/refresh `<sport>_data_inventory.md` against the lake.

## 9. Migration to post-profit infra (no rewrite)
The **S3 Parquet lake is the durable core.** When a sport earns heavier infra:
- **Lambda → Dagster:** Dagster ops call the *same* `ingest/` functions; EventBridge schedule → Dagster schedule/sensor.
- **DuckDB → Snowflake:** Snowflake **external tables** or `COPY INTO` from the *same* S3 prefixes; dbt re-targets (the model SQL is shared, so it's an adapter/profile change, not a rewrite).
- Serving (Railway PG + Credence) is unchanged.

## 10. Per-sport source registries
- **NFL** (`football/nfl/`): `nfl_data_py` import_* per §4 — **re-pull fresh** (brownfield; the Snowflake `FOOTBALL_DATA` data is stale). Add `import_injuries` (was missing) + Odds API.
- **NCAAF** (`football/ncaaf/`): **CollegeFootballData (CFBD)** API (PBP/rosters/recruiting/talent) + draft/combine + Odds API; plus the college→NFL feeder xref.
- **NCAAB** (`basketball/ncaab/`): efficiency/tempo source (Torvik/KenPom-style or computed from PBP) + Odds API.
- **All:** **The Odds API** (odds/props/scores) on its own Lambda+schedule → `<sport>/raw/odds_*`.

```
▶ New-session prompt — build the platform scaffold (first instance: NFL)
Read: this guide (sport_data_platform.md) IN FULL + multi_sport_roadmap.md §6 + football/nfl/nfl_guide.md
(the port plan) + football/nfl/nfl_data_inventory.md (the prior Snowflake models to port).

Build the SHARED scaffold against NFL as the first instance:
  1. ingest/: s3io.py + handler.py + backfill.py (per §4) + football/nfl/ingest/sources.py (the nfl_data_py
     registry, incl. import_injuries). Containerized (Dockerfile). Backfill 2015–present OFF-Lambda → S3 lake.
  2. infra/: one Lambda + a weekly EventBridge schedule (incremental, current season); least-privilege S3 IAM;
     Odds API key in SSM. (Lambda container image; mem 2–3GB; backfill runs off-Lambda.)
  3. dbt/ (dbt-duckdb): profiles.yml + _sources.yml (external Parquet) + port the prior jaffle_shop staging +
     refined marts (fct_player_week, NGS satellites, mart_player_season, mart_projections_preseason,
     dim_nfl_betting) — SQL unchanged, only the source layer differs. dbt build over S3.
  4. Reverse-ETL the serving marts → Railway PG; refresh nfl_data_inventory.md against the lake.
  5. Ship tools/query_lake.py (§7A) — the DuckDB-over-S3 helper that is the PARITY TOOL to the Snowflake MCP;
     every later session explores the lake via it (e.g. `from tools.query_lake import q; q("select … read_parquet('s3://…')")`).
Keep it weekly batch + incremental + idempotent-partition writes. Conventions: uv run python; IAM/SSM for
secrets (NO ACCOUNTADMIN / keys-in-code); do not git commit/push. Make the shared pieces reusable so NCAAB/NCAAF
only add a sources.py + dbt models + a schedule.
```
