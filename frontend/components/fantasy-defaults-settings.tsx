"use client"

// NF-C7b — ACCOUNT-level fantasy defaults.
//
// NF-C7 shipped per-position depth targets in `localStorage`, keyed by season + scoring-format
// name. Three consequences nobody chose: two different leagues on the same format silently shared
// one setting, nothing followed the user to another device, and the Chrome extension — which never
// touches this browser's storage — could not read them at all.
//
// The fix gives a target two homes. This is the lower one: a default applied to every league the
// user has NOT given its own. The per-league value lives on the league record
// (/fantasy/league-settings) and wins; `lib/depth-targets.ts` owns that precedence and nothing
// here restates it.

import { useEffect, useMemo, useState } from "react"
import { DepthTargetsField } from "@/components/fantasy/depth-targets-field"
import { Button } from "@/components/ui/button"
import {
  ALL_DEPTH_TARGET_POSITIONS,
  sanitizeDepthTargets,
  type DepthTargets,
} from "@/lib/depth-targets"
import { useFantasyPreferences, useSaveFantasyPreferences } from "@/lib/fantasy-queries"

export function FantasyDefaultsSettings() {
  const prefs = useFantasyPreferences()
  const save = useSaveFantasyPreferences()
  const [draft, setDraft] = useState<DepthTargets | null>(null)
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error" | "dropped">("idle")

  // Seed ONCE from the server, and only after it answers. Seeding from `data ?? {}` would show an
  // empty control while the read was still in flight, which is indistinguishable from "you have no
  // defaults" — and a user who typed into it would overwrite a default they never saw.
  useEffect(() => {
    if (draft === null && prefs.data) setDraft(sanitizeDepthTargets(prefs.data.depth_targets ?? {}))
  }, [prefs.data, draft])

  const saved = useMemo(
    () => sanitizeDepthTargets(prefs.data?.depth_targets ?? {}),
    [prefs.data],
  )
  const dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(saved)

  const onSave = async () => {
    if (draft === null) return
    setStatus("saving")
    try {
      const result = await save.mutateAsync({ depth_targets: draft })
      // ⭐ COMPARE RETURNED AGAINST SENT (E8.6). These models set no `extra="forbid"`, so a backend
      // that predates this field accepts the request, ignores the key and returns 200 — the user
      // sees "Saved" and then watches the setting vanish on reload, with no error anywhere. The
      // only way to catch that from the client is to read back what the server actually stored.
      const stored = sanitizeDepthTargets(result.depth_targets ?? {})
      setStatus(JSON.stringify(stored) === JSON.stringify(draft) ? "saved" : "dropped")
    } catch {
      setStatus("error")
    }
  }

  return (
    <section className="rounded-lg border border-[#262626] bg-[#141414]">
      <div className="p-6">
        <h2 className="text-base font-semibold text-white">Fantasy Defaults</h2>
        <p className="mt-1 text-sm text-[#a3a3a3]">
          How many of each position you want to finish a draft holding. Applies to every league you
          have not given its own targets — in the draft optimizer, the mock draft, and the live
          draft assistant in the browser extension.
        </p>

        <div className="mt-4">
          {/* ⚠️ BRANCH ON DATA PRESENCE, NOT `isLoading` — a hydration-mismatch trap. The query is
              `enabled: !!accessToken`, and there is no token during SSR, so `isLoading` is FALSE on
              the server (disabled) and TRUE on the client's first render (fetching). Branching on
              it renders different text on the two passes and React throws #418. "No data yet" is
              the same on both. */}
          {!prefs.data && !prefs.isError ? (
            <p className="text-sm text-[#a3a3a3]">Loading your defaults…</p>
          ) : prefs.isError ? (
            // ⚠️ NAMED, never rendered as an empty control. An unreadable preference shown as "no
            // targets" is a claim we cannot support, and the user would edit from a blank slate
            // and overwrite whatever is really stored (the honest-empty-state rule).
            <p className="text-sm text-[#ef4444]">
              We couldn&apos;t load your defaults just now. Reload before editing — saving from here
              would overwrite whatever is stored.
            </p>
          ) : (
            <>
              <DepthTargetsField
                config={null}
                positions={ALL_DEPTH_TARGET_POSITIONS}
                targets={draft ?? {}}
                onChange={(next) => {
                  setDraft(next)
                  setStatus("idle")
                }}
              />
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <Button size="sm" onClick={onSave} disabled={!dirty || status === "saving"}>
                  {status === "saving" ? "Saving…" : "Save defaults"}
                </Button>
                {status === "saved" && <span className="text-sm text-[#22c55e]">✓ Saved</span>}
                {status === "error" && (
                  <span className="text-sm text-[#ef4444]">Couldn&apos;t save — try again.</span>
                )}
                {status === "dropped" && (
                  <span className="text-sm text-[#ef4444]">
                    Saved, but the server didn&apos;t store every value — reload to see what stuck.
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  )
}
