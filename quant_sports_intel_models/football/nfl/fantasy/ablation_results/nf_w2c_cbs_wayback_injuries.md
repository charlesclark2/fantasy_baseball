# NF-W2c-CBS — parsing the CBS injury captures, raising the 2025 per-week PIT coverage floor

Generated 2026-08-09. Extends NF-W2c (`nf_w2c_wayback_injuries.md`) — nfl.com + espn.com were
parsed and landed there (1,166 admissible rows, 17/18 REG weeks); CBS was enumerated + fetched
but its parser deferred (carded). This story writes that parser and lands the additional rows,
**additively** — the nfl/espn rows in the store are untouched.

## What CBS's report looks like (source assessment addendum)

cbssports.com/nfl/injuries is a per-team `TableBase` report: player / position / last-report
date / injury / status cells. Unlike nfl.com's single page-level declared week, **CBS embeds
its own declared week PER ROW** inside the status text (e.g. `"Questionable for Week 14 vs.
L.A. Rams"`, `"Did Not Practice on Friday. Doubtful for Week 14 at Arizona"`) — a single page
mixes the current week's report with a preview of next week's. Roster/reserve tags (IR, NFI-R,
Physically Unable to Perform, Suspended, Retired) and playoff/training-camp preview rows
(`"for Divisional Playoffs"`, `"for start of Training Camp"`) share the same status cell but
never match the `Out|Doubtful|Questionable ... for Week N` vocabulary — excluded **by
construction**, not by an explicit denylist (mirrors ESPN's IR exclusion in NF-W2c).

Stamp encoding is unchanged from NF-W2c: `capture_timestamp`/`feature_timestamp`/
`ingestion_timestamp` = the Wayback capture instant; `source_timestamp` = a declared absence
(CBS publishes no per-row vendor as-of). Admissibility = capture strictly before the player's
own gameday 00:00 UTC, gamedays from the W2b matrix, per-row `declared_week` used exactly like
nfl.com's page-level week (a `(player_id, declared_week)` join to the gameday matrix).

## Crawl + parse + crosswalk + PIT gate (CBS only)

72/72 CDX-listed CBS captures cached (0 unreplayable — better than NF-W2c's 178/179). 62 of the
72 produced ≥1 parsed row (10 produced zero — bare `"—"` / preseason / playoff-only pages whose
status cells never match the weekly vocabulary, same shape as nfl.com's own week-12/18 gaps).

| stage | count |
|---|---|
| snapshots enumerated | 72 |
| snapshots parsed (≥1 row) | 62 |
| rows parsed (raw CBS designation rows, all positions) | 9,268 |
| rows crosswalked to a gsis id | 2,842 |
| **rows admissible (player, week, source)** | **1,021** |
| PIT gate: records checked / dropped | 1,021 / **0** |
| weeks with ≥1 admissible row | **18 / 18** |

Crosswalk quality, restricted to the four modeled positions (QB/RB/WR/TE — the ones
`stats_player_week` can resolve at all; CB/LB/OT/DE/SAF/DT/G/C/OLB/OG rows are non-skill and
were never going to match `attach_gsis`'s skill-position crosswalk, which is why the raw
9,268→2,842 rate looks low): **2,842/2,929 = 97.0%** matched — 87 unmatched rows across 40
distinct names, mostly deep-roster/practice-squad players (`Deuce Vaughn`, `Zonovan Knight`,
`Carlos Washington Jr.`, …), logged (not dropped silently) by the runner's new per-source
unmatched-name warning. Matches NF-W2c's documented 97–100% skill-position crosswalk baseline.

## Landed (2026-08-09, additive — dedup on `capture_id` proves it)

`land()` on the 1,021-row CBS artifact: **1,021 written, 0 duplicate, 0 recapture, 0 revision**.
Read back from `s3://credence-sports-lakehouse/nfl/pit/wayback_injuries`:

| source | rows | first capture | last capture |
|---|---|---|---|
| nfl | 629 | 2025-09-11 | 2025-12-27 |
| espn | 537 | 2025-09-01 | 2025-11-26 |
| **cbs** | **1,021** | 2025-08-03 | 2026-01-03 |
| **total** | **2,187** | | |

629 + 537 = 1,166 reproduces NF-W2c's landed count exactly — confirms the CBS land touched
nothing already there.

## The per-week PIT coverage-floor lift (modeled positions QB/RB/WR/TE, distinct players/week)

| week | before CBS | after CBS | lift |
|---|---|---|---|
| 1 | 69 | 119 | +50 |
| 2 | 68 | 70 | +2 |
| 3 | 86 | 86 | +0 |
| 4 | 67 | 102 | +35 |
| 5 | 22 | 63 | +41 |
| 6 | 84 | 89 | +5 |
| 7 | 29 | 77 | +48 |
| 8 | 56 | 65 | +9 |
| 9 | 16 | 72 | +56 |
| 10 | 34 | 70 | +36 |
| 11 | 92 | 94 | +2 |
| 12 (Thanksgiving) | 2 | 2 | +0 |
| 13 | 42 | 59 | +17 |
| 14 | 69 | 77 | +8 |
| 15 | 98 | 105 | +7 |
| 16 | 100 | 103 | +3 |
| 17 | 63 | 87 | +24 |
| **18** | **0** | **66** | **+66** |
| **total** | **997** | **1,406** | **+409 (+41%)** |

**Week CBS uniquely covers: week 18** — the only week with ZERO modeled-position admissible
rows before CBS (nfl.com had no pre-gameday week-18 capture; ESPN was dark in December). CBS
alone contributes 66 modeled-position players there, closing NF-W2c's one genuine coverage gap
(`"week 18 has no pre-gameday capture"`). Week 12 (Thanksgiving) stays thin at 2 either way —
CBS's own week-12 rows fully overlap the 2 players nfl/espn already covered, adding no net-new
player (a short week with few games and even CBS's report caught little of it).

The other big lifts (weeks 5/7/9/10, +36 to +56 each) land on ESPN's known December-and-
mid-season-gap weeks and nfl.com's sparse early-season weeks — CBS is dense where the other two
sources are thin, which is exactly the complementary-source shape NF-W2c's source assessment
predicted for CBS ("data-bearing … 65 [now 72] captures").

## What this feeds

**17/18 → 18/18 REG weeks now have at least one admissible source, and the modeled-position
per-week floor rises from a minimum of 2 (week 12) to a genuine per-week distribution with no
zero week.** This is the input NF-W2d needs for its fold-power registration — the coverage floor
was the binding constraint on how many usable weekly folds the 2025 injury-availability
re-gating could register; it is materially wider now (409 more modeled-position player-weeks,
concentrated in previously-thin weeks 5/7/9/10/18).

## Guards

`betting_ml/tests/test_nf_w2c_wayback_injuries.py::TestCbsParser` (9 tests) + one
`stamped_rows_from_capture` cbs test, on 7 rows cut verbatim from a real 2025-12-06 capture
(NF-C0e — not invented fixtures): the bare weekly designation, both practice-prefix forms
(`Did Not Practice`/`Full Practice`), an `Out … Expected Return` row (proves the regex keeps
the REPORT week, not the return week), and the three excluded forms (IR, NFI-R, a bare `—`).
RED-proven: loosening the status regex to also match IR/NFI-R turned 10 of 11 CBS tests red
(verified, then reverted) — the exclusion tests are not vacuous.

## Landmines inherited (both already cured by NF-W2c, both re-confirmed live here)

- **Archived bytes are bytes**: all 72 CBS bodies fetched as raw bytes, gzip-magic-checked,
  gunzipped before decode via the existing `snapshot_text`. 0 mangled-gzip refusals hit.
- **CDX-listed ≠ replayable**: crawl completed 72/72 with 0 unreplayable snapshots this time —
  no skip-not-abort case exercised live, but the guard (`SnapshotUnavailable` → count, don't
  abort) is unchanged and still covers it.
