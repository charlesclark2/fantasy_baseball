# NF-C0-Yahoo-ENABLE — Half A (compliance)

**Date:** 2026-08-20 · **Branch:** `nf-c0-yahoo-halfa-compliance` · `best_alpha = 0`

> ## ⚠️ PARTIALLY SUPERSEDED — read `nf_c0_yahoo_clause_audit.md` first
>
> This document was written **without the agreement text**, against the spike memo's paraphrase of
> it. The operator supplied the executed agreement on 2026-08-21 and the clause-by-clause audit is
> in **`docs/nf_c0_yahoo_clause_audit.md`**. Three claims below did not survive contact with it and
> are corrected there rather than edited out here — a record edited after the fact is no longer a
> record of what was decided and on what basis:
>
> * **§1 — the 30-day retention window does NOT satisfy §2.c.vii**, which prohibits storing Yahoo
>   Fantasy Information with no retention qualifier at all. The window is a mitigation, not
>   compliance. **This is the open item and it blocks Half B.**
> * **§1 — "the scoring config is ours" is a weak textual argument.** §1.e defines Yahoo Fantasy
>   Information as *any information retrieved from the Yahoo Fantasy Database*, which includes the
>   league settings this document treats as our own derived artefact.
> * **§2 — the credit had to be in the page FOOTER**, which the paraphrase did not say. Fixed on
>   `nf-c0-yahoo-halfa-clause-audit`.
>
> **§4 (US + CA) is RESOLVED and the decision it recorded STANDS** — §2.b bounds the licence, not
> delivery. The hedge ("I could not read the clause") no longer applies; the audit carries the
> reading, and the declared-jurisdiction attestation it sketched is not needed.

Half A closes the three compliance gaps the NF-C0-Yahoo spike measured and left for a PM decision
(`docs/nf_c0_yahoo_spike_memo.md` §5, gaps **B2–B4**), and records the decision on the agreement's
**US + CA** scope.

⛔ **HALF B (ENABLEMENT) IS UNCHANGED AND STILL BLOCKED.** `YAHOO_IMPORT_ENABLED` stays off and
`yahoo_oauth.is_enabled()` still refuses every Yahoo route. The blocker is Yahoo's, not ours: our
app carries no Fantasy Sports entitlement, so every `/fantasy/v2/*` returns a bare 401
`oauth_problem="additional_authorization_required"` while `openid/v1/userinfo` returns 200 for the
same token. Signing the data agreement did not attach it, and because permissions bind at CONSENT
time, enabling it will need a fresh consent. Nothing in this story touches that.

⭐ **WHY IT IS WORTH SHIPPING WHILE HALF B IS BLOCKED.** Two of the four items are not Yahoo-specific
at all. The retention window and the deletion-on-disconnect apply to **every** platform whose
rosters we copy — ESPN and Sleeper leagues are live today and were being kept forever, with no way
for a user to remove them — and the privacy policy described none of it. Only the Yahoo attribution
is contingent on Yahoo, and it is inert until a Yahoo league exists.

---

## 1. Retention + deletion (spike gaps B2 / §2.c.vii + §6)

### What was wrong

* `DELETE /fantasy/import/yahoo/connection` dropped the **OAuth token and nothing else**. A user who
  disconnected kept every roster we had copied, indefinitely, and the endpoint they used to
  disconnect was their only handle on it.
* Rosters were persisted with **no retention bound at all** — no TTL, no expiry, no sweep.

### What now happens

| | Kept | Deleted |
|---|---|---|
| **Scoring config** — `scoring`, `roster` slots, `n_teams`, `ppr`, `depth_targets` | ✅ | |
| **Copied rosters** — `imported_roster`, `league_rosters`, their `*_synced_at`, `league_rosters_truncated` | | ✅ |

The split is the design, and it is drawn in one place (`dynamo.PLATFORM_ROSTER_FIELDS`). The rosters
are a copy of the platform's league state — Yahoo Fantasy Information by any reading. The scoring
config is our own derived artefact, in the same class as a hand-entered league; deleting it would
destroy work the user did, on an action they took to stop us reading Yahoo.

**Deletion on disconnect.** `yahoo_disconnect` now calls `purge_platform_league_data(user_id,
"yahoo")` **before** dropping the token. The order is the contract: dropping the token first would
leave the rosters behind with the connection already gone, so a purge that cannot complete surfaces
as a failed disconnect the user can retry rather than a silent partial one.

**Retention window: `PLATFORM_ROSTER_RETENTION_DAYS = 30`.**

⚠️ **This is deliberately not a DynamoDB TTL.** DynamoDB's TTL deletes whole **items**, and every
one of a user's leagues is an attribute on their **single** user row alongside their bets, portfolio
and preferences (`MAX_FANTASY_LEAGUES_BYTES` documents why). A native TTL here would delete the
user's entire account row when a roster aged out. So the window is enforced in `dynamo`, with
semantics that deliberately mirror DynamoDB's own:

1. **The read is the guarantee.** `list_fantasy_leagues` strips expired roster data before returning
   it, and every reader in the codebase — `get_fantasy_league` included — goes through it. No caller
   can serve expired data, whether or not any sweep ever runs.
2. **The sweep removes the bytes.** The same read fires a best-effort `REMOVE` when it observes an
   expiry, so "we do not *store* it past the window" is satisfied and not merely "we do not *show*
   it". It is conditional on an expiry actually being seen, so an ordinary read costs no extra write.

**Fail-closed on a missing stamp.** A record holding roster data with no expiry stamp is treated as
**expired**. The only way to be in that state is to have been stored before this shipped — i.e.
under no retention bound at all — so treating a missing stamp as "not expired yet" would exempt
exactly the records this story exists to bound.

**The deletion says it was a deletion.** A purged league and a league that has not drafted produce
the **identical payload**: a linked team with an empty roster. Until now My Teams explained both as
*"the usual reason is your league hasn't drafted yet"* — a confident wrong answer for something we
did, telling the user to re-import to fix a non-problem (the NF-C6b ambiguous-empty-state class). So
`roster_retention_purged` is served, and My Teams names the window and says the settings survived.

---

## 2. Attribution (spike gap B3 / Cover + §5)

**Was:** *"Fantasy data provided by Yahoo Fantasy"*, hyperlinked, rendering in **exactly one place** —
the import preview, before the league is even saved. Every surface showing the data after the save
showed none.

**Now:** one shared component, `frontend/components/fantasy/platform-attribution.tsx`, keyed on the
league's own `source_platform`, rendered on **twelve** surfaces:

| Named in the brief | Also carried |
|---|---|
| My League · My Teams · Roster report · League board · Draft optimizer · Auction optimizer · League settings | Import preview (repointed at the shared component) · Rankings · Big board · Mock draft · Player page |

⭐ **The extra five are deliberate, and the reason is that the brief's line is hard to hold.** The
brief names seven surfaces including the **league board**, which shows our own projections re-scored
under the platform's scoring rules. Rankings, the big board, the mock draft and the player page do
exactly the same thing under the same `custom:<league_id>` selection — there is no principled line
that puts the league board inside the requirement and those four outside it. Rendering the credit on
all of them costs one line each and removes the judgement call.

**Two-sided, because a one-sided test is worse than none here.** The credit keys on provenance and
nothing else, so `frontend/e2e/specs/fantasy-platform-attribution.spec.ts` runs every surface twice
against the SAME league differing in `source_platform` alone:

* a component that never renders the credit fails the Yahoo case;
* a component that renders it **unconditionally** fails the Sleeper case — and crediting Yahoo for
  data Yahoo did not supply is its own false statement about a third party.

**Asserted on rendered output, not source (NF-C4).** A grep for the string would have passed
throughout the entire outage: the string was in the codebase, it just never reached seven of the
eight screens that owed it.

🪤 **And the browser test immediately found a gap a source guard could not have.** Both optimizers
early-return a **separate setup screen** (`if (!started) return …`), and that is the screen carrying
the league PICKER, the format description and the roster slots read from the platform. The credit
placed at the end of the component reached only the LIVE draft tree — so a user configuring a draft,
which is where the time is actually spent looking at those settings, saw none. Every source-level
check was satisfied (the file imports the component, renders it, and the component is correct); only
driving the real route caught it. Both setup screens now carry it, and the spec reaches them because
it never presses "Start draft".

**And the enumeration is derived, not remembered.** The gap was never "the component is wrong" — it
was "nobody enumerated the screens". `test_nf_c0_yahoo_halfa_compliance.py` scans every component in
`frontend/components/fantasy/` that can resolve one of the caller's saved leagues (`useSavedLeagues`
/ `useMyTeams`) and requires each to render the shared component. A new surface added without one
goes red instead of shipping a silent compliance gap.

---

## 3. Privacy policy (spike gap B4 / §7)

`frontend/app/privacy/page.tsx` had **zero** occurrences of "league", "fantasy", "import", "Yahoo",
"Sleeper" or "ESPN" — it did not describe this data flow at all.

New **§5 — Fantasy League Import (Yahoo, ESPN, Sleeper)**, before Data Retention, covering: what we
read and per-platform how; that every request is read-only and we never see a platform password;
that settings are kept and rosters expire in 30 days; that disconnecting deletes the rosters
immediately while leaving the settings; and the four things we never do with it (train or evaluate a
model, send it to an LLM, index it, sell or share it). Data Retention cross-references the window.

⚠️ **The policy renders `PLATFORM_ROSTER_RETENTION_DAYS` rather than a typed literal**, and the two
spellings are pinned equal by test. A policy page promising 30 days over a store that keeps 90 is a
compliance statement that is simply untrue, and nothing about the rendered page would look wrong.

---

## 4. US + CA scope — the decision

**Decision: no geo-restriction is added, and none is planned. Recorded as an accepted risk with a
named trigger, not as a cleared item.**

⚠️ **Stated plainly: I could not read the clause.** The signed agreement is not in this repo (I
searched — the only Yahoo material here is the OAuth setup doc, the spike memo and the code), so
this is a decision made on the constraint as the spike memo describes it, not a reading of the
words. The same caveat the spike memo carries for §2.c.v–vi.

**Three findings that hold regardless of the wording:**

1. **The read-only half is satisfied by construction.** Every Yahoo call in
   `app/backend/services/platform_import/yahoo.py` is a `GET`; nothing anywhere writes to Yahoo.
2. **No country signal reaches the path that would need gating.** Authenticated calls go from the
   browser straight to `NEXT_PUBLIC_API_URL` (API Gateway → Lambda) — they never traverse Vercel's
   edge, which is the only layer in this stack that carries a viewer-country header
   (`frontend/app/api/public/[...path]/route.ts` is anonymous-only, and CloudFront is documented as
   *not yet provisioned*). So a geo gate is not a config change; it is a new signal on a new hop.
3. **⭐ And acquiring that signal would contradict a standing promise.** The privacy policy states,
   under *Information We Do Not Collect*, that we do not collect **precise geolocation data**.
   IP-derived country is not precise geolocation, so this is not a straight contradiction — but it
   is close enough that adding one is a **privacy-policy decision as much as a compliance one**, and
   it should not be slipped in as an implementation detail.

**Therefore:** a delivery-side geo restriction is treated as **not a real constraint today**. The
product has no country signal, no user-declared jurisdiction, and no user-facing statement that the
import is US/CA-only.

⏭️ **The trigger that reverses this, and what it costs.** If the clause turns out to bind
**delivery** — who may *use* the import — rather than only the **scope of the licence**, then this
is an open gap and the cheapest honest answer is *not* an IP gate. It is a **declared-jurisdiction
attestation at the point of connecting** (one checkbox on the Yahoo connect step, stored on the user
record), because it needs no new signal, no new hop, and no new collection of location data. An IP
gate is the more expensive and less accurate option and should be argued for, not assumed.

⏭️ **Operator action:** read the clause and confirm which reading is right. That is a five-minute
answer for whoever has the document, and it is the only input this decision is missing.

---

## What is guarded, and how

| | |
|---|---|
| Store round-trip: write → read → purge → re-read | `test_nf_c0_yahoo_halfa_compliance.py` (a fake table that **interprets** the update expressions and raises on a malformed one — a dict the test mutates itself could not catch a bad `UpdateExpression`, which is the only way this fails in production) |
| The bytes are gone from the stored item, not merely masked | same file, asserted underneath every reader |
| The route calls the purge, and calls it **first** | same file — wired is not invoked (NF-C0e) |
| The retention window, both directions + fail-closed | same file |
| Constants agree: store ↔ client ↔ privacy copy | same file |
| Every league-aware surface renders the credit | same file (derived registry, non-vacuity asserted) |
| The credit **renders**, on twelve routes, two-sided | `frontend/e2e/specs/fantasy-platform-attribution.spec.ts` |
| A purged league is not explained as a pre-draft one | same spec, with a pre-draft control |
| **All of the above actually fail when broken** | `uv run python betting_ml/tests/nf_c0_yahoo_halfa_red_proof.py` — **16/16 RED** |

**Verified locally before the PR:** Python fast gate **10,845 passed**; the new suite **24 passed**;
the RED proof **16/16 RED**; `tsc --noEmit` clean; the full Playwright suite **498 passed, 22
skipped, 0 failed** (`npm run e2e:build` then `npx playwright test`).

🪤 **The RED proof earned its keep on the first run.** It reported one guard as vacuous — and the
guard was fine; the *break* had missed. `roster_retention_purged` has **two** writers
(`_strip_platform_rosters` on the read-mask path, `_remove_roster_attributes` in the store), and
breaking one left the other satisfying the clause. Split into one break per writer, each pointed at
the clause that actually depends on it, both go red. Recorded because a *false* vacuity report is
the dangerous direction: it reads as a finding and invites weakening a correct guard.

---

## ⏭️ Operator steps

1. **Merge the PR to `dev`.** Frontend auto-deploys from `main`; the backend does not.
2. **After merge, deploy the API Lambda — this is the half that does not ship itself:**
   ```
   ./infrastructure/lambda/deploy.sh
   ```
   Run on the **LAPTOP**. Without it, `yahoo_disconnect` keeps dropping only the token and the
   retention window is never enforced, while the frontend already promises both.
   ⚠️ Deploy skew has a direction here: the frontend ships first (Vercel, on merge to `main`), so
   between the two the privacy policy states a retention window the store is not yet applying.
3. Read the US + CA clause and confirm the §4 decision above (or reverse it).
