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

## PHASE 0 — ✅ DONE 2026-06-26 (pre + post-lineup picks live on S3). Now a DAILY MANUAL CYCLE until P1.
**Goal:** serve fresh picks while the AWS build happens. The frontend already falls back to S3 (it's up on stale AM data) → refresh S3.
**What happened (2026-06-26):** the morning predict had ALREADY run before Railway died → Snowflake already held today's 15 games in `daily_model_predictions` (`prediction_type=morning`) + feature + schedule rows. The pipeline only died at the serving-WRITE step (it wrote to the dead PG, never S3). So today's fix was just `write_serving_store → S3`, not a re-predict. Pre-lineup + post-lineup both rendered fresh from `credence-prod-s3-api-cache`.

**🔑 GOTCHAS (carry forward — these cost time):**
1. **`DATABASE_URL` won't unset via `env -u`** — the script's `load_dotenv()` (default `override=False`) repopulates it from `.env` → it then dials the dead Railway PG. **Fix: pass it EMPTY-but-present:** `DATABASE_URL='' CACHE_BUCKET=credence-prod-s3-api-cache uv run python scripts/write_serving_store.py`. Empty → `load_dotenv` leaves it → `_pg_connect()` returns `None`, PG skipped, only the S3 writes fire. (Backend read order PG→S3→Snowflake confirmed in `picks.py`; S3 keys `api-cache/{today}/picks/*.json`.)
2. **dbt type-drift self-heal:** the feature rebuild failed on `feature_pregame_game_features_raw` + `_game_features` — `cannot change column HOME_AVG_K_PCT_30D from NUMBER(38,3) to FLOAT`. `--full-refresh` is unreliable in dbt-fusion (MERGEs, doesn't DROP+CREATE — known repo quirk) → fix = manual `DROP TABLE` both, then rebuild → recreate as FLOAT. **Now self-healed (FLOAT going forward).** `_meta_model_features` + `_public_betting_features` aren't needed for a post-lineup pass (meta serves morning-only; public-betting is lineup-independent) → leave them.
3. **W3pre stash dependency:** before any dbt build, **stash the 4 W3pre stg models** so the build runs against the original Snowflake-flatten models (the W3pre external tables don't exist yet — see the W3pre parked entry in story_prompts.md); `git stash pop` after.

**📋 DAILY MANUAL CYCLE until P1 restores orchestration:**
- *If the morning predict already ran* (like 2026-06-26): just `write_serving_store` with `DATABASE_URL=''` → S3 (pre-lineup), then after lineups re-run the post-lineup tail.
- *Tomorrow / cold start (heavier — morning predict won't pre-run):* full off-Railway cycle — `ingest_statsapi.py schedule` (+ `savant_ingestion batter_pitches` if needed) → **stash W3pre** → `+feature_pregame_game_features` dbt build → `predict_today --prediction-type morning` → `write_serving_store` (`DATABASE_URL=''`) → S3 → **stash pop**. After lineups: `ingest_statsapi schedule` (confirmed lineups) → rebuild feature chain → `predict_today --prediction-type post_lineup --lineup-confirmed` → `write_serving_store` → S3.
- **AC (met):** ✅ pre + post-lineup picks render fresh on the live site from S3. Odds gap quantified + routed to P3 (below).

**⚠️ ODDS REALITY (corrects the original P0/P3 assumption):** there is **NO live runtime odds pull**. Both `predict_today` and `write_serving_store` read CAPTURED odds from `mart_odds_outcomes` → **displayed prices are stale as of the last capture, not current.** On 2026-06-26: last raw capture (`mlb_odds_raw`) 11:02 UTC; served odds (`mart_odds_outcomes`) 07:32 UTC (lags raw because the dbt-runner is down); gap growing ~6–10h. **Pick SELECTION (which side) is the morning model's and is fine; only the PRICES are stale.** This raises P3's urgency — restoring capture is what makes displayed prices current again.

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

## PHASE 2 — 💾 Serving cache: Railway Postgres → DynamoDB  ✅ DONE 2026-06-26
**Goal:** replace the serving Postgres (the `api_cache` KV table) with DynamoDB.

> **✅ SHIPPED + DEPLOYED LIVE 2026-06-26.** Table `credence-prod-serving-cache`
> (single-table **structured PK/SK**: `pk`=namespace, `sk`=`{rest}#{date}`|`{rest}#PERMANENT`,
> `value`=JSON string — not the PK=`cache_key` sketch below; chosen because the only
> non-point ops are the `team/` list + `picks/game/*` purge + admin `invalidate_today`).
> New `app/backend/services/serving_cache.py` reader (DynamoDB→S3); cache fns deleted from
> `pg.py` → **`pg.py` removed**; 6 routers repointed; `user_portfolios` → a `portfolio` map
> on the DynamoDB users table (`dynamo.py`); `daily_picks` retired; `write_serving_store`
> writes DynamoDB+S3; IAM on the EC2 instance-profile + Lambda role; serving `DATABASE_URL`
> dropped from box + Lambda. **E9.31 heatmap unparked + renders live.** Provision via
> `infrastructure/dynamo/create_serving_cache_table.sh`. Gotcha solved: a Compose `env_file`
> can't carry PEM newlines → `resources/__init__.py` + writer + dbt-runner entrypoint now
> normalize `\n`-escaped/base64 keys (had silently broken ALL container Snowflake access).
- The serving store IS a key→JSON cache (`cache_key` → `value`, `is_permanent`, `updated_at`) → maps 1:1 to a DynamoDB table: **PK = `cache_key`**, attributes = the JSON value + `is_permanent` + `updated_at`. (Range/list reads like `picks/game/*` → use a GSI or a structured PK, e.g. PK=`picks/game`, SK=`{game_pk}`.)
- Backend: swap `app/backend/services/pg.py` `get_cache()` (+ the INC-12 `ORDER BY updated_at DESC` dedup) → DynamoDB `get_item`/`query`.
- Writer: `scripts/write_serving_store.py` → write to DynamoDB instead of the PG `api_cache` (keep the S3 writes as the fallback; the read order becomes **DynamoDB → S3**).
- Port the `is_permanent` semantics + the **E9.28 bulk-permanent-invalidation** (`invalidate_permanent_picks`) to a DynamoDB query+batch-delete.
- **AC:** picks/game-detail/book-odds/performance all read from DynamoDB; `write_serving_store` writes DynamoDB + S3; permanent-cache invalidation works; latency acceptable; a full read path validated.

## PHASE 3 — Capture crons → EC2 host-cron (→ Lambda/EventBridge later)
**Goal:** restore ALL the Railway capture feeds (odds / schedule / derivative / weather) off Railway.

> **✅ CODE-COMPLETE 2026-06-26 — approach: EC2 host-cron (operator decision; Lambda/EventBridge
> deferred until data sources / ingest frequency grow).** The 4 capture crons are re-homed as
> run-once images under the `capture` profile in `services/dagster/aws/docker-compose.yml`, fired
> by the host crontab `services/dagster/aws/capture.crontab` via `docker compose run --rm`.
> **🔑 Same key bug as P2 fixed in all 4 entrypoints:** they materialized the PEM with
> `printf '%s\n' "$SNOWFLAKE_PRIVATE_KEY"` → broke on a single-line `\n`-escaped/base64 value;
> now normalized (`\n`-escaped first, then base64, raw passthrough). `schedule`+`weather`
> entrypoints self-guard their UTC windows. **Served-price freshness (task 3):** P3 makes RAW
> odds (`mlb_odds_raw`) current; DISPLAYED prices (`mart_odds_outcomes`) refresh via the odds-mart
> rebuild (`stg_oddsapi_odds mart_odds_outcomes`) — the `odds_current_rebuild_sensor`, enabled at
> P4; an optional interim refresh chain is in `capture.crontab` (commented). **OPERATOR DEPLOY:**
> on the box — `git pull` → `docker compose --profile capture build` → smoke-test one capture →
> `crontab services/dagster/aws/capture.crontab` → run the odds **backfill** for the live gap
> (`MAX(captured_at)` in `mlb_odds_raw` → now; historical pull if the provider tier supports it,
> else log the gap). Full steps: `services/dagster/aws/README.md`.
- ⚠️ **FIRST enumerate every cron that lived on Railway** (cross-check the old Railway cron/service config + the Dagster schedules in `pipeline/` + the CLAUDE.md op→tier map) so none are missed.
- Re-host as **Lambda functions on EventBridge schedules** (serverless, ~$0) writing to S3/Snowflake — `odds_capture`, `schedule_capture` (schedule/probables), `derivative_capture`, **`ingest_weather` (pregame) + `intraday_weather_capture`**. (Or run on the EC2 box via cron — Lambda is cheaper + more reliable.)
- ⚠️ `derivative_capture`: keep the corrected F5 keys (`*_1st_5_innings`) from E2.0b-fix.
- Preserve each op's tier: weather = **WARN** (non-critical; predictions run without it), `schedule_capture`'s dbt trigger = **ALERT-loud-on-skip**.
- **AC:** odds / schedule / derivative / weather feeds all flowing again to S3/Snowflake on schedule.

## PHASE 4 — dev→main cutover, validate, decommission Railway
> **🔧 ARTIFACTS CODE-COMPLETE 2026-06-26 — cutover itself is operator-run (multi-day window).**
> Code-side delivered: (1) **no-double-serve VERIFIED in code** — the 4 host-cron captures have NO
> registered Dagster schedule (`intraday_schedule_capture_*` / `intraday_weather_*` are omitted from
> `all_intraday_schedules`; registered = 7 weekly/daily + `odds_clv_rebuild_daily`, none a capture);
> nothing boots `default_status=RUNNING`. (2) **Caddy HTTPS+basic-auth** service + `Caddyfile` added to
> the compose (webserver re-bound to `127.0.0.1:3000`; `caddy_data`/`caddy_config` volumes; secrets via
> `env_file` so the bcrypt `$` survives). (3) `.env.example` updated (P4 dagit vars + P2 DynamoDB vars;
> dropped stale `DATABASE_URL`). (4) Full P4 runbook (checklist + Caddy + SSM + SG + DNS commands) in
> `services/dagster/aws/README.md` §P4; `aws_resources.md` P4 record (auth choice = **Caddy basic-auth
> + SG allowlist**, operator-confirmed). **OPERATOR RUNTIME STEPS** (sequence in README §P4): merge
> dev→main + rebuild (incl. `--profile capture`) → pre-cutover checklist → full daily cycle → flip
> schedules + enable `odds_current_rebuild_sensor` + re-comment `capture.crontab` line 42 (same window)
> → DNS A record + Caddy secret + SG 80/443 + SSM policy → multi-day soak → cancel Railway + Dagster+.

> **🔥 PHASE-G DRY-RUN FINDINGS 2026-06-26 (env/IAM gaps — box `.env` was populated from memory, not the
> full Railway/Dagster+ env; all surfaced by manually running `daily_ingestion_job`):**
> 1. **Sub-model `.pkl`s wouldn't load** — `generate_*_signals.py` (run_env/offense/starter/starter_ip/matchup/bullpen, 7 scripts) gated S3-vs-local on `AWS_ACCESS_KEY_ID` (a static key the box doesn't have — it uses the instance role) → fell back to a local path not in the image → `FileNotFoundError`. FIX: switch also honors `ARTIFACTS_FROM_S3`; set `ARTIFACTS_FROM_S3=1` in box `.env`. (Same class as the PEM bug: Railway assumed static keys.)
> 2. **`CACHE_BUCKET` unset on the box** → `write_serving_store`/`write_api_cache` SILENTLY skip all S3 fallback writes (guarded `if bucket:`) — DynamoDB still served, but the S3 fallback went empty. Set `CACHE_BUCKET=credence-prod-s3-api-cache` (the SERVING cache bucket — NOT the `baseball-betting-ml-artifacts` ML bucket).
> 3. **IAM: role lacked write on the serving-cache bucket** — `write_api_cache` got `AccessDenied s3:PutObject` on `credence-prod-s3-api-cache` (P1 role was scoped to `baseball-betting-ml-artifacts` only). FIX: added inline policy `credence-s3-api-cache-rw` (Get/Put on `/*` + ListBucket) to `credence-dagster-ec2-role`.
> 4. **All other daily-job S3 writers (statcast ingest/export, ref_players, W1 lakehouse, raw_writer) target `baseball-betting-ml-artifacts`** (role already RW) → no further S3/IAM gaps on the serving path (swept).
> 5. **PREVENTIVE:** diff box `.env` keys vs the Dagster+ Cloud env export (the documented source of truth) to flush any remaining missing vars at once, instead of one failed op at a time. `daily_ingestion_job` confirmed GREEN after fixes 1–3.
- The box tracks **`dev`** → **merge `dev`→`main`** (carries P2 + the PEM key-normalization + P3), repoint the box to `main`, `docker compose up -d --build`.
- **PRE-CUTOVER CHECKLIST (from the P2/P3 findings — all green before enabling schedules):** dbt-runner key loads (`head -1 /tmp/snowflake_rsa_key.pem` = `-----BEGIN`, the `_normalize_pem` fix); IMDSv2 hop-limit=2 persists + `AWS_DEFAULT_REGION=us-east-1` in container env; Lambda still has the `DynamoServingCacheRead` + `S3ArtifactsZoneOverlayRead` grants after any redeploy; `DATABASE_URL` absent on box + Lambda.
- Run a FULL daily cycle end-to-end (compute_elo → dbt_daily_build → predict_today → write_serving_store → DynamoDB/S3); validate picks served + the 4 backend surfaces + the E9.31 heatmap.
- **Flip schedules in ONE window:** enable the AWS-box dagit schedules WHILE turning Dagster+ Cloud schedules OFF — never both on (no double-serve). Restores `lineup_monitor` re-scoring → post-lineup predictions render again.
- **🌐 dagit at a real hostname + SSM shell:** A record `dagster.credencesports.com` → the EIP (`100.57.225.242`; subdomain — apex stays Vercel) + **Caddy** reverse proxy w/ Let's Encrypt TLS → dagit:3000. ⚠️ **dagit has NO built-in auth** → keep an auth layer (SG IP-allowlist simplest/$0, or Caddy basic-auth, or ALB+Cognito later ~$16/mo); never open it bare. **SSM Session Manager** for shell (no SSH keys / no open :22) → retires SSH. Record DNS + cert + auth choice in `aws_resources.md`.
- Keep **Dagster+ Cloud as the emergency rollback** until AWS proves stable for a few days.
- Then **cancel the Railway plan** (everything on it is regenerable; the serving PG is fully replaced by DynamoDB; a `pg_dump` is optional insurance only).
- **AC:** dev→main merged + box on main; pre-cutover checklist green; a clean multi-day daily cycle on AWS; lineup re-scoring live; dagit at `https://dagster.credencesports.com` behind auth + SSM shell working; Railway cancelled; Dagster+ decommissioned after; the ~$275/mo Dagster+ saving banked; total AWS infra ~$15–35/mo.

## PHASE 5 — Orchestration CI/CD (GitHub) — guard + auto-deploy future orchestration merges
> **✅ EXECUTED LIVE 2026-06-27 — all 3 CI checks GREEN on the PR; CD proven end-to-end (OIDC → SSM →
> deploy.sh ran full pull→env-parity→drain→rebuild→6 verify checks on the box); auto-on-merge trigger
> confirmed; operator completed OIDC role + repo vars/secret + branch protection.** Built:
> `.github/workflows/orchestration_ci.yml` (defs-validate + `compose config` + lean-image
> builds + `scripts/ci/check_env_parity.py` + `scripts/ci/check_deploy_wiring.py`) and
> `.github/workflows/orchestration_cd.yml` (OIDC → SSM RunCommand → `deploy.sh`).
> `services/dagster/aws/deploy.sh` = the payload (**pull FIRST** → env-parity non-empty → snapshot →
> drain → `up -d --build` + `--profile capture build` → crontab-reinstall-if-changed
> → verify → **auto-rollback on failure**). `env.required` manifest added; flaresolverr
> pinned off `:latest` (P7-t1); cloud-init + provision-ec2 fold in cronie/SSM/IMDS-hop-2/
> P4 IAM grants so a fresh box is fully wired.
> **🔥 LIVE-DEPLOY GOTCHAS (this session):** (1) CI runner has NO box `.env` and NO dbt build artifacts —
> defs-validate needs 4 `SNOWFLAKE_*` placeholders (read at import, never connect) + `dbtf parse` to
> generate `dbt/target/manifest.json` offline (install dbtf via the cached install.sh the dbt-build job
> uses); `compose config -q` needs `cp .env.example .env` first. (2) **env-parity MUST run after the pull**
> — originally pre-pull, so it validated the STALE `env.required`; a key add/remove never took effect via
> CD until reordered (pull = step 1 now). (3) **BOOTSTRAP:** deploy.sh can't deploy itself — a brand-new
> deploy.sh (or a change to its own pull-vs-check order) needs ONE manual `git pull` on the box (SSM,
> ec2-user) before CD finds it; pull-first self-heals all future manifest changes. (4) `OPENWEATHERMAP_API_KEY`
> dropped from env.required (optional weather fallback); operator set `SERVING_CACHE_TABLE` on the box .env.
> EVENTUAL (deferred): true blue/green (daemon = singleton). Full runbook: `services/dagster/aws/README.md` §P5.
**Why (the recurring footgun):** "a pipeline change isn't live until the codeloc redeploys off main" is a MANUAL step that already bit a session (CI compile-only let the W1d runtime break through → INC-15). Once the box owns live orchestration, any future merge touching `pipeline/`, `services/dagster/aws/`, the dbt-runner, or the capture Lambdas must be (a) GATED by CI before merge and (b) auto-DEPLOYED to the box on merge to `main` — no silent drift between `main` and the running box.
**Scope = a GitHub Actions workflow (specced as INC-16-P5 in story_prompts.md):**
- **CI gate** (on PRs touching orchestration paths): Dagster `definitions validate` (defs load — catches the boot `_InactiveRpcError`/import breaks), `docker compose config` + a build of the changed images, a smoke that the PEM `_normalize_pem` + `AWS_DEFAULT_REGION` wiring is present, plus the existing Python fast gate + dbt jobs.
- **CD** (on merge to `main`, orchestration paths): deploy to the box (SSH/SSM `git pull` + `docker compose up -d --build` + a post-deploy `/health` + defs-loaded check), so `main` == running box automatically.
- **Safe-deploy / blue-green (replaces Railway's rolling deploys — PHASED):** serving is decoupled from the box (no site downtime on redeploy), and the Dagster daemon is a SINGLETON (never two at once). **NOW:** health-gated deploy with auto-rollback to the prior image + graceful drain of in-flight runs before recreate (~$0). **EVENTUAL (deferred, gated on an uptime SLA):** true blue/green — proxy-fronted dual stateless tier + a daemon-ownership handoff, or a standby instance (≈ doubled compute during deploys).
- **AC:** orchestration-affecting PRs are CI-gated; merges to `main` auto-deploy + self-verify + auto-rollback on failure; the "manual codeloc redeploy" step is gone.

## PHASE 6 — Observability + email alerting (the box now runs live with NO alerting)
**Why:** a silent failure (dead box / crashed daemon / failed build / bad deploy) wouldn't surface until someone notices stale picks. Email-preferred (SES already wired); ~$0. **CAN START NOW** (liveness layer doesn't wait on P4; the daily-output dead-man switch finalizes at/after P4). Three failure modes → one layer each, + reuse existing signals:
- **🪦 Daily-output dead-man's switch (highest value, do first):** alert if today's picks aren't in `credence-prod-serving-cache` by a cutoff (~8am ET) — outcome-based, fires for ANY root cause (watches what users see). Lambda+EventBridge or a CloudWatch heartbeat metric from `write_serving_store` → SES/SNS email on miss.
- **📉 Box/instance liveness + resource pressure (burstable t4g.medium — tuned so daily-build bursts don't page):** CloudWatch EC2 status-check alarms (instance + system) → SNS → email; + via the CloudWatch agent: **memory `mem_used_percent`>85% + swap climbing (highest-value — OOM is the likeliest failure on 4 GB, not CPU; check `dmesg | grep -i oom`)**, **disk>85%**, **CPU>90% SUSTAINED 30 min** (NOT brief build spikes — baseline 40%, load-avg>2 = saturated), and **CPU-credits** (`CPUCreditBalance`<50 if `standard`; if `unlimited` watch `CPUSurplusCreditsCharged` for cost instead).
- **🐳 Service liveness (box up, container down — a ping misses this):** host-cron healthcheck (~5 min) — `docker compose ps` all-Up + curl dagit:3000 / dbt-runner:8080 / flaresolverr:8191 (+ daemon-heartbeat-stale) → SNS/SES.
- **🚨 Dagster run-failure → SES**, scoped LOUD to HALT-tier ops (E11.7 map); WARN-tier digested to avoid noise.
- **♻️ Reuse, don't reinvent:** route `check_data_freshness` / `signal_freshness_check` output to the same channel; add a capture-feed dead-man switch (odds not landing in `mart_odds_outcomes`) since the P3 captures are host-cron, not Dagster-monitored.
- **AC:** a verified email per layer (missed daily output, instance/disk, stopped container, HALT-tier run failure); existing freshness routed to the same channel; de-duped + documented in `aws_resources.md`.

## PHASE 7 — Dependency / upgrade & patch management (self-hosting = we own versions now)
**Why:** Dagster, dbt-runner, flaresolverr, the metadata Postgres, the OS (AL2023), and all base images + Python deps now need deliberate, tested upgrades + CVE awareness — Railway/Dagster+ used to own this.
- **🛠️ PIN EVERYTHING (DO-NOW; fold into P5's reproducible box):** kill all `:latest` in `docker-compose.yml` (+ capture profile) — pin to explicit versions/`@sha256` (known: `flaresolverr:latest`). With P5's auto-`--build`, a `:latest` can pull a breaking upstream image onto the LIVE box silently → pinning makes upgrades deliberate.
- **🧩 Dagster coupling:** daemon + webserver + codeloc + the `dagster` lib must all be the SAME version (mixed = broken gRPC); a bump = coordinated across all four + `dagster instance migrate` + read release notes + validate defs before live. Document in `services/dagster/aws/UPGRADING.md`.
- **🤖 Renovate/Dependabot** for orchestration image tags + Python deps → PRs flow through the **P5 CI gate** (defs-validate + compose-build catch breakage pre-merge); grouped/scheduled to avoid noise.
- **🔒 Patch cadence (~monthly):** OS/base-image refresh (prefer "replace the box" via a fresh AMI/cloud-init over patch-in-place) + security-advisory scan; subscribe to Dagster release notes + GH security advisories.
- **🧪 Upgrade test path:** CI-green required; Dagster minor/major bumps validated on a standby box (P5 EVENTUAL) before promoting; P5 auto-rollback + P6 alerting are the net.
- **AC:** all image tags pinned (no `:latest`) + deps to lockfile; `UPGRADING.md`; Renovate/Dependabot raising grouped PRs through CI; documented patch cadence + advisory subs; an upgrade test path.

## PHASE 8 — DEV/staging box for PR pipeline integration testing (🔭 down-the-road, NOT beta-blocking)
**Why:** P5's CI gate is STRUCTURAL (defs-validate + compose-build + `dbtf compile`) — it doesn't RUN a pipeline against real-shaped data, which is the exact gap that caused INC-15 (W1d wrong types passed compile, broke at runtime). A dev box that executes the AFFECTED pipeline end-to-end on real-ish data catches what compile can't — the next tier above P5.
- **💡 One box, three jobs:** scope a single dev box that also serves as P7's Dagster-upgrade test box + P5's EVENTUAL blue/green standby (justifies the cost; don't build three).
- **Cost-shape:** ephemeral spin-up-on-PR / spot (~$0, preferred for beta) > dedicated small standby (~$25/mo) > ⛔ reuse prod box (contention/isolation risk).
- **🔒 Data isolation (the real work):** read a SAMPLED dataset, write ONLY to dev Snowflake schema / dev S3 prefix / dev DynamoDB table — NEVER prod serving (`mart_odds_outcomes`, `credence-prod-serving-cache`); dev IAM role scoped so prod-write is impossible.
- **Diff-scoped:** run only what the PR touches (dbt `state:modified+` + changed `pipeline/` ops), wired into P5's CD as a higher gate that reports PR status.
- **AC:** reproducible dev box (from P5 cloud-init); isolated dev data targets with no path to prod; PR-diff-scoped pipeline run on PRs + status report; verified isolation guardrail.

## Strategic upside
Consolidating orchestration + serving onto AWS (where Lambda/S3/DynamoDB/Cognito/SES already live) **removes the single-provider single-point-of-failure that just bricked everything** — no separate restrictable account can take the whole stack down again. The lakehouse (S3/duckdb) + Snowflake-minimization work continues unchanged (the dbt-runner just runs on EC2 now); end-state Snowflake-touch is still only the Cortex narrative.

## Open
- The Snowflake serving reads (Wsv) + the script migration (build_roadmap §Session-B item 9) continue on the new AWS host.
- Decide: EC2 vs Lightsail (Lightsail = simpler/fixed price; EC2 = more control/spot savings).
- **🅱️ E9.31 (zone heatmap) IAM grant — fold into P2's Lambda role, don't patch the old one.** E9.31 is parked on a one-time prod-Lambda S3 grant (GetObject on `baseball-betting-ml-artifacts/baseball/serving/zone_matchup/*`). Since P2 rebuilds the backend Lambda's execution context anyway, **add this statement to the NEW prod Lambda role during P2** (rather than `put-role-policy` on the soon-to-change `credence-prod-lambda-execution-role` and redo it). Once granted, the heatmap renders live — unparks E9.31.
