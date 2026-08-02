# MLB Edge-E8.2a — CBS Fantasy Baseball ACCESS PROBE (spike)

**Run:** 2026-07-31 · **Target:** `https://friction.baseball.cbssports.com/teams` (operator's own
league) · **Type:** research spike only — no production code, no committed integration, nothing
persisted beyond this memo · **Gates:** E8.2 Path B (CBS auto-import)

## Recommendation: **NO-GO** on CBS auto-import. E8.2 ships **Path A (manual roster upload) only.**

This is an earned NO-GO, not a default — all four plausible compliant paths from the story prompt
were tested live against the real target, not assumed from docs. Every path failed for an
independent, verifiable reason; none failed merely because it "looked hard."

---

## 1. What was tried, and what happened

### (a) Documented CBS Fantasy read API
CBS ran a genuine third-party "Fantasy Platform" developer program (launched 2012, REST API v3.0,
hosted at `developer.cbssports.com`) — this was real and, per community references, at one point
open to outside app developers. **It is dead today:**
- `developer.cbssports.com` does not resolve to a serving origin. `WebFetch` → `ENOTFOUND`. A raw
  `dig` shows only a CNAME to CBS's Fastly edge (`cbs-digital-ipv4.map.fastly.net`) with no
  resolvable A record via `WebFetch`'s resolver, and a direct `curl` against the host times out
  (`000`) — there is no live application behind it, just a dangling DNS entry.
- No current CBS-hosted developer/API documentation page exists anywhere in search results;
  everything that surfaces is 2012-era press releases or third-party archives of the old docs.
- **Verdict: NO-GO.** The program is discontinued; there is nothing to integrate against.

### (b) Public / shareable / read-only league view, no auth
- CBS's own Commissioner help docs describe a "make my league public" toggle, but that setting
  governs who can **join** the league, not anonymous **viewing** of rosters — no public/read-only
  league-viewer product surface was found.
- CBS's own "invite link" sharing mechanism (per CBS help content) still requires the recipient to
  **log in with a CBS Sports account** before anything renders.
- **Live proof against the actual target:** `GET https://friction.baseball.cbssports.com/teams`
  unauthenticated → HTTP `302` → `https://www.cbssports.com/login?product_abbrev=mgmt&xurl=...` —
  a full login wall, zero roster data exposed pre-auth.
- **Verdict: NO-GO.** No no-auth read surface exists for a private league (and this one is private).

### (c) Underlying JSON/XML endpoint the `/teams` page itself calls
This is the path the story correctly flags as the realistic winner for a private league — **but it
is foreclosed here on policy grounds, independent of whether it's technically reachable:**
- `robots.txt` for the entire fantasy-game application is a blanket disallow, checked at three
  levels:
  - `baseball.cbssports.com/robots.txt` → `User-agent: * / Disallow: /`
  - `friction.baseball.cbssports.com/robots.txt` → `User-agent: * / Disallow: /`
  - (contrast) `www.cbssports.com/robots.txt` — the marketing/editorial site — is NOT blanket-disallowed
    (has scoped disallows like `/data/*`, `/login*`, `/user*`); the blanket block is specific to the
    **fantasy game application subdomains**, not the whole company.
- This repo's own access discipline (stated directly in the E8.2a story and the NF-D8 precedent) is
  **"Anthropic honors robots.txt — a hard stop."** A blanket `Disallow: /` on the exact host that
  serves league rosters means building or operating any automated fetch against that host — even
  one that inspects/replays a network call the authenticated browser session makes — is off the
  table by policy, regardless of the login wall.
- Because of the login wall (see (b)), the page's own client-side network calls were never even
  observable pre-auth — a further practical blocker on top of the policy one.
- **Verdict: NO-GO — on both policy (robots.txt) and practical (auth-gated, unobservable) grounds.**

### (d) OAuth / user-authorized token flow
- No CBS-hosted OAuth/delegated-auth grant flow for third-party fantasy data access was found
  anywhere in current CBS documentation, help content, or search results.
- The one concrete artifact of how third parties actually pulled CBS fantasy data historically is a
  community Ruby gem (`geoffharcourt/cbs_fantasy_sports_api_token_fetcher`). Its own README shows the
  "auth flow" is: submit the user's **raw CBS email + password** directly to the fetcher to obtain a
  token (`CbsFantasySportsApiTokenFetcher.new(league_name:, password:, user_id:).fetch`). **This is
  exactly the pattern the story's hard constraint forbids** — it requires the integration to receive
  and handle the user's password, not a delegated/OAuth exchange. Even setting the credential
  problem aside, it authenticates against the now-dead `developer.cbssports.com` API from (a).
- For contrast (not in scope, noted for the record): Yahoo Fantasy Sports publishes a live,
  documented OAuth2 API today (`developer.yahoo.com/fantasysports`) — i.e. the "OAuth for a fantasy
  platform" pattern is real and used elsewhere; CBS specifically does not currently offer it.
- **Verdict: NO-GO.** No compliant delegated-auth mechanism exists; the only known token flow
  requires exactly the credential handling the story prohibits, against a dead API besides.

### ToS / Acceptable Use Policy
`cbssports.com/info/about/tos/aup` has no explicit anti-scraping/anti-bot clause, but does prohibit
disobeying "requirements, procedures, policies or regulations of networks connected to the
Service" — which reads back to the robots.txt block in (c). (CBS Interactive's separate ToU URL is
dead — redirects to a generic Paramount brand page post-rebrand — so the AUP is the operative
document found.) No third-party-app/API terms were found (consistent with the developer program
being discontinued).

---

## 2. Per-player fields CBS exposes — **not directly observed, caveated**

The probe never got past the CBS login wall (see (b)), so no live roster JSON/HTML was captured and
no field list can be reported as measured. Do not treat any field-level claim about CBS's roster
data as verified. If E8.2 ever revisits this (e.g. CBS ships a real OAuth program), the field
inventory — including whether minors/bench/IL stash slots are distinguishable from active-roster
slots, which E8.2's availability filter needs — must be captured from a real authenticated payload,
not assumed.

---

## 3. Implication for E8.2

- **Path B (CBS auto-import): omitted.** All four compliant-access options were tried against the
  real target league and failed independently — dead developer API, no public/read-only view, a
  policy-level robots.txt hard stop on the one host that would carry a network-call replay, and no
  OAuth flow (only a credential-handling pattern this program forbids). This is a genuine NO-GO, not
  an untried default.
- **Path A (manual roster upload): stands alone as E8.2's only import path**, per the story's
  guaranteed-floor design — build it regardless of this outcome.
- If CBS ever ships a real third-party OAuth program for fantasy data, this spike should be re-run
  against it specifically (its auth flow, its robots.txt for the OAuth/API host, its field shape) —
  none of today's findings would need to change, they'd just gain a new, currently-nonexistent path
  (d) to evaluate.
