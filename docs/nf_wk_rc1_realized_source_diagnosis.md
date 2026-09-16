# NF-WK-RC1 node 1 — the realized weekly stat source: diagnosis

**Status: NODE 1 COMPLETE. One BLOCKING finding, reported to the operator before endpoint code.**
Measured 2026-09-15/16 (UTC) against the live lake, the live nflverse release, and the live
published api-cache. Every column name in this document came out of a `DESCRIBE` or a payload, never
out of a spelling that looked right.

---

## 1. The source

| | |
|---|---|
| **Table** | `nflverse.stats_player_week` — the NFL lake's Delta raw tier, `s3://credence-sports-lakehouse/nfl/raw/stats_player_week` |
| **Read through** | `quant_sports_intel_models.football.nfl.ingest.query_lake.q` / `delta()` |
| **Grain** | one row per player-week |
| **Width** | 145 columns |
| **Why this one** | it is the table the weekly champion already trains on: `run_nf_w1_weekly_bakeoff.load_sources_w1` reads it under `season_type = 'REG'`, and the NF-W0 label is pinned `v1.nflverse.stats_player_week`. The registry names it explicitly as "THE weekly fact (not legacy `player_stats`)". |
| **Own PPR** | `fantasy_points_ppr` — computed upstream, which makes it an INDEPENDENT parity anchor (§5) |

---

## 2. 🚨 BLOCKING — the table has no 2026 rows and no scheduled in-season writer

```
season  n_rows  n_weeks        stats_player_week, season_type='REG'
  2024   18128       18
  2025   18539       18
  2026       0        —        ← every 2026 week, including the two already played
```

This is not a lake outage. The discriminating probe separates the two candidate causes:

| lake table | in `ROLL_FORWARD_SOURCES`? | max season | 2026 rows |
|---|---|---|---|
| `schedules` | ✅ yes | **2026** | 272 |
| `weekly_rosters` | ✅ yes | **2026** | 5,450 |
| `injuries` | ✅ yes | **2026** | 182 |
| `snap_counts` | ❌ no | 2025 | **0** |
| `stats_player_week` | ❌ no | 2025 | **0** |
| `stats_team_week` | ❌ no | 2025 | **0** |

Every table **in** the recurring source set carries 2026. Every table **out** of it stops at 2025.

### Both legs of the NF-CAP1 test hold

The PM's 2026-09-13 ruling: *"zero rows in table X ⇒ process Y is not running" is only sound when
the spec names the MECHANISM, and you read an EXECUTION WITNESS rather than the row count.* Both are
available here and both agree.

**Mechanism.** `stats_player_week ∉ ROLL_FORWARD_SOURCES`, and the roll-forward is the only
recurring ingest. `sources.py` states the exclusion and its reasoning in as many words:

> DELIBERATELY EXCLUDED: the heavy per-play/advanced stack (…`stats_player_*`, `stats_team_week`,
> `snap_counts`…) — **those are populated from REALIZED games, so they don't exist yet for an
> unplayed season** and would just be repeated 404-clean-skips every refresh

That reasoning was **correct for the window it was written in** — the roll-forward was `3-8`
(March–August), a PRE-SEASON cadence, and a realized-outcome feed genuinely has nothing to say
before kickoff. **NF-FRESH2 P0 widened the WINDOW to `3-12,1-2`** (a full season cycle) to close the
`09-01` seasonal-boundary hole — and did not revisit the **SOURCE SET**, whose exclusion rationale
is only true pre-season. So the widening fixed the clock and carried a pre-season-only premise into
the season. The daily board-publish ingest does not close it either: `BOARD_INPUT_SOURCES` is
`["depth_charts", "rosters", "weekly_rosters"]`.

⭐ This is a **sibling of NCAAF-RF1, one level in**: there a month-range CRON was the seasonal hole;
here the cron was fixed and the SOURCE SET is the hole. Both have the same tell — a feed that is
structurally quiet exactly when it matters most.

**Execution witness** — the Delta transaction log, which records a write even when the write lands
zero rows:

```
stats_player_week    27 commits · newest @ 2026-07-18T01:19:46Z   ← the N0.2 backfill, ~2 months ago
snap_counts          14 commits · newest @ 2026-07-18T01:19:54Z   ← same backfill
schedules            37 commits · newest @ 2026-09-14T13:15:26Z   ← Monday's roll-forward
injuries             19 commits · newest @ 2026-09-14T13:15:31Z   ← Monday's roll-forward
weekly_rosters       76 commits · newest @ 2026-09-15T14:15:24Z   ← today's board-publish ingest
```

Nothing has written the realized tier since the one-time backfill. The roll-forward **is** running
(Monday 2026-09-14) — it simply does not carry this table.

### The data EXISTS upstream — this is our gap, not an absence

Read directly from the nflverse release, through the registry's own URL builder:

```
stats_player_week_2026.parquet  ✅ PUBLISHED — 1,118 REG rows, week 1, 32/32 teams,
                                  16/16 game_ids, 0 null fantasy_points_ppr
```

---

## 3. ⚠️ The spec's timing premise is wrong by a week — and in our favour

The spec states *"the first fully-scoreable week is week 2 (completes Tue 09-16 night)"*. Read off
the live `schedules` table:

| week | first day | last day | games | unplayed |
|---|---|---|---|---|
| **1** | 2026-09-09 Wed | **2026-09-14 Mon** | 16 | 1 → now 0 |
| **2** | **2026-09-17 Thu** | **2026-09-21 Mon** | 16 | 16 |
| 3 | 2026-09-24 | 2026-09-28 | 16 | 16 |

**Week 1 is the first completed week**, and it completed Monday 2026-09-14 (DEN @ KC, 20:15).
**Week 2 has not started** — it opens Thursday 2026-09-17 and completes **Monday 2026-09-21**, five
days later than the spec assumed. So the runtime gate does **not** wait until 09-21: week 1 is
scoreable the moment the feed lands.

---

## 4. Completeness semantics — when a week may render FINAL

Measured on week 1, whose Monday-night game ended ~2026-09-15 03:15Z. At **2026-09-16 02:34Z**
(~23h later) the upstream release carried **all 32 teams and all 16 `game_id`s**, including both MNF
participants. That matches the inventory's "nflverse updates within ~24h in-season" with a live
reading rather than a quotation.

**⭐ THE GATE IS A COUNT, NOT A CLOCK.** A week is FINAL when

```
count(distinct game_id) in stats_player_week for (season, week)
  ==  count(*) in schedules for that (season, week, game_type='REG')
```

A clock rule ("Tuesday morning") is wrong in the one case that matters: a postponed or flexed game
moves and the clock rule silently calls a 15/16 week final. The count is **derived from two
independent sources** and can only ever describe the data in hand — the NF-K1 direction. Anything
short of equality is **PARTIAL** and must say so (spec node 4); it must never render as final.

### ⚠️ A second, independent staleness hole on the same path

`schedules` refreshes on the **weekly Monday 06:15 PT roll-forward** — i.e. *before* Monday Night
Football. The live table proves it: 15 of 16 week-1 games carry a result, and the missing one is
DEN @ KC (Mon 20:15), whose result will not land until **Monday 2026-09-21**. So the
denominator of the completeness gate above, and any game-level result the recap shows, is **up to 7
days stale for exactly one game per week**. A recap that reads `schedules` for MNF would be wrong
for a week at a time.

---

## 5. `REALIZED_STAT_FIELD` — derived, and PROVEN field-by-field

`app/backend/services/realized_stat_fields.py`. Same shape as `nfl_weekly.resolve_component_fields`:
the **key set is the scorer's**, and `resolve_realized_fields` RAISES on any key this module names
that `projection_fields.STAT_FIELD` does not know. The converse — a scorer key with no realized
source — is an honest ABSENCE that `resolve_scoring` classifies CAPTURED.

⛔ **No fourth scorer.** `league_scoring.score_row` already takes `stat_field=` and
`resolve_scoring` already takes `fields=`. Handing them the realized map is the entire change; the
coverage report in §6 is the existing machinery's output.

### The parity proof — and it caught a real mis-mapping

The realized line is a **better** parity anchor than MT1's: nflverse publishes its own
`fantasy_points_ppr`, computed with no knowledge of our scorer. Scoring a full-PPR config through
`score_row` over `REALIZED_STAT_FIELD` must reproduce a number we did not compute, which checks the
map **field by field** rather than only checking arithmetic.

First run, over all **1,118 real 2026 week-1 rows**: 1,116 agreed to 1e-9; **exactly two disagreed
by exactly 2.0** — Jimmy Horn Jr. and Chimere Dike, both return men, both with
`fumbles_lost_total = 1` and all three per-phase fumble columns at 0. `fumbles_lost_total` counts
**punt and kickoff return fumbles**; nflverse's PPR does not. Over 2025 REG the gap is 36 rows
(249 vs 213).

The module's own docstring had argued the opposite from the armchair ("the total is the column that
means what the scorer's key means"). The measurement refuted it, and two independent authorities
agree on the narrow reading: the projected twin is `proj_fumbles_lost = touches × 0.006` — an
**offensive-touch** heuristic that cannot mean a return fumble — and nflverse's own PPR uses the
same three columns. Pairing a return-inclusive realized number against a touch-based projection
would measure two different quantities, which is what boundary (i) exists to prevent.

**After the fix: max |ours − nflverse| = 3.55e-15 over 1,118 rows, 0 rows beyond 1e-9.**

### The three wrong-key traps this table sets

1. ⭐ **`passing_40` / `rushing_40` / `receiving_40` are 40+ yard PLAY counts, not 40+ yard
   TOUCHDOWN counts** — and they are the nearest-looking columns to the scorer's `pass_td_40p` /
   `rush_td_40p` / `rec_td_40p`. Measured on 2025 REG: `passing_40` **exceeds** `passing_tds` on 36
   player-weeks and `receiving_40` exceeds `receiving_tds` on 108, which is impossible for a subset
   of the touchdown count. The authoritative derivation (`run_nf_c0e_captured_terms`) reads `pbp`
   (`pass_touchdown = 1 AND yards_gained >= 40`). Mapped ABSENT, deliberately.
2. `fg_blocked` / `pat_blocked` / `pt_blocked` are the **kicking** side's blocked kicks, not the
   defence's `def_blocked_kick`. Mapped ABSENT.
3. The `dst_*` family is **team**-grained; this table is player-grained. Mapped ABSENT.

*(A fourth trap surfaced while probing and is worth recording: `snap_counts` uses `game_type`, not
`season_type`. DESCRIBE-first turned that into an immediate BinderException rather than a false
"the feed is empty".)*

---

## 6. The coverage report (MT1 shape, MT1 machinery)

Against a **maximal** league — every one of the 54 terms the editor catalog offers, at its modal
default, so the question is "what can the realized line score of everything a user can ask for"
rather than "what does one preset happen to set":

| verdict | n | |
|---|---|---|
| **APPLIED** | 24 | pass_att/cmp/yds/td/int · rush_att/yds/td · targets/rec/rec_yds/rec_td · fumbles_lost · two_pt · fg_made_40_49 · fg_missed · pat_made · def_sacks/int/fumble_rec/td/safety/forced_fumble · st_td |
| **DERIVED (exact)** | 5 | the five fine FG buckets folding onto `fg_made_0_39` / `fg_made_50_plus` |
| **CAPTURED** | 25 | 21 `dst_*` · `def_blocked_kick` · the three `*_td_40p` |
| | | *(plus `pat_missed`, `fumble_rec_td`, `st_player_td` — the scorer has no key for these on EITHER side)* |

**`hasApproximation: False`**, and that is a genuine improvement over the projected lens rather than
a coincidence: realized FG data is **finer** than the scorer's coarse buckets, so the fold is a
TOTAL and is exact. On the projection side the same fold runs the other way (six league buckets onto
three projected ones, by attempt share) and can be inexact.

⭐ **Kickers are fully scoreable from this line** (every FG/PAT column is present per player) — a
material improvement on the projected lens, which covers QB/RB/WR/TE only. **Team D/ST is the one
real gap**: 21 of the 25 captured terms are `dst_*`, and closing it needs a **team-level** read
(points allowed from `schedules`, yards allowed from `stats_team_week` — itself in the same
un-ingested tier). That is a scoping decision for Phase A, not a defect.

---

## 7. What node 1 hands the rest of the story

- **`app/backend/services/realized_stat_fields.py`** — the map, the derived unsupported-key set,
  the two-cause absence reasons, the flattener, and the lake column list the read must SELECT
  (derived, so adding a term widens the query automatically).
- **The parity method**, with a stronger anchor than MT1's: compare against the source's OWN
  `fantasy_points_ppr`, which our scorer had no hand in.
- **The completeness gate**: `distinct game_id == the schedule's game count`, never a clock.
- **Two blockers for the operator** (§2 and §3 of the handoff).

## 8. Findings for `closeout.followUps`

1. 🚨 **The realized-outcome lake tier has no in-season writer.** `stats_player_week`,
   `stats_team_week`, `snap_counts` (and the rest of the realized stack) are excluded from
   `ROLL_FORWARD_SOURCES` on a rationale that was true only pre-season; NF-FRESH2 P0 widened the
   window without revisiting the set. Blocks RC1 outright.
2. ⚠️ **The live weekly projection is building 2026 features from 2025 outcomes, and its own
   manifest says so.** The published week-2 manifest carries
   `input_vintage.stats_as_of = "2025-W18"` / `snaps_as_of = "2025-W18"` beside
   `rosters_as_of = "2026-W2"`. The stamp is honest and correct; **nothing reads it back and
   escalates** (the NF-INJ1 "a stamp nothing reads back is not a freshness guarantee" shape). The
   NF-C6-PH2 freshness monitor judges the artifact's WEEK and AGE, neither of which can see a
   current-week artifact built from a 9-month-old feature vintage. **This is a live serving finding
   independent of RC1** and should be triaged on its own.
3. ⚠️ **`schedules` refreshes Monday 06:15 PT, before Monday Night Football** — so one game per week
   carries no result for up to 7 days. Affects any surface reading game results from `schedules`.
4. **`pat_missed` / `fumble_rec_td` / `st_player_td` are scoreable from the realized line but have
   no `STAT_FIELD` key** (they failed NF-C0e's held-out gate as *projections*; as *realized* facts
   they are simply present). Adding them is a three-mirror `STAT_FIELD` change with a paid-set
   consequence — a deliberate decision, not a tidy-up.
5. **Team D/ST realized scoring needs a team-level read** (`schedules` for points allowed,
   `stats_team_week` for yards allowed). 21 of 25 captured terms.

---

# D2 — the team D/ST construction: STOPPED AND REPORTED, not shipped

**Status: the PM's stop condition fired.** The ruling said *"If the team-level path turns out not to
be cheap-ish after all, stop and report rather than absorbing the growth silently."* It did, and this
is the report. The module (`app/backend/services/realized_dst.py`) is committed because its proven
parts are load-bearing for whatever comes next, but **it is not wired into a served surface.**

## What the cross-check turned out to be

Better than the ruling assumed. The ruling anticipated *"where none [an independently-computed
figure] exists, prove the construction two-sided."* One DOES exist: **Sleeper scores every started
defence under that league's own settings**, so `starters_points` for the DEF seat is an external
authority computed by someone else. That converts D2 from a two-sided sanity argument into a
measured reproduction rate — which is why the residual below was found at all.

## What is PROVEN, and worth keeping regardless

1. ⭐⭐ **"Points allowed" is NOT the opponent's final score.** A D/ST is charged only with what the
   opposing OFFENSE scored; a pick-six against your quarterback is not your defence's fault.
   Measured decisively: MIN 2025 wk1 — CHI scored 24, of which a **defensive touchdown**
   was 7, so MIN's defence allowed **17, not 24**, moving it from the 21-27 tier (worth 0) to the
   14-20 tier (worth 1). Naive = 5.0; corrected = **6.0 = Sleeper's figure exactly**. PHI in the
   same week reproduces at **4.0** either way, so the correction is what discriminates.
   ⚠️ The 7 is an ASSUMPTION (6 plus an assumed made extra point) and is carried on the wire as
   `pointsAllowedAssumption`, never hidden; exact derivation needs `pbp`, which is not ingested.
2. **`sack_yards_lost` is stored NEGATIVE** (CHI wk1: −12), so net yards = `passing + rushing +
   sack_yards_lost`. The natural-looking subtraction moves the total the WRONG WAY (it inflated
   CHI's 317 to 341). The first cut of the probe did exactly that.
3. **The bucket ranges parse from the scorer's own key names** (`dst_pa_g_14_17` → 14..17,
   `dst_pa_g_46p` → 46..∞), per the ruling's "derived from the scorer's key set, never hand-typed",
   and an unparseable tier RAISES rather than scoring nothing silently.
4. **The lake says `LA` for the Rams; Sleeper says `LAR`** — the NF-W3 franchise-code family.
   Un-normalised, LAR was dropped entirely (0.00 vs 11.00). Normalised through the scorer's own
   team vocabulary it reproduces exactly.
5. **A scorer-key vs field-name wrong-key bug, caught by the cross-check.** `dst_row` first keyed
   team counters by SCORER key (`def_fumble_rec`) while `score_row` reads them by the map's FIELD
   name (`fumble_recovery_opp`), so every team defensive counter silently scored ZERO — **9 of 12
   defences low**. Fixed by translating inside the module and giving the merged map ONE owner
   (`dst_stat_field`), because the bug entered at a call site assembling two dicts by hand.

## What is NOT resolved — the reason this stops

Against Sleeper's own figure, over the probed league's four weeks (12 started defences each):

| week | disagreeing / 12 |
|---|---|
| 1 | 1 |
| 2 | 3 |
| 3 | 6 |
| 4 | 3 |

**13 of 48 team-weeks (~27%) do not reproduce.** That is systematic, not a stat-correction artifact
— which is what the four-week run was for; a one-off would have been consistent with the platform
restating a played week, and this is not.

One further mechanism was identified and fixed, with only marginal effect: **nflverse keeps
`fumble_recovery_tds` SEPARATE from `def_tds`** (BAL wk2 carries a 63-yard opponent fumble-recovery
touchdown with `def_tds = 0`), so a fumble-return touchdown was missed entirely. Folding it in moved
week 3 from 7 to 6 and changed nothing else. ⚠️ And it introduces its own ambiguity that is itself a
finding: `fumble_recovery_tds` does **not** split own-fumble from opponent-fumble recoveries, and
only the opponent kind is a D/ST score.

At least one mechanism remains unidentified. The cleanest instance is **SEA 2025 wk1: ours 6.00,
Sleeper 8.00**, where the realized line is fully accounted for (PA 17 → 14-20 tier = 1; 1 sack = 1;
2 interceptions = 4; 384 net yards → the 350-399 tier, which is absent from the league's settings
and therefore 0) and the league's **complete, unfiltered 56-key** scoring settings contain no term
that could supply the missing 2 points.

## What this means for RC1

The player side is unaffected and solid (3.55e-15 against nflverse's own PPR). The honest options
for D/ST are a PM call, not a worker call:

- **render D/ST as a stated absence** for now (the MT1 discipline) and card the construction, or
- **fund the residual** as its own scoped piece of work — the cross-check harness now exists, so the
  question is a bounded "explain 13 team-weeks", not an open-ended one, but it is plainly not the
  "cheap-ish" the ruling scoped.

⛔ What must NOT happen is shipping it at ~73% agreement. A D/ST number that is right three times in
four is exactly the plausible-but-wrong failure the D1 ruling refused on the recap side, and a
starting-slot score that quietly disagrees with the league's own is the same defect wearing a
different hat.
