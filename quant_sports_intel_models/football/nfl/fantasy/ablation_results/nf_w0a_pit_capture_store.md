# NF-W0a — NFL point-in-time immutable capture store + fail-closed leakage guards

**Date:** 2026-08-05 · **Branch:** `nf-w0a-pit-capture` · **`best_alpha` N/A** (data-infra; no model,
no serving change, no app surface) · **Cost:** $0 new (Open-Meteo free/no-key; nflverse free;
market on the existing Odds-API sub at ~30 credits/snapshot).

---

## Verdict

**Both gate halves delivered.** (1) All four forward-capture legs are LIVE-VERIFIED end to end and
wired to Dagster schedules; the two free legs ship `RUNNING` so they cannot be silently forgotten.
(2) The immutable store + the fail-closed §13 leakage guard are built around them, with every
rejection case deliberately constructed and **RED-proven by deleting the clause from the source**.

⚠️ **One operator action is load-bearing and dated:** the PAID market schedule ships `STOPPED` and
**must be enabled before 2026-09-09** or no Tuesday/Friday market feature is ever backtestable.

---

## ⭐ Two point-in-time defects found here (neither is in NF-W0)

Both silently corrupt a naive weather capture; both were found by probing the live nflverse
release rather than by reading the schema.

### 1. `roof` is a POST-HOC field at retractable venues — the `temp`/`wind` class, one column over

NF-W0 established that `schedules.temp`/`wind` are realized game-book weather, not forecasts. The
same is true of `roof`, and it was not flagged.

Measured on the live release:

| finding | value |
|---|---|
| blank-`roof` rows in the **entire** release | **43 — all of them season 2026 (unplayed)** |
| which venues | exactly the 5 retractable ones (ARI/DAL/HOU/ATL/IND) + 2 neutral sites |
| what those venues carry historically | `closed` 227 · `open` 32 · **`dome` 0** |

`closed`/`open` is a value that exists only *after* the game-day roof decision. So:

- **For an unplayed game the roof state is genuinely unknown at projection time.** Capture must
  fail-open — the roof might be open, and skipping blanks would permanently lose every
  ARI/DAL/HOU/ATL/IND home game's weather. `roof_known=false` is stored so consumers gate honestly.
- **The historical `closed`/`open` value is not PIT-safe.** Using it in a Tuesday build is a leak,
  and gating training on it while gating serving on a blank produces train/serve skew.
- ⛔ Gating on the team's `is_dome_home` (as a naive port of MLB's park logic would) is wrong twice
  over: that column is documented INFORMATIONAL, and a team can play outdoors at a neutral site.

### 2. The home team's stadium is the WRONG PLACE for a neutral-site game

2026 schedules **eight** international games, all listed under the home *team*:

| game | nflverse home_team | actually played at |
|---|---|---|
| `2026_01_SF_LA` | LA | **Melbourne** Cricket Ground |
| `2026_03_BAL_DAL` | DAL | **Maracanã**, Rio |
| `2026_04_IND_WAS` | WAS | Tottenham, **London** |
| `2026_06_HOU_JAX` | JAX | Wembley, **London** |
| `2026_07_PIT_NO` | NO | Stade de France, **Paris** |
| `2026_09_CIN_ATL` | ATL | Bernabéu, **Madrid** |
| `2026_10_NE_DET` | DET | Allianz, **Munich** |
| `2026_11_MIN_SF` | SF | Estadio Banorte, **Mexico City** |

Fetching at the home team's coordinates returns entirely plausible numbers for the wrong
hemisphere, with no error anywhere. `stadium_id` does not rescue it — Melbourne carries `LAX01`,
the *team's* code. ⇒ neutral sites resolve by stadium **name**, and an unrecognised neutral venue
is **REFUSED** (loud) rather than fetched at the home stadium: capturing the wrong city is
strictly worse than capturing nothing. All 8 are mapped, pinned by a test so a vendor rename fails
offline in CI rather than silently on a capture morning.

**Verified:** all 272 games of 2026 resolve — 8 neutral, 52 fixed-dome skipped, 0 refused.

---

## A third defect, found in this story's OWN first cut

**A vendor-revision detector whose false-positive rate is 100 % is worse than none.** Open-Meteo
stamps `generationtime_ms` (server timing) on every response, so two byte-identical forecasts
hashed differently and **every benign re-fire was classified as a vendor revision** — the
over-paging monitor that gets muted, and then the one real revision goes unread.

Two-part cure, both parts necessary:

1. **Declared volatile-key exclusion** from the content hash, with the excluded set STORED on the
   row (`hash_excluded_keys`) — a hash that silently ignores fields is its own silent-death risk.
2. **Per-source revision semantics**, declared rather than inferred:
   - `REVISION_SEMANTICS` (injuries, schemas) — the vendor should publish a *stable* record, so a
     changed payload **is** the §13 revised-record case: keep the original, **alert**.
   - `LIVE_VALUE_SEMANTICS` (weather, market) — the feed *moves by design*, so a re-read inside one
     checkpoint is expected: keep the first, **do not alert**.

   In both cases the original stands and nothing is overwritten; `semantics` changes only how the
   difference is *reported*.

---

## The four capture legs (all live-verified 2026-08-05)

| leg | cadence | verified live | cost |
|---|---|---|---|
| **weather** | hourly ladder `[120,72,48,24,3,1]`h | 3 real Open-Meteo forecasts stored (Lambeau / AT&T-blank-roof / **Wembley 60.5 °F** — London, not Jacksonville) | free |
| **market** | Tue/Fri live board | **272 events, 10 books each**, all phase `open` | ~30 cr/snapshot |
| **injuries** | Tue/Fri | **6,068 rows** stamped with our own `capture_timestamp` | free |
| **schema** | Tue/Fri, per ingest | **30 assets** described | free |

**The ladder adaptation is load-bearing.** MLB's `ingest_weather.py` tops out at T-24h because a
baseball build is same-day. An NFL Tuesday build for a Sunday game stands ~120h out, so an
MLB-verbatim ladder would have given the Tue/Fri builds **no weather at all** — precisely the
feature the capture exists to make backtestable. Pinned by a test (`max(ladder) >= 120`), along
with the window arithmetic: no two rungs can match one moment, and an hourly cron cannot miss one.

**⭐ The schema leg independently reproduces both of NF-W0's 2025 breaks, from the release file:**

```
depth_charts  watched_missing = ['week', 'depth_team', 'position']   ← the schema REPLACEMENT
injuries      watched_missing = ['date_modified']                     ← the DELETED as-of stamp
schedules     watched_missing = []                                    ← healthy
```

Our own lake structurally *cannot* see this: the ingest writes `schema_mode='merge'`, so a dropped
column is backfilled with NULLs and still reads as present. The vendor's release file has no such
amnesia. The leg also probes null RATES for the small high-value assets, because "present but
100 % NULL" is the second silent-death signature a pure schema check would miss.

**⚠️ …AND REPRODUCING THEM EVERY RUN IS EXACTLY WHY THE FIRST CUT WOULD HAVE PAGED FOREVER.**
Both breaks are **permanent, already-triaged states**, not events — so `escalate` was `True` on
every fire, and the box run's tail said so plainly: `ALERT — legs needing attention: ['schema']`.
Once `sports_nfl_pit_metadata_job` starts firing that is an ERROR page every Tuesday and Friday,
≈44 identical unactionable pages a season. Note `drifts` was `[]` in both box runs: **nothing had
changed** — the escalation conflated "a known bad state" with "a new event".

The harm is not the noise. It is that a muted `NFL PIT capture:` subject line also swallows the
weather leg's CRITICAL *"this slate's forecast is being lost permanently"* — the one page in this
story that is genuinely unrecoverable. It is also the judgement E11.30 already made for
`check_injury_status_health_op`, which deliberately stays log-only on the known off-season ingest
hole rather than paging daily for four months.

**Fix:** `ACCEPTED_MISSING` — a baseline of named `(asset, column)` pairs. Missing-ness is still
reported in full every run (`watched_missing`); only the paging decision reads
`watched_missing_new`. Four properties make the mute safe rather than a blindfold:

| property | why |
|---|---|
| mutes **named pairs**, never an asset | a *third* watched injuries column still pages the day it disappears |
| a **watched DRIFT** of an accepted column still escalates | muting "is missing" must not mute "it just changed" — the disappearance is an event |
| a restored column is reported (`accepted_missing_resolved`) | a stale mute is how the *next* deletion of that column goes unnoticed |
| every pair is validated against `WATCHED_COLUMNS` by a guard | a typo'd entry is **inert** — it mutes nothing while reading as coverage |

RED-proven both ways: emptying `ACCEPTED_MISSING` makes the live box condition page again, and
reverting the escalation to the un-baselined `watched_missing` turns the baseline test red.

**The market board is already fully priced 35 days pre-opener** (272 events × 10 books) — so
enabling the market schedule early also captures pre-season line movement, at no extra cost.

---

## The box runtime gate — PASSED, and it found a cost defect

Run on the box 2026-08-05: `Found credentials from IAM Role: credence-dagster-ec2-role` (the
instance-role path the AKID landmine kills), schema 30 assets with both 2025 breaks detected,
injuries **6,068 rows written, 0 revisions, `vendor_asof_present: false`**.

⚠️ **It also took 14 minutes**, and that was a real defect the laptop could not have surfaced —
the local-filesystem smoke wrote 6,068 files in under a second, so the per-row write only became
visible against real S3 latency (~130ms/row over ~12,000 sequential calls). At the Tue/Fri cadence
that is **~267,000 objects and ~10 hours of box time per season** for a job whose useful output is
2.7 MB.

**FIXED — raw payloads are now retained one object per BATCH** (`retain_raw_batch`), payloads keyed
by `capture_id` inside, with each row storing its `raw_payload_key`:

| | before | after |
|---|---|---|
| S3 calls per injury capture | ~12,136 | **2** |
| objects per season | ~267,000 | **44** |
| wall clock (6,068 rows) | 14 min | **~2 s** (1.6s measured locally) |
| box time per season | ~10 h | seconds |

The §13 guarantee is unchanged, and that is the point: immutability is a property of the OBJECT (a
batch object is still written once and never replaced), and dedup keys off `capture_id` in the
Delta table, independent of how the bytes are grouped. Per-row objects only ever bought
single-record lookup, which no consumer performs.

⭐ **The batch key is CONTENT-ADDRESSED** (sha over its sorted `capture_id`s) rather than keyed on
`capture_date`. A date-only key would have made a second same-day batch collide with the first, and
the write-once refusal would then have **silently dropped its payloads** — the immutability
guarantee inverted into data loss. Pinned by
`test_a_DIFFERENT_batch_the_same_day_does_not_collide`.

**Also fixed (found while investigating the memory profile): DuckDB was unclamped.** All six
connections in `pit/` used a bare `duckdb.connect()`, which inherits ~80% of physical RAM — ~12.8 GB
on the 16 GB box. That is INC-22 #4 verbatim: DuckDB believes it never needs to spill, blows past
physical memory, and the kernel OOM-kills the *host*, taking Dagster with it. So the failure mode of
an NFL research capture was an MLB serving outage. All connections now route through `pit/duck.py`
(60% of RAM, floored 2 GB / capped 11 GB, `threads=2`, mirroring
`run_w1_lakehouse._safe_memory_limit_gb`), with a guard forbidding a direct `duckdb.connect()`
anywhere in the package.

Both fixes RED-proven: reintroducing per-row writes fails 2 tests; reintroducing a bare
`duckdb.connect()` fails the clamp guard.

## The store: append-only, and why that is the whole design

`ingest/s3io.write_season_partition` writes `mode="overwrite"` with `replaceWhere season = N`.
Correct for a *reproducible* feed; fatal here. A PIT capture is a **measurement of a moment** —
overwriting Tuesday's forecast with Friday's destroys the only copy of what was knowable on
Tuesday, and no archive returns it. `pit/store.py` is append-only, partitioned by `capture_date`,
with write-once raw payloads (`nfl/pit_raw/…`, HEAD-before-PUT). A source-inspection guard forbids
an `overwrite` literal — and strips comments first, so prose about not overwriting cannot satisfy
it (INC-38). **RED-proven:** reintroducing `mode="overwrite"` turns it red.

Dedup without overwriting: `capture_id` is deterministic over
`(capture_source, subject_key, checkpoint)`, so a re-fired cron produces the same id and is dropped
before the write.

---

## The leakage guard, and its non-vacuity proof

Every §13 rejection is an independent clause: the five `*_timestamp > projection_timestamp`
comparisons (all five — `ingestion` and `vendor_release` are as disqualifying as the three §13
spells out), missing provenance, a revised record standing in for the original, a late market
joining an earlier projection, a rolling window reaching the target, and **anything unevaluable**
(fail-closed).

**14 leakage cases are deliberately constructed and required to be rejected.** Beyond that,
`TestTheGuardIsNotVacuous` disables the owning clause and requires each case to become CLEAN — the
NF-D17 lesson made mechanical. A fixture that trips two clauses proves neither.

**That test earned its keep immediately.** `check_market_phase` originally compared projection vs
**capture**, which fires only when the capture is already late by the stamps — i.e. exactly when
the timestamp clause fires anyway. The clause was dead weight and the test caught it. The fix
compares projection vs **kickoff**: a board that is closing-tier for a Sunday game cannot have
existed at a Tuesday projection *whatever its capture stamp claims*, so the clause now catches
mislabelled and mis-stamped boards — while still permitting the Sunday-morning re-projection to
consume a near-closing board (a designed build of the weekly system; a blanket ban would break the
product rather than protect it).

**Source-deletion RED proof** — deleting each clause from `leakage_guard.py`:

| clause deleted | tests turning red |
|---|---|
| `check_provenance_present` | 5 |
| `check_timestamps_not_after_projection` | 11 |
| `check_original_capture` | 4 |
| `check_market_phase` | 5 |
| `check_rolling_window` | 6 |

Integration half: a real capture → the real store → the real index → the real guard. A later
projection accepts all rows; an earlier one rejects them with the right reasons. Verified on the
272 genuinely-captured market rows too.

---

## What is NOT done (honest scope)

- **No dbt staging over `nfl/pit/*`.** Nothing reads the store yet — correct (NF-W1 is the first
  consumer) but it means these tables are unexercised by any downstream contract.
- **The guard is a library, not yet wired into a build.** NF-W1 must call `assert_point_in_time`
  at its feature-assembly boundary. Shipping a guard that nothing invokes is the "wired ≠ invoked"
  defect (NF-C0e), so it is stated rather than implied.
- **No backfill mode**, because there is nothing to backfill. A missed checkpoint shows up as an
  absent `capture_id` for that rung, permanently.
- **Player props are OFF by default** (`NFL_PIT_CAPTURE_PROPS`): ~120 credits/event ≈ 1,700 per
  slate snapshot ≈ **75,000/season** at this cadence. A deliberate budget decision, not a default.
- **The box run is the real runtime gate.** Everything above was verified on the laptop against
  live sources; CI mocks all IO, so only a box run proves the schedules fire there.
