# G100-C0-MFA — passwordless subscribers, and the flip that would have locked them out

**Status:** ✅ **VERIFIED LIVE 2026-08-13** against the real pool, both directions, with
`ENFORCE_SUBSCRIBER_MFA=1` genuinely on for the test window and restored afterwards.
⇒ E9.8-P2 is cleared to flip the flag. Measurements below; the runbook that produced them
follows, and is the re-verification procedure if this is ever suspected of regressing.

---

## ✅ What was measured (2026-08-13, live pool, `guard_version: g100-c0-mfa/1`)

**The acceptance pair — one account, one session type, the group as the only variable.**
`charlie@credencesports.com` (`347864d8-…`, created by the email-OTP door), in `subscriber`,
no TOTP, `mfa_enforced: true` on both readings:

| state | guard verdict | `GET /picks/today` |
|---|---|---|
| **with** `passwordless` | `totp_exempt: true`, `totp_exempt_reason: "passwordless_group"` | **200**, picks render |
| **without** it | `totp_exempt: false` | **403** "Two-factor authentication is required" |

Using one account for both halves is stronger than the two-account version this doc originally
prescribed: same username shape, same absent `amr`, same everything — so the flip is
attributable to the group and to nothing else. The genuine password account
(`legb-probe@…`, password set by hand, no TOTP) independently read
`would_be_blocked_if_subscriber: true`, which is the population that pair stands in for.

**⭐ There is no `amr`, on any door.** Password, Google, and a freshly-minted CUSTOM_AUTH
token straight out of `/verify` all return `amr: []`. The ACCESS token — which is what the
frontend sends — carries exactly:

```
auth_time, client_id, cognito:groups, event_id, exp, iat, iss, jti,
origin_jti, scope, sub, token_use, username
```

No `amr`, no `identities`. Consequences, all of them load-bearing:

1. `_amr_names_a_federated_idp` **cannot fire in production**. The pre-existing federated
   exemption rested entirely on the `google_…` username shape, i.e. only legacy
   federated-only accounts — which is exactly the lockout this story predicted, now with a
   measured mechanism rather than a hypothesis.
2. The `passwordless` group was not the cheapest signal available. It was the **only** one.
3. A **linked** Google user's session is indistinguishable from their password session (UUID
   username, no `amr`, no `identities`), so they WILL be challenged at flip time. Safe — they
   have a password and can enroll — but "Google sessions are exempt" is no longer true in
   general, and the PM should know it.

**⭐ `cognito:groups` really is bracketed, including for a single group.** Observed
`"[admin fantasy_comp]"`, `"[passwordless]"`, `"[subscriber]"`, `"[subscriber passwordless]"`,
and **absent entirely** (`null`, no key) for a user in no groups. The pre-fix comma split
would have matched nothing in *every* one of those cases, not just the multi-group one — so
with enforcement on, the guard would have gated **nobody**. The 403 above is the live proof
that it now does: the guard read `"[subscriber]"`, matched, and refused.

**Both creation paths write the group.** The OTP door was verified end-to-end (signup →
`is_passwordless: true`, and `admin-list-groups-for-user` returned `["passwordless"]` on the
same `sub`). The pre-provision door was verified by invoking the deployed trigger directly
with a synthetic `PreSignUp_ExternalProvider` event — real IAM role, real pool, group applied.
⚠️ Recorded honestly: that half is **"pre-provision group write verified by direct
invocation"**, not a full Google-first sign-in, which was last verified end-to-end at G100-C0
(2026-08-10). No fresh Google address was available to re-run it.

---

## The defect

`ENFORCE_SUBSCRIBER_MFA=1` is part of the E9.8 Stripe go-live. With it on,
`auth.require_subscriber_mfa` 403s any `subscriber` whose Cognito account has no TOTP factor,
exempting only sessions `_session_is_federated` recognises — which keys on `amr` and on the
federated **username shape** (`google_…`).

G100-C0 changed the population that lands on. A pre-provisioned or linked user's username is a
plain **UUID**, so the shape never matches, and the check fails CLOSED. That instruction was
right when the only alternative to a federated session was a password session: re-verifying
TOTP is an annoyance. It stopped being right the moment there were accounts with **no
password** — an email-OTP subscriber would be 403'd to `/settings?mfa=required`, whose only
exit (`reauthenticatePassword`) asks for a credential they have never had. A locked-out paying
customer with no self-service recovery, created by the flip itself.

## The fix

A Cognito group, `passwordless`, applied at the two points where we create a native user with a
random password nobody is ever told, and exempted in the guard:

| Path | Who it creates | Where |
|---|---|---|
| Email OTP, brand-new address | the person's native user | `app/backend/services/identity.py::create_native_user` |
| Google-first sign-in (pre-provision) | the native user Google is linked into | `infrastructure/cognito/presignup_link/handler.py::_preprovision_native_user` |

Groups ride inside the API-Gateway-validated token, so the signal is server-verifiable and
needs no pool schema change — unlike the client's `credence_auth_method` marker, which is
client-controlled and must never gate a security decision.

⛔ **The group is NOT applied when Google is linked into an EXISTING native user.** That
account may well have a real password (every beta account does), and marking it would hand a
permanent MFA exemption to a password account — the bypass this story exists not to create.
Guarded by `test_the_trigger_does_NOT_mark_an_existing_native_user`.

## ⭐ A second defect, found on the way, that the acceptance test depends on

`require_subscriber_mfa` parsed `cognito:groups` by splitting on `,` **only**. The API Gateway
HTTP API (v2) JWT authorizer flattens a multi-valued claim into a **bracketed, space-separated
string** (`[fantasy_comp subscriber]` — this repo's own measured finding, recorded in
`dependencies._groups_from_request`). So `"[subscriber]"` parsed to `["[subscriber]"]`, matched
no group, and **every subscriber returned early**: enforcement that reads as ON in the config
and enforces nothing.

That matters here beyond being a bug: leg B of the acceptance test ("a password subscriber is
still challenged") could not have passed with it in place, and its failure would have looked
like the exemption over-reaching rather than the gate never firing. Both readings now come from
one shared parser, `dependencies.parse_groups_claim`.

The pre-existing tests all passed because they were written with the comma form — a test that
restates the parser's own assumption rather than testing it (the NF-C0e class).

---

## The live gate

CI mocks all IO and cannot see Cognito, so nothing above is evidence. **A wrong exemption here
is an MFA bypass on a paying account and passes CI exactly as happily as the correct version.**

The instrument is `GET /auth/session-diagnostics` (authenticated, self-only): it reports the
claims as the Lambda receives them *after* the authorizer has validated the token, plus the
verdict the guard would reach. It answers both acceptance questions **without a real
subscription and without flipping the flag**, which is what makes this runnable safely.

### 0. Prerequisites (operator, LAPTOP)

```bash
export AWS_DEFAULT_REGION=us-east-1   # ⚠️ a lakehouse shell defaults to us-east-2 → every
                                      # command here fails with ResourceNotFoundException
```

**Create the group** (nothing else works until this exists — `admin_add_user_to_group` against
a group that does not exist raises, so the marking silently fails open and logs `[ALERT]`):

```bash
aws cognito-idp create-group \
  --user-pool-id us-east-1_gG9zMbwQt \
  --group-name passwordless \
  --description "No user-chosen password (email OTP / pre-provisioned). Exempt from subscriber TOTP — G100-C0-MFA."
```

**Grant the PreSignUp trigger role the group write.** ⚠️ `put-role-policy` REPLACES the named
policy, so this passes back the four existing actions plus the new one:

```bash
POOL_ARN=$(aws cognito-idp describe-user-pool --user-pool-id us-east-1_gG9zMbwQt \
  --region us-east-1 --query 'UserPool.Arn' --output text)
cat > /tmp/presignup-policy.json <<JSON
{ "Version": "2012-10-17", "Statement": [
  { "Effect": "Allow",
    "Action": ["cognito-idp:ListUsers", "cognito-idp:AdminLinkProviderForUser",
               "cognito-idp:AdminCreateUser", "cognito-idp:AdminSetUserPassword",
               "cognito-idp:AdminAddUserToGroup"],
    "Resource": "${POOL_ARN}" } ] }
JSON
aws iam put-role-policy \
  --role-name credence-prod-cognito-presignup-link-role \
  --policy-name presignup-link-cognito \
  --policy-document file:///tmp/presignup-policy.json
```

The API Lambda needs **no new grant** — `credence-prod-lambda-execution-role` already carries
`AdminAddUserToGroup` for the Stripe promotion path (verified working in test mode, E9.8).

**Deploy both halves** (neither has CD; a `git push` deploys the frontend only):

```bash
./infrastructure/cognito/presignup_link/deploy.sh   # the trigger
./infrastructure/lambda/deploy.sh                   # the API
```

**No API Gateway route step (NF3.2), and that is a conclusion, not an omission.** The
always-forgotten step applies to routes that must be made PUBLIC; this one is authenticated, so
it is served by the catch-all that already carries the JWT authorizer — which is also what makes
its "self-only" property enforceable. Nothing to create, and nothing to add to the CDN
allowlist or the public cache rules: `/auth` is degrade-allowlisted (correctly — nobody could
sign in otherwise), but the response carries a token, so `cache_control_for` forces
`private, no-store` and it can never reach a shared cache. Pinned by a test.

### 1. Confirm the deploy actually landed

A merged PR is not a deployed Lambda. Sign in as any account and:

```js
// browser devtools console, on https://www.credencesports.com while signed in
const P = 'CognitoIdentityServiceProvider.1qh95e78bd7g6ipqcvdcpf7ou6'
const u = localStorage.getItem(P + '.LastAuthUser')
const t = localStorage.getItem(`${P}.${u}.accessToken`)   // the app sends the ACCESS token
const r = await fetch('https://api.credencesports.com/auth/session-diagnostics',
                      { headers: { Authorization: 'Bearer ' + t } })
console.log(JSON.stringify(await r.json(), null, 2))
```

`guard_version` must read `g100-c0-mfa/1`. Anything else (or a 404) means the API Lambda is
running an older build — stop here.

### 2. Leg A — a passwordless session is exempt (the lockout half)

In a **private window**, with an address that has never touched the product: sign up at
`/signup` via **"Email me a sign-in code"**, land signed in, then run the snippet above.

Required:

```jsonc
{
  "authorizer_context_present": true,     // else nothing below was gateway-validated
  "is_passwordless": true,                // the group was applied at creation
  "totp_exempt": true,
  "totp_exempt_reason": "passwordless_group",
  "would_be_blocked_if_subscriber": false // ⭐ the lockout question, answered
}
```

⭐ **Record `amr` and `groups_claim_raw` verbatim in this doc when you run it.** They are the
two things nobody has ever seen for a CUSTOM_AUTH session, they are why this story exists
separately from G100-C0, and the second one is the delimiter that made the old parse a no-op.

Cross-check the group from the other side:

```bash
UUID=$(aws cognito-idp list-users --user-pool-id us-east-1_gG9zMbwQt \
  --filter "email = \"<the address>\"" --query 'Users[0].Username' --output text)
aws cognito-idp admin-list-groups-for-user --user-pool-id us-east-1_gG9zMbwQt \
  --username "$UUID" --query 'Groups[].GroupName'
```

Then repeat the whole leg with a **second fresh address signing in with Google first** — that
is the pre-provision path, a different writer of the same group, and the population whose
username is a UUID rather than `google_…`.

### 3. Leg B — a password session is still challenged (the bypass half)

Sign in with an ordinary **password** account (any beta account) and run the snippet:

```jsonc
{
  "is_passwordless": false,
  "totp_exempt": false,
  "totp_exempt_reason": null,
  "totp_enrolled": false,                 // an account WITHOUT TOTP, deliberately
  "would_be_blocked_if_subscriber": true  // ⭐ the bypass question, answered
}
```

⚠️ If that account has TOTP enrolled, `would_be_blocked_if_subscriber` is `false` for the right
reason — use one without it, or the leg proves nothing.

### 4. The end-to-end confirmation (enforcement actually on)

Legs 2–3 are dry runs of the same predicate the guard uses; this is the real thing. Put a test
account in `subscriber`, flip the flag, exercise both, flip it back.

```bash
# ① make a passwordless test account a subscriber
aws cognito-idp admin-add-user-to-group --user-pool-id us-east-1_gG9zMbwQt \
  --username "$UUID" --group-name subscriber
```

⚠️⚠️ **THEN SIGN THAT ACCOUNT OUT AND BACK IN.** `cognito:groups` is stamped into the token
at ISSUANCE — a group added to a live session does not appear until new tokens are minted. Skip
this and `session-diagnostics` reports `is_subscriber: false` on an account you just made a
subscriber, which reads exactly like the group write having failed. The same applies to every
account you touch in the backfill (§5): the exemption does not reach an already-open session.

```bash
# ② turn enforcement on  ⚠️ update-function-configuration REPLACES the whole Variables map —
#    read the current one and pass it back with the flag added, or you wipe the API's env.
aws lambda get-function-configuration --function-name credence-prod-lambda-api \
  --query 'Environment.Variables' --output json > /tmp/api-env-before.json   # ⭐ KEEP THIS
jq '{Variables: (. + {ENFORCE_SUBSCRIBER_MFA: "1"})}' /tmp/api-env-before.json > /tmp/api-env-on.json
jq '{Variables: .}'                                  /tmp/api-env-before.json > /tmp/api-env-restore.json

aws lambda update-function-configuration --function-name credence-prod-lambda-api \
  --environment file:///tmp/api-env-on.json
```

⚠️ `--environment` takes `file://` JSON of the form `{"Variables": {...}}`. The shorthand
(`Variables={K=v,…}`) cannot carry an arbitrary JSON map, and a malformed one is how you lose
the function's whole environment.

Then, signed in as each account, call a paid endpoint (e.g.
`GET https://api.credencesports.com/picks/today`) with the access token:

- passwordless subscriber → **200** (and `session-diagnostics` shows `mfa_enforced: true`)
- password subscriber without TOTP → **403** "Two-factor authentication is required"

Finally restore:

```bash
aws lambda update-function-configuration --function-name credence-prod-lambda-api \
  --environment file:///tmp/api-env-restore.json
aws cognito-idp admin-remove-user-from-group --user-pool-id us-east-1_gG9zMbwQt \
  --username "$UUID" --group-name subscriber
```

and re-run `session-diagnostics` to confirm `mfa_enforced` is back to `false` — read the flag,
do not infer it from a status code.

> ⚠️ Pick the window deliberately. `ENFORCE_SUBSCRIBER_MFA=1` is account-wide for the whole
> API; while it is on, ANY real subscriber without TOTP is 403'd. Today there are none (Stripe
> is still in test mode), which is exactly why this is a safe context now and will not be later.

### 5. Backfill the accounts created before this shipped

Every passwordless account created between G100-C0's deploy (2026-08-10) and this one has no
group and would be locked out. Small, closed set — but list and confirm each **by hand**:
over-applying the group is an MFA exemption for a password account.

```bash
aws cognito-idp list-users --user-pool-id us-east-1_gG9zMbwQt \
  --query 'sort_by(Users, &to_string(UserCreateDate))[].{U:Username,Created:UserCreateDate,Status:UserStatus}' \
  --output table
```

⛔ Do NOT filter with `Users[?UserCreateDate>=\`2026-08-10\`]`. JMESPath's `>=` is defined for
NUMBERS only; against a timestamp it evaluates to null, the filter drops every row, and you get
an empty table that reads as "nothing to backfill" — a false clean on the one step whose whole
job is finding accounts. Sort and read the dates yourself.

For each one you can confirm never chose a password (an OTP signup, or a Google-first
pre-provision — both have UUID usernames and appear in the email-OTP / presignup CloudWatch
logs):

```bash
aws cognito-idp admin-add-user-to-group --user-pool-id us-east-1_gG9zMbwQt \
  --username <uuid> --group-name passwordless
```

⛔ Do **not** add it to a beta account, an admin account, or anyone who has ever set a password.

---

## What this does NOT close (stated, not hidden)

1. **The group describes the ACCOUNT, not the SESSION.** Someone who later gives themselves a
   password through forgot-password keeps the exemption until the group is removed. Bounded —
   the reset proves control of the same mailbox the exemption is predicated on — but real.
   ⛔ **The tightening this doc originally proposed is impossible, and that is now measured,
   not suspected.** The plan was `passwordless_group AND amr does not indicate a password`,
   pending the live reading. The reading came back empty: **no door carries an `amr`**, so
   there is no per-session signal to add. The only honest candidates left are (a) REMOVE the
   group when someone sets a password — the password-reset flow is client-driven against
   Cognito today, so this needs a backend hop or a trigger — or (b) mint a claim from a
   PreTokenGeneration trigger. Neither is needed to ship. ⛔ Do not re-propose the `amr`
   version; it was checked.
2. **An OTP sign-in by someone who DOES have a password is still challenged.** Any native user
   can use the OTP door, so an OTP session is not proof of passwordlessness. Such a person is
   asked for TOTP they can actually enroll (they have a password to re-authenticate with), so
   this is an annoyance, not a lockout — and erring this way is the correct direction.
3. **A failed group write at creation fails OPEN**, matching the discipline of the only public
   signup path. It logs `[ALERT] passwordless-group assignment FAILED …` with the exact repair
   command. Grep for that string after any signup incident.

## Rollback

The flag itself: leave `ENFORCE_SUBSCRIBER_MFA` unset/`0` — the guard is inert and the
exemption cannot matter. The group assignment is additive and harmless while the flag is off.

## Guards

`betting_ml/tests/test_g100_c0_mfa_passwordless.py` — 45 tests, both directions, each exemption
clause fixture-isolated (NF-D17). Six deliberate breaks were applied to the real source and all
six went RED before the suite was trusted (the harness asserts each mutation actually landed
first — a red-proof that can silently no-op reports a false pass).
</content>
