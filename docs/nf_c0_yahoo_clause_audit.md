# Yahoo API Access and Use Agreement — clause audit against the shipped code

**Date:** 2026-08-21 · **Agreement:** executed 2026-08-14, Effective Date 2026-08-15 ·
**Reviewed against:** `dev` at the NF-C0-Yahoo-ENABLE Half A merge (PR #985) plus this branch.

⚠️ **I am not a lawyer and this is not legal advice.** It is an engineering audit: for each clause,
what the code actually does, measured. Where a clause turns on a legal reading rather than on a
fact about the system, I say so and stop.

## The short answer

**Half A does NOT bring us into compliance.** It closed real gaps and it is worth having, but the
headline item it was built around — a 30-day retention window for copied rosters — **does not
satisfy §2.c.vii, which is an unqualified prohibition on storing Yahoo Fantasy Information at all.**
Half A was specified against the spike memo's paraphrase of the clause; the actual text is stricter
than the paraphrase in two places (§2.c.vii's absoluteness, and the Cover Page's "footer") and
broader in one (§1.e's definition, which sweeps in the league settings Half A treated as ours).

**This branch fixes what is mine to fix.** Two of the three findings are engineering defects with
bounded fixes and they are shipped here. The third is a product and legal decision that I should not
make unilaterally, and it is the one that actually blocks Half B.

| | Clause | Verdict |
|---|---|---|
| 1 | Cover Page — attribution **in the footer of each page** | ⛔ was **NOT MET** → **fixed here** |
| 2 | §2.c.vii — no store/cache/index of Yahoo Fantasy Information | ⛔ **NOT MET; PM/legal decision** |
| 3 | §6 — delete every copy within 10 business days of termination | ⛔ was **UNMEETABLE** → **fixed here** |
| 4 | Cover Page — Territory (US + CA) | ✅ met; the Half A hedge is now **resolved** |
| 5 | §1.c / §2.c.xii / §3.e — never into training or an AI tool | ✅ met, mechanically guarded |
| 6 | §2.c.x — do not present all players in a fantasy league | ⚠️ **grey; needs a reading** |
| 7 | §5 — display only within the Developer Application | ✅ met |
| 8 | §2.c.v — rate limits, retry, backoff | ✅ defensible, with a note |
| 9 | §3.d — 48-hour breach notification to Yahoo | ⚠️ **no process exists** (operational) |
| 10 | §7 — privacy policy accurately describes collection | ✅ met by Half A |
| 11 | §16 — no marks, no publicising the relationship | ✅ met, with one thing to watch |
| 12 | §2.c.iv / §2.c.xi — no resale; no competing product | ⚠️ **business judgement, flagged** |

---

## 1. Attribution must be **in the footer of each page** — was not met, fixed here

> **Cover Page, Attribution.** "Developer must provide clear attribution to Yahoo Fantasy wherever
> Yahoo Fantasy Information is displayed … **Web** — For websites and web-based Developer
> Applications, attribution must appear **in the footer of each page** where Yahoo Fantasy
> Information is displayed and must include a hyperlink to an official Yahoo Fantasy webpage."

**Two defects in what Half A shipped, both invisible without the clause text.**

**(a) It was not in the footer.** Half A rendered the credit at the end of each surface's main
content — above `SiteFooter`, not inside it. The spike memo's paraphrase read "attribution +
hyperlink on every page showing Yahoo data" and never used the word "footer", so the placement
requirement was not in view when the work was specified. A reader would see the credit at the bottom
of the page either way, which is exactly why nothing flagged it.

**(b) The import screen showed Yahoo data uncredited.** The credit rendered inside the *preview*
block, but the screen before it lists the user's Yahoo leagues — names, team counts, season, status,
all straight from their API. That list was uncredited for the whole time a user spends choosing
which league to import, which is the longest they look at that screen.

**Fixed.** `PlatformAttribution` now *registers* what a surface is displaying and
`PlatformAttributionFooterSlot` renders the credit inside `SiteFooter`'s `<footer>`; the import
screen credits the league list on sight. ⚠️ `SiteFooter` is a **sibling** of the page in the root
layout, so no page-level component can render into it — the same structural fact NF-C4 hit from the
other side. The registration goes through two contexts, not one, and that split is load-bearing: a
single context would change identity on every registration, the registering effect would re-run, its
cleanup would unregister, and the two would flip forever. That renders as a hung tab.

It **fails safe**: with no provider above it, the component renders the credit inline rather than
silently nothing.

The E2E now scopes every assertion to `<footer>`, because `getByTestId` alone would pass just as
happily with the credit back where it was.

## 2. §2.c.vii — "Developer shall not store, cache or index the Yahoo Fantasy Information"

> **§2.c.vii.** "Developer shall not reverse engineer, modify, decompile, separate the Yahoo Fantasy
> Information from the API, or otherwise alter the API or the Yahoo Fantasy Database. **Developer
> shall not store, cache or index the Yahoo Fantasy Information.**"
>
> **§1.e.** "**Yahoo Fantasy Information.** Any information retrieved from the Yahoo Fantasy
> Database."

⛔ **This is the finding that matters, and Half A does not close it.**

**The prohibition carries no retention qualifier.** There is no "beyond a reasonable period", no
"other than as necessary for the Approved Use Case", no stated window anywhere in §2. A 30-day
retention window is a *mitigation* of §2.c.vii, not compliance with it. Half A's own commit message
and privacy copy describe the window as though the clause permitted one; on the text, it does not.

**And §1.e is broader than Half A assumed.** Half A drew a line between "the rosters are theirs" and
"the scoring config is ours — our own derived artefact, in the same class as a hand-entered league."
That is a good *practical* argument (the user could have typed the same numbers by hand) and a weak
*textual* one: §1.e defines Yahoo Fantasy Information as **any information retrieved from the Yahoo
Fantasy Database**, and the scoring rules, roster slots and team count were retrieved from it. Under
the clause, the league settings we keep indefinitely are also Yahoo Fantasy Information.

⚠️ **There is a genuine internal tension in the Agreement, and it is worth putting in front of
counsel rather than resolving in a commit.** The Approved Use Case authorises reading league
settings and rosters "for the purpose of personalizing player projections and draft boards", which
cannot be delivered without holding that data at least for the duration of the work; §13 separately
contemplates retaining Historical Data "no longer than is reasonably necessary to support the
Approved Use Case"; and §3.e names a 30-day maximum, but only for AI Tool inputs and outputs, which
we do not have. A reading that §2.c.vii bars building a persistent **cache or index of Yahoo's
database** — rather than barring the transient operational storage the Approved Use Case requires —
is coherent. It is also not what the sentence says.

**⏭️ This is a PM and legal decision, not an engineering one.** Three options, honestly costed:

1. **Get the retention window in writing.** §17 permits amendment by a signed writing, and §2.c
   restrictions are qualified elsewhere by "unless expressly approved in writing by Yahoo". A short
   amendment naming a retention period for the Approved Use Case would make the shipped design
   compliant as-is. **Lowest engineering cost; requires a conversation with Yahoo.**
2. **Store nothing durable for Yahoo leagues.** Hold settings and rosters for the request only, and
   re-fetch on every read. Costs the whole personalization model for Yahoo (My Teams, the roster
   report, league boards and both optimizers all read a *saved* league), multiplies API calls
   against §2.c.v rate limits, and makes ESPN — which we cannot re-fetch at all, since its import is
   a browser paste — behave differently from Yahoo on the same screens.
3. **Narrow what is stored.** Keep the settings (needed to score a board at all), drop `imported_roster`
   and `league_rosters` for Yahoo entirely. Halves the exposure and keeps most of the product, but
   still stores Yahoo-derived data, so it does not satisfy the clause literally either.

⛔ I have deliberately **not** implemented any of these. Ripping the rosters out is a large,
user-visible product change and picking option 2 or 3 unilaterally would be making the PM's decision
in code. **Half B (`YAHOO_IMPORT_ENABLED=1`) should not flip until this is settled** — it is the one
finding here that is genuinely blocking, and it is blocking on a decision rather than on work.

## 3. §6 — deletion on termination was unmeetable; fixed here

> **§6.** "As soon as practicable following any termination or expiration of this Agreement (and in
> no event more than **ten (10) business days** thereafter), Developer agrees to uninstall and
> delete from its computer systems and servers **all copies** of the Yahoo Materials and Yahoo
> Fantasy Information …"

`purge_platform_league_data` deletes **one** user's copies and is reachable only through that user's
own disconnect. So on the day the Agreement ends, there was no way to execute this obligation across
the account base at all — a clause naming a ten-business-day deadline against a mechanism that did
not exist. It is also what a §14 audit would need answered.

**Fixed:** `dynamo.iter_platform_league_holders(platform)` enumerates every account holding that
platform's rosters, and `scripts/purge_platform_data.py` deletes them. It goes through the **same**
purge function a user's own disconnect calls, so there is one deletion implementation rather than
two that can drift. **Dry run by default** — it destroys data across every account, and the only
thing worse than being unable to run it is running it by accident. A partial purge exits non-zero,
because §6 is a deadline and an operator who reads "done" over a partial run has no reason to return.

⚠️ **Scope, stated because it is easy to overclaim:** it deletes **rosters**, not leagues, and not
the stored OAuth tokens. Whether league *settings* must also go depends on finding 2 above — if the
strict §1.e reading holds, this script needs to delete more than it currently does. It is written so
that widening it is a change to `PLATFORM_ROSTER_FIELDS`, in one place.

## 4. Territory (US + CA) — the Half A hedge is resolved

Half A recorded "no geo-restriction, accepted risk with a named trigger", explicitly flagged that I
could not read the clause, and named the trigger as: *does the Territory bind delivery, or only the
scope of the licence?*

**The clause answers it: it bounds the licence.**

> **§2.b.** "**During the Term and in the Territory**, subject to the terms of this Agreement, Yahoo
> grants Developer a limited, royalty-free, nonexclusive … license … solely for purposes of enabling
> Developer Application to **retrieve** certain information …"

"In the Territory" qualifies the grant of the licence to **retrieve**. Our retrieval happens from
AWS Lambda in `us-east-1` — in the Territory. Nothing in §2.c's restrictions, §5's display rule, or
§7's warranties mentions territory or the location of Users. ⇒ **The decision stands, and now on the
clause rather than on an assumption: no geo-restriction, and the attestation fallback Half A
sketched is not needed.** The three supporting facts in `nf_c0_yahoo_halfa_compliance.md` §4 (every
call is a GET; no country signal reaches the authenticated path; acquiring one brushes our own
"no precise geolocation" promise) are unchanged and still hold.

⚠️ **One residual, small:** if we later move API egress outside the US/CA — a non-US Lambda region,
or a proxy — the retrieval leaves the Territory and this reading stops protecting us.

## 5. Never into training or an AI tool — met, and guarded

> **§2.c.xii.** "…shall not use Yahoo Fantasy Information for profiling unrelated to the Approved
> Use Case, for creating or enriching independent datasets or user profiles, for **training or
> improving any models or algorithms (including AI Tools)**…"
> **§3.e.** "…not use … for the purpose of training, grounding, or otherwise improving any AI Tool…"

✅ Our models train on nflverse and public play-by-play, never on user leagues, and the repo's one
LLM call site (the MLB narrative generator on Bedrock Nova Micro) takes no league input. This held by
convention until the spike and is now a mechanical source guard
(`test_nf_c0_yahoo_spike.py::TestYahooDataNeverReachesTrainingOrTheLLM`).

⚠️ **Worth knowing about §3.e's other half:** if the Developer Application ever includes AI Tools,
*all* Yahoo Fantasy Information entered into them **belongs exclusively to Yahoo**, and Input/Output
must be deleted at intervals no longer than 30 days. Nothing here trips it today. The live draft
assistant and the mock-draft CPUs are deterministic simulations, not generative models — but a
future "ask our assistant about your roster" feature would land squarely inside §3.e.

## 6. §2.c.x — presenting "all players in a fantasy league" (grey, needs a reading)

> **§2.c.x.** "Developer shall not use the Yahoo Materials or the Yahoo Fantasy Information to
> **compile and present** complete boxscores, complete statistics for any players in the League, all
> players on any League team (unless all such players are also on a User's fantasy team) or **all
> players in a fantasy league**."

**Measured, because the answer turns on what we actually put on screen:**

* ✅ **We do not display other teams' rosters.** The roster report's league-comparison table renders
  team **names, aggregate projected totals, an 80% range and a matched-count** — no opposing
  players. The waiver section names players who are on *nobody's* roster, sourced from our own board.
* ⚠️ **We do transmit them.** `/fantasy/nfl/league-board` serves `league_rosters` with every team's
  player rows joined to the board, so the full set is in the browser and readable in devtools even
  though nothing paints it.
* ⛔ **And we store them** — which is finding 2, not this one.

**The reading it turns on:** whether "present" means *display to the User* (we comply) or reaches
*transmitting to the Developer Application* (we may not). I am not going to decide that. ⏭️ If the
answer is the stricter one, the fix is cheap and local: aggregate the totals **server-side** and
serve only `{team_name, total, p10, p90, matched}` — the UI already renders nothing more. That is a
one-endpoint change and is worth doing regardless if finding 2 resolves toward narrowing.

## 7–8. Display scope and rate limits — met

**§5** ("display Yahoo Fantasy Information only within the Developer Application"): ✅ nothing exports,
shares or publishes league data; the served payloads are per-caller and are explicitly excluded from
the CDN allowlist and the public cache rules.

**§2.c.v** (rate limits, "appropriate retry logic, exponential backoff, and error handling"): ✅
defensible. `platform_import/http.py` retries a throttled GET **once**, honours `Retry-After`, and
declines to retry when `Retry-After` exceeds the budget. ⚠️ It is not *exponential* backoff, and the
reason is physical rather than lazy: API Gateway kills a request at 29s and the per-call timeout is
8s, so one retry fits inside the window and two do not. Sleeping through the gateway's own deadline
would convert a legible 429 into an unexplained edge timeout. Recorded here so the deviation is a
stated design decision and not an oversight.

## 9. §3.d — breach notification within 48 hours (no process exists)

> **§3.d.** "If Developer … discover[s] or [is] notified of a breach or potential breach of security
> relating to the Yahoo Materials, Developer shall, as soon as possible … **but in no event later
> than 48 hours**: (i) notify Yahoo of such breach …"

⚠️ **There is no runbook entry, no alert route and no owner for this.** It is operational rather than
code, but it is a 48-hour clock with a named recipient (`legalnotices@yahooinc.com`, Cover Page) and
today nobody would know to start it. ⏭️ Recommend a short entry in `BOX_OPERATIONS.md`: who decides
it is a breach, the 48-hour clock, the address, and that the OAuth refresh tokens in
`platform_tokens` are the sensitive asset (they are Fernet-encrypted; the key is in SSM).

## 10–12. Privacy policy, marks, and two business questions

**§7** (privacy policy accurately describes collection): ✅ Half A's new §5 covers what we read per
platform, retention, deletion on disconnect, and the four things we never do with it. ⚠️ Its
retention sentence inherits finding 2 — it states a 30-day window as though it were the agreed
position. If finding 2 resolves toward "store nothing durable", that copy must change with it.

**§16** (no marks or logos; no publicising the relationship): ✅ no Yahoo logo or mark anywhere; the
only Yahoo strings are the required attribution and the plain-text platform label. ⚠️ **One thing to
watch:** §16 permits the Cover Page attribution and §5 display, and forbids "public statements
regarding the existence of this Agreement or the relationship". Naming Yahoo as a platform we can
import from — in the privacy policy and the changelog — is factual, is required by §7, and is not a
statement about the *relationship*. But **marketing copy that reads as a partnership** ("official
Yahoo integration", "we work with Yahoo") would cross the line. Worth a note wherever launch copy is
written.

**§2.c.iv** (no sale, lease or sublicense of Yahoo Fantasy Information): ✅ our paid tier gates *our*
projections; the Approved Use Case explicitly contemplates "Credence Sports **subscribers**". A user
pays for our analysis, not for access to their own Yahoo data.

**§2.c.xi** (no use "in a product or service that competes with products or services offered by
Yahoo"): ⚠️ **a business judgement, and it is not mine.** Yahoo Fantasy offers rankings, projections
and draft tools; so do we. Yahoo signed this agreement with the Approved Use Case in front of them,
which is a strong indication they do not read our product as competing — but the clause exists, §6
lets Yahoo terminate "immediately for any reason or for no reason", and §9 caps their liability at
$1,000. ⏭️ Worth being clear-eyed that Yahoo access is revocable at will, and that no part of the
product should become load-bearing on it.

---

## ⏭️ What I recommend, in order

1. **Decide finding 2** (§2.c.vii). It blocks Half B. Ask Yahoo for a written retention allowance
   first — it is the cheapest path and §17 provides for it. If that fails, choose between narrowing
   what is stored and dropping durable storage for Yahoo.
2. **Get a reading on finding 6** (§2.c.x, "present"). If strict, aggregate the league comparison
   server-side — a small change worth making anyway.
3. **Add the §3.d breach-notification runbook entry.** Half a page, no code.
4. **Watch the launch copy against §16** — factual platform naming is fine, partnership language is
   not.

## What this branch ships

| | |
|---|---|
| Attribution moved into the page `<footer>` (Cover Page) | `platform-attribution.tsx`, `site-footer.tsx`, `providers.tsx` |
| The import screen credits the league LIST, not only the preview | `league-import.tsx` |
| §6 account-wide termination purge | `dynamo.iter_platform_league_holders`, `scripts/purge_platform_data.py` |
| Guards for all of the above | `test_nf_c0_yahoo_halfa_compliance.py` (30 cases) |
| RED proof | `nf_c0_yahoo_halfa_red_proof.py` — **22/22 RED** |

⛔ **It does not change what is stored or for how long.** That is finding 2, and it is the PM's call.
