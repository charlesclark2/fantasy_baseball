# E9.8-P2 — Stripe go-live: pre-flip audit, GO/NO-GO, and the operator run-order

**Audit run:** 2026-08-15, against the real prod account (`769392325318`), read-only.
**Instrument:** `scripts/check_stripe_golive_readiness.py` — every finding below is reproducible
by re-running it, and it is the post-flip re-check too.

---

## ⛔ VERDICT: **NO-GO** — one blocking defect, one item only the operator can clear

| | |
|---|---|
| **BLOCKER 1** | The founding-100 counter reads **4**, and all four conversions came from Stripe **TEST** mode. Flipping now silently turns "the first 100 members" into the first 96, and the first real customer is counted as #5. **Not self-correcting** — the counter is never decremented. One DynamoDB write, before the flip. |
| **BLOCKER 2** | The **LIVE Price has not been read**. It cannot be verified from this session (no live key, by design). The `$10` in the story, on `/subscribe`, and in every marketing surface is whatever the live Price object says — nobody has looked at it. Part C step 1. |
| **Everything else** | **GO.** 6 of 8 checks clean, each proven by its denial path rather than by looking enabled. |

Clear both and the gate turns GO. Neither is a code change; both are pre-flip operator steps.

---

## PART A — the audit

### A1. Guardrails: proven to ENFORCE, not to look enabled

The G100-D1 lesson is that *a check whose failure state is indistinguishable from its healthy
state has not been verified*. So each guardrail below was established by its **denial** path.

| Guardrail | State | How it was proven |
|---|---|---|
| **Cost kill switch** | `COST_DEGRADE_MODE` **absent → OFF** | Read from the **flag** (`Environment.Variables.COST_DEGRADE_MODE`), never inferred from an endpoint. ⛔ There is no anonymous probe that could answer this: all 15 `--authorization-type NONE` routes are *also* degrade-allowlisted by design, so a token-free request 401s at the gateway with degrade on **or** off. E9.46 already drew a wrong conclusion from exactly that reasoning. |
| **Degrade allowlist** | resolves against the **real** route table | Two-sided, in-process with the flag on: all 10 sampled floor paths stay UP (`/subscription/public-pricing`, `/stripe/webhook`, `/stripe/create-checkout-session`, `/subscription/status`, `/health`, `/auth/*`, the free board, `/picks/featured`, `/blog/posts`) and all 9 sampled expensive paths are **refused** (`/picks/today`, `/performance/*`, `/bets`, `/portfolio`, `/parlay/*`, `/fantasy/nfl/projections-full`, `/fantasy/nfl/league-board`, `/teams`, `/players/*`). |
| ↳ **RED proof** | non-vacuous | Reintroducing the exact pre-fix G100-D1 defect (`/subscription` → `/stripe/public`) turns `test_the_billing_and_funnel_paths_stay_up_in_degrade_mode` **red**. The guard can fail, so its passing means something. |
| **Billing alarm** | `credence-prod-billing-over-250`, **GO** | Existence is not evidence. Proven on the alarm's **own** dimensions (`AWS/Billing EstimatedCharges {Currency: USD}`): `get-metric-statistics` returns **8 datapoints**, latest **$50.25** at 2026-08-15T20:03Z. `TreatMissingData=missing` ✅ (with `notBreaching` an absent metric would read healthy). `ActionsEnabled=true` → SNS `credence-prod-alerts`. |
| **Public routes** | 15 `NONE`, **GO** | `POST /stripe/webhook` and `GET /subscription/public-pricing` are both `--authorization-type NONE` — the NF3.2 requirement, without which the JWT authorizer 401s them in front of the Lambda regardless of the code's own public-ness. Cross-checked: **every** public route survives degrade mode, so the kill switch cannot black out an anonymous surface or silently drop a payment event. |
| **Rate limiter** | always on | Unchanged from G100-D1; 130 guardrail/billing/MFA tests green. |

⚠️ **Scope, stated because it is easy to over-read:** `AWS/Billing EstimatedCharges` covers **AWS
only**. Vercel and Stripe fees are not in it — Vercel is tracked separately on the admin cost page
(E9.62). The alarm is a **runaway** detector at $250 against ~$50 MTD, not a budget tripwire.

### A2. Subscriber group — the test-mode residue

The `subscriber` group holds **exactly one** account:

| Account | Username | Status | Groups | Stripe customer |
|---|---|---|---|---|
| `charles.t.clark89@gmail.com` | `google_108559353865403184189` (sub `c41874d8-…`) | `EXTERNAL_PROVIDER` | `subscriber`, `…_Google` | `cus_V1Oe9fJycbCWLF` |

⭐ **The story's premise was that this is deliberate. It is not — it is an E9.8 test-mode leftover,
and it DID feed the founding counter.** It carries a Stripe customer id, i.e. it went through a real
(test-mode) Checkout on 2026-08-06 and was promoted by the test-mode webhook, which called
`increment_founding_slots`. Three sibling conversions exist whose Cognito users have since been
deleted, leaving orphaned `__stripe_customer__#` rows:

```
__stripe_meta__#founding        -> slots_used = 4      ← the blocker
__stripe_customer__#cus_V1Oe9fJycbCWLF -> c41874d8-…   (charles.t.clark89, still exists)
__stripe_customer__#cus_UwqEkkLz5xS9xu -> d48814f8-…   (Cognito user deleted)
__stripe_customer__#cus_V0vq0OgDMLBPbH -> d4d8f428-…   (Cognito user deleted)
__stripe_customer__#cus_V1OFsdRSpDl5rm -> d4088438-…   (Cognito user deleted)
__stripe_event__#evt_…  × 4                            (idempotency ledger, harmless)
```

**Why the counter matters and the group does not.** `founding_slots_used()` is what
`_pricing_decision()` reads to choose the $10 Price and what `/subscription/public-pricing` renders
as `founding_slots_remaining` — the public page is **already advertising "96 seats left"** on the
strength of four test transactions. Group membership is a separate question: removing
`charles.t.clark89` from `subscriber` would **not** decrement the counter (deliberately — a freed
slot is never reclaimed).

🪤 **A second, quieter defect in the same rows: Stripe customer ids are MODE-SCOPED.**
`cus_V1Oe9fJycbCWLF` exists only in test mode. `create_portal_session` passes it straight to
`stripe.billing_portal.Session.create`, and `create_checkout_session` reuses it as `customer=` for
a returning user — both of which fail against a live key. So the link must be cleared with the
counter, or the one surviving test-mode account hits a 502 the first time it opens billing.

**Decisions for the operator (both in Part C):**
1. **Reset the counter to 0** — required. Without it the founding promise is quietly founding-96.
2. **Decide whether `charles.t.clark89` keeps `subscriber`** — a PM call, not a blocker. It is the
   operator's own alternate Google account. Note that `subscriber` is the group paid analytics and
   the tier model key on; `fantasy_comp` exists precisely so a comp does not have to sit in it.

`nfepic1-probe@example.com` (`e408d498-…`, NF-EPIC 1 residue, created 2026-08-10) exists but is in
**no groups at all** — so the story's "delete it from `subscriber`" framing is stale; it is not
feeding anything. Deleting it is still right (a fake-domain account in a production pool), and the
command is in Part C.

### A3. MFA lockout re-check (#763) — **nobody is lockable**

The question: is anyone in `subscriber` with a **UUID username** and **no `passwordless` group**?
Such an account is 403'd the moment `ENFORCE_SUBSCRIBER_MFA=1`, and its only self-service exit asks
for a password it may never have had.

**Answer: no.** The single subscriber's username is `google_108559353865403184189`, which
`_username_is_federated` matches against `^(google|signinwithapple|facebook|loginwithamazon)_` →
exemption `federated_username`. It is also `EXTERNAL_PROVIDER`, so it could not enroll TOTP even if
it wanted to — precisely the population that exemption exists for.

The other four `passwordless` members (`ctcb57+r1`, `ctcb57+r2`, `charlie@credencesports.com`,
`ctcb57+leaktest`) are not subscribers, and would be exempt anyway.

- **PR #763 is already MERGED into `dev`** (`b525230a`, "record the backfill census + the go-live
  re-check"). The story's "merge #763 before the flip" item is **closed**.
- The guard's group parser was RED-proved: reverting `parse_groups_claim` to the pre-fix comma-only
  split turns **8** tests red, including `test_a_bracketed_subscriber_is_actually_gated`. The
  bracketed `[subscriber]` form the HTTP API v2 authorizer actually emits is genuinely handled.

### A4. Resting state before the flip

| | Read | Expected | |
|---|---|---|---|
| `STRIPE_SECRET_KEY` | `sk_test_…` | test | ✅ |
| `ENFORCE_SUBSCRIBER_MFA` | absent → OFF | OFF | ✅ |
| `COST_DEGRADE_MODE` | absent → OFF | OFF | ✅ |
| `STRIPE_PRICE_FOUNDING` / `_STANDARD` | both set (test ids) | set | ✅ |
| `STRIPE_WEBHOOK_SECRET` | `whsec_…` | set | ✅ |
| `APP_BASE_URL` | `https://www.credencesports.com` | — | ✅ |
| Lambda | 25 env vars, python3.12, 512 MB, last deployed 2026-08-15T23:47Z | — | ✅ |

### A5. 🚨 A NAME MISMATCH IN THE STORY BRIEF — read this before setting anything

The brief says to set **`STRIPE_WEBHOOK_SIGNING_SECRET`**. **The code reads
`STRIPE_WEBHOOK_SECRET`** (`routers/stripe.py::stripe_webhook`), and that is the name currently on
the Lambda.

Setting the brief's name would leave the real one holding the **test-mode** secret. Every live
delivery then fails signature verification, the handler raises 503 "Webhook not configured", and
**Stripe retries for days** — so cards are charged, `customer.subscription.created` never lands,
nobody is promoted to `subscriber`, and the first symptom is a customer emailing that they paid and
got nothing. Part C uses the code's name. The readiness gate now warns if the wrong name appears.

### A6. Not verifiable from this session — operator must confirm

| Item | Why | Where |
|---|---|---|
| **LIVE Price is genuinely $10/month USD recurring** | needs a live key; the session never touches one | Part C step 1 |
| **Google OAuth consent screen is PUBLISHED** (not "Testing") | console-only setting; in Testing, only allow-listed testers can sign in and everyone else sees "app not verified" | Part C step 0 |
| **`NEXT_PUBLIC_ENFORCE_SUBSCRIBER_MFA` on Vercel** | no Vercel CLI on this machine | Part C step 5 |

---

## PART B — what shipped in this PR

### B1. `infrastructure/lambda/set_lambda_env.py` — the flip tool

`aws lambda update-function-configuration --environment` **replaces the whole `Variables` map**.
One forgotten read wipes `COGNITO_USER_POOL_ID`, `CACHE_BUCKET`, `SNOWFLAKE_PRIVATE_KEY` and 22
others — and **`deploy.sh` will not restore them** (it only calls `update-function-code`; it never
touches the environment). The documented workaround was a hand-rolled heredoc copied into
`aws_resources.md` **twice**, which is this repo's recurring "one logical thing, many owners" shape
(INC-30, INC-36, INC-38): every copy is another chance to paste the update without the read.

Six properties, each closing a way the hand-rolled version fails silently:

1. **Read-modify-write that refuses a bad read** — an empty or failed `get-function-configuration`
   **aborts without writing**. Merging onto `{}` *is* the wipe payload, and an empty read is
   indistinguishable from a permissions failure, so it is a precondition, not a step.
2. **The preservation invariant is asserted** — every pre-existing key must survive byte-identical
   unless named; a key leaves only via an explicit `--unset`.
3. **It verifies after the write** — waits for the asynchronous `LastUpdateStatus` to settle, then
   re-reads and asserts each intended key landed and nothing else moved. Without the wait, a
   verification confirms the **pre-change** state and calls it success.
4. **Secrets never reach argv or stdout** — `--set-env` / `--set-stdin` keep `sk_live_…` out of
   shell history and `ps`; a `--set K=V` that looks like a credential is refused and told the safe
   channel. All output is masked, but keeps the `sk_test_`/`sk_live_` prefix, which is the whole
   question a go-live turns on.
5. **Dry run is the default** — `--apply` is required to write.
6. **A 0600 backup into gitignored `.secrets/`**, with the restore command printed.

Live dry-run against prod: **25 vars in → 26 out, 0 removed, nothing written.**

**16 guard tests, 5 clauses independently RED-proved.** The RED proof caught a genuine defect in its
own first draft: the `preservation_invariant` clause was paired with a test that a *different*
clause was already failing — the NF-D17 vacuous-pairing trap, found mechanically rather than by
eye, and repaired by giving that clause a test that actually reaches it.

### B2. `scripts/check_stripe_golive_readiness.py` — the audit, as an instrument

Part A as a re-runnable gate. A hand-run audit answers "was this true on 2026-08-15"; the operator's
real question comes *after* the flip. Exit 0 = GO, 1 = NO-GO. An **unevaluable check is never scored
healthy** (NF1.7 (a)) — it reports UNKNOWN and, if blocking, it blocks. That rule is RED-proved:
weakening it to `verdict == NO_GO` turns `test_an_unevaluable_blocking_check_blocks` red.

Two-sided on live data: exits **1** on the real founding-counter blocker, **0** when only that
blocker is relaxed. It discriminates.

### B3. E2E pricing fixture

- Re-captured `subscription-public-pricing.json` from prod — byte-identical (`sha 813bdbb756e99e1f`),
  confirming the served price is the unchanged test-mode $10 and the public endpoint is healthy.
- `capture-fixtures.mjs --only <substring>`: the flip changes exactly **one** payload, and a full
  re-capture would rewrite the 378 KB board blobs at the same time — burying a one-line price change
  in an unreviewable diff and re-capturing those at whatever moment the flip lands on.
- ⚠️ A filtered run **merges** provenance instead of replacing it. Writing `provenance` verbatim
  after `--only` would delete the records of the six untouched fixtures, leaving `CAPTURE.json`
  claiming they do not exist while they sit beside it. Each entry now carries its **own**
  `captured_at`, because one header date over files of different vintages hides staleness
  (NF-FRESH2).
- **The go-live price contract is pinned**: $10.00 / USD / monthly / recurring / `tier=founding`,
  asserted against the captured payload. If the post-flip re-capture lands on a mis-provisioned
  live Price, that goes red instead of shipping a wrong number on the page that takes money.

### B4. `nfepic1-probe` + #763

`#763` is already merged. The probe delete is Part C step 2 (it is in no groups, so nothing depends
on it).

---

## PART C — the operator run-order

Run **in order**, all from the **LAPTOP** unless marked. `A()` below is the admin-profile shim used
throughout the audit:

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/e9.8-p2
A() { env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
        aws --profile AdministratorAccess-769392325318 "$@"; }
```

### Step 0 — Google OAuth consent screen (BROWSER, before any traffic)

console.cloud.google.com → **APIs & Services → OAuth consent screen**. Publishing status must read
**In production**. If it reads **Testing**, only allow-listed test users can sign in with Google and
everyone else sees an "app not verified" interstitial — press **Publish app**.

### Step 1 — Provision live keys and READ the live Price (BROWSER + LAPTOP)

In the Stripe dashboard with the **live/test toggle set to LIVE**, create the two Prices and the
webhook endpoint, then confirm the founding Price really is $10:

```bash
# Live restricted/secret key in the shell only — never on a command line.
read -rs STRIPE_LIVE_KEY && export STRIPE_LIVE_KEY

curl -s https://api.stripe.com/v1/prices/<LIVE_FOUNDING_PRICE_ID> \
  -u "$STRIPE_LIVE_KEY:" -d 'expand[]=product' \
  | python3 -m json.tool \
  | grep -E '"(unit_amount|currency|interval|interval_count|livemode|type|name|active)"'
```

**Required:** `unit_amount: 1000`, `currency: "usd"`, `interval: "month"`, `interval_count: 1`,
`livemode: true`, `type: "recurring"`, `active: true`. Repeat for the standard Price (expect
`unit_amount: 2000`). ⛔ **If the founding Price is not exactly 1000, STOP** — every marketing
surface says $10 and `stripe_pricing.resolve()` will render whatever Stripe returns.

**Webhook endpoint (live mode):** URL `https://api.credencesports.com/stripe/webhook`, subscribed to
exactly:

```
checkout.session.completed      customer.subscription.created
customer.subscription.deleted   invoice.payment_failed
price.created  price.updated  product.updated       ← optional (pricing-cache invalidation)
```

⚠️ Test-mode and live-mode endpoints are **separate objects**. Copying the signing secret without
creating the live endpoint means nothing ever arrives. Copy its `whsec_…` for step 4.

### Step 2 — Clear the test-mode residue (BLOCKER 1) — **before the flip**

```bash
# 2a. Reset the founding counter. SET, not ADD — this is an assignment, not an increment.
A dynamodb update-item --table-name credence-prod-dynamo-users --region us-east-1 \
  --key '{"user_id":{"S":"__stripe_meta__#founding"}}' \
  --update-expression 'SET slots_used = :zero' \
  --expression-attribute-values '{":zero":{"N":"0"}}' \
  --return-values UPDATED_NEW

# 2b. Drop the four TEST-mode customer reverse-lookup rows (mode-scoped ids; useless in live).
for C in cus_V1Oe9fJycbCWLF cus_UwqEkkLz5xS9xu cus_V0vq0OgDMLBPbH cus_V1OFsdRSpDl5rm; do
  A dynamodb delete-item --table-name credence-prod-dynamo-users --region us-east-1 \
    --key "{\"user_id\":{\"S\":\"__stripe_customer__#$C\"}}"
done

# 2c. Drop the stale test-mode customer id off the one surviving user row, or their first
#     billing-portal click 502s against a live key.
A dynamodb update-item --table-name credence-prod-dynamo-users --region us-east-1 \
  --key '{"user_id":{"S":"c41874d8-a081-70c2-e5a4-3d9d6d2ea7aa"}}' \
  --update-expression 'REMOVE stripe_customer_id'

# 2d. Delete the NF-EPIC 1 probe account (in no groups; nothing depends on it).
A cognito-idp admin-delete-user --user-pool-id us-east-1_gG9zMbwQt \
  --username e408d498-2011-70b5-8621-e8f3f05b4ad3 --region us-east-1

# 2e. OPTIONAL — PM call. Remove the test-mode leftover from the paid group.
#     `subscriber` is what paid analytics and the tier model key on; `fantasy_comp` is the
#     comp mechanism. Skipping this is fine; it just leaves one comp inside the paid group.
# A cognito-idp admin-remove-user-from-group --user-pool-id us-east-1_gG9zMbwQt \
#   --username google_108559353865403184189 --group-name subscriber --region us-east-1

# 2f. Confirm the blocker is cleared — expect "Founding counter: slots_used=0" and VERDICT: GO.
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  uv run python scripts/check_stripe_golive_readiness.py \
    --profile AdministratorAccess-769392325318
```

### Step 3 — Deploy the backend FIRST, and PROVE the MFA guard is in it (LAPTOP)

**This PR contains no `app/backend/` change**, so the deploy is not for *this* PR. It is for the
flag being flipped in step 4: `ENFORCE_SUBSCRIBER_MFA=1` is only safe if the **running** code
carries the G100-C0-MFA guard — the `passwordless` exemption *and* the bracketed-`[subscriber]`
group parser. Flip it against an older build and the guard reads as enabled while gating **nobody**
(the pre-fix comma-only split matched no group in any observed claim shape).

The API Lambda has **no CD**, so a merged PR is not a deployed build — and FU-1's lesson is that a
flag is not armed until it is proven in the thing that actually runs. Deploy, then read the marker:

```bash
./infrastructure/lambda/deploy.sh

# Prove the deployed build carries the guard. Sign in at www.credencesports.com, copy the
# `authorization` request header from any API call in devtools → Network, then:
TOKEN='eyJ...'
curl -s -H "Authorization: Bearer $TOKEN" \
  https://api.credencesports.com/auth/session-diagnostics | python3 -m json.tool
```

**Required: `"guard_version": "g100-c0-mfa/1"`.** Anything else (or a 404) means the deployed build
predates the guard — **stop and re-deploy**. The same response reports `mfa_enforced`,
`totp_exempt` and `totp_exempt_reason`, which is what makes step 7's MFA leg answerable rather than
guessed.

### Step 4 — Flip the Lambda env, in ONE update (LAPTOP)

⚠️ Use the code's variable name `STRIPE_WEBHOOK_SECRET` — **not** the brief's
`STRIPE_WEBHOOK_SIGNING_SECRET` (see A5).

```bash
# Secrets into the shell only — `read -rs` echoes nothing and keeps them out of history.
read -rs STRIPE_SECRET_KEY   && export STRIPE_SECRET_KEY      # sk_live_…
read -rs STRIPE_WEBHOOK_SECRET && export STRIPE_WEBHOOK_SECRET  # whsec_… from step 1

# DRY RUN first — writes nothing. Check the diff says sk_test_ -> sk_live_ and "0 removed".
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  uv run python infrastructure/lambda/set_lambda_env.py \
    --profile AdministratorAccess-769392325318 \
    --set-env STRIPE_SECRET_KEY \
    --set-env STRIPE_WEBHOOK_SECRET \
    --set STRIPE_PRICE_FOUNDING=<LIVE_FOUNDING_PRICE_ID> \
    --set STRIPE_PRICE_STANDARD=<LIVE_STANDARD_PRICE_ID> \
    --set ENFORCE_SUBSCRIBER_MFA=1

# Then re-run the IDENTICAL command with --apply appended.
```

All five keys go in **one** update on purpose: a live key must never be live in the function
separately from the live price ids or the live webhook secret. The tool waits for the async update,
re-reads, and confirms every key landed with nothing else moved.

```bash
unset STRIPE_SECRET_KEY STRIPE_WEBHOOK_SECRET   # don't leave them in the shell
```

### Step 5 — Frontend MFA flag (VERCEL DASHBOARD)

Set `NEXT_PUBLIC_ENFORCE_SUBSCRIBER_MFA=1` (Production).

🪤 **Then redeploy with "Use project's Ignore Build Step" UNTICKED.** An env-var change does not
change git, so a plain Redeploy re-diffs the same commit; if that commit did not touch `frontend/`
the ignore step exits 0, the build is skipped, and **the new variable never takes effect with no
error** — the site just serves the old build. See `docs/vercel_build_skipping.md`.

### Step 6 — Post-flip verification (LAPTOP)

```bash
# The gate, re-aimed at the post-flip expected state. Expect VERDICT: GO.
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  uv run python scripts/check_stripe_golive_readiness.py \
    --profile AdministratorAccess-769392325318 --expect-mode live --expect-mfa on

# The public price now reads from the LIVE Stripe Price. Expect 1000 / usd / month / founding,
# and founding_slots_remaining = 100.
curl -s https://api.credencesports.com/subscription/public-pricing | python3 -m json.tool

# Re-capture the fixture onto the live shape, then let the pinned contract check it.
cd frontend && node e2e/fixtures/capture-fixtures.mjs --only subscription-public-pricing && cd ..
uv run pytest betting_ml/tests/test_e9_8_p2_lambda_env_helper.py -q -k GoLivePriceContract
```

### Step 7 — 🟥 THE RUNTIME GATE (the DoD): one REAL founding checkout

CI mocks all IO; none of the above is evidence that money moves. Do this with a **real card**, on a
**non-subscriber account**:

1. Sign up fresh → `/subscribe` shows **$10** and "100 founding seats left".
2. Check out. **Founding price charged** ($10.00, not $20).
3. Webhook lands → the account is in `subscriber`:
   ```bash
   A cognito-idp admin-list-groups-for-user --user-pool-id us-east-1_gG9zMbwQt \
     --username <new-sub> --region us-east-1 --query 'Groups[].GroupName'
   ```
4. **Counter incremented exactly once** — `slots_used = 1`, not 2. Then **replay the event from the
   Stripe dashboard** and confirm it is *still* 1 (that is the idempotency gate, and a replay is
   the only way to see it work):
   ```bash
   A dynamodb get-item --table-name credence-prod-dynamo-users --region us-east-1 \
     --key '{"user_id":{"S":"__stripe_meta__#founding"}}'
   ```
5. **MFA enforced** — the new subscriber is a password/UUID account, so a paid endpoint must 403
   until TOTP is enrolled, then 200 after. (`GET /auth/session-diagnostics` reports which signal
   decided, if it does not behave as expected.)
6. **Cancel revokes** — cancel in the billing portal; `/subscription/status` should immediately show
   `cancel_at_period_end: true` with an access-ends date, and access should persist until then.
   Access is dropped only when `customer.subscription.deleted` actually fires at period end.
7. **Beta bypass intact** — a `beta_tester` still has access and `POST
   /stripe/create-checkout-session` returns **409**, so a beta user can never be charged.
8. **Telemetry** — the funnel fires end to end:
   ```bash
   uv run python scripts/diagnose_posthog_funnel.py
   ```
   Expect `user_signup_completed → checkout_started → subscription_started`.
   ⏳ **Respect the grace window.** PostHog's client-batch → ClickHouse path runs 3–5 minutes, so a
   zero read seconds after the walk is **lag, not a miss** — and in a multi-step redirect flow the
   *start* event lands in an earlier batch than the *complete*, so a perfectly healthy funnel
   transiently shows started-without-completed. The script's `LIVE_EDGE_SECONDS = 300` already
   encodes this; do not re-derive a scarier reading from a fresher query.

### Step 8 — Changelog (only AFTER step 7 passes)

This PR ships **no** changelog entry, deliberately: it is tooling, docs and one byte-identical
fixture re-capture, and announcing paid subscriptions before the flip would be untrue. Add the entry
once a real checkout has cleared:

```json
{
  "tag": "added",
  "text": "Memberships are open. The first 100 members pay $10/month, locked in for as long as the membership stays active; after that it's $20. You can cancel any time from Settings — access runs to the end of the period you've already paid for, and the page tells you the exact date rather than leaving you guessing."
}
```

🪤 Put it in the block whose `week` is the **Monday of the week you flip**. If that block already
exists, **merge the item into it** — a second block with the same Monday fails
`betting_ml/tests/test_changelog_guard.py`, and this exact same-week collision has bitten twice
(E5.9 / NF-C6P2). `frontend/` auto-deploys on push to `main`.

### Rollback

`set_lambda_env.py` prints a `.secrets/lambda-env.*.json` restore command on every `--apply`. To
revert billing alone, re-run step 4 with the test values. Delete the backup once confirmed:
`rm .secrets/lambda-env.*.json`.

---

## What this story deliberately did NOT do

- **No live key was touched.** The session read `sk_test_`'s first 8 characters and nothing else.
- **No flag was flipped, no group changed, no counter written.** Every AWS call in the audit is a
  read; the two mutating tools ship dry-run-by-default and were only ever run dry.
- **The live Price was not verified** — it cannot be without a live key. It is Part C step 1 and one
  of the two things standing between this and GO.
