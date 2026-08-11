# NF-EPIC 1 — Entitlement enforcement: audit and close

**Date:** 2026-08-10 · **Branch:** `nf-epic1` · **Spec:** `nf_delivery_epic.md` §5 (E9.56 / E9.8-P2 / E9.57)
`best_alpha = 0`. Nothing here changes a model or a bet.

> ## ⭐ RESOLVED — PM chose **Option C**, and it shipped (2026-08-10)
>
> The audit below found one open leak (§4): `fpStd`, `fpHalf` and the raw stat line reached
> anonymous callers, gated only by which component drew them. **The PM ruled the raw stat line
> PAID** — it is the re-scorable projection substrate, not the shop-window summary — and chose
> **Option C: split the payload and score the free personalized league server-side.**
>
> Shipped in this branch:
> - `/fantasy/nfl/projections` no longer carries any scorable stat, `fpStd` or `fpHalf`. The paid
>   set is **derived from the scorer's own `STAT_FIELD` map**, so a new scorable stat is withheld
>   automatically instead of shipping public by default.
> - The paid half moved to `/fantasy/nfl/projections-full`, behind `require_fantasy_access`.
> - A free account keeps G100-C1's one personalized league: it is scored **on the server**
>   (`/fantasy/nfl/league-board`, `/fantasy/nfl/my-teams`), so the browser receives a board it could
>   not have computed and never sees the substrate.
> - The public blob is still **byte-identical for every caller**, so G100-D1's CDN cache survives.
> - `contrib` stays public (PM Q3): attribution is show-our-work transparency.
>
> **§4's "the leak cannot be closed by redaction" conclusion was too pessimistic, and §8 records
> exactly why.** The acceptance-criteria reconciliation the audit asked for is §7.

---

## Verdict

**Every boundary the server is able to enforce, it enforces — verified against LIVE production
payloads, not fixtures.** 24 surfaces checked across both axes; no server-side leak found, nothing
re-built, no code changed.

**One finding requires a PM decision before E9.8-P2**, and it is not a defect to fix: three values
the pricing page treats as paid (`fpStd`, `fpHalf`, and the raw stat line) ship in the anonymous
payload and are gated only by which component renders them. That is the shipped freemium design,
documented and operator-approved on 2026-08-08 — and §5's acceptance criteria, written before it,
call the same thing release-blocking. §4 shows the gate is *structural*: it cannot be closed by
redaction without withdrawing G100-C1's free personalized league.

---

## 1. The card's premise is stale — read this first

§5 specifies a contract that **was deliberately retired**:

> a free payload carries `{locked:true, rank/tier/projection/p10/p90/projectedStats = null}` for
> everything outside top-10-overall / top-3-per-position

That is E9.56's locked-marker redaction. The **freemium build (2026-08-08, GROWTH-100 §1/§6/§14)**
replaced it, moving the boundary from **season** to **capability**. The retirement is explicit in
three places, and one of them forbids exactly the "fix" §5 would imply:

- `app/backend/services/entitlement.py` header — *"no live route calls it any more… ⛔ Do not reason
  from it about current behaviour, and do not re-introduce a call to it without an operator decision"*
- `docs/freemium_tier.md` — the full rationale
- root `CLAUDE.md` — *"A FULLY-FREE GENERIC BOARD IS SCRAPEABLE, AND THAT IS AN ACCEPTED COST, not an
  oversight… Do not 'fix' this by re-locking values."*

So this audit measures the **shipped** boundary. Re-implementing top-10/top-3 would have contradicted
a standing operator instruction. (This is the E9.61 lesson verbatim: *pre-flight a card against the
running system — a card written days before pickup can carry a false premise*.)

### Two §5 mechanisms were never built, and correctly so

| §5 requirement | Status |
|---|---|
| `player_detail_unlocks = 3` | **Does not exist.** Grepped repo-wide: no counter, no state, no route. Player pages are free. |
| `draft_optimizer_runs = 1` | **Does not exist.** No run counter anywhere. |
| `overall_values_visible = top 10` / `per_position = top 3` | **Retired.** Free board carries all 858 rows, unredacted, by design. |

These are not gaps against the current tier — they are artifacts of the model that was replaced.
⛔ Do not "restore" them without a pricing decision.

---

## 2. The boundary as shipped

| Capability | Tier | Enforced by |
|---|---|---|
| `GENERIC_BOARD` — one preset board (`full_ppr`/12), projections, ranges, ADP, player pages | **FREE**, anonymous included | n/a (free by design) |
| `PERSONALIZATION` — board re-scored for *your* saved league, VOR vs your roster, saved state | PAID (+ free quota of **1**, G100-C1) | `require_personalized_league_access`, quota at create **and** serve |
| `DECISION_SUPPORT` — draft optimizer, weekly tools | PAID | `require_fantasy_access` (server) + `FantasyGuard` (render) |

**14 preset boards published; 1 free, 13 paid** — confirmed live from the manifest
(7 configs × 2 sizes; `freeBoard: {config: full_ppr, size: 12}`).

---

## 3. The enumerated audit

All evidence below is **live production**, captured 2026-08-10 against
`https://api.credencesports.com` and `https://www.credencesports.com`.

### 3a. Axis 1 — every surface that RETURNS or RENDERS gated data

| # | Surface | Check | Result | Evidence |
|---|---|---|---|---|
| 1 | `GET /fantasy/nfl/board` free preset | anonymous 200 | ✅ PASS | `200`, 240,095 B, 858 rows, bare list |
| 2 | `GET /fantasy/nfl/board` paid **config** | anonymous refused | ✅ PASS | `half_ppr`/12 → `403` |
| 3 | `GET /fantasy/nfl/board` paid **size** | both coordinates gate | ✅ PASS | `full_ppr`/**10** → `403` |
| 4 | All 6 config×size probes | exactly one is free | ✅ PASS | `full_ppr`/12 → 200; other 5 → 403 |
| 5 | `GET /fantasy/nfl/projections` | free by design | ✅ PASS (see §4) | `200`, 858 players |
| 6 | `GET /fantasy/nfl/manifest` | free, marks the free preset | ✅ PASS | `free:true` on `full_ppr` only |
| 7 | `GET /fantasy/mlb/prospects/board` | admin-only | ✅ PASS | anonymous `401` |
| 8 | `GET /fantasy/mlb/prospects/manifest` | admin-only | ✅ PASS | anonymous `401` |
| 9 | `GET /fantasy/leagues` | identity required | ✅ PASS | anonymous `401` (sign-in, not pay) |
| 10 | `GET /fantasy/nfl/my-teams` | identity + quota | ✅ PASS | anonymous `401` |
| 11 | `GET /fantasy/import/*` (9 routes) | quota-gated | ✅ PASS | anonymous `401` |
| 12 | `POST /fantasy/league/preview` (MLB) | admin-only | ✅ PASS | anonymous `401` |
| 13 | `GET /fantasy/nfl/track-record/*` | intentionally public (NF3.2/NF-TR1) | ✅ PASS | `200`, past seasons only |
| 14 | `GET /fantasy/nfl/featured-player` | intentionally public (E9.46) | ✅ PASS | `200` |
| 15 | **Forged-token escalation** | unsigned `{"cognito:groups":["subscriber","admin"]}` | ✅ PASS | paid board still `403` — `jwt_verify` refuses |
| 16 | **Direct S3** on the board bucket | no public read | ✅ PASS | `403 AccessDenied` on board + projections keys and on bucket root |
| 17 | **Static assets** in `frontend/public/` | no board JSON shipped | ✅ PASS | no `*.json`; the legacy `/data/nfl-fantasy/` path is gone |
| 18 | **Frontend bundle** | no embedded board values | ✅ PASS | only `e2e/fixtures/` (not served) carry `fpStd`/`fpHalf` |

### 3b. Axis 2 — every path that CREATES a personalized/gated view

The G100-C1 lesson: enumerate **creators**, not just renderers — that story shipped a renderer gate
while the importer ignored the quota.

| # | Creation path | Check | Result |
|---|---|---|---|
| 19 | `POST /fantasy/leagues` | quota enforced server-side | ✅ PASS — quota from caller's entitlement → `409`; `dynamo.put_fantasy_league` clamps `min(quota, MAX_LEAGUES_PER_USER)` |
| 20 | `PUT /fantasy/leagues/{id}` | cannot be used to create | ✅ PASS — 404s unless the record already exists; cap deliberately not applied to edits |
| 21 | **Platform import** (Sleeper/ESPN/Yahoo) | cannot bypass the quota | ✅ PASS — import routes are **preview-only**; no league write exists in the router. The save goes through #19 |
| 22 | `GET /fantasy/nfl/my-teams` | serve-side cap catches the lapsed subscriber | ✅ PASS — `leagues_within_quota`, oldest-first by `created_at` |
| 23 | MLB league create (`POST /league/…`) | gated | ✅ PASS — `require_fantasy_access` (router) **+** `get_admin_user` (route) |
| 24 | Yahoo OAuth callback (`public_router`) | no data egress | ✅ PASS — token exchange only |

### 3c. Cache correctness — tier is in the key

The hazard: a subscriber-warmed entry served to an anonymous visitor, or the reverse.

| Arm | Expected | Live result |
|---|---|---|
| Anonymous free board | shared-cacheable | `public, s-maxage=900, stale-while-revalidate=3600` |
| **Any request carrying `Authorization`** | never shared | `private, no-store` |
| Anonymous **403** on a paid board | never cached | `no-store` |
| Anonymous projections | shared-cacheable | `public, s-maxage=900…` |
| **All four arms** | keyed on the token | `Vary: Authorization` present on **every** response |

Both halves are required and both are present: `Vary` alone still lets a URL-keyed cache mix bodies;
`private` alone still lets an anonymous entry be reused. Non-200s are never cached (E9.26b).

### 3d. The CDN proxy (`/api/public/…`) — G100-D1's edge

| Probe | Expected | Live result |
|---|---|---|
| free board | 200 | `200`, 240,095 B (byte-identical to the API) |
| paid **config** (`half_ppr`) | unreachable | `422` — regex rejects, param dropped, upstream refuses |
| paid **size** (`10`) | unreachable | `422` |
| request carrying `Authorization` | token ignored | `422` (identical to the un-tokened probe) |
| open-relay: `leagues`, `nfl/my-teams`, `picks/today` | not proxied | `404` |

The edge **cannot ask the upstream a question whose answer depends on the caller** — a stronger
guarantee than remembering not to forward the header.

---

## 4. The finding — three render-only gates, and why they are structural

### What leaks

`GET /fantasy/nfl/projections` is anonymous, `200`, and carries for all 858 players:

- `fpStd` and `fpHalf` — the two reference scorings the Projections picker and the player-page tiles
  gate behind a `LockChip`
- the **complete raw stat line** (`rec`, `recYds`, `tgt`, `passYds`, `rushYds`, …) — gated on the
  player page for an unentitled viewer

Measured live, no account required:

```
Ja'Marr Chase   fpPpr 261.4 (free)   fpHalf 213.5 (gated)   fpStd 165.6 (gated)   rec 95.7
  identity:  261.4 − 0.5×95.7 = 213.5 ✓      261.4 − 1.0×95.7 = 165.7 ≈ 165.6 ✓
```

`curl` recovers every gated value. So does the network tab. Against §5's *"Browser dev tools cannot
recover gated values"* and its **prohibited pattern** (*full board sent → frontend hides*), this is a
literal failure.

### Why it cannot be closed by redaction

This is the part that turns it from a defect into a decision. Three facts compose:

1. **The stat line makes the totals derivable.** `half = full − 0.5·rec`, `standard = full − 1.0·rec`
   — verified above to a tenth. Redacting `fpStd`/`fpHalf` while the stat line ships accomplishes
   **nothing**; the reader does it in their head.
2. **The stat line is load-bearing for a shipped FREE feature.** `lib/league-scoring.ts::scoreRow`
   computes `pts += weight × rawStat[field]` — the client scorer reads the raw stat line directly.
   `buildBoard` is what powers `useCustomBoard`, i.e. **G100-C1's one free personalized league**.
   Withholding the stat line from a free account withdraws that feature.
3. **Varying the payload by caller costs the CDN.** The free surfaces are byte-identical for every
   caller, which is precisely what makes G100-D1's edge cache legal on the 1.3 MB projections blob —
   the single biggest anonymous cost lever. Serving a reduced anonymous payload re-introduces the
   "same URL, two bodies" hazard and puts every anonymous view back on the Lambda.

⇒ The render gate is not laziness; **it is the only gate available** while the free tier includes a
personalized league. The operator's own copy guard
(`test_the_stat_line_lock_does_not_claim_to_stop_scraping`) already forbids the code from claiming
otherwise, which is direct evidence this was understood when it shipped.

The same root cause means **league scoring for any format is reproducible in the browser** from the
free payload. The server enforces how many leagues you may *store* and be *served*; it cannot
enforce arithmetic a visitor runs locally on data we publish.

### The decision this needs

Three options; **(a) is the recommendation** — it is the shipped, documented state:

| | Option | Cost |
|---|---|---|
| **(a)** | **Accept and amend §5.** Record that "no full-board leak" was superseded on 2026-08-08; the tier is capability-based and the generic board is scrapeable by design. | None. Requires a written PM amendment so the acceptance criteria stop asserting something untrue. |
| (b) | Withhold the stat line from unentitled callers. | **Withdraws G100-C1's free league** and breaks CDN byte-identity → every anonymous view back on the Lambda. |
| (c) | Move league scoring server-side. | New compute path; `fantasy_engine` (pandas/numpy) cannot be imported into the API Lambda — a second, driftable scorer. Large, and it still cannot un-publish the stat line. |

---

## 5. What was NOT changed

No source changed. The enforcement is already correct everywhere it can be, and the one finding is a
pricing decision the session is not entitled to make — re-locking is forbidden by `CLAUDE.md` and by
`entitlement.py` without an operator call. Per the brief: *a clean audit that ends the epic is the
success case; don't invent work.*

**Existing guard coverage is comprehensive** — `254 tests pass` across `test_freemium_tier.py`,
`test_g100_c1_free_league.py`, `test_e9_56_entitlement.py`, `test_e9_56b_public_surface.py`,
`test_fantasy_entitlement.py`, `test_g100_d1_cost_guardrails.py`, including a forged-token case, a
byte-identity case, a both-coordinates case, the cache-partition case, the CDN-allowlist case, and
the stat-line derivation pinned as executable arithmetic. No new guard is warranted: every property
this audit verified live is already pinned, and adding a duplicate clause would risk the E9.60
coupling trap for no gain.

### One forward-looking risk, logged not fixed

`open_projections_payload` returns `{**data}` verbatim — **no allowlist**. Today that is correct
(the generic payload is free in full), but it means any field a future exporter adds to
`projections.json` ships publicly on the next publish, with no code change and no test failure. The
retired path had `test_an_unknown_new_field_is_locked_by_default`; the live path has no analog. If a
future NF-D story adds a paid-class column there, it leaks silently. **Recommendation:** when the
next exporter field lands, add a reviewed field registry to the publish step. Not actioned here —
speculative today, and the fix belongs with the field that motivates it.

---

## 7. The acceptance-criteria amendment (PM-approved, 2026-08-10)

§5 was written before the freemium build and carries this line:

> Browser dev tools cannot recover gated values.

Read literally against the *pre-freemium* product — where the whole current-season board was
paid — that line was satisfiable. The 8 Aug freemium decision made the generic board free **and
deliberately scrapeable**, so the sentence stopped describing the product on that date. It was not
failed; it was superseded, and the audit found it still being carried as if it were live.

**The standard we actually hold, and now meet:**

> **No PAID value is recoverable without paying.** The generic board — rankings, our PPR
> projection, the 80% ranges, market ADP, `contrib`, the player pages — is free to everyone
> including anonymous callers, by design, and is scrapeable. That is the acquisition wedge and an
> accepted cost. What must never be obtainable free is the PAID substrate: the raw stat line, the
> two paid reference scorings, the 13 paid preset boards, and personalization.

⚠️ **Recorded, not papered over.** Three things stay true in the record: the pre-freemium line was
correct when written; the freemium build superseded it on 8 Aug; and between 8 Aug and 10 Aug the
product did NOT meet either standard, because the stat line was paid in the UI and free on the
wire. Option C closed that gap — it did not retroactively make the interim period fine.

**§5 checklist items that are now decided rather than open:**

| §5 item | Disposition |
|---|---|
| `overall_values_visible = top 10` / `per_position = top 3` | ⛔ **Retired 8 Aug.** The free board carries all 858 rows unredacted. Do not restore without a pricing decision. |
| `player_detail_unlocks = 3` | ⛔ **Never built, and correctly so.** Player pages are free. |
| `draft_optimizer_runs = 1` | ⛔ **Never built.** The optimizer is gated by capability, not by a run counter. |
| "Locked marker schema" | 🗄️ Retired with the E9.56 redaction; the code is kept, unused, as the withdraw-the-board mechanism. |
| "Server-side board filtering" | ✅ Met differently: 13 of 14 preset boards 403, and the paid substrate is a separate authenticated payload. |

---

## 8. Why §4's "cannot be closed by redaction" was too pessimistic

The audit concluded the leak was structural. That was right about the *constraints* and wrong about
the *conclusion*, and the correction is worth recording because the reasoning error is reusable.

§4 established three true facts — the totals are derivable from the stat line; the client scorer
needs the stat line; a caller-dependent payload forfeits the CDN — and then treated them as jointly
binding. They are not. **All three are constraints on WHERE THE ARITHMETIC HAPPENS, and only one
placement was considered.** Once scoring moves to the server:

- the stat line never needs to reach a free browser, so fact 2 dissolves;
- the totals cannot be derived from a stat line the caller does not have, so fact 1 dissolves;
- and the PUBLIC blob stays byte-identical for every caller (the paid half is a *different URL*,
  not a different body on the same URL), so fact 3 never applied to the split at all.

The mistake was assuming the paid half had to travel on the same URL. It is the same shape as this
repo's "documented ≠ actually served" family: an inherited assumption about the delivery mechanism
was carried as if it were a property of the data.

⚠️ **The one fact from §4 that still stands, and it is the important one:** account creation is
free, instant and self-serve, so a gate at "signed in" is not a gate. That is why the stat line is
withheld from *free signed-in accounts* too, not merely from anonymous ones — and it is why
Option B (withdraw the free league) and Option C (score it server-side) were the only two real
options.

---

## 9. Known residual — bounded, not zero

Recording this because "no leak" would be an overclaim, and an overclaim is what makes the next
audit distrust this one.

**A free account can still probe the substrate through its own league.** The server scores any
league config the caller saves, so a determined user could save a league whose scoring is a single
stat at weight 1.0, read the resulting `pts` column, and recover that stat for every player — then
repeat per stat. It is a real path and it is deliberately bounded rather than closed:

| Bound | Effect |
|---|---|
| **Free quota = 1 league** (`FREE_PERSONALIZED_LEAGUE_QUOTA`) | Only one config at a time; each additional stat requires an edit + refetch. |
| **~50 scorable stats** | ~50 sequential edit-and-read cycles for one full stat line. |
| **G100-D1 per-IP rate limiter** | Caps the cycle rate from one address. |
| **Board rounding** (`round(x, 1)`) | Recovers a 1-decimal approximation, not the stored value. |
| **Identity required** | Every request carries a Cognito `sub`, so the activity is attributable — unlike the previous `curl`, which was anonymous. |

⇒ the honest statement is **"the substrate is no longer served to a free caller, and reconstructing
it is now slow, rate-limited and attributable"**, not "reconstruction is impossible". Closing it
completely would mean validating saved configs against a plausibility rule, which would refuse real
leagues — a worse trade for a path that costs ~50 authenticated round trips to walk.

---

## 10. E9.8-P2

*(§6 below is the original pre-decision verdict, kept for the record.)*

**Cleared on the enforcement leg.** The PM's Q4 ruling: Stripe ships in parallel, and Option C is a
pre-launch fast-follow that must land before traffic is driven to `/subscribe`. Option C is in this
branch.

Answering the question the PM asked to be answered plainly — *is any paid value (stat line /
`fpStd` / `fpHalf`) recoverable by an anonymous or free caller?*

**No — pending the live re-verification below, which cannot run until `deploy.sh` does.** The
backend change is what closes it, and this repo has no CD for the API Lambda, so the code being
merged is not the same event as the leak being closed.

⏭️ **Operator steps, in order** — full commands in the handoff:
1. `./infrastructure/lambda/deploy.sh` (the leak is open until this runs).
2. Re-run the leak repro anonymously and confirm no `fpStd` / `fpHalf` / stat line.
3. Confirm the public blob is still byte-identical and the paid one is `private, no-store`.
4. PM live walk: anonymous + signed-in free account.

---

## 6. E9.8-P2 *(original, pre-decision — superseded by §10)*

**Unblocked on the enforcement leg, conditional on one PM sign-off.**

- ✅ No server-side leak. Every gated surface refuses anonymous callers; the 13 paid boards 403 on
  both coordinates; forged tokens are refused; S3 is private; the CDN cannot reach a paid board or
  relay; caches are partitioned by tier.
- ✅ Counts are server-authoritative: the league quota is enforced at create **and** serve, and by
  the only creation path that exists.
- ⚠️ **Required before flipping Stripe to live:** a written decision on §4 — option (a) plus an
  amendment to §5's acceptance criteria. Nothing technical blocks; what blocks is that the epic's
  written criteria currently assert a property the product deliberately does not have, and shipping
  against them unamended would record a false pass.
- ⏭️ **PM live walk (the sign-off the brief reserves):** the logged-out arm is captured above; the
  **signed-in free-account arm** needs a real token this session could not mint. Its behaviour is
  pinned by `test_a_signed_in_non_subscriber_is_refused_a_paid_preset` and
  `test_a_signed_in_free_account_reaches_personalization_with_a_quota_of_one`, but a live walk is the
  honest confirmation.
