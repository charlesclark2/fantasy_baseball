// Per-SURFACE entitlement (E9.45). The app is multi-PRODUCT (betting + fantasy) and
// entitlement now differs BY SURFACE — a single paywall boolean is no longer enough:
//
//  • BETTING is GRANDFATHERED — open to every current access tier (admin / subscriber /
//    beta_tester). This mirrors the existing `has_access` rule; do NOT tighten it.
//  • FANTASY is a PAID feature: `subscriber` or `admin` or the `fantasy_comp` comp
//    allow-list ONLY. `beta_tester` is deliberately NOT granted fantasy (the divergence
//    from E9.8's paywall, where beta_tester bypasses) — no beta tier for fantasy.
//
// The `fantasy_comp` group is kept DISTINCT from `subscriber` on purpose: comps must not
// count toward E9.8's founding-100 $10→$20 flip, nor into paid analytics.
//
// The server enforces the same rule on the fantasy DATA endpoints (require_fantasy_access
// → 403) — this client helper only decides nav visibility / the locked-vs-open state.

export type Surface = "betting" | "fantasy"

// Betting = the existing has_access group set (E9.8's ACCESS_GROUPS). Grandfathered.
const BETTING_GROUPS = ["admin", "subscriber", "beta_tester"] as const
// Fantasy = paid subscribers + admin + the comp allow-list. No beta tier.
const FANTASY_GROUPS = ["admin", "subscriber", "fantasy_comp"] as const

export function canAccess(surface: Surface, groups: string[]): boolean {
  const allowed = surface === "fantasy" ? FANTASY_GROUPS : BETTING_GROUPS
  return allowed.some((g) => groups.includes(g))
}

// True for an operator/comp on the fantasy allow-list (distinct from a paid subscriber).
export function isFantasyComp(groups: string[]): boolean {
  return groups.includes("fantasy_comp")
}
