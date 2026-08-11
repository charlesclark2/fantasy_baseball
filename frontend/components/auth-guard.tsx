"use client"

import React, { useEffect } from "react"
import { usePathname, useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"
import { canAccess, canAccessFantasyBeta, canConfigureLeague } from "@/lib/entitlements"
import { getMfaStatus, sessionUsesPasswordlessAuth, subscriberMfaRequired } from "@/lib/cognito"
import { TermsGate } from "@/components/terms-gate"

// E9.58 — carry the page the visitor was actually trying to reach through the sign-in wall.
// Every one of these bounces used to be a bare `/login`, so a stranger who followed a link to a
// walled surface, created an account and came back was deposited on /dashboard with no trace of
// where they had been heading. /login and /signup both honour `?next=` (sanitised to a
// same-origin path — see `sanitizeInternalPath`).
function loginHref(pathname: string | null): string {
  return pathname && pathname !== "/login" ? `/login?next=${encodeURIComponent(pathname)}` : "/login"
}

// Subscriber MFA enforcement (E9.19) — the SINGLE in-app gate that gates E9.8 go-live.
// No-op in beta (NEXT_PUBLIC_ENFORCE_SUBSCRIBER_MFA unset). When flipped on at Stripe
// launch: a `subscriber` who signed in with a password and hasn't enrolled TOTP is
// bounced to Settings to enroll. Google sessions are exempt (IdP MFA) — keyed off the
// session's auth METHOD, not a per-sub flag (post-E9.7 a linked user has both).
//
// G100-C0 — the exemption now reads "this session used no password" rather than "this session
// used Google". An email-OTP user has NO password at all, so bouncing them to enroll TOTP would
// strand them: the only way back off that screen (`reauthenticatePassword`) asks for a credential
// they have never had. Same property, correctly stated.
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { accessToken, groups, loading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (!loading && accessToken === null) router.push(loginHref(pathname))
  }, [loading, accessToken, pathname])

  useEffect(() => {
    if (loading || accessToken === null) return
    if (!subscriberMfaRequired(groups)) return
    if (sessionUsesPasswordlessAuth()) return
    let cancelled = false
    getMfaStatus()
      .then((status) => {
        if (!cancelled && !status.federated && !status.enabled) {
          router.push("/settings?mfa=required")
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
    // deliberately NOT keyed on pathname — this effect issues a network read, and re-firing it on
    // every in-app navigation would turn one MFA check into one per route change.
  }, [loading, accessToken, groups, router])

  if (loading || accessToken === null) return null
  // E9.58b — every authed surface goes through here, so this is the one place that guarantees
  // no signed-in account uses the product without an acceptance record on file. It renders its
  // children and overlays only when the backend positively reports none (see TermsGate).
  return <TermsGate>{children}</TermsGate>
}

// Fantasy surface gate (E9.45). A signed-in caller without fantasy entitlement
// (subscriber / admin / fantasy_comp) is bounced to /subscribe — the upsell. A
// beta_tester is deliberately NOT entitled here (they keep full betting access).
// This is the client half of a defense-in-depth pair: the fantasy DATA endpoints
// enforce the same rule server-side (403), so hiding the page is not the only gate.
export function FantasyGuard({ children }: { children: React.ReactNode }) {
  const { accessToken, groups, loading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (loading) return
    if (accessToken === null) { router.push(loginHref(pathname)); return }
    if (!canAccess("fantasy", groups)) { router.push("/subscribe"); return }
  }, [loading, accessToken, groups, router, pathname])

  if (loading || accessToken === null || !canAccess("fantasy", groups)) return null
  return <>{children}</>
}

// ── The FREE GENERIC BOARD surfaces (`Capability.GENERIC_BOARD`) ─────────────────────────────────
//
// Renders its children for EVERYONE — logged out, free, subscriber alike — because these surfaces
// carry no per-caller content at all: `/fantasy/nfl/{manifest,projections,board}` return the same
// bytes to every caller since the freemium build, so there is nothing here to gate.
//
// 🗄️ E9.56b introduced this guard for a WEAKER reason that no longer applies: those endpoints were
// then DUAL-MODE (an entitled caller got the numbers, everyone else got the same rows with every
// model value removed and `locked: true` in its place), and the point was that a locked point must
// render a "subscribe to unlock" CTA rather than vanish. The lock is retired; the guard is not,
// because its real job — below — was never about the lock.
//
// ⇒ bouncing a visitor to /login here would defeat the whole funnel. The free board IS the
// acquisition wedge, and a redirect is how you lose the visitor before they see it.
//
// ⚠️ WHY THIS IS A NAMED COMPONENT RATHER THAN JUST OMITTING THE GUARD (which is what NF3.2's
// player page does, and the reason that route has a long explanatory docstring instead):
// `grep -rl FantasyPublicGuard frontend/app` ENUMERATES the public set in one command. Guard
// OMISSION is not greppable — you would have to search for the ABSENCE of a wrapper, which no tool
// does well and no reviewer does reliably. Since the risk on this story is entirely "a page that
// should be gated quietly becomes public", the set has to be something a test can assert on; see
// `frontend/lib/__tests__/public-surface.test.ts`. (Same reasoning as E9.56's separate
// `board_router` on the backend: an exemption is a NAMED object, never a flag inside the gated
// thing. The NF3.1 player route predates this and could migrate onto it later — deliberately NOT
// done here, to keep this story's blast radius to the two surfaces it is about.)
//
// ⛔ DO NOT wrap a surface in this unless every endpoint it reads is `Capability.GENERIC_BOARD`.
// A page whose endpoints 403 a free caller (My Teams, League Settings, Import, saved leagues) would
// render permanently broken, and the draft optimizer is PAID for a product reason rather than a
// data one — its inputs are free, but it is the decision-support half of the boundary.
export function FantasyPublicGuard({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}

// NF-C0b — the manual league-settings editor: `admin` + `fantasy_comp` ONLY, which is
// NARROWER than the fantasy surface itself (a paying subscriber does not get it yet).
//
// A non-entitled caller is sent to the fantasy pages they DO have rather than to
// /subscribe: unlike a locked surface this is a staged rollout, not something a
// subscriber can buy their way into, so an upsell there would be a false promise.
// Server-side, /fantasy/leagues enforces the same rule (403) — these are WRITE
// endpoints, so hiding the page is explicitly not the gate.
export function FantasyBetaGuard({ children }: { children: React.ReactNode }) {
  const { accessToken, groups, loading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (loading) return
    if (accessToken === null) { router.push(loginHref(pathname)); return }
    if (!canAccess("fantasy", groups)) { router.push("/subscribe"); return }
    if (!canAccessFantasyBeta(groups)) { router.push("/fantasy/league-board"); return }
  }, [loading, accessToken, groups, router, pathname])

  if (loading || accessToken === null || !canAccessFantasyBeta(groups)) return null
  return <>{children}</>
}

// ⭐ G100-C1 — the SAVED-LEAGUE surfaces: My League, League Settings, Import.
//
// Signed in + a personalization quota above zero. That is every signed-in account today (the free
// quota is 1) and it is deliberately NOT `canAccess("fantasy", …)`: the whole story is that a free
// account gets one personalized league, so gating these on fantasy entitlement would 403 exactly
// the users this exists for.
//
// ⚠️ THE TWO REFUSALS GO TO DIFFERENT PLACES, and getting that wrong costs signups. A logged-out
// visitor is sent to LOGIN (with `next`, so they land back here) — they need an ACCOUNT, and
// sending them to /subscribe asks them to pay for something free. A signed-in caller whose quota
// has been withdrawn (`FREE_PERSONALIZED_LEAGUE_QUOTA=0`) is sent to /subscribe, because for them
// it genuinely is a membership. This mirrors the server exactly: 401 vs 403.
//
// ⛔ NOT the gate. `/fantasy/leagues` and `/fantasy/import/*` enforce the same rule server-side and
// these are WRITE endpoints — hiding a page stops nobody from POSTing a config straight to the API.
export function FantasyLeagueGuard({ children }: { children: React.ReactNode }) {
  const { accessToken, groups, loading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const allowed = canConfigureLeague(accessToken !== null, groups)

  useEffect(() => {
    if (loading) return
    if (accessToken === null) { router.push(loginHref(pathname)); return }
    if (!allowed) { router.push("/subscribe"); return }
  }, [loading, accessToken, allowed, router, pathname])

  if (loading || !allowed) return null
  return <>{children}</>
}

export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { accessToken, isAdmin, loading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (loading) return
    if (accessToken === null) { router.push(loginHref(pathname)); return }
    if (!isAdmin) { router.push("/dashboard"); return }
  }, [loading, accessToken, isAdmin, pathname])

  if (loading || accessToken === null || !isAdmin) return null
  return <>{children}</>
}
