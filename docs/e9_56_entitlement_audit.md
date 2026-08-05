# E9.56 — API entitlement + anti-scrape audit

**Date:** 2026-08-04 · **Branch:** `e9.56-entitlement` · **Status:** enforcement shipped; the launch
gateway flip + the live post-deploy attacker test are operator steps (see the handoff).

**The honest frame, restated because it decides what is worth building.** You cannot hide an endpoint
or its payload from dev-tools — the browser must receive what it renders, so anything fetched is
readable and replayable. Renaming, encoding or minifying endpoints is theatre. The only defence is
that **there is nothing sensitive to see**: the server returns exactly what the caller is entitled
to. No obfuscation was built.

---

## 1. What was measured (not assumed)

All figures below are live readings against production on 2026-08-04, reproducible with
`uv run python scripts/check_api_entitlement.py`.

### 1.1 ⭐ The story's stated highest-risk leak does not exist

The story flagged the static S3 api-cache blobs as "the highest-risk leak vector … served publicly
off the api-cache bucket, so any 2026 value in a public blob bypasses ALL endpoint auth."

**Measured: both buckets refuse anonymous reads.**

| Bucket | Anonymous `GET` |
|---|---|
| `credence-prod-s3-api-cache` (`fantasy/nfl/2026/projections.json`) | **403** |
| `credence-prod-s3-api-cache` (`fantasy/nfl/track_record/manifest.json`) | **403** |
| `baseball-betting-ml-artifacts` | **403** |

Every blob is read server-side by the Lambda (`fantasy._load_json` → `s3.get_object` with the
execution role) and re-served through an entitlement check. There is no public blob to split, so
step 3 of the story ("split the static payloads") required **no bucket change** — the split is
enforced at the endpoint instead, which is strictly stronger.

The frontend also never fetches S3 directly: `grep` over `frontend/{lib,hooks,app,components}` finds
no `s3.amazonaws.com` / bucket-host reference, and `frontend/public/` holds only brand assets.

### 1.2 The season key space makes the split unusually clean

`s3://credence-prod-s3-api-cache/fantasy/nfl/` contains **only** `2026/` (boards, manifest,
projections) plus `track_record/` (`season_2019` … `season_2025`).

⇒ *every* board/projection artifact is the paid season, and *every* past-season artifact is already
the public receipts surface. "Past seasons free, 2026 locked" is therefore a boundary that already
matches how the data is stored — there is no mixed blob anywhere.

### 1.3 Route inventory

103 routes enumerated from the live FastAPI app with their full dependency chains. Summary:

| Class | Count | Gate |
|---|---|---|
| Cognito-authorized + a server-side dependency | 88 | gateway JWT + `get_user_id`/`require_*` |
| Deliberately public (marketing / OAuth / webhook) | 8 | see below |
| Gateway-authorized but **no** server-side dependency | 7 | gateway only — see §2.2 |

Deliberately public, each verified against the code rather than assumed:
`GET /health` · `GET /blog/posts` (+`/{post_id}`; filtered to `published=true`) ·
`GET /picks/featured` (landing-page teaser) · `GET /fantasy/nfl/track-record/{manifest,season}` ·
`POST /auth/refresh` · `POST /stripe/webhook` (Stripe signature) ·
`GET /fantasy/import/yahoo/callback` (HMAC-signed `state`) · `POST /feedback/data-quality`.

---

## 2. Findings and what was done

### 2.1 🚨 CRITICAL — a forged JWT is accepted on any gateway-`NONE` route

**This is the finding that gates the whole story**, because it makes the obvious implementation of
the freemium split actively dangerous.

Everywhere in this backend, `dependencies._decode_jwt_payload` reads a Bearer token **without
verifying its signature**. That is correct *because* the API Gateway JWT authorizer validated it
first — but that holds only while the route carries the authorizer. Measured:

```
forged unsigned JWT, payload {"cognito:groups":["subscriber","admin","fantasy_comp"]}
  GET /fantasy/nfl/track-record/manifest   (authorizer NONE) → 200   ← reaches the Lambda intact
  GET /fantasy/nfl/projections             (authorizer JWT)  → 401
  GET /picks/today                         (authorizer JWT)  → 401
```

The public routes today read no entitlement, so nothing leaks *yet*. But the launch step is
precisely "make the 2026 surfaces reachable without the authorizer" — and an entitlement-aware
public endpoint resolving `cognito:groups` through the usual unverified decode would hand the paid
projections to anyone who base64-encodes `{"cognito:groups":["subscriber"]}`. That is a **worse**
leak than the static-blob one the story was written to close, and the FastAPI source would look
entirely correct.

**Fixed** — `app/backend/services/jwt_verify.py`: real RS256 verification against the Cognito JWKS
(`python-jose[cryptography]`, already in the Lambda bundle — no new dependency), checking the
algorithm from our side, the `kid`, the signature, `exp`, `iss`, and the audience (`client_id` for
access tokens, which is what the frontend sends; `aud` for ID tokens). Fails closed: every failure
path, including an unreachable JWKS, yields anonymous.

`dependencies._groups_from_request` was hardened in the same shape: when the authorizer context is
**absent**, groups come only from a verified token. That protects any *future* route mounted public,
rather than relying on nobody ever doing so.

### 2.2 🚨 HIGH — `/admin/data-quality-reports` had no server-side admin check

`GET /admin/data-quality-reports` and `PATCH /admin/data-quality-reports/{id}/resolve` live in
`routers/feedback.py` (no router-level dependency) rather than `routers/admin.py` (where every route
carries `get_admin_user`). Their only protection was the gateway authorizer — which proves the caller
is **logged in**, never that they are an **admin**.

Consequence before the fix: any authenticated account — including a free `beta_tester` or a
`churned` user — could list every submitted report (each carrying the reporter's `user_email` (PII)
and free-text description) and mark any report resolved.

**Fixed** — both routes now `Depends(get_admin_user)`. No behaviour change for an actual admin.

### 2.3 The 2026 surfaces had no locked-marker mechanism (the story's core ask)

`/fantasy/nfl/{manifest,projections,board}` were all-or-nothing: `require_fantasy_access` → full
payload or 403. The operator's rule needs a third state — the row visible, the value withheld, a
CTA rendered.

**Built** — `app/backend/services/entitlement.py` + a second router object (`fantasy.board_router`,
carrying no `require_fantasy_access`, mirroring the existing `fantasy_public.router` /
`fantasy_import.public_router` idiom: an exemption is a separate router, never a flag inside the
gated one). The gated `router` keeps its blanket 403 for everything else.

Three properties make the redaction actually safe:

1. **Allowlist, never denylist.** `_PUBLIC_*_FIELDS` names what a non-entitled caller *may* see;
   everything else is dropped. Under a denylist, the next field an exporter adds would be public by
   default on the next publish — no code change, no failing test, no error.
2. ⭐ **The row ORDER is itself the paid data.** `projections.json` is sorted by our projection
   within position and `board_*.json` by `ovrRank`, so a payload that nulls every number but keeps
   the array order hands over the ranking exactly — the array index *is* the rank. Locked payloads
   are re-sorted onto a public key (market ADP, then name).
3. **Container types preserved** (NF-C0): projections/manifest stay dicts with *additive* keys; the
   board stays a bare list, with lock state on each row and the page-level CTA copy on the manifest.

What a non-entitled caller receives for 2026: `id, name, pos, team, bye, rookie, draftPick,
birthDate, heightIn, weightLb, college, yearsExp, headshot, adp` + `locked: true`. No projection, no
interval, no rank, no VOR, no attribution, no confidence tier.

**One judgement call flagged for the operator:** market **ADP is kept** in the free view. It is
third-party consensus (FFC / MyFantasyLeague), not our model — it is the benchmark our projection is
measured *against* — and it supplies the public sort key that stops the ordering leak. If you want
ADP paid too, delete `_PUBLIC_MARKET_FIELDS`; `_public_sort_key` already falls back to
name-alphabetical, so nothing else changes.

### 2.4 Payload minimization

`featureLegend` + `featureContributionsMeta` (manifest) exist solely to label the entitled `contrib`
attribution panel; with `contrib` locked there is nothing for them to describe, so they are dropped
from a locked manifest. The locked projections payload also drops all ~60 raw stat columns.

Entitled payloads are deliberately **unchanged** — minimizing them further is a separate,
higher-risk change (every field there is rendered by some surface) and was not in this story's AC.

### 2.5 Rate limiting / bot protection

⚠️ **AWS WAF does not support API Gateway *HTTP* APIs** (v2) — it covers REST APIs, CloudFront, ALB,
AppSync and others. This API is an HTTP API (`credence-prod-apigw-api`), so the story's "WAF" option
is not directly available; the lever that is available is **stage/route throttling**. Commands are in
`infrastructure/aws_resources.md` → *API Gateway throttling*, as operator steps (the
`baseball-access-user` CLI profile has no `apigateway:*` permission, so these cannot be applied or
verified from a session).

Throttling will not stop one user reading one payload — nothing can. It stops the case that actually
matters: a competitor bulk-pulling the whole board in one pass, and daily polling of
`/picks/featured` (the one-free-pick teaser, which ships full model detail for that pick by
deliberate product design — the most attractive scrape target on the betting half).

⚠️ **Two mechanics that decide whether the caps do anything** (corrected 2026-08-04, after the
backend deploy): **(a)** per-route settings govern only routes that EXIST, and this API authorizes
per explicit route on top of a catch-all — most paths have no route object at all. An entry for a
non-existent key governs nothing while looking exactly like a limit that is in place, so the route
list must be read first; the 2026 routes do not exist until the launch flip creates them, making
their per-route caps a POST-flip step. **(b)** `update-stage --route-settings` REPLACES the whole map
rather than merging, so the current settings must be read and re-sent in one call. **(c)** Throttling
is per-API, not per-caller — HTTP APIs have no per-client dimension (usage plans are REST-only), so a
cap low enough to stop a scraper can also degrade a burst of genuine traffic. Per-caller limiting
would need CloudFront + WAF in front.

---

## 3. Verification

| Layer | Instrument | Result |
|---|---|---|
| Policy functions | `betting_ml/tests/test_e9_56_entitlement.py` | 30 pass |
| End-to-end through the real ASGI app | same file, `test_e2e_*` (raw ASGI — needs no `httpx`, and can set the `aws.event` scope key that carries the authorizer context) | anonymous → locked; forged token → locked; gateway-validated subscriber → real numbers; past season → free for everyone |
| Live production | `scripts/check_api_entitlement.py` | 42 pass, 0 fail |

**Every guard was RED-proven against deliberately-broken source** before being trusted — a guard that
cannot fail is worse than none (INC-38 / INC-39). Six breaks, and what went red:

| Break | RED |
|---|---|
| `_lock_row` returns the row unchanged | 4 |
| `lock_*_rows` drops the `sorted(...)` re-order | 2 |
| allowlist → denylist | 1 |
| `resolve_entitlement` falls back to the unverified decode | 2 |
| `_may_see_values` always True | 3 |
| board returns the raw list unredacted | 1 |

The suite also asserts the **no-regression** direction (a gateway-validated subscriber still gets the
real numbers, a past season is still free for everyone). Without those, a redaction bug that locked
*everyone* would satisfy every leak assertion and the suite would be green with the product broken.

### 3.1 What is NOT yet proven

The locked-payload path has **not** been exercised against production, because the 2026 routes are
still gateway-gated (401 before Lambda) — that is the correct pre-launch state, and it is why the
end-to-end ASGI tests exist. The live proof is the operator re-running
`scripts/check_api_entitlement.py --strict` **after** the launch gateway flip: check 4 then switches
from "gateway-gated" to asserting the payload carries no model field, no model ordering, and a
locked marker on every row.

---

## 4. Launch checklist (ordering is load-bearing)

1. Merge the PR to `dev` → `main`. **Frontend auto-deploys**; it now renders the locked marker and
   tolerates its absence (`?? ` / optional fields), so it is safe against the old backend.
2. `./infrastructure/lambda/deploy.sh` — the API Lambda has no CI/CD. Until this runs, the backend
   returns 403 to non-entitled fantasy callers exactly as before.
3. Apply the API Gateway throttling settings (§2.5).
4. **Only then**, and only when the public launch is wanted, flip the 2026 routes to
   `--authorization-type NONE` (commands in `infrastructure/aws_resources.md`).
5. Re-run `uv run python scripts/check_api_entitlement.py --strict` and confirm 0 FAIL.

⛔ Do not do step 4 before step 2: an un-deployed backend on a public route would serve the **full**
2026 payload to anonymous callers — the exact leak this story exists to prevent.
