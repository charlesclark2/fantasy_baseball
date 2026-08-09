# G100-D0 — Funnel telemetry and the founder daily dashboard

**Status:** shipped (instrumentation). Dashboard provisioning is an operator step — see §6.
**Scope:** measurement only. No user-facing copy, no claim. `best_alpha = 0`.

---

## 1. The decision: a PostHog dashboard, provisioned from a versioned spec

The story offered two homes for the founder dashboard — a PostHog dashboard, or an in-app panel
extending E9.21's "PostHog in Admin" base. **This ships the PostHog dashboard**, defined by
`scripts/provision_posthog_funnel_dashboard.py` and reviewed in this repo.

Four reasons, in order of weight:

1. **E9.21 does not exist to extend.** The roadmap records it as
   *"E9.21 PostHog admin metrics DEFERRED (only matters once there are users to measure)"*. The
   in-app option is therefore not "extend a panel", it is "build an admin surface, put a PostHog
   personal API key in the Lambda environment, and `deploy.sh`" — a materially bigger change with a
   new long-lived credential, for an internal read.
2. **G100-D1 just spent a story getting per-view Lambda work off the acquisition path.** Adding a
   new endpoint that calls the PostHog Query API on every panel render is the same shape pointing
   the other way. It is admin-only, so the blast radius is small — but the upside is zero.
3. **Cohort funnels, breakdowns and retention are free in PostHog and expensive to re-implement.**
   The rates below need conversion *windows* and person-level de-duplication across sessions;
   PostHog computes both natively.
4. **The definitions still live in the repo.** Provisioning from a versioned spec means the
   numerator and denominator of every metric is a reviewable diff, which is the actual thing an
   in-app panel would have bought. A dashboard clicked together in a UI is not.

**Consequence for deploys:** this story ships **no backend change**, so
`./infrastructure/lambda/deploy.sh` is **not required**. Instrumentation is frontend only and rides
the normal Vercel deploy on merge to `main`.

---

## 2. The event contract

Six events form the spine. Names are a contract between `frontend/lib/funnel-telemetry.ts`, this
document, and the provisioning script; `betting_ml/tests/test_g100_d0_funnel_telemetry.py` fails if
they drift apart. ⛔ Do not rename one without the others.

| # | Event | Fired where | New in D0? |
|---|---|---|---|
| 1 | `landing_view` | `<LandingView/>` on the four acquisition surfaces | ✅ new |
| 2 | `user_signup_completed` | `/callback`, when the round-trip began with signup intent | E9.58 |
| 3 | `league_config_completed` | manual editor **and** import, `method` separates them | G100-C1 |
| 4 | `custom_board_viewed` | `/fantasy/my-league`, when the board actually renders — **ACTIVATION** | G100-C1 |
| 5 | `checkout_started` | `/subscribe`, immediately before the redirect to Stripe | ✅ new |
| 6 | `subscription_started` | `/subscribe/success`, once the webhook has granted access | ✅ new |

`user_signup_started` (E9.58) is also emitted and is useful for diagnosing the OAuth round-trip
(started vs completed), but it is not a spine step.

### Acquisition surfaces

`landing_view`'s population **is** the denominator of visitor→signup, so what counts as an
acquisition surface is a product decision made per page, not a pathname regex:

`/` · `/fantasy/rankings` · `/fantasy/projections` · `/fantasy/player/[playerId]`

⛔ **`/subscribe` and `/login` are deliberately excluded.** Both are public; neither is acquisition.
One is the conversion surface, the other a return path. Counting people who are already deep in the
funnel as fresh visitors is the cheapest available way to manufacture a conversion problem that is
not there.

### Dimensions

Registered as PostHog **super properties**, so they ride on every event including the ones fired
days later on the far side of a signup — which is what makes "activation rate by acquisition
source" answerable at all.

| Property | Semantics |
|---|---|
| `acquisition_source` | **First touch, forever.** `utm_source`, else the external referrer host, else `direct`. An *internal* referrer is dropped, never recorded. |
| `campaign` | First touch `utm_campaign`, else `null`. |
| `referrer` | First touch external referrer host, else `null`. |
| `device` | `mobile` / `tablet` / `desktop`, from the **viewport** (Tailwind `sm`/`lg` boundaries), re-read per navigation. |
| `free_paid_status` | `anonymous` / `free` / `paid` / `comped`. |

⭐ **`comped` is a separate value on purpose.** `admin`, `beta_tester` and `fantasy_comp` all have
full access and have paid nothing. Folding them into `paid` would put the operator's own account —
and every beta tester — into the numerator of the metric this whole sprint is judged on. At launch
scale that is not a rounding error; it is most of the numerator.

### Identity stitching

`posthog.identify(email)` runs at `onLoginSuccess` (`lib/auth-context.tsx`) **and** whenever a
restored session produces an email (`components/funnel-telemetry.tsx`). The first covers the signup
round-trip — the case that joins an anonymous `landing_view` to the account it produced. The second
covers a returning visitor, who has no login event at all: PostHog persists the identified id, so
they are usually still stitched, right up until they clear storage or open the product on a second
device, at which point one human becomes two people and every rate below is wrong in both
directions.

---

## 3. The three rates — numerator and denominator

**Every metric counts DISTINCT PERSONS, never events.** This is not a stylistic preference. It is
the correctness risk G100-C1's live testing surfaced: `custom_board_viewed` fires once per page
mount by design, and one real user produced **three in an hour**. An activation rate on event
volume is inflated by revisits, and an inflated activation rate reads as a *conversion* problem —
sending the next story to fix pricing when nothing is wrong with pricing.

### R1 — visitor → signup

| | |
|---|---|
| **Denominator** | distinct persons with ≥1 `landing_view` |
| **Numerator** | distinct persons with ≥1 `user_signup_completed` |

⚠️ **A "visitor" is a PostHog *person*, not a human.** For an anonymous browser that is a
device-plus-storage identity: one human on a phone and a laptop is two visitors; one human who
clears cookies is two visitors. It is a de-duplicated *session identity*, and it is the best
available anonymous unit — but it is an over-count of humans, so R1 is a **floor** on the true
visitor→signup rate.

⚠️ **`user_signup_completed` is not `account_created`.** It means *"clicked a Sign-Up affordance,
completed the OAuth round-trip, and now has a session"* — which **includes a returning user who
happened to click Sign Up**. That is the right denominator for a funnel *step* and the wrong number
for counting new accounts. **New-account counts come from Cognito user creation dates**, not from
this event. If the two disagree, Cognito is right.

### R2 — signup → ACTIVATION

| | |
|---|---|
| **Denominator** | distinct persons with ≥1 `user_signup_completed` |
| **Numerator** | distinct persons with ≥1 `custom_board_viewed` |

Activation is G100-C1's conjunction: `account_created AND league_config_completed AND
custom_board_viewed`. The funnel uses `custom_board_viewed` as the marker because it is the
conjunction's *terminal* clause — it is unreachable without a saved league, and a signed-out visitor
cannot produce one.

⚠️ **That equivalence holds because of how the app is built, not by definition.** If a future story
ever renders a personalised board without a saved league, this stops being true and the dashboard
needs the explicit three-way intersection. The funnel insight in §4 carries
`league_config_completed` as its own step, so a divergence between step 3 and step 4 is visible
rather than assumed away.

⚠️ **`league_config_completed` fires only on a CREATE.** Both doors (manual editor, import) emit it,
separated by `method`; a re-import that refreshes a roster deliberately does **not** re-count. This
is the one activation clause with **no production evidence yet** — it must be confirmed on the wire
the first time a genuinely new account configures a league (see §7).

### R3 — ACTIVATION → paid

| | |
|---|---|
| **Denominator** | distinct persons with ≥1 `custom_board_viewed` — **activation is the paid denominator** |
| **Numerator** | distinct persons with ≥1 `subscription_started` |

⚠️ **`subscription_started` is a floor, not a count of revenue.** It fires on the post-checkout
screen once `/subscription/status` reports `has_access` — i.e. once the Stripe *webhook* has
actually granted the group, which is the first honest moment. But it is client-confirmed: a visitor
who closes the tab during the 2–24 s provisioning poll pays us and is never counted. **Stripe is
the source of truth for paid counts**, exactly as Cognito is for new accounts. This event is the
funnel's paid *step* — the thing you can attribute to a source and intersect with activation.

A lossless number is available if it is ever wanted: capture server-side from the Stripe webhook in
`app/backend/routers/stripe.py`, keyed on the same email `identify()` uses. Deliberately not done
here — it would put a new network dependency inside the webhook path for a launch-scale metric that
Stripe already reports.

---

## 4. What the dashboard contains

`scripts/provision_posthog_funnel_dashboard.py` creates one dashboard, **"G100 — Founder daily
funnel"**, with five insights:

1. **Funnel — full spine (7-day conversion window).** All six events in order, person-level. This
   is the **cohort-correct** reading of the three rates: a person is counted at step *n+1* only if
   they reached step *n* first, within the window.
2. **Funnel — by acquisition source.** The same funnel, broken down on `acquisition_source`.
3. **Daily distinct persons per step.** Six series, each unique-persons-per-day. This is the
   "what happened today" table.
4. **Daily conversion rates (R1, R2, R3).** Ratios of the daily unique-person counts.
5. **Activation → paid, by device and free/paid status.** Where the drop-off differs by segment.

⚠️ **Insight 4 is a SAME-DAY RATIO, NOT a cohort conversion**, and the difference matters: its
numerator and denominator are different people. Somebody who signs up today may have landed a week
ago, so on any day the ratio can exceed the true conversion rate, or fall below it, purely from
traffic shape. It is the right instrument for *trend* ("is today unusual?") and the wrong one for
*level* ("what fraction of visitors convert?"). **For level, read insight 1.** Each tile's
description states this; do not delete those descriptions.

⚠️ **The trailing days of insight 1 are incomplete by construction** — a 7-day conversion window
means the last week's cohorts have not finished converting. A downward slope at the right-hand edge
is the window, not a regression.

---

## 5. What is deliberately NOT instrumented

The roadmap's D0 event list is longer than the spine. These are omitted, and the reason is the same
each time: **do not chart a metric that is not emitted, and do not emit one nobody reads.**

| Event | Why not |
|---|---|
| `rankings_scroll_depth` | High volume, no decision attached to it yet. Adds ingest cost for a number nothing would change. |
| `player_open`, `customize_clicked` | Intra-page engagement, not funnel steps. Worth adding when there is a question about *which* free surface converts. |
| `optimizer_preview` | The surface does not exist. |
| `share_generated`, `share_clicked` | G100-G0's events; nothing generates a share yet. |
| `auth_provider_selected` | Google is currently the only working provider (see `lib/access.ts` — native password registration is a deliberate dead end), so the dimension has one value. Becomes meaningful at G100-C0. |

`league_import_started` / `league_import_completed` **are** emitted (G100-C1) and carry
`league_platform`; they are diagnostics for the import funnel rather than spine steps.

---

## 6. Operator: provisioning the dashboard

**Where:** LAPTOP. Needs the numeric project id (PostHog → Settings → Project) and a **personal API
key** (PostHog → Settings → Personal API keys) carrying **exactly two scopes**:

| Scope | What needs it |
|---|---|
| `dashboard:write` | `POST /api/projects/{id}/dashboards/` — creating the dashboard |
| `insight:write` | `POST` / `PATCH /api/projects/{id}/insights/` — creating and updating each insight |

⭐ **The `:read` scopes are NOT needed, and adding them grants nothing extra.** The script also lists
dashboards and insights (to be idempotent), which derives `dashboard:read` / `insight:read` — but
PostHog's `APIScopePermission` accepts the `:write` scope wherever a `:read` is required
(`posthog/permissions.py`: *"For all valid scopes with :read we also add :write"*). Two scopes is the
minimum, not a shortcut.

⛔ **It does NOT need `query:read`, `event:read` or `person:read`** — worth stating because
`query:read` is the one you would expect. This script only writes insight *definitions*; the queries
execute when a human opens the dashboard, under their own session auth. The key never reads an event
or a person.

Two hardening steps, both cheap:

- **Scope the key to this one project.** A key's project restriction is independent of its scope
  list, so set it to the single project rather than "all projects" — a leaked key then cannot reach
  another project even within those two scopes.
- **Delete the key once the dashboard exists.** It is used once, at provisioning; nothing in the
  shipped app holds it, and no read path needs it. Re-issuing later is a 30-second job.

⚠️ If a scope is short the failure names itself — PostHog answers
`API key missing required scope '<scope>'`, which the script surfaces verbatim rather than as a bare
`HTTP 403`. `--dry-run` needs no key at all.

Review the payloads first — this never writes on a dry run:

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/g100-d0 && \
  uv run python scripts/provision_posthog_funnel_dashboard.py --dry-run
```

Then create it:

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/g100-d0 && \
  POSTHOG_PERSONAL_API_KEY='phx_…' \
  POSTHOG_PROJECT_ID='12345' \
  uv run python scripts/provision_posthog_funnel_dashboard.py --apply
```

Re-running is safe: an insight whose name already exists on the dashboard is **updated**, not
duplicated (`--apply` matches on name). Add `--host https://eu.posthog.com` for an EU project.

---

## 7. Operator: the runtime verify (post-merge)

CI proves the events leave the page under the right names
(`frontend/e2e/specs/funnel-telemetry.spec.ts`, driving the real rendered app against an
intercepted ingest endpoint). It cannot prove they arrive in *your* PostHog project. Walk the real
funnel on production once, with PostHog's **Activity → Live events** view open:

1. Open `credencesports.com/?utm_source=verify&utm_campaign=g100d0` in a **fresh private window**.
   → `landing_view` (`surface: home`), carrying `acquisition_source: verify`,
   `campaign: g100d0`, `free_paid_status: anonymous`.
2. Navigate to `/fantasy/rankings`. → a second `landing_view` (`surface: fantasy_rankings`) **still
   carrying `acquisition_source: verify`** — this is the first-touch super property working. If it
   reads `direct` or `credencesports.com`, attribution is broken.
3. Sign up with a **genuinely new** Google account. → `user_signup_started`, then
   `user_signup_completed`. Confirm in PostHog that the anonymous events from steps 1–2 are now on
   the **same person** as the identified one — that is the stitch, and it is the single thing that
   would silently double-count every visitor if it failed.
4. Configure a league (either door). → ⭐ **`league_config_completed`, with `method`.** This is the
   clause with no production evidence; this step is the whole reason the walk is worth doing.
5. Open `/fantasy/my-league` and let the board render. → `custom_board_viewed`, exactly once.
   Reload it. → a second event, **same person** — confirm the dashboard still shows **one**
   activated person. If activation counts 2, a metric is counting events.
6. Click Subscribe. → `checkout_started`. Complete or abandon the Stripe form as you prefer;
   completing gives you `subscription_started` on the success screen once access lands.

Then confirm the dashboard populates and that step 5's reload did not move the activation count.
