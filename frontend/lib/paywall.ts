// Config-driven free-vs-paid paywall boundary (E9.8).
//
// ⚠️ OPERATOR DECISION OWED: which surfaces are free vs paid at Aug-1 launch is the
// one product call still open (GTM §11). This ships a PROVISIONAL boundary; changing
// it is a one-line edit to PAID_ROUTE_PREFIXES below — not a refactor.
//
// Access model (E9.4 Cognito groups): a user in ANY of {admin, subscriber, beta_tester}
// has full access. Everyone else (free / churned / signed-out) is sent to /subscribe
// when they hit a paid route. Beta testers bypass checkout entirely (they never pay).
//
// The whole paywall is inert until NEXT_PUBLIC_PAYWALL_ENABLED=1 (flip at go-live, in
// the coordinated launch step) so Phase-1 test-mode work never redirects real users.

export const PAYWALL_ENABLED = process.env.NEXT_PUBLIC_PAYWALL_ENABLED === "1"

// Groups that grant full access. Order irrelevant.
const ACCESS_GROUPS = ["admin", "subscriber", "beta_tester"] as const

// PROVISIONAL boundary — paid (gated) route prefixes. A pathname that starts with any
// of these needs an access group; everything else (landing, /about, /blog, /faq, the
// auth pages, /subscribe itself, /settings) stays free.
//
// Free at launch: the marketing/landing surface + auth + account/settings + the
// calculator (/parlay is a pure EV/breakeven calculator = a lead-gen hook).
// Paid: the daily model depth — dashboard, picks/EV, props, performance, research.
export const PAID_ROUTE_PREFIXES: string[] = [
  "/dashboard",
  "/ev-tracker",
  "/props",
  "/performance",
  "/players",
  "/teams",
  "/bet-log",
  "/picks",
]

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
