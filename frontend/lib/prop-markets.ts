// E5.10 — the ONE description of a loggable prop market, shared by both bookkeeping
// affordances: "Log a prop" (the manual back-log dialog, log-past-prop-dialog.tsx) and
// "Log this prop" (the one-click copy on a projection page, log-prop-button.tsx).
//
// WHY SHARED: the `market` string here is what settlement grades against
// (settle_user_bets.py `_K_PROP_MARKETS` / `_TB_PROP_MARKETS`, and the same set in
// app/backend/models/bets.py). Two surfaces posting bets independently is exactly the
// "two renderers of one field are two rule sets" failure — one could ship a market string
// settlement does not know, and such a bet sits Pending forever with no error anywhere
// (the E9.49 unsettleable-bet class). They read from this table instead.
//
// 🔒 HONEST FRAMING: every string here is user-facing copy, so it carries no profitability
// or recommendation framing — these are bookkeeping records of what the USER entered. The
// banned-language scan (betting_ml/tests/test_k_projection_serving.py) covers this file and
// both consumers. ⚠️ That scan is a RAW TEXT match, so it fires on the banned words even
// inside a comment explaining the rule — describe the policy, never spell out its examples.

export type PropKind = "strikeouts" | "total_bases"

export interface PropMarketConfig {
  /** Human label for the prop-type picker. */
  label: string
  /** Back-log picker source. */
  endpoint: string
  /** Key holding the row array in that endpoint's response. */
  collection: string
  /** React-Query key prefix. */
  queryKey: string
  /** Noun for the player being logged ("Pitcher" / "Batter"). */
  playerLabel: string
  /** Label above the line input. */
  lineLabel: string
  linePlaceholder: string
  /** Short tag appended to the stored `matchup` string (e.g. "Ohtani K vs BOS"). */
  matchupTag: string
  /** ⚠️ Graded by settle_user_bets.py — changing these breaks settlement silently. */
  marketOver: string
  marketUnder: string
  /** Plain-language statement of what the bet settles against. */
  settlesAgainst: string
  /** Placeholder when the picker has no rows for the chosen date. */
  emptyLabel: string
}

export const PROP_MARKETS: Record<PropKind, PropMarketConfig> = {
  strikeouts: {
    label: "Pitcher strikeouts",
    endpoint: "/props/starters",
    collection: "starters",
    queryKey: "prop-starters",
    playerLabel: "Pitcher",
    lineLabel: "Strikeout line",
    linePlaceholder: "6.5",
    matchupTag: "K",
    marketOver: "strikeouts over",
    marketUnder: "strikeouts under",
    settlesAgainst: "the pitcher's actual strikeouts",
    emptyLabel: "No starters for this date yet",
  },
  total_bases: {
    label: "Batter total bases",
    endpoint: "/props/batters",
    collection: "batters",
    queryKey: "prop-batters",
    playerLabel: "Batter",
    lineLabel: "Total bases line",
    linePlaceholder: "1.5",
    matchupTag: "TB",
    marketOver: "total bases over",
    marketUnder: "total bases under",
    settlesAgainst: "the batter's actual total bases",
    emptyLabel: "No posted lineups for this date yet",
  },
}

export const PROP_KINDS = Object.keys(PROP_MARKETS) as PropKind[]

/** Title-case a book slug ("bovada" → "Bovada") so logged props read like the rest of the log. */
export function bookLabel(book: string): string {
  return book ? book.charAt(0).toUpperCase() + book.slice(1) : book
}
