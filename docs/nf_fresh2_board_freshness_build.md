# NF-FRESH2 — Phase-2 draft-board freshness build

**Shipped:** 2026-08-15 · branch `nf-fresh2` (operator-created worktree) · `best_alpha = 0` ·
projection product, no edge/win-rate/market-beating claim anywhere.

Phase 1 (`docs/nf_fresh1_draft_board_freshness_audit.md`) measured the defect. This is the fix for
P0/P1/P2/P4. **Where the audit and the corrected session recap disagree, the recap wins** — box
diagnostics overturned the audit's §6.2/P3, and P3 is therefore *not* in this story.

---

## 0. What was wrong, in one paragraph

The served NFL draft board was a static, hand-published S3 blob. Its market inputs (FFC ADP,
FantasyPros ECR) were read from on-disk caches **that no code path could refresh** — both fetchers
default `refresh=False` and every caller omitted the argument — so a full rebuild-and-republish
re-read a three-week-old snapshot and shipped it. That market does not merely decorate the board: it
feeds the served **ranking** (market-led at QB/RB/WR, market-blend at TE), so a "value vs ADP"
reading could invert its own advice. Meanwhile the UI rendered one `built <date>` over inputs of
three different vintages, and both NFL ingest schedules were month-scoped `3-8`, meaning every raw
feed would have frozen on 09-01 — through the opener and the whole season.

Nothing about that produced an error, a log line, or an artifact distinguishable from a healthy one.
That is why every claim below is RED-proven.

---

## 1. P0 — the September-1 seasonal cliff (the hard deadline)

`NFL_ROLL_FORWARD_CRON` and `NFL_SLEEPER_INJURIES_CRON` widened `3-8` → `3-12,1-2` (March through
the following February — one full season cycle).

**The in-season safety audit, run before flipping** (the story required it):

| Question | Finding |
|---|---|
| Does anything assume these raw feeds are quiet in-season? | **No.** The only "the pull stops for the season" prose belongs to the **NCAAF** schedule, whose game-day `sports_ncaaf_dbt_schedule` genuinely takes over. The NFL game-day schedule rebuilds **marts** and ingests **nothing**, so widening the NFL window replaces no other writer. |
| Can an in-season overwrite damage point-in-time fidelity? | **No.** The raw tier is a latest-snapshot tier by construction (`replaceWhere season=YYYY`), which is exactly *why* NF-W0a's PIT capture writes to its own store with its own `capture_timestamp`. |
| Does it create a concurrent dbt writer? | **No.** The three NFL crons stay disjoint: roll-forward 06:15 Mon, Sleeper 06:30 daily, game-day mart rebuild 11:00 daily. |
| Does it fix the Sleeper break? | **No, and the docstring says so.** `sports_nfl_sleeper_injuries_job` dies at `duckdb.connect()` in ~114ms and its bare `except` returns SUCCESS. A wider cron produces *more* green-and-empty runs. Tracked separately. |

`services/dagster/aws/BOX_OPERATIONS.md §10` is corrected on both NFL rows: it recorded the
roll-forward as STOPPED (it is RUNNING) and Sleeper as healthy (it is running and producing
nothing). **Verify a claimed schedule state against the box run list, never against that table.**

## 2. P1 — unfreezing the market

`--market-refresh` / `--no-market-refresh` on `run_nf1_5.py`, `run_season_projection.py` and
`export_draft_board_json.py`, **default ON**, threaded to both `fetch_ffc_adp` and `fetch_fp_ecr`.
Default ON because *the failure mode of OFF is invisible* — a stale market is indistinguishable from
a fresh one in every log and artifact — while the failure mode of ON is loud.

### 2.1 The correctness boundary is structural, not a convention

Every refresh decision reduces through `market_freshness.should_refresh_market(season, flag)`, which
**refuses any season that is not the clock-derived `current_season()`**, whatever the caller passed.
So threading the flag through a whole 2017→2026 training pool refreshes the current season only.

This is the E5.9 backfill boundary: refreshing 2019–2024 would regrade the published track record
against an ADP that did not exist when the projection was made. Putting the season test *inside* the
helper means no future call site can forget it. `export_track_record_json.py`'s `_CLAIM_DENYLIST`
assert is untouched.

⚠️ **It governs RE-fetching, not cold-starting.** With no cache on disk a historical season still
goes to the network — the only way a first-ever backtest can obtain its market — and that is not a
hindsight pull: FFC serves a past season's *archived* preseason window. Verified live 2026-08-15:
2021 returns `2021-08-31 → 2021-09-01`, 1,709 drafts, and a 2021 build with the flag ON left that
pinned snapshot byte-identical.

### 2.2 A failed refresh falls back to the cache, loudly

`refresh=True` is now on the path of a serving artifact, so a transient FFC/FantasyPros outage that
propagated would degrade the season to market-**blind** — i.e. a 30-second blip would silently
reorder the served board. Both `_ffc_payload` and `_fp_payload` keep the last good snapshot and WARN
instead. The fallback **announces itself** rather than hiding: the `adp_as_of` stamp is read from the
same cache file, so a bound fallback ships and renders the *old* date.

### 2.3 Live proof (2026-08-15, one HTTP GET each, into a scratch cache)

| | before (the real stale caches) | after `--market-refresh` |
|---|---|---|
| ADP | `2026-07-18 → 07-25`, 3,091 drafts | **`2026-08-07 → 08-14`, 6,334 drafts** |
| ECR | `7/26`, 89 experts | **`8/15`, 91 experts** |

The "before" column reproduces the audit's independently-measured figures exactly.

## 3. Per-input vintage — the honesty fix

`adp_as_of` / `ecr_as_of` ship flat on `projections.json` **and** `manifest.json`, with a nested
`freshness` block carrying the ADP draft window + count, every ADP sample the export pulled, and the
lake-input vintages. `ProvenanceLine` renders a second line: *"Market and role inputs as of: ADP 8/14
· expert ranks 8/15 · depth charts 8/10"*.

Three things worth keeping:

- **The lake vintage is recorded BY the build that consumed it** (`run_nf1_5.read_input_vintage` →
  the projection summary → the exporter), never re-derived at export time. Re-deriving would report
  what the lake holds *now* — a different and flattering question. NF-FRESH1 §1.1 measured the gap:
  a board generated 7h42m *before* that day's ingest landed.
- **Absent ≠ null.** An absent key (an older payload, or an older backend under NF-C0 deploy skew)
  renders nothing; a null value renders **"unknown"**. Inventing "unknown" during a deploy window
  would be noise; dropping a null would let a missing stamp read as covered by the build date
  (NF1.7(a)).
- **The stamps survive the entitlement allowlists.** `lock_projections_payload` /
  `lock_manifest_payload` build their output from allowlists, so a served field absent from them is
  stripped with no error (the E9.41 dropped-field class, allowlist form). Provenance is not paid
  content, and withholding it would leave the honesty defect in place for the non-entitled half of
  the audience. **Any future provenance field must join those three allowlists in the same change.**

## 4. P2/P4 — the publish cadence

`pipeline/jobs/sports_nfl_board_publish_job.py` + `sports_nfl_board_publish_schedule`.

```
nfl_board_input_refresh_op   (P4)  depth_charts + rosters + weekly_rosters → nfl.staging → nfl.marts
          │  ← a GRAPH EDGE, not a cron offset
          ▼
nfl_board_publish_op         (P2)  nf1_5 build (--market-refresh) → league boards → export --publish
                                   → VERIFY the artifact that shipped
```

- **Ordering (INC-25).** Step 2 consumes exactly what step 1 lands, in the same run. Two schedules
  with an offset would reproduce the measured 2026-08-10 race on the first slow ingest; an edge
  cannot.
- **Cadence.** One cron, 07:15 PT, **no month range** (the P0 lesson applied to the new schedule),
  which decides its own cadence: daily Aug 1 – Sep 15, weekly (Mondays) otherwise. One owner, not
  two — a daily cron beside a weekly one would overlap in exactly the window that matters (the
  INC-30 / INC-36 / INC-38 shape).
- **Tier.** It can never blank the product: a failure fails its own standalone run and leaves the
  previous board serving. But the publish op **pages and raises** rather than reporting a green run
  that published nothing — the explicit inverse of the Sleeper op's 19 consecutive green runs.
- **Verification.** Three exit-0 subprocesses prove each script ran, not that a board advanced. The
  op re-reads the manifest and asserts (a) `generated_at` is not older than this run, and (b)
  `adp_as_of` is present. An **unreadable** manifest is a failure, never a pass.
- **Precondition.** The build chain reads the box's sports DuckDB, which is gitignored and therefore
  absent from the image. The op checks for it first and pages with a named remedy.

## 5. Honest framing — what this does NOT claim

- **Projections move on real information only.** No jitter, decay or recency tilt was added. If only
  the ADP window changed between two builds, the projection moves by exactly the amount the market
  moved it. Nothing in the model changed here; only how recent its inputs are.
- **A fresher build is not a better model.** `MARKET_LEAN_NOTE` ships verbatim and is guard-tested.
  Refreshing ADP makes the *market half* of the ordering current — it does not make our order more
  independent of the market.
- **No track-record claim rides on any of this.** Historical seasons keep their pinned snapshot;
  the `_CLAIM_DENYLIST` assert is untouched. An in-season "how are we doing" would need a
  point-in-time capture of what was *served* on each date (the NF-W0a discipline), never a
  re-derivation from today's inputs.
- Every new user-visible string was screened against the shared denylist: clean.

## 6. Falsifiability

`uv run python betting_ml/tests/nf_fresh2_red_proof.py` — 12 deliberate breaks, **all 12 caught**
(the pre-NF-FRESH2 cache-always-wins ordering; refreshing every season; losing the market on an
outage; dropping a stamp from the allowlist; both `3-8` crons; un-chaining the two ops; swallowing
the DuckDB precondition; dropping the explicit `--market-refresh`; and each verification clause on
its own, so neither is vacuous). The harness asserts its own mutation landed before running pytest.

⚠️ Like the repo's nine other Python red proofs it is **not scheduled**, and E9.64 measured what that
costs. Wiring the Python red proofs into a scheduled workflow is worth doing and is deliberately not
smuggled into this story.

## 7. Known limits, stated

- **Not runtime-gated.** CI mocks IO, so nothing here has run on the box. The publish job's real
  first failure will most likely be the missing sports DuckDB — by design it pages rather than going
  green.
- **The worktree cannot validate the artifact-precedence path.** The ADP/ECR caches and the board
  artifacts are gitignored and live in the main checkout. The as-of stamps were therefore smoked
  against the **real** cache files copied in, not a synthetic fixture — but a full
  build → export → publish was not run from here.
- **Depth-chart daily ingest is only as useful as the publish it feeds**, which is why P4 lives
  inside P2's job rather than as its own schedule.
- **P3 and P5/P6 are out of scope.** P3 was overturned by the box recap (the Sleeper schedule runs;
  its op is broken). P5 (injury information beyond the roster designation) belongs to NF-I0. P6
  recommends building no transactions feed.
