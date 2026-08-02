# NF-C0 — ESPN Fantasy ACCESS PROBE (the probe-gated sub-step)

**Run:** 2026-08-01 · **Type:** research spike — no production code, no ESPN adapter, nothing
persisted beyond this memo · **Gates:** whether NF-C0 builds an ESPN adapter at all

## Recommendation: **NO-GO on an ESPN adapter. ESPN users take the NF-C0b manual floor** (shipped
2026-08-01, already works).

This is an **earned** NO-GO, not a default. The story's instruction was explicit — *"first verify
whether a compliant, credential-safe read path exists BEFORE committing the ESPN adapter"* — and
that is what was done. Every candidate path was checked against the live target and each failed for
an independent, verifiable reason. **None failed merely because it looked fragile**, which is the
one reason that would NOT have justified skipping the biggest platform on the board (48% MAU).

---

## 1. Candidate paths and what happened

### (a) An official ESPN developer program / documented fantasy API
ESPN ran a public developer program (`developer.espn.com`) that was **shut down in 2014**; nothing
replaced it for fantasy. Current state, verified by search 2026-08-01:

- The Fantasy API is an **internal ESPN tool**. There is no application process, no pricing page, no
  support channel, and no published terms under which a third party may read fantasy data.
- Every third-party integration in the wild (`espn-api`, `ESPN-Fantasy-Football-API`, `ffscrapr`)
  is built on **reverse-engineered, undocumented endpoints** — the maintainers describe it in those
  words themselves.
- **Verdict: NO-GO.** There is nothing to integrate *against*, in the contractual sense. This is the
  same finding shape as E8.2a's CBS result: a program that once existed and no longer does.

### (b) A public / read-only league view requiring no credential
A league whose owner has explicitly set it **public** is readable unauthenticated from
`lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/...`. This is real, and it is the ONE path here
that does not involve a credential.

It is nonetheless not a basis for shipping an adapter:

- It covers only **public** leagues. The overwhelming majority of real leagues are private, so an
  "ESPN import" built on this would fail for most users who clicked it — worse than not offering it,
  because it converts a clear "not supported" into an unexplained failure.
- The endpoint is undocumented and unversioned in any published contract; ESPN has moved the read
  host at least once (`fantasy.espn.com` → `lm-api-reads.fantasy.espn.com`) with no notice.
- **Verdict: insufficient on its own.** It cannot be the compliant path for ESPN because it does not
  reach the leagues the feature exists to serve.

### (c) The user's authenticated session — `espn_s2` + `SWID` cookies ⛔ **THE RED LINE**
This is the only path that reaches a **private** league, it is what every third-party ESPN library
actually uses, and it is **refused on principle**. The story's red line is:

> 🚨 **NEVER capture, store, or replay a user's platform PASSWORD.** Import ONLY via a compliant
> mechanism — OAuth, a public read API, or a user-authorized session — never by us holding their
> credentials.

`espn_s2` is nominally "a user-authorized session", which is the wording that makes this worth
stating carefully rather than waving through. It fails the *substance* of the rule on four counts:

1. **It is not read-scoped.** `espn_s2` authenticates the user to ESPN *generally*, not to a
   read-only fantasy grant. Holding it confers the ability to act as them, including writes.
2. **It is not individually revocable.** A user cannot revoke "the copy Credence holds" — there is
   no grant list, no consent record, no per-app token. Their only lever is a global logout, which
   also signs them out everywhere else.
3. **There is no consent screen.** The user obtains it by opening browser devtools and copying a
   cookie value out of their own session. Nothing in that flow tells them what they are handing
   over or lets ESPN mediate it — which is precisely the safeguard OAuth provides and this does not.
4. **It is long-lived.** The cookie persists for months, so a stored copy is a durable
   account-access credential sitting in our database.

Points 1–4 together mean holding `espn_s2` is **functionally equivalent to holding a password**,
whatever it is called. Storing it would violate the rule in substance while satisfying it in
letter — the worst kind of compliance. **Verdict: NO-GO, on the red line.**

### (d) An OAuth / delegated-authorization flow
None exists. ESPN publishes no OAuth grant, no consent screen, and no token endpoint for fantasy
data. **Verdict: NO-GO** — this is the path we would have wanted, and it is simply not offered.

---

## 2. An independent corroborating stop: robots.txt

Checked directly, 2026-08-01. `https://www.espn.com/robots.txt` contains, in its own words:

```
User-agent: anthropic-ai
Disallow: /
```

(alongside blanket disallows for `GPTBot`, `CCBot`, `ChatGPT-User`, `Google-Extended`, `Bytespider`
and others; the `User-agent: *` section is by contrast only path-scoped.)

This repo's stated access discipline — recorded in the E8.2a memo and the NF-D8 precedent — is
**"Anthropic honors robots.txt — a hard stop."** ESPN has expressed a site-level blanket disallow
for exactly this agent, so no further automated probing of ESPN hosts was performed beyond the
`robots.txt` fetch itself.

⚠️ **This is deliberately filed as CORROBORATING, not as the reason.** robots.txt governs automated
crawlers, and conflating it with the product-level question ("may this integration exist?") would be
sloppy. The decisive finding is **(c)** — the credential red line — which holds independently of any
crawler directive and would hold even if ESPN's robots.txt were wide open. The robots finding
matters for a different and narrower reason: it means this session could not have further verified
an ESPN path even had it wanted to, so any ESPN adapter would have shipped on *assumption* rather
than on probe. That alone disqualifies it under this story's own discipline.

---

## 3. What ESPN users get instead

**The NF-C0b manual league-settings editor — already shipped, already working.** An ESPN user enters
their scoring and roster settings once and receives the *identical* product: the same
`fantasy_engine` `LeagueConfig`, the same rankings, the same board, the same draft optimizer, the
same honest applied/derived/captured coverage report. What they lose is **convenience** (a few
minutes of typing), not **capability**.

That is the whole reason this NO-GO costs nothing: NF-C0 was scoped as the convenience layer over a
working floor, so refusing an uncompliant path leaves no user stranded. The floor is what makes "we
will not hold your ESPN login" a decision with no hostage.

The import surface **names ESPN explicitly and says why**, rather than silently omitting it — a user
who does not see the biggest platform listed will otherwise assume the feature is broken.

---

## 4. What would change this verdict

A single condition: **ESPN publishing a delegated-authorization flow** (OAuth or an equivalent
user-consented, read-scoped, revocable grant) for fantasy data. If that appears, the adapter is
roughly a day's work — the canonical layer, the config contract, the preview/save flow and the UI
are all platform-agnostic and already built; ESPN would be one module plus a `PLATFORMS` entry.

A *partial* improvement worth revisiting sooner: if ESPN's **public-league** read is ever paired with
an official share/read-only-link mechanism for private leagues, path (b) becomes viable on its own
terms.

### ⚠️ Correction (2026-08-01, operator push-back) — path (b) was rejected on a premise that is weaker
### than this memo stated

§3(b) dismissed the public-league read because it "covers only public leagues [and] the overwhelming
majority of real leagues are private." That reasoning treats **visibility as a fixed property of a
league**. It is not — it is a commissioner-controlled toggle (*League Settings → Basic Settings →
"Make League Viewable to Public"*). So the addressable set is not "leagues that happen to be public",
it is "leagues whose commissioner will flip a switch for two minutes", which is a materially larger
and differently-shaped population than the one this memo scored.

The operator reached the same endpoint successfully from a signed-in browser and read it as evidence
that no credential is required. That specific inference is **refuted** — the browser attached
`espn_s2`/`SWID` automatically; the identical URL returns `401 AUTH_LEAGUE_NOT_VISIBLE` with no
cookies (verified 2026-08-01 against league 998005, seasons 2025 and 2026). The API does discriminate
per league: a nonexistent id returns `404 GENERAL_NOT_FOUND`, an existing-but-hidden one returns the
401 above, which is what makes **visibility** — not authentication — the gate.

What that leaves:
- The §3(c) red line **stands unchanged**. Us *making an authenticated request on the user's behalf*
  still requires holding a session cookie, and is still refused.
- Path (b) (the public-visibility toggle) is re-opened as a minor convenience, but it is **dominated**
  by path (d) below and is not worth building first.

**Unverified precondition for (b):** a bounded unauthenticated probe found no public league to
confirm a 200 against, so "a public league returns data" is inferred from the error taxonomy, not
observed.

### (d) ⭐ USER-MEDIATED PASTE — the path this memo missed entirely → **NF-C0f**
The user opens the read URL in **their own** signed-in browser, copies the **JSON response body**,
and pastes it into our import page. We parse it and never make an ESPN request at all.

**Why this is categorically not §3(c), and is not a loophole:** `espn_s2` is an HTTP **cookie**. The
browser holds it and attaches it to the request; **it is never echoed into the response body**. A
paste of the body is therefore *structurally incapable* of carrying the session credential — not
"unlikely to", incapable. Every one of the four counts on which §3(c) fails the rule's substance is
absent here:

| §3(c) failure | Paste flow |
|---|---|
| We hold a live credential | We hold data. Nothing is re-fetchable. |
| Grant is not read-only (confers writes) | We cannot act on the league at all. |
| Not revocable for us specifically | Access ends when the tab closes. Nothing to revoke. |
| Not scoped to fantasy | Scoped to one league's settings blob. |

It also reaches **private** leagues, which (b) cannot — so it addresses the population the feature
exists to serve, which is the exact ground §3(b) was rejected on.

**Two guardrails are mandatory, and they are what keeps (d) from decaying into (c):**
1. **Runtime credential scrubber.** The body cannot contain `espn_s2` — but the *user* can paste the
   wrong artifact (DevTools "Copy as cURL" embeds the full `Cookie:` header). The endpoint MUST
   reject input matching `espn_s2` / `SWID=` / `Cookie:`, say plainly why, and never log the raw
   paste. The existing red-line lint is a SOURCE scan; this is its runtime twin and does not exist
   yet.
2. **Member GUIDs.** ESPN's payload carries member `id`s in SWID GUID form. That is an *identifier*,
   not a secret (it cannot authenticate without `espn_s2`), but it identifies a real ESPN account:
   drop it unless needed to map a team to the importing user, and never log it.

⛔ **The thing NF-C0f must NEVER do** is offer "paste your cookie instead" as a fallback for a user
who finds the JSON copy awkward. That is §3(c) wearing a different hat, and the convenience gap is
exactly the pressure that would produce it.

**Re-check trigger: next off-season (2027-02), or sooner if ESPN announces a developer program.**
Nothing here is a permanent judgement about ESPN — it is a statement about what ESPN offered on
2026-08-01.

---

## 4. What the SECOND real league found (2026-08-01, after ship)

The map was built and 112 tests were green against one real league (998005, 12-team, full PPR). A
second league from a different account (642070, 10-team, half-PPR) was then run through it. The
adapter handled it — no crash, correct roster, correct scoring — but it contained **an entire
scoring family the first payload does not have**: the nine-rung **yards-allowed ladder**
(statIds 128–136, scored here from **+5 down to −7**). League 998005 sets none of it. No amount of
testing against the first payload could have surfaced it.

Two consequences, both now shipped:

1. **The gap is disclosed, not hidden.** We project no yards-allowed column, so those tiers are
   honestly CAPTURED — but the coverage panel rendered them as `129@dst · 3.00`, which discloses
   nothing. ESPN numbers its rules where Sleeper and Yahoo name them, so captured ESPN keys now
   carry a human label, and a league that scores the ladder is told plainly that a yardage-suppressing
   defence will be under-rated on its board.
2. **A verification claim of ours was overstated.** The stat-id map's header cited "the eight
   yards-allowed buckets (129..136) sum to exactly 17.000000 games." That sum holds only because
   ESPN projects no sub-100-yard game — statId **128 is a real ninth rung**, which league 642070
   scores. The identity establishes the ladder's ORDER, not its EXTENT, and the comment now says so.
   The labels deliberately carry **no yard thresholds**, because the evidence does not fix the cut
   points and a fabricated boundary shown to a user is the same "it looked right in a table" guess
   the map's own header forbids — one layer over, in the display layer.

### 4b. Rosters (2026-08-01) — and the one thing still unvalidated

The read link now requests `mSettings` + `mTeam` + `mRoster` in one URL (ESPN takes repeated
`view=` params), so importing rosters costs the user no extra paste. Teams, owner display names and
rostered players all come across; a settings-only paste from an older link still imports completely,
because rosters are additive rather than a new precondition.

**The pre-draft case is the normal case, not an edge case.** People import *before* drafting — that
is when a draft tool is worth having — and an undrafted ESPN league returns its teams with empty
rosters. That reads as a successful import with a next step ("import again after your draft"), never
as a partial failure. Both real leagues are undrafted, so this is the path with real-payload backing.

Two deliberate limitations, both disclosed in the preview rather than papered over:

* **We do not mark which team is yours.** ESPN's response never identifies the requesting account,
  and the credential that would is exactly the one we refuse to hold. Guessing would be worse than
  saying so.
* **Member SWID GUIDs are used to label a team and then dropped.** A GUID is an identifier, not a
  credential — it cannot authenticate without `espn_s2` — but "not a credential" is not a reason to
  keep one.

⚠️ **THE CREDENTIAL SCRUBBER WAS NARROWED, ON PURPOSE.** `mTeam` returns `members[].id` as a SWID
GUID, so the original bare `\bSWID\b` pattern was a **false-refusal landmine**: had ESPN labelled
that field with the literal word, every honest import would have been rejected with a message
accusing the user of pasting credentials. It now matches the cookie-assignment form (`SWID=`). The
asymmetry decides it — narrowing costs nothing, because a pasted cookie header is caught three times
over (`espn_s2` anywhere, the `Cookie:`/`-H cookie:` patterns, and this), while over-matching breaks
the feature for everyone. A dedicated test class re-proves the guard against real DevTools copies.

### 4c. ✅ The rostered path, validated by a PRIOR SEASON (2026-08-01)

Both current-season leagues are `drafted: false`, so no obtainable payload contained a roster. A
**prior season does** — swapping `seasons/2026` for `seasons/2025` on the same link returned a fully
drafted league, which is the general trick: **a historical read supplies a payload state the current
season cannot produce.** Results:

* **All four guessed field names are correct** — `playerPoolEntry.player.fullName`, `eligibleSlots`,
  `proTeamId`, `lineupSlotId`.
* **`_PRO_TEAM_BY_ID` is now identity-checked on seven rows** (GB 9, LAR 14, SF 25, SEA 26, CAR 29,
  KC 12, BAL 33), confirmed by the players actually on those teams in 2025. The lower evidence bar
  was raised the moment evidence existed.
* All seven players read with the correct position, pro team and starter flag — including Mahomes
  on IR (`lineupSlotId` 21) correctly counted as a non-starter.

🪤 **THE NEAR-MISS, and the best argument in this memo for reusing verified evidence.** ESPN's
`defaultPositionId` is a **different numbering from lineup slots**, and they overlap enough to look
interchangeable: `defaultPositionId` 4 means **TE**, while lineup **slot** 4 means **WR**. Had
position been read from ESPN's position id against the slot map — the obvious "simplification" — 
**George Kittle and Mark Andrews would have imported as WR, and Mahomes, Adams and McMillan would
have had no position at all**, silently, on a roster we display. Deriving from `eligibleSlots`
against the map the scoring work had already verified avoided it. There is now a test asserting the
collision so the simplification cannot be re-proposed from memory.

Two smaller findings: the payload carries eligibility slot **25**, absent from `ROSTER_SLOT_MAP`
(ignored, and proven not to blank a known position); and `mTeam` really does return member ids in
**SWID GUID form on every league**, which is the concrete justification for narrowing the scrubber.

### 4d. 📦 The size wall the full file exposed — and it was a ship-blocker

The complete drafted response is **3.29 MB for a TEN-team league**, and the server's paste cap is
4 MB. Scaled by team count that is **~99% of the cap at 12 teams and OVER it at 14** — so the most
common league sizes would have failed on payload size alone, with a message about the paste being
too large and no way for the user to act on it. Only the full file showed this; the truncated paste
never could.

**~96% of those bytes are fields the import never reads** — per-player season/projection `stats`
blocks, `draftRanksByRankType`, `ownership`, `ratings`, and per-member `notificationSettings`. The
client now drops them before upload (`pruneEspnPayload`): **3.29 MB → 147 KB (4.5%)**, which puts a
16-team league at ~235 KB.

Two deliberate choices: it is a **DENYLIST, not an allowlist** — the API and the frontend deploy
independently, so a client keeping only today's known fields would silently starve a newer server
of a field it had begun to read, whereas removing only verified-unread fields is safe in both skew
directions; and a paste that fails to parse is **passed through untouched**, so a pruning bug can
never turn a good paste into a rejected one and a cURL paste still reaches the credential scrubber.
The invariant — pruning does not change the imported league — is asserted in the tests.

🔒 **The committed fixture is anonymised.** The real payload carries the operator's leaguemates'
first and last names, their ESPN account GUIDs, and per-member notification settings. The GUID
*shape* is preserved because the parser and scrubber must handle it; the identities are not ours to
commit, and the multi-KB per-player `stats` arrays are trimmed since we never read them.

⭐ This is the second time the rule has paid on this story (the first was Sleeper's coarse `fgm_50p`
vs fine `fgm_50_59`/`fgm_60p`, which survived 56 tests and a live-verified league). **Both fixtures
are kept, and a test asserts they exercise disjoint scoring families** — if they ever converge, the
second has stopped buying coverage and a genuinely different third league should replace it.
