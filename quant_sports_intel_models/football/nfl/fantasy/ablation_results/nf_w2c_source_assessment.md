# NF-W2c — sourcing PIT-clean 2025 injury data: the source assessment

**2026-08-09 · branch `nf-w2c` · deploy-held · `best_alpha = 0`.** The hard bar (NF-W0/W0a
§13): a 2025 row is consumable ONLY with a provable pre-gameday as-of stamp that passes
`assert_point_in_time`. "We found the designations" is the FAILURE mode — the lake already
holds all 6,068 stampless 2025 rows; what this story sources is **defensible as-of instants**.

## Lead verdicts (cheapest-first, as registered)

| lead | verdict | evidence |
|---|---|---|
| (c) Sleeper | ❌ DEAD | our own captures start 2026-07-26 (one snapshot); the API is current-state only — no 2025 history exists anywhere in it |
| (a) nflverse release history | ❌ DEAD | the `injuries_2025.*` release assets were wholesale re-created 2026-03-18 (post-season); GitHub retains no prior asset versions; the release-download URL has **zero** Wayback captures |
| (b) Wayback captures | ✅ **CLEARS THE BAR** | see below — data-bearing snapshots with third-party capture instants, verified two-sided against the §13 guard |
| (d) paid providers | not evaluated | (b) cleared first, per the registered stop rule |

## Lead (b): what was found, and the two traps that nearly killed it falsely

Wayback capture density over Sep 2025 – Feb 2026 (status-200, CDX):

| page | captures | distinct days | notes |
|---|---|---|---|
| nfl.com/injuries (+ deep league pages) | 35 | 32 | the OFFICIAL weekly report: per-player practice participation + game status; the page title declares its week; covers **December** |
| espn.com/nfl/injuries | 79 | 46 | embedded `__espnfitt__` JSON: designations + each player's next game date; dense Sep–Nov, **empty in December** (the two sources complement) |
| cbssports.com/nfl/injuries | 65 | 58 | data-bearing; **parser deferred (carded)** — the crawl retains its raw bytes either way |
| fantasypros / covers / draftsharks / PFR | 0–43 | — | covers.com has 43 captures (unassessed); the rest negligible |

**Trap 1 (a false "dataless shell" verdict, self-inflicted):** archived bodies are stored
gzip'd; fetching them and decoding as text with `errors="ignore"` strips the `\x8b` magic byte
and yields 40–60KB of mojibake that "parses" to zero designations with no error. All three
sources initially read as JS shells. Refetched as BYTES + gunzipped: **NFL.com 566KB with 215
practice entries (Week 15), ESPN 866KB with 256 designations, CBS 1.1MB with 164.**
`snapshot_text` now refuses mangled bytes loudly (guard-tested), and the lesson is recorded in
memory — a lossy decode is a graceful fallback that hides the defect.

**Trap 2 (SPA pages whose data rides in XHRs):** checked and NOT the case here — but the
underlying API endpoints (site.api.espn.com, api.nfl.com) have zero Wayback captures, so the
HTML pages are the only stamped carrier.

## Parser proof (real snapshots, in-session smoke)

- `parse_nfl_report` on the 2025-12-12 09:34 UTC capture: **week=15, 341 players** — practice
  line 86 DNP / 129 limited / 126 full; designations 3 Out / 2 Doubtful / 6 Questionable (a
  Friday-morning capture predates most final designations — Fri-PM/Sat captures carry more).
- `parse_espn` on the 2025-10-10 16:45 UTC capture: **256 designation rows** (61 Out / 4
  Doubtful / 191 Questionable), each with a game-date hint resolving to the player's own
  gameday (182×Oct-12, 28×Oct-13, …) — per-player admissibility, not per-page.
- ESPN roster designations (IR etc.) are SKIPPED — they are not the weekly-report channel.

## The stamp encoding (verified two-sided against `assert_point_in_time`)

`capture_timestamp`/`feature_timestamp`/`ingestion_timestamp` = the Wayback capture instant;
`source_timestamp` = **declared absence** (the page publishes no per-row vendor as-of — the
archive's instant must never be laundered into a vendor claim). The guard PASSES a pre-gameday
capture and REJECTS a post-gameday one (`CAPTURE_TIMESTAMP_AFTER_PROJECTION`). Admissibility =
capture strictly before the player's own gameday 00:00 UTC — the NF-W2 bound verbatim.

## What this can and cannot recover (design expectation, to be MEASURED by the crawl)

- Weeks with a Fri/Sat capture (final designations): roughly 9–11 of 18 REG weeks across the
  two parsed sources. Early-week captures add practice-line rows for a few more weeks.
- The reconstruction is PARTIAL BY DESIGN: uncovered player-weeks stay NaN/unobserved — the
  family is NULL-bearing and the observed flag will be per-covered-instant, never per-season.
  ⛔ No fillna(0): absence of a capture is absence of evidence.
- The build cross-checks reconstructed designations against the lake's stampless values per
  (player, week) — the agreement rate is the quality proof the measurement reports.

## Status + what remains

Code: `wayback_injury_source.py` (CDX/fetch/parsers/stamping) + `run_nf_w2c_wayback_injuries.py`
(`--enumerate` / `--crawl` / `--build` / `--land`); 18 guards in
`betting_ml/tests/test_nf_w2c_wayback_injuries.py` (real trimmed fixtures; the mangled-gzip
refusal is RED-provable by construction).

⏭️ OPERATOR: run the crawl + build (LAPTOP, ~15 min — ~180 polite archive fetches + the W2b
matrix reload); the build writes `nf_w2c_wayback_injuries.{md,json}` with the per-week coverage
+ agreement measurement. `--land` (appends to the immutable NF-W0a store, source
`wayback_injuries`) is a separate deliberate step after reviewing the measurement. Re-gating
the 2025 folds (making them gated-evaluable in a future bake-off) is a successor registration
once the landed coverage is known — NOT this story's scope.

## Measurement review (2026-08-09, post-crawl — the reading that clears `--land`)

Crawl: 178/179 snapshots cached (1 CDX-listed capture 404s on replay — skipped, its coverage
simply absent). Build: 24,634 capture-stamped rows parsed from 111 snapshots → 6,657
crosswalked to a gsis id → **1,166 admissible (player, week, source) rows, 0 PIT drops,
17 of 18 REG weeks with stamped rows** (week 18 has no pre-gameday capture; week 12 —
Thanksgiving — has 2 rows). Full per-week table: `nf_w2c_wayback_injuries.md`.

The pooled per-week agreement column is BIMODAL (1.00 in weeks 7/15/16/17 vs 0.25–0.44
elsewhere) — the discriminating cut is **source × capture-to-gameday distance**, not week:

| cut | agreement | n |
|---|---|---|
| nfl (all — captures land 1–2 days pre-gameday) | **1.000** | 119 |
| espn, 1 day pre-gameday | 0.800 | 45 |
| espn, 2 days | 0.443 | 88 |
| espn, 4+ days | ~0.31–0.48 | 122 |

- **The parser + crosswalk are proven correct by the NFL source's 119/119** (and ESPN's
  day-1 0.80): identical vocabulary both sides (`out/doubtful/questionable`), no mapping
  mismatch.
- **ESPN's low pooled agreement is capture TIMING, not a defect**: the dominant "disagreement"
  is `questionable → out` (104 of 136 — the canonical mid-week downgrade), and agreement
  decays monotonically with capture distance. An early-week capture SHOULD disagree with the
  lake's FINAL designation — that early-week reading is precisely the point-in-time
  information this story exists to recover, so the disagreement is signal, not noise.
- Consequence for the successor registration: an ESPN-stamped row is an as-of-that-instant
  observation, NOT a proxy for the final Friday designation. Any 2025 re-gating must consume
  it as such (the observed-flag-per-covered-instant design already does).

**Verdict: the measurement supports `--land`.** The agreement table above is the quality
proof the design section asked for.
