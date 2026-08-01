"use client"

// NF-C0b — the MANUAL league-settings editor: the customization FLOOR.
//
// Platform import (NF-C0) is the CONVENIENCE path and it will never cover every league — unofficial
// and fragile ESPN endpoints, long-tail platforms, private leagues, partial imports. This editor is
// the GUARANTEE underneath it: whatever your league is, you can type it in and the fantasy tools
// work. It is the NFL analog of E8.2's manual-upload floor.
//
// 🎯 THE CONTRACT: this produces the SAME `fantasy_engine` LeagueConfig object a platform import
// produces. There is no second settings schema — an imported league and a typed-in league are the
// same object, so a config is portable between the two paths and every downstream surface (board,
// VOR, draft) reads them identically.
//
// 🚨 HONEST COVERAGE is the other half of the job, and it is enforced by CODE rather than by copy.
// A real league scores things we do not project (a defensive forced fumble, a fumble-recovery TD),
// and the scorer treats a missing column as a zero term — so those settings would be accepted and
// then silently score nothing. `resolveScoring` classifies every term against the projection data
// ACTUALLY PRESENT, and this surface renders that verdict verbatim:
//   • applied  — the weight moves the number exactly
//   • derived  — your league is finer than the projection (a 6-bucket FG table over our 3), folded;
//                exact when the sub-values agree, and labelled approximate when they genuinely differ
//   • captured — stored faithfully, contributes NOTHING to the board, and says so
// Nothing here can promote a term to "applied" by asserting it; only a projection column can.

import { useEffect, useMemo, useState } from "react"
import { Plus, Save, Trash2, TriangleAlert, Check, Info } from "lucide-react"
import {
  useCustomBoard,
  useDeleteLeague,
  useFantasyManifest,
  useSaveLeague,
  useSavedLeagues,
} from "@/lib/fantasy-queries"
import type { SavedLeague } from "@/lib/fantasy"
import {
  CAPTURED_RULE_CATALOG,
  POSITIONS,
  SCORING_CATALOG,
  SCORING_GROUPS,
  detectSuperflex,
  newCustomConfig,
  presetToConfig,
  resolveScoring,
  validateConfig,
} from "@/lib/league-config"
import type { LeagueConfig, RosterSlotConfig, TermCoverage } from "@/lib/league-config"
import { availableFields } from "@/lib/league-scoring"
import { useFantasyProjections } from "@/lib/fantasy-queries"
import { EmptyBlock, LoadingBlock, PosBadge, SurfaceHeader, num } from "@/components/fantasy/shared"

const VERDICT_STYLE: Record<string, string> = {
  applied: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  derived: "text-sky-400 bg-sky-500/10 border-sky-500/30",
  captured: "text-amber-400 bg-amber-500/10 border-amber-500/30",
}

const VERDICT_COPY: Record<string, string> = {
  applied: "Applied to your board exactly.",
  derived: "Folded onto the resolution our projection has.",
  captured: "Saved with your league, but NOT applied — we do not project this stat.",
}

export function LeagueSettingsEditor() {
  const { data: manifest } = useFantasyManifest()
  const { data: leagues, isLoading: leaguesLoading } = useSavedLeagues()
  const { data: projections } = useFantasyProjections()
  const saveLeague = useSaveLeague()
  const deleteLeague = useDeleteLeague()

  const [leagueId, setLeagueId] = useState<string | null>(null)
  const [cfg, setCfg] = useState<LeagueConfig>(() => newCustomConfig())
  const [dirty, setDirty] = useState(false)
  const [saved, setSaved] = useState(false)
  // Which preset was last loaded. Held in STATE rather than resetting the control to a
  // placeholder: loading a preset can legitimately change very little that is on screen —
  // "Full PPR" over a fresh config changes only the ROSTER, since the editor's defaults are
  // already full-PPR scoring — so a control that snaps back to "Choose…" reads as broken.
  const [presetChoice, setPresetChoice] = useState("")
  const [presetNote, setPresetNote] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  // Load the first saved league once, so returning users land on their own league.
  useEffect(() => {
    if (leagueId !== null || dirty || !leagues?.length) return
    const first = leagues[0]
    setLeagueId(first.league_id)
    setCfg(stripServerFields(first))
  }, [leagues, leagueId, dirty])

  const update = (patch: Partial<LeagueConfig>) => {
    setCfg((c) => ({ ...c, ...patch }))
    setDirty(true)
    setSaved(false)
  }

  const setStat = (key: string, value: number) =>
    update({ scoring: { ...cfg.scoring, per_stat: { ...cfg.scoring.per_stat, [key]: value } } })

  const errors = useMemo(() => validateConfig(cfg), [cfg])

  // ── the honest-coverage report, computed against the data actually present ──────────────────
  const coverage = useMemo(() => {
    const fields = projections?.players?.length ? availableFields(projections.players) : undefined
    return resolveScoring(cfg.scoring, {
      availableFields: fields,
      capturedRules: Object.keys(cfg.captured_rules ?? {}),
    }).report
  }, [cfg.scoring, cfg.captured_rules, projections])

  const byVerdict = (v: string) => coverage.terms.filter((t) => t.verdict === v)

  // A live preview proves the settings actually drive the board the tools will use.
  const preview = useCustomBoard(errors.length === 0 ? cfg : null)

  const onSave = async () => {
    if (errors.length) return
    const payload: LeagueConfig = { ...cfg, superflex: detectSuperflex(cfg.roster) }
    const result = await saveLeague.mutateAsync({ leagueId, config: payload })
    setLeagueId(result.league_id)
    setCfg(stripServerFields(result))
    setDirty(false)
    setSaved(true)
  }

  const onSelectLeague = (id: string) => {
    const found = leagues?.find((l) => l.league_id === id)
    if (!found) return
    setLeagueId(id)
    setCfg(stripServerFields(found))
    setDirty(false)
    setSaved(false)
    setPresetChoice("")
    setPresetNote(null)
    setConfirmDelete(false)
  }

  const onNew = () => {
    setLeagueId(null)
    setCfg(newCustomConfig())
    setDirty(true)
    setSaved(false)
    setPresetChoice("")
    setPresetNote(null)
    setConfirmDelete(false)
  }

  const onStartFromPreset = (presetName: string) => {
    setPresetChoice(presetName)
    const meta = manifest?.configs.find((c) => c.name === presetName)
    if (!meta || !meta.roster?.length) {
      // Never leave the control showing a selection that did nothing — that is the exact
      // failure this whole change exists to remove.
      setPresetChoice("")
      setPresetNote(null)
      setLoadError("That format could not be loaded — build your league below instead.")
      return
    }
    setLoadError(null)
    const next = presetToConfig(meta, cfg.n_teams)
    // Keep what the preset does not speak to: the league's NAME and the captured rules the user
    // ticked (median scoring and friends are independent of the scoring format, so changing the
    // starting point must not silently discard them).
    update({ ...next, name: cfg.name || next.name, captured_rules: { ...(cfg.captured_rules ?? {}) } })

    // Say what actually changed. Loading a preset is often a SMALL edit — the editor's defaults
    // are already full-PPR scoring, so "Full PPR" changes only the roster — and silence there is
    // indistinguishable from a broken control.
    const starters = next.roster.filter((s) => !s.bench).reduce((n, s) => n + s.count, 0)
    const flex = next.roster.filter((s) => !s.bench && s.eligible.length > 1).reduce((n, s) => n + s.count, 0)
    const rec = next.scoring.per_stat.rec ?? 0
    setPresetNote(
      `Loaded ${meta.label}: ${rec} pt per reception, ${starters} starting slots` +
        `${flex ? ` (${flex} flex)` : ""}. Edit anything below.`,
    )
  }

  const onDelete = async () => {
    if (!leagueId) return
    await deleteLeague.mutateAsync(leagueId)
    setLeagueId(null)
    setCfg(newCustomConfig())
    setDirty(false)
    setSaved(false)
    setConfirmDelete(false)
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <SurfaceHeader
        title="League settings"
        blurb="Enter your league's real settings by hand — no platform import required. Everything the tools use (the board, value over replacement, the draft optimizer) is computed from exactly what you set here."
      />

      {/* ── which league ─────────────────────────────────────────────────────────────────── */}
      <section className="mt-6 rounded-lg border border-gray-800 bg-[#0f0f0f] p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          <div className="w-full sm:min-w-[220px] sm:flex-1">
            <FieldLabel>Your leagues</FieldLabel>
            {leaguesLoading ? (
              <div className="text-sm text-gray-500">Loading…</div>
            ) : (
              <select
                className="w-full rounded border border-gray-700 bg-[#151515] px-2 py-2 text-sm text-gray-200"
                value={leagueId ?? ""}
                onChange={(e) => (e.target.value ? onSelectLeague(e.target.value) : onNew())}
              >
                <option value="">— New league —</option>
                {(leagues ?? []).map((l) => (
                  <option key={l.league_id} value={l.league_id}>
                    {l.name} ({l.n_teams}-team)
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={onNew}
              className="flex flex-1 items-center justify-center gap-1.5 rounded border border-gray-700 px-3 py-2 text-sm text-gray-300 hover:bg-gray-800 sm:flex-none"
            >
              <Plus className="h-3.5 w-3.5" /> New league
            </button>
            {leagueId && !confirmDelete && (
              <button
                onClick={() => setConfirmDelete(true)}
                className="flex flex-1 items-center justify-center gap-1.5 rounded border border-red-900/60 px-3 py-2 text-sm text-red-400 hover:bg-red-950/30 sm:flex-none"
              >
                <Trash2 className="h-3.5 w-3.5" /> Delete
              </button>
            )}
          </div>
        </div>

        {/* Deleting a saved league is irreversible, so it asks first rather than firing on one tap
            — easy to hit by accident on a phone, where the button sits next to "New league". */}
        {leagueId && confirmDelete && (
          <div className="mt-3 rounded border border-red-900/60 bg-red-950/20 p-3">
            <p className="text-xs text-gray-300">
              Delete <span className="font-medium text-white">{cfg.name}</span> permanently? Any
              surface currently showing this league will fall back to a standard format.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                onClick={onDelete}
                disabled={deleteLeague.isPending}
                className="rounded bg-red-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-60"
              >
                {deleteLeague.isPending ? "Deleting…" : "Yes, delete it"}
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="rounded border border-gray-700 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-800"
              >
                Cancel
              </button>
            </div>
            {deleteLeague.isError && (
              <p className="mt-2 text-xs text-red-400">
                Could not delete. {(deleteLeague.error as Error)?.message ?? "Please try again."}
              </p>
            )}
          </div>
        )}

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <FieldLabel>League name</FieldLabel>
            <input
              className="w-full rounded border border-gray-700 bg-[#151515] px-2 py-2 text-sm text-gray-200"
              value={cfg.name}
              maxLength={80}
              onChange={(e) => update({ name: e.target.value })}
            />
          </div>
          <div>
            <FieldLabel>Teams</FieldLabel>
            <input
              type="number"
              inputMode="numeric"
              min={2}
              max={32}
              className="w-full rounded border border-gray-700 bg-[#151515] px-2 py-2 text-sm text-gray-200"
              value={cfg.n_teams}
              onChange={(e) => update({ n_teams: Number(e.target.value) })}
            />
          </div>
          <div className="sm:col-span-2 lg:col-span-1">
            <FieldLabel>Start from a preset</FieldLabel>
            <select
              className="w-full rounded border border-gray-700 bg-[#151515] px-2 py-2 text-sm text-gray-200 disabled:opacity-60"
              value={presetChoice}
              disabled={!manifest?.configs?.length}
              onChange={(e) => e.target.value && onStartFromPreset(e.target.value)}
            >
              <option value="">Choose a starting point…</option>
              {(manifest?.configs ?? []).map((c) => (
                <option key={c.name} value={c.name}>
                  {c.label}
                </option>
              ))}
            </select>
            {!manifest?.configs?.length ? (
              <p className="mt-1 text-[11px] text-amber-400">
                Standard formats aren&apos;t available right now — you can still build your league
                from scratch below.
              </p>
            ) : loadError ? (
              <p className="mt-1 text-[11px] text-amber-400">{loadError}</p>
            ) : presetNote ? (
              <p className="mt-1 flex items-start gap-1 text-[11px] text-emerald-400">
                <Check className="mt-px h-3 w-3 shrink-0" />
                <span>{presetNote}</span>
              </p>
            ) : (
              <p className="mt-1 text-[11px] text-gray-500">
                Loads that format&apos;s scoring and roster, then edit anything below.
              </p>
            )}
          </div>
        </div>
      </section>

      {/* ── roster ───────────────────────────────────────────────────────────────────────── */}
      <RosterEditor roster={cfg.roster} onChange={(roster) => update({ roster })} />

      {/* ── scoring ──────────────────────────────────────────────────────────────────────── */}
      <section className="mt-6 rounded-lg border border-gray-800 bg-[#0f0f0f] p-4">
        <h2 className="text-sm font-semibold text-gray-200">Scoring</h2>
        <p className="mt-1 text-xs text-gray-500">
          Enter your league&apos;s values. A stat set to 0 simply does not score.
        </p>
        <div className="mt-4 space-y-5">
          {SCORING_GROUPS.map((group) => (
            <ScoringGroup
              key={group.id}
              group={group}
              perStat={cfg.scoring.per_stat}
              coverage={coverage.terms}
              onChange={setStat}
            />
          ))}
          <TePremiumRow cfg={cfg} onChange={update} />
        </div>
      </section>

      {/* ── captured-but-not-applied league rules ────────────────────────────────────────── */}
      <section className="mt-6 rounded-lg border border-gray-800 bg-[#0f0f0f] p-4">
        <h2 className="text-sm font-semibold text-gray-200">Other league rules</h2>
        <p className="mt-1 text-xs text-gray-500">
          These are saved with your league so its settings stay a faithful record — but they do not
          change any player&apos;s projection or the board, and we say so rather than implying they do.
        </p>
        <div className="mt-3 space-y-2">
          {CAPTURED_RULE_CATALOG.map((rule) => {
            const on = Boolean(cfg.captured_rules?.[rule.key])
            return (
              <label key={rule.key} className="flex cursor-pointer items-start gap-2.5">
                <input
                  type="checkbox"
                  className="mt-0.5 h-3.5 w-3.5 accent-sky-500"
                  checked={on}
                  onChange={(e) => {
                    const next = { ...(cfg.captured_rules ?? {}) }
                    if (e.target.checked) next[rule.key] = true
                    else delete next[rule.key]
                    update({ captured_rules: next })
                  }}
                />
                <span className="text-xs">
                  <span className="font-medium text-gray-300">{rule.label}</span>
                  <span className="ml-2 rounded border border-amber-500/30 bg-amber-500/10 px-1 py-0.5 text-[10px] text-amber-400">
                    not applied to the board
                  </span>
                  <span className="mt-0.5 block text-gray-500">{rule.help}</span>
                </span>
              </label>
            )
          })}
        </div>
      </section>

      {/* ── the honest coverage panel ────────────────────────────────────────────────────── */}
      <CoveragePanel terms={coverage.terms} byVerdict={byVerdict} />

      {/* ── save ─────────────────────────────────────────────────────────────────────────── */}
      {/* Sticky on mobile so Save is always reachable — the form is long and the button would
          otherwise sit far below the scoring grid. */}
      <section className="sticky bottom-0 z-10 mt-6 -mx-4 border-t border-gray-800 bg-[#0a0a0a]/95 px-4 py-3 backdrop-blur sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:px-0 sm:backdrop-blur-none">
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={onSave}
            disabled={errors.length > 0 || saveLeague.isPending}
            className="flex w-full items-center justify-center gap-1.5 rounded bg-sky-600 px-4 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-gray-700 sm:w-auto"
          >
            <Save className="h-4 w-4" />
            {saveLeague.isPending ? "Saving…" : leagueId ? "Save changes" : "Save league"}
          </button>
          {saved && !dirty && (
            <span className="flex items-center gap-1 text-xs text-emerald-400">
              <Check className="h-3.5 w-3.5" /> Saved — the board, rankings and draft tools now use
              this league.
            </span>
          )}
          {dirty && !saveLeague.isPending && (
            <span className="text-xs text-amber-400">Unsaved changes.</span>
          )}
          {saveLeague.isError && (
            <span className="text-xs text-red-400">
              Could not save. {(saveLeague.error as Error)?.message ?? "Please try again."}
            </span>
          )}
        </div>
        {errors.length > 0 && (
          <ul className="mt-2 text-xs text-red-400">
            {errors.map((e) => (
              <li key={e}>• {e}</li>
            ))}
          </ul>
        )}
      </section>

      {/* ── live preview ─────────────────────────────────────────────────────────────────── */}
      <BoardPreview preview={preview} />
    </div>
  )
}

function stripServerFields(l: SavedLeague): LeagueConfig {
  const { league_id: _id, user_id: _u, created_at: _c, updated_at: _up, ...cfg } = l
  return {
    ...cfg,
    scoring: {
      per_stat: { ...(cfg.scoring?.per_stat ?? {}) },
      position_bonuses: { ...(cfg.scoring?.position_bonuses ?? {}) },
    },
    roster: (cfg.roster ?? []).map((s) => ({ ...s, eligible: [...s.eligible] })),
    captured_rules: { ...(cfg.captured_rules ?? {}) },
  }
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-gray-500">{children}</label>
}

// ── roster ─────────────────────────────────────────────────────────────────────────────────────
function RosterEditor({
  roster,
  onChange,
}: {
  roster: RosterSlotConfig[]
  onChange: (r: RosterSlotConfig[]) => void
}) {
  const patch = (i: number, p: Partial<RosterSlotConfig>) =>
    onChange(roster.map((s, j) => (i === j ? { ...s, ...p } : s)))

  const toggleEligible = (i: number, pos: string) => {
    const s = roster[i]
    const has = s.eligible.includes(pos)
    patch(i, { eligible: has ? s.eligible.filter((p) => p !== pos) : [...s.eligible, pos] })
  }

  const starters = roster.filter((s) => !s.bench).reduce((n, s) => n + s.count, 0)
  const bench = roster.filter((s) => s.bench).reduce((n, s) => n + s.count, 0)

  return (
    <section className="mt-6 rounded-lg border border-gray-800 bg-[#0f0f0f] p-4">
      <h2 className="text-sm font-semibold text-gray-200">Roster</h2>
      <p className="mt-1 text-xs text-gray-500">
        Starting slots drive positional scarcity: more starters at a position means a deeper
        replacement level, which is what makes a QB and a WR comparable on one board.{" "}
        <span className="text-gray-400">
          Bench and IR slots never start, so they correctly have no effect on that.
        </span>{" "}
        A FLEX is any slot with more than one eligible position — tick every position it accepts
        (add QB for a SUPERFLEX).
      </p>

      {/* A CARD PER SLOT rather than a wide table: the table needed ~560px and forced horizontal
          scrolling on a phone, which is where a lot of draft-prep actually happens. Cards reflow to
          a single column and keep every control at a tappable size. */}
      <div className="mt-3 space-y-2">
        {roster.map((s, i) => (
          <div key={i} className="rounded border border-gray-800 bg-[#131313] p-3">
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-0 flex-1 basis-32">
                <FieldLabel>Slot</FieldLabel>
                <input
                  className="w-full rounded border border-gray-700 bg-[#151515] px-2 py-2 text-sm text-gray-200"
                  value={s.name}
                  onChange={(e) => patch(i, { name: e.target.value })}
                />
              </div>
              <div className="w-20 shrink-0">
                <FieldLabel>Count</FieldLabel>
                <input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={40}
                  className="w-full rounded border border-gray-700 bg-[#151515] px-2 py-2 text-sm text-gray-200"
                  value={s.count}
                  onChange={(e) => patch(i, { count: Number(e.target.value) })}
                />
              </div>
              <label className="flex shrink-0 cursor-pointer items-center gap-1.5 pb-2 text-xs text-gray-400">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-sky-500"
                  checked={s.bench}
                  onChange={(e) => patch(i, { bench: e.target.checked })}
                />
                Bench / IR
              </label>
              <button
                type="button"
                onClick={() => onChange(roster.filter((_, j) => j !== i))}
                className="ml-auto shrink-0 rounded p-2 text-gray-600 hover:bg-red-950/30 hover:text-red-400"
                aria-label={`Remove ${s.name}`}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-2">
              <FieldLabel>Eligible positions</FieldLabel>
              <div className="flex flex-wrap gap-1.5">
                {POSITIONS.map((p) => {
                  const on = s.eligible.includes(p)
                  return (
                    <button
                      key={p}
                      type="button"
                      aria-pressed={on}
                      onClick={() => toggleEligible(i, p)}
                      className={`rounded border px-2.5 py-1 text-xs font-semibold ${
                        on
                          ? "border-sky-500/40 bg-sky-500/15 text-sky-300"
                          : "border-gray-700 text-gray-600 hover:text-gray-400"
                      }`}
                    >
                      {p}
                    </button>
                  )
                })}
              </div>
              {s.bench && s.eligible.length === 0 && (
                <p className="mt-1 text-[11px] text-gray-500">Any position.</p>
              )}
              {!s.bench && s.eligible.length === 0 && (
                <p className="mt-1 text-[11px] text-amber-400">
                  A starting slot needs at least one eligible position.
                </p>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() =>
            onChange([...roster, { name: "NEW", count: 1, eligible: ["RB", "WR", "TE"], bench: false }])
          }
          className="flex items-center gap-1.5 rounded border border-gray-700 px-3 py-2 text-xs text-gray-300 hover:bg-gray-800"
        >
          <Plus className="h-3.5 w-3.5" /> Add slot
        </button>
        <span className="text-xs text-gray-500">
          {starters} starting · {bench} bench/IR
        </span>
      </div>
    </section>
  )
}

// ── scoring ────────────────────────────────────────────────────────────────────────────────────
function ScoringGroup({
  group,
  perStat,
  coverage,
  onChange,
}: {
  group: { id: string; label: string }
  perStat: Record<string, number>
  coverage: TermCoverage[]
  onChange: (key: string, value: number) => void
}) {
  const terms = SCORING_CATALOG.filter((t) => t.group === group.id)
  if (!terms.length) return null
  const verdictOf = (key: string) => coverage.find((c) => c.key === key)?.verdict

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400">{group.label}</h3>
      {group.id === "dst_points_allowed" && (
        <p className="mt-1 text-[11px] text-gray-500">
          Points allowed per game. If your league&apos;s table has a single &quot;14-20&quot; or
          &quot;35+&quot; tier, set both rows in that pair to the same value — that is an exact
          restatement of your table, not an approximation.
        </p>
      )}
      <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {terms.map((t) => {
          const verdict = verdictOf(t.key)
          return (
            <div key={t.key} className="flex items-center justify-between gap-2 rounded border border-gray-800 bg-[#131313] px-2.5 py-1.5">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-xs text-gray-300">{t.label}</span>
                  {verdict && verdict !== "applied" && (
                    <span
                      className={`shrink-0 rounded border px-1 py-0.5 text-[9px] font-medium ${VERDICT_STYLE[verdict]}`}
                      title={VERDICT_COPY[verdict]}
                    >
                      {verdict}
                    </span>
                  )}
                </div>
                {t.help && <p className="truncate text-[10px] text-gray-600" title={t.help}>{t.help}</p>}
              </div>
              <input
                type="number"
                step="any"
                inputMode="decimal"
                aria-label={t.label}
                className="w-20 shrink-0 rounded border border-gray-700 bg-[#151515] px-2 py-2 text-right text-sm text-gray-200"
                value={perStat[t.key] ?? 0}
                onChange={(e) => onChange(t.key, Number(e.target.value))}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** TE-premium is a per-POSITION bonus rather than a base weight, so it gets its own control. */
function TePremiumRow({
  cfg,
  onChange,
}: {
  cfg: LeagueConfig
  onChange: (p: Partial<LeagueConfig>) => void
}) {
  const value = cfg.scoring.position_bonuses?.TE?.rec ?? 0
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400">TE premium</h3>
      <div className="mt-2 flex items-center justify-between gap-2 rounded border border-gray-800 bg-[#131313] px-2.5 py-1.5 sm:max-w-sm">
        <span className="text-xs text-gray-300">Extra points per TE reception</span>
        <input
          type="number"
          step="any"
          inputMode="decimal"
          aria-label="Extra points per TE reception"
          className="w-20 rounded border border-gray-700 bg-[#151515] px-2 py-2 text-right text-sm text-gray-200"
          value={value}
          onChange={(e) => {
            const v = Number(e.target.value)
            const bonuses = { ...(cfg.scoring.position_bonuses ?? {}) }
            if (v) bonuses.TE = { ...(bonuses.TE ?? {}), rec: v }
            else if (bonuses.TE) {
              const { rec: _rec, ...rest } = bonuses.TE
              if (Object.keys(rest).length) bonuses.TE = rest
              else delete bonuses.TE
            }
            onChange({ scoring: { ...cfg.scoring, position_bonuses: bonuses } })
          }}
        />
      </div>
    </div>
  )
}

// ── coverage ───────────────────────────────────────────────────────────────────────────────────
function CoveragePanel({
  terms,
  byVerdict,
}: {
  terms: TermCoverage[]
  byVerdict: (v: string) => TermCoverage[]
}) {
  const labelOf = (key: string) => SCORING_CATALOG.find((t) => t.key === key)?.label ?? key
  const captured = byVerdict("captured")
  const derived = byVerdict("derived")
  const applied = byVerdict("applied")
  const approx = derived.filter((t) => !t.exact)

  return (
    <section className="mt-6 rounded-lg border border-gray-800 bg-[#0f0f0f] p-4">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-gray-200">What we actually apply</h2>
        <Info className="h-3.5 w-3.5 text-gray-600" />
      </div>
      <p className="mt-1 text-xs text-gray-500">
        Your settings are saved exactly as entered. This is the honest account of which of them move
        a number on the board — a stat we do not project is kept with your league and contributes
        nothing, rather than quietly scoring zero behind your back.
      </p>

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <CoverageCard verdict="applied" count={applied.length} label="Applied exactly" />
        <CoverageCard verdict="derived" count={derived.length} label="Folded to our resolution" />
        <CoverageCard verdict="captured" count={captured.length} label="Captured, not applied" />
      </div>

      {captured.length > 0 && (
        <div className="mt-4 rounded border border-amber-500/25 bg-amber-500/5 p-3">
          <p className="text-xs font-medium text-amber-300">
            Saved with your league, but not applied to the board
          </p>
          <p className="mt-1 text-[11px] text-gray-400">
            We do not project these stats, so we will not invent a value for them. Your league keeps
            the setting; the board simply does not include it.
          </p>
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-gray-400">
            {captured.map((t) => (
              <li key={t.key}>
                {labelOf(t.key)} <span className="text-gray-600">({num(t.weight, 2)})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {approx.length > 0 && (
        <div className="mt-3 rounded border border-sky-500/25 bg-sky-500/5 p-3">
          <p className="flex items-center gap-1.5 text-xs font-medium text-sky-300">
            <TriangleAlert className="h-3.5 w-3.5" /> Combined at our resolution
          </p>
          <p className="mt-1 text-[11px] text-gray-400">
            Our kicker projection resolves field goals at 0-39 / 40-49 / 50+. You have priced buckets
            inside one of those ranges differently, so they are combined by their attempt share. Set
            them to the same value and the match becomes exact.
          </p>
        </div>
      )}

      {terms.length === 0 && (
        <p className="mt-3 text-xs text-gray-500">Set a scoring value to see its coverage.</p>
      )}
    </section>
  )
}

function CoverageCard({ verdict, count, label }: { verdict: string; count: number; label: string }) {
  return (
    <div className={`rounded border px-3 py-2 ${VERDICT_STYLE[verdict]}`}>
      <div className="text-lg font-semibold">{count}</div>
      <div className="text-[11px] opacity-90">{label}</div>
    </div>
  )
}

// ── preview ────────────────────────────────────────────────────────────────────────────────────
function BoardPreview({ preview }: { preview: ReturnType<typeof useCustomBoard> }) {
  if (!preview) {
    return (
      <section className="mt-6">
        <h2 className="text-sm font-semibold text-gray-200">Preview</h2>
        <LoadingBlock label="Scoring your league…" />
      </section>
    )
  }
  const top = preview.players.slice(0, 12)
  if (!top.length) {
    return (
      <section className="mt-6">
        <h2 className="text-sm font-semibold text-gray-200">Preview</h2>
        <EmptyBlock
          title="Nothing to preview yet"
          detail="No projected player matches the positions this roster can start. Check the eligible positions on your starting slots."
        />
      </section>
    )
  }
  return (
    <section className="mt-6 rounded-lg border border-gray-800 bg-[#0f0f0f] p-4">
      <h2 className="text-sm font-semibold text-gray-200">Preview — your board&apos;s top 12</h2>
      <p className="mt-1 text-xs text-gray-500">
        Scored under the settings above. This is the same computation the League Board and Draft
        Optimizer run once you save.
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[480px] text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-left text-[11px] uppercase tracking-wide text-gray-500">
              <th className="py-1.5 pr-2 w-8">#</th>
              <th className="py-1.5 pr-2">Player</th>
              <th className="py-1.5 pr-2 w-14">Pos</th>
              <th className="py-1.5 pr-2 w-20 text-right">Points</th>
              <th className="py-1.5 w-20 text-right">VOR</th>
            </tr>
          </thead>
          <tbody>
            {top.map((p) => (
              <tr key={p.id} className="border-b border-gray-900">
                <td className="py-1.5 pr-2 text-gray-600">{p.ovrRank}</td>
                <td className="py-1.5 pr-2 text-gray-200">{p.name}</td>
                <td className="py-1.5 pr-2">
                  <PosBadge pos={p.pos} />
                </td>
                <td className="py-1.5 pr-2 text-right text-gray-300">{num(p.pts)}</td>
                <td className="py-1.5 text-right text-gray-300">{num(p.vor)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
