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
append-only) and `nfl/pit_raw/<leg>/capture_date=…/<capture_id>.json` (write-once raw payloads).

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
