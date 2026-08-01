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

**Re-check trigger: next off-season (2027-02), or sooner if ESPN announces a developer program.**
Nothing here is a permanent judgement about ESPN — it is a statement about what ESPN offered on
2026-08-01.
