"use client"

// NF-C7 — the per-position DEPTH TARGET control, shared by the live draft tool and the mock draft.
//
// ⭐ ONE COMPONENT FOR BOTH SURFACES (E9.61: two renderers of one field are two rule sets). The two
// setup screens are near-duplicates and have drifted before; a targets grid copied into each would
// eventually offer different positions, different bounds or a different storage key, and the user
// would find their preference silently applied on one screen and not the other.
import { NumericInput } from "@/components/ui/numeric-input"
import { InfoTip } from "@/components/fantasy/shared"
import {
  MAX_DEPTH_TARGET,
  depthTargetPositions,
  starterRequirement,
  type DepthTargets,
  type RosterShaped,
} from "@/lib/depth-targets"

export function DepthTargetsField({
  config,
  targets,
  onChange,
  positions: positionsOverride,
}: {
  config: RosterShaped | undefined | null
  targets: DepthTargets
  onChange: (next: DepthTargets) => void
  /** NF-C7b — offer THESE positions instead of deriving them from a league's roster. The ACCOUNT
   *  default has no league, so there is no roster to read: it offers every position we project.
   *  Deliberately an override rather than "fall back to all when config is null" — a league whose
   *  roster genuinely seats nothing must still render nothing, and folding the two cases together
   *  would make a broken config look like an account-level control. */
  positions?: readonly string[]
}) {
  const positions = positionsOverride ?? depthTargetPositions(config)
  if (!positions.length) return null

  const set = (pos: string, n: number) => {
    const next: DepthTargets = { ...targets }
    // ⭐ 0 DELETES rather than storing a zero, so "no target" has exactly ONE representation and a
    // caller can never see `{QB: 0}` and `{}` behave differently (`lib/depth-targets` sanitises the
    // same way on read — the rule lives in one place).
    if (n > 0) next[pos] = Math.min(n, MAX_DEPTH_TARGET)
    else delete next[pos]
    onChange(next)
  }

  return (
    <div>
      <span className="mb-1 flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-gray-500">
        <InfoTip label="Depth targets">
          How many of each position you want on your roster IN TOTAL, starters included. A position
          you are short of gets a nudge once your starting spots are filled — weaker than an open
          starter slot, stronger than generic bench depth. Leave a box empty for no preference.
          Your league&apos;s required starters can never be starved by a target.
        </InfoTip>
      </span>
      <p className="mb-2 text-xs text-gray-500">
        Optional — leave a position at 0 for no preference. Bench picks are otherwise ranked on how
        many weeks you&apos;d actually have to start the player and by how much he beats your next
        man up.
      </p>
      {/* ⚠️ `min-w-0` on the grid ITEMS: a grid track's automatic minimum is its min-content width,
          so a long label or an unbreakable input can widen the track and give the whole page a
          horizontal scrollbar (NF-C2.1, measured on two surfaces). */}
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
        {positions.map((pos) => {
          const starts = starterRequirement(config, pos)
          return (
            <label key={pos} className="block min-w-0">
              {/* ⚠️ The starter count goes in the LABEL, not the input's `placeholder`: a
                  `NumericInput` renders `String(value)`, so a 0-valued field shows "0" and its
                  placeholder is unreachable — an invisible hint is not a hint. */}
              <span className="mb-1 block truncate text-[11px] font-medium text-gray-400">
                {pos}
                {starts > 0 && <span className="text-gray-600"> · starts {starts}</span>}
              </span>
              <NumericInput
                value={targets[pos] ?? 0}
                min={0}
                max={MAX_DEPTH_TARGET}
                ariaLabel={`${pos} depth target`}
                className="w-full rounded border border-[#262626] bg-[#0a0a0a] px-2 py-2 text-base sm:text-sm text-gray-200"
                onCommit={(n) => set(pos, n)}
              />
            </label>
          )
        })}
      </div>
    </div>
  )
}
