# NF-C0-Yahoo-SPIKE — GO/NO-GO memo

**Verdict: ⛔ NO-GO for user traffic today.** Do **not** set `YAHOO_IMPORT_ENABLED=1` yet.
**One blocker is infrastructure and takes one command; three are compliance gaps against the signed
agreement; and the payload reconciliation — the thing the spike was chartered to prove — is still
unrun, because it is gated behind the infrastructure blocker.**

Probed live **2026-08-19** against the real approved credentials. Everything below labelled
MEASURED was executed against Yahoo's live endpoints or the live AWS account; nothing was read off
a spec or inferred from the previous session's notes.

---

## The one-paragraph version

Our half of the integration is in better shape than the NF-C0 handoff assumed: the SSM secrets are
present **and provably correct**, the IAM grant is right, and the redirect URI matches Yahoo
byte-for-byte — all three verified two-sided, without needing anyone's consent. What is broken is
the return leg: **the OAuth callback route 401s at the API Gateway before the Lambda is ever
invoked** (the NF3.2 landmine, live and unfixed), so a user who consents on Yahoo's screen is
redirected into an "Unauthorized" JSON page and the grant is never stored. Nobody could have
completed a connect at any point since NF-C0 shipped. Separately, three delivery constraints of the
signed agreement are not met by the code as it stands — most materially, we durably persist every
team's roster in a user's league with no retention bound and no deletion on disconnect.

---

## 1. OAuth 2.0 handshake — ⚠️ PARTIAL (both ends verified; the middle is blocked)

| Leg | Result | How it was established |
|---|---|---|
| Client credentials in SSM | ✅ **present and CORRECT** | MEASURED, two-sided: the real secret returns `INVALID_AUTHORIZATION_CODE` ("your client is fine, that code isn't"); a deliberately wrong secret returns `INVALID_CLIENT_SECRET`. The endpoint discriminates, so this is a pass, not an absence of failure. |
| Lambda IAM → SSM | ✅ correct | `credence-yahoo-oauth-ssm-read` grants `ssm:GetParameter` on `/credence/prod/yahoo_*` + `kms:Decrypt` via SSM. |
| Redirect URI registration | ✅ **matches byte-for-byte** | MEASURED, two-sided: the registered URI returns Yahoo's real 63 KB sign-in page; a wrong URI **and a trailing-slash variant** both return an 8.5 KB error page reading *"Developers: Please specify a valid request and submit again."* This eliminates what the setup guide calls the single most common way this setup goes wrong. |
| Authorize → consent → **callback** | ⛔ **BLOCKED** | The callback 401s at the gateway. See §2. |
| code → token exchange | ⏳ unrun | Needs a real code, which needs the callback (or a manual copy out of the address bar — see the runbook). |
| refresh | ⏳ unrun | Same. The code path is correct by inspection and the refresh-token **rotation** write-back is already handled. |
| **Granted scopes** | ⚠️ **there is no scope to record** | Yahoo's Fantasy permission is a property of the **approved app**, not of the request or the token — no `scope` parameter is sent and no `scope` field comes back. The honest answer to "what scopes were granted" is "read access, provisioned server-side on approval". |
| **Token lifetime** | ⏳ unrun (documented 3600s; the code defaults to 3600 with a 60s safety margin) | The harness prints the real value on the first successful exchange. |

⚠️ **Whether Yahoo has actually approved our Fantasy access is still UNCONFIRMED.** The signed
agreement (2026-08-14, effective 08-15) is strong evidence it landed, but the only proof is a real
token reading a real league. Note the failure modes are **indistinguishable**: an unapproved app and
an account with no NFL league both produce an empty league list. The harness says so explicitly
rather than reporting the empty list as a result.

## 2. ⛔ BLOCKER 1 — the OAuth callback is not reachable (NF3.2)

**MEASURED:**

```
GET https://api.credencesports.com/fantasy/import/yahoo/callback?code=…&state=…
  → HTTP 401  {"message":"Unauthorized"}          ← the GATEWAY authorizer's body, not FastAPI's
GET https://api.credencesports.com/subscription/public-pricing   (a known --authorization-type NONE route)
  → HTTP 200                                       ← the two-sided control
```

The HTTP API (`8dhmehjak7`) has **16 routes**; `GET /fantasy/import/yahoo/callback` is not among
them, so it falls to the catch-all `ANY /{proxy+}`, which carries the Cognito JWT authorizer
(`maqziq`). The callback is entered by the **user's browser** on a redirect from Yahoo and therefore
carries no bearer token — it is refused before the Lambda runs.

This is exactly the landmine CLAUDE.md documents ("a route that is genuinely public IN CODE still
returns 401 at the gateway"), and the backend was written correctly for it: the callback is mounted
on a separate `public_router` and authenticates itself with the HMAC-signed `state`. Only the
gateway route was never created. **Fix = one command (operator step O1).**

Consequence worth stating plainly: **Yahoo import has never been completable by anyone**, and
flipping `YAHOO_IMPORT_ENABLED=1` without O1 would ship a button that sends users to Yahoo, takes a
real permission grant from them, and drops it on the floor — strictly worse than the current honest
"coming soon".

## 3. Endpoint payloads reconcile? — ⏳ **NOT YET VERIFIED** (this is the honest answer)

This is the question the spike exists to answer and it **cannot be answered without a token**. Every
Fantasy v2 resource is OAuth-gated (`/game/nfl` unauthenticated → 401, MEASURED), so there is no
read-only path to a real payload, and writing another hand-authored fixture would restate the
parser's own assumptions rather than test them (NF-C0e).

What was done instead: **`scripts/probe_yahoo_fantasy_live.py`**, which turns the remaining work
into one operator command. It drives the **shipping adapter functions** (not a copy) against a live
token and reports, field by field:

* every `stat_id` Yahoo actually sent vs `STAT_ID_MAP` — **listing each unmapped id with its weight
  and its human name**, flagged `⚠️ SCORES` when the weight is non-zero (an unmapped rule that
  actually scores is the defect that matters; an unmapped rule at 0.0 is noise);
* every roster-position token vs `ROSTER_SLOT_MAP`;
* the `import_league()` verdict — teams parsed, players per team, starters, whether `is_owner`
  resolved, draft picks, warnings — with five **named failure conditions** that decide the payload
  half of GO/NO-GO (empty teams, no players, no `is_owner`, empty roster, no core scoring term).

🔒 It writes a **shape report** — key skeletons, stat ids, counts — with player names, team names
and manager nicknames redacted, so running the probe does not itself create a store of Yahoo Fantasy
Information (§2.c.vii). `--keep-values` exists for a genuine parsing dead end and warns.

⚠️ **Run it against ≥2 independently-sourced leagues** (NF-C0e): a single league cannot disconfirm a
wrong key map, and Yahoo emits variant shapes (PPR/half/standard, coarse vs fine buckets, IDP,
multi-position, auction vs snake).

## 4. Rate limiting + single account — ✅ now honoured (2 defects found and FIXED)

* ⛔ **was:** Yahoo throttles with **HTTP 999**, which fell through the generic `status >= 400`
  branch and reached the user as a **502 "the platform could not be reached"** — an outage report
  for a limit we had hit and would clear by waiting. **Now:** `RATE_LIMIT_STATUSES = (429, 999)`,
  classified as 429, with the true upstream status preserved on the exception for diagnosis.
* ⛔ **was:** no backoff at all on either status. **Now:** exactly **one** retry on a throttled
  **GET**, honouring `Retry-After`. The budget is deliberate: API Gateway dies at 29s and the
  request timeout is 8s, so one retry fits and two do not — and a `Retry-After` longer than 5s is
  honoured **by not retrying**, because sleeping through the gateway's own deadline converts a
  legible 429 into an unexplained edge timeout. The single-use OAuth token **POST is never retried**
  (replaying it can spend the grant and return the second, failing answer).
* ✅ **Single account:** the grant is stored at `platform_tokens.yahoo` keyed on `user_id`, so one
  Credence user holds at most one Yahoo grant, a second connect replaces the first, and no request
  path can read one user's leagues with another user's token (`_access_token(user_id)` is the only
  reader). ⚠️ I could not read the §2.c.v-vi clause text — this is an audit of what the code does,
  against my reading of the constraint, not a check against the words.

## 5. Compliance audit (verified IN CODE)

| Clause | Verdict | Finding |
|---|---|---|
| §1.c / §2.c.xii / §3.e — never into training or an LLM | ✅ **PASS, and now guarded** | Nothing under `quant_sports_intel_models/`, `betting_ml/`, `pipeline/`, `scripts/`, `dbt/` reads `fantasy_leagues` / `league_rosters` / `imported_roster` / `platform_tokens`; the repo's one LLM call site (the MLB narrative generator, Bedrock Nova Micro) takes no league input. It held by convention only, so it is now a mechanical guard over the source. |
| §2.c.vii — no store/cache/index of Yahoo Fantasy Information | ⛔ **GAP (B2)** | On save we durably persist **every team's roster in the league** (`league_rosters`: team name + each player's name/position/team, up to the caps), the user's own roster (`imported_roster`), and the derived scoring config — in DynamoDB, **with no TTL and no retention bound**. The *derived scoring config* is defensible as our own derived artifact; **the rosters are Yahoo Fantasy Information by any reading.** |
| §6 — deletion on disconnect / termination | ⛔ **GAP (B2)** | `DELETE /fantasy/import/yahoo/connection` deletes **only the OAuth token**. A user who disconnects keeps every Yahoo-derived roster we stored, indefinitely. There is no account-closure routine that purges them either. |
| Cover / §5 — attribution + hyperlink on every page showing Yahoo data | ⚠️ **PARTIAL (B3)** | The string and the link are correct — *"Fantasy data provided by Yahoo Fantasy"*, hyperlinked to `football.fantasysports.yahoo.com` — but they render in **exactly one place**: the import **preview**, before saving (`league-import.tsx`). Every surface that shows the data *after* it is saved — My League, My Teams, the roster report, the league board, the draft and auction optimizers, the settings editor — shows none. |
| §7 — privacy policy covers the import | ⛔ **GAP (B4)** | `frontend/app/privacy/page.tsx` contains **zero** occurrences of "league", "fantasy", "import", "Yahoo", "Sleeper" or "ESPN". The policy does not describe this data flow at all. |
| §16 / §12 — no Yahoo marks or logos; no publicising the partnership | ✅ PASS | No Yahoo logo or mark anywhere in `frontend/`; the only Yahoo strings are the required attribution and the plain-text platform label. No marketing copy references the relationship. |
| Red line — never handle a Yahoo password | ✅ PASS (pre-existing guard) | Enforced against the source by `test_nf_c0_platform_import.py`. |
| US + CA read-only | ✅ PASS by construction | Every call is a GET; nothing writes to Yahoo. ⚠️ **No geo-restriction exists** — if the agreement's US+CA scope is a *delivery* constraint on who may use the import, that is an unlisted gap needing the clause text to size. |

## 6. What changed in code (this PR)

1. **`yahoo_oauth._token_call` — the vendor's real error codes.** MEASURED: the code-exchange leg
   returns `INVALID_AUTHORIZATION_CODE` and the refresh leg returns `invalid_grant` — the two legs
   disagree on both spelling and casing, and only the RFC spelling was mapped. So the *most common
   OAuth failure there is* (the consent screen sat open past the code's lifetime, or the callback
   was replayed) surfaced as a 502 blaming Yahoo, instead of a 401 the user fixes by reconnecting.
   ⭐ `INVALID_CLIENT_SECRET` is **deliberately excluded**: it is our credential, so "please
   reconnect" would ask the user to fix something only the operator can, and would bury a broken
   deploy behind a message that reads like routine token churn.
2. **`http.py` — 999/429 recognition and a bounded backoff** (§4 above).
3. **`fantasy_import._handle_platform_error`** — classifies the whole rate-limit set, not just 429.
4. **`betting_ml/tests/test_nf_c0_yahoo_spike.py`** — 12 tests, **all 7 guard clauses RED-proven**
   against deliberately broken source (each mutation anchor asserted unique and asserted to have
   landed, per the repo's own red-proof-lies lessons).
5. **`scripts/probe_yahoo_fantasy_live.py`** — the live reconciliation harness (§3).

⛔ **What was deliberately NOT built:** the compliance gaps B2–B4. Retention/deletion and
attribution placement are product and legal decisions with real user-visible consequences — deleting
a user's configured league because they disconnected Yahoo could destroy work they still want — so
they are specified here for the operator to decide, not resolved unilaterally inside a spike.

## 7. Blockers to close before user traffic

| # | Blocker | Owner | Cost |
|---|---|---|---|
| **B1** | Callback route 401s at the gateway | operator (O1) | one CLI command |
| **B2** | Yahoo rosters persisted with no retention bound; disconnect deletes only the token | PM decision, then a small backend change | needs a decision on *what* disconnect should delete |
| **B3** | Attribution on the ~7 post-save surfaces, not just the preview | frontend | small, mechanical (a shared component keyed on `source_platform === "yahoo"`) |
| **B4** | Privacy policy silent on league import | PM/legal copy | one section |
| **B5** | Payload reconciliation unrun; ≥2 real leagues | operator + this session's harness | ~10 min once B1 is done |

**B1 and B5 are the spike's own remaining scope.** B2–B4 are delivery constraints of the signed
agreement and are the reason this is a NO-GO rather than a "flip it after the route is fixed".
