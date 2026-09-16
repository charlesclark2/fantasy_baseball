# NF-WVR1 node 1 — the FA pool, the freshness dependency, and the season-ROS source: diagnosis

**Status: NODE 1 COMPLETE. TWO BLOCKING findings, reported to the PM before endpoint code.**

Measured 2026-09-15 (UTC) against the **live** published board, the **live** nflverse release, the
**live** `dev` tree and RC1's in-flight branch. Every column and field name below came out of a
payload, a `DESCRIBE`, or the source file it is attributed to — never out of a spelling that looked
right (the MT1 probe rule).

The spec's node 1 asks three questions. All three are answered, and **two of the three answers
contradict a premise the spec builds on**, which is why this node stops rather than proceeding into
node 2's recipe.

---

## 0. The short version

| # | Finding | Severity |
|---|---|---|
| **F1** | **The season board carries no rest-of-season projection.** It is a FULL-SEASON projection (max `g` = 17.000) that does not decrement as weeks are played. The only ROS artifact in the system is the WEEKLY model's roll-up — the substrate this spec forbids. | 🚨 **BLOCKING** |
| **F1b** | A **live paid surface already mislabels it**: `my-teams` says "Projections are the rest-of-season figure (pre-kickoff, so this is effectively the full season)". The parenthetical was true when written. Kickoff has passed. | ⚠️ live copy defect |
| **F2** | **Neither value column the board publishes orders an FA pool usefully.** Measured through the real scorer: the top-25 available players rank **6 QB / 3 TE / 16 K** by points and **14 K / 8 DST / 2 TE / 1 QB** by VOR. | 🚨 **BLOCKING** for node 2's recipe as written |
| **F3** | **The FA-pool substrate already exists and is already served** (`League.league_rosters` → `/nfl/league-board`). Only the *re-fetch* is missing — and **RC1's fetch does not close it**: it carries STARTERS only, by design. | dependency, stated |
| **F4** | **Coverage is fine; the ID JOIN is the risk.** 97.8% of real week-1 performers are on the board — but only via a two-step ladder. 113 of 870 board rows carry synthetic non-gsis ids (81 rookies + 32 D/ST). | design constraint |

---

## 1. F1 — the season board is FULL-SEASON, not rest-of-season 🚨

### The artifact, named precisely

| | |
|---|---|
| **Object** | `s3://$CACHE_BUCKET/fantasy/nfl/<season>/projections.json` |
| **Read through** | `app/backend/routers/fantasy.py::_full_projections` (memoized, 900 s TTL) |
| **Served by** | `/fantasy/nfl/projections-full` (paid, whole blob) · `/fantasy/nfl/league-board` + `/fantasy/nfl/my-teams` (scored output only) |
| **Rows** | 870 — QB 106 · RB 197 · WR 321 · TE 172 · K 42 · DST 32 |
| **Per-row value + interval** | `fpPpr` (point), `fpSd`, `fpP10` / `fpP90` (the published 80% band), `g` (projected games), `bye` |
| **Band coverage** | **870 / 870** rows carry `fpPpr` *and* `fpP10`/`fpP90` — no row is band-less |
| **Model** | `model_version: nfl_fantasy_nf1_5_v1`, `projection_source: nf1_5`, **`base_season: 2025`** |

### Refresh cadence in-season — it *is* rebuilt daily

`generated_at: 2026-09-15T14:21:50Z` — today. The build re-reads live inputs each day:

```
adp_as_of              2026-09-15   (FFC, ppr/12, window 09-08→09-15, 733 drafts)
ecr_as_of              2026-09-10   (FantasyPros PPR, 178 experts)
depth_chart_as_of      2026-09-15 12:39:14
sleeper_status_as_of   2026-09-15T13:30:14Z   (injury feed, 0.9 h old, coherence verdict OK)
injuryGamesStamp       44 of 44 fitted rows moved, largest move 4.57 games
designationDiscount    93 eligible rows, 93 discounted
```

So the board is **live and responsive to injury and market news**. That is not the problem.

### The problem, measured

```
max g = 17.000        min g = 0.700
players with g > 16.0 :  53      e.g. Josh Allen 16.50, Drake Maye 16.50, Jalen Hurts 16.50
```

An NFL team plays **17 games** in an 18-week season. **Week 1 completed Monday 2026-09-14** (RC1's
node 1 read this off the live `schedules` table; week 2 opens Thu 09-17). A rest-of-season figure
computed after week 1 therefore **cannot exceed 16 games** — and 53 rows exceed it, with the
maximum sitting exactly on the full-season count.

`fpPpr` is the season total over that same `g`. Christian McCaffrey: `g: 15.5`, `fpPpr: 355.2` — a
full-season line, on 2026-09-15, with one week already in the books.

**⇒ the board projects the FULL 2026 season, including games already played, and nothing decrements
it as weeks complete.** It is a *preseason* projection kept fresh on its *inputs*, not a
rest-of-season projection.

### The only ROS artifact in the system is the forbidden one

```
app/backend/models/nfl_weekly.py:308   "rest-of-season, summed over the remaining weeks on the frozen-form basis"
frontend/lib/fantasy-claim-copy.ts:1255   WEEKLY_ROS_LABEL = "Rest of season"
```

Rest-of-season exists exactly once, and it belongs to the **weekly** model — which NF-INC-0916 has
measured at **0.355 of realized** and which this spec rules off-substrate in as many words. So:

> **The spec's phrase "the season product's ROS projections (the draft board's live, trusted
> machinery)" names an artifact that does not exist.** The draft board's machinery is live and
> trusted; the quantity it publishes is not a ROS quantity.

This is the `plan_spec_process.md` spec-premise class (PM ruling 2026-09-01, NF-RATE1) — and the
premise is traceable: it reads like a paraphrase of the `my-teams` copy in F1b, which asserted the
equivalence under a parenthetical that has since expired.

### How much the gap will grow

Using a full-season number as a ROS proxy over-states remaining value by **at least** the fraction
of the season already played — ~5.9% after week 1, ~53% by week 10, 100% by week 18 — and that
floor is *uniform*, so it under-states the real per-player error, which is concentrated in exactly
the players a waiver surface is about. There is a partial in-season update channel (ECR/ADP are
model features and are refreshed), but note the vintages: **ECR `2026-09-10` sits *inside* week 1**
(09-09 → 09-14), so the currently-served board's expert channel does not yet reflect week-1 results.
ADP's window (09-08 → 09-15) does, partially.

### ⭐ …and the update channel is narrower than "rebuilt daily" suggests — it excludes production

A first pass left this as an open question. It is answerable structurally, and the answer is
decisive. `run_nf1.assemble_features` states its own contract:

> *"Every column is a **base-season realized quantity** or a **leakage-safe forward designation**
> for `projection_season`."*

`base_season` is **2025**. And the daily publish job refreshes exactly three feeds:

```
pipeline/jobs/sports_nfl_board_publish_job.py:82
BOARD_INPUT_SOURCES = ["depth_charts", "rosters", "weekly_rosters"]
```

No results feed of any kind — consistent with RC1's independent finding that `stats_player_week`
carries **zero 2026 rows** and has no scheduled in-season writer. So every performance feature
(`pergame_fp`, `snap_share`, `target_share`, `carry_share`, `base_games`) is a **2025** quantity.

**⇒ the board is structurally incapable of reflecting 2026 on-field production, and that is BY
DESIGN** — a leakage-safe preseason draft board is *supposed* to be blind to the season it projects.
It is the right design for its own job and the wrong substrate for a waiver ranking, which is
exactly a question about what has changed since the draft.

Its 2026-responsive channels, in full: **depth chart · roster status · injury & designation status ·
Vegas win totals · ADP/ECR**. Role, health and market — **not production**. Fernando Mendoza tops the
available pool at 268.3 projected points and did not take a snap in week 1; the board cannot know.

This narrows option (a) in §6 considerably: an honest label cannot stop at "refreshed daily for
injury and market news", because that leaves the impression the number tracks performance. It would
have to say the projection **does not reflect 2026 on-field production at all**.

---

## 1b. F1b — the live copy defect that follows ⚠️

`frontend/components/fantasy/my-teams.tsx`:

```
:26   // ROS = the season projection (pre-kickoff, so "rest of season" is effectively the full season)
:80   blurb="… Projections are the rest-of-season figure (pre-kickoff, so this is effectively the full season)."
:368  "… this page shows the season/ROS projection only."
```

True when written. **Kickoff has passed**, so a shipped, paid surface now calls a full-season number
"the rest-of-season figure" and justifies it with a condition that no longer holds. This is
independent of whether WVR1 ships and wants its own disposition.

---

## 2. F2 — neither published value column orders an FA pool 🚨

Node 2's recipe is "available players scored by the season product's ROS value, league-scored
server-side". Setting F1 aside entirely and asking only *"does the board's value column order the
available pool usefully?"* — measured through the **real** `league_scoring.replacement_levels`, over
the **live** 870-row board, 12-team full-PPR (`fpPpr` as the full-PPR point total, which is what it
is), FA pool proxied by "no ADP" (676 rows — nobody drafted them in a 12-team PPR sample):

```
replacement level   RB 148.6   QB 246.5   WR 151.2   TE 134.3   K 129.5   DST 109.4

TOP 25 available by RAW POINTS :  QB 6   TE 3   K 16
TOP 25 available by VOR        :  K 14   DST 8   TE 2   QB 1
```

The full list by VOR opens: Kenyon Sadiq (TE, +27.6), Fernando Mendoza (QB, +21.8), then **Jake
Elliott, Chase McLaughlin, Tyler Bass, Cairo Santos — four kickers** — then four team defences.

**The mechanism, and why VOR makes it worse rather than better.** The FA pool *is* the
below-replacement population **by construction** — that is what makes a player available. So
draft-VOR is ≤ 0 for essentially all of it, and the positions that float to the top are the ones
with the *smallest dispersion*: every kicker projects 125–138, so K sits within ~3 points of its own
replacement level while a genuinely useful available RB is 100+ points below his.

This is the repo's own recorded lesson, one surface over:

- **NF-C7** (PR #953): *"'best value on the board' LATE IN A DRAFT IS STRUCTURALLY A BACKUP TE/QB …
  once a 12-team room consumes the players who clear replacement, positive VOR survives only at the
  one-per-team positions where a bench player helps you LEAST."*
- **NF-C5** (PR #906): *"a starter-cutoff replacement carried into an auction is the bug."*

A waiver pool is the same situation in a harder form. **Carrying the draft board's replacement level
onto a waiver surface reproduces a defect this program has already paid for twice.**

⇒ **node 2's ranking cannot be built from the board's value columns as the spec describes it.**

### The narrowing that does survive the measurement

The skew is entirely a **cross-position** artifact. *Within* a position the board's ordering is a
legitimate and useful statement ("the best available RB"), and a waiver surface is naturally consumed
per position — which the spec's own need annotation already selects. So **rank within position, never
across it** is buildable from existing machinery, invents no arithmetic, and is strictly *more*
conservative than the spec's "any combined ordering states its rule". Offered as the option, not
taken unilaterally — it does not repair F1, which is the PM's call.

---

## 3. F3 — the FA-pool substrate exists; only the re-fetch is missing

### It is already stored and already served

`app/backend/models/fantasy.py:202` — and its own docstring names this very story:

> *"Two things it makes possible, neither of which was expressible before: **a TRUE free-agent pool
> (a player on nobody's roster**, instead of "outside the pool a league your size drafts"), and a
> comparison of your roster against the other teams in your own league."*

```
League.league_rosters            every team's roster, slimmed
League.league_rosters_synced_at  the age
League.league_rosters_truncated  whether whole teams were dropped
```

`/fantasy/nfl/league-board` already serves them joined to the scored board
(`fantasy.py::_joined_league_rosters`). **The FA pool is `board["players"]` minus the union of those
rosters** — an inversion of machinery that already runs, not new machinery.

### The freshness limit, stated by the field itself

> *"⚠️ A SNAPSHOT AT IMPORT TIME … **we never re-fetch**, so a waiver claim made after the import is
> invisible to us. `league_rosters_synced_at` is what keeps the age honest."*

This is exactly the risk the spec names: an FA pool from a stale import recommends already-rostered
players.

### ⛔ RC1's fetch does NOT close it — it carries STARTERS only

`app/backend/services/platform_import/sleeper_matchups.py` (RC1 branch `nf-wk-rc1`, commit
`2ab1dc24`) reads `GET /v1/league/<id>/matchups/<week>` and resolves, in its own words:

> *"only the ones that actually started: a recap lays out lineups, not rosters, so resolving bench
> players would be work nothing renders."*

That is **correct for a recap and insufficient for an FA pool**, which needs the whole rostered set —
bench, IR and taxi included, since those players are equally unavailable.

**The two objects also want opposite freshness semantics**, which is worth stating so the "one fetch
owner" rule is applied to the right seam:

| | RC1's weekly record | WVR1's FA pool |
|---|---|---|
| question | "what happened in week N" | "who is available **now**" |
| correct behaviour | **frozen** — *"a recap must be stable after it renders"* | **current** — a stale pool is the defect |
| grain | per (league, **week**) | per league, **latest** |
| source | `/matchups/{week}` → `starters` | `/rosters` → `players` |

**They are different objects on the same host, not a duplicated fetcher.** And `/league/{id}/rosters`
is already called twice in-tree — `sleeper._fetch_teams` (the import) and RC1's
`sleeper_matchups._team_names` (team labels). **So the one-owner rule points at extending
`platform_import/sleeper.py`, which already owns that endpoint** — not at a new module, and not at
forking RC1's.

**Dependency stated honestly: RC1's branch is unmerged** (`origin/nf-wk-rc1` does not exist; the work
is local on their worktree, 6 commits, D2 recorded "STOPPED, not shipped"). Nothing WVR1 needs is
blocked *by* it, because the capability WVR1 needs is a different endpoint on the same adapter — but
**the PM should confirm the seam** before either session writes the roster re-fetch, so it is written
once.

### Two storage constraints that bite a naive FA pool

1. **`LEAGUE_ROSTER_PLAYER_FIELDS = ("name","position","team")`** — `player_key` is deliberately
   dropped, so the subtraction **must** join by name+position (D/ST by franchise), which is what
   `league_scoring._join_key` already does. Measured on the live board: **870 rows → 870 distinct
   join keys, 0 collisions.** The join is clean today; that is a property to *guard*, not assume.
2. **`bound_league_rosters` truncates by WHOLE TEAMS** at `MAX_LEAGUE_ROSTER_PLAYERS = 500`. A
   truncated league's FA pool would contain every dropped team's players — **the exact
   plausible-but-wrong failure this story exists to avoid.** `league_rosters_truncated` is already on
   the record, so the surface can and must **refuse** rather than render a pool it knows is wrong.

---

## 4. F4 — coverage is adequate; the ID JOIN is the real risk

Measured against the **live** nflverse release
(`stats_player/stats_player_week_2026.parquet`, read directly — no ingest, so no collision with
NF-INC-0916's or RC1's ingest ownership): **1,118 REG rows, week 1 only.** Of the 357 skill-position
(QB/RB/WR/TE) rows:

```
matched to the board by gsis id   313   87.7%
matched by name+position           36   10.1%   <- the rookie / synthetic-id rows
TOTAL board coverage              349   97.8%
past the board's tail               8    2.2%
```

**The 8 genuinely-uncovered players all scored under 4 PPR** (best: Dohnte Meyers, WR CIN, 3.8; none
reached 5). So the spec's anticipated failure — *"a deep-league FA pool reaches past the board's
tail"* — is **real but small and low-stakes**, and the "stated absence, never a zero or an omission"
requirement still stands for those rows.

**The bigger risk is the join, not the tail.** 113 of 870 board rows carry an id that is **not** a
gsis id:

```
board rows with a non-gsis id: 113   (QB 10 · RB 13 · WR 36 · TE 22 · DST 32)   of which 81 are rookies
   MEN516487 Fernando Mendoza   LOV121782 Jeremiyah Love   SAD482340 Kenyon Sadiq   DST-DEN …
```

A gsis-id join therefore **silently drops the entire rookie class plus every team defence** — the
repo's documented crosswalk class (NF-INFRA1; NF-C-LDA-0's *"nflverse assigns no ESPN id until an
NFL-roster appearance … fails SILENTLY on exactly the players a draft cares about"*). Sleeper's own
rosters carry **Sleeper** ids, a third vocabulary again.

⇒ **the FA-pool subtraction must stay on `league_scoring._join_key` (name+position, D/ST by
franchise).** Anything that "improves" it to an id join reintroduces the defect. *(This also caught a
first-pass error in this diagnosis: an id-only coverage read reported 87.7% and listed Kenyon Sadiq
as both on and off the board.)*

---

## 4b. Observed in passing — the `contrib` driver block's vintage (NOT adjudicated)

Measured on the live payload, recorded because a waiver surface might want to show "why":

```
rows carrying `contrib`                702 of 870   (168 without)
featureContributionsMeta.generated_at  2026-08-02T03:28:32Z   (~6 weeks old)
featureContributionsMeta.model_version nfl_fantasy_nf1_v1
payload model_version                  nfl_fantasy_nf1_5_v1
```

So the driver block shown beside a player is stamped with a different model version from the
projection it explains, and is six weeks old. ⚠️ **I have NOT established this is a defect** — the
metadata stamps its own vintage and version honestly (so nothing is hidden), and NF1.5 is a
market-aware refinement layered on NF1, so NF1 attributions may legitimately explain the NF1
component by design. Flagged for whoever owns NF1.5 to confirm or dismiss; not a WVR1 finding.

---

## 5. ⚠️ The #1139 promotion hold — confirmed active

`gh pr view 1139` → **OPEN**, `dev` → `main`, `MERGEABLE`/`CLEAN`, and `origin/main..origin/dev` is
**21 commits**. NF-INC-0916 node 4 owns lifting it. So for WVR1: **merging to `dev` does not serve**,
and the usual "merged never means served" caveat is doubly true — a Phase A endpoint would sit behind
the hold. Per the spec, that is surfaced, never ridden or worked around.

---

## 6. What node 1 hands the rest of the story

**Answered:**
- the season-ROS source — `projections.json`, named, cadence measured (daily, live injury/market
  inputs), **and it is not a ROS projection** (F1);
- its coverage vs the FA pool — **97.8%**, tail risk small and low-stakes, **join risk real** (F4);
- FA-pool freshness — substrate already stored and served, **re-fetch missing**, RC1's fetch does not
  supply it, the seam named (F3).

**Blocked, needing a PM ruling before node 2:**
1. **The substrate.** The spec's ROS quantity does not exist. The weekly ROS roll-up is forbidden.
   A full-season number can be *labelled* honestly but its gap to ROS grows every week.
2. **The ranking.** Both published value columns rank an FA pool as a kicker/QB/DST list. The
   within-position narrowing (§2) is the one option that needs no new arithmetic.

**Not blocked and buildable today under any ruling:** the FA pool itself (who is available, with the
import age stated and a refusal on a truncated league) and the positional-need annotation from the
user's roster against their lineup slots — neither needs a projection.
