# NCAAB data inventory (NCAAB-P0)

The vertical's master data file (`sport_data_platform.md` §2). Every figure here was **measured**
on 2026-09-14, not read from documentation. Witnesses:
`ablation_results/ncaab_p0_source_audit.json` · `ablation_results/ncaab_p0_credit_probe.json`.
Regenerate both: `python -m …ingest.source_audit` · `python -m …ingest.credit_probe`.

## 1. Sources

| Source | What it gives | Licence / terms | Cost |
|---|---|---|---|
| **hoopR** (`sportsdataverse/hoopR-mbb-data`) | schedules, team box, crosswalk (+ pbp, player box, rosters, standings, shots, officials — not yet ingested) | **CC BY 4.0** — commercial use with attribution | **Free** |
| **The Odds API** | title futures (live + historical), game lines (live + historical) | existing subscription | measured — see `docs/ncaab_p0_credit_arithmetic.md` |
| ESPN `sports.core.api` | *audit corroboration only* — not in the pipeline | robots.txt 403s → **undeclared** | free |

⛔ **Not used, and why.** `www.espn.com` and `www.ncaa.com` both `Disallow: /` our agent class;
`stats.ncaa.org` 403s; ESPN's `site.api` host 403s on every path and user agent tried. The
vertical is built on the **licensed redistribution**, not on scraping.

**Attribution obligation** (CC BY 4.0) is carried in code as `sources.ATTRIBUTION` so the P3
serving story inherits it rather than having to discover it in a licence file it never opens.

## 2. Lake tables

`s3://credence-sports-lakehouse/ncaab/raw/<source>/` — Delta, season-partitioned.

| Table | Grain | Cadence | Rows (2026) | Notes |
|---|---|---|---|---|
| `schedules` | game | daily | 6,318 | 86 cols. The spine. |
| `team_box` | game × team | daily | 12,598 | 59 cols. Carries all four possession operands. |
| `team_crosswalk` | team | seasonal | 362 | Conference **names** + KenPom/Torvik/Fox/Yahoo keys. Current season only upstream. |
| `odds_futures` | board | daily | — | **Not yet enabled** (spend decision). |
| `odds_game_lines` | board | intraday | — | **Not yet enabled** (spend decision). |
| `odds_historical` | board | on-demand | — | Paid `/historical`; `on_demand` so a routine run cannot burn credits. |

Every row carries `capture_timestamp` — **our** fetch time, never a file mtime.

## 3. Coverage

| | Measured |
|---|---|
| Seasons published | **2003–2027** (25 files) |
| Fully-scored seasons | **24** (2003–2026), **100.0%** of games scored in each |
| D-I teams | **366** (2026) — independently corroborated by ESPN's D-I group returning **366** |
| Conferences | 31–33 |
| Games/season | ~6,300 |
| Venue coverage | 100% from 2014; 87–93% before |
| Upcoming season | 2027 loaded — **1,629 games** |

## 4. Known gaps — none is a purchase decision

| Gap | Fixable with money? | Effect |
|---|---|---|
| Market history begins **2020-11-16** | **No** (vendor archive floor) | Market-relative windows cap at **6 seasons**; game-only work has 24. |
| `neutral_site` identically 0 before 2008 | No | An **absence**, not a False. Surfaced as `neutral_site_is_trustworthy`. |
| No conference-futures sport key | No | Futures ship as **title only**. |
| NCAAB player props not offered (0 books) | No | E5-style props are blocked **at the source**. |
| Crosswalk is current-season only | No | Names resolve for the latest season; ids carry history. A defunct conference keeps its history and is flagged `name_unresolved`. |
| hoopR publishes no as-of | No | Solved by our content-timestamped Delta writes + time travel. |
| `team_box` 404s before the first tip | No | Normal pre-season state; classified, not escalated. |

## 5. dbt models

**Staging** (`ncaab_staging`, materialized as tables — the DeltaScan-serialization cure):
`stg_ncaab_schedule` · `stg_ncaab_team_box` (owns the single shared possession definition) ·
`stg_ncaab_team_crosswalk`.

**Marts** (`ncaab_marts`): `dim_ncaab_team` (SCD-2 over conference) · `dim_ncaab_conference` ·
`fact_ncaab_team_game` (the P1 fitting surface).

⚠️ **`dbt build --select ncaab` SEGFAULTS the fusion binary** — not our SQL and not the data (both verified independently). Build model-by-model; the recipe, the evidence and two non-fixes are in **`docs/ncaab_p0_dbt_build.md`**. There is also **no NCAAB Dagster dbt job**, so the marts do not rebuild on the box.

Verified build: **PASS=28, WARN=1, ERROR=0** over 6 ingested seasons (reproduced end-to-end against real S3 on 2026-09-14). The one warning is a
D-I-reclassifying school with no conference (West Florida) — a true state of the world, held at
`warn` severity so a hard failure cannot train the operator to ignore staging tests.

## 6. Conference realignment — the SCD

**52 teams changed conference 2023–2027**, and 80 carry multiple SCD versions touching 2023+.
Arizona / Arizona State / Colorado read Pac-12 (21) through 2024 and Big 12 (8) from 2025;
California moved to the ACC (2). The Pac-12 itself resolves `is_defunct` with its history intact.

This is why the dimension is SCD-2: a type-1 dimension would report a 2023 Arizona game as a Big
12 game and silently corrupt every conference-strength feature computed from it.

## 7. Derived quantities

`possessions ≈ FGA − ORB + TO + 0.475·FTA`, computed **once** in `stg_ncaab_team_box` so no two
downstream models can disagree about pace. Measured output: **69.2 possessions/team-game**,
squarely in the real NCAAB range. Per-100 efficiency is NULL below a 20-possession floor — a
rate divided by a near-zero possession count is finite, enormous and completely fake, and no
NULL check catches it (hoopR's own repo records a model incident from one zero-possession row).

## 8. P1 readiness statement

*Mirrors the canonical copy in `plan_specs/ncaab/ncaab-p0.yaml` → `closeout.followUps` item 8.
Keep them in step.*

**The fitting surface.** `fact_ncaab_team_game` — box line, shared possession estimate, per-100
efficiency, and the **point-in-time-correct** conference from the SCD. 24 seasons available;
6 ingested. Extending is a re-run, not a code change.

### ⭐ Registration constraint — binding, not advisory

> **Any P1/P2 clause that touches market data declares its window INSIDE the 2020-11-16 archive
> floor, and no story is ever scoped around a longer one.**

Game data reaches **24 seasons** free; market data reaches **6**, at any spend. The bound is the
vendor's archive, not the budget, so the window is a **design input you declare**, not something
discovered mid-story. The historical backfill is priced but deliberately unpurchased
(DEFERRED-ON-DEMAND) precisely so that a registered design names its window and the purchase buys
exactly that — see `docs/ncaab_p0_credit_arithmetic.md` §4.

### ⭐ The training window is a DECLARE-FORWARD choice

**10–15 seasons is a suggestion from P0 and carries no authority.** P1's pre-registration must
**declare its window family forward**, citing the *mechanism* for each candidate cut:

| Candidate boundary | Mechanism |
|---|---|
| ≥ 2008 | the **birth of the `neutral_site` flag** — before it, the field is an absence, not a False |
| ≥ 2015 | the **shot-clock reduction to 30 seconds** — a direct, deliberate change to possession count |
| ≥ 2023 | the **realignment wave** — 52 teams changed conference 2023–2027 |

A window chosen *after* seeing fits is the E2.1-r inversion in its most literal form. The data
supports all 24 seasons either way; **which of them are the same game** is the modelling question
P1 registers and TESTS, not one P0 settles.

### ⚠️ Two honest-absence caveats P1 inherits

Both are already surfaced in the models, so neither can be read wrong by accident — but a design
that ignores them will mis-specify silently rather than fail:

- **`neutral_site` is identically 0 for every season before 2008.** That is the flag *not
  existing*, not "no neutral-site games were played" — and 2008–2026 average ~650 neutral games a
  season, so reading the earlier zeros as `False` would silently mis-specify every pre-2008 game.
  Surfaced as an explicit `neutral_site_is_trustworthy` column on `stg_ncaab_schedule` so a
  training window cannot read missing as False.
- **Per-100 efficiency is NULL below a 20-possession floor**, because a rate divided by a
  near-zero possession count is finite, enormous and completely fake, and no NULL check catches it
  (hoopR's own repo records a model incident from one zero-possession row). The row is kept and
  flagged `possessions_unusable` rather than dropped, so the absence is countable.

### ✅ The lake is live, with two operational caveats

The runtime gate passed 2026-09-14 against real S3: `schedules` holds 2022–2027 (32,732 rows),
`team_box` 2022–2026 (62,020), `team_crosswalk` 2026 (362), and the marts build over them. P1 can
fit on this today.

Two things P1 inherits rather than discovers:

- ⚠️ **`dbt build --select ncaab` segfaults dbt-fusion** — not our SQL, not the data (both
  verified independently). Build model-by-model: `docs/ncaab_p0_dbt_build.md`.
- ⚠️ **There is no NCAAB Dagster dbt job.** The daily ingest advances the lake, but nothing
  rebuilds the marts on the box — they sit at whatever was last built by hand. Wire that before
  anything serves off them.
