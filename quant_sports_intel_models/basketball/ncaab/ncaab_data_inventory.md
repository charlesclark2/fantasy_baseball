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

Verified build: **PASS=28, WARN=1, ERROR=0** over 6 ingested seasons. The one warning is a
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

## 8. What P1 can fit on

`fact_ncaab_team_game` — box line, shared possession estimate, per-100 efficiency, and the
**point-in-time-correct** conference from the SCD. 24 seasons available; 6 ingested.
**Suggested training depth: 10–15 seasons** — the data supports 24, but the 2008 neutral-site
flag, the 2015 shot-clock reduction and the 2023–25 realignment wave make the older seasons a
different game. That is a modelling judgment for P1 to test, not a data limit.
