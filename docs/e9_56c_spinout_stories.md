# E9.56c spin-outs — two launch-funnel stories

Written for the PM to fold into `build_roadmap.md`. Both were found while fixing E9.56c's broken
CTAs, both are **out of scope for a frontend fix**, and both block a public fantasy launch in a way
no copy change can unblock.

They are ordered. **E9.58 is a hard dependency of E9.59**: a pricing page that converts strangers is
pointless while a stranger cannot open an account, and a self-serve signup with nothing to sell into
is a half-funnel. If only one ships, ship E9.58.

---

## E9.58 — Self-serve signup

### The problem

**There is no way for a member of the public to create an account.** Every "get an account"
affordance in the product is the same `mailto:charlie@credencesports.com` — the nav's Request Access
button, both home-page CTAs, the About page, and (as of E9.56c) the login page and `/subscribe`.

That was correct for a private beta. It stopped being correct the moment E9.56b opened the 2026
Rankings and Projections to the public and put a **Subscribe** button on every withheld number.
The funnel now reads:

> stranger lands on an indexed locked projection → clicks Subscribe → *"email Charlie and wait"*

Most people will not send the email. The measurable cost is invisible: there is no failed signup to
count, because there is no signup.

⚠️ E9.56c made the *copy* honest about this ("Credence is invite-only while we finish building") so
the page reads as a deliberate process rather than a broken one. **That is a holding pattern, not a
fix** — do not let the improved copy disguise the gap.

### Scope

1. **Cognito**: open the user pool for public registration (currently `AllowAdminCreateUserOnly`
   posture — confirm; `baseball-access-user` is denied `cognito-idp:DescribeUserPool`, so this needs
   operator-level AWS credentials to even *read*).
2. **Email verification.** Note the E9.57 finding already on record: *Cognito has no email
   auto-verify.* A signup flow that skips verification creates unverified accounts that later fail
   password reset — worse than no signup.
3. `/signup` route + `POST /auth/signup`; Google sign-in already exists via the Hosted UI and is the
   cheapest path to a working signup — **evaluate "Continue with Google" as the whole of v1** before
   building a password flow.
4. Terms/privacy acceptance at signup (the existing `POST /auth/accept-terms` already does this on
   the new-password path — reuse it, do not re-invent).
5. Retire the mailto from nav/home/about/login/subscribe **in one change**, once signup is live —
   `frontend/lib/access.ts` was created by E9.56c to centralise it, and nav/home still carry the
   literal because the home-page redesign owns those files. Adopt the constant there first.

### Acceptance

- A visitor with no account can go **locked projection → Subscribe → account → paying** without
  human involvement.
- A new account lands in the correct Cognito group (i.e. **not** entitled to fantasy until it pays —
  re-run `scripts/check_api_entitlement.py` after, since the group set is what
  `require_fantasy_access` reads).
- Email verification is exercised end-to-end, including the reset path afterwards.
- `test_e9_56c_cta_routes.py::test_every_internal_link_resolves_to_a_real_route` stays green — a new
  `/signup` link with no `page.tsx` fails it.

### Landmines

- **The API Gateway JWT authorizer is per-route and lives in the AWS console, not in this repo.** A
  new *public* signup route returns 401 before the Lambda is ever invoked until someone runs
  `aws apigatewayv2 create-route … --authorization-type NONE`. This has now bitten E9.56 and NF3.2.
  A public router in code is **not** done until the gateway route is confirmed.
- `deploy.sh` is manual — the backend half does not ship on `git push`.

---

## E9.59 — Pricing page

### The problem

`/subscribe` **cannot show a logged-out visitor the price.** `GET /subscription/pricing` is behind
`Depends(get_user_id)`, so the fetch 401s and the page renders no number at all. E9.56c worked
around it by showing the perks list to logged-out visitors (previously it rendered only inside the
signed-in branch, i.e. only to people who already had an account) — **the price is still absent.**

A subscribe page that won't say the price is a weak ask, and it is the page every padlock on the
free fantasy surfaces now points at.

Separately: **`/pricing` is not a real route.** E9.56c added a permanent `/pricing → /subscribe`
redirect in `next.config.mjs`, because `/pricing` was the URL every locked CTA shipped with and is
the URL people will type. Decide whether this story makes `/pricing` the real page and `/subscribe`
the checkout step, or keeps one page. **If `/pricing` becomes a real `page.tsx`, delete the
redirect** — a redirect shadowing a real route is the kind of thing that silently survives for
months.

### Scope

1. A **public** pricing read. Two options, and the choice is the story's main decision:
   - *Make `/subscription/pricing` public.* Cheapest. ⚠️ It returns `founding_slots_used` and
     `founding_cap` — publishing "3 of 100 founding slots taken" is a business-sensitive number and
     a weak signal early on. If public, **return only what the page renders** (E9.56's minimise-the-
     payload rule): `unit_amount`, `currency`, `founding_available`. Not the counts.
   - *Bake the price into the page at build time.* No new public surface at all; goes stale when the
     Stripe Price changes. Given how rarely that happens, this is the more conservative answer and
     probably the right one for v1.
2. Decide the `/pricing` vs `/subscribe` route split (above).
3. Reconsider the perks copy as marketing rather than a feature list. E9.56c added the NFL fantasy
   line because locked fantasy pages are now the largest inbound path and the list was **entirely
   MLB betting** — but it is still a list, not an argument.
4. **Lead with the track record.** `UpgradeBanner` already renders the NF3.2 headline verbatim on
   the locked surfaces and it is the strongest asset the product owns. The pricing page does not use
   it at all. ⚠️ NF-D3 claim scope applies: it is generated by
   `export_track_record_json.build_headline` from the scorecard's own numbers **precisely so a
   performance claim cannot be edited into marketing copy.** Render it; never retype it.

### Acceptance

- A logged-out visitor sees the price without an account.
- No business-sensitive field is added to a public payload (re-run
  `scripts/check_api_entitlement.py`; add the pricing route to its `DELIBERATE_PUBLIC` list with a
  field allowlist if it goes public).
- Whichever of `/pricing` / `/subscribe` is canonical, the other resolves — and the route guard
  still passes.

### Landmines

- The **same gateway-authorizer landmine as E9.58** if the pricing endpoint goes public.
- `resolveUpgradeHref` in `components/fantasy/shared.tsx` allowlists the CTA target the API returns.
  If the canonical route changes, update `KNOWN_CTA_ROUTES` **and** `entitlement.py`'s `ctaHref`
  together — `test_backend_cta_target_agrees_with_the_frontend_allowlist` pins them to each other,
  so a one-sided change fails CI rather than shipping a dead button. That test exists because a
  dead button is exactly what shipped in E9.56.
