// Config-driven paywall route-guard (E9.8, REVISED by E9.45).
//
// ⭐ E9.45 owns the paywall boundary. E9.8 shipped a PROVISIONAL boundary that gated the
// BETTING surfaces as paid — a placeholder. The real model is per-SURFACE (see
// lib/entitlements.ts): BETTING is FREE/grandfathered — open to every current user —
// and FANTASY is the paid surface. Fantasy is NOT gated here: it uses the per-surface
// `canAccess('fantasy')` (subscriber/admin/fantasy_comp, NOT beta_tester) via
// FantasyGuard client-side + the backend require_fantasy_access (403) server-side. A
// single access-group boolean can't express that divergence, so this generic gate
// deliberately holds NO betting prefixes — betting must never be locked for a current
// user, even if PAYWALL_ENABLED is later flipped on.
//
// The whole paywall is inert until NEXT_PUBLIC_PAYWALL_ENABLED=1.

export const PAYWALL_ENABLED = process.env.NEXT_PUBLIC_PAYWALL_ENABLED === "1"

// Groups that grant full (betting) access — the grandfathered set. Order irrelevant.
const ACCESS_GROUPS = ["admin", "subscriber", "beta_tester"] as const

// Paid (generically gated) route prefixes. EMPTY under the E9.45 model: betting is
// grandfathered-free, and the paid surface (fantasy) is gated per-surface (FantasyGuard
// + the backend), not by this single-boolean guard. Kept as the extension point if a
// future non-fantasy surface ever needs the generic access-group gate.
export const PAID_ROUTE_PREFIXES: string[] = []

// Routes that must ALWAYS stay reachable regardless of the paywall (auth/enrollment/
// billing surfaces) — guards against a misconfigured prefix locking a user out of the
// very page they'd use to subscribe or enable MFA.
const ALWAYS_FREE_PREFIXES = [
  "/subscribe",
  "/settings",
  "/login",
  "/callback",
  "/forgot-password",
  "/reset-password",
]

export function hasEntitlement(groups: string[]): boolean {
  return ACCESS_GROUPS.some((g) => groups.includes(g))
}

export function isPaidRoute(pathname: string): boolean {
  if (ALWAYS_FREE_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + "/"))) {
    return false
  }
  return PAID_ROUTE_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + "/"))
}
