# Design — W7b-2: flip the INTRADAY serving + post_lineup predict to `--s3`

**Status:** SCOPED (2026-07-20). Not implemented. This is the LAST code gate before E11.20 phase-2a
step 3 (deleting the capture tick's `refresh_w1_external_tables` + `intraday_lineup_rebuild` SF legs)
can be done — the consumer audit (`monthly_schedule_s3_flip_design.md`) narrowed the game-hours
SF-view readers to exactly the two scripts this flip moves.

**Serving-criticality: HIGH** (the live post_lineup picks + the intraday game-detail/book-odds
blobs). Merge bar for the FLIP = a real box run (RUNTIME GATE). The CODE is default-OFF, so merging is
a runtime no-op.

---

## The W7b-1 blocker — and why it is already closed

`write_serving_store_intraday_op` (`pipeline/ops/daily_ingestion_ops.py`) and the tick's
`lineup_predict`→`predict_today.py` (`pipeline/ops/sensor_ops.py`) both run **without `--s3`**, unlike
the MORNING path (`predict_today_morning` / `write_serving_store_op`) which already passes
`_w7b_s3_args()` (`--s3` when `W7B_LAKEHOUSE_S3=1`, enforced-ON). The stated reason (W7b-1 docstring):

> "the export-mirror is daily-cadence (a full-history feature re-export every ~10-min intraday fire is
> too costly), and today's lineup-driven feature freshness needs the W6-style `_current`-bucket split
> **or the W7b-2 DuckDB feature build** → so the daily morning path goes S3 first; the intraday/
> post-lineup serving path is the documented W7b remaining tail."

**That prerequisite now exists.** `lineup_intraday_s3_feature_rebuild` (s2b in `lineup_monitor_job`,
added 2026-06-30 for the 824819 loop, gated on `LINEUP_INTRADAY_S3_REBUILD` which is **enforced-ON** in
`REQUIRED_INTRADAY_FLAGS`) IS the W7b-2 DuckDB feature build: it rebuilds the S3 W8b
feature/matchup/aggregator parquet intraday (`run_w1_lakehouse --w8b-only`) from the fresh confirmed
lineup, then refreshes the ext tables — BEFORE predict runs. Morning uses the daily export-mirror;
intraday uses this DuckDB rebuild. So the intraday `--s3` feature read is now as fresh as the SF read.

`lineup_monitor_job` order (already correct): `s1u → s2 (dbt staging, SF) → s2b (--w8b S3 feature
rebuild) → s2c (dbt feature, SF) → s3 (predict) → clv → serving`. s2b is upstream of predict.

---

## The flip

A NEW default-OFF gate `W7B_INTRADAY_S3` (NOT reuse `W7B_LAKEHOUSE_S3`, which is already `1` — reusing
it would flip serving-critical intraday behavior the instant the code merges, with no soak). Merge =
no-op; the operator sets it after the box gate, and unsetting it is the instant rollback.

```python
# pipeline/ops/daily_ingestion_ops.py
def _w7b_intraday_s3_args() -> list[str]:
    # W7b-2: the intraday predict + serving read S3 (features kept fresh by
    # lineup_intraday_s3_feature_rebuild, s2b). Separate default-OFF gate so this serving-critical
    # intraday flip soaks independently of the morning/daily path (W7B_LAKEHOUSE_S3).
    return ["--s3"] if os.environ.get("W7B_INTRADAY_S3") == "1" else []
```

Two call sites:
1. **`write_serving_store_intraday_op`** — currently `["--picks", "--game-detail", "--book-odds"]`;
   append `_w7b_intraday_s3_args()`.
2. **`lineup_predict`** (`sensor_ops.py`) — currently
   `["--prediction-type", "post_lineup", "--lineup-confirmed", "--notify"]` (+ game-pks); append the
   same flag args. (`sensor_ops` can't import the daily-ops helper cleanly if it introduces a cycle —
   read the env var directly there, or lift the helper to a shared `pipeline/ops/_serving_flags.py`.)

Nothing else changes: `predict_today.py --s3` (`set_s3_mode`) and `write_serving_store.py --s3` are the
SAME daily-proven read paths (INC-23-audited); this only routes the intraday callers through them.

---

## Freshness dependency chain (what must be fresh in S3 before the intraday `--s3` read)

| S3 input the intraday `--s3` path reads | Kept fresh intraday by | Status |
|---|---|---|
| `feature_pregame_*` / matchup / aggregator (`--w8b`) | `lineup_intraday_s3_feature_rebuild` (s2b), upstream of predict | ✅ enforced-ON |
| `mart_odds_outcomes` (book-odds, pre-game odds) | W6 intraday (`odds_current_rebuild` → `_w6_lakehouse_intraday`), gated `W6_LAKEHOUSE_INTRADAY` | ⚠️ **HARD PREREQ — NOT enforced** (see below) |
| `stg_statsapi_games/_lineups_wide/_probable_pitchers` | `intraday_schedule_job` `--w3pre`/`--w7b`; and lineup_monitor DETECTED via the S3 lineups_wide, so it is already fresh at fire time | ✅ |
| `daily_model_predictions` (serving reads picks) | `lineup_predict` writes them, then mirrors to S3 (the E11.20 phase-2a mirror already added) | ✅ |

If s2b is skipped/fails (mirror-tier, ALERT-continue), the intraday `--s3` predict reads the last-good
S3 features — same degraded-not-dead behavior as today, and the Story 30.13 serve-time freshness gate
backstops genuine staleness. **Validation item:** confirm predict_today's freshness/coverage gate is
active in `--s3` mode (it is on the morning path; assert it fires on a stale intraday S3).

### ⚠️ HARD PREREQUISITE — `W6_LAKEHOUSE_INTRADAY=1` for the book-odds leg

`W6_LAKEHOUSE_INTRADAY` gates the intraday `mart_odds_outcomes` S3 rebuild, and it is **NOT in the
enforced set** (`REQUIRED_INTRADAY_FLAGS` / `env.required`), so it may be OFF on the box. If OFF, the
intraday S3 `mart_odds_outcomes` parquet is not rebuilt intraday → `write_serving_store_intraday
--book-odds --s3` would serve STALE (morning) odds. Precedent: `write_book_odds_op` already couples
its own `--s3` to **BOTH** `W7B_LAKEHOUSE_S3` AND `_W6_INTRADAY_ENABLED` for exactly this reason (the
2026-07-03 line-movement-freeze regression). W7b-2 must honor the same coupling. Two options:
- **(pref) Verify `W6_LAKEHOUSE_INTRADAY=1` on the box** (audit the LIVE container env, not the docs —
  the "documented ≠ set" landmine) and make it a stated prereq of the flip; ideally add it to the
  enforced set at the same time.
- Or scope W7b-2 in two steps: flip `--picks`+`--game-detail` to `--s3` first (features via s2b, no
  odds dependency), and gate the `--book-odds` `--s3` leg on `W6_LAKEHOUSE_INTRADAY` like
  `write_book_odds_op`. (predict itself is market-blind — `best_alpha=0` — so the PICK doesn't depend
  on odds; only the served book-odds/consensus display does.)

---

## Box runtime gate (the merge bar for the FLIP)

1. Deploy (code merged, `W7B_INTRADAY_S3` unset → no-op). Then set `W7B_INTRADAY_S3=1`.
2. On a live slate, after a post_lineup re-score: **parity** — the intraday `--s3` picks == the SF
   picks for the same game_pks (run `predict_today.py --prediction-type post_lineup --game-pks <…>`
   both with and without `--s3`, diff the `pick`/`p_home_win`/`pred_total_runs`). A mismatch beyond
   float noise is a real defect (stale S3 feature or an INC-23 cast gap).
3. **post_lineup coverage does not regress** vs the 0.811–0.812 baseline (the served lineup block —
   `avg_eb_woba` etc. — must be populated, not NULL: the INC-17/INC-31 class).
4. Confirm no Snowflake session from `write_serving_store`/`predict_today` in that window
   (`query_history`) — the point of the flip.
5. Instant rollback = unset `W7B_INTRADAY_S3`.

---

## Then step 3 (the credit win) — and its one remaining coupling

After W7b-2 flips, NO game-hours consumer reads the SF staging views (per the audit), so the tick's
`refresh_w1_external_tables` + `intraday_lineup_rebuild` (dbt) legs can be deleted, and the tick goes
Snowflake-free (capture writer→S3 + `--w3pre` + `--w7b`; the `--w8b` s2b rebuild stays).

⚠️ **One coupling to verify before deleting the tick's dbt staging leg:** `lineup_intraday_s3_feature_
rebuild` step 1 = `backfill_lineup_state_scd2.py`. Confirm its INPUT read (the confirmed lineup it
MERGEs into the SCD-2) comes from the **S3** `stg_statsapi_lineups_wide` parquet, not the SF staging
table that `intraday_lineup_rebuild` (s2) rebuilds. If it reads SF staging, s2 (or an S3-equivalent)
must survive the tick delete, or s2b would build features from a stale lineup. `enforce W7b-2` does not
depend on this; the STEP-3 delete does.

Enforce `W7B_INTRADAY_S3` (add to `env.required` + `REQUIRED_INTRADAY_FLAGS` + `BOX_OPERATIONS.md
§10a`) only AFTER the soak passes — same coupling caveat as `LINEUP_MONITOR_S3` (a rollback then also
reverts the enforcement, else the heartbeat false-pages).
