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
              { label: "Draft Optimizer", href: "/fantasy/draft", key: "fantasy-draft" },
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
