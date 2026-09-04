# MLB-INC-0904 — the W3pre tick outgrew its budget, and a fan-out leaf that never ran

**Date:** 2026-09-04 · **Severity:** two CRITICAL pages · **Slate impact:** none measured
**Alerts:** (A) `run_w1_lakehouse --w3pre-only` killed at the 480 s leg cap mid-`stg_statsapi_games`;
(B) `stg_ref_players` STALE at 1817 active-min vs an 1800-min SLA.

---

## 1. Verdict up front

Two **separate** causes that share one pressure (September = season-max data on a 2-vCPU box), and
one premise in the alert that the measurements corrected.

| | Alert A | Alert B |
|---|---|---|
| Cause | the W3pre tier's **cost** grew past its 480 s leg cap; the serving-critical table was built **last** | the daily fan-out leaf that writes the dimension **did not run** on 09-03 |
| Class | slow monotonic growth crossing a fixed cap | a leaf that pages when it *fails* but is silent when it never *executes* |
| Shared? | **No** — different jobs, different caps, different failure modes. Same underlying data growth. | |
| Status | **fixed in this PR** (ordering + a threshold) | **restored**; proximate cause needs the Dagster event log |

⚠️ **Two premises in the alert were wrong, and both mattered:**

1. **"post_lineup predictions silently stop."** They did not, and could not. INC-41 split the two
   intraday rebuilds into independent `try` blocks; `--w7b-only` — which owns
   `stg_statsapi_lineups_wide` and `stg_statsapi_probable_pitchers` — ran normally. Measured at
   04:19Z: both **OK at 30 min lag**. The "post_lineup stops" shape is the *pre*-INC-41 behaviour;
   that repair held. `--w3pre-only` owns game state and odds staging only.
2. **Alert A had already self-healed** by the time it was worked. `stg_statsapi_games` read **OK,
   30 min** — a later tick's leg completed. The timeout is **intermittent**, not a hard failure,
   which is the whole diagnosis: the tier sits *just* under its cap and tips over on busy ticks.

Alert B, conversely, was **worse than paged**: 1817 → **2347 active-min** (39.1 h) and still
climbing when measured.

---

## 2. Timeline (UTC)

| When | What |
|---|---|
| 2026-09-02 13:13 | last successful `stg_ref_players` build (the `built_at` stamp inside the parquet) |
| 2026-09-03 ~12:00 | the daily run in which the `build_ref_players_dimension_op` leaf should have rebuilt it — **no evidence it executed** (see §4) |
| 2026-09-03/04 | Alert A: a `--w3pre-only` leg killed at 480 s mid-`stg_statsapi_games` |
| 2026-09-04 03:30 | a later tick completes the whole tier in ~459 s — **21 s of margin**, on a quiet overnight tick |
| 2026-09-04 04:19 | measured: A self-healed (games OK, 30 m); B STALE at 2347 min |
| 2026-09-04 ~04:28 | operator rebuilds the dimension from the laptop; all five artifacts OK, `problem_count=0` |

---

## 3. Alert A — root cause, measured

### 3.1 The numbers

Per-table cost reconstructed from the S3 write timestamps of the 03:30 tick (a **quiet overnight**
tick — the favourable case):

| model | cost | raw input | intraday consumer |
|---|---|---|---|
| `stg_oddsapi_odds` | ~140 s | `mlb_odds_raw` — 225 files / 147.6 MB / 120 `dt=` partitions | none |
| `stg_oddsapi_events` | 8 s | `mlb_events_raw` — 39 files | none |
| **`stg_derivative_odds`** | **299 s** | `derivative_odds_raw` — **2,063 files** / 130.6 MB | none (daily CLV) |
| **`stg_statsapi_games`** | **12 s** | `monthly_schedule` — 6 files | **yes — 90-min SLA** |
| | **~459 s of a 480 s cap** | | |

**The serving-critical table costs 12 seconds.** It was killed because `W3PRE_STG_MODELS` built it
**last**, behind ~447 s of staging that nothing reads intraday.

### 3.2 Which hypothesis

- **(i) the odds tables outgrew the budget — CONFIRMED.** They are 93 % of the tier. Both odds
  flattens bind the **full-history** raw glob every 30 minutes, and DuckDB's bind cost is ~linear
  in **file count** (INC-42, measured: 21.8 s to bind `mlb_odds_raw` at 1,859 files). The raw
  stores are append-only, so tier cost rises monotonically all season. This was never a threshold
  event; it was a slow squeeze that had to cross 480 s. The growth is visible *inside* this
  incident: `stg_derivative_odds` was **211.4 s** in the alert body and **299.0 s** hours later.
- **(ii) `stg_statsapi_games` hung or slowed — REFUTED with a number.** It costs 12 s and completes
  fine. It was starved, not slow.
- **(iii) box contention — not needed to explain it, and not excluded.** A quiet tick already sits
  at 96 % of the cap, so contention is the *trigger* that tips a marginal tick over, not the cause.

### 3.3 Why the growth is asymmetric between the two odds stores

`mlb_odds_raw` **is** compacted — `compact_lakehouse_raw.py` runs daily at 08:40 UTC via
`capture.crontab` and has taken it 1,859 → 225 files. `derivative_odds_raw` is **not**: it is
absent from `COMPACTABLE_SOURCES` and from the cron, and has grown 6 → 813 → 1,123 objects/month.
INC-42 built the cure and applied it to one of the two append-only 30-minute capture stores. This
is the repo's recurring **one logical thing, many owners** shape (INC-30 crontab, INC-36
concurrency, INC-38 per-caller flags), here as a compaction allowlist.

---

## 4. Alert B — root cause, as far as measurement reaches

**The sources are healthy.** A read-only `--dry-run` of the builder returns **31,078 players,
1,420 current-season** against a floor of 200. So this is not the E5.10 signature, the coverage
guard was never going to refuse, and `player_profiles_raw` / `stg_batter_pitches` are both current.

**The writer simply did not advance.** `build_ref_players_dimension_op` is an **unbound fan-out
leaf** anchored at the end of the daily chain (downstream of `p_matchup`, i.e. of the whole
lk1..lk10 lakehouse build), ALERT-tier with `timeout=1800`.

⭐ **The discriminating evidence: the op DOES page on failure** — `send_alert(..., severity="ERROR",
dedup_key="ref_players_dimension_rebuild")`. No such page was received; only the freshness SLA
fired. A leaf that runs and fails pages; a leaf that **never executes** is silent. So the balance
of evidence is that the 09-03 run did not reach it, rather than that it ran and failed.

**This is the fork the spec asked to resolve, and it resolves to (i): the writer stopped
advancing — NOT an SLA-vs-cadence mismatch.** The 30 h SLA is correctly sized against a ~24 h
cadence with ~6 h of slack for the leaf's position at the end of a long chain. One missed daily
run puts the lag at ~48 h, which no defensible SLA would tolerate. **No SLA change is proposed.**

**Open:** *which* upstream op stopped the 09-03 run. That lives only in the Dagster event log —
see the operator command in §7. A corroborating oddity worth checking there:
`feature_pregame_lineup_features` carries a content stamp of **2026-09-03 22:51Z**, far later than
the ~13:00 a healthy 12:00 daily run would produce.

---

## 5. What shipped

1. **`W3PRE_STG_MODELS` reordered — `stg_statsapi_games` first.** The models are independent (each
   flattens its own raw JSON; no intra-tier dependency), so the order was always free to choose —
   and it decides *which table dies* when the tier runs out of time. This inverts the failure
   mode: the 12 s serving-critical table can no longer be starved, and a timeout instead truncates
   daily-cadence staging that nothing reads intraday and that the next tick rebuilds.
2. **A tier-budget threshold** (`w3pre_tier_verdict`, in the module that already owns
   `LEG_TIMEOUT_SECONDS`). Per-model seconds were **always printed** — the alert's own 158.8 s /
   211.4 s figures came from that log. Nothing ever **compared** them to the budget they had to fit
   in. That is the E11.30 shape exactly (detection existed, notification did not), so the cure is a
   threshold plus `[METRIC]` lines, not more logging. Warns at 60 % of the cap — chosen to leave
   ~190 s of headroom, deliberately **not** reverse-engineered from the 459 s that broke, since a
   threshold set just under the failing number fires only on the way past. **It never raises:** a
   build script that fails on slowness manufactures the outage it exists to predict.
3. **The DDL generator's mirrored copy** of the tier is documented as mirroring **membership, not
   order** (its order is cosmetic; syncing it either way would churn generated SQL or silently undo
   the fix), with a guard so membership cannot drift.

**Not changed, deliberately:** the E11.26 budget constants, any SLA, any schedule, any `.env`, and
the INC-41 content-timestamp / active-hours semantics.

### Why *not* a budget raise

The E11.26 invariants bound it hard: I3 (`3 legs × LEG ≤ MAX`) caps `LEG` at **500 s** with
`MAX=1500`, and I2 (`MAX < 1800`) caps it at ~**599 s** even if the whole cadence slack is spent.
So the maximum available raise is roughly **+25 %** — against an input that grows monotonically all
season. It would be consumed in weeks, and it would spend the slack that stops ticks stacking
(INC-32/INC-36). Making the tier cheaper is the only remedy that outlives the season.

---

## 6. What would have caught this earlier

| | |
|---|---|
| **A** | A threshold on tier time vs the leg cap — shipped here. The evidence was in the log for weeks; nothing compared it to a bar. |
| **A** | Extending INC-42's compaction to the *second* append-only capture store when it was applied to the first. A per-source allowlist needs a per-source sweep. |
| **B** | Nothing available would have. A fan-out leaf pages when it fails and is **silent when it never runs**; the INC-41 freshness SLA is the only instrument that can see it, and by construction it takes ~30 h. A per-run "did every expected leaf execute?" check is the missing detector — carded, not built here. |

---

## 7. Follow-ups (PM triage)

1. **`derivative_odds_raw` compaction** — the largest single cost in the tier (299 s, 2,063 files).
   Requires: a per-source reader argument (the script **refuses a borrowed rationale**), an
   allowlist entry, an operator `--apply`, and a crontab line. **Partial analysis done:**
   `mart_derivative_closes` *is* duplicate-idempotent (`row_number() ... = 1` over
   `(event_id, market_key, bookmaker_key, outcome_name, outcome_description, outcome_point)`), so
   the promote-then-delete duplicate window is a no-op for it. ⚠️ But `stg_derivative_odds` itself
   has **no dedup**, and `eval_cross_market.py` reads its parquet and does its own closing
   selection — that reader must be signed off before the source is allowlisted.
2. **Move the three odds staging models out of the intraday tick entirely.** They are daily-cadence.
   ⚠️ **Blocked on a fact to verify first:** `W11_W3PRE_DAILY` is default-OFF and **not in
   `env.required`**, so the daily w3pre build may be skipped — in which case the intraday tick is
   currently the *only* builder and removing them would freeze them. Check the box's live value
   before acting. (Recent-scoping the flattens is **not** a safe substitute: these are
   full-history tables, and a recent-scoped write to the same key would truncate history.)
3. **A "did every expected leaf run?" check** for the daily job — the detector §6 says is missing.
4. **Name the 09-03 daily-run failure** from the event log (§4).

---

## 8. Operator commands

**BOX** — the 09-03 daily run's fate and the per-op durations (read-only):

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
  python3 scripts/ops/dagster_runs.py daily_ingestion_job 6
```
```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
  python3 scripts/ops/dagster_runs.py daily_ingestion_job --steps
```

**BOX** — is the daily w3pre build even enabled (follow-up 2)?

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
  printenv W11_W3PRE_DAILY
```

**LAPTOP** — verify freshness by CONTENT timestamp (never S3 mtime):

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy && \
set -a && source .env && set +a && \
uv run python scripts/check_artifact_freshness.py --strict
```
