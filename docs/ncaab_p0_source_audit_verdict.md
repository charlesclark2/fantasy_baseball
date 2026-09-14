# NCAAB-P0 — free-source audit and the PAID-NECESSITY VERDICT

**For the operator. A spend decision, made on measurement.**
Measured 2026-09-14 by live pulls. Witness:
`quant_sports_intel_models/basketball/ncaab/ablation_results/ncaab_p0_source_audit.json`.
Reproduce: `python -m quant_sports_intel_models.basketball.ncaab.ingest.source_audit`.
**No paid signup happened in this story.**

---

## VERDICT

> ## Free sources SUFFICE for P1's strength model and P2's calibration. No paid data purchase
> ## is required to reach the launch target. There is no named gap in the game-data layer.
>
> The one hard limit found is **not purchasable**: market history begins 2020-11-16, so any
> market-relative training window is capped at **6 seasons at any price**. Game data reaches
> **24 seasons**, free.

Two capabilities the roadmap assumed would need money, measured and found free:

- **Adjusted efficiency / tempo.** The roadmap stub proposed "ingest a Torvik/KenPom-style
  source". Not needed: the possession identity's four operands (FGA, ORB, TO, FTA) are present
  in the free box scores **from 2003**, so tempo × efficiency is computable from the substrate
  we already have. Built and verified — the mart returns **69.2 possessions per team-game**,
  squarely in the real NCAAB range.
- **The option on buying one later.** hoopR's crosswalk ships `kp_team`/`kp_conf` and
  `bart_team`/`bart_conf` — ready join keys to **KenPom and Bart Torvik**. If the operator
  ever does buy one, the crosswalk to it already exists and is CC BY 4.0.

---

## The evidence

### Coverage — hoopR (`sportsdataverse/hoopR-mbb-data`)

| | Measured |
|---|---|
| Seasons published | **2003–2027** (25 files) |
| Fully-scored seasons | **24** (2003–2026) — **100.0% of games carry both scores in every one** |
| Games | ~6,300/season (2026: 6,318) |
| D-I teams | **366 distinct home teams** (2026) |
| Conferences | 31–33 |
| Venue coverage | **100% from 2014**; 87–93% 2003–2013 |
| Upcoming season | **2027 already populated — 1,629 games** |

**Independent corroboration of the team universe:** ESPN's core API D-I group (id 50) returns
**exactly 366** teams for 2026, against hoopR's 366. Two unrelated sources agreeing is what
makes "~360 D-I teams" a *measured* figure rather than a repeated one.

### Field inventory vs the NCAAF-parity MVP

**Missing: NONE.** All of `home_score`, `away_score`, `home_winner`, `game_date`, `season`,
`season_type`, `neutral_site`, `venue_id`, both team ids, both conference ids, and
`status_type_completed` are present (86 schedule columns, 59 team-box columns).

**Pace: computable, from 2003.** All four possession operands present.

### ⚠️ The one field-level gap, and it is an absence not a value

`neutral_site` is **identically 0 for every season before 2008**. That is the flag *not
existing*, not "no neutral-site games were played" — and 2008–2026 average ~650 neutral games a
season, so reading the earlier zeros as `False` would silently mis-specify every pre-2008 game.
Surfaced as an explicit `neutral_site_is_trustworthy` column on `stg_ncaab_schedule` so a
training window cannot read missing as False by accident. **Practical impact: none** — 18
trustworthy seasons is far more than a strength prior needs.

### Point-in-time properties

| | Finding |
|---|---|
| Is there an as-of? | **No.** No vintage, no snapshot id, no as-of parameter. |
| Does it revise history? | **Completed seasons: no.** The 2015 file has 3 commits, all on its 2023 load date. |
| The current season? | **Rewritten continuously** — ≥100 commits to the 2026 file across one season. |

⇒ **Point-in-time is ours to create, and that is a design consequence, not a defect.** "What did
the schedule say on December 3rd" is unanswerable from the source and answerable from our lake,
because every ingest stamps its own `capture_timestamp` and lands a content-timestamped Delta
version — Delta time-travel becomes the as-of the source lacks. This is exactly why the ingest
stamps fetch time and never a file mtime.

### Terms of use — measured live, and this decided the architecture

| Host | Directive for our agent class | Usable? |
|---|---|---|
| **hoopR (raw.githubusercontent.com)** | **CC BY 4.0** — share + adapt, **commercially**, with attribution | ✅ **Yes** |
| `www.espn.com` | `User-agent: anthropic-ai` → `Disallow: /` | ❌ No |
| `www.ncaa.com` | `anthropic-ai`, `ClaudeBot`, `Claude-Web` grouped → `Disallow: /` | ❌ No |
| `stats.ncaa.org` | 403s outright on most requests | ❌ No |
| `site.api.espn.com` | **403 on every path and every user agent tried** | ❌ Unreachable |
| `sports.core.api.espn.com` | Answers, but `robots.txt` itself 403s → **no directive obtainable** | ⚠️ Undeclared |

Two traps worth recording, because the naive read is wrong in both:

1. **GitHub's licence API reports hoopR as `NOASSERTION / Other`**, which reads as legal risk.
   It is **CC BY 4.0** — the R packaging convention puts only year and holder in `LICENSE` and
   names the licence in `DESCRIPTION`/`LICENSE.md`. Trusting the API field alone would have
   wrongly disqualified the best free source in the audit.
2. **`ncaa.com` lists 20+ AI agents as consecutive `User-agent:` lines closed by a single
   `Disallow: /`.** A per-line robots parse reads those agents as having *no rules* and reports
   the site as permitted — the exact inversion. The audit's parser honours the grouping, and
   the reason is written above the code so it cannot be "simplified" back into the bug.

   ⚠️ **The first cut of that parser had the opposite bug and it is worth recording**, because
   it is the shape that ships unnoticed: it never reset the group when a new `User-agent`
   block began after a rule line, so a *later* group's `Disallow: /` leaked onto an agent an
   *earlier* group had explicitly allowed — a **false DISALLOWED**. It did not change either
   real reading here (ESPN and NCAA both genuinely block us, confirmed by reading the raw
   files by hand), which is exactly why nothing about the verdict would have looked wrong.
   Found by feeding the parser a synthetic site that permits us; both directions are now
   guarded and RED-proven.

**Architectural consequence:** we build on the **licensed redistribution** (hoopR, CC BY 4.0),
not on scraping ESPN or NCAA. The ESPN core API is used for **nothing** in the shipped pipeline —
it appears in the audit only as an independent corroboration of the team count. Attribution is
carried in code (`sources.ATTRIBUTION`) so the P3 serving story inherits an obligation it would
otherwise have to discover by opening a licence file it never opens.

---

## Named gaps, and what each actually costs

| Gap | Can money fix it? | Impact |
|---|---|---|
| Market history starts **2020-11-16** (6 seasons) | **No** — the vendor's archive floor | Caps market-relative training at 6 seasons. Game-only models are unaffected (24 seasons). |
| `neutral_site` absent pre-2008 | No | None — 18 trustworthy seasons is ample. |
| **No conference-futures key** at The Odds API | No | The spec's "title/conference" futures ships as **title only**. |
| **NCAAB player props not offered** (0 books, 0 markets) | No | The roadmap's E5-style props track is **blocked at the source**. |
| hoopR crosswalk is **current-season only** | No | Conference *names* resolve for the latest season; historical membership uses the stable per-season ids. A defunct conference (Pac-12) keeps its history and is flagged `name_unresolved` rather than dropped. |
| No as-of from hoopR | No | Solved by our own content-timestamped Delta writes. |

**None of these is a purchase decision.** Every one is either structural to the vendor or
already solved in the lake design.

---

## What P1 can fit on

- `fact_ncaab_team_game` — one row per (game, team): full box line, the **single shared**
  possession estimate, per-100 offensive/defensive efficiency, and the **point-in-time-correct**
  conference resolved through the SCD.
- `dim_ncaab_team` — SCD-2 over conference. **80 teams carry multiple versions touching 2023+.**
  Arizona reads Pac-12 through 2024 and Big 12 from 2025, which is what stops a 2023 game being
  retroactively labelled a Big 12 game.
- `dim_ncaab_conference` — id → name, lifespan, and `is_defunct` (the Pac-12 correctly resolves
  as defunct with its history intact).
- **Depth: 24 seasons available.** A 6-season window (2022–2027) is ingested and built; extending
  is a re-run, not a code change, and costs nothing but time.

**Suggested training depth: 10–15 seasons.** Rationale: the source supports 24, but college
basketball's structure changed materially (the 2008 neutral-site flag, the 2015 shot-clock
reduction to 30 seconds, and the 2023–25 realignment wave), so the older seasons are a
different game rather than more of the same one. That is a **modelling** judgment for P1 to
test, not a data constraint — the data is there either way.

> ⚠️ **This is a suggestion with no authority, and P1 must not inherit it as a default.** Per the
> PM ruling of 2026-09-14, P1's pre-registration **declares its window family FORWARD**, citing
> the mechanism for each candidate cut; a window chosen after seeing fits is the E2.1-r inversion.
> The canonical wording, the per-boundary mechanism table, and the binding **2020-11-16
> market-archive registration constraint** live in the **P1 readiness statement** —
> `plan_specs/ncaab/ncaab-p0.yaml` → `closeout.followUps` item 8, mirrored in
> `ncaab_data_inventory.md` §8. Read that, not this paragraph, when scoping P1.
