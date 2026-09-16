# NCAA Basketball (NCAAB) — Implementation Guide

**Status:** v0.4 — Phase 0 (NCAAB-P0) **COMPLETE**. The box runtime gate PASSED 2026-09-14:
the instance role wrote the `ncaab/` prefix on its first attempt (no IAM grant needed), the box
reads hoopR over HTTPS, and the full mart chain builds — 28 passes + 1 warn. The lake holds
2022–2027 and `fact_ncaab_team_game` is live at 69.1–69.6 possessions/team-game. **P1 is
unblocked.** ⚠️ Two operational caveats it inherits: `dbt build --select ncaab` segfaults
dbt-fusion (build model-by-model — `docs/ncaab_p0_dbt_build.md`), and there is **no NCAAB
Dagster dbt job**, so the marts do not rebuild on the box.

> 🚩 **STALENESS CORRECTIONS (NCAAB-P0, 2026-09-14) — READ BEFORE TRUSTING ANYTHING BELOW.**
> The original stub predates the current architecture and FIVE of its claims are now WRONG:
> 1. **"Railway PG"** — DECOMMISSIONED (INC-16). Serving is DynamoDB → S3.
> 2. **"Lambda + EventBridge cron"** — superseded. Orchestration is the existing Dagster EC2
>    box; NCAAB's free ingest is `sports_ncaab_ingest_schedule` (daily, RUNNING).
> 3. **"ingest a Torvik/KenPom-style source"** — MEASURED UNNECESSARY. The possession identity's
>    four operands are in the free box scores from 2003, so tempo × efficiency is computable
>    from the substrate we already have (measured: 69.2 possessions/team-game). hoopR's
>    crosswalk even ships KenPom/Torvik join keys, so buying one later stays cheap.
> 4. **"E5 player props"** — BLOCKED AT THE SOURCE, not a budget question: The Odds API carries
>    no NCAAB player props (measured: HTTP 200, 0 books, 0 markets, 0 credits).
> 5. **"futures (title/conference)"** — TITLE ONLY. There is no conference-futures sport key at
>    this vendor; the live `/sports` list carries exactly two NCAAB keys (`basketball_ncaab`,
>    `basketball_ncaab_championship_winner`). Not purchasable.
>
> ⛔ **A BLOCKED TRACK IS MARKED, NEVER DELETED (PM ruling, 2026-09-14).** Where a track below is
> struck through, it is struck through *with its measurement attached*. The reason is a reading
> hazard rather than a courtesy: a **removed** section reads as never-considered and invites the
> next reader to re-scope it from scratch, while a **blocked** one reads as answered and hands
> them the evidence. Nothing here was dropped for being inconvenient — each strike carries the
> date and the measurement that earned it.
>
> **Current master data file:** `ncaab_data_inventory.md`.
> **Operator decisions:** `docs/ncaab_p0_source_audit_verdict.md` (no paid data needed) and
> `docs/ncaab_p0_credit_arithmetic.md` (the capture spend decision, still open).

**Original stub text follows, retained for provenance.**

**Status (original):** v0.1 — scaffold (Phase 0 not yet started)
**Parent:** `quant_sports_intel_models/multi_sport_roadmap.md`
**Reference implementation:** MLB `baseball/edge_program/` — NCAAB instantiates the same tracks.
**Master data file:** `basketball/ncaab/ncaab_data_inventory.md` *(to be created in Phase 0)*.

> **Cost posture (pre-profit):** start on the **lean substrate** (roadmap §6; **scaffold in `sport_data_platform.md`** — instantiate it, don't reinvent) — free data ingested by **Lambda + EventBridge cron → S3 Parquet lake**, transformed with **`dbt-duckdb`** (Athena for ad hoc), served on the existing Railway PG. No Snowflake warehouse to start. Weekly/daily batch ⇒ naturally cheap. Port-up later (if it earns traction) = Lambda→Dagster, DuckDB→Snowflake from the same S3 prefixes.

## Why NCAAB fits the methodology well
**Most runway** (season ~early Nov) and a **huge game sample** (~360 D1 teams, thousands of games) — far friendlier to the modeling than NFL's ~17 games/team. The base model is the well-established **tempo × efficiency** structure (adjusted offensive/defensive efficiency + pace, KenPom/Torvik-style) → a per-game scoring distribution. The clearest edge seam: **markets are sharp on majors but soft on mid-majors / small conferences** — a strong fit for the **cross-book sharp-anchor (E4)**.

## Applicable Edge tracks
| MLB track | NCAAB instantiation |
|---|---|
| E1 (overfitting audit / CV) | reuse directly |
| E2 (per-side distributions) | tempo×efficiency → game total, team totals, 1H totals (convolve two team-scoring distributions) |
| E3 (closing-line / CLV) | applies; lots of games/day → CLV stabilizes fast |
| E4 (cross-book sharp-anchor) | **strongest seam** — mid-major / small-conference lines lag the sharps |
| ~~E5 (player props)~~ | ⛔ **BLOCKED-AT-SOURCE** — ~~points/rebounds/assists/threes props~~. Measured NCAAB-P0 2026-09-14: a per-event props request returns **HTTP 200 with 0 books, 0 markets and 0 credits billed**. The vendor does not offer NCAAB player props at all, so this is not a budget question and **no spend unblocks it**. Re-open only if a future measurement shows the vendor has started carrying them. |
| E10 (parlay) | calculator first |

## Phased plan (kickoff ~early Nov — most runway of the three)
- **Phase 0 — data:** ✅ COMPLETE (NCAAB-P0; runtime gate passed 2026-09-14). The Odds API NCAAB (odds + ~~props~~ ⛔ not offered + scores) on the Railway-cron pattern; team/efficiency + pace data (compute adjusted efficiency from PBP, or ingest a Torvik/KenPom-style source); rosters + injuries; build `ncaab_data_inventory.md`.
- **Phase 1 — honest surfaces by kickoff:** tempo×efficiency base totals/team-totals distribution, parlay calculator, per-book/CLV transparency (esp. mid-major sharp-vs-soft comparison).
- **Phase 2 — gated edge (post-kickoff):** sharp-anchor (E4 — lead with mid-majors), ~~props (E5)~~ ⛔ **BLOCKED-AT-SOURCE, see the table above**, CLV (E3); each PBO<0.2 + DSR>0.
  ⚠️ **E3/E4 both consume market data and are therefore bounded by the archive floor:** any clause touching the market declares its window inside **2020-11-16** (6 seasons), and no story is scoped around a longer one. Game-only work has 24 seasons. See `ncaab_data_inventory.md` §8.

```
▶ New-session prompt — NCAAB Phase 0 (data inventory + base model)
Read: multi_sport_roadmap.md + this stub + baseball/edge_program §0/§6 + E2 (the convolution/distribution
pattern) + E4 (sharp-anchor). STEP 1: ingest Odds API NCAAB (odds/props/scores) + team efficiency/pace +
rosters/injuries → write basketball/ncaab/ncaab_data_inventory.md. STEP 2: build a tempo×efficiency per-team
scoring distribution → convolve to game/team totals (E2 analog). Conventions: dbtf not dbt; Snowflake via MCP
fully-qualified no USE; uv run python; hand >1min scripts to the operator; do not git commit/push.
```
