"use client"

// E8.2 — set up an MLB dynasty league, and see what it makes unavailable on the board.
//
// 🚪 UPLOAD ONLY, BY DECISION. E8.2a probed CBS for a compliant read and found none, so there is no
// "connect your league" button here and there never was one to remove. This screen NEVER asks for a
// platform password — the only thing it accepts is a file the user exported themselves.
//
// ⭐ THE SCREEN IS BUILT AROUND THE REVIEW QUEUE, not around a match percentage. Most of a fantasy
// roster is established major-leaguers who are not prospects, so "101 of 442 matched" is the
// EXPECTED shape of a working import and leading with it would train the user to distrust it. What
// actually deserves attention is small and specific — on the operator's real 442-player export it
// is eleven rows: a name matching two prospects (never guessed), a same-name player whose position
// contradicts the board, and a minors-slot stash we could not place.

import { useMemo, useRef, useState } from "react"
import { AlertTriangle, Check, Copy, Flag, Trash2, Upload, X } from "lucide-react"
import { EmptyBlock, LoadingBlock, SurfaceHeader } from "@/components/fantasy/shared"
import { Picker } from "@/components/ui/picker"
import {
  useActiveMlbLeague,
  useDeleteMlbLeague,
  useDraftPick,
  useMlbLeague,
  useMlbLeagues,
  useResolveMlbRosterRow,
  useSaveMlbLeague,
  useSetMyTeam,
  useUploadTeamRoster,
} from "@/lib/fantasy-queries"
import { useProspectBoard } from "@/lib/fantasy-queries"
import { STATUS_LABEL, coverageGapsCsv, matchSummary } from "@/lib/mlb-league"
import type { LeagueDetail, ReviewRow, RosterEntry } from "@/lib/mlb-league"

const SCOPES = [
  { value: "AL", label: "American League only" },
  { value: "NL", label: "National League only" },
  { value: "BOTH", label: "Both leagues" },
]

/** The documented upload schema, shown in the UI rather than buried in a doc — a user who cannot
 *  export a CBS grid needs to know what shape to reshape their own export into. */
const LONG_FORM_EXAMPLE = `Team,Player,Position,Status
Antonio Picante,Samuel Basallo,C,Minors
Antonio Picante,Jasson Dominguez,OF,
Red Paps,Kumar Rocker,P,IL`

/** What each review tier actually means, in the user's terms. Keyed by tier so a new tier added
 *  server-side falls back to the honest generic line rather than silently borrowing another
 *  tier's explanation — which is how a "we couldn't place him" row would come to read as
 *  "we matched him". */
const REVIEW_EXPLANATION: Record<string, string> = {
  ambiguous:
    "This name matches more than one prospect in your league's scope, so it was NOT guessed. " +
    "Until you pick one, all of them still read as available.",
  position_conflict:
    "A prospect has this name, but he doesn't play the position you have this player slotted at " +
    "— so this is almost certainly a different player who happens to share a name, and we did " +
    "not match them. If we got that wrong, pick him below.",
  contested:
    "Another player on your rosters already matched this prospect, and a player can only be on " +
    "one roster — so one of the two is someone else. We kept the first and left this one " +
    "unmatched rather than overwriting it.",
  variant:
    "Matched on a name-rendering difference rather than an exact one. It is already applied — " +
    "confirm it is the right player.",
  unresolved:
    "A minors-slot stash we could not place on the board. Most likely he is simply not ranked; " +
    "if he IS on the board, he is currently showing as available.",
}

function StatusChip({ status }: { status: string | null }) {
  if (!status) return null
  const tone =
    status === "minors"
      ? "text-sky-400 bg-sky-500/10 border-sky-500/30"
      : status === "injured"
        ? "text-amber-400 bg-amber-500/10 border-amber-500/30"
        : "text-gray-400 bg-gray-500/10 border-gray-500/30"
  return (
    <span className={`ml-1.5 rounded border px-1 py-px text-[10px] uppercase ${tone}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  )
}

// ── upload ───────────────────────────────────────────────────────────────────────────────────

function UploadPanel({
  leagueId,
  initialName,
  initialScope,
  onSaved,
}: {
  leagueId?: string
  initialName?: string
  initialScope?: string
  onSaved: (id: string) => void
}) {
  const [name, setName] = useState(initialName ?? "My dynasty league")
  const [scope, setScope] = useState(initialScope ?? "AL")
  const [text, setText] = useState("")
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const save = useSaveMlbLeague()

  const submit = async () => {
    setError(null)
    try {
      const result = await save.mutateAsync({ name, text, leagueScope: scope, leagueId })
      onSaved(result.league.league_id)
      setText("")
    } catch (e) {
      // The API's own `detail` is written for a user ("That upload has no data rows…"), so it is
      // shown verbatim rather than replaced with a generic failure message (E9.26b, outward).
      setError(e instanceof Error ? e.message : "The upload could not be read.")
    }
  }

  const readFile = (file: File) => {
    const reader = new FileReader()
    reader.onload = () => setText(String(reader.result ?? ""))
    reader.onerror = () => setError("That file could not be read.")
    reader.readAsText(file)
  }

  return (
    <div className="space-y-4 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-[11px] uppercase tracking-wide text-gray-500">
            League name
          </span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={80}
            className="w-full rounded border border-[#262626] bg-[#0a0a0a] px-2 py-1.5 text-base sm:text-sm text-gray-200"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-[11px] uppercase tracking-wide text-gray-500">
            League scope
          </span>
          <Picker
            value={scope}
            onValueChange={setScope}
            options={SCOPES}
            ariaLabel="League scope"
          />
          <span className="mt-1 block text-[11px] text-gray-600">
            A dynasty league is usually one league only. This scopes the board before anything is
            subtracted, so an NL prospect never counts against an AL league.
          </span>
        </label>
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-wide text-gray-500">
            Paste your roster export
          </span>
          <button
            onClick={() => fileRef.current?.click()}
            className="inline-flex items-center gap-1 rounded border border-[#262626] px-2 py-1 text-[11px] text-gray-400 hover:text-gray-200"
          >
            <Upload className="h-3 w-3" /> Choose a file
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.tsv,.txt,text/csv,text/plain"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) readFile(file)
            }}
          />
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={8}
          spellCheck={false}
          placeholder={`Team,C,1B,2B,3B,SS,MI,CI,OF,DH,P\nAntonio Picante,C Jensen,N Kurtz,…`}
          className="w-full rounded border border-[#262626] bg-[#0a0a0a] p-2 font-mono text-base sm:text-[11px] text-gray-300"
        />
      </div>

      <details className="text-[11px] text-gray-500">
        <summary className="cursor-pointer text-gray-400">What can I paste here?</summary>
        <div className="mt-2 space-y-2">
          <p>
            <span className="text-gray-300">A CBS roster grid</span> — one row per fantasy team,
            with a column per position slot. Players run together inside a cell; that is expected
            and it is read correctly, including <code>(M)</code> minors stashes,{" "}
            <code>(I)</code> injured and <code>(R)</code> reserve.
          </p>
          <p>
            <span className="text-gray-300">Or any platform</span>, reshaped into one row per
            player. This is the documented fallback so the feature is not tied to CBS:
          </p>
          <pre className="overflow-x-auto rounded bg-[#0a0a0a] p-2 text-[10px] text-gray-400">
            {LONG_FORM_EXAMPLE}
          </pre>
          <p>
            A <code>Team</code> (or Owner) column and a <code>Player</code> column are required.
            Position and Status are optional.
          </p>
        </div>
      </details>

      {error && (
        <p className="flex items-start gap-2 rounded border border-rose-500/30 bg-rose-500/10 p-2 text-xs text-rose-300">
          <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" />
          {error}
        </p>
      )}

      <button
        onClick={submit}
        disabled={!text.trim() || save.isPending}
        className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
      >
        {save.isPending ? "Reading…" : leagueId ? "Replace rosters" : "Import rosters"}
      </button>
      {leagueId && (
        <p className="text-[11px] text-gray-600">
          A re-upload REPLACES this league&apos;s rosters, so a player you have since dropped stops
          counting as rostered. Your manual name fixes and any draft picks are kept.
        </p>
      )}
    </div>
  )
}

// ── review queue ─────────────────────────────────────────────────────────────────────────────

function ReviewQueue({ league, rows }: { league: LeagueDetail; rows: ReviewRow[] }) {
  const resolve = useResolveMlbRosterRow(league.league.league_id)
  if (!rows.length) {
    return (
      <p className="rounded border border-emerald-500/25 bg-emerald-500/5 p-3 text-xs text-emerald-300">
        <Check className="mr-1 inline h-3.5 w-3.5" />
        Nothing to review — every name that could be a board prospect resolved to one.
      </p>
    )
  }
  return (
    <div className="space-y-2">
      {rows.map((row) => (
        <div key={row.key} className="rounded border border-[#262626] bg-[#0f0f0f] p-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium text-gray-200">{row.name}</span>
            <StatusChip status={row.status} />
            <span className="text-[11px] text-gray-500">
              {row.team} · {row.slot}
            </span>
            <span
              className={`ml-auto rounded border px-1.5 py-px text-[10px] uppercase ${
                row.confidence === "ambiguous" || row.confidence === "contested"
                  ? "border-amber-500/30 bg-amber-500/10 text-amber-400"
                  : row.confidence === "variant"
                    ? "border-sky-500/30 bg-sky-500/10 text-sky-400"
                    : "border-gray-500/30 bg-gray-500/10 text-gray-400"
              }`}
            >
              {row.confidence.replace("_", " ")}
            </span>
          </div>

          <p className="mt-1 text-[11px] leading-relaxed text-gray-500">
            {REVIEW_EXPLANATION[row.confidence] ?? REVIEW_EXPLANATION.unresolved}
          </p>

          <div className="mt-2 flex flex-wrap gap-1.5">
            {row.candidates.map((c) => (
              <button
                key={c.rank}
                onClick={() => resolve.mutate({ [row.key]: c.rank })}
                disabled={resolve.isPending}
                className="rounded border border-[#333] px-2 py-1 text-[11px] text-gray-300 hover:border-emerald-500/50 hover:text-emerald-300 disabled:opacity-40"
              >
                #{c.rank} {c.name}
                {c.org ? ` · ${c.org}` : ""}
                {c.pos ? ` · ${c.pos}` : ""}
              </button>
            ))}
            {/* ⭐ TWO dismissals, not one. "Not a prospect" is Salvador Perez; "missing from our
                board" is a prospect somebody is spending a dynasty roster spot on that we do not
                carry — which is a coverage signal worth keeping, not a row to delete. */}
            <button
              onClick={() => resolve.mutate({ [row.key]: "missing_from_board" })}
              disabled={resolve.isPending}
              className="inline-flex items-center gap-1 rounded border border-amber-500/40 px-2 py-1 text-[11px] text-amber-400 hover:bg-amber-500/10 disabled:opacity-40"
            >
              <Flag className="h-3 w-3" /> Missing from our board
            </button>
            <button
              onClick={() => resolve.mutate({ [row.key]: "not_a_prospect" })}
              disabled={resolve.isPending}
              className="inline-flex items-center gap-1 rounded border border-[#333] px-2 py-1 text-[11px] text-gray-500 hover:text-gray-300 disabled:opacity-40"
            >
              <X className="h-3 w-3" /> Not a prospect
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

/** Replace ONE team from a per-team CBS "roster overview" export.
 *
 *  ⭐ Why offer this alongside the whole-league grid: the per-team export carries FULL NAMES and the
 *  MLB club, and on the live AL board the full name removes the ambiguity class outright (9
 *  ambiguous board keys → 0). The grid stays the fast path for the whole league; this is how you
 *  fix the one team the grid could not resolve, without re-uploading everything. */
function TeamUploadPanel({ league }: { league: LeagueDetail }) {
  const upload = useUploadTeamRoster(league.league.league_id)
  const [team, setTeam] = useState("")
  const [text, setText] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  const submit = async () => {
    setError(null)
    setDone(null)
    try {
      const res = await upload.mutateAsync({ team: team.trim(), text })
      setDone(`Imported ${res.imported} players for ${team.trim()} (replaced ${res.replaced}).`)
      setText("")
    } catch (e) {
      setError(e instanceof Error ? e.message : "That roster could not be read.")
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-[#262626] bg-[#0f0f0f] p-4">
      <div>
        <h3 className="text-sm font-medium text-gray-200">Upload one team&apos;s roster</h3>
        <p className="mt-0.5 text-[11px] leading-relaxed text-gray-500">
          A per-team CBS export carries full names and each player&apos;s MLB club, where the
          league-wide grid gives only an initial and a surname. That removes the “this name matches
          two prospects” problem entirely, so it is the way to fix a team the grid left unresolved —
          and it makes the coverage report below actionable.
        </p>
      </div>
      <label className="block">
        <span className="mb-1 block text-[11px] uppercase tracking-wide text-gray-500">
          Which team is this? (the export doesn&apos;t say)
        </span>
        <input
          value={team}
          onChange={(e) => setTeam(e.target.value)}
          list="mlb-league-teams"
          maxLength={80}
          placeholder="e.g. Statcast and Chill"
          className="w-full rounded border border-[#262626] bg-[#0a0a0a] px-2 py-1.5 text-base sm:text-sm text-gray-200"
        />
        <datalist id="mlb-league-teams">
          {league.teams.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
      </label>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={6}
        spellCheck={false}
        placeholder={"Batters\n,Pos,Players, 8/3, …\n,C,Dillon Dingler C | DET ,…"}
        className="w-full rounded border border-[#262626] bg-[#0a0a0a] p-2 font-mono text-base sm:text-[11px] text-gray-300"
      />
      {error && (
        <p className="flex items-start gap-2 rounded border border-rose-500/30 bg-rose-500/10 p-2 text-xs text-rose-300">
          <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" />
          {error}
        </p>
      )}
      {done && <p className="text-xs text-emerald-400">{done}</p>}
      <button
        onClick={submit}
        disabled={!team.trim() || !text.trim() || upload.isPending}
        className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
      >
        {upload.isPending ? "Reading…" : "Replace this team"}
      </button>
    </div>
  )
}

// ── board coverage ───────────────────────────────────────────────────────────────────────────

/** ⭐ Prospects the league is rostering that our board does not carry.
 *
 *  This panel exists because the signal was previously thrown away. A player in somebody's MINORS
 *  slot who matches no board row is not noise — a competitive dynasty owner is spending a roster
 *  spot on him, which is independent evidence he is worth tracking. It is deliberately EXPORTABLE:
 *  the point is to get these players onto the board, so the output has to leave this screen. */
function CoverageGaps({ league }: { league: LeagueDetail }) {
  const [copied, setCopied] = useState(false)
  const gaps = league.coverage_gaps ?? []
  if (!gaps.length) {
    return (
      <p className="rounded border border-[#262626] bg-[#0f0f0f] p-3 text-xs text-gray-500">
        No coverage gaps — every minors-slot stash in this league resolved to a board row.
      </p>
    )
  }
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(coverageGapsCsv(gaps))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      /* clipboard unavailable — the table below is still readable and selectable */
    }
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline gap-2">
        <p className="text-xs leading-relaxed text-gray-400">
          {gaps.length} rostered {gaps.length === 1 ? "player" : "players"} look like prospects the
          board does not carry. Somebody is spending a dynasty roster spot on them, which is a
          reason to consider tracking them.
        </p>
        <button
          onClick={copy}
          className="ml-auto inline-flex items-center gap-1 rounded border border-[#262626] px-2 py-1 text-[11px] text-gray-400 hover:text-gray-200"
        >
          <Copy className="h-3 w-3" /> {copied ? "Copied" : "Copy as CSV"}
        </button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-[#262626]">
        <table className="w-full text-left text-[11px]">
          <thead className="bg-[#0f0f0f] text-[10px] uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-3 py-1.5">Player</th>
              <th className="px-3 py-1.5">Pos</th>
              <th className="px-3 py-1.5">MLB</th>
              <th className="px-3 py-1.5">Roster spot</th>
              <th className="px-3 py-1.5">Rostered by</th>
              <th className="px-3 py-1.5">Flagged</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1a1a1a]">
            {gaps.map((g) => (
              <tr key={g.key}>
                <td className="px-3 py-1.5 font-medium text-gray-200">{g.name}</td>
                <td className="px-3 py-1.5 text-gray-400">{g.positions ?? g.slot}</td>
                <td className="px-3 py-1.5 text-gray-400">{g.org ?? "—"}</td>
                <td className="px-3 py-1.5 text-gray-400">
                  {g.status ? (STATUS_LABEL[g.status] ?? g.status) : "active"}
                </td>
                <td className="px-3 py-1.5 text-gray-500">{g.team}</td>
                <td className="px-3 py-1.5">
                  <span
                    className={
                      g.source === "confirmed"
                        ? "text-amber-400"
                        : "text-gray-600"
                    }
                  >
                    {g.source === "confirmed" ? "by you" : "auto"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] leading-relaxed text-gray-600">
        “auto” = an unplaceable minors-slot stash. “by you” = you marked it missing in Review. An MLB
        club is shown when the upload carried one — a per-team export does, the league-wide grid does
        not, which is the main reason to use one.
      </p>
    </div>
  )
}

// ── rosters ──────────────────────────────────────────────────────────────────────────────────

function TeamRosters({ league }: { league: LeagueDetail }) {
  const boardQ = useProspectBoard()
  const nameByRank = useMemo(() => {
    const map = new Map<number, string>()
    for (const p of boardQ.data?.players ?? []) map.set(p.rank, p.name)
    return map
  }, [boardQ.data])

  const byTeam = useMemo(() => {
    const map = new Map<string, RosterEntry[]>()
    for (const e of league.entries) {
      const list = map.get(e.team) ?? []
      list.push(e)
      map.set(e.team, list)
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [league.entries])

  // Which board prospects each team holds — the draft-relevant half of a roster.
  const prospectsByTeam = useMemo(() => {
    const map = new Map<string, { rank: number; name: string; source: string }[]>()
    for (const [rank, held] of Object.entries(league.rostered)) {
      const list = map.get(held.team) ?? []
      list.push({
        rank: Number(rank),
        name: nameByRank.get(Number(rank)) ?? `#${rank}`,
        source: held.source,
      })
      map.set(held.team, list)
    }
    for (const list of map.values()) list.sort((a, b) => a.rank - b.rank)
    return map
  }, [league.rostered, nameByRank])

  const teams = byTeam.length
    ? byTeam
    : [...prospectsByTeam.keys()].sort().map((t) => [t, [] as RosterEntry[]] as const)

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {teams.map(([team, entries]) => {
        const prospects = prospectsByTeam.get(team) ?? []
        const mine = !!league.my_team && team === league.my_team
        return (
          <div
            key={team}
            className={`rounded-lg border p-3 ${
              mine ? "border-emerald-500/40 bg-emerald-500/5" : "border-[#262626] bg-[#0f0f0f]"
            }`}
          >
            <div className="flex items-baseline justify-between">
              <h3 className="truncate text-sm font-medium text-gray-200">
                {mine && <span className="text-emerald-400">★ </span>}
                {team}
              </h3>
              <span className="text-[11px] text-gray-600">
                {entries.length} rostered · {prospects.length} on the board
              </span>
            </div>
            {prospects.length > 0 && (
              <ul className="mt-2 space-y-0.5">
                {prospects.map((p) => (
                  <li key={p.rank} className="text-[11px] text-emerald-300/90">
                    #{p.rank} {p.name}
                    {p.source === "draft" && (
                      <span className="ml-1 text-[10px] text-gray-500">(drafted here)</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <details className="mt-2">
              <summary className="cursor-pointer text-[11px] text-gray-500 hover:text-gray-300">
                Full roster
              </summary>
              <ul className="mt-1 columns-2 text-[11px] text-gray-500">
                {entries.map((e, i) => (
                  <li key={`${e.name}-${i}`} className="break-inside-avoid">
                    {e.name}
                    <StatusChip status={e.status} />
                  </li>
                ))}
              </ul>
            </details>
          </div>
        )
      })}
    </div>
  )
}

// A Radix `Select` cannot carry an empty-string item value (it reserves "" for "nothing
// selected" — see the Picker's own doc comment), so "not set" needs a real sentinel here.
const NOT_SET = "__not_set__"

/** E8.6 — which of the league's teams is the user's own, so the prospect board can highlight it. */
function MyTeamPicker({ league }: { league: LeagueDetail }) {
  const setMyTeam = useSetMyTeam(league.league.league_id)
  // A league can have draft picks seating a team the upload never carried (E8.2's own design —
  // "a draft can seat a team whose roster was not in the upload") — offer those too, so a
  // brand-new draft-only league still has something to pick from.
  const options = [...new Set([...league.teams, ...Object.values(league.picks)])].sort()

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[#262626] bg-[#0f0f0f] p-3">
      <span className="text-xs text-gray-400">Which team is yours?</span>
      <Picker
        value={league.my_team ?? NOT_SET}
        onValueChange={(v) => setMyTeam.mutate(v === NOT_SET ? "" : v)}
        ariaLabel="Which team is yours"
        disabled={setMyTeam.isPending}
        options={[
          { value: NOT_SET, label: "Not set" },
          ...options.map((t) => ({ value: t, label: t })),
        ]}
      />
      <span className="text-[11px] leading-relaxed text-gray-600">
        Highlights your own roster on the prospect board.
        {options.length === 0 && " Upload a roster or make a draft pick first."}
      </span>
    </div>
  )
}

function DraftPicks({ league }: { league: LeagueDetail }) {
  const boardQ = useProspectBoard()
  const pick = useDraftPick(league.league.league_id)
  const entries = Object.entries(league.picks)
  if (!entries.length) return null
  const nameByRank = new Map((boardQ.data?.players ?? []).map((p) => [p.rank, p.name]))
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-3">
      <h3 className="text-sm font-medium text-gray-200">Marked drafted this session</h3>
      <p className="mt-0.5 text-[11px] text-gray-600">
        Recorded on the board as picks happen. These override the uploaded snapshot, because the
        upload is a point-in-time file and a pick is what just happened.
      </p>
      <ul className="mt-2 space-y-1">
        {entries.map(([rank, team]) => (
          <li key={rank} className="flex items-center gap-2 text-[11px]">
            <span className="text-gray-300">
              #{rank} {nameByRank.get(Number(rank)) ?? ""}
            </span>
            <span className="text-gray-500">→ {team}</span>
            <button
              onClick={() => pick.mutate({ rank: Number(rank), team: null })}
              disabled={pick.isPending}
              className="ml-auto text-gray-600 hover:text-rose-400 disabled:opacity-40"
              aria-label={`Undo pick ${rank}`}
            >
              <X className="h-3 w-3" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ── the surface ──────────────────────────────────────────────────────────────────────────────

export function MlbLeagueSetup() {
  const leaguesQ = useMlbLeagues()
  const [activeId, setActiveId] = useActiveMlbLeague()
  const leagues = leaguesQ.data?.leagues ?? []
  const selectedId = activeId && leagues.some((l) => l.league_id === activeId) ? activeId : null
  const leagueQ = useMlbLeague(selectedId)
  const del = useDeleteMlbLeague()
  const [replacing, setReplacing] = useState(false)
  const [tab, setTab] = useState<"review" | "coverage" | "rosters">("review")

  const league = leagueQ.data

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <SurfaceHeader
        title="My league"
        blurb="Import your league's rosters so the prospect board can show who is actually draftable."
      />

      {leaguesQ.isLoading && <LoadingBlock label="Loading your leagues" />}

      {!leaguesQ.isLoading && leagues.length === 0 && (
        <div className="mt-4 space-y-3">
          <p className="text-xs leading-relaxed text-gray-500">
            We could not find a compliant way to read a CBS league directly — their API is retired,
            league pages need a login, and their robots.txt disallows automated access — so this
            works from an export you download yourself. Nothing here asks for a platform password.
          </p>
          <UploadPanel onSaved={setActiveId} />
        </div>
      )}

      {leagues.length > 0 && (
        <div className="mt-4 space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Picker
              value={selectedId ?? ""}
              onValueChange={(v) => setActiveId(v || null)}
              placeholder="Choose a league"
              ariaLabel="Active league"
              options={leagues.map((l) => ({
                value: l.league_id,
                label: `${l.name} · ${l.league_scope} · ${l.team_count} teams`,
              }))}
            />
            <button
              onClick={() => setReplacing((r) => !r)}
              className="rounded border border-[#262626] px-2 py-1.5 text-xs text-gray-400 hover:text-gray-200"
            >
              {replacing ? "Cancel" : selectedId ? "Re-upload rosters" : "Add a league"}
            </button>
            {selectedId && (
              <button
                onClick={() => {
                  if (confirm("Delete this league and its roster data?")) {
                    del.mutate(selectedId, { onSuccess: () => setActiveId(null) })
                  }
                }}
                className="inline-flex items-center gap-1 rounded border border-[#262626] px-2 py-1.5 text-xs text-gray-500 hover:border-rose-500/40 hover:text-rose-400"
              >
                <Trash2 className="h-3 w-3" /> Delete
              </button>
            )}
          </div>

          {replacing && (
            <UploadPanel
              leagueId={selectedId ?? undefined}
              initialName={league?.league.name}
              initialScope={league?.league.league_scope}
              onSaved={(id) => {
                setActiveId(id)
                setReplacing(false)
              }}
            />
          )}

          {leagueQ.isLoading && <LoadingBlock label="Matching your rosters to the board" />}

          {leagueQ.error && (
            <EmptyBlock
              title="That league could not be read"
              detail="Its roster data is saved — this is a read failure, not a lost league. Try again in a moment."
            />
          )}

          {league && (
            <>
              <div className="rounded-lg border border-[#262626] bg-[#0f0f0f] p-3">
                <p className="text-sm text-gray-300">{matchSummary(league.counts)}</p>
                <p className="mt-1.5 text-[11px] leading-relaxed text-gray-500">
                  {league.framing}
                </p>
              </div>

              <MyTeamPicker league={league} />

              <DraftPicks league={league} />

              <div className="flex gap-1 border-b border-[#262626]">
                {(["review", "coverage", "rosters"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className={`px-3 py-1.5 text-xs capitalize ${
                      tab === t
                        ? "border-b-2 border-emerald-500 text-gray-200"
                        : "text-gray-500 hover:text-gray-300"
                    }`}
                  >
                    {t === "review"
                      ? `Review${league.review.length ? ` (${league.review.length})` : ""}`
                      : t === "coverage"
                        ? `Board coverage${
                            league.coverage_gaps?.length ? ` (${league.coverage_gaps.length})` : ""
                          }`
                        : `Rosters (${league.teams.length})`}
                  </button>
                ))}
              </div>

              {tab === "review" && <ReviewQueue league={league} rows={league.review} />}
              {tab === "coverage" && <CoverageGaps league={league} />}
              {tab === "rosters" && (
                <div className="space-y-4">
                  <TeamRosters league={league} />
                  <TeamUploadPanel league={league} />
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
