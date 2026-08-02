# INC-38 — user bets stuck PENDING forever on late month-boundary games

**Date:** 2026-08-02 · **Severity:** P1 (user-visible, silent, never self-heals) · **Status:** RESOLVED
**Sibling of:** [INC-37](inc37_month_boundary_schedule_hole.md) — the same month boundary, the other direction.

---

## Summary

Three user bets on 2026-07-31 games sat `Pending` in the bet log with a settlement op that ran
clean on every pass. The games had been over for two days.

`ingest_statsapi.py schedule` fetches **whole calendar months**. INC-37 fixed the forward half of
that boundary (`--lookahead-days 3`, so the last captures of a month also fetch the next). Nothing
fixed the backward half: once the calendar rolls, **no capture ever revisits the previous month**.

A game that first-pitches after `00:00 UTC` on the 1st — every West-coast night game on the last
day of a month — is therefore still Pre-Game or In-Progress in the final same-month capture, and
its Final + score is never written. `stg_statsapi_games` is the flatten of that capture, and
`settle_user_bets._final_scores` grades h2h/totals only on `status_code in ('F','O')` with scores.
So the bet never settles, no error is raised, and nothing pages.

## Evidence (live lakehouse, 2026-08-02)

The month boundary is the *entire* signature — these were the only non-terminal historical games
in the 2026 season:

| official_date | status | n |
|---|---|---|
| 2026-06-30 | In Progress | 4 |
| 2026-07-31 | In Progress | 7 |
| 2026-07-31 | Pre-Game | 7 |

07-31 was 14 of 15 games frozen. The last July capture was `2026-07-31T23:30:15Z`; the next
capture, `2026-08-02T03:30:13Z`, was August-scoped. The two stuck games first-pitched at
`00:40Z` and `01:40Z` — i.e. they had not started when the last July capture ran.

### ⚠️ The near-miss

The frozen rows carry **non-null partial scores** (game 824486 sat at `5-3` In Progress). A
score-presence check alone would have settled live bets off a mid-game score. Only the
`status_code in ('F','O')` gate prevented it. That gate is now pinned by test.

## Why the existing cure did not hold

`ingest_statsapi_schedule` has passed `--start-date <yesterday>` since **2026-07-15**, added for
exactly this symptom (6/30's 4 frozen games). It did not work, and the reason is the retention
policy, not the flag:

`run_schedule` writes with `mode="overwrite_partition"` into `dt=<fire date>`. Each fire
**replaces that entire partition with only the months it pulled**. So the month-only *intraday*
tick, running minutes after the daily op, clobbers the daily op's wider fetch. One caller carrying
the flag is not enough — this is the repo's recurring "one logical job, two execution owners"
shape (cf. INC-30 crontab, INC-36 concurrency) wearing a retention-policy costume.

### …and the caller set is four, not two

INC-37 shipped `--lookahead-days` to the two Dagster ops, leaving
`services/schedule_capture/entrypoint.sh` and `sensor_ops.lineup_ingest_schedule` with **no
month-boundary flags at all**.

> ⚠️ **Establish which caller is live from the deployed config, not from a docstring.**
> `sensor_ops.lineup_ingest_schedule` still says *"the schedule_capture cron handles statsapi
> schedule ingestion every 30 min off Dagster's bill"* — that describes the **pre-AWS Railway**
> arrangement. On the AWS box `schedule-capture` **is** defined in
> `services/dagster/aws/docker-compose.yml` but is **not in `capture.crontab`**. The live 30-min
> capture is the Dagster `intraday_schedule_capture_{daytime,overnight}` schedule
> (`*/30 14-23` and `0,30 0-3` UTC), which matches the observed `23:30:15Z` and `03:30:13Z` fires
> exactly. A session that trusts the docstring fixes the **dormant** image and calls it done.
>
> This first draft made exactly that error. The cure is to flag **every** caller regardless of
> which is live today: which one is live is a deploy-config fact that drifts underneath the code —
> the same class as `W7B_LAKEHOUSE_S3` being documented as cut over while never actually set.

Full caller set, all now flagged and pinned:

| caller | state before |
|---|---|
| `pipeline/ops/daily_ingestion_ops.py` | daily; `--start-date <yesterday>` + lookahead |
| `pipeline/ops/intraday_ops.py` | **the live 30-min capture on AWS** (`intraday_schedule_capture_{daytime,overnight}`); had lookahead |
| `pipeline/ops/sensor_ops.py` | manual/emergency; **no flags at all** |
| `services/schedule_capture/entrypoint.sh` | lean image — built in the AWS compose but **dormant** (not in `capture.crontab`); **no flags at all** |
| `pipeline/sensors/schedule_freshness_alert_sensor.py` | not an invocation — the remediation it **prescribes** to a human, which was a bare `schedule` |

⇒ When a fix is a **per-caller flag**, enumerate callers by grepping the script name across
`.sh`/`Dockerfile`/crontab as well as `.py`, and pin the registry itself in a test. Do **not** try
to fix "only the live one": which caller is live is a deploy-config fact (compose + crontab +
Dagster schedule status) that drifts underneath the code, and the in-repo comments describing it
were two platform migrations out of date. Flagging all of them makes the question moot.
Include human-facing remediation strings: the likeliest moment someone runs the sensor's
prescribed command is a boundary morning, i.e. the prescription re-opened the hole it paged about.

### ⚠️ A source-inspection guard is vacuous if prose can satisfy it

Caught two-sided while writing these tests. The first cut of the caller guard matched the flag
*anywhere* in the file — so the explanatory comment written above each fixed command made it
**pass on source with the flag deleted from the actual command**. A guard that cannot fail is the
NF1.7 (a) vacuous-anchor class in a new costume.

Cure: match a real argv form (`"--flag", "3"`) or strip comment lines first, and **prove the guard
fails on deliberately-broken source** before trusting it. Both are now asserted
(`test_the_check_is_not_satisfied_by_prose`), and the fire-check was run by hand on both forms.

## Fixes

1. **`--lookback-days N`** (`scripts/ingest_statsapi.py::apply_lookback`, the pure mirror of
   `apply_lookahead`) — the first N captures of a month also re-fetch the previous one. Wired into
   **all four** callers plus the sensor's prescription (see the table above); guard tests fail if
   any drops either flag, and a further test fails if a new caller appears outside the registry.
   `--lookahead-days 3` was added to the two callers INC-37 had missed at the same time.
2. **Settlement decoupled from the schedule flatten** — `settle_user_bets._statsapi_final_scores`
   asks the MLB Stats API directly for any game-market bet whose game our own table does not
   report final. The lakehouse stays primary; the API answers only the gap, only for games the
   live schedule reports **terminal** (never a partial in-game score), and only with a full score
   pair. `settle_source` records which authority answered. Kill switch:
   `SETTLE_SCORE_STATSAPI_FALLBACK=0`.
3. **The stale-pending-bet guard** — every pass emits `[METRIC] stale_pending_bets=<n|-1>`;
   `_alert_on_stale_pending_bets` pages CRITICAL. A bet pending >24h past first pitch is a data
   defect, not a long game. `-1`/absent ⇒ WARN, never scored healthy (NF1.7 (a)).

## Remediation performed

- Re-ran the fixed capture (laptop, **production** S3 keys):
  `--start-date 2026-08-02 --end-date 2026-08-02 --lookback-days 3 --lookahead-days 3` →
  fetched **2 months (July + August)**; the pre-fix form fetches August only. The July blob in
  `dt=2026-08-02` now holds **15/15 games Final for 07-31**.
- Ran `settle_user_bets.py`. All three bets settled from the Stats API and were verified flipped in
  DynamoDB (`pending_game_pk` removed, pending index empty):

  | bet | market | game | outcome | P/L | source |
  |---|---|---|---|---|---|
  | 419458f0 | under 11 | 824975 (DET 13 – ATH 1, total 14) | loss | −5.00 | statsapi |
  | 1a80d9bc | h2h away | 824325 (COL 3 – KC 1) | loss | −5.00 | statsapi |
  | e9132f2f | under 11 | 824325 (total 4) | win | +4.55 | statsapi |

  Grades were checked against the Stats API finals independently of the settlement code.

## ⚠️ Known residual (verified, not speculated)

`prune_same_month_partitions` is scoped to the **fire's** calendar month. The re-fetched July blob
therefore lives in an **August** `dt=` partition and is deleted once the 3-day lookback window
closes; the flatten then reverts to the stale `dt=2026-07-31` snapshot, which is still present and
still holds 1/15 final.

**So the lookback heals the live window every daily consumer reads, but does not permanently heal
history.** A durable fix needs content-aware retention — keep the latest partition per *content*
month, which requires a month column on the raw mirror. That is a change to a serving-critical raw
table's retention and was deliberately left out of an incident fix.

Bets are immune to the residual regardless, because settlement no longer reads that table for
finality — which is why decoupling settlement, and not the lookback, is the primary cure.

## Guards

`betting_ml/tests/test_inc38_month_boundary_settlement.py` — the pure lookback across real month
boundaries; both callers carry the flag; the writer still overwrites the whole fire-date partition
(the reason both must); the terminal-status gate rejects In-Progress/Pre-Game/Postponed even when a
partial score is present; end-to-end settlement with and without the fallback (a two-sided proof —
the fix test fails on the pre-fix path); and a two-sided stale check (a 2h-old game must not page,
a 30h-old one must).
