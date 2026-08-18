# NF-C-LDA-0 — live-draft assistant FEASIBILITY SPIKE (ESPN, Chrome extension)

**Run:** 2026-08-18 · **Type:** de-risking spike — no user-facing ship, no changelog · `best_alpha=0`,
no edge claim · **Gates:** how the overlay story is built (and whether it is built at all)

---

## 0. Verdict

The spike asked two questions. **They came back with different confidence, and conflating them
would misreport the result**, so they are graded separately.

| # | Question | Verdict | Basis |
|---|---|---|---|
| 2 | Can we resolve ESPN's players to OUR ids? | ✅ **GO — MEASURED** | 172 real rostered players, **98.8%** resolved, **0.0% join failures** |
| 1 | Can we reliably READ the live ESPN draft state? | 🟡 **CONDITIONAL GO — INSTRUMENTED, NOT OBSERVED** | probe built; a structured source is evidenced in committed payloads, the LIVE pick stream is unconfirmed |

**Overall: GO on the half that was the real risk, and the other half is one operator mock draft from
a verdict.** The instrument that settles it is built, loadable and self-reporting.

⚠️ **Why question 1 could not be closed in-session, stated plainly rather than buried.** ESPN's
`robots.txt` carries `User-agent: anthropic-ai / Disallow: /`, and this repo's standing access
discipline is *"Anthropic honors robots.txt — a hard stop"* (`docs/nf_c0_espn_access_probe.md` §2).
So no ESPN page was fetched, and no live draft room was observed. Everything below about the live
read is derived from **payloads already committed to this repo** or is labelled a hypothesis for the
capture to confirm. ⛔ The one thing this memo does not do is dress an inference up as an
observation — that is the failure mode a spike exists to prevent, not commit.

---

## 1. Question 1 — the read source

### 1.1 The recommended source, and why

**Recommend tier B — the draft-state responses the room already requests — with tier A (in-page JSON
state) as the equal-ranked fallback, and tier C (DOM text) explicitly refused as a primary.**

The reasoning is not "JSON is nicer than HTML". It is that **tier C cannot support the break
detection this feature needs** (§4): rendered text has no version, no contract, and no way to
distinguish "ESPN restyled the room" from "no picks have happened yet". A draft assistant that
cannot tell those apart shows stale or empty state as though it were live — the
confidently-wrong-and-renders-perfectly class this repo has been bitten by repeatedly (E9.46
headshots, NF-K1's missing K/DST, INC-40's misplaced monitor).

### 1.2 What is EVIDENCED, versus what is HYPOTHESIS

This distinction is the memo's load-bearing honesty, so it is a table rather than prose.

| Claim | Status | Evidence |
|---|---|---|
| ESPN serves league state as **structured JSON**, selected by repeatable `view=` params | ✅ **evidenced** | `betting_ml/tests/fixtures/espn_league_642070_2025_drafted.json` — a committed real response |
| That payload carries a **`draftDetail`** object | ✅ **evidenced** | present as `{"drafted": true, "inProgress": false}` — and it arrived **without being requested** (`READ_VIEWS` is `mSettings`/`mTeam`/`mRoster`) |
| Each player carries a **stable numeric ESPN id** | ✅ **evidenced** | `player.id` on 172/172 rostered players |
| Player identity fields are stable and typed | ✅ **evidenced** | `fullName`, `proTeamId`, `eligibleSlots` — all four field names verified in NF-C0 §4c |
| `view=mDraftDetail` returns a **`picks[]`** array (pick #, team, player id) | 🟡 **hypothesis** | the natural reading of the `draftDetail` stub above; **not observed** |
| The live room pushes picks over a **WebSocket** | 🟡 **hypothesis** | probe instruments it either way |
| State hangs on a specific global (`window.__espnfitt__` etc.) | 🟡 **hypothesis** | ⛔ deliberately **not** hardcoded — see below |
| The `kona_player_info` pool endpoint currently works | ❌ **NOT evidence** | `espn_source.py` codes against it, but `espn_benchmark` **is unlanded in the lake** (checked: `No files in log segment`) — so nothing here demonstrates it was ever used successfully |

That last row is included because it was the tempting citation. The module exists and reads well;
the artifact it would have produced does not exist, so it proves nothing and is not leaned on.

### 1.3 The probe is SHAPE-directed, not NAME-directed

`extension/src/main-world-probe.js` does **not** look for a remembered global name. It scores every
window object and every `<script type="application/json">` blob by **how many draft-shaped keys it
carries** (`draftDetail`, `picks`, `overallPickNumber`, `playerPoolEntry`, `eligibleSlots`, …).

This matters because a name-directed probe answers *"is the global I guessed still there?"* — and a
NO would be indistinguishable from *"ESPN renamed it"*, which is exactly the ambiguity the spike
exists to remove. Shape-scoring survives a rename and **reports the new path instead**. (The NF-C0e
lesson — a check that reads a value back under the key the code wrote can never catch a wrong key —
applied to discovery.)

### 1.4 What state the probe reads

Per the story's item 3, and mapped to where each item comes from:

| Wanted | Source | Note |
|---|---|---|
| drafted players (pick #, drafting team) | tier A/B `picks[]` | the hypothesis in §1.2; the probe captures it wherever it appears |
| whose pick it is now | tier A/B `currentPick` / `onTheClock` | in the key signature |
| the USER's roster so far | tier A/B team rosters | ⚠️ **see the caveat below** |
| available-player pool | tier A/B player pool | pool shape already evidenced by `playerPoolEntry` in the committed payload |

⚠️ **One known gap, inherited and unresolved: we cannot identify WHICH TEAM IS THE USER'S from the
league payload.** NF-C0 §4b established that ESPN's response never identifies the requesting
account, and the credential that would is the one we refuse to hold. In a *draft room* this may well
be solvable (the room is rendered for one user and the client must know who it is), which is a
**specific thing the operator capture should look for** — but it is not solved by anything here, and
a draft assistant that does not know which roster is yours is severely degraded. ⛔ Guessing is
worse than saying so.

---

## 2. Question 2 — entity resolution ✅ MEASURED

### 2.1 The join has no shared key, which is why this was the real risk

Our board keys on the **nflverse `gsis_id`** (`00-0034857`) and `DST-<TEAM>` for defences. ESPN keys
on its **own numeric id**. There is no shared key, so this is a genuine resolution problem — the
recurring one this repo keeps paying for (NF-C0e's wrong key-map, NF-C6P3's 0/15 D/ST join,
NF-W3's franchise codes).

### 2.2 Result — reproduce with `extension/tools/measure_resolution.py`

Population: the **172 rostered players across 10 teams** in the committed real ESPN capture
(`espn_league_642070_2025_drafted.json`), joined to the **858-player published 2026 board**.

```
BOARD   rows=858  distinct join keys=858  positions=['DST','K','QB','RB','TE','WR']
ESPN    rostered players=172   with an espn id=172/172

RESOLUTION LADDER
  tier 1  stable vendor id (espn_id → gsis)      154   89.5%
  tier 3  exact name + position (+DST franchise)  16    9.3%
  UNRESOLVED                                       2    1.2%
  ─ combined                                     170   98.8%

  ambiguous espn_id (abstained)                    1
  ⭐ tier1/tier3 DISAGREEMENTS                      0
```

**Four findings, in descending order of importance:**

**(a) The join-failure rate is 0.0%, not 1.2%.** The two unresolved rows are **Brandon McManus (K)**
and **Joe Mixon (RB)**, and both are *absent from the 2026 board entirely* — NF-K1 **cause 3** (we do
not project them), not **cause 2** (a name that should have matched and didn't). The board publishes
all six projectable positions, so cause 1 is excluded too. Reporting a bare "98.8% match rate" would
have hidden that the join itself missed nothing. The harness prints the three causes separately for
exactly this reason.

**(b) Zero disagreement between two independent identity paths.** On the 154 rows where both the
ESPN-id crosswalk and the name join fire, they select the **same board row every time**. That is a
mutual cross-validation neither path could provide alone, and it is the strongest evidence in this
memo that the resolution is right rather than merely high-yield — a fuzzy join that confidently
merges the wrong players scores a *better* yield than one that honestly abstains (`resolver.py`'s
own calibration finding).

**(c) The ladder is required; neither rung alone is sufficient.** Measured on the lake, `espn_id`
coverage over the 826 non-DST board players is **89.7% (741/826)**, season-unscoped. The 85 missing
are overwhelmingly **incoming rookies** — Fernando Mendoza, Jeremiyah Love, Jordyn Tyson, Carnell
Tate, Makai Lemon, Kenyon Sadiq — plus UDFA kickers, because nflverse assigns no `espn_id` until a
player appears on an NFL roster. ⚠️ **Those are precisely the players a fantasy draft room cares
most about.** A tier-1-only design would fail silently on the entire incoming rookie class; the name
rung is what covers them (it contributed 9.3% here). Conversely the id rung is what survives
nicknames and re-spellings the name rung cannot. **Build the ladder, not either rung.**

**(d) `espn_id` is sparse in the raw and must not be treated as a dense key.** Across *all* rostered
players it is only **53–70%** populated by season (2022: 60.6%, 2023: 53.0%, 2024: 64.7%, 2025:
70.4%, 2026: 66.5%) — the same trap `crosswalk.py` documents for `pfr_id`. The 89.7% board figure is
higher only because the board is the fantasy-relevant subset. One `espn_id` mapped to more than one
`gsis_id` in the fixture; the harness **abstains** rather than guessing, per `resolver.py`'s rule
that a wrong merge is far more expensive than a miss.

### 2.3 It resolves through the SHIPPED join

The harness calls `league_scoring._join_key` — the same function the served
`/fantasy/nfl/league-board` roster join uses, including NF-C6P3's D/ST franchise resolution (the
board publishes `DET D/ST`, ESPN publishes `Lions D/ST`; as text those never match, which is why a
unit is joined on its **franchise**). A private matcher would have measured a join we do not ship
and been free to drift from the one we do — the E9.61 "two renderers of one field are two rule sets"
lesson on the measurement side. All 15 D/ST rows resolved.

### 2.4 ⭐ Design consequence: resolution belongs SERVER-SIDE

Tier 1 needs the crosswalk (in the lake) and tier 3 needs the published board — **both server-side**.
The extension should therefore send `{espn_id, name, position, team}` and let our API resolve, which
also matches the epic's "recommendations come from OUR API running the SAME optimizer — one ranker".
⛔ Bundling a board or a matcher into the extension would create a second ranker and a second
matcher, and both would drift.

---

## 3. Brittleness verdict

**🟡 MODERATE — acceptable, conditional on the capture landing on tier A or B.**

| Factor | Assessment |
|---|---|
| Is there a stable/versioned source? | **Partly.** ESPN's `view=`-selected JSON is *structured* and has been *stable in field names* — NF-C0 §4c verified four guessed field names correct against a real payload. It is **not contractually versioned**: undocumented, unversioned, no published terms. |
| Has it moved before? | **Yes, with no notice** — `fantasy.espn.com` → `lm-api-reads.fantasy.espn.com`. Assume it moves again. |
| Blast radius of a break | **Low, by construction.** The extension is standalone: it cannot degrade the app, the board, or serving. The worst case is the assistant saying it cannot read the draft. |
| Cost of a break at the wrong moment | **High in USER terms.** Drafts are a ~2-hour window once a year. A break during the draft is unrecoverable for that user, which is what makes §4 the load-bearing half of this verdict rather than a nicety. |

**The honest framing:** this is not a stable integration and will never be one — ESPN offers no
contract (NF-C0 §1(a): the developer program shut down in 2014). It is a **reverse-engineered read
that must be assumed to break**, and the engineering question is therefore not "how do we stop it
breaking" but "**how does it fail**". Which is §4.

---

## 4. Break detection — how it degrades

The requirement from the story: degrade to *"we can't read your draft right now"* instead of silently
showing stale or garbage state. Implemented in `extension/src/content.js::verdict()`:

| Level | Condition | Shown |
|---|---|---|
| `OK` | a draft-shaped **network response** was observed, or an in-page state object scored ≥ 3 | source + which |
| `DEGRADED` | no structured source, but pick-like DOM nodes exist | "DOM-text only — brittle" |
| `BLOCKED` | nothing found | **"cannot read this draft right now"** |
| `unknown` | the probe has not reported yet | named as such |

**Three properties make this a real detector rather than a label:**

1. **The verdict is DERIVED from what was observed, never assumed.** It reads the actual scan
   results, so a rename downgrades the level rather than silently returning stale state.
2. **An unreadable state is a NAMED state, not an empty one.** `BLOCKED` and "no picks yet" are
   different renderings. This is NF1.7(a) — a check that could not run is not a pass — and it is the
   single most important line in the whole design, because "empty" and "broken" are otherwise
   pixel-identical.
3. **It re-publishes on a 5s tick**, so a mid-draft break is caught during the draft, not at load.
   A one-shot scan at page load would under-report the network tier badly (state arrives over time)
   *and* would never notice a break that happens at pick 40.

⭐ **For the overlay story, the same discipline must extend to STALENESS**: a structured read that
silently stops advancing is the INC-41 artifact-freshness shape (a feed can be healthy while the
derived thing freezes). The overlay should show the pick number it is reasoning about, so a frozen
read is visible rather than inferable.

---

## 5. What the operator capture must produce — and what a SECOND one must differ in

**The capture (one ESPN mock draft, ~10 picks) settles question 1.** Steps are in
`extension/README.md`. It should answer, in order:

1. Which tier lit up — `network` entries with `score > 0` (tier B), a scoring `globals` entry
   (tier A), or only `dom` (tier C, the yellow flag)?
2. Does a pick list carry **pick number, drafting team, and player id**?
3. Is there a **"who am I"** signal? (§1.4's known gap — the highest-value unknown.)
4. Is the **available pool** exposed, or only the drafted players?
5. Is the transport a **WebSocket** or **polling**? (Changes the overlay's update model.)

⚠️ **One capture cannot disconfirm** — NF-C0e is the standing proof (Sleeper's coarse `fgm_50p` vs
fine `fgm_50_59` survived 56 tests and a live-verified league; ESPN's yards-allowed ladder was absent
from the first league entirely). **A second capture must differ in the dimensions that plausibly
change the READ**, not merely be a second draft:

- **a different draft TYPE** — snake vs **auction** (an auction room has nominations and bids, a
  structurally different state machine, and `bidAmount`/`nominatingTeamId` exist in ESPN's pick
  shape);
- **a different league SIZE** (8/12/14) — the pool and pick-order shape scale with it;
- **a real live draft rather than a mock**, if the mock room is a different client build;
- ideally **a different ESPN account**, per NF-C0's finding that a second real account is what
  exposed a whole scoring family the first could not.

⚠️ And a note on the resolution measurement's own limits, stated because it flatters us: the 172
rostered players are the **drafted top of the pool**. A live assistant must resolve the **entire
available pool** (~1,000+ rows), where obscure players and name collisions live. There is **no local
ESPN pool capture** to measure that against (checked — the `espn_cache/` directory does not exist),
so **full-pool resolution is UNMEASURED**. The capture should include the pool if the page exposes
it, and `measure_resolution.py` should then be re-run against it. Two further honest caveats: the
fixture is a **2025** league scored against a **2026** board, so cross-season attrition means 98.8%
is a **lower bound**; and the DST rung was exercised on 15 rows.

---

## 6. Red-proof record

`betting_ml/tests/test_nf_c_lda_0_extension_red_line.py` (13 tests) is the durable artifact. A green
suite is not evidence it works, so each clause was broken deliberately and confirmed to go red —
re-runnable via `uv run python extension/tools/red_proof.py`:

| Deliberate break | Clause that went RED |
|---|---|
| manifest requests the `cookies` permission | `test_the_manifest_requests_no_credential_bearing_permission` ✓ |
| manifest host scope widened to `*://*/*` | `test_the_manifest_host_scope_is_narrow` ✓ |
| probe reads `document.cookie` | `test_no_source_reads_a_credential[document.cookie]` ✓ |
| probe ORIGINATES a `fetch` to ESPN | `test_no_source_originates_a_network_call[fetch(]` ✓ |
| probe stops wrapping fetch (abstains) | `test_the_probe_really_does_wrap_rather_than_merely_abstain` ✓ |

**Three ways a red proof itself lies, all closed:** the harness asserts each mutation **actually
landed** (#682), that its anchor is **unique** (#885), and each break targets **one named clause**
(#815). ⭐ The uniqueness check paid immediately — it caught two bad anchors on the first run (one
occurring 3×, one 0×) that would otherwise have reported a **false "the guard is vacuous"**, which is
the dangerous direction because it invites weakening a correct guard.

Two design notes inside the guard, both deliberate:

- **Comment stripping is load-bearing, not boilerplate.** The probe *documents* this red line in
  prose that necessarily contains the forbidden tokens ("…grows an originating call or touches
  `document.cookie`"). Without stripping, the comment explaining the rule would **trip** the rule —
  INC-38 facing the false-positive direction.
- **The token list distinguishes WRAPPING from ORIGINATING.** The probe legitimately wraps
  `fetch`/`XHR`/`WebSocket`, so a blanket ban on the word `fetch` would refuse the working design. A
  wrapper only ever re-invokes the **saved original** (`origFetch.apply`, `new OrigWS`); originating
  requires calling the global name itself. Plus a two-sided clause asserting the wrappers are
  **present** — without it, "no originating call" is satisfied by an empty file, which is also what
  a silently-broken probe looks like.

---

## 7. Compliance — where this sits against the NF-C0 red line

`docs/nf_c0_espn_access_probe.md` §3(c) refuses holding or replaying `espn_s2`. This extension is the
**automated analogue of §3(d)** (the user-mediated paste), and the property that keeps it there is:

> **Observe, never originate.**

| §3(c) failure | This extension |
|---|---|
| We hold a live credential | We hold none. `"permissions": []` — no `cookies`, no `webRequest`, no storage. |
| Grant confers writes | We cannot act on the league at all; every read is passive. |
| Not revocable for us specifically | Access ends when the tab closes or the extension is removed. |
| Not scoped to fantasy | Host-scoped to `fantasy.espn.com/football/draft*` alone. |

It reads **response bodies only, never request headers** — the §3(d) argument is precisely that a
body cannot carry the cookie while a header can.

### ⚠️ ONE POLICY QUESTION THIS SPIKE DELIBERATELY DOES NOT DECIDE

A content script with an ESPN host permission **could** call ESPN's league API directly, and the
browser would attach the user's cookie automatically. That would make the read far more robust than
observing the page — it would turn tier B from "whatever the room happens to request" into "we ask
for `view=mDraftDetail` whenever we like".

**It is also arguably §3(c) wearing an extension costume**, and the argument genuinely cuts both
ways: we would never come into *possession* of the cookie (it stays in the user's browser, exactly
as in the paste flow), but we *would* be "making an authenticated request on the user's behalf",
which the probe memo's correction section refuses in those words.

⛔ **This spike does not take that decision, and did not quietly build toward it.** The probe is
observe-only and the guard suite makes originating a build failure. It is flagged as an **explicit
operator/PM decision** for the overlay story, because it is exactly the convenience pressure the
probe memo warned would produce "paste your cookie instead" — and a decision of that shape should be
argued once, in the open, not arrived at by refactor. **Recommendation: stay observe-only** unless
the capture shows passive observation cannot see the picks, in which case bring the trade-off back
explicitly with what it buys.

---

## 8. What this decides for the overlay story

1. **Build it.** The resolution risk — the thing most likely to make this infeasible — is **measured
   and answered**: 0.0% join failures through the shipped join.
2. **Resolve server-side** (§2.4). The extension sends identity triples; our API runs the ladder and
   the optimizer. One ranker, one matcher.
3. **Implement the ladder, not the id rung** (§2.2c) — or the incoming rookie class fails silently.
4. **Break detection is a first-class feature, not polish** (§4). Drafts are a once-a-year
   two-hour window; "empty" must never be able to look like "working".
5. **The gating unknown is the capture** (§5) — one operator mock draft. If it lands on tier C only,
   the correct answer is to re-scope, not to ship a DOM scraper into a draft room.
6. **Solve, or scope around, "which team is the user's"** (§1.4). It is unsolved from the league
   payload and is the highest-value thing the capture can answer.

---

## 9. Files

| Path | What |
|---|---|
| `extension/manifest.json` | MV3, zero permissions, draft-path host scope |
| `extension/src/main-world-probe.js` | tiered read probe — passive observers + shape-directed scan |
| `extension/src/content.js` | verdict + capture readout (⛔ not the overlay) |
| `extension/tools/measure_resolution.py` | reproduces every §2 figure |
| `extension/tools/red_proof.py` | proves the guard can fail |
| `betting_ml/tests/test_nf_c_lda_0_extension_red_line.py` | the credential red line, 13 tests |
| `extension/README.md` | load-unpacked + capture instructions |

Nothing here deploys. The extension is not part of the Next.js app and does not go through Vercel or
`infrastructure/lambda/deploy.sh`; it is loaded unpacked by hand. **No changelog entry** — nothing
user-facing ships from a spike.
