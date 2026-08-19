# NF-C0-Yahoo-SPIKE — GO/NO-GO memo

**Verdict: ⛔ NO-GO for user traffic.** Do not set `YAHOO_IMPORT_ENABLED=1`.
**But the reason changed during the spike, and the new one is much better news:** OAuth is now
**proven working end-to-end in production**, and the remaining blocker is a single, precisely-named
Yahoo-side entitlement — not anything wrong with our code.

Probed live **2026-08-19** with the real approved credentials and a real consent by the operator.
Everything labelled MEASURED was executed against Yahoo's live endpoints or the live AWS account.

---

## The one-paragraph version

The operator completed a real consent and the browser returned to `…/fantasy/import?yahoo=connected`
— which only happens after the **deployed Lambda** verified the signed `state`, exchanged the code,
Fernet-encrypted the refresh token and wrote it to DynamoDB. **The entire 3-legged handshake works
in production**, including the runtime SSM read and the IAM grant. Then every Fantasy resource
returned a bare **401** carrying `oauth_problem="additional_authorization_required"`, while Yahoo's
own `openid/v1/userinfo` returned **200** for the *same token*. That control is what makes this
unambiguous: the token is fine, the account is fine, and **our app simply does not carry Yahoo
Fantasy Sports data access.** So the payload reconciliation still cannot run — but for a reason we
can now name in one line and hand to Yahoo, rather than an unknown.

⭐ **This is exactly the scenario `yahoo_oauth.is_enabled()` was built to prevent**, and it held: the
docstring predicted "the handshake would succeed and every Fantasy endpoint would 401 — the user
grants a permission that buys them nothing." That is precisely what happened, and it only happened
because the probe bypasses the availability gate. Had `YAHOO_IMPORT_ENABLED=1` been set, real users
would have hit it. **That is the single strongest argument for leaving the flag off.**

---

## 1. OAuth 2.0 handshake — ✅ **WORKS**, proven end-to-end in production

| Leg | Result | How |
|---|---|---|
| Client credentials in SSM | ✅ present and **CORRECT** | MEASURED, two-sided: the real secret returns `INVALID_AUTHORIZATION_CODE`; a wrong one returns `INVALID_CLIENT_SECRET`. |
| Lambda IAM → SSM **at runtime** | ✅ **proven** | The deployed callback read all three parameters and completed the exchange. Not an inspection of the policy — the real Lambda did it. |
| Redirect URI registration | ✅ **byte-for-byte** | MEASURED, two-sided: a wrong URI *and a trailing-slash variant* both return Yahoo's "Developers: Please specify a valid request" page; the registered one returns the real sign-in page. |
| authorize → consent → callback | ✅ **works** | Operator consented; browser returned `?yahoo=connected`. A garbage code now returns **302** (the failure redirect) where it returned 401 before the route fix. |
| code → token exchange | ✅ **works** | Done by the deployed Lambda. |
| encrypted token storage | ✅ **works** | Fernet ciphertext + `expires_at` + `connected_at` present in `credence-prod-dynamo-users`. |
| **refresh** | ✅ **works** | MEASURED via the shipping `refresh_access_token`: returned a new access token, **no rotation on this refresh** (the write-back path is still required — Yahoo *may* rotate). |
| **token lifetime** | ✅ **3600s (60 min)** | MEASURED — and independently corroborated by the stored record (`expires_at − connected_at = 3540s`, i.e. 3600 less the code's deliberate 60s safety margin). |
| **granted scopes** | ⚠️ **there is no scope to record** | Yahoo sends no `scope` parameter and returns no `scope` field for Fantasy. The token carries **OpenID Connect** permission (userinfo returns 200) and **not** Fantasy. Permission is a property of the approved **app**, so "what scopes were granted" has no per-request answer — which is exactly why the gap below was invisible until a Fantasy call was made. |

## 2. ⛔ THE BLOCKER — our app has no Fantasy Sports entitlement

**MEASURED, with the control that makes it decisive:**

```
GET https://api.login.yahoo.com/openid/v1/userinfo            → 200  {"sub":…,"name":…}   ← token is VALID
GET https://fantasysports.yahooapis.com/fantasy/v2/game/nfl   → 401
GET …/fantasy/v2/users;use_login=1/games                      → 401
GET …/fantasy/v2/users;use_login=1/games;game_keys=nfl/leagues→ 401
     WWW-Authenticate: OAuth oauth_problem="additional_authorization_required", realm="yahooapis.com"
```

Same token, same second. A valid token that reads the user's Yahoo profile and cannot read any
Fantasy resource is **an app-entitlement fault**, not a token, URL, account or empty-league problem
— all four of which were candidate explanations before the control was run.

**This is the setup guide's open question, now answered.** The 2026-08-01 session found there is no
"Fantasy Sports" checkbox on the app-creation form and *inferred* that access would be provisioned
server-side on approval. **The measurement says it has not been.** The signed agreement (2026-08-14)
evidently did not, by itself, attach Fantasy read access to app `qnVLbJOd`.

**⚠️ A granted permission set is bound at consent time**, so enabling the permission will require a
**fresh consent** — the existing grant will not silently acquire it.

### What the previous blocker was, and its status
The API Gateway callback route (`GET /fantasy/import/yahoo/callback` falling to `ANY /{proxy+}` and
its JWT authorizer → 401 before the Lambda ran, NF3.2) — **✅ CLOSED.** The operator created it with
`--authorization-type NONE`; the route is live, auto-deploy is on, and the 401 is now a 302.

## 3. Endpoint payloads reconcile? — ⏳ **STILL UNVERIFIED**, now for a named reason

Blocked behind §2: no Fantasy resource returns data, so there is no payload to reconcile. Everything
needed to answer it in one command is built and now **exercised as far as Yahoo permits** —
`scripts/probe_yahoo_fantasy_live.py` ran the real OAuth path end-to-end, which is how §1 and §2
were established. The moment the entitlement lands:

    …probe_yahoo_fantasy_live.py --authorize-url        # fresh consent (required — see §2)
    …probe_yahoo_fantasy_live.py --from-stored-grant nf-c0-yahoo-spike
    …probe_yahoo_fantasy_live.py --forget nf-c0-yahoo-spike

It drives the **shipping adapter** (not a copy) and reports every `stat_id`/roster token the parser
does not know — flagged `⚠️ SCORES` when the weight is non-zero — plus five named pass/fail
conditions (empty teams, no players, no `is_owner`, empty roster, no core scoring term). It writes a
value-**redacted** shape report, so running it does not itself create a store of Yahoo Fantasy
Information (§2.c.vii).

⚠️ Run it on **≥2 independently-sourced leagues** (NF-C0e): one league cannot disconfirm a wrong key
map, and Yahoo emits variant shapes (PPR/half/standard, coarse vs fine buckets, IDP, multi-position,
auction vs snake).

⭐ **`--from-stored-grant` exists because of a real trap this spike hit:** the deployed callback
**spends** the single-use code the instant Yahoo redirects, so on the very run that *proves the
handshake works*, `--callback-url` reports "no code in that URL". The grant is in DynamoDB; resume
from there. ⭐ And `--forget` exists because a successful consent leaves a **real, live Yahoo grant
in the production users table** under a synthetic id no UI would ever show — it has been deleted for
this run.

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
3. **`YahooNotEntitled` — an unentitled app is no longer reported as the user's problem.** MEASURED
   in §2: both "this app cannot read Fantasy data" and "this user's grant is dead" arrive as a bare
   401 and differ **only in the response body**. The old code mapped both to *"Your connection to
   that platform is no longer authorized"*, which invites a **reconnect that cannot possibly work** —
   re-consenting grants the same non-Fantasy permission again, so the user loops through Yahoo's
   consent screen forever on a fault only the operator can clear. `PlatformHTTPError` now carries the
   401 body, `yahoo._get` classifies on `oauth_problem`, and the entitlement case becomes a **503
   "not available yet"**. Verified against the live endpoint: `YahooNotEntitled` → HTTP 503. The
   two-sided half is guarded — a genuinely dead grant still reads as a 401.
4. **`fantasy_import._handle_platform_error`** — classifies the whole rate-limit set, not just 429.
5. **`betting_ml/tests/test_nf_c0_yahoo_spike.py`** — 15 tests, **all 10 guard clauses RED-proven**
   against deliberately broken source (each mutation anchor asserted unique and asserted to have
   landed, per the repo's own red-proof-lies lessons).
6. **`scripts/probe_yahoo_fantasy_live.py`** — the live harness (§3), now with `--from-stored-grant` and `--forget`.

⛔ **What was deliberately NOT built:** the compliance gaps B2–B4. Retention/deletion and
attribution placement are product and legal decisions with real user-visible consequences — deleting
a user's configured league because they disconnected Yahoo could destroy work they still want — so
they are specified here for the operator to decide, not resolved unilaterally inside a spike.

## 7. Blockers to close before user traffic

| # | Blocker | Owner | Cost |
|---|---|---|---|
| ~~B1~~ | ~~Callback route 401s at the gateway~~ | ~~operator~~ | ✅ **DONE** |
| **B1′** | **Our Yahoo app has no Fantasy Sports data access** (`additional_authorization_required`) | **operator → Yahoo** | unknown — Yahoo's to grant; then a **fresh consent** |
| **B2** | Yahoo rosters persisted with no retention bound; disconnect deletes only the token | PM decision, then a small backend change | needs a decision on *what* disconnect should delete |
| **B3** | Attribution on the ~7 post-save surfaces, not just the preview | frontend | small, mechanical (a shared component keyed on `source_platform === "yahoo"`) |
| **B4** | Privacy policy silent on league import | PM/legal copy | one section |
| **B5** | Payload reconciliation unrun; needs ≥2 real leagues | operator + the harness | ~10 min once B1′ clears |

**B1′ is now the critical path and it is not ours to close.** Concretely, for the operator: open the
YDN app (`developer.yahoo.com/apps/`, App ID `qnVLbJOd`) and check whether **Fantasy Sports → Read**
now appears under API Permissions — it was absent at creation and may only become selectable once
access is provisioned. If it is not there, the agreement is signed but the entitlement was never
attached to the app, and that is the question to put to Yahoo, quoting the exact string:
`oauth_problem="additional_authorization_required"` on `/fantasy/v2/game/nfl` with a token whose
`openid/v1/userinfo` returns 200.

B2–B4 remain independent of B1′ and must close before user traffic regardless.
