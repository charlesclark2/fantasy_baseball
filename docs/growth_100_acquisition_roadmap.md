# GROWTH-100 — First 100 Fantasy Subscribers
## Three-Week Customer Acquisition and Conversion Roadmap

**Execution window:** August 7–28, 2026  
**Primary business objective:** Build a repeatable acquisition → activation → paid conversion loop capable of reaching the first 100 fantasy subscribers before the NFL regular season  
**Primary acquisition wedge:** Free preseason draft rankings and one personalized league experience  
**Paid value proposition:** Decision support across the draft and regular season  
**Operating constraint:** Self-funded business; infrastructure and external API costs must remain bounded and measurable  
**Product context:** Season/draft model and weekly projection model already exist; this epic should prioritize distribution and conversion rather than new predictive-model work

---

# 1. Executive Decision

For the next three weeks, Credence should treat customer acquisition as a product launch program, not as a marketing side project.

The strategic funnel is:

```text
Public fantasy content
        ↓
Free Credence rankings
        ↓
"Customize for my league"
        ↓
Free account
        ↓
League import / configuration
        ↓
Personalized draft board
        ↓
Decision-support paywall
        ↓
Paid subscriber
        ↓
Weekly product retention
```

The core freemium distinction should be:

> **Free tells the user what Credence thinks. Paid helps the user decide what to do.**

## Public / Anonymous

- Generic preseason rankings.
- Generic player projections.
- Selected uncertainty information.
- ADP/reference comparisons.
- Public methodology and track record.
- Basic player pages.

## Free Account

- One imported/configured fantasy league.
- League-specific scoring.
- Personalized draft board.
- Limited VOR/customization.
- Saved league/team state.
- Limited weekly preview after the draft.

## Paid

- Draft optimizer / pick recommendations.
- Full league-specific VOR and decision layers.
- Multiple leagues.
- Full weekly projections.
- Start/sit and matchup optimization.
- Waiver recommendations.
- Trade tools as they become available.
- Advanced simulations and future WAR-style metrics.

The goal is not to maximize August paywall coverage. The goal is to maximize qualified acquisition → activation → measurable conversion → weekly retention without allowing free-user infrastructure cost to become unbounded.

---

# 2. North-Star Metrics

## Primary Growth KPI

```text
PaidConversionFromActivatedLeague
= Paid Subscribers / Users Who Completed League Import or Configuration
```

## Supporting Funnel Events

```text
landing_page_view
rankings_view
player_page_view
signup_view
signup_started
signup_completed
league_import_started
league_import_completed
custom_board_viewed
draft_optimizer_viewed
draft_optimizer_used
checkout_started
subscription_started
share_generated
share_clicked
weekly_preview_viewed
```

## Cost Metrics

Track at minimum:

```text
incremental infra cost / anonymous visitor
incremental infra cost / registered user
incremental infra cost / league import
incremental infra cost / activated user
incremental infra cost / paid subscriber
external API cost / activated user
```

---

# 3. Three-Week Outcome Targets

## End of Week 1 — Funnel Exists

- Free rankings accessible anonymously.
- Auth friction reduced.
- One-league free experience functioning.
- Analytics implemented.
- Infrastructure guardrails implemented.
- Fantasy-specific landing page live.
- Founder offer defined.
- First distribution assets ready.

## End of Week 2 — Acquisition Loop Proven

- Several hundred qualified visitors.
- League-import activation measurable.
- First meaningful paid cohort.
- At least two acquisition channels producing activated users.
- Creator/community outreach underway.
- Share/referral mechanism in use.
- Conversion bottleneck identified empirically.

## End of Week 3 — Scale the Winner

- 1,500+ qualified fantasy visitors cumulative.
- 300–500 registered users.
- 200–300 league imports/configurations.
- 100+ high-intent activated users.
- Strong trajectory toward or through 100 paid subscribers.
- Known free-to-paid conversion rate.
- Known infrastructure cost per activated and paid user.
- Clear channel ranking for the remainder of draft season.

---

# 4. Epic Structure

Treat this as one umbrella epic:

```text
GROWTH-100
```

with seven workstreams:

```text
G100-A  Offer and positioning
G100-B  Free acquisition surface
G100-C  Authentication and activation
G100-D  Funnel telemetry and cost controls
G100-E  Conversion and pricing
G100-F  Distribution
G100-G  Referral, proof, and retention
```

These workstreams are not parallel by default. The sequence below is load-bearing.

---

# 5. Critical Path

```text
G100-A0 Positioning
        ↓
G100-B0 Anonymous free rankings
        ↓
G100-D0 Funnel + cost telemetry
        ↓
G100-C0 Universal signup path
        ↓
G100-C1 One free personalized league
        ↓
G100-E0 Paid decision boundary
        ↓
G100-E1 Founder offer / checkout
        ↓
G100-F0 Warm launch
        ↓
G100-F1 Community + creator distribution
        ↓
G100-G0 Sharing/referral
        ↓
G100-G1 Weekly retention transition
```

Do not aggressively acquire traffic before the free value is visible, signup works for more than Google users, activation can be measured, costs can be monitored, and checkout works.

---

# 6. WEEK 1 — BUILD THE FUNNEL
## August 7–13

The objective is:

> A qualified visitor should be able to understand Credence, experience differentiated value, create an account with minimal friction, customize one league, and understand why the paid product is worth buying.

## G100-A0 — Reposition Fantasy Acquisition Surface

**Priority:** P0  
**Sequence:** 1  
**Effort:** Small

Recommended headline:

> **Fantasy rankings built for your league.**

Supporting lifecycle message:

> **Draft with Credence. Manage with Credence.**

Page requirements:

- Free draft rankings CTA.
- Custom-league CTA.
- Draft board screenshot.
- Projection uncertainty.
- Credence-vs-consensus examples.
- Weekly-product continuation.
- Clear free-versus-paid explanation.
- Pricing.
- Methodology/trust link.

Acceptance: a visitor can answer within 10 seconds what Credence is, what is free, why it differs, what requires payment, and why it matters after the draft.

## G100-B0 — Anonymous Free Draft Rankings

**Priority:** P0  
**Sequence:** 2  
**Effort:** Small–medium

Allow anonymous access to:

- Overall rankings.
- Position rankings.
- Player point projections.
- Selected uncertainty bands.
- ADP/reference rank.
- Basic player detail.
- Methodology.

Cost rules:

- Static/cached artifacts.
- CDN/S3 where available.
- No per-view model execution.
- No expensive database query.
- No LLM call.
- Sane rate limiting.

## G100-D0 — Funnel Telemetry

**Priority:** P0  
**Sequence:** 3

Required events:

```text
fantasy_landing_view
rankings_view
rankings_scroll_depth
player_open
customize_clicked
signup_view
auth_provider_selected
signup_completed
league_import_started
league_import_completed
custom_board_viewed
optimizer_preview
checkout_started
subscription_started
share_generated
share_clicked
```

Required dimensions:

```text
acquisition_source
campaign
referrer
auth_provider
league_platform
league_format
league_size
device
free_paid_status
```

## G100-D1 — Infrastructure Cost Guardrails

**Priority:** P0  
**Sequence:** 3

Measure or estimate cost for:

- Static ranking delivery.
- Authentication.
- League import.
- Personalized scoring.
- Draft optimization.
- Simulation.
- External APIs.
- Email.
- LLM or third-party inference, if any.

Controls:

- AWS budget alarm.
- Cost anomaly alert.
- Endpoint rate limits.
- Free league cap.
- Free optimizer quota if previews exist.
- Cache expensive deterministic results.
- No anonymous expensive compute endpoints.

Set:

```text
FREE_ACQUISITION_INFRA_BUDGET = $X
```

75% triggers review; 100% triggers tightening of expensive free actions, not shutdown of static rankings.

## G100-C0 — Expand Authentication Beyond Google

**Priority:** P0  
**Sequence:** 4

Keep Google. Add email OTP or magic link first. Add Apple if cheap. Do not prioritize username/password.

Architecture rule:

```text
canonical Credence user_id
    ↓
multiple auth identities
```

Auth is required for personalization/saving, not for browsing generic rankings.

**✅ SHIPPED 2026-08-10 — PR #722.** Email OTP (a 6-digit code via SES), not a magic link: a
link authenticates whatever opens it, which on mobile is routinely a webview inside the mail
client rather than the tab the person started in. Not username/password either — that path is
permanently closed on this pool (no email auto-verification, so a self-registered password
account can never confirm itself or reset its password). A code sidesteps that dead end rather
than trying to fix it: the code arriving in the mailbox **is** the ownership proof.

The architecture rule above is enforced in Cognito itself, not in a mapping layer beside it.
The canonical `user_id` is the NATIVE Cognito `sub`; federated identities are LINKED INTO it.
E9.7 already did that in one arrival order; G100-C0 closed the other by pre-provisioning a
native user for a brand-new federated sign-in, so Google-then-OTP and OTP-then-Google both
resolve to one account. PM ratified all five open calls (2026-08-10) — see
`infrastructure/cognito/email_otp/README.md`.

⚠️ **Not retroactive, by decision.** An account created before that deploy is federated-only;
its `sub` owns the person's data and cannot be moved, so OTP is REFUSED for those addresses
with "continue with Google" rather than minting a second, empty account. ⛔ No destructive
per-account migration without the PM naming specific accounts and confirming each is empty.
Population count is an operator step (`cognito-idp:ListUsers` is denied to the session IAM
user); if it is materially large, a one-time in-app notice is a fast-follow, not a blocker.

## G100-C0-MFA — Passwordless subscribers must not be locked out by MFA enforcement

**Priority:** P0 (blocking, not in the Week-1 funnel)
**Sequence:** before the E9.8 go-live, independent of the rest of GROWTH-100
**Owner:** the E9.8 / entitlement backend track
**Status:** 🟡 CODE LANDED 2026-08-12, ⛔ **NOT live-verified — the flip stays blocked.**
Carded 2026-08-10 out of G100-C0's PM review.

The ratified fix is built: a `passwordless` group applied at both creation points (the OTP
path and the PreSignUp pre-provision, and deliberately NOT when Google links into an existing
native user, which may have a real password) and exempted in `_totp_exemption`. Operator
runbook, the two-sided acceptance test and the backfill: `docs/g100_c0_mfa_passwordless_exemption.md`.
The live gate needs operator hands — Cognito group creation, one IAM addition, both deploys
(neither the API Lambda nor the trigger has CD), then the test. **Until it passes, `ENFORCE_SUBSCRIBER_MFA=1`
must not fire**, exactly as this card said before.

⭐ Found while fixing it, and it blocks the same flip from the other side: the guard parsed
`cognito:groups` by splitting on `,` while this gateway delivers `[subscriber]`, so with
enforcement ON it would have gated **nobody** — enforcement that reads as enabled and enforces
nothing. Fixed and RED-proven; it is also why leg B of the acceptance test could not have
passed before.

**This story is a hard blocking precondition on flipping `ENFORCE_SUBSCRIBER_MFA=1`.** That
flip must not fire until this lands AND is live-verified.

The defect, stated plainly: `auth.require_subscriber_mfa` exempts a session only when
`_session_is_federated` recognises it, and that keys off `amr` plus the federated USERNAME
SHAPE (`google_…`). A linked or pre-provisioned user's username is a plain UUID, so the check
fails — and it fails CLOSED, exactly as E9.8's own spec instructed ("if none is reliable,
FAIL-CLOSED"). That instruction was correct when the only alternative was a password session.
G100-C0 changed the population it lands on: with enforcement on, a `subscriber` who signs in
by email OTP is 403'd and told to enroll TOTP they **cannot** enroll, because the only way off
that screen (`reauthenticatePassword`) asks for a password they have never had. A locked-out
paying customer with no self-service recovery.

Inert today — `ENFORCE_SUBSCRIBER_MFA` defaults to `0`, and the frontend half is already
correct (`sessionUsesPasswordlessAuth()`). This is why it did not block PR #722.

**Ratified approach (PM, 2026-08-10):** apply a `passwordless` Cognito group at
pre-provision / OTP-account-creation time and exempt that group in `_session_is_federated`.
Groups already travel in the API-Gateway-validated token, so the signal is server-verifiable
and needs no pool schema change — unlike the client-side `credence_auth_method` marker, which
is client-controlled and must never gate a security decision.

🟥 **Why this is its own story and not a scoped item: it needs a live runtime gate the G100-C0
session could not run.** Before trusting the exemption, verify against the real pool what a
CUSTOM_AUTH session's token actually carries — `amr`, and whether the group claim is present
on it. ⛔ No blind fix: a wrong exemption here is an MFA BYPASS on a paying account, which is
the failure this guard exists to prevent, and it would pass CI exactly as happily as the
correct version. CI mocks all IO and cannot see Cognito.

## G100-C1 — One Free Personalized League

**Priority:** P0  
**Sequence:** 5

Free user receives:

- One league.
- Imported or manually configured scoring.
- League-specific player scoring.
- Personalized board.
- Limited VOR.
- Credence-versus-consensus differences.
- Saved state.

Activation definition:

```text
account_created
AND league_config_completed
AND custom_board_viewed
```

The product must answer visibly:

> **What changed because this is my league?**

## G100-E0 — Paid Decision Boundary

**Priority:** P0  
**Sequence:** 6

Product rule:

```text
Free = information
Paid = decision assistance
```

Paid draft examples:

- Full draft optimizer.
- Who-to-pick recommendations.
- Draft-state-aware VOR.
- Probability a player survives to next pick.
- Multiple leagues.
- Advanced simulations.

Paid in-season examples:

- Full weekly projections.
- Start/sit recommendations.
- Matchup win probabilities.
- Waiver optimization.
- Trade recommendations.

## G100-E1 — Founding 100 Offer

**Priority:** P1  
**Sequence:** 7

Potential benefits:

- Founder pricing while continuously subscribed.
- Founder badge.
- Direct product feedback channel.
- Early access to new fantasy tools.
- Input on roadmap priorities.

Scarcity is real: 100 founding memberships.

---

# 7. WEEK 1 EXIT GATE

Do not begin broad cold distribution until:

```text
[ ] Anonymous rankings work
[ ] Analytics works
[ ] Cost alerts work
[ ] Google + email signup work
[ ] One free league works
[ ] Paid boundary is clear
[ ] Checkout works
[ ] Fantasy landing page is coherent
```

---

# 8. WEEK 2 — PROVE ACQUISITION
## August 14–20

Week 2 answers:

> Can Credence repeatedly turn a qualified fantasy player into an activated user and then into a subscriber?

## G100-F0 — Warm-Network Launch

**Priority:** P0  
**Sequence:** 8

Contact fantasy players in the founder network, existing users, league mates, sports/data contacts, and former coworkers.

Lead with:

> We made our 2026 rankings free. Import your league and see where Credence changes your draft board. I’d love your feedback.

Initial goal: 25–50 activated users for funnel debugging.

## G100-F1 — Analytical Content Engine

**Priority:** P0  
**Sequence:** 9

Initial content themes:

1. Players Credence differs most from ADP on.
2. How 10/12/14-team league size changes value.
3. How superflex changes QB value.
4. Players with widest floor/ceiling distributions.
5. Platform-specific draft-room ranking inefficiencies.
6. Where VOR changes consensus ordering.
7. Overrated/underrated players with methodology.
8. Draft simulations and roster-construction lessons.

CTA:

> Free rankings → customize for your league.

## G100-F2 — Community Distribution

**Priority:** P1  
**Sequence:** 10

Potential channels:

- Reddit.
- Fantasy football communities.
- Discord.
- X.
- Facebook fantasy groups where permitted.
- Sports analytics communities.

Rule: provide useful analysis first; do not post generic product spam.

Measure activated users per referred visitor.

## G100-F3 — Micro-Creator Outreach

**Priority:** P1  
**Sequence:** 10

Target 30–50 smaller creators, newsletters, podcasts, YouTube channels, Discord operators, and fantasy analysts.

Do not ask for promotion first. Give them personalized content or league-format analysis they can use.

## G100-G0 — Shareable Draft Artifact

**Priority:** P1  
**Sequence:** 11

After league import, mock draft, or real draft, allow generation of a shareable artifact such as:

```text
CREDENCE DRAFT OUTLOOK

Draft Grade: A-
Projected Finish: 2nd
Best Value: Player X
Biggest Reach: Player Y

credencesports.com
```

Only include probabilities such as championship odds if validated.

Shared links should carry referral attribution.

---

# 9. WEEK 2 DIAGNOSTIC GATE

At the end of Week 2 classify the bottleneck.

## TRAFFIC

Few visitors, strong activation/conversion → increase distribution.

## ACTIVATION

Traffic exists, few league imports → fix onboarding/customization before more traffic.

## CONVERSION

League imports high, paid conversion low → fix offer, paywall, optimizer value, pricing, or trust.

## COST

Activation grows, infra cost unacceptable → tighten expensive free actions while preserving static acquisition.

## PRODUCT-WIN

Activation high, conversion high, cost controlled → scale the best channel aggressively in Week 3.

---

# 10. WEEK 3 — SCALE THE WINNER
## August 21–28

## G100-F4 — Channel Reallocation

**Priority:** P0  
**Sequence:** 12

Rank channels by:

```text
paid subscribers / effort
activated users / visitor
paid subscribers / visitor
infra cost / paid subscriber
```

Put founder time into the best-performing channel.

## G100-E2 — Conversion Follow-Up

**Priority:** P0  
**Sequence:** 13

Lifecycle communication:

- Registered, no league import → finish league setup.
- Imported, not paid → personalized board is ready; unlock decision tools.
- Draft approaching → open your Credence board.
- Draft completed → weekly projections are now live.

Respect communication consent and preferences.

## G100-E3 — Onboarding Optimization

**Priority:** P1  
**Sequence:** 13

Use observed funnel data. Test one bottleneck at a time rather than a large multivariate field.

Candidate tests:

- CTA copy.
- Personalized ranking reveal.
- Optimizer preview.
- Founder offer placement.
- Checkout messaging.

## G100-G1 — Draft-to-Weekly Retention Bridge

**Priority:** P0  
**Sequence:** 14

Product transition:

```text
Before draft:
Who should I draft?

After draft:
Who should I start?
Who should I add?
How likely am I to win?
What changed this week?
```

Free users receive a limited weekly preview. Paid users receive full weekly decision support.

## G100-G2 — Referral / Founder Loop

**Priority:** P1  
**Sequence:** 15

Test a lightweight league-mate referral mechanism. Do not overbuild affiliate infrastructure yet.

---

# 11. Explicit Three-Week Calendar

## August 7–9

```text
G100-A0  Fantasy positioning
G100-B0  Anonymous rankings
G100-D0  Funnel analytics
G100-D1  Cost guardrails
```

## August 9–11

```text
G100-C0  Email auth
G100-C1  One free league
G100-E0  Paid decision boundary
G100-E1  Founding 100 offer
```

## August 11–13

```text
QA entire funnel
Checkout verification
Mobile test
Cost test
Warm-launch prep
```

## August 14–16

```text
G100-F0  Warm launch
G100-F1  First analytical posts
G100-F2  Community distribution
```

## August 16–20

```text
G100-F3  Creator outreach
G100-G0  Shareable artifact
Continue content
Collect funnel data
```

## August 20

```text
WEEK-2 DIAGNOSTIC GATE
Classify:
TRAFFIC
ACTIVATION
CONVERSION
COST
or PRODUCT-WIN
```

## August 21–24

```text
G100-F4  Reallocate to winning channels
G100-E2  Conversion follow-up
G100-E3  Fix measured bottleneck
```

## August 24–28

```text
G100-G1  Weekly retention bridge
G100-G2  Referral loop
Scale strongest channel
Founder-100 conversion push
```

---

# 12. Suggested Story Cards

1. `G100-01 · Free public fantasy rankings`
2. `G100-02 · Fantasy landing page and lifecycle positioning`
3. `G100-03 · Acquisition-to-paid funnel telemetry`
4. `G100-04 · Free-tier infrastructure budget and rate guards`
5. `G100-05 · Email OTP authentication and canonical identity`
6. `G100-06 · One free personalized fantasy league`
7. `G100-07 · Draft-information versus decision-assistance paywall`
8. `G100-08 · Founding 100 subscription offer`
9. `G100-09 · Warm-network fantasy launch`
10. `G100-10 · Credence fantasy analytical content program`
11. `G100-11 · Community distribution`
12. `G100-12 · Micro-creator outreach`
13. `G100-13 · Shareable custom-board / draft artifact`
14. `G100-14 · Activation and checkout lifecycle messaging`
15. `G100-15 · Draft-to-weekly retention conversion`
16. `G100-16 · Lightweight league-mate referral loop`

---

# 13. Product Work Explicitly Deferred

Unless required to unblock conversion, do not allow these to consume the three-week growth window:

- WAR.
- Weekly-to-preseason simulator.
- Dynasty.
- Broad season-model research.
- Another large ranking-model bake-off.
- Advanced trade engine.
- Sophisticated referral economy.
- Full creator affiliate system.
- Expensive LLM personalization.
- Large paid advertising campaigns.
- Complex SEO rebuild.
- Every league-platform integration.

The existing season and weekly models are sufficiently mature to test customer demand.

---

# 14. Free-Tier Infrastructure Policy

## Effectively Unlimited / Cached

- Static rankings.
- Static projections.
- Public methodology.
- Cached player pages.

## Generous but Bounded

- One custom league.
- Deterministic league rescoring.
- Saved personalized rankings.

## Metered

- Draft optimizer.
- Monte Carlo simulations.
- Expensive backend recomputation.
- External paid APIs.
- LLM-generated narratives.

Any feature where marginal usage materially increases compute cost should trend toward paid unless required for activation.

---

# 15. Authentication Roadmap

## Now

```text
Anonymous rankings
+
Google
+
Email OTP / magic link
```

## Near-Term Optional

```text
Sign in with Apple
```

## Not Needed

```text
username/password
```

Key rule: Credence owns the canonical user identity; OAuth providers are authentication methods only.

---

# 16. Founder-Level Daily Dashboard

Review every day during the sprint:

```text
qualified visitors
new accounts
league imports
activated users
checkout starts
new paid
cumulative paid
free→paid %
infra spend
infra / activated user
top acquisition source
```

---

# 17. LLC / Business Formation Decision

**This section is operational guidance, not legal or tax advice.**

## Recommendation

**Form the customer-facing business entity now—before the paid subscriber push begins.**

The company is moving from:

```text
prototype / personal project
```

to:

```text
public acquisition
+
subscriptions
+
recurring revenue
+
customer contracts
+
business expenses
```

That is the point at which continuing indefinitely as an individual becomes increasingly unattractive.

## Practical Trigger

The LLC does not need to exist merely because code was written. It should exist before, or at minimum contemporaneously with:

- Accepting meaningful paid subscriptions.
- Entering customer-facing Terms of Service.
- Signing vendor/customer contracts in the company name.
- Opening the production payment account.
- Creating a dedicated operating bank account.
- Paying recurring business expenses at meaningful scale.
- Hiring contractors or employees.

Credence is now entering that stage.

## Recommended Timing

```text
Week 1 of GROWTH-100
```

Complete the entity decision and formation before the broad acquisition push and before materially scaling paid subscriptions.

---

# 18. Wisconsin LLC Baseline

For a Wisconsin domestic LLC, the state currently publishes:

```text
online Articles of Organization filing: $130
paper filing: $170
annual report: $25/year
```

The Articles of Organization require, among other items:

- LLC name.
- Registered agent.
- Wisconsin registered office.
- Principal office.
- Organizer.
- Contact information.

A single-member LLC is generally treated as a disregarded entity for federal income-tax purposes unless another tax classification is elected.

An EIN is often useful operationally even when a no-employee single-member disregarded LLC may not strictly need one for federal income-tax purposes.

---

# 19. Structure Decision Before Filing

Before filing, decide which legal architecture you actually want.

## Option A — Credence Sports LLC Directly

```text
Owner
  ↓
Credence Sports LLC
```

Best when simplicity matters and Credence is the main operating company.

## Option B — Parent + Credence Operating Entity

```text
Parent HoldCo
    ↓
Credence Sports LLC
```

Best only when there is a concrete reason to separate businesses, liability profiles, investors, IP ownership, or capital structure.

Do not create multiple entities merely because the structure sounds sophisticated. Every entity creates filing, accounting, banking, tax, contract, and annual-compliance work.

For a self-funded company chasing its first 100 subscribers, simplicity has substantial value. If a holding-company architecture remains part of the plan, have a business attorney/CPA review it before filing.

---

# 20. Expenses Already Incurred

Do not assume pre-formation expenses are lost.

Federal tax rules distinguish business start-up and organizational costs and provide mechanisms for deduction/amortization when the business begins.

Preserve:

- Infrastructure invoices.
- Domain/software/API bills.
- Advertising costs.
- Contractor invoices.
- Equipment and service receipts.
- Date, amount, vendor, and business purpose.

Have a tax professional classify pre-formation expenses correctly.

---

# 21. Post-Formation Operational Checklist

```text
[ ] Obtain EIN if appropriate
[ ] Open dedicated business checking
[ ] Move Stripe/payment processing to business identity
[ ] Use company identity in Terms / Privacy / subscriptions
[ ] Move recurring AWS/API/software spend to business payment method
[ ] Establish bookkeeping
[ ] Record founder contributions/reimbursements correctly
[ ] Maintain registered agent
[ ] Calendar Wisconsin annual report
[ ] Review tax registration requirements with CPA
[ ] Review Terms of Service / Privacy Policy
```

---

# Final Strategic Call

The next three weeks should answer:

> **Can Credence repeatedly acquire a fantasy player, show them enough personalized value to activate, convert the engaged segment to paid, and retain them into the weekly season at sustainable marginal cost?**

The correct sequence is:

```text
MAKE VALUE VISIBLE
        ↓
REMOVE FRICTION
        ↓
MEASURE EVERYTHING
        ↓
PERSONALIZE
        ↓
CONVERT DECISION SUPPORT
        ↓
DISTRIBUTE
        ↓
SCALE THE WINNING CHANNEL
        ↓
RETAIN INTO WEEKLY
```

Because Credence is now deliberately preparing to acquire paying customers, entity formation should move from future administrative work to **Week-1 operating work**.
