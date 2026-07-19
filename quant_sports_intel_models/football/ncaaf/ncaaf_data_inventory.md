# NCAAF — Data Inventory (the master data file)

**Status:** v1.0 — produced by **NCAAF-P0.1** (2026-07-13). **Ground-truthed against LIVE endpoints**, not docs.
**Parents:** `ncaaf_roadmap.md` §2 (the wishlist this resolves) · `../../sport_data_platform.md` (the lakehouse to instantiate) · `../../multi_sport_roadmap.md` §4 (the NFL feeder).
**Consumers:** NCAAF-P0.2 (scaffold) + NCAAF-P0.3 (college↔NFL xref) start from the locked source set in §7.

> **How this was verified:** every ✅ below is backed by a real sample pull executed on 2026-07-13 against
> `https://api.collegefootballdata.com` (v2, `CFBD_API_KEY` already in `.env`), `https://api.the-odds-api.com/v4`
> (`ODDS_API_KEY`), and the nflverse release Parquet. Row counts + field lists in §2–§5 are **observed**, not documented.

---

## 0. TL;DR — the five decisions

1. **CFBD delivers the minimum bar and most of the reach.** Box scores (team + player), full play-by-play, player-level play stats, team-advanced (SP+/havoc/line-yards/stuff/success/explosiveness), rosters, recruiting/talent, drives, win-prob and even betting lines are all **live and free-tier-accessible**. 39 of 42 probed endpoints returned data.
2. **💰 BUY CFBD Patreon Tier 3 ($10/mo, 75k calls).** The free tier is **1,000 calls/mo — confirmed by the live `X-Calllimit-Remaining` response header**, and the backfill needs **~15,800 calls** (§6). Free tier cannot do it (it would take ~16 months); Tier 3 does the whole thing in **one month with ~5× headroom**. This is the **only Phase-0 cost.**
3. **The Odds API (existing sub) fully covers NCAAF** — `americanfootball_ncaaf`, 11 US books incl. **Bovada** (our target book), h2h/spreads/totals live, alt-spreads/alt-totals/team-totals + player props on the event endpoint, scores for settlement. **Historical floor = 2020** (2019 returns zero events).
4. **⭐ The NFL-feeder spine is SOLVED and it is *not* an ID join.** There is **no shared player ID** between CFBD and nflverse. But the **draft slot `(season, overall pick)` is a deterministic key: 99.7% of CFBD draft picks (2015–2025) resolve to an NFL `gsis_id`**, independently validated at 92–100% surname agreement. Combine measurables attach on the nflverse side. **P0.3 can build the xref deterministically for drafted players** — fuzzy matching is only needed for UDFAs.
5. **⛔ PFF is NOT a Phase-0 buy, and it is not even cleanly buyable.** The $119.99/yr PFF+ subscription is a **website/UI** product, not an API or bulk-data license (§5). Ship Tier-A + PBP-derived proxies first, exactly as the roadmap's default lean.

---

## 1. Source register

| Source | Auth | Status | Cost | Role |
|---|---|---|---|---|
| **CFBD v2** `api.collegefootballdata.com` | `CFBD_API_KEY` (in `.env`, **free tier**) | ✅ live (39/42 endpoints) | $0 now → **$10/mo Tier 3 recommended** | The backbone: box, PBP, team-advanced, rosters, recruiting, draft |
| **The Odds API v4** | `ODDS_API_KEY` (in `.env`) | ✅ live | existing sub (4.66M credits remaining) | Lines/totals/spreads/props/scores + historical (2020+) |
| **nflverse release Parquet** | none (public GitHub release assets) | ✅ live | $0 | NFL-feeder: `draft_picks`, `combine`, `players` (the ID universe) |
| **PFF College** | — | ⛔ not acquired | $119.99/yr (UI only; no API) | Deferred, edge-gated (§5) |

### ⚠️ Landmines found while probing (carry these into P0.2)

- **🧨 A WRONG CFBD PATH RETURNS HTTP 200 WITH THE SWAGGER HTML PAGE — NOT A 404.** The v1-style singular paths
  (`/play/types`, `/play/stats`, `/play/stat/types`) return **`200 text/html`** with the API-docs bundle. A naive ingest that
  checks only `status_code == 200` would **silently write an HTML page as data.** The correct v2 paths are **plural**:
  `/plays/types`, `/plays/stats`, `/plays/stats/types`. ⇒ **every CFBD fetcher must assert `Content-Type: application/json`
  AND that the body parses to a list/dict — status code alone is not a success signal.**
- **📄 `/plays/stats` is hard-capped at 2,000 rows per response** (a league-week exceeds this: week 5 2025 returned exactly
  2000). It must be pulled **per-game** (`gameId`, ~218 rows/game) — this is the single biggest driver of the call budget (§6).
- **🔑 Tier gating is enforced server-side:** `/live/plays` → `401 "requires a Patreon subscription at Tier 2 or higher"`.
  This is how we *proved* the key is on the free/low tier.
- **🧮 `/plays` REQUIRES `week`** (`400 Validation Failed: week`) → per-week loop is mandatory. By contrast `/roster`,
  `/player/usage`, `/stats/player/season`, `/ppa/players/season`, `/recruiting/players`, `/player/returning` all accept
  **year-only** (1 call/season — do **not** loop 136 teams; that was a 136× budget trap).
- **🪪 `/game/box/advanced` takes `id=`, not `gameId=`** (`400 Validation Failed: id`).
- **🐍 `nfl_data_py` is effectively abandoned** — v0.3.3 pins `pandas==1.5.3`, which **fails to build on Python 3.12**.
  ⇒ **Do NOT depend on it.** Read the nflverse **release Parquet directly** (DuckDB `read_parquet` over the GitHub release
  URL) — dependency-free and native to our lakehouse. This contradicts `sport_data_platform.md §4/§10`, which still names
  `nfl_data_py`; that guidance is **stale** for a py3.12 environment.
- **💥 pandas merges NaN-to-NaN.** Coercing nflverse's `cfb_player_id` (a *slug*, `caleb-williams-3`) with `to_numeric`
  yields all-NaN and a **cartesian explosion** that fabricates a bogus 99.6% "match". Drop null join keys on both sides and
  assert `len(merged) == len(left)`. (This bit this session; it is exactly the class of silent-wrong that the MLB landmine
  list exists to prevent.)

---

## 2. CFBD — endpoints that deliver (all verified live, 2025 season unless noted)

**Grain legend:** 🏟️ game · 👥 team · 🧍 player · ▶️ play · 🗓️ season

### 2.1 Box scores — **the minimum bar** ✅ MET

| Endpoint | Grain | Verified | Fields / notes |
|---|---|---|---|
| `/games` | 🏟️ | ✅ 2004+ | id, teams, scores, venue, startDate, conferences, excitement |
| `/games/teams` | 🏟️👥 | ✅ 2004+ (49–54 games/wk) | **29 team stat categories**: totalYards, netPassingYards, rushingYards/Attempts, completionAttempts, firstDowns, third/fourthDownEff, possessionTime, turnovers, sacks, tacklesForLoss, **qbHurries**, passesDeflected, penalties, fumbles |
| `/games/players` | 🏟️🧍 | ✅ 2004+ | **8 categories**: passing (C/ATT, YDS, AVG, TD, INT, **QBR**), rushing, receiving, fumbles, **defensive**, interceptions, puntReturns, kicking. Nested `teams[].categories[].types[].athletes[]` (id, name, stat-as-string) |
| `/game/box/advanced` | 🏟️👥 | ✅ (param `id=`) | ppa, cumulativePpa, successRates (overall/standard/passingDowns), explosiveness, **rushing: lineYards, openFieldYards, secondLevelYards, powerSuccess, stuffRate**, **havoc: total/frontSeven/db**, scoringOpportunities, fieldPosition |

### 2.2 Play-by-play — **the raw material we derive from** ✅

| Endpoint | Grain | Verified | Fields / notes |
|---|---|---|---|
| `/plays` | ▶️ | ✅ 2004+ (**18,837 rows/week** 2025) | down, distance, yardsToGoal, yardsGained, playType, playText, **ppa** (CFBD's own EPA), offense/defense + conferences, scores, clock, period, driveId, wallclock. **`week` is REQUIRED.** |
| `/plays/stats` | ▶️🧍 | ✅ **2013+** (0 before) | **athleteId, athleteName, statType, stat** per play — `Target`, `Reception`, `Completion`, `Incompletion`, `Pass Breakup`, … ⇒ **this is how we get TARGETS** (the box score does not carry them). **2,000-row cap ⇒ pull per `gameId`.** |
| `/plays/types`, `/plays/stats/types` | 🗓️ | ✅ | reference dimensions |
| `/drives` | 🏟️ | ✅ (2,490/wk) | driveResult, plays, yards, start/end yardline + period + clock, elapsed, scoring |
| `/live/plays` | ▶️ | ⛔ **401 — Tier 2+** | in-game; not needed pre-kickoff |

### 2.3 Advanced TEAM metrics ✅ (this is where NCAAF is *richer* than expected)

| Endpoint | Grain | Verified | Fields |
|---|---|---|---|
| `/stats/season/advanced` | 🗓️👥 | ✅ | offense **and** defense: ppa, successRate, explosiveness, **lineYards, secondLevelYards, openFieldYards, stuffRate, powerSuccess**, havoc, standardDowns/passingDowns splits, fieldPosition, pointsPerOpportunity |
| `/stats/game/advanced` | 🏟️👥 | ✅ 2004+ | same block, **per game** — the modelling grain |
| `/ratings/sp` | 🗓️👥 | ✅ 1980+ | SP+ overall/offense/defense/specialTeams + nested **explosiveness, success, pace, runRate, rushing, passing, standardDowns, passingDowns, havoc**, sos, secondOrderWins |
| `/ratings/srs`, `/ratings/elo`, `/ratings/fpi` | 🗓️👥 | ✅ | SRS, Elo (week-grained), FPI (+ efficiencies, resumeRanks) |
| `/ppa/teams`, `/ppa/games` | 🗓️/🏟️👥 | ✅ | PPA by overall/passing/rushing × down |
| `/stats/season`, `/stats/categories` | 🗓️👥 | ✅ | 38 raw stat categories |
| `/metrics/wp/pregame` | 🏟️ | ✅ | homeWinProbability + **spread** (a free market anchor) |

### 2.4 Player-advanced (PBP-derived, CFBD-computed) ✅ — **but only from 2013/2014**

| Endpoint | Grain | Verified | Fields |
|---|---|---|---|
| `/ppa/players/games` | 🏟️🧍 | ✅ **2014+ (0 before)** | averagePPA {all, pass, rush} per player-game |
| `/ppa/players/season` | 🗓️🧍 | ✅ (year-only OK; 5,209 players) | averagePPA + **totalPPA** × {all, pass, rush, firstDown, secondDown, thirdDown, standardDowns, passingDowns} |
| `/player/usage` | 🗓️🧍 | ✅ (year-only; 5,209) | **usage share** {overall, pass, rush, firstDown, secondDown, thirdDown, standardDowns, passingDowns} |
| `/player/returning` | 🗓️👥 | ✅ (134 teams) | returning production: percentPPA, percent{Passing,Rushing,Receiving}PPA, usage |
| `/stats/player/season` | 🗓️🧍 | ✅ (year-only; **138,693 rows**) | long-format category/statType/stat |

### 2.5 Rosters, recruiting, reference ✅

| Endpoint | Grain | Verified | Notes |
|---|---|---|---|
| `/roster` | 🗓️🧍 | ✅ year-only → **30,072 players** | id, name, position, jersey, height, weight, year, hometown, **recruitIds** |
| `/player/search` | 🧍 | ✅ | + `teamStints` (transfer history) |
| `/player/portal` | 🗓️🧍 | ✅ (4,499 rows 2025) | transfer portal: origin, destination, rating, stars, eligibility |
| `/recruiting/players` | 🗓️🧍 | ✅ year-only (2,507); 2000+ | stars, rating, ranking, **athleteId** (→ roster `recruitIds`) |
| `/recruiting/teams`, `/talent` | 🗓️👥 | ✅ | class rankings; **team talent composite** (the mismatch-regime feature, roadmap §4) |
| `/teams/fbs`, `/venues`, `/coaches`, `/calendar` | 🗓️ | ✅ | 136 FBS teams; venue incl. **dome, elevation, grass, timezone**; coach history w/ SP+ |

### 2.6 Betting (CFBD's own) ✅ — a free cross-check, **not** our primary

`/lines` → per game: provider, spread, spreadOpen, overUnder, overUnderOpen, homeMoneyline, awayMoneyline.
Useful as a **free historical line back to 2004** (deeper than the Odds API's 2020 floor) and as a consensus cross-check.
**The Odds API remains primary** for per-book pricing/CLV (Bovada is our target book; CFBD `/lines` providers are a thin consensus).

### 2.7 ⛔ Season coverage — **the hard floor, and it bites**

Observed league-wide row counts at week 5 (no team filter — an earlier team-filtered probe was confounded by bye weeks):

| Dataset | 2004 | 2006 | 2008 | 2010 | 2012 | 2014 | **Usable from** |
|---|---|---|---|---|---|---|---|
| `/games/players` (box) | 49 | 54 | 53 | 52 | 54 | 54 | **2004** |
| `/games/teams` (box) | 49 | 54 | 53 | 52 | 54 | 54 | **2004** |
| `/plays` (PBP) | 6,527 | 7,844 | 9,206 | 9,371 | 9,740 | 9,783 | **2004** (thinner early) |
| `/stats/game/advanced` | 68 | 92 | 102 | 104 | 102 | 102 | **2004** (thinner early) |
| **`/ppa/players/games`** | **0** | **0** | **0** | **0** | **0** | 964 | **⚠️ 2014** |
| **`/plays/stats`** (targets!) | **0** | **0** | **0** | **0** | 92 | 2,000 | **⚠️ 2013** |

⇒ **Team/box/PBP history: 2004+. Player-ADVANCED history (usage, player PPA, targets): 2014+.**
**Recommended backfill window: 2014–2025 (12 seasons)** — the deepest window where *every* modelled feature exists.
Optionally extend team-only features to 2004. (Note: PFF College grades also start 2014 — the windows coincide.)

---

## 3. The Odds API — NCAAF ✅ (existing sub; no new cost)

| Item | Verified |
|---|---|
| Sport keys | `americanfootball_ncaaf` (active), `americanfootball_ncaaf_championship_winner` (outrights) |
| Live coverage | **78 events already priced for the 2026 season** (opener 2026-08-29), **11 US books** |
| Books | fanduel, draftkings, **bovada** ⭐, betmgm, **williamhill_us** (= Caesars-US), fanatics, betrivers, mybookieag, betonlineag, lowvig |
| Core markets | `h2h`, `spreads`, `totals` — on the bulk `/odds` endpoint |
| Alt/derivative | `alternate_spreads`, `alternate_totals`, `team_totals` — ⚠️ **event endpoint only** (bulk `/odds` returns `422 INVALID_MARKET`) |
| **Player props** | ✅ **proved via a historical in-season snapshot** (2024-11-02, Ohio State @ Penn State): `player_anytime_td` (DK, FanDuel, **Bovada**), `player_pass_yds`, `player_rush_yds`, `player_reception_yds` (FanDuel). ⚠️ **THIN** — FanDuel posted only 2 pass-yds outcomes (the starting QB) and 4–6 rush/rec; Bovada posted anytime-TD only. Props are **marquee-game / top-player biased**, nothing like MLB's depth. |
| Scores (settlement) | ✅ `/scores` (`daysFrom` ≤ 3) |
| **Historical depth** | ✅ **2020 → present.** 2020-09-12 ✅ (22 ev), 2020-11-07 ✅ (40), 2021 ✅ (68), 2023 ✅ (55), 2024 ✅ (53). **2019 → 0 events = the floor.** ⇒ **CLV/backtest window = 2020–2025 (6 seasons).** |
| Credit cost | bulk `/odds` = 3 credits (3 markets); historical `/odds` = 10/market; historical **event** props = ~40. Remaining: **4,656,790**. |

**Why it matters:** props are too thin for an MLB-style prop engine, but `h2h`/`spreads`/`totals` are deep across 11 books —
which is exactly what Phase-2's re-pointed instruments (E13.16 microstructure, E13.14 cross-market) need. The
**offseason caveat**: player props could not be observed on the *live* endpoint in July (no book posts them 7 weeks out);
the historical snapshot is the honest proof they exist in-season.

---

## 4. ⭐ The NFL feeder — draft/combine + the ID xref (P0.3's spine)

### 4.1 The ID-space truth (this is the load-bearing finding)

| System | Example | Note |
|---|---|---|
| CFBD `collegeAthleteId` | `4431611` | ESPN-style numeric college athlete id |
| CFBD `nflAthleteId` | `108247` | **NOT** an ESPN NFL id — **∩ nflverse `espn_id` = 0 of 257** |
| nflverse `cfb_player_id` / combine `cfb_id` | `caleb-williams-3` | a **sports-reference SLUG**, not a number |
| nflverse `gsis_id` / `pfr_player_id` | `00-0039918` / — | the NFL-side keys |

⇒ **There is NO direct ID join between CFBD and nflverse.** Any plan that assumes one is wrong.

### 4.2 The deterministic key that DOES work: **the draft slot**

`CFBD /draft/picks (year, overall)` ⇄ `nflverse draft_picks (season, pick)` — nflverse `pick` is the **overall** pick
(round 2 starts at 33, confirmed). Every draft slot is unique, so this is a clean 1:1 key.

| Season | CFBD picks | Matched → `gsis_id` | Match % | Independent surname agreement |
|---|---|---|---|---|
| 2015 | 256 | 254 | 99.2% | 98.4% |
| 2016 | 253 | 253 | 100.0% | 100.0% |
| 2017 | 253 | 252 | 99.6% | 99.2% |
| 2018 | 256 | 256 | 100.0% | 97.7% |
| 2019 | 254 | 254 | 100.0% | 96.9% |
| 2020 | 255 | 253 | 99.2% | 98.8% |
| 2021 | 259 | 259 | 100.0% | 96.9% |
| 2022 | 262 | 262 | 100.0% | 98.1% |
| 2023 | 259 | 258 | 99.6% | 93.8% |
| 2024 | 257 | 256 | 99.6% | 97.3% |
| 2025 | 257 | 256 | 99.6% | 91.8% |
| **Total** | **2,821** | **2,813** | **99.7%** | — |

Surname agreement is computed *independently of the join* — it is the validation that the slot key is sound, not circular.
(Residual disagreement is name-normalisation: suffixes, `Jr.`, apostrophes.)

### 4.3 Datasets

| Dataset | Source | Grain | Coverage | Key fields |
|---|---|---|---|---|
| `draft_picks` | nflverse release Parquet | 🧍 pick | **1980–2026**, 12,927 rows | `season, round, pick(overall), gsis_id, pfr_player_id, cfb_player_id, college, position` + **career outcomes** (`car_av`, `w_av`, `games`, `seasons_started`, `probowls`, `allpro`, `hof`, plus career pass/rush/rec lines) ⇒ **the feeder's TARGET variable is already here** |
| `combine` | nflverse release Parquet | 🧍 | **2000–2026**, 8,968 rows | `forty, vertical, bench, broad_jump, cone, shuttle, ht, wt, school, pos, cfb_id, pfr_id, draft_ovr` — **includes invited-but-undrafted players** |
| `players` | nflverse release Parquet | 🧍 | 25,033 | the NFL ID universe: `gsis_id, pfr_id, espn_id, pff_id, otc_id, smart_id, esb_id, nfl_id` (`espn_id` 33% null) |
| CFBD `/draft/picks` | CFBD | 🧍 pick | **2000+** (254–257/yr) | `collegeAthleteId` ⇐ **the bridge back into the CFBD college universe**, + `preDraftGrade`, `preDraftRanking`, `preDraftPositionRanking` |

**Combine attach (clean, null keys dropped, no cartesian):** of 2,821 drafted players 2015–25 — 93.6% carry a
`cfb_player_id` slug, **81.8% attach to a combine row, 65.7% have a 40-time.**

### 4.4 The resolved xref recipe for P0.3

```
CFBD college player  ──(collegeAthleteId)──▶  CFBD /draft/picks (year, overall)
                                                        │  deterministic slot join  (99.7%)
                                                        ▼
                              nflverse draft_picks (season, pick) ──▶ gsis_id / pfr_player_id / cfb_player_id
                                                        │  slug join (nflverse-internal)
                                                        ▼
                                        nflverse combine (cfb_id) ──▶ forty/vertical/bench/…
```
**Gaps P0.3 must still solve:** (a) **UDFAs** have no draft slot ⇒ genuinely need fuzzy `name + school + position + year`
matching; (b) **transfers** — a player's CFBD college production spans multiple schools (use `/player/portal` +
`/player/search.teamStints`); (c) name-normalisation for the ~2–8% surname disagreement.

---

## 5. 💰 The PFF / paid-charting decision — **DEFER (and it's not even a clean buy)**

**What PFF College uniquely has** (verified as *absent* from every CFBD endpoint probed): individual **grades** and charting —
OL pass-block/run-block grades + **pressures allowed**, DB **coverage grade** + completion% / passer-rating allowed,
WR **separation / YPRR / contested-catch / drop rate**, RB **yards-after-contact / forced missed tackles**,
QB **CPOE / air yards (ADOT) / time-to-throw / big-time-throw / turnover-worthy-play**. Grades go back to **2014** — the
same floor as CFBD's player-advanced data, so the windows align cleanly *if* we ever buy.

**⛔ The catch that settles it:** the PFF product at **$119.99/yr (PFF+, annual; $24.99/mo)** is a **website/UI subscription**
— player grade pages, a betting dashboard, Premium Stats tables. It is **not an API and not a bulk-data license.** Ingesting
it into a lakehouse would mean scraping a paywalled product (a ToS and engineering problem), or negotiating a
quote-based **enterprise data licence** (price not public). **So "buy PFF" is not a $120 line item — it's a licensing project.**

**RECOMMENDATION (matches the roadmap's default lean, now with evidence): ship Tier-A + PBP-derived proxies FIRST.**
Revisit PFF only if (a) the Tier-A model demonstrably earns, **and** (b) an ablation shows the residual error concentrates
in exactly what grades measure (trench play / coverage). Treat it as an **edge-gated, licence-negotiated** buy — never a
Phase-0 cost.

---

## 6. 🧮 The call budget — why Tier 3 is the buy

**Free tier = 1,000 calls/mo, confirmed live** (`X-Calllimit-Remaining: 956` after ~44 probe calls; this session used ~110).

Per-season call cost of a full pull (~16 week-units = 15 regular + postseason):

| Class | Endpoints | Calls / season |
|---|---|---|
| Week-grained (`week` required or per-week natural) | `/games`, `/games/teams`, `/games/players`, `/plays`, `/drives`, `/stats/game/advanced`, `/ppa/games`, `/ppa/players/games`, `/metrics/wp/pregame`, `/lines`, `/ratings/elo` = 11 × 16 | **176** |
| **Per-GAME** (forced by the 2,000-row cap) | `/plays/stats` — ~60 FBS games/wk × 16 | **~960** |
| Season-grained (year-only ⇒ 1 call each) | `/roster`, `/player/usage`, `/stats/player/season`, `/ppa/players/season`, `/player/returning`, `/ppa/teams`, `/stats/season(+advanced)`, `/ratings/sp|srs|fpi`, `/talent`, `/recruiting/players|teams`, `/player/portal`, `/coaches`, `/teams/fbs`, `/calendar`, `/draft/picks` | **~19** |
| | **Total** | **~1,155 / season** |

| Scenario | Calls | Verdict on the free 1,000/mo tier |
|---|---|---|
| **Backfill 2014–2025** (12 seasons, full incl. `/plays/stats`) | **~13,860** | ❌ ~14 months |
| + team/box/PBP-only 2004–2013 (10 × ~195) | +1,950 → **~15,810** | ❌ ~16 months |
| **In-season steady state** (~80 calls/week) | **~350 / month** | ✅ *fits* the free tier |

⇒ **The backfill is the only thing the free tier can't do — and it's a one-time job.**
**BUY Patreon Tier 3 — $10/mo, 75,000 calls/mo** ([tiers](https://collegefootballdata.com/api-tiers)): the entire
~15.8k-call backfill completes **inside a single month with ~5× headroom**, and it also unlocks **GraphQL** (Tier 3) and
**live play-by-play** (Tier 2+, which we proved is 401-gated today). Steady-state could revert to free, but at **$10/mo the
churn isn't worth it — keep the sub while NCAAF is active.** Tier 2 ($5/mo, 30k) would also clear the backfill in one month
but leaves no headroom for re-pulls and no GraphQL; **Tier 3 is the right buy.**

---

## 7. ✅ The by-position coverage map — **RESOLVED against live endpoints**

Roadmap §2's wishlist, every item marked with the **named source** that delivers it.

**Legend:** ✅ = free/Tier-A, live-verified · 🟡 = derivable by us from PBP (`/plays` + `/plays/stats`), not served ready-made · 💰 = PFF-only · ⛔ = genuine gap

### QB
| Wishlist item | Verdict | Source |
|---|---|---|
| Box: cmp/att/yds/TD/INT/sacks/rush | ✅ | CFBD `/games/players` (passing, rushing) + `/games/teams` (sacks) |
| QBR | ✅ | CFBD `/games/players` passing.QBR |
| EPA/play, success rate, usage share | ✅ | CFBD `/ppa/players/games`, `/ppa/players/season`, `/player/usage` (**2014+**) |
| Pressure→sack, hurries (team-level) | ✅ | CFBD `/games/teams` **qbHurries**, sacks; `/stats/*/advanced` havoc |
| **CPOE** | 🟡→💰 | no completion-probability model is served; a **CPOE proxy is derivable** from `/plays` (down/distance/yardline) but **true CPOE needs air yards** ⇒ effectively 💰 PFF |
| **Air yards / ADOT** | 💰 | ⛔ not in any CFBD field. `playText` is prose; air yards are **not** charted free. **PFF only.** |
| **Time-to-throw**, big-time-throw / turnover-worthy-play grades | 💰 | PFF only |

### RB
| Wishlist item | Verdict | Source |
|---|---|---|
| Box: rush/rec lines, fumbles | ✅ | CFBD `/games/players` (rushing, receiving, fumbles) |
| EPA/rush, success rate, usage/snap share | ✅ | CFBD `/ppa/players/*`, `/player/usage` |
| Explosive-run rate, **stuff rate**, line-yards, second-level, open-field | ✅ | CFBD `/stats/game/advanced` + `/game/box/advanced` **rushing block** (team grain) |
| Player-level explosive-run rate | 🟡 | derive from `/plays` (yardsGained distribution per rusher) |
| **Yards-after-contact, forced missed tackles** | 💰 | PFF only |
| **YPRR** | 💰 | needs routes run — PFF only |

### WR / TE
| Wishlist item | Verdict | Source |
|---|---|---|
| Box: rec/yds/TD | ✅ | CFBD `/games/players` receiving |
| **Targets** ⇒ **target share** | ✅ | ⭐ CFBD **`/plays/stats`** `statType='Target'` (**2013+**) — *not* in the box score; this endpoint is why it's ✅ not ⛔ |
| EPA/target, usage share | ✅ | CFBD `/ppa/players/*` + `/player/usage` |
| **aDOT** | 💰 | ⛔ air yards are not charted free (see QB) — **PFF only.** *(roadmap §2 optimistically listed aDOT as ✅-from-PBP; **that is now corrected to 💰**)* |
| Drop rate | 🟡 | partially derivable — `/plays/stats` has `Incompletion`/`Pass Breakup`, but **a "drop" is a charting judgement**; a proxy only |
| **Separation, YAC-over-expected, contested-catch %, YPRR** | 💰 | PFF only (tracking/charting) |

### OL — ⛔ **the confirmed gap**
| Wishlist item | Verdict | Source |
|---|---|---|
| **Individual OL production** | ⛔ **CONFIRMED GAP** | **No free source exists.** Verified: `/games/players` has **no OL category** (its 8 categories are passing/rushing/receiving/fumbles/defensive/interceptions/puntReturns/kicking); `/plays/stats` stat types are ball-carrier/defender events. **An OL only appears in the data when he is penalised.** |
| **UNIT-level OL proxies** | ✅ | CFBD `/stats/game/advanced` + `/game/box/advanced` **rushing**: `lineYards`, `lineYardsAverage`, `secondLevelYards`, `openFieldYards`, `powerSuccess`, `stuffRate`; `/games/teams`: **sacks allowed**, TFL allowed; `/stats/*/advanced`: **havoc allowed** |
| Individual pass-block/run-block grade, **pressures allowed** | 💰 | PFF only |
⇒ **Model OL at the UNIT level from Tier-A team line-metrics. Individual OL is a PFF-gated reach — exactly as the roadmap predicted, now verified.**

### Defense
| Wishlist item | Verdict | Source |
|---|---|---|
| Team: havoc (total/frontSeven/**db**), stuff rate, PPA/EPA + success allowed, explosiveness allowed | ✅ | CFBD `/stats/*/advanced` (defense block) + `/game/box/advanced` **havoc** |
| Individual box: tackles, TFL, sacks, **QB hurries**, INT, PBU, FF | ✅ | CFBD `/games/players` **defensive** + interceptions categories; `/games/teams` qbHurries/passesDeflected |
| Individual pressure rate / pass-rush win rate | 🟡→💰 | sacks+hurries are box-countable ✅, but **true pressure rate needs snap counts + charting** ⇒ 💰 |
| **Coverage grade, completion% / passer-rating allowed in coverage** | 💰 | ⛔ CFBD has **no defender-in-coverage attribution**. `/plays/stats` gives `Pass Breakup` (a partial proxy). **PFF only.** |
| **Missed-tackle rate** | 💰 | PFF only |
| Snap counts (all positions) | ⛔ | **No CFBD snap-count endpoint** (NFL has one via nflverse; college does not). Use `/player/usage` (**play-share by usage**) as the proxy. |

### Priors / context (bonus — all ✅, and richer than the roadmap assumed)
Recruiting stars/ratings (`/recruiting/players`, 2000+) · **team talent composite** (`/talent`) · **transfer portal**
(`/player/portal`) · returning production (`/player/returning`) · coaching history (`/coaches`) · venue **dome / elevation /
grass / timezone** (`/venues`) · SP+/FPI/Elo/SRS. ⇒ the **talent-mismatch regime axis** (roadmap §4) is well-supplied.

---

## 8. 🔒 Locked Phase-0 source set (what P0.2 + P0.3 build against)

**Backfill window: 2014–2025** (player-advanced floor; optionally 2004+ for team-only features).
**Lake layout** (per `sport_data_platform.md §3`): `s3://<bucket>/ncaaf/raw/<source>/season=YYYY/[week=NN/]…`

| # | Lake table | Endpoint | Grain | Partition | Cadence |
|---|---|---|---|---|---|
| 1 | `games` | CFBD `/games` | 🏟️ | season/week | weekly |
| 2 | `game_team_stats` | CFBD `/games/teams` | 🏟️👥 | season/week | weekly |
| 3 | `game_player_stats` | CFBD `/games/players` | 🏟️🧍 | season/week | weekly |
| 4 | `plays` | CFBD `/plays` | ▶️ | season/week | weekly |
| 5 | **`play_stats`** | CFBD `/plays/stats` **per gameId** | ▶️🧍 | season/week | weekly (**the target-share source**) |
| 6 | `drives` | CFBD `/drives` | 🏟️ | season/week | weekly |
| 7 | `game_advanced` | CFBD `/stats/game/advanced` | 🏟️👥 | season/week | weekly |
| 8 | `box_advanced` | CFBD `/game/box/advanced` (`id=`) | 🏟️👥 | season/week | weekly (optional; overlaps #7) |
| 9 | `ppa_players_games` | CFBD `/ppa/players/games` | 🏟️🧍 | season/week | weekly |
| 10 | `player_usage` | CFBD `/player/usage` | 🗓️🧍 | season | weekly |
| 11 | `roster` | CFBD `/roster` | 🗓️🧍 | season | weekly |
| 12 | `team_advanced_season` | CFBD `/stats/season/advanced` | 🗓️👥 | season | weekly |
| 13 | `ratings_sp` (+ srs/fpi/elo) | CFBD `/ratings/*` | 🗓️👥 | season | weekly |
| 14 | `talent`, `recruiting_players`, `recruiting_teams` | CFBD | 🗓️ | season | seasonal |
| 15 | `transfer_portal`, `returning_production` | CFBD | 🗓️ | season | seasonal |
| 16 | `teams`, `venues`, `coaches`, `calendar` | CFBD | 🗓️ | season | seasonal |
| 17 | `cfbd_draft_picks` | CFBD `/draft/picks` | 🧍 | season | seasonal |
| 18 | `odds_ncaaf` | Odds API `/odds` (h2h, spreads, totals) | 🏟️ | season/week | **intraday in-season** |
| 19 | `odds_ncaaf_props` | Odds API event endpoint | 🏟️🧍 | season/week | in-season (thin) |
| 20 | `odds_ncaaf_scores` | Odds API `/scores` | 🏟️ | season/week | daily in-season |
| 21 | `odds_ncaaf_historical` | Odds API `/historical/*` (**2020+**) | 🏟️ | season | one-time backfill |
| 22 | **`nflverse_draft_picks`** | nflverse release Parquet | 🧍 | season | seasonal (**feeder target**) |
| 23 | **`nflverse_combine`** | nflverse release Parquet | 🧍 | season | seasonal |
| 24 | `nflverse_players` | nflverse release Parquet | 🧍 | — | seasonal |

**Cost line:** CFBD **$10/mo** (Tier 3) · Odds API **$0 incremental** (existing sub, 4.66M credits) · nflverse **$0** ·
compute = Lambda + DuckDB-over-S3 (pennies). **⇒ Total new Phase-0 spend: $10/mo.**

---

## 9. Open gaps (carry into P0.2/P0.3 and Phase 1)

1. **⛔ Individual OL production** — no free source, anywhere. Unit-level only. *(PFF-gated)*
2. **⛔ Air yards / aDOT / CPOE** — not charted free. **This corrects roadmap §2**, which listed aDOT as ✅-from-PBP. *(PFF-gated)*
3. **⛔ Snap counts** — no college equivalent of nflverse `snap_counts`. Proxy = `/player/usage` play-share.
4. **⚠️ Player-advanced history starts 2014**, not 2004 — caps the feeder's training window at ~12 draft classes.
5. **⚠️ Odds history starts 2020** — CLV/backtest window is 6 seasons (CFBD `/lines` reaches back to 2004 as a thinner consensus cross-check).
6. **⚠️ NCAAF player props are thin** (marquee games/top players only) — do **not** assume an MLB-style prop surface.
7. **UDFA feeder coverage** — the draft-slot key covers drafted players only; UDFAs need fuzzy matching (P0.3).
8. **Non-FBS (FCS) opponents** — CFBD covers them unevenly; decide an FBS-only modelling universe in P0.2.
9. **⛔ NIL $ valuations** — the paid/scraped talent-money signal. **Documented + deferred in §10** (P0.4 shipped the FREE transfer/roster-continuity signal instead). *(edge-gated, PFF-class)*

---

## 10. 💰 The NIL-$ decision — **DEFER (PFF-class; ship the FREE portal/continuity signal first)** — P0.4

**The thesis (roadmap P0.4):** the transfer portal + NIL money are re-shaping lower-conference power — talent moves fast now,
so the game model needs a **roster-continuity / talent-flux** input or it will misprice teams whose roster turned over.

**✅ What P0.4 SHIPPED (FREE, CFBD-only, landed + validated):** the derived mart **`ncaaf_team_roster_continuity`**
(`sports_dbt/models/ncaaf/marts/`, one row per season+team, FBS, 2014–2025), a leakage-safe (pre-season, as-of) per-team-season
signal combining:
- **Returning production** — CFBD `/player/returning` (`returning_ppa_pct` = the headline "returning production %", + pass/rec/rush splits + usage).
- **Transfer-portal flux** — CFBD `/player/portal` (in/out counts, star- & 247-rating-weighted, blue-chip in/out, attrition/uncommitted). Portal era = **2021+** (`portal_data_covered` flags it).
- **Roster year-over-year continuity** — CFBD `/roster` head-count overlap (same player, same team, N & N-1).
- **Talent level + flux** — CFBD `/talent` (247 composite + YoY delta; 2015+).

All four raw feeds were already locked in the §8 Phase-0 set (P0.2), so P0.4 added **zero new ingest / cost** — it is a pure dbt
derivation. Feeds **P1.2** (a team-strength covariate) + **P1.3** (features).

**⛔ NIL $ valuations — NOT cleanly buyable (the PFF pattern, §5).** The known sources are **On3 NIL Valuation / On3 NIL 100**
and **Rivals** (On3 merged into Rivals/Yahoo in 2024) — per-athlete $ valuations + team "roster value" / collective rankings,
computed by a proprietary algorithm. **⚠️ Source-honesty note: unlike every CFBD claim in this doc, these were NOT ground-truthed
on a live pull — there is no public bulk API to pull.** Ingesting NIL $ would mean **scraping a paywalled / ToS-protected website
product**, or a **quote-based enterprise data licence (price not public)** — exactly the PFF licensing-project class, not a clean
line item. (Adjacent: **Opendorse** holds transactional NIL-deal data, also private/marketplace-gated.)

**RECOMMENDATION:** ship on the FREE transfer/roster-continuity signal (done). Revisit NIL $ **only** if (a) the Phase-1 model
demonstrably earns, **and** (b) an ablation shows residual error concentrating where roster-money would explain it *beyond* what
returning-production + portal-star-flux + talent already capture (they proxy much of the same talent-retention/acquisition
axis for free). Treat NIL $ as an **edge-gated, licence-negotiated** buy — **never a Phase-0 dependency.**

---

## 11. 🧭 Coaching-change data — **HC FREE from CFBD (shipped); OC/DC DEFERRED (gap, no free API)** — P0.5

**The thesis (roadmap P0.5):** a new HC/OC/DC can flip a team's scheme + scoring profile overnight (~63–71 new Power-4
coordinators in the 2026 cycle alone) → the game model needs a **coaching-continuity** input or it will misprice a team whose
staff turned over.

**✅ HEAD COACH — SHIPPED FREE (CFBD `/coaches`, ground-truthed live 2026-07-19).** The endpoint is **year-only** (1 call/season,
no team loop) and returns one record per coach with a `seasons` array of per-year rows carrying **school, year, wins/losses, srs,
and ⭐ the SP+ splits `spOverall`/`spOffense`/`spDefense`**. A `minYear/maxYear` pull returns each coach's FULL multi-season
career (e.g. Jeff Brohm, 12 seasons across schools) — confirming the endpoint carries the **prior-track-record** signal the story
called for. Live pull (2014–2025): **381 coaches, 1,568 (school,year) cells, ~133 FBS schools/season**; **107 cells (~7%) had >1
coach** = a mid-season change/interim. `spOverall` is present on 1,623/1,678 season-rows (nulls = early/FCS).

Landed as:
- **`coaches`** — the 25th §8 lake table (CFBD `/coaches`, year-only, season-partitioned Delta; added to `ingest/sources.py`).
- staging **`stg_ncaaf_coaches`** — the `seasons` array EXPLODED to a coach-school-season grain (SP+ splits typed).
- mart **`ncaaf_team_coaching_change`** (`sports_dbt/models/ncaaf/marts/`) — ONE row per (season, team), FBS spine (same
  returning-production universe as P0.4). Emits: **HC identity + tenure**, **year-over-year HC-change flag**
  (`hc_change_from_prev`, NULL at the 2014 floor), **mid-season-change flag** (`hc_midseason_change`, coach of record = most
  games), and ⭐ **the coach's PRIOR SP+ profile** (`hc_prior_sp_overall/offense/defense_avg` career-to-date + `hc_recent_sp_*`
  most-recent-prior-season + `is_first_time_hc`). ⭐ **Leakage-safe:** HC identity/change/tenure are known pre-season; the
  prior-SP+ aggregates read **strictly seasons before `season`** — the current-season SP+ row is used only to identify the coach,
  never emitted as a feature. Feeds **P1.3** (the coaching feature block).

**⛔ OC/DC (coordinators) — NOT in CFBD → DEFERRED (gated like NIL-$, §10).** CFBD `/coaches` is **head-coach only**; there is no
CFBD coordinator endpoint (verified — the coach record has no coordinator field). The **known trackers are editorial, not APIs:**
- **FootballScoop** — the industry OC/DC coaching-change tracker (also **ESPN** / **CBS Sports** hire trackers). ⚠️ **Source-honesty
  note: like the NIL-$ sources in §10, these were NOT ground-truthed on a live pull — there is no public bulk/free API.** Ingesting
  OC/DC would mean **scraping an editorial/ToS-protected site** or **maintaining a small hand-curated season table** (labor, not a
  clean feed).
- **SportsDataIO** — a PAID vendor that *does* expose coordinators via a licensed API (price quote-based, not public) — the paid
  alternative, same class as PFF/On3: an edge-gated licence, **never a Phase-0 dependency.**

**RECOMMENDATION:** ship the FREE HC-continuity signal (done). Add OC/DC **only** as a best-effort scraped/manual layer if a
Phase-1 ablation shows residual error where a coordinator change would explain it beyond the HC signal + returning-production +
roster flux (P0.4) — and even then prefer a **small curated season seed** over a fragile scraper. Treat OC/DC as **best-effort /
edge-gated**, gated exactly like NIL-$ (§10) — **not a blocker for P1.3.**

---

_Ground-truthed 2026-07-13 against CFBD v2 (live, free-tier key), The Odds API v4 (live), and nflverse release Parquet.
Row counts and field lists are observed, not documented. Re-verify before any tier/licence purchase._
_§10 (NIL / roster-continuity) added 2026-07-19 (P0.4) — the CFBD `/player/returning`, `/player/portal`, `/talent`,
`/roster` schemas were re-pulled live; the NIL-$ (On3/Rivals) claims are documented-as-unavailable, NOT live-pulled (no public API)._
_§11 (coaching-change) added 2026-07-19 (P0.5) — CFBD `/coaches` re-pulled live (year-only + minYear/maxYear); the HC signal is
shipped free, the OC/DC (FootballScoop/ESPN/CBS/SportsDataIO) claims are documented-as-unavailable-free, NOT live-pulled._
