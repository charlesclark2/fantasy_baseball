// E9.26 — the ONE canonical performance-metric semantics for the frontend.
//
// Mirrors app/backend/services/metric_semantics.py exactly so every surface
// (Performance, Bet Log, the E9.40 "who called it" Results tally, any future
// record display) means the SAME thing by "win rate" and "record":
//
//   * record   — wins / (wins + losses); PUSHES ARE EXCLUDED from the denominator.
//   * decisive — wins + losses (the rate denominator).
//   * low sample — below SMALL_SAMPLE_N decisive settled outcomes a rate is not
//     trustworthy; surfaces flag it and should caveat / de-emphasise the number.
//   * ROI      — net realized P&L / stake actually at risk on SETTLED bets, net of
//     vig. Realized settlement only — never a market-advantage claim (best_alpha = 0).
//
// Keep this file free of any profitability framing; it is scanned by the
// honest-framing guard (betting_ml/tests/test_metric_semantics_e9_26.py).

// Must match SMALL_SAMPLE_N in the Python module.
export const SMALL_SAMPLE_N = 30

export interface Record {
  wins: number
  losses: number
  pushes: number
  decisive: number
  winRate: number | null
  lowSample: boolean
}

/** A settled outcome as stored on a bet: "win" | "loss" | "push" | "void" | null. */
export function recordFromOutcomes(outcomes: Array<string | null | undefined>): Record {
  let wins = 0
  let losses = 0
  let pushes = 0
  for (const o of outcomes) {
    if (o === "win") wins++
    else if (o === "loss") losses++
    else if (o === "push") pushes++
    // void / null / pending contribute nothing.
  }
  const decisive = wins + losses
  return {
    wins,
    losses,
    pushes,
    decisive,
    winRate: decisive > 0 ? wins / decisive : null,
    lowSample: decisive < SMALL_SAMPLE_N,
  }
}

/** Realized ROI = net P&L / settled stake at risk. Null when nothing settled. */
export function realizedRoi(netPnl: number | null, settledStake: number): number | null {
  if (settledStake <= 0 || netPnl == null) return null
  return netPnl / settledStake
}

/** e.g. 0.541 → "54.1%"; null/undefined → "—". */
export function fmtPct(val: number | null | undefined): string {
  if (val == null) return "—"
  return `${(val * 100).toFixed(1)}%`
}

/** Win-rate color thresholds shared across surfaces. */
export function winRateColor(val: number | null | undefined): string {
  if (val == null) return "text-gray-400"
  if (val > 0.52) return "text-[#10b981]"
  if (val >= 0.5) return "text-[#f59e0b]"
  return "text-[#ef4444]"
}

/** Compact honest record label, e.g. "12W–10L–1P". */
export function fmtRecord(r: Record): string {
  return `${r.wins}W–${r.losses}L–${r.pushes}P`
}
