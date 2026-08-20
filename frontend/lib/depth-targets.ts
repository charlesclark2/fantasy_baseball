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

/** ⭐ NF-C7b — THE MINIMUM THESE HELPERS ACTUALLY NEED. They read a roster and nothing else, and
 *  two different config shapes carry one: `LeagueConfigMeta` (the draft surfaces') and
 *  `LeagueConfig` (the league-settings editor's). Taking the narrow structural type lets the SAME
 *  control serve both without a cast — a cast between two league shapes is exactly where a field
 *  silently stops being read. `LeagueConfigMeta` satisfies this structurally, so no call site
 *  changed. */
export interface RosterShaped {
  roster: { count: number; eligible: string[]; bench?: boolean }[]
}

/** The order positions are offered in — a stable, familiar reading order rather than whatever the
 *  league's roster happens to list first. A position not in a league's roster is not offered. */
const POSITION_ORDER = ["QB", "RB", "WR", "TE", "K", "DST"] as const

/** Every position a depth target can name, for the ACCOUNT-level default — which applies across
 *  leagues and so has no single roster to read. Mirrors `DEPTH_TARGET_POSITIONS` in
 *  `app/backend/models/fantasy.py`; the shared precedence fixture pins that they agree. */
export const ALL_DEPTH_TARGET_POSITIONS: readonly string[] = POSITION_ORDER

/** Every position this league's STARTING lineup can seat, in `POSITION_ORDER`. Read off the config
 *  rather than hardcoded, so a superflex league offers QB depth and a league with no kicker slot
 *  does not offer a kicker target. */
export function depthTargetPositions(config: RosterShaped | undefined | null): string[] {
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
export function starterRequirement(config: RosterShaped | undefined | null, position: string): number {
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

/** The one place a target is normalised: a non-finite, negative, zero, out-of-range or
 *  unknown-position entry is DROPPED, so `{}` and `{QB: 0}` are the same inert thing and no caller
 *  has to check both.
 *
 *  ⭐ NF-C7b — DROPS RATHER THAN CLAMPS, AND MUST MATCH `app/backend/models/fantasy.py`. This
 *  originally clamped an over-large count to the ceiling. Once targets became a SAVED, SHARED
 *  setting that also has to be read server-side for the Chrome extension, clamping here and
 *  dropping there would mean the same stored map resolved to two different rosters depending on
 *  which surface read it — the E9.61 two-renderers shape, on a value the user is looking at.
 *  Dropping is the safer of the two to agree on: by the time a count reaches storage the user has
 *  no way to see a correction, so storing a number they never chose is worse than storing nothing.
 *  Unreachable from the UI either way — `NumericInput` refuses the keystroke — which is precisely
 *  why it had to be pinned rather than argued about.
 *
 *  The ceiling is cosmetic rather than protective: the tier does not scale with the shortfall, so a
 *  typo'd `999` could never have bought more than a `2` does. It exists to stop a nonsense number
 *  reaching the sentence shown beside a recommendation. */
export const MAX_DEPTH_TARGET = 20

export function sanitizeDepthTargets(raw: Record<string, unknown>): DepthTargets {
  const out: DepthTargets = {}
  for (const pos of POSITION_ORDER) {
    const n = Math.floor(Number(raw[pos]))
    if (!Number.isFinite(n) || n <= 0 || n > MAX_DEPTH_TARGET) continue
    out[pos] = n
  }
  return out
}

/** True when the user has actually asked for something — drives the "on" chip in the setup screens
 *  so an inert control does not read as an active one. */
export const hasDepthTargets = (t: DepthTargets | undefined | null): boolean =>
  !!t && Object.values(t).some((n) => n > 0)

// ══ NF-C7b — WHERE A TARGET COMES FROM ════════════════════════════════════════════════════════
// NF-C7 kept targets in `localStorage` keyed by season + scoring-format NAME. That had three
// consequences nobody chose: two different leagues on the same format silently shared one setting,
// nothing followed the user to another device, and — the real gap — the Chrome extension could not
// read them at all, because it never touches this browser's storage.
//
// So a target now has two homes: the SAVED LEAGUE (per league) and the ACCOUNT (a default for every
// league that has none). The browser key below survives for the one case neither covers: a draft
// run against a PRESET format rather than a saved league, where there is no record to write to.

/** The three answers `resolveDepthTargets` can give. Mirrors `SOURCE_*` in
 *  `app/backend/services/depth_targets.py`. */
export type DepthTargetSource = "league" | "account" | "local" | "none"

/**
 * Which targets apply, and WHERE THEY CAME FROM.
 *
 * Precedence: an explicit per-league value → the account default → this browser's local value →
 * none.
 *
 * ⭐ THE RULE LIVES IN ONE PLACE PER SIDE AND IS PINNED BY A SHARED FIXTURE
 * (`betting_ml/tests/fixtures/nf_c7b_depth_target_precedence.json`), which the Python tests and the
 * frontend tests both read. Neither side restates it in prose. E9.61 is the reason: two renderers of
 * one field become two rule sets, and the grep that clears one file says nothing about the other.
 *
 * ⭐ `league === null` AND `league === {}` ARE DIFFERENT, and that is the whole reason this is a
 * function rather than `league || account || local`. `null` means "never set for this league" and
 * inherits; `{}` means "the user cleared this league" and stops. Written the obvious way an empty
 * object is falsy, so clearing one league's targets would silently restore the account default —
 * the user would have no way to turn the feature off for that league and it would present as "my
 * setting will not save" (the E8.6 silent-save class).
 *
 * ⚠️ A LEAGUE VALUE REPLACES THE ACCOUNT DEFAULT WHOLE — it is not merged per position. A merge
 * would make "this league wants 6 RBs" quietly inherit an account-level `TE: 3` the user never
 * asked for here, and no single screen would show the effective set.
 *
 * ⚠️ `local` SITS BELOW `account` ON PURPOSE. A value typed into this browser months ago must not
 * outrank a default the user set deliberately on their account; the ad-hoc control exists for a
 * preset-format draft that has no record to write to, not as a third opinion about a saved league.
 */
export function resolveDepthTargets(args: {
  league?: DepthTargets | null
  account?: DepthTargets | null
  local?: DepthTargets | null
}): { targets: DepthTargets; source: DepthTargetSource } {
  if (args.league != null) {
    const league = sanitizeDepthTargets(args.league)
    // An explicit map resolves to itself even when normalisation empties it — one rule, so a client
    // that sent an unrecognised position cannot silently reinstate a default the user turned off.
    return Object.keys(league).length
      ? { targets: league, source: "league" }
      : { targets: NO_DEPTH_TARGETS, source: "none" }
  }
  const account = sanitizeDepthTargets(args.account ?? {})
  if (Object.keys(account).length) return { targets: account, source: "account" }

  const local = sanitizeDepthTargets(args.local ?? {})
  if (Object.keys(local).length) return { targets: local, source: "local" }

  return { targets: NO_DEPTH_TARGETS, source: "none" }
}

/** How the applied targets are described to the user. The sentence names the SCREEN to change them
 *  on, because a league target of `{QB: 2}` and an account default of `{QB: 2}` produce an
 *  identical board — indistinguishable until something says which one is in force. */
export const DEPTH_TARGET_SOURCE_LABEL: Record<DepthTargetSource, string> = {
  league: "from this league's settings",
  account: "from your account default",
  local: "set for this draft only",
  none: "not set",
}
