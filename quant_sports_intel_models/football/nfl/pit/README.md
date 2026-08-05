# NFL point-in-time capture store + fail-closed leakage guards (NF-W0a)

The data backbone the weekly component system (NF-W1…W8) sits on. Two halves:

1. **Forward capture** (time-critical) — weather / market / injuries / nflverse schemas, written
   raw and immutably with the doc §13 timestamp keys.
2. **The store + guard** — an append-only immutable Delta store and a fail-closed enforcement of
   every §13 rejection case, RED-proven.

Everything here is DuckDB/S3-native and **Snowflake-free**.

## ⏰ Why the capture cannot wait, and cannot be backfilled

The 2026 season opens **2026-09-09**. Three of the four legs capture something that *does not
exist in any archive*:

| leg | what an archive gives you instead | consequence |
|---|---|---|
| **weather** | Open-Meteo's archive returns **observations**, not the forecast that stood on a historical Tuesday | training on outcomes while serving on forecasts — a hard leak one way, a distribution shift the other |
| **market** | the Odds API history holds **closing** lines (that is what `odds_nfl_historical` captures, by design, for CLV) | no Tue/Fri-build market feature can *ever* be backtested |
| **injuries** | nflverse **deleted `injuries.date_modified`** in 2025 | there is no vendor as-of stamp left; the only one is the one we make |

Every week not captured is permanently absent from the training frame.

## Layout

```
pit/
  timestamps.py       the §13 key contract (ISO-UTC VARCHAR, fail-closed on naive stamps)
  store.py            APPEND-ONLY immutable Delta + write-once raw payloads
  venues.py           stadium geo, neutral-site resolution, roof policy
  schedule.py         the nflverse schedule spine (ET→UTC kickoffs)
  weather_capture.py  Open-Meteo forecast ladder [120,72,48,24,3,1]h
  market_capture.py   Tue/Fri live odds board (PAID; props opt-in)
  injury_capture.py   injury reports stamped with OUR capture_timestamp
  schema_snapshot.py  per-ingest nflverse schema snapshot + drift detection
  leakage_guard.py    the fail-closed §13 rejection set
  run_capture.py      the single CLI / callable driving every leg
```

Storage: `s3://credence-sports-lakehouse/nfl/pit/<leg>/capture_date=YYYY-MM-DD/` (Delta,
append-only) and `nfl/pit_raw/<leg>/capture_date=…/batch_<id>.json` (write-once raw payloads,
**one object per capture batch**, keyed by `capture_id` inside; each row stores its
`raw_payload_key`).

⚠️ **Raw retention is BATCHED, and that was a measured fix.** The first cut wrote one object per
capture row with a HEAD before each PUT: a 6,068-row injury capture took **14 minutes** on the box
(~12,000 sequential S3 calls), which at the Tue/Fri cadence is ~267,000 objects and ~10 hours of
box time per season. Batching makes it 1 PUT + 1 HEAD — **267,000 objects → 44**, 14 min → ~2s.
The §13 guarantee is unchanged: immutability is a property of the *object* (a batch object is
still never replaced), and dedup keys off `capture_id` in the Delta table, independent of the raw
layout. The batch key is content-addressed (sha over its sorted `capture_id`s) so an identical
re-fire is idempotent while a *different* same-day batch cannot collide — a `capture_date`-only
key would have had the write-once refusal silently drop the second batch's payloads.

**DuckDB is clamped to the box.** Every connection goes through `pit/duck.py` (60% of RAM, floored
2 GB / capped 11 GB, `threads=2`). A bare `duckdb.connect()` inherits ~80% of RAM — ~12.8 GB on the
16 GB box — which is INC-22 #4 verbatim: DuckDB never spills, blows past physical memory, and the
kernel OOM-kills the *host*, taking Dagster with it. A guard forbids a direct `duckdb.connect()`
anywhere in `pit/`.

## ⭐ The one structural divergence from `ingest/s3io.py`

`s3io.write_season_partition` writes `mode="overwrite"` with `replaceWhere season = N`. That is
exactly right for a reproducible feed and exactly wrong here: a PIT capture is a **measurement of
a moment**, not a reproducible pull. Overwriting Tuesday's forecast with Friday's destroys the
only copy of what was knowable on Tuesday. So `store.py` is append-only and never issues an
overwrite — pinned by a source-inspection guard that strips comments first, so prose about not
overwriting cannot satisfy it.

Deduplication without overwriting: `capture_id` is deterministic over
`(capture_source, subject_key, checkpoint)`, so a re-fired cron produces the same id and is
dropped before the write.

**Two meanings of "same id, different payload"**, declared per source rather than inferred:

- `REVISION_SEMANTICS` (injuries, schemas) — the vendor is expected to publish a *stable* record,
  so a changed payload **is** the §13 revised-vendor-record case: keep the original, **alert**.
- `LIVE_VALUE_SEMANTICS` (weather, market) — the feed *moves by design*, so a re-read inside one
  checkpoint is expected: keep the first, **do not alert**.

Measured 2026-08-05: without that split, every benign weather re-fire alerted as a vendor
revision (Open-Meteo stamps a server-timing field on each response) — a 100 %-false-positive
channel, i.e. the monitor that gets muted. The volatile field is excluded from the content hash,
and the excluded set is stored on each row (`hash_excluded_keys`) so the exclusion is auditable.

## Paging discipline: the schema leg's accepted baseline

The schema leg reproduces both of NF-W0's 2025 breaks on **every** run — `injuries.date_modified`
is deleted and `depth_charts` was schema-replaced, permanently. Escalating on those meant an ERROR
page every Tue/Fri forever (≈44 a season) about two conditions nobody can act on, which is the
monitor-gets-muted failure mode — and a muted `NFL PIT capture:` subject would also swallow the
weather leg's CRITICAL *"this slate's forecast is being lost permanently"*.

So `schema_snapshot.ACCEPTED_MISSING` names the already-triaged `(asset, column)` pairs. The full
state is still reported every run (`watched_missing`); only the paging decision reads
`watched_missing_new`. The mute is deliberately narrow: it covers **named pairs, not assets**
(a third watched column still pages), a watched **drift** of an accepted column still escalates
(muting "is missing" must not mute "it just changed"), a **restored** column is reported so the
stale mute gets dropped, and every pair is validated against `WATCHED_COLUMNS` by a guard so a
typo cannot silently widen it.

⇒ **when a break is triaged and accepted, add the pair here in the same change.** Leaving it
paging is not conservatism; it spends the alert channel the irreversible legs depend on.

### …and the same split one level up, for the ASSET

⏰ `current_season()` is right about which season we are **in** and wrong as a proxy for which
season nflverse has **files** for. It rolls over in March; nflverse publishes season-scoped assets
as data appears. Measured 2026-08-05: `depth_charts_2026.parquet` existed (created 08-04, training
camp) while `injuries_2026`, `play_by_play_2026`, `snap_counts_2026` and ten others **did not
exist at all**. So for roughly six months a year a season URL 404s *by design* — and unhandled,
that pages ERROR on every Tue/Fri fire through the pre-season, including both fires before the
opener, plus a hard failure of the injuries leg.

`classify_unreadable` splits them, and the discriminator is the **snapshot store, not a calendar
guess**: an asset we described successfully before and cannot describe now is a REGRESSION and
escalates immediately; one we have never seen for this season is simply not published yet. That
quiet branch is bounded by `schedule.data_expected_from` (week 2's first kickoff, since week 1's
data lands days earlier) so it can never become a permanent blindfold — past the bar, a
still-absent asset escalates. Only an unambiguous 404 qualifies; any other read failure keeps its
escalation, because a network blip must never be laundered into "not published yet".

Two related honesty rules the same finding forced:

- an **UNREADABLE** asset reports `watched_missing = []`. It has no columns, so a naive
  computation announces every watched column as deleted — they are **unknown**, not missing.
  That is NF1.7 (a) inverted, and it double-reports one condition as two.
- an unresolvable bar (`expected_from is None`) never licenses silence.

## ⭐ Two point-in-time defects found by this story

Both are in `venues.py`, both silently corrupt a naive capture, and neither was in NF-W0.

**1. `roof` is a post-hoc field at retractable venues — the `temp`/`wind` class, one column over.**
All 43 blank-`roof` rows in the entire nflverse release are unplayed 2026 games, and they are
precisely the five retractable venues (ARI/DAL/HOU/ATL/IND) plus two neutral sites. Those venues
*never* carry `dome`; historically they carry `closed` (227) or `open` (32) — values that exist
only after the game-day roof decision. So a blank roof means **unknown at projection time**, and:

- capture must **fail-open** (the roof might be open; skipping loses those games' weather
  permanently), while `roof_known=false` is stored so consumers can gate honestly;
- the historical `closed`/`open` value is **not PIT-safe** — using it in a Tuesday build is a
  leak, and gating training on it while gating serving on a blank produces train/serve skew.

**2. The home team's stadium is the wrong place for a neutral-site game.** 2026 schedules eight
international games. `2026_11_MIN_SF` is home_team `SF` but played at Estadio Banorte in **Mexico
City**; `2026_01_SF_LA` is home_team `LA` at the **Melbourne Cricket Ground**. Fetching at the
home team's coordinates returns entirely plausible numbers for the wrong hemisphere, with no
error anywhere. nflverse's `stadium_id` does not help (Melbourne carries `LAX01`). So neutral
sites resolve by stadium **name**, and an unrecognised neutral venue is **refused** — capturing
the wrong city is strictly worse than capturing nothing.

## The leakage guard

`assert_point_in_time(records, projection_timestamp, store_index=…)` raises `LeakageRejection`
on any of: each of the five `*_timestamp > projection_timestamp` comparisons · missing
provenance · a revised vendor record standing in for the original · a closing line/late prop
joining an earlier projection · a rolling window containing the target or a future game · and
**anything unevaluable** (fail-closed — NF1.7 (a): a check that did not run is not a pass).

Each clause is an independent function so each can be RED-proven in isolation.
`test_nfl_pit_leakage_guard.py` constructs every case deliberately and additionally **disables
the owning clause and requires the case to become clean** — the NF-D17 non-vacuity proof, run
mechanically. Verified: deleting any clause from the source turns 4–11 tests red.

Note on `check_market_phase`: it compares **projection vs kickoff**, not projection vs capture.
A first cut compared against the capture stamp, which made it a restatement of the timestamp
clause — the non-vacuity test caught that.

## Run

```bash
# hourly ladder (the leg with the deadline)
uv run python -m quant_sports_intel_models.football.nfl.pit.run_capture --leg weather

# the Tuesday weekly-build snapshot
uv run python -m quant_sports_intel_models.football.nfl.pit.run_capture \
    --leg weather --observation-type forecast_pregame

# a Tue/Fri market board (~30 credits; props opt-in via NFL_PIT_CAPTURE_PROPS=1)
uv run python -m quant_sports_intel_models.football.nfl.pit.run_capture --leg market

# everything, offline, no bucket / no creds / no paid calls
uv run python -m quant_sports_intel_models.football.nfl.pit.run_capture \
    --leg all --dry-run --local-root /tmp/nfl_pit
```

## Orchestration

| job | schedule | status | cost |
|---|---|---|---|
| `sports_nfl_pit_weather_job` | hourly, Sep–Feb | **RUNNING** | free |
| `sports_nfl_pit_metadata_job` | Tue/Fri 09:00 PT, Sep–Feb | **RUNNING** | free |
| `sports_nfl_pit_market_job` | Tue/Fri 09:15 PT, Sep–Feb | ⛔ **STOPPED** | paid |

The free legs ship `RUNNING` deliberately: their misses are permanent, and a schedule that boots
STOPPED silently never runs (E11.23) — that would be discovered in January, with the season's
Tuesday-build weather already unrecoverable. The market leg spends Odds-API credits, so it is an
explicit operator decision — **but it must be enabled before 2026-09-09.**

Costs: game lines ≈ 30 credits/snapshot (≈1,300/season). Player props are the per-event endpoint
at ≈120 credits/event ≈ 1,700 per slate snapshot ≈ **75,000/season** — hence off by default.

## Not yet done (honest scope)

- The store has **no dbt staging layer** — nothing reads `nfl/pit/*` yet. That is correct for
  now (NF-W1 is the first consumer) but means these tables are unexercised by any downstream
  contract.
- `run_capture` has **no in-season backfill mode**, because there is nothing to backfill: a
  missed checkpoint is gone. A gap shows up as absent `capture_id`s for that rung.
- The guard is a **library**, not yet wired into a build — NF-W1 must call
  `assert_point_in_time` at its feature-assembly boundary. Shipping the guard unused would be the
  "wired ≠ invoked" defect, so this is called out rather than implied.
