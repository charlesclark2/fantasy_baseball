# NF-INC-0917B — operator handoff

Written for: **Charlie (operator)**, to run in order.

Spec: `plan_specs/nfl_fantasy/nf-inc-0917b.yaml`. Branch `nf-inc-0917B`, PR → `dev`.
Parent incident: `plan_specs/nfl_fantasy/nf-inc-0917.yaml` (PRs #1143 / #1144 / #1145).

---

## What was wrong, in three lines

The weekly builder called `NflWeeklyManifest.model_validate(manifest)`, **discarded the result**, and
wrote the raw input dict. `framing` is declared REQUIRED **with a default**, so validating a dict
that omits it *passes* — the default lands on an object nobody keeps. A declared field, a passing
validation, and nothing on the wire. `/fantasy/weekly` then died on `framing.interval_note` for 758
minutes, and the served manifest is **still** short of nine declared fields as of this writing.

`best_alpha = 0`. No model, number or value changes — only the payload's completeness against its
own declaration.

---

## What changed

| half | file | ships via |
|---|---|---|
| builder serialises the validated model | `quant_sports_intel_models/football/nfl/fantasy/run_weekly_serving.py` | **box CD** on merge to `main` |
| write-path gate (`assert_contract_shaped`) | same file | same |
| route `response_model` + coercion | `app/backend/routers/fantasy.py`, `app/backend/models/nfl_weekly.py` | **`deploy.sh`** (manual) |
| CSP `worker-src` | `frontend/next.config.mjs` | **Vercel**, on merge to `main` |

⚠️ **Three different pipes, and none of them is the others.** Merging to `dev` deploys nothing.

---

## ⭐ STEP 1 — merge the PR to `dev`, then promote `dev` → `main`

The promotion is what moves the builder half (box CD) and the CSP line (Vercel). The `#1139` hold
that the spec was written around **is already discharged** — #1139 merged 2026-09-16T05:32:17Z, and
the NF-INC-0916 session has closed. Verified by content rather than by merge status:

```bash
# LAPTOP, repo root. Read-only, instant.
git fetch origin
git show origin/main:quant_sports_intel_models/football/nfl/fantasy/run_weekly_serving.py | grep -c "NF-INC-0916"   # expect 2
git show origin/main:frontend/lib/weekly-suppression.ts | grep -c 'WEEKLY_NUMBERS_WITHHELD = true'                  # expect 1
```

⚠️ `main` is currently **3 commits ahead of `dev`** (#1139's merge commit, #1145, and its record
commit). Merge `main` into `dev` before the promotion, or the promote PR will show a confusing diff.

**After the promotion, verify `main` actually carries this change** — a long-open `dev → main` PR can
merge an earlier `dev` snapshot with every signal green:

```bash
# LAPTOP, repo root. Read-only, instant.
git fetch origin
git show origin/main:quant_sports_intel_models/football/nfl/fantasy/run_weekly_serving.py \
  | grep -c "manifest = C.NflWeeklyManifest.model_validate(manifest).model_dump()"   # expect 1
git show origin/main:frontend/next.config.mjs | grep -c "worker-src"                  # expect 2 (comment + directive)
git rev-list --count origin/main..origin/dev                                          # expect 0
```

---

## STEP 2 — the box republishes BY ITSELF

`orchestration_cd.yml` path-filters `quant_sports_intel_models/football/nfl/fantasy/**`, so merging
to `main` rebuilds and deploys the box image, and the next **`sports_nfl_weekly_serving_schedule`
fire (daily, 08:30 PT)** publishes a complete manifest. **Nothing to run by hand.**

If you want it sooner, run the publish from a checkout of **merged `dev`** (⛔ never from the story
branch — the standing publish-from-merged-`dev` rule):

```bash
# LAPTOP, repo root, on merged dev. ~9 min. Writes PRODUCTION S3 (the live api-cache).
AWS_DEFAULT_REGION=us-east-2 uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_weekly_serving \
  --s3-bucket credence-prod-s3-api-cache --publish
```

Success looks like a new `[METRIC] weekly_contract_fields_checked=` line (the gate reporting how
many declared fields it examined — a gate that examined nothing has not passed) and a published
manifest for the target week.

**Then confirm the wire, which is the only statement that matters here:**

```bash
# LAPTOP. Read-only, instant. Expect: missing=[] and a non-empty interval note.
curl -s "https://www.credencesports.com/api/public/weekly-manifest?season=2026&cb=$(date +%s)" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); \
req=['season_type','scoring_system_id','interval_lo_level','interval_hi_level','ros_basis', \
'ros_sigma_lo_level','ros_sigma_hi_level','positions','framing']; \
print('missing=', [k for k in req if k not in d]); \
print('interval_note=', (d.get('framing') or {}).get('interval_note','')[:60])"
```

⚠️ The CDN entry is `s-maxage=900`, so allow up to 15 minutes, or keep the cache-buster.

---

## STEP 3 — `deploy.sh` for the route half

The route half is independent of the box and does **not** ride the promotion:

```bash
# LAPTOP, repo root, on merged dev. ~2 min. Deploys the PRODUCTION API Lambda.
./infrastructure/lambda/deploy.sh
```

⭐ **Worth doing FIRST if you want the page whole today**: the route coercion completes the manifest
from the blob **already sitting in S3**, so it fixes the wire without waiting for a republish. The
same STEP 2 `curl` verifies it.

⚠️ `deploy.sh` calls `aws lambda wait`, which needs `lambda:GetFunctionConfiguration` — use the admin
profile, not `baseball-access-user`.

---

## STEP 4 — the Sentry notification rule (UI, ~3 minutes)

⚠️ **I have no Sentry access, so none of this is verified — it is a configuration to apply and then
prove, not a report of something already working.** The proof step is at the bottom and is the part
that matters: an alert rule nobody has seen fire is the same class of thing as the guard that was
green through this whole outage.

**Org `credence-sports` · project `javascript-nextjs` · Alerts → Create Alert → Issues.**

Create **two** rules, because they answer different questions:

### Rule 1 — "New client error on a serving route" (the one that would have caught this)

| field | value |
|---|---|
| WHEN | `A new issue is created` |
| IF | `The event's environment equals production` |
| IF | `The event's level equals error` |
| THEN | Send a notification to **your email** (and Slack if wired) |
| Action interval | `5 minutes` |
| Rule name | `New client error (production)` |

⭐ **`A new issue is created` is the whole fix.** This outage produced its first Sentry event at
**15:33Z** and was found by a human opening the page at **~03:47Z the next morning** — 12.6 hours
later. A first-seen rule turns that into minutes, and it does not care about volume at all.

### Rule 2 — "A client error is recurring" (the trickle net)

| field | value |
|---|---|
| WHEN | `The issue is seen more than 4 times in 1 hour` |
| IF | `The event's environment equals production` |
| THEN | Send a notification to **your email** |
| Action interval | `1 hour` |
| Rule name | `Recurring client error (production)` |

⛔ **DO NOT use a percent-change / spike rule here, and this is the load-bearing instruction.** The
options Sentry offers by default (`…is seen more than X% more than in the last hour`, issue-velocity
alerts) are built for traffic spikes. **This outage was a low, steady trickle for 12.6 hours** — a
page nobody was looking at, erroring at whatever rate people wandered onto it. Against a flat rate
from the very first event there is no percentage increase to detect, so a spike rule plausibly never
fires at all. An **absolute low count** is what sees a quiet page that is completely broken.

⚠️ `4 times in 1 hour` is deliberately low. If it turns out to be noisy, raise it — but raise it
having seen the noise, not in anticipation of it. A monitor tuned for silence before it has ever
spoken is the one that gets muted later.

### 🔬 Prove each rule fires — do not skip this

1. Open **Alerts → the rule → Preview** if your Sentry plan offers it: it replays recent issues and
   tells you how many would have triggered. A preview of **0 over the last 14 days** on Rule 1 means
   the environment/level filters do not match your real events — the commonest cause is `environment`
   not being set on the client (check an existing event's tags before trusting the filter).
2. Then fire a real one. In a **production** browser console:
   `Sentry.captureException(new Error("NF-INC-0917B alert rule smoke test"))`
   — expect an email within the action interval. **Label it as a smoke test in the message**, which
   is the INC-39 lesson: an unlabelled synthetic alert costs an incident response, and a real one
   that shares its dedup slot is suppressed for the window.
3. If nothing arrives, check **Settings → Notifications** before re-editing the rule: a correct rule
   with notifications muted looks exactly like a broken rule.

---

## STEP 5 — the two open verifications from the parent incident

### (a) Sentry last-seen vs the restoring deploy — *nearly closed*

PR #1145 recorded a captured event at **2026-09-16T03:47:19Z**, which is already **before** the
restoring deployment `6473589545` at **04:10:44Z**. What it did not state is whether that is the
issue's **last** event, which is the actual claim.

**Open the issue and read the `Last seen` field.** Expect it to be at or before 04:10:44Z and to have
stopped advancing. If it is still advancing, the fix did not take and that is a P1 — but note the
page was verified restored by content at 04:11Z, so the expected answer is "stopped".

⚠️ While you are there: confirm the issue has **no replay attached** (it will not — that is what the
CSP line fixes) and then, **after the frontend deploys**, open `/fantasy/weekly` in production, force
an error, and confirm a replay **does** attach. That is the only way to know the `worker-src` line
worked; it has no server-side signal.

### (b) The combined-page copy review — **now possible, and it needs your eye**

This one has never been looked at, because the two pieces of copy have never rendered together.
`WEEKLY_NUMBERS_WITHHELD = true` is live on `main`, so the page now shows **the INC-0916 suppression
notice** (we have taken this week's numbers down) and, until the corrected manifest publishes, **the
INC-0917 framing-absence panel** (the measurement notes are not in this payload).

They are **different facts** and both are honest. The question is whether they read as *two
apologies where one honest sentence would do* — a reader meeting both may conclude the product is
broken in two ways rather than that one build is being withheld while one caveat block is missing.

⭐ **The reason this is a judgment call and not a fix:** the two have different lifetimes. The
framing absence disappears the moment STEP 2's republish lands; the suppression lifts only on your
verdict-table read (card `VicWAoZl`, NF-INC-0916 node 4). So merging them into one sentence would
produce copy that is wrong as soon as either half resolves — which is why this session has **not**
merged them and is handing you the look instead.

```bash
# LAPTOP. Open in a real browser, cache-busted. Read both panels together.
open "https://www.credencesports.com/fantasy/weekly?cb=$(date +%s)"
```

⛔ Do **not** verify this with `curl | grep`: the weekly table is client-rendered and React escapes
apostrophes, so a grep of the served HTML reports a healthy page as broken (the NF-INC-0916 node-0
false-RED, already recorded).

If it reads as two apologies, the cheapest honest fix is a single ordering/lead-in change on the
page, carded rather than done here — this session has no basis for a copy decision the PM owns.

---

## What this does NOT do, stated plainly

- **It does not change a single projected number.** Measured on the real published artifacts: the
  coercion adds 9 manifest fields + 4 in `lineage` + `scoring_system_id` on the players blob, removes
  nothing, and changes no value on any of 500 rows.
- **It does not un-suppress anything.** NF-INC-0916 node 4 is yours and is untouched here.
- **It does not fix the other 15 pass-through routes.** They are a report-only census in the spec's
  `closeout.followUps` for PM triage, not work done in this story.
