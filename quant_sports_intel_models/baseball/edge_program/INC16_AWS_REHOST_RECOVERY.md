# INC-16 — Railway workspace restricted → AWS re-host recovery plan

**Status:** 🔴 OPEN (2026-06-26). Railway workspace auto-restricted by Trust & Safety ("cannot create new resources"; bot says irreversible for paid workspaces). All Railway services down. **Decision (operator 2026-06-26): re-host the Railway stack on AWS; drop the serving Postgres → DynamoDB.**

## What's down vs up
- 🔴 DOWN (was on Railway): self-hosted Dagster (orchestration), the dbt-runner, the **serving Postgres** (picks cache), the capture crons (schedule/odds/derivative), the Dagster run-storage Postgres.
- 🟢 UP (not on Railway): frontend (Vercel), backend API (Lambda), **S3** (lakehouse + serving fallback — currently serving early-AM picks), **Snowflake** (alive), **DynamoDB** (users + bets — untouched), Cognito, SES. **Dagster+ Cloud** still exists as the idle rollback.

## The reassurance (scope this correctly)
**This is a re-hosting fire drill, NOT data loss.** The Railway serving Postgres is a DERIVED CACHE (written from Snowflake + predictions by `write_serving_store`) → fully regenerable. Real user/bet data is in DynamoDB (AWS), untouched. So the work is: re-home compute + swap the cache to DynamoDB — nothing irreplaceable was on Railway.

## Cost — re-host KEEPS the migration's goal
Dagster+ stays at $0 (we just move the self-host from Railway → AWS). Approx (verify in the AWS calculator):
| Component | AWS | ~$/mo |
|---|---|---|
| Dagster (daemon+web+codeloc) + dbt-runner + a tiny Dagster-storage PG | one small EC2 `t4g.small`/`medium` (or Lightsail $20) | $12–25 |
| Serving cache | **DynamoDB on-demand** (KV; pennies at beta volume) | ~$1–3 |
| Capture crons | Lambda + EventBridge schedules | ~$0–2 |
| Storage + egress | small | $1–5 |
| **Total** | | **~$15–35/mo** (≤ the Railway ~$50 target) |
**❌ COST TRAPS — avoid:** Aurora Serverless v2 (~$43/mo floor) · MWAA managed Airflow (~$350/mo floor — keep self-hosted Dagster OSS) · NAT Gateway (~$32/mo — use a public subnet + an S3 VPC endpoint) · oversized EC2 (this is a ~2 GB-RAM job).

---

## PHASE 0 — 🚑 IMMEDIATE: keep beta current TODAY (no Railway needed)
**Goal:** serve fresh picks while the AWS build happens. The frontend already falls back to S3 (it's up on stale AM data) → just refresh S3.
- Run `predict_today` + `write_serving_store` as a ONE-OFF **off Railway** (laptop / a throwaway EC2 / a Lambda): read the feature store from **Snowflake** (alive; yesterday's marts persist — skip the dbt feature-rebuild for one cycle), write the serving payload to **S3**.
- Verify the live frontend serves the refreshed picks (S3 fallback path).
- Repeat once per day until the AWS pipeline is live.
- **AC:** today's picks render on the live site from a fresh off-Railway run.

## PHASE 1 — AWS compute (Dagster + dbt-runner)
**Goal:** stand the orchestration + dbt-runner up on AWS (re-home, not rebuild — the Dagster OSS config already exists from the Railway self-host).
- One EC2 (`t4g.small`/`t4g.medium`, public subnet, security-group-locked) — or Lightsail for simplicity. S3 access via an **S3 VPC endpoint** (no NAT).
- Run the existing Dagster OSS services (daemon / webserver / codeloc) via **Docker Compose or systemd** — port `services/dagster/dagster.yaml` + `workspace.yaml`; replace the Railway `railway.*.toml` with compose/systemd units. Run a SMALL self-managed Postgres on the box for **Dagster's own run/event/schedule storage** (metadata only — NOT the serving cache).
- Re-deploy the **dbt-runner** on the same box (it already ran on Railway).
- **🕷️ flaresolverr (FanGraphs Cloudflare proxy):** re-home the `ghcr.io/flaresolverr/flaresolverr` container **on the SAME EC2** as the Dagster agent (~1 GB RAM for its Chromium → size the box at `t4g.medium`, not `small`). 🔑 **Must share an egress IP with the agent** — FanGraphs' `cf_clearance` cookie is IP-bound; co-locating on one instance satisfies this (as Railway did). Set `FLARESOLVERR_URL` on the agent to the local container. Without it: predictions still run (all FanGraphs features are nullable LEFT JOINs → Statcast fallback), but lose Stuff+ enrichment. **Do NOT migrate off FanGraphs** — Stuff+ is proprietary/irreplaceable and the re-home is trivial; this is a venue change, not a data-source decision.
- **🛡️ Robustness fix (E11.7 gap found during INC-16):** the FanGraphs ingest ops in `pipeline/ops/daily_ingestion_ops.py` aren't try/except-wrapped and aren't in the CLAUDE.md op→tier map. Make `ingest_fangraphs_stuff_plus` / `ingest_fangraphs_hitting_leaderboard` (+ zips) **WARN-tier** (catch → `context.log.warning` → op succeeds) so a flaresolverr/FanGraphs outage degrades quietly instead of raising into the daily job. Add them to the op→tier map.
- 🔑 Carry the CI/CD lesson: a pipeline change isn't live until the codeloc redeploys off main.

### P1 artifacts (code-complete 2026-06-26 — `services/dagster/aws/`)
The whole stack is now a single Docker Compose box (re-deploy, not rebuild):
- `docker-compose.yml` — all 6 containers (dagster-postgres/codeloc/daemon/webserver, dbt-runner, flaresolverr) on one bridge network; ports the OSS `dagster.yaml` + start commands; codeloc→dbt-runner / →flaresolverr wired by compose DNS; **schedules boot STOPPED**.
- `workspace.yaml` — daemon/webserver → `dagster-codeloc:4000` (compose DNS; the Railway `../workspace.yaml` is untouched for rollback).
- `provision-ec2.sh` — t4g.medium (arm64) + SG (operator-IP-locked SSH/3000) + **S3 gateway VPC endpoint (no NAT)** + IAM instance profile (S3, no static keys) + **Elastic IP (stable egress for FanGraphs cf_clearance)**.
- `cloud-init.sh` — Docker + compose + git + a 4 GB swapfile (the heavy image build OOMs without it).
- `.env.example` / `.gitignore` — env template (reconcile vs the Dagster Cloud secrets export); secrets never committed.
- `validate_flaresolverr.py` — real FanGraphs leaderboard pull → "Cloudflare clearance obtained" (proves IP-sharing).
- **Robustness fix shipped:** `ingest_fangraphs_stuff_plus` / `ingest_fangraphs_hitting_leaderboard` now WARN-tier in `pipeline/ops/daily_ingestion_ops.py` + the CLAUDE.md op→tier map.
- **Operator action (spends money / real infra):** run `provision-ec2.sh`, then on the box clone + fill `.env` + `docker compose up -d --build`. Full runbook: `services/dagster/aws/README.md`.

- **AC:** Dagster webserver + daemon healthy on EC2; defs load; the dbt-runner reachable; flaresolverr container healthy + sharing the agent's egress IP (a test FanGraphs leaderboard pull logs "Cloudflare clearance obtained"); FanGraphs ops are WARN-tier; schedules OFF until Phase 2/4.

## PHASE 2 — 💾 Serving cache: Railway Postgres → DynamoDB
**Goal:** replace the serving Postgres (the `api_cache` KV table) with DynamoDB.
- The serving store IS a key→JSON cache (`cache_key` → `value`, `is_permanent`, `updated_at`) → maps 1:1 to a DynamoDB table: **PK = `cache_key`**, attributes = the JSON value + `is_permanent` + `updated_at`. (Range/list reads like `picks/game/*` → use a GSI or a structured PK, e.g. PK=`picks/game`, SK=`{game_pk}`.)
- Backend: swap `app/backend/services/pg.py` `get_cache()` (+ the INC-12 `ORDER BY updated_at DESC` dedup) → DynamoDB `get_item`/`query`.
- Writer: `scripts/write_serving_store.py` → write to DynamoDB instead of the PG `api_cache` (keep the S3 writes as the fallback; the read order becomes **DynamoDB → S3**).
- Port the `is_permanent` semantics + the **E9.28 bulk-permanent-invalidation** (`invalidate_permanent_picks`) to a DynamoDB query+batch-delete.
- **AC:** picks/game-detail/book-odds/performance all read from DynamoDB; `write_serving_store` writes DynamoDB + S3; permanent-cache invalidation works; latency acceptable; a full read path validated.

## PHASE 3 — Capture crons → Lambda + EventBridge
**Goal:** restore the data feeds (odds/schedule/derivative) off Railway.
- Re-host `odds_capture` / `schedule_capture` / `derivative_capture` as **Lambda functions on EventBridge schedules** (serverless, ~$0) writing to S3/Snowflake. (Or run them on the EC2 box via cron — Lambda is cheaper + more reliable.)
- ⚠️ derivative_capture: keep the corrected F5 keys (`*_1st_5_innings`) from E2.0b-fix.
- **AC:** odds/schedule/derivative feeds flowing again to S3/Snowflake on schedule.

## PHASE 4 — Cut over, validate, decommission Railway
- Enable the schedules on the AWS Dagster; run a FULL daily cycle end-to-end (compute_elo → dbt_daily_build → predict_today → write_serving_store → DynamoDB/S3); validate picks served.
- Keep **Dagster+ Cloud as the emergency rollback** until AWS proves stable for a few days.
- Then **cancel the Railway plan** (everything on it is regenerable; a `pg_dump` of the serving PG is optional insurance only — it's a cache).
- **AC:** a clean multi-day daily cycle on AWS; Railway cancelled; Dagster+ decommissioned after; the ~$275/mo Dagster+ saving banked; total AWS infra ~$15–35/mo.

## Strategic upside
Consolidating orchestration + serving onto AWS (where Lambda/S3/DynamoDB/Cognito/SES already live) **removes the single-provider single-point-of-failure that just bricked everything** — no separate restrictable account can take the whole stack down again. The lakehouse (S3/duckdb) + Snowflake-minimization work continues unchanged (the dbt-runner just runs on EC2 now); end-state Snowflake-touch is still only the Cortex narrative.

## Open
- The Snowflake serving reads (Wsv) + the script migration (build_roadmap §Session-B item 9) continue on the new AWS host.
- Decide: EC2 vs Lightsail (Lightsail = simpler/fixed price; EC2 = more control/spot savings).
- **🅱️ E9.31 (zone heatmap) IAM grant — fold into P2's Lambda role, don't patch the old one.** E9.31 is parked on a one-time prod-Lambda S3 grant (GetObject on `baseball-betting-ml-artifacts/baseball/serving/zone_matchup/*`). Since P2 rebuilds the backend Lambda's execution context anyway, **add this statement to the NEW prod Lambda role during P2** (rather than `put-role-policy` on the soon-to-change `credence-prod-lambda-execution-role` and redo it). Once granted, the heatmap renders live — unparks E9.31.
