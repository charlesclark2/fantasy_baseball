// Sport-first navigation model (E9.45). Primary axis = SPORT (MLB, NFL, …); within a
// sport, the available SURFACES (Betting, Fantasy). Only (sport × surface) combos that
// EXIST are declared here, so sparse combos render gracefully — today MLB has Betting
// only and NFL has Fantasy only (no empty tabs). Adding NFL→Betting or MLB→Fantasy later
// is a data edit here, not a nav rewrite — and the per-SKU GTM split stays a config change.
//
// `key` values MUST match the Nav `activeLink` prop each page passes, so the active
// highlight keeps working across the restructure.

import type { Surface } from "@/lib/entitlements"

export interface NavItem {
  label: string
  href: string
  key: string
  /** An extra entitlement this ITEM needs, beyond its surface's. Items with no `restrict`
   *  follow the surface gate. Nav visibility is cosmetic — the API enforces the same rule
   *  server-side.
   *
   *   • `"fantasy_beta"` — NF-C0b's league-settings editor: `admin` + `fantasy_comp` only, so a
   *     paying subscriber does not see it yet.
   *   • `"admin"` — admin ONLY, the narrowest tier there is. E8.1's MLB prospect board uses it
   *     while the surface is in development: `require_fantasy_access` would expose an unfinished
   *     surface to every subscriber, and even `fantasy_beta` is too wide. */
  restrict?: "fantasy_beta" | "admin"
  /** NF3.2 — the OPPOSITE of `restrict`: this item stays visible even when its surface is LOCKED
   *  (an unentitled caller normally sees only the "Unlock Fantasy" upsell in place of every item —
   *  see `isLocked`/the locked-branch rendering in `nav.tsx`). Only the past-season track record
   *  qualifies today: its data is genuinely public regardless of fantasy entitlement. */
  public?: boolean
}

export interface SurfaceGroup {
  surface: Surface
  label: string
  // Optional sub-section grouping within a surface (e.g. Betting vs Research under MLB).
  sections: { label: string | null; items: NavItem[] }[]
}

export interface SportNav {
  sport: string
  label: string
  surfaces: SurfaceGroup[]
}

export const SPORTS: SportNav[] = [
  {
    sport: "mlb",
    label: "MLB",
    surfaces: [
      {
        surface: "betting",
        label: "Betting",
        sections: [
          {
            label: null,
            items: [
              { label: "Dashboard", href: "/dashboard", key: "dashboard" },
              { label: "EV Tracker", href: "/ev-tracker", key: "ev-tracker" },
              { label: "Props", href: "/props", key: "props" },
              { label: "Parlay Calculator", href: "/parlay", key: "parlay" },
              { label: "Performance", href: "/performance", key: "performance" },
              { label: "Bet Log", href: "/bet-log", key: "bet-log" },
            ],
          },
          {
            label: "Research",
            items: [
              { label: "Teams", href: "/teams", key: "teams" },
              { label: "Players", href: "/players", key: "players" },
            ],
          },
        ],
      },
      // E8.1 — MLB→Fantasy. The comment at the top of this file said "today MLB has Betting only
      // and NFL has Fantasy only… adding MLB→Fantasy later is a data edit here, not a nav rewrite";
      // this is that edit. It inherits the fantasy surface gate automatically (`isLocked` in
      // nav.tsx keys on `g.surface === "fantasy"`, not on the sport), so the MLB board is upsold to
      // an unentitled visitor exactly like the NFL one.
      {
        surface: "fantasy",
        label: "Fantasy",
        sections: [
          {
            label: null,
            items: [
              // Order is PRODUCT order: the board is the surface, the disagreement view is the
              // differentiated cut OF that board and only makes sense after it.
              //
              // 🔒 `restrict: "admin"` — ADMIN ONLY while the surface is in development
              // (operator, 2026-08-02). Deliberately NOT `fantasy_beta`, which would also admit
              // `fantasy_comp`. Mirrors `get_admin_user` on the two `/fantasy/mlb/prospects/*`
              // routes; the API is the real gate, this only hides the nav entries. Both move
              // together when the surface opens up.
              {
                label: "Prospect Board",
                href: "/fantasy/mlb/prospects",
                key: "mlb-prospects",
                restrict: "admin",
              },
              {
                label: "Where We Disagree",
                href: "/fantasy/mlb/disagreements",
                key: "mlb-disagreements",
                restrict: "admin",
              },
              // E8.2 — league roster import. Same admin restriction as the board it overlays; it
              // opens up in the same single change (see the E8.1 comment above).
              {
                label: "My League",
                href: "/fantasy/mlb/league",
                key: "mlb-league",
                restrict: "admin",
              },
            ],
          },
        ],
      },
    ],
  },
  {
    sport: "nfl",
    label: "NFL",
    surfaces: [
      {
        surface: "fantasy",
        label: "Fantasy",
        sections: [
          {
            label: null,
            items: [
              // ⭐ Order is PRODUCT order, not build order. Rankings leads because it is the actual
              // product — the projection re-scored for YOUR league's format and roster. Projections
              // is the format-independent raw line underneath it: useful, but a supporting view.
              { label: "Rankings", href: "/fantasy/rankings", key: "fantasy-rankings" },
              { label: "League Board", href: "/fantasy/league-board", key: "fantasy-league-board" },
              { label: "Projections", href: "/fantasy/projections", key: "fantasy-projections" },
              // NF3.1 — direct lookup: search a name, land on his player page. A separate nav item
              // (not folded into Projections' own search box) because it is the entry point every
              // OTHER surface's Player cell links out to, so it needs to be reachable on its own.
              { label: "Player Search", href: "/fantasy/players", key: "fantasy-players" },
              { label: "Draft Optimizer", href: "/fantasy/draft", key: "fantasy-draft" },
              // NF-C0 — platform import: pull the real league in from Sleeper/Yahoo. Sits ABOVE
              // the manual editor because it is the path most users should take; the editor stays
              // as the floor beneath it for every league we cannot reach compliantly.
              {
                label: "Import League",
                href: "/fantasy/import",
                key: "fantasy-import",
                restrict: "fantasy_beta",
              },
              // NF-C0b — the manual customization floor: hand-enter a league we cannot import.
              // Restricted to admin + fantasy_comp while the editor is still proving out.
              {
                label: "My League Settings",
                href: "/fantasy/league-settings",
                key: "fantasy-league-settings",
                restrict: "fantasy_beta",
              },
              // NF-C6 — cross-league browse: every saved league's roster, scored under its own
              // format, in one place. Deliberately NOT `fantasy_beta`-restricted like Import/League
              // Settings above it: the endpoint reads at the standard fantasy gate (any subscriber),
              // so this stays correct without a second nav edit whenever NF-C0's write side opens
              // wider — today it just means an honest empty state for anyone without a saved league.
              { label: "My Teams", href: "/fantasy/my-teams", key: "fantasy-my-teams" },
              // NF3.2 — the past-season "receipts" proof asset. `public: true`: it stays reachable
              // even for a caller not entitled to Fantasy, since none of its data is the paid
              // current-season projection (see nav-model.ts's `NavItem.public` doc).
              {
                label: "Track Record",
                href: "/fantasy/track-record",
                key: "fantasy-track-record",
                public: true,
              },
            ],
          },
        ],
      },
    ],
  },
]

// Flatten a surface's sections into its items (for simple rendering / active checks).
export function surfaceItems(g: SurfaceGroup): NavItem[] {
  return g.sections.flatMap((s) => s.items)
}

// NF3.2 fix: `item.public` only matters once a visitor is INSIDE a surface's dropdown, but the
// whole sub-nav (every sport/surface dropdown) is itself hidden for a fully signed-out visitor
// (`showSubNav` in nav.tsx) — so a `public` item was structurally unreachable pre-login, the exact
// opposite of the point of marking it public. This flattens every `public` item across every
// sport/surface so nav.tsx can render them as a small always-visible link set regardless of auth
// state, independent of whether the full sub-nav is showing.
export function publicNavItems(): NavItem[] {
  return SPORTS.flatMap((sport) => sport.surfaces.flatMap((g) => surfaceItems(g).filter((i) => i.public)))
}
