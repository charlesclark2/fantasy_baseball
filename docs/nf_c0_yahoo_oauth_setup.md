# NF-C0 — Yahoo Fantasy API: operator setup guide

## 📌 LIVE STATUS (update this block as it moves)

| | |
|---|---|
| **YDN app created** | ✅ 2026-08-01 — App ID **`qnVLbJOd`**, name "Credence Sports", confidential client, redirect URI `https://api.credencesports.com/fantasy/import/yahoo/callback` |
| **Access application submitted** | ✅ 2026-08-01 via `sports.yahoo.com/developer/access/` (App ID supplied; read-only; Small <1,000 users) |
| **Yahoo approval** | ⏳ **PENDING — no SLA published; the latency is entirely Yahoo's** |
| **SSM parameters written** | ⛔ **NOT YET** — blocked on `aws sso login --profile AdministratorAccess-769392325318` (see step 3) |
| **Lambda IAM grant** | ⛔ Not yet (step 4) |

⏰ **CHASE TRIGGER: if Yahoo has not replied by 2026-08-15, Yahoo import will NOT be ready for the
operator's 2026-08-22 draft.** That is the operationally meaningful deadline, not an arbitrary one —
so treat 8/15 as the date to follow up, and plan the draft-window GTM on **Sleeper import + the
NF-C0b manual editor**, both of which are live and need nothing from Yahoo.

---

**Written 2026-08-01 against the LIVE Yahoo developer surface**, not from cached documentation.
Everything below was probe-verified on that date; the "verified" column says how.

**Your job is steps 1–4.** Everything else — the redirect URI, the OAuth code, the token store, the
encryption, the league reader, the UI — is built and merged. When the two secrets land in SSM, Yahoo
import switches itself on (the backend reads them at runtime; **no redeploy is needed**).

---

## ⚠️ READ THIS FIRST — the story's premise has changed, and it changes your expectations

The NF-C0 story assumed Yahoo setup was **"~5 console clicks + paste two secrets."** That was true
historically. **It is not true today**, and the probe is what caught it:

| What the story assumed | What is actually live (2026-08-01) |
|---|---|
| Self-serve app creation grants Fantasy API access immediately | App creation is still self-serve, but Fantasy API access is now gated behind an **application REVIEW** — "We'll review your application and reach out with next steps" |
| You tick "Fantasy Sports → Read" when creating the app | **There is no Fantasy Sports checkbox on the create-app form** (verified on the live form 2026-08-01). Fantasy access is provisioned on approval in step 2 — see the note in step 1 |
| Docs at `developer.yahoo.com/fantasysports/guide/` | That URL now **308-redirects** to `sports.yahoo.com/developer`; the real docs are at `sports.yahoo.com/developer/docs/` |
| Access is a same-day setup | Approval latency is **entirely Yahoo's**, unbounded, and outside our control |

**Practical consequence:** treat Yahoo import as *code-complete but not date-committed*. Submit the
application now (it may take a while), and expect the **Sleeper** adapter — which is live, needs no
approval, and covers 33% of the market — to be what carries draft-season GTM. Every Yahoo user is
covered in the meantime by the NF-C0b manual editor.

---

## Step 1 — create the Yahoo developer app (~5 minutes, gets you an App ID)

You need a Yahoo account (any personal one is fine) and to accept Yahoo's developer terms.

1. Go to **<https://developer.yahoo.com/apps/create/>** — *verified live 2026-08-01: 302s to the
   Yahoo login, then to the create-app form.* Sign in.
2. Fill the form in exactly these terms:

   | Field | What to enter |
   |---|---|
   | **Application Name** | `Credence Sports` |
   | **Description** | `Fantasy league import for Credence Sports — reads a user's own league settings and rosters to produce personalised draft rankings.` |
   | **Home Page URL** | `https://www.credencesports.com` |
   | **Redirect URI(s)** | Both lines below — see the ⚠️ under this table |
   | **API Permissions** | Tick **OpenID Connect Permissions** (Profile only if sub-options appear; leave Email unchecked). ⚠️ See the note below — there is NO "Fantasy Sports" option here any more |
   | **OAuth Client Type** | **Confidential Client** (this is a server-side app; the secret lives in SSM, never in a browser) |

   **Redirect URIs — paste both, one per line:**
   ```
   https://api.credencesports.com/fantasy/import/yahoo/callback
   https://localhost:3000/fantasy/import/yahoo/callback
   ```

   > ⚠️ **THE KNOWN GOTCHA: Yahoo requires HTTPS.** An `http://` callback is rejected at
   > registration — including for localhost. If Yahoo refuses the local line, **drop it and register
   > only the production URI**; local development is covered by pointing `YAHOO_OAUTH_REDIRECT_URI`
   > at the production host, or by running the dev server behind an HTTPS tunnel.
   >
   > ⚠️ **THERE IS NO "FANTASY SPORTS" PERMISSION ON THIS FORM (confirmed on the live form
   > 2026-08-01).** Yahoo's own docs page still says *"select either Read or Read/Write access for
   > Fantasy Sports"* — that is **stale**. The live checklist offers only **OpenID Connect
   > Permissions** (with Profile/Email sub-options) and **TW Auction** (Yahoo Taiwan's
   > auction/commerce API — unrelated, leave it unchecked).
   >
   > This is not a problem, and it is the same finding as the review gate: **fantasy access is
   > provisioned server-side when your application in step 2 is approved**, which is exactly what
   > that form says (*"access will be provisioned after approval"*). Step 1 exists to produce the
   > **App ID** that step 2 asks for.
   >
   > Tick **OpenID Connect Permissions** anyway. Its job here is to make the app a *confidential
   > 3-legged OAuth client with a required Redirect URI* — the part we need. Our code never requests
   > an `id_token` and never reads profile or email, so it grants nothing we store; take **Profile
   > only** and leave Email unchecked if the sub-options appear (minimum the form will accept).

   > ⚠️ **It must match BYTE-FOR-BYTE** what the code sends — no trailing slash, no `www.`. The code
   > sends exactly `https://api.credencesports.com/fantasy/import/yahoo/callback`
   > (`yahoo_oauth.DEFAULT_REDIRECT_URI`, overridable via the `YAHOO_OAUTH_REDIRECT_URI` env var).
   > A mismatch fails the token exchange with an opaque `invalid_request` that gives no hint it is
   > the URI at fault — this is the single most common way this setup goes wrong.

3. Submit. Yahoo shows you a **Client ID (Consumer Key)** and **Client Secret (Consumer Secret)**,
   plus an **App ID**. **Copy all three now** — the secret is shown once.

## Step 2 — apply for Fantasy Sports API access (the new gate)

1. Go to **<https://sports.yahoo.com/developer/access/>** — *verified live 2026-08-01: a real
   application form.*
2. Complete it. The fields that matter, and what to say:
   - **Expected Users** → **Small (< 1,000 users)**. True today, and an honest small number is the
     easiest thing to approve.
   - **App ID** → the App ID from step 1. The form states: *"Existing Yahoo Developer Network users:
     enter the App ID from your YDN account."* Supplying it links the approval to the app you
     already made, which is why step 1 comes first.
   - **Use case / notes** → something like: *"Credence Sports is a subscription fantasy-football
     analytics product. We read a signed-in user's OWN league settings, rosters and draft results to
     generate personalised draft rankings for their league's scoring format. Read-only access is
     sufficient — we never write to a user's league. Yahoo attribution is displayed with a link back
     to Yahoo Fantasy wherever the data appears."*
   - Access is **read-only by default**, which is what we want — do not request read/write.
3. Submit and wait for Yahoo to reach out. **This is the unbounded step.**

## Step 3 — put the two secrets in SSM Parameter Store

Region **us-east-1** (the app stack's region — *not* the lakehouse's `us-east-2`).

**Run on the LAPTOP.** Substitute the real values for `PASTE_...`:

```bash
aws ssm put-parameter --region us-east-1 --type SecureString --overwrite \
  --name /credence/prod/yahoo_oauth_client_id \
  --value 'PASTE_CLIENT_ID_HERE'

aws ssm put-parameter --region us-east-1 --type SecureString --overwrite \
  --name /credence/prod/yahoo_oauth_client_secret \
  --value 'PASTE_CLIENT_SECRET_HERE'
```

Then generate and store the **token-encryption key**. This one is ours, not Yahoo's — it encrypts
each user's refresh token at rest, so reading the DynamoDB users table is not by itself enough to
use anyone's Yahoo grant:

```bash
# generates a fresh Fernet key and writes it straight to SSM (never printed to your shell history)
aws ssm put-parameter --region us-east-1 --type SecureString --overwrite \
  --name /credence/prod/yahoo_token_encryption_key \
  --value "$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

> 🔁 **Rotating this key invalidates every stored Yahoo connection** — users would see "please
> reconnect" (handled gracefully) and have to re-authorize. Rotate deliberately, not casually.

**The three parameter names, for the record:**

| Parameter | Type | What it is |
|---|---|---|
| `/credence/prod/yahoo_oauth_client_id` | SecureString | Yahoo Consumer Key (our app credential) |
| `/credence/prod/yahoo_oauth_client_secret` | SecureString | Yahoo Consumer Secret (our app credential) |
| `/credence/prod/yahoo_token_encryption_key` | SecureString | Fernet key encrypting each user's refresh token |

## Step 4 — grant the API Lambda permission to read them

The Lambda's execution role needs `ssm:GetParameter` on those three names and `kms:Decrypt` on the
key that encrypts them (the AWS-managed `alias/aws/ssm` key if you did not specify one).

**Run on the LAPTOP** (substitute the Lambda's actual role name — find it with
`aws lambda get-function-configuration --function-name credence-prod-lambda-api --region us-east-1 --query 'Role'`):

```bash
aws iam put-role-policy --role-name <LAMBDA_EXECUTION_ROLE_NAME> \
  --policy-name credence-yahoo-oauth-ssm-read \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": "ssm:GetParameter",
        "Resource": "arn:aws:ssm:us-east-1:*:parameter/credence/prod/yahoo_*"
      },
      {
        "Effect": "Allow",
        "Action": "kms:Decrypt",
        "Resource": "*",
        "Condition": {"StringEquals": {"kms:ViaService": "ssm.us-east-1.amazonaws.com"}}
      }
    ]
  }'
```

---

## How to tell it worked

1. `GET /fantasy/import/platforms` (as an admin/fantasy_comp user) returns the Yahoo entry with
   **`"configured": true`**. Until the SSM parameters exist it reports `false`, and the UI says
   *"Yahoo import is not switched on yet"* rather than offering a button that fails.
2. On `/fantasy/import`, pick **Yahoo → Sign in with Yahoo**. You should land on **Yahoo's own**
   consent screen, approve, and return to `/fantasy/import?yahoo=connected`.
3. **Load my Yahoo leagues** should list your real leagues; picking one shows the preview.

### If it fails

| Symptom | Almost certainly |
|---|---|
| `configured: false` after step 3 | The Lambda cannot read SSM → step 4 (IAM), or the parameter names are misspelled |
| Yahoo consent page shows an `invalid_request` / redirect error | Redirect URI mismatch — compare byte-for-byte with `yahoo_oauth.DEFAULT_REDIRECT_URI` |
| Consent succeeds but you return with `?yahoo=failed` | The token exchange was rejected — usually a wrong client secret. CloudWatch has the traceback |
| League list is empty but you have leagues | The step-2 access application is not approved yet. (There is no app-level Fantasy permission to check — approval is the only grant.) |

---

## What is already built (so you do not have to think about it)

- **Full 3-legged OAuth**: authorize redirect → Yahoo consent → callback → token exchange → refresh
  on expiry, with Yahoo's refresh-token **rotation** handled (Yahoo revokes the old one when it
  issues a new one, so the write-back is required for correctness).
- **CSRF protection**: the `state` parameter is HMAC-SHA256 signed, carries the user id, and expires
  in 15 minutes — so a returning grant can only attach to the account that started the flow.
- **Encrypted token store**: refresh tokens are Fernet-encrypted before they touch DynamoDB.
- **Honest degradation**: with no SSM parameters, every Yahoo route returns a **503 with an
  explanation** and the UI says so — it never 500s, and it never affects the Sleeper path.
- **Attribution**: *"Fantasy data provided by Yahoo Fantasy"*, linked back to Yahoo Fantasy, is
  rendered on any imported-Yahoo view — this is a Yahoo API **terms requirement**, not decoration.
- **We never see a password.** The user authenticates on Yahoo's own page. What we hold is a
  revocable, read-scoped grant, and the UI links to Yahoo's account-security page for revocation
  rather than pretending our "Disconnect" button revokes it upstream.

## One honest caveat about the Yahoo adapter

Sleeper's adapter was **verified end-to-end against a real live league**. Yahoo's could not be: every
Fantasy resource requires an approved app, which is exactly what step 2 is waiting on. So the Yahoo
**endpoints, auth flow and stat-id table are probe- or doc-verified**, but its **response parsing is
not yet exercised against a real payload**.

That gap shaped the code rather than being left to chance:

- Parsing **searches the response tree** for the fields it needs instead of indexing fixed positions
  (`league[1]["settings"][0]`). Yahoo's JSON mixes arrays with numeric-keyed objects and the
  ordering varies by resource — positional parsing is exactly the code that breaks on first contact.
- Scoring maps by **stat ID, not display name**: Yahoo ships id 6 *"Interceptions"* (thrown by a QB)
  and id 33 *"Interception"* (made by a defense), and a name-matching importer would silently pay
  quarterbacks for defensive picks.

**Expect to shake out one or two parsing details on the first real Yahoo league** — that is a
15-minute fix once a payload is in hand, and the preview-before-save flow means a mis-read is
visible on screen before it ever becomes a saved league.
