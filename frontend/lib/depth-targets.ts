// NF-C7 — PER-POSITION DEPTH TARGETS: the user-facing half of the pick-recommendation upgrade.
//
// ══ WHY THIS EXISTS ═══════════════════════════════════════════════════════════════════════════
// NF-C7 replaced the bench comparator with an INSURANCE value — P(you actually need him) × his
// upgrade over the next man up. Measured over 120 paired drafts (NF-C-LDA-6) that is worth +77.3
// season points and captures 83% of a peeking oracle's headroom, and it is right ON AVERAGE.
//
// It is also, deliberately, LESS interested in a backup QB or TE than the rule it replaced: those
// were 47% and 53% of the retired rule's bench and are 21% / 24% of the oracle's. A user who wants
// one therefore has less of it than they did last week AND no way to ask. That is the wrong shape
// for a tool: the model should carry the average case and the user should be able to state a
// preference the model has no way to know.
//
// So: a target COUNT per position. A position short of its target sorts above one that is not,
// INSIDE the bench cohort only — below every open starter slot, above generic depth. It is an
// ORDERING TIER, the same mechanism the K/DST deferral already uses, NOT a score bonus: a weighted
// bonus was built first and MEASURED INERT (a VOR-shaped nudge added to an insurance-shaped score
// came to well under a point against bench backs scoring 50+, and never reached a panel). The
// reasoning is recorded in full beside `BENCH_RERANK_SHORTLIST` in `lib/draft-optimizer.ts`.
//
// ⛔ WHAT IS DELIBERATELY *NOT* EXPOSED: the bench comparator itself. Insurance beats the runner-up
// by 19.5 season points on the paired delta — a real difference, and not one a user has any basis
// to adjudicate. Offering "which valuation rule would you like?" would be dressing a measurement up
// as a preference.
//
// ⭐ SHARED BECAUSE THE RULE HAS TO HOLD ON BOTH SURFACES (E9.61). The live draft tool and the mock
// draft both read a depth target and both persist one; two copies of the storage key or of the
// default would let a user's targets silently apply on one screen and not the other.
import type { LeagueConfigMeta } from "@/lib/draft-optimizer"

export type DepthTargets = Record<string, number>

/** The order positions are offered in — a stable, familiar reading order rather than whatever the
 *  league's roster happens to list first. A position not in a league's roster is not offered. */
const POSITION_ORDER = ["QB", "RB", "WR", "TE", "K", "DST"] as const

/** Every position this league's STARTING lineup can seat, in `POSITION_ORDER`. Read off the config
 *  rather than hardcoded, so a superflex league offers QB depth and a league with no kicker slot
 *  does not offer a kicker target. */
export function depthTargetPositions(config: LeagueConfigMeta | undefined | null): string[] {
  if (!config) return []
  const seen = new Set<string>()
  for (const slot of config.roster) {
    if (slot.bench) continue
    for (const e of slot.eligible) seen.add(e)
  }
  return POSITION_ORDER.filter((p) => seen.has(p))
}

/** How many of this position the league REQUIRES you to start — the dedicated slots only.
 *  Rendered as the input's placeholder so "2" means something to the reader ("you start 1"). */
export function starterRequirement(config: LeagueConfigMeta | undefined | null, position: string): number {
  if (!config) return 0
  return config.roster.reduce(
    (a, s) => a + (!s.bench && s.eligible.length === 1 && s.eligible[0] === position ? s.count : 0),
    0,
  )
}

/**
 * ⭐ THE DEFAULT IS *OFF*, AND THAT IS A DELIBERATE CHOICE, NOT AN OMISSION.
 *
 * With no target set the engine's `depthBonus` is 0 for every candidate, so the shipped default is
 * EXACTLY the insurance rule NF-C-LDA-6 measured — nothing rides on a number nobody validated. A
 * roster-derived default (say "your starters plus one") would be a second, unmeasured ranking
 * shipped as though it were the measured one.
 */
export const NO_DEPTH_TARGETS: DepthTargets = {}

/** Targets are a PREFERENCE about a league, so they are keyed per league format — a superflex room
 *  wants two quarterbacks and a 1QB room does not. ⚠️ Deliberately NOT keyed on the draft slot: a
 *  user re-picking their slot has not changed their mind about wanting a backup tight end. */
export const depthTargetsStorageKey = (season: number, configName: string) =>
  `nfl-depth-targets-${season}-${configName}`

/** Read stored targets, tolerating anything. A corrupt or hostile blob yields NO targets, which is
 *  the inert state — never a partially-applied one. */
export function loadDepthTargets(season: number, configName: string): DepthTargets {
  if (typeof window === "undefined" || !configName) return NO_DEPTH_TARGETS
  try {
    const raw = window.localStorage.getItem(depthTargetsStorageKey(season, configName))
    if (!raw) return NO_DEPTH_TARGETS
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return NO_DEPTH_TARGETS
    return sanitizeDepthTargets(parsed as Record<string, unknown>)
  } catch {
    return NO_DEPTH_TARGETS
  }
}

export function saveDepthTargets(season: number, configName: string, targets: DepthTargets): void {
  if (typeof window === "undefined" || !configName) return
  try {
    window.localStorage.setItem(depthTargetsStorageKey(season, configName), JSON.stringify(targets))
  } catch {
    /* ignore quota — a preference is not worth failing a draft over */
  }
}

/** The one place a target is normalised: a non-finite, negative or zero entry is DROPPED, not
 *  clamped, so `{}` and `{QB: 0}` are the same inert thing and no caller has to check both. The
 *  ceiling is cosmetic rather than protective — the tier does not scale with the shortfall, so a
 *  typo'd `999` cannot buy more than a `2` does — but it stops a nonsense number reaching the
 *  sentence shown beside a recommendation. */
export const MAX_DEPTH_TARGET = 20

export function sanitizeDepthTargets(raw: Record<string, unknown>): DepthTargets {
  const out: DepthTargets = {}
  for (const [pos, v] of Object.entries(raw)) {
    const n = Math.floor(Number(v))
    if (!Number.isFinite(n) || n <= 0) continue
    out[pos] = Math.min(n, MAX_DEPTH_TARGET)
  }
  return out
}

/** True when the user has actually asked for something — drives the "on" chip in the setup screens
 *  so an inert control does not read as an active one. */
export const hasDepthTargets = (t: DepthTargets | undefined | null): boolean =>
  !!t && Object.values(t).some((n) => n > 0)
