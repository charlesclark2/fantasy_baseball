# NF-CAP1 — why the NFL point-in-time captures were (and were not) running

**2026-09-05. Measured, not inferred.** Every number below came from the live artifacts, the live
nflverse release and the live Odds API on the date of writing.

---

## The headline: the premise was wrong on both legs, in opposite directions

The story was written against a reading of `nfl/pit/injuries` — 12,136 rows, one capture date,
zero 2026 rows — as "this capture has fired once in its life". That reading is what two prior
sessions arrived at, and it is wrong. The measurement was right; the inference from it was not.

| leg | believed | **measured** |
|---|---|---|
| injuries | fired once ever, never since | **firing on cron, correctly capturing nothing** |
| market (game lines) | schedule STOPPED, never enabled | **RUNNING and firing; 272 events on 09-01 and 09-04** |
| market (props) | enabled 08-05, maybe not firing | **never captured; `market_tier` is `game_lines` on all 816 rows** |

The one real defect is the last row, and it is not the one the story expected.

---

## Leg A — injuries: running, healthy, nothing lost

**The schedule is not stopped.** `sports_nfl_pit_metadata_schedule` ships
`default_status=RUNNING`, so it self-starts; it is not in the STOPPED class at all.

**The 2026-08-05 capture was a manual run, and could not have been anything else.** Its cron is
month-gated `9-12,1-2` (Sep–Feb). August is outside that gate, so no scheduled fire can exist in
August. Its two writes are stamped `07:10:53Z` and (an hour earlier checkpoint) — neither is a
cron instant. It is the NF-W0a runtime-gate verification run, on the day the code landed on main.
The 12,136 rows are `2 × 6,068` — the same 6,068-row release captured at two checkpoint hours.

**Zero 2026 rows is the healthy state, and the artifact cannot say otherwise.** Measured today:

```
GET .../releases/download/injuries/injuries_2026.parquet  ->  HTTP 404
GET .../releases/download/injuries/injuries_2025.parquet  ->  HTTP 200, 97,497 bytes
```

DuckDB's error text is `HTTP Error: HTTP GET error on '…' (HTTP 404 Not Found)`;
`looks_like_missing_asset()` returns **True** against it, and `data_expected_from(2026)` — week
2's first kickoff, ~2026-09-17 — is still in the future. So the leg takes its `expected_absent`
branch: it records the absence, writes nothing, and does not page. **By design.** nflverse
publishes a season's injuries file only once injury reports exist, and week 1's practice reports
begin the week of the 09-09 opener.

⭐ **So the artifact is structurally incapable of distinguishing "fired and correctly captured
nothing" from "never fired"** — which is exactly the trap the story warned about, arriving from
the other side. "Absence of a page is not health" has a twin: **absence of rows is not evidence of
non-execution.**

**The discriminator, and it needed no Dagit read.** `nfl_pit_metadata_capture_op` runs
`for leg in ("injuries", "schema")` — one op, two legs, sequentially. So a schema capture at a
cron instant proves the injuries leg executed at that instant too:

```
nfl/pit/schema_snapshot   capture_timestamp 2026-09-01T16:00:34Z   (Tue 09:00:34 PDT)
nfl/pit/schema_snapshot   capture_timestamp 2026-09-04T16:00:41Z   (Fri 09:00:41 PDT)
```

The cron is `0 9 * 9-12,1-2 2,5`. Both fires landed, on time, to the second. **Check the sibling,
never the silence.**

> ⚠️ `aws s3 ls` prints LastModified in SHELL-LOCAL time (E11.20). The listings read `11:00`
> because this shell is CDT. Every timestamp above is read from INSIDE the parquet.

**Permanently lost for leg A: ZERO weeks.** There has been nothing to capture.
First capturable fire: **Fri 2026-09-11**, or Tue 09-15, depending on when nflverse publishes.

---

## Leg B — market: game lines fine, props never captured

**The schedule is running.** Measured from content:

```
nfl/pit/market   capture_date=2026-08-05   272 events   07:11:22Z   (the manual verification run)
nfl/pit/market   capture_date=2026-09-01   272 events   16:15:19Z   (Tue 09:15:19 PDT — the cron)
nfl/pit/market   capture_date=2026-09-04   272 events   16:15:19Z   (Fri 09:15:19 PDT — the cron)
```

Cron `15 9 * 9-12,1-2 2,5`. Both in-season fires landed. **`BOX_OPERATIONS.md §10` said
"STOPPED → TURN ON BEFORE THE OPENER" and was stale** — the operator had already enabled it. That
row is corrected in this change; do not re-derive intended state from the table without checking
the artifact.

**Props never captured, on any date:**

```
select distinct market_tier from nfl/pit/market   ->   ['game_lines']      (816 rows)
```

**Why it was silent, which is the part worth keeping.** Three mechanisms stacked:

1. `props_enabled()` collapsed **unset** and **"0"** into `False`, so "the operator decided
   against props" and "the flag never reached the container" were the same value.
2. The leg escalates only when it captures *nothing at all* — and the game-line tier fills that
   check on its own. 272 game-line rows land, the healthy branch is taken, the op returns success.
3. The artifact carries **no record of the props decision**. `capture_props` lives only in a
   Dagster manifest log line.

⇒ a props-disabled run is byte-identical to a props-enabled one in every signal anyone watches.

**Leading cause: the flag is not set in the container that executes the job.** It is absent from
`env.required` and from every `.env.example` — the bite `env.required` already documents
verbatim: *"an absent key makes 'flip it to 1' a silent no-op."* And an env change does not reach
an already-running container; it needs a recreate (FU-1). Two alternatives are not excluded from
here and need the box's Dagster event log to separate:

- **(b)** the flag IS set and `_odds_nfl_props` raised — also silent (caught, appended to
  `manifest["errors"]`, no escalation because game lines filled `rows`);
- **(c)** the flag IS set and every per-event fetch failed individually.

A live props pull on this repo's key succeeded during this session, which makes a
key/entitlement cause unlikely but does not settle which container the box uses.

**Permanently lost for leg B: 2 point-in-time props boards — 2026-09-01 and 2026-09-04.**
Game lines: nothing lost. Nothing is recoverable: the live `/odds` endpoint has no history, and
the `/historical` endpoint retains closing lines only.

⏰ **The next fire is Tue 2026-09-08 16:15 UTC — the LAST capture before the 09-09 opener.**

---

## Credits: the 10× error is real, and correcting only half of it makes things worse

Measured live against `x-requests-remaining`, bracketed by free `/sports` reads. The brackets are
**certified rather than assumed** — three `/sports` reads returned a delta of exactly 0.

| call | repo said | **measured** |
|---|---|---|
| `/sports` | — | **0** (free) |
| `/events` list | — | **0** (free) |
| game lines `/odds` (3 markets × 1 region) | ~30 | **3 credits** |
| props `/events/{id}/odds` (12 markets × 1 region) | ~120/event | **10 credits/event** |

**Mechanism:** the Odds API's 10× multiplier applies to the **`/historical`** endpoint. Both PIT
legs use the **LIVE** endpoint. Props are billed per market **actually returned** — 10 of the 12
requested are priced (`player_reception_tds` and `player_rush_tds` are not offered), measured
identically on two independent events; ceiling 12.

⭐ **The unit price is only half the arithmetic, and this is the trap.** `_odds_nfl_props` fans
out over the **whole** `/events` board — `odds_max_events` is `None` on this path — which measured
**272 events**. So:

| | old §10 | **corrected** |
|---|---|---|
| game lines / snapshot | ~30 | **3** |
| game lines / season (2×/wk × 22wk) | ~1,300 | **~132** |
| props / snapshot | ~1,700 ("per slate") | **~2,720** (272 events × 10) |
| props / season | ~75,000 | **~60,000** |

The old props figures were roughly right **by accident** — two compensating errors (per-event
price 12× too high, event count ~19× too low). **Correcting the unit price alone while keeping a
"~14-event slate" would understate the props budget by ~10×.** Balance at time of writing:
**4,927,687**; a props season is ~1.2% of it.

**New spend incurred by this diagnosis: 23 credits** (3 game lines + 10 + 10 props, on two
events). Flagged per the story's boundary. No other paid call was made.

---

## What shipped

**Made the silent states loud (minimal, RED-proven):**

- `props_state()` is three-valued — `on` / `off` / **`undeclared`**. A deliberate `"0"` stays
  silent (props are a real spend decision; a monitor that pages on a legitimate choice gets
  muted); an **undeclared** flag pages, because `env.required` now demands the key be present, so
  undeclared is not a state anyone chose.
- The props tier gets **its own** zero-check, because the game-line tier satisfies the shared one.
- `NFL_PIT_CAPTURE_PROPS` joins `env.required` + both `.env.example` files. The box's live `.env`
  is the fourth owner and is the operator's step.
- **Injuries:** a published-but-**empty** asset previously took neither the 404 branch nor the
  captured-rows branch and returned a clean manifest — the NF-W2c silent-zero shape, live in the
  current window. It now uses the *same* `data_expected_from` bar as the 404 path: quiet before,
  loud after. One rule, two absence shapes.

**The never-again detector (INC-41 machinery, extended — not a new monitor species):**

- `FreshnessContract` gains `active_weekdays` / `active_months`. Hours alone cannot express a
  weekly or seasonal writer, and a Tue/Fri Sep–Feb capture needs both.
- The lag scan is **day-bucketed**. The old flat cap returned `days × 24 × 60` regardless of which
  minutes were active — correct for hour-only contracts, and it would have **false-paged a
  seasonal contract**: frozen 08-05, read 09-20 returned 64,800 minutes when the true active lag
  is zero. Now exact to 400 days.
- Two contracts: `nfl_pit_market`, `nfl_pit_injuries`, read from the PIT Delta store through the
  handle delta-rs already authenticated (never a `delta_scan` URI — INC-45).
- **SLA derived, not chosen.** Under Tue/Fri × Sep–Feb one cadence interval is *exactly* 24.00
  active hours in both directions and DST-invariant (there is no hour filter to shift); one missed
  fire is exactly 48.00. **36h** sits halfway.
- `nfl_pit_injuries` is armed **Oct–Feb**, not Sep: through September the artifact *cannot*
  advance, so a Sep-armed SLA would page daily on a leg working as designed (INC-45's "do not SLA
  a deliberately-static artifact", applied to a *window*). September is covered by the leg's own
  bar and by the heartbeat.

**Heartbeat:** the two FREE, self-starting captures join `CRITICAL_SCHEDULES`.

⛔ **The PAID market schedule deliberately does NOT**, and this is a correctness finding rather
than scoping. `stopped_critical_instigators` flags an instigator only when Dagster holds a
**persisted STOPPED row**. That schedule ships `default_status=STOPPED` and is RUNNING only
because the operator toggled it on — so the exact revert an entry would claim to cover (a volume
reset wiping the toggle) returns it to its STOPPED **default** with *no row at all*, which the
function correctly does not flag. **The entry would have read as coverage while detecting
nothing.** Its coverage is the `nfl_pit_market` freshness contract instead, which asserts the
artifact and goes STALE ~36 active hours after a missed fire regardless of any surface signal.

*(A pre-existing guard, `test_critical_instigators_self_start`, caught this. It was right; the
design was wrong.)*

---

## Open decision for the PM

**Should `sports_nfl_pit_market_schedule` flip to `default_status=RUNNING`?**

Today its ON state lives only in the Dagster Postgres, so a volume reset or box re-host silently
reverts it and the season's market boards stop. The freshness contract detects that within ~36
active hours, but does not *prevent* it — only `default_status=RUNNING` self-heals.

The cost of flipping: a **paid** capture auto-starts on every fresh deployment (~3 credits per
snapshot for game lines, and ~2,720 if props are on). That is a spend decision, not a monitoring
change, so it is left to the PM rather than taken here.

**Also worth a decision:** the props leg captures **all 272 events every fire**, so a week-17 game
four months out is re-captured ~40 times. A commence-time horizon would cut the props season from
~60,000 credits to a small fraction of it. Left alone (it is inside the already-authorised
envelope, and narrowing it is a scope change, not a defect fix).
