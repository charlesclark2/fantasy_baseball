# G100-D1 — Launch cost model + spend guardrails

**Status:** analysis complete, guardrails shipped (code), alarms pending operator action (§7).
**Date:** 2026-08-08 · **Context:** E9.46 + the freemium build are about to expose the generic
rankings board to anonymous traffic. Self-funded on Vercel Pro + AWS. `best_alpha = 0`.

Regenerate every number here with:

```bash
uv run python scripts/estimate_launch_cost.py            # the table in §3
uv run python scripts/estimate_launch_cost.py --no-guardrails   # the pre-G100-D1 baseline
```

The script is the model; this doc is its reading. Editing an assumption in
`scripts/estimate_launch_cost.py::Assumptions` and re-running is the supported way to disagree
with anything below.

---

## 1. The answer, in four lines

1. **Organic traffic is not the risk.** At 100,000 monthly visitors the projected bill is
   **~$21/month** — the $20 Vercel Pro seat plus **$0.88 of AWS**. Ten thousand visitors costs
   ~$0.10 of AWS. There is no traffic level in the plausible next-two-years range where serving
   the free board organically is expensive.
2. **The first real cliff is Vercel Edge Requests at ~250,000 monthly visitors**, and it is a soft
   one: $2.00 per additional million requests, so 500k visitors is ~$41/month and 1M is ~$81/month.
   Nothing about this is a spike.
3. **⭐ The actual exposure is ABUSE, and it is ~150× the organic bill.** One scraper at 50 req/s
   for a month costs **$3,210**, of which **$2,772 is S3/Lambda egress** — bandwidth, not compute.
   That is the number that justifies this story. With the per-IP limiter shipped here the same
   attack costs **$273**, so the limiter avoids **~$2,936/month** in the single-scraper case.
4. **Recommended alarm threshold: an AWS Budget and a CloudWatch billing alarm at $250/month**,
   plus free Cost Anomaly Detection for faster signal. Rationale and exact commands in §7.

> ⚠️ **An honest caveat about this story's own value.** The CDN/caching work in G100-D1 changes the
> *organic* bill by pennies ($21.01 → $20.88 at 100k visitors) — the visitor-driven cost was never
> the problem. Its value is entirely in the tail: bounding abuse, removing a per-request lakehouse
> read from a public path, and providing a one-flip floor. If the guardrails are justified on
> organic savings they are not justified at all; they are justified on §5.

---

## 2. Assumptions

Unit prices are **as of 2026-08-08** and are published/exact. Vercel re-prices its
managed-infrastructure line items — verify against the dashboard's Usage page before quoting.

| Vercel Pro | Included / month | Overage |
|---|---|---|
| Seat | — | $20.00 / member |
| Fast Data Transfer | 1 TB | $0.15 / GB |
| Fast Origin Transfer | 100 GB | $0.06 / GB |
| Edge Requests | 10 M | $2.00 / M |
| Function Invocations | 1 M | $0.60 / M |
| Function Duration | 1,000 GB-hr | $0.18 / GB-hr |
| Image Optimization | 5,000 images | $0.05 / 1,000 — **structurally $0 for us**: `next.config.mjs` sets `images: { unoptimized: true }` |

| AWS (us-east-1) | Rate |
|---|---|
| Lambda requests | $0.20 / M |
| Lambda duration | $0.0000166667 / GB-s (function is **512 MB**) |
| API Gateway HTTP API | $1.00 / M requests |
| DynamoDB on-demand read | $0.125 / M RRU (a ≤4 KB eventually-consistent read = 0.5 RRU) |
| DynamoDB on-demand write | $0.625 / M WRU |
| S3 GET | $0.40 / M |
| **Data transfer out to internet** | **$0.09 / GB** after 100 GB free — *the line that dominates the abuse case* |
| CloudWatch Logs ingest | $0.50 / GB |

**Traffic assumptions — this is where the error lives.** The unit prices are exact; these are
guesses until real analytics exist, and the total moves roughly linearly in each.

| Assumption | Value | Note |
|---|---|---|
| Page views / session | 2.5 | |
| KB transferred / session | 700 | first load pulls the JS bundle; later navigations are client-side |
| Edge requests / session | 40 | HTML + JS/CSS chunks + fonts + API calls; static chunks browser-cache after view 1 |
| Anonymous API reads / session | 3 | featured + manifest + board |
| **CDN POP multiplier** | **5** | ⭐ a CDN cache is **per-POP**, so an `s-maxage=300` object is fetched from origin ~once per 300 s *per POP that sees traffic*. Modelling this as 1 understates origin load ~5×. |
| Distinct cache keys | 12 | the board's key includes `(config, size)`, so origin load scales with the number of **format combinations**, not with visitors |
| Mean `s-maxage` | 600 s | featured 300 · board/manifest/projections 900 · track-record 3600 |
| Lambda ms / cached read | 120 | DynamoDB point read or one S3 GetObject on a warm container — **not** the lakehouse path |

---

## 3. Traffic → cost

**With the G100-D1 guardrails:**

| Monthly visitors | Vercel | AWS | TOTAL | Largest single line |
|---|---|---|---|---|
| 1,000 | $20.00 | $0.01 | **$20.01** | Lambda duration ($0.00) |
| 10,000 | $20.00 | $0.10 | **$20.10** | Lambda duration ($0.03) |
| 100,000 | $20.00 | $0.88 | **$20.88** | Lambda duration ($0.26) |
| 250,000 | $20.00 | $0.88 | **$20.88** | Lambda duration ($0.26) |
| 500,000 | $40.00 | $0.88 | **$40.88** | Vercel edge requests ($20.00) |
| 1,000,000 | $80.00 | $0.88 | **$80.88** | Vercel edge requests ($60.00) |

Note the AWS column **goes flat at $0.88 from 100k visitors upward**. That is the caching guardrail
working as designed: once a surface is CDN-cached, origin load is bounded by
`(windows per month × cache keys × POPs)` — a ceiling that does not grow with traffic.

**Vercel Pro included-quota utilisation:**

| Monthly visitors | Edge requests | Data transfer | Fn invocations | Fn duration |
|---|---|---|---|---|
| 1,000 | 0.4% | 0.1% | 0.3% | 0.0% |
| 10,000 | 4.0% | 0.7% | 3.0% | 0.2% |
| 100,000 | 40.0% | 6.7% | 25.9% | 1.8% |
| 250,000 | **100.0%** | 16.7% | 25.9% | 1.8% |

---

## 4. Where the cliffs are

| Quota | First exceeded at | What it costs past it |
|---|---|---|
| **Vercel Edge Requests (10 M)** | **~250,000 monthly visitors** | $2.00 / M — 500k ≈ +$20/mo, 1M ≈ +$60/mo |
| Vercel Fast Data Transfer (1 TB) | ~1.5 M visitors | $0.15 / GB |
| Vercel Function Invocations (1 M) | never at plausible traffic | capped by the cache ceiling, not by visitors |
| Vercel Function Duration (1,000 GB-hr) | never at plausible traffic | as above |

**Reading this:** edge requests bind first, and they are driven by the **number of static assets
per page view**, which none of the G100-D1 work touches. If the bill ever needs reducing at scale,
the lever is asset count/bundling — a different optimisation from anything here. There is no "Pro
overage cliff" in the sense of a step change: every Vercel overage is linear per-unit, so the bill
degrades gracefully rather than jumping.

---

## 5. ⭐ The abuse scenario — the actual risk

One source, 50 req/s, sustained for a month (129.6 M requests):

| | Total | of which egress |
|---|---|---|
| **No per-IP limit (the state before this story)** | **$3,209.67** | $2,771.91 |
| With the per-IP limit shipped here | $273.29 | $22.11 |
| **Avoided** | **$2,936.38** | |

Three things make this the real finding:

- **Egress dominates, not compute.** A 250 KB board pulled 129.6 M times is ~32 TB at $0.09/GB.
  Every intuition that says "Lambda is cheap" is correct and irrelevant.
- **It is not visitor-driven, so §3 cannot see it.** No traffic forecast contains it; it is a step
  function that starts the day someone points a crawler at an un-gated board.
- **The limiter does not reduce the request COUNT** — the attacker still connects. It reduces what
  each request costs, because a 429 returns a few hundred bytes instead of a board. The residual
  $273 is almost entirely API Gateway + Lambda request charges for cheap refusals; the API Gateway
  **stage throttle** (§7 of `infrastructure/aws_resources.md`) is the second layer that bounds
  those. Per-IP shaping and a total-blast-radius cap are complementary, not alternatives.

⚠️ **Honest limitation.** The per-IP bucket is per-Lambda-container, so the effective ceiling is
`limit × live containers`, and a low-and-slow attacker spread thinly across cold starts is
under-counted. An exact limiter needs a DynamoDB read+write on *every* request — itself a
per-request cost on the hot path this story exists to protect. See the module docstring in
`app/backend/services/cost_guardrails.py`.

---

## 6. What shipped (the guardrails)

| Guardrail | Where | Effect |
|---|---|---|
| Anonymous board + featured pick served from the Vercel CDN | `frontend/app/api/public/[...path]/route.ts`, `lib/api.ts::cdnFetch` | anonymous views cost **one origin call per `s-maxage` window per POP**, not one Lambda per view |
| Per-IP token bucket | `app/backend/services/cost_guardrails.py` | 30 burst / 0.5 per s anonymous; 60 / 2.0 authenticated. Keyed on the **gateway-observed** source IP, not a spoofable header |
| Degrade kill switch (`COST_DEGRADE_MODE=1`) | same module | serves only the cheap cached/static floor; expensive personalized endpoints answer 503. **Allowlist**, so a future endpoint is contained by default |
| Entitlement-keyed `Cache-Control` | same module | anonymous public reads get `public, s-maxage=…`; **any** request bearing `Authorization` gets `private, no-store` + `Vary: Authorization` |
| Per-request lakehouse read removed from `/picks/featured` | `app/backend/routers/picks.py` | the pending-recap self-heal only wrote back on success, so an unsettled game re-ran a DuckDB-over-S3 query **per anonymous visitor**. Now cooldown-bounded, and skipped entirely in degrade mode |

DynamoDB is confirmed **on-demand (pay-per-request)** on all three tables — no provisioned-capacity
surprise (`infrastructure/aws_resources.md`, "Billing mode" rows).

---

## 7. Recommended alarm threshold

**$250/month**, on both an AWS Budget and a CloudWatch billing alarm.

Why $250:

- Current AWS baseline is dominated by the always-on EC2 box (`r6g.large` ≈ $74/mo + EBS) plus
  small S3/Lambda/DynamoDB lines. The app tier adds **under $1** at 100k visitors (§3).
- $250 therefore sits **comfortably above any organic outcome** — it would not fire at 1 M monthly
  visitors — and **well below the $3,210 abuse case**.
- Time-to-fire matters more than the exact number. The $3,210 scenario burns ~$107/day, so a
  $250 monthly-total alarm over a ~$120 baseline trips **within ~1.2 days** of an attack starting.
  Cost Anomaly Detection (free) fires faster still.

⚠️ **Read the real baseline before committing to the number.** The operator already has it: the
Admin → Finances panel calls Cost Explorer and groups by service. If the trailing-3-month AWS
average is materially above ~$120, scale the threshold to **~2× the trailing average** and keep the
anomaly detector as the fast signal.

Exact commands: see the **G100-D1 spend alarms** section added to
`infrastructure/aws_resources.md`. Two gotchas encoded there and worth repeating:

- 🔴 **The `AWS/Billing` `EstimatedCharges` metric is only published in `us-east-1`.** A billing
  alarm created in any other region watches a metric that does not exist and never fires — a guard
  that cannot fail.
- 🔴 **SNS for this alarm is `us-east-1`.** Do **not** pass `AWS_DEFAULT_REGION=us-east-2`; that is
  the S3 *lakehouse bucket* only. Reuse the existing `credence-prod-alerts` topic so these land in
  the same inbox as every other page.

---

## 8. What this model does NOT cover

Stated so nobody reads a number here as broader than it is.

- **Snowflake.** Billed separately and unaffected by web traffic. Its own cost work is E11.20-COST /
  E11.24 (~80% of the burn is warehouse wake/idle, not query compute).
- **The EC2 Dagster box.** A flat always-on cost independent of visitors; it dominates today's AWS
  bill and nothing in this story changes it.
- **Stripe fees**, which are revenue-proportional.
- **A DDoS**, as distinct from a scraper. The per-IP limiter and the stage throttle bound cost, not
  availability. AWS WAF is not available on HTTP APIs; if real bot protection is ever needed the
  path is CloudFront + WAF in front of the API.
- **Cold-start latency and its UX cost** — a performance question, not a billing one.
