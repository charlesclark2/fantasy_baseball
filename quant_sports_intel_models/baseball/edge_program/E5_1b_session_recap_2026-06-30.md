# E5.1b session recap — props forward-cadence + emergency free-key pivot (2026-06-30)

## TL;DR
Wired the **daily forward player-prop capture** (E5.1b) and ran the historical
batter-prop backfills. Mid-session **the paid Odds-API credits ran out**, so we
**switched the live odds capture to the FREE/Starter key** and locked it to
**game lines only**. ⚠️ **This must be flipped BACK to the paid MAIN key at
midnight tonight (2026-07-01 00:00) when the 5M credits refresh** — see the PM
handoff at the bottom.

## Backfill progress (S3 `mlb/props/`, ground-truthed via DuckDB over parquet)

| market | status | coverage | rows |
|---|---|---|---|
| `batter_runs_scored` | ✅ **COMPLETE** | 2023-05-03 → **2026-06-29** (all 4 seasons) | 883,141 |
| `batter_rbis` | ✅ **COMPLETE** | 2023-05-03 → **2026-06-29** (all 4 seasons) | 929,359 |
| `batter_hits_runs_rbis` | 🟡 **PARTIAL — stopped on credit exhaustion** | 2023 full · 2024 full · **2025 only through 2025-06-24** · 2026 not started | 388,214 |

**`batter_hits_runs_rbis` remaining when credits return:**
- 2025-06-25 → 2025-11-01 (rest of the 2025 season)
- 2026-03-26 → 2026-06-29 (all of 2026 to date)
- then it joins the daily `--player-props-only` cadence and self-maintains.

The 5 pre-existing player props (`batter_total_bases/hits/home_runs`,
`pitcher_strikeouts/outs`) were last fresh ~2026-06-22 and still need their
06-23 → present catch-up (deferred until credits return; would have run via the
local catch-up command but that also needs the paid key).

## Code shipped this session (E5.1b forward cadence)
- `scripts/backfill_multisport_props_to_s3.py`: added the 3 batter markets to the
  `baseball_mlb` canonical `markets` list + a new **`--player-props-only`** flag
  (filters to `batter_*`/`pitcher_*`/`player_*` → the 8 player props). Daily run
  advances `mlb/props/` to yesterday via dynamic season-end (`today-1`) +
  idempotent partition skip. ~2k cr/day (~60k/mo) on the paid key.
- `betting_ml/tests/test_props_cron_market_filter.py` — 3 fast tests guarding the
  market filter (no derivative/spread key can leak in). Fast gate green (834 pass).
- `services/dagster/aws/capture.crontab` — daily cron line (0 13 UTC) via
  `docker compose exec -T -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc …`.
  ⚠️ **Currently DISABLED** (commented out) during the free-key window — see below.
- Local-run path proven: `AWS_DEFAULT_REGION=us-east-2 uv run scripts/backfill_multisport_props_to_s3.py --mode backfill --sport baseball_mlb --player-props-only`
  (region prefix REQUIRED — the box & local default to us-east-1; the artifacts
  bucket is us-east-2).

> Note: the `capture.crontab` + script edits were **hand-applied on the box** to
> unblock; the matching repo commit (dev → main) is still pending so the box stays
> in sync. `git add` list: `scripts/backfill_multisport_props_to_s3.py`,
> `betting_ml/tests/test_props_cron_market_filter.py`,
> `services/dagster/aws/capture.crontab`,
> `quant_sports_intel_models/baseball/edge_program/build_roadmap.md`.

## ⚠️ Emergency pivot — paid credits exhausted → FREE/Starter Odds-API key
When the paid MAIN key (`ODDS_API_KEY`) ran dry mid-session, to keep today's odds
flowing we made these **box** changes (under `~/app/services/dagster/aws/`):
1. **`.env`: pointed `ODDS_API_KEY` at the free/Starter key** (paid value backed up
   to `.env.bak`). The live `odds-capture` `/odds` pull is hardcoded
   `prefer_main=True`, so it now uses the working free key on the first attempt.
2. **Disabled the non-game-line Odds-API consumers in `capture.crontab`**
   (commented out + reinstalled): `derivative-capture` (team_totals / F5 / NRFI)
   and the new `--player-props-only` props cron. So the limited free quota is spent
   **only on h2h + totals game lines** (`odds-capture`, already h2h/totals-only).
3. Triggered an immediate `odds-capture` run to pull today's slate.

**Degradation accepted while on the free tier:** narrower book roster — omits
Fanatics, Caesars (`williamhill_us`), rebet (Bovada/Pinnacle/DK/FD/MGM still land).
Cost ≈ 2 markets × 3 regions × 48 runs/day ≈ 288 credits/day — fine for one day.

## ⏭️ PM SESSION HANDOFF — flip BACK to paid at the midnight credit refresh
**WHEN:** 2026-07-01 00:00 (midnight tonight), the moment the 5M paid credits
refresh. We are intentionally limping through the rest of **today** on the free
key (game lines only); the free tier should cover today's slate.

**FLIP-BACK checklist (reverse of the pivot):**
1. **Restore the paid key** — `~/app/services/dagster/aws/.env`: set `ODDS_API_KEY`
   back to the paid MAIN value (`cp .env.bak .env`, or restore that one line).
   First verify the refresh landed: `curl -s "https://api.the-odds-api.com/v4/sports?apiKey=<paid key>" -D - -o /dev/null | grep -i x-requests-remaining` (~5M).
2. **Re-enable the disabled crons** — these are now **committed disabled** in
   `services/dagster/aws/capture.crontab` (the `🚨 DISABLED 2026-06-30 — FREE-KEY
   WINDOW` blocks on `derivative-capture` + the `--player-props-only` props line),
   so the mandatory migration deploy reconciles to the disabled state cleanly.
   To re-enable: uncomment both lines IN THE REPO, commit → main → deploy (the
   deploy's step-6 reinstalls the crontab). If you can't wait for a deploy, hand-edit
   `~/app/services/dagster/aws/capture.crontab` on the box + `crontab <file>`, but
   then reconcile git so the next deploy doesn't abort on a dirty tree.
3. **Resume the historical backfills on the paid key:**
   - finish `batter_hits_runs_rbis` (2025-06-25→2025-11-01 + all 2026) —
     `--markets batter_hits_runs_rbis` (idempotent; only fetches the gap).
   - catch up the 5 stale existing props (06-23→present) — the
     `--player-props-only` cron does this on its next 13:00 UTC fire, or run it once
     manually (locally with `AWS_DEFAULT_REGION=us-east-2`, or on the box).
4. (Optional) confirm full book roster returns on `mart_odds_outcomes` for the
   first post-flip slate (Fanatics/Caesars/rebet back).

**Bottom line for the PM:** the free key is a stopgap for **today only**. At
midnight, restore `ODDS_API_KEY` to paid + re-enable derivative/props capture, and
resume the `batter_hits_runs_rbis` (+ stale-5) backfills. Should be a clean revert
via `.env.bak` and uncommenting two crontab lines.
